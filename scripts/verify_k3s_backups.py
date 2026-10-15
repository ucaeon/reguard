"""Check backup persistence and fail-closed behavior without touching source data."""

import json
import time
from local_k3s import kube, run


def verified_sets(path):
    return set(
        run(
            "docker",
            "exec",
            "k3d-reguard-server-0",
            "find",
            path,
            "-mindepth",
            "2",
            "-maxdepth",
            "2",
            "-name",
            "VERIFIED",
            "-type",
            "f",
        ).splitlines()
    )


def main():
    claim = json.loads(kube("get", "pvc", "database-backups", "-o", "json"))
    volume = json.loads(kube("get", "pv", claim["spec"]["volumeName"], "-o", "json"))
    assert volume["spec"]["persistentVolumeReclaimPolicy"] == "Retain"
    path = (volume["spec"].get("local") or volume["spec"].get("hostPath"))["path"]
    before = verified_sets(path)
    assert before, "No verified backup sets"
    name = "database-backup-failure-check-" + str(int(time.time()))
    job = json.loads(
        kube(
            "create",
            "job",
            name,
            "--from=cronjob/database-backup",
            "--dry-run=client",
            "-o",
            "json",
        )
    )
    job["spec"]["backoffLimit"] = 0
    job["spec"]["activeDeadlineSeconds"] = 90
    for entry in job["spec"]["template"]["spec"]["containers"][0]["env"]:
        if entry["name"] == "MEMBER_DB_PASSWORD":
            entry.pop("valueFrom")
            entry["value"] = "invalid-backup-test-password"
    kube("create", "-f", "-", input=json.dumps(job))
    for _ in range(60):
        status = json.loads(kube("get", "job", name, "-o", "json"))["status"]
        if any(
            c["type"] == "Failed" and c["status"] == "True"
            for c in status.get("conditions", [])
        ):
            break
        if status.get("succeeded"):
            raise AssertionError("Invalid credentials accepted")
        time.sleep(2)
    else:
        raise RuntimeError("Failure test timed out")
    after = verified_sets(path)
    assert before.issubset(after), "A valid backup disappeared on failure"
    log = kube("logs", "job/" + name)
    assert "SUCCESS " not in log and "FAILED " in log
    print("PASS invalid credentials fail the Job; existing verified backups remain")
    latest = sorted(before)[-1].removesuffix("/VERIFIED")
    print(
        run(
            "docker",
            "exec",
            "k3d-reguard-server-0",
            "sh",
            "-ec",
            'cd "$1"; sha256sum --check SHA256SUMS',
            "sh",
            latest,
        ).strip()
    )
    print(
        run(
            "docker",
            "exec",
            "k3d-reguard-server-0",
            "cat",
            latest + "/reguard_safety.restored-counts",
        ).strip()
    )
    print(
        "PASS saved backup checksums and restored table counts remain after Job completion"
    )


if __name__ == "__main__":
    main()
