package dev.reguard.safety.recall;

public record ProductRecall(
        Recall recall,
        long recallVersion,
        String matchStatus,
        String matchMethod,
        String ruleVersion,
        String eligibilityStatus
) {}
