# ENGINE SCOPING - what the engine cannot express today

ELwA-FEATURES, 2026-10-07. Asked for by MANAGER #66 (standing order addendum 2, rule 4) within 24
hours of 10-05 and **delivered two days late** - the lane spent 10-05 and 10-06 on the ADJ-level
warning, pull provenance, the split guard and the push queue. Stating that plainly because the
queue order was mine to manage and the doc was the thing that slipped.

Every count and date below was measured today against the repo and the masters, not recalled.
Where something is an opinion rather than a measurement it says so.

---

## 1. BASKET JOB TYPE - the top item

**What exists.** `api/runner.py:602` dispatches on `job["type"]`, and there are exactly eight:
`backtest`, `grid`, `walkforward`, `validate`, `book`, `gate_validate`, `ai_optimize`,
`ai_evolve` (grep `jtype == "` in that file). Every one of them resolves **exactly one master**
through `find_master(instrument, timeframe, session, source)` and hands four price arrays to a
strategy's `run_backtest`.

**What that forbids.** A strategy whose unit of decision is "a set of names on a date" cannot be
expressed at all. There is no point-in-time universe, no per-name cost, no cross-sectional rank
step, and no way to say "hold the top k of these 500 from this date to that one". So the whole
stock-event class - the SETUPS work, the EDGAR/filing ideas, FINRA short interest, RESMOM's own
cross-section - can be researched in a harness but can **never reach Auto-Validate**, which is
the gate the house uses to decide anything. That is the single biggest expressiveness gap and it
blocks a whole family of work rather than one strategy.

**Shape I would build.** A `basket` job type whose contract is:

- a **universe file per rebalance date** (point-in-time, so a name that delisted is present
  before and absent after - a universe computed today and applied backwards is survivorship bias
  and the engine should make that impossible rather than discouraged);
- a **rank step** the strategy owns: given the date and the names' bars so far, return weights;
- **per-name cost in basis points**, not points - a stock basket's cost is proportional, and the
  current `cost_pts` subtracted once per trade cannot express it;
- the same metrics block every other job type returns, so RUNBOARD / COMPARE need no new reader.

**Open question for the owner, not for me:** whether a basket result is allowed on the same
leaderboard as a futures run. They are not the same risk object and ROC %/yr at $30k daily
drawdown may not mean the same thing across them.

## 2. SECOND-MASTER INPUTS

**Measured:** no job type and no engine entry point accepts a second master. `grep -n
"instrument2\|master2\|second_master\|aux_master\|instruments="` over `api/runner.py` and
`augur_engine/engine.py` returns nothing.

**What needed it this week.** KEEL and the order-flow work both want a second series beside the
traded one (a 10-second delta series, an index, a VIX-like level). Today a lane does this by
loading the second series itself inside the strategy file, which means: the engine's trial cache
cannot see it (so a sweep silently reuses a result computed on different auxiliary data - a real
correctness hazard, not a convenience one), the data fingerprint in `load_master_arrays` does not
cover it, and the walk-forward fold splitter does not know its date span.

**Shape:** `aux` as a dict of name -> master row on the job, resolved by the same `find_master`,
sliced to the same window, and passed to `run_backtest(..., aux={"delta": arrays})` only for
strategies that declare the kwarg - the same opt-in pattern `index` already uses in
`augur_engine/engine.py`. The fingerprint must fold in every aux master's fingerprint or the
cache will lie.

## 3. MONTHLY REBALANCE JOBS

Related to but not the same as the basket type: RESMOM's line ranks monthly and holds to the next
month-end. Today that is a bespoke script per lane. A `rebalance` schedule on a job (monthly /
weekly, with the hold file convention STRATEGY-BEATING already uses) would let the same strategy
be validated rather than only researched. Lower priority than the basket type because only one
line needs it today.

## 4. RESEARCH ROWS

Lanes produce results that are not Auto-Validate runs (a scan, an ablation, a null distribution)
and there is nowhere in the registry for them, so they live in chat messages and
`C:\EdgeLog\_anatomy_cache`. MANAGER's RUNBOARD already has a `research` list. The engine side of
this is small: a row type that carries a verdict, a prereg sha and a pointer to its artefacts,
with no metrics block pretending to be a backtest. Worth doing because a result nobody can find
again gets re-derived, which is how the family-seed hunt re-tested dead mechanisms.

## 5. SHARED SEAT-PIPELINE HARNESS - specified, waiting on FRONTIER's first cut

FRONTIER asked where it should live (#73); answered today (their #108). It goes at
`augur_engine/seat_pipeline.py` with `tests/test_seat_pipeline.py`, because four lanes import it
and `augur_engine` is where shared arithmetic already lives (`book.py`, `rolls.py`); `tools/` is
for scripts.

Their draft `C:\EdgeLog\_anatomy_cache\bookq\q19_a2.py` has the definitions right and they are to
be kept verbatim - `episodes`, `figs`, `dd`, `so`, `L = book + c x RES`. The **only** thing that
has to change is that it is shaped as a script: it calls `os.chdir` and `sys.path.insert` at
import, hardcodes `C:/EdgeLog` and `C:/Users` paths, computes `M` and `D` at module level, and
raises `SystemExit` on `argv`. Any one of those breaks the next lane that imports it.

Contract I asked for: no import-time work at all; every path and window passed in with a
documented default; `figures(series, start, end)`; `episodes(series, min_fraction=1/3)`;
`line_L(book_mtm, res, c_res=0.264)`; `seat_size(series, target_dd)`; a seedable
`random_name_null`; and `load_pinned_daily(path, expect_sha=...)` that raises - keeping the sha
refusal, but with the expected sha in the **caller's prereg**, not in the module, so a new pinned
file does not need a module edit. The parity numbers (93.81 / 3.816 / $44,849 and 120.82 / 3.916
/ $36,526) go in as module data and I add the test that asserts them, so a change to the
arithmetic fails the suite instead of someone's eye.

## 6. BACKTEST SPEED

`BACKTEST_SPEED.md` is current and nothing here supersedes it. One thing this week added:
`tools/affected_tests.py` (on main, `9f4e0d9e`) narrows a re-validation by what the tests
actually read, following imports transitively. It paid for itself on 10-05: 29 incoming changed
files narrowed to 20 test files, 582 tests in 1m49s against a 34-minute full suite. It is used by
the pre-push hook on a rejected push; **it is not yet used by anything a lane runs by hand**, and
it should be - that is a small, concrete win.

## 7. FOUND-LIST

Fixed today, pending a gate tomorrow morning (18:29 MST when written, past the 17:10 cutoff):

- **`api/spy_daily.py` wrote a nested array.** `bars: [[date, close], ...]` - Firestore rejects a
  nested array outright, so the module raised `InvalidArgument 400` on **every runner start since
  2026-10-02 15:59** and `users/{uid}/meta/spy_daily` was never written. The web app's vs-SPY
  overlay has read "not available yet" for five days. Now a flat map `closes: {date: close}`;
  both readers accept the old shape too so no stored history is discarded. **No test caught
  this**, so the fix adds one that walks the whole document for a nested array anywhere - the bug
  class, not the instance. Mutation-checked: reverting the shape fails it.
- **`api/market_calendar.py` closed two real trading days.** `_observed` moved a Saturday holiday
  to the preceding Friday and New Year's Day went through it, so 2021-12-31 and 2027-12-31 read
  as holidays while the NYSE was open both days. The exchange's own rule has the carve-out: a
  Saturday holiday is observed the preceding Friday **unless that Friday is the last business day
  of the year**, which for New Year's it always is. A Saturday Jan 1 is therefore not observed at
  all. Five dated cases added to the module self-test, including the Sunday shifts that must keep
  working.

Found this week and already on main: the gate-vs-rejection conflation that cost 43 minutes, the
13 short-thread-join tests (hand-searching found 4 of them), and the ADJ-level question that no
source scan can answer.

**Still open, not mine:** `wt.py` carrying VERSION/CHANGELOG edits from a lane commit (#69) -
TRADING-LOG owns the fix (#70) and I review it when it lands. It cost this lane a rebase conflict
on 10-05, so the diagnosis is confirmed from a second lane.

## 8. MONTH-END PULL TASK

`tools/rocfrontier/r17_resmom_pull.py` is STRATEGY-BEATING's (their #65) and refuses before
2026-10-30 by design. From 11-30 it needs `--hold
C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_line\hold_next.txt` (their #71), and the house ES
master must be refreshed through the month-end before their next-morning rank. The scheduled task
is mine to wire. **I have not wired it yet** and it is not due until 10-30; it goes in after the
seat-pipeline module. When wired it runs one command, writes the cache and posts its own inbox
line, same shape as the roll-watch task.

## 9. RUNBOARD MARKERS (MANAGER #72 item 2)

Two kinds of row are not what they look like and should be marked:

- NOISE lockbox cells taken from run docs are **cold-restart reloads** and drop roughly a quarter
  of the year's trades;
- ORB #234 / #239 / #257 walk-forward cells are **pinned-card in-sample replays**.

This is a `tools/runboard_watch.py` field plus a note where COMPARE-RUNBOARD renders. Small, and
worth doing before anyone quotes those cells forward again.

## 10. DATA DEFECTS - recorded beside the ES holes

**Verified today** against `augur_uploads/ADJ_NQ_1m_ETH.csv` (5,499,475 rows, 2010-06-06 ->
2026-10-07): exactly one hole longer than ten days, **2026-06-30 14:49 UTC -> 2026-08-06 04:09
UTC, 36.56 days** (10:49 -> 00:09 ET), which matches MANAGER #72 item 3 exactly. It sits after
the sealed year and inside the paper warm-up. Every other gap in that master is a holiday weekend
(3.0-3.6 days). There is no un-adjusted `NQ_1m_ETH.csv` in `augur_uploads` to compare against.

The NT capture holds 34,820 of 34,821 minutes for that window but is a different feed and is
**not** to be mixed into a master.

---

## RANKED ORDER

1. **Seat-pipeline module** - four lanes are blocked or duplicating; FRONTIER writes the numerics
   to the layout above, I own the contract, tests and ship.
2. **Basket job type** - the one gap that blocks Auto-Validate for a whole class. Biggest piece
   of work here; needs the owner's call on whether basket results share a leaderboard.
3. **The two found-list fixes** - done, gate tomorrow morning.
4. **Second-master inputs** - the cache-lying hazard makes this a correctness item, not a
   convenience one.
5. **RUNBOARD markers** - small, prevents a misread.
6. **`affected_tests.py` as a hand-run command** - small, saves every lane time.
7. **Month-end pull task** - not due until 10-30.
8. **Research rows** - stops re-derivation.
9. **Monthly rebalance jobs** - one line needs it today.
