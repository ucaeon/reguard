package dev.reguard.member.auth;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import java.time.OffsetDateTime;
import java.util.*;

@Repository
public class AuthRepository {
    public record Credentials(UUID id, String hash) {}
    public record Account(UUID id, String email, String displayName, OffsetDateTime createdAt) {}
    private final NamedParameterJdbcTemplate jdbc;
    public AuthRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }
    public void insert(UUID id, String email, String name, String hash) {
        jdbc.update("INSERT INTO users(id,email,display_name,password_hash) VALUES (:id,:email,:name,:hash)",
                Map.of("id", id, "email", email, "name", name, "hash", hash));
    }
    public List<Credentials> lockCredentials(String email) {
        return jdbc.query("SELECT id,password_hash FROM users WHERE lower(btrim(email))=:email FOR UPDATE",
                Map.of("email", email), (rs, n) -> new Credentials(rs.getObject("id", UUID.class), rs.getString("password_hash")));
    }
    public void insertToken(String hash, UUID user, OffsetDateTime expires) {
        jdbc.update("INSERT INTO access_tokens(token_hash,user_id,expires_at) VALUES (:hash,:user,:expires)",
                Map.of("hash", hash, "user", user, "expires", expires));
    }
    public UUID activeTokenUser(String hash) {
        return jdbc.query("SELECT user_id FROM access_tokens WHERE token_hash=:hash AND expires_at>CURRENT_TIMESTAMP",
                Map.of("hash", hash), (rs, n) -> rs.getObject("user_id", UUID.class)).stream().findFirst().orElse(null);
    }
    public void deleteToken(String hash) {
        jdbc.update("DELETE FROM access_tokens WHERE token_hash=:hash", Map.of("hash", hash));
    }
    public Optional<Account> find(UUID user) {
        return jdbc.query("SELECT id,email,display_name,created_at FROM users WHERE id=:id", Map.of("id", user),
                (rs, n) -> new Account(rs.getObject("id", UUID.class), rs.getString("email"), rs.getString("display_name"), rs.getObject("created_at", OffsetDateTime.class))).stream().findFirst();
    }
}
