import argparse
from contextlib import redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from pipelines.collectors.collect import collect
from pipelines.collectors.common import ApiClient, CollectionError
from pipelines.collectors.providers import food_rows, safety_rows


class CollectorTest(unittest.TestCase):
    def api(self, handler, max_requests=20):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return ApiClient(
            client, max_requests=max_requests, interval=0, sleep=lambda _: None
        )

    def food(self, api, state, limit=0, page_size=2):
        return list(
            food_rows(
                api, "test-secret", "I0490", "RTRVLDSUSE_SEQ", page_size, limit, state
            )
        )

    def body(self, rows, total=3):
        return {
            "I0490": {
                "RESULT": {"CODE": "INFO-000"},
                "total_count": str(total),
                "row": rows,
            }
        }

    def test_transport_diagnostics_preserve_failure_and_hide_secrets(self):
        def respond(request):
            raise httpx.ConnectError("secret-key in URL", request=request)

        api = self.api(respond)
        with self.assertRaisesRegex(CollectionError, "^NETWORK_ERROR$"):
            api.get("https://example.test/secret-key")
        self.assertEqual(api.transport_errors, {"CONNECT_ERROR": 3})
        self.assertEqual(api.requests, 3)
        self.assertEqual(api.retries, 2)
        self.assertNotIn("secret-key", json.dumps(api.transport_errors))

    def test_transport_diagnostics_survive_successful_retry(self):
        calls = []

        def respond(request):
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ReadTimeout("private URL", request=request)
            return httpx.Response(200, json={"ok": True})

        api = self.api(respond)
        self.assertEqual(api.get("https://example.test"), {"ok": True})
        self.assertEqual(api.transport_errors, {"READ_TIMEOUT": 1})
        self.assertEqual(api.retries, 1)

    def test_product_report_filter(self):
        paths = []

        def respond(request):
            paths.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "I1250": {
                        "RESULT": {"CODE": "INFO-000"},
                        "total_count": "1",
                        "row": [{"PRDLST_REPORT_NO": "00123"}],
                    }
                },
            )

        rows = list(
            food_rows(
                self.api(respond),
                "test-secret",
                "I1250",
                "PRDLST_REPORT_NO",
                100,
                2,
                {},
                "00123",
            )
        )
        self.assertEqual(rows, [{"PRDLST_REPORT_NO": "00123"}])
        self.assertTrue(paths[0].endswith("/PRDLST_REPORT_NO=00123"))

    def test_product_report_filter_rejects_unrelated_product(self):
        api = self.api(
            lambda _: httpx.Response(
                200,
                json={
                    "I1250": {
                        "RESULT": {"CODE": "INFO-000"},
                        "total_count": "1",
                        "row": [{"PRDLST_REPORT_NO": "999"}],
                    }
                },
            )
        )
        with self.assertRaisesRegex(
            CollectionError, "UNEXPECTED_REPORT_NUMBER_FILTER_RESULT"
        ):
            list(
                food_rows(
                    api, "test-secret", "I1250", "PRDLST_REPORT_NO", 100, 2, {}, "00123"
                )
            )

    def test_supplement_report_filter(self):
        api = self.api(
            lambda _: httpx.Response(
                200,
                json={
                    "I0030": {
                        "RESULT": {"CODE": "INFO-000"},
                        "total_count": "1",
                        "row": [{"PRDLST_REPORT_NO": "00123"}],
                    }
                },
            )
        )
        self.assertEqual(
            len(
                list(
                    food_rows(
                        api,
                        "test-secret",
                        "I0030",
                        "PRDLST_REPORT_NO",
                        100,
                        2,
                        {},
                        "00123",
                    )
                )
            ),
            1,
        )

    def test_kc_cert_filter(self):
        paths = []

        def respond(request):
            paths.append(request.url.params.get("certNum"))
            return httpx.Response(
                200,
                json={
                    "resultCode": "2000",
                    "resultData": {"certUid": 12, "certNum": "CB001-1234"},
                },
            )

        state = {}
        rows = list(
            safety_rows(
                self.api(respond),
                "test-secret",
                "cert",
                "certUid",
                None,
                None,
                1,
                state,
                "CB001-1234",
            )
        )
        self.assertEqual(paths, ["CB001-1234"])
        self.assertEqual(rows[0]["certUid"], 12)
        self.assertTrue(state["scope_complete"])

    def test_kc_cert_filter_rejects_wrong_identity(self):
        api = self.api(
            lambda _: httpx.Response(
                200,
                json={
                    "resultCode": "2000",
                    "resultData": {"certUid": 12, "certNum": "WRONG-1234"},
                },
            )
        )
        with self.assertRaisesRegex(CollectionError, "INVALID_DETAIL_RESPONSE"):
            list(
                safety_rows(
                    api,
                    "test-secret",
                    "cert",
                    "certUid",
                    None,
                    None,
                    1,
                    {},
                    "CB001-1234",
                )
            )

    def test_food_pages_and_string_identifiers(self):
        paths = []

        def respond(request):
            paths.append(request.url.path)
            ids = ["001", "002"] if len(paths) == 1 else ["003"]
            return httpx.Response(
                200, json=self.body([{"RTRVLDSUSE_SEQ": x} for x in ids])
            )

        state = {}
        rows = self.food(self.api(respond), state)
        self.assertEqual([r["RTRVLDSUSE_SEQ"] for r in rows], ["001", "002", "003"])
        self.assertTrue(paths[1].endswith("/3/4"))
        self.assertTrue(state["scope_complete"])

    def test_food_limit_is_not_complete(self):
        state = {"scope_complete": False}
        self.food(
            self.api(
                lambda _: httpx.Response(200, json=self.body([{"RTRVLDSUSE_SEQ": "1"}]))
            ),
            state,
            limit=1,
        )
        self.assertFalse(state["scope_complete"])

    def test_food_empty(self):
        state = {}
        self.assertEqual(
            self.food(
                self.api(
                    lambda _: httpx.Response(200, json={"RESULT": {"CODE": "INFO-200"}})
                ),
                state,
            ),
            [],
        )
        self.assertTrue(state["scope_complete"])

    def test_auth_error_is_not_retried_or_leaked(self):
        api = self.api(
            lambda _: httpx.Response(
                200, json={"RESULT": {"CODE": "INFO-100", "MSG": "test-secret"}}
            )
        )
        with self.assertRaisesRegex(CollectionError, "^INFO-100$"):
            self.food(api, {})
        self.assertEqual(api.requests, 1)

    def test_retry_and_request_budget(self):
        calls = []

        def respond(_):
            calls.append(1)
            return (
                httpx.Response(503)
                if len(calls) < 3
                else httpx.Response(200, json={"ok": True})
            )

        api = self.api(respond)
        self.assertTrue(api.get("https://example.test")["ok"])
        self.assertEqual(api.retries, 2)
        with self.assertRaisesRegex(CollectionError, "REQUEST_BUDGET"):
            self.api(lambda _: httpx.Response(503), max_requests=1).get(
                "https://example.test"
            )

    def test_redirect_is_not_followed(self):
        with self.assertRaisesRegex(CollectionError, "HTTP_302"):
            self.api(
                lambda _: httpx.Response(
                    302, headers={"Location": "https://other.test"}
                )
            ).get("https://example.test")

    def test_invalid_json_and_short_page(self):
        with self.assertRaisesRegex(CollectionError, "INVALID_JSON"):
            self.api(lambda _: httpx.Response(200, text="<html>")).get(
                "https://example.test"
            )
        with self.assertRaisesRegex(CollectionError, "UNEXPECTED_PAGE_SIZE"):
            self.food(self.api(lambda _: httpx.Response(200, json=self.body([]))), {})

    def test_duplicate_and_missing_ids(self):
        for rows, code in [
            ([{"RTRVLDSUSE_SEQ": "1"}] * 2, "DUPLICATE_SOURCE_ID"),
            ([{}, {}], "MISSING_SOURCE_ID"),
        ]:
            with self.assertRaisesRegex(CollectionError, code):
                self.food(
                    self.api(
                        lambda _: httpx.Response(200, json=self.body(rows, total=2))
                    ),
                    {},
                )

    def safety(self, api, state, limit=0):
        return list(
            safety_rows(
                api,
                "test-secret",
                "recall",
                "recallUid",
                date(2026, 9, 15),
                date(2026, 9, 16),
                limit,
                state,
            )
        )

    def test_safety_dates_and_details_with_image(self):
        calls = []

        def respond(request):
            self.assertEqual(request.headers["AuthKey"], "test-secret")
            calls.append(request)
            if request.url.params.get("conditionValue") == "20260915":
                return httpx.Response(200, json={"resultCode": 2004})
            if request.url.path.endswith("recallList.json"):
                data = [{"recallUid": "1", "publishDate": "20260916"}]
            else:
                data = {
                    "recallUid": "1",
                    "recallFiles": [{"imageUrl": "https://example.test/image.jpg"}],
                }
            return httpx.Response(200, json={"resultCode": 2000, "resultData": data})

        state = {}
        rows = self.safety(self.api(respond), state)
        self.assertEqual(len(calls), 3)
        self.assertTrue(rows[0]["recallFiles"])
        self.assertTrue(state["scope_complete"])

    def test_safety_cap_and_mismatched_detail(self):
        with self.assertRaisesRegex(CollectionError, "SAFETY_DAILY_LIMIT"):
            self.safety(
                self.api(
                    lambda _: httpx.Response(
                        200, json={"resultCode": 2000, "resultData": [{}] * 1000}
                    )
                ),
                {},
            )

        def respond(request):
            data = (
                [{"recallUid": "1", "publishDate": "20260915"}]
                if request.url.path.endswith("List.json")
                else {"recallUid": "2"}
            )
            return httpx.Response(200, json={"resultCode": 2000, "resultData": data})

        with self.assertRaisesRegex(CollectionError, "INVALID_DETAIL"):
            self.safety(self.api(respond), {})

    def test_failed_run_keeps_partial_and_report_without_key(self):
        calls = []

        def respond(_):
            calls.append(1)
            return (
                httpx.Response(200, json=self.body([{"RTRVLDSUSE_SEQ": "1"}], total=2))
                if len(calls) == 1
                else httpx.Response(
                    200, json={"RESULT": {"CODE": "INFO-100", "MSG": "test-secret"}}
                )
            )

        self.check_output(respond, 1, "failed", False)

    def test_successful_run_preserves_raw_payload(self):
        self.check_output(
            lambda _: httpx.Response(
                200,
                json=self.body(
                    [{"RTRVLDSUSE_SEQ": "001", "IMG_FILE_PATH": None}], total=1
                ),
            ),
            0,
            "complete",
            True,
        )

    def check_output(self, handler, exit_code, status, complete):
        args = argparse.Namespace(
            source="food-recalls",
            max_requests=4,
            interval=0,
            max_records=0,
            page_size=1,
            start_date=None,
            end_date=None,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
        ):
            output = io.StringIO()
            with (
                patch("pipelines.collectors.collect.ROOT", Path(directory)),
                redirect_stdout(output),
            ):
                self.assertEqual(collect(args, client, "test-secret"), exit_code)
            report_path = next(Path(directory).rglob("report.json"))
            report = json.loads(report_path.read_text())
            self.assertEqual(report["status"], status)
            self.assertEqual((report_path.parent / "records.jsonl").exists(), complete)
            self.assertNotIn("test-secret", output.getvalue() + report_path.read_text())
            if complete:
                row = json.loads((report_path.parent / "records.jsonl").read_text())
                self.assertEqual(row["source_record_id"], "001")
                self.assertIsNone(row["payload"]["IMG_FILE_PATH"])


if __name__ == "__main__":
    unittest.main()
