import csv
import io

from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.payment import PaymentAttempt


def export_invoices(db: Session, freelancer_id: str):

    invoices = (
        db.query(Invoice)
        .filter(Invoice.freelancer_id == freelancer_id)
        .all()
    )

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Invoice Number",
        "Client",
        "Invoice Date",
        "Due Date",
        "Invoice Amount",
        "Currency",
        "Invoice Status",
        "Payment Source Asset",
        "Payment Status",
        "Received USDC",
        "Destination",
        "Deposit Address"
    ])

    for invoice in invoices:

        attempts = (
            db.query(PaymentAttempt)
            .filter(PaymentAttempt.invoice_id == invoice.id)
            .all()
        )

        if not attempts:
            attempts = [None]

        for attempt in attempts:

            writer.writerow([
                invoice.invoice_number,
                invoice.client_name,
                invoice.created_at,
                invoice.due_date,
                str(invoice.total),
                invoice.currency,
                invoice.status,
                attempt.source_asset if attempt else "",
                attempt.status if attempt else "",
                str(attempt.received_amount or "")
                if attempt else "",
                "NEAR",
                attempt.deposit_address if attempt else ""
            ])

    return output.getvalue()