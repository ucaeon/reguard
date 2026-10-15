package dev.reguard.notification;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.reguard.notification.api.ApiException;
import dev.reguard.notification.events.RecallAlertConsumer;
import dev.reguard.notification.inbox.*;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.*;

class NotificationTest {
    @Test
    void invalidPageNeverQueriesDatabase() {
        var repository = mock(NotificationRepository.class);
        var controller = new NotificationController(new NotificationService(repository));
        assertThrows(ApiException.class, () -> controller.list(UUID.randomUUID(), -1, 20));
        assertThrows(ApiException.class, () -> controller.list(UUID.randomUUID(), 0, 101));
        verifyNoInteractions(repository);
    }

    @Test
    void pageUsesUserAndLongOffset() {
        var repository = mock(NotificationRepository.class);
        var controller = new NotificationController(new NotificationService(repository));
        UUID user = UUID.randomUUID();
        var page = controller.list(user, Integer.MAX_VALUE, 100);
        assertTrue(page.items().isEmpty());
        verify(repository).list(user, 214748364700L, 101);
    }

    @Test
    void malformedEventIsQuarantined() {
        var jdbc = mock(NamedParameterJdbcTemplate.class);
        var events = new RecallAlertConsumer(jdbc, new ObjectMapper());
        events.receive(new ConsumerRecord<>("test", 0, 1L, "user", "invalid-json"));
        verify(jdbc).update(contains("rejected_notification_events"), anyMap());
        verify(jdbc, never()).update(contains("INSERT INTO notifications("), anyMap());
    }

    @Test
    void databaseFailurePropagatesForKafkaRetry() throws Exception {
        var jdbc = mock(NamedParameterJdbcTemplate.class);
        var mapper = new ObjectMapper();
        var events = new RecallAlertConsumer(jdbc, mapper);
        String payload =
                mapper.writeValueAsString(
                        Map.of(
                                "schemaVersion", 1,
                                "eventId", UUID.randomUUID(),
                                "userId", UUID.randomUUID(),
                                "ownedProductId", UUID.randomUUID(),
                                "recallId", UUID.randomUUID(),
                                "productName", "제품",
                                "matchStatus", "CONFIRMED"));
        when(jdbc.update(contains("INSERT INTO notifications("), anyMap()))
                .thenThrow(new DataAccessResourceFailureException("offline"));
        assertThrows(
                DataAccessResourceFailureException.class,
                () -> events.receive(new ConsumerRecord<>("test", 0, 1L, "user", payload)));
        verify(jdbc, never()).update(contains("rejected_notification_events"), anyMap());
    }

    @Test
    void quarantineDatabaseFailureAlsoRetries() {
        var jdbc = mock(NamedParameterJdbcTemplate.class);
        when(jdbc.update(anyString(), anyMap()))
                .thenThrow(new DataAccessResourceFailureException("offline"));
        assertThrows(
                DataAccessResourceFailureException.class,
                () ->
                        new RecallAlertConsumer(jdbc, new ObjectMapper())
                                .receive(new ConsumerRecord<>("test", 0, 1L, "u", "bad")));
    }
}
