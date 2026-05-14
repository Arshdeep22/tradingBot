"""
EOD Report Generator
---------------------
Runs at 3:35 PM IST via GitHub Actions.
Reads today's AI recommendations log and the database to generate
reports/YYYY-MM-DD_ai_report.md showing which trades succeeded.

Usage:
    python report_generator.py              # Uses today's IST date
    python report_generator.py 2026-05-15   # Override date (for testing)
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import DatabaseManager

os.makedirs("reports", exist_ok=True)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/report_generator.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

db = DatabaseManager()
STRATEGY = "AI Recommendations"


def ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)


def load_recommendations_log(today: str) -> dict:
    path = f"reports/{today}_recommendations.json"
    if not os.path.exists(path):
        logger.warning(f"No recommendations log found at {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def get_todays_ai_trades(today: str) -> dict:
    """
    Return a dict of symbol -> trade for AI trades active today.
    Combines: open trades, closed trades (exit today), and trades entered today.
    """
    all_ai_trades = db.get_trades_by_strategy(STRATEGY)
    result = {}
    for t in all_ai_trades:
        entry_date = (t.get("entry_time") or "")[:10]
        exit_date = (t.get("exit_time") or "")[:10]
        if entry_date == today or exit_date == today:
            result[t["symbol"]] = t
    return result


def get_todays_ai_pending(today: str) -> list:
    """Pending orders with strategy='AI Recommendations' created today."""
    all_pending = db.get_pending_orders()
    result = []
    for o in all_pending:
        if o.get("strategy") != STRATEGY:
            continue
        created = (o.get("created_at") or "")[:10]
        if created == today:
            result.append(o)
    return result


def _pnl_str(pnl) -> str:
    if pnl is None:
        return "—"
    sign = "+" if pnl >= 0 else ""
    return f"₹{sign}{pnl:,.2f}"


def _status_icon(status: str) -> str:
    icons = {"TARGET HIT": "✅", "STOP LOSS HIT": "❌", "OPEN": "📊", "PENDING": "⏳", "EXPIRED": "💤"}
    for key, icon in icons.items():
        if key in status.upper():
            return icon
    return "❓"


def generate_report(today: str, rec_log: dict, ai_trades: dict, ai_pending: list) -> str:
    scan_time = rec_log.get("scan_time_ist", "N/A")
    total_setups = rec_log.get("total_setups_found", "N/A")
    ai_available = rec_log.get("ai_available", False)
    market_context = rec_log.get("market_context", "")
    top10 = rec_log.get("top10_recommendations", [])
    orders_placed_log = rec_log.get("orders_placed", [])

    # Counts
    placed_symbols = {p["symbol"] for p in orders_placed_log}
    target_hits = [t for t in ai_trades.values() if "TARGET HIT" in (t.get("reason") or "").upper()]
    sl_hits = [t for t in ai_trades.values() if "STOP LOSS HIT" in (t.get("reason") or "").upper()]
    still_open = [t for t in ai_trades.values() if t.get("status") == "OPEN"]
    executed_count = len(ai_trades)
    win_rate = (len(target_hits) / len(sl_hits + target_hits) * 100) if (sl_hits or target_hits) else 0
    total_pnl = sum(t.get("pnl") or 0 for t in ai_trades.values())

    lines = [
        f"# AI Trade Report — {today}",
        "",
        f"**Generated:** {ist_now().strftime('%Y-%m-%d %H:%M:%S IST')}",
        f"**Scan time:** {scan_time}",
        f"**AI available:** {'Yes' if ai_available else 'No (zone score fallback)'}",
        f"**Total setups found across Nifty 50:** {total_setups}",
        "",
    ]

    if market_context:
        lines += [f"> {market_context}", ""]

    lines += [
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total AI recommendations (top 10) | {len(top10)} |",
        f"| Pending orders placed | {len(orders_placed_log)} |",
        f"| Orders executed (became trades) | {executed_count} |",
        f"| Still pending at close | {len(ai_pending)} |",
        f"| Hit Target | {len(target_hits)} ✅ |",
        f"| Hit Stop Loss | {len(sl_hits)} ❌ |",
        f"| Still Open | {len(still_open)} 📊 |",
        f"| Win Rate | {win_rate:.1f}% |",
        f"| Total P&L | {_pnl_str(total_pnl)} |",
        "",
        "## Top 10 AI Recommendations",
        "",
        "| Rank | Symbol | Side | Entry | SL | Target | AI Prob | Order Placed | Outcome | P&L |",
        "|------|--------|------|-------|----|--------|---------|--------------|---------|-----|",
    ]

    for rec in top10:
        symbol = rec["symbol"]
        placed = "Yes" if symbol in placed_symbols else "No"
        trade = ai_trades.get(symbol)
        if trade:
            status = trade.get("status", "OPEN")
            reason = trade.get("reason", "")
            if "TARGET HIT" in reason.upper():
                outcome = "✅ Target"
            elif "STOP LOSS HIT" in reason.upper():
                outcome = "❌ SL Hit"
            else:
                outcome = "📊 Open"
            pnl = _pnl_str(trade.get("pnl"))
        elif any(o["symbol"] == symbol for o in ai_pending):
            outcome = "⏳ Pending"
            pnl = "—"
        else:
            outcome = "— Not triggered"
            pnl = "—"

        prob = rec.get("win_probability", "—")
        prob_str = f"{prob}%" if isinstance(prob, int) else str(prob)
        lines.append(
            f"| {rec['rank']} | {symbol.replace('.NS','')} | {rec['side']} "
            f"| ₹{rec['entry']:,.2f} | ₹{rec['stop_loss']:,.2f} | ₹{rec['target']:,.2f} "
            f"| {prob_str} | {placed} | {outcome} | {pnl} |"
        )

    if not top10:
        lines.append("| — | No recommendations found for today | | | | | | | | |")

    lines += [""]

    if still_open:
        lines += [
            "## Open Positions at Close",
            "",
            "| Symbol | Side | Entry | Current SL | Target | Unrealized P&L |",
            "|--------|------|-------|------------|--------|----------------|",
        ]
        for t in still_open:
            lines.append(
                f"| {t['symbol'].replace('.NS','')} | {t['side']} "
                f"| ₹{t['entry_price']:,.2f} | ₹{t.get('stop_loss',0):,.2f} "
                f"| ₹{t.get('target',0):,.2f} | — |"
            )
        lines.append("")

    lines += [
        "---",
        f"*Report generated by report_generator.py · {today}*",
    ]

    return "\n".join(lines)


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        today = sys.argv[1]
    else:
        today = ist_now().strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info(f"EOD Report Generator — {today}")
    logger.info("=" * 60)

    rec_log = load_recommendations_log(today)
    ai_trades = get_todays_ai_trades(today)
    ai_pending = get_todays_ai_pending(today)

    logger.info(
        f"Found {len(ai_trades)} AI trades and {len(ai_pending)} pending AI orders for {today}"
    )

    report = generate_report(today, rec_log, ai_trades, ai_pending)

    output_path = f"reports/{today}_ai_report.md"
    with open(output_path, "w") as f:
        f.write(report)

    logger.info(f"Report saved to {output_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
