"""SQLite-backed storage for optimizer + trading agents.

All agent-owned state (session state, memories, iteration records,
hypothesis embeddings, tool invocation traces, runtime log lines,
trading-agent config, runs, decisions, and trades) is persisted here —
no JSON/log files on disk.
"""
from autonomous_optimizer.storage.agent_db import (
    AgentDB,
    agent_scope,
    current_agent,
    current_run_id,
    get_agent_db,
)
from autonomous_optimizer.storage.db_log_handler import (
    SQLiteLogHandler,
    install_db_logging,
)

__all__ = [
    "AgentDB",
    "get_agent_db",
    "agent_scope",
    "current_agent",
    "current_run_id",
    "SQLiteLogHandler",
    "install_db_logging",
]