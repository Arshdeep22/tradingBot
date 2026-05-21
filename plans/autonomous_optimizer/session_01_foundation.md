# Session 01: Package Foundation

**Goal**: Create the `autonomous_optimizer/` package skeleton with configuration, dataclasses, and a runnable (but stub) entry point.  
**Deliverable**: `python -m autonomous_optimizer --dry-run` prints "dry-run OK" and exits 0.  
**Estimated LOC per file**: all files ≤ 200 lines. No business logic yet — only types, config, and the package scaffold.

---

## Files to Create

### `autonomous_optimizer/__init__.py`
Empty init — just the package marker.

```python
# autonomous_optimizer/__init__.py
```

---

### `autonomous_optimizer/config.py`  (~80 lines)

Central configuration. All tunable knobs live here. No imports from other agent modules.

```python
from dataclasses import dataclass, field

@dataclass
class AgentConfig:
    # Iteration control
    max_iterations: int = 500
    iteration_interval_seconds: int = 0   # 0 = run as fast as possible

    # Validation tier thresholds
    tier1_days: int = 10
    tier1_min_wr: float = 55.0
    tier1_min_trades: int = 6
    tier2_days: int = 50
    tier2_min_wr: float = 70.0
    tier2_min_trades: int = 30
    tier2_min_pnl: float = 45_000.0       # rupees

    # Consecutive success requirement
    consecutive_required: int = 3

    # Composite score decision thresholds
    score_improve_threshold: float = 0.0   # must beat this to commit
    score_revert_threshold: float = -0.05  # revert immediately if worse by this much

    # Safety rails
    capital_floor_rupees: float = 70_000.0
    max_consecutive_losses: int = 7
    max_risk_pct_phase_ab: float = 1.0
    max_risk_pct_phase_c: float = 2.5
    max_drawdown_from_peak_pct: float = 20.0  # stop simulated run at this drawdown

    # Memory
    working_memory_window: int = 10        # iterations of full detail
    episodic_summarize_every: int = 10     # compress working memory every N iterations

    # Reflector thresholds
    min_confidence_for_tier2: float = 0.4
    novelty_reject_threshold: float = 0.15  # reject hypothesis if novelty < this

    # Stuck detector
    stuck_score_variance_threshold: float = 0.02
    stuck_min_unique_hypotheses: int = 4   # out of last 10 must be distinct
    stuck_phase_max_iterations: int = 25

    # Git
    agent_branch: str = "agent/optimize"
    repo_root: str = "."                   # override in tests

    # Paths
    state_file: str = "autonomous_optimizer/context/session_state.json"
    iterations_dir: str = "autonomous_optimizer/context/iterations"

    # Backtest runner
    backtest_timeout_seconds: int = 900    # 15-min hard kill

    # LLM
    llm_model: str = "anthropic--claude-4.6-opus"


DEFAULT_CONFIG = AgentConfig()
```

---

### `autonomous_optimizer/models.py`  (~120 lines)

All shared dataclasses. Pure data — no logic, no imports from agent submodules.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# ── Observation (Observer output) ──────────────────────────────────────────────
@dataclass
class BacktestResult:
    win_rate: float = 0.0
    total_pnl: float = 0.0
    trade_count: int = 0
    trades_per_day: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_rupees: float = 0.0
    pnl_by_week: list[float] = field(default_factory=list)
    capital_floor_hit: bool = False
    consecutive_losses_max: int = 0
    days_run: int = 0
    raw: dict = field(default_factory=dict)   # full runner output for debugging

@dataclass
class Observation:
    backtest: BacktestResult
    code_diff: str
    test_output: str
    anomaly_flags: list[str]
    data_freshness: dict[str, Any]
    regime_state: str
    git_blame_recent: list[str]
    iteration: int

# ── Root Cause (Analyzer output) ──────────────────────────────────────────────
@dataclass
class RootCause:
    category: str           # e.g. "entry_timing", "zone_quality", "exit_logic"
    evidence: list[str]
    confidence: float       # 0–1
    ruling_out: list[str]   # alternative explanations explicitly rejected

# ── Hypothesis (Strategist output) ────────────────────────────────────────────
@dataclass
class Hypothesis:
    slug: str
    description: str
    target_files: list[str]
    expected_delta: str
    novelty_score: float = 1.0

# ── Reflector output ──────────────────────────────────────────────────────────
@dataclass
class ReflectionResult:
    confidence: float
    stuck: bool
    mode: str               # "exploit" | "explore"
    gate_tier2: bool
    reason: str

# ── Critic output ─────────────────────────────────────────────────────────────
@dataclass
class CriticResult:
    approved: bool
    reason: str
    scope_violations: list[str]
    hypothesis_drift: bool

# ── Composite score ───────────────────────────────────────────────────────────
def normalize(x: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 0.0
    return max(0.0, min(1.0, (x - min_val) / (max_val - min_val)))

def composite_score(r: BacktestResult) -> float:
    return (
        0.35 * normalize(r.win_rate, 0, 100)
      + 0.30 * normalize(r.total_pnl, -50_000, 100_000)
      + 0.20 * normalize(r.trades_per_day, 0, 5)
      + 0.10 * normalize(r.profit_factor, 0, 4)
      + 0.05 * normalize(r.sharpe_ratio, -2, 4)
    )

# ── Session state (persisted to disk) ─────────────────────────────────────────
@dataclass
class SessionState:
    iteration: int = 0
    phase: str = "A"                         # "A" | "B" | "C"
    consecutive_dual_success: int = 0
    best_win_rate: float = 0.0
    best_trade_count: int = 0
    best_pnl: float = 0.0
    best_composite: float = 0.0
    approaches_tried: list[dict] = field(default_factory=list)
    blocked_approaches: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    wr_trajectory: list[float] = field(default_factory=list)
    pnl_trajectory: list[float] = field(default_factory=list)
    trade_count_trajectory: list[int] = field(default_factory=list)
    composite_score_trajectory: list[float] = field(default_factory=list)
    tier1_false_positives: int = 0
    hypothesis_embeddings: list[dict] = field(default_factory=list)
    current_hypothesis_slug: str = ""
```

---

### `autonomous_optimizer/__main__.py`  (~40 lines)

Stub entry point. Accepts `--dry-run` flag. Full logic wired in Session 07.

```python
"""Entry point: python -m autonomous_optimizer [--dry-run] [--iterations N]"""
import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args():
    p = argparse.ArgumentParser(description="Autonomous Trading Bot Optimizer")
    p.add_argument("--dry-run", action="store_true", help="Validate setup and exit")
    p.add_argument("--iterations", type=int, default=None, help="Override max_iterations")
    p.add_argument("--phase", choices=["A", "B", "C"], default=None, help="Force start phase")
    return p.parse_args()


def main():
    args = _parse_args()

    if args.dry_run:
        # Import everything to validate no import errors
        from autonomous_optimizer.config import DEFAULT_CONFIG
        from autonomous_optimizer.models import (
            BacktestResult, Observation, RootCause,
            Hypothesis, ReflectionResult, CriticResult, SessionState,
            composite_score
        )
        logger.info("dry-run OK — all imports resolved")
        sys.exit(0)

    # Full agent loop wired in Session 07
    logger.info("Agent not yet fully wired — run with --dry-run for now")
    sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_models.py`  (~80 lines)

```
test_composite_score_all_zeros          → returns 0.0
test_composite_score_perfect            → returns 1.0 (win_rate=100, pnl=100k, etc.)
test_composite_score_partial            → verifiable by hand: e.g. 70% WR only → 0.35 * 0.7 = 0.245
test_normalize_clamps                   → normalize(200, 0, 100) == 1.0, normalize(-1, 0, 100) == 0.0
test_session_state_defaults             → all lists empty, phase="A", iteration=0
test_backtest_result_defaults           → no exceptions, capital_floor_hit=False
```

Run: `python -m pytest tests/autonomous_optimizer/test_models.py -v`

---

## Acceptance Criteria

1. `python -m autonomous_optimizer --dry-run` exits 0 and logs "dry-run OK"
2. `python -m pytest tests/autonomous_optimizer/test_models.py -v` — all tests green
3. No file exceeds 200 lines
4. No circular imports between `config.py` and `models.py`
