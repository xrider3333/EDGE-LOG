"""Point score ps1.2 in the trade-bars publisher (owner 2026-10-02 via MANAGER #18): the score is the SMA
record with the EMA record under alt.ema, an older record is re-scored once to get both, and the bars doc
carries 200 lines that pass through the very reference the score compared the signal candle against."""
import types

import numpy as np
import pandas as pd
import pytest

from api import trade_bars as tb

ET = "America/New_York"


class _Doc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return _Coll(self.db, self.path + "/" + name)

    def set(self, d, merge=False):
        cur = self.db.store.get(self.path, {}) if merge else {}
        cur = dict(cur)
        cur.update(d)
        self.db.store[self.path] = cur

    def update(self, d):
        self.set(d, merge=True)


class _Coll:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, i):
        return _Doc(self.db, self.path + "/" + i)


class _Db:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _Coll(self, name)


def _trade(**kw):
    t = {"symbol": "MNQ", "date": "2026-09-30", "entryTime": "10:00", "exitTime": "10:05", "type": "LONG",
         "entry": 20000.0, "exit": 20010.0, "size": 1, "pnl": 20.0}
    t.update(kw)
    return t


def _rec(ma, total):
    return {"v": "ps1.2", "ma": ma, "total": total, "max": 9, "na_count": 0, "trend": None, "signal_bar": "s",
            "points": [{"k": "ma200_1m", "hit": True, "na_reason": None}]}


class _Mod(types.SimpleNamespace):
    """A ps1.2-shaped scorer: score_trade(tr, ma=...) returns a different total per average."""

    def __init__(self, calls):
        super().__init__(VERSION="ps1.2", MA_TYPES=("sma", "ema"), NA_NOBAR="nobar", NA_NO10BAR="x", NA_NO10="y")
        self.calls = calls

    def score_trade(self, tr, ma="sma"):
        self.calls.append((tr["fill"], ma))
        return _rec(ma, 7 if ma == "sma" else 5)


def test_the_score_is_the_sma_record_and_carries_the_ema_one(monkeypatch):
    calls = []
    monkeypatch.setattr(tb, "_point_score_module", lambda: _Mod(calls))
    rec = tb.point_score(_trade(), ({}, {}))
    assert [m for _f, m in calls] == ["sma", "ema"]
    assert rec["ma"] == "sma" and rec["total"] == 7
    assert rec["alt"]["ema"]["ma"] == "ema" and rec["alt"]["ema"]["total"] == 5
    assert set(rec["alt"]["ema"]) == set(tb.PS_ALT_KEYS)


def test_a_record_without_its_ema_twin_is_rescored_once(monkeypatch):
    calls = []
    monkeypatch.setattr(tb, "_point_score_module", lambda: _Mod(calls))
    monkeypatch.setattr(tb, "build", lambda *a, **k: (None, "no_bars"))
    t = _trade()
    tid, key = "nt_1", "users/u/trades/nt_1"
    t["pointScore"] = dict(_rec("sma", 7), sig=tb.signature(t))          # ps1.2 already, but no alt
    state = {tid: {"sig": tb.signature(t), "complete": True, "covers": True}}
    db = _Db()
    now = pd.Timestamp("2026-10-04 12:00", tz=ET)
    tb.publish(db, "u", [(tid, t)], log=lambda *_: None, state=state, fills=({}, {}), now=now)
    assert db.store[key]["pointScore"]["alt"]["ema"]["total"] == 5
    n = len(calls)
    t["pointScore"] = db.store[key]["pointScore"]                        # has both now: left alone
    tb.publish(db, "u", [(tid, t)], log=lambda *_: None, state=state, fills=({}, {}), now=now)
    assert len(calls) == n


# ── the 200 lines, against the REAL scorer ──────────────────────────────────────────────────
@pytest.fixture
def scorer(monkeypatch):
    """tools/point_score.py on synthetic bars: 3 days of 1-minute bars from 2026-09-28 18:00 ET with a
    10-second capture on the last 2 hours, no contract rolls."""
    mod = tb._point_score_module()
    if not tb._ps_has_both(mod):
        pytest.skip("scorer older than ps1.2")
    rng = np.random.default_rng(7)
    t0 = int(pd.Timestamp("2026-09-28 18:00", tz=ET).timestamp())
    n = 3 * 1380
    t = t0 + 60 * np.arange(n, dtype="int64")
    c = 20000 + np.cumsum(rng.normal(0, 2, n)).round(2)
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) + 1, np.minimum(o, c) - 1
    v = rng.integers(10, 500, n).astype(float)
    t10 = np.arange(t[-1] - 7200 + 60, t[-1] + 60, 10, dtype="int64")
    c10 = 20000 + np.cumsum(rng.normal(0, 0.5, len(t10))).round(2)
    bars = mod.Bars(t, o, h, l, c, v, root="NQ", asset="futures", t10=t10, c10=c10, switches=[])
    monkeypatch.setattr(mod, "load_bars", lambda root, *a, **k: bars)
    monkeypatch.setattr(tb, "_point_score_module", lambda: mod)
    monkeypatch.setattr(tb, "_ps_fresh_bars", lambda m: None)
    monkeypatch.setattr(tb, "_MA_CACHE", {})
    return types.SimpleNamespace(mod=mod, bars=bars, t=t, c=c, t10=t10, c10=c10)


def _pk(times, step, shift=0.0):
    t0 = int(times[0])
    return {"t0": t0, "step": step, "s": ";".join(f"{(int(x) - t0) // step},1,1,1,1,1" for x in times), "shift": shift}


def _unpack(line):
    """The web's decoder: one slot per bar from t0, first value in hundredths, then changes; empty = no value."""
    out, cur = {}, None
    for i, x in enumerate(line["d"].split(",")):
        if x == "":
            continue
        cur = int(x) if cur is None else cur + int(x)
        out[line["t0"] + i * line["step"]] = cur / 100
    return out


def test_the_line_packing_round_trips_across_gaps():
    times, vals = [600, 660, 720, 900, 960], [100.0, 100.25, 99.99, 101.5, 101.5]
    pk = tb._pack_line(times, vals, 60)
    assert pk["d"] == "10000,25,-26,,,151,0"
    assert _unpack(pk) == dict(zip(times, vals))


def test_the_1m_and_5m_lines_pass_through_the_scores_own_reference(scorer):
    mod, t = scorer.mod, scorer.t
    win = t[-900:]                                                      # the chart's 1m window
    doc = {"inst": "NQ", "b1m": _pk(win, 60), "b10s": _pk(scorer.t10[-300:], 10)}
    ml = tb.ma_lines(_trade(), doc)
    assert ml["v"] == mod.VERSION and ml["len"] == 200
    sig = int(t[-120])                                                  # signal candle: 2 h before the end
    fill = pd.Timestamp(sig + 65, unit="s", tz="UTC").tz_convert(ET).strftime("%Y-%m-%d %H:%M:%S")
    for ma in ("sma", "ema"):
        rec = mod.score_trade({"sym": "MNQ", "side": "LONG", "fill": fill}, bars=scorer.bars, ma=ma)
        ref = {p["k"]: p["ref"] for p in rec["points"]}
        l1, l5 = _unpack(ml[ma]["1m"]), _unpack(ml[ma]["5m"])
        assert l1[sig] == pytest.approx(ref["ma200_1m"], abs=0.006)
        b5 = sig // 300 * 300 - 300                                     # the 5m bar BEFORE the one holding S
        assert l5[b5] == pytest.approx(ref["ma200_5m"], abs=0.006)
        assert min(l1) >= int(win[0]) and max(l1) <= int(win[-1])       # only the chart's own window
    sma1 = _unpack(ml["sma"]["1m"])
    k = len(t) - 500
    assert sma1[int(t[k])] == pytest.approx(scorer.c[k - 199:k + 1].mean(), abs=0.006)


def test_the_10s_line_is_the_capture_average_and_lines_follow_the_chart_shift(scorer):
    doc = {"inst": "NQ", "b1m": _pk(scorer.t[-60:], 60, shift=-1.25), "b10s": _pk(scorer.t10[-300:], 10, shift=0.5)}
    ml = tb.ma_lines(_trade(), doc)
    l10 = _unpack(ml["sma"]["10s"])
    j = len(scorer.t10) - 10
    assert l10[int(scorer.t10[j])] == pytest.approx(scorer.c10[j - 199:j + 1].mean() + 0.5, abs=0.006)
    k = len(scorer.t) - 5
    l1 = _unpack(ml["sma"]["1m"])
    assert l1[int(scorer.t[k])] == pytest.approx(scorer.c[k - 199:k + 1].mean() - 1.25, abs=0.006)
    # 720 capture bars: the 10s EMA never reaches the score's 600-bar warm-up inside this window's start
    e10 = _unpack(ml["ema"]["10s"])
    assert min(e10) >= int(scorer.t10[599])


def test_lines_over_the_size_cap_drop_the_10s_ones_first(monkeypatch):
    monkeypatch.setattr(tb, "DOC_CAP_BYTES", 400)
    doc = {"b1m": {"s": "x" * 100}}
    ml = {"v": "ps1.2", "len": 200, "sma": {"1m": {"s": "1" * 50}, "10s": {"s": "1" * 300}}, "ema": {}}
    tb._attach_ma(doc, ml)
    assert "10s" not in doc["ma"]["sma"] and "1m" in doc["ma"]["sma"]
    doc2 = {"b1m": {"s": "x" * 500}}
    tb._attach_ma(doc2, {"v": "ps1.2", "sma": {"1m": {"s": "1"}}, "ema": {}})
    assert "ma" not in doc2
