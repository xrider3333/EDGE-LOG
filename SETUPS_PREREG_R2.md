# SETUPS round 2: point-score leads as an algorithm (pre-registration)

**Written and committed 2026-10-01, before any strategy file or result for this rule exists.**

- **Owner ask (2026-09-30, via MANAGER):** "have strategies test further and AUTO-VALIDATE anything
  promising".
- **MANAGER's lane-specific ask:** test the point-score backfill leads algorithmically on history, without
  re-reading the owner's 53 trades.
- **The leads:** largest body, largest volume, trend-up day and the first half hour. They are exploratory
  results from those 53 trades (`docs/POINT_SCORE_BACKFILL_2026-09-30.md`). Here they become the rule.
  The test runs only on years those trades never touched.
- **Honest prior: low.** In round 1, CBU and ENGU as plain one-minute rules had no edge (CBU-Q #427 FAILED).
  The "largest candle since the low" trigger is new, but it is a close cousin of that rule.

## 1. File and family

- `augur_strategies/CBUQ_PTS_1_0.py`, family **CBU-Q**, long.
- Its short mirror `CBDQ_PTS_1_0.py`, built by price inversion through `augur_engine.setup_kit.mirror_short`.
- Shared mechanics come from `augur_engine/setup_kit.py` (sessions, walk, mirror), exactly as in round 1.

## 2. Data and windows (the same as round 1)

- **Bars:** ES and NQ 1-minute 24-hour **roll-corrected** masters, `FADJ_ES_1m_ETH` / `FADJ_NQ_1m_ETH`.
  This replaces round 1's no-adjust masters plus seam detector, because the 200 EMAs below cross rolls.
- **Selection** (triage and validate optimisation): 2010-06-07 to 2025-07-06.
- **Held-out** (validate lockbox): 2025-07-07 to 2026-04-06 (`date_to` 2026-04-06, `lockbox_months` 9).
- **Nothing from 2026-04-07 on** is used for outcomes, so the owner's trades (from 2026-04-07) stay out.

## 3. The rule (long; the short mirrors every comparison)

The decision is made at the close of a regular-session one-minute bar i (start 09:30-15:58 ET). Entry is
at the open of bar i+1. There is one trade per session: the first bar that passes.

**Trigger: the two leads.**

- **Green candle:** C > O.
- **Largest body since today's low:** |C − O| ≥ |close − open| of every bar in the window.
- **Largest volume since today's low:** V ≥ the volume of every bar in the window.
- **The window** runs from the LATEST bar that holds today's lowest low through bar i. "Today" starts at
  09:30 on i's date.
- The window must hold at least `min_win` bars, so the first bars after a new low cannot qualify by default.

**Filter** (`filt`, one of five; all read only bars closed by bar i):

- `none`: the trigger alone (the raw twin).
- `trend`: the prior regular session's high and low are both above the session before it.
  - A "regular session" is a date whose regular-session bars end at 13:14 or later.
  - Holiday 09:30-13:00 stubs and cut-off days are skipped. No holiday list is needed in 2010-2026.
- `open30`: bar i starts 09:30-09:59.
- `ema3`: C is above the 200 EMA of the 1-minute, 5-minute and 30-minute bars (24-hour bars). For 5m and
  30m, the EMA is that of the bar before the one containing i, as in the point-score spec.
- `yhigh`: C is above the prior regular session's high.

**Stop and exits:**

- Stop = low(i) − `stop_buf_atr` × ATR14. No trade when risk ≤ 0.
- `exit_mode` `ride`: breakeven armed when a bar closes at entry + 1 R, flat at the 15:59 close.
- `exit_mode` `target`: a fixed target at 1 R (the owner's own scalp style), stop or target, flat at 15:59.
- Walk, fills, stop-first and costs are exactly as in round 1, section 3.

## 4. Triage (scan, then strategy file, then belief)

**Cells:**

- 5 filters × 2 exits × 2 sides × 2 roots = **40 cells**.
- Every cell uses `min_win` 5 and `stop_buf_atr` 0, scored at house and stress cost.

**House bar,** unchanged from round 1 section 6 (the round-37 scorer):

- PF ≥ 1.25;
- net / max drawdown ≥ 8;
- at least 300 trades;
- at least 6 of 8 slices positive;
- top-10 share < 90% with positive net without them;
- $/trade ≥ 2× cost.

**A cell advances** only if it passes the house bar at house cost and keeps PF ≥ 1.10 at stress cost. At
least 2 of its one-step neighbours (the filter or the exit moved; `min_win` 10; `stop_buf_atr` 0.25) must
also keep PF ≥ 1.15.

**Also reported, for information:**

- each filter against the `none` twin (does the lead add anything?);
- the share of trades on NOISE #382 days with the same direction (round 1's overlap test).

## 5. Validate (advancing cells only)

**Job settings,** as round 1 section 7:

- `type validate` on the passing instrument; `timeframe 1m`; `session eth`; the FADJ source.
- `date_from` 2010-06-07, `date_to` 2026-04-06, `lockbox_months` 9.
- `n_trials` **900** (never lower), `wf_folds` 8, `auto_expand` false, `oos_sample_k` 0,
  `select_oos_topk` 10.
- House `cost_pts`, and `transfer_to` the other instrument.
- The grid is the file's preset: filter × exit × `min_win` {5, 10} × `stop_buf_atr` {0, 0.25}.

**Before queueing,** `tools/queue_guard.py` and `tools/concentration_check.py` must not say ARTIFACT.

**Verdict:**

- Auto-Validate PASS.
- Then the owner yardstick:
  - ROC %/yr at a $30k daily-valued worst drawdown, walk-forward and lockbox shown apart, plus Sortino;
  - at least 100 walk-forward and 50 lockbox trades;
  - the lockbox stays profitable without its single biggest trade;
  - the filtered version must beat its `none` twin on that ROC and on Sortino.
- It must earn on days NOISE #382 and ORB #314 are flat (net > 0 and at least 30% of its own net).
- Anything that passes goes on the RUNBOARD watch list with the verdict.

**If no cell advances,** the leads are recorded as not tradeable as a stand-alone one-minute rule on
NQ/ES. Point scoring of the owner's real trades continues forward.

## 6. Look-ahead alarms

- Unit tests prove that changing any bar at or after i+1 never changes a decision at i.
- The long/short mirror matches by price inversion.
- The 5m/30m EMA reference bar is the one before the bucket containing i.
- The since-low window never reads past i.
- The "prior regular session" is a strictly earlier date.

## 7. Deviations log (append only)

(none yet)
