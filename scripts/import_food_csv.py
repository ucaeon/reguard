import argparse
import csv
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile
import time
import unicodedata
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

SPECS = {
    "일반식품검색.csv": ("FOOD_I1250", "FOOD"),
    "건강기능식품검색.csv": ("FOOD_I0030", "HEALTH_SUPPLEMENT"),
    "식품리콜알림.csv": ("FOOD_I0490", None),
}
MISSING = {"", "해당없음", "데이터없음", "-"}


def clean(value):
    value = value.strip()
    return None if value in MISSING else value


def required(row, key, maximum):
    value = clean(row[key])
    if value is None or len(value) > maximum or "\x00" in value:
        raise ValueError(f"invalid {key}")
    return value


def optional(row, key, maximum=None):
    value = clean(row.get(key, ""))
    if value and ((maximum and len(value) > maximum) or "\x00" in value):
        raise ValueError(f"invalid {key}")
    return value


def timestamp(value):
    value = clean(value)
    if value is None:
        return None
    dt = (
        datetime.strptime(value, "%Y%m%d")
        if len(value) == 8
        else datetime.fromisoformat(value)
    )
    return (
        dt.replace(tzinfo=ZoneInfo("Asia/Seoul")) if dt.tzinfo is None else dt
    ).isoformat()


def uid(*parts):
    return str(uuid5(NAMESPACE_URL, "reguard:" + ":".join(parts)))


def copy_line(values):
    def escape(value):
        if value is None:
            return "\\N"
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    return "\t".join(escape(v) for v in values) + "\n"


def representative_image(value):
    first = (value or "").split(",", 1)[0].strip()
    return first if re.fullmatch(r"https?://[^\s]+", first) else None


def map_row(row, source, category):
    if category:
        key = required(row, "PRDLST_REPORT_NO", 255)
        return [
            uid(source, key),
            source,
            key,
            required(row, "PRDLST_NM", 500),
            optional(row, "BSSH_NM", 500),
            category,
            timestamp(row["LAST_UPDT_DTM"]),
        ]
    key = required(row, "RTRVLDSUSE_SEQ", 255)
    conditions = {k: optional(row, k) for k in ("MNFDT", "DISTBTMLMT", "FRMLCUNIT")}
    conditions = {k: v for k, v in conditions.items() if v is not None}
    return [
        uid(source, key),
        source,
        key,
        required(row, "PRDTNM", 500),
        optional(row, "BSSHNM", 500),
        optional(row, "RTRVLPRVNS"),
        optional(row, "RTRVLPLANDOC_RTRVLMTHD"),
        json.dumps(conditions, ensure_ascii=False) if conditions else None,
        timestamp(row["CRET_DTM"]),
        representative_image(row.get("IMG_FILE_PATH")),
        json.dumps(row, ensure_ascii=False),
    ]


def load(path, source, category, args, run_dir):
    started = time.monotonic()
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    table = "products" if category else "recalls"
    key = "source_record_id" if category else "source_recall_id"
    cols = (
        ["id", "source", key, "name", "company_name", "category", "source_updated_at"]
        if category
        else [
            "id",
            "source",
            key,
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
    updates = cols[3:]
    changed = (
        "ROW("
        + ",".join("t." + c for c in updates)
        + ") IS DISTINCT FROM ROW("
        + ",".join("s." + c for c in updates)
        + ")"
    )
    seen = accepted = rejected = 0
    quarantine = run_dir / (source + "-rejected.jsonl")

    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as sql,
        path.open(encoding="utf-8-sig", newline="") as f,
        quarantine.open("w", encoding="utf-8") as bad,
    ):
        sql.write("BEGIN;\nSELECT pg_advisory_xact_lock(72648301);\n")
        sql.write(
            f"CREATE TEMP TABLE incoming (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP;\n"
        )
        sql.write(f"COPY incoming ({','.join(cols)}) FROM STDIN;\n")
        reader = csv.reader(f)
        headers = next(reader)
        required_headers = (
            {"PRDLST_REPORT_NO", "PRDLST_NM", "BSSH_NM", "LAST_UPDT_DTM"}
            if category
            else {
                "RTRVLDSUSE_SEQ",
                "PRDTNM",
                "BSSHNM",
                "CRET_DTM",
                "RTRVLPRVNS",
                "RTRVLPLANDOC_RTRVLMTHD",
                "MNFDT",
                "DISTBTMLMT",
                "FRMLCUNIT",
            }
        )
        if not required_headers.issubset(headers):
            raise ValueError(f"Missing CSV columns: {required_headers - set(headers)}")
        for line, values in enumerate(reader, 2):
            if args.limit and seen >= args.limit:
                break
            seen += 1
            try:
                if len(values) != len(headers):
                    raise ValueError("column count mismatch")
                row = {}
                for k, v in zip(headers, values):
                    if k in row and row[k] != v:
                        raise ValueError(f"conflicting duplicate column {k}")
                    row[k] = v
                mapped = map_row(row, source, category)
                sql.write(copy_line(mapped))
                accepted += 1
            except (ValueError, KeyError) as e:
                rejected += 1
                bad.write(
                    json.dumps(
                        {"line": line, "reason": str(e), "values": values},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        sql.write("\\.\n")

        sql.write(
            f"CREATE UNIQUE INDEX ON incoming (source,{key});\nANALYZE incoming;\n"
        )
        sql.write(
            f"SELECT json_build_object('new',count(*) FILTER (WHERE t.id IS NULL),'changed',count(*) FILTER (WHERE t.id IS NOT NULL AND {changed}),'unchanged',count(*) FILTER (WHERE t.id IS NOT NULL AND NOT ({changed}))) FROM incoming s LEFT JOIN {table} t ON t.source=s.source AND t.{key}=s.{key};\n"
        )
        assignments = ",".join(c + "=EXCLUDED." + c for c in updates)
        compare = changed.replace("s.", "EXCLUDED.")
        sql.write(
            f"INSERT INTO {table} AS t ({','.join(cols)}) SELECT {','.join(cols)} FROM incoming ON CONFLICT (source,{key}) DO UPDATE SET {assignments} WHERE {compare};\n"
        )
        if category:
            sql.write(
                "INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value) SELECT t.id,t.id,'FOOD_REPORT_NO',s.source_record_id FROM incoming s JOIN products t ON t.source=s.source AND t.source_record_id=s.source_record_id ON CONFLICT (product_id,identifier_type,identifier_value) DO NOTHING;\n"
            )
        sql.write("COMMIT;\n")
        sql.flush()
        sql.seek(0)
        if accepted == 0:
            raise ValueError(f"No accepted rows in {path}")
        command = [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "reguard_safety",
            "-d",
            "reguard_safety",
        ]
        result = subprocess.run(command, stdin=sql, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        counts = next(
            json.loads(line)
            for line in result.stdout.splitlines()
            if line.startswith("{")
        )
    report = {
        "file": str(path),
        "sha256": digest.hexdigest(),
        "source": source,
        "read": seen,
        "accepted": accepted,
        "rejected": rejected,
        **counts,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "quarantine": str(quarantine),
    }
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--limit", type=int, default=0, help="Rows per file; 0 means all"
    )
    parser.add_argument("--container", default="reguard-local-postgres-1")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("limit must be >= 0")
    files = {}
    for p in args.data_dir.rglob("*.csv"):
        name = unicodedata.normalize("NFC", p.name)
        if name in SPECS:
            if name in files:
                raise ValueError(f"Ambiguous filename: {name}")
            files[name] = p
    if set(files) != set(SPECS):
        raise ValueError(
            f"Expected three source CSV files; missing {set(SPECS) - set(files)}"
        )
    run_dir = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "import-reports"
        / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    run_dir.mkdir(parents=True)
    reports = []
    try:
        for name, (source, category) in SPECS.items():
            reports.append(load(files[name], source, category, args, run_dir))
    finally:
        (run_dir / "report.json").write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"Report: {run_dir / 'report.json'}")


if __name__ == "__main__":
    main()
