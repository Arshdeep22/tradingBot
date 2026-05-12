# 📈 Trading Bot - Paper Trading System

A modular Python trading bot that starts with paper trading and can be plugged into real brokers (Zerodha) later.

## 🏗️ Architecture

```
tradingBot/
├── config/
│   └── settings.py              # All configuration (symbols, capital, timeframes)
├── strategies/
│   ├── base_strategy.py         # Abstract base class for strategies
│   └── ema_crossover.py         # Default EMA crossover strategy
├── strategies_docs/             # 📁 Upload your strategy PDFs/TXT here
├── core/
│   ├── data_fetcher.py          # Fetches market data (yfinance)
│   ├── engine.py                # Main trading engine loop
│   ├── broker_interface.py      # Abstract broker interface
│   └── paper_trader.py          # Paper trading implementation
├── database/
│   └── db.py                    # SQLite database for trade history
├── dashboard/
│   └── app.py                   # Streamlit web dashboard
├── logs/                        # Bot logs
├── main.py                      # Entry point
└── requirements.txt
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Mac/Linux
# venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Settings

Edit `config/settings.py` to customize:
- **SYMBOLS**: Stocks to trade (NSE format: "RELIANCE.NS")
- **INITIAL_CAPITAL**: Starting paper money (default: ₹1,00,000)
- **DEFAULT_TIMEFRAME**: Candle timeframe (3m, 5m, 15m)
- **ACTIVE_STRATEGY**: Which strategy to use

### 3. Run the Bot

```bash
# Run one cycle (recommended for testing)
python main.py --once

# Run continuously during market hours
python main.py

# Run ignoring market hours (for testing anytime)
python main.py --backtest
```

### 4. View Dashboard

```bash
streamlit run dashboard/app.py
```

Open http://localhost:8501 in your browser to see:
- Trade history
- Win rate & P&L metrics
- Equity curve
- Strategy analysis

## 📊 Default Strategy: EMA Crossover

| Parameter | Value |
|-----------|-------|
| Fast EMA | 9 periods |
| Slow EMA | 21 periods |
| Timeframe | 15 minutes |
| Stop Loss | 1% |
| Target | 2% (1:2 RR) |

**Rules:**
- **BUY**: When 9 EMA crosses above 21 EMA
- **SELL**: When 9 EMA crosses below 21 EMA
- **Exit**: On SL hit, Target hit, or opposite signal

## 🔧 Adding Your Own Strategy

1. Place your strategy document in `strategies_docs/`
2. Create a new file in `strategies/` (see template in `strategies_docs/README.md`)
3. Register it in `main.py`
4. Update `ACTIVE_STRATEGY` in `config/settings.py`

## 📱 Dashboard Features

- **Overview**: KPIs, win/loss pie chart, open positions
- **Trade History**: All trades with filters (symbol, status, strategy)
- **Equity Curve**: Portfolio value over time, P&L per trade
- **Strategy Analysis**: Performance by symbol, P&L distribution

## 🔌 Future: Zerodha Integration

The bot is designed with a pluggable broker interface. To switch to live trading:

1. Install `kiteconnect`: `pip install kiteconnect`
2. Add your API credentials in `config/settings.py`
3. Implement `ZerodhaBroker` class (inheriting from `BrokerInterface`)
4. Change `BROKER = "zerodha"` in settings

## ⚠️ Disclaimer

This is for educational purposes. Paper trading results may differ from live trading. Always test thoroughly before using real money.

## 📝 Commands Reference

| Command | Description |
|---------|-------------|
| `python main.py` | Run bot (market hours only) |
| `python main.py --once` | Run single cycle |
| `python main.py --backtest` | Run ignoring market hours |
| `streamlit run dashboard/app.py` | Open dashboard |