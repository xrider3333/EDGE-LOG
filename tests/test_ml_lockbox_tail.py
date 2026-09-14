"""Lockbox tails for the 1A CONFIG FUNNEL's ML lines (2026-09-13).

WHY: the owner said the lockbox on the funnel "still shows as stretched". Every ML line
(gate candidates, tilts, hybrids, KEEL, the chosen gate) saves ONE 300-point stride sample
of the whole run. On #384 that is 4,075 trades, so the 273 held-out trades get about 20 of
those points, and with the lockbox at a quarter of the funnel's width they draw as long
straight strokes. The RAW config lines look fine because they save their lockbox stretch
separately.

The engine now adds a dense sample of just the lockbox stretch to each ML row
(analytics.lockbox_tail, carried as equity.lb_tail / equity.lb_tail_gated). These tests pin:
  a. downsample_curve is unchanged - the tail replays its index rule, and every saved run's
     300-point curve was cut by it, so an edit there would silently misplace the door;
  b. the helper: real per-trade values only (never interpolated), evenly spread, ending on
     the final trade, the door index matching the saved points, JSON-safe flat output - and
     NO tail when it would draw the lockbox with fewer points than the saved curve already
     does (a short run, or a lockbox that is a big share of the trades), so a stitch can
     never lose a real high or low the old line showed;
  c. the cases where no honest door exists return None;
  d. gate_validate puts a sound tail on EVERY ML row, the door is the ungated pre-lockbox
     count, and lb_tail_cap=0 reproduces the old output exactly (old runs stay identical);
  e. a door at the hybrid's own kept_pre (the bug the web shipped once) is caught by (d);
  f. the runner's Firestore size guard never trims a tail.
"""
import copy
import json
import types

import numpy as np
import pandas as pd
import pytest

import augur_engine.ml_gate as G
import augur_engine.ml_keel as K
from augur_engine.analytics import (LB_TAIL_CAP, LB_TAIL_POINT_BUDGET, downsample_curve,
                                    lb_tail_adds_points, lb_tail_line_cap, lockbox_tail,
                                    strip_lb_tails)


# ─────────────────────────────────────────────────────────────────────────────
# a. golden copy of downsample_curve (verbatim, v73.757 analytics.py)
# ─────────────────────────────────────────────────────────────────────────────

def _golden_downsample_curve(cum, cap=300, ndp=1):
    xs = [float(x) for x in (cum if cum is not None else [])]
    n = len(xs)
    if n == 0:
        return []
    if n <= int(cap):
        return [int(round(x)) for x in xs] if ndp is None else [round(x, ndp) for x in xs]
    st = n / float(cap)
    out = [xs[int(i * st)] for i in range(int(cap))]
    out[-1] = xs[-1]
    return [int(round(x)) for x in out] if ndp is None else [round(x, ndp) for x in out]


def test_downsample_curve_matches_the_golden_copy():
    rng = np.random.default_rng(11)
    walk = [float(x) for x in np.cumsum(rng.normal(0.3, 25.0, 2000))]
    assert downsample_curve([]) == [] and downsample_curve(None) == []
    for n in range(1, 2001):
        cum = walk[:n]
        for cap in (300, 110):
            for ndp in (None, 1):
                assert downsample_curve(cum, cap=cap, ndp=ndp) == \
                    _golden_downsample_curve(cum, cap=cap, ndp=ndp), (n, cap, ndp)


# ─────────────────────────────────────────────────────────────────────────────
# b. lockbox_tail properties
# ─────────────────────────────────────────────────────────────────────────────

def _saved_positions(n, pts):
    """The trade index behind each point downsample_curve keeps, restated longhand."""
    if n <= pts:
        return list(range(n))
    st = n / float(pts)
    pos = [int(k * st) for k in range(pts)]
    pos[-1] = n - 1
    return pos


def _brute_j0(n, pts, i0):
    """Saved points strictly before the last pre-lockbox trade - the ones the web keeps."""
    return sum(1 for p in _saved_positions(n, pts)[:-1] if p < i0 - 1)


def _rnd(x, ndp):
    return int(round(x)) if ndp is None else round(x, ndp)


def _flat_json_safe(t):
    assert set(t) == {"v", "cum", "base", "i0", "j0", "pts"}
    for k in ("v", "i0", "j0", "pts"):
        assert type(t[k]) is int, k
    assert type(t["base"]) in (int, float)
    assert isinstance(t["cum"], list)
    assert all(type(x) in (int, float) for x in t["cum"])     # flat: Firestore rejects nesting
    assert json.loads(json.dumps(t)) == t


@pytest.mark.parametrize("n", [5, 299, 300, 301, 1400, 4075])
def test_lockbox_tail_properties(n):
    rng = np.random.default_rng(n)
    cum = np.cumsum(rng.normal(0.4, 30.0, n))
    ident = np.arange(n, dtype=float)                           # value == trade index
    for pts_cap in (300, 110):
        assert downsample_curve(ident, cap=pts_cap, ndp=None) == _saved_positions(n, pts_cap)
        for i0 in sorted({2, n // 2, n - 1}):
            L = n - i0
            for cap in (LB_TAIL_CAP, 7, 5000):
                for ndp in (None, 1):
                    saved = downsample_curve(cum, cap=pts_cap, ndp=ndp)
                    # the geometry, with the density rule off so every case is exercised
                    t = lockbox_tail(cum, i0, len(saved), cap, ndp, only_if_denser=False)
                    assert t is not None, (n, i0, pts_cap, cap, ndp)
                    _flat_json_safe(t)
                    m = min(cap, L)
                    assert t["v"] == 1 and t["i0"] == i0 and t["pts"] == len(saved)
                    assert len(t["cum"]) == m
                    assert t["base"] == _rnd(cum[i0 - 1], ndp)
                    assert t["cum"][-1] == saved[-1]                # same final as the saved curve
                    assert t["j0"] == _brute_j0(n, len(saved), i0)
                    assert 1 <= t["j0"] <= len(saved) - 1
                    # the density rule: a tail only when it puts MORE points from the door on
                    #   than the saved curve has there; otherwise None, never a thinner line
                    denser = m + 1 > len(saved) - t["j0"]
                    assert lb_tail_adds_points(m, len(saved), t["j0"]) is denser
                    assert lockbox_tail(cum, i0, len(saved), cap, ndp) == (t if denser else None)
                    if n <= pts_cap:
                        assert not denser               # the saved curve already holds every trade
                    # where each tail value sits, read off an identity curve
                    ti = lockbox_tail(ident, i0, len(saved), cap, None, only_if_denser=False)
                    pos = ti["cum"]
                    assert ti["base"] == i0 - 1 and ti["j0"] == t["j0"]
                    assert pos[0] >= i0 and pos[-1] == n - 1
                    assert all(b > a for a, b in zip(pos, pos[1:]))
                    gaps = {b - a for a, b in zip([i0 - 1] + pos, pos)}
                    assert gaps <= {L // m, -(-L // m)}             # evenly spread
                    # real per-trade values only - nothing interpolated
                    assert t["cum"] == [_rnd(cum[p], ndp) for p in pos]
                    # the web's stitch: saved[:j0] + [base] + tail is a real, ordered curve
                    sp = _saved_positions(n, len(saved))
                    stitched_pos = sp[:t["j0"]] + [i0 - 1] + pos
                    stitched_val = saved[:t["j0"]] + [t["base"]] + t["cum"]
                    assert all(b > a for a, b in zip(stitched_pos, stitched_pos[1:]))
                    assert stitched_val == [_rnd(cum[p], ndp) for p in stitched_pos]
                    assert stitched_pos[-1] == n - 1 and stitched_val[-1] == saved[-1]


def test_lockbox_tail_on_the_384_shape():
    """#384: 4,075 trades, 3,802 before the lockbox, a 300-point saved curve."""
    cum = np.cumsum(np.random.default_rng(384).normal(6.0, 40.0, 4075))
    saved = downsample_curve(cum, cap=300, ndp=None)
    t = lockbox_tail(cum, 3802, len(saved), LB_TAIL_CAP, None)
    assert (t["i0"], t["j0"], t["pts"], len(t["cum"])) == (3802, 280, 300, 80)
    assert _brute_j0(4075, 300, 3801) == 280            # same count below i0 as below i0-1
    assert abs(t["cum"][-1] - t["base"] - float(np.sum(np.diff(cum)[3801:]))) <= 1.0


def test_a_tiny_lockbox_gets_its_tail_at_the_last_saved_point():
    """A lockbox so small that only the final saved point is past the door (j0 = pts-1) is the
    MOST stretched line - one straight stroke across the whole lockbox. Its tail must exist,
    and the stitch must still be a real, ordered curve. 27 lockbox trades is the edge on #384."""
    cum = np.cumsum(np.random.default_rng(26).normal(6.0, 40.0, 4075))
    saved = downsample_curve(cum, cap=300, ndp=None)
    for i0, j0 in ((4049, 299), (4065, 299), (4074, 299), (4048, 298)):
        t = lockbox_tail(cum, i0, len(saved), LB_TAIL_CAP, None)
        assert t is not None and t["j0"] == j0 and len(t["cum"]) == 4075 - i0, i0
        pos = _saved_positions(4075, 300)[:j0] + [i0 - 1] + list(range(i0, 4075))
        assert all(b > a for a, b in zip(pos, pos[1:]))
        assert saved[:j0] + [t["base"]] + t["cum"] == [_rnd(cum[p], None) for p in pos]


@pytest.mark.parametrize("n,i0,cap", [(900, 600, 80), (250, 150, 80), (1000, 667, 40),
                                      (1000, 640, 80), (300, 200, 80), (1000, 731, 80)])
def test_no_tail_when_the_saved_curve_already_draws_the_lockbox_denser(n, i0, cap):
    """The reviewer's lossy cases: the 300-point sample already has at least as many points past
    the door as the stitched line would, so stitching would thin the lockbox out."""
    cum = np.cumsum(np.random.default_rng(n + i0).normal(3.0, 30.0, n))
    saved = downsample_curve(cum, cap=300, ndp=None)
    j0 = _brute_j0(n, len(saved), i0)
    assert min(cap, n - i0) + 1 <= len(saved) - j0            # the case really is the lossy one
    assert lockbox_tail(cum, i0, len(saved), cap, None) is None
    assert lockbox_tail(cum, i0, len(saved), cap, None, only_if_denser=False) is not None


def test_break_even_and_the_spike_the_saved_curve_keeps():
    # 1,000 trades: a door at 732 leaves 80 saved points past it against 81 stitched - a tail;
    #   at 731 the saved curve has 81 there, as many as the stitch would - no tail
    cum = np.cumsum(np.random.default_rng(3).normal(3.0, 30.0, 1000))
    assert 300 - _brute_j0(1000, 300, 732) == 80 and lockbox_tail(cum, 732, 300) is not None
    assert 300 - _brute_j0(1000, 300, 731) == 81 and lockbox_tail(cum, 731, 300) is None
    # a one-trade spike on trade 646 that the saved curve keeps and an 80-point tail steps over:
    #   no tail, so the spike stays on the line
    p = np.random.default_rng(4).normal(3.0, 30.0, 1000)
    p[646] += 1_000_000.0
    p[647] -= 1_000_000.0
    cf = np.cumsum(p)
    sv = downsample_curve(cf, cap=300, ndp=None)
    forced = lockbox_tail(cf, 640, 300, only_if_denser=False)
    assert max(sv) > 900_000 and max(forced["cum"]) < 900_000
    assert lockbox_tail(cf, 640, 300) is None


def test_the_per_line_cap_is_a_hard_budget():
    for n_lines in range(1, 5001):
        c = lb_tail_line_cap(n_lines)
        assert 0 <= c <= LB_TAIL_CAP and c * n_lines <= LB_TAIL_POINT_BUDGET, n_lines
    assert lb_tail_line_cap(37) == 80 and lb_tail_line_cap(88) == 36 and lb_tail_line_cap(172) == 18
    assert lb_tail_line_cap(4000) == 0 and lb_tail_line_cap(10, cap=0) == 0


# ─────────────────────────────────────────────────────────────────────────────
# c. no honest door -> None
# ─────────────────────────────────────────────────────────────────────────────

def test_lockbox_tail_none_cases():
    c10 = list(np.cumsum(np.ones(10)))
    assert lockbox_tail(None, 2, 300) is None
    assert lockbox_tail([], 2, 300) is None
    assert lockbox_tail([1.0], 2, 300) is None
    assert lockbox_tail([1.0, 2.0], 2, 300) is None            # n < 3
    assert lockbox_tail(c10, 0, 10) is None                      # i0 < 2
    assert lockbox_tail(c10, 1, 10) is None
    assert lockbox_tail(c10, -3, 10) is None
    assert lockbox_tail(c10, 10, 10) is None                     # empty lockbox
    assert lockbox_tail(c10, 15, 10) is None
    assert lockbox_tail(c10, 5, 10, cap=0) is None               # tails switched off
    assert lockbox_tail(c10, 5, 1) is None                       # no saved curve to stitch onto
    assert lockbox_tail(c10, 5, 0) is None
    assert lockbox_tail(c10, "x", 10) is None
    assert lockbox_tail(c10, 5, 10) is None                      # 10 saved points hold every trade
    assert lockbox_tail(c10, 5, 10, only_if_denser=False) is not None   # control


def test_strip_lb_tails_removes_only_tails_and_never_mutates():
    tail = {"v": 1, "cum": [1, 2], "base": 0, "i0": 2, "j0": 1, "pts": 3}
    gv = {"candidates": [{"model": "a", "equity": {"cum": [0, 1, 2], "n": 5, "lb_tail": tail}}],
          "tilts": [{"model": "b", "equity": {"cum": [0, 1, 2], "n": 5, "lb_tail": tail}}],
          "hybrids": [{"model": "c", "equity": {"cum": [0, 1, 2], "n": 5}}],
          "keel": {"model": "keel", "equity": {"cum": [0, 1, 2], "n": 5, "lb_tail": tail}},
          "equity": {"cum_ungated": [0, 1, 2], "cum_gated": [0, 1, 2], "n": 5,
                     "lb_tail_gated": tail},
          "lb_tail_backfill": {"at": "x"}, "verdict": "v"}
    before = copy.deepcopy(gv)
    s = strip_lb_tails(gv)
    assert gv == before                                          # original untouched
    assert "lb_tail" not in json.dumps(s)
    assert s["candidates"][0] == {"model": "a", "equity": {"cum": [0, 1, 2], "n": 5}}
    assert s["hybrids"] == before["hybrids"] and s["verdict"] == "v"
    assert s["equity"] == {"cum_ungated": [0, 1, 2], "cum_gated": [0, 1, 2], "n": 5}
    assert strip_lb_tails(None) is None
    assert strip_lb_tails({"error": "x"}) == {"error": "x"}
    assert strip_lb_tails({"keel": {"error": "boom"}}) == {"keel": {"error": "boom"}}


# ─────────────────────────────────────────────────────────────────────────────
# d. gate_validate integration (synthetic, tz-aware - tests/test_fold_detail.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

_LB_FROM = "2020-01-16"


def _synthetic_run():
    rng = np.random.default_rng(7)
    idx = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"),
                        pd.Timestamp("2020-01-21", tz="US/Eastern"), freq="5min", tz="US/Eastern")
    n = len(idx)
    close = 1000.0 + np.cumsum(rng.normal(0, 1.0, n))
    day_id = pd.factorize(pd.Series(idx).dt.date)[0].astype("int64")
    arrays = {"open": close.copy(), "high": close + 1.0, "low": close - 1.0,
              "close": close.copy(), "volume": np.full(n, 1000.0), "day_id": day_id,
              "index": idx}
    trades = [(int(e), int(e) + 6, float(rng.normal(0.5, 10.0)))
              for e in np.arange(50, n - 10, 14)]
    return arrays, trades


_GV_KW = dict(gates=("logistic", "tree"), thresholds=(0.5,), min_kept=1, min_keep_frac=0.0,
              lb_from=_LB_FROM)


@pytest.fixture(scope="module")
def synth():
    arrays, trades = _synthetic_run()
    # KEEL's walk is the slow part and does not depend on lb_tail_cap, so the cap=0 twin
    #   reuses it instead of paying for a second identical walk.
    orig, memo = K.keel_walk, {}

    def _walk(*a, **kw):
        key = kw.get("version")
        if key not in memo:
            memo[key] = orig(*a, **kw)
        return memo[key]

    K.keel_walk = _walk
    try:
        on = G.gate_validate(arrays, trades, keel=True, **_GV_KW)
        off = G.gate_validate(arrays, trades, keel=True, lb_tail_cap=0, **_GV_KW)
    finally:
        K.keel_walk = orig
    return {"arrays": arrays, "trades": trades, "on": on, "off": off}


def _row_lockbox_total(gv, r):
    return (r.get("lockbox") or {}).get("total_pnl")


def _tail_problems(gv, keel=True, cap=LB_TAIL_CAP):
    """Every way a row's lockbox tail can disagree with its own run. Empty list = sound."""
    bad = []
    i0 = int(gv["ungated_pre"]["num_trades"])
    L = int(gv["ungated_lockbox"]["num_trades"])
    rows = ([("candidate %s@%s" % (r["model"], r["threshold"]), r) for r in gv["candidates"]]
            + [("tilt %s/%s" % (r["model"], r["scheme"]), r) for r in gv["tilts"]]
            + [("hybrid %s" % r["model"], r) for r in gv["hybrids"]])
    if keel:
        rows.append(("keel", gv["keel"]))
    lines = [(name, r.get("equity") or {}, "cum", "lb_tail", _row_lockbox_total(gv, r), 1.0)
             for name, r in rows]
    ch = gv.get("chosen")
    if ch is not None:
        lbg = ((gv.get("lockbox") or {}).get("gated") or {}).get("total_pnl")
        if lbg is None:                     # gate did not earn: its candidate row has the block
            lbg = next(_row_lockbox_total(gv, c) for c in gv["candidates"]
                       if c["model"] == ch["model"] and c["threshold"] == ch["threshold"])
        lines.append(("chosen gate", gv.get("equity") or {}, "cum_gated", "lb_tail_gated", lbg, 0.1))
    for name, eq, ck, tk, lb_total, tol in lines:
        cum, t = eq.get(ck), eq.get(tk)
        if not isinstance(t, dict) or not isinstance(cum, list):
            bad.append("%s: no tail" % name)
            continue
        if t["i0"] != i0:
            bad.append("%s: i0 %s != ungated pre-lockbox count %s" % (name, t["i0"], i0))
        if t["pts"] != len(cum):
            bad.append("%s: pts %s != saved curve length %s" % (name, t["pts"], len(cum)))
        if t["j0"] != _brute_j0(int(eq["n"]), len(cum), i0):
            bad.append("%s: j0 %s does not match the saved index rule" % (name, t["j0"]))
        if not t["cum"] or t["cum"][-1] != cum[-1]:
            bad.append("%s: tail does not end on the saved curve's final value" % name)
        elif abs(t["cum"][-1] - t["base"] - lb_total) > tol + 1e-6:
            bad.append("%s: span %.3f != lockbox total %.3f"
                       % (name, t["cum"][-1] - t["base"], lb_total))
        if len(t["cum"]) != min(cap, L):
            bad.append("%s: %s tail points, expected %s" % (name, len(t["cum"]), min(cap, L)))
        if not lb_tail_adds_points(len(t["cum"]), len(cum), t["j0"]):
            bad.append("%s: the tail adds no lockbox points over the saved curve" % name)
    return bad


def test_every_ml_row_carries_a_sound_lockbox_tail(synth):
    gv = synth["on"]
    # presence first: the builders swallow exceptions, so a missing row must not pass quietly
    assert len(gv["candidates"]) == 2 and len(gv["tilts"]) == 4 and len(gv["hybrids"]) == 2
    assert gv["chosen"] is not None and "error" not in gv["keel"]
    assert int(gv["ungated_lockbox"]["num_trades"]) > LB_TAIL_CAP   # the stride is exercised
    assert _tail_problems(gv) == []
    # the door is the ungated count, and the hybrids' own kept_pre really is different here
    assert all(h["kept_pre"] != gv["ungated_pre"]["num_trades"] for h in gv["hybrids"])


def test_cap_zero_is_the_old_output_exactly(synth):
    on, off = synth["on"], synth["off"]
    assert "lb_tail" not in json.dumps(off, default=str)
    before = json.dumps(on, default=str)
    assert json.dumps(strip_lb_tails(on), default=str) == json.dumps(off, default=str)
    assert json.dumps(on, default=str) == before                   # stripping never mutates
    # every saved 300-point curve is identical with tails on and off
    for k in ("candidates", "tilts", "hybrids"):
        for a, b in zip(on[k], off[k]):
            assert a["equity"]["cum"] == b["equity"]["cum"] and a["equity"]["n"] == b["equity"]["n"]
    assert on["keel"]["equity"]["cum"] == off["keel"]["equity"]["cum"]
    for ck in ("cum_ungated", "cum_gated", "n"):
        assert on["equity"][ck] == off["equity"][ck]


def _tail_points(gv):
    rows = gv["candidates"] + gv["tilts"] + gv["hybrids"] + [gv.get("keel") or {}]
    eqs = [r.get("equity") or {} for r in rows] + [gv.get("equity") or {}]
    return sum(len(e[k]["cum"]) for e in eqs for k in e if str(k).startswith("lb_tail"))


def test_wide_grid_shrinks_the_per_line_cap_inside_the_budget(synth):
    # 2 gates x 40 cut-offs = 88 lines -> 36 points a line, 3,168 in all. The lockbox here is
    #   late enough (41 trades, 30 saved points past the door) that 36 still adds points.
    ths = tuple(round(0.30 + 0.01 * i, 2) for i in range(40))
    gv = G.gate_validate(synth["arrays"], synth["trades"], gates=("logistic", "tree"),
                         thresholds=ths, min_kept=1, min_keep_frac=0.0, lb_from="2020-01-19",
                         keel=False)
    ncur = 2 * 40 + 3 * 2 + 2
    cap = lb_tail_line_cap(ncur)
    assert cap == 36 and int(gv["ungated_lockbox"]["num_trades"]) > cap   # the stride is exercised
    assert len(gv["candidates"]) == 80
    assert _tail_problems(gv, keel=False, cap=cap) == []
    # the budget holds for the grid as a whole, not just per line
    assert 0 < _tail_points(gv) <= LB_TAIL_POINT_BUDGET


def test_no_tails_without_an_honest_door(synth):
    arrays, trades = synth["arrays"], synth["trades"]
    for lb in ("2020-01-25", "2020-01-01 04:00",       # empty lockbox / under 2 pre-lockbox trades
               "2020-01-14"):                          # the saved curve already draws it denser
        gv = G.gate_validate(arrays, trades, gates=("logistic",), thresholds=(0.5,),
                             min_kept=1, min_keep_frac=0.0, lb_from=lb, keel=False)
        assert gv is not None
        assert "lb_tail" not in json.dumps(gv, default=str), lb


# ─────────────────────────────────────────────────────────────────────────────
# e. mutation proof: a door at the hybrid's kept_pre must fail (d)
# ─────────────────────────────────────────────────────────────────────────────

_HYB_TAIL_CALL = '_lt = _tail(_cf, hrow["equity"]["cum"])'


def _mutant_gate_validate(new_call):
    """gate_validate compiled from ml_gate's own source with the hybrid tail call replaced."""
    src = open(G.__file__, encoding="utf-8").read()
    assert src.count(_HYB_TAIL_CALL) == 1          # the anchor exists, so the mutant is real
    mod = types.ModuleType("augur_engine._ml_gate_kept_pre_mutant")
    mod.__package__ = "augur_engine"
    mod.__file__ = G.__file__
    exec(compile(src.replace(_HYB_TAIL_CALL, new_call), G.__file__, "exec"), mod.__dict__)
    return mod.gate_validate


@pytest.mark.parametrize("new_call,expect", [
    # the plain bug: door at kept_pre. The density rule is switched off in the mutant so the
    #   door is the only thing wrong - an early door leaves more saved points past it, and the
    #   rule alone would otherwise hide the mutant as "no tail".
    ('_lt = lockbox_tail(_cf, int(hrow["kept_pre"]), len(hrow["equity"]["cum"]), _tcap, None, False)',
     "i0"),
    # the sneaky one: the door is at kept_pre but the row still claims the ungated count
    ('_lt = dict(lockbox_tail(_cf, int(hrow["kept_pre"]), len(hrow["equity"]["cum"]), _tcap, None,'
     ' False), i0=ung_pre_n)', "span"),
])
def test_kept_pre_door_is_caught(synth, new_call, expect):
    gv = _mutant_gate_validate(new_call)(synth["arrays"], synth["trades"], keel=False, **_GV_KW)
    problems = _tail_problems(gv, keel=False)
    assert problems, "a kept_pre door slipped through the integration checks"
    assert all(p.startswith("hybrid") for p in problems)
    assert any((": %s " % expect) in p for p in problems), problems
    # and the unmutated engine on the same inputs is clean
    assert _tail_problems(G.gate_validate(synth["arrays"], synth["trades"], keel=False,
                                          **_GV_KW), keel=False) == []


# ─────────────────────────────────────────────────────────────────────────────
# f. the runner's size guard leaves tails alone
# ─────────────────────────────────────────────────────────────────────────────

def test_runner_shrink_to_fit_leaves_tails_intact(synth):
    import api.runner as R
    gv = copy.deepcopy(synth["on"])
    doc = {"gate_validate": gv,
           "validate": {"gate_bakeoff": strip_lb_tails(gv),
                        "equity": [float(i) for i in range(5000)]},
           "equity": [float(i) for i in range(20000)],
           "dist": [{"total_pnl": float(i), "blob": "x" * 60} for i in range(3000)],
           "junk_field": ["x" * 500] * 2000}
    before = json.dumps(doc["gate_validate"], default=str)
    budget = R._doc_size({"gate_validate": gv, "validate": doc["validate"]["gate_bakeoff"]}) + 20_000
    assert R._doc_size(doc) > budget
    logs = []
    out = R.shrink_to_fit(doc, budget=budget, log=logs.append, label="lb-tail-test")
    assert any("stage 1" in m for m in logs) and any("stage 3" in m for m in logs), logs
    assert json.dumps(out["gate_validate"], default=str) == before
    assert _tail_problems(out["gate_validate"]) == []
