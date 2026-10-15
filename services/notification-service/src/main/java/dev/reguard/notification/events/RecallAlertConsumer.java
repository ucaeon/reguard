package dev.reguard.notification.events;

import com.fasterxml.jackson.databind.*;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

@Component
public class RecallAlertConsumer {
    private record Event(
            UUID id,
            UUID user,
            UUID owned,
            UUID recall,
            long version,
            String type,
            String name,
            String status
    ) {}

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public RecallAlertConsumer(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    private Event parse(String payload) throws Exception {
        JsonNode node = mapper.readTree(payload);

        if (node == null || !node.path("schemaVersion").isIntegralNumber())
            throw new IllegalArgumentException();
        int schema = node.path("schemaVersion").asInt();

        if (schema != 1 && schema != 2) {
            throw new IllegalArgumentException();
        }
        UUID id = UUID.fromString(node.path("eventId").asText());
        UUID user = UUID.fromString(node.path("userId").asText());
        UUID owned = UUID.fromString(node.path("ownedProductId").asText());
        String type = schema == 1 ? "RECALL_MATCH" : node.path("eventType").asText();

        if (type.equals("OWNED_PRODUCT_DELETED"))
            return new Event(id, user, owned, null, 0, type, null, null);

        if (!type.equals("RECALL_MATCH")) {
            throw new IllegalArgumentException();
        }
        String status = node.path("matchStatus").asText();

        if (!Set.of("CONFIRMED", "CANDIDATE").contains(status))
            throw new IllegalArgumentException();
        UUID recall = UUID.fromString(node.path("recallId").asText());
        long version = schema == 1 ? 1 : node.path("recallVersion").asLong(0);

        if (version < 1) {
            throw new IllegalArgumentException();
        }
        if (!node.path("productName").isTextual()) {
            throw new IllegalArgumentException();
        }
        String name = node.path("productName").asText();

        if (name.isBlank() || name.length() > 500 || name.indexOf(0) >= 0)
            throw new IllegalArgumentException();

        return new Event(id, user, owned, recall, version, type, name, status);
    }

    @Transactional
    @KafkaListener(
            topics = "${reguard.alert-topic:reguard.recall-alerts.v1}",
            groupId = "${reguard.alert-group:reguard-notification-v1}")
    public void receive(ConsumerRecord<String, String> record) {
        Event event;
        try {
            event = parse(record.value());
        } catch (Exception e) {
            jdbc.update(
                    """
                    INSERT INTO rejected_notification_events(topic,partition_id,offset_id,reason,payload)
                    VALUES (:topic,:partition,:offset,'INVALID_EVENT',:payload) ON CONFLICT DO NOTHING
                    """,
                    Map.of(
                            "topic", record.topic(),
                            "partition", record.partition(),
                            "offset", record.offset(),
                            "payload", Objects.toString(record.value(), "null").replace("\u0000", "")));
            return;
        }
        jdbc.query(
                "SELECT pg_advisory_xact_lock(hashtextextended(:id,0))", Map.of("id", event.owned().toString()),
                (rs, row) -> 0);

        if (event.type().equals("OWNED_PRODUCT_DELETED")) {
            jdbc.update(
                    "INSERT INTO deleted_owned_products(owned_product_id,user_id) VALUES"
                        + " (:owned,:user) ON CONFLICT DO NOTHING",
                    Map.of("owned", event.owned(), "user", event.user()));
            jdbc.update(
                    "DELETE FROM notifications WHERE owned_product_id=:owned AND user_id=:user", Map.of("owned", event.owned(), "user", event.user()));
            return;
        }
        String title =
                event.version() > 1
                        ? "등록 제품의 리콜 정보가 변경되었습니다"
                        : event.status().equals("CONFIRMED")
                                ? "등록 제품의 관련 리콜을 확인해주세요"
                                : "등록 제품의 리콜 후보를 확인해주세요";
        jdbc.update(
                """
                INSERT INTO notifications(id,user_id,owned_product_id,recall_id,notification_type,title,message,eligibility_status,recall_version)
                SELECT :id,:user,:owned,:recall,'RECALL_MATCH',:title,:message,'NEEDS_CHECK',:version
                WHERE NOT EXISTS (SELECT 1 FROM deleted_owned_products WHERE owned_product_id=:owned)
                ON CONFLICT DO NOTHING
                """,
                Map.of(
                        "id", event.id(),
                        "user", event.user(),
                        "owned", event.owned(),
                        "recall", event.recall(),
                        "title", title,
                        "message", event.name() + "에 관련된 리콜 정보가 있습니다. 제조일·소비기한 등 회수 조건을 확인해주세요.",
                        "version", event.version()));
    }
}
