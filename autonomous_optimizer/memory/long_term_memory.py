"""Long-term memory backed by the agent SQLite DB.

Public API is unchanged (PhaseSummary dataclass + LongTermMemory methods),
but every mutation/read goes through AgentDB instead of in-process lists.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from autonomous_optimizer.memory.embeddings import embed
from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db


@dataclass
class PhaseSummary:
    phase: str
    iterations_run: int
    best_composite: float
    breakthroughs: list[str]
    dead_ends: list[str]
    insight: str


class LongTermMemory:
    def __init__(self, db: Optional[AgentDB] = None):
        self._db = db or get_agent_db()

    # --- phase summaries ---
    def add_phase_summary(self, summary: PhaseSummary) -> None:
        self._db.add_phase_summary({
            "phase": summary.phase,
            "iterations_run": summary.iterations_run,
            "best_composite": summary.best_composite,
            "breakthroughs": summary.breakthroughs,
            "dead_ends": summary.dead_ends,
            "insight": summary.insight,
        })

    def get_phase_summaries(self) -> list[PhaseSummary]:
        out: list[PhaseSummary] = []
        for r in self._db.get_phase_summaries():
            out.append(PhaseSummary(
                phase=r["phase"],
                iterations_run=r["iterations_run"],
                best_composite=r["best_composite"],
                breakthroughs=r["breakthroughs"],
                dead_ends=r["dead_ends"],
                insight=r["insight"],
            ))
        return out

    # --- hypothesis embeddings ---
    def add_hypothesis_embedding(self, slug: str, description: str,
                                 result: str, iteration: int) -> None:
        vec = embed(description)
        self._db.add_hypothesis_embedding(slug, description, result, iteration, vec)

    def get_hypothesis_embeddings(self) -> list[dict]:
        # Reshape DB rows into the schema older code expects.
        rows = self._db.get_hypothesis_embeddings()
        return [
            {
                "slug": r["slug"],
                "description": r["description"],
                "result": r["result"],
                "iteration": r["iteration"],
                "embedding": r["embedding"],
            }
            for r in rows
        ]

    # --- blocked approaches ---
    def block_approach(self, description: str) -> None:
        self._db.block_approach(description)

    def is_blocked(self, description: str) -> bool:
        desc_lower = description.lower()
        return any(
            blocked.lower() in desc_lower or desc_lower in blocked.lower()
            for blocked in self._db.get_blocked_approaches()
        )

    # Property used by legacy code paths (session_manager.thinker_context).
    @property
    def _blocked_approaches(self) -> list[str]:
        return self._db.get_blocked_approaches()

    # --- (de)serialisation ---
    # Kept for backwards-compat callers; state now lives in the DB so these
    # are effectively no-ops from a persistence standpoint.
    def to_dict(self) -> dict:
        return {
            "phase_summaries": [asdict(s) for s in self.get_phase_summaries()],
            "hypothesis_embeddings": self.get_hypothesis_embeddings(),
            "blocked_approaches": self._blocked_approaches,
        }

    @classmethod
    def from_dict(cls, data: dict, db: Optional[AgentDB] = None) -> "LongTermMemory":
        # The DB is the source of truth — legacy `data` is ignored here.
        return cls(db=db)