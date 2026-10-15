"""Install the local backup schedule; retain any already provisioned backup volume."""

import json
from local_k3s import ROOT, kube


def resource_list(text):
    items = []
    decoder = json.JSONDecoder()
    while text.strip():
        value, end = decoder.raw_decode(text.lstrip())
        items.extend(value["items"] if value.get("kind") == "List" else [value])
        text = text.lstrip()[end:]
    return {"apiVersion": "v1", "kind": "List", "items": items}


def configure():
    script = (ROOT / "infra/k3s/backup/run.sh").read_text()
    config = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "database-backup-script", "namespace": "reguard"},
        "data": {"run.sh": script},
    }
    kube("apply", "-f", "-", input=json.dumps(config))
    manifest = resource_list(
        kube(
            "create",
            "--dry-run=client",
            "-f",
            str(ROOT / "infra/k3s/backup/cronjob.yaml"),
            "-o",
            "json",
        )
    )
    existing = kube(
        "get", "pvc", "database-backups", "--ignore-not-found", "-o", "json"
    )
    if existing:
        # A bound claim's storage class is immutable; retain its existing volume below.
        storage_class = json.loads(existing)["spec"]["storageClassName"]
        for item in manifest["items"]:
            if item["kind"] == "PersistentVolumeClaim":
                item["spec"]["storageClassName"] = storage_class
    kube("apply", "-f", "-", input=json.dumps(manifest))
    claim = json.loads(kube("get", "pvc", "database-backups", "-o", "json"))
    volume = claim["spec"].get("volumeName")
    if volume:
        kube(
            "patch",
            "pv",
            volume,
            "--type=merge",
            "-p",
            json.dumps({"spec": {"persistentVolumeReclaimPolicy": "Retain"}}),
        )
    print(
        "Configured daily 03:30 Asia/Seoul backup, 14-day retention, full restore verification"
    )


if __name__ == "__main__":
    configure()
