"""Pending Orders operations - SQLite and Supabase."""
from datetime import datetime, timedelta


class OrdersMixin:
    """Mixin for pending order operations. Requires BaseDB attributes."""

    def save_pending_order(self, symbol, side, quantity, entry_price,
                           stop_loss=0.0, target=0.0, strategy="",
                           reason="", expires_at=None):
        """Save a pending order. Returns order ID."""
        if self.use_supabase:
            data = {
                'symbol': symbol, 'side': side, 'quantity': quantity,
                'entry_price': entry_price, 'stop_loss': stop_loss,
                'target': target, 'strategy': strategy, 'reason': reason,
                'status': 'PENDING', 'expires_at': expires_at,
                'created_at': datetime.now().isoformat()
            }
            res = self.supabase_client.table('pending_orders').insert(data).execute()
            return res.data[0]['id'] if res.data else 0

        conn = self._get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_orders "
            "(symbol,side,quantity,entry_price,stop_loss,target,strategy,reason,status,expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,'PENDING',?)",
            (symbol, side, quantity, entry_price, stop_loss, target,
             strategy, reason, expires_at))
        oid = c.lastrowid
        conn.commit()
        conn.close()
        return oid

    def get_pending_orders(self):
        """Get all pending orders."""
        if self.use_supabase:
            res = (self.supabase_client.table('pending_orders')
                   .select('*').eq('status', 'PENDING')
                   .order('created_at', desc=True).execute())
            return res.data or []

        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM pending_orders WHERE status='PENDING' ORDER BY created_at DESC")
        orders = [dict(row) for row in c.fetchall()]
        conn.close()
        return orders

    def execute_pending_order(self, order_id):
        """Mark order as executed and create a trade. Returns order dict."""
        if self.use_supabase:
            res = (self.supabase_client.table('pending_orders')
                   .select('*').eq('id', order_id).execute())
            if not res.data:
                return None
            order = res.data[0]
            self.supabase_client.table('pending_orders').update({
                'status': 'EXECUTED', 'executed_at': datetime.now().isoformat()
            }).eq('id', order_id).execute()
            trade_data = {
                'symbol': order['symbol'], 'side': order['side'],
                'quantity': order['quantity'], 'entry_price': order['entry_price'],
                'stop_loss': order['stop_loss'], 'target': order['target'],
                'strategy': order['strategy'], 'reason': order['reason'],
                'status': 'OPEN', 'entry_time': datetime.now().isoformat(),
                'created_at': datetime.now().isoformat()
            }
            self.supabase_client.table('trades').insert(trade_data).execute()
            return order

        conn = self._get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM pending_orders WHERE id=?", (order_id,))
        order = c.fetchone()
        if not order:
            conn.close()
            return None
        od = dict(order)
        c.execute("UPDATE pending_orders SET status='EXECUTED', executed_at=? WHERE id=?",
                  (datetime.now().isoformat(), order_id))
        c.execute(
            "INSERT INTO trades "
            "(symbol,side,quantity,entry_price,stop_loss,target,strategy,reason,status,entry_time) "
            "VALUES (?,?,?,?,?,?,?,?,'OPEN',?)",
            (od['symbol'], od['side'], od['quantity'], od['entry_price'],
             od['stop_loss'], od['target'], od['strategy'], od['reason'],
             datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return od

    def cancel_pending_order(self, order_id):
        """Cancel a pending order."""
        if self.use_supabase:
            self.supabase_client.table('pending_orders').update({
                'status': 'CANCELLED'
            }).eq('id', order_id).execute()
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE pending_orders SET status='CANCELLED' WHERE id=?", (order_id,))
            conn.commit()
            conn.close()

    def expire_old_orders(self, max_age_days=3):
        """Expire pending orders older than max_age_days."""
        if self.use_supabase:
            cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
            (self.supabase_client.table('pending_orders')
             .update({'status': 'EXPIRED'})
             .eq('status', 'PENDING').lt('created_at', cutoff).execute())
        else:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute(
                "UPDATE pending_orders SET status='EXPIRED' "
                "WHERE status='PENDING' AND created_at < datetime('now', ?)",
                (f'-{max_age_days} days',))
            conn.commit()
            conn.close()