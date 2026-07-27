"""Throwaway driver: ingest 10-K Item 1A + Item 7 for the golden-set tickers.

Reuses the EDGAR ingestion (`ingest_latest`) and chunking
(`persist_filing_chunks`). Blurbs are disabled so the golden corpus is
deterministic and needs no Gemini calls; embeddings are local bge-small.

Idempotent: skips a ticker whose 10-K is already in the DB so re-runs are safe.

Run: uv run python scripts/ingest_golden.py
"""

from __future__ import annotations

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.ingestion.edgar import ingest_latest
from app.models import Filing
from app.rag.chunk import persist_filing_chunks

# CIKs are the SEC central index keys; ingest_latest zero-pads them.
TICKERS: list[tuple[str, str]] = [
    ("AAPL", "320193"),
    ("MSFT", "789019"),
    ("NVDA", "1045810"),
    ("AMZN", "1018724"),
    ("META", "1326801"),
    ("TSLA", "1318605"),
]

SECTIONS = ["item 1a", "item 7"]  # Risk Factors + MD&A — the analyst-relevant sections


def main() -> None:
    with httpx.Client() as client:
        for ticker, cik in TICKERS:
            with SessionLocal() as db:
                exists = db.execute(
                    select(Filing.id).where(
                        Filing.ticker == ticker, Filing.form_type == "10-K"
                    )
                ).first()
                if exists:
                    print(f"{ticker}: 10-K already ingested — skipping")
                    continue

                filing = ingest_latest(ticker, cik, "10-K", db, client)
                present = [s for s in SECTIONS if s in filing.sections]
                n = persist_filing_chunks(db, filing, sections=present, do_blurbs=False)
                print(
                    f"{ticker}: ingested {filing.accession} "
                    f"({filing.report_date}) sections={present} -> {n} chunks"
                )


if __name__ == "__main__":
    main()
