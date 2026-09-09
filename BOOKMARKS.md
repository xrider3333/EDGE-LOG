# BOOKMARKS — the promising things, in one place

Owner ask 2026-08-25: "bookmark what you've found promising so far." This file is the
durable list. Every entry names the exact reproduction path. Numbers are pre-lockbox
unless a run number says otherwise. Bar for "promising" = a real edge fingerprint,
whether or not it clears the full house bar (PF >= 1.25, MAR >= 8, n >= 300).

## TIER 1 — passed a pre-registered bar

| # | What | Numbers | Where / reproduce | Caveat |
|---|---|---|---|---|
| B1 | **Weak-edge book** — 4 dip-buy mechanisms (RSI2 long/both, 7-day low, pullback-to-20d, NQ capitulation) x {NQ, GLD, TLT, IWM, QQQ}, ALL 20 legs, causal equal-risk, scored as ONE strategy | n=2925 · $1,220,386 · PF 1.52 · DD $118,321 · **MAR 10.31** · **WF 8/8** · bootstrap p~0 · corr 0.055 to champion book | `tools/r25_weak_edge_book.py`, kill-checks `tools/r25b_book_killchecks.py`; STUDIES rows 1027-1051 | STOCKS-account book (ETF legs alone MAR 10.33, NQ legs alone 4.19); recent half MAR 7.20; stack on champion +12% vs +15% bar; no stops on multi-day holds |
| B2 | ENGU-Q ETH — **family CROWN since 2026-09-05** (was #226; owner: "crown #309 and swap the paper leg to it") | run **#309** PASS 6/6; selection n=1,505 · PF 1.661 · $505,756 · DD $44,403 · EV R 0.439 · R/YR 43.9; LB n=99 · PF 1.620 · $85,511 · EV R 0.407 · R/YR 40.4 | `augur_strategies/ENGUQ_1M_ETH_ER_1_0.py` (er_th=0.0, gate off); PAPER leg `ENGUQ_309` live since 2026-09-05 (`api/paper.py`) | beats #226 on selection/lockbox EV R and tail dependence (top-10 share 53% vs 80%); LOSES lockbox R/YR (40.4 vs 68.5, trades ~half as often); #226 kept as the documented control (TIER 3 lesson below, ENGUQ.md CROWN CHANGE 2026-09-05) |
| B3 | Legal ORB crown | **run #314** `ORB_3_6_R6.py` (crowned 2026-09-05, replaces #234): stop 2.5x / target 5.0R / breakeven 0.5R / filters 0.75-0.80. PASS 7/7, WF 7/8, LB $92,102 / PF 1.561, **ES 1.019 PASS**. Leads annualised MAR in every window (5y 2.79 vs 2.37, DD $22,925 vs $28,502) | Past Runs #314 · paper leg `ORB_R6` | crowned on RISK — makes ~5% LESS money than #234; wfe 3.15 vs 4.65; trades 152/yr vs 166, droughts to 28 days. Do NOT cite its EV R (gameable by the breakeven) |

## TIER 2 — real edge fingerprint, fails the bar (revisit only as a BOOK leg or a lower-bar sleeve)

| # | What | Numbers | Where | Why it failed |
|---|---|---|---|---|
| B4 | QQQ 2-day dip buy (RSI2<10, close>200d, exit close>5d) | n=155 · $70,913 · PF 1.95 · **MAR 7.67** | `tools/r19_etf_classics.py`; row 553-area | nearest single-leg miss of the hunt (bar 8) |
| B5 | GLD 7-day-low buy | n=160 · $135,185 · **PF 2.33** · MAR 4.9 | same | highest PF of the hunt, half the MAR bar |
| B6 | NQ capitulation buy, exit +5d | n=194 · $238,892 · PF 1.81 · MAR 4.0 | `tools/r20_misc_triage.py` | no honest stop, MAR |
| B7 | NQ pullback to 20d EMA (long) | n=168 · $150,654 · PF 1.88 · MAR 4.6 | `tools/r17_misc_triage.py` | one -$23k stopless 2022 hold |
| B8 | ES 24h ENGU-Q with ES-fit params | validate job `WczpkNIr17qkomvXq1FS`: $139,799 / PF 1.63 / DD $34,948 / MAR 4.0 · WF 6/8 · LB $39,734 / PF 1.88 / MAR 1.33 · verdict WEAK (PBO fail) | Past Runs (no run number assigned by the runner; job doc holds the full report) | overfit check failed; ES is not this mechanism's tape |
| B9 | NQ Mondays only (buy open, sell close) | n=769 · $131,967 · PF 1.35 · MAR 4.9 | `tools/r24_calendar_vix.py` | best calendar cell, under bar |
| B10 | ENGU-Q ETH on mid-VIX days | PF 1.47 vs 1.28 unfiltered (n 711) | same | a FACT not a filter — MAR falls because 2/3 of trades are dropped |

## TIER 3 — structural lessons that now steer every search

- Leg-level performance does NOT persist; diversification does (r25b K2: selecting legs on 2010-17 -> MAR 3.45 vs 7.20 taking all).
- Every fade dies (rounds 13-21). The 9:30 NY open is the only tradeable open for ORB (r20). The crown risk engine is not portable (r22/23). ENGU-Q needs 1m granularity (r22). Resting overnight stops only hurt a close->open hold (r18b).
- Never filter trades on a quantity known only after the trade's own window (r18 retraction).
- **The EV R / R-YR answer on ENGU-Q is run #309's crown, and it was already in the library
  (2026-09-05).** `ENGUQ_1M_ETH_ER_1_0.py` @ buf_atr 0.3 / tl_len 206 / ema_len 220 / limit_atr 0.55 /
  er_len 100 / er_th 0.0 / regime_len 10 / stop_mult 1.3 / breakeven_R 3.0 / act_R 1.5 / trail_frac 2.5
  / min_brk 1.6 / vol_mult 1.1 / atr_len 52. Continuous, entry-sliced: selection n=1,505 / PF 1.661 /
  $505,756 / DD $44,403 / **EV R 0.439 / R / YR 43.9**; lockbox n=99 / PF 1.620 / $85,511 /
  **EV R 0.407 / R / YR 40.4**; **top-10 share 53%** — the lowest measured, and ex-top-10 it still
  nets $235,741. Beats the DEPLOYED #226 leg on selection EV R and R / YR, on lockbox EV R, and on
  tail dependence (53% vs 80%); loses only on lockbox R / YR (40.4 vs 68.5) because it trades about
  half as often. Verified with `tools/continuous_lb_check.py`. **CROWNED 2026-09-05 (owner) — see
  B2 above and ENGUQ.md's CROWN CHANGE 2026-09-05 section.**
- **EV R is a tail detector on ENGU-Q ETH (measured 2026-09-05).** Every config found at EV R ≥ 0.9
  had a top-10 share ≥ 90% — two of them LOSE money without their ten best trades, and one (run
  #310, verdict PASS) takes zero lockbox trades because it holds one position 449 days. The cause is
  a wide trailing exit on a 24h tape with no EOD flat. Report top-10 share and longest hold beside
  every EV R, and run `tools/continuous_lb_check.py` before queuing a validate or a book. See
  ENGUQ.md §1.0.

## Search log pointer
Rounds 13-25 detail: `MISC_SWEEP.md`, `TV_SWEEP.md`, `BACKTESTING_STACK.md` (Changelog).

## TIER 1 additions — round 26 (walk-forward optimized, OOS-only numbers)

| # | What | Numbers | Where / reproduce | Caveat |
|---|---|---|---|---|
| **B11** | **NASDAQ 8-leg WF book** — now a real file `augur_strategies/NQDIP_1_0.py`; **Auto-Validates queued 2026-08-25: NQ 5m job `8zkU44lPUNRtKR5IMWR2`, QQQ 1d job `n35b6uNdKpKRCt1CQ3nV`** (full discovery, 10 ranged knobs, 8 WF folds, 12-mo lockbox, costs/sizing inside the plugin so cost_pts 0 + mult 1 are correct) — 4 dip mechanisms (2-day RSI dip, N-day low, pullback to short EMA, capitulation) on QQQ + the same 4 on NQ micros, re-tuned per fold on past data only | n=1250 · $706,799 · PF 1.95 · DD $69,877 · **MAR 10.11** · 12/14 yrs · corr 0.041 to champion · **STACK on champion 8.31 -> 11.20 (+35%, bar +15%), net +85%** | `tools/wfo_nasdaq_fine.py` (+ `wfo_daily_dips.py`, `wfo_daily_dips_books.py`); OOS series `tools/r16_results/wfo_nasdaq_fine_oos.csv`; STUDIES rows 1141-1158 | recent half MAR 4.26; 1999-2010 holdout MAR 1.3-2.3 (bull-regime edge); no stops; QQQ half = stocks account |
| B12 | NQ 4-mech WF book in whole MNQ contracts (the half tradeable today) | n=544 · $263,886 · PF 1.83 · DD $32,248 · **MAR 8.18** | same harness, integer-MNQ sizing (`tools/r16_results` + this session's check) | futures account only; DBL leg alone PF 2.56 / MAR 9.9 |
| B13 | QQQ 7-day-low buy (WF star leg) | n=134 · $113,336 · PF 2.54 · DD $9,304 · MAR 12.18 · **12/12 folds** | `tools/wfo_nasdaq_fine.py` | n<150 alone; config drifts (n 4-15, trend 150-300) |

## TIER 3 additions
- Re-optimizing a BROAD multi-instrument book per fold makes it worse (MAR 3.05) than fixed simple settings (r25, 10.31); only the Nasdaq legs reward re-tuning.
- Hourly-scale intraday mean reversion (RSI/Bollinger on 30m/60m NQ+ES) is dead out of sample.
- Constant-notional sizing matters: 1-contract NQ legs looked like MAR 3-4; at constant $100k (micros) the same legs score 6-10.

## Final-process status (2026-08-25)
- `augur_strategies/NQDIP_1_0.py` — the book as one ranged strategy file (asset model auto-detected: one bar per session = ETF/shares, else NQ/whole MNQ micros). Fixed-default parity through the engine, 2010-06-07..2025-06-29: NQ n=629 / $333,424 / PF 1.74 / DD $40,479 / MAR 8.24; QQQ n=618 / $335,922 / PF 1.72 / DD $42,771 / MAR 7.85.
- `QQQ 1d` master registered (Yahoo total-return daily, bars stamped 09:30 ET, 1999-03-10..2026-08-25, source `yahoo_adj`).
- Auto-Validate jobs: **NQ 5m `8zkU44lPUNRtKR5IMWR2`**, **QQQ 1d `n35b6uNdKpKRCt1CQ3nV`** — queued behind the sibling session's ENGU-Q validates. When both land: queue the BOOK job (two legs, each validate's champion params, mult 1) so the pooled card exists too.

## Round 27 (2026-09-04) — the EV R / R / YR hunt (owner: beat everything on EV R and R / YR)

Definitions (v73.589): EV R = (1 - win%) x (PF - 1); R / YR = EV R x trades per year. Board rows 1165-1177 (v73.589).

| # | What | Numbers | Where / reproduce | Caveat |
|---|---|---|---|---|
| **B14** | **R / YR frontier config** — the UNCROWNED candidate inside run #309 (`ENGUQ_1M_ETH_ER_1_0.py`, NQ 1m 24h): buf_atr 0.45, tl_len 206, trail_frac 3.0, breakeven_R 0.5, atr_len 52, act_R 1.5, ema_len 220, limit_atr 0.4, er_len 50, stop_mult 1.8, regime_len 5, min_brk 1.3, vol_mult 1.1, er_th 0.1 | pre-lockbox n=2342 · $449,149 · PF 1.705 · win 14.9% · DD $82,181 · **EV R 0.60 · R / YR 93** (crown of #309 = 32; NOISE crown #305 = 77) · WF 7/8 folds · **lockbox +$43.7k, PF 1.29, 211 trades** | `tools/mine_ryr_frontier.py` -> `tools/r16_results/ryr_frontier.csv`; own card = grid job `52SsjQYXXV6NBOdbPDDX`; CONFIGS view of #309 | **VERIFIED + PRICED 2026-09-05** (`tools/continuous_lb_check.py`). Reproduces to the dollar as a card (run #313, and again independently: n=2,342 / $449,149 / PF 1.705 / EV R 0.600 / R / YR 93.3, and the engine's own `expectancy_r` agrees to 3 dp). **Delete its 10 best trades: net $85,637 (−81%), EV R 0.115, R / YR 17.8.** That top-10 share of 81% is NOT unusual for this family — the DEPLOYED #226 leg measures 80% on the same window with the same tool, and even ex-top-10 B14 still beats #226 on both reads (0.115 / 17.8 vs 0.046 / 8.0). What it does not beat is the config the MAR rule crowned instead: same MAR (0.36 vs 0.37) on a 35% deeper drawdown ($82k vs $61k), and ex-top-10 the ER crown holds more of its edge per trade (EV R 0.134). **Read it as: the best R / YR config in the library, bought with drawdown rather than with a better trade.** Promotion needs a pre-registered decision on whether R / YR outranks MAR, not another backtest. |
| B15 | NQDIP 1.1 — three added dip legs (IBS, losing streak, gap-down) | 7 legs at best single-leg settings: n=1714 · $623,053 · PF 1.64 · DD $61,090 · MAR 10.2 · win 67.8% · EV R 0.21 · **R / YR 23.5** (1.0 book: 9.4) · 8/8 slices | `augur_strategies/NQDIP_1_1.py`, `tools/sweep_nqdip11.py`; Auto-Validate queued `6FcGzxBn0LKbKNcMVlla` | **⚠ DEAD 2026-09-05 — the Auto-Validate came back FAIL.** Run **#315**: 4 of 6 gates, **3 of 8 walk-forward folds**, walk-forward efficiency **0.15**, lockbox 110 trades / PF 1.21 / EV R 0.085 / R / YR 9.3 against a pre-lockbox R / YR of 20.1. The sweep that promoted it claimed MAR 10.2 on 8-of-8 slices; the validate is the answer and the sweep was not. LESSON: an in-house slice sweep is a shortlist, never a verdict — the folds are where a 7-leg pile of dip mechanisms falls apart. |
| B16 | 3-leg paper-honest book (ORB #234 + ENGU-Q ETH #226 + NQDIP #307) | run **#311** PASS · n=5902 · $1,037,330 · PF 1.38 · DD $114,107 · EV R 0.23 · **R / YR 82** · LB PF 1.56 | Past Runs #311 | books add R / YR by adding trades (legal 2-leg with NOISE #261 = 113) |

Dead this round: `EMAPB_1_0.py` (1m EMA-pullback continuation, 27/27 cells lose, PF 0.86-0.94); ENGU-Q NQ+ES pooled (#312) R / YR 48 vs 43 alone - the WEAK ES leg dilutes.
Lesson: the crowning rule (MAR floor) and the owner metric (R / YR) pick DIFFERENT configs from the same search - mine populations before building anything new.

## Round 28 (2026-09-05) — the R / YR OBJECTIVE SEARCH (board rows 1241-1245, v73.589)

The app crowns on its MAR rule; the owner ranks on EV R / R / YR. Different objectives -> the
R / YR frontier sits uncrowned inside passed runs. Method: `tools/ryr_search.py` (objective
random search over a file's OWN declared ranges) -> `tools/ryr_neighbourhood.py` (one-step
plateau check) -> only if the plateau holds, a fenced neighbourhood file -> full Auto-Validate.

| # | What | Numbers (pre-lockbox, 2010-06..2025-06) | Where | Status |
|---|---|---|---|---|
| **B17** | **EV R RECORD — ENGU-Q 24h ER frontier config** | n=833 · $257,557 · PF 2.553 · win 9.8% · DD $17,583 · MAR 14.65 · **EV R 1.40** · 55 tr/yr · R / YR 77.4 · 7/8 slices | `augur_strategies/ENGUQ_1M_ETH_ER_RYR.py` (fenced 243-cell nbhd, parity-verified); search `tools/r16_results/ryr_search_enguq_er.csv` | **Auto-Validate queued `B88YSrSDg9KtupQXjJdI`** |
| **B18** | **R / YR RECORD for NOISE** | n=5,548 · $146,392 · PF 1.325 · win 14.3% · DD $16,345 · MAR 8.96 · EV R 0.279 · **368 tr/yr · R / YR 102.6** · 7/8 slices | `augur_strategies/NOISE_1_2_RYR.py`; search `ryr_search_noise.csv` | **Auto-Validate queued `Sl7Gxvj6cktTeQnOPRmZ`** |

Plateau evidence (before any validate was spent): ENGU-Q 26/26 one-step neighbours keep PF>=1.25
and 6+/8 slices, median neighbour R / YR 77.3 vs centre 77.4; NOISE 29/30 keep PF>=1.25, median
100.9 vs 102.6. Files `ryr_nb_*.csv`.

**Honest negative: NQDIP 1.1 FAILED its Auto-Validate (run #315)** — wfe 0.154, consistency fail.
The sweep's R / YR 23.5 / 8-of-8 did not survive the app's own walk-forward. NQDIP 1.0 (#307,
PASS 6/6) stands; 1.1 parked. A sweep is never the last step.

## Round 29 (2026-09-05) — the frontier legs pooled: **the best book measured** (rows 1246-1252, v73.589)

One common pre-lockbox window (2010-06-07..2025-06-29), real engine, pooled by exit time,
scored as ONE strategy (`tools/book_ryr_frontier.py`).

| # | Book | n | Net | PF | MaxDD | MAR | EV R | tr/yr | **R / YR** | slices |
|---|---|---|---|---|---|---|---|---|---|---|
| — | CROWNED pair (NOISE crown #305 + ENGU-Q LIM #310) — baseline | 6,128 | $630,450 | 1.344 | $64,540 | 9.77 | 0.231 | 407 | 94.1 | 8/8 |
| **B19** | **FRONTIER pair (NOISE R/YR + ENGU-Q EV R 1.40)** | 6,381 | $403,949 | **1.656** | **$17,900** | **22.57** | **0.566** | 424 | **239.7** | 7/8 |
| B20 | FRONTIER trio (+ legal ORB #234) | 8,792 | $704,728 | 1.421 | $30,956 | 22.77 | 0.324 | 584 | 189.4 | 7/8 |
| — | All five legs | 14,920 | $1,335,177 | 1.380 | $75,417 | 17.70 | 0.278 | 991 | 275.4 | 8/8 |

**B19 beats the crowned baseline on EV R, R / YR, PF, drawdown AND MAR simultaneously**, on
legs that are effectively independent (daily correlation +0.022). Book cards queued:
`UQI8tV4YPyZh7DqCCdSv` (2-leg), `w60azTVlKDptxfCwfJRS` (3-leg).

Limits measured, not assumed: **a book cannot beat its best leg on EV R** (trade-weighted
average) — it can only add R / YR. Adding ORB dilutes (EV R 0.57 -> 0.32) because ORB is the
lowest-EV-R leg in the library (0.150); an R / YR search over 400 ORB configs could not pass 21.

**Caveat carried on every card:** both frontier legs were selected by a search on this same
window, so the book inherits that selection. Their own fenced validates are queued (B17/B18).

## Round 30 (2026-09-05) — the R / YR ceiling of every family (rows 1253-1257, v73.589)

Identical objective search (`tools/ryr_search.py`) on each family's own file and ranges,
same seed/window/gates, so the ceilings read against each other:

| Family | configs | ceiling | what it is |
|---|---|---|---|
| **NOISE** | 600 | **R / YR 103** (368 tr/yr, EV R 0.28) | the FREQUENCY family |
| **ENGU-Q 24h efficiency variant** | 200 | **EV R 1.40** (55 tr/yr, R / YR 77) | the EDGE family — library record |
| ENGU-Q 24h base (the paper leg) | 180 | EV R 0.45 / R / YR 82 | the ER variant is genuinely better, not luck |
| ORB | 400 | R / YR 21 (EV R 0.13–0.17) | the FLOOR — earns money, almost no edge per trade |
| TTM Squeeze | 250 | R / YR 12 | confirms closed |

**Why it matters:** the frequency ceiling and the edge ceiling sit in DIFFERENT families —
that is exactly why pooling them (B19) beat every book measured, and why pooling two legs
from the same family would not have.

## 2026-09-08 — RETRACTION of B17 and B19 (rows 1283-1287, v73.589)

**B17 (EV R record 1.40, ENGU-Q ER frontier) is WITHDRAWN.** Its Auto-Validate came back
**PASS 6/6 (run #320)** and it still fails the test that matters: **101% of its net comes
from TEN trades**; ex-top-10 the other 823 trades make **-$3,821 at PF 0.977**. The house
artifact guard flags it SUSPECT at 99% top-10 share and is correct. EV R divides by the
average LOSING trade, so it rewards exactly this few-enormous-winners shape — a wide trail
on the 24h tape (holds to 179 days) scores 1.4 while being untradeable.

**B19 (the frontier PAIR book, "R/YR 240 / EV R 0.57") is WITHDRAWN with it** — 65% of its
net was those same ten trades; ex-top-10 it is $142,571 at PF 1.23, EV R 0.20. Both book
cards were already cancelled in the queue and are **not** being requeued.

**B18 (NOISE R/YR frontier) SURVIVES the same test**: top-10 share 43%, ex-top-10 still
$84,029 across 5,538 trades at PF 1.187, EV R 0.160. Its own validate was **WEAK** (run
#319, overfit check only) — a candidate, not a champion.

**New gate: `tools/concentration_check.py`** — run BEFORE queueing. Bar: top-10 share >=90%
or a negative ex-top-10 net = ARTIFACT, do not queue; 50-90% = state it on the card; <50%
with positive ex-top-10 = spread. Reference: deployed ENGU-Q leg 80%, NOISE crowns 22-43%.

**Process lesson:** plateau = do neighbouring settings agree (26/26 did). Walk-forward = does
it hold untuned (it did). **Neither answers whether the profit is ten trades.** Three
different questions; ask all three.

## Round 31 (2026-09-08) — B19's replacement books, and the crown's own risk-knob sibling

B19's original frontier-pair cards were cancelled (the ER_RYR leg is an EV R tail artifact, see
the retraction above). Replacement BOOK validates, all verdict **PASS**, common window
2010-06-21..2026-06-30, lockbox from 2025-06-30, book lockbox = day-sliced P&L:

| # | Book | Pre-lockbox | Lockbox | Note |
|---|---|---|---|---|
| **B22** | pair NOISE_1_2_RYR + ENGUQ_1M_ETH_ER_1_0 (#309 crown) | run **#317**: 7,052 trades / PF 1.520 / $631,992 / DD $40,129 | 521 trades / PF 1.556 / $133,038 | |
| **B23** | pair NOISE_1_2_RYR + ENGUQ_1M_ETH_R2_1_0 | run **#323**: 7,378 trades / PF 1.551 / $650,981 / DD $34,769 | 540 trades / PF 1.585 / $135,907 | **beats #317 (B22) on every header read** |
| **B24** | trio (+ NOISE_1_0 afternoon leg) | run **#324**: 11,797 trades / PF 1.496 / $797,524 / DD $39,947 | 791 trades / PF 1.524 / $158,135 | more money, lower PF, same DD — the third leg adds trades, not quality |

Per-leg continuous entry-sliced guard (`tools/queue_guard.py`, same window/split):

- **NOISE_1_2_RYR** defaults: selection 5,525 trades / PF 1.325 / $146,020 / DD $16,345 / EV R
  0.278 / R-YR 103.0; lockbox 421 trades / PF 1.270 / $27,371; top-10 share 43%; **PASS**.
- **ENGUQ_1M_ETH_R2_1_0** defaults (be 2.0 / stop 1.0): selection 1,830 trades / PF 1.714 /
  $522,613 / DD $38,687 / EV R 0.505 / R-YR 61.7; lockbox 118 trades / PF 1.675 / $88,380 / DD
  $41,534 / EV R 0.487 / R-YR 57.5; top-10 share 52%; longest hold 142 d; **PASS**.

Note the pooled per-leg continuous lockbox ($115,751 = $27,371 + $88,380) is BELOW the book's
day-sliced lockbox ($135,907, B23) because a 142-day ENGU-Q hold that entered before the split
lands in different windows under the two slicing rules — state both, neither is wrong.

Also landed this round: NOISE momentum-tilt validate **#327 = WEAK** (not adopted); compression
gate **#321 = PASS** (already recorded — see the feature-board memory / BACKTESTING_STACK
Changelog, cross-reference only, not repeated here); ORB R7 **#325 = FAIL** (transfer + PBO) —
**#314 stays the ORB crown** (see `ORB.md`, memory `edgelog-which-orb-to-trade`).

### B25 — "R2 = the crown's risk knobs corrected"

`ENGUQ_1M_ETH_R2_1_0.py` vs the #309 crown, both measured continuously (`tools/queue_guard.py`,
entry-sliced, same window/split as above):

| | #309 (crown) | R2 sibling |
|---|---|---|
| selection | PF 1.661 / $505,756 / EV R 0.439 / R-YR 43.9 | PF 1.714 / $522,613 / EV R 0.505 / R-YR 61.7 |
| lockbox | 99 trades / PF 1.620 / $85,511 / EV R 0.407 / R-YR 40.4 | 118 trades / PF 1.675 / $88,380 / EV R 0.487 / R-YR 57.5 |
| top-10 share | 53% | 52% |
| longest hold | 282 d | 142 d |

**R2 beats #309 on every read above. CROWNED 2026-09-08:** the validate posted as run **#335, PASS**
(6/6 checks, WF 8/8, lockbox held, PBO 0.385); paper leg `ENGUQ_335` trades the R2 defaults on both
boards and #309 is its matched control. The validate's own best cell is a different configuration
with a weaker held-out year ($49.8k PF 1.46 vs $88.4k PF 1.68) — recorded, not adopted; see
`ENGUQ.md` CROWN CHANGE 2026-09-08. NinjaTrader unchanged. See `ENGUQ.md` for the `{}`-params trap this
comparison exposed and fixed.

## 2026-09-08 — B21 GAPGO family seed (rounds 32-34, rows 1288-1299, v73.589)

**Owner ask:** something that can branch out into its own strategy family for another session.
Seven never-traded mechanisms pre-registered (`tools/r32_family_seeds.py`, `r32b_weekly_or.py`,
`r33_family_seeds2.py`, `r33b_ovngo_controls.py`, `r34_family_seeds3.py`), concentration test in the loop.
**Six dead** (RELEASE, VALUE AREA, WEEKLY-OR, VOLBAR, LEAD-LAG, RETEST — 55 cells, do not re-test).

**B21 — GAPGO 1.0 (`augur_strategies/GAPGO_1_0.py`)**: trade the overnight-gap direction (|open − prior RTH
close| ≥ gap_mult × ATR20 of daily ranges) once a 5m bar CLOSES beyond the first bar(s) that way; stop =
stop_mult × first-bar range; BE 1R pinned; flat at close; calendar roll-seam skip. Triage (2010-06-07..2025-06-29,
lockbox never loaded): **n=2007 / $151,024 / PF 1.341 / DD $16,672 / n/DD 9.06 / 8-of-8 slices / EV R 0.26 /
R/YR 35**. Parity harness↔plugin exact. Controls: plain 5m ORB both sides PF 1.10 (4/8); against-gap = tail;
any-gap direction PF 1.20 (8/8) → **the gap direction is the edge**. Plateau gap 0.10-0.25; 0.35 dies.

**Honest marks:** concentration 50% top-10 (ex-top-10 +$74,781 / PF 1.17) = CONCENTRATED, queueable.
**Overlap with ORB crown** (`tools/gapgo_vs_orb_overlap.py`): 63% of trade days shared, same direction 61%,
daily corr 0.19 (0.35 shared days), $136k of $151k earned on ORB days; ORB+GAPGO 1:1 n/DD 10.03 vs ORB 10.32 —
**a new trigger on the opening-momentum factor, not a diversifier.**

**Status:** Auto-Validate QUEUED 2026-09-08 (job G59lJB5aID4v2EFBqrAi, `tools/queue_gapgo_validate.py`; 8 WF folds,
12-month lockbox, window pinned to ORB crown 2010-06-07..2026-08-13). Open knobs gap_mult 0.10-0.30, stop_mult
0.5-1.0, or_bars 1-3. **Hand-off for another session:** 24h tape, ES, gap as a regime gate on the ORB crown
(replace/gate first-candle direction with gap direction), confirmation-bar count.

### B21 addendum — rounds 35-36 (rows 1300-1309, v73.589): GAPGO is a FAMILY

- **The gap is not yesterday:** first-bar break in the prior-day direction = PF 1.10, top-10 135%, ex-top-10 negative (`tools/r35_family_seeds4.py`).
- **ES transfer:** GAPGO 0.15 ATR on ES = PF 1.20, 6/8, top-10 72%, $56,733 at $50/pt — same sign, a quarter of the edge; not a leg.
- **B22 — GAPGO TRAVEL 1.0 (`augur_strategies/GAPGO_TRAVEL_1_0.py`)**: at 10:00 ET, |close − open| ≥ 0.3 × ATR20 → go with it, stop at the open, BE 1R pinned, flat at close. Triage n=1050 / $146,387 / PF 1.345 / DD $18,115 / n/DD 8.08 / 6-of-8 / top-10 54% (ex-top-10 +$67,064 PF 1.16). Edge decays with the clock (10:30 PF 1.23, 11:00 PF 1.16). Parity exact.
- **Why a family member, not a twin** (`tools/r36b_travel_vs_gapgo.py`): 26% of GAPGO days shared, TRAVEL earns +$157,283 on non-GAPGO days and −$10,896 on shared days, daily corr 0.24; pooled 1:1 n/DD 9.79 vs 9.06 / 8.08 alone.
- **Overnight-range position** (open in the outer 20% of the 18:00-09:25 range → first-bar break) is a third read: PF 1.31, 7/8, but 88% top-10 — noted, not adopted.
- **Dead in r35-36:** STREAK (3/4-bar persistence), FAILED FILL. 17 more cells.
- **Validates queued:** GAPGO_1_0 (G59lJB5aID4v2EFBqrAi) and GAPGO_TRAVEL_1_0 (`tools/queue_travel_validate.py`), both 8 WF folds / 12-month lockbox / ORB crown window 2010-06-07..2026-08-13. **Hand-off point = both posted.**

### B21 / B22 RESULT (rows 1310-1313, v73.589): both validates FAIL on the lockbox

- **#330 GAPGO 1.0** (gap 0.15 / stop 1.0 / 2 bars): selection n=1902 / $205,545 / PF 1.33 / DD $32,654; 6/6 gates, WF 8/8 (wfe 1.77), plateau HIGH GROUND, PBO 0.27, top-10 37%; **lockbox 2025-08-13..2026-08-13 = −$39,179 / PF 0.77 / 135 trades → FAIL.**
- **#329 GAPGO TRAVEL 1.0** (10:00 / 0.2 ATR / stop at open): selection n=1741 / $189,606 / PF 1.29 / DD $26,737; 6/6 gates, WF 7/8 (wfe 2.39), PBO 0.44, top-10 44%; **lockbox = −$15,923 / PF 0.90 / 134 trades → FAIL.**
- **Diagnosis** (`tools/gapgo_lockbox_year.py`): five positive Aug–Aug years before it for both; June–July 2026 lost $37.6k / $32.8k with median gaps ~0.5 ATR (norm 0.28) and 450–535-pt daily ranges; every gap-size bucket lost (pre-window >0.5-ATR gaps earned PF 1.26 on 691 trades, so a cap was never supported); master is clean Databento, 78 bars/day. **ORB crown made +$88,943 in the same year** — the gap read broke, not the factor.
- **Status: NOT validated, NOT handed over as a family.** Only open lead = a pre-registered, before-the-open regime condition (trailing median gap / range level) under which the gap read is trusted, re-validated on a fresh lockbox — never fitted to Jun–Jul 2026.

## Round 37 (2026-09-08) — THE SCALP HUNT (rows 1315-1336, v73.589)

Owner: beat the crowns from the SHORTER side, scalping if possible. Full doc: `NOISE.md` round 37.

| # | What | Numbers (pre-lockbox, 2010-06..2025-06) | Where | Status |
|---|---|---|---|---|
| **B26** | **NOISE on 2-MINUTE bars — the 4-minute scalp.** Search leader of `NOISE_1_0.py`'s own ranges on NQ 2m RTH: boundary exit · ATR stop 3.5 · confirm 4 · skip-top-long · lookback 46 · bands 0.75/1.5 · vol-skip 78 | n=5,340 · $213,549 · PF 1.477 · DD $10,917 · MAR 19.6 · EV R 0.40 · **R / YR 140.6 (library record; prior 102.6)** · 6/8 slices · median hold 4 min · $40/trade · top-10 34% (ex-top-10 +$141,865 PF 1.32) · plateau 30/30 · guard PASS. Daytype-OFF neighbour: R / YR 162, MAR 23.8, 7/8 | `tools/ryr_search.py` noise2m → `tools/r37_results/`; STUDIES rows 1321-1322 | **Auto-Validate QUEUED — `NOISE_1_0.py` FULL space on the NQ 2m master, job `qsSDwagxJsahDSmAwx1r`** (spent-lockbox caveat on the card) |
| B27 | The paper crown #243 configuration, untouched, on 2m bars | n=6,431 · $319,554 · PF 1.338 · **DD $12,873 (−30%)** · **MAR 24.8** · R / YR 96.9 · 7/8 · hold 12 min | STUDIES row 1316 | reference — the bar size is the lever; the 2m validate above is the test |

**TIER 3 additions (round 37):**
- **A fixed target cannot make a scalp on NQ 1m.** 25 of 25 fixed-target cells (1R / 2R, 30–60 min time stop) across five mechanisms lose or net nothing after the 0.533 round trip; only ride-to-close exits earn, and those hold 100+ minutes. The money is in the tail — shorten the BAR under a tail-keeping exit (NOISE's VWAP / boundary), never the trade.
- **1m is past the point where the NOISE band pays:** $27–29 a trade vs $40–50 on 2m, slices thin to 5/8. Two minutes is the floor for this mechanism at house costs.
- **Confirm-bar geometry does not travel across bar sizes** (#305's confirm-4 on 5m collapses on 2m to MAR 5.3; #243's confirm-1 improves). Re-search per bar size; never carry a bar-counted knob.

## TIER 1 addition — TTM round 7 (BOOK-validated, 2026-09-08)

| # | What | Numbers | Where / reproduce | Caveat |
|---|---|---|---|---|
| **B28** | **TTM crown (run 299, ES 30m, hourly-compression verified) as a BOOK LEG** — three ES contracts stacked on the baseline blend ORB #234 + ENGU-Q #309 (1 NQ each) | BOOK run **#336** vs control **#337**, identical window 2010-06-07..2026-06-30, LB 12 mo: whole $1,119,697 vs $964,571 · DD **$34,329 vs $34,329 (identical)** · ann. MAR **2.03 vs 1.75 (+16%, bar +15%)** · LB $193,170 vs $178,192 at LB DD **$26,235 vs $33,112 (−21%)** · slices 8/8 both, every slice improved · TTM leg $155,126 · corr TTM~ORB 0.060, TTM~ENGU-Q 0.003 | `augur_strategies/TTMSQZ_3_0_ES30N.py` @ gate_len 20 / stop_atr 1.5 / eod_cutoff 1 / kc_mult 1.5, weight 3; book legs as in run #336 doc; STUDIES rows 1365-1366 (key ttmsqz7); stack scan `tools/ttmsqz_round6_parts.py` legs | TTM alone is ~$2,900/yr — it earns its place ONLY as a diversifier (its losing days do not coincide with the crowns); the NQ TTM cells do NOT diversify (corr 0.3-0.4, add DD). 3 ES contracts ≈ $11k standalone DD; equal-risk (x9.6) overshoots (LB DD +36%). Not in paper; owner call. |

## 2026-09-08 — B23 ENGU-Q branches onto ES (round 37, rows 1367-1374, v73.599)

**Question turned around:** not a new mechanism on NQ, but a crowned mechanism on a second instrument (`tools/r37_es_branch.py`).
- ORB crown card on ES 5m RTH: PF 1.06, top-10 174%, ex-top-10 −$31k → dead (matches the validate transfer legs).
- NOISE crown card on ES 5m RTH: n=4204 / $131,957 / PF 1.236 / n/DD 14.3 / 5-of-8 / top-10 37% → near miss, not a leg.
- **ENGU-Q R2 crown (`ENGUQ_1M_ETH_R2_1_0.py`, NQ defaults, nothing re-tuned — all knobs ATR/R-relative) on ES 1m ETH at 0.40 pts/RT, $50/pt: n=2013 / $208,644 / PF 1.367 / DD $19,396 / n/DD 10.76 / 7-of-8 / EV R 0.27 / R/YR 36.** Top-10 69% (NQ crown 52%), ex-top-10 +$64,902 PF 1.11. Cost 0.60 → PF 1.32 / n/DD 8.4 (clears); 0.80 → PF 1.28 / n/DD 6.3. Plateau: 27/27 neighbours hold, 26/27 PF ≥ 1.25; best = trail 3.0 (PF 1.60, n/DD 14.8), worst = regime 5d (n/DD 4.1). Longest hold ~98 days (ENGU-Q shape).
- **Not yet measured:** ES-leg vs NQ-leg daily correlation (expect high on big days → account diversifier, not return diversifier).
- **Validate QUEUED** job GIrlgbDJ1umq12NrnfY8 (`tools/queue_enguq_es_validate.py`): ES 1m ETH, open ranges, 8 folds, LB 12m, window pinned to R2 crown #335 (2010-06-07..2026-06-30). **Hand-off point = validate posted.**
- **Correlation measured (`tools/r37d_es_nq_corr.py`): ES leg vs NQ leg, exit-day PnL corr 0.20, monthly 0.21; 685 shared entry days of 1,148 (NQ) / 1,262 (ES). Pooled 1:1 (daily-aggregated): NQ alone n/DD 13.2, ES alone 7.5, NQ+ES $720,491 / DD $44,896 / n/DD 16.1 — a RETURN diversifier, not just an account diversifier.**

## WEEK OF 2026-09-07 — what is of note, and what is still to be done (annotated 2026-09-08 night)

**Crowns and legs that moved this week**
- **ENGU-Q crown moved to run #335 (R2 = #309 + breakeven 2.0 R / stop 1.0)**; paper leg ENGUQ_335 on both boards, #309 kept as control; the R2 validate had to survive four fleet restarts to post (keep-aware restart `tools/fleet_restart.py --keep N` now exists because of it).
- **ORB is CLOSED on every axis** (#314 crown; round 7 prior-day filter FAILED #325; rounds 9-10b: fills honest, delayed range / re-entry / trap reversal / pyramid / time stop / direction rule 0 of 72). Only forward paper data is left.
- **The 1.5x compression SIZE TILT is the one overlay that passed its own bar** (run #333 on NOISE; #331's 2x corner was leverage). Paper legs C15 / C15G on NOISE, ENGU-Q, ORB from 2026-09-08/09. KEEL v10/v11 model rounds: no change.
- **TTM Squeeze = a BOOK LEG, not a strategy** (book #336 vs baseline #337: MAR +16% at identical DD, LB DD −21%, corr 0.06). Adoption = owner call.
- **Weak-edge ETF BOOK validated: run #332 PASS** (PF 1.72, net/DD 11.4, 8/8 slices, LB +$85k but LB DD $61k; NQDIP = 40% of net). Stocks-account book; ETF-only sub-book control queued.
- **NOISE on 2-MINUTE bars is the scalp side that pays** (R/YR 140.6 record, 4-minute median hold, plateau 30/30; full-space 2m validate queued). Five other 1m scalp mechanisms: 0 of 39; a fixed target cannot make a scalp at house costs.

**Retractions and guards**
- **The EV R 1.40 record (ENGU-Q ER) and the frontier pair book were WITHDRAWN**: 101% of net was ten trades; a 6/6 validate PASS did not catch it. New pre-queue gate `tools/concentration_check.py`; `queue_guard.py --run N` now resolves empty params like the runner and grades book legs (`--book-run`).
- **Runner fleet**: Firestore quota exhaustion traced to idle polling (~29k reads/day floor) and fixed; workers run no command thread; walk-forward folds in parallel processes (bit-identical); gate/KEEL models fit on one thread (two thirds of a validate was thread churn); the epoch run id from the 2026-09-07 outage renumbered to #328; one launcher for the 5-runner set.
- **CI was red for 14 commits** because an unpinned install pulled pandas 3; pinned `pandas>=2.2,<3`.

**The new-family hunt (this session, rounds 32-37)**
- Nine never-traded mechanisms across 72 cells: eight dead (RELEASE, VALUE AREA, WEEKLY-OR, VOLBAR, LEAD-LAG, RETEST, STREAK, FAILED FILL).
- **GAPGO (overnight-gap direction) and GAPGO TRAVEL (distance from open at 10:00) both passed triage and 6/6 gates, then LOST the sealed year** (#330 −$39k, #329 −$16k) while the ORB crown made +$89k in the same months: the gap READ broke in the June-July 2026 mega-gap regime, not the opening-momentum factor. Family NOT handed over.
- **The branch is an instrument, not a mechanism: the ENGU-Q R2 crown file clears the house bar on ES 1m 24h at its NQ defaults** (PF 1.37, n/DD 10.8, plateau 27/27, survives 0.60 pts/RT), and the ES leg's correlation to the NQ leg is only 0.20 (pooled n/DD 16.1 vs 13.2). **ES validate running (job GIrlgbDJ1umq12NrnfY8).**

**TO BE DONE (open action items, owner calls marked)**
1. Read the ENGU-Q ES validate when it posts; if it passes its sealed year, hand the ES branch to another session (files + `tools/r37*` harnesses + B23) and decide whether it becomes a paper leg on the ES/MES account. — this session
2. Read the NOISE 2m full-space validate (job qsSDwagxJsahDSmAwx1r); if it passes, the 2m leg is the scalp-side candidate for paper. — NOISE session
3. **Owner call:** adopt the TTM book leg (#336) into the baseline book, or not.
4. **Owner call:** ETF weak-edge book — run the ETF-only sub-book control, then decide on a QQQ-shadow paper leg.
5. **Owner call:** the 1.5x compression tilt legs (C15/C15G) — judge on forward paper data, first read after a few weeks.
6. NinjaTrader still runs the #226 ENGU-Q port; the live leg has not been moved to the #335 crown (NT restart is owner-only).
7. NOISE crown on ES is a near miss (PF 1.24, 5/8): one fenced neighbourhood look on the ES 5m tape, cheap, not yet done.
8. ~~Scalpers round 38~~ DONE: 0 of 20 (rows 1375-1381, v73.603) - sweep-reclaim, chop-fade, ignition, box-break all lose at house cost with fixed AND ride exits; the 1m tape is cost-dominated; week total 0 of 59 short-hold cells across two sessions. Do not re-test 1m fixed-target scalps.
9. Data: the NQ 1-minute hole 2026-07-01..08-05 is unrecoverable (5m is clean); any 1m validate whose lockbox spans it needs the caveat on the card.
10. Alpaca key / Databento buy remains the only route to a genuinely new data axis (1m stock bars for an intraday QQQ family, or other futures for instrument branches).
