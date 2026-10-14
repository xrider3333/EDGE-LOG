# PREREG - NOISE #422 + PROFIT-TARGET KNOB: a 900-trial Auto-Validate (owner order 10-14, MANAGER #91)

Written 2026-10-14 by the NOISE lane, before the job was queued. It lands on main before the queue (MANAGER #91).

## Why
- **The owner (10-14):** "keep testing ... autovalidate on EL the top 3 results from the last few weeks that you find
  promising. let me know their past runs."
- **NOISE's cell (MANAGER #91):** NOISE #422 with a profit-target knob opened (off / 1R / 1.5R / 2R / 3R) on top of
  its normal ranges.
- **What led here:** NOISE TARGET r1 (ledger 2.151, owner override 10-12) ran +1R on #422's walk-forward.
  - ROC@30k rose from 83.2 to 96.9.
  - But it was flagged as one episode: Sortino fell (4.13 -> 3.91), the month-block bootstrap gave P(gain) = 0.27, and
    the 2R neighbour gave the gain back (83.0).
  - This job tests the knob properly, with #422's whole search surface around it.

## The job: pinned to run #422's own shape (its run record, read 10-14)

**Files:**
- `augur_strategies/NOISE_1_8_CT304H_TP.py`: NOISE_1_8_CT304H.py with one more open knob, `tp`.
- `augur_strategies/NOISE_1_10_TP.py`: NOISE_1_0.py unchanged, plus `tp_r`.

**OPEN:**
- #422's own 27 cells, unchanged:
  - gate_len 16 / 20 / 24
  - gate_ratio 0.85 / 1.0 / 1.15
  - tilt_mult 1.25 / 1.5 / 1.75
- tp off / 1.0 / 1.5 / 2.0 / 3.0 x R (R = fill to the trade's initial stop).
- That is 135 cells.

**PINNED:**
- Run #304's core: CT304H's _FROZEN, written out literally.
- The 60-minute verification frame.

**Why the core stays pinned:** the core is #422's own design. Its 27 cells are the "real ranges" run #422 searched. The
core itself was crowned by run #304's own validate. Opening it would re-search #304, not test the target.

**Target rule:**
- A resting limit at entry + tp x R.
- Checked inside every bar after the fill bar, after the stop: a bar that touches both fills the stop.
- A bar that opens through the target fills at that open.
- The exit frees the slot for the next break.

**Market, cost and size:**
- NQ 5m RTH, source db_noadj_rth, master pinned by filename `NOADJ_NQ_5m_RTH.csv`.
- The engine runs signals ratio-adjusted and fills raw: the 10-08 roll guard, the same path the parity used.
- Cost 0.533 pt round trip, $20 a point, commission 0, slippage 0 (run #422's).

**Window and validate settings:**
- 2010-06-07 .. 2026-07-16 (run #422's window).
- Lockbox 12 months: 2025-07-16 .. 2026-07-16, the same as run #422's. That lockbox is already SPENT: read for #422 and
  in BOOK LOOKS.
- WF split 2016-06-30, 8 folds, warm_days 300.
- 900 trials (OWNER RULE), discover auto.
- Selection wf_oos_topk, k = 10, oos_sample_k 30.
- mc 500.
- No AI rounds.

**Default and parity:**
- The file default is run #422's crown (20 / 1.15 / 1.75) with tp off. A call with no params IS run #422.
- Parity was run before queueing (`tools/noise_422_tp_parity.py`, on the shared checkout's engine and master):
  - **P1:** tp off at the crown = NOISE_1_8_CT304H through the engine, 4,828 trades identical (bars, points, sizes).
  - **P2:** NOISE_1_10_TP at tp_r 0 = NOISE_1_0 at the #304 core, to the cent.
  - **P3:** tp 1.0 = NOISE TARGET r1's separately coded T100 cell, 6,178 trades identical.
- The master has been restated since run #422 ran: the 2020 1m-hole splices were filled 10-12 / 10-14. So the crown now
  reads 4,828 trades over the window against the run's 4,825. The job re-runs tp off itself, so every comparison sits on
  one tape.

## Reading rule (fixed now)

**What is read:**
- The engine's own verdict (PASS / WEAK / FAIL) and its crowned cell.
- **FOUR NUMBERS** (owner rule 10-11) for the crown, WF and lockbox apart: ROC@30k, DD5 (with the one-episode flag),
  DD% from the peak (house helper), Sortino.
- Also: win rate and average win / average loss.
- The same numbers for **the tp-off twin at the crown's gate cell**, so the target's own effect is printed beside it.

**A "target lift" stands only if ALL of these hold:**
1. The crowned tp is not off.
2. Over its own tp-off twin, WF ROC@30k AND WF Sortino both rise.
3. The rise is not one episode: the crown's worst WF drawdown is no more than 1.3 x its DD5, or the twin's flag is
   unchanged.
4. Both tp neighbours (the next level up and down; off counts for 1.0) keep WF ROC@30k above the twin's.

**Otherwise:** nothing changes. The lockbox is spent, so it is a veto and a report only, never a reason to adopt.

**Prior, written now:** the crown picks tp off or 1.0, and the lift does not survive rule 3 or 4: P(target lift stands)
about 15%. Any change to #422 goes to the owner; nothing live, paper or in BOOK #463 changes from this job.

## Driver
`tools/noise_queue_422_tp_validate.py` (`--dry` first).
- It refuses unless both strategy files are in the shared checkout, the master is the registered `NOADJ_NQ_5m_RTH.csv`,
  and no job carrying its tag or the same file + window is queued, running or paused.
