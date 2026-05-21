import pytest
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult, SessionState
from autonomous_optimizer.success_checker import SuccessChecker

DEFAULT_CONFIG = AgentConfig()


def _checker(config=None):
    return SuccessChecker(config or DEFAULT_CONFIG)


# ── Tier 1 ────────────────────────────────────────────────────────────────────

def test_passes_tier1_true():
    r = BacktestResult(win_rate=60.0, trade_count=8)
    assert _checker().passes_tier1(r) is True


def test_passes_tier1_false_wr():
    r = BacktestResult(win_rate=40.0, trade_count=8)
    assert _checker().passes_tier1(r) is False


def test_passes_tier1_false_trades():
    r = BacktestResult(win_rate=60.0, trade_count=3)
    assert _checker().passes_tier1(r) is False


def test_passes_tier1_exact_boundary():
    cfg = AgentConfig(tier1_min_wr=55.0, tier1_min_trades=6)
    r = BacktestResult(win_rate=55.0, trade_count=6)
    assert _checker(cfg).passes_tier1(r) is True


# ── Tier 2 ────────────────────────────────────────────────────────────────────

def test_passes_tier2_true():
    r = BacktestResult(win_rate=72.0, trade_count=35, total_pnl=50000.0)
    assert _checker().passes_tier2(r) is True


def test_passes_tier2_false_pnl():
    r = BacktestResult(win_rate=72.0, trade_count=35, total_pnl=40000.0)
    assert _checker().passes_tier2(r) is False


def test_passes_tier2_false_wr():
    r = BacktestResult(win_rate=60.0, trade_count=35, total_pnl=50000.0)
    assert _checker().passes_tier2(r) is False


def test_passes_tier2_false_trades():
    r = BacktestResult(win_rate=72.0, trade_count=10, total_pnl=50000.0)
    assert _checker().passes_tier2(r) is False


# ── Safety rails ──────────────────────────────────────────────────────────────

def test_passes_safety_rails_clean():
    r = BacktestResult(capital_floor_hit=False, consecutive_losses_max=3, max_drawdown_rupees=0.0)
    assert _checker().passes_safety_rails(r) is True


def test_passes_safety_rails_cap_floor():
    r = BacktestResult(capital_floor_hit=True)
    assert _checker().passes_safety_rails(r) is False


def test_passes_safety_rails_consec_loss():
    cfg = AgentConfig(max_consecutive_losses=7)
    r = BacktestResult(consecutive_losses_max=8)
    assert _checker(cfg).passes_safety_rails(r) is False


def test_passes_safety_rails_consec_loss_at_limit():
    cfg = AgentConfig(max_consecutive_losses=7)
    r = BacktestResult(consecutive_losses_max=7)
    assert _checker(cfg).passes_safety_rails(r) is True


def test_passes_safety_rails_drawdown_exceeded():
    # capital_floor=70000, max_drawdown=20% → limit=14000
    cfg = AgentConfig(capital_floor_rupees=70_000.0, max_drawdown_from_peak_pct=20.0)
    r = BacktestResult(max_drawdown_rupees=15_000.0)
    assert _checker(cfg).passes_safety_rails(r) is False


def test_passes_safety_rails_drawdown_at_limit():
    cfg = AgentConfig(capital_floor_rupees=70_000.0, max_drawdown_from_peak_pct=20.0)
    r = BacktestResult(max_drawdown_rupees=14_000.0)
    assert _checker(cfg).passes_safety_rails(r) is True


# ── Goal achieved ─────────────────────────────────────────────────────────────

def test_check_goal_achieved_true():
    cfg = AgentConfig(consecutive_required=3)
    state = SessionState(consecutive_dual_success=3)
    assert _checker(cfg).check_goal_achieved(state) is True


def test_check_goal_achieved_false():
    cfg = AgentConfig(consecutive_required=3)
    state = SessionState(consecutive_dual_success=2)
    assert _checker(cfg).check_goal_achieved(state) is False


def test_check_goal_achieved_exceeds():
    cfg = AgentConfig(consecutive_required=3)
    state = SessionState(consecutive_dual_success=5)
    assert _checker(cfg).check_goal_achieved(state) is True
