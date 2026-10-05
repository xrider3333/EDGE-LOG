# PRE-REGISTRATION (DRAFT for MANAGER) - XSML r1: a learned model as the SIGNAL on the US stock cross-section (2026-10-05)

Custom ML, MANAGER #61 (owner 10-05 07:10: lanes hunt new strategy TYPES; Custom ML = three new-type preregs where a model
is the SIGNAL of a new mechanism, each judged against the matched-risk shuffle). Three cells, A / B / C, sharing one
harness. Walk-forward ONLY: the harness never loads a row after 2025-06-29. Nothing below has been computed; the only
data facts used are the cache's shape (6,596 symbols, 2016-01-04..2026-06-30, delisted names included). Research-round
label only - a family name is assigned (vocabulary rule) only if a cell ever becomes a run.

## Why these, and what is different from the dead list (RESEARCH_LEDGER section 2)
- 2.17 (dead): xgboost on 24 features timing ONE futures series at 30-minute marks - no breadth; a model had one bet
  at a time. Here the model ranks ~500 stocks per decision, the setting where the ML-pricing literature finds its gains.
- 2.10 / 09-27 edge audit ("learned ML = coin flip"): every prior ML use was a SIZER or GATE of existing trades. Here
  the model chooses the trades; there is no raw strategy underneath.
- DDW r1 L1 (rocfrontier, reviewed, unrun): raw one-week reversal, top-500, dollar-neutral. Cell A uses that signal
  INSIDE its twin, so A must beat it; cell B removes statistical factors first.
- TTIBS r3 (dead, IBS reversal on 50 large caps), SIPORB (dead, intraday ORB on in-play names), ATTN (dead, overnight
  attention premium), NQBRD (dead, breadth timing NQ), REVERT r1/r2 (NQ futures fades), TTM r20c on stocks (dead): none
  is a learned cross-sectional ranking; IBS and overnight returns appear in A and C only as two inputs among many.
- Rotation / ETF stack / TRANSFER r2 (dead) traded a handful of ETFs; these cells trade single stocks.

## Map placement (docs/MDL_MAP_R1.md)
Each cell is a NEW LEG, dollar-neutral on stocks, so its drawdown weeks should be only loosely tied to #463's NQ/ES legs.
Map bar: about $15,000 a year at a $30,000 drawdown of its own (WF ROC @ $30k >= 15) with rho_dd within +/-0.15; a leg
that EARNS while #463 falls helps below $5,000 a year. Cell C is aimed at that second case (low-risk names tend to hold
up in sell-offs); A and B must clear the first.

## Shared harness (frozen now)
- **Data:** C:\EdgeLog\alpaca_cache\siporb\daily_split.parquet (sha256 printed at run time), split-adjusted SIP dailies.
  Every one of the 369 whole-ratio flags in C:\EdgeLog\_research_cache\split_qa\siporb_split_flags_voltest.csv removes that
  symbol from features, targets and P&L for 21 sessions either side (Alpaca re-adjusts between pulls; flags are not
  patched). No dividends (price return); a stock that stops trading exits at its last close (no delisting return - a
  bias that flatters longs and hurts shorts, disclosed).
- **Universe, point in time, at every decision date t:** common stocks with close >= $5 and >= 260 sessions of history;
  the 500 with the highest median dollar volume over sessions t-19..t.
- **Clock:** features use data through t's CLOSE; orders fill at t+1's OPEN (auction print); exits at a later open.
  Positions are valued at each close for the daily P&L.
- **Book:** equal dollars per name, $1,000,000 long and $1,000,000 short gross (ROC @ $30k does not depend on the scale).
- **Costs:** base 5 bps a side + 1%/yr borrow on short notional; stress 10 bps a side.
- **Walk-forward:** expanding window, refit every 1 January on decisions whose target ended before that date (purged);
  first refit 2018-01-01 on 2017 decisions (features need 252 sessions). Scored stretch: positions exited
  2018-01-02..2025-06-29 (7.5 years; the house WF starts 2016-07 but the first two years feed the warm-up).
- **Model (registered, no search):** sklearn HistGradientBoosting (regressor for A, classifier for C): max_iter 300,
  learning_rate 0.05, max_leaf_nodes 31, min_samples_leaf 200, l2_regularization 1.0, no early stopping,
  random_state 20261005. Features are cross-sectional ranks scaled to [-0.5, 0.5] at each date.
- **Yardstick:** house convention - ROC @ $30k = 30 x (net / years) / max drawdown of the daily P&L; Sortino from daily
  P&L with zero days. Drawdown weeks: #463's WF daily P&L (book rebuilt to 2025-06-29, parity 93.81 / 3.816 asserted);
  qualifying episodes = peak-to-trough drops at least 1/3 of the deepest ($14,950); a DD week = a calendar week with
  >= 3 trading days inside one (DDW r1 [T5] / MDL r1). rho_dd = correlation of weekly sums over the DD weeks; DO = the
  cell's P&L over the DD days / #463's loss over them.
- **The matched-risk shuffle (signal version of the 09-27 audit):** 1,000 random books per cell; at every decision date
  the model's scores are permuted across that date's eligible names and the cell's own portfolio rule is applied
  unchanged (same counts, same holding rule, same dollar-neutrality). Judged GROSS of costs, so the random books' higher
  turnover is not held against them (seed 20261005).
- **Power line first:** the shuffle's 50th / 95th percentile gross WF ROC per cell is printed and committed BEFORE any
  cell's own number is computed.

## Cell A - PATTERN: weekly cross-sectional ranking from price and volume characteristics
- **Mechanism (literature):** Gu, Kelly & Xiu (2020, RFS) - trees and nets on price-trend, liquidity and volatility
  characteristics predict the cross-section, with the gain in nonlinear interactions; Jiang, Kelly & Xiu (2023, JF) -
  price-pattern information at 5-20 day horizons that is not reversal or momentum.
- **Inputs (18, daily OHLCV only):** returns over 1, 5, 21 sessions; momentum 252..21 and 126..21; overnight and intraday
  return sums over 5 and 21; realised vol 21 and 63; max and min daily return over 21; IBS today and its 5-day mean;
  distance to the 252-day high; log dollar volume 21; volume ratio 5 / 63; Amihud illiquidity 21.
- **Target:** cross-sectional rank of the return from t+1 open to t+6 open.
- **Rule:** decisions every Friday close; long the top 50, short the bottom 50 of the 500; hold to the next Monday open.
- **Raw twin (no model):** the rank average of 5-day reversal and 252..21 momentum, the two classic signals, same rule.

## Cell B - STATARB: factor-neutral residual reversal from a learned statistical factor model
- **Mechanism (literature):** Avellaneda & Lee (2010, QF) - idiosyncratic returns, after removing statistical factors,
  mean-revert; Yeo & Papanicolaou (2017); Guijarro-Ordonez, Pelger & Zanotti (2022) find the residual signal survives
  recent years in liquid names. The model is the signal: a rolling PCA factor model + an OU fit per stock.
- **Model:** each day, PCA on the 252-day correlation matrix of the 500 names' daily returns, 15 factors; each stock's
  60-day residual (return minus its factor regression) is cumulated and fitted as an AR(1) = OU process; s-score =
  (cumulated residual - its OU mean) / equilibrium sd (the 2010 paper's form; negative = cheap). Stocks with mean-reversion speed below 252/30 (half-life over ~30
  sessions) are not traded.
- **Rule (the 2010 paper's thresholds, not tuned):** open long when s < -1.25, short when s > +1.25; close a long when
  s > -0.50, a short when s < +0.75. Long and short sides each scaled to equal gross dollars daily.
- **Raw twin (no model):** the same thresholds on a z-score of each stock's raw 5-day return (its own 60-day mean and
  sd) - no factor model. B must show the learned factor structure adds something.

## Cell C - CRASH: a learned crash-probability model, short the likely crashers, long the unlikely
- **Mechanism (literature):** lottery demand and the idiosyncratic-risk puzzle - Bali, Cakici & Whitelaw (2011, JFE,
  MAX); Ang, Hodrick, Xing & Zhang (2006, JF, IVOL); Conrad, Kapadia & Xing (2014, JFE, "Death and jackpot": stocks with a
  high predicted probability of extreme moves earn low future returns).
- **Model:** classifier for P(the next 21-session return lands in the bottom 5% of the cross-section), inputs: IVOL vs
  the equal-weight universe 21 and 63, MAX 21, skewness 63, min daily return 21, distance to the 252-day high, log
  dollar volume, turnover proxy, 252..21 momentum, 252-day beta, overnight and intraday 21-day sums.
- **Rule:** decisions at each month's last close; short the top 50 by predicted crash probability, long the bottom 50;
  BETA-NEUTRAL (each side scaled by its trailing 252-day beta to the equal-weight universe); hold to the next
  month's fill (about 21 sessions).
- **Raw twin (no model):** the same rule on plain 63-day IVOL.

## Stage A bars, per cell (walk-forward only; all must hold)
1. Net WF ROC @ $30k >= 15 at base costs, and net > 0 at stress costs.
2. Gross WF ROC above the 95th percentile of its matched-risk shuffle.
3. Beats its raw twin on net WF ROC AND Sortino.
4. The map: rho_dd <= +0.15 (Cell C additionally reports DO; if C's ROC is below 15, it may still pass bar 1 only if
   DO > 0 and rho_dd <= -0.15, the map's "earns while #463 falls" case).
5. RISK r1: net positive without Feb-Apr 2020; net positive in >= 5 of the 7 July-June WF years; both halves
   (2018-01..2021-06, 2021-07..2025-06) net positive.
6. >= 100 name-positions and >= 26 independent decision dates.
Reported regardless: per-year net, long vs short leg P&L, turnover, average names held, top-10-name share of net.

## What a result means
- A cell that passes -> MANAGER. This harness is not an EDGELOG engine run, so no Auto-Validate can express it; its
  sealed year (2025-06-30..2026-06-30) is the same stock sealed year that SIPORB, ATTN and DDW share on ONE read day
  (rocfrontier's rule [M5]), so a pass asks MANAGER to add it to that day; otherwise a forward paper shadow. RUNBOARD
  research row either way.
- A cell that fails is dead: ledger + memory, no variants (no other horizons, thresholds, counts or inputs).
- Nothing live or in the book changes.

## Priors to disclose
- 09-27 audit: learned models matched raw at matched risk in 26 of 52 runs; the house prior on ML is a coin flip.
- Published US cross-sectional ML gains are largest in small, illiquid names; this universe is the 500 most liquid, where
  the literature finds a smaller but non-zero effect, and costs here are modelled at 5-10 bps a side.
- Statistical-arbitrage residual reversal decayed after the mid-2000s in the 2010 paper's own data.

---

## ADDENDUM 1 (2026-10-05 08:00 MST, before any cell or twin number) - MANAGER house line #63 for new standalone legs
MANAGER #63 (07:48, all lanes, names "Custom ML XSML"): for a NEW STANDALONE leg the standalone Stage A bars decide; the
book-add test is a REPORT that only decides whether a forward BOOK shadow line is also opened. Binding changes:
1. **Bar 4 (rho_dd <= +0.15) becomes a REPORT**, printed beside the result with DO. It still enters bar 1 for Cell C's
   earner route (DO > 0 and rho_dd <= -0.15 when C's ROC is below 15).
2. **Bar 7, PF >= 1.0:** A and C - profit factor of name-periods (each name over one holding period) net of a 5 bps
   round trip; B - profit factor of its WF daily net P&L (its positions change daily, so name-days are not trades).
3. **Bar 8, neighbours:** both neighbours' net WF ROC @ $30k > 0 - A and C at 25 and 100 names a side (registered 50);
   B at open thresholds 1.0 and 1.5 (registered 1.25, closes unchanged). Never picked from.
4. **A pass** goes to the RUNBOARD as a research row the same day and to MANAGER for the leg's own sealed-year veto on
   the shared stock sealed-year day (#63: the book add on that year is a report). These cross-sectional books cannot be
   expressed as an EDGELOG engine run, so there is no pinned Auto-Validate.
5. **Harness facts printed before this addendum (no P&L):** the universe holds 500 names every session from 2017;
   1,293 symbols are ever in it; 313 symbols carry a quarantined split window; #463's WF drawdown episodes / days /
   ISO weeks reproduce DDW r1 exactly (28 / 460 / 92) and are asserted at run time; 391 weekly (A) and 90 monthly (C)
   WF decisions, 1,887 daily (B).

## POWER LINE (committed before any cell or twin number) - C:\EdgeLog\custom_ml\xsml_r1\POWER.txt
```
data sha256 083f8c23d1d62cf7bda99d5c9a6373130c336ac605f57db5eeac832504281f6d; 1,293 symbols ever in the universe; 313 quarantined
#463 parity 93.81 / 3.816 OK; WF drawdown episodes >= 1/3 of $44,849: 28; DD days 460; DD weeks 92 (DDW r1 printed 28 / 460 / 92)
POWER LINE - matched-risk shuffles (random books, same rule, GROSS), no cell or twin P&L read:
  A PATTERN  (391 weekly decisions): gross WF ROC 50th -0.1  95th +10.3
  C CRASH    (90 monthly decisions): gross WF ROC 50th -0.0  95th +9.2
  B STATARB  (1887 daily decisions): gross WF ROC 50th +0.2  95th +10.0
Map bar: net WF ROC @ $30k >= 15 with rho_dd <= 0.15 (or DO > 0 and rho_dd <= -0.15 for C).
```
Read: a random dollar-neutral book of 50 / 50 names from this universe reaches a gross WF ROC @ $30k of about 10 at its
95th percentile in every cell. Bar 2 (edit 6 below) asks the cell's NET ROC to clear that, so a real but thin edge (net
ROC under ~10) cannot be told from luck here.

---

## ADDENDUM 2 (2026-10-05 08:20 MST, before any cell or twin number) - MANAGER review #64 GO WITH EDITS, all six adopted
1. **Concentration (bar 5 widened):** net WF > 0 without the best 1% of name-periods (B: name-days) AND without the best
   5 decision periods (A: weeks, C: months, B: days). The run prints the 30 largest single-name contributors; before any
   pass is spoken they are hand-audited (split factor, TBIS flag, symbol map, a public corporate-actions lookup), and a data
   event removes that name-period from the cell AND the shuffle.
2. **Delisting:** reported beside the base - (a) the cell with DELISTED LONGS marked to zero the session after their last row
   (the cell's worst case); (b) the short leg's WF P&L at the base (last close) and with delisted SHORTS to zero. If the
   short leg's sign needs (b), the short side is called a data artefact. "Delisted" = no row after a date more than 5
   sessions before 2025-06-29.
3. **Corporate actions:** STRATEGY-BEATING's Alpaca dividends + splits file for XGAP is used (no second pull). Dividends
   are paid to holders of record (ex-dates after the fill through the exit open; shorts pay), added back to the A / C
   training targets, and to B's overnight return on the ex-date; every listed split not already in the 369 flags is
   quarantined the same way. `run` refuses to start without the file. Its column mapping goes in addendum 3 when the format
   is posted.
4. **Cell B turnover and cost per year** are printed and committed (POWER2.txt) before any number.
5. **Cell C's earner route** needs DO above its null's 95th percentile (1,000 random beta-neutral books, re-drawn with seed
   20261007, in POWER2.txt) AND rho_dd <= -0.15; "DO > 0" is retired.
6. **Bar 2 is now NET:** the cell's NET WF ROC at base costs must clear the matched-risk shuffle's 95th percentile (the null
   stays gross); the net and gross leads are printed side by side. With bar 3 (beat the raw twin), this is what it takes to
   overturn the 09-27 prior ("learned ML = coin flip").
A pass -> RUNBOARD research row the same day + the leg's own sealed-year veto on the one stock day; the forward shadow
decides. Code: tools/xsml_r1.py (the rewrite reproduces the committed nulls exactly: first three A shuffles
+5.899154 / +0.169021 / -2.757513 both ways).

## POWER LINE 2 (review #64 edits 4 + 5; committed before any cell or twin number) - C:\EdgeLog\custom_ml\xsml_r1\POWER2.txt
```
B STATARB turnover (positions only): 27.4% of the $2M gross a day; $137,727,611 traded a year -> cost $68,864/yr at 5 bps a side ($137,728 at 10 bps); avg names long / short 96.5 / 82.1
C CRASH earner-route null (1,000 random beta-neutral books, gross): DO 50th -0.004 95th +0.209; rho_dd 5th -0.170 50th -0.005
```
Read: cell B must earn about $69,000 a year before costs just to break even at 5 bps a side on $1M a side; cell C's earner route needs DO above +0.209.
