CREATE TABLE auth_request_limits (
    bucket_hash CHAR(64) PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_auth_request_limits_expiry ON auth_request_limits(expires_at);
