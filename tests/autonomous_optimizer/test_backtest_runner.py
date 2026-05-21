import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from autonomous_optimizer.backtest_runner import BacktestRunner, BacktestTimeoutError, BacktestError
from autonomous_optimizer.config import AgentConfig

DEFAULT_CONFIG = AgentConfig()


def _sample_report():
    return {
        "overall_win_rate": 65.0,
        "total_pnl": 22000.0,
        "total_triggered": 35,
        "days_run": 50,
        "weekly_summaries": [
            {"pnl": 4000.0, "win_rate": 70.0},
            {"pnl": 3000.0, "win_rate": 60.0},
        ],
    }


def test_parse_report_maps_fields(tmp_path):
    path = tmp_path / "latest_backtest_result.json"
    path.write_text(json.dumps(_sample_report()))
    runner = BacktestRunner(DEFAULT_CONFIG)
    result = runner._parse_report(str(path))
    assert result.win_rate == 65.0
    assert result.total_pnl == 22000.0
    assert result.trade_count == 35
    assert result.days_run == 50
    assert len(result.pnl_by_week) == 2
    assert result.pnl_by_week == [4000.0, 3000.0]


def test_parse_report_trades_per_day(tmp_path):
    path = tmp_path / "latest_backtest_result.json"
    path.write_text(json.dumps(_sample_report()))
    runner = BacktestRunner(DEFAULT_CONFIG)
    result = runner._parse_report(str(path))
    assert result.trades_per_day == pytest.approx(35 / 50)


def test_parse_report_profit_factor(tmp_path):
    report = _sample_report()
    report["weekly_summaries"] = [{"pnl": 6000.0}, {"pnl": -2000.0}]
    path = tmp_path / "r.json"
    path.write_text(json.dumps(report))
    result = BacktestRunner(DEFAULT_CONFIG)._parse_report(str(path))
    assert result.profit_factor == pytest.approx(6000.0 / 2000.0)


def test_parse_report_profit_factor_no_losses(tmp_path):
    report = _sample_report()
    report["weekly_summaries"] = [{"pnl": 5000.0}, {"pnl": 3000.0}]
    path = tmp_path / "r.json"
    path.write_text(json.dumps(report))
    result = BacktestRunner(DEFAULT_CONFIG)._parse_report(str(path))
    assert result.profit_factor == 1.0


def test_parse_report_defaults_for_missing_fields(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"overall_win_rate": 50.0}))
    result = BacktestRunner(DEFAULT_CONFIG)._parse_report(str(path))
    assert result.trade_count == 0
    assert result.days_run == 0
    assert result.trades_per_day == 0.0
    assert result.capital_floor_hit is False
    assert result.consecutive_losses_max == 0


def test_subprocess_timeout_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AgentConfig(repo_root=str(tmp_path))
    runner = BacktestRunner(cfg)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1)):
        with pytest.raises(BacktestTimeoutError):
            runner._run_subprocess(days=10)


def test_subprocess_nonzero_exit_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AgentConfig(repo_root=str(tmp_path))
    runner = BacktestRunner(cfg)
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "some error"
    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(BacktestError):
            runner._run_subprocess(days=10)


def test_run_tier1_uses_10_days(tmp_path):
    cfg = AgentConfig(repo_root=str(tmp_path), tier1_days=10)
    runner = BacktestRunner(cfg)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result_path = tmp_path / "reports" / "training" / "latest_backtest_result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(_sample_report()))
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_run):
        runner.run_tier1()

    assert "--days=10" in captured["cmd"]


def test_run_tier2_uses_50_days(tmp_path):
    cfg = AgentConfig(repo_root=str(tmp_path), tier2_days=50)
    runner = BacktestRunner(cfg)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result_path = tmp_path / "reports" / "training" / "latest_backtest_result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(_sample_report()))
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_run):
        runner.run_tier2()

    assert "--days=50" in captured["cmd"]


def test_run_subprocess_includes_no_ai_and_json_output(tmp_path):
    cfg = AgentConfig(repo_root=str(tmp_path))
    runner = BacktestRunner(cfg)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result_path = tmp_path / "reports" / "training" / "latest_backtest_result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(_sample_report()))
        mock = MagicMock()
        mock.returncode = 0
        return mock

    with patch("subprocess.run", side_effect=fake_run):
        runner._run_subprocess(days=10)

    assert "--no-ai" in captured["cmd"]
    assert "--json-output" in captured["cmd"]
