"""Compare scoped and full matching inside rollback-only transactions."""
import json
from pathlib import Path
import statistics
import time
from uuid import uuid4
from psycopg import sql as pgsql

from orchestration.airflow.state import database
from pipelines.spark.matching import match_sources

SOURCES = {'FOOD_I1250', 'FOOD_I0030', 'FOOD_I0490', 'SAFETY_KC', 'SAFETY_RECALL'}


def result(connection):
    return set(connection.execute('''SELECT recall_id, product_id, match_method,
        match_status, rule_version FROM recall_product_matches''').fetchall())


def run_rule(connection, sources, products=None, recalls=None):
    connection.execute('SAVEPOINT matching_check')
    previous = set(connection.execute("SELECT id,recall_id,product_id,matched_at FROM recall_product_matches").fetchall())
    started = time.perf_counter()
    match_sources(connection, sources, products, recalls)
    elapsed = time.perf_counter() - started
    rows = result(connection)
    if products is not None or recalls is not None:
        affected = {row[0] for row in connection.execute("SELECT recall_id FROM matching_scope")}
        current = set(connection.execute("SELECT id,recall_id,product_id,matched_at FROM recall_product_matches").fetchall())
        assert {row for row in previous if row[1] not in affected} == {
            row for row in current if row[1] not in affected
        }, "unrelated matching rows changed"
    scoped = connection.execute('SELECT count(*) FROM matching_scope').fetchone()[0]
    connection.execute('ROLLBACK TO SAVEPOINT matching_check')
    return rows, elapsed, scoped


def verify_changes(connection, schema="public"):
    checks = []
    for table in ('products', 'recalls', 'product_identifiers', 'recall_product_matches'):
        connection.execute(pgsql.SQL('CREATE TEMP TABLE {} (LIKE {}.{} INCLUDING ALL) ON COMMIT DROP').format(
            pgsql.Identifier(table), pgsql.Identifier(schema), pgsql.Identifier(table)))
    products = [uuid4(), uuid4(), uuid4()]
    recalls = [uuid4(), uuid4()]
    for index, product in enumerate(products):
        connection.execute('''INSERT INTO products(id,source,source_record_id,name,company_name,category)
            VALUES (%s,'FOOD_I1250',%s,'same','maker','FOOD')''', (product,str(index)))
        connection.execute('INSERT INTO product_identifiers VALUES (%s,%s,\'FOOD_REPORT_NO\',%s)',
                           (uuid4(),product,'1' if index < 2 else '2'))
    for index, recall in enumerate(recalls):
        connection.execute('''INSERT INTO recalls(id,source,source_recall_id,product_name,company_name,raw_payload)
            VALUES (%s,'FOOD_I0490',%s,'same','maker',%s::jsonb)''',
            (recall,str(index),json.dumps({'PRDLST_REPORT_NO':str(index+1)})))
    kc_product, kc_recall = uuid4(), uuid4()
    connection.execute("INSERT INTO products(id,source,source_record_id,name,model_name,category) VALUES (%s,'SAFETY_KC','kc','toy','MODEL-A','KC')", (kc_product,))
    connection.execute("INSERT INTO product_identifiers VALUES (%s,%s,'KC_CERT_NO','CB001-1234')", (uuid4(),kc_product))
    connection.execute("INSERT INTO recalls(id,source,source_recall_id,product_name,raw_payload) VALUES (%s,'SAFETY_RECALL','kc','toy',%s::jsonb)",
                       (kc_recall,json.dumps({'certNum':'CB001-1234','recallModelName':'MODEL-A'})))
    match_sources(connection,SOURCES)
    for name in ('matching_scope','proposed_matches','kc_proposed'):
        connection.execute(f'DROP TABLE {name}')
    untouched = connection.execute('SELECT id,matched_at FROM recall_product_matches WHERE recall_id=%s', (recalls[1],)).fetchall()
    changes = [
        ('kc_model_changed', "UPDATE products SET model_name='MODEL-B' WHERE id=%s", (kc_product,), {kc_product}, set()),
        ('kc_recall_changed', "UPDATE recalls SET raw_payload=jsonb_set(raw_payload,'{recallModelName}', '\"MODEL-B\"'::jsonb) WHERE id=%s", (kc_recall,), set(), {kc_recall}),
        ('identifier_removed', "DELETE FROM product_identifiers WHERE product_id=%s", (products[1],), {products[1]}, set()),
        ('identifier_changed', "UPDATE product_identifiers SET identifier_value='3' WHERE product_id=%s", (products[0],), {products[0]}, set()),
        ('recall_changed', "UPDATE recalls SET raw_payload='{}'::jsonb WHERE id=%s", (recalls[0],), set(), {recalls[0]}),
    ]
    for name, sql, params, changed_products, changed_recalls in changes:
        connection.execute(sql, params)
        full, _, _ = run_rule(connection,SOURCES)
        scoped, _, _ = run_rule(connection,SOURCES,changed_products,changed_recalls)
        assert full == scoped, name
        assert untouched == connection.execute('SELECT id,matched_at FROM recall_product_matches WHERE recall_id=%s', (recalls[1],)).fetchall()
        checks.append(dict(scenario=name, status='passed', equivalent=True, unrelated_preserved=True))
        print('PASS',name)
        # Establish the updated baseline for the next change.
        match_sources(connection,SOURCES)
        for table in ('matching_scope','proposed_matches','kc_proposed'):
            connection.execute(f'DROP TABLE {table}')

    return checks

def benchmark(connection):
    connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    connection.execute('SELECT pg_advisory_xact_lock(72648301)')
    match_sources(connection,SOURCES)
    for table in ('matching_scope','proposed_matches','kc_proposed'):
        connection.execute(f'DROP TABLE {table}')
    cases = [
        ('one_matched_product', [connection.execute('SELECT product_id FROM recall_product_matches ORDER BY product_id LIMIT 1').fetchone()[0]]),
        ('172_supplements', [x[0] for x in connection.execute("SELECT id FROM products WHERE source='FOOD_I0030' ORDER BY collected_at DESC,id LIMIT 172")]),
        ('100_kc_products', [x[0] for x in connection.execute("SELECT id FROM products WHERE source='SAFETY_KC' ORDER BY id LIMIT 100")]),
    ]
    measurements = []
    for name, ids in cases:
        sources={r[0] for r in connection.execute('SELECT source FROM products WHERE id=ANY(%s)',(ids,))}
        full_times=[]; scoped_times=[]
        for _ in range(3):
            full,full_seconds,_=run_rule(connection,sources)
            scoped,scoped_seconds,scope=run_rule(connection,sources,set(ids),set())
            assert full==scoped,name
            full_times.append(full_seconds);scoped_times.append(scoped_seconds)
        item={'case':name,'changed_products':len(ids),'affected_recalls':scope,
              'full_median_ms':round(statistics.median(full_times)*1000,2),
              'scoped_median_ms':round(statistics.median(scoped_times)*1000,2),
              'equivalent':True,'repeats':3}
        measurements.append(item);print(json.dumps(item),flush=True)
    return measurements


if __name__=='__main__':
    with database() as connection:
        scenarios = verify_changes(connection)
        connection.rollback()
    with database() as connection:
        measurements = benchmark(connection)
        connection.rollback()
    from orchestration.airflow.state import atomic_json, root
    atomic_json(root() / "verification" / "incremental-matching.json", {
        "measurements": measurements,
        "scenarios": scenarios,
        "transaction": "rolled_back",
        "unrelated_matches_preserved": True,
        "method": "three sequential runs, local PostgreSQL, median milliseconds",
    })
