# Session 05: LLM Client + Observer + Analyzer

**Prerequisite**: Sessions 01–03 complete (models, config, memory, git_ops exist).  
**Goal**: Build the LLM infrastructure layer and the first two cognitive modules — Observer (reads only, structured facts) and Analyzer (root cause only, no solutions).  
**Rule**: No file exceeds 200 lines. No LLM calls in tests — use mocked responses.

---

## Context

The agent uses SAP AI Core which proxies `anthropic--claude-4.6-opus`. The existing `AICoreLLM` class in `core/llm_advisor.py` handles authentication. The LLM client module in this session wraps it for the agent's use: structured JSON outputs, retry logic, and prompt helpers.

The Observer and Analyzer are the first two layers in the cognitive pipeline:
- **Observer** — reads raw data (backtest results, git diff, test output), produces a structured `Observation` object. No interpretation.
- **Analyzer** — receives `Observation + working memory`, commits to a `RootCause` before any solution is proposed.

---

## Files to Create

### `autonomous_optimizer/llm/__init__.py`  (empty)

### `autonomous_optimizer/llm/client.py`  (~120 lines)

Thin wrapper around `AICoreLLM` for agent use. All agent LLM calls go through this.

```python
import os
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Reuse existing AICoreLLM — do NOT duplicate its logic
from core.llm_advisor import AICoreLLM


class AgentLLMClient:
    def __init__(self, config):
        """
        Build AICoreLLM from environment variables.
        Raises EnvironmentError if required vars missing.
        Required env vars: AICORE_AUTH_URL, AICORE_API_URL, AICORE_CLIENT_ID, AICORE_CLIENT_SECRET
        Optional: AICORE_RESOURCE_GROUP (default "default"), AICORE_MODEL (default from config)
        """

    def call(self, system_prompt: str, user_message: str,
             expect_json: bool = True, max_retries: int = 3) -> Any:
        """
        Call the LLM with system + user prompt.
        If expect_json=True:
          - Appends "Respond ONLY with valid JSON." to system prompt.
          - Parses response as JSON. Retries up to max_retries on parse failure.
          - Returns parsed dict/list.
        If expect_json=False:
          - Returns raw string response.
        Raises LLMError after max_retries exhausted.
        Logs token usage (input/output) at DEBUG level.
        """

    def _build_llm(self) -> AICoreLLM:
        """Create AICoreLLM from env vars."""


class LLMError(RuntimeError): pass
```

**Important**: `AgentLLMClient` must handle the case where `AICoreLLM.call()` returns a response with the JSON wrapped in markdown fences (```json ... ```). Strip fences before parsing.

---

### `autonomous_optimizer/llm/observer.py`  (~140 lines)

Reads raw data sources and packages them into a structured `Observation`. No LLM calls — pure data collection.

```python
import subprocess
from pathlib import Path

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Observation, BacktestResult
from autonomous_optimizer.git_ops import GitOps


class Observer:
    def __init__(self, config: AgentConfig, git_ops: GitOps):
        self._config = config
        self._git = git_ops

    def observe(self, iteration: int, backtest_result: BacktestResult,
                test_output: str) -> Observation:
        """
        Collect all structured facts from the environment.
        Populates:
          backtest       → from the passed BacktestResult
          code_diff      → git.current_diff("HEAD")
          test_output    → from passed argument
          anomaly_flags  → detect: any weekly P&L > 80% of total (fragile strategy)
                                    trade_count == 0 (no trades)
                                    win_rate == 0.0 (all losses)
          data_freshness → scan reports/training/ for last modified time
          regime_state   → read from latest backtest report if available, else "unknown"
          git_blame_recent → git.recent_blame() on files changed in last 3 iterations
        """

    def _detect_anomalies(self, result: BacktestResult) -> list[str]:
        """
        Return list of anomaly flag strings. Examples:
        - "FRAGILE: 85% of P&L in one week" if max week > 0.8 * total_pnl
        - "NO_TRADES: zero trades generated"
        - "ALL_LOSSES: win_rate == 0.0"
        """

    def _data_freshness(self) -> dict:
        """Scan reports/training/ for latest report timestamp."""

    def _regime_state(self) -> str:
        """Read regime from latest_backtest_result.json if present, else 'unknown'."""
```

---

### `autonomous_optimizer/llm/analyzer.py`  (~140 lines)

Root-cause analysis only. Commits to a single cause before any solution is proposed.

```python
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Observation, RootCause
from autonomous_optimizer.llm.client import AgentLLMClient

_SYSTEM_PROMPT = """
You are the Analyzer component of an autonomous trading bot optimizer.
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
}
"""


class Analyzer:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient):
        self._config = config
        self._llm = llm

    def analyze(self, observation: Observation, context: dict) -> RootCause:
        """
        Run root cause analysis.
        context = session_manager.thinker_context()
        Returns RootCause dataclass.
        Raises ValueError if LLM returns invalid category.
        """

    def _build_user_message(self, observation: Observation, context: dict) -> str:
        """
        Format the observation and context into a focused user prompt.
        Include: backtest metrics, anomaly flags, recent iteration history (context["recent"]),
                 what has been tried before (context["learned"]).
        Keep under ~1500 tokens.
        """

    def _validate_and_parse(self, raw: dict) -> RootCause:
        """
        Parse LLM JSON response into RootCause.
        Validates category is in the allowed list.
        Clamps confidence to [0.0, 1.0].
        """

    _VALID_CATEGORIES = frozenset({
        "entry_timing", "zone_quality", "exit_logic", "trade_frequency",
        "regime_mismatch", "symbol_selection", "scoring_threshold",
        "infrastructure_bug", "position_sizing", "unknown"
    })
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_llm_client.py`  (~80 lines)

All tests mock the underlying `AICoreLLM.call()` — no real API calls.

```
test_call_parses_valid_json             → mock returns '{"key": "value"}' → dict returned
test_call_strips_markdown_fences        → mock returns '```json\n{"k":"v"}\n```' → dict parsed
test_call_retries_on_invalid_json       → first call returns invalid JSON, second returns valid
test_call_raises_after_max_retries      → 3 invalid responses → LLMError
test_call_not_json_mode_returns_string  → expect_json=False → raw string returned
test_missing_env_vars_raises            → EnvironmentError on construction without vars
```

### `tests/autonomous_optimizer/test_observer.py`  (~80 lines)

No LLM calls. Mock git_ops and file system where needed.

```
test_observe_returns_observation_type   → returns Observation dataclass
test_anomaly_fragile_pnl                → pnl_by_week=[45000.0], total_pnl=50000 → "FRAGILE" flag
test_anomaly_no_trades                  → trade_count=0 → "NO_TRADES" flag
test_anomaly_all_losses                 → win_rate=0.0 → "ALL_LOSSES" flag
test_no_anomalies_clean_result          → normal backtest → empty anomaly list
test_regime_state_unknown_no_file       → no JSON report file → "unknown"
```

### `tests/autonomous_optimizer/test_analyzer.py`  (~80 lines)

Mock the LLM client.

```
test_analyze_returns_root_cause         → mock valid JSON → RootCause returned
test_analyze_valid_category             → category "entry_timing" → no exception
test_analyze_invalid_category_raises    → category "wrong" in LLM response → ValueError
test_analyze_confidence_clamped_high    → confidence=1.5 in response → clamped to 1.0
test_analyze_confidence_clamped_low     → confidence=-0.1 → clamped to 0.0
test_user_message_under_1500_tokens     → approximation: len(msg) < 6000 chars
```

Run: `python -m pytest tests/autonomous_optimizer/test_llm_client.py tests/autonomous_optimizer/test_observer.py tests/autonomous_optimizer/test_analyzer.py -v`

---

## Acceptance Criteria

1. All tests pass without any real LLM or API calls.
2. `AgentLLMClient` correctly strips markdown code fences from JSON responses.
3. `Analyzer` raises `ValueError` if LLM returns an invalid category.
4. `Observer.observe()` returns a fully-populated `Observation` — no None fields.
5. No file exceeds 200 lines.
6. `AgentLLMClient` raises `EnvironmentError` (not a generic exception) if required env vars are missing.
