# SHELF No. 32 - the VIX split of the European-open hold: power-first draft read on PRE-WF rows (TV, pre-registered 2026-10-16)

Written by TV before any number in it was computed. Paper: Bondarenko and Muravyev (2023), "Market Return Around the Clock:
A Puzzle", JFQA 58(3) 939-967 (shelf r2 No. 32; read from the shelf card and the RePEc abstract only - no PDF downloaded).
Scope set by MANAGER #145 (10-15): the paper's core trade, long index futures around the European open, is ledger 2.13 on NQ
(long 01:30-04:00 ET, $8.5 a trade, $16.6 after a down session, dead for ROC) and 2.75 (DD-WEEK r1: 16:00 -> 03:30 after a
down session, ROC 3.7, the overnight seat closed). Only the paper's VIX side - fear builds overnight and eases at the European
open - is new. So this is ONE question: does splitting the European-open hold by the day's VIX move make a leg worth a prereg?
If its prior cannot clear the map, it closes at draft with a two-line ledger row (MANAGER #145, power-first gate).

## Disclosure (already seen before this file)
- 2.13 (NQ, old roll detector): 01:30 -> 04:00 long, $8.5 a trade all nights, $16.6 after a down session (9 of 16 years).
- 2.75: NQ 16:00 -> 03:30 after any down session $48.8 a night, PF 1.10, ROC 3.7 on the 2016-07 .. 2025-06 WF; ES 03:30 cells
  +$8k to +$10k on #463's drawdown days but negative without their 3 best nights.
- MAPCHECK-F r1: OVERNIGHT-DOWNDAY prior (n 100, Sharpe 0.15) -> own ROC median 1.5, P(own >= 15) 4%, P(lift) 14%, CLOSE.
- NOT seen: any VIX-conditioned overnight number on any stretch; any 23:30 -> 03:30 number; anything after 2016-06-30 in this
  shape is used here.

## Data (pre-WF rows only)
- House 5-minute ETH masters back-adjusted on the true switch bars (source db_adj_eth: NQ id 71 ADJ_NQ_5m_ETH.csv, ES id 62
  ADJ_ES_5m_ETH.csv), bars stamped at START, clock US/Eastern. Every array is cut to bars before 2016-07-01 00:00 ET BEFORE any
  signal is computed (first bar 2010-06-06). The walk-forward (2016-07-01 ..) and the lockbox are not read.
- VIX: the CBOE daily history photograph `C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv` (sha256 6edc3e39...,
  the file the Super Scalper pins), columns DATE / CLOSE.
- Hold crossing a switch time (tools/data/rolls_<ROOT>.csv, kind != not_a_roll) pays 0.25 pt extra.

## The trade
- Night = calendar evening D with a bar starting in [23:30, 23:59] ET (decided before entry, by bar existence only).
  Window W2 (THE 2.13 WINDOW, the candidate): entry = the open of the first bar starting at or after 01:30 ET on D+1, which must
  start before 02:00 (else no entry); exit = the open of the first bar starting at or after 04:00 ET on D+1, however late.
  Window W1 (the shelf card's 23:30 -> 03:30, the paper's four hours; CONTEXT ONLY): entry = the open of the first bar starting
  at or after 23:30 ET on D; exit = the open of the first bar starting at or after 03:30 ET on D+1, however late. No entered
  night is ever dropped for what comes after its entry (DD-WEEK r1 addendum 2's rule); exits starting 30+ minutes after their
  target are counted and printed per market x window.
- Long 1 contract, no stop. P&L $ = (exit - entry - cost - 0.25 x switches crossed) x $20 NQ / $50 ES.
- Cost per round trip: NQ 0.706 pt, ES 0.582 pt (commission + 1 tick each side, the house rule). Stress +0.25 pt.
- VIX signal, known before the 23:30 entry: v = CLOSE of the last VIX date on or before D minus the CLOSE of the VIX date
  before it (a Sunday evening reads Friday's change; VIX closes 16:15 ET). Split UP = v > 0, DOWN = v < 0; v = 0 counted, in
  neither split. ALL = every night (the 2.13 baseline shape).
- Cells: 2 markets x 2 windows x 3 splits (ALL / UP / DOWN) = 12 rows, each with trades, $ a trade, t, per-trade Sharpe,
  trades a year, yearly Sharpe (= per-trade Sharpe x sqrt(trades a year)), calendar years positive, and the stress line. Plus
  UP minus DOWN per market x window ($ a trade, Welch t).

## Pre-set reading (the power-first gate)
- The question is the SPLIT, judged against the 2.13 baseline (MANAGER #145). The paper's direction: the European-open return is
  bigger when fear built (UP). Candidate per market = W2-UP (the 2.13 window, VIX-up nights only). W1 is printed with the same
  numbers as context and is never a pass route.
- Gate 1 - the split itself (its own power bar): W2 UP-minus-DOWN $ a trade > 0 with Welch t >= 2.0 on the pre-WF rows
  (unrounded means). Below that, the split adds nothing measurable over the 2.13 shape and the market closes, whatever the map
  says. Two markets are read, so a t near 2 in one of them is weak evidence; the map below is the real bar.
- Gate 2 - the leg (MAPCHECK-F's three rules): prior n = W2-UP trades a year on the pre-WF rows (unrounded), s_mid = HALF its
  pre-WF yearly Sharpe after cost (post-publication decay + 1 of 2 markets; floored at 0), s_sd 0.15, rho_dd 0.0 ('zero'), t3
  tails, clustered vol - the OVERNIGHT-DOWNDAY row's shape exactly. The unhalved Sharpe (not floored) is printed as an
  upper-bound row, labelled "upper bound - not judged" in the written record.
- MAPCHECK-F is pinned: tools/mapcheck_f.py LF sha256 e14ba5daaac0190a2d2d0d522b8a4bc962013f21db118e20a2ebe9daaab8bc06,
  tools/rocfrontier/r12_mdl.py 7675875aed479eb83d902fcf4b8385a5bbdce40cbe30b60fde9f2c0ee84562d9, tools/rocfrontier/r11_risk.py
  bf8f9ca5410e947f44e1628717fd4d415bdc0707998d14a6ab5ec3656166cd6b, and PRIORS holds its 10 rows before this file's rows are
  appended (seeds [20261010, k] for k = 10.., printed); any mismatch stops the run before a number.
- VERDICT per market: CLEARS (Gate 1 AND Gate 2) -> a full prereg (WF Stage A, then the 900-trial Auto-Validate on a ranged
  file). Otherwise CLOSE AT DRAFT with a two-line ledger row.
- Four numbers (ROC @ $30k, DD5, DD% from peak, Sortino) are printed for each W2-UP and W1-UP cell on the pre-WF daily P&L at
  one contract, k = 30000 / max DD, flagged "pre-WF, draft read" - context, not the verdict.

## Harness
`tools/tv_shelf32_vixsplit.py` checks this file's LF sha256 and the three MAPCHECK-F pins at start (its own LF sha256 is printed
and posted to MANAGER before the run) and stops on a mismatch. Output: `C:\EdgeLog\_research_cache\tv_shelf\paper32_vixsplit\`.
Pushed as prereg/tv-shelf32 before the run (RUN-BEFORE-MAIN). Review before freeze (3 lenses, adversarial verify, 10-16): the
first draft judged the W1-UP leg against W1-ALL and never tested the split against the 2.13 window - fixed here; minor fixes:
s_sd = the row's 0.15, unrounded n and means, upper-bound row not judged, MAPCHECK-F pinned, late exits kept and counted.
