CREATE TABLE signup_email_verifications (
 email varchar(320) PRIMARY KEY,
 code_hash varchar(64) NOT NULL,
 expires_at timestamptz NOT NULL,
 sent_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 attempts integer NOT NULL DEFAULT 0,
 proof_hash varchar(64)
);
