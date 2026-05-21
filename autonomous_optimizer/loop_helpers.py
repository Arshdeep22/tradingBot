from __future__ import annotations

from typing import TYPE_CHECKING

from autonomous_optimizer.models import BacktestResult

if TYPE_CHECKING:
    from autonomous_optimizer.config import AgentConfig
    from autonomous_optimizer.models import SessionState
    from autonomous_optimizer.session_manager import SessionManager
    from autonomous_optimizer.backtest_runner import BacktestRunner


def _check_stuck(state: "SessionState", config: "AgentConfig") -> bool:
    """Return True if composite score variance across recent iterations is below threshold."""
    scores = state.composite_score_trajectory[-config.working_memory_window:]
    if len(scores) < config.working_memory_window:
        return False
    return max(scores) - min(scores) < config.stuck_score_variance_threshold


def _format_commit(n: int, phase: str, result: BacktestResult, score: float, slug: str) -> str:
    """Format a commit message matching git_ops._COMMIT_RE."""
    return (
        f"[iter={n}][phase={phase}][wr={round(result.win_rate, 2)}]"
        f"[pnl={int(round(result.total_pnl))}][trades={result.trade_count}]"
        f"[composite={round(score, 4)}][hyp={slug}]"
    )


def _maybe_advance_phase(session: "SessionManager", config: "AgentConfig") -> None:
    """Advance phase from A→B or B→C if the session detects score stagnation."""
    if session.state.phase == "C":
        return
    if session.should_advance_phase():
        session.advance_phase()


def _safe_run_tier1(runner: "BacktestRunner") -> BacktestResult:
    """Run Tier 1 backtest; return a zeroed BacktestResult on any failure."""
    try:
        return runner.run_tier1()
    except Exception:
        return BacktestResult()
