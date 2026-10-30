# C18 - trading-PC hygiene plan (DISC draft, 2026-10-30, board C18 via MANAGER #124)

Three asks: broker keys out of agent reach, a secret scanner on every push, a versioned backup to a second drive.
Anything that changes system settings, ACLs or scheduled tasks is marked **OWNER** - the owner does it; agents do not.

## 1. Secret scanner on every push - DONE in this commit
- `tools/secret_scan.py` scans the ADDED lines of every pushed commit (and new file names) for private-key blocks,
  GCP service-account keys, Google / GitHub / Anthropic / OpenAI / AWS / Slack tokens, and `key|secret|token|password|pin = "<16+ chars>"`.
- Wired into `tools/githooks/pre-push` before the boot gate: a hit REFUSES the push (exit 1); a tooling failure
  never blocks (exit 2). Values are masked in the output; a secret is never printed.
- Forbidden file names: serviceAccount*.json, credentials*.json, .env, *.key, *.pem, .alpaca_keys.json,
  webull*keys*.json, augur_config.json, id_rsa*.
- Placeholders (PASTE_/NOT_A/EXAMPLE/FAKE/DUMMY/TEST...) are skipped; a real false positive is cleared with
  `secret-scan: allow` on that line, never with --no-verify.
- Audit of every tracked file today (`--all`): 0 real hits (4 test placeholders, now skipped).

## 2. Broker keys out of agent reach - PLAN (OWNER steps)
Today the Webull live / paper keys sit in `C:\EdgeLog\webull_*keys*.json` and `C:\EdgeLog\webull_orders\config.json`,
readable by every Claude shell (same Windows user). Agents only need to place orders through the executor, never read the keys.
- **Step A (OWNER):** create a second local Windows user `edgelog-exec` and move the key files into a folder only that user
  (and SYSTEM) can read - `icacls <dir> /inheritance:r /grant edgelog-exec:R /grant SYSTEM:F`.
- **Step B (OWNER):** run the Webull executor / box sync under that user (Task Scheduler "Run as edgelog-exec").
  The code already reads keys from `EDGELOG_WEBULL_KEYS` / `EDGELOG_WEBULL_PAPER_KEYS`, so only the path changes.
- **Step C (agents, after A+B):** add a `.claude/settings.json` deny rule for `Read(C:/EdgeLog/**/*keys*.json)` and the
  new folder (a backstop; the ACL is the real wall), and a startup check in the executor that refuses to run if the
  key file is readable by the interactive user.
- Rotate the Webull app secret once after the move (OWNER, in the Webull portal) - assume today's copy has been read.

## 3. Versioned backup to a second drive - PLAN (OWNER installs, agents write the script)
- What: `C:\EdgeLog\` (masters, run records, caches, inbox, state), the repo is already on GitHub, Firestore has its nightly backup.
- How: a robocopy mirror into dated snapshots on drive D: (or USB), keep 14 daily + 8 weekly; key files EXCLUDED
  (they stay only on the PC and in the owner's password manager).
- Script: `tools/backup_edgelog.ps1` (to write next, dry-run mode default). **OWNER** schedules it daily at 20:30
  (before his 21:00 sign-out) and picks the drive.

## Open for the owner
1. Approve Step A/B (second Windows user + ACL) or name another wall.
2. Name the backup drive.
