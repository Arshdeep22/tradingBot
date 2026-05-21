# Session 04: Backtest Runner + Success Checker

**Prerequisite**: Session 01 complete (models.py, config.py exist). Session 03's SessionState used for persistence.  
**Goal**: A clean Python wrapper around `historical_trainer.runner` that (a) runs backtests in a sandboxed subprocess with a hard timeout, (b) parses results into `BacktestResult`, and (c) checks for the 3-consecutive-success stopping condition.  
**Rule**: No file exceeds 200 lines.

---

## Context

`historical_trainer/runner.py` currently calls `run_training()` which writes a JSON report to `reports/training/<run_id>_training_report.json` and logs to stdout/stderr. It accepts `--no-ai` to skip LLM calls and run faster.

The agent needs a **machine-readable** result. The cleanest approach: call `run_training()` as a subprocess, let it write its JSON report, then parse that file. The runner already calls `save_training_report()` which writes a `.json` file — that is the interface.

**Do NOT modify `historical_trainer/runner.py`** in this session. The wrapper adapts to what exists.

---

## Files to Create

### `autonomous_optimizer/backtest_runner.py`  (~160 lines)

```python
import subprocess
import json
import os
import glob
import time
import logging
from pathlib import Path

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult

logger = logging.getLogger(__name__)


class BacktestTimeoutError(RuntimeError): pass
class BacktestError(RuntimeError): pass


class BacktestRunner:
    def __init__(self, config: AgentConfig):
        self._config = config

    def run_tier1(self) -> BacktestResult:
        """
        Run a quick 10-day backtest (Tier 1 filter).
        Uses --days=10 --no-ai flags.
        Timeout: config.backtest_timeout_seconds (default 900s).
        Returns BacktestResult parsed from the JSON report.
        Raises BacktestTimeoutError if the subprocess exceeds timeout.
        Raises BacktestError if exit code != 0.
        """

    def run_tier2(self) -> BacktestResult:
        """
        Run a full 50-day backtest (Tier 2 validation).
        Uses --days=50 --no-ai flags.
        Same error handling as run_tier1.
        """

    def _run_subprocess(self, days: int) -> BacktestResult:
        """
        Internal: spawn the subprocess, wait, parse result.
        Command: python -m historical_trainer.runner --days=<days> --no-ai --json-output
        
        IMPORTANT: historical_trainer.runner does NOT currently accept --days or --json-output.
        This session must ALSO add those two flags to historical_trainer/runner.py:
          --days N    → pass last_n_days=N to run_training()  (currently hardcoded)
          --json-output → write BacktestResult-compatible JSON to a fixed path:
                         reports/training/latest_backtest_result.json
        This is the only change permitted to existing files in this session.
        """

    def _parse_report(self, report_path: str) -> BacktestResult:
        """
        Parse the JSON training report into a BacktestResult.
        
        Mapping from runner report keys:
          overall_win_rate       → win_rate
          total_pnl              → total_pnl  (rupees — requires P&L bug to be fixed in Session 07)
          total_triggered        → trade_count
          total_triggered / days → trades_per_day
          weekly_summaries       → pnl_by_week (list of weekly P&L values)
        
        Fields not in current report (compute or default):
          profit_factor          → compute from winning_pnl / abs(losing_pnl) if available, else 1.0
          sharpe_ratio           → default 0.0 until runner provides it
          max_drawdown_rupees    → default 0.0 until runner provides it
          capital_floor_hit      → default False
          consecutive_losses_max → default 0
        """
```

**Adding `--days` and `--json-output` to `historical_trainer/runner.py`**:

In `historical_trainer/runner.py`, the `main()` function already parses `sys.argv`. Add these two arguments:

```python
# In main() function of historical_trainer/runner.py, add after existing arg parsing:
days_arg = None
for arg in sys.argv[1:]:
    if arg.startswith("--days="):
        days_arg = int(arg.split("=")[1])
json_output = "--json-output" in sys.argv

# Pass days_arg to run_training():
report = run_training(quick=quick, no_ai=no_ai, last_n_days=days_arg)

# And in run_training() signature: add last_n_days: Optional[int] = None
# Use it to slice trading_days: if last_n_days: trading_days = trading_days[-last_n_days:]

# If --json-output: write a simplified JSON to reports/training/latest_backtest_result.json
if json_output:
    _write_json_result(report)
```

Add `_write_json_result(report: dict)` to `historical_trainer/runner.py` that writes:
```json
{
  "overall_win_rate": 61.2,
  "total_pnl": 18400.0,
  "total_triggered": 38,
  "days_run": 50,
  "weekly_summaries": [{"pnl": 3200.0, "win_rate": 60.0}, ...]
}
```

This change to `runner.py` must be minimal — no refactoring, no structural changes.

---

### `autonomous_optimizer/success_checker.py`  (~60 lines)

```python
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult, SessionState


class SuccessChecker:
    def __init__(self, config: AgentConfig):
        self._config = config

    def passes_tier1(self, result: BacktestResult) -> bool:
        """WR >= tier1_min_wr AND trades >= tier1_min_trades."""

    def passes_tier2(self, result: BacktestResult) -> bool:
        """WR >= tier2_min_wr AND trades >= tier2_min_trades AND pnl >= tier2_min_pnl."""

    def passes_safety_rails(self, result: BacktestResult) -> bool:
        """
        Returns False if any safety rail is triggered:
        - capital_floor_hit
        - consecutive_losses_max > config.max_consecutive_losses
        - max_drawdown_rupees > (capital_start * max_drawdown_from_peak_pct / 100)
        """

    def check_goal_achieved(self, state: SessionState) -> bool:
        """Return True if consecutive_dual_success >= consecutive_required."""
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_backtest_runner.py`  (~100 lines)

Use mocking to avoid running real backtests. The key things to test: subprocess wiring, timeout handling, JSON parsing.

```python
from unittest.mock import patch, MagicMock
import json

# Test _parse_report with a fixture JSON file
def test_parse_report_maps_fields(tmp_path):
    """Write a sample report JSON, call _parse_report, check BacktestResult fields."""
    report = {
        "overall_win_rate": 65.0,
        "total_pnl": 22000.0,
        "total_triggered": 35,
        "days_run": 50,
        "weekly_summaries": [{"pnl": 4000.0}, {"pnl": 3000.0}]
    }
    path = tmp_path / "latest_backtest_result.json"
    path.write_text(json.dumps(report))
    runner = BacktestRunner(DEFAULT_CONFIG)
    result = runner._parse_report(str(path))
    assert result.win_rate == 65.0
    assert result.total_pnl == 22000.0
    assert result.trade_count == 35
    assert len(result.pnl_by_week) == 2

def test_subprocess_timeout_raises(monkeypatch):
    """Mock subprocess.run to raise subprocess.TimeoutExpired → BacktestTimeoutError."""

def test_subprocess_nonzero_exit_raises(monkeypatch):
    """Mock subprocess.run to return returncode=1 → BacktestError."""

def test_run_tier1_uses_10_days(monkeypatch):
    """Verify the subprocess command contains --days=10."""

def test_run_tier2_uses_50_days(monkeypatch):
    """Verify the subprocess command contains --days=50."""
```

### `tests/autonomous_optimizer/test_success_checker.py`  (~70 lines)

```
test_passes_tier1_true              → WR=60, trades=8 → True (thresholds: 55, 6)
test_passes_tier1_false_wr          → WR=40, trades=8 → False
test_passes_tier1_false_trades      → WR=60, trades=3 → False
test_passes_tier2_true              → WR=72, trades=35, pnl=50000 → True
test_passes_tier2_false_pnl         → WR=72, trades=35, pnl=40000 → False
test_passes_safety_rails_cap_floor  → capital_floor_hit=True → False
test_passes_safety_rails_consec_loss → consecutive_losses_max=8 → False
test_check_goal_achieved_true       → consecutive_dual_success=3 → True
test_check_goal_achieved_false      → consecutive_dual_success=2 → False
```

### `tests/autonomous_optimizer/test_runner_integration.py`  (~50 lines)

One integration test that actually invokes `historical_trainer.runner` with `--days=10 --no-ai --json-output` and checks that the JSON output file is created and parseable. This test is **slow** (~2-5 minutes) and marked with `@pytest.mark.slow`. Skip by default:

```python
@pytest.mark.slow
def test_real_backtest_tier1_produces_parseable_json():
    """
    Actually runs the historical trainer for 10 days with no AI.
    Checks that latest_backtest_result.json is created and has required keys.
    Only run manually: pytest -m slow tests/autonomous_optimizer/test_runner_integration.py
    """
```

Run: `python -m pytest tests/autonomous_optimizer/test_backtest_runner.py tests/autonomous_optimizer/test_success_checker.py -v`  
(skip slow tests by default — run integration test separately with `-m slow`)

---

## Acceptance Criteria

1. All non-slow tests pass.
2. `BacktestRunner._parse_report()` correctly maps all available fields from the runner JSON.
3. `historical_trainer/runner.py` change is minimal: only `--days` and `--json-output` flags added, no structural changes.
4. `BacktestTimeoutError` is raised (not a generic Exception) on timeout.
5. `SuccessChecker.passes_safety_rails()` returns False for capital floor hit.
6. No file exceeds 200 lines.
