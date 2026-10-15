import json
import unittest
from configure_k3s_backups import resource_list


class ResourceParsingTest(unittest.TestCase):
    def test_multiple_kubectl_documents(self):
        resources = resource_list(' {"kind":"StorageClass"}\n {"kind":"CronJob"}\n')
        self.assertEqual(
            [item["kind"] for item in resources["items"]], ["StorageClass", "CronJob"]
        )

    def test_list_document(self):
        resources = resource_list(
            '{"kind":"List","items":[{"kind":"PersistentVolumeClaim"}]}'
        )
        self.assertEqual(resources["items"], [{"kind": "PersistentVolumeClaim"}])

    def test_invalid_output_is_not_silently_applied(self):
        with self.assertRaises(json.JSONDecodeError):
            resource_list('{"kind":"CronJob"} invalid')


if __name__ == "__main__":
    unittest.main()
