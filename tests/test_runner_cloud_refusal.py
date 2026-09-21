"""The job runner refuses to run on the cloud box (2026-09-21).

A runner nobody meant to start on the Oracle box called itself the primary and, for 14
hours, published the live gate as down over the PC's healthy status (the web header's
GATE DOWN chip), ran the 9am NinjaTrader preflight from a machine with no NinjaTrader,
and claimed re-validate jobs it had no market data for. See api/runner.py,
_cloud_runner_refusal.
"""
import os

import pytest

from api import runner

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_pc_carries_no_host_role_and_may_run():
    assert runner._cloud_runner_refusal({}) is None


@pytest.mark.parametrize("role", ["", "  ", "pc", "PC"])
def test_other_roles_may_run(role):
    assert runner._cloud_runner_refusal({"EDGELOG_HOST_ROLE": role}) is None


@pytest.mark.parametrize("role", ["cloud", "CLOUD", " cloud "])
def test_the_cloud_box_is_refused(role):
    msg = runner._cloud_runner_refusal({"EDGELOG_HOST_ROLE": role})
    assert msg and "cloud box" in msg


def test_main_stops_before_it_touches_firestore(monkeypatch):
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")

    def _must_not_build(*a, **k):
        raise AssertionError("the queue must never be built on the cloud box")

    monkeypatch.setattr(runner, "FirestoreQueue", _must_not_build)
    with pytest.raises(SystemExit) as ei:
        runner.main(["--firestore", "--cred", "serviceAccount.json",
                     "--allow-uid", "someone", "--watch"])
    assert ei.value.code == runner.CLOUD_REFUSAL_EXIT == 78


def test_the_unit_treats_the_refusal_as_a_clean_stop():
    # Restart=always would otherwise retry the refusal every 15 seconds forever.
    with open(os.path.join(ROOT, "deploy", "cloud", "edgelog-runner.service"),
              encoding="utf-8") as fh:
        unit = fh.read()
    code = str(runner.CLOUD_REFUSAL_EXIT)
    assert "SuccessExitStatus=" + code in unit
    assert "RestartPreventExitStatus=" + code in unit


def test_the_healthcheck_never_starts_a_stopped_runner():
    with open(os.path.join(ROOT, "deploy", "cloud", "healthcheck.sh"),
              encoding="utf-8") as fh:
        sh = fh.read()
    assert "systemctl is-active --quiet edgelog-runner.service" in sh
    assert "systemctl restart edgelog-runner" not in sh
