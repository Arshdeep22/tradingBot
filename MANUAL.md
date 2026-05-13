# Trading Bot — Complete User Manual

---

## What This Bot Does

This is a **paper trading bot** for Indian stocks (Nifty 50). It:
- Automatically scans Nifty 50 stocks for trade setups every 5 minutes during market hours
- Monitors open trades and closes them when Stop Loss or Target is hit
- Runs on GitHub Actions — no need to keep your laptop on
- Tracks all trades in a database and shows analytics on a dashboard

**Paper trading means no real money is used.** Everything is simulated, so you can test strategies safely before going live.

---

## Table of Contents

1. [First-Time Setup](#1-first-time-setup)
2. [The Dashboard — Page by Page](#2-the-dashboard--page-by-page)
3. [Strategies — How They Work](#3-strategies--how-they-work)
4. [Backtesting — Test Before You Trade](#4-backtesting--test-before-you-trade)
5. [Running the Bot Live](#5-running-the-bot-live)
6. [Evaluating Performance](#6-evaluating-performance)
7. [Risk Management](#7-risk-management)
8. [Configuration Reference](#8-configuration-reference)
9. [Adding a New Strategy](#9-adding-a-new-strategy)
10. [Glossary](#10-glossary)

---

## 1. First-Time Setup

### Requirements
- Python 3.10+
- A GitHub account (for the auto-runner)
- SAP AI Core access (optional — only needed for AI strategy optimization)

### Install & Run

```bash
# 1. Clone and enter the project
cd tradingBot

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the dashboard
streamlit run dashboard/app.py
```

Open **http://localhost:8501** in your browser.

---

## 2. The Dashboard — Page by Page

The dashboard has 4 pages accessible from the left sidebar.

---

### 🏠 Home (app.py)

The first screen you see. Shows:

| Card | What it means |
|------|--------------|
| **Capital** | Your starting paper money (₹1,00,000) |
| **Total Trades** | All trades ever recorded |
| **Win Rate** | % of closed trades that hit target |
| **Total P&L** | Sum of all profits and losses |
| **Open Positions** | Trades currently active |

The open positions table at the bottom shows every trade currently running, including entry price, stop loss, and target.

**No action needed here** — it's a summary view only.

---

### 🎯 Zone Scanner (Page 1)

This is where you manually find trade setups and optionally enter them.

**How to use:**
1. Pick a symbol from the dropdown (default 5 symbols, or switch to Nifty 50 for all 50)
2. Adjust **Min Score** (higher = fewer but better quality zones)
3. Adjust **R:R Ratio** (e.g. 3.0 means target is 3× your risk)
4. Click **Scan Zones**
5. Review the zones shown — each zone has a chart, score, and reasoning
6. Click **Take Trade** on a zone to record it as a pending order

**What the score means:**

| Score | Quality |
|-------|---------|
| 90–100 | Excellent — strong zone, high confidence |
| 80–89 | Good — use these |
| 70–79 | Marginal — skip unless other factors align |
| < 70 | Weak — avoid |

**Zone types:**
- **DEMAND zone** (green) → potential BUY. Price dropped sharply from this level, so buyers are likely to defend it again.
- **SUPPLY zone** (red) → potential SELL. Price rose sharply from this level, so sellers are likely to re-emerge.

**What "multi-timeframe" means:** The scanner checks the 15m chart for zones, then the 5m chart to confirm the trend is in your favour. A DEMAND zone is skipped if the 5m trend is bearish.

---

### 📋 Trade History (Page 2)

Shows every trade you've ever taken. Use the filters at the top to narrow down by status, symbol, or strategy.

**Trade statuses:**
- **PENDING** — order placed, waiting for price to reach entry
- **OPEN** — entry triggered, trade is live
- **CLOSED (Target)** — trade won, price hit the target
- **CLOSED (SL)** — trade lost, price hit the stop loss
- **EXPIRED** — pending order that was never triggered and aged out (3 days)

**The chart** on each trade card shows the price action with entry, SL, and target lines so you can see exactly what happened.

**Delete button** removes a trade record from the database.

---

### 📈 Performance (Page 3)

Your full analytics page. Check this to understand whether your strategy is actually working.

**Key metrics explained:**

| Metric | What it means | Good value |
|--------|--------------|------------|
| **Total P&L** | Sum of all profits & losses in ₹ | Positive and growing |
| **Win Rate** | % of completed trades that hit target | > 50% for 1:2 RR, > 35% for 1:3 RR |
| **Profit Factor** | Total profit ÷ total loss | > 1.5 is good, > 2.0 is excellent |
| **Max Drawdown** | Largest peak-to-trough loss | < 10% of capital |
| **Sharpe Ratio** | Return adjusted for volatility | > 1.0 is acceptable, > 2.0 is great |
| **Sortino Ratio** | Like Sharpe but only penalises downside | > 1.5 is good |

**Equity curve** — the most important chart. A consistently rising curve means the strategy has edge. A flat or declining curve means something needs fixing.

---

### 🧪 Test Strategy (Page 4)

**This is the most important page.** Before trading any strategy live, backtest it here.

See [Section 4 — Backtesting](#4-backtesting--test-before-you-trade) for full instructions.

---

## 3. Strategies — How They Work

Three strategies are currently available. Choose the one that fits your style.

---

### Supply & Demand Zones (Default, Recommended)

**What it does:**
Finds price levels where the market previously moved sharply (a "zone"). These zones tend to act as future support or resistance because institutional buyers/sellers are present there.

**Entry logic:**
- DEMAND zone → wait for price to return to the zone → BUY
- SUPPLY zone → wait for price to return to the zone → SELL

**Zone scoring (0–100 points):**
- **Freshness (40 pts):** Has price returned to this zone before? Fresh zones (never tested) score higher. A zone becomes stale only if price *closes through* it — a wick that bounces is still valid.
- **Leg-out strength (30 pts):** How explosive was the move away from the zone? Big, fast candles score higher.
- **Base tightness (30 pts):** Were the candles inside the zone small and consolidated? Tight bases score higher.

**Stop loss:** 0.4% below the zone bottom (DEMAND) or above the zone top (SUPPLY).

**Best market conditions:** Trending or ranging markets with clear structure. Avoid during news events or pre-budget periods.

**Parameters to tune:**
- `min_score` (default 80) — lower to get more signals, raise to get fewer but better ones
- `rr_ratio` (default 3.0) — your target will be 3× your risk

---

### RSI Reversal

**What it does:**
Trades mean-reversion when RSI reaches extreme levels (oversold or overbought).

**Entry logic:**
- RSI ≤ 30 AND candle closes bullish → BUY
- RSI ≥ 70 AND candle closes bearish → SELL

**Stop loss:** 1× ATR(14) away from entry.

**Best market conditions:** Ranging, sideways markets. Performs poorly in strong trends (will keep firing "oversold" signals while price continues falling).

**Parameters to tune:**
- `rsi_period` (default 14) — shorter = more signals, noisier
- `oversold_level` (default 30) — lower to 25 for fewer but more extreme setups
- `overbought_level` (default 70) — raise to 75 for fewer but more extreme setups
- `rr_ratio` (default 2.0)

---

### EMA Crossover

**What it does:**
Buys when the fast EMA (9) crosses above the slow EMA (21), sells on the reverse.

**Entry logic:**
- EMA 9 crosses above EMA 21 → BUY
- EMA 9 crosses below EMA 21 → SELL

**Stop loss:** 1% below entry (fixed percentage).

**Best market conditions:** Trending markets. Suffers in choppy/sideways markets (many false crossovers).

**Parameters:** `fast_period`, `slow_period`

---

### Which strategy should I use?

| Your situation | Recommended strategy |
|---------------|---------------------|
| Learning the bot, want to understand zones | Supply & Demand Zones |
| Market is range-bound, no clear trend | RSI Reversal |
| Strong trending market | EMA Crossover |
| Want AI-assisted optimisation | Supply & Demand Zones (AI Refinement) |

**To change the strategy the live bot uses**, edit `config/settings.py`:
```python
ACTIVE_STRATEGY = "RSI Reversal"   # or "Supply & Demand Zones" or "EMA Crossover"
```

---

## 4. Backtesting — Test Before You Trade

Backtesting replays a strategy on historical data so you can see how it *would have* performed — before risking anything.

### Step-by-step

1. Go to **Test Strategy** (Page 4)
2. Select a **Strategy** from the dropdown
3. Pick a **Symbol** (e.g. RELIANCE.NS)
4. Set **Build Period** — how many days of history the strategy uses to find setups (e.g. 30 days)
5. Set **Test Period** — how many days forward to simulate (e.g. 14 days)
6. Adjust strategy parameters
7. Click **Run Backtest**

### Reading the results

**Summary cards:**
- **Setups Found** — how many trade opportunities the strategy identified
- **Triggered** — how many were actually entered (price reached entry)
- **Targets Hit / SL Hit** — breakdown of wins vs losses
- **Win Rate** — % of triggered trades that won
- **Total P&L** — simulated profit/loss in ₹

**The chart** shows price action with every entry, stop loss, and target plotted. Green markers = target hit, red markers = SL hit.

**The trade table** lists every simulated trade with entry, exit, and P&L.

### What makes a backtest result trustworthy?

| Question | What to look for |
|----------|-----------------|
| Enough trades? | At least 20–30 triggered trades for statistical significance |
| Win rate vs R:R? | At 1:3 RR, you need >25% win rate to be profitable. At 1:2, you need >34% |
| Consistent across symbols? | Run on 5+ symbols — don't cherry-pick the one that worked |
| Consistent across time periods? | Run on different date ranges — did it work last month AND last quarter? |

### AI Refinement (Supply & Demand Zones only)

When Supply & Demand Zones is selected, an **AI Refinement** section appears below the results. This uses an LLM (Claude) to automatically tune `min_score`, `rr_ratio`, and `build_days` across multiple iterations.

**How to use it:**
1. Run a baseline backtest first
2. Scroll down to AI Refinement
3. Set number of iterations (5–10 is usually enough)
4. Click **Run AI Refinement**
5. The AI will test different parameter combinations and show a comparison table
6. The best parameters are saved and automatically used by the live bot

**Important:** AI refinement is not magic. If a strategy has no edge on a symbol, the AI will not find one. Use it to *optimise* a working strategy, not to fix a broken one.

---

## 5. Running the Bot Live

The bot runs automatically via **GitHub Actions** every 5 minutes during NSE market hours (9:15 AM – 3:30 PM IST, Monday–Friday, excluding holidays).

### What the bot does each run

1. **Expire old orders** — cancels pending orders older than 3 days
2. **Check pending orders** — if price has reached entry, executes the trade
3. **Monitor open trades** — closes trades that hit SL or Target; moves SL to breakeven when 1:1 R is reached
4. **Daily loss check** — if today's losses exceed 1% of capital (₹1,000), halts new orders for the day
5. **Scan for new setups** — finds new zones/signals and creates pending orders

### Running manually

```bash
# Full cycle (check orders + monitor + scan for new zones)
python bot_runner.py

# Skip market hours check (useful for testing)
python bot_runner.py --force

# Only check & monitor existing trades (no new scanning)
python bot_runner.py --check-only

# Only scan for new zones (no monitoring)
python bot_runner.py --scan-only
```

### GitHub Actions setup

The bot auto-runs via `.github/workflows/trading_bot.yml`. Make sure:
1. The workflow file is committed to your repo
2. GitHub Actions is enabled on your repository (Settings → Actions → Allow all actions)
3. The workflow has write permissions to commit the database back to the repo

You can also trigger a manual run from the GitHub Actions tab → select the workflow → Run workflow.

---

## 6. Evaluating Performance

### The honest truth about evaluation

A strategy needs **at least 30–50 closed trades** before you can draw any conclusions. Don't judge by 5 trades.

### Weekly review checklist

Go to the **Performance page** and check:

- [ ] **Equity curve trending up?** If flat or down for 2+ weeks, something is wrong
- [ ] **Win rate above breakeven?** (see table below)
- [ ] **Profit factor > 1.5?** Below 1.0 means you're losing money overall
- [ ] **Max drawdown < 10%?** If larger, reduce position size or raise min_score
- [ ] **Any patterns in the losers?** Look at Trade History — do losses cluster in certain symbols, days of week, or market conditions?

### Breakeven win rate by R:R ratio

| R:R Ratio | Minimum win rate to break even |
|-----------|-------------------------------|
| 1:1 | 50% |
| 1:2 | 34% |
| 1:3 | 25% |
| 1:4 | 20% |

If your win rate is below the breakeven for your R:R ratio, you are losing money even if individual wins feel large.

### When to change strategy parameters

**Raise min_score** (e.g. 80 → 85) if:
- Win rate is low (< 40% on 1:2 RR)
- Many zones are triggered but quickly stopped out
- You have too many open positions and want fewer, better-quality setups

**Lower min_score** (e.g. 80 → 75) if:
- Very few zones are being found (< 2 per day across all symbols)
- Win rate is high but sample size is too small to be meaningful

**Raise rr_ratio** (e.g. 3.0 → 4.0) if:
- Win rate is consistently above 30% and you want larger wins
- You are comfortable with fewer wins in exchange for larger reward

**Lower rr_ratio** (e.g. 3.0 → 2.0) if:
- Targets are never being reached (price bounces back before hitting target)
- Win rate is very low — a closer target may be hit more often

### Red flags — stop trading and investigate

- 3 consecutive SL hits on the same symbol → that symbol may be in an unusual regime (news, earnings)
- Daily loss limit triggered 2+ days in a row → reduce position size in `config/settings.py` (`MAX_POSITION_SIZE`)
- Win rate drops below 25% over 20+ trades → run a new backtest on recent data to check if the strategy still works

---

## 7. Risk Management

The bot has several built-in risk controls. Here is what each one does and how to configure it.

### Position sizing

Each trade risks **1% of capital** (₹1,000 on ₹1,00,000). The quantity is calculated automatically:

```
Quantity = (Capital × 1%) / Risk per share
Risk per share = Entry price − Stop Loss price
```

So on a ₹500 stock with a ₹10 stop loss, quantity = ₹1,000 / ₹10 = 100 shares.

### Maximum open positions

Default: **5 positions simultaneously.** Set in `config/settings.py`:
```python
MAX_OPEN_POSITIONS = 5
```

### Daily loss circuit breaker

If total P&L for the day drops below **−1% of capital (−₹1,000)**, the bot stops creating new orders for the rest of that day. This prevents a bad day from becoming a catastrophic day.

Adjust in `config/settings.py`:
```python
MAX_DAILY_LOSS_PCT = 1.0   # 1% of capital
```

### Trailing stop to breakeven

Once a trade moves 1:1 in your favour (profit equals your initial risk), the stop loss automatically moves to the entry price. This means the trade can no longer lose money — worst case is breakeven.

### Order expiry

Pending orders that are never triggered expire after **3 days**. This prevents stale zone levels from being entered long after the market has moved on.

### What is NOT protected against

- **Gap openings:** If a stock gaps down through your stop loss on open, you may get a worse fill than the SL price (in live trading). Backtests assume perfect fills.
- **News events:** The bot does not read news. Earnings, RBI policy, or geopolitical events can cause large moves that stop you out even from high-quality zones.
- **Low liquidity:** Small-cap stocks may have wide spreads. Stick to Nifty 50 stocks for reliable fills.

---

## 8. Configuration Reference

All settings are in `config/settings.py`.

| Setting | Default | What it controls |
|---------|---------|-----------------|
| `INITIAL_CAPITAL` | 100000 | Starting paper capital in ₹ |
| `MAX_POSITION_SIZE` | 0.1 | Max 10% of capital per single trade |
| `MAX_OPEN_POSITIONS` | 5 | Max simultaneous trades |
| `MAX_DAILY_LOSS_PCT` | 1.0 | Daily loss halt threshold (% of capital) |
| `ACTIVE_STRATEGY` | "Supply & Demand Zones" | Which strategy the live bot uses |
| `SYMBOLS` | 5 Nifty stocks | Symbols the bot scans by default |
| `DEFAULT_TIMEFRAME` | "15m" | Candle interval for analysis |
| `LOOKBACK_PERIOD` | "5d" | How much history to fetch |

### Changing the symbols

Edit the `SYMBOLS` list to scan different stocks:
```python
SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
```

Add `.NS` suffix for NSE stocks. Always use Nifty 50 symbols for best data quality.

### Changing the active strategy

```python
ACTIVE_STRATEGY = "Supply & Demand Zones"   # default
ACTIVE_STRATEGY = "RSI Reversal"
ACTIVE_STRATEGY = "EMA Crossover"
```

---

## 9. Adding a New Strategy

Adding a new strategy takes two steps.

### Step 1 — Create the strategy file

Create `strategies/my_strategy.py`:

```python
from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
import pandas as pd
from typing import List

class MyStrategy(BaseStrategy):

    def __init__(self, timeframe: str = "15m"):
        super().__init__("My Strategy", timeframe)

    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        # Your logic here — return BUY, SELL, or HOLD
        return TradeSignal(Signal.HOLD, symbol, reason="No signal")

    def get_parameters(self) -> dict:
        return {"name": self.name, "timeframe": self.timeframe}
```

Optionally override `get_trade_setups()` if your strategy can find multiple setups per scan (like zone scanner does).

### Step 2 — Register it

Add one line to `strategies/__init__.py`:

```python
STRATEGY_REGISTRY = {
    "Supply & Demand Zones": ZoneScanner,
    "EMA Crossover": EMACrossoverStrategy,
    "RSI Reversal": RSIReversalStrategy,
    "My Strategy": MyStrategy,          # ← add this
}
```

That's it. Your strategy immediately appears in the Test Strategy dropdown and can be set as `ACTIVE_STRATEGY`.

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| **Zone** | A price level where the market previously moved sharply, likely to act as future support/resistance |
| **DEMAND zone** | A support level — buyers are expected to step in here |
| **SUPPLY zone** | A resistance level — sellers are expected to step in here |
| **Entry** | The price at which the trade is triggered |
| **Stop Loss (SL)** | If price reaches this level, the trade is closed at a loss to limit damage |
| **Target** | If price reaches this level, the trade is closed at a profit |
| **R:R ratio** | Reward-to-risk ratio — how much you aim to make vs how much you risk |
| **Win rate** | % of closed trades that hit target (not SL) |
| **Profit factor** | Total profit from winning trades ÷ total loss from losing trades |
| **Drawdown** | The % decline from a portfolio peak to a trough |
| **Sharpe ratio** | Return per unit of volatility — higher means more consistent returns |
| **Sortino ratio** | Like Sharpe but only counts downside volatility as "bad" |
| **ATR** | Average True Range — a measure of how much price moves per candle, used for SL sizing |
| **RSI** | Relative Strength Index — oscillator (0–100) measuring overbought/oversold conditions |
| **EMA** | Exponential Moving Average — a trend-following line that weights recent data more heavily |
| **Paper trading** | Simulated trading with no real money |
| **Backtest** | Running a strategy on historical data to see how it would have performed |
| **Slippage** | The difference between the expected fill price and the actual fill price |
| **Commission** | Brokerage fee per trade (simulated at 0.1% in backtests) |
| **Pending order** | An order waiting for price to reach the entry level |
| **Breakeven stop** | Moving stop loss to entry price after a trade moves 1:1 in profit |

---

*Last updated: May 2026*
