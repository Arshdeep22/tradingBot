import json
import os
from unittest.mock import MagicMock, patch

import pytest

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.llm.observer import Observer
from autonomous_optimizer.models import BacktestResult, Observation


def _make_observer(tmp_path=None) -> Observer:
    config = AgentConfig()
    if tmp_path:
        config.repo_root = str(tmp_path)
    git_ops = MagicMock()
    git_ops.current_diff.return_value = ""
    git_ops.recent_blame.return_value = []
    return Observer(config, git_ops)


def _clean_result(**kwargs) -> BacktestResult:
    defaults = dict(
        win_rate=65.0, total_pnl=30000.0, trade_count=20,
        trades_per_day=2.0, profit_factor=1.8, sharpe_ratio=1.2,
        max_drawdown_rupees=5000.0, pnl_by_week=[10000.0, 8000.0, 7000.0, 5000.0],
        capital_floor_hit=False, consecutive_losses_max=3, days_run=10,
    )
    defaults.update(kwargs)
    return BacktestResult(**defaults)


def test_observe_returns_observation_type(tmp_path):
    obs = _make_observer(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = obs.observe(1, _clean_result(), "tests passed")
    assert isinstance(result, Observation)
    assert result.iteration == 1


def test_anomaly_fragile_pnl():
    obs = _make_observer()
    result = obs._detect_anomalies(BacktestResult(
        trade_count=10, win_rate=60.0, total_pnl=50000.0,
        pnl_by_week=[45000.0, 5000.0],
    ))
    assert any("FRAGILE" in f for f in result)


def test_anomaly_no_trades():
    obs = _make_observer()
    result = obs._detect_anomalies(BacktestResult(trade_count=0))
    assert any("NO_TRADES" in f for f in result)


def test_anomaly_all_losses():
    obs = _make_observer()
    result = obs._detect_anomalies(BacktestResult(trade_count=5, win_rate=0.0))
    assert any("ALL_LOSSES" in f for f in result)


def test_no_anomalies_clean_result():
    obs = _make_observer()
    result = obs._detect_anomalies(_clean_result())
    assert result == []


def test_regime_state_unknown_no_file(tmp_path):
    obs = _make_observer(tmp_path)
    assert obs._regime_state() == "unknown"


def test_regime_state_reads_from_file(tmp_path):
    report_dir = tmp_path / "reports" / "training"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "latest_backtest_result.json"
    report_file.write_text(json.dumps({"regime": "trending"}))
    obs = _make_observer(tmp_path)
    assert obs._regime_state() == "trending"
