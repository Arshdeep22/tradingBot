"""Optimizer tool: drive the Trading Agent.

Two responsibilities:
  1. Hot-reload every module under `trading_agent.*` and `strategies.*`
     so that any code edit the optimizer just made takes effect on the
     very next run — no subprocess required.
  2. Invoke `TradingAgentRunner.run_backtest(...)` (or paper mode later)
     and return a compact result the optimizer's success-checker can
     score.

Every call is traced to `tool_invocations` with `agent='optimizer'` and
`tool_name='trading_bot'`, so the optimizer's own audit trail records
"iteration N asked the trading agent to run for D days". The trading
agent's OWN traces (agent='trading_bot') are written by its tools while
inside the `agent_scope('trading_bot', run_id=...)` block.
"""
from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import asdict
from typing import Any, Optional

from autonomous_optimizer.storage.agent_db import (
    AgentDB, get_agent_db,
)

logger = logging.getLogger(__name__)


# Prefixes we hot-reload when the optimizer's code editor may have touched
# them. Order matters: leaf modules first, packages last.
_RELOAD_PREFIXES: tuple[str, ...] = (
    "trading_agent.tools.",
    "trading_agent.",
    "strategies.",
)


class TradingBotTool:
    """Optimizer-side controller for the trading agent."""

    tool_name = "trading_bot"

    def __init__(self, db: Optional[AgentDB] = None):
        self._db = db or get_agent_db()

    # ── public API ─────────────────────────────────────────────────────────
    def run_backtest(self, *, days: int = 10,
                     symbols: Optional[list[str]] = None,
                     max_bars_per_symbol: Optional[int] = None,
                     iteration: Optional[int] = None,
                     hot_reload: bool = True) -> dict[str, Any]:
        """Reload the trading-agent package (if requested) and run one
        backtest. Returns a dict the optimizer can score directly.
        """
        args = {
            "days": days, "symbols": symbols,
            "max_bars_per_symbol": max_bars_per_symbol,
            "hot_reload": hot_reload,
        }
        try:
            if hot_reload:
                reloaded = self._hot_reload()
                logger.info("Hot-reloaded %d trading-agent modules", reloaded)

            # Import LATE so the reloaded modules take effect.
            from trading_agent.runner import TradingAgentRunner
            runner = TradingAgentRunner(db=self._db)
            result = runner.run_backtest(
                days=days, symbols=symbols,
                max_bars_per_symbol=max_bars_per_symbol,
                triggered_by="optimizer",
            )
            payload = asdict(result)
            self._db.record_tool(
                tool_name=self.tool_name, action="run_backtest",
                args=args, result=payload, ok=result.ok, error=result.error,
                iteration=iteration,
                agent="optimizer",
            )
            return payload
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            self._db.record_tool(
                tool_name=self.tool_name, action="run_backtest",
                args=args, result={}, ok=False, error=err,
                iteration=iteration, agent="optimizer",
            )
            raise

    # ── hot-reload internals ───────────────────────────────────────────────
    def _hot_reload(self) -> int:
        """Drop-and-reimport every module whose name starts with one of the
        watched prefixes. Returns how many modules were reloaded.
        """
        to_drop = [
            name for name in list(sys.modules)
            if any(name == p.rstrip(".") or name.startswith(p)
                   for p in _RELOAD_PREFIXES)
        ]
        for name in to_drop:
            sys.modules.pop(name, None)

        # Re-import the top-level packages so submodule imports rebuild
        # cleanly on next use. We don't force-import EVERY submodule —
        # they'll be re-imported lazily by whoever uses them.
        try:
            importlib.import_module("trading_agent")
        except Exception as e:
            logger.warning("Re-import of trading_agent failed: %s", e)
        try:
            importlib.import_module("strategies")
        except Exception:
            pass  # strategies may not have an __init__.py we care about
        return len(to_drop)