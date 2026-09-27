# DIP round 2 — pre-registered 2026-09-27 (MANAGER tasker, no owner decision needed)

Written before any real-data number for either test was looked at. Both runs are Auto-Validates on
ES 5m RTH, source **db_noadj_rth pinned** (the DIP 1.2+ files remove roll offsets themselves; on an ADJ_
master they would remove them twice), window 2010-06-07..2026-08-24, 12-month lockbox, 8 folds, warm 400,
900 tuning trials, trade floor 30 — the exact settings of #432, the reference.

Reference **#432** (DIP on ES, `NQDIP_1_2.py`): WEAK 5/6 (overfit score only); WF 17.8 %/yr, Sortino 1.32;
LB 25.4 %/yr, Sortino 3.77; whole-run drawdown $66,592. The Frontier book test (#439/#440) failed it as a
seat of the roll-corrected #396 on drawdown, driven by the Feb-Mar 2020 crash.

## Test A — DIP 1.1 rules on ES (`NQDIP_1_3.py`)

DIP 1.1 (seven dip legs) has only ever been validated on NQ. Question: do the extra legs help on ES?
**A replaces #432 as the DIP on ES reference only if ALL hold:** verdict at least WEAK; WF ROC %/yr above
17.8 AND WF Sortino above 1.32; lockbox net positive; whole-run drawdown no deeper than $66,592 x 1.10.

## Test B — DIP on ES with a crash stop (`NQDIP_1_4.py`, new)

`NQDIP_1_4.py` = `NQDIP_1_2.py` + one knob, `stop_atr` in {0 (off), 1, 2, ..., 8} x ATR20 below the entry,
fixed at entry, gap-honest (tests/test_dip_true_rolls.py sections 5; stop 0 reproduces 1.2 trade-for-trade).
The validate searches it like every other knob, so "no stop" can win.
**B is the better DIP on ES for a book only if ALL hold:** verdict at least WEAK; the champion's stop is ON
(stop_atr > 0); whole-run drawdown at most $53,274 (0.8 x #432); the loss from 2020-02-19 to 2020-03-31 at
the champion is smaller than #432's champion over the same dates (measured locally with each file at its own
champion, same data); WF ROC %/yr at least 16.0 (0.9 x #432).
If the search picks stop 0, B is reported as "the search prefers no stop" and #432 stands.

Either way nothing is adopted here. A pass sends the winner back to the Frontier chat for the same seat test
as #439/#440; the book decision stays with the owner.

## Results

Run 2026-09-27 (sections above unchanged; pre-registration commit 48c0e5c8).

**Test A - PASSES its bar. Run #452 (`NQDIP_1_3.py` on ES) replaces #432 as the DIP on ES reference.**
WEAK 5/6 (overfit score 0.90 only; 7 of 8 walk-forward stretches held, efficiency 0.82). WF **22.8 %/yr,
Sortino 1.39** (bar: above 17.8 and 1.32). Lockbox +$31,119 = **31.1 %/yr, Sortino 3.63**, PF 1.78 (bar:
positive). Whole-run drawdown $68,480 (bar: at most $73,251). Champion: RSI 2/25/exit 4, trend 300, N-day 4,
pullback 5/13, capitulation 1.0/0.25/4, IBS 0.10/0.90/8, gap-down 1.0 ATR/2 days; the losing-streak leg off.

**Test B - the search prefers no stop. Run #451 (`NQDIP_1_4.py` on ES) crowned stop_atr = 0**, which is
#432's exact config (1,036 trades, drawdown $66,592, lockbox $25,409). Its walk-forward, where each fold
re-tunes and sometimes picks a stop, fell to 9.8 %/yr, Sortino 0.60 (from #432's 17.8 / 1.32): stops chosen
in-sample hurt out of sample. A crash stop is not the fix for DIP's 2020 drawdown. #432's rules stand.

**Next (pre-registered above):** #452 goes to the Frontier chat for the same seat test as #439/#440. Its
drawdown ($68,480) is no smaller than #432's, so the seat's drawdown clauses are not expected to pass;
the owner decides.
