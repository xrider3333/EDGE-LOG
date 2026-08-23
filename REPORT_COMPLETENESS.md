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

## 5. Changelog

- 2026-08-23 — file created; audit of ten validates; full-discovery ENGU-Q ETH run queued.
