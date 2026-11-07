from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.invoice import InvoiceCreate
from app.services.invoice_service import (
    create_invoice,
    get_invoice
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.post("/")
def create(data: InvoiceCreate, db: Session = Depends(get_db)):

    try:
        invoice = create_invoice(db, data)

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
            "status": invoice.status,
            "payment_url": f"/pay/{invoice.id}"
        }

    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{invoice_id}")
def retrieve(invoice_id: str, db: Session = Depends(get_db)):

    invoice = get_invoice(db, invoice_id)

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "client_name": invoice.client_name,
        "total": str(invoice.total),
        "currency": invoice.currency,
        "status": invoice.status,
        "due_date": invoice.due_date,
        "items": [
            {
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price)
            }
            for item in invoice.items
        ]
    }