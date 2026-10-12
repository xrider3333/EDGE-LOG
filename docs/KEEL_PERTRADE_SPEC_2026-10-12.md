# KEEL per-trade live update - the exact walk spec (Custom ML for PAPER-WB, 2026-10-12)

Owner 10-12 via MANAGER #102: live KEEL on Webull NOISE #382 = the backtest **exactly**. PAPER-WB builds the
per-trade push; this file is the math and the proof it must match.

## The backtest (what "exact" means)
- `augur_engine.ml_keel.keel_walk(arrays_NQ, trades_382, version="v12")`, seed 42: run #382's Auto-Validate KEEL row.
- For trade k (entry order), the ledger is every #382 NQ trade with **exit bar < k's entry bar**.
- **Refit:** when 25 more trades have closed since the last fit (REFIT_EVERY), on the whole ledger, with recency weights exp(-age/400).
- **Ensemble score:** each member's z is trust-weighted by its own 600-trade dollar ledger.
- **Trust:** the skill trust times a 50-trade fast cut. The shade applies when fast t < -0.5 and z != 0.
- **Fixed tilts, then size:** Friday x1.5, squeeze x1.5 (cap 3.0), then FOMC morning x0.5.

## What closes the gap
- **Today's live state is NIGHTLY.** A 2nd/3rd entry on a day misses that day's earlier NQ exits. DISC's replay found 557 of 4,873 trades size differently, by a mean of 0.18x when it happens. It is zero today (trust 0) but real when trust is on.
- **New:** `ml_keel.keel_append_trade(state, x_row, pnl, entry_bar, exit_bar)` advances a state by ONE closed trade. It is exactly one more pass of the walk's loop, and returns a NEW state; the input is untouched.

## The contract (all four, or it is not exact)
1. **Append in entry order, after the exit, one trade at a time.** #382 never overlaps itself (0 overlap or same-bar pairs over 4,873 trades); the replay re-checks this.
2. **`x_row` = `keel_features` on the NQ 5m arrays at the trade's ENTRY bar** (20 columns, names must equal `state["feature_names"]`). **`pnl`** = the trade's P exactly as `tools/keel_live_state.run_nq_backtest` gives it (the walk's own units: points, after cost 0.533).
3. **Same-bar rule:** a live entry whose entry bar is the bar an NQ trade EXITS on is scored with the state BEFORE that trade is appended (the walk's strict `<`). Keep the previous state in memory for this one case. It was never seen in #382, but code it.
4. **Score unchanged:** `keel_score_from_state(state, arrays, entry_bar, x_row=row, cross_series=True)`. For the backtest's own size the row is the **NQ** entry bar's. Live today passes the QQQ row; DISC measured that as mean 0.03x, max 0.40x while trust is on (item 2 of the difference list, an owner call).

## Pipeline (proposal - PAPER-WB owns the build)
- **PC, intraday:**
  - Run #382 on the NQ 5m no-adjust master, the same file the nightly push carries, after each NQ bar.
  - When a #382 trade CLOSES, push `{leg: "NOISE_382", entry_ts, exit_ts, pnl, x_row[20], feature_names, master_sha, n_before}` to the box. `n_before` = how many trades the PC's walk holds before this one.
  - Same data file as the nightly push, or the nightly rebuild and the appended state disagree (DISC: box vs PC masters differed on 10-08/09 opens by up to 2.25 pts).
- **Box, on receipt:**
  - **Refuse** (log, alert) if:
    - `n_before != state["n"]` (a push was missed or duplicated);
    - `entry_ts <=` the last appended trade's `exit_ts`;
    - the feature names differ;
    - the trade's day is not after the state's `data_through`.
  - **Otherwise:** `state = keel_append_trade(...)`, then write it atomically (tmp + os.replace) as `NOISE_382_v12_intraday.joblib`. The scorer prefers the intraday file when its `data_through` matches and it reloads by mtime (the scorer already does).
- **Nightly 18:30 ET:** the full rebuild stays the anchor. **Before overwriting, compare the day's appended state with the rebuild**: n, n_fits, fitted_on, the last z / trust / t_fast_now to 1e-9. A mismatch = alert (data or push problem), never silent.
- **Missed push at entry time:** still score (nightly behaviour), but mark the entry `ledger_behind=N` so the parity report can count it.
- **Library:** exact parity also needs the box on scikit-learn **1.6.1** (the backtest's), per DISC's addendum 2. Otherwise ExtraTrees z differs by up to 0.023 (about 0.03x size).

## The proof
- **Tests** (`tests/test_ml_keel_state.py`, section 4):
  - From an EMPTY state, score-then-append every synthetic trade. Every size equals `keel_walk` to 1e-12 (warm-up, every refit, Friday, squeeze and FOMC included).
  - The final state equals a fresh `keel_build_state` (ledgers, refit count, models).
  - The same holds from a mid-walk state, and the input state is not modified.
- **Replay on the real #382 history:** `python tools/keel_pertrade_replay.py [--from YYYY-MM-DD]`.
  - It builds the morning state, then scores each NQ trade and appends it after it closes, for every trade. It compares against `keel_walk` trade by trade and prints the nightly design's gap beside it.
  - Exit 0 = exact on every trade. CSV: C:\EdgeLog\custom_ml\keel_pertrade\replay_NOISE_382.csv.
- **PAPER-WB's wiring check:** feed the replay's trade sequence through the box handler (push payloads built from the same arrays) and assert the handler's states give the replay's `live_size` column to 1e-12.

## Addendum 1 (2026-10-12 afternoon) - the owner chose the LIVE QQQ trades as the feed (MANAGER #106, PAPER-WB #107)
- **Units (confirmed):** P = (Webull P&L of record / shares) x plugin size (engine size / keel_size) x (NQ close / QQQ close, prior session).
  - The walk's P already carries the plugin size (pts = s*raw - (s-1)*cost).
  - Replay sanity: QQQ trades in NQ-point terms have median |P| 25.3 vs the NQ ledger's 29.2.
  - A missing price ratio would read about 0.6, so this is a cheap units alarm.
- **Cut:** the nightly NQ state of the cut night, then QQQ trades appended. No backfill of 09-24..10-12 (rows never persisted; trust 0 on both).
- **How far a QQQ-fed state drifts from the NQ-fed backtest** (scratch replay, 9 cut-years 2017-2025, each 12 months; both states score the same QQQ entries):
  - **Sizes:** sizes differ on **56%** of entries, mean **0.21x**, p95 0.79x, p99 1.5x, max 2.25x. The branch differs on 21%.
    - This happens only when trust is on in either state; both are at trust 0 today.
  - **Growth over time:** the drift grows with time since the cut.
    - Nightly |trust_now| difference p99: 0.41 (months 0-3), 0.56 (3-6), 1.00 (6-12).
    - |t_fast_now| p99: 1.5 / 2.1 / 1.9.
  - **Money:** the feed's effect is -464 NQ pts over 9 years (about -$1k a year at one contract). The sign is mixed by year (-828 to +580), so there is no edge either way.
  - **Plain reading:** once trust turns on, a QQQ-fed KEEL is NOT the backtest. It sizes about half the entries differently within 3 months. It costs nothing measurable, and it cannot stay "exact".
- **Alert design** (natural drift is too large for a drift alarm to catch bugs):
  1. **EXACT (alert):** nightly, rebuild the live state from the cut state plus the persisted QQQ rows, and compare to the live state to 1e-9: n, n_fits, fitted_on, trust_now, t_fast_now, last z. Any miss = plumbing bug.
  2. **UNITS (alert):** the median |P| of the last 20 appended trades must be within 0.5x-2x of the median |P| of the NQ ledger's last 600.
  3. **DRIFT (report, not alert):** log live vs NQ-reference trust_now / t_fast_now / branch nightly.
     - Note it only when outside the envelope above for its months since the cut: |trust| > 0.41 (0-3), > 0.56 (3-6); none after 6 months.
     - Or note it when an entry's size differs by more than 1.5x.
