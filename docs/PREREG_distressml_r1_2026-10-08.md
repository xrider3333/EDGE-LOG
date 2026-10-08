# PRE-REGISTRATION (DRAFT for MANAGER) - DISTRESS-ML r1: a learned distress model on point-in-time XBRL + prices (2026-10-08)

Custom ML, queue item 2 of docs/SCOPE_CUSTOM-ML_2026-10-07.md (standing order addendum 2; MANAGER #71 / #76 b).
Walk-forward ONLY; nothing filed or traded after 2025-06-29 is loaded. Computed before this draft: nothing on returns.
The only numbers seen are FUND-ML r1's coverage-only dry load (names x months with each fundamental; no returns).

## Why this, and what is different
- XSML r1 cell C (ledger 2.97, dead) was a PRICE-only crash classifier: gross 0.6, DO +0.235 just above its null's
  +0.209, rho_dd -0.04. This cell adds the balance sheet and income statement (leverage, cash, losses, coverage) - the
  inputs the distress literature says carry the failure signal - and a horizon long enough for them to matter.
- FUND-ML r1 (queue item 1) ranks EXPECTED RETURN on value / quality inputs; this ranks the probability of a crash and
  trades only the tails of that probability. Shares the extract, the point-in-time rules and the harness.
- Dead-list cross-check: no dead family shorts distress (ledger section 2). FRONTIER owns plain quality / BAB sorts;
  the twin here is the published CHS logit (fixed coefficients, no learning), reported for FRONTIER if it clears.

## Map placement (docs/MDL_MAP_R1.md)
The EARNER route is the point: junk falls hardest in sell-offs, so a short-junk / long-safe book should earn while #463
falls (its drawdown weeks: 2020-02..04, 2022, 2025). A leg that earns in those weeks helps at almost any size; as a
standalone leg it would need net WF ROC >= 15, which nobody expects (0-8). Pre-registered from the mechanism, never
fitted to those episodes.

## Data (all held)
- Prices, universe, dividends, split quarantine, delisting: the XSML r1 harness unchanged (Alpaca SIP dailies, top 500
  by 20-day median dollar volume, close >= $5, >= 260 sessions; corporate-actions file sha256 e5bc8487...).
- Fundamentals: FUND-ML r1's extract (fundamentals_asfiled, 35 us-gaap concepts, first filing per fact, facts filed on
  or after 2025-06-30 cut) and share counts, with FUND-ML's point-in-time rules INCLUDING its addendum 1: a fact is
  used from the session after its FIRST filing; flows = latest annual fact within 15 months; stocks = latest instant
  fact within 9 months; share count first filed before t with period end within 15 months, else market value missing.
- Symbol -> CIK: the reviewed map; unmapped names are out; the mapped share by WF year and the survivor-tilt line are
  printed exactly as in FUND-ML addendum 1 (3).

## The cell
- **Label:** 1 if the name's 63-session total return (fill open t+1 to exit open, dividends added) lands in the bottom
  5% of the eligible cross-section, else 0. A name with no row at the exit (delisted inside the window) is NOT
  trainable: the cause (failure vs takeover) is unknowable without the submissions pull, and a takeover premium
  labelled as a failure would teach the model the wrong thing. Disclosed; the P&L still carries the name to its last
  price (and the worst-case rows below).
- **Inputs (cross-sectional ranks in [-0.5, 0.5], NaN kept; 25):**
  - CHS (2008) eight: NIMTA (annual net income / (market value + total liabilities)), TLMTA, EXRETAVG (12 monthly log
    excess returns over the equal-weight universe, weights 2^(-(j-1)/3) normalised), SIGMA (63-session daily return
    std, annualised), RSIZE (log market value / the universe's total), CASHMTA, MB (market value / adjusted book
    BE + 0.1 (MV - BE); BE <= 0 set to $1, as CHS), PRICE (log of min(close, 15)).
  - Altman (1968) five: working capital / assets, retained earnings / assets, operating income / assets, market value
    / total liabilities, revenue / assets.
  - Ohlson (1980) and coverage, six: log assets, current liabilities / current assets, loss flag (net income < 0 this
    year AND last), net income change ((NI - NI_1y) / (|NI| + |NI_1y|)), operating cash flow / total liabilities,
    operating income / interest expense.
  - XSML cell C's price set, six: idiosyncratic vol 63 vs the equal-weight universe, MAX 21, distance to the 252-day
    high, momentum 252..21, 252-day beta, log dollar volume.
- **Eligible names:** all eight CHS inputs finite (so the cell and the twin trade the same names).
- **Model (registered, no search):** sklearn HistGradientBoostingClassifier with XSML / FUND-ML's settings (max_iter
  300, learning_rate 0.05, max_leaf_nodes 31, min_samples_leaf 200, l2 1.0, no early stopping, random_state
  20261008); refit every 1 January on decisions whose 63-session window ended before it (purged). First refit
  2018-01-01 - fit on 2017's decisions only (the universe starts in 2017); the row count of each refit is printed and
  2018 is expected to be the weakest year.
- **Rule:** decisions at each month's last close; SHORT the top 50 by predicted probability, LONG the bottom 50;
  BETA-NEUTRAL (XSML cell C's scaling); hold to the next month's fill. The label looks 63 sessions ahead and the book
  holds about 21 - a distress score moves slowly, so monthly re-ranking keeps the book on the current tails. $1M a
  side; 5 bps a side + 1%/yr borrow; stress 10 bps.
- **Plain twin (no learning):** the CHS failure score with its published coefficients (Table IV, column 3, as
  restated in the Management Science online appendix of "Distressed Stocks in Distressed Times"): -20.264 NIMTA
  + 1.416 TLMTA - 7.129 EXRETAVG + 1.411 SIGMA - 0.045 RSIZE - 2.132 CASHMTA + 0.075 MB - 0.058 PRICE (the intercept
  does not change a ranking), computed on the RAW inputs, same rule. CHS use quarterly NIMTA averaged over four
  quarters; this house holds annual flows, so NIMTA is the latest annual figure - the same input for cell and twin.
- **Null:** 1,000 random beta-neutral books on the same eligible names, same rule, GROSS (the cell is judged NET -
  deliberately conservative; the net null's 95th printed for the record). The power line is printed and committed
  first: ROC 50th / 95th, the earner-route null (DO 95th, rho_dd 5th), the MDE in dollars a year at a $30k drawdown,
  eligible names by month, the mapped share by WF year.

## Stage A bars (house line #45; XSML r1 / FUND-ML set)
1. Net WF ROC @ $30k >= 15, OR the earner route: DO above its null's 95th AND rho_dd <= -0.15 AND net WF P&L > 0;
   either way net > 0 at the stress cost.
2. NET WF ROC above the null's 95th percentile - OR, on the earner route, DO above the null's 95th (bar 1 already).
3. Beats the CHS twin on net WF ROC AND Sortino (on the earner route: on DO as well).
4. RISK r1 + concentration: net > 0 without Feb-Apr 2020; >= 5 of 7 July-June WF years; both halves (2018-21,
   2022-25); without the best 1% of name-periods; without the best 5 months.
5. >= 100 name-positions and >= 26 decisions; PF of name-periods (net of a round trip) >= 1.0.
6. Neighbours (25 and 100 names a side) both net WF ROC > 0 (earner route: both DO > the null's 50th).
Reported regardless (standing order addendum 2 (2), #77): DD5 beside every ROC with the one-episode flag; event-time
path; cost curve 0 / 5 / 10 / 20 bps; per-year rows and the cell's P&L inside each of #463's five deepest WF drawdowns;
long vs short legs; beta to the equal-weight universe; delisted LONGS to zero and delisted SHORTS to zero (the second
flatters the cell - report only); the 30 largest single-name contributors; the twin's full row; the label's base rate
and the model's out-of-sample AUC by year (a report: an AUC near 0.5 with a profitable book means the book is luck).

## What a result means
- A pass -> hand audit of the 30 names, then MANAGER: RUNBOARD research row the same day, the leg's own sealed-year
  veto on the one stock day, a forward paper shadow; the book-add report incremental over the RESMOM line L (a
  report, never a gate); the basket cannot run as an EDGELOG engine job.
- A fail -> dead, ledger + memory, no variants. If the CHS twin clears the earner route and the model does not, the
  twin's row goes to FRONTIER.
- Nothing live or in the adopted book changes.

## Priors to disclose
- CHS (2008) find distressed stocks UNDERPERFORM (the distress anomaly), concentrated in small, illiquid, low-priced
  names - exactly the names a top-500, >= $5 universe excludes. The liquid tail is mild junk, not failures; the
  expected edge is small.
- Junk rallied hard from April 2020 to early 2021 (the short side's worst stretch); XSML cell C's short-crashers book
  did not earn in #463's drawdown weeks (rho_dd -0.04). Asness, Frazzini & Pedersen (2019, quality minus junk) is the
  case for large caps.
- 09-27 audit, XSML r1: learned models here have matched or lost to plain rules every time so far.
- Expected: 0-8 net standalone; the earner route is the point, and it is more likely dead than alive.
