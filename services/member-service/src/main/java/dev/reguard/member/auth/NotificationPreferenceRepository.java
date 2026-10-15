package dev.reguard.member.auth;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.*;

@Repository
public class NotificationPreferenceRepository {
    private final NamedParameterJdbcTemplate jdbc;
    public NotificationPreferenceRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }
    public boolean get(UUID user) {
        return Boolean.TRUE.equals(jdbc.queryForObject("SELECT notifications_enabled FROM users WHERE id=:id", Map.of("id", user), Boolean.class));
    }
    public boolean save(UUID user, boolean enabled) {
        return Boolean.TRUE.equals(jdbc.queryForObject("UPDATE users SET notifications_enabled=:enabled WHERE id=:id RETURNING notifications_enabled", Map.of("id", user, "enabled", enabled), Boolean.class));
    }
}
