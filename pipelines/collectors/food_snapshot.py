"""Official gzip/CSV recovery, retaining source evidence and publishing only changes."""
import csv
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
from itertools import islice
from pathlib import Path
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import httpx
from .common import CollectionError, record_id
from .providers import SOURCES
from pipelines.spark.quality import text, timestamp, QualityError


def download(directory, service, key, client, reserve=None):
    archive = directory / 'snapshot.csv.gz'
    metadata = directory / 'snapshot.json'
    if archive.exists() and metadata.exists():
        info = json.loads(metadata.read_text())
        with archive.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != info['sha256']:
            raise CollectionError('SNAPSHOT_CHECKSUM_MISMATCH')
        return archive, info
    if reserve:
        reserve(service)
    temporary = archive.with_suffix('.partial')
    try:
        with client.stream('GET', 'https://openapi.foodsafetykorea.go.kr/api/' + quote(key, safe='') + '/' + service + '/file') as response:
            if response.status_code != 200:
                raise CollectionError('SNAPSHOT_HTTP_' + str(response.status_code))
            modified = parsedate_to_datetime(response.headers.get('last-modified', ''))
            now = datetime.now(timezone.utc)
            if modified > now + timedelta(minutes=5) or now - modified > timedelta(days=3):
                raise CollectionError('SNAPSHOT_NOT_RECENT')
            digest = hashlib.sha256()
            size = 0
            with temporary.open('wb') as output:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000_000:
                        raise CollectionError('SNAPSHOT_TOO_LARGE')
                    output.write(chunk)
                    digest.update(chunk)
            if response.headers.get('content-length') and size != int(response.headers['content-length']):
                raise CollectionError('SNAPSHOT_TRUNCATED')
            with temporary.open('rb') as stream:
                magic = stream.read(2)
            if magic != b'\x1f\x8b':
                raise CollectionError('SNAPSHOT_NOT_GZIP')
            temporary.replace(archive)
            info = {'service':service, 'last_modified':modified.isoformat(), 'downloaded_at':now.isoformat(), 'bytes':size, 'sha256':digest.hexdigest()}
            metadata.write_text(json.dumps(info, indent=2))
            return archive, info
    except httpx.HTTPError:
        # Never expose a URL containing the provider key in task logs.
        raise CollectionError('SNAPSHOT_NETWORK_ERROR') from None
    except (ValueError, TypeError):
        raise CollectionError('SNAPSHOT_INVALID_METADATA') from None


def product_signature(row, source):
    updated = timestamp(row.get('LAST_UPDT_DTM'))
    return (text(row.get('PRDLST_NM'), True, 500), text(row.get('BSSH_NM'), maximum=500),
            'FOOD' if source == 'FOOD_I1250' else 'HEALTH_SUPPLEMENT',
            datetime.fromisoformat(updated) if updated else None)


def existing_products(connection, source, ids):
    rows = connection.execute('''SELECT p.source_record_id,p.name,p.company_name,p.category,p.source_updated_at
        FROM products p WHERE p.source=%s AND p.source_record_id=ANY(%s)
        AND p.model_name IS NULL AND p.image_url IS NULL
        AND EXISTS (SELECT 1 FROM product_identifiers i WHERE i.product_id=p.id
            AND i.identifier_type='FOOD_REPORT_NO' AND i.identifier_value=p.source_record_id)''', (source, ids)).fetchall()
    return {row[0]:tuple(row[1:]) for row in rows}


def convert(archive, directory, source_name, run_id, info, connection, exclusions=None):
    source, _, id_field = SOURCES[source_name]
    partial = directory / 'snapshot-records.partial'
    checksum = hashlib.sha256()
    seen = set()
    changed = unchanged = 0
    rejected = []
    exclusions = exclusions or {}
    # Snapshot time, not conversion time, prevents an older file replacing a newer recall.
    collected = info['last_modified']
    with gzip.open(archive, 'rt', encoding='utf-8-sig', newline='') as stream, partial.open('wb') as output:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or id_field not in reader.fieldnames:
            raise CollectionError('SNAPSHOT_INVALID_COLUMNS')
        while batch := list(islice(reader, 1000)):
            ids = [record_id(row, id_field) for row in batch]
            existing = existing_products(connection, source, ids) if source != 'FOOD_I0490' else {}
            for row, identity in zip(batch, ids):
                if None in row or any(v is None for v in row.values()):
                    raise CollectionError('SNAPSHOT_INVALID_ROW')
                if identity in seen:
                    raise CollectionError('DUPLICATE_SOURCE_ID')
                seen.add(identity)
                if source != 'FOOD_I0490':
                    try:
                        signature = product_signature(row, source)
                    except QualityError as error:
                        digest = hashlib.sha256(json.dumps(row, ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                        evidence = exclusions.get(source + ':' + identity, {})
                        if evidence.get('payload_sha256') != digest or evidence.get('reason') != str(error) or not evidence.get('verified_at'):
                            raise
                        rejected.append({'source':source, 'source_record_id':identity, 'payload':row, 'reason':str(error), 'evidence':evidence})
                        continue
                if source != 'FOOD_I0490' and existing.get(identity) == signature:
                    unchanged += 1
                    continue
                payload_hash = hashlib.sha256(json.dumps(row, ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                envelope = dict(schema_version=1,source=source,source_record_id=identity,collected_at=collected,run_id=run_id,payload_sha256=payload_hash,payload=row)
                line = (json.dumps(envelope, ensure_ascii=False)+'\n').encode()
                output.write(line); checksum.update(line); changed += 1
    if not seen:
        raise CollectionError('SNAPSHOT_EMPTY')
    partial.replace(directory / 'records.jsonl')
    report = dict(status='complete',scope_complete=True,source=source,run_id=run_id,records=changed,sha256=checksum.hexdigest(),snapshot_records=len(seen),unchanged_records=unchanged,reviewed_source_rejections=len(rejected),snapshot=info,finished_at=datetime.now(timezone.utc).isoformat())
    (directory/'source-rejections.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2))
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report
