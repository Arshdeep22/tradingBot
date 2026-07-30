"""TradingAgentRunner — drives a `TradingAgent` over a stream of bars.

Two entrypoints:

* `run_backtest(days=..., symbols=...)` — pulls historical bars via
  `core.data_fetcher.DataFetcher` (or a pre-supplied per-symbol dict),
  caches them, then walks bar-by-bar calling `agent.process_bar(...)`.
  Everything lands in `trading_agent_runs / _decisions / _trades /
  runtime_logs / tool_invocations` with the same `run_id`.

* `run_paper()`  — same loop but real-time, hitting live data at each
  tick. (Sketch — enable after the backtest loop consistently produces
  good results.)
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from autonomous_optimizer.storage.agent_db import (
    AgentDB, agent_scope, get_agent_db,
)

from trading_agent.agent import TradingAgent, BarOutcome
from trading_agent.config import TradingAgentConfig, load_config

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    run_id: str
    mode: str
    trade_count: int
    win_rate: float
    total_pnl: float
    trades_per_day: float
    days: Optional[int]
    ok: bool = True
    error: Optional[str] = None


class TradingAgentRunner:
    def __init__(self, *, config: Optional[TradingAgentConfig] = None,
                 db: Optional[AgentDB] = None):
        self.db = db or get_agent_db()
        self.config = config or load_config(self.db)

    # ── backtest ───────────────────────────────────────────────────────────
    def run_backtest(self, *, days: int = 10,
                     symbols: Optional[list[str]] = None,
                     cached_bars: Optional[dict] = None,
                     max_bars_per_symbol: Optional[int] = None,
                     triggered_by: str = "optimizer") -> RunResult:
        """Replay historical bars for each symbol.

        Parameters
        ----------
        cached_bars : dict[str, pandas.DataFrame], optional
            If supplied, uses these DataFrames directly (nice for tests
            and reproducibility). Each df is expected to have lowercase
            ohlcv columns and a DatetimeIndex.
        """
        symbols = symbols or self.config.symbols
        run_id = f"tarun-{uuid.uuid4().hex[:12]}"

        # Enter agent scope FIRST so every log line and tool invocation is
        # correctly tagged with agent='trading_bot' and this run_id.
        with agent_scope("trading_bot", run_id=run_id):
            self.db.start_trading_run(
                run_id=run_id, mode="backtest",
                days=days, symbols=symbols, triggered_by=triggered_by,
            )
            logger.info("Trading agent backtest starting run_id=%s "
                        "symbols=%s days=%s", run_id, symbols, days)
            agent = TradingAgent(run_id=run_id, config=self.config, db=self.db)

            # Load or accept cached bars, populate the market_data cache.
            per_symbol_bars = cached_bars or self._load_bars(symbols, days=days)
            for sym, df in per_symbol_bars.items():
                agent.market_data.set_cache(sym, df)

            error: Optional[str] = None
            try:
                for sym, df in per_symbol_bars.items():
                    total = len(df)
                    if total < 30:
                        logger.warning("Skipping %s — only %d bars", sym, total)
                        continue
                    end = total if max_bars_per_symbol is None \
                        else min(total, max_bars_per_symbol + 30)
                    # Start from index 30 so indicators have warm-up.
                    for i in range(30, end):
                        outcome = agent.process_bar(sym, bar_index=i)
                        if outcome.decision != "HOLD":
                            logger.info("[%s bar=%d] %s (%s)",
                                        sym, i, outcome.decision, outcome.reason)

                # End-of-run: force-close remaining positions at last close
                last_prices = {
                    sym: float(df.iloc[-1]["close"])
                    for sym, df in per_symbol_bars.items() if len(df)
                }
                agent.close_all_positions(last_prices, reason="end_of_backtest")
            except Exception as exc:
                logger.exception("Trading agent backtest crashed")
                error = f"{type(exc).__name__}: {exc}"

            summary = agent.summarise()
            trades_per_day = (summary["trade_count"] / days) if days else 0.0
            self.db.end_trading_run(
                run_id=run_id,
                win_rate=summary["win_rate"],
                total_pnl=summary["total_pnl"],
                trade_count=summary["trade_count"],
                trades_per_day=trades_per_day,
                notes=(f"open_positions_left={summary['open_positions_left']}"),
                ok=(error is None), error=error,
            )
            logger.info("Trading agent backtest done run_id=%s summary=%s",
                        run_id, summary)
            return RunResult(
                run_id=run_id, mode="backtest",
                trade_count=summary["trade_count"],
                win_rate=summary["win_rate"],
                total_pnl=summary["total_pnl"],
                trades_per_day=trades_per_day,
                days=days, ok=(error is None), error=error,
            )

    # ── paper (stub) ───────────────────────────────────────────────────────
    def run_paper(self, *, poll_seconds: int = 60,
                  max_iters: Optional[int] = None) -> RunResult:
        """Live-data loop (stub). Wires up the same agent + tools but polls
        `MarketDataTool.get_current_price` instead of walking cached bars.

        Kept minimal — the optimizer works on the backtest path first;
        paper is only used once the strategy is stable enough for real
        forward-testing. Extend with your own broker integration.
        """
        raise NotImplementedError(
            "paper mode is stubbed — implement once backtest results are stable"
        )

    # ── data loading ───────────────────────────────────────────────────────
    def _load_bars(self, symbols: list[str], *, days: int) -> dict:
        """Best-effort load. Uses `historical_trainer` if present, else
        falls back to `core.data_fetcher.DataFetcher`."""
        try:
            return self._load_via_historical_trainer(symbols, days=days)
        except Exception as e:
            logger.info("historical_trainer path unavailable (%s); "
                        "falling back to DataFetcher", e)
        return self._load_via_data_fetcher(symbols, days=days)

    def _load_via_historical_trainer(self, symbols: list[str],
                                     *, days: int) -> dict:
        # historical_trainer already caches Nifty500 bars; try to reuse.
        from historical_trainer.data_loader import load_symbol_history  # type: ignore
        out: dict = {}
        for sym in symbols:
            df = load_symbol_history(sym, days=days)
            if df is None or df.empty:
                continue
            df.columns = [c.lower() for c in df.columns]
            out[sym] = df
        if not out:
            raise RuntimeError("historical_trainer returned no data")
        return out

    def _load_via_data_fetcher(self, symbols: list[str],
                               *, days: int) -> dict:
        from core.data_fetcher import DataFetcher
        f = DataFetcher()
        period_map = {
            1: "1d", 5: "5d", 10: "1mo", 15: "1mo", 20: "1mo",
            30: "3mo", 50: "3mo", 60: "3mo", 90: "3mo",
        }
        period = period_map.get(days, "3mo")
        out: dict = {}
        tf = self.config.strategy_params.get("timeframe", "15m")
        for sym in symbols:
            df = f.get_data(sym, timeframe=tf, period=period)
            if df is None or df.empty:
                continue
            df.columns = [c.lower() for c in df.columns]
            out[sym] = df
        return out