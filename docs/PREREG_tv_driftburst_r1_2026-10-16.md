# PREREG - DRIFTBURST r1: fade a statistically explosive 5-30 minute drift on NQ / ES (power-first screen, PRE-WF rows) - TV, 2026-10-16

Written before any number of this rule exists. Owner standing order 10-16 via MANAGER #148: keep looking for scalpers (1-5 minute
NQ / ES, pre-WF rows first, house cost and +1 tick). Source: TV's scalper scout of 10-16 (literature vs the house's 109 tested
mechanisms): the one fresh, data-feasible idea with >= 50 events a year. Family name: MISC (a hunt, not a family yet).

## Mechanism (published)
Christensen, Oomen and Reno, "The drift burst hypothesis", Journal of Econometrics 227(2), 2022 (arXiv 2601.08974 revision, 2026):
short, locally explosive drifts - price runs in one direction within minutes far faster than its local volatility - occur about once
a week per asset and are mostly followed by reversion, more so after negative, high-volume bursts; their story is liquidity provision
(providers step back when immediacy demand spikes, price overshoots, and reverts when liquidity returns). Read from the abstract and
landing page only; no P&L, reversal fraction or Sharpe is published, so the edge after cost is unknown - this screen measures it.

## Not seen before (the house's dead list, checked)
Round 37-38 RANGE-BURST (a breakout of a wide bar, continuation), chop-fade (fades in quiet chop), volume ignition (60-bar break),
REVERT r1 (failed new high / low of the day fade, 5-minute bars, RTH), REVERT r2 (post-close auction reversal) and the 10s fades are
all different triggers. No house test fades a VOLATILITY-NORMALISED k-minute drift statistic. Disclosure: rows 2010-06 .. 2016-06 of
NQ / ES 1m are untouched by any short-horizon fade at the house; the Super Scalper (a different rule) read them today (r2e).

## Data (pre-WF rows only)
- NQ 1m ETH no-adjust master id 34 (NOADJ_NQ_1m_ETH.csv) and ES 1m ETH no-adjust id 30 (NOADJ_ES_1m_ETH.csv), bars stamped at START
  in US/Eastern, 2010-06-06 .. 2016-06-30 (arrays cut before 2016-07-01 00:00 ET before any signal). Walk-forward and lockbox unread.
- Roll switches from tools/data/rolls_<ROOT>.csv (kind != not_a_roll): no k-minute signal window and no hold may straddle a switch
  (such signals are skipped - decided at the signal bar, from the calendar, never from price).

## The rule
- 1-minute log returns r_t = ln(close_t / close_{t-1}) between consecutive bars <= 5 minutes apart (else r_t = 0 and the bar starts a
  new segment: no window spans a data gap or the daily halt).
- Diurnal volatility: for each minute-of-day m (New York), v_m(t) = the mean of r^2 at minute m over the previous 20 dates ON WHICH
  THAT MINUTE TRADED (strictly before the current date; at least 15 such dates, else no signal); a bar whose interval straddles a
  roll switch gives no r^2 (the contract offset is not volatility). sigma_k(t) = sqrt(sum of v over the k BARS of the window).
- Drift statistic over the last k bars: T_t = (ln close_t - ln close_{t-k}) / sigma_k(t), the k bars all in one segment and spanning
  at most k minutes + 2 (missing minutes would inflate T in thin hours).
- Burst: |T_t| >= c and |T_{t-1}| < c with T_{t-1} defined (a fresh crossing), market flat. Trade AGAINST the drift (T > 0 -> short; T < 0 -> long).
  Two entry modes: CROSS = at the OPEN of bar t+1 (the burst may still be running); EXHAUST = at the OPEN of the bar after the first
  bar j in t+1 .. t+30 (same segment) whose 1-minute return opposes the drift (the burst has stalled; no such bar = no trade). Exit at
  the OPEN of the entry bar + H bars. A trade whose hold would cross a gap of more than 5 minutes (the daily halt, a weekend, a data
  hole) is SKIPPED - a scalper does not carry the halt. One position per market at a time (bursts during an EXHAUST scan, and up to
  a skipped EXHAUST trigger, belong to the scanned burst); no stop. Synthetic check before freeze: CROSS fades a planted burst
  while it still runs - EXHAUST is the published post-burst reversal; both are kept, the null covers the choice.
- Grid (24 cells per market): mode in {CROSS, EXHAUST} x k in {5, 15, 30} minutes x c in {4, 6} x H in {15, 60} minutes.
- Cost per round trip: NQ 0.706 pt, ES 0.582 pt (commission + 1 tick each side); stress +0.25 pt. P&L $ = points x $20 / $50.

## Statistics (per cell, per market)
Trades, trades a year (/ 6.07), win rate, avg win / loss, net PF, net points, mean net points a trade with its t, yearly Sharpe after
cost, calendar years with net > 0, the stress PF, the share of trades signalled within 5 minutes after 08:30 / 10:00 / 12:30 / 14:00 /
14:15 ET (macro releases, incl. the pre-2013 FOMC times), and the four numbers (ROC@30k, DD5 and DD% from peak at the $30k sizing,
daily Sortino) on the cell's daily P&L booked on the exit's CME trade date (18:00 ET and later books to the next date); calendar = NY
dates with RTH bars plus every exit date, zeros included.
EVENTS: NQ and ES fire on the same bursts (correlation ~0.9), so the pooled unit is the BURST CLUSTER - trades from any cell and either
market whose holds overlap in time share one global cluster id; a cell's events are its trades summed per cluster (net $).

## Family-wise null (fixed now)
Direction-randomisation by burst: one random sign per GLOBAL burst cluster (shared by both markets and all cells, so paired NQ / ES
trades flip together), cost unchanged; recompute each (mode, k, c, H) cell's pooled event t (mean net $ per event / its standard
error); the statistic is the MAX over the 24 cells (the same statistic the candidate is picked on); 1,000 reps, seed 20261016. The observed max t is compared with the
null's 95th percentile.

## Pre-set reading (the power-first gate)
- CANDIDATE = the cell (mode, k, c, H) with the highest pooled event t.
- It CLEARS the screen only if ALL of: (1) its pooled event t exceeds the family-wise null's 95th percentile AND its mean net per
  event is > 0; (2) the fade earns after cost in BOTH markets separately (>= 61 trades, i.e. 10 a year, AND net PF > 1.00 at the
  house cost, in NQ and in ES); (3) >= 50 events a year; (4) MAPCHECK-F (tools/mapcheck_f.py, pinned by LF sha256 as in shelf 32)
  on n = its events a year and s_mid = HALF its event-level yearly Sharpe after cost (winner's curse over 24 cells + publication),
  s_sd 0.25, rho_dd 0.0 ('zero'), t3 tails, clustered vol, returns CLEARS.
- CLEARS -> a full prereg: a ranged strategy file (mode, k, c, H as knobs) and the 900-trial Auto-Validate with window + master pinned, after
  MANAGER reads this. Otherwise CLOSED AT DRAFT with a two-line ledger row, each failed condition named.
- A momentum reading (bursts CONTINUE) is printed as the mirror sign of every cell, never a pass route here.

## Harness
`tools/tv_driftburst_r1.py` - checks this file's LF sha256 and the MAPCHECK-F pins at start, prints its own; output
`C:\EdgeLog\_research_cache\tv_scalp\driftburst_r1\`. Pushed as prereg/tv-driftburst before the run (RUN-BEFORE-MAIN).
Review before freeze (2 lenses, adversarial verify, 10-16): fixed - holds through the daily halt / weekends (now skipped), NQ / ES
trades treated as independent in the pooled t and the null (now burst clusters); minor - roll bars out of the variance, the 20-date
lookback counted over dates the minute traded, bar-vs-minute window span, fresh crossing needs T_{t-1}, EXHAUST skip window, per-market
trade floor, positive net in t1, trade-date booking, the macro minutes.
