from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from pipelines.collectors.kafka_producer import publish_run


class FakeProducer:
    def __init__(self, failure=False):
        self.messages = []
        self.failure = failure

    def produce(self, topic, key, value, on_delivery):
        self.messages.append((key, json.loads(value)))
        on_delivery(object() if self.failure else None, None)

    def poll(self, timeout):
        pass

    def flush(self, timeout):
        return 0


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        payload = {"id": "001"}
        row = {
            "schema_version": 1,
            "source": "FOOD_I0490",
            "source_record_id": "001",
            "run_id": "test-run",
            "collected_at": "2026-09-29T00:00:00+00:00",
            "payload": payload,
            "payload_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        self.raw = (json.dumps(row) + "\n").encode()
        (self.directory / "records.jsonl").write_bytes(self.raw)
        self.report = {
            "status": "limited",
            "records": 1,
            "source": "FOOD_I0490",
            "run_id": "test-run",
            "sha256": hashlib.sha256(self.raw).hexdigest(),
        }
        self.write_report()

    def write_report(self):
        (self.directory / "report.json").write_text(json.dumps(self.report))

    def run_publish(self, producer):
        with redirect_stdout(io.StringIO()):
            return publish_run(
                self.directory, "localhost:19092", producer_factory=lambda _: producer
            )

    def test_success_and_replay_identity(self):
        producer = FakeProducer()
        self.assertEqual(self.run_publish(producer), 0)
        self.assertEqual(self.run_publish(producer), 0)
        self.assertEqual(producer.messages[0], producer.messages[1])
        self.assertEqual(producer.messages[0][0], b"FOOD_I0490:001")
        self.assertEqual((self.directory / "records.jsonl").read_bytes(), self.raw)

    def test_delivery_failure_is_failure(self):
        self.assertEqual(self.run_publish(FakeProducer(True)), 1)
        report = json.loads(next(self.directory.glob("publish-*.json")).read_text())
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["acknowledged"], 0)

    def test_failed_collection_is_not_sent(self):
        self.report["status"] = "failed"
        self.write_report()
        producer = FakeProducer()
        self.assertEqual(self.run_publish(producer), 1)
        self.assertEqual(producer.messages, [])

    def test_corruption_is_not_sent(self):
        (self.directory / "records.jsonl").write_bytes(self.raw + b"\n")
        producer = FakeProducer()
        self.assertEqual(self.run_publish(producer), 1)
        self.assertEqual(producer.messages, [])

    def test_unconfirmed_is_not_success(self):
        class Unconfirmed(FakeProducer):
            def produce(self, *args, **kwargs):
                pass

        self.assertEqual(self.run_publish(Unconfirmed()), 1)
        report = json.loads(next(self.directory.glob("publish-*.json")).read_text())
        self.assertEqual(report["unconfirmed"], 1)


if __name__ == "__main__":
    unittest.main()
