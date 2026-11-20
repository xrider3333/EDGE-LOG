# Webull LIVE runbook (QQQ book) — one page for the owner

## 1. What "armed" means
- Real orders need TWO things on the box:
  1. `"mode": "LIVE"` in the box's `/home/ubuntu/edgelog/webull_orders/config.json` (env `EDGELOG_WEBULL_ORDERS_CONFIG`), with the legs named in `rails.live_legs` (empty = nothing trades live).
  2. An empty file named **`ARM_LIVE`** in `/home/ubuntu/edgelog/webull_orders/` on the box (path can be changed with env `EDGELOG_WEBULL_ARM_LIVE`). You create it by hand. Claude never does.
- Missing either one = no live orders (the book keeps trading on paper / shadow only).
- LIVE keeps its own books: `state.LIVE.json`, next to the paper `state.json`. Paper positions never carry over.

## 2. Before you arm (all must be true)
- A **separate Webull margin account** with **$3k–8k** in it (not your main account). Live keys saved at the live keys path.
- **Account pin — YOU type this, nobody else.** In the box's `/home/ubuntu/edgelog/webull_orders/config.json`, set `"account": {"stock_last4": "NNNN"}` with the LAST 4 digits of the live account number (never the full number). Without it every LIVE send is refused ("live account not pinned"). No Claude lane enters, reads back or prints this value.
- Wipe `qqq_exec/books_toggle_applied.json` (paper toggles must not carry into LIVE).
- **Paper book flat.** If paper still holds shares, LIVE refuses and stays OFF (you get no live orders).
- Every item in the go-live readiness table (`docs/WEBULL_GOLIVE_READINESS_1118.md`, must-fix rows) and `docs/EDGELOG_GOLIVE.md` ticked.
- **MANAGER and you both say GO** in chat.
- Arm before 09:30 ET, on a normal day (no FOMC, no half day).

## 3. First live day — what to watch
- Phone title on every push names the account: **"Webull LIVE"** plus the account's last 4. If you see "paper", it is not armed.
- First fill: "QQQ book: ... bought" note. Check in the Webull app the share count matches (1–15 shares).
- Numbers to watch: **shares held** (Webull vs the board — must match), **today's P&L** vs the daily loss limit, **fill price vs signal price** (slippage, a few cents).
- After 16:00 ET: Webull must show **0 QQQ** (unless a trade is a planned overnight hold). The "day done" note sums the day.
- Any **CHECK NOW** note: open Webull, then ask Claude.

## 4. Pull the plug
- **Delete the `ARM_LIVE` file.** That is the off switch.
- If LIVE is flat: next tick = OFF, nothing more is sent.
- If LIVE still holds shares: **CLOSE-ONLY** — no new entries, but exits still go to Webull, so held shares get sold normally (`api/webull_orders.py` `effective_mode`, ~line 1269). Once flat it turns fully OFF.
- Emergency (sell now): create the `KILL` file — every lot is closed and new entries are blocked. Or sell in the Webull app yourself, then tell Claude.

## 5. Costs (sells only)
- **SEC fee** ~ $27.80 per $1M sold → about **$0.01** on a $7,500 sale.
- **FINRA TAF** ~ $0.000166 per share sold (capped) → **under $0.01** at 1–15 shares.
- Both are tiny at our size. Slippage matters more.

## 6. Every phone note the QQQ book can send (37)
Titles start "QQQ book: ...". **CHECK NOW** = look at Webull right away.

| Key | Title / what it says | What it means | What you do |
|---|---|---|---|
| fill:<leg> | "<leg> bought / sold" | An order filled at Webull | Nothing |
| fill_digest | Several fills in one note | Many fills at once | Nothing |
| held:<leg> | "held overnight" | A trade is kept overnight on purpose | Nothing |
| held_missed:<leg> | CHECK NOW | Planned overnight hold is not at Webull | Open Webull, ask Claude |
| entry:<leg> | "entry missed" | Buy did not reach Webull; book still counts it | Nothing; ask Claude if again tomorrow |
| exit:<leg> | CHECK NOW "did not go through" | A sell failed; Webull may still hold shares | Check Webull; sell by hand if needed |
| exit:repair | "repair gave up" | Next-open fix of leftover shares failed | Check Webull, ask Claude |
| exit:repair_hold | CHECK NOW | Repair on hold: Webull does not match | Check Webull, ask Claude |
| eod_flat | CHECK NOW "still holds shares after the close" / "could not be read" | Webull not flat after the close | Check Webull, sell leftovers |
| after_hours:start:<leg> | "EOD exit missed: selling after hours" | Close missed; selling after hours | Nothing |
| after_hours:fill:<leg> | "sold after hours" | After-hours sell filled | Nothing |
| after_hours:gave_up:<leg> | CHECK NOW "still holds shares overnight" | After-hours sell failed | Sell at the open or ask Claude |
| after_hours:armed:<leg> | "will sell at the 09:30 open" | Leftover queued for the open | Nothing |
| after_hours:blocked | CHECK NOW "may stay overnight" | After-hours sell on hold | Check Webull |
| books:<leg> | "book counts more shares than Webull" | Books and Webull disagree | Ask Claude |
| part_fill:<leg> | "needs a fix" | Part fill changed the books | Ask Claude |
| resend_landed:<leg> | "re-send was dropped" | A retry landed late | Ask Claude |
| unclear:<leg> / unclear_hand:<leg> | Unclear order answer | Webull answer unclear (or hand order seen) | Check Webull, ask Claude |
| hold:<cause> | "orders on hold" (high) | New orders stopped (books mismatch etc.) | Check Webull, ask Claude |
| late:<leg>:<action> | Late order | Order sent late | Nothing unless repeated |
| resting_place | "stop could not be placed" | ORB exits on bar close instead | Ask Claude |
| resting_escape | "stop ended without answer" | Stop order lost; no new stop | Ask Claude |
| fill_ledger | "fill could not be written" | Record-keeping only | Ask Claude |
| boot_unknown | Unknown orders at start-up | Webull had orders the book did not know | Check Webull open orders |
| boot:held_lost | CHECK NOW | After a restart the book lost held shares | Check Webull, ask Claude |
| daily_stop | "loss past the daily limit" | Day's loss limit hit; no more entries | Nothing; review tonight |
| loss_stop | Loss stop tripped | Weekly / since-arm loss limit hit | Consider pulling the plug |
| dip_rail | "DIP stop hit" | DIP's own daily limit | Nothing |
| kill | "Kill file present" | KILL file seen; all closed, entries blocked | Confirm Webull is flat |
| kill_flat | Kill done, flat | Kill orders sent | Confirm in Webull |
| day_summary | "day done" | End-of-day summary | Read it |
| tick_crash | CHECK NOW "checks crashed" | The executor keeps crashing | Ask Claude now |
| database | CHECK NOW "cloud database unreachable" | Cloud DB down | Ask Claude |
| lease_alert | Lease problem | Box/PC ownership unclear | Ask Claude |
| stood_down | "Stood down on <host>" | This machine stopped trading (another took over) | Ask Claude |
| refuse_local | "qqq_exec REFUSED" | Started on the wrong machine | Ask Claude |
| repricing (helper) | Re-price note | Limit re-priced | Nothing |

Source: every `_say(...)` call in `api/qqq_exec.py` (`api/webull_orders.py` sends no phone notes itself; it only logs).

## PICK6 restart hook: one-time box install (BUILT 11-20, not deployed)
Units in `deploy/cloud/`: `edgelog-eodrev.service` (now Restart=on-failure, RestartSec=20, at most 5 starts in 600 s,
OnFailure= alert), new `edgelog-eodrev-resume.service` (at boot: `run --resume-only`) and new
`edgelog-eodrev-alert.service` (one HIGH phone line: "PICK6 unit failed at HH:MM, basket N legs open").
What the resume unit does: nothing unless today's saved basket has open legs and it is 15:27-16:00 ET; then it resumes
so the 15:59:00 / 15:59:35 MARKET exits go out for the filled qty. It never makes a fresh entry. After 16:00 ET with
legs still open it sends one HIGH line and no order.

On the box, after the code is pulled, at a flat moment (not 15:20-16:10 ET):
```
cd ~/edgelog/repo   # the repo dir install.sh used
for u in edgelog-eodrev.service edgelog-eodrev-resume.service edgelog-eodrev-alert.service; do
  sed -e "s#__EDGELOG_USER__#$USER#g" -e "s#__EDGELOG_REPO__#$PWD#g"       -e "s#__EDGELOG_VENV__#$HOME/edgelog/venv#g" -e "s#__EDGELOG_HOME__#$HOME/edgelog#g"       deploy/cloud/$u | sudo tee /etc/systemd/system/$u >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable edgelog-eodrev-resume.service   # runs at boot only; do not start it by hand
systemctl cat edgelog-eodrev.service | grep -E "Restart|OnFailure|StartLimit"
```
Check the venv / home paths against the existing `/etc/systemd/system/edgelog-eodrev.service` first and use the same.
The timer (`edgelog-eodrev.timer`) is unchanged. Undo: `sudo systemctl disable edgelog-eodrev-resume.service` and
re-copy the old service file.
