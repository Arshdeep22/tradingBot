# Weekly Review — 2026-W21

**Win rate:** 100.0% | **Trend:** stable | **Progress:** 100% win rate but meaningless — need 3-5 trades/day minimum to evaluate. Effective weekly P&L of ₹1996 is far below potential.

## Summary
Extremely low trade frequency (1 trade in 5 days) is the dominant issue this week. The single trade taken was a winner at ₹1996, but the bot is clearly too selective — the min_score of 75 and strict zone criteria are filtering out nearly all setups. The 100% win rate is statistically meaningless with n=1. The primary structural problem is insufficient trade generation, not poor execution.

## Regime Assessment
Regime detection identified 3 trending_up and 2 trending_down days, which seems reasonable for a mixed week. However, with zero trades on 4 of 5 days across BOTH regime types, the regime filter isn't the bottleneck — the zone identification criteria are too strict regardless of regime.

## Structural Recommendations

**[HIGH]** Add a 'near-miss' logging system that records zones scoring 55-74 (below threshold) with their hypothetical outcomes. This provides data on whether lowering thresholds would have been profitable without risking capital.
  Expected: Within 1-2 weeks, provides evidence-based guidance for threshold tuning. Could reveal 50-100 missed opportunities per week.

**[HIGH]** Implement adaptive min_score based on daily opportunity count. If fewer than 2 qualifying zones are found by 10:30 AM, automatically lower min_score by 5 points (floor of 60) to ensure minimum participation.
  Expected: Increase trade frequency from 0.2/day to 2-3/day, enabling statistically meaningful performance measurement within 2 weeks.

**[MEDIUM]** Add a secondary strategy (e.g., VWAP mean-reversion or Opening Range Breakout) that activates when Supply & Demand Zones produce zero candidates by mid-morning. This ensures the bot is never fully idle.
  Expected: Reduce zero-trade days from 80% to under 20%. Even at 55% win rate, additional trades improve weekly P&L consistency.

**[HIGH]** Log scan-level diagnostics: how many symbols scanned, how many zones identified, how many passed scoring, how many had valid RR. This pipeline visibility will pinpoint exactly where candidates are being lost.
  Expected: Enables targeted parameter tuning rather than guessing. Should accelerate optimization by 2-3 weeks.

