# PRE-REGISTRATION — NOISE round 69: is NOISE #422's compression size-up too small? (2026-10-04, revised after review; amended per MANAGER call #28)

Owner ask via MANAGER (inbox #26): push the frontier (BOOK #463: WF 93.8 / LB 155.5 %/yr ROC at a $30k worst drawdown
valued daily, Sortino 3.82 / 4.15) with ONE best remaining NOISE shot. Draft 1335ea5e; MANAGER review GO WITH EDITS
(inbox #27, C:\EdgeLog\manager\reviews\noise_r69_review_2026-10-04.md); this text carries all eight edits. The only
numbers computed before this commit: the parity of stored run #422 and the power line below (spread only).

## The question and why it is the one shot
Every other NOISE lever is closed (filters, entry timing, exits incl. three breakeven tests, pyramids, order flow, ES and
overnight information). The corpus lesson: survivors keep every trade and re-size it from state, and #422's
hourly-compression size-up is the one NOISE change that has held. ROC at a $30k drawdown is leverage-free, so only the
RELATIVE weight of compressed vs other trades can move it. Hints that 1.75x is too small: #422's validate crowned 1.75x at
the TOP edge of its 1.25 / 1.5 / 1.75 grid; round 62 found that KEEL's squeeze multiplier (~2.6x on the same 615
compressed trades) made money and return per drawdown worse when removed.

## DISCLOSURE (edit 1): the lockbox is partly seen for this family
#422's validate read the lockbox at 1.25 / 1.5 / 1.75x, and round 62 read walk-forward AND lockbox with KEEL's multiplier
putting ~2.6x on these trades. KEEL as a whole FAILED walk-forward on NOISE (09-27 export), so the round-62 hint is an
ablation inside a failing model. A lockbox pass at 2.25x is therefore CONFIRMATORY, not discovery; the weight of this
round is the walk-forward, the paired test and the book readout.

AMENDMENT (MANAGER #28, after a further disclosure by NOISE, before any 2.25x number): the WALK-FORWARD near 2.25x is
partly seen too. Custom ML's 09-27 'fixed' #422 package (C:\EdgeLog\book_legs\NOISE422_fixed; run #457 / round 61
addendum B) put ~2.6x on the same compressed trades together with Friday 1.5x, an FOMC 0.5x and a cap of 3; its WF
read about 109-112 ROC at $30k against #422's 85, and its lockbox was glimpsed at book level. This round is therefore
CONFIRMATORY. What that read did not answer, and Stage A does at no lockbox cost: does the compression weight ALONE
carry it (the package mixed three tweaks), and is it broad (6 of 9 years) under a paired test?

## Rule, fixed now
NOISE #422 unchanged (crown core, 60-minute compression gate 20 bars, ratio 1.15) except the size on a compressed decision
bar: PRIMARY 2.25x (others 1x). Neighbours reported, never picked from: 2.0x and 2.75x. Twin = #422 at 1.75x. Per-trade
size arithmetic as the strategy file (s x net); legs rebuilt with round 68's harness, reproducing NOISE_1_8_CT304H trade
for trade. Data: NQ 5-minute RTH no-adjust master to 2026-09-16, cost 0.533/contract, $20/pt, $100k.
Predicted shape (edit 4): concave with an interior top, or a flat top. A monotone rise 1.75 < 2.0 < 2.25 < 2.75 is NOT a
stronger pass; it is recorded as "top edge again". The grid is never extended past 2.75x after any result.

## Parity gate (edit 6) - DONE before this commit
Round 68's harness reproduces stored run #422 on the yardstick: WF 2,805 trades, ROC@30k 84.6, Sortino 4.49, drawdown
$17,590; LB 314 trades, 118.1, 3.34, $17,053 (round 68 / round 62 recompute). Any mismatch at run time aborts the round.

## STAGE A - walk-forward ONLY (edit 2). The 2.25x lockbox is NOT computed by hand.
All of these must hold on WF 2016-06-30 .. 2025-07-16:
A1. 2.25x beats #422 on ROC at a $30k drawdown AND Sortino; >= 100 trades.
A2. Both neighbours beat #422's WF ROC at $30k.
A3. Paired difference (edit 3a): stationary block bootstrap (mean block 20 trading days, 1,000 draws, seed 20261004) of
    the daily-valued P&L of 2.25x and 1.75x resampled TOGETHER; the 5th percentile of the WF ROC-at-$30k difference
    (2.25x minus 1.75x) is above zero.
    POWER, stated before running (tools/r69_noise_power.py, spread only, no 2.25x number): the difference's annual mean
    has a block-bootstrap SE of $1,813/yr against #422's $17,590 WF drawdown, so the smallest WF ROC-at-$30k gain this
    test detects at 80% power is about 7.7 points. A real but smaller gain will FAIL - the test is deliberately
    conservative.
A4. Breadth (edit 3b): 2.25x beats 1.75x on ROC at $30k in at least 6 of the 9 WF years (nine consecutive years from
    2016-06-30, the last one ending 2025-07-16; valued daily inside each year).
A5. Book walk-forward - INFORMATION ONLY after amendment #28 (no longer a bar): BOOK #463 with its NOISE leg at 2.25x,
    raw (no V2), the 10-01 unified convention (valued daily, exit-day stamping as of 10-02), read by the book lane
    against WF 93.8 / Sortino 3.82 on the exported walk-forward leg.
Sanity line only (not a bar): 1,000 shuffles of the 2.25x cell's own sizes across WF trades.
A Stage A fail closes the round (recorded dead) and #422 stays at 1.75x.

## STAGE B - DROPPED (amendment #28): no lockbox read in this round
A third glimpse of a partly seen lockbox proves nothing, so the fenced Auto-Validate is not run. If Stage A passes
on EVERY bar (A1-A4), the frozen 2.25x cell becomes a NO-ORDER forward shadow leg beside #422 in the nightly paper
run, judged under the paired sequential stop (c = frozen WF mean relative size; docs/PREREG_paired_sequential_
stop_2026-09-29.md) at 50 closed trades; the book readout stays walk-forward information. A FORWARD pass, not this
backtest, is the only thing that could ever move #422's size. If Stage A fails on any bar the round is recorded dead
and #422 stays at 1.75x.

## Not read (edit 7) and live (edit 8)
The 2026-07-16 .. 09-16 tail is read in neither stage (an INFO row at most, after everything else is written). Webull's
per-leg caps (20 shares a leg, 40 total) [CORRECTION 2026-10-05, MANAGER assessment: the caps were raised to 60 a leg / 80 total on 2026-09-24 - the box configs and the forward-log columns carry 60 / 80; the original text is kept] would truncate a 2.25x tilt, so any live effect is smaller than the test; a pass
changes nothing live or in the book without the owner.
