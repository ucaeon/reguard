"""Kill the complete Spark container at DB commit boundaries and resume its checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker():
    import psycopg
    from pyspark.sql import SparkSession
    from pipelines.spark.streaming_job import run
    config=json.loads(Path('/evidence/config.json').read_text())
    boundary=os.environ.get('CRASH_BOUNDARY')
    if boundary:
        original=psycopg.connect
        class Connection:
            def __enter__(self):
                self.connection=original(**config['db'])
                return self.connection.__enter__()
            def __exit__(self, typ, value, tb):
                if typ is None and boundary=='before_commit':
                    pause()
                result=self.connection.__exit__(typ,value,tb)
                if typ is None and boundary=='after_commit':
                    pause()
                return result
        def pause():
            Path('/evidence/boundary.json').write_text(json.dumps({'boundary':boundary,'pid':os.getpid()}))
            while True:
                time.sleep(1)
        psycopg.connect=lambda **kwargs: Connection()
    spark=(SparkSession.builder.master('local[2]').appName('reguard-crash-recovery')
           .config('spark.jars',','.join(str(p) for p in Path('/opt/kafka-jars').glob('*.jar')))
           .config('spark.sql.shuffle.partitions','2').config('spark.driver.memory','512m').getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    try:
        run(spark,'kafka:9092',config['topic'],Path('/evidence/checkpoint'),config['db'],True).awaitTermination()
    finally:
        spark.stop()


def command(*args, **kwargs):
    return subprocess.run(args,check=True,text=True,capture_output=True,**kwargs).stdout.strip()


def wait_for(check, seconds=90):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            value=check()
            if value:
                return value
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError('verification deadline exceeded')


def main():
    import psycopg
    from confluent_kafka import Producer
    from confluent_kafka.admin import AdminClient, NewTopic
    from pipelines.spark.tests.test_normalize import envelope
    stamp=uuid4().hex[:10]
    prefix='reguard-crash-'+stamp
    output=ROOT/'data/verification'/prefix
    output.mkdir(parents=True)
    network=prefix
    dbname=prefix+'-db'; kafka=prefix+'-kafka'
    image='reguard-spark:portable-20261015.2'
    containers=[]
    report={'status':'running','scenarios':[], 'method':'real Spark JVM/Python container SIGKILL; original checkpoint restart; isolated Kafka/PostgreSQL',
            'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [ROOT/'pipelines/spark/sink.py',ROOT/'pipelines/spark/streaming_job.py',Path(__file__)]}}
    try:
        command('docker','network','create',network)
        containers.append(dbname)
        command('docker','run','-d','--name',dbname,'--network',network,'--network-alias','postgres',
                '-e','POSTGRES_USER=reguard_safety','-e','POSTGRES_PASSWORD=isolated-test-only',
                '-e','POSTGRES_DB=reguard_safety','-p','127.0.0.1::5432','postgres:16')
        port=command('docker','port',dbname,'5432').split(':')[-1]
        db=dict(host='127.0.0.1',port=port,dbname='reguard_safety',user='reguard_safety',password='isolated-test-only')
        def ready():
            with psycopg.connect(**db) as c:
                return c.execute('SELECT 1').fetchone()
        wait_for(ready)
        containers.append(kafka)
        # Port only serves this short-lived verification; Docker fails if occupied.
        kafka_port='29093'
        args=['docker','run','-d','--name',kafka,'--network',network,'--network-alias','kafka','-p',f'127.0.0.1:{kafka_port}:19092']
        env={'KAFKA_NODE_ID':'1','KAFKA_PROCESS_ROLES':'broker,controller',
             'KAFKA_LISTENERS':'INTERNAL://:9092,EXTERNAL://:19092,CONTROLLER://:9093',
             'KAFKA_ADVERTISED_LISTENERS':f'INTERNAL://kafka:9092,EXTERNAL://127.0.0.1:{kafka_port}',
             'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP':'INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT',
             'KAFKA_INTER_BROKER_LISTENER_NAME':'INTERNAL','KAFKA_CONTROLLER_LISTENER_NAMES':'CONTROLLER',
             'KAFKA_CONTROLLER_QUORUM_VOTERS':'1@kafka:9093','KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR':'1',
             'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR':'1','KAFKA_TRANSACTION_STATE_LOG_MIN_ISR':'1',
             'KAFKA_AUTO_CREATE_TOPICS_ENABLE':'false','KAFKA_HEAP_OPTS':'-Xmx384m -Xms128m'}
        for k,v in env.items():args+=['-e',k+'='+v]
        command(*args,'apache/kafka:3.9.1')
        admin=AdminClient({'bootstrap.servers':'127.0.0.1:'+kafka_port})
        wait_for(lambda:admin.list_topics(timeout=2).brokers)
        for boundary in ('before_commit','after_commit'):
            from psycopg import sql
            schema='test_'+boundary
            with psycopg.connect(**db) as c:
                c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                for p in sorted((ROOT/'services/safety-service/src/main/resources/db/migration').glob('V*.sql')):
                    c.execute(p.read_text())
            scoped={**db,'options':'-c search_path='+schema}
            def count(table):
                with psycopg.connect(**scoped) as c:
                    return c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
            folder=output/boundary; folder.mkdir()
            topic='test-'+boundary
            admin.create_topics([NewTopic(topic,3,1)])[topic].result(20)
            producer=Producer({'bootstrap.servers':'127.0.0.1:'+kafka_port,'acks':'all'})
            products=[envelope('FOOD_I1250',str(i),{'PRDLST_REPORT_NO':str(i),'PRDLST_NM':f'product-{i}'}) for i in range(36)]
            recall=envelope('FOOD_I0490','r1',{'RTRVLDSUSE_SEQ':'r1','PRDTNM':'product-0','PRDLST_REPORT_NO':'0'})
            published=[]
            def publish(events):
                errors=[]
                for key,raw in events:
                    partition=len(published)%3
                    producer.produce(topic,key=key,value=raw,partition=partition,
                                     on_delivery=lambda error,msg: errors.append(str(error)) if error else None)
                    published.append((partition,key,raw))
                assert producer.flush(20)==0 and not errors,errors
            publish(products[:24]+[recall])
            (folder/'config.json').write_text(json.dumps({'db':{**scoped,'host':'postgres','port':'5432'},'topic':topic}))
            def start(name, fault=None):
                containers.append(name)
                args=['docker','run','-d','--name',name,'--network',network,'--memory','1536m',
                      '-v',str(ROOT)+':/opt/reguard:ro','-v',str(folder)+':/evidence','--entrypoint','python']
                if fault: args+=['-e','CRASH_BOUNDARY='+fault]
                command(*args,image,'scripts/verify_spark_crash_recovery.py','--worker')
            name=prefix+'-'+boundary
            start(name,boundary)
            wait_for(lambda:(folder/'boundary.json').exists(),180)
            checkpoint=folder/'checkpoint'
            assert (checkpoint/'offsets/0').exists()
            assert not (checkpoint/'commits/0').exists()
            identity=(checkpoint/'reguard-query.json').read_text()
            metadata=(checkpoint/'metadata').read_text()
            before={t:count(t) for t in ('products','recalls','ingestion_events','ingestion_offsets','recall_product_matches')}
            assert before['products']==(0 if boundary=='before_commit' else 24),before
            command('docker','kill','--signal','KILL',name)
            command('docker','wait',name)
            assert command('docker','inspect','-f','{{.State.ExitCode}}',name)=='137'
            (folder/'killed.log').write_text(command('docker','logs',name))
            publish(products[24:]+products[:3])
            resumed=name+'-resumed'
            start(resumed)
            wait_for(lambda:command('docker','inspect','-f','{{.State.Running}}',resumed)=='false',180)
            logs=subprocess.run(['docker','logs',resumed],text=True,capture_output=True)
            (folder/'resumed.log').write_text(logs.stdout+logs.stderr)
            assert command('docker','inspect','-f','{{.State.ExitCode}}',resumed)=='0',str(folder/'resumed.log')
            assert (checkpoint/'reguard-query.json').read_text()==identity
            assert (checkpoint/'metadata').read_text()==metadata
            assert (checkpoint/'commits/0').exists()
            with psycopg.connect(**scoped) as c:
                actual=set(c.execute('SELECT source_record_id,name FROM products').fetchall())
                assert actual=={(str(i),f'product-{i}') for i in range(36)}
                expected_events={json.loads(raw)['event_id'] for _,_,raw in published}
                assert {str(r[0]) for r in c.execute('SELECT event_id FROM ingestion_events')}==expected_events
                expected_offsets=set(); positions={0:0,1:0,2:0}
                for partition,_,_ in published:
                    expected_offsets.add((topic,partition,positions[partition]));positions[partition]+=1
                assert set(c.execute('SELECT topic,partition_id,offset_id FROM ingestion_offsets'))==expected_offsets
                assert count('recall_product_matches')==1 and count('ingestion_quarantine')==0
            # A further restart with no input must not change persisted state.
            final={t:count(t) for t in ('products','recalls','ingestion_events','ingestion_offsets','recall_product_matches','ingestion_batches')}
            third=name+'-empty'
            start(third)
            wait_for(lambda:command('docker','inspect','-f','{{.State.Running}}',third)=='false',180)
            assert command('docker','inspect','-f','{{.State.ExitCode}}',third)=='0'
            assert final=={t:count(t) for t in final}
            report['scenarios'].append(dict(boundary=boundary,status='passed',exit_code=137,
                checkpoint_commit_absent_before_kill=True,checkpoint_identity_preserved=True,
                committed_after_resume=True,counts_before_kill=before,final_counts=final,
                kafka_messages=len(published),unique_events=len(expected_events),missing_products=0,
                extra_products=0,all_kafka_offsets_accounted=True,empty_restart_unchanged=True))
            print('PASS',boundary,flush=True)
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['error']=str(error)
        raise
    finally:
        from datetime import datetime,timezone
        report['completed_at']=datetime.now(timezone.utc).isoformat()
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        for name in reversed(containers):
            subprocess.run(['docker','rm','-f',name],capture_output=True)
        subprocess.run(['docker','network','rm',network],capture_output=True)
        print(output/'report.json',flush=True)


if __name__=='__main__':
    worker() if '--worker' in sys.argv else main()
