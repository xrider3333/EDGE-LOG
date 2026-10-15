# SUPERSCALPER r2 EXPLORE (OUR PORT, development data only) - RESULT (TV, 2026-10-15)

Prereg `docs/PREREG_tv_superscalper_r2_explore_2026-10-15.md` (LF sha256 d5e421ac..., witness prereg/tv-ssexplore-1015 @ 661408a1,
pushed before the run); harness `tools/superscalper_explore_r2.py` (26a2f9aa..., checked prereg + port 8566c2c1 at start: OK).
NQ / ES 1m ETH no-adjust, intrabar 'worst', cost NQ 0.706 / ES 0.582 pt. Only 2023 and 2024 read; no lockbox. 230 s.
Four numbers = ROC %/yr at a $30k worst DD, DD5 and DD % from peak at that sizing, daily Sortino (one-year stretches: every one is
flagged "1 episode" - a single year has few drawdown episodes).

## E0 - the r1 pick on the second development year (NQ 2023): DOES NOT HOLD
| cell | trades | win | avg win / loss (net pt) | net PF | stress +0.25 | ROC@30k | DD5 @30k | DD% peak | Sortino |
|---|---|---|---|---|---|---|---|---|---|
| IMPROVED_R1 (file defaults) | 2,311 | 59.0% | 22.22 / 29.83 | 1.071 | 1.050 | 28.6 | $15.8k | 26.1% | 1.13 |
| AS_PORTED | 2,398 | 70.4% | 12.54 / 27.80 | 1.073 | 1.042 | 43.4 | $19.0k | 25.3% | 1.27 |
- The r1 exits do not beat the as-ported exits on an unread year (rule: >= 1.00 AND beats as-ported -> fails the second clause).
  STRATEGY-BEATING's selection-luck read (#127) is borne out: the 2024 lift was the year, not the exits.
- Both cells are PROFITABLE in 2023 (net PF ~1.07): the port itself had a good 2023 and a bad 2024 (as-ported 0.962).

## E1 - time-of-day windows (NQ 2024, file defaults, decomposition; 'any' totals = 'fifo' totals, 3,856.25 pt gross both)
| window (signal bar, ET) | trades | win | avg win / loss | net PF | ROC@30k | DD5 @30k | DD% peak | Sortino |
|---|---|---|---|---|---|---|---|---|
| all | 2,633 | 58.5% | 26.29 / 35.28 | 1.052 | 35.9 | $19.5k | 24.1% | 0.95 |
| W1 open 09:30-10:59 | 172 | 23.8% | 92.26 / 29.82 | 0.968 | -2.6 | $7.5k | 26.3% | -0.22 |
| W2 midday 11:00-13:59 | 222 | 33.8% | 35.48 / 19.29 | 0.939 | -4.8 | $8.8k | 24.9% | -0.47 |
| W3 close 14:00-15:59 | 230 | 21.7% | 58.45 / 16.99 | 0.956 | -6.2 | $16.9k | 29.2% | -0.37 |
| W4 outside RTH | 2,009 | 68.4% | 22.66 / 45.30 | 1.085 | 53.4 | $19.5k | 24.3% | 1.27 |
- No candidate (rule: 2024 net PF >= 1.10 with >= 300 trades) -> nothing read on 2023, no entry-window proposal.
- Shape worth recording: 76% of the trades and all of the profit come from OUTSIDE regular hours; every RTH window loses. The RTH
  windows have only ~200 trades each (the script's RTH gates are strict), far fewer than the prereg's ~650 guess.

## E2 - the port on ES (2024): DEAD
| cell | trades | win | avg win / loss | net PF | ROC@30k | DD5 @30k | DD% peak | Sortino |
|---|---|---|---|---|---|---|---|---|
| a AS_PORTED | 417 | 53.0% | 7.58 / 9.55 | 0.896 | -14.9 | $10.3k | 29.4% | -0.94 |
| b IMPROVED_R1 | 408 | 34.3% | 14.31 / 8.19 | 0.913 | -16.3 | $11.2k | 28.9% | -0.73 |
| c IMPROVED_R1 + ES-scaled point knobs | 2,228 | 60.8% | 5.27 / 8.67 | 0.942 | -17.0 | $17.1k | 28.6% | -0.86 |
- No candidate (rule: net PF >= 1.05 with >= 500 trades). The NQ-point thresholds starve ES of trades (a, b); scaling them (c)
  restores the count and still loses after ES's 0.582-pt cost.

## For the queued validate
- Labelled: "r1 pick did not hold on 2023" (the validate still runs - owner order; it searches the full ranges, the defaults only
  anchor it). Its walk-forward read prints the folds overlapping 2023 AND 2024 apart, plus the chain without them.
- What is different from the 10-12 scalp hunt: the port is a confluence design that made money in 2023 under both exits - but its
  2023-2024 record is one good year and one bad one, and the r1 exit change is not real.
