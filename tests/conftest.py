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
