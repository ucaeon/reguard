package dev.reguard.member.auth;

import dev.reguard.member.api.ApiException;
import org.springframework.stereotype.Service;
import java.util.UUID;

@Service
public class NotificationPreferenceService {
    private final NotificationPreferenceRepository repository;
    public NotificationPreferenceService(NotificationPreferenceRepository repository) { this.repository = repository; }
    public boolean get(UUID user) { return repository.get(user); }
    public boolean save(UUID user, Boolean enabled) {
        if (enabled == null) throw ApiException.invalid("알림 수신 여부를 선택해 주세요.");
        return repository.save(user, enabled);
    }
}
