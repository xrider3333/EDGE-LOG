"""tests/test_box_deploy.py -- pure decision-function tests for tools/box_deploy.py
(the box deploy/change-control tool, WEBULL_GO_LIVE.md 1.9). Exercises the time-window
and flatness decisions, the strategy-chain text parser, the NRestarts crash-loop guard
(_n_restarts/_restarts_stable) and the boot-verification poll loop (_verify_boot) --
all with fake clocks/state/text, plus every small remote-git/config helper
(_read_remote_json, _remote_resolve_commit, _remote_git_clean, _remote_broker_mode)
with `_ssh` monkeypatched to a fake result (never a real subprocess). No test in this
module opens an ssh connection or touches the network; importing tools.box_deploy
itself performs no I/O.
"""
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import box_deploy  # noqa: E402


# ── _in_protected_window ──────────────────────────────────────────────────────────────
def test_inside_window_on_a_trading_day_is_protected():
    # Wednesday 2026-09-23, 10:00 ET -- an ordinary trading session, mid-window.
    now = dt.datetime(2026, 9, 23, 10, 0)
    assert box_deploy._in_protected_window(now) is True


def test_before_open_is_not_protected():
    now = dt.datetime(2026, 9, 23, 9, 24, 59)
    assert box_deploy._in_protected_window(now) is False


def test_at_0925_is_protected_boundary_inclusive():
    now = dt.datetime(2026, 9, 23, 9, 25, 0)
    assert box_deploy._in_protected_window(now) is True


def test_at_1605_is_not_protected_boundary_exclusive():
    now = dt.datetime(2026, 9, 23, 16, 5, 0)
    assert box_deploy._in_protected_window(now) is False


def test_just_before_1605_is_still_protected():
    now = dt.datetime(2026, 9, 23, 16, 4, 59)
    assert box_deploy._in_protected_window(now) is True


def test_weekend_is_never_protected_even_at_1000():
    # Saturday 2026-09-26.
    now = dt.datetime(2026, 9, 26, 10, 0)
    assert box_deploy._in_protected_window(now) is False


def test_market_holiday_is_never_protected():
    # Labor Day 2026-09-07 (Monday) -- a weekday but not a session.
    now = dt.datetime(2026, 9, 7, 10, 0)
    assert box_deploy._in_protected_window(now) is False


def test_half_day_afternoon_is_still_a_session_and_protected():
    # Day after Thanksgiving 2026-11-27 closes at 13:00 ET, but 10:00 ET is still a
    # normal trading session and still inside the protected window -- _in_protected_window
    # only ever checks is_session + the fixed clock window, never the half-day close time.
    now = dt.datetime(2026, 11, 27, 10, 0)
    assert box_deploy._in_protected_window(now) is True


# ── _book_is_flat ──────────────────────────────────────────────────────────────────────
def test_refuses_when_qqq_state_is_unreadable():
    # None means "couldn't read/parse it" (see _read_remote_json) -- it must never be
    # treated as an empty, flat book. This is the case the pre-fix bug got wrong:
    # _read_remote_json used to return {} on any ssh failure, and _book_is_flat({}, ...)
    # trusted that as flat.
    flat, reasons = box_deploy._book_is_flat(None, {})
    assert flat is False
    assert any("qqq_exec state.json unreadable" in r for r in reasons)


def test_refuses_when_webull_state_is_unreadable():
    flat, reasons = box_deploy._book_is_flat({}, None)
    assert flat is False
    assert any("webull_orders state.json unreadable" in r for r in reasons)


def test_refuses_when_both_states_are_unreadable():
    flat, reasons = box_deploy._book_is_flat(None, None)
    assert flat is False
    assert len(reasons) == 2


def test_flat_with_explicitly_empty_structures():
    qqq = {"legs": {}, "_broker_resend": {}, "_broker_fill_capture": {}}
    webull = {"broker_sent_positions": {}}
    flat, reasons = box_deploy._book_is_flat(qqq, webull)
    assert flat is True
    assert reasons == []


def test_not_flat_with_an_open_leg():
    qqq = {"legs": {"NOISE_382": {"side": "long", "qty": 5}}}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("open legs" in r for r in reasons)


def test_not_flat_with_nonzero_broker_position():
    webull = {"broker_sent_positions": {"NOISE_382": {"qty": 15}}}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is False
    assert any("broker_sent_positions" in r for r in reasons)


def test_flat_with_zero_qty_broker_position():
    # a leftover 0-qty entry (the go-live audit's "ORB on a different account" case)
    # must NOT block a deploy.
    webull = {"broker_sent_positions": {"ORB_R6": {"qty": 0}}}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is True
    assert reasons == []


def test_not_flat_with_pending_resend():
    qqq = {"_broker_resend": {"NOISE_382:OPEN": {"tries": 1}}}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("resend" in r for r in reasons)


def test_not_flat_with_pending_fill_capture():
    qqq = {"_broker_fill_capture": {"ORB_R6:OPEN": {"leg": "ORB_R6"}}}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("fill-capture" in r for r in reasons)


def test_not_flat_reports_every_reason_at_once():
    qqq = {"legs": {"NOISE_382": {}}, "_broker_resend": {"x": {}}}
    webull = {"broker_sent_positions": {"NOISE_382": {"qty": 3}}}
    flat, reasons = box_deploy._book_is_flat(qqq, webull)
    assert flat is False
    assert len(reasons) == 3


# ── _book_is_flat: malformed shapes must fail closed, never raise ─────────────────────
def test_malformed_broker_position_value_does_not_raise():
    # A broker_sent_positions entry that is a bare int (not {"qty": ...}) used to
    # blow up with AttributeError inside (v or {}).get("qty") -- must now be reported
    # as a reason, not crash, and the book must be treated as not flat.
    webull = {"broker_sent_positions": {"NOISE_382": 5}}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is False
    assert any("not a mapping" in r for r in reasons)


def test_malformed_legs_value_does_not_raise():
    # "legs" itself as a list (not a dict) used to blow up in sorted(legs) after the
    # truthy check, or otherwise be silently misread -- must fail closed instead.
    qqq = {"legs": ["NOISE_382"]}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("'legs' is not a mapping" in r for r in reasons)


def test_malformed_broker_sent_positions_container_does_not_raise():
    webull = {"broker_sent_positions": "not-a-dict"}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is False
    assert any("broker_sent_positions' is not a mapping" in r for r in reasons)


def test_malformed_resend_and_fillcap_do_not_raise():
    qqq = {"_broker_resend": 1, "_broker_fill_capture": [1, 2]}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("_broker_resend' is not a mapping" in r for r in reasons)
    assert any("_broker_fill_capture' is not a mapping" in r for r in reasons)


def test_well_formed_flat_state_is_unaffected_by_the_malformed_shape_guard():
    # The hardening above must not change the result for ordinary, well-formed
    # input -- re-asserts the original flat/not-flat behaviour still holds.
    qqq = {"legs": {}, "_broker_resend": {}, "_broker_fill_capture": {}}
    webull = {"broker_sent_positions": {"ORB_R6": {"qty": 0}}}
    flat, reasons = box_deploy._book_is_flat(qqq, webull)
    assert flat is True
    assert reasons == []


def test_none_states_refuse_rather_than_count_as_empty():
    # Renamed/inverted from the pre-fix version of this test, which asserted flat is
    # True -- exactly the fail-open behaviour the go-live review flagged.
    flat, reasons = box_deploy._book_is_flat(None, None)
    assert flat is False
    assert reasons != []


# ── strategy-chain parsing (pure text, no ssh) ────────────────────────────────────────
def test_parse_crown_strategy_files_from_cloud_signal_source():
    src = '''
CROWN_LEGS = {
    "ORB_R6": {"strategy": "ORB_3_6_R6.py", "timeframe": "5m"},
    "NOISE_382": {"strategy": "NOISE_1_8_CT304.py", "timeframe": "5m"},
    "ENGUQ_335": {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "timeframe": "1m"},
}
'''
    got = box_deploy.parse_crown_strategy_files(src)
    assert got == ["ENGUQ_1M_ETH_R2_1_0.py", "NOISE_1_8_CT304.py", "ORB_3_6_R6.py"]


def test_strategy_chain_follows_augur_parent():
    files = {
        "ORB_3_6_R6.py": '_AUGUR_PARENT = "ORB_3_6.py"\n',
        "ORB_3_6.py": "# base strategy, no parent\n",
    }
    got = box_deploy.strategy_chain("ORB_3_6_R6.py", lambda n: files.get(n))
    assert got == ["ORB_3_6.py", "ORB_3_6_R6.py"]


def test_strategy_chain_stops_when_a_parent_file_is_missing():
    files = {"ORB_3_6_R6.py": '_AUGUR_PARENT = "GONE.py"\n'}
    got = box_deploy.strategy_chain("ORB_3_6_R6.py", lambda n: files.get(n))
    assert got == ["ORB_3_6_R6.py"]


def test_strategy_chain_guards_against_a_cycle():
    files = {
        "A.py": '_AUGUR_PARENT = "B.py"\n',
        "B.py": '_AUGUR_PARENT = "A.py"\n',
    }
    got = box_deploy.strategy_chain("A.py", lambda n: files.get(n))
    assert got == ["A.py", "B.py"]


def test_strategy_chain_with_no_parent_returns_just_itself():
    got = box_deploy.strategy_chain("ORB_3_6.py", lambda n: "# no parent here\n")
    assert got == ["ORB_3_6.py"]


# ── _read_remote_json (ssh mocked out -- no real subprocess anywhere here) ─────────────
class _FakeResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def test_read_remote_json_returns_none_on_ssh_failure(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=1, stdout=""))
    assert box_deploy._read_remote_json("/home/ubuntu/edgelog/qqq_exec/state.json") is None


def test_read_remote_json_returns_none_on_empty_output(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout=""))
    assert box_deploy._read_remote_json("/some/missing/file.json") is None


def test_read_remote_json_returns_none_on_bad_json(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout="{not valid json"))
    assert box_deploy._read_remote_json("/some/file.json") is None


def test_read_remote_json_returns_none_when_top_level_is_not_a_dict(monkeypatch):
    # A state.json is always an object -- a list or scalar means something is very
    # wrong, and must refuse exactly like an unreadable file, not be treated as flat.
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout="[1, 2, 3]"))
    assert box_deploy._read_remote_json("/some/file.json") is None


def test_read_remote_json_returns_the_parsed_dict_on_success(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout='{"legs": {}}'))
    assert box_deploy._read_remote_json("/some/file.json") == {"legs": {}}


# ── _n_restarts / _restarts_stable (NRestarts crash-loop guard) ────────────────────────
def test_n_restarts_queries_each_service_in_its_own_ssh_call(monkeypatch):
    # Regression for the real bug: a single combined
    # `systemctl show A B -p NRestarts --value` call printed a blank line between the
    # two units' values on the box ('0', '', '0'), so zipping by position always read
    # edgelog-cloud-signal's count off the blank line. Querying one unit per call
    # sidesteps that shape entirely -- assert exactly one ssh call per service, each
    # naming only that service.
    calls = []

    def fake_ssh(cmd, **kw):
        calls.append(cmd)
        # Return a distinct, correct value per unit -- proves no cross-unit mixup.
        if "edgelog-qqq-exec" in cmd:
            return _FakeResult(returncode=0, stdout="3\n")
        if "edgelog-cloud-signal" in cmd:
            return _FakeResult(returncode=0, stdout="7\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    out = box_deploy._n_restarts()
    assert out == {"edgelog-qqq-exec": 3, "edgelog-cloud-signal": 7}
    assert len(calls) == len(box_deploy.SERVICES)


def test_n_restarts_returns_none_for_blank_output_rather_than_crashing(monkeypatch):
    # The exact real-world shape that broke the old parser: this unit's own call
    # comes back blank.
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout="\n"))
    out = box_deploy._n_restarts()
    assert out == {name: None for name in box_deploy.SERVICES}


def test_restarts_stable_true_when_all_unchanged_and_known():
    before = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 5}
    after = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 5}
    assert box_deploy._restarts_stable(before, after) is True


def test_restarts_stable_false_when_a_count_increased():
    before = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 5}
    after = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 6}
    assert box_deploy._restarts_stable(before, after) is False


def test_restarts_stable_fails_closed_on_a_none_value():
    # This is the exact inversion the go-live review flagged: None == None used to
    # read as "stable" for the service whose value couldn't be parsed. A None on
    # either side must now read as NOT stable.
    before = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": None}
    after = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": None}
    assert box_deploy._restarts_stable(before, after) is False


def test_restarts_stable_fails_closed_on_a_missing_service_key():
    before = {"edgelog-qqq-exec": 2}
    after = {"edgelog-qqq-exec": 2}
    assert box_deploy._restarts_stable(before, after) is False


# ── _verify_boot: polls the whole window, stops early only on a bad signal ────────────
class _FakeClock:
    """A controllable fake for time.time()/time.sleep() so _verify_boot's tests run
    instantly and can assert exactly how many polls happened, instead of a real
    60-second sleep loop."""
    def __init__(self):
        self.now = 0.0
        self.sleeps = 0

    def time(self):
        return self.now

    def sleep(self, secs):
        self.sleeps += 1
        self.now += secs


def test_verify_boot_polls_the_full_window_even_after_good_lines_appear(monkeypatch):
    # The pre-fix bug: the loop broke the instant it saw SERVING + (lease OR
    # reconcile_ok), so a crash later in the window was never observed. It must now
    # keep polling for the whole timeout_sec, seeing good lines on the very first
    # poll, and MUST NOT stop early because of them.
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    calls = {"n": 0}

    def fake_ssh(cmd, **kw):
        calls["n"] += 1
        return _FakeResult(returncode=0, stdout="SERVING\nlease claimed\n"
                                                  "broker reconcile OK at boot\n")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["serving"] and seen["lease"] and seen["reconcile_ok"]
    assert not seen["traceback"] and seen["reconcile_fail"] is None
    # 60s / 3s poll interval = 20 polls -- it must have used (approximately) the
    # whole window, not returned after the first poll.
    assert calls["n"] >= 19


def test_verify_boot_stops_early_on_traceback(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    calls = {"n": 0}

    def fake_ssh(cmd, **kw):
        calls["n"] += 1
        return _FakeResult(returncode=0, stdout="SERVING\nTraceback (most recent call last)\n")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["traceback"] is True
    assert calls["n"] == 1  # stopped on the very first poll, not the whole window


def test_verify_boot_stops_early_on_reconcile_mismatch(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    calls = {"n": 0}

    def fake_ssh(cmd, **kw):
        calls["n"] += 1
        return _FakeResult(returncode=0,
                           stdout="SERVING\nlease claimed\n"
                                  "BROKER RECONCILE MISMATCH at boot -- halted\n")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["reconcile_fail"] == "BROKER RECONCILE MISMATCH at boot"
    assert calls["n"] == 1


def test_verify_boot_never_saw_reconcile_ok_when_it_never_appeared(monkeypatch):
    # Simulates OFF mode: SERVING and lease claimed show up, but no reconcile line
    # ever appears (the adapter never logs one -- see _reconcile_broker_at_boot).
    # _verify_boot itself makes no OFF-mode decision -- it just reports what it saw.
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout="SERVING\nlease claimed\n"))
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["serving"] and seen["lease"]
    assert seen["reconcile_ok"] is False
    assert seen["reconcile_fail"] is None
    assert not seen["traceback"]


# ── _remote_resolve_commit / _remote_git_clean / _remote_broker_mode ───────────────────
def test_remote_resolve_commit_returns_the_full_sha(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout="abc123def456\n"))
    assert box_deploy._remote_resolve_commit("main") == "abc123def456"


def test_remote_resolve_commit_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=128, stdout=""))
    assert box_deploy._remote_resolve_commit("not-a-real-ref") is None


def test_remote_git_clean_true_on_empty_status(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout=""))
    assert box_deploy._remote_git_clean() is True


def test_remote_git_clean_false_when_status_reports_changes(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout=" M api/qqq_exec.py\n"))
    assert box_deploy._remote_git_clean() is False


def test_remote_git_clean_false_when_ssh_itself_fails(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=255, stdout=""))
    assert box_deploy._remote_git_clean() is False


def test_remote_broker_mode_defaults_to_off_when_config_missing(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout=""))
    assert box_deploy._remote_broker_mode() == "OFF"


def test_remote_broker_mode_reads_paper(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout='{"mode": "PAPER"}'))
    assert box_deploy._remote_broker_mode() == "PAPER"


def test_remote_broker_mode_defaults_to_off_on_malformed_config(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout="[1, 2]"))
    assert box_deploy._remote_broker_mode() == "OFF"


# ── _UNIT_OR_DEPS_RE (deploy/cloud unit-template/deps-change warning) ──────────────────
def test_unit_or_deps_pattern_matches_only_the_expected_files():
    candidates = [
        "deploy/cloud/edgelog-qqq-exec.service",
        "deploy/cloud/edgelog-keel-state.timer",
        "deploy/cloud/edgelog-keel-state.path",
        "deploy/cloud/requirements-cloud.txt",
        "deploy/cloud/edgelog.logrotate",
        "deploy/cloud/README.md",
        "deploy/cloud/install.sh",
        "api/qqq_exec.py",
        "requirements-cloud.txt",  # not under deploy/cloud/ -- must not match
    ]
    hits = [n for n in candidates if box_deploy._UNIT_OR_DEPS_RE.match(n)]
    assert hits == [
        "deploy/cloud/edgelog-qqq-exec.service",
        "deploy/cloud/edgelog-keel-state.timer",
        "deploy/cloud/edgelog-keel-state.path",
        "deploy/cloud/requirements-cloud.txt",
        "deploy/cloud/edgelog.logrotate",
    ]
