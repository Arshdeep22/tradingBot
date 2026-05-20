# Historical Training Report — 2026-05-19T1345

## Summary
- Strategy: Professional Zone Scanner (6-dimension scoring, 0-60 scale)
- Period: 2026-02-18 → 2026-05-19 (59 trading days)
- Symbols: 20 | Quick: False
- Trades simulated: 81 | WR: 23.0% | Avg RR: -0.49 | P&L: ₹-2314
- Optimizer runs: 11 | Claude synthesis calls: 0

## Final Zone Parameters
| Parameter | Value |
|-----------|-------|
| min_score_to_trade | 40 |
| default_rr_ratio | 2.5 |
| min_rr_ratio | 1.5 |
| sl_atr_multiplier | 0.8 |
| max_sl_pct | 1.5 |
| max_base_candles | 3 |

## Learning Curve (Week by Week)
| Week | Dates | Trades | WR | Avg RR | P&L |
|------|-------|--------|----|--------|-----|
| 1 | 2026-02-18–2026-02-24 | 5 | 40.0% | 0.04 | ₹-111 |
| 2 | 2026-02-25–2026-03-04 | 9 | 55.6% | 0.25 | ₹-134 |
| 3 | 2026-03-05–2026-03-11 | 3 | 33.3% | -0.25 | ₹-144 |
| 4 | 2026-03-12–2026-03-18 | 10 | 20.0% | -0.57 | ₹-344 |
| 5 | 2026-03-19–2026-03-25 | 7 | 42.9% | -0.05 | ₹-137 |
| 6 | 2026-03-27–2026-04-06 | 5 | 20.0% | -0.65 | ₹-321 |
| 7 | 2026-04-07–2026-04-13 | 8 | 0.0% | -0.63 | ₹-495 |
| 8 | 2026-04-15–2026-04-21 | 3 | 0.0% | -1.03 | ₹-41 |
| 9 | 2026-04-22–2026-04-28 | 7 | 0.0% | -1.03 | ₹-199 |
| 10 | 2026-04-29–2026-05-06 | 8 | 14.3% | -0.55 | ₹-63 |
| 11 | 2026-05-07–2026-05-13 | 11 | 0.0% | -1.10 | ₹-357 |
| 12 | 2026-05-14–2026-05-19 | 5 | 40.0% | -0.08 | ₹+31 |

## Scoring System
Zones scored on 6 dimensions (0-10 each, max 60):
1. **Departure** — Leg-out quality (body size, count, volume)
2. **Base** — Base tightness (fewer candles = better)
3. **Freshness** — Untested zone (never touched = better)
4. **Arrival** — Leg-in quality (gradual arrival = better)
5. **Time** — Age of zone (newer = better)
6. **Trend** — Alignment with higher-TF trend