package dev.reguard.member.owned;

import org.springframework.jdbc.core.namedparam.*;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.sql.*;
import java.time.*;
import java.util.*;

@Repository
public class OwnedRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public OwnedRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private OwnedProduct map(ResultSet rs) throws SQLException {
        return new OwnedProduct(
                rs.getObject("id", UUID.class),
                rs.getObject("catalog_product_id", UUID.class),
                rs.getString("registration_type"),
                rs.getString("product_name"),
                rs.getString("company_name"),
                rs.getString("model_name"),
                rs.getString("identifier_type"),
                rs.getString("identifier_value"),
                rs.getObject("expiry_date", LocalDate.class),
                rs.getString("lot_number"),
                rs.getObject("created_at", OffsetDateTime.class));
    }

    public Optional<OwnedProduct> find(UUID user, UUID id) {
        return jdbc
                .query(
                        "SELECT * FROM owned_products WHERE id=:id AND user_id=:user", Map.of("id", id, "user", user),
                        (rs, n) -> map(rs))
                .stream()
                .findFirst();
    }

    public Optional<OwnedProduct> lock(UUID user, UUID id) {
        return jdbc
                .query(
                        "SELECT * FROM owned_products WHERE id=:id AND user_id=:user FOR UPDATE", Map.of("id", id, "user", user),
                        (rs, n) -> map(rs))
                .stream()
                .findFirst();
    }

    public List<OwnedProduct> list(UUID user, long offset, int limit) {
        return jdbc.query(
                """
                SELECT * FROM owned_products WHERE user_id=:user
                ORDER BY created_at DESC, id LIMIT :limit OFFSET :offset
                """,
                Map.of("user", user, "limit", limit, "offset", offset),
                (rs, n) -> map(rs));
    }

    private MapSqlParameterSource params(UUID user, OwnedProduct p) {
        return new MapSqlParameterSource()
                .addValue("user", user)
                .addValue("id", p.id())
                .addValue("catalog", p.catalogProductId())
                .addValue("type", p.registrationType())
                .addValue("name", p.productName())
                .addValue("company", p.companyName())
                .addValue("model", p.modelName())
                .addValue("identifierType", p.identifierType())
                .addValue("identifierValue", p.identifierValue())
                .addValue("expiry", p.expiryDate())
                .addValue("lot", p.lotNumber());
    }

    public OwnedProduct insert(UUID user, OwnedProduct p) {
        return jdbc.queryForObject(
                """
                INSERT INTO owned_products (
                    id, user_id, catalog_product_id, registration_type, product_name,
                    company_name, model_name, identifier_type, identifier_value, expiry_date, lot_number
                ) VALUES (
                    :id, :user, :catalog, :type, :name,
                    :company, :model, :identifierType, :identifierValue, :expiry, :lot
                ) RETURNING *
                """,
                params(user, p),
                (rs, n) -> map(rs));
    }

    public Optional<OwnedProduct> update(UUID user, OwnedProduct p) {
        return jdbc
                .query(
                        """
                        UPDATE owned_products SET product_name=:name, company_name=:company,
                            model_name=:model, identifier_type=:identifierType, identifier_value=:identifierValue,
                            expiry_date=:expiry, lot_number=:lot
                        WHERE id=:id AND user_id=:user RETURNING *
                        """,
                        params(user, p),
                        (rs, n) -> map(rs))
                .stream()
                .findFirst();
    }

    @Transactional
    public boolean delete(UUID user, UUID id) {
        int deleted =
                jdbc.update(
                        "DELETE FROM owned_products WHERE id=:id AND user_id=:user", Map.of("id", id, "user", user));

        if (deleted == 0) {
            return false;
        }
        UUID event = UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO alert_outbox(event_id,user_id,owned_product_id,recall_id,payload,event_type,recall_version)
                VALUES (:event,:user,:owned,NULL,
                    jsonb_build_object('schemaVersion',2,'eventType','OWNED_PRODUCT_DELETED',
                        'eventId',CAST(:event AS text),'userId',CAST(:user AS text),'ownedProductId',CAST(:owned AS text)),
                    'OWNED_PRODUCT_DELETED',0)
                """,
                Map.of("event", event, "user", user, "owned", id));

        return true;
    }
}
