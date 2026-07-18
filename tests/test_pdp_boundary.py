"""Unit tests for the PDP boundary-peak detector (3C.1b) —
augur_engine.analytics.pdp_plateau's `boundary_flags` / `search_truncated`.

Each test builds a tiny, fully deterministic points list (one varying param, no
real data) so the smoothed PDP curve is hand-checkable. The rule under test (see
analytics._pdp_boundary_flags): a NUMERIC param's smoothed curve peaking at the
first/last TESTED value while still sloping toward that edge means the search
range was too narrow — the true optimum likely sits outside the tested range —
so it must be flagged instead of silently reported as "the" answer.
"""
from augur_engine import analytics as A


def _pts(param, values, pnls):
    return [{param: v, "pnl": p} for v, p in zip(values, pnls)]


# ── (a) rising to the top edge → flag edge='max' ────────────────────────────────

def test_rising_to_max_edge_flags_max():
    pts = _pts("ibs_entry", [1, 2, 3, 4, 5], [10.0, 20.0, 30.0, 40.0, 50.0])
    r = A.pdp_plateau(pts, min_points=5)
    assert r is not None
    assert r["search_truncated"] is True
    flags = r["boundary_flags"]
    assert len(flags) == 1
    f = flags[0]
    assert f["param"] == "ibs_entry"
    assert f["edge"] == "max"
    assert f["value"] == 5
    assert f["tested_min"] == 1 and f["tested_max"] == 5
    assert f["n_values"] == 5
    assert f["rel_slope"] > A.PDP_EDGE_SLOPE_MIN
    assert "ibs_entry" in f["msg"] and "truncated" in f["msg"]


# ── (b) rising to the bottom edge → flag edge='min' ─────────────────────────────

def test_rising_to_min_edge_flags_min():
    pts = _pts("hold_cap", [1, 2, 3, 4, 5], [50.0, 40.0, 30.0, 20.0, 10.0])
    r = A.pdp_plateau(pts, min_points=5)
    assert r is not None
    assert r["search_truncated"] is True
    flags = r["boundary_flags"]
    assert len(flags) == 1
    f = flags[0]
    assert f["param"] == "hold_cap"
    assert f["edge"] == "min"
    assert f["value"] == 1
    assert f["tested_min"] == 1 and f["tested_max"] == 5
    assert f["n_values"] == 5
    assert f["rel_slope"] > A.PDP_EDGE_SLOPE_MIN
    assert "hold_cap" in f["msg"] and "truncated" in f["msg"]


# ── (c) clean interior peak — properly captured, no flag ────────────────────────

def test_interior_peak_not_flagged():
    pts = _pts("p", [1, 2, 3, 4, 5], [10.0, 30.0, 50.0, 30.0, 10.0])
    r = A.pdp_plateau(pts, min_points=5)
    assert r is not None
    assert r["boundary_flags"] == []
    assert r["search_truncated"] is False


# ── (d) edge technically "rising" but below the noise threshold — no flag ──────

def test_flat_edge_below_threshold_not_flagged():
    # last value nudges up by 0.8 on a flat-100 baseline: rel_slope ~0.3%,
    # comfortably under PDP_EDGE_SLOPE_MIN (2%) — a dead-flat edge, not truncation.
    pts = _pts("p", [1, 2, 3, 4, 5], [100.0, 100.0, 100.0, 100.0, 100.8])
    r = A.pdp_plateau(pts, min_points=5)
    assert r is not None
    assert r["boundary_flags"] == []
    assert r["search_truncated"] is False


# ── (e) categorical param — never flagged, no matter the shape of its curve ────

def test_categorical_param_never_flagged():
    # alphabetically-last value "C" has the highest mean pnl (would look like a
    # rising-to-max edge if it were numeric) — but it's a string param, so no flag.
    pts = _pts("mode", ["A", "B", "C"], [10.0, 30.0, 50.0])
    r = A.pdp_plateau(pts, min_points=3)
    assert r is not None
    assert r["boundary_flags"] == []
    assert r["search_truncated"] is False


# ── multi-param: only the truncated numeric axis is flagged ────────────────────

def test_multi_param_flags_only_the_truncated_axis():
    pts = [{"ibs_entry": ie, "mode": md, "pnl": pnl} for ie, md, pnl in zip(
        [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
        ["A", "A", "A", "A", "A", "B", "B", "B", "B", "B"],
        [10.0, 20.0, 30.0, 40.0, 50.0, 12.0, 22.0, 32.0, 42.0, 52.0])]
    r = A.pdp_plateau(pts, min_points=10)
    assert r is not None
    assert r["search_truncated"] is True
    params_flagged = {f["param"] for f in r["boundary_flags"]}
    assert params_flagged == {"ibs_entry"}   # "mode" is categorical -> never flagged


# ── backward compatibility: only additive — no existing key removed/renamed ────

def test_existing_return_keys_unchanged():
    pts = _pts("p", [1, 2, 3, 4, 5], [10.0, 30.0, 50.0, 30.0, 10.0])
    r = A.pdp_plateau(pts, min_points=5)
    assert set(r) == {"index", "params", "score", "argmax_index", "argmax_score",
                      "curves", "boundary_flags", "search_truncated"}


def test_none_input_still_returns_none():
    assert A.pdp_plateau([], min_points=5) is None
    assert A.pdp_plateau(None, min_points=5) is None
