# Webull paper trading — to-do list

**What this is.** The to-do list for the Claude session that runs Webull paper trading (the
"Paper: WB" chat; in EDGELOG it is **PAPER TRADE ▸ WEBULL QQQ**). The owner points that session
at this file. Item numbers are permanent: an item keeps its number when its status changes, and
new items go at the bottom. Every item says what it needs from the owner and how to tell it is
done.

## Board

| # | item | status | needs from owner |
| ---: | --- | --- | --- |
| 1 | Void the fake NOISE rows a test re-run wrote into the live signal record | **DONE** (2026-09-25, applied on the box after the close) | nothing |
| 2 | Stop a hand-run signal step from writing beside the live signal thread | **DONE** (2026-09-25, 307a128, live on the box) | nothing |
| 3 | Keep the QQQ lease fresh when status publishes are throttled | **DONE** (2026-09-25, 7cdd490, live on the box) | nothing |
| 4 | A second signal engine ran on the cloud box for 12 hours: one duplicate NOISE entry row to judge | **DONE** (2026-09-25, row voided with item 1) | nothing |
| 5 | NOISE bought in the book but never at Webull: re-send a blocked buy, never sell what Webull does not hold, retry a same-instant duplicate | **DONE** (2026-09-21, after-close check passed) | nothing |
| 6 | ML filter for the Webull book, NOISE first (then ORB, then ENGU-Q) | **CLOSED** (2026-09-25): no filter passes on any leg | optional: a resizing-only test, pre-registered |
| 7 | One Webull account, three strategies: net the orders | **DONE** (2026-09-23, d14e2a3) | nothing; watch the first split order |
| 8 | Live positions + account equity, honest warnings, plain-English broker errors | **DONE** (2026-09-23) | nothing; watch the live feed's load at the open |
| 9 | KEEL v12 on top of run #382 on the NOISE leg | **LIVE** (2026-09-24, 5326d02) | nothing |
| 10 | Fire orders at the bar close from the live price feed | **SHADOW** (2026-09-25, 4aaabc8, live on the box, switch off) | after about a week of shadow numbers: switch it on or not |
| 11 | Re-price trades from Webull's own tape, not Yahoo | **DONE** (2026-09-25, 9805414, live on the box) | nothing |
| 12 | NOISE's volatility skip never fires live | **PARTLY DONE** (2026-09-26): NOISE asks for 262 sessions; the box holds 77 | an intraday data key (e.g. a free Alpaca account) for a year of QQQ 5m bars |
| 13 | Share cap vs #382 x KEEL sizes | **DONE** (2026-09-24: 60 per leg, 80 total) | nothing |
| 14 | Taking the book live: the go-live punch list (WEBULL_GO_LIVE.md) | **IN PROGRESS** (2026-09-26: 1.1-1.4, 1.8, 1.9, 3.6-3.8, 3.11 done; see its status note) | decisions in its section 2: account, size and the day-trade rule, shorting, token, KEEL stack, ENGU-Q; a private alert topic |
| 15 | ORB never enters before about 14:05 ET: the half-day test drops today's unfinished session | **DONE** (2026-09-26, 9a82613, live on the box) | nothing; watch ORB's first morning entries |
| 16 | Entries and exits go out one 5-minute bar after the backtest's fill | **OPEN** (2026-09-26, confirmed from the live record) | nothing |
| 17 | Order-path rework (unknown outcomes, fill status, split orders, separate live state, safe disarm) | **OPEN** (2026-09-26: built, not shipped) | nothing |

---

## 1. Void the fake NOISE rows a test re-run wrote into the live signal record

**Status: DONE 2026-09-25.** Applied on the cloud box at 16:07 ET on the owner's "fix all now", with both
services stopped and the book flat. The dry run listed exactly rows 8-12 and row 24 (item 4) and
the NOISE_304 leg record; `--apply` voided them (VOID_SEED / VOID_ENTRY / VOID_EXIT, reason kept),
removed the leg record, and wrote backups (`signals.csv.pre-repair-20260914`,
`state.json.pre-repair-20260914`) and the audit trail `cloud_signal/corrections.log`. Tool:
`tools/cloud_signal_repair_20260914.py` (0260c73).

**Earlier status: WAITING ON OWNER.** Build nothing that writes the live files, and apply nothing, until
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

**Status: DONE 2026-09-25** (307a128; live on the box from the 16:07 ET restart). A hand-run signal step
now refuses to run beside the live signal thread and exits with code 2.

**Earlier status: OPEN.** Nothing needed from the owner: build, test and push. Added 2026-09-14 from the
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

---

## 3. Keep the QQQ lease fresh when status publishes are throttled

**Status: DONE 2026-09-25** (7cdd490; live on the box from the 16:07 ET restart). The same commit puts
the engine's KEEL size on the trade row and stops the false morning tick-gap warning.

**Earlier status: BUILT, NOT SHIPPED (2026-09-25, worktree `bookfix`).** Needs nothing from the owner.
Added 2026-09-14 from the owner's chat of the same name, which was closed before any work
started (no worktree, branch, edit or commit).

**What was built (design (a), "advertised cadence" -- picked over "(b) lease-only renewal" as
the CONSERVATIVE choice: (b)'s extra merge write would need to fire roughly every 45s around the
clock, ~13x more writes than today's 600s off-hours cadence, undoing most of the write-quota
savings this throttle exists for; (a) costs zero extra writes).** A publishing host now stamps
its lease with `renew_every_sec` -- the same interval `_should_publish` just used for that
publish (`api/qqq_exec.py`'s `_publish_interval_for`, wired through `publish_async`/
`publish_now` -> `_Publisher.write_one` -> `_do_set`). A claimer (`_lease_claimable`, and so
`_check_lease`/`_claim_lease`, plus `_check_lease_for_broker`'s own foreign-claim check) judges
staleness against `max(LEASE_STALE_SEC, 1.5 x that advertised cadence)` instead of the fixed 90s
alone (see `_lease_stale_bound`), so a healthy off-hours holder is no longer mistaken for dead. A
lease doc from before this shipped, or from a caller that never advertised a cadence, falls back
to the old fixed 90s bound exactly as before -- never less safe. `_LeaseHolder.write_mode` /
`within_hold` / `send_gate` and the suspended-loop re-claim were reviewed and left unchanged (see
the LEASE_STALE_MARGIN comment in `api/qqq_exec.py` for why each is unaffected).
`tools/qqq_failover_sim.py` scenario G exercises the fixed behaviour directly; new tests in
`tests/test_qqq_exec_lease.py` and `tests/test_qqq_exec_publish_throttle.py` cover the bound and
the advertised value end to end. `deploy/cloud/README.md`'s "Two machines, one shadow book"
section and its handover-timing estimate (step 8) are updated to match.
Not yet shipped to `main` (built in a worktree per this session's instructions) and not observed
against the live two-host setup or the Linux CI job's 35-failure baseline -- both still open
before this can read fully DONE.

**What happened, in plain words.** Only one machine may run the Webull paper trading book at a
time. The machine running it proves it is alive by refreshing a timestamp (the "lease") each time
it updates the status the QQQ tab reads, and another machine may take over once that timestamp is
90 seconds old. A later change cut how often that status is written, to save the daily write
quota: with the Webull order mirror switched OFF it goes out once a minute during the session and
once every 10 minutes outside it. So after the close a healthy PC looks dead most of the time.
With one machine that is harmless. With the cloud VM running it is not: the VM could take the book
while the PC still runs (both books then run for up to 10 minutes), and overnight the VM looks
dead too, so any PC relaunch (a runner restart, or the 06:05 premarket check) would take the book
back from the VM, which breaks what the cloud README promises.

**Evidence** (verified 2026-09-14 16:50 ET on the live PC, adapter pid 35568, main `c61d3e8`)
- `aaca82b` added the LEASE PROTOCOL in `api/qqq_exec.py` (big comment block next to
  `LEASE_STALE_SEC`). Every status publish to Firestore `users/{uid}/meta/qqq_exec` is also the
  lease renewal (`_Publisher._do_set` stamps `doc["lease"] = {host_id, leased_at}`). Another host
  may claim the lease once the stamp is older than `LEASE_STALE_SEC` = 90 s (`_lease_claimable` /
  `_claim_lease`).
- `ae9842d` then throttled publishes in `_should_publish`: while the broker mirror is armed
  (PAPER/LIVE) at least every `publish_interval_armed_sec` = 20 s (fine), but while it is OFF,
  every `publish_interval_session_sec` = 60 s in the session and every
  `publish_interval_offhours_sec` = 600 s outside it, unless the fingerprint changes.
- Result: with the broker OFF, outside market hours the running host's lease stamp is older than
  90 s most of the time. Observed live: stamp age 89.8 s at 16:48:31 ET, last publish 16:47:02.
- Consequence 1: a second host (the planned Oracle VM, `deploy/cloud/`) can claim the lease while
  the PC is still running, and both shadow books run until the PC's next publish (up to 10 min),
  which is a compare-and-set that then stands the PC down.
- Consequence 2, worse for the migration: `deploy/cloud/README.md` section "Two machines, one
  shadow book", checklist step 7, promises "a relaunched copy is refused for as long as the VM
  holds the lease". Off-hours the VM's own stamp is stale too, so the PC runner's relaunch (every
  runner restart via `ensure_standalone`, and `tools/premarket_ensure.py` at 06:05 local) would
  claim the lease and take the book back overnight.
- In-session OFF (60 s) stays under 90 s, but with only ~25 s of margin.

**The task**
Make lease freshness independent of the status-publish throttle without giving back most of the
write savings. Two candidate designs; pick one and justify it in the protocol comment:
- **(a) Advertised cadence.** The holder advertises its renewal cadence in the lease (e.g.
  `lease.renew_every_sec` = the interval `_should_publish` is using), and claimers treat a lease as
  stale only after `max(LEASE_STALE_SEC, ~1.5 x that cadence)`. Zero extra writes; off-hours
  takeovers become slow (fine, nothing trades off-hours). Check every reader: `_check_lease`,
  `_lease_claimable`, `_check_lease_for_broker` (own-stale rule uses `LEASE_HOLD_SEC` 60 s),
  `_LeaseHolder.write_mode` / `within_hold` / `send_gate`, and the loop's suspended-gap re-claim.
- **(b) Lease-only renewal.** A small merge write of just the lease field (compare-and-set when
  outside the hold bound) whenever the throttled publish would leave the stamp older than ~45 s.

Either way, keep the fail-open (shadow book) / fail-closed (real orders) split and the armed 20 s
cadence, and update the README section's wording if the timing it describes changes.

**Done when**
- `tests/test_qqq_exec_lease.py` shows a running holder publishing at the off-hours cadence is
  never claimable by another host, and a genuinely dead holder is still claimable in bounded time.
- `tools/qqq_failover_sim.py` has a scenario "G: throttled holder's lease looks stale off-hours"
  that prints GAP PRESENT on main before the fix and "gap closed" after it. The existing A/B/C
  stay GAP PRESENT and D/E/F stay closed.
- `python tools/qqq_failover_sim.py` and the qqq_exec tests pass, and the Linux CI job shows no
  new failures. Baseline at hand-off: 35 pre-existing webull-SDK failures; if the CI fix lands
  first, compare against main as it stands after that.
- This item reads DONE and the memory note `qqq-cross-host-failover-state` records the fix.

**Constraints**
- Work in your own worktree (`python tools/wt.py new <name>`) and never commit in the shared
  checkout. Backend-only changes may push direct to main; no `index.html` VERSION bump needed.
- Never restart the live QQQ adapter (`python -m api.qqq_exec --serve`) during 09:25-16:05 ET,
  and only while it holds no open lot.
- Other sessions were changing `api/qqq_exec.py`, its tests and the failover sim on 2026-09-14
  (runner fallback honoring the lease, exits tied to their trade, adapter tests writing live broker
  state). Rebase onto the newest main before shipping.
- Noted 2026-09-14, not re-checked: a test that calls `tick()` without stubbing the broker adapter
  re-saves the LIVE `C:\EdgeLog\webull_orders\state.json`, so stub it in the new tests. And if a sim
  scenario flips to "gap closed" without a fix aimed at it, check the simulated orders actually
  flowed before believing it (`1ed627e` once made A and C pass vacuously).

---

## 4. A second signal engine ran on the cloud box for 12 hours: one duplicate NOISE entry row

**Status: DONE 2026-09-25.** Row 24 (the duplicate NOISE_304 ENTRY) was voided with item 1's repair;
row 23 is kept.

**Earlier status: OPEN.** Nothing needed from the owner to check it. Voiding the row, if you decide it
should be, follows item 1's rule: build and apply only after the owner says "apply the ledger
repair". Added 2026-09-21 by the session that fixed the GATE DOWN header chip.

**What happened, in plain words.** The job runner on the cloud box was switched off on 2026-09-20,
but its 5-minute healthcheck saw the stopped runner's log go quiet and started it again at 00:37
UTC on 2026-09-21. That runner ran its own copy of the signal engine, so from the cold move
(edgelog-cloud-signal.service, ~02:09 UTC) until it was stopped at ~14:33 UTC the box had two
writers of the live signal record - the case item 2 describes, from a different door. The runner
is now stopped, its healthcheck timer disabled, and `api/runner.py` refuses to start on
`EDGELOG_HOST_ROLE=cloud` (commit "Cloud box never runs the job runner"). Neither paper service
was touched.

**Evidence (read-only, 2026-09-21 ~10:45 ET)**
- `~/edgelog/cloud_signal/signals.csv`: the last two rows are the same event twice - NOISE_304
  ENTRY long, ref 09:40 ET @ 729.81, trade id `NOISE_304-20260921T134000Z-L`, emitted 09:45:09.41
  and 09:45:10.06 ET.
- `~/edgelog/logs/qqq_exec.log`: `WARN entry_duplicate: NOISE entry signal repeats the trade
  already open ... ignored`. One shadow ENTER in `qqq_exec/orders.csv` (09:45:12). No second
  order: the broker row for that entry was BLOCKED by the reconcile halt anyway.
- Earlier trade ids appearing twice in the file are ENTRY + EXIT pairs, not duplicates. Rows from
  02:09 to 13:45 UTC were not checked one by one for lost state records (the second failure mode
  item 2 names); `state.json` was not inspected.

**The task**
1. Confirm the duplicate row is the only damage: check `state.json`'s NOISE_304 / ENGUQ_335 /
   ORB_R6 records against `signals.csv` for 2026-09-21 00:37-14:33 UTC.
2. Decide whether the duplicate ENTRY row should be relabelled `VOID_*` in place (never deleted -
   the adapter reads by row-number cursor), and if so ask the owner, as item 1.
3. Item 2's fix does not cover this door (the runner's thread is the one it deliberately never
   refuses); the runner-side refusal does. Nothing else to build here.

**Done when** the check in step 1 is written up here, and the row is either voided (owner OK) or
recorded as left in place, with the reason.

---

## 5. NOISE bought in the book but never at Webull: re-send a blocked buy, never sell what Webull does not hold

**Status: DONE 2026-09-21** (after-close check 16:14 ET). The fix went live at 11:57 ET (main 60fa741,
one-time in-hours restart the owner approved). Outcome: NOISE closed in the book at the 15:59 flatten
(10 @ 741.58, +$117.60 - a BOOK-ONLY result, Webull never held this trade), and the guard stopped its
sell - broker row BLOCKED "nothing to close", no order sent. No other broker orders, re-sends, halts or
duplicate rejects after 11:57; 50 periodic reconciles all OK, the last at 16:05:39 ET (broker {} = sent
0). Books flat on every side: book legs {}, re-send queue empty, the adapter's sent and believed
positions 0 on every leg, open_legs {}, Webull stock-account positions {} and 0 open orders in all
five paper accounts. The published curve carries no NaN and ends at +$164.88.
Handed over 2026-09-21 ~11:10 ET by the system-check session ("Paper: NT8")
at the owner's request; taken by the session that shipped the 30-second reconcile grace (c7d07ae).
Fix built on branch `session/noise-blocked-open` (api/webull_orders.py, api/qqq_exec.py,
tests/test_qqq_exec_broker_resend.py). Code reaches the cloud box only at an after-close restart
(the no-restart-during-hours rule), unless the owner waives it.

**What happened, in plain words** (cloud box `~/edgelog/logs/qqq_exec.log` and
`~/edgelog/qqq_exec/broker_orders.csv`):
- 09:31:00 the open-time repair sold Friday's 20 stuck QQQ. ENGU-Q's sell filled; ORB's identical
  sell, sent in the same instant, was rejected as a duplicate (Webull compares the ORDER, not our id).
- 09:42:10 the repair's retry sold ORB's 10 (one per tick since 2f99aad). The reconcile on the very
  next tick read Webull's positions before that fill showed up (broker 10 vs sent 0) and halted new
  entries on every leg.
- 09:45:12 NOISE_304 entered in the book (long 10 @ 729.82, trade `NOISE_304-20260921T134000Z-L`).
  Its Webull buy was BLOCKED by that halt. The halt cleared seconds later, but nothing ever re-sent
  the buy, so since then the book holds NOISE and Webull holds nothing (checked ~11:15 ET: the
  Individual Cash paper account has no position and no open orders).
- Hazard for the rest of the day: when NOISE exits, the running code still sends SELL 10 QQQ,
  because a close skips every rail and nothing checks that the leg was ever bought at Webull. On a
  cash account Webull most likely refuses it, but its order preview does not check holdings (it
  returned a cost estimate with no error), so that cannot be confirmed without a real order.
- Do NOT buy the 10 QQQ by hand to "match" the book: the system never recorded that buy, so the next
  reconcile reads broker 10 vs sent 0 and freezes ENGU-Q and ORB buys for the rest of the day, and
  after NOISE's sell the books read sent -10 vs broker 0, which carries the freeze into tomorrow.

**Answers to the three asks.**
1. Re-send a blocked buy once the halt clears: built (below).
2. Don't let the orphan-close window halt other legs: the halt came from looking 5 s after a fill.
   The 30-second grace (c7d07ae, on main) waits before that look, and while a halt is on the check
   now repeats every 30 s instead of every 5 minutes, so a false freeze lasts seconds, not minutes.
3. The 09:31 duplicate reject was NOT "already closing": it was ENGU-Q's identical sell. Treating
   it as closing would have left ORB's 10 shares at Webull. The right handling is to send it again a
   tick later under a fresh id, which is now built for every order, not only repairs.

**What was built.**
- Never sell what was never bought: a close goes to Webull only for shares this system actually
  sent there for that leg; otherwise it is skipped, logged and pushed to the phone. A close larger
  than what was sent is trimmed to it.
- A buy blocked by the system's own reconcile halt is re-sent once the halt clears, but only while
  the book still holds that very trade, within 10 minutes of the first try and before the
  last-entry time; otherwise it is dropped with a phone alert. A kill-file halt, a lease block or a
  rails refusal is never re-sent.
- An order Webull rejects as a same-instant duplicate is re-sent a tick later under a fresh id (the
  id gains R1, R2, R3), one re-send per tick, at most 3, then a phone alert. This also covers an
  end-of-day flatten with two legs open and two legs buying on the same bar.
- While halted by its own reconcile, the system looks at Webull again every 30 s.

**Needs from the owner.** Today only: whether to restart the cloud book before the close to load
the guard (a one-time waiver of the no-restart rule); otherwise it goes live at the 16:12 ET restart.

**Done when** the fixes run on the box, today's NOISE close either sent nothing (guard) or was
refused by Webull, and the books read flat after the close (broker 0 = sent 0 for every leg).

---

## 6. ML filter for the Webull book, NOISE first (then ORB, then ENGU-Q)

**Status: CLOSED 2026-09-25.**

**Item 6 result (2026-09-25): CLOSED - no ML filter on any Webull leg.** The same pre-registered money test (the filter must make MORE than plain on BOTH the walk-forward stretch and the held-out year) was applied to all three legs, and none passes, so plain trading continues on NOISE, ORB and ENGU-Q.
- NOISE (run #408, a fresh gate_validate 2026-09-21): lost over the long history ($347,398 vs $350,650 plain); beat plain in the held-out year by only $3,389 on 6 skipped trades of 288 - too small to trust.
- ORB (run #314's own stored bake-off, validated 2026-09-04, after the 2026-08-10 causal-feature fix - no new run): Extra Trees @ 45% made $4,946 more over the long history but skipped 0 of 168 held-out trades, so the held-out year is a tie, not a win.
- ENGU-Q (run #335's own stored bake-off, validated 2026-09-08 - no new run): Random Forest @ 45% cut over half the trades and made $121,162 LESS over the long history ($370,356 vs $491,518) and $205 less in the held-out year.
- In all three the app's green "lockbox held" light measured a smaller drawdown, not more money - the drawdown-dial trap this rule exists to catch.
- Curiosity, not a result: most resizing hybrids beat plain in the held-out year on ORB and ENGU-Q (some with less drawdown), but picking one after seeing the numbers is shopping. The only legitimate next step is a resizing-only test pre-registered before looking, if the owner wants it.

**Earlier status: NOISE FAILED STEP 1 - nothing built (run #408, 2026-09-21 15:27 ET).** Result below; the owner
decides whether ORB #314 gets the same one-job test or the item closes. Step 1 was queued
2026-09-21 (owner: "go, run it as a twin beside NOISE") with
`tools/queue_noise304_gate_validate.py --queue`; the result lands as a run in PAST RUNS and is judged
against the pre-registered pass below before anything else is built. Asked 2026-09-21 (owner: "yes plan the ML
for webull, start with NOISE"), after learning the Webull book trades all three crowns with NO ML filter:
the owner's 2026-09-01 plan was the ML configs, but the filters were never refit when the crowns changed
(2026-09-05..08) and the cloud signal engine went live without them. Step 1 is a pass/fail test; nothing
is built for the cloud unless the filter passes it.

**STEP 1 RESULT - FAIL (run #408, job BZWazqipZT9tvUEGO9n1, pinned to run #304; points x $20).**
The engine chose a LOGISTIC filter at the 45% cut-off (selection rule: net $ within 80% of the best
pre-held-out MAR). Against the pre-registered money rule:
- 15-year walk-forward stretch (2010-08..2025-08; the filter refits every 25 trades on past trades
  only): filtered $347,398 vs plain $350,650 - $3,252 LESS money, with a slightly smaller drawdown
  ($15,775 vs $16,917) and a higher PF (1.41 vs 1.37). That is a drawdown dial, not an upgrade.
- Held-out year (2025-08..2026-08): filtered $65,994 vs plain $62,605 (+$3,389), same drawdown - but
  it skipped only 6 of 288 trades, so the gain is noise-sized.
- Resizing (hybrid) versions at the same 45% floor, judged at equal drawdown: every one made LESS
  money than plain NOISE in the held-out year (logistic $50,115, rf $48,063, et $55,725, tree
  $38,109, xgb $1,436 vs plain $62,605), even though four of them led in the 15-year stretch.
- The run report shows the engine's green "LOCKBOX HELD" chip: that grades money-per-drawdown in the
  held-out year only (2.69 vs 2.55). The rule fixed before the run needs more MONEY in both
  stretches, so NOISE fails. No other candidate is picked from the hindsight numbers - that would
  be shopping.
Consequence: plain NOISE keeps trading on Webull; no model file, no cloud scorer, no NOISE-ML leg.
Same verdict as the ML tab of run #304's own Auto-Validate (FAILED, 18-month held-out stretch) - see
the correction below. RULE FOR THE NEXT LEG: every Auto-Validate already stores a full ML bake-off,
so read the crown run's GATE / TILT / HYBRID tabs first; queue a separate Gate bake-off only when
the run has none.

**Where things stand (read-only research, 2026-09-21).**
- **CORRECTION 2026-09-22 (owner: "theres proably about 20 auto validates on past runs"):** the line below
  was WRONG. Run #304's own Auto-Validate (2026-08-30) already carries the same ML bake-off (5 models x
  cut-offs 45/50/55/60, the GATE / TILT / HYBRID tabs of its report). It chose logistic at 50% and
  FAILED its 18-month held-out stretch: filtered $72,006 vs plain $82,123, and $324,491 vs $331,132
  before it. The research behind this plan read only the docs, never the run itself, so step 1 (run
  #408) repeated a test that already existed. It reached the same answer.
- (superseded) No ML filter has ever been built or tested on NOISE's current crown, run #304 (`NOISE_1_1_NBHD.py`,
  NQ 5m RTH, 2010-06-07..2026-07-16: 4,824 trades, PF 1.357, net $398,775, about 300 trades a year).
  The PC's live filters for NinjaTrader sit on retired NOISE configs: #225 tree@0.55, #231 rf@0.55,
  #243 et@0.50 (`api/paper.py` PAPER_LEGS, served by `api/gate_live.py`).
- The evidence on NOISE is MIXED, which is why step 1 comes first:
  - formal cut-filter tests on #219/#225/#243 (logistic@55, et@50) lost to raw in the held-out year
    once the look-ahead was fixed (NOISE.md "ML gate - still closed");
  - the 2026-08-27 year-by-year re-measure found the et HYBRID on #243 added +$13.3k a year (t=3.0,
    13 of 15 years helped) - the only leg of the three with a signal that clears noise
    (memory ml-overlay-evidence-2026-08);
  - resizing alone (TILT) is dead on NOISE (0 of 18 cells), and KEEL on #304 was leverage, not skill.
- All 13 filter inputs are scale-free (moves in ATRs, ATR ratios, range position, trend correlation,
  prior-day distances in ATRs, touch count, clock) and none uses volume (`augur_engine/ml_gate.py`
  entry_features), so an NQ-trained filter can in principle read QQQ bars. That carry-over has only
  ever been ASSERTED (`tools/qqq_paper.py` docstring), never measured.
- The cloud box has no scoring service, and its scikit-learn is 1.9.1 against the PC's 1.6.1, so a
  pickled model is not safe to ship there (`gate_live.py` writes joblib pickles).
- QQQ 5-minute history on both machines starts 2026-06-08 (about 3.5 months); 1-minute starts 2026-08-11.

**The plan.**
1. **Test the filter on #304 (NQ, PC runner) - the go/no-go.** One GATE VALIDATE of
   `NOISE_1_1_NBHD.py` with #304's own settings, its window and master pinned to the crown run. The
   engine's standard search: five model types (logistic, rf, xgb, tree, et) x cut-offs 45/50/55/60,
   causal features, a held-out stretch at the end (the engine default is 12 months; use 36 if the
   RESEARCH.md item 9 lockbox proposal is adopted first), candidates chosen by net $ within 80% of the
   best MAR. PRE-REGISTERED PASS, judged on money like the ORB crown: the chosen filter makes MORE money
   than raw #304 on BOTH the walk-forward stretch and the held-out stretch - for a resizing (hybrid)
   filter, at equal drawdown (the HYBRID equal-drawdown tab), so leverage cannot fake a win. Earning
   less with a smaller drawdown is a "drawdown dial": reported, not adopted. FAIL = NOISE stops here.
   Cost: one runner job; nothing live changes.
2. **Measure the NQ-to-QQQ carry-over.** Score the chosen filter on every 5-minute RTH bar since
   2026-06-08 on BOTH tapes (about 5,000 bars), and on #304's own signals run on both tapes over that
   window. PRE-REGISTERED PASS: probabilities correlate at 0.9 or better and keep/skip agrees on 90% of
   bars or more. FAIL = the filter is not trusted on QQQ; stop and report.
3. **Ship the model as a plain data file.** Fit the chosen filter on all #304 NQ history on the PC and
   export it as a JSON model file in the repo (scaler, trees or coefficients, cut-off, training window,
   checksum), scored by a small numpy function - no pickle, so the scikit-learn version gap cannot bite.
   A test proves the file reproduces scikit-learn's probabilities on 1,000 rows, on both machines. Refit
   monthly on the PC (the engine's walk refits every 25 trades, about a month of NOISE); the box picks
   the new file up at an after-close restart.
4. **Add a filtered twin, "NOISE-ML", beside raw NOISE on Webull.** The cloud signal engine filters
   NOISE's OWN trade list (no second backtest - the pattern of `api/paper_gate.py` apply_gate), so
   NOISE-ML's trades are exactly raw NOISE's minus the ones the filter skips. Every NOISE signal logs its
   probability and keep/skip; kept signals trade 10 QQQ at Webull under the new leg, and raw NOISE keeps
   trading as the matched control. Places to change: `api/cloud_signal.py` (CROWN_LEGS + a derived-leg
   hook), `api/qqq_exec.py` (LEGS, ENGINE_LEG_MAP, shares), `index.html` Webull tab (a 4th QE_LEGS entry
   plus the two hard-coded leg lists in the chart), and a keep/skip list on the tab. When both legs take
   a trade Webull holds 20 QQQ; their identical same-bar orders collide as duplicates and the second goes
   a tick later (item 5's re-send). Deploy after the close only.
5. **Forward test, then decide.** NOISE fires about 1-2 times a week on QQQ, so judge after about 20
   signals (roughly 3 months), with a monthly readout. Then either keep NOISE-ML and repeat steps 1-4
   for ORB #314, and after it ENGU-Q #335 (last: its ETH-tuned crown already runs on an RTH-only QQQ
   tape), or retire it with the reason.

**Needs from the owner.**
- ~~"go" for step 1~~ - given 2026-09-21.
- ~~Twin beside raw NOISE, or replace it~~ - TWIN beside raw NOISE (owner 2026-09-21).
- If a resizing (hybrid) filter wins, whether NOISE-ML may trade a variable share count (for example
  5-15) instead of a fixed 10 - decide when the result is in.
- Not part of this item: the hourly-squeeze NOISE (#398) passed its fenced re-search but is not
  crowned. If it is crowned later, the filter is refit on it.

**Done when** NOISE has a keep-or-retire decision after its forward test, and the recipe is either
under way for ORB or closed with the reason.

---

## 7. One Webull account, three strategies: net the orders

**Status: DONE (2026-09-23, main d14e2a3, box deployed 16:14 ET while flat).** ORB, ENGU-Q and NOISE
all trade QQQ through ONE Webull margin paper account, and Webull holds one position per symbol. Each
leg's own side went out as-is, so legs that disagreed collided: after ENGU-Q bought 10 at 14:01,
NOISE's 14:10, 14:30, ~15:10, ~15:20 and 15:50 shorts came back HTTP 417
OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN ("close your existing long positions ... before placing
a short order") and became book-only. Earlier that day ENGU-Q's buy had silently covered NOISE's
accepted short; the account net stayed right only by luck.

**What changed.** The adapter plans the broker order(s) from the ACCOUNT net (sum of every leg's
accepted sends) instead of the leg's literal side: a short while the account is long becomes a SELL,
a short from flat stays a SHORT, and an order that would cross zero is split in two. Every per-leg
guard still runs first on the leg's own request (share caps, daily stop, session window, kill file,
one open position per leg, nothing-to-close). A replay of 2026-09-23 against a fake broker that
enforces Webull's refusals: every order accepted, flat after the 15:59 flatten.

**Watch at the open.** The first split order ever sent to the real broker, and whether Webull would
have accepted a single BUY that crosses from short to long (assumed NOT, so it is split; if Webull
allows it, the split is only one extra call).

**Needs from the owner.** Nothing.

---

## 8. Live positions + account equity, honest warnings, plain-English broker errors

**Status: DONE (2026-09-23: c87131f, 2877795, 20f2742; box deployed by 17:09 ET while flat).**
Owner's screenshot asks: the RATIO DRIFT and SLOW LATENCY badges, the empty gap under STATUS, the raw
Webull error text, and "show the positions live and potentially equity".
- POSITIONS - LIVE card under STATUS: each open leg's side, shares, entry, live price (Webull's live
  price feed, running on the serving host only; last closed bar when the feed is quiet), open P&L,
  time in trade; total open P&L; the margin account's equity with today's change (read at boot and
  every ~60 s in market hours; STALE only when those reads stop in market hours); a check that
  Webull's position equals the legs' sum.
- RATIO DRIFT: the QQQ:NQ ratio prices nothing in engine mode - now "ratio not used".
- SLOW LATENCY: engine-mode latency counted from the signal bar's START, so every 5m order read
  ~330 s. Now timed from the bar's CLOSE (new orders.csv column after_close_s; older rows derived the
  same way): ~30 s on 2026-09-23; the badge needs more than 60 s.
- NOT READY counts Webull parity, not NinjaTrader. Webull refusals show as one plain sentence with the
  raw text behind "details", never twice.

**Watch at the open.** The live price feed's load on the one-core box (messages per minute, CPU,
order timing) and the regular-hours trading-session label it reports. Kill switch if needed:
`live_stream_enabled: false` in the box's qqq_exec config, then an after-close restart.

**Needs from the owner.** Nothing.

---

## 9. KEEL v12 on top of run #382 on the NOISE leg

**Status: LIVE from the 2026-09-24 session (main 5326d02; asked 2026-09-23: "after that add the keel v12 on
top", "train it on the NQ backtest like the validation").** NOISE moved to run #382 for the session of 2026-09-24 (main 840b164):
the #304 core plus the validated squeeze size tilt (2x on a 30-minute squeeze). KEEL v12 goes on top.
- Training = the validation's own walk: run #382 on the NQ 5m RTH master, KEEL v12 over those NQ
  trades, rebuilt NIGHTLY on the box (its scikit-learn differs from the PC's, so no model file crosses
  machines).
- Each new NOISE trade on QQQ is scored as one more trade appended to that walk, from QQQ's own bars.
  Final size = #382 size x KEEL size. Any KEEL failure = size 1.0, never a blocked trade.
- Needs the NQ master on the box every night (pushed from the PC, which refreshes it daily).
- Caveat recorded 2026-09-10 (round 53): on #304, KEEL v12's back-tested gain was mostly bigger
  average size (about 1.2x), so this is a forward test, not a proven edge.

**Live facts.** Box and PC builds agree (same file, 4,855 trades, 194 fits, trust 0; one ledger reading
differs 0.1% across library versions). Owner 2026-09-24: "pick up from where the price action was prior
to us taking it live" - the state was rebuilt at 11:43 ET through 2026-09-23 (the last session before
go-live, 4,860 trades), and the nightly push now tops the NQ master up with the full session first, so
each night's build includes that day. Trades of the SAME day join the model that evening (the
validation's walk would already count earlier same-day trades - a one-day lag of a few trades out of
600/50 in its ledgers).

**Needs from the owner.** Nothing.

---

## 10. Fire orders at the bar close from the live price feed

**Status: SHADOW 2026-09-25** (4aaabc8; live on the box from the 16:07 ET restart, switch
`bar_close_from_stream` off). The engine still fires from Webull's REST bar. Beside it, it logs
whether the live feed's closed bar agrees and how many seconds it would save. After about a week
of those numbers, the owner decides whether to switch it on.

**Earlier status: OPEN.** Orders go out ~30 s after a bar closes: the signal engine waits for Webull's REST
bar to settle and then polls. The live feed (item 8) already builds its own 1m/5m bars from every
trade, so the engine can run the moment a bar closes and cut ~30 s to about a second. The feed runs
in the exec process and the engine in its own service, so the bars need a hand-off (the feed already
writes ohlc_stream/QQQ_*.csv every 10 s), plus a guard that REST stays the record of truth.

**Needs from the owner.** Nothing.

---

## 11. Re-price trades from Webull's own tape, not Yahoo

**Status: DONE 2026-09-25** (9805414; live on the box from the 16:07 ET restart). The re-price reads
the live feed's 1m bars first, then Webull's REST history, then Yahoo, and records which one it
used on each row.

**Earlier status: OPEN.** The nightly re-price (reprice.csv) reads yfinance 1-minute bars. Webull's own 1m
bars (REST history, or the live feed's ohlc_stream files) are the tape the orders actually traded on.

**Needs from the owner.** Nothing.

---

## 12. NOISE's volatility skip never fires live

**Status: PARTLY DONE 2026-09-25** (307a128; live from the 16:07 ET restart). The engine now hands
NOISE 70 sessions (the log reads "look-back COMPLETE"), so the skip can engage live. The
backtest still ranks against up to 252 sessions, not about 70, so some skip days will differ.
A full match needs at least 262 sessions of QQQ 5m bars on the box (go-live list item 3.8).

**Earlier status: OPEN.** NOISE's volatility skip looks back 60 sessions, and the live window hands the
strategy exactly 60, so the look-back is never complete and the skip never engages. Needs a longer
QQQ history window on the box (its 5m cache starts 2026-06-08; the rest from Alpaca's 1m SIP history,
free since 2016) and a check that the live trades then match a full-history re-run.

**Needs from the owner.** Nothing.

---

## 13. Share cap vs #382 x KEEL sizes

**Status: DONE (owner 2026-09-24: "keep it as honest to the backtest as possible. im fine with
raising").** Per-leg cap 60 (the most #382 x KEEL can ask: 2.0 x 3.0 x 10) and total 80, on both
machines, live from the next after-close restart. The $400 daily stop stays: over #382's last 12
months NOISE's worst day at uncapped KEEL sizes was -$177 (it never binds). Uncapped vs capped at
20 over that year: $1,361 vs $1,132 - the cap would have cost about a sixth of NOISE's money.
Earlier text, kept for the record: Caps since 2026-09-23: 20 shares per strategy, 40 in
total, $400 daily stop, on both machines. #382 alone wants 10 or 20 shares; with KEEL on top a NOISE
trade can want up to 60 (2x times up to 3x). Anything over 20 is cut to 20, and the tab shows how many
were wanted. Keep 20, or raise NOISE's own cap so the sizes the validation assumed can trade.

**Needs from the owner.** Nothing.

---

## 14. Taking the book live: the go-live punch list

**Status: OPEN.** Added 2026-09-25. The full list is in WEBULL_GO_LIVE.md: 12 things Claude must
fix before any real share, 10 owner decisions, 12 fixes before sizing up, and a staged plan.
Stage 1 is NOISE only at 1-3 shares with the owner watching.

**Done when:** every item in its section 1 is fixed, the owner has settled its section 2, and a
supervised 1-share live test leaves both the book and Webull flat.

---

## 15. ORB never enters before about 14:05 ET

**Status: OPEN.** Added 2026-09-25 (go-live audit, checked by hand).

**What is wrong.** ORB #314 skips half days by comparing each session's length to 70% of a
normal session. On the live engine, today's session is still being built, so until about 14:05 ET
it looks shorter than that and is dropped as a half day. By the time it counts as a full day, the
morning breakout is hours old and the engine skips it as late. The backtests never see this,
because every session in them is complete. On the box, ORB has fired once since 09-09 (a 15:45
entry on 09-18) and has 6 late skips.

**Fix.** Judge a half day from the market calendar (or leave the unfinished last session out of
the length test) on the live path only. Then replay 60 sessions and check the ORB entries match
the backtest one for one.

**Done when:** the replay matches and ORB can take a morning entry on paper.

---

## 16. Entries and exits go out one 5-minute bar after the backtest's fill

**Status: OPEN.** Added 2026-09-26 (owner question via MANAGER; NOISE round 61 priced it at
about 0.45-0.66 NQ points a trade).

**What is wrong.** The backtest decides at the close of bar D and fills at the OPEN of bar D+1.
The live engine only sees finished bars, so it learns of that fill when bar D+1 closes and sends
5-35 s later: every recent NOISE entry went out 5 minutes plus 5-35 s after its backtest fill
(09-22 to 09-25). The 09-22 exit fix only removed the exits' second bar. Item 10 (bar-close
firing) would only cut the 5-35 s.

**Fix.** Let the engine see the decision at bar D's close (for example, run the strategy with a
stand-in next bar and send any entry or exit it would fill at that bar's open), then prove on a
replay that every live order goes out within seconds of the backtest's fill.

---

## 17. Order-path rework

**Status: OPEN.** Added 2026-09-26. The go-live items 1.5-1.7 were built (worktree wb-orders,
about 3,000 lines in api/webull_orders.py) but four review rounds kept finding new edge cases, so
none of it shipped. Redo it smaller: unknown outcomes resolved by order id, fill status and
filled quantity applied to the books, a split order's second part only after the first fills,
then (LIVE only) a separate live state file, a flat-before-arming guard and a safe disarm.
