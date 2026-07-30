"""Optimizer's backtest runner — a thin façade over two implementations.

Modes:
  * `use_trading_agent=True` (default) — drives the in-process Trading
    Agent via `TradingBotTool` with hot-reload. Every trading-bot LLM
    decision and tool call is captured in the DB with `agent='trading_bot'`
    and stamped with the run_id, so the optimizer can inspect *why* the
    bot did what it did (not just the aggregate metrics).

  * `use_trading_agent=False` — falls back to the legacy subprocess-based
    invocation of `historical_trainer.runner`. Kept so existing pipelines
    (and the older tests) still work.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Optional

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult
from autonomous_optimizer.storage.agent_db import get_agent_db

logger = logging.getLogger(__name__)

# Suppress console window on Windows when spawning subprocesses.
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class BacktestTimeoutError(RuntimeError):
    pass


class BacktestError(RuntimeError):
    pass


class BacktestRunner:
    def __init__(self, config: AgentConfig):
        self._config = config
        self._db = get_agent_db()
        # Lazy import to avoid a hard dependency on trading_agent at import
        # time (e.g. in the dry-run smoke test).
        self._trading_tool = None

    # ── public API ─────────────────────────────────────────────────────────
    def run_tier1(self) -> BacktestResult:
        return self._run(days=self._config.tier1_days)

    def run_tier2(self) -> BacktestResult:
        return self._run(days=self._config.tier2_days)

    # ── dispatch ───────────────────────────────────────────────────────────
    def _run(self, days: int) -> BacktestResult:
        if getattr(self._config, "use_trading_agent", True):
            return self._run_via_trading_agent(days=days)
        return self._run_via_subprocess(days=days)

    # ── path 1: drive the in-process Trading Agent ─────────────────────────
    def _run_via_trading_agent(self, days: int) -> BacktestResult:
        if self._trading_tool is None:
            from autonomous_optimizer.tools.trading_bot_tool import TradingBotTool
            self._trading_tool = TradingBotTool(db=self._db)

        symbols = getattr(self._config, "trading_agent_symbols", None) or None
        try:
            payload = self._trading_tool.run_backtest(
                days=days, symbols=symbols, hot_reload=True,
            )
        except Exception as e:
            raise BacktestError(f"trading_agent run failed: {e}") from e

        if not payload.get("ok"):
            raise BacktestError(
                f"trading_agent reported failure: {payload.get('error')}"
            )

        trade_count = int(payload.get("trade_count") or 0)
        win_rate = float(payload.get("win_rate") or 0.0)
        total_pnl = float(payload.get("total_pnl") or 0.0)
        trades_per_day = float(payload.get("trades_per_day") or 0.0)

        # Profit factor + sharpe are not tracked yet in the trading-agent
        # summary; leave as neutral values so composite_score is stable.
        return BacktestResult(
            win_rate=win_rate,
            total_pnl=total_pnl,
            trade_count=trade_count,
            trades_per_day=trades_per_day,
            profit_factor=1.0,
            sharpe_ratio=0.0,
            max_drawdown_rupees=0.0,
            pnl_by_week=[],
            capital_floor_hit=False,
            consecutive_losses_max=0,
            days_run=days,
            raw={"trading_agent": payload},
        )

    # ── path 2: legacy subprocess ──────────────────────────────────────────
    def _run_via_subprocess(self, days: int) -> BacktestResult:
        cmd = [
            sys.executable, "-m", "historical_trainer.runner",
            f"--days={days}", "--no-ai", "--json-output",
        ]
        repo_root = os.path.abspath(self._config.repo_root)
        logger.info("Running legacy subprocess backtest: days=%d, cwd=%s",
                    days, repo_root)

        try:
            proc = subprocess.run(
                cmd, cwd=repo_root,
                timeout=self._config.backtest_timeout_seconds,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
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

        result_path = os.path.join(
            repo_root, "reports", "training", "latest_backtest_result.json",
        )
        return self._parse_report(result_path)

    def _parse_report(self, report_path: str) -> BacktestResult:
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