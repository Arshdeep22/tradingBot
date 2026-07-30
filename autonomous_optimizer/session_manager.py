from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import SessionState, BacktestResult
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
        path = Path(self._config.state_file)
        if not path.exists():
            return
        with path.open() as f:
            data = json.load(f)
        s = data.get("state", {})
        self.state = SessionState(
            iteration=s.get("iteration", 0),
            phase=s.get("phase", "A"),
            consecutive_dual_success=s.get("consecutive_dual_success", 0),
            best_win_rate=s.get("best_win_rate", 0.0),
            best_trade_count=s.get("best_trade_count", 0),
            best_pnl=s.get("best_pnl", 0.0),
            best_composite=s.get("best_composite", 0.0),
            approaches_tried=s.get("approaches_tried", []),
            blocked_approaches=s.get("blocked_approaches", []),
            insights=s.get("insights", []),
            wr_trajectory=s.get("wr_trajectory", []),
            pnl_trajectory=s.get("pnl_trajectory", []),
            trade_count_trajectory=s.get("trade_count_trajectory", []),
            composite_score_trajectory=s.get("composite_score_trajectory", []),
            tier1_false_positives=s.get("tier1_false_positives", 0),
            hypothesis_embeddings=s.get("hypothesis_embeddings", []),
            current_hypothesis_slug=s.get("current_hypothesis_slug", ""),
        )
        self.working = WorkingMemory.from_dict(
            data.get("working_memory", []),
            window=self._config.working_memory_window,
        )
        self.long_term = LongTermMemory.from_dict(data.get("long_term_memory", {}))

    def save(self) -> None:
        path = Path(self._config.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "state": asdict(self.state),
            "working_memory": self.working.to_dict(),
            "long_term_memory": self.long_term.to_dict(),
        }
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)

    # ── Context for LLM calls ──────────────────────────────────────────────────

    def thinker_context(self) -> dict:
        summaries = [asdict(s) for s in self.long_term.get_phase_summaries()]
        return {
            "recent": self.working.to_dict(),
            "learned": summaries,
            "blocked": self.long_term._blocked_approaches,
            "current_phase": self.state.phase,
            "approaches_tried": self.state.approaches_tried[-20:],
            "best_metrics": {
                "wr": self.state.best_win_rate,
                "pnl": self.state.best_pnl,
                "trades": self.state.best_trade_count,
                "composite": self.state.best_composite,
            },
        }

    # ── Iteration lifecycle ────────────────────────────────────────────────────

    def record_iteration(self, record: IterationRecord) -> None:
        self.working.add(record)
        self.state.wr_trajectory.append(record.win_rate)
        self.state.pnl_trajectory.append(record.pnl)
        self.state.trade_count_trajectory.append(record.trade_count)
        self.state.composite_score_trajectory.append(record.composite_score)
        if record.composite_score > self.state.best_composite:
            self.state.best_composite = record.composite_score
            self.state.best_win_rate = record.win_rate
            self.state.best_pnl = record.pnl
            self.state.best_trade_count = record.trade_count

    def maybe_compress(self) -> bool:
        every = self._config.episodic_summarize_every
        if self.state.iteration == 0 or self.state.iteration % every != 0:
            return False
        keep = self._config.working_memory_window // 2
        evicted = self.working.clear_oldest(keep)
        if not evicted:
            return False
        breakthroughs = [r.hypothesis_slug for r in evicted
                         if not r.reverted and r.composite_score > 0]
        dead_ends = [r.hypothesis_slug for r in evicted if r.reverted]
        best = max((r.composite_score for r in evicted), default=0.0)
        summary = PhaseSummary(
            phase=self.state.phase,
            iterations_run=len(evicted),
            best_composite=best,
            breakthroughs=breakthroughs,
            dead_ends=dead_ends,
            insight=f"Phase {self.state.phase}: {len(breakthroughs)} improvements, "
                    f"{len(dead_ends)} reverts over {len(evicted)} iterations.",
        )
        self.long_term.add_phase_summary(summary)
        return True

    # ── Phase management ──────────────────────────────────────────────────────

    def advance_phase(self) -> str:
        transitions = {"A": "B", "B": "C"}
        if self.state.phase not in transitions:
            raise ValueError(f"Cannot advance from phase {self.state.phase}")
        self.state.phase = transitions[self.state.phase]
        return self.state.phase

    def should_advance_phase(self, last_n: int = 10) -> bool:
        scores = self.state.composite_score_trajectory[-last_n:]
        if len(scores) < last_n:
            return False
        return max(scores) - min(scores) < self._config.stuck_score_variance_threshold

    # ── Success tracking ──────────────────────────────────────────────────────

    def record_success_run(self, result: BacktestResult) -> int:
        self.state.consecutive_dual_success += 1
        return self.state.consecutive_dual_success

    def reset_consecutive_success(self) -> None:
        self.state.consecutive_dual_success = 0
