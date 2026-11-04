# Webull LIVE runbook (one page). Owner signs off. v1 2026-11-04.

Box = the Oracle server that runs the book. Arm file = `~/edgelog/webull_orders/ARM_LIVE` on the box. Kill file = `~/edgelog/qqq_exec/KILL`.
Live stage 1: NOISE only, base 1 share, size multiplier exact (2x tilt = 2 sh), caps 3 per leg / 3 total, daily stop $40, weekly $120, since-arm $300.

## 0. Before arming (once)
1. Owner: shorting ON for the live margin account; account last 4 given to Claude; live API token approved on the phone; phone subscribed to the private alert topic.
2. Claude: both config files set and snapshotted (qqq_exec config.json shares NOISE 1 / all other legs 0, max_shares_per_leg 3, daily_loss_limit_usd 40; webull_orders config.json rails live_legs ["NOISE"], max_shares_per_leg 3, max_total_position_shares 3, daily_loss_limit_usd 40, account.stock_last4).
3. Pre-open check green for LIVE: mode LIVE, arm absent, live token NORMAL and not expiring today, Webull real position 0, no paper lots in state.LIVE.json.
4. The 1-share supervised test (section 5) passed.

## 1. Arm (evening, book flat, after 16:05 ET)
1. `tools/box_deploy.py --dry-run` then deploy the approved commit. Confirm `git log -1` on the box = that commit.
2. Stop both services. Archive paper state: `webull_orders/state.json` -> `state.paper.<date>.json`.
3. Start services on empty `state.LIVE.json`. Live order PREVIEW (no send) must name the pinned account.
4. Owner creates the arm file with one line: `<last4> <YYYY-MM-DD>`. The book refuses an arm file without today's date.
5. Test push to the phone lands.

## 2. Morning (owner present every live day in stage 1)
- 08:30 and 09:15 ET pre-open pushes say LIVE OK. If any line says AFFECTED: do not trade - remove the arm file BEFORE 09:30 (nothing held yet), ask PAPER-WB.
- Webull app: account flat, buying power shown, day-trade counter normal.

## 3. During the day
- Each fill push names the account `Webull LIVE <last4>`. Check the fill in the app within a minute. Share count must equal the push.
- Any of these = STOP (section 4): a stranded position (app shows shares, book says flat, or the reverse), a book-only trade, a refused exit, a token PENDING push, box dead-man push.

## 4. Stop. ORDER MATTERS: kill, confirm flat, then disarm. Never remove the arm file while shares are held.
1. Drop the kill file (box: `touch ~/edgelog/qqq_exec/KILL`). The book sells longs / buys back shorts at market and pushes when Webull reads flat.
2. Open the Webull app. If not flat within 2 minutes, close the position BY HAND in the app.
3. Only when the app shows 0 QQQ: remove the arm file. Remove the kill file.
4. Tell MANAGER. Paper restarts on a fresh paper state the next evening.

## 5. The 1-share supervised test (one market hour, owner watching)
Buy 1, confirm status, sell 1, confirm status; one short 1 + cover; one deliberate duplicate (expect refusal); one after-hours send (expect refusal); one service restart while holding 1 share (position survives, no double send). PASS only if book and Webull agree after every step and every push named the account.

## 6. After the close
- 16:10 push `Webull LIVE <last4>: flat` must arrive. If it says mismatch or unreadable: open the app, sell by hand if not flat, then tell PAPER-WB.
- Owner confirms flat in the app once, by eye.

## 7. The box is gone (no pushes, dead-man fired, ssh dead)
1. Webull app: flatten by hand. The app is the truth; the book's belief is lost.
2. Do NOT restart the book from the PC. The PC must never serve live.
3. PAPER-WB rebuilds the box from the last deploy + `C:\EdgeLog\box_backup` ledgers, starts in PAPER, and re-arms only after a fresh section-1 pass.

## 8. Size steps
Stage 2 (base 10) only after 50 Webull-filled round trips, 0 stranded / book-only / refused exits, slippage inside 0.25 $/sh. Stage 3 adds ORB, stage 4 ENGU-Q only on a passed re-validation.
