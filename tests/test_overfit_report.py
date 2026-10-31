"""C9: Deflated Sharpe + PBO in every report (report-only, AUGUR_OVERFIT_REPORT kill switch)."""
import json
import math

import numpy as np
import pytest

from augur_engine.analytics import (deflated_sharpe, overfit_summary,
                                    probability_backtest_overfitting)


def _winner():
    return {"sr": 2.0, "n": 252, "tpy": 252.0, "skew": 0.0, "kurt": 3.0}


def _srs_var_quarter():
    d = math.sqrt(7.0 / 32.0)            # 8 values +-d around 1.0 -> sample var (ddof=1) 0.25
    return [1.0 + d] * 4 + [1.0 - d] * 4


def test_dsr_matches_hand_computed_case():
    # Hand calc (Bailey & Lopez de Prado 2014), N=100, V[SR]=0.25, SR=2.0/yr, T=252, 1 yr,
    #   normal returns: E[max] factor = 0.42278*Z(0.99) + 0.57722*Z(1-1/(100e)) = 2.530603
    #   SR0 = 0.5 * 2.530603 = 1.265301; per-trade SR = 2/sqrt(252), SR0/sqrt(252)
    #   DSR = Phi((0.125988-0.079706)*sqrt(251) / sqrt(1 + 0.5*0.015873)) = 0.767411
    d = deflated_sharpe(_winner(), _srs_var_quarter(), 100, 1.0)
    assert d["luck_bar"] == pytest.approx(1.2653014466, abs=1e-8)
    assert d["dsr"] == pytest.approx(0.7674109149, abs=1e-8)
    assert d["sr_var"] == pytest.approx(0.25)
    assert (d["skew"], d["kurt"], d["n_obs"], d["n_sr"]) == (0.0, 3.0, 252, 8)
    o = overfit_summary(d, None)
    assert o["dsr"] == pytest.approx(0.7674, abs=1e-4)
    assert o["dsr_p"] == pytest.approx(0.2326, abs=1e-4)
    assert o["n_trials"] == 100 and o["sr_var"] == pytest.approx(0.25)


def test_sr_var_backed_out_for_an_old_dsr_dict():
    d = deflated_sharpe(_winner(), _srs_var_quarter(), 100, 1.0)
    old = {k: d[k] for k in ("winner_sharpe", "luck_bar", "dsr", "n_cfg", "verdict")}
    assert overfit_summary(old, None)["sr_var"] == pytest.approx(0.25, abs=1e-4)


def test_pbo_all_noise_is_about_half():
    rng = np.random.default_rng(7)
    vals = [probability_backtest_overfitting(rng.normal(0, 1, (40, 120)))["pbo"]
            for _ in range(5)]
    assert 0.3 <= float(np.mean(vals)) <= 0.7


def test_pbo_one_real_edge_is_low():
    rng = np.random.default_rng(11)
    m = rng.normal(0, 1, (40, 120))
    m[5] += 1.0                         # one config with a real, persistent edge
    assert probability_backtest_overfitting(m)["pbo"] <= 0.1


def test_fields_present_and_small():
    rng = np.random.default_rng(3)
    o = overfit_summary(deflated_sharpe(_winner(), _srs_var_quarter(), 900, 1.0),
                        probability_backtest_overfitting(rng.normal(0, 1, (24, 60))),
                        dsr_scope="dsr scope", pbo_scope="pbo scope")
    for k in ("dsr", "dsr_p", "n_trials", "sr_hat", "sr0", "sr_var", "skew", "kurt",
              "n_obs", "pbo", "pbo_n_configs", "pbo_n_splits", "pbo_n_blocks", "method",
              "notes", "v"):
        assert k in o
    assert o["pbo"] is not None and o["pbo_n_splits"] == 252
    assert len(json.dumps(o)) < 2048


def test_missing_inputs_give_null_with_reason():
    o = overfit_summary(None, None, pbo_reason="no trial matrix")
    assert o["dsr"] is None and o["pbo"] is None
    assert any("no trial matrix" in n for n in o["notes"])


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("AUGUR_OVERFIT_REPORT", "0")
    assert overfit_summary(None, None) is None


# ---- golden: a small synthetic validate is identical with the switch on / off ----
from test_wholerun_figures import _KWARGS, _strategy, _patched_data_layer  # noqa: F401,E402


def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k not in ("overfit", "timings")}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


def test_golden_validate_identical_switch_on_off(_patched_data_layer, monkeypatch):  # noqa: F811
    from augur_engine.validate import run_validate
    monkeypatch.setenv("AUGUR_OVERFIT_REPORT", "1")
    on = run_validate(_strategy(False), **_KWARGS)
    monkeypatch.setenv("AUGUR_OVERFIT_REPORT", "0")
    off = run_validate(_strategy(False), **_KWARGS)
    assert isinstance(on["validate"]["overfit"], dict)
    assert off["validate"]["overfit"] is None
    assert len(json.dumps(on["validate"]["overfit"])) < 2048
    a = json.dumps(_strip(on), sort_keys=True, default=str)
    b = json.dumps(_strip(off), sort_keys=True, default=str)
    assert a == b
