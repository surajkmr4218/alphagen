"""Chunk hashing + idempotent persistence."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import delete, func, select

from app.rag.chunk import text_sha


def test_text_sha_is_md5_hex_of_utf8() -> None:
    assert text_sha("abc") == hashlib.md5(b"abc").hexdigest()
    assert len(text_sha("x")) == 32


def test_persist_filing_chunks_is_idempotent() -> None:
    from app.db import SessionLocal, db_available
    from app.models import Chunk, Filing
    from app.rag.chunk import persist_filing_chunks

    if not db_available():
        pytest.skip("no database reachable")

    with SessionLocal() as db:
        filing = Filing(
            ticker="ZZTEST", cik="0", form_type="10-K", accession="TEST-IDEMPOTENT-0001",
            sections={"item 1a": "Alpha risk.\nBeta risk.", "item 7": "Gamma outlook."},
        )
        db.add(filing)
        db.commit()
        db.refresh(filing)
        try:
            first = persist_filing_chunks(db, filing, do_blurbs=False)
            second = persist_filing_chunks(db, filing, do_blurbs=False)
            n = db.scalar(select(func.count(Chunk.id)).where(Chunk.filing_id == filing.id))
            assert first > 0
            assert second == 0 # should not ingest the same filing
            assert n == first
        finally:
            db.execute(delete(Chunk).where(Chunk.filing_id == filing.id))
            db.execute(delete(Filing).where(Filing.id == filing.id))
            db.commit()
