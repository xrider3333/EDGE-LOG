# PREREG - ENGU-Q R62 CASH-SESSION GATE, CO-TUNED (GAUNTLET E1, census top-1) - 2026-11-03, lane ENGU-Q

Owner GO 11-03 ("results today"; MANAGER #133: "the first co-tuned Auto-Validate starts the minute
the census top-1 is named"). Census = ENGUQ #1996, rank 1. Scope
`C:\EdgeLog\manager\scopes\SCOPE_RESEARCH_LOOP_2026-11-03.md`, experiment E1, process change C3.

FROZEN BEFORE ANY NUMBER. **This is a run-ready spec: the file, the ranges and the window below are
enough for TBIS to queue it without asking me anything.**

## 0. Why this is the top-1, in four numbers

2026-09-27, ENGU-Q round 62 (`ENGUQ_R62_PREREG.md`, result in `ENGUQ.md`). One knob - take entry
signals only between 09:30 and 16:00 ET; exits, stops, trailing and the hold untouched. Against the
raw 24-hour twin on `ADJ_NQ_1m_ETH`, cost 0.783, drawdown valued daily:

| | WF trades | WF ROC@30k | WF Sortino | WF drawdown | LB ROC@30k | LB Sortino | LB without its biggest trade |
|---|---|---|---|---|---|---|---|
| raw twin (the crown's shape) | 1,178 | 26.8 | 3.66 | $48,566 | 44.4 | 3.38 | **-$16,283** |
| R62, entries 09:30-16:00 ET | 678 | **33.2** | 3.59 | **$35,170** | **62.6** | **5.70** | **-$2,567** |

**It was killed by a 0.07 Sortino miss** (clause 2: WF Sortino 3.59 against the twin's 3.66) and by
clause 4 (the sealed year still negative without its biggest trade, though six times better). Four of
six clauses passed, including era stability in all four eras (day-one survival 38.9 / 36.4 / 38.8 /
37.5 percent for kept entries against 10.7 / 11.3 / 14.7 / 12.5 for the removed ones - no drift in
sixteen years) and the harness parity gate.

**What has never been done is the thing this prereg does.** Every number above was measured with the
crown's other FOURTEEN knobs frozen at #335's values. The gate halves the trade count and shortens
the day, so the trail width, the trail activation, the risk multiple and the regime dial are all
mis-set for it. A 900-trial walk-forward re-tunes them AROUND the gate. That is a different question
from the one that failed, and per the census it is a question this lane has never asked of any idea.

## 1. The run, exactly

- **File: `augur_strategies/ENGUQ_1M_ETH_R62_1_0.py`** - NOT pinned, NOT a new file. It already
  exposes the gate as two ordinary ranged knobs beside all fourteen crown dials, so the standard
  search space builder co-tunes them with no code change:

| knob | min | max | step | note |
|---|---|---|---|---|
| `sess_from` | 0 | 1600 | 10 | HHMM ET; **0 with `sess_to` 2400 = gate OFF** |
| `sess_to` | 0 | 2400 | 10 | HHMM ET |
| `er_len` | 20 | 120 | 10 | |
| `er_th` | 0.0 | 0.5 | 0.05 | 0 = off |
| `limit_atr` | 0.0 | 1.0 | 0.05 | 0 = off |
| `tl_len` | 50 | 300 | 4 | |
| `vol_mult` | 0.0 | 5.0 | 0.1 | |
| `stop_mult` | 0.8 | 1.4 | 0.1 | |
| `act_R` | 0.0 | 3.0 | 0.5 | |
| `trail_frac` | 0.5 | 4.0 | 0.5 | |
| `buf_atr` | 0.0 | 1.0 | 0.05 | |
| `min_brk` | 0.0 | 3.0 | 0.1 | |
| `ema_len` | 100 | 1600 | 40 | |
| `atr_len` | 20 | 180 | 4 | |
| `regime_len` | 0 | 100 | 5 | 0 = off |
| `breakeven_R` | 1.0 | 2.5 | 0.5 | |

- **THE LATTICE REACHES BOTH REFERENCE CELLS, checked rather than assumed:** `sess_from` 0 /
  `sess_to` 2400 is on the grid (gate off = the parent's own shape), and 930 / 1600 is on the grid
  (round 62's cell). The house has three times written a step that could not land on its own
  reference cell; this one can land on both.
- **900 trials** (the owner's rule, never lowered). 8 folds, rolling, the house default.
- **Instrument / master:** NQ 1m ETH, `db_adj_eth`, `ADJ_NQ_1m_ETH`, **pinned by filename AND row
  count** in the job note. Cost **0.783 points** a round trip, $20 a point.
- **Window: `date_from` 2010-06-07, `date_to` 2025-06-30.** The lockbox 2025-07-01 .. 2026-06-30 is
  **not loaded, not scored and veto-only afterwards.** Nothing in this round may select on it.
- Walk-forward reporting stretch for the comparison: **2016-10-12 .. 2025-06-27**, #335's own 8 folds
  as frozen in `docs/PREREG_enguq_executor_r1_2026-10-18.md`, so the fold table is comparable to
  every other ENGU-Q round.

## 2. What it is compared against

Two baselines, both already measured, neither re-fitted here:

1. **The crown #335 R2 as it trades** - the leg in BOOK #463, 24-hour entries, WF 26.8 / Sortino
   3.66 / drawdown $48,566.
2. **Round 62's frozen cell** - the gate at 930/1600 with the crown's other knobs, WF 33.2 /
   Sortino 3.59.

Baseline 2 is the one that matters for C3/E2: **the lift of the co-tuned chain over the frozen cell
IS the measurement of how much alpha the frozen grid was hiding.** Report it as its own number.

## 3. THE BAR, written before the data

The walk-forward CHAIN (not the champion-over-WF figure - #489 read 39.87 as champion-over-WF against
the honest chain's 10.1, and this lane will not repeat that) must clear all of:

1. **ROC@30k** beats the crown's on the same stretch;
2. **>= 7 of 8 folds** beat the crown (P(X>=7 | p=0.5) = 0.035; 6 of 8 is suggestive and is not a
   pass; <= 5 is no fold evidence);
3. **not one episode** - worst DD <= 1.3 x DD5. A better DD% from peak with a WORSE DD5 is recorded
   as "one episode moved", not as an edge;
4. **>= 50 trades a year** kept (round 62's cell held 678 over nine years, so this is the binding
   risk if the search tightens the window);
5. **Sortino (daily, zero days included) not worse than the crown's by more than 0.07** - the exact
   miss that killed round 62, carried forward so the bar cannot be said to have moved for my
   convenience either way;
6. **the champion's neighbours hold** - the plateau around the winning cell, and PBO reported.

**Lockbox is veto-only:** a chain that clears 1-6 and then fails the lockbox is dead; a chain that
fails 1-6 is dead whatever the lockbox says. The lockbox never promotes anything.

## 4. Prior, written before the data

- **I expect the chain to beat the crown on ROC@30k and to fail the fold bar.** This is the lane's
  own pattern: executor r1's T07 led by +2.33 ROC points on the whole stretch and won 3 of 8 folds.
- **The specific thing I expect the search to do, and it is the main way this round can fool us:** the
  window knobs are free to settle on a NARROW window (say 10:00-11:30) that holds the family's best
  hours in-sample. That is a clock-window fit and it will show as fold disagreement about the window.
  **So report the per-fold chosen `sess_from` / `sess_to` explicitly** - if the eight folds disagree
  about the hours the way hold cap r2's eight folds disagreed about the cap (0, 0, 6540, 0, 6420,
  6420, 900, 900, chain 8.5 against the crown's 26.5), the answer is the same: dead.
- **R62 is an entry filter, and seven entry filters on this family have failed** a pre-set bar, every
  one after showing a real era-stable mechanism. The measured reason is the refill effect: declining a
  signal frees the slot and the walk takes a later, worse signal of the same move. Co-tuning does not
  repeal that. I ranked this top-1 on its 28% shallower drawdown, not because I expect it to pass.
- Honest confidence: **about one chance in four of clearing the fold bar.**

## 5. Records

- One run-record JSONL line per stage (IS / WF / LB-not-read noted) in
  `C:\EdgeLog\run_records\enguq_202611.jsonl` through `tools/run_record.py`, handed the DAILY series.
- `tools/runboard_watch.py add <run#> --verdict "..." --from ENGUQ` the day it lands, with ROC@$30k
  and DD% in the verdict text.
- Ledger row on the lane's next ship; the result doc is `docs/RESULTS_enguq_r62_cotuned_2026-11-03.md`.
- Addenda appended with a time and a reason, never a replacement. No bar clause moves after a number.
