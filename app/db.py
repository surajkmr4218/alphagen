from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    """Single declarative base. models.py and alembic/env.py both import THIS."""
    pass


@contextmanager
def session_scope() -> Generator[Session]:
    """A short-lived DB session with commit-on-exit."""
    db = SessionLocal()
    try:
        yield db
        db.commit()   # all adds/updates done inside the with block become permanent in the database.
    finally:
        db.close()    # connection returns to the pool for reuse
