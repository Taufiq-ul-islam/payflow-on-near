from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    company: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(default=None, max_length=150)
    notes: Optional[str] = None


class ClientResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    company: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)