"""Unit tests for tools/feature_board.py's promotion rule — synthetic cells only, no
engine run, no network. Importing tools.feature_board must not touch Firestore or run
any backtest (those only happen inside build_leg/main), so these tests import fast."""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("feature_board", os.path.join(ROOT, "tools", "feature_board.py"))
FB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FB)

LEGS = [
    dict(key="ORB_A", family="ORB"),
    dict(key="ORB_B", family="ORB"),
    dict(key="NOISE_A", family="NOISE"),
    dict(key="ENGUQ_A", family="ENGUQ"),
    dict(key="NQDIP_A", family="NQDIP"),
]
FEATURES = [dict(name="feat_x", label="Feature X", group="bar", desc="test feature")]


def _cell(rho, survives, lb_agrees=None):
    return dict(rho=rho, ci_lo=0.01, ci_hi=0.20, q=0.01, n=100, survives=survives,
               beats_probe=True, lb_rho=(rho if lb_agrees else -rho) if lb_agrees is not None else None,
               lb_n=(50 if lb_agrees is not None else 0), lb_agrees=lb_agrees)


def test_promoted_needs_three_families_same_sign_and_lockbox_agreement():
    cells = {"feat_x": {
        "ORB_A": _cell(0.15, True, lb_agrees=True),
        "NOISE_A": _cell(0.10, True, lb_agrees=True),
        "ENGUQ_A": _cell(0.20, True, lb_agrees=True),
        "NQDIP_A": _cell(0.05, False),                 # did not survive — shouldn't matter
    }}
    verdicts = FB.promote(cells, FEATURES, LEGS)
    v = verdicts[0]
    assert v["tier"] == "PROMOTED"
    assert v["sign"] == "+"
    assert set(v["families_agree"]) == {"ORB", "NOISE", "ENGUQ"}
    assert v["lb_agree_count"] == 3


def test_watch_when_only_two_families_agree():
    cells = {"feat_x": {
        "ORB_A": _cell(0.15, True, lb_agrees=True),
        "NOISE_A": _cell(0.10, True, lb_agrees=True),
        "ENGUQ_A": _cell(0.05, False),
        "NQDIP_A": _cell(0.02, False),
    }}
    verdicts = FB.promote(cells, FEATURES, LEGS)
    v = verdicts[0]
    assert v["tier"] == "WATCH"
    assert set(v["families_agree"]) == {"ORB", "NOISE"}


def test_watch_when_three_families_agree_but_lockbox_sign_flips_in_one():
    cells = {"feat_x": {
        "ORB_A": _cell(0.15, True, lb_agrees=True),
        "NOISE_A": _cell(0.10, True, lb_agrees=True),
        "ENGUQ_A": _cell(0.20, True, lb_agrees=False),   # sign flipped in lockbox
        "NQDIP_A": _cell(0.05, False),
    }}
    verdicts = FB.promote(cells, FEATURES, LEGS)
    v = verdicts[0]
    assert v["tier"] == "WATCH"
    assert set(v["families_agree"]) == {"ORB", "NOISE", "ENGUQ"}
    assert v["reason"]


def test_none_when_signs_disagree_or_nothing_survives():
    cells = {"feat_x": {
        "ORB_A": _cell(0.15, True, lb_agrees=True),
        "NOISE_A": _cell(-0.10, True, lb_agrees=True),    # opposite sign
        "ENGUQ_A": _cell(0.20, False),
        "NQDIP_A": _cell(0.05, False),
    }}
    verdicts = FB.promote(cells, FEATURES, LEGS)
    v = verdicts[0]
    assert v["tier"] == "NONE"
    assert v["families_agree"] == []

    cells2 = {"feat_x": {k: None for k in ("ORB_A", "NOISE_A", "ENGUQ_A", "NQDIP_A")}}
    verdicts2 = FB.promote(cells2, FEATURES, LEGS)
    assert verdicts2[0]["tier"] == "NONE"


def test_one_leg_per_family_is_enough_for_lockbox_agreement():
    """Two ORB legs: one survives with lb_agrees False, the other survives with
    lb_agrees True — the family only needs ONE agreeing leg, not both."""
    cells = {"feat_x": {
        "ORB_A": _cell(0.15, True, lb_agrees=False),
        "ORB_B": _cell(0.12, True, lb_agrees=True),
        "NOISE_A": _cell(0.10, True, lb_agrees=True),
        "ENGUQ_A": _cell(0.20, True, lb_agrees=True),
        "NQDIP_A": _cell(0.05, False),
    }}
    verdicts = FB.promote(cells, FEATURES, LEGS)
    v = verdicts[0]
    assert v["tier"] == "PROMOTED"
    assert set(v["families_agree"]) == {"ORB", "NOISE", "ENGUQ"}


def test_lift_detects_planted_tail_effect_that_rank_misses():
    """A binary feature where 97% of ON trades look identical to OFF trades, but
    3% of ON trades are huge winners (+8000 vs a ~N(-30, 100) baseline). Spearman
    barely moves (a rare outlier only shifts a few percent of the ranks), but the
    mean-based lift statistic should catch it clearly and survive."""
    rng = np.random.default_rng(0)
    n_days, per_day = 600, 4
    days = pd.date_range("2020-01-01", periods=n_days, freq="B")
    entry_date = np.repeat(np.array([d.date() for d in days]), per_day)
    n = len(entry_date)
    comp = rng.integers(0, 2, size=n).astype(float)
    pnl = rng.normal(-30, 100, size=n)
    big = (comp == 1) & (rng.random(n) < 0.03)
    pnl[big] += 8000
    X = pd.DataFrame({"compressed_60m": comp})
    lb = np.zeros(n, dtype=bool)
    lb[-int(n * 0.15):] = True
    data = dict(X=X, usd=pnl, entry_date=entry_date, lb=lb,
               daily_series={"compressed_60m": pd.Series(comp[:len(days)], index=[d.date() for d in days])})

    out = FB.score_leg(data)
    c = out["compressed_60m"]
    assert abs(c["rho"]) < 0.03 and c["survives"] is False, c
    assert c["lift_r"] > 1.5
    assert c["lift_lo"] > 0
    assert c["lift_survives"] is True, c


def test_permutation_pvalue_roughly_uniform_under_the_null():
    """When the feature carries no real relationship to the outcome, the
    permutation p-value should not be systematically small -- average p over many
    independent null draws should sit near 0.5, not collapse toward 0."""
    rng = np.random.default_rng(123)
    pvals = []
    for trial in range(30):
        n_days, per_day = 60, 5
        day_code = np.repeat(np.arange(n_days), per_day)
        n = len(day_code)
        day_vals = rng.integers(0, 2, size=n_days).astype(float)
        x = day_vals[day_code]
        r = rng.normal(size=n)
        spec = FB._lift_threshold_spec(x)
        hi, lo = FB._lift_masks(x, spec)
        obs = FB._lift_r(r, hi, lo)
        p = FB._lift_perm_pvalue(x, r, spec, obs, day_code, n_days, "day", n_perm=200, seed=trial)
        pvals.append(p)
    pvals = np.array(pvals)
    assert 0.3 < pvals.mean() < 0.7, pvals.mean()


def _lift_only_cell(lift_r, lift_survives, lb_lift_agrees=None):
    return dict(rho=0.01, survives=False, beats_probe=False, lb_rho=None, lb_n=0, lb_agrees=None,
               lift_r=lift_r, lift_lo=0.1, lift_hi=2.0, lift_p=0.001, lift_q=0.01,
               lift_beats_probe=True, lift_survives=lift_survives,
               lb_lift_r=((lift_r if lb_lift_agrees else -lift_r) if lb_lift_agrees is not None else None),
               lb_lift_agrees=lb_lift_agrees)


def test_promotion_picks_lift_basis_when_only_lift_clears():
    cells = {"feat_x": {
        "ORB_A": _lift_only_cell(2.5, True, lb_lift_agrees=True),
        "NOISE_A": _lift_only_cell(1.8, True, lb_lift_agrees=True),
        "ENGUQ_A": _lift_only_cell(3.0, True, lb_lift_agrees=True),
        "NQDIP_A": _lift_only_cell(0.1, False),
    }}
    verdicts = FB.promote(cells, FEATURES, LEGS)
    v = verdicts[0]
    assert v["tier"] == "PROMOTED"
    assert v["basis"] == "lift"
    assert set(v["families_agree"]) == {"ORB", "NOISE", "ENGUQ"}


def _both_cell(rho, lift_r):
    """rank AND lift both clear their bars, with whatever signs are passed in."""
    c = _lift_only_cell(lift_r, True, lb_lift_agrees=True)
    c.update(rho=rho, survives=True, beats_probe=True, lb_rho=rho, lb_n=100, lb_agrees=True)
    return c


def test_conflict_when_rank_and_lift_point_opposite_ways():
    # rank says HURTS (rho < 0) in three families while lift says HELPS (lift_r > 0):
    # a tail-vs-bulk contradiction. Must never read as PROMOTED "on both".
    cells = {"feat_x": {
        "ORB_A": _both_cell(-0.12, 0.9),
        "NOISE_A": _both_cell(-0.08, 0.5),
        "ENGUQ_A": _both_cell(-0.14, 1.0),
        "NQDIP_A": _both_cell(0.01, 0.0),
    }}
    v = FB.promote(cells, FEATURES, LEGS)[0]
    assert v["basis"] == "conflict"
    assert v["tier"] == "WATCH"
    assert v["sign"] == "mixed"
    assert "disagree" in v["reason"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
