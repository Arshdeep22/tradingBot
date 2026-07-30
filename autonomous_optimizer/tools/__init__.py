"""Optimizer's own tools that ACT on the trading agent.

Currently:
  * `trading_bot_tool.TradingBotTool` — runs a `TradingAgentRunner`
    (backtest) after hot-reloading the `trading_agent` package so the
    optimizer's latest edits take effect immediately.
"""
from autonomous_optimizer.tools.trading_bot_tool import TradingBotTool

__all__ = ["TradingBotTool"]