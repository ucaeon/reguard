from datetime import date
import unittest
from unittest.mock import Mock

from pipelines.collectors.common import CollectionError
from pipelines.collectors.food import food_rows


class SupplementBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.rows = [{"PRDLST_REPORT_NO": "1"}, {"PRDLST_REPORT_NO": "2"}]
        self.body = {
            "RESULT": {"CODE": "INFO-000"},
            "total_count": "1",
            "row": self.rows,
        }
        self.api = Mock()
        self.api.get.return_value = {"I0030": self.body}
        self.state = {}

    def collect(self, repeated=None, terminal=None):
        self.api.get_fresh.side_effect = [
            {"I0030": self.body} if repeated is None else repeated,
            {"I0030": {"RESULT": {"CODE": "INFO-200"}}}
            if terminal is None else terminal,
        ]
        return list(food_rows(
            self.api, "key", "I0030", "PRDLST_REPORT_NO", 1000, 0,
            self.state, changed_since=date(2026, 10, 13),
        ))

    def test_stable_response_requires_uncached_boundary_requests(self):
        self.assertEqual(self.collect(), self.rows)
        self.assertTrue(self.state["scope_complete"])
        self.assertEqual(self.state["count_verification"]["verified_total"], 2)
        self.assertEqual(self.api.get.call_count, 1)
        self.assertEqual(self.api.get_fresh.call_count, 2)
        url = self.api.get_fresh.call_args_list[1].args[0]
        self.assertTrue(url.endswith("/3/1002/CHNG_DT=20261013"))

    def test_changed_response_is_rejected(self):
        with self.assertRaisesRegex(CollectionError, "INCONSISTENT_SUPPLEMENT_BOUNDARY"):
            self.collect(repeated={"I0030": {**self.body, "total_count": "2"}})
        self.assertFalse(self.state.get("scope_complete", False))

    def test_nonempty_successor_is_rejected(self):
        with self.assertRaisesRegex(CollectionError, "INCONSISTENT_SUPPLEMENT_BOUNDARY"):
            self.collect(terminal={"I0030": self.body})

    def test_malformed_successor_is_rejected(self):
        for terminal in ([], {"I0030": []}, {"I0030": {"RESULT": None}}):
            with self.subTest(terminal=terminal):
                with self.assertRaisesRegex(CollectionError, "INCONSISTENT_SUPPLEMENT_BOUNDARY"):
                    self.collect(terminal=terminal)

    def test_duplicate_identifiers_are_rejected(self):
        self.rows[1]["PRDLST_REPORT_NO"] = "1"
        with self.assertRaisesRegex(CollectionError, "DUPLICATE_SOURCE_ID"):
            self.collect()
        self.assertFalse(self.state.get("scope_complete", False))
