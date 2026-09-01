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
| **B11** | **NASDAQ 8-leg WF book** — 4 dip mechanisms (2-day RSI dip, N-day low, pullback to short EMA, capitulation) on QQQ + the same 4 on NQ micros, re-tuned per fold on past data only | n=1250 · $706,799 · PF 1.95 · DD $69,877 · **MAR 10.11** · 12/14 yrs · corr 0.041 to champion · **STACK on champion 8.31 -> 11.20 (+35%, bar +15%), net +85%** | `tools/wfo_nasdaq_fine.py` (+ `wfo_daily_dips.py`, `wfo_daily_dips_books.py`); OOS series `tools/r16_results/wfo_nasdaq_fine_oos.csv`; STUDIES rows 1141-1158 | recent half MAR 4.26; 1999-2010 holdout MAR 1.3-2.3 (bull-regime edge); no stops; QQQ half = stocks account |
| B12 | NQ 4-mech WF book in whole MNQ contracts (the half tradeable today) | n=544 · $263,886 · PF 1.83 · DD $32,248 · **MAR 8.18** | same harness, integer-MNQ sizing (`tools/r16_results` + this session's check) | futures account only; DBL leg alone PF 2.56 / MAR 9.9 |
| B13 | QQQ 7-day-low buy (WF star leg) | n=134 · $113,336 · PF 2.54 · DD $9,304 · MAR 12.18 · **12/12 folds** | `tools/wfo_nasdaq_fine.py` | n<150 alone; config drifts (n 4-15, trend 150-300) |

## TIER 3 additions
- Re-optimizing a BROAD multi-instrument book per fold makes it worse (MAR 3.05) than fixed simple settings (r25, 10.31); only the Nasdaq legs reward re-tuning.
- Hourly-scale intraday mean reversion (RSI/Bollinger on 30m/60m NQ+ES) is dead out of sample.
- Constant-notional sizing matters: 1-contract NQ legs looked like MAR 3-4; at constant $100k (micros) the same legs score 6-10.
