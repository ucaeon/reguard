import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import NAMESPACE_URL, uuid5

from dotenv import dotenv_values
import httpx
import ijson
import psycopg

from pipelines.spark.quality import text, timestamp, QualityError

ROOT = Path(__file__).resolve().parents[2]


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def download(folder, key):
    folder.mkdir(parents=True, exist_ok=True)
    for kind, endpoint in [
        ("cert", "cert/certificationList.json"),
        ("recall", "recall/recallList.json"),
    ]:
        path = folder / (kind + "-list.json")
        if path.exists():
            continue
        started = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256()
        size = 0
        with httpx.Client(timeout=httpx.Timeout(600, connect=15)) as client:
            with client.stream(
                "GET",
                "https://www.safetykorea.kr/openapi/api/" + endpoint,
                headers={"AuthKey": key},
                params={"conditionKey": "all", "conditionValue": "all"},
            ) as response:
                response.raise_for_status()
                with path.with_suffix(".partial").open("wb") as output:
                    for block in response.iter_bytes():
                        output.write(block)
                        digest.update(block)
                        size += len(block)
        path.with_suffix(".partial").replace(path)
        write_json(
            path.with_suffix(".download.json"),
            {
                "started_at": started,
                "sha256": digest.hexdigest(),
                "downloaded_bytes": size,
            },
        )


def normalize_product(row):
    identity = text(row.get("certUid"), True, 255)
    name = text(row.get("productName"), True, 500)
    missing_date = 0
    value = row.get("certChgDate") or row.get("certDate")
    if value in ("00000000", "0000-00-00"):
        value = None
        missing_date = 1
    changed = timestamp(value)
    cert = text(row.get("certNum"), maximum=255)
    import re

    if cert and not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", cert):
        cert = None
    category = (
        "TOY"
        if "완구" in name
        else "ELECTRICAL" if "전기" in (row.get("certDiv") or "") else "OTHER"
    )
    return (
        uuid5(NAMESPACE_URL, "reguard:SAFETY_KC:" + identity),
        identity,
        name,
        text(row.get("makerName") or row.get("importerName"), maximum=500),
        category,
        text(row.get("modelName"), maximum=500),
        changed,
        cert,
    ), missing_date


def load_products(folder, db):
    path = folder / "cert-list.json"
    meta = json.loads(path.with_suffix(".download.json").read_text())
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if digest != meta["sha256"]:
        raise RuntimeError("SNAPSHOT_HASH_MISMATCH")
    snapshot_at = (
        meta.get("started_at")
        or datetime.fromtimestamp(
            path.stat().st_mtime - meta.get("seconds", 600), timezone.utc
        ).isoformat()
    )
    with path.open("rb") as stream:
        code = next(ijson.items(stream, "resultCode"), None)
    if str(code) != "2000":
        raise RuntimeError("SNAPSHOT_PROVIDER_ERROR")
    report = {
        "status": "staging",
        "snapshot_at": snapshot_at,
        "raw": 0,
        "accepted": 0,
        "rejected": 0,
        "unknown_date": 0,
        "processed": 0,
        "sha256": digest,
    }
    with psycopg.connect(**db) as connection:
        connection.execute(
            "CREATE TEMP TABLE kc_stage (id uuid, source_id text, name text, company text, category text, model text, changed timestamptz, cert text)"
        )
        with (
            path.open("rb") as stream,
            (folder / "rejected.jsonl").open("w") as rejected,
        ):
            with connection.cursor().copy("COPY kc_stage FROM STDIN") as copy:
                for row in ijson.items(stream, "resultData.item"):
                    report["raw"] += 1
                    try:
                        record, missing = normalize_product(row)
                        copy.write_row(record)
                        report["accepted"] += 1
                        report["unknown_date"] += missing
                    except (QualityError, TypeError, ValueError) as error:
                        report["rejected"] += 1
                        rejected.write(
                            json.dumps(
                                {"certUid": row.get("certUid"), "reason": str(error)},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
        if not report["raw"] or report["rejected"] > max(10, report["raw"] // 100):
            raise RuntimeError("SNAPSHOT_QUALITY_FAILED")
        duplicates = connection.execute(
            "SELECT count(*)-count(DISTINCT source_id) FROM kc_stage"
        ).fetchone()[0]
        if duplicates:
            raise RuntimeError("DUPLICATE_SOURCE_ID")
        existing = connection.execute(
            "SELECT count(*) FROM products WHERE source='SAFETY_KC'"
        ).fetchone()[0]
        if existing > 10000 and report["raw"] < existing * 0.9:
            raise RuntimeError("SNAPSHOT_UNEXPECTED_SHRINK")
        connection.execute("CREATE UNIQUE INDEX ON kc_stage(source_id)")
        connection.execute("SET statement_timeout='120s'")
        connection.commit()
        cursor = ""
        report_path = folder / "products-report.json"
        if report_path.exists():
            previous = json.loads(report_path.read_text())
            if previous.get("sha256") == digest and previous.get("last_source_id"):
                cursor = previous["last_source_id"]
                report["processed"] = previous["processed"]
        while True:
            with connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(72648301)")
                connection.execute(
                    "CREATE TEMP TABLE kc_chunk ON COMMIT DROP AS SELECT * FROM kc_stage WHERE source_id>%s ORDER BY source_id LIMIT 10000",
                    (cursor,),
                )
                connection.execute("CREATE INDEX ON kc_chunk(source_id)")
                connection.execute("ANALYZE kc_chunk")
                count, end = connection.execute(
                    "SELECT count(*),max(source_id) FROM kc_chunk"
                ).fetchone()
                if not count:
                    break
                connection.execute(
                    """DELETE FROM kc_chunk c USING ingestion_source_state s
                    WHERE s.source='SAFETY_KC' AND s.source_record_id=c.source_id AND s.collected_at>%s""",
                    (snapshot_at,),
                )
                connection.execute(
                    """INSERT INTO products AS p(id,source,source_record_id,name,company_name,category,model_name,source_updated_at)
                    SELECT id,'SAFETY_KC',source_id,name,company,category,model,changed FROM kc_chunk
                    ON CONFLICT(source,source_record_id) DO UPDATE SET
                    name=EXCLUDED.name,company_name=EXCLUDED.company_name,category=EXCLUDED.category,
                    model_name=EXCLUDED.model_name,source_updated_at=EXCLUDED.source_updated_at
                    WHERE ROW(p.name,p.company_name,p.category,p.model_name,p.source_updated_at)
                    IS DISTINCT FROM ROW(EXCLUDED.name,EXCLUDED.company_name,EXCLUDED.category,EXCLUDED.model_name,EXCLUDED.source_updated_at)"""
                )
                connection.execute(
                    """DELETE FROM product_identifiers i USING products p,kc_chunk c
                    WHERE p.source='SAFETY_KC' AND p.source_record_id=c.source_id AND i.product_id=p.id
                    AND i.identifier_type='KC_CERT_NO' AND i.identifier_value IS DISTINCT FROM c.cert"""
                )
                connection.execute(
                    """INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value)
                    SELECT gen_random_uuid(),p.id,'KC_CERT_NO',c.cert FROM kc_chunk c JOIN products p
                    ON p.source='SAFETY_KC' AND p.source_record_id=c.source_id WHERE c.cert IS NOT NULL
                    ON CONFLICT(product_id,identifier_type,identifier_value) DO NOTHING"""
                )
                connection.execute(
                    """INSERT INTO ingestion_source_state AS s(source,source_record_id,version_at,collected_at,event_id)
                    SELECT 'SAFETY_KC',source_id,coalesce(changed,'-infinity'::timestamptz),%s,%s FROM kc_chunk
                    ON CONFLICT(source,source_record_id) DO UPDATE SET version_at=EXCLUDED.version_at,
                    collected_at=EXCLUDED.collected_at,event_id=EXCLUDED.event_id""",
                    (snapshot_at, uuid5(NAMESPACE_URL, "kc-bootstrap:" + digest)),
                )
                report["processed"] += count
                cursor = end
                report["last_source_id"] = cursor
            write_json(folder / "products-report.json", report)
            print("processed", report["processed"], flush=True)
        report["catalog_count"] = connection.execute(
            "SELECT count(*) FROM products WHERE source='SAFETY_KC'"
        ).fetchone()[0]
        report["snapshot_missing_in_db"] = connection.execute(
            "SELECT count(*) FROM kc_stage c WHERE NOT EXISTS(SELECT 1 FROM products p WHERE p.source='SAFETY_KC' AND p.source_record_id=c.source_id)"
        ).fetchone()[0]
        report["status"] = (
            "complete" if report["snapshot_missing_in_db"] == 0 else "failed"
        )
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        write_json(folder / "products-report.json", report)
        return report


def load_recalls(folder, db):
    from pipelines.spark.normalize import normalize, canonical
    from pipelines.spark.sink import upsert

    path = folder / "recall-list.json"
    meta = json.loads(path.with_suffix(".download.json").read_text())
    digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if digest != meta["sha256"]:
        raise RuntimeError("SNAPSHOT_HASH_MISMATCH")
    collected = (
        meta.get("started_at")
        or datetime.fromtimestamp(
            path.stat().st_mtime - meta.get("seconds", 600), timezone.utc
        ).isoformat()
    )
    with path.open("rb") as stream:
        if str(next(ijson.items(stream, "resultCode"), None)) != "2000":
            raise RuntimeError("SNAPSHOT_PROVIDER_ERROR")
    run = str(uuid5(NAMESPACE_URL, "recall-bootstrap:" + digest))
    report = {
        "status": "running",
        "raw": 0,
        "applied": 0,
        "skipped_newer": 0,
        "rejected": 0,
    }
    seen = set()
    with (
        psycopg.connect(**db) as connection,
        path.open("rb") as stream,
        (folder / "recall-rejected.jsonl").open("w") as rejected,
    ):
        with connection.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='120s'")
            cur.execute("SELECT pg_advisory_xact_lock(72648301)")
            for row in ijson.items(stream, "resultData.item"):
                report["raw"] += 1
                identity = str(row.get("recallUid", ""))
                if not identity or identity in seen:
                    raise RuntimeError("INVALID_OR_DUPLICATE_RECALL_ID")
                seen.add(identity)
                cur.execute(
                    "SELECT collected_at FROM ingestion_source_state WHERE source='SAFETY_RECALL' AND source_record_id=%s",
                    (identity,),
                )
                current = cur.fetchone()
                if current and current[0] > datetime.fromisoformat(collected):
                    report["skipped_newer"] += 1
                    continue
                cur.execute(
                    "SELECT raw_payload FROM recalls WHERE source='SAFETY_RECALL' AND source_recall_id=%s",
                    (identity,),
                )
                current = cur.fetchone()
                payload = dict(current[0]) if current else {}
                payload.update({k: v for k, v in row.items() if v is not None})
                key = "SAFETY_RECALL:" + identity
                payload_hash = hashlib.sha256(canonical(payload).encode()).hexdigest()
                event = str(uuid5(NAMESPACE_URL, run + ":" + key + ":" + payload_hash))
                envelope = {
                    "schema_version": 1,
                    "source": "SAFETY_RECALL",
                    "source_record_id": identity,
                    "run_id": run,
                    "collected_at": collected,
                    "payload": payload,
                    "payload_sha256": payload_hash,
                    "event_id": event,
                }
                normalized = json.loads(normalize(canonical(envelope), key))
                if not normalized["ok"]:
                    report["rejected"] += 1
                    rejected.write(
                        json.dumps({"id": identity, "reason": normalized["reason"]})
                        + "\n"
                    )
                    continue
                upsert(cur, normalized["record"])
                cur.execute(
                    """INSERT INTO ingestion_source_state VALUES ('SAFETY_RECALL',%s,%s,%s,%s)
                    ON CONFLICT(source,source_record_id) DO UPDATE SET version_at=EXCLUDED.version_at,
                    collected_at=EXCLUDED.collected_at,event_id=EXCLUDED.event_id""",
                    (identity, collected, collected, event),
                )
                report["applied"] += 1
            if report["rejected"] > max(10, report["raw"] // 100):
                raise RuntimeError("RECALL_SNAPSHOT_QUALITY_FAILED")
            cur.execute("CREATE TEMP TABLE matching_scope ON COMMIT DROP AS SELECT id AS recall_id FROM recalls;")
            cur.execute((ROOT / "pipelines/spark/kc_matching.sql").read_text())
            cur.execute("SELECT count(*) FROM recalls WHERE source='SAFETY_RECALL'")
            report["database_count"] = cur.fetchone()[0]
        report["status"] = "complete"
    write_json(folder / "recalls-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["download", "load-products", "load-recalls"])
    parser.add_argument("--directory", type=Path, default=ROOT / "data/kc-bootstrap")
    args = parser.parse_args()
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    if args.action == "download":
        download(args.directory, env["SAFETY_KOREA_API_KEY"])
    else:
        loader = load_products if args.action == "load-products" else load_recalls
        result = loader(
            args.directory,
            dict(
                host=env.get("DB_HOST", "127.0.0.1"),
                port=env.get("DB_PORT", "15432"),
                dbname="reguard_safety",
                user="reguard_safety",
                password=env["SAFETY_DB_PASSWORD"],
            ),
        )
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
