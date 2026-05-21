from dataclasses import dataclass, asdict
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
    notes: str = ""


class WorkingMemory:
    def __init__(self, window: int = 10):
        self._window = window
        self._records: list[IterationRecord] = []

    def add(self, record: IterationRecord) -> None:
        self._records.append(record)
        if len(self._records) > self._window:
            self._records = self._records[-self._window:]

    def get_last(self, n: int = 10) -> list[IterationRecord]:
        return self._records[-n:] if n < len(self._records) else list(self._records)

    def to_dict(self) -> list[dict]:
        return [asdict(r) for r in self._records]

    @classmethod
    def from_dict(cls, data: list[dict], window: int = 10) -> "WorkingMemory":
        wm = cls(window=window)
        wm._records = [IterationRecord(**d) for d in data]
        return wm

    def clear_oldest(self, keep: int) -> list[IterationRecord]:
        if keep >= len(self._records):
            return []
        evicted = self._records[:-keep] if keep > 0 else list(self._records)
        self._records = self._records[-keep:] if keep > 0 else []
        return evicted
