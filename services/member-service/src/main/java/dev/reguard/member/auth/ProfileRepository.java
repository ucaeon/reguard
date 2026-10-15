package dev.reguard.member.auth;

import org.springframework.jdbc.core.namedparam.*;
import org.springframework.stereotype.Repository;
import java.sql.Types;
import java.util.*;

@Repository
public class ProfileRepository {
    public record StoredProfile(String email, String displayName, byte[] photo) {}
    private final NamedParameterJdbcTemplate jdbc;
    public ProfileRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }
    public StoredProfile find(UUID user) {
        return jdbc.queryForObject("SELECT email,display_name,profile_photo FROM users WHERE id=:id",
                Map.of("id", user), (rs, n) -> new StoredProfile(rs.getString("email"), rs.getString("display_name"), rs.getBytes("profile_photo")));
    }
    public void update(UUID user, String name, byte[] photo) {
        jdbc.update("UPDATE users SET display_name=:name,profile_photo=:photo WHERE id=:id",
                new MapSqlParameterSource().addValue("id", user).addValue("name", name).addValue("photo", photo, Types.BINARY));
    }
    public String lockPassword(UUID user) {
        return jdbc.queryForObject("SELECT password_hash FROM users WHERE id=:id FOR UPDATE", Map.of("id", user), String.class);
    }
    public void changePassword(UUID user, String hash) {
        jdbc.update("UPDATE users SET password_hash=:hash WHERE id=:id", Map.of("id", user, "hash", hash));
        jdbc.update("DELETE FROM access_tokens WHERE user_id=:id", Map.of("id", user));
        jdbc.update("DELETE FROM password_reset_tokens WHERE user_id=:id", Map.of("id", user));
    }
}
