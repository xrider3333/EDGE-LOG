# PRE-REGISTRATION (DRAFT for MANAGER review) — NOISE round 70: size NOISE #422's SHORTS up (2026-10-05; amended per MANAGER review #36)

Standing order 10-04 (queue of three; the map first). Draft sent to MANAGER before any tilted number exists; if no answer
in 60 minutes, Stage A (walk-forward only, no lockbox) runs and the review is folded in as a dated addendum.

## Map placement (docs/MDL_MAP_R1.md)
The house's main hunt is a leg or re-size that EARNS WHILE #463 FALLS (its drawdown weeks: 2020-02..04, 2022, 2025). NOISE
shorts are the part of #463 that is built to earn in sell-offs; this re-size moves NOISE weight toward them. A NOISE
re-size must beat PLAIN EXTRA NOISE at the same average size - that is the bar, at the book level.

## DISCLOSURE - partly seen
While reviewing Custom ML's hedge-tilt draft (10-05), NOISE computed #422's side split: walk-forward longs 2,068 trades,
PF 1.36, $110 a trade; shorts 737, PF 1.83, $301 (IS 1.13 vs 1.24). The walk-forward is therefore partly seen at the
level of the side split (not the tilted book, not its drawdown); the lockbox side split was NOT computed. As in round 69,
Stage A is confirmatory; its value is whether the short weight survives the drawdown, the paired test, breadth and the
book comparison. Round 69's lesson applies: up-weighting the better subset lowered ROC at $30k because drawdown grew
faster, so a better per-trade side is not enough.

## Mechanism (before any tilted number)
Down-moves are faster and more one-sided than up-moves (forced selling, volatility rising into the fall), so an intraday
momentum break to the downside carries further; NOISE's crown already demands a wider short band (1.5 vs 0.75), keeping
only the strongest down-breaks. Those trades cluster in the book's falling weeks, so weighting them up should add return
where #463 loses. Why it may fail: shorts are a quarter of the trades, so more weight concentrates the leg (round 69);
2020 and 2022 may carry it alone; ENGU-Q and ORB may already be short-neutral in those weeks.

## Rule, fixed now
NOISE #422 unchanged except every SHORT trade is sized x 1.5 (on top of its own 1.75x compression size); longs unchanged.
Neighbours reported, never picked from: shorts x 1.25 and x 2.0. Twin = #422.

## Stage A - walk-forward only (2016-06-30 .. 2025-07-16), lockbox and tail unread
A1. NOISE leg: beats #422 on WF ROC at a $30k drawdown (valued daily) AND Sortino; >= 100 trades.
A2. Both neighbours beat #422's WF ROC at $30k.
A3. Paired stationary block bootstrap (mean block 20 sessions, 1,000 draws, seed 20261005) of tilted vs #422 daily P&L:
    5th percentile of the WF ROC-at-$30k difference > 0. Power line (from #422's own WF spread, stated before running).
A4. Breadth: beats #422 in >= 6 of 9 WF years, AND still beats it with 2020-02-01 .. 04-30 removed AND with 2022 removed.
A5. BOOK bar (the map's): #463 with this NOISE leg beats #463 with plain NOISE scaled by c (c = mean tilted size /
    mean #422 size over WF trades, sizes only) on WF ROC at $30k AND Sortino - computed by the book lane (or by NOISE on
    the book lane's #463 daily legs, reproducing WF 93.8 / 3.82 first).
PASS on every bar -> MANAGER decides the one lockbox read (a pinned, fenced Auto-Validate of a CT304H sibling with a
short_mult knob {1.0, 1.25, 1.5, 2.0} only, or a no-order forward shadow if MANAGER rules the partly-seen WF makes a
lockbox read worthless). FAIL on any -> dead, no variants.

## AMENDMENT - MANAGER review #36 (C:\EdgeLog\manager\reviews\noise_r70_sidetilt_review_2026-10-05.md), before any run
1. FAMILY: Custom ML's NOISE hedge tilt (1.5x NOISE shorts / 0.5x longs while ENGU-Q is long) and this round both
   up-weight NOISE shorts in sell-offs - ONE hunt; if both pass it is one finding, not two. The correlation of the two
   tilted legs' daily difference series is reported once Custom ML's series exists (NOISE exports its own difference
   series for that).
2. Reported with Stage A: per-WF-year long and short P&L, tilted vs #422.
3. Reported with A5: the book's worst walk-forward drawdown in dollars, and the share of that drawdown's dollars that
   fall on days carrying a NOISE short (for #463, the tilted book and the twin).
4. Live note: Webull netting REFUSES a NOISE short while ENGU-Q is long (v73.878) and the caps truncate the rest; the
   full expression exists only on the paper book and the NQ shadows. Nothing changes live without the owner.
5. LOCKBOX ROUTE (decided now): a Stage A pass on every bar -> the pinned, fenced house Auto-Validate of a CT304H
   sibling with short_mult in {1.0, 1.25, 1.5, 2.0} only (date_from 2010-06-07 / date_to 2026-07-16, 900 trials), queued
   the SAME DAY - the one lockbox read and the RUNBOARD entry; runboard_watch verdict with ROC at $30k and DD%; the run
   note says the partly-seen walk-forward makes that read a VETO, not a discovery. Fail = dead, no variants.
