CREATE INDEX IF NOT EXISTS ix_product_identifiers_lookup
    ON product_identifiers(identifier_type, identifier_value, product_id);
