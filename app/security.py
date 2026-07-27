from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic_core import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(settings.fernet_key.encode())  # urlsafe-base64 string  


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:  
        raise ValueError("token could not be decrypted (key rotated or corrupt)") from e


def link_robinhood(db: Session, user: User, access_token: str, refresh_token: str | None) -> None:
    """Manual link path (API): store a minimal token blob from raw access/refresh strings."""
    token = OAuthToken(access_token=access_token, refresh_token=refresh_token)
    user.rh_oauth_token_enc = encrypt_token(token.model_dump_json())
    user.robinhood_linked = True
    db.commit()


def get_robinhood_access_token(user: User) -> str | None:
    blob = user.rh_oauth_token_enc
    if not blob: 
        return None
    
    try:
        return OAuthToken.model_validate_json(decrypt_token(blob)).access_token 
    except (ValidationError, ValueError): 
        return None

class DbTokenStorage(TokenStorage):
    """Primary OAuth token storage: encrypted, per-user, in Postgres."""

    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user

    async def get_tokens(self) -> OAuthToken | None:
        blob = self.user.rh_oauth_token_enc
        if not blob:
            return None
        
        try:
            decrypted_json = decrypt_token(blob)
            return OAuthToken.model_validate_json(decrypted_json)
        except (ValidationError, ValueError):
            return None
        

    async def set_tokens(self, tokens: OAuthToken) -> None:
        # Store the full token blob (access + refresh + expires_in/scope) as the source of truth.
        self.user.rh_oauth_token_enc = encrypt_token(tokens.model_dump_json())
        self.user.robinhood_linked = True
        self.db.commit()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        blob = self.user.rh_oauth_client_enc
        return OAuthClientInformationFull.model_validate_json(decrypt_token(blob)) if blob else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.user.rh_oauth_client_enc = encrypt_token(client_info.model_dump_json())
        self.db.commit()


# Dev-script identity: scripts have no Clerk request context, so they act as the local
# owner. In prod the API binds DbTokenStorage to the authenticated request's User instead.
OWNER_CLERK_ID = "local-owner"


def get_or_create_owner(db: Session) -> User:
    user = db.scalars(select(User).where(User.role == "owner")).first()
    if user is None:
        user = User(clerk_user_id=OWNER_CLERK_ID, role="owner")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@contextmanager
def owner_token_storage() -> Generator[DbTokenStorage]:
    """DbTokenStorage for the local owner, with a managed DB session. For scripts/cron."""
    db = SessionLocal()
    try:
        yield DbTokenStorage(db, get_or_create_owner(db))
    finally:
        db.close()