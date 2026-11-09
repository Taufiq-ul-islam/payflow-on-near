import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.services.csv_service import export_invoices
from app.api.auth import current_user

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/invoices/csv")
def download_csv(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    csv_data = export_invoices(db, user.near_account_id)

    return StreamingResponse(
        io.BytesIO(csv_data.encode("utf-8-sig")),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=payflow_invoices.csv"
        },
    )