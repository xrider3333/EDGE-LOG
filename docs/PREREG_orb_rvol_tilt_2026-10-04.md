# PRE-REGISTRATION — ORB round 65: breakout-bar participation size tilt (2026-10-04)

**Status: REVIEWED.** MANAGER (Fable) reviewed it twice and gave GO WITH EDITS: inbox #26 / `C:/EdgeLog/manager/reviews/orb_r65_review_2026-10-04.md`
and #27 / `orb_r65_review2_2026-10-04.md`. Every edit below is in. This file goes to main **before Stage A runs**.

Owner ask via MANAGER (10-04): push the frontier (BOOK #463, WF 93.8 / LB 155.5 %/yr at a $30k drawdown) with
one best remaining ORB shot, pre-registered.

## Why this shot and not another

**An ORB seat swap is a bet on a year that has already been read.** In every ORB seat tested so far (#234, #239,
#314, #257), #463's lockbox drawdown is the same $49,855 (±$400), because other legs set it. So the book's
lockbox ROC moves only with the ORB seat's net in 2025-06-30..2026-06-30. A seat passes only if it out-earns #234
in that one year, and that year has been read for every seat already. A 50/50 #234 + #314 seat fails by
arithmetic: about (155.5 + 147.3) / 2 = 151.4.

**What is already dead on the legal base, so not re-tested:**
- entry structure (0/66: later opening ranges, re-entry, reversal, pyramiding, time stops);
- direction rules;
- filters: prior-day, gap, NR7, OR width, quiet-tape loosening;
- the July side tilt, risk parity and time tilt (retracted or DEAD);
- exits (round 64: ORB already rides);
- event calendars (a noise list);
- travel to ES, ETFs, RTY and YM;
- NQ-100 breadth (NQBRD) and ES breadth;
- re-tuning (#421 and #480 both crowned worse cells).

**What the crown has never used: the breakout bar's own volume.**

*Look-ahead.* With the bar-close confirmation on (`close_confirm`, pinned ON in `ORB_3_6_C2.py`'s parameters),
the entry fills at the close of the bar that closes beyond the range: `ORB_3_6.py` lines 337 and 345,
`entry = sc[k]`. That bar's volume is final at that moment, as known as the close that triggers the trade. The
crown's volume-pace gate reads only the bars before it (`sv[:k]`, line 329). The house already treats this
read as legal on close-confirmed entries (the 08-10 #125 audit). The #205-#209 VOID runs read it on a TOUCH
entry, which is different. **Live parity:** a NinjaTrader or Webull port must compute the same RVOL from the same
completed 5-minute bar, against the same 20-session same-slot reference. Neither port does this today; one is
built only if Stage B passes.

*Prior art against it, answered.*
- (a) In the 08-10 audit, once the entry was close-confirmed, the breakout-bar volume gate earned only about
  $6k over sixteen years ($62,900 to $69,210). "High-volume breakouts work" collapsed with the look-ahead. **The
  signal that survived was the drawdown, which halved ($79,024 to $36,750; MAR 0.05 to 0.12), not the money.**
- (b) The crown already carries a volume-pace gate (cumulative session volume before the breakout bar against
  its 20-session norm at that time of day) and the volatility stand-down. So the bottom third here acts on
  trades that are already volume-gated.

Why a same-bar, time-of-day-normalised rank could still carry information that gate did not:
- the gate measures how busy the session has been so far;
- RVOL measures how much participation the breakout bar itself drew, against that bar's own normal for its
  time of day.

A quiet morning can still produce a heavy breakout bar, and a busy morning a thin one. Expected sign per third:
top above middle above bottom in dollars per trade, with the bottom third (thin breakouts that the busy-session
gate let through) the weakest. If the thirds come out flat or inverted, the shot is dead; the tool prints them.

*Other evidence.* The July RVOL buckets (avg $85 to $365, PF 1.40 to 2.43) were on a leaked touch-entry base and
are NOT evidence. The tilt has never been tested on the legal crown, nor as a size rule. The mechanism fits the
one sizing lesson that held: never size down on wide-range sessions.

**Lockbox disclosure.** ORB's lockbox (2025-08-13..2026-08-13) has been read many times for other questions:
the crown, the round-63 and round-64 seats, and Frontier's seat runs #473, #474 and #478. The tilt itself is
unread there.

**Prior that an arm clears: under 1 in 4.** MANAGER calls 1 in 4 generous given (a).

## The rule (frozen; no grid, no neighbours, no re-pick)

- **RVOL** = the breakout bar's volume divided by the mean volume of the same bar slot (same bar number after
  09:30) over the previous 20 sessions, needing at least 10 of them to have that slot.
- **Size** = RVOL ranked against the RVOL of the previous 250 trades of the same arm (earlier trades only).
  Top third 1.5x, bottom third 0.5x, middle third 1x. The first 250 trades are 1x, so the tilt starts around
  2012. The mean size is about 1 by construction: the test is of aim, not leverage. MANAGER's review 2 fixed
  this cell (1.5 / 0.5 / 250) as the frozen cell.
- **P1** = crown #314 with the tilt. **P2** = #234 (BOOK #463's ORB leg) with the tilt. Entries, exits and costs
  are unchanged. The raw twins are the same trades at 1x.

## Data, windows, parity (as round 64)

- House NQ 5-minute RTH master (db_noadj_rth), warm series 2010-06-07..2026-08-13, 0.533 points, $20 a point.
- Walk-forward stretch 2016-07-13..2025-08-12.
- Parity: each twin's cold lockbox replica must reproduce its stored lockbox trade count and points (#314 168 /
  4,605.081, #234 178 / 4,447.126), or the round stops. That check reads the twin's sum only. **No lockbox figure
  of any arm is computed in Stage A.**
- Book parity: the round's #234 trades must equal #463's stored ORB leg day by day (to $1), or the book part is
  skipped.
- Yardstick on the unified convention: daily-valued net and drawdown inside each stretch,
  years = (last - first) / 365.25, Sortino over every session.

## STAGE A — walk-forward only (per arm against its raw twin; all seven must hold)

1. ROC at a $30k drawdown higher;
2. daily Sortino higher;
3. at least 100 walk-forward trades;
4. **family-aware null, both halves.** The family is every size sequence using the same three sizes in the same
   proportions on the same trades. The ROC gain must beat the 95th percentile of:
   - (a) 500 per-trade shuffles of the arm's own walk-forward sizes (aim, not shape);
   - (b) 500 circular time-shifts of its size sequence by 50 or more trades (keeps the clustering, so a sequence
     that wins only by being big in the right months fails).
5. **paired block bootstrap:** the arm's and twin's daily walk-forward P&L, resampled together in 20-session blocks,
   1,000 draws. The 5th percentile of the ROC difference must be above zero;
6. **breadth:** the paired statistic d = (size - c) x one-contract P&L, with c = the walk-forward mean size, summed
   by walk-forward year, is positive in at least 6 of 9 years. The years are nine 365-day blocks from 2016-07-13;
   the last block absorbs the final month to 2025-08-12;
7. **without Feb-Apr 2020:** the walk-forward ROC gain, recomputed with 2020-02-01..2020-04-30 removed from both
   series, keeps its sign.

**Reported in Stage A, never judged:**
- the 2010-06..2016-07 block (sign; the tilt starts after 250 trades, so its first years are untuned);
- the share of 1.5x and 0.5x trades by year;
- trades, mean $ and PF per RVOL third (expected order: top > middle > bottom);
- the top-minus-bottom gap and its standard error (power);
- RVOL's rank correlation with the opening-range width;
- a skip-the-bottom-third filter version, for the record only (filters have failed every time).

**Book readout in Stage A — walk-forward only.** #463 with its ORB seat sized (P2; P1 reported) on the book's own
walk-forward window 2016-07-13..2025-06-29. To pass, it needs ROC and Sortino above #463 on that window (#463
reads 94.0 there; the reference is 93.8), and must not be behind by calendar year 2011..2025-06-29.

**ORB's own lockbox window (2025-08-13..2026-08-13) differs from the book's (2025-06-30..2026-06-30).** The
book's lockbox is read ONCE, by FRONTIER, on the book's windows and the 10-01 convention, and only after Stage B
passes.

**Power, stated before the data.** About 430-480 walk-forward trades per third. ORB's per-trade spread is wide (a
typical loss is about $900, a target trade $15-25k). So the gap between the top and bottom thirds must be roughly
$250-350 a trade to stand two standard errors clear. Power is marginal: a fail is weak evidence of no effect,
not proof.

## STAGE B — THE one lockbox read (only for an arm that passes Stage A)

A fenced house Auto-Validate on the runner:
- a strategy file applying the tilt inside the engine;
- narrow open ranges on the tilt only: top size 1.25 / 1.5 / 1.75, bottom 0.5 / 0.75 / 1.0, ranking window
  150 / 250 / 400 (27 cells), with **the frozen cell 1.5 / 0.5 / 250 inside the grid**;
- the crown's own settings pinned;
- window 2010-06-07..2026-08-13, 12-month lockbox, the 900-trial budget, ES transfer.

**The frozen cell's lockbox row is the lockbox read** (same rule as NOISE round 69). To pass, its ROC at a $30k
drawdown and its Sortino must be above the raw twin's lockbox, with at least 50 lockbox trades, and the lockbox
must stay profitable without its biggest trade. The region (folds, PBO, neighbours) is reported. The validate's
own crowned cell is never the candidate.

**If an arm passes Stage B:** the frozen cell becomes a no-order paper shadow beside its twin, under the paired
sequential stop (c = running mean size). If P2 also passed the Stage A book readout, FRONTIER reads the book's
lockbox once for the owner's call.

**If no arm passes:** written up DEAD. **The ORB lane's frontier work is then the shadows only:** #239, #257 and
the order-flow forward test.

## The regime question (MANAGER's lane note) and why it is not this shot

MANAGER asked whether ORB's improvement is a regime the book can see in advance. The evidence leans against
making that the shot:
- the improvement is a slow trend across 200-trade blocks (permutation p 0.03), present in configs nobody
  selected, so a proxy would have to predict a trend, not a state;
- quiet tape is already sized to zero by the volatility filter, which round 5 priced as drawdown insurance
  costing $31,000;
- volatility-target sizing is DEAD on ORB ($397k to $124k);
- sizing up in high volatility is leverage that the $30k-drawdown yardstick charges for;
- calendars were noise in the event scan.

## Disclosures (before Stage A)

1. **Smoke runs on PERMUTED volumes.** Two code-path runs used `--smoke`, which randomly permutes the bar
   volumes, so no real tilt effect can appear. Both reproduced both twins and #463's ORB leg to the cent.
2. **The first smoke run printed three REAL regime reads**, which do not use volume. Accepted by MANAGER (review 2):
   - realised volatility shows no ordering (#314 PF 1.42 / 1.50 / 1.34 low / mid / high; #234 1.33 / 1.52 / 1.25);
   - the day after a quiet-tape stand-down is mixed (#314 PF 1.34 on 60 trades; #234 1.82 on 40);
   - roll week stands out (#314 PF 2.14 on 97 trades vs 1.35; #234 1.57 on 116).

   **Roll week is a forward read or its own pre-registered calendar test with a family-aware null, never this
   round.** Those lines were removed from the Stage A tool.
3. **The second smoke run printed the twins' walk-forward and 2010-16 figures**, which do not use volume either:
   - #314 walk-forward ROC 35.3, Sortino 2.20; #234 34.2, 2.08 (both already known from round 64);
   - 2010-06..2016-07 ROC #314 0.6, #234 -0.2;
   - #463 94.0 on the book's walk-forward window.

   None of these says anything about the tilt.

Tool: `tools/orb_r65_rvol_tilt.py` (Stage A; `--smoke` = permuted-volume code check). Results: `ORB_ROUND65_RVOL_TILT.md`.
