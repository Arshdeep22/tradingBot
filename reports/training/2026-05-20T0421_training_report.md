# Historical Training Report — 2026-05-20T0421

## Summary
- Strategy: Professional Zone Scanner (6-dimension scoring, 0-60 scale)
- Period: 2026-02-19 → 2026-05-20 (59 trading days)
- Symbols: 10 | Quick: True
- Trades simulated: 6 | WR: 25.0% | Avg RR: -0.70 | P&L: ₹-104
- Optimizer runs: 11 | Claude synthesis calls: 5

## Final Zone Parameters
| Parameter | Value |
|-----------|-------|
| min_score_to_trade | 30 |
| default_rr_ratio | 1.5 |
| min_rr_ratio | 1.0 |
| sl_atr_multiplier | 2.0 |
| max_sl_pct | 3.0 |
| max_base_candles | 5 |

## Learning Curve (Week by Week)
| Week | Dates | Trades | WR | Avg RR | P&L |
|------|-------|--------|----|--------|-----|
| 1 | 2026-02-19–2026-02-25 | 1 | 0.0% | -0.90 | ₹-11 |
| 2 | 2026-02-26–2026-03-05 | 3 | 33.3% | -0.48 | ₹-32 |
| 3 | 2026-03-06–2026-03-12 | 1 | 0.0% | -1.15 | ₹-39 |
| 4 | 2026-03-13–2026-03-19 | 0 | 0.0% | 0.00 | ₹+0 |
| 5 | 2026-03-20–2026-03-27 | 0 | 0.0% | 0.00 | ₹+0 |
| 6 | 2026-03-30–2026-04-07 | 0 | 0.0% | 0.00 | ₹+0 |
| 7 | 2026-04-08–2026-04-15 | 0 | 0.0% | 0.00 | ₹+0 |
| 8 | 2026-04-16–2026-04-22 | 0 | 0.0% | 0.00 | ₹+0 |
| 9 | 2026-04-23–2026-04-29 | 1 | 0.0% | -0.75 | ₹-22 |
| 10 | 2026-04-30–2026-05-07 | 0 | 0.0% | 0.00 | ₹+0 |
| 11 | 2026-05-08–2026-05-14 | 0 | 0.0% | 0.00 | ₹+0 |
| 12 | 2026-05-15–2026-05-20 | 0 | 0.0% | 0.00 | ₹+0 |

## Key Insights
The 12-week walk-forward simulation produced only 6 trades with a 25% win rate and negative average RR of -0.71, providing insufficient data for statistically meaningful conclusions. The system oscillated between being too restrictive (generating zero trades for weeks) and too loose (producing losing trades), never finding a stable equilibrium. Parameters never converged, with the optimizer repeatedly cycling between tightening filters after losses and loosening them after dry spells. The fundamental issue is that the zone scanner in its current form cannot reliably identify actionable setups in this market regime.
- The system is fundamentally undertrained: 6 trades over 12 weeks is far below the ~30+ minimum needed for any statistical reliability, making all parameter conclusions tentative at best
- A recurring tension exists between trade frequency and quality - min_score_to_trade above 33-34 produces zero trades for extended periods, while below 28-30 it generates losing trades, suggesting the scoring model itself needs recalibration rather than just threshold adjustment
- Stop losses appear adequately sized (1.82-2.0 ATR) since most losses were partial (RR of -0.75 to -0.90 rather than full -1.0), indicating trades are expiring or being managed rather than getting hard-stopped consistently
- The max_base_candles parameter of 3 is likely too restrictive and filters out legitimate zones with slightly wider consolidation bases - the market may require 5-6 candle bases to form valid institutional zones
- The single winning trade occurred in Week 2 when parameters were relatively loose (min_score ~28-30 range), suggesting that over-filtering eliminates marginal winners that would improve overall expectancy

**Best setup:** The only winning trade occurred in the early phase (Week 2) when looser parameters were active, suggesting zones with moderate scores (28-35 range) in trending conditions may offer better opportunity than waiting exclusively for premium 40+ scored zones that rarely materialize. Insufficient data exists to identify a specific reliable pattern - no zone type, regime, or score band demonstrated repeatable success.

**Recommended approach:** Deploy in paper-trade/minimal-risk mode for an additional 8-12 weeks minimum to accumulate at least 30 trades before committing meaningful capital. Use the loosest defensible parameters to maximize trade generation for learning purposes. Focus on collecting data across different market regimes (trending, ranging, volatile) rather than optimizing for a single regime. Consider adding a time-based exit at 50% of max holding period if trade is breakeven, to avoid the repeated pattern of trades expiring at partial losses. Do NOT trade this system live with real capital until win rate exceeds 40% over 30+ trades.

## Scoring System
Zones scored on 6 dimensions (0-10 each, max 60):
1. **Departure** — Leg-out quality (body size, count, volume)
2. **Base** — Base tightness (fewer candles = better)
3. **Freshness** — Untested zone (never touched = better)
4. **Arrival** — Leg-in quality (gradual arrival = better)
5. **Time** — Age of zone (newer = better)
6. **Trend** — Alignment with higher-TF trend