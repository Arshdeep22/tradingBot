import pytest
from unittest.mock import MagicMock, patch

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import RootCause, Hypothesis
from autonomous_optimizer.llm.strategist import Strategist, ConstraintViolation
from autonomous_optimizer.memory.long_term_memory import LongTermMemory


@pytest.fixture
def config():
    return AgentConfig(novelty_reject_threshold=0.15)


@pytest.fixture
def llm():
    return MagicMock()


@pytest.fixture
def long_term():
    return LongTermMemory()


@pytest.fixture
def strategist(config, llm, long_term):
    return Strategist(config, llm, long_term)


@pytest.fixture
def root_cause():
    return RootCause(
        category="entry_timing",
        evidence=["WR dropped 5%"],
        confidence=0.7,
        ruling_out=["zone_quality"],
    )


_VALID_JSON = {
    "slug": "trailing-stop-breakeven",
    "description": "Add trailing stop logic to exit at breakeven",
    "target_files": ["core/trade_simulator.py"],
    "expected_delta": "WR +5-10%, trades unchanged",
}


def test_strategize_returns_hypothesis(strategist, llm, root_cause):
    llm.call.return_value = _VALID_JSON
    with patch("autonomous_optimizer.llm.strategist.novelty_score", return_value=0.9):
        h = strategist.strategize(root_cause, {"phase": "A"})
    assert isinstance(h, Hypothesis)
    assert h.slug == "trailing-stop-breakeven"
    assert h.novelty_score == 0.9


def test_novelty_check_rejects_similar(strategist, llm, long_term, root_cause):
    llm.call.return_value = _VALID_JSON
    long_term.add_hypothesis_embedding("old-slug", "some old hypothesis", "improved", 1)
    with patch("autonomous_optimizer.llm.strategist.novelty_score", side_effect=[0.05, 0.9]):
        strategist.strategize(root_cause, {"phase": "A"})
    assert llm.call.call_count == 2


def test_phase_b_constraint_enforced(strategist, llm, root_cause):
    data = dict(_VALID_JSON, target_files=["file1.py", "file2.py", "file3.py"])
    llm.call.return_value = data
    with patch("autonomous_optimizer.llm.strategist.novelty_score", return_value=0.9):
        with pytest.raises(ConstraintViolation):
            strategist.strategize(root_cause, {"phase": "B"})


def test_phase_a_no_constraint(strategist, llm, root_cause):
    data = dict(_VALID_JSON, target_files=["file1.py", "file2.py", "file3.py"])
    llm.call.return_value = data
    with patch("autonomous_optimizer.llm.strategist.novelty_score", return_value=0.9):
        h = strategist.strategize(root_cause, {"phase": "A"})
    assert len(h.target_files) == 3


def test_explore_mode_appends_suffix(strategist, llm, root_cause):
    llm.call.return_value = _VALID_JSON
    with patch("autonomous_optimizer.llm.strategist.novelty_score", return_value=0.9):
        strategist.strategize(root_cause, {"phase": "A"}, explore=True)
    user_message = llm.call.call_args[0][1]
    assert "EXPLORE" in user_message


def test_slug_kebab_validation(strategist, llm, root_cause):
    data = dict(_VALID_JSON, slug="invalid slug with spaces")
    llm.call.return_value = data
    with patch("autonomous_optimizer.llm.strategist.novelty_score", return_value=0.9):
        with pytest.raises(ValueError):
            strategist.strategize(root_cause, {"phase": "A"})
