package dev.reguard.member.alerts;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.reguard.member.owned.SafetyClient;
import dev.reguard.member.owned.OwnedProduct;
import org.springframework.beans.factory.annotation.Value;

import org.slf4j.*;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.*;

@Component
public class RecallAlertScanner {
    private static final Logger log = LoggerFactory.getLogger(RecallAlertScanner.class);

    private final NamedParameterJdbcTemplate jdbc;
    private final SafetyClient safety;
    private final ObjectMapper mapper;
    private final boolean enabled;
    private UUID cursor = new UUID(0, 0);

    public RecallAlertScanner(
            NamedParameterJdbcTemplate jdbc, SafetyClient safety, ObjectMapper mapper,
            @Value("${reguard.alerts.enabled:false}") boolean enabled) {
        this.jdbc = jdbc;
        this.safety = safety;
        this.mapper = mapper;
        this.enabled = enabled;
    }

    @Scheduled(fixedDelayString = "${reguard.alerts.scan-delay-ms:60000}")
    public void scan() {
        if (!enabled) return;
        var products = jdbc.query(
                "SELECT * FROM owned_products WHERE EXISTS (SELECT 1 FROM users WHERE users.id=owned_products.user_id AND notifications_enabled) AND id>:cursor ORDER BY id LIMIT 50",
                Map.of("cursor", cursor),
                (rs, n) -> Map.entry(rs.getObject("user_id", UUID.class), new OwnedProduct(
                        rs.getObject("id", UUID.class), rs.getObject("catalog_product_id", UUID.class),
                        rs.getString("registration_type"), rs.getString("product_name"),
                        rs.getString("company_name"), rs.getString("model_name"),
                        rs.getString("identifier_type"), rs.getString("identifier_value"),
                        rs.getObject("expiry_date", java.time.LocalDate.class), rs.getString("lot_number"),
                        rs.getObject("created_at", java.time.OffsetDateTime.class))));
        for (var entry : products) {
            scanProduct(entry.getKey(), entry.getValue());
            cursor = entry.getValue().id();
        }
        if (products.size() < 50) cursor = new UUID(0, 0);
    }

    public void scanProduct(UUID user, OwnedProduct owned) {
        if (!enabled) return;
        try {
            int page = 0;
            boolean more;
            do {
                var result = safety.recalls(owned, page++, 100);

                for (var item : result.path("items")) {
                    String status = item.path("matchStatus").asText();

                    if (!Set.of("CONFIRMED", "CANDIDATE").contains(status)) {
                        continue;
                    }
                    UUID recall = UUID.fromString(item.path("recall").path("id").asText());
                    UUID event = UUID.randomUUID();
                    String payload =
                            mapper.writeValueAsString(
                                    Map.of(
                                            "schemaVersion", 2,
                                            "eventType", "RECALL_MATCH",
                                            "recallVersion", item.path("recallVersion").asLong(1),
                                            "eventId", event,
                                            "userId", user,
                                            "ownedProductId", owned.id(),
                                            "recallId", recall,
                                            "productName", owned.productName(),
                                            "matchStatus", status));
                    jdbc.update(
                            """
                            INSERT INTO alert_outbox(event_id,user_id,owned_product_id,recall_id,payload,recall_version)
                            SELECT :event,user_id,id,:recall,CAST(:payload AS jsonb),:version FROM owned_products
                            WHERE id=:owned AND user_id=:user
                              AND EXISTS (SELECT 1 FROM users WHERE users.id=:user AND notifications_enabled)
                              AND product_name=:name
                              AND company_name IS NOT DISTINCT FROM :company
                              AND model_name IS NOT DISTINCT FROM :model
                              AND identifier_type IS NOT DISTINCT FROM :identifierType
                              AND identifier_value IS NOT DISTINCT FROM :identifierValue
                            ON CONFLICT (owned_product_id,recall_id,event_type,recall_version) DO NOTHING
                            """,
                            new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
                                    .addValue("event", event)
                                    .addValue("owned", owned.id())
                                    .addValue("user", user)
                                    .addValue("recall", recall)
                                    .addValue("payload", payload)
                                    .addValue("version", item.path("recallVersion").asLong(1))
                                    .addValue("name", owned.productName())
                                    .addValue("company", owned.companyName())
                                    .addValue("model", owned.modelName())
                                    .addValue("identifierType", owned.identifierType())
                                    .addValue("identifierValue", owned.identifierValue()));
                }
                more = result.path("hasNext").asBoolean();
            } while (more);
        } catch (Exception e) {
            log.warn("Recall lookup postponed: {}", e.getClass().getSimpleName());
        }
    }
}
