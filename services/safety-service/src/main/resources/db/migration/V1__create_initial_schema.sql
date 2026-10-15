CREATE TABLE products (
    id UUID PRIMARY KEY,
    source VARCHAR(40) NOT NULL CHECK (btrim(source) <> ''),
    source_record_id VARCHAR(255) NOT NULL CHECK (btrim(source_record_id) <> ''),
    name VARCHAR(500) NOT NULL CHECK (btrim(name) <> ''),
    company_name VARCHAR(500),
    category VARCHAR(40) NOT NULL CHECK (btrim(category) <> ''),
    model_name VARCHAR(500),
    image_url TEXT,
    source_updated_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_products_source UNIQUE (source, source_record_id)
);
CREATE TABLE product_identifiers (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id),
    identifier_type VARCHAR(40) NOT NULL CHECK (btrim(identifier_type) <> ''),
    identifier_value VARCHAR(255) NOT NULL CHECK (btrim(identifier_value) <> ''),
    CONSTRAINT uq_product_identifier UNIQUE (product_id, identifier_type, identifier_value)
);
CREATE TABLE recalls (
    id UUID PRIMARY KEY,
    source VARCHAR(40) NOT NULL CHECK (btrim(source) <> ''),
    source_recall_id VARCHAR(255) NOT NULL CHECK (btrim(source_recall_id) <> ''),
    product_name VARCHAR(500) NOT NULL CHECK (btrim(product_name) <> ''),
    company_name VARCHAR(500),
    reason TEXT,
    action_method TEXT,
    target_conditions TEXT,
    source_url TEXT,
    source_created_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload JSONB NOT NULL CHECK (jsonb_typeof(raw_payload) = 'object'),
    CONSTRAINT uq_recalls_source UNIQUE (source, source_recall_id)
);
CREATE TABLE recall_product_matches (
    id UUID PRIMARY KEY,
    recall_id UUID NOT NULL REFERENCES recalls(id),
    product_id UUID NOT NULL REFERENCES products(id),
    match_method VARCHAR(40) NOT NULL CHECK (btrim(match_method) <> ''),
    match_status VARCHAR(30) NOT NULL CHECK (match_status IN ('CONFIRMED', 'CANDIDATE')),
    rule_version VARCHAR(40) NOT NULL CHECK (btrim(rule_version) <> ''),
    matched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_recall_product UNIQUE (recall_id, product_id)
);
COMMENT ON TABLE recall_product_matches IS 'Product identity match; CONFIRMED does not establish lot/expiry recall eligibility';
COMMENT ON COLUMN products.source_record_id IS 'Stable source record key; KC key must be verified against real API responses';
