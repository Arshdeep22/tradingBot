# Historical Training Report -- 2026-05-17T1322

## Summary
- Strategy: Supply & Demand Zones (Zone Scanner)
- Period: 2026-02-16 -> 2026-05-15 (59 trading days)
- Symbols: 10 | Quick: True
- Trades simulated: 454 | WR: 25.4% | P&L: Rs-3084
- Optimizer runs: 11 | Claude synthesis calls: 5
- Final Zone params: {'min_score': 85, 'rr_ratio': 1.5, 'max_base_candles': 3}

## Learning Curve (Week by Week)
| Week | Dates | Trades | WR | P&L |
|------|-------|--------|----|-----|
| 1 | 2026-02-16-2026-02-20 | 36 | 19.2% | Rs-266 |
| 2 | 2026-02-23-2026-02-27 | 43 | 35.7% | Rs-47 |
| 3 | 2026-03-02-2026-03-09 | 31 | 37.0% | Rs-313 |
| 4 | 2026-03-10-2026-03-16 | 43 | 7.7% | Rs-434 |
| 5 | 2026-03-17-2026-03-23 | 31 | 50.0% | Rs+35 |
| 6 | 2026-03-24-2026-04-01 | 41 | 28.1% | Rs-274 |
| 7 | 2026-04-02-2026-04-09 | 41 | 4.0% | Rs-381 |
| 8 | 2026-04-10-2026-04-17 | 42 | 17.6% | Rs-282 |
| 9 | 2026-04-20-2026-04-24 | 32 | 16.7% | Rs-383 |
| 10 | 2026-04-27-2026-05-04 | 38 | 20.0% | Rs-272 |
| 11 | 2026-05-05-2026-05-11 | 44 | 29.7% | Rs-294 |
| 12 | 2026-05-12-2026-05-15 | 32 | 42.9% | Rs-172 |

## Key Insights
The walk-forward simulation of 454 trades over 12 weeks produced a dismal 25.4% overall win rate with consistent negative P&L, indicating the zone scanner alone is insufficient for profitable trading. The system chronically over-traded (30-44 trades/week) with poor zone quality filtering, frequently entering against prevailing trends. The only profitable week (Week 5, 50% WR, ₹+35) coincided with higher min_score thresholds and reduced RR targets, while catastrophic weeks (4 and 7 at 7.7% and 4.0% WR) occurred when the system traded aggressively into trending markets without directional bias filtering.
- Zone scoring threshold of 70 is far too permissive - the system generates excessive low-quality signals that get stopped out; weeks with implied higher filtering (Week 5 at 50% WR, Week 12 at 42.9% WR) dramatically outperformed, suggesting min_score of 82-85 is necessary to filter noise
- The 2.0 RR ratio is rarely achieved in practice - actual winning trades averaged only ₹21.1 while stops averaged ₹18.5 (effective RR ~1.14:1), meaning price enters zones but lacks momentum to reach full targets; a 1.3-1.5 RR with higher win rate is mathematically superior for this setup
- Trading against the prevailing trend is the #1 killer - SELL zones in bullish markets and BUY zones in bearish markets account for the majority of SL_HIT losses; TCS.NS (9 losses/1 win) and BHARTIARTL.NS (0 wins/10 trades) show certain instruments need directional bias confirmation before entry
- EXPIRED trades (averaging 40-50% of all trades) with small negative P&L indicate zones are being touched but price consolidates rather than reversing sharply - tighter base candle requirements (max 2-3) would select only the sharpest departure zones with genuine institutional interest
- The optimizer consistently reverted to permissive params (min_score 70, RR 2.0) because it lacked enough winning trade data to validate tighter settings - this is a classic overfitting-to-noise trap where the system needs fewer, higher-conviction trades rather than more attempts

## Final Parameters
Zone: min_score=85, rr_ratio=1.5, max_base_candles=3