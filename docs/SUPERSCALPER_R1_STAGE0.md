# SUPERSCALPER r1 - Stage 0 (port fidelity) RESULT: FAIL (TV, 2026-10-14)

Prereg: `docs/PREREG_tv_superscalper_r1_2026-10-14.md` + Amendment 1 (witness branch prereg/tv-superscalper-1014 @ 7d4f3ec8).
Reference: the author's published 274-trade report (273 closed; MNQ1! 1-minute, 2026-03-29 .. 04-21, Chicago time).
Port: `augur_strategies/MISC_SUPERSCALPER_1_0.py`; harness `tools/superscalper_parity.py compare` (match statistics only - the
window is inside the lockbox year; no port P&L, total, win rate or drawdown on it was printed or read).

## The registered statistic (intrabar = 'tv', TradingView's fill model)
- TradingView trades matched (side + entry minute +/- 1 bar): 144 of 273 = **52.7%** (bar 80%) -> FAIL
- Port trades matched: 66.7% of 216; entry price median gap 1 tick after TradingView's slippage
- Matched pairs' P&L correlation: **0.804** (bar 0.80) -> passes alone; exit-reason agreement 86.8%; exit price median gap 37.5 ticks
- Also run, in the house default mode by mistake first (intrabar 'worst', not the registered mode): 52.7% / 0.743 - disclosed.

## Why (diagnostics, match statistics only - `tools/superscalper_parity_diag.py`)
- The misses are everywhere, not one session: unmatched TradingView trades spread over every New York hour; 81 of the 129 have no
  same-side port entry within 30 minutes (the port never took them). Exits diverge too: of the 144 matched pairs only 58 exit within
  a minute of TradingView, 50 more than 15 minutes apart.
- The script reads three TradingView-only feeds the house does not hold for history: `request.footprint(50, 70)` (Premium tick data:
  POC / VAH / VAL and delta, used in targets and the direction score), `USI:TICK` (NYSE TICK) and `CBOE:VIX` on 1-minute bars (both
  inside the 17-factor direction score that vetoes entries). The port takes the script's own "data missing" branches, which the
  author's run never took; MNQ volume (relative-volume filter) is also not held (NQ used).
- These are DATA gaps, not porting slips: a repair round (allowed once by the prereg) has nothing to repair with until the house holds
  intraday VIX, NYSE TICK and tick-level NQ / MNQ data (Databento was declined by the owner). Verdict: **the port cannot reproduce the
  published script on house data** - per the prereg no Stage A verdict is claimed for the script itself.

## Disclosure
The port's developer (a sub-agent, on TV's instruction written before the prereg) ran the port on 2024 (inside the walk-forward
window, before Stage 0 and before STRATEGY-BEATING's second check) as a speed / sanity test: 2,718 trades, 68.8% wins, average win
15.5 vs average loss 33.4 points, gross profit factor 1.03, net 0.96 at the 0.706-point cost. Reported here so nobody reads it as a
clean result: it is one development year of a port that does not match the script.
