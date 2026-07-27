from __future__ import annotations

import datetime as dt
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)   # ALWAYS upper-case
    cik: Mapped[str] = mapped_column(String(16), index=True)
    form_type: Mapped[str] = mapped_column(String(16))           # 10-K / 10-Q / 8-K
    accession: Mapped[str] = mapped_column(String(32), unique=True)
    # SEC period-of-report (period end). We store the real date, NOT a derived
    # fiscal-quarter label — fiscal calendars vary by issuer.
    report_date: Mapped[date | None] = mapped_column(Date, index=True)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {item_label: section_text}, e.g. {"item 1a": "...", "item 7": "..."}
    sections: Mapped[dict] = mapped_column(JSON, default=dict)

    chunks: Mapped[list[Chunk]] = relationship(back_populates="filing")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), index=True)
    section: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    context_blurb: Mapped[str | None] = mapped_column(Text)      
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))  
    meta: Mapped[dict] = mapped_column(JSON, default=dict)       

    filing: Mapped[Filing] = relationship(back_populates="chunks")


class Diff(Base):
    __tablename__ = "diffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)  
    section: Mapped[str] = mapped_column(String(64))
    cur_accession: Mapped[str] = mapped_column(String(32), ForeignKey("filings.accession"))
    prior_accession: Mapped[str] = mapped_column(String(32))
    semantic_drift: Mapped[float] = mapped_column(Float)
    lexical_change: Mapped[float] = mapped_column(Float)
    added: Mapped[list] = mapped_column(JSON, default=list)     
    removed: Mapped[list] = mapped_column(JSON, default=list)  
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)   
    kind: Mapped[str] = mapped_column(String(32))   
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)  
    direction: Mapped[str] = mapped_column(String(16))  
    order_type: Mapped[str] = mapped_column(String(16))          
    limit_price: Mapped[float | None] = mapped_column(Float)
    size_usd: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)  
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    __tablename__ = "decisions"

    # decision_id is the PRIMARY KEY so `db.merge()` in write_decision() is idempotent on
    # re-invoke graph and equals the LangGraph thread_id.  
    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)     
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    hypothesis: Mapped[dict] = mapped_column(JSON, default=dict)   
    critic_verdict: Mapped[dict | None] = mapped_column(JSON, default=dict)
    guardrail: Mapped[dict] = mapped_column(JSON, default=dict)     
    passed: Mapped[bool] = mapped_column(Boolean, default=False)    # all HARD rules passed
    user_id: Mapped[str] = mapped_column(String(64), default="owner", index=True)
    # approved / rejected / pending — set at the Week-7 human-approval gate.
    human_decision: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decisions.decision_id"), primary_key=True
    )
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))            
    side: Mapped[str] = mapped_column(String(8))             
    order_type: Mapped[str] = mapped_column(String(16))      
    size_usd: Mapped[float] = mapped_column(Float)         
    qty: Mapped[float | None] = mapped_column(Float)         
    limit_price: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))            
    reason: Mapped[str | None] = mapped_column(Text)
    broker_order_id: Mapped[str | None] = mapped_column(String(64))  # filled Week 7
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("decisions.decision_id"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    fill_price: Mapped[float | None] = mapped_column(Float)        
    forward_return: Mapped[float | None] = mapped_column(Float)     
    spy_return: Mapped[float | None] = mapped_column(Float)        
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # the "sub"
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="public")  # "owner" | "public"

    robinhood_linked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Full OAuth blobs (Fernet ciphertext — never plaintext), round-tripped by DbTokenStorage.
    # The token blob is the whole OAuthToken (access + refresh + expires_in/scope/token_type).
    rh_oauth_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The client blob is the dynamic-client-registration record so a fresh process skips re-reg.
    rh_oauth_client_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def execution_enabled_for(user: User) -> bool:
    """only owner trades, else read-only."""
    return user.role == "owner"