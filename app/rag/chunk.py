from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Filing
from app.rag.embed import embed

PARA_SPLIT = re.compile(r"\n+")  # split on any newline run (SEC text uses single \n)

def chunk_section(text: str, target: int = 1200, overlap: int = 150) -> list[str]:
    """Pack text lines into ~target-char chunks with a char overlap tail.

    Pure function: SEC filings flatten to single-`\n` lines (no blank-line
    paragraphs), so we split on any newline run, hard-slice any single line still
    larger than target (else it would never be cut), then accumulate lines until
    the buffer would exceed target, flush, and seed the next buffer with the last
    overlap chars so context straddling a boundary survives.
    """
    raw = [p.strip() for p in PARA_SPLIT.split(text) if p.strip()]
    segments: list[str] = []
    for p in raw:
        if len(p) <= target:
            segments.append(p)
        else:  # a single oversized line: hard-window it so nothing exceeds target
            segments += [p[i:i + target] for i in range(0, len(p), target)]

    chunks: list[str] = []
    buf = ""
    for seg in segments:
        if buf and len(buf) + len(seg) + 1 > target:
            chunks.append(buf)
            buf = buf[-overlap:] + "\n" + seg  # carry overlap tail
        else:
            buf = f"{buf}\n{seg}" if buf else seg
    if buf.strip():
        chunks.append(buf)
    return chunks


# ---- IO edge: contextual blurb via Gemini --------------------------------

# Cheap, high-volume per-chunk call -> Flash-Lite: cheapest tier, highest daily quota.
# Reasoning-heavy calls (Hypothesis/critic) use gemini-3.5-flash instead.
BLURB_MODEL = "gemini-3.1-flash-lite"
# BLURB_MODEL = "gemini-3.5-flash"  # swap up if blurbs need more reasoning per call

_BLURB_PROMPT = (
    "Here is a section from an SEC filing:\n<section>\n{section}\n</section>\n\n"
    "Here is a chunk from that section:\n<chunk>\n{chunk}\n</chunk>\n\n"
    "Give a single short sentence that situates this chunk within the section so it can "
    "be retrieved on its own. Output only the sentence, no preamble."
)


def _client():
    from google import genai  # lazy import

    return genai.Client(api_key=settings.gemini_api_key)


def contextual_blurb(section_text: str, chunk: str) -> str:
    """One-sentence Gemini blurb situating `chunk` inside `section_text`.

    Keep the section context bounded so we don't blow the prompt up for huge 10-Ks.
    """
    prompt = _BLURB_PROMPT.format(section=section_text[:6000], chunk=chunk)
    resp = _client().models.generate_content(
        model=BLURB_MODEL,
        contents=prompt,
        config={"max_output_tokens": 80},
    )
    return resp.text.strip()

def persist_filing_chunks(
    session: Session,
    filing: Filing,
    sections: list[str] | None = None,
    do_blurbs: bool = True,
) -> int:
    """Chunk a filing's sections, embed (blurb+chunk), and insert Chunk rows.

    `sections` lets you restrict to e.g. ["item 1a", "item 7"]; default
    is every section present on the filing. Returns the number of chunks written.
    """
    ticker = filing.ticker.upper()  # convention: always upper-keyed
    items = sections or list(filing.sections.keys())

    rows: list[Chunk] = []
    blurbs: list[str] = []
    payloads: list[tuple[str, str]] = []  # (section, chunk_text)

    for item in items:
        section_text = filing.sections.get(item, "")
        if not section_text:
            continue
        for chunk in chunk_section(section_text):
            blurb = ""
            if do_blurbs:
                try:
                    blurb = contextual_blurb(section_text, chunk)
                except Exception:  # never let a blurb call abort the persist
                    blurb = ""
            blurbs.append(blurb)
            payloads.append((item, chunk))

    # one batched embed call over (blurb + chunk) concatenations
    to_embed = [f"{b}\n{c}" if b else c for b, (_, c) in zip(blurbs, payloads)]
    vectors = embed(to_embed)

    for (section, chunk), blurb, vec in zip(payloads, blurbs, vectors):
        rows.append(
            Chunk(
                filing_id=filing.id,
                section=section,
                text=chunk,
                context_blurb=blurb,
                embedding=vec,
                meta={"ticker": ticker, "accession": filing.accession},
            )
        )

    session.add_all(rows)  # SQLAlchemy bulk insert + reason for not async here
    session.commit()
    return len(rows)