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
- `spread_r1.py` — SPREAD r1: NQ vs ES dollar-neutral relative value, 12 pre-registered cells (`PREREG_SPREAD_R1.txt`), pre-lockbox only.
- `PREREG_TRANSFER_R1.txt` + `DATABENTO_TRANSFER_R1.md` — TRANSFER r1 (2026-09-28, pre-registered, not run): ORB / NOISE / TTM crowns unchanged on ZN / 6E / CL / GC; the Databento data spec, exact price and the owner's account/key steps. **SHELVED 2026-09-30 (owner declined Databento).**
- `PREREG_ALPACA_R1.txt` + `ALPACA_STAGE_R1.md` — ALPACA r1 (2026-09-30, staged, nothing runs until the owner saves the free keys): stocks-in-play ORB and the NQ breadth trigger, the owner's key steps and the loader interface.
- `PREREG_REVERT_R1.txt` + `r6_revert.py` — REVERT r1 (2026-09-30): fade a failed new high / low of the day. `P` = price-only Stage A on the ADJ RTH masters, pre-lockbox (DEAD); `F hist` = the order-flow (absorption) variant on the 10-second capture, descriptive; `F forward` = the forward shadow from 2026-10-01 (prints trade counts only until 150 pooled trades, then the pre-registered read). `B` = lockbox, refuses without an A2 pass.
- `PREREG_VOLCARRY_R1.txt` + `r7_volcarry.py` — VOLCARRY r1 (2026-09-30) - DEAD at Stage A (ledger 2.39): the volatility risk premium as a book leg (-0.5x short VIX futures via VIXY, held only while the VIX curve slopes upward). `fetch --owner-ok` = the one-time free Yahoo pull (only after the owner's OK); `A` = parity + Stage A + A2, pre-lockbox; `B` = lockbox once.
- `build_ndx_members.py` (+ `tools/data/ndx_members*.csv`, `ndx_members_wikipedia.json`) — point-in-time Nasdaq-100 membership for NQBRD, from the Wikipedia list in force on the first of each month (2016-06..2026-07).
- `r5_nqbrd.py` — ALPACA r1 family B (NQ breadth trigger): `pull` (needs the owner's Alpaca keys; 09:30-10:00 bars of each day's members into `C:\EdgeLog\alpaca_cache`), `A` = Stage A + A2 pre-lockbox, `B` = lockbox once.
- `r5_siporb.py` — ALPACA r1 family A (stocks-in-play ORB): `probe`, `assets`, `daily`, `open5`, `min1 top|twin|est` (all need the owner's Alpaca keys), `A` = replication + Stage A + A2 pre-lockbox, `B` = lockbox once; `smoke DIR` = offline self-test on synthetic data.
- `PREREG_TRANSFER_R2.txt` + `r8_transfer_etf.py` — TRANSFER r2 (2026-09-30, pre-registered, not run): the crowns unchanged on ETF proxies with free Alpaca data. Order: `ttmcheck` (runs now on ES; passes), `pull` (needs keys; registers fund masters via the shared loader and checks NQ / ES lookups do not move), `gates`, `A`, then `B --ledger-ok` and `C` only after passes; `smoke DIR` = offline self-test.
- `PREREG_REVERT_R2.txt` + `r9_postclose.py` — REVERT r2 (2026-09-30): fade the last ten minutes of the cash session in the futures' first quarter hour after the close; `A` = Stage A + A2 pre-lockbox (DEAD), `B` = lockbox once.
- `IDEAS_R4.md` — round 4 (2026-09-28): ten new-family ideas vs BOOK #463; three triaged, all dead (ledger 2.33).
- `r4_book463.py` — BOOK #463's daily leg P&L (at close + valued daily), reproduces the frontier lane's 60.34 / 164.76 exactly.
- `r4_triage.py` + `PREREG_WKND_FOMCWK_R1.txt` — WKND (weekend gap) and FOMCWK (FOMC-cycle weeks) Stage A, pre-lockbox only.
- `r4b_earn.py` + `PREREG_EARN_R1.txt` — EARN (overnight after mega-cap earnings evenings) Stage A, pre-lockbox only.
- `seam_leg.py` — contract-roll stitch P&L crossed inside a multi-day leg's trades.
- `rank.py` — ranks runs_roc.json by walk-forward ROC/yr.
- `rank_ml.py` — ranks runs_ml.json (tilts/keel/hybrids) by walk-forward ROC/yr.
- `book397_daily.py` — rebuilds frontier book #397's (or another run's) leg daily P&L from book_jobs.json.
- `pull_runs.py` — Firestore pull: every run's walk-forward block + lockbox -> runs_roc.json.
- `pull_ml.py` — Firestore pull: every run's ML rows (tilts/keel/hybrids) -> runs_ml.json.
- `pull_jobs.py` — Firestore pull: book job docs (#396/#397/#372) -> book_jobs.json.
- `pull_books.py` — Firestore pull: book summaries (#396/#397/#372/#366/#379) -> books.json.
