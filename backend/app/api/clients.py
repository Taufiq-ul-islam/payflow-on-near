from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from app.services.client_service import (
    list_clients,
    get_client,
    create_client,
    update_client,
    delete_client,
)
from app.api.auth import current_user

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("/", response_model=list[ClientResponse])
def get_clients(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return list_clients(db, user.near_account_id)


@router.post("/", response_model=ClientResponse, status_code=201)
def add_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        return create_client(db, user.near_account_id, data)

    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A client with this email already exists",
        )


@router.get("/{client_id}", response_model=ClientResponse)
def retrieve_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    client = get_client(db, client_id, user.near_account_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client


@router.patch("/{client_id}", response_model=ClientResponse)
def edit_client(
    client_id: UUID,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    client = get_client(db, client_id, user.near_account_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        return update_client(db, client, data)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A client with this email already exists",
        )


@router.delete("/{client_id}", status_code=204)
def remove_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    client = get_client(db, client_id, user.near_account_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    delete_client(db, client)
    return None