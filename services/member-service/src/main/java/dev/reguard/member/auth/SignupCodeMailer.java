package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class SignupCodeMailer {
    private final JavaMailSender mail;
    private final String from;
    private final boolean enabled;

    public SignupCodeMailer(JavaMailSender mail,
            @Value("${reguard.mail.from:}") String from,
            @Value("${reguard.mail.enabled:false}") boolean enabled) {
        this.mail = mail;
        this.from = from;
        this.enabled = enabled;
    }

    public void requireConfigured() {
        if (!enabled || from.isBlank()) {
            throw new ApiException(503, "MAIL_NOT_CONFIGURED", "이메일 발송 설정이 아직 준비되지 않았습니다.");
        }
    }

    public void send(String email, String code) {
        requireConfigured();
        var message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(email);
        message.setSubject("[ReGuard] 회원가입 인증번호");
        message.setText("인증번호는 " + code + " 입니다. 10분 안에 입력해 주세요.\n본인이 요청하지 않았다면 이 메일을 무시하세요.");
        mail.send(message);
    }
}
