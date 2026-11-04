#!/usr/bin/env bash
# Install the EDGE-LOG needrestart override on the Oracle box (CHANGE_CONTROL.md
# "Automatic Ubuntu upgrades", option a). Idempotent: safe to run every deploy.
#
#   1. copies deploy/cloud/needrestart-edgelog.conf -> /etc/needrestart/conf.d/edgelog.conf
#      (only when the content differs)
#   2. pins Unattended-Upgrade::Automatic-Reboot "false" in
#      /etc/apt/apt.conf.d/52edgelog-no-auto-reboot (the box must never reboot itself)
#   3. verifies with a batch/list-only needrestart dry run (-b -r l): neither edgelog
#      service may appear as "needs restart"
#   4. prints whether /var/run/reboot-required exists (a pending kernel reboot is
#      taken BY HAND on a weekend, see CHANGE_CONTROL.md "Pending reboot")
#
# Usage (on the box): sudo bash deploy/cloud/install_needrestart_override.sh
# Exit 0 = installed + verified; 1 = verification found an edgelog service still
# marked for restart; 2 = could not install.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/needrestart-edgelog.conf"
DST="/etc/needrestart/conf.d/edgelog.conf"
APT_DST="/etc/apt/apt.conf.d/52edgelog-no-auto-reboot"
APT_LINE='Unattended-Upgrade::Automatic-Reboot "false";'
SUDO=""
if [ "$(id -u)" != "0" ]; then SUDO="sudo -n"; fi

echo "needrestart override: source $SRC"
if [ ! -f "$SRC" ]; then echo "FAILED: $SRC missing"; exit 2; fi

# 1. conf.d override (write only when changed)
$SUDO mkdir -p "$(dirname "$DST")" || { echo "FAILED: cannot create $(dirname "$DST")"; exit 2; }
if $SUDO cmp -s "$SRC" "$DST" 2>/dev/null; then
  echo "needrestart override: $DST already up to date (unchanged)"
else
  $SUDO install -m 0644 -o root -g root "$SRC" "$DST" || { echo "FAILED: install $DST"; exit 2; }
  echo "needrestart override: INSTALLED $DST"
fi

# 2. apt: never reboot automatically
if [ -f "$APT_DST" ] && $SUDO grep -qxF "$APT_LINE" "$APT_DST" 2>/dev/null; then
  echo "apt auto-reboot: $APT_DST already set (unchanged)"
else
  printf '%s\n' "// EDGE-LOG: the box must never reboot itself after an unattended upgrade." \
                "$APT_LINE" | $SUDO tee "$APT_DST" >/dev/null \
    || { echo "FAILED: write $APT_DST"; exit 2; }
  echo "apt auto-reboot: WROTE $APT_DST"
fi
echo "apt effective: $(apt-config dump 2>/dev/null | grep -i 'Unattended-Upgrade::Automatic-Reboot ' || echo 'Unattended-Upgrade::Automatic-Reboot (unset = off)')"

# 3. verify: batch, list-only dry run (never restarts anything)
rc=0
if command -v needrestart >/dev/null 2>&1; then
  OUT="$($SUDO needrestart -b -r l 2>&1)"
  echo "needrestart -b -r l:"
  printf '%s\n' "$OUT" | sed 's/^/  /'
  if printf '%s\n' "$OUT" | grep -E 'NEEDRESTART-SVC: *edgelog-(qqq-exec|cloud-signal)\.service' >/dev/null; then
    echo "VERIFY FAILED: an edgelog service is still marked for restart by needrestart"
    rc=1
  else
    echo "VERIFY OK: neither edgelog-qqq-exec nor edgelog-cloud-signal is marked for restart"
  fi
else
  echo "needrestart not installed on this box -- nothing to override (conf left in place)"
fi

# 4. pending reboot?
if [ -e /var/run/reboot-required ]; then
  echo "REBOOT PENDING: /var/run/reboot-required exists ($(stat -c %y /var/run/reboot-required 2>/dev/null | cut -d. -f1))"
  [ -f /var/run/reboot-required.pkgs ] && echo "  packages: $(tr '\n' ' ' < /var/run/reboot-required.pkgs)"
  echo "  take it on a weekend with both services stopped (CHANGE_CONTROL.md 'Pending reboot')"
else
  echo "no reboot pending (/var/run/reboot-required absent)"
fi
exit $rc
