"""Ingest the exact 10-K filings the golden set was labeled against.

Reads (ticker, accession) pairs from app/eval/golden.json and ingests each PINNED filing
via `ingest_accession` — never "latest", because issuers keep filing and the labels are tied
to one document. Chunks Item 1A + Item 7 with blurbs disabled so the corpus is deterministic
and needs no Gemini calls; embeddings are local bge-small.

Idempotent: a stored accession is reused and `persist_filing_chunks` skips chunks already
present (content-hash unique index), so re-runs are safe.

Run: uv run python -m scripts.ingest_golden
"""

from __future__ import annotations

import httpx

from app.db import SessionLocal
from app.eval.golden import load
from app.ingestion.edgar import cik_for, ingest_accession
from app.rag.chunk import persist_filing_chunks

SECTIONS = ["item 1a", "item 7"]  # Risk Factors + MD&A — the analyst-relevant sections


def main() -> None:
    pinned = sorted({(c["ticker"], c["accession"]) for c in load()})
    with httpx.Client() as client:
        for ticker, accession in pinned:
            with SessionLocal() as db:
                filing = ingest_accession(ticker, cik_for(ticker, client), accession, db, client)
                present = [s for s in SECTIONS if s in filing.sections]
                n = persist_filing_chunks(db, filing, sections=present, do_blurbs=False)
                print(
                    f"{ticker}: {accession} ({filing.report_date}) "
                    f"sections={present} -> {n} new chunks"
                )


if __name__ == "__main__":
    main()
