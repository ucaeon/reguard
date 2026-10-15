WITH unmatched AS (
    SELECT r.* FROM recalls r
    WHERE NOT EXISTS (
        SELECT 1 FROM recall_product_matches m WHERE m.recall_id = r.id
    )
), classified AS (
    SELECT source,
        CASE WHEN source = 'FOOD_I0490' THEN
            CASE WHEN coalesce(btrim(raw_payload->>'PRDLST_REPORT_NO'), '') IN ('', '-', '해당없음', '데이터없음')
                THEN 'missing_report_number' ELSE 'report_number_not_in_catalog' END
        WHEN source = 'SAFETY_RECALL' THEN
            CASE WHEN coalesce(btrim(raw_payload->>'certNum'), '') IN ('', '-', '해당없음', '없음', '미인증')
                THEN 'missing_certificate'
            WHEN EXISTS (
                SELECT 1 FROM regexp_split_to_table(raw_payload->>'certNum', E'[,;\n\r]+|[[:space:]]+/[[:space:]]+') cert(value)
                JOIN product_identifiers i ON i.identifier_type = 'KC_CERT_NO'
                    AND i.identifier_value = btrim(cert.value)
            ) THEN 'model_not_matched'
            ELSE 'certificate_not_in_catalog' END
        ELSE 'unsupported_source' END AS reason
    FROM unmatched
)
SELECT source, reason, count(*) FROM classified GROUP BY source, reason ORDER BY source, reason;
