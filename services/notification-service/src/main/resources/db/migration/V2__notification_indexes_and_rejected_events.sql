CREATE INDEX ix_notifications_user_created ON notifications(user_id,created_at DESC,id);
CREATE INDEX ix_notifications_user_unread ON notifications(user_id) WHERE read_at IS NULL;
CREATE TABLE rejected_notification_events (
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    offset_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    payload TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(topic, partition_id, offset_id)
);
