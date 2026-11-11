import base64
import hashlib
import secrets

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    ACCOUNT_ID_RE,
    auth_recipient,
    auth_callback_url,
    is_full_access_key,
    verify_nep413_signature,
)
from app.models.auth import AuthChallenge, UserSession
from app.models.user import User


CHALLENGE_MINUTES = 5


def create_challenge(db: Session, account_id: str):
    account_id = account_id.strip().lower()

    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise ValueError("Invalid NEAR account ID")

    nonce = base64.b64encode(secrets.token_bytes(32)).decode("ascii")

    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=CHALLENGE_MINUTES)

    message = (
        "Sign in to PayFlow\n\n"
        f"Account: {account_id}\n"
        f"Issued At: {issued.isoformat()}\n"
        f"Expires At: {expires.isoformat()}\n"
        "This signature is only for authentication. "
        "It does not authorize a transaction."
    )

    challenge = AuthChallenge(
        account_id=account_id,
        message=message,
        nonce=nonce,
        expires_at=expires,
    )

    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    return {
        "challenge_id": str(challenge.id),
        "account_id": account_id,
        "message": message,
        "nonce": nonce,
        "recipient": auth_recipient(),
        "callback_url": auth_callback_url(),
        "expires_at": expires.isoformat(),
    }


async def authenticate_signature(
    db: Session,
    challenge_id: UUID,
    account_id: str,
    public_key: str,
    signature: str,
):
    challenge = (
        db.query(AuthChallenge)
        .filter(AuthChallenge.id == challenge_id)
        .with_for_update()
        .first()
    )

    now = datetime.now(timezone.utc)

    if not challenge:
        raise ValueError("Invalid authentication challenge")

    if challenge.consumed_at:
        raise ValueError("Challenge has already been used")

    expires_at = challenge.expires_at

    # Handle databases that return naive timestamps.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        raise ValueError("Challenge has expired")

    account_id = account_id.strip().lower()

    if challenge.account_id != account_id:
        raise ValueError("Account ID does not match the challenge")

    valid_signature = verify_nep413_signature(
        public_key=public_key,
        signature=signature,
        message=challenge.message,
        nonce_b64=challenge.nonce,
        recipient=auth_recipient(),
        callback_url=auth_callback_url(),
    )

    if not valid_signature:
        raise ValueError("Invalid wallet signature")

    if not await is_full_access_key(account_id, public_key):
        raise ValueError(
            "The signing key is not an active full-access key"
        )

    user = (
        db.query(User)
        .filter(User.near_account_id == account_id)
        .first()
    )

    if user and not user.is_active:
        raise ValueError("This PayFlow account is disabled")

    if user is None:
        user = User(
            near_account_id=account_id,
            email=None,
            password_hash=None,
            is_active=True,
        )
        db.add(user)
        db.flush()

    # Consume the challenge and create a session atomically.
    challenge.consumed_at = now

    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(
            days=settings.auth_session_days
        ),
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return user, raw_token, session.expires_at


def get_user_for_session(
    db: Session,
    raw_token: str | None,
):
    if not raw_token:
        return None

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == token_hash,
            UserSession.revoked.is_(False),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )

    if not session:
        return None

    return (
        db.query(User)
        .filter(
            User.id == session.user_id,
            User.is_active.is_(True),
        )
        .first()
    )


def revoke_session(
    db: Session,
    raw_token: str | None,
):
    if not raw_token:
        return

    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    session = (
        db.query(UserSession)
        .filter(UserSession.token_hash == token_hash)
        .first()
    )

    if session and not session.revoked:
        session.revoked = True
        db.commit()