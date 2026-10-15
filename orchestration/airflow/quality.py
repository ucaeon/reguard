"""Collection readiness and data quality checks."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from pipelines.collectors.providers import SOURCES
from .state import root, atomic_json, state_db, database
from .state import KST
from .quality_status import dimensions


def prepare_quality(workflow_id, now=None):
    now = now or datetime.now(KST)
    now = now.astimezone(KST)
    schedules = {
        "food-products": (19, 30),
        "food-supplements": (20, 0),
        "kc-products": (1, 30),
        "food-recalls": (None, 5),
        "safety-recalls": (None, 15),
    }
    required = {}
    for source, (hour, minute) in schedules.items():
        scheduled = now.replace(
            hour=now.hour if hour is None else hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if scheduled > now:
            scheduled -= timedelta(hours=1) if hour is None else timedelta(days=1)
        required[source] = {
            "day": scheduled.date().isoformat(),
            "completed_after": scheduled.isoformat(),
        }
    path = (
        root() / "quality" / str(uuid5(NAMESPACE_URL, workflow_id)) / "readiness.json"
    )
    if not path.exists():
        atomic_json(
            path,
            {
                "required": required,
                "started_at": now.isoformat(),
                "deadline": (now + timedelta(hours=4)).isoformat(),
                "status": "waiting",
            },
        )
    return str(path)


def collection_ready(path, now=None):
    now = now or datetime.now(KST)
    report = json.loads(Path(path).read_text())
    with state_db() as connection:
        marks = {
            s: (d, t) for s, d, t in connection.execute("SELECT * FROM watermarks")
        }
    pending = [
        source
        for source, required in report["required"].items()
        if source not in marks
        or marks[source][0] < required["day"]
        or datetime.fromisoformat(marks[source][1])
        < datetime.fromisoformat(required["completed_after"])
    ]
    report["pending_sources"] = pending
    report["checked_at"] = now.isoformat()
    report["status"] = (
        "ready"
        if not pending
        else (
            "collection_delayed"
            if now >= datetime.fromisoformat(report["deadline"])
            else "waiting"
        )
    )
    atomic_json(Path(path), report)
    if report["status"] == "collection_delayed":
        raise RuntimeError("COLLECTION_DELAYED: " + ", ".join(pending))
    return not pending


def quality_report():
    with database() as connection:
        products = dict(
            connection.execute(
                "SELECT source,count(*) FROM products GROUP BY source"
            ).fetchall()
        )
        recalls = dict(
            connection.execute(
                "SELECT source,count(*) FROM recalls GROUP BY source"
            ).fetchall()
        )
        quarantine = connection.execute(
            "SELECT count(*) FROM ingestion_quarantine WHERE created_at > now()-interval '24 hours'"
        ).fetchone()[0]
        unmatched = dict(
            connection.execute(
                "SELECT r.source,count(*) FROM recalls r WHERE NOT EXISTS (SELECT 1 FROM recall_product_matches m WHERE m.recall_id=r.id) GROUP BY r.source"
            ).fetchall()
        )
        matched_recalls = connection.execute(
            "SELECT count(DISTINCT recall_id) FROM recall_product_matches"
        ).fetchone()[0]
        unmatched_reasons = [
            {"source": source, "reason": reason, "count": count}
            for source, reason, count in connection.execute(
                Path(__file__).with_name("unmatched_reasons.sql").read_text()
            ).fetchall()
        ]
    with state_db() as connection:
        marks = {
            s: {"day": d, "completed_at": t}
            for s, d, t in connection.execute("SELECT * FROM watermarks")
        }
    now = datetime.now(timezone.utc)
    stale = [
        s
        for s in SOURCES
        if s not in marks
        or (now - datetime.fromisoformat(marks[s]["completed_at"])).total_seconds()
        > 26 * 3600
    ]
    reviewed = []
    for source in ("food-products", "food-supplements", "food-recalls"):
        snapshots = list((root() / "raw" / source).glob("*/source-rejections.json"))
        if snapshots:
            latest = max(snapshots, key=lambda p: p.stat().st_mtime)
            rows = json.loads(latest.read_text())
            if rows:
                reviewed.append(
                    {"source": source, "count": len(rows), "evidence": str(latest)}
                )
    report = {
        "dimensions": dimensions(quarantine, stale, unmatched, matched_recalls),
        "status_scope": "ingestion_and_freshness",
        "reviewed_source_rejections": reviewed,
        "checked_at": now.isoformat(),
        "products": products,
        "recalls": recalls,
        "quarantined_24h": quarantine,
        "unmatched_recalls": unmatched,
        "unmatched_reasons": unmatched_reasons,
        "watermarks": marks,
        "stale_sources": stale,
        "status": "failed" if quarantine or stale else "passed",
    }
    path = root() / "quality" / (now.strftime("%Y%m%dT%H%M%S") + ".json")
    atomic_json(path, report)
    if report["status"] != "passed":
        raise RuntimeError("QUALITY_CHECK_FAILED: " + str(path))
    return {"report": str(path), "status": "passed"}
