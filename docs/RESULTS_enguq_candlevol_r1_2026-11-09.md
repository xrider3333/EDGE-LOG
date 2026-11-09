# RESULTS — ENGU-Q CANDLE STRENGTH + VOLUME, DAILY-TREND ALIGNED · ES 15m · r1

**VERDICT: CLOSES AT DRAFT. 0 of 48 cells OPEN; all 48 read BETA, NOT A SIGNAL.** No trial budget
spent, no strategy file written, no lockbox opened, nothing touched live, paper, the box or any
account.

Prereg `docs/PREREG_enguq_candlevol_2026-11-09.md`, LF-normalised body sha
`34e89659a1736cd2b47b371c20a70ba9987dc97f908f440430fdb4f0ad3826b0`, **verified MATCHES by the
harness at start** — the bounds and the verdict words below were fixed before any number existed.
Gate `tools/enguq_candlevol_gate.py` (selftest 16 PASS), output
`C:\EdgeLog\_anatomy_cache\enguq_candlevol_gate\gate.json`.

Master `ADJ_ES_15m_RTH.csv`, 108,097 bars; **pre-lockbox 99,154 bars, 2010-06-07 .. 2025-06-30,
15.06 yr.** Daily trend passes 2,591 of 3,869 sessions at N=20 and 2,725 at N=50.

---

## 1. The headline, which is the paired difference and not a P&L

Per §6 of the prereg the statistic is `delta = mean(signal R) − mean(random-entry R)`, the control
drawn 20 times per signal from the **same 15-minute time-of-day slot on a different session that
passed the SAME daily-trend filter**, running the **identical** floored stop and hold-to-close exit,
seed 20261109. A strategy with no edge scores delta 0.

| | |
|---|---|
| cells screened | **48** |
| **OPEN** | **0** |
| **BETA, NOT A SIGNAL** (delta ≤ its two-sample MDE) | **48** |
| delta negative — signal literally worse than random | 6 of 48 |
| best delta | **0.0439 R** (N=50 bf=0.5 cl=0.9 rv=2.0 f=10), against **MDE2 0.2204 R** |
| that cell's n | 208 trades, 13.8 a year — **below the 50/yr floor as well** |

**Not one cell comes within a factor of two of its own minimum detectable edge.** The best delta is
**five times smaller** than the edge its sample size could have detected.

## 2. The power read, stated rather than buried — and this is the part that is actually conclusive

The large-delta cells are the thin ones and are unpowered; the powered cells are the ones that say
no. Both halves have to be reported or the round proves nothing.

| cell | n | delta R | MDE2 R | read |
|---|---|---|---|---|
| N=50 bf=0.5 cl=0.7 rv=1.0 f=10 | **4,183** | 0.0220 | 0.0501 | powered to ~0.05 R; finds 0.022 |
| N=50 bf=0.5 cl=0.7 rv=1.0 f=20 | **4,183** | 0.0104 | **0.0357** | **the best-powered cell in the grid** |
| N=20 bf=0.5 cl=0.7 rv=1.0 f=20 | 3,627 | −0.0003 | 0.0366 | dead flat |
| N=50 bf=0.5 cl=0.9 rv=2.0 f=10 | 208 | **0.0439** | 0.2204 | the best delta, 20× underpowered |

**The best-powered cell rules out any edge larger than 0.0357 R and measures 0.0104 R.** On that
cell's 20.24-point mean risk, 0.0357 R is **0.72 ES points** — larger than the real 0.45-point round
trip but smaller than the 0.95-point slippage rung. So the honest statement of what this round
establishes is narrow and true: **on ES 15m this entry carries no edge over a matched random entry
larger than about one-and-a-half round trips, and the two cells with the most data measure it at
roughly a quarter of that.** A smaller edge than that is not excluded by 15 years of ES, and would
not be tradeable at 0.95 points anyway.

## 3. How this reconciles with STRONGBAR r1 — it does NOT simply replicate it, and the difference is the finding

TBIS ran the same mechanism on **NQ 5m** hours before this (memory `edgelog-strongbar-r1-dead`,
gate `tools/strongbar_r1_gate.py`, pushed `f36c890c`) with the same random-entry instrument. I read
their result before building this harness and said so in my post; this round was kept because it asks
two questions theirs could not.

| | STRONGBAR r1 (NQ 5m) | this round (ES 15m) |
|---|---|---|
| stop | the signal bar's extreme — **tight** | **max(1.5×ATR20, 10 or 20 pt) — wide, floored** |
| signal arm ROC@30k | **0.49** | n/a — scored in R, not run to ROC (§5) |
| random control | **10.36** | — |
| **signal vs random** | **catastrophically WORSE** (beat random in 2 of 17 years) | **indistinguishable**: 42 of 48 mildly positive, all below MDE |
| grid outcome | 0 of 144 reach ROC 15 | 0 of 48 OPEN |

**TBIS's diagnosis was that the trigger "enters late, after the expansion, with a tight stop, and
gives [the beta] away." This round tests the obvious repair of exactly that diagnosis, and the repair
works mechanically while buying no edge.** With a floored, therefore wide, stop the signal arm stops
being *worse* than random and lands *level* with it. Cost as a fraction of R collapsed as predicted
in §2a of the prereg: **0.022–0.039 of 1R at the real round trip**, against the 0.11–0.36 that the
pre-BBRF 5m cells paid.

So the two rounds together say something neither says alone:

> **The tight stop was never the problem. It was an aggravation.** Remove it entirely and the
> candle-strength + volume trigger does not become an edge — it becomes *nothing*, worth what a coin
> flip in the same regime at the same hour is worth. The money in "trade with the daily trend" is the
> daily trend.

**Two instruments, two timeframes, both stop styles, and the matched control is beaten in neither.**
Nobody needs to test this mechanism a third time, and this is now the ninth entry in the lane's dead
column for volume-as-a-trigger.

## 4. My prior, scored

I wrote **under 15%** in §2 of the prereg, having already lowered it from the 20% I gave BBRF. After
reading STRONGBAR but before building the harness I said in post #2221 that the honest expectation
was now a close. **The prior was correct in direction and the round landed where the prereg said it
would** — §6 pre-declared "if all 48 land here, the round closes at draft and that is reported as the
result," and all 48 did.

**What I got wrong:** I expected ES 15m to come out *worse than random* like NQ 5m. It came out
*level*. The floored stop mattered more than I credited, just not in the direction that pays.

## 5. What this round did NOT do, and one clause that could have been vacuous but was not

- **No run records.** The 48 gate cells are **per-trade R statistics with no daily dollar series**,
  so there are no four numbers to write and nothing is re-derived from a net. This is the same call
  made for BBRF's 48 gate cells in `2.220`, and it is deliberate: the COMPARE chart cannot tell a
  figure that does not exist from one that was never measured.
- **Arms B and C were never screened.** §5 of the prereg restricted the gate to arm A on purpose,
  because arm A is the control and the question was whether the entry does anything at all. It does
  not, so the fixed target `T ∈ {1,2,3}` and time stop `M ∈ {4,8,16}` were never run and my §4
  prediction that **arm A beats B and C stays untested here** — it remains at seven independent
  confirmations, not eight.
- **No short arm, no limit fills, no second data source** for the daily trend; daily bars were
  resampled from the same 15m master, as pinned.
- **The anti-vacuity clause held.** §6 required that "no clause in this gate can be satisfied by
  construction", written in after my BBRF ceiling clause turned out near-vacuous and its 36 "OPEN"
  verdicts worthless (`2.220` §1a). A paired difference against a matched control cannot fail that
  way, and it did not: the control's own mean R is **0.0054–0.0340**, visibly non-zero and visibly
  varying by cell, so it is measuring something real rather than returning a constant. **A constant
  repeated across heterogeneous cells is never a result**, and this one is not constant.

## 6. Look-ahead guards, as pinned in §3

Complete signal bar; **fill at the next bar's open**; relative volume against the same 15-minute slot
over the **prior 20 sessions only**, shifted a session; daily trend from the **previous completed
session**; ATR shifted one bar; one tape, no splice. The stop is checked **before** any favourable
price on every bar, so a bar covering both books the stop.
