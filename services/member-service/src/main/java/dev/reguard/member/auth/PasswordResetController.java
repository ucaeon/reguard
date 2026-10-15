package dev.reguard.member.auth;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth/password-reset")
public class PasswordResetController {
    public record Request(
            @NotBlank @Email @Size(max = 320) String email
    ) {}

    public record Confirm(
            @NotBlank @Size(max = 100) String token,
            @NotBlank @Size(max = 72) String newPassword
    ) {}

    public record Accepted(
            String message
    ) {}

    private final PasswordResetService service;

    public PasswordResetController(PasswordResetService service) {
        this.service = service;
    }

    @PostMapping("/request")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Accepted request(@Valid @RequestBody Request body) {
        service.request(body.email());

        return new Accepted("등록된 이메일이면 비밀번호 재설정 안내를 발송합니다.");
    }

    @PostMapping("/confirm")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void confirm(@Valid @RequestBody Confirm body) {
        service.confirm(body.token(), body.newPassword());
    }
}
