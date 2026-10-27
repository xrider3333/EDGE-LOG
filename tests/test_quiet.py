"""QUIET MODE (OWNER 10-27, MANAGER #133) - tools/quiet.py, its runner claim/refresh gate and the
wt.py ship wait. Fakes only: no Firestore, no real C:\\EdgeLog files (conftest points
EDGELOG_QUIET_FILE / EDGELOG_QUIET_STATE at tmp paths)."""
import ast
import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
for p in (ROOT, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

import quiet as Q  # noqa: E402

UTC = dt.timezone.utc


def mst(y, m, d, hh, mm):
    """An MST wall time as aware UTC (MST = UTC-7, no DST)."""
    return dt.datetime(y, m, d, hh, mm, tzinfo=UTC) + dt.timedelta(hours=7)


TUE = (2026, 10, 27)          # a CME trading day
SAT = (2026, 10, 31)
THANKSGIVING = (2026, 11, 26)  # holiday SHORT session - still a trading day
CHRISTMAS = (2026, 12, 25)     # closed


# ── the truth table ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("hhmm,want", [((6, 24), False), ((6, 25), True), ((8, 59), True),
                                       ((9, 0), False)])
def test_auto_window_edges(hhmm, want):
    q, why, until = Q.is_quiet(mst(*TUE, *hhmm), None, False)
    assert q is want
    if want:
        assert why == Q.WHY_AUTO and until == "2026-10-27T16:00:00Z"
    else:
        assert why is None and until is None


@pytest.mark.parametrize("day,want", [(SAT, False), (CHRISTMAS, False), (THANKSGIVING, True)])
def test_auto_window_only_on_trading_days(day, want):
    assert Q.is_quiet(mst(*day, 7, 0), None, False)[0] is want


def test_button_on_off_and_until():
    now = mst(*TUE, 12, 0)
    assert Q.is_quiet(now, {"on": True, "until": None}, False) == (True, "button", None)
    later = "2026-10-27T20:00:00Z"
    assert Q.is_quiet(now, {"on": True, "until": later}, False) == (True, "button", later)
    assert Q.is_quiet(now, {"on": True, "until": "2026-10-27T18:00:00Z"}, False)[0] is False
    assert Q.is_quiet(now, {"on": False}, False)[0] is False
    # button wins the 'why' even inside the auto window
    assert Q.is_quiet(mst(*TUE, 7, 0), {"on": True}, False)[1] == "button"


def test_auto_false_skips_today_only():
    now = mst(*TUE, 7, 0)
    today = {"on": False, "auto": False, "set_at": "2026-10-27T13:00:00Z"}     # 06:00 MST today
    yesterday = {"on": False, "auto": False, "set_at": "2026-10-26T13:00:00Z"}
    assert Q.is_quiet(now, today, False)[0] is False
    assert Q.is_quiet(now, yesterday, False) == (True, Q.WHY_AUTO, "2026-10-27T16:00:00Z")
    # 23:30 MST on the 26th is 06:30 UTC on the 27th: the MST date decides, not the UTC one
    late = {"auto": False, "set_at": "2026-10-27T06:30:00Z"}
    assert Q.is_quiet(now, late, False)[0] is True


def test_local_file():
    now = mst(*SAT, 12, 0)
    assert Q.is_quiet(now, None, True) == (True, "local flag", None)
    assert Q.is_quiet(now, None, True, "2026-10-31T20:00:00Z")[0] is True
    assert Q.is_quiet(now, None, True, "2026-10-31T20:00:00Z")[2] == "2026-10-31T20:00:00Z"
    assert Q.is_quiet(now, None, True, "2026-10-31T10:00:00Z")[0] is False
    assert Q.is_quiet(now, None, False)[0] is False


def test_cli_on_off_writes_only_the_local_file(capsys):
    assert Q.main(["on"]) == 0
    assert os.path.exists(Q.quiet_file())
    assert Q.current_state(use_cache=False)["quiet"] is True
    Q.main(["off"])
    assert not os.path.exists(Q.quiet_file())


def test_current_state_uses_fresh_runner_file_and_falls_back_when_stale(monkeypatch):
    now = mst(*TUE, 7, 0)                                    # inside the auto window
    Q.write_state({"quiet": False, "why": None, "until": None, "at": Q._iso(now)})
    # fresh runner says not quiet (e.g. auto=false today): honoured
    assert Q.current_state(now=now)["quiet"] is False
    # stale (runner down): the auto window is computed locally
    st = Q.current_state(now=now + dt.timedelta(minutes=10))
    assert st["quiet"] is True and st["why"] == Q.WHY_AUTO and st["source"] == "local"
    # a local flag made since still counts over a fresh 'not quiet'
    os.makedirs(os.path.dirname(Q.quiet_file()), exist_ok=True)
    open(Q.quiet_file(), "w").close()
    assert Q.current_state(now=now)["why"] == Q.WHY_LOCAL


# ── the monitor ─────────────────────────────────────────────────────────────────────────────
class _Doc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return _Doc(self.db, self.path + "/" + name)

    def document(self, name):
        return _Doc(self.db, self.path + "/" + name)

    def get(self):
        self.db.reads.append(self.path)
        if self.db.fail:
            raise RuntimeError("ServiceUnavailable: 503")
        data = self.db.docs.get(self.path)

        class _S:
            exists = data is not None

            def to_dict(s):
                return dict(data or {})
        return _S()

    def set(self, doc):
        self.db.writes.append((self.path, dict(doc)))


class _FakeDb:
    def __init__(self):
        self.docs, self.reads, self.writes, self.fail = {}, [], [], False

    def collection(self, name):
        return _Doc(self, name)


class _Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _mon(start, db=None, **k):
    clock = _Clock(start.timestamp())
    logs = []
    m = Q.QuietMonitor(db=db if db is not None else _FakeDb(), uids=["uid1"],
                       log=logs.append, clock=clock, **k)
    return m, clock, logs


BUTTON = "users/uid1/control/quiet"
STATUS = "users/uid1/control/quiet_status"


def test_status_doc_throttle_and_reads():
    m, clock, _ = _mon(mst(*TUE, 12, 0))
    m.tick()
    assert len(m.db.reads) == 1 and len(m.db.writes) == 1
    assert m.db.writes[0][0] == STATUS
    for _ in range(5):                       # 5 ticks inside the minute: no read, no write
        clock.t += 10
        m.tick()
    assert len(m.db.reads) == 1 and len(m.db.writes) == 1
    clock.t += 15                            # past 60 s: one read, one write
    m.tick()
    assert len(m.db.reads) == 2 and len(m.db.writes) == 2
    doc = m.db.writes[-1][1]
    assert set(doc) == {"quiet", "why", "until", "since", "held_jobs", "deferred",
                        "running_jobs", "runner_seen_at"}
    # 1,440 reads a day per uid at most
    assert 86400 / m.POLL_SEC <= 1500


def test_state_change_writes_status_immediately():
    m, clock, logs = _mon(mst(*TUE, 12, 0))
    m.tick()
    m.db.docs[BUTTON] = {"on": True}
    clock.t += 60
    m.tick()
    assert m.state[0] and m.db.writes[-1][1]["quiet"] is True and m.db.writes[-1][1]["why"] == "button"
    with open(Q.state_file()) as f:
        assert json.load(f)["quiet"] is True
    assert any("QUIET ON" in s for s in logs)


def test_fail_open_keeps_last_button_value():
    m, clock, logs = _mon(mst(*TUE, 12, 0))
    m.db.docs[BUTTON] = {"on": True}
    m.tick()
    assert m.quiet()
    m.db.fail = True
    m.db.docs[BUTTON] = {"on": False}
    clock.t += 61
    m.tick()
    assert m.quiet(), "a read error keeps the last button value"
    assert any("read failed" in s for s in logs)


def test_fail_open_auto_window_still_applies_with_no_reads():
    db = _FakeDb()
    db.fail = True
    m, _, _ = _mon(mst(*TUE, 7, 0), db=db)
    assert m.quiet() and m.state[1] == Q.WHY_AUTO


def test_refresh_deferred_then_runs_once():
    m, clock, logs = _mon(mst(*TUE, 8, 58))
    ran = []
    assert m.defer("master refresh", lambda: ran.append(1)) is True
    assert m.defer("master refresh", lambda: ran.append(1)) is True     # deduped
    assert sum("master refresh deferred" in s for s in logs) == 1
    clock.t += 60
    m.tick()
    assert ran == []                         # 08:59 still quiet
    clock.t += 60                            # 09:00
    m.tick()
    assert ran == [1]
    clock.t += 60
    m.tick()
    assert ran == [1], "runs once"
    assert m.defer("master refresh", lambda: ran.append(2)) is False    # not quiet: run now


def test_hold_logs_once_per_state_change_and_lists_jobs():
    m, clock, logs = _mon(mst(*TUE, 7, 0))
    assert m.hold("A") and m.hold("B") and m.hold("A")
    assert m.held == ["A", "B"]
    assert sum("holding" in s for s in logs) == 1
    clock.t = mst(*TUE, 9, 0).timestamp()
    m.tick()
    assert not m.hold("A") and m.held == []


def test_worker_monitor_never_touches_firestore():
    m = Q.QuietMonitor(db=None, uids=["uid1"], log=lambda *_: None,
                       clock=_Clock(mst(*TUE, 7, 0).timestamp()))
    assert m.quiet() and m.state[1] == Q.WHY_AUTO
    assert not os.path.exists(Q.state_file()), "a worker never writes the state file"


# ── the runner claim gate ───────────────────────────────────────────────────────────────────
def _runner():
    pytest.importorskip("google.cloud.firestore_v1.base_query",
                        reason="google-cloud-firestore is not part of the CI dev deps")
    pytest.importorskip("firebase_admin", reason="firebase-admin is not part of the CI dev deps")
    from api import runner as R
    return R


class _Ref:
    def __init__(self):
        self.updates = []
        self.path = "users/uid1/backtests/job1"

    def update(self, patch, option=None):
        self.updates.append(dict(patch))


class _Snap:
    def __init__(self, doc, sid="job1"):
        self.reference, self._doc, self.id = _Ref(), doc, sid
        self.create_time = self.update_time = None

    def to_dict(self):
        return dict(self._doc)


class _QDb:
    def __init__(self, snaps):
        self.snaps = snaps

    def collection(self, _n):
        return self

    def document(self, _n):
        return self

    def where(self, filter=None):
        return self

    def limit(self, _n):
        return self

    def stream(self):
        return iter([s for s in self.snaps if s._doc.get("status") == "queued"])

    def write_option(self, **_k):
        return object()


def _queue(R, snaps, monitor):
    q = R.FirestoreQueue.__new__(R.FirestoreQueue)
    q.col, q.allow = "backtests", {"uid1"}
    q.db = _QDb(snaps)
    q.quiet = monitor
    return q


def test_runner_holds_claims_while_quiet_and_releases_after(monkeypatch):
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)
    m, clock, _ = _mon(mst(*TUE, 7, 0))
    snap = _Snap({"status": "queued", "type": "backtest"})
    q = _queue(R, [snap], m)
    ran = []
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: (ran.append(m.running.copy()),
                                              {"status": "error", "error": "x",
                                               "finishedAt": 1.0})[1])
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    assert q.run_once(log=lambda *_: None) == 0
    assert snap.reference.updates == [], "nothing written: the job stays queued"
    assert m.held == ["job1"] and ran == []
    clock.t = mst(*TUE, 9, 0).timestamp()
    m.tick()
    assert q.run_once(log=lambda *_: None) == 1
    assert snap.reference.updates[0]["status"] == "running"
    assert ran == [{"job1"}], "listed as running while it runs"
    assert m.running == set()


def test_stop_and_pause_are_not_gated(monkeypatch):
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)
    m, _, _ = _mon(mst(*TUE, 7, 0))
    stop = _Snap({"status": "queued", "control": "stop"}, "S")
    pause = _Snap({"status": "queued", "control": "pause"}, "P")
    q = _queue(R, [stop, pause], m)
    q.run_once(log=lambda *_: None)
    assert stop.reference.updates[0]["status"] == "cancelled"
    assert m.held == [], "a paused job is not counted as held"


def test_running_job_untouched_while_quiet(monkeypatch):
    """A job that turns quiet mid-run finishes: the gate is read only before a claim."""
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)
    m, clock, _ = _mon(mst(*TUE, 6, 24))
    snap = _Snap({"status": "queued", "type": "backtest"})
    q = _queue(R, [snap], m)

    def job(j, cb=None):
        clock.t = mst(*TUE, 6, 30).timestamp()
        m.tick()
        assert m.quiet()
        return {"status": "done", "finishedAt": 1.0}
    monkeypatch.setattr(R, "process_job", job)
    saved = []
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: saved.append(patch))
    monkeypatch.setattr(q, "_persist_run", lambda *a, **k: None, raising=False)
    q.run_once(log=lambda *_: None)
    assert saved and saved[0]["status"] == "done"


def _quiet_refs():
    """(function name, line) of every reference to the quiet gate in api/runner.py."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    out = []

    def walk(node, fn):
        for ch in ast.iter_child_nodes(node):
            name = fn
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = ch.name
            if isinstance(ch, ast.Name) and ch.id in ("_quiet", "_qm", "_qmod"):
                out.append((fn, ch.lineno))
            if isinstance(ch, ast.Attribute) and ch.attr == "quiet":
                out.append((fn, ch.lineno))
            walk(ch, name)
    walk(tree, None)
    return out


def test_paper_gate_bridge_paths_never_consult_quiet():
    allowed = {"run_once", "_refresh_async", "_boot_chores", "main", "_start_quiet", "__init__"}
    refs = _quiet_refs()
    assert refs, "the gate exists"
    bad = [r for r in refs if r[0] not in allowed]
    assert not bad, bad
    # in main() the gate is only set up - never read around the paper/QQQ/gate/bridge hooks
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    for hook in ("_paper.maybe_run_eod", "_qqq_paper.maybe_run", "_bridge_watchdog_thread",
                 "qqq_exec_thread", "run_commands()", "sweep_orphans(log=print, tag=\"sweep\")"):
        i = src.index(hook)
        assert "_quiet" not in src[i - 400:i + 200], hook
    for mod in ("paper.py", "qqq_paper_publish.py", "qqq_exec.py", "gate_live.py", "nt_bridge.py"):
        p = os.path.join(ROOT, "api", mod)
        if os.path.exists(p):
            assert "tools.quiet" not in open(p, encoding="utf-8").read(), mod


# ── wt.py ship ──────────────────────────────────────────────────────────────────────────────
def test_wait_while_quiet_polls_then_continues():
    states = iter([{"quiet": True, "why": "auto 06:25-09:00 MST", "until": "U"}] * 3
                  + [{"quiet": True, "why": "button", "until": None},
                     {"quiet": False}])
    logs, sleeps = [], []
    n = Q.wait_while_quiet("the engine tier", log=logs.append, sleep=sleeps.append,
                           state_fn=lambda: next(states), env={})
    assert n == 4 and sleeps == [60.0] * 4
    assert [s for s in logs if s.startswith("QUIET: waiting")] == [
        "QUIET: waiting before the engine tier (auto 06:25-09:00 MST, until U)",
        "QUIET: waiting before the engine tier (button, until turned off)"]


def test_ship_escape_env():
    called = []
    assert Q.wait_while_quiet("x", sleep=called.append, env={"EDGELOG_SHIP_IGNORE_QUIET": "1"},
                              state_fn=lambda: {"quiet": True}) == 0
    assert called == []


def test_wt_waits_before_prelock_gates_but_never_under_the_lock(monkeypatch, tmp_path):
    import wt
    waits = []
    monkeypatch.setattr(wt, "wait_if_quiet", lambda label: waits.append(label))
    monkeypatch.setattr(wt, "hold_gate_slot", lambda *a, **k: None)
    monkeypatch.setattr(wt, "run_gate", lambda *a: ("PASS", 0))
    monkeypatch.setattr(wt, "tree_moved", lambda *a: None)
    monkeypatch.setattr(wt, "save_stamp", lambda *a: None)
    g = [x for x in wt.GATES if x.key == "home"][0]
    stamp = {"key": "k", "gates": {}}
    wt.run_plan(str(tmp_path), str(tmp_path), [(g, None)], stamp, "s", "T", "B", "pre-lock")
    assert waits == [g.label]
    wt.run_plan(str(tmp_path), str(tmp_path), [(g, None)], stamp, "s", "T", "B", "locked")
    assert waits == [g.label], "never waits while holding the push lock"


def test_wt_waits_before_heavy_tests_only(monkeypatch, tmp_path):
    import wt
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "hook_tests.py").write_text("")
    waits = []
    monkeypatch.setattr(wt, "wait_if_quiet", lambda label: waits.append(label))
    monkeypatch.setattr(wt, "hold_gate_slot", lambda *a, **k: None)

    class _R:
        returncode = 0
    monkeypatch.setattr(wt.subprocess, "run", lambda *a, **k: _R())
    monkeypatch.setattr(wt, "tests_plan", lambda w: {"run_files": 3, "timed": True, "est_secs": 1})
    wt.prelock_tests(str(tmp_path))
    assert waits == []
    monkeypatch.setattr(wt, "tests_plan", lambda w: {"run_files": 3, "timed": True,
                                                     "est_secs": 10 ** 6})
    wt.prelock_tests(str(tmp_path))
    assert waits == ["the heavy pre-lock test tier"]


def test_wt_wait_if_quiet_honours_the_escape(monkeypatch):
    import wt
    monkeypatch.setenv("EDGELOG_SHIP_IGNORE_QUIET", "1")
    monkeypatch.setattr(Q, "current_state", lambda **k: pytest.fail("not consulted"))
    assert wt.wait_if_quiet("x") == 0
