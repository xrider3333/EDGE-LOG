"""MISC_PAIRZ_1_0 (opus hunt strategy 76, cell 76c): defaults = the hunt cell, the plugin gate lets it through, and
(when the pinned panel and the hunt files are on this machine) the default trades match the harness's 76c trades on
2018. Everything runs on the panel CUT AT 2025-06-30 (tools/misc_pairz_parity.load_plugin_sealed)."""
import os
import sys

import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "augur_strategies", "MISC_PAIRZ_1_0.py")
HUNT_TRADES = r"C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S76/trades_76c.csv"
sys.path.insert(0, os.path.join(REPO, "tools"))

import misc_pairz_parity as P  # noqa: E402


def test_defaults_are_cell_76c():
    mod, _ = P.load_plugin_sealed()
    d = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}
    assert d == {"notional": 100000, "spread_cents": 1.0, "fee_bps": 0.3, "z_entry": 2.0, "exit_z": 0.0,
                 "sigma_len": 20, "max_cost_bp": 5.0, "flat_min": 60, "first_sig_offset": 0,
                 "high_corr_only": False}
    assert len(mod.PAIRS) == 39 and len(set(mod.PAIRS)) == 39
    assert len(mod.PAIRS_CORR80) == 20 and set(mod.PAIRS_CORR80) <= set(mod.PAIRS)
    for k, v in mod.DEFAULT_PARAMS.items():                     # every default sits inside its range
        if "min" in v:
            assert v["min"] <= v["default"] <= v["max"], k
    assert mod.PARAM_GRID_PRESETS["Short  (the hunt cell 76c)"] == {k: [v] for k, v in d.items()
                                                                    if k not in ("notional", "spread_cents", "fee_bps")}


def test_plugin_gate_lets_it_through():
    from augur_engine import plugin_gate as G
    with open(PLUGIN, "rb") as f:
        src = G.lf_bytes(f.read()).decode("utf-8")
    assert G.MARKER_RX.search(src).group(1) == "claude-review"
    assert G.lookahead_check(src) == []
    G.gate_plugin(PLUGIN)                                         # raises PluginGateError on a refusal


def test_2018_trades_match_harness_76c():
    mod, p = P.load_plugin_sealed()
    if p is None or not os.path.exists(HUNT_TRADES):
        pytest.skip("pinned panel or hunt trades not on this machine")
    T = P.plugin_trades(mod, p)
    T = T[(T.d >= 20180101) & (T.d <= 20181231)].sort_values(["d", "a", "b"]).reset_index(drop=True)
    H = pd.read_csv(HUNT_TRADES)
    H["d"] = pd.to_datetime(H.d).dt.strftime("%Y%m%d").astype("int64")
    H = H[(H.d >= 20180101) & (H.d <= 20181231)].sort_values(["d", "a", "b"]).reset_index(drop=True)
    assert len(T) == len(H) > 100
    assert (T[["d", "a", "b", "fill_min", "exit_idx"]].values == H[["d", "a", "b", "fill_min", "exit_idx"]].values).all()
    assert (T.net - H.net).abs().max() < 1e-6
