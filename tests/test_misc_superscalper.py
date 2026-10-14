"""Fast synthetic checks for MISC_SUPERSCALPER_1_0 (TradingView NQ/MNQ Super Scalper port)
and its parity harness tools/superscalper_parity.py.

No real data is touched: random-walk 1-minute bars, the walk kernel driven by forced signal
arrays, and the real roll table only for the seam guard. What is pinned:
  * the full pipeline runs (every port knob) and is deterministic;
  * entries fill at the OPEN of the bar AFTER the signal bar, never earlier;
  * open tickets never exceed the pyramiding cap;
  * every trade exits on or after its entry bar;
  * no trade holds across a contract switch (seam guard);
  * the compiled kernels give the same trades as the interpreted ones;
  * the harness refuses lockbox windows and matches TV trades by side + entry time.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

from augur_engine import rolls as R
from augur_engine.strategies import load_strategy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = load_strategy("MISC_SUPERSCALPER_1_0.py")


def _bars(n=600, seed=4, start="2024-03-04 18:00"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="1min", tz="America/New_York")
    ret = rng.normal(0, 3, n) + np.sin(np.arange(n) / 60.0) * 1.5
    c = 18000 + np.cumsum(ret)
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.5, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 2.5, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 2.5, n))
    v = np.abs(rng.normal(1000, 400, n)) * (1 + 3 * (rng.random(n) < 0.08))
    return o, h, l, c, v, idx


def _run(bars, root=None, **kw):
    o, h, l, c, v, idx = bars
    with R.roll_context(root, R.epoch_seconds(idx), 60):
        return MOD.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True,
                                _feeds="off", _detail=True, **kw)


def _open_count(trades, n):
    """Open tickets right after each bar's opening fills: entries so far minus exits before
    this bar (independent of how FIFO pairs entries with exits)."""
    ent = np.zeros(n + 1, int); ext = np.zeros(n + 1, int)
    for t in trades:
        ent[t[0]] += 1
        ext[t[1]] += 1
    return np.cumsum(ent)[:n] - np.r_[0, np.cumsum(ext)[:n - 1]]


@pytest.mark.parametrize("kw", [dict(), dict(intrabar="tv"), dict(close_rule="any"),
                                dict(footprint="clv"), dict(spy_proxy="none", daily_close="last"),
                                dict(pyramiding=1, longs_enabled=False, eth_enabled=False)])
def test_pipeline_runs_and_is_wellformed(kw):
    r = _run(_bars(), **kw)
    if r is None:
        return
    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown",
              "avg_pnl", "wins", "losses", "trades"):
        assert k in r
    assert r["num_trades"] == len(r["trades"]) == len(r["trade_detail"])
    assert np.isfinite(r["total_pnl"])


def test_pipeline_deterministic():
    a = _run(_bars(seed=3))
    b = _run(_bars(seed=3))
    assert a is not None and a["trades"] == b["trades"]


@pytest.mark.parametrize("seed", [3, 4, 7, 9])
def test_pipeline_fill_timing_and_exit_order(seed):
    bars = _bars(seed=seed)
    o = bars[0]
    r = _run(bars)
    assert r is not None and r["num_trades"] > 0
    for d in r["trade_detail"]:
        assert d["entry_bar"] == d["signal_bar"] + 1          # next bar's open, never the signal bar
        assert d["exit_bar"] >= d["entry_bar"]
    for d in r["trade_detail"]:
        if d["exit_reason"] != "reverse":
            # FIFO pairs exits with the oldest entry; the entry price is still an open fill
            assert d["entry_price"] == pytest.approx(o[d["entry_bar"]])
    assert r["max_open_tickets"] <= 20


def _walk_inputs(n=400, seed=1, every=1, sl_pts=40.0, tp_pts=60.0, both_sides=False):
    rng = np.random.default_rng(seed)
    c = 15000 + np.cumsum(rng.normal(0, 2, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.5, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 1.5, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 1.5, n))
    chain = np.zeros(n, np.int64)
    chain[::every] = 1 + (np.arange(n)[::every] % 5)
    z = np.zeros(n, bool)
    nanv = np.full(n, np.nan)
    tp_l = c + tp_pts; sl_l = c - sl_pts
    chain_s = chain.copy() if both_sides else np.zeros(n, np.int64)
    tp_s = c - tp_pts; sl_s = c + sl_pts
    return (o, h, l, c, chain, tp_l, sl_l, z, nanv, nanv, chain_s, tp_s, sl_s, z, nanv, nanv)


@pytest.mark.parametrize("cap", [1, 3, 20])
@pytest.mark.parametrize("fifo", [True, False])
def test_walk_respects_pyramiding_cap(cap, fifo):
    args = _walk_inputs()
    n = len(args[0])
    out = MOD._k_walk(*args, np.zeros(n, bool), np.zeros(n, bool), cap, False, fifo, 4 * n)
    eb, xb = out[0], out[1]
    assert out[-1] <= cap
    trades = list(zip(eb, xb))
    assert len(trades) > 0
    assert _open_count(trades, n).max() <= cap
    assert all(x >= e for e, x in trades)


@pytest.mark.parametrize("mode_tv", [False, True])
def test_walk_entries_next_open_and_brackets(mode_tv):
    args = _walk_inputs(every=7, sl_pts=3.0, tp_pts=3.0, both_sides=True)
    o, h, l = args[0], args[1], args[2]
    n = len(o)
    out = MOD._k_walk(*args, np.zeros(n, bool), np.zeros(n, bool), 20, mode_tv, True, 4 * n)
    eb, xb, sd, ep, xp, rs, pa, sg = out[:8]
    assert len(eb) > 0
    for i in range(len(eb)):
        assert eb[i] > sg[i]                                    # filled after the signal bar
        assert xb[i] >= eb[i]
        assert ep[i] == o[eb[i]]
        if rs[i] in (1, 2):                                     # a stop / limit fill stays in the bar
            assert l[xb[i]] - 1e-9 <= xp[i] <= h[xb[i]] + 1e-9


def test_walk_worst_mode_takes_the_stop_when_both_legs_touch():
    n = 6
    o = np.array([100., 100., 100., 100., 100., 100.])
    c = o.copy()
    h = np.array([100., 100., 110., 100., 100., 100.])
    l = np.array([100., 100., 90., 100., 100., 100.])
    chain = np.zeros(n, np.int64); chain[1] = 1                # signal at bar 1 -> fill at bar 2
    tp = np.full(n, 105.0); sl = np.full(n, 95.0)
    z = np.zeros(n, bool); nanv = np.full(n, np.nan); zi = np.zeros(n, np.int64)
    args = (o, h, l, c, chain, tp, sl, z, nanv, nanv, zi, nanv, nanv, z, nanv, nanv, z, z, 20)
    worst = MOD._k_walk(*args, False, True, 16)
    assert worst[1][0] == 2 and worst[5][0] == 1 and worst[4][0] == 95.0   # stop first
    # TV path: open is equidistant -> O-L-H-C (low first) also stops; make the high closer
    h2 = h.copy(); h2[2] = 106.0
    tv = MOD._k_walk(o, h2, l, c, chain, tp, sl, z, nanv, nanv, zi, nanv, nanv, z, nanv, nanv,
                     z, z, 20, True, True, 16)
    assert tv[5][0] == 2 and tv[4][0] == 105.0                  # O-H-L-C: target first


def test_seam_guard_no_trade_crosses_a_switch():
    # bars around the 2024-06-16 20:00 ET NQ switch in tools/data/rolls_NQ.csv
    bars = _bars(n=1800, seed=4, start="2024-06-16 18:00")
    o, h, l, c, v, idx = bars
    t = R.epoch_seconds(idx)
    with R.roll_context("NQ", t, 60):
        no_fill, flat = MOD._seam_masks(*MOD._time_arrays(idx, len(idx)))
    assert flat.sum() == 1
    e = int(np.flatnonzero(flat)[0])
    assert idx[e].strftime("%H:%M") == "19:59" and no_fill[:e + 1].all()
    # forced long signals every bar with brackets that never fill: only the seam can close them
    n = len(o)
    zi = np.zeros(n, np.int64); z = np.zeros(n, bool); nanv = np.full(n, np.nan)
    chain = np.ones(n, np.int64)
    out = MOD._k_walk(o, h, l, c, chain, c + 1e6, c - 1e6, z, nanv, nanv, zi, nanv, nanv, z,
                      nanv, nanv, no_fill, flat, 20, False, True, 4 * n)
    cross = R.crossing_trades(t, "NQ", 60, out[0], out[1])
    assert not cross.any()
    r = _run(bars, root="NQ")
    if r is not None:
        assert not R.crossing_trades(t, "NQ", 60, [x[0] for x in r["trades"]],
                                     [x[1] for x in r["trades"]]).any()


def test_needs_roll_context_and_index():
    o, h, l, c, v, idx = _bars()
    assert MOD.run_backtest(o, h, l, c, volumes=v, index=None) is None
    with pytest.raises(R.RollContextMissing):
        MOD.run_backtest(o, h, l, c, volumes=v, index=idx, _feeds="off")


def test_compiled_kernels_match_interpreted(monkeypatch):
    pytest.importorskip("numba")
    bars = _bars(n=900, seed=3)
    monkeypatch.setenv("EDGELOG_NO_FASTLOOP", "1")
    a = _run(bars, footprint="clv")
    monkeypatch.delenv("EDGELOG_NO_FASTLOOP")
    monkeypatch.setattr(MOD, "_FAST_MIN_BARS", 0)
    b = _run(bars, footprint="clv")
    assert a is not None and a["trades"] == b["trades"]


def test_defaults_cover_the_script_inputs():
    p = MOD.DEFAULT_PARAMS
    script_knobs = [k for k in p if k not in ("intrabar", "close_rule", "pyramiding", "spy_proxy",
                                              "footprint", "daily_close")]
    assert len(script_knobs) == 31                         # 41 inputs - 10 dropped (docstring)
    assert p["adx_min"]["default"] == 25 and p["short_min_rules"]["default"] == 5
    assert p["pyramiding"]["default"] == 20 and p["intrabar"]["default"] == "worst"
    for k, m in p.items():
        if m["type"] in ("int", "float"):
            assert m["min"] <= m["default"] <= m["max"], k
    assert MOD.ROLL_SIGNAL == "raw"


# ── parity harness ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def harness():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import superscalper_parity as sp
    return sp


def test_harness_refuses_lockbox_export(harness, tmp_path):
    with pytest.raises(SystemExit):
        harness.main(["export", "--from", "2025-06-01", "--to", "2025-07-01",
                      "--out", str(tmp_path / "x.csv")])


def test_harness_refuses_lockbox_tv_file_outside_window(harness, tmp_path):
    f = tmp_path / "tv.csv"
    f.write_text("trade,side,exit_time,entry_time,exit_price,entry_price,qty,net_pnl_usd\n"
                 '1,Long,"Aug 5, 2025, 09:40","Aug 5, 2025, 09:31",100.25,100.00,1,+1.00\n')
    with pytest.raises(SystemExit):
        harness.main(["compare", "--tv", str(f)])


def test_harness_reads_both_tv_formats_and_matches(harness, tmp_path):
    f1 = tmp_path / "pub.csv"
    f1.write_text("trade,side,exit_time,entry_time,exit_price,entry_price,qty,net_pnl_usd\n"
                  '1,Short,"Mar 29, 2026, 19:01","Mar 29, 2026, 18:47",23102.75,23130.50,1,+54.26\n'
                  '2,Long,"Open","Mar 29, 2026, 19:20",0,23237.50,1,0\n')
    tv = harness.read_tv(str(f1), "America/Chicago")
    assert len(tv) == 1 and tv[0]["side"] == -1
    assert tv[0]["entry_ts"] == pd.Timestamp("2026-03-29 19:47", tz="America/New_York")
    f2 = tmp_path / "list.csv"
    f2.write_text("Trade #,Type,Signal,Date/Time,Price USD,Contracts,Profit USD\n"
                  "1,Exit long,MAIN_L_X_5,2024-06-03 09:40,18700.25,1,40.5\n"
                  "1,Entry long,MAIN_L_5,2024-06-03 09:31,18680.00,1,40.5\n")
    tv2 = harness.read_tv(str(f2), "America/New_York")
    assert len(tv2) == 1 and tv2[0]["side"] == 1 and tv2[0]["entry_price"] == 18680.0
    te = tv2[0]["entry_ts"].value // 10 ** 9
    port = [{"side": 1, "entry_epoch": te + 60}, {"side": -1, "entry_epoch": te},
            {"side": 1, "entry_epoch": te + 120}]
    assert harness.match(tv2, port) == [(0, 0)]               # same side, +1 bar
