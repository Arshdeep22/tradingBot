"""Performance metrics and portfolio snapshots - SQLite and Supabase."""
import math
from datetime import datetime


class MetricsMixin:
    """Mixin for performance metrics and portfolio. Requires BaseDB attributes."""

    def get_performance_metrics(self):
        """Calculate performance metrics from closed trades."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('status', 'CLOSED').execute())
            trades = res.data or []
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM trades WHERE status='CLOSED'")
            trades = [dict(row) for row in c.fetchall()]
            conn.close()

        if not trades:
            return {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0,
                "max_profit": 0.0, "max_loss": 0.0, "avg_win": 0.0,
                "avg_loss": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
                "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
            }

        total = len(trades)
        pnls = [t['pnl'] or 0 for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        total_pnl = sum(pnls)
        win_rate = (len(wins) / total) * 100 if total > 0 else 0

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        # Max drawdown
        peak = 0
        max_drawdown = 0
        running = 0
        for p in pnls:
            running += p
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_drawdown:
                max_drawdown = dd

        # Sharpe and Sortino (annualised, assuming ~252 trading days)
        # Use per-trade returns (pnl as fraction of initial capital) as proxy for daily returns
        n = len(pnls)
        mean_r = sum(pnls) / n
        variance = sum((p - mean_r) ** 2 for p in pnls) / n if n > 1 else 0
        std_r = math.sqrt(variance)
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

        downside = [p for p in pnls if p < 0]
        if downside:
            downside_var = sum(p ** 2 for p in downside) / n
            downside_std = math.sqrt(downside_var)
            sortino = (mean_r / downside_std * math.sqrt(252)) if downside_std > 0 else 0.0
        else:
            sortino = float('inf')

        return {
            "total_trades": total,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / total, 2) if total > 0 else 0,
            "max_profit": round(max(pnls), 2) if pnls else 0,
            "max_loss": round(min(pnls), 2) if pnls else 0,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2) if sortino != float('inf') else float('inf'),
        }

    def save_portfolio_snapshot(self, balance, portfolio_value, open_positions, total_pnl):
        """Save a portfolio snapshot for equity curve."""
        if self.use_supabase:
            data = {
                'balance': balance, 'portfolio_value': portfolio_value,
                'open_positions': open_positions, 'total_pnl': total_pnl,
                'timestamp': datetime.now().isoformat()
            }
            self.supabase_client.table('portfolio_snapshots').insert(data).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "INSERT INTO portfolio_snapshots (balance,portfolio_value,open_positions,total_pnl) "
                "VALUES (?,?,?,?)",
                (balance, portfolio_value, open_positions, total_pnl))
            conn.commit()
            conn.close()

    def get_portfolio_history(self):
        """Get portfolio history for equity curve."""
        if self.use_supabase:
            res = (self.supabase_client.table('portfolio_snapshots')
                   .select('*').order('timestamp').execute())
            return res.data or []
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM portfolio_snapshots ORDER BY timestamp ASC")
        snapshots = [dict(row) for row in c.fetchall()]
        conn.close()
        return snapshots

    def clear_all_trades(self):
        """Clear all trades, orders, and snapshots."""
        if self.use_supabase:
            self.supabase_client.table('trades').delete().neq('id', 0).execute()
            self.supabase_client.table('pending_orders').delete().neq('id', 0).execute()
            self.supabase_client.table('portfolio_snapshots').delete().neq('id', 0).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM trades")
            c.execute("DELETE FROM pending_orders")
            c.execute("DELETE FROM portfolio_snapshots")
            conn.commit()
            conn.close()