# REPORT COMPLETENESS — why recent Auto-Validates show an empty section 2

Owner, 2026-08-23, on run #226: *"why do i only see one raw config … where is the parallel
coordinates chart with the PDP underneath it … your liberties to take shortcuts are preventing
me from seeing the bigger picture."*

This file is the answer, the audit behind it, and the standing rule so it does not recur.

## 1. What happened (plain language)

An Auto-Validate has two halves:

- **Section 1 — the verdict.** One champion config: equity curve, walk-forward folds, lockbox,
  Monte-Carlo drawdown, stress, regime card, ML gate bake-off. Needs only ONE config.
- **Section 2 — the bigger picture.** The *population* of configs the search visited: 2B/2C
  scatter, 2E 3-D surfaces, **2F parallel coordinates with the 2G PDP underneath**, 2H knob
  importance, 2I neighbour robustness, plateau pick, surrogate, DSR / PBO. Needs MANY configs.

Since 2026-08-12 every validate on this project's crowns was queued on a **pinned "card" file**
(`*_FROZEN`, `*_LIM50`, `*_ER25`, `ORB_3_4_C221`, `NOISE_1_1_SBS`): a strategy file whose
DEFAULT_PARAMS carry no ranges, so discovery evaluates exactly one config
(`n_evaluated = 1`, `points = 1`). Section 1 is complete on those runs. Section 2 has nothing to
draw, because nothing was searched. The shortcut was taken to reproduce a *certified* config
bit-for-bit and to spend the engine time on the gate bake-off instead of a search. It delivered
the verdict and threw away the landscape.

## 2. The audit (run docs read from Firestore 2026-08-23)

| run | strategy file | discover | configs | neighbours | plateau | surrogate | relationship | DSR | PBO | gate bake-off |
|---|---|---|---|---|---|---|---|---|---|---|
| #137 | ORB_SIMPLE_1_0 | auto | 300 | yes | – | – | yes | yes | – | – |
| #149 | ENGUQ_1M_1_0 | auto | 29 | yes | – | – | – | yes | – | – |
| #170 | TTIBS_1_0 | auto | 171 | yes | yes | yes | yes | yes | yes | yes |
| #174 | TTIBS_1_0 | auto | 171 | yes | yes | yes | yes | yes | yes | yes |
| #225 | NOISE_1_0 | auto | 300 | yes | yes | yes | yes | yes | yes | yes |
| **#226** | ENGUQ_1M_ETH_**FROZEN** | auto | **1** | – | – | – | – | – | – | yes |
| #230 | ORB_3_4_**C221** | auto | **1** | – | – | – | – | – | – | yes |
| #241 | NOISE_1_1_**SBS** | auto | **1** | – | – | – | – | – | – | yes |
| #249 | ENGUQ_1M_ETH_**LIM50** | auto | **1** | – | – | – | – | – | – | yes |
| #265 | ENGUQ_1M_ETH_**ER25** | auto | **1** | – | – | – | – | – | – | yes |

"configs" = `n_evaluated` / length of `points`. Everything in the right-hand columns is a
section-2 block; "–" means the field is absent from the run doc, not hidden by the UI. The
pattern is exact: every run with one config is a card file; every run with a population is a
ranged strategy file. The UI was never the cause — v73.226 already draws the only space a
pinned run did search (the ML gate model × cut-off landscape) in the SURFACES column.

Walk-forward folds are present on all of them (8/8 on #226) — those come from section 1.

## 3. The fix (queued 2026-08-23, job `2vBZVcmazbRrLXwYgkIo`)

A **full-discovery Auto-Validate of `ENGUQ_1M_ETH_1_0.py`** — the ranged ETH file, whose
ranges contain the #226 champion (ema_len 1380 / tl_len 170 / atr_len 106) — on the **same
window, source and costs as #226** so the two read side by side:

- window 2010-06-07 → 2026-06-30, NQ 1m ETH `db_noadj_eth`, cost 0.533 pts, 12-month lockbox
- discovery `auto`, 300 trials × 5 rounds, DSR on, ES transfer off (same machinery as #225)

What it gives that #226 cannot: 2F parallel coordinates + 2G PDP, 2B/2C config scatter, 2E
3-D surfaces on the *strategy* knobs, 2H knob importance, 2I neighbour robustness, plateau
pick, surrogate, DSR, PBO — the whole bigger picture for ENGU-Q ETH.

What to expect, said before it finishes: the search crowns its own champion. It may land on
#226's exact config, or on a neighbour. If the plateau and neighbour checks agree with #226 the
crown is stronger; if the search finds a better-placed config, #226 stays certified and the
new run becomes the comparison, not a silent replacement. Nothing on the PAPER board moves off
this run without the owner's call.

## 4. Standing rule (added to the project rules)

**A pinned card file is for reproduction, not for the report of record.** Every strategy that
is crowned, paper-traded, or shown to the owner as a result gets a full-discovery
Auto-Validate on a ranged file, window pinned to the certified run. Card-file validates are
allowed for parity checks and gate bake-offs, and must say "pinned — section 2 n/a" in their
note. If a card-file validate is the only one a strategy has, the gap is listed here until the
full run exists.

Strategies currently in the gap (card-only): ORB #230 (`ORB_3_4_C221`), NOISE #241
(`NOISE_1_1_SBS`), ENGU-Q limit-0.50 #249, ENGU-Q efficiency #265. ENGU-Q ETH #226 is the one
being closed now; the other four follow once this run's result is in and the owner has seen it.

## 4c. NOISE crown #243 — audited 2026-08-31 (owner: "its missing quite a lot of info")

Read straight off the run docs, not inferred:

| run | file | n_evaluated | n_valid | plateau | PBO | DSR | holds the crown config? |
|---|---|---|---|---|---|---|---|
| **#243** | `NOISE_1_1_SBS_V90.py` | **1** | **1** | – | – | – | it IS the crown |
| #237 | `NOISE_1_0.py` | 570 | 292 | yes | yes | yes | **no** — not exactly, not within one knob |
| #302 | `NOISE_1_0.py` | 570 | 292 | yes | yes | yes | **no** — identical population to #237 |
| **#304** | `NOISE_1_1_NBHD.py` | 495 | 233 | yes | yes | yes | **yes** — exact, plus 69 within one knob |

**What #243 is missing:** the plateau pick, the surrogate, `relationship`, PBO and DSR — every
section-2 block that needs a population. Section 1 is complete: equity, 8 walk-forward folds,
lockbox, gate bake-off, regime, context all ran.

**RE-RUNNING #243 CANNOT FIX IT.** `NOISE_1_1_SBS_V90.py` is a pinned card file — every knob has
`min == max` — so a fresh Auto-Validate of it evaluates exactly one configuration again and
produces exactly the same gap. This is the standing rule in §4, applied to the crown.

**The landscape already exists, and §4b was wrong about which run supplies it.** §4b recorded
"NOISE #241 — none needed, #225 and the 2026-08-17 filter run are already 300-config populations
on the same window". That reasoning does not survive the check: #237 and #302 search all 15 knobs
over the right window, but neither population contains the crowned configuration — nor anything
within one knob of it — and their own champion is a different animal (lookback 64, band 0.50,
day-type filter off). They show what the NOISE space looks like; they do not show where the crown
sits in it. **Run #304 does** — a restricted re-search around #243 on the same window and master,
233 valid configs, the crown itself in the population and 69 of its immediate neighbours, with the
plateau pick, PBO and DSR all present.

**Shipped with this audit:** a one-config run used to point at the family's NEWEST sweep. That
landed on #304 for NOISE by luck, and would have sent the reader to #302 the moment another
`NOISE_1_0.py` sweep finished — a population the crown is absent from, with nothing saying so. The
pointer now prefers a sibling that DECLARES it searched around this run, then one on the same
window and master, and it states which of those it used. When it can only offer a same-window
sweep it says outright that the population may not hold this exact configuration.

**Still open (owner's call, not done here):** the job note that says "restricted re-search around
champion #243" lives on the JOB document and is not copied onto the RUN document, so the
declarative branch of that pointer cannot fire yet. Copying it across at save time would make the
link exact rather than merely same-window.

## 4b. Status of the sweep (updated 2026-08-26)

| gap | full-discovery run | result |
|---|---|---|
| ORB #230 | **#274**, 647 configs | DONE. Section 2 complete. Its own champion is weak and the verdict is FAIL (transfer + luck); **#230 keeps the crown** — this run exists for the geometry around it. STUDIES row 590. |
| ENGU-Q ETH #226 | job `2vBZ…` | RUNNING (restarted 2026-08-26, see below). |
| ENGU-Q efficiency #265 | job `Lsvv…` | QUEUED. |
| ENGU-Q limit #249 | job `syX8…` | QUEUED. |
| NOISE #241 | none needed | #225 and the 2026-08-17 filter run are already 300-config populations on the same window; #241 is a pinned variant of those. |

**Three days were lost to a runner trap, and it is now fixed in code.** The first three
jobs were queued 2026-08-23 and were still showing `running` on 2026-08-26 — frozen at
20 / 48 / 79%. They were not slow; they were dead. A runner restart (another session's)
leaves a mid-flight job's doc on `status='running'` forever: the worker is gone and nothing
ever finishes it. This was the THIRD occurrence (see the 2026-08-05 note in the transfer-sweep
memory) and every previous fix was manual.

`api/runner.py` now sweeps for this at startup: any job on `status='running'` whose Firestore
doc has not been written in 60 minutes had its worker die, so it goes back on the queue with
the reason recorded on the doc. A live job rewrites its own doc every ~1.5s through the
progress callback, so no new bookkeeping was needed — the doc's own update time is the
liveness signal. Deliberately conservative (startup only, never in the poll loop; a full hour;
loudly logged) because a false positive means a job runs twice. Verified against live data
before shipping: the running job (doc age 1 min) was correctly left alone while a genuinely
stranded one (doc age 524 min) was correctly identified.

## 5. Changelog

- 2026-08-23 — file created; audit of ten validates; full-discovery ENGU-Q ETH run queued.
- 2026-08-26 — ORB gap CLOSED (run #274). Found the three ENGU-Q jobs had been dead for three days on a restart-orphaned `running` status; requeued them and fixed the cause in `api/runner.py` (startup orphan sweep).
