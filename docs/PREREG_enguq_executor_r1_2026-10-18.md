# PREREG - ENGU-Q EXECUTOR ROUND r1 (board rows T07 and T08)

2026-10-18, lane ENGU-Q, MANAGER inbox #116 ("more testing on everything on things that are promising", owner 10-18).

FROZEN BEFORE ANY NUMBER IS COMPUTED. Verdicts are only those written here.

## 0. What is being tested, and what is NOT

Two board rows the owner called promising. Both are EXECUTOR reads on an EXISTING leg - ENGU-Q #335 as it
sits in BOOK #463 - not new strategies and not a re-fit. **Nothing is optimised in this round.** No parameter
is searched, no lattice is walked, no cell is chosen after seeing a number. Every arm is the same leg under a
different execution rule.

| row | arm | what it is | published |
|---|---|---|---|
| - | LEG | ENGU-Q #335 on NQ, as the book trades it | ROC@30k 26.09, DD5 $31,177, Sortino 1.68 |
| T07 | QQQ-COPY | NQ's own signals filled on real QQQ 1m prints, 822 shares = 1 NQ, held overnight | 28.42, $34,652, 1.64 |
| T08 | RTH-EXEC | the same RTH-only-executor-that-holds-overnight, on NQ prices | 24.57, $35,511, 1.47 |

The leg: `ENGUQ_1M_ETH_R2_1_0.py`, NQ 1m ETH `db_adj_eth`, cost 0.783 pts, $20 a point, params as
`api/book_shadow.BOOK463_LEGS` holds them (tl_len 206, atr_len 52, stop_mult 1.0, min_brk 1.6, ...).
The executor rule (frozen in Q34, 2026-10-09): a signal on a bar inside a regular session's 09:30-15:59 ET
fills at that bar's CLOSE; any other signal fills at the OPEN of the next regular session's first RTH bar; an
entry and an exit that land on the same open cancel (no trade, no cost).

## 1. Stretch, and what may not be read

- **WALK-FORWARD YEARS ONLY: 2016-07-01 .. 2025-06-29**, the stretch the two published reads were made on
  (2,626 sessions, 8.9938 years). This is #335's own tuning stretch, so nothing here is out-of-sample for the
  LEG - it is a comparison BETWEEN execution rules on one fixed signal set, which is what the owner asked.
- **The lockbox (2025-07-01 .. 2026-06-30) is VETO-ONLY and is not read in this round.** No arm is chosen,
  ranked or tuned on it.
- One stretch at a time; WF and LB never pooled.

## 2. The four numbers, from one source

Every arm, every sub-stretch: `augur_engine.drawdowns.four_numbers(daily)` (FRONTIER #114, on main 3f41e830)
-> ROC@30k, DD5 $, DD% from peak, Sortino. Daily series, every session present, **zero days included**;
Sortino is never per trade. Drawdown is valued DAILY. `one_episode` = worst DD > 1.3 x DD5.

## 3. The bar (MANAGER #116, written before data)

An arm PASSES only if ALL FOUR hold:

1. **gross $/trade >= cost $/trade** (the arm pays for itself before it pays anything else);
2. **net ROC@30k > 0** on the WF stretch;
3. **NOT one episode** (worst DD <= 1.3 x DD5);
4. **MDL path** - standalone ROC@30k >= 15 on WF, >= 50 trades/yr, and drawdown-day correlation with
   BOOK #463 no WORSE than the bare LEG's. (These are executor variants of a leg already in the book, so the
   MDL question is not "is it a new leg" but "does the execution rule make the seat more correlated".)

An arm that fails any one of the four is reported as FAILED on that condition. No arm is promoted to anything
on this round's strength - the output is a read, not a crown.

## 4. The clauses

### C0 - PARITY GATE (runs first; nothing downstream is published without it)

The harness re-derives LEG, T07 and T08 daily from the masters and compares each with the frozen series
`C:\EdgeLog\_anatomy_cache\q34\q34_daily.csv` and `C:\EdgeLog\_anatomy_cache\q36\q36_daily.csv` (the published
reads' own output).

- Pass = max absolute daily difference <= $0.50 for every arm.
- On failure, C1 and C3-halves still run (they need only the frozen series, which are the published numbers),
  and **C2, C4 and the C3 extra are reported as NOT COMPUTED** with the parity gap printed. No recomputed
  number is published against a baseline the harness cannot reproduce.

### C1 - FOLD BY FOLD: in how many of #335's 8 walk-forward folds does each arm beat the bare LEG?

Fold windows are #335's own, derived from its stored `train_bars` 2,034,525 / `test_bars` 381,473 against the
NQ no-adj 1m ETH master over the run's window, and FROZEN here (rolling scheme; dates inclusive of `from`,
exclusive of `to`, except fold 8 which is inclusive of both):

| fold | from | to |
|---|---|---|
| 1 | 2016-10-12 | 2017-11-23 |
| 2 | 2017-11-23 | 2018-12-30 |
| 3 | 2018-12-30 | 2020-02-03 |
| 4 | 2020-02-03 | 2021-03-08 |
| 5 | 2021-03-08 | 2022-04-04 |
| 6 | 2022-04-04 | 2023-05-02 |
| 7 | 2023-05-02 | 2024-05-29 |
| 8 | 2024-05-29 | 2025-06-27 |

Per fold, per arm: the four numbers on that fold's own daily slice (years = fold days / 365.25, drawdown
valued daily WITHIN the fold). An arm "wins" a fold when its ROC@30k exceeds the LEG's on the same fold.

**Pre-set bar, binomial, one-sided, a coin flip as the null:**

- **>= 7 of 8 = HOLDS ACROSS FOLDS** (P(X>=7 | p=0.5) = 0.035);
- 6 of 8 = SUGGESTIVE, not a pass (P = 0.145);
- <= 5 of 8 = NO FOLD-LEVEL EVIDENCE - the whole-stretch lead is carried by a minority of the folds.

Also reported, because a count throws away size: the per-fold ROC difference (arm - LEG), its mean, its sd,
and which folds carry the whole-stretch lead.

### C2 - COST LADDER

Four rungs per arm, gross unchanged, only the fill price and the per-round-trip cost move. A **tick** is the
instrument's own minimum increment, and a rung adds it **to each side** (so "+1 tick" = 2 ticks a round trip):

- `base` - as published (NQ $15.66 a round trip = 0.783 pts; QQQ $0.02 a share = $16.44 at 822 shares);
- `+1 tick` - NQ +0.50 pts ($10.00) a round trip; QQQ +$0.02 a share (+$16.44) a round trip;
- `+2 ticks` - NQ +1.00 pt ($20.00); QQQ +$0.04 a share (+$32.88);
- `late` - every fill one bar later than the rule says, at base cost (a close fill at bar k becomes a close
  fill at k+1; an open fill at bar k becomes an open fill at k+1; the same-open cancel is re-tested after the
  shift). This is the "1-bar-late fills" rung and it is NOT combined with the cost rungs.

Reported per rung: the four numbers, trades, gross $/trade, cost $/trade, and whether condition 1 of the bar
still holds. The rung that first turns net ROC@30k <= 0 is named.

### C3 - THE YEARS OR THE SIGNALS

**Item (3) of #116 cannot be answered as written, and this is declared before any result.** It asks for the
NQ-signal copy on 2010-16 vs 2017-26. The QQQ 1m tape begins **2016-01-04** (registry master
`master_dd092f50.csv`, Alpaca split-adjusted RTH, rows 1,023,757, date_from 2016-01-04). There are no QQQ
prints before 2016, so no 2010-16 QQQ arm exists to read, at any cost or any sizing. The substitute, fixed
here:

- **Halves of the WF stretch**: H1 = folds 1-4 (2016-10-12 .. 2021-03-08), H2 = folds 5-8 (2021-03-08 ..
  2025-06-27). Four numbers for LEG, T07, T08 in each half, plus the GAP (arm - LEG) in each half.
- **The reading rule, fixed before the numbers:** if the GAP holds its sign and rough size across both halves
  while the LEVEL moves, the retention is a property of the SIGNALS/execution. If the GAP flips sign or
  collapses between halves, it is a property of the YEARS. A gap that is small in both halves relative to the
  per-fold sd from C1 says neither, and that is the honest answer.
- **FLAGGED EXTRA, outside the bar:** T08 runs on NQ prices alone, so it CAN be read on 2010-06-07 ..
  2016-06-30. That stretch is pre-walk-forward, i.e. outside "WF years only", so it is reported as an EXTRA,
  it cannot pass or fail anything, and no verdict in this prereg may cite it. It is included because it is
  the closest honest thing to the 2010-16 read the owner asked for.

### C4 - T08's OVERNIGHT GAPS

The T08 executor's whole point is that it holds through the close. On the WF stretch:

- Every position held across a session boundary is identified (the executor's own fills: held from the last
  RTH bar of session d through to the first RTH bar of session d+1 or later).
- The gap move is valued in dollars at 1 NQ and at the **$30k sizing** (the scale factor that puts the arm's
  worst daily drawdown at $30,000, i.e. 30,000 / max_dd - the same scaling ROC@30k uses).
- Reported: the worst 5 by dollars with their dates, the total overnight share of the arm's net, and whether
  those 5 fall inside the DD5 episodes.
- `one_episode` for T08's DD5 is reported from `four_numbers`, with the worst-DD / DD5 ratio printed.

## 5. Priors, written before the data

- **C1**: both arms beat the LEG on the whole stretch by less than one per-fold sd, so I expect 4-6 of 8 for
  T07 and 2-4 of 8 for T08. I expect NEITHER to reach 7. Stated plainly: I expect the fold test to say the
  whole-stretch leads are not fold-level evidence.
- **C2**: T07 is the one at risk. It takes ~1,194 trades against the LEG's ~400, so a cost rung costs it
  three times as much per year. I expect T07 to still be positive at +2 ticks but to lose most of its lead
  over the LEG by +1 tick; I expect T08, which takes the LEG's own trade count, to be nearly cost-insensitive.
  1-bar-late I expect to cost T07 more than the cost rungs do, because its fills are concentrated at the open.
- **C3**: I expect the gap to be stable (signals, not years) - the executor is a mechanical re-fill of one
  fixed signal set, and there is no mechanism by which a fill rule should work in one half and not the other.
- **C4**: T08's published DD5 is one episode, so I expect a small number of gaps to carry it, and I expect at
  least one of the worst 5 to sit inside the deepest episode.

## 6. Method pins

- Harness: `tools/enguq_exec_r1.py`, frozen with this document; it checks this file's LF sha256 at start and
  stops on a mismatch, and prints its own.
- Frozen inputs, checked by LF sha256 at start: `q34_daily.csv`, `q36_daily.csv` (the published reads).
- Run order is the order above; C0 gates C2/C4/C3-extra only.
- No stopping rule, no "try another window", no post-hoc arm. Addenda are appended to this file with a time
  and a reason, never a replacement.
- RUN-BEFORE-MAIN: the frozen commit is pushed to `origin` as `prereg/enguq-executor-r1` and its sha256s are
  posted to MANAGER before the harness is launched; the ship to main is the permanent record.
