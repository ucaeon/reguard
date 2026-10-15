from datetime import timedelta

from .common import CollectionError, record_id, records
from .food import food_rows

SOURCES = {
    "food-recalls": ("FOOD_I0490", "I0490", "RTRVLDSUSE_SEQ"),
    "food-products": ("FOOD_I1250", "I1250", "PRDLST_REPORT_NO"),
    "food-supplements": ("FOOD_I0030", "I0030", "PRDLST_REPORT_NO"),
    "kc-products": ("SAFETY_KC", "cert", "certUid"),
    "safety-recalls": ("SAFETY_RECALL", "recall", "recallUid"),
}



def safety_rows(
    api,
    key,
    kind,
    id_field,
    start_date,
    end_date,
    max_records,
    state,
    cert_no=None,
    date_field=None,
):
    base = "https://www.safetykorea.kr/openapi/api/"
    headers = {"AuthKey": key}
    is_cert = kind == "cert"
    listing = "cert/certificationList.json" if is_cert else "recall/recallList.json"
    detail = "cert/certificationDetail.json" if is_cert else "recall/recallDetail.json"
    date_field = date_field or ("certDate" if is_cert else "publishDate")
    if date_field not in ({"certDate", "signDate"} if is_cert else {"publishDate"}):
        raise CollectionError("INVALID_DATE_FIELD")
    detail_key = "certNum" if is_cert else "recallUid"
    day = start_date
    seen = set()

    def fetch(path, params):
        payload = api.get(base + path, headers=headers, params=params)
        code = str(payload.get("resultCode"))
        if code == "2004":
            return None
        if code != "2000":
            raise CollectionError(
                "SAFETY_" + code
                if code in {"4000", "4001", "4005", "5000"}
                else "PROVIDER_ERROR"
            )
        if payload.get("resultData") is None:
            raise CollectionError("INVALID_RESPONSE_SHAPE")
        return payload["resultData"]

    if cert_no:
        if not is_cert or start_date or end_date:
            raise CollectionError("INVALID_CERT_NUMBER_FILTER")
        item = fetch(detail, {"certNum": cert_no})
        if item is not None:
            if not isinstance(item, dict) or item.get("certNum") != cert_no:
                raise CollectionError("INVALID_DETAIL_RESPONSE")
            record_id(item, id_field)
            yield item
        state["scope_complete"] = True
        return

    while day <= end_date:
        date = day.strftime("%Y%m%d")
        value = fetch(listing, {"conditionKey": date_field, "conditionValue": date})
        rows = [] if value is None else records(value)
        if len(rows) >= 1000:
            raise CollectionError("SAFETY_DAILY_LIMIT_REACHED")
        for row in rows:
            if max_records and len(seen) >= max_records:
                return
            if row.get(date_field) != date:
                raise CollectionError("UNEXPECTED_DATE_FILTER_RESULT")
            identity = record_id(row, id_field)
            if identity in seen:
                raise CollectionError("DUPLICATE_SOURCE_ID")
            item = fetch(detail, {detail_key: record_id(row, detail_key)})
            if not isinstance(item, dict) or record_id(item, id_field) != identity:
                raise CollectionError("INVALID_DETAIL_RESPONSE")
            seen.add(identity)
            yield item
        state["last_completed_date"] = day.isoformat()
        day += timedelta(days=1)
        if max_records and len(seen) >= max_records and day <= end_date:
            return
    state["scope_complete"] = True
