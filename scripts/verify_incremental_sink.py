"""Exercise ingestion and incremental matching in a disposable PostgreSQL schema."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from dotenv import dotenv_values
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.spark.normalize import normalize
from pipelines.spark.sink import save_batch
from pipelines.spark.tests.test_normalize import envelope


def main():
    env = {**dotenv_values(ROOT / '.env'), **os.environ}
    db = dict(host=env.get('DB_HOST','127.0.0.1'),port=env.get('DB_PORT','15432'),
              dbname='reguard_safety',user='reguard_safety',password=env['SAFETY_DB_PASSWORD'])
    schema = 'incremental_test_' + uuid4().hex
    with psycopg.connect(**db) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        for path in sorted((ROOT/'services/safety-service/src/main/resources/db/migration').glob('V*.sql')):
            c.execute(path.read_text())
    scoped = {**db,'options':'-c search_path='+schema}
    try:
        fixtures = [
            ('FOOD_I1250','001',{'PRDLST_REPORT_NO':'001','PRDLST_NM':'test','BSSH_NM':'maker'}),
            ('FOOD_I0490','r1',{'RTRVLDSUSE_SEQ':'r1','PRDTNM':'test','BSSH_NM':'maker','PRDLST_REPORT_NO':'001','RTRVLPRVNS':'test'}),
        ]
        events=[]
        for offset, fixture in enumerate(fixtures):
            key,raw=envelope(*fixture)
            events.append(dict(topic='test',partition=0,offset=offset,raw=raw,normalized=normalize(raw,key)))
        metrics=save_batch(events,0,'test',scoped)
        assert metrics['applied']==2,metrics
        with psycopg.connect(**scoped) as c:
            assert c.execute('SELECT count(*) FROM recall_product_matches').fetchone()[0]==1
        replay=save_batch(events,1,'test',scoped)
        assert replay['duplicate']==2 and replay['applied']==0,replay
        def interrupted():
            yield {**events[0],'offset':99}
            raise RuntimeError('simulated failure')
        try:
            save_batch(interrupted(),2,'test',scoped)
        except RuntimeError:
            pass
        else:
            raise AssertionError('expected rollback')
        with psycopg.connect(**scoped) as c:
            assert c.execute('SELECT count(*) FROM ingestion_offsets WHERE offset_id=99').fetchone()[0]==0
        print('PASS: actual sink matches new records, ignores replay and rolls back interrupted batch')
    finally:
        with psycopg.connect(**db) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':
    main()
