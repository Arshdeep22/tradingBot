from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from autonomous_optimizer.models import BacktestResult

if TYPE_CHECKING:
    from autonomous_optimizer.models import SessionState
    from autonomous_optimizer.session_manager import SessionManager
    from autonomous_optimizer.backtest_runner import BacktestRunner

logger = logging.getLogger(__name__)


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


def _maybe_advance_phase(
    session: "SessionManager",
    tier2_result: BacktestResult | None = None,
) -> str | None:
    """Advance phase A→B or B→C based on metric gates or score stagnation.

    Returns the new phase name if advanced, None otherwise.
    """
    if session.state.phase == "C":
        return None

    phase = session.state.phase

    if tier2_result is not None:
        if phase == "A":
            if tier2_result.trade_count >= 30 and tier2_result.win_rate >= 40.0:
                logger.info(
                    "Phase A gate passed (trades=%d, wr=%.1f%%) — advancing to B",
                    tier2_result.trade_count, tier2_result.win_rate,
                )
                return session.advance_phase()
        elif phase == "B":
            if (
                tier2_result.win_rate >= 60.0
                and tier2_result.trade_count >= 30
                and tier2_result.total_pnl > 0
            ):
                logger.info(
                    "Phase B gate passed (wr=%.1f%%, trades=%d, pnl=%.0f) — advancing to C",
                    tier2_result.win_rate, tier2_result.trade_count, tier2_result.total_pnl,
                )
                return session.advance_phase()

    if session.should_advance_phase():
        logger.info("Phase %s stagnated — advancing via score variance", phase)
        return session.advance_phase()

    return None


def _safe_run_tier1(runner: "BacktestRunner") -> BacktestResult:
    """Run Tier 1 backtest; return a zeroed BacktestResult on any failure."""
    try:
        return runner.run_tier1()
    except Exception:
        return BacktestResult()
