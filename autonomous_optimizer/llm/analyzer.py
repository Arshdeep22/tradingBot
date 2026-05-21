import json

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.models import Observation, RootCause

_SYSTEM_PROMPT = """You are the Analyzer component of an autonomous trading bot optimizer.
Your ONLY job is root cause analysis. You must NOT propose solutions.

Rules:
1. Commit to exactly ONE root cause category from this list:
   entry_timing | zone_quality | exit_logic | trade_frequency | regime_mismatch |
   symbol_selection | scoring_threshold | infrastructure_bug | position_sizing | unknown

2. Provide 2-5 specific facts from the observation that support your conclusion.
3. Explicitly rule out at least 2 alternative causes and explain why.
4. Set confidence 0.0-1.0 based on how strongly the evidence points to your cause.

Respond ONLY with valid JSON matching this schema:
{
  "category": "<one of the categories above>",
  "evidence": ["<fact 1>", "<fact 2>", ...],
  "confidence": 0.0-1.0,
  "ruling_out": ["<alt cause 1: why rejected>", "<alt cause 2: why rejected>"]
}"""

_VALID_CATEGORIES = frozenset({
    "entry_timing", "zone_quality", "exit_logic", "trade_frequency",
    "regime_mismatch", "symbol_selection", "scoring_threshold",
    "infrastructure_bug", "position_sizing", "unknown",
})


class Analyzer:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient):
        self._config = config
        self._llm = llm

    def analyze(self, observation: Observation, context: dict) -> RootCause:
        user_msg = self._build_user_message(observation, context)
        raw = self._llm.call(_SYSTEM_PROMPT, user_msg, expect_json=True)
        return self._validate_and_parse(raw)

    def _build_user_message(self, observation: Observation, context: dict) -> str:
        bt = observation.backtest
        parts = [
            f"## Iteration {observation.iteration}",
            "",
            "### Backtest Metrics",
            f"win_rate={bt.win_rate:.1f}%  total_pnl={bt.total_pnl:.0f}  "
            f"trade_count={bt.trade_count}  trades_per_day={bt.trades_per_day:.2f}",
            f"profit_factor={bt.profit_factor:.2f}  sharpe={bt.sharpe_ratio:.2f}  "
            f"max_drawdown={bt.max_drawdown_rupees:.0f}  days_run={bt.days_run}",
            f"capital_floor_hit={bt.capital_floor_hit}  "
            f"consecutive_losses_max={bt.consecutive_losses_max}",
        ]

        if observation.anomaly_flags:
            parts += ["", "### Anomaly Flags"]
            parts += [f"- {flag}" for flag in observation.anomaly_flags]

        if observation.regime_state:
            parts += ["", f"### Market Regime: {observation.regime_state}"]

        recent = context.get("recent", {})
        if recent:
            parts += ["", "### Recent Iteration History (last 10)"]
            for entry in (recent.get("iterations") or [])[-5:]:
                r = entry.get("result", {})
                parts.append(
                    f"iter={entry.get('iteration','?')}  "
                    f"wr={r.get('win_rate','?')}  pnl={r.get('total_pnl','?')}  "
                    f"trades={r.get('trade_count','?')}  hyp={entry.get('hypothesis','?')}"
                )

        learned = context.get("learned", [])
        if learned:
            parts += ["", "### Learned from Memory (key insights)"]
            for item in learned[:5]:
                parts.append(f"- {item}")

        if observation.code_diff:
            diff_preview = observation.code_diff[:800]
            parts += ["", "### Recent Code Diff (truncated)", "```", diff_preview, "```"]

        return "\n".join(parts)

    def _validate_and_parse(self, raw: dict) -> RootCause:
        category = raw.get("category", "unknown")
        if category not in _VALID_CATEGORIES:
            raise ValueError(
                f"Invalid root cause category: {category!r}. "
                f"Must be one of: {sorted(_VALID_CATEGORIES)}"
            )

        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return RootCause(
            category=category,
            evidence=list(raw.get("evidence", [])),
            confidence=confidence,
            ruling_out=list(raw.get("ruling_out", [])),
        )
