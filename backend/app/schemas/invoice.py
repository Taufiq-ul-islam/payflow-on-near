from pydantic import BaseModel, EmailStr
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


class InvoiceItemCreate(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal


class InvoiceCreate(BaseModel):
    client_name: str
    client_email: EmailStr
    due_date: Optional[datetime] = None
    items: List[InvoiceItemCreate]


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    total: Decimal
    currency: str
    status: str

    class Config:
        from_attributes = True