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

Run 2026-09-28 (`tools/dip3_triage.py`; leg-split parity exact: 1,593 trades / $524,434 on #452, 1,336 /
$600,514 on #433). ROC @ $30k DD (daily-valued) and daily Sortino:

| Cell | ES #452 WF | ES #452 LB | NQ #433 WF | NQ #433 LB | Whole DD ES / NQ |
|---|---|---|---|---|---|
| RAW | 13.2 / 1.03 (951 tr) | 54.9 / 1.36 (115 tr) | **26.9 / 1.62** (789 tr) | 42.2 / 0.97 (94 tr) | $71,941 / $53,267 |
| CAP1 | 5.7 / 0.65 | 34.8 / 0.85 (39 tr) | 19.5 / 1.30 | 10.6 / 0.32 (43 tr) | $33,774 / $23,425 |
| CAP2 | 8.9 / 0.79 | 34.6 / 0.81 | 17.7 / 1.37 | 19.4 / 0.57 | $42,149 / $47,344 |
| TBX | 10.9 / 0.86 | 54.9 / 1.36 | 29.7 / 1.71 | 30.8 / 0.86 | $69,785 / $48,027 |
| CAP1+TBX | 3.0 / 0.44 | 34.8 / 0.85 | 16.1 / 1.16 | 4.9 / 0.18 | $46,659 / $27,730 |
| CAP2+TBX | 5.1 / 0.61 | 34.6 / 0.81 | 23.7 / 1.54 | 15.9 / 0.47 | $55,394 / $43,766 |

**Verdict: all five rule cells DEAD.** Every cap halves the drawdown but cuts return by more, so return per
unit of drawdown FALLS: the legs that fire together are not duplicates, each earns its own bounce. The
trend-break exit helps NQ's walk-forward (26.9 -> 29.7) but hurts ES and both lockboxes. Nothing is queued.

**What it teaches:** DIP's drawdown is the price of its exposure, not waste inside it. At matched risk the
RAW NQ file is already respectable (26.9 %/yr at $30k in the walk-forward, 42.2 in the lockbox); the book
problem is that its drawdown lands in the same crash as the book's, which no in-file rule tested here fixes.
Ideas 3 (volatility-scaled size), 4 (cross-market confirmation) and 6 (24h sessions) remain untested.

## Addendum A (pre-registered 2026-09-28, after the cells above, before running it): idea 3, volatility-scaled size

Cell **VOL**: each trade's notional = $100,000 x min(1, v_med / v20), where v20 = standard deviation of the
20 daily adjusted-close returns before the entry day and v_med = the median of v20 over the 252 sessions
before that (both causal); whole micros as the file rounds them. Everything else RAW. Same bar as above
(beat RAW on ROC @ $30k DD and Sortino in WF and LB on both markets; 100 / 50 trades; LB > 0 without its
biggest trade). No other scaling variant is tried.

**Addendum A result (2026-09-28): VOL is DEAD by its bar.** ES #452: WF 13.2 -> **19.7** %/yr at $30k, Sortino
1.03 -> 1.22, whole drawdown $71,941 -> **$44,305** (under the book's $48,364 cap); LB 54.9 -> 53.0 (fails by
1.9), Sortino 1.36 -> 1.38. NQ #433: WF 26.9 -> 23.5, LB 42.2 -> 32.2 (fails). Pre-registered as "both
markets", so it stops here. Stated for the owner, not acted on: on ES alone it is the first DIP rule to bring
the drawdown under the book cap while raising walk-forward return per unit of risk; a single-market re-test
would have to be registered fresh and judged on data it has not seen.
