"""Collect and publish immutable planned runs."""

import argparse
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from uuid import uuid4
import httpx
from pipelines.collectors.collect import collect
from pipelines.collectors.common import CollectionError
from pipelines.collectors.kafka_producer import publish_run, validate_run
from pipelines.collectors.providers import SOURCES
from .state import root, atomic_json, lock, database
from .providers import reserve_snapshot_request, BudgetClient, CachedApi
from .planning import read_plan, directories
from .state import KST


def collect_plan(path):
    value = read_plan(path)
    source = value["source"]
    key_name = (
        "FOOD_SAFETY_API_KEY" if source.startswith("food-") else "SAFETY_KOREA_API_KEY"
    )
    logging.getLogger("httpx").disabled = True
    logging.getLogger("httpcore").disabled = True
    key = os.environ.get(key_name, "").strip()
    if not key:
        raise CollectionError("MISSING_PROVIDER_KEY")
    if value["mode"] == "snapshot":
        from pipelines.collectors.food_snapshot import download, convert

        for part, directory in zip(value["parts"], directories(value)):
            with lock(part["run_id"]):
                directory.mkdir(parents=True, exist_ok=True)
                if (directory / "report.json").exists():
                    validate_run(directory)
                    continue
                with httpx.Client(timeout=120, follow_redirects=False) as client:
                    archive, info = download(
                        directory,
                        SOURCES[source][1],
                        key,
                        client,
                        reserve_snapshot_request,
                    )
                with database() as connection:
                    exclusions_path = (
                        Path(os.environ.get("REGUARD_STATE_ROOT", str(root())))
                        / "food-source-exclusions.json"
                    )
                    exclusions = (
                        json.loads(exclusions_path.read_text())
                        if exclusions_path.exists()
                        else {}
                    )
                    convert(
                        archive,
                        directory,
                        source,
                        part["run_id"],
                        info,
                        connection,
                        exclusions,
                    )
        return path
    incremental = source.startswith("food-") and value["mode"] != "reconcile"
    changed = date.fromisoformat(value["start_day"]) if incremental else None
    if changed and (datetime.now(KST).date() - changed).days > 6:
        raise CollectionError("FOOD_GAP_REQUIRES_SNAPSHOT_RECOVERY")
    for part, directory in zip(value["parts"], directories(value)):
        with lock(part["run_id"]):
            if (directory / "report.json").exists():
                report = json.loads((directory / "report.json").read_text())
                if report["status"] == "complete":
                    validate_run(directory)
                    continue
                if report["status"] == "failed":
                    atomic_json(directory / ("report.failed-" + str(uuid4()) + ".json"), report)
                if report["status"] == "limited":
                    raise CollectionError("INCOMPLETE_COLLECTION")
            if (directory / "records.jsonl").exists():
                (directory / "records.jsonl").rename(
                    directory / ("records.uncommitted-" + str(uuid4()) + ".jsonl")
                )
            day = date.fromisoformat(part["day"]) if part["day"] else None
            args = argparse.Namespace(
                source=source,
                run_id=part["run_id"],
                output_root=root() / "raw",
                max_records=0,
                page_size=1000,
                max_requests=3000,
                interval=1.0,
                start_date=day,
                end_date=day,
                changed_since=changed,
                date_field="signDate" if source == "kc-products" else None,
            )
            fallback = directory / "incremental-failure.json"
            if fallback.exists():
                args.changed_since = None
            with BudgetClient(source, bool(args.changed_since)) as client:
                api = CachedApi(client, root() / "cache" / part["run_id"])
                result = collect(args, client, key, api=api)
            report = json.loads((directory / "report.json").read_text())
            if (
                result
                and source == "food-recalls"
                and args.changed_since
                and report.get("error_code")
                in {
                    "TOTAL_CHANGED_DURING_COLLECTION",
                    "UNEXPECTED_PAGE_SIZE",
                    "DUPLICATE_SOURCE_ID",
                    "UNEXPECTED_EMPTY_PAGE",
                }
            ):
                atomic_json(fallback, report)
                args.changed_since = None
                with BudgetClient(source, False) as client:
                    api = CachedApi(client, root() / "cache" / part["run_id"])
                    result = collect(args, client, key, api=api)
                report = json.loads((directory / "report.json").read_text())
            if fallback.exists():
                report["fallback"] = "FULL_RECALL_RECONCILIATION"
                atomic_json(directory / "report.json", report)
            if result or report["status"] != "complete":
                code = report.get("error_code", "INCOMPLETE_COLLECTION")
                if code in {
                    "TOTAL_CHANGED_DURING_COLLECTION",
                    "UNEXPECTED_PAGE_SIZE",
                    "DUPLICATE_SOURCE_ID",
                    "UNEXPECTED_EMPTY_PAGE",
                }:
                    cache = root() / "cache" / part["run_id"]
                    if cache.exists():
                        cache.rename(
                            cache.with_name(
                                cache.name + "-inconsistent-" + str(uuid4())
                            )
                        )
                raise CollectionError(code)
    return path


def publish_plan(path):
    value = read_plan(path)
    for directory in directories(value):
        with lock(str(directory)):
            report = json.loads((directory / "report.json").read_text())
            if report["status"] != "complete":
                raise CollectionError("INCOMPLETE_COLLECTION")
            validate_run(directory)
            done = directory / "published.json"
            if done.exists():
                continue
            if publish_run(
                directory, os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
            ):
                raise RuntimeError("KAFKA_PUBLISH_FAILED")
            atomic_json(done, {"completed_at": datetime.now(timezone.utc).isoformat()})
    return path
