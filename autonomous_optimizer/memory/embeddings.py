import math
from typing import Optional

try:
    from sentence_transformers import SentenceTransformer as _ST
    _model = _ST("all-MiniLM-L6-v2")
    _EMBEDDINGS_AVAILABLE = True
except Exception:
    _model = None
    _EMBEDDINGS_AVAILABLE = False


def embed(text: str) -> list[float]:
    if not _EMBEDDINGS_AVAILABLE or _model is None:
        return []
    return _model.encode(text).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def novelty_score(hypothesis_text: str, past_embeddings: list[dict]) -> float:
    if not _EMBEDDINGS_AVAILABLE or not past_embeddings:
        return 1.0
    vec = embed(hypothesis_text)
    if not vec:
        return 1.0
    max_sim = max(
        cosine_similarity(vec, entry["embedding"])
        for entry in past_embeddings
        if entry.get("embedding")
    ) if past_embeddings else 0.0
    return 1.0 - max_sim


def most_similar_past(hypothesis_text: str, past_embeddings: list[dict]) -> Optional[dict]:
    if not _EMBEDDINGS_AVAILABLE or not past_embeddings:
        return None
    vec = embed(hypothesis_text)
    if not vec:
        return None
    best = max(
        past_embeddings,
        key=lambda e: cosine_similarity(vec, e.get("embedding", [])),
    )
    return best
