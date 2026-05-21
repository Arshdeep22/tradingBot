from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import BacktestResult, SessionState


class SuccessChecker:
    def __init__(self, config: AgentConfig):
        self._config = config

    def passes_tier1(self, result: BacktestResult) -> bool:
        """WR >= tier1_min_wr AND trades >= tier1_min_trades."""
        return (
            result.win_rate >= self._config.tier1_min_wr
            and result.trade_count >= self._config.tier1_min_trades
        )

    def passes_tier2(self, result: BacktestResult) -> bool:
        """WR >= tier2_min_wr AND trades >= tier2_min_trades AND pnl >= tier2_min_pnl."""
        return (
            result.win_rate >= self._config.tier2_min_wr
            and result.trade_count >= self._config.tier2_min_trades
            and result.total_pnl >= self._config.tier2_min_pnl
        )

    def passes_safety_rails(self, result: BacktestResult) -> bool:
        """
        Returns False if any safety rail is triggered:
        - capital_floor_hit
        - consecutive_losses_max > config.max_consecutive_losses
        - max_drawdown_rupees > (capital_floor_rupees * max_drawdown_from_peak_pct / 100)
        """
        if result.capital_floor_hit:
            return False
        if result.consecutive_losses_max > self._config.max_consecutive_losses:
            return False
        drawdown_limit = (
            self._config.capital_floor_rupees
            * self._config.max_drawdown_from_peak_pct
            / 100.0
        )
        if result.max_drawdown_rupees > drawdown_limit:
            return False
        return True

    def check_goal_achieved(self, state: SessionState) -> bool:
        """Return True if consecutive_dual_success >= consecutive_required."""
        return state.consecutive_dual_success >= self._config.consecutive_required
