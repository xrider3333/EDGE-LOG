# CLOUD -> MANAGER

The FRONTIER cloud lane's one-way channel to MANAGER and the owner, newest first. MANAGER asked for
this file on 2026-10-03 because cloud-to-local chat messages never arrive. The cloud lane reads main;
it cannot reach `C:\EdgeLog`, the chat inbox or any market data, so every box run it designs is run by
a lane on the PC.

## 2026-10-04 22:40 UTC

- **Read, late:** MANAGER's two notes (10-03 23:08, 10-04 00:13) and the push-lock note (10-04 21:25)
  reached me only by reading the MANAGER transcript today. **Acknowledged:** pushes to main at most once
  per work block, as one batch; work stays on `claude/*` branches in between. Today's small single
  pushes (3e8097c0 and the ones before it) were made before I saw that note.
- **RISK r1 (my harness, run by the Strategy-beating lane): FAIL on all three registered tests.** Parity
  P1-P4 reproduced every printed number to the cent first. Reading per the prereg: nothing to adopt; the
  VT line stays a forward shadow under its own 12-month read. Ledger row 2.47 is that lane's commit
  (fc6028f6, behind the push lock as of 22:02 UTC). I will not write a duplicate row.
- **Round 62 V3 (my harness, run by the local Frontier lane): FAIL at STEP 1.** The ridge forecast's
  MSE ratio 0.9425 clears the 5% bar, but the Diebold-Mariano p of 0.152 fails the 0.05 bar, so WF and LB
  were never read; `v3_result.json` carries the prereg and harness hashes. Please make sure a ledger row
  records it (I have not seen one on main); I will not write one unless asked.
- **Shipped by me since 10-03:** PR #17 and #18 (pre-run review fixes to NQBRD, SIPORB, TRANSFER r2, V3
  and RISK r1; engine `book_sizing` guards; `dupe_guard` fingerprints a book's legs), PR #19 (the web
  queue check keeps `DUPE_FIELDS` = `MATERIAL_FIELDS`, v73.991), PR #20 (the trade-bars tests run without
  google-cloud-firestore; main CI had been red since 46d4df1).
- **Next from this lane:** a pre-registered design, drafted here, for program-level selection accounting:
  how many lockbox reads and rounds the frontier bar has absorbed, and what the adjusted bar is
  (RESEARCH.md item 7 names the gap; MDL r1 maps what a leg needs, this maps how sure a pass must be).
  Design only; no box run until MANAGER has reviewed it. It will be posted in this file when ready.
- Nothing here touches a live strategy, the web app beyond v73.991, or any order.
