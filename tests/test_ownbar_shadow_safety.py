"""VERIFIER 11-21 should-fixes for tools/ownbar_shadow.py: 429 back-off on the shared Webull
key, and the shared token dir is never written (the SDK is pointed at a private copy)."""
import importlib.util
import os
import pathlib
import sys
import time


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    p = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ownbar_shadow.py"
    spec = importlib.util.spec_from_file_location("ownbar_shadow_t", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Cs:
    def __init__(self, exc=None, err=None):
        self.exc, self._WEBULL_LAST_ERR, self.calls = exc, ({"text": err} if err else {}), 0

    def _fetch_webull(self, *a, **k):
        self.calls += 1
        if self.exc:
            raise self.exc
        return None


def test_429_exception_backs_off_and_stops_calling(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    cs = _Cs(exc=RuntimeError("HTTP Status: 429 Too Many Requests"))
    assert m.rest_read(cs, 0) == "ERR 429"
    assert m.rest_read(cs, 0) == "BACKOFF"
    assert cs.calls == 1


def test_429_in_last_err_backs_off(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    cs = _Cs(err="rate limit exceeded")
    assert m.rest_read(cs, 0) == "ERR 429"
    assert m._BACKOFF_UNTIL[0] > time.time()


def test_other_error_does_not_back_off(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    cs = _Cs(exc=ValueError("boom"))
    assert m.rest_read(cs, 0) == "ERR ValueError"
    assert m._BACKOFF_UNTIL[0] == 0.0


def test_token_dir_is_a_private_copy(tmp_path, monkeypatch):
    shared = tmp_path / "webull_token"
    shared.mkdir()
    (shared / "token.txt").write_text("T")
    monkeypatch.setenv("EDGELOG_WEBULL_TOKEN_DIR", str(shared))
    m = _load(tmp_path, monkeypatch)
    priv = m._private_token_dir()
    assert priv and os.path.realpath(priv) != os.path.realpath(str(shared))
    assert os.environ["EDGELOG_WEBULL_TOKEN_DIR"] == priv
    assert (pathlib.Path(priv) / "token.txt").read_text() == "T"
    (pathlib.Path(priv) / "token.txt").write_text("NEW")
    assert (shared / "token.txt").read_text() == "T"
