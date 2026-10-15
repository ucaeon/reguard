package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.OffsetDateTime;
import java.util.*;

@Service
public class AuthService {
    public record User(
            UUID id,
            String email,
            String displayName,
            OffsetDateTime createdAt
    ) {}

    public record Token(
            String accessToken,
            String tokenType,
            OffsetDateTime expiresAt
    ) {}

    private final AuthRepository repository;
    private final PasswordEncoder encoder;
    private final SignupVerification verification;
    private final SecureRandom random = new SecureRandom();
    private final String dummyHash;

    public AuthService(AuthRepository repository, PasswordEncoder encoder, SignupVerification verification) {
        this.repository = repository;
        this.verification = verification;
        this.encoder = encoder;
        dummyHash = encoder.encode(UUID.randomUUID().toString());
    }

    private String email(String value) {
        String normalized = value.strip().toLowerCase(Locale.ROOT);

        if (normalized.length() > 320 || !normalized.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+"))
            throw ApiException.invalid("올바른 이메일을 입력해주세요.");

        return normalized;
    }

    private void password(String value) {
        if (value.length() < 8 || value.getBytes(StandardCharsets.UTF_8).length > 72)
            throw ApiException.invalid("비밀번호는 8자 이상, UTF-8 기준 72바이트 이하여야 합니다.");
    }

    @Transactional
    public User signup(String email, String password, String displayName, String verificationToken) {
        password(password);
        verification.consume(email, verificationToken);
        String name = displayName.strip();

        if (name.isEmpty() || name.length() > 100 || name.indexOf(0) >= 0)
            throw ApiException.invalid("이름은 1~100자로 입력해주세요.");
        UUID id = UUID.randomUUID();
        try {
            repository.insert(id, email(email), name, encoder.encode(password));
        } catch (DuplicateKeyException e) {
            throw new ApiException(409, "EMAIL_ALREADY_EXISTS", "이미 등록된 이메일입니다.");
        }
        return me(id);
    }

    @Transactional
    public Token login(String email, String password) {
        password(password);
        var rows = repository.lockCredentials(email(email));
        String hash =
                rows.isEmpty() || rows.getFirst().hash() == null
                        ? dummyHash
                        : rows.getFirst().hash();
        boolean valid = encoder.matches(password, hash);

        if (!valid || rows.isEmpty() || rows.getFirst().hash() == null)
            throw new ApiException(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호를 확인해주세요.");
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        var expires = OffsetDateTime.now().plusHours(24);
        repository.insertToken(digest(token), rows.getFirst().id(), expires);

        return new Token(token, "Bearer", expires);
    }

    public UUID authenticate(String token) {
        if (!token.matches("[A-Za-z0-9_-]{43}")) {
            return null;
        }
        return repository.activeTokenUser(digest(token));
    }

    public void logout(String token) { repository.deleteToken(digest(token)); }

    public User me(UUID id) {
        var account = repository.find(id).orElseThrow(() -> new ApiException(401, "UNAUTHORIZED", "로그인이 필요합니다."));
        return new User(account.id(), account.email(), account.displayName(), account.createdAt());
    }

    private static String digest(String token) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
