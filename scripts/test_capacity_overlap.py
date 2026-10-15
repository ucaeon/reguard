import json
import unittest
from unittest.mock import patch

from k3s_resources import deployment
from verify_capacity_overlap import restore_limits


class CapacityConfigurationTest(unittest.TestCase):
    def test_airflow_probe_has_time_to_import_without_removing_health_check(self):
        resources = []
        probe = {'exec': {'command': ['airflow', 'jobs', 'check', '--job-type', 'DagProcessorJob', '--local']}}
        deployment('dag-processor', 'airflow', {}, [], [], ('1', '768Mi'), probe, [],
                   lambda kind, name, **value: resources.append((kind, value)))
        spec = next(value for kind, value in resources if kind == 'Deployment')
        container = spec['spec']['template']['spec']['containers'][0]
        for kind in ('readinessProbe', 'startupProbe', 'livenessProbe'):
            self.assertEqual(container[kind]['exec'], probe['exec'])
            self.assertEqual(container[kind]['timeoutSeconds'], 30)
            self.assertEqual(container[kind]['periodSeconds'], 60)

    @patch('verify_capacity_overlap.run')
    def test_unlimited_restore_uses_host_ceiling_not_ignored_zero(self, run):
        desired = {'Memory': 8 * 1024**3, 'MemorySwap': 16 * 1024**3, 'NanoCpus': 4_000_000_000}
        run.side_effect = [json.dumps({'MemTotal': desired['Memory'], 'NCPU': 4}), '',
                           json.dumps([{'HostConfig': desired}])]
        self.assertEqual(restore_limits({'Memory': 0, 'MemorySwap': 0, 'NanoCpus': 0}), desired)

    @patch('verify_capacity_overlap.run')
    def test_restore_failure_is_not_reported_as_success(self, run):
        run.side_effect = [json.dumps({'MemTotal': 8 * 1024**3, 'NCPU': 4}), '',
                           json.dumps([{'HostConfig': {'Memory': 7 * 1024**3, 'MemorySwap': 16 * 1024**3, 'NanoCpus': 4_000_000_000}}])]
        with self.assertRaisesRegex(RuntimeError, 'restoration failed'):
            restore_limits({'Memory': 0, 'MemorySwap': 0, 'NanoCpus': 0})


if __name__ == '__main__':
    unittest.main()
