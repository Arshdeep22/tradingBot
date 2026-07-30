"""
Verify that the agent uses a local SQLite DB for all persistent data:
  * session state          → database/agent.db (session_state table)
  * working / long-term memory → agent.db (working_memory, phase_summaries, ...)
  * runtime logs           → agent.db (runtime_logs)
  * tool invocations       → agent.db (tool_invocations)

Nothing should be written to autonomous_optimizer/context/session_state.json
or logs/*.log by any of the migrated components.
"""
from __future__ import annotations

import gc
import logging
import os
import sqlite3
import sys
import tempfile

# Make the repo root importable when running this file directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _fresh_db(tmpdir: str):
    """Build a fresh AgentDB pointed at a temp file (isolated from repo db)."""
    from autonomous_optimizer.storage.agent_db import AgentDB
    return AgentDB(db_path=os.path.join(tmpdir, "agent.db"))


def _tmpdir():
    # ignore_cleanup_errors=True → Windows won't fail the test if SQLite's
    # WAL/SHM file hasn't been fully released by the OS yet.
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def test_schema_created():
    with _tmpdir() as td:
        db = _fresh_db(td)
        try:
            with sqlite3.connect(db._db_path) as c:
                names = {
                    r[0] for r in c.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            expected = {
                "session_state", "working_memory", "phase_summaries",
                "hypothesis_embeddings", "blocked_approaches",
                "approaches_tried", "trajectories", "runtime_logs",
                "tool_invocations",
            }
            missing = expected - names
            assert not missing, f"missing tables: {missing}"
            print("OK schema_created:", sorted(names))
        finally:
            db.close()
            del db
            gc.collect()


def test_session_state_roundtrip():
    with _tmpdir() as td:
        db = _fresh_db(td)
        try:
            db.save_session_state({
                "iteration": 7,
                "phase": "B",
                "consecutive_dual_success": 2,
                "best_win_rate": 61.5,
                "best_trade_count": 42,
                "best_pnl": 12345.6,
                "best_composite": 0.71,
                "tier1_false_positives": 3,
                "current_hypothesis_slug": "test-slug",
                "insights": ["works well when regime = trending"],
            })
            loaded = db.load_session_state()
            assert loaded["iteration"] == 7
            assert loaded["phase"] == "B"
            assert loaded["consecutive_dual_success"] == 2
            assert loaded["best_win_rate"] == 61.5
            assert loaded["current_hypothesis_slug"] == "test-slug"
            assert loaded["insights"] == ["works well when regime = trending"]
            print("OK session_state_roundtrip:", loaded)
        finally:
            db.close()
            del db
            gc.collect()


def test_working_memory_rolling_window():
    with _tmpdir() as td:
        db = _fresh_db(td)
        try:
            from autonomous_optimizer.memory.working_memory import (
                WorkingMemory, IterationRecord,
            )
            wm = WorkingMemory(window=3, db=db)
            for i in range(1, 6):
                wm.add(IterationRecord(
                    iteration=i, phase="A",
                    hypothesis_slug=f"h{i}",
                    hypothesis_description=f"desc {i}",
                    root_cause_category="cat",
                    win_rate=float(i), pnl=100.0*i,
                    trade_count=i, composite_score=0.1*i,
                    reverted=False,
                ))
            got = wm.get_last(10)
            iters = [r.iteration for r in got]
            assert iters == [3, 4, 5], iters
            print("OK working_memory_rolling_window:", iters)
        finally:
            db.close()
            del db
            gc.collect()


def test_long_term_memory_persists_across_instances():
    with _tmpdir() as td:
        db = _fresh_db(td)
        try:
            from autonomous_optimizer.memory.long_term_memory import (
                LongTermMemory, PhaseSummary,
            )
            ltm = LongTermMemory(db=db)
            ltm.add_phase_summary(PhaseSummary(
                phase="A", iterations_run=5, best_composite=0.4,
                breakthroughs=["b1"], dead_ends=["d1"],
                insight="phase A complete",
            ))
            ltm.block_approach("do-not-do-this")

            # New instance, same DB → sees the data.
            ltm2 = LongTermMemory(db=db)
            summaries = ltm2.get_phase_summaries()
            assert len(summaries) == 1
            assert summaries[0].phase == "A"
            assert summaries[0].breakthroughs == ["b1"]
            assert ltm2.is_blocked("this is do-not-do-this variation")
            print("OK long_term_memory_persists:",
                  [s.phase for s in summaries], ltm2._blocked_approaches)
        finally:
            db.close()
            del db
            gc.collect()


def test_runtime_logs_go_to_db_not_files():
    with _tmpdir() as td:
        db = _fresh_db(td)
        try:
            from autonomous_optimizer.storage.db_log_handler import SQLiteLogHandler
            h = SQLiteLogHandler(db=db, level=logging.INFO)
            h.setFormatter(logging.Formatter("%(message)s"))
            root = logging.getLogger("agentdb-test")
            root.setLevel(logging.INFO)
            root.handlers.clear()
            root.propagate = False
            root.addHandler(h)

            root.info("iteration 42 starting")
            root.warning("something odd")

            rows = db.tail_logs(10)
            msgs = [r["message"] for r in rows]
            assert any("iteration 42 starting" in m for m in msgs), msgs
            assert any("something odd" in m for m in msgs), msgs

            # No .log file should have been written by this handler.
            for name in os.listdir(td):
                assert not name.endswith(".log"), f"unexpected log file: {name}"
            print("OK runtime_logs_go_to_db_not_files:", msgs)

            root.removeHandler(h)
        finally:
            db.close()
            del db
            gc.collect()


def test_tool_invocations_recorded():
    with _tmpdir() as td:
        db = _fresh_db(td)
        try:
            db.record_tool(
                tool_name="code_editor", action="write_file",
                args={"path": "core/foo.py"}, result={"bytes": 123},
                ok=True, iteration=5,
            )
            db.record_tool(
                tool_name="backtest_runner", action="run",
                args={"days": 50}, ok=False, error="boom",
            )
            got = db.get_tool_invocations(limit=10)
            actions = [(r["tool_name"], r["action"], r["ok"]) for r in got]
            assert ("code_editor", "write_file", True) in actions
            assert ("backtest_runner", "run", False) in actions
            wf = next(r for r in got if r["action"] == "write_file")
            assert wf["args"] == {"path": "core/foo.py"}
            assert wf["result"] == {"bytes": 123}
            print("OK tool_invocations_recorded:", actions)
        finally:
            db.close()
            del db
            gc.collect()


def test_session_manager_no_file_persistence():
    with _tmpdir() as td:
        from autonomous_optimizer.storage.agent_db import AgentDB
        from autonomous_optimizer.config import AgentConfig
        from autonomous_optimizer.session_manager import SessionManager
        from autonomous_optimizer.memory.working_memory import IterationRecord

        db = AgentDB(db_path=os.path.join(td, "agent.db"))
        try:
            cfg = AgentConfig(
                working_memory_window=4, episodic_summarize_every=2,
                repo_root=td,
                state_file=os.path.join(td, "should_not_exist.json"),
            )
            sm = SessionManager(cfg, db=db)

            sm.state.iteration = 0
            sm.state.phase = "A"

            for i in range(1, 4):
                sm.record_iteration(IterationRecord(
                    iteration=i, phase="A",
                    hypothesis_slug=f"h{i}", hypothesis_description=f"d{i}",
                    root_cause_category="c",
                    win_rate=50 + i, pnl=1000.0 * i,
                    trade_count=10 * i, composite_score=0.1 * i,
                    reverted=False,
                ))
                sm.record_approach(
                    slug=f"h{i}", description=f"d{i}", iteration=i,
                    result="improved", reverted=False,
                )
                sm.state.iteration = i
                sm.save()

            sm2 = SessionManager(cfg, db=db)
            sm2.load()
            assert sm2.state.iteration == 3
            assert len(sm2.state.approaches_tried) == 3
            assert sm2.state.wr_trajectory == [51.0, 52.0, 53.0]

            assert not os.path.exists(cfg.state_file), (
                f"session_manager still writes to {cfg.state_file}"
            )
            print(
                "OK session_manager_no_file_persistence: iter=",
                sm2.state.iteration, "approaches=", len(sm2.state.approaches_tried),
            )
        finally:
            db.close()
            del db
            gc.collect()


if __name__ == "__main__":
    test_schema_created()
    test_session_state_roundtrip()
    test_working_memory_rolling_window()
    test_long_term_memory_persists_across_instances()
    test_runtime_logs_go_to_db_not_files()
    test_tool_invocations_recorded()
    test_session_manager_no_file_persistence()
    print("\nALL TESTS PASSED")