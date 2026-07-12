# Weekly Review — 2026-W28

**Win rate:** 0.0% | **Trend:** declining | **Progress:** 0% — catastrophically below 70% target

## Summary
The bot finally took 3 trades after weeks of paralysis, but all 3 were losses resulting in ₹-2995. The reduced min_score (75) allowed entries but zone quality is clearly insufficient — every trade hit stop loss. The Supply & Demand Zone strategy is fundamentally broken in its current form: it either takes no trades or takes losing trades. A complete structural overhaul is needed, not parameter tuning.

## Regime Assessment
Regime detection appears functional (correctly identified shift from trending_up to trending_down mid-week) but the strategy cannot capitalize on either regime. Losses occurred in both trending_up (Mon/Tue) and trending_down (Thu), suggesting the strategy is regime-agnostic in a bad way — zones are not aligning with trend direction.

## Structural Recommendations

**[HIGH]** Add trend-alignment filter: only take demand zones in trending_up, only supply zones in trending_down. Currently the strategy appears to trade counter-trend zones.
  Expected: Should eliminate at least 50% of losing trades by filtering against-trend entries

**[HIGH]** Implement a secondary confirmation signal (e.g., price must show rejection candle at zone, or volume spike) before entry. Raw zone touch is insufficient.
  Expected: Reduce false entries by 30-50%, improving win rate from 0% toward 40%+

**[HIGH]** Add trailing stop or partial profit-taking at 1R instead of holding for full 2R target. All 3 trades lost ~₹1000 each suggesting stops are being hit with no opportunity for partial wins.
  Expected: Even with same entry quality, capturing partial profits could turn some full losses into breakeven or small wins

**[MEDIUM]** Log and track per-symbol performance data. Current system provides no symbol visibility making it impossible to identify which instruments are tradeable.
  Expected: Enable data-driven symbol selection within 2-3 weeks

**[MEDIUM]** Consider adding a momentum/breakout strategy as secondary strategy for trending regimes. Supply & Demand zones are mean-reversion plays that conflict with strong trends.
  Expected: Diversified strategy set could capture trending moves that S&D zones miss, adding 2-4 trades per week

**[HIGH]** Reduce position size to ₹500 risk per trade until win rate exceeds 40% over 10+ trades. Current ₹1000 risk with 0% win rate is pure capital destruction.
  Expected: Halves weekly drawdown from ~₹3000 to ~₹1500 during strategy validation phase

