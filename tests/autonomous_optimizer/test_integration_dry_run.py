import subprocess

import pytest


@pytest.mark.integration
def test_dry_run_exits_zero():
    """
    Run: python -m autonomous_optimizer --dry-run
    Expected: process exits 0, logs "dry-run OK"
    """
    result = subprocess.run(
        ["python", "-m", "autonomous_optimizer", "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "dry-run OK" in combined, (
        f"Expected 'dry-run OK' in output\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
