from pathlib import Path
import subprocess

rule = (Path(__file__).resolve().parents[1] / "pipelines/spark/food_matching.sql").read_text()
setup = """
BEGIN;
CREATE TEMP TABLE products (LIKE public.products INCLUDING ALL);
CREATE TEMP TABLE recalls (LIKE public.recalls INCLUDING ALL);
CREATE TEMP TABLE product_identifiers (LIKE public.product_identifiers INCLUDING ALL);
CREATE TEMP TABLE recall_product_matches (LIKE public.recall_product_matches INCLUDING ALL);
INSERT INTO products(id,source,source_record_id,name,company_name,category)
SELECT md5(n::text)::uuid, 'FOOD_I1250', n::text, '제품'||n, '업체', 'FOOD' FROM generate_series(1,4) n;
INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value)
SELECT id,id,'FOOD_REPORT_NO',CASE WHEN source_record_id IN ('2','3') THEN '22' ELSE source_record_id END FROM products;
INSERT INTO recalls(id,source,source_recall_id,product_name,company_name,raw_payload)
VALUES
(md5('r1')::uuid,'FOOD_I0490','r1','다른 표기','업체','{"PRDLST_REPORT_NO":"1"}'),
(md5('r2')::uuid,'FOOD_I0490','r2','제품2','업체','{"PRDLST_REPORT_NO":"22"}'),
(md5('r3')::uuid,'FOOD_I0490','r3','제품4','업체','{}'),
(md5('r4')::uuid,'FOOD_I0490','r4','제품4','다른 업체','{}'),
(md5('r5')::uuid,'FOOD_I0490','r5','제품4','업체','{"PRDLST_REPORT_NO":"999"}');
"""
checks = """
DO $$ BEGIN
 IF (SELECT count(*) FROM recall_product_matches WHERE match_status='CONFIRMED') <> 1
 OR (SELECT count(*) FROM recall_product_matches WHERE match_status='CANDIDATE') <> 3
 THEN RAISE EXCEPTION 'Incorrect identity matching'; END IF;
END $$;
CREATE TEMP TABLE previous_matches AS TABLE recall_product_matches;
DROP TABLE proposed_matches;
"""
repeat = """
DO $$ BEGIN
 IF EXISTS ((TABLE previous_matches EXCEPT TABLE recall_product_matches)
 UNION ALL (TABLE recall_product_matches EXCEPT TABLE previous_matches))
 THEN RAISE EXCEPTION 'Rerun changed existing matches'; END IF;
END $$;
UPDATE recalls SET raw_payload='{"PRDLST_REPORT_NO":"999"}' WHERE source_recall_id='r1';
DROP TABLE proposed_matches;
"""
finish = """
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM recall_product_matches WHERE recall_id=md5('r1')::uuid)
 THEN RAISE EXCEPTION 'Stale match survived'; END IF;
END $$;
ROLLBACK;
"""
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--k3s", action="store_true")
    args = parser.parse_args()
    statement = setup + "CREATE TEMP TABLE matching_scope ON COMMIT DROP AS SELECT id AS recall_id FROM recalls;" + rule + checks + rule + repeat + rule + finish
    command = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", "reguard_safety", "-d", "reguard_safety"]
    if args.k3s:
        from local_k3s import kube
        kube("exec", "-i", "deployment/postgres", "--", *command, input=statement)
    else:
        subprocess.run(["docker", "exec", "-i", "reguard-local-postgres-1", *command], input=statement, text=True, check=True)
    print("PASS: identity matching, ambiguity, idempotency and stale removal; fixtures rolled back")


if __name__ == "__main__":
    main()
