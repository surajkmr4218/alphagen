from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import session_scope
from app.models import User, execution_enabled_for
from app.security import link_robinhood

app = FastAPI(title = "Alphagen")

# Browser calls come from the Vite dev origin; without this the preflight fails
# and every fetch from the SPA is blocked. curl bypasses CORS, so test in-browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@lru_cache(maxsize=1)
def _jwks() -> dict:
    resp = httpx.get(settings.clerk_jwks_url, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _verify_clerk_jwt(token: str) -> str:
    try:
        claims = jwt.decode(token, _jwks(), algorithms=["RS256"], options={"verify_aud": False})
    except JWTError as e:
        raise HTTPException(status_code=401, detail="invalid token") from e
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token missing sub")
    return sub


def current_user_id(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _verify_clerk_jwt(authorization.removeprefix("Bearer "))

def get_db(clerk_user_id: str = Depends(current_user_id)) -> Iterator[Session]:
    # session_scope sets the RLS GUC (app.user_id) to the same clerk_user_id that
    # write_decision stamps into the user_id column — one tenant key, set on every session.
    with session_scope(clerk_user_id) as db:
        yield db

def current_user(
    clerk_user_id: str = Depends(current_user_id), db: Session = Depends(get_db)
) -> User:
    user = db.query(User).filter_by(clerk_user_id=clerk_user_id).one_or_none()
    if user is None:  # first sign-in -> least-privilege default
        user = User(clerk_user_id=clerk_user_id, role="public")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "clerk_user_id": user.clerk_user_id,
        "role": user.role,
        "execution_enabled": execution_enabled_for(user),
        "robinhood_linked": user.robinhood_linked,
    }

@app.get("/onboarding/status")
def onboarding_status(user: User = Depends(current_user)) -> dict:
    return {"robinhood_linked": user.robinhood_linked}


class LinkPayload(BaseModel):
    access_token: str
    refresh_token: str | None = None


@app.post("/onboarding/link-robinhood")
def link_rh(
    payload: LinkPayload, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    link_robinhood(db, user, payload.access_token, payload.refresh_token)
    return {"robinhood_linked": True}  # do NOT echo the token back