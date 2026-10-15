package dev.reguard.safety.recall;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.*;

@Repository
public class RecallRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public RecallRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private Recall map(ResultSet rs) throws SQLException {
        return new Recall(
                rs.getObject("id", UUID.class),
                rs.getString("source"),
                rs.getString("product_name"),
                rs.getString("company_name"),
                rs.getString("reason"),
                rs.getString("action_method"),
                rs.getString("target_conditions"),
                rs.getString("source_url"),
                rs.getString("image_url"),
                rs.getObject("source_created_at", OffsetDateTime.class));
    }

    public List<Recall> list(String q, long offset, int limit) {
        return list(q, null, offset, limit);
    }

    public List<Recall> list(String q, String source, long offset, int limit) {
        return list(q, source, "latest", null, null, offset, limit);
    }

    public List<Recall> list(String q, String source, String sort, java.time.LocalDate from, java.time.LocalDate to, long offset, int limit) {
        var params = new HashMap<String, Object>();
        params.put("offset", offset);
        params.put("limit", limit);
        String where = "";

        if (q != null) {
            params.put(
                    "pattern", "%" + q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%");
            where =
                    " WHERE (r.product_name ILIKE :pattern ESCAPE '!' OR r.company_name ILIKE"
                        + " :pattern ESCAPE '!')";
        }
        if (source != null) {
            where += (where.isEmpty() ? " WHERE " : " AND ") + "r.source = :source";
            params.put("source", source);
        }
        if (from != null) {
            where += (where.isEmpty() ? " WHERE " : " AND ") + "r.source_created_at >= :fromDate";
            params.put("fromDate", from.atStartOfDay(java.time.ZoneId.of("Asia/Seoul")).toOffsetDateTime());
        }
        if (to != null) {
            where += (where.isEmpty() ? " WHERE " : " AND ") + "r.source_created_at < :toDate";
            params.put("toDate", to.plusDays(1).atStartOfDay(java.time.ZoneId.of("Asia/Seoul")).toOffsetDateTime());
        }
        return jdbc.query(
                "SELECT r.* FROM recalls r"
                        + where
                        + " ORDER BY r.source_created_at " + ("oldest".equals(sort) ? "ASC" : "DESC") + " NULLS LAST, r.id LIMIT :limit OFFSET"
                        + " :offset",
                params,
                (rs, row) -> map(rs));
    }

    public List<ProductRecall> forManual(ManualRecallQuery query, long offset, int limit) {
        var params = new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
                .addValue("name", query.productName())
                .addValue("company", query.companyName())
                .addValue("model", query.modelName())
                .addValue("identifier", query.identifierValue())
                .addValue("type", query.identifierType())
                .addValue("offset", offset)
                .addValue("limit", limit);
        String where;
        String status = "CANDIDATE";
        String method = "MANUAL_EXACT_NAME_COMPANY";
        if ("FOOD_REPORT_NO".equals(query.identifierType())) {
            where = "r.source='FOOD_I0490' AND btrim(r.raw_payload->>'PRDLST_REPORT_NO')=:identifier";
            status = "CONFIRMED";
            method = "MANUAL_FOOD_REPORT_NO";
        } else if ("KC_CERT_NO".equals(query.identifierType())) {
            where = "r.source='SAFETY_RECALL' AND upper(btrim(r.raw_payload->>'certNum'))=upper(:identifier)";
            method = "MANUAL_KC_CERT_NO";
        } else if (query.identifierType() != null) {
            where = """
                    EXISTS (SELECT 1 FROM recall_product_matches m
                    JOIN product_identifiers i ON i.product_id=m.product_id
                    WHERE m.recall_id=r.id AND i.identifier_type=:type
                    AND i.identifier_value=:identifier)
                    """;
            method = "MANUAL_CATALOG_IDENTIFIER";
        } else {
            if (query.companyName() == null) return List.of();
            where = """
                    btrim(r.company_name)=:company AND (
                        (r.source='FOOD_I0490' AND btrim(r.product_name)=:name)
                        OR (r.source='SAFETY_RECALL' AND btrim(r.product_name)=:name
                            AND btrim(r.raw_payload->>'recallModelName')=:model)
                    )
                    """;
        }
        final String matchStatus = status;
        final String matchMethod = method;
        return jdbc.query(
                "SELECT r.* FROM recalls r WHERE " + where
                        + " ORDER BY r.source_created_at DESC NULLS LAST,r.id LIMIT :limit OFFSET :offset",
                params,
                (rs, row) -> new ProductRecall(map(rs), rs.getLong("revision"),
                        matchStatus, matchMethod, "manual-identity-v1", "NEEDS_CHECK"));
    }

    public Optional<Recall> find(UUID id) {
        return jdbc
                .query(
                        "SELECT * FROM recalls WHERE id = :id", Map.of("id", id),
                        (rs, row) -> map(rs))
                .stream()
                .findFirst();
    }

    public List<ProductRecall> forProduct(UUID id, long offset, int limit) {
        return jdbc.query(
                """
                SELECT r.*, m.match_status, m.match_method, m.rule_version
                FROM recall_product_matches m
                JOIN recalls r ON r.id = m.recall_id
                WHERE m.product_id = :id
                ORDER BY r.source_created_at DESC NULLS LAST, r.id
                LIMIT :limit OFFSET :offset
                """,
                Map.of("id", id, "offset", offset, "limit", limit),
                (rs, row) ->
                        new ProductRecall(
                                map(rs),
                                rs.getLong("revision"),
                                rs.getString("match_status"),
                                rs.getString("match_method"),
                                rs.getString("rule_version"),
                                "NEEDS_CHECK"));
    }
}
