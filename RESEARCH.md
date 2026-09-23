# RESEARCH — validation methodology, findings and the actions they imply

Single place for **research about how EDGELOG validates**, as opposed to research about a strategy.
Strategy findings stay in their own files (`ORB.md`, `NOISE.md`, `ENGUQ.md`, `BOOKMARKS.md`, …);
status of the machinery stays in `BACKTESTING_STACK.md`; shipping backlog stays in `ROADMAP.md`.
This file is the bridge: **what we learned → what EDGELOG should change**.

`RESEARCH_LEDGER.md` (repo root) indexes EVERY line of work tried or added - validation
changes, edge hunts and tools - each with the document holding its evidence and the verdict
it earned. Start there to find something; come here for what it means.

Owner pointed the research chat here on 2026-09-20. Add to the action table as findings land; move an
item to ROADMAP.md when it becomes scheduled work, and record the outcome back here.

---

## 1. The two deep dives (2026-09-16)

| Doc | Question | One-line answer |
|---|---|---|
| [`docs/WF_LOCKBOX_DEEP_DIVE.md`](docs/WF_LOCKBOX_DEEP_DIVE.md) | Fixed-settings walk-forward vs re-tuned walk-forward vs lockbox — what should a go-live decision rest on? | The fixed-settings walk-forward number is the score the crown was **selected on**; the re-tuned walk-forward test is the honest reading; the lockbox is clean but far too short to rank. |
| [`docs/IS_LENGTH_OOS_VALIDATION.md`](docs/IS_LENGTH_OOS_VALIDATION.md) | Is ~15 years of tuning history needed, could more go to the lockbox, and what does the literature say? | 2–3 years picks settings as well as 15; a 24-month warm-started lockbox costs the pick nothing; no lockbox length can rank; 91 sources checked, several methods worth adopting. |

Both were produced by multi-agent runs with an adversarial verification pass; every headline number in
them is the **verified** version, and the limits are stated in each doc's own "what this does not show"
section. Data and scripts: see §5.

---

## 2. Findings that change how we should read the board

1. **The crown is chosen by its walk-forward-years score** (validate Stage A.5, on by default since
   2026-07-23, top-10 finalists). So the report's fixed-settings walk-forward column is that selection
   score, not a test: ~16% above the re-tuned reading on runs with a real shortlist, equal on pinned
   runs (#257 ORB has zero free knobs; #243 NOISE is pinned).
2. **The re-tuned walk-forward test is calibrated.** Lockbox profit factor ÷ reading profit factor,
   median across 151 runs: re-tuned 0.99, fixed 0.95. Rank power of both ≈ 0.33 — no better than
   in-sample, so treat any single reading as evidence, not a promise (typical per-run miss ≈ 0.2 PF).
3. **Crowning on walk-forward years did not pick better configs.** Where Stage A.5 overrode the
   in-sample pick, the crowned config had the better sealed year in ~4 of 10 runs; #335's crown ranked
   6th of 10 finalists on its own sealed year.
4. **The 12-month lockbox cannot confirm anything.** Engine power field median 0.11; months needed for
   80% power on the claimed edge: 404 (#257), 120 (#335), 232 (#243). The pass rule (net > 0, PF ≥ 1)
   is a sign test: a no-edge series passes ~50% of the time at every length 12–36 months.
5. **Tuning depth is not the scarce resource.** Pick quality flat from ~2–3 years out to 15 in every
   family tested; what depth buys is an honest in-sample number (tuning-window PF optimism 2.3× at
   1 year, 1.3× at 3, ~1.05× at 8) and walk-forward test data.
6. **Cold starts distort the sealed year.** 12-month lockbox loses a median 24% of trades to warm-up
   vs 5% at 24 months; NQDIP #401 loses 71% at 12 months, 36% at 24.
7. **Selection accounting is incomplete.** The engine's deflated-Sharpe and backtest-overfit checks
   count one run's own search only — not the 300 candidates × 8 folds inside it, not the repeated
   rounds per family, not the cross-run leaderboard.
8. **Straddling trades leak.** Scoring a window by trade ENTRY lets post-cut money count toward a
   pre-cut score; it moved 26–41% of ENGU-Q's short-window picks in testing (small, unsigned effect on
   outcome, but a real channel).

---

## 3. Action table (owner decides; nothing here is scheduled work yet)

| # | Action | Why (finding) | Cost | Status |
|---|---|---|---|---|
| 1 | Count trials per FAMILY (search + per-fold candidates + rounds ever run) and apply the luck-adjusted bar to crowns; show it beside the existing within-run check | §2.7; Harvey & Liu (2015), Bailey & López de Prado (2014) | Moderate: registry fields + board chip | OPEN |
| 2 | Purge straddling trades at every cut (assign by exit, or drop from the training score) | §2.8; López de Prado (2018) purging/embargo | Small engine change | OPEN |
| 3 | Search-adjusted p-value for the crown pick (Reality-Check-style bootstrap over the 10 finalists) | §2.1, §2.3; White (2000), Hansen (2005) | Script only, but the DATA IS NOT THERE YET: per-fold candidate rows are only recorded on validates run since 2026-09-09 (none of the 293 cached run docs carry them, and the 351-run extract in §5 has no validate block). Either wait for new runs or rebuild from the deep-dive matrices | BLOCKED on data |
| 4 | "Months until trustworthy" per crown (minimum track-record length) + a lockbox **looks counter** per run/family | §2.4; Bailey & López de Prado (2012), Dwork et al. (2015) | Small: compute from saved fields, two pills | OPEN |
| 5 | Lockbox **36 months for everything**, warm-started, one look, veto only (supersedes the 24 / 36-for-slow-legs split proposed in the second dive) | §2.4, §2.6; and the second dive's own note that 36 for everything is defensible because the tuning cost is zero | Engine parameter + re-judging | OPEN — owner leaning 36 (2026-09-20); test via item 9 |
| 6 | Pass rule = sealed PF within a margin (~0.15) of the re-tuned walk-forward PF + trade floor (~60 trades / 24 mo) + the luck bar | §2.2, §2.4 | Small (verdict + web pill) | OPEN |
| 7 | Warm-start the walk-forward folds and the sealed stretch (evaluate on all history to the slice end, keep only trades entering inside it) | §2.6; also the long-standing cold-start defect | ~1 day engineering; re-judge NQDIP 1.1 and the ETF stack afterwards | **SHIPPED 2026-09-20** — see §3b |
| 8 | Rank COMPARE on the re-tuned walk-forward test (PF + trade floor); show fixed as "crowning score" with a gap chip; lockbox = pass gate, never a ranking column | §2.1–§2.4; the gap predicts the sealed shortfall (ρ 0.52) | Web change | **DECIDED 2026-09-20** (owner: rank on the re-tuned test). Being built now by the COMPARE session; the walk-forward relabel (F14) is unblocked. Rank metric stays return-per-year for now - profit-factor-first is still an owner call |
| 9 | Re-validate #257, #243, #335 at **36 months** (and 24 as a control), windows pinned | Direct test of item 5 before adopting | ~20 min / ~30 min / 1–2 h runner time per length | **RAN 2026-09-21** — see §3c |
| 10 | Drop or correct the Stage A.5 crowning step (crown from the tuning search; then the fixed reading after the search's data ends is a clean test) | §2.3 | Small (crown rule); reverses the 2026-07-20 decision | OPEN |
| 11 | Rank/gate on risk-shape stability across folds (volatility, drawdown), not profit alone; size live expectations with a haircut | Wiecki et al. (2016): backtest Sharpe R² ≈ 0.02 to live, volatility 0.67, drawdown 0.34; Suhonen et al. (2017): median 73% Sharpe haircut live | Moderate | OPEN |
| 12 | Consider a combinatorial purged cross-validation path (many walk-forward paths instead of one) for a distribution rather than a single number | López de Prado (2018) ch. 12 | Large — evaluate after items 2 and 7 | PARKED |
| 13 | Fix the daily dip family's fold reproduction (0 of 8 against the engine's own saved folds, §5) | Nothing in items 1–11 can judge a family whose folds do not reproduce | ~half a day of engine debugging | OPEN |

---

## 3b. Item 7 — warm starts, shipped 2026-09-20

**What changed.** Every stretch a validate SCORES out of sample now runs from 300 trading
sessions before it opens, keeping only the trades that ENTER inside the stretch: each
walk-forward fold's test leg, Stage A's 25% split, the lockbox, and every candidate carried
into the lockbox. Training windows are untouched — an anchored fold already trains from the
first bar, and warming a rolling fold's TRAINING window would change which config is picked,
which is a different question and is not part of this.

**Why it cannot leak.** A warmed stretch still ends exactly where it always did, so nothing
after its own end is read. A test pins this directly: rewrite every bar after the stretch and
the warmed result does not move.

**Why 300 sessions and not all history.** The longest look-back in the book is a 250-day
trend filter, so 300 covers every strategy we run with headroom, and it costs one pass over
the warm-up bars per scored stretch instead of a pass over the whole history. Measured
against warming from the first bar (the 2026-09-15 audit's own method) the two agree to the
dollar on all four legs checked.

**Verification** (`tools/warm_start_parity.py`, engine path vs the independent 2026-09-15
implementation, per fold):

| Leg | Cold trades / net | Warm trades / net | Cold start cost | Engine vs audit |
|---|---|---|---|---|
| QQQ RSI2, 250-day trend | 28 / $18,962 | 191 / $124,675 | 85% of its trades | exact |
| GLD N-day low, 125-day trend | 54 / $44,789 | 97 / $65,051 | 44% | exact |
| NOISE crown #304 | 2,402 / 12,188 pts | 2,812 / 16,468 pts | 15% | exact |
| ORB crown #234 (control) | 1,457 / 15,534 pts | 1,448 / 15,417 pts | none (−1%) | exact |

**What it does NOT do.** It does not re-judge anything by itself. Every stored verdict was
formed on cold folds and a cold lockbox; the daily long-trend failures (NQDIP 1.1, the ETF
stack's walk-forward efficiency) stay on the books until those runs are re-run.

**Opting out.** `warm_days: 0` on a job reproduces a pre-2026-09-20 run exactly. Each saved
run records the setting it used, so cold and warm runs stay distinguishable.

---

## 3c. Item 9 — 12 vs 36-month lockbox, ran 2026-09-21

Paired arms, same file / window / 900 trials, warm starts on in both (`tools/queue_lockbox_36mo.py`).
ORB and NOISE searched their declared PARENT files (the crowns' own files are pinned), so those two
rows are about the family, not crowns #257 / #243. Lockbox $ = points x $20.

| Family | 12-month arm | 36-month arm | Same crown? |
|---|---|---|---|
| ORB (ORB_3_6) | #404 FAIL — LB -$19,480, PF 0.92, 193 trades | #403 FAIL — LB +$97,400, PF 1.11, 746 trades | No |
| NOISE (NOISE_1_0) | #406 PASS — LB +$50,380, PF 1.31, 288 trades | #405 WEAK — LB +$95,720, PF 1.24, 733 trades | No |
| ENGU-Q (R2) | #402 WEAK — LB +$65,960, PF 1.22, 197 trades | #407 PASS — LB +$147,200, PF 1.59, 273 trades | No |

**Reading.** The crown moved in all three families, and the verdict changed in two of them in
OPPOSITE directions (NOISE PASS -> WEAK, ENGU-Q WEAK -> PASS). That is what an unstable pick and a
noisy verdict look like, not evidence that the three extra tuning years were load-bearing: the
candidate board already showed the choice among near-equal finalists is a coin flip, so a different
crown from a different window is expected even when pick QUALITY is unchanged. What the longer arm
reliably buys is sample: 2.5-3.8x the lockbox trades in every family. Nothing here shows the 36-month
arm costing anything.

**Limits.** One run per arm, three families; the crowns differ, so the two arms' lockboxes score
different configs on overlapping-but-different stretches and cannot be compared dollar for dollar.

**Recommendation:** adopt item 5 (36 months, warm, veto only), and stop reading a single validate's
PASS/WEAK/FAIL as a property of the family — two of three flipped on the lockbox length alone.

---

## 3a. Settled — do not re-open without new evidence

**Tuning breadth stays at 900 configurations per search (owner, 2026-09-20).** The default moved
from 200 to 900 on 2026-09-11 and is not to be reduced. The A/B that settled it (runs #383 vs #384 —
same file, same window, same fence, only the budget differing) went against the old budget study on
every measure that matters: overfit probability 0.603 at 900 vs 0.802 at 200, twice the held-out
trades (277 vs 140) and three times the sealed-year profit, for 45 minutes of runner time against
26. This supersedes the earlier "trial budget is not the bottleneck" note, which rested on one wide
ORB space. Nothing in the action table above touches it: every item there is about how a search is
JUDGED, not how widely it looks.

**Why more sampling and a shorter tuning span are not in tension.** Depth (how many YEARS the search
may see) measured flat from 2-3 years out to 15; breadth (how many CONFIGURATIONS it tries inside
those years) did not — breadth is what finds a plateau rather than a spike. So the years are free to
move to the sealed stretch (item 5) while the configuration budget stays where it is.

---

## 3b. Handed to the features chat (backtesting side), 2026-09-20

The owner asked that the runner-side work be evaluated from the features chat rather than the COMPARE
session. Nothing below has been queued.

**Item 9, the 24-month re-validates (owner ordered).** Re-validate the three crowns with a 24-month
lockbox, everything else pinned to each baseline run - same strategy file, instrument, timeframe,
session, data source, cost, trial budget, seed, fold count and the exact date_from / date_to - so the
lockbox length is the only difference. The question: do the crown and the verdict move when a year
leaves the tuning window?

- **The catch:** #257 (ORB) and #243 (NOISE) are PINNED files - every knob min == max - and the runner
  refuses a validate on a zero-knob file (guard since v73.350) and names the declared parent instead
  (ORB_3_6_C2 -> ORB_3_6.py, NOISE_1_1_SBS_V90 -> NOISE_1_0.py). Running a parent re-searches and may
  crown a different config, which answers a different question than "the same frozen config over a
  longer sealed window". Decide which question to answer before queueing.
- If parents are used, queue a matched 12-month arm on the same file, window and budget: the existing
  parent re-runs (2026-08-28) used 12 months for ORB at 200 trials and 18 months for NOISE at 300, so
  they are not a clean control for each other.
- #335 (ENGU-Q, 14 free knobs) re-validates directly, and its own run is the 12-month control.
- Rough runner cost per arm: ORB 5m about 20 minutes, NOISE 5m about 30, ENGU-Q 1m one to two hours.

**Also engine-side, if the owner points you at them:** items 2 (purge straddling trades), 7 (warm-start
the folds and the sealed stretch), 1 (per-family trial ledger behind the luck bar), 4 (minimum track
record and a looks counter) and 13 (the daily dip family whose folds no longer reproduce - worth doing
first, since no other item can judge a family whose folds do not reproduce).

**RUNBOARD backlog E, from RUNBOARD.md.** The Overlay x ENS stacked book is an untested sixth row;
both upgrades modify the ORB half, so it needs its own pre-registration and a book run before it can
be judged. Not a web change - it belongs with the backtesting work above.

---

## 4. Open owner decisions (both dives)

- What COMPARE ranks on (item 8) — until this is settled, the report's 1E walk-forward column keeps its
  current label and the COMPARE audit's F14 stays on hold.
- Lockbox length and pass rule (items 5 and 6) — owner leaning 36 months for every leg (item 5); test with item 9 first.
- Crowning step (item 10) and warm starts (item 7) — both change every future verdict and force re-judging.
- Tuning span: no change recommended; shortening is not harmful but buys nothing.
- Tuning breadth: SETTLED, see §3a — the 900-configuration budget stays.

---

## 5. Sources, data and how to reproduce

- **Sources:** `docs/IS_LENGTH_OOS_VALIDATION.md` §8 lists every source with a URL, what was actually
  read (full text / abstract), and which specific claims a second pass could not confirm. 91 sources
  across five topics: split choice and power, backtest overfitting and multiple testing, estimation
  window under regime change, holdout reuse, track-record length and practitioner walk-forward.
  All were checked for existence; metadata errors and overstated claims are marked in place.
- **Scripts:** `tools/wfdive/` (first dive: which reading predicts the sealed year, frozen-vs-re-tuned
  replay, training-length experiment, lockbox length and power) and `tools/wfdive/isdepth/` (second
  dive: candidate-matrix builder, shared analysis, verification). Stdlib + the engine; no Firestore
  writes anywhere.
- **Data:** the matrices and per-lens JSON live outside git in the research worktree
  (`_wfdive_data/`, ~145 MB: 1,000 warm full-history configs per family for runs 299 TTM, 304 NOISE,
  307 NQDIP, 314 ORB, 335 ENGU-Q, plus the 351-run Firestore extract). Rebuild with
  `tools/wfdive/isdepth/build_matrix.py <run_id>` (about 15–25 min per family, CPU-locked and
  below-normal priority so it never fights the live fleet).
- **Known gap:** NQDIP fold reproduction is 0/8 against the engine's own saved folds — its matrix
  describes the warm procedure, not the engine's cold picks. Worth half a day of engine debugging
  before trusting any NQDIP fold number.

---

## 6. Standing cautions for anyone adding research here

- Families are not independent votes: ~125 run-families collapse to about 8 mechanisms, and NOISE and
  ENGU-Q variants dominate everything recent.
- Never compare eras in raw dollars (NQ amplitude grew ~7×); use profit factor, percentile ranks or
  per-trade R.
- Overlapping windows are autocorrelated — block-bootstrap by origin and say so.
- Three of the five strategy files tested are narrow fences around an already-chosen crown; they can
  answer "does depth matter here" but not "how should discovery-stage tuning work".
