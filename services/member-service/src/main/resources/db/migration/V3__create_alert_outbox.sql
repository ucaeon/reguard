CREATE TABLE alert_outbox (
    event_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    owned_product_id UUID NOT NULL,
    recall_id UUID NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ,
    CONSTRAINT uq_alert_outbox UNIQUE(owned_product_id,recall_id)
);
CREATE INDEX ix_alert_outbox_pending ON alert_outbox(created_at,event_id) WHERE sent_at IS NULL;
