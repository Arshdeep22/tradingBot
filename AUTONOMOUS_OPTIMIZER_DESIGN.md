# Autonomous Trading Bot Optimizer Agent - Design Document

**Created**: 2026-05-20
**Status**: Ready for Implementation
**Goal**: Achieve 70% or higher win rate on last 50 days of historical data (3 consecutive runs)

---

## 1. Problem Statement

The current trading bot has severe performance issues:
- Only 6-8 trades generated over 59 trading days - far too few for any statistical reliability
- Win rate: 25-37% - well below the 70% target
- Strategy oscillates between being too restrictive (0 trades for weeks) and too loose (generating losing trades)
- Parameters never converge - optimizer cycles between tightening after losses and loosening after dry spells
- Structural limitations: Scans zones only until 11 AM, max 2 trades/day, fixed entry/exit logic

The core issue is not just parameter tuning - it is structural trading logic that needs rethinking.

---

## 2. Solution: Autonomous Self-Improving Agent

An autonomous agent that runs continuously, modifying the trading bot code, testing changes, and iterating until 70% win rate is achieved. No human approval required.

### Success Criteria

The agent STOPS when:
- Last 3 backtest runs on the most recent 50 trading days ALL show 70% or higher win rate
- AND total trades in each run are at least 10 (statistical minimum)

---

## 3. Architecture

The agent uses a session-based architecture:

- SESSION MANAGER (Context Brain): Maintains full history of what was tried, tracks which approaches failed/succeeded, decides what to try next (avoids repetition), manages sub-sessions for dedicated tasks

- Sub-sessions:
  - STRATEGY SESSION: Modify trading logic
  - INFRA SESSION: Modify trainer, simulator
  - TEST SESSION: Run tests and fix breaks
  - EVALUATE SESSION: Run backtest, analyze

- SCOPE: ALL FILES ARE MODIFIABLE
  - strategies/* (zone detection, scoring, filters, entry/exit)
  - historical_trainer/* (simulation, constants, grid, runner)
  - core/* (trade simulator, backtester, data fetcher)
  - config/* (settings, symbols, timeframes)
  - nightly_optimizer.py (optimization logic)
  - ai_trade_runner.py (live execution logic)
  - tests/* (test cases, validation)

- SUCCESS: 3 consecutive backtest runs with 70%+ WR on last 50 days

---

## 4. Agent Loop (Main Cycle)

Each iteration follows this pattern:

1. OBSERVE - Run backtest
   - Get win rate, trade count, P&L
   - Identify which trades failed/why

2. ANALYZE - Failure analysis
   - Categorize loss patterns
   - Identify structural bottlenecks
   - Compare with history of attempts

3. STRATEGIZE - Plan improvements
   - Claude proposes code changes
   - Avoids approaches already tried
   - Can modify ANY file in the repo

4. IMPLEMENT - Apply code changes
   - Modify strategy, simulator, etc.
   - Multiple files can change at once

5. TEST - Verify nothing broke
   - Run unit tests
   - If tests fail then auto-revert

6. VALIDATE - Run backtest again
   - Compare new WR vs previous
   - If improved then commit and push
   - If worse then revert and log failure

7. CHECK SUCCESS - 3 runs at 70%?
   - Yes then STOP (goal achieved!)
   - No then Go to step 1

---

## 5. Session and Context Management

### Why Sessions?

LLMs have limited context windows. The agent needs to manage information across potentially hundreds of iterations. Solution: dedicated sub-sessions with focused context.

### Session Types

- Analysis Session: Analyze backtest results, identify root causes. Context: Backtest results + trade logs + current params
- Strategy Session: Design a new approach/modification. Context: Analysis output + trading domain knowledge + what was already tried
- Code Session: Implement the code changes. Context: Strategy plan + target files content + coding guidelines
- Test Session: Run tests, fix any breaks. Context: Changed files + test output + error messages
- Evaluate Session: Run backtest, compare results. Context: New code state + backtest results + history of results

### Persistent State (autonomous_optimizer/context/session_state.json)

The state tracks:
- iteration number
- current phase
- best win rate achieved
- best trade count
- consecutive 70% runs count
- all approaches tried (with results, files changed, whether reverted)
- current hypothesis
- blocked approaches (things that definitely dont work)
- insights learned so far

This state persists across agent restarts, ensuring no work is ever lost.

---

## 6. Full Modification Scope

The agent is NOT limited to tuning parameters. It can modify any aspect of the trading system:

### Trading Logic (What/When/How to Trade)
- Scan window: Currently 11 AM cutoff. Can make continuous, multi-session, adaptive
- Holding period: Currently 75 bars. Can add trailing stops, partial exits, time-based exits
- Entry logic: Currently zone midpoint. Can try edge, confirmation, limit vs market
- Exit logic: Currently fixed SL/Target. Can add trailing, partial profit booking, breakeven
- Trade count: Currently max 2/day. Can increase based on quality/regime
- Symbol selection: Currently top 10/20 Nifty. Can add sector rotation, momentum filters

### Scoring/Detection (Which Zones to Trade)
- Scoring dimensions: Weights, thresholds, new dimensions
- Zone detection: Base candles, body ratio, volume requirements
- Filters: Width, distance, freshness decay, overlap rules
- Regime detection: Thresholds, new regime types, regime-specific rules

### Infrastructure (How We Measure Success)
- Simulation logic: Slippage, commission, entry detection
- Backtester: How results are calculated
- Training loop: Walk-forward vs expanding window, optimizer frequency
- Win rate calculation: How expired trades are counted

### Files In Scope

strategies/ - Zone detection, scoring, filters, entry/exit
- zone_scanner.py, zone_filters.py, zone_scoring.py, zone_models.py, zone_risk.py
- zone_detection/*.py, zone_mtf/*.py, zone_scoring/*.py, zone_trade_levels/*.py
- market_conditions.py, stock_selector.py, base_strategy.py

historical_trainer/ - Training/simulation infrastructure
- simulation.py, constants.py, grid_search.py, runner.py
- time_utils.py, llm_calls.py, reporting.py, data_loader.py

core/ - Core execution engine
- trade_simulator.py, backtester.py, backtester_models.py
- data_fetcher.py, market_regime.py, engine.py

config/ - Configuration
- settings.py

tests/ - Test cases (agent maintains these)

---

## 7. Deployment: Local Machine (tmux)

### Why Not GitHub Actions?
- Unreliable (actions dont always run)
- 6-hour time limit per job
- Complex setup for long-running tasks

### How to Run

```bash
# Start the agent (runs until 70% achieved or manually stopped)
tmux new -s trading-agent "cd /Users/i516386/Documents/GitHub/tradingBot && python -m autonomous_optimizer"

# Detach: Ctrl+B then D
# Reconnect: tmux attach -t trading-agent

# Or simpler (background with logs):
cd /Users/i516386/Documents/GitHub/tradingBot
nohup python -m autonomous_optimizer > logs/agent.log 2>&1 &
```

### Monitoring Progress

```bash
# Live log output
tail -f logs/agent.log

# Current state summary
cat autonomous_optimizer/context/session_state.json | python -m json.tool

# See iteration history
ls autonomous_optimizer/context/iterations/

# Git log of changes
git log --oneline agent/optimize
```

---

## 8. LLM Configuration

- Provider: Claude (Anthropic) via existing .streamlit/secrets.toml
- Usage: Multiple calls per iteration (analysis, strategy, coding, testing)
- Estimated cost: ~$0.50-1.00 per iteration, ~$20-40/day at 40 iterations/day
- No human approval needed: Agent makes all decisions autonomously

---

## 9. Safety Rails

Even without human approval, the agent has automated safety:

1. Test gate: Unit tests must pass before any commit. If tests break then auto-revert
2. Win rate regression protection: If WR drops >20% from best achieved then revert immediately
3. Max iterations cap: Default 500 (configurable). Prevents infinite loops
4. State persistence: If agent crashes, it resumes from last saved state
5. Git branching: All work on agent/optimize branch. Main branch untouched
6. Revert capability: Every iterations changes are tracked. Any change can be undone
7. File whitelist: Agent cannot modify .streamlit/secrets.toml, .git/, or autonomous_optimizer/ core files

---

## 10. Implementation Plan

### Phase 1: Agent Infrastructure
1. Package structure - Create autonomous_optimizer/ with all submodules
2. Session manager - Context persistence, history tracking, sub-session orchestration
3. Code editor - Safe file read/write across entire codebase
4. Git operations - Branch creation, commit, push, revert
5. Backtest runner - Wraps existing historical_trainer for quick evaluation
6. Success checker - Validates 3 consecutive 70%+ WR criteria

### Phase 2: Agent Brain (LLM Integration)
7. Strategist - Claude-powered strategy session (proposes improvements)
8. Analyzer - Claude-powered failure analysis (identifies root causes)
9. Coder - Claude-powered code generation (implements changes)
10. Tester - Runs tests, auto-fixes simple breaks

### Phase 3: Main Loop
11. Agent loop - Main orchestration (observe, think, act, test, evaluate)
12. Entry point - __main__.py (single command to start)

### Phase 4: Launch
13. Start script - tmux/nohup launcher
14. Branch setup - Create agent/optimize branch
15. Test run - Verify one full iteration works

---

## 11. File Structure

```
autonomous_optimizer/
  __init__.py
  __main__.py              - Entry point: python -m autonomous_optimizer
  agent.py                 - Main loop (observe, think, act, test, evaluate)
  config.py                - Agent configuration (max iterations, timeouts, etc.)
  session_manager.py       - Context management, history, sub-sessions
  code_editor.py           - Safe file read/write operations
  git_ops.py               - Git branch/commit/push/revert
  backtest_runner.py       - Runs backtests, returns structured results
  success_checker.py       - Checks 3 consecutive 70%+ WR
  llm/
    __init__.py
    client.py              - Claude API wrapper (uses secrets.toml)
    analyzer.py            - Failure analysis sessions
    strategist.py          - Strategy improvement sessions
    coder.py               - Code generation sessions
  context/
    session_state.json     - Persistent state (auto-created)
    iterations/            - Per-iteration logs (auto-created)
  scripts/
    start.sh               - One-command launcher
```

---

## 12. Key Technical Details

### How Backtests Are Run

The agent uses the existing historical_trainer but in a streamlined mode:

```python
from historical_trainer.runner import run_training
result = run_training(quick=True, no_ai=True)  # No Claude calls during backtest
win_rate = result["overall_win_rate"]
trade_count = result["total_triggered"]
```

### How Code Changes Are Applied

The agent reads target files, sends them to Claude with the improvement strategy, gets back modified code, and writes it:

```python
current_code = read_file("historical_trainer/simulation.py")
new_code = claude_session("coder", {
    "task": "Add trailing stop-loss that moves to breakeven after 0.5R profit",
    "current_code": current_code,
    "constraints": "Keep same function signatures, dont break imports"
})
write_file("historical_trainer/simulation.py", new_code)
```

### How Git Is Managed

```python
# Before changes
git_ops.create_snapshot()  # Tags current state for easy revert

# After successful iteration
git_ops.commit(f"Iteration {n}: WR {old}% -> {new}% (+{diff}%)")
git_ops.push("agent/optimize")

# After failed iteration
git_ops.revert_to_snapshot()  # Undo all changes
```

---

## 13. Expected Optimization Path

Based on analysis of the current codebase, the agent will likely try these approaches in order:

### Phase A: Generate More Trades (Priority #1)
The biggest problem is only 6 trades over 59 days. Before optimizing WR, we need signal.

1. Remove 11 AM scan restriction - allow zones to be detected throughout the day
2. Increase max trades/day from 2 to 5-8
3. Loosen scoring threshold to 25-30 (from 38)
4. Expand symbol list to full Nifty 50
5. Widen zone detection - allow 5-6 base candles, lower volume requirement

### Phase B: Improve Win Rate (Once trades > 30)
With enough trades, we can identify what works:

6. Regime-specific rules - only trade in trending markets
7. Trailing stop-loss - move SL to breakeven after 0.5R
8. Partial exits - book 50% at 1R, let rest run
9. Better entry timing - wait for confirmation candle
10. Time-of-day filter - avoid first 30 min and last 30 min

### Phase C: Fine-Tune to 70% (Once WR > 55%)

11. Score-based position sizing - higher score = larger position
12. Dynamic RR targeting - lower target in ranging, higher in trending
13. Multi-timeframe confirmation - hourly trend must align
14. Sector rotation - focus on trending sectors only

---

## 14. Differences from Current Approach

| Aspect | Current System | Autonomous Agent |
|--------|---------------|-----------------|
| What changes | 6 numeric parameters | Any code, any file |
| How often | Nightly optimization | Every 5-10 minutes |
| Who decides | Grid search + Claude suggests | Claude implements directly |
| Scope | Parameter tuning | Structural redesign |
| Human involvement | Manual review | Zero |
| Stopping condition | None (runs forever) | 3 consecutive 70%+ WR |
| Context | Resets each run | Persistent across all runs |
| Trade generation | ~0.1 trades/day | Target: 1-3 quality trades/day |

---

## 15. Risk Acknowledgment

Important: Achieving 70% win rate on historical data does NOT guarantee future performance. However, it provides:
- Statistical confidence that the strategy has an edge
- Enough sample size to validate the approach
- A framework that can be further improved post-deployment

The agents goal is to find a strategy configuration that consistently demonstrates edge over a 50-day window, which is a strong foundation for live trading.

---

## 16. How to Start (After Implementation)

```bash
# 1. Navigate to the project
cd /Users/i516386/Documents/GitHub/tradingBot

# 2. Start the agent in a tmux session
tmux new -s trading-agent

# 3. Run the agent
python -m autonomous_optimizer

# 4. Detach and let it run (Ctrl+B then D)

# 5. Check progress anytime
tmux attach -t trading-agent
# or
cat autonomous_optimizer/context/session_state.json | jq '.iteration, .best_win_rate_achieved, .consecutive_70pct_runs'
```

The agent will print progress like:
```
[Iteration 1] Starting backtest...
[Iteration 1] Result: WR=28.5%, Trades=14, PnL=-89
[Iteration 1] Analyzing: Too few winning trades, ranging regime killing us
[Iteration 1] Strategy: Remove ranging regime entirely, add trailing SL
[Iteration 1] Modifying: simulation.py, constants.py
[Iteration 1] Tests passed
[Iteration 1] New backtest: WR=42.1%, Trades=19, PnL=+156
[Iteration 1] Improved! Committing... (28.5% -> 42.1%)
---
[Iteration 2] Starting next iteration...