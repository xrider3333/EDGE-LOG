"""The as-if extension hook in the three side-panel plugins (PICK6 #511, OPUS86a #526, GLDNIGHT #541; 2026-11-21).

The hook (PANEL_EXT_ENV in each file) lets tools/book_asif_series.py score sessions after the pinned panel's end on a
fresher panel. The validated runs must not move, so:
  * the pinned panel path and sha256 are unchanged;
  * with the variable UNSET the new file returns exactly what the pre-hook file (its git blob, pinned below) returns,
    on synthetic panels and a synthetic bar clock - every trade tuple, every score;
  * with it SET, every trade up to the pinned end is unchanged and the only new trades are dated after it;
  * a set path that does not exist raises.
Synthetic data only: no real panel or master is needed (runs in CI).
"""
import importlib.util
import os
import subprocess

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# file -> (pinned path, pinned sha256, the pre-hook git blob)
PLUGINS = {
    "MISC_EODREV_1_2": ("C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_u100_panel_v1.npz",
                        "2d789ae97f566ccf94d6bebe97e4f2ff0f224ee11e1d71929409238785ec37ab",
                        "48170ec368e050d5f458fa83cc46abf3a8d98811"),
    "MISC_AUCHABIT_1_0": ("C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_v1.npz",
                          "e7de7ff79afa137f14d0a989a45d10e693e2b6d9ec8bacb8b95bb81e05a2b6e1",
                          "fab9e618488ded9e35cff7fdb5cf301c618c71a1"),
    "MISC_GLDNIGHT_1_0": ("C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_v1.npz",
                          "274eff68f1269ac46d19a3f3ebe54f79aba582284209609e78d8e6cee6de632a",
                          "77f07bfa2cc676b25833ef903f8088f8409085b6"),
}
PARAMS = {
    "MISC_EODREV_1_2": dict(k=3, beta_len=60, min_price=40, period_len=20, period_wt=1.5),
    "MISC_AUCHABIT_1_0": dict(period_len=20, k=3, min_price=40),
    "MISC_GLDNIGHT_1_0": dict(nights="weeknights"),
}


def _load_file(name, path):
    sp = importlib.util.spec_from_file_location("%s_%d" % (name, abs(hash(path))), path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _new(name):
    return _load_file(name, os.path.join(REPO, "augur_strategies", name + ".py"))


def _old(name, tmp_path):
    blob = PLUGINS[name][2]
    try:
        src = subprocess.run(["git", "cat-file", "-p", blob], cwd=REPO, capture_output=True, check=True).stdout
    except Exception:
        pytest.skip("git history not available")
    p = tmp_path / ("old_" + name + ".py")
    p.write_bytes(src)
    return _load_file(name, str(p))


def _days(start, n):
    return pd.bdate_range(start, periods=n)


def _sha(p):
    import hashlib
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _panel(name, days, path, seed):
    """A synthetic side panel of the plugin's layout over these sessions."""
    rng = np.random.default_rng(seed)
    T = len(days)
    dates = np.array([int(d.strftime("%Y%m%d")) for d in days], "int64")
    if name == "MISC_GLDNIGHT_1_0":
        c = 180 * np.exp(np.cumsum(rng.normal(0, 0.01, T)))
        o = c * np.exp(rng.normal(0, 0.004, T))
        gap = np.concatenate([[0], np.diff(days.values).astype("timedelta64[D]").astype("int64")])
        np.savez(path, dates=dates, open=o, close=c, raw=c, first_min=np.full(T, 570, "int64"),
                 last_min=np.full(T, 955, "int64"), gap=gap)
        return
    names = ["N%02d" % i for i in range(24)]
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, (T, len(names) + 1)), axis=0))
    j = lambda s: px * np.exp(rng.normal(0, s, px.shape))
    if name == "MISC_EODREV_1_2":
        nm = names + ["SPY"]
        np.savez(path, dates=dates, names=np.array(nm), ps=j(0.003), pe=j(0.003), c10=j(0.002), dc=px, raw=px,
                 member=np.ones((T, len(nm)), bool))
    else:
        p = px[:, :-1]
        np.savez(path, dates=dates, names=np.array(names), full=np.ones(T, bool),
                 o50=(p * np.exp(rng.normal(0, 0.003, p.shape))).astype("float32"),
                 c50=(p * np.exp(rng.normal(0, 0.001, p.shape))).astype("float32"),
                 dc=p.astype("float32"), raw=p.astype("float32"), member=np.ones(p.shape, bool))


def _clock(days):
    """5m RTH bars 09:30 .. 15:55 ET for each session (the master is the clock only)."""
    idx = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 5 * i) for d in days for i in range(78)]).tz_localize(
        "US/Eastern")
    x = np.linspace(100, 110, len(idx))
    return dict(opens=x, highs=x + 0.1, lows=x - 0.1, closes=x, index=idx)


def _run(mod, bars, params):
    mod._CACHE.clear()
    r = mod.run_backtest(bars["opens"], bars["highs"], bars["lows"], bars["closes"], index=bars["index"],
                         return_trades=True, **params)
    return r


@pytest.mark.parametrize("name", sorted(PLUGINS))
def test_pinned_constants_unchanged(name):
    m = _new(name)
    path, sha, _blob = PLUGINS[name]
    assert m.PANEL_PATH == path and m.PANEL_SHA256 == sha
    assert m.PANEL_EXT_ENV == name + "_PANEL_EXT"


@pytest.mark.parametrize("name", sorted(PLUGINS))
def test_default_equals_prehook_file(name, tmp_path, monkeypatch):
    monkeypatch.delenv(name + "_PANEL_EXT", raising=False)
    days = _days("2025-01-02", 160)
    pin = tmp_path / "pinned.npz"
    _panel(name, days, str(pin), 1)
    bars = _clock(_days("2025-01-02", 200))             # the clock runs past the pinned end, as the master now does
    out = []
    for mod in (_old(name, tmp_path), _new(name)):
        mod.PANEL_PATH, mod.PANEL_SHA256 = str(pin), _sha(pin)
        out.append(_run(mod, bars, PARAMS[name]))
    assert out[0] is not None and out[0]["num_trades"] > 20
    assert out[0] == out[1]                               # every trade tuple and every score


@pytest.mark.parametrize("name", sorted(PLUGINS))
def test_ext_adds_only_sessions_after_the_pinned_end(name, tmp_path, monkeypatch):
    all_days = _days("2025-01-02", 200)
    pin, ext = tmp_path / "pinned.npz", tmp_path / "ext.npz"
    _panel(name, all_days[:160], str(pin), 1)
    _panel(name, all_days[60:], str(ext), 2)              # the extension starts before the pinned end (warm-up)
    bars = _clock(all_days)
    mod = _new(name)
    mod.PANEL_PATH, mod.PANEL_SHA256 = str(pin), _sha(pin)
    monkeypatch.delenv(name + "_PANEL_EXT", raising=False)
    base = _run(mod, bars, PARAMS[name])
    monkeypatch.setenv(name + "_PANEL_EXT", str(ext))
    got = _run(mod, bars, PARAMS[name])
    day_of = lambda t: int(bars["index"][t[1]].strftime("%Y%m%d"))
    last = int(all_days[159].strftime("%Y%m%d"))
    before = [t for t in got["trades"] if day_of(t) <= last]
    after = [t for t in got["trades"] if day_of(t) > last]
    assert before == base["trades"]                       # nothing up to the pinned end moves
    assert len(after) > 10 and all(day_of(t) > last for t in after)
    assert max(day_of(t) for t in base["trades"]) <= last


@pytest.mark.parametrize("name", sorted(PLUGINS))
def test_missing_ext_raises(name, tmp_path, monkeypatch):
    days = _days("2025-01-02", 120)
    pin = tmp_path / "pinned.npz"
    _panel(name, days, str(pin), 1)
    mod = _new(name)
    mod.PANEL_PATH, mod.PANEL_SHA256 = str(pin), _sha(pin)
    monkeypatch.setenv(name + "_PANEL_EXT", str(tmp_path / "nope.npz"))
    with pytest.raises(RuntimeError):
        _run(mod, _clock(days), PARAMS[name])
