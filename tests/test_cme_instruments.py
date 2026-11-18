from augur_engine import instruments as I
from augur_engine.book import _MULT
from augur_engine.reconcile import MULT


def test_specs_match_contracts():
    assert I.SPECS["RTY"]["tick_usd"] == 5.0
    assert I.SPECS["YM"]["tick_usd"] == 5.0
    assert I.SPECS["ZN"]["tick_usd"] == 15.625
    assert abs(I.default_cost_pts("RTY") - 0.213) < 1e-9
    assert abs(I.default_cost_pts("YM") - 2.13) < 1e-9
    assert I.default_cost_pts("NQ") is None and I.default_cost_pts("ES") is None


def test_multipliers_agree():
    for r, s in I.SPECS.items():
        assert _MULT[r] == s["mult"] and MULT[r] == s["mult"]
