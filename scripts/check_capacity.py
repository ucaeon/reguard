"""Read Kubernetes memory usage and limits without exporting environment or secrets."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import time


def memory_mib(value):
    units = {'Ki': Decimal(1) / 1024, 'Mi': Decimal(1), 'Gi': Decimal(1024),
             'K': Decimal(1000) / 1048576, 'M': Decimal(1000000) / 1048576,
             'G': Decimal(1000000000) / 1048576}
    for suffix, factor in units.items():
        if value.endswith(suffix):
            return float(Decimal(value[:-len(suffix)]) * factor)
    return float(Decimal(value) / 1048576)


def pod_limit(spec):
    containers = spec.get('containers', []) + spec.get('initContainers', [])
    if any('memory' not in c.get('resources', {}).get('limits', {}) for c in containers):
        raise ValueError('Container without memory limit')
    app = sum(memory_mib(c['resources']['limits']['memory']) for c in spec['containers'])
    init = max((memory_mib(c['resources']['limits']['memory'])
                for c in spec.get('initContainers', [])), default=0)
    return max(app, init)


def assess(deployments, cronjobs, samples, node_mib, reserve_mib):
    limits = sum(pod_limit(d['spec']['template']['spec']) * d['spec'].get('replicas', 1)
                 for d in deployments)
    # Conservatively allow every scheduled job to overlap application workloads.
    jobs = sum(pod_limit(j['spec']['jobTemplate']['spec']['template']['spec']) for j in cronjobs)
    required = limits + jobs + reserve_mib
    return {'measured_at': datetime.now(timezone.utc).isoformat(),
            'candidate_memory_mib': node_mib, 'reserved_memory_mib': reserve_mib,
            'deployment_limits_mib': limits, 'scheduled_job_limits_mib': jobs,
            'observed_sample_max_mib': max(samples), 'sample_count': len(samples),
            'conservative_required_mib': required,
            'capacity_gate': 'pass' if required <= node_mib else 'review_required',
            'limitation': 'Samples are not peak-load proof. Limits are a conservative envelope, not allocated memory. Airflow child processes share parent pod limits.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconfig', required=True)
    parser.add_argument('--namespace', default='reguard')
    parser.add_argument('--node-mib', type=int, default=8192)
    parser.add_argument('--reserve-mib', type=int, default=1024)
    parser.add_argument('--samples', type=int, default=6)
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.samples < 1 or not 0 <= args.interval <= 60 or args.node_mib <= 0 or args.reserve_mib < 0:
        parser.error('Invalid sampling or capacity parameters')

    def kube(*command):
        return subprocess.check_output(['kubectl', '--kubeconfig', args.kubeconfig,
                                        '-n', args.namespace, *command], text=True, timeout=30)

    deployments = json.loads(kube('get', 'deployments', '-o', 'json'))['items']
    jobs = json.loads(kube('get', 'cronjobs', '-o', 'json'))['items']
    samples = []
    for index in range(args.samples):
        rows = kube('top', 'pods', '--no-headers').splitlines()
        if not rows:
            raise RuntimeError('No pod metrics; capacity cannot be verified')
        samples.append(sum(memory_mib(row.split()[2]) for row in rows))
        if index + 1 < args.samples:
            time.sleep(args.interval)
    report = assess(deployments, jobs, samples, args.node_mib, args.reserve_mib)
    output = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    print(output)
    return 0 if report['capacity_gate'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
