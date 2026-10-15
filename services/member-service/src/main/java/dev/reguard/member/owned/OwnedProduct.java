package dev.reguard.member.owned;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

public record OwnedProduct(
        UUID id,
        UUID catalogProductId,
        String registrationType,
        String productName,
        String companyName,
        String modelName,
        String identifierType,
        String identifierValue,
        LocalDate expiryDate,
        String lotNumber,
        OffsetDateTime createdAt
) {}
