"""api/book_shadow.py - the #463 shadow lines (volatility target, agreement tilt)."""
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


def _t(entry, exit_, side, pnl):
    return {"entryIso": f"2026-09-30T{entry}:00-04:00", "exitIso": f"2026-09-30T{exit_}:00-04:00", "side": side, "pnl_usd": pnl}


def test_agreement_tilt_rule():
    reports = {
        "ORB": {"_trades": [_t("09:40", "15:55", 1, 800.0),       # ORB long open all day
                            _t("09:30", "09:35", -1, -50.0)]},     # a short, closed before NOISE trades
        "NOISE_422": {"_trades": [_t("10:15", "11:00", 1, 300.0),   # enters while ORB is long -> tilted
                                  _t("11:30", "12:00", -1, -200.0),  # short while ORB long -> not tilted
                                  _t("09:30", "09:45", -1, 100.0)]},  # same bar as the ORB short -> NOISE takes it
    }
    tilted = bs.agreement_tilted(reports)
    got = sorted((k, t["entryIso"][11:16]) for k, t in tilted)
    assert got == [("NOISE_422", "09:30"), ("NOISE_422", "10:15")]
    blk = bs.ag_block(reports, {"ORB": 1.0, "NOISE_422": 1.0}, book_pnl=1000.0)
    assert blk["n_tilted"] == 2
    assert blk["pnl_usd"] == 1000.0 + 0.5 * (300.0 + 100.0)


def test_agreement_tilt_orb_entering_inside_noise():
    reports = {"ORB": {"_trades": [_t("10:00", "15:55", 1, 500.0)]},
               "NOISE_422": {"_trades": [_t("09:45", "10:30", 1, 200.0)]}}
    assert [(k, t["entryIso"][11:16]) for k, t in bs.agreement_tilted(reports)] == [("ORB", "10:00")]


def test_book463_legs_match_the_paper_legs():
    from api import paper as P
    by = {l["strategy"]: l for l in bs.BOOK463_LEGS}
    assert by["ORB_3_6_C2.py"]["params"] == dict(P.ORB_234)
    assert by["ENGUQ_1M_ETH_R2_1_0.py"]["params"] == dict(P.ENGUQ_335)
    assert by["NOISE_1_8_CT304H.py"]["params"] == dict(P.NOISE_422)
    assert by["TTMSQZ_3_0_ES30SSOF2.py"]["params"] == dict(P.TTM_299_SSOF2)
    assert by["TTMSQZ_3_0_ES30SSOF2.py"]["weight"] == 3
