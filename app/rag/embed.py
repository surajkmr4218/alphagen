from __future__ import annotations

from functools import lru_cache

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384-dim, free, local CPU
EMBED_DIM = 384  # MUST match Chunk.embedding = Vector(384)  


@lru_cache(maxsize=1)
def _model():
    """Lazy, cached SentenceTransformer load.

    sentence-transformers pulls in torch (~3-5s import) and downloads the model
    (~130MB) on first use. We hide that cost behind a one-time cache so importing
    this module stays cheap and module import never triggers a network call.
    """
    from sentence_transformers import SentenceTransformer  # lazy heavy import

    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """Encode a batch of texts to L2-normalized 384-dim vectors.

    Returns a list of plain Python float lists (JSON/pgvector friendly).
    normalize_embeddings=True so cosine == dot product downstream.
    """
    if not texts:
        return []
    vecs = _model().encode(texts, normalize_embeddings=True)
    return vecs.tolist()