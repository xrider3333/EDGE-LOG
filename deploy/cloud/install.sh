#!/usr/bin/env bash
# EDGE-LOG cloud runner installer -- Ubuntu 24.04 ARM (Oracle Cloud "Always Free" A1,
# or any similar box). Idempotent: safe to re-run after `git pull` to pick up new
# deps/units -- it never overwrites an env file the owner has already edited, and
# `git clone` only happens once (later runs fast-forward `main` instead).
#
# What this does:
#   1. apt: python3.12 + venv + build deps
#   2. clone/update ~/edgelog/EDGE-LOG from GitHub
#   3. create a venv, pip install the runner's full runtime dependency set
#      (deploy/cloud/requirements-cloud.txt)
#   4. create ~/edgelog/{ohlc,qqq_exec,logs,webull_token}
#   5. write ~/edgelog/edgelog.env ONCE (fill in the CHANGE-ME lines yourself)
#   6. install + enable the systemd units (edgelog-runner.service,
#      edgelog-healthcheck.timer/.service)
#
# Usage (see README.md for the full runbook):
#   curl -fsSL https://raw.githubusercontent.com/xrider3333/EDGE-LOG/main/deploy/cloud/install.sh | bash
#   -- or --
#   git clone https://github.com/xrider3333/EDGE-LOG.git ~/edgelog/EDGE-LOG
#   bash ~/edgelog/EDGE-LOG/deploy/cloud/install.sh
#
# This script does NOT start the runner -- it stops short of that on purpose so you
# can copy the secrets first. After it finishes: copy serviceAccount.json,
# webull_keys.json and webull_token/token.txt (README.md step (d)), edit
# ~/edgelog/edgelog.env, then `sudo systemctl start edgelog-runner.service`.

set -euo pipefail

REPO_URL="https://github.com/xrider3333/EDGE-LOG.git"
EDGELOG_HOME="${EDGELOG_HOME:-$HOME/edgelog}"
REPO_DIR="${EDGELOG_HOME}/EDGE-LOG"
VENV_DIR="${EDGELOG_HOME}/venv"
RUN_USER="$(id -un)"
# Owner's Firebase uid -- already committed in plain text in this same repo at
# tools/_restart_runner.bat.example (the Windows launcher's --allow-uid), reused here
# so the cloud runner allowlists the same account without inventing a new secret.
ALLOW_UID="IO0K35JpLIcH9YK4C0pMNYUzZOM2"

echo "==> EDGE-LOG cloud installer: home=${EDGELOG_HOME} user=${RUN_USER}"

# 1. OS packages ---------------------------------------------------------------
echo "==> apt: python3.12 + venv + build deps"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  python3.12 python3.12-venv python3-pip \
  build-essential git curl ca-certificates tzdata

# 2. Clone / update the repo ----------------------------------------------------
mkdir -p "$EDGELOG_HOME"
if [ -d "${REPO_DIR}/.git" ]; then
  echo "==> repo already at ${REPO_DIR}, fast-forwarding main"
  git -C "$REPO_DIR" fetch --quiet origin
  git -C "$REPO_DIR" checkout --quiet main
  git -C "$REPO_DIR" merge --ff-only --quiet origin/main
else
  echo "==> cloning ${REPO_URL} -> ${REPO_DIR}"
  git clone --quiet "$REPO_URL" "$REPO_DIR"
fi

# 3. venv + deps -----------------------------------------------------------------
echo "==> python venv: ${VENV_DIR}"
if [ ! -d "$VENV_DIR" ]; then
  python3.12 -m venv "$VENV_DIR"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
echo "==> pip install -r deploy/cloud/requirements-cloud.txt"
"${VENV_DIR}/bin/pip" install -r "${REPO_DIR}/deploy/cloud/requirements-cloud.txt"

# 4. runtime dirs -------------------------------------------------------------------
echo "==> creating ${EDGELOG_HOME}/{ohlc,qqq_exec,logs,webull_token,webull_paper_token,webull_orders}"
mkdir -p "${EDGELOG_HOME}/ohlc" "${EDGELOG_HOME}/qqq_exec" "${EDGELOG_HOME}/logs" \
         "${EDGELOG_HOME}/webull_token" "${EDGELOG_HOME}/webull_paper_token" \
         "${EDGELOG_HOME}/webull_orders"
touch "${EDGELOG_HOME}/logs/runner.log" "${EDGELOG_HOME}/logs/qqq_exec.log"

# 5. env file -- write once, never clobber an owner-edited file --------------------
ENV_FILE="${EDGELOG_HOME}/edgelog.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "==> writing ${ENV_FILE} (edit the CHANGE-ME line before starting the service)"
  cat > "$ENV_FILE" <<EOF
# EDGE-LOG cloud runner environment. Edit CHANGE-ME below, then:
#   sudo systemctl restart edgelog-runner.service
EDGELOG_HOME=${EDGELOG_HOME}
TZ=America/New_York
GOOGLE_APPLICATION_CREDENTIALS=${REPO_DIR}/serviceAccount.json
EDGELOG_WEBULL_KEYS=${EDGELOG_HOME}/webull_keys.json
EDGELOG_WEBULL_TOKEN_DIR=${EDGELOG_HOME}/webull_token
# Webull ORDER adapter (api/webull_orders.py) -- SEPARATE from the live keys above.
# Left pointing at paths that don't exist yet on purpose: the adapter no-ops (logs
# one line, sends nothing) until the owner has real paper credentials and copies
# them here. See README.md "Webull ORDER adapter" section before filling any of
# this in -- do NOT put the live webull_keys.json contents in webull_paper_keys.json.
EDGELOG_WEBULL_PAPER_KEYS=${EDGELOG_HOME}/webull_paper_keys.json
EDGELOG_WEBULL_PAPER_TOKEN_DIR=${EDGELOG_HOME}/webull_paper_token
EDGELOG_WEBULL_ORDERS_CONFIG=${EDGELOG_HOME}/webull_orders/config.json
EDGELOG_WEBULL_ORDERS_STATE=${EDGELOG_HOME}/webull_orders/state.json
EDGELOG_WEBULL_ORDERS_KILL=${EDGELOG_HOME}/webull_orders/KILL
EDGELOG_WEBULL_ARM_LIVE=${EDGELOG_HOME}/webull_orders/ARM_LIVE
EDGELOG_NT_OHLC=${EDGELOG_HOME}/ohlc
EDGELOG_QQQ_EXEC_DIR=${EDGELOG_HOME}/qqq_exec
# Tells the QQQ shadow adapter (api/qqq_exec.py) it is the CLOUD copy, for the phone
# tab's "running on" label. The cross-host lease tells the PC and this VM apart by
# hostname (or EDGELOG_HOST_ID) -- what it does and does not protect is in README.md,
# "Two machines, one shadow book". Leave this exactly as "cloud" -- do NOT set it on the PC.
EDGELOG_HOST_ROLE=cloud
# Fold-level parallelism inside one validate (augur_engine.wf_pool). Keep this at or
# below the box's OCPU count -- 2 for the recommended 2-OCPU/12GB Always Free shape,
# raise to 3-4 if the instance was sized up to 4 OCPU/24GB.
EDGELOG_VALIDATE_WORKERS=2
AUGUR_TRIAL_CACHE=1
# ntfy.sh push topic used by edgelog-healthcheck.service and by the runner's own
# alerters (api/nt_exec_review.py, api/nt_drawdown_alert.py). The owner already has
# a topic in tools/_restart_runner.bat.example on the PC -- reuse it here so alerts
# land on the same phone, or pick a fresh topic name (anyone who learns the topic
# name can read the messages, so treat it like a lightly-kept secret).
NTFY_TOPIC=CHANGE-ME
EOF
else
  echo "==> ${ENV_FILE} already exists, leaving it alone"
fi

# 6. systemd units ------------------------------------------------------------------
echo "==> installing systemd units"
UNIT_SRC="${REPO_DIR}/deploy/cloud"
for unit in edgelog-runner.service edgelog-qqq-exec.service edgelog-cloud-signal.service edgelog-healthcheck.service edgelog-healthcheck.timer edgelog-keel-state.service edgelog-keel-state.timer; do
  sed \
    -e "s#__EDGELOG_USER__#${RUN_USER}#g" \
    -e "s#__EDGELOG_REPO__#${REPO_DIR}#g" \
    -e "s#__EDGELOG_VENV__#${VENV_DIR}#g" \
    -e "s#__EDGELOG_HOME__#${EDGELOG_HOME}#g" \
    -e "s#__EDGELOG_ALLOW_UID__#${ALLOW_UID}#g" \
    "${UNIT_SRC}/${unit}" | sudo tee "/etc/systemd/system/${unit}" >/dev/null
done

sudo systemctl daemon-reload
# The paper book's two services are ENABLED (start on boot) but not started here, so the
# owner copies secrets and reviews rails/mode before either can place a single order.
sudo systemctl enable edgelog-qqq-exec.service edgelog-cloud-signal.service
# KEEL v12 nightly state build (needs the NQ master the PC pushes into ${EDGELOG_HOME}/nq/).
sudo systemctl enable edgelog-keel-state.timer
# The job runner does NOT run on this box (2026-09-21 -- api/runner.py refuses on
# EDGELOG_HOST_ROLE=cloud; see _cloud_runner_refusal there for what went wrong when one
# did). Its unit is still installed so the refusal is logged if anyone starts it, but it
# is switched off at boot, and so is the healthcheck that only ever watched it. A re-run
# of this script on an older box turns both off.
sudo systemctl disable --now edgelog-runner.service edgelog-healthcheck.timer 2>/dev/null || true

echo
echo "==> install.sh done. Nothing is started yet. Next steps:"
echo "    1. Copy secrets from the PC (README.md step (d)):"
echo "         serviceAccount.json   -> ${REPO_DIR}/serviceAccount.json"
echo "         webull_keys.json      -> ${EDGELOG_HOME}/webull_keys.json"
echo "         webull_token/token.txt -> ${EDGELOG_HOME}/webull_token/token.txt"
echo "       (Webull ORDER adapter paper credentials, once you have them, go in"
echo "        ${EDGELOG_HOME}/webull_paper_keys.json -- see README.md \"Webull ORDER adapter\".)"
echo "    2. Edit ${ENV_FILE} (set NTFY_TOPIC)."
echo "    3. Start the paper book (the job runner stays off on this box -- api/runner.py"
echo "       refuses to run here; the PC's runner owns the job queue):"
echo "         sudo systemctl start edgelog-cloud-signal.service"
echo "         sudo systemctl start edgelog-qqq-exec.service"
echo "    4. Check it:          bash ${REPO_DIR}/deploy/cloud/check.sh"
echo "    5. Turn OFF the PC-side shadow adapter once the phone tab shows CLOUD (see"
echo "       README.md's numbered checklist) -- never run both at once."
