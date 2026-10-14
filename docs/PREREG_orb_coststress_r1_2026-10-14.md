# PREREG: ORB COSTSTRESS r1 - what trading cost the live Webull ORB leg can carry (ORB lane, 2026-10-14)

**Why.** MANAGER #77 (owner 10-14: keep testing). The ORB_R6 execution check built for the harm monitor (ORB #857 item 2) found that the Webull
executor's fills ran about $0.21 a share per round trip worse than the cloud engine's own prices, on 4 trades. The leg's harm bands
(bookq q38) assume $0.02. If the real cost is ten times the modelled one, the live leg may sit below the house bar. This test asks two
questions before more trades accumulate. (1) How much cost the leg can carry on its walk-forward. (2) What the live fills say so far,
and how many trades it takes to know.

**What is tested.** Nothing new and no search. The leg exactly as the box runs it: `api.cloud_signal.CROWN_LEGS["ORB_R6"]` (ORB_3_6_R6.py, #314's
settings) on the QQQ 5m Alpaca master (source alpaca_split_rth), through `augur_engine.engine.run_backtest` at cost 0, per share, at the
live unit of 10 shares, each trade booked on its exit day.

**Stretch.** WF only: 2016-07-01 .. 2025-06-29 (bars from the master's start for warm-up; trades entering before 2016-07-01 dropped). The
lockbox (2025-06-30 on) is not read.

**Cost grid.** $ per share per round trip: 0.00, 0.02 (the house figure), 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40. Each trade pays
10 x cost.

**Numbers per cell (house four + context).**
- ROC %/yr at a $30k worst drawdown: 30 x net a year / worst drawdown, on the daily curve from flat.
- DD5.
- DD % from peak (`augur_engine.drawdowns.dd_pct_peak`, start $100,000), on the leg sized to a $30k worst drawdown.
- Sortino: daily mean / root-mean-square of the negative days x sqrt(252).
- Also: net a year at 10 shares, trades a year, PF.

**Break-evens.**
- c0, the cost that zeroes WF net, solved exactly as gross / (shares x trades).
- c15, the cost where ROC @ $30k falls to 15 (the MDL bar), by bisection to $0.001.

**Live read.** Forward, from the newest box_backup pull-job folder (tools/harm_monitor.webull_folder):
- Every closed ORB_R6 trade with both engine signals and an executor fill, matched on trade_id.
- Execution shortfall a share per round trip = adverse entry gap + adverse exit gap vs the engine's ref prices. Reported overall and split by exit
  type (EOD vs other).
- n, mean, sd and a two-sided 95% t interval.
- Engine trades with no fill are counted and named; they are not costed.

**Verdict (set now).**
- **V1 (walk-forward):** report c0 and c15. If c15 < $0.05, the leg is cost-fragile on its own backtest.
- **V2 (live):**
  - mean shortfall < c15 and upper 95% bound < c15 -> "live cost inside the bar";
  - mean > c15 -> "at the measured cost the leg is below the ROC-15 bar: flagged to MANAGER, an owner decision; nothing changes";
  - otherwise "undecided at n trades".
  - Power line: the n at which the 95% half-width falls to (c15 - 0.02) / 2, using the measured sd.
- Report-only. No rule, size or live setting changes. #314 untouched.

**Harness:** `tools/orb_coststress_r1.py`. It checks this note's LF sha256 at start and stops on a mismatch.
