import uuid

from sqlalchemy import Integer, Column, String, DateTime, ForeignKey, Boolean, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_payment_attempt_idempotency_key",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id"),
        nullable=False,
        index=True,
    )

    idempotency_key = Column(String(128), nullable=True)

    quote_id = Column(String(150))
    quote_signature = Column(String)
    quote_response = Column(JSON, nullable=False)

    deposit_address = Column(String(255), unique=True, nullable=False)
    deposit_memo = Column(String(255))

    source_asset = Column(String(255), nullable=False)
    destination_asset = Column(String(255), nullable=False)

    expected_input_amount = Column(String(100))
    expected_amount = Column(String(100), nullable=False)
    received_amount = Column(String(100))

    refund_address = Column(String(255))

    payer_address = Column(String(255), nullable=True)
    payer_network = Column(String(50), nullable=True)
    payer_asset = Column(String(255), nullable=True)
    payer_asset_decimals = Column(Integer, nullable=True)

    status = Column(
        String(40),
        default="PENDING_DEPOSIT",
        nullable=False,
        index=True,
    )

    provider_correlation_id = Column(String(150))
    provider_response = Column(JSON)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )

    invoice = relationship("Invoice", back_populates="payment_attempts")

    transactions = relationship(
        "Transaction",
        back_populates="payment_attempt",
        cascade="all, delete-orphan",
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    payment_attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payment_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chain = Column(String(50))
    tx_hash = Column(String(255), nullable=False, unique=True)
    transaction_type = Column(String(30), nullable=False)
    amount = Column(String(100))

    explorer_url = Column(String(500))

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    payment_attempt = relationship(
        "PaymentAttempt",
        back_populates="transactions",
    )