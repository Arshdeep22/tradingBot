from __future__ import annotations

import logging
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import RootCause, Hypothesis
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.memory.embeddings import novelty_score
from autonomous_optimizer.memory.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)

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


class ConstraintViolation(ValueError):
    pass


class Strategist:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient,
                 long_term: LongTermMemory):
        self._config = config
        self._llm = llm
        self._long_term = long_term

    def strategize(self, root_cause: RootCause, context: dict,
                   explore: bool = False) -> Hypothesis:
        msg = self._build_user_message(root_cause, context, explore)
        data = self._llm.call(_SYSTEM_PROMPT, msg)
        hypothesis = self._parse_hypothesis(data)
        self._validate_slug(hypothesis.slug)

        past_embeddings = self._long_term.get_hypothesis_embeddings()
        score = novelty_score(hypothesis.description, past_embeddings)
        hypothesis.novelty_score = score

        if score < self._config.novelty_reject_threshold and past_embeddings:
            logger.info("Novelty too low (%.3f), regenerating once", score)
            msg2 = self._build_user_message(root_cause, context, explore=True)
            data2 = self._llm.call(_SYSTEM_PROMPT, msg2)
            hypothesis = self._parse_hypothesis(data2)
            self._validate_slug(hypothesis.slug)
            score2 = novelty_score(hypothesis.description, past_embeddings)
            hypothesis.novelty_score = score2

        self._enforce_phase_constraint(hypothesis, context.get("current_phase", "A"))
        return hypothesis

    def _enforce_phase_constraint(self, hypothesis: Hypothesis, phase: str) -> None:
        if phase in ("B", "C") and len(hypothesis.target_files) > 2:
            raise ConstraintViolation(
                f"Phase {phase} allows max 2 target_files, "
                f"got {len(hypothesis.target_files)}: {hypothesis.target_files}"
            )

    def _build_user_message(self, root_cause: RootCause, context: dict,
                             explore: bool) -> str:
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

        msg = (
            f"Phase: {phase}\n"
            f"Root cause category: {root_cause.category}\n"
            f"Confidence: {root_cause.confidence:.2f}\n"
            f"Evidence:\n{evidence_lines}\n"
            f"Ruled out:\n{ruling_out_lines}\n"
            f"\nApproaches tried (last 10):\n{tried_lines}\n"
            f"\nBlocked approaches:\n{blocked_lines}\n"
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
