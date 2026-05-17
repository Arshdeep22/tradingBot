"""
Nightly Optimizer
------------------
Runs automatically at 4:30 PM IST (after market close) via GitHub Actions.

What it does:
1. Fetches 60 days of 15m data for all 50 Nifty stocks
2. Runs param grid backtests for Zone Scanner strategy
3. Asks Claude to pick the best params for tomorrow
4. Updates .streamlit/strategy_memory.json
5. Appends a daily entry to .streamlit/learning_journal.json
6. Writes reports/YYYY-MM-DD_optimization.json for audit

Usage:
    python nightly_optimizer.py           # Full optimization run
    python nightly_optimizer.py --quick   # Reduced grid (faster, for testing)
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/nightly_optimizer.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

from core.backtester import Backtester
from core.data_fetcher import DataFetcher
from core.llm_advisor import AICoreLLM, StrategyMemory
from core.market_regime import detect_regime
from core.learning_journal import LearningJournal
from core.ai_recommender import create_llm_from_env
from strategies.zone_scanner import ZoneScanner
from config.settings import NIFTY_50

# ── Parameter grids ──────────────────────────────────────────────────────────

ZONE_GRID = list(product(
    [70, 75, 80],         # min_score
    [2.0, 2.5, 3.0],      # rr_ratio
    [3, 4, 5],            # max_base_candles
))

QUICK_ZONE_GRID = list(product([70, 75, 80], [2.0, 3.0], [4]))

BUILD_DAYS = 45
TEST_DAYS  = 15
DATA_FETCH_PERIOD = "60d"


def ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)


def fetch_all_data(symbols: list) -> dict:
    """
    Fetch 60 days of 15m OHLCV data for every symbol.
    Returns {symbol: DataFrame}. Symbols with insufficient data are skipped.
    """
    fetcher = DataFetcher()
    data_dict = {}
    logger.info(f"Fetching data for {len(symbols)} symbols...")
    for i, sym in enumerate(symbols):
        try:
            df = fetcher.get_data(sym, timeframe="15m", period=DATA_FETCH_PERIOD)
            if df is not None and len(df) >= 50:
                data_dict[sym] = df
            else:
                logger.warning(f"Skipping {sym} — insufficient data ({len(df) if df is not None else 0} bars)")
        except Exception as e:
            logger.warning(f"Failed to fetch {sym}: {e}")
        if (i + 1) % 10 == 0:
            logger.info(f"  Fetched {i + 1}/{len(symbols)} symbols")
    logger.info(f"Data ready for {len(data_dict)} symbols")
    return data_dict


def _split_date(data_dict: dict) -> datetime:
    """Compute split date: TEST_DAYS before the most recent data point."""
    latest = max(df.index[-1] for df in data_dict.values())
    if hasattr(latest, 'to_pydatetime'):
        latest = latest.to_pydatetime()
    return latest - timedelta(days=TEST_DAYS)


def run_zone_grid(data_dict: dict, split_date: datetime, grid: list) -> list:
    """Run all param combos for Supply & Demand Zones. Returns list of result dicts."""
    results = []
    total = len(grid)
    for idx, (min_score, rr_ratio, max_base) in enumerate(grid):
        strategy = ZoneScanner(min_score=min_score, rr_ratio=rr_ratio,
                               max_base_candles=max_base)
        bt = Backtester(strategy=strategy)

        agg = {"triggers": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        for sym, df in data_dict.items():
            try:
                report = bt.run(df, split_date, symbol=sym)
                agg["triggers"] += report.zones_triggered
                agg["wins"]     += report.targets_hit
                agg["losses"]   += report.sl_hit
                agg["pnl"]      += report.total_pnl
            except Exception:
                pass

        wr = (agg["wins"] / agg["triggers"] * 100) if agg["triggers"] > 0 else 0.0
        pf_num = agg["pnl"] if agg["pnl"] > 0 else 0.0
        pf_den = abs(agg["pnl"]) if agg["pnl"] < 0 else 1.0
        results.append({
            "strategy": "Supply & Demand Zones",
            "params": {"min_score": min_score, "rr_ratio": rr_ratio,
                       "max_base_candles": max_base},
            "triggers": agg["triggers"],
            "wins": agg["wins"],
            "losses": agg["losses"],
            "win_rate": round(wr, 1),
            "total_pnl": round(agg["pnl"], 2),
            "profit_factor": round(pf_num / pf_den, 2) if pf_den > 0 else 0.0,
        })
        if (idx + 1) % 5 == 0 or idx + 1 == total:
            logger.info(f"  Zones grid: {idx + 1}/{total} combos done")

    return results


def _grid_table(results: list) -> str:
    """Format grid results as a compact markdown table for Claude."""
    if not results:
        return "No results."

    param_keys = list(results[0]["params"].keys())
    header = " | ".join(param_keys) + " | triggers | win_rate | total_pnl"
    separator = " | ".join(["---"] * (len(param_keys) + 3))

    rows = [f"| {header} |", f"| {separator} |"]
    for r in sorted(results, key=lambda x: x["win_rate"], reverse=True):
        param_vals = " | ".join(str(r["params"][k]) for k in param_keys)
        rows.append(
            f"| {param_vals} | {r['triggers']} | {r['win_rate']}% | ₹{r['total_pnl']:.0f} |"
        )
    return "### Supply & Demand Zones\n" + "\n".join(rows)


def ask_claude_for_best_params(llm: AICoreLLM, zone_results: list,
                                regime, memory: StrategyMemory) -> dict:
    """Send grid results to Claude and get best Zone params."""
    current_best = json.dumps(memory.best_params, indent=2) if memory.best_params else "None yet"

    system = (
        "You are an expert quantitative strategy optimizer for Supply & Demand Zone trading. "
        "Select the SINGLE BEST parameter set that maximizes win rate "
        "with at least 5 triggered trades (statistical minimum). "
        "Respond ONLY with valid JSON, no markdown."
    )

    user = f"""## Current Market Regime
{json.dumps(regime.to_dict(), indent=2)}

## Grid Results — last {BUILD_DAYS} days build, {TEST_DAYS} days test, all Nifty 50 symbols

{_grid_table(zone_results)}

## Current Best (strategy_memory.json)
{current_best}

## Instructions
1. Pick the combo with the highest win_rate where triggers >= 5.
2. If no combo has >= 5 triggers, pick the one with the most triggers.
3. Consider regime: volatile markets need higher min_score, ranging needs tighter R:R.
4. Set update_memory: true if the chosen params beat current best win_rate.

Respond with this exact JSON:
{{
  "analysis": "2-3 sentence summary of what the grid revealed",
  "regime_context": "how regime affected zone performance",
  "zone_best": {{
    "min_score": 75, "rr_ratio": 2.0, "max_base_candles": 4,
    "win_rate": 68.5, "triggers": 23, "reasoning": "why"
  }},
  "update_memory": true,
  "confidence": 8
}}"""

    raw = llm.chat(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1500,
        temperature=0.2,
    )
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
        ).strip()
    return json.loads(text)


def main():
    quick = "--quick" in sys.argv
    today = ist_now().strftime("%Y-%m-%d")
    day_of_week = ist_now().strftime("%A")

    logger.info("=" * 60)
    logger.info(f"Nightly Optimizer — {today} ({day_of_week})")
    logger.info("=" * 60)

    # Step 1: Detect regime
    logger.info("\n--- STEP 1: Detecting market regime ---")
    regime = detect_regime()
    logger.info(f"Regime: {regime.regime} | ADX={regime.adx} | VIX={regime.vix}")

    # Step 2: Fetch data for all Nifty 50 symbols
    logger.info("\n--- STEP 2: Fetching market data ---")
    data_dict = fetch_all_data(NIFTY_50)
    if len(data_dict) < 10:
        logger.error("Too few symbols with valid data. Aborting.")
        return

    split_date = _split_date(data_dict)
    logger.info(f"Split date: {split_date.strftime('%Y-%m-%d')} | "
                f"Build: ~{BUILD_DAYS}d | Test: ~{TEST_DAYS}d")

    # Step 3: Run Zone param grid
    logger.info("\n--- STEP 3: Running Zone parameter grid ---")
    zone_grid = QUICK_ZONE_GRID if quick else ZONE_GRID
    logger.info(f"Grid size: {len(zone_grid)} combinations")

    logger.info("Running Zones grid...")
    zone_results = run_zone_grid(data_dict, split_date, zone_grid)
    logger.info(f"Grid complete: {len(zone_results)} combinations tested")

    # Step 4: Ask Claude for best params
    logger.info("\n--- STEP 4: Asking Claude to select best params ---")
    memory = StrategyMemory()
    llm_output = None
    try:
        llm = create_llm_from_env()
        llm_output = ask_claude_for_best_params(llm, zone_results, regime, memory)
        logger.info(f"Claude analysis: {llm_output.get('analysis', '')[:100]}")
    except KeyError as e:
        logger.warning(f"AICORE env var missing ({e}) — using best result by win_rate")
    except Exception as e:
        logger.warning(f"Claude call failed ({e}) — using best result by win_rate")

    # Step 5: Update strategy_memory.json
    logger.info("\n--- STEP 5: Updating strategy memory ---")
    if llm_output and llm_output.get("update_memory"):
        zone_best = llm_output.get("zone_best", {})
        new_params = {
            "min_score":        zone_best.get("min_score", 75),
            "rr_ratio":         zone_best.get("rr_ratio", 2.0),
            "max_base_candles": zone_best.get("max_base_candles", 4),
        }
        new_wr = zone_best.get("win_rate", 0.0)
        memory.add(
            params=new_params,
            results={
                "win_rate": new_wr,
                "total_pnl": sum(r["total_pnl"] for r in zone_results
                                 if r["params"].get("min_score") == new_params["min_score"]),
                "total_zones": sum(r["triggers"] for r in zone_results
                                   if r["params"].get("min_score") == new_params["min_score"]),
                "triggered": zone_best.get("triggers", 0),
                "targets_hit": int(zone_best.get("triggers", 0) * new_wr / 100),
                "sl_hit": zone_best.get("triggers", 0) - int(zone_best.get("triggers", 0) * new_wr / 100),
            },
            analysis=llm_output.get("analysis", "Nightly grid optimization"),
            symbols=list(data_dict.keys()),
        )
        logger.info(f"Memory updated: score={new_params['min_score']}, "
                    f"rr={new_params['rr_ratio']}, base={new_params['max_base_candles']}, "
                    f"WR={new_wr:.1f}%")
    else:
        # Fallback: pick best zone combo by win_rate with >= 5 triggers
        valid = [r for r in zone_results if r["triggers"] >= 5]
        if valid:
            best = max(valid, key=lambda r: r["win_rate"])
            memory.add(
                params=best["params"],
                results={"win_rate": best["win_rate"], "total_pnl": best["total_pnl"],
                         "triggered": best["triggers"], "targets_hit": best["wins"],
                         "sl_hit": best["losses"], "total_zones": best["triggers"]},
                analysis="Nightly fallback (no Claude) — best win_rate with >= 5 triggers",
                symbols=list(data_dict.keys()),
            )
            logger.info(f"Fallback memory update: {best['params']} WR={best['win_rate']:.1f}%")

    # Step 6: Append to learning journal
    logger.info("\n--- STEP 6: Updating learning journal ---")
    journal = LearningJournal()

    # Load today's trading stats from EOD report if available
    today_trades = 0
    today_wins = 0
    today_losses = 0
    today_pnl = 0.0
    try:
        from database.db import DatabaseManager
        db = DatabaseManager()
        trades = db.get_closed_trades_for_date(today)
        today_trades = len(trades)
        today_wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
        today_losses = today_trades - today_wins
        today_pnl = sum((t.get("pnl") or 0) for t in trades)
    except Exception as e:
        logger.warning(f"Could not load today's trades for journal: {e}")

    journal.append_daily_entry({
        "date": today,
        "day_of_week": day_of_week,
        "regime": regime.regime,
        "nifty_direction": regime.nifty_direction,
        "adx": regime.adx,
        "vix": regime.vix,
        "strategy_used": "Supply & Demand Zones",
        "params": memory.live_params(),
        "trades_today": today_trades,
        "wins": today_wins,
        "losses": today_losses,
        "win_rate": round(today_wins / today_trades * 100, 1) if today_trades > 0 else 0.0,
        "total_pnl": round(today_pnl, 2),
        "optimization_combos_tested": len(zone_results),
        "best_zone_wr_found": max((r["win_rate"] for r in zone_results), default=0.0),
        "feedback_improvements": [],
        "notable_symbols": {},
    })

    # Step 7: Save audit report
    audit = {
        "date": today,
        "run_time_ist": ist_now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime": regime.to_dict(),
        "symbols_tested": len(data_dict),
        "combos_tested": len(zone_results),
        "zone_results": zone_results,
        "claude_output": llm_output,
        "memory_updated": bool(llm_output and llm_output.get("update_memory")),
        "new_best_params": memory.best_params,
        "new_best_win_rate": memory.best_win_rate,
    }
    audit_path = f"reports/{today}_optimization.json"
    with open(audit_path, "w") as f:
        json.dump(audit, f, indent=2)
    logger.info(f"Audit report saved to {audit_path}")

    logger.info("=" * 60)
    logger.info(f"Nightly Optimizer complete. Best zone WR: {memory.best_win_rate:.1f}%")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
