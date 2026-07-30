"""Trading-agent memory — thin wrapper around the DB.

Two kinds of memory:
  * `lessons`       — curated by the optimizer, injected into every LLM prompt
                      (e.g. "avoid trading TCS during the first 15 min").
  * `run history`   — read-only view over past `trading_agent_runs` so the
                      LLM can be told "in your last 5 runs win rate was X%".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db


@dataclass
class TradingMemory:
    db: AgentDB

    # ── lessons ────────────────────────────────────────────────────────────
    def get_lessons(self, symbol: Optional[str] = None,
                    limit: int = 50) -> list[str]:
        """Return the newest `limit` lessons formatted as bullet strings.

        The optimizer writes into `trading_agent_memory` via
        `db.add_trading_lesson(...)`. Here we shape them for the LLM.
        """
        rows = self.db.get_trading_lessons(symbol=symbol, limit=limit)
        # rows are returned in ascending id order — keep newest-first for the LLM
        rows = list(reversed(rows))
        out: list[str] = []
        for r in rows:
            sym = r.get("symbol")
            if sym:
                out.append(f"[{r['kind']} / {sym}] {r['content']}")
            else:
                out.append(f"[{r['kind']}] {r['content']}")
        return out

    def add_lesson(self, content: str, *, kind: str = "lesson",
                   symbol: Optional[str] = None,
                   source: str = "optimizer") -> None:
        self.db.add_trading_lesson(kind=kind, content=content,
                                   symbol=symbol, source=source)

    # ── run history ────────────────────────────────────────────────────────
    def recent_run_summary(self, n: int = 5) -> str:
        """Human/LLM-readable summary of the last `n` completed runs."""
        runs = [r for r in self.db.get_recent_trading_runs(limit=n * 2)
                if r.get("ended_at")]
        runs = runs[:n]
        if not runs:
            return "No prior runs."
        lines = []
        for r in runs:
            lines.append(
                f"- {r['started_at']} mode={r['mode']} "
                f"wr={r.get('win_rate')} pnl={r.get('total_pnl')} "
                f"trades={r.get('trade_count')}"
            )
        return "\n".join(lines)


def get_memory(db: AgentDB | None = None) -> TradingMemory:
    return TradingMemory(db=db or get_agent_db())