# docs/anatomy

## How to point this at a past run

- `python tools/trade_anatomy.py --run 314` replays run #314's own crowned parameters on its own window and costs (repeatable: `--run 314 --run 309`). `--job <backtests-doc-id>` points at a job doc directly. `--leg <KEY>` runs one of the hard-coded legs in feature_board.LEGS; `--list` prints those keys plus this usage line.
- DISCOVERY / HOLDOUT is a hard split by calendar date, not trade count: only the first 60% of the leg's pre-lockbox span is mined below. The remaining 40% (holdout) is touched exactly once, as a single pre-registered check. Lockbox trades (the leg's own last N months) are never loaded here at all.
- Nothing on this page is a finding by itself. A rule only means something once it clears the TOTAL-MONEY ledger in section 2c (not the per-trade averages in sections 1/2 -- that section explains the trap) AND has passed a fenced Auto-Validate with walk-forward and lockbox checks. Never adopt a rule straight from this report.

