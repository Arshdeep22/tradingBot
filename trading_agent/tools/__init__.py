"""Trading-agent tools.

Every tool inherits from `ToolBase` which auto-traces every call into
`tool_invocations` with `agent='trading_bot'` and the current `run_id`
(picked up from `contextvars`). That way the Optimizer can query exactly
which trading-bot tool failed inside any given run.
"""
from trading_agent.tools.base import ToolBase, ToolError
from trading_agent.tools.market_data import MarketDataTool
from trading_agent.tools.indicators import IndicatorTool
from trading_agent.tools.strategy import StrategyTool
from trading_agent.tools.risk import RiskTool
from trading_agent.tools.broker import BrokerTool, PaperBroker

__all__ = [
    "ToolBase",
    "ToolError",
    "MarketDataTool",
    "IndicatorTool",
    "StrategyTool",
    "RiskTool",
    "BrokerTool",
    "PaperBroker",
]