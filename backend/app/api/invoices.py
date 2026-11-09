from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.invoice import InvoiceCreate
from app.services.invoice_service import create_invoice, get_invoice, get_owned_invoice
from app.api.auth import current_user

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
def create(
    data: InvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not user.near_account_id:
        raise HTTPException(
            status_code=400,
            detail="Your account has no linked NEAR account",
        )

    try:
        invoice = create_invoice(db, data, user.near_account_id)

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
            "currency": invoice.currency,
            "status": invoice.status,
            "payment_url": f"/pay/{invoice.id}",
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/")
def list_invoices(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    invoices = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .filter(Invoice.freelancer_id == user.near_account_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )

    return [serialize_invoice(invoice) for invoice in invoices]


# Public endpoint: used by the client-facing payment page.
@router.get("/{invoice_id}")
def retrieve(
    invoice_id: UUID,
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .filter(Invoice.id == invoice_id)
        .first()
    )

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return serialize_invoice(invoice)


# Private endpoint: used by the freelancer dashboard.
@router.get("/{invoice_id}/manage")
def retrieve_owned(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.items))
        .filter(
            Invoice.id == invoice_id,
            Invoice.freelancer_id == user.near_account_id,
        )
        .first()
    )

    if not invoice:
        # Do not disclose whether another freelancer owns this invoice.
        raise HTTPException(status_code=404, detail="Invoice not found")

    return serialize_invoice(invoice)