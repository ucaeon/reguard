CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE CHECK (btrim(email) <> ''),
    display_name VARCHAR(100) NOT NULL CHECK (btrim(display_name) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE owned_products (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    catalog_product_id UUID,
    registration_type VARCHAR(20) NOT NULL CHECK (registration_type IN ('CATALOG', 'MANUAL')),
    product_name VARCHAR(500) NOT NULL CHECK (btrim(product_name) <> ''),
    company_name VARCHAR(500),
    model_name VARCHAR(500),
    identifier_type VARCHAR(40),
    identifier_value VARCHAR(255),
    expiry_date DATE,
    lot_number VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_owned_registration CHECK (
        (registration_type = 'CATALOG' AND catalog_product_id IS NOT NULL)
        OR (registration_type = 'MANUAL' AND catalog_product_id IS NULL)
    ),
    CONSTRAINT ck_owned_identifier CHECK (
        (identifier_type IS NULL AND identifier_value IS NULL)
        OR (identifier_type IS NOT NULL AND identifier_value IS NOT NULL
            AND btrim(identifier_type) <> '' AND btrim(identifier_value) <> '')
    )
);
COMMENT ON COLUMN owned_products.catalog_product_id IS 'Logical reference to safety DB products.id; no cross-database FK';
COMMENT ON TABLE users IS 'Authentication method is not implemented; email normalization belongs to the application';
