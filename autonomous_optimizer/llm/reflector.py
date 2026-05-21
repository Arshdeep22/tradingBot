from __future__ import annotations

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import ReflectionResult, Hypothesis, SessionState
from autonomous_optimizer.memory.embeddings import most_similar_past


class Reflector:
    def __init__(self, config: AgentConfig):
        self._config = config

    def reflect(self, hypothesis: Hypothesis, root_cause,
                state: SessionState) -> ReflectionResult:
        past_signal = self._past_similar_outcome_signal(hypothesis, state)
        confidence = (
            0.4 * root_cause.confidence
            + 0.4 * hypothesis.novelty_score
            + 0.2 * past_signal
        )
        confidence = max(0.0, min(1.0, confidence))

        stuck = self._detect_stuck(state)
        mode = "explore" if stuck else "exploit"
        gate_tier2 = confidence >= self._config.min_confidence_for_tier2
        reason = self._stuck_reason(state) if stuck else ""

        return ReflectionResult(
            confidence=confidence,
            stuck=stuck,
            mode=mode,
            gate_tier2=gate_tier2,
            reason=reason,
        )

    def _detect_stuck(self, state: SessionState) -> bool:
        trajectory = state.composite_score_trajectory[-10:]
        if len(trajectory) >= 2 and self._variance(trajectory) < self._config.stuck_score_variance_threshold:
            return True

        tried = state.approaches_tried[-10:]
        unique_slugs = {a.get("slug", "") for a in tried if a.get("slug")}
        if len(tried) >= 10 and len(unique_slugs) < self._config.stuck_min_unique_hypotheses:
            return True

        if (state.iteration > self._config.stuck_phase_max_iterations
                and state.consecutive_dual_success == 0):
            return True

        rejections = [a for a in state.approaches_tried[-10:] if a.get("critic_rejected")]
        if len(state.approaches_tried) >= 10 and len(rejections) / 10 > 0.6:
            return True

        return False

    def _stuck_reason(self, state: SessionState) -> str:
        trajectory = state.composite_score_trajectory[-10:]
        if len(trajectory) >= 2 and self._variance(trajectory) < self._config.stuck_score_variance_threshold:
            return "score_oscillation"
        tried = state.approaches_tried[-10:]
        unique_slugs = {a.get("slug", "") for a in tried if a.get("slug")}
        if len(tried) >= 10 and len(unique_slugs) < self._config.stuck_min_unique_hypotheses:
            return "hypothesis_cycling"
        if (state.iteration > self._config.stuck_phase_max_iterations
                and state.consecutive_dual_success == 0):
            return "phase_exhausted"
        return "critic_rejection_rate"

    def _past_similar_outcome_signal(self, hypothesis: Hypothesis,
                                      state: SessionState) -> float:
        if not state.hypothesis_embeddings:
            signal = 0.0
            return (signal + 0.5) / 1.0

        past = most_similar_past(hypothesis.description, state.hypothesis_embeddings)
        if past is None:
            signal = 0.0
        else:
            result = past.get("result", "").lower()
            if "improv" in result:
                signal = 0.5
            elif "degrad" in result or "fail" in result:
                signal = -0.5
            else:
                signal = 0.0

        return (signal + 0.5) / 1.0

    def _variance(self, values: list[float]) -> float:
        if len(values) <= 1:
            return 0.0
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)
