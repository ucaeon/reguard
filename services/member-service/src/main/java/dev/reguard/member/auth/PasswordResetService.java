package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;

import org.slf4j.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.*;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.util.Locale;

@Service
public class PasswordResetService {
    private static final Logger log = LoggerFactory.getLogger(PasswordResetService.class);
    private final PasswordResetTokens tokens;
    private final AuthRequestLimits limits;
    private final JavaMailSender mail;
    private final String from;
    private final String resetUrl;
    private final boolean enabled;

    public PasswordResetService(
            PasswordResetTokens tokens,
            AuthRequestLimits limits,
            JavaMailSender mail,
            @Value("${reguard.mail.from:}") String from,
            @Value("${reguard.mail.enabled:false}") boolean enabled,
            @Value("${reguard.password-reset-url:http://localhost:3000/reset-password}")
                    String resetUrl) {
        this.tokens = tokens;
        this.limits = limits;
        this.mail = mail;
        this.from = from;
        this.enabled = enabled;
        this.resetUrl = resetUrl;
    }

    public void request(String email) {
        if (!enabled || from.isBlank())
            throw new ApiException(503, "MAIL_NOT_CONFIGURED", "이메일 발송 설정이 아직 준비되지 않았습니다.");
        String normalized = email.strip().toLowerCase(Locale.ROOT);
        limits.acquire("reset-account-minute", normalized, 1, 60);
        limits.acquire("reset-account-hour", normalized, 5, 3600);
        var issued = tokens.issue(normalized);

        if (issued.isEmpty()) return;
        var reset = issued.get();
        var message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(reset.email());
        message.setSubject("[ReGuard] 비밀번호 재설정");
        String link = resetUrl + (resetUrl.contains("?") ? "&" : "?") + "token=" + reset.token();
        message.setText(
                "비밀번호 재설정 링크입니다. 30분 이내에 한 번 사용할 수 있습니다.\n\n"
                        + link
                        + "\n\n요청하지 않았다면 이 메일을 무시하세요. 비밀번호는 변경되지 않습니다.");
        try {
            mail.send(message);
        } catch (MailException e) {
            tokens.revoke(reset.token());
            log.warn("Password reset mail delivery failed: {}", e.getClass().getSimpleName());
        }
    }

    public void confirm(String token, String password) {
        tokens.reset(token, password);
    }
}
