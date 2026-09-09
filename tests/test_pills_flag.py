"""Diagnostic 'pills' flag wiring (2026-09-09 audit).

WHY: an audit of run #335 (Auto-Validate) found every top-level pill key
(adversarial/conformal/causal/synthetic/lead_lag/acf/vif/feature_select/edge_sig/
tailfit/seasonality) null on the saved run doc, even though `validate.flags` carried
real adversarial/vif verdicts. The root cause turned out NOT to be a dropped-detail
bug: `run_validate()` (augur_engine/validate.py) has always computed this whole
bundle unconditionally and saved it nested under `validate.*` (confirmed against the
live run #335 doc — `validate.adversarial` carries drift_features, n_pre, n_lockbox,
model and auc=0.636 in full). The TOP-level keys are null for validate runs by
design (api/runner.py's own comment: "top-level on Auto-Optimize runs; Auto-Validate
keeps its own copies under validate") — grid/auto jobs are the ones gated by
`job.get("pills", False)` (default OFF) via `compute_pills` in augur_engine/auto.py.

What WAS a real gap, fixed here: validate.py's inline pill block had (a) no way to
turn itself off, and (b) ONE outer try/except around all eleven checks, so a single
failing pill silently suppressed every other pill for that run. It's been replaced
with a call into the shared `analytics.run_pills()` bundle (the same one Auto-Optimize
already used via `compute_pills`), which wraps each pill in its own try/except. Two
new keyword params on `run_validate()`: `compute_pills` (default True — preserves the
prior always-on behavior) and `compute_feature_select` (default True — a separate
switch for the single most expensive pill; see the timing note below).

Timing (2026-09-09, NQ 1m ETH-equivalent master, 2010-06-07..2026-06-30, ~1.585M bars,
measured directly against analytics.py's underlying functions, not mocked): the
whole-array pills (acf/tailfit/seasonality/vif incl. entry_features, adversarial,
lead_lag incl. loading the ES sibling master) totalled ~36s; the champion-trade pills
on ~2,000 synthetic trades added ~28s more, almost all of it ONE pill —
`gate_feature_select` (~27.6s, ~43% of the ~64s combined). That is the dominant cost
and the reason `compute_feature_select` exists as its own flag: a caller under load
(the runner already runs 5 concurrent jobs) can turn off just that one pill without
losing adversarial/conformal/causal/synthetic/edge_sig/acf/vif/tailfit/seasonality/
lead_lag. Everything else this file tests is behavior, not timing (real timing needs
real master data + a live champion, which the test suite intentionally does not load).
"""
import inspect
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.runner as R
import augur_engine.analytics as analytics
import augur_engine.ml_gate as ml_gate
from augur_engine.validate import run_validate


# ── 1. defaults on the public signatures ─────────────────────────────────────────

def test_run_validate_pills_default_on():
    params = inspect.signature(run_validate).parameters
    assert params["compute_pills"].default is True
    assert params["compute_feature_select"].default is True


def test_run_pills_feature_select_default_on():
    params = inspect.signature(analytics.run_pills).parameters
    assert params["include_feature_select"].default is True


# ── 2. runner.py -> run_validate wiring (api/runner.py process_job, jtype=='validate') ──
# Mocks augur_engine.run_validate (the `ae.run_validate` api/runner.py calls) so this
# never touches real master data; only the kwargs the runner threads through matter here.

def _validate_job(strategy="NONEXISTENT_PILLS_TEST_STRAT.py", **extra):
    job = {"type": "validate", "strategy": strategy, "instrument": "SYN",
           "timeframe": "5m", "session": "rth"}
    job.update(extra)
    return job


def _fake_run_validate_result():
    return {"mode": "validate",
            "validate": {"verdict": "PASS", "checks": {}, "n_pass": 0, "n_gates": 0},
            "best_params": {}, "best": {}, "top": []}


def test_runner_defaults_pills_on_for_validate_job(monkeypatch):
    captured = {}

    def fake_run_validate(strategy, **kw):
        captured.update(kw)
        return _fake_run_validate_result()

    monkeypatch.setattr(R.ae, "run_validate", fake_run_validate)
    out = R.process_job(_validate_job())
    assert out["status"] == "done"
    assert captured.get("compute_pills") is True
    assert captured.get("compute_feature_select") is True


def test_runner_honors_explicit_pills_off(monkeypatch):
    captured = {}

    def fake_run_validate(strategy, **kw):
        captured.update(kw)
        return _fake_run_validate_result()

    monkeypatch.setattr(R.ae, "run_validate", fake_run_validate)
    out = R.process_job(_validate_job(pills=False, pills_feature_select=False))
    assert out["status"] == "done"
    assert captured.get("compute_pills") is False
    assert captured.get("compute_feature_select") is False


# ── 3. one pill's exception never suppresses the others (analytics.run_pills) ────
# Small synthetic arrays -- big enough for seasonality's >=500-bar floor and for
# entry_features' rolling windows to produce non-degenerate output.

def _synthetic_arrays(n=600):
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="US/Eastern")
    rng = np.random.RandomState(0)
    close = 100.0 + np.cumsum(rng.normal(0, 0.1, n))
    high = close + np.abs(rng.normal(0, 0.05, n))
    low = close - np.abs(rng.normal(0, 0.05, n))
    day_id = pd.factorize(idx.date)[0].astype("int64")
    return {"open": close.copy(), "high": high, "low": low, "close": close,
            "volume": np.full(n, 1000.0), "day_id": day_id, "index": idx}


def test_run_pills_isolates_a_failing_pill(monkeypatch):
    arrays = _synthetic_arrays()

    def boom(*a, **kw):
        raise RuntimeError("synthetic pill failure")

    # tailfit is a whole-array pill with no dependency on any other pill's output --
    # breaking it must not take acf/vif/seasonality down with it.
    monkeypatch.setattr(analytics, "return_tailfit", boom)
    out = analytics.run_pills(arrays, instrument="SYN", timeframe="1m", session="rth")
    assert "tailfit" not in out           # the broken pill is simply absent
    assert "acf" in out and out["acf"] is not None
    assert "seasonality" in out and out["seasonality"] is not None
    assert "vif" in out and out["vif"] is not None


def test_run_pills_include_feature_select_false_skips_it(monkeypatch):
    arrays = _synthetic_arrays()
    calls = {"n": 0}

    def spy(*a, **kw):
        calls["n"] += 1
        return {"kept": [], "dropped": []}

    monkeypatch.setattr(ml_gate, "gate_feature_select", spy)
    trades = [(i, i + 1, 1.0) for i in range(50)]
    out_on = analytics.run_pills(arrays, champ_trades=trades, instrument="SYN",
                                  timeframe="1m", session="rth", include_feature_select=True)
    out_off = analytics.run_pills(arrays, champ_trades=trades, instrument="SYN",
                                   timeframe="1m", session="rth", include_feature_select=False)
    assert "feature_select" in out_on
    assert "feature_select" not in out_off
    assert calls["n"] == 1   # only the include=True call reached gate_feature_select


# ── 4. shrink_to_fit's oversized-doc trim path fires ─────────────────────────────

def test_shrink_to_fit_trims_an_oversized_unprotected_field():
    big = {"junk_field": ["x" * 500] * 5000,   # not in _PROTECTED_KEY_HINTS
           "best": {"total_pnl": 123.0}}        # protected -- must survive
    logs = []
    out = R.shrink_to_fit(dict(big), budget=50_000, log=lambda m: logs.append(m),
                           label="test-doc")
    assert R._doc_size(out) <= 50_000 or out.get("fields_dropped")
    assert out["best"] == {"total_pnl": 123.0}          # protected field untouched
    assert ("junk_field" not in out) or (out.get("population_truncated") is True)
    assert any("size-guard" in m for m in logs)
