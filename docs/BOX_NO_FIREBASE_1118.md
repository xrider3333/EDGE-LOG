# Box trades without Firebase (owner 11-18: "we shouldn't need firebase to trade")

Status: BUILT on branch session/boxlocallease, NOT shipped, NOT deployed. Deploy needs MANAGER's word, after a close, with the book flat.

## (a) Why the box touches Firebase today
1. Lease READ before every send (cached 30 s): "may this host send?" Fail-closed, so a Firestore outage or quota 429 blocks orders. This is the 11-13 cause.
2. Lease CLAIM at start (compare-and-set) and lease RENEW stamped on every publish. A send needs our own stamp to have landed under 30 s ago, so failed writes also block orders.
3. Publish of the book doc (users/{uid}/meta/qqq_exec): what the WEBULL PAPER page shows. Not needed to trade.
4. serve() refuses to start at all without a reachable Firestore ("the published doc IS the record").
5. Nothing else: config, the kill switch (KILL file), rails, KEEL state and signals are all LOCAL files on the box. cloud_signal.py makes no Firestore calls.

## What the Firestore lease protects today, and how local mode keeps it
- Two hosts sending at once (PC failover vs box): kept by serving_hosts, a static allow-list that never touches the network. The PC config already has serving_hosts=["edgelog"], so the PC refuses to run the book. In local mode the list is MANDATORY on the box too: missing or empty means no ticking and no sends.
- A second process on the same box (systemd plus a manual run): kept by the existing host slot (SERVING.lock, _enter_host_slot). Local mode also requires this process's own pid to hold the slot.
- Automatic PC takeover if the box dies: LOST by design. The owner says the PC never serves; that was already true via serving_hosts. If the box is down, nothing trades, which is the safe failure.
- A second box (a clone or rebuilt VM with the same hostname): NOT covered by a local lock. Mitigation: never run two VMs; box_deploy targets one host. Optional later: an advisory Firestore "claim" that only alerts, never blocks.

## (b) Change (api/qqq_exec.py, +54/-6)
- New config key "lease_mode": "local". Absent or "firestore" means today's behaviour, byte for byte.
- tick(): in local mode the send gate is _local_lease_ok(cfg) = this host is in serving_hosts AND this pid holds the host slot. No Firestore read, no stamp-age gate.
- qqq_exec_thread(): in local mode it never claims the Firestore lease. The publisher writes plain, best-effort sets, and a failed write never touches trading.
- serve() / main(): local mode skips the Firestore lease check, and --serve runs even when Firestore is unreachable (publish off, trading on).
- Tests: tests/test_qqq_exec_local_lease.py (3 new, covering fail-closed with no list, PC host, another pid and slot not held). All 1,562 qqq_exec tests pass.

## Rollout (on MANAGER's word)
1. wt.py ship boxlocallease; then box_deploy --dry-run and --yes after a close, book flat. The code is inert until config changes.
2. Box config.json: add "serving_hosts": ["edgelog"] and "lease_mode": "local" (a box config change: owner word, snapshot first).
3. Restart the unit and check the log line "LOCAL lease held by host 'edgelog'" plus reconcile ok.
4. Rollback: remove "lease_mode" and restart.

## Open
- Not covered by tests: an end-to-end tick() in local mode with a fake broker (the unit tests cover the gate only). Run a paper --once on the box before flipping the config.
- The page may read the lease host from the doc. With no lease stamps it should show "serving" from updated_at; Trading Log to check.
