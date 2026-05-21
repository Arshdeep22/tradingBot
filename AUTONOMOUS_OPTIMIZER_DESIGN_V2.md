# Autonomous Trading Bot Optimizer Agent - Design Document

**Created**: 2026-05-20
**Status**: Ready for Implementation
**Goal**: Achieve 70%+ win rate AND ₹50,000 profit on ₹1,00,000 capital in 50 days (3 consecutive runs)

---

## Overview & Goals

An autonomous agent that runs continuously, modifying the trading bot code, testing changes, and iterating until both goals are achieved. No human approval required.

### Success Criteria (Compound Gate)

The agent STOPS when all three are true across 3 consecutive 50-day backtests:
- Win rate >= 70% in every run
- Total trades >= 30 per run (statistical minimum AND frequency viability for the P&L target)
- Total simulated P&L >= ₹45,000 per run (10% buffer below the ₹50k live trading target)

All three must hold simultaneously. A 70% WR run with only 8 trades does NOT count.

### Differences from Current Approach

| Aspect | Current System | Autonomous Agent |
|--------|---------------|-----------------|
| What changes | 6 numeric parameters | Any code, any file |
| How often | Nightly optimization | Every 5-10 minutes |
| Who decides | Grid search + Claude suggests | Claude implements directly |
| Scope | Parameter tuning | Structural redesign |
| Human involvement | Manual review | Zero |
| Stopping condition | None (runs forever) | 3 consecutive: WR >= 70% + trades >= 30 + P&L >= ₹45k |
| Context | Resets each run | Persistent across all runs |
| Trade generation | ~0.1 trades/day | Target: 1-3 quality trades/day |
| P&L tracking | Broken (per-share, not rupees) | Fixed in Phase A iteration 1 |

---

## Problem Statement

The current trading bot has severe performance issues:
- Only 6-8 trades generated over 59 trading days - far too few for any statistical reliability
- Win rate: 25-37% - well below the 70% target
- Strategy oscillates between being too restrictive (0 trades for weeks) and too loose (generating losing trades)
- Parameters never converge - optimizer cycles between tightening after losses and loosening after dry spells
- Structural limitations: Scans zones only until 11 AM, max 2 trades/day, fixed entry/exit logic
- **P&L tracking is broken**: `trade_simulator.py` computes P&L as `exit_price - entry_price` (per-share) but never multiplies by position size. All reported P&L figures are per-share values, not actual rupee outcomes. This must be fixed first.

The core issue is not just parameter tuning - it is structural trading logic that needs rethinking.

### The Math: Why 70% WR Alone is Insufficient

| Scenario | Risk/Trade | Trades Needed for ₹50k | Trades/Day Required |
|----------|-----------|------------------------|---------------------|
| 1% risk, 1.8 RR, 70% WR | ₹1,000 | ~52 trades | ~1.0/day |
| 2% risk, 1.8 RR, 70% WR | ₹2,000 | ~26 trades | ~0.5/day |
| Current actual | 1% | 6 trades in 59 days | **0.1/day** |

Gap: Need 5-10x improvement in trade frequency AND a P&L goal alongside win rate.

---

## Architecture

The agent uses a layered cognitive architecture. Each layer has a single responsibility and cannot do the job of another layer.

```
OBSERVER     — reads only, never writes. Produces structured facts.
THINKER      — reasons only, never calls tools. Three sub-agents: Analyzer, Strategist, Coder.
REFLECTOR    — meta-cognition only. Detects loops, scores confidence, gates Tier-2.
SESSION MGR  — context brain. Routes sub-sessions, manages working + long-term memory.
EXECUTOR     — applies diffs + runs tests. Sandboxed subprocess with timeout guard.
VALIDATOR    — runs Tier-1 / Tier-2 backtests, computes composite score.
GIT LAYER    — truth of record. Snapshot, semantic commit, milestone tags, revert.
MEMORY STORE — persists across restarts. Includes semantic embeddings of past hypotheses.
SAFETY RAILS — always-on, non-negotiable. Cannot be overridden by any layer.
```

**Key design principle**: The Thinker never calls tools. The Actor (Executor) never reasons. Mixing them causes the LLM to rush to conclusions without fully observing, and to rationalize bad code instead of generating clean code.

- SESSION MANAGER (Context Brain): Maintains full history of what was tried, tracks which approaches failed/succeeded, decides what to try next (avoids repetition), manages sub-sessions for dedicated tasks. Routes: Analyze → Strategize → Code → Reflect → Execute → Validate.

- SCOPE: ALL FILES ARE MODIFIABLE
  - strategies/* (zone detection, scoring, filters, entry/exit)
  - historical_trainer/* (simulation, constants, grid, runner)
  - core/* (trade simulator, backtester, data fetcher)
  - config/* (settings, symbols, timeframes)
  - nightly_optimizer.py (optimization logic)
  - ai_trade_runner.py (live execution logic)
  - tests/* (test cases, validation)

- SUCCESS: 3 consecutive backtest runs with WR >= 70% + trades >= 30 + P&L >= ₹45k

### Updated Architecture Diagram

```
EXTERNAL WORLD
  ↓ (market data, backtest results, test output)
OBSERVER  [reads only — structured facts, no interpretation]
  ↓ (Observation object)
WORKING MEMORY ←→ LONG-TERM MEMORY + EMBEDDINGS
  ↓ (compressed context: recent 10 iters + phase summaries)
ANALYZER  [root cause only — commits to cause before any solution]
  ↓ (RootCause object)
STRATEGIST  [hypothesis only — novelty check via embeddings before proposing]
  ↓ (Hypothesis object)
REFLECTOR  [meta-cognition — confidence score, stuck detector, explore/exploit mode]
  ↓ (ReflectionResult — gates Tier-2 if confidence < 0.4)
CRITIC  [coherence check — does diff match hypothesis? blocks before filesystem write]
  ↓ (approved diff)
CODER → AST VALIDATION → WRITE TO DISK
  ↓
TEST RUNNER  [sandboxed subprocess, 15-min hard timeout]
  ↓ (pass/fail)
VALIDATOR  [Tier-1 quick → Tier-2 full if Tier-1 passes]
  ↓ (composite score, phase gate check)
GIT OPS  [semantic commit, milestone tags, revert on failure]
  ↓
SESSION STATE UPDATE  [working memory, long-term memory, embeddings store]
  ↓
STUCK DETECTOR  [fire explore mode if 10 iters with no improvement]
  ↑___________________________|
         (feedback loop)
```

**Safety Rails** sit outside this loop and cannot be overridden:
whitelist · capital floor · max-consec-loss gate · drawdown stop · file lock · iteration cap · position size cap

---

## Agent Loop

Each iteration follows this pattern:

1. **OBSERVE** - Structured fact collection (Observer only — no interpretation)
   - Backtest metrics: WR, trade count, P&L, composite score
   - Code diff from last iteration
   - Test output, anomaly flags, data freshness check
   - Regime state, git blame of recently changed lines

2. **ANALYZE** - Root cause only (Thinker: Analyzer sub-agent)
   - Commit to a root cause BEFORE proposing any solution
   - Categorize loss patterns, identify structural bottlenecks
   - Query long-term memory: what was tried before in similar conditions?
   - Output: structured root cause (not a solution)

3. **STRATEGIZE** - Hypothesis generation (Thinker: Strategist sub-agent)
   - Propose ONE constrained, testable hypothesis based on root cause
   - Novelty check: embed hypothesis text, compare against past hypothesis embeddings (threshold 0.85 cosine similarity) — if too similar to a failed attempt, reject and try again
   - Phase B/C constraint: hypothesis must touch <= 2 files (causal attribution)

4. **REFLECT** - Meta-cognition gate (Reflector)
   - Compute confidence score (0–1) on hypothesis
   - Check stuck signals: score trajectory variance, hypothesis cycling, phase exhaustion
   - If confidence < 0.4: skip Tier-2, log low-confidence attempt
   - If stuck signals fire: switch to explore mode

5. **CRITIC REVIEW** - Coherence check before touching filesystem
   - Does the proposed diff implement exactly what the hypothesis claims?
   - Any regressions introduced beyond the hypothesis scope?
   - If blocked: discard without touching filesystem, log reason

6. **IMPLEMENT** - Apply code changes (Executor: Actor)
   - AST-validate generated code before writing to disk
   - Surgical node-level edits via libcst where possible
   - Git snapshot before any write

7. **TEST** - Verify nothing broke (Executor)
   - Run unit tests in sandboxed subprocess with 15-minute timeout hard kill
   - If tests fail: auto-revert to snapshot

8. **VALIDATE** - Run backtest (Validator)
   - Tier 1 (10-day, fast): if fails, revert without Tier-2
   - Tier 2 (50-day, full): only if Tier 1 passes AND Reflector confidence >= 0.4
   - Compare composite score vs previous

9. **COMMIT OR REVERT**
   - Improved: semantic git commit + push
   - Worse: revert to snapshot, log failure with root cause

10. **CHECK SUCCESS** - 3 consecutive dual-success runs?
    - Yes: STOP (goal achieved!)
    - No: update memory, advance phase if gate passed, go to step 1

---

## Session & Context Management

### Why Sessions?

LLMs have limited context windows. The agent needs to manage information across potentially hundreds of iterations. Solution: dedicated sub-sessions with focused context, and a two-tier memory architecture that prevents context bloat.

### Session Types

- **Analysis Session**: Root cause only — no solution proposals. Context: backtest results + trade logs + current params + recent working memory
- **Strategy Session**: Hypothesis generation only. Context: root cause output + novelty check results + what was already tried (compressed)
- **Reflect Session**: Meta-cognition. Context: score trajectories + hypothesis history + stuck signals
- **Code Session**: Implement the approved hypothesis. Context: hypothesis + target files content + coding guidelines (no backtest data)
- **Test Session**: Run tests, fix any breaks. Context: changed files + test output + error messages
- **Evaluate Session**: Run backtest, compare results. Context: new code state + backtest results + history of results

### Two-Tier Memory Architecture

**Working Memory** (last 10 iterations, full detail, ~2k tokens):
- Feeds directly into every LLM call
- Contains: recent results, current hypothesis, last diffs, error messages

**Long-Term Memory** (compressed phase summaries, ~500 tokens):
- What moved the needle in each phase (e.g. "symbol expansion +50% and max_trades=4 were the Phase A breakthroughs; score filter changes had zero impact across 5 attempts")
- Semantic embeddings of every past hypothesis for novelty dedup
- Blocked approaches (never retry)

```python
thinker_context = {
    "recent": working_memory.get_last(n=10),    # ~2k tokens
    "learned": long_term.get_phase_summaries(),  # ~500 tokens
    "blocked": session_state.blocked_approaches
}
```

The episodic summarizer runs every 10 iterations: compresses working memory into a phase summary and promotes it to long-term memory. Working memory is then trimmed.

### Persistent State (autonomous_optimizer/context/session_state.json)

The state tracks:
- iteration number
- current phase (A, B, or C)
- best win rate achieved
- best trade count
- best P&L achieved (rupees)
- consecutive_dual_success (runs meeting ALL 3 criteria)
- all approaches tried (with results, files changed, whether reverted)
- current hypothesis + confidence score
- blocked approaches (things that definitely don't work)
- insights learned so far
- pnl_trajectory, wr_trajectory, trade_count_trajectory, composite_score_trajectory
- tier1_false_positives
- hypothesis_embeddings (list of (embedding_vector, result_summary) per past hypothesis)

This state persists across agent restarts, ensuring no work is ever lost.

---

## Full Modification Scope

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

```
strategies/ - Zone detection, scoring, filters, entry/exit
  zone_scanner.py, zone_filters.py, zone_scoring.py, zone_models.py, zone_risk.py
  zone_detection/*.py, zone_mtf/*.py, zone_scoring/*.py, zone_trade_levels/*.py
  market_conditions.py, stock_selector.py, base_strategy.py

historical_trainer/ - Training/simulation infrastructure
  simulation.py, constants.py, grid_search.py, runner.py
  time_utils.py, llm_calls.py, reporting.py, data_loader.py

core/ - Core execution engine
  trade_simulator.py, backtester.py, backtester_models.py
  data_fetcher.py, market_regime.py, engine.py

config/ - Configuration
  settings.py

tests/ - Test cases (agent maintains these)
```

---

## Optimization Phases

Based on analysis of the current codebase, the agent will follow these phases. Each phase has a specific success gate before advancing.

### Phase A: Fix Infrastructure + Generate Signal (Target: 30+ trades in 50 days)

**Goal**: Go from 6 trades/59 days to 30+ trades/50 days. Win rate is secondary here.

| Priority | Change | File | Expected Impact |
|----------|--------|------|-----------------|
| 1 **MANDATORY** | Fix P&L bug: add `quantity: int` to `TradeSetup`, multiply P&L by quantity in `simulate_setup()` | `strategies/base_strategy.py`, `core/trade_simulator.py` | P&L numbers become meaningful in rupees |
| 2 | Expand symbols: `TRAINING_SYMBOLS_FULL = NIFTY_50[:30]` | `historical_trainer/constants.py` | +50% opportunities |
| 3 | Expose `max_trades_per_day` as param in `DEFAULT_ZONE_PARAMS`, set to 4 | `historical_trainer/constants.py`, `historical_trainer/simulation.py` line 194 | 2x trade volume |
| 4 | Change split time to 1 PM IST: `SPLIT_UTC_H=7, SPLIT_UTC_M=2` | `historical_trainer/constants.py` | Captures afternoon institutional zones |
| 5 | Add afternoon scanning: run `run_day()` twice per day (morning + afternoon split) | `historical_trainer/simulation.py` | 2x zone formation opportunities |
| 6 | Lower `min_score_to_trade` to 28; remove ranging +5 penalty in `simulation.py` line 213 | `historical_trainer/constants.py`, `historical_trainer/simulation.py` | More candidates qualify |
| 7 | Zone blacklist expiry: 10 trading days instead of permanent | `historical_trainer/simulation.py` | Re-trade reformed zones |

**Phase A success gate**: >= 30 trades in any 50-day backtest AND WR >= 40%. If not achieved in 30 iterations, loosen further (symbols to 40+, score to 22, max_trades to 6).

### Phase B: Improve Win Rate (Target: 60%+ WR, 30+ trades maintained)

**Goal**: Push win rate from ~40% to 60%+. Trade count must not fall below 30.

| Priority | Change | File |
|----------|--------|------|
| 1 | Trailing stop: after 0.5R profit, move SL to breakeven (converts small losses to breakeven) | `core/trade_simulator.py` |
| 2 | Regime-specific score thresholds: 45+ in trending, 30+ in ranging | `historical_trainer/simulation.py` |
| 3 | Time-of-day filter: skip first 30 bars after open (9:15-9:45 IST) | `historical_trainer/simulation.py` |
| 4 | Partial exit at 1R: book 50% of position, trail remainder at breakeven | `core/trade_simulator.py` |
| 5 | Multi-timeframe confirmation: only trade demand in confirmed 1H uptrend, supply in confirmed 1H downtrend | `strategies/zone_scanner.py` |

**Phase B success gate**: WR >= 60%, trades >= 30, P&L > 0 in a 50-day backtest.

### Phase C: Hit Dual Target (70% WR + ₹45k P&L)

**Goal**: Achieve both stopping criteria simultaneously. Position sizing upgrades unlock here.

| Priority | Change | File |
|----------|--------|------|
| 1 | Score-tiered position sizing: score 50-60 → 2% risk; score 45-49 → 1.5% risk; score 38-44 → 1% risk | `historical_trainer/simulation.py`, new `position_sizing.py` |
| 2 | Dynamic RR: trending regime → 2.5R target; ranging regime → 1.5R target | `strategies/zone_trade_levels/targets.py` |
| 3 | Capital compounding: track running capital, size positions on current capital (not fixed ₹1L) | `historical_trainer/simulation.py` |
| 4 | Sector rotation filter: focus on top 2 trending Nifty sectors (use `config/stock_sectors.json`) | `strategies/zone_scanner.py` |

**Phase C unlock condition**: Phase B success gate must have passed on at least 2 consecutive backtests before position sizing can be increased.

### Phase Advancement Logic

```
if composite_score not improved in 10 consecutive iterations:
    advance to next phase early (current phase is exhausted)

if current_phase == "A" and trades >= 30 and wr >= 40%:
    advance to Phase B

if current_phase == "B" and wr >= 60% and trades >= 30 and pnl > 0:
    advance to Phase C
```

---

## Validation & Scoring

### Two-Tier Validation Protocol

To avoid running a 50-day backtest for every iteration (expensive), the agent uses:

**Tier 1 — Quick Validation (last 10 trading days)**
- Run before every full backtest
- Pass criteria: WR >= 55% AND trades >= 6
- ~10x faster than full backtest
- Filters out obviously bad changes before committing time to full run
- Track `tier1_false_positives` (Tier 1 pass → Tier 2 fail); if > 40%, tighten Tier 1 thresholds

**Tier 2 — Full Validation (last 50 trading days)**
- Only run when Tier 1 passes
- Pass criteria: WR >= 70% AND trades >= 30 AND P&L >= ₹45,000

```python
# In backtest_runner.py
def run_quick(last_n_days=10) -> BacktestResult:
    """Tier 1: fast filter, ~1-2 minutes"""

def run_full(last_n_days=50) -> BacktestResult:
    """Tier 2: full validation, ~10-15 minutes"""

# In agent.py main loop:
tier1 = runner.run_quick()
if tier1.passes_tier1:
    tier2 = runner.run_full()
    evaluate(tier2)
else:
    git_ops.revert_to_snapshot()
    log("Tier 1 failed, reverting without full backtest")
```

This reduces average iteration time by ~70% because most changes fail Tier 1.

### Multi-Objective Composite Score

The agent needs a single number to answer "was iteration N better than N-1?" when WR improved but P&L dropped, or vice versa.

```python
def normalize(x, min_val, max_val):
    return max(0.0, min(1.0, (x - min_val) / (max_val - min_val)))

def composite_score(result: BacktestResult) -> float:
    return (
        0.35 * normalize(result.win_rate, 0, 100)
      + 0.30 * normalize(result.total_pnl, -50000, 100000)
      + 0.20 * normalize(result.trades_per_day, 0, 5)
      + 0.10 * normalize(result.profit_factor, 0, 4)
      + 0.05 * normalize(result.sharpe_ratio, -2, 4)
    )
```

**Weight rationale**:
- WR (35%): primary goal but not everything
- P&L (30%): the ₹50k goal - heavily weighted
- Trade frequency (20%): must not sacrifice frequency for WR
- Profit factor (10%): ensures consistency (wins bigger than losses)
- Sharpe (5%): tie-breaker for similar strategies

**Decision rules for the agent**:
- `composite_new > composite_old`: commit the change
- `composite_new < composite_old - 0.05`: revert immediately
- `composite_new` within ±0.05: keep if WR improved, revert if WR degraded
- No improvement in 10 consecutive iterations: advance phase

### Evaluation Metrics Reference

The agent must compute and track these metrics per iteration (not just WR):

| Metric | Target (Phase A) | Target (Phase B) | Target (Phase C) |
|--------|-----------------|-----------------|-----------------|
| `win_rate_pct` | >= 40% | >= 60% | >= 70% |
| `total_pnl_rupees` | > 0 | > ₹10,000 | >= ₹45,000 |
| `trades_per_day` | >= 0.6 | >= 0.6 | >= 0.6 |
| `avg_pnl_per_trade` | > 0 | > ₹300 | > ₹900 |
| `max_drawdown_rupees` | < ₹20,000 | < ₹15,000 | < ₹12,000 |
| `profit_factor` | >= 1.0 | >= 1.5 | >= 2.0 |
| `sharpe_ratio` | > 0 | > 0.5 | > 1.0 |
| `capital_floor_hit` | False | False | False |

**profit_factor** = `sum(winning_pnl) / abs(sum(losing_pnl))` - must be >= 1.5 to advance from Phase A, >= 2.0 for Phase C completion.

**pnl_by_week** = array of 10 weekly P&L values - detects if gains are concentrated in 1 lucky week (fragile strategy signal).

---

## Safety Rails

Even without human approval, the agent has automated safety:

1. Test gate: Unit tests must pass before any commit. If tests break then auto-revert
2. Win rate regression protection: If WR drops >20% from best achieved then revert immediately
3. Max iterations cap: Default 500 (configurable). Prevents infinite loops
4. State persistence: If agent crashes, it resumes from last saved state
5. Git branching: All work on agent/optimize branch. Main branch untouched
6. Revert capability: Every iterations changes are tracked. Any change can be undone
7. File whitelist: Agent cannot modify .streamlit/secrets.toml, .git/, or autonomous_optimizer/ core files
8. Capital floor: If simulated capital drops below ₹70,000 at any point in a 50-day run, that parameter set is REJECTED even if final WR is 70%
9. Max consecutive loss gate: If max consecutive losses in a backtest run exceeds 7, the parameter set is rejected (7 × 2% = 14% drawdown, the psychological ruin threshold)
10. Position size lock: `risk_pct` is capped at 1.0% for all Phase A and Phase B iterations. Only Phase C may test 1.5-2%. Agent cannot exceed 2.5% under any circumstance.
11. Drawdown stop during simulation: If running capital drops below 80% of its peak during a simulated run, stop adding new trades for that run (mirrors real trading discipline)

---

## Technical Implementation Details

### Cognitive Layer Roles

The agent separates cognition into strict roles. No layer does the job of another.

#### Observer (reads only, no interpretation)

Inputs: raw data sources. Output: structured `Observation` object with no opinions.

```python
@dataclass
class Observation:
    backtest: BacktestResult
    code_diff: str          # diff from last committed state
    test_output: str
    anomaly_flags: list[str]  # data gaps, stale prices, zero-volume days
    data_freshness: dict    # last-updated timestamps per symbol
    regime_state: str       # trending / ranging / choppy
    git_blame_recent: list  # which lines changed in last 3 iterations
```

The Observer never says "the win rate dropped because of X". It reports: "win rate dropped from 61% to 49%." Interpretation is the Analyzer's job.

#### Thinker: Analyzer (root cause only)

Receives: Observation + working memory. Outputs: `RootCause` — one committed explanation, no solution.

```python
@dataclass
class RootCause:
    category: str           # e.g. "entry_timing", "zone_quality", "exit_logic"
    evidence: list[str]     # specific facts from Observation supporting this
    confidence: float       # 0–1 how confident the Analyzer is
    ruling_out: list[str]   # alternative explanations explicitly rejected
```

Forcing the Analyzer to rule out alternatives prevents the model from latching onto the first plausible cause.

#### Thinker: Strategist (hypothesis only)

Receives: RootCause + novelty check result. Outputs: `Hypothesis` — one testable change.

```python
@dataclass
class Hypothesis:
    slug: str               # short ID for git commits, e.g. "trailing-stop-breakeven"
    description: str        # plain English: what changes and why
    target_files: list[str] # max 2 files in Phase B/C
    expected_delta: str     # "expect WR +5-10%, trades unchanged"
    novelty_score: float    # 1.0 = fully novel, 0.0 = identical to past attempt
```

#### Thinker: Coder (implementation only)

Receives: approved Hypothesis + file contents. Outputs: diffs only — no reasoning, no rationale. Must not change anything outside the `target_files` listed in the hypothesis.

#### Reflector (meta-cognition)

Runs after Strategist, before Critic. Outputs a `ReflectionResult`:

```python
@dataclass
class ReflectionResult:
    confidence: float       # 0–1 confidence in the current hypothesis
    stuck: bool             # True if stuck signals fire (see Stuck Signals section)
    mode: str               # "exploit" (normal) or "explore" (stuck)
    gate_tier2: bool        # False if confidence < 0.4, skip Tier-2 to save time
    reason: str             # human-readable explanation for logs
```

#### Critic (coherence check before filesystem write)

Receives: Hypothesis + generated diffs. Outputs: `CriticResult`.

```python
@dataclass
class CriticResult:
    approved: bool
    reason: str             # if blocked: why it was rejected
    scope_violations: list  # files changed outside target_files
    hypothesis_drift: bool  # True if diff implements something different from hypothesis
```

If `approved=False`, the iteration is discarded **without touching the filesystem**. No revert needed.

### Reflector and Meta-Cognition

The Reflector answers: *"Is the agent making genuine progress, or is it cycling?"*

#### Stuck Signals

```python
STUCK_SIGNALS = {
    "score_oscillation":   variance(composite_score_trajectory[-10:]) < 0.02,
    "hypothesis_cycling":  len(set(hypothesis_slugs[-10:])) < 4,
    "phase_exhausted":     phase_iterations > 25 and not phase_gate_hit,
    "critic_rejection_rate": rejections_last_10 / 10 > 0.6,
}

stuck = any(STUCK_SIGNALS.values())
```

#### Explore Mode

When stuck, the Strategist switches from local search to structural exploration:

```python
if reflector.mode == "explore":
    strategist.prompt_suffix = (
        "Ignore all prior constraints. Assume everything tried so far was wrong. "
        "Propose something structurally different from any past hypothesis. "
        "It is acceptable to sacrifice some WR to learn what the bottleneck is."
    )
```

#### Confidence Score

The Reflector computes confidence based on:
- How strongly the root cause is supported by evidence (Analyzer confidence)
- Novelty score of the hypothesis (low novelty = low confidence)
- Whether similar hypotheses improved or degraded score in the past

```python
confidence = (
    0.4 * analyzer_confidence
  + 0.4 * hypothesis.novelty_score
  + 0.2 * past_similar_outcomes_signal  # +1 if similar improved, -1 if degraded
)
```

If `confidence < 0.4`: run Tier-1 only. Log the low-confidence attempt. Do not spend 15 minutes on Tier-2.

### Semantic Embeddings for Hypothesis Dedup

The most expensive mistake the agent can make is re-trying a variant of something that already failed. Text matching alone misses paraphrases ("add trailing stop" ≈ "move SL to breakeven after profit"). Embeddings catch them.

#### How it Works

Every hypothesis is embedded on creation and compared against all past hypothesis embeddings:

```python
from memory.embeddings import embed, cosine_similarity

def novelty_check(hypothesis: Hypothesis, memory: LongTermMemory) -> float:
    h_vec = embed(hypothesis.description)
    similarities = [
        cosine_similarity(h_vec, past.embedding)
        for past in memory.hypothesis_embeddings
    ]
    if not similarities:
        return 1.0  # first hypothesis, fully novel
    max_sim = max(similarities)
    return 1.0 - max_sim  # novelty = 1 - max similarity to any past hypothesis

# In strategist:
novelty = novelty_check(hypothesis, long_term_memory)
if novelty < 0.15:  # < 15% novel = too similar to a past attempt
    most_similar = find_most_similar(hypothesis, memory)
    log(f"Hypothesis too similar to iter {most_similar.iter} ({most_similar.result}). Regenerating.")
    return regenerate_hypothesis(root_cause, exclude=most_similar)
```

#### Embedding Model

Use a small local embedding model (e.g. `sentence-transformers/all-MiniLM-L6-v2`) to avoid API cost. Embeddings are cheap and local:

```python
from sentence_transformers import SentenceTransformer
_model = SentenceTransformer("all-MiniLM-L6-v2")

def embed(text: str) -> list[float]:
    return _model.encode(text).tolist()
```

Each embedding is stored in `session_state.json` alongside the hypothesis result, forming a permanent knowledge base of what was tried.

### How Backtests Are Run

The agent uses the existing historical_trainer but in a streamlined, sandboxed mode with a hard timeout:

```python
import subprocess, json

def run_backtest(last_n_days: int) -> BacktestResult:
    result = subprocess.run(
        ["python", "-m", "historical_trainer.runner", f"--days={last_n_days}", "--no-ai"],
        capture_output=True, text=True,
        timeout=900  # 15-minute hard kill — prevents runaway loops in new code
    )
    return BacktestResult(**json.loads(result.stdout))
```

### How Code Changes Are Applied (AST-Aware)

The agent reads target files, sends them to the Coder with the approved hypothesis, gets back modified code, validates syntax before writing:

```python
import ast, libcst as cst

current_code = read_file("historical_trainer/simulation.py")
new_code = claude_session("coder", {
    "task": "Add trailing stop-loss that moves to breakeven after 0.5R profit",
    "current_code": current_code,
    "constraints": "Keep same function signatures, don't break imports, change <= 2 functions"
})

# Validate syntax before touching disk
try:
    ast.parse(new_code)
except SyntaxError as e:
    log_error(f"Coder generated invalid syntax: {e}. Discarding.")
    return  # Never writes to disk

write_file("historical_trainer/simulation.py", new_code)
```

For surgical single-function edits, use libcst to replace only the target node:

```python
# libcst surgical edit: replace only simulate_setup(), leave all other code untouched
tree = cst.parse_module(current_code)
modified = tree.visit(ReplaceFunctionVisitor("simulate_setup", new_function_src))
write_file(path, modified.code)
```

### How Git Is Managed (Semantic Commits + Milestone Tags)

```python
# Before changes
git_ops.create_snapshot()  # Tags current state for easy revert

# After successful iteration — semantic commit message (machine-queryable)
git_ops.commit(
    f"[iter={n}][phase={phase}][wr={new_wr:.1f}%][pnl={pnl}]"
    f"[trades={trades}][composite={score:.3f}][hyp={hypothesis.slug}]"
)
git_ops.push("agent/optimize")

# Milestone tags — queryable starting points if Phase C breaks things badly
if phase_just_advanced:
    git_ops.tag(f"phase-{new_phase.lower()}-start")
if first_time_wr_above_70:
    git_ops.tag("first-70pct")
if consecutive_dual_success == 3:
    git_ops.tag("goal-achieved")

# After failed iteration
git_ops.revert_to_snapshot()
```

Query historical performance of a specific technique:
```python
history = git_ops.query_commits(tag_filter="trailing_stop", metric="wr")
# Returns [{iter: 9, wr: 61, pnl: 18400}, ...]
```

### Git as Knowledge Graph

Git is not just a backup mechanism — it is a queryable log of what improved things and why.

#### Semantic Commit Format

```
[iter=14][phase=B][wr=61.2][pnl=18400][trades=38][composite=0.522][hyp=trailing-stop-breakeven]

Hypothesis: after 0.5R profit, move SL to breakeven. Expected +5-10% WR.
Actual: WR +12.4%, P&L +₹8,200, trades unchanged. Root cause: exits at full loss avoidable.
```

Machine-readable tags allow the Analyzer to query git history directly:

```python
def query_commits(tag_filter: str, metric: str) -> list[dict]:
    log = subprocess.check_output(
        ["git", "log", "--oneline", "--grep", tag_filter, "agent/optimize"]
    )
    # parse [metric=value] from each commit message
```

#### Branch-per-Hypothesis (Optional for Parallel Experiments)

For Phase C, run two hypotheses in parallel on separate branches and pick the winner:

```
agent/optimize/            ← stable merged improvements
agent/hyp/dynamic-rr       ← active experiment A
agent/hyp/sector-rotation  ← active experiment B
```

Pick the branch with higher composite score, merge to `agent/optimize`, delete the loser.

### Causal Attribution and Single-Change Constraint

#### Why This Matters

If iteration 14 changes trailing stops, score thresholds, AND symbol count simultaneously and WR improves 12%, the agent cannot know which change caused the improvement. It may keep all three, then spend 20 iterations trying to improve something that was already optimal.

#### Single-Change Constraint (Phase B/C)

```python
if session_state.phase in ("B", "C"):
    if len(hypothesis.target_files) > 2:
        raise ConstraintViolation(
            "Phase B/C: hypothesis must touch <= 2 files for causal clarity"
        )
```

Phase A is exempt because the goal is just to get trades flowing — causality is less important.

#### Causal Attribution Tracking

Track which specific change contributed to the best run:

```json
{
  "best_run_at_iter": 28,
  "contributing_changes": [
    {"iter": 4,  "hyp": "expand-symbols",          "delta_composite": 0.13},
    {"iter": 9,  "hyp": "trailing-stop-breakeven", "delta_composite": 0.18},
    {"iter": 14, "hyp": "mtf-confirmation",         "delta_composite": 0.09}
  ]
}
```

The Strategist reads this before proposing Phase C improvements — it won't re-try anything already confirmed as working.

### LLM Configuration

- Provider: SAP AI Core (proxies `anthropic--claude-4.6-opus`)
- Credentials: env vars `AICORE_AUTH_URL`, `AICORE_API_URL`, `AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET` — same vars used by existing GitHub Actions workflows; NOT `.streamlit/secrets.toml` (that file is Streamlit-local only)
- Client: reuse `core/ai_recommender.py` `AICoreLLM` class for all LLM calls
- Python target: 3.11 (matches GitHub Actions CI environment)
- Usage: Multiple calls per iteration (analysis, strategy, coding, testing)
- Estimated cost: ~$0.50-1.00 per iteration, ~$20-40/day at 40 iterations/day
- No human approval needed: Agent makes all decisions autonomously

---

## File Structure

```
autonomous_optimizer/
  __init__.py
  __main__.py              - Entry point: python -m autonomous_optimizer
  agent.py                 - Main loop (observe, analyze, reflect, critique, execute, validate)
  config.py                - Agent configuration (max iterations, timeouts, etc.)
  session_manager.py       - Context management, two-tier memory, episodic summarizer
  code_editor.py           - AST-aware file read/write (ast.parse + libcst surgical edits)
  git_ops.py               - Git branch/semantic-commit/milestone-tags/push/revert
  backtest_runner.py       - Runs backtests in sandboxed subprocess (15-min timeout)
  success_checker.py       - Checks 3 consecutive dual-success runs
  llm/
    __init__.py
    client.py              - Claude API wrapper (uses secrets.toml)
    observer.py            - Structured fact collection (reads only, no interpretation)
    analyzer.py            - Root cause analysis (commits to cause before solution)
    strategist.py          - Hypothesis generation + novelty check
    reflector.py           - Meta-cognition: confidence score, stuck detector
    critic.py              - Coherence check before filesystem write
    coder.py               - Code generation with AST validation
  memory/
    working_memory.py      - Last 10 iterations, full detail
    long_term_memory.py    - Compressed phase summaries + semantic embeddings
    embeddings.py          - Hypothesis embedding + cosine similarity search
  context/
    session_state.json     - Persistent state (auto-created)
    iterations/            - Per-iteration logs (auto-created)
  scripts/
    start.sh               - One-command launcher
```

**Optimizer-only dependencies** (install on Oracle Cloud VM — not in `requirements.txt`):
```
libcst>=1.1.0               - AST-aware surgical code edits
sentence-transformers>=2.7  - Local embeddings for hypothesis dedup (all-MiniLM-L6-v2)
```

---

## Implementation Plan

### Phase 1: Agent Infrastructure
1. Package structure - Create autonomous_optimizer/ with all submodules
2. Session manager - Context persistence, two-tier memory, episodic summarizer, sub-session router
3. Code editor - AST-aware file read/write (ast.parse() validation + libcst surgical edits)
4. Git operations - Branch creation, semantic commit, milestone tags, push, revert
5. Backtest runner - Wraps existing historical_trainer, sandboxed subprocess with 15-min timeout
6. Success checker - Validates 3 consecutive dual-success criteria

### Phase 2: Agent Brain (LLM Integration)
7. Observer - Structured fact collection (metrics, diffs, anomaly flags, freshness check)
8. Analyzer - Root-cause-only session (commits to cause before proposing solution)
9. Strategist - Hypothesis generation with novelty check via semantic embeddings
10. Reflector - Meta-cognition: confidence score, stuck detector, explore mode
11. Critic - Coherence check: does diff match hypothesis? blocks before filesystem write
12. Coder - Code generation with AST validation before write

### Phase 3: Main Loop
13. Agent loop - Main orchestration (observe, analyze, strategize, reflect, critique, execute, validate)
14. Entry point - __main__.py (single command to start)

### Phase 4: Launch
15. Start script - tmux/nohup launcher
16. Branch setup - Create agent/optimize branch, set phase-start tag
17. Test run - Verify one full iteration works end-to-end

---

## Deployment & Monitoring

### Why Oracle Cloud Free Tier?

| Option | Problem |
|--------|---------|
| Local machine | Computer must stay on 24/7 |
| GitHub Actions | 6-hour job limit, no persistent filesystem |
| Streamlit Community Cloud | Web-app-only; apps sleep on inactivity; no subprocess support |
| **Oracle Cloud Free Tier** | ✅ 4 ARM cores + 24 GB RAM, free forever, full persistent disk, 24/7 unattended |

### One-Time VM Setup

```bash
# 1. Create VM at cloud.oracle.com
#    Shape: VM.Standard.A1.Flex — 4 OCPUs, 24 GB RAM, Ubuntu 22.04 (ARM)
#    Add your SSH public key during creation

# 2. SSH in and install dependencies
ssh ubuntu@<VM_PUBLIC_IP>
sudo apt update && sudo apt install -y python3.11 python3.11-venv git tmux

# 3. Clone the repo
git clone git@github.com:Arshdeep22/tradingBot.git
cd tradingBot

# 4. Set up Python environment
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install libcst sentence-transformers   # optimizer-only extras

# 5. Set credentials (add to ~/.bashrc so they survive reboots)
export AICORE_AUTH_URL="..."
export AICORE_API_URL="..."
export AICORE_CLIENT_ID="..."
export AICORE_CLIENT_SECRET="..."
export SUPABASE_URL="..."
export SUPABASE_KEY="..."

# 6. Add a GitHub SSH key so the agent can push commits
ssh-keygen -t ed25519 -C "oracle-optimizer"
cat ~/.ssh/id_ed25519.pub   # add this to GitHub → Settings → SSH Keys
```

### Running the Agent

```bash
# Start in a persistent tmux session
tmux new -s trading-agent
source .venv/bin/activate
python -m autonomous_optimizer
# Detach: Ctrl+B then D
# Reconnect: tmux attach -t trading-agent
```

### Auto-Restart on VM Reboot (systemd — recommended)

```ini
# /etc/systemd/system/trading-optimizer.service
[Unit]
Description=Autonomous Trading Bot Optimizer
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/tradingBot
EnvironmentFile=/home/ubuntu/.env_optimizer
ExecStart=/home/ubuntu/tradingBot/.venv/bin/python -m autonomous_optimizer
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable trading-optimizer && sudo systemctl start trading-optimizer
```

### Monitoring Progress

```bash
# From any device — SSH in to see live logs
ssh ubuntu@<VM_PUBLIC_IP>
tmux attach -t trading-agent

# Or via journalctl if using systemd
journalctl -fu trading-optimizer

# Quick status check without SSH — agent commits state after every iteration
# Check: github.com/Arshdeep22/tradingBot/commits/agent/optimize

# State summary
cat autonomous_optimizer/context/session_state.json | jq '.iteration, .best_win_rate_achieved, .best_pnl_achieved, .consecutive_dual_success'

# Iteration history
ls autonomous_optimizer/context/iterations/

# Git log of agent changes
git log --oneline agent/optimize
```

### Sample Progress Output

```
[Iteration 1] Phase A | Tier1 backtest...
[Iteration 1] Tier1: WR=28.5%, Trades=3 (10-day) - FAILED (< 55% WR). Reverting.
---
[Iteration 2] Phase A | Applying: Expand symbols + max_trades=4...
[Iteration 2] Tier1: WR=41.0%, Trades=7 (10-day) - PASSED
[Iteration 2] Tier2 full backtest (50-day)...
[Iteration 2] Result: WR=38.2%, Trades=31, PnL=₹4,200, Composite=0.31
[Iteration 2] Improved (0.18 -> 0.31)! Committing...
---
[Iteration 15] Phase B | WR=61%, Trades=38, PnL=₹18,400, Composite=0.52
[Iteration 15] Phase B gate passed! Advancing to Phase C...
---
[Iteration 28] Phase C | WR=72%, Trades=44, PnL=₹51,200, Composite=0.87
[Iteration 28] DUAL SUCCESS RUN 1/3 - Win rate 72% + P&L ₹51,200 on ₹1L!
```

### Milestone Tags

| Tag | When to Set |
|-----|-------------|
| `phase-a-start` | Agent starts |
| `phase-b-start` | Phase A gate passed |
| `phase-c-start` | Phase B gate passed |
| `first-70pct` | First time WR >= 70% in any backtest |
| `goal-achieved` | 3 consecutive dual-success runs |

If Phase C badly degrades Phase B results, `git checkout phase-b-start` gives a clean known-good baseline without bisecting 50+ commits.

---

## Risk Acknowledgment

Important: Achieving 70% win rate and ₹45k simulated P&L on historical data does NOT guarantee future performance. However, it provides:
- Statistical confidence that the strategy has an edge (30+ trades, not 6)
- Real rupee P&L validation (not just win rate)
- A framework that can be further improved post-deployment

The agents goal is to find a strategy configuration that consistently demonstrates edge over a 50-day window, which is a strong foundation for live paper trading.
