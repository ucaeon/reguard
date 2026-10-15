import hashlib
import json
import unittest
from uuid import NAMESPACE_URL, uuid4, uuid5

from pipelines.spark.normalize import canonical, normalize


def envelope(source, identity, payload, collected="2026-09-29T00:00:00+00:00"):
    run = str(uuid4())
    key = source + ":" + identity
    digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
    return key, canonical(
        {
            "schema_version": 1,
            "source": source,
            "source_record_id": identity,
            "run_id": run,
            "collected_at": collected,
            "payload": payload,
            "payload_sha256": digest,
            "event_id": str(uuid5(NAMESPACE_URL, run + ":" + key + ":" + digest)),
        }
    )


class NormalizeTest(unittest.TestCase):
    def check(self, source, identity, payload):
        key, raw = envelope(source, identity, payload)
        return json.loads(normalize(raw, key))

    def test_food_product_and_uuid_compatibility(self):
        result = self.check(
            "FOOD_I1250",
            "001",
            {
                "PRDLST_REPORT_NO": "001",
                "PRDLST_NM": " 제품 ",
                "LAST_UPDT_DTM": "20260928",
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["record"]["id"], str(uuid5(NAMESPACE_URL, "reguard:FOOD_I1250:001"))
        )
        self.assertEqual(result["record"]["identifiers"], [["FOOD_REPORT_NO", "001"]])

    def test_supplement(self):
        self.assertEqual(
            self.check(
                "FOOD_I0030", "1", {"PRDLST_REPORT_NO": "1", "PRDLST_NM": "비타민"}
            )["record"]["category"],
            "HEALTH_SUPPLEMENT",
        )

    def test_kc(self):
        r = self.check(
            "SAFETY_KC",
            "1",
            {
                "certUid": 1,
                "productName": "완구",
                "certNum": "AB123-456",
                "certificationImageUrls": ["https://example.test/x.jpg"],
            },
        )["record"]
        self.assertEqual(r["category"], "TOY")
        self.assertEqual(r["identifiers"], [["KC_CERT_NO", "AB123-456"]])

    def test_recalls_preserve_conditions(self):
        r = self.check(
            "FOOD_I0490",
            "1",
            {
                "RTRVLDSUSE_SEQ": "1",
                "PRDTNM": "식품",
                "MNFDT": "2026년 일부 제품",
                "CRET_DTM": "20260928",
            },
        )["record"]
        self.assertEqual(
            json.loads(r["target_conditions"])["MNFDT"], "2026년 일부 제품"
        )
        r = self.check(
            "SAFETY_RECALL",
            "1",
            {
                "recallUid": "1",
                "recallProductName": "완구",
                "recallFiles": [{"imageUrl": "https://example.test/x"}],
            },
        )["record"]
        self.assertEqual(r["image_url"], "https://example.test/x")

    def test_invalid_fields(self):
        for payload in [
            {"RTRVLDSUSE_SEQ": "1"},
            {"RTRVLDSUSE_SEQ": "1", "PRDTNM": "x", "CRET_DTM": "20260230"},
            {"RTRVLDSUSE_SEQ": "2", "PRDTNM": "x"},
        ]:
            self.assertFalse(self.check("FOOD_I0490", "1", payload)["ok"])

    def test_bad_json_and_hash_and_key(self):
        self.assertFalse(json.loads(normalize("{", "bad"))["ok"])
        key, raw = envelope("FOOD_I0490", "1", {"RTRVLDSUSE_SEQ": "1", "PRDTNM": "x"})
        self.assertFalse(json.loads(normalize(raw, "wrong"))["ok"])
        value = json.loads(raw)
        value["payload"]["PRDTNM"] = "changed"
        self.assertEqual(
            json.loads(normalize(json.dumps(value), key))["reason"],
            "PAYLOAD_HASH_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
