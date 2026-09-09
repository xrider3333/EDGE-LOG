#!/usr/bin/env bash
# EDGE-LOG cloud healthcheck -- run every 5 min by edgelog-healthcheck.timer.
#
# The runner writes a line to runner.log on basically every pass of its watch loop
# (queue poll every 30s at minimum). If that file hasn't been touched in 10+ minutes,
# the process is hung or dead even if systemd still shows it "active" (a wedged
# thread doesn't crash the process). Force a restart and page the owner over ntfy --
# there is nobody sitting at this box to notice a silent stall.
set -euo pipefail

EDGELOG_HOME="${EDGELOG_HOME:-$HOME/edgelog}"
LOG_FILE="${EDGELOG_HOME}/logs/runner.log"
STALE_SEC=600   # 10 minutes
NTFY_TOPIC="${NTFY_TOPIC:-}"

_ntfy() {
  local msg="$1"
  if [ -z "$NTFY_TOPIC" ]; then
    echo "[healthcheck] NTFY_TOPIC not set in edgelog.env -- skipping push: $msg"
    return 0
  fi
  curl -fsS -m 10 -d "$msg" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 \
    || echo "[healthcheck] ntfy push failed (non-fatal)"
}

if [ ! -f "$LOG_FILE" ]; then
  echo "[healthcheck] ${LOG_FILE} does not exist yet -- runner may still be starting, skipping"
  exit 0
fi

now_epoch=$(date +%s)
mtime_epoch=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo "$now_epoch")
age=$(( now_epoch - mtime_epoch ))

if [ "$age" -gt "$STALE_SEC" ]; then
  echo "[healthcheck] runner.log is ${age}s old (> ${STALE_SEC}s) -- restarting edgelog-runner.service"
  systemctl restart edgelog-runner.service
  _ntfy "EDGE-LOG cloud runner: log was stale (${age}s old), restarted the service."
else
  echo "[healthcheck] runner.log is ${age}s old -- OK"
fi
