# ORB late entries - fix A prepared, NOT shipped (2026-11-18, PAPER-WB)

Status: on branch `session/orblate` only. Not pushed to main, not deployed. Owner GO needed (ORB_3_6.py is a frozen crown file).

## Cause
`augur_strategies/ORB_3_6.py` (the live leg ORB_R6 imports it) only evaluates a session once it holds MORE than `or_bars + 1` bars. The box re-runs the plugin as each bar closes, so at the 09:40 bar's close (the first bar that can break out, or_bars=2) today's session has exactly 3 bars and is skipped. The breakout is first seen at the 09:45 close, and the order goes out a whole bar late. A backtest always has complete sessions, so it never sees the guard.

## Fix A (the only option; fix B, live-window padding, was REJECTED by MANAGER and the ORB lane)
```
- if m > or_bars + 1 and or_bars >= 1:
+ if m > or_bars and or_bars >= 1:
```
ORB_3_6.py:296. One character of logic.

## Proof
- **Backtest-neutral (ORB lane's second read, cited, not re-run):** none of the 4,228 sessions has 3 bars. The ORB_314 and R6 trade lists are identical before and after. Scratch: C:/EdgeLog/_anatomy_cache/orb_guard/ (base.py, fixA.py, run.py).
- **Box-path replay:** run through api/cloud_signal.leg_decision_trades on the box's own QQQ_5m.csv and QQQ_1d.csv, ORB_R6 cfg, with `now` = 09:45:05 ET (the 09:40 bar just closed):

| Day | Before (09:45 tick) | After fix A (09:45 tick) | Both at 09:50 tick |
|---|---|---|---|
| 11-03 | no entry | long 09:40 @ 686.94 | long 09:40 @ 686.94 |
| 11-04 | no entry | long 09:40 @ 697.59 | long 09:40 @ 697.59 |
| 11-05 | no entry | short 09:40 @ 671.10 | short 09:40 @ 671.10 |
| 11-09 | no entry | long 09:40 @ 670.5474 | long 09:40 @ 670.5474 |
| 11-10 (control, no 09:40 signal) | none | none | none |

The entry now fires at the 09:40 close, with the same bar, side and price the late tick reported. The next tick reports the same (entry_time, side), so the diff reads it as already sent: no double order.

## Same pattern in the other live legs
- **NOISE #382 (NOISE_1_8_CT304 on NOISE_1_0):** no intraday bar-count gate; its `range(1, n_sess)` is per session. Box evidence: 69 NOISE orders since after_close_s logging began on 11-04, median 8.4-8.6 s after the bar close, 0 over 60 s.
- **ENGU-Q (ENGUQ_1M_ETH_R2_1_0):** code read finds no per-session bar-count gate. No ENGU-Q orders since 11-04, so there is no box timing evidence for it.
- **PICK6 (eodrev_exec):** not bar-driven. It reads a signal file and enters at a fixed 15:30, so the pattern can't apply.
- **ORB:** 10 entries, 2 over 300 s (the 09:40 cases). 1 exit at 307 s (11-11, a different cause, see WEBULL_GOLIVE_READINESS_1118.md).

## LATE alert (same branch)
api/qqq_exec.py `_late_order_alert`, called from `_record_order`: an engine order with after_close_s > 60 s sends one ntfy push per leg + action per ET day. It never blocks an order and never raises. Tests: tests/test_qqq_exec_late_order_alert.py (2). Subset run: 863 qqq_exec tests pass.
