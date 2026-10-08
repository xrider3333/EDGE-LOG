# ENGINE ROLL GUARD (2026-10-08)

Owner ask 10-08, relayed by MANAGER #54: "fix so this doesn't happen again." The design follows MANAGER #57 and the ruling #58 on TTM's review #56. Code: `augur_engine/rolls.py`, with the plan section starting at "THE ROLL PLAN".

## What a run on an NQ / ES tape now gets

| Master | File | What the strategy sees | Fills / P&L | Crossing a switch |
|---|---|---|---|---|
| unadjusted (`db_noadj_*`, tv, yahoo, blank; MNQ / MES too) | point logic: trades unchanged under a +C price shift | **difference-adjusted** series (Panama, from `tools/data/rolls_<ROOT>.csv`, = the db_adj master) | raw contract prices; P&L exact, roll step out | allowed (roll-clean) |
| unadjusted | % logic: changes under shift, unchanged under a x k scale | **ratio-adjusted** series (each switch's offset as a ratio to the old contract's last close) | re-priced to raw: entry / exit divided back by the bar's factor, roll step out, metrics re-derived | allowed (roll-clean) |
| unadjusted | neither (reads levels), `ROLL_SIGNAL = "raw"`, `roll_treatment="raw"`, or no trades in the test | raw prices + the true seam calendar | raw | **REFUSED** |
| unadjusted | ROLL_AWARE (NQDIP 1.2-1.4, pinned by sha256) | raw; the file removes the offset itself | the file's own | allowed |
| `db_adj_*` / `db_fadj_*` | any | the master | the master | allowed; **refused if the master is stale** (a table switch after its build); a level/% file is **warned** in the stamp |
| futures root with no roll table (CL, GC, ZN, RTY, YM ...) | any | - | - | **REFUSED** |
| no instrument in `arrays["meta"]` | any | - | - | **REFUSED** unless meta says `roll_mode = "none"` (synthetic / stock tapes) or `"live"` (set by `api/cloud_signal.closed_arrays`, the live bar builder; reported only) |

Live, paper and nightly-shadow paths are never refused and never changed. That means calls that come through `api/{cloud_signal, paper, gate_live, book_shadow, etf_book_shadow, noise_forward, qqq_exec, nt_sync}`, or through these `tools/` scripts:
- `keel_live_state` and `backfill_keel`: the live KEEL state, fitted on the NQ legs' backtest trades, so a planned run would change live sizing;
- `paper_forward`, `paper_gate_calibrate` and `qqq_paper`;
- the forward reads `noise_forward_log`, `dip_forward_read`, `orb_rollweek_forward` and `orb_orderflow_shadow`. They run raw and the stamp records what they held across (MANAGER D2). Proposed hard date: the Dec 2026 roll (TTM #56 point 8), which is MANAGER's call.

## The signal method

- **Declared:** a strategy file may say `ROLL_SIGNAL = "difference" | "ratio" | "raw"`. The engine checks a declared method with its own test and refuses it if more than 1% of the file's trades move.
- **Found by test** (`rolls.invariance`, whole window): the file is run on raw prices, on raw + C, and, only if that moves trades, on raw x k.
  - C is a whole number of points: the largest back-adjust shift in the window, and at least 500.
  - k is at least 1.5.
  - No change under +C means difference. Otherwise, no change under x k means ratio. Otherwise the file runs raw.
- **Caching:** the result is cached once per (file content, master, window) with the first parameter set seen, so a sweep pays for the test once. A parameter that switches level logic on mid-sweep is not re-tested. The saved run's raw-vs-adjusted check below is the backstop.

## The roll stamp (every saved NQ / ES run; books per leg + total)

- master type and source;
- roll source (table + sha);
- calendar (the plan kind);
- signal method and who chose it (declared / test / master), with the test scores;
- switches in the window (estimated ones counted);
- trades crossing a true switch, and their $;
- $ of pure roll step booked (0 when roll-clean);
- $ booked on switch sessions;
- synthetic no-fill bars;
- any warning;
- `raw_vs_adjusted` (TTM's check, run for every saved run via `run_backtest(roll_diff=True)`):
  - the same file on raw prices, trade by trade against the planned run;
  - it separates trades moved by the file's own **roll-day skip** (no step to skip on adjusted prices) from trades moved by **price**;
  - price moves are split into those near a switch (within 20 sessions, or held across one: signals that read the roll step, now removed) and those elsewhere (level reading, or a knock-on in a file that carries state).

## Every engine path

All of these run inside the plan:
- `engine.run_backtest` (runner, blotter, server, book legs);
- the slice evaluator (Auto-Validate and its parallel folds);
- `run_auto` champion and report panels;
- `run_grid`, single-thread and process pool;
- the grid winner's ensemble, regime and neighbour panels;
- `window_delta`.

Also:
- Planned arrays that are cut afterwards (slice, boolean mask, IS/OOS split keeping meta) get the plan restricted to their bars by timestamp.
- The trial-cache key carries `roll_guard = "v3|<kind>|<table sha>"` for NQ / ES jobs only; other jobs' keys are unchanged.

## The one seam calendar and the ship lint

- The 25 strategy files that carried their own `detect_roll_seams` now import `rolls.seam_days` (the table's calendar; no strategy logic change). Outside a roll context it refuses, with a plain message.
- `tests/test_roll_detector_lint.py` runs in the pre-push suite. It fails a ship that defines a roll detector outside `rolls.py`:
  - by name, by the retired signature, or by the retired algorithm's fingerprint (quarterly months + abs + max);
  - nested defs count.
- In `augur_strategies` / `augur_engine` / `api` it also fails:
  - assignment or lambda bindings of a detector name;
  - imports of one from anywhere but `augur_engine.rolls`;
  - strategy imports from `tools/`;
  - getattr / exec / eval reaches.
- New or changed `tools/` files are checked against origin/main. Named exemptions, each with its reason:
  - `data_quality.roll_seam_check`: an audit tool;
  - `setup_kit.contract_switch_sessions`: the SETUPS harness. Found by the fingerprint; flagged to MANAGER for its lane to move onto `seam_days_for`.
- Research harnesses that simulate positions themselves (`tools/*_stageA.py`) call `rolls.assert_no_crossings(entry_times, exit_times, instrument, source)`.

## Real-data checks (NQ 5m RTH, 2016-07 .. 2025-06, cost 0.533 pts)

| Run | Before | Now |
|---|---|---|
| ORB #314 adj | 1286 tr, 15,429.437 pts | identical |
| ORB #314 noadj | 1286 tr, 15,429.437 pts | identical, difference-adjusted; raw-vs-adjusted "identical" |
| TTIBS_1_0 noadj | 347 tr, 5,752.8 (raw, roll-day skip) | 352 tr, 6,294.134 = the db_adj master to the cent; all differences from its roll-day skip |
| RSIDIV_1_0 noadj (to 2026-06) | 2401 tr, 14,572.0 | 2425 tr, 15,945.0; 33 trades moved by price, all near switches |
| NQDIP_1_2 noadj | roll-aware | unchanged (34 crossings, its own offset removal) |

## Hardening after TTM's attack on v4 (2026-10-08, 7 holes, lint 14 evasions)

- **Roll-aware trust:** a file is trusted only when the module that will run IS the pinned file. Every function and simple module-level constant must match a fresh compile of it. A module rebuilt in memory that borrows the file's name and `__file__` is not trusted.
- **Instrument aliases:** NQ1!, /NQ, NQZ6, NQ=F and similar resolve to their root. A futures-looking symbol with no roll table (CL1!, GC=F, CLZ6, RTY1!) is refused.
- **The label must agree with the prices** (`rolls.label_check`): at each switch with an offset at least 5x the gap noise, an unadjusted series jumps by about the offset and an adjusted one does not.
  - The run is refused when at least 6 such switches are in the window and at least 70% of them contradict the label.
  - Otherwise the stamp says "not verifiable here".
  - On the house masters over full history: no-adj masters are 86-97% raw-like and adj masters 67-97% adjusted-like.
- **Report mode** (`guard_mode('report')`) is allowed only for `tools/roll_guard_probe.py` and the tests. It waives refusals, but signals are still planned, and the stamp says "not a research result".
- **Report-only live paths** are matched by their real path inside this checkout, not by file name.
- **Method-test cache:** keyed by the code that runs (function bytecode, defaults, module constants), so two modules built in memory never share a result.
- **Plans already on the arrays:** a plan that does not adjust is ignored and the run re-planned. An adjusting plan is used only if it fits: root, an on-the-fly source, and the table's own factors for these bars.
- **Lint:** the fingerprint now covers lambdas, module-level code and other spellings:
  - `mo % 3` after `mo = t.month`;
  - `range(3, 13, 3)`;
  - `.quarter`;
  - `maximum(d, -d)`, `sign`, `**2`;
  - nlargest, sort and similar picks.
  
  Detector names are also caught as attributes and as strings, including split strings. Strategies may not use runpy, compile, FunctionType, globals(), sys.modules, exec or eval, or name a tools/ module (tools/data roll-table paths are fine).

## Known limits (said out loud)

1. The method test reads the window it is given. A level threshold no price in the window ever reaches is invisible to it, and harmless in that window.
2. The test is cached per file and window with the first parameter set; `raw_vs_adjusted` on the saved run is the backstop.
3. Level-reading files run raw: their indicators still see the roll step near switches, but their trades can't hold across one. The exact fix is a roll-aware or `ROLL_SIGNAL`-declared version of the file.
4. `db_adj` masters are difference-adjusted. A %-reading file on one is warned, not converted.
5. Bars a switch falls inside (2026 in-bar splices) are rebuilt as bodies and counted as no-fill bars.
6. The label check needs switches whose step stands clear of the gap noise.
   - ETH masters and RTH windows from 2022 on have them.
   - NQ/ES RTH windows before 2022 do not: their roll offsets are smaller than ordinary overnight gaps, so a mislabelled pre-2022 RTH window cannot be told from its prices (TTM attack 5, 2019-20). The stamp says so.
7. Lint: a plain gap-threshold rule with renamed knobs (no quarter cue, no pick) cannot be told from real gap logic. The run-time guard, which feeds such a file jump-free prices, is the backstop.
