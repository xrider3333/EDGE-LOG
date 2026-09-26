# RUNBOARD — spec + running record

> ⚠ **2026-08-11 — ORB look-ahead bug affects the ORB rows on this board.** Touch-entry
> ORB fills the instant price touches the range edge (intrabar), but its volume filter
> gates on the breakout bar's FINISHED volume — a number that doesn't exist yet at fill
> time. Crowned #125 shows $360,591 net but live-legal fills top out around $44k-$69k;
> this also drags down the ORB × ENGU-Q blend baseline. Full writeup: `ORB.md` (repo
> root, top banner).

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

**v71.22–71.34 (2026-08-09) — the 1A + 1E rebuild SHIPPED.** Three panels side by side:
strategy list · funnel · matrix. The board flows through the same COMPARE pipeline as
PICK RUNS / BY STRATEGY:
- **1A · FUNNEL** (middle): the live equity overlay dressed in 1A's own visual language —
  blue WF band + purple LB band with in-sample un-shaded, IS/WF/LB printed inside the top
  of each region, a dashed purple door line, ending-$ pills on the right gutter at each
  line's height, crosshair, drawdown pane, ⛶ fullscreen explorer. Runs have DIFFERENT
  windows, so bands span from the earliest door onward and each key row states its span.
  Turned on via `window._cmpOvl1A` before `cmpOvlMount` — COMPARE's own chart is unchanged.
- **1E · MATRIX** (right): the shared `_matrixTbl` shell — the SAME component 1E / 2B / 2C
  use. Grouped bands RUN · RETURN · DRAWDOWN · EDGE · SAMPLE · VERDICT, metric names pinned
  left, one column per strategy in its curve colour, leader column tinted, green best-in-row.
  SAMPLE / RANK / VIEW ride on this tile as `_tabBtn` rails (blue / teal / violet).
  Board keeps its OWN orientation pref (`rbOrient`) so the 1E look survives COMPARE on HORIZ.
- **RESIZE**: drag bar under the funnel and under the matrix set those heights
  (`rbFunnelH`, `rbMtxH`); drag bars BETWEEN the three columns trade width (`rbCols`).
  Double-click any bar resets it. The report's own handles only ever existed inside
  `res-detail`, which is why COMPARE had none — these are wired in the compare handler block.
- **QUICK TOGGLE** (v71.35): click a strategy in the funnel key to drop its curve; click again to
  restore. Hidden ones stay listed struck-through; axis, bands and drawdown pane rescale to what
  is shown. State lives on `window._cmpOvlHide`, cleared whenever the curve set changes.
- **BOOKS are real runs** (v71.42+): `type:'book'` jobs pool N legs and save an ordinary run doc —
  see §5. Real book runs list at the top of the BOOKS tile as green ▸ LIVE RUN rows, click to open
  the run report. The offline rows stay beneath until each is replaced.
- **WINDOW row** (v71.34): each strategy's date span + length, flagged yellow under 2 years.
  Added because run #42 (19 days, ES 1m) was topping the NET ranking against 16-year runs
  and drawing as a hairline blip on the funnel with nothing on screen explaining why.
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
| B | ~~Book-level validate path — "the BOOKS problem"~~ | **SHIPPED v71.42–71.49.** `augur_engine/book.py` + runner job `type:'book'`. Launch from RUNBOARD ▸ BOOKS ▸ ＋ RUN A BOOK. First real book run = **#204 (BOOK-1)**. Verified against the offline script: the baseline book's IS net/DD/PF/trades come out identical ($654,771 / $45,849 / 1.432 / 5,777) — `python tools/book_smoke.py`. Two bugs the end-to-end test caught and fixed: a leg whose run never recorded its session (overnight leg asked for day-session data → book died; now inferred from the source with fallbacks), and the BOOKS tile matching every 🔒 LOCKBOX run as a book (the word contains "book"; now keyed on the pooled block). Original problem, for the record: | The 5 BOOKS rows are the only hand-fed thing left on the board. They are computed offline by `tools/t5_runboard.py` and pasted into `index.html`, because a BOOK is two strategies traded together and Auto-Validate can only take ONE strategy file. Consequences: (a) no app verdict — their WF 8/8 is a house 8-slice test, not the fold engine; (b) no saved equity curve, so they cannot draw on the funnel; (c) they go stale until someone re-runs the script. FIX = teach the runner a `book` job type that runs N strategy files over one window, pools the trades, and saves ONE run doc — then a book becomes an ordinary row on the board and items C/F close with it. |
| C | ~~Auto-populate from run history~~ | **SHIPPED v71.22** for the strategy-champion rows (board reads saved runs directly); the pooled BOOK rows are still pasted from `tools/t5_runboard.py` — pending item B |
| D | ~~Add columns the owner flagged as useful~~ | **SHIPPED v73.883** (the LONGEST FLAT STRETCH follow-up for books landed in **v73.884**). TRADES / YR, WORST MONTH and LONGEST FLAT STRETCH now sit on the matrix, one reading per STAGE, read from each run's saved month-by-month P&L grid through its own small masked fetch rather than the whole run document. Average $ per trade is the existing EV row, not a new one. Worst single DAY and correlation to the current book were NOT built: no run saves a daily P&L series, and a book saves no monthly one either — the engine itself would first have to start saving a daily or monthly P&L series per run, books included. |
| E | Overlay × ENS stacked book | untested 6th row — both upgrades modify the ORB half; needs its own pre-registration. Stays open — belongs to the features chat, not web work (it needs a pre-registered book run first). |
| F | ~~Book curves in the funnel~~ | **SHIPPED v73.883.** Books now sit under one BOOKS family chip — the same grouping the rest of COMPARE uses — and draw their saved equity curves on the funnel. Every BOOK job has saved an equity curve since v71.42; the gap was only in how books were grouped and keyed, never in what the engine saved. |
| G | ~~RUNBOARD WINDOW row on IS/LB, book-name labels, chart-key wording~~ | Three items from `audit3_report.md`'s COMPARE audit. **F25**: the WINDOW row on IS and LB now reads the stage's own stretch (its own dates and years), the same stretch the MAR and TRADES / YR rows beside it already divide by, instead of the whole run's span — FULL and WF were already correct and are unchanged. **F30**: a book stopped reading like a strategy file name (a parsed version/branch number lifted off its own descriptive text) in the OVERLAY chart key's no-curve list; a rank number (R1..Rn) no longer prints on a hand-picked comparison, only on CHAMPIONS and RUNBOARD, where the order is real; the RUNBOARD matrix header stopped doubling a run's id when it has no saved family-run number; ETFDIP now reads the same abbreviation everywhere instead of "ETFDI" on some screens. **F31**: RUNBOARD's LB chart key calling a saved-but-empty lockbox curve "no curve saved" was checked and found already correct on the current build — the reason already names that the lockbox took no trades — so no change was made. **SHIPPED 2026-09-24** (the version is in that day’s changelog entry). |
| H | ~~ROC % / YR + SORTINO rows and the MANAGER watch list~~ (owner go via MANAGER 2026-09-26) | **SHIPPED v73.911.** ROC % / YR (return band, under TOTAL) = the stage's net per year on the ACCT account ($100k default) - the same net and years TOTAL and MAR read, the same arithmetic as COMPARE > EXPLORE and the weekly report. SORTINO (under SHARPE) = the engine's own annualised figure: WF = the saved walk-forward test, LB = the lockbox strip, FULL = the whole run; no run saves an in-sample Sortino and books compute none, so those dash with the reason. WF RULE: every WF row reads the walk-forward TEST, never the crowning score; a run that also saved a crowning score names it in the WF ROC hover (#382: test 44.2%/yr, crowning score 55.8%/yr). All 22 watched runs matched MANAGER's reference pull (C:\EdgeLog\manager\stats_board_2026-09-25.json) to 0.1. WATCH LIST = one Firestore doc (users/{uid}/meta/runboard_watch) edited by `tools/runboard_watch.py` (add / verdict / note / remove / import, --dry); the page reads it once per load, the WATCH chip shows every listed run (no 10-column cap, no short-run drop), the LANE VERDICT row labels each watched run. Seeded 2026-09-26 with the 22 runs of the week-of-09-19 report. |

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

---

## 5. BOOK runs (v71.42+) — how a book is measured

A BOOK is what actually gets deployed: two or more strategies running side by side in one
account, 1 contract each. `augur_engine/book.py` runs one as a normal job.

**The mechanic.** Every leg is replayed over the SAME window with its own frozen params,
its own market/timeframe/session/source and its own contract multiplier. Each leg's trades
are converted to DOLLARS, stamped by EXIT date, and poured into one pile. The pile is then
scored as a single strategy — which is the whole point: profit factor is computed across the
pooled trades, and drawdown is measured on the DAILY account curve, so a day where one leg
loses and the other wins nets out first, exactly as the account sees it.

**What a book reports:** whole-window / pre-lockbox / lockbox stats, a real equity curve
(so it draws on the funnel), the per-leg breakdown, and the house count of how many of 8
equal stretches were profitable.

**What a book deliberately does NOT report: walk-forward folds.** Nothing is tuned during a
book run — the params arrive frozen — so there is no fold engine result, and `top10_results`
is left empty on purpose so no house number can ever land in a WF column. The 8-stretch count
rides under `book.slices` as its own thing. Do not merge the two.

**Launching one:** RUNBOARD ▸ BOOKS ▸ ＋ RUN A BOOK. The picker lists each strategy family's
champion; the window defaults to the OVERLAP of the picked runs (the only stretch where every
leg has data), and is pinned into the job.

**Regression test:** `python tools/book_smoke.py` — reproduces the offline baseline book
(ORB 3.1 + ENGU-Q 1m) and fails if net or trade count drifts more than 2%.
> ⚠ 2026-08-11: this reproduces a fixed number as a regression check only — that number
> itself is inflated by the ORB look-ahead bug and is not live-achievable. See `ORB.md`.
