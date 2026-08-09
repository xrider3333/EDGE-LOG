# RUNBOARD — spec + running record

**What it is:** the one place that compares whole **BOOKS** (deployable strategy
combinations) against each other, instead of comparing individual runs.

**Where it lives:** the app, **COMPARE tab → RUNBOARD** (third pill, next to PICK RUNS
and BY STRATEGY). Shipped web v71.2. There is also a standalone `runboard.html` at the
repo root (same table, no login) kept as a backup.

**Owner's ask, verbatim (2026-08-08):** *"maybe make it look like a 1E matrix how it
compares different configs of a strategy but this can compare the top configs of
different strategies… user can select sample and rank data. could put that on the EL
site somewhere and i can tell claude to update it via chat bc comparisons are always
different format and i have to relearn the language of how you give me data."*
Follow-up: *"i want it to be like the 1A funnel and a 1E matrix from the auto-validate
results tab."*

**Why it exists:** every comparison used to arrive in a different ad-hoc table, so the
owner had to relearn the layout each time. The RUNBOARD is the ONE fixed layout. When
he says *"give me the RUNBOARD"* or *"update the runboard"*, emit/refresh exactly this.

---

## 1. Current state (built)

**v71.22 (2026-08-09) — the 1A + 1E rebuild SHIPPED.** The board now flows through the
same COMPARE pipeline as PICK RUNS / BY STRATEGY:
- **FUNNEL** (top right): the live equity overlay — key pills on their lines, crosshair,
  drawdown pane, solid IS / dashed WF / dotted LB stages, ⛶ fullscreen explorer.
- **MATRIX** (under the funnel): the sectioned compare table — metrics as rows grouped
  return / drawdown / reward÷risk / edge / sample, strategies as columns, green
  best-in-row, VERT / HORIZ flip, TOTAL with indented IS / WF / LB rows on FULL.
- **AUTO-POPULATED**: the top run of every strategy family (same champion rule as
  BY STRATEGY), listed in the left tile — no more hand-pasted run rows.
- **SAMPLE** (FULL / IS / LB) redraws the funnel curves (IS = cut at the first WF fold,
  LB = lockbox tail rebased to $0), recomputes the matrix, re-ranks everything.
  **RANK BY** (MAR / PF / NET / MAX DD) orders the funnel key, matrix columns and list,
  measured on the picked SAMPLE. Both persist (`rbSample`, `rbRank`).
- **BOOKS tile** (bottom): the pooled two-strategy book rows keep their own clearly
  separated table (columns `# · STRATEGY · VERSION · NET · PF · MAX DD · MAR · TRADES ·
  WF · VERDICT`), still hard-coded from `tools/t5_runboard.py` — search `index.html` for
  `RUNBOARD DATA`.

Honesty mechanics: FULL/LB drawdowns and MAR are read off the stored (downsampled)
champion curve — close approximations, same treatment every row; FULL-sample PF ranking
falls back to the optimize-window PF (no whole-run PF is stored); a run missing a stage
shows a dash and sinks in the ranking; a run with no saved curve drops to the funnel's
no-curve key list.

House conventions that must not drift:
- **MAX DD prints POSITIVE** (the header already says drawdown).
- Stage names are only ever **IS / WF / LB** — never "sealed year" or "held-out year".
- **STRATEGY** = the book name (`BLEND` = two strategies traded side by side, 1 contract
  each; `ENGU-Q ETH` = a single strategy alone). **VERSION** = what differs about that
  book. The models that make up the book are named in small text under the strategy.
- Verdict chips: ★ CHAMPION · ● CANDIDATE · ‖ PARKED · ✕ DEAD.
- Every book is scored as **ONE strategy** — all legs' trades pooled — so PF and MAR are
  true book-level numbers, not a leg's.

### ⚠️ Validation status of the current rows — READ THIS BEFORE TRUSTING THEM
**None of the five book rows is an app Auto-Validate run.** The app's Auto-Validate can
only validate ONE strategy file at a time; a two-strategy book has no Auto-Validate path
today. The rows are offline computations from `tools/t5_runboard.py` (and t1/t2/t3).
- The **legs** are separately validated in Past Runs (ORB 3.0 / ORB_3_0_ENS / ENGU-Q 1m /
  ENGU-Q ETH all have 🧭 Auto-Validate runs).
- The **WF 8/8** column is a house test built for this board — the full history cut into
  8 equal stretches, frozen params, count profitable. It is NOT the app's walk-forward
  fold engine and the two must never be conflated in the same column.
- Therefore: the RUNBOARD ranks candidates honestly against each other, but a row is not
  "validated" in the app sense until a book-level validate path exists (see §3, item B).

### Name collision to be aware of
`ORB 3.0-ENSEMBLE` in **Past Runs** = the ORB ensemble strategy **alone** (one leg,
Auto-Validated, NQ 5m, ≈$181k net / DD ≈$10.6k / PF 1.57 / 2,787 trades — runs #180,
#184-#200). The RUNBOARD's `BLEND / ENS exits …` rows use that **same strategy file as
the ORB half of a two-strategy book**, then add ENGU-Q — which is why the book totals
(≈$942k) look nothing like the standalone run. Same file, different unit of measurement.
Keep the STRATEGY column reading BLEND so the unit is unambiguous.

---

## 2. What the owner wants next — make it look like 1A + 1E

Two existing charts in **RESULTS ▸ auto-validate report** are the visual target. Match
their look and interaction, not just their data:

**A. Like `1E KPI MATRIX`** — the metric matrix layout:
- Metrics as ROWS, books as COLUMNS (1E is runs-as-columns; do the same with books), with
  the option to flip orientation like COMPARE already offers (VERT / HORIZ).
- Grouped metric bands with indented sub-rows, the way 1E groups return / drawdown /
  reward-to-risk / edge / sample.
- **Best-in-row highlighting in green**, exactly like COMPARE and 1E do today.
- The stage split visible as indented rows (IS · WF · LB) under the TOTAL row, mirroring
  how the run report's KPI matrix breaks TOTAL into its three stages.
- Same tight vertical padding rhythm 1E uses (see web v71.1 changelog note).

**B. Like `1A CONFIG FUNNEL`** — a visual, not just numbers:
- A funnel/curve panel above the matrix showing each book's equity curve overlaid, one
  line per book, same line weight and colour discipline as 1A / the COMPARE equity
  overlay.
- Respect the SAMPLE selector: FULL / IS / LB should redraw the curves, not just the table.
- Gutter pills labelling each line must sit ON their line (see the v71.1 fix — do not
  re-introduce a de-collide pass that walks pills off their lines).

**C. Keep** the SAMPLE and RANK BY controls, the pooled-book scoring, and all §1
conventions.

---

## 3. Backlog

| # | Item | Notes |
|---|---|---|
| A | ~~Rebuild RUNBOARD in the 1E matrix + 1A funnel style~~ | **SHIPPED v71.22** (§1 above) |
| B | Book-level validate path | so a BLEND row can carry a real Auto-Validate verdict + WF folds + LB, instead of the house 8-slice test |
| C | ~~Auto-populate from run history~~ | **SHIPPED v71.22** for the strategy-champion rows (board reads saved runs directly); the pooled BOOK rows are still pasted from `tools/t5_runboard.py` — pending item B |
| D | Add columns the owner flagged as useful | trades per year · average $ per trade · worst single day · longest flat stretch · correlation to the current book |
| E | Overlay × ENS stacked book | untested 6th row — both upgrades modify the ORB half; needs its own pre-registration |
| F | Book curves in the funnel | the BOOKS rows carry no equity curve, so only strategy champions draw; t5_runboard.py could emit a downsampled per-book curve to overlay |

---

## 4. How to regenerate the numbers

```
python tools/t5_runboard.py
```
Pins the window 2010-06-07 → 2026-06-30, NQ, 1 contract per leg, costs in
(0.533 pts/round-trip), trades bucketed by exit date, ENGU-Q leg = the certified
`ENGUQ_1M_1_0.NQ_DEPLOY_PARAMS_149`. It prints a JSON block — paste it into the
`RUNBOARD DATA` array in `index.html` and bump the web version.

Related drivers: `tools/blend_recert.py` (baseline recert), `tools/t1_ens_blend.py`
(ENS leg swap), `tools/t2_overlay_sens.py` (sizing overlay + rule sensitivity),
`tools/t3_eth_wf.py` (ETH frozen walk-forward).
