from pathlib import Path

RULES = (
    (frozenset({"FOOD_I1250", "FOOD_I0030", "FOOD_I0490"}), "food_matching.sql"),
    (frozenset({"SAFETY_KC", "SAFETY_RECALL"}), "kc_matching.sql"),
)


def match_sources(cursor, changed_sources, product_ids=None, recall_ids=None):
    """Run affected rules in the caller's ingestion transaction."""
    if not changed_sources:
        return []
    cursor.execute("CREATE TEMP TABLE matching_scope(recall_id uuid PRIMARY KEY) ON COMMIT DROP")
    if product_ids is None and recall_ids is None:
        cursor.execute("INSERT INTO matching_scope SELECT id FROM recalls")
    else:
        cursor.execute("INSERT INTO matching_scope SELECT unnest(%s::uuid[]) ON CONFLICT DO NOTHING",
                       (list(recall_ids or ()),))
        cursor.execute("CREATE TEMP TABLE changed_matching_products(product_id uuid PRIMARY KEY) ON COMMIT DROP")
        cursor.execute("INSERT INTO changed_matching_products SELECT unnest(%s::uuid[])",
                       (list(product_ids or ()),))
        cursor.execute("ANALYZE changed_matching_products")
        recall_sources = []
        if RULES[0][0].intersection(changed_sources):
            recall_sources.append("FOOD_I0490")
        if RULES[1][0].intersection(changed_sources):
            recall_sources.append("SAFETY_RECALL")
        cursor.execute(Path(__file__).with_name("matching_scope.sql").read_text(),
                       (recall_sources,))
        scope = cursor.execute("SELECT EXISTS(SELECT 1 FROM matching_scope)").fetchone()
        if not scope[0]:
            return []
    cursor.execute("ANALYZE matching_scope")
    executed = []
    for sources, filename in RULES:
        if sources.intersection(changed_sources):
            cursor.execute(Path(__file__).with_name(filename).read_text())
            executed.append(filename)
    return executed
