"""MISC_AUCHABIT_1_0 (opus hunt strategy 86, cell 86a): defaults = the hunt cell and the search space is the declared
1,440 combos; the plugin gate lets it through; no panel -> no trades; and, when the pinned panel is on this machine,
the engine contract holds on a 2018 slice, the picks never read a field known only after the 15:50 entry print, and
the 2018 picks and daily net match the hunt's 86a. Everything runs on the panel CUT AT 2025-06-30
(tools/misc_auchabit_parity.load_plugin_sealed); the synthetic SPY clock never goes past 2018."""
import importlib.util
import os
import pickle
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_AUCHABIT_1_0.py")
HUNT = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S86/"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_auchabit_parity as P  # noqa: E402

PINNED = ("notional", "spread_cents", "fee_bps")
REQUIRED_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins", "losses"}


@pytest.fixture(scope="module")
def sealed():
    return P.load_plugin_sealed()


def _fresh(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clock(first, last):
    """A SPY-like 5m RTH master (09:30 .. 15:55 bars, US/Eastern) over the business days first..last. Only its clock
    matters to the plugin; prices are a seeded walk."""
    days = pd.bdate_range(first, last)
    idx = pd.DatetimeIndex([d + pd.Timedelta(minutes=570 + 5 * j) for d in days for j in range(78)]).tz_localize(
        "US/Eastern")
    rng = np.random.default_rng(86)
    close = 270 + rng.normal(0, 0.1, len(idx)).cumsum()
    return {"open": close + rng.normal(0, 0.02, len(idx)), "high": close + 0.05, "low": close - 0.05, "close": close,
            "volume": np.full(len(idx), 1000.0), "day_id": np.repeat(np.arange(len(days)), 78).astype("int64"),
            "index": idx, "meta": {"name": "SPY", "roll_mode": "none"}}


def test_defaults_are_cell_86a_and_the_space_is_1440(sealed):
    mod, _ = sealed
    d = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    assert d == {"notional": 100000, "spread_cents": 1.0, "fee_bps": 0.3, "period_len": 60, "k": 5, "min_price": 40,
                 "weekday_habit": False, "legs": 0}
    for k, v in mod.DEFAULT_PARAMS.items():                     # every default sits on its own grid
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
            assert abs((v["default"] - v["min"]) / v["step"] - round((v["default"] - v["min"]) / v["step"])) < 1e-9, k
        if "hard_min" in v:
            assert v["hard_min"] <= v["min"] and v["max"] <= v["hard_max"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 86a)"] == {k: [v] for k, v in d.items() if k not in PINNED}
    from augur_engine.auto import _auto_space_from_params
    n = {}
    for name, spec in _auto_space_from_params(mod.DEFAULT_PARAMS).items():
        if spec[0] == "cat":
            n[name] = len(spec[1])
        elif spec[0] == "int":
            n[name] = (spec[2] - spec[1]) // spec[3] + 1
        else:
            n[name] = int(round((spec[2] - spec[1]) / spec[3])) + 1
    assert all(n[k] == 1 for k in PINNED)
    assert n == {"notional": 1, "spread_cents": 1, "fee_bps": 1, "period_len": 6, "k": 8, "min_price": 5,
                 "weekday_habit": 2, "legs": 3}
    assert int(np.prod(list(n.values()))) == 1440


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_no_panel_no_trades_and_a_foreign_panel_is_refused(tmp_path):
    arr = _clock("2018-06-04", "2018-06-08")
    mod = _fresh("misc_auchabit_nopanel")
    mod.PANEL_PATH = str(tmp_path / "absent.npz")
    assert mod.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], index=arr["index"],
                            return_trades=True) is None
    bad = tmp_path / "foreign.npz"
    np.savez(bad, dates=np.array([20180604]))
    mod2 = _fresh("misc_auchabit_foreign")
    mod2.PANEL_PATH = str(bad)
    with pytest.raises(RuntimeError, match="not the pinned build"):
        mod2.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], index=arr["index"])


def test_engine_contract_on_a_sealed_2018_slice(sealed):
    mod, a = sealed
    if a is None:
        pytest.skip("pinned panel not on this machine")
    from augur_engine import run_backtest
    arr = _clock("2018-06-04", "2018-06-29")                     # 20 sessions, no holiday
    r = run_backtest(mod, arrays=arr, params={}, return_trades=True)
    assert REQUIRED_KEYS <= set(r)
    dd, net = mod._daily(mod._CACHE["panel"], 100000, 1.0, 0.3, 60, 5, 40, False, 0)
    want = {int(x): v for x, v in zip(dd, net) if 20180604 <= x <= 20180629}
    idx = arr["index"]
    tr = r["trades"]
    assert len(tr) == len(want) >= 18
    for t in tr:
        e, x = idx[t[0]], idx[t[1]]
        day = e.year * 10000 + e.month * 100 + e.day
        assert (e.hour, e.minute) == (15, 50) and (x.hour, x.minute) == (15, 55) and x.normalize() == e.normalize()
        assert t[2] == want[day] and np.isfinite(t[2])
    assert r["num_trades"] == len(tr) and abs(r["total_pnl"] - sum(want.values())) < 1e-6
    # the contract's look-ahead test: removing the last 3 sessions leaves every earlier trade identical
    cut = int((arr["day_id"] < 17).sum())
    short = {k: (v[:cut] if k in ("open", "high", "low", "close", "volume", "day_id", "index") else v)
             for k, v in arr.items()}
    r2 = run_backtest(mod, arrays=short, params={}, return_trades=True)
    assert {(t[0], t[1], round(t[2], 6)) for t in r2["trades"]} == {(t[0], t[1], round(t[2], 6)) for t in tr
                                                                   if t[1] < cut}
    r3 = run_backtest(mod, arrays=arr, params={}, return_trades=True)
    assert (r3["num_trades"], r3["total_pnl"]) == (r["num_trades"], r["total_pnl"])
    # a session without its 15:50 bar (a half day on the master) gives no trade
    keep = ~((arr["day_id"] == 0) & (idx.hour * 60 + idx.minute >= 950))
    half = {k: (v[keep] if k in ("open", "high", "low", "close", "volume", "day_id", "index") else v)
            for k, v in arr.items()}
    r4 = run_backtest(mod, arrays=half, params={}, return_trades=True)
    assert 20180604 in want and r4["num_trades"] == len(tr) - 1


def _scramble(rng, x, rows, blank=True):
    y = x[rows].astype(np.float64) * rng.lognormal(0.0, 0.05, x[rows].shape)
    if blank:
        y[rng.random(y.shape) < 0.1] = np.nan
    x[rows] = y.astype(x.dtype)


@pytest.mark.parametrize("cfg", [dict(period_len=60, k=5, min_price=40, weekday_habit=False),
                                 dict(period_len=20, k=3, min_price=0, weekday_habit=True),
                                 dict(period_len=120, k=10, min_price=80, weekday_habit=False)])
def test_picks_never_read_a_field_known_after_the_entry_print(sealed, cfg):
    """For a test session T: every field known only after T's 15:50 entry print - T's own 15:50-bar close, official
    close and raw close, the entry print's VALUE, and every price and FULL flag of later sessions - is scrambled (values
    noised, 10 pct blanked). The picks of every session up to T must not move; T's P&L must (the scramble reaches the
    fill). Control: scrambling the 60 sessions BEFORE T must move T's picks."""
    mod, a = sealed
    if a is None:
        pytest.skip("pinned panel not on this machine")
    rng = np.random.default_rng(8686)
    p0 = mod._prepare(**a)
    base = {int(p0["dates"][i]): (hi.tolist(), lo.tolist()) for i, hi, lo in mod._picks(p0, **cfg)}
    dd0, net0 = mod._daily(p0, 100000, 1.0, 0.3, legs=0, **cfg)
    moved = 0
    for T in (20180615, 20210310, 20240920):
        t = int(np.flatnonzero(a["dates"] == T)[0])
        assert a["full"][t] and T in base
        b = {key: (v if key == "names" else v.copy()) for key, v in a.items()}
        for key in ("o50", "c50", "dc", "raw"):
            _scramble(rng, b[key], slice(t + 1, None))
        for key in ("c50", "dc", "raw"):
            _scramble(rng, b[key], slice(t, t + 1))
        _scramble(rng, b["o50"], slice(t, t + 1), blank=False)     # the entry print's value; its presence is known
        b["full"][t + 1:] = rng.random(len(b["full"]) - t - 1) < 0.5
        p1 = mod._prepare(**b)
        got = {int(p1["dates"][i]): (hi.tolist(), lo.tolist()) for i, hi, lo in mod._picks(p1, **cfg)
               if p1["dates"][i] <= T}
        assert got == {d: v for d, v in base.items() if d <= T}, T
        dd1, net1 = mod._daily(p1, 100000, 1.0, 0.3, legs=0, **cfg)
        assert net1[dd1 == T][0] != net0[dd0 == T][0]
        c = {key: (v if key == "names" else v.copy()) for key, v in a.items()}
        fr = np.flatnonzero(a["full"][:t])[-60:]
        for key in ("o50", "dc"):
            _scramble(rng, c[key], fr, blank=False)
        p2 = mod._prepare(**c)
        ctl = {int(p2["dates"][i]): (hi.tolist(), lo.tolist()) for i, hi, lo in mod._picks(p2, **cfg)
               if p2["dates"][i] == T}
        moved += ctl.get(T) != base[T]
    assert moved >= 2                                               # the check can see a real input change


def test_2018_picks_and_daily_net_match_hunt_86a(sealed):
    mod, a = sealed
    if a is None or not os.path.exists(HUNT + "trades_86a.csv") or not os.path.exists(HUNT + "series.pkl"):
        pytest.skip("pinned panel or hunt files not on this machine")
    T = P.plugin_picks(mod)
    T = T[(T.d >= 20180101) & (T.d <= 20181231)].sort_values(["d", "side", "name"]).reset_index(drop=True)
    H = P.hunt_trades("86a")
    H = H[(H.d >= 20180101) & (H.d <= 20181231)].sort_values(["d", "side", "name"]).reset_index(drop=True)
    assert len(T) == len(H) > 2000
    assert (T[["d", "name", "side"]].values == H[["d", "name", "side"]].values).all()
    assert ((T.R.values == H.R.values) | (np.isnan(T.R.values) & np.isnan(H.R.values))).all()
    dd, net = mod._daily(mod._CACHE["panel"], 100000, 1.0, 0.3, 60, 5, 40, False, 0)
    got = pd.Series(net, index=pd.to_datetime(dd.astype(str))).loc["2018-01-01":"2018-12-31"]
    want = pickle.load(open(HUNT + "series.pkl", "rb"))["86a"].loc["2018-01-01":"2018-12-31"]
    want = want[want != 0]
    assert list(got.index) == list(want.index)
    assert np.abs(got.values - want.values).max() < 1e-6
