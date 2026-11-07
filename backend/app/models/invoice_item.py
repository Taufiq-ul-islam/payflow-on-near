from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False
    )

    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(12, 4), nullable=False)
    unit_price = Column(Numeric(24, 8), nullable=False)

    invoice = relationship("Invoice", back_populates="items")