import unittest
from check_capacity import assess, memory_mib, pod_limit


def spec(memory):
    return {'containers': [{'resources': {'limits': {'memory': memory}}}]}


class CapacityTest(unittest.TestCase):
    def test_decimal_and_binary_units(self):
        self.assertEqual(memory_mib('1Gi'), 1024)
        self.assertEqual(memory_mib('1048576'), 1)
        self.assertLess(memory_mib('1G'), memory_mib('1Gi'))

    def test_init_peak_and_missing_limit(self):
        pod = spec('256Mi')
        pod['initContainers'] = spec('1Gi')['containers']
        self.assertEqual(pod_limit(pod), 1024)
        with self.assertRaises(ValueError):
            pod_limit({'containers': [{}]})

    def test_low_observed_usage_does_not_pass_overcommitted_node(self):
        deployments = [{'spec': {'replicas': 2, 'template': {'spec': spec('3Gi')}}}]
        jobs = [{'spec': {'jobTemplate': {'spec': {'template': {'spec': spec('2Gi')}}}}}]
        report = assess(deployments, jobs, [100, 200], 8192, 1024)
        self.assertEqual(report['capacity_gate'], 'review_required')
        self.assertEqual(report['conservative_required_mib'], 9216)
        self.assertEqual(assess(deployments, jobs, [200], 16384, 1024)['capacity_gate'], 'pass')


if __name__ == '__main__':
    unittest.main()
