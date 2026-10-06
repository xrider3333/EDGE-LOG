# PRE-REGISTRATION - SKEWREAL r1: does a fund's realized skewness this week predict next week's return across the ten gated funds? (TTM scope rank 6, opened by MANAGER #70)

Drafted 2026-10-06 by the TTM lane BEFORE any real-sort number exists. DRAFT for MANAGER review.
- Computed so far: the photograph check, COUNTS, and the power line from ONE label-shuffled (random) book. No real-skew
  sort has been computed.
- Harness: `tools/skewreal_r1_stageA.py`. Only `--counts` and `--power` have run. It reuses HALFHOUR r1's book,
  power-line and standalone-bar code, and TRANSFER r2's fund loader (`tools/rocfrontier/r8_transfer_etf.py`).

## Mechanism (theory and literature)
- Realized skewness, measured from intraday returns, predicts the NEXT week's return with a negative sign. Over a large
  stock cross-section, the lowest-skew decile beats the highest by about 19 bps a week (Amaya, Christoffersen, Jacobs &
  Vasquez 2015 JFE).
- The proposed reason is a taste for lottery-like payoffs: investors overpay for assets that recently showed right-tail
  jumps (Barberis & Huang 2008 AER; Boyer, Mitton & Vorkink 2010 RFS).
- Here the cross-section is the ten funds the house has photographed. These are diversified funds, not single stocks, so
  the effect is expected to be weaker. MANAGER calls it "thin by construction".

## What is different (one line), and the dead families it is not
**No house row sorts on a higher moment. Sector rotation, BAB and PAIRS (TV 2.69) sorted on returns, beta or price
ratios; this sorts on the third moment of the week's intraday returns.**

Dead and not re-tested:
- Sector rotation (memory: edgelog-rotation-sector-dead).
- TV NEW-TYPE r1: PAIRS / BAB / ONMOM (2.69).
- TREND as a seat (2.58).
- RESMOM as a standalone leg (2.76).
- TRANSFER r2: ORB / NOISE / TTM unchanged on funds (2.49).

## Rules (frozen; MANAGER #70's specification)
**Data.**
- The photographed NOISE fund pull (ledger 2.83): SPY, QQQ, TLT, XLF, XLU, XLV, XLP, XLI, XLY, XLK. SMH and VIXY are out.
- 5m RTH split-adjusted masters, loaded through TRANSFER r2's `load` with date_to 2025-06-29.
- Each master FILE is re-hashed against `C:\EdgeLog\_anatomy_cache\noise_funds_r1\pull.json` (filename and sha256)
  before use. The run aborts on any mismatch.
- **Price returns only:** the split-adjusted bars carry no dividends. Disclosed, not corrected. On TLT / XLU / XLP an
  ex-dividend drop lands on whichever side holds the fund that week.

**Signal**, at each week's last session close (weeks ending Friday):
- RSK_i = sqrt(N) x sum(r^3) / (sum(r^2))^1.5 over fund i's WITHIN-SESSION 5m log returns that week. A session's first
  bar counts as its own open-to-close; no overnight return enters.
- A fund is eligible when it has at least 80% of the week's largest N, a trailing 60-session daily vol and beta, and the
  next session's open.

**Book.**
- LONG the 3 lowest RSK, SHORT the 3 highest.
- Filled at the NEXT session's open. Fixed shares, held to the open one week later, which is the next rebalance.
- **Equal-risk** inside each side: dollars proportional to 1 / trailing 60-session daily vol, $50k a side.
- **Beta-neutral:** a SPY overlay of minus the portfolio's dollar beta to SPY (trailing 60-session daily betas).
- The dollar-neutral book (no overlay) prints beside it, as a report.

**Costs (the fund rule).** 5 bps a side on the dollars traded at each rebalance (|new - old| per fund, overlay included).
Stress at 10 and 20.

**Cells.**
- **1-week hold = PRIMARY.**
- **2-week hold = the neighbour:** two staggered half-capital cohorts, each rebalanced every other week.

**Counts (no returns).**
- 469 WF signal weeks. Eligible funds per week: min 8, median 10; no week has fewer than 6.
- 2,814 name-weeks per cell, about 313 a year. A "trade" for the count bar is one fund held for one cohort-week. The
  number of rebalances (469) is printed beside it.

**Family null (MANAGER #70).**
- Each week, the fund labels are shuffled before the sort: the same 3 long / 3 short among the eligible, the same
  sizing, overlay and costs. Count-matched by construction.
- 1,000 draws, seed 20261006, the SAME shuffles for both cells. Statistic: the family MAX of own ROC@$30k.

## POWER LINE (printed before any real sort; house rule MANAGER #37)
- From ONE label-shuffled book on the primary's schedule, added to #463's WF daily (parity 93.81 / 3.816 asserted).
- **VOL scale (x2.22):** SD of the book-add lead 7.0 points; minimum detectable 11.5; four in five 17.4.
- **$30k own drawdown (x0.79):** 2.7; 4.5; 6.8.
- Both implementations of the book give the same line: a loop version, then the vectorized version used for the null.
  This is a parity check on the book code.

## Stage A bars (walk-forward only, 2016-07-01 .. 2025-06-29; all must pass)
- **A1 standalone (house line #45, HALFHOUR's code):**
  - own ROC@$30k >= 15, OR the earner route;
  - PF > 1 on weekly P&L;
  - >= 100 trades and >= 50 a year (name-weeks);
  - >= 6 of 9 July-June years positive.
- **A1b:** the same route holds without 2020.
- **A2 null:** primary own ROC@$30k > the null's 95th percentile.
- **A3:** the 2-week neighbour is net positive.
- **A4:** net > 0 without the best week; net > 0 at 10 bps a side.
- No EARLY block: the fund bars start in 2016-01, as for DISC's stock legs.
- **Thin by construction (MANAGER #70):** a primary that clears every bar except a power-bound one is a RESEARCH ROW, not
  a pass, with no variants.

## Reported (no verdict)
- The R-day sum (printed first).
- The book add at the VOL scale and the $30k twin.
- The dollar-neutral book.
- The LONG side alone and the SHORT side alone.
- The cost curve at 0 / 5 / 10 / 20 bps a side.
- Regime halves 2016-21 / 2022-25.
- Per-year rows.
- Per-week rows: the count positive and the five best and worst weeks.
- The event path by session of the hold.
- How often each fund is long / short.
- **Overlap with NOISE's fund-habitat tests:** the same ten funds, but NOISE trades intraday noise-band breakouts
  (docs/SCOPE_NOISE_2026-10-05.md part A) and SKEWREAL holds a weekly cross-section. Different mechanism, no conflict
  (MANAGER #70).

## What follows
- **PASS:** a SKEWREAL_1_0 plugin (ten-fund, weekly; harness parity to the week first), then a WINDOW-PINNED
  Auto-Validate on a RANGED file: 900 trials over the lookback, K and the hold, lockbox veto-only. Then a RUNBOARD row.
- **FAIL:** dead; no other moment, universe or hold. Ledger row, TTM.md note, RUNBOARD research row (family MISC).
- Nothing live or in the adopted book changes without the owner.

## AMENDMENT 1 - MANAGER #71 (2026-10-06 12:36 MST, GO as drafted), written in before any real-sort return
- **The ex-dividend weeks of TLT / XLU / XLP, as a REPORT.**
  - No dividend data is held, so ex-dates come from a CALENDAR PROXY:
    - TLT: the first session of each month (iShares bond funds go ex on the first business day);
    - XLU / XLP: the first session after the third Friday of March / June / September / December (the Select Sector
      SPDRs' quarterly ex-dates).
  - A primary week is flagged when it held TLT, XLU or XLP (either side) across a proxy ex-session in (entry, exit]:
    108 of 468 weeks (counted from the schedule only).
  - The report prints the net and own ROC@$30k without those weeks, beside the full book. It decides nothing.
- Unchanged: a power-bound fail is a research row; the verdict is posted in one line with the power line beside it.
