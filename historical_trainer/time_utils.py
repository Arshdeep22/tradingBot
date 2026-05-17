"""
Date and time utility functions for the Historical Trainer.
"""

from datetime import date, datetime, timezone
import pandas as pd

from .constants import SPLIT_UTC_H, SPLIT_UTC_M, EOD_UTC_H, EOD_UTC_M


def split_dt(d: date) -> datetime:
    """11:02 AM IST on date d, expressed in UTC."""
    return datetime(d.year, d.month, d.day, SPLIT_UTC_H, SPLIT_UTC_M, tzinfo=timezone.utc)


def eod_dt(d: date) -> datetime:
    """3:30 PM IST (market close) on date d, expressed in UTC."""
    return datetime(d.year, d.month, d.day, EOD_UTC_H, EOD_UTC_M, tzinfo=timezone.utc)


def slice_data(df: pd.DataFrame, up_to: datetime) -> pd.DataFrame:
    """Return rows of df with index <= up_to. Handles tz-aware and naive indices."""
    ts = pd.Timestamp(up_to)
    idx = df.index
    try:
        if hasattr(idx, 'tz') and idx.tz is not None:
            if ts.tzinfo is None:
                ts = ts.tz_localize('UTC')
        else:
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
    except Exception:
        ts = pd.Timestamp(up_to.replace(tzinfo=None))
    return df[idx <= ts]


def extract_trading_days(data_dict: dict) -> list:
    """Return sorted unique NSE trading dates present in the data."""
    dates = set()
    for df in data_dict.values():
        for ts in df.index:
            # NSE hours 9:15–15:30 IST = 3:45–10:00 UTC — same calendar date
            dates.add(pd.Timestamp(ts).date())
    return sorted(dates)