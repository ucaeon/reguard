"""Opt-in PostgreSQL integration tests; each run uses and drops an isolated schema."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from pipelines.images import worker
from pipelines.spark.sink import upsert

ROOT = Path(__file__).resolve().parents[3]
PHOTO = 'https://office.safetykorea.kr/fileData/test.png'
SUCCESS = {'status': 'success', 'images': [{'imageUrl': PHOTO, 'sourceUrl': 'https://www.safetykorea.kr/recall/ajax/recallBoard?recallUid=123'}], 'error': None}


class RetryPolicyTest(unittest.TestCase):
    def test_backoff_limit_and_monthly_missing(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(worker.next_attempt('retry', 1, now), now + timedelta(hours=1))
        self.assertEqual(worker.next_attempt('retry', 4, now), now + timedelta(hours=8))
        self.assertIsNone(worker.next_attempt('retry', 5, now))
        self.assertEqual(worker.next_attempt('not_found', 2, now), now + timedelta(days=30))


@unittest.skipUnless(os.environ.get('REGUARD_TEST_DB') == '1', 'set REGUARD_TEST_DB=1 for isolated PostgreSQL tests')
class WorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = {**dotenv_values(ROOT / '.env'), **os.environ}
        cls.db = dict(host=cfg.get('DB_HOST','127.0.0.1'), port=cfg.get('DB_PORT','15432'),
                      dbname='reguard_safety', user='reguard_safety', password=cfg['SAFETY_DB_PASSWORD'])
        cls.conn = psycopg.connect(**cls.db)
        cls.schema = 'image_test_' + uuid4().hex
        cls.lock_patch = patch.object(worker, 'LOCK_ID', int(uuid4().hex[:15], 16))
        cls.lock_patch.start()
        cls.addClassCleanup(cls.lock_patch.stop)
        cls.conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        cls.conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(cls.schema)))
        for path in sorted((ROOT / 'services/safety-service/src/main/resources/db/migration').glob('V*.sql')):
            cls.conn.execute(path.read_text())
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        cls.conn.commit()
        cls.conn.close()

    def setUp(self):
        self.conn.rollback()
        self.conn.execute('TRUNCATE recalls CASCADE')
        self.id = uuid4()
        self.payload = dict(recallUid='123', certNum='CB123', recallModelName='허니', recallCmpnyName='리틀아이')
        self.conn.execute('''INSERT INTO recalls(id,source,source_recall_id,product_name,raw_payload)
            VALUES (%s,'SAFETY_RECALL','123','완구',%s)''', (self.id,Jsonb(self.payload)))
        self.conn.commit()

    def run_worker(self):
        return worker.run(self.conn, client=object(), interval=0)

    def due_now(self):
        self.conn.execute("UPDATE recall_image_jobs SET next_attempt_at=now()-interval '1 second'")
        self.conn.commit()

    def test_success_is_not_requested_twice_and_url_survives_upsert(self):
        with patch.object(worker,'discover_images',return_value=SUCCESS) as discover:
            self.run_worker()
            self.run_worker()
            self.assertEqual(discover.call_count,1)
            row = dict(kind='recall',id=self.id,source='SAFETY_RECALL',source_record_id='123',
                       product_name='완구',company_name=None,reason='updated',action_method=None,
                       target_conditions=None,source_created_at=None,image_url=None,raw_payload=self.payload)
            upsert(self.conn.cursor(),row)
            self.conn.commit()
            self.run_worker()
            self.assertEqual(discover.call_count,1)
        self.assertEqual(self.conn.execute('SELECT image_url FROM recalls').fetchone()[0],PHOTO)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM recall_image_attempts').fetchone()[0],1)

    def test_retry_waits_then_stops_after_limit(self):
        with patch.object(worker,'discover_images',return_value={'status':'retry','images':[],'error':'HTTP_503'}) as discover:
            self.run_worker()
            self.run_worker()
            self.assertEqual(discover.call_count,1)
            for _ in range(4):
                self.due_now()
                self.run_worker()
            self.run_worker()
            self.assertEqual(discover.call_count,5)
        self.assertEqual(self.conn.execute('SELECT status,next_attempt_at FROM recall_image_jobs').fetchone(),('failed',None))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM recall_image_attempts').fetchone()[0],5)

    def test_legacy_urls_are_adopted_without_network(self):
        self.conn.execute('UPDATE recalls SET image_url=%s WHERE id=%s',(PHOTO,self.id))
        self.conn.commit()
        with patch.object(worker,'discover_images',side_effect=AssertionError('duplicate request')):
            self.run_worker()
        self.assertEqual(self.conn.execute('SELECT status FROM recall_image_jobs').fetchone()[0],'success')

    def test_changed_identity_invalidates_old_photo(self):
        with patch.object(worker,'discover_images',return_value=SUCCESS):
            self.run_worker()
        self.payload['recallModelName']='다른 제품'
        self.conn.execute('UPDATE recalls SET raw_payload=%s',(Jsonb(self.payload),))
        self.conn.commit()
        worker.run(self.conn,sync_only=True)
        self.assertIsNone(self.conn.execute('SELECT image_url FROM recalls').fetchone()[0])
        self.assertEqual(self.conn.execute('SELECT status,attempts FROM recall_image_jobs').fetchone(),('pending',0))

    def test_no_photo_does_not_repeat_until_due(self):
        with patch.object(worker,'discover_images',return_value={'status':'not_found','images':[],'error':None}) as discover:
            self.run_worker()
            self.run_worker()
            self.assertEqual(discover.call_count,1)
        self.assertGreater(self.conn.execute('SELECT next_attempt_at FROM recall_image_jobs').fetchone()[0],worker.utcnow()+timedelta(days=29))

    def test_concurrent_worker_skips(self):
        with psycopg.connect(**self.db) as other:
            other.execute('SELECT pg_advisory_lock(%s)',(worker.LOCK_ID,))
            try:
                self.assertEqual(self.run_worker()['status'],'already_running')
            finally:
                other.execute('SELECT pg_advisory_unlock(%s)',(worker.LOCK_ID,))

    def test_interrupted_attempt_recovers(self):
        worker.run(self.conn,sync_only=True)
        self.conn.execute("UPDATE recall_image_jobs SET attempts=1,status='retry'")
        self.conn.execute("INSERT INTO recall_image_attempts(recall_id,input_hash,attempt_number,outcome) SELECT recall_id,input_hash,1,'started' FROM recall_image_jobs")
        self.conn.commit()
        with patch.object(worker,'discover_images',return_value=SUCCESS):
            self.run_worker()
        outcomes=[r[0] for r in self.conn.execute('SELECT outcome FROM recall_image_attempts ORDER BY id')]
        self.assertEqual(outcomes,['interrupted','success'])

    def test_new_job_is_immediately_due_despite_host_clock_skew(self):
        # Docker and the host may disagree after sleep; queue readiness uses DB time.
        with patch.object(worker, 'utcnow', return_value=datetime.now(timezone.utc) + timedelta(minutes=5)):
            with patch.object(worker, 'discover_images', return_value=SUCCESS) as discover:
                self.run_worker()
                self.assertEqual(discover.call_count, 1)
        self.assertEqual(self.conn.execute('SELECT status FROM recall_image_jobs').fetchone()[0], 'success')

    def test_product_changed_during_request_does_not_get_stale_image(self):
        def discover(*args):
            with psycopg.connect(**self.db) as other:
                other.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
                other.execute('UPDATE recalls SET raw_payload=%s',(Jsonb({**self.payload,'certNum':'DIFFERENT'}),))
            return SUCCESS
        with patch.object(worker,'discover_images',side_effect=discover):
            self.run_worker()
        self.assertIsNone(self.conn.execute('SELECT image_url FROM recalls').fetchone()[0])
        self.assertEqual(self.conn.execute('SELECT outcome FROM recall_image_attempts').fetchone()[0],'superseded')
