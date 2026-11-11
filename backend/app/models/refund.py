from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(UUID(as_uuid=True), primary_key=True)

    payment_attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    idempotency_key = Column(String(255), unique=True, nullable=True)

    destination_network = Column(String(100), nullable=False)
    destination_asset = Column(String(255), nullable=False)
    destination_address = Column(String(255), nullable=False)

    deposit_address = Column(String(255), nullable=True)
    deposit_memo = Column(String(255), nullable=True)

    requested_amount = Column(Numeric(24, 8), nullable=False)

    source_asset = Column(String(255), nullable=False)
    source_amount = Column(Numeric(24, 8), nullable=False)
    expected_amount = Column(Numeric(24, 8), nullable=False)
    received_amount = Column(Numeric(24, 8), nullable=True)

    quote_id = Column(String(255), nullable=True)
    quote_signature = Column(Text, nullable=True)
    quote_response = Column(JSONB, nullable=True)

    fee_details = Column(JSONB, nullable=True)

    provider_correlation_id = Column(String(255), nullable=True)
    provider_response = Column(JSONB, nullable=True)

    status = Column(
        String(40),
        nullable=False,
        default="AWAITING_APPROVAL",
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    payment_attempt = relationship("PaymentAttempt")

    transactions = relationship(
        "RefundTransaction",
        back_populates="refund",
    )


class RefundTransaction(Base):
    __tablename__ = "refund_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True)

    refund_id = Column(
        UUID(as_uuid=True),
        ForeignKey("refunds.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    chain = Column(String(100), nullable=False)
    tx_hash = Column(String(255), nullable=False, unique=True)

    transaction_type = Column(String(40), nullable=False)
    asset = Column(String(255), nullable=True)
    amount = Column(Numeric(24, 8), nullable=True)

    explorer_url = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    refund = relationship(
        "Refund",
        back_populates="transactions",
    )