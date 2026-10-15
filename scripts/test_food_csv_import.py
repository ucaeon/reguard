import unittest
from import_food_csv import copy_line, map_row, timestamp, representative_image


class ImportMappingTests(unittest.TestCase):
    def test_representative_image(self):
        self.assertEqual(
            representative_image(
                " http://example.org/a.jpg, https://example.org/b.jpg "
            ),
            "http://example.org/a.jpg",
        )
        for value in [None, "", "-", "해당없음", "javascript:alert(1)"]:
            self.assertIsNone(representative_image(value))

    def test_copy_delimiters_and_null_are_distinct(self):
        self.assertEqual(
            copy_line([None, r"\N", "a\tb\nc", "한글"]), "\\N\t\\\\N\ta\\tb\\nc\t한글\n"
        )

    def test_missing_name_rejected_without_losing_identifier_zero(self):
        row = dict(
            PRDLST_REPORT_NO="00123",
            PRDLST_NM=" 제품 ",
            BSSH_NM="회사",
            LAST_UPDT_DTM="20260928",
        )
        self.assertEqual(map_row(row, "FOOD_I1250", "FOOD")[2:4], ["00123", "제품"])
        for value in [" ", "해당없음"]:
            row["PRDLST_NM"] = value
            with self.assertRaises(ValueError):
                map_row(row, "FOOD_I1250", "FOOD")

    def test_dates_use_korean_timezone_and_invalid_dates_fail(self):
        self.assertEqual(timestamp("20260928"), "2026-09-28T00:00:00+09:00")
        with self.assertRaises(ValueError):
            timestamp("20260230")

    def test_recall_without_product_identifier_is_preserved(self):
        import json

        row = dict(
            RTRVLDSUSE_SEQ="12",
            PRDTNM="제품",
            BSSHNM="회사",
            CRET_DTM="2026-09-23 18:11:58.979897",
            PRDLST_REPORT_NO="",
            MNFDT="데이터없음",
            DISTBTMLMT="기한",
            FRMLCUNIT="120ml",
        )
        values = map_row(row, "FOOD_I0490", None)
        self.assertEqual(json.loads(values[-1]), row)
        self.assertNotIn("MNFDT", json.loads(values[7]))


if __name__ == "__main__":
    unittest.main()
