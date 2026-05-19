"""Trade CRUD operations - SQLite and Supabase."""
from datetime import datetime


class TradesMixin:
    """Mixin for trade operations. Requires BaseDB attributes."""

    def save_trade(self, symbol, side, quantity, entry_price,
                   stop_loss=0.0, target=0.0, strategy="", reason="",
                   base_candles=2, current_sl=None):
        """Save a new trade. Returns trade ID."""
        current_sl = current_sl if current_sl is not None else stop_loss
        if self.use_supabase:
            data = {
                'symbol': symbol, 'side': side, 'quantity': quantity,
                'entry_price': entry_price, 'stop_loss': stop_loss,
                'target': target, 'strategy': strategy, 'reason': reason,
                'status': 'OPEN', 'entry_time': datetime.now().isoformat(),
                'created_at': datetime.now().isoformat(),
                'current_sl': current_sl, 'base_candles': base_candles,
                'breakeven_applied': 0, 'partial_taken': 0,
            }
            res = self.supabase_client.table('trades').insert(data).execute()
            return res.data[0]['id'] if res.data else 0

        conn = self._get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO trades (symbol,side,quantity,entry_price,stop_loss,"
            "target,strategy,reason,status,entry_time,current_sl,base_candles,"
            "breakeven_applied,partial_taken) "
            "VALUES (?,?,?,?,?,?,?,?,'OPEN',?,?,?,0,0)",
            (symbol, side, quantity, entry_price, stop_loss, target,
             strategy, reason, datetime.now().isoformat(), current_sl, base_candles))
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

    def delete_trade(self, trade_id):
        """Delete a specific trade by ID."""
        trade_id = int(trade_id)
        if self.use_supabase:
            self.supabase_client.table('trades').delete().eq('id', trade_id).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM trades WHERE id=?", (trade_id,))
            conn.commit()
            conn.close()

    def update_trade_stop_loss(self, trade_id: int, new_stop_loss: float):
        """Update the stop loss of an open trade (used for trailing stop / breakeven)."""
        trade_id = int(trade_id)
        if self.use_supabase:
            self.supabase_client.table('trades').update(
                {'stop_loss': new_stop_loss}
            ).eq('id', trade_id).eq('status', 'OPEN').execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "UPDATE trades SET stop_loss=? WHERE id=? AND status='OPEN'",
                (new_stop_loss, trade_id))
            conn.commit()
            conn.close()

    def get_closed_trades_for_date(self, date_str: str):
        """Get closed trades where exit_time falls on the given date (YYYY-MM-DD)."""
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('status', 'CLOSED')
                   .gte('exit_time', f"{date_str}T00:00:00")
                   .lt('exit_time', f"{date_str}T23:59:59")
                   .execute())
            return res.data or []
        conn = self._get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM trades WHERE status='CLOSED' AND exit_time LIKE ?",
            (f"{date_str}%",))
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

    # ── Bot runner / trade management ────────────────────────────────────────

    def close_trade_by_id(self, trade_id: int, exit_price: float, reason: str = ""):
        """Close a specific trade by ID (used by bot_runner)."""
        trade_id = int(trade_id)
        if self.use_supabase:
            res = (self.supabase_client.table('trades')
                   .select('*').eq('id', trade_id).eq('status', 'OPEN').execute())
            if not res.data:
                return
            t = res.data[0]
            ep, qty, side = t['entry_price'], t['quantity'], t['side']
            pnl = (exit_price - ep) * qty if side == "BUY" else (ep - exit_price) * qty
            pnl_pct = ((exit_price - ep) / ep * 100) * (1 if side == "BUY" else -1)
            self.supabase_client.table('trades').update({
                'exit_price': exit_price, 'pnl': round(pnl, 2),
                'pnl_percent': round(pnl_pct, 4), 'status': 'CLOSED',
                'exit_time': datetime.now().isoformat(),
                'reason': (t.get('reason') or '') + f' | Exit: {reason}',
            }).eq('id', trade_id).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "SELECT id,entry_price,quantity,side FROM trades "
                "WHERE id=? AND status='OPEN'", (trade_id,))
            t = c.fetchone()
            if not t:
                conn.close()
                return
            ep, qty, side = t['entry_price'], t['quantity'], t['side']
            pnl = (exit_price - ep) * qty if side == "BUY" else (ep - exit_price) * qty
            pnl_pct = ((exit_price - ep) / ep * 100) * (1 if side == "BUY" else -1)
            c.execute(
                "UPDATE trades SET exit_price=?,pnl=?,pnl_percent=?,status='CLOSED',"
                "exit_time=?,reason=reason||' | Exit: '||? WHERE id=?",
                (exit_price, round(pnl, 2), round(pnl_pct, 4),
                 datetime.now().isoformat(), reason, trade_id))
            conn.commit()
            conn.close()

    def record_partial_exit(self, trade_id: int, new_quantity: int, partial_pnl: float):
        """Reduce trade quantity after a partial exit (50% profit at 1:1 R:R)."""
        trade_id = int(trade_id)
        if self.use_supabase:
            self.supabase_client.table('trades').update({
                'quantity': new_quantity,
                'pnl': round(partial_pnl, 2),
            }).eq('id', trade_id).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "UPDATE trades SET quantity=?,pnl=? WHERE id=? AND status='OPEN'",
                (new_quantity, round(partial_pnl, 2), trade_id))
            conn.commit()
            conn.close()

    def update_trade_management_state(self, trade_id: int, current_sl: float,
                                      breakeven_applied: bool, partial_taken: bool,
                                      high_since_entry: float, low_since_entry: float):
        """Persist bot_runner trade management state back to DB."""
        trade_id = int(trade_id)
        fields = {
            'current_sl': current_sl,
            'breakeven_applied': int(breakeven_applied),
            'partial_taken': int(partial_taken),
            'high_since_entry': high_since_entry,
            'low_since_entry': low_since_entry,
            'stop_loss': current_sl,  # keep stop_loss in sync for display
        }
        if self.use_supabase:
            self.supabase_client.table('trades').update(fields).eq(
                'id', trade_id).eq('status', 'OPEN').execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "UPDATE trades SET current_sl=?,breakeven_applied=?,partial_taken=?,"
                "high_since_entry=?,low_since_entry=?,stop_loss=? "
                "WHERE id=? AND status='OPEN'",
                (current_sl, int(breakeven_applied), int(partial_taken),
                 high_since_entry, low_since_entry, current_sl, trade_id))
            conn.commit()
            conn.close()

    def get_open_trades_with_management_state(self):
        """Get open trades with all management columns (for bot_runner)."""
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
