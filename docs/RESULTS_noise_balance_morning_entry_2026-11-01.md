# RESULTS - NOISE #382 balance-morning ENTRY filter (test 244 follow-up, 2026-11-01)

Prereg `docs/PREREG_noise_balance_morning_entry_2026-11-01.md`, locked 34c391e7f49d and pushed e09e87d9 BEFORE this ran.
Tool `tools/noise_balmorn_entry.py`; record `C:\EdgeLog\_anatomy_cache\t244_balmorn\result.json`.
Data: t74 rebuild of #382's walk-forward chain (2,345 trades, MFE parity 100%, ~0.5% off the stored trades), cost 0.533,
WF stretch only, lockbox unread.

## Verdict: NO LIFT - and the idea points the wrong way. Nothing live changes.

| WF chain 2016-25 | ROC@30k | DD5 | DD% | Sortino | Net | Folds won |
|---|---|---|---|---|---|---|
| Hold (leg as is) | 62.25 | $18.0k | 6.46 | 3.04 | $401.5k | - |
| Skip after-11:00 entries on balance mornings | 40.76 | $17.1k | 10.32 | 2.46 | $266.3k | 1/8 |

- The filter skips 412 trades (45.6 a year) and throws away $135k (-$15.0k a year). It wins 1 of 8 folds.
- Neither curve is one episode.

## Why (descriptive)

| Entries | n | Avg $/trade | Win rate | Avg MFE pts | Avg giveback pts |
|---|---|---|---|---|---|
| After 11:00, balance morning (eff < 0.55) | 412 | $328 | 47.6% | 54.3 | 42.4 |
| After 11:00, trend morning (eff >= 0.55) | 671 | $83 | 37.1% | 26.2 | 23.0 |
| Before 11:00 (untouched) | 1,262 | $167 | 34.9% | 52.7 | 47.0 |

- Balance mornings are where #382 earns most after 11:00: highest $/trade and win rate of the three groups. A mean-
  reversion-to-VWAP leg is supposed to do best on a balance (rotational) day.
- They also show big givebacks in POINTS because their MFE is twice the trend-morning MFE: the giveback is the price of
  the larger moves, not a sign of bad trades. That is how test 244's M5 lock looked good: it cut a few faded winners
  on the leg's best days, it did not find bad trades.
- If anything, trend mornings are the weaker after-11:00 entries ($83/trade, 37% wins); that is a NEW observation found
  here and is not tested (it would need its own prereg, and it is still a split on the same tuned chain).

## Caveat
The lead came from the same chain (test 244 M5), so a pass could only have been a lead; a fail closes it.
