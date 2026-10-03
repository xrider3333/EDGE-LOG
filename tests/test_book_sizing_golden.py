"""GOLDEN: book-level sizing must not move a single figure of a book that does not ask for it.

The book engine was refactored for book_sizing (2026-10-03): the closed-trade loop moved into
_closed_series and _leg_trades can keep re-pricing state. This test loads the engine as it was BEFORE
that change (git, commit 65a5352) and drives both versions through the REAL _leg_trades - only the
data and the strategy run are faked - on the cases that have bitten books before:
  * a tz-aware US/Eastern tape that crosses the March DST switch, with EVENING fills that the engine's
    UTC-truncated stamp moves to the next day (book.py 'WHICH DAY IS THIS TRADE ON?');
  * a multi-day points leg valued daily (_mtm_increments);
  * a gated leg (per-trade sizes from api.paper_gate.apply_gate);
  * a dollar-P&L leg that values its own open positions (PNL_UNITS = 'usd' + mark_open_trades).
Pass = the whole result (every key, every number) is identical with no book_sizing block, and a block
held at x1.0 reproduces every scored figure. The test then checks causality end to end: rewriting the
P&L of trades that enter after day D does not move the size of any trade entering on or before D.
"""
import json
import subprocess
import sys
import types

import numpy as np
import pandas as pd
import pytest

import augur_engine.book as NEW
import augur_engine.book_sizing as BS

BASE = "65a5352"          # main before book-level sizing


def _load_base():
    try:
        src = subprocess.run(["git", "show", f"{BASE}:augur_engine/book.py"], capture_output=True,
                             text=True, check=True).stdout
    except Exception as e:                                   # shallow clone / no git: nothing to compare against
        pytest.skip(f"base engine {BASE} not available: {e}")
    mod = types.ModuleType("augur_engine._book_golden_base")
    mod.__package__ = "augur_engine"
    sys.modules[mod.__name__] = mod
    exec(compile(src, "book_base.py", "exec"), mod.__dict__)
    return mod


def _tape():
    idx = pd.date_range("2021-02-22 00:00", "2021-04-30 23:30", freq="30min", tz="US/Eastern")
    idx = idx[idx.dayofweek != 5]                            # no Saturdays; Sunday evening trades
    rng = np.random.default_rng(5)
    close = 13000.0 + np.cumsum(rng.normal(0, 8, len(idx)))
    return {"index": idx, "open": close - 1, "high": close + 4, "low": close - 4, "close": close,
            "volume": np.ones(len(idx)), "day_id": np.asarray(idx.tz_localize(None).normalize().factorize()[0]),
            "meta": {"name": "synthetic"}}


ARR = _tape()


def _bar(ts):
    return int(ARR["index"].get_indexer([pd.Timestamp(ts, tz="US/Eastern")])[0])


def _trades(kind, bump_after=None):
    """(entry_bar, exit_bar, pts, side, entry_px). bump_after rewrites pts of trades entering after it."""
    rng = np.random.default_rng({"IN.py": 1, "ON.py": 2, "GT.py": 3, "USD.py": 4}[kind])
    out = []
    for d in pd.bdate_range("2021-02-23", "2021-04-26"):
        if kind in ("IN.py", "GT.py"):
            e, x = _bar(f"{d.date()} 10:00"), _bar(f"{d.date()} 15:00")
        elif kind == "ON.py":
            if d.dayofweek not in (0, 3):
                continue
            e, x = _bar(f"{d.date()} 21:00"), _bar(f"{(d + pd.Timedelta(days=3)).date()} 22:00")    # evening fills
        else:
            if d.dayofweek != 2:
                continue
            e, x = _bar(f"{d.date()} 11:00"), _bar(f"{(d + pd.Timedelta(days=5)).date()} 11:30")
        if e < 0 or x < 0:
            continue
        side = 1 if rng.random() < 0.6 else -1
        pts = float(side * (ARR["close"][x] - ARR["close"][e]) - 0.5)
        if kind == "USD.py":
            pts *= 20.0                                       # dollars, its own sizing
        if bump_after is not None and ARR["index"][e].tz_localize(None) > pd.Timestamp(bump_after):
            pts = pts * 7.0 + 1234.0
        out.append((e, x, pts, side, float(ARR["close"][e])))
    return out


class _UsdMod:
    PNL_UNITS = "usd"

    @staticmethod
    def mark_open_trades(trades, o, h, l, c, **kw):
        out = []
        ends = np.flatnonzero(ARR["day_id"][1:] != ARR["day_id"][:-1])
        for t in trades:
            e, x, side = int(t[0]), int(t[1]), float(t[3])
            out.append([(int(k), side * (float(c[k]) - float(t[4])) * 20.0) for k in ends if e <= k < x])
        return out


def _patch(monkeypatch, mods, bump_after=None):
    def run_backtest(strategy, arrays=None, params=None, cost_pts=0.0, return_trades=True):
        return {"trades": _trades(strategy, bump_after)}

    def find_master(inst, tf, sess, src):
        return {"name": "synthetic", "source": src}

    def load_master_arrays(master, date_from=None, date_to=None):
        return ARR

    def load_strategy(name):
        if name == "USD.py":
            return _UsdMod
        raise ImportError(name)

    def apply_gate(arr, raw_trades, cfg):
        return [(t, (1.5 if i % 3 == 0 else 0.75)) for i, t in enumerate(raw_trades)], {"ok": True, "size_norm": 1.0}

    for m in mods:
        monkeypatch.setattr(m, "run_backtest", run_backtest)
        monkeypatch.setattr(m, "find_master", find_master)
        monkeypatch.setattr(m, "load_master_arrays", load_master_arrays)
    import augur_engine.strategies as S
    import api.paper_gate as PG
    monkeypatch.setattr(S, "load_strategy", load_strategy)
    monkeypatch.setattr(PG, "apply_gate", apply_gate)


LEGS = [
    {"strategy": "IN.py", "instrument": "NQ", "timeframe": "30m", "session": "eth", "source": "s1", "cost_pts": 0.5, "mult": 20, "weight": 1, "params": {"a": 1}},
    {"strategy": "ON.py", "instrument": "NQ", "timeframe": "30m", "session": "eth", "source": "s2", "cost_pts": 0.5, "mult": 20, "weight": 1, "params": {"a": 1}},
    {"strategy": "GT.py", "instrument": "ES", "timeframe": "30m", "session": "eth", "source": "s3", "cost_pts": 0.3, "mult": 50, "weight": 3, "params": {"a": 1},
     "gate": {"mode": "tilt"}},
    {"strategy": "USD.py", "instrument": "NQ", "timeframe": "30m", "session": "eth", "source": "s4", "cost_pts": 0.0, "mult": 1, "weight": 1, "params": {"a": 1}},
]
KW = dict(date_from="2021-02-22", date_to="2021-04-30", lockbox_months=1)


def _dump(r):
    return json.dumps(r, sort_keys=True, default=str)


def test_no_block_is_byte_identical_to_the_engine_before_book_sizing(monkeypatch):
    base = _load_base()
    _patch(monkeypatch, [base, NEW])
    a, b = base.run_book(LEGS, **KW), NEW.run_book(LEGS, **KW)
    assert b["book"]["mtm"]["marked_trades"] > 0 and b["book"]["day_rule"].get("session_day")
    assert _dump(a) == _dump(b)


def test_a_unit_block_reproduces_every_scored_figure_through_the_real_leg_runner(monkeypatch):
    base = _load_base()
    _patch(monkeypatch, [base, NEW])
    a = base.run_book(LEGS, **KW)
    u = NEW.run_book(LEGS, book_sizing={"mode": "vt", "lo": 1.0, "hi": 1.0}, **KW)
    for k in ("whole", "pre_lockbox", "lockbox", "slices", "worst_stretch", "worst_stretch_lockbox"):
        assert _dump(u["book"][k]) == _dump(a["book"][k]), k
    for k in ("whole", "pre_lockbox", "lockbox", "worst_stretch"):
        assert _dump(u["book"]["mtm"][k]) == _dump(a["book"]["mtm"][k]), k
    assert _dump(u["book"]["day_rule"]) == _dump(a["book"]["day_rule"])
    assert u["book"]["book_sizing"]["raw_twin"]["whole"] == a["book"]["whole"]


def test_sizing_is_causal_end_to_end(monkeypatch):
    """The live VT line sizes a trade from the book before its entry day; nothing that happens on or
    after that day may move it. Rewrite every trade entering after D and compare sizes up to D."""
    D = "2021-04-12"
    states = {}
    for tag, bump in (("plain", None), ("bumped", D + " 23:59")):
        _patch(monkeypatch, [NEW], bump_after=bump)
        infos, mtms = [], []
        for leg in LEGS:
            tr, info = NEW._leg_trades(dict(leg), KW["date_from"], KW["date_to"], keep_state=True)
            mtms.append(info.pop("_mtm_day"))
            infos.append(info)
        cfg = BS.check_config({"mode": "vt", "lookback": 5, "ref": 10})          # short windows so D is past warm-up
        rebuilt, rep = BS.apply(cfg, LEGS, infos, mtms, KW["date_from"], KW["date_to"])
        states[tag] = (infos, rebuilt, rep)
    (i0, r0, rep0), (i1, r1, _) = states["plain"], states["bumped"]
    assert rep0["first_sized_day"] < D
    cut = np.datetime64(D, "D")
    n_checked = 0
    for k in range(len(LEGS)):
        st0, st1 = i0[k]["_state"], i1[k]["_state"]
        for j, ((t0, s0), (t1, s1)) in enumerate(zip(st0["sized"], st1["sized"])):
            if BS.entry_day(st0, t0) > cut:
                continue
            assert t0 == t1                                    # the trade itself was not rewritten
            assert r0[k][0][j][1] == pytest.approx(r1[k][0][j][1], abs=1e-9), (k, j)
            n_checked += 1
    assert n_checked > 40
