from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from orchestration.airflow import jobs, planning, execution, completion, quality
from pipelines.collectors.common import CollectionError
from pipelines.collectors.providers import food_rows, safety_rows


class JobsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(
            os.environ,
            {"REGUARD_DATA_ROOT": self.temp.name, "FOOD_SAFETY_API_KEY": "test-secret"},
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.now = datetime(2026, 9, 29, 20, tzinfo=jobs.KST)

    def test_state_migration_preserves_history_and_does_not_overwrite(self):
        with jobs.state_db() as connection:
            connection.execute(
                "INSERT INTO watermarks VALUES (?,?,?)",
                ("kc-products", "2026-09-28", self.now.isoformat()),
            )
        destination = str(Path(self.temp.name) / "native")
        with patch.dict(os.environ, {"REGUARD_STATE_ROOT": destination}):
            with jobs.state_db() as connection:
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                self.assertEqual(
                    connection.execute("SELECT day FROM watermarks").fetchone()[0],
                    "2026-09-28",
                )
                connection.execute("UPDATE watermarks SET day='2026-09-29'")
            with jobs.state_db() as connection:
                self.assertEqual(
                    connection.execute("SELECT day FROM watermarks").fetchone()[0],
                    "2026-09-29",
                )
        with jobs.state_db() as connection:
            self.assertEqual(
                connection.execute("SELECT day FROM watermarks").fetchone()[0],
                "2026-09-28",
            )

    def test_quality_waits_without_opening_product_database(self):
        path = jobs.prepare_quality("first", self.now)
        with patch.object(
            quality, "database", side_effect=AssertionError("premature inspection")
        ):
            self.assertFalse(jobs.collection_ready(path, self.now))
        self.assertEqual(json.loads(Path(path).read_text())["status"], "waiting")

    def test_quality_reports_delay_after_deadline(self):
        path = jobs.prepare_quality("delay", self.now)
        with self.assertRaisesRegex(RuntimeError, "COLLECTION_DELAYED"):
            jobs.collection_ready(path, self.now + timedelta(hours=4))
        self.assertEqual(
            json.loads(Path(path).read_text())["status"], "collection_delayed"
        )

    def test_quality_requires_current_collection_and_preserves_deadline(self):
        path = jobs.prepare_quality("ready", self.now)
        report = json.loads(Path(path).read_text())
        with jobs.state_db() as connection:
            for source, required in report["required"].items():
                connection.execute(
                    "INSERT INTO watermarks VALUES (?,?,?)",
                    (source, required["day"], required["completed_after"]),
                )
        self.assertTrue(jobs.collection_ready(path, self.now))
        with jobs.state_db() as connection:
            connection.execute(
                "UPDATE watermarks SET completed_at=? WHERE source='food-recalls'",
                ((self.now - timedelta(days=1)).isoformat(),),
            )
        self.assertFalse(jobs.collection_ready(path, self.now))
        jobs.prepare_quality("ready", self.now + timedelta(hours=1))
        self.assertEqual(
            json.loads(Path(path).read_text())["deadline"], report["deadline"]
        )

    def test_quality_morning_requires_previous_evening_food_and_today_kc(self):
        path = jobs.prepare_quality("morning", self.now.replace(hour=5))
        required = json.loads(Path(path).read_text())["required"]
        self.assertEqual(required["food-products"]["day"], "2026-09-28")
        self.assertEqual(required["kc-products"]["day"], "2026-09-29")

    def test_plan_partitions_safety_by_registration_day(self):
        path = jobs.plan(
            "kc-products", "backfill", "manual-1", "2026-09-28", "2026-09-27", self.now
        )
        data = jobs.read_plan(path)
        self.assertEqual(
            [p["day"] for p in data["parts"]], ["2026-09-27", "2026-09-28"]
        )
        self.assertEqual(
            jobs.plan(
                "kc-products",
                "backfill",
                "manual-1",
                "2026-09-28",
                "2026-09-27",
                self.now,
            ),
            path,
        )

    def test_old_food_watermark_requires_snapshot(self):
        with jobs.state_db() as c:
            c.execute(
                "INSERT INTO watermarks VALUES (?,?,?)",
                ("food-products", "2026-09-10", self.now.isoformat()),
            )
        value = jobs.read_plan(
            jobs.plan("food-products", "incremental", "old", now=self.now)
        )
        self.assertEqual(value["mode"], "snapshot")
        self.assertTrue(value["gap_recovery"])

    def test_food_window_overlaps_previous_success(self):
        with jobs.state_db() as c:
            c.execute(
                "INSERT INTO watermarks VALUES (?,?,?)",
                ("food-products", "2026-09-25", self.now.isoformat()),
            )
        value = jobs.read_plan(
            jobs.plan("food-products", "incremental", "overlap", now=self.now)
        )
        self.assertEqual(value["start_day"], "2026-09-24")

    def test_budget_enforced_before_http(self):
        for _ in range(90):
            jobs.reserve_request("food", "food-recalls", False, self.now)
        with self.assertRaisesRegex(CollectionError, "BUDGET"):
            jobs.reserve_request("food", "food-products", False, self.now)
        jobs.reserve_request(
            "food", "food-products", False, self.now + timedelta(hours=2)
        )

    def test_daytime_budget_includes_incremental(self):
        now = self.now.replace(hour=10)
        for _ in range(280):
            jobs.reserve_request("food", "food-products", True, now)
        with self.assertRaisesRegex(CollectionError, "BUDGET"):
            jobs.reserve_request("food", "food-products", True, now)
        jobs.reserve_request("food", "food-products", True, self.now)

    def test_success_response_is_cached_but_errors_are_not(self):
        calls = []

        def respond(request):
            calls.append(1)
            return httpx.Response(
                200,
                json={"RESULT": {"CODE": "INFO-000" if len(calls) > 1 else "INFO-500"}},
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            api = jobs.CachedApi(client, Path(self.temp.name) / "cache")
            api.sleep = lambda _: None
            for _ in range(3):
                api.get("https://example.test")
        self.assertEqual(len(calls), 2)

    def test_invalid_plan_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_PLAN_PATH"):
            jobs.read_plan("/tmp/plan.json")

    def test_database_lag_does_not_advance_watermark(self):
        path = jobs.plan("food-products", "incremental", "lag", now=self.now)
        with patch.object(completion, "applied_plan", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "NOT_CAUGHT_UP"):
                jobs.finish_plan(path)
        with jobs.state_db() as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM watermarks").fetchone()[0], 0
            )

    def successful_run(self):
        path = jobs.plan("food-recalls", "reconcile", "cached", now=self.now)
        data = jobs.read_plan(path)
        directory = jobs.directories(data)[0]
        directory.mkdir(parents=True)
        (directory / "records.jsonl").write_bytes(b"")
        jobs.atomic_json(
            directory / "report.json",
            {
                "status": "complete",
                "records": 0,
                "sha256": hashlib.sha256(b"").hexdigest(),
                "run_id": data["parts"][0]["run_id"],
            },
        )
        return path, directory

    def test_success_advances_incremental_watermark_only(self):
        path, _ = self.successful_run()
        with patch.object(completion, "applied_plan", return_value=True):
            jobs.finish_plan(path)
        with jobs.state_db() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM watermarks").fetchone()[0], 0
            )
        value = jobs.read_plan(path)
        value["mode"] = "incremental"
        jobs.atomic_json(Path(path), value)
        with patch.object(completion, "applied_plan", return_value=True):
            jobs.finish_plan(path)
        with jobs.state_db() as connection:
            self.assertEqual(
                connection.execute("SELECT source,day FROM watermarks").fetchone(),
                ("food-recalls", value["end_day"]),
            )

    def test_collect_retry_reuses_completed_file(self):
        path, _ = self.successful_run()
        with patch.object(
            execution, "collect", side_effect=AssertionError("must not recollect")
        ):
            self.assertEqual(jobs.collect_plan(path), path)

    def test_publish_retry_reuses_success_marker(self):
        path, _ = self.successful_run()
        with patch.object(execution, "publish_run", return_value=0) as send:
            jobs.publish_plan(path)
            jobs.publish_plan(path)
        self.assertEqual(send.call_count, 1)

    def test_failed_publish_can_retry_same_file(self):
        path, _ = self.successful_run()
        with patch.object(execution, "publish_run", side_effect=[1, 0]) as send:
            with self.assertRaisesRegex(RuntimeError, "PUBLISH"):
                jobs.publish_plan(path)
            jobs.publish_plan(path)
        self.assertEqual(send.call_args_list[0], send.call_args_list[1])

    def test_incomplete_run_is_not_published(self):
        path, directory = self.successful_run()
        report = json.loads((directory / "report.json").read_text())
        report["status"] = "limited"
        jobs.atomic_json(directory / "report.json", report)
        with patch.object(
            execution, "publish_run", side_effect=AssertionError("must not send")
        ):
            with self.assertRaisesRegex(CollectionError, "INCOMPLETE"):
                jobs.publish_plan(path)

    def test_kc_gap_extends_collection_window(self):
        with jobs.state_db() as c:
            c.execute(
                "INSERT INTO watermarks VALUES (?,?,?)",
                ("kc-products", "2026-09-24", self.now.isoformat()),
            )
        value = jobs.read_plan(
            jobs.plan("kc-products", "incremental", "kc-gap", now=self.now)
        )
        self.assertEqual(value["start_day"], "2026-09-23")

    def test_recall_count_mismatch_falls_back_once_to_full(self):
        path = jobs.plan("food-recalls", "incremental", "fallback")
        observed = []

        def collect(args, client, key, api=None):
            observed.append(args.changed_since)
            directory = jobs.root() / "raw" / args.source / args.run_id
            directory.mkdir(parents=True, exist_ok=True)
            report = {"status": "failed", "error_code": "UNEXPECTED_PAGE_SIZE"}
            if len(observed) == 2:
                (directory / "records.jsonl").write_bytes(b"")
                report = {
                    "status": "complete",
                    "records": 0,
                    "sha256": hashlib.sha256(b"").hexdigest(),
                }
            jobs.atomic_json(directory / "report.json", report)
            return 1 if len(observed) == 1 else 0

        with patch.object(execution, "collect", side_effect=collect):
            jobs.collect_plan(path)
        self.assertIsNotNone(observed[0])
        self.assertIsNone(observed[1])
        directory = jobs.directories(jobs.read_plan(path))[0]
        self.assertEqual(
            json.loads((directory / "report.json").read_text())["fallback"],
            "FULL_RECALL_RECONCILIATION",
        )

    def test_food_changed_filter_in_request(self):
        paths = []

        def respond(request):
            paths.append(request.url.path)
            return httpx.Response(200, json={"RESULT": {"CODE": "INFO-200"}})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            api = jobs.ApiClient(client)
            self.assertEqual(
                list(
                    food_rows(
                        api,
                        "test-key",
                        "I0490",
                        "RTRVLDSUSE_SEQ",
                        1000,
                        0,
                        {},
                        changed_since=self.now.date(),
                    )
                ),
                [],
            )
        self.assertTrue(paths[0].endswith("/CHNG_DT=20260929"))

    def test_safety_registration_date_filter(self):
        def respond(request):
            if "List" in request.url.path:
                self.assertEqual(request.url.params["conditionKey"], "signDate")
                return httpx.Response(
                    200,
                    json={
                        "resultCode": "2000",
                        "resultData": [
                            {
                                "certUid": 1,
                                "certNum": "TEST-001",
                                "certDate": "20120101",
                                "signDate": "20260929",
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "resultCode": "2000",
                    "resultData": {"certUid": 1, "certNum": "TEST-001"},
                },
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            api = jobs.ApiClient(client, interval=0)
            rows = list(
                safety_rows(
                    api,
                    "test-key",
                    "cert",
                    "certUid",
                    self.now.date(),
                    self.now.date(),
                    0,
                    {},
                    date_field="signDate",
                )
            )
        self.assertEqual(len(rows), 1)

    def test_recovery_plan_is_stable_after_watermark_changes(self):
        with jobs.state_db() as c:
            c.execute(
                "INSERT INTO watermarks VALUES (?,?,?)",
                ("food-products", "2026-09-10", self.now.isoformat()),
            )
        path = jobs.plan(
            "food-products", "incremental", "replay-recovery", now=self.now
        )
        with jobs.state_db() as c:
            c.execute("UPDATE watermarks SET day='2026-09-29'")
        self.assertEqual(
            jobs.plan("food-products", "incremental", "replay-recovery", now=self.now),
            path,
        )
        self.assertEqual(jobs.read_plan(path)["mode"], "snapshot")

    def test_snapshot_advances_only_verified_baseline_not_current_day(self):
        path, directory = self.successful_run()
        value = jobs.read_plan(path)
        value["mode"] = "snapshot"
        jobs.atomic_json(Path(path), value)
        jobs.atomic_json(
            directory / "snapshot.json", {"last_modified": "2026-09-28T15:00:00+00:00"}
        )
        with patch.object(completion, "applied_plan", return_value=True):
            jobs.finish_plan(path)
        with jobs.state_db() as c:
            self.assertEqual(
                c.execute("SELECT day FROM watermarks").fetchone()[0], "2026-09-28"
            )

    def test_old_snapshot_does_not_refresh_newer_watermark(self):
        path, directory = self.successful_run()
        value = jobs.read_plan(path)
        value["mode"] = "snapshot"
        jobs.atomic_json(Path(path), value)
        jobs.atomic_json(directory / "snapshot.json", {"last_modified": "2026-09-28T15:00:00+00:00"})
        previous = (value["source"], "2026-09-29", self.now.isoformat())
        with jobs.state_db() as connection:
            connection.execute("INSERT INTO watermarks VALUES (?,?,?)", previous)
        with patch.object(completion, "applied_plan", return_value=True):
            jobs.finish_plan(path)
        with jobs.state_db() as connection:
            self.assertEqual(connection.execute("SELECT * FROM watermarks").fetchone(), previous)

    def test_file_budget_is_separate_per_service_and_bounded(self):
        for _ in range(9):
            jobs.reserve_snapshot_request("I1250")
        with self.assertRaisesRegex(CollectionError, "SNAPSHOT_DAILY_BUDGET"):
            jobs.reserve_snapshot_request("I1250")
        jobs.reserve_snapshot_request("I0030")

    def test_kc_baseline_requires_completed_load_and_matching_digest(self):
        directory = jobs.root() / "kc-snapshots" / "test"
        directory.mkdir(parents=True)
        raw = directory / "cert-list.json"
        raw.write_text("[]")
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        at = "2026-09-28T01:00:00+00:00"
        jobs.atomic_json(
            directory / "products-report.json",
            {
                "status": "complete",
                "snapshot_missing_in_db": 0,
                "snapshot_at": at,
                "raw": 2,
                "accepted": 2,
                "rejected": 0,
                "processed": 2,
                "sha256": digest,
            },
        )
        jobs.atomic_json(
            directory / "cert-list.download.json", {"sha256": digest, "started_at": at}
        )
        with patch.object(planning, "database") as db:
            db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (
                2,
            )
            start, proof = jobs.verified_kc_baseline(
                self.now.date() - timedelta(days=20), self.now.date()
            )
            self.assertEqual(start.isoformat(), "2026-09-27")
            self.assertEqual(proof["sha256"], digest)
            raw.write_text("changed")
            with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
                jobs.verified_kc_baseline(
                    self.now.date() - timedelta(days=20), self.now.date()
                )


if __name__ == "__main__":
    unittest.main()
