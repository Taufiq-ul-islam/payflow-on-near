import uuid

from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem


def create_invoice(db: Session, data, freelancer_id: str):
    if not data.items:
        raise ValueError("Invoice must contain at least one item")

    total = Decimal("0")

    for item in data.items:
        quantity = Decimal(str(item.quantity))
        unit_price = Decimal(str(item.unit_price))

        if quantity <= 0:
            raise ValueError("Item quantity must be positive")

        if unit_price < 0:
            raise ValueError("Item price cannot be negative")

        total += quantity * unit_price

    if total <= 0:
        raise ValueError("Invoice total must be positive")

    invoice = Invoice(
        invoice_number=f"PF-{uuid.uuid4().hex[:8].upper()}",
        freelancer_id=freelancer_id,
        client_name=data.client_name,
        client_email=str(data.client_email).lower(),
        total=total,
        due_date=data.due_date,
        currency="USD",
        status="PENDING"
    )

    invoice.items = [
        InvoiceItem(
            description=item.description.strip(),
            quantity=item.quantity,
            unit_price=item.unit_price
        )
        for item in data.items
    ]

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return invoice


def get_invoice(db: Session, invoice_id):
    return (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id)
        .first()
    )


def get_owned_invoice(db: Session, invoice_id, freelancer_id: str):
    return (
        db.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.freelancer_id == freelancer_id,
        )
        .first()
    )