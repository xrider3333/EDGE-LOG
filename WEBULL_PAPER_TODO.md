# Webull paper trading — to-do list

**What this is.** The to-do list for the Claude session that runs Webull paper trading (the
"Paper: WB" chat; in EDGELOG it is **PAPER TRADE ▸ WEBULL QQQ**). The owner points that session
at this file. Item numbers are permanent: an item keeps its number when its status changes, and
new items go at the bottom. Every item says what it needs from the owner and how to tell it is
done.

## Board

| # | item | status | needs from owner |
| ---: | --- | --- | --- |
| 1 | Void the fake NOISE rows a test re-run wrote into the live signal record | **WAITING ON OWNER** | reply "apply the ledger repair" |
| 2 | Stop a hand-run signal step from writing beside the live signal thread | **OPEN** | nothing |

---

## 1. Void the fake NOISE rows a test re-run wrote into the live signal record

**Status: WAITING ON OWNER.** Build nothing that writes the live files, and apply nothing, until
the owner says "apply the ledger repair" in chat. Added 2026-09-14.

**What happened, in plain words.** At 00:55 ET on 2026-09-14 a background Claude session
re-ran Thursday Sept 3 through the QQQ signal engine and wrote into the live signal record (the
file on the PC that feeds Webull paper trading) instead of a scratch copy. It added four fake
NOISE rows: a start marker, two Sept 3 buys and a Sept 3 sell. The re-run stopped one bar before
its second buy's 15:55 sell, so the engine kept that buy as open, and at 09:31 ET the live engine
sent the sell. Webull paper trading held no NOISE position and ignored it: no order, trade or P&L
change. Leaving the rows cannot cause a trade, but this record is the evidence for dropping
NinjaTrader, and five of its rows are false.

**Already done**
- The cause is fixed on main (`cff0006`): `python -m api.cloud_signal --replay` runs on an
  isolated copy, `--live-paths` is the explicit opt-in and is refused while the live heartbeat is
  under 180 s old, and an offline `step()` without an explicit store raises.
- Exits are matched by trade id on main (`550055c`, another session): an EXIT closes only its own
  trade, and rows without a trade id are refused.
- The repair is specified, not built: `docs/CLOUD_SIGNAL_REPAIR_20260914.md` (`0aada10`). Owner
  page: https://claude.ai/code/artifact/2f53d0ac-798e-429a-9cf8-03d51e34d019

**The rows** (`C:\EdgeLog\cloud_signal\signals.csv`, data rows 8-12, header not counted)

| row | emitted_at (ET) | event | trade | written by |
| ---: | --- | --- | --- | --- |
| 8 | 2026-09-14 00:55:21 | SEED | NOISE_304 start marker | re-run |
| 9 | 2026-09-14 00:55:22 | ENTRY | long, Sept 3 09:40 @ 712.78 | re-run |
| 10 | 2026-09-14 00:55:23 | EXIT | long, Sept 3 10:05 @ 711.275 | re-run |
| 11 | 2026-09-14 00:55:25 | ENTRY | long, Sept 3 11:00 @ 713.5699 | re-run |
| 12 | 2026-09-14 09:31:00 | EXIT | long, Sept 3 15:55 @ 717.61 | live engine, closing row 11 |

**Re-check the spec against main before building.** The spec was written before `550055c`
landed, and three things differ now (checked read-only at 16:52 ET on 2026-09-14):
1. The live ledger header already carries a `trade_id` column (migrated 16:22 ET). The file is
   still 13 lines, CRLF, rows 8-12 unchanged, each with an empty trade id. Match rows on content
   and keep whatever header is on disk.
2. `state.json` trade records were still keyed the old way (entry price in the key), but the
   first step on the new code re-keys each leg to `trade_id_v1` and merges twin records (for
   example ENGU-Q's two 09-09 10:07 records). Compute the change from the files as they are at
   apply time; the spec's insertion positions for the 11 inert ORB records are informational only.
3. `api/qqq_exec.py` refuses ENTRY and EXIT rows without a trade id, so rows 8-12 can no longer
   be acted on even if something re-reads them. It still finds new rows by row count
   (`engine_cursor`), so the rows must still be relabelled in place and never deleted.

**The task, after the owner's OK**
1. Build `tools/cloud_signal_repair_20260914.py` as the spec describes (dry run by default,
   `--apply`, `--home`), plus a test that applies it to a copy of the live files.
2. Run `tests/test_cloud_signal.py`, `tests/test_qqq_exec_*.py`, `tests/test_qqq_cache_atomic.py`
   and `python tools/qqq_exec_smoke.py`; commit and push (a backend-only change can push direct).
3. Dry run against the live home: it must list exactly rows 8-12 and one `legs.NOISE_304`.
4. Apply inside the window: a weekday after 16:05 or before 09:25 ET, or a weekend. In that window
   the runner's signal thread writes only its heartbeat, so no runner restart is needed.

**Done when**
- Rows 8-12 read `VOID_*`, the line count is unchanged, and every other line is byte-identical to
  the backup.
- `legs.NOISE_304` is gone, the repair marker is present, and a second run prints "nothing to
  repair".
- At the next open there is exactly one new `NOISE_304 SEED` row and no NOISE_304 ENTRY or EXIT
  dated before that day.
- This item reads DONE and the memory note `qqq-cross-host-failover-state` records the apply.

**Constraints**
- Work in your own worktree (`python tools/wt.py new <name>`) and never commit in the shared
  checkout; other sessions are shipping to `api/qqq_exec.py` and `api/cloud_signal.py` today.
- Never restart the runner or the shadow adapter during market hours.
- Never edit the live files by hand; only the tool's backed-up, logged path.

**Related:** `python -m api.cloud_signal --once` and `--loop` still have no live-writer check, so
running either by hand beside the runner's own thread gives the signal record two writers. Now
tracked as item 2.

---

## 2. Stop a hand-run signal step from writing beside the live signal thread

**Status: OPEN.** Nothing needed from the owner: build, test and push. Added 2026-09-14 from the
owner's spec below. Checked read-only at ~16:55 ET on 2026-09-14 against origin/main `c61d3e8`:
the gap is still open, and no session branch or worktree held an unshipped edit to
`api/cloud_signal.py`.

**What can go wrong, in plain words.** The runner already steps the QQQ signal engine every 30
seconds and writes the live signal record. Running the engine by hand at the same time makes a
second writer of the same files. Two writers can send the same entry twice, or lose a trade's
bookkeeping so the engine sends its entry again after its exit. Webull paper trading would then
open a trade that never happened, and once the Webull broker mirror is armed that becomes a real
order. It is the same kind of accident as the two ledger contaminations so far (2026-09-09, and
2026-09-14 = item 1).

**Context.** `api/cloud_signal.py` is the QQQ-bar signal engine. The runner's primary process runs
`cloud_signal_thread`, which calls `step(fetch=True, paths=DEFAULT_PATHS)` every 30 s during RTH and
writes `<EDGELOG_HOME>/cloud_signal/heartbeat.json` every 30-60 s at all hours. `step()` loads
state.json, diffs, rewrites state.json and appends to signals.csv; `api/qqq_exec.py` consumes
signals.csv by row-number cursor and acts on ENTRY/EXIT rows emitted within 30 min. Commit
`cff0006` (2026-09-14) made `--replay` isolated by default and added `--live-paths`, which is
refused while `_live_writer_age_sec(DEFAULT_PATHS)` is under `LIVE_WRITER_FRESH_SEC` (180 s).

**The gap.** `python -m api.cloud_signal --once` (`cmd_once`) and `--loop` (`cmd_loop`) still step
into DEFAULT_PATHS with no check, so run by hand while the runner thread is live they become a
second writer of state.json / signals.csv. Two overlapping steps can both emit the same ENTRY (the
adapter ignores a second ENTRY while a lot is open), or a lost state update can drop a trade record
so the next step re-emits its ENTRY after its EXIT, which would open a phantom shadow lot, and a
real order once the Webull broker mirror is armed.

**The task**
1. Make `cmd_once` and `cmd_loop` refuse (exit code 2, a clear message naming the heartbeat age and
   path) when a live writer's heartbeat is fresh, reusing `_live_writer_age_sec` /
   `LIVE_WRITER_FRESH_SEC`.
2. `cmd_loop` writes the heartbeat itself, so check ONCE at startup, before its first heartbeat
   write.
3. Do NOT add a refusal to `cloud_signal_thread`: a stale heartbeat left by an old `--loop` must
   never stop the runner's live parallel run.
4. Add tests in `tests/test_cloud_signal.py` following the existing `fake_live` fixture pattern
   (monkeypatch `cs.DEFAULT_PATHS` to a tmp home; never touch C:\EdgeLog): a fresh heartbeat is
   refused and the stand-in live home stays byte-identical; a stale or absent heartbeat lets
   `cmd_once` proceed (monkeypatch `fetch_and_merge` to avoid the network).
5. Update the CLI section of the module docstring.
6. Before pushing, run `tests/test_cloud_signal.py`, `tests/test_qqq_exec_*.py`,
   `tests/test_qqq_cache_atomic.py` and `python tools/qqq_exec_smoke.py`.

**Found while filing (worth knowing, not part of the spec)**
- `main()` discards what `cmd_once()` and `cmd_loop()` return; only the `--replay` branch does
  `rc = ...; sys.exit(rc)`. Exit code 2 has to be passed through there as well.
- Helpers already sit beside `fake_live`: `_stamp_heartbeat(paths, age_sec)` and `_tree_bytes(root)`.
- `cmd_once` stamps the heartbeat itself, so a second hand-run `--once` within 180 s is refused too.
  That is safe; the message should say to wait it out.
- The design leaves one opening: a runner thread that starts AFTER a `--loop` is already running is
  not caught, because the thread must not refuse and the loop checks only at startup. If that
  matters, the loop could compare the heartbeat's `ts` with the one it last wrote and stop on a
  newer stamp. That is the owner's call.

**Done when**
- With a heartbeat under 180 s old, `--once` and `--loop` exit with code 2, name the heartbeat's age
  and path, and change no file under the home.
- With a stale or absent heartbeat, `--once` steps exactly as before.
- `cloud_signal_thread` is unchanged, so the runner needs no restart for this.
- The new tests and the four checks in task step 6 pass, and the change is on main.
- This item reads DONE with its commit.

**Constraints**
- Work in your own worktree (`python tools/wt.py new <name>`) and never commit in the shared
  checkout. A backend-only change may push direct after rebasing onto origin/main; the pre-push hook
  still runs the gates.
- Other sessions ship to `api/cloud_signal.py` and `api/qqq_exec.py` today (`550055c`, `cff0006`), so
  fetch and rebase right before pushing.
- Never restart the runner or the shadow adapter during market hours.
