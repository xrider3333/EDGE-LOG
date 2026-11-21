"""Latency item D (2026-11-21): keep-alive HTTPS session for the Webull SDK.

install_keepalive() swaps webull.core.http.response.Session for a per-thread persistent
session factory; these tests check reuse, per-thread isolation, drop-on-error, idle
recycle, cookie clearing, the env kill switch and the no-patch fallback.
"""
import sys
import threading
import types

import pytest
import requests

from api import webull_orders as WO


class _FakeSession:
    made = 0

    def __init__(self):
        _FakeSession.made += 1
        self.closed = False
        self.cookies = requests.cookies.RequestsCookieJar()

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset():
    _FakeSession.made = 0
    WO.uninstall_keepalive()
    yield
    WO.uninstall_keepalive()


def test_reuses_one_session_per_thread():
    f = WO._KeepAliveSessionFactory(_FakeSession)
    with f() as a:
        pass
    with f() as b:
        pass
    assert a is b and not a.closed and _FakeSession.made == 1
    out = []
    t = threading.Thread(target=lambda: out.append(f().__enter__()))
    t.start()
    t.join()
    assert out[0] is not a and _FakeSession.made == 2


def test_error_drops_session():
    f = WO._KeepAliveSessionFactory(_FakeSession)
    with pytest.raises(RuntimeError):
        with f() as a:
            raise RuntimeError("boom")
    assert a.closed
    with f() as b:
        pass
    assert b is not a


def test_idle_session_is_replaced():
    now = {"t": 0.0}
    f = WO._KeepAliveSessionFactory(_FakeSession, max_idle=50.0, clock=lambda: now["t"])
    with f() as a:
        pass
    now["t"] = 49.0
    with f() as b:
        pass
    assert b is a
    now["t"] = 49.0 + 51.0
    with f() as c:
        pass
    assert c is not a and a.closed


def test_cookies_cleared_before_each_use():
    f = WO._KeepAliveSessionFactory(_FakeSession)
    with f() as a:
        a.cookies.set("x", "1")
    with f() as b:
        assert len(b.cookies) == 0


def _fake_sdk(monkeypatch, session_obj):
    resp = types.ModuleType("webull.core.http.response")
    resp.Session = session_obj
    for name in ("webull", "webull.core", "webull.core.http"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["webull.core.http"].response = resp
    monkeypatch.setitem(sys.modules, "webull.core.http.response", resp)
    return resp


def test_install_patches_and_uninstall_restores(monkeypatch):
    monkeypatch.delenv("EDGELOG_WEBULL_KEEPALIVE", raising=False)
    resp = _fake_sdk(monkeypatch, requests.Session)
    assert WO.install_keepalive() is True
    assert isinstance(resp.Session, WO._KeepAliveSessionFactory)
    assert WO.install_keepalive() is True          # idempotent
    WO.uninstall_keepalive()
    assert resp.Session is requests.Session


def test_unexpected_sdk_shape_falls_back(monkeypatch):
    monkeypatch.delenv("EDGELOG_WEBULL_KEEPALIVE", raising=False)
    sentinel = object()
    resp = _fake_sdk(monkeypatch, sentinel)
    logs = []
    assert WO.install_keepalive(log=logs.append) is False
    assert resp.Session is sentinel and logs


def test_env_kill_switch(monkeypatch):
    monkeypatch.setenv("EDGELOG_WEBULL_KEEPALIVE", "0")
    resp = _fake_sdk(monkeypatch, requests.Session)
    assert WO.install_keepalive() is False
    assert resp.Session is requests.Session
