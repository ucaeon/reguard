CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    owned_product_id UUID NOT NULL,
    recall_id UUID NOT NULL,
    notification_type VARCHAR(40) NOT NULL CHECK (btrim(notification_type) <> ''),
    title VARCHAR(500) NOT NULL CHECK (btrim(title) <> ''),
    message TEXT NOT NULL CHECK (btrim(message) <> ''),
    eligibility_status VARCHAR(40) NOT NULL DEFAULT 'NEEDS_CHECK'
        CHECK (eligibility_status IN ('NEEDS_CHECK', 'USER_CONFIRMED', 'USER_EXCLUDED')),
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_notification_dedup UNIQUE (owned_product_id, recall_id, notification_type)
);
COMMENT ON TABLE notifications IS 'User, owned product and recall IDs are logical references to other services, not physical FKs';
