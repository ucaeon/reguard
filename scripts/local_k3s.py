"""Single-node local migration; existing Docker volumes remain the rollback source."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from k3s_resources import resources

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/k3s"
CONTEXT = STATE / "kubeconfig"
NAMESPACE = "reguard"
SOURCES = {
    "postgres": "reguard-local-postgres-1",
    "metadata": "reguard-airflow-metadata-1",
    "kafka": "reguard-events-kafka-1",
    "api-server": "reguard-airflow-api-server-1",
    "scheduler": "reguard-airflow-scheduler-1",
    "dag-processor": "reguard-airflow-dag-processor-1",
    "spark": "reguard-airflow-spark-1",
}


def run(*args, **kwargs):
    return subprocess.run(
        args, check=True, text=True, capture_output=True, **kwargs
    ).stdout


def kube(*args, **kwargs):
    return run(
        "kubectl", "--kubeconfig", str(CONTEXT), "-n", NAMESPACE, *args, **kwargs
    )


def source_config():
    # Inspect preserves the exact running credentials without logging or writing them.
    containers = json.loads(run("docker", "inspect", *SOURCES.values()))
    return {name: container for name, container in zip(SOURCES, containers)}


def prepare():
    STATE.mkdir(parents=True, exist_ok=True)
    source = source_config()
    clusters = json.loads(run("k3d", "cluster", "list", "-o", "json"))
    if not any(c["name"] == "reguard" for c in clusters):
        args = [
            "k3d",
            "cluster",
            "create",
            "--config",
            str(ROOT / "infra/k3s/cluster.yaml"),
            "--volume",
            str(ROOT) + ":/workspace@server:0",
        ]
        volumes = {
            m["Name"]
            for c in source.values()
            for m in c["Mounts"]
            if m["Type"] == "volume" and m.get("Name", "").startswith("reguard-")
        }
        for volume in sorted(volumes):
            args += ["--volume", volume + ":/persistent/" + volume + "@server:0"]
        print(run(*args))
    CONTEXT.write_text(run("k3d", "kubeconfig", "get", "reguard"))
    CONTEXT.chmod(0o600)
    images = {c["Config"]["Image"] for c in source.values()} | {
        "reguard-" + s + ":validation"
        for s in ("web", "member", "safety", "notification")
    }
    # Import directly: some k3d/k3s combinations report success without registering images.
    with subprocess.Popen(
        ["docker", "image", "save", *sorted(images)], stdout=subprocess.PIPE
    ) as source:
        imported = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "k3d-reguard-server-0",
                "ctr",
                "-n",
                "k8s.io",
                "images",
                "import",
                "--platform",
                "linux/arm64",
                "-",
            ],
            stdin=source.stdout,
            capture_output=True,
        )
        source.stdout.close()
        if source.wait() or imported.returncode:
            raise RuntimeError("Local image import failed")
    available = run(
        "docker", "exec", "k3d-reguard-server-0", "crictl", "images", "-o", "json"
    )
    tags = {
        tag
        for image in json.loads(available)["images"]
        for tag in image.get("repoTags", [])
    }
    for image in images:
        expected = "docker.io/" + ("library/" if "/" not in image else "") + image
        if expected not in tags:
            raise RuntimeError("Missing imported image: " + image)
    print("All runtime images verified")


def stop_source():
    active = run(
        "docker",
        "exec",
        SOURCES["metadata"],
        "psql",
        "-U",
        "airflow",
        "-d",
        "airflow",
        "-Atc",
        "select count(*) from task_instance where state in ('running','queued','restarting')",
    ).strip()
    if active != "0":
        raise RuntimeError("Airflow tasks still active; wait before switching")
    source = source_config()
    snapshot = {
        name: {
            "restart": c["HostConfig"]["RestartPolicy"]["Name"],
            "running": c["State"]["Running"],
        }
        for name, c in source.items()
    }
    path = STATE / "source-state.json"
    if path.exists():
        raise RuntimeError("Source snapshot already exists; do not overwrite it")
    path.write_text(json.dumps(snapshot))
    for name in (
        "scheduler",
        "dag-processor",
        "api-server",
        "spark",
        "kafka",
        "postgres",
        "metadata",
    ):
        run("docker", "update", "--restart=no", SOURCES[name])
        run("docker", "stop", "-t", "120", SOURCES[name])
    print("Source stopped; volumes retained")


def rollback():
    snapshot = json.loads((STATE / "source-state.json").read_text())
    kube("scale", "deployment", "--all", "--replicas=0")
    kube("wait", "--for=delete", "pod", "--all", "--timeout=300s")
    for name in (
        "postgres",
        "metadata",
        "kafka",
        "spark",
        "api-server",
        "scheduler",
        "dag-processor",
    ):
        run("docker", "update", "--restart=" + snapshot[name]["restart"], SOURCES[name])
        if snapshot[name]["running"]:
            run("docker", "start", SOURCES[name])
    (STATE / "source-state.json").unlink()
    print("Restored Compose services; k3s workloads stopped")


def apply():
    source = source_config()
    active = [name for name, c in source.items() if c["State"]["Running"]]
    if active:
        raise RuntimeError(
            "Stop source writers before attaching volumes: " + ", ".join(active)
        )
    payload = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "List",
            "items": resources(source, ROOT, NAMESPACE),
        }
    )
    print(
        kube(
            "apply",
            "--server-side",
            "--field-manager=reguard-local",
            "-f",
            "-",
            input=payload,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["prepare", "stop-source", "apply", "status", "rollback"]
    )
    action = parser.parse_args().action
    if action == "prepare":
        prepare()
    elif action == "apply":
        apply()
    elif action == "stop-source":
        stop_source()
    elif action == "rollback":
        rollback()
    else:
        print(kube("get", "pods,pvc"))
