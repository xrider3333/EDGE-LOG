"""A BOOK leg with no params must be refused, not silently run on file defaults.

WHY (2026-09-25). BOOK runs #419, #417 and #418 were queued with the `params` block
missing on their first legs. Nothing in the engine or the saved run said so, and each of
those legs quietly ran its strategy FILE's DEFAULT_PARAMS instead of the frozen settings
the book card named: the ENGU-Q leg booked 2,843 trades / $420,506 where run #396's leg
books 1,949 / $603,381, and the card still read "#396 + TTIBS". Nothing is tuned inside a
book run, so a leg's params ARE the leg - an empty block is never a harmless default.

The guard refuses the job before any backtest runs. A leg that really does want the file
defaults says so with "use_defaults": true, which leaves the intent on the job doc.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.runner import book_legs_missing_params as missing  # noqa: E402


def _leg(name, **kw):
    return dict(strategy=name, instrument="NQ", timeframe="5m", session="rth",
                source="db_noadj_rth", cost_pts=0.533, mult=20, weight=1, **kw)


def test_a_fully_specified_book_is_accepted():
    legs = [_leg("ORB_3_6_C2.py", params={"or_bars": 2, "target_R": 5.5}),
            _leg("NOISE_1_0.py", params={"lookback": 40})]
    assert missing(legs) == []


def test_the_419_shape_is_caught_and_the_leg_is_named():
    """#419's own shape: the first legs carry no params at all."""
    legs = [_leg("ENGUQ_1M_ETH_R2_1_0.py"),
            _leg("NOISE_1_0.py"),
            _leg("TTIBS_1_0.py", params={"entry": 1.0})]
    bad = missing(legs)
    assert len(bad) == 2
    assert "leg 1 (ENGUQ_1M_ETH_R2_1_0.py)" in bad
    assert "leg 2 (NOISE_1_0.py)" in bad
    assert not any("TTIBS" in b for b in bad)


def test_an_empty_params_dict_counts_as_missing():
    """`params: {}` is the same silent substitution as no key at all."""
    assert missing([_leg("ORB_3_6.py", params={})]) == ["leg 1 (ORB_3_6.py)"]


def test_use_defaults_is_the_explicit_opt_in():
    assert missing([_leg("ORB_3_6.py", use_defaults=True)]) == []
    # ...and it is only an opt-in when it is actually true
    assert missing([_leg("ORB_3_6.py", use_defaults=False)]) == ["leg 1 (ORB_3_6.py)"]


def test_rows_that_are_not_legs_are_ignored():
    """A blank row or a note in the legs array must not become a phantom complaint."""
    assert missing([{"note": "spacer"}, None, {"strategy": ""},
                    _leg("ORB_3_6.py", params={"or_bars": 2})]) == []


def test_leg_numbers_are_the_position_in_the_job_doc():
    """The message has to point at the row to fix, counting from 1 including good legs."""
    legs = [_leg("A.py", params={"k": 1}), _leg("B.py", params={"k": 1}), _leg("C.py")]
    assert missing(legs) == ["leg 3 (C.py)"]


def test_no_legs_at_all_is_not_this_guard_s_complaint():
    """An empty book is the engine's own error ('a book needs at least one leg')."""
    assert missing([]) == []
    assert missing(None) == []
