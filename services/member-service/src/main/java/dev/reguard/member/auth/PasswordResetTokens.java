package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;

@Repository
public class PasswordResetTokens {
    public record Issued(
            String email,
            String token
    ) {}

    private final NamedParameterJdbcTemplate jdbc;
    private final PasswordEncoder encoder;
    private final SecureRandom random = new SecureRandom();

    public PasswordResetTokens(NamedParameterJdbcTemplate jdbc, PasswordEncoder encoder) {
        this.jdbc = jdbc;
        this.encoder = encoder;
    }

    @Transactional
    public Optional<Issued> issue(String email) {
        var users =
                jdbc.query(
                        "SELECT id FROM users WHERE lower(btrim(email))=:email FOR UPDATE", Map.of("email", email),
                        (rs, row) -> rs.getObject("id", UUID.class));

        if (users.isEmpty()) {
            return Optional.empty();
        }
        UUID user = users.getFirst();
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        jdbc.update("DELETE FROM password_reset_tokens WHERE user_id=:user", Map.of("user", user));
        jdbc.update(
                """
                INSERT INTO password_reset_tokens(token_hash,user_id,expires_at)
                VALUES (:hash,:user,CURRENT_TIMESTAMP+interval '30 minutes')
                """,
                Map.of("hash", hash(token), "user", user));

        return Optional.of(new Issued(email, token));
    }

    public void revoke(String token) {
        jdbc.update(
                "DELETE FROM password_reset_tokens WHERE token_hash=:hash", Map.of("hash", hash(token)));
    }

    @Transactional
    public void reset(String token, String password) {
        if (password.length() < 8 || password.getBytes(StandardCharsets.UTF_8).length > 72)
            throw ApiException.invalid("비밀번호는 8자 이상, UTF-8 기준 72바이트 이하여야 합니다.");

        if (!token.matches("[A-Za-z0-9_-]{43}")) {
            throw invalid();
        }
        var params = Map.of("hash", hash(token));
        var users =
                jdbc.query(
                        "SELECT user_id FROM password_reset_tokens WHERE token_hash=:hash", params,
                        (rs, row) -> rs.getObject("user_id", UUID.class));

        if (users.isEmpty()) {
            throw invalid();
        }
        UUID user = users.getFirst();
        jdbc.query(
                "SELECT id FROM users WHERE id=:user FOR UPDATE", Map.of("user", user),
                (rs, row) -> 0);
        var active =
                jdbc.query(
                        """
                        SELECT user_id FROM password_reset_tokens
                        WHERE token_hash=:hash AND expires_at>CURRENT_TIMESTAMP FOR UPDATE
                        """,
                        params,
                        (rs, row) -> rs.getObject("user_id", UUID.class));

        if (active.isEmpty()) {
            throw invalid();
        }
        jdbc.update(
                "UPDATE users SET password_hash=:password WHERE id=:user", Map.of("password", encoder.encode(password), "user", user));
        jdbc.update("DELETE FROM access_tokens WHERE user_id=:user", Map.of("user", user));
        jdbc.update("DELETE FROM password_reset_tokens WHERE user_id=:user", Map.of("user", user));
    }

    private ApiException invalid() {
        return new ApiException(400, "INVALID_RESET_TOKEN", "재설정 링크가 유효하지 않거나 만료되었습니다.");
    }

    private static String hash(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
