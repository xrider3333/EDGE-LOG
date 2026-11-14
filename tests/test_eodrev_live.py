"""Strategy 23 live signal (api/eodrev_live.py): picks must equal the plugin's on the pinned panel,
using only what is known at 15:20, and the hand-off file must hold the agreed fields."""
import importlib.util
import json
import os

import numpy as np
import pandas as pd
import pytest

from api import eodrev_live as L

PINNED = r"C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_u100_panel_v1.npz"
HAVE = os.path.exists(PINNED)
P511 = L.PARAMS


def _plugin():
    path = os.path.join(L.ROOT, "augur_strategies", "MISC_EODREV_1_2.py")
    spec = importlib.util.spec_from_file_location("eodrev12", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _plugin_picks(m, p, prm):
    """The plugin's own L / W selection (its _daily_pnl lines), every day."""
    names = p["names"]; s0 = p["s0"]; spy = s0["SPY"]; rp = p["rp"]
    ok = p["member"] & (rp >= float(prm["min_price"]))
    rev = -(s0[names] - m._beta(p, int(prm["beta_len"])).mul(spy, axis=0))
    score = (rev.where(ok).rank(axis=1, pct=True)
             + float(prm["period_wt"]) * m._habit(p, int(prm["period_len"]), prm["min_price"]).where(ok).rank(axis=1, pct=True)).where(ok)
    r = score.rank(axis=1, ascending=False); n = score.notna().sum(axis=1); k = int(prm["k"])
    return score, (r <= k), (r > n.values[:, None] - k), n


@pytest.mark.skipif(not HAVE, reason="pinned panel not on this machine")
def test_picks_match_plugin_on_pinned_panel():
    m = _plugin(); p = m._panel()
    z = dict(np.load(PINNED, allow_pickle=False))
    score, Lm, Wm, n = _plugin_picks(m, p, P511)
    days = [d for d in p["days"] if n.loc[d] >= 4 * P511["k"]]
    rng = np.random.default_rng(23)
    sample = sorted(rng.choice(days[200:], size=60, replace=False).tolist()) + [days[-1]]
    for d in sample:
        row, nn = L.score_day(z, int(d))
        assert nn == int(n.loc[d]), d
        lo, sh = L.picks(row, P511["k"])
        assert set(lo.index) == set(Lm.columns[Lm.loc[d].values]), d
        assert set(sh.index) == set(Wm.columns[Wm.loc[d].values]), d


@pytest.mark.skipif(not HAVE, reason="pinned panel not on this machine")
def test_after_1520_fields_cannot_move_the_picks():
    z = dict(np.load(PINNED, allow_pickle=False))
    d = int(z["dates"][-30])
    i = int(np.flatnonzero(z["dates"] == d)[0])
    z2 = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in z.items()}
    for key in ("pe", "c10", "dc", "raw"):
        z2[key][i] = z2[key][i] * 1.37           # scramble everything known only after 15:20
    a, _ = L.score_day(z, d); b, _ = L.score_day(z2, d)
    pd.testing.assert_series_equal(a, b)


@pytest.mark.skipif(not HAVE, reason="pinned panel not on this machine")
def test_live_row_equals_replay_row():
    z = dict(np.load(PINNED, allow_pickle=False))
    d = int(z["dates"][-5]); i = int(np.flatnonzero(z["dates"] == d)[0])
    names = [str(x) for x in z["names"]]
    ps_today = {s: float(v) for s, v in zip(names, z["ps"][i]) if np.isfinite(v)}
    cut = {k: (v[:i] if k not in ("names",) else v) for k, v in z.items()}
    mem = [s for s, v in zip(names, z["member"][i]) if v]
    a, _ = L.score_day(z, d)
    b, _ = L.score_day(cut, d, ps_today=ps_today, member_today=mem)
    pd.testing.assert_series_equal(a, b)


@pytest.mark.skipif(not HAVE, reason="pinned panel not on this machine")
def test_signal_file_fields(tmp_path):
    z = dict(np.load(PINNED, allow_pickle=False))
    d = int(z["dates"][-5])
    sig = L.build_signal(z, d, panel_sha="x", written_et="replay")
    for key in ("date", "asof_et", "written_et", "strategy", "run", "status", "reason", "k", "long", "short",
                "universe_n", "scored_n", "panel_date", "panel_sha", "params"):
        assert key in sig
    assert sig["status"] == "OK" and len(sig["long"]) == 3 and len(sig["short"]) == 3
    assert not set(x["sym"] for x in sig["long"]) & set(x["sym"] for x in sig["short"])
    for x in sig["long"] + sig["short"]:
        assert set(x) == {"sym", "px", "score", "exch"} and x["px"] > 0
    assert sig["panel_date"] < sig["date"]
    f = tmp_path / "s.json"; L._write_atomic(str(f), sig)
    assert json.load(open(f))["run"] == 511


def test_skip_reason_is_a_skip():
    z = {"dates": np.array([20260102, 20260105]), "names": np.array(["AAA", "SPY"]),
         "ps": np.ones((2, 2)), "pe": np.ones((2, 2)), "c10": np.ones((2, 2)), "dc": np.ones((2, 2)),
         "raw": np.ones((2, 2)), "member": np.ones((2, 2), bool)}
    sig = L.build_signal(z, 20260106, status_reason="no SPY 15:10-15:19 bars", written_et="t")
    assert sig["status"] == "SKIP" and sig["long"] == [] and sig["panel_date"] == "2026-01-05"


def test_missed_split_is_rescaled():
    days = pd.Index([20260610, 20260611, 20260612, 20260615])
    cols = ["KLAC", "SPY"]
    pre = pd.DataFrame({"KLAC": [2135.0, 2411.0, 254.5, 256.4], "SPY": [600, 601, 602, 603.0]}, index=days)
    ps, pe, c10, dc = (pre.copy() for _ in range(4))
    ps2, pe2, c102, dc2 = L.fix_missed_splits(ps, pe, c10, dc, ["KLAC"], log=lambda *_: None)
    assert dc2.loc[20260611, "KLAC"] == pytest.approx(241.1)
    assert dc2.loc[20260612, "KLAC"] == 254.5 and dc2["SPY"].equals(pre["SPY"])


def test_real_crash_is_not_a_split():
    days = pd.Index([1, 2])
    df = pd.DataFrame({"X": [100.0, 70.0]}, index=days)
    out = L.fix_missed_splits(df, df, df, df, ["X"], log=lambda *_: None)[3]
    assert out.loc[1, "X"] == 100.0          # a -30 pct day is below the 40 pct trigger: untouched
