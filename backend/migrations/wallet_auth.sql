ALTER TABLE users
    ALTER COLUMN email DROP NOT NULL;

ALTER TABLE users
    ALTER COLUMN password_hash DROP NOT NULL;


CREATE TABLE IF NOT EXISTS auth_challenges (
    id UUID PRIMARY KEY,
    account_id VARCHAR(128) NOT NULL,
    message VARCHAR(1000) NOT NULL,
    nonce VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_auth_challenges_account_id
    ON auth_challenges(account_id);


CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id
    ON user_sessions(user_id);

CREATE INDEX IF NOT EXISTS ix_user_sessions_token_hash
    ON user_sessions(token_hash);