package dev.reguard.safety.recall;

import java.time.OffsetDateTime;
import java.util.UUID;

public record Recall(
        UUID id,
        String source,
        String productName,
        String companyName,
        String reason,
        String actionMethod,
        String targetConditions,
        String sourceUrl,
        String imageUrl,
        OffsetDateTime sourceCreatedAt
) {}
