import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from pipelines.collectors import food_snapshot as snapshot
from pipelines.collectors.common import CollectionError
from pipelines.collectors.kafka_producer import validate_run


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.archive = self.directory / 'source.gz'
        self.info = {'last_modified':datetime.now(timezone.utc).isoformat()}
        self.run = str(uuid4())

    def write(self, rows):
        with gzip.open(self.archive,'wt',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)

    def test_snapshot_retains_unchanged_count_and_emits_changed_and_new(self):
        old={'PRDLST_REPORT_NO':'1','PRDLST_NM':'기존 식품','BSSH_NM':'업체','LAST_UPDT_DTM':'2026-10-14'}
        new={**old,'PRDLST_REPORT_NO':'2','PRDLST_NM':'새 식품'}
        self.write([old,new])
        with patch.object(snapshot,'existing_products',return_value={'1':snapshot.product_signature(old,'FOOD_I1250')}):
            report=snapshot.convert(self.archive,self.directory,'food-products',self.run,self.info,None)
        self.assertEqual((report['snapshot_records'],report['unchanged_records'],report['records']),(2,1,1))
        validate_run(self.directory)
        self.assertEqual(json.loads((self.directory/'records.jsonl').read_text())['source_record_id'],'2')

    def test_duplicate_or_empty_file_cannot_mark_complete(self):
        row={'RTRVLDSUSE_SEQ':'1','PRDTNM':'식품'}
        self.write([row,row])
        with self.assertRaisesRegex(CollectionError,'DUPLICATE'):
            snapshot.convert(self.archive,self.directory,'food-recalls',self.run,self.info,None)
        self.assertFalse((self.directory/'report.json').exists())
        self.write([row])
        with gzip.open(self.archive,'wt') as f:f.write('RTRVLDSUSE_SEQ,PRDTNM\n')
        with self.assertRaisesRegex(CollectionError,'EMPTY'):
            snapshot.convert(self.archive,self.directory,'food-recalls',self.run,self.info,None)

    def test_download_reuses_verified_archive_and_hides_secret_on_error(self):
        content=gzip.compress(b'RTRVLDSUSE_SEQ,PRDTNM\n1,food\n')
        calls=[]
        def respond(request):
            calls.append(1)
            return httpx.Response(200,content=content,headers={'last-modified':datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            snapshot.download(self.directory,'I0490','secret-key',client)
            snapshot.download(self.directory,'I0490','secret-key',client)
        self.assertEqual(len(calls),1)
        with tempfile.TemporaryDirectory() as d,httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(429))) as client:
            with self.assertRaisesRegex(CollectionError,'SNAPSHOT_HTTP_429') as error:
                snapshot.download(Path(d),'I0490','secret-key',client)
            self.assertNotIn('secret-key',str(error.exception))

    def test_only_exact_reviewed_source_error_can_be_excluded(self):
        import hashlib
        row={'PRDLST_REPORT_NO':'1','PRDLST_NM':'','BSSH_NM':'업체','LAST_UPDT_DTM':'2026-10-14'}
        self.write([row])
        digest=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        evidence={'FOOD_I1250:1':{'payload_sha256':digest,'reason':'MISSING_REQUIRED_FIELD','verified_at':self.info['last_modified']}}
        with patch.object(snapshot,'existing_products',return_value={}):
            with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED'):
                snapshot.convert(self.archive,self.directory,'food-products',self.run,self.info,None)
            report=snapshot.convert(self.archive,self.directory,'food-products',self.run,self.info,None,evidence)
            self.assertEqual(report['reviewed_source_rejections'],1)
            self.assertEqual(report['records'],0)
            self.assertEqual(len(json.loads((self.directory/'source-rejections.json').read_text())),1)
            self.write([{**row,'BSSH_NM':'변경 업체'}])
            with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED'):
                snapshot.convert(self.archive,self.directory,'food-products',self.run,self.info,None,evidence)
