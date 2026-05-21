from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    # Iteration control
    max_iterations: int = 500
    iteration_interval_seconds: int = 0   # 0 = run as fast as possible

    # Validation tier thresholds
    tier1_days: int = 10
    tier1_min_wr: float = 55.0
    tier1_min_trades: int = 6
    tier2_days: int = 50
    tier2_min_wr: float = 70.0
    tier2_min_trades: int = 30
    tier2_min_pnl: float = 45_000.0       # rupees

    # Consecutive success requirement
    consecutive_required: int = 3

    # Composite score decision thresholds
    score_improve_threshold: float = 0.0   # must beat this to commit
    score_revert_threshold: float = -0.05  # revert immediately if worse by this much

    # Safety rails
    capital_floor_rupees: float = 70_000.0
    max_consecutive_losses: int = 7
    max_risk_pct_phase_ab: float = 1.0
    max_risk_pct_phase_c: float = 2.5
    max_drawdown_from_peak_pct: float = 20.0  # stop simulated run at this drawdown

    # Memory
    working_memory_window: int = 10        # iterations of full detail
    episodic_summarize_every: int = 10     # compress working memory every N iterations

    # Reflector thresholds
    min_confidence_for_tier2: float = 0.4
    novelty_reject_threshold: float = 0.15  # reject hypothesis if novelty < this

    # Stuck detector
    stuck_score_variance_threshold: float = 0.02
    stuck_min_unique_hypotheses: int = 4   # out of last 10 must be distinct
    stuck_phase_max_iterations: int = 25

    # Git
    agent_branch: str = "agent/optimize"
    repo_root: str = "."                   # override in tests

    # Paths
    state_file: str = "autonomous_optimizer/context/session_state.json"
    iterations_dir: str = "autonomous_optimizer/context/iterations"

    # Backtest runner
    backtest_timeout_seconds: int = 900    # 15-min hard kill

    # LLM
    llm_model: str = "anthropic--claude-4.6-opus"


DEFAULT_CONFIG = AgentConfig()
