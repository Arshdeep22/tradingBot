# Session 07: Main Agent Loop + Integration

**Prerequisite**: Sessions 01–06 complete. All modules exist and their unit tests pass.  
**Goal**: Wire all modules into the main `agent.py` loop, complete `__main__.py`, add a start script, and run one full dry-run iteration end-to-end.  
**Rule**: No file exceeds 200 lines. If `agent.py` approaches the limit, extract helper methods into `autonomous_optimizer/loop_helpers.py`.

---

## Files to Create / Complete

### `autonomous_optimizer/agent.py`  (~190 lines)

The main orchestration loop. Follows the 10-step pattern from the design doc.

```python
import logging
import time
from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.session_manager import SessionManager
from autonomous_optimizer.git_ops import GitOps
from autonomous_optimizer.code_editor import CodeEditor
from autonomous_optimizer.backtest_runner import BacktestRunner, BacktestTimeoutError
from autonomous_optimizer.success_checker import SuccessChecker
from autonomous_optimizer.memory.working_memory import IterationRecord
from autonomous_optimizer.models import composite_score
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.llm.observer import Observer
from autonomous_optimizer.llm.analyzer import Analyzer
from autonomous_optimizer.llm.strategist import Strategist
from autonomous_optimizer.llm.reflector import Reflector
from autonomous_optimizer.llm.critic import Critic
from autonomous_optimizer.llm.coder import Coder

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, config: AgentConfig):
        self._config = config
        self._session = SessionManager(config)
        self._git = GitOps(config)
        self._editor = CodeEditor()
        self._runner = BacktestRunner(config)
        self._checker = SuccessChecker(config)
        llm = AgentLLMClient(config)
        self._observer = Observer(config, self._git)
        self._analyzer = Analyzer(config, llm)
        self._strategist = Strategist(config, llm, self._session.long_term)
        self._reflector = Reflector(config)
        self._critic = Critic(config, self._editor)
        self._coder = Coder(config, llm, self._editor)

    def run(self, override_iterations: int = None,
            override_phase: str = None) -> None:
        """
        Main loop. Runs until success or max_iterations.
        """
        self._session.load()
        if override_phase:
            self._session.state.phase = override_phase
        self._git.ensure_branch()

        max_iters = override_iterations or self._config.max_iterations

        while self._session.state.iteration < max_iters:
            n = self._session.state.iteration + 1
            logger.info(f"[Iteration {n}] Phase {self._session.state.phase}")
            self._run_one_iteration(n)

            if self._checker.check_goal_achieved(self._session.state):
                logger.info("GOAL ACHIEVED — 3 consecutive dual-success runs!")
                self._git.tag("goal-achieved")
                break

    def _run_one_iteration(self, n: int) -> None:
        """
        Single iteration: observe → analyze → strategize → reflect →
        critic → implement → test → validate → commit_or_revert → update.
        """
        # Step 1: OBSERVE
        # Run Tier 1 backtest first to have something to observe
        # (On iteration 1, use most recent training report if no backtest yet)
        tier1_result = self._safe_run_tier1()
        observation = self._observer.observe(n, tier1_result, test_output="")

        # Step 2: ANALYZE
        context = self._session.thinker_context()
        root_cause = self._analyzer.analyze(observation, context)
        logger.info(f"[Iteration {n}] Root cause: {root_cause.category} (conf={root_cause.confidence:.2f})")

        # Step 3: STRATEGIZE
        stuck_mode = _check_stuck(self._session.state, self._config)
        hypothesis = self._strategist.strategize(root_cause, context, explore=stuck_mode)
        logger.info(f"[Iteration {n}] Hypothesis: {hypothesis.slug}")

        # Step 4: REFLECT
        reflection = self._reflector.reflect(hypothesis, root_cause, self._session.state)
        logger.info(f"[Iteration {n}] Confidence={reflection.confidence:.2f} stuck={reflection.stuck} mode={reflection.mode}")

        # Step 5: GENERATE CODE
        proposed = self._coder.generate_changes(hypothesis)

        # Step 6: CRITIC
        critic_result = self._critic.review(hypothesis, proposed)
        if not critic_result.approved:
            logger.warning(f"[Iteration {n}] Critic blocked: {critic_result.reason}")
            self._session.state.iteration += 1
            self._session.save()
            return

        # Step 7: IMPLEMENT — snapshot first
        self._git.create_snapshot(f"pre-iter-{n}")
        applied = self._coder.apply_changes(proposed)

        # Step 8: VALIDATE
        reverted = False
        tier2_result = None
        prev_score = self._session.state.best_composite

        if reflection.gate_tier2 and self._checker.passes_tier1(tier1_result):
            try:
                tier2_result = self._runner.run_tier2()
            except BacktestTimeoutError:
                logger.error(f"[Iteration {n}] Tier 2 timed out — reverting")
                self._git.revert_to_snapshot()
                reverted = True

        if tier2_result and not reverted:
            new_score = composite_score(tier2_result)
            if new_score < prev_score + self._config.score_improve_threshold:
                logger.info(f"[Iteration {n}] Score regressed ({new_score:.3f} vs {prev_score:.3f}) — reverting")
                self._git.revert_to_snapshot()
                reverted = True
            else:
                # Step 9: COMMIT
                msg = _format_commit(n, self._session.state.phase, tier2_result, new_score, hypothesis.slug)
                self._git.commit(msg)
                self._session.state.best_composite = new_score
                if tier2_result.win_rate > self._session.state.best_win_rate:
                    self._session.state.best_win_rate = tier2_result.win_rate
                if self._checker.passes_tier2(tier2_result):
                    count = self._session.record_success_run(tier2_result)
                    logger.info(f"[Iteration {n}] DUAL SUCCESS {count}/{self._config.consecutive_required}")
                else:
                    self._session.reset_consecutive_success()

        # Step 10: UPDATE STATE
        result_to_record = tier2_result or tier1_result
        record = IterationRecord(
            iteration=n, phase=self._session.state.phase,
            hypothesis_slug=hypothesis.slug,
            hypothesis_description=hypothesis.description,
            root_cause_category=root_cause.category,
            win_rate=result_to_record.win_rate,
            pnl=result_to_record.total_pnl,
            trade_count=result_to_record.trade_count,
            composite_score=composite_score(result_to_record),
            reverted=reverted,
        )
        self._session.record_iteration(record)
        self._session.maybe_compress()
        self._session.state.iteration += 1
        self._session.save()
        _maybe_advance_phase(self._session, self._config)
```

If `agent.py` approaches 200 lines, extract `_check_stuck`, `_format_commit`, `_maybe_advance_phase`, and `_safe_run_tier1` into:

### `autonomous_optimizer/loop_helpers.py`  (~80 lines)

```python
def _check_stuck(state, config) -> bool:
    """Return True if any stuck signal fires."""

def _format_commit(n, phase, result, score, slug) -> str:
    """Format the semantic commit message string."""

def _maybe_advance_phase(session, config) -> None:
    """Advance phase if gate passed or phase exhausted."""

def _safe_run_tier1(runner, last_report_path) -> BacktestResult:
    """Run Tier1 or load most recent report if it's iteration 1 with no prior result."""
```

---

### `autonomous_optimizer/__main__.py`  (complete — replaces stub from Session 01, ~60 lines)

```python
"""Entry point: python -m autonomous_optimizer [--dry-run] [--iterations N] [--phase A|B|C]"""
import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args():
    p = argparse.ArgumentParser(description="Autonomous Trading Bot Optimizer")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--phase", choices=["A", "B", "C"], default=None)
    return p.parse_args()


def main():
    args = _parse_args()

    if args.dry_run:
        from autonomous_optimizer.agent import Agent
        from autonomous_optimizer.config import DEFAULT_CONFIG
        agent = Agent(DEFAULT_CONFIG)
        logger.info("dry-run OK — Agent constructed successfully")
        sys.exit(0)

    from autonomous_optimizer.agent import Agent
    from autonomous_optimizer.config import DEFAULT_CONFIG
    agent = Agent(DEFAULT_CONFIG)
    agent.run(
        override_iterations=args.iterations,
        override_phase=args.phase,
    )


if __name__ == "__main__":
    main()
```

---

### `autonomous_optimizer/scripts/start.sh`  (~20 lines)

```bash
#!/usr/bin/env bash
# Start the autonomous optimizer in a persistent tmux session.
# Usage: ./autonomous_optimizer/scripts/start.sh [--dry-run]

SESSION="trading-agent"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session '$SESSION' already running. Attach: tmux attach -t $SESSION"
    exit 0
fi

cd "$REPO_ROOT" || exit 1
source .venv/bin/activate 2>/dev/null || true

tmux new-session -d -s "$SESSION" \
    "python -m autonomous_optimizer $*; echo 'AGENT STOPPED — press any key'; read"

echo "Started in tmux session '$SESSION'"
echo "Attach: tmux attach -t $SESSION"
echo "Detach: Ctrl+B then D"
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_agent_loop.py`  (~120 lines)

Mock all external calls (LLM, backtest runner, git). Verify the loop logic: correct sequencing, revert on regression, success tracking.

```python
@pytest.fixture
def mock_agent(tmp_path):
    """Agent with all external dependencies mocked."""
    # Mock: BacktestRunner.run_tier1/run_tier2 → return pre-built BacktestResult
    # Mock: AgentLLMClient.call → return canned responses
    # Mock: GitOps → no-op all git commands
    # Use tmp_path as repo_root
    ...

def test_one_iteration_commits_on_improvement(mock_agent):
    """
    Mocks: tier2 returns score 0.6, prev best was 0.3.
    Expected: git.commit called, session.state.best_composite updated.
    """

def test_one_iteration_reverts_on_regression(mock_agent):
    """
    Mocks: tier2 returns score 0.2, prev best was 0.5.
    Expected: git.revert_to_snapshot called, session.state.best_composite unchanged.
    """

def test_critic_block_skips_implementation(mock_agent):
    """
    Mocks: Critic.review returns approved=False.
    Expected: Coder.apply_changes never called, iteration still increments.
    """

def test_goal_achieved_stops_loop(mock_agent):
    """
    Mocks: 3 consecutive tier2 passes (all criteria met).
    Expected: agent.run() returns after 3 iterations, "goal-achieved" tag set.
    """

def test_timeout_reverts(mock_agent):
    """
    Mocks: tier2 raises BacktestTimeoutError.
    Expected: git.revert_to_snapshot called.
    """

def test_session_saved_every_iteration(mock_agent):
    """
    Run 3 iterations.
    Expected: session.save() called 3 times.
    """
```

### `tests/autonomous_optimizer/test_loop_helpers.py`  (~50 lines)

```
test_format_commit_matches_regex    → output matches _COMMIT_RE from git_ops.py
test_check_stuck_returns_true       → 10 identical scores → True
test_check_stuck_returns_false      → varying scores → False
test_maybe_advance_phase_a_to_b     → meets Phase A gate → state.phase becomes "B"
test_maybe_advance_no_change        → below gate → phase unchanged
```

---

## Integration Test (run manually)

### `tests/autonomous_optimizer/test_integration_dry_run.py`

```python
@pytest.mark.integration
def test_dry_run_exits_zero():
    """
    Run: python -m autonomous_optimizer --dry-run
    Expected: process exits 0, logs "dry-run OK"
    """
    import subprocess
    result = subprocess.run(
        ["python", "-m", "autonomous_optimizer", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "dry-run OK" in result.stderr or "dry-run OK" in result.stdout
```

Run: `python -m pytest tests/autonomous_optimizer/test_agent_loop.py tests/autonomous_optimizer/test_loop_helpers.py -v`  
Integration: `python -m pytest -m integration tests/autonomous_optimizer/test_integration_dry_run.py -v`

---

## Acceptance Criteria

1. All unit tests pass.
2. `python -m autonomous_optimizer --dry-run` exits 0.
3. One complete mocked iteration runs without errors: observe → analyze → strategize → reflect → code → critic → implement → validate → commit/revert → state update.
4. Agent resumes correctly from saved state after simulated restart (load → run → saves iteration N+1).
5. `scripts/start.sh` starts a tmux session and the process is visible via `tmux ls`.
6. No file exceeds 200 lines (split into `loop_helpers.py` if needed).
7. `git.tag("goal-achieved")` is called when `consecutive_dual_success == 3`.
