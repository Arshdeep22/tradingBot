# Historical Training Report — 2026-05-19T1334

## Summary
- Strategy: Professional Zone Scanner (6-dimension scoring, 0-60 scale)
- Period: 2026-02-18 → 2026-05-19 (59 trading days)
- Symbols: 10 | Quick: True
- Trades simulated: 25 | WR: 43.5% | Avg RR: -0.00 | P&L: ₹+29
- Optimizer runs: 11 | Claude synthesis calls: 5

## Final Zone Parameters
| Parameter | Value |
|-----------|-------|
| min_score_to_trade | 45 |
| default_rr_ratio | 2.0 |
| min_rr_ratio | 1.5 |
| sl_atr_multiplier | 1.5 |
| max_sl_pct | 2.0 |
| max_base_candles | 3 |

## Learning Curve (Week by Week)
| Week | Dates | Trades | WR | Avg RR | P&L |
|------|-------|--------|----|--------|-----|
| 1 | 2026-02-18–2026-02-24 | 1 | 100.0% | 1.52 | ₹+20 |
| 2 | 2026-02-25–2026-03-04 | 5 | 80.0% | 1.03 | ₹+68 |
| 3 | 2026-03-05–2026-03-11 | 2 | 50.0% | 0.05 | ₹-6 |
| 4 | 2026-03-12–2026-03-18 | 5 | 40.0% | 0.06 | ₹-13 |
| 5 | 2026-03-19–2026-03-25 | 0 | 0.0% | 0.00 | ₹+0 |
| 6 | 2026-03-27–2026-04-06 | 2 | 50.0% | 0.22 | ₹+3 |
| 7 | 2026-04-07–2026-04-13 | 1 | 0.0% | -0.40 | ₹-7 |
| 8 | 2026-04-15–2026-04-21 | 2 | 0.0% | -1.25 | ₹-20 |
| 9 | 2026-04-22–2026-04-28 | 0 | 0.0% | 0.00 | ₹+0 |
| 10 | 2026-04-29–2026-05-06 | 4 | 0.0% | -1.00 | ₹-49 |
| 11 | 2026-05-07–2026-05-13 | 0 | 0.0% | 0.00 | ₹+0 |
| 12 | 2026-05-14–2026-05-19 | 3 | 33.3% | -0.21 | ₹+31 |

## Key Insights
The walk-forward simulation revealed a sharp performance degradation after the initial 2 weeks (80-100% WR) dropping to near 0% in weeks 7-10, resulting in an overall 43.5% win rate and breakeven avg RR. The 1.0x ATR stop-loss was consistently too tight, with price reversing just past the stop before moving in the intended direction. Parameters never converged—the optimizer oscillated between tight filters (score 50) and loose filters (score 35)—indicating the strategy needs structural improvements beyond parameter tuning, particularly in regime-aware stop placement and trade direction filtering.
- Stop-loss at 1.0x ATR is systematically too tight: repeated analysis showed losses clustering at exactly -1.0 to -1.25 RR, suggesting price probes past the zone boundary before reversing, requiring at minimum 1.5x ATR stops to survive normal zone retests
- Early success (weeks 1-2, 80%+ WR) occurred in what appears to be a trending market favorable to the strategy, while later weeks saw regime shifts that destroyed edge—regime alignment scoring alone (the Trend dimension) was insufficient to prevent counter-trend losses
- Higher score thresholds (45-50) reduced trade frequency but did NOT improve win rate in adverse conditions—even 50-52/60 scored zones produced losses, indicating zone quality scoring cannot compensate for poor market timing or inadequate stop width
- The SELL-side bias was problematic: most losses came from short trades in trending_up or ranging regimes, suggesting the strategy needs explicit directional filtering beyond the existing trend dimension score
- A default RR target of 3.0 was too ambitious and rarely hit; the single best profitable period used 2.5 RR, while winning trades averaged approximately 1.0-1.5 actual RR achieved

**Best setup:** Weeks 1-2 produced 6 trades with 83% win rate and +₹88 P&L using moderate parameters (min_score 35, RR 2.5, SL 1.0 ATR). The common pattern was fresh zones with tight bases (≤3 candles) scored 40+ in clearly trending markets where trade direction aligned with the dominant trend. The single best trade scored 47/60 and captured 1.52R profit, suggesting zones scoring 45+ in strongly trending environments with first-touch (fresh) status represent the highest probability setup.

**Recommended approach:** Deploy with conservative parameters emphasizing survival over frequency: use wider stops (1.5x ATR) to avoid premature stop-outs, moderate RR targets (2.0-2.5) that are actually achievable, and a high score threshold (45+) to ensure only institutional-quality zones are traded. Critically, add a hard rule to ONLY trade in the direction of the higher-timeframe trend—no counter-trend zone trades regardless of score. Start with minimum position sizing and require 20+ trades before adjusting parameters. Monitor the stop-hunt pattern closely: if price consistently reverses within 0.5 ATR past the stop level, the zone thesis is correct but execution needs refinement via wider stops or limit orders deeper in the zone.

## Scoring System
Zones scored on 6 dimensions (0-10 each, max 60):
1. **Departure** — Leg-out quality (body size, count, volume)
2. **Base** — Base tightness (fewer candles = better)
3. **Freshness** — Untested zone (never touched = better)
4. **Arrival** — Leg-in quality (gradual arrival = better)
5. **Time** — Age of zone (newer = better)
6. **Trend** — Alignment with higher-TF trend