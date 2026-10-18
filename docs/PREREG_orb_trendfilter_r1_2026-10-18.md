# PREREG: ORB TRENDFILTER r1 (T05) - the trend-day catcher as a filter on #314's entries (ORB lane, 2026-10-18)

**Why.** MANAGER #106 (owner 10-18, "more testing on things that are promising"). Board row T05:
- ORB is a trend-day catcher: 24 of its 26 best WF days are NQ top-5% move days (ledger 2.96).
- The harm monitor's trend-capture read has been on main since 10-17.
- Next round: the catcher as a filter on #314's entries vs #314 bare. Stage A on the WF years only; frozen prereg first.

**The catcher (causal).** A trend day is known only at the close, so the filter uses what is known when the order fills: the move so far.
- m = side x (fill price - the session's first RTH open) / the session's first RTH open on the RAW (no-adjust) twin `NOADJ_NQ_5m_RTH.csv`.
  - The back-adjusted level carries future roll offsets (memory: split/roll-adjusted level trap), so a % of it drifts across years.
  - The adj - raw offset is constant inside every session (checked: max spread 0.0000 pts), so the numerator is the same on either master.
- Threshold **theta = 0.584%** (0.00584), set now as the pre-WF upper quartile of raw m (0.5838%) and not tuned. One value only.
  - The harness recomputes the pre-WF q75 and stops if it is more than 0.005 points of % away (the data or the leg moved).

**Draft reads (pre-WF rows 2010-06-07 .. 2016-06-30 only; `C:\EdgeLog\_anatomy_cache\orb_trendfilter\t05_draft2_out.txt`, `t05_draft3_out.txt`).**
- Disclosure: a first draft (`t05_draft_out.txt`) used the adjusted denominator and looked at 3 thetas (0.25 / 0.50 / 0.75%) and the WF
  keep share. It is superseded by draft 2 (raw denominator, theta fixed as the pre-WF q75 before looking at any split).
- **The prior points AGAINST the catcher as a keep-filter.** By tercile of raw m (837 trades):
  - low (0.07-0.35%): +$26 a trade;
  - mid (0.35-0.52%): +$21;
  - high (0.52-2.09%): -$41.
- **theta 0.584%:** kept 210 trades at -0.099% a trade vs skipped 627 at +0.041%, diff -0.139% (95% -0.276 .. -0.003, t -2.00) = -0.20 trade-sd.
  WF keep share 35%; WF per-trade MDE80 0.16 trade-sd.
- **Pre-WF paired Sharpe (annualised, daily, Ledoit-Wolf b 20, 999 draws):** #314 bare 0.05 (flat pre-WF);
  - F+ vs A: diff -0.68 (se 0.32, p 0.05);
  - F- vs A: diff +0.60 (se 0.27, p 0.04).
  - WF MDE80 = 2.8 x se scaled by sqrt(1,550 / 2,260 sessions) = 0.75 (F+) / 0.64 (F-). At 3.08 x se (Holm's first step at 0.025) the WF MDE
    is about 0.82 / 0.70. The F- prior (+0.60) sits just under that bar: an honest 50/50 read, not a sure one. Pre-WF signal thins on WF by
    about sqrt of the session ratio.
- **Map:** 17 of the 26 pre-WF money-day trades filled with m < theta ($20,084 of $33,978). ORB catches a trend at its start, not after it has run.
- **m is mostly the opening-range width:** corr(m, 2-bar OR width / raw open) = 0.83 pre-WF. An OR-width gate was already tested DEAD on the
  legal base (TESTED_CATALOGUE "ORB on the legal base ... OR-width gate"; ORB.md rounds 11 / 11b), and TRENDSIZE (ledger 2.159) died.
  So a report-only OR-width control arm runs beside the filter (below) to show whether m adds anything beyond the width.

Two verdict arms (both pre-set now), each against #314 bare:
- **F+ CATCHER:** take only entries with m >= theta (the filter as asked).
- **F- NARROW OPEN:** skip entries with m >= theta (the side the prior points to; in practice close to a wide-opening-range skip).
Report-only, not in the verdict:
- **W- OR-WIDTH CONTROL:** skip entries whose 2-bar OR width / raw open >= its pre-WF q75 (computed by the harness from pre-WF entries).

## Trades and rows

- **#314** = `api.cloud_signal.CROWN_LEGS["ORB_R6"]`: `ORB_3_6_R6.py` with params or_bars 2, First-candle dir, stop_frac 2.5, atr_filter 0.75,
  vpace_filter 0.8, close_confirm, breakout_buf 0.25, trail 0, target_R 5, partial 0, be_after_R 0.5, flat_eod, skip_holidays. The harness
  asserts this leg and prints the LF sha256 of `ORB_3_6.py` and `ORB_3_6_R6.py`, the bar count, first / last stamp and master fingerprints.
- **Data:** NQ 5m RTH back-adjusted master `ADJ_NQ_5m_RTH.csv` (db_adj_rth) for the engine; `NOADJ_NQ_5m_RTH.csv` (db_noadj_rth) for the %
  denominators only; both must share one bar index. 0.533 points a round trip, $20 a point, one contract.
- **Run:** the engine is asked for data from 2010-05-01; the masters start 2010-06-07 (the run starts at the master's first bar, so the
  indicators warm on pre-WF bars).
- **Scored trades:** only those that ENTER 2016-07-01 .. 2025-06-27 (the WF years). The lockbox is not read.
- **Daily $:** by exit day, on every RTH session of the WF stretch (zero days included); the harness stops if any exit-day P&L falls off it.

## Numbers per arm (A = #314 bare, F+, F-, W-)

- **The four numbers:** via `augur_engine.drawdowns.four_numbers(daily, years=WF length)` on the arm's daily $ scaled to a $30k worst
  drawdown. Scaling changes no ROC or Sortino; DD5 and DD % from peak are then read at $30k on a $100k account.
- **Also:** net a year, trades and trades a year, gross points a trade, cost a trade, worst DD / DD5, and the one-episode flag.
- **The arm vs A:**
  - the Ledoit-Wolf paired Sharpe difference (`augur_engine/sharpe_diff.py`, LF sha256
    704559490f7b3dd1c393c9b8ccdd5333321ddd4ff5269ea55246570a5e3af894, from LW44 commit b736e168 on `prereg/orb-lw44-r1`, loaded by path;
    block 20, 4,999 draws, seed 7) with its 95% interval, two-sided p, and MDE80 = 2.8 x HAC se;
  - the ROC @ $30k difference with a 90% block bootstrap (20 sessions, 2,000 draws, seed 7): REPORT-ONLY (a resampled path's max drawdown is
    not centred on the observed one, so the interval need not contain the point lead).
- **Per-trade split:** kept vs skipped mean return (% of the raw price at the fill), Welch 95%.

## Verdict per arm (set now; decisions on unrounded values)

**LIFTS** only if ALL hold:
1. the paired Sharpe difference vs A is > 0 with p < 0.05, Holm over the 2 verdict arms (strict <: first step p < 0.025, then p < 0.05);
2. ROC @ $30k is above A's;
3. not one episode (worst drawdown <= 1.3 x DD5);
4. MANAGER's bar: gross a trade >= cost a trade, net ROC @ $30k > 0, MDL path = own ROC @ $30k >= 15 (MDL map band |rho_dd| < 0.15; the
   earner route is not used). Trades a year are printed beside it (the MDL map's >= 50 a year is a note, not a clause).

**Otherwise NO LIFT**, read NOT SHOWN, or REVERSED if the Sharpe interval is entirely below 0. Each failing clause is named.

**Overall:** "THE CATCHER FILTER LIFTS #314" if F+ lifts; "A NARROW-OPEN FILTER LIFTS #314" if F- lifts (then a candidate for a pinned
validate under the owner's Auto-Validate rule, nothing live; read beside the W- control, since a lift that W- matches is the OR-width gate
already tested dead on the legal base); else "NO FILTER LIFT".

**Report-only:** no rule, size or live change; #314 untouched. Harness `tools/orb_trendfilter_r1.py` checks this note's LF sha256 and
`augur_engine/sharpe_diff.py`'s at start and stops on a mismatch.
