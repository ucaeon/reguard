package dev.reguard.safety.recall;

import java.util.List;

public record RecallPage<T>(List<T> items, int page, int size, boolean hasNext) {}
