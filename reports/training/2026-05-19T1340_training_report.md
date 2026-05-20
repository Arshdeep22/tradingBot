# Historical Training Report — 2026-05-19T1340

## Summary
- Strategy: Professional Zone Scanner (6-dimension scoring, 0-60 scale)
- Period: 2026-02-18 → 2026-05-19 (59 trading days)
- Symbols: 20 | Quick: False
- Trades simulated: 53 | WR: 28.0% | Avg RR: -0.36 | P&L: ₹-1283
- Optimizer runs: 11 | Claude synthesis calls: 5

## Final Zone Parameters
| Parameter | Value |
|-----------|-------|
| min_score_to_trade | 42 |
| default_rr_ratio | 2.0 |
| min_rr_ratio | 1.4 |
| sl_atr_multiplier | 1.3 |
| max_sl_pct | 1.8 |
| max_base_candles | 3 |

## Learning Curve (Week by Week)
| Week | Dates | Trades | WR | Avg RR | P&L |
|------|-------|--------|----|--------|-----|
| 1 | 2026-02-18–2026-02-24 | 5 | 40.0% | 0.04 | ₹-111 |
| 2 | 2026-02-25–2026-03-04 | 9 | 55.6% | 0.25 | ₹-134 |
| 3 | 2026-03-05–2026-03-11 | 3 | 33.3% | -0.35 | ₹-163 |
| 4 | 2026-03-12–2026-03-18 | 10 | 20.0% | -0.57 | ₹-344 |
| 5 | 2026-03-19–2026-03-25 | 0 | 0.0% | 0.00 | ₹+0 |
| 6 | 2026-03-27–2026-04-06 | 5 | 20.0% | -0.65 | ₹-321 |
| 7 | 2026-04-07–2026-04-13 | 2 | 0.0% | -0.05 | ₹-54 |
| 8 | 2026-04-15–2026-04-21 | 3 | 0.0% | -1.03 | ₹-41 |
| 9 | 2026-04-22–2026-04-28 | 0 | 0.0% | 0.00 | ₹+0 |
| 10 | 2026-04-29–2026-05-06 | 8 | 14.3% | -0.55 | ₹-63 |
| 11 | 2026-05-07–2026-05-13 | 3 | 0.0% | -1.17 | ₹-84 |
| 12 | 2026-05-14–2026-05-19 | 5 | 40.0% | -0.08 | ₹+31 |

## Key Insights
The walk-forward simulation produced a dismal 28% win rate and negative average RR of -0.36 across 53 trades, indicating the zone scoring system in its current form is not predictive of profitable outcomes. The most critical finding is that stop-losses at 0.8 ATR are consistently too tight—price repeatedly exceeds the stop by a small margin before reversing—while RR targets of 3.5 are unreachable in prevailing conditions. Parameters never converged, oscillating between tight/aggressive and loose/conservative settings, suggesting the strategy requires fundamental structural improvements beyond parameter tuning.
- Stop-loss at 0.8 ATR is demonstrably too tight: 6 of 7 decided trades in one batch hit SL with RR between -1.19 and -1.29, meaning price exceeded stops by a small margin before reversing—widening to 1.3-1.5 ATR would have saved many trades
- Counter-trend trades are toxic: BUY signals in trending_down regimes went 0/3 and SELL signals in trending_up/ranging went 0/4, yet the scoring system's trend dimension (max 10/60 points) lacks sufficient weight to filter these out
- High zone scores (46-50/60) did NOT correlate with wins—the only winner in one batch was a low-score 35/60 trade in a ranging regime, indicating the 6-dimension scoring system needs recalibration or the dimensions are not capturing what matters
- RR targets of 3.5 were never reached in any batch; even 2.5 was rarely achieved. The best realistic target appears to be 2.0 RR, with partial exits at 1.0-1.5 RR being the only consistent profit opportunities observed
- Early weeks (1-2) with lower score thresholds and more permissive entry actually performed best (40-55% WR), suggesting over-filtering with high score thresholds may remove the few genuinely good setups while the remaining 'perfect score' zones still fail

**Best setup:** Week 2 produced the best results (55.6% WR, +0.25 avg RR) with a lower min_score threshold of 35, moderate RR target of 2.5, and likely more ranging market conditions. The single best pattern observed was SELL zones in strong trending_up markets where zone quality was exceptional (strong departure leg), suggesting only the highest-conviction counter-trend reversals work, while with-trend zone entries paradoxically failed more often—possibly because with-trend entries occur after extended moves where momentum is exhausting.

**Recommended approach:** Deploy conservatively with strict regime filtering: only take trades aligned with the dominant trend OR in confirmed ranging markets. Implement a mandatory trend-alignment gate that overrides zone score—no counter-trend trades regardless of score. Use wider stops (1.3 ATR) to survive the common 'stop hunt then reverse' pattern observed. Target 2.0 RR with a mandatory partial exit at 1.0 RR to lock in profits. Limit to 2-3 trades per week maximum and require a minimum holding period analysis before entry. Consider the strategy experimental until live results confirm at least 40% win rate over 30+ trades.

## Scoring System
Zones scored on 6 dimensions (0-10 each, max 60):
1. **Departure** — Leg-out quality (body size, count, volume)
2. **Base** — Base tightness (fewer candles = better)
3. **Freshness** — Untested zone (never touched = better)
4. **Arrival** — Leg-in quality (gradual arrival = better)
5. **Time** — Age of zone (newer = better)
6. **Trend** — Alignment with higher-TF trend