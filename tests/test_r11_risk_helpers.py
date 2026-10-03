"""RISK r1 harness (tools/rocfrontier/r11_risk.py) - the statistics and the sparse book, on hand-checkable inputs.

The harness's own `smoke` runs the whole round on a synthetic world through the engine's leg runner (and shows the test has power and
does not pass a null world); these pin the pieces a verdict rests on: the drawdown path (peak from 0), CDaR95, the underwater periods
E3 ranks, the Diebold-Mariano / HLN read of R5, Newey-West OLS, the stationary bootstrap, and the entry-row rule of the sparse book.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "rocfrontier"))
import r11_risk as R  # noqa: E402


def test_drawdown_starts_from_zero_and_cdar_is_the_mean_of_the_worst_five_percent():
    x = np.array([-10.0, 5.0, 20.0, -30.0, 10.0] + [1.0] * 15)
    dd = R.ddpath(x)
    assert dd[0] == 10.0                                    # an opening loss is a drawdown (peak starts at 0)
    assert dd.max() == 30.0
    s = R.stats(x, pd.bdate_range("2021-01-04", periods=len(x)))
    assert s["cdar95"] == 30.0                              # ceil(5% of 20) = 1 worst value
    yrs = (pd.bdate_range("2021-01-04", periods=20)[-1] - pd.Timestamp("2021-01-04")).days / 365.25
    assert s["roc"] == pytest.approx(30.0 * (x.sum() / yrs) / 30.0)
    assert s["cdr"] == pytest.approx(30.0 * (x.sum() / yrs) / 30.0)


def test_underwater_periods_are_maximal_runs_ranked_by_depth():
    x = np.array([5.0, -3.0, -4.0, 10.0, -1.0, 2.0, -6.0, 1.0])
    u = R.underwater(x, pd.bdate_range("2022-03-01", periods=len(x)))
    assert [round(p["depth"], 9) for p in u] == [7.0, 6.0, 1.0]
    assert u[0]["peak"] == "2022-03-01" and u[0]["trough"] == "2022-03-03"


def test_dm_hln_reads_a_real_improvement_and_not_noise():
    rng = np.random.default_rng(3)
    better = 0.2 + rng.normal(0, 0.5, 1500)
    stat, p = R.dm_hln(better, 20, 19)
    assert p < 0.01 and stat > 0
    _, p0 = R.dm_hln(rng.normal(0, 0.5, 1500), 20, 19)
    assert p0 > 0.01


def test_newey_west_ols_recovers_coefficients():
    rng = np.random.default_rng(4)
    x = rng.normal(0, 1, 3000)
    y = 0.5 + 2.0 * x + rng.normal(0, 0.1, 3000)
    b, t = R.ols_nw(y, np.column_stack([np.ones(3000), x]), 10)
    assert b[0] == pytest.approx(0.5, abs=0.02) and b[1] == pytest.approx(2.0, abs=0.02) and t[1] > 100


def test_stationary_bootstrap_stays_in_range_with_the_mean_block_asked_for():
    rng = np.random.default_rng(5)
    ix = R.stationary_bootstrap(20000, 60, rng)
    assert ix.min() >= 0 and ix.max() < 20000
    jumps = np.mean(ix[1:] != (ix[:-1] + 1) % 20000)
    assert 1 / 75 < jumps < 1 / 48                          # ~ one jump every 60 rows


def test_the_sparse_book_sizes_each_trade_by_its_entry_row_and_reads_the_next_row_off_index():
    D = lambda s: np.datetime64(s, "D")
    rec = {  # trade 0: intraday Monday; trade 1: entered on a Sunday (off the business-day index), marked Mon, closed Tue
        "entry": np.array([D("2020-01-06"), D("2020-01-05")]), "exit": np.array([D("2020-01-06"), D("2020-01-07")]),
        "closed": np.array([100.0, 50.0]), "leg": np.array([0, 1]),
        "inc_t": np.array([0, 1, 1]), "inc_d": np.array([D("2020-01-06"), D("2020-01-06"), D("2020-01-07")]),
        "inc_v": np.array([100.0, 80.0, -30.0])}
    meta = [{"strategy": "A", "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.5},
            {"strategy": "ENGUQ", "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.783}]
    B = R.Book(rec, meta)
    assert B.index[B.erow[1]] == pd.Timestamp("2020-01-06")  # Sunday entry reads Monday's row
    m = np.ones(B.n)
    m[B.erow[1]] = 2.0                                         # the Monday row's multiplier
    out = pd.Series(B.sized(m), index=B.index)
    assert out.loc["2020-01-06"] == pytest.approx(2 * 100.0 + 2 * 80.0)   # both trades enter on the Monday row
    assert out.loc["2020-01-07"] == pytest.approx(2 * -30.0)
    assert np.allclose(B.sized(np.ones(B.n)), B.raw)
    assert pd.Series(B.sized_closed(np.ones(B.n)), index=B.index).loc["2020-01-07"] == 50.0


# ------------------------------------------------------------------ pre-run review round 2, 2026-10-03: report-only pieces
META2 = [{"strategy": "ENGUQ", "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.783},
         {"strategy": "A", "instrument": "NQ", "mult": 20.0, "weight": 1.0, "cost_pts": 0.5}]


def _book(trades):
    """(leg, entry, exit, [(day, $ mark), ...]) per trade -> R.Book; closed $ = the sum of its marks."""
    D = lambda s: np.datetime64(s, "D")
    ent, ext, clo, leg, it, idd, iv = [], [], [], [], [], [], []
    for n, (lg, e, x, marks) in enumerate(trades):
        ent.append(D(e)); ext.append(D(x)); leg.append(lg); clo.append(sum(v for _, v in marks))
        for d, v in marks:
            it.append(n); idd.append(D(d)); iv.append(v)
    return R.Book({"entry": np.array(ent), "exit": np.array(ext), "closed": np.array(clo, float), "leg": np.array(leg, np.int64),
                   "inc_t": np.array(it, np.int64), "inc_d": np.array(idd), "inc_v": np.array(iv, float)}, META2)


def _m(B, ups):
    m = np.ones(B.n)
    for d, v in ups.items():
        m[B.index.get_loc(pd.Timestamp(d))] = v
    return m


def test_e3_diag_58b_on_allx_skips_the_excised_rows():
    B = _book([(1, "2020-01-06", "2020-01-06", [("2020-01-06", 1000.0)]),
               (0, "2020-02-03", "2020-05-05", [("2020-02-10", -100.0), ("2020-03-10", -500.0), ("2020-05-05", -50.0)]),   # 03-10 is excised
               (1, "2020-06-01", "2020-06-01", [("2020-06-01", 5000.0)])])
    m = _m(B, {"2020-02-03": 2.0})                              # the ENGU-Q trade is upsized and open at the peak
    out = R.e3(B, {"V2": m}, 0)
    d = out["ALLX"]["diag_58b"][0]
    assert d["engq_upsized_open_trades"] == 1
    assert d["engq_upsized_pnl_in_drawdown"] == pytest.approx(out["ALLX"]["c"] * 2.0 * (-100.0 - 50.0))
    assert out["ALL"]["diag_58b"][0]["engq_upsized_pnl_in_drawdown"] == pytest.approx(out["ALL"]["c"] * 2.0 * (-100.0 - 500.0 - 50.0))


def test_e3_diag_58b_keeps_the_first_row_when_the_span_starts_underwater():
    B = _book([(0, "2010-12-27", "2011-01-04", [("2011-01-03", -300.0), ("2011-01-04", -200.0)]),   # 2011-01-03 = row 0 of the span
               (1, "2012-03-01", "2012-03-01", [("2012-03-01", 10000.0)])])
    m = _m(B, {"2010-12-27": 2.0})
    out = R.e3(B, {"V2": m}, 0)
    for span in ("ALL", "ALLX"):
        d = out[span]["diag_58b"][0]
        assert d["engq_upsized_open_trades"] == 1
        assert d["engq_upsized_pnl_in_drawdown"] == pytest.approx(out[span]["c"] * 2.0 * (-300.0 - 200.0))


def test_v2_wf_deepest_raw_change_runs_from_the_row_after_the_peak_to_the_trough():
    B = _book([(1, "2017-01-03", "2017-01-03", [("2017-01-03", 1000.0)]),
               (1, "2017-01-04", "2017-01-04", [("2017-01-04", -400.0)]),
               (1, "2017-01-05", "2017-01-05", [("2017-01-05", -300.0)]),
               (1, "2017-02-01", "2017-02-01", [("2017-02-01", 2000.0)])])
    w = R.e3(B, {"V2": _m(B, {"2017-01-04": 2.0})}, -1)["v2_wf_deepest_unscaled"]
    assert (w["peak"], w["trough"], w["depth"]) == ("2017-01-03", "2017-01-05", 1100.0)
    assert w["raw_change_same_dates"] == pytest.approx(-700.0)  # not the peak day's +1,000
    # WF opening underwater: the period starts on WF's first row and that row's P&L counts
    B = _book([(1, "2016-07-01", "2016-07-01", [("2016-07-01", -500.0)]),
               (1, "2016-07-05", "2016-07-05", [("2016-07-05", -250.0)]),
               (1, "2016-08-01", "2016-08-01", [("2016-08-01", 3000.0)])])
    w = R.e3(B, {"V2": np.ones(B.n)}, -1)["v2_wf_deepest_unscaled"]
    assert w["trough"] == "2016-07-05" and w["raw_change_same_dates"] == pytest.approx(-750.0)


def test_kronos_result_reads_only_real_result_files_newest_first_and_records_an_unreadable_one(tmp_path, monkeypatch):
    kd = tmp_path / "kronos"
    (kd / "step0_results").mkdir(parents=True)                  # a FOLDER named *result*: not a file, never opened
    (kd / "step0_results" / "notes.txt").write_text("not a result name")
    junk = [kd / "venv" / "lib" / "site-packages" / "pkg" / "result.py", kd / ".venv" / "result.txt", kd / ".git" / "result",
            kd / "__pycache__" / "result.cpython-311.pyc", kd / "py311" / "result.txt"]
    (kd / "py311").mkdir()
    (kd / "py311" / "pyvenv.cfg").write_text("home = /usr/bin")  # a virtualenv by its marker, whatever its name
    for p in junk:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("junk")
        os.utime(p, (2_000_000_000, 2_000_000_000))             # newest of all: must not take a slot
    real = []
    for i in range(7):
        p = kd / ("sub" if i % 2 else "") / f"r{i}_result.txt"
        p.parent.mkdir(exist_ok=True)
        p.write_text(f"\n  RESULT {i}: step 0 line\nmore\n")
        os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))
        real.append(str(p))
    bad = real[5]
    real_open = open

    def fake_open(path, *a, **kw):
        if str(path) == bad:
            raise PermissionError("denied")
        return real_open(path, *a, **kw)
    monkeypatch.setattr(R, "open", fake_open, raising=False)
    monkeypatch.setattr(R, "REPO", str(tmp_path / "no_repo"))
    monkeypatch.setenv("EDGELOG_KRONOS_DIR", str(kd))
    got = R.kronos_result()
    assert [g["source"] for g in got] == real[6:1:-1]            # the 5 newest real files, newest first; no junk, no folder
    assert "PermissionError" in got[1]["error"] and "excerpt" not in got[1]
    assert got[0]["excerpt"].startswith("\n  RESULT 6")
    lines = R.kronos_lines(got)
    assert lines[0].endswith(real[6] + " - RESULT 6: step 0 line") and "unreadable: PermissionError" in lines[1]


def test_kronos_result_reports_nothing_found_and_the_verdict_line_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "REPO", str(tmp_path / "no_repo"))
    monkeypatch.setenv("EDGELOG_KRONOS_DIR", str(tmp_path / "missing"))
    got = R.kronos_result()
    assert got == "no Kronos step-0 result found"
    assert R.kronos_lines(got) == ["Kronos step 0 (report only): no Kronos step-0 result found"]


def test_kronos_lines_stay_ascii_for_binary_and_non_ascii_results_and_hidden_or_conda_folders_are_skipped(tmp_path, monkeypatch):
    kd = tmp_path / "kronos"
    (kd / ".ipynb_checkpoints").mkdir(parents=True)
    (kd / ".ipynb_checkpoints" / "step0_results-checkpoint.ipynb").write_text("checkpoint copy")
    (kd / "condaenv" / "conda-meta").mkdir(parents=True)
    (kd / "condaenv" / "Lib" / "unittest").mkdir(parents=True)
    (kd / "condaenv" / "Lib" / "unittest" / "result.py").write_text("stdlib")
    (kd / "step0_results.npz").write_bytes(b"PK\x03\x04\x00\x00\xff\xfe binary")
    (kd / "summary_result.txt").write_text("≥ 0.05 → skill — none\n", encoding="utf-8")
    monkeypatch.setattr(R, "REPO", str(tmp_path / "no_repo"))
    monkeypatch.setenv("EDGELOG_KRONOS_DIR", str(kd))
    got = R.kronos_result()
    assert sorted(os.path.basename(g["source"]) for g in got) == ["step0_results.npz", "summary_result.txt"]
    lines = R.kronos_lines(got)
    for ln in lines:
        ln.encode("cp1252")                                       # the owner's console / default file encoding
        ln.encode("ascii")
    assert any("(binary file)" in ln for ln in lines)
