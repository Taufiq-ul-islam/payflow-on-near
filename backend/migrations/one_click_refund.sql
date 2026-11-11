ALTER TABLE payment_attempts
    ADD COLUMN payer_address VARCHAR(255),
    ADD COLUMN payer_network VARCHAR(50),
    ADD COLUMN payer_asset VARCHAR(255),
    ADD COLUMN payer_asset_decimals INTEGER;