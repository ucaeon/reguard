CREATE TEMP TABLE proposed_matches ON COMMIT DROP AS
WITH numbered AS (
    SELECT r.id AS recall_id, i.product_id,
           count(*) OVER (PARTITION BY r.id) AS targets
    FROM recalls r
JOIN matching_scope scope ON scope.recall_id = r.id
    JOIN product_identifiers i
      ON i.identifier_type = 'FOOD_REPORT_NO'
     AND i.identifier_value = btrim(r.raw_payload ->> 'PRDLST_REPORT_NO')
    JOIN products p ON p.id = i.product_id
    WHERE r.source = 'FOOD_I0490'
      AND p.source IN ('FOOD_I1250', 'FOOD_I0030')
      AND btrim(r.raw_payload ->> 'PRDLST_REPORT_NO') ~ '^[0-9]+$'
), named AS (
    SELECT r.id AS recall_id, p.id AS product_id
    FROM recalls r
JOIN matching_scope scope ON scope.recall_id = r.id
    JOIN products p ON btrim(p.name) = btrim(r.product_name)
                   AND btrim(p.company_name) = btrim(r.company_name)
    WHERE r.source = 'FOOD_I0490'
      AND p.source IN ('FOOD_I1250', 'FOOD_I0030')
      AND coalesce(btrim(r.raw_payload ->> 'PRDLST_REPORT_NO'), '') IN ('', '-', '해당없음', '데이터없음')
      AND btrim(r.company_name) NOT IN ('', '-', '해당없음', '데이터없음')
)
SELECT recall_id, product_id, 'FOOD_REPORT_NO'::text AS method,
       CASE WHEN targets = 1 THEN 'CONFIRMED' ELSE 'CANDIDATE' END AS status
FROM numbered
UNION ALL
SELECT recall_id, product_id, 'EXACT_NAME_COMPANY', 'CANDIDATE' FROM named;

DELETE FROM recall_product_matches m
WHERE EXISTS (SELECT 1 FROM matching_scope scope WHERE scope.recall_id = m.recall_id)
  AND m.rule_version = 'food-identity-v1'
  AND NOT EXISTS (SELECT 1 FROM proposed_matches n
                  WHERE n.recall_id = m.recall_id AND n.product_id = m.product_id);
INSERT INTO recall_product_matches AS m
    (id, recall_id, product_id, match_method, match_status, rule_version)
SELECT gen_random_uuid(), recall_id, product_id, method, status, 'food-identity-v1'
FROM proposed_matches
ON CONFLICT (recall_id, product_id) DO UPDATE
SET match_method = EXCLUDED.match_method,
    match_status = EXCLUDED.match_status,
    matched_at = CURRENT_TIMESTAMP
WHERE m.rule_version = 'food-identity-v1'
  AND (m.match_method, m.match_status) IS DISTINCT FROM (EXCLUDED.match_method, EXCLUDED.match_status);
