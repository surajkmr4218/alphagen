from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    """Single declarative base. models.py and alembic/env.py both import THIS."""
    pass


@contextmanager
def session_scope(user_id: str | None = None) -> Iterator[Session]:
    """A DB session with the RLS tenant key set for its whole lifetime.

    Row-Level Security on decisions/orders/outcomes compares each row's `user_id`
    column against the GUC `app.user_id` (`current_setting('app.user_id')`). That GUC
    MUST be set on *every* session that touches those tables — the API request, the
    agent nodes, and any cron/reconcile job — or reads fail closed (zero rows) and the
    tenant key on writes has nothing to match against. This is the single place that
    opens a `SessionLocal` and sets the GUC, so no write path can forget it.

    Pass the caller's `clerk_user_id` (the one tenant identity used everywhere: the GUC
    here, and the `user_id` column stamped by write_decision). `None`/"" leaves the GUC
    empty, which under the fail-closed policy matches no rows.
    """
    db = SessionLocal()
    try:
        # set_config parameterizes the value (no SQL injection); false = session-scoped.
        db.execute(text("SELECT set_config('app.user_id', :uid, false)"), {"uid": user_id or ""})
        yield db
    finally:
        # reset so a pooled connection doesn't bleed this id to the next checkout; the
        # commit persists the reset (a session-level set_config is rolled back otherwise).
        db.execute(text("SELECT set_config('app.user_id', '', false)"))
        db.commit()
        db.close()