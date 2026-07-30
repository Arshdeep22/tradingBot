"""Technical-indicator tool — pure, no external calls, always traced."""
from __future__ import annotations

from typing import Any

try:
    import numpy as np  # type: ignore
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover
    np = None  # type: ignore
    pd = None  # type: ignore

from trading_agent.tools.base import ToolBase, traced_action


class IndicatorTool(ToolBase):
    tool_name = "indicators"

    @traced_action("compute")
    def compute(self, df, *, atr_period: int = 14,
                rsi_period: int = 14) -> dict[str, Any]:
        """Return the latest indicator snapshot for `df` (OHLCV, lowercase cols)."""
        if df is None or len(df) < max(atr_period, rsi_period) + 1:
            return {"ok": False, "reason": "not_enough_bars"}

        df = df.copy()
        df.columns = [c.lower() for c in df.columns]

        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        # ── ATR (Wilder) ───────────────────────────────────────────────────
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(atr_period, min_periods=atr_period).mean().iloc[-1]

        # ── RSI ────────────────────────────────────────────────────────────
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.rolling(rsi_period, min_periods=rsi_period).mean().iloc[-1]
        avg_loss = loss.rolling(rsi_period, min_periods=rsi_period).mean().iloc[-1]
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - 100.0 / (1.0 + rs)

        # ── SMA-20/50 as regime hint ───────────────────────────────────────
        sma20 = close.tail(20).mean() if len(close) >= 20 else None
        sma50 = close.tail(50).mean() if len(close) >= 50 else None

        last_close = float(close.iloc[-1])

        return {
            "ok": True,
            "close": last_close,
            "atr": float(atr) if atr == atr else None,           # NaN check
            "rsi": float(rsi) if rsi == rsi else None,
            "sma20": float(sma20) if sma20 is not None else None,
            "sma50": float(sma50) if sma50 is not None else None,
            "trend": (
                "up" if sma20 is not None and sma50 is not None and sma20 > sma50
                else "down" if sma20 is not None and sma50 is not None and sma20 < sma50
                else "unknown"
            ),
        }