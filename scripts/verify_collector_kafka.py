from contextlib import redirect_stdout
import hashlib
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.collectors.kafka_producer import publish_run


def main():
    bootstrap = (
        dotenv_values(ROOT / ".env").get("KAFKA_BOOTSTRAP_SERVERS") or "127.0.0.1:19092"
    )
    topic = "reguard.raw-test." + uuid4().hex
    admin = AdminClient({"bootstrap.servers": bootstrap})
    consumer = None
    created = False
    try:
        admin.create_topics([NewTopic(topic, num_partitions=3, replication_factor=1)])[
            topic
        ].result(15)
        created = True
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            rows = []
            for source in [
                "FOOD_I0490",
                "FOOD_I1250",
                "FOOD_I0030",
                "SAFETY_KC",
                "SAFETY_RECALL",
            ]:
                run = directory / source
                run.mkdir()
                payload = {"id": "001", "name": "검증 제품", "image": None}
                row = {
                    "schema_version": 1,
                    "source": source,
                    "source_record_id": "001",
                    "run_id": uuid4().hex,
                    "collected_at": "2026-09-29T00:00:00+00:00",
                    "payload": payload,
                    "payload_sha256": hashlib.sha256(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest(),
                }
                raw = (json.dumps(row, ensure_ascii=False) + "\n").encode()
                (run / "records.jsonl").write_bytes(raw)
                (run / "report.json").write_text(
                    json.dumps(
                        {
                            "status": "limited",
                            "source": source,
                            "run_id": row["run_id"],
                            "records": 1,
                            "sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
                )
                rows.append((run, row))
            consumer = Consumer(
                {
                    "bootstrap.servers": bootstrap,
                    "group.id": topic,
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": False,
                }
            )
            consumer.subscribe([topic])
            logger = logging.getLogger("reguard.verify")
            logger.addHandler(logging.NullHandler())
            logger.propagate = False

            def unavailable(_):
                return Producer(
                    {
                        "bootstrap.servers": "127.0.0.1:1",
                        "delivery.timeout.ms": 1000,
                        "request.timeout.ms": 500,
                        "logger": logger,
                    }
                )

            with redirect_stdout(io.StringIO()):
                assert publish_run(rows[0][0], bootstrap, topic, unavailable) == 1
                for run, _ in rows:
                    assert publish_run(run, bootstrap, topic) == 0
                assert publish_run(rows[0][0], bootstrap, topic) == 0
            received = []
            deadline = time.monotonic() + 30
            while len(received) < 6 and time.monotonic() < deadline:
                message = consumer.poll(1)
                if message is None:
                    continue
                if message.error():
                    raise RuntimeError("Consumer error")
                row = json.loads(message.value())
                received.append(row)
                assert (
                    message.key().decode()
                    == row["source"] + ":" + row["source_record_id"]
                )
            assert len(received) == 6
            assert {r["source"] for r in received} == {r["source"] for _, r in rows}
            originals = {r["source"]: r for _, r in rows}
            for row in received:
                assert {k: v for k, v in row.items() if k != "event_id"} == originals[
                    row["source"]
                ]
            duplicates = [r for r in received if r["source"] == "FOOD_I0490"]
            assert (
                len(duplicates) == 2
                and duplicates[0]["event_id"] == duplicates[1]["event_id"]
            )
            print(
                "PASS: 5 sources, actual broker delivery/readback, keys and payload equality, failed delivery then replay, stable replay event IDs; duplicate replay remains explicit."
            )
    finally:
        if consumer is not None:
            consumer.close()
        if created:
            admin.delete_topics([topic])[topic].result(15)


if __name__ == "__main__":
    main()
