"""Cold, consistent recovery of all service volumes, including Kafka and checkpoints."""

import json
import os
from pathlib import Path
import subprocess
import tarfile
from release_resources import CLAIMS, resources, WORKLOADS
from release_install import digest


def helper(cluster, image):
    cluster.apply(
        [
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": "release-volume-copy",
                    "namespace": cluster.namespace,
                },
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "containers": [
                        {
                            "name": "copy",
                            "image": image,
                            "imagePullPolicy": "Never",
                            "command": ["sleep", "86400"],
                            "securityContext": {"runAsUser": 0},
                            "resources": {
                                "requests": {"cpu": "50m", "memory": "32Mi"},
                                "limits": {"cpu": "500m", "memory": "128Mi"},
                            },
                            "volumeMounts": [
                                {"name": name, "mountPath": "/volumes/" + name}
                                for name in CLAIMS
                            ],
                        }
                    ],
                    "volumes": [
                        {"name": name, "persistentVolumeClaim": {"claimName": name}}
                        for name in CLAIMS
                    ],
                },
            }
        ]
    )
    cluster.call(
        "wait", "--for=condition=Ready", "pod/release-volume-copy", "--timeout=300s"
    )


def snapshot(cluster, args, lock):
    if not args.snapshot:
        raise ValueError("--snapshot is required")
    # Stopping an executing collector would invalidate a claimed consistent recovery point.
    active = cluster.call(
        "exec",
        "deployment/metadata",
        "--",
        "psql",
        "-U",
        "airflow",
        "-d",
        "airflow",
        "-tAc",
        "select count(*) from task_instance where state in ('running','queued','restarting')",
    ).strip()
    if active != "0":
        raise ValueError("Airflow tasks are active; let them finish before snapshot")
    jobs = json.loads(cluster.call("get", "jobs", "-o", "json"))["items"]
    if any(j.get("status", {}).get("active", 0) for j in jobs):
        raise ValueError("A Kubernetes job is active")
    args.snapshot.mkdir(parents=True, exist_ok=False)
    os.chmod(args.snapshot, 0o700)
    deployments = json.loads(cluster.call("get", "deployments", "-o", "json"))["items"]
    replicas = {d["metadata"]["name"]: d["spec"]["replicas"] for d in deployments}
    cronjobs = json.loads(cluster.call("get", "cronjobs", "-o", "json"))["items"]
    marker = json.loads(
        cluster.call("get", "configmap", "reguard-release", "-o", "json")
    )["data"]
    if marker["version"] != lock["version"]:
        raise ValueError("Snapshot release differs from bundle")
    images = json.loads(marker["images"])
    try:
        for c in cronjobs:
            cluster.call(
                "patch",
                "cronjob",
                c["metadata"]["name"],
                "--type=merge",
                "-p",
                '{"spec":{"suspend":true}}',
            )
        cluster.scale("scheduler", 0)
        cluster.call(
            "wait", "--for=delete", "pod", "-l", "app=scheduler", "--timeout=180s"
        )
        active = cluster.call(
            "exec",
            "deployment/metadata",
            "--",
            "psql",
            "-U",
            "airflow",
            "-d",
            "airflow",
            "-tAc",
            "select count(*) from task_instance where state in ('running','queued','restarting')",
        ).strip()
        jobs = json.loads(cluster.call("get", "jobs", "-o", "json"))["items"]
        if active != "0" or any(j.get("status", {}).get("active", 0) for j in jobs):
            raise ValueError(
                "Work started during quiescence; snapshot aborted without copying data"
            )
        # Stop ingress and writers before the broker and databases.
        for name in reversed(WORKLOADS):
            if name in replicas and name != "scheduler":
                cluster.scale(name, 0)
                cluster.call(
                    "wait", "--for=delete", "pod", "-l", "app=" + name, "--timeout=180s"
                )
        helper(cluster, images["postgres"])
        files = {}
        for name in CLAIMS:
            archive = args.snapshot / (name + ".tar")
            with archive.open("wb") as output:
                subprocess.run(
                    cluster.prefix
                    + [
                        "exec",
                        "release-volume-copy",
                        "--",
                        "tar",
                        "-C",
                        "/volumes/" + name,
                        "-cpf",
                        "-",
                        ".",
                    ],
                    stdout=output,
                    check=True,
                )
            files[archive.name] = digest(archive)
        manifest = {
            "release_sha256": digest(args.bundle / "release.json"),
            "credentials_sha256": digest(args.secrets),
            "files": files,
            "replicas": replicas,
            "namespace": cluster.namespace,
            "consistency": "all-deployments-stopped",
        }
        (args.snapshot / "snapshot.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        print("Consistent snapshot completed: " + str(args.snapshot), flush=True)
    finally:
        cluster.call(
            "delete",
            "pod",
            "release-volume-copy",
            "--ignore-not-found=true",
            "--wait=true",
        )
        resume_errors = []
        for name in WORKLOADS:
            if replicas.get(name, 0):
                try:
                    cluster.scale(name, replicas[name])
                    cluster.ready(name)
                except RuntimeError as error:
                    resume_errors.append(str(error))
        for c in cronjobs:
            try:
                cluster.call(
                    "patch",
                    "cronjob",
                    c["metadata"]["name"],
                    "--type=merge",
                    "-p",
                    json.dumps({"spec": {"suspend": c["spec"].get("suspend", False)}}),
                )
            except RuntimeError as error:
                resume_errors.append(str(error))
        if resume_errors:
            raise RuntimeError(
                "Some services could not resume: " + "; ".join(resume_errors)
            )


def validate_snapshot(directory, bundle, credentials):
    manifest = json.loads((directory / "snapshot.json").read_text())
    if manifest["release_sha256"] != digest(bundle / "release.json") or manifest[
        "credentials_sha256"
    ] != digest(credentials):
        raise ValueError(
            "Snapshot requires its original release bundle and credentials"
        )
    if set(manifest["files"]) != {name + ".tar" for name in CLAIMS}:
        raise ValueError("Incomplete snapshot inventory")
    for name, expected in manifest["files"].items():
        archive = directory / name
        if digest(archive) != expected:
            raise ValueError("Snapshot checksum mismatch: " + name)
        with tarfile.open(archive) as tar:
            for member in tar:
                p = Path(member.name)
                if (
                    p.is_absolute()
                    or ".." in p.parts
                    or member.isdev()
                    or member.isfifo()
                ):
                    raise ValueError("Unsafe snapshot entry")
                if member.issym() or member.islnk():
                    target = Path(member.linkname)
                    if target.is_absolute() or ".." in target.parts:
                        raise ValueError("Unsafe snapshot link")
    return manifest


def restore(cluster, args, config, credentials, images, lock):
    if not args.snapshot:
        raise ValueError("--snapshot is required")
    validate_snapshot(args.snapshot, args.bundle, args.secrets)
    for resource in ("deployments", "pvc"):
        if json.loads(cluster.call("get", resource, "-o", "json"))["items"]:
            raise ValueError(
                "Restore requires a new namespace with no deployments or PVCs"
            )
    base = [
        o
        for o in resources(config, credentials, images)
        if o["kind"] in ("Namespace", "PersistentVolumeClaim", "StorageClass")
    ]
    cluster.apply(base)
    try:
        helper(cluster, images["postgres"])
        for name in CLAIMS:
            content = cluster.call(
                "exec",
                "release-volume-copy",
                "--",
                "find",
                "/volumes/" + name,
                "-mindepth",
                "1",
                "-maxdepth",
                "1",
            ).strip()
            if content:
                raise ValueError("Refusing to overwrite nonempty volume: " + name)
            with (args.snapshot / (name + ".tar")).open("rb") as stream:
                subprocess.run(
                    cluster.prefix
                    + [
                        "exec",
                        "-i",
                        "release-volume-copy",
                        "--",
                        "tar",
                        "-C",
                        "/volumes/" + name,
                        "-xpf",
                        "-",
                    ],
                    stdin=stream,
                    check=True,
                )
        print("All volumes restored; starting the original release.", flush=True)
    finally:
        cluster.call(
            "delete",
            "pod",
            "release-volume-copy",
            "--ignore-not-found=true",
            "--wait=true",
        )
