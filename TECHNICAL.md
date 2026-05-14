# Trading Bot — Technical Reference

> Architecture, modules, database, workflows, and system design.
> For feature descriptions and usage guidance, see [FUNCTIONAL.md](FUNCTIONAL.md).

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Structure](#2-repository-structure)
3. [Module Reference](#3-module-reference)
4. [Architecture & Component Interactions](#4-architecture--component-interactions)
5. [Database Design](#5-database-design)
6. [Execution Workflows](#6-execution-workflows)
7. [External Integrations](#7-external-integrations)
8. [Configuration Reference](#8-configuration-reference)
9. [GitHub Actions Automation](#9-github-actions-automation)
10. [Data Models](#10-data-models)

---

## 1. System Overview

This is a **fully automated, AI-enhanced paper trading system** for Nifty 50 stocks listed on NSE (India). The system operates entirely on GitHub Actions — no server or local machine needs to run continuously.

**Core capabilities:**
- Automated trade lifecycle management (pending → open → closed)
- Supply and demand zone detection with a 0–100 scoring engine
- Claude AI integration for ranking setups and optimising strategy parameters
- Dual database backend (SQLite local + Supabase cloud)
- Streamlit web dashboard for analysis and manual interaction
- End-of-day automated reporting

**Runtime environment:**
- Python 3.11
- GitHub Actions (Ubuntu runners)
- Streamlit Cloud (dashboard hosting)
- Market coverage: NSE, Mon–Fri, 9:15 AM – 3:30 PM IST

---

## 2. Repository Structure

```
tradingBot/
│
├── main.py                    # Local dev entry point — runs continuous trading loop
├── bot_runner.py              # GH Actions: every-5-min trade management cycle
├── ai_trade_runner.py         # GH Actions: 11 AM AI recommendation engine
├── report_generator.py        # GH Actions: 3:35 PM EOD outcome report
├── simulate_trades.py         # Simulation / testing utility
├── requirements.txt           # Python package dependencies
│
├── config/
│   └── settings.py            # All system-wide configuration constants
│
├── core/
│   ├── engine.py              # Main trading loop orchestrator
│   ├── data_fetcher.py        # Market data aggregation layer
│   ├── broker_interface.py    # Abstract broker interface + Order/Position models
│   ├── paper_trader.py        # Paper trading simulator
│   ├── ai_recommender.py      # Standalone AI scanning engine (no UI dependency)
│   ├── llm_advisor.py         # SAP AI Core client + iterative parameter optimiser
│   └── backtester.py          # Historical simulation engine
│
├── strategies/
│   ├── base_strategy.py       # Abstract base class + Signal/TradeSignal/TradeSetup types
│   ├── zone_scanner.py        # Supply & demand zone detection and scoring
│   ├── ema_crossover.py       # EMA 9/21 crossover strategy
│   ├── rsi_reversal.py        # RSI mean-reversion at extremes
│   └── __init__.py            # STRATEGY_REGISTRY — maps display names to classes
│
├── database/
│   ├── base.py                # Connection management (SQLite + Supabase detection)
│   ├── trades.py              # TradesMixin — CRUD for trades table
│   ├── orders.py              # OrdersMixin — CRUD for pending_orders table
│   ├── metrics.py             # MetricsMixin — performance calculations
│   ├── db.py                  # DatabaseManager facade combining all mixins
│   └── trades.db              # SQLite database file (committed to repo)
│
├── dashboard/
│   ├── app.py                 # Streamlit home page — KPIs + open positions
│   └── pages/
│       ├── 1_🎯_Zone_Scanner.py        # Manual zone scan + trade entry UI
│       ├── 2_📋_Trade_History.py       # All trades with filters + delete
│       ├── 3_📈_Performance.py         # Analytics, equity curve, metrics
│       ├── 4_🧪_Test_Strategy.py       # Backtester UI + AI refinement loop
│       └── 5_🤖_AI_Recommendations.py  # Claude top-10 + win probabilities
│
├── .github/
│   └── workflows/
│       └── trading_bot.yml    # Three scheduled GitHub Actions jobs
│
├── reports/
│   ├── YYYY-MM-DD_recommendations.json  # Morning AI top-10 output
│   └── YYYY-MM-DD_ai_report.md          # EOD outcome report (auto-committed)
│
├── logs/
│   ├── bot_runner.log
│   ├── ai_trade_runner.log
│   └── report_generator.log
│
├── strategies_docs/           # Strategy explanation documents
├── .streamlit/
│   └── secrets.toml           # Local credentials (not committed)
├── MANUAL.md                  # Documentation index
├── TECHNICAL.md               # This document
└── FUNCTIONAL.md              # User-facing feature guide
```

---

## 3. Module Reference

### `config/settings.py`
Single source of truth for all runtime constants. Every other module imports from here. Controls capital, symbols, risk limits, market hours, NSE holiday calendar, timeframes, strategy selection, and broker selection.

---

### `core/engine.py` — Trading Engine
The orchestrator for local execution via `main.py`. Initialises all components (data fetcher, strategy, paper trader, database), then runs a continuous loop calling: fetch data → generate signal → execute trade → monitor positions.

**Dependencies:** DataFetcher, PaperTrader, DatabaseManager, active strategy class

---

### `core/data_fetcher.py` — Market Data Layer
Abstracts all data retrieval. Supports yfinance as the primary source with a placeholder for Zerodha live feeds. Enforces a staleness check — if the last data point is more than 20 minutes old, the price is considered invalid.

**Key methods:**
- `get_data(symbol, timeframe, period)` — returns OHLCV DataFrame
- `get_current_price(symbol)` — returns latest close with staleness check
- `is_market_hours()` — checks IST time, weekday, and NSE holiday list

---

### `core/broker_interface.py` — Broker Abstraction
Defines `Order` and `Position` data classes and the abstract `BrokerInterface`. All broker-specific logic is isolated behind this interface, allowing paper and live (Zerodha) trading to share the same calling code.

---

### `core/paper_trader.py` — Paper Trading Simulator
Implements the broker interface with simulated execution. Fills orders immediately at the given price, tracks position P&L in memory, enforces the maximum open positions limit, and applies the 1% risk sizing formula.

---

### `core/ai_recommender.py` — Standalone AI Engine
Scans the full Nifty 50 list for zone setups (without any Streamlit dependency), builds a JSON payload of the top candidates, sends it to Claude via SAP AI Core, and returns a ranked list with win probabilities and conviction levels. Used by `ai_trade_runner.py`.

**Fallback:** If AI Core credentials are missing or the API call fails, zones are ranked by their score alone.

---

### `core/llm_advisor.py` — Parameter Optimiser
Wraps the SAP AI Core OAuth2 client. Exposes `iterate(backtest_results, parameters)` which sends current backtest statistics to Claude and receives suggested parameter adjustments. Persists the iteration history and best parameters to `.streamlit/strategy_memory.json` so the live bot uses them on subsequent runs.

---

### `core/backtester.py` — Historical Simulation
Splits historical OHLCV data into a "build" period (zone detection) and a "test" period (forward simulation). Replays each detected setup candle-by-candle to determine whether entry, target, or stop loss was triggered first. Returns a `BacktestReport` with per-trade results and aggregate statistics.

---

### `strategies/base_strategy.py` — Strategy Interface
Defines the contract all strategies must implement:
- `generate_signal(data, symbol) → TradeSignal` — single BUY/SELL/HOLD signal
- `get_trade_setups(data, symbol) → List[TradeSetup]` — multiple ranked setups

Also defines the `Signal` enum, `TradeSignal`, and `TradeSetup` dataclasses.

---

### `strategies/zone_scanner.py` — Zone Detector
The primary strategy. Scans OHLCV data to detect supply and demand zones using a three-component scoring model:

| Component | Max Points | Criterion |
|-----------|-----------|-----------|
| Freshness | 40 | Has the zone been tested before? Never-tested scores highest. |
| Leg-out strength | 30 | How explosive was the move away? Large, fast candles score highest. |
| Base tightness | 30 | How consolidated was the base? Fewer, smaller candles score highest. |

A zone must score at least 80/100 to produce a trade setup by default. Entry is placed at the zone edge, stop loss 0.4% beyond the zone, and target is calculated from the `rr_ratio` parameter.

---

### `strategies/ema_crossover.py`
Generates a BUY signal when EMA(9) crosses above EMA(21) and a SELL when the cross reverses. Stop loss is a fixed 1% from entry. Best suited to trending markets.

---

### `strategies/rsi_reversal.py`
Generates a BUY when RSI ≤ 30 and the candle closes bullish, and a SELL when RSI ≥ 70 and the candle closes bearish. Stop loss is 1× ATR(14). Best suited to ranging markets.

---

### `database/` — Data Persistence Layer

| File | Responsibility |
|------|---------------|
| `base.py` | Detects whether to use SQLite or Supabase; creates tables on first run |
| `trades.py` | CRUD for the `trades` table |
| `orders.py` | CRUD for the `pending_orders` table; handles expiry logic |
| `metrics.py` | Calculates win rate, profit factor, drawdown, Sharpe, Sortino from trade history |
| `db.py` | `DatabaseManager` class — single facade combining all three mixins |

The database auto-selects its backend:
1. Check for Supabase credentials in `.streamlit/secrets.toml`
2. Check for `SUPABASE_URL` / `SUPABASE_KEY` environment variables
3. Fall back to SQLite (`database/trades.db`)

---

### `dashboard/` — Streamlit UI Layer

| Page | Path | Purpose |
|------|------|---------|
| Home | `app.py` | KPI cards + open positions table |
| Zone Scanner | `pages/1_🎯_Zone_Scanner.py` | Manual scan UI, chart, "Take Trade" |
| Trade History | `pages/2_📋_Trade_History.py` | All trades, filter, delete |
| Performance | `pages/3_📈_Performance.py` | Equity curve + metric cards |
| Test Strategy | `pages/4_🧪_Test_Strategy.py` | Backtest UI + AI refinement |
| AI Recommendations | `pages/5_🤖_AI_Recommendations.py` | Morning Claude rankings |

---

## 4. Architecture & Component Interactions

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GITHUB ACTIONS                               │
│                                                                      │
│  ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────┐  │
│  │  Every 5 minutes │  │  11:00 AM IST     │  │  3:35 PM IST     │  │
│  │  bot_runner.py   │  │  ai_trade_runner  │  │  report_generator│  │
│  └────────┬─────────┘  └────────┬──────────┘  └────────┬─────────┘  │
└───────────┼─────────────────────┼────────────────────────┼───────────┘
            │                     │                         │
            ▼                     ▼                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          CORE LAYER                                  │
│                                                                      │
│  DataFetcher          ZoneScanner            AIRecommender          │
│  (yfinance)           (zone detection        (Nifty 50 scan +       │
│  OHLCV data           + scoring)             Claude ranking)        │
│       │                    │                        │                │
│       └────────────────────┴────────────────────────┘               │
│                              │                                       │
│                         TradingEngine                                │
│                   (orchestrates the cycle)                           │
│                              │                                       │
│               ┌──────────────┴──────────────┐                       │
│               ▼                             ▼                       │
│        PaperTrader                   DatabaseManager                │
│      (order execution,              (trades, orders,                │
│       position tracking)             metrics, snapshots)            │
└─────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         STORAGE LAYER                                │
│                                                                      │
│  ┌───────────────────────┐      ┌────────────────────────────────┐  │
│  │  SQLite (trades.db)   │  OR  │  Supabase (cloud PostgreSQL)   │  │
│  │  Local / GitHub repo  │      │  Streamlit Cloud deployment    │  │
│  └───────────────────────┘      └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        DASHBOARD LAYER                               │
│                  (Streamlit — read + write)                          │
│                                                                      │
│   Home  │  Zone Scanner  │  Trade History  │  Performance           │
│   Test Strategy  │  AI Recommendations                              │
└─────────────────────────────────────────────────────────────────────┘
```

**Key data flows:**

**Live trading cycle (every 5 min):**
`bot_runner` → `DataFetcher` (prices) → check pending orders → execute if triggered → monitor open trades → close on SL/target hit → scan for new zones → save new pending orders → commit `trades.db` to repo

**AI recommendation cycle (11 AM):**
`ai_trade_runner` → `ZoneScanner` (all 50 stocks) → `AIRecommender` (Claude ranking) → place top 5 as pending orders → save JSON report → commit to repo

**EOD report cycle (3:35 PM):**
`report_generator` → load morning JSON → query DB for AI trades → compute outcomes → write markdown report → commit to repo

**Backtest + AI refinement cycle (manual):**
User selects params → `Backtester.run()` → `ZoneScanner` (build period) → forward simulate (test period) → show results → `LLMAdvisor.iterate()` → Claude suggests next params → repeat N times → save best params to `strategy_memory.json`

---

## 5. Database Design

The system uses three tables. The backend is either SQLite (`database/trades.db`) or Supabase, selected automatically at runtime.

---

### `trades` Table

Stores all completed and active trade records.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK) | Auto-increment identifier |
| symbol | TEXT | e.g. `RELIANCE.NS` |
| side | TEXT | `BUY` or `SELL` |
| quantity | INTEGER | Number of shares |
| entry_price | REAL | Price at which trade was entered |
| exit_price | REAL | Price at close; NULL if still open |
| stop_loss | REAL | Stop loss level |
| target | REAL | Profit target level |
| pnl | REAL | Realised profit/loss in ₹ |
| pnl_percent | REAL | P&L as % of position value |
| strategy | TEXT | Strategy name that generated the signal |
| reason | TEXT | Human-readable signal description and exit reason |
| status | TEXT | `OPEN` or `CLOSED` |
| entry_time | TIMESTAMP | When the trade was entered |
| exit_time | TIMESTAMP | When the trade was closed; NULL if open |
| created_at | TIMESTAMP | Row creation time |

---

### `pending_orders` Table

Stores trade setups that are waiting for the market to reach the entry price.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK) | Auto-increment identifier |
| symbol | TEXT | Target instrument |
| side | TEXT | `BUY` or `SELL` |
| quantity | INTEGER | Calculated position size |
| entry_price | REAL | Limit price at which to enter |
| stop_loss | REAL | SL once entered |
| target | REAL | Target once entered |
| strategy | TEXT | Source strategy name |
| reason | TEXT | Zone or signal description |
| status | TEXT | `PENDING`, `EXECUTED`, `EXPIRED`, or `CANCELLED` |
| created_at | TIMESTAMP | When order was created |
| expires_at | TIMESTAMP | Auto-expire after 3 days |
| executed_at | TIMESTAMP | When price was triggered; NULL until then |

---

### `portfolio_snapshots` Table

Periodic snapshots of portfolio state. Written on each bot run for equity curve construction.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK) | Auto-increment identifier |
| timestamp | TIMESTAMP | Snapshot time |
| balance | REAL | Available cash |
| portfolio_value | REAL | Cash + unrealised position value |
| open_positions | INTEGER | Count of open trades |
| total_pnl | REAL | Cumulative realised P&L |

---

### Lifecycle State Machine

```
pending_orders:   PENDING ──► EXECUTED ──► (record moves to trades table)
                      │
                      ├──► EXPIRED   (age > 3 days, price never reached)
                      └──► CANCELLED (manually cancelled)

trades:           OPEN ──► CLOSED    (target hit or SL hit)
```

---

### Performance Metrics (computed, not stored)

The `metrics.py` mixin computes these on demand from the `trades` table:

| Metric | Calculation |
|--------|-------------|
| Win rate | `winning_trades / total_closed_trades × 100` |
| Profit factor | `sum(winning PnLs) / abs(sum(losing PnLs))` |
| Max drawdown | Largest peak-to-trough drop in cumulative P&L series |
| Sharpe ratio | `(mean daily return / std daily return) × √252` |
| Sortino ratio | Same as Sharpe but std uses only negative returns |
| Daily P&L | Sum of `pnl` for trades closed on the current IST date (circuit breaker input) |

---

## 6. Execution Workflows

### A. Live Trading Cycle — `bot_runner.py` (Every 5 min)

```
1. is_market_hours()?
   ├─ No  → expire old orders → exit
   └─ Yes → continue

2. expire_old_orders(max_age_days=3)
   → Mark PENDING orders older than 3 days as EXPIRED

3. check_pending_orders()     [skipped with --scan-only]
   → For each PENDING order:
     - Fetch current price
     - BUY: if current_price ≤ entry_price → execute
     - SELL: if current_price ≥ entry_price → execute
     - On execute: create OPEN trade, mark order EXECUTED

4. monitor_open_trades()      [skipped with --scan-only]
   → For each OPEN trade:
     - Fetch current price
     - BUY trade:
       * price ≤ stop_loss  → close, reason = "STOP LOSS HIT"
       * price ≥ target     → close, reason = "TARGET HIT"
       * price ≥ entry + risk → move SL to entry (breakeven)
     - SELL trade: reverse comparisons
     - Record exit_price, pnl, exit_time, status = CLOSED

5. daily_loss_circuit_breaker()
   → Sum pnl of today's closed trades
   → If total ≤ -(capital × MAX_DAILY_LOSS_PCT / 100) → halt, return

6. auto_scan_zones()          [skipped with --check-only]
   → slots = MAX_OPEN_POSITIONS - (open + pending count)
   → For each symbol not already active:
     - Fetch 5d of 15min data
     - strategy.get_trade_setups() → scored zone list
     - If best zone score ≥ min_score:
       * quantity = (capital × 1%) / (entry - stop_loss)
       * save_pending_order()

7. Git commit trades.db + reports/ → push
```

---

### B. AI Recommendation Cycle — `ai_trade_runner.py` (11 AM IST)

```
1. is_market_hours()? → skip if not

2. scan_nifty50_zones(min_score=75)
   → Fetch 10d of 15min data for each of 50 stocks
   → Run zone_scanner.get_trade_setups() on each
   → Collect all setups scoring ≥ 75
   → Sort by score descending → take top ~20 candidates

3. get_ai_recommendations(candidates)
   → Build JSON payload: symbol, side, entry, SL, target, rr_ratio, score, reasoning
   → POST to Claude Opus 4.6 via SAP AI Core
   → Claude returns:
     { market_context, recommendations: [{ rank, win_probability, conviction,
       reasoning[], risks, entry_advice }] }
   → Fallback: sort by zone score if AI unavailable

4. place_orders(top_5_recommendations)
   → For each: calculate quantity, save_pending_order()
   → strategy tag = "AI Recommendations"

5. Save reports/YYYY-MM-DD_recommendations.json
   → Contains: total_setups_found, market_context, top10, orders_placed

6. Git commit + push
```

---

### C. EOD Report Cycle — `report_generator.py` (3:35 PM IST)

```
1. Load reports/YYYY-MM-DD_recommendations.json

2. Query DB:
   - Trades WHERE strategy = 'AI Recommendations' AND date = today
   - Pending orders WHERE strategy = 'AI Recommendations' AND date = today

3. For each recommended setup: determine outcome
   - TARGET HIT  → win
   - STOP LOSS   → loss
   - Still OPEN  → ongoing
   - Still PENDING → never triggered

4. Build markdown report table:
   | Rank | Symbol | Side | Entry | SL | Target | Prob | Conviction | Outcome | PnL |

5. Calculate daily AI stats: win rate, total P&L, triggered count

6. Save reports/YYYY-MM-DD_ai_report.md

7. Git commit + push
```

---

### D. Backtest + AI Refinement — `backtester.py` + `llm_advisor.py`

```
User inputs → symbol, strategy, build_days, test_days, parameters

1. Backtester.run():
   - Fetch (build_days + test_days) of 15min data
   - Split: building_data | testing_data
   - strategy.get_trade_setups(building_data) → list of setups
   - For each setup, replay through testing_data candle-by-candle:
     * Did price reach entry? → entered
     * If entered: did SL hit before target? → outcome
   - Return BacktestReport (statistics + per-trade results)

2. If AI Refinement enabled (N iterations):
   - LLMAdvisor.iterate(current_results, current_params)
   - Claude analyses win rate, profit factor, zone count, avg RR
   - Claude returns suggested parameter adjustments
   - Run backtest again with new params
   - Compare all iterations → select best
   - Save best params to strategy_memory.json
   - Live bot reads strategy_memory.json on next run
```

---

## 7. External Integrations

### yfinance — Market Data

| Attribute | Detail |
|-----------|--------|
| Purpose | OHLCV price data for all Nifty 50 symbols |
| Authentication | None (public API) |
| Symbols | NSE format: `RELIANCE.NS`, `TCS.NS`, etc. |
| Supported timeframes | 3m, 5m, 15m |
| Staleness threshold | 20 minutes — older data triggers a warning |
| Failure mode | DataFetcher logs an error; that symbol is skipped for the cycle |

---

### Supabase — Cloud Database

| Attribute | Detail |
|-----------|--------|
| Purpose | Cloud-hosted PostgreSQL; mirrors the SQLite schema |
| Authentication | API URL + service role key |
| Credential sources | `.streamlit/secrets.toml` → env vars (`SUPABASE_URL`, `SUPABASE_KEY`) |
| When used | Automatically when credentials are present; otherwise SQLite |
| Use case | Streamlit Cloud deployment (cannot write to local files) |

---

### SAP AI Core — Claude Opus 4.6

| Attribute | Detail |
|-----------|--------|
| Purpose | Trade ranking (AI Recommendations) and parameter optimisation (backtester) |
| Model | `anthropic--claude-4.6-opus` |
| Authentication | OAuth2 client credentials (4 env vars) |
| Credential sources | `.streamlit/secrets.toml` → GitHub Secrets |
| Required env vars | `AICORE_AUTH_URL`, `AICORE_API_URL`, `AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET` |
| Token handling | Auto-refresh by `AICoreLLM._get_token()` |
| Failure mode | Falls back to zone score ranking; logs warning |

---

### Zerodha — Live Broker (Future)

The broker interface is fully defined but not yet connected. When `BROKER = "zerodha"` is set in `settings.py`, the system will route orders through Zerodha's Kite API. The data fetcher also has a Zerodha data path for real-time tick data. Currently no implementation exists behind these placeholders.

---

## 8. Configuration Reference

All settings live in `config/settings.py`. Changes take effect on the next GitHub Actions run after a `git push`.

### Capital & Risk

| Setting | Default | Effect |
|---------|---------|--------|
| `INITIAL_CAPITAL` | 100000 | Paper trading starting balance in ₹ |
| `MAX_POSITION_SIZE` | 0.1 | Maximum 10% of capital in a single trade |
| `MAX_OPEN_POSITIONS` | 5 | Maximum concurrent open trades |
| `MAX_DAILY_LOSS_PCT` | 1.0 | Daily P&L floor — halts new orders when breached |
| `STOP_LOSS_PERCENT` | 1.0 | Default SL for non-zone strategies |
| `TARGET_PERCENT` | 2.0 | Default target for non-zone strategies |
| `TRAILING_STOP` | False | Enable breakeven stop movement |

### Symbols & Data

| Setting | Default | Effect |
|---------|---------|--------|
| `SYMBOLS` | 5 Nifty stocks | Live bot watchlist |
| `NIFTY_50` | 50 symbols | AI scan watchlist (ai_trade_runner) |
| `DEFAULT_TIMEFRAME` | `"15m"` | Candle interval for zone detection |
| `SUPPORTED_TIMEFRAMES` | `["3m", "5m", "15m"]` | Allowed in dashboard dropdowns |
| `LOOKBACK_PERIOD` | `"5d"` | History window for live scans |
| `DATA_SOURCE` | `"yfinance"` | Market data provider |

### Strategy & Broker

| Setting | Default | Effect |
|---------|---------|--------|
| `ACTIVE_STRATEGY` | `"Supply & Demand Zones"` | Strategy used by `bot_runner.py` |
| `EMA_FAST_PERIOD` | 9 | EMA crossover fast period |
| `EMA_SLOW_PERIOD` | 21 | EMA crossover slow period |
| `BROKER` | `"paper"` | `"paper"` or `"zerodha"` |

### Market Hours

| Setting | Default | Effect |
|---------|---------|--------|
| `MARKET_OPEN_HOUR` | 9 | IST open hour |
| `MARKET_OPEN_MINUTE` | 15 | IST open minute |
| `MARKET_CLOSE_HOUR` | 15 | IST close hour |
| `MARKET_CLOSE_MINUTE` | 30 | IST close minute |
| `NSE_HOLIDAYS_2026` | Full calendar | Dates when bot skips all activity |
| `CHECK_INTERVAL` | 60 | Polling interval in seconds (local mode) |

---

## 9. GitHub Actions Automation

The workflow file `.github/workflows/trading_bot.yml` defines three jobs.

### Job 1 — `run-bot` (Every 5 minutes during market hours)

**Schedule:** UTC cron `*/5 3-10 * * 1-5` (maps to 8:30 AM – 4:29 PM IST, Mon–Fri)

**Execution steps:**
1. Checkout repository
2. Set up Python 3.11 with pip cache
3. Install requirements
4. Restore `trades.db` from GitHub Actions cache
5. Run `bot_runner.py` with selected mode
6. Save updated `trades.db` to cache
7. `git add` → `git commit` → `git push` (if changes exist)
8. Upload `bot_runner.log` as artifact (7-day retention)

**Manual trigger modes:**
- `full` — complete cycle (default)
- `check-only` — monitor existing trades, no new scanning
- `scan-only` — scan for new setups, no trade monitoring
- `force` — bypass market hours check

---

### Job 2 — `ai-recommendations` (11:00 AM IST)

**Schedule:** UTC cron `30 5 * * 1-5` (5:30 AM UTC = 11:00 AM IST)

**Execution steps:**
1. Checkout + Python + pip
2. Restore `trades.db` from cache
3. Run `ai_trade_runner.py` (with `--force` if triggered manually)
4. Inject all `SUPABASE_*` and `AICORE_*` secrets as environment variables
5. Save `trades.db` + `reports/` + `logs/`
6. `git commit` + `git push`
7. Upload `ai_trade_runner.log` artifact (7-day retention)

---

### Job 3 — `eod-report` (3:35 PM IST)

**Schedule:** UTC cron `5 10 * * 1-5` (10:05 AM UTC = 3:35 PM IST)

**Execution steps:**
1. Checkout + Python + pip
2. Restore `trades.db` from cache
3. Run `report_generator.py`
4. Inject `SUPABASE_*` secrets
5. Save `reports/` + `logs/`
6. `git commit` + `git push`
7. Upload report artifacts (30-day retention)

---

### Database Persistence Across Runs

GitHub Actions runners are ephemeral — files do not persist between jobs. `trades.db` is preserved using the GitHub Actions cache with a key tied to `github.run_id`. The flow is:

```
Previous run → Save trades.db to cache
Current run  → Restore trades.db from cache → Execute → Save updated trades.db → Git push
```

The `git push` step also creates a permanent copy of `trades.db` in the repository, so data is never lost even if the cache is evicted.

---

### Required Repository Secrets

| Secret | Used By |
|--------|---------|
| `SUPABASE_URL` | Jobs 1, 2, 3 |
| `SUPABASE_KEY` | Jobs 1, 2, 3 |
| `AICORE_AUTH_URL` | Job 2 |
| `AICORE_API_URL` | Job 2 |
| `AICORE_CLIENT_ID` | Job 2 |
| `AICORE_CLIENT_SECRET` | Job 2 |
| `AICORE_RESOURCE_GROUP` | Job 2 |
| `GITHUB_TOKEN` | All (auto-provided) |

---

## 10. Data Models

### Signal (Enum)
`BUY` | `SELL` | `HOLD`

---

### TradeSignal
Single directional signal returned by `generate_signal()`.

| Field | Type | Description |
|-------|------|-------------|
| signal | Signal | BUY / SELL / HOLD |
| symbol | str | Instrument identifier |
| price | float | Current market price |
| stop_loss | float | Suggested SL level |
| target | float | Suggested target level |
| reason | str | Human-readable description |

---

### TradeSetup
One ranked opportunity returned by `get_trade_setups()`. Multiple may exist per symbol.

| Field | Type | Description |
|-------|------|-------------|
| symbol | str | Instrument identifier |
| side | str | `"BUY"` or `"SELL"` |
| entry | float | Entry price level |
| stop_loss | float | Stop loss level |
| target | float | Profit target level |
| score | int | Confidence score 0–100 |
| reasoning | str | Why this setup was identified |

---

### Zone (Zone Scanner internal)
Detailed representation of a detected supply or demand zone.

| Field | Type | Description |
|-------|------|-------------|
| zone_type | str | `"DEMAND"` or `"SUPPLY"` |
| zone_top | float | Upper boundary of zone |
| zone_bottom | float | Lower boundary of zone |
| score | int | Composite 0–100 score |
| freshness_score | int | 0–40 (never tested = 40) |
| legout_score | int | 0–30 (explosive move = 30) |
| base_score | int | 0–30 (tight base = 30) |
| is_fresh | bool | True if zone has not been revisited |
| leg_out_pct | float | % move away from zone |
| base_candles | int | Number of candles in the base |
| entry | float | Calculated entry price |
| stop_loss | float | Calculated SL price |
| target | float | Calculated target price |
| reasoning | str | Scoring narrative |

---

### Order (Broker Interface)

| Field | Type | Description |
|-------|------|-------------|
| order_id | str | Unique identifier |
| symbol | str | Instrument |
| order_type | str | `"MARKET"` or `"LIMIT"` |
| side | str | `"BUY"` or `"SELL"` |
| quantity | int | Number of shares |
| price | float | Limit price |
| stop_loss | float | SL associated with this order |
| target | float | Target associated with this order |
| status | str | `PENDING` / `EXECUTED` / `REJECTED` / `CANCELLED` |

---

### Position (Broker Interface)

| Field | Type | Description |
|-------|------|-------------|
| symbol | str | Instrument |
| side | str | `"BUY"` or `"SELL"` |
| quantity | int | Position size |
| entry_price | float | Average entry price |
| current_price | float | Latest market price |
| stop_loss | float | Current SL level |
| target | float | Current target level |
| pnl | float | Unrealised P&L in ₹ |
| pnl_percent | float | Unrealised P&L as % |

---

### BacktestReport

| Field | Type | Description |
|-------|------|-------------|
| symbol | str | Tested instrument |
| building_start / end | str | Date range for zone detection |
| testing_start / end | str | Date range for forward simulation |
| total_zones_found | int | Zones detected in build period |
| zones_triggered | int | Zones where price reached entry |
| targets_hit | int | Trades that hit target |
| sl_hit | int | Trades that hit SL |
| pending | int | Trades never triggered |
| win_rate | float | `targets_hit / zones_triggered × 100` |
| total_pnl | float | Sum of all simulated trade PnLs |
| avg_rr_achieved | float | Average actual reward:risk ratio |
| max_win / max_loss | float | Largest individual trade outcome |
| trade_results | list | Per-trade detail records |

---

### IterationResult (LLM Advisor)

One cycle in the AI parameter refinement loop.

| Field | Type | Description |
|-------|------|-------------|
| iteration | int | Iteration number |
| parameters | dict | Parameters tested in this round |
| win_rate | float | Backtest win rate |
| total_pnl | float | Backtest P&L |
| zones_found | int | Total zones detected |
| zones_triggered | int | Zones that triggered entry |
| avg_rr | float | Average RR achieved |
| llm_analysis | str | Claude's narrative analysis |
| llm_suggestions | dict | Next parameter values suggested by Claude |

---

*Last updated: May 2026*
