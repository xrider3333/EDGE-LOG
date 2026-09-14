# Cloud signal ledger repair, 2026-09-14 replay contamination

**Status: PROPOSED, NOT APPLIED.** Nothing in this document has been done to the live files.
Applying it needs the owner's OK in chat. The code fix that stops this happening again is
already on main (commit `cff0006`, backend only, no web version bump).

## In plain words (for the owner)

- **What happened.** At 00:55 ET a background diagnosis session re-ran September 3 through
  the QQQ signal engine (the NT-free engine that feeds the Webull paper trading tab). The
  re-run wrote into the engine's live signal record instead of a scratch copy. It added four
  fake NOISE rows: a start marker, two September 3 buys and one September 3 sell.
- **Why it reached the paper book.** The re-run stopped at 16:00, one bar too early to see
  the second fake buy's 15:55 sell, so the engine remembered that buy as still open. At
  09:31 this morning the live engine found the sell and announced it. The Webull paper
  trading book read it, found no open NOISE position and ignored it. No order, no trade and
  no P&L changed. Had a real NOISE position been open, it would have been closed at the
  September 3 price.
- **Already fixed.** A re-run now always works on a throwaway copy. Writing into the live
  record needs an explicit switch and is refused while the live engine is running.
- **What the repair does.** It marks the five bad rows as void. They stay in the file,
  because the paper book finds new signals by row number and deleting rows would make it
  miss the next five real ones. It also clears the engine's NOISE memory, so at the next
  open the engine re-learns NOISE's history silently, exactly as it would have this morning.
- **What it does not touch.** The paper book's own files, Firestore, and the ORB and ENGU-Q
  memory (their leftovers from the re-run are inert and are only written into the log).
- **When.** Any weekday after 16:05 ET and before 09:25 ET, or any time at the weekend. In
  that window neither the engine nor the paper book touches these two files, so no runner
  restart is needed (a restart would kill any backtest in flight).

## Evidence (read-only checks, 2026-09-14 about 12:00 ET)

**Who ran it.** A background subagent of session `ca3282b4` (task: "why does the ORB leg
never fire on QQQ bars") ran `python -m api.cloud_signal --replay 2026-09-03` in the shared
checkout at 04:55:16 UTC. Its own output printed exactly the four NOISE_304 events below.
The CLI always replays all three crown legs, so ORB_R6 and ENGUQ_335 were stepped too; they
emitted nothing.

**`C:\EdgeLog\cloud_signal\signals.csv`** (13 lines, CRLF, header + 12 rows, unchanged since
09:31 ET). Rows 8-12 are the contamination; rows 1-7 are live and untouched by this repair.

| Row | emitted_at | leg | event | ref_time | ref_price | Origin |
|---|---|---|---|---|---|---|
| 8 | 2026-09-14T00:55:21.008295-04:00 | NOISE_304 | SEED | | | replay cold start, "absorbed 3" |
| 9 | 2026-09-14T00:55:22.286878-04:00 | NOISE_304 | ENTRY long | 2026-09-03T09:40:00-04:00 | 712.78 | replay |
| 10 | 2026-09-14T00:55:23.555021-04:00 | NOISE_304 | EXIT long | 2026-09-03T10:05:00-04:00 | 711.275 | replay |
| 11 | 2026-09-14T00:55:25.724420-04:00 | NOISE_304 | ENTRY long | 2026-09-03T11:00:00-04:00 | 713.5699 | replay |
| 12 | 2026-09-14T09:31:00.324783-04:00 | NOISE_304 | EXIT long | 2026-09-03T15:55:00-04:00 | 717.61 | LIVE engine, exit of row 11's trade |

**`C:\EdgeLog\cloud_signal\state.json`**

- `legs.NOISE_304` exists only because of the replay. Its `seeded: true` came from the
  replay's cold start on a window ending 2026-09-02. It holds 8 records: 3 absorbed by that
  cold start (08-27 13:05, 08-27 15:55, 08-28 11:00), 2 emitted by the replay (09-03 09:40,
  09-03 11:00, the latter flagged exited by the live 09:31 EXIT), and 3 the live engine then
  counted as stale (08-24 09:40 short, 08-25 09:50, 09-04 10:00) because the leg already
  looked seeded, hence `stale_skipped: 3`. Without the replay, the live engine's first tick
  at 09:30 would have absorbed all 8 silently and written one SEED row.
- Every NOISE_304 record already has `exit_emitted: true`, so the state cannot emit anything
  further for these trades. The repair is about an honest record, not about stopping a
  second bad signal.
- `legs.ORB_R6`: `stale_skipped: 28` very likely includes 11 inert records the replay added:
  06-30 (9 intraday entries), 07-02 10:25 short, 07-06 10:05 long, at insertion positions
  35-45. The inference rests on insertion order (they sit between the 09-11 live records and
  the 09-14 live batch) and on geometry: the replay ran the old 65-calendar-day window, whose
  left edge was 06-30 and crawled through that session as the replay's clock advanced, which
  is what an unsorted same-day cluster looks like. There is no pre-replay backup, so this is
  not provable.
- `legs.ENGUQ_335`: one stale record (08-28 09:30) of unprovable origin, inert.
- Top-level `generated_at`, `bar_source` and every leg's `last_bar_epoch` / `asof` have been
  rewritten by the live engine since; nothing to repair there.

**`C:\EdgeLog\qqq_exec` (the Webull paper trading shadow book)**

- `state.json` `engine_cursor` is 12 and no lot is open. The adapter seeded its cursor at 11
  rows at 09:25 (event `engine_seed`), so rows 8-11 were absorbed without acting. It consumed
  row 12 at 09:31: `C:\EdgeLog\qqq_exec_serve.log` reads `WARN engine EXIT for NOISE with no
  open shadow lot -- skipped`.
- `orders.csv` and `trades.csv` were last written on 09-04 and 09-05. Nothing was recorded,
  published or sent to a broker.

## Repair specification (for the session that applies it)

### Tool

`tools/cloud_signal_repair_20260914.py [--apply] [--home DIR]`, modelled on
`tools/qqq_exec_correct_20260903.py`. Dry run by default. `--home` defaults to
`EDGELOG_HOME`, so the tool can be proven on a copy first. It must ship with a test that
copies the live files into a temp home, applies, and asserts the verification list below.

### Preconditions (the tool refuses and exits 2 otherwise)

1. **No writer of either file can run during the apply.** Now (ET) is a weekday after 16:05
   or before 09:25, or a weekend. `heartbeat.json` is either older than 180 s (thread stopped)
   or fresh with `note == "outside session hours"` (thread alive and idle). No process has
   `api.cloud_signal` with `--loop`, `--once` or `--live-paths` on its command line.
   Why this is enough: the runner thread only calls `step()`, the sole writer of both files,
   from 09:30 to 16:00 ET on session days and only writes `heartbeat.json` otherwise; the
   shadow adapter only reads `signals.csv` from 09:25 to 16:05 ET on weekdays. No runner stop
   and no in-process hook are needed in this window. (The adapter does open `state.json` for
   a moment on every tick, at all hours, to read the bar source for its status panel. That is
   a reader, not a writer; it only matters for the replace step below.)
2. **Targets match.** Each of rows 8-12 matches the table above exactly on `emitted_at`,
   `leg`, `event`, `ref_time` and `ref_price`, or is already voided (see Idempotency).
3. **No swallowed exit.** `legs.NOISE_304` has no record with `exit_emitted: false`. If one
   exists (a NOISE trade taken live after 09:31 today and still open in the engine's
   memory), refuse unless the shadow adapter's `state.json` has no open `NOISE` lot, since
   the EXIT a reset swallows would then have been skipped anyway. Print the record either way.
4. **No half-applied state.** If `*.pre-repair-20260914` backups exist without the repair
   marker, proceed only when both live files are byte-identical to their backups (an earlier
   attempt aborted before changing anything). Otherwise stop for a human.

### Changes

**`signals.csv`: relabel five rows in place, never delete.** Same row count, same order,
same CRLF. Only `event` and `reason` change, and only on the five matched rows. Every other
byte is copied through.

| Row | event | reason (new) |
|---|---|---|
| 8 | SEED → VOID_SEED | `void 20260914: written into the live ledger by CLI --replay 2026-09-03 at 00:55 ET; ` + old reason |
| 9 | ENTRY → VOID_ENTRY | same prefix |
| 10 | EXIT → VOID_EXIT | same prefix |
| 11 | ENTRY → VOID_ENTRY | same prefix |
| 12 | EXIT → VOID_EXIT | `void 20260914: live EXIT of the replay's 2026-09-03 11:00 trade; ` + old reason |

Why in place: `api/qqq_exec.py` consumes the ledger by row-number cursor (currently 12), so
deleting five rows would hide the next five real signals from it. Both readers act on the
exact strings `ENTRY` / `EXIT` only (`_consume_engine_signals`, `_engine_confirms_entry`),
so `VOID_*` rows are inert, and `cloud_signal` itself only ever appends.

**`state.json`**

- Delete `legs.NOISE_304` entirely. Copy the removed object verbatim into the log.
- Add a top-level marker
  `"repairs": {"20260914_replay_contamination": {"applied_at": <ET iso>, "tool": "tools/cloud_signal_repair_20260914.py", "git_sha": <sha>}}`.
  `step()` rewrites the whole dict it loaded, so an unknown top-level key survives.
- `legs.ORB_R6` and `legs.ENGUQ_335`: no change. Write the inference above into the log.
  Removing the 11 ORB records would also be safe (the engine silently re-records any trade it
  still sees), but nothing reads that counter, so the repair leaves them alone.
- Effect: at the next session's first tick the engine cold-starts NOISE_304. It absorbs every
  trade in its window without emitting and appends exactly one `NOISE_304 SEED` row, the same
  thing it would have done at 09:30 on 2026-09-14.

**`qqq_exec`: no change.** The cursor stays valid because the row count does not change.

### Backups, log, idempotency

- Before any write: `shutil.copy2` to `signals.csv.pre-repair-20260914` and
  `state.json.pre-repair-20260914`.
- Write `state.json` first, then `signals.csv`, each to a `.tmp` sibling and `os.replace`d.
  Retry each replace up to 5 times, 200 ms apart: Windows refuses to replace a file another
  process has open, and the shadow adapter opens `state.json` briefly every tick. If
  `state.json` still cannot be replaced, nothing has changed yet, so exit non-zero. If
  `signals.csv` cannot be replaced after `state.json` was, restore `state.json` from its
  backup and exit non-zero.
- Append to `C:\EdgeLog\cloud_signal\corrections.log` (new file): ET timestamp, tool and git
  sha, the preconditions as observed (ET time, heartbeat age and note), each row before and
  after, the removed `legs.NOISE_304` object, and the ORB_R6 note.
- Idempotent: if all five rows are already `VOID_*` and the marker is present, print "nothing
  to repair" and exit 0. Any mixture (some rows voided, marker without voids, backups without
  marker) means a human looks first: print what was found and exit 2.

### Apply procedure

1. Owner's OK in chat.
2. Build the tool and its copy-based test, run the cloud_signal and qqq_exec suites, commit and
   push.
3. Dry run against the live home. It must list exactly rows 8-12 and one leg of 8 records.
4. In the precondition window, run with `--apply`.
5. Verify, then append a line to the memory file `qqq-cross-host-failover-state` (scenario F).

### Verification

- `signals.csv` has the same line count as its backup; rows 8-12 read `VOID_*`; every other
  line is byte-identical to the backup.
- `state.json` has no `legs.NOISE_304`, carries the marker, and its ORB_R6 and ENGUQ_335
  objects equal the backup's.
- A second run prints "nothing to repair".
- At the next open: exactly one new `NOISE_304 SEED` row, no NOISE_304 ENTRY or EXIT dated
  before that day, and no `engine EXIT for NOISE with no open shadow lot` line in
  `C:\EdgeLog\qqq_exec_serve.log`.

## Not in scope

- **Failover simulation scenario F stays open.** EXIT rows carry no trade id, so a stray EXIT
  closes whatever lot is open on that leg. This morning it did nothing only because no NOISE
  lot was open. Re-run `python tools/qqq_failover_sim.py` after any fix to that.
- The code fix (`cff0006`) closes the source: `--replay` runs on an isolated copy,
  `--live-paths` is refused while a live writer's heartbeat is under 180 s old, and an offline
  `step()` without an explicit store raises.
