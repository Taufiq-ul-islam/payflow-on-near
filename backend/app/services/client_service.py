from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate


def list_clients(db: Session, freelancer_id: str):
    return (
        db.query(Client)
        .filter(Client.freelancer_id == freelancer_id)
        .order_by(Client.created_at.desc())
        .all()
    )


def get_client(db: Session, client_id: UUID, freelancer_id: str):
    return (
        db.query(Client)
        .filter(
            Client.id == client_id,
            Client.freelancer_id == freelancer_id
        )
        .first()
    )


def create_client(
    db: Session,
    freelancer_id: str,
    data: ClientCreate
):
    existing = (
        db.query(Client)
        .filter(
            Client.freelancer_id == freelancer_id,
            Client.email == str(data.email).lower()
        )
        .first()
    )

    if existing:
        raise ValueError("A client with this email already exists")

    client = Client(
        freelancer_id=freelancer_id,
        name=data.name.strip(),
        email=str(data.email).lower(),
        company=data.company,
        notes=data.notes
    )

    db.add(client)
    db.commit()
    db.refresh(client)

    return client


def update_client(
    db: Session,
    client: Client,
    data: ClientUpdate
):
    updates = data.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

    if "email" in updates and updates["email"] is not None:
        updates["email"] = str(updates["email"]).lower()

    for field, value in updates.items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)

    return client


def delete_client(db: Session, client: Client):
    db.delete(client)
    db.commit()