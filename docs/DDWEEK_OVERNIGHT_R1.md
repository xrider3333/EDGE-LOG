# DD-WEEK r1: OVERNIGHT after a down session, as a leg that earns while BOOK #463 falls (pre-registered 2026-10-04)

Written 2026-10-04 by TV (second lane on the drawdown-week earner hunt, MANAGER standing order of 2026-10-04 #28: "a leg
that EARNS while #463 falls ... pre-registered from the mechanism, never fitted to those episodes"; TV takes the
daily-bar / multi-day side on NQ and ES). Written BEFORE any number in it was computed. Harness to be written after this
file is on main: `tools/ddw1_overnight.py`. Results: `C:\EdgeLog\_anatomy_cache\ddweek\r1\` and RESEARCH_LEDGER.md. Any
change after the commit = a dated addendum below, never an edit.

## Why this one, and where it sits on the map

docs/MDL_MAP_R1.md: a leg that earns while #463 falls helps "at almost any positive return: under $5,000 a year" at a
$30k drawdown of its own; an uncorrelated leg needs ~$15,000; a leg that falls with the book needs $40,000+. #463 is four
RTH / multi-day directional NQ-ES legs; its drawdown weeks are sell-offs (2-27 March 2020 is the walk-forward's worst).
The overnight session after a sell-off is a slot none of the four legs trades on purpose, and the published mechanism
says it pays MOST exactly when the cash session has just sold off. So it is the one held-data NQ/ES shape whose payoff is
predicted (not fitted) to land in the book's drawdown weeks.

MECHANISM (Boyarchenko, Larsen & Whelan 2023, "The Overnight Drift", RFS): dealers absorb the end-of-day order imbalance
at the US close; after a sell-off they carry inventory overnight and are paid for it as the imbalance resolves, mostly
around the European open (~02:00-03:30 ET). Prediction: a long held from the US close after a DOWN cash session earns
more than a random night, more so after a large down session, and most of it is in by 03:30 ET.

DISCLOSURE (what was already seen - read this first). RESEARCH_LEDGER 2.13 measured this on NQ only with the OLD roll
detector (19 of 64 switches caught): 01:30 -> 04:00 ET long, $8.5 a trade on all nights, $16.6 after a down session (9 of
16 years); 16:15 -> 09:25 after a down session $90 a trade on 8 of 12 years; "dead for ROC". IDEAS_R4 #4 then listed
"overnight reversal after a down RTH session" as not run because those pre-lockbox numbers were seen. ONDRIFT (r18,
uptrend-only nights) died honest at PF 1.205. NOT seen: ES; the k-scaled cells; any P&L on true rolls; any drawdown-week
number; any book-add number; ANY lockbox number. Because the leg-level walk-forward was seen, Stage A below is a
SCREEN, not evidence of an edge: the clean evidence is the drawdown-week test and the book add (never computed), then
the lockbox (never read) and a forward shadow.

## Rules

- Data: house 5-minute ETH masters, back-adjusted on the true switch bars of `tools/data/rolls_<ROOT>.csv` (source
  db_adj_eth: NQ registry id 71, ES id 62), bars stamped at START, clock US/Eastern. Point differences are the real
  contract P&L across a switch; a hold that crosses a switch time pays 0.25 pt extra. Every array is cut to bars
  before 2025-06-30 00:00 ET BEFORE any signal is computed.
- Eligible session: all 78 RTH bars 09:30-15:55 present (early closes and gappy sessions skipped).
- Signal (known at 15:55): r = close of the 15:50 bar / open of the 09:30 bar - 1. Scale = median |r| of the previous 60
  eligible sessions (at least 40, else no trade).
- Cells, signal: S0 r < 0; S1 r <= -1 x scale; S2 r <= -2 x scale. Exit: E1 = open of the first bar starting at or after
  03:30 ET on the next trading day; E2 = open of the first bar starting at or after 09:30 ET on that day. Markets: NQ, ES.
  = 12 cells (2 x 2 x 3). Friday entries hold to the next trading day (weekend included - the mechanism has no weekday).
  A night whose exit bar is more than 4 calendar days after entry is skipped.
- Trade: long 1 contract at the close of the 15:55 bar (16:00 ET), out at the exit. No stop (the 18b finding: resting
  overnight stops strictly hurt). P&L $ = (exit - entry) x ($20 NQ / $50 ES) - cost.
- Cost per round trip (house rule, as SPREAD r2): NQ 0.533 pt, ES 0.363 pt; + 0.25 pt per switch crossed. Stress = +0.25
  pt per contract.
- Controls, never a pass route: unconditional long overnight (every eligible night) and the up-session mirror (r > 0).
- Stretches: EARLY = first eligible session -> 2016-06-30 (sign check); WF = 2016-07-01 -> 2025-06-29 (the 10-01 house
  convention; #463's own WF).
- P&L is booked on the EXIT date. No position is open at any RTH close, so the daily series is closed = valued daily.
- Family-wide null: within each market, the r values of the eligible WF sessions are shuffled across sessions (one
  shuffle per market per rep, shared by all six cells of that market; scale recomputed from the shuffled series);
  statistic = the MAX over all 12 cells of the WF per-trade t; 500 reps, fixed seed 20261004.
- Yardstick (owner rule 2026-09-28, house convention 2026-10-01): ROC %/yr at a $30,000 worst drawdown = 30 x (net per
  year) / worst drawdown of the daily P&L (every eligible session, zeros included), years = (last - first) / 365.25;
  Sortino = mean / RMS of negative daily P&L x sqrt(252), zero days included.
- #463's drawdown days (WF): from `C:\EdgeLog\_anatomy_cache\rocfrontier\r4\book463_daily.csv` (column mtm, the book's
  daily valued P&L), every peak-to-trough episode of the WF equity whose depth is at least $14,950 (the MDL map's own
  threshold); the drawdown days are the days after each peak through its trough. #463 must first reproduce WF 93.81 /
  Sortino 3.816 / worst drawdown $44,849 on this convention, else nothing runs.

## Stage A (screen, WF) - a cell passes only if ALL hold

a. >= 100 WF trades                                    f. profitable without its single biggest trade
b. ROC @ $30k >= 5 %/yr (the map's floor for a          g. positive in >= 6 of the 9 WF years (RISK r1 check)
   drawdown-week earner)                               h. DRAWDOWN-WEEK EARNER: summed P&L over #463's WF drawdown
c. profit factor >= 1.10                                  days > 0, AND still > 0 without its 3 best nights there
d. t >= 2.0 AND above the null max's 95th percentile    i. net > 0 with 2020-02-01 .. 2020-04-30 removed (RISK r1)
e. net > 0 at the stress cost                           j. EARLY net > 0 (RISK r1's 2010-16 block)

Reported, never a pass route: the daily correlation with each #463 leg and the book, overall and inside the drawdown
days; the map's first-order ratio (P&L during 2-27 March 2020 vs the $3,127 a year per $1,000 lost rule); the Friday-
entry subset; the ten biggest WF nights; both controls.

## Stage A2 (book add, WF, pre-lockbox)

The Stage-A pass with the highest WF ROC @ $30k added to #463's daily mtm at c in {1, 2, 3} contracts; c = the best by
book WF ROC @ $30k, then frozen. Passes only if the book's WF ROC @ $30k >= 98.50 (1.05 x 93.81, the map's bar) AND its
WF Sortino >= 3.816. If no cell passes A, A2 still runs on the S0 cell of each market at c = 1, REPORTED ONLY (it tells
the map where this kind of leg sits; it can never pass).

## Stage C (house Auto-Validate) and Stage B (lockbox, read ONCE) - both wait for MANAGER's line

C: a strategy file on the ETH master that reproduces the frozen cell to the cent, open ranges on k (0-3), the exit time
(02:00-09:30) and the scale window (20-120); ONE Auto-Validate on the runner, 900 trials, pinned date_from / date_to;
RUNBOARD watch list with ROC %/yr at $30k and DD%. It reads the house lockbox, so it is queued only on MANAGER's line.
B (frozen pre-registered cell and c, not the validate's tuned setting): book LB (2025-06-30 -> 2026-06-30 inclusive)
ROC @ $30k >= 155.54 AND Sortino >= 4.150 AND book LB net without its biggest trade > 0 AND the leg's own LB net > 0 on
>= 50 LB trades. The READ flag is written only after the data has loaded and #463's LB reproduces. A pass goes to MANAGER
for the owner's call, with a forward no-order shadow proposed; nothing is adopted here.

Zero passes at A2 = DD-WEEK r1 dead; ledger + memory; the lockbox stays sealed for it.

## How it could fool us

1. The leg-level walk-forward was seen (disclosure) - Stage A screens, it does not prove; h and A2 are the new reads.
2. Down sessions cluster in crises, so the drawdown-week sum can hang on a few nights (March 2020 had limit moves both
   ways overnight) - h's "without its 3 best nights" and i guard it.
3. Weekend holds overlap WKND (dead: continuation beat the fade on the Sunday reopen) - the Friday subset is reported.
4. A 16:00 ET fill is the futures close a quarter-hour after the cash close; REVERT r2 found the 16:00-16:15 drift real
   but under cost, so entry at 16:00 carries a little of it - the stress cost covers part.
5. Twelve cells on two correlated markets - the family-wide null takes the max over all twelve.

## Addendum 1 (2026-10-05, before any number): handed over, not run by TV

MANAGER #30 (2026-10-04) split the drawdown-week hunt: overnight and intraday NQ/ES belong to STRATEGY-BEATING, daily-bar
and multi-day to TV. This draft was handed to STRATEGY-BEATING (their inbox #39) to run or drop under their own name; TV
does not run it. Kept on main as the dated pre-registration it is. Note DAILYFADE (docs/DDWEEK_FADE_R1.md) shares its
long-after-a-down-session piece; if both run they are one piece of evidence.

## Addendum 2 (2026-10-05, before any number): run by STRATEGY-BEATING, the house rules of 10-05 folded in

Written by STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y, which runs this family under its own name (MANAGER #30 / #43; its
queue, MANAGER #59). No number of this family had been computed when this was written. These replace the matching text
above; nothing else changes.

1. HARNESS. TV's `tools/ddw1_overnight.py`, adapted by this lane: it stops unless this file's LF sha256 is the
   registered one, and it stamps that sha and its own into stage_a.json.
2. POINTS, NOT PERCENTAGES (MANAGER's DAILYFADE review, edit 2; the 10-05 percent-read audit). The masters are
   back-adjusted, so a percentage read off them is distorted up to ~3x in the early years. r is now in POINTS: close of
   the 15:50 bar - open of the 09:30 bar. The scale is the median |r| in points over the previous 60 eligible sessions
   (at least 40). S0 / S1 / S2 keep their form (r < 0; r <= -1 x scale; r <= -2 x scale), and the null shuffles the
   point values. Points are shift-invariant; the trade P&L was already in points.
3. NO SKIP ON WHAT HAPPENS AFTER THE ENTRY (ORB's DAILYFADE fix 2). A night is no longer skipped because its exit bar is
   missing or the next session is more than 4 calendar days away: the exit is the open of the first bar at or after the
   exit time on or after the next date with RTH bars, however late. A data hole holds the position through it, as it
   would in a real account. Reported: the nights that cross a weekday without RTH bars (a holiday or a hole) and the
   exits filled more than 30 minutes after their target or on a later date (count and P&L).
4. #463's DRAWDOWN DAYS = MDL r1's. The episode rule must give the house count, 460 WF days in 28 episodes, or nothing
   runs.
5. A2 IS A REPORT, AND c IS SET BY VOLATILITY (MANAGER #45 / #56; the Q9 rule). The pick of the best c in {1, 2, 3} by
   book ROC is withdrawn. Instead c = 25% x std(#463's daily P&L, 2016-07-01 .. 2018-06-29) / std(the cell's daily P&L
   at one contract over the same days), in whole micros (0.1 contract, at least one); the book at 0.5c and 2c is
   reported. An A2 pass (book WF ROC @ $30k >= 98.50 and Sortino >= 3.816) opens a forward BOOK shadow line beside the
   leg's own, nothing more. With no Stage A pass, the S0 cells' A2 rows are still reported at their volatility c, as
   registered.
6. STAGE B IS THE LEG'S OWN VETO (MANAGER #48). Nobody reads #463's lockbox year to pass a book candidate. On MANAGER's
   line, the frozen cell at its frozen c is read once on 2025-06-30 -> 2026-06-30 inclusive. It vetoes unless the leg's
   own LB net > 0 on >= 50 LB trades and > 0 without its biggest trade. The book add on that year is REPORTED, never a
   pass. Stage C is unchanged (MANAGER's line).
7. DISCLOSURE - DAILYFADE (DD-WEEK r2, TV, dead at Stage A 0 / 8 on 2026-10-05, WF only, lockbox untouched). Its money
   was the long side after down sessions held to the next close (NQ +$107k in its every-day flat cell; the short side
   -$58k). The family failed the drawdown-day test: NQ +$8k to +$19k over #463's 460 drawdown days against the null's
   95th percentile of $93k, and negative without its 3 best days; ES lost there (-$17k to -$31k). That long side
   contains this family's mechanism held longer, so this run's drawdown-day test (h) is NOT independent of it. If a cell
   passes here, the owner hears ONE finding with DAILYFADE's failure beside it (as addendum 1 says).
