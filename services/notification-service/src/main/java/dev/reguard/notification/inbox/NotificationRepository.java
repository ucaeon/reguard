package dev.reguard.notification.inbox;

import dev.reguard.notification.api.ApiException;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.*;
import java.time.OffsetDateTime;
import java.util.*;

@Repository
public class NotificationRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public NotificationRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private Notification map(ResultSet rs) throws SQLException {
        return new Notification(
                rs.getObject("id", UUID.class),
                rs.getObject("owned_product_id", UUID.class),
                rs.getObject("recall_id", UUID.class),
                rs.getLong("recall_version"),
                rs.getString("notification_type"),
                rs.getString("title"),
                rs.getString("message"),
                rs.getString("eligibility_status"),
                rs.getObject("read_at", OffsetDateTime.class),
                rs.getObject("created_at", OffsetDateTime.class));
    }

    public List<Notification> list(UUID user, long offset, int limit) {
        return jdbc.query(
                "SELECT * FROM notifications WHERE user_id=:user ORDER BY created_at DESC,id LIMIT"
                    + " :limit OFFSET :offset",
                Map.of("user", user, "offset", offset, "limit", limit),
                (rs, row) -> map(rs));
    }

    public long unread(UUID user) {
        return jdbc.queryForObject(
                "SELECT count(*) FROM notifications WHERE user_id=:user AND read_at IS NULL", Map.of("user", user),
                Long.class);
    }

    public Notification read(UUID user, UUID id) {
        return jdbc
                .query(
                        """
                        UPDATE notifications SET read_at=coalesce(read_at,CURRENT_TIMESTAMP)
                        WHERE id=:id AND user_id=:user RETURNING *
                        """,
                        Map.of("id", id, "user", user),
                        (rs, row) -> map(rs))
                .stream()
                .findFirst()
                .orElseThrow(
                        () -> new ApiException(404, "NOTIFICATION_NOT_FOUND", "알림을 찾을 수 없습니다."));
    }
}
