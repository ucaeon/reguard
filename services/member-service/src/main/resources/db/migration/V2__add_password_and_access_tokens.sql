-- Existing accounts cannot log in until credentials are established.
ALTER TABLE users ADD COLUMN password_hash VARCHAR(100);
CREATE UNIQUE INDEX uq_users_normalized_email ON users (lower(btrim(email)));
CREATE TABLE access_tokens (
    token_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_access_tokens_expiry ON access_tokens(expires_at);
CREATE INDEX ix_owned_products_user_created ON owned_products(user_id, created_at DESC, id);
