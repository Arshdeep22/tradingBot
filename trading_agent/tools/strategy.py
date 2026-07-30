"""Strategy tool — decides whether the current bar has a valid setup.

This is intentionally a THIN wrapper: it just looks at recent bars and
indicator snapshot and emits a candidate signal with a "score". The LLM
then reasons about the signal (given lessons + risk state) and finalises
the decision. Keeping the strategy dumb here means the optimizer can
edit *this file* freely to make it smarter without breaking anything.
"""
from __future__ import annotations

from typing import Any, Optional

from trading_agent.tools.base import ToolBase, traced_action


class StrategyTool(ToolBase):
    tool_name = "strategy"

    def __init__(self, db=None, params: Optional[dict] = None):
        super().__init__(db=db)
        self._params = params or {}

    @traced_action("scan")
    def scan(self, df, indicators: dict, *,
             zone_score_threshold: Optional[float] = None) -> dict[str, Any]:
        """Return a candidate setup for the current bar, or `signal='none'`.

        Very simple demo baseline (the optimizer is expected to improve it):
          * "long" candidate  when RSI < 35 AND trend == 'up'
          * "short" candidate when RSI > 65 AND trend == 'down'
          * otherwise no signal
        A `zone_score` in [0..100] is exposed so the LLM/critic can gate
        on it via `strategy_params.zone_score_threshold`.
        """
        if not indicators.get("ok"):
            return {"signal": "none", "reason": indicators.get("reason", "")}

        rsi = indicators.get("rsi")
        trend = indicators.get("trend")
        atr = indicators.get("atr")
        close = indicators.get("close")

        signal = "none"
        score = 0.0
        reason = ""

        if rsi is not None and trend and close is not None:
            if rsi < 35 and trend == "up":
                signal = "long"
                score = min(100.0, (35 - rsi) * 3.0 + 40.0)
                reason = f"RSI={rsi:.1f} oversold in uptrend"
            elif rsi > 65 and trend == "down":
                signal = "short"
                score = min(100.0, (rsi - 65) * 3.0 + 40.0)
                reason = f"RSI={rsi:.1f} overbought in downtrend"

        threshold = zone_score_threshold if zone_score_threshold is not None \
            else self._params.get("zone_score_threshold", 60)

        if signal != "none" and score < threshold:
            reason = f"{reason} (score {score:.1f} below threshold {threshold})"
            signal = "none"

        # Rough SL/TP suggestions in ATRs — the LLM/RiskTool can override.
        sl = tp = None
        if signal == "long" and atr:
            sl = close - 1.5 * atr
            tp = close + 3.0 * atr
        elif signal == "short" and atr:
            sl = close + 1.5 * atr
            tp = close - 3.0 * atr

        return {
            "signal": signal,
            "score": score,
            "reason": reason,
            "suggested_sl": sl,
            "suggested_tp": tp,
        }