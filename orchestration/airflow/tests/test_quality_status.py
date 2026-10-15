import unittest
from orchestration.airflow.quality_status import dimensions


class QualityStatusTest(unittest.TestCase):
    def test_unmatched_is_visible_without_claiming_ingestion_failure(self):
        result = dimensions(0, [], {"FOOD_I0490": 3}, 7)
        self.assertEqual(result["ingestion"]["status"], "passed")
        self.assertEqual(result["matching"]["status"], "needs_review")
        self.assertEqual(result["matching"]["coverage"], 0.7)

    def test_stale_and_quarantine_fail_independently(self):
        result = dimensions(2, ["food-products"], {}, 7)
        self.assertEqual(result["freshness"]["status"], "failed")
        self.assertEqual(result["ingestion"]["status"], "failed")
        self.assertEqual(result["matching"]["status"], "passed")

    def test_empty_dataset_has_no_coverage_percentage(self):
        self.assertIsNone(dimensions(0, [], {}, 0)["matching"]["coverage"])
