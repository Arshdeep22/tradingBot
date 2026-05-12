"""
Simulate Trades
================
This script simulates some trades to populate the database
so you can see the dashboard working.

Run: python3 simulate_trades.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import DatabaseManager
from datetime import datetime, timedelta
import random

db = DatabaseManager()

# Clear previous simulated data
db.clear_all_trades()

print("Simulating trades for dashboard demo...")
print("=" * 50)

# Simulate 15 trades over the past few days
symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
base_prices = {
    "RELIANCE.NS": 1389.0,
    "TCS.NS": 2299.0,
    "INFY.NS": 1131.0,
    "HDFCBANK.NS": 757.0,
    "ICICIBANK.NS": 1245.0
}

trades_data = []
for i in range(15):
    symbol = random.choice(symbols)
    price = base_prices[symbol]
    
    # Random entry price variation
    entry_price = round(price * (1 + random.uniform(-0.02, 0.02)), 2)
    
    # Random outcome: 60% win, 40% loss
    is_winner = random.random() < 0.6
    
    if is_winner:
        # Won: hit target (1-2% profit)
        exit_price = round(entry_price * (1 + random.uniform(0.01, 0.025)), 2)
    else:
        # Lost: hit stop loss (0.5-1% loss)
        exit_price = round(entry_price * (1 - random.uniform(0.005, 0.012)), 2)
    
    quantity = max(1, int(10000 / entry_price))
    stop_loss = round(entry_price * 0.99, 2)
    target = round(entry_price * 1.02, 2)
    pnl = round((exit_price - entry_price) * quantity, 2)
    
    trades_data.append({
        "symbol": symbol,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "target": target,
        "pnl": pnl,
        "is_winner": is_winner
    })

# Insert trades into database
for i, trade in enumerate(trades_data):
    # Save open trade
    trade_id = db.save_trade(
        symbol=trade["symbol"],
        side="BUY",
        quantity=trade["quantity"],
        entry_price=trade["entry_price"],
        stop_loss=trade["stop_loss"],
        target=trade["target"],
        strategy="EMA Crossover",
        reason="EMA 9 crossed above EMA 21"
    )
    
    # Close it
    db.close_trade(
        symbol=trade["symbol"],
        exit_price=trade["exit_price"],
        pnl=trade["pnl"],
        reason="Target Hit" if trade["is_winner"] else "Stop Loss Hit"
    )
    
    status = "✅ WIN" if trade["is_winner"] else "❌ LOSS"
    print(f"  Trade {i+1}: {trade['symbol']} | Entry: {trade['entry_price']} | "
          f"Exit: {trade['exit_price']} | PnL: {trade['pnl']:+.2f} | {status}")

# Add 2 open positions
for symbol in ["RELIANCE.NS", "INFY.NS"]:
    price = base_prices[symbol]
    entry = round(price * (1 + random.uniform(-0.01, 0.01)), 2)
    quantity = max(1, int(10000 / entry))
    db.save_trade(
        symbol=symbol,
        side="BUY",
        quantity=quantity,
        entry_price=entry,
        stop_loss=round(entry * 0.99, 2),
        target=round(entry * 1.02, 2),
        strategy="EMA Crossover",
        reason="EMA 9 crossed above EMA 21"
    )
    print(f"  Open: {symbol} | Entry: {entry} | Qty: {quantity}")

print()
print("=" * 50)
print(f"✅ Simulated 15 closed trades + 2 open positions")
print(f"📊 Refresh the dashboard at http://localhost:8501 to see results!")
print("=" * 50)