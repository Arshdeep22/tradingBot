import logging

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
from autonomous_optimizer.loop_helpers import (
    _check_stuck, _format_commit, _maybe_advance_phase, _safe_run_tier1,
)

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
        """Main loop. Runs until success or max_iterations."""
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
        critic → implement → validate → commit_or_revert → update.
        """
        # Step 1: OBSERVE
        tier1_result = _safe_run_tier1(self._runner)
        observation = self._observer.observe(n, tier1_result, test_output="")

        # Step 2: ANALYZE
        context = self._session.thinker_context()
        root_cause = self._analyzer.analyze(observation, context)
        logger.info(
            f"[Iteration {n}] Root cause: {root_cause.category} "
            f"(conf={root_cause.confidence:.2f})"
        )

        # Step 3: STRATEGIZE
        stuck_mode = _check_stuck(self._session.state, self._config)
        hypothesis = self._strategist.strategize(root_cause, context, explore=stuck_mode)
        logger.info(f"[Iteration {n}] Hypothesis: {hypothesis.slug}")

        # Step 4: REFLECT
        reflection = self._reflector.reflect(hypothesis, root_cause, self._session.state)
        logger.info(
            f"[Iteration {n}] Confidence={reflection.confidence:.2f} "
            f"stuck={reflection.stuck} mode={reflection.mode}"
        )

        # Step 5: GENERATE CODE
        proposed = self._coder.generate_changes(hypothesis)

        # Step 6: CRITIC
        critic_result = self._critic.review(hypothesis, proposed)
        if not critic_result.approved:
            logger.warning(f"[Iteration {n}] Critic blocked: {critic_result.reason}")
            self._session.long_term.block_approach(hypothesis.description)
            self._session.long_term.add_hypothesis_embedding(
                hypothesis.slug, hypothesis.description, "critic_rejected", n
            )
            self._session.state.approaches_tried.append({
                "slug": hypothesis.slug,
                "description": hypothesis.description,
                "iteration": n,
                "result": "critic_rejected",
                "reverted": False,
            })
            self._session.state.iteration += 1
            self._session.save()
            return

        # Step 7: IMPLEMENT — snapshot first
        self._git.create_snapshot(f"pre-iter-{n}")
        self._coder.apply_changes(proposed)

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
                logger.info(
                    f"[Iteration {n}] Score regressed "
                    f"({new_score:.3f} vs {prev_score:.3f}) — reverting"
                )
                self._git.revert_to_snapshot()
                reverted = True
            else:
                # Step 9: COMMIT
                msg = _format_commit(
                    n, self._session.state.phase, tier2_result, new_score, hypothesis.slug
                )
                self._git.commit(msg)
                self._session.state.best_composite = new_score
                if tier2_result.win_rate > self._session.state.best_win_rate:
                    self._session.state.best_win_rate = tier2_result.win_rate
                if self._checker.passes_tier2(tier2_result):
                    count = self._session.record_success_run(tier2_result)
                    logger.info(
                        f"[Iteration {n}] DUAL SUCCESS "
                        f"{count}/{self._config.consecutive_required}"
                    )
                else:
                    self._session.reset_consecutive_success()

        # Step 10: UPDATE STATE
        result_to_record = tier2_result or tier1_result
        outcome = (
            "improved" if (tier2_result and not reverted) else
            "degraded" if reverted else
            "neutral"
        )
        self._session.state.approaches_tried.append({
            "slug": hypothesis.slug,
            "description": hypothesis.description,
            "iteration": n,
            "result": outcome,
            "reverted": reverted,
        })
        self._session.long_term.add_hypothesis_embedding(
            hypothesis.slug, hypothesis.description, outcome, n
        )
        record = IterationRecord(
            iteration=n,
            phase=self._session.state.phase,
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
        new_phase = _maybe_advance_phase(self._session, tier2_result)
        if new_phase:
            self._git.tag(f"phase-{new_phase.lower()}-start")
