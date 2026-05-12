# Strategy Documents

Upload your strategy documents (PDF, TXT, or any format) in this folder.

## How to use:
1. Place your strategy document in this folder
2. Create a corresponding Python strategy file in `../strategies/`
3. Inherit from `BaseStrategy` and implement `generate_signal()`
4. Update `config/settings.py` to set your strategy as active

## Strategy Template:

```python
from strategies.base_strategy import BaseStrategy, Signal, TradeSignal
import pandas as pd

class MyCustomStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(name="My Strategy", timeframe="15m")
    
    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        # Your logic here
        # data has columns: Open, High, Low, Close, Volume
        
        current_price = data['Close'].iloc[-1]
        
        # Example: Return BUY signal
        return TradeSignal(
            signal=Signal.BUY,
            symbol=symbol,
            price=current_price,
            stop_loss=current_price * 0.99,  # 1% SL
            target=current_price * 1.02,      # 2% target
            reason="My custom condition met"
        )
    
    def get_parameters(self) -> dict:
        return {"name": self.name}
```

## Registering Your Strategy:

After creating the strategy file, add it to `main.py`:

```python
from strategies.my_custom_strategy import MyCustomStrategy

# In get_strategy() function:
strategies = {
    "ema_crossover": EMACrossoverStrategy(timeframe=DEFAULT_TIMEFRAME),
    "my_strategy": MyCustomStrategy(),  # Add your strategy here
}
```

Then update `config/settings.py`:
```python
ACTIVE_STRATEGY = "my_strategy"
```

## Current Strategies:
- **EMA Crossover** (`ema_crossover`) - Default strategy (9 EMA / 21 EMA crossover)