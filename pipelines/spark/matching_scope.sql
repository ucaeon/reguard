INSERT INTO matching_scope(recall_id)
SELECT r.id FROM recalls r
WHERE r.source = ANY(%s) AND (EXISTS (
    SELECT 1 FROM recall_product_matches m
    JOIN changed_matching_products changed ON changed.product_id = m.product_id
    WHERE m.recall_id = r.id
) OR (
    r.source = 'FOOD_I0490' AND EXISTS (
        SELECT 1 FROM changed_matching_products changed
        JOIN products p ON p.id = changed.product_id
        WHERE p.source IN ('FOOD_I1250', 'FOOD_I0030')
        AND (
            EXISTS (
                SELECT 1 FROM product_identifiers i
                WHERE i.product_id = p.id AND i.identifier_type = 'FOOD_REPORT_NO'
                    AND i.identifier_value = btrim(r.raw_payload->>'PRDLST_REPORT_NO')
            ) OR (btrim(p.name) = btrim(r.product_name)
                  AND btrim(p.company_name) = btrim(r.company_name))
        )
    )
) OR (
    r.source = 'SAFETY_RECALL' AND EXISTS (
        SELECT 1 FROM regexp_split_to_table(
            r.raw_payload->>'certNum', E'[,;\n\r]+|[[:space:]]+/[[:space:]]+'
        ) cert(value)
        JOIN product_identifiers i ON i.identifier_type = 'KC_CERT_NO'
            AND i.identifier_value = btrim(cert.value)
        JOIN changed_matching_products changed ON changed.product_id = i.product_id
    )
))
ON CONFLICT DO NOTHING;
