"""Session manager backed by the agent SQLite DB.

Replaces the previous JSON-file (`autonomous_optimizer/context/session_state.json`)
persistence with rows in `database/agent.db`. Public API is preserved so
`Agent` and its collaborators don't need to change.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import SessionState, BacktestResult
from autonomous_optimizer.memory.working_memory import WorkingMemory, IterationRecord
from autonomous_optimizer.memory.long_term_memory import LongTermMemory, PhaseSummary
from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db


class SessionManager:
    def __init__(self, config: AgentConfig, db: Optional[AgentDB] = None):
        self._config = config
        self._db = db or get_agent_db()
        self.state: SessionState = SessionState()
        self.working: WorkingMemory = WorkingMemory(
            window=config.working_memory_window, db=self._db,
        )
        self.long_term: LongTermMemory = LongTermMemory(db=self._db)

    # ── Persistence (all DB-backed; no files) ──────────────────────────────

    def load(self) -> None:
        """Populate self.state from the DB (session_state + approaches + trajectories)."""
        s = self._db.load_session_state()
        approaches = self._db.get_approaches_tried()
        traj = self._db.get_trajectories()
        embeds = self._db.get_hypothesis_embeddings()

        self.state = SessionState(
            iteration=int(s.get("iteration", 0)),
            phase=str(s.get("phase", "A")),
            consecutive_dual_success=int(s.get("consecutive_dual_success", 0)),
            best_win_rate=float(s.get("best_win_rate", 0.0)),
            best_trade_count=int(s.get("best_trade_count", 0)),
            best_pnl=float(s.get("best_pnl", 0.0)),
            best_composite=float(s.get("best_composite", 0.0)),
            approaches_tried=[
                {
                    "slug": a["slug"],
                    "description": a["description"],
                    "iteration": a["iteration"],
                    "result": a["result"],
                    "reverted": a["reverted"],
                }
                for a in approaches
            ],
            blocked_approaches=self._db.get_blocked_approaches(),
            insights=list(s.get("insights", [])),
            wr_trajectory=traj["wr"],
            pnl_trajectory=traj["pnl"],
            trade_count_trajectory=traj["trade_count"],
            composite_score_trajectory=traj["composite"],
            tier1_false_positives=int(s.get("tier1_false_positives", 0)),
            hypothesis_embeddings=embeds,
            current_hypothesis_slug=str(s.get("current_hypothesis_slug", "")),
        )

    def save(self) -> None:
        """Flush scalar session-state fields back to the DB.

        Trajectories, approaches, embeddings, and memories are written by
        their respective helpers as they mutate — no bulk-serialisation
        needed here.
        """
        self._db.save_session_state({
            "iteration": self.state.iteration,
            "phase": self.state.phase,
            "consecutive_dual_success": self.state.consecutive_dual_success,
            "best_win_rate": self.state.best_win_rate,
            "best_trade_count": self.state.best_trade_count,
            "best_pnl": self.state.best_pnl,
            "best_composite": self.state.best_composite,
            "tier1_false_positives": self.state.tier1_false_positives,
            "current_hypothesis_slug": self.state.current_hypothesis_slug,
            "insights": self.state.insights,
        })

    # ── Context for LLM calls ──────────────────────────────────────────────

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

    # ── Iteration lifecycle ────────────────────────────────────────────────

    def record_iteration(self, record: IterationRecord) -> None:
        # 1) rolling-window working memory (DB-backed)
        self.working.add(record)

        # 2) trajectory row (DB) + mirror to in-memory state for callers that
        #    still read state.*_trajectory during the current run
        self._db.append_trajectory(
            iteration=record.iteration,
            wr=record.win_rate,
            pnl=record.pnl,
            trade_count=record.trade_count,
            composite=record.composite_score,
        )
        self.state.wr_trajectory.append(record.win_rate)
        self.state.pnl_trajectory.append(record.pnl)
        self.state.trade_count_trajectory.append(record.trade_count)
        self.state.composite_score_trajectory.append(record.composite_score)

        # 3) bests
        if record.composite_score > self.state.best_composite:
            self.state.best_composite = record.composite_score
            self.state.best_win_rate = record.win_rate
            self.state.best_pnl = record.pnl
            self.state.best_trade_count = record.trade_count

    def record_approach(self, slug: str, description: str, iteration: int,
                        result: str, reverted: bool) -> None:
        """Append an approach to both the DB audit trail and in-memory state."""
        self._db.record_approach(slug, description, iteration, result, reverted)
        self.state.approaches_tried.append({
            "slug": slug,
            "description": description,
            "iteration": iteration,
            "result": result,
            "reverted": reverted,
        })

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

    # ── Phase management ──────────────────────────────────────────────────

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

    # ── Success tracking ──────────────────────────────────────────────────

    def record_success_run(self, result: BacktestResult) -> int:
        self.state.consecutive_dual_success += 1
        return self.state.consecutive_dual_success

    def reset_consecutive_success(self) -> None:
        self.state.consecutive_dual_success = 0