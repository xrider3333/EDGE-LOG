"""MATCHED READ r1 harness (tools/rocfrontier/r17_matched.py) - the statistics, the swap null, the family read and the refusals on hand-checkable
inputs; the harness's own smoke in both synthetic worlds. No box data, no market data.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "rocfrontier"))
import r17_matched as R  # noqa: E402
import r11_risk as R11  # noqa: E402

SMOKE_GLOBALS = ("OUT", "CHECK_REFS", "SMOKE_TBD_OK", "NDRAW", "CHUNK")


def _pin_globals(monkeypatch):
    """smoke() rebinds module globals; pinning them to their current values makes monkeypatch restore them after the test."""
    for g in SMOKE_GLOBALS:
        monkeypatch.setattr(R, g, getattr(R, g))


def _manifest(path, n=None, keel_nan=3, keel_line=False, **edits):
    """A valid manifest: every weekday of the walk-forward (or n rows from WF0), keel_d NaN on the first keel_nan rows; `edits` overwrite whole columns."""
    dates = pd.bdate_range(R.WF0, R.WF1) if n is None else pd.bdate_range(R.WF0, periods=n)
    n = len(dates)
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], "b463": rng.normal(50, 900, n), "orb463": rng.normal(20, 500, n),
                       "orb314": rng.normal(20, 500, n), "orb239": rng.normal(20, 500, n), "keel_d": rng.normal(10, 300, n)})
    df.loc[: keel_nan - 1, "keel_d"] = np.nan
    if keel_line:
        df["keel_line"] = df["b463"] + 1.0
        df.loc[: keel_nan - 1, "keel_line"] = np.nan
    for c, v in edits.items():
        df[c] = v
    df.to_csv(path, index=False)
    return df


def test_smoke_planted_world(tmp_path, monkeypatch):
    _pin_globals(monkeypatch)
    s = R.smoke(str(tmp_path / "smoke"), "planted")
    assert s["lines_in"] == ["ORB314", "ORB239", "KEEL"] and s["keel_parity"] == "not supplied" and s["keel_flag"]
    out = tmp_path / "smoke" / "matched"
    for n in ("MATCHED.txt", "matched.json", "power.csv", "parity.json"):
        assert (out / n).exists()
    txt = (out / "MATCHED.txt").read_text(encoding="utf-8")
    txt.encode("ascii")
    assert "TRUTH is an UPPER bound" in txt and txt.strip().splitlines()[-1].startswith("wall time")
    assert "per READ, not per look at the forward record" in txt and "NESTED in the reference" in txt      # the two fixed caveats
    assert "HEADLINE" in txt and txt.index("HEADLINE") > txt.index("minTRL")                     # the headline prints last
    assert "MEAN for KEEL" in txt and "T_self (report only, never in the family or the headline)" in txt
    pw = pd.read_csv(out / "power.csv")
    assert list(pw.columns)[:7] == ["line", "statistic", "horizon", "shrink", "false_pass", "power", "crit"]
    assert set(pw["statistic"]) == set(R.FAMILIES) and set(pw["horizon"]) == set(R.HORIZONS) and set(pw["shrink"]) == set(R.SHRINK)
    assert set(pw["own_stat"]) == {"M1", "M2", "M3", "R2", "MEAN", "T_self"} and set(pw.loc[pw["own_stat"] == "T_self", "statistic"]) == {R.PRIMARY}
    ts = pw[pw["own_stat"] == "T_self"].pivot(index="horizon", columns="shrink", values="power")
    assert (ts[1.0] == ts[0.5]).all()                                                             # scale-free: the half edge cannot show
    assert all("T_self" not in s["families"][S][n]["members"] for S in R.FAMILIES for n in R.HORIZONS)
    assert not (tmp_path / "smoke" / "matched" / "READY").exists()                               # the smoke ends on the READY-missing refusal


def test_smoke_null_world(tmp_path, monkeypatch):
    _pin_globals(monkeypatch)
    s = R.smoke(str(tmp_path / "smoke"), "null")
    f = s["families"]["M1"][252]["lines"]["ORB314"]
    assert f["power"][1.0] <= 0.15 and abs(f["null_mean"]) <= 0.25 * f["sd_null"]
    cal = s["null_calibration"]
    assert cal["n_worlds"] == 30 and 0.0 <= cal["share_orb314"] <= 0.17 and cal["share_family"] <= 0.25 and cal["passes_family"] >= cal["passes_orb314"]
    assert R.CHECK_REFS is False and R.NDRAW == 400                                              # inside the test the smoke settings are in force


def test_dsd_and_the_matched_statistics_by_hand():
    a = np.array([-100.0, 50.0, -200.0, 300.0, -50.0, 10.0])
    b = np.array([-40.0, 50.0, -80.0, 150.0, -50.0, 10.0])
    assert R.dsd(a) == pytest.approx(np.sqrt(52500.0 / 6.0)) and R.dsd(b) == pytest.approx(np.sqrt(10500.0 / 6.0))
    assert R.m1(a, b) == pytest.approx(np.sqrt(0.2) - 1.0)                                      # DSD(b) / DSD(a) - 1 = sqrt(1750 / 8750) - 1
    assert R.m2(a, b) == pytest.approx(60.0)                                                    # loss days of a: (60 + 120 + 0) / 3
    assert R.m3(a, b) == pytest.approx(102.5)                                                   # q05: a -200 + 0.25 x 100 = -175; b -80 + 0.25 x 30 = -72.5
    assert R.r2(a, b) == pytest.approx(30.0)
    w = R.m1_ex_worst(a, b, pd.bdate_range("2020-01-01", periods=6))                             # both legs' worst day is row 2; without it: sqrt(820 / 2500) - 1
    assert w["a_worst_row"] == w["b_worst_row"] == 2 and w["same_row"] and w["a_worst_day"] == "2020-01-03"
    assert w["M1"] == pytest.approx(np.sqrt(0.2) - 1.0) and w["M1_ex_a_worst"] == w["M1_ex_b_worst"] == w["M1_ex_both"] == pytest.approx(np.sqrt(0.328) - 1.0)
    w2 = R.m1_ex_worst(a, np.array([-40.0, 50.0, -80.0, 150.0, -300.0, 10.0]))                   # b's worst day is row 4: dropped from both legs
    assert w2["b_worst_row"] == 4 and not w2["same_row"] and w2["M1_ex_b_worst"] == pytest.approx(np.sqrt((1600 + 6400) / 5.0) / np.sqrt((10000 + 40000) / 5.0) - 1.0)
    assert np.isnan(R.m2(np.array([1.0, 2.0]), np.array([3.0, 4.0])))                            # no losing day of a -> NaN
    assert np.isnan(R.m1(np.array([1.0, 2.0]), np.array([3.0, -4.0])))                           # DSD(a) 0 -> NaN
    d = np.array([np.nan, 1.0, 2.0, 3.0, 0.0, 4.0])
    assert R.keel_mean(d) == pytest.approx(2.0) and R.keel_t(d) == pytest.approx(2.0 / (np.sqrt(2.5) / np.sqrt(5.0))) and R.keel_sum(d) == pytest.approx(10.0)
    assert np.isnan(R.keel_t(np.array([np.nan, 5.0]))) and np.isnan(R.keel_t(np.array([2.0, 2.0, 2.0]))) and np.isnan(R.keel_mean(np.array([np.nan, np.nan])))
    assert R.keel_mean(np.stack([d, 2.0 * d])) == pytest.approx([2.0, 4.0]) and R.keel_t(2.0 * d) == pytest.approx(R.keel_t(d))   # MEAN scales, T_self does not
    ks = R.keel_stats(np.stack([d, d]), 6)
    assert set(ks) == {"MEAN", "R2", "T_self"} and ks["MEAN"][0] == pytest.approx(2.0) and R.keel_stats(d, 3)["R2"] == pytest.approx(3.0)
    st = R.orb_stats(np.stack([a, a]), np.stack([b, b]), 6)                                     # vectorised over draws, first n rows
    assert st["M1"].shape == (2,) and st["M1"][1] == pytest.approx(np.sqrt(0.2) - 1.0) and st["M3"][0] == pytest.approx(102.5)
    assert R.orb_stats(a, b, 3)["R2"] == pytest.approx(180.0)                                    # the first 3 rows only
    assert R.SIGN["M1"] == -1.0 and all(R.SIGN[k] == 1.0 for k in ("M2", "M3", "R2", "MEAN", "T_self"))
    assert R.own_stat("ORB314", "M2") == "M2" and R.own_stat("KEEL", "M2") == "MEAN" and R.own_stat("KEEL", "R2") == "R2"
    assert R.REPORT_ONLY == "T_self" and all(R.own_stat("KEEL", S) != "T_self" for S in R.FAMILIES) and R.kinds_of("KEEL") == ("MEAN", "R2", "T_self")


def test_block_draws_are_circular_blocks_with_one_shared_flag_each():
    rng = np.random.default_rng(1)
    idx, swap = R.block_draws(rng, 100, 5, 63, block=21)
    assert idx.shape == swap.shape == (5, 63) and idx.min() >= 0 and idx.max() < 100
    for j in range(3):                                                                           # each block runs consecutively mod N, one flag per block
        blk, fl = idx[:, 21 * j:21 * (j + 1)], swap[:, 21 * j:21 * (j + 1)]
        assert ((blk - blk[:, :1]) % 100 == np.arange(21)[None, :]).all() and (fl == fl[:, :1]).all()
    idx2, swap2 = R.block_draws(np.random.default_rng(1), 100, 5, 63, block=21)
    assert (idx == idx2).all() and (swap == swap2).all()                                         # the seed fixes the draw
    assert R.block_draws(rng, 100, 2, 50, block=21)[0].shape == (2, 50)                          # a horizon that is not a block multiple is cut


def test_the_swap_null_leaves_m1_centred_and_the_draws_are_deterministic():
    rng = np.random.default_rng(11)
    n = 900
    a = 30.0 + 500.0 * rng.standard_t(4, n)
    b = 30.0 + 500.0 * rng.standard_t(4, n)                                                      # an exchangeable partner: no edge either way
    bc = a.copy()
    cut = (a < 0) & (rng.random(n) < 0.3)
    bc[cut] = 0.4 * a[cut]                                                                       # a nested partner with a planted loss cut
    keel = np.where(rng.random(n) < 0.3, 300.0 + 800.0 * rng.standard_t(4, n), 0.0)              # a real KEEL edge: mean 300 on its trade days
    keel[:5] = np.nan                                                                            # the rows before KEEL's first day
    M = {"n": n, "orb463": a, "orb314": b, "orb239": bc, "keel_d": keel}
    raw, meta = R.simulate(M, ["ORB314", "ORB239", "KEEL"], ndraw=300, chunk=100, seed=3)
    assert meta["ndraw"] == 300 and meta["rows_per_draw"] == 756 and meta["blocks_per_draw"] == 36
    assert meta["keel_rows_eff"][756]["min"] <= meta["keel_rows_eff"][756]["mean"] <= 756 and meta["keel_rows_eff"][252]["mean"] > 240
    for line in ("ORB314", "ORB239"):
        x = raw["null"][line]["M1"][252]
        assert np.isfinite(x).all() and abs(x.mean()) <= 0.25 * x.std() and 0.4 <= np.mean(x > 0) <= 0.6, (line, x.mean(), x.std())
    for n_ in (504, 756):                                                                        # the sign flip alone centres KEEL's MEAN: without it the
        t = raw["null"]["KEEL"]["MEAN"][n_]                                                      # null mean would sit at the truth mean, many null sds up
        assert abs(t.mean()) <= 0.25 * t.std() and 0.4 <= np.mean(t > 0) <= 0.6, (n_, t.mean(), t.std())
        assert raw["truth_1"]["KEEL"]["MEAN"][n_].mean() > 2.0 * t.std(), (n_, raw["truth_1"]["KEEL"]["MEAN"][n_].mean(), t.std())
    ts = raw["null"]["KEEL"]["T_self"][504]
    assert abs(ts.mean()) <= 0.25 * ts.std() and 0.4 <= np.mean(ts > 0) <= 0.6
    assert raw["truth_1"]["ORB239"]["M1"][756].mean() < -2.0 * raw["null"]["ORB239"]["M1"][756].std()   # the planted cut shows at face value
    half = raw["truth_0.5"]["ORB239"]["M1"][756]
    assert half.mean() < 0 and half.mean() > raw["truth_1"]["ORB239"]["M1"][756].mean()          # half the edge: between the null and face value
    raw2, _ = R.simulate(M, ["ORB314", "ORB239", "KEEL"], ndraw=300, chunk=100, seed=3)
    assert (raw2["null"]["ORB314"]["M1"][252] == raw["null"]["ORB314"]["M1"][252]).all()          # SEED and CHUNK together fix every draw
    assert (raw2[R._variant_key(0.5)]["KEEL"]["MEAN"][756] == raw[R._variant_key(0.5)]["KEEL"]["MEAN"][756]).all()
    raw3, _ = R.simulate(M, ["ORB314"], ndraw=300, chunk=100, seed=3)
    assert (raw3["null"]["ORB314"]["M1"][252] == raw["null"]["ORB314"]["M1"][252]).all()          # a line left out does not move the others' draws
    assert not (R.simulate(M, ["ORB314"], ndraw=300, chunk=100, seed=4)[0]["null"]["ORB314"]["M1"][252] == raw["null"]["ORB314"]["M1"][252]).all()


def _fake_raw(rng, lines, ndraw, shift=1.5):
    raw = {}
    for v, off in (("null", 0.0), (R._variant_key(1.0), shift), (R._variant_key(0.5), shift / 2.0)):
        raw[v] = {l: {k: {n: 3.0 * rng.normal(0.0, 1.0, ndraw) + off * R.SIGN[k] + (0.7 if k == "M2" else 0.0) for n in R.HORIZONS}
                      for k in R.kinds_of(l)} for l in lines}
    return raw


def test_the_critical_value_is_the_95th_percentile_of_the_family_max_by_brute_force():
    rng = np.random.default_rng(5)
    lines, ndraw = ["ORB314", "ORB239", "KEEL"], 60
    raw = _fake_raw(rng, lines, ndraw)
    fam = R.family_read(raw, lines)
    for S in R.FAMILIES:
        for n in R.HORIZONS:
            members = [(l, R.own_stat(l, S)) for l in lines]
            z = {}
            for l, k in members:
                x = [R.SIGN[k] * v for v in raw["null"][l][k][n]]
                mu, sd = np.mean(x), np.std(x, ddof=1)
                z[l] = [(v - mu) / sd for v in x]
            maxz = [max(z[l][i] for l, _ in members) for i in range(ndraw)]
            c = np.percentile(maxz, 95)
            f = fam[S][n]
            assert f["crit"] == pytest.approx(c) and f["members"] == lines
            assert f["fwer"] == pytest.approx(sum(1 for m in maxz if m >= c) / ndraw) and f["fwer"] <= 0.05 + 1.0 / ndraw
            for l, k in members:
                r = f["lines"][l]
                assert r["own_stat"] == k and r["false_pass"] == pytest.approx(sum(1 for v in z[l] if v >= c) / ndraw) and r["false_pass"] <= f["fwer"]
                x = raw[R._variant_key(1.0)][l][k][n]
                mu, sd = np.mean([R.SIGN[k] * v for v in raw["null"][l][k][n]]), np.std([R.SIGN[k] * v for v in raw["null"][l][k][n]], ddof=1)
                assert r["power"][1.0] == pytest.approx(sum(1 for v in x if (R.SIGN[k] * v - mu) / sd >= c) / ndraw)
            assert sum(f["lines"][l]["false_pass"] for l, _ in members) >= f["fwer"] - 1e-12                 # union bound
    assert R.crit(np.array([1.0, 2.0, 3.0, 4.0, -np.inf]), 0.05) == pytest.approx(np.percentile([1.0, 2.0, 3.0, 4.0, -np.inf], 95))
    assert R.crit(np.array([1.0, 2.0, -np.inf, -np.inf]), 0.5) == pytest.approx(1.5)              # a percentile between -inf and a value falls back to the finite draws
    assert R.crit(np.array([1.0, 2.0, 3.0, 4.0, -np.inf, -np.inf, -np.inf]), 0.5) == pytest.approx(1.0)      # a finite one stands (the -inf draws never pass)


def test_min_trl_formula_by_hand_and_undefined_when_the_edge_is_not_positive():
    d = np.arange(1.0, 9.0)                                                                      # 1..8: symmetric, skew 0
    t = R.min_trl(d)
    mu, sd = 4.5, np.sqrt(6.0)
    sr = mu / sd
    kurt = np.mean(((d - mu) / sd) ** 4)
    want = 1.0 + (1.0 - 0.0 * sr + (kurt - 1.0) / 4.0 * sr ** 2) * (1.645 / sr) ** 2
    assert t["sr"] == pytest.approx(sr) and t["skew"] == pytest.approx(0.0, abs=1e-12) and t["kurt"] == pytest.approx(kurt)
    assert t["min_trl_rows"] == pytest.approx(want) and t["min_trl_months"] == pytest.approx(want / 21.0) and "rows" in t["printed"]
    g = np.random.default_rng(2).normal(0.02, 1.0, 200000)                                       # near-normal: kurt ~ 3 -> 1 + (1 + SR^2 / 2)(z / SR)^2
    tg = R.min_trl(g)
    assert tg["min_trl_rows"] == pytest.approx(1.0 + (1.0 - tg["skew"] * tg["sr"] + (tg["kurt"] - 1.0) / 4.0 * tg["sr"] ** 2) * (1.645 / tg["sr"]) ** 2)
    assert tg["min_trl_rows"] == pytest.approx(1.0 + (1.0 + 0.5 * tg["sr"] ** 2) * (1.645 / tg["sr"]) ** 2, rel=0.02)
    assert R.min_trl(np.array([-1.0, -2.0, 0.0, 1.0]))["printed"] == "undefined"                 # SR < 0
    assert R.min_trl(np.array([1.0, -1.0, 2.0, -2.0]))["printed"] == "undefined"                 # SR = 0
    assert R.min_trl(np.array([3.0, 3.0, 3.0, 3.0]))["printed"] == "undefined"                   # sd 0
    assert R.min_trl(np.array([1.0, np.nan, 2.0]))["printed"] == "undefined" and R.min_trl(np.array([1.0, np.nan, 2.0]))["n"] == 2
    assert R.min_trl(np.array([np.nan, 1.0, 2.0, 3.0, 4.0, 5.0]))["n"] == 5                       # NaN rows (KEEL before its first day) are dropped


def test_headline_reads_the_first_horizon_reaching_power():
    assert R.first_horizon({252: 0.3, 504: 0.55, 756: 0.9}, 0.5) == "24 months" and R.first_horizon({252: 0.3, 504: 0.55, 756: 0.9}, 0.8) == "36 months"
    assert R.first_horizon({252: 0.6, 504: 0.7, 756: 0.75}, 0.5) == "12 months" and R.first_horizon({252: 0.6, 504: 0.7, 756: 0.75}, 0.8) == "> 36 months"
    assert R.first_horizon({252: float("nan"), 504: 0.5}, 0.5) == "24 months" and R.first_horizon({}, 0.5) == "> 36 months"
    assert R.months(252) == 12 and R.months(504) == 24 and R.months(756) == 36
    rng = np.random.default_rng(9)
    lines = ["ORB314", "KEEL"]
    fam = R.family_read(_fake_raw(rng, lines, 80, shift=9.0), lines)                             # a huge shift: power 1 at every horizon
    H = R.headline(fam, lines)
    assert H["ORB314"]["statistic"] == "M1" and H["KEEL"]["statistic"] == "MEAN" and H["ORB314"]["family"] == R.PRIMARY == "M1"
    assert "KEEL_T_self" in fam["M1"][252]["report_only"] and fam["M2"][252]["report_only"] == {}      # T_self is read only beside the primary family
    assert H["ORB314"]["months"][1.0] == {"0.5": "12 months", "0.8": "12 months"} and H["KEEL"]["q16_months"] == "> 36"
    assert H["ORB314"]["power"][1.0][252] == fam["M1"][252]["lines"]["ORB314"]["power"][1.0]
    assert R.Q16_MONTHS == {"ORB314": "> 36", "ORB239": "> 36", "KEEL": "> 36"}


def test_manifest_format_refusals(tmp_path):
    p = str(tmp_path / "m.csv")
    _manifest(p)
    M = R.read_manifest(p)
    assert M["n"] == M["expected_rows"] == 2346 and M["keel_first_row"] == 3 and M["keel_rows"] == 2343 and M["keel_line"] is None and M["sha"] == R11.sha_lf(p)
    assert str(M["dates"][0].date()) == R.WF0 and str(M["dates"][-1].date()) == "2025-06-27" and M["weekend_rows"] == 0
    _manifest(p, keel_line=True)
    assert R.read_manifest(p)["keel_line"] is not None
    df = _manifest(p)
    last = len(df) - 1
    df.drop(columns=["orb239"]).to_csv(p, index=False)
    with pytest.raises(SystemExit, match="lacks column"):
        R.read_manifest(p)
    df2 = df.copy()
    df2.loc[5, "date"] = df2.loc[4, "date"]                                                     # a repeated date
    df2.to_csv(p, index=False)
    with pytest.raises(SystemExit, match="strictly increasing"):
        R.read_manifest(p)
    df2 = df.copy()
    df2.loc[last, "date"] = "2025-06-30"                                                        # the day after WF1 (the lockbox)
    df2.to_csv(p, index=False)
    with pytest.raises(SystemExit, match="outside the walk-forward"):
        R.read_manifest(p)
    df2 = df.copy()
    df2.loc[0, "date"] = "2016-06-30"                                                            # the day before WF0
    df2.to_csv(p, index=False)
    with pytest.raises(SystemExit, match="outside the walk-forward"):
        R.read_manifest(p)
    for c in R.NONAN:
        df2 = df.copy()
        df2.loc[7, c] = np.nan
        df2.to_csv(p, index=False)
        with pytest.raises(SystemExit, match=f"column {c} is NaN"):
            R.read_manifest(p)
    df2 = df.copy()
    df2.loc[10, "keel_d"] = np.nan                                                               # NaN after KEEL's first row
    df2.to_csv(p, index=False)
    with pytest.raises(SystemExit, match="keel_d is NaN at row 10"):
        R.read_manifest(p)
    df2 = df.copy()
    df2["keel_d"] = np.nan
    df2.to_csv(p, index=False)
    with pytest.raises(SystemExit, match="no finite row"):
        R.read_manifest(p)
    with pytest.raises(SystemExit, match="not found"):
        R.read_manifest(str(tmp_path / "absent.csv"))
    _manifest(p, n=1)
    with pytest.raises(SystemExit, match="fewer than 2"):
        R.read_manifest(p)


def test_manifest_must_cover_the_whole_walk_forward(tmp_path):
    p = str(tmp_path / "m.csv")
    df = _manifest(p)
    df.iloc[1:].to_csv(p, index=False)                                                           # starts on 2016-07-04
    with pytest.raises(SystemExit, match="must cover the whole walk-forward.*need 2016-07-01"):
        R.read_manifest(p)
    df.iloc[:-1].to_csv(p, index=False)                                                          # ends on 2025-06-26
    with pytest.raises(SystemExit, match="must cover the whole walk-forward.*need 2025-06-27"):
        R.read_manifest(p)
    _manifest(p, n=30)                                                                           # a short export
    with pytest.raises(SystemExit, match="must cover the whole walk-forward"):
        R.read_manifest(p)
    df.drop(index=[100, 101]).to_csv(p, index=False)                                              # two interior rows missing (holidays): accepted, noted
    M = R.read_manifest(p)
    assert M["n"] == 2344 and M["expected_rows"] == 2346 and str(M["dates"][0].date()) == R.WF0 and str(M["dates"][-1].date()) == "2025-06-27"
    assert len(pd.bdate_range(R.WF0, R.WF1)) == 2346


def test_keel_mean_bites_under_the_half_edge_while_t_self_does_not():
    rng = np.random.default_rng(21)
    n = 1200
    a = 30.0 + 500.0 * rng.standard_t(4, n)
    keel = np.where(rng.random(n) < 0.3, 400.0 + 900.0 * rng.standard_t(4, n), 0.0)
    keel[:7] = np.nan
    M = {"n": n, "orb463": a, "orb314": a.copy(), "orb239": a.copy(), "keel_d": keel}
    raw, _ = R.simulate(M, ["KEEL"], ndraw=200, chunk=100, seed=8)
    for n_ in R.HORIZONS:
        full, half = raw["truth_1"]["KEEL"]["MEAN"][n_], raw["truth_0.5"]["KEEL"]["MEAN"][n_]
        assert np.allclose(half, 0.5 * full) and not np.allclose(half, full)                      # the paired mean halves with the edge
        assert np.allclose(raw["truth_0.5"]["KEEL"]["T_self"][n_], raw["truth_1"]["KEEL"]["T_self"][n_])   # the self-normalised t does not move
        assert np.allclose(raw["truth_0.5"]["KEEL"]["R2"][n_], 0.5 * raw["truth_1"]["KEEL"]["R2"][n_])
    fam = R.family_read(raw, ["KEEL"])
    for n_ in R.HORIZONS:
        r = fam["M1"][n_]["lines"]["KEEL"]
        ro = fam["M1"][n_]["report_only"]["KEEL_T_self"]
        assert r["own_stat"] == "MEAN" and r["truth_mean"][0.5] == pytest.approx(0.5 * r["truth_mean"][1.0]) and r["power"][0.5] <= r["power"][1.0]
        assert ro["own_stat"] == "T_self" and ro["power"][1.0] == ro["power"][0.5] and ro["false_pass"] < 0.5    # not a member: its pass set is not inside the family's
        assert fam["M1"][n_]["members"] == ["KEEL"]
    assert fam["M1"][756]["lines"]["KEEL"]["power"][1.0] > fam["M1"][756]["lines"]["KEEL"]["power"][0.5]   # with this edge the half edge reads weaker
    H = R.headline(fam, ["KEEL"])
    assert H["KEEL"]["statistic"] == "MEAN" and "T_self" not in str(H)


def test_prereg_sha_refusals(tmp_path, monkeypatch):
    probe = tmp_path / "prereg.txt"
    probe.write_text("the plan\r\nline two\r\n")
    sha = R11.sha_lf(str(probe))
    assert R.check_prereg(str(probe), sha) == sha                                                # CRLF-insensitive
    with pytest.raises(SystemExit, match="not the registered"):
        R.check_prereg(str(probe), "0" * 64)
    monkeypatch.setattr(R, "SMOKE_TBD_OK", False)
    with pytest.raises(SystemExit, match="TBD"):
        R.check_prereg(str(probe), "TBD")
    monkeypatch.setattr(R, "SMOKE_TBD_OK", True)
    assert R.check_prereg(str(probe), "TBD") == "TBD"                                            # only the smoke tolerates TBD
    assert R.check_prereg(str(tmp_path / "absent.txt"), "TBD") == "TBD"
    monkeypatch.setattr(R, "SMOKE_TBD_OK", False)
    with pytest.raises(SystemExit, match="not found"):
        R.check_prereg(str(tmp_path / "absent.txt"), "0" * 64)
    probe.write_text("the plan\nline two\naddendum\n")
    with pytest.raises(SystemExit, match="the plan changed"):
        R.check_prereg(str(probe), sha)
    assert R.PREREG_SHA == "TBD" or len(R.PREREG_SHA) == 64
    if R.PREREG_SHA != "TBD":                                                                    # once registered, the file in the repo must hash to it
        assert R11.sha_lf(R.PREREG) == R.PREREG_SHA


def test_run_refuses_without_ready_and_when_the_prereg_or_the_manifest_changed(tmp_path, monkeypatch):
    probe = tmp_path / "prereg.txt"
    probe.write_text("the plan\n")
    monkeypatch.setattr(R, "PREREG", str(probe))
    monkeypatch.setattr(R, "PREREG_SHA", R11.sha_lf(str(probe)))
    monkeypatch.setattr(R, "OUT", str(tmp_path / "out"))
    monkeypatch.setattr(R, "SMOKE_TBD_OK", False)
    man = str(tmp_path / "m.csv")
    _manifest(man)
    with pytest.raises(SystemExit, match="parity has not passed"):
        R.run(man)
    os.makedirs(R.OUT)
    good = {"parity": "passed", "manifest_sha256": R11.sha_lf(man), "prereg_sha256": R.PREREG_SHA, "lines_in": ["ORB314"]}
    with open(R._ready_path(), "w") as f:
        f.write(json.dumps(dict(good, prereg_sha256="0" * 64)))
    with pytest.raises(SystemExit, match="prereg changed"):
        R.run(man)
    with open(R._ready_path(), "w") as f:
        f.write(json.dumps(dict(good, manifest_sha256="0" * 64)))
    with pytest.raises(SystemExit, match="manifest changed"):
        R.run(man)
    with open(R._ready_path(), "w") as f:
        f.write(json.dumps(good))
    _manifest(man, b463=1.0)                                                                     # the file changed after parity
    with pytest.raises(SystemExit, match="manifest changed"):
        R.run(man)
    with pytest.raises(SystemExit, match="manifest not found"):
        R.run(str(tmp_path / "absent.csv"))
    _manifest(man)
    with open(R._ready_path(), "w") as f:
        f.write(json.dumps(dict(good, lines_in=[])))
    with pytest.raises(SystemExit, match="lists no line"):
        R.run(man)
    monkeypatch.setattr(R, "PREREG_SHA", "TBD")
    with pytest.raises(SystemExit, match="TBD"):
        R.run(man)
    with pytest.raises(SystemExit, match="TBD"):
        R.parity(man)


def test_parity_excludes_a_line_that_misses_and_refuses_on_b463(tmp_path, monkeypatch):
    probe = tmp_path / "prereg.txt"
    probe.write_text("the plan\n")
    monkeypatch.setattr(R, "PREREG", str(probe))
    monkeypatch.setattr(R, "PREREG_SHA", R11.sha_lf(str(probe)))
    monkeypatch.setattr(R, "OUT", str(tmp_path / "out"))
    monkeypatch.setattr(R, "CHECK_REFS", True)
    man = str(tmp_path / "manifest_smoke.csv")
    R.synth_manifest(man, "planted")
    M = R.read_manifest(man)
    assert M["n"] == 2346 and M["keel_first"] == "2016-07-27" and M["keel_rows"] == 2346 - 18
    fig = lambda x, dates: R.figures(x, dates)
    g463, g314 = fig(M["b463"], M["dates"]), fig(R.line_series(M, "ORB314"), M["dates"])
    REF0 = dict(R.REF)                                                                           # the recorded figures, kept apart from the patched dict
    ref = dict(R.REF)
    ref["b463"], ref["ORB314"] = (g463["roc"], g463["sort"], g463["dd"]), (g314["roc"], g314["sort"], g314["dd"])
    monkeypatch.setattr(R, "REF", ref)                                                           # ORB239 keeps the recorded figure: it misses
    out = R.parity(man)
    assert out["lines_in"] == ["ORB314", "KEEL"] and "ORB239" in out["lines_out"] and "parity miss" in out["lines_out"]["ORB239"]
    assert out["keel_parity"] == "not supplied" and out["keel_flag"] and out["figures"]["b463"]["ok"] and not out["figures"]["ORB239"]["ok"]
    with open(R._ready_path()) as f:
        ready = json.load(f)
    assert ready["lines_in"] == ["ORB314", "KEEL"] and ready["manifest_sha256"] == M["sha"] and ready["prereg_sha256"] == R.PREREG_SHA
    # a supplied keel_line is checked on its own rows, loosely, and labelled with its convention
    df = pd.read_csv(man)
    kl = df["b463"].to_numpy(float).copy()
    kl[:18] = np.nan
    df["keel_line"] = kl
    df.to_csv(man, index=False)
    M2 = R.read_manifest(man)
    gk = fig(M2["keel_line"][18:], M2["dates"][18:])
    ref["KEEL"] = (gk["roc"] + 0.5, gk["sort"] + 0.04, gk["dd"] + 9.0)                           # inside KEEL_TOL, outside TOL
    out = R.parity(man)
    assert out["lines_in"] == ["ORB314", "KEEL"] and out["keel_parity"] == "checked ok" and not out["keel_flag"]
    assert out["figures"]["KEEL"]["convention"] == "keel_eval convention" and out["figures"]["KEEL"]["rows"] == 2346 - 18
    ref["KEEL"] = (gk["roc"] + 2.0, gk["sort"], gk["dd"])
    out = R.parity(man)
    assert out["lines_in"] == ["ORB314"] and "KEEL" in out["lines_out"]
    ref["ORB314"] = REF0["ORB314"]
    with pytest.raises(SystemExit, match="no line reproduces"):
        R.parity(man)
    assert not os.path.exists(R._ready_path())
    ref["b463"] = REF0["b463"]
    with pytest.raises(SystemExit, match="FAILED on b463"):
        R.parity(man)
    assert not os.path.exists(R._ready_path()) and not json.load(open(os.path.join(R.OUT, "parity.json")))["pass"]
    monkeypatch.setattr(R, "CHECK_REFS", False)                                                  # the smoke setting: figures reported, nothing refused
    assert R.parity(man)["lines_in"] == ["ORB314", "ORB239", "KEEL"]
