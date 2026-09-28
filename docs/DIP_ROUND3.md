# DIP round 3 — ideas and a pre-registered triage (2026-09-28, owner ask via MANAGER inbox #15)

Written before any number below was computed. Yardstick = the owner rule of 2026-09-28: **ROC %/yr at a $30k
worst drawdown** (= 30 x (net per year) / worst drawdown, drawdown valued DAILY), walk-forward and lockbox
apart; a rule variant must beat its raw twin on that number AND on Sortino in both stretches; at least 100
walk-forward and 50 lockbox trades; the lockbox profitable without its biggest trade.

Why DIP is out of the book: its drawdown ($68-72k valued daily on ES) breaks the book's $48k cap, and the
damage is the Feb-Mar 2020 crash. A price stop was tried (round 2) and the search chose none.

## Ideas (dead hunts checked: no re-test of rotation, sector/non-equity widening, trend-following, calendar
## tilts, short mirrors, learned ML gates, crash stops)

| # | Mechanism (why it should make money / cut drawdown) | Change | Data | Expected effect | Cost | Main way it fools us |
|---|---|---|---|---|---|---|
| 1 | **Exposure cap across legs.** The 4-7 DIP legs are correlated reads of the SAME dip; in a crash they all fire and stack up to 4-7 x $100k of long exposure. Capping concurrent positions keeps one dip = one bet | max concurrent positions across legs, fixed at 1 or 2 | existing | drawdown down roughly in proportion to the stacking; return down less (skipped trades are duplicates) | local minutes; validate if survivor | fewer trades can look smoother by luck; the cap skips whichever leg fires second |
| 2 | **Trend-break exit.** Every leg enters only above the trend average; when the close falls below it the entry premise is gone. An exit on that, not on a price level, leaves normal dips alone and gets out of regime breaks (2020, 2022) | exit next open after a close below the leg's own trend SMA | existing | cuts the long crash holds; small cost in V-shaped recoveries | local minutes | 2020 is one event; a rule that fixes one crash can be a story about one crash |
| 3 | **Volatility-scaled size (fixed rule).** Same trade, smaller in high volatility: notional x (median / current 20-day vol), capped at 1x | size only | existing | shrinks crash-period losses; the one kind of sizing with prior support | local | must beat the raw twin at matched drawdown, not just shrink it |
| 4 | **Cross-market confirmation.** Take the ES dip only if NQ is also in a dip that day (and vice versa) - a broad sell-off bounces, a one-index wobble is noise | entry filter | existing NQ+ES | fewer, better trades | local | a filter on the signal day, fine; but it halves trade counts toward the 100/50 minimums |
| 5 | **ES + NQ as one capped DIP book** (idea 1 across markets): one dip = one position in whichever index fired first | book-level cap | existing | the uncorrelated-to-#463 diversifier with half the stacking | Frontier book run | book weights are an owner call |
| 6 | **Session transfer: DIP on the 24h master.** Signals read on the RTH close miss overnight capitulation | daily bars from ETH sessions | existing ETH masters | modest; different entry prices | validate | roll handling on 24h data needs the bar-level table (have it) |
| 7 | **Hold cap on the no-limit legs.** The RSI and N-day legs can hold for weeks in a slide; a fixed 10-session cap like the pullback leg's | exit rule | existing | trims tail holds | local | a hold cap is a parameter; fix it at 10 (the pullback leg's default), no search |

## Pre-registered triage: ideas 1 and 2 (plus both together)

Local harness `tools/dip3_triage.py`, frozen champions (pre-lockbox picks) of **#452** (`NQDIP_1_3.py` on ES)
and **#433** (`NQDIP_1_2.py` on NQ), db_noadj_rth, true rolls, 2010-06-07..2026-08-24.
Stretches: **WF** = the runs' walk-forward window 2016-07-18..2025-08-22; **LB** = 2025-08-24..2026-08-24
(trades entered in the stretch). Cells, fixed now: RAW; CAP1 (at most 1 open position across legs); CAP2 (at
most 2); TBX (trend-break exit); CAP1+TBX; CAP2+TBX. Six cells x two markets.
Approximation stated up front: the cap is applied to the file's trade list in entry order (a skipped leg is
treated as flat until its original exit); the trend-break exit truncates each trade at the first close below
its trend SMA and re-prices it on the adjusted series. The file versions come only for survivors.

**A cell SURVIVES only if, on BOTH ES and NQ:** ROC @ $30k DD beats RAW in WF AND in LB; daily Sortino beats
RAW in WF AND LB; >= 100 WF trades and >= 50 LB trades; LB net > 0 without its biggest trade.
**Book relevance (reported, not gated):** whole-run drawdown valued daily vs the $48,364 cap.
At most the best TWO survivors (by WF ROC @ $30k on ES) go to Auto-Validate as file versions.

## Results

_(filled in after the triage)_
