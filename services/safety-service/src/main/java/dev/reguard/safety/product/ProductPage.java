package dev.reguard.safety.product;

import java.util.List;

public record ProductPage(
        List<Product> items,
        int page,
        int size,
        boolean hasNext
) {}
