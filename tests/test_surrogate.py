"""Unit tests for the multi-surrogate bake-off READ-OUT (#31 P1) —
augur_engine.surrogate.surrogate_bakeoff + its opt-in run_auto integration.

All synthetic — deterministic points/strategies, no real data files, so the
suite runs anywhere in well under a minute. See docs/SURROGATE_DISCOVERY_DESIGN.md
for the design this implements (§2 steps 2-4+6, §3 bake-off, §4 cards).
"""
import types

import numpy as np
import pytest

import augur_engine.surrogate as S
from augur_engine.auto import run_auto
from augur_engine.surrogate import surrogate_bakeoff

SEED = 42
N = 90


def _dp_2num():
    return {
        "a": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
        "b": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
        "c": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
    }


def _grid_points(fn, dp, n=N, seed=SEED, noise=0.0):
    """N deterministic points sampled uniformly over each numeric param's declared
    [min,max] step-grid, PnL = fn(row) (+ optional deterministic-seeded noise)."""
    rng = np.random.RandomState(seed)
    keys = list(dp.keys())
    axes = {}
    for k, meta in dp.items():
        lo, hi, step = meta["min"], meta["max"], meta["step"]
        axes[k] = np.arange(lo, hi + step / 2, step)
    pts = []
    for _ in range(n):
        row = {k: float(rng.choice(axes[k])) for k in keys}
        pnl = fn(row)
        if noise:
            pnl += rng.normal(0, noise)
        pts.append(dict(row, pnl=round(float(pnl), 2), dd=round(abs(pnl) * 0.2, 2)))
    return pts, keys


# ─────────────────────────────────────────────────────────────────────────────
# (a) known STRONG interaction beats an additive-only surface
# ─────────────────────────────────────────────────────────────────────────────
def test_strong_interaction_beats_additive_only():
    # Domain CENTERED at 0 (not [0,10]) so a*b is a PURE interaction term with no
    # linear component (E[a]=E[b]=0 -> the 1-D marginals of a*b are flat) -- this
    # isolates the interaction statistic from main-effect magnitude, which would
    # otherwise dominate the H-stat's denominator on an off-center domain (e.g.
    # [0,10]: a*b there decomposes into large linear terms + a smaller residual).
    dp = {
        "a": {"type": "float", "min": -5.0, "max": 5.0, "step": 0.5, "default": 0.0},
        "b": {"type": "float", "min": -5.0, "max": 5.0, "step": 0.5, "default": 0.0},
        "c": {"type": "float", "min": -5.0, "max": 5.0, "step": 0.5, "default": 0.0},
    }

    # Multiplicative surface: pnl = a*b (pure interaction) + c (additive, no interaction).
    pts_mult, keys = _grid_points(lambda r: r["a"] * r["b"] * 10.0 + r["c"] * 3.0, dp)
    out_mult = surrogate_bakeoff(pts_mult, keys, dp, seed=SEED)
    assert out_mult is not None
    best_mult = next(c for c in out_mult["models"] if c["model"] == out_mult["best_model"])
    top_pair = best_mult["top_interactions"][0]
    assert {top_pair["param_a"], top_pair["param_b"]} == {"a", "b"}
    strength_mult = top_pair["strength"]

    # Purely additive surface over the SAME (a,b) pair: no interaction at all.
    pts_add, _ = _grid_points(lambda r: r["a"] * 10.0 + r["b"] * 10.0 + r["c"] * 3.0, dp)
    out_add = surrogate_bakeoff(pts_add, keys, dp, seed=SEED)
    assert out_add is not None
    best_add = next(c for c in out_add["models"] if c["model"] == out_add["best_model"])
    ab_add = next((p for p in best_add["top_interactions"]
                  if {p["param_a"], p["param_b"]} == {"a", "b"}), None)
    strength_add = ab_add["strength"] if ab_add else 0.0

    assert strength_mult > strength_add
    assert strength_mult > 0.6          # a real, dominant interaction on the centered domain
    assert strength_add < 0.15          # additive surface: near-zero residual


# ─────────────────────────────────────────────────────────────────────────────
# (b) LASSO screen: live knob >> noise knob, noise knob verdicts 'dead'
# ─────────────────────────────────────────────────────────────────────────────
def test_lasso_screen_ranks_live_knob_over_dead_noise_knob():
    dp = {
        "live": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.25, "default": 5.0},
        "noise": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.25, "default": 5.0},
    }
    rng = np.random.RandomState(SEED)
    axes = {k: np.arange(m["min"], m["max"] + m["step"] / 2, m["step"]) for k, m in dp.items()}
    pts = []
    for _ in range(N):
        live = float(rng.choice(axes["live"]))
        noise = float(rng.choice(axes["noise"]))
        pnl = live * 50.0            # PURE linear in `live`; `noise` never enters the formula
        pts.append({"live": live, "noise": noise, "pnl": round(pnl, 2)})
    keys = ["live", "noise"]

    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    ks = out["knob_screen"]
    assert ks["live"]["lasso"] is not None and ks["noise"]["lasso"] is not None
    assert ks["live"]["lasso"] > ks["noise"]["lasso"] * 5   # live >> noise, not just slightly bigger
    assert ks["noise"]["verdict"] == "dead"
    assert ks["live"]["verdict"] == "drives PnL"


# ─────────────────────────────────────────────────────────────────────────────
# (#39) permutation-importance vote + random-noise-probe upgrade
# ─────────────────────────────────────────────────────────────────────────────
def _live_vs_noise_points():
    """Same construction as the LASSO test above (one PURE-linear knob, one knob
    that never enters the PnL formula at all) -- reused for the probe tests
    since it's the cleanest ground truth for "this knob really is noise"."""
    dp = {
        "live": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.25, "default": 5.0},
        "noise": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.25, "default": 5.0},
    }
    rng = np.random.RandomState(SEED)
    axes = {k: np.arange(m["min"], m["max"] + m["step"] / 2, m["step"]) for k, m in dp.items()}
    pts = []
    for _ in range(N):
        live = float(rng.choice(axes["live"]))
        noise = float(rng.choice(axes["noise"]))
        pts.append({"live": live, "noise": noise, "pnl": round(live * 50.0, 2)})
    return pts, ["live", "noise"], dp


def test_a_pure_noise_knob_scores_at_or_below_the_probe_and_verdicts_dead():
    pts, keys, dp = _live_vs_noise_points()
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    noise = out["knob_screen"]["noise"]
    assert noise["perm"] is not None
    assert noise["probe_margin"] is not None
    assert noise["probe_margin"] <= 0.05             # at/below the probe (small numerical slack, not a hard 0)
    assert noise["verdict"] == "dead"
    assert "noise probe" in noise["verdict_note"]


def test_b_a_strong_knob_scores_clearly_above_the_probe_and_keeps_drives_pnl():
    pts, keys, dp = _live_vs_noise_points()
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    live = out["knob_screen"]["live"]
    noise = out["knob_screen"]["noise"]
    assert live["perm"] is not None and live["perm"] > 0
    assert live["probe_margin"] is not None
    assert live["probe_margin"] > 0.5                # clearly, not marginally, above the probe
    assert live["probe_margin"] > noise["probe_margin"]
    assert live["verdict"] == "drives PnL"
    assert "above noise probe" in live["verdict_note"]


def test_c_probe_and_perm_fields_are_deterministic():
    pts, keys, dp = _make_bakeoff_points()
    out1 = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    out2 = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out1["knob_screen"] == out2["knob_screen"]
    assert out1["knob_screen_probe"] == out2["knob_screen_probe"]
    assert out1 == out2                              # whole-payload determinism, unchanged contract


def test_d_backward_compat_knob_screen_keys_and_legal_verdict_strings():
    pts, keys, dp = _make_bakeoff_points()
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    for k in keys:
        entry = out["knob_screen"][k]
        # the v58.7 web panel reads exactly these three keys -- must still be there,
        # and `verdict` must be EXACTLY one of the three strings the panel chip-colors
        # on (index.html surrogatePanelHtml's chip() does an EXACT match, not a prefix
        # test -- checked directly -- so the probe's explanation lives in the new
        # `verdict_note` field instead of a 4th verdict string).
        assert {"lasso", "shap_or_imp", "verdict"} <= set(entry)
        assert entry["verdict"] in ("drives PnL", "weak", "dead")
        # additive-only new fields
        assert "perm" in entry and "probe_margin" in entry and "verdict_note" in entry
    # the probe summary is a SIBLING top-level key, never nested inside knob_screen
    # (nesting it there would make index.html's per-key chip loop render a bogus chip)
    assert "knob_screen_probe" in out
    assert "knob_screen_probe" not in out["knob_screen"]
    probe = out["knob_screen_probe"]
    assert {"lasso", "shap_or_imp", "perm", "source_model", "note"} <= set(probe)


def test_e_probe_never_leaks_into_predicted_best_params_interactions_or_cards():
    pts, keys, dp = _make_bakeoff_points()
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    for c in out["models"]:
        if c.get("skipped"):
            continue
        # predicted_best_params has exactly the real knobs -- no extra probe column
        assert set(c["predicted_best_params"]) == set(keys)
        for it in c.get("top_interactions", []):
            assert it["param_a"] in keys and it["param_b"] in keys
        assert not any("probe" in str(kk).lower() for kk in c)
    assert set(out["knob_screen"]) == set(keys)      # no bogus "_probe" entry among the per-knob chips
    assert not any("probe" in str(kk).lower() for kk in out["knob_screen"])


# ─────────────────────────────────────────────────────────────────────────────
# (c) cards well-formed for every available model; xgboost/shap absence degrades
# ─────────────────────────────────────────────────────────────────────────────
def _make_bakeoff_points():
    dp = _dp_2num()
    pts, keys = _grid_points(lambda r: r["a"] * r["b"] * 4.0 - (r["a"] - 5) ** 2 * 2 + r["c"], dp)
    return pts, keys, dp


def test_cards_well_formed_when_everything_available():
    pts, keys, dp = _make_bakeoff_points()
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    names = {c["model"] for c in out["models"]}
    assert names == {"quadratic", "random_forest", "xgboost", "gp", "gam"}
    for c in out["models"]:
        if c.get("skipped"):
            continue
        assert isinstance(c["cv_r2"], float)
        assert isinstance(c["cv_rmse"], float)
        assert isinstance(c["best_hyperparams"], dict) and c["best_hyperparams"]
        assert "predicted_best_params" in c and set(c["predicted_best_params"]) == set(keys)
        assert isinstance(c["predicted_best_pnl"], float)
        assert "top_interactions" in c
    assert out["best_model"] in names
    assert set(out["knob_screen"]) == set(keys)


def test_xgboost_and_shap_absence_degrade_gracefully(monkeypatch):
    pts, keys, dp = _make_bakeoff_points()
    monkeypatch.setattr(S, "HAS_XGBOOST", False)
    monkeypatch.setattr(S, "HAS_SHAP", False)
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    xgb_card = next(c for c in out["models"] if c["model"] == "xgboost")
    assert xgb_card.get("skipped") == "xgboost not installed"
    # every other model still fits fine (gam unaffected -- only xgboost/shap disabled here)
    fit_names = {c["model"] for c in out["models"] if "cv_r2" in c}
    expected = {"quadratic", "random_forest", "gp"} | ({"gam"} if S.HAS_PYGAM else set())
    assert fit_names == expected
    # knob screen falls back to RF impurity importances, never crashes, never
    # silently claims a `shap:` source it didn't actually compute
    for k in keys:
        src = out["knob_screen"][k]["shap_source"]
        assert src is None or src.startswith("rf_importance:")


# ─────────────────────────────────────────────────────────────────────────────
# (#35) pyGAM adapter — 5th roster entry; finite CV-R2 card when installed,
# graceful skip (never an exception, bake-off still returns) when it isn't.
# ─────────────────────────────────────────────────────────────────────────────
def test_gam_card_appears_with_finite_cv_r2_when_pygam_installed():
    pytest.importorskip("pygam")
    pts, keys, dp = _make_bakeoff_points()
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    gam_card = next(c for c in out["models"] if c["model"] == "gam")
    assert not gam_card.get("skipped")
    assert isinstance(gam_card["cv_r2"], float) and np.isfinite(gam_card["cv_r2"])
    assert isinstance(gam_card["cv_rmse"], float) and np.isfinite(gam_card["cv_rmse"])
    assert isinstance(gam_card["best_hyperparams"], dict) and gam_card["best_hyperparams"]
    assert "predicted_best_params" in gam_card and set(gam_card["predicted_best_params"]) == set(keys)
    assert isinstance(gam_card["predicted_best_pnl"], float)
    assert "top_interactions" in gam_card       # generic PD-based path, same as every other model


def test_bakeoff_still_picks_a_best_model_when_pygam_absent(monkeypatch):
    """Simulates pygam-not-installed by monkeypatching the module's own HAS_PYGAM
    flag (same pattern the file already uses for HAS_XGBOOST/HAS_SHAP above) --
    the bake-off must degrade the `gam` card to `skipped` and keep going,
    never raise, and still pick a best model from whatever else fit."""
    pts, keys, dp = _make_bakeoff_points()
    monkeypatch.setattr(S, "HAS_PYGAM", False)
    out = surrogate_bakeoff(pts, keys, dp, seed=SEED)
    assert out is not None
    gam_card = next(c for c in out["models"] if c["model"] == "gam")
    assert gam_card.get("skipped") == "pygam not installed"
    fit_names = {c["model"] for c in out["models"] if "cv_r2" in c}
    assert fit_names == {"quadratic", "random_forest", "xgboost", "gp"}
    assert out["best_model"] in fit_names


# ─────────────────────────────────────────────────────────────────────────────
# (d) ground_truth_fn called once per UNIQUE proposal; result lands in the card
# ─────────────────────────────────────────────────────────────────────────────
def test_ground_truth_fn_called_per_unique_proposal_and_recorded():
    pts, keys, dp = _make_bakeoff_points()
    calls = []

    def _true_pnl(params):
        return params["a"] * params["b"] * 4.0 - (params["a"] - 5) ** 2 * 2 + params["c"]

    def gt_fn(params):
        calls.append(tuple(sorted(params.items())))          # instrumentation ONLY
        return {"total_pnl": _true_pnl(params)}

    out = surrogate_bakeoff(pts, keys, dp, ground_truth_fn=gt_fn, seed=SEED)
    assert out is not None
    fit_cards = [c for c in out["models"] if "cv_r2" in c]
    assert fit_cards       # at least one model fit
    for c in fit_cards:
        assert c["ground_truth_pnl"] is not None
        expected = _true_pnl(c["predicted_best_params"])      # NOT gt_fn -- keep `calls` clean
        assert c["ground_truth_pnl"] == pytest.approx(round(expected, 1), abs=0.15)
        assert "beat_sampled_best" in c

    # dedup: ground_truth_fn called exactly once per DISTINCT proposal, not once per model
    unique_proposals = {tuple(sorted(c["predicted_best_params"].items())) for c in fit_cards}
    assert len(calls) == len(unique_proposals)
    assert "sampled_best_pnl" in out


# ─────────────────────────────────────────────────────────────────────────────
# (e) determinism: two identical calls -> byte-identical output
# ─────────────────────────────────────────────────────────────────────────────
def test_determinism_two_identical_calls_match():
    pts, keys, dp = _make_bakeoff_points()

    def gt_fn(params):
        return {"total_pnl": params["a"] * params["b"] * 4.0 - (params["a"] - 5) ** 2 * 2 + params["c"]}

    out1 = surrogate_bakeoff(pts, keys, dp, ground_truth_fn=gt_fn, seed=SEED)
    out2 = surrogate_bakeoff(pts, keys, dp, ground_truth_fn=gt_fn, seed=SEED)
    assert out1 == out2


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail: too few points / too few varying params -> None
# ─────────────────────────────────────────────────────────────────────────────
def test_none_when_too_few_points():
    dp = _dp_2num()
    pts, keys = _grid_points(lambda r: r["a"] * r["b"], dp, n=20)
    assert surrogate_bakeoff(pts, keys, dp, seed=SEED) is None


def test_none_when_fewer_than_two_varying_params():
    dp = {"a": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0}}
    pts = [{"a": round(i * 0.1, 2), "pnl": i * 1.0} for i in range(N)]
    assert surrogate_bakeoff(pts, ["a"], dp, seed=SEED) is None


# ─────────────────────────────────────────────────────────────────────────────
# (f) run_auto integration: compute_surrogate=True attaches out['surrogate'];
#     default/False leaves output byte-identical to before.
# ─────────────────────────────────────────────────────────────────────────────
def _make_two_knob_strategy():
    """Two independent numeric knobs with a real (non-degenerate) joint PnL
    surface, plenty of resolution -> comfortably clears MIN_POINTS/varying-param
    guardrails from a modest n_trials."""
    mod = types.ModuleType("fake_surrogate_strategy")
    mod.STRATEGY_NAME = "SYNTHETIC (surrogate test only)"
    mod.DEFAULT_PARAMS = {
        "knob_a": {"type": "float", "min": 0.0, "max": 20.0, "step": 1.0, "default": 10.0},
        "knob_b": {"type": "float", "min": 0.0, "max": 20.0, "step": 1.0, "default": 10.0},
    }

    def run_backtest(opens, highs, lows, closes, knob_a=None, knob_b=None,
                     return_trades=False, **_ignore):
        pnl = float(knob_a) * float(knob_b) - (float(knob_a) - 10.0) ** 2 * 2.0
        out = {"total_pnl": pnl, "num_trades": 50, "win_rate": 60.0, "profit_factor": 1.5,
               "max_drawdown": -100.0, "avg_pnl": pnl / 50.0, "wins": 30, "losses": 20}
        if return_trades:
            out["trades"] = []
        return out

    mod.run_backtest = run_backtest
    return mod


def _make_arrays(n=60):
    return {"open": np.full(n, 100.0), "high": np.full(n, 101.0), "low": np.full(n, 99.0),
           "close": np.full(n, 100.0), "volume": np.full(n, 1000.0),
           "day_id": (np.arange(n) // 6).astype("int64"), "index": None,
           "meta": {"name": "SYN"}}


def test_run_auto_compute_surrogate_true_attaches_surrogate():
    mod = _make_two_knob_strategy()
    out = run_auto(mod, arrays=_make_arrays(), oos=False, method="single",
                   n_trials=90, min_trades=1, seed=SEED, auto_expand=False,
                   compute_surrogate=True)
    assert "surrogate" in out
    surr = out["surrogate"]
    assert "error" not in surr
    assert surr["best_model"] in {c["model"] for c in surr["models"]}
    assert set(surr["knob_screen"]) == {"knob_a", "knob_b"}


def test_run_auto_compute_surrogate_default_false_is_byte_identical():
    mod = _make_two_knob_strategy()
    kwargs = dict(arrays=_make_arrays(), oos=False, method="single",
                  n_trials=90, min_trades=1, seed=SEED, auto_expand=False)
    out_default = run_auto(mod, **kwargs)
    out_explicit_false = run_auto(mod, compute_surrogate=False, **kwargs)
    assert "surrogate" not in out_default
    assert "surrogate" not in out_explicit_false
    assert out_default == out_explicit_false
