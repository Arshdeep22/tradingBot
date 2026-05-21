# Session 03: Memory System + Session Manager

**Prerequisite**: Session 01 complete (models.py, config.py exist).  
**Goal**: Persistent memory across restarts: working memory (last N iterations), long-term memory (phase summaries + embeddings), and session state I/O. The session manager ties them together.  
**Rule**: No file exceeds 200 lines.

---

## Context

The agent needs to remember what it tried across hundreds of iterations and agent restarts. Memory has two tiers:
- **Working memory**: last 10 iterations in full detail — feeds every LLM call.
- **Long-term memory**: compressed phase summaries + semantic embeddings of every hypothesis — prevents retrying approaches that failed.

State persists in `autonomous_optimizer/context/session_state.json`. Embeddings use `sentence-transformers/all-MiniLM-L6-v2` locally. If the model isn't installed, embeddings are skipped and novelty defaults to 1.0.

---

## Files to Create

### `autonomous_optimizer/memory/__init__.py`  (empty)

### `autonomous_optimizer/memory/working_memory.py`  (~100 lines)

In-memory ring buffer of the last N iteration records. Serialisable to/from dict for inclusion in session_state.json.

```python
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class IterationRecord:
    iteration: int
    phase: str
    hypothesis_slug: str
    hypothesis_description: str
    root_cause_category: str
    win_rate: float
    pnl: float
    trade_count: int
    composite_score: float
    reverted: bool
    notes: str = ""   # any extra context (e.g. "Tier1 failed")

class WorkingMemory:
    def __init__(self, window: int = 10):
        self._window = window
        self._records: list[IterationRecord] = []

    def add(self, record: IterationRecord) -> None:
        """Append record; evict oldest if over window."""

    def get_last(self, n: int = 10) -> list[IterationRecord]:
        """Return last min(n, len) records, newest last."""

    def to_dict(self) -> list[dict]:
        """Serialise to list of dicts for JSON storage."""

    @classmethod
    def from_dict(cls, data: list[dict], window: int = 10) -> "WorkingMemory":
        """Deserialise from list of dicts."""

    def clear_oldest(self, keep: int) -> list[IterationRecord]:
        """Evict all but the newest `keep` records. Returns evicted."""
```

### `autonomous_optimizer/memory/embeddings.py`  (~80 lines)

Hypothesis dedup via cosine similarity. Falls back gracefully if sentence-transformers not installed.

```python
import math
from typing import Optional

try:
    from sentence_transformers import SentenceTransformer as _ST
    _model = _ST("all-MiniLM-L6-v2")
    _EMBEDDINGS_AVAILABLE = True
except Exception:
    _model = None
    _EMBEDDINGS_AVAILABLE = False


def embed(text: str) -> list[float]:
    """
    Return embedding vector for text.
    Returns empty list [] if sentence-transformers not available.
    """

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Cosine similarity between two vectors.
    Returns 0.0 if either is empty (graceful degradation when embeddings unavailable).
    """

def novelty_score(hypothesis_text: str, past_embeddings: list[dict]) -> float:
    """
    Return 1.0 - max_cosine_similarity(hypothesis, all past hypotheses).
    Returns 1.0 (fully novel) if embeddings unavailable or past_embeddings is empty.
    past_embeddings: list of {"embedding": [...], "result": "improved|degraded|reverted"}
    """

def most_similar_past(hypothesis_text: str, past_embeddings: list[dict]) -> Optional[dict]:
    """
    Return the past_embeddings entry most similar to hypothesis_text.
    Returns None if list is empty or embeddings unavailable.
    """
```

### `autonomous_optimizer/memory/long_term_memory.py`  (~150 lines)

Compressed phase summaries + hypothesis embedding store. Serialisable.

```python
from dataclasses import dataclass, field

@dataclass
class PhaseSummary:
    phase: str
    iterations_run: int
    best_composite: float
    breakthroughs: list[str]   # hypotheses that improved score significantly
    dead_ends: list[str]       # hypotheses that had no effect or degraded
    insight: str               # one-sentence summary of what moved the needle

class LongTermMemory:
    def __init__(self):
        self._phase_summaries: list[PhaseSummary] = []
        self._hypothesis_embeddings: list[dict] = []   # {embedding, slug, result, iter}
        self._blocked_approaches: list[str] = []

    def add_phase_summary(self, summary: PhaseSummary) -> None: ...

    def get_phase_summaries(self) -> list[PhaseSummary]:
        """Return all phase summaries (≤ ~500 tokens when serialised)."""

    def add_hypothesis_embedding(self, slug: str, description: str,
                                  result: str, iteration: int) -> None:
        """Embed description and store with metadata."""

    def get_hypothesis_embeddings(self) -> list[dict]: ...

    def block_approach(self, description: str) -> None:
        """Mark an approach as permanently blocked."""

    def is_blocked(self, description: str) -> bool:
        """Check via substring match if description overlaps a blocked approach."""

    def to_dict(self) -> dict:
        """Serialise for JSON storage."""

    @classmethod
    def from_dict(cls, data: dict) -> "LongTermMemory": ...
```

### `autonomous_optimizer/session_manager.py`  (~180 lines)

Central brain: loads/saves state, exposes context window for LLM calls, runs episodic compression.

```python
import json
import os
from pathlib import Path

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import SessionState, BacktestResult, IterationRecord
from autonomous_optimizer.memory.working_memory import WorkingMemory, IterationRecord
from autonomous_optimizer.memory.long_term_memory import LongTermMemory, PhaseSummary

class SessionManager:
    def __init__(self, config: AgentConfig):
        self._config = config
        self.state: SessionState = SessionState()
        self.working: WorkingMemory = WorkingMemory(window=config.working_memory_window)
        self.long_term: LongTermMemory = LongTermMemory()

    # ── Persistence ────────────────────────────────────────────────────────────
    def load(self) -> None:
        """Load session state from disk. No-op if file doesn't exist (fresh start)."""

    def save(self) -> None:
        """Save session state, working memory, and long-term memory to disk atomically.
        Writes to a .tmp file first, then renames to avoid corruption on crash."""

    # ── Context for LLM calls ──────────────────────────────────────────────────
    def thinker_context(self) -> dict:
        """
        Return the compressed context dict fed to every Thinker sub-agent.
        {
          "recent": [last 10 IterationRecords as dicts],
          "learned": [phase summaries],
          "blocked": [blocked approaches list],
          "current_phase": "A"|"B"|"C",
          "best_metrics": {"wr": ..., "pnl": ..., "trades": ...},
        }
        Keeps total size ≤ ~2,500 tokens.
        """

    # ── Iteration lifecycle ────────────────────────────────────────────────────
    def record_iteration(self, record: IterationRecord) -> None:
        """Append to working memory, update state trajectories."""

    def maybe_compress(self) -> bool:
        """
        If iteration % episodic_summarize_every == 0:
          - Build a PhaseSummary from evicted working memory records.
          - Promote to long-term memory.
          - Trim working memory to last window/2.
        Returns True if compression ran.
        """

    # ── Phase management ──────────────────────────────────────────────────────
    def advance_phase(self) -> str:
        """Advance phase A→B or B→C. Returns new phase. Raises if already C."""

    def should_advance_phase(self, last_n: int = 10) -> bool:
        """Return True if composite score didn't improve in last N iterations."""

    # ── Success tracking ──────────────────────────────────────────────────────
    def record_success_run(self, result: BacktestResult) -> int:
        """Increment consecutive_dual_success. Returns new count."""

    def reset_consecutive_success(self) -> None:
        """Called on any failed iteration."""
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_working_memory.py`  (~60 lines)

```
test_add_respects_window          → add 15 records to window=10 → len==10, newest preserved
test_get_last_fewer_than_window   → add 3 records, get_last(10) → 3 records
test_serialise_roundtrip          → to_dict() then from_dict() → equal records
test_clear_oldest                 → evicted records returned correctly
```

### `tests/autonomous_optimizer/test_embeddings.py`  (~50 lines)

```
test_cosine_similarity_identical  → cosine_similarity(v, v) == 1.0
test_cosine_similarity_empty      → cosine_similarity([], []) == 0.0
test_novelty_score_empty_history  → novelty_score(text, []) == 1.0
test_novelty_score_similar        → if embeddings available: two similar texts → novelty < 0.5
test_embed_no_crash_when_unavail  → even if ST not installed, embed() returns []
```

### `tests/autonomous_optimizer/test_session_manager.py`  (~80 lines)

```
test_load_fresh_start             → no state file → SessionState defaults
test_save_and_reload              → save, load in new instance → state identical
test_save_atomic_no_corruption    → simulate crash mid-write (mock) → original file intact
test_record_iteration_appends     → record_iteration adds to working memory
test_maybe_compress_runs_every_10 → iteration 10 triggers compression
test_advance_phase_a_to_b         → phase becomes B
test_advance_phase_c_raises       → advance from C raises ValueError
test_should_advance_flat_scores   → 10 identical scores → returns True
test_thinker_context_keys         → dict has "recent", "learned", "blocked", "current_phase"
```

Run: `python -m pytest tests/autonomous_optimizer/test_working_memory.py tests/autonomous_optimizer/test_embeddings.py tests/autonomous_optimizer/test_session_manager.py -v`

---

## Acceptance Criteria

1. All tests pass.
2. `session_manager.save()` uses atomic write (write `.tmp`, rename to final path).
3. Agent can crash and restart — `load()` restores full state without data loss.
4. `thinker_context()` output is ≤ ~2,500 tokens when serialised to JSON.
5. No file exceeds 200 lines.
6. Embeddings gracefully degrade: all tests pass even without `sentence-transformers` installed.
