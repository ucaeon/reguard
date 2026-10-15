package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static dev.reguard.member.auth.ProfileData.*;

@Service
public class ProfileService {
    private final ProfileRepository repository;
    private final PasswordEncoder encoder;
    public ProfileService(ProfileRepository repository, PasswordEncoder encoder) {
        this.repository = repository; this.encoder = encoder;
    }
    public Profile get(UUID user) {
        var stored = repository.find(user);
        return new Profile(stored.email(), stored.displayName(), stored.photo() == null ? null :
                "data:image/png;base64," + Base64.getEncoder().encodeToString(stored.photo()));
    }
    @Transactional
    public Profile update(UUID user, Update request) {
        String name = request.displayName();
        if (name == null || name.isBlank() || name.trim().length() > 100 || name.indexOf(0) >= 0)
            throw ApiException.invalid("닉네임은 1~100자로 입력해 주세요.");
        byte[] photo = ProfilePhoto.normalize(request.photo());
        repository.update(user, name.trim(), photo);
        return get(user);
    }
    @Transactional
    public void password(UUID user, PasswordChange request) {
        if (request.currentPassword() == null || request.currentPassword().getBytes(StandardCharsets.UTF_8).length > 72
                || request.newPassword() == null || request.newPassword().length() < 8
                || request.newPassword().getBytes(StandardCharsets.UTF_8).length > 72)
            throw ApiException.invalid("새 비밀번호는 8자 이상, 72바이트 이하로 입력해 주세요.");
        String hash = repository.lockPassword(user);
        if (hash == null || !encoder.matches(request.currentPassword(), hash))
            throw ApiException.invalid("현재 비밀번호가 일치하지 않아요.");
        repository.changePassword(user, encoder.encode(request.newPassword()));
    }
}
