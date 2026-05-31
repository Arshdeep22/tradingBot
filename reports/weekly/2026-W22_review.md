# Weekly Review — 2026-W22

**Win rate:** 20.0% | **Trend:** declining | **Progress:** 20% — 50% below 70% target

## Summary
Win rate collapsed to 20% with 4 consecutive losses after the W21 review loosened parameters to increase trade frequency. The bot went from 1 trade/week (100% win) to 5 trades/week (20% win), indicating quality was sacrificed for quantity. The core problem has shifted from 'too few trades' to 'poor entry quality' — we need a middle ground that generates 3-4 high-quality trades per week rather than forcing entries at marginal zones.

## Regime Assessment
Regime detection shows mixed evidence. The trending_up regime produced the one winner (Fri 5/22) but also generated 2 losses on Wed 5/27 — same regime, opposite outcomes. The trending_down day on 5/29 produced 2 losses, suggesting the bot should NOT be entering supply/demand trades during trending_down regimes. Regime filter is not being used effectively as a trade gate.

## Structural Recommendations

**[HIGH]** Add regime-based trade gate: BLOCK all entries when regime is trending_down. Supply & Demand zones are counter-trend by nature and fail in strong directional moves.
  Expected: Would have eliminated the 2 losses on 5/29 (₹1997 saved), improving week P&L from -₹1995 to +₹2. Expected to improve win rate by 10-15% by removing the worst-regime trades.

**[HIGH]** Implement zone freshness filter: only trade zones being tested for the first time or second time. Zones that have already been tested 3+ times are degraded and more likely to break.
  Expected: Estimated 15-20% improvement in zone reliability based on typical S&D zone degradation patterns. Should reduce false entries by 1-2 per week.

**[MEDIUM]** Add per-symbol performance tracking to log which instruments generate wins vs losses, enabling data-driven watchlist curation within 2-3 weeks.
  Expected: No immediate P&L impact but enables symbol-level decisions within 2-3 weeks that could add 5-10% to win rate through focus list optimization.

**[MEDIUM]** Implement a daily loss cap of 1 trade: if the first trade of the day loses, do not take a second entry that same day. Both multi-trade days (5/27 and 5/29) produced double losses.
  Expected: Would have saved ₹~1000 this week by preventing the second loss on each double-loss day. Reduces drawdown velocity by 50% on losing days.

