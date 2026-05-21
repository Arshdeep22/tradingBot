import pytest
from autonomous_optimizer.memory.embeddings import (
    embed, cosine_similarity, novelty_score, most_similar_past,
    _EMBEDDINGS_AVAILABLE,
)


def test_cosine_similarity_identical():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_empty():
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], []) == 0.0
    assert cosine_similarity([], [1.0]) == 0.0


def test_novelty_score_empty_history():
    assert novelty_score("some hypothesis text", []) == 1.0


def test_embed_no_crash_when_unavail():
    result = embed("test text")
    assert isinstance(result, list)


def test_novelty_score_similar():
    if not _EMBEDDINGS_AVAILABLE:
        pytest.skip("sentence-transformers not installed")
    text = "add a momentum filter to entry conditions"
    similar = "apply momentum filter on entry signal"
    vec = embed(similar)
    past = [{"embedding": vec, "result": "improved"}]
    score = novelty_score(text, past)
    assert score < 0.5


def test_novelty_score_dissimilar():
    if not _EMBEDDINGS_AVAILABLE:
        pytest.skip("sentence-transformers not installed")
    text = "reduce stop loss distance"
    past_vec = embed("add moving average crossover to entry")
    past = [{"embedding": past_vec, "result": "degraded"}]
    score = novelty_score(text, past)
    assert score > 0.5


def test_most_similar_past_empty():
    result = most_similar_past("some text", [])
    assert result is None


def test_most_similar_past_returns_closest():
    if not _EMBEDDINGS_AVAILABLE:
        pytest.skip("sentence-transformers not installed")
    target = "momentum entry filter"
    entries = [
        {"embedding": embed("momentum filter for entries"), "result": "improved"},
        {"embedding": embed("reduce stop loss"), "result": "degraded"},
    ]
    best = most_similar_past(target, entries)
    assert best["result"] == "improved"
