"""Trade CRUD operations - SQLite and Supabase."""
from datetime import datetime


class TradesMixin:
    """Mixin for trade operations. Requires BaseDB attributes."""

    def save_trade(self, symbol, side, quantity, entry_price,
                   stop_loss=0.0, target=0.0, strategy="", reason=""):
        """Save a new trade. Returns trade ID."""
        if self.use_supabase:
            data = {
                'symbol': symbol, 'side': side, 'quantity': quantity,
                'entry_price': entry_price, 'stop_loss': stop_loss,
                'target': target, 'strategy': strategy, 'reason': reason,
                'status': 'OPEN', 'entry_time': datetime.now().isoformat(),
                'created_at': datetime.now().isoformat()
            }
            res = self.supabase_client.table('trades').insert(data).execute()
            return res.data[0]['id'] if res.data else 0

        conn = self._get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO trades (symbol,side,quantity,entry_price,stop_loss,"
            "target,strategy,reason,status,entry_time) "
            "VALUES (?,?,?,?,?,?,?,?,'OPEN',?)",
            (symbol, side, quantity, entry_price, stop_loss, target,
             strategy, reason, datetime.now().isoformat()))
        tid = c.lastrowid
        conn.commit()
        conn.close()
        return tid

    def close_trade(self, symbol, exit_price, pnl=0.0, reason=""):
        """Close an open trade by symbol."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('symbol', symbol).eq('status', 'OPEN')
                   .order('entry_time', desc=True).limit(1).execute())
            if not res.data:
                return
            trade = res.data[0]
            ep, qty, side = trade['entry_price'], trade['quantity'], trade['side']
            if pnl == 0.0:
                pnl = (exit_price - ep) * qty if side == "BUY" else (ep - exit_price) * qty
            pnl_pct = ((exit_price - ep) / ep) * 100
            if side == "SELL":
                pnl_pct = -pnl_pct
            self.supabase_client.table('trades').update({
                'exit_price': exit_price, 'pnl': round(pnl, 2),
                'pnl_percent': round(pnl_pct, 4), 'status': 'CLOSED',
                'exit_time': datetime.now().isoformat(),
                'reason': (trade.get('reason', '') or '') + ' | Exit: ' + reason
            }).eq('id', trade['id']).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "SELECT id,entry_price,quantity,side FROM trades "
                "WHERE symbol=? AND status='OPEN' ORDER BY entry_time DESC LIMIT 1",
                (symbol,))
            trade = c.fetchone()
            if not trade:
                conn.close()
                return
            tid, ep, qty, side = trade['id'], trade['entry_price'], trade['quantity'], trade['side']
            if pnl == 0.0:
                pnl = (exit_price - ep) * qty if side == "BUY" else (ep - exit_price) * qty
            pnl_pct = ((exit_price - ep) / ep) * 100
            if side == "SELL":
                pnl_pct = -pnl_pct
            c.execute(
                "UPDATE trades SET exit_price=?, pnl=?, pnl_percent=?, "
                "status='CLOSED', exit_time=?, reason=reason||' | Exit: '||? WHERE id=?",
                (exit_price, pnl, pnl_pct, datetime.now().isoformat(), reason, tid))
            conn.commit()
            conn.close()

    def get_all_trades(self):
        """Get all trades."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').order('entry_time', desc=True).execute())
            return res.data or []
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM trades ORDER BY entry_time DESC")
        trades = [dict(row) for row in c.fetchall()]
        conn.close()
        return trades

    def get_open_trades(self):
        """Get open trades."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('status', 'OPEN')
                   .order('entry_time', desc=True).execute())
            return res.data or []
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_time DESC")
        trades = [dict(row) for row in c.fetchall()]
        conn.close()
        return trades

    def get_closed_trades(self):
        """Get closed trades."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('status', 'CLOSED')
                   .order('exit_time', desc=True).execute())
            return res.data or []
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM trades WHERE status='CLOSED' ORDER BY exit_time DESC")
        trades = [dict(row) for row in c.fetchall()]
        conn.close()
        return trades

    def get_trades_by_strategy(self, strategy):
        """Get trades filtered by strategy."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('strategy', strategy)
                   .order('entry_time', desc=True).execute())
            return res.data or []
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM trades WHERE strategy=? ORDER BY entry_time DESC", (strategy,))
        trades = [dict(row) for row in c.fetchall()]
        conn.close()
        return trades