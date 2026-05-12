-- ============================================================
-- Supabase Table Setup for Trading Bot
-- ============================================================
-- Run this in your Supabase SQL Editor:
-- https://supabase.com/dashboard → Your Project → SQL Editor
-- ============================================================

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION,
    stop_loss DOUBLE PRECISION,
    target DOUBLE PRECISION,
    pnl DOUBLE PRECISION,
    pnl_percent DOUBLE PRECISION,
    strategy TEXT,
    reason TEXT,
    status TEXT DEFAULT 'OPEN',
    entry_time TIMESTAMPTZ DEFAULT NOW(),
    exit_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pending orders table
CREATE TABLE IF NOT EXISTS pending_orders (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    stop_loss DOUBLE PRECISION,
    target DOUBLE PRECISION,
    strategy TEXT,
    reason TEXT,
    status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ
);

-- Portfolio snapshots table
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    balance DOUBLE PRECISION,
    portfolio_value DOUBLE PRECISION,
    open_positions INTEGER,
    total_pnl DOUBLE PRECISION
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_pending_orders_status ON pending_orders(status);

-- Enable Row Level Security (optional, for public access with anon key)
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;

-- Allow all operations with anon key (for personal use)
CREATE POLICY "Allow all on trades" ON trades FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on pending_orders" ON pending_orders FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on portfolio_snapshots" ON portfolio_snapshots FOR ALL USING (true) WITH CHECK (true);