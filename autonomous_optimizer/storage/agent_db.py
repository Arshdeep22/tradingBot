"""
Local SQLite database for BOTH the optimizer agent and the trading agent.

Design goals:
  * Two agents share one DB file (database/agent.db) but every row that
    could belong to either is tagged with `agent` ('optimizer' | 'trading_bot')
    and grouped by `run_id` so their memories and logs stay cleanly separated.
  * No JSON files, no *.log files — only rows.

Table layout
============

Optimizer-only tables (memory / audit trail specific to the optimizer)
---------------------------------------------------------------------
* session_state              — singleton row, current optimizer iteration/phase/bests
* working_memory             — rolling window of recent iterations
* phase_summaries            — long-term compressed learnings per phase
* hypothesis_embeddings      — vector memory of past hypotheses
* blocked_approaches         — approaches the critic banned
* approaches_tried           — full audit trail of every hypothesis
* trajectories               — per-iteration metric samples

Trading-agent tables (state the trading bot needs to operate)
-------------------------------------------------------------
* trading_agent_config       — singleton row: system_prompt, llm_model, risk knobs
* trading_agent_memory       — lessons/notes the optimizer curates for the bot
* trading_agent_runs         — one row per invocation (backtest/paper/live)
* trading_agent_decisions    — every LLM decision the trading bot makes
* trading_agent_trades       — every trade opened/closed inside a run

Shared / cross-agent tables (tagged with `agent` + `run_id`)
------------------------------------------------------------
* runtime_logs               — every log record (replaces *.log files)
* tool_invocations           — every tool call from EITHER agent
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import sqlite3
import threading
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "database",
)
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "agent.db")

# ─────────────────────────────────────────────────────────────────────────────
# Context variables so log handlers / tool tracers know WHICH agent + run they
# are executing under, without having to plumb a `db` object everywhere.
# ─────────────────────────────────────────────────────────────────────────────
current_agent: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_agent", default="optimizer",
)
current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_run_id", default=None,
)


@contextlib.contextmanager
def agent_scope(agent: str, run_id: Optional[str] = None) -> Iterator[str]:
    """Set `current_agent` / `current_run_id` for a block of code.

    Usage:
        with agent_scope("trading_bot", run_id="abc123"):
            ...   # every log line + tool invocation is stamped agent+run_id
    """
    rid = run_id or f"run-{uuid.uuid4().hex[:12]}"
    a_tok = current_agent.set(agent)
    r_tok = current_run_id.set(rid)
    try:
        yield rid
    finally:
        current_agent.reset(a_tok)
        current_run_id.reset(r_tok)


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_json_default)


class AgentDB:
    """Thread-safe SQLite wrapper for optimizer + trading-agent state."""

    _SCHEMA = [
        # ── optimizer session state (singleton row, id=1) ────────────────
        """CREATE TABLE IF NOT EXISTS session_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            iteration INTEGER NOT NULL DEFAULT 0,
            phase TEXT NOT NULL DEFAULT 'A',
            consecutive_dual_success INTEGER NOT NULL DEFAULT 0,
            best_win_rate REAL NOT NULL DEFAULT 0.0,
            best_trade_count INTEGER NOT NULL DEFAULT 0,
            best_pnl REAL NOT NULL DEFAULT 0.0,
            best_composite REAL NOT NULL DEFAULT 0.0,
            tier1_false_positives INTEGER NOT NULL DEFAULT 0,
            current_hypothesis_slug TEXT NOT NULL DEFAULT '',
            insights_json TEXT NOT NULL DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        # ── optimizer working memory ─────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS working_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration INTEGER NOT NULL,
            phase TEXT NOT NULL,
            hypothesis_slug TEXT NOT NULL,
            hypothesis_description TEXT NOT NULL,
            root_cause_category TEXT NOT NULL,
            win_rate REAL NOT NULL,
            pnl REAL NOT NULL,
            trade_count INTEGER NOT NULL,
            composite_score REAL NOT NULL,
            reverted INTEGER NOT NULL,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        # ── optimizer long-term memory ───────────────────────────────────
        """CREATE TABLE IF NOT EXISTS phase_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phase TEXT NOT NULL,
            iterations_run INTEGER NOT NULL,
            best_composite REAL NOT NULL,
            breakthroughs_json TEXT NOT NULL DEFAULT '[]',
            dead_ends_json TEXT NOT NULL DEFAULT '[]',
            insight TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS hypothesis_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            description TEXT NOT NULL,
            result TEXT NOT NULL,
            iteration INTEGER NOT NULL,
            embedding_json TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS blocked_approaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS approaches_tried (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            description TEXT NOT NULL,
            iteration INTEGER NOT NULL,
            result TEXT NOT NULL,
            reverted INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS trajectories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            pnl REAL NOT NULL,
            trade_count INTEGER NOT NULL,
            composite_score REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        # ── shared: logs (tagged with agent+run_id) ──────────────────────
        """CREATE TABLE IF NOT EXISTS runtime_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            agent TEXT NOT NULL DEFAULT 'optimizer',
            run_id TEXT,
            level TEXT NOT NULL,
            logger_name TEXT NOT NULL,
            message TEXT NOT NULL,
            iteration INTEGER
        )""",

        # ── shared: tool invocations (tagged with agent+run_id) ──────────
        """CREATE TABLE IF NOT EXISTS tool_invocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            agent TEXT NOT NULL DEFAULT 'optimizer',
            run_id TEXT,
            iteration INTEGER,
            tool_name TEXT NOT NULL,
            action TEXT NOT NULL,
            args_json TEXT DEFAULT '{}',
            result_json TEXT DEFAULT '{}',
            ok INTEGER NOT NULL DEFAULT 1,
            error TEXT
        )""",

        # ── trading agent: singleton config ──────────────────────────────
        """CREATE TABLE IF NOT EXISTS trading_agent_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            system_prompt TEXT NOT NULL DEFAULT '',
            llm_model TEXT NOT NULL DEFAULT 'anthropic--claude-4.5-haiku',
            mode TEXT NOT NULL DEFAULT 'backtest',
            risk_params_json TEXT NOT NULL DEFAULT '{}',
            strategy_params_json TEXT NOT NULL DEFAULT '{}',
            symbols_json TEXT NOT NULL DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        # ── trading agent: curated lessons / memory ──────────────────────
        """CREATE TABLE IF NOT EXISTS trading_agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,               -- 'lesson' | 'symbol_note' | 'regime_note'
            symbol TEXT,                       -- nullable — some lessons are global
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'optimizer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",

        # ── trading agent: one row per invocation ────────────────────────
        """CREATE TABLE IF NOT EXISTS trading_agent_runs (
            run_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,                -- 'backtest' | 'paper' | 'live'
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            days INTEGER,
            symbols_json TEXT DEFAULT '[]',
            win_rate REAL,
            total_pnl REAL,
            trade_count INTEGER,
            trades_per_day REAL,
            notes TEXT DEFAULT '',
            triggered_by TEXT DEFAULT 'optimizer',
            ok INTEGER NOT NULL DEFAULT 1,
            error TEXT
        )""",

        # ── trading agent: every LLM decision inside a run ───────────────
        """CREATE TABLE IF NOT EXISTS trading_agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            bar_ts TIMESTAMP,                  -- the candle the decision applies to
            context_json TEXT DEFAULT '{}',    -- indicators / zone summary fed to the LLM
            decision TEXT NOT NULL,            -- 'BUY' | 'SELL' | 'HOLD' | 'CLOSE'
            confidence REAL,
            reasoning TEXT,
            raw_llm_response TEXT
        )""",

        # ── trading agent: every trade opened/closed inside a run ────────
        """CREATE TABLE IF NOT EXISTS trading_agent_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            decision_id INTEGER,               -- FK to trading_agent_decisions (nullable)
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,                -- 'BUY' | 'SELL'
            quantity INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            stop_loss REAL,
            target REAL,
            pnl REAL,
            pnl_percent REAL,
            entry_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exit_ts TIMESTAMP,
            status TEXT DEFAULT 'OPEN',        -- 'OPEN' | 'CLOSED'
            exit_reason TEXT
        )""",
    ]

    _INDEXES = [
        "CREATE INDEX IF NOT EXISTS idx_working_iter ON working_memory(iteration)",
        "CREATE INDEX IF NOT EXISTS idx_traj_iter ON trajectories(iteration)",
        "CREATE INDEX IF NOT EXISTS idx_logs_ts ON runtime_logs(ts)",
        "CREATE INDEX IF NOT EXISTS idx_logs_iter ON runtime_logs(iteration)",
        "CREATE INDEX IF NOT EXISTS idx_logs_agent ON runtime_logs(agent)",
        "CREATE INDEX IF NOT EXISTS idx_logs_run ON runtime_logs(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_tools_iter ON tool_invocations(iteration)",
        "CREATE INDEX IF NOT EXISTS idx_tools_name ON tool_invocations(tool_name)",
        "CREATE INDEX IF NOT EXISTS idx_tools_agent ON tool_invocations(agent)",
        "CREATE INDEX IF NOT EXISTS idx_tools_run ON tool_invocations(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_embed_slug ON hypothesis_embeddings(slug)",
        "CREATE INDEX IF NOT EXISTS idx_tarun_started ON trading_agent_runs(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_tadec_run ON trading_agent_decisions(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_tatrade_run ON trading_agent_trades(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_tatrade_symbol ON trading_agent_trades(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_tamem_symbol ON trading_agent_memory(symbol)",
    ]

    # Migration helpers — additive columns for repos that already have the old
    # schema. Runs every startup, idempotent.
    _COLUMN_ADDS: list[tuple[str, str, str]] = [
        ("runtime_logs", "agent", "TEXT NOT NULL DEFAULT 'optimizer'"),
        ("runtime_logs", "run_id", "TEXT"),
        ("tool_invocations", "agent", "TEXT NOT NULL DEFAULT 'optimizer'"),
        ("tool_invocations", "run_id", "TEXT"),
    ]

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    # ── connection ─────────────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def close(self) -> None:
        try:
            with self._lock, self._conn() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("PRAGMA journal_mode=DELETE")
        except Exception:
            pass

    def _init_schema(self) -> None:
        with self._lock, self._conn() as conn:
            for stmt in self._SCHEMA:
                conn.execute(stmt)

            # Additive migrations for older DBs.
            for table, col, decl in self._COLUMN_ADDS:
                cols = {
                    row["name"]
                    for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

            for stmt in self._INDEXES:
                conn.execute(stmt)

            conn.execute("INSERT OR IGNORE INTO session_state (id) VALUES (1)")
            conn.execute("INSERT OR IGNORE INTO trading_agent_config (id) VALUES (1)")

    # ══════════════════════════════════════════════════════════════════════
    # Optimizer: session_state (singleton row id=1)
    # ══════════════════════════════════════════════════════════════════════
    def load_session_state(self) -> dict:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM session_state WHERE id = 1"
            ).fetchone()
            if row is None:
                return {}
            data = dict(row)
            data["insights"] = json.loads(data.pop("insights_json", "[]") or "[]")
            return data

    def save_session_state(self, state: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """UPDATE session_state SET
                    iteration = ?, phase = ?, consecutive_dual_success = ?,
                    best_win_rate = ?, best_trade_count = ?, best_pnl = ?,
                    best_composite = ?, tier1_false_positives = ?,
                    current_hypothesis_slug = ?, insights_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1""",
                (
                    int(state.get("iteration", 0)),
                    str(state.get("phase", "A")),
                    int(state.get("consecutive_dual_success", 0)),
                    float(state.get("best_win_rate", 0.0)),
                    int(state.get("best_trade_count", 0)),
                    float(state.get("best_pnl", 0.0)),
                    float(state.get("best_composite", 0.0)),
                    int(state.get("tier1_false_positives", 0)),
                    str(state.get("current_hypothesis_slug", "")),
                    _dumps(state.get("insights", [])),
                ),
            )

    # ══════════════════════════════════════════════════════════════════════
    # Optimizer: trajectories
    # ══════════════════════════════════════════════════════════════════════
    def append_trajectory(self, iteration: int, wr: float, pnl: float,
                          trade_count: int, composite: float) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO trajectories
                   (iteration, win_rate, pnl, trade_count, composite_score)
                   VALUES (?, ?, ?, ?, ?)""",
                (iteration, wr, pnl, trade_count, composite),
            )

    def get_trajectories(self) -> dict[str, list]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT win_rate, pnl, trade_count, composite_score "
                "FROM trajectories ORDER BY id ASC"
            ).fetchall()
        return {
            "wr": [r["win_rate"] for r in rows],
            "pnl": [r["pnl"] for r in rows],
            "trade_count": [r["trade_count"] for r in rows],
            "composite": [r["composite_score"] for r in rows],
        }

    # ══════════════════════════════════════════════════════════════════════
    # Optimizer: working memory
    # ══════════════════════════════════════════════════════════════════════
    def add_working_record(self, rec: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO working_memory
                   (iteration, phase, hypothesis_slug, hypothesis_description,
                    root_cause_category, win_rate, pnl, trade_count,
                    composite_score, reverted, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec["iteration"], rec["phase"], rec["hypothesis_slug"],
                    rec["hypothesis_description"], rec["root_cause_category"],
                    rec["win_rate"], rec["pnl"], rec["trade_count"],
                    rec["composite_score"], int(bool(rec["reverted"])),
                    rec.get("notes", ""),
                ),
            )

    def get_working_records(self, limit: Optional[int] = None) -> list[dict]:
        q = "SELECT * FROM working_memory ORDER BY id ASC"
        with self._lock, self._conn() as conn:
            rows = conn.execute(q).fetchall()
        records = [dict(r) for r in rows]
        for r in records:
            r["reverted"] = bool(r["reverted"])
        if limit is not None and limit < len(records):
            return records[-limit:]
        return records

    def evict_working_records(self, keep_last: int) -> list[dict]:
        with self._lock, self._conn() as conn:
            all_rows = conn.execute(
                "SELECT * FROM working_memory ORDER BY id ASC"
            ).fetchall()
            if keep_last >= len(all_rows):
                return []
            evicted = [dict(r) for r in all_rows[:len(all_rows) - keep_last]]
            evicted_ids = [r["id"] for r in evicted]
            placeholders = ",".join("?" * len(evicted_ids))
            conn.execute(
                f"DELETE FROM working_memory WHERE id IN ({placeholders})",
                evicted_ids,
            )
        for r in evicted:
            r["reverted"] = bool(r["reverted"])
        return evicted

    # ══════════════════════════════════════════════════════════════════════
    # Optimizer: long-term memory
    # ══════════════════════════════════════════════════════════════════════
    def add_phase_summary(self, summary: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO phase_summaries
                   (phase, iterations_run, best_composite,
                    breakthroughs_json, dead_ends_json, insight)
                   VALUES (?,?,?,?,?,?)""",
                (
                    summary["phase"], summary["iterations_run"],
                    summary["best_composite"],
                    _dumps(summary.get("breakthroughs", [])),
                    _dumps(summary.get("dead_ends", [])),
                    summary.get("insight", ""),
                ),
            )

    def get_phase_summaries(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM phase_summaries ORDER BY id ASC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["breakthroughs"] = json.loads(d.pop("breakthroughs_json") or "[]")
            d["dead_ends"] = json.loads(d.pop("dead_ends_json") or "[]")
            out.append(d)
        return out

    def add_hypothesis_embedding(self, slug: str, description: str,
                                 result: str, iteration: int,
                                 embedding: list[float]) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO hypothesis_embeddings
                   (slug, description, result, iteration, embedding_json)
                   VALUES (?,?,?,?,?)""",
                (slug, description, result, iteration, _dumps(embedding)),
            )

    def get_hypothesis_embeddings(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM hypothesis_embeddings ORDER BY id ASC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["embedding"] = json.loads(d.pop("embedding_json") or "[]")
            out.append(d)
        return out

    def block_approach(self, description: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO blocked_approaches (description) VALUES (?)",
                (description,),
            )

    def get_blocked_approaches(self) -> list[str]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT description FROM blocked_approaches ORDER BY id ASC"
            ).fetchall()
        return [r["description"] for r in rows]

    def record_approach(self, slug: str, description: str, iteration: int,
                        result: str, reverted: bool) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO approaches_tried
                   (slug, description, iteration, result, reverted)
                   VALUES (?,?,?,?,?)""",
                (slug, description, iteration, result, int(bool(reverted))),
            )

    def get_approaches_tried(self, limit: Optional[int] = None) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM approaches_tried ORDER BY id ASC"
            ).fetchall()
        out = [dict(r) for r in rows]
        for r in out:
            r["reverted"] = bool(r["reverted"])
        if limit is not None and limit < len(out):
            return out[-limit:]
        return out

    # ══════════════════════════════════════════════════════════════════════
    # Shared: runtime logs (tagged with agent + run_id)
    # ══════════════════════════════════════════════════════════════════════
    def add_log(self, level: str, logger_name: str, message: str,
                iteration: Optional[int] = None,
                agent: Optional[str] = None,
                run_id: Optional[str] = None) -> None:
        a = agent or current_agent.get()
        r = run_id if run_id is not None else current_run_id.get()
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO runtime_logs
                   (agent, run_id, level, logger_name, message, iteration)
                   VALUES (?,?,?,?,?,?)""",
                (a, r, level, logger_name, message, iteration),
            )

    def tail_logs(self, n: int = 200, agent: Optional[str] = None,
                  run_id: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM runtime_logs"
        clauses, params = [], []
        if agent is not None:
            clauses.append("agent = ?")
            params.append(agent)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(n)
        with self._lock, self._conn() as conn:
            rows = conn.execute(q, tuple(params)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ══════════════════════════════════════════════════════════════════════
    # Shared: tool invocations (tagged with agent + run_id)
    # ══════════════════════════════════════════════════════════════════════
    def record_tool(self, tool_name: str, action: str,
                    args: Any = None, result: Any = None,
                    ok: bool = True, error: Optional[str] = None,
                    iteration: Optional[int] = None,
                    agent: Optional[str] = None,
                    run_id: Optional[str] = None) -> None:
        a = agent or current_agent.get()
        r = run_id if run_id is not None else current_run_id.get()
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO tool_invocations
                   (agent, run_id, iteration, tool_name, action,
                    args_json, result_json, ok, error)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    a, r, iteration, tool_name, action,
                    _dumps(args or {}), _dumps(result or {}),
                    1 if ok else 0, error,
                ),
            )

    def get_tool_invocations(self, tool_name: Optional[str] = None,
                             agent: Optional[str] = None,
                             run_id: Optional[str] = None,
                             limit: int = 100) -> list[dict]:
        q = "SELECT * FROM tool_invocations"
        clauses, params = [], []
        if tool_name:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if agent is not None:
            clauses.append("agent = ?")
            params.append(agent)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._conn() as conn:
            rows = conn.execute(q, tuple(params)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["ok"] = bool(d["ok"])
            d["args"] = json.loads(d.pop("args_json") or "{}")
            d["result"] = json.loads(d.pop("result_json") or "{}")
            out.append(d)
        return list(reversed(out))

    # ══════════════════════════════════════════════════════════════════════
    # Trading agent: config (singleton row id=1)
    # ══════════════════════════════════════════════════════════════════════
    def load_trading_config(self) -> dict:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM trading_agent_config WHERE id = 1"
            ).fetchone()
        if row is None:
            return {}
        d = dict(row)
        d["risk_params"] = json.loads(d.pop("risk_params_json") or "{}")
        d["strategy_params"] = json.loads(d.pop("strategy_params_json") or "{}")
        d["symbols"] = json.loads(d.pop("symbols_json") or "[]")
        return d

    def save_trading_config(self, cfg: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """UPDATE trading_agent_config SET
                    system_prompt = ?, llm_model = ?, mode = ?,
                    risk_params_json = ?, strategy_params_json = ?,
                    symbols_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1""",
                (
                    str(cfg.get("system_prompt", "")),
                    str(cfg.get("llm_model", "anthropic--claude-4.5-haiku")),
                    str(cfg.get("mode", "backtest")),
                    _dumps(cfg.get("risk_params", {})),
                    _dumps(cfg.get("strategy_params", {})),
                    _dumps(cfg.get("symbols", [])),
                ),
            )

    # ══════════════════════════════════════════════════════════════════════
    # Trading agent: memory (curated lessons)
    # ══════════════════════════════════════════════════════════════════════
    def add_trading_lesson(self, kind: str, content: str,
                            symbol: Optional[str] = None,
                            source: str = "optimizer") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO trading_agent_memory (kind, symbol, content, source)
                   VALUES (?,?,?,?)""",
                (kind, symbol, content, source),
            )

    def get_trading_lessons(self, symbol: Optional[str] = None,
                             kind: Optional[str] = None,
                             limit: int = 200) -> list[dict]:
        q = "SELECT * FROM trading_agent_memory"
        clauses, params = [], []
        if symbol:
            clauses.append("(symbol IS NULL OR symbol = ?)")
            params.append(symbol)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._conn() as conn:
            rows = conn.execute(q, tuple(params)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ══════════════════════════════════════════════════════════════════════
    # Trading agent: runs / decisions / trades
    # ══════════════════════════════════════════════════════════════════════
    def start_trading_run(self, run_id: str, mode: str,
                           days: Optional[int] = None,
                           symbols: Optional[list[str]] = None,
                           triggered_by: str = "optimizer") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO trading_agent_runs
                   (run_id, mode, days, symbols_json, triggered_by, ok)
                   VALUES (?,?,?,?,?,1)""",
                (run_id, mode, days, _dumps(symbols or []), triggered_by),
            )

    def end_trading_run(self, run_id: str, *,
                         win_rate: Optional[float] = None,
                         total_pnl: Optional[float] = None,
                         trade_count: Optional[int] = None,
                         trades_per_day: Optional[float] = None,
                         notes: str = "", ok: bool = True,
                         error: Optional[str] = None) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """UPDATE trading_agent_runs SET
                    ended_at = CURRENT_TIMESTAMP,
                    win_rate = COALESCE(?, win_rate),
                    total_pnl = COALESCE(?, total_pnl),
                    trade_count = COALESCE(?, trade_count),
                    trades_per_day = COALESCE(?, trades_per_day),
                    notes = ?, ok = ?, error = ?
                    WHERE run_id = ?""",
                (
                    win_rate, total_pnl, trade_count, trades_per_day,
                    notes, 1 if ok else 0, error, run_id,
                ),
            )

    def get_trading_run(self, run_id: str) -> Optional[dict]:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM trading_agent_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["symbols"] = json.loads(d.pop("symbols_json") or "[]")
        d["ok"] = bool(d["ok"])
        return d

    def get_recent_trading_runs(self, limit: int = 20) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_agent_runs "
                "ORDER BY started_at DESC LIMIT ?", (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["symbols"] = json.loads(d.pop("symbols_json") or "[]")
            d["ok"] = bool(d["ok"])
            out.append(d)
        return out

    def record_trading_decision(self, run_id: str, symbol: str, decision: str,
                                 *, confidence: Optional[float] = None,
                                 reasoning: str = "",
                                 raw_llm_response: str = "",
                                 bar_ts: Optional[str] = None,
                                 context: Any = None) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO trading_agent_decisions
                   (run_id, symbol, bar_ts, context_json,
                    decision, confidence, reasoning, raw_llm_response)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    run_id, symbol, bar_ts, _dumps(context or {}),
                    decision, confidence, reasoning, raw_llm_response,
                ),
            )
            return cur.lastrowid

    def get_trading_decisions(self, run_id: str,
                               limit: int = 500) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_agent_decisions WHERE run_id = ? "
                "ORDER BY id ASC LIMIT ?", (run_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["context"] = json.loads(d.pop("context_json") or "{}")
            out.append(d)
        return out

    def record_trading_trade(self, run_id: str, symbol: str, side: str,
                              quantity: int, entry_price: float,
                              *, stop_loss: Optional[float] = None,
                              target: Optional[float] = None,
                              decision_id: Optional[int] = None) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO trading_agent_trades
                   (run_id, decision_id, symbol, side, quantity,
                    entry_price, stop_loss, target, status)
                   VALUES (?,?,?,?,?,?,?,?, 'OPEN')""",
                (
                    run_id, decision_id, symbol, side, quantity,
                    entry_price, stop_loss, target,
                ),
            )
            return cur.lastrowid

    def close_trading_trade(self, trade_id: int, exit_price: float,
                             *, pnl: Optional[float] = None,
                             pnl_percent: Optional[float] = None,
                             exit_reason: str = "") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """UPDATE trading_agent_trades SET
                    exit_price = ?, pnl = ?, pnl_percent = ?,
                    exit_ts = CURRENT_TIMESTAMP,
                    status = 'CLOSED', exit_reason = ?
                    WHERE id = ?""",
                (exit_price, pnl, pnl_percent, exit_reason, trade_id),
            )

    def get_trading_trades(self, run_id: str) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_agent_trades WHERE run_id = ? "
                "ORDER BY id ASC", (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ══════════════════════════════════════════════════════════════════════
    # Maintenance
    # ══════════════════════════════════════════════════════════════════════
    def reset_all(self) -> None:
        """Nuke every agent table (useful in tests / clean restart).

        The two singleton config rows are reset to their defaults rather than
        deleted so future callers still have a row to update.
        """
        tables = [
            "working_memory", "phase_summaries", "hypothesis_embeddings",
            "blocked_approaches", "approaches_tried", "trajectories",
            "runtime_logs", "tool_invocations",
            "trading_agent_memory", "trading_agent_runs",
            "trading_agent_decisions", "trading_agent_trades",
        ]
        with self._lock, self._conn() as conn:
            for t in tables:
                conn.execute(f"DELETE FROM {t}")
            conn.execute(
                "UPDATE session_state SET iteration=0, phase='A', "
                "consecutive_dual_success=0, best_win_rate=0, best_trade_count=0, "
                "best_pnl=0, best_composite=0, tier1_false_positives=0, "
                "current_hypothesis_slug='', insights_json='[]' WHERE id=1"
            )
            conn.execute(
                "UPDATE trading_agent_config SET "
                "system_prompt='', llm_model='anthropic--claude-4.5-haiku', "
                "mode='backtest', risk_params_json='{}', strategy_params_json='{}', "
                "symbols_json='[]', updated_at=CURRENT_TIMESTAMP WHERE id=1"
            )

    def reset_optimizer(self) -> None:
        """Reset only optimizer-owned tables; leave the trading agent alone."""
        tables = [
            "working_memory", "phase_summaries", "hypothesis_embeddings",
            "blocked_approaches", "approaches_tried", "trajectories",
        ]
        with self._lock, self._conn() as conn:
            for t in tables:
                conn.execute(f"DELETE FROM {t}")
            conn.execute("DELETE FROM runtime_logs WHERE agent = 'optimizer'")
            conn.execute("DELETE FROM tool_invocations WHERE agent = 'optimizer'")
            conn.execute(
                "UPDATE session_state SET iteration=0, phase='A', "
                "consecutive_dual_success=0, best_win_rate=0, best_trade_count=0, "
                "best_pnl=0, best_composite=0, tier1_false_positives=0, "
                "current_hypothesis_slug='', insights_json='[]' WHERE id=1"
            )

    def reset_trading_agent(self) -> None:
        """Reset only trading-agent-owned tables; leave the optimizer alone."""
        tables = [
            "trading_agent_memory", "trading_agent_runs",
            "trading_agent_decisions", "trading_agent_trades",
        ]
        with self._lock, self._conn() as conn:
            for t in tables:
                conn.execute(f"DELETE FROM {t}")
            conn.execute("DELETE FROM runtime_logs WHERE agent = 'trading_bot'")
            conn.execute("DELETE FROM tool_invocations WHERE agent = 'trading_bot'")
            conn.execute(
                "UPDATE trading_agent_config SET "
                "system_prompt='', llm_model='anthropic--claude-4.5-haiku', "
                "mode='backtest', risk_params_json='{}', strategy_params_json='{}', "
                "symbols_json='[]', updated_at=CURRENT_TIMESTAMP WHERE id=1"
            )


# ── module-level singleton ────────────────────────────────────────────────
_singleton: Optional[AgentDB] = None
_singleton_lock = threading.Lock()


def get_agent_db(db_path: Optional[str] = None) -> AgentDB:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = AgentDB(db_path=db_path)
    return _singleton