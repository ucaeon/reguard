package dev.reguard.notification.inbox;

import dev.reguard.notification.api.ApiException;
import org.springframework.stereotype.Service;
import java.util.*;
import dev.reguard.notification.inbox.NotificationData.Page;
import dev.reguard.notification.inbox.NotificationData.UnreadCount;

@Service
public class NotificationService {
    private final NotificationRepository repository;
    public NotificationService(NotificationRepository repository) { this.repository = repository; }
    public Page list(
            UUID user,
            int page,
            int size) {
        if (page < 0 || size < 1 || size > 100)
            throw ApiException.invalid("page는 0 이상, size는 1~100이어야 합니다.");
        var rows = repository.list(user, (long) page * size, size + 1);

        return new Page(
                List.copyOf(rows.subList(0, Math.min(rows.size(), size))),
                page,
                size,
                rows.size() > size);
    }

    public UnreadCount unread(UUID user) {
        return new UnreadCount(repository.unread(user));
    }

    public Notification read(
            UUID user, UUID notificationId) {
        return repository.read(user, notificationId);
    }
}
