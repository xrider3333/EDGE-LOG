# TV NEW-TYPE round 1 - three new strategy TYPES on fund dailies (DRAFT pre-registrations, 2026-10-05)

DRAFTS for MANAGER (adversarial review; standing-order addendum #40: "a lane whose family is exhausted hunts NEW STRATEGY TYPES
... queue of 3 new-type preregs within 24 hours ... Stage A walk-forward only"). Written before any number of any of the three
exists. Families are research names until something passes (then the vocabulary gets the name in one commit, CLAUDE.md rule):
**PAIRS**, **BAB**, **ONMOM**; RUNBOARD rows file them under MISC by research id. Harness after review: `tools/tvnt1_triage.py`;
results `C:\EdgeLog\_anatomy_cache\tv_newtypes_r1\` + RESEARCH_LEDGER.md. Any change after the commit = a dated addendum.

## Why these three, and what is different from the dead list

TV's daily-bar NQ/ES list is used up (MANAGER #299: daily trend, short mirrors, DIP variants, calendar, rotation, daily NQ-ES spread,
vol targeting, DAILYFADE all dead). The three below are relative-value / cross-sectional mechanisms on the fund dailies we already
hold, none of which the house has computed (ledger and memory searched: no pairs, no beta-sorted, no overnight-clientele test):
- **PAIRS** is mean REVERSION of economically linked pairs - rotation (dead) bought relative STRENGTH; SPREAD r1/r2 (dead) were NQ-ES
  ratio MOMENTUM (daily) and first-hour continuation (intraday). Different sign, different assets.
- **BAB** sorts on trailing BETA, not on past return (rotation) and not on price dips (DIP / sector DIP widening, dead), and is built
  beta-neutral - not a defensive tilt and not a short mirror.
- **ONMOM** is persistence of the OVERNIGHT component across funds (a clientele effect). TRANSFER r2 (dead) moved the house crowns
  to funds' cash sessions; the DD-WEEK r1 overnight draft (now STRATEGY-BEATING's) is NQ/ES after a down day. ONMOM is cross-
  sectional, on funds, conditioned on each fund's own overnight history. If MANAGER rules the overnight slot covers funds too, ONMOM
  goes to STRATEGY-BEATING unchanged.

## The map (docs/MDL_MAP_R1.md) - placed before drafting

All three are built market-neutral, so their correlation with #463 in its drawdown weeks should sit near zero: the map's line is
~$15k a year at a $30k drawdown of their own (ROC @ $30k >= 15) to lift #463 half the time. BAB has a second, stated route: it is
long the low-beta (defensive) funds, so it may EARN in #463's drawdown weeks (2022, 2025-04 were defensive-led), where the map
needs < $5k a year - that route is a pre-registered alternative bar below, held to a null, never a free pass.

## Shared rules (all three)

- DATA (no new pull): Yahoo daily, dividend- and split-adjusted opens and closes (one factor for O and C, so an overnight return
  across an ex-date is right): `C:\EdgeLog\_research_cache\sector_open/close.csv` (SPY + XLB XLE XLF XLI XLK XLP XLU XLV XLY),
  `nonequity_open/close.csv` (DBC FXA FXE FXY IEF SHY SLV TIP USO UUP), and the registry's yahoo_adj masters QQQ IWM GLD TLT. Each
  file's sha256 is printed with the result. Every array is cut before 2025-06-30 before any signal. SHY is excluded (no movement).
- TIMING: signals at the close of day t from data through t; fills at the OPEN of t+1 (PAIRS, BAB) - never at the signal's own
  print. ONMOM fills at the close by design (its trade IS the overnight) with a signal fixed from data through t's open.
- COSTS per side, of notional: 2 bps for SPY QQQ IWM the nine SPDR sectors TLT IEF GLD; 5 bps for SLV TIP DBC USO UUP FXA FXE FXY;
  stress = double. Short borrow 0.25 %/yr on short notional (all are general collateral). No compounding; $100,000 account.
- STRETCHES: EARLY = 2007-03-01 (every fund trading) -> 2016-06-30, sign check; WF = 2016-07-01 -> 2025-06-29 (#463's own WF);
  LB = 2025-06-30 -> 2026-06-30, sealed.
- YARDSTICK: daily P&L marked at every close; ROC @ $30k = 30 x (net / years) / worst drawdown; Sortino with zero days; #463's
  drawdown days = peak-to-trough episodes of its WF daily mtm (r4/book463_daily.csv) >= $14,950 deep; #463 must reproduce
  93.81 / 3.816 / $44,849 first. Reported for every cell: the drawdown-day P&L and its correlation with #463 there (rho_dd), the
  realised beta to SPY overall and in the drawdown days.
- STAGE A2 (WF): the best Stage-A pass by WF ROC @ $30k added to #463's daily mtm at c in {0.5, 1, 2}; book WF ROC >= 98.50 AND
  Sortino >= 3.816 (best c frozen - a selection step, acceptable because Stage B reads once).
- STAGE B (MANAGER's line; the frozen cell and c): book LB >= 155.54 with Sortino >= 4.150; the leg's own LB >= 50 trades (or 50
  weekly rebalances for BAB), net > 0, and > 0 without its biggest trade.
- STAGE C: a multi-fund basket is no engine job type, so a pass = a written forward paper shadow + an owner call, on the RUNBOARD
  by research id (v73.1022 research rows) with ROC @ $30k and DD%.
- Every family: zero passes at A2 = dead; the next draft is a new mechanism, never a re-tune.

## 1. PAIRS r1 - mean reversion of economically linked fund pairs (Gatev, Goetzmann & Rouwenhorst 2006)

MECHANISM. Two claims on overlapping cash flows (the same yield curve, the same commodity complex, overlapping index members) are
held apart by arbitrage capital; temporary flow and liquidity shocks push the price ratio away and it converges.
PAIRS, fixed now by economics, never by a screen: IEF/TLT (curve), TIP/IEF (breakeven inflation), GLD/SLV (gold-silver ratio),
XLK/QQQ (tech overlap), XLE/USO (energy equity vs crude), XLP/XLU (two defensives), XLB/XLI (materials vs industrials),
SPY/IWM (large vs small).
SIGNAL (close t): beta = OLS slope of log A on log B over the previous 120 sessions; spread = log A - beta x log B; z = (spread -
its 60-session mean) / its 60-session std. ENTRY at the next open when |z| >= Z: short the rich leg, long the cheap leg, $50,000
of A against beta x $50,000 of B. EXIT at the next open after z crosses 0, or after 20 sessions. One position per pair at a time.
CELLS: Z = 2.0 and Z = 2.5 (2 cells, the eight pairs pooled into one book per cell).
NULL (family-aware): for each pair, entries on random sessions (same count, same holding lengths, direction by coin), costs re-
applied; statistic = the MAX over the 2 cells of WF ROC @ $30k; 500 draws, seed 20261005.
STAGE A (WF, per cell): >= 100 trades; ROC @ $30k >= 15; PF >= 1.10; t >= 2.0 and ROC above the null's 95th percentile; net > 0 at
the stress cost; profitable without its biggest trade AND without its best pair; positive in >= 6 of 9 July-June WF years;
net > 0 without 2020-02-15 .. 2020-04-30; EARLY net > 0.

## 2. BAB r1 - betting against beta across the equity funds, weekly (Frazzini & Pedersen 2014)

MECHANISM. Investors who cannot or will not borrow buy high-beta assets for their implied leverage, so high-beta assets are priced
too high and low-beta too low; a portfolio long low-beta levered to beta 1 and short high-beta de-levered to beta 1 earns that
premium with no market exposure ex ante.
UNIVERSE: the nine SPDR sectors + QQQ + IWM (11). BETA (Friday close): daily-return beta to SPY over the previous 252 sessions,
shrunk 0.6 x beta + 0.4 x 1 (the paper's shrink). Rank; long the K lowest-beta funds equally, short the K highest; long notional
$50,000 / mean beta of the long side, short notional $50,000 / mean beta of the short side (both sides beta 1 at $50k). Rebalance
at Monday's open; hold the week.
CELLS: K = 5 and K = 3 (2 cells). Control, never a pass route: the same longs and shorts at equal dollars (a net-short-beta
defensive tilt - the thing BAB must NOT be mistaken for).
NULL: each week the long and short sets drawn at random from the 11 (same K), same scaling and costs; statistic = MAX over the 2
cells of WF ROC @ $30k (and, for route 2, MAX of the drawdown-day sum); 500 draws, seed 20261005.
STAGE A (WF, per cell): >= 400 weekly rebalances; |realised beta to SPY| <= 0.20 over WF (else it is a hidden directional bet -
fails outright); net > 0 at stress; profitable without its best week; 6 of 9 years; net > 0 without 2020-02-15 .. 04-30;
EARLY net > 0; and EITHER route 1: ROC @ $30k >= 15, PF >= 1.10, ROC above the null's 95th pct, OR route 2 (drawdown-week
earner): ROC @ $30k >= 5 AND #463 drawdown-day P&L > 0, still > 0 without its 3 best days, AND above the null's 95th pct of the
drawdown-day sum.

## 3. ONMOM r1 - persistence of the overnight component across funds (Lou, Polk & Skouras 2019, "A Tug of War")

MECHANISM. Different clienteles trade at the open (retail, news-driven) and at the close (institutions, flows), so a fund's
overnight returns persist: funds with high recent overnight returns keep earning overnight. Trade only the overnight.
UNIVERSE: the 20 funds above minus SHY (11 equity + TLT IEF GLD SLV TIP DBC USO UUP FXA FXE FXY = 21). SIGNAL (fixed at t's
open, so known well before t's close): the sum of each fund's overnight returns (open / previous close - 1) over the previous L
sessions through t's open. Long the 5 highest, short the 5 lowest, $10,000 each, at t's CLOSE; out at t+1's OPEN. Every night.
CELLS: L = 20 and L = 60 (2 cells). Controls, never a pass route: long all 21 overnight (the plain overnight drift); the mirror.
NULL: each night the 5 longs and 5 shorts drawn at random from the 21, same costs; statistic = MAX over the 2 cells of WF ROC
@ $30k; 500 draws, seed 20261005.
STAGE A (WF, per cell): >= 1,800 nights traded; ROC @ $30k >= 15; PF >= 1.10; t >= 2.0 and above the null's 95th pct; beats its
mirror; net > 0 at stress (it pays two sides every night on ten funds - the stress cost is the main way it dies); profitable
without its best 5 nights; 6 of 9 years; net > 0 without 2020-02-15 .. 04-30; EARLY net > 0.

## How these could fool us

1. Fund dailies are adjusted closes from one vendor pull (Yahoo restates recent bars - memory; the cut at 2025-06-30 is far from
   the restated tail). 2. PAIRS: a pair that broke for good (XLE/USO in the 2020 negative-oil month, USO's 2020 restructuring) can
   carry or sink the book - the "without its best pair" veto, and the reported per-pair table. 3. BAB on 11 funds is thin: sector
   betas move slowly, so the long and short sets change rarely - turnover and the set-change count are reported. 4. ONMOM's open
   prints are auction prints; a fund that does not trade at 09:30 has a stale open - reported count of zero-overnight-return days.
5. Three families x two cells: each family's null covers its own cells; the round is three hypotheses and is reported as such.

## Addendum 1 (2026-10-05 07:58 MST, PRE-DATA - MANAGER house line #43)

No number of any of the three existed when this was written. For a NEW STANDALONE leg the standalone Stage A bars decide; the
book add is a REPORT. So, replacing the matching lines above: Stage A2 (book add at c in {0.5, 1, 2}) is computed and printed
for every Stage-A pass but gates nothing - it decides only whether a forward BOOK shadow line is ALSO proposed. A family is
dead when no cell passes STAGE A (not A2). A Stage-A pass goes the same day to (i) a RUNBOARD research row with WF ROC @ $30k
and DD, and (ii) because a multi-fund basket is no engine job type and cannot be Auto-Validated, a written forward paper
shadow with its own bar for MANAGER and the owner; Stage B (the sealed year) becomes the LEG's own veto (its LB net > 0 on
>= 50 trades and > 0 without its biggest trade), the book add on that year report-only. The power line: each family's
minimum detectable ROC @ $30k is printed from its null's spread (95th minus 50th percentile) beside the result.

## Addendum 2 (2026-10-05 08:15 MST, PRE-DATA - MANAGER review C:/EdgeLog/manager/reviews/tv_newtypes_r1_review_2026-10-05.md)

Still no real-data number of any of the three exists (the results folder had not been created). Folded in before Stage A runs:
1. HOUSE LINE #45. The book add is a REPORT at ONE c fixed from volatility, not the best of {0.5, 1, 2}: c = 0.25 x the daily std
   of #463's WF mtm over the first two WF years (2016-07-01 .. 2018-06-30) / the cell's daily std over the same two years. Stage B
   = the leg's own sealed-year veto (one shared day, per LOOKS r1); the book add on that year is reported only. A Stage-A pass ->
   a RUNBOARD research row the same day + a written forward paper shadow.
2. BAB r1 IS THE HOUSE'S ONE BAB TEST (FRONTIER's Q14 sector BAB is withdrawn and reads these cells in the seat frame). Added to
   every BAB cell's report (never a gate): the leg's dollars over #463's drawdown days WITHOUT #463's single best episode for the
   leg (episodes = the peak-to-trough runs >= $14,950 that define the drawdown days), the per-year (July-June) net rows, and the
   vol share = the leg's share of the combined variance at c, c x cov(leg, #463 + c x leg) / var(#463 + c x leg). BAB is
   always on (every week held), so that share is the cost it charges the book on every day.
3. PAIRS: a pass must ALSO hold with XLK/QQQ and SPY/IWM removed: the same cell recomputed on the six remaining pairs must clear
   the Stage A checks that do not depend on the 8-pair null (ROC @ $30k >= 15, PF >= 1.10, t >= 2.0, stress > 0, ex-top > 0,
   6 of 9 years, ex-2020 > 0, EARLY > 0; >= 100 trades). Printed as a row, not a new cell.
4. BAB: realised beta to SPY printed PER July-June YEAR as well as over WF, and the long side's leverage per week = 1 / mean
   shrunk beta of the long set (min / median / max over WF weeks; $100k gross per week printed too).
5. ONMOM, exactly: the formation window is L sessions of overnight returns (open_s / close_{s-1} - 1), s = t-L+1 .. t, the last
   being t's own overnight, so the signal is known at t's opening print; the fill is the official closing print of t (the Yahoo
   daily close, which is the closing auction - no 15:55 bar is used) and the exit is t+1's official open. The long five and the
   short five are reported apart (each with its own costs; borrow on the short five). Also reported: the count of zero-overnight
   days per fund (stale-open check, "how these could fool us" item 4).
6. Two harness corrections found in TV's own pre-run read (no number seen): (a) BAB's "best week" veto and its PF / t were being
   read per SIDE-week (long and short legs of the same week as two trades); trades are now summed per week before any veto.
   (b) BAB's beta gate is read on the side-notional basis the draft sizes on ($50,000 beta-1 per side): |dollar beta / $50,000|
   <= 0.20; the per-$100k-account figure is printed beside it. Beta estimates are computed once per week and shared by the cells
   and every null draw (the null permutes NAMES, not estimates - unchanged).

## RESULTS - Stage A, walk-forward only (run 2026-10-05 08:09-08:40 MST, harness c4f69c59; lockbox never loaded)

#463 reproduced 93.81 / 3.816 / $44,849 first. Data sha256 (first 16): sector_open a33b4a4795cbe9c0, sector_close 2ee801f82f8fd9c5,
nonequity_open 3445e27cfabd0b87, nonequity_close 210a504e49780085; last bar 2025-06-27. Full printout and JSON:
`C:\EdgeLog\_anatomy_cache\tv_newtypes_r1\` (stage_a_run_2026-10-05.log, stage_a_PAIRS_BAB_ONMOM.json).

**ALL THREE FAMILIES DEAD - 0 of 6 cells pass Stage A.** Per the shared rules the next draft in each is a new mechanism, never a re-tune.

- **PAIRS** (null 95th 8.5, 50th 0.3; power line ~8 ROC points). z 2.0: ROC @ $30k -0.7, net -$7.4k, DD $33.0k, PF 0.95, t -0.27,
  EARLY -$11.9k. z 2.5 (best): ROC 2.5, net +$16.1k over nine years, DD $21.2k, PF 1.22, t 0.67 (below the null), 5 of 9 years,
  EARLY -$2.7k; the six-pair row (no XLK/QQQ, SPY/IWM) fails too (ROC 2.0, EARLY -$8.6k). One pair carries it: XLE/USO +$37.7k
  of +$16.1k; without it the book loses. Mean reversion between economically linked funds is not there at daily horizon after costs.
- **BAB** (null 95th 1.9; power line ~4 points; drawdown-day null 95th $9,986). K 5: ROC -3.3, net -$26.5k, DD $27.2k, PF 0.85,
  1 of 9 years positive, stress -$46.5k; beta per $50k side -0.15 (-0.06 .. -0.38 by year; -0.09 in #463's drawdown days); long
  leverage 1.06-1.56x (median 1.21x). K 3: ROC -3.0, net -$32.9k, beta -0.21 (fails the beta gate on its own). Both fail route 1
  and route 2 (route 2 needs ROC >= 5). SEAT REPORT (for FRONTIER, never a gate): the leg DOES earn in #463's drawdown days - K 5
  +$17.8k over the 28 episodes (+$14.6k without its best episode, 20 of 28 positive), K 3 +$22.9k (+$18.4k) - both above the
  drawdown-day null's 95th - but it pays for it every other week (only 2021-22 positive), and part of it is its residual short
  beta. Vol share at the volatility c: 0.009 (K 5, c 1.83) / 0.002 (K 3, c 1.13). Book add at that c: 98.16 / 3.622 and
  92.80 / 3.692 - neither clears #463's 98.50 / 3.816. The equal-dollar control (the plain defensive tilt) reads -3.3 too.
- **ONMOM** (L 20 / 60): ROC -3.2 / -3.3, net -$124k / -$108k, PF 0.68 / 0.71, EARLY -$125k / -$116k. The long five lose -$17.5k
  and the short five -$106k in WF; before costs the long-short makes about +$2.5k / +$4.2k a year, against about $16k a year of costs
  (ten funds both ways every night; cost = the stress run minus the base run). The null is degenerate - every draw is a steady cost bleed, which reads ROC ~ -3.33 whatever the
  ranking - so its 95th percentile (-3.3) carries no information; the decisive fails are ROC, PF, stress and EARLY. Stale opens:
  SLV 82, FXY 39, USO 36 zero-overnight days in WF (reported, not decisive).

Book-add REPORTS (house line #45 - they gate nothing): the PAIRS z 2.5 cell at c 1.60 prints 108.59 / 3.826 over #463. That is
one of six reports, on a leg that fails Stage A on seven checks, carried by one pair (XLE/USO) - it is not a finding and is not
proposed as a shadow. Everything else is at or below #463.
