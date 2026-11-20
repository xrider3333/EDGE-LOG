"""HOST PIN (owner 11-20, MANAGER GO): job host field, EDGELOG_HOST_TAG, 6 h fallback."""
import argparse
import datetime

from api import runner as R
from tools.job_host import add_host_args, apply_host


def test_no_host_field_is_claimed_exactly_as_today():
    for tag in (None, "desktop", "razer"):
        assert R.host_pin_verdict({"strategy": "X"}, tag, 0.0, None) == (True, False, "")
        assert R.host_pin_verdict({"host": ""}, tag, 99.0, False) == (True, False, "")


def test_matching_tag_claims_at_once():
    assert R.host_pin_verdict({"host": "Desktop"}, "desktop", 0.0, None) == (True, False, "")


def test_other_runner_leaves_it_before_the_fallback_age():
    ok, fb, why = R.host_pin_verdict({"host": "desktop"}, None, 5.9, None, fallback_h=6)
    assert (ok, fb) == (False, False) and "pinned" in why
    ok, fb, _ = R.host_pin_verdict({"host": "desktop"}, "razer", None, None, fallback_h=6)
    assert (ok, fb) == (False, False)          # unknown age never falls back


def test_past_the_age_it_asks_for_liveness_then_decides():
    j = {"host": "desktop"}
    assert R.host_pin_verdict(j, None, 6.5, None, fallback_h=6)[2] == "needs-liveness"
    assert R.host_pin_verdict(j, None, 6.5, True, fallback_h=6)[:2] == (False, False)
    ok, fb, why = R.host_pin_verdict(j, None, 6.5, False, fallback_h=6)
    assert (ok, fb) == (True, True) and "falling back" in why


class _Snap:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


class _Col:
    def __init__(self, docs, boom=False):
        self.docs, self.boom = docs, boom

    def where(self, filter=None):
        return self

    def stream(self):
        if self.boom:
            raise RuntimeError("quota")
        return [_Snap(d) for d in self.docs]


def test_liveness_reads_a_fresh_heartbeat_of_that_tag_only():
    now = datetime.datetime.now(datetime.timezone.utc)
    fresh, stale = now - datetime.timedelta(minutes=1), now - datetime.timedelta(minutes=30)
    assert R._pinned_host_alive(_Col([{"claimHostTag": "desktop", "heartbeat_at": fresh}]), "desktop")
    assert not R._pinned_host_alive(_Col([{"claimHostTag": "desktop", "heartbeat_at": stale}]), "desktop")
    assert not R._pinned_host_alive(_Col([{"claimHostTag": None, "heartbeat_at": fresh}]), "desktop")
    assert not R._pinned_host_alive(_Col([]), "desktop")


def test_a_failed_liveness_read_never_falls_back():
    assert R._pinned_host_alive(_Col([], boom=True), "desktop") is True


def test_queue_helper_flags():
    ap = add_host_args(argparse.ArgumentParser())
    assert apply_host({"n_trials": 900}, ap.parse_args([])) == {"n_trials": 900}
    assert apply_host({}, ap.parse_args(["--on-desktop"])) == {"host": "desktop"}
    assert apply_host({}, ap.parse_args(["--host", "Lab"])) == {"host": "lab"}
    assert apply_host({}, host="desktop") == {"host": "desktop"}
