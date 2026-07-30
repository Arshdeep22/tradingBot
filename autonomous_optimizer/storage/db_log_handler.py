"""Python logging handler that writes log records into the agent SQLite DB.

Every log line is stamped with an `agent` field (`'optimizer'` or
`'trading_bot'`) and, when inside a trading-agent run, a `run_id`, so the
optimizer can later ask questions like "show me the trading bot's logs
for run abc123".

The handler picks those up automatically from `contextvars` in
`autonomous_optimizer.storage.agent_db.agent_scope(...)`, so callers
usually don't have to pass them explicitly.
"""
from __future__ import annotations

import logging
from typing import Optional

from autonomous_optimizer.storage.agent_db import (
    AgentDB,
    current_agent,
    current_run_id,
    get_agent_db,
)


class SQLiteLogHandler(logging.Handler):
    """Persist every LogRecord into `AgentDB.runtime_logs`.

    Parameters
    ----------
    db : AgentDB, optional
        Which AgentDB instance to write to. Defaults to the singleton.
    level : int
        Standard logging level.
    agent : str, optional
        Fixed agent label for this handler. If provided, every record is
        forced to this agent (useful when you want a dedicated handler for
        a specific agent). If None (default), the handler reads
        `current_agent` from the context var, so a single handler can be
        shared and still correctly attribute logs to whichever agent is
        active in the current call stack.
    """

    def __init__(self, db: Optional[AgentDB] = None,
                 level: int = logging.INFO,
                 agent: Optional[str] = None):
        super().__init__(level=level)
        self._db = db or get_agent_db()
        self._fixed_agent = agent

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            iteration = getattr(record, "iteration", None)
            agent = self._fixed_agent or current_agent.get()
            run_id = current_run_id.get()
            self._db.add_log(
                level=record.levelname,
                logger_name=record.name,
                message=msg,
                iteration=iteration,
                agent=agent,
                run_id=run_id,
            )
        except Exception:
            self.handleError(record)


def install_db_logging(level: int = logging.INFO,
                       also_console: bool = True,
                       agent: Optional[str] = None,
                       console_prefix: Optional[str] = None) -> None:
    """Attach a SQLite-backed handler to the root logger.

    Parameters
    ----------
    level : int
        Root log level.
    also_console : bool
        If True, also attach a `StreamHandler` for live console output.
        NO `FileHandler` is ever attached — the DB is the durable log store.
    agent : str, optional
        If set, forces every emitted log to this agent name. If None the
        handler uses `contextvars` so multiple agents can share the same
        root logger and still be tagged correctly.
    console_prefix : str, optional
        String prepended to every console log line (e.g. "[OPT]" or "[BOT]")
        so operators can eyeball which agent produced which line.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Never write log FILES — remove any pre-existing FileHandlers.
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)

    fmt_console = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if console_prefix:
        fmt_console = f"{console_prefix} {fmt_console}"
    fmt_db = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    # SQLite handler (always).
    if not any(isinstance(h, SQLiteLogHandler) for h in root.handlers):
        db_handler = SQLiteLogHandler(level=level, agent=agent)
        db_handler.setFormatter(logging.Formatter(fmt_db))
        root.addHandler(db_handler)

    # Console handler (optional).
    if also_console and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, SQLiteLogHandler)
        for h in root.handlers
    ):
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(fmt_console))
        ch.setLevel(level)
        root.addHandler(ch)