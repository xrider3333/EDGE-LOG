# RESULTS - GAMMA r1 Stage A: arms A (GEXEXP), B (GEXREV) and C (GEXGATE) all FAIL (2026-10-10)

Pre-registration: `docs/PREREG_gamma_r1_2026-10-07.md` (arms A, B, shared null). Arm C: `docs/SCOPE_CALMDAY_2026-10-10.md`
section 4. Owner go: the same file, section 7 ("not buying anything so you choose"). Harness: `tools/gamma_r1_stageA.py --stageA`.
Full log: `tools/r37_results/gamma_r1_stageA.txt`.

**Verdict: all three arms FAIL their pre-registered bars.** Dealer gamma, as read from the SqueezeMetrics GEX photograph, is not a
day-type switch for these rules on ES, and it is not a loser-class filter for #463's ORB and NOISE legs. Per both texts, each arm is
dead: no other source, state cut or window. Per scope section 4, GEX is not tried again as a filter, on any cut.

## Order of work (run-before-main #77)
1. Arm C wired, parity run (no gamma), then the whole Stage A path run once with the real labels REPLACED by one shuffle (`--dry`)
   as a plumbing check.
2. Harness committed and pushed BEFORE the real-label run: `78bf9f12` on `origin/prereg/gamma-r1-armc` and
   `origin/claude/calmday-scope`. Hashes posted to MANAGER (inbox #845) before the run.
   - prereg LF sha256 `fd3091040344279c140da4444c14cd9aa075e1e6099ed93c8070b1235a457c90`
   - CALMDAY scope LF sha256 `190b3f8e87582008cca7b5ef06ea8dba15841830bbabcb18edbeded421da3729`
   - harness LF sha256 `ce075c6328e35967e836cd64dd3e5b91e98957edf47fbb367a0a5407e2f0d16d` (printed by the run)
3. Real-label run on the committed harness. Walk-forward 2016-07-01 .. 2025-06-29 only. The lockbox was not read: every master is
   loaded with date_to 2025-06-29, and GEX rows after 2025-06-29 are dropped on read.

## Parity (all exact, no gamma)
- **#463:** WF ROC@$30k 93.81, Sortino 3.816 (DD5 $36,095).
- **Arm C legs:** the four legs captured from `api.book_shadow.book463_valued_daily`'s own build, with keep_state for re-pricing.
  They sum to the book's daily column with max |diff| $0.00 over 2,626 WF days. ORB 1,442 and NOISE 2,797 WF trades, all
  intra-session.
- **Arm B:** BALANCE r1's ES transfer reproduced exactly (B1 592 / PF 0.992 / -$1,245; B2 378 / PF 0.995).
- **Counts re-derived:** GEXEXP 582 and GEXREV B1 608, as frozen. GEXREV selected-from-all equals the masked run.
- **Arm C gating:** the engine path (`augur_engine.book_sizing.resize`) equals the null's fast path to the cent on C1, C2 and C3.
- **Disclosure, roll guard:** the engine roll guard (landed 10-09) re-prices NOISE's no-adjust signals when it is called from a
  research script. That build has 4,510 trades in full history, against 4,503 for the adopted one, and its legs miss the book by up
  to $1,639 on a day. #463's 93.81 is the report-only build (the `api/` path). Arm C's parity and cells use that build, which is the
  book as adopted.

## Family null
- **Method:** within-calendar-year shuffles of the session GEX percentile on the ES WF calendar (2,318 sessions), 1,000 draws,
  seed 20261007.
- **Statistic:** the family max over seven cells.
  - Own ROC@$30k for A primary, A neighbour, B1 and B2.
  - ROC gain over #463 for C1, C2 and C3 (scope section 7: Arm C joins the family).
- **Family p95 = 17.93** (median 7.31). Without the C cells it would be 16.72; that is a report and changes no verdict.

## ARM A - GEXEXP (ES 30m breakout, short-gamma days): FAIL
| | value |
|---|---|
| WF trades | 582 (64.7 a year) |
| net / PF / $ per trade | $16,924 / 1.053 / $29 |
| own ROC@$30k | **1.34** (DD5 $16,564, driven by one episode) |
| July-June years positive | 6 of 9 |

Bars:
- A1: FAIL. Neither route (ROC < 15, and it loses $21,669 in #463's worst WF drawdown).
- A1b: FAIL.
- A2: FAIL (1.34 < 17.93).
- A3: FAIL (the neighbour nets -$259).
- A4: PASS.

Twins: all sessions 1,986 trades, ROC 2.57; long-gamma days -0.89. The primary does not beat the all-sessions twin. The halves
disagree: 2016-21 -$22,003 and 2022-25 +$38,927. R days -$47,895.

## ARM B - GEXREV (ES 5m BALANCE fade, long-gamma days): FAIL
| | value |
|---|---|
| WF trades | 608 (67.6 a year) |
| net / PF / $ per trade | $6,215 / 1.061 / $10 |
| own ROC@$30k | **1.88** (DD5 $5,004, driven by one episode) |
| July-June years positive | 4 of 9 |

Bars:
- A1: FAIL.
- A1b: FAIL.
- A2: FAIL (1.88 < 17.93).
- A3: FAIL (B2 nets -$5,542).
- A4: FAIL (-$4,820 at 2x cost).

Twins: all sessions ROC 1.30; short-gamma days -2.49. This matches the prior (median ROC 1).

## ARM C - GEXGATE (ORB #234 + NOISE #422 stand down on long-gamma days): FAIL
**The first number (binding): each leg's WF trades by entry day, on long-gamma days (p >= 2/3, 985 WF days) against the other days.**

| leg | days | WF net | trades | PF | $/trade |
|---|---|---|---|---|---|
| ORB | long-gamma | $70,924 | 562 | 1.249 | 126.2 |
| ORB | other | $230,264 | 880 | 1.373 | 261.7 |
| NOISE | long-gamma | $76,116 | 1,070 | 1.238 | 71.1 |
| NOISE | other | $371,528 | 1,727 | 1.646 | 215.1 |
| ORB + NOISE | long-gamma | **$147,040** | 1,632 | 1.243 | 90.1 |
| ORB + NOISE | other | $601,792 | 2,607 | 1.505 | 230.8 |

Top quartile (C3, 794 days): ORB $51,307 (436 trades, PF 1.255, $117.7/trade); NOISE $32,742 (876, PF 1.128, $37.4/trade).

| book | WF ROC@$30k | DD5 | Sortino | $ a year | gain |
|---|---|---|---|---|---|
| #463 | 93.81 | $36,095 | 3.816 | $140,235 | - |
| #463 + C1 (judged) | 82.87 | $37,028 | 3.607 | $123,886 | -10.94 |
| #463 + C2 (0.5x) | 88.34 | $34,784 | 3.781 | $132,061 | -5.47 |
| #463 + C3 (top quartile) | 87.55 | $35,783 | 3.743 | $130,890 | -6.25 |
| ORB only gated, C1 days (report) | 88.53 | $36,316 | 3.771 | - | -5.27 |
| NOISE only gated, C1 days (report) | 88.14 | $34,688 | 3.720 | - | -5.66 |

Bars:
- **C-A1 FAIL:** removed-day net is +$147,040, not below 0. It fails on dollars, so the cell fails whatever else it shows.
- **C-A2 FAIL:** ROC 82.87 < 93.81, and $123,886 a year < $140,235.
- **C-A3 FAIL:** the gain of -10.94 is below the null p95 of 17.93. The 71-look band (10z) is a report only: ORB +49%, NOISE +64%,
  and the gain is -11.7%.
- **C-A4 FAIL:**
  - removed-day net 2016-21 +$22,296;
  - 2022-25 +$124,744;
  - without 2020 +$115,406;
  - without the single worst removed day +$153,646.
- **C-A5 PASS:** 1,632 removed trades. Every July-June year has at least 71.
- **C-A6 FAIL:** C3 removed-day net is +$84,049.

**Reading.** Long-gamma days are WEAKER days for both breakout legs: $90 a trade against $231, and PF 1.24 against 1.51. That fits the
damping mechanism in direction. But they are still profitable, so standing down gives up money: a lower-quality trade is not a losing
one. The scope's prior (C-A1 fails for ORB and is close for NOISE) was half right. ORB failed as expected, and NOISE was not close.

**VIX confound (report).** Prior-close VIX terciles over WF book days (cuts 14.13 / 19.58):

| VIX tercile | long-gamma days | ORB+NOISE net, long-gamma | ORB+NOISE net, other days |
|---|---|---|---|
| low | 534 of 876 | $74,204 | $23,673 |
| mid | 303 of 875 | $79,031 | $141,211 |
| high | 148 of 875 | -$6,194 | $436,908 |

Most long-gamma days are low-VIX days. Inside the low-VIX tercile, long-gamma days earn MORE than the other days. The gamma gap in the
first table is largely the house's known volatility-harvester profile (section 10al): the legs earn on high-VIX days, which are
rarely long-gamma days. It is not a separate positioning effect.

## Not produced (prereg "reported" list)
- The event path, and per-trade overlap with ORB / NOISE held BARS. A day-level same-side overlap is printed instead: GEXEXP 64%,
  GEXREV 25%.
- The book add labels print "NQ" for the leg-size multiplier. For arms A and B that multiplier is in ES contracts.

## Follow-ups (for MANAGER; nothing done here)
- Ledger rows for GAMMA r1 arms A, B and C, all DEAD.
- A LOOKS-ledger entry for Arm C, which was a book look.
- RUNBOARD research rows (family MISC).
- The parked GEX idea goes back to closed.
- Nothing live or in the adopted book changed. No money was spent and no data was bought.
