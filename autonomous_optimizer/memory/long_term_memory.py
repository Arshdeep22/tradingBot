from dataclasses import dataclass, field, asdict

from autonomous_optimizer.memory.embeddings import embed


@dataclass
class PhaseSummary:
    phase: str
    iterations_run: int
    best_composite: float
    breakthroughs: list[str]
    dead_ends: list[str]
    insight: str


class LongTermMemory:
    def __init__(self):
        self._phase_summaries: list[PhaseSummary] = []
        self._hypothesis_embeddings: list[dict] = []
        self._blocked_approaches: list[str] = []

    def add_phase_summary(self, summary: PhaseSummary) -> None:
        self._phase_summaries.append(summary)

    def get_phase_summaries(self) -> list[PhaseSummary]:
        return list(self._phase_summaries)

    def add_hypothesis_embedding(self, slug: str, description: str,
                                  result: str, iteration: int) -> None:
        vec = embed(description)
        self._hypothesis_embeddings.append({
            "slug": slug,
            "description": description,
            "result": result,
            "iteration": iteration,
            "embedding": vec,
        })

    def get_hypothesis_embeddings(self) -> list[dict]:
        return list(self._hypothesis_embeddings)

    def block_approach(self, description: str) -> None:
        if description not in self._blocked_approaches:
            self._blocked_approaches.append(description)

    def is_blocked(self, description: str) -> bool:
        desc_lower = description.lower()
        return any(blocked.lower() in desc_lower or desc_lower in blocked.lower()
                   for blocked in self._blocked_approaches)

    def to_dict(self) -> dict:
        return {
            "phase_summaries": [asdict(s) for s in self._phase_summaries],
            "hypothesis_embeddings": self._hypothesis_embeddings,
            "blocked_approaches": self._blocked_approaches,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LongTermMemory":
        ltm = cls()
        for s in data.get("phase_summaries", []):
            ltm._phase_summaries.append(PhaseSummary(**s))
        ltm._hypothesis_embeddings = data.get("hypothesis_embeddings", [])
        ltm._blocked_approaches = data.get("blocked_approaches", [])
        return ltm
