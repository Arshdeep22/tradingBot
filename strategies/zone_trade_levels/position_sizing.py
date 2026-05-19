"""
Position sizing for zone trading.
Implements the 1% risk rule for professional position management.
"""


def calculate_position_size(entry: float, stop_loss: float,
                            capital: float = 100000,
                            risk_pct: float = 1.0) -> int:
    """
    Calculate position size using fixed percentage risk model.

    Position Size = Risk Amount / Risk Per Share
    Risk Amount = capital * (risk_pct / 100)
    Risk Per Share = |entry - stop_loss|

    Returns integer number of shares (rounded down).
    Returns 0 if risk per share is zero or negative.
    """
    if capital <= 0 or risk_pct <= 0:
        return 0

    risk_amount = capital * (risk_pct / 100.0)
    risk_per_share = abs(entry - stop_loss)

    if risk_per_share <= 0:
        return 0

    position_size = int(risk_amount / risk_per_share)
    return max(position_size, 0)


def calculate_risk_amount(capital: float, risk_pct: float = 1.0) -> float:
    """Calculate total risk amount in currency."""
    return round(capital * (risk_pct / 100.0), 2)


def calculate_position_value(entry: float, position_size: int) -> float:
    """Calculate total position value."""
    return round(entry * position_size, 2)


def validate_position_size(position_size: int, entry: float,
                           capital: float, max_position_pct: float = 20.0) -> bool:
    """
    Validate that position doesn't exceed max percentage of capital.
    Default max is 20% of capital in a single position.
    """
    if position_size <= 0 or capital <= 0:
        return False
    position_value = entry * position_size
    position_pct = (position_value / capital) * 100
    return position_pct <= max_position_pct