"""Manual entrypoint: `python -m trading_agent [--days N] [--symbols A B ...]`.

Useful for smoke-testing the trading agent on its own, without the
optimizer driving it. Every log line + tool call still lands in
`database/agent.db` with `agent='trading_bot'`.
"""
from __future__ import annotations

import argparse
import logging
import sys

from autonomous_optimizer.storage import install_db_logging


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trading Agent — standalone runner")
    p.add_argument("--days", type=int, default=10,
                   help="Historical days to backtest (default 10)")
    p.add_argument("--symbols", nargs="*", default=None,
                   help="Override symbols (else uses trading_agent_config.symbols)")
    p.add_argument("--max-bars", type=int, default=None,
                   help="Cap bars per symbol (useful in smoke tests)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    install_db_logging(level=logging.INFO, also_console=True,
                       agent="trading_bot", console_prefix="[BOT]")

    from trading_agent.runner import TradingAgentRunner
    runner = TradingAgentRunner()
    result = runner.run_backtest(
        days=args.days, symbols=args.symbols,
        max_bars_per_symbol=args.max_bars,
        triggered_by="cli",
    )
    print(
        f"run_id={result.run_id} trades={result.trade_count} "
        f"win_rate={result.win_rate:.1f}% pnl={result.total_pnl:.2f} "
        f"ok={result.ok}"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())