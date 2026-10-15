CREATE TEMP TABLE kc_proposed ON COMMIT DROP AS
SELECT DISTINCT r.id AS recall_id, p.id AS product_id
FROM recalls r
JOIN matching_scope scope ON scope.recall_id = r.id
JOIN LATERAL regexp_split_to_table(
    r.raw_payload->>'certNum', E'[,;\n\r]+|[[:space:]]+/[[:space:]]+'
) AS cert(value) ON TRUE
JOIN product_identifiers i
    ON i.identifier_type = 'KC_CERT_NO'
    AND i.identifier_value = btrim(cert.value)
JOIN products p ON p.id = i.product_id AND p.source = 'SAFETY_KC'
WHERE r.source = 'SAFETY_RECALL'
    AND EXISTS (
        SELECT 1
        FROM unnest(array_append(
            regexp_split_to_array(
                r.raw_payload->>'recallModelName',
                E'[,;\n\r]+|[[:space:]]+/[[:space:]]+'
            ),
            r.raw_payload->>'recallModelName'
        )) AS model(value)
        CROSS JOIN LATERAL (
            SELECT btrim(regexp_replace(
                btrim(model.value), '^[(](제품명|품명)[)][[:space:]]*', ''
            )) AS recall_model
        ) normalized
        WHERE normalized.recall_model <> ''
            AND normalized.recall_model = btrim(regexp_replace(
                btrim(p.model_name), '^[(](제품명|품명)[)][[:space:]]*', ''
            ))
    );

DELETE FROM recall_product_matches m
WHERE EXISTS (SELECT 1 FROM matching_scope scope WHERE scope.recall_id = m.recall_id)
  AND m.rule_version IN ('kc-cert-model-v1', 'kc-cert-model-v2', 'kc-cert-model-v3')
    AND NOT EXISTS (
        SELECT 1 FROM kc_proposed p
        WHERE p.recall_id = m.recall_id AND p.product_id = m.product_id
    );

INSERT INTO recall_product_matches (
    id, recall_id, product_id, match_method, match_status, rule_version
)
SELECT gen_random_uuid(), recall_id, product_id,
    'KC_CERT_MODEL', 'CANDIDATE', 'kc-cert-model-v3'
FROM kc_proposed
ON CONFLICT (recall_id, product_id) DO UPDATE
SET rule_version = EXCLUDED.rule_version
WHERE recall_product_matches.rule_version IN ('kc-cert-model-v1', 'kc-cert-model-v2');
