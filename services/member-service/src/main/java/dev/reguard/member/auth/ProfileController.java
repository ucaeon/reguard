package dev.reguard.member.auth;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import java.util.*;
import static dev.reguard.member.auth.ProfileData.*;

@RestController
@RequestMapping("/api/v1/me/profile")
public class ProfileController {
    private final ProfileService service;
    public ProfileController(ProfileService service) { this.service = service; }
    @GetMapping
    public Profile get(@AuthenticationPrincipal UUID user) { return service.get(user); }
    @PutMapping
    public Profile update(@AuthenticationPrincipal UUID user, @RequestBody Update request) { return service.update(user, request); }
    @PostMapping("/password")
    public Map<String, String> password(@AuthenticationPrincipal UUID user, @RequestBody PasswordChange request) {
        service.password(user, request);
        return Map.of("message", "비밀번호를 변경했어요. 다시 로그인해 주세요.");
    }
}
