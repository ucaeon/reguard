-- URL metadata only: no image bytes or local filesystem paths.
CREATE TABLE recall_image_jobs (
    recall_id UUID PRIMARY KEY REFERENCES recalls(id) ON DELETE CASCADE,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','success','retry','not_found','identity_unconfirmed','failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ,
    checked_at TIMESTAMPTZ,
    last_error TEXT,
    images JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(images) = 'array'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX recall_image_jobs_due ON recall_image_jobs(next_attempt_at) WHERE status <> 'success';
CREATE TABLE recall_image_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recall_id UUID NOT NULL REFERENCES recall_image_jobs(recall_id) ON DELETE CASCADE,
    input_hash TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    outcome TEXT NOT NULL,
    error_code TEXT
);
CREATE INDEX recall_image_attempts_recall ON recall_image_attempts(recall_id, started_at DESC);
