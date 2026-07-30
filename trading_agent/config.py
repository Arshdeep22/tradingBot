"""Trading-agent configuration — persisted in `trading_agent_config` (DB).

The optimizer is expected to edit these fields (via
`save_config(...)`) between runs to tune the bot's behaviour.
Loading always goes through the DB so every process picks up the newest
values without a subprocess restart.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db


_DEFAULT_SYSTEM_PROMPT = """You are the decision engine of a Nifty-500 intraday trading bot.

Your job on every call: given the current bar's context (indicators,
recent price action, active zone info, and lessons learned from prior
runs), output a single JSON object with exactly these keys:

  {
    "decision":   "BUY" | "SELL" | "HOLD" | "CLOSE",
    "confidence": 0.0..1.0,
    "reasoning":  "one short sentence"
  }

Guardrails (never violate):
  1. Only issue BUY/SELL when a valid zone setup is present in the context.
  2. Respect the risk parameters — never propose a trade that would
     breach `max_risk_pct` of capital.
  3. If uncertain, output HOLD with low confidence, not a random side.
  4. Reasoning must reference concrete numbers from the context (e.g. RSI,
     ATR, zone score) — no hand-wavy answers.
"""


_DEFAULT_RISK_PARAMS: dict[str, Any] = {
    "max_risk_pct_per_trade": 1.0,
    "max_concurrent_positions": 3,
    "max_trades_per_day": 3,
    "capital_floor_rupees": 70000.0,
    "starting_capital_rupees": 100000.0,
}

_DEFAULT_STRATEGY_PARAMS: dict[str, Any] = {
    "timeframe": "15m",
    "atr_period": 14,
    "rsi_period": 14,
    "zone_score_threshold": 60,
    "min_confidence_to_trade": 0.55,
}

_DEFAULT_SYMBOLS: list[str] = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]


@dataclass
class TradingAgentConfig:
    """In-memory view of `trading_agent_config`. Immutable within a run;
    a new run reloads from the DB."""

    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    llm_model: str = "anthropic--claude-4.5-haiku"
    mode: str = "backtest"                          # backtest | paper | live
    risk_params: dict[str, Any] = field(
        default_factory=lambda: dict(_DEFAULT_RISK_PARAMS)
    )
    strategy_params: dict[str, Any] = field(
        default_factory=lambda: dict(_DEFAULT_STRATEGY_PARAMS)
    )
    symbols: list[str] = field(
        default_factory=lambda: list(_DEFAULT_SYMBOLS)
    )

    def to_dict(self) -> dict:
        return {
            "system_prompt": self.system_prompt,
            "llm_model": self.llm_model,
            "mode": self.mode,
            "risk_params": self.risk_params,
            "strategy_params": self.strategy_params,
            "symbols": self.symbols,
        }


def load_config(db: AgentDB | None = None) -> TradingAgentConfig:
    """Load the trading-agent config from the DB, filling in defaults for
    any missing/empty fields (so a fresh DB Just Works)."""
    db = db or get_agent_db()
    raw = db.load_trading_config()

    cfg = TradingAgentConfig(
        system_prompt=raw.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT,
        llm_model=raw.get("llm_model") or "anthropic--claude-4.5-haiku",
        mode=raw.get("mode") or "backtest",
        risk_params={**_DEFAULT_RISK_PARAMS, **(raw.get("risk_params") or {})},
        strategy_params={
            **_DEFAULT_STRATEGY_PARAMS, **(raw.get("strategy_params") or {})
        },
        symbols=list(raw.get("symbols") or _DEFAULT_SYMBOLS),
    )
    return cfg


def save_config(cfg: TradingAgentConfig, db: AgentDB | None = None) -> None:
    """Persist the config back to the DB (used by the optimizer)."""
    db = db or get_agent_db()
    db.save_trading_config(cfg.to_dict())


# ── Guardrail validation used by the optimizer's critic ───────────────────
_MANDATORY_PROMPT_SECTIONS = [
    "guardrails",
    "decision",
    "reasoning",
]

_MAX_PROMPT_LENGTH = 8000


def validate_system_prompt(prompt: str) -> tuple[bool, str]:
    """Return (ok, reason). Used by the optimizer's Critic before it lets
    a rewritten prompt be committed to the DB.
    """
    if not prompt or not prompt.strip():
        return False, "prompt is empty"
    if len(prompt) > _MAX_PROMPT_LENGTH:
        return False, f"prompt exceeds {_MAX_PROMPT_LENGTH} chars"
    lower = prompt.lower()
    missing = [s for s in _MANDATORY_PROMPT_SECTIONS if s not in lower]
    if missing:
        return False, f"prompt is missing mandatory sections: {missing}"
    return True, "ok"