"""Board C6: bar-data checks before the engine reads a master."""
import os

import numpy as np
import pandas as pd
import pytest

from augur_engine import bar_checks as B
from augur_engine import data as D

T0 = 1_700_000_000  # 2023-11-14, not in a roll window


def _clean(n=50):
    t = T0 + 60 * np.arange(n)
    c = 100 + np.cumsum(np.sin(np.arange(n)) * 0.1)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + 0.05
    l = np.minimum(o, c) - 0.05
    return t, o, h, l, c


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("AUGUR_BAR_CHECKS", raising=False)
    B._cache_clear()
    D._memo_clear()
    yield
    B._cache_clear()


def test_clean_passes():
    r = B.check_bars(*_clean())
    assert r["ok"] and not r["soft"] and r["n_bad_ohlc"] == 0 and r["jumps"] == []


@pytest.mark.parametrize("cls", ["nan", "inf", "zero"])
def test_nonfinite_hard(cls):
    t, o, h, l, c = _clean()
    c = c.copy(); c[7] = {"nan": np.nan, "inf": np.inf, "zero": 0.0}[cls]
    r = B.check_bars(t, o, h, l, c)
    assert not r["ok"] and r["n_nonfinite"] == 1 and "n_nonfinite" in r["hard"]


def test_dup_and_out_of_order_hard():
    t, o, h, l, c = _clean()
    t = t.copy(); t[5] = t[4]
    r = B.check_bars(t, o, h, l, c)
    assert r["n_dup_ts"] == 1 and not r["ok"]
    t2 = _clean()[0].copy(); t2[10], t2[11] = t2[11], t2[10]
    r = B.check_bars(t2, o, h, l, c)
    assert r["n_out_of_order"] == 1 and not r["ok"]


def test_high_lt_low_hard():
    t, o, h, l, c = _clean()
    h = h.copy(); h[3] = l[3] - 1
    r = B.check_bars(t, o, h, l, c)
    assert r["n_high_lt_low"] == 1 and not r["ok"]


def test_containment_soft():
    t, o, h, l, c = _clean()
    h = h.copy(); h[3] = max(o[3], c[3]) - 0.01
    l = l.copy(); l[4] = min(o[4], c[4]) + 0.01
    r = B.check_bars(t, o, h, l, c)
    assert r["ok"] and r["soft"] and r["n_bad_ohlc"] == 2


def test_jump_soft_and_roll_window_explained():
    t, o, h, l, c = _clean()
    c = c.copy(); c[20:] *= 1.5; h = h.copy(); h[20:] *= 1.5; o = o.copy(); o[20:] *= 1.5; l = l.copy(); l[20:] *= 1.5
    r = B.check_bars(t, o, h, l, c)
    assert r["ok"] and r["n_jumps"] == 1 and r["jumps"][0]["ratio"] == pytest.approx(1.5, rel=1e-2)
    # 2024-03-12 sits in the March 2024 roll window (expiry 03-15)
    tr = 1710252000 + 60 * np.arange(len(t))
    assert B.check_bars(tr, o, h, l, c)["n_jumps"] == 0


def test_soft_override_demotes():
    t, o, h, l, c = _clean()
    t = t.copy(); t[5] = t[4]
    B.SOFT_OVERRIDE.add("n_dup_ts")
    try:
        assert B.check_bars(t, o, h, l, c)["ok"]
    finally:
        B.SOFT_OVERRIDE.discard("n_dup_ts")


def _write(tmp_path, arrs, name="m.csv"):
    t, o, h, l, c = arrs
    p = tmp_path / name
    pd.DataFrame({"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}).to_csv(p, index=False)
    return p


def _load(monkeypatch, tmp_path, name="m.csv"):
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    return D.load_master_arrays({"filename": name, "source": "tv"})


def test_load_refuses_hard_and_kill_switch(monkeypatch, tmp_path):
    t, o, h, l, c = _clean()
    t = t.copy(); t[5] = t[4]
    _write(tmp_path, (t, o, h, l, c))
    with pytest.raises(B.BarCheckError, match=r"REFUSED master m\.csv: dup_ts x1, first at 2023"):
        _load(monkeypatch, tmp_path)
    monkeypatch.setenv("AUGUR_BAR_CHECKS", "0")
    assert _load(monkeypatch, tmp_path)["bar_checks"] is None


def test_clean_load_identical_and_cached(monkeypatch, tmp_path):
    arrs = _clean()
    _write(tmp_path, arrs)
    on = _load(monkeypatch, tmp_path)
    assert on["bar_checks"]["ok"]
    calls = []
    real = B.check_bars
    monkeypatch.setattr(B, "check_bars", lambda *a, **k: calls.append(1) or real(*a, **k))
    D._memo_clear()
    _load(monkeypatch, tmp_path)
    assert calls == []                       # cached per (path, size, mtime)
    monkeypatch.setenv("AUGUR_BAR_CHECKS", "0")
    D._memo_clear()
    off = _load(monkeypatch, tmp_path)
    for k in ("open", "high", "low", "close", "volume", "day_id"):
        assert np.array_equal(on[k], off[k])
    assert on["fingerprint"] == off["fingerprint"] and on["index"].equals(off["index"])


def test_golden_backtest_on_off(monkeypatch, tmp_path):
    """A tiny synthetic backtest (MA cross on the loaded arrays) is identical with checks on vs off."""
    n = 400
    t = T0 + 300 * np.arange(n)
    c = 100 + np.cumsum(np.sin(np.arange(n) / 7.0))
    o = np.r_[c[0], c[:-1]]
    _write(tmp_path, (t, o, np.maximum(o, c) + .2, np.minimum(o, c) - .2, c))

    def bt(a):
        cl = a["close"]
        f = pd.Series(cl).rolling(5).mean().values
        s = pd.Series(cl).rolling(20).mean().values
        pos = np.where(f > s, 1.0, 0.0)
        return float(np.nansum(pos[:-1] * np.diff(cl)))

    on = bt(_load(monkeypatch, tmp_path))
    monkeypatch.setenv("AUGUR_BAR_CHECKS", "0")
    D._memo_clear()
    off = bt(_load(monkeypatch, tmp_path))
    assert on == off
