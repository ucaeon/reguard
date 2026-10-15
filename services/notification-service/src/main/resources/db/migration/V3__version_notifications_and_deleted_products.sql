ALTER TABLE notifications ADD COLUMN recall_version BIGINT NOT NULL DEFAULT 1;
ALTER TABLE notifications DROP CONSTRAINT uq_notification_dedup;
ALTER TABLE notifications ADD CONSTRAINT uq_notification_revision
    UNIQUE(owned_product_id,recall_id,notification_type,recall_version);
CREATE TABLE deleted_owned_products (
    owned_product_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
