"""Verify database acknowledgement before advancing watermarks."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from pipelines.collectors.kafka_producer import validate_run
from .state import atomic_json, state_db, database
from .planning import read_plan, directories
from .state import KST


def event_ids(directory):
    with (directory / "records.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            key = row["source"] + ":" + row["source_record_id"]
            yield uuid5(
                NAMESPACE_URL, row["run_id"] + ":" + key + ":" + row["payload_sha256"]
            )


def applied_plan(path):
    value = read_plan(path)
    expected = 0
    accepted = 0
    with database() as connection:
        for directory in directories(value):
            validate_run(directory)
            chunk = []
            for event in event_ids(directory):
                chunk.append(event)
                if len(chunk) == 1000:
                    expected += len(chunk)
                    accepted += connection.execute(
                        "SELECT count(*) FROM ingestion_events WHERE event_id=ANY(%s)",
                        (chunk,),
                    ).fetchone()[0]
                    chunk = []
            if chunk:
                expected += len(chunk)
                accepted += connection.execute(
                    "SELECT count(*) FROM ingestion_events WHERE event_id=ANY(%s)",
                    (chunk,),
                ).fetchone()[0]
    atomic_json(
        Path(path).parent / "db-status.json",
        {
            "expected": expected,
            "accepted": accepted,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return accepted == expected


def finish_plan(path):
    if not applied_plan(path):
        raise RuntimeError("DATABASE_NOT_CAUGHT_UP")
    value = read_plan(path)
    completed = datetime.now(timezone.utc).isoformat()
    if value["mode"] in {"incremental", "snapshot"}:
        watermark_day = value["end_day"]
        if value["mode"] == "snapshot":
            dates = [
                datetime.fromisoformat(
                    json.loads((d / "snapshot.json").read_text())["last_modified"]
                )
                .astimezone(KST)
                .date()
                for d in directories(value)
            ]
            watermark_day = (min(dates) - timedelta(days=1)).isoformat()
        with state_db() as connection:
            connection.execute(
                "INSERT INTO watermarks VALUES (?,?,?) ON CONFLICT(source) DO UPDATE SET day=max(watermarks.day,excluded.day),completed_at=excluded.completed_at WHERE excluded.day >= watermarks.day",
                (value["source"], watermark_day, completed),
            )
    report = {
        "source": value["source"],
        "mode": value["mode"],
        "completed_at": completed,
        "start_day": value["start_day"],
        "end_day": value["end_day"],
        "records": sum(
            json.loads((d / "report.json").read_text())["records"]
            for d in directories(value)
        ),
    }
    atomic_json(Path(path).parent / "completed.json", report)
    return report
