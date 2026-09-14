# BACKTEST SPEED - read this before running any backtest, validate or sweep

Owner, 2026-09-14: "add the speed changes that we did to any claude session running a backtest."
This is the one place those changes live. CLAUDE.md points here. Everything below was measured
on this machine (Razer Blade, i7-12800H, 14 cores / 20 threads, 32 GB, external cooling).

## 1. What is already on - use it, do not undo it

| Change | Measured gain | How it is switched on | Off switch |
|---|---|---|---|
| **Compiled hot loops** (`augur_engine/fastloop.py`, Numba `@njit(cache=True)`) in the four ENGU-Q 1-minute files R2-R5 | full-history backtest **7.61 s -> 0.29 s (26x)**, **0 of 1,949 trades differ**; a 900-trial validate took 44.8 min instead of ~6 h | automatic whenever `numba` imports; the Python loop stays underneath as the fallback | `EDGELOG_NO_FASTLOOP=1` (only to re-check a suspicious result) |
| **Walk-forward folds in parallel processes** (`augur_engine/wf_pool.py`) | Stage B 379 s -> 160 s with 3 processes, bit-identical rows | the runner launcher `C:\EdgeLog\_restart_runner.bat` sets `EDGELOG_VALIDATE_WORKERS=3` | code default is **1** - see rule 2 |
| **ML gate + KEEL models fit on ONE thread** (`_GATE_N_JOBS=1`) | gate_validate 151 s -> 60 s, identical output | always on in code; `tests/test_gate_threads.py` fails if someone sets `n_jobs=-1` again | none - do not add one |
| **Trial cache** (#26) | a re-search of a known region is mostly cache hits | launcher sets `AUGUR_TRIAL_CACHE=1` | code default is **off** - see rule 2 |
| **Five job slots** (primary + `EDGELOG_WORKERS=4` drain-only workers) | 5 queued jobs run at once | launcher | each runner refuses new work under 2.5 GiB free RAM |
| **CPU Boost** (Razer Synapse -> Performance -> CPU Boost max, fans max) | idle benchmark **9.13 s -> 8.04 s (+13.5%)** | the owner set it; Synapse keeps it through reboots | the owner's machine setting - **Claude never changes system or hardware settings** |
| **900 trials by default** on Auto-Validate jobs | lower overfit probability on the ENGU-Q A/B (0.603 vs 0.802), more held-out trades | `api/runner.py` job default `n_trials` 900 | pass `n_trials` on the job |

New validates pick all of this up automatically on the runner. A session running code **locally**
only gets the parts that live in code - so follow the rules below.

## 2. Rules for a session running backtests itself (drivers, sweeps, probes, parity checks)

1. **Call the engine, never a hand-written copy of a strategy loop.** Use the strategy file's own
   functions through `run_backtest` / `run_auto` / `run_validate`. A driver that re-implements the
   walk gets none of the compiled speed and is not the parity-tested arithmetic.
2. **Set the launcher's environment before a local run:** `AUGUR_TRIAL_CACHE=1`, and
   `EDGELOG_VALIDATE_WORKERS=3` for a validate (or pass `workers=3`). Without them a local validate is
   sequential and uncached - the slow path the runner stopped using on 2026-09-08.
3. **Run data-reading drivers from the shared checkout** (`C:\Users\xride\OneDrive\Desktop\EDGE-LOG`).
   A worktree has no master registry (`optimizer_history.db` is untracked) and no `serviceAccount.json`.
   Code changes still go through a worktree; only the run itself happens in the shared checkout.
4. **Wrap every multiprocessing caller in `if __name__ == "__main__":`.** Calling `run_validate` at
   module level breaks the spawn pool, and it silently falls back to the in-line (slow) path.
5. **Parallelise across processes, keep each process single-threaded.** `ProcessPoolExecutor`, with
   `OMP_NUM_THREADS=1`, sklearn `n_jobs=1`, XGBoost `nthread=1` inside each worker. Nested thread
   pools inside process pools were two thirds of a validate's time before 2026-09-08.
6. **Check the load first and size to what is free.** `python tools/queue_truth.py` shows the
   runner's jobs; up to five may already be running, each validate using 3 fold processes. A busy box
   ran the same backtest at 16.2 s against 9.1 s idle, so more processes than free cores makes every
   job slower, including the owner's. Leave at least 2.5 GiB free RAM per process (the runner's own floor).
7. **Make long local runs visible.** Wrap the driver in the research beacon so it shows on the top-bar
   dials and in BUILDER instead of an idle-looking queue:
   ```python
   from research_beacon import beacon          # tools/research_beacon.py
   with beacon("ENGU-Q limit x cap grid", total=len(cells)) as b:
       for i, cell in enumerate(cells, 1):
           ...
           b.step(i)
   ```
8. **Keep research caches outside worktrees:** `C:\EdgeLog\_anatomy_cache` (or `EDGELOG_CACHE_DIR`).
   A worktree cleanup has wiped caches before.
9. **Benchmark honestly:** idle box, five repetitions, compare medians; under 3% is noise on this laptop.
10. **Do not restart the runner to "speed things up"** without checking for a job in flight (CLAUDE.md,
    runner restarts). A full restart kills every running job.

## 3. Already tested - do not propose again

| Idea | Result |
|---|---|
| GPU (3080 Ti) | no GPU code anywhere in the engine - zero gain |
| 32-bit prices ("narrow numbers") | 16.57 s vs 16.22 s = 0.98x, dead |
| Cloud compute (Modal) | assessed 2026-09-06: not worth it; job-level concurrency gave the win locally for $0 |
| More trials as a speed trade | trials are a quality setting (900 default), not a speed lever |

## 4. Making another strategy fast (the compiled-loop recipe)

**New strategy files do NOT get compiled speed automatically** - the dials, beacon, fence, cache and
fold parallelism are universal; the compiled walk is per-strategy code.

Only worth doing when one backtest is slow. Measured per backtest: ENGU-Q 1-minute 7.6 s interpreted
(0.29 s compiled); ORB 0.8 s, NOISE 1.2 s, TTM 0.5 s on 5-minute / 30-minute bars - not worth it.

1. Transcribe the trade walk into `augur_engine/fastloop.py` style: line for line, keeping every
   `>=` vs `>` and `max(a, x)` exactly as written - those choices decide trades at the boundary.
2. Keep the original Python loop underneath as the fallback; take the compiled path only when the
   caller asks for nothing it cannot do (no research probes, no stop/pause events), and honour
   `EDGELOG_NO_FASTLOOP`.
3. Parity test in the pattern of `tests/test_fastloop_parity.py`: several configurations run both ways,
   requiring identical trade counts, entry bars, exit bars, entry prices and per-trade profit.
4. Before shipping, run real-data parity over the full history, trade by trade. **If a single trade
   differs, it does not ship** - every crowned run, paper leg and book card was earned by the Python loop.

Sources: commits 2d0a552 (compiled loops), a953167 (parallel folds), 4bdfb63 (one-thread models),
8281313 / dd10247 (multi-worker runner); CLAUDE.md runner-restart rule.
