import uuid

from sqlalchemy import Column, String, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    invoice_number = Column(String(30), unique=True, nullable=False)

    freelancer_id = Column(String(100), nullable=False)

    client_name = Column(String(150), nullable=False)
    client_email = Column(String(200), nullable=False)

    total = Column(Numeric(24, 8), nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    due_date = Column(DateTime(timezone=True))

    status = Column(String(20), default="PENDING", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan"
    )

    payment_attempts = relationship(
        "PaymentAttempt",
        back_populates="invoice"
    )