from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.csv_service import export_invoices

import io

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/invoices/{freelancer_id}/csv")
def download_csv(
    freelancer_id: str,
    db: Session = Depends(get_db)
):

    csv_data = export_invoices(db, freelancer_id)

    return StreamingResponse(
        io.BytesIO(csv_data.encode("utf-8-sig")),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=payflow_invoices.csv"
        }
    )