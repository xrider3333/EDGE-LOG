"""Guard rails between the test suite and the owner's LIVE trading setup.

THE LEAK (2026-09-14). Since ae9842d, api/qqq_exec.py's tick() calls
_run_broker_housekeeping() -> _get_broker_adapter() on every tick, and that module singleton is
built from api/webull_orders.py's DEFAULT_* paths -- on the owner's PC the LIVE
C:\\EdgeLog\\webull_orders\\config.json and state.json. So a test that ticked without stubbing the
adapter loaded the live order-adapter state, reset its daily_pnl and saved it back over the live
file, racing the live adapter's own saves (the pre-push engine gate did it at 16:18 ET, another
session's run at 14:04 ET). Once the live config was in PAPER mode, the same test also built a
real Webull client from the owner's paper keys and called the paper account from inside pytest.
tools/qqq_exec_smoke.py was isolated the same way in 550055c; this does it for every test.

1. _isolate_broker_adapter (autouse) starts every test with that singleton already set to an
   OFF-mode OrderAdapter whose state / kill / arm / key / token paths are in a private temp dir,
   and with qqq_exec.BROKER_ORDERS_CSV pointed there too. A test that monkeypatches
   _get_broker_adapter itself bypasses the singleton, exactly as before. webull_orders.DEFAULT_*
   are deliberately left alone: tests/test_qqq_exec_edgelog_home.py asserts them.
2. live_system_guard (autouse) + an audit hook BLOCK any write-type file operation under the real
   EDGELOG_HOME and any connection to a Webull host, and fail the test that attempted one -- even
   when the code under test swallows the error, as OrderAdapter._save_state and reconcile() do.
   The home is resolved once, at import, before any test can touch the environment. A blocked
   attempt outside any test (collection, module-scoped teardown) fails the session. Not covered:
   subprocesses a test spawns, and I/O done in C (sqlite, compiled extensions).
3. On Windows the same hook blocks os.kill(pid, 0). That is POSIX's "is this pid alive?" probe, but
   on Windows signal 0 is CTRL_C_EVENT: a Ctrl+C to EVERY process on the console. A test that
   faked os.name = "posix" in front of api/qqq_exec.py's _pid_alive sent one (2026-09-14): pytest
   died of KeyboardInterrupt a few dozen tests later, and the PowerShell that launched it died too.
   Run from Git Bash, as the pre-push gate runs it, pytest survives that, which is why nothing
   noticed. Blocked, it fails the test that tried, in every shell.
4. _isolate_qqq_stream (autouse, 2026-09-23) covers the SAME class of leak for
   api/qqq_exec.py's live Webull price stream (item 3, "LIVE POSITIONS + ACCOUNT
   EQUITY"): qqq_exec_thread can start api.webull_stream.WebullBarStreamer -- a real
   MQTT session against the owner's Webull key -- on a background thread once it holds
   the serving lease (_start_qqq_stream). An un-isolated test that drives
   qqq_exec_thread for real (tests/test_qqq_exec_lease.py does, more than once) would
   build that streamer from the owner's real webull_keys.json and dial out exactly
   like the ORDER adapter leak above. Swapped for an inert stub (_InertStreamer) that
   records start()/stop() calls and touches neither a thread nor the network; a test
   that wants the real wiring logic (guarded-thread, exception-containment, standby-
   never-streams) overrides qqq_exec._webull_stream_factory with its OWN fake via
   monkeypatch, never the genuine class. Belt-and-suspenders alongside guard #2 above,
   which independently blocks any socket connect to a "webull"-named host regardless.
5. _isolate_inflight_send (autouse, 2026-09-26, "alerts in book" review) resets
   qqq_exec._inflight_send / ._send_stall_logged before and after every test.
   _place_stock_order_with_timeout tracks its shared single worker's current future at
   MODULE level (major review findings #1/#2 -- see that function and
   _run_broker_housekeeping) so a still-running send is visible across the whole
   process, not just within one call; a test that exercises a real hang (a fake
   place_stock_order that blocks) and does not itself resolve the future before
   returning would otherwise leave every LATER test believing a send is still in
   flight, silently turning their own sends into instant BLOCKED-not-sent records.
"""
import errno
import itertools
import os
import sys

import pytest


# ── 2. the live-system guard ──────────────────────────────────────────────────────────────
def _default_edgelog_home():
    # the same rule as api/qqq_exec.py and api/webull_orders.py
    return r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog"


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


REAL_EDGELOG_HOME = _norm(os.environ.get("EDGELOG_HOME") or _default_edgelog_home())
_PROTECTED = sorted({REAL_EDGELOG_HOME, os.path.normcase(os.path.realpath(REAL_EDGELOG_HOME))})

# "open" is raised by builtins.open / io.open AND os.open; its flags argument says whether the
# file is opened for writing either way (the mode argument is None for os.open).
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
# every other audit event that changes the file system -> positions of its path arguments
# (os.replace raises os.rename; for link/symlink only the new link's path is written)
_PATH_EVENTS = {"os.rename": (0, 1), "os.link": (1,), "os.symlink": (1,), "os.remove": (0,),
                "os.rmdir": (0,), "os.mkdir": (0,), "os.truncate": (0,), "os.utime": (0,),
                "os.chmod": (0,), "shutil.rmtree": (0,)}

_BLOCKED = []            # {"test": nodeid or None, "event", "target", "claimed"}
_current_test = [None]


def _is_live(path):
    if path is None or isinstance(path, int):
        return False
    try:
        p = _norm(os.fsdecode(path))
    except (TypeError, ValueError):
        return False
    return any(p == root or p.startswith(root.rstrip("\\/") + os.sep) for root in _PROTECTED)


def _live_target(event, args):
    """(target, what it would do) when this audit event reaches the live setup, else None."""
    if event == "open":
        if len(args) < 3 or not isinstance(args[2], int) or not args[2] & _WRITE_FLAGS:
            return None
        paths = (args[0],)
    elif event in _PATH_EVENTS:
        paths = [args[i] for i in _PATH_EVENTS[event] if i < len(args)]
    elif event in ("socket.getaddrinfo", "socket.connect"):
        host = args[0] if event == "socket.getaddrinfo" else args[1]
        if isinstance(host, tuple):
            host = host[0] if host else None
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        if isinstance(host, str) and "webull" in host.lower():
            return host, "connect to Webull"
        return None
    elif event == "os.kill":
        # 3. above -- sys.platform, unlike os.name, is not something a test fakes
        if sys.platform == "win32" and len(args) > 1 and args[1] == 0:
            return (f"pid {args[0]}, signal 0 = CTRL_C_EVENT, a Ctrl+C to every process on "
                    "this console", "send a console-wide Ctrl+C (os.kill(pid, 0) on Windows)")
        return None
    else:
        return None
    for path in paths:
        # os.makedirs(..., exist_ok=True) on a directory that already exists changes nothing
        if _is_live(path) and not (event == "os.mkdir" and os.path.isdir(path)):
            return os.fsdecode(path), f"write under the real EDGELOG_HOME ({REAL_EDGELOG_HOME})"
    return None


def _audit_live_system(event, args):
    try:
        hit = _live_target(event, args)
    except Exception:   # an event shape this does not expect must never break the call itself
        return
    if hit:
        target, what = hit
        _BLOCKED.append({"test": _current_test[0], "event": event, "target": target,
                         "claimed": False})
        raise PermissionError(errno.EACCES, f"tests must never {what}: blocked {event}", target)


sys.addaudithook(_audit_live_system)


class _LiveSystemGuard:
    """What a test gets when it requests `live_system_guard` by name."""
    real_home = REAL_EDGELOG_HOME
    is_live = staticmethod(_is_live)

    def __init__(self, nodeid):
        self._nodeid = nodeid

    def take(self):
        """Claim and return this test's blocked attempts -- for a test that triggers one on
        purpose, so that its own teardown does not fail it."""
        mine = [b for b in _BLOCKED if b["test"] == self._nodeid and not b["claimed"]]
        for b in mine:
            b["claimed"] = True
        return mine


@pytest.fixture(autouse=True)
def live_system_guard(request):
    _current_test[0] = request.node.nodeid
    guard = _LiveSystemGuard(request.node.nodeid)
    yield guard
    _current_test[0] = None
    blocked = guard.take()
    if blocked:
        pytest.fail("this test reached for the owner's live setup and was blocked -- use temp "
                    f"paths and fakes (real EDGELOG_HOME: {REAL_EDGELOG_HOME}):\n"
                    + "\n".join(f"  {b['event']}: {b['target']}" for b in blocked), pytrace=False)


def pytest_sessionfinish(session, exitstatus):
    if (any(not b["claimed"] for b in _BLOCKED)
            and session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED)):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    stray = [b for b in _BLOCKED if not b["claimed"]]
    if stray:
        terminalreporter.section("blocked reaches for the live setup outside any test", red=True)
        for b in stray:
            terminalreporter.line(f"{b['event']}: {b['target']}")


# ── 1. the QQQ shadow's broker order adapter ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def _broker_isolation_root(tmp_path_factory):
    return tmp_path_factory.mktemp("broker_isolation")


_broker_dirs = itertools.count()


@pytest.fixture(autouse=True)
def _isolate_broker_adapter(live_system_guard, monkeypatch, _broker_isolation_root):
    try:
        from api import qqq_exec as qe
        from api import webull_orders as wo
    except ImportError:   # then nothing in this run can reach the singleton either
        yield
        return
    d = _broker_isolation_root / str(next(_broker_dirs))
    d.mkdir()
    cfg = wo.load_config(str(d / "config.json"))   # no such file -> defaults, mode OFF
    cfg.update(mode=wo.MODE_OFF, state_path=str(d / "state.json"), kill_file=str(d / "KILL"),
               arm_live_file=str(d / "ARM_LIVE"), paper_keys_path=str(d / "paper_keys.json"),
               live_keys_path=str(d / "live_keys.json"), paper_token_dir=str(d / "paper_token"),
               live_token_dir=str(d / "live_token"))
    monkeypatch.setattr(qe, "_ORDER_ADAPTER", wo.OrderAdapter(config=cfg, log=lambda *a, **k: None))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(d / "broker_orders.csv"))
    yield


# ── 1b. the SERVING_HOSTS GATE's config.json (major review fix, 2026-09-26) ──────────────
@pytest.fixture(autouse=True)
def _isolate_serving_hosts_config(live_system_guard, monkeypatch, _broker_isolation_root):
    """api.qqq_exec._serving_hosts_ok and api.cloud_signal._serving_hosts_ok both read
    config.json's optional "serving_hosts" allow-list BEFORE a test can reach anything
    else it wants to exercise (the host slot, the lease, a ledger upgrade, a heartbeat
    write...), and neither call touches Firestore or the broker, so nothing else in this
    file isolates it. Without this, two things went wrong (major review finding): on a
    fresh EDGELOG_HOME (CI, a new box) the gate's read used to be load_config(), which
    WRITES a default config.json the live-system guard then blocked, failing tests that
    never cared about config at all; and on a host that HAS the owner's recommended
    serving_hosts key in its real config.json, the gate genuinely refused that host,
    silently changing the behaviour of unrelated tests that assume "every host may
    serve" (today's behaviour). Point both modules at ONE private, per-test config path
    with no serving_hosts key -- so a real C:\\EdgeLog\\qqq_exec\\config.json, present on
    the PC and on any host once the owner adds this key, can never reach a test that did
    not ask for it. A test that wants the gate itself writes its own config to this same
    path (or overrides these same attributes), exactly like every other fixture here.

    Only CONFIG_PATH is repointed, never OUT_DIR: OUT_DIR (and everything else derived
    from it -- STATE_PATH, ORDERS_CSV, SERVING_LOCK...) is a module-level constant other
    tests assert the exact literal value of (tests/test_qqq_exec_edgelog_home.py), and
    only CONFIG_PATH is what load_config/_read_config_for_gate actually read.
    api.cloud_signal._qqq_exec_config_path is monkeypatched directly rather than via the
    EDGELOG_QQQ_EXEC_DIR env var: that env var is real process environment, which leaks
    into every subprocess a test spawns (tests/test_qqq_exec_edgelog_home.py's own
    EDGELOG_HOME-override tests run qqq_exec in a fresh subprocess specifically to prove
    what an UNPATCHED environment does) -- an attribute monkeypatch never crosses that
    boundary. A test that wants _qqq_exec_config_path's own path-building logic keeps its
    own reference to the real function, captured at collection time before this fixture
    ever runs (see tests/test_cloud_signal_serving_hosts.py)."""
    try:
        from api import qqq_exec as qe
    except ImportError:   # then nothing in this run can reach either gate
        yield
        return
    d = _broker_isolation_root / f"servinghosts_{next(_broker_dirs)}"
    d.mkdir()
    cfg_path = str(d / "config.json")
    monkeypatch.setattr(qe, "CONFIG_PATH", cfg_path)
    try:
        from api import cloud_signal as cs
        monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: cfg_path)
    except ImportError:
        pass
    yield


# ── 4. the QQQ shadow's live Webull price stream ─────────────────────────────────────────
class _InertStreamer:
    """Stand-in for api.webull_stream.WebullBarStreamer: records start()/stop() calls,
    starts no thread, opens no socket. The default every test gets from
    qqq_exec._webull_stream_factory() (see _isolate_qqq_stream) -- a test that wants to
    exercise the REAL wiring (guarded-thread, exception containment, standby-never-
    streams) installs its own fake via monkeypatch instead, never this one and never
    the genuine class."""
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        _InertStreamer.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def last_trade(self):
        return None

    def is_fresh(self):
        return False

    def health(self):
        return {"connected": False, "fresh": False, "last_message_age_s": None,
                "messages_per_min": 0.0, "reconnects": 0, "subscribed_symbols": [],
                "trading_session_counts": {}}


@pytest.fixture(autouse=True)
def _isolate_qqq_stream(live_system_guard, monkeypatch):
    try:
        from api import qqq_exec as qe
    except ImportError:
        yield
        return
    _InertStreamer.instances = []
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _InertStreamer)
    # A stray streamer left running by a test that bypassed _start_qqq_stream (or by
    # this fixture's own prior run, belt-and-suspenders) must never survive into the
    # next test.
    monkeypatch.setattr(qe, "_qqq_stream_state",
                        {"streamer": None, "starting": False, "stop_requested": False})
    yield


# ── 5. the QQQ shadow's in-flight broker-send tracker ────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_inflight_send(live_system_guard, monkeypatch):
    try:
        from api import qqq_exec as qe
    except ImportError:
        yield
        return
    # fresh before AND after: a test that deliberately drives a real hang through
    # _place_stock_order_with_timeout must not have some earlier test's leftover
    # "in flight" belief make its own first send instantly BLOCKED, and must not leave
    # its own belief behind for the next test either.
    monkeypatch.setattr(qe, "_inflight_send", {"future": None, "leg": None, "intent": None})
    monkeypatch.setattr(qe, "_send_stall_logged", {"active": False})
    # same for the order-lookup tracker (a timed-out lookup future is remembered so the
    # next lookup is skipped while it still runs) -- never leaks between tests
    monkeypatch.setattr(qe, "_order_lookup_inflight", {"future": None}, raising=False)
    yield
    monkeypatch.setattr(qe, "_inflight_send", {"future": None, "leg": None, "intent": None})
    monkeypatch.setattr(qe, "_send_stall_logged", {"active": False})
    monkeypatch.setattr(qe, "_order_lookup_inflight", {"future": None}, raising=False)


@pytest.fixture(autouse=True)
def _reset_order_lookup_cooldown():
    """api.qqq_exec skips order lookups for a few seconds after one timed out
    (_order_lookup_timeout_at). Reset it around every test so one test's timeout can
    never turn another test's lookup into 'unverifiable'."""
    import sys
    qe = sys.modules.get("api.qqq_exec")
    if qe is not None and hasattr(qe, "_order_lookup_timeout_at"):
        qe._order_lookup_timeout_at["t"] = 0.0
    yield
    qe = sys.modules.get("api.qqq_exec")
    if qe is not None and hasattr(qe, "_order_lookup_timeout_at"):
        qe._order_lookup_timeout_at["t"] = 0.0
