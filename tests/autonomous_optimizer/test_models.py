import pytest
from autonomous_optimizer.models import (
    BacktestResult,
    SessionState,
    normalize,
    composite_score,
)


def test_normalize_clamps():
    assert normalize(200, 0, 100) == 1.0
    assert normalize(-1, 0, 100) == 0.0
    assert normalize(50, 0, 100) == 0.5


def test_normalize_equal_bounds():
    assert normalize(5, 5, 5) == 0.0


def test_composite_score_all_zeros():
    r = BacktestResult()
    score = composite_score(r)
    # win_rate=0 → norm=0, pnl=0 → norm=50k/150k≈0.333, rest=0
    # 0.35*0 + 0.30*(50000/150000) + 0.20*0 + 0.10*0 + 0.05*(2/6)
    expected = 0.30 * normalize(0.0, -50_000, 100_000) + 0.05 * normalize(0.0, -2, 4)
    assert abs(score - expected) < 1e-9


def test_composite_score_perfect():
    r = BacktestResult(
        win_rate=100.0,
        total_pnl=100_000.0,
        trades_per_day=5.0,
        profit_factor=4.0,
        sharpe_ratio=4.0,
    )
    assert composite_score(r) == pytest.approx(1.0)


def test_composite_score_partial():
    # Only win_rate=70, everything else at minimum → score = 0.35 * 0.7
    r = BacktestResult(
        win_rate=70.0,
        total_pnl=-50_000.0,
        trades_per_day=0.0,
        profit_factor=0.0,
        sharpe_ratio=-2.0,
    )
    expected = 0.35 * 0.7
    assert composite_score(r) == pytest.approx(expected)


def test_session_state_defaults():
    s = SessionState()
    assert s.iteration == 0
    assert s.phase == "A"
    assert s.approaches_tried == []
    assert s.blocked_approaches == []
    assert s.insights == []
    assert s.wr_trajectory == []
    assert s.pnl_trajectory == []
    assert s.trade_count_trajectory == []
    assert s.composite_score_trajectory == []
    assert s.hypothesis_embeddings == []
    assert s.current_hypothesis_slug == ""


def test_backtest_result_defaults():
    r = BacktestResult()
    assert r.capital_floor_hit is False
    assert r.win_rate == 0.0
    assert r.trade_count == 0
    assert r.pnl_by_week == []
    assert r.raw == {}
