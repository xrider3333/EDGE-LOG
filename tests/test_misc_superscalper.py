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
OUR PORT ADDITIONS (exit knobs + daily VIX stand-in):
  * every new knob at its default reproduces the as-ported trades exactly (fingerprints of
    the pre-change module's trade lists: synthetic, and NQ 1m ETH 2024-06-03..06-14 when
    the data registry is reachable - this checkout or EDGELOG_DATA_ROOT; else skipped);
  * each exit knob moves exits the intended way; the daily VIX has no look-ahead.
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import pytest

from augur_engine import rolls as R
from augur_engine.strategies import load_strategy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = load_strategy("MISC_SUPERSCALPER_1_0.py")
OURS = ("sl_cap_atr", "sl_scale", "tp_scale", "max_hold_bars", "be_trigger", "vix_feed")


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
    out = MOD._k_walk(*args, np.zeros(n, bool), np.zeros(n, bool), cap, False, fifo, 4 * n, 0, 0.0)
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
    out = MOD._k_walk(*args, np.zeros(n, bool), np.zeros(n, bool), 20, mode_tv, True, 4 * n, 0, 0.0)
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
    worst = MOD._k_walk(*args, False, True, 16, 0, 0.0)
    assert worst[1][0] == 2 and worst[5][0] == 1 and worst[4][0] == 95.0   # stop first
    # TV path: open is equidistant -> O-L-H-C (low first) also stops; make the high closer
    h2 = h.copy(); h2[2] = 106.0
    tv = MOD._k_walk(o, h2, l, c, chain, tp, sl, z, nanv, nanv, zi, nanv, nanv, z, nanv, nanv,
                     z, z, 20, True, True, 16, 0, 0.0)
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
                      nanv, nanv, no_fill, flat, 20, False, True, 4 * n, 0, 0.0)
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
                                              "footprint", "daily_close") + OURS]
    assert len(script_knobs) == 31                         # 41 inputs - 10 dropped (docstring)
    assert p["adx_min"]["default"] == 25 and p["short_min_rules"]["default"] == 5
    assert p["pyramiding"]["default"] == 20 and p["intrabar"]["default"] == "worst"
    for k, m in p.items():
        if m["type"] in ("int", "float"):
            assert m["min"] <= m["default"] <= m["max"], k
    assert MOD.ROLL_SIGNAL == "raw"


# ── OUR PORT ADDITIONS ───────────────────────────────────────────────────────

def _fp(trades):
    return hashlib.sha256(repr([tuple(t) for t in trades]).encode()).hexdigest()[:16]


def _defaults_ours():
    return {k: MOD.DEFAULT_PARAMS[k]["default"] for k in OURS}


def test_new_knobs_lattices_and_order():
    p = MOD.DEFAULT_PARAMS
    keys = list(p)
    assert keys[-6:] == list(OURS)                          # appended; old order untouched
    assert keys.index("daily_close") == len(keys) - 7
    assert p["sl_cap_atr"]["options"] == ["off", "3.0"] and p["sl_cap_atr"]["default"] == "off"
    assert (p["sl_scale"]["min"], p["sl_scale"]["max"], p["sl_scale"]["step"],
            p["sl_scale"]["default"]) == (0.40, 1.20, 0.05, 1.0)
    assert (p["tp_scale"]["min"], p["tp_scale"]["max"], p["tp_scale"]["step"],
            p["tp_scale"]["default"]) == (1.0, 2.0, 0.25, 1.0)
    assert (p["max_hold_bars"]["type"], p["max_hold_bars"]["min"], p["max_hold_bars"]["max"],
            p["max_hold_bars"]["step"], p["max_hold_bars"]["default"]) == ("int", 0, 240, 30, 0)
    assert (p["be_trigger"]["min"], p["be_trigger"]["max"], p["be_trigger"]["step"],
            p["be_trigger"]["default"]) == (0.0, 2.0, 0.5, 0.0)
    assert p["vix_feed"]["options"] == ["none", "daily"] and p["vix_feed"]["default"] == "none"


# Fingerprints of the PRE-CHANGE module's trade lists (as ported, before these knobs).
_PINNED_SYNTH = {
    (600, 3, "2024-03-04 18:00", False): "ee208b7dd92f5151",
    (6000, 3, "2024-03-04 18:00", False): "0207f2b6b9e04d9a",
    (6000, 3, "2024-03-04 18:00", True): "f77686c41a08481b",
    (6000, 4, "2024-03-05 08:00", False): "8439adbd56091ab4",
    (6000, 4, "2024-03-05 08:00", True): "1bd9087422a96e2f",
}
_PINNED_NQ_2024_06_03_14 = (96, "cf2878d08ba7d2d4")


@pytest.fixture
def fast_kernels(monkeypatch):
    """Compiled kernels even on short tapes when Numba is present (on-disk cached; the
    trades are identical to the interpreted ones - test_compiled_kernels_match_interpreted
    and the interpreted-computed fingerprints below pin that)."""
    monkeypatch.setattr(MOD, "_FAST_MIN_BARS", 0)


@pytest.mark.parametrize("key", sorted(_PINNED_SYNTH))
def test_new_knob_defaults_reproduce_as_ported_trades_synthetic(key, fast_kernels):
    n, seed, start, alt = key
    kw = dict(intrabar="tv", close_rule="any") if alt else {}
    bars = _bars(n=n, seed=seed, start=start)
    explicit = _run(bars, **kw, **_defaults_ours())["trades"]   # every new knob at its default
    assert _fp(explicit) == _PINNED_SYNTH[key]


def _real_master(monkeypatch):
    import augur_engine.data as D
    import augur_engine.paths as PP
    m = D.find_master("NQ", "1m", "eth", "db_noadj_eth")
    if m is None and os.environ.get("EDGELOG_DATA_ROOT"):
        root = os.environ["EDGELOG_DATA_ROOT"]               # read-only use of another checkout
        monkeypatch.setattr(D, "DB_PATH", os.path.join(root, "optimizer_history.db"))
        monkeypatch.setattr(D, "UPLOADS", os.path.join(root, "augur_uploads"))
        monkeypatch.setattr(PP, "UPLOADS", os.path.join(root, "augur_uploads"))
        m = D.find_master("NQ", "1m", "eth", "db_noadj_eth")
    if m is None:
        pytest.skip("no NQ 1m ETH db_noadj_eth master reachable (set EDGELOG_DATA_ROOT)")
    return D, m


SESSION_PATHS = ("MAIN", "BOS", "RE")                  # tickets whose stop IS the session stop


def test_new_knob_defaults_reproduce_as_ported_trades_nq_2024_06(monkeypatch, fast_kernels):
    D, m = _real_master(monkeypatch)
    from augur_engine.engine import run_backtest
    arr = D.load_master_arrays(m, date_from="2024-06-03", date_to="2024-06-14")   # lockbox-safe
    path = os.path.join(ROOT, "augur_strategies", "MISC_SUPERSCALPER_1_0.py")
    b = run_backtest(path, arrays=arr, master=m, params=dict(_defaults_ours(), _detail=True),
                     cost_pts=0.0, return_trades=True)
    assert (len(b["trades"]), _fp(b["trades"])) == _PINNED_NQ_2024_06_03_14
    # cap scope on real tickets: only session-stop tickets move, and they sit <= 3 ATR
    cap = run_backtest(path, arrays=arr, master=m, params={"sl_cap_atr": "3.0", "_detail": True},
                       cost_pts=0.0, return_trades=True)
    b0 = _by_signal(b)
    changed = 0
    for k, d in _by_signal(cap).items():
        if d["path"] in SESSION_PATHS:
            assert abs(d["signal_close"] - d["ticket_sl"]) <= 3.0 * d["signal_atr"] + 0.125 + 1e-9
        if k in b0 and d["ticket_sl"] != b0[k]["ticket_sl"]:
            changed += 1
            assert d["path"] in SESSION_PATHS, k
    assert changed > 0


def test_exit_levels_cap_then_scales():
    rng = np.random.default_rng(11)
    n = 5000
    c = 18000 + rng.normal(0, 50, n)
    atr = rng.uniform(2, 12, n)
    d_sl = rng.uniform(0.5, 6.0, n) * atr
    d_tp = rng.uniform(1.0, 8.0, n) * atr
    P = MOD._params({})
    for is_long, sgn in ((True, 1.0), (False, -1.0)):
        sl = c - sgn * d_sl
        tp = c + sgn * d_tp
        mask = rng.random(n) < 0.5                                    # session-stop tickets
        t0, s0 = MOD._exit_levels(c, atr, tp, sl, is_long, P, mask)
        assert np.array_equal(t0, tp) and np.array_equal(s0, sl)       # defaults: bit-for-bit
        tc, sc = MOD._exit_levels(c, atr, tp, sl, is_long, dict(P, sl_cap_atr="3.0"), mask)
        dist = sgn * (c - sc)
        assert (dist[mask] <= 3.0 * atr[mask] + 1e-9).all()           # capped: never > 3 ATR
        assert (d_sl[mask] > 3.0 * atr[mask]).any() and (d_sl[~mask] > 3.0 * atr[~mask]).any()
        np.testing.assert_allclose(dist[mask], np.minimum(d_sl, 3.0 * atr)[mask], rtol=0, atol=1e-9)
        assert np.array_equal(sc[~mask], sl[~mask])                    # other paths: untouched
        assert np.array_equal(tc, tp)
        _, snone = MOD._exit_levels(c, atr, tp, sl, is_long, dict(P, sl_cap_atr="3.0"))
        assert np.array_equal(snone, sl)                               # no mask (OD): no cap
        _, sh = MOD._exit_levels(c, atr, tp, sl, is_long, dict(P, sl_scale=0.5), mask)
        np.testing.assert_allclose(sgn * (c - sh), 0.5 * d_sl, rtol=0, atol=1e-9)
        _, sch = MOD._exit_levels(c, atr, tp, sl, is_long, dict(P, sl_cap_atr="3.0", sl_scale=0.5),
                                  mask)
        np.testing.assert_allclose(sgn * (c - sch), 0.5 * np.where(mask, np.minimum(d_sl, 3.0 * atr), d_sl),
                                   rtol=0, atol=1e-9)                 # scale AFTER the cap, every path
        t2, s2 = MOD._exit_levels(c, atr, tp, sl, is_long, dict(P, tp_scale=2.0))
        np.testing.assert_allclose(sgn * (t2 - c), 2.0 * d_tp, rtol=0, atol=1e-9)
        assert np.array_equal(s2, sl)


def _by_signal(r):
    return {(d["signal_bar"], d["side"], d["path"]): d for d in r["trade_detail"]}


def test_pipeline_exit_knobs_move_the_tickets(fast_kernels):
    bars = _bars(n=6000, seed=4, start="2024-03-05 08:00")
    base = _run(bars)
    assert base is not None and base["num_trades"] > 5
    cap = _run(bars, sl_cap_atr="3.0")
    for d in cap["trade_detail"]:                                  # tick rounding: +-1/2 tick
        if d["path"] in SESSION_PATHS:
            assert abs(d["signal_close"] - d["ticket_sl"]) <= 3.0 * d["signal_atr"] + 0.125 + 1e-9
    half = _run(bars, sl_scale=0.5)
    dbl = _run(bars, tp_scale=2.0)
    b0 = _by_signal(base)
    for run_, field, mult in ((half, "ticket_sl", 0.5), (dbl, "ticket_tp", 2.0)):
        common = [(k, d) for k, d in _by_signal(run_).items() if k in b0]
        assert common
        for k, d in common:
            full = b0[k][field] - b0[k]["signal_close"]
            new = d[field] - d["signal_close"]
            assert abs(new - mult * full) <= 0.125 * (1 + mult) + 1e-9, (k, field)  # tick rounding
    held = _run(bars, max_hold_bars=30)
    assert all(d["exit_bar"] - d["entry_bar"] <= 30 for d in held["trade_detail"])
    for kw in (dict(be_trigger=1.0), dict(vix_feed="daily", _feed_vix=([], []))):
        r = _run(bars, **kw)
        assert r is None or r["num_trades"] == len(r["trades"])


@pytest.mark.parametrize("fifo", [True, False])
def test_walk_max_hold_never_holds_past_n_bars(fifo):
    args = _walk_inputs(n=600, every=3, sl_pts=1e6, tp_pts=1e6)     # brackets never fill
    n = len(args[0])
    z = np.zeros(n, bool)
    out = MOD._k_walk(*args, z, z, 20, False, fifo, 4 * n, 30, 0.0)
    eb, xb, rs = out[0], out[1], out[5]
    assert len(eb) > 50 and (rs == 5).sum() > 50
    assert ((xb - eb) <= 30).all()                                 # <= 31 bars incl. the exit bar
    assert ((xb - eb)[rs == 5] == 30).all()
    assert (out[4][rs == 5] == args[0][xb[rs == 5]]).all()         # at the next bar's open
    none = MOD._k_walk(*args, z, z, 20, False, fifo, 4 * n, 0, 0.0)
    assert len(none[0]) == 0                                       # off: nothing ever closes


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("fifo", [False, True])
def test_walk_breakeven_never_fires_on_its_trigger_bar(side, fifo):
    o, h, l, c, chain, tp_l, sl_l, z, nanv, _, chain_s, tp_s, sl_s, _, _, _ = _walk_inputs(
        n=1500, seed=5, every=9, sl_pts=4.0, tp_pts=1e6, both_sides=False)
    zi = np.zeros(len(o), np.int64)
    if side < 0:
        chain_s, chain = chain, zi
    n = len(o)
    base_args = (o, h, l, c, chain, tp_l, sl_l, z, nanv, nanv, chain_s, tp_s, sl_s, z, nanv,
                 nanv, z, z, 20, False, fifo, 4 * n, 0)
    off = MOD._k_walk(*base_args, 0.0)
    on = MOD._k_walk(*base_args, 1.0)
    eb, xb, sd, ep, xp, rs = on[:6]
    tsl, bsl = on[8], on[10]
    # a stop order sitting at some ticket's entry price = that ticket's breakeven stop (the
    # random opens are unique); under FIFO it may close an older trade, so look the ticket up
    owner = {float(ep[j]): j for j in range(len(eb))}
    moved = 0
    for i in range(len(eb)):
        j = owner.get(float(bsl[i])) if rs[i] == 1 else None
        if j is None:
            continue
        moved += 1
        risk = sd[j] * (ep[j] - tsl[j])                            # the ticket's initial risk
        trig = ep[j] + sd[j] * 1.0 * risk
        path = h[eb[j]:xb[i] + 1] if sd[j] > 0 else -l[eb[j]:xb[i] + 1]
        hit = np.flatnonzero(path >= sd[j] * trig)
        assert len(hit) and eb[j] + hit[0] < xb[i]                 # armed strictly before the exit bar
        if not fifo:
            assert j == i                                          # own pairing: its own trade
    assert moved > 5
    assert not np.array_equal(on[4], off[4]) or len(on[0]) != len(off[0])
    # off = the as-ported broker: no stop order ever sits at an entry price
    ent = {float(x) for x in off[3]}
    assert not any(float(x) in ent for x, r in zip(off[10], off[5]) if r == 1)
    if not fifo:
        st = off[5] == 1
        np.testing.assert_allclose(off[10][st], off[8][st])


def test_walk_compiles_with_new_knobs(monkeypatch):
    pytest.importorskip("numba")
    monkeypatch.delenv("EDGELOG_NO_FASTLOOP", raising=False)
    monkeypatch.setattr(MOD, "_FAST_MIN_BARS", 0)
    jw = MOD._kern("walk")
    args = _walk_inputs(n=800, seed=2, every=4, sl_pts=5.0, tp_pts=9.0, both_sides=True)
    n = len(args[0])
    z = np.zeros(n, bool)
    for mh, be in ((0, 0.0), (30, 0.0), (0, 1.0), (60, 0.5)):
        for fifo in (True, False):
            a = MOD._k_walk(*args, z, z, 20, False, fifo, 4 * n, mh, be)
            b = jw(*args, z, z, 20, False, fifo, 4 * n, mh, be)
            for x, y in zip(a[:-1], b[:-1]):
                np.testing.assert_array_equal(x, y)
            assert a[-1] == b[-1]
    assert MOD._JIT["walk"] is not MOD._k_walk                     # really compiled, no fallback


def _vix_tape():
    """ET 1-minute stamps 09:30-16:59 on 14 weekdays from 2024-06-03, plus a CME-holiday
    style weekday (2024-06-19, Juneteenth) whose tape stops at 12:59."""
    days = pd.bdate_range("2024-06-03", periods=15)
    stamps = []
    for d in days:
        end = "12:59" if d.strftime("%Y-%m-%d") == "2024-06-19" else "16:59"
        stamps.append(pd.date_range(d.strftime("%Y-%m-%d") + " 09:30", d.strftime("%Y-%m-%d") + " " + end,
                                    freq="1min", tz="America/New_York"))
    idx = stamps[0].append(stamps[1:])
    loc = MOD._time_arrays(idx, len(idx))[1]
    return days, idx, loc


def test_vix_daily_no_lookahead_and_session_counting():
    days, idx, loc = _vix_tape()
    sess = [d for d in days if d.strftime("%Y-%m-%d") != "2024-06-19"]
    closes = {d.strftime("%Y-%m-%d"): 10.0 + i for i, d in enumerate(days)}
    closes["2024-06-19"] = 999.0                                   # holiday row: must be dropped
    vd, vc = MOD._vix_table(list(closes), list(closes.values()))
    vclose, vprev = MOD._vix_daily(loc, vd, vc)
    assert not (vclose == 999.0).any() and not (vprev == 999.0).any()
    ds = [d.strftime("%Y-%m-%d") for d in sess]
    D = ds[12]                                     # 2024-06-20, the session after the holiday
    stamp = lambda hm: int(np.flatnonzero(idx == pd.Timestamp(D + " " + hm, tz="America/New_York"))[0])  # noqa: E731
    i1614, i1615 = stamp("16:14"), stamp("16:15")
    assert ds[11] == "2024-06-18"
    assert vclose[i1614] == closes[ds[11]]         # 16:14: D's close not seen (holiday skipped)
    assert vclose[i1615] == closes[D]              # 16:15: D's close usable
    assert vprev[i1615] == closes[ds[2]]           # 10 NQ sessions earlier (holiday not counted)
    assert vprev[i1614] == closes[ds[1]]
    assert np.isnan(vclose[0]) and np.isnan(vprev[0])  # warm-up: nothing usable yet
    # a bar never sees a close dated after its own ET date, nor its own date before 16:15
    bar_day = loc // 86400
    bar_min = (loc // 60) % 1440
    day_of = {float(v): int(d) for d, v in zip(vd, vc)}
    for i in np.flatnonzero(~np.isnan(vclose)):
        dd = day_of[float(vclose[i])]
        assert dd < bar_day[i] or (dd == bar_day[i] and bar_min[i] >= 16 * 60 + 15)


def test_cap_scope_session_stop_paths_only(monkeypatch):
    """Forced candidates on every path with stops 10 ATR away: sl_cap_atr=3.0 caps only the
    MAIN/BOS/RE tickets (the session stop); OB, TRAP and OD keep their stops; sl_scale
    then scales every path."""
    bars = _bars(n=2400, seed=2)
    o, h, l, c, v, idx = bars
    n = len(c)
    atr = np.full(n, 4.0)
    chain_l = np.zeros(n, np.int64); chain_s = np.zeros(n, np.int64)
    od_l = np.zeros(n, bool); od_s = np.zeros(n, bool)
    sig_bars = np.arange(300, n - 20, 25)
    for i, u in enumerate(sig_bars):
        code = 1 + (i // 2) % 6                   # 1..5 = chain paths, 6 = OD
        if code == 6:
            (od_l if i % 2 == 0 else od_s)[u] = True
        else:
            (chain_l if i % 2 == 0 else chain_s)[u] = code
    far = 10.0 * atr
    fake = dict(chainL=chain_l, tpL=c + 2.0, slL=c - far, odL=od_l, odTpL=c + 2.0, odSlL=c - far,
                chainS=chain_s, tpS=c - 2.0, slS=c + far, odS=od_s, odTpS=c - 2.0, odSlS=c + far,
                atr=atr)
    monkeypatch.setattr(MOD, "_build", lambda *a, **k: fake)
    base = _run(bars)
    cap = _run(bars, sl_cap_atr="3.0")
    both = _run(bars, sl_cap_atr="3.0", sl_scale=0.5)
    seen = set()
    for r, scale in ((cap, 1.0), (both, 0.5)):
        for d in r["trade_detail"]:
            seen.add(d["path"])
            dist = abs(d["signal_close"] - d["ticket_sl"])
            want = (3.0 if d["path"] in SESSION_PATHS else 10.0) * 4.0 * scale
            assert abs(dist - want) <= 0.125 + 1e-9, (d["path"], dist, want)
    assert seen == {"MAIN", "BOS", "OB", "RE", "TRAP", "OD"}
    for d in base["trade_detail"]:                               # off: every stop as built
        assert abs(abs(d["signal_close"] - d["ticket_sl"]) - 40.0) <= 0.125 + 1e-9


_VIX_RAW_SHA = "6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a"
_VIX_DERIVED_SHA = "9790df06b649df21d34ab7cb31a5ed5e4c3c71fcda33952d1f41e431cb4e2470"


def _day(s):
    return int((pd.Timestamp(s) - pd.Timestamp("1970-01-01")).days)


def _need_vix_files():
    for which in ("raw", "derived"):
        if not os.path.exists(MOD._VIX_FILES[which][0]):
            pytest.skip("CBOE VIX files not on this machine")


def test_vix_files_pinned():
    assert MOD._VIX_FILES["raw"][1] == _VIX_RAW_SHA
    assert MOD._VIX_FILES["derived"][1] == _VIX_DERIVED_SHA
    assert MOD._VIX_FILES["raw"][0].endswith(os.path.join("public_series", "cboe", "VIX_History.csv"))
    assert MOD._VIX_FILES["derived"][0].endswith(os.path.join("public_series", "cboe_vol_daily.csv"))


def test_vix_file_is_refused_on_mismatch(monkeypatch, tmp_path):
    bad = tmp_path / "VIX_History.csv"
    bad.write_text("DATE,OPEN,HIGH,LOW,CLOSE\n06/03/2024,12,12,12,12.0\n")
    files = dict(MOD._VIX_FILES)
    files["raw"] = (str(bad),) + MOD._VIX_FILES["raw"][1:]
    monkeypatch.setattr(MOD, "_VIX_FILES", files)
    monkeypatch.setattr(MOD, "_VIX_MEMO", {})
    with pytest.raises(ValueError, match="sha256"):
        MOD._load_vix_daily("raw", _day("2024-06-30"))
    o, h, l, c, v, idx = _bars()
    with pytest.raises(ValueError, match="sha256"):              # 'raw' is the default source
        with R.roll_context(None, R.epoch_seconds(idx), 60):
            MOD.run_backtest(o, h, l, c, volumes=v, index=idx, _feeds="off", vix_feed="daily")
    with pytest.raises(ValueError, match="_vix_file"):
        MOD._load_vix_daily("bogus", _day("2024-06-30"))


def test_vix_drop_rows_after_the_window(monkeypatch):
    _need_vix_files()
    monkeypatch.setattr(MOD, "_VIX_MEMO", {})
    for which in ("raw", "derived"):
        for d in ("2016-06-30", "2024-06-14", "2024-12-31"):
            vd, vc = MOD._load_vix_daily(which, _day(d))
            assert len(vd) > 6000 and vd.max() <= _day(d) and (np.diff(vd) > 0).all()
            assert vd.max() >= _day(d) - 4                          # cut at D, not earlier
    keys = {k[0] for k in MOD._VIX_MEMO}
    assert keys == {"raw", "derived"}                                # memo keyed by the file
    # run_backtest passes the chosen file and the last bar's CME trading date
    calls = []
    real = MOD._load_vix_daily
    monkeypatch.setattr(MOD, "_load_vix_daily", lambda w, d: calls.append((w, d)) or real(w, d))
    o, h, l, c, v, idx = _bars(start="2024-03-04 18:00")             # ends 2024-03-05 03:59 ET
    with R.roll_context(None, R.epoch_seconds(idx), 60):
        MOD.run_backtest(o, h, l, c, volumes=v, index=idx, _feeds="off", vix_feed="daily")
        MOD.run_backtest(o, h, l, c, volumes=v, index=idx, _feeds="off", vix_feed="daily",
                         _vix_file="derived")
    assert calls == [("raw", _day("2024-03-05")), ("derived", _day("2024-03-05"))]


def _vix_arrays(loc, which):
    last_day = int((loc[-1] + 6 * 3600) // 86400)
    return MOD._vix_daily(loc, *MOD._load_vix_daily(which, last_day))


def test_vix_raw_and_derived_align_identically_synthetic():
    _need_vix_files()
    days, idx, loc = _vix_tape()
    a = _vix_arrays(loc, "raw")
    b = _vix_arrays(loc, "derived")
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x, y)
    assert np.isfinite(a[0]).mean() > 0.5 and np.isfinite(a[1]).any()


def test_vix_raw_and_derived_align_identically_nq_2024(monkeypatch):
    _need_vix_files()
    D, m = _real_master(monkeypatch)
    arr = D.load_master_arrays(m, date_from="2024-01-01", date_to="2024-12-31")   # lockbox-safe
    loc = MOD._time_arrays(arr["index"], len(arr["index"]))[1]
    a = _vix_arrays(loc, "raw")
    b = _vix_arrays(loc, "derived")
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x, y)
    assert np.isfinite(a[0]).mean() > 0.99 and np.isfinite(a[1]).mean() > 0.9


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


def test_mechanics_knobs_are_not_searchable():
    """The Auto-Validate searches every str knob's options: a fill model or stand-in feed must offer exactly one (prereg
    Amendment 4), and intrabar's one option is the house 'worst' fill."""
    dp = MOD.DEFAULT_PARAMS
    for k in ("intrabar", "close_rule", "spy_proxy", "footprint", "daily_close"):
        assert dp[k]["options"] == [dp[k]["default"]], k
    assert dp["intrabar"]["default"] == "worst"
    assert dp["sl_cap_atr"]["options"] == ["off", "3.0"] and dp["vix_feed"]["options"] == ["none", "daily"]


def test_build_releases_its_locals():
    """tools/free_locals.py output is current: re-running it on the port changes nothing (idempotent), so every working
    array in _build_inner is released after its last use (memory ~0.3 GB a year of 1m bars instead of ~1.5 GB)."""
    import subprocess, tempfile
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "augur_strategies", "MISC_SUPERSCALPER_1_0.py")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "x.py")
        subprocess.run([sys.executable, os.path.join(root, "tools", "free_locals.py"), src, "_build_inner", out],
                       check=True, capture_output=True)
        assert open(out, "rb").read() == open(src, "rb").read()
