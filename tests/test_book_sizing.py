"""BOOK-LEVEL SIZING (augur_engine/book_sizing.py, run_book(book_sizing=...)) - frontier RISK r1, 2026-10-03.

Round 62's V2 rule (BOOK.md 10o) is the only structural change that beat BOOK #463 in both stretches, and it
could not be a real run because the engine had no book-level sizing. These tests guard what makes the new
feature trustworthy:
  1. no block = the book exactly as before (no new key, same numbers); a block at x1.0 = the same to the cent;
  2. the multiplier is the live VT shadow's arithmetic (api/book_shadow.vt_multipliers), value for value;
  3. it is causal: the multiplier for day D never moves when P&L on D or later changes;
  4. each trade is sized at its ENTRY day - a multi-day trade carries one multiplier on every daily mark -
     and its marks still sum to its closed dollars, so sized net is identical both ways;
  5. unselected legs are untouched; a block the engine cannot read fails loudly instead of running unsized.
"""
import numpy as np
import pandas as pd
import pytest

import augur_engine.book as B
import augur_engine.book_sizing as BS


# ------------------------------------------------------------------ synthetic legs priced by the engine's own formulas
def _leg_spec(seed, n_days=320, multi_day=False, start="2020-01-01"):
    """Two bars a day; one intraday trade a day whose size of move clusters (calm, wild, calm);
    optionally a few multi-day trades. Trade tuple = (entry_bar, exit_bar, pts, side, entry_px)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n_days)
    days_idx = np.repeat(days.values.astype("datetime64[D]"), 2)
    scale = np.where((np.arange(n_days) > 200) & (np.arange(n_days) < 240), 4.0, 1.0)
    close = 1000.0 + np.cumsum(rng.normal(0, 1, 2 * n_days) * np.repeat(scale, 2))
    trades = []
    for k in range(n_days):
        pts = float(rng.normal(0.3, 2.0) * scale[k])
        trades.append((2 * k, 2 * k + 1, pts, 1, float(close[2 * k])))
    if multi_day:
        for k in range(30, n_days - 10, 37):
            e, x = 2 * k, 2 * (k + 6) + 1                     # held across six day boundaries
            pts = float(close[x] - close[e]) - 0.5
            trades.append((e, x, pts, 1, float(close[e])))
    return {"days_idx": days_idx, "close": close, "trades": trades}


def _install(monkeypatch, specs):
    """Replace _leg_trades with one that prices each leg's synthetic trades through _closed_series and
    _mtm_increments exactly as the real one does (and keeps the same re-pricing state)."""
    def fake(leg, date_from, date_to, keep_state=False):
        sp = specs[leg["strategy"]]
        sized = [(t, 1.0) for t in sp["trades"]]
        mult, weight = float(leg.get("mult", 20)), float(leg.get("weight", 1) or 1)
        last = len(sp["days_idx"]) - 1
        out, out_sess = B._closed_series(sized, sp["days_idx"], None, last, mult, weight)
        mtm, mk, um = B._mtm_increments(sp["days_idx"], sp["close"], sized, mult, weight)
        info = {"strategy": leg["strategy"], "instrument": "NQ", "timeframe": "5m", "session": "rth",
                "source": "x", "mult": mult, "weight": weight, "trades": len(out),
                "net": round(sum(p for _, p in out), 2), "master": "synthetic", "cost_pts": 0.0,
                "mtm_marked": mk, "_session_day": out_sess, "_mtm_day": mtm}
        if keep_state:
            info["_state"] = {"days_idx": sp["days_idx"], "sess_idx": None, "last": last, "close": sp["close"],
                              "sized": sized, "mult": mult, "weight": weight, "plugin_marks": None,
                              "usd_units": False, "mtm_failed": False}
        return out, info
    monkeypatch.setattr(B, "_leg_trades", fake)


LEGS = [{"strategy": "A.py", "mult": 20}, {"strategy": "B.py", "mult": 20, "weight": 2}]


@pytest.fixture
def two_legs(monkeypatch):
    specs = {"A.py": _leg_spec(1), "B.py": _leg_spec(2, multi_day=True)}
    _install(monkeypatch, specs)
    return specs


def _run(**kw):
    return B.run_book(LEGS, date_from="2020-01-01", date_to="2021-03-31", lockbox_months=3, **kw)


# ------------------------------------------------------------------ 1. off = unchanged; x1.0 = identical
def test_no_block_reports_no_sizing_and_a_unit_block_changes_nothing(two_legs):
    plain = _run()
    unit = _run(book_sizing={"mode": "vt", "lo": 1.0, "hi": 1.0})
    assert "book_sizing" not in plain["book"]
    assert unit["book"]["book_sizing"]["avg_multiplier_trades"] == 1.0
    for k in ("whole", "pre_lockbox", "lockbox"):
        assert unit["book"][k] == plain["book"][k]
        assert unit["book"]["mtm"][k] == plain["book"]["mtm"][k]
    assert unit["book"]["book_sizing"]["raw_twin"]["whole"] == plain["book"]["whole"]
    assert unit["book"]["book_sizing"]["raw_twin"]["mtm"]["whole"] == plain["book"]["mtm"]["whole"]


def _expected_net(spec, mult, weight, m):
    """Sum over a leg's trades of m(entry day) x closed dollars."""
    lut = {np.datetime64(d.date(), "D"): v for d, v in m.items()}
    return sum(lut.get(spec["days_idx"][t[0]], 1.0) * t[2] * mult * weight for t in spec["trades"])


def test_a_flat_half_clip_halves_every_trade_after_warm_up_and_none_during_it(two_legs):
    """V2's rule: m = 1.0 until its reference exists (lookback + ref // 2 index days), the clip after."""
    half = _run(book_sizing={"mode": "vt", "lo": 0.5, "hi": 0.5})
    plain = _run()
    unsized = [p for leg in ("A.py", "B.py")
               for p in [B._mtm_increments(two_legs[leg]["days_idx"], two_legs[leg]["close"],
                                           [(t, 1.0) for t in two_legs[leg]["trades"]], 20.0,
                                           1.0 if leg == "A.py" else 2.0)[0]]]
    entries = [two_legs[leg]["days_idx"][t[0]] for leg in ("A.py", "B.py") for t in two_legs[leg]["trades"]]
    m, _ = BS.multipliers(BS.check_config({"mode": "vt", "lo": 0.5, "hi": 0.5}), unsized,
                          "2020-01-01", "2021-03-31")
    warm = 20 + 250 // 2
    assert (m.iloc[:warm] == 1.0).all() and (m.iloc[warm:] == 0.5).all()
    want = _expected_net(two_legs["A.py"], 20.0, 1.0, m) + _expected_net(two_legs["B.py"], 20.0, 2.0, m)
    assert half["book"]["whole"]["total_pnl"] == pytest.approx(want, abs=0.05)
    assert half["book"]["whole"]["total_pnl"] != pytest.approx(plain["book"]["whole"]["total_pnl"], abs=1.0)


# ------------------------------------------------------------------ 2. the live VT shadow's arithmetic
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_vt_multipliers_equal_the_live_shadow(seed):
    from api.book_shadow import vt_multipliers as shadow
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=900)
    x = rng.normal(0, 1000, len(idx)) * np.where(rng.random(len(idx)) < 0.2, 0.0, 1.0)   # zero days included
    x[400:430] *= 5.0                                                                       # a wild stretch
    M = pd.Series(x, index=idx)
    pd.testing.assert_series_equal(BS.vt_multipliers(M), shadow(M))


# ------------------------------------------------------------------ 3. causal
def test_the_multiplier_for_a_day_ignores_that_day_and_everything_after():
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2018-01-01", periods=600)
    M = pd.Series(rng.normal(0, 500, len(idx)), index=idx)
    base = BS.vt_multipliers(M)
    for cut in (300, 450, 599):
        M2 = M.copy()
        M2.iloc[cut:] = rng.normal(0, 50000, len(idx) - cut)          # rewrite day `cut` onward
        alt = BS.vt_multipliers(M2)
        pd.testing.assert_series_equal(base.iloc[:cut + 1], alt.iloc[:cut + 1])


# ------------------------------------------------------------------ 4. entry-day sizing, money identity
def test_each_trade_is_sized_at_its_entry_day_and_its_marks_still_sum_to_its_closed_dollars(two_legs):
    cfg = BS.check_config({"mode": "vt"})
    st = two_legs["B.py"]
    state = {"days_idx": st["days_idx"], "sess_idx": None, "last": len(st["days_idx"]) - 1, "close": st["close"],
             "sized": [(t, 1.0) for t in st["trades"]], "mult": 20.0, "weight": 2.0, "plugin_marks": None,
             "usd_units": False, "mtm_failed": False}
    # a multiplier that differs on every day, so a mark priced at any day but the entry day would show
    days = pd.DatetimeIndex(np.unique(st["days_idx"]))
    m = pd.Series(np.round(np.linspace(0.5, 2.0, len(days)), 1), index=days)
    lut = {np.datetime64(d.date(), "D"): v for d, v in m.items()}
    out, _, mtm, sizes = BS.resize(state, lambda t: lut[BS.entry_day(state, t)])
    multi = [t for t in st["trades"] if st["days_idx"][t[0]] != st["days_idx"][t[1]]]
    assert multi, "the fixture must hold multi-day trades"
    for t in multi:
        f = lut[BS.entry_day(state, t)]
        one, _, one_mtm, _ = BS.resize({**state, "sized": [(t, 1.0)]}, lambda _t: f)
        unit, _, unit_mtm, _ = BS.resize({**state, "sized": [(t, 1.0)]}, lambda _t: 1.0)
        assert len(one_mtm) > 2                                            # marked on every day it was open
        for (d1, a), (d2, b) in zip(one_mtm, unit_mtm):
            assert d1 == d2 and a == pytest.approx(f * b, abs=1e-9)        # ONE multiplier on every mark
        assert sum(p for _, p in one_mtm) == pytest.approx(one[0][1], abs=1e-9)
    assert sum(p for _, p in mtm) == pytest.approx(sum(p for _, p in out), abs=1e-6)
    assert cfg["lookback"] == 20 and cfg["ref"] == 250


def test_a_sized_book_keeps_net_identical_both_readings_and_reports_its_raw_twin(two_legs):
    plain = _run()
    vt = _run(book_sizing={"mode": "vt"})
    bs = vt["book"]["book_sizing"]
    assert vt["book"]["whole"]["total_pnl"] == pytest.approx(vt["book"]["mtm"]["whole"]["total_pnl"], abs=0.05)
    assert bs["raw_twin"]["whole"] == plain["book"]["whole"]
    assert bs["raw_twin"]["mtm"]["lockbox"] == plain["book"]["mtm"]["lockbox"]
    assert 0.5 <= bs["avg_multiplier_trades"] <= 2.0
    assert bs["days_at_lo"] + bs["days_at_hi"] > 0                       # the wild stretch moved it
    assert vt["book"]["whole"]["total_pnl"] != plain["book"]["whole"]["total_pnl"]
    assert all("_state" not in l for l in vt["book"]["legs"])             # no arrays leak into the result


# ------------------------------------------------------------------ 5. selection and loud failures
def test_only_the_selected_leg_is_sized(two_legs):
    plain = _run()
    one = _run(book_sizing={"mode": "vt", "legs": ["B.py"], "lo": 0.5, "hi": 0.5})
    legs_plain = {l["strategy"]: l["net"] for l in plain["book"]["legs"]}
    legs_one = {l["strategy"]: l["net"] for l in one["book"]["legs"]}
    assert legs_one["A.py"] == legs_plain["A.py"]
    assert legs_one["B.py"] != pytest.approx(legs_plain["B.py"], abs=1.0)
    assert [x["strategy"] for x in one["book"]["book_sizing"]["legs_sized"]] == ["B.py"]
    # signal "book" (default) reads BOTH legs' volatility even when only B is sized
    sp = two_legs
    unsized = [B._mtm_increments(sp[k]["days_idx"], sp[k]["close"], [(t, 1.0) for t in sp[k]["trades"]], 20.0, w)[0]
               for k, w in (("A.py", 1.0), ("B.py", 2.0))]
    entries = [sp["B.py"]["days_idx"][t[0]] for t in sp["B.py"]["trades"]]
    m, _ = BS.multipliers(BS.check_config({"mode": "vt", "lo": 0.5, "hi": 0.5}), unsized,
                          "2020-01-01", "2021-03-31")
    assert legs_one["B.py"] == pytest.approx(_expected_net(sp["B.py"], 20.0, 2.0, m), abs=0.05)


@pytest.mark.parametrize("bad", [
    {"mode": "volcano"}, {"mode": "vt", "lookbak": 20}, {"mode": "vt", "lo": 2.0, "hi": 1.0},
    {"mode": "vt", "legs": ["NOPE.py"]}, {"mode": "vt", "legs": [5]}, {"mode": "vt", "signal": "moon"}, "vt",
])
def test_a_block_the_engine_cannot_read_fails_instead_of_running_unsized(two_legs, bad):
    with pytest.raises(ValueError):
        _run(book_sizing=bad)


# ------------------------------------------------------------------ 6. refusals that keep the signal valued-daily (review 2026-10-03)
@pytest.mark.parametrize("bad_info", [{"mtm_error": "ValueError: boom"}, {"mtm_unmarked": 3}, {"source": "db_noadj_rth"}])
def test_a_degraded_signal_leg_is_refused(bad_info):
    legs = [{"strategy": "A.py", "source": "db_adj_rth"}]
    info = [{"strategy": "A.py", "source": "db_adj_rth", **bad_info}]
    with pytest.raises(ValueError):
        BS.signal_guard(legs, info, [0])
    BS.signal_guard(legs, [{"strategy": "A.py", "source": "db_adj_rth"}], [0])        # a clean leg passes


# ------------------------------------------------------------------ 7. an entry day off the index reads what the live shadow would
def test_an_off_index_entry_day_reads_the_shadow_insertion_value():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2019-01-01", periods=500)
    M = pd.Series(rng.normal(0, 800, len(idx)), index=idx)
    cfg = BS.check_config({"mode": "vt"})
    m = BS.vt_multipliers(M)
    for sunday in (pd.Timestamp("2019-09-08"), pd.Timestamp("2020-06-14")):
        assert sunday not in idx
        M2 = M.reindex(M.index.union(pd.DatetimeIndex([sunday]))).fillna(0.0)          # book_shadow.vt_multiplier_for
        want = float(BS.vt_multipliers(M2).loc[sunday])
        assert BS.multiplier_on(m, M, cfg, sunday) == want
    beyond = idx[-1] + pd.Timedelta(days=3)
    M3 = M.reindex(M.index.union(pd.DatetimeIndex([beyond]))).fillna(0.0)
    assert BS.multiplier_on(m, M, cfg, beyond) == float(BS.vt_multipliers(M3).loc[beyond])


# ------------------------------------------------------------------ 8. the per-stretch yardstick, sized and unsized
def test_stretch_readings_are_reported_for_sized_and_raw(two_legs):
    vt = _run(book_sizing={"mode": "vt", "stretches": [{"name": "late", "from": "2020-09-01", "to": "2021-02-26"}]})
    st = vt["book"]["book_sizing"]["stretches"][0]
    assert st["name"] == "late" and st["sized"]["from"] >= "2020-09-01" and st["raw_twin"]["to"] <= "2021-02-26"
    assert st["sized"]["net"] != st["raw_twin"]["net"]
    for side in ("sized", "raw_twin"):
        r = st[side]
        if r["roc_30k"] is not None:
            yrs = (pd.Timestamp(r["to"]) - pd.Timestamp(r["from"])).days / 365.25
            assert r["roc_30k"] == pytest.approx(30.0 * (r["net"] / yrs) / r["max_drawdown"], rel=1e-3)
