import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import power_line as PL  # noqa: E402


def test_stationary_indices_shape_range_and_block_length():
    idx = PL.stationary_indices(500, 200, 20, np.random.default_rng(1))
    assert idx.shape == (200, 500)
    assert idx.min() >= 0 and idx.max() < 500
    cont = (np.diff(idx, axis=1) == 1) | ((idx[:, 1:] == 0) & (idx[:, :-1] == 499))
    mean_block = 1.0 / (1.0 - cont.mean())
    assert 15 < mean_block < 26                     # geometric blocks with mean 20


def test_identical_series_have_no_detectable_lead():
    x = np.random.default_rng(2).normal(50, 400, 600)
    r = PL.power_line(x, x.copy(), years=2.4, draws=200, seed=3)
    assert r["sd"] == 0.0 and r["line_5pct"] == 0.0 and r["line_80pct"] == 0.0


def test_more_independent_noise_raises_the_line():
    rng = np.random.default_rng(4)
    twin = rng.normal(60, 400, 800)
    small = twin + rng.normal(0, 50, 800)
    large = twin + rng.normal(0, 400, 800)
    a = PL.power_line(small, twin, years=3.2, draws=300, seed=5)
    b = PL.power_line(large, twin, years=3.2, draws=300, seed=5)
    assert 0 < a["sd"] < b["sd"]
    assert abs(b["line_80pct"] / b["sd"] - (PL.Z5 + PL.Z80)) < 1e-9


def test_cli_never_prints_the_lead(tmp_path, capsys):
    rng = np.random.default_rng(6)
    days = pd.bdate_range("2020-01-01", periods=700)
    twin = rng.normal(40, 300, len(days))
    cand = twin + 120.0                              # a large, obvious lead
    pd.DataFrame({"date": days, "pnl_usd": cand}).to_csv(tmp_path / "c.csv", index=False)
    pd.DataFrame({"date": days, "pnl_usd": twin}).to_csv(tmp_path / "t.csv", index=False)
    r = PL.main(["--cand", str(tmp_path / "c.csv"), "--twin", str(tmp_path / "t.csv"), "--draws", "200"])
    out = capsys.readouterr().out
    assert "MINIMUM DETECTABLE" in out
    yrs = (days[-1] - days[0]).days / 365.25
    lead = PL.roc30(cand[None, :], yrs)[0] - PL.roc30(twin[None, :], yrs)[0]
    assert ("%.1f" % lead) not in out and "lead itself is not computed" in out
    assert set(r) >= {"sd", "line_5pct", "line_80pct"} and "lead" not in r
