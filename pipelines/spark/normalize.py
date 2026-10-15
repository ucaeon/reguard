import hashlib
import json
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from pipelines.spark.quality import QualityError, image, text, timestamp

SOURCES = {
    "FOOD_I1250": ("product", "PRDLST_REPORT_NO"),
    "FOOD_I0030": ("product", "PRDLST_REPORT_NO"),
    "FOOD_I0490": ("recall", "RTRVLDSUSE_SEQ"),
    "SAFETY_KC": ("product", "certUid"),
    "SAFETY_RECALL": ("recall", "recallUid"),
}


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def normalize(raw, key):
    try:
        env = json.loads(raw)
        if not isinstance(env, dict) or env.get("schema_version") != 1:
            raise QualityError("INVALID_ENVELOPE")
        source = env.get("source")
        if source not in SOURCES:
            raise QualityError("UNKNOWN_SOURCE")
        kind, id_field = SOURCES[source]
        payload = env.get("payload")
        if not isinstance(payload, dict):
            raise QualityError("INVALID_PAYLOAD")
        original_id = text(env.get("source_record_id"), True, 255)
        if text(payload.get(id_field), True, 255) != original_id:
            raise QualityError("SOURCE_ID_MISMATCH")
        if key != source + ":" + original_id:
            raise QualityError("MESSAGE_KEY_MISMATCH")
        payload_hash = hashlib.sha256(canonical(payload).encode()).hexdigest()
        if payload_hash != env.get("payload_sha256"):
            raise QualityError("PAYLOAD_HASH_MISMATCH")
        run = str(UUID(env["run_id"]))
        expected = str(uuid5(NAMESPACE_URL, run + ":" + key + ":" + payload_hash))
        if env.get("event_id") != expected:
            raise QualityError("EVENT_ID_MISMATCH")
        collected = timestamp(env.get("collected_at"), True, True)
        result = {
            "kind": kind,
            "source": source,
            "source_record_id": original_id,
            "id": str(uuid5(NAMESPACE_URL, "reguard:" + source + ":" + original_id)),
            "event_id": expected,
            "content_hash": hashlib.sha256(canonical(env).encode()).hexdigest(),
            "collected_at": collected,
            "version_at": collected,
        }
        if source in {"FOOD_I1250", "FOOD_I0030"}:
            result.update(
                name=text(payload.get("PRDLST_NM"), True, 500),
                company_name=text(payload.get("BSSH_NM"), maximum=500),
                category="FOOD" if source == "FOOD_I1250" else "HEALTH_SUPPLEMENT",
                model_name=None,
                image_url=None,
                source_updated_at=timestamp(payload.get("LAST_UPDT_DTM")),
                identifiers=[["FOOD_REPORT_NO", original_id]],
            )
            result["version_at"] = result["source_updated_at"] or collected
        elif source == "SAFETY_KC":
            images = payload.get("certificationImageUrls") or []
            if not isinstance(images, list):
                raise QualityError("INVALID_IMAGES")
            name = text(payload.get("productName"), True, 500)
            category = (
                "TOY"
                if "완구" in name
                else (
                    "ELECTRICAL"
                    if "전기" in (payload.get("certDiv") or "")
                    else "OTHER"
                )
            )
            cert = text(payload.get("certNum"), maximum=255)
            result.update(
                name=name,
                company_name=text(
                    payload.get("makerName") or payload.get("importerName"), maximum=500
                ),
                category=category,
                model_name=text(payload.get("modelName"), maximum=500),
                image_url=image(images[0]) if images else None,
                source_updated_at=timestamp(
                    payload.get("certChgDate") or payload.get("certDate")
                ),
                identifiers=(
                    [["KC_CERT_NO", cert]]
                    if cert and re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", cert)
                    else []
                ),
            )
            result["version_at"] = result["source_updated_at"] or collected
        elif source == "FOOD_I0490":
            conditions = {
                k: payload[k]
                for k in ["MNFDT", "DISTBTMLMT", "FRMLCUNIT"]
                if text(payload.get(k))
            }
            result.update(
                product_name=text(payload.get("PRDTNM"), True, 500),
                company_name=text(payload.get("BSSHNM"), maximum=500),
                reason=text(payload.get("RTRVLPRVNS")),
                action_method=text(payload.get("RTRVLPLANDOC_RTRVLMTHD")),
                target_conditions=(
                    json.dumps(conditions, ensure_ascii=False) if conditions else None
                ),
                source_created_at=timestamp(payload.get("CRET_DTM")),
                image_url=image(payload.get("IMG_FILE_PATH")),
                raw_payload=payload,
            )
        else:
            images = payload.get("recallFiles") or []
            if not isinstance(images, list) or any(
                not isinstance(v, dict) for v in images
            ):
                raise QualityError("INVALID_IMAGES")
            conditions = {
                k: payload[k]
                for k in [
                    "recallModelName",
                    "certNum",
                    "publishRecallVol",
                    "recallStaDate",
                    "recallEndDate",
                ]
                if text(payload.get(k))
            }
            result.update(
                product_name=text(payload.get("recallProductName"), True, 500),
                company_name=text(
                    payload.get("recallCmpnyName") or payload.get("makerName"),
                    maximum=500,
                ),
                reason=text(payload.get("harmDscr")),
                action_method=text(
                    payload.get("publishActionDscr") or payload.get("recallMeans")
                ),
                target_conditions=(
                    json.dumps(conditions, ensure_ascii=False) if conditions else None
                ),
                source_created_at=timestamp(payload.get("publishDate")),
                image_url=next(
                    (
                        image(v.get("imageUrl"))
                        for v in images
                        if image(v.get("imageUrl"))
                    ),
                    None,
                ),
                raw_payload=payload,
            )
        canonical(result)
        return canonical({"ok": True, "record": result})
    except QualityError as error:
        return canonical({"ok": False, "reason": str(error)})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return canonical({"ok": False, "reason": "MALFORMED_MESSAGE"})
