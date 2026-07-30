"""Quick sanity dump of the live agent DB — for manual verification only."""
import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from autonomous_optimizer.storage.agent_db import AgentDB

db = AgentDB()  # default path: database/agent.db
print(f"DB path: {db._db_path}")

c = sqlite3.connect(db._db_path)
c.row_factory = sqlite3.Row

print("\nTables:")
for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall():
    print(f"  - {r[0]}")

print("\nRow counts:")
for t in [
    "session_state", "working_memory", "runtime_logs",
    "tool_invocations", "phase_summaries", "hypothesis_embeddings",
    "blocked_approaches", "approaches_tried", "trajectories",
]:
    n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  - {t}: {n}")

print("\nsession_state row:")
row = c.execute("SELECT * FROM session_state WHERE id=1").fetchone()
if row:
    for k in row.keys():
        print(f"  {k}: {row[k]}")
c.close()