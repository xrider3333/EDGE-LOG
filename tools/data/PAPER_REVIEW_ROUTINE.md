# Daily PAPER review routine

Runs every weekday after the close as a scheduled Claude session (task
"edgelog-paper-eod-review"). It reviews the day's shadow/paper trading and writes the
verdict into Firestore. The report itself is written by the always-on runner
(`api/paper.py`, `users/<uid>/paper_reports/{date}`, status `runner_done`) around 16:10
ET; this routine reads that report, gathers supporting facts, and turns
`status: 'runner_done'` into `status: 'reviewed'` with a verdict attached.

The session runs unattended, so it uses exactly ONE script and writes exactly ONE file.
The shared checkout's `.claude/settings.json` gives standing permission for those two
things and nothing else. Any other command stalls the run on an approval prompt nobody
is there to click - which is exactly how this routine's predecessor stalled ~5 seconds
into nearly every run since late August (its first Bash command wanted a permission
nobody had granted, and the run still reported "succeeded").

## What is actually being reviewed (read this before trusting an old prompt)

Two systems, not one:

1. **NT8 shadow legs** (`api/paper.py`) - the engine re-run nightly on fresh NQ data
   against ~35 leg configurations (`PAPER_LEGS`), written to
   `users/<uid>/paper_reports/{date}` (per-leg `n_signals`, `pnl_usd` for THAT DAY,
   `n_since_start`, `bars_appended`, `data_fresh_thru`, `warnings`) and
   `users/<uid>/paper_trades` (one doc per trade, `run_date` field for the day query).
   The report doc also carries `blend` (ORB + ENGU-Q 1:1), `book` (the owner's
   multi-leg book, currently ORB + ENGU-Q-309 + 3x the TTM leg, see `api/paper.py`'s own
   comments for the latest swap), `live` (raw NT demo fills, Layer 1), `reconcile`
   (Layer 3, `api/paper_reconcile.py` - already computed, just read it) and `gate_live`
   (Layer 4, `api/gate_audit.py` - also already computed). Do not re-derive the
   reconcile or gate-audit verdicts by hand; they are already on the report doc.
2. **The Webull paper book** - live NQ→QQQ share execution on Webull's paper account
   from an Oracle cloud VM (`api/qqq_exec.py`, legs `ORB` (#314), `ENGUQ` (#335),
   `NOISE` (#382), KEEL v12 sizing). It publishes ONE continuously-overwritten snapshot
   doc at `users/<uid>/meta/qqq_exec` - **not a per-day history**. `cum_pnl` on that doc
   is genuinely cumulative since the book's `live_from` date, and `trades_all` (capped,
   newest first) can be filtered by date for a specific day's closed trades, but
   `rails`/`keel`/`health`/`readiness`/`broker`/`parity` are the CURRENT state only - when
   reviewing a catch-up day that is not today, those fields describe today, not the
   reviewed day, and facts.json says so explicitly.

The old prompt (superseded, do not use it) described ORB #125 / ENGU-Q #149 and a "QQQ
shadow" that mirrored NT fills (`api/qqq_paper_publish.py` / `tools/qqq_paper.py`,
Firestore `users/<uid>/meta/qqq_paper`) - that module is a separate, older signal-only
simulator (stale leg configs) still wired into the runner but not the thing the owner
means by "Webull paper trading" today. Mention it only if it is genuinely relevant; the
roster above is the one to report on.

## Steps (the scheduled session follows these exactly)

1. `python tools/paper_review_routine.py start`
   - `RESULT: NOTHING TO REVIEW` - done, nothing to do.
   - `RESULT: MISSING REPORT <date>` - the runner never wrote that day's report. Report
     the failure instead of a review: facts.json carries `runner_log_matches`, a
     full scan of `C:\EdgeLog\runner.log` for that date (the file is 380+ MB and grows
     fast, so `start` only pays that cost when a report is actually missing).
   - `RESULT: REVIEW <date>` - go to step 2.

   **Date picked:** the last 5 US trading days (weekends and NYSE holidays skipped via
   `api/market_calendar.py`), walked OLDEST -> NEWEST, stopping at the first day that is
   not already `reviewed` - so a run of missed days catches up one day per `start` call
   (run it again after `finish` to pick up the next one). If that first not-yet-reviewed
   day has no report doc at all, that is MISSING REPORT, not skipped past in favour of a
   later day that happens to have one: a missing report is a runner failure and a later
   day being fine does not explain it away.
2. Read `tools/data/paper_review_inbox/facts.json` (and the human-readable
   `facts.md`). Write `tools/data/paper_review_inbox/verdict.json`:
   ```json
   {
     "date": "2026-09-24",
     "verdict": "Plain English, <=120 words: what fired, whether data was fresh, what "
                "any warnings mean, whether the day looks consistent with backtest "
                "behavior, and anything the owner should act on.",
     "nt_book": {"ORB": "one short sentence per leg or group worth calling out", "...": "..."},
     "webull_book": {"orders": 4, "trades": 2, "realized_pnl": -38.5, "rail_trips": 0,
                     "feed_stale_minutes": 0, "verdict": "one short sentence"},
     "owner_actions": ["anything the owner should actually look at or do - can be empty"]
   }
   ```
   - `date` must exactly match facts.json's date.
   - `verdict` <= 120 words.
   - `nt_book`: one short string per leg/topic worth mentioning - not every one of the
     ~35 legs needs a line; group the quiet ones ("everything else: flat, no warnings").
   - `webull_book`: the five numeric/verdict fields; a numeric field may be `null` when
     the book has no data for that day (e.g. reviewing a date before 2026-09-20, or the
     cloud box was down) - say why in `verdict`.
   - `owner_actions`: plain-English list, can be empty.
   - Use the trade lists, reconcile/gate_live blocks and diagnostics already in
     facts.json - do not invent numbers that are not there.
3. `python tools/paper_review_routine.py finish` - validates verdict.json (`FIX:` lines
   name exactly what to fix; edit and run finish again), then merge-writes into
   `users/<uid>/paper_reports/{date}`: `status: 'reviewed'`, `reviewedAt` (server
   timestamp), `verdict`, `nt_book_review`, `webull_book_review`, `owner_actions`.
   MERGE ONLY - every other field already on the report doc (legs, trades, reconcile,
   etc.) is left exactly as the runner wrote it. `RESULT: WRITTEN <date>` when done.

`python tools/paper_review_routine.py abort` throws a run away; its inbox files are kept
under `tools/data/paper_review_inbox/_aborted/`.

**Proving the permissions without publishing anything:** `start --selftest` builds one
fixture day (2026-08-11, entirely fabricated, no Firestore read) - write verdict.json for
it, then `finish --dry-run` runs every step except the Firestore write (a selftest finish
is always a dry run regardless of `--dry-run`).

## Why `--date` exists

`start --date YYYY-MM-DD` reviews a specific day directly, bypassing the oldest-unreviewed
scan - still refuses a non-trading day and still reports MISSING REPORT if that day's
report does not exist. Unlike the scan, an explicit `--date` will re-gather facts for an
already-`reviewed` day (an explicit ask overrides the "already done" skip); the scan never
does this on its own.

## Data sources

- `users/<uid>/paper_reports/{date}` - the day's NT8 report (see above).
- `users/<uid>/paper_trades` (query `run_date == date`) - that day's shadow trades.
- `users/<uid>/meta/qqq_exec` - the Webull book's live snapshot (see above).
- `C:\EdgeLog\runner.log` - `[paper]` lines (only fully scanned on MISSING REPORT).
- `C:\EdgeLog\nt_recover.log` - NinjaTrader bridge outage lines.
- `C:\EdgeLog\gate_live.log` - the live ML gate's own decision log.
- `roll_artifact` - if a trade doc or Webull trade row ever carries this flag (another
  agent may add it retroactively for 2026-09-14..09-16 roll-splice days), it is surfaced
  in `facts.json.nt_book.roll_artifact_trade_ids` and should be called out, not silently
  folded into "clean" totals.

## Cumulative totals

`facts.json.nt_book.cumulative` sums each daily report's `legs[k].pnl_usd` / `blend.pnl_usd`
/ `book.pnl_usd` from `PAPER_START` (2026-08-11) through the reviewed date - one Firestore
read per trading day in range (a few dozen by now, well inside the free-tier budget). The
Webull book's `cum_pnl` field on `meta/qqq_exec` is already cumulative (computed from the
full trade history each publish) and is used as-is.
