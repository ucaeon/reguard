import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from dotenv import dotenv_values
from pyspark.sql import SparkSession, functions as F

from pipelines.spark.normalize import normalize
from pipelines.spark.sink import save_batch

ROOT = Path(__file__).resolve().parents[2]


def run(
    spark,
    bootstrap,
    topic,
    checkpoint,
    db,
    available_now=False,
    max_offsets=1000,
    match_food=True,
):
    checkpoint = Path(checkpoint).resolve()
    checkpoint.mkdir(parents=True, exist_ok=True)
    identity = checkpoint / "reguard-query.json"
    target = {k: db.get(k) for k in ("host", "port", "dbname", "user", "options")}
    if identity.exists():
        saved = json.loads(identity.read_text())
        if (
            saved["topic"] != topic
            or saved["bootstrap"] != bootstrap
            or saved["database"] != db["dbname"]
            or saved.get("target") != target
        ):
            raise ValueError("CHECKPOINT_TARGET_MISMATCH")
    else:
        saved = {
            "query_id": str(uuid4()),
            "topic": topic,
            "bootstrap": bootstrap,
            "database": db["dbname"],
            "target": target,
        }
        with identity.open("x") as output:
            json.dump(saved, output)
    source = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "true")
        .option("maxOffsetsPerTrigger", max_offsets)
        .load()
    )
    parsed = source.select(
        "topic",
        "partition",
        "offset",
        F.col("value").cast("string").alias("raw"),
        F.col("key").cast("string").alias("key"),
    ).withColumn("normalized", F.udf(normalize, "string")("raw", "key"))

    def write(batch, batch_id):
        save_batch(batch.toLocalIterator(), batch_id, saved["query_id"], db, match_food)

    writer = parsed.writeStream.foreachBatch(write).option(
        "checkpointLocation", str(checkpoint)
    )
    return (
        writer.trigger(availableNow=True).start()
        if available_now
        else writer.trigger(processingTime="10 seconds").start()
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--available-now", action="store_true")
    parser.add_argument(
        "--checkpoint", type=Path, default=ROOT / "checkpoints/safety-raw-v1"
    )
    args = parser.parse_args()
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    os.environ["PYSPARK_PYTHON"] = sys.executable
    db = {
        "host": env.get("DB_HOST", "127.0.0.1"),
        "port": env.get("DB_PORT", "15432"),
        "dbname": "reguard_safety",
        "user": "reguard_safety",
        "password": env.get("SAFETY_DB_PASSWORD"),
        "connect_timeout": 10,
    }
    spark = (
        SparkSession.builder.master("local[2]")
        .appName("reguard-raw-normalization")
        .config(
            "spark.jars" if env.get("SPARK_KAFKA_JARS") else "spark.jars.packages",
            (
                ",".join(
                    str(p) for p in sorted(Path(env["SPARK_KAFKA_JARS"]).glob("*.jar"))
                )
                if env.get("SPARK_KAFKA_JARS")
                else "org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.3"
            ),
        )
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    try:
        query = run(
            spark,
            env.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:19092"),
            "reguard.raw-records.v1",
            args.checkpoint,
            db,
            args.available_now,
        )
        query.awaitTermination()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
