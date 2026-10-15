"""Independent image-URL enrichment, with PostgreSQL-backed history and retries.

No image bytes, manifests, or checkpoints are written to the filesystem.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time

import httpx
from psycopg.types.json import Jsonb

from pipelines.collectors.recall_images import discover_images, fingerprint, official_image_url

LOCK_ID = 72648309
MAX_ATTEMPTS = 5


def utcnow():
    return datetime.now(timezone.utc)


@contextmanager
def worker_lock(connection):
    acquired = connection.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0]
    connection.commit()
    try:
        yield acquired
    finally:
        connection.rollback()
        if acquired:
            connection.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
            connection.commit()


def synchronize(connection):
    """Discover new/changed recalls, including those loaded by weekly snapshots."""
    rows = connection.execute('''SELECT r.id,r.raw_payload,r.image_url,j.input_hash
        FROM recalls r LEFT JOIN recall_image_jobs j ON j.recall_id=r.id
        WHERE r.source='SAFETY_RECALL' ''').fetchall()
    count = 0
    for recall_id, payload, image_url, previous_hash in rows:
        digest = fingerprint(payload)
        if previous_hash == digest:
            continue
        images = []
        # Adopt already verified legacy URLs once; never reuse a previous product's photo.
        if previous_hash is None and official_image_url(image_url):
            for item in payload.get('recallFiles') or []:
                url = official_image_url(item.get('imageUrl')) if isinstance(item, dict) else None
                if url:
                    images.append({'imageUrl': url, 'sourceUrl':
                        f"https://www.safetykorea.kr/recall/ajax/recallBoard?recallUid={payload.get('recallUid', '')}"})
            if not images:
                images = [{'imageUrl': official_image_url(image_url), 'sourceUrl':
                    f"https://www.safetykorea.kr/recall/ajax/recallBoard?recallUid={payload.get('recallUid', '')}"}]
        connection.execute('''INSERT INTO recall_image_jobs
            (recall_id,input_hash,status,next_attempt_at,images,checked_at)
            VALUES (%s,%s,%s,CASE WHEN %s THEN NULL ELSE now() END,%s,%s)
            ON CONFLICT(recall_id) DO UPDATE SET input_hash=EXCLUDED.input_hash,
            status=EXCLUDED.status,attempts=0,next_attempt_at=EXCLUDED.next_attempt_at,
            images=EXCLUDED.images,checked_at=NULL,last_error=NULL,updated_at=now()''',
            (recall_id,digest,'success' if images else 'pending',bool(images),
             Jsonb(images),utcnow() if images else None))
        if previous_hash is not None:
            connection.execute('UPDATE recalls SET image_url=NULL WHERE id=%s', (recall_id,))
        if images:
            connection.execute('''INSERT INTO recall_image_attempts
                (recall_id,input_hash,attempt_number,finished_at,outcome)
                VALUES (%s,%s,0,now(),'imported')''', (recall_id,digest))
        count += 1
    connection.commit()
    return count


def next_attempt(status, attempt, now):
    if status == 'retry':
        return None if attempt >= MAX_ATTEMPTS else now + timedelta(hours=2 ** (attempt - 1))
    if status in ('not_found', 'identity_unconfirmed'):
        return now + timedelta(days=30)
    return None


def process_due(connection, client, limit=100, interval=0.5, sleep=time.sleep):
    rows = connection.execute('''SELECT j.recall_id,j.input_hash,j.attempts,r.raw_payload
        FROM recall_image_jobs j JOIN recalls r ON r.id=j.recall_id
        WHERE j.status IN ('pending','retry','not_found','identity_unconfirmed')
          AND j.next_attempt_at <= now()
        ORDER BY j.next_attempt_at,r.source_created_at DESC NULLS LAST,j.recall_id LIMIT %s''',
        (limit,)).fetchall()
    connection.commit()
    counts = Counter()
    for recall_id, digest, attempts, payload in rows:
        # A worker crash leaves a started attempt in the DB; recover it when its lease expires.
        connection.execute('''UPDATE recall_image_attempts SET outcome='interrupted',
            finished_at=now(),error_code='WORKER_INTERRUPTED'
            WHERE recall_id=%s AND finished_at IS NULL''', (recall_id,))
        if attempts >= MAX_ATTEMPTS:
            connection.execute("UPDATE recall_image_jobs SET status='failed',next_attempt_at=NULL,last_error='RETRY_LIMIT' WHERE recall_id=%s", (recall_id,))
            connection.commit()
            counts['failed'] += 1
            continue
        attempt = attempts + 1
        connection.execute('''UPDATE recall_image_jobs SET status='retry',attempts=%s,
            next_attempt_at=now()+interval '1 hour',updated_at=now() WHERE recall_id=%s''',
            (attempt,recall_id))
        attempt_id = connection.execute('''INSERT INTO recall_image_attempts
            (recall_id,input_hash,attempt_number,outcome) VALUES (%s,%s,%s,'started') RETURNING id''',
            (recall_id,digest,attempt)).fetchone()[0]
        connection.commit()
        result = discover_images(payload, client)
        status, images, error = result['status'], result['images'], result['error']
        due = next_attempt(status, attempt, utcnow())
        if status == 'retry' and attempt >= MAX_ATTEMPTS:
            status = 'failed'
        # Do not attach results if ingestion changed the product during the HTTP request.
        current = connection.execute('SELECT raw_payload FROM recalls WHERE id=%s FOR UPDATE',
                                     (recall_id,)).fetchone()
        if current is None:
            connection.rollback()
            counts['deleted'] += 1
            continue
        if fingerprint(current[0]) != digest:
            connection.execute("UPDATE recall_image_attempts SET finished_at=now(),outcome='superseded' WHERE id=%s", (attempt_id,))
            connection.execute("UPDATE recall_image_jobs SET status='pending',next_attempt_at=now() WHERE recall_id=%s", (recall_id,))
            connection.commit()
            counts['superseded'] += 1
            continue
        connection.execute('''UPDATE recall_image_jobs SET status=%s,images=%s,
            attempts=%s,next_attempt_at=%s,checked_at=now(),last_error=%s,updated_at=now()
            WHERE recall_id=%s''',
            (status,Jsonb(images),0 if status in ('not_found','identity_unconfirmed') else attempt,
             due,error,recall_id))
        connection.execute('''UPDATE recall_image_attempts SET finished_at=now(),outcome=%s,
            error_code=%s WHERE id=%s''', (status,error,attempt_id))
        if status == 'success':
            connection.execute('''UPDATE recalls SET image_url=%s,source_url=COALESCE(source_url,%s)
                WHERE id=%s''', (images[0]['imageUrl'],images[0]['sourceUrl'],recall_id))
        connection.commit()
        counts[status] += 1
        sleep(interval)
    return dict(counts)


def run(connection, client=None, limit=100, interval=0.5, sync_only=False):
    if not 1 <= limit <= 500:
        raise ValueError('limit must be between 1 and 500')
    with worker_lock(connection) as acquired:
        if not acquired:
            return {'status': 'already_running'}
        queued = synchronize(connection)
        if sync_only:
            return {'status': 'synchronized', 'changed': queued}
        if client is not None:
            counts = process_due(connection, client, limit, interval)
        else:
            with httpx.Client() as http:
                counts = process_due(connection, http, limit, interval)
        return {'status': 'complete', 'changed': queued, 'results': counts}
