import json
import os
import subprocess
import sys
from pathlib import Path

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.git_ops import GitOps
from autonomous_optimizer.models import BacktestResult, Observation

_LATEST_REPORT = os.path.join("reports", "training", "latest_backtest_result.json")
_TRAINING_DIR = os.path.join("reports", "training")
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class Observer:
    def __init__(self, config: AgentConfig, git_ops: GitOps):
        self._config = config
        self._git = git_ops

    def observe(self, iteration: int, backtest_result: BacktestResult,
                test_output: str) -> Observation:
        changed_files = self._recently_changed_files()
        return Observation(
            backtest=backtest_result,
            code_diff=self._git.current_diff("HEAD"),
            test_output=test_output,
            anomaly_flags=self._detect_anomalies(backtest_result),
            data_freshness=self._data_freshness(),
            regime_state=self._regime_state(),
            git_blame_recent=self._git.recent_blame(changed_files),
            iteration=iteration,
        )

    def _detect_anomalies(self, result: BacktestResult) -> list[str]:
        flags: list[str] = []

        if result.trade_count == 0:
            flags.append("NO_TRADES: zero trades generated")
            return flags

        if result.win_rate == 0.0:
            flags.append("ALL_LOSSES: win_rate == 0.0")

        if result.trades_per_day > self._config.max_trades_per_day:
            flags.append(
                f"OVERTRADING: {result.trades_per_day:.1f} trades/day exceeds "
                f"max {self._config.max_trades_per_day} — setup criteria too loose"
            )

        if result.pnl_by_week and result.total_pnl != 0.0:
            max_week = max(abs(w) for w in result.pnl_by_week)
            if max_week > 0.8 * abs(result.total_pnl):
                pct = int(100 * max_week / abs(result.total_pnl))
                flags.append(f"FRAGILE: {pct}% of P&L in one week")

        return flags

    def _data_freshness(self) -> dict:
        training_dir = Path(self._config.repo_root) / _TRAINING_DIR
        if not training_dir.exists():
            return {"last_modified": None, "file_count": 0}

        reports = sorted(training_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not reports:
            return {"last_modified": None, "file_count": 0}

        latest = reports[-1]
        return {
            "last_modified": latest.stat().st_mtime,
            "latest_file": latest.name,
            "file_count": len(reports),
        }

    def _regime_state(self) -> str:
        report_path = Path(self._config.repo_root) / _LATEST_REPORT
        if not report_path.exists():
            return "unknown"
        try:
            with report_path.open(encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("regime", data.get("market_regime", "unknown")))
        except (json.JSONDecodeError, OSError):
            return "unknown"

    def _recently_changed_files(self) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~3", "HEAD"],
                cwd=self._config.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                creationflags=_CREATIONFLAGS,
            )
            return [f for f in result.stdout.splitlines() if f.strip()]
        except OSError:
            return []
