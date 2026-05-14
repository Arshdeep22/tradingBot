# Trading Bot — Functional Guide

> Features, usage, strategy improvement, and decision-making guide.
> For architecture, modules, and technical design, see [TECHNICAL.md](TECHNICAL.md).

---

## Table of Contents

1. [What This Bot Does](#1-what-this-bot-does)
2. [How the Bot Runs](#2-how-the-bot-runs)
3. [The Dashboard — Feature by Feature](#3-the-dashboard--feature-by-feature)
4. [Trading Strategies](#4-trading-strategies)
5. [AI Features](#5-ai-features)
6. [Risk Management](#6-risk-management)
7. [Evaluating Performance](#7-evaluating-performance)
8. [Improving Your Strategy](#8-improving-your-strategy)
9. [What You Can Change](#9-what-you-can-change)
10. [Glossary](#10-glossary)

---

## 1. What This Bot Does

This is a **paper trading bot** for Indian stocks listed on the NSE. It automatically finds trade setups, places orders, monitors them, and closes them — all without any manual action required during the trading day.

**Paper trading** means all money is simulated. No real funds are used or at risk. The purpose is to test whether a strategy actually produces consistent edge before committing real capital.

**What makes this bot different from a simple alert tool:**

- It does not just notify you — it acts. It places orders, moves stop losses, and closes trades on its own.
- It uses AI to rank trade setups by win probability each morning and suggest strategy improvements over time.
- Everything runs on GitHub's servers. Your laptop does not need to be on during market hours.
- All results are tracked and analysed automatically — equity curve, win rate, drawdown, and daily reports are generated without you doing anything.

---

## 2. How the Bot Runs

The bot has three automated processes that run on a schedule every trading day (Monday–Friday, excluding NSE holidays).

---

### Morning — AI Recommendations (11:00 AM IST)

At 11 AM, the bot scans all 50 Nifty stocks for trade setups. Every setup is scored and the best ones are sent to Claude AI, which ranks the top 10 by estimated win probability. The top 5 are automatically placed as pending orders. A JSON file is saved to the `reports/` folder recording all 10 recommendations with reasoning.

---

### Throughout the Day — Trade Management (Every 5 Minutes, 9:15 AM – 3:30 PM IST)

Every 5 minutes, the bot runs a full cycle:

1. **Expire stale orders** — pending orders older than 3 days are cancelled automatically
2. **Check pending orders** — if the market price has reached a pending order's entry level, the order is executed and becomes an open trade
3. **Monitor open trades** — if a trade's stop loss or target is hit, the trade is closed and the profit or loss is recorded
4. **Scan for new setups** — if there are available slots (fewer than 5 open positions), the bot scans its watchlist for new trade setups and creates new pending orders
5. **Daily loss protection** — if the day's total loss exceeds 1% of capital, no new orders are created for the rest of that day

---

### End of Day — Outcome Report (3:35 PM IST)

At 3:35 PM, after market close, the bot generates a markdown report comparing the morning's AI recommendations against what actually happened. It records which trades hit target, which hit their stop loss, and which are still open. This report is committed to the `reports/` folder automatically.

---

### What Runs Without Any Action From You

| Time | What Happens |
|------|-------------|
| 11:00 AM | AI scans 50 stocks, ranks top 10, places top 5 as pending orders |
| Every 5 min | Orders checked, trades monitored, new setups scanned |
| 3:35 PM | EOD report generated comparing predictions to outcomes |

You only need to act if you want to manually add or remove trades, adjust strategy settings, or review performance on the dashboard.

---

## 3. The Dashboard — Feature by Feature

The dashboard is a web application accessible via browser. It reads from and writes to the same database the bot uses.

---

### Home — Portfolio Summary

The home page shows five key numbers at a glance:

| Card | What it Means |
|------|--------------|
| Capital | Your starting paper balance (₹1,00,000) |
| Total Trades | Every trade ever recorded, open and closed |
| Win Rate | Percentage of closed trades that hit their target |
| Total P&L | Cumulative profit and loss across all closed trades |
| Open Positions | How many trades are currently live |

Below the KPI cards, a table shows all currently open trades with their entry price, stop loss, target, and current unrealised P&L.

**This page is read-only.** It is your at-a-glance health check.

---

### Zone Scanner — Find and Enter Trades Manually

This page lets you scan any stock for supply and demand zones and optionally enter a trade without waiting for the bot's automated cycle.

**How to use it:**

1. Select a symbol from the dropdown
2. Adjust the minimum score threshold (higher = fewer but better setups)
3. Adjust the reward-to-risk ratio (higher = more ambitious target)
4. Click Scan Zones
5. Review the results — each zone shows a chart, its score, the reasoning behind the score, and the entry, stop loss, and target levels
6. Click "Take Trade" on any zone you want to act on — this creates a pending order immediately

**Zone quality guide:**

| Score Range | Quality | Recommended Action |
|-------------|---------|-------------------|
| 90–100 | Excellent — high institutional interest | Take the trade |
| 80–89 | Good — solid setup | Take the trade |
| 70–79 | Marginal — some weakness in the zone | Skip unless the broader context is strongly in your favour |
| Below 70 | Weak — high failure probability | Avoid |

**DEMAND zones** (shown in green) are potential buy setups. The market previously moved sharply upward from this price level, suggesting strong buying interest. If price returns here, buyers are likely to defend it.

**SUPPLY zones** (shown in red) are potential sell setups. The market previously moved sharply downward from this price level, suggesting strong selling pressure. If price returns here, sellers are likely to re-emerge.

---

### Trade History — View All Trades

This page shows every trade ever recorded. Filters at the top let you narrow by status, symbol, or strategy.

**Trade statuses explained:**

| Status | Meaning |
|--------|---------|
| PENDING | Order placed, waiting for price to reach the entry level |
| OPEN | Entry triggered, trade is currently live |
| CLOSED (Target) | Trade won — price reached the target |
| CLOSED (SL) | Trade lost — price hit the stop loss |
| EXPIRED | Pending order that was never triggered and aged out after 3 days |
| CANCELLED | Manually cancelled before execution |

Each trade card shows a price chart with entry, stop loss, and target levels plotted so you can see exactly what happened to the trade in the context of the price action.

A **Delete** button on each trade removes it from the database permanently. Use this only to clean up test entries or errors.

---

### Performance — Analytics and Equity Curve

This is where you measure whether the strategy is actually working.

**The equity curve** is the most important chart on this page. It plots your cumulative P&L over time. A consistently rising curve means the strategy has real edge. A flat or falling curve means something needs to change.

**Key metrics on this page:**

| Metric | What It Measures | Healthy Range |
|--------|-----------------|---------------|
| Total P&L | Sum of all closed trade profits and losses | Positive and growing |
| Win Rate | Percentage of closed trades that hit target | Depends on R:R ratio — see below |
| Profit Factor | Total winnings ÷ total losses | Above 1.5 is good; above 2.0 is excellent |
| Max Drawdown | Largest peak-to-trough loss in the equity curve | Below 10% of capital |
| Sharpe Ratio | Return per unit of volatility | Above 1.0 is acceptable; above 2.0 is strong |
| Sortino Ratio | Like Sharpe but only penalises downside volatility | Above 1.5 is good |

**Win rate breakeven by reward-to-risk ratio:**

| R:R Ratio | Minimum Win Rate to Be Profitable |
|-----------|----------------------------------|
| 1:1 | 50% |
| 1:2 | 34% |
| 1:3 | 25% |
| 1:4 | 20% |

If your win rate is below the breakeven threshold for your R:R ratio, the strategy is losing money even when individual wins feel meaningful.

---

### Test Strategy — Backtesting and AI Refinement

This is the most important page for strategy development. Before running any strategy live, test it here on historical data.

**How to run a backtest:**

1. Select a strategy from the dropdown
2. Pick a symbol
3. Set the build period — how many days of history the strategy uses to identify zones (30 days is a reasonable starting point)
4. Set the test period — how many days forward to simulate (14 days is typical)
5. Adjust strategy parameters using the sliders
6. Click Run Backtest

**Reading the backtest results:**

| Result Card | What It Shows |
|-------------|--------------|
| Setups Found | How many trade opportunities were detected in the build period |
| Triggered | How many were actually entered (price reached entry) |
| Targets Hit | How many went on to hit the profit target |
| SL Hit | How many were stopped out at a loss |
| Win Rate | Targets hit ÷ triggered × 100 |
| Total P&L | Sum of all simulated trade results |

The chart shows every setup plotted on the price action with green markers for target hits and red markers for SL hits.

**What makes a backtest result trustworthy:**

| Question | What to Look For |
|----------|-----------------|
| Sample size large enough? | At least 20–30 triggered trades — fewer than this is statistically meaningless |
| Win rate vs R:R? | Must exceed the breakeven threshold for your ratio |
| Consistent across symbols? | Run on at least 5 different stocks — do not cherry-pick the one that worked |
| Consistent across time? | Run on multiple date ranges — did it work last month AND last quarter? |

**AI Refinement** (Supply & Demand Zones only): After running a baseline backtest, you can run the AI refinement loop. Claude analyses your results and suggests different parameter combinations to test. It runs multiple iterations automatically, comparing results, and saves the best parameters found. The live bot uses these improved parameters on its next run.

---

### AI Recommendations — Morning Trade Ranking

This page shows the output of the morning AI scan. Every trading day at 11 AM, Claude analyses the best zone setups found across the full Nifty 50 and returns a ranked list of the top 10.

**What you see for each recommendation:**

| Field | Meaning |
|-------|---------|
| Rank | Claude's ranking (1 = highest conviction) |
| Symbol | The stock |
| Side | BUY or SELL |
| Entry / SL / Target | The zone's key levels |
| Zone Score | The algorithmic quality score (0–100) |
| Win Probability | Claude's estimated probability of success |
| Conviction | HIGH, MEDIUM, or LOW |
| Reasoning | Why Claude ranked this setup |
| Risks | What could cause this trade to fail |

The top 5 recommendations are placed as pending orders automatically. Ranks 6–10 are shown for reference but not acted on unless you manually take them via the Zone Scanner.

You can also see historical recommendation pages — select a past date to review what Claude recommended and how those trades performed.

---

## 4. Trading Strategies

Three strategies are available. The bot runs one strategy at a time for its automated cycle. All three can be backtested independently.

---

### Supply & Demand Zones — Default, Primary Strategy

**What it does:**
Identifies price levels where the market previously moved sharply away (a "zone"). These levels represent areas where institutional buyers or sellers were active. When price returns to the zone, those participants are likely to act again — creating a high-probability trade opportunity.

**When it works best:**
Markets with clear price structure — either trending with visible pullback levels or ranging with obvious support and resistance. Works across all Nifty 50 stocks because institutional order flow is consistently present in large-cap names.

**When to be cautious:**
During news-driven sessions (RBI policy, earnings, Union Budget), price can move through zones without respecting them. Consider pausing the bot or reducing position size around these events.

**Parameters you can adjust:**

| Parameter | What It Does | Default |
|-----------|-------------|---------|
| min_score | Minimum quality threshold for a zone to generate a trade | 80 |
| rr_ratio | How many times your risk you aim to make on each trade | 3.0 |

**This is the strategy used by the AI Recommendations feature.** Claude ranks setups from this strategy only.

---

### RSI Reversal — Mean-Reversion Strategy

**What it does:**
Trades the premise that extreme moves tend to reverse. When the RSI indicator falls to or below 30 (deeply oversold), the strategy looks to buy expecting a bounce back toward the mean. When RSI rises to or above 70 (overbought), it looks to sell expecting a pullback.

**When it works best:**
Range-bound, sideways markets where price oscillates between support and resistance without a clear directional trend.

**When to avoid it:**
Strong trending markets. In a downtrend, a stock can stay oversold for days while continuing to fall. The RSI reversal strategy will generate repeated losing buy signals in this environment.

**Parameters you can adjust:**

| Parameter | What It Does | Default |
|-----------|-------------|---------|
| rsi_period | How many candles to calculate RSI over — shorter = more sensitive | 14 |
| oversold_level | RSI threshold for buy signals — lower = rarer but more extreme | 30 |
| overbought_level | RSI threshold for sell signals — higher = rarer but more extreme | 70 |
| rr_ratio | Reward-to-risk ratio | 2.0 |

---

### EMA Crossover — Trend-Following Strategy

**What it does:**
Buys when the fast moving average (9-period EMA) crosses above the slow moving average (21-period EMA), signalling a shift to bullish momentum. Sells when the fast EMA crosses back below.

**When it works best:**
Strong, directional markets. When price is trending clearly in one direction, crossover signals are reliable and early.

**When to avoid it:**
Choppy, sideways markets. When price oscillates without direction, the EMAs will cross back and forth repeatedly, generating a string of small losses from false signals.

**Parameters you can adjust:**

| Parameter | What It Does | Default |
|-----------|-------------|---------|
| fast_period | Period for the faster EMA — shorter = more reactive | 9 |
| slow_period | Period for the slower EMA — longer = smoother | 21 |

---

### Which Strategy Should You Use?

| Situation | Best Choice |
|-----------|-------------|
| Want to use AI recommendations and the AI optimisation features | Supply & Demand Zones |
| Market is range-bound, no clear trend | RSI Reversal |
| Market is in a strong directional trend | EMA Crossover |
| Want the most battle-tested option with the most tuning tools | Supply & Demand Zones |

---

## 5. AI Features

The bot integrates Claude Opus 4.6 via SAP AI Core for two distinct purposes.

---

### AI Morning Recommendations

Every trading day at 11 AM, Claude receives the top zone setups found across all 50 Nifty stocks. It evaluates each one and returns:

- A **ranking** of the top 10 setups
- An estimated **win probability** (percentage) for each
- A **conviction level** (HIGH, MEDIUM, LOW)
- **Reasoning** explaining the ranking
- **Identified risks** for each setup
- **Entry timing advice** — whether to enter at open, wait for confirmation, etc.
- A **market context summary** describing the overall conditions that day

The top 5 ranked setups are automatically placed as pending orders tagged "AI Recommendations". The bot then monitors them through the normal 5-minute cycle.

**What Claude is good at here:**
- Weighting zone quality against current market context
- Identifying setups that look good mechanically but carry elevated risk (e.g. earnings upcoming)
- Ranking when multiple similarly-scored zones are available

**What Claude cannot do:**
- Access real-time news or corporate filings
- Know about intraday events that happen after 11 AM
- Override a bad zone — if the zone score is genuinely weak, the AI ranking will reflect that

**Fallback:** If AI Core credentials are missing or the API call fails, setups are ranked by zone score alone and the top 5 are still placed as orders. The system does not halt.

---

### AI Strategy Refinement (Backtester)

When you run a backtest on Supply & Demand Zones and enable AI Refinement, Claude is given the backtest statistics and asked to suggest improved parameters. It then runs multiple iterations:

1. You set a baseline — run a backtest with default parameters
2. Claude analyses the results and suggests a new parameter combination to test
3. The backtest runs again with the new parameters
4. Claude compares the results and either converges on better parameters or explores a new direction
5. After the set number of iterations, the best performing combination is saved

**The saved parameters are used by the live bot automatically** — it reads the saved optimisation result on its next run.

**Important caveats about AI refinement:**
- It optimises for the data provided. If the test period is short or the sample size is small, the "best" parameters may just be overfitted to noise
- Always validate the AI-refined parameters by backtesting on a completely different symbol and time period before trusting them live
- AI refinement cannot create edge where none exists — it can only find the best version of a working strategy

---

## 6. Risk Management

The bot has five built-in risk controls that are always active.

---

### Position Sizing — 1% Risk Per Trade

Every trade is sized so that a stop loss hit costs exactly 1% of capital (₹1,000 on ₹1,00,000). The position size is calculated automatically from the distance between entry and stop loss. A trade with a wide stop loss gets a smaller position; a trade with a tight stop loss gets a larger position.

This means:
- No single loss can devastate the account
- Position sizes are consistent regardless of the stock's price
- You do not need to manually decide how many shares to buy

---

### Maximum Open Positions — 5 Simultaneous Trades

The bot will not open more than 5 trades at the same time. When 5 positions are open, no new pending orders are created regardless of how many good setups are found. This prevents over-exposure to market moves that affect many stocks simultaneously.

---

### Daily Loss Circuit Breaker — 1% Daily Limit

If the day's total realised losses exceed 1% of capital (₹1,000), the bot stops creating new orders for the rest of that trading day. Existing open trades continue to be monitored and closed normally — only new order creation is halted. This prevents a bad morning from compounding into a much larger daily loss.

---

### Breakeven Stop — Protect Profitable Trades

Once a trade moves 1:1 in your favour (unrealised profit equals the initial risk), the stop loss is automatically moved to the entry price. The trade cannot lose money from that point — the worst outcome is breakeven. This locks in progress while allowing the trade to continue toward its full target.

---

### Order Expiry — Prevent Stale Entries

Pending orders that are never triggered expire automatically after 3 days. A zone that was identified 3 days ago may no longer be relevant — the market structure may have changed. Auto-expiry ensures the bot is not entering trades based on outdated analysis.

---

### What Risk Controls Cannot Protect Against

| Scenario | Why It Is Not Covered |
|----------|----------------------|
| Gap openings | If a stock gaps through the stop loss overnight, the exit may occur at a worse price than the SL level |
| News events | Earnings releases, RBI decisions, and geopolitical events can cause moves that bypass zone logic |
| Low liquidity | Very thin stocks may have wide bid-ask spreads; yfinance data may be delayed |
| Extended bear markets | If the entire Nifty falls for weeks, demand zones will be violated across all 50 stocks |

---

## 7. Evaluating Performance

A strategy needs at least **30–50 closed trades** before you can draw any conclusions from the results. Do not judge based on a week of activity.

---

### Weekly Review Checklist

Visit the Performance page weekly and work through these questions:

- Is the equity curve trending upward? A flat or declining curve for two or more weeks is a signal to investigate.
- Is the win rate above the breakeven threshold for your R:R ratio?
- Is the profit factor above 1.5? Below 1.0 means you are losing money overall.
- Is the maximum drawdown below 10% of capital? If it has exceeded 10%, reduce position risk or increase the minimum zone score.
- Are there patterns in the losing trades? Look at Trade History — do losses cluster in specific stocks, specific days of the week, or specific market conditions?

---

### Reading the Equity Curve

The equity curve is your most honest performance indicator. Here is how to interpret different shapes:

| Curve Shape | What It Means |
|-------------|--------------|
| Steady upward slope | Strategy has consistent edge — continue |
| Steep then flat | Early luck followed by mean reversion — evaluate carefully |
| Staircase (up then flat, repeat) | Normal for zone strategies — wins come in clusters |
| Steadily declining | Strategy has no edge in the current market regime — investigate |
| Volatile with large swings | Position sizing may be too aggressive |

---

### Red Flags — Stop and Investigate

| Signal | What to Do |
|--------|-----------|
| 3 consecutive SL hits on the same symbol | Check for news or earnings on that stock |
| Daily loss limit triggered 2+ consecutive days | Reduce position size or raise minimum zone score |
| Win rate falls below 25% over 20+ trades | Run a new backtest on recent data to check if the strategy still works |
| No pending orders are being created | Check that the bot ran; verify market hours and holiday calendar |
| Equity curve falls more than 10% from peak | Reduce to 0.5% risk per trade until the cause is identified |

---

## 8. Improving Your Strategy

The primary lever for improving performance is adjusting the Supply & Demand Zone parameters. Here is how to think through each adjustment.

---

### The Two Core Parameters

**Minimum Score (`min_score`)**
Controls the quality gate for zone setups. A higher threshold produces fewer but more selective trades. A lower threshold produces more trades but accepts lower-quality zones.

**Reward-to-Risk Ratio (`rr_ratio`)**
Controls how far your target is set relative to your stop loss. A ratio of 3.0 means the target is 3 times further away than the stop loss. Higher ratios mean larger wins when trades work but fewer trades that reach their target.

---

### When to Raise Minimum Score

Consider raising the minimum score when:

- Win rate is below 40% on a 1:2 R:R ratio
- Many trades are entered but quickly stopped out (entering at low-quality zones)
- You have too many open positions simultaneously and want fewer, higher-quality setups
- The equity curve is declining despite normal trade frequency

Typical adjustment: move from 80 to 85. Test the new threshold on the backtest page before applying it live.

---

### When to Lower Minimum Score

Consider lowering the minimum score when:

- The bot is finding fewer than 2 setups per day across all watched symbols
- Win rate is high but sample size is too small to be statistically meaningful
- You want to see more of the available opportunity set

Typical adjustment: move from 80 to 75. Be aware that this will increase trade frequency and reduce average quality.

---

### When to Raise the R:R Ratio

Consider raising the R:R ratio when:

- Win rate is consistently above 35% and you want to capture more upside per trade
- The equity curve is profitable but grows slowly
- Analysis of closed trades shows price frequently continues past the current target

Typical adjustment: move from 3.0 to 3.5 or 4.0.

---

### When to Lower the R:R Ratio

Consider lowering the R:R ratio when:

- Targets are rarely being reached — price bounces from the zone but reverses before the full target
- Win rate is very low — a closer target would be hit more frequently
- Backtest results show a large number of open/pending trades that never resolved

Typical adjustment: move from 3.0 to 2.5 or 2.0.

---

### Using the AI Refinement Loop Effectively

The AI refinement feature on the Test Strategy page automates parameter search. To use it well:

1. **Start with a baseline.** Run a backtest with default parameters (min_score=80, rr_ratio=3.0) and make sure you have at least 15–20 triggered trades. If you have fewer, extend the build period.

2. **Run 5–8 iterations.** More iterations give Claude more data to work with, but the marginal benefit diminishes after around 10. Eight is a good stopping point.

3. **Look at the iteration table.** The AI will show you all tested parameter combinations and their results. Do not just take the "best" result blindly — look for combinations that improve on multiple metrics simultaneously (win rate AND profit factor AND trade count).

4. **Validate on a different symbol.** After saving the refined parameters, run a backtest on a completely different stock to verify the improvement is real and not overfitted.

5. **Apply gradually.** Change one parameter at a time in live trading. If both min_score and rr_ratio were changed, start by applying just one and observe the results for a week.

---

### Symbol Selection and Watchlist Management

The default watchlist covers 5 Nifty stocks. The AI recommendations engine scans all 50 Nifty stocks independently.

**For the live bot's automated watchlist**, focus on stocks with these characteristics:
- High daily volume (reduces gap risk and ensures reliable yfinance data)
- Clear price structure (trending or ranging, not random noise)
- No upcoming catalysts (earnings, AGMs, index rebalancing events)

**Adding more symbols to the live watchlist** increases the number of potential setups per day but also increases the number of simultaneous open positions. Ensure `MAX_OPEN_POSITIONS` is set appropriately before expanding the watchlist.

---

### Timeframe Considerations

The bot currently operates on the 15-minute timeframe for zone detection with 5-minute confirmation. This is appropriate for intraday trading in Nifty 50 stocks.

**Shorter timeframes (5m, 3m):**
- More signals, but more noise and more false breakouts
- Zones are smaller and more frequent — requires tighter stop losses
- Higher transaction frequency increases execution risk in live trading

**Longer timeframes (1h, daily):**
- Fewer but higher-quality zones with larger risk-reward potential
- Require multi-day holding periods — not suitable for the current 3-day expiry model
- Would require significant changes to the order management logic

---

## 9. What You Can Change

Most changes are made in `config/settings.py`. After editing this file and pushing to GitHub, the changes take effect on the next bot run.

---

### Changes You Can Make Without Code

| What to Change | Where to Change It | When to Change It |
|----------------|-------------------|------------------|
| Active strategy | `config/settings.py` → `ACTIVE_STRATEGY` | When you want the live bot to use a different strategy |
| Live watchlist | `config/settings.py` → `SYMBOLS` | When you want to add or remove symbols from the live scan |
| Starting capital | `config/settings.py` → `INITIAL_CAPITAL` | When you reset the paper trading account |
| Maximum open positions | `config/settings.py` → `MAX_OPEN_POSITIONS` | When you want to allow more or fewer simultaneous trades |
| Daily loss limit | `config/settings.py` → `MAX_DAILY_LOSS_PCT` | When you want more or less protection against bad days |
| Zone score threshold | Dashboard → Zone Scanner → Min Score slider | For one-off manual scans only |
| R:R ratio | Dashboard → Zone Scanner → R:R Ratio slider | For one-off manual scans only |
| Zone score threshold (live bot) | `config/settings.py` or via AI refinement save | For permanent changes to the automated cycle |

---

### Changes That Require Adding a New Strategy File

If you want to trade a different strategy beyond the three built in:

1. Create a new strategy in the `strategies/` folder following the existing pattern
2. Add it to the `STRATEGY_REGISTRY` in `strategies/__init__.py`
3. Set `ACTIVE_STRATEGY` in settings to use it live

No other changes are required — the new strategy will immediately appear in all dashboard dropdowns and can be backtested.

---

### Changes That Require Modifying Existing Code

| Change | Module to Edit |
|--------|---------------|
| Change how zones are scored | `strategies/zone_scanner.py` |
| Change order expiry duration (currently 3 days) | `database/orders.py` |
| Change the breakeven stop logic (currently 1:1) | `bot_runner.py` |
| Change how position size is calculated | `bot_runner.py` + `paper_trader.py` |
| Change the number of AI recommendations placed (currently top 5) | `ai_trade_runner.py` |
| Change what Claude is asked to evaluate | `core/ai_recommender.py` + `core/llm_advisor.py` |
| Add a new dashboard page | Create a new file in `dashboard/pages/` |

---

### Changes That Should Not Be Made Without Full Testing

| Change | Risk |
|--------|------|
| Removing the daily loss circuit breaker | A single bad day could wipe a significant portion of simulated capital |
| Setting `MAX_OPEN_POSITIONS` above 10 | Correlated losses across many positions simultaneously |
| Setting risk per trade above 2% | Individual losses become large enough to materially impact the curve |
| Switching to live Zerodha trading | Real money — requires full end-to-end testing in paper mode first |

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| Zone | A price level where the market previously moved sharply, likely to act as future support or resistance |
| Demand Zone | A support level — buyers are expected to defend this price when revisited |
| Supply Zone | A resistance level — sellers are expected to re-emerge at this price |
| Entry | The price level at which a trade is triggered |
| Stop Loss (SL) | The price at which the trade is automatically closed to limit losses |
| Target | The price at which the trade is automatically closed to take profit |
| Pending Order | An order waiting for price to reach the entry level before executing |
| Open Trade | A trade that has been entered and is currently live |
| Closed Trade | A trade that has been exited — either at target (win) or stop loss (loss) |
| Expired Order | A pending order that was never triggered and was automatically cancelled after 3 days |
| R:R Ratio | Reward-to-risk ratio — how much you aim to gain relative to what you risk |
| Win Rate | Percentage of closed trades that hit the target rather than the stop loss |
| Profit Factor | Total gross profit divided by total gross loss — above 1.0 means net positive |
| Drawdown | The percentage decline from a portfolio's peak value to a subsequent trough |
| Sharpe Ratio | Return divided by volatility — measures consistency of returns |
| Sortino Ratio | Like Sharpe but only penalises downside volatility |
| Equity Curve | A chart of cumulative P&L over time — the primary indicator of strategy health |
| Paper Trading | Simulated trading with no real money — identical logic to live trading |
| Backtest | Running a strategy on historical data to estimate how it would have performed |
| Build Period | The historical window used to detect zones in a backtest |
| Test Period | The forward window used to simulate trade outcomes in a backtest |
| Breakeven Stop | Moving the stop loss to the entry price after the trade moves 1:1 in profit |
| Circuit Breaker | The daily loss limit — when hit, halts new order creation for the day |
| ATR | Average True Range — a measure of average candle size, used for stop loss sizing in RSI Reversal |
| RSI | Relative Strength Index — an oscillator (0–100) measuring momentum; below 30 is oversold, above 70 is overbought |
| EMA | Exponential Moving Average — a trend line that gives more weight to recent price data |
| Nifty 50 | The 50 largest companies on the National Stock Exchange of India by market capitalisation |
| NSE | National Stock Exchange — the primary Indian stock exchange |
| IST | Indian Standard Time — UTC+5:30 |
| Conviction | Claude's qualitative confidence in a recommendation: HIGH, MEDIUM, or LOW |
| Win Probability | Claude's estimated likelihood (as a percentage) that a setup will reach its target |
| Zone Score | The algorithmic quality rating (0–100) based on freshness, leg-out strength, and base tightness |

---

*Last updated: May 2026*
