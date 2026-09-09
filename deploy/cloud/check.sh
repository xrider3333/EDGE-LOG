#!/usr/bin/env bash
# EDGE-LOG cloud runner status check -- run this by hand any time.
# Read-only: prints service status, the last 20 log lines, disk/mem, and whether the
# env file + copied secrets exist. Never restarts or changes anything.
set -uo pipefail

EDGELOG_HOME="${EDGELOG_HOME:-$HOME/edgelog}"
REPO_DIR="${EDGELOG_HOME}/EDGE-LOG"
LOG_FILE="${EDGELOG_HOME}/logs/runner.log"

hr() { printf '%s\n' "------------------------------------------------------------"; }

hr; echo "SERVICE STATUS"; hr
systemctl status edgelog-runner.service --no-pager -l 2>&1 || echo "(edgelog-runner.service not found -- run install.sh)"
echo
systemctl list-timers edgelog-healthcheck.timer --no-pager 2>&1 || echo "(edgelog-healthcheck.timer not found -- run install.sh)"

hr; echo "LAST 20 LOG LINES (${LOG_FILE})"; hr
if [ -f "$LOG_FILE" ]; then
  tail -n 20 "$LOG_FILE"
else
  echo "MISSING: ${LOG_FILE}"
fi

hr; echo "DISK"; hr
df -h "$EDGELOG_HOME" 2>/dev/null || df -h /

hr; echo "MEMORY"; hr
free -h

hr; echo "ENV FILE + SECRETS"; hr
check_path() {
  local path="$1" label="$2"
  if [ -e "$path" ]; then
    local size
    size=$(stat -c%s "$path" 2>/dev/null || echo "?")
    printf '  [ok]      %-9s %-55s %s bytes\n' "$label" "$path" "$size"
  else
    printf '  [MISSING] %-9s %s\n' "$label" "$path"
  fi
}
check_path "${EDGELOG_HOME}/edgelog.env"                 "env"
check_path "${REPO_DIR}/serviceAccount.json"              "firebase"
check_path "${EDGELOG_HOME}/webull_keys.json"             "webull"
check_path "${EDGELOG_HOME}/webull_token/token.txt"       "webull"
hr
