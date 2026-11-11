from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from redis_fastapi import rate_limit

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.auth_service import (
    create_challenge,
    authenticate_signature,
    get_user_for_session,
    revoke_session,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])

SESSION_COOKIE = "payflow_session"


class ChallengeRequest(BaseModel):
    account_id: str = Field(min_length=2, max_length=128)


class VerifyRequest(BaseModel):
    challenge_id: UUID
    account_id: str = Field(min_length=2, max_length=128)
    public_key: str = Field(min_length=20, max_length=128)
    signature: str = Field(min_length=40, max_length=256)


def current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user = get_user_for_session(db, request.cookies.get(SESSION_COOKIE))

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    return user


@router.post("/challenge", dependencies=[Depends(rate_limit("5/minute"))])
def issue_challenge(
    data: ChallengeRequest,
    db: Session = Depends(get_db),
):
    try:
        return create_challenge(db, data.account_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/verify", dependencies=[Depends(rate_limit("5/minute"))])
async def verify_wallet(
    data: VerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        user, token, expires_at = await authenticate_signature(
            db=db,
            challenge_id=data.challenge_id,
            account_id=data.account_id,
            public_key=data.public_key,
            signature=data.signature,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(401, str(exc))

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_days * 24 * 60 * 60,
        path="/",
    )

    return {
        "authenticated": True,
        "account_id": user.near_account_id,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/me")
def who_am_i(
    user: User = Depends(current_user),
):
    return {
        "authenticated": True,
        "account_id": user.near_account_id,
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    revoke_session(db, request.cookies.get(SESSION_COOKIE))

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )

    return {"authenticated": False}