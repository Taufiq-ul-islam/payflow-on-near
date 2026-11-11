ALTER TABLE refunds
    ADD COLUMN deposit_address VARCHAR(255),
    ADD COLUMN deposit_memo VARCHAR(255);