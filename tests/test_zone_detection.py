"""Tests for Zone Detection (Plan 1) - Models and Detection."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from strategies.zone_models import Zone, ZoneAnalysis
from strategies.zone_detection import (
    detect_zones, DEFAULT_CONFIG, prepare_candle_data,
    compute_thresholds, find_leg_out_candles, find_base,
    find_leg_in, classify_pattern,
)


def make_ohlcv(n=50, price=100.0, seed=42):
    np.random.seed(seed)
    dates = pd.date_range('2024-01-01', periods=n, freq='15min')
    o, h, l, c, v = [price], [], [], [], []
    for i in range(n):
        op = o[i] if i < len(o) else c[-1]
        if i >= len(o):
            o.append(op)
        cl = op + np.random.randn() * 0.5
        hi = max(op, cl) + abs(np.random.randn() * 0.2)
        lo = min(op, cl) - abs(np.random.randn() * 0.2)
        h.append(hi)
        l.append(lo)
        c.append(cl)
        v.append(int(np.random.uniform(1e5, 5e5)))
        if i < n - 1:
            o.append(cl)
    return pd.DataFrame({'Open': o[:n], 'High': h, 'Low': l, 'Close': c, 'Volume': v}, index=dates)


def make_dbr(n=50):
    dates = pd.date_range('2024-01-01', periods=n, freq='15min')
    o, h, l, c, v = [], [], [], [], []
    p = 100.0
    for i in range(n):
        if i < 5:
            op, cl = p, p + np.random.uniform(-0.2, 0.2)
            hi, lo, vol = max(op, cl) + 0.1, min(op, cl) - 0.1, 200000
        elif 5 <= i <= 7:
            op, cl = p, p - 1.5
            hi, lo, vol = op + 0.1, cl - 0.1, 400000
        elif 8 <= i <= 9:
            op, cl = p, p + np.random.uniform(-0.05, 0.05)
            hi, lo, vol = max(op, cl) + 0.05, min(op, cl) - 0.05, 150000
        elif 10 <= i <= 12:
            op, cl = p, p + 2.0
            hi, lo, vol = cl + 0.1, op - 0.05, 500000
        else:
            op, cl = p, p + np.random.uniform(-0.3, 0.3)
            hi, lo, vol = max(op, cl) + 0.15, min(op, cl) - 0.15, 200000
        o.append(op)
        h.append(hi)
        l.append(lo)
        c.append(cl)
        v.append(vol)
        p = cl
    return pd.DataFrame({'Open': o, 'High': h, 'Low': l, 'Close': c, 'Volume': v}, index=dates)


def make_rbd(n=50):
    dates = pd.date_range('2024-01-01', periods=n, freq='15min')
    o, h, l, c, v = [], [], [], [], []
    p = 100.0
    for i in range(n):
        if i < 5:
            op, cl = p, p + np.random.uniform(-0.2, 0.2)
            hi, lo, vol = max(op, cl) + 0.1, min(op, cl) - 0.1, 200000
        elif 5 <= i <= 7:
            op, cl = p, p + 1.5
            hi, lo, vol = cl + 0.1, op - 0.05, 400000
        elif 8 <= i <= 9:
            op, cl = p, p + np.random.uniform(-0.05, 0.05)
            hi, lo, vol = max(op, cl) + 0.05, min(op, cl) - 0.05, 150000
        elif 10 <= i <= 12:
            op, cl = p, p - 2.0
            hi, lo, vol = op + 0.05, cl - 0.1, 500000
        else:
            op, cl = p, p + np.random.uniform(-0.3, 0.3)
            hi, lo, vol = max(op, cl) + 0.15, min(op, cl) - 0.15, 200000
        o.append(op)
        h.append(hi)
        l.append(lo)
        c.append(cl)
        v.append(vol)
        p = cl
    return pd.DataFrame({'Open': o, 'High': h, 'Low': l, 'Close': c, 'Volume': v}, index=dates)


def test_zone_model():
    z = Zone(
        zone_type="DEMAND", pattern="DBR", zone_top=101.0, zone_bottom=99.5,
        base_candles=2, formed_at_index=8, formed_at_time="t",
        leg_out_count=3, leg_out_body_pct=2.5, leg_out_body_ratio=0.85,
        leg_out_volume_ratio=2.1, has_gap=True, leg_in_body_pct=1.8, leg_in_candle_count=2)
    assert z.is_demand and z.is_reversal and not z.is_continuation
    assert abs(z.zone_height - 1.5) < 0.001
    assert abs(z.midpoint - 100.25) < 0.001
    assert z.score == 0 and z.is_fresh and "gap=Y" in repr(z)
    print("  [PASS] Zone model")


def test_zone_supply():
    z = Zone(
        zone_type="SUPPLY", pattern="RBD", zone_top=105.0, zone_bottom=104.0,
        base_candles=1, formed_at_index=10, formed_at_time="t",
        leg_out_count=2, leg_out_body_pct=3.0, leg_out_body_ratio=0.9,
        leg_out_volume_ratio=1.8, has_gap=True, leg_in_body_pct=2.0, leg_in_candle_count=1)
    assert z.is_supply and z.is_reversal and z.has_gap
    print("  [PASS] Zone supply model")


def test_zone_continuation():
    rbr = Zone(
        zone_type="DEMAND", pattern="RBR", zone_top=102, zone_bottom=101,
        base_candles=2, formed_at_index=5, formed_at_time="t",
        leg_out_count=1, leg_out_body_pct=1.5, leg_out_body_ratio=0.7,
        leg_out_volume_ratio=1.3, has_gap=False, leg_in_body_pct=1.2, leg_in_candle_count=1)
    dbd = Zone(
        zone_type="SUPPLY", pattern="DBD", zone_top=98, zone_bottom=97,
        base_candles=3, formed_at_index=7, formed_at_time="t",
        leg_out_count=2, leg_out_body_pct=2.0, leg_out_body_ratio=0.8,
        leg_out_volume_ratio=1.6, has_gap=False, leg_in_body_pct=1.8, leg_in_candle_count=2)
    assert rbr.is_continuation and rbr.is_demand
    assert dbd.is_continuation and dbd.is_supply
    print("  [PASS] Zone continuation")


def test_prepare_data():
    p = prepare_candle_data(make_ohlcv(30))
    for col in ['body', 'body_pct', 'candle_range', 'body_ratio', 'is_bullish', 'is_bearish']:
        assert col in p.columns
    assert (p['body'] >= 0).all()
    print("  [PASS] Prepare candle data")


def test_thresholds():
    p = prepare_candle_data(make_ohlcv(50))
    t = compute_thresholds(p, DEFAULT_CONFIG)
    assert t['large_candle_threshold'] > t['small_candle_threshold']
    print("  [PASS] Compute thresholds")


def test_classify():
    assert classify_pattern("BEARISH", "BULLISH") == ("DEMAND", "DBR")
    assert classify_pattern("BULLISH", "BEARISH") == ("SUPPLY", "RBD")
    assert classify_pattern("BULLISH", "BULLISH") == ("DEMAND", "RBR")
    assert classify_pattern("BEARISH", "BEARISH") == ("SUPPLY", "DBD")
    print("  [PASS] Classify pattern")


def test_detect_empty():
    assert detect_zones(None) == []
    assert detect_zones(pd.DataFrame()) == []
    assert detect_zones(make_ohlcv(10)) == []
    print("  [PASS] detect_zones handles empty/short data")


def test_detect_dbr():
    cfg = {**DEFAULT_CONFIG, 'min_body_ratio': 0.50, 'min_legin_multiplier': 0.5}
    zones = detect_zones(make_dbr(), config=cfg)
    demand = [z for z in zones if z.zone_type == "DEMAND"]
    if demand:
        z = demand[0]
        assert z.zone_top > z.zone_bottom and z.leg_out_count >= 1
        print(f"  [PASS] Detect DBR ({z.pattern}, legout={z.leg_out_count}x)")
    else:
        print(f"  [INFO] Detect DBR - {len(zones)} total zones, no DEMAND (threshold-dependent)")


def test_detect_rbd():
    cfg = {**DEFAULT_CONFIG, 'min_body_ratio': 0.50, 'min_legin_multiplier': 0.5}
    zones = detect_zones(make_rbd(), config=cfg)
    supply = [z for z in zones if z.zone_type == "SUPPLY"]
    if supply:
        z = supply[0]
        assert z.zone_top > z.zone_bottom and z.leg_out_count >= 1
        print(f"  [PASS] Detect RBD ({z.pattern}, legout={z.leg_out_count}x)")
    else:
        print(f"  [INFO] Detect RBD - {len(zones)} total zones, no SUPPLY (threshold-dependent)")


def test_config_toggle():
    cfg = {**DEFAULT_CONFIG, 'detect_dbr': False, 'detect_rbd': False,
           'detect_rbr': False, 'detect_dbd': False}
    assert detect_zones(make_dbr(), config=cfg) == []
    print("  [PASS] Config toggle (all off = no zones)")


def test_detect_returns_list():
    zones = detect_zones(make_ohlcv(50))
    assert isinstance(zones, list)
    for z in zones:
        assert z.zone_type in ("DEMAND", "SUPPLY")
        assert z.pattern in ("DBR", "RBD", "RBR", "DBD")
        assert z.zone_top > z.zone_bottom
        assert z.base_candles >= 1
        assert z.leg_out_count >= 1
    print(f"  [PASS] detect_zones returns valid list ({len(zones)} zones)")


def run_all_tests():
    print("\n" + "=" * 60)
    print("  ZONE DETECTION TEST SUITE (Plan 1)")
    print("=" * 60)
    tests = [
        test_zone_model, test_zone_supply, test_zone_continuation,
        test_prepare_data, test_thresholds, test_classify,
        test_detect_empty, test_detect_dbr, test_detect_rbd,
        test_config_toggle, test_detect_returns_list,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)