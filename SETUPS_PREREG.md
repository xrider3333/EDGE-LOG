# SETUPS round 1 — pre-registration (CBU-Q, CBD-Q, EBU-Q, ENGU 2.0, ENGU 2.0 D)

Written and committed 2026-09-25, **before any strategy file for these rules exists**. Owner ask, verbatim:
"back test these on EL. make them work". Background and prior art: `setups/ALGO_SCOPE.md`; the answer key
is the journal in `setups/` (44 real futures trades).

"Make them work" is read as: search honestly inside the spaces declared here, on data the tests have not
seen, and report what survives. Nothing is rescued by moving a bar, adding a filter after the results, or
touching the held-out stretch. Honest prior: low (rounds 37-38 closed 1-minute fixed-target scalps; the
legacy ENGU files died under honest fills).

## 1. Families and files

| File | Family | Setup | Side |
|---|---|---|---|
| `augur_strategies/CBUQ_1M_1_0.py` | CBU-Q (new) | CBU: new high of the day above a morning level | long |
| `augur_strategies/CBDQ_1M_1_0.py` | CBU-Q | CBD: the short mirror | short |
| `augur_strategies/EBUQ_1M_1_0.py` | CBU-Q | EBU: local breakout below the day's high | long |
| `augur_strategies/ENGU_2_0.py` | ENGU (legacy family) | ENGU: engulfing candle inside the day's range | long |
| `augur_strategies/ENGU_2_0_D.py` | ENGU | ENGD: the short mirror | short |

CBU-Q is added to the family list (runner, index.html tables, family_rename, tests, CLAUDE.md) in the
same commit as the files.

## 2. Data and windows

- ES and NQ 1-minute 24-hour masters (`session eth`, source `db_noadj_eth`). Sessions roll at 18:00 ET
  (computed from the bar timestamps, never from `day_id`). Decisions only on regular-session bars
  09:30-15:59 ET.
- **Selection** (triage and validate optimisation): 2010-06-07 to 2025-07-06.
- **Held-out** (validate lockbox): 2025-07-07 to 2026-04-06, i.e. `date_to` 2026-04-06 with
  `lockbox_months` 9 (validate.py: start = date_to - int(9 x 30.44) days). Deviation from the house 12
  months, so that no journal trade (they start 2026-04-07), no design choice taken from them, and not the
  2026-07-01..08-05 data hole sits in the held-out stretch.
- Nothing dated 2026-04-07 or later is used for outcomes. April-September 2026 is used only for recall:
  does the final rule fire where the owner traded.

## 3. Mechanics shared by all five files

- **Decision** at the close of regular-session bar i; **entry** at the open of bar i+1 (same session,
  entry no later than 15:58). One trade per session per file (the first signal).
- **ATR14** = simple mean true range of the 14 bars ending at i-1 (24-hour tape).
- **Volume baseline** = mean volume of the 10 bars before i; for the 09:30 bar it is the mean volume of
  the 09:30 bars of the prior 20 sessions (the pre-market average would make every 09:30 bar a spike).
- **Stop** = low(i) - `stop_buf_atr` x ATR14 (long; high + buffer for a short). Risk = entry - stop. No
  trade when risk <= `min_risk_atr` x ATR14 or when the entry is at or beyond the stop.
- **Exits** (`exit_mode`): `ride` = breakeven armed when a bar CLOSES at or beyond entry + `be_R` x risk,
  applied from the next bar, flat at the 15:59 bar's close; `trail` = as ride, and once breakeven is
  armed the stop also trails the lowest low (highest high) of the prior `trail_bars` bars, only moving in
  the trade's favour; `target` = fixed target at `target_R` x risk with a 15:59 flat (a control that
  rounds 37-38 say will fail). Stop-first when one bar touches both; a bar opening beyond the stop fills
  at its open; targets fill at the target price.
- **Levels**: premarket = 04:00-09:29 ET of the session; prior day = the previous session that has
  regular-session bars (holidays skipped); on a roll seam (the house `detect_roll_seams`, copied
  verbatim) the prior-day level is missing and any rule that needs it does not trade that session.
- **Costs**: NQ 0.533, ES 0.363 points per round trip (house); stress NQ 0.783, ES 0.613.
- Trades are 5-tuples (fill bar, exit bar, points, side, entry price).

## 4. The rules (short files flip every comparison)

**A. CBU-Q / CBD-Q.** At bar i: close > the highest high of today's regular-session bars before i
(skipped for the 09:30 bar); close > `level` (`level_mode` pm = premarket high, pdh = prior-day high,
both = above both); minutes from 09:30 to the bar's close <= `end_min`; `first_bar` allow/skip for the
09:30 bar; volume >= `vol_mult` x baseline (0 = off); if `base_bars` > 0, the span of the `base_bars`
bars before i <= `base_k` x ATR14.

**B. EBU-Q.** At bar i (09:31 or later): close > the highest high of the `brk_n` bars before i AND close
<= the highest high of today's regular-session bars before i (a local break inside the day's range);
volume, base, window and exits as A.

**C. ENGU 2.0 / 2.0 D.** At bar i (09:31 or later): a green candle; body >= `body_frac` x range; body >=
`body_mult` x the median body of the 10 bars before; close > the highest high of the `eng_n` bars before
(the engulf); volume >= `vol_mult` x baseline; close < the day's regular-session high so far (inside the
range); a pullback: (day high so far - lowest low of the 10 bars before) >= `pb_atr` x ATR14.

## 5. Knob spaces (what Auto-Validate may search; `auto_expand` off)

- All files: `exit_mode` {ride, trail, target}; `be_R` 0.5-2.0 step 0.5; `trail_bars` 5-30 step 5;
  `target_R` 1-5 step 1; `stop_buf_atr` 0-0.5 step 0.25; `min_risk_atr` 0-1 step 0.5; `end_min` 30-360
  step 30; `vol_mult` 0-4 step 1.
- A: `level_mode` {pm, pdh, both}; `first_bar` {allow, skip}; `base_bars` 0-6 step 3; `base_k` 1.5-3.0
  step 0.5.
- B: `brk_n` 5-20 step 5; `base_bars`, `base_k` as A.
- C: `body_frac` 0.5-0.8 step 0.1; `body_mult` 1.5-3.0 step 0.5; `eng_n` 1-3; `pb_atr` 0-4 step 1.

## 6. Triage (selection window only; the files' own `run_backtest` through the engine)

Pre-declared cells, every one reported:

- A (each side): `level_mode` {pm, pdh, both} x `end_min` {30, 120, 360} x `vol_mult` {0, 2} x exit
  {ride be_R 1, trail be_R 1 / 15 bars, target 2R}; `first_bar` allow, base off, buffer 0, min risk 0.
  54 cells.
- B: `brk_n` {5, 10, 20} x `end_min` {30, 120, 360} x `vol_mult` {0, 2} x the same 3 exits. 54 cells.
- C (each side): `body_mult` {2, 3} x `pb_atr` {0, 2} x `end_min` {60, 360} x `vol_mult` {0, 2} x the same
  3 exits; `body_frac` 0.6, `eng_n` 1. 48 cells.
- 258 cells x ES and NQ = 516 backtests, scored at the house and the stress cost.

**House bar** (the round-37 `score()` in `tools/r37_scalp_triage.py`, in dollars at $20 NQ / $50 ES): PF
>= 1.25, net / max drawdown >= 8, >= 300 trades, >= 6 of 8 chronological slices positive, top-10 share <
90% with positive net without them, $/trade >= 2x the round-trip cost.

**A file advances** only if a cell passes the house bar at house cost, keeps PF >= 1.10 at the stress
cost, and at least 2 of its one-step neighbours (one knob moved to the next declared value) keep PF >=
1.15. Otherwise the file is dead at triage.

## 7. Validate (advancing files only)

`type validate`, the passing instrument, `timeframe 1m`, `session eth`, `source db_noadj_eth`, `date_from`
2010-06-07, `date_to` 2026-04-06, `lockbox_months` 9, `n_trials` 900, `wf_folds` 8, `auto_expand` false,
`oos_sample_k` 0, `select_oos_topk` 10, house `cost_pts`, `transfer_to` the other instrument. Before
queueing: `tools/queue_guard.py` (split 2025-07-07) and `tools/concentration_check.py` must not say
ARTIFACT. **Verdict**: PASS required (WEAK or FAIL = dead); the crowned config's held-out stretch needs
>= 60 trades and PF >= 1.10; and against ORB #314 and NOISE #382 on the same window the file must earn
on days the crown is flat (net > 0 and >= 30% of its own net), or it is that crown's factor, not a new
family.

## 8. Wave 2 (declared now; runs only if nothing advances in wave 1)

The same five files and the same cells on **5-minute** 24-hour bars (bar-count knobs stay in bars,
`end_min` stays in minutes). Reason: the shop's own lesson that the bar size, under a tail-keeping exit,
is the lever (NOISE on 2 minutes). Same bar, same validate rules. Any other idea after the results needs
a new pre-registration.

## 9. Look-ahead alarms and parity

- A0: perturbing every bar after bar k must leave every trade entered at or before k unchanged (a test in
  `tests/`).
- A1: any triage cell with PF >= 2 or net / drawdown >= 20 is treated as a look-ahead alarm and audited
  before it is believed.
- A2: each short file run on price-inverted bars reproduces its long file's trades exactly.
- Multiple testing: 516 triage backtests here, plus the 324-combination scratch scan run while scoping (setups/ALGO_SCOPE.md), plus wave 2
  if it runs. The neighbour rule in section 6 is the guard against a lucky cell.

## 10. Deviations log (append only)

- (none yet)
