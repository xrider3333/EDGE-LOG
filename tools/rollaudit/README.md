# tools/rollaudit - reproduce ROLL_AUDIT.md (2026-09-25)

Research kit, not shipped code. Nothing here is imported by a strategy, the runner or a paper leg.

- `ground_truth.py` - rebuilds the exact NQ/ES contract switches from `databento_raw/` with the masters' own
  stitch rule (`tools/stitch_databento._active_by_day`). 64 switches per root 2010-06..2026-03; the raw files
  end 2026-06-05, so the two later rows are marked `inferred_after_raw_end` and are NOT trustworthy (the audit
  found both 2026 rolls are in-bar splices: 2026-06-15 03:30/05:30 ET and 2026-09-14 11:30 ET).
  The committed tables are `tools/data/contract_switches_NQ.csv` / `_ES.csv`.
- `detector_accuracy.py` - how often the house `detect_roll_seams` finds the real switches, per data type.
- `rollaudit_lib.py` - `load_switches`, `adjusted_arrays` (Panama back-adjust by the true contract offsets),
  `true_detector` (drop-in for `detect_roll_seams`), `stitch_points` (per-trade roll offset booked as P&L).

The per-group scripts and outputs of the audit live outside git in `C:\EdgeLog\_anatomy_cache\rollaudit\work\`
and `work2\`.
