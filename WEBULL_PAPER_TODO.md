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

**Related, not tracked yet:** `python -m api.cloud_signal --once` and `--loop` still have no
live-writer check, so running either by hand beside the runner's own thread gives the signal
record two writers. Worth its own item if the owner wants it.
