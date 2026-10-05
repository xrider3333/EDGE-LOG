# GUARD r1 - PRE-REGISTRATION (written 2026-10-05, before any paper trade, report or cold run was read)

Lane: PAPER-NT8 (owner of the paper pipeline). Brief: docs/CLOUD_TO_MANAGER.md section 3 "GUARD r1" (cloud lane,
2026-10-05 00:30 UTC); assignment: MANAGER inbox #54 (2026-10-05). Harness: `tools/guard_r1.py`. Tests:
`tests/test_guard_r1.py`. **First binding read: cut-off 2026-10-30.** Every run before that is a DRY RUN and says so in
its header.

**What was read before this file was committed:** code (api/paper.py, api/paper_exitday.py, api/paper_bundle.py,
api/book_shadow.py, augur_engine/data.py, book.py), the committed docs, the master registry's file list and date spans
(optimizer_history.db csv_files rows), and the `data_source` field of ONE Firestore run document per run number named
below (users/<uid>/runs/<n>, to pin each leg's registered master). **No paper_trades document, no paper_reports
document, no paper_bundle chunk and no cold backtest output has been read.** Anything the first data read teaches us goes
in an AMENDMENT section at the bottom, dated, with the harness sha at the time; no number below is edited after the
first read.

## 1. What GUARD r1 is, and what it is not

The 2027 forward reads (VT, KEEL, the ORB seat shadows, Q4, the DIP shadows, the NOISE tilt vs its twin) all read the
FORWARD RECORD: users/<uid>/paper_trades and the nightly users/<uid>/paper_reports. That record is produced by
`api/paper.py` (`run_shadow` + `_run_one_uid`), which is not the backtest engine on the pinned masters:
`run_shadow` resolves its master with `find_master(instrument, timeframe, session)` and no source (so always the
no-adjust master, never a `db_adj_*` source a book job registered), warms raw legs up for only 150 days, appends a
NinjaTrader 10-second capture tail, and re-upserts every trade each night with `merge=True`. Nothing so far has checked
that record against a cold engine run. GUARD r1 does, once a month, read-only.

GUARD r1 never prints, stores or computes a line's cumulative P&L, ROC or Sortino. It compares record to reference leg
by leg and trade by trade, and reports counts, percentages, price differences in points, dollar differences between two
stored figures (never a level), and trade ids. It cannot leak a forward read because it never forms one.

## 2. The 13 legs, and why these

The brief says "13 legs" without a list. The registered 2027 reads are the book line, the VT line, the KEEL shadow, the
ORB seat shadows (orb314 / orb239 and the order-flow / roll-week reads that name #257), Q4, and the DIP shadows. The
legs those reads stand on, derived from `api/paper.py` (`_BOOK`, `_BOOK_SHADOW`), `api/book_shadow.py` (`SUM_SHADOWS`)
and the PREREG documents, are:

| # | leg key | why it is in GUARD r1 |
|---|---|---|
| 1 | ORB | BOOK #463 leg (`_BOOK`); also the control twin in every ORB seat read |
| 2 | ENGUQ_335 | BOOK #463 leg; also in the orb314 / orb239 lines |
| 3 | TTM_299_SSOF2 | BOOK #463 leg (weight 3); also in Q4 / orb314 / orb239 |
| 4 | NOISE_422 | BOOK #463 leg; in every sum line |
| 5 | TTM_458_KEEL | the KEEL shadow (`book_shadow`, `_BOOK_SHADOW`) |
| 6 | ORB_R6 | ORB #314: the orb314 and Q4 lines |
| 7 | ENGUQ_335_S1 | the Q4 line's ENGU-Q seat (cash-session entries) |
| 8 | ORB_239 | the orb239 line |
| 9 | DIP_ES_452 | DIP forward shadow on ES (docs/DIP_FORWARD.md) |
| 10 | DIP_NQ_433 | DIP forward shadow on NQ (docs/DIP_FORWARD.md) |
| 11 | ORB_257 | the "SEAT test": ORB #257 is the third seat shadow (PREREG order-flow and roll-week reads score it) |
| 12 | ENGUQ_335_S2 | round-62 sibling arm of S1, registered with it (ENGUQ_R62_FO) |
| 13 | NOISE_304 | the raw twin NOISE_422's forward read is judged against ("must keep beating its raw twin (NOISE_304)") |

**Judgment calls, stated so MANAGER can overrule them:** items 1-10 follow from the code and the lines directly. Item 11
is my reading of "the SEAT test". Items 12 and 13 complete the count to 13; the alternatives I rejected were
TTM_299_SSOF2R5 (a staged leg whose book flip was dropped) and ENGUQ_335_VC (a control with no registered read). The
harness takes its leg list from one table (`LEGS` in tools/guard_r1.py, mirrored in section 11 below and pinned by a
test), so swapping a leg is a one-row change plus an amendment here. The lines are not legs: they are checked in
section 8. A line that appears in a report document but is not registered in section 11 (a later `SUM_SHADOWS` addition) is
printed as a NOTE, never silently skipped, and is added here by amendment.

## 3. The cold reference, per leg

**Pinned master = the leg's REGISTERED source**, not whatever `find_master` resolves without a source:

- BOOK #463's four job legs: the source in book run #463's own leg list (also `api/book_shadow.py BOOK463_LEGS`):
  ORB `db_adj_rth`, ENGUQ_335 `db_adj_eth`, TTM_299_SSOF2 `db_adj_rth`, NOISE_422 `db_noadj_rth`.
- ORB_R6 and ORB_239: the ORB seat in book runs #473 / #478 (read from those run documents): `db_adj_rth`.
- ORB_257: PREREG_frontier_bookq line "Same master as #463's ORB (db_adj_rth)": `db_adj_rth`.
- ENGUQ_335_S1, S2: PREREG_frontier_bookq "same master (db_adj_eth)": `db_adj_eth`.
- TTM_458_KEEL: run #458 `data_source` and PREREG_ttm458_keel_shadow ("ES 30m RTH NO-ADJUST master"): `db_noadj_rth`.
- DIP_ES_452, DIP_NQ_433: runs #452 / #433 `data_source` (true rolls handled inside the files): `db_noadj_rth`.
- NOISE_304: run #304 `data_source`: `db_noadj_rth`.

**Window:** the whole master from 2010-06-07 (the leg's `history_from` is forced to 2010-06-07 for every leg, including
the raw legs the paper pipeline warms up for only 150 days), no date_to; the master file name, size, mtime and last bar
are recorded in the result.

**Trade extraction:** the paper pipeline's own function. The harness calls `api.paper.run_shadow(leg, cutoff)` with two
things swapped for the duration of the call and restored in a `finally`: `find_master` (returns the pinned source's
master) and `_load_fresh_ticks` (returns no capture tail). Everything after that, the gate (`paper_gate.apply_gate`,
including the frozen KEEL v12 of TTM_458_KEEL), `size_contract` sizing, `px_tuple6`, `_extract_trades`, the open-trade
flag (`paper_exitday.is_open`) and the `PAPER_START` filter, is `run_shadow`'s own code, not a copy. The leg's own
`params`, `cost_pts`, `mult`, `gate` and `strategy` from `PAPER_LEGS` are used unchanged (the cold run reproduces the
PIPELINE on a pinned master; it is not a re-validation of a run). A cold run whose `run_shadow` returns `ran_ok` false
or any warning other than the two the missing tail causes ("10s data file missing/empty", "zero fresh bars appended") is
INCOMPLETE for that leg, with the warning printed.

**Price basis.** The paper pipeline trades the no-adjust master plus a capture tail; a leg pinned to `db_adj_*` is
level-shifted by the back-adjustment (NQ 5m RTH: about 3x in 2010, +296.5 points for bars before the September 2026
roll). The harness therefore puts every cold price on the paper record's raw basis before comparing: it loads the
sibling `db_noadj_*` master (same instrument, timeframe, session) and subtracts `adj close - noadj close` at the last bar
common to both at or before the trade's entry bar (for the entry price) and exit bar (for the exit price). A leg pinned
to a no-adjust master has offset zero. A trade that crosses a roll therefore still differs by its true roll effect, and
that difference is real (section 6).

## 4. Population and matching

- **Forward trades** of a leg = trade documents whose entry falls on a US/Eastern calendar date in
  `[LEG_LIVE_FROM[leg], cutoff]` (api/paper.py `LEG_LIVE_FROM`; the document's own `backfill` flag must agree, and a
  disagreement is itself a FAIL: "backfill flag"). Trades before `LEG_LIVE_FROM` are BACKFILL: a backtest re-run, not
  forward evidence. They are compared with the same rules and printed on a separate "backfill (information only)" line
  that does not enter the verdict.
- **Matching key** = (leg, entry bar). The entry bar is the engine bar the trade enters on, stamped by the master's index
  (bar START, US/Eastern; the 10-second capture is END-stamped and `api/paper._resample` buckets it with `(t-1)//60`),
  read as the Unix second the trade document id carries (`pt_<leg>_<entryTime>`). No tolerance on the bar: a trade on the
  adjacent bar is one missing plus one extra, never a price-band match. The harness additionally prints how many
  missing/extra pairs sit exactly one bar apart, because that is the signature of a stamping shift.
- **Side** must be equal.
- **Closed vs open:** a trade is OPEN if either record flags it open (paper `open` true, or the cold trade's
  `paper_exitday.is_open`). For an open-either trade only side, entry bar and entry price are compared; exit bar, exit
  price and dollars are not (an open trade's exit is a mark at the last bar and moves every night).

## 5. In band, exact, and the four per-leg conditions

For a matched, both-closed trade the record is **in band** when ALL hold, on the raw basis of section 3:

1. entry price and exit price each within the band: **NQ 1.00 point, ES 0.50 point** (four NQ ticks, two ES ticks);
2. exit bar equal (same exit Unix second);
3. size equal within 1e-4 (paper size is derived as `pnl_usd / (pnl_pts * mult)` when read from the bundle, which does not
   carry `size`; read from a trade document it is the stored `size`);
4. dollars: `|d pnl_usd| <= (|d entry_px| + |d exit_px|) * mult * N * max(size) + 0.01`, N being the most contracts one
   trade can carry (1 for the NQ legs, whose size field carries sizing; 7 for the three TTM legs, whose ladder is up to 7
   contracts; 17 for DIP_ES_452 and 5 for DIP_NQ_433, whose dollars are `notional / price` units at a $100,000
   notional). This says dollars may differ only as much as the price differences allow; a cost, size or fill-model
   drift fails it.

A matched trade is **exact** when prices and size agree within 1e-6 and dollars within $0.01 (and, if both closed, the
exit bar is equal). Exact is a subset of in band.

Per leg, over the forward population, with `denominator` = paper forward trades minus EXPLAINED ones minus UNCOVERED ones
(section 6):

| id | condition | PASS needs |
|---|---|---|
| C1 | in band / denominator | >= 99% |
| C2 | exact / denominator | >= 95% |
| C3 | unexplained MISSING (cold trade, no paper trade) | 0 |
| C4 | unexplained EXTRA (paper trade, no cold trade) | 0 |
| C5 | post-close changes (section 7) | 0 |

With fewer than 100 trades the 99% rule means zero out-of-band trades; that is intended.

## 6. What "explained" means (and what is not)

A trade difference is explained, and leaves both numerator and denominator, only in these cases:

- **E1 roll artifact:** the paper trade (leg, entry Unix) is listed in `tools/data/paper_roll_artifacts.json` (the
  committed September 2026 splice list). It may be EXTRA, or matched but out of band. A cold-only trade is explained only
  if the same leg has a listed artifact on the same US/Eastern calendar day.
- **E2 open:** a trade open in either record is compared on entry only (section 4); nothing is "missing" because its exit
  is not final.
- **E3 before the live date:** trades before `LEG_LIVE_FROM` are backfill (section 4), not part of the verdict.
- **E4 after the cut-off:** trades with an entry date after the cut-off are excluded on both sides.

Everything else is unexplained. Two situations are not "explained" and not a PASS either; they make the leg
**INCOMPLETE**:

- **UNCOVERED:** a paper trade whose entry is after the cold master's last bar (the capture tail covered it; the master
  cannot). Also INCOMPLETE if the master's last bar is before the cut-off date.
- the cold run failed (section 3), or the paper bundle is older than the cut-off day's 16:00 ET (the nightly run that
  closes the cut-off day had not written it yet), or there is no report document for a trading day in the window.

A leg with zero forward trades in the paper record AND zero in the cold reference, everything else clean, reads **NO
TRADES** (nothing to verify; it neither passes nor fails). Zero paper and a non-empty cold set is C3 FAIL.

**Known before any data is read, stated so a later note is not a surprise:**

- DIP_ES_452 and DIP_NQ_433 go live 2026-10-05 (`LEG_LIVE_FROM`); at a cut-off before that date they have no forward
  trades and read NO TRADES, with their backfill compared for information.
- The three TTM legs trade about 16 times a year; a short window may hold none.
- The ENGUQ_335 paper leg books `cost_pts` 0.533; BOOK #463's registered ENGU-Q leg books 0.783 (the 24-hour cost). The
  cold run uses the paper leg's own cost (section 3), so this does not fail anything; the harness prints it as a NOTE
  (config drift versus BOOK463_LEGS: strategy, instrument, timeframe, session, params, cost_pts, mult), for the four
  legs BOOK463_LEGS registers.
- The paper pipeline warms raw legs up 150 days; the cold run uses the full history. Any trade this changes is an
  unexplained difference and a FAIL by design: it is exactly what the skeptic judge asked about.

## 7. Post-close changes (C5)

A closed trade must not change after the day it closed. Two detectors, both must be clean:

1. **Report versus trade documents (stateless).** For every report day D <= cut-off and every one of the 13 legs the
   report document carries, `legs[leg].pnl_usd` must equal the sum of `pnl_usd` over the leg's CLOSED trade documents
   whose `close_day` is D, within $0.01. The nightly run re-merges only the previous 7 calendar days of reports
   (`api/paper_exitday.py LOOKBACK_DAYS`), so a closed trade that is re-upserted with a different exit or dollars (or
   pruned) after that leaves its old day's report behind and shows here. The mismatch names the leg, the day, the
   dollar difference and the trade ids that closed that day. Report days before **2026-10-02** (the exit-day cut-over,
   owner GO of that date) booked money by ENTRY day; they are tallied on an information line and do not enter the
   verdict.
2. **Snapshot diff (stateful).** Every run stores, in its result JSON, a SHA-1 digest per closed trade (`exit Unix | exit
   price | dollars`, no readable dollars). The next run loads the newest earlier snapshot (cut-off strictly smaller) from
   `C:\EdgeLog\guard\` and fails any trade closed in that snapshot whose digest is now different or absent. The first
   run has no prior snapshot and says so ("baseline written"); a dry run's snapshot counts as the baseline for the next
   run.

## 8. Lines (L1 - L3)

Lines are checked on every report day D with a report document, D from the line's start date to the cut-off:

- **L1 sum of legs.** For `book`, `book_shadow`, `book_shadow_q4`, `book_shadow_orb314`, `book_shadow_orb239`,
  `book_shadow_noise125` (added to `SUM_SHADOWS` by FRONTIER Q8 on 2026-10-05, from 2026-10-06; its legs are all among the 13): the
  stored `pnl_usd` equals the sum over the doc's OWN `weights` of `weight * legs[k].pnl_usd` (a leg absent from the doc
  counts $0, as `rebucket_payload` does), within **$0.01**. A mismatch prints the day, the line and the dollar DIFFERENCE
  only.
- **L1b composition.** From each line's start date (book 2026-09-28; book_shadow 2026-09-29; q4, orb314, orb239
  2026-10-01; noise125 2026-10-06) the doc's `weights` must equal the registered weights (section 11; a test pins them to `api/paper.py` `_BOOK`,
  `_BOOK_SHADOW` and `api/book_shadow.py` `SUM_SHADOWS`). A different composition is a FAIL.
- **L2 VT identity.** From 2026-09-30, `book_shadow_vt.pnl_usd` equals `book_shadow_vt.multiplier * book.pnl_usd`
  within $0.01 (the exit-day re-merge writes exactly that).
- **L3 VT multiplier, cold.** `api/book_shadow.book463_valued_daily` is run ONCE from three years before the first VT
  day through the cut-off on #463's pinned job legs (it refuses a different source and a failed daily valuation), and
  `vt_multipliers` is applied. The stored multiplier for each day D is a PASS when it equals the cold multiplier rounded
  to 0.1, or when the cold UNROUNDED value is within 0.055 of the stored one (the slack is one rounding step plus 0.005,
  for the recent bars a feed restates). Otherwise FAIL naming the day and both multipliers (a multiplier is not P&L).

A line is **READ FROM COLD REFERENCE** (printed) until it passes: for a line whose legs are not all PASS or NO TRADES,
or whose L1-L3 fails, the harness writes the cold reference trade rows of the non-passing legs (and only those) to
`C:\EdgeLog\guard\cold_<cutoff>.json`; no cold P&L is stored for a passing leg. The line-to-leg map is in section 11.

## 9. Verdicts, exit code, output

Per leg: **PASS**, **FAIL** (any of C1-C5), **INCOMPLETE**, **NO TRADES**. Per line: **PASS** / **FAIL** /
**INCOMPLETE** (a report day missing). Overall: FAIL if anything FAILs (exit code 1); else INCOMPLETE if anything is
(exit code 2); else PASS (0). "Binding" is printed only for a run that is not `--dry-run` with a cut-off on or after
2026-10-30; everything else prints `DRY RUN - NOT THE BINDING READ (first binding read 2026-10-30)` in its first line.

The default cut-off is the last trading day (NYSE calendar, `api/market_calendar`) of the latest month that ended
strictly before today.

Output, per leg, one line: key, pinned source and its last bar, forward trades in the paper record, matched, in band %,
exact %, missing, extra, open, explained, uncovered, post-close, verdict. Under a FAIL: one line per defect naming the
statistic, the leg and the trade ids (`pt_<leg>_<entry Unix>`), and for price differences the difference in points. Then
the lines, the notes (config drift, backfill information, legacy-convention days), the paper bundle's age, Firestore
reads used, the prereg's SHA-256 and the harness's git revision. **Never printed and never stored:** a cumulative P&L,
a ROC, a Sortino, any leg's or line's dollars level. A test scans the rendered output and the result JSON for them.

Writes: stdout and one JSON under `C:\EdgeLog\guard\` (`guard_r1_<cutoff>_<utc timestamp>.json`, carrying the result and
the snapshot digests). Firestore: read-only (the client is wrapped so any write method raises). The runner, the live
strategies, NinjaTrader and the masters are never touched; `run_shadow` is called as a pure function and writes
nothing.

## 10. Limits, said plainly

- GUARD r1 checks that the record is what the pipeline's own arithmetic gives on pinned data. It does not check that the
  pipeline's logic equals NinjaTrader's fills (the reconcile tool does that) or that a leg is a good strategy.
- A cold reference built from a master the vendor later restates will differ from a record written before the restatement;
  the price band absorbs small restatements, and anything larger is reported, not hidden.
- With few trades the percentages are coarse; the zero-missing and zero-extra rules carry the weight.
- The ADJ-master cold reference and the no-adjust record can legitimately differ on a trade that crosses a roll; that is
  a FAIL until it is added to the artifact list by the owner, never silently excused.

## 11. Constants (machine-readable; a test compares this block with the harness)

<!-- GUARD_R1_CONSTANTS_BEGIN -->
```json
{
  "version": "GUARD_R1_v1",
  "first_binding_cutoff": "2026-10-30",
  "history_from": "2010-06-07",
  "band_pts": {"NQ": 1.0, "ES": 0.5},
  "exact_tol": {"px": 1e-06, "size": 1e-06, "pnl_usd": 0.01},
  "band_size_tol": 0.0001,
  "pnl_band_floor_usd": 0.01,
  "in_band_min": 0.99,
  "exact_min": 0.95,
  "unexplained_missing_max": 0,
  "unexplained_extra_max": 0,
  "post_close_changes_max": 0,
  "line_tol_usd": 0.01,
  "vt_multiplier_slack": 0.055,
  "exitday_cutover": "2026-10-02",
  "vt_first_day": "2026-09-30",
  "line_from": {"book": "2026-09-28", "book_shadow": "2026-09-29", "book_shadow_q4": "2026-10-01",
                "book_shadow_orb314": "2026-10-01", "book_shadow_orb239": "2026-10-01",
                "book_shadow_noise125": "2026-10-06"},
  "legs": [
    {"key": "ORB", "pinned_source": "db_adj_rth", "n_contracts": 1},
    {"key": "ENGUQ_335", "pinned_source": "db_adj_eth", "n_contracts": 1},
    {"key": "TTM_299_SSOF2", "pinned_source": "db_adj_rth", "n_contracts": 7},
    {"key": "NOISE_422", "pinned_source": "db_noadj_rth", "n_contracts": 1},
    {"key": "TTM_458_KEEL", "pinned_source": "db_noadj_rth", "n_contracts": 7},
    {"key": "ORB_R6", "pinned_source": "db_adj_rth", "n_contracts": 1},
    {"key": "ENGUQ_335_S1", "pinned_source": "db_adj_eth", "n_contracts": 1},
    {"key": "ORB_239", "pinned_source": "db_adj_rth", "n_contracts": 1},
    {"key": "DIP_ES_452", "pinned_source": "db_noadj_rth", "n_contracts": 17},
    {"key": "DIP_NQ_433", "pinned_source": "db_noadj_rth", "n_contracts": 5},
    {"key": "ORB_257", "pinned_source": "db_adj_rth", "n_contracts": 1},
    {"key": "ENGUQ_335_S2", "pinned_source": "db_adj_eth", "n_contracts": 1},
    {"key": "NOISE_304", "pinned_source": "db_noadj_rth", "n_contracts": 1}
  ],
  "lines": {
    "book": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_458_KEEL": 1.0, "NOISE_422": 1.0},
    "book_shadow_q4": {"ORB_R6": 1.0, "ENGUQ_335_S1": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow_orb314": {"ORB_R6": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow_orb239": {"ORB_239": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow_noise125": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.25},
    "book_shadow_vt": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0}
  }
}
```
<!-- GUARD_R1_CONSTANTS_END -->

## AMENDMENTS

**Amendment 1 - 2026-10-05, after the first (dry-run) read of cut-off 2026-09-30. No threshold, band, rule or leg changed.**
Prereg commit 220e9064, harness af3c0f7f.

1. *Harness correction (conforms the code to section 8):* a line whose start date is after the cut-off has an empty
   window. The first run reported such lines (q4, orb314, orb239, noise125 at a 2026-09-30 cut-off) INCOMPLETE because
   `sessions_between` swaps reversed arguments; they now read NO DAYS. A test pins it.
2. *Post-hoc diagnostic (not a rule; labelled so):* the dry run's one leg FAIL, ENGUQ_335, was re-run by hand on three
   masters. The paper record equals the cold run on the NO-ADJUST ETH master 13 of 13 forward trades, with the full
   history and with the 150-day warm-up alike; it equals the cold run on the registered ADJ master 1 of 13. So the cause is
   the master (the strategy's lookbacks span the September roll, and the no-adjust master carries the fake gap), not the
   warm-up, the capture tail or a stamping shift. Under section 6 this stays a FAIL: "the ADJ-master cold reference and
   the no-adjust record can differ ... a FAIL until the owner lists it". It is a finding about the pinned source, for
   MANAGER, not an excuse built into the harness.
3. *Note:* `book_staged` appears in the reports and is not registered here; the harness prints it as a NOTE (section 2).
