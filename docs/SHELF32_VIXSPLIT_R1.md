# SHELF No. 32 - the VIX split of the European-open hold: CLOSED AT DRAFT (TV, 2026-10-16)

Paper: Bondarenko and Muravyev (2023), "Market Return Around the Clock: A Puzzle", JFQA 58(3). Scope: MANAGER #145 - only the
paper's VIX side is new (the European-open hold itself is ledger 2.13 / 2.75). Prereg `docs/PREREG_tv_shelf32_vixsplit_2026-10-16.md`
(LF sha256 0bc4cfb7..., witness branch prereg/tv-shelf32 @ 823a46a9, pushed and posted to MANAGER before the run; reviewed
adversarially before the freeze). Harness `tools/tv_shelf32_vixsplit.py` (LF 83299fb1...; MAPCHECK-F pinned by sha). Output
`C:\EdgeLog\_research_cache\tv_shelf\paper32_vixsplit\` (result.json, MAPCHECK_F.txt / .csv; run log `..\shelf32_run.log`).

PRE-WF ROWS ONLY: NQ / ES 5-minute ETH back-adjusted masters (ids 71 / 62), 2010-06-07 .. 2016-06-30 (6.06 years, 1,547 nights).
Walk-forward and lockbox not read. Long 1 contract, no stop; NQ 0.706 pt / ES 0.582 pt a round trip; VIX = the day's CBOE close
change known before the 23:30 entry (UP 710 nights, DOWN 830, flat 7).

## Verdict: CLOSE AT DRAFT on both markets (both gates fail)
| Market | Gate 1: W2 UP minus DOWN (the split vs 2.13) | Gate 2: MAPCHECK-F on the halved W2-UP prior | Verdict |
|---|---|---|---|
| NQ | +$6.11 a night, Welch t 0.67 (bar 2.0) | own WF ROC median +0.6, P(>= 15) 2%, P(lift #463) 9% | CLOSE |
| ES | +$17.73 a night, Welch t 1.69 (bar 2.0) | Sharpe floored at 0: own ROC -0.0, P(>= 15) 2%, P(lift) 9% | CLOSE |

The unhalved upper bound also closes (NQ own ROC +1.6, P(>= 15) 4%, lift 14%; ES -1.1) - printed, not judged.

## The cells ($ a night after cost, pre-WF)
| Cell | NQ ALL | NQ UP | NQ DOWN | ES ALL | ES UP | ES DOWN |
|---|---|---|---|---|---|---|
| W2 01:30 -> 04:00 (2.13 window, candidate) | -0.25 | +2.60 | -3.51 | -12.03 | -3.04 | -20.77 |
| W1 23:30 -> 03:30 (paper's hours, context) | +2.72 | +6.88 | -1.10 | -8.25 | +3.84 | -18.87 |

Four numbers on the pre-WF daily P&L at one contract, scaled to a $30k worst drawdown (draft read, context only):
- NQ W2-UP: ROC@30k 2.6, DD5 $19.2k, DD% from peak 27.8%, Sortino 0.23 (1 EPISODE).
- NQ W1-UP: 7.8 / $20.9k / 29.1% / 0.66 (1 EPISODE).
- ES W2-UP: -1.7 / $30.0k / 29.8% / -0.23.
- ES W1-UP: 2.4 / $12.6k / 29.2% / 0.32 (1 EPISODE).

## Reading
- The paper's direction shows up - VIX-up nights beat VIX-down nights in every cell - but the gap is a loss on down nights more than a
  gain on up nights, and it is not significant in the candidate window (t 0.67 NQ, 1.69 ES). The one cell over t 2 is ES W1 (t 2.31),
  a context window, never a pass route, and its UP leg makes $3.84 a night (ROC 2.4).
- The European-open drift is real gross on ES (W1 ALL ~ +$21 a night before the $29 round trip) but the cost eats it; on NQ it is
  ~$17 a night gross, $2.7 after cost. Same lesson as 2.13 / 2.75 / OVERNIGHT-DOWNDAY: the overnight seat is closed, with or without the VIX split.
- Nothing to Auto-Validate (the map did not clear). Nothing live or paper changes.
