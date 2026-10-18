# PREREG: ORB RELAY r2 (T34) - the live Webull ORB leg on NQ's signals, at the Webull leg's cost, +2 slippage ticks, late fills and fold by fold (ORB lane, 2026-10-18)

**Why.** MANAGER #106 (owner 10-18, "more testing on things that are promising"). Board row T34.
- ORB RELAY r1 (`ORB_RELAY_R1.md`): the QQQ ORB leg on NQ #314's signals, filled on QQQ 1m prints, read ROC @ $30k 34.36 vs the live
  leg's own QQQ bars 23.47 (1,161 trades). Verdict LEADS, NOT DISTINGUISHABLE (90% -10.9 .. +38.2).
- DISC confirmed it blind; COSTSTRESS r1 put the Webull leg's break-even-to-15 cost at $0.097 a share (c15), where C read 22.3 vs A 15.0.
  The live shortfall so far is $0.19 a share (n = 5 fills, mostly EOD timing).
- This round asks whether the lead survives: the Webull-leg cost; +2 slippage ticks a side; fills one bar late; and in how many of 8
  slices of the WF years it holds.

**Known before the run.** r1 read every row one episode: C's worst drawdown = 1.37 x DD5, A's 1.52 x. r2's C is r1's C (same engine,
params, NQ master and fills), so C is expected to fail the bar's one-episode clause at every cost, and plain "HOLDS" is not reachable
unless the data changed. A pre-set companion branch (below) reads the lead's stability when one-episode is the only failure.
MANAGER's bar is MANAGER's; the clause is kept as set.

## Fills (WF only: 2016-07-01 .. 2025-06-27, trades exiting inside it; the lockbox is not read)

10 QQQ shares; daily $ by exit day on every QQQ RTH WF session (zero days included).
- **A AS LIVE:** ORB_R6 (`api.cloud_signal.CROWN_LEGS["ORB_R6"]`, `ORB_3_6_R6.py`, params asserted by the harness) on QQQ's own 5m bars
  (`master_ac263357.csv`, alpaca_split_rth), the engine's fills (cost 0 in the engine, then 10 x (gross - cost)).
- **C RELAY, next-print fill:** NQ #314 (same file and params) on `ADJ_NQ_5m_RTH.csv`.
  - Entry at the OPEN of the first QQQ 1m minute after the NQ signal bar closes (minute te+5; bar-start stamps).
  - Exit at the QQQ close of the first NQ 1m minute (`ADJ_NQ_1m_RTH.csv`) that reaches the NQ exit level; EOD exits at the QQQ close of the
    session's last QQQ minute (`master_dd092f50.csv`).
- **CL ONE BAR LATE:** entry at the open of QQQ minute te+10; a stop / target exit at the QQQ close 5 minutes after the exit minute, capped at
  the session's last minute; EOD unchanged. CL is blind for 5 minutes: a trade whose NQ exit fires before the late entry is still entered
  and exited at hm+5 (counted and printed). CL assumes a real-time NQ feed.
- **CY YAHOO DELAY (report-only):** the box's only NQ feed is Yahoo (about 10 min CME delay + bars held 15 min), so bar te is seen at about
  te+20. Entry at the open of QQQ minute te+20; stop / target exit at the QQQ close of minute hm+15 (capped at the last minute); EOD
  unchanged. Relay exits are NQ-triggered market orders, not resting QQQ stops (the live leg rests its levels).
- **Dropped and counted:** trades without the needed QQQ minute, by reason (entry vs exit); phantom last-bar entries (enter and go flat on a
  session's last bar, pts 0: the executor cannot fill a 16:00 signal) are skipped on BOTH A and the relay and counted; stop / target exits
  with no NQ minute at the level (fall back to the bar's last minute) are counted. The harness stops if any row falls off the QQQ calendar.

## Costs ($ a share a round trip)

- $0.02 house (COSTSTRESS r1 / RELAY r1); $0.06 = house + 2 ticks a side ($0.02 + 2 x 2 x $0.01; the house "+2 ticks a side" convention,
  PREREG_balance_r1_2026-10-06 / SCOPE_DISC_2026-10-06);
- **$0.097 = the Webull leg (COSTSTRESS r1 c15)**; **$0.137 = Webull + 2 ticks a side (the worst case)**;
- $0.19 = the live shortfall (n = 5), report-only.

Arms: A, C at $0.02 (the r1 repro rows); A2, C2 at $0.06; **AW, CW, CLW at $0.097**; **AW2, CW2, CLW2**, CYW2 at $0.137; A4, C4, CL4 at $0.19.

**Repro gate (before any pair is read):** A at $0.02 with phantoms kept (as r1) must give 1,161 trades and ROC 23.47 +/- 0.05, and C at
$0.02 ROC 34.36 +/- 0.10; otherwise the harness prints REPRO MISMATCH and stops. The harness also pins the four master filenames, prints their
fingerprints, and the LF sha256 of `ORB_3_6.py` and `ORB_3_6_R6.py`.

## Numbers

- **The four numbers per arm:** `augur_engine.drawdowns.four_numbers(daily, years=WF length)` on the arm's daily $ scaled to a $30k worst
  drawdown, so DD5 and DD % from peak read at $30k on a $100k account. Also worst DD / DD5, net a year, trades a year, gross a share, cost
  a share and gross / cost.
- **Pairs.** Verdict pairs: CW vs AW, CLW2 vs AW2. Report-only pairs: C vs A, C2 vs A2, CLW vs AW, CW2 vs AW2, CYW2 vs AW2, C4 vs A4, CL4 vs A4.
  For each pair:
  - **Fold by fold:** 8 equal consecutive slices of the 2,260 QQQ WF sessions (not the validate's anchored folds). The lead HOLDS in a slice
    when the relay arm's net beats the live arm's at 10 shares (ties do not hold). Count of 8 and the one-sided sign-test p; 6 / 8 is a
    stability floor (sign p 0.145), 7 / 8 is p 0.035. Also printed: the count on the $30k-scaled dailies (report-only).
  - **ROC @ $30k lead** with a 90% paired block bootstrap (20 sessions, 2,000 draws, seed 20261018, common draws across pairs): report-only.
  - **Ledoit-Wolf paired Sharpe difference** (`augur_engine/sharpe_diff.py`, LF sha256
    704559490f7b3dd1c393c9b8ccdd5333321ddd4ff5269ea55246570a5e3af894, from LW44 commit b736e168 on `prereg/orb-lw44-r1`, loaded by path;
    block 20, 4,999 draws, seed 7), its 95% interval, two-sided p and MDE80: report-only. MANAGER's bar does not ask for it, and shelf 44 r1
    found Sharpe cannot see DD-shape lifts (the ENGU-Q NQ-signal QQQ relay read NOT SHOWN; #314's seat SR p 0.39).
- **Power line (set now):** r1's 90% ROC-lead interval was -10.9 .. +38.2 on the same 9 years, so this round cannot prove the lead; it reads
  whether the lead is stable across slices and survives costs and delay. The fold count is the stability read, not a significance test.

## Bar per arm (MANAGER #106, set now)

PASSES only if all four clauses hold (each failing clause is named):
- gross a share >= cost a share (on one trade set this equals net >= 0; it carries information at the Webull cost, where it is read);
- net ROC @ $30k > 0;
- not one episode (worst drawdown <= 1.3 x DD5);
- MDL path: own ROC @ $30k >= 15 (the MDL map band |rho_dd| < 0.15; the earner route is not used).

## Verdict (set now; decided on unrounded values, in this order)

1. **"NO CASE FOR THE RELAY"** if CW's ROC @ $30k is not above AW's (decided first).
2. **"RELAY HOLDS UNDER STRESS"** if all of:
   - CW passes the bar (all four clauses);
   - CW vs AW holds in >= 6 of 8 slices;
   - CLW2's ROC @ $30k is above AW2's;
   - CLW2 passes the bar;
   - CLW2 vs AW2 holds in >= 6 of 8 slices.
3. **"RELAY LEAD STABLE, ONE-EPISODE"** if the only failing conditions are one-episode clauses (worst / DD5 printed).
4. **"RELAY LEADS, NOT ROBUST (fails: ...)"** otherwise, naming each failing condition.

Report-only: no rule or live change. The relay is a design call for PAPER-WB and the owner (it needs a live NQ signal on the box, and the
box's Yahoo feed is the CY row). Harness `tools/orb_relay_r2.py` checks this note's LF sha256 and `augur_engine/sharpe_diff.py`'s at start.
