import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from uuid import NAMESPACE_URL, uuid4, uuid5

from confluent_kafka import Producer
from dotenv import dotenv_values

from .providers import SOURCES

ROOT = Path(__file__).resolve().parents[2]
TOPIC = "reguard.raw-records.v1"


class PublishError(Exception):
    pass


def validate_run(directory):
    report = json.loads((directory / "report.json").read_text())
    if report.get("status") not in {"complete", "limited"}:
        raise PublishError("COLLECTION_NOT_SUCCESSFUL")
    digest = hashlib.sha256()
    count = 0
    allowed = {spec[0] for spec in SOURCES.values()}
    with (directory / "records.jsonl").open("rb") as stream:
        for line in stream:
            digest.update(line)
            row = json.loads(line)
            if (
                row.get("schema_version") != 1
                or row.get("source") not in allowed
                or row.get("source") != report.get("source")
                or row.get("run_id") != report.get("run_id")
                or not isinstance(row.get("source_record_id"), str)
                or not row["source_record_id"]
                or not isinstance(row.get("payload"), dict)
                or not isinstance(row.get("collected_at"), str)
            ):
                raise PublishError("INVALID_ENVELOPE")
            payload = json.dumps(
                row["payload"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            if hashlib.sha256(payload).hexdigest() != row.get("payload_sha256"):
                raise PublishError("PAYLOAD_HASH_MISMATCH")
            count += 1
    if count != report.get("records") or digest.hexdigest() != report.get("sha256"):
        raise PublishError("FILE_INTEGRITY_ERROR")
    return count


def create_producer(bootstrap):
    logger = logging.getLogger("reguard.kafka")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return Producer(
        {
            "bootstrap.servers": bootstrap,
            "client.id": "reguard-collector",
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "gzip",
            "linger.ms": 20,
            "delivery.timeout.ms": 30000,
            "request.timeout.ms": 10000,
            "queue.buffering.max.messages": 1000,
            "queue.buffering.max.kbytes": 16384,
            "allow.auto.create.topics": False,
            "logger": logger,
        }
    )


def publish_run(directory, bootstrap, topic=TOPIC, producer_factory=create_producer):
    directory = Path(directory).resolve()
    started = time.monotonic()
    report = {
        "status": "running",
        "topic": topic,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "records": 0,
        "queued": 0,
        "acknowledged": 0,
        "failed": 0,
        "error_code": None,
    }
    producer = None

    def delivered(error, message):
        if error is None:
            report["acknowledged"] += 1
        else:
            report["failed"] += 1
            report["error_code"] = "KAFKA_DELIVERY_FAILED"

    try:
        if topic != TOPIC and not topic.startswith("reguard.raw-test."):
            raise PublishError("INVALID_RAW_TOPIC")
        report["records"] = validate_run(directory)
        if report["records"]:
            producer = producer_factory(bootstrap)
            with (directory / "records.jsonl").open() as stream:
                for line in stream:
                    if report["failed"]:
                        raise PublishError("KAFKA_DELIVERY_FAILED")
                    row = json.loads(line)
                    key = row["source"] + ":" + row["source_record_id"]
                    row["event_id"] = str(
                        uuid5(
                            NAMESPACE_URL,
                            row["run_id"] + ":" + key + ":" + row["payload_sha256"],
                        )
                    )
                    value = json.dumps(row, ensure_ascii=False).encode()
                    try:
                        producer.produce(
                            topic, key=key.encode(), value=value, on_delivery=delivered
                        )
                    except BufferError:
                        producer.flush(35)
                        if report["failed"]:
                            raise PublishError("KAFKA_DELIVERY_FAILED") from None
                        producer.produce(
                            topic, key=key.encode(), value=value, on_delivery=delivered
                        )
                    report["queued"] += 1
                    producer.poll(0)
            producer.flush(35)
        if report["acknowledged"] != report["records"] or report["failed"]:
            raise PublishError("KAFKA_DELIVERY_INCOMPLETE")
        report["status"] = "complete"
    except PublishError as error:
        report["status"] = "failed"
        report["error_code"] = str(error)
    except KeyboardInterrupt:
        report["status"] = "failed"
        report["error_code"] = "INTERRUPTED"
    except Exception:
        report["status"] = "failed"
        report["error_code"] = "PUBLISH_ERROR"
    finally:
        if producer is not None:
            try:
                producer.flush(35)
            except Exception:
                report["status"] = "failed"
                report["error_code"] = "KAFKA_FLUSH_ERROR"
        report["unconfirmed"] = (
            report["queued"] - report["acknowledged"] - report["failed"]
        )
        report["not_queued"] = report["records"] - report["queued"]
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        path = directory / ("publish-" + str(uuid4()) + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "kafka_status": report["status"],
                "acknowledged": report["acknowledged"],
                "failed": report["failed"],
                "unconfirmed": report["unconfirmed"],
                "report": str(path),
                "error_code": report["error_code"],
            }
        )
    )
    return 0 if report["status"] == "complete" else 1


def main():
    parser = argparse.ArgumentParser(
        description="Publish or replay a validated collection run to Kafka."
    )
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    if not args.run_directory.is_dir():
        parser.error("Collection run directory does not exist")
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    try:
        return publish_run(
            args.run_directory, env.get("KAFKA_BOOTSTRAP_SERVERS") or "127.0.0.1:19092"
        )
    except OSError:
        print("Publish failed: LOCAL_IO_ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
