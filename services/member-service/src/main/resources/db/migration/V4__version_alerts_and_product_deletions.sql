ALTER TABLE alert_outbox ADD COLUMN event_type VARCHAR(40) NOT NULL DEFAULT 'RECALL_MATCH';
ALTER TABLE alert_outbox ADD COLUMN recall_version BIGINT NOT NULL DEFAULT 1;
ALTER TABLE alert_outbox ALTER COLUMN recall_id DROP NOT NULL;
ALTER TABLE alert_outbox DROP CONSTRAINT uq_alert_outbox;
ALTER TABLE alert_outbox ADD CONSTRAINT uq_alert_outbox_revision
    UNIQUE NULLS NOT DISTINCT(owned_product_id,recall_id,event_type,recall_version);
