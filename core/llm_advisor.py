"""
LLM Strategy Advisor
--------------------
Uses SAP AI Core (Claude Sonnet) to analyze backtest results
and suggest parameter refinements through an automated iteration loop.
"""

import json
import logging
import os
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class StrategyMemory:
    """
    Persists iteration history across sessions so the LLM never repeats
    a failed combination and builds toward the win-rate target over time.
    """

    DEFAULT_PATH = ".streamlit/strategy_memory.json"

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"iterations": [], "best_win_rate": 0.0, "best_params": {}}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def add(self, params: Dict, results: Dict, analysis: str, symbols: List[str]):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "symbols": sorted(symbols),
            "params": params,
            "win_rate": results.get("win_rate", 0),
            "pnl": results.get("total_pnl", 0),
            "zones": results.get("total_zones", 0),
            "triggered": results.get("triggered", 0),
            "wins": results.get("targets_hit", 0),
            "losses": results.get("sl_hit", 0),
            "analysis": analysis,
        }
        self.data["iterations"].append(entry)
        if entry["win_rate"] > self.data["best_win_rate"]:
            self.data["best_win_rate"] = entry["win_rate"]
            self.data["best_params"] = dict(params)
        self.save()

    def clear(self):
        self.data = {"iterations": [], "best_win_rate": 0.0, "best_params": {}}
        self.save()

    @property
    def best_params(self) -> Dict:
        return self.data.get("best_params", {})

    def live_params(self) -> Dict:
        """Returns only the params relevant to live ZoneScanner (excludes build_days/test_days)."""
        bp = self.best_params
        return {
            "min_score": bp.get("min_score", 80),
            "rr_ratio": bp.get("rr_ratio", 3.0),
            "max_base_candles": bp.get("max_base_candles", 5),
        }

    @property
    def best_win_rate(self) -> float:
        return self.data.get("best_win_rate", 0.0)

    @property
    def total_iterations(self) -> int:
        return len(self.data["iterations"])

    def recent_history(self, limit: int = 30) -> List[Dict]:
        return self.data["iterations"][-limit:]


@dataclass
class IterationResult:
    """Result of one iteration of the refinement loop"""
    iteration: int
    parameters: Dict
    win_rate: float
    total_pnl: float
    zones_found: int
    zones_triggered: int
    targets_hit: int
    sl_hit: int
    avg_rr: float
    llm_analysis: str = ""
    llm_suggestions: Dict = field(default_factory=dict)


class AICoreLLM:
    """
    SAP AI Core LLM client with OAuth2 authentication.
    Supports Claude models deployed via SAP AI Core.
    """

    def __init__(self, auth_url: str, api_url: str, client_id: str,
                 client_secret: str, resource_group: str = "default",
                 model: str = "claude-3.5-sonnet"):
        self.auth_url = auth_url
        self.api_url = api_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.resource_group = resource_group
        self.model = model
        self._token = None
        self._deployment_id = None

    def _get_token(self) -> str:
        """Get OAuth2 token from XSUAA"""
        if self._token:
            return self._token

        token_url = f"{self.auth_url}/oauth/token"
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def _get_deployment_id(self) -> str:
        """Get deployment ID for the model"""
        if self._deployment_id:
            return self._deployment_id

        token = self._get_token()
        url = f"{self.api_url}/v2/lm/deployments"
        headers = {
            "Authorization": f"Bearer {token}",
            "AI-Resource-Group": self.resource_group,
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        deployments = response.json().get("resources", [])
        for dep in deployments:
            # Look for a running deployment with our model
            if dep.get("status") == "RUNNING":
                model_name = dep.get("details", {}).get("resources", {}).get("backend_details", {}).get("model", {}).get("name", "")
                if not model_name:
                    # Try alternate path for model name
                    model_name = str(dep.get("details", {}))
                # Use first running deployment if model matches or as fallback
                if self.model.lower() in model_name.lower() or self.model.lower() in str(dep).lower():
                    self._deployment_id = dep["id"]
                    return self._deployment_id

        # Fallback: use first running deployment
        for dep in deployments:
            if dep.get("status") == "RUNNING":
                self._deployment_id = dep["id"]
                logger.info(f"Using deployment: {self._deployment_id}")
                return self._deployment_id

        raise ValueError(f"No running deployment found for model '{self.model}' in resource group '{self.resource_group}'")

    def chat(self, messages: List[Dict], max_tokens: int = 4096, temperature: float = 0.3) -> str:
        """
        Send chat completion request to SAP AI Core.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens in response
            temperature: Creativity level (lower = more deterministic)

        Returns:
            Assistant's response text
        """
        token = self._get_token()
        deployment_id = self._get_deployment_id()

        url = f"{self.api_url}/v2/inference/deployments/{deployment_id}/invoke"
        headers = {
            "Authorization": f"Bearer {token}",
            "AI-Resource-Group": self.resource_group,
            "Content-Type": "application/json",
        }

        # SAP AI Core + Claude: system as top-level field (Anthropic native format)
        system_prompt = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                user_messages.append(msg)

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": user_messages,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = requests.post(url, headers=headers, json=payload)
        if not response.ok:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        result = response.json()
        # Handle different response formats
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        elif "content" in result:
            return result["content"][0]["text"]
        else:
            return str(result)


class StrategyAdvisor:
    """
    Automated strategy refinement using LLM.

    Loop:
    1. Run backtest with current params
    2. Send results to LLM
    3. LLM suggests new params
    4. Re-run backtest
    5. Compare and repeat
    """

    def __init__(self, llm: AICoreLLM):
        self.llm = llm
        self.iterations: List[IterationResult] = []

    def analyze_and_suggest(self, backtest_results: Dict, current_params: Dict,
                            iteration_history: List[Dict] = None,
                            memory_history: List[Dict] = None,
                            target_win_rate: float = 70.0) -> Dict:
        """
        Analyze backtest results and suggest parameter changes.

        Args:
            backtest_results: Summary of backtest performance
            current_params: Current strategy parameters
            iteration_history: Previous iteration results (for context)

        Returns:
            Dict with 'analysis', 'suggestions' (new params), 'confidence', 'reasoning'
        """
        prompt = self._build_prompt(
            backtest_results, current_params, iteration_history,
            memory_history, target_win_rate
        )

        messages = [
            {
                "role": "system",
                "content": self._system_prompt()
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        try:
            response = self.llm.chat(messages, max_tokens=4096, temperature=0.2)
            parsed = self._parse_response(response)
            return parsed
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {
                "analysis": f"Error: {str(e)}",
                "suggestions": current_params,
                "confidence": 0,
                "reasoning": "LLM call failed"
            }

    def _system_prompt(self) -> str:
        return """You are an expert quantitative trading strategy advisor with PERSISTENT MEMORY across sessions.

MISSION: Reach a 70%+ win rate on Supply & Demand zone trades on 15-minute Indian equity candles.
You are given the FULL history of every combination ever tried — never repeat a failed combo.

STRATEGY:
- Zones scored 0-100: Freshness (40pts), Leg-out strength (30pts), Base candles (30pts)
- Only zones >= min_score are traded. Entry at zone boundary, SL outside zone, Target at R:R × risk.
- ~26 candles per trading day on 15m.

TUNABLE PARAMETERS (all must be present in suggestions):
- min_score (50-100): Quality filter. Lower = more zones, lower quality.
- rr_ratio (2.0-5.0): Target distance as multiple of risk. Lower = easier targets.
- max_base_candles (1-6): Tighter base = cleaner zone.
- build_days (5-40): History window to detect zones. More = more zones.
- test_days (2-14): Forward window to test if price reaches zone.

DIAGNOSIS → ACTION MAP:
| Symptom                        | Primary fix                                      |
|-------------------------------|--------------------------------------------------|
| zones=0                       | Lower min_score OR increase build_days           |
| triggered=0                   | Increase test_days (price needs more time)       |
| All SL, no targets            | Lower rr_ratio so target is closer               |
| WR<40%, many triggered        | Raise min_score (filter noise) + lower rr_ratio  |
| WR>60%, few trades            | Lower min_score to get more signals              |
| Pending > triggered           | Increase test_days                               |

REINFORCEMENT RULES:
1. Study the FULL history — every tried combo and its outcome is given to you.
2. NEVER suggest a parameter combination that already produced WR < 40%.
3. Make the BIGGEST promising jump, not a timid ±5 tweak, if previous gentle changes failed.
4. If WR is already > 50%, make smaller refinements to push it to 70%.
5. If stuck (3+ iterations with WR < 30%), make a radical change (e.g., flip build_days dramatically).

RESPONSE FORMAT — strict JSON, no markdown, no extra text:
{
    "analysis": "1-2 sentence diagnosis referencing specific numbers",
    "primary_issue": "zones_not_found|zones_not_triggered|low_win_rate|low_sample_size|near_target",
    "suggestions": {
        "min_score": <int 50-100>,
        "rr_ratio": <float 2.0-5.0>,
        "max_base_candles": <int 1-6>,
        "build_days": <int 5-40>,
        "test_days": <int 2-14>
    },
    "reasoning": "Specific reasoning tied to history — why this combo hasn't been tried and should work",
    "confidence": <int 1-10>,
    "expected_improvement": "e.g. WR should rise from 20% to 50%+"
}"""

    def _build_prompt(self, results: Dict, params: Dict,
                      history: List[Dict] = None,
                      memory_history: List[Dict] = None,
                      target_win_rate: float = 70.0) -> str:
        triggered = results.get('triggered', 0)
        zones = results.get('total_zones', 0)
        wr = results.get('win_rate', 0)

        if zones == 0:
            diagnosis = "⚠️ CRITICAL: No zones detected. Lower min_score or increase build_days."
        elif triggered == 0:
            diagnosis = "⚠️ CRITICAL: Zones found but none triggered. Increase test_days."
        elif wr < 30:
            diagnosis = "⚠️ Poor win rate. Lower rr_ratio to make targets easier, or raise min_score."
        elif wr < target_win_rate:
            diagnosis = f"🔶 Win rate {wr:.1f}% — need {target_win_rate:.0f}%. Refine carefully."
        else:
            diagnosis = f"✅ Target {target_win_rate:.0f}% reached!"

        prompt = f"""## TARGET: {target_win_rate:.0f}% Win Rate

## Current Diagnosis
{diagnosis}

## Current Parameters
min_score={params.get('min_score',80)} | rr_ratio={params.get('rr_ratio',3.0)} | max_base_candles={params.get('max_base_candles',5)} | build_days={params.get('build_days',10)} | test_days={params.get('test_days',3)}

## Current Results
Zones={zones} | Triggered={triggered} | Wins={results.get('targets_hit',0)} | Losses={results.get('sl_hit',0)} | Pending={results.get('pending',0)}
Win Rate={wr:.1f}% | P&L=₹{results.get('total_pnl',0):.2f} | Avg R:R={results.get('avg_rr',0):.2f}
"""
        trades = results.get('trade_details', [])
        if trades:
            prompt += "\n## Trade Breakdown\n| # | Type | Score | Outcome | P&L | R:R |\n|---|------|-------|---------|-----|-----|\n"
            for i, t in enumerate(trades[:12]):
                prompt += f"| {i+1} | {t.get('type','?')} | {t.get('score',0)} | {t.get('outcome','?')} | ₹{t.get('pnl',0):.2f} | {t.get('rr',0):.1f} |\n"

        if history:
            prompt += "\n## This Session History\n"
            for h in history:
                prompt += (f"Iter {h.get('iteration','?')}: "
                           f"score={h.get('min_score')} rr={h.get('rr_ratio')} "
                           f"build={h.get('build_days','?')}d test={h.get('test_days','?')}d "
                           f"→ WR={h.get('win_rate',0):.1f}% zones={h.get('zones',0)} trig={h.get('triggered',0)}\n")

        if memory_history:
            prompt += f"\n## Cross-Session Memory ({len(memory_history)} past runs — NEVER repeat a failing combo)\n"
            for m in memory_history[-20:]:
                p = m.get('params', {})
                prompt += (f"[{m.get('timestamp','?')[:10]}] "
                           f"score={p.get('min_score')} rr={p.get('rr_ratio')} "
                           f"build={p.get('build_days','?')}d test={p.get('test_days','?')}d "
                           f"→ WR={m.get('win_rate',0):.1f}% zones={m.get('zones',0)} trig={m.get('triggered',0)}\n")

        prompt += "\nRespond ONLY with the JSON object."
        return prompt

    def _parse_response(self, response: str) -> Dict:
        """Parse LLM response, handling markdown code blocks"""
        # Strip markdown code block if present
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            parsed = json.loads(text)
            suggestions = parsed.get("suggestions", {})
            if "min_score" in suggestions:
                suggestions["min_score"] = max(50, min(100, int(suggestions["min_score"])))
            if "rr_ratio" in suggestions:
                suggestions["rr_ratio"] = max(2.0, min(5.0, float(suggestions["rr_ratio"])))
            if "max_base_candles" in suggestions:
                suggestions["max_base_candles"] = max(1, min(6, int(suggestions["max_base_candles"])))
            if "build_days" in suggestions:
                suggestions["build_days"] = max(5, min(40, int(suggestions["build_days"])))
            if "test_days" in suggestions:
                suggestions["test_days"] = max(2, min(14, int(suggestions["test_days"])))
            parsed["suggestions"] = suggestions
            return parsed
        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw text as analysis
            return {
                "analysis": text,
                "suggestions": {},
                "confidence": 0,
                "reasoning": "Could not parse LLM response as JSON"
            }


def create_llm_from_secrets(secrets: Dict) -> AICoreLLM:
    """Create AICoreLLM instance from Streamlit secrets"""
    aicore = secrets.get("aicore", {})
    return AICoreLLM(
        auth_url=aicore.get("auth_url", ""),
        api_url=aicore.get("api_url", ""),
        client_id=aicore.get("client_id", ""),
        client_secret=aicore.get("client_secret", ""),
        resource_group=aicore.get("resource_group", "default"),
        model=aicore.get("model", "anthropic--claude-4.6-opus"),
    )
