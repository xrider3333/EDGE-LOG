# Change control for the live box (WEBULL_GO_LIVE.md 1.9)

Plain rules for changing anything on the Oracle box that runs the Webull QQQ paper book
(`edgelog-qqq-exec` + `edgelog-cloud-signal`).

## The rule

**Deploy only with `python tools/box_deploy.py`, run from the PC.** Never `git pull` on
the box by hand, and never `sudo systemctl restart edgelog-qqq-exec` /
`edgelog-cloud-signal` by hand either — both of those skip every check below.

`tools/box_deploy.py`:
- picks an exact commit (default: `origin/main` right now, printed so you know what
  you're getting) instead of "whatever `main` happens to be when the box pulls";
- refuses between 09:25 and 16:05 ET on a trading day unless you pass
  `--owner-waiver '<text>'` — every waiver is printed and logged, so there is always a
  record of *why* someone deployed mid-session;
- refuses unless the book is flat (no open leg, no non-zero broker position, no
  pending resend/fill-capture) — the same check `flat_restart_once.sh` used to make,
  now unit tested instead of trusted;
- shows you the exact commits and files that are about to change on the book's own
  code paths before it does anything;
- snapshots the box's config before and after, so a config drift is visible
  immediately, not discovered later.

**`~/edgelog/flat_restart_once.sh` is retired.** It restarted both services whenever it
found them flat, with no time-of-day check and no record of who ran it or why — exactly
the kind of silent restart this change control is meant to stop. The lead deletes it
from the box once `box_deploy.py` has shipped there. Do not write anything else like it.

## Config changes

The box's config files (`qqq_exec/config.json`, `webull_orders/config.json`,
`cloud_signal/stream_config.json`, the systemd units, the logrotate config) exist only
on the box — they are not in git, because some of them can hold account ids. Any change
to one of them, made by hand or by a deploy, should be preceded and followed by
`python tools/box_config_snapshot.py`, which copies them into
`C:\EdgeLog\box_config_history\<timestamp>\` (private, untracked, never the repo) and
prints a diff against the last snapshot. `box_deploy.py` already calls this
automatically around every deploy; run it by hand around any OTHER config edit (e.g.
editing `qqq_exec/config.json` directly to change a cap).

## Automatic Ubuntu upgrades

Facts read off the box (read-only) on 2026-09-26:

- **`/etc/apt/apt.conf.d/20auto-upgrades`**: both periodic flags are on —
  `APT::Periodic::Update-Package-Lists "1"` and
  `APT::Periodic::Unattended-Upgrade "1"`. The box checks for and installs updates
  every day (`apt-daily.timer` / `apt-daily-upgrade.timer`, both enabled and running —
  next fires: `apt-daily.timer` daily, `apt-daily-upgrade.timer` daily).
- **`/etc/apt/apt.conf.d/50unattended-upgrades`**: the allowed origins include
  `${distro_id}:${distro_codename}-security` (security updates are installed
  automatically). `Unattended-Upgrade::Automatic-Reboot` is commented out (defaults to
  **off** — the box will not reboot itself even when a kernel update needs one).
- **`/var/run/reboot-required`**: **present** right now (dated 2026-09-21) — a kernel or
  core-library update from five days ago is still waiting for a reboot the box will
  never take on its own, because automatic reboot is off.
- **`/etc/needrestart/needrestart.conf`**: `$nrconf{restart}` is commented out (its
  default, `'i'` — "ask interactively"), and `/etc/needrestart/conf.d/` has no override
  file, only the stock `README.needrestart` placeholder. **No service is excluded from
  needrestart's own default behavior**, which is why it restarts `edgelog-qqq-exec` and
  `edgelog-cloud-signal` whenever a library either one links against gets upgraded —
  there is no interactive terminal for it to ask, so it restarts rather than skips.
- **`journalctl` restarts, last few for each service** — both services restart at the
  identical timestamp every time, confirming they are restarted TOGETHER by the same
  outside event, not independently:
  - 2026-09-23 20:59:59, 21:09:35, 22:48:32 UTC
  - 2026-09-24 20:08:43 UTC
  - 2026-09-25 14:10:47, 20:07:25/41 UTC
  - **2026-09-26 06:23:07 UTC** — this one lines up exactly with
    `/var/log/unattended-upgrades/unattended-upgrades.log`, which shows an unattended
    upgrade of `curl libcurl3t64-gnutls libcurl4t64 libexpat1` starting at 06:23:02 and
    finishing at 06:23:20 that same morning. This is needrestart, triggered by
    unattended-upgrades, restarting both services because they (or something they use)
    link against one of those libraries. It is the clearest evidence on the box that
    an automatic library upgrade restarts the live services with nobody watching.

**Two options — owner decides:**

**(a) Keep security upgrades, stop needrestart from touching the edgelog services.**
Add a new file on the box, `/etc/needrestart/conf.d/edgelog.conf`:

```perl
# EDGE-LOG: never let needrestart auto-restart the live book services. A library
# upgrade still gets installed; the SERVICE restart happens only through
# tools/box_deploy.py, on the owner's schedule.
$nrconf{override_rc}{'^edgelog-qqq-exec\.service$'} = 0;
$nrconf{override_rc}{'^edgelog-cloud-signal\.service$'} = 0;
```

(`0` in `override_rc` means "treat as already restarted / does not need a restart" —
the same mechanism the stock file already uses for `docker`, `NetworkManager`, etc.)
Unattended security upgrades keep happening; the two services simply stop being
restarted because of them. The already-pending reboot (`/var/run/reboot-required`)
should then be scheduled for a weekend by hand, since this file only stops
*service*-level restarts, not a kernel reboot.

**(b) Leave it as is.** Security patches keep landing, and needrestart keeps
restarting both services within a minute or two of any library upgrade that touches
them, at any time of day — including mid-session, since `apt-daily-upgrade.timer`
does not know or care about market hours.

Neither option is applied by this change — the owner picks one and the lead applies it
by hand on the box.
