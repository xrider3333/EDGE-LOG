"""Fast synthetic tests for tools/candidate_board.py -- no Firestore, no market data.

Four checks, one per load-bearing piece:
  1. harvest -> build_table shape (cache-only harvest, BOOK runs skipped, columns present)
  2. the rank-correlation math (spearman: perfect / reversed / uninformative)
  3. the crowned-vs-rest paired test (sign_test + the q2 pairing itself)
  4. the fence detector (on_fence + searched_ranges + q6 aggregation)
"""
import os
import sys
import json

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import candidate_board as cb  # noqa: E402


# ---------------------------------------------------------------------------
def _cand(ix, crowned, is_pnl, wf, lb_net, params, lb_dd=-1000.0, lb_pf=1.5):
    return {
        "crowned": crowned,
        "params": params,
        "is_pnl": is_pnl,
        "wf_oos_pnl": wf,
        "folds_held": 6,
        "cal": {
            "is": {"total_pnl": is_pnl * 0.2, "profit_factor": 1.3, "num_trades": 100,
                   "max_drawdown": -500.0},
            "wf": {"total_pnl": wf, "profit_factor": 1.4, "num_trades": 200, "max_drawdown": -800.0},
            "pre": {"total_pnl": is_pnl + wf, "profit_factor": 1.35, "num_trades": 300,
                    "max_drawdown": -900.0},
        },
        "metrics": {"total_pnl": is_pnl + wf, "profit_factor": 1.35, "num_trades": 300,
                    "max_drawdown": -900.0},
        "lockbox": {"total_pnl": lb_net, "profit_factor": lb_pf, "num_trades": 50,
                    "max_drawdown": lb_dd},
    }


def _run_doc(rid, cands, fam="FAKE", ranges=None, points=None):
    d = {
        "id": rid, "famKey": fam, "famSeq": rid, "strategy": f"FAKE_{rid}.py",
        "instrument": "NQ", "timeframe": "1m", "data_source": "db_noadj_eth",
        "timestamp": f"2026-0{1 + rid % 9}-01 10:00", "date_from": "2010-01-01",
        "date_to": "2026-06-30", "n_evaluated": 500, "dsr": {"dsr": 0.9},
        "selection": {"candidates": cands},
        "validate": {"windows": {"optimize": ["2010-01-01", "2025-06-30"],
                                 "lockbox": ["2025-06-30", "2026-06-30"], "lockbox_months": 12},
                     "pbo": {"pbo": 0.2}},
        "relationship": [{"param": "a", "mi": 0.2, "r": 0.5, "pps": 0.15},
                         {"param": "b", "mi": 0.0, "r": 0.01, "pps": 0.0}],
    }
    if ranges:
        d["auto_expand"] = [{"param": p, "orig_range": list(r), "final_range": list(r)}
                            for p, r in ranges.items()]
    if points:
        d["points"] = points
    return d


def _write_cache(tmp_path, docs):
    """Materialise a fake run cache so harvest(fetch=False) reads it off disk."""
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    for rid, d in docs.items():
        (runs / f"{rid}.json").write_text(json.dumps(d), encoding="utf-8")
    cb.RUN_CACHE_DIR = str(runs)
    cb.MISSING_FP = str(runs / "_missing.json")
    return runs


# ---------------------------------------------------------------------------
# 1. harvest -> table shape
# ---------------------------------------------------------------------------
def test_harvest_builds_table_and_skips_books(tmp_path):
    prm = {"a": 1.0, "b": 10.0}
    docs_in = {
        1: _run_doc(1, [_cand(i, i == 0, 100.0 * i, 50.0 * i, 10.0 * i, prm) for i in range(10)]),
        2: _run_doc(2, [_cand(i, i == 3, 100.0 * i, 50.0 * i, -5.0 * i, prm) for i in range(10)]),
    }
    book = _run_doc(3, [_cand(0, True, 1.0, 1.0, 1.0, prm)], fam="BOOK-13")
    book["book"] = {"legs": ["x", "y"]}
    docs_in[3] = book
    _write_cache(tmp_path, docs_in)

    docs = cb.harvest(max_id=5, fetch=False, verbose=False)
    assert set(docs) == {1, 2, 3}
    assert cb.READS["n"] == 0, "cache-only harvest must not touch Firestore"

    df = cb.build_table(docs)
    assert len(df) == 20, "two 10-candidate runs; the BOOK run must be dropped"
    assert set(df["run"]) == {1, 2}
    for col in ("run", "famKey", "strategy", "instrument", "timeframe", "session",
                "lb_from", "lb_to", "params", "crowned", "folds_held", "pbo", "dsr",
                "n_evaluated", "is_pnl", "wf_oos_pnl"):
        assert col in df.columns, col
    for tag in ("is", "wf", "pre", "lb"):
        for m in ("net", "pf", "trades", "dd", "netdd"):
            assert f"{tag}_{m}" in df.columns
    assert df["session"].iloc[0] == "ETH"
    assert df.groupby("run")["crowned"].sum().tolist() == [1, 1]
    # net/DD sign convention: dd is stored negative, net/DD must use its magnitude
    row = df[(df["run"] == 1) & (df["cand_ix"] == 5)].iloc[0]
    assert row["lb_netdd"] == pytest.approx(50.0 / 1000.0)
    # only run 1 is scoreable-clean on lockbox; both have >=3 lockbox rows
    assert cb.scoreable(df)["run"].nunique() == 2


# ---------------------------------------------------------------------------
# 2. rank-correlation math
# ---------------------------------------------------------------------------
def test_spearman_math():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert cb.spearman(x, [10.0, 20.0, 30.0, 40.0, 50.0]) == pytest.approx(1.0)
    assert cb.spearman(x, [50.0, 40.0, 30.0, 20.0, 10.0]) == pytest.approx(-1.0)
    # monotone but non-linear -> Spearman still 1 (it is a RANK correlation)
    assert cb.spearman(x, [1.0, 4.0, 9.0, 16.0, 25.0]) == pytest.approx(1.0)
    assert np.isnan(cb.spearman(x, [7.0] * 5)), "constant side carries no ranking"
    assert np.isnan(cb.spearman([1.0, 2.0], [1.0, 2.0])), "fewer than 3 pairs"
    # NaNs are dropped pairwise, not propagated
    assert cb.spearman([1.0, 2.0, np.nan, 4.0], [1.0, 2.0, 99.0, 4.0]) == pytest.approx(1.0)

    # a perfectly informative run and a perfectly anti-informative one average to zero,
    # and the sign-flip permutation must NOT call that significant
    obs, p = cb.perm_p_mean([1.0, -1.0, 1.0, -1.0, 1.0, -1.0], n_perm=2000)
    assert obs == pytest.approx(0.0)
    assert p > 0.5
    obs, p = cb.perm_p_mean([0.9] * 12, n_perm=2000)
    assert obs == pytest.approx(0.9)
    assert p < 0.01

    # q1 end-to-end on a run whose IS order exactly reproduces the LB order
    prm = {"a": 1.0}
    docs = {1: _run_doc(1, [_cand(i, i == 0, 100.0 * i, 1.0, 10.0 * i, prm) for i in range(10)])}
    df = cb.build_table(docs)
    out, summ = cb.q1(cb.scoreable(df), "is_pnl")
    assert out["rho"].iloc[0] == pytest.approx(1.0)
    assert out["top_is_lb_rank"].iloc[0] == 1 and bool(out["top3"].iloc[0])


# ---------------------------------------------------------------------------
# 3. crowned-vs-rest paired test
# ---------------------------------------------------------------------------
def test_crowned_vs_rest_paired_test():
    # sign test: 8 positives out of 8 is significant; a 50/50 split is not; zeros drop out
    n, k, p = cb.sign_test([1.0] * 8)
    assert (n, k) == (8, 8) and p < 0.01
    n, k, p = cb.sign_test([1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    assert (n, k) == (6, 3) and p > 0.5
    n, k, _ = cb.sign_test([1.0, 0.0, -1.0, np.nan])
    assert (n, k) == (2, 1), "exact zeros and NaNs are excluded from a sign test"
    # effect size is undefined when every paired difference is identical (zero variance)
    assert np.isnan(cb.cohen_d_paired([2.0, 2.0, 2.0, 2.0]))
    assert cb.cohen_d_paired([2.0, 3.0, 4.0, 5.0]) > 0

    prm = {"a": 1.0}
    # runs where the CROWNED candidate is the lockbox best by a wide margin
    docs = {}
    for rid in range(1, 9):
        cands = [_cand(i, i == 0, 100.0 * i, 50.0, 500.0 if i == 0 else 10.0, prm, lb_pf=2.5 if i == 0 else 1.1)
                 for i in range(10)]
        docs[rid] = _run_doc(rid, cands)
    det, res = cb.q2(cb.scoreable(cb.build_table(docs)))
    assert len(det) == 8
    assert res["lb_net"]["n_pos"] == 8 and res["lb_net"]["p"] < 0.01
    assert res["lb_net"]["median_d"] == pytest.approx(500.0 - 10.0)
    assert res["lb_pf"]["n_pos"] == 8
    assert res["lb_netdd"]["n_pos"] == 8

    # and the mirror: crowning the WORST candidate must come out significantly negative
    docs2 = {}
    for rid in range(1, 9):
        # jitter per run so the paired differences have non-zero variance and Cohen's d
        # is defined (identical diffs legitimately return NaN -- asserted above)
        cands = [_cand(i, i == 0, 100.0 * i, 50.0, -500.0 - 10.0 * rid if i == 0 else 10.0, prm)
                 for i in range(10)]
        docs2[rid] = _run_doc(rid, cands)
    _, res2 = cb.q2(cb.scoreable(cb.build_table(docs2)))
    assert res2["lb_net"]["n_pos"] == 0 and res2["lb_net"]["p"] < 0.01
    assert res2["lb_net"]["d_effect"] < 0


# ---------------------------------------------------------------------------
# 4. fence detector
# ---------------------------------------------------------------------------
def test_fence_detector():
    assert cb.on_fence(0.0, 0.0, 1.0) is True          # exactly the low edge
    assert cb.on_fence(1.0, 0.0, 1.0) is True          # exactly the high edge
    assert cb.on_fence(0.5, 0.0, 1.0) is False         # interior
    assert cb.on_fence(0.015, 0.0, 1.0) is True        # inside the 2% tolerance
    assert cb.on_fence(0.05, 0.0, 1.0) is False        # outside it
    assert cb.on_fence(np.nan, 0.0, 1.0) is False
    assert cb.on_fence(0.5, 1.0, 1.0) is False, "degenerate range is never a fence"

    # searched_ranges prefers auto_expand.final_range, then falls back to the points grid.
    # `sw` is an on/off switch: only two values ever tried.
    pts = [{"a": 0.2, "b": 2.0, "c": 1.0, "sw": 0.0, "pnl": 5.0, "dd": -1.0},
           {"a": 0.5, "b": 6.0, "c": 4.0, "sw": 1.0, "pnl": 6.0, "dd": -1.0},
           {"a": 0.8, "b": 9.0, "c": 7.0, "sw": 0.0, "pnl": 7.0, "dd": -1.0}]
    doc = _run_doc(1, [_cand(0, True, 1.0, 1.0, 1.0, {"a": 0.0, "b": 5.0, "c": 3.0, "sw": 1.0})],
                   ranges={"a": (0.0, 1.0)}, points=pts)
    rng = cb.searched_ranges(doc)
    assert rng["a"] == (0.0, 1.0), "auto_expand wins over the observed points"
    assert rng["b"] == (2.0, 9.0), "no auto_expand -> empirical min/max over points+candidates"
    assert "pnl" not in rng and "dd" not in rng, "score columns are not knobs"

    counts = cb.grid_counts(doc)
    assert counts["sw"] == 2 and counts["a"] >= 3

    # q6: knob a is pinned to its low edge, b and c are interior, sw is an excluded switch
    df = cb.build_table({1: doc})
    det, fam = cb.q6(df, {1: doc})
    assert len(det) == 1
    r = det.iloc[0]
    assert r["n_knobs"] == 3, "the on/off switch must NOT count as a fenceable knob"
    assert r["n_binary"] == 1
    assert r["n_fenced"] == 1
    assert r["fenced_params"] == "a" and bool(r["any_fenced"])
    assert r["frac_fenced"] == pytest.approx(1 / 3)
    assert fam["share_any"].iloc[0] == pytest.approx(1.0)

    # a fully interior crown must report no fence at all
    doc2 = _run_doc(2, [_cand(0, True, 1.0, 1.0, 1.0, {"a": 0.5})], ranges={"a": (0.0, 1.0)},
                   points=[{"a": 0.1, "pnl": 1.0}, {"a": 0.5, "pnl": 2.0}, {"a": 0.9, "pnl": 3.0}])
    det2, _ = cb.q6(cb.build_table({2: doc2}), {2: doc2})
    assert det2["n_fenced"].iloc[0] == 0 and not bool(det2["any_fenced"].iloc[0])

    # a run whose ONLY knobs are switches yields no fence row at all (not a false 100%)
    doc3 = _run_doc(3, [_cand(0, True, 1.0, 1.0, 1.0, {"sw": 1.0})],
                    points=[{"sw": 0.0, "pnl": 1.0}, {"sw": 1.0, "pnl": 2.0}])
    det3, _ = cb.q6(cb.build_table({3: doc3}), {3: doc3})
    assert len(det3) == 0
