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
