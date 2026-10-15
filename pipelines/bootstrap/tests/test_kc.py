import unittest
from pipelines.bootstrap.kc import normalize_product
from pipelines.spark.quality import QualityError


class KcBootstrapTest(unittest.TestCase):
    def test_unknown_date_does_not_discard_searchable_product(self):
        row, missing = normalize_product(
            {
                "certUid": 123,
                "productName": "완구",
                "certDate": "00000000",
                "certNum": "TEST-01",
            }
        )
        self.assertEqual(row[1], "123")
        self.assertIsNone(row[6])
        self.assertEqual(row[7], "TEST-01")
        self.assertEqual(missing, 1)

    def test_missing_name_is_quarantined(self):
        with self.assertRaises(QualityError):
            normalize_product({"certUid": 123, "productName": None})

    def test_malformed_date_is_not_silently_discarded(self):
        with self.assertRaises(QualityError):
            normalize_product(
                {"certUid": 123, "productName": "제품", "certDate": "20260230"}
            )

    def test_ids_are_stable_and_unrecognized_cert_is_not_matchable(self):
        data = {"certUid": 123, "productName": "제품", "certNum": "해당없음"}
        self.assertEqual(normalize_product(data), normalize_product(data))
        self.assertIsNone(normalize_product(data)[0][7])
