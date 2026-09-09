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
echo "==> creating ${EDGELOG_HOME}/{ohlc,qqq_exec,logs,webull_token}"
mkdir -p "${EDGELOG_HOME}/ohlc" "${EDGELOG_HOME}/qqq_exec" "${EDGELOG_HOME}/logs" \
         "${EDGELOG_HOME}/webull_token"
touch "${EDGELOG_HOME}/logs/runner.log"

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
EDGELOG_NT_OHLC=${EDGELOG_HOME}/ohlc
EDGELOG_QQQ_EXEC_DIR=${EDGELOG_HOME}/qqq_exec
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
for unit in edgelog-runner.service edgelog-healthcheck.service edgelog-healthcheck.timer; do
  sed \
    -e "s#__EDGELOG_USER__#${RUN_USER}#g" \
    -e "s#__EDGELOG_REPO__#${REPO_DIR}#g" \
    -e "s#__EDGELOG_VENV__#${VENV_DIR}#g" \
    -e "s#__EDGELOG_HOME__#${EDGELOG_HOME}#g" \
    -e "s#__EDGELOG_ALLOW_UID__#${ALLOW_UID}#g" \
    "${UNIT_SRC}/${unit}" | sudo tee "/etc/systemd/system/${unit}" >/dev/null
done

sudo systemctl daemon-reload
sudo systemctl enable edgelog-runner.service edgelog-healthcheck.timer
sudo systemctl start edgelog-healthcheck.timer

echo
echo "==> install.sh done. The runner is NOT started yet. Next steps:"
echo "    1. Copy secrets from the PC (README.md step (d)):"
echo "         serviceAccount.json   -> ${REPO_DIR}/serviceAccount.json"
echo "         webull_keys.json      -> ${EDGELOG_HOME}/webull_keys.json"
echo "         webull_token/token.txt -> ${EDGELOG_HOME}/webull_token/token.txt"
echo "    2. Edit ${ENV_FILE} (set NTFY_TOPIC)."
echo "    3. Start the runner:  sudo systemctl start edgelog-runner.service"
echo "    4. Check it:          bash ${REPO_DIR}/deploy/cloud/check.sh"
