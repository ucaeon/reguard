def dimensions(quarantined, stale_sources, unmatched, matched_recalls):
    unmatched_count = sum(unmatched.values())
    total = matched_recalls + unmatched_count
    return {
        "freshness": {"status": "failed" if stale_sources else "passed", "stale_sources": stale_sources},
        "ingestion": {"status": "failed" if quarantined else "passed", "quarantined_24h": quarantined},
        "matching": {
            "status": "needs_review" if unmatched_count else "passed",
            "matched_recalls": matched_recalls,
            "unmatched_recalls": unmatched_count,
            "coverage": round(matched_recalls / total, 4) if total else None,
        },
    }
