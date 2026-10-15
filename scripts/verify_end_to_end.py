from signup_fixture import verified_signup
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid4, uuid5

from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from dotenv import dotenv_values
import httpx
import psycopg
from psycopg import sql
from pyspark.sql import SparkSession

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.collectors.collect import collect
from pipelines.collectors.kafka_producer import publish_run
from pipelines.spark.streaming_job import run


def request(method, path, body=None, token=None, expected=200, port=18081):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    elif method not in ("GET", "HEAD", "OPTIONS"):
        with urllib.request.urlopen(
            "http://127.0.0.1:18081/api/v1/auth/csrf", timeout=10
        ) as response:
            csrf = json.load(response)
            headers[csrf["headerName"]] = csrf["token"]
            headers["Cookie"] = "; ".join(
                v.split(";", 1)[0] for v in response.headers.get_all("Set-Cookie", [])
            )
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, data = error.code, error.read()
    if status != expected:
        raise AssertionError(f"{method} {path}: {status}, expected {expected}")
    return json.loads(data) if data else None


def wait_for(check, description):
    for _ in range(100):
        result = check()
        if result:
            return result
        time.sleep(0.3)
    raise AssertionError(description + " timed out")


def main():
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    os.environ["PYSPARK_PYTHON"] = sys.executable
    java = str(Path(env["JAVA_HOME"]) / "bin/java") if env.get("JAVA_HOME") else "java"
    bootstrap = env.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:19092")
    suffix = uuid4().hex
    schema = "e2e_" + suffix
    raw_topic = "reguard.raw-test." + suffix
    alert_topic = "reguard.alert-test." + suffix
    admin = AdminClient({"bootstrap.servers": bootstrap})
    processes, schemas, topics, logs = [], [], [], []
    spark = None

    def db(service, scoped=False):
        result = {
            "host": env.get("DB_HOST", "127.0.0.1"),
            "port": env.get("DB_PORT", "15432"),
            "dbname": "reguard_" + service,
            "user": "reguard_" + service,
            "password": env[service.upper() + "_DB_PASSWORD"],
        }
        if scoped:
            result["options"] = "-c search_path=" + schema
        return result

    def seed_verification(statement):
        with psycopg.connect(**db("member", scoped=True)) as connection:
            connection.execute(statement)

    def start(service, port):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
        log = open("/private/tmp/reguard-e2e-" + service + ".log", "w")
        logs.append(log)
        config = {
            **env,
            "SERVER_PORT": str(port),
            "SERVER_ADDRESS": "127.0.0.1",
            "SPRING_DATASOURCE_URL": f"jdbc:postgresql://{db(service)['host']}:{db(service)['port']}/reguard_{service}?currentSchema={schema}",
            "SPRING_FLYWAY_DEFAULT_SCHEMA": schema,
            "ALERTS_ENABLED": "true",
            "ALERT_TOPIC": alert_topic,
            "ALERT_GROUP": alert_topic,
            "ALERT_SCAN_DELAY_MS": "500",
            "ALERT_PUBLISH_DELAY_MS": "300",
            "SAFETY_BASE_URL": "http://127.0.0.1:18082",
            "MEMBER_BASE_URL": "http://127.0.0.1:18081",
            "MAIL_ENABLED": "false",
            "COOKIE_SECURE": "false",
        }
        p = subprocess.Popen(
            [
                java,
                "-jar",
                str(
                    ROOT
                    / f"services/{service}-service/target/{service}-service-0.0.1-SNAPSHOT.jar"
                ),
            ],
            env={k: v for k, v in config.items() if v is not None},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        processes.append(p)
        for _ in range(120):
            if p.poll() is not None:
                raise RuntimeError(service + " exited; inspect its e2e log")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/actuator/health/readiness", timeout=2
                ) as response:
                    if json.load(response)["status"] == "UP":
                        return p
            except OSError:
                pass
            time.sleep(0.25)
        raise RuntimeError(service + " startup timeout")

    try:
        for service in ["safety", "member", "notification"]:
            with psycopg.connect(**db(service)) as c:
                c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            schemas.append(service)
        for topic in [raw_topic, alert_topic]:
            admin.create_topics(
                [NewTopic(topic, num_partitions=1, replication_factor=1)]
            )[topic].result(15)
            topics.append(topic)
        for service, port in [
            ("safety", 18082),
            ("member", 18081),
            ("notification", 18083),
        ]:
            start(service, port)
        spark = (
            SparkSession.builder.master("local[2]")
            .appName("reguard-end-to-end")
            .config(
                "spark.jars.packages",
                "org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.3",
            )
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            checkpoint = output / "checkpoint"

            def process():
                run(
                    spark, bootstrap, raw_topic, checkpoint, db("safety", True), True
                ).awaitTermination()

            def ingest(source, payload):
                code = "I1250" if source == "food-products" else "I0490"
                args = argparse.Namespace(
                    source=source,
                    max_records=1,
                    page_size=1,
                    max_requests=2,
                    interval=0.1,
                    start_date=None,
                    end_date=None,
                )
                response = {
                    code: {
                        "RESULT": {"CODE": "INFO-000"},
                        "total_count": "1",
                        "row": [payload],
                    }
                }
                with (
                    httpx.Client(
                        transport=httpx.MockTransport(
                            lambda _: httpx.Response(200, json=response)
                        )
                    ) as client,
                    patch("pipelines.collectors.collect.ROOT", output),
                    redirect_stdout(io.StringIO()),
                ):
                    assert collect(args, client, "test-key") == 0
                    directory = max(
                        (output / "data/raw" / source).iterdir(),
                        key=lambda p: p.stat().st_mtime_ns,
                    )
                    assert publish_run(directory, bootstrap, raw_topic) == 0
                process()
                return directory

            report_no = "90000000000001"
            product = {
                "PRDLST_REPORT_NO": report_no,
                "PRDLST_NM": "E2E 시험 제품",
                "BSSH_NM": "E2E 시험 회사",
                "LAST_UPDT_DTM": "20260929",
            }
            ingest("food-products", product)
            product_id = str(uuid5(NAMESPACE_URL, "reguard:FOOD_I1250:" + report_no))
            request("GET", "/products/" + product_id, port=18082)
            credentials = {
                "email": suffix + "@example.com",
                "password": "E2e-" + suffix,
            }
            verified_signup(
                request,
                {**credentials, "displayName": "E2E 사용자"},
                execute=seed_verification,
            )
            token = request("POST", "/auth/token", credentials)["accessToken"]
            owned = request(
                "POST",
                "/me/products",
                {"registrationType": "CATALOG", "catalogProductId": product_id},
                token,
                201,
            )

            def alerts():
                return request("GET", "/me/notifications", token=token, port=18083)[
                    "items"
                ]

            assert not alerts()
            recall = {
                "RTRVLDSUSE_SEQ": "E2E-RECALL",
                "PRDTNM": product["PRDLST_NM"],
                "BSSHNM": product["BSSH_NM"],
                "PRDLST_REPORT_NO": report_no,
                "RTRVLPRVNS": "원인 A",
                "CRET_DTM": "20260929",
            }
            original = ingest("food-recalls", recall)
            first = wait_for(alerts, "first alert")
            assert (
                len(first) == 1
                and first[0]["ownedProductId"] == owned["id"]
                and first[0]["recallVersion"] == 1
            )
            with redirect_stdout(io.StringIO()):
                assert publish_run(original, bootstrap, raw_topic) == 0
            process()
            time.sleep(2)
            assert len(alerts()) == 1
            ingest("food-recalls", {**recall, "RTRVLPRVNS": "원인 B"})
            wait_for(lambda: len(alerts()) == 2, "revision alert")
            assert {x["recallVersion"] for x in alerts()} == {1, 2}
            with psycopg.connect(**db("member", True)) as c:
                saved = c.execute(
                    "SELECT payload::text FROM alert_outbox WHERE owned_product_id=%s AND recall_id IS NOT NULL ORDER BY created_at LIMIT 1",
                    (owned["id"],),
                ).fetchone()[0]
            request("DELETE", "/me/products/" + owned["id"], token=token, expected=204)
            wait_for(lambda: not alerts(), "alert deletion")
            producer = Producer({"bootstrap.servers": bootstrap})
            delivered = []
            producer.produce(
                alert_topic,
                key=json.loads(saved)["userId"],
                value=saved,
                on_delivery=lambda error, message: delivered.append((error, message)),
            )
            assert producer.flush(10) == 0
            assert len(delivered) == 1 and delivered[0][0] is None
            replay_offset = delivered[0][1].offset()
            observer = Consumer(
                {
                    "bootstrap.servers": bootstrap,
                    "group.id": alert_topic,
                    "enable.auto.commit": False,
                }
            )
            try:
                wait_for(
                    lambda: observer.committed(
                        [TopicPartition(alert_topic, 0)], timeout=5
                    )[0].offset
                    > replay_offset,
                    "late alert consumed",
                )
            finally:
                observer.close()
            with redirect_stdout(io.StringIO()):
                assert publish_run(original, bootstrap, raw_topic) == 0
            process()
            time.sleep(2)
            assert alerts() == []
            print(
                "PASS: controlled API response → real collector → raw Kafka → Spark → Safety DB/matching → Member → alert Kafka → Notification HTTP API; initial alert, replay dedup, revision re-alert, deletion and late replay."
            )
    finally:
        if spark:
            spark.stop()
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
        for log in logs:
            log.close()
        for topic in topics:
            admin.delete_topics([topic])[topic].result(15)
        for service in reversed(schemas):
            with psycopg.connect(**db(service)) as c:
                c.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
        print("Temporary service processes, schemas, topics and files cleaned up.")


if __name__ == "__main__":
    main()
