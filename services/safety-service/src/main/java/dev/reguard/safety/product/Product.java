package dev.reguard.safety.product;

import java.util.List;
import java.util.UUID;

public record Product(
        UUID id,
        String name,
        String companyName,
        String category,
        String modelName,
        String imageUrl,
        List<Identifier> identifiers
) {
    public record Identifier(
            String type,
            String value
    ) {}
}
