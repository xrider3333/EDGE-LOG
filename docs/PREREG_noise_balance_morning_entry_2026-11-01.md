# PREREG - NOISE #382 balance-morning ENTRY filter (test 244 follow-up, MANAGER #155, 2026-11-01)

Written and locked BEFORE any number of this test is computed.

## Question
Test 244 (profit lock round 4, M5) found #382's giveback concentrates on BALANCE mornings. Asked as an ENTRY question:
does #382 take worse trades after 11:00 on balance mornings, and does skipping them beat the leg as it is?

## The one cell (no grid)
- **Morning efficiency** exactly as `C:\EdgeLog\_anatomy_cache\t244_lock2\lock2.py` `features()` computes it:
  |close of the 18th RTH bar (10:55-11:00) - open of the first bar (09:30)| / (high - low of those 18 bars).
- **Balance morning** = efficiency < **0.55** (M5's own threshold, not re-chosen).
- **Causal:** the value is known only at the close of the 10:55 bar (11:00). The filter acts only on entries whose
  entry bar is the 19th bar of the session or later (fills at/after 11:00). Those entries are SKIPPED on balance
  mornings. Entries before 11:00 are untouched on every day.
- Nothing else changes: same trades, exits, size, cost 0.533 pts, one round trip.

## Data
The t74 rebuild of #382's walk-forward chain (`C:\EdgeLog\_anatomy_cache\t74_giveback\chain_382_mfe.csv`, parity
checked by lock2's `run_leg` path: MFE re-computed from the master, >= 99% match or refuse). About 0.5% off the
stored #382 trades; both arms use the same trades. Walk-forward stretch only; the master is loaded only up to the
optimize window end and the run refuses if a bar reaches the lockbox start (2025-07-16). **Lockbox unread.**

## Reading rule (as test 242)
The filter is a lift only if ALL hold:
1. WF ROC@30k above hold AND WF Sortino above hold;
2. folds won >= 5 of 8 (fold $ above hold's fold $);
3. not one episode (worst DD <= 1.3 x DD5 on the filtered curve, or hold's flag unchanged).
Prior about 15%.

**The lead came from the SAME tuned chain (test 244 M5).** So this check can kill the idea but cannot confirm it;
only forward trades or the lockbox could, and the lockbox stays unread. A pass here means "worth a forward watch",
never "change the live leg".

## Also reported (descriptive, not part of the verdict)
Entries at/after 11:00, balance vs trend mornings: count, average $/trade after cost, win rate, average MFE (pts),
average giveback (MFE - final, pts). Entries before 11:00 shown as a third row for scale.

## Outputs
`tools/noise_balmorn_entry.py`, `C:\EdgeLog\_anatomy_cache\t244_balmorn\result.json`,
`docs/RESULTS_noise_balance_morning_entry_2026-11-01.md`.
