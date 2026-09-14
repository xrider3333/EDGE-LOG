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

## Do these in order

One numbered list, start to finish. Each step links to its detailed section below.
Nothing here creates an Oracle account, enters your Webull/Firebase credentials, or
places an order — every step that touches money or credentials is something you
personally do.

1. **Create the Oracle account and the VM.** <https://signup.oraclecloud.com/> → see
   [(a) Create the free Oracle Cloud VM](#a-create-the-free-oracle-cloud-vm) below.
2. **Download the SSH key** Oracle generates when you create the VM (or paste your own
   public key at creation) — you'll need its file path in steps 4 and 5.
3. **SSH in and run the installer** — see [(b) SSH in](#b-ssh-in) and
   [(c) Install everything with one command](#c-install-everything-with-one-command).
   This clones the repo, builds the Python environment, and installs (but does not
   start) `edgelog-runner.service` and `edgelog-qqq-exec.service`.
4. **Copy your secrets up from the PC**, using `push_secrets.ps1` from a PowerShell
   window ON YOUR PC (never run this on the VM, and this script never prints a secret's
   contents — only file names/sizes):
   ```powershell
   cd C:\Users\xride\OneDrive\Desktop\EDGE-LOG\deploy\cloud
   .\push_secrets.ps1 -VmIp <the-public-ip> -KeyPath C:\path\to\your-downloaded-key.key
   ```
   It copies `serviceAccount.json`, the live Webull keys + token, and — if you already
   have one — the Webull paper-trading keys. Re-run it any time a secret changes (e.g.
   a fresh Webull live token).
5. **Fill in `~/edgelog/edgelog.env`** on the VM (`nano ~/edgelog/edgelog.env`) — see
   [`edgelog.env.example`](edgelog.env.example) for what every line means. At minimum,
   set `NTFY_TOPIC`. Leave `EDGELOG_HOST_ROLE=cloud` exactly as install.sh wrote it.
6. **Enable and start the services**, qqq-exec BEFORE runner (order matters — see
   `edgelog-qqq-exec.service`'s own comments):
   ```bash
   sudo systemctl start edgelog-qqq-exec.service
   sudo systemctl start edgelog-runner.service
   bash ~/edgelog/EDGE-LOG/deploy/cloud/check.sh
   ```
7. **Confirm the phone tab shows CLOUD** — open the EDGELOG web app's QQQ SHADOW /
   Webull paper tab and check the status card's "running on" reads **CLOUD**, not
   THIS PC. If it still says THIS PC, `check.sh`'s log tail will show why
   (`edgelog-qqq-exec.service` not started, or its heartbeat not fresh yet).
8. **Turn the PC-side shadow adapter off**, only after step 7 confirms CLOUD is live:
   stop `C:\EdgeLog\_run_qqq_exec.vbs`'s process (Task Manager, or however you normally
   stop it) and don't relaunch it. **You do not have to race this** — the cross-host
   lease guard (see below) already refuses to let the VM and the PC serve at the same
   time, so there is no window where both place orders; this step is just cleanup so
   the PC stops ticking uselessly.
9. **Decide on PAPER mode** (flip it on with a one-line config change) — see
   [Webull ORDER adapter](#webull-order-adapter-paper-orders-now-live-staged-for-later)
   below for the exact steps and the LIVE 2FA caveat. Do this whenever you're ready;
   it is independent of steps 1–8 above.

**Why two hosts can never both trade:** the QQQ shadow adapter publishes a heartbeat
(`lease.host_id` / `lease.leased_at`) to the same Firestore status doc the phone tab
reads, every tick. Before either host starts serving, it checks that doc: if the OTHER
host's heartbeat is still fresh (under 90 seconds old), it refuses to serve and says so
in its log, rather than risk two copies mirroring orders to the same broker account at
once. A host only takes over once the other one's heartbeat has actually gone stale
(crashed, stopped, or never started) — so step 8 is safe to do at your own pace.

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

Three-to-four files never live in the git repo (they're gitignored / kept off GitHub
on purpose) and have to be copied, once, from your PC to the VM. **Preferred:** run
`deploy/cloud/push_secrets.ps1` from a PowerShell window on your PC (see
[Do these in order, step 4](#do-these-in-order) above) — it copies exactly these
files, sets `chmod 600` on each, and never prints a secret's contents. Its manual
equivalent, if you'd rather run scp yourself:

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

# only if you already have Webull paper-trading credentials (see "Webull ORDER
# adapter" below) -- skip this one until you do:
scp -i C:\path\to\your-downloaded-key.key `
    "C:\EdgeLog\webull_paper_keys.json" `
    ubuntu@<the-public-ip>:~/edgelog/webull_paper_keys.json
```

What each one is:
- **`serviceAccount.json`** — the Firebase admin key. Lets the cloud runner read/write
  the same job queue and run history your web app already uses. Treat it like a
  password; it isn't in git.
- **`webull_keys.json`** — your Webull OpenAPI App Key/Secret, used by the QQQ shadow
  adapter and the daily Webull trade-history pull.
- **`webull_token\token.txt`** — the current Webull login token, so the box doesn't
  need you to re-authenticate Webull by hand.
- **`webull_paper_keys.json`** (optional, once you have it) — the SEPARATE sandbox
  App Key/Secret that flips the Webull ORDER adapter into PAPER mode. See "Webull
  ORDER adapter" below.

Then finish `~/edgelog/edgelog.env` on the VM (`nano ~/edgelog/edgelog.env`) — see
[`edgelog.env.example`](edgelog.env.example) for what every line means. At minimum,
fill in `NTFY_TOPIC` (the push-notification topic — reuse the one already set on your
PC in `tools/_restart_runner.bat.example`, or pick a fresh name at <https://ntfy.sh>).

---

## (e) Start it and confirm it's running

Start the QQQ shadow adapter BEFORE the runner (see `edgelog-qqq-exec.service`'s own
comments for why the order matters):

```bash
sudo systemctl start edgelog-qqq-exec.service
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

## Webull ORDER adapter (paper orders now, live staged for later)

`api/webull_orders.py` lets a strategy place a stock/ETF order through Webull's
**official** OpenAPI — first into Webull's paper/sandbox environment, later (only when
the owner explicitly arms it) into the real live account. It ships **OFF by default**:
with nothing configured, it just writes down what it WOULD have ordered and sends
nothing. This section is for the owner, in plain language, covering only the pieces
this bundle adds — the module itself, its tests, and these env vars/directories.

### Where paper credentials go

Webull's paper-trading OpenAPI needs its own app key/secret, **separate from** the
live one already in `webull_keys.json`. On the VM that file is:

```
~/edgelog/webull_paper_keys.json
```

(the `EDGELOG_WEBULL_PAPER_KEYS` line `install.sh` writes into `edgelog.env`). Shape:

```json
{"app_key": "your-sandbox-app-key", "app_secret": "your-sandbox-app-secret"}
```

Until that file exists (or while it still has placeholder text), the adapter logs one
line naming exactly this and sends nothing — it will **never** read the live
`webull_keys.json` as a fallback, even if both files are present. Copy it up with
`scp`, the same way as the other secrets in step (d) above. There is no paper token
directory to copy — `webull_paper_token/` starts empty and the SDK populates it after
the first paper login (a 2FA approval on the owner's phone), no different from the
existing live-token flow the day-to-day steps above already document.

### How to enable Webull's paper trading access (verified 2026-09-13 against
developer.webull.com's own docs — Individual Application API, "Retail Individual
Mode" → Sandbox tab)

1. Go to webull.com, log in, click your avatar (top right) → **Developer Tool** →
   this opens the **Developer Management Center**.
2. Under **My Application**, click **"Using OpenAPI service in Paper Trading"**.
3. That opens the **Sandbox Trading** page → **API Management** → **My Application**
   → apply for the **Sandbox Trading API**. Webull's docs state this is
   auto-approved, typically within a few minutes — no waiting on a human reviewer.
4. Still under **API Management** → **API Keys Management**: register an
   application (give it a name, tick "I have read and accept the agreement"), then
   click **Generate Key** to get an **App Key** + **App Secret**. (**Reset Key**
   there invalidates the old key immediately — only use it if you need to rotate.)
5. Save those two values to `webull_paper_keys.json` (path above) as:
   ```json
   {"app_key": "your-sandbox-app-key", "app_secret": "your-sandbox-app-secret"}
   ```
   (`api/webull_orders.py`'s `load_paper_keys()` reads exactly these two field
   names — `app_key` and `app_secret` — nothing else.) Webull's environments doc
   confirms the sandbox Trading HTTP host is `api.sandbox.webull.com` (events
   `events-api.sandbox.webull.com`) — already wired into this adapter, nothing to
   configure on your end for that part.
6. Webull states paper logins are normal (no forced 2FA), unlike the live flow's
   ~2-week re-approval below.

*One thing I could not verify from outside a real account: whether the portal's menu
wording is character-for-character what's above at the moment you click through it —
Webull sometimes reflows its own UI. If a label looks slightly different, it will be
the nearest thing on the page to "Paper Trading" / "Sandbox" / "API Keys".*

### The 2FA token problem for LIVE (read this before ever arming LIVE)

The **existing live** Webull key (used today by `api/webull_sync.py`) re-authenticates
via a 2FA approval on the owner's phone roughly **every two weeks** — the SDK caches a
token under `webull_token/` between approvals. That is fine for a daily trade-history
pull that just backs off and retries later, but it is a real problem for an
**unattended, 24/7 order-placing** process on a VM nobody is watching: if the token
lapses while the owner is asleep or away, LIVE order calls fail closed (this module
refuses when its client build errors) — but it means the strategy silently stops
placing real orders until someone re-approves on their phone. Options, none applied by
this bundle:
- **Accept the gap.** Treat a lapsed LIVE token as a "flat until re-approved" state —
  safe (nothing fires) but the strategy misses whatever it would have traded in that
  window. This module already fails closed this way; no code change needed.
- **Alert on it.** Wire a check (future work) that pages the owner via `ntfy.sh`
  (already used by `edgelog-healthcheck.service`) the moment a LIVE order attempt
  fails with a re-auth-looking error, so the two-week clock is never a surprise.
- **Ask Webull for a longer-lived / app-only credential** for the live account, if
  their OpenAPI offers one — not confirmed either way from the SDK source alone.
- **Never run LIVE unattended at all** — only PAPER runs 24/7 on the VM; LIVE stays a
  manually-armed, manually-watched mode the owner turns on only when present. This is
  the safest default and requires nothing further.

Paper mode does NOT have this problem the same way (its own token, and Webull's docs
say paper logins are normal, not gated behind 2FA) — this is a LIVE-only wrinkle.

### Flipping PAPER on is a one-line config change

Once `webull_paper_keys.json` exists (steps above) and every shadow OPEN/CLOSE is
already wired to hand its intent to this adapter (`api/qqq_exec.py`'s
`_mirror_to_broker`, always on — mode OFF is what makes it a no-op today), turning
PAPER trading on is exactly **one line** in a file that doesn't exist until you create
it — nothing else to touch:

```bash
mkdir -p ~/edgelog/webull_orders   # or C:\EdgeLog\webull_orders on the PC
cat > ~/edgelog/webull_orders/config.json <<'EOF'
{"mode": "PAPER"}
EOF
```

(`EDGELOG_WEBULL_ORDERS_CONFIG` in `edgelog.env` already points here — see
`edgelog.env.example`.) The adapter re-reads this file fresh on the next order it
places (it does not need a restart to notice a mode flip), and its `status()` —
folded into the published `meta/qqq_exec` doc's `"broker"` field — will show
`effective_mode: "PAPER"` and `paper_credentials_present: true` once both are true.

Before relying on PAPER results for anything, also set real rails in that same
`config.json` (`"rails": {"max_shares_per_leg": ..., "max_total_position_shares": ...,
"daily_loss_limit_usd": ..., "session_start": ..., "session_end": ...}`) — the shipped
defaults (`DEFAULT_RAILS` in `api/webull_orders.py`) are conservative placeholders,
not tuned to any real strategy. **Never** create `webull_orders/ARM_LIVE` until you've
picked a LIVE unattended-token policy from the options above — that file plus
`"mode": "LIVE"` in `config.json` are the only two things that arm real-money orders,
and neither is created by this bundle or by any Claude session without your explicit
ask.

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
| 15 | `api/qqq_exec.py` `OUT_DIR` | `C:\EdgeLog\qqq_exec` | **Yes** — `EDGELOG_QQQ_EXEC_DIR`, else `EDGELOG_HOME`/qqq_exec | QQQ shadow adapter output dir (**FIXED 2026-09-13** — was a bare literal, now `EDGELOG_HOME`-based) |
| 16 | `api/qqq_exec.py` `NQ_10S_PRIMARY` | `C:\EdgeLog\ohlc_addon\NQ_10s.csv` | **Yes** — `EDGELOG_NQ_10S_PRIMARY`, else `EDGELOG_HOME` (**FIXED 2026-09-13**) | QQQ shadow adapter's 10s feed, primary path (ninjatrader signal-source mode only) |
| 17 | `api/qqq_exec.py` `NQ_10S_FALLBACK` | `C:\EdgeLog\ohlc\NQ_10s.csv` | **Yes** — `EDGELOG_NQ_10S_FALLBACK`, else `EDGELOG_HOME` (**FIXED 2026-09-13**) | QQQ shadow adapter's 10s feed, fallback path (ninjatrader signal-source mode only) |
| 18 | `api/qqq_exec.py` `WEBULL_KEYS` | `C:\EdgeLog\webull_keys.json` | **Yes** — `EDGELOG_WEBULL_KEYS`, else `EDGELOG_HOME` | Webull API keys |
| 19 | `api/qqq_exec.py` `_WEBULL_TOKEN_DIR` | `C:\EdgeLog\webull_token` | **Yes** — `EDGELOG_WEBULL_TOKEN_DIR`, else `EDGELOG_HOME` | Webull token directory |
| 20 | `api/qqq_exec.py` `DEFAULT_CONFIG["kill_file"]` | `C:\EdgeLog\qqq_exec\KILL` | **Yes** — derives from `OUT_DIR` (row 15), so `EDGELOG_QQQ_EXEC_DIR`/`EDGELOG_HOME` move it too (**FIXED 2026-09-13**) | QQQ shadow adapter kill-switch file |
| 21 | `api/qqq_paper_publish.py:46` | `C:\EdgeLog\qqq_paper\state.json` | No | QQQ paper-board publish state |
| 22 | `api/qqq_paper_publish.py:47` | `C:\EdgeLog\qqq_paper\blotter.csv` | No | QQQ paper-board blotter |
| 23 | `api/runner.py:2282` | `C:\EdgeLog\fills.csv` (CLI default) | **Yes** — `EDGELOG_NT_FILLS` | `--nt-fills` flag default |
| 24 | `api/runner.py:2288` | `C:\EdgeLog\webull_keys.json` (CLI default) | **Yes** — `EDGELOG_WEBULL_KEYS` | `--webull-keys` flag default |
| 25 | `api/webull_sync.py:44` | `C:\EdgeLog\webull_keys.json` | **Yes** — `EDGELOG_WEBULL_KEYS` | Webull API keys |
| 26 | `api/webull_sync.py:45` | `C:\EdgeLog\webull_token` | **Yes** — `EDGELOG_WEBULL_TOKEN_DIR` | Webull token directory |
| 27 | `api/webull_orders.py` `DEFAULT_CONFIG_PATH` | `C:\EdgeLog\webull_orders\config.json` | **Yes** — `EDGELOG_WEBULL_ORDERS_CONFIG` | Order adapter mode + rails config |
| 28 | `api/webull_orders.py` `DEFAULT_PAPER_KEYS` | `C:\EdgeLog\webull_paper_keys.json` | **Yes** — `EDGELOG_WEBULL_PAPER_KEYS` | Webull PAPER (sandbox) API keys |
| 29 | `api/webull_orders.py` `DEFAULT_PAPER_TOKEN_DIR` | `C:\EdgeLog\webull_paper_token` | **Yes** — `EDGELOG_WEBULL_PAPER_TOKEN_DIR` | PAPER token directory |
| 30 | `api/webull_orders.py` `DEFAULT_ARM_LIVE_FILE` | `C:\EdgeLog\webull_orders\ARM_LIVE` | **Yes** — `EDGELOG_WEBULL_ARM_LIVE` | LIVE-mode arm file (owner-created only) |
| 31 | `api/webull_orders.py` `DEFAULT_KILL_FILE` | `C:\EdgeLog\webull_orders\KILL` | **Yes** — `EDGELOG_WEBULL_ORDERS_KILL` | Order adapter kill switch |
| 32 | `api/webull_orders.py` `DEFAULT_STATE_PATH` | `C:\EdgeLog\webull_orders\state.json` | **Yes** — `EDGELOG_WEBULL_ORDERS_STATE` | Idempotency/rails state file |

**32 hardcoded lines across 12 files in `api/`.** 18 of them already read an env
override first and only fall back to a default path (rows 1, 9, 10, 15-20, 23,
24, 25, 26-32 — using `os.environ.get("EDGELOG_...", ...)`) — this
bundle's `install.sh` sets those overrides (rows 27-32 newly added by the Webull ORDER
adapter, rows 15-20 **FIXED 2026-09-13** to default off `EDGELOG_HOME` instead of a
bare `C:\EdgeLog\...` literal — see `api/qqq_exec.py`'s `EDGELOG_HOME`/`_default_edgelog_home`
— all still defaulted to non-existent paths so the adapter starts in its safe OFF
no-op state until the owner fills them in) in `edgelog.env`, so they already work
correctly on Linux today. The other 14 (rows 2-8, 11-14, 21-22) are plain
hardcoded strings with no override; on the cloud box they simply point at paths that
don't exist, so those specific side duties (the NinjaTrader-bridge readers, which have
nothing to read without NT running, plus `api/paper.py`'s own 10-second NQ bar feed
and `api/qqq_paper_publish.py`) degrade to "not present" rather than doing anything —
noted here for whoever does that follow-up, not addressed in this bundle. The QQQ
shadow adapter itself (`api/qqq_exec.py`) no longer has this problem: rows 15-20 are
fixed, and its default `signal_source` is "engine" (api/cloud_signal.py's own QQQ-bar
signals), which never reads the NinjaTrader/NQ-feed paths in rows 16-17 at all — see
that module's docstring.

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
- **Phone tab still shows THIS PC, not CLOUD:** `journalctl -u edgelog-qqq-exec -n 50
  --no-pager` — the most common cause is the log line `REFUSING to serve for <uid>:
  host '<pc-hostname>' holds a fresh lease` (the PC-side adapter is still running and
  ticking within the last 90 seconds — that's the cross-host guard working correctly,
  not a bug; wait for the PC copy to stop, or stop it yourself, and the VM will take
  over the next time its heartbeat goes stale). A missing `serviceAccount.json` or an
  unreachable Firestore also shows up here rather than silently failing.
- **Worried two copies might trade at once:** they can't stay running at once by
  design — see "Why two hosts can never both trade" in the numbered checklist above —
  but if you ever need to force a takeover immediately rather than wait ~90 seconds,
  stop the other host's service/process first, then start this one.
