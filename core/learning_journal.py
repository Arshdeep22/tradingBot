"""
Learning Journal
-----------------
Appends daily trading entries to .streamlit/learning_journal.json.
Used by nightly_optimizer.py (write) and weekly_reviewer.py (read).
Also used by bot_runner.py to pick the best-performing strategy over last N days.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

JOURNAL_PATH = ".streamlit/learning_journal.json"


class LearningJournal:
    def __init__(self, path: str = JOURNAL_PATH):
        self.path = path
        self._data: Optional[list] = None

    def _load(self) -> list:
        if self._data is not None:
            return self._data
        try:
            with open(self.path) as f:
                self._data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = []
        return self._data

    def _save(self, entries: list):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(entries, f, indent=2)
        self._data = entries

    def append_daily_entry(self, entry: dict):
        """
        Append a daily record. Expected keys:
          date, regime, strategy_used, params, trades_today, wins, losses,
          win_rate, total_pnl, feedback_improvements, notable_symbols, day_of_week
        """
        entries = self._load()
        # Deduplicate: remove any existing entry for the same date
        entries = [e for e in entries if e.get("date") != entry.get("date")]
        entry.setdefault("recorded_at", datetime.utcnow().isoformat())
        entries.append(entry)
        self._save(entries)
        logger.info(f"Learning journal: appended entry for {entry.get('date')}")

    def get_last_n_days(self, n: int = 7) -> list:
        """Return the most recent n daily entries, newest first."""
        entries = self._load()
        sorted_entries = sorted(entries, key=lambda e: e.get("date", ""), reverse=True)
        return sorted_entries[:n]

    def best_strategy_last_n_days(self, n: int = 5) -> Optional[str]:
        """
        Return the strategy with highest average win_rate over last n days.
        Returns None if fewer than 3 days of data exist (not enough signal).
        """
        recent = self.get_last_n_days(n)
        if len(recent) < 3:
            return None

        # Aggregate win rates by strategy
        strategy_stats: dict[str, list] = {}
        for entry in recent:
            strat = entry.get("strategy_used")
            wr = entry.get("win_rate", 0)
            trades = entry.get("trades_today", 0)
            if strat and trades >= 2:  # Only count days with at least 2 trades
                strategy_stats.setdefault(strat, []).append(wr)

        if not strategy_stats:
            return None

        best = max(strategy_stats, key=lambda s: sum(strategy_stats[s]) / len(strategy_stats[s]))
        avg_wr = sum(strategy_stats[best]) / len(strategy_stats[best])
        logger.info(f"Best strategy last {n} days: {best} (avg WR {avg_wr:.1f}%)")
        return best

    def symbol_performance(self) -> dict:
        """Return per-symbol win rate aggregated across all entries."""
        entries = self._load()
        symbol_stats: dict[str, dict] = {}
        for entry in entries:
            for symbol, outcome in (entry.get("notable_symbols") or {}).items():
                if symbol not in symbol_stats:
                    symbol_stats[symbol] = {"wins": 0, "losses": 0}
                if outcome == "win":
                    symbol_stats[symbol]["wins"] += 1
                elif outcome == "loss":
                    symbol_stats[symbol]["losses"] += 1

        result = {}
        for sym, stats in symbol_stats.items():
            total = stats["wins"] + stats["losses"]
            result[sym] = {
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(stats["wins"] / total * 100, 1) if total > 0 else 0.0,
            }
        return result

    def rolling_win_rate(self, strategy_name: Optional[str] = None, days: int = 10) -> float:
        """
        Compute rolling win rate across recent days.
        If strategy_name is given, filter to entries using that strategy.
        """
        recent = self.get_last_n_days(days)
        if strategy_name:
            recent = [e for e in recent if e.get("strategy_used") == strategy_name]

        if not recent:
            return 0.0

        total_wins = sum(e.get("wins", 0) for e in recent)
        total_trades = sum(e.get("trades_today", 0) for e in recent)
        return round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0.0

    def day_of_week_stats(self) -> dict:
        """Return average win rate by day of week."""
        entries = self._load()
        dow_stats: dict[str, list] = {}
        for entry in entries:
            dow = entry.get("day_of_week")
            wr = entry.get("win_rate", 0)
            trades = entry.get("trades_today", 0)
            if dow and trades >= 2:
                dow_stats.setdefault(dow, []).append(wr)

        return {
            dow: round(sum(wrs) / len(wrs), 1)
            for dow, wrs in dow_stats.items()
            if wrs
        }

    def all_entries(self) -> list:
        return self._load()
