"""
Seed the live `database/agent.db` with a bit of sample data so the
Streamlit "Agent DB Explorer" page has something to display on first
open. Safe to re-run: it appends only.

Usage:
    py -3.12 tests\_seed_agent_db.py
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from autonomous_optimizer.storage.agent_db import (
    AgentDB, agent_scope, get_agent_db,
)
from trading_agent.config import (
    TradingAgentConfig, save_config,
)


def main() -> None:
    db = get_agent_db()

    # 1. Optimizer state
    db.save_session_state({
        "iteration": 3, "phase": "A",
        "consecutive_dual_success": 0,
        "best_win_rate": 55.0, "best_trade_count": 12,
        "best_pnl": 4200.0, "best_composite": 0.42,
        "tier1_false_positives": 1,
        "current_hypothesis_slug": "seed-demo",
        "insights": ["seed run for the dashboard"],
    })

    # 2. A couple of approaches + working-memory rows.
    db.record_approach("seed-approach-1", "widen zone score threshold",
                       iteration=1, result="improved", reverted=False)
    db.record_approach("seed-approach-2", "tighten SL to 1.5×ATR",
                       iteration=2, result="degraded", reverted=True)

    db.add_working_record({
        "iteration": 1, "phase": "A",
        "hypothesis_slug": "seed-approach-1",
        "hypothesis_description": "widen zone score threshold",
        "root_cause_category": "entry_quality",
        "win_rate": 55.0, "pnl": 4200.0, "trade_count": 12,
        "composite_score": 0.42, "reverted": False,
        "notes": "seed",
    })
    db.append_trajectory(iteration=1, wr=52.0, pnl=3000.0,
                          trade_count=10, composite=0.35)
    db.append_trajectory(iteration=2, wr=48.5, pnl=-1200.0,
                          trade_count=15, composite=0.28)
    db.append_trajectory(iteration=3, wr=55.0, pnl=4200.0,
                          trade_count=12, composite=0.42)

    # 3. Optimizer logs + a tool trace.
    db.add_log(level="INFO", logger_name="autonomous_optimizer.agent",
                message="[Iteration 3] Phase A", iteration=3,
                agent="optimizer")
    db.record_tool(tool_name="code_editor", action="write_file",
                    args={"path": "trading_agent/tools/strategy.py"},
                    result={"bytes": 2048}, ok=True,
                    iteration=3, agent="optimizer")

    # 4. Trading-agent config with a proper prompt.
    save_config(TradingAgentConfig(
        system_prompt=(
            "You are the trading bot.\n"
            "Guardrails: never breach max_risk_pct; only trade valid setups.\n"
            "Output {decision, confidence, reasoning} as JSON."
        ),
        llm_model="anthropic--claude-4.5-haiku",
        mode="backtest",
        symbols=["RELIANCE.NS", "TCS.NS"],
    ), db=db)

    # 5. A trading-agent lesson.
    db.add_trading_lesson(kind="lesson",
                           content="Avoid opening trades in the first 15 min.",
                           source="seed")

    # 6. A fake trading-agent run + one decision + one closed trade.
    run_id = "tarun-seed-demo"
    db.start_trading_run(run_id=run_id, mode="backtest",
                          days=10, symbols=["RELIANCE.NS"],
                          triggered_by="seed")
    dec_id = db.record_trading_decision(
        run_id=run_id, symbol="RELIANCE.NS", decision="BUY",
        confidence=0.62, reasoning="RSI 28 in confirmed uptrend",
        raw_llm_response='{"decision":"BUY","confidence":0.62,"reasoning":"..."}',
        bar_ts="2024-06-03 10:15",
        context={"rsi": 28.4, "trend": "up", "close": 2820.5, "atr": 12.3},
    )
    trade_id = db.record_trading_trade(
        run_id=run_id, symbol="RELIANCE.NS", side="BUY",
        quantity=8, entry_price=2820.5,
        stop_loss=2801.0, target=2860.0, decision_id=dec_id,
    )
    db.close_trading_trade(trade_id=trade_id, exit_price=2848.7,
                            pnl=(2848.7 - 2820.5) * 8,
                            pnl_percent=(2848.7 / 2820.5 - 1) * 100,
                            exit_reason="target")

    # Trading-agent logs + tool traces inside agent_scope, so they get
    # tagged with agent='trading_bot' + run_id automatically.
    with agent_scope("trading_bot", run_id=run_id):
        db.add_log(level="INFO", logger_name="trading_agent.runner",
                    message=f"Backtest starting run_id={run_id}")
        db.record_tool(tool_name="market_data", action="get_bars",
                        args={"symbol": "RELIANCE.NS", "lookback": 100},
                        result={"rows": 100, "source": "cache"}, ok=True)
        db.record_tool(tool_name="broker", action="open_position",
                        args={"trade_id": trade_id, "side": "BUY"},
                        result={"quantity": 8, "capital_after": 78000.0},
                        ok=True)
        db.record_tool(tool_name="broker", action="close_position",
                        args={"trade_id": trade_id, "reason": "target"},
                        result={"pnl": 225.6}, ok=True)
        db.add_log(level="INFO", logger_name="trading_agent.runner",
                    message=f"Backtest done run_id={run_id}")

    db.end_trading_run(run_id=run_id, win_rate=100.0,
                        total_pnl=225.6, trade_count=1,
                        trades_per_day=0.1,
                        notes="seed_open_positions=0", ok=True)

    print("Seeded database/agent.db with:")
    print("  • 3 trajectory points, 2 approaches, 1 working-memory row")
    print("  • 1 trading-agent config, 1 lesson, 1 run, 1 decision, 1 trade")
    print("  • optimizer log + tool trace, trading-bot logs + tool traces")
    print(f"  run_id = {run_id}")


if __name__ == "__main__":
    main()