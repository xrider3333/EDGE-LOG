"""fold_anchor: stored fold bounds follow their bars by timestamp, or refuse naming what moved (MANAGER #100)."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import fold_anchor as FA  # noqa: E402


def _arrays(n=600, seed=3, start="2020-02-26 09:30"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="1min", tz="US/Eastern")
    c = 9000.0 + np.round(np.cumsum(rng.normal(0, 1.0, n)) * 4) / 4
    o = np.r_[c[0], c[:-1]]
    return dict(index=idx, open=o, high=np.maximum(o, c) + 0.25, low=np.minimum(o, c) - 0.25, close=c,
                volume=rng.integers(100, 900, n).astype(float))


def _take(arr, keep):
    keep = np.asarray(keep)
    return {k: (v[keep] if k != "index" else v[keep]) for k, v in arr.items()}


def test_an_unchanged_window_resolves_same_on_the_fast_path():
    A = _arrays()
    fp, st = FA.window_fp(A), FA.stamp(A, 300, 400, warm_from=250)
    r = FA.resolve(A, st, fp)
    assert (r["a"], r["b"], r["w"], r["status"]) == (300, 400, 250, "same")


def test_bars_added_before_the_fold_shift_it_to_the_same_bars():
    A = _arrays(n=700)
    old = _take(A, np.r_[0:40, 100:700])                 # the run saw a 60-bar hole ...
    fp, st = FA.window_fp(old), FA.stamp(old, 300, 400, warm_from=250)
    r = FA.resolve(A, st, fp)                             # ... that a later splice filled
    assert r["status"] == "shifted" and (r["a"], r["b"], r["w"]) == (360, 460, 310)
    assert np.array_equal(A["close"][r["a"]:r["b"]], old["close"][300:400])


def test_a_price_edit_inside_the_span_refuses_and_names_it():
    A = _arrays()
    fp, st = FA.window_fp(A), FA.stamp(A, 300, 400)
    B = {k: (v.copy() if k != "index" else v) for k, v in A.items()}
    B["low"][350] -= 39.0                                   # a cut-bar repair, like 2026-06-30 10:50
    with pytest.raises(FA.BoundsDrift, match="VALUES-CHANGED"):
        FA.resolve(B, st, fp)
    assert FA.resolve(B, st, fp, strict=False)["status"] == "values-changed"


def test_a_constant_shift_of_the_whole_span_is_re_anchored_not_a_repair():
    A = _arrays()
    fp, st = FA.window_fp(A), FA.stamp(A, 300, 400, warm_from=200)
    B = {k: (v + 125.0 if k in ("open", "high", "low", "close") else v) for k, v in A.items()}
    r = FA.resolve(B, st, fp, strict=False)
    assert r["status"] == "re-anchored"
    with pytest.raises(FA.BoundsDrift, match="RE-ANCHORED"):
        FA.resolve(B, st, fp)
    assert FA.resolve(B, st, fp, allow=("same", "shifted", "re-anchored"))["a"] == 300


def test_a_bar_removed_inside_the_span_is_changed():
    A = _arrays()
    fp, st = FA.window_fp(A), FA.stamp(A, 300, 400)
    B = _take(A, np.r_[0:350, 351:600])
    with pytest.raises(FA.BoundsDrift, match=r"CHANGED: bars added or removed inside the span \(100 -> 99 bars\)"):
        FA.resolve(B, st, fp)


def test_a_bound_whose_bar_is_gone_is_missing_and_the_refusal_says_which_years_moved():
    A = _arrays()
    fp, st = FA.window_fp(A), FA.stamp(A, 300, 400)
    B = _take(A, np.r_[0:300, 301:600])
    with pytest.raises(FA.BoundsDrift, match="MISSING: .*start.*bars per year moved: 2020 -1"):
        FA.resolve(B, st, fp)


def test_explain_text_is_added_to_the_refusal():
    A = _arrays()
    st = FA.stamp(A, 300, 400)
    B = _take(A, np.r_[0:350, 351:600])
    with pytest.raises(FA.BoundsDrift, match="splice NQ 2020-02-28 by TBIS"):
        FA.resolve(B, st, explain=lambda s: "splice NQ 2020-02-28 by TBIS")


def test_stamps_and_fingerprints_stay_small_and_serialisable():
    import json
    A = _arrays(n=5000)
    fp, st = FA.window_fp(A, {"filename": "NOADJ_NQ_1m_ETH.csv"}), FA.stamp(A, 2000, 3000, warm_from=1500)
    assert len(json.dumps(st)) < 300 and len(json.dumps(fp)) < 1200
    assert fp["master"] == "NOADJ_NQ_1m_ETH.csv" and fp["master_sha"] == ""      # no uploads dir given


def test_bad_bounds_are_refused_at_stamp_time():
    A = _arrays()
    for a, b, w in ((300, 300, None), (300, 700, None), (300, 400, 350), (-1, 10, None)):
        with pytest.raises(ValueError):
            FA.stamp(A, a, b, warm_from=w)
