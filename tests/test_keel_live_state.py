"""tests/test_keel_live_state.py -- tools/keel_live_state.py, the nightly KEEL v12
state builder for the NOISE_382 leg (OWNER DECISION 2026-09-23, design doc D).

Runs entirely on small synthetic data -- no dependency on the real NQ master (not
present in a worktree, see BACKTEST_SPEED.md rule 3) or on serviceAccount.json. The
real 4,825-trade #382 walk itself was verified out of band (too slow -- ~4-5 minutes --
to run on every push); see this task's delivered report for those numbers (exact
reproduction of the stored run #382 gate_validate.keel row: n_trades and
size-weighted total_pnl both matched to the reported precision).
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.keel_live_state as kls          # noqa: E402
import api.cloud_signal as cs                 # noqa: E402


# ── the one place these facts are duplicated must never drift ────────────────────────────
def test_strategy_facts_match_cloud_signals_own_crown_leg():
    leg = cs.CROWN_LEGS["NOISE_382"]
    assert kls.STRATEGY_FILE == leg["strategy"]
    assert kls.STRATEGY_PARAMS == leg["params"]
    assert kls.LEG_KEY == "NOISE_382"
    assert leg["keel"]["version"] == kls.VERSION


# ── a small, real, NQ-master-shaped CSV to drive load_nq_arrays/build on ─────────────────
def _write_master_csv(path, n_full_days, last_day_bars=None, bars_per_day=kls.FULL_SESSION_BARS,
                      start="2024-01-02", seed=1):
    """Epoch-schema RTH bars (time,open,high,low,close,volume,source) shaped like
    augur_uploads/NOADJ_NQ_5m_RTH.csv -- `n_full_days` complete sessions of
    `bars_per_day` bars, optionally followed by one more day of only `last_day_bars`
    bars (an in-progress session, the case load_nq_arrays must drop)."""
    rng = np.random.RandomState(seed)
    rows = []
    price = 15000.0
    day = pd.Timestamp(start, tz="US/Eastern")
    n_days = n_full_days + (1 if last_day_bars is not None else 0)
    for d in range(n_days):
        while day.dayofweek > 4:
            day = day + pd.Timedelta(days=1)
        n_bars_today = bars_per_day if d < n_full_days else last_day_bars
        day_start = day.replace(hour=9, minute=30)
        for b in range(n_bars_today):
            ts = day_start + pd.Timedelta(minutes=5 * b)
            price += rng.normal(0, 3.0)
            rows.append({"time": int(ts.tz_convert("UTC").timestamp()),
                        "open": price, "high": price + 2, "low": price - 2,
                        "close": price + rng.normal(0, 1), "volume": 1000.0, "source": "test"})
        day = day + pd.Timedelta(days=1)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return path


# ── drop-incomplete-session ───────────────────────────────────────────────────────────────
def test_drops_an_incomplete_final_session(tmp_path):
    path = _write_master_csv(tmp_path / "nq.csv", n_full_days=5, last_day_bars=34)
    arr, dropped = kls.load_nq_arrays(str(path), date_from=None)
    assert dropped is not None
    day_id = arr["day_id"]
    # every remaining session has the FULL bar count -- the partial one is gone.
    counts = pd.Series(day_id).value_counts()
    assert (counts == kls.FULL_SESSION_BARS).all()
    assert len(np.unique(day_id)) == 5


def test_keeps_a_complete_final_session(tmp_path):
    path = _write_master_csv(tmp_path / "nq.csv", n_full_days=5, last_day_bars=None)
    arr, dropped = kls.load_nq_arrays(str(path), date_from=None)
    assert dropped is None
    assert len(np.unique(arr["day_id"])) == 5


def test_drop_incomplete_session_survives_extra_non_array_keys_from_load_master_arrays(tmp_path, monkeypatch):
    """REGRESSION: augur_engine.data.load_master_arrays also returns "meta" (dict) and
    "fingerprint" (str) alongside the per-bar arrays -- neither is indexable by a
    per-bar boolean mask. The first version of load_nq_arrays only excluded "meta" and
    crashed on "fingerprint" the first time it ran against the real master (see this
    task's delivered report). Reproduced here with a stub loader so it never depends
    on which extra keys the real function happens to return today."""
    import augur_engine.data as _data

    def fake_load_master_arrays(master, date_from=None, date_to=None):
        n = 2 * kls.FULL_SESSION_BARS + 10   # 2 full days + a partial 3rd
        day_id = np.array([0] * kls.FULL_SESSION_BARS + [1] * kls.FULL_SESSION_BARS + [2] * 10,
                          dtype="int64")
        idx = pd.date_range("2024-01-02 09:30", periods=n, freq="5min", tz="US/Eastern")
        c = np.linspace(100, 110, n)
        return {"open": c, "high": c + 1, "low": c - 1, "close": c,
               "volume": np.full(n, 1.0), "day_id": day_id, "index": idx,
               "meta": {"whatever": 1}, "fingerprint": "deadbeef"}

    monkeypatch.setattr(_data, "load_master_arrays", fake_load_master_arrays)
    arr, dropped = kls.load_nq_arrays(str(tmp_path / "unused.csv"))
    assert dropped is not None
    assert len(np.unique(arr["day_id"])) == 2
    assert arr["meta"] == {"whatever": 1}
    assert arr["fingerprint"] == "deadbeef"


# ── end-to-end build() on a tiny synthetic master ────────────────────────────────────────
def test_build_writes_a_loadable_state_and_a_json_safe_summary(tmp_path):
    path = _write_master_csv(tmp_path / "nq.csv", n_full_days=90, seed=4)
    out_dir = tmp_path / "out"
    state, summary = kls.build(str(path), str(out_dir), version="v12", log=lambda *a, **k: None)

    state_path = out_dir / "NOISE_382_v12_state.joblib"
    summary_path = out_dir / "NOISE_382_v12_summary.json"
    # atomic swap (2026-09-24): both files land by rename -- nothing half-written is left behind
    assert not [p for p in out_dir.iterdir() if p.name.endswith(".tmp")]
    assert state_path.exists() and summary_path.exists()

    import joblib
    reloaded = joblib.load(str(state_path))
    assert reloaded["version"] == "v12"
    assert reloaded["n"] == state["n"]

    with open(summary_path, encoding="utf-8") as f:
        disk_summary = json.load(f)
    assert disk_summary["leg"] == "NOISE_382"
    assert disk_summary["strategy"] == kls.STRATEGY_FILE
    assert disk_summary["nq_file_sha256"] and len(disk_summary["nq_file_sha256"]) == 64
    assert disk_summary["build_seconds"] >= 0
    assert "timings_seconds" in disk_summary
    # JSON round-trips without needing default=str a second time -- proves every value
    # keel_state_summary hands back is already a plain type.
    json.dumps(summary)


def test_default_paths_are_portable_and_do_not_touch_the_shared_or_live_home(tmp_path, monkeypatch):
    """_default_out_dir must honour EDGELOG_HOME (never hardcode C:\\EdgeLog) so a test
    or an isolated run can redirect it -- see the live-system guard in tests/conftest.py,
    which would fail this whole file if _default_out_dir ever silently pointed at the
    real EDGELOG_HOME instead of what the caller configured."""
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "fake_home"))
    out = kls._default_out_dir()
    assert out == os.path.join(str(tmp_path / "fake_home"), "cloud_signal", "keel")


def test_check_against_run_doc_skips_cleanly_without_credentials(tmp_path, monkeypatch):
    """No serviceAccount.json (the normal state for a worktree, and possibly for the
    nightly Linux box too) -> a clean, logged skip, never an exception -- whichever of
    the two guards (firebase_admin missing, or just the credential file missing) fires
    first in this environment."""
    monkeypatch.setattr(kls, "ROOT", str(tmp_path))   # a directory with no serviceAccount.json
    logged = []
    result = kls.check_against_run_doc(run_id=382, log=logged.append)
    assert result is None
    assert logged and "skipping run-doc check" in logged[-1]
