"""api/ntfy_push.py -- the one shared ntfy.sh sender (WEBULL_GO_LIVE.md 1.10).

Never opens a real socket: urllib.request.urlopen is always replaced with a fake opener
that records the built Request and returns a canned response, per the task's "no network
calls from tests" rule. These tests pin the contract every other alerter is switched to:
NTFY_TOPIC required, NTFY_TOKEN optional (sent as an Authorization header, and omitted --
not sent as an empty header -- when unset), NTFY_SERVER optional, never raises, and never
puts the topic or token value into anything `log` receives.
"""
import importlib.util
import os
import urllib.error

import pytest

from api import ntfy_push
from api import nt_drawdown_alert
from api import nt_exec_review
from api import nt_heartbeat

# tools/ scripts aren't a package (no __init__.py) -- load them by path, the same way
# tests/test_nt_rollover.py already does.
_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


def _load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_TOOLS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nt_rollover = _load_tool("nt_rollover")
nt_cloud_watchdog = _load_tool("nt_cloud_watchdog")


class _FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_opener(response=None, exc=None, capture=None):
    def _open(req, timeout=None):
        if capture is not None:
            capture.append(req)
        if exc is not None:
            raise exc
        return response or _FakeResponse(200)
    return _open


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Every test starts with none of these set, then opts in explicitly -- a leaked real
    # NTFY_TOPIC from the running machine's own environment must never reach a test.
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("NTFY_TOKEN", raising=False)
    monkeypatch.delenv("NTFY_SERVER", raising=False)


def test_no_topic_skips_the_push_and_never_hits_the_network(monkeypatch):
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    logged = []
    ok = ntfy_push.push("body", title="t", log=logged.append)
    assert ok is False
    assert calls == []
    # The alert text itself must still reach the log even though the push is skipped --
    # every sender used to log its own message text in this case (dd-alert, exec-review,
    # nt-heartbeat, rollover), so this is not just "push skipped".
    assert logged == ["NTFY_TOPIC unset, push skipped: t: body"]


def test_no_topic_skips_the_push_with_no_title(monkeypatch):
    # No title at all -- the "<title>: " prefix must not appear (no "None: " either).
    logged = []
    ok = ntfy_push.push("body only", log=logged.append)
    assert ok is False
    assert logged == ["NTFY_TOPIC unset, push skipped: body only"]


def test_successful_push_posts_to_the_topic_url_with_title_and_priority(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    logged = []
    ok = ntfy_push.push("hello", title="Title Here", priority="high", log=logged.append)
    assert ok is True
    assert logged == []
    assert len(calls) == 1
    req = calls[0]
    assert req.full_url == "https://ntfy.sh/sometopic"
    assert req.data == b"hello"
    assert req.get_header("Title") == "Title Here"
    assert req.get_header("Priority") == "high"
    assert req.get_header("Authorization") is None


def test_token_set_sends_bearer_authorization_header(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setenv("NTFY_TOKEN", "tk_abc123")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    ok = ntfy_push.push("hello")
    assert ok is True
    assert calls[0].get_header("Authorization") == "Bearer tk_abc123"


def test_token_unset_behaves_exactly_like_before_this_module(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    ok = ntfy_push.push("hello", title="T", priority="high")
    assert ok is True
    assert calls[0].get_header("Authorization") is None
    assert calls[0].full_url == "https://ntfy.sh/sometopic"


def test_custom_server_overrides_the_default_host(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.com/")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    ntfy_push.push("hello")
    assert calls[0].full_url == "https://ntfy.example.com/sometopic"


def test_non_2xx_status_is_a_failure(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(response=_FakeResponse(500)))
    assert ntfy_push.push("hello") is False


def test_network_error_never_raises_and_is_reported_through_log(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setattr(
        ntfy_push.urllib.request, "urlopen",
        _fake_opener(exc=urllib.error.URLError("no route to host")))
    logged = []
    ok = ntfy_push.push("hello", log=logged.append)
    assert ok is False
    assert len(logged) == 1
    assert "URLError" in logged[0]
    assert "sometopic" not in logged[0]


def test_log_is_optional_and_defaults_to_silent(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setattr(
        ntfy_push.urllib.request, "urlopen",
        _fake_opener(exc=urllib.error.URLError("boom")))
    # No log= passed at all -- must not raise for lack of one.
    assert ntfy_push.push("hello") is False


def test_trailing_space_in_topic_is_stripped(monkeypatch):
    # `cmd /c "set NTFY_TOPIC=sometopic && python ..."` (deploy/_run_qqq_exec.vbs,
    # tools/_restart_runner.bat.example, the "EdgeLog NT futures rollover" scheduled
    # task) leaves a trailing space on the value -- confirmed in cmd.exe: `set
    # FOO=abc && python ...` prints "abc ". A URL path with a trailing space is an
    # InvalidURL to http.client, so every push from one of those launchers failed
    # silently before push() stripped this.
    monkeypatch.setenv("NTFY_TOPIC", "sometopic ")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    assert ntfy_push.push("hello") is True
    assert calls[0].full_url == "https://ntfy.sh/sometopic"


def test_trailing_space_in_token_and_server_is_also_stripped(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setenv("NTFY_TOKEN", "tk_abc123 ")
    monkeypatch.setenv("NTFY_SERVER", " https://ntfy.example.com ")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    ntfy_push.push("hello")
    assert calls[0].get_header("Authorization") == "Bearer tk_abc123"
    # NTFY_SERVER isn't leading-space-stripped by rstrip("/") alone -- only .strip()
    # (added alongside the topic/token strip) catches a leading space too.
    assert calls[0].full_url == "https://ntfy.example.com/sometopic"


def test_changeme_placeholder_token_is_never_sent(monkeypatch):
    # deploy/cloud/install.sh and deploy/cloud/edgelog.env.example now ship an EMPTY
    # NTFY_TOKEN default, but this is a belt-and-suspenders guard for an older/manually
    # edited env file that still has the placeholder: ntfy.sh 401s ANY request bearing
    # invalid credentials, even on a public topic, so sending "CHANGE-ME..." verbatim
    # would silently break every push rather than behave like no token was set.
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")
    monkeypatch.setenv("NTFY_TOKEN", "CHANGE-ME-OR-LEAVE-BLANK")
    calls = []
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen",
                         _fake_opener(capture=calls))
    ntfy_push.push("hello")
    assert calls[0].get_header("Authorization") is None


# ── switched senders: each must pass its own title/priority/timeout through unchanged ──
# WHY THIS BLOCK EXISTS: the helper above has 8 good tests, but none of them checked
# that a SWITCHED sender still calls ntfy_push.push() with its own title/priority/
# timeout intact -- the exact promise these senders' own docstrings make ("behaves
# exactly as it did before this change"). Every sender below ultimately does
# `from api import ntfy_push; ntfy_push.push(...)` (some at module level, some lazily
# inside their own notify function) -- since Python caches `api.ntfy_push` in
# sys.modules, patching the SAME module object imported here as `ntfy_push` reaches
# every one of them, whichever way they imported it.
def _capture_push(calls):
    def _fake(message, title=None, priority=None, timeout=8, log=None):
        calls.append({"message": message, "title": title, "priority": priority,
                      "timeout": timeout})
        return True
    return _fake


def test_drawdown_alert_notify_passes_its_title_priority_and_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(ntfy_push, "push", _capture_push(calls))
    nt_drawdown_alert._notify("acct down $600", "EDGELOG: intraday drawdown",
                              priority="high")
    assert len(calls) == 1
    assert calls[0]["title"] == "EDGELOG: intraday drawdown"
    assert calls[0]["priority"] == "high"
    assert calls[0]["timeout"] == nt_drawdown_alert.TIMEOUT_SEC


def test_exec_review_notify_passes_its_timeout_with_no_title_or_priority(monkeypatch):
    # nt_exec_review's _notify never sets a title/priority -- every fill/REVIEW
    # message rides the plain default, unchanged from before this module existed.
    calls = []
    monkeypatch.setattr(ntfy_push, "push", _capture_push(calls))
    nt_exec_review._notify("fill: DEMO7240108 NQ Long 1 @ 20000.0 (now)")
    assert len(calls) == 1
    assert calls[0]["title"] is None
    assert calls[0]["priority"] is None
    assert calls[0]["timeout"] == nt_exec_review.TIMEOUT_SEC


def test_nt_heartbeat_page_passes_its_title_and_high_priority(monkeypatch):
    calls = []
    monkeypatch.setattr(ntfy_push, "push", _capture_push(calls))
    nt_heartbeat._page("NT bridge stale 20m", "EDGELOG NT FEED")
    assert len(calls) == 1
    assert calls[0]["title"] == "EDGELOG NT FEED"
    assert calls[0]["priority"] == "high"
    assert calls[0]["timeout"] == 8


def test_nt_rollover_page_passes_its_title_and_high_priority(monkeypatch):
    calls = []
    monkeypatch.setattr(ntfy_push, "push", _capture_push(calls))
    nt_rollover.page("NT futures rolled", "Now on 12-26: EdgeLogNOISE Realtime MNQ 12-26")
    assert len(calls) == 1
    assert calls[0]["title"] == "NT futures rolled"
    assert calls[0]["priority"] == "high"
    assert calls[0]["timeout"] == 8


def test_nt_cloud_watchdog_pages_with_critical_title_and_urgent_priority(monkeypatch):
    monkeypatch.setenv("EDGELOG_UID", "test-uid")
    monkeypatch.setenv("NTFY_TOPIC", "sometopic")  # cw's own presence gate, not push's
    monkeypatch.setattr(nt_cloud_watchdog, "_get_firestore_client", lambda: object())
    monkeypatch.setattr(nt_cloud_watchdog, "_read_meta_doc",
                        lambda db, uid, name: None)
    monkeypatch.setattr(nt_cloud_watchdog.nt_heartbeat, "evaluate",
                        lambda bridge_data, prior_alert: {
                            "severity": "critical",
                            "message": "NT bridge heartbeat stale -- last roster Realtime",
                        })
    calls = []
    monkeypatch.setattr(ntfy_push, "push", _capture_push(calls))
    rc = nt_cloud_watchdog.main()
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["title"] == "EDGELOG: NT bridge DOWN"
    assert calls[0]["priority"] == "urgent"
    # The old _ntfy_post used timeout=10 -- must not silently drop to the helper's
    # default (8) now that this sender is switched.
    assert calls[0]["timeout"] == 10
