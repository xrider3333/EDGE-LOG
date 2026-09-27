# ORB round 60 — the evidence for the crown call (2026-09-27)

Pre-registered in `tools/orb_r60_crown_evidence.py` and pushed (1dcf1c74) before any number
existed. Parity first: #257 reproduced its stored run exactly (2,751 trades, $416,381.84).
Output: `_r60_crown_evidence.log`.

## Test A — is #257's money lead real, or a few lucky years?

Paired calendar-year block bootstrap, 20,000 draws, the same resampled years for every config;
NQ 5m RTH, one contract, certified window 2010-06-07 → 2026-08-13. Pre-registered bar: a lead is
**REAL** only if P ≥ 0.80 on **both** the whole window and the recent regime (2018+).

| #257 against | P(more money) whole / 2018+ | Called | P(deeper drawdown) whole / 2018+ | Called |
|---|---|---|---|---|
| **#314 (crown)** | 0.718 / 0.808 | **COIN FLIP** | **0.956 / 0.946** | **REAL** |
| #234 (control) | **0.843 / 0.905** | **REAL** | 0.705 / 0.754 | not established |
| #239 (breakeven 0.8) | 0.750 / 0.817 | COIN FLIP | 0.796 / 0.799 | not established |

Actual whole-window figures: #257 $416,382 / drawdown $32,505 / 2,751 trades; #314 $397,150 /
$28,857 / 2,299; #234 $389,874 / $29,142 / 2,607; #239 $394,864 / $29,377 / 2,607.

**Read:** #257 reliably earns more than the control, but against the crown its money lead is not
established on the pre-registered bar, while its deeper drawdown is. Moving the crown from #314 to
#257 would swap a drawdown difference that is real for a money difference that is not.

## Test B — the only unseen data (report only)

Trades entered 2026-08-14 → 2026-09-25, the weeks no ORB validate saw, on the roll-corrected
master (history from 2025-06-01 so both filters are warm). Raw master beside it.

| Config | Roll-corrected: trades / money / won | Raw master |
|---|---|---|
| #257 | 20 / **−$7,663.20** / 7 | 20 / −$7,663.20 / 7 |
| #314 | 6 / **+$14,131.04** / 5 | 7 / +$11,720.38 / 5 |
| #234 | 7 / +$6,520.38 / 5 | 8 / +$4,589.72 / 5 |
| #239 | 7 / +$6,520.38 / 5 | 8 / +$4,589.72 / 5 |
| #421 cell | 20 / −$413.20 / 7 | 20 / −$413.20 / 7 |

- Pre-registered as report-only: six weeks and 6-20 trades cannot separate these configs.
- What it does show is the mechanism working as described: this was a quiet tape, the tighter
  volatility filters (0.70 / 0.75) stood down on most days, and #257's 0.50 filter — which has not
  removed a trade since July 2021 (round 59) — traded through them and lost.
- The roll correction removes exactly the 2026-09-16 splice trade from #314 and #234 and leaves
  #257 untouched. The corrected #314 figure, $14,131.04, matches the corrected ORB_R6 paper window
  in ROLL_AUDIT §4.5.4 to the cent.

## What this changes

Nothing is moved; the crown is the owner's call. The ORB lane's **recommendation** for that call:
**keep #314 as the crown**, keep #257 running as the forward shadow paper leg (`ORB_257`, from
2026-09-28), and revisit when the paper record has enough trades to say more than this bootstrap.
