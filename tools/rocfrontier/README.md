# tools/rocfrontier

Research drivers from the 2026-09-24 ROC frontier hunt. Results: RESEARCH_LEDGER.md rows 1.15, 2.12-2.19.

Run every script from the shared checkout (`C:\Users\xride\OneDrive\Desktop\EDGE-LOG`) — they import
`augur_engine`/`augur_strategies` from there. Data/output cache (outside git):
`C:\EdgeLog\_anatomy_cache\rocfrontier` (override with env var `EDGELOG_ROCFRONTIER`).

Order: `make_daily.py` first (builds the daily CSVs the scans read), then the scans; `feats.py` before
`wf_model.py`; `rebal_scan.py` before `rebal_book.py`; the `pull_*.py` scripts are each one Firestore
read and can run any time.

- `make_daily.py` — builds NQ/ES daily RTH OHLC + roll-seam flags into the cache.
- `hod_scan.py` — hour-of-day drift scan on NQ 5m ETH.
- `flow_scan.py` — overnight/late-day/European-morning flow mechanism scan.
- `crash_short_scan.py` — crash-regime NQ short as a hedge leg for book #397.
- `feats.py` — causal intraday feature table for the standalone walk-forward model.
- `wf_model.py` — yearly-refit xgboost walk-forward model on feats.py's table, vs. baselines.
- `rebal_scan.py` — month-end pension-rebalancing scan (SPY-vs-TLT spread) on NQ/ES.
- `rebal_book.py` — tests the rebalancing leg added to frontier book #397 at matched drawdown.
- `rebal_intraday.py` — where inside the day the month-end flow lands (spread across the session, not a closing-hour flow).
- `engudq_regime.py` — regime-gated ENGU-Q short mirror, pre-lockbox only (loads the frozen `ENGUDQ_1M_ETH_1_0.py` copy in the cache).
- `seam_leg.py` — contract-roll stitch P&L crossed inside a multi-day leg's trades.
- `rank.py` — ranks runs_roc.json by walk-forward ROC/yr.
- `rank_ml.py` — ranks runs_ml.json (tilts/keel/hybrids) by walk-forward ROC/yr.
- `book397_daily.py` — rebuilds frontier book #397's (or another run's) leg daily P&L from book_jobs.json.
- `pull_runs.py` — Firestore pull: every run's walk-forward block + lockbox -> runs_roc.json.
- `pull_ml.py` — Firestore pull: every run's ML rows (tilts/keel/hybrids) -> runs_ml.json.
- `pull_jobs.py` — Firestore pull: book job docs (#396/#397/#372) -> book_jobs.json.
- `pull_books.py` — Firestore pull: book summaries (#396/#397/#372/#366/#379) -> books.json.
