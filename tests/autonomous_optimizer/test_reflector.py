import pytest

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis, SessionState, RootCause
from autonomous_optimizer.llm.reflector import Reflector


@pytest.fixture
def config():
    return AgentConfig(
        min_confidence_for_tier2=0.4,
        stuck_score_variance_threshold=0.02,
        stuck_min_unique_hypotheses=4,
        stuck_phase_max_iterations=25,
    )


@pytest.fixture
def reflector(config):
    return Reflector(config)


@pytest.fixture
def hypothesis():
    return Hypothesis(
        slug="test-hypothesis",
        description="Test description",
        target_files=["file.py"],
        expected_delta="WR +5%",
        novelty_score=0.8,
    )


@pytest.fixture
def root_cause():
    return RootCause(
        category="entry_timing",
        evidence=["WR low"],
        confidence=0.6,
        ruling_out=[],
    )


@pytest.fixture
def healthy_state():
    # variance ≈ 0.055 > 0.02, 10 unique slugs, iteration=5 < 25
    return SessionState(
        iteration=5,
        composite_score_trajectory=[0.1, 0.3, 0.1, 0.5, 0.2, 0.6, 0.3, 0.7, 0.5, 0.8],
        approaches_tried=[
            {"slug": f"hyp-{i}", "description": f"desc {i}"} for i in range(10)
        ],
    )


def test_confidence_formula(reflector, hypothesis, root_cause):
    # No past embeddings → signal=0.0 → normalized=0.5
    # confidence = 0.4*0.6 + 0.4*0.8 + 0.2*0.5 = 0.24 + 0.32 + 0.10 = 0.66
    state = SessionState()
    result = reflector.reflect(hypothesis, root_cause, state)
    assert abs(result.confidence - 0.66) < 0.01


def test_stuck_score_oscillation(reflector, hypothesis, root_cause):
    state = SessionState(
        composite_score_trajectory=[0.5] * 10,
        approaches_tried=[{"slug": f"h{i}", "description": f"d{i}"} for i in range(10)],
    )
    result = reflector.reflect(hypothesis, root_cause, state)
    assert result.stuck is True


def test_stuck_hypothesis_cycling(reflector, hypothesis, root_cause):
    # High variance (won't trigger oscillation), only 3 unique slugs (triggers cycling)
    state = SessionState(
        composite_score_trajectory=[0.1, 0.9] * 5,
        approaches_tried=[{"slug": f"h{i % 3}", "description": "desc"} for i in range(10)],
    )
    result = reflector.reflect(hypothesis, root_cause, state)
    assert result.stuck is True


def test_not_stuck_healthy_progress(reflector, hypothesis, root_cause, healthy_state):
    result = reflector.reflect(hypothesis, root_cause, healthy_state)
    assert result.stuck is False


def test_gate_tier2_low_confidence(reflector):
    h = Hypothesis(slug="h", description="d", target_files=[], expected_delta="", novelty_score=0.1)
    rc = RootCause(category="c", evidence=[], confidence=0.1, ruling_out=[])
    state = SessionState()
    result = reflector.reflect(h, rc, state)
    assert result.gate_tier2 is False


def test_gate_tier2_high_confidence(reflector):
    h = Hypothesis(slug="h", description="d", target_files=[], expected_delta="", novelty_score=1.0)
    rc = RootCause(category="c", evidence=[], confidence=1.0, ruling_out=[])
    state = SessionState()
    result = reflector.reflect(h, rc, state)
    assert result.gate_tier2 is True


def test_mode_explore_when_stuck(reflector, hypothesis, root_cause):
    state = SessionState(composite_score_trajectory=[0.5] * 10)
    result = reflector.reflect(hypothesis, root_cause, state)
    assert result.mode == "explore"


def test_variance_empty_list(reflector):
    assert reflector._variance([]) == 0.0
