"""
Standalone AI Recommendation Engine
-------------------------------------
Extracts the scan + Claude AI logic from the Streamlit dashboard page so it
can be called headlessly (GitHub Actions, CLI) without Streamlit.

Secrets are read from environment variables instead of st.secrets.
"""

import json
import logging
import os
from typing import Optional

from core.data_fetcher import DataFetcher
from core.llm_advisor import AICoreLLM, StrategyMemory
from strategies.zone_scanner import ZoneScanner
from config.settings import NIFTY_50

logger = logging.getLogger(__name__)


def create_llm_from_env() -> AICoreLLM:
    """Create AICoreLLM from environment variables (for GitHub Actions)."""
    return AICoreLLM(
        auth_url=os.environ["AICORE_AUTH_URL"],
        api_url=os.environ["AICORE_API_URL"],
        client_id=os.environ["AICORE_CLIENT_ID"],
        client_secret=os.environ["AICORE_CLIENT_SECRET"],
        resource_group=os.environ.get("AICORE_RESOURCE_GROUP", "default"),
        model=os.environ.get("AICORE_MODEL", "anthropic--claude-4.6-opus"),
    )


def scan_nifty50_zones(min_score: int = 75) -> list:
    """
    Scan all Nifty 50 stocks for Supply & Demand zone setups.
    Returns all setups sorted by score descending.
    """
    memory = StrategyMemory()
    if memory.best_params:
        lp = memory.live_params()
        logger.info(
            f"Using AI-optimized params: score={lp['min_score']}, "
            f"rr={lp['rr_ratio']}, base={lp['max_base_candles']}"
        )
    else:
        lp = {"min_score": min_score, "rr_ratio": 3.0, "max_base_candles": 5}
        logger.info("No AI memory found — using default params")

    scanner = ZoneScanner(
        min_score=lp["min_score"],
        rr_ratio=lp["rr_ratio"],
        max_base_candles=lp["max_base_candles"],
    )
    data_fetcher = DataFetcher()
    all_setups = []

    for i, symbol in enumerate(NIFTY_50):
        logger.info(f"Scanning {symbol}… ({i + 1}/{len(NIFTY_50)})")
        try:
            data = data_fetcher.get_data(symbol, "15m", "10d")
            if data is not None and len(data) > 20:
                setups = scanner.get_trade_setups(data, symbol)
                if setups:
                    all_setups.extend(setups)
        except Exception as e:
            logger.warning(f"Error scanning {symbol}: {e}")

    all_setups.sort(key=lambda s: s.score, reverse=True)
    logger.info(f"Scan complete: {len(all_setups)} setups found across {len(NIFTY_50)} stocks")
    return all_setups


def get_ai_recommendations(candidates: list, llm: AICoreLLM) -> Optional[dict]:
    """
    Send top candidates to Claude and get ranked top 10 with reasoning.
    Same prompt as ask_ai() in dashboard/pages/5_AI_Recommendations.py.
    Returns parsed JSON dict or None on failure.
    """
    setups_payload = []
    for i, s in enumerate(candidates):
        risk = abs(s.entry - s.stop_loss)
        reward = abs(s.target - s.entry)
        rr = round(reward / risk, 1) if risk > 0 else 0
        setups_payload.append({
            "id":             i,
            "symbol":         s.symbol,
            "side":           s.side,
            "entry":          s.entry,
            "stop_loss":      s.stop_loss,
            "target":         s.target,
            "rr_ratio":       rr,
            "zone_score":     s.score,
            "zone_reasoning": s.reasoning,
        })

    system = (
        "You are an expert NSE equity trader specialising in Supply & Demand zone trading on 15-minute charts. "
        "Evaluate the given trade setups and select the TOP 10 with the highest probability of success. "
        "Consider zone quality score, R:R ratio, and zone reasoning. "
        "Respond ONLY with valid JSON — no markdown fences, no extra text."
    )

    user = f"""Here are {len(setups_payload)} trade setups detected across Nifty 50 stocks on 15-minute charts.

Select exactly 10 with the highest win probability.

SETUPS:
{json.dumps(setups_payload, indent=2)}

Respond with this exact JSON structure (no markdown, no extra keys):
{{
  "market_context": "2-3 sentence overview of which setups look strongest and why",
  "recommendations": [
    {{
      "id": <same id from SETUPS>,
      "rank": 1,
      "win_probability": 82,
      "conviction": "HIGH",
      "reasoning": ["bullet 1", "bullet 2", "bullet 3"],
      "risks": "key risk in one sentence",
      "entry_advice": "e.g. Limit order at zone entry, or wait for bullish confirmation candle"
    }}
  ]
}}"""

    try:
        raw = llm.chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=4096,
            temperature=0.2,
        )
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
            ).strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"AI recommendation call failed: {e}")
        return None
