import re

import pytest

from autonomous_optimizer.loop_helpers import (
    _check_stuck, _format_commit, _maybe_advance_phase,
)
from autonomous_optimizer.models import BacktestResult, SessionState
from autonomous_optimizer.config import AgentConfig

_COMMIT_RE = re.compile(
    r"\[iter=\d+\]\[phase=[ABC]\]\[wr=[\d.]+\]\[pnl=[-\d.]+\]"
    r"\[trades=\d+\]\[composite=[\d.]+\]\[hyp=[\w-]+\]"
)


def _result(**kwargs) -> BacktestResult:
    defaults = dict(
        win_rate=72.0, total_pnl=50_000.0, trade_count=35,
        trades_per_day=1.5, profit_factor=2.0, sharpe_ratio=1.2,
        max_drawdown_rupees=3_000.0, days_run=50,
    )
    defaults.update(kwargs)
    return BacktestResult(**defaults)


def test_format_commit_matches_regex():
    msg = _format_commit(5, "A", _result(), 0.6512, "improve-entry")
    assert _COMMIT_RE.search(msg), f"Message did not match regex: {msg!r}"


def test_format_commit_negative_pnl_matches_regex():
    msg = _format_commit(2, "B", _result(total_pnl=-10_000.0), 0.25, "fix-exits")
    assert _COMMIT_RE.search(msg), f"Negative PnL message did not match regex: {msg!r}"


def test_check_stuck_returns_true():
    state = SessionState()
    state.composite_score_trajectory = [0.5] * 10
    assert _check_stuck(state, AgentConfig()) is True


def test_check_stuck_returns_false():
    state = SessionState()
    state.composite_score_trajectory = [0.1 * i for i in range(1, 11)]
    assert _check_stuck(state, AgentConfig()) is False


def test_check_stuck_insufficient_history():
    state = SessionState()
    state.composite_score_trajectory = [0.5] * 5  # less than working_memory_window
    assert _check_stuck(state, AgentConfig()) is False


def test_maybe_advance_phase_a_to_b(tmp_path):
    from autonomous_optimizer.session_manager import SessionManager
    config = AgentConfig(
        repo_root=str(tmp_path),
        state_file=str(tmp_path / "state.json"),
        iterations_dir=str(tmp_path / "iterations"),
    )
    session = SessionManager(config)
    session.state.phase = "A"
    session.state.composite_score_trajectory = [0.5] * 10  # no variance → stuck

    _maybe_advance_phase(session, config)

    assert session.state.phase == "B"


def test_maybe_advance_no_change(tmp_path):
    from autonomous_optimizer.session_manager import SessionManager
    config = AgentConfig(
        repo_root=str(tmp_path),
        state_file=str(tmp_path / "state.json"),
        iterations_dir=str(tmp_path / "iterations"),
    )
    session = SessionManager(config)
    session.state.phase = "A"
    session.state.composite_score_trajectory = [0.1 * i for i in range(1, 11)]

    _maybe_advance_phase(session, config)

    assert session.state.phase == "A"


def test_maybe_advance_stays_at_c(tmp_path):
    from autonomous_optimizer.session_manager import SessionManager
    config = AgentConfig(
        repo_root=str(tmp_path),
        state_file=str(tmp_path / "state.json"),
        iterations_dir=str(tmp_path / "iterations"),
    )
    session = SessionManager(config)
    session.state.phase = "C"
    session.state.composite_score_trajectory = [0.5] * 10

    _maybe_advance_phase(session, config)

    assert session.state.phase == "C"
