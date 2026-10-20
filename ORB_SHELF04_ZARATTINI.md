# READING SHELF No. 4: Zarattini & Aziz 2023, "Can Day Trading Really Be Profitable?" (ORB lane, 2026-10-20)

**Verdict: CLOSED AT DRAFT** on the power-first map. Pre-WF rows only; no walk-forward or lockbox number was computed.

**The paper** (SSRN 4416622; PDF + text in `C:\EdgeLog\manager\papers\ssrn_4416622\`), table 1:
- Trade the colour of the first 5-minute bar: long if it closed up, short if down, no trade on a doji.
- Enter at the open of the second 5-minute bar. Stop at the first bar's low (long) or high (short); that distance is R.
- Target 10R, else exit at the close. Size: 1% of the account at risk, 4x leverage cap. Commission $0.0005 a share, no slippage.
- Sample: QQQ 2016-2023, no separate out-of-sample period. Those are the house's WF years, so the paper itself is a public look at
  WF, not independent evidence.
- The shelf card's "stop at a fraction of ATR" is wrong: that is the stocks-in-play sibling (SIPORB r1, dead).

**Why it was not already tested.** #314 / #234 need a confirmed breakout of a 2-bar range plus volatility and pace filters. This rule
enters at 09:35 on the first bar's colour with no breakout. The catalogue's "direction rules" and "entry cutoffs" rows were all
inside the breakout frame.

**Map** (`C:\EdgeLog\_anatomy_cache\shelf04\map_shelf04.py`, stdout beside it): NQ 5m RTH (no-adjust master), 2010-06-07 ..
2016-06-30, 1 contract, $20 a point, 0.533 pt a round trip. Exits on 5m bars; a bar touching both stop and target counts as the stop.

| Read | Value |
|---|---|
| Trades | 1,479 (244 a year); 31 sessions skipped (dojis, half days) |
| Gross a trade | 0.595 pt = 1.12 x cost (net +0.06 pt) |
| Exits | 78% stop, 2.6% target, 19% at the close |
| Four numbers at $30k (pre-WF) | ROC 0.62 / DD5 $12,902 / DD % 25.6 / Sortino 0.14, one episode |
| Net by year ($) | 2010 -2,975; 2011 -970; 2012 -105; 2013 +3,965; 2014 +5,677; 2015 -9,837; 2016H1 +6,079 |

**Against #314 on the same days.**
- #314's own pre-WF gross is 1.20 x cost on 837 trades. Pre-WF is a weak stretch for ORB, so a flat gross/cost line is not the test.
- The shelf rule is weaker per trade (1.12 x) and trades 1.8 x as often. It trades on 822 of #314's 837 days; daily correlation 0.45.

**As a book addition** (#463 pre-WF 47.27 on the cached RISK r1 daily; paired 21-day block bootstrap, 2,000 draws):

| Added weight | ROC@30k change | Paired SD | 1.96 SD bar |
|---|---|---|---|
| 0.25 | -0.85 | 2.41 | 4.73 |
| 0.50 | -1.66 | 4.46 | 8.74 |
| 1.00 | -3.18 | 7.58 | 14.86 |

The 1.05 x bar needs +2.36. Every weight lowers the book's ROC, and the noise bar is out of reach. An outside replication
(mql5 blog, five indices) also reports the gross edge reproduced and the net near zero after spread and slippage.

**Nothing is queued.** Run record: one preWF line in `C:\EdgeLog\run_records\orb_202610.jsonl`.
