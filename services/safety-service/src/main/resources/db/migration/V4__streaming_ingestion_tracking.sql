CREATE TABLE ingestion_events (
    event_id UUID PRIMARY KEY,
    content_hash TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE ingestion_offsets (
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    offset_id BIGINT NOT NULL,
    PRIMARY KEY(topic, partition_id, offset_id)
);
CREATE TABLE ingestion_quarantine (
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    offset_id BIGINT NOT NULL,
    raw_message TEXT,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(topic, partition_id, offset_id)
);
CREATE TABLE ingestion_source_state (
    source VARCHAR(40) NOT NULL,
    source_record_id VARCHAR(255) NOT NULL,
    version_at TIMESTAMPTZ NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    PRIMARY KEY(source, source_record_id)
);
CREATE TABLE ingestion_batches (
    query_id TEXT NOT NULL,
    batch_id BIGINT NOT NULL,
    metrics JSONB NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(query_id,batch_id)
);
