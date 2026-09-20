# RESEARCH — validation methodology, findings and the actions they imply

Single place for **research about how EDGELOG validates**, as opposed to research about a strategy.
Strategy findings stay in their own files (`ORB.md`, `NOISE.md`, `ENGUQ.md`, `BOOKMARKS.md`, …);
status of the machinery stays in `BACKTESTING_STACK.md`; shipping backlog stays in `ROADMAP.md`.
This file is the bridge: **what we learned → what EDGELOG should change**.

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
| R1 | Count trials per FAMILY (search + per-fold candidates + rounds ever run) and apply the luck-adjusted bar to crowns; show it beside the existing within-run check | §2.7; Harvey & Liu (2015), Bailey & López de Prado (2014) | Moderate: registry fields + board chip | OPEN |
| R2 | Purge straddling trades at every cut (assign by exit, or drop from the training score) | §2.8; López de Prado (2018) purging/embargo | Small engine change | OPEN |
| R3 | Search-adjusted p-value for the crown pick (Reality-Check-style bootstrap over the 10 finalists) | §2.1, §2.3; White (2000), Hansen (2005) | Script only — finalists' fold results are already saved | OPEN |
| R4 | "Months until trustworthy" per crown (minimum track-record length) + a lockbox **looks counter** per run/family | §2.4; Bailey & López de Prado (2012), Dwork et al. (2015) | Small: compute from saved fields, two pills | OPEN |
| R5 | Lockbox 24 months default / 36 for daily or long-warm-up legs, warm-started, one look, veto only | §2.4, §2.6 | Engine parameter + re-judging | OPEN — test first via R9 |
| R6 | Pass rule = sealed PF within a margin (~0.15) of the re-tuned walk-forward PF + trade floor (~60 trades / 24 mo) + the luck bar | §2.2, §2.4 | Small (verdict + web pill) | OPEN |
| R7 | Warm-start the walk-forward folds and the sealed stretch (evaluate on all history to the slice end, keep only trades entering inside it) | §2.6; also the long-standing cold-start defect | ~1 day engineering; re-judge NQDIP 1.1 and the ETF stack afterwards | OPEN |
| R8 | Rank COMPARE on the re-tuned walk-forward test (PF + trade floor); show fixed as "crowning score" with a gap chip; lockbox = pass gate, never a ranking column | §2.1–§2.4; the gap predicts the sealed shortfall (ρ 0.52) | Web change | OPEN — blocks the walk-forward relabel (F14) in the COMPARE audit backlog |
| R9 | Re-validate #257, #243, #335 with a 24-month lockbox, windows pinned | Direct test of R5 before adopting | ~20 min / ~30 min / 1–2 h runner time | OPEN |
| R10 | Drop or correct the Stage A.5 crowning step (crown from the tuning search; then the fixed reading after the search's data ends is a clean test) | §2.3 | Small (crown rule); reverses the 2026-07-20 decision | OPEN |
| R11 | Rank/gate on risk-shape stability across folds (volatility, drawdown), not profit alone; size live expectations with a haircut | Wiecki et al. (2016): backtest Sharpe R² ≈ 0.02 to live, volatility 0.67, drawdown 0.34; Suhonen et al. (2017): median 73% Sharpe haircut live | Moderate | OPEN |
| R12 | Consider a combinatorial purged cross-validation path (many walk-forward paths instead of one) for a distribution rather than a single number | López de Prado (2018) ch. 12 | Large — evaluate after R2/R7 | PARKED |

---

## 4. Open owner decisions (both dives)

- What COMPARE ranks on (R8) — until this is settled, the report's 1E walk-forward column keeps its
  current label and the COMPARE audit's F14 stays on hold.
- Lockbox length and pass rule (R5, R6) — test with R9 first.
- Crowning step (R10) and warm starts (R7) — both change every future verdict and force re-judging.
- Tuning span: no change recommended; shortening is not harmful but buys nothing.

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
