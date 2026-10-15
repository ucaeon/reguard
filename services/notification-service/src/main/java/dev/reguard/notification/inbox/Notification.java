package dev.reguard.notification.inbox;

import java.time.OffsetDateTime;
import java.util.UUID;

public record Notification(
        UUID id,
        UUID ownedProductId,
        UUID recallId,
        long recallVersion,
        String notificationType,
        String title,
        String message,
        String eligibilityStatus,
        OffsetDateTime readAt,
        OffsetDateTime createdAt
) {}
