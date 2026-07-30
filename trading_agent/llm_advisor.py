"""LLM advisor for the trading agent.

Wraps the SAP AI Core client (already used by the optimizer). Provides a
single `decide(...)` entrypoint that:
  1. Builds a prompt from system_prompt + lessons + context.
  2. Sends it to the model configured in `trading_agent_config.llm_model`.
  3. Parses `{decision, confidence, reasoning}` from the response.
  4. Traces the call to `tool_invocations` (agent='trading_bot').
  5. Persists the decision to `trading_agent_decisions`.

If SAP AI Core credentials are missing the advisor falls back to a
deterministic rule-based decision (based on the strategy signal) so that
the whole pipeline still runs in tests / CI.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from autonomous_optimizer.storage.agent_db import (
    AgentDB, current_run_id, get_agent_db,
)
from trading_agent.tools.base import ToolBase, traced_action

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    decision: str            # BUY | SELL | HOLD | CLOSE
    confidence: float
    reasoning: str
    raw: str = ""
    decision_id: Optional[int] = None      # set after DB insert
    source: str = "llm"                    # "llm" | "fallback"


def _credentials_present() -> bool:
    keys = ("AICORE_AUTH_URL", "AICORE_API_URL",
            "AICORE_CLIENT_ID", "AICORE_CLIENT_SECRET")
    return all(os.environ.get(k) for k in keys)


class LLMAdvisor(ToolBase):
    tool_name = "llm_advisor"

    def __init__(self, *, model: str, system_prompt: str,
                 db: Optional[AgentDB] = None):
        super().__init__(db=db)
        self._model = model
        self._system_prompt = system_prompt
        self._client = None  # lazy — only if creds are present

    # ── main entrypoint ────────────────────────────────────────────────────
    @traced_action("decide")
    def decide(self, *, run_id: str, symbol: str,
               context: dict[str, Any],
               lessons: list[str],
               strategy_signal: dict[str, Any]) -> Decision:
        """Call the LLM (or fallback) and persist the decision. Returns Decision."""

        # ── Fallback path when creds/library missing ──────────────────────
        if not _credentials_present():
            d = self._fallback_decision(strategy_signal)
            d.decision_id = self._db.record_trading_decision(
                run_id=run_id, symbol=symbol,
                decision=d.decision, confidence=d.confidence,
                reasoning=d.reasoning, raw_llm_response=d.raw,
                bar_ts=str(context.get("bar_ts", "")),
                context={"context": context, "signal": strategy_signal,
                          "lessons": lessons[:10]},
            )
            return d

        # ── Real LLM path ─────────────────────────────────────────────────
        prompt = self._build_user_prompt(symbol, context, lessons, strategy_signal)
        try:
            raw = self._call_llm(prompt)
        except Exception as e:
            logger.warning("LLM call failed (%s) — falling back to rule.", e)
            d = self._fallback_decision(strategy_signal)
            d.reasoning = f"[llm_failed:{e}] " + d.reasoning
            d.decision_id = self._db.record_trading_decision(
                run_id=run_id, symbol=symbol,
                decision=d.decision, confidence=d.confidence,
                reasoning=d.reasoning, raw_llm_response="",
                bar_ts=str(context.get("bar_ts", "")),
                context={"context": context, "signal": strategy_signal},
            )
            return d

        parsed = self._parse_response(raw, fallback=strategy_signal)
        parsed.raw = raw
        parsed.decision_id = self._db.record_trading_decision(
            run_id=run_id, symbol=symbol,
            decision=parsed.decision, confidence=parsed.confidence,
            reasoning=parsed.reasoning, raw_llm_response=raw,
            bar_ts=str(context.get("bar_ts", "")),
            context={"context": context, "signal": strategy_signal,
                      "lessons": lessons[:10]},
        )
        return parsed

    # ── prompt / response plumbing ─────────────────────────────────────────
    def _build_user_prompt(self, symbol: str, context: dict,
                            lessons: list[str],
                            strategy_signal: dict) -> str:
        lesson_block = "\n".join(f"- {l}" for l in lessons[:15]) or "(no lessons yet)"
        return (
            f"Symbol: {symbol}\n"
            f"Bar context:\n{json.dumps(context, indent=2, default=str)}\n\n"
            f"Strategy candidate signal:\n{json.dumps(strategy_signal, indent=2, default=str)}\n\n"
            f"Lessons from prior runs:\n{lesson_block}\n\n"
            f"Reply with a single JSON object: "
            f'{{"decision": "...", "confidence": 0..1, "reasoning": "..."}}'
        )

    def _call_llm(self, user_prompt: str) -> str:
        if self._client is None:
            # Reuse the optimizer's LLM client so we don't duplicate auth logic.
            from autonomous_optimizer.llm.client import AgentLLMClient
            from autonomous_optimizer.config import AgentConfig
            cfg = AgentConfig(llm_model=self._model)
            self._client = AgentLLMClient(cfg)
        # `call(...)` with expect_json=False returns the raw string.
        return self._client.call(
            system_prompt=self._system_prompt,
            user_message=user_prompt,
            expect_json=False,
            max_tokens=512,
            stage="trading_agent",
        )

    _JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

    def _parse_response(self, raw: str, *, fallback: dict) -> Decision:
        try:
            m = self._JSON_RE.search(raw)
            payload = json.loads(m.group(0)) if m else {}
            dec = str(payload.get("decision", "HOLD")).upper()
            if dec not in {"BUY", "SELL", "HOLD", "CLOSE"}:
                dec = "HOLD"
            conf = float(payload.get("confidence", 0.0))
            reasoning = str(payload.get("reasoning", "")).strip()[:500]
            return Decision(decision=dec, confidence=conf, reasoning=reasoning)
        except Exception as e:
            logger.debug("could not parse LLM output (%s); using fallback", e)
            return self._fallback_decision(fallback)

    def _fallback_decision(self, strategy_signal: dict) -> Decision:
        sig = (strategy_signal or {}).get("signal", "none")
        if sig == "long":
            return Decision("BUY", 0.5,
                            f"[fallback] strategy long, score={strategy_signal.get('score')}",
                            source="fallback")
        if sig == "short":
            return Decision("SELL", 0.5,
                            f"[fallback] strategy short, score={strategy_signal.get('score')}",
                            source="fallback")
        return Decision("HOLD", 0.5,
                        "[fallback] no strategy signal",
                        source="fallback")