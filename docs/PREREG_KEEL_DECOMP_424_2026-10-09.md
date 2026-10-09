# KEEL DECOMPOSITION on run #424 - pre-data note (2026-10-09)

For MANAGER and TTM (MANAGER #146 (3), the owner's KEEL question from the reading shelf: Kim-Tse-Wald and Nagel 2025).
Written BEFORE any twin is computed. Read so far: #424's metadata only. That is the strategy, windows and KEEL version
from the run doc, plus the doc's KEEL average size of 1.253 and trust-on 45.9%. No P&L of any reading has been read for this
note (the doc's KEEL row exists on the site; this lane has not opened it). REPORT ONLY: nothing here is adopted, crowned
or traded. TTM independently re-implements every twin below from this note and checks the numbers.

## The run and the data

- **#424:** NQDIP_1_1.py (DIP 1.1) on NQ 5m RTH (db_noadj_rth), 2010-06-07 .. 2026-08-24, multiplier 1.0, cost 0.
  It was superseded for its verdict by #434 (true rolls); MANAGER named #424, so #424 it is. The definitions carry over
  unchanged to #434 if MANAGER prefers it.
- **Reproduction first (tools/backfill_keel.py's path):** the doc's champion through `run_backtest(..., return_trades=True)`
  on the doc's own window. Guard: the ungated pre-lockbox block must match the doc's `gate_validate.ungated_pre`
  (3,185 trades exactly, net within 0.5%), else stop and report.
- **KEEL as shipped in the row:** `ml_keel.keel_walk(arrays, trades, version="v12")` over ALL the run's trades (the walk
  is causal; its 600-trade ledger warms up on 2010-16). Every statistic below is read on the **WF trades only**: entry
  date in [2016-07-18, 2025-08-24). The lockbox (from 2025-08-24) is not read; the KEEL family's lockbox is spent.
- **r_i** = trade i's P&L at size 1 (the run's own units). A reading with sizes s books s_i x r_i on trade i's EXIT
  session. The yardstick is applied to that daily series: WF ROC @ $30k (= 30 x MAR, daily drawdown), DD5 beside it
  ("driven by one episode" if worst DD > 1.3 x DD5), $ a year, Sortino, worst DD, by calendar year.
- **Costs:** the run's are 0, and every reading below keeps 0. At a constant per-unit cost, the timing component
  (below) is cost-neutral by construction, because sum (s_i - s_bar) x c = 0. The leverage part is not.

## KEEL v12's size, in its parts (ml_keel.py as on main)

s_i = event(comp(dow(L_i))), where:
- **L_i (learned part):**
  - Shade branch: when fast-trust t_fast < -0.5 and z != 0, L = clip(1 - z, 0.5, 1.5).
  - Otherwise: L = clip(1 + 1.5 x trust x z, 0.75, 2.0), with trust from the 600-trade dollar ledger, cut by the 50-trade fast ledger.
- **dow:** x1.5 on Fridays, capped at 3.0.
- **comp:** x1.5 when sq60_on, capped at 3.0.
- **event:** x0.5 before a FOMC statement (cut hour 14), applied last.

The fixed tilts alone (L = 1) are exactly `ml_keel.fixed_tilt_sizes_v12`.

## The readings (each on the same WF trades; s_bar = KEEL's MEAN SIZE OVER THE WF TRADES, measured and printed)

1. **RAW:** s = 1.
2. **KEEL:** s_i as above.
3. **F - the Kim-Tse-Wald fixed twin:** s = s_bar on every trade. F's ROC @ $30k equals RAW's: a constant size cancels
   in MAR. On the yardstick, KEEL against F is therefore the whole question. The dollar split is printed:
   KEEL - RAW = (s_bar - 1) x RAW [LEVERAGE] + sum (s_i - s_bar) x r_i [TIMING].
4. **FT - fixed tilts only:** fixed_tilt_sizes_v12, multiplied by one constant so its WF mean is s_bar.
5. **LO - learned part only:** L_i (dow / comp / event off), multiplied by one constant so its WF mean is s_bar.
   The timing of KEEL - FT - LO is printed as the INTERACTION.
6. **M - the Nagel momentum twin (the strategy's own trailing P&L):**
   - m_i = the sum of r_j over the last 20 trades whose EXIT bar is strictly before trade i's entry bar.
   - z_i = m_i / sd_i, where sd_i = the sd of all such 20-trade sums known before i (expanding). z_i = 0 until 100
     trades have resolved.
   - s_i = clip(a + b x z_i, 0.5, 2.0), the clip MANAGER named.
   - a and b are solved together so that M's WF sizes have KEEL's WF MEAN and KEEL's WF SD: the same amount of leverage
     and the same amount of timing. If no (a, b) reaches both inside the clip, b = 0.5 (KEEL's base slope) and only the
     mean is matched, said so.
   - Also printed: corr(KEEL's s_i - s_bar, z_i) and the OLS slope of KEEL's s_i on z_i. This is Nagel's question:
     how much of KEEL's sizing is the strategy's own momentum?
7. **P1 - reversal placebo of M:** the same as M with b -> -b (size up after recent losses), same a, same clip, mean
   re-matched to s_bar. If momentum timing is real, P1 should lose about what M makes.
8. **P2 - KEEL on the sign-flipped series:** keel_walk(v12) re-run with every trade's P&L sign flipped (r_i -> -r_i;
   entries, exits and features unchanged), read on the flipped WF series against the flipped RAW and F.
   - A sizer with real per-trade skill learns the flipped mapping and should still add timing money there.
   - The fixed tilts cannot adapt, so their part flips sign.
   - A sizer that only rides the leg's own run of luck should show little in either direction.

## The null for every timing number (the only "is it more than chance" line)

For KEEL, FT, LO and M, the timing component sum (s_i - s_bar) x r_i is set against 2,000 permutations of that reading's
own WF sizes across the WF trades. Each permutation keeps the size distribution and the mean, and destroys the
alignment with outcomes. Printed:
- the p95 of a plain shuffle;
- the p95 of a shuffle in blocks of 20 trades (keeps size clustering);
- the reading's percentile.

Seeds 20261009 / 20261010.

## What gets reported (to MANAGER + TTM; nothing adopted)

- Per reading: WF net, $ a year, ROC @ $30k / DD5, Sortino, worst DD, mean / sd / min / max size, % of trades sized
  by the shade branch (KEEL, P2), and by year.
- The KEEL - RAW dollar split (leverage, timing), and timing split into FT / LO / interaction, each against its null.
- Nagel line: M's timing and its null beside KEEL's; the KEEL-on-momentum slope and correlation; P1 and P2.
- One sentence for the owner: is KEEL's WF gain on #424 leverage, fixed tilts, learned selection, or the leg's own
  momentum.

## Not done here

- No search over the 20-trade window, the slope or the clip. One value each, fixed above; others are not tried.
- No lockbox. No change to KEEL, ml_keel.py or any live leg.
- Code: a new script, tools/rocfrontier/r28_keel_decomp.py, which imports ml_keel / engine / backfill_keel's
  loaders unchanged. Its sha256 goes to MANAGER + TTM before it runs.
