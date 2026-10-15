package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;

@Service
public class SignupVerification {
    private final SignupVerificationRepository repository;
    private final SignupCodeMailer mailer;
    private final SecureRandom random = new SecureRandom();

    public SignupVerification(SignupVerificationRepository repository, SignupCodeMailer mailer) {
        this.repository = repository;
        this.mailer = mailer;
    }

    static String normalize(String email) {
        String value = email.strip().toLowerCase(Locale.ROOT);
        if (value.length() > 320 || !value.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+"))
            throw ApiException.invalid("올바른 이메일을 입력해 주세요.");
        return value;
    }

    static String hash(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public void send(String email) {
        email = normalize(email);
        mailer.requireConfigured();
        String code = String.format("%06d", random.nextInt(1000000));
        String digest = hash(email + ":" + code);
        int issued = repository.issue(email, digest);
        if (issued == 0) throw new ApiException(429, "TOO_MANY_REQUESTS", "1분 후 다시 요청해 주세요.");
        try {
            mailer.send(email, code);
        } catch (MailException failure) {
            repository.deleteIssued(email, digest);
            throw new ApiException(503, "MAIL_DELIVERY_FAILED", "인증 메일을 보내지 못했어요. 잠시 후 다시 시도해 주세요.");
        }
    }

    public String verify(String email, String code) {
        email = normalize(email);
        var rows = repository.attempt(email);
        String digest = hash(email + ":" + code);
        if (rows.isEmpty() || !MessageDigest.isEqual(
                rows.getFirst().getBytes(StandardCharsets.UTF_8),
                digest.getBytes(StandardCharsets.UTF_8)))
            throw ApiException.invalid("인증번호가 틀렸거나 만료됐어요. 5회 실패하면 새 번호를 요청해 주세요.");
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String proof = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        int updated = repository.saveProof(email, digest, hash(proof));
        if (updated != 1) throw ApiException.invalid("인증번호를 다시 요청해 주세요.");
        return proof;
    }

    public void consume(String email, String proof) {
        if (proof == null || proof.isBlank()) throw ApiException.invalid("이메일 인증을 먼저 완료해 주세요.");
        int consumed = repository.consume(normalize(email), hash(proof));
        if (consumed != 1) throw ApiException.invalid("이메일 인증이 만료됐어요. 다시 인증해 주세요.");
    }
}
