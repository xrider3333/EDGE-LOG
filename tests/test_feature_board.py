"""Unit tests for tools/feature_board.py's promotion rule — synthetic cells only, no
engine run, no network. Importing tools.feature_board must not touch Firestore or run
any backtest (those only happen inside build_leg/main), so these tests import fast."""
import importlib.util
import os

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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
