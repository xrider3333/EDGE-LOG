"""MISC_NIGHTPERSIST_1_0 (opus hunt strategy 83, NIGHTPERSIST-120, cell 83d): defaults = the hunt cell, the plugin gate
lets it through, the contract's synthetic (non-RTH) arrays never touch the panel, no panel -> no trades, a gap in the
clock never makes a two-night hold, and - when the pinned panel and the hunt files are on this machine - a contract
smoke on an RTH clock (15:55 of t -> 09:30 of t+1, one mark at the entry close), the 2019 nights equal the harness's
trades_83d.csv, and no pick moves when every print known only after the entry is scrambled or blanked (and the same
check DOES catch a variant that peeks at the holding night).
Everything that reads prices runs on the panel CUT AT 2025-06-30 (tools/misc_nightpersist_parity.load_plugin_sealed)."""
import itertools
import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_NIGHTPERSIST_1_0.py")
HUNT_TRADES = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S83/trades_83d.csv"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_nightpersist_parity as P  # noqa: E402

PINNED = ("notional", "spread_cents", "fee_bps", "min_names")
KNOBS = ("lookback", "k", "min_price", "beta_resid", "tug", "min_names")
CELL_83D = {"notional": 100000, "spread_cents": 1.0, "fee_bps": 0.3, "min_names": 40, "lookback": 120, "k": 10,
            "min_price": 40, "beta_resid": False, "tug": False, "legs": 0}


def _defaults(mod):
    return {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}


def _rth_arrays(days):
    """A SPY-like 5m RTH clock (09:30 .. 15:55, 78 bars) on the given yyyymmdd sessions."""
    rng = np.random.default_rng(83)
    stamps = [pd.Timestamp(str(d)) + pd.Timedelta(minutes=570 + 5 * j) for d in days for j in range(78)]
    idx = pd.DatetimeIndex(stamps).tz_localize("US/Eastern")
    n = len(idx)
    close = 300 + rng.normal(0, 0.1, n).cumsum()
    openp = close + rng.normal(0, 0.05, n)
    return {"open": openp, "high": np.maximum(openp, close) + 0.05, "low": np.minimum(openp, close) - 0.05,
            "close": close, "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(len(days)), 78),
            "index": idx, "meta": {"name": "SYN", "roll_mode": "none"}}


def test_defaults_are_cell_83d():
    mod = P.fresh_plugin()
    d = _defaults(mod)
    assert d == CELL_83D
    for k, v in mod.DEFAULT_PARAMS.items():                     # every default sits inside its range and hard fence
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
            assert v["hard_min"] <= v["min"] and v["max"] <= v["hard_max"], k
            assert (v["default"] - v["min"]) % v["step"] == 0, k  # the hunt cell is ON the grid
        if k in PINNED:
            assert v["min"] == v["max"] == v["default"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 83d)"] == {k: [v] for k, v in d.items()
                                                                    if k not in PINNED[:3]}
    from augur_engine.auto import _auto_space_from_params, _collapse
    space = _auto_space_from_params(mod.DEFAULT_PARAMS)
    axes = {}
    for name, spec in space.items():
        if spec[0] == "cat":
            axes[name] = list(spec[1])
        else:
            axes[name] = [spec[1] + spec[3] * i for i in range(int(round((spec[2] - spec[1]) / spec[3])) + 1)]
    grid = [dict(zip(axes, combo)) for combo in itertools.product(*axes.values())]
    assert len(grid) == 8400
    distinct = {tuple(sorted(_collapse(g, mod.DEFAULT_PARAMS).items())) for g in grid}
    assert len(distinct) == 6300                                # tug collapses to off without beta_resid
    cells = [dict(d, lookback=120), dict(d, lookback=120, beta_resid=True), dict(d, lookback=250, beta_resid=True),
             dict(d, lookback=60, beta_resid=True, tug=True)]    # 83d, 83a, 83b, 83c
    keys = {tuple(sorted(g.items())) for g in grid}
    for c in cells:
        assert tuple(sorted(c.items())) in keys, c


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_synthetic_contract_arrays_never_touch_the_panel():
    """tests/test_strategy_contract.py hands every plugin a continuous 5m tape dated 2026-03 (inside the engine's
    lockbox). No day of it ends on a 15:55 bar, so the plugin returns None BEFORE it opens the panel."""
    rng = np.random.default_rng(7)                                # the contract test's _make_arrays(), 10 x 78 bars
    n = 780
    close = 15000 + rng.normal(0, 1, n).cumsum()
    idx = pd.date_range("2026-03-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    mod = P.fresh_plugin()
    r = mod.run_backtest(close, close + 1, close - 1, close, np.full(n, 1000.0),
                         np.repeat(np.arange(10), 78).astype("int64"), idx, return_trades=True)
    assert r is None
    assert "panel" not in mod._CACHE


def test_no_panel_no_trades():
    mod = P.fresh_plugin()
    mod.PANEL_PATH = os.path.join(REPO, "no_such_dir", "nightpersist_panel_v1.npz")
    a = _rth_arrays([20190304, 20190305, 20190306])
    from augur_engine import run_backtest
    assert run_backtest(mod, arrays=a, params={}, return_trades=True) is None
    assert mod._CACHE.get("panel", "missing") is None
    assert mod.mark_open_trades([(77, 78, 1.0, 1, 1.0, 1.0)], a["open"], a["high"], a["low"], a["close"],
                                index=a["index"]) == [[]]


def test_contract_smoke_on_an_rth_clock():
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    days = [int(d) for d in p["days"] if 20190101 <= d <= 20191231]
    a = _rth_arrays(days)
    from augur_engine import run_backtest
    r = run_backtest(mod, arrays=a, params={}, return_trades=True)
    assert {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins",
            "losses"} <= set(r)
    want = P.plugin_nights(mod, p)
    want = want[(want["entry"] >= 20190101) & (want.index <= 20191231)]   # the clock's last day has no next session
    assert r["num_trades"] == len(want) > 200
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    for t in r["trades"]:
        e, x = idx[t[0]], idx[t[1]]
        assert (e.hour, e.minute) == (15, 55) and (x.hour, x.minute) == (9, 30) and x.date() > e.date()
        row = want.loc[int(x.strftime("%Y%m%d"))]
        assert int(row["entry"]) == int(e.strftime("%Y%m%d"))
        assert abs(t[2] - row["net"]) < 1e-9
    marks = mod.mark_open_trades(r["trades"], a["open"], a["high"], a["low"], a["close"], index=a["index"])
    assert len(marks) == len(r["trades"])
    for mm, t in zip(marks, r["trades"]):
        row = want.loc[int(idx[t[1]].strftime("%Y%m%d"))]
        assert len(mm) == 1 and mm[0][0] == t[0] and abs(mm[0][1] + 0.5 * row["c"]) < 1e-9 and mm[0][1] < 0


def test_a_gap_in_the_clock_never_makes_a_two_night_hold():
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    days = [int(d) for d in p["days"] if 20190301 <= d <= 20190329]
    nights = P.plugin_nights(mod, p)
    held = [d for d in days[:-1] if d in set(nights["entry"])]
    assert len(held) >= 15
    gone = held[5]                                                # drop the session after an entry from the clock
    nxt = days[days.index(gone) + 1]
    a = _rth_arrays([d for d in days if d != nxt])
    from augur_engine import run_backtest
    r = run_backtest(mod, arrays=a, params={}, return_trades=True)
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    entries = {int(idx[t[0]].strftime("%Y%m%d")) for t in r["trades"]}
    assert gone not in entries and nxt not in entries
    assert len(entries) == len(held) - 2 + (0 if nxt in held else 1)


def test_2019_nights_match_harness_83d():
    mod, p = P.load_plugin_sealed()
    if p is None or not os.path.exists(HUNT_TRADES):
        pytest.skip("pinned panel or hunt trades file not on this machine")
    got = P.plugin_nights(mod, p)
    got = got[(got.index >= 20190101) & (got.index <= 20191231)]
    H = P.hunt_trades("83d")
    H = H[(H.index >= 20190101) & (H.index <= 20191231)]
    assert list(got.index) == list(H.index) and len(H) > 200
    assert (got["n"].astype(int).to_numpy() == H["n"].astype(int).to_numpy()).all()
    assert (got["miss"].astype(int).to_numpy() == H["miss"].astype(int).to_numpy()).all()
    for col in ("gl", "gs", "cl", "cs", "net"):
        assert (got[col] - H[col]).abs().max() < 1e-6, col


def _scrambled_cut(cut, i, rng, blank):
    """Rows 0 .. i+1 of the sealed arrays (every later session dropped); row i's close prints (split close, raw
    close, SPY's close) and EVERY print of row i+1 scaled by random factors or, with `blank`, partly removed."""
    c = {key: (v[:i + 2].copy() if key in P.SESSION_KEYS else v) for key, v in cut.items()}

    def hit(key, row):
        x = c[key][row]
        if np.ndim(x) == 0:
            c[key][row] = np.nan if blank and rng.random() < 0.5 else x * rng.uniform(0.5, 1.5)
            return
        y = (x * rng.uniform(0.5, 1.5, x.shape)).astype(x.dtype)
        if blank:
            y[rng.random(x.shape) < 0.3] = np.nan
        c[key][row] = y

    for key in ("c", "r", "spy_close"):                           # the entry prints (known at the close)
        hit(key, i)
    for key in ("o", "c", "r", "spy_open", "spy_close"):          # the exit session: every print
        hit(key, i + 1)
    return c


def _moved(mod, p, cut, kn, n_rows=8, seed=1083):
    """(sessions whose picks or eligible count moved, sessions whose net moved) over sampled traded sessions, both
    scramble modes. Picks are the plugin's _picks (before the after-pick close-print drop)."""
    args = [kn[x] for x in KNOBS]
    L, S, n = mod._picks(p, *args)
    net0 = mod._book(p, **kn)["net"]
    rows = np.flatnonzero(L.any(axis=1).to_numpy())
    rows = rows[np.linspace(0, len(rows) - 1, n_rows).astype(int)]
    rng = np.random.default_rng(seed)
    moved, net_moved = set(), set()
    for i in rows:
        for blank in (False, True):
            p2 = mod._frames(_scrambled_cut(cut, i, rng, blank))
            L2, S2, n2 = mod._picks(p2, *args)
            if not ((L2.iloc[i] == L.iloc[i]).all() and (S2.iloc[i] == S.iloc[i]).all()
                    and int(n2.iloc[i]) == int(n.iloc[i])):
                moved.add(int(i))
            day = int(p["days"][i])
            net2 = mod._book(p2, **kn)["net"]
            if day not in net2.index or abs(float(net2[day]) - float(net0[day])) > 1e-6:
                net_moved.add(int(i))
    return moved, net_moved, len(rows)


@pytest.mark.parametrize("cell", ["83d", "83a", "83c"])
def test_picks_ignore_prints_known_after_the_entry(cell):
    """Look-ahead check. For sampled traded sessions t: drop every session after t+1, scramble (or partly blank)
    t's official closes (split and raw) and SPY's close, and every print of t+1 (the exit open included), then
    rebuild the frames. The long / short picks and the day's eligible count must not move, while the night's net
    does (the scramble reached the PnL)."""
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    cut = P.sealed_arrays(mod)
    kn = P.defaults(mod, **({"83d": {}} | P.CELLS)[cell])
    moved, net_moved, n_rows = _moved(mod, p, cut, kn)
    assert moved == set(), sorted(moved)
    assert len(net_moved) >= n_rows - 1


def test_the_lookahead_check_catches_a_peeking_variant(monkeypatch):
    """The same check on a deliberately broken signal that adds tonight's holding return (exit open of t+1 over
    the close of t) to S: the picks must move on (nearly) every sampled session."""
    mod, p = P.load_plugin_sealed()
    if p is None:
        pytest.skip("pinned panel not on this machine")
    cut = P.sealed_arrays(mod)
    real = mod._signal

    def peeking(pp, lookback, min_price, beta_resid, tug):
        return real(pp, lookback, min_price, beta_resid, tug) + pp["hold"]

    monkeypatch.setattr(mod, "_signal", peeking)
    moved, _, n_rows = _moved(mod, p, cut, P.defaults(mod))
    assert len(moved) >= n_rows - 1
