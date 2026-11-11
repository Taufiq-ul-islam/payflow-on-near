BEGIN;

CREATE TABLE refunds (
    id UUID PRIMARY KEY,

    payment_attempt_id UUID NOT NULL
        REFERENCES payment_attempts(id) ON DELETE RESTRICT,

    idempotency_key VARCHAR(255) UNIQUE,

    -- Refund destination
    destination_network VARCHAR(100) NOT NULL,
    destination_asset VARCHAR(255) NOT NULL,
    destination_address VARCHAR(255) NOT NULL,

    -- Refund amounts, denominated in the relevant asset
    requested_amount NUMERIC(24, 8) NOT NULL
        CHECK (requested_amount > 0),

    source_asset VARCHAR(255) NOT NULL,
    source_amount NUMERIC(24, 8) NOT NULL
        CHECK (source_amount > 0),

    expected_amount NUMERIC(24, 8) NOT NULL
        CHECK (expected_amount > 0),

    received_amount NUMERIC(24, 8),

    -- Quote and provider information
    quote_id VARCHAR(255),
    quote_signature TEXT,
    quote_response JSONB,

    fee_details JSONB,

    provider_correlation_id VARCHAR(255),
    provider_response JSONB,

    status VARCHAR(40) NOT NULL DEFAULT 'AWAITING_APPROVAL',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_refunds_payment_attempt
    ON refunds(payment_attempt_id);

CREATE INDEX idx_refunds_status
    ON refunds(status);

CREATE TABLE refund_transactions (
    id UUID PRIMARY KEY,

    refund_id UUID NOT NULL
        REFERENCES refunds(id) ON DELETE RESTRICT,

    chain VARCHAR(100) NOT NULL,
    tx_hash VARCHAR(255) NOT NULL UNIQUE,

    transaction_type VARCHAR(40) NOT NULL,
    asset VARCHAR(255),
    amount NUMERIC(24, 8),

    explorer_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refund_transactions_refund
    ON refund_transactions(refund_id);

COMMIT;