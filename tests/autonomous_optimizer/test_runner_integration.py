"""
Integration test: actually invokes historical_trainer.runner with --days=10 --no-ai --json-output.
Marked @pytest.mark.slow — skip by default.
Run manually: pytest -m slow tests/autonomous_optimizer/test_runner_integration.py
"""
import json
import os
import subprocess
import sys

import pytest


REQUIRED_KEYS = {"overall_win_rate", "total_pnl", "total_triggered", "days_run", "weekly_summaries"}
RESULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reports", "training", "latest_backtest_result.json",
)


@pytest.mark.slow
def test_real_backtest_tier1_produces_parseable_json():
    """
    Actually runs the historical trainer for 10 days with no AI.
    Checks that latest_backtest_result.json is created and has required keys.
    Only run manually: pytest -m slow tests/autonomous_optimizer/test_runner_integration.py
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    result = subprocess.run(
        [sys.executable, "-m", "historical_trainer.runner", "--days=10", "--no-ai", "--json-output"],
        cwd=repo_root,
        timeout=600,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Runner failed:\n{result.stderr[-3000:]}"
    assert os.path.exists(RESULT_PATH), "latest_backtest_result.json was not created"

    with open(RESULT_PATH) as f:
        data = json.load(f)

    missing = REQUIRED_KEYS - set(data.keys())
    assert not missing, f"Missing keys in output: {missing}"
    assert isinstance(data["overall_win_rate"], (int, float))
    assert isinstance(data["total_triggered"], int)
    assert isinstance(data["weekly_summaries"], list)
    assert data["days_run"] <= 10
