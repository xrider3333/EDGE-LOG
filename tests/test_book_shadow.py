"""api/book_shadow.py - the #463 shadow lines (volatility target, weighted-sum lines; AG retired 10-01)."""
import numpy as np
import pandas as pd

from api import book_shadow as bs


def _series(n_calm=400, n_wild=40, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_calm + n_wild)
    return pd.Series(np.concatenate([rng.normal(0, 1000, n_calm), rng.normal(0, 4000, n_wild)]), index=idx)


def test_vt_multiplier_is_one_in_calm_and_floors_after_a_vol_spike():
    m = bs.vt_multipliers(_series())
    calm = m.iloc[300:400]
    assert 0.7 <= calm.median() <= 1.3
    assert m.iloc[-1] == bs.VT_LO                     # 4x the usual volatility -> the 0.5 floor
    assert set(np.round(m.unique() * 10) % 1) <= {0.0}  # rounded to 0.1 (micro contracts)


def test_vt_multiplier_uses_only_days_before():
    M = _series()
    base = bs.vt_multipliers(M)
    D = M.index[380]
    M2 = M.copy()
    M2.loc[D:] = M2.loc[D:] * 50                      # change day D and everything after it
    assert bs.vt_multipliers(M2).loc[D] == base.loc[D]


def test_book463_legs_match_the_paper_legs():
    from api import paper as P
    by = {l["strategy"]: l for l in bs.BOOK463_LEGS}
    assert by["ORB_3_6_C2.py"]["params"] == dict(P.ORB_234)
    assert by["ENGUQ_1M_ETH_R2_1_0.py"]["params"] == dict(P.ENGUQ_335)
    assert by["NOISE_1_8_CT304H.py"]["params"] == dict(P.NOISE_422)
    assert by["TTMSQZ_3_0_ES30SSOF2.py"]["params"] == dict(P.TTM_299_SSOF2)
    assert by["TTMSQZ_3_0_ES30SSOF2.py"]["weight"] == 3


def test_sum_shadows_use_real_paper_legs_and_add_up():
    from api import paper as P
    keys = {l["key"] for l in P.PAPER_LEGS}
    for spec in bs.SUM_SHADOWS.values():
        assert set(spec["weights"]) <= keys, set(spec["weights"]) - keys
    reports = {"ORB_R6": {"pnl_usd": 100.0}, "ENGUQ_335_S1": {"pnl_usd": -50.0}, "TTM_299_SSOF2": {"pnl_usd": 10.0}}
    blk = bs.sum_blocks(reports)["book_shadow_q4"]
    assert blk["pnl_usd"] == 100.0 - 50.0 + 30.0
    assert blk["missing"] == ["NOISE_422"]


def test_stale_lag_counts_business_days_behind_d_minus_1():
    D = pd.Timestamp("2026-10-01")                      # a Thursday
    lag = bs.stale_lag({"a": "2026-09-30", "b": "2026-09-29", "c": "2026-09-25", "d": None}, D)
    assert lag == {"a": 0, "b": 1, "c": 3, "d": 99}
    assert bs.stale_lag({"a": "2026-09-25"}, pd.Timestamp("2026-09-28")) == {"a": 0}   # Monday after a Friday


def test_agreement_tilt_line_is_retired():
    # Owner GO via MANAGER #48 (2026-10-01): the AG line is dropped from the nightly report; it must not come back
    # by accident (its evidence was a same-bar look-ahead).
    import inspect
    from api import paper as P
    assert not hasattr(bs, "ag_block") and not hasattr(bs, "agreement_tilted")
    assert "book_shadow_ag" not in inspect.getsource(P)
