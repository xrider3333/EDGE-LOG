# ENGU-Q round 62 - FORWARD SHADOW pre-registration (written before the first shadow bar)

Owner GO through the MANAGER chat, 2026-09-29 (inbox item #18), on option (a) of the round-62
write-up: run the cash-session entry-gated cell as a forward paper shadow beside the live ENGU-Q
#335 cell, with NO orders, judged only on bars after today. The 08:00-17:00 ET window rides as a
second, labelled arm. This file is the bar, and it is committed before the first shadow bar is
counted.

## Why a forward shadow rather than another backtest

Round 62 (ENGUQ.md 2026-09-28, v73.938) failed two of six pre-registered clauses and was written
up dead as queued work. The awkward residue: the ONE window that clears the failing clause,
08:00-17:00 ET, is also exactly what a purely mechanical rule picks - every hour whose median
one-minute volume is at or above the tape's own median. But that rule was written down AFTER the
plateau table had been read, so adopting it on this history would be choosing the bar after seeing
the answer. **Forward bars are the only data left that this round has not read.**

## What runs

Two shadow arms on `augur_strategies/ENGUQ_1M_ETH_R62_1_0.py`, both carrying the live crown's
fourteen knobs unchanged and differing from the live leg in the entry window alone:

| arm | window (ET) | status |
|---|---|---|
| `ENGUQ_335_S1` | 09:30-16:00 | **the pre-registered arm** - the US cash session, fixed on mechanism |
| `ENGUQ_335_S2` | 08:00-17:00 | **exploratory, labelled** - the volume-defined window, chosen after reading the plateau |
| `ENGUQ_335` | 24 hours | the live crown, and the CONTROL for both arms |

No orders. Neither arm has a NinjaTrader row, so the NinjaTrader port is untouched and nothing
reaches the Webull book, where ENGU-Q is paper-only by the owner's 2026-09-28 decision. Both arms
carry `live_from = 2026-09-30`, so nothing from today or before counts.

## The bar, written before any forward bar is read

**The primary test is the MECHANISM, not the money, and that is deliberate.** ENGU-Q takes about
120 trades a year, its documented loss streaks run to 21, and its whole edge historically sits in
about 31 trades. A few months of forward profit and loss cannot settle anything. Day-one survival
is a per-trade rate with far more power, and it is the exact quantity the idea rests on.

1. **PRIMARY.** Day-one survival for the entries `ENGUQ_335_S1` takes must exceed day-one survival
   for the entries the gate removes by **at least 15 percentage points**. The backtested gap was
   about 25 points (36-39% against 11-15%) and was stable across all four eras, so 15 is a real
   hurdle rather than a formality.
2. **CHECKPOINTS, and no reading between them.** Judge at **60 gated entries**, and again at
   **150 gated entries**. Reading the gap continuously and stopping when it looks good is peeking;
   these two points are the only ones that count.
3. **SECONDARY, reported from the start but binding only at 50+ forward trades in an arm:** ROC
   per year at a $30,000 worst drawdown with the drawdown valued daily, each arm against the
   `ENGUQ_335` control, walk-forward and lockbox not applicable here - this is one live stretch.
   Also reported each time: whether the arm's forward net survives deleting its single biggest
   trade, the clause the live cell fails on history.
4. **FAILURE.** If the survival gap is under 15 points at the 150-entry checkpoint, the mechanism
   does not hold forward and round 62 is closed for good, not re-cut.
5. **S2 CANNOT BE ADOPTED ON ITS OWN.** It exists to answer one question - does the wider,
   volume-defined window behave like the cash-session window, or not? If `ENGUQ_335_S1` fails and
   `ENGUQ_335_S2` passes, that is NOT a pass; it is evidence that the earlier plateau was noise,
   and it would need its own pre-registration on data later than these checkpoints.

## How this could still fool us - declared now

- **Small samples.** Sixty gated entries is roughly six months of ENGU-Q at its historical rate.
  The survival gap is measurable there; the money is not, which is why the money clause is
  secondary and why no adoption decision rests on it.
- **One regime.** Everything after 2026-09-30 is a single market environment. A gap that holds
  forward is consistent with the mechanism and does not prove it; a gap that vanishes is the more
  informative outcome, and that asymmetry is accepted in advance.
- **The gate is on the SIGNAL bar, the shadow's own fills land later.** About 45% of this file's
  fills arrive 2-10 bars after the signal, so a signal at 15:55 can fill after 16:00. That is
  intended and matches the backtest, but it means "cash-session entries" is a statement about
  signals, never about fills.
- **The control shares its history.** `ENGUQ_335` has been live-shadowed since 2026-09-08, so its
  own forward record starts earlier. Only the overlapping window from 2026-09-30 is comparable,
  and only that window will be quoted.
