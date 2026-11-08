from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.invoice import Invoice
from app.schemas.invoice import InvoiceCreate
from app.services.invoice_service import create_invoice, get_invoice

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def serialize_invoice(invoice):
    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "freelancer_id": invoice.freelancer_id,
        "client_name": invoice.client_name,
        "client_email": invoice.client_email,
        "total": str(invoice.total),
        "currency": invoice.currency,
        "status": invoice.status,
        "due_date": invoice.due_date,
        "created_at": invoice.created_at,
        "payment_url": f"/pay/{invoice.id}",
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
            }
            for item in invoice.items
        ],
    }


@router.post("/")
def create(data: InvoiceCreate, db: Session = Depends(get_db)):
    try:
        invoice = create_invoice(db, data)

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
            "currency": invoice.currency,
            "status": invoice.status,
            "payment_url": f"/pay/{invoice.id}",
        }

    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/")
def list_invoices(
    freelancer_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    invoices = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .filter(Invoice.freelancer_id == freelancer_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )

    return [serialize_invoice(invoice) for invoice in invoices]


@router.get("/{invoice_id}")
def retrieve(invoice_id: UUID, db: Session = Depends(get_db)):
    invoice = get_invoice(db, invoice_id)

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    return serialize_invoice(invoice)