"""Fast synthetic tests for tools/knob_audit.py -- no Firestore, no market data.

Four checks, one per load-bearing piece:
  1. the spread and edge-rate maths (norm_pos / iqr_frac / on_edge / edge_rate / edge_sides)
  2. the on/off-switch exclusion (is_switch judges the FILE, not one search's grid) and
     that a switch never falls through to the WIDEN branch
  3. the drift correlation (drift_rho over run dates)
  4. the recommendation ladder (FREEZE / WIDEN / KEEP / UNCLEAR) end to end on a
     synthetic run cache, including the widened range it proposes
"""
import os
import sys
import json

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import knob_audit as ka  # noqa: E402


# ---------------------------------------------------------------------------
# 1. spread + edge rate
# ---------------------------------------------------------------------------
def test_spread_and_edge_rate_math():
    # position inside a declared 0..10 range
    assert ka.norm_pos(0, 0, 10) == 0.0
    assert ka.norm_pos(10, 0, 10) == 1.0
    assert ka.norm_pos(2.5, 0, 10) == pytest.approx(0.25)
    assert np.isnan(ka.norm_pos(5, 10, 10))        # degenerate: min == max, knob is pinned
    assert np.isnan(ka.norm_pos("off", 0, 10))     # non-numeric knob value

    # spread: identical crowns = 0, crowns spread across the whole range = wide
    assert ka.iqr_frac([0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.0)
    assert ka.iqr_frac([0.0, 0.25, 0.5, 0.75, 1.0]) == pytest.approx(0.5)
    assert np.isnan(ka.iqr_frac([0.4]))            # one run says nothing about spread

    # an edge is within 2% of the range width of either end
    assert ka.on_edge(0.0, 0, 10) and ka.on_edge(10.0, 0, 10)
    assert ka.on_edge(0.19, 0, 10)                 # 1.9% in -- still the edge
    assert not ka.on_edge(0.21, 0, 10)             # 2.1% in -- interior
    assert not ka.on_edge(5.0, 0, 10)

    # edge rate and which end the crowns pile on
    vals = [10, 10, 10, 5, 0]                      # 3 at the top, 1 interior, 1 at the bottom
    assert ka.edge_rate(vals, 0, 10) == pytest.approx(0.8)
    lo_share, hi_share = ka.edge_sides(vals, 0, 10)
    assert lo_share == pytest.approx(0.2)
    assert hi_share == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# 2. the on/off-switch exclusion
# ---------------------------------------------------------------------------
def test_switch_exclusion():
    # switches, judged from the strategy file's own declaration
    assert ka.is_switch({"type": "bool", "default": True})
    assert ka.is_switch({"type": "str", "options": ["On", "Off"]})
    assert ka.is_switch({"type": "int", "min": 0, "max": 1, "step": 1})     # 2 settings

    # NOT switches
    assert not ka.is_switch({"type": "float", "min": 0.0, "max": 1.0, "step": 0.1})
    assert not ka.is_switch({"type": "str", "options": ["A", "B", "C"]})
    assert not ka.is_switch({})
    # a continuous knob that ONE search happened to give only two values to is an
    # under-searched range, not a switch -- the file is the authority, not the grid
    assert not ka.is_switch({"type": "float", "min": 0.5, "max": 2.5, "step": 0.25})

    # step counts drive the budget arithmetic
    assert ka.step_count({"type": "bool"}) == 2
    assert ka.step_count({"type": "str", "options": ["A", "B", "C"]}) == 3
    assert ka.step_count({"min": 0, "max": 10, "step": 1}) == 11
    assert ka.step_count({"min": 0.0, "max": 0.5, "step": 0.05}) == 11

    # a switch is on an edge by construction, so it must never reach the WIDEN branch:
    # the same evidence gives WIDEN as a range and a switch verdict as a switch.
    ev = dict(n_runs=20, edge_rate=1.0, lo_share=0.0, hi_share=1.0, iqr=0.0,
              med_pps=0.0, n_power=10, lo=0.0, hi=1.0, median_pos=1.0)
    assert ka.recommend(dict(ev, kind="range"))[0] == "WIDEN"
    v, why = ka.recommend(dict(ev, kind="switch"))
    assert v == "FREEZE" and "switch" in why


# ---------------------------------------------------------------------------
# 3. drift
# ---------------------------------------------------------------------------
def test_drift_correlation():
    ts = ["2026-01-01 10:00", "2026-02-01 10:00", "2026-03-01 10:00",
          "2026-04-01 10:00", "2026-05-01 10:00"]
    assert ka.drift_rho(ts, [1, 2, 3, 4, 5]) == pytest.approx(1.0)     # rises with time
    assert ka.drift_rho(ts, [5, 4, 3, 2, 1]) == pytest.approx(-1.0)    # falls with time
    assert np.isnan(ka.drift_rho(ts, [3, 3, 3, 3, 3]))                 # never moves
    assert np.isnan(ka.drift_rho(ts[:2], [1, 2]))                      # too few runs
    assert np.isnan(ka.drift_rho(["n/a"] * 5, [1, 2, 3, 4, 5]))        # no usable dates
    # a non-monotone wander sits near zero, not at the extremes
    assert abs(ka.drift_rho(ts, [3, 1, 4, 2, 3])) < 0.7


# ---------------------------------------------------------------------------
# 4. the recommendation ladder, end to end
# ---------------------------------------------------------------------------
STRAT_SRC = '''
DEFAULT_PARAMS = {
    "stuck":  {"default": 2.0, "min": 0.0, "max": 4.0, "step": 0.5, "type": "float"},
    "maxed":  {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.5, "type": "float"},
    "useful": {"default": 5.0, "min": 0.0, "max": 10.0, "step": 1.0, "type": "float"},
    "thin":   {"default": 1.0, "min": 0.0, "max": 3.0, "step": 1.0, "type": "float"},
}
'''


def _mkrun(rid, params, month, rel):
    return dict(id=rid, famKey="SYN", strategy="SYN_1_0.py",
                timestamp=f"2026-{month:02d}-01 09:00", best_params=params,
                relationship=rel,
                selection={"candidates": [
                    {"crowned": True, "params": params, "lockbox": {"total_pnl": 100.0}},
                    {"crowned": False, "params": dict(params, useful=params["useful"] + 1),
                     "lockbox": {"total_pnl": 10.0}},
                    {"crowned": False, "params": dict(params, useful=params["useful"] - 1),
                     "lockbox": {"total_pnl": 1.0}},
                ]})


def test_recommendation_rules(tmp_path):
    # --- unit level: each rung of the ladder fires on its own evidence
    base = dict(kind="range", n_runs=20, edge_rate=0.0, lo_share=0.0, hi_share=0.0,
                iqr=0.05, med_pps=0.0, n_power=10, lo=1.0, hi=5.0, median_pos=0.5)
    assert ka.recommend(base)[0] == "FREEZE"                         # no power, sits still
    assert ka.recommend(dict(base, n_runs=2))[0] == "UNCLEAR"        # too few runs
    assert "3 more" in ka.recommend(dict(base, n_runs=2))[1]
    assert ka.recommend(dict(base, edge_rate=0.8, hi_share=0.8))[0] == "WIDEN"
    assert ka.recommend(dict(base, med_pps=0.2))[0] == "KEEP"
    assert ka.recommend(dict(base, iqr=0.6))[0] == "UNCLEAR"         # no power but wanders
    assert ka.recommend(dict(base, n_power=0, med_pps=np.nan))[0] == "UNCLEAR"
    # a majority parked on a 0 floor is a decision to switch the knob off, not a fence
    v, why = ka.recommend(dict(base, lo=0.0, edge_rate=0.9, lo_share=0.9, iqr=0.4))
    assert v == "FREEZE" and ka.OFF_FLOOR_TAG in why

    # the range the audit would declare instead, snapped to the declared step
    assert ka.widen_to(0.0, 2.0, 0.5, hi_share=0.9, lo_share=0.0) == (0.0, 3.0)
    assert ka.widen_to(10.0, 40.0, 1.0, hi_share=0.0, lo_share=0.9) == (5.0, 40.0)

    # --- end to end over a synthetic run cache
    sd = tmp_path / "augur_strategies"
    sd.mkdir()
    (sd / "SYN_1_0.py").write_text(STRAT_SRC, encoding="utf-8")
    ka.STRAT_DIR = str(sd)
    ka._PARAM_CACHE.clear()

    cd = tmp_path / "runs"
    cd.mkdir()
    rel = [{"param": "stuck", "pps": 0.0, "mi": 0.0, "r": 0.0},
           {"param": "maxed", "pps": 0.0, "mi": 0.1, "r": 0.1},
           {"param": "useful", "pps": 0.30, "mi": 0.9, "r": 0.5},
           {"param": "thin", "pps": 0.10, "mi": 0.2, "r": 0.2}]
    for i in range(8):
        p = {"stuck": 2.0,                       # never moves, no power   -> FREEZE
             "maxed": 2.0,                       # always the ceiling      -> WIDEN
             "useful": 4.0 + (i % 3),            # interior, real power    -> KEEP
             "thin": 1.0}
        (cd / f"{100 + i}.json").write_text(json.dumps(_mkrun(100 + i, p, i + 1, rel)),
                                            encoding="utf-8")
    # one extra run of a different family, too few to judge -> UNCLEAR
    (cd / "200.json").write_text(json.dumps(dict(
        _mkrun(200, {"stuck": 1.0, "maxed": 1.0, "useful": 5.0, "thin": 2.0}, 9, rel),
        famKey="LONE")), encoding="utf-8")

    docs = ka.load_docs(str(cd))
    assert len(docs) == 9
    _, res, _ = ka.audit(docs, min_runs=5)
    got = res.set_index(["famKey", "param"])["recommendation"].to_dict()
    assert got[("SYN", "stuck")] == "FREEZE"
    assert got[("SYN", "maxed")] == "WIDEN"
    assert got[("SYN", "useful")] == "KEEP"
    assert got[("LONE", "useful")] == "UNCLEAR"

    row = res.set_index(["famKey", "param"]).loc[("SYN", "maxed")]
    assert (row["widen_lo"], row["widen_hi"]) == (0.0, 3.0)
    assert res.set_index(["famKey", "param"]).loc[("SYN", "stuck"), "pin_at"] == 2.0

    # the sanity check: only `useful` was ever varied between the finalists, so the
    # FREEZE on `stuck` must be flagged as an artifact of the grid, not hidden
    idx = res.set_index(["famKey", "param"])
    assert bool(idx.loc[("SYN", "stuck"), "freeze_is_artifact"]) is True
    assert idx.loc[("SYN", "stuck"), "share_finalists_all_same"] == pytest.approx(1.0)
    assert idx.loc[("SYN", "useful"), "share_finalists_all_same"] == pytest.approx(0.0)

    # budget: freezing `stuck` removes its 9 settings from the grid
    bud = ka.budget(res, docs)
    syn = bud.set_index("famKey").loc["SYN"]
    assert syn["knobs_now"] == 4 and syn["knobs_kept"] == 3
    assert syn["grid_now"] == 9 * 5 * 11 * 4
    assert syn["grid_kept"] == 5 * 11 * 4
