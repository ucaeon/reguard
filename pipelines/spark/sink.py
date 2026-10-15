import json
import time
from uuid import NAMESPACE_URL, uuid5

import psycopg
from psycopg.types.json import Jsonb

from .matching import match_sources


def upsert(cur, row):
    product = row["kind"] == "product"
    table = "products" if product else "recalls"
    key = "source_record_id" if product else "source_recall_id"
    fields = (
        [
            "name",
            "company_name",
            "category",
            "model_name",
            "image_url",
            "source_updated_at",
        ]
        if product
        else [
            "product_name",
            "company_name",
            "reason",
            "action_method",
            "target_conditions",
            "source_created_at",
            "image_url",
            "raw_payload",
        ]
    )
    if product and row["source"] in {"FOOD_I1250", "FOOD_I0030"}:
        fields.remove("image_url")
    content_fields = [f for f in fields if f != "source_updated_at"]
    previous = None
    if product:
        cur.execute(
            f"SELECT {','.join(content_fields)} FROM products WHERE source=%s AND {key}=%s",
            (row["source"], row["source_record_id"]),
        )
        previous = cur.fetchone()
    values = [row["id"], row["source"], row["source_record_id"]] + [
        Jsonb(row[f]) if f == "raw_payload" else row[f] for f in fields
    ]
    columns = ["id", "source", key] + fields
    # Safety Korea photos are owned by the independent image worker.
    # A source refresh without images must not erase a verified URL.
    update_fields = [f for f in fields if not (
        not product and row["source"] == "SAFETY_RECALL" and f == "image_url"
    )]
    assignments = ",".join(f"{f}=EXCLUDED.{f}" for f in update_fields)
    comparisons = ",".join("t." + f for f in update_fields)
    incoming = ",".join("EXCLUDED." + f for f in update_fields)
    cur.execute(
        f"INSERT INTO {table} AS t ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) ON CONFLICT(source,{key}) DO UPDATE SET {assignments} WHERE ROW({comparisons}) IS DISTINCT FROM ROW({incoming}) RETURNING id",
        values,
    )
    stored_change = cur.fetchone() is not None
    content_changed = stored_change
    if product:
        content_changed = previous is None or tuple(previous) != tuple(row[f] for f in content_fields)
        cur.execute(
            "SELECT id FROM products WHERE source=%s AND source_record_id=%s",
            (row["source"], row["source_record_id"]),
        )
        product_id = cur.fetchone()[0]
        kind = "KC_CERT_NO" if row["source"] == "SAFETY_KC" else "FOOD_REPORT_NO"
        cur.execute(
            "SELECT identifier_type,identifier_value FROM product_identifiers WHERE product_id=%s AND identifier_type=%s",
            (product_id, kind),
        )
        identifiers = {tuple(value) for value in row["identifiers"]}
        identifiers_changed = set(cur.fetchall()) != identifiers
        if not identifiers_changed:
            return content_changed
        cur.execute(
            "DELETE FROM product_identifiers WHERE product_id=%s AND identifier_type=%s",
            (product_id, kind),
        )
        for identifier_type, value in row["identifiers"]:
            identity = uuid5(
                NAMESPACE_URL,
                f"reguard:identifier:{product_id}:{identifier_type}:{value}",
            )
            cur.execute(
                "INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (identity, product_id, identifier_type, value),
            )

        content_changed = content_changed or identifiers_changed
    return content_changed


def save_batch(rows, batch_id, query_id, db, match_food=True):
    changed_sources = set()
    changed_products = set()
    changed_recalls = set()
    started = time.monotonic()
    metrics = {"input": 0, "applied": 0, "duplicate": 0, "stale": 0, "quarantined": 0, "unchanged": 0}
    with psycopg.connect(**db) as connection:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(72648301)")
            for item in rows:
                metrics["input"] += 1
                location = (item["topic"], item["partition"], item["offset"])
                cur.execute(
                    "INSERT INTO ingestion_offsets VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING offset_id",
                    location,
                )
                if cur.fetchone() is None:
                    metrics["duplicate"] += 1
                    continue
                result = json.loads(item["normalized"])
                if not result["ok"]:
                    cur.execute(
                        "INSERT INTO ingestion_quarantine(topic,partition_id,offset_id,raw_message,reason) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (
                            *location,
                            (item["raw"] or "").replace("\x00", "\\u0000"),
                            result["reason"],
                        ),
                    )
                    metrics["quarantined"] += 1
                    continue
                row = result["record"]
                cur.execute(
                    "INSERT INTO ingestion_events(event_id,content_hash) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING event_id",
                    (row["event_id"], row["content_hash"]),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        "SELECT content_hash FROM ingestion_events WHERE event_id=%s",
                        (row["event_id"],),
                    )
                    if cur.fetchone()[0] != row["content_hash"]:
                        cur.execute(
                            "INSERT INTO ingestion_quarantine(topic,partition_id,offset_id,raw_message,reason) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (*location, (item["raw"] or "").replace("\x00", "\\u0000"), "EVENT_ID_CONTENT_CONFLICT"),
                        )
                        metrics["quarantined"] += 1
                        continue
                    metrics["duplicate"] += 1
                    continue
                cur.execute(
                    """INSERT INTO ingestion_source_state AS s(source,source_record_id,version_at,collected_at,event_id)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(source,source_record_id) DO UPDATE
                    SET version_at=EXCLUDED.version_at,collected_at=EXCLUDED.collected_at,event_id=EXCLUDED.event_id
                    WHERE ROW(EXCLUDED.version_at,EXCLUDED.collected_at,EXCLUDED.event_id)>ROW(s.version_at,s.collected_at,s.event_id)
                    RETURNING source""",
                    (
                        row["source"],
                        row["source_record_id"],
                        row["version_at"],
                        row["collected_at"],
                        row["event_id"],
                    ),
                )
                if cur.fetchone() is None:
                    metrics["stale"] += 1
                    continue
                if row["kind"] == "product" and row["source_updated_at"]:
                    cur.execute(
                        "SELECT 1 FROM products WHERE source=%s AND source_record_id=%s AND source_updated_at>%s",
                        (
                            row["source"],
                            row["source_record_id"],
                            row["source_updated_at"],
                        ),
                    )
                    if cur.fetchone():
                        metrics["stale"] += 1
                        continue
                content_changed = upsert(cur, row)
                metrics["applied"] += 1
                if not content_changed:
                    metrics["unchanged"] += 1
                    continue
                if row["kind"] == "product":
                    cur.execute("SELECT id FROM products WHERE source=%s AND source_record_id=%s",
                                (row["source"], row["source_record_id"]))
                    changed_products.add(cur.fetchone()[0])
                else:
                    cur.execute("SELECT id FROM recalls WHERE source=%s AND source_recall_id=%s",
                                (row["source"], row["source_record_id"]))
                    changed_recalls.add(cur.fetchone()[0])
                changed_sources.add(row["source"])
            metrics["changed_products"] = len(changed_products)
            metrics["changed_recalls"] = len(changed_recalls)
            if changed_sources and match_food:
                metrics["matching_rules"] = match_sources(
                    cur, changed_sources, changed_products, changed_recalls
                )
            metrics["elapsed_seconds"] = round(time.monotonic() - started, 3)
            cur.execute(
                "INSERT INTO ingestion_batches(query_id,batch_id,metrics) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (query_id, batch_id, Jsonb(metrics)),
            )
    print(json.dumps({"batch_id": batch_id, **metrics}), flush=True)
    return metrics
