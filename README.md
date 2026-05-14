# 📈 Trading Bot — AI-Powered Paper Trading System

Automated paper trading bot for NSE Nifty 50 stocks. Runs fully on GitHub Actions — no laptop needed.

## What it does

- **Scans** all 50 Nifty stocks for Supply & Demand zone setups every 5 minutes during market hours
- **AI Recommendations** — at 11 AM IST, Claude Opus 4.6 ranks the top 10 setups and auto-places the top 5 as pending orders
- **Executes trades** automatically when price reaches the entry level
- **Monitors** open trades and closes them when Stop Loss or Target is hit
- **EOD Report** — generates a daily markdown report at market close showing which AI trades succeeded
- **Dashboard** — Streamlit web app for analytics, backtesting, and manual trading

## Architecture

```
tradingBot/
├── .github/workflows/
│   └── trading_bot.yml          # 3 scheduled jobs (bot / AI recs / EOD report)
├── config/
│   └── settings.py              # All configuration
├── core/
│   ├── ai_recommender.py        # Standalone AI scan + Claude API (no Streamlit)
│   ├── data_fetcher.py          # yfinance market data
│   ├── engine.py                # Trading engine loop
│   ├── llm_advisor.py           # SAP AI Core / Claude client + strategy memory
│   ├── broker_interface.py      # Abstract broker interface
│   └── paper_trader.py          # Paper trading simulator
├── strategies/
│   ├── zone_scanner.py          # Supply & Demand zone detection (primary)
│   ├── ema_crossover.py         # EMA crossover strategy
│   ├── rsi_reversal.py          # RSI reversal strategy
│   └── base_strategy.py        # Abstract base class
├── database/
│   ├── db.py                    # DatabaseManager facade
│   ├── trades.py                # Trade CRUD
│   ├── orders.py                # Pending order CRUD
│   ├── metrics.py               # Performance metrics
│   ├── base.py                  # SQLite + Supabase connection
│   └── trades.db                # Local SQLite (auto-committed by bot)
├── dashboard/
│   ├── app.py                   # Home page (KPIs + open positions)
│   └── pages/
│       ├── 1_🎯_Zone_Scanner.py          # Manual zone scan + Take Trade
│       ├── 2_📋_Trade_History.py         # Pending orders + executed trades
│       ├── 3_📈_Performance.py           # Equity curve + analytics
│       ├── 4_🧪_Test_Strategy.py         # Backtest + AI parameter refinement
│       └── 5_🤖_AI_Recommendations.py   # Claude-ranked top 10 setups
├── reports/                     # Daily AI recommendation + EOD report files
├── logs/                        # Bot execution logs
├── bot_runner.py                # 5-min job: check orders + monitor + scan
├── ai_trade_runner.py           # 11 AM job: AI scan + auto-place top 5 orders
├── report_generator.py          # EOD job: generate daily AI report
└── main.py                      # Local development entry point
```

## Quick Start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run dashboard/app.py   # http://localhost:8501
```

## GitHub Actions Schedule

| Time (IST) | Job | Script |
|---|---|---|
| Every 5 min (9:15 AM – 3:30 PM) | Monitor trades + execute orders | `bot_runner.py` |
| 11:00 AM | AI recommendations → top 5 pending orders | `ai_trade_runner.py` |
| 3:35 PM | EOD report | `report_generator.py` |

## Manual Triggers

Go to **GitHub → Actions → Trading Bot → Run workflow** and pick a mode:

| Mode | What it does |
|------|-------------|
| `full` | Normal bot cycle |
| `check-only` | Check + monitor only (no new zone scan) |
| `scan-only` | Zone scan only (no monitoring) |
| `force` | Full cycle, skip market hours check |
| `ai-recommendations` | Run AI recommender now (skips market hours check) |
| `eod-report` | Generate EOD report now |

## Local Commands

```bash
python bot_runner.py                    # Full cycle
python bot_runner.py --force            # Skip market hours check
python bot_runner.py --check-only
python bot_runner.py --scan-only

python ai_trade_runner.py               # AI scan (market hours only)
python ai_trade_runner.py --force       # AI scan (skip hours check)

python report_generator.py              # EOD report for today
python report_generator.py 2026-05-14  # EOD report for specific date
```

## Daily Output Files

```
reports/
  2026-05-15_recommendations.json    # Morning: AI top 10 + which 5 were placed
  2026-05-15_ai_report.md            # EOD: outcomes, win rate, P&L
```

## AI Model

Claude Opus 4.6 via SAP AI Core (`anthropic--claude-4.6-opus`).  
Configured in `.streamlit/secrets.toml` under `[aicore] model`.

## Disclaimer

Paper trading only. No real money is used. Past simulated performance does not guarantee future results.
