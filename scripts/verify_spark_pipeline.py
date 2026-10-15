import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from dotenv import dotenv_values
import psycopg
from psycopg import sql
from pyspark.sql import SparkSession

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.spark.streaming_job import run
from pipelines.spark.tests.test_normalize import envelope
from pipelines.spark.sink import save_batch
from pipelines.spark.normalize import normalize


def main():
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    os.environ["PYSPARK_PYTHON"] = sys.executable
    db = {
        "host": env.get("DB_HOST", "127.0.0.1"),
        "port": env.get("DB_PORT", "15432"),
        "dbname": "reguard_safety",
        "user": "reguard_safety",
        "password": env["SAFETY_DB_PASSWORD"],
    }
    schema = "spark_test_" + uuid4().hex
    topic = "reguard.raw-test." + uuid4().hex
    bootstrap = env.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:19092")
    admin = AdminClient({"bootstrap.servers": bootstrap})
    spark = None
    created = False
    try:
        with psycopg.connect(**db) as c:
            c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            for p in sorted(
                (ROOT / "services/safety-service/src/main/resources/db/migration").glob(
                    "V*.sql"
                )
            ):
                c.execute(p.read_text())
        scoped = {**db, "options": "-c search_path=" + schema}
        admin.create_topics([NewTopic(topic, num_partitions=3, replication_factor=1)])[
            topic
        ].result(15)
        created = True
        producer = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
        fixtures = [
            (
                "FOOD_I1250",
                "001",
                {
                    "PRDLST_REPORT_NO": "001",
                    "PRDLST_NM": "시험 식품",
                    "BSSH_NM": "시험 회사",
                    "LAST_UPDT_DTM": "20260928",
                },
            ),
            (
                "FOOD_I0030",
                "002",
                {"PRDLST_REPORT_NO": "002", "PRDLST_NM": "시험 비타민"},
            ),
            (
                "FOOD_I0490",
                "r1",
                {
                    "RTRVLDSUSE_SEQ": "r1",
                    "PRDTNM": "시험 식품",
                    "PRDLST_REPORT_NO": "001",
                    "RTRVLPRVNS": "원인 A",
                },
            ),
            (
                "SAFETY_KC",
                "1",
                {
                    "certUid": 1,
                    "productName": "완구",
                    "certNum": "AB123-456",
                    "modelName": "X1",
                },
            ),
            (
                "SAFETY_RECALL",
                "r2",
                {
                    "recallUid": "r2",
                    "recallProductName": "완구",
                    "certNum": "AB123-456",
                    "recallModelName": "X1",
                },
            ),
        ]
        events = [envelope(*f) for f in fixtures]
        for key, raw in events + [events[0]]:
            producer.produce(topic, key=key, value=raw)
        producer.produce(topic, key="bad", value="{bad json")
        assert producer.flush(15) == 0
        spark = (
            SparkSession.builder.master("local[2]")
            .appName("reguard-spark-verification")
            .config(
                "spark.jars.packages",
                "org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.3",
            )
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")

        def scalar(query):
            with psycopg.connect(**scoped) as c:
                return c.execute(query).fetchone()[0]

        with tempfile.TemporaryDirectory() as temp:
            checkpoint = Path(temp) / "checkpoint"
            run(spark, bootstrap, topic, checkpoint, scoped, True).awaitTermination()
            assert scalar("SELECT count(*) FROM products") == 3
            assert scalar("SELECT count(*) FROM recalls") == 2
            assert scalar("SELECT count(*) FROM ingestion_events") == 5
            assert scalar("SELECT count(*) FROM ingestion_quarantine") == 1
            assert scalar("SELECT count(*) FROM recall_product_matches") == 2
            run(
                spark, bootstrap, topic, Path(temp) / "replay", scoped, True
            ).awaitTermination()
            assert scalar("SELECT max(revision) FROM recalls") == 1
            payload = {**fixtures[2][2], "RTRVLPRVNS": "원인 B"}
            key, raw = envelope(
                "FOOD_I0490", "r1", payload, "2026-09-29T01:00:00+00:00"
            )
            producer.produce(topic, key=key, value=raw)
            producer.flush(15)
            run(spark, bootstrap, topic, checkpoint, scoped, True).awaitTermination()
            assert (
                scalar("SELECT revision FROM recalls WHERE source_recall_id='r1'") == 2
            )
            key, raw = envelope(*fixtures[2], collected="2026-09-29T00:30:00+00:00")
            producer.produce(topic, key=key, value=raw)
            producer.flush(15)
            run(spark, bootstrap, topic, checkpoint, scoped, True).awaitTermination()
            assert (
                scalar("SELECT reason FROM recalls WHERE source_recall_id='r1'")
                == "원인 B"
            )

            original_key, original_raw = events[0]
            conflict = json.loads(normalize(original_raw, original_key))
            conflict["record"]["content_hash"] = "f" * 64
            healthy_key, healthy_raw = envelope("FOOD_I1250", "003", {"PRDLST_REPORT_NO": "003", "PRDLST_NM": "정상 후속 식품"})
            metrics = save_batch([{"topic": "conflict", "partition": 0, "offset": 0,
                "raw": "test conflicting event", "normalized": json.dumps(conflict)}, {"topic": "conflict", "partition": 0, "offset": 1,
                "raw": healthy_raw, "normalized": normalize(healthy_raw, healthy_key)}], 97, "conflict-test", scoped)
            assert metrics["quarantined"] == 1 and metrics["applied"] == 1
            assert scalar("SELECT name FROM products WHERE source_record_id='003'") == "정상 후속 식품"
            assert scalar("SELECT count(*) FROM ingestion_quarantine WHERE reason='EVENT_ID_CONTENT_CONFLICT'") == 1
            assert scalar("SELECT name FROM products WHERE source_record_id='001'") == "시험 식품"
            print("PASS: event ID collision quarantined without overwriting accepted data")

            def interrupted():
                yield {
                    "topic": "rollback",
                    "partition": 0,
                    "offset": 0,
                    "raw": raw,
                    "normalized": normalize(raw, key),
                }
                raise RuntimeError("TEST_ABORT")

            try:
                save_batch(interrupted(), 99, "rollback", scoped)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Rollback not triggered")
            assert (
                scalar("SELECT count(*) FROM ingestion_offsets WHERE topic='rollback'")
                == 0
            )
            print(
                "PASS: actual Spark/Kafka/PostgreSQL, 5 sources, dedup, quarantine, food/KC matching, checkpoint restart, replay, recall revision, stale event, transaction rollback"
            )
    finally:
        if spark:
            spark.stop()
        if created:
            admin.delete_topics([topic])[topic].result(15)
        with psycopg.connect(**db) as c:
            c.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )


if __name__ == "__main__":
    main()
