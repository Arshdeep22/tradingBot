# Session 06: Strategist + Reflector + Critic + Coder

**Prerequisite**: Sessions 01–05 complete (models, config, memory, llm/client, observer, analyzer exist).  
**Goal**: The remaining four cognitive modules that complete the reasoning pipeline. All four follow the same pattern: receive structured input from the previous layer, call LLM with a focused prompt, return a typed dataclass.  
**Rule**: No file exceeds 200 lines. Mock all LLM calls in tests.

---

## Files to Create

### `autonomous_optimizer/llm/strategist.py`  (~160 lines)

Hypothesis generation with novelty dedup. The only module that calls `embeddings.py`.

```python
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import RootCause, Hypothesis
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.memory.embeddings import novelty_score, most_similar_past
from autonomous_optimizer.memory.long_term_memory import LongTermMemory

_SYSTEM_PROMPT = """
You are the Strategist component of an autonomous trading bot optimizer.
Your ONLY job is to propose ONE testable hypothesis based on the root cause provided.

Rules:
1. Propose EXACTLY ONE hypothesis. Not two. Not a list.
2. The hypothesis must directly address the root cause category.
3. Name target_files: the files that must change. Phase B/C: max 2 files.
4. expected_delta: predict the metric change (e.g. "WR +5-10%, trades unchanged").
5. The slug must be kebab-case, ≤ 5 words, unique (you will be told if it was tried before).
6. Do NOT propose solutions that are in the blocked list.

Respond ONLY with valid JSON:
{
  "slug": "trailing-stop-breakeven",
  "description": "plain English: what changes and why",
  "target_files": ["core/trade_simulator.py"],
  "expected_delta": "WR +5-10%, trades unchanged"
}
"""

_EXPLORE_SUFFIX = (
    "IMPORTANT: You are in EXPLORE mode. Ignore all prior constraints. "
    "Assume everything tried so far was wrong. Propose something structurally "
    "different from any past hypothesis. It is acceptable to sacrifice some WR "
    "to learn what the bottleneck is."
)


class Strategist:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient,
                 long_term: LongTermMemory):
        self._config = config
        self._llm = llm
        self._long_term = long_term

    def strategize(self, root_cause: RootCause, context: dict,
                   explore: bool = False) -> Hypothesis:
        """
        Generate a hypothesis for the given root cause.
        1. Call LLM to generate a hypothesis.
        2. Compute novelty_score against past hypothesis embeddings.
        3. If novelty < config.novelty_reject_threshold: log, regenerate once.
        4. If Phase B/C: enforce ≤ 2 target_files constraint.
        5. Return Hypothesis with novelty_score set.
        """

    def _enforce_phase_constraint(self, hypothesis: Hypothesis, phase: str) -> None:
        """Raise ConstraintViolation if Phase B/C and target_files > 2."""

    def _build_user_message(self, root_cause: RootCause, context: dict,
                             explore: bool) -> str:
        """
        Format root cause + tried approaches + blocked list into user prompt.
        If explore=True: append _EXPLORE_SUFFIX.
        """


class ConstraintViolation(ValueError): pass
```

---

### `autonomous_optimizer/llm/reflector.py`  (~120 lines)

Meta-cognition: is the agent making progress or cycling?

```python
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import ReflectionResult, Hypothesis, SessionState

class Reflector:
    def __init__(self, config: AgentConfig):
        self._config = config

    def reflect(self, hypothesis: Hypothesis, root_cause,
                state: SessionState) -> ReflectionResult:
        """
        Compute confidence and detect stuck signals. No LLM call — pure computation.

        Confidence formula:
          confidence = 0.4 * root_cause.confidence
                     + 0.4 * hypothesis.novelty_score
                     + 0.2 * _past_similar_outcome_signal(hypothesis, state)

        Stuck signals (any True → stuck=True):
          score_oscillation:    variance(composite_score_trajectory[-10:]) < threshold
          hypothesis_cycling:   unique slugs in last 10 hypothesis_slugs < 4
          phase_exhausted:      phase iterations > stuck_phase_max_iterations and not phase gate hit
          critic_rejection_rate: rejections in last 10 / 10 > 0.6  (read from state)

        Returns:
          mode = "explore" if stuck else "exploit"
          gate_tier2 = confidence >= config.min_confidence_for_tier2
        """

    def _past_similar_outcome_signal(self, hypothesis: Hypothesis,
                                      state: SessionState) -> float:
        """
        +0.5 if the most similar past hypothesis improved composite score.
        -0.5 if it degraded composite score.
        0.0 if no similar past hypothesis found or embeddings unavailable.
        Final returned value is (signal + 0.5) / 1.0 → maps to [0.0, 1.0].
        """

    def _variance(self, values: list[float]) -> float:
        """Population variance. Returns 0.0 for empty or single-element list."""
```

---

### `autonomous_optimizer/llm/critic.py`  (~120 lines)

Coherence check before the diff touches the filesystem. No LLM — pure structural analysis.

```python
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis, CriticResult
from autonomous_optimizer.code_editor import CodeEditor

class Critic:
    def __init__(self, config: AgentConfig, code_editor: CodeEditor):
        self._config = config
        self._editor = code_editor

    def review(self, hypothesis: Hypothesis, proposed_code: dict[str, str]) -> CriticResult:
        """
        Check the proposed code changes for coherence and scope.
        proposed_code: {filepath: new_file_contents}

        Checks:
        1. scope_violations: files in proposed_code keys but NOT in hypothesis.target_files
        2. syntax_check: all proposed file contents parse without SyntaxError
        3. hypothesis_drift: if hypothesis.slug appears in the code comment/docstring (simple check)

        Returns CriticResult with:
          approved = True only if no scope_violations AND no syntax errors
          reason = human-readable explanation if blocked
        """

    def _check_syntax(self, filepath: str, code: str) -> str | None:
        """
        Try ast.parse(code). Returns None if OK, error string if failed.
        """

    def _check_scope(self, proposed_files: list[str],
                     target_files: list[str]) -> list[str]:
        """Return list of files in proposed_files that are not in target_files."""
```

---

### `autonomous_optimizer/llm/coder.py`  (~140 lines)

Code generation. Receives an approved hypothesis and file contents, returns modified files.

```python
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.code_editor import CodeEditor

_SYSTEM_PROMPT = """
You are the Coder component of an autonomous trading bot optimizer.
You will receive a hypothesis and the current content of files to modify.

Rules:
1. Output ONLY valid Python code for each file — no explanations, no markdown.
2. Do NOT change function signatures that are called from other files.
3. Do NOT add new imports unless strictly required by the change.
4. Do NOT change anything outside the scope of the hypothesis.
5. The output must be a JSON object: {"filepath": "new_file_contents", ...}
6. Only include files that actually need to change.
"""


class Coder:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient,
                 code_editor: CodeEditor):
        self._config = config
        self._llm = llm
        self._editor = code_editor

    def generate_changes(self, hypothesis: Hypothesis) -> dict[str, str]:
        """
        Generate code changes for the hypothesis.
        1. Read current contents of each file in hypothesis.target_files.
        2. Call LLM with hypothesis + file contents.
        3. Parse response as {filepath: new_code}.
        4. Validate syntax of each generated file via code_editor.validate_syntax().
        5. Return {filepath: new_code} only for files that passed validation.
        Raises CoderError if ALL files fail syntax validation.
        """

    def _build_user_message(self, hypothesis: Hypothesis,
                             file_contents: dict[str, str]) -> str:
        """
        Format hypothesis description + file contents into a prompt.
        Include: slug, description, expected_delta, current code.
        Keep each file truncated to first 150 lines if over that — Coder sees the key section.
        """

    def apply_changes(self, changes: dict[str, str]) -> list[str]:
        """
        Write all approved changes to disk via code_editor.write_file().
        Returns list of files actually written.
        """


class CoderError(RuntimeError): pass
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_strategist.py`  (~90 lines)

```
test_strategize_returns_hypothesis          → mock LLM valid JSON → Hypothesis returned
test_novelty_check_rejects_similar          → novelty < threshold → regenerates (LLM called twice)
test_phase_b_constraint_enforced            → Phase B + 3 target_files → ConstraintViolation
test_phase_a_no_constraint                  → Phase A + 3 target_files → no exception
test_explore_mode_appends_suffix            → explore=True → prompt contains EXPLORE suffix
test_slug_kebab_validation                  → slug with spaces → ValueError
```

### `tests/autonomous_optimizer/test_reflector.py`  (~80 lines)

No LLM — pure computation tests.

```
test_confidence_formula                 → known inputs → hand-computed expected value
test_stuck_score_oscillation            → 10 identical composite scores → stuck=True
test_stuck_hypothesis_cycling           → only 3 unique slugs in last 10 → stuck=True
test_not_stuck_healthy_progress         → variance > threshold, 6 unique slugs → stuck=False
test_gate_tier2_low_confidence          → confidence=0.3 → gate_tier2=False
test_gate_tier2_high_confidence         → confidence=0.5 → gate_tier2=True
test_mode_explore_when_stuck            → stuck=True → mode=="explore"
test_variance_empty_list                → returns 0.0
```

### `tests/autonomous_optimizer/test_critic.py`  (~70 lines)

```
test_review_approved_clean              → no scope violations, valid syntax → approved=True
test_review_scope_violation             → file outside target_files → approved=False
test_review_syntax_error_blocks         → invalid Python in proposed code → approved=False
test_scope_violations_listed            → returns which files violated scope
test_no_violations_reason_empty         → approved=True → reason is ""
```

### `tests/autonomous_optimizer/test_coder.py`  (~70 lines)

```
test_generate_changes_returns_dict      → mock LLM → dict of {filepath: code}
test_invalid_syntax_file_excluded       → one file has bad syntax → excluded from result
test_all_syntax_fails_raises            → all files invalid → CoderError
test_build_user_message_truncates_long  → file > 150 lines → message doesn't include line 200
test_apply_changes_writes_files         → calls code_editor.write_file for each change
```

Run: `python -m pytest tests/autonomous_optimizer/test_strategist.py tests/autonomous_optimizer/test_reflector.py tests/autonomous_optimizer/test_critic.py tests/autonomous_optimizer/test_coder.py -v`

---

## Acceptance Criteria

1. All tests pass (no real LLM calls).
2. `Reflector` has zero LLM calls — all computation.
3. `Critic` has zero LLM calls — structural analysis only.
4. `Strategist` enforces the 2-file constraint in Phase B/C.
5. `Coder` never writes to disk if syntax validation fails.
6. `Strategist` attempts regeneration at most once on low novelty (not an infinite loop).
7. No file exceeds 200 lines.
