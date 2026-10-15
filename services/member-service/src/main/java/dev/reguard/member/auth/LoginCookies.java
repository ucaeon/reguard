package dev.reguard.member.auth;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Component;

import java.time.*;

@Component
public class LoginCookies {
    private final boolean secure;

    public LoginCookies(@Value("${reguard.cookie.secure:false}") boolean secure) {
        this.secure = secure;
    }

    public void issue(HttpServletResponse response, AuthService.Token token) {
        response.addHeader(
                HttpHeaders.SET_COOKIE,
                cookie(
                                "REGUARD_SESSION", token.accessToken(),
                                Math.max(
                                        0,
                                        Duration.between(OffsetDateTime.now(), token.expiresAt())
                                                .toSeconds()))
                        .toString());
    }

    public void clear(HttpServletResponse response) {
        for (String name :
                new String[] {
                    "REGUARD_SESSION", "REGUARD_MEMBER_CSRF", "REGUARD_NOTIFICATION_CSRF"
                }) response.addHeader(HttpHeaders.SET_COOKIE, cookie(name, "", 0).toString());
    }

    private ResponseCookie cookie(String name, String value, long maxAge) {
        return ResponseCookie.from((secure ? "__Host-" : "") + name, value)
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .path("/")
                .maxAge(maxAge)
                .build();
    }
}
