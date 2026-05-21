import pytest

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis
from autonomous_optimizer.llm.critic import Critic
from autonomous_optimizer.code_editor import CodeEditor


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def code_editor():
    return CodeEditor()


@pytest.fixture
def critic(config, code_editor):
    return Critic(config, code_editor)


@pytest.fixture
def hypothesis():
    return Hypothesis(
        slug="fix-trailing-stop",
        description="Fix trailing stop logic",
        target_files=["core/trade_simulator.py"],
        expected_delta="WR +5%",
    )


_VALID_CODE = "def foo():\n    return 42\n"
_INVALID_CODE = "def foo(\n    return 42\n"


def test_review_approved_clean(critic, hypothesis):
    result = critic.review(hypothesis, {"core/trade_simulator.py": _VALID_CODE})
    assert result.approved is True
    assert result.scope_violations == []


def test_review_scope_violation(critic, hypothesis):
    result = critic.review(hypothesis, {
        "core/trade_simulator.py": _VALID_CODE,
        "other/file.py": _VALID_CODE,
    })
    assert result.approved is False
    assert "other/file.py" in result.scope_violations


def test_review_syntax_error_blocks(critic, hypothesis):
    result = critic.review(hypothesis, {"core/trade_simulator.py": _INVALID_CODE})
    assert result.approved is False


def test_scope_violations_listed(critic, hypothesis):
    result = critic.review(hypothesis, {
        "core/trade_simulator.py": _VALID_CODE,
        "extra1.py": _VALID_CODE,
        "extra2.py": _VALID_CODE,
    })
    assert set(result.scope_violations) == {"extra1.py", "extra2.py"}


def test_no_violations_reason_empty(critic, hypothesis):
    result = critic.review(hypothesis, {"core/trade_simulator.py": _VALID_CODE})
    assert result.approved is True
    assert result.reason == ""
