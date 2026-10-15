"""Install a release on an existing single-node k3s, without Docker or source mounts.

Run bootstrap.sh first on Linux. Supply --node only for isolated k3d testing.
Secrets stay outside the release bundle. Kubernetes access must be explicit.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from release_resources import resources, new_secrets, WORKLOADS


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_bundle(bundle):
    lock = json.loads((bundle / "release.json").read_text())
    if lock["platform"] != "linux/arm64":
        raise ValueError("Unsupported release architecture")
    files = {
        **lock["files"],
        **{i["archive"]: i["sha256"] for i in lock["images"].values()},
    }
    for name, expected in files.items():
        if Path(name).name != name or digest(bundle / name) != expected:
            raise ValueError("Release checksum mismatch: " + name)
    return lock


class Cluster:
    def __init__(self, kubeconfig, namespace, node=None):
        self.prefix = ["kubectl", "--kubeconfig", str(kubeconfig), "-n", namespace]
        self.namespace = namespace
        self.node = node

    def call(self, *args, input=None):
        result = subprocess.run(
            self.prefix + list(args), input=input, text=True, capture_output=True
        )
        if result.returncode:
            # Do not print input manifests: they contain credentials.
            raise RuntimeError(
                "kubectl " + args[0] + " failed: " + result.stderr[:1500]
            )
        return result.stdout

    def apply(self, objects):
        self.call(
            "apply",
            "--server-side",
            "--field-manager=reguard-release",
            "-f",
            "-",
            input=json.dumps({"apiVersion": "v1", "kind": "List", "items": objects}),
        )

    def ready(self, name):
        print("Waiting for " + name, flush=True)
        self.call("rollout", "status", "deployment/" + name, "--timeout=600s")

    def scale(self, name, count):
        self.call("scale", "deployment/" + name, "--replicas=" + str(count))

    def import_images(self, bundle, lock):
        prefix = ["docker", "exec", "-i", self.node] if self.node else []
        refs = {}
        for name, item in lock["images"].items():
            with (bundle / item["archive"]).open("rb") as stream:
                subprocess.run(
                    prefix
                    + [
                        "ctr",
                        "--namespace",
                        "k8s.io",
                        "images",
                        "import",
                        "--platform",
                        "linux/arm64",
                        "-",
                    ],
                    stdin=stream,
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
            raw = subprocess.check_output(
                prefix + ["ctr", "--namespace", "k8s.io", "images", "ls"], text=True
            )
            tag = item["tag"]
            full = "docker.io/library/" + tag
            matches = [
                line.split()[2]
                for line in raw.splitlines()[1:]
                if line.split()[0] == full
            ]
            if len(matches) != 1 or matches[0] != item["id"]:
                raise ValueError("Imported image not found: " + name)
            # Use the content digest, never the tag, in the installed Pod specs.
            refs[name] = full.split(":")[0] + "@" + matches[0]
            subprocess.run(
                prefix
                + [
                    "ctr",
                    "--namespace",
                    "k8s.io",
                    "images",
                    "tag",
                    "--force",
                    full,
                    refs[name],
                ],
                stdout=subprocess.DEVNULL,
                check=True,
            )
        return refs


def job(cluster, name, pod):
    pod = json.loads(json.dumps(pod))
    pod["restartPolicy"] = "Never"
    pod.pop("terminationGracePeriodSeconds", None)
    for container in pod["containers"]:
        for key in ("startupProbe", "livenessProbe", "readinessProbe"):
            container.pop(key, None)
    cluster.call("delete", "job", name, "--ignore-not-found=true", "--wait=true")
    cluster.apply(
        [
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"name": name, "namespace": cluster.namespace},
                "spec": {
                    "backoffLimit": 0,
                    "activeDeadlineSeconds": 600,
                    "template": {"spec": pod},
                },
            }
        ]
    )
    cluster.call("wait", "--for=condition=complete", "job/" + name, "--timeout=610s")


def initialize(cluster, objects):
    pods = {
        o["metadata"]["name"]: o["spec"]["template"]["spec"]
        for o in objects
        if o["kind"] == "Deployment"
    }
    pod = json.loads(json.dumps(pods["api-server"]))
    pod["containers"][0]["args"] = [
        "bash",
        "-ec",
        'airflow db migrate && airflow pools set food_api 1 "Shared food API key" && airflow pools set safety_api 1 "Safety Korea API"',
    ]
    job(cluster, "initialize-airflow", pod)
    pod = json.loads(json.dumps(pods["kafka"]))
    pod.pop("initContainers", None)
    pod["volumes"] = []
    c = pod["containers"][0]
    c["volumeMounts"] = []
    c["command"] = ["/bin/bash", "-ec"]
    c["args"] = [
        'for topic in reguard.raw-records.v1 reguard.recall-alerts.v1; do /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic "$topic" --partitions 1 --replication-factor 1; done'
    ]
    job(cluster, "initialize-kafka", pod)


def install(cluster, config, credentials, images, lock):
    objects = resources(config, credentials, images)
    fingerprint = hashlib.sha256(
        json.dumps(credentials, sort_keys=True).encode()
    ).hexdigest()
    marker_data = {
        "version": lock["version"],
        "images": json.dumps(images, sort_keys=True),
        "credentials_sha256": fingerprint,
    }
    existing = json.loads(cluster.call("get", "deployment", "-o", "json"))["items"]
    if existing:
        marker = json.loads(
            cluster.call("get", "configmap", "reguard-release", "-o", "json")
        )["data"]
        if marker != marker_data:
            raise ValueError(
                "Existing deployment has another release or credentials; use a fresh namespace"
            )
    base = [o for o in objects if o["kind"] not in ("Deployment", "CronJob")]
    cluster.apply(base)
    cluster.apply(
        [
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "reguard-release", "namespace": cluster.namespace},
                "data": marker_data,
            }
        ]
    )
    for name in ("postgres", "metadata", "kafka"):
        cluster.apply(
            [
                o
                for o in objects
                if o["kind"] == "Deployment" and o["metadata"]["name"] == name
            ]
        )
        cluster.ready(name)
    initialize(cluster, objects)
    for name in WORKLOADS[3:]:
        cluster.apply(
            [
                o
                for o in objects
                if o["kind"] == "Deployment" and o["metadata"]["name"] == name
            ]
        )
        cluster.ready(name)
    cluster.apply([o for o in objects if o["kind"] == "CronJob"])
    print(
        "All release workloads ready; collection DAGs remain paused on first install.",
        flush=True,
    )


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action", choices=["secrets", "verify", "install", "snapshot", "restore"]
    )
    p.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    p.add_argument("--config", type=Path)
    p.add_argument("--secrets", type=Path, required=True)
    p.add_argument("--kubeconfig", type=Path)
    p.add_argument("--node", help="k3d node name, only for local verification")
    p.add_argument("--snapshot", type=Path)
    return p


def main():
    args = parser().parse_args()
    if args.action == "secrets":
        fd = os.open(args.secrets, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(new_secrets(), stream, indent=2)
        print(
            "Created credentials file. Fill provider and SMTP credentials before production installation."
        )
        return
    lock = verify_bundle(args.bundle)
    if args.action == "verify":
        print("Release checksums verified")
        return
    if not args.kubeconfig or not args.config:
        raise ValueError("--kubeconfig and --config are required")
    if args.secrets.stat().st_mode & 0o077:
        raise ValueError("Credentials file must have permissions 0600")
    config = json.loads(args.config.read_text())
    credentials = json.loads(args.secrets.read_text())
    from release_resources import validate

    validate(config, credentials)
    cluster = Cluster(args.kubeconfig, config["namespace"], args.node)
    nodes = json.loads(cluster.call("get", "nodes", "-o", "json"))["items"]
    if len(nodes) != 1 or nodes[0]["status"]["nodeInfo"]["architecture"] != "arm64":
        raise ValueError("This release requires one ARM64 node")
    expected_version = lock["k3s"].replace("-k3s", "+k3s")
    if nodes[0]["status"]["nodeInfo"]["kubeletVersion"] != expected_version:
        raise ValueError("The cluster k3s version does not match this release")
    if args.action == "snapshot":
        from release_recovery import snapshot

        snapshot(cluster, args, lock)
        return
    images = cluster.import_images(args.bundle, lock)
    if args.action == "restore":
        from release_recovery import restore

        restore(cluster, args, config, credentials, images, lock)
    install(cluster, config, credentials, images, lock)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
