# RESULTS - test 240 parts (b) + (c), NOISE #382: regime-gated trails and vol-scaled partials - NO LIFT (0 of 12)

Prereg: docs/PREREG_noise_t240_timedecay_2026-10-31.md (locked v1 sha 29fb732423d9, pushed 9606e01e before this ran).
Tool: tools/noise_t240_regime_exits.py. Files: C:\EdgeLog\_anatomy_cache\t240\{full_bc,chain_bc,verdict_bc}.csv.
Part (a), the time-decay trail Auto-Validate, is job CO9CS1XtXevohTdujzsi (queued behind test 196); read separately.

## Verdict line - #382's crown run once 2010-06-07..2025-07-15, lockbox never loaded
OOS = 2022-01-01..2025-07-15 (1,016 trades), IS = 2010-06-07..2021-12-31 (3,496 trades).

| Cell | OOS ROC@30k | OOS DD5 | OOS DD% | OOS Sortino | OOS net | OOS years won | IS ROC@30k | MFE kept (OOS) |
|---|---|---|---|---|---|---|---|---|
| HOLD (#382) | 129.3 | $17.5k | 10.2 | 4.30 | $318k | - | 41.2 | 15.8% |
| G2+E1 VWAP-slope-gated ATR trail (closest) | 134.9 | $15.3k | 10.1 | 4.59 | $324k | 2/4 | 20.9 | 15.6% |
| G3+E5 ES-gated BE + trail | 140.6 | $14.5k | 9.5 | 4.26 | $312k | 3/4 | 33.8 | 15.4% |
| G2+E5 VWAP-slope-gated BE + trail | 140.0 | $14.5k | 9.7 | 4.24 | $311k | 3/4 | 28.2 | 15.3% |
| P0.75/1-3 partial 1/3 at 0.75 x day range | 130.0 | $17.1k | 10.1 | 4.23 | $313k | 0/4 | 41.9 | 15.4% |

- **0 of 12 cells pass.** Every gated trail beats hold on OOS ROC, but each fails another clause:
  - G2+E1 is the only cell that also beats hold on OOS Sortino and nets more. It wins only 2 of 4 OOS years, loses
    half the IS ROC (20.9 vs 41.2), and carries the one-episode flag.
  - The BE+trail cells' ROC lead is a smaller drawdown with LESS money (the 239 pattern), and their Sortino is lower.
- **Vol-scaled partials:** all 6 lose OOS money and win 0 of 4 years; the tighter the target, the worse (0.25 x range:
  ROC 105-114). The 0.75 x range cell barely touches trades (91 of 1,016) and is a wash.
- **No cell keeps more of the best open profit** than hold (15.8%); the gates do not change the giveback (median ~0.47R).

## Second line - test 74's WF-chain rebuild (2016-10..2025-07, ~0.5% off #382's stored trades, both arms alike)
HOLD 62.2 / $18.0k / 6.46% / 3.04. G3+E1 (ES-gated ATR trail) 72.2 / $15.5k / 6.03% / 3.18, 5 of 10 years, nets $5k
LESS; G2+E1 66.4 / $15.9k / 6.14% / 3.34, 7 of 10 years, nets +$16k but one-episode flagged. Not the verdict line; both
fail the verdict line's IS clause.

## Read
Gating the trail on a trend day removes most of the damage trails did in 239 (IS losses shrink, OOS ROC rises), but it
still does not add money in both halves: the gate cannot tell, at the time it acts, a dip that runs to the close from a
real reversal. G2+E1 is the one shape worth keeping an eye on (VWAP slope with the trade, then a 3 x ATR trail); it is
not a pass and nothing changes. Nothing live, paper or in BOOK #463 changes.
