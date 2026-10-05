# DD-WEEK r2 (TV): REVERT daily - fade NQ / ES daily moves both ways, leaning in when volatility is high (DRAFT 2026-10-04)

DRAFT for MANAGER (adversarial) before any number of it exists. TV's slot in the drawdown-week earner hunt (MANAGER #30:
NQ/ES daily-bar / multi-day mechanisms; STRATEGY-BEATING owns intraday + overnight). Family name: REVERT (daily). Harness
after review: `tools/ddw2_fade.py`; results `C:\EdgeLog\_anatomy_cache\ddweek\r2\` + RESEARCH_LEDGER.md.

## Map first (docs/MDL_MAP_R1.md)

#463 is four directional momentum / breakout legs; its drawdown weeks are stress weeks (2020-02..04, 2022, 2025-04) where
index moves get large and alternate. A two-sided daily fade is anti-momentum by construction and trades every session (no
crisis-only trade-count problem: ~250 a year), and the mechanism below predicts its edge is concentrated in exactly those
weeks. If it earns there it needs < $5k a year at a $30k drawdown of its own; if it only earns overall it needs ~$15k.

MECHANISM (index-level liquidity provision): when volatility spikes, liquidity providers withdraw and forced / risk-
targeting flows (vol-target and leveraged-ETF rebalancing, margin calls) push the index past fair value; the next session
partly reverses. The return to supplying that liquidity rises with volatility (Nagel 2012, "Evaporating Liquidity";
Grossman & Miller 1988), and US index daily returns are negatively autocorrelated in high-volatility regimes. Prediction:
fading the cash-session move pays little or nothing in calm markets and pays in stress; leaning size into volatility
should raise return per unit of drawdown, not just size.

DISCLOSURE (seen before this file): DIP (the long side only, trend-filtered dip rules) - profitable, loses in the 2020
crash; RSI2 "both sides" on NQ inside the r25 weak-edge pooled book (pooled with ETFs, never alone); the ENGU-Q short
mirror on 24h (+$70,698 in 2022, bleeds 15 other years); the crash-regime short (18/18 dead); STRATEGY-BEATING's DDW r1
(the same mechanism on single stocks). NOT computed anywhere: an unfiltered two-sided fade of NQ/ES cash-session moves,
any volatility lean on it, any drawdown-week number for it, its lockbox.

## Rules

- Data: house 5-minute RTH masters, roll-corrected (db_adj_rth), bars stamped at START, US/Eastern; sessions with all 78
  bars only. Arrays cut before 2025-06-30 00:00 ET before any signal.
- Signal at 15:55 on session t: R = close of the 15:50 bar(t) / close of the 15:55 bar(t-1) - 1 (cash close to almost-close).
  Scale = median |R| over the previous 60 eligible sessions (>= 40).
- Trade: side = -sign(R); enter at the close of the 15:55 bar (16:00), exit at the close of the 15:55 bar of the next
  eligible session (one session held, one trade per session, each its own round trip). A session whose next eligible
  session is more than 4 calendar days away is skipped.
- Size: notional $100,000 x k in contract equivalents (fractional, priced as micros), F cells k = 1; S cells k = ES 20-session
  realised volatility (std of daily log returns of the 16:00 closes) / its median over the previous 252 sessions, clipped to
  [0.5, 2.0], known at the prior close.
- Cells: market {NQ, ES} x filter {m0: every session, m1: |R| >= 1 x scale} x lean {F, S} = 8.
- Cost per round trip per full-contract equivalent: NQ 0.533 pt ($20/pt), ES 0.363 pt ($50/pt), micros at their own rate
  (MNQ / MES: the same points, 1/10 the dollars, + $0.50 a side commission per micro); stress +0.25 pt.
- Null (family-wide): each session's side replaced by a fair coin (one coin per session per market, shared across that
  market's four cells), costs and sizes re-applied; statistics = (1) the MAX over the 8 cells of the WF per-trade t and
  (2) the MAX over the 8 cells of the drawdown-day sum (below); 500 reps, seed 20261004.
- Yardstick and #463 drawdown days: as DD-WEEK r1 / house convention - ROC %/yr at $30k = 30 x (net / years) / worst
  daily-valued drawdown; drawdown days = peak-to-trough episodes of #463's WF daily mtm (r4/book463_daily.csv) at least
  $14,950 deep, days after each peak through the trough; #463 must reproduce 93.81 / 3.816 / $44,849 first or nothing runs.

## Stage A (WF 2016-07-01 -> 2025-06-29) - a cell passes only if ALL hold

a. >= 100 WF trades;  b. ROC @ $30k >= 5 %/yr;  c. profit factor >= 1.05;  d. t >= 2.0 and above the null's 95th
percentile of max-t;  e. net > 0 at the stress cost;  f. profitable without its single biggest day;  g. positive in >= 6
of the 9 July-June WF years;  h. DRAWDOWN-DAY EARNER: summed P&L over #463's drawdown days > 0, still > 0 without its 3
best days there, AND above the null's 95th percentile of the max drawdown-day sum;  i. net > 0 without 2020-02-15 ..
2020-04-30;  j. EARLY (2010-06 -> 2016-06-30) net > 0;  k. an S cell must also beat its own F twin on WF ROC @ $30k AND
Sortino (raw-twin rule; otherwise a pass could be leverage in 2020).
Reported: each cell's P&L in every #463 drawdown episode; correlation with each #463 leg overall and inside drawdown days;
long and short sides apart; the 10 biggest days.

## Stage A2, C, B

A2 (WF): the best Stage-A pass by WF ROC added to #463's daily mtm at c in {0.5, 1, 2} (best c frozen): book WF ROC @ $30k
>= 98.50 AND Sortino >= 3.816. If nothing passes A, A2 runs on NQ-m0-F and ES-m0-F at c = 1, REPORTED ONLY.
C (MANAGER's line; reads the lockbox): a strategy file reproducing the frozen cell to the cent; ONE Auto-Validate, 900
trials, pinned date_from / date_to; RUNBOARD with ROC @ $30k and DD%. B (once, MANAGER's line): book LB >= 155.54 with
Sortino >= 4.150, book LB net without its biggest day > 0, the leg's own LB >= 50 trades and net > 0.
Zero passes at A2 = dead; the next TV draft is a new mechanism, never a re-tune of this one.

## How it could fool us

1. 2020 dominance - i and h's "without its 3 best days" guard it.  2. The S lean is leverage that happens to land in
crashes (RISK r1's V2 lesson) - k (raw twin) and i.  3. The long side is DIP-like and was seen; the short side bleeds in
bull years - both sides reported.  4. Daily round trips pay cost every session (~$11-18 a contract) - e and the stress
cost.  5. One #463 path - the map's limit.

## Addendum 1 (2026-10-05 06:40 MST, PRE-DATA - MANAGER review C:/EdgeLog/manager/reviews/tv_ddweek_r2_review_2026-10-05.md, GO WITH EDITS)

No number of this family had been computed when this was written. These replace the matching text above; nothing else changes.

1. FAMILY NAME = DAILYFADE (not REVERT). REVERT r1 / r2 (STRATEGY-BEATING, 2026-09-30, ledger 2.38 / 2.41) were INTRADAY fades
   on NQ/ES - a failed new high/low of the day (r1, price-only dead, order-flow variant a forward shadow) and the post-close
   quarter-hour (r2) - both dead. DAILYFADE differs: one-session holds, index-level daily moves, no 10-second delta, no
   intraday trigger.
2. POINTS, NOT PERCENTAGES. The roll-corrected masters are back-adjusted (June 2010 NQ reads ~5,553 adjusted vs ~1,820 raw),
   so any percentage read off them is understated up to ~3x in the early years. All signal quantities are now in POINTS,
   which are shift-invariant: R = close of the 15:50 bar(t) - close of the 15:55 bar(t-1); scale = median |R| over the
   previous 60 eligible sessions (>= 40); k = std of the 20 daily point changes (16:00 close to 16:00 close) before t /
   its median over the previous 252 sessions, clipped [0.5, 2.0], ES's series for both markets, known at the prior close.
   P&L = points x $ per point. The RAW (no-adjust) master supplies only the price level that sets the contract count.
3. LIVE ROUNDING. Size = whole micros, nearest, at least 1: n = max(1, round($100,000 x k / (raw price x $2 MNQ or $5 MES))),
   recomputed every session (about 2-3 MNQ and ~3 MES at 2025 prices, more micros in early years). A paper line rounds
   the same way. Cost per micro per round trip = the house points (NQ 0.533, ES 0.363) x the micro's $/pt + $1.00
   commission; stress +0.25 pt; + 0.25 pt per contract switch crossed. (Replaces the fractional contract-equivalents.)
4. THE OVERNIGHT DRAFT. The long side of this fade after a down session contains the DD-WEEK r1 overnight mechanism held
   to the next close; DD-WEEK r1 was handed to STRATEGY-BEATING (MANAGER #30: overnight is their slot). If both run they are
   ONE piece of evidence, not two. Every cell reports its long side (trades entered after a down session) beside it.
5. STAGE B USES THE FROZEN CELL and its frozen c. The Auto-Validate (Stage C) champion of a 900-trial region is for the
   RUNBOARD only and never enters the book add without a new pre-registration.

## Results - Stage A (WF only), 2026-10-05 06:5x MST: DAILYFADE is DEAD (0 of 8 cells pass)

Run `tools/ddw2_fade.py` exactly as committed (33d336f3, after addendum 1 cee87446; it ran from the local commits while the
push waited in the lock queue). #463 reproduced 93.81 / 3.816 / $44,849; 460 WF drawdown days. Family null 95th pct: max t
2.07, max drawdown-day sum $93,375. Per cell (WF trades, ROC @ $30k, Sortino, t, drawdown-day sum / without its 3 best days):
- NQ every day, flat: 2,207, 4.3, 0.37, t 0.75, +$8,340 / -$6,886; EARLY -$95,400.
- NQ every day, leaned: 1,954, 3.7, 0.39, t 0.77, +$8,630 / -$18,068; EARLY -$160,226.
- NQ big days, flat: 1,117, 3.7, 0.41, t 0.79, +$13,265 / -$468; EARLY -$55,832.
- NQ big days, leaned: 988, 6.1, 0.67, t 1.23, +$18,967 / -$4,857; EARLY -$90,009 (best cell; fails d, g, h, j).
- ES, all four cells: ROC -1.5 to 0.5, t <= 0.12, drawdown-day sums -$17k to -$31k (it LOSES while the book falls).
Long side vs short side (NQ every day, flat): long +$107,018, short -$58,335 - the money is in buying after down sessions
(the DIP / overnight piece already known, addendum 1 item 4); the short side that was meant to earn in sell-offs bleeds.
Book add, reported only (c = 1, WF): NQ 71.3 / Sortino 3.96, ES 65.6 / 3.66 vs #463's 93.81 / 3.816 - it lowers the book's
return per unit of drawdown.

What it teaches: index-level daily reversal does not concentrate in #463's drawdown weeks on these markets - the NQ sum
there is a fraction of the null's and turns negative without its three best days, and on ES it is negative. The 2010-16
block loses on every cell. Zero passes at A2 = dead by the pre-registered rule; the next TV draft is a new mechanism.
Lockbox untouched. Results: C:\EdgeLog\_anatomy_cache\ddweek\r2\stage_a.json, log stage_a_r2.log.
