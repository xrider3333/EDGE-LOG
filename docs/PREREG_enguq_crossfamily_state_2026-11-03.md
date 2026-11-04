# PREREG - ENGU-Q <-> NOISE cross-family state filters (GAUNTLET w93) - 2026-11-03, lane ENGU-Q

Owner GO 11-03 ("proceed with all"), scope `C:\EdgeLog\manager\scopes\SCOPE_RESEARCH_LOOP_2026-11-03.md`,
row w93 feed: "ENGUQ+TTM = cross-family state filters". TTM's own prereg
(`PREREG_ttm_crossfamily_state_filters_2026-11-03.md`) covers TTM squeeze state on ORB and NOISE;
this one covers the **ENGU-Q <-> NOISE pair in both directions** and nothing else, so the two do not overlap.

FROZEN BEFORE ANY NUMBER.

## 0. C7 DECLARATION - this shape has been tested before, and here is the revive reason

Honesty first, because the scope's own C7 rule says a prereg must refuse an idea already DEAD on the
same data and bar unless it states why it is different.

| prior round | what it did | verdict |
|---|---|---|
| CROSS-FAMILY DAY-TYPE r1 (2026-08-18, `CROSSFAMILY_DAYTYPE.md`) | NOISE's best state variable (prior session's close position in its own range) as an entry veto on ENGU-Q and ORB | **FAILED on both.** "NOT program-wide" - sign-flipped on ORB |
| r2 (08-22) | the two ENGU-Q day-type levers r1 banked, as size tilts | both die on the concentration gate |
| r3 | the 0.6-0.8 band long veto | "a lockbox mirage", 4 of 7 gates fail |
| NOISE HEDGE TILT (ledger 2.55, 10-04) | the REVERSE direction - NOISE #422 sized x1.5/x0.5 by whether ENGU-Q holds its long | **Stage A FAIL, dead.** Lead at the 39th percentile of 200 shifted-calendar placebos, 3 of 9 years |
| ENGU-Q rounds 57, 62, 65, 66 | seven pre-registered entry filters | **all seven failed**, every one after showing a real era-stable mechanism |

**Three things are different here, and if MANAGER does not accept all three this item should be
closed at draft instead of run.**

1. **A different state variable.** The 08-18 round read a *generic day-type statistic* that NOISE
   happens to like (close-in-range of the prior session). This round reads **NOISE's own model
   state at the ENGU-Q signal bar** - whether the live NOISE leg is in a position, on which side,
   and whether its own entry gate is open. That is a different quantity and it has never been read
   on an ENGU-Q signal bar.
2. **Co-tuned, not frozen (scope C3).** Every one of the twelve prior rounds above screened its knob
   as a one-knob swap with the crown's other fourteen settings frozen. This prereg puts the state
   knob **inside the Auto-Validate search space** so the trail, risk and regime dials re-tune around
   it. The 11-03 census (ENGUQ #1996) says plainly that this has never been done for this family,
   and E2 in the scope exists to measure exactly how much the frozen grid was hiding.
3. **The reverse direction is the better-powered half, for a stated mechanical reason** - see §2.

## 1. The legs and tapes, pinned

Both legs exactly as BOOK #463 carries them (`api/book_shadow.BOOK463_LEGS`):

| | strategy file | instrument | tf | session | source | cost |
|---|---|---|---|---|---|---|
| ENGU-Q | `ENGUQ_1M_ETH_R2_1_0.py` (#335 R2) | NQ | 1m | **ETH** | `db_adj_eth` | 0.783 pts |
| NOISE | `NOISE_1_8_CT304H.py` | NQ | 5m | **RTH** | `db_noadj_rth` | 0.533 pts |

$20 a point. Walk-forward **2016-10-12 .. 2025-06-27** (#335's own 8 folds, the windows frozen in
`docs/PREREG_enguq_executor_r1_2026-10-18.md`) for the ENGU-Q side; NOISE's own crown windows for
the NOISE side. **The lockbox is not read in this round, in either direction, at all.**

**The tape mismatch is the first real constraint and it is declared, not discovered:** ENGU-Q trades
the 23-hour session on an adjusted tape, NOISE trades regular hours on an unadjusted one. NOISE state
is therefore **undefined for every ENGU-Q signal outside 09:30-16:00 ET**. Executor r1 measured that
an RTH-only ENGU-Q executor loses 31% of the leg's trades, so roughly two thirds of the entries are
addressable and one third is not. Arms are specified so that an out-of-RTH signal is **taken
unchanged** (state = unavailable, filter inert), never silently dropped.

## 2. Why the two directions are not symmetric, said before the data

**ENGU-Q side (NOISE state -> ENGU-Q entries): the refill effect is the enemy.** The measured reason
seven entry filters failed on this family is that declining a signal frees the slot and the walk
takes a later, worse signal of the same move. A veto cannot escape that by having a better state
variable, so **no veto arm is pre-registered on the ENGU-Q side.** Only a size tilt is, which changes
what a taken signal is worth and never changes which signals are taken.

**NOISE side (ENGU-Q state -> NOISE entries): the refill effect does not apply.** NOISE is a
short-hold leg that sets one stop at entry and never moves it; it has no multi-week survivors and no
slot to refill, so a declined NOISE signal is simply not taken. A veto is therefore an honest arm
there, and this is the half I expect to be readable.

## 3. The state knob

`NOISE_STATE`, read on the **CLOSED 5-minute NOISE bar at or before the other family's signal bar**
(never the forming bar; the lag is asserted in the harness), one of:

- `flat` - the NOISE leg holds nothing
- `long` / `short` - it holds a position on that side
- `unavailable` - outside RTH, or the NOISE tape has no bar

and `ENGUQ_STATE` the mirror: `flat` / `long` (ENGU-Q is long only) / `unavailable`.

Both are built from each leg's own backtest trade list on its own pinned master, so nothing is
re-simulated and no new look-ahead path is created. **Causality:** a state is only read from bars
that closed strictly before the signal bar's close.

## 4. Arms, fixed here

| arm | direction | rule |
|---|---|---|
| A1 | NOISE state -> ENGU-Q | **size tilt** on ENGU-Q entries: x`w_opp` when NOISE is SHORT at the signal bar, x`w_same` when NOISE is LONG, x1 when flat or unavailable |
| A2 | ENGU-Q state -> NOISE | **entry veto** on NOISE entries: skip NOISE entries on the side named by `veto_side` while ENGU-Q holds its long |
| A3 | ENGU-Q state -> NOISE | **size tilt** version of A2, so the veto's failure cannot be confused with the state carrying no information |

`w_opp`, `w_same` and `veto_side` are **knobs in the Auto-Validate search space**, not grid points.
Each arm is the crown's own search space PLUS its knob; the lattice must be able to land exactly on
the crown (w = 1, veto off), because the house has broken that three times.

**Twins, so a result cannot be a size story:** every sized arm is reported beside a **capital-matched
constant twin** at the same average exposure. A sized arm that does not beat its own flat twin is a
leverage result, not a state result.

## 5. GATES, IN ORDER - stop at the first failure

**G0 OVERLAP AND POWER (minutes, no runner, and it can end the round).** Before anything is sized or
vetoed, report: how many ENGU-Q entries fall in each NOISE state; how many NOISE entries fall in each
ENGU-Q state; the gross points a trade and the cost a trade in each cell; and the trades needed for
80% power at the measured per-trade difference. **If the addressable cell holds fewer trades than its
own 80%-power line, or fewer than 50 a year, that direction closes at draft with one ledger row and
no trial spent.** This is the scope's C2 screen, computed by hand until `tools/power_screen.py` lands
on w85, and the number is published whichever way it falls.

**G1 PARITY.** Each fork with its knob off must reproduce its parent's trade list exactly (ENGU-Q
2,053 trades over 2010-06-07..2026-06-30; NOISE its own count). A mismatch stops the arm.

**G2 AUTO-VALIDATE, 900 trials x 8 folds** (the owner's rule, never lowered), windows and masters
pinned, co-tuned, **lockbox untouched and veto-only**, maximum 2 arms queued (the runner takes 2 a
night). Priority if only two fit: **A2 then A1** - the NOISE side first, for the §2 reason.

**G3 THE BAR, written before the data.** An arm HOLDS only if all of:
1. its whole-stretch **ROC@30k** beats the unfiltered crown's;
2. it beats it in **>= 7 of the 8 folds** (P(X>=7 | p=0.5) = 0.035; 6 of 8 is suggestive and is not a
   pass);
3. it is **not one episode** (worst DD <= 1.3 x DD5) - and a better DD% from peak with a WORSE DD5 is
   recorded as "one episode moved", not as an edge;
4. **>= 50 trades a year** kept;
5. it beats its own capital-matched constant twin.

All four numbers (ROC@30k, DD5, DD% from peak, daily Sortino including zero days) from
`augur_engine.drawdowns.four_numbers` on the DAILY mark-to-market series, per arm per stage.

## 6. What could fool us, listed before the run

- **Both legs trade NQ.** A filter that helps one leg can stack drawdown at book level. A book-level
  read of #463 is reported for any arm that reaches G3, and no book change is proposed from this round.
- **The 2020 episode.** Ledger 2.55's hedge arm lost its lead without Feb-Apr 2020, and shelf-37's
  ENGU-Q cell was ~10 high-VIX trades. Every arm is reported with and without 2020-02..04.
- **Placebo.** Any arm reaching G3 is also run against **200 shifted-calendar placebos** (the state
  series moved +/- 1 to 10 sessions), as 2.55 was; a lead inside the placebo distribution is not a
  lead. 2.55's sat at the 39th percentile.
- **Long/short split** per arm, because r24's money was all shorts.
- **The state is another family's crown**, so it carries that family's own selection history. A lift
  here could be NOISE's fitting showing up in ENGU-Q's P&L; that is why the twin and the placebo are
  gates rather than extras.

## 7. Prior, written before the data

- **I expect G0 to kill A1.** NOISE is flat most of the time; the cell where NOISE is short AND
  ENGU-Q fires inside RTH is plausibly a few hundred trades over nine years, and executor r1 and the
  census both say this leg's money is in a small number of long survivors, so the sized subset will
  be too thin to resolve against its own power line.
- **A2/A3 are the real test** and I give them maybe one chance in four of reaching G2, less of
  passing G3. Twelve prior rounds on this exact shape have failed, and the honest reason to run it at
  all is item 2 of §0 - the co-tuning has never been tried, and E2 exists to price that.
- **I do not expect a book lift.** The MDL map wants about $15k a year at a $30k drawdown of its own
  from a change like this, and nothing in the record suggests a state veto on two NQ legs delivers it.

## 8. Method pins

- Harness `tools/enguq_crossfamily_state_r1.py`, frozen with this document, checks this file's LF
  sha256 at start, prints its own, and carries a `selftest` that proves the state lag and the
  "unavailable = taken unchanged" rule on hand-made bars with no data.
- Masters pinned by FILENAME AND ROW COUNT, printed and recorded (a refill moves every bar index -
  this lane's own 10-18 finding; the C0 parity gate in executor r1 failed for exactly that reason).
- RUN-BEFORE-MAIN: the frozen commit is pushed as `prereg/enguq-crossfamily-state-r1` and its
  sha256s go to MANAGER before the harness is launched.
- One run-record JSONL line per arm per stage in `C:\EdgeLog\run_records\enguq_202611.jsonl` through
  `tools/run_record.py`, handed the daily series; ledger row on the lane's ship of the day.
- Addenda are appended with a time and a reason, never a replacement. No arm, threshold, side or
  weight is added, moved or dropped after a number is seen.
