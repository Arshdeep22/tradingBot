from __future__ import annotations

import logging
import os
from pathlib import Path

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import RootCause, Hypothesis
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.memory.embeddings import novelty_score
from autonomous_optimizer.memory.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)


# Files the Strategist is ALLOWED to propose as target_files.
# This list reflects the ACTUAL trading strategy surface of the repo, so the
# LLM stops hallucinating paths like "core/backtest_runner.py" (nonexistent)
# or "core/data_loader.py" (nonexistent).
_ALLOWED_TARGET_FILES = [
    # Strategy / signal generation
    "core/engine.py",
    "core/market_regime.py",
    "core/trade_simulator.py",
    "core/paper_trader.py",
    "core/ai_recommender.py",
    "core/learning_journal.py",
    "core/market_data.py",
    "core/backtester.py",
    "core/backtester_models.py",
    "core/broker_interface.py",
    "core/data_fetcher.py",
    # Backtest / historical trainer
    "historical_trainer/simulation.py",
    "historical_trainer/grid_search.py",
    "historical_trainer/weights.py",
    "historical_trainer/data_loader.py",
    "historical_trainer/constants.py",
    "historical_trainer/reporting.py",
    "historical_trainer/runner.py",
    "historical_trainer/time_utils.py",
    "historical_trainer/llm_calls.py",
    # Live strategy files
    "strategies",   # directory — enumerated below
]

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

HARD CONSTRAINT — setup quality over trade count:
- NEVER loosen entry filters, scoring thresholds, zone criteria, or confirmation rules
  to generate more trades. More trades with lower quality destroys win-rate and
  produces statistical hallucinations.
- If trade count is low, the correct response is to WAIT for better setups — not to
  accept weaker ones. Fewer high-quality trades > many low-quality trades.
- Any hypothesis whose primary effect is increasing trade volume (e.g. "lower min_score
  from 60 to 50", "remove confirmation filter", "relax zone width requirement") is
  FORBIDDEN unless win-rate is explicitly expected to hold or improve.
- Acceptable ways to get more trades: expand the symbol universe, run on more sessions,
  fix bugs that cause valid setups to be skipped — not soften the setup criteria.

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


class ConstraintViolation(ValueError):
    pass


class Strategist:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient,
                 long_term: LongTermMemory):
        self._config = config
        self._llm = llm
        self._long_term = long_term

    def _available_files(self) -> list[str]:
        """Enumerate real files under the repo the strategist may modify."""
        root = Path(self._config.repo_root).resolve()
        files: list[str] = []
        for entry in _ALLOWED_TARGET_FILES:
            p = root / entry
            if p.is_dir():
                for py in sorted(p.rglob("*.py")):
                    rel = py.relative_to(root).as_posix()
                    if "__pycache__" in rel:
                        continue
                    files.append(rel)
            elif p.is_file():
                files.append(entry)
        return files

    def strategize(self, root_cause: RootCause, context: dict,
                   explore: bool = False) -> Hypothesis:
        available_files = self._available_files()
        msg = self._build_user_message(root_cause, context, explore, available_files)
        data = self._llm.call(_SYSTEM_PROMPT, msg, stage="strategist")
        hypothesis = self._parse_hypothesis(data)
        self._validate_slug(hypothesis.slug)
        self._validate_target_files(hypothesis, available_files)

        past_embeddings = self._long_term.get_hypothesis_embeddings()
        score = novelty_score(hypothesis.description, past_embeddings)
        hypothesis.novelty_score = score

        if score < self._config.novelty_reject_threshold and past_embeddings:
            logger.info("Novelty too low (%.3f), regenerating once", score)
            msg2 = self._build_user_message(root_cause, context, explore=True,
                                            available_files=available_files)
            data2 = self._llm.call(_SYSTEM_PROMPT, msg2, stage="strategist-explore")
            hypothesis = self._parse_hypothesis(data2)
            self._validate_slug(hypothesis.slug)
            self._validate_target_files(hypothesis, available_files)
            score2 = novelty_score(hypothesis.description, past_embeddings)
            hypothesis.novelty_score = score2

        self._enforce_phase_constraint(hypothesis, context.get("current_phase", "A"))
        return hypothesis

    def _validate_target_files(self, hypothesis: Hypothesis,
                               available: list[str]) -> None:
        """Reject any hypothesis that names files not on disk."""
        available_set = set(available)
        missing = [f for f in hypothesis.target_files if f not in available_set]
        if missing:
            raise ConstraintViolation(
                f"Hypothesis {hypothesis.slug!r} targets files that do NOT exist "
                f"in this repo: {missing}. "
                f"Only files from the enumerated allowed list may be modified."
            )

    def _enforce_phase_constraint(self, hypothesis: Hypothesis, phase: str) -> None:
        if phase in ("B", "C") and len(hypothesis.target_files) > 2:
            raise ConstraintViolation(
                f"Phase {phase} allows max 2 target_files, "
                f"got {len(hypothesis.target_files)}: {hypothesis.target_files}"
            )

    def _build_user_message(self, root_cause: RootCause, context: dict,
                             explore: bool, available_files: list[str]) -> str:
        phase = context.get("current_phase", "A")
        tried = context.get("approaches_tried", [])
        blocked = context.get("blocked_approaches", [])

        tried_lines = "\n".join(
            f"  - {a.get('slug', '?')}: {a.get('description', '?')}"
            for a in tried[-10:]
        ) or "  None"
        blocked_lines = "\n".join(f"  - {b}" for b in blocked) or "  None"
        evidence_lines = "\n".join(f"  - {e}" for e in root_cause.evidence)
        ruling_out_lines = "\n".join(f"  - {r}" for r in root_cause.ruling_out) or "  None"
        files_lines = "\n".join(f"  - {f}" for f in available_files)

        msg = (
            f"Phase: {phase}\n"
            f"Root cause category: {root_cause.category}\n"
            f"Confidence: {root_cause.confidence:.2f}\n"
            f"Evidence:\n{evidence_lines}\n"
            f"Ruled out:\n{ruling_out_lines}\n"
            f"\nApproaches tried (last 10):\n{tried_lines}\n"
            f"\nBlocked approaches:\n{blocked_lines}\n"
            f"\n### FILES YOU MAY MODIFY (these actually exist on disk — "
            f"target_files MUST be a subset of this list; any other path is REJECTED):\n"
            f"{files_lines}\n"
        )

        if explore:
            msg += f"\n{_EXPLORE_SUFFIX}"

        return msg

    def _parse_hypothesis(self, data: dict) -> Hypothesis:
        return Hypothesis(
            slug=data["slug"],
            description=data["description"],
            target_files=data["target_files"],
            expected_delta=data["expected_delta"],
        )

    def _validate_slug(self, slug: str) -> None:
        if " " in slug:
            raise ValueError(f"Slug must be kebab-case (no spaces): {slug!r}")
