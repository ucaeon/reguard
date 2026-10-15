"""Exercise real collection and verified backup under a temporary local node limit."""

import argparse
from datetime import datetime, timezone
import json
import signal
import time
from uuid import uuid4

from local_k3s import kube, run, ROOT

NODE = 'k3d-reguard-server-0'
DAGS = ('reguard_food_recall_reconcile', 'reguard_food_supplements', 'reguard_kc_products')


def sql(query):
    return kube('exec', 'deployment/metadata', '--', 'psql', '-U', 'airflow', '-d', 'airflow', '-Atc', query).strip()


def counters():
    value = run('docker', 'exec', NODE, 'sh', '-c',
                'cat /sys/fs/cgroup/memory.current; cat /sys/fs/cgroup/memory.events; cat /sys/fs/cgroup/cpu.stat')
    lines = value.splitlines()
    return {'memory_bytes': int(lines[0]), **{p[0]: int(p[1]) for p in map(str.split, lines[1:])}}


def pod_state():
    pods = json.loads(kube('get', 'pods', '-o', 'json'))['items']
    return {p['metadata']['name']: {
        'ready': all(c.get('ready', False) for c in p['status'].get('containerStatuses', [])),
        'restarts': sum(c.get('restartCount', 0) for c in p['status'].get('containerStatuses', []))}
        for p in pods if p['status'].get('phase') == 'Running'}



def restore_limits(original):
    # Docker update treats zero as "unchanged"; use the host ceiling for unlimited inputs.
    host = json.loads(run('docker', 'info', '--format', '{{json .}}'))
    desired = {
        'Memory': original['Memory'] or host['MemTotal'],
        'MemorySwap': original['MemorySwap'] if original['MemorySwap'] > 0 else host['MemTotal'] * 2,
        'NanoCpus': original['NanoCpus'] or host['NCPU'] * 1_000_000_000,
    }
    run('docker', 'update', '--memory', str(desired['Memory']),
        '--memory-swap', str(desired['MemorySwap']),
        '--cpus', str(desired['NanoCpus'] / 1e9), NODE)
    actual = json.loads(run('docker', 'inspect', NODE))[0]['HostConfig']
    if any(actual[k] != v for k, v in desired.items()):
        raise RuntimeError('Resource limit restoration failed')
    return desired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpus', type=float, default=2)
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--dag', action='append', choices=DAGS, help='DAGs whose completion must be verified')
    args = parser.parse_args()
    if not 0.1 <= args.cpus <= 2 or not 120 <= args.timeout <= 1800:
        parser.error('Use 0.1–2 CPUs and a 120–1800 second timeout')
    selected_dags = tuple(dict.fromkeys(args.dag or DAGS))
    identifier = 'capacity_' + uuid4().hex[:12]
    report_path = ROOT / 'data/verification' / (identifier + '.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    config = json.loads(run('docker', 'inspect', NODE))[0]['HostConfig']
    original = {k: config[k] for k in ('Memory', 'MemorySwap', 'NanoCpus', 'CpuPeriod', 'CpuQuota')}
    if original['CpuPeriod'] or original['CpuQuota']:
        raise RuntimeError('Unexpected existing CPU quota; do not override it')
    initial = counters()
    if initial['memory_bytes'] > 6.5 * 1024**3:
        raise RuntimeError('Node is too close to the proposed limit; inspect before testing')
    before = pod_state()
    report = {'run_id': identifier, 'started_at': datetime.now(timezone.utc).isoformat(),
              'limit_gib': 7, 'reserved_for_host_gib': 1, 'cpu_quota': args.cpus, 'selected_dags': selected_dags,
              'original_limits': original, 'before': before, 'samples': [], 'status': 'running'}
    report_path.write_text(json.dumps(report, indent=2))

    def interrupted(signum, frame):
        raise InterruptedError('Capacity verification interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    backup_name = 'database-backup-' + identifier.replace('_', '-')
    started = time.monotonic()
    try:
        run('docker', 'update', '--memory', '7g', '--memory-swap', '7g', '--cpus', str(args.cpus), NODE)
        print('LIMIT 7GiB without swap, CPUs=' + str(args.cpus), flush=True)
        for dag in selected_dags:
            kube('exec', 'deployment/scheduler', '--', 'airflow', 'dags', 'trigger', dag, '--run-id', identifier)
        kube('create', 'job', backup_name, '--from=cronjob/database-backup')
        print('START real collection DAGs and snapshot/restore backup', flush=True)
        while time.monotonic() - started < args.timeout:
            metric = counters()
            states = sql("select dag_id||'|'||state from dag_run where run_id='" + identifier + "' order by dag_id")
            tasks = sql("select dag_id||'|'||task_id from task_instance where run_id='" + identifier + "' and state='running'")
            backup = json.loads(kube('get', 'job', backup_name, '-o', 'json'))['status']
            metric.update(elapsed_seconds=round(time.monotonic()-started, 1), dags=states.splitlines(),
                          active_tasks=tasks.splitlines(), backup_active=backup.get('active', 0),
                          backup_succeeded=backup.get('succeeded', 0))
            report['samples'].append(metric)
            report_path.write_text(json.dumps(report, indent=2))
            if metric['oom_kill'] != initial['oom_kill'] or metric['oom'] != initial['oom']:
                raise RuntimeError('Node memory exhaustion detected')
            if backup.get('failed', 0) or '|failed' in states:
                raise RuntimeError('A collection or backup failed; inspect preserved run evidence')
            done = len(states.splitlines()) == len(selected_dags) and all(s.endswith('|success') for s in states.splitlines())
            if done and backup.get('succeeded') and time.monotonic()-started >= 120:
                break
            time.sleep(5)
        else:
            raise TimeoutError('Collection/backup did not complete within verification window')
        report['backup_log'] = kube('logs', 'job/' + backup_name)
        if 'SUCCESS ' not in report['backup_log'] or report['backup_log'].count('PASS restore ') != 4:
            raise RuntimeError('Full backup restore not proven')
        report['overlap_samples'] = sum(s['backup_active'] > 0 and any('|collect' in task for task in s['active_tasks']) for s in report['samples'])
        if not report['overlap_samples']:
            raise RuntimeError('No observed collect/backup overlap; do not report a pass')
        report['after'] = pod_state()
        for name, previous in before.items():
            current = report['after'].get(name)
            if current != previous or not current['ready']:
                raise RuntimeError('A service restarted or lost readiness: ' + name)
        report['peak_sample_memory_gib'] = round(max(s['memory_bytes'] for s in report['samples']) / 1024**3, 3)
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        report['limits_restored'] = False
        try:
            report['restored_limits'] = restore_limits(original)
            report['limits_restored'] = True
        except Exception as error:
            report['status'] = 'failed'
            report['restoration_error'] = str(error)
            raise
        finally:
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            report_path.write_text(json.dumps(report, indent=2))
            print('REPORT ' + str(report_path), flush=True)
            print('STATUS ' + report['status'] + ', limits_restored=' + str(report['limits_restored']), flush=True)
    print('PASS peak=' + str(report['peak_sample_memory_gib']) + 'GiB overlap_samples=' + str(report['overlap_samples']), flush=True)


if __name__ == '__main__':
    main()
