import pytest
from unittest.mock import MagicMock, patch

from autonomous_optimizer.agent import Agent
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import (
    BacktestResult, RootCause, Hypothesis, ReflectionResult, CriticResult,
)
from autonomous_optimizer.backtest_runner import BacktestTimeoutError


def _result(win_rate=75.0, pnl=60_000.0, trades=40) -> BacktestResult:
    return BacktestResult(
        win_rate=win_rate, total_pnl=pnl, trade_count=trades,
        trades_per_day=1.5, profit_factor=2.0, sharpe_ratio=1.2,
        max_drawdown_rupees=3_000.0, days_run=50,
    )


@pytest.fixture
def agent(tmp_path):
    config = AgentConfig(
        repo_root=str(tmp_path),
        state_file=str(tmp_path / "state.json"),
        iterations_dir=str(tmp_path / "iterations"),
        max_iterations=10,
        consecutive_required=3,
    )
    _patches = [
        patch("autonomous_optimizer.agent.GitOps"),
        patch("autonomous_optimizer.agent.BacktestRunner"),
        patch("autonomous_optimizer.agent.SuccessChecker"),
        patch("autonomous_optimizer.agent.AgentLLMClient"),
        patch("autonomous_optimizer.agent.Observer"),
        patch("autonomous_optimizer.agent.Analyzer"),
        patch("autonomous_optimizer.agent.Strategist"),
        patch("autonomous_optimizer.agent.Reflector"),
        patch("autonomous_optimizer.agent.Critic"),
        patch("autonomous_optimizer.agent.Coder"),
        patch("autonomous_optimizer.agent._safe_run_tier1"),
    ]
    mocks = [p.start() for p in _patches]
    a = Agent(config)

    # Default LLM component returns
    a._observer.observe.return_value = MagicMock()
    a._analyzer.analyze.return_value = RootCause("entry_timing", ["e"], 0.7, ["r"])
    a._strategist.strategize.return_value = Hypothesis("test-hyp", "desc", ["f.py"], "+5%", 0.8)
    a._reflector.reflect.return_value = ReflectionResult(0.7, False, "exploit", True, "ok")
    a._critic.review.return_value = CriticResult(True, "ok", [], False)
    a._coder.generate_changes.return_value = {"f.py": "code"}
    a._coder.apply_changes.return_value = True

    # Default runner / checker
    mocks[-1].return_value = _result(60.0, 10_000.0, 8)  # _safe_run_tier1
    a._runner.run_tier2.return_value = _result()
    a._checker.passes_tier1.return_value = True
    a._checker.passes_tier2.return_value = False
    a._checker.check_goal_achieved.return_value = False
    a._git.commit.return_value = "abc1234"

    yield a

    for p in _patches:
        p.stop()


def test_one_iteration_commits_on_improvement(agent):
    agent._session.state.best_composite = 0.3
    agent._runner.run_tier2.return_value = _result(75.0, 60_000.0, 40)

    agent._run_one_iteration(1)

    assert agent._git.commit.called
    assert agent._session.state.best_composite > 0.3


def test_one_iteration_reverts_on_regression(agent):
    agent._session.state.best_composite = 0.9
    agent._runner.run_tier2.return_value = _result(30.0, 0.0, 2)

    agent._run_one_iteration(1)

    agent._git.revert_to_snapshot.assert_called_once()
    assert not agent._git.commit.called
    assert agent._session.state.best_composite == 0.9


def test_critic_block_skips_implementation(agent):
    agent._critic.review.return_value = CriticResult(False, "out of scope", ["bad.py"], False)

    agent._run_one_iteration(1)

    agent._coder.apply_changes.assert_not_called()
    assert agent._session.state.iteration == 1


def test_goal_achieved_stops_loop(agent):
    agent._session.state.best_composite = 0.0
    agent._runner.run_tier2.return_value = _result()
    agent._checker.passes_tier2.return_value = True
    agent._checker.check_goal_achieved.side_effect = [False, False, True]

    agent.run(override_iterations=10)

    agent._git.tag.assert_called_once_with("goal-achieved")
    assert agent._session.state.iteration == 3


def test_timeout_reverts(agent):
    agent._runner.run_tier2.side_effect = BacktestTimeoutError("timed out")

    agent._run_one_iteration(1)

    agent._git.revert_to_snapshot.assert_called_once()
    assert not agent._git.commit.called


def test_session_saved_every_iteration(agent):
    agent._session.state.best_composite = 0.0
    agent._runner.run_tier2.return_value = _result()
    agent._checker.check_goal_achieved.return_value = False

    save_count = [0]
    agent._session.save = lambda: save_count.__setitem__(0, save_count[0] + 1)

    agent.run(override_iterations=3)

    assert save_count[0] == 3
