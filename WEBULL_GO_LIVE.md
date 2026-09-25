# Webull QQQ book: go-live punch list

**What this is.** Everything that has to be fixed or decided before the Webull QQQ book trades
real shares. Written 2026-09-25 by the Paper: WB chat from a read-only audit: seven checkers each
took one area (orders, risk limits, backtest match, the cloud box, readiness evidence, broker
rules, the web tab), every finding was re-checked by a second agent (two for the serious ones),
then a critic looked for gaps. 69 findings, 3 thrown out, the rest merged below. Board item 14 in
WEBULL_PAPER_TODO.md points here.

**Checked again by hand on 2026-09-25:**
- ORB is blind before about 14:05 ET (item 3.6). The half-day test compares today's session, which is
  still being built, to a full day's length, so every morning session is dropped as a half day.
- The half-day flatten is set to the 13:00 bell itself (item 1.8).
- The cross-host send check blocks exits too, not only entries (item 1.2).
- The repo is public, and two tracked files set the phone-alert channel name (item 1.10).
- NOISE's volatility skip now engages live (today's fix), but it ranks against about 70 sessions,
  not the backtest's 252 (item 3.8).

**Thrown out:**
- The Webull token does NOT expire on a fixed date. Its expiry moves forward a day each day the box
  uses it, and on 2026-09-25 it read 2026-10-10.
- "A cash account cannot run the book" is already handled: stock orders moved to the margin account
  on 09-23.
- The "ORB on a different account" in the broker records is a leftover 0-share record from the old
  paper cash account (see item 1.6).

Nothing here should go live until every item in section 1 is done. A few of section 2's owner decisions also block day 1; those are marked **(day 1)**. Today's fixes are not repeated here.

The "ORB on a different account" question is answered. It is a leftover record from the old paper cash account, from before the 09-23 switch to margin, and it holds 0 shares. It is harmless now, but it is the reason for item 1.6 below.

## 1. Blockers before any real share

**1.1 A failed exit is silent**
- **What is wrong:** When an exit or the 15:59 flatten is refused or times out, nothing retries it and no phone alert goes out. The position check still reads "matched", and the end-of-day summary never asks Webull whether you are flat. This already stranded 20 shares over the 09-17 and 09-18 weekend.
- **What to do:**
  - Push an alert on every refused order.
  - Retry exits until 15:59:50.
  - After the flatten, read the real Webull position and page "Webull still holds N QQQ, sell by hand" if it is not zero.
  - Add a "Webull is flat" line to the end-of-day summary.
- **Who:** Claude
- **Evidence:** qqq_exec.py:1691-1693, 1734-1762, 5995-6002, 5018-5040; webull_orders.py:1248-1251; broker_orders.csv 09-17 16:00:04 and 09-18 16:00:03/05 (417 FIXGW_NOT_READY_MARKET)

**1.2 A Firestore hiccup blocks every exit**
- **What is wrong:** The cross-host permission check that gates sends also gates exits. If Firestore is down or out of quota for more than 30 seconds, every exit, breaker close, kill and 15:59 flatten is blocked without a sound, and nothing re-sends them later. Firestore returned a real 503 on 09-23.
- **What to do:** Let exits skip that check when this box holds the local serving slot. Otherwise queue blocked exits for re-send and send a high-priority push.
- **Who:** Claude
- **Evidence:** qqq_exec.py:1616-1628, 6298, 6825-6835, 6690+; publish_down event 09-23 12:30 ET

**1.3 The PC can take over mid-session**
- **What is wrong:** The PC is still a hot standby. If the box drops out for more than about 90 seconds, the PC can take over the book in paper mode, using a ledger last written 09-20 and its own drifted signal file. The real shares would then be left with no one managing them.
- **What to do:**
  - Make the book refuse to serve on any machine except the cloud box.
  - Stop the PC's relaunch and its signal-engine thread for the QQQ book.
  - Keep it that way until failover gaps A-C are closed, and prove it with the failover simulator.
- **Who:** Claude
- **Evidence:** C:\EdgeLog\qqq_exec\SERVING.lock.standby rewritten 09-25 12:05; PC signals.csv written 12:15 today; qqq_exec.py:6255; deploy/cloud/README.md:131-137

**1.4 No one is told if the box, the book or the signal engine dies**
- **What is wrong:**
  - The box health timer is disabled, and it only watches the stopped job runner anyway.
  - No watchdog outside the box covers the QQQ book.
  - A stalled signal engine and a position-check halt only write a log line.
  - Every push goes out at default priority, mixed in with routine fill pings.
- **What to do:**
  - Add an off-box dead-man switch (GitHub Actions, the same pattern as the NinjaTrader watchdog). It pages if the book's heartbeat is older than about 2-3 minutes during 09:25-16:10 ET.
  - Push on signal-engine stalls while a position is open, on position-check mismatches, and after repeated tick failures.
  - Put a hard timeout around order sends.
  - Send safety alerts at high priority and move fill pings to a quiet channel.
- **Who:** Claude
- **Evidence:** box `systemctl` (healthcheck timer disabled); deploy/cloud/healthcheck.sh:12,31; tools/nt_cloud_watchdog.py; qqq_exec.py:630, 2917-2948, 2489-2496, 6190-6191, 1630

**1.5 Orders with an unknown result are booked wrong**
- **What is wrong:**
  - If Webull's reply times out, the book assumes the order was never placed, even though it may have filled.
  - An acknowledged order counts as a full fill even if Webull later cancels, rejects or part-fills it.
  - 26 of 35 accepted paper orders never got a fill price.
- **What to do:**
  - Save a "pending" record before each send.
  - After any error, look the order up by its id before deciding what happened.
  - When a status comes back as rejected, cancelled or partial, correct the held count and push an alert.
  - Find out why most fill prices are missing.
- **Who:** Claude
- **Evidence:** webull_orders.py:845-846, 1234-1237, 1246-1251, 1285; qqq_exec.py:1552-1558; log line 09-21 "broker=10 shadow_sent=0"

**1.6 Leftover paper positions can open a real short at the switch**
- **What is wrong:** Paper and live share one order-state file, and the "is there anything to close" check ignores which account a lot is on. If you flip while a paper lot is open, that lot's close is sent to the live account as a brand-new short. NOISE holds 15 paper shares right now. The paper day's losses and "leg already open" flags also carry into live.
- **What to do:**
  - Give live its own state file.
  - Make the close check and the limits account-aware.
  - Refuse to arm while any lot is booked under another account.
  - Make the cutover procedure: flip after the close, while flat, and archive the old state first.
- **Who:** Claude (code and procedure)
- **Evidence:** webull_orders.py:201/206, 1022, 1164, 1204, 1029-1055; box webull_orders/state.json (NOISE 15, daily P&L -37.95, ORB on the old cash account id)

**1.7 Turning live off can strand real shares, and the kill switch is weak**
- **What is wrong:**
  - Deleting the arm file with a position open makes the book mark it closed without ever sending the sell, and the position check stops looking.
  - Editing the order config does nothing until a restart, even though the README says it takes effect on the next order.
  - The kill file exists only on the box and fires once. After hours it fails.
  - Kill and repair act only on what the book thinks it holds, not what Webull holds, and they cannot buy back a short.
- **What to do:**
  - Refuse to leave live while real shares are held.
  - Re-read the config every tick.
  - Build one kill path that reads Webull's actual position, retries within the session, covers shorts, and can be triggered from the web tab. It pushes a confirmation once Webull reads flat.
  - Fix the README.
- **Who:** Claude
- **Evidence:** webull_orders.py:739, 803-817, 1145-1152, 1412; qqq_exec.py:1003-1011, 5917-5923, 3779-3826 (hard-coded long side at 3824); deploy/cloud/README.md:476-477

**1.8 On half days the flatten fires at the 13:00 bell**
- **What is wrong:** On half days the flatten time is set to the closing bell itself, so the sells go out just after the close and are refused, the same failure as 09-17 and 09-18. The next half day is 2026-11-27.
- **What to do:** Move the half-day flatten to 2-5 minutes before the early close, move the last entry to 5-10 minutes before it, and add a test for 11-27.
- **Who:** Claude
- **Evidence:** qqq_exec.py:5898-5907, 362-364; market_calendar.py:169-173

**1.9 Nothing controls changes on the live box**
- **What is wrong:**
  - The box pulls the shared main branch at any time.
  - It was restarted mid-session on 09-21, 09-23 and 09-25, including by a script that restarts the book whenever it is flat.
  - Ubuntu's automatic updates restart both services overnight.
  - The live config files exist only on the box, and an unrecorded change to the flatten time already stranded shares once.
- **What to do:**
  - Pin the box to a release you approve.
  - Block restarts and config changes between 09:25 and 16:05.
  - Delete the restart script.
  - Stop automatic restarts of the book after updates.
  - Keep the live configs in git, or at least in a change log.
  - Schedule the pending kernel reboot for a weekend.
- **Who:** Claude builds it; the owner approves the release process.
- **Evidence:** box git reflog (12 pulls in 5 days); journalctl restarts; ~/edgelog/flat_restart_once.sh; /etc/apt/apt.conf.d/20auto-upgrades; /var/run/reboot-required

**1.10 The alert channel is public**
- **What is wrong:** The phone-alert channel name is committed to a public GitHub repo. Anyone can read your fills and P&L, send fake "all clear" pushes, or flood the channel so a real alarm gets buried.
- **What to do:** Create a new private channel with an access token, keep it only in the box and PC settings, remove it from tracked files and task arguments, and resubscribe the phone.
- **Who:** Owner (new channel, phone) and Claude (scrub files)
- **Evidence:** deploy/_run_qqq_exec.vbs; tools/_restart_runner.bat.example (commits b1e179e, 06d8dff); the "EdgeLog NT futures rollover" scheduled task

**1.11 The live order path has never sent a single order**
- **What is wrong:** Every broker row so far is paper or blocked, and Webull refused 12 of the 47 paper sends. The production order route, the live key's permission to trade, and the shape of the live replies have never been tested.
- **What to do:** Run a supervised 1-share live test during market hours with you watching: buy, check status, sell, check status, a duplicate-order refusal and an after-hours refusal. It passes only if both the book and Webull read flat at the end.
- **Who:** Owner (present) and Claude (runs it)
- **Evidence:** box broker_orders.csv (PAPER 47, BLOCKED 11, LIVE 0); webull_orders.py (client setup)

**1.12 There is no live runbook**
- **What is wrong:** The README says never to create the arm file until a live token policy has been chosen and written down.
- **What to do:** Write one page covering:
  - how to arm
  - how to stop: kill, confirm flat, then disarm, never the other way round
  - the morning check
  - the after-close flat check
  - "the box is gone: flatten in the Webull app, then rebuild"
- **Who:** Claude writes it; the owner signs off.
- **Evidence:** deploy/cloud/README.md ~440-489

## 2. Owner decisions and actions

**2.1 Which account (day 1)**
- **What is wrong:** Live would trade your personal Webull login. The position check compares every stock in that account, so any other holding halts all entries. Any QQQ you trade by hand gets netted against the book, and your manual day trades count toward the same day-trade limit.
- **What to do:** Open or set aside an account used only by the book. Claude then pins it by its last four digits and limits the position check to QQQ.
- **Who:** Owner, then Claude
- **Evidence:** webull_orders.py:198, 252-255, 1441

**2.2 Account size, day-trade rule and buying power (day 1)**
- **What is wrong:**
  - The live margin account was about $3k in July.
  - One 10-share order is about $7.4k, which is over its buying power.
  - NOISE makes about 9-10 round trips on busy days.
  - Under $25k, Webull's day-trade protection refuses the closing order of the 4th day trade in 5 business days, so the limit shows up as a stuck exit.
  - A cash account cannot short at all.
- **What to do:**
  - Owner: either fund a margin account comfortably above $25k (for example $30k or more, so a few bad days can't push it under), or accept tiny size and long-only. Also check the day-trade protection setting.
  - Claude: add a check before each entry that reads the remaining day trades and buying power, and blocks any entry that could not be closed the same day.
- **Who:** Owner, then Claude
- **Evidence:** memory edgelog-webull-integration (about $3k net value; the balance reports remaining day trades); box trades.csv 09-22/09-23; no day-trade logic anywhere in api/

**2.3 Short permission (day 1)**
- **What is wrong:** Only one short has ever been accepted, and the book has no plain-English messages for refusals such as "not shortable", "hard to borrow", "short-sale restriction" or "margin call".
- **What to do:** Owner confirms shorting is enabled on the live account. Claude runs a short order preview and adds readable messages and pushes for those refusals.
- **Who:** Owner, then Claude
- **Evidence:** box broker_orders.csv (1 short accepted; 2 new-short and 6 side-mismatch refusals); qqq_exec.py:1872-1878

**2.4 Webull 2FA token (day 1)**
- **What is wrong:** Two services rewrite one token file every few minutes, without taking turns. The token already went into "PENDING" (waiting for your approval) twice around 09-21. If that happens mid-session, every Webull call fails, exits included, and the only trace is a log line.
- **What to do:**
  - Owner: approve a separate token for the live order client and choose the token policy.
  - Claude: build the Webull connection once per process, lock the token file while writing, push on any PENDING or token error, and page at 09:00 ET if the token is not healthy.
- **Who:** Owner, then Claude
- **Evidence:** cloud_signal.py:296-305; qqq_exec.py:2597-2625; webull_orders.py:839-855; cloud_signal.log ERROR_INIT_TOKEN PENDING

**2.5 Starting size and loss limits (day 1)**
- **What is wrong:** The caps of 60 per leg and 80 in total, and the $400 daily stop, are paper "honest to the backtest" settings. $400 is about 13% of $3k, and nothing stops a run of bad days.
- **What to do:**
  - Set the stage-1 values shown in the staged plan below.
  - Add a weekly and a since-start loss stop that disarms the book and pages you.
  - Write down, before arming, when each size step happens and when the trial ends.
- **Who:** Owner decides; Claude builds the loss stops.
- **Evidence:** box webull_orders/config.json rails; WEBULL_PAPER_TODO.md:603-607

**2.6 KEEL stack for live**
- **What is wrong:** Live NOISE runs #382's 2x tilt with KEEL v12 on top, which is not the stack that held its validation. KEEL's learned part is switched off (trust 0), so only its fixed rules change size, up to 4.5x.
- **What to do:** Choose one:
  - #382 without KEEL
  - #304 plus KEEL, the stack that held
  - run one validate of the exact live stack before sizing up
- **Who:** Owner
- **Evidence:** NOISE.md:19, 43; box KEEL summary (trust 0.0)

**2.7 ENGU-Q**
- **What is wrong:** The book closes ENGU-Q at 15:59 every day, but #335's edge comes from multi-day holds. Live would trade a cut-short version that has never been tested. It also uses NQ-sized dollar floors on QQQ prices.
- **What to do:** Keep ENGU-Q paper-only, or re-validate a regular-hours, flat-at-close version with floors scaled to QQQ before it trades real shares.
- **Who:** Owner
- **Evidence:** qqq_exec.py:5995-6002; ENGUQ_1M_ETH_R2_1_0.py:278, 288, 309; box signals.csv (holds of 09-18 to 09-23 and 09-23 to 09-24)

**2.8 Firestore plan**
- **What is wrong:** The book shares its free-tier Firestore daily quota with the research app, and that quota has run out four times. Once it runs out, sends stay blocked until 03:00 ET the next day.
- **What to do:** Move to the paid Blaze plan with a budget alert, or give the book its own Firebase project.
- **Who:** Owner
- **Evidence:** memory edgelog-firestore-quota; box log (about 5k writes a day)

**2.9 Backup of the cloud server**
- **What is wrong:** The book's positions, today's P&L and order memory exist only on one virtual machine.
- **What to do:** Turn on a boot-volume backup policy in the Oracle console.
- **Who:** Owner
- **Evidence:** box `systemctl list-timers`; C:\EdgeLog\backup_repos.ps1

**2.10 Taxes**
- **What is wrong:** Daily QQQ round trips mean most small losses fall under the wash-sale rule, so the tab's P&L will not match the tax form (1099).
- **What to do:** Talk to a tax adviser about wash sales and the trader tax election (Section 475(f)) and its deadline before the first real trade. Avoid QQQ in other accounts, including an IRA, during the trial.
- **Who:** Owner
- **Evidence:** box trades.csv; webull_sync.py:20

## 3. Fix before scaling up or adding a leg

**3.1 The main number is not real money**
- **What is wrong:**
  - The tab's main figure is the book's P&L, and all of the book's paper profit came from trades Webull never held.
  - Paper and live rows will mix in one ledger with no mode or account column.
  - "Webull holds N" shows the book's own record, not what Webull actually reports.
  - The header still says "paper only".
  - The repriced P&L is labelled "broker-verified" but comes from Yahoo prices.
- **What to do:**
  - Build a ledger from Webull's actual fills and make it the main number in live.
  - Add mode and account columns.
  - Archive the paper ledgers at the switch and set the live start date then.
  - Show Webull's real position.
  - Drive the header from the actual mode and fix the stale wording.
- **Who:** Claude
- **Evidence:** box trades.csv (+$144, of which +$162.80 is book-only); qqq_exec.py:151, 841-866, 1288-1294, 4637-4693; index.html:33576, 33586, 33594, 33694, 35104

**3.2 "Ready for real shares?" checks the wrong things**
- **What is wrong:**
  - The check can never pass: 28 of 28 trades fail parity at a tolerance of a fraction of a cent.
  - It ignores book-only trades, position-check halts, skipped or phantom signals, and whether the account type is right.
  - The web row and the backend disagree on the parity rule.
- **What to do:** Rebuild it. For each leg that is on, require:
  - a minimum number of round trips Webull actually filled
  - zero book-only trades
  - zero unresolved halts
  - a daily confirmation that Webull was flat after the close
  - slippage within a written budget
  - account checks (type, equity, day trades left)
  - a nightly replay of the signals against the backtest

  Also restate parity per share and ignore paper fills that fall outside that minute's price range.
- **Who:** Claude
- **Evidence:** qqq_exec.py:4492, 4947-4990; index.html:33660-33694. The fill-realism part of this item is marked uncertain.

**3.3 Execution cost may eat NOISE's edge**
- **What is wrong:** This is the biggest open question on whether NOISE makes money.
  - Live orders go out a full bar after the backtest's fill, as market orders.
  - No stop or target rests at Webull.
  - The median gap is about $0.30 per share each way, against #304's edge of about $0.10 per share per trade.
- **What to do:**
  - Re-run #382 with fills at the next bar's open (live-style fills) and see whether it still pays.
  - Fire NOISE at the decision bar instead of a bar later.
  - Place protective stop orders at Webull, with the engine as backup.
  - Judge live on 100 or more trades of real fills.
- **Who:** Claude
- **Evidence:** NOISE_1_0.py:529/545; cloud_signal.py:413; box reprice.csv; NOISE.md:123. Marked uncertain.

**3.4 The daily stop is unreliable**
- **What is wrong:**
  - There are two daily stops working from two different P&L figures, and the tab shows the other one.
  - The breaker prices positions from old closed bars and stops working when the price feed dies.
  - The broker-side limit only blocks new entries.
  - The limit counts paper rows and requested share counts rather than filled ones.
- **What to do:**
  - Price the breaker from the live Webull stream, with a maximum age on the price.
  - Treat "position open with no fresh price" as a trip or an alert.
  - Count only this mode and account, using filled shares.
  - Show the stop that actually applies.
- **Who:** Claude
- **Evidence:** qqq_exec.py:2299, 2344-2391, 2980-3003, 3953-4001; webull_orders.py:975-984; index.html:34891-34906

**3.5 Before adding a second leg: orders that cross zero are untested**
- **What is wrong:** When two legs point opposite ways, one order gets split into two parts. The second part goes out before the first has filled, and a refused remainder is never retried. This has never happened at Webull.
- **What to do:** Wait for part one to fill (or queue the remainder for re-send), then force a crossing on paper first.
- **Who:** Claude
- **Evidence:** webull_orders.py:104-110, 1215-1251; 7 side-mismatch refusals on 09-23

**3.6 Before ORB: it cannot trade before about 14:05 ET**
- **What is wrong:**
  - The half-day filter treats today's unfinished session as a half day, so every morning breakout is thrown away as "late". That removes about 98% of #314's trades.
  - ORB has also never made one clean round trip.
- **What to do:** Stop the in-progress session counting as a half day. Replay 60 sessions and confirm the entries match the backtest one for one. Then require 10 clean paper round trips on the margin account.
- **Who:** Claude
- **Evidence:** ORB_3_6.py:189-196, 232; paper.py:180-183; cloud_signal.py:1216, 1340-1347; box state.json (6 late skips)

**3.7 ENGU-Q sends phantom entries**
- **What is wrong:** When the end of the data cuts off a limit order's 10-bar fill window, the strategy moves on to the next signal. Live then books a trade the backtest never takes. The real trade's exit never matches the book's lot, which leaves "ghost" open trades.
- **What to do:** Emit a limit entry only once it stays the same when the next bar closes. Add replay tests for 09-17 15:07 and 09-23 14:00, and void the two ghost records with a logged tool.
- **Who:** Claude
- **Evidence:** ENGUQ_1M_ETH_R2_1_0.py:297, 304; box signals.csv; qqq_exec.log entry_leg_busy 09-23 14:01

**3.8 NOISE's volatility skip uses the wrong look-back**
- **What is wrong:** Live ranks volatility against about 68 sessions while the backtest uses 252, so about half the skip days differ from the backtest's.
- **What to do:** Backfill at least 262 sessions of QQQ 5-minute bars (for example from Alpaca SIP), widen the window, and check the skip days against a full-history run.
- **Who:** Claude
- **Evidence:** NOISE_1_0.py:389; commit 307a128; box 5-minute cache holds 77 sessions

**3.9 The order record deletes itself and has no backup**
- **What is wrong:** The broker order record keeps only its last 100 rows, about a week of NOISE, and nothing copies the box's ledgers anywhere.
- **What to do:** Rotate to dated archives instead of trimming, and copy the book, order-state and signal folders to the PC every night.
- **Who:** Claude
- **Evidence:** qqq_exec.py:157-160, 781-803

**3.10 Plain market orders with no price limit**
- **What is wrong:** Every order is a plain market order, so an order sent into a halt, the open or a bad signal has no price protection.
- **What to do:** Send limit orders a few cents past the last price, and escalate if they don't fill.
- **Who:** Claude
- **Evidence:** qqq_exec.py:1630-1632; webull_orders.py:1224

**3.11 KEEL depends on the PC**
- **What is wrong:** KEEL only gets new data when the PC is awake, silently falls back to size 1.0 when its data is stale, and can rebuild mid-session on the box's only CPU core.
- **What to do:** Push when KEEL is more than one session old or has fallen back, and hold rebuilds until after 16:05.
- **Who:** Claude
- **Evidence:** cloud_signal.py:191, 888-921; keel_state.log (rebuild at 10:14 ET)

**3.12 The box and the PC run different library versions**
- **What is wrong:** The box and the PC run different Python and library versions, and the cloud install list is mostly unpinned.
- **What to do:** Freeze the box's working versions into a constraints file, and compare the box's signals against a PC re-run every night.
- **Who:** Claude
- **Evidence:** deploy/cloud/requirements-cloud.txt:20-45

## 4. Nice to have

- **Signal-engine log:** it belongs to root, so log rotation cannot touch it, and its lines have no timestamps. Fix the owner, add Eastern-time timestamps, and check that tomorrow's first rotation works. (Claude; logs/cloud_signal.log, /etc/logrotate.d/edgelog)
- **Trading log:** live trades reach it only through the PC's sync, with no leg tag and a 7-day re-pull window. Tag each trade with its leg from the order id and widen the window, or run the sync from the box. (Claude; webull_sync.py:446-472, 539-540)
- **Fees:** subtract Webull's reported sell-side fees from broker-side P&L. (Claude; webull_sync.py:20)
- **Unused setting:** remove the unused extended-hours option from the order call, or connect it. (Claude; webull_orders.py:1077)

## Staged go-live plan

**Stage 0: before arming**
1. Finish every section-1 item.
2. Owner completes 2.1-2.5.
3. Run the supervised 1-share live test from item 1.11.
4. Cutover, done after the close while the paper book is flat:
   1. Stop both services.
   2. Archive the paper order state and ledgers.
   3. Start on empty live files, pinned to the dedicated account.
   4. Confirm the target account with a live order preview.
   5. Owner creates the arm file.

**Stage 1: NOISE only, tiny size, owner present for 2-4 weeks**
- ORB and ENGU-Q stay off.
- 1-3 shares, with the tilt and KEEL forced to 1.0.
- Caps of 3 shares per leg and 3 in total.
- Daily loss $30-50, plus a weekly stop.
- Shorts only if item 2.3 is confirmed. If not, run long-only and note that long-only is not the validated strategy.

**What to watch on day 1**
- Every order appears in the Webull app within seconds with the right share count.
- The book and Webull positions agree after every exit.
- Note the fill price against the book price, per share, for every trade.
- The day-trade counter.
- A test push lands on the phone in the morning.
- No unplanned restarts.
- At 16:00, Webull reads flat, and you confirm it in the app yourself.

**Abort criteria.** Go back to paper on any one of these:
- a stranded position
- a book-only trade
- a refused exit
- slippage over budget across 20 trades
- the since-start loss stop is hit

**Back-out steps, in this order**
1. Drop the kill file.
2. Confirm Webull is flat in the app, and sell by hand if it is not.
3. Only then remove the arm file. Never remove it while shares are held.
4. Restart in paper on a fresh state file.

**Stage 2: NOISE at full base size**
- Needs 50 or more clean round trips that Webull actually filled.
- Slippage must stay inside budget.
- There must be zero stranded or book-only events.
- Items 3.1-3.4 must be done.
- Then move NOISE to 10 shares, with the KEEL choice from item 2.6.

**Stage 3: add ORB**
- Needs items 3.5 and 3.6 done.
- Needs 10 clean paper round trips on the margin account.
- Needs one crossing-zero order tested on paper.

**Stage 4: ENGU-Q**
- Only after a regular-hours, flat-at-close version is re-validated (item 2.7) and item 3.7 is fixed.
- Otherwise it stays on paper for good.