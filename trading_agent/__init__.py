"""Trading Agent — a self-contained LLM-driven trading bot.

Owns its OWN memory and OWN logs (all stored in `database/agent.db` with
`agent='trading_bot'`) so the Optimizer Agent can drive it, observe every
tool call and LLM decision, and tune the bot's code, prompt, or memory
without polluting the optimizer's state.

Modes (chosen via `trading_agent_config.mode`):
  * "backtest" — replay historical bars; no real broker
  * "paper"    — live market data but simulated fills
  * "live"     — real market data + real broker (future)
"""
from trading_agent.config import TradingAgentConfig, load_config, save_config
from trading_agent.agent import TradingAgent
from trading_agent.runner import TradingAgentRunner, RunResult

__all__ = [
    "TradingAgent",
    "TradingAgentRunner",
    "TradingAgentConfig",
    "RunResult",
    "load_config",
    "save_config",
]