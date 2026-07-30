import subprocess
import json
import os
import logging
import sys

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult

logger = logging.getLogger(__name__)

# Suppress console window on Windows when spawning subprocesses
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class BacktestTimeoutError(RuntimeError):
    pass


class BacktestError(RuntimeError):
    pass


class BacktestRunner:
    def __init__(self, config: AgentConfig):
        self._config = config

    def run_tier1(self) -> BacktestResult:
        """Run a quick 10-day backtest (Tier 1 filter)."""
        return self._run_subprocess(days=self._config.tier1_days)

    def run_tier2(self) -> BacktestResult:
        """Run a full 50-day backtest (Tier 2 validation)."""
        return self._run_subprocess(days=self._config.tier2_days)

    def _run_subprocess(self, days: int) -> BacktestResult:
        """Spawn subprocess, wait for completion, parse result."""
        cmd = [
            sys.executable, "-m", "historical_trainer.runner",
            f"--days={days}", "--no-ai", "--json-output",
        ]
        repo_root = os.path.abspath(self._config.repo_root)
        logger.info("Running backtest: days=%d, cwd=%s", days, repo_root)

        try:
            proc = subprocess.run(
                cmd,
                cwd=repo_root,
                timeout=self._config.backtest_timeout_seconds,
                capture_output=True,
                text=True,
                creationflags=_CREATIONFLAGS,
            )
        except subprocess.TimeoutExpired as exc:
            raise BacktestTimeoutError(
                f"Backtest timed out after {self._config.backtest_timeout_seconds}s"
            ) from exc

        if proc.returncode != 0:
            raise BacktestError(
                f"Backtest subprocess exited with code {proc.returncode}.\n"
                f"stderr: {proc.stderr[-2000:]}"
            )

        result_path = os.path.join(repo_root, "reports", "training", "latest_backtest_result.json")
        return self._parse_report(result_path)

    def _parse_report(self, report_path: str) -> BacktestResult:
        """Parse the JSON backtest result file into a BacktestResult."""
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)

        days_run = data.get("days_run", 0)
        trade_count = data.get("total_triggered", 0)
        trades_per_day = trade_count / days_run if days_run > 0 else 0.0

        weekly_summaries = data.get("weekly_summaries", [])
        pnl_by_week = [w.get("pnl", 0.0) for w in weekly_summaries]

        winning_pnl = sum(p for p in pnl_by_week if p > 0)
        losing_pnl = abs(sum(p for p in pnl_by_week if p < 0))
        profit_factor = winning_pnl / losing_pnl if losing_pnl > 0 else 1.0

        return BacktestResult(
            win_rate=data.get("overall_win_rate", 0.0),
            total_pnl=data.get("total_pnl", 0.0),
            trade_count=trade_count,
            trades_per_day=trades_per_day,
            profit_factor=profit_factor,
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            max_drawdown_rupees=data.get("max_drawdown_rupees", 0.0),
            pnl_by_week=pnl_by_week,
            capital_floor_hit=data.get("capital_floor_hit", False),
            consecutive_losses_max=data.get("consecutive_losses_max", 0),
            days_run=days_run,
            raw=data,
        )
