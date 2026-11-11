BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_refunds_cross_chain_quote_metadata'
          AND conrelid = 'public.refunds'::regclass
    ) THEN
        ALTER TABLE public.refunds
        ADD CONSTRAINT ck_refunds_cross_chain_quote_metadata
        CHECK (
            lower(btrim(destination_network)) = 'near'
            OR (
                quote_signature IS NOT NULL
                AND btrim(quote_signature) <> ''
                AND provider_correlation_id IS NOT NULL
                AND btrim(provider_correlation_id) <> ''
            )
        );
    END IF;
END
$$;

COMMENT ON CONSTRAINT ck_refunds_cross_chain_quote_metadata
ON public.refunds IS
'Cross-chain refunds must persist Tidepool quote signature and provider correlation ID; direct NEAR refunds do not require quote metadata.';

COMMIT;