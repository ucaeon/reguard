"""Verify real PostgreSQL commit boundaries in disposable schemas.

The worker is SIGKILLed immediately before/after DB commit. Replaying the
same batch models an unadvanced Spark checkpoint; this does not kill Spark.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.spark.normalize import normalize
from pipelines.spark.sink import save_batch
from pipelines.spark.tests.test_normalize import envelope
from scripts.verify_incremental_matching import verify_changes, run_rule, SOURCES


def event(source, identity, payload, offset, day=1):
    key, raw = envelope(source, identity, payload, f'2026-10-{day:02}T00:00:00+00:00')
    return dict(topic='test', partition=0, offset=offset, raw=raw, normalized=normalize(raw,key))


def fixtures():
    return [event('FOOD_I1250','001',{'PRDLST_REPORT_NO':'001','PRDLST_NM':'test','BSSH_NM':'maker'},0),
            event('FOOD_I0490','r1',{'RTRVLDSUSE_SEQ':'r1','PRDTNM':'test','BSSHNM':'maker','PRDLST_REPORT_NO':'001'},1)]


def snapshot(db):
    with psycopg.connect(**db) as c:
        return {table: sorted(c.execute(f'SELECT row_to_json(t)::text FROM {table} t').fetchall())
                for table in ('products','recalls','product_identifiers','recall_product_matches',
                              'ingestion_events','ingestion_offsets','ingestion_source_state','ingestion_batches')}


def worker():
    request=json.loads(sys.stdin.read())
    original=psycopg.connect
    class Boundary:
        def __enter__(self):
            self.connection=original(**request['db'])
            return self.connection.__enter__()
        def __exit__(self, typ, value, tb):
            if typ is None and request['boundary']=='before_commit':
                os.kill(os.getpid(),signal.SIGKILL)
            result=self.connection.__exit__(typ,value,tb)
            if typ is None:
                os.kill(os.getpid(),signal.SIGKILL)
            return result
    psycopg.connect=lambda **kwargs: Boundary()
    save_batch(request['events'],0,'boundary',request['db'])


def main():
    db=dict(host=os.environ['DB_HOST'],port=os.environ['DB_PORT'],dbname='reguard_safety',
            user='reguard_safety',password=os.environ['SAFETY_DB_PASSWORD'])
    results=[]
    schema='boundary_'+uuid4().hex
    scoped={**db,'options':'-c search_path='+schema}
    with psycopg.connect(**db) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        for path in sorted((ROOT/'services/safety-service/src/main/resources/db/migration').glob('V*.sql')):
            c.execute(path.read_text())
    try:
        for boundary in ('before_commit','after_commit'):
            with psycopg.connect(**scoped) as c:
                c.execute('TRUNCATE products,recalls,ingestion_events,ingestion_offsets,ingestion_source_state,ingestion_batches CASCADE')
            events=fixtures()
            child=subprocess.run([sys.executable,__file__,'--worker'],input=json.dumps(
                dict(db=scoped,events=events,boundary=boundary)),text=True,capture_output=True,timeout=30)
            assert child.returncode == -signal.SIGKILL, child.stderr
            before=snapshot(scoped)
            expected=0 if boundary=='before_commit' else 1
            assert len(before['products'])==expected and len(before['recall_product_matches'])==expected
            assert len(before['ingestion_offsets'])==2*expected
            if boundary=='before_commit':
                assert all(not rows for rows in before.values())
            metrics=save_batch(events,0,'boundary',scoped)
            after=snapshot(scoped)
            assert len(after['products'])==1 and len(after['recall_product_matches'])==1
            if boundary=='after_commit':
                assert before==after
                assert metrics['duplicate']==2 and metrics['applied']==0
            else:
                assert metrics['applied']==2
            results.append(dict(scenario=boundary,status='passed',exit_signal='SIGKILL',replay=metrics))
        baseline=snapshot(scoped)
        row=json.loads(events[0]['raw'])
        unchanged=event(row['source'],row['source_record_id'],row['payload'],10,2)
        metrics=save_batch([unchanged],1,'boundary',scoped)
        current=snapshot(scoped)
        assert metrics['changed_products']==0 and metrics['unchanged']==1
        assert 'matching_rules' not in metrics
        for table in ('products','product_identifiers','recall_product_matches'):
            assert baseline[table]==current[table]
        results.append(dict(scenario='new_run_same_content',status='passed',metrics=metrics))
        payload={**row['payload'],'LAST_UPDT_DTM':'20261003'}
        metrics=save_batch([event(row['source'],row['source_record_id'],payload,11,3)],2,'boundary',scoped)
        assert metrics['changed_products']==0 and metrics['unchanged']==1
        assert snapshot(scoped)['recall_product_matches']==baseline['recall_product_matches']
        results.append(dict(scenario='source_timestamp_only',status='passed',metrics=metrics))
        payload={**payload,'PRDLST_NM':'changed'}
        metrics=save_batch([event(row['source'],row['source_record_id'],payload,12,4)],3,'boundary',scoped)
        assert metrics['changed_products']==1
        with psycopg.connect(**scoped) as c:
            full,_,_=run_rule(c,SOURCES)
            from scripts.verify_incremental_matching import result
            assert full==result(c)
        results.append(dict(scenario='product_content_changed',status='passed',metrics=metrics))
        replay=save_batch([{**events[0],'offset':19}],4,'boundary',scoped)
        assert replay['duplicate']==1 and replay['changed_products']==0
        results.append(dict(scenario='same_event_new_offset',status='passed',metrics=replay))
        # KC identifiers can change without any product column changing.
        payload={'certUid':'kc1','productName':'toy','modelName':'A','certNum':'CB001-1234'}
        recall_events=[event('SAFETY_RECALL',identity,{'recallUid':identity,'recallProductName':'toy',
                       'recallModelName':'A','certNum':cert},offset,5)
                       for identity,cert,offset in [('ka','CB001-1234',30),('kb','CB001-5678',31)]]
        save_batch(recall_events,5,'boundary',scoped)
        unaffected=snapshot(scoped)['recall_product_matches']
        for offset,cert in ((20,'CB001-1234'),(21,'CB001-5678'),(22,'')):
            metrics=save_batch([event('SAFETY_KC','kc1',{**payload,'certNum':cert},offset,offset-14)],offset,'boundary',scoped)
            assert metrics['changed_products']==1
            with psycopg.connect(**scoped) as c:
                from scripts.verify_incremental_matching import result
                assert run_rule(c,SOURCES)[0]==result(c)
                matches=c.execute("SELECT r.source_recall_id FROM recall_product_matches m JOIN recalls r ON r.id=m.recall_id WHERE r.source='SAFETY_RECALL'").fetchall()
                assert matches==({'CB001-1234':[('ka',)],'CB001-5678':[('kb',)],'':[]}[cert])
            assert all(row in snapshot(scoped)['recall_product_matches'] for row in unaffected)
            results.append(dict(scenario={20:'kc_insert',21:'identifier_only_change',22:'identifier_only_removal'}[offset],status='passed',metrics=metrics))
        # Scenario helper uses temporary tables cloned from public schema.
        # Run against this isolated schema instead by passing the schema name.
        with psycopg.connect(**scoped) as c:
            results.extend(verify_changes(c, schema))
            c.rollback()
        report=dict(status='passed',environment='disposable PostgreSQL schemas; synthetic fixtures',
                    boundary_method='SIGKILL around psycopg transaction exit; identical batch replay, not Spark process termination',
                    scenarios=results,
                    source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [ROOT/'pipelines/spark/sink.py',Path(__file__),ROOT/'scripts/verify_incremental_matching.py']})
        from datetime import datetime, timezone
        report['completed_at']=datetime.now(timezone.utc).isoformat()
        output=ROOT/'data/verification/matching-boundaries.json'
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(f'PASS {len(results)} scenarios; {output}')
    finally:
        with psycopg.connect(**db) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':
    worker() if '--worker' in sys.argv else main()
