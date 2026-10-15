package dev.reguard.notification.auth;

import org.springframework.http.*;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

@RestController
public class CsrfController {
    public record Token(
            String headerName,
            String token
    ) {}

    @GetMapping("/api/v1/me/notifications/csrf")
    public ResponseEntity<Token> csrf(CsrfToken token) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Token(token.getHeaderName(), token.getToken()));
    }
}
