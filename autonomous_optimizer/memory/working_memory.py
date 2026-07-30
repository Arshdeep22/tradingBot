"""Working memory (recent iteration records) backed by the agent SQLite DB.

Public API mirrors the original list-based implementation, but every read/
write hits AgentDB.working_memory. A rolling window is enforced by
evicting the oldest rows whenever the row count exceeds `window`.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db


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
    notes: str = ""


class WorkingMemory:
    def __init__(self, window: int = 10, db: Optional[AgentDB] = None):
        self._window = window
        self._db = db or get_agent_db()

    def add(self, record: IterationRecord) -> None:
        self._db.add_working_record(asdict(record))
        # Enforce rolling window: keep only the newest `window` rows.
        self._db.evict_working_records(keep_last=self._window)

    def get_last(self, n: int = 10) -> list[IterationRecord]:
        rows = self._db.get_working_records(limit=n)
        return [_row_to_record(r) for r in rows]

    def to_dict(self) -> list[dict]:
        return [asdict(r) for r in self.get_last(self._window)]

    @classmethod
    def from_dict(cls, data: list[dict], window: int = 10,
                  db: Optional[AgentDB] = None) -> "WorkingMemory":
        # DB is authoritative — legacy `data` is ignored.
        return cls(window=window, db=db)

    def clear_oldest(self, keep: int) -> list[IterationRecord]:
        """Evict all but the newest `keep` records; return the evicted ones."""
        evicted_rows = self._db.evict_working_records(keep_last=keep)
        return [_row_to_record(r) for r in evicted_rows]


def _row_to_record(row: dict[str, Any]) -> IterationRecord:
    return IterationRecord(
        iteration=row["iteration"],
        phase=row["phase"],
        hypothesis_slug=row["hypothesis_slug"],
        hypothesis_description=row["hypothesis_description"],
        root_cause_category=row["root_cause_category"],
        win_rate=row["win_rate"],
        pnl=row["pnl"],
        trade_count=row["trade_count"],
        composite_score=row["composite_score"],
        reverted=bool(row["reverted"]),
        notes=row.get("notes", "") or "",
    )