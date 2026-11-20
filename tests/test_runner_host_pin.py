"""HOST PIN (owner 11-20, MANAGER GO): job host field, EDGELOG_HOST_TAG, 6 h fallback."""
import argparse
import datetime
import time

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
    assert R._pinned_host_alive_read(_Col([{"claimHostTag": "desktop", "heartbeat_at": fresh}]), "desktop")
    assert not R._pinned_host_alive_read(_Col([{"claimHostTag": "desktop", "heartbeat_at": stale}]), "desktop")
    assert not R._pinned_host_alive_read(_Col([{"claimHostTag": None, "heartbeat_at": fresh}]), "desktop")
    assert not R._pinned_host_alive_read(_Col([]), "desktop")


def test_a_failed_liveness_read_never_falls_back():
    assert R._pinned_host_alive_read(_Col([], boom=True), "desktop") is True


def test_queue_helper_flags():
    ap = add_host_args(argparse.ArgumentParser())
    assert apply_host({"n_trials": 900}, ap.parse_args([])) == {"n_trials": 900}
    j = apply_host({}, ap.parse_args(["--on-desktop"]))
    assert j["host"] == "desktop" and abs(j["host_pinned_at"] - time.time()) < 60
    assert apply_host({}, ap.parse_args(["--host", "Lab"]))["host"] == "lab"
    assert apply_host({}, host="desktop")["host"] == "desktop"


def test_liveness_is_cached_per_tag_for_five_minutes():
    R._ALIVE_CACHE.clear()
    calls = []

    class _Counting(_Col):
        def stream(self):
            calls.append(1)
            return []
    col, t = _Counting([]), [1000.0]
    for _ in range(50):                                   # 50 polls inside 5 min = ONE read
        assert R._pinned_host_alive(col, "desktop", now_fn=lambda: t[0]) is False
        t[0] += 5
    assert len(calls) == 1
    t[0] += R.ALIVE_CACHE_SEC
    R._pinned_host_alive(col, "desktop", now_fn=lambda: t[0])
    assert len(calls) == 2
    R._pinned_host_alive(col, "lab", now_fn=lambda: t[0])  # another tag has its own entry
    assert len(calls) == 3
    R._ALIVE_CACHE.clear()


# ── book jobs through the pre-claim data/code guard (MANAGER 11-20) ──
def _fake(tmp_path, have_panel=True, have_master=True, on_disk=True):
    f = tmp_path / "S23.py"
    f.write_text("x")
    panel = tmp_path / "panel.npz"
    if have_panel:
        panel.write_text("p")
    return dict(
        strategy_path=lambda name: str(tmp_path / name),
        strategy_panels=lambda sp: [str(panel)] if sp.endswith("S23.py") else [],
        find_master=lambda *a: ({"id": 1, "filename": "m.csv"} if have_master else None),
        master_on_disk=lambda m: on_disk)


def test_book_all_legs_present_is_runnable(tmp_path):
    legs = [{"strategy": "S23.py", "instrument": "QQQ"}, {"strategy": "S23.py", "instrument": "NQ"}]
    assert R.book_legs_lacking(legs, **_fake(tmp_path)) == []


def test_book_leg_without_its_panel_is_named(tmp_path):
    out = R.book_legs_lacking([{"strategy": "S23.py", "instrument": "QQQ"}], **_fake(tmp_path, have_panel=False))
    assert len(out) == 1 and "leg 1 (S23.py)" in out[0] and "panel" in out[0]


def test_book_leg_missing_file_or_master(tmp_path):
    kw = _fake(tmp_path)
    assert "not on disk" in R.book_legs_lacking([{"strategy": "NOPE.py"}], **kw)[0]
    assert "no master" in R.book_legs_lacking([{"strategy": "S23.py", "instrument": "RTY"}],
                                              **_fake(tmp_path, have_master=False))[0]
    assert "not on this disk" in R.book_legs_lacking([{"strategy": "S23.py", "instrument": "RTY"}],
                                                     **_fake(tmp_path, on_disk=False))[0]


class _Ref:
    def __init__(self):
        self.updates = []

    def update(self, d, option=None):
        self.updates.append(d)


class _QSnap:
    def __init__(self, age_h):
        self.create_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_h)
        self.update_time = None
        self.id = "B1"


def test_stuck_book_alert_once_after_the_age():
    pushed = []
    ref = _Ref()
    assert not R._stuck_alert(ref, _QSnap(1), {}, ["leg 1 (S23.py): panel"], push=lambda m, **k: pushed.append(m))
    assert R._stuck_alert(ref, _QSnap(7), {}, ["leg 1 (S23.py): panel"], push=lambda m, **k: pushed.append(m))
    assert len(pushed) == 1 and "legStuckAlertAt" in ref.updates[0]
    assert not R._stuck_alert(ref, _QSnap(9), {"legStuckAlertAt": "x"}, ["l"], push=lambda m, **k: pushed.append(m))
    assert len(pushed) == 1


def test_leg_check_note_rides_in_the_claim_write_only():
    assert R.claim_extra_fields() == {}
    assert R.claim_extra_fields("", "skipped on x: E: y") == {"legCheck": "skipped on x: E: y"}
    assert R.claim_extra_fields("fb", "n") == {"hostFallback": "fb", "legCheck": "n"}
    # no other write of legCheck anywhere in the runner (a pre-claim write breaks the precondition)
    import inspect
    src = inspect.getsource(R)
    assert src.count('"legCheck"') == 1 and "ref.update({\"legCheck\"" not in src
