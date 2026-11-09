BEGIN;

ALTER TABLE invoices
    ADD COLUMN paid_payment_attempt_id UUID NULL,
    ADD COLUMN paid_at TIMESTAMPTZ NULL;

CREATE INDEX idx_invoices_paid_payment_attempt
    ON invoices (paid_payment_attempt_id)
    WHERE paid_payment_attempt_id IS NOT NULL;

COMMIT;