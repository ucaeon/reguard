package dev.reguard.notification.inbox;

import java.util.List;

public final class NotificationData {
    private NotificationData() {}
    public record Page(
            List<Notification> items,
            int page,
            int size,
            boolean hasNext
    ) {}

    public record UnreadCount(
            long count
    ) {}

}
