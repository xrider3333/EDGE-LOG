"""BOOK HEALTH r1 harness (tools/rocfrontier/r18_health.py) - the monitors on hand-checkable inputs, no box data.

The harness's own `smoke` runs the whole round on a synthetic Book-like reference and re-does h1, a q99 and a count band by hand from the
saved block starts; these pin the registered rules a daily read rests on: the CUSUM recursion, the h1 search (the smallest grid value
meeting the level), the circular block bootstrap (rows and leg counts drawn together), the drawdown prefix quantiles, the Poisson band,
the H2 / H3 state rules, the exit-row leg counts, the forward-csv refusals, and the READY / prereg refusals.
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "rocfrontier"))
import r18_health as H  # noqa: E402
import r11_risk as R11  # noqa: E402


def test_cusum_recursion_by_hand_on_five_rows():
    z = np.array([0.2, -1.0, -2.0, 0.5, -3.0])                                      # C_t = max(0, C_(t-1) - z_t - 0.5), C_0 = 0
    C = H.cusum(z, k=0.5)
    assert np.allclose(C, [0.0, 0.5, 2.0, 1.0, 3.5])                                   # 0; 0+1-.5; .5+2-.5; 2-.5-.5; 1+3-.5
    assert np.allclose(H.cusum(np.vstack([z, -z]), 0.5)[0], C) and np.allclose(H.cusum(np.vstack([z, -z]), 0.5)[1], [0.0, 0.0, 0.0, 0.0, 0.0])
    assert H.cusum(z, k=0.0)[-1] == pytest.approx(5.5)                                 # a zero reference value only adds the losses up
    assert np.allclose(H.cusum(z, k=0.1), [0.0, 0.9, 2.8, 2.2, 5.1])                   # the calibrated k is small: 0+1-.1; .9+2-.1; 2.8-.5-.1; 2.2+3-.1
    with pytest.raises(TypeError):
        H.cusum(z)                                                                     # k is always passed, never a default
    assert list(H.first_cross(C, 2.0)) == [3] and list(H.first_cross(C, 3.5)) == [5] and list(H.first_cross(C, 4.0)) == [0]
    assert list(H.first_cross(np.vstack([C, C - 10.0]), 1.0)) == [3, 0]                # row 3 is the first at or above 1.0 (0.5 is not)
    # a forward mean below the reference drifts the chart up: the same noise shifted down alarms earlier, never later
    rng = np.random.default_rng(3)
    z = rng.normal(0.0, 1.0, (50, 300))
    d0, d1 = H.first_cross(H.cusum(z, 0.5), 5.0), H.first_cross(H.cusum(z - 1.0, 0.5), 5.0)
    assert (d1 > 0).all() and all(b <= a for a, b in zip(d0, d1) if a > 0)
    # the day quantiles run over ALL draws, a never-alarmed draw beyond the horizon (inverted-cdf rule): 10 draws, 3 alarm on days 3, 5, 9
    first = np.array([0, 5, 3, 0, 9, 0, 0, 0, 0, 0])
    assert H.day_quantile(first, 0.1) == 3.0 and H.day_quantile(first, 0.3) == 9.0 and H.day_quantile(first, 0.5) is None
    days = np.where(first > 0, first, np.inf).astype(float)
    assert H.day_quantile(first, 0.3) == float(np.quantile(days, 0.3, method="inverted_cdf"))
    assert not np.isfinite(np.quantile(days, 0.5, method="inverted_cdf"))
    assert H.day_quantile(np.array([4, 2, 2, 8]), 0.5) == 2.0 and H.day_quantile(np.array([4, 2, 2, 8]), 0.9) == 8.0
    s = H.alarm_summary(first)
    assert s["share"]["252"] == pytest.approx(0.3) and s["n_alarm_756"] == 3 and s["median_day"] is None and s["p90_day"] is None
    assert H.dfmt(None) == ">756" and H.dfmt(9.0) == "9"


def test_h1_search_picks_the_smallest_grid_value_meeting_the_level():
    assert H.H_GRID[0] == 0.5 and H.H_GRID[-1] == 60.0 and H.H_GRID[1] == 0.75 and len(H.H_GRID) == 239
    cmax = np.concatenate([np.zeros(90), [3.1, 3.2, 3.3, 3.4, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]])   # 100 draws
    h, fa = H.h_search(cmax, 0.05)
    assert h == 5.25                                                                   # at 5.0 six draws reach it (0.06); at 5.25 five (0.05)
    i = int(np.flatnonzero(H.H_GRID == 5.25)[0])
    assert fa[i] == pytest.approx(0.05) and fa[i - 1] == pytest.approx(0.06) and fa[0] == pytest.approx(0.10)
    assert H.h_search(cmax, 0.10)[0] == 0.5 and H.h_search(cmax, 0.08)[0] == 3.25        # ten draws are nonzero: 0.10 holds at the first grid value
    assert H.h_search(cmax, 0.01)[0] == 9.25                                              # 0.01 leaves one draw (10.0): 9.0 still admits two
    assert H.h_search(np.full(100, 100.0), 0.05)[0] is None                            # no grid value holds the level


def test_block_bootstrap_rows_are_circular_contiguous_and_drawn_jointly_with_the_counts():
    rng = np.random.default_rng(0)
    n_src = 100
    st = H.block_starts(rng, n_src, 7, nrows=50, block=21)
    assert st.shape == (7, 3) and st.min() >= 0 and st.max() < n_src                   # ceil(50 / 21) = 3 blocks a draw
    idx = H.expand(st, n_src, nrows=50, block=21)
    assert idx.shape == (7, 50)
    for r in range(7):
        for b in range(2):                                                             # every full block is a contiguous circular slice
            assert list(idx[r, b * 21:(b + 1) * 21]) == [(st[r, b] + j) % n_src for j in range(21)]
        assert list(idx[r, 42:50]) == [(st[r, 2] + j) % n_src for j in range(8)]       # the last block is trimmed to the draw length
    st2 = np.array([[95, 0]])
    assert list(H.expand(st2, n_src, nrows=25, block=21)[0][:7]) == [95, 96, 97, 98, 99, 0, 1]   # wraps around the end of the source
    x = np.arange(n_src, dtype=float) * 10.0
    cnt = np.stack([np.arange(n_src), np.arange(n_src) * 2], axis=1)
    i1 = H.expand(st, n_src, nrows=50, block=21)
    assert (x[i1] / 10.0 == cnt[i1][:, :, 0]).all() and (cnt[i1][:, :, 1] == 2 * cnt[i1][:, :, 0]).all()   # one index set serves $ and counts
    assert (H.expand(H.block_starts(np.random.default_rng(1), 2346, 5), 2346) == H.expand(H.block_starts(np.random.default_rng(1), 2346, 5), 2346)).all()


def test_drawdown_rows_match_r11_and_the_prefix_quantiles_are_monotone_in_n():
    X = np.random.default_rng(5).normal(0.2, 1.0, (300, 60))
    dd = H.ddpath_rows(X)
    for r in (0, 17, 299):
        assert np.allclose(dd[r], R11.ddpath(X[r]))                                     # peak starts at 0, row by row
    assert np.allclose(H.ddpath_rows(np.array([[-10.0, 5.0, 20.0, -30.0, 10.0]]))[0], [10.0, 5.0, 0.0, 30.0, 20.0])
    MDD = np.maximum.accumulate(dd, axis=1)
    q95, q99, ladder = H.dd_tables(MDD)
    assert q95.shape == q99.shape == (60,) and ladder.shape == (60, 1001)
    assert (np.diff(q95) >= 0).all() and (np.diff(q99) >= 0).all() and (q99 >= q95).all()   # a longer prefix never has a shallower quantile
    assert q99[-1] == pytest.approx(float(np.quantile(MDD[:, -1], 0.99))) and q95[9] == pytest.approx(float(np.quantile(MDD[:, 9], 0.95)))
    assert (np.diff(ladder, axis=1) >= 0).all() and ladder[:, 0] == pytest.approx(MDD.min(axis=0)) and ladder[:, -1] == pytest.approx(MDD.max(axis=0))
    assert H.share_deeper(ladder, 60, -1.0) == 1.0 and H.share_deeper(ladder, 60, MDD[:, -1].max() + 1.0) == 0.0
    med = float(np.median(MDD[:, 29]))
    assert abs(H.share_deeper(ladder, 30, med) - 0.5) <= 0.01                           # the ladder reads the cdf to 0.001
    S = np.sort(MDD, axis=0)
    assert np.allclose(H.q_sorted(S, 0.5), np.median(MDD, axis=0)) and np.allclose(H.q_sorted(S, [0.1, 0.9]), np.quantile(MDD, [0.1, 0.9], axis=0))


def test_poisson_band_by_hand():
    assert H.poisson_band(4.0) == (1, 8)                                               # F(0) = .018 < .025 <= F(1) = .092; F(7) = .949 < .975 <= F(8) = .979
    assert H.poisson_band(0.0) == (0, 0) and H.poisson_band(-1.0) == (0, 0)
    assert H.poisson_band(0.01) == (0, 0) and H.poisson_band(0.1) == (0, 1)             # F(0) = e^-0.1 = .905 < .975 <= F(1) = .995
    lo, hi = H.poisson_band(1000.0)                                                     # log-space pmf: no underflow at a large mean
    assert abs(lo - (1000 - 1.96 * math.sqrt(1000))) <= 2 and abs(hi - (1000 + 1.96 * math.sqrt(1000))) <= 2
    lo, hi = H.poisson_band(25.0, q=(0.5, 0.5))
    assert lo == hi == 25


def test_k_is_half_the_fall_to_zero_edge_and_the_threshold_must_sit_inside_the_grid(capsys):
    assert H.K_FRACTION == 0.5
    index = pd.bdate_range("2016-06-27", "2025-07-04")
    wf = np.flatnonzero((index >= "2016-07-01") & (index <= "2025-06-29"))
    raw = np.zeros(len(index))
    raw[wf] = np.tile([300.0, -100.0], len(wf) // 2 + 1)[:len(wf)]                     # mean 100, sd 200: delta 0.5, k 0.25
    meta = [{"strategy": s} for s in H.SMOKE_LEG_NAMES]
    B = H._StubBook(index, raw, np.array([0]), np.array([wf[0]]))
    saved = H.CHECK_REFS
    H.CHECK_REFS = False
    try:
        ref = H.reference(B, meta)
        assert ref["k"] == pytest.approx(0.5 * ref["mu0"] / ref["sigma0"]) and abs(ref["k"] - 0.25) < 0.001
        raw[wf] = -raw[wf]
        with pytest.raises(SystemExit, match="not positive"):                           # k = delta / 2 needs an edge to watch
            H.reference(H._StubBook(index, raw, np.array([0]), np.array([wf[0]])), meta)
    finally:
        H.CHECK_REFS = saved
    assert H.h_interior(5.25, "h1") is False and H.h_interior(59.75, "h1") is False
    assert H.h_interior(0.5, "h1") is True and "bottom" in capsys.readouterr().out       # the bottom is fine, and printed
    with pytest.raises(SystemExit, match="top of H_GRID"):
        H.h_interior(60.0, "h1")
    with pytest.raises(SystemExit, match="not on H_GRID"):
        H.h_interior(None, "h1")


def test_h2_and_h3_state_rules_and_the_count_bands():
    assert H.h2_state(500.0, 1000.0, 2000.0) == "OK" and H.h2_state(1000.0, 1000.0, 2000.0) == "WARN" and H.h2_state(2000.0, 1000.0, 2000.0) == "ALARM"
    assert H.h2_state(0.0, 0.0, 0.0) == "OK"                                           # no drawdown is never a state
    assert H.h3_flag(5, 6, 10) == "UNDER" and H.h3_flag(11, 6, 10) == "OVER" and H.h3_flag(6, 6, 10) == "within" and H.h3_flag(10, 6, 10) == "within"
    CUM = np.zeros((100, 3, 2), np.int16)
    CUM[:, 2, 0] = np.arange(100)                                                      # leg 0 at n = 3: counts 0..99
    CUM[:, 2, 1] = 7
    lo, hi = H.count_bands(CUM)
    assert lo.shape == hi.shape == (3, 2)
    assert lo[2, 0] == 2 and hi[2, 0] == 97                                            # floor(.025 x 99) = 2; ceil(.975 x 99) = 97
    assert lo[2, 1] == hi[2, 1] == 7 and lo[0, 0] == hi[0, 0] == 0


def test_leg_counts_sit_on_the_exit_row_in_legs_order_and_the_reference_is_the_wf_window():
    index = pd.bdate_range("2016-06-27", "2025-07-04")
    n = len(index)
    wf = np.flatnonzero((index >= "2016-07-01") & (index <= "2025-06-29"))
    raw = np.zeros(n)
    raw[wf] = 100.0
    raw[wf[::2]] = -50.0
    meta = [{"strategy": s} for s in H.SMOKE_LEG_NAMES]                                # ORB, ENGU-Q, TTM, NOISE by the file names
    B = H._StubBook(index, raw, np.array([0, 1, 2, 3, 0, 0, 2]), np.array([wf[0], wf[0], wf[1], n - 1, 0, wf[0], wf[1]]))
    C, fams = H.leg_counts(B, meta, wf)
    assert fams == list(H.LEGS)
    assert C[0].tolist() == [2, 1, 0, 0] and C[1].tolist() == [0, 0, 2, 0] and C[2:].sum() == 0    # row n-1 and row 0 are outside the window
    saved = H.CHECK_REFS
    H.CHECK_REFS = False
    try:
        ref = H.reference(B, meta)
    finally:
        H.CHECK_REFS = saved
    assert ref["n_rows"] == len(wf) == 2346 and ref["first"] == "2016-07-01" and ref["last"] == "2025-06-27"
    assert ref["mu0"] == pytest.approx(float(raw[wf].mean())) and ref["sigma0"] == pytest.approx(float(raw[wf].std(ddof=1)))
    assert ref["trades_wf"] == {"ORB": 2, "ENGU-Q": 1, "TTM": 2, "NOISE": 0} and ref["rate"]["ORB"] == pytest.approx(2 / 2346)
    assert ref["wf_figures"]["checked"] is False and ref["wf_figures"]["as_recorded"] is False
    H.CHECK_REFS = True
    try:
        with pytest.raises(SystemExit, match="not the recorded"):                      # a real calibrate holds the rows to 93.81 / 3.816 / 44,849
            H.reference(B, meta)
    finally:
        H.CHECK_REFS = saved
    with pytest.raises(SystemExit, match="not one of"):
        H.leg_counts(B, [{"strategy": "VWAP_1.py"}] + meta[1:], wf)


def _csv(path, dates, pnl, counts=None):
    return H.write_forward_csv(str(path), dates, pnl, counts)


def test_forward_csv_refusals_and_the_asof_trim(tmp_path):
    d = pd.bdate_range("2026-09-28", periods=5)
    ok = _csv(tmp_path / "ok.csv", d, [10.0, -5.0, 0.0, 2.5, 1.0], {"ORB": [1, 0, 2, 1, 0], "TTM": [0, 0, 0, 1, 1]})
    dates, pnl, counts = H.read_forward(ok)
    assert len(dates) == 5 and pnl.tolist() == [10.0, -5.0, 0.0, 2.5, 1.0] and sorted(counts) == ["ORB", "TTM"] and counts["ORB"].sum() == 4
    dates, pnl, counts = H.read_forward(ok, asof="2026-09-30")
    assert len(dates) == 3 and str(dates[-1].date()) == "2026-09-30" and counts["TTM"].tolist() == [0, 0, 0]
    with pytest.raises(SystemExit, match="pretending to be forward"):                   # a row on WF1 itself
        H.read_forward(_csv(tmp_path / "wf.csv", [pd.Timestamp("2025-06-29")] + list(d), [1.0] * 6))
    with pytest.raises(SystemExit, match="pretending to be forward"):                   # a row before the forward start
        H.read_forward(_csv(tmp_path / "early.csv", pd.bdate_range("2026-09-21", periods=5), [1.0] * 5))
    with pytest.raises(SystemExit, match="earlier than the registered forward start"):   # --from can only move the start later
        H.read_forward(_csv(tmp_path / "early.csv", pd.bdate_range("2026-09-21", periods=5), [1.0] * 5), frm="2026-09-21")
    later = _csv(tmp_path / "later.csv", pd.bdate_range("2026-10-05", periods=3), [1.0] * 3)
    assert len(H.read_forward(later, frm="2026-10-05")[0]) == 3                        # a later start is accepted...
    with pytest.raises(SystemExit, match="pretending to be forward"):                   # ...and every row must respect it
        H.read_forward(ok, frm="2026-10-05")
    with pytest.raises(SystemExit, match="weekday 2026-09-30 is missing"):               # one row per weekday: a gap is refused
        H.read_forward(_csv(tmp_path / "gap.csv", [d[0], d[1], d[3]], [1.0, 2.0, 3.0]))
    hol = _csv(tmp_path / "holiday.csv", pd.bdate_range("2026-11-25", periods=3), [5.0, 0.0, 7.0])   # Thanksgiving as a 0 row
    assert H.read_forward(hol)[1].tolist() == [5.0, 0.0, 7.0]
    with pytest.raises(SystemExit, match="not strictly increasing"):
        H.read_forward(_csv(tmp_path / "order.csv", [d[0], d[2], d[1]], [1.0, 2.0, 3.0]))
    with pytest.raises(SystemExit, match="not strictly increasing"):
        H.read_forward(_csv(tmp_path / "dup.csv", [d[0], d[0]], [1.0, 2.0]))
    with pytest.raises(SystemExit, match="weekend"):
        H.read_forward(_csv(tmp_path / "sat.csv", [d[0], pd.Timestamp("2026-10-03")], [1.0, 2.0]))
    (tmp_path / "nan.csv").write_text("date,pnl\n2026-09-28,10\n2026-09-29,\n")
    with pytest.raises(SystemExit, match="no pnl"):
        H.read_forward(str(tmp_path / "nan.csv"))
    (tmp_path / "nocol.csv").write_text("day,pnl\n2026-09-28,10\n")
    with pytest.raises(SystemExit, match="lacks column"):
        H.read_forward(str(tmp_path / "nocol.csv"))
    (tmp_path / "badcount.csv").write_text("date,pnl,n_ORB\n2026-09-28,10,1.5\n")
    with pytest.raises(SystemExit, match="n_ORB"):
        H.read_forward(str(tmp_path / "badcount.csv"))
    (tmp_path / "alias.csv").write_text("date,pnl,n_ENGU-Q\n2026-09-28,10,2\n")
    assert H.read_forward(str(tmp_path / "alias.csv"))[2]["ENGU-Q"].tolist() == [2]       # the alias column name is accepted
    long = pd.bdate_range("2026-09-28", periods=H.HMAX + 1)
    f = _csv(tmp_path / "long.csv", long, np.ones(H.HMAX + 1))
    with pytest.raises(SystemExit, match="horizon"):                                    # 757 rows: the registered horizon is spent
        H.read_forward(f)
    assert len(H.read_forward(f, asof=str(long[H.HMAX - 1].date()))[0]) == H.HMAX           # a re-read as of an earlier day still works
    with pytest.raises(SystemExit, match="no forward row"):
        H.read_forward(ok, asof="2026-09-27")
    with pytest.raises(SystemExit, match="not found"):
        H.read_forward(str(tmp_path / "missing.csv"))


def test_prereg_tbd_refuses_calibrate_outside_smoke_and_read_needs_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "OUT", str(tmp_path / "out"))
    monkeypatch.setattr(H, "PREREG_SHA", "TBD")
    monkeypatch.setattr(H, "SMOKE_TBD_OK", False)
    monkeypatch.setattr(H, "load_records", lambda: (_ for _ in ()).throw(AssertionError("records must not be touched")))
    with pytest.raises(SystemExit, match="TBD"):
        H.calibrate()
    with pytest.raises(SystemExit, match="TBD"):
        H.check_prereg()
    probe = tmp_path / "prereg.txt"
    probe.write_text("the plan\r\nline two\r\n")
    sha = R11.sha_lf(str(probe))
    assert H.check_prereg(str(probe), sha) == sha                                     # CRLF-insensitive
    with pytest.raises(SystemExit, match="plan changed"):
        H.check_prereg(str(probe), "0" * 64)
    with pytest.raises(SystemExit, match="not on disk"):
        H.check_prereg(str(tmp_path / "absent.txt"), sha)
    monkeypatch.setattr(H, "SMOKE_TBD_OK", True)
    assert H.check_prereg(str(tmp_path / "absent.txt"), "TBD") == "TBD"               # only the smoke tolerates an unregistered plan
    f = _csv(tmp_path / "f.csv", pd.bdate_range("2026-09-28", periods=3), [1.0, 2.0, 3.0])
    with pytest.raises(SystemExit, match="READY is missing"):
        H.read(f)
    os.makedirs(H.OUT)
    with open(H._ready_path(), "w") as fh:
        fh.write(json.dumps({"sha256": {"calibration.json": "0" * 64, "null.npz": "0" * 64}, "prereg_sha256": "TBD"}))
    with pytest.raises(SystemExit, match="does not match the sha READY recorded"):     # READY without its files, or with changed files
        H.read(f)
    with open(os.path.join(H.OUT, "calibration.json"), "w") as fh:
        fh.write("{}")
    np.savez(os.path.join(H.OUT, "null.npz"), mdd_ladder=np.zeros((1, 3)))
    shas = {n: R11._sha_file(os.path.join(H.OUT, n)) for n in ("calibration.json", "null.npz")}
    with open(H._ready_path(), "w") as fh:
        fh.write(json.dumps({"sha256": shas, "prereg_sha256": "0" * 64}))
    with pytest.raises(SystemExit, match="prereg changed after calibration"):
        H.read(f)


def ready_k(d):
    return json.load(open(d / "READY"))["k"]


def test_smoke_runs_offline_end_to_end_and_restores_the_module(tmp_path, capsys):
    before = (H.OUT, H.NDRAW, H.SMOKE_TBD_OK, H.CHECK_REFS, H.load_records)
    H.smoke(str(tmp_path / "smoke_health"))
    assert (H.OUT, H.NDRAW, H.SMOKE_TBD_OK, H.CHECK_REFS, H.load_records) == before
    out = capsys.readouterr().out
    assert "SMOKE PASS" in out.splitlines()[-1]
    d = tmp_path / "smoke_health" / "health"
    cal = json.load(open(d / "calibration.json"))
    assert cal["H1"]["h1"] in H.H_GRID.tolist() and cal["H1"]["fa_at_h1_252"] <= H.FA_LEVEL and cal["ndraw"] == 400
    assert cal["H1"]["k"] == pytest.approx(0.5 * cal["mu0"] / cal["sigma0"]) and cal["H1"]["k_fraction"] == 0.5 and cal["H1b"]["k"] == cal["H1"]["k"]
    assert cal["H1"]["h1"] < H.H_GRID[-1] and cal["power"]["H1"]["0.0"]["share"]["756"] >= 0.5 and cal["power"]["H1"]["0.0"]["median_day"] is not None
    assert ready_k(d) == cal["H1"]["k"]
    assert len(cal["H2"]["q99"]) == H.HMAX and len(cal["H3"]["boot_lo"]["NOISE"]) == H.HMAX and cal["prereg_sha256"] == "TBD"
    assert set(cal["power"]["H1"]) == {"0.5", "0.0", "-0.5"} and cal["headline"].startswith("if #463 stopped earning tomorrow")
    ready = json.load(open(d / "READY"))
    assert ready["sha256"]["calibration.json"] == R11._sha_file(str(d / "calibration.json"))
    reads = sorted(p for p in os.listdir(d) if p.startswith("health_") and p.endswith(".json"))
    assert len(reads) >= 3
    states = {json.load(open(d / p))["rows"]: json.load(open(d / p))["states"] for p in reads}
    assert states[200]["H1"] == "ALARM" and states[72]["H2"] in ("WARN", "ALARM") and states[120]["H1"] == "OK"
    for p in os.listdir(d):
        if p.endswith(".txt"):
            open(d / p, encoding="utf-8").read().encode("ascii")
    with pytest.raises(AssertionError, match="smoke"):
        H.smoke(str(tmp_path / "real_cache"))                                           # the folder's name must say smoke


def test_the_registered_prereg_sha_is_the_file_in_the_repo():
    assert os.path.isfile(H.PREREG)
    if H.PREREG_SHA == "TBD":
        with pytest.raises(SystemExit, match="TBD"):
            H.check_prereg()                                                            # unregistered: nothing runs outside the smoke
    else:
        got = R11.sha_lf(H.PREREG)
        assert got == H.PREREG_SHA, f"PREREG_HEALTH_R1.txt hashes to {got}, r18_health.PREREG_SHA is {H.PREREG_SHA} - an addendum landed? re-hash it"
    assert H.LEGS == ("ORB", "ENGU-Q", "TTM", "NOISE") and H.HORIZONS == (252, 504, 756) and H.SEED == 20261021 and H.BLOCK == 21
