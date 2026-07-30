# Two-Agent Trading System — Optimizer + Trading Bot

This repo contains **two agents** that share one local SQLite database
(`database/agent.db`) but keep completely separate memory and logs.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      OPTIMIZER AGENT                                 │
│  goal: improve the Trading Agent until it wins consistently on       │
│        historical data, then STOP.                                   │
│  package:  autonomous_optimizer/                                     │
│  memory:   session_state, working_memory, phase_summaries,           │
│            hypothesis_embeddings, blocked_approaches,                │
│            approaches_tried, trajectories                            │
│  logs:     runtime_logs WHERE agent='optimizer'                      │
│  tools:    code_editor, git_ops, trading_bot (runs the bot)          │
└─────────────────────────────────────────────────────────────────────┘
                       ▼  drives (hot-reloaded)
┌─────────────────────────────────────────────────────────────────────┐
│                      TRADING AGENT                                   │
│  goal: given market + capital, decide + execute trades.              │
│  package:  trading_agent/                                            │
│  memory:   trading_agent_config, trading_agent_memory (lessons),     │
│            trading_agent_runs, trading_agent_decisions,              │
│            trading_agent_trades                                      │
│  logs:     runtime_logs WHERE agent='trading_bot'                    │
│  tools:    market_data, indicators, strategy, risk, broker, llm_advisor
│  modes:    backtest → paper → live (single config flag)              │
└─────────────────────────────────────────────────────────────────────┘
```

**No files are ever written by either agent** — no `logs/*.log`, no
`context/*.json`. Everything you need to inspect, debug, or resume is
in `database/agent.db`.

## Prerequisites

- Python 3.12
- Windows PowerShell
- `pip install -r requirements.txt`
- SAP AI Core credentials (already baked into `run_agent.ps1`)

## Run the optimizer (drives the trading agent in a loop)

```powershell
powershell -ExecutionPolicy Bypass -File .\run_agent.ps1
```

The optimizer will:
1. Load its state from `session_state` + memories.
2. Ask the Trading Agent to run a Tier-1 backtest (10 days). The trading
   agent's every tool call and LLM decision is written into the DB with
   `agent='trading_bot'` and a fresh `run_id`.
3. Read that run's traces, decide what's broken (a tool? the prompt? a
   lesson missing?), edit the appropriate file / DB row, `git snapshot`,
   hot-reload `trading_agent.*`, re-run.
4. If the result improves, `git commit`; else `git revert`. Repeat until
   3 consecutive dual-success runs (Tier-1 + Tier-2) then tag
   `goal-achieved` and stop.

Console output prefixes every line with `[OPT]` (optimizer) or `[BOT]`
(trading agent) so it's easy to see which agent is talking.

## Run just the trading agent (smoke test / manual)

```powershell
py -3.12 -m trading_agent --days 10 --symbols RELIANCE.NS TCS.NS
```

Every log line + tool call + decision + trade is persisted the same way,
tagged `agent='trading_bot'`, `triggered_by='cli'`.

## Inspect state

Everything is in `database/agent.db`. Some useful queries:

```sql
-- Optimizer state
SELECT * FROM session_state;
SELECT slug, result, reverted FROM approaches_tried ORDER BY id DESC LIMIT 10;

-- Trading agent's current config (edited by the optimizer)
SELECT system_prompt, llm_model, mode FROM trading_agent_config;

-- Recent trading-agent runs
SELECT run_id, mode, started_at, win_rate, total_pnl, trade_count
  FROM trading_agent_runs ORDER BY started_at DESC LIMIT 10;

-- Every LLM decision the trading agent made in a specific run
SELECT symbol, decision, confidence, reasoning
  FROM trading_agent_decisions WHERE run_id = 'tarun-...';

-- Which trading-bot tool failed in a specific run?
SELECT tool_name, action, error
  FROM tool_invocations
  WHERE agent = 'trading_bot' AND run_id = 'tarun-...' AND ok = 0;

-- Latest logs, separated by agent
SELECT ts, level, message FROM runtime_logs
  WHERE agent = 'optimizer' ORDER BY id DESC LIMIT 30;
SELECT ts, level, message FROM runtime_logs
  WHERE agent = 'trading_bot' ORDER BY id DESC LIMIT 30;
```

Or run the ready-made dumper:

```powershell
py -3.12 tests\_inspect_agent_db.py
```

## Reset the state

```python
from autonomous_optimizer.storage import get_agent_db
db = get_agent_db()
db.reset_optimizer()      # nukes optimizer memory + logs only
db.reset_trading_agent()  # nukes trading-agent memory + logs + runs
db.reset_all()            # nukes everything
```

## How the two agents interact

1. **Optimizer's `TradingBotTool`** is the only bridge. It:
   - Drops every `trading_agent.*` / `strategies.*` module from
     `sys.modules` (hot reload — the optimizer's freshest code edits
     become active without a subprocess).
   - Constructs a fresh `TradingAgent(config=…from DB…)` and runs a
     backtest through `TradingAgentRunner`.
2. Inside that run, `agent_scope('trading_bot', run_id=…)` (a
   `contextvars` context manager) is entered, so every subsequent log
   line and tool invocation is auto-tagged `agent='trading_bot'` +
   `run_id`.
3. The optimizer then queries the DB to *see everything* the trading
   agent did — including per-tool errors — and uses that to plan the
   next code / prompt / lesson change.

## What the optimizer can edit

| Kind | Where | How |
|---|---|---|
| Trading-bot source code (tools, strategy, agent loop) | `trading_agent/**.py` + `strategies/**.py` | `CodeEditor.write_file` — traced, syntax-checked, hot-reloaded |
| System prompt | `trading_agent_config.system_prompt` (DB row) | `save_config(...)` — validated by `validate_system_prompt` (must contain "guardrails"/"decision"/"reasoning", max 8000 chars) |
| Lessons | `trading_agent_memory` table | `db.add_trading_lesson(...)`; every new run pulls newest 15 into the LLM prompt |
| Risk / strategy params | `trading_agent_config.risk_params_json` / `strategy_params_json` | `save_config(...)` |
| Symbol universe | `trading_agent_config.symbols_json` | `save_config(...)` |

## Modes: backtest → paper → live

- Set in `trading_agent_config.mode` (single row).
- `backtest` — historical bars, in-memory paper broker.
- `paper` — live market data, in-memory paper broker (stubbed — flip on
  once your backtest results are consistently good).
- `live` — same interface, real broker adapter (not implemented yet).

The `TradingAgent` code path is identical across modes; only the broker
adapter differs, so nothing in the agent needs to change when you go
from `backtest` to `paper`.

## Tests

Two suites — both pass on this repo:

```powershell
py -3.12 tests\test_agent_db_migration.py       # 7 tests
py -3.12 tests\test_two_agent_architecture.py   # 7 tests
```

Coverage:
- Schema: agent+run_id columns and all 12 tables exist.
- `agent_scope` correctly stamps logs + tool traces.
- `TradingAgentConfig` and lessons round-trip through the DB.
- End-to-end backtest: run + decisions + trades + `trading_bot` logs +
  `market_data`/`indicators`/`broker` tool invocations all captured.
- `TradingBotTool` traces itself as `agent='optimizer'` while the run
  underneath traces as `agent='trading_bot'`.
- Hot-reload actually reimports `trading_agent.*` modules.
- `reset_trading_agent()` leaves optimizer state intact and vice-versa.

## Key file layout

```
autonomous_optimizer/                    # OPTIMIZER AGENT
  __main__.py                            # `python -m autonomous_optimizer`
  agent.py                               # main loop
  config.py                              # tunables + `use_trading_agent` flag
  code_editor.py                         # traced file writes
  backtest_runner.py                     # façade → trading_agent OR legacy subprocess
  git_ops.py                             # traced snapshot + revert
  llm/                                   # analyzer/strategist/coder/critic/…
  memory/                                # DB-backed working + long-term memory
  session_manager.py                     # DB-backed session state
  storage/
    agent_db.py                          # AgentDB — shared SQLite (all tables)
    db_log_handler.py                    # SQLiteLogHandler (agent+run_id aware)
    __init__.py                          # exports agent_scope, install_db_logging
  tools/
    trading_bot_tool.py                  # NEW — hot-reload + drive TradingAgent

trading_agent/                           # TRADING AGENT
  __init__.py                            # public API
  __main__.py                            # `python -m trading_agent`
  agent.py                               # per-bar orchestration
  runner.py                              # backtest / paper loop
  config.py                              # DB-loaded TradingAgentConfig
  memory.py                              # lessons + run-history view
  llm_advisor.py                         # per-signal LLM call (haiku by default)
  tools/
    base.py                              # ToolBase + @traced_action decorator
    market_data.py                       # cached-or-live OHLCV
    indicators.py                        # ATR, RSI, SMA snapshot
    strategy.py                          # candidate-setup detection (dumb baseline)
    risk.py                              # position sizing + portfolio guards
    broker.py                            # PaperBroker + BrokerTool

database/
  agent.db                               # THE ONE local store
  trades.db                              # pre-existing (used by dashboards / bot_runner)

tests/
  test_agent_db_migration.py             # original DB migration suite
  test_two_agent_architecture.py         # new two-agent suite
  _inspect_agent_db.py                   # quick DB dumper
```

## Important behaviour

- **Optimizer commits directly to `main`**. Every change is either
  `git commit`ed on success or `git reset --hard` reverted on failure.
- **Tracked files survive reverts; untracked ones do NOT.** If you add
  helper files, `git add` them or they'll be wiped by the next revert.
- **All agent-owned state lives in `database/agent.db`** — reset it via
  `AgentDB.reset_all()` / `reset_optimizer()` / `reset_trading_agent()`.
- **No log files are ever written**. Query `runtime_logs` instead.
- **The trading-agent LLM is called `per-signal`, not per-bar**, so a
  50-day backtest costs a handful of LLM calls, not thousands.
- **`AICORE_*` env vars missing?** The `LLMAdvisor` falls back to a
  deterministic rule-based decision so tests / CI still work.