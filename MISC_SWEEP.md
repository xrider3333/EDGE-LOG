# MISC_SWEEP.md — round 16: six classic mechanisms, first look (2026-08-24)

Owner directive: *"find others we may have not tried either in TV or otherplaces."*
This round tested mechanism FAMILIES, not TradingView scripts — the 2026-08-24
inventory of `augur_strategies/` (119 files) plus the round-13 TV sweep (12 dead),
web rounds 1/2/15 and the TTM study left exactly six classic families untouched.

Harness: `tools/r16_misc_triage.py` (committed). Cell-by-cell results:
`tools/r16_results/r16_triage.csv`. Studies-board rows: **487–517, fam MISC**
(web v73.246).

## Pre-registration (fixed before any result was computed)

- **Window:** 2010-06-07 → 2025-06-29 hard cutoff. The lockbox year was never loaded.
- **Data/costs:** NQ 5m RTH, 0.533 pts/RT (SESSBRK: NQ 1m ETH, 0.783; PAIRS adds the
  ES leg at 0.363 — both legs costed, $28.81/RT per pair).
- **Fills:** close-confirmed signals → next bar's open; resting stop-entries fill at
  the level with gap-through at the open; stop-first pessimism inside a bar; OOPS
  skips roll-seam days (GAPFADE-calibrated detector).
- **Gates (triage, all must pass):** PF ≥ 1.25, MAR ≥ 8, n ≥ 300.
- **The 30-cell grid below is the whole grid.** No cell added after results existed.

## Verdict: 0 of 30 cells pass. Family banked DEAD.

| Concept | Cells | Best cell | n | Net$ | PF | DD$ | MAR |
|---|---|---|---|---|---|---|---|
| OOPS gap-reversal | 4 | stop 0.5×ATR / hold-to-close | 786 | 49,543 | 1.139 | 23,733 | 2.09 |
| NR7/NR4/inside breakout | 6 | NR4 / 2R target | 989 | 106,952 | 1.225 | 33,256 | 3.22 |
| Floor pivots | 4 | breakout / stop 1.0×band | 3,040 | 208,952 | 1.156 | 34,639 | 6.03 |
| Last-hour drift (MOC) | 8 | 60m / momentum / 0.3-ATR filter | 2,238 | 117,153 | **1.246** | 23,121 | 5.07 |
| Session-range break (ETH) | 4 | london / half-range stop | 3,814 | 161,730 | 1.112 | 43,069 | 3.76 |
| ES/NQ spread | 4 | z2.5 / w1170 | 206 | 6,308 | 1.029 | 44,134 | 0.14 |
| B0 drift yardstick | 1 | always-long RTH | 3,868 | 97,767 | 1.040 | 90,626 | 1.08 |

Readings:

- **The house pattern held exactly:** every breakout-direction cell is positive,
  every fade is negative (pivot fade −$89k/−$110k, MOC fade −$60k to −$199k,
  asia-range fade-side included). NQ intraday pays breakout, kills fades — same
  verdict as REVERT/GAPFADE/VWAP_FADE/ORB_FADE.
- **Nearest miss:** MOC 60m momentum + 0.3-ATR filter, PF 1.246 vs the 1.25 bar,
  MAR 5.07 vs 8. A near miss is not a re-tune license; it also conceptually overlaps
  the DRIVE first-hour-momentum family already measured. Banked dead, not parked.
- **PAIRS answers a standing question:** ES/NQ log-ratio mean reversion at 1 contract
  a leg loses its whole edge to the doubled cost — best cell +$6.3k over 15 years.
- **PIVOT breakout ≈ a worse ORB:** the mechanism (break of a prior-day-derived level,
  with trend) earns PF 1.16–1.19 where the ORB crown's opening-range level earns 1.31.
  The opening range is simply the better level; nothing to fuse.
- **The lockbox was never opened for any row.**

Round tally now: rounds 13 (TV 0/12), 14/15 (web, empty), 16 (classics 0/30). The
next genuinely new edge still looks like it comes from new instruments/order-flow
data or an owner idea — not from public mechanism recipes.

---

# Round 17 — the hold-for-days playbook (2026-08-24, same session)

Harness: `tools/r17_misc_triage.py`. Results: `tools/r16_results/r17_triage.csv`.
Board rows **518–533, fam MISC** (web v73.247). Same window, same costs, same bar
(multi-day cells: 150-trade floor instead of 300, pre-registered in the harness).

Six more never-tested families, on daily bars built from the 5m day session. Multi-day
holds are honest: contract-roll days book no fake jump (seam detector + 0.25-pt roll
cost), and no overnight stop is pretended (the ENGU-Q $178k lesson).

## Verdict: 0 of 16 pass.

| Concept | Best cell | n | Net$ | PF | DD$ | MAR |
|---|---|---|---|---|---|---|
| Pullback to 20-day avg (long) | ema20/long | 168 | 150,654 | **1.879** | 32,856 | 4.59 |
| 7-day low buy (long) | 7d/long | 132 | 119,768 | 1.703 | 31,611 | 3.79 |
| Turtle breakout | 20/10 | 97 | 99,516 | 1.362 | 31,488 | 3.16 |
| 2-day dip buy (long) | thr10/long | 109 | 47,708 | 1.402 | 33,286 | 1.43 |
| Gap continuation | gap0.5% | 758 | −27,990 | 0.957 | 78,484 | neg |
| 10 o'clock fade | best of 4 | 1,067 | −110,254 | 0.775 | 118,204 | neg |

- **PB20 long = best cell of the whole hunt.** Independently rebuilt, reproduces to the
  dollar; post-2021 share only 26%. Still fails: MAR 4.59 vs 8, profit concentrated in
  2020/2021/2024, and one 2022 trade lost $23,361 (10-day hold, no stop). Banked dead.
- **MOC recheck (owner ask):** the round-16 near miss (PF 1.246) reproduces exactly in an
  independent clock-time rebuild — but 2010–2017 is eight flat years and 73% of profit is
  post-2021, which fails the year-concentration check. Dead twice over. Row 503 updated.
- **Gap pair complete:** fading gaps failed (round 13-era), riding them fails too.
- Buying weakness in an uptrend (dip/pullback/7-day-low) is the one shape that keeps
  showing a real edge fingerprint (PF 1.4–1.9, 70%+ winners) — it just doesn't earn
  enough per unit of its worst stretch to clear a futures bar built for MAR 8.

---

# Round 18 — the overnight session (2026-08-24, same session)

Harness: `tools/r18_misc_triage.py`. Results: `tools/r16_results/r18_triage.csv`.
Board rows **534–542, fam MISC** (web v73.249). Same window, same bar; overnight
cost 0.783 pts/RT; roll nights skipped.

## Verdict: **1 of 9 passes — the first pass of the entire hunt (55 dead cells before it).**

| Concept | Cell | n | Net$ | PF | DD$ | MAR | Gate |
|---|---|---|---|---|---|---|---|
| **Overnight drift** | **uptrend (close>200d SMA)** | **2,541** | **282,478** | **1.498** | **19,366** | **14.59** | **PASS** |
| Overnight drift | always | 3,054 | 249,189 | 1.303 | 59,772 | 4.17 | fail |
| Overnight drift | after-down / after-up / short | — | — | ≤1.42 | — | ≤5.0 | fail |
| VWAP trend pullback | long / both | 3,183+ | ≈0 | 1.01 | — | 0.2 | fail |
| Afternoon breakout | buf 0 / 0.25 ATR | 2,802+ | 83,801 | 1.09 | — | 2.4 | fail |

**The pass — ONDRIFT/uptrend:** buy the RTH close when close>200-day SMA, sell the next
RTH open. Kill-checks all survived: post-2021 share 28%; years 2017–2024 = 7/8 positive
(only 2022 negative, −$2.7k on 11 nights — the filter kept it out of the bear); SMA150/250
neighbors PF 1.46/1.47 (not knife-edge); bootstrap p ≈ 0; **corr to C2 −0.013, to ENGU-Q
ETH −0.006** — a true third factor (long-overnight), orthogonal to both live legs.
Avg win 29.7 pts vs avg loss 25.6 pts at 56.4% win rate; worst night −$5,151.

Honesty: the signal uses the close itself (live = MOC armed a minute early); the effect is
widely published (overnight risk premium), which is both validation and crowding risk;
2011–2016 contributed little (~$12k over 6 years) — the effect strengthened as overnight
liquidity grew.

Families closed this round: VWAP (fade AND trend now both dead), level-breaks (afternoon
breakout = a worse ORB), overnight short side (earns nothing).

**Next steps (in order): plugin file → frozen WF → formal Auto-Validate. Lockbox sealed
until owner sign-off.**

---

# Round 18 CORRECTION — the pass is RETRACTED (2026-08-24, same day)

Caught at the parity gate, before any validate run was queued. The r18 harness's
roll-night skip flagged nights by their OWN jump size (>=15 pts and >=2.5x trailing
median) — knowable only the next morning = accidental foresight. It removed 441 of
the worst nights. Honest engine rebuild (`ONDRIFT_1_0.py`, house calendar-anchored
detector): **n=2982 / $218,592 / PF 1.205 / DD $41,696 / MAR 5.24 — UNDER the bar.**

Pre-registered causal follow-up (one look): skip the night after a big-range day
(range > k x ATR20, knowable at the close), k in {1.0, 1.5, 2.0}: best cell
MAR 4.55. Nothing recovers.

- ONDRIFT_1_0.py stays in the library as the honest reference, marked DEAD.
- The 18b stop finding (every resting overnight stop level strictly worse, measured
  on the 1m Globex tape) stands on its own.
- Board rows 535/543 retoned + correction notes on both studies (web v73.251).
- **The MISC hunt stands at 0 passes across 58 cells.**
- Lesson for every future harness: NEVER filter a trade using a quantity that is
  only known after the trade's own holding window (here: the overnight jump the
  trade itself rides). The engine + house detector is the parity gate that caught it.

---

# Round 19 — owner: "both" (2026-08-24, same session)

## 19a — graveyard ideas as day-skip filters on the ORB crown: 0/6 adopt

Applied to the true #234 crown (parity $389,874 / PF 1.307 / MAR 13.38 exact), full
window, adopt bar pre-registered (MAR +15%, net -10% max). Filters (all knowable
before the open): prior-day up / prior-day down / NR7 / inside day / gap-against /
gap-with. NOT ONE improves the crown at all (best: skip-after-inside-day, MAR 13.21 <
13.38). The counter-prior-day overlay candidate from the August ORB hunt is formally
DEAD. Agrees with the TRADE CONTEXT scan (nothing survives FDR on ORB).

## 19b — the classics on new instruments via free daily data: 0/33

GLD / TLT / IWM / USO + QQQ control, Yahoo daily total-return bars 2006 -> 2025-06-29,
$100k/trade, 2 bps RT. Round-17 shapes FROZEN (RSI2, DBL7, DONCH, PB20). Best cells:
GLD DBL7/long **PF 2.33** MAR 4.9 (highest PF of the whole hunt), QQQ RSI2/long
**MAR 7.67 vs 8** (nearest miss). Pre-registered pooled read (same cell x 5 tickers,
one book): dip-buy PF 1.53 MAR 5.2, 7-day-low PF 1.58 MAR 6.1, pullback 1.16/2.6 —
diversification helps, still under. Turtle fails everywhere.

Standing: dip-buying-in-uptrend = real but under-powered in every market tested
(3 markets deep). Possible OWNER decision someday: a lower-bar Webull stocks sleeve
on the pooled dip book — a sizing decision, not a validation pass.

OPEN (owner action): free Alpaca key -> 1m ETF bars since 2016 -> test ORB/ENGU
mechanisms intraday on stocks. Harness: tools/r19_etf_classics.py (re-downloads its
own data). Board rows 1027-1051 (v73.313).

---

# Rounds 20-23 — the autonomous grind (2026-08-24/25, owner: "keep trying until you find something")

Harnesses: tools/r20..r23_misc_triage.py; CSVs beside them. Board rows 697-736
(v73.309). All pre-registered, lockbox never loaded, house roll detector.

## Verdict: 0 of 40 more cells (hunt total: 0/144). The map got much sharper:

- **The 9:30 open is special, not the ORB mechanism** (r20): the crown mechanism is
  decisively NEGATIVE at the Asia and London opens (PF 0.82-0.86).
- **No slice of the overnight holds an edge** (r20): all 10 segment cells ~PF 1.0 -
  independently confirms the r18 ONDRIFT retraction.
- **Every fade is now dead** (r21 turtle soup completes it): 2010-2025 NQ pays
  breakout-followers and punishes top-callers at every timescale tested.
- **ES-ETH frozen transfer of ENGU-Q = PF 1.125** (r21) - under the 1.15 transfer
  bar; a full Auto-Validate with ES-fit params is QUEUED (job ktTjVhb2PRo9Ckg3rBFv).
- **The crown risk engine is not portable** (r22+r23): transplanted onto dips it
  deletes their multi-day edge; rebuilt into the turtle it is WORSE than no-stop.
  It works only where the edge realizes within its own session.
- **ENGU-Q needs 1-minute granularity** (r22): the 5m port drops PF 1.33 -> 1.11.
- **Capitulation-buying = the dip fingerprint again** (r20): PF 1.81, MAR 4.0.

---

# Round 26 — oversample the IS, judge by WF: THE NASDAQ BOOK (2026-08-25)

Owner: "continue searching for better parameters or strategies that beat anything
we've found thus far. oversample the crap out of the IS section if you have to until
you find something that excels at the WF section. idk what time frame or instrument."

Method = walk-forward optimization (tools/wfo_daily_dips.py, wfo_daily_dips_books.py,
wfo_nasdaq_fine.py, wfo_nasdaq_prewindow.py, wfo_intraday_mr.py, qqq_prewindow_check.py):
per fold, search the WHOLE grid on the anchored IS, trade the IS winner on the OOS
slice, score ONLY the concatenated OOS. Board rows 1141-1158 (v73.437).

## Screen 1 — 9 instruments x 4 dip mechanisms, 8 folds (OOS only)
QQQ is the standout on every mechanism (DBL MAR 9.19 / CAP 7.88 / RSI PF 2.41);
NQ/ES carry the edge in PF terms (NQ RSI PF 1.84 WFE 1.64; ES CAP PF 1.62 WFE 1.68);
GLD/TLT/IWM/EEM/USO are weak-to-dead out of sample. **Broad 36-series book with
per-fold re-optimization = MAR 3.05 (FAIL) — the fixed-parameter r25 book (10.31)
beats it. Re-tuning chases noise on weak legs.**

## Screen 2 — hourly intraday mean reversion (NQ/ES 30m+60m, RSI + Bollinger): DEAD
Pooled OOS PF 1.00 / MAR 0.03. Best cell ES-60m BB PF 1.67 / MAR 3.0.

## The result — Nasdaq fine grid (1,254 configs, 12 folds, OOS only)
| leg / book | n | net | PF | DD | MAR | folds+ |
|---|---|---|---|---|---|---|
| QQQ DBL (7-day-low buy) | 134 | $113,336 | 2.54 | $9,304 | **12.18** | **12/12** |
| QQQ RSI / PB / CAP | 158 / 225 / 141 | 73k / 133k / 81k | 2.10 / 1.78 / 1.75 | — | 6.6 / 4.1 / 4.9 | 7 / 12 / 8 of 12 |
| NQ DBL / RSI / PB / CAP (const $100k) | 123 / 174 / 171 / 124 | 87k / 85k / 73k / 72k | 2.37 / 2.18 / 1.52 / 1.89 | — | 7.9 / 5.6 / 3.5 / 6.5 | 8-9 of 12 |
| BOOK QQQ 4 mech | 658 | $403,633 | 1.98 | $47,204 | **8.55** | 11/14 yrs |
| BOOK NQ 4 mech (const notional) | 592 | $318,905 | 1.92 | $34,736 | **9.18** | 11/13 yrs |
| BOOK NQ 4 mech, whole MNQ contracts | 544 | $263,886 | 1.83 | $32,248 | **8.18** | — |
| **BOOK NASDAQ 8 legs (QQQ + NQ)** | **1250** | **$706,799** | **1.95** | **$69,877** | **10.11** | **12/14 yrs** |

Kill-checks on the 8-leg book: post-2021 share 18%; bootstrap p = 0.0000; halves
2012-17 MAR 7.10 / 2018-25 MAR 4.26; **corr to champion book 0.041**;
**STACK on champion (same window): MAR 8.31 -> 11.20 = +35% (bar +15%), net +85%
=> ADOPT BAR CLEARED** (the first candidate to clear it).

## The regime caveat (a window the hunt never touched: 1999-03 -> 2010-06)
QQQ fixed params: PF 1.26 / MAR 1.32 / 5-of-11 yrs. QQQ walk-forward: PF 1.35 /
MAR 2.28. SPY WFO control: MAR 5.78. => a bull-regime buy-the-dip edge behind a
trend filter; profitable in the bear decade, nowhere near the bar there.

## Config drift of the star leg (QQQ DBL, chosen per fold)
2012-17: n=4-7 / sma 300 -> 2017-21: n=15 / sma 150 -> 2021-24: n=6 / sma 250 ->
2024-25: n=15 / sma 300. The process adapts; no single setting is "the" setting.

## Next gates
1. Strategy plugin files for the 4 mechanisms (parametrized, ranged - NOT pinned).
2. QQQ daily master in the library; NQ daily from the 5m RTH master.
3. Formal BOOK validate with the sealed lockbox (post-2025-06-29).
4. NQ half can paper-trade in MNQ now; QQQ half needs the Webull stocks account.
