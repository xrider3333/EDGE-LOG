# ORB RELAY r2 (T34): result (2026-10-18)

**Setup:**
- Prereg: `docs/PREREG_orb_relay_r2_2026-10-18.md` (LF sha256 072b1df6..., branch prereg/orb-relay-r2 = 93a896ac, pushed and posted to
  MANAGER before the run). Fixed after an adversarial review, before the freeze.
- Harness: `tools/orb_relay_r2.py` (LF sha256 ad8c16ef...). It checked the note, `augur_engine/sharpe_diff.py` (704559490f7b...), the leg,
  the four masters, then reproduced RELAY r1: A 1,161 trades ROC 23.468 (r1 23.47); C ROC 34.359 (r1 34.36). It read no pair before that.
- Output: `C:\EdgeLog\_anatomy_cache\orb_relay_r2\t34_r2_result.json` + `t34_r2_stdout.txt`.
- Scope: WF 2016-07-01 .. 2025-06-27, lockbox unread, 10 QQQ shares, report-only.

**The question:** does the Webull ORB leg on NQ's signals (RELAY r1: 34.4 vs 23.5) survive the Webull cost, +2 slippage ticks a side,
fills one bar late, and 8 slices of the WF years?

| Arm | Cost / sh | ROC @ $30k | DD5 (at $30k) | DD % (at $30k) | Sortino | Worst / DD5 | Net a year | Gross / cost |
|---|---|---|---|---|---|---|---|---|
| A as live | $0.02 | 23.49 | $19,735 | 20.1 | 1.86 | 1.52 | $345 | 14.4 x |
| C relay, next print | $0.02 | 34.36 | $21,918 | 17.9 | 2.22 | 1.37 | $411 | 15.5 x |
| A2 | $0.06 | 19.47 | $20,082 | 22.0 | 1.57 | 1.49 | $293 | 4.8 x |
| C2 | $0.06 | 27.72 | $21,531 | 20.7 | 1.90 | 1.39 | $355 | 5.2 x |
| **AW** (Webull leg) | $0.097 | 15.10 | $19,641 | 24.1 | 1.30 | 1.53 | $246 | 3.0 x |
| **CW** | $0.097 | 22.30 | $21,468 | 23.7 | 1.60 | 1.40 | $302 | 3.2 x |
| CLW one bar late | $0.097 | 20.15 | $21,833 | 23.3 | 1.43 | 1.37 | $276 | 3.0 x |
| **AW2** (Webull + 2 ticks a side) | $0.137 | 10.26 | $18,276 | 26.5 | 1.02 | 1.64 | $195 | 2.1 x |
| CW2 | $0.137 | 17.09 | $21,910 | 27.5 | 1.28 | 1.37 | $246 | 2.3 x |
| **CLW2** (worst case) | $0.137 | 15.11 | $22,602 | 27.0 | 1.13 | 1.33 | $219 | 2.1 x |
| CYW2 Yahoo delay (report) | $0.137 | 16.63 | $26,278 | 23.1 | 1.02 | 1.14 | $196 | 2.0 x |
| A4 (live shortfall) | $0.19 | 5.49 | $17,287 | 29.1 | 0.65 | 1.74 | $127 | 1.5 x |
| C4 | $0.19 | 8.06 | $17,097 | 30.0 | 0.88 | 1.76 | $171 | 1.6 x |
| CL4 | $0.19 | 7.08 | $17,406 | 30.0 | 0.73 | 1.72 | $144 | 1.5 x |

- **Trades a year:** A 128 (1,152 WF trades), relay 141 (1,271).
- **Skipped or dropped:**
  - phantom last-bar entries skipped: A 9, NQ 8;
  - relay dropped for a missing QQQ entry minute: C 2, CL 3, CY 5;
  - no stop or target exit lacked its NQ minute;
  - 943 relay trades exited at EOD.
- **The bar:** every arm fails "not one episode" except CYW2. AW2, A4, C4 and CL4 also miss ROC >= 15.

**Relay vs live, by slice** (net at 10 shares, relay minus live, ~1.1 years each):

| Pair | 16-17 | 17-18 | 18-19 | 19-20 | 21-22 | 22-23 | 23-24 | 24-25 | Holds | ROC lead (90%, report) | Sharpe diff (p) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **CW vs AW** | -68 | -42 | +7 | +232 | -65 | +301 | +190 | -47 | 4 / 8 | +7.2 (-9.9 .. +24.9) | +0.15 (0.40) |
| **CLW2 vs AW2** | -96 | -13 | -6 | +244 | -75 | +159 | +49 | -40 | 3 / 8 | +4.8 (-10.4 .. +16.2) | +0.05 (0.79) |
| C vs A | -61 | -26 | +16 | +244 | -49 | +311 | +201 | -38 | 4 / 8 | +10.9 (-12.8 .. +35.7) | +0.17 (0.34) |
| CYW2 vs AW2 | -61 | -32 | -43 | +369 | -187 | +300 | -95 | -239 | 2 / 8 | +6.4 (-12.4 .. +14.3) | -0.00 (0.99) |

- Counted on the $30k-scaled dailies instead, CW holds 6 / 8 and CLW2 6 / 8 (report-only).
- The relay's smaller worst drawdown scales it up more, which turns small slice losses into wins.

**Verdict (pre-set): RELAY LEADS, NOT ROBUST.** It fails four conditions:
- CW is one episode;
- CW vs AW holds in only 4 of 8 slices (needs 6);
- CLW2 is one episode;
- CLW2 vs AW2 holds in only 3 of 8.

CW's ROC is above AW's, and CLW2's above AW2's. Both pass gross >= cost and ROC >= 15.

**What it means:**
- **The lead survives costs and delay on the totals.** It shrinks from +10.9 at $0.02 to +7.2 at the Webull cost, and to +4.8 one bar late
  at Webull + 2 ticks. Even at the worst case the relay keeps the leg on the MDL path (15.1), while the live leg drops off it (10.3).
- **But it is not steady. It is three good stretches:** Nov 2019 - Dec 2020 and Feb 2022 - May 2024. In the other five slices the relay
  trails by $10-100 a slice at 10 shares.
  - Those are the trend years. NQ's signal catches the big NQ trend days that QQQ's own bars miss.
  - This matches ledger 2.96: the gain is on the NQ-only signals.
- **One episode was known before the run** (r1: C 1.37 x DD5). The fold floor, not the one-episode clause, is what sinks the verdict.
  So the companion "LEAD STABLE, ONE-EPISODE" branch did not apply.
- **The box's real feed (CYW2, Yahoo ~20 min late)** keeps the ROC lead on paper (+6.4), but holds in only 2 of 8 slices with a zero
  Sharpe difference. A Yahoo-fed relay is not the r1 relay.
- **At the live shortfall ($0.19 a share)** neither leg is worth running (ROC 5-8).
  The cost of the Webull leg matters more than where its signal comes from.

Nothing changes. The relay stays a design call for PAPER-WB and the owner. It now carries this caveat: the lead is real on totals but
concentrated in trend years, and it needs a real-time NQ feed (not Yahoo).
