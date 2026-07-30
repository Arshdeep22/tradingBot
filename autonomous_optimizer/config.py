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

    # Quality guard: reject any result that averaged more than this many trades
    # per day — prevents the agent from loosening setup criteria just to hit
    # trade-count minimums. ~3/day ≈ 150 trades over 50 days is already generous.
    max_trades_per_day: float = 3.0

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
    # Operate directly on `main` — the agent commits and reverts on this branch.
    # (Snapshots + composite-score gate + revert-on-regression still protect
    #  against bad code.)
    agent_branch: str = "main"
    repo_root: str = "."                   # override in tests

    # Paths
    # NOTE: state_file / iterations_dir are DEPRECATED. All agent-owned state
    # (session, memories, logs, tool traces) now lives in the SQLite DB at
    # `agent_db_path`. These fields are kept only so any legacy code that
    # still references them keeps importing cleanly.
    state_file: str = "autonomous_optimizer/context/session_state.json"
    iterations_dir: str = "autonomous_optimizer/context/iterations"
    agent_db_path: str = "database/agent.db"

    # Backtest runner
    backtest_timeout_seconds: int = 900    # 15-min hard kill

    # Two-agent architecture:
    # When True, the optimizer drives the in-process Trading Agent (with
    # hot-reload) via `TradingBotTool` — every LLM decision + tool call
    # of the trading bot is captured in the DB with agent='trading_bot'.
    # When False, it falls back to the legacy subprocess-based
    # `historical_trainer.runner` invocation.
    use_trading_agent: bool = True

    # Which symbols the trading agent runs on when driven by the
    # optimizer. Empty → use whatever `trading_agent_config.symbols` holds.
    trading_agent_symbols: list = None       # type: ignore[assignment]

    # LLM
    # NOTE: claude-4.8-opus exists in this tenant but is heavily rate-limited
    # (429 on almost every call). claude-4.7-opus = same capability tier with
    # much better throughput → recommended default. Override via AICORE_MODEL.
    llm_model: str = "anthropic--claude-4.7-opus"


DEFAULT_CONFIG = AgentConfig()
