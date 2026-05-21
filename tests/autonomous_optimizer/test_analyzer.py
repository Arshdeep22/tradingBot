from unittest.mock import MagicMock

import pytest

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.llm.analyzer import Analyzer
from autonomous_optimizer.models import BacktestResult, Observation, RootCause


def _make_observation() -> Observation:
    return Observation(
        backtest=BacktestResult(
            win_rate=55.0, total_pnl=20000.0, trade_count=15,
            trades_per_day=1.5, profit_factor=1.5, sharpe_ratio=1.0,
            max_drawdown_rupees=4000.0, days_run=10,
        ),
        code_diff="",
        test_output="",
        anomaly_flags=[],
        data_freshness={},
        regime_state="trending",
        git_blame_recent=[],
        iteration=3,
    )


def _make_analyzer() -> tuple[Analyzer, MagicMock]:
    llm = MagicMock()
    analyzer = Analyzer(AgentConfig(), llm)
    return analyzer, llm


def _valid_response(**overrides) -> dict:
    base = {
        "category": "entry_timing",
        "evidence": ["win rate low", "trades miss entry"],
        "confidence": 0.7,
        "ruling_out": ["exit_logic: exits are fine", "zone_quality: zones look good"],
    }
    base.update(overrides)
    return base


def test_analyze_returns_root_cause():
    analyzer, llm = _make_analyzer()
    llm.call.return_value = _valid_response()
    result = analyzer.analyze(_make_observation(), {})
    assert isinstance(result, RootCause)


def test_analyze_valid_category():
    analyzer, llm = _make_analyzer()
    llm.call.return_value = _valid_response(category="entry_timing")
    result = analyzer.analyze(_make_observation(), {})
    assert result.category == "entry_timing"


def test_analyze_invalid_category_raises():
    analyzer, llm = _make_analyzer()
    llm.call.return_value = _valid_response(category="wrong_category")
    with pytest.raises(ValueError, match="Invalid root cause category"):
        analyzer.analyze(_make_observation(), {})


def test_analyze_confidence_clamped_high():
    analyzer, llm = _make_analyzer()
    llm.call.return_value = _valid_response(confidence=1.5)
    result = analyzer.analyze(_make_observation(), {})
    assert result.confidence == 1.0


def test_analyze_confidence_clamped_low():
    analyzer, llm = _make_analyzer()
    llm.call.return_value = _valid_response(confidence=-0.1)
    result = analyzer.analyze(_make_observation(), {})
    assert result.confidence == 0.0


def test_user_message_under_1500_tokens():
    analyzer, _ = _make_analyzer()
    context = {
        "recent": {"iterations": [
            {"iteration": i, "result": {"win_rate": 50.0, "total_pnl": 1000, "trade_count": 5},
             "hypothesis": f"hyp-{i}"}
            for i in range(5)
        ]},
        "learned": ["insight A", "insight B"],
    }
    msg = analyzer._build_user_message(_make_observation(), context)
    assert len(msg) < 6000
