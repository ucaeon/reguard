package dev.reguard.member.alerts;

import org.slf4j.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.*;
import java.util.concurrent.TimeUnit;

@Component
@ConditionalOnProperty(name = "reguard.alerts.enabled", havingValue = "true")
public class RecallAlertProducer {
    private static final Logger log = LoggerFactory.getLogger(RecallAlertProducer.class);

    private record Pending(
            UUID eventId,
            UUID user,
            String payload
    ) {}

    private final NamedParameterJdbcTemplate jdbc;
    private final KafkaTemplate<String, String> kafka;
    private final TransactionTemplate transaction;
    private final String topic;

    public RecallAlertProducer(
            NamedParameterJdbcTemplate jdbc,
            KafkaTemplate<String, String> kafka,
            TransactionTemplate transaction,
            @Value("${reguard.alert-topic:reguard.recall-alerts.v1}") String topic) {
        this.jdbc = jdbc;
        this.kafka = kafka;
        this.transaction = transaction;
        this.topic = topic;
    }

    @Scheduled(fixedDelayString = "${reguard.alerts.publish-delay-ms:3000}")
    public void publish() {
        try {
            for (int i = 0; i < 10; i++) {
                Boolean sent =
                        transaction.execute(
                                tx -> {
                                    var rows =
                                            jdbc.query(
                                                    """
                                                    SELECT event_id,user_id,payload::text FROM alert_outbox
                                                    WHERE sent_at IS NULL AND (event_type <> 'RECALL_MATCH' OR EXISTS (SELECT 1 FROM users WHERE users.id=alert_outbox.user_id AND notifications_enabled)) ORDER BY created_at,event_id LIMIT 1 FOR UPDATE SKIP LOCKED
                                                    """,
                                                    Map.of(),
                                                    (rs, n) ->
                                                            new Pending(
                                                                    rs.getObject(
                                                                            "event_id", UUID.class),
                                                                    rs.getObject(
                                                                            "user_id", UUID.class),
                                                                    rs.getString("payload")));

                                    if (rows.isEmpty()) {
                                        return false;
                                    }
                                    var event = rows.getFirst();
                                    try {
                                        kafka.send(topic, event.user().toString(), event.payload())
                                                .get(10, TimeUnit.SECONDS);
                                    } catch (InterruptedException e) {
                                        Thread.currentThread().interrupt();
                                        throw new IllegalStateException(
                                                "Alert publication interrupted", e);
                                    } catch (Exception e) {
                                        throw new IllegalStateException(
                                                "Alert publication deferred", e);
                                    }
                                    jdbc.update(
                                            "UPDATE alert_outbox SET sent_at=CURRENT_TIMESTAMP"
                                                + " WHERE event_id=:id",
                                            Map.of("id", event.eventId()));

                                    return true;
                                });

                if (!Boolean.TRUE.equals(sent)) break;
            }
        } catch (Exception e) {
            log.warn("Alert outbox will retry: {}", e.getClass().getSimpleName());
        }
    }
}
