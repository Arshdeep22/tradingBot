# Historical Training Report — 2026-05-20T0401

## Summary
- Strategy: Professional Zone Scanner (6-dimension scoring, 0-60 scale)
- Period: 2026-02-19 → 2026-05-20 (59 trading days)
- Symbols: 10 | Quick: True
- Trades simulated: 8 | WR: 37.5% | Avg RR: -0.37 | P&L: ₹-60
- Optimizer runs: 11 | Claude synthesis calls: 5

## Final Zone Parameters
| Parameter | Value |
|-----------|-------|
| min_score_to_trade | 42 |
| default_rr_ratio | 2.0 |
| min_rr_ratio | 1.5 |
| sl_atr_multiplier | 1.5 |
| max_sl_pct | 1.8 |
| max_base_candles | 3 |

## Learning Curve (Week by Week)
| Week | Dates | Trades | WR | Avg RR | P&L |
|------|-------|--------|----|--------|-----|
| 1 | 2026-02-19–2026-02-25 | 1 | 0.0% | -1.25 | ₹-4 |
| 2 | 2026-02-26–2026-03-05 | 2 | 100.0% | 1.03 | ₹+23 |
| 3 | 2026-03-06–2026-03-12 | 1 | 0.0% | -1.18 | ₹-34 |
| 4 | 2026-03-13–2026-03-19 | 3 | 33.3% | -0.47 | ₹-15 |
| 5 | 2026-03-20–2026-03-27 | 0 | 0.0% | 0.00 | ₹+0 |
| 6 | 2026-03-30–2026-04-07 | 0 | 0.0% | 0.00 | ₹+0 |
| 7 | 2026-04-08–2026-04-15 | 0 | 0.0% | 0.00 | ₹+0 |
| 8 | 2026-04-16–2026-04-22 | 0 | 0.0% | 0.00 | ₹+0 |
| 9 | 2026-04-23–2026-04-29 | 1 | 0.0% | -1.18 | ₹-29 |
| 10 | 2026-04-30–2026-05-07 | 0 | 0.0% | 0.00 | ₹+0 |
| 11 | 2026-05-08–2026-05-14 | 0 | 0.0% | 0.00 | ₹+0 |
| 12 | 2026-05-15–2026-05-20 | 0 | 0.0% | 0.00 | ₹+0 |

## Key Insights
The 12-week walk-forward simulation produced only 8 trades with a 37.5% win rate and negative average RR of -0.37, indicating severe insufficiency in both trade generation and edge identification. The strategy oscillated between being too restrictive (generating zero trades for weeks) and too loose (taking low-quality zones that failed). The only profitable week (Week 2, 100% WR, +1.03 avg RR) occurred with earlier, stricter parameters, suggesting that higher-quality zone filtering with appropriate RR targets is the correct direction, but the market environment provided extremely limited opportunities for this timeframe and instrument.
- The fundamental tension throughout the simulation was between trade frequency and trade quality - loosening parameters to generate trades consistently produced losses, while tightening them eliminated all opportunities entirely, suggesting the underlying market structure did not frequently produce high-quality SD zones during this period.
- The only winning period (Week 2) used early parameters with min_score around 45+ and tighter base requirements, confirming that quality filtering is more important than trade frequency - taking fewer but higher-conviction zones is the correct approach.
- Stop losses averaging -1.18 to -1.25 RR on losses indicate the SL placement (1.5-1.6x ATR) was reasonable but not exceptional - losses were roughly 1R which is acceptable, but the win rate was too low to overcome them, pointing to zone identification quality rather than SL mechanics as the core issue.
- Parameters never truly converged - they oscillated between restrictive (37-42 min_score, 3 max_base_candles) and permissive (32-33 min_score, 5 max_base_candles) without finding a stable optimum, indicating insufficient data to calibrate the model and likely requiring a longer training period or additional confluence filters.
- The ranging market regime dominated weeks 3-12, and zones formed in ranging/choppy conditions showed poor follow-through, suggesting a regime filter (only trading zones aligned with a clear trending environment) would significantly improve performance.

**Best setup:** Week 2 produced 2 winning trades with 100% win rate and average 1.03 RR. These trades occurred with higher minimum score thresholds (likely 45+), tight base structures (max 3 candles), and were aligned with a short-term trending move. The successful pattern was: high-score zones (strong departure leg, tight base, fresh/untested) entered in trend-aligned conditions with moderate RR targets around 1.5-2.0, suggesting that the strategy works best when it is highly selective and only fires in clearly trending environments.

**Recommended approach:** Deploy with conservative, quality-first parameters and accept very low trade frequency (1-3 trades per week maximum). Add a mandatory trend regime filter - only take zones when the higher timeframe shows a clear directional bias (e.g., price above/below 20 EMA with ADX > 20). Use a staged approach: start with paper trading the recommended params for 4 weeks to accumulate at least 20 trades before risking real capital. Scale position sizes at 0.5% risk per trade initially, graduating to 1% only after demonstrating positive expectancy over 30+ trades. Consider adding a time-of-day filter to avoid choppy opening and closing periods.

## Scoring System
Zones scored on 6 dimensions (0-10 each, max 60):
1. **Departure** — Leg-out quality (body size, count, volume)
2. **Base** — Base tightness (fewer candles = better)
3. **Freshness** — Untested zone (never touched = better)
4. **Arrival** — Leg-in quality (gradual arrival = better)
5. **Time** — Age of zone (newer = better)
6. **Trend** — Alignment with higher-TF trend