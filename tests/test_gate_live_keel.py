"""api/gate_live.py /keel -- the KEEL v12 size multiplier for the NinjaTrader KEEL legs
(EdgeLogNOISE555K -> NOISE_555_K12, EdgeLogNOISE545K -> NOISE_545_K12).

Pins: the served keel_size is the paper leg's own walk size for the next trade (keel_walk on
the same trades, same version), the multiplier is that x the file's own tilt, the bar
interlock refuses like decide(), every failure is multiplier 1.0, and the paper leg's
gate-on-a-self-sizing-file rows unfold to size = file size x KEEL size.
"""
import numpy as np
import pandas as pd
import pytest

from api import gate_live as g
from api import paper
from augur_engine import ml_keel

ET = "US/Eastern"


def _world(n_days=60, seed=7):
    """A synthetic NQ 5m RTH tape (78 bars a session, weekdays) plus ~200 non-overlapping trades."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-03-02", periods=n_days)
    stamps = []
    for d in days:
        t0 = pd.Timestamp(d.date()).tz_localize(ET) + pd.Timedelta(hours=9, minutes=30)
        stamps.extend(t0 + pd.Timedelta(minutes=5 * i) for i in range(78))
    idx = pd.DatetimeIndex(stamps)
    n = len(idx)
    c = 20000 + np.cumsum(rng.normal(0, 8, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 6, n)
    l = np.minimum(o, c) - rng.uniform(0, 6, n)
    arrays = {"index": idx, "open": o, "high": h, "low": l, "close": c,
              "volume": rng.uniform(100, 1000, n),
              "day_id": pd.factorize(pd.Series(idx).dt.date)[0].astype("int64")}
    T, e = [], 200
    while e < n - 40:
        x = e + int(rng.integers(2, 12))
        T.append((e, x, float(rng.normal(2.0, 30.0))))
        e = x + int(rng.integers(1, 8))
    # entries never on a session's first bar (NOISE decides at a bar close, fills the next open)
    T = [t for t in T if idx[t[0]].time() != pd.Timestamp("09:30").time()]
    return arrays, T


def _leg(key):
    return {l["key"]: l for l in g.keel_legs()}[key]


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(g, "_log", lambda *a, **k: None)
    monkeypatch.setattr(g, "_max_contracts", lambda: 40)
    g._keel_states.clear(); g._live_caches.clear()
    yield
    g._keel_states.clear(); g._live_caches.clear()


def _serve_prefix(leg, arrays, e):
    """The live window as decide() sees it the instant bar e-1 closed."""
    cut = {k: (v[:e] if hasattr(v, "__len__") and len(v) == len(arrays["index"]) else v)
           for k, v in arrays.items()}
    c = g._cache_for(leg)
    c["arrays"], c["covered_through"] = cut, 10 ** 12
    return cut


def test_keel_legs_are_the_two_nt_keel_legs():
    keys = {l["key"] for l in g.keel_legs()}
    assert keys == {"NOISE_555_K12", "NOISE_545_K12"}
    for l in g.keel_legs():
        assert l["gate"]["mode"] == "keel" and l["gate"]["version"] == "v12"
        assert l["size_contract"] and not g.serves(l)       # never in the ML-gate artifact path
    assert _leg("NOISE_555_K12")["strategy"] == "NOISE_1_8_CT304H_FT.py"
    assert _leg("NOISE_555_K12")["params"] == dict(tilt_mult=1.75, gate_len=16, gate_ratio=1.15)
    assert _leg("NOISE_545_K12")["strategy"] == "NOISE_1_8_CT304H_KFX.py"
    assert _leg("NOISE_545_K12")["params"] == dict(tilt_mult=2.75, gate_len=16, gate_ratio=1.15, fri_mult=2.0)
    assert paper.LEG_LIVE_FROM["NOISE_555_K12"] == "2026-11-23" == paper.LEG_LIVE_FROM["NOISE_545_K12"]


@pytest.mark.parametrize("key", ["NOISE_555_K12", "NOISE_545_K12"])
def test_keel_size_equals_the_paper_walk_times_the_file_tilt(quiet, key):
    leg = _leg(key)
    arrays, T = _world()
    feats = ml_keel.keel_features(arrays)
    walk = ml_keel.keel_walk(arrays, T, feats=feats, version="v12")["size"]
    checked = 0
    for k in (len(T) - 30, len(T) - 9, len(T) - 1):
        e = T[k][0]
        st = ml_keel.keel_build_state(arrays, T[:k], feats=feats, version="v12")
        g._keel_states[key] = {"state": st, "n_trades": k, "trained_through": "t", "version": "v12"}
        _serve_prefix(leg, arrays, e)
        out = g.keel_size(key, None)
        assert out["fallback"] is False, out
        if key == "NOISE_555_K12":
            ft = float(ml_keel.fixed_tilt_sizes_v12(arrays, [e], feats=feats)[0])
        else:
            ft = 2.0 if arrays["index"][e].dayofweek == 4 else 1.0
        assert out["keel_size"] == pytest.approx(walk[k], abs=1e-4)
        assert out["file_tilt"] == pytest.approx(ft, abs=1e-4)
        assert out["multiplier"] == pytest.approx(walk[k] * ft, abs=1e-3)
        assert out["entry_bar"] == str(arrays["index"][e])
        checked += 1
    assert checked == 3


def test_fail_open_unknown_leg_and_no_state(quiet):
    out = g.keel_size("NOISE_H_RF")
    assert out["multiplier"] == 1.0 and out["fallback"] is True and "unknown keel leg" in out["error"]
    out = g.keel_size("NOISE_555_K12")
    assert out["multiplier"] == 1.0 and out["fallback"] is True and "not built" in out["error"]


def test_fail_open_logs_loudly(monkeypatch):
    lines = []
    monkeypatch.setattr(g, "_log", lines.append)
    g._keel_states.clear()
    g.keel_size("NOISE_545_K12")
    assert any(l.startswith("KEEL FAIL-OPEN NOISE_545_K12") for l in lines)


def test_bar_interlock_mismatch_fails_open(quiet):
    key = "NOISE_555_K12"
    leg = _leg(key)
    arrays, T = _world()
    st = ml_keel.keel_build_state(arrays, T[:-1], version="v12")
    g._keel_states[key] = {"state": st, "n_trades": len(T) - 1, "trained_through": "t", "version": "v12"}
    cut = _serve_prefix(leg, arrays, T[-1][0])
    far = (cut["index"][-1] - pd.Timedelta(hours=3)).isoformat()
    out = g.keel_size(key, far)
    assert out["multiplier"] == 1.0 and out["fallback"] and out["bar_check"] == "mismatch"
    ok = g.keel_size(key, cut["index"][-1].isoformat())
    assert ok["fallback"] is False and ok["bar_check"] == "ok"


def test_incomplete_bar_fails_open(quiet):
    key = "NOISE_545_K12"
    leg = _leg(key)
    arrays, T = _world()
    st = ml_keel.keel_build_state(arrays, T[:-1], version="v12")
    g._keel_states[key] = {"state": st, "n_trades": len(T) - 1, "trained_through": "t", "version": "v12"}
    cut = _serve_prefix(leg, arrays, T[-1][0])
    g._cache_for(leg)["covered_through"] = 0           # the capture has not written that bar yet
    out = g.keel_size(key, cut["index"][-1].isoformat())
    assert out["multiplier"] == 1.0 and out["bar_check"] == "incomplete"


def test_keel_size_reads_no_disk(quiet, monkeypatch):
    """decide()'s NEVER TOUCHES DISK rule: no master load, no tick read, no backtest in the request."""
    key = "NOISE_555_K12"
    leg = _leg(key)
    arrays, T = _world()
    st = ml_keel.keel_build_state(arrays, T[:-1], version="v12")
    g._keel_states[key] = {"state": st, "n_trades": len(T) - 1, "trained_through": "t", "version": "v12"}
    _serve_prefix(leg, arrays, T[-1][0])

    def boom(*a, **k):
        raise AssertionError("disk / backtest touched in the request path")
    import augur_engine.data as d
    import augur_engine.engine as eng
    monkeypatch.setattr(d, "load_master_arrays", boom)
    monkeypatch.setattr(eng, "run_backtest", boom)
    monkeypatch.setattr(paper, "_load_fresh_ticks", boom)
    monkeypatch.setattr(g, "_leg_arrays", boom)
    assert g.keel_size(key, None)["fallback"] is False


def test_append_closed_matches_a_fresh_build(quiet, monkeypatch):
    """The bg loop's trade-by-trade append lands on the state a full walk would build."""
    key = "NOISE_555_K12"
    leg = _leg(key)
    arrays, T = _world()
    k = len(T) - 6
    feats = ml_keel.keel_features(arrays)
    st = ml_keel.keel_build_state(arrays, T[:k], feats=feats, version="v12")
    idx = arrays["index"]
    g._keel_states[key] = {"state": st, "n_trades": k, "trained_through": "t", "version": "v12",
                           "last_entry_ts": str(idx[T[k - 1][0]]), "appended": 0}
    monkeypatch.setattr(g, "_keel_leg_trades", lambda leg_, arr: list(T))
    assert g.keel_append_closed(leg, arrays=arrays) == len(T) - k
    full = ml_keel.keel_build_state(arrays, T, feats=feats, version="v12")
    got = g._keel_states[key]["state"]
    assert got["n"] == full["n"]
    x = feats[0][min(len(idx) - 1, T[-1][1] + 3)].reshape(1, -1)
    a, _ = ml_keel.keel_score_from_state(got, arrays, entry_bar=T[-1][1] + 3, x_row=x)
    b, _ = ml_keel.keel_score_from_state(full, arrays, entry_bar=T[-1][1] + 3, x_row=x)
    assert a == pytest.approx(b, abs=1e-9)


def test_unfold_gate_sizes_keeps_dollars_and_multiplies_sizes():
    raw = [(10, 14, 3.5, 1, 100.0), (20, 25, -1.2, -1, 101.0)]
    file_sizes = [1.75, 1.0]
    sized = [(raw[1], 0.8), (raw[0], 1.5)]                 # apply_gate re-sorts; match on bars
    out = paper.unfold_gate_sizes(raw, file_sizes, sized)
    by = {t[0]: (t, w) for t, w in out}
    t, w = by[10]
    assert w == pytest.approx(1.75 * 1.5) and t[2] == pytest.approx(3.5 / 1.75)
    assert t[2] * w == pytest.approx(3.5 * 1.5)               # money unchanged
    t, w = by[20]
    assert w == pytest.approx(0.8) and t[2] == pytest.approx(-1.2)
    with pytest.raises(ValueError):
        paper.unfold_gate_sizes(raw, [1.0], sized)
