package dev.reguard.member.auth;

import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1")
public class AuthController {
    public record Signup(
            @NotBlank @Size(max = 320) String email,
            @NotBlank @Size(max = 72) String password,
            @NotBlank @Size(max = 100) String displayName,
            @NotBlank @Size(max = 100) String verificationToken
    ) {}

    public record Login(
            @NotBlank @Size(max = 320) String email,
            @NotBlank @Size(max = 72) String password
    ) {}

    public record CookieLogin(
            String authentication,
            java.time.OffsetDateTime expiresAt
    ) {}

    public record EmailRequest(@NotBlank @Email @Size(max=320) String email) {}
    public record VerifyRequest(@NotBlank @Email @Size(max=320) String email, @NotBlank @Pattern(regexp="[0-9]{6}") String code) {}
    public record VerificationResult(String verificationToken) {}
    private final SignupVerification verification;
    private final AuthRequestLimits limits;
    private final AuthService service;
    private final LoginCookies cookies;
    private final CookieCsrfTokenRepository csrfTokens;

    public AuthController(
            AuthService service, LoginCookies cookies, CookieCsrfTokenRepository csrfTokens, SignupVerification verification, AuthRequestLimits limits) {
        this.service = service;
        this.limits = limits;
        this.verification = verification;
        this.cookies = cookies;
        this.csrfTokens = csrfTokens;
    }

    @PostMapping("/auth/signup")
    @ResponseStatus(HttpStatus.CREATED)
    public AuthService.User signup(@Valid @RequestBody Signup request) {
        return service.signup(request.email(), request.password(), request.displayName(), request.verificationToken());
    }

    @PostMapping("/auth/signup/email/request")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void sendCode(@Valid @RequestBody EmailRequest request) { verification.send(request.email()); }

    @PostMapping("/auth/signup/email/verify")
    public ResponseEntity<VerificationResult> verifyCode(@Valid @RequestBody VerifyRequest request) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(new VerificationResult(verification.verify(request.email(), request.code())));
    }

    @PostMapping("/auth/login")
    public ResponseEntity<CookieLogin> login(
            @Valid @RequestBody Login request,
            HttpServletRequest httpRequest,
            HttpServletResponse httpResponse) {
        limits.acquire("login-account", SignupVerification.normalize(request.email()), 10, 900);
        var token = service.login(request.email(), request.password());
        String previous = (String) httpRequest.getAttribute(SecurityConfig.AUTH_TOKEN);

        if (previous != null) service.logout(previous);
        cookies.issue(httpResponse, token);
        csrfTokens.saveToken(null, httpRequest, httpResponse);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new CookieLogin("COOKIE", token.expiresAt()));
    }

    @PostMapping("/auth/token")
    public ResponseEntity<AuthService.Token> token(@Valid @RequestBody Login request) {
        limits.acquire("login-account", SignupVerification.normalize(request.email()), 10, 900);
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(service.login(request.email(), request.password()));
    }

    @PostMapping("/auth/logout")
    public ResponseEntity<Void> logout(HttpServletRequest request, HttpServletResponse response) {
        service.logout((String) request.getAttribute(SecurityConfig.AUTH_TOKEN));
        cookies.clear(response);
        csrfTokens.saveToken(null, request, response);

        return ResponseEntity.noContent().cacheControl(CacheControl.noStore()).build();
    }

    @GetMapping("/me")
    public AuthService.User me(@AuthenticationPrincipal UUID userId) {
        return service.me(userId);
    }
}
