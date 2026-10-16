# NOISE x shelf No. 42 (Patton & Sheppard 2015, signed semivariance) - POWER-FIRST MAP CHECK, pre-stated 2026-10-15

MANAGER #114: scope No. 42 to NOISE only. ORB's half is already answered (fixed-sizing r1; TRENDSIZE r1).

## Shelf proposal

Size NOISE to equal FORECAST risk, using Patton-Sheppard's SHAR next-day volatility forecast (down-move and up-move realized
semivariance) instead of the current sizing.

## What the house already knows

- **RISK r1 (ledger 2.47):** V2, sizing by inverse trailing volatility, lost on IS* 2011-16 on the intraday legs (36.1 vs
  47.6). Its WF gain was the 2020 crash, and sized-up and sized-down trades had the same profit factor.
- **RISK r1's R5:** a HAR forecast beat trailing volatility on 2013-16 (QLIKE) but was 18% worse on WF. There is no better
  risk forecast.
- **So:** SHAR can only change NOISE's result if its SIZES differ materially from HAR's and from trailing volatility's.

## The map check (OUTCOME-FREE)

No NOISE P&L is read.

**Inputs:**
- NQ 5m RTH no-adjust master, 2010-06-07 .. 2025-07-15 (the end of run #422's optimize window).
- Intraday 5-minute log returns inside each session, overnight excluded.
- Per day: RV = sum r^2, RS+ = sum r^2 [r > 0], RS- = sum r^2 [r < 0].

**Three next-day forecasts, each fitted by OLS on an EXPANDING window refit at each month start (data up to the prior
day):**
- TRAIL: the mean RV of the last 20 sessions. This is V2's input; no fit.
- HAR: RV(t+1) ~ RV_d + RV_w(5) + RV_m(22).
- SHAR: RV(t+1) ~ RS+_d + RS-_d + RV_w(5) + RV_m(22).

The first fit uses 500 sessions, so forecasts start about 2012-06.

**Size and forecast quality:**
- Size = 1 / sqrt(forecast), normalised to mean 1 over the stretch.
- Scored on 2016-07-01 .. 2025-07-15 (run #422's WF window): QLIKE of each forecast against realized RV.

## Reading rule (fixed now)

**Close-at-draft condition:**
- corr(SHAR size, HAR size) >= 0.95 AND corr(SHAR size, TRAIL size) >= 0.90.
- Then SHAR sizing is HAR / V2 sizing in all but name, and it inherits RISK r1's verdict.
- The line is CLOSED AT THE MAP CHECK, and no NOISE P&L is ever computed for it.

**Otherwise:**
- Report how and where SHAR sizes differ: the share of sessions where |SHAR size - HAR size| > 0.25, and the years.
- Draft a NOISE Stage A prereg (pinned, WF-only; #422 per-trade sizes x SHAR size vs the same trades x HAR size as the
  twin) for MANAGER's GO.

**Printed either way:** QLIKE per forecast (SHAR vs HAR; the paper's claim, as a check of the build) and the size
dispersion (CV).

Four numbers: '-' (a map check, no curve).
