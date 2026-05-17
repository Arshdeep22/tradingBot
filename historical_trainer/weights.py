"""
Strategy weight computation helpers.
With single strategy (Zone Scanner), this is simplified to just return zone-only config.
"""


def compute_zone_slots(zone_wr: float, max_slots: int = 12) -> int:
    """Return number of slots to allocate to Zone Scanner based on win rate."""
    if zone_wr <= 0:
        return max_slots // 2
    return max_slots