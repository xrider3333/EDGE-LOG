# EDGE-LOG cloud runner — owner runbook

Run the EDGE-LOG job runner (`api.runner`, the process that drains the queue of
Auto-Validate/backtest jobs, keeps the ETF book master data fresh, and — once the QQQ
shadow adapter is switched into CLOUD mode — trades the paper book) on a **free**
always-on Linux VM instead of your Windows PC. No NinjaTrader, no Windows PC in the
loop, for that piece of the stack. This is a runbook for **you** — every step from
"I have nothing" to "the runner is live" is here. Every technical term is explained the
first time it's used.

**Cost: $0.** Oracle Cloud's "Always Free" tier includes an Ampere A1 (ARM)
virtual machine, up to 4 OCPU / 24 GB RAM, forever — not a trial. This guide uses 2
OCPU / 12 GB, which is plenty; you can resize later without losing anything.

---

## What runs where

| | Cloud VM (this guide) | Your PC |
|---|---|---|
| Job queue runner (Auto-Validate, backtests, master-data refresh) | **Yes** — 24/7 | No longer needed for this |
| QQQ shadow adapter (paper only, no live money) | Yes, once switched to CLOUD mode (a separate follow-up — this bundle just gets the box ready) | Currently runs here |
| NinjaTrader + the local NT bridge (live futures execution) | **No** — NinjaTrader is Windows-only and isn't part of this bundle | Yes, stays here until the owner decides to decommission it |
| Streamlit app (`optimizer.py`) | No — it's a desktop UI, not meant to run headless | Yes, when you want it |
| EDGELOG website (`index.html`) | Unaffected — it's a static site on GitHub Pages either way | Unaffected |

So after this bundle is running: the cloud box drains the job queue and keeps data
fresh even when your PC is off. Your PC keeps doing exactly what it does today for
NinjaTrader/live execution — nothing about that changes until you decide to move it.

---

## (a) Create the free Oracle Cloud VM

1. Go to <https://signup.oraclecloud.com/> and create an account (needs a credit card
   for identity verification only — Always Free resources are never billed; Oracle
   will not silently upgrade you without you explicitly buying paid resources).
2. Pick a **home region** close to you and remember it — Always Free resources are
   pinned to whichever region you pick at signup.
3. In the console: **Compute → Instances → Create Instance**.
4. **Image and shape:**
   - Image: **Canonical Ubuntu 24.04** (the "Minimal" or standard image both work).
   - Shape: click "Change shape" → **Ampere** → **VM.Standard.A1.Flex**. Set
     **2 OCPU / 12 GB memory** (comfortably inside the 4 OCPU / 24 GB Always Free
     cap, leaves headroom to resize up later without recreating the instance).
5. **Networking:** use the default VCN/subnet Oracle offers to create. Leave the
   default security list — it only opens **port 22 (SSH)** inbound, nothing else.
   Do not open any other inbound port; this box has no reason to accept inbound
   traffic besides your own SSH session.
6. **Add SSH keys:** let Oracle generate a key pair and download the private key (or
   paste your own public key if you already have one). You'll use this to log in —
   there is no password login.
7. Click **Create**.

**"Out of host capacity" retry trick.** A1 (ARM) Always Free capacity is popular and
busy regions sometimes show "Out of capacity" when you click Create. This is not a
quota problem — it means try again. Either: (1) just retry the Create button every
few minutes/hours, or (2) switch **Availability Domain** in the same region if your
region has more than one, or (3) try a different Always-Free-eligible region if you
truly get stuck for days. This is a known, common, temporary Oracle Free-tier
condition — it is not something wrong with your account.

Once created, note the instance's **public IP address** — you'll SSH to that.

---

## (b) SSH in

From your PC (PowerShell, or any terminal with `ssh`):

```
ssh -i C:\path\to\your-downloaded-key.key ubuntu@<the-public-ip>
```

(Ubuntu cloud images use the `ubuntu` user by default.) You should land at a normal
Linux shell prompt.

---

## (c) Install everything with one command

Once you can SSH in, run **one** of these (both do the same thing):

```bash
curl -fsSL https://raw.githubusercontent.com/xrider3333/EDGE-LOG/main/deploy/cloud/install.sh | bash
```

— or, if you'd rather see the code before running it —

```bash
git clone https://github.com/xrider3333/EDGE-LOG.git ~/edgelog/EDGE-LOG
bash ~/edgelog/EDGE-LOG/deploy/cloud/install.sh
```

This installs Python, clones the repo to `~/edgelog/EDGE-LOG`, builds a Python virtual
environment (an isolated Python install so this doesn't touch/conflict with the
system's own Python) with every package the runner needs, creates the runner's data
folders, writes a starter `~/edgelog/edgelog.env` settings file, and installs (but does
**not yet start**) the background services. It's safe to re-run any time — for example
after a `git pull`, to pick up newly added dependencies — it won't overwrite an
`edgelog.env` you've already edited.

**Requires `sudo`.** The `ubuntu` user on an Oracle image has passwordless sudo by
default, so this should just work without a password prompt.

When it finishes it prints exactly what's still needed — the next two steps below.

---

## (d) Copy your secrets from the PC

Three files never live in the git repo (they're gitignored / kept off GitHub on
purpose) and have to be copied by hand, once, from your PC to the VM. From a
**PowerShell window on your PC** (not the VM):

```powershell
scp -i C:\path\to\your-downloaded-key.key `
    "C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json" `
    ubuntu@<the-public-ip>:~/edgelog/EDGE-LOG/serviceAccount.json

scp -i C:\path\to\your-downloaded-key.key `
    "C:\EdgeLog\webull_keys.json" `
    ubuntu@<the-public-ip>:~/edgelog/webull_keys.json

scp -i C:\path\to\your-downloaded-key.key `
    "C:\EdgeLog\webull_token\token.txt" `
    ubuntu@<the-public-ip>:~/edgelog/webull_token/token.txt
```

What each one is:
- **`serviceAccount.json`** — the Firebase admin key. Lets the cloud runner read/write
  the same job queue and run history your web app already uses. Treat it like a
  password; it isn't in git.
- **`webull_keys.json`** — your Webull OpenAPI App Key/Secret, used by the QQQ shadow
  adapter and the daily Webull trade-history pull.
- **`webull_token\token.txt`** — the current Webull login token, so the box doesn't
  need you to re-authenticate Webull by hand.

Then finish `~/edgelog/edgelog.env` on the VM (`nano ~/edgelog/edgelog.env`): fill in
`NTFY_TOPIC` (the push-notification topic — reuse the one already set on your PC in
`tools/_restart_runner.bat.example`, or pick a fresh name at <https://ntfy.sh>).

---

## (e) Start it and confirm it's running

```bash
sudo systemctl start edgelog-runner.service
bash ~/edgelog/EDGE-LOG/deploy/cloud/check.sh
```

`check.sh` prints the service status, the last 20 log lines, disk/memory, and whether
every secret + the env file are actually in place. Look for `Active: active (running)`
and recent-looking log lines. The runner logs a startup banner naming the Firestore
collection and the allowlisted account — that's your confirmation it's talking to the
same queue as the website.

---

## (f) Day-to-day operations

| Task | Command (run on the VM) |
|---|---|
| **See live logs** | `tail -f ~/edgelog/logs/runner.log` (Ctrl+C to stop watching) |
| **Check status + secrets** | `bash ~/edgelog/EDGE-LOG/deploy/cloud/check.sh` |
| **Restart** (e.g. after editing edgelog.env) | `sudo systemctl restart edgelog-runner.service` |
| **Stop** | `sudo systemctl stop edgelog-runner.service` |
| **Update to the latest code** | `cd ~/edgelog/EDGE-LOG && git pull && bash deploy/cloud/install.sh && sudo systemctl restart edgelog-runner.service` |
| **Full status incl. the healthcheck timer** | `systemctl status edgelog-runner.service edgelog-healthcheck.timer` |

The service is set to **restart automatically** if it ever crashes (`Restart=always`,
15-second backoff), and a separate **healthcheck runs every 5 minutes**: if
`runner.log` hasn't been touched in over 10 minutes (a sign the process is hung, not
just quiet), it force-restarts the service and pushes an alert to your phone via
`ntfy.sh`. Both start automatically on every reboot — you never need to log back in
after a VM reboot for the runner to come back.

### The Always-Free idle-reclaim rule

Oracle can reclaim (delete) an Always Free VM that it judges idle for **7 consecutive
days** — the published thresholds are roughly: CPU utilization under 20%, network
under 20%, and memory under 20% (on A1 shapes), all at once, for a full week. A runner
that's actively polling Firestore every 30 seconds and periodically running validates
should stay well above that on its own. If you ever plan to leave it truly idle for an
extended stretch (no queued jobs, market closed for an extended period), it's worth
glancing at the instance's utilization graph in the Oracle console occasionally — this
bundle does not attempt to work around the idle-reclaim rule, it just documents it so
a VM disappearing isn't a mystery.

---

## Portability blockers — inventory (not fixed in this change)

The runner and its side-processes were written for the Windows PC and hardcode
`C:\EdgeLog\...` in a number of places. None of this blocks the **job-queue runner**
itself (`api/runner.py`'s core loop only needs `augur_engine`, which is already fully
portable — see below), but several **side duties** that run alongside it
(NinjaTrader-bridge readers, the QQQ shadow adapter's 10-second bar feed) reference
Windows paths that simply won't exist on the cloud box. They'll fail closed (log
"not present" / skip) rather than crash the runner, but they won't do anything useful
in the cloud until either an env override is added (some already have one) or the code
is changed. This is an **inventory only** — nothing below was fixed in this change.

| # | File : line | Hardcoded path | Env override already exists? | What it's for |
|---|---|---|---|---|
| 1 | `api/data_health.py:31` | `C:\EdgeLog\ohlc` | **Yes** — `EDGELOG_NT_OHLC` | NT OHLC feed health check |
| 2 | `api/gate_audit.py:50` | `C:\EdgeLog\gate_decisions.csv` | No | NinjaScript gate-decision log (NT-only) |
| 3 | `api/gate_audit.py:51` | `C:\EdgeLog\gate_live.log` | No | Gate service log (NT-only) |
| 4 | `api/gate_audit.py:52` | `C:\EdgeLog\fills.csv` | No | Broker fills (NT-only) |
| 5 | `api/gate_live.py:64` | `C:\EdgeLog\gate_models` | No | ML gate model artifacts (NT-only) |
| 6 | `api/gate_live.py:66` | `C:\EdgeLog\gate_live.log` | No | Gate service log (NT-only) |
| 7 | `api/gate_live.py:67` | `C:\EdgeLog\bridge.json` | No | NT bridge config/rails (NT-only) |
| 8 | `api/nt_backup.py:41` | `C:\EdgeLog\_ntbackup` | No | NinjaTrader workspace backup (NT-only, PC job) |
| 9 | `api/nt_drawdown_alert.py:38` | `C:\EdgeLog\dd_alert_state.json` | **Yes** — `EDGELOG_DD_STATE` | Intraday drawdown alert state (NT-only) |
| 10 | `api/nt_exec_review.py:65` | `C:\EdgeLog\seen_executions.json` | **Yes** — `EDGELOG_EXEC_REVIEW_STATE` | Fill-review dedupe state (NT-only) |
| 11 | `api/nt_sync.py:125` | `C:\EdgeLog\fills.csv` | No (has `--nt-fills` / `EDGELOG_NT_FILLS` at the runner CLI level — see below) | NT fill import default |
| 12 | `api/paper.py:1316` | `C:\EdgeLog\fills.csv` | No | Paper-book fill reads (NT-only) |
| 13 | `api/paper.py:1320` | `C:\EdgeLog\ohlc_addon\NQ_10s.csv` | No | 10-second bar feed, primary path |
| 14 | `api/paper.py:1321` | `C:\EdgeLog\ohlc\NQ_10s.csv` | No | 10-second bar feed, fallback path |
| 15 | `api/qqq_exec.py:88` | `C:\EdgeLog\qqq_exec` | **Yes** — `EDGELOG_QQQ_EXEC_DIR` | QQQ shadow adapter output dir |
| 16 | `api/qqq_exec.py:94` | `C:\EdgeLog\ohlc_addon\NQ_10s.csv` | No | QQQ shadow adapter's 10s feed, primary path |
| 17 | `api/qqq_exec.py:95` | `C:\EdgeLog\ohlc\NQ_10s.csv` | No | QQQ shadow adapter's 10s feed, fallback path |
| 18 | `api/qqq_exec.py:96` | `C:\EdgeLog\webull_keys.json` | **Yes** — `EDGELOG_WEBULL_KEYS` | Webull API keys |
| 19 | `api/qqq_exec.py:97` | `C:\EdgeLog\webull_token` | **Yes** — `EDGELOG_WEBULL_TOKEN_DIR` | Webull token directory |
| 20 | `api/qqq_exec.py:120` | `C:\EdgeLog\qqq_exec\KILL` | No | QQQ shadow adapter kill-switch file |
| 21 | `api/qqq_paper_publish.py:46` | `C:\EdgeLog\qqq_paper\state.json` | No | QQQ paper-board publish state |
| 22 | `api/qqq_paper_publish.py:47` | `C:\EdgeLog\qqq_paper\blotter.csv` | No | QQQ paper-board blotter |
| 23 | `api/runner.py:2282` | `C:\EdgeLog\fills.csv` (CLI default) | **Yes** — `EDGELOG_NT_FILLS` | `--nt-fills` flag default |
| 24 | `api/runner.py:2288` | `C:\EdgeLog\webull_keys.json` (CLI default) | **Yes** — `EDGELOG_WEBULL_KEYS` | `--webull-keys` flag default |
| 25 | `api/webull_sync.py:44` | `C:\EdgeLog\webull_keys.json` | **Yes** — `EDGELOG_WEBULL_KEYS` | Webull API keys |
| 26 | `api/webull_sync.py:45` | `C:\EdgeLog\webull_token` | **Yes** — `EDGELOG_WEBULL_TOKEN_DIR` | Webull token directory |

**26 hardcoded lines across 11 files in `api/`.** 9 of them already read an env
override first and only fall back to the Windows path (rows 1, 9, 10, 15, 18, 19, 23,
24, 25, 26 — using `os.environ.get("EDGELOG_...", r"C:\EdgeLog\...")`) — this bundle's
`install.sh` sets those overrides in `edgelog.env`, so they already work correctly on
Linux today. The other 17 (rows 2-8, 11-14, 16-17, 20-22) are plain hardcoded strings
with no override; on the cloud box they simply point at paths that don't exist, so
those specific side duties (mostly the NinjaTrader-bridge readers, which have nothing
to read without NT running) degrade to "not present" rather than doing anything, and
the QQQ shadow adapter's 10-second bar feed (rows 13, 16-17) and kill-switch (row 20)
won't work in CLOUD mode until one of those is fixed — noted here for whoever does
that follow-up, not addressed in this bundle.

**`augur_engine/*.py` has zero hardcoded paths.** `augur_engine/paths.py` already
supports a Linux home out of the box: every path (`ROOT`, `UPLOADS`, `STRAT_DIR`,
`PINE_DIR`, `DB_PATH`, `CONFIG`, `TRIAL_CACHE_DB`) is built with `os.path.join` off
`os.path.dirname(os.path.abspath(__file__))` — the repo's own location — so it's
already correct on any OS with no changes needed. The job-queue runner's actual
backtest/validate engine work runs entirely through this package, which is why the
runner's core function (draining the Firestore queue and running jobs) works on this
cloud box today, even though several of its Windows-PC side duties don't yet.

---

## Troubleshooting

- **`systemctl status` shows `failed`:** run `journalctl -u edgelog-runner -n 50
  --no-pager` for the real error, and check `bash deploy/cloud/check.sh` — the most
  common cause is a missing secret (step d) or an unedited `NTFY_TOPIC=CHANGE-ME`
  causing the healthcheck to skip pushes (harmless, but you won't get alerts).
- **"Out of capacity" when creating the VM:** see the retry trick in step (a) — this
  is normal for the free ARM shape in busy regions, not an account problem.
- **Can't SSH in:** confirm the security list still only opens port 22 and that
  you're using the private key that matches the public key you added at creation.
