"""
Per-day walk-forward simulation logic (v3).
KEY FIXES:
- Entry at zone midpoint (not edge) for better risk/reward
- Ranging regime quality gate (+5 score threshold)
- Rejection candle confirmation required
- Counter-trend hard filter
- Zone blacklist across days
- Max 2 trades/day (A+ only)
- Volatile regime blocked entirely
"""

import logging
from datetime import date
from typing import Set, Tuple

import pandas as pd
import numpy as np

from core.backtester import Backtester
from strategies.zone_scanner import ProfessionalZoneScanner

from .constants import DEFAULT_ZONE_PARAMS
from .time_utils import split_dt, eod_dt, slice_data

logger = logging.getLogger(__name__)

MAX_HOLDING_BARS = 75  # 3 trading days on 15m


def detect_regime(data: pd.DataFrame) -> Tuple[str, float]:
    """Regime detection. Returns (regime, ema_slope)."""
    if data is None or len(data) < 30:
        return "unknown", 0.0

    close = data['Close']
    ema20 = close.ewm(span=20, adjust=False).mean()
    if len(ema20) < 11:
        return "unknown", 0.0

    ema_slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10] * 100

    high = data['High']
    low = data['Low']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(com=13, adjust=False).mean()

    if len(atr) < 20:
        return "unknown", ema_slope

    current_atr = atr.iloc[-1]
    atr_median = atr.iloc[-50:].median() if len(atr) >= 50 else atr.median()
    atr_ratio = current_atr / atr_median if atr_median > 0 else 1.0

    ema50 = close.ewm(span=50, adjust=False).mean() if len(close) >= 50 else ema20
    price_vs_ema50 = (close.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1] * 100

    if atr_ratio > 1.8:
        return "volatile", ema_slope
    elif ema_slope > 0.8 and price_vs_ema50 > 0.5:
        return "trending_up", ema_slope
    elif ema_slope < -0.8 and price_vs_ema50 < -0.5:
        return "trending_down", ema_slope
    elif abs(ema_slope) > 0.4:
        return ("trending_up" if ema_slope > 0 else "trending_down"), ema_slope
    else:
        return "ranging", ema_slope


def _is_counter_trend(side: str, regime: str, ema_slope: float) -> bool:
    """Block counter-trend trades entirely."""
    if side == "BUY":
        if regime == "trending_down" or ema_slope < -0.3:
            return True
        if regime == "volatile" and ema_slope < 0.5:
            return True
    elif side == "SELL":
        if regime == "trending_up" or ema_slope > 0.3:
            return True
        if regime == "volatile" and ema_slope > -0.5:
            return True
    return False


def _zone_key(symbol: str, entry: float, stop_loss: float) -> str:
    """Unique key for zone blacklist."""
    entry_bucket = round(entry / (entry * 0.005)) if entry > 0 else 0
    sl_bucket = round(stop_loss / (stop_loss * 0.005)) if stop_loss > 0 else 0
    return f"{symbol}_{entry_bucket}_{sl_bucket}"


def _has_rejection_candle(data: pd.DataFrame, entry: float, side: str,
                          lookback: int = 8) -> bool:
    """
    Check for rejection candle near entry level confirming zone respect.
    More lenient than before — checks within 1% of entry price.
    """
    if data is None or len(data) < lookback:
        return True

    recent = data.tail(lookback)
    tolerance = entry * 0.01  # 1% tolerance

    for _, candle in recent.iterrows():
        full_range = candle['High'] - candle['Low']
        if full_range == 0:
            continue

        if side == "BUY":
            # Price came near entry and showed buying pressure
            if candle['Low'] <= entry + tolerance:
                lower_wick = min(candle['Open'], candle['Close']) - candle['Low']
                if lower_wick / full_range > 0.35:
                    return True
                # Or bullish close after touching zone
                if candle['Close'] > candle['Open']:
                    return True
        else:  # SELL
            if candle['High'] >= entry - tolerance:
                upper_wick = candle['High'] - max(candle['Open'], candle['Close'])
                if upper_wick / full_range > 0.35:
                    return True
                # Or bearish close after touching zone
                if candle['Close'] < candle['Open']:
                    return True

    return False


def _build_scanner_config(zone_params: dict) -> dict:
    """Build ProfessionalZoneScanner config from training params."""
    return {
        "enable_stock_selection": False,
        "enable_market_conditions": False,
        "check_confirmation": False,
        "max_base_candles": zone_params.get("max_base_candles", DEFAULT_ZONE_PARAMS["max_base_candles"]),
        "min_body_ratio": zone_params.get("min_body_ratio", DEFAULT_ZONE_PARAMS["min_body_ratio"]),
        "min_volume_ratio": zone_params.get("min_volume_ratio", DEFAULT_ZONE_PARAMS["min_volume_ratio"]),
        "min_legin_multiplier": 0.8,
        "detect_dbr": True, "detect_rbd": True, "detect_rbr": True, "detect_dbd": True,
        "max_zone_width_pct": zone_params.get("max_zone_width_pct", DEFAULT_ZONE_PARAMS["max_zone_width_pct"]),
        "min_zone_width_pct": 0.1,
        "max_distance_from_cmp": zone_params.get("max_distance_from_cmp", DEFAULT_ZONE_PARAMS["max_distance_from_cmp"]),
        "min_score_to_trade": zone_params.get("min_score_to_trade", DEFAULT_ZONE_PARAMS["min_score_to_trade"]),
        "sl_atr_multiplier": zone_params.get("sl_atr_multiplier", DEFAULT_ZONE_PARAMS["sl_atr_multiplier"]),
        "max_sl_pct": zone_params.get("max_sl_pct", DEFAULT_ZONE_PARAMS["max_sl_pct"]),
        "default_rr_ratio": zone_params.get("default_rr_ratio", DEFAULT_ZONE_PARAMS["default_rr_ratio"]),
        "min_rr_ratio": zone_params.get("min_rr_ratio", DEFAULT_ZONE_PARAMS["min_rr_ratio"]),
        "risk_per_trade_pct": 1.0,
        "capital": 100000,
    }


def _get_3day_test_window(day: date, all_days: list, data_dict: dict, symbol: str):
    """Get test data spanning up to 3 trading days forward."""
    try:
        day_idx = all_days.index(day)
    except ValueError:
        return None

    end_day_idx = min(day_idx + 2, len(all_days) - 1)
    end_day = all_days[end_day_idx]

    split_time = split_dt(day)
    end_time = eod_dt(end_day)

    if symbol not in data_dict:
        return None

    full_df = data_dict[symbol]
    test_slice = full_df[(full_df.index >= split_time) & (full_df.index <= end_time)]
    return test_slice if len(test_slice) > 0 else None


def run_day(day: date, data_dict: dict, current_zone_params: dict,
            current_weights: dict = None, all_days: list = None,
            traded_zones: Set[str] = None) -> list:
    """
    Simulate one walk-forward trading day.
    Returns list of trade dicts for triggered setups.
    """
    split_time = split_dt(day)
    eod_time = eod_dt(day)

    zp = current_zone_params or dict(DEFAULT_ZONE_PARAMS)
    scanner_config = _build_scanner_config(zp)
    zone_scanner = ProfessionalZoneScanner(**scanner_config)

    bt = Backtester(strategy=zone_scanner, max_holding_bars=MAX_HOLDING_BARS)
    day_trades = []
    max_trades_per_day = 2

    if traded_zones is None:
        traded_zones = set()

    base_min_score = zp.get("min_score_to_trade", DEFAULT_ZONE_PARAMS["min_score_to_trade"])

    for symbol, full_df in data_dict.items():
        if len(day_trades) >= max_trades_per_day:
            break

        build_data = slice_data(full_df, split_time)
        if len(build_data) < 30:
            continue

        regime, ema_slope = detect_regime(build_data)

        # Ranging regime quality gate
        effective_min_score = base_min_score
        if regime == "ranging":
            effective_min_score = base_min_score + 5

        # Skip volatile regime entirely
        if regime == "volatile":
            continue

        try:
            if all_days:
                test_data_3d = _get_3day_test_window(day, all_days, data_dict, symbol)
            else:
                test_data_3d = slice_data(full_df, eod_time)
                test_data_3d = test_data_3d[test_data_3d.index >= split_time]

            if test_data_3d is None or len(test_data_3d) < 5:
                continue

            combined = pd.concat([build_data, test_data_3d])
            combined = combined[~combined.index.duplicated(keep='first')]
            report = bt.run(combined, split_time, symbol)

            first = next(
                (tr for tr in report.trade_results
                 if tr.triggered and tr.outcome in ("TARGET_HIT", "SL_HIT", "EXPIRED")),
                None,
            )
            if first is None:
                continue

            # Score quality gate (regime-adjusted)
            if first.setup.score < effective_min_score:
                continue

            # Hard trend filter
            if _is_counter_trend(first.setup.side, regime, ema_slope):
                continue

            # Zone blacklist
            zkey = _zone_key(symbol, first.setup.entry, first.setup.stop_loss)
            if zkey in traded_zones:
                continue
            traded_zones.add(zkey)

            # Rejection candle confirmation
            if not _has_rejection_candle(build_data, first.setup.entry, first.setup.side):
                continue

            trade = {
                "symbol": symbol,
                "strategy": "Professional Zone Scanner",
                "side": first.setup.side,
                "outcome": first.outcome,
                "pnl": round(first.pnl, 2),
                "entry": round(first.trigger_price, 2),
                "stop_loss": round(first.setup.stop_loss, 2),
                "target": round(first.setup.target, 2),
                "score": first.setup.score,
                "rr_achieved": round(first.rr_achieved, 2),
                "trigger_time": first.trigger_time,
                "exit_time": first.exit_time,
                "regime": regime,
                "ema_slope": round(ema_slope, 2),
                "zone_params": {
                    "min_score_to_trade": zp.get("min_score_to_trade", DEFAULT_ZONE_PARAMS["min_score_to_trade"]),
                    "default_rr_ratio": zp.get("default_rr_ratio", DEFAULT_ZONE_PARAMS["default_rr_ratio"]),
                    "sl_atr_multiplier": zp.get("sl_atr_multiplier", DEFAULT_ZONE_PARAMS["sl_atr_multiplier"]),
                },
            }
            day_trades.append(trade)

        except Exception as e:
            logger.debug("  %s: %s", symbol, e)

    return day_trades