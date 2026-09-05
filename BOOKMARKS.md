# BOOKMARKS — the promising things, in one place

Owner ask 2026-08-25: "bookmark what you've found promising so far." This file is the
durable list. Every entry names the exact reproduction path. Numbers are pre-lockbox
unless a run number says otherwise. Bar for "promising" = a real edge fingerprint,
whether or not it clears the full house bar (PF >= 1.25, MAR >= 8, n >= 300).

## TIER 1 — passed a pre-registered bar

| # | What | Numbers | Where / reproduce | Caveat |
|---|---|---|---|---|
| B1 | **Weak-edge book** — 4 dip-buy mechanisms (RSI2 long/both, 7-day low, pullback-to-20d, NQ capitulation) x {NQ, GLD, TLT, IWM, QQQ}, ALL 20 legs, causal equal-risk, scored as ONE strategy | n=2925 · $1,220,386 · PF 1.52 · DD $118,321 · **MAR 10.31** · **WF 8/8** · bootstrap p~0 · corr 0.055 to champion book | `tools/r25_weak_edge_book.py`, kill-checks `tools/r25b_book_killchecks.py`; STUDIES rows 1027-1051 | STOCKS-account book (ETF legs alone MAR 10.33, NQ legs alone 4.19); recent half MAR 7.20; stack on champion +12% vs +15% bar; no stops on multi-day holds |
| B2 | ENGU-Q ETH (the certified champion leg, sibling session) | run **#226** PASS 5/5; $434,721 / PF 1.33 / DD $50,420 / MAR 8.62; LB $98,488 / PF 1.49 | `augur_strategies/ENGUQ_1M_ETH_FROZEN_1_0.py`; paper-forward live since 2026-08-17 | the only ENGU-Q variant whose backtest matches live behaviour |
| B3 | Legal ORB crown | run **#234** `ORB_3_6_C2.py`: $389,874 / PF 1.307 / DD $29,142 / MAR 13.38; LB $88,942 / PF 1.45 | pinned card | NQ 5m RTH only — does not travel |

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

Definitions (v73.460): EV R = (1 - win%) x (PF - 1); R / YR = EV R x trades per year. Board rows 1165-1177 (v73.479).

| # | What | Numbers | Where / reproduce | Caveat |
|---|---|---|---|---|
| **B14** | **R / YR frontier config** — the UNCROWNED candidate inside run #309 (`ENGUQ_1M_ETH_ER_1_0.py`, NQ 1m 24h): buf_atr 0.45, tl_len 206, trail_frac 3.0, breakeven_R 0.5, atr_len 52, act_R 1.5, ema_len 220, limit_atr 0.4, er_len 50, stop_mult 1.8, regime_len 5, min_brk 1.3, vol_mult 1.1, er_th 0.1 | pre-lockbox n=2342 · $449,149 · PF 1.705 · win 14.9% · DD $82,181 · **EV R 0.60 · R / YR 93** (crown of #309 = 32; NOISE crown #305 = 77) · WF 7/8 folds · **lockbox +$43.7k, PF 1.29, 211 trades** | `tools/mine_ryr_frontier.py` -> `tools/r16_results/ryr_frontier.csv`; own card = grid job `52SsjQYXXV6NBOdbPDDX`; CONFIGS view of #309 | uncrowned by the MAR rule (DD $82k vs crown's $44k); ER variant is the sibling session's file |
| B15 | NQDIP 1.1 — three added dip legs (IBS, losing streak, gap-down) | 7 legs at best single-leg settings: n=1714 · $623,053 · PF 1.64 · DD $61,090 · MAR 10.2 · win 67.8% · EV R 0.21 · **R / YR 23.5** (1.0 book: 9.4) · 8/8 slices | `augur_strategies/NQDIP_1_1.py`, `tools/sweep_nqdip11.py`; Auto-Validate queued `6FcGzxBn0LKbKNcMVlla` | one look at the combination; still a quarter of the ENGU-Q frontier |
| B16 | 3-leg paper-honest book (ORB #234 + ENGU-Q ETH #226 + NQDIP #307) | run **#311** PASS · n=5902 · $1,037,330 · PF 1.38 · DD $114,107 · EV R 0.23 · **R / YR 82** · LB PF 1.56 | Past Runs #311 | books add R / YR by adding trades (legal 2-leg with NOISE #261 = 113) |

Dead this round: `EMAPB_1_0.py` (1m EMA-pullback continuation, 27/27 cells lose, PF 0.86-0.94); ENGU-Q NQ+ES pooled (#312) R / YR 48 vs 43 alone - the WEAK ES leg dilutes.
Lesson: the crowning rule (MAR floor) and the owner metric (R / YR) pick DIFFERENT configs from the same search - mine populations before building anything new.
