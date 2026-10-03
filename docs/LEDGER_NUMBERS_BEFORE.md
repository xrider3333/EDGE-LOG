# LEDGER unify - numbers sheet, BEFORE (step 0, 2026-10-03)

Read off the live site in the owner's Chrome, web v73.984, 2026-10-03, nothing changed by the reader.
Every later unify step compares its boards against this sheet and explains any difference.
Before screenshots (12: three boards x laptop 1366x768 / phone 375x812 x glass / paper):
`C:\EdgeLog\manager\ledger_unify_1001\before_2026-10-03\` (outside git).
The step-0 render probe for REAL is `tools/home_render_probe.py` (ship gate since 97184897).

## REAL (HOME > REAL, all accounts, P&L mode, 86 trades)

| Range | Big number | Change line | Win rate | Profit factor | Max DD | Today |
|---|---|---|---|---|---|---|
| 3M (owner's saved range) | $153.76 | down $1.63 (-0.04%) past 3 months | 59% (2 ignored) | 1.01 | $207.08 | +$0.00 |
| ALL | $153.76 | up $153.76 (+3.44%) all time | 63% | 1.37 | $207.08 | +$0.00 |

- The header reads "CUMULATIVE P&L - ALL ACCOUNTS, reconciled with Webull".
- REAL has no calendar on this board (it lives in ANALYTICS).

## NT8 PAPER (NT8 futures paper, NQ demo, since 2026-08-11, all time)

| Big number | Today | Trades | Strategies | Win rate | Profit factor | Avg trade | Avg win | Avg loss | Max drawdown |
|---|---|---|---|---|---|---|---|---|---|
| $295,402 | $0 | 486 | 18 of 18 | 29% | 1.73 | $608 | $4,980 | -$1,179 | $115,066 |

- The trade list header reads "TRADES - 500 (14 OPEN) (showing 200)": the board loads the newest 500 trades only.
- The chart's top label reads $235,779, not the $295,402 big number (the known big-number vs bold-curve mismatch).

## WEBULL PAPER (since 2026-09-03, range ALL)

| Big number | Today | Closed trades | Broker share | Win rate | Profit factor | Trades | Max drawdown | Account equity |
|---|---|---|---|---|---|---|---|---|
| -$21.68 | +$0.00 | 46 | $2.82 of it (8 book-only trades excluded) | 30% | 0.93 | 46 | $206.02 | $999,838.15 (-$47.27, -0.01%) |

- Strategy rows: ORB #314 -$41.11, ENGU-Q #335 +$43.38, NOISE #382 -$23.95 (all FLAT).

## Things the screenshots show that the unify should fix
- On a phone, REAL's equity line is squashed into a short band in a tall box (confirms the scope's open question).
- In the paper (light) theme, Webull's strategy sparklines draw as solid black shapes.
- On a phone, NT8's data-feed warnings push the chart down by about a screen.
