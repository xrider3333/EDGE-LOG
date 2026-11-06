"""The NinjaTrader connection re-dial (owner 2026-11-06): nt_recover.ps1 step 0 and tools/nt_conn_poll.ps1.

Both are PowerShell, so this pins the contract by reading the files: the watchdog re-dials BEFORE
its 'healthy' exit, both honour the C:\\EdgeLog\\NO_AUTO_RECONNECT_<NAME> opt-out, both only ever
call `nt_bridge.py connect` (never restart / enable / disable / orders), and the poller has the
backoff numbers the owner was told (20 s poll, 60 s per name, 10 fails -> alert).
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOVER = os.path.join(ROOT, "tools", "nt_recover.ps1")
POLL = os.path.join(ROOT, "tools", "nt_conn_poll.ps1")
VBS = os.path.join(ROOT, "deploy", "windows", "EdgeLogNtConnPoll.vbs")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_recover_redials_before_the_healthy_exit():
    s = _read(RECOVER)
    i0 = s.index("if (BridgeUp) { ReconnectLost }")
    assert s.index('Log "=== recover start') < i0 < s.index("# \u2500\u2500 1. already healthy?")
    assert "$reconnNames = @('Live', 'Simulation')" in s
    assert "@('ConnectionLost', 'Disconnected')" in s
    assert "NO_AUTO_RECONNECT_$($n.ToUpper())" in s


def test_poller_contract():
    s = _read(POLL)
    assert "$names     = @('Live', 'Simulation')" in s
    assert "$PollSec    = 20" in s and "$BackoffSec = 60" in s and "$MaxFails   = 10" in s
    assert "NO_AUTO_RECONNECT_$($n.ToUpper())" in s
    assert "post --from NT-CONNPOLL PAPER-NT8" in s
    assert "nt_conn_poll.log" in s
    assert "Global\\EdgeLogNtConnPoll" in s  # single instance


def test_both_only_dial_the_bridge():
    for p in (POLL,):
        s = _read(p)
        for forbidden in ("/shutdown", "/strategy/enable", "/strategy/disable", "/orders", "/positions", "nt_login"):
            assert forbidden not in s, (p, forbidden)
        assert re.search(r"\$cli connect --name \$n", s)
    s = _read(RECOVER)
    step0 = s[s.index("# \u2500\u2500 0. re-dial lost connections"):s.index("# \u2500\u2500 1. already healthy?")]
    for forbidden in ("/shutdown", "/strategy/enable", "/strategy/disable", "/orders", "/positions"):
        assert forbidden not in step0


def test_logon_launcher_runs_the_deployed_copy():
    s = _read(VBS)
    assert 'C:\\EdgeLog\\nt_conn_poll.ps1' in s
    assert ", 0, False" in s  # hidden, do not wait
