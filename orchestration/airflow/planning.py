"""Stable collection plans and verified baseline selection."""

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from pipelines.collectors.providers import SOURCES
from .state import root, atomic_json, state_db, database
from .state import KST


def verified_kc_baseline(start, today):
    """A completed full load covers the old gap; still overlap its first day."""
    candidates = sorted(
        (root() / "kc-snapshots").glob("*/products-report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for report_path in candidates:
        report = json.loads(report_path.read_text())
        if (
            report.get("status") != "complete"
            or report.get("snapshot_missing_in_db") != 0
        ):
            continue
        snapshot_day = (
            datetime.fromisoformat(report["snapshot_at"]).astimezone(KST).date()
        )
        overlap = snapshot_day - timedelta(days=1)
        if overlap <= start or snapshot_day > today:
            continue
        if report.get("processed") != report.get("accepted") or report.get(
            "raw"
        ) != report.get("accepted", 0) + report.get("rejected", 0):
            raise ValueError("KC_BASELINE_INCOMPLETE")
        raw = report_path.parent / "cert-list.json"
        meta = json.loads(raw.with_suffix(".download.json").read_text())
        with raw.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (
            digest != report["sha256"]
            or digest != meta["sha256"]
            or report["snapshot_at"] != meta["started_at"]
        ):
            raise ValueError("KC_BASELINE_HASH_MISMATCH")
        with database() as connection:
            count = connection.execute(
                "SELECT count(*) FROM products WHERE source='SAFETY_KC'"
            ).fetchone()[0]
        if count < report["accepted"]:
            raise ValueError("KC_BASELINE_DATABASE_MISSING")
        return overlap, {
            "report": str(report_path),
            "sha256": digest,
            "snapshot_at": report["snapshot_at"],
            "accepted": report["accepted"],
            "rejected": report["rejected"],
        }
    return start, None


def plan(source, mode, workflow_id, end_day=None, start_day=None, now=None):
    if source not in SOURCES or mode not in {
        "incremental",
        "reconcile",
        "backfill",
        "snapshot",
    }:
        raise ValueError("INVALID_COLLECTION_PLAN")
    if mode == "snapshot" and not source.startswith("food-"):
        raise ValueError("SNAPSHOT_FOOD_ONLY")
    identifier = str(uuid5(NAMESPACE_URL, "reguard:airflow:" + workflow_id))
    path = root() / "runs" / identifier / "plan.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if (
            saved["source"] != source
            or saved.get("requested_mode", saved["mode"]) != mode
        ):
            raise ValueError("RUN_PLAN_CONFLICT")
        return str(path)
    requested_mode = mode
    now = now or datetime.now(KST)
    today = now.astimezone(KST).date()
    end = date.fromisoformat(end_day) if end_day else today
    start = date.fromisoformat(start_day) if start_day else end - timedelta(days=2)
    if mode == "reconcile" and source != "food-recalls":
        raise ValueError("FULL_INITIAL_LOAD_IS_SEPARATE")
    if mode == "incremental":
        with state_db() as connection:
            row = connection.execute(
                "SELECT day FROM watermarks WHERE source=?", (source,)
            ).fetchone()
        if row:
            start = min(start, date.fromisoformat(row[0]) - timedelta(days=1))
    baseline = None
    if source == "kc-products" and mode == "incremental":
        start, baseline = verified_kc_baseline(start, today)
    recovery = False
    if source.startswith("food-") and mode not in {"reconcile", "snapshot"}:
        if not 0 <= (today - start).days <= 6:
            if mode != "incremental":
                raise ValueError("FOOD_GAP_REQUIRES_SNAPSHOT_RECOVERY")
            mode = "snapshot"
            recovery = True
            start = end - timedelta(days=2)
    if start > end or end > today or (end - start).days > 30:
        raise ValueError("INVALID_DATE_RANGE")
    days = (
        [None]
        if source.startswith("food-")
        else [
            (start + timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)
        ]
    )
    parts = [
        {"run_id": str(uuid5(NAMESPACE_URL, identifier + ":" + str(day))), "day": day}
        for day in days
    ]
    value = {
        "id": identifier,
        "source": source,
        "mode": mode,
        "requested_mode": requested_mode,
        "start_day": start.isoformat(),
        "end_day": end.isoformat(),
        "created_at": now.isoformat(),
        "parts": parts,
        "gap_recovery": recovery,
        "baseline_recovery": baseline,
    }
    atomic_json(path, value)
    return str(path)


def read_plan(path):
    path = Path(path).resolve()
    if not path.is_relative_to((root() / "runs").resolve()) or path.name != "plan.json":
        raise ValueError("INVALID_PLAN_PATH")
    return json.loads(path.read_text())


def directories(value):
    return [
        root() / "raw" / value["source"] / part["run_id"] for part in value["parts"]
    ]
