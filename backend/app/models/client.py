import uuid

from sqlalchemy import Column, String, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base

class Client(Base):
    __tablename__ = "clients"

    __table_args__ = (
        UniqueConstraint(
            "freelancer_id",
            "email",
            name="uq_client_freelancer_email"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    freelancer_id = Column(String(100), nullable=False, index=True)

    name = Column(String(150), nullable=False)
    email = Column(String(200), nullable=False)
    company = Column(String(150))
    notes = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )