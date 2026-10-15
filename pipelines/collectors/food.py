import re
from urllib.parse import quote

from .common import CollectionError, record_id, records

FOOD_API_BASE = "https://openapi.foodsafetykorea.go.kr/api"


def food_url(key, service, start, end, report_no=None, changed_since=None):
    url = f"{FOOD_API_BASE}/{quote(key, safe='')}/{service}/json/{start}/{end}"
    filters = []
    if changed_since:
        filters.append("CHNG_DT=" + changed_since.strftime("%Y%m%d"))
    if report_no:
        if (
            service not in {"I1250", "I0030"}
            or not report_no.isdigit()
            or len(report_no) > 255
        ):
            raise CollectionError("INVALID_REPORT_NUMBER_FILTER")
        filters.append("PRDLST_REPORT_NO=" + quote(report_no, safe=""))
    return url + ("/" + "&".join(filters) if filters else "")


def verify_supplement_boundary(api, key, service, body, rows, size, report_no, changed_since):
    # A cached response cannot establish that the provider's result is stable.
    fresh = getattr(api, "get_fresh", api.get)
    repeated = fresh(food_url(key, service, 1, size, report_no, changed_since))
    terminal = fresh(food_url(
        key, service, len(rows) + 1, len(rows) + size, report_no, changed_since
    ))
    repeated = repeated.get(service) if isinstance(repeated, dict) else None
    terminal = terminal.get(service) if isinstance(terminal, dict) else None
    if not isinstance(terminal, dict) or not isinstance(terminal.get("RESULT"), dict):
        raise CollectionError("INCONSISTENT_SUPPLEMENT_BOUNDARY")
    if (
        repeated != body
        or terminal["RESULT"].get("CODE") != "INFO-200"
        or terminal.get("row")
    ):
        raise CollectionError("INCONSISTENT_SUPPLEMENT_BOUNDARY")
    return {
        "method": "identical_full_response_and_empty_successor",
        "declared_total": int(body["total_count"]),
        "verified_total": len(rows),
    }


def food_rows(
    api,
    key,
    service,
    id_field,
    page_size,
    max_records,
    state,
    report_no=None,
    changed_since=None,
):
    start = 1
    total = None
    seen = set()
    while True:
        size = min(page_size, max_records - len(seen)) if max_records else page_size
        end = start + size - 1
        url = food_url(key, service, start, end, report_no, changed_since)
        payload = api.get(url)
        body = payload.get(service, payload)
        if not isinstance(body, dict) or not isinstance(body.get("RESULT"), dict):
            raise CollectionError("INVALID_RESPONSE_SHAPE")
        code = body["RESULT"].get("CODE")
        if code == "INFO-200":
            if total is not None and start <= total:
                raise CollectionError("UNEXPECTED_EMPTY_PAGE")
            state["scope_complete"] = True
            return
        if code != "INFO-000":
            safe = isinstance(code, str) and re.fullmatch(
                r"(?:INFO|ERROR)-[0-9]{3}", code
            )
            raise CollectionError(code if safe else "PROVIDER_ERROR")
        count = body.get("total_count")
        if isinstance(count, bool) or not str(count).isdigit():
            raise CollectionError("INVALID_TOTAL_COUNT")
        current_total = int(count)
        if total is not None and current_total != total:
            raise CollectionError("TOTAL_CHANGED_DURING_COLLECTION")
        total = current_total
        state["provider_total"] = total
        rows = records(body.get("row", []))
        if len(rows) != min(size, max(0, total - start + 1)):
            if not (
                service == "I0030"
                and changed_since
                and not max_records
                and start == 1
                and 0 <= total < len(rows) < size
            ):
                raise CollectionError("UNEXPECTED_PAGE_SIZE")
            state["count_verification"] = verify_supplement_boundary(
                api, key, service, body, rows, size, report_no, changed_since
            )
            total = len(rows)
        for row in rows:
            identity = record_id(row, id_field)
            if report_no and identity != report_no:
                raise CollectionError("UNEXPECTED_REPORT_NUMBER_FILTER_RESULT")
            if identity in seen:
                raise CollectionError("DUPLICATE_SOURCE_ID")
            seen.add(identity)
            yield row
        if end >= total:
            state["scope_complete"] = True
            return
        if max_records and len(seen) >= max_records:
            return
        start = end + 1

