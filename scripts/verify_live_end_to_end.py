from signup_fixture import verified_signup
import argparse
from datetime import date
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from uuid import NAMESPACE_URL, uuid4, uuid5


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
            .appName("reguard-live-end-to-end")
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

            def collect_live(source, report_no=None, cert_no=None, day=None):
                args = argparse.Namespace(
                    source=source,
                    max_records=100 if source == "food-recalls" else 10,
                    page_size=100,
                    max_requests=20,
                    interval=1.0,
                    start_date=day,
                    end_date=day,
                    food_report_no=report_no,
                    kc_cert_no=cert_no,
                )
                before = set((ROOT / "data/raw" / source).glob("*"))
                key = (
                    "FOOD_SAFETY_API_KEY"
                    if source.startswith("food-")
                    else "SAFETY_KOREA_API_KEY"
                )
                with httpx.Client(timeout=30, follow_redirects=False) as client:
                    assert collect(args, client, env[key]) == 0, source
                added = set((ROOT / "data/raw" / source).glob("*")) - before
                assert len(added) == 1
                directory = added.pop()
                rows = [
                    json.loads(line)["payload"]
                    for line in (directory / "records.jsonl").read_text().splitlines()
                ]
                return directory, rows

            food_run, food_recalls = collect_live("food-recalls")
            kc_run, kc_recalls = collect_live("safety-recalls", day=date(2026, 9, 16))
            assert food_recalls and kc_recalls
            product_runs = []
            cases = []
            for source, tag, supplement in [
                ("food-products", "FOOD_I1250", False),
                ("food-supplements", "FOOD_I0030", True),
            ]:
                candidates = [
                    r
                    for r in food_recalls
                    if (r.get("PRDLST_TYPE") == "건강기능식품") == supplement
                    and str(r.get("PRDLST_REPORT_NO", "")).isdigit()
                ]
                assert candidates, source + " has no matching recall sample"
                for recall in candidates[:10]:
                    number = str(recall["PRDLST_REPORT_NO"])
                    directory, rows = collect_live(source, report_no=number)
                    if len(rows) == 1:
                        break
                else:
                    raise AssertionError(
                        source + " has no unique matching real product in 10 candidates"
                    )
                product_runs.append(directory)
                cases.append(
                    {
                        "source": tag,
                        "source_id": number,
                        "name": rows[0]["PRDLST_NM"].strip(),
                        "expected": [
                            str(r["RTRVLDSUSE_SEQ"])
                            for r in food_recalls
                            if str(r.get("PRDLST_REPORT_NO")) == number
                        ],
                        "recall_source": "FOOD_I0490",
                        "match_status": "CONFIRMED",
                    }
                )
            for recall in kc_recalls:
                number = recall["certNum"].strip()
                directory, rows = collect_live("kc-products", cert_no=number)
                assert len(rows) == 1
                product = rows[0]
                product_runs.append(directory)
                models = [
                    re.sub(r"^\(제품명\)\s*", "", s.strip())
                    for s in recall["recallModelName"].split(",")
                ]
                matched = (
                    re.sub(r"^\(제품명\)\s*", "", product["modelName"].strip())
                    in models
                )
                cases.append(
                    {
                        "source": "SAFETY_KC",
                        "source_id": str(product["certUid"]),
                        "name": product["productName"].strip(),
                        "model": product["modelName"],
                        "recall_model": recall["recallModelName"],
                        "expected": [str(recall["recallUid"])] if matched else [],
                        "recall_source": "SAFETY_RECALL",
                        "match_status": "CANDIDATE",
                    }
                )
            assert any(c["source"] == "SAFETY_KC" and c["expected"] for c in cases)
            for directory in product_runs:
                assert publish_run(directory, bootstrap, raw_topic) == 0
            process()
            credentials = {
                "email": suffix + "@example.com",
                "password": "E2e-" + suffix,
            }
            verified_signup(
                request,
                {**credentials, "displayName": "전체 실제 데이터 검증"},
                execute=seed_verification,
                expected=201,
            )
            token = request("POST", "/auth/token", credentials)["accessToken"]
            for case in cases:
                product_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        "reguard:" + case["source"] + ":" + case["source_id"],
                    )
                )
                detail = request("GET", "/products/" + product_id, port=18082)
                assert detail["name"] == case["name"]
                case["product_id"] = product_id
                case["owned_id"] = request(
                    "POST",
                    "/me/products",
                    {"registrationType": "CATALOG", "catalogProductId": product_id},
                    token,
                    201,
                )["id"]

            def alerts():
                return request(
                    "GET", "/me/notifications?size=100", token=token, port=18083
                )["items"]

            assert alerts() == []
            for directory in [food_run, kc_run]:
                assert publish_run(directory, bootstrap, raw_topic) == 0
            process()
            expected_pairs = set()
            for case in cases:
                expected_ids = {
                    str(
                        uuid5(
                            NAMESPACE_URL,
                            "reguard:" + case["recall_source"] + ":" + rid,
                        )
                    )
                    for rid in case["expected"]
                }
                result = request(
                    "GET",
                    "/products/" + case["product_id"] + "/recalls?size=100",
                    port=18082,
                )
                assert {
                    r["recall"]["id"] for r in result["items"]
                } == expected_ids, case
                assert all(
                    r["matchStatus"] == case["match_status"] for r in result["items"]
                )
                expected_pairs.update((case["owned_id"], rid) for rid in expected_ids)
            wait_for(
                lambda: {(r["ownedProductId"], r["recallId"]) for r in alerts()}
                == expected_pairs,
                "all-source recall alerts",
            )
            first = alerts()
            assert len(first) == len(expected_pairs)
            for case in cases:
                found = [r for r in first if r["ownedProductId"] == case["owned_id"]]
                assert len(found) == len(case["expected"])
                assert all(r["eligibilityStatus"] == "NEEDS_CHECK" for r in found)
                if case["match_status"] == "CANDIDATE":
                    assert all("후보" in r["title"] for r in found)
                case["observed_alerts"] = len(found)
            before_ids = {r["id"] for r in first}
            for directory in [*product_runs, food_run, kc_run]:
                assert publish_run(directory, bootstrap, raw_topic) == 0
            process()
            time.sleep(2)
            assert {r["id"] for r in alerts()} == before_ids
            with psycopg.connect(**db("safety", True)) as c:
                assert (
                    c.execute("SELECT count(*) FROM ingestion_quarantine").fetchone()[0]
                    == 0
                )
                counts = dict(
                    c.execute(
                        "SELECT source,count(*) FROM ingestion_source_state GROUP BY source"
                    ).fetchall()
                )
                assert set(counts) == {
                    "FOOD_I1250",
                    "FOOD_I0030",
                    "FOOD_I0490",
                    "SAFETY_KC",
                    "SAFETY_RECALL",
                }
            for case in cases:
                request(
                    "DELETE",
                    "/me/products/" + case["owned_id"],
                    token=token,
                    expected=204,
                )
            wait_for(lambda: not alerts(), "all-source alert deletion")
            evidence = {
                "status": "passed",
                "data_kind": "live_official_api_unmodified",
                "source_counts": counts,
                "cases": cases,
                "expected_alerts": len(expected_pairs),
                "observed_alerts": len(first),
                "replay_duplicate_alerts": 0,
                "quarantined": 0,
                "alerts_after_product_deletion": 0,
                "runs": [str(p) for p in [*product_runs, food_run, kc_run]],
                "scope": "All five sources; bounded samples; isolated local schemas and topics",
            }
            evidence_dir = ROOT / "data/live-verification" / suffix
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "result.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
            )
            print(json.dumps(evidence, ensure_ascii=False), flush=True)
            print(
                "PASS: all five live sources, matching, candidate alerts, replay dedup and deletion"
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
        print(
            "Temporary service processes, schemas and topics cleaned up; actual API files and evidence retained in ignored data/."
        )


if __name__ == "__main__":
    main()
