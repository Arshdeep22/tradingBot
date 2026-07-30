"""The trading agent — orchestrates tools + LLM per bar.

Public entrypoints:
  * `TradingAgent.process_bar(symbol, bar_index)` — one decision cycle.
  * `TradingAgent.close_all_positions(reason=...)` — used at end of run.

The high-level `run_backtest(...)` /  `run_paper()` loops live in
`trading_agent/runner.py` which drives this class over a stream of bars.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db

from trading_agent.config import TradingAgentConfig, load_config
from trading_agent.memory import TradingMemory, get_memory
from trading_agent.llm_advisor import LLMAdvisor, Decision
from trading_agent.tools import (
    MarketDataTool, IndicatorTool, StrategyTool, RiskTool, BrokerTool,
)

logger = logging.getLogger(__name__)


@dataclass
class BarOutcome:
    """What happened for a single (symbol, bar) processing step."""
    symbol: str
    bar_index: int
    decision: str                    # BUY | SELL | HOLD | CLOSE
    trade_id: Optional[int] = None
    reason: str = ""


class TradingAgent:
    def __init__(self, run_id: str, *,
                 config: Optional[TradingAgentConfig] = None,
                 db: Optional[AgentDB] = None,
                 market_data: Optional[MarketDataTool] = None):
        self.db = db or get_agent_db()
        self.config = config or load_config(self.db)
        self.memory: TradingMemory = get_memory(self.db)
        self.run_id = run_id

        # Tools ------------------------------------------------------------
        self.market_data = market_data or MarketDataTool(db=self.db)
        self.indicators = IndicatorTool(db=self.db)
        self.strategy = StrategyTool(db=self.db,
                                     params=self.config.strategy_params)
        self.risk = RiskTool(db=self.db, params=self.config.risk_params)
        self.broker = BrokerTool(
            db=self.db,
            starting_capital=float(
                self.config.risk_params.get("starting_capital_rupees", 100_000.0)
            ),
            mode=self.config.mode if self.config.mode != "live" else "paper",
        )
        self.llm = LLMAdvisor(
            model=self.config.llm_model,
            system_prompt=self.config.system_prompt,
            db=self.db,
        )

        # Per-run counters -------------------------------------------------
        self._trades_today: dict[str, int] = {}     # date-string -> count

    # ── main per-bar decision cycle ────────────────────────────────────────
    def process_bar(self, symbol: str, bar_index: int) -> BarOutcome:
        # 1. fetch bars (from cache during backtest)
        bars_out = self.market_data.get_bars(
            symbol=symbol,
            timeframe=self.config.strategy_params.get("timeframe", "15m"),
            up_to_index=bar_index,
            lookback=100,
        )
        df = bars_out["df"]
        if df is None or len(df) < 20:
            return BarOutcome(symbol, bar_index, "HOLD", reason="not_enough_bars")

        # 2. price stops on the current bar BEFORE any new decision
        last = df.iloc[-1]
        try:
            hits = self.broker.check_stops(symbol,
                                            float(last["high"]),
                                            float(last["low"]))
        except Exception:
            hits = []
        for trade_id, fill_price, reason in hits:
            self._close_and_persist(trade_id, fill_price, reason)

        # 3. indicators
        ind = self.indicators.compute(
            df,
            atr_period=int(self.config.strategy_params.get("atr_period", 14)),
            rsi_period=int(self.config.strategy_params.get("rsi_period", 14)),
        )

        # 4. strategy candidate
        signal = self.strategy.scan(
            df, ind,
            zone_score_threshold=self.config.strategy_params.get(
                "zone_score_threshold", 60
            ),
        )

        # 5. LLM decision (per-signal cadence: only call when strategy fires)
        if signal["signal"] == "none":
            return BarOutcome(symbol, bar_index, "HOLD",
                              reason=signal.get("reason", "no_signal"))

        lessons = self.memory.get_lessons(symbol=symbol, limit=15)
        bar_ts = str(getattr(last, "name", bar_index))
        context = {
            "bar_ts": bar_ts,
            "close": float(last["close"]),
            "indicators": ind,
        }
        decision = self.llm.decide(
            run_id=self.run_id, symbol=symbol,
            context=context, lessons=lessons,
            strategy_signal=signal,
        )
        return self._act_on_decision(symbol, bar_index, df, ind,
                                      signal, decision)

    # ── decision execution ─────────────────────────────────────────────────
    def _act_on_decision(self, symbol: str, bar_index: int, df,
                          ind: dict, signal: dict,
                          decision: Decision) -> BarOutcome:
        min_conf = float(
            self.config.strategy_params.get("min_confidence_to_trade", 0.55)
        )
        if decision.decision in ("HOLD", "CLOSE"):
            return BarOutcome(symbol, bar_index, decision.decision,
                              reason=decision.reasoning)
        if decision.confidence < min_conf:
            return BarOutcome(symbol, bar_index, "HOLD",
                              reason=f"confidence {decision.confidence:.2f} < {min_conf:.2f}")

        # Portfolio-level check
        open_positions = len(self.broker.broker.positions)
        trades_today = sum(self._trades_today.values())
        gate = self.risk.can_open_new(
            open_positions=open_positions, trades_today=trades_today,
        )
        if not gate["ok"]:
            return BarOutcome(symbol, bar_index, "HOLD",
                              reason=f"risk_gate: {gate['reason']}")

        # Size the position
        side = "BUY" if decision.decision == "BUY" else "SELL"
        entry = float(df.iloc[-1]["close"])
        sl = signal.get("suggested_sl")
        tp = signal.get("suggested_tp")
        if sl is None:
            return BarOutcome(symbol, bar_index, "HOLD",
                              reason="strategy did not suggest a stop_loss")

        size = self.risk.size_position(
            capital=self.broker.broker.capital,
            entry=entry, stop_loss=float(sl), side=side,
        )
        if not size["ok"]:
            return BarOutcome(symbol, bar_index, "HOLD",
                              reason=f"risk_sizing: {size['reason']}")

        # Persist to DB, then send to broker
        trade_id = self.db.record_trading_trade(
            run_id=self.run_id, symbol=symbol, side=side,
            quantity=size["quantity"], entry_price=entry,
            stop_loss=float(sl), target=float(tp) if tp is not None else None,
            decision_id=decision.decision_id,
        )
        try:
            self.broker.open_position(
                trade_id=trade_id, symbol=symbol, side=side,
                quantity=size["quantity"], entry_price=entry,
                stop_loss=float(sl),
                target=float(tp) if tp is not None else None,
            )
        except Exception as e:
            logger.error("broker.open_position failed: %s", e)
            return BarOutcome(symbol, bar_index, "HOLD",
                              reason=f"broker_error:{e}")

        self._trades_today[str(df.iloc[-1].name)[:10]] = (
            self._trades_today.get(str(df.iloc[-1].name)[:10], 0) + 1
        )
        return BarOutcome(symbol, bar_index, side, trade_id=trade_id,
                          reason=decision.reasoning)

    def _close_and_persist(self, trade_id: int, exit_price: float,
                            reason: str) -> None:
        try:
            rec = self.broker.close_position(trade_id, exit_price, reason=reason)
        except Exception as e:
            logger.error("broker.close_position failed for %s: %s", trade_id, e)
            return
        pnl = rec.get("pnl", 0.0)
        pnl_pct = None
        if rec.get("entry_price"):
            direction = 1.0 if rec["side"] == "BUY" else -1.0
            pnl_pct = direction * (exit_price / rec["entry_price"] - 1.0) * 100.0
        self.db.close_trading_trade(
            trade_id=trade_id, exit_price=exit_price,
            pnl=pnl, pnl_percent=pnl_pct, exit_reason=reason,
        )

    # ── run wrap-up ────────────────────────────────────────────────────────
    def close_all_positions(self, prices: dict[str, float],
                             reason: str = "end_of_run") -> None:
        for tid, pos in list(self.broker.broker.positions.items()):
            price = prices.get(pos.symbol) or pos.entry_price
            self._close_and_persist(tid, price, reason)

    def summarise(self) -> dict[str, Any]:
        """Compute the run metrics the optimizer cares about."""
        trades = self.db.get_trading_trades(self.run_id)
        closed = [t for t in trades if t["status"] == "CLOSED"]
        n = len(closed)
        wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        total_pnl = sum((t.get("pnl") or 0.0) for t in closed)
        win_rate = (wins / n * 100.0) if n else 0.0
        return {
            "trade_count": n, "wins": wins, "win_rate": win_rate,
            "total_pnl": round(total_pnl, 2),
            "open_positions_left": len(self.broker.broker.positions),
        }