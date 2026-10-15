import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from uuid import UUID, uuid4

from dotenv import dotenv_values
import httpx

from .common import ApiClient, CollectionError, record_id
from .providers import SOURCES, food_rows, safety_rows

ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def collect(args, client, key, api=None):
    source, service, id_field = SOURCES[args.source]
    run_id = (
        str(UUID(str(args.run_id))) if getattr(args, "run_id", None) else str(uuid4())
    )
    directory = (
        Path(getattr(args, "output_root", ROOT / "data" / "raw")) / args.source / run_id
    )
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "records.jsonl").exists():
        raise CollectionError("RUN_ALREADY_EXISTS")
    if (directory / "records.partial.jsonl").exists():
        (directory / "records.partial.jsonl").rename(
            directory / ("records.failed-" + str(uuid4()) + ".jsonl")
        )
    partial = directory / "records.partial.jsonl"
    report = {
        "run_id": run_id,
        "source": source,
        "started_at": utc_now(),
        "status": "running",
        "scope_complete": False,
        "records": 0,
        "max_records": args.max_records,
        "food_report_no": getattr(args, "food_report_no", None),
        "changed_since": str(getattr(args, "changed_since", None)),
        "date_field": getattr(args, "date_field", None),
        "kc_cert_no": getattr(args, "kc_cert_no", None),
        "start_date": args.start_date.isoformat() if args.start_date else None,
        "end_date": args.end_date.isoformat() if args.end_date else None,
    }
    api = api or ApiClient(client, args.max_requests, args.interval)
    started = time.monotonic()
    checksum = hashlib.sha256()
    try:
        if args.source.startswith("food-"):
            rows = food_rows(
                api,
                key,
                service,
                id_field,
                args.page_size,
                args.max_records,
                report,
                getattr(args, "food_report_no", None),
                getattr(args, "changed_since", None),
            )
        else:
            rows = safety_rows(
                api,
                key,
                service,
                id_field,
                args.start_date,
                args.end_date,
                args.max_records,
                report,
                getattr(args, "kc_cert_no", None),
                getattr(args, "date_field", None),
            )
        with partial.open("xb") as output:
            for row in rows:
                payload_hash = hashlib.sha256(
                    json.dumps(
                        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                envelope = {
                    "schema_version": 1,
                    "source": source,
                    "source_record_id": record_id(row, id_field),
                    "collected_at": utc_now(),
                    "run_id": run_id,
                    "payload_sha256": payload_hash,
                    "payload": row,
                }
                line = (json.dumps(envelope, ensure_ascii=False) + "\n").encode()
                output.write(line)
                checksum.update(line)
                report["records"] += 1
        partial.rename(directory / "records.jsonl")
        report["status"] = "complete" if report["scope_complete"] else "limited"
    except CollectionError as error:
        report["status"] = "failed"
        report["error_code"] = str(error)
    except (OSError, ValueError, TypeError, KeyError):
        report["status"] = "failed"
        report["error_code"] = "LOCAL_OR_RESPONSE_ERROR"
    except KeyboardInterrupt:
        report["status"] = "failed"
        report["error_code"] = "INTERRUPTED"
    finally:
        report.update(
            {
                "finished_at": utc_now(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "requests": api.requests,
                "retries": api.retries,
                "transport_errors": getattr(api, "transport_errors", {}),
                "sha256": checksum.hexdigest(),
            }
        )
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    print(
        json.dumps(
            {
                "status": report["status"],
                "records": report["records"],
                "requests": api.requests,
                "report": str(directory / "report.json"),
                "error_code": report.get("error_code"),
            },
            ensure_ascii=False,
        )
    )
    if report["status"] == "failed":
        return 1
    if getattr(args, "publish_kafka", False):
        from .kafka_producer import publish_run

        return publish_run(directory, args.kafka_bootstrap)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Collect public API records into ignored local JSONL files."
    )
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("--publish-kafka", action="store_true")
    parser.add_argument("--food-report-no")
    parser.add_argument("--kc-cert-no")
    parser.add_argument("--changed-since", type=date.fromisoformat)
    parser.add_argument("--date-field", choices=["certDate", "signDate", "publishDate"])
    parser.add_argument("--max-records", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-requests", type=int, default=20)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()
    if args.changed_since and (
        not args.source.startswith("food-")
        or not 0 <= (date.today() - args.changed_since).days <= 6
    ):
        parser.error(
            "--changed-since requires food source and the last 7 calendar days"
        )
    if args.date_field and (
        args.source.startswith("food-")
        or args.source == "safety-recalls"
        and args.date_field != "publishDate"
        or args.source == "kc-products"
        and args.date_field == "publishDate"
    ):
        parser.error("Invalid date field for source")
    if args.food_report_no and (
        args.source not in {"food-products", "food-supplements"}
        or not args.food_report_no.isdigit()
        or len(args.food_report_no) > 255
    ):
        parser.error(
            "--food-report-no requires food-products or food-supplements and a numeric report number"
        )
    if args.kc_cert_no and (
        args.source != "kc-products"
        or args.start_date
        or args.end_date
        or len(args.kc_cert_no) > 255
    ):
        parser.error("--kc-cert-no requires kc-products without date filters")
    if (
        args.max_records < 0
        or not 1 <= args.page_size <= 1000
        or args.max_requests < 1
        or not 0.1 <= args.interval <= 3600
    ):
        parser.error("Invalid collection limits")
    if args.source.startswith("food-"):
        if args.start_date or args.end_date:
            parser.error(
                "Date filters are only supported for Safety Korea in this version"
            )
    elif not args.kc_cert_no and (
        not args.start_date
        or not args.end_date
        or not 0 <= (args.end_date - args.start_date).days <= 30
    ):
        parser.error("Safety Korea requires an inclusive date range of 1 to 31 days")
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    args.kafka_bootstrap = env.get("KAFKA_BOOTSTRAP_SERVERS") or "127.0.0.1:19092"
    key_name = (
        "FOOD_SAFETY_API_KEY"
        if args.source.startswith("food-")
        else "SAFETY_KOREA_API_KEY"
    )
    key = (env.get(key_name) or "").strip()
    if not key or key.lower() == "sample":
        parser.error(f"Configure a real {key_name} in .env")
    logging.getLogger("httpx").disabled = True
    logging.getLogger("httpcore").disabled = True
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            return collect(args, client, key)
    except OSError:
        print("Collection failed: LOCAL_IO_ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
