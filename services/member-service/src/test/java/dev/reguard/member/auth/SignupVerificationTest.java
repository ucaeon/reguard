package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.mail.javamail.JavaMailSender;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class SignupVerificationTest {
    final NamedParameterJdbcTemplate jdbc = mock(NamedParameterJdbcTemplate.class);
    final JavaMailSender mail = mock(JavaMailSender.class);
    final SignupVerification service = new SignupVerification(new SignupVerificationRepository(jdbc), new SignupCodeMailer(mail, "test@example.com", true));
    @Test void requiresProofBeforeSignup() {
        assertThrows(ApiException.class, () -> service.consume("test@example.com", null));
        verifyNoInteractions(jdbc);
    }
    @Test void rejectsExpiredOrUsedProof() {
        when(jdbc.update(anyString(), anyMap())).thenReturn(0);
        assertThrows(ApiException.class, () -> service.consume("test@example.com", "old-proof"));
    }
    @Test void rejectsExpiredCode() {
        when(jdbc.queryForList(anyString(), anyMap(), eq(String.class))).thenReturn(List.of());
        assertThrows(ApiException.class, () -> service.verify("test@example.com", "123456"));
        verify(jdbc, never()).update(anyString(), anyMap());
    }
    @Test void rejectsWrongCode() {
        when(jdbc.queryForList(anyString(), anyMap(), eq(String.class))).thenReturn(List.of(SignupVerification.hash("test@example.com:654321")));
        assertThrows(ApiException.class, () -> service.verify("test@example.com", "123456"));
        verify(jdbc, never()).update(anyString(), anyMap());
    }
    @Test void returnsProofOnlyAfterValidCode() {
        when(jdbc.queryForList(anyString(), anyMap(), eq(String.class))).thenReturn(List.of(SignupVerification.hash("test@example.com:123456")));
        when(jdbc.update(anyString(), anyMap())).thenReturn(1);
        assertEquals(43, service.verify(" TEST@example.com ", "123456").length());
    }
    @Test void refusesSendWhenMailIsNotConfigured() {
        var disabled = new SignupVerification(new SignupVerificationRepository(jdbc), new SignupCodeMailer(mail, "", false));
        assertThrows(ApiException.class, () -> disabled.send("test@example.com"));
        verifyNoInteractions(jdbc, mail);
    }
    @Test void deliveryFailureRemovesOnlyIssuedCode() {
        when(jdbc.update(anyString(), anyMap())).thenReturn(1);
        doThrow(new org.springframework.mail.MailSendException("unavailable"))
                .when(mail).send(any(org.springframework.mail.SimpleMailMessage.class));
        assertThrows(ApiException.class, () -> service.send("test@example.com"));
        verify(jdbc).update(startsWith("DELETE FROM signup_email_verifications WHERE email=:email AND code_hash=:hash"), anyMap());
    }

    @Test void throttledRequestDoesNotSendMail() {
        when(jdbc.update(anyString(), anyMap())).thenReturn(0);
        assertThrows(ApiException.class, () -> service.send("test@example.com"));
        verifyNoInteractions(mail);
    }
}
