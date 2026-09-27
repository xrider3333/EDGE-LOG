"""tests/test_keel_live_state.py -- tools/keel_live_state.py, the nightly KEEL v12
state builder for the live KEEL leg (OWNER DECISION 2026-09-23, design doc D) -- NOISE_382
until the 2026-09-27 swap, NOISE_422 after it, read from api/cloud_signal.CROWN_LEGS.

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


def _learned_crown_legs():
    """CROWN_LEGS with NOISE_422 on the LEARNED go-day line, whichever of the three lines
    (api/cloud_signal.py's THREE SHAPES) is live in the file. The build tests here are about
    the learned build itself; which line is live is tests/test_noise_422_switch.py's to
    check, so these must not go red when MANAGER picks the fixed or the no-KEEL line."""
    return dict(cs.CROWN_LEGS, NOISE_422=dict(
        cs.CROWN_LEGS["NOISE_422"], keel=dict(version="v12", **cs.keel_paths("NOISE_422", "v12"))))


@pytest.fixture(autouse=True)
def _learned_live_leg(monkeypatch):
    """Every test here runs on the learned line (see _learned_crown_legs); a test that
    wants another CROWN_LEGS patches its own on top."""
    monkeypatch.setattr(cs, "CROWN_LEGS", _learned_crown_legs())


# ── the leg comes from CROWN_LEGS itself -- nothing duplicated here to drift ─────────────
def test_default_leg_is_the_one_crown_leg_with_a_keel_block():
    leg = kls.resolve_leg()
    assert leg["leg_key"] == "NOISE_422"
    cfg = cs.CROWN_LEGS["NOISE_422"]
    assert leg["strategy"] == cfg["strategy"] == "NOISE_1_8_CT304H.py"
    assert leg["params"] == cfg["params"]
    assert leg["version"] == cfg["keel"]["version"] == kls.VERSION
    assert leg["live"] is True


def test_resolve_leg_refuses_zero_or_several_keel_legs():
    """No guess: with KEEL taken off every leg, or on two legs at once, the nightly
    default must fail loudly (main() turns this into a SystemExit) rather than build
    one arbitrarily or nothing silently."""
    plain = {"ORB_R6": {"strategy": "ORB_3_6_R6.py", "params": {}}}
    with pytest.raises(kls.LegResolutionError, match="found 0"):
        kls.resolve_leg(crown_legs=plain)
    two = {"A": {"strategy": "a.py", "keel": {"version": "v12"}},
           "B": {"strategy": "b.py", "keel": {"version": "v12"}}}
    with pytest.raises(kls.LegResolutionError, match="found 2"):
        kls.resolve_leg(crown_legs=two)
    # an explicit leg that carries no KEEL block is refused too -- this script builds
    # KEEL states and nothing else
    with pytest.raises(kls.LegResolutionError, match="no \"keel\" block"):
        kls.resolve_leg("ORB_R6")
    with pytest.raises(kls.LegResolutionError, match="unknown leg"):
        kls.resolve_leg("NOT_A_LEG")


def test_retired_noise_382_leg_stays_resolvable_by_hand():
    """--leg NOISE_382 keeps working after the swap (rebuild or --check-run-doc against
    run #382's own stored KEEL row), from run #382's own cell -- not the live leg's."""
    assert "NOISE_382" not in cs.CROWN_LEGS
    leg = kls.resolve_leg("NOISE_382")
    assert leg == {"leg_key": "NOISE_382", "strategy": "NOISE_1_8_CT304.py",
                   "params": cs.NOISE_382_PARAMS, "version": "v12", "live": False}
    assert kls.RUN_ID_FOR_LEG["NOISE_382"] == 382


def test_main_fails_loudly_when_no_leg_carries_keel(tmp_path, monkeypatch):
    """The no-KEEL alternative (the "keel" key deleted from CROWN_LEGS["NOISE_422"]): the
    nightly unit's own invocation must exit non-zero with the reason, writing nothing."""
    no_keel = {k: {kk: vv for kk, vv in v.items() if kk != "keel"}
               for k, v in cs.CROWN_LEGS.items()}
    monkeypatch.setattr(cs, "CROWN_LEGS", no_keel)
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=3)
    old_argv = sys.argv
    sys.argv = ["keel_live_state.py", "--nq-file", str(nq), "--out-dir", str(tmp_path / "out")]
    try:
        with pytest.raises(SystemExit) as ei:
            kls.main()
    finally:
        sys.argv = old_argv
    assert "found 0" in str(ei.value.code)
    assert not (tmp_path / "out").exists()


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

    # the live KEEL leg's own names -- exactly what cloud_signal.keel_paths reads
    state_path = out_dir / "NOISE_422_v12_state.joblib"
    summary_path = out_dir / "NOISE_422_v12_summary.json"
    assert os.path.basename(cs.CROWN_LEGS["NOISE_422"]["keel"]["state_path"]) == state_path.name
    assert os.path.basename(cs.CROWN_LEGS["NOISE_422"]["keel"]["summary_path"]) == summary_path.name
    # atomic swap (2026-09-24): both files land by rename -- nothing half-written is left behind
    assert not [p for p in out_dir.iterdir() if p.name.endswith(".tmp")]
    assert state_path.exists() and summary_path.exists()

    import joblib
    reloaded = joblib.load(str(state_path))
    assert reloaded["version"] == "v12"
    assert reloaded["n"] == state["n"]

    with open(summary_path, encoding="utf-8") as f:
        disk_summary = json.load(f)
    assert disk_summary["leg"] == "NOISE_422"
    assert disk_summary["leg_live"] is True
    assert disk_summary["strategy"] == "NOISE_1_8_CT304H.py"
    assert disk_summary["params"] == cs.NOISE_422_PARAMS
    assert disk_summary["cost_pts"] == 0.533 and disk_summary["date_from"] == "2010-06-07"
    assert disk_summary["nq_file_sha256"] and len(disk_summary["nq_file_sha256"]) == 64
    assert disk_summary["build_seconds"] >= 0
    assert "timings_seconds" in disk_summary
    # JSON round-trips without needing default=str a second time -- proves every value
    # keel_state_summary hands back is already a plain type.
    json.dumps(summary)

    # item D (2026-09-25): "data_through" is the last BAR used (post-drop), independent
    # of whether any trade landed on it -- this file has no incomplete final session,
    # so it should equal the last day load_nq_arrays itself returns.
    arr_check, dropped_check = kls.load_nq_arrays(str(path), date_from=None)
    assert dropped_check is None
    expected_data_through = str(pd.DatetimeIndex(arr_check["index"])[-1].date())
    assert disk_summary["data_through"] == expected_data_through


# ── item D (2026-09-25): "trained through" means the data, not the last trade ────────────
def test_data_through_is_the_last_bar_even_with_no_recent_trade(tmp_path, monkeypatch):
    """The exact bug this item fixes: on several quiet closing sessions with no NQ
    #382 trade at all, ml_keel.py's own 'last_nq_session' (the last TRADE's date)
    stays behind, but 'data_through' (the last BAR actually used) must still reflect
    the newest complete session."""
    path = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=7)
    out_dir = tmp_path / "out"

    # Force every trade's bar indices into the FIRST of the 10 sessions -- simulates
    # nine quiet closing sessions in a row with no NQ trade whatsoever.
    early_trades = [(5, 8, 12.5), (20, 25, -4.0), (40, 44, 6.25)]
    monkeypatch.setattr(kls, "run_nq_backtest",
                        lambda arr, leg=None, log=print: (list(early_trades), {"total_pnl": 14.75}))

    state, summary = kls.build(str(path), str(out_dir), version="v12", log=lambda *a, **k: None)

    arr_check, dropped_check = kls.load_nq_arrays(str(path), date_from=None)
    assert dropped_check is None
    expected_data_through = str(pd.DatetimeIndex(arr_check["index"])[-1].date())

    assert summary["data_through"] == expected_data_through
    assert summary["last_nq_session"] is not None
    assert summary["last_nq_session"] != summary["data_through"]
    # the last trade's session must be EARLIER than the data's own last session --
    # string YYYY-MM-DD dates compare lexicographically the same as chronologically.
    assert summary["last_nq_session"] < summary["data_through"]


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


# ── --leg: a retired leg builds under its OWN names, never the live leg's ────────────────
def test_build_for_the_retired_noise_382_leg_writes_its_own_files(tmp_path, monkeypatch):
    path = _write_master_csv(tmp_path / "nq.csv", n_full_days=5, seed=2)
    seen = {}

    def fake_backtest(arr, leg=None, log=print):
        seen["leg"] = leg
        return [(5, 8, 12.5), (20, 25, -4.0)], {"total_pnl": 8.5}
    monkeypatch.setattr(kls, "run_nq_backtest", fake_backtest)
    state, summary = kls.build(str(path), str(tmp_path / "out"), leg="NOISE_382",
                               log=lambda *a, **k: None)
    assert seen["leg"]["strategy"] == "NOISE_1_8_CT304.py"
    assert (tmp_path / "out" / "NOISE_382_v12_state.joblib").exists()
    assert not (tmp_path / "out" / "NOISE_422_v12_state.joblib").exists()
    assert summary["leg"] == "NOISE_382" and summary["leg_live"] is False


# ── the READ-ONLY walk-vs-state check (the #422 reproduction check) ─────────────────────
def test_walk_cut_points_cover_warmup_refit_and_the_last_trade():
    from augur_engine import ml_keel as K
    cuts = kls.walk_cut_points(4861, n_cuts=3)
    assert cuts[0] == K.MIN_HISTORY - 1 and K.MIN_HISTORY in cuts
    assert K.MIN_HISTORY + K.REFIT_EVERY in cuts
    assert cuts[-1] == 4860 and cuts == sorted(set(cuts))
    assert kls.walk_cut_points(10) == [9]
    assert kls.walk_cut_points(0) == []


def test_check_state_matches_walk_passes_on_a_real_walk(tmp_path):
    """check_state_matches_walk on a small series: state-built scoring equals keel_walk's
    own size at every cut point (the same 1e-12 bar tests/test_ml_keel_state.py holds the
    split to), and it writes nothing."""
    rng = np.random.RandomState(9)
    n_days, bars = 60, 16
    idx = []
    day = pd.Timestamp("2024-01-02", tz="US/Eastern")
    d = 0
    while d < n_days:
        if day.dayofweek <= 4:
            idx += [day.replace(hour=9, minute=30) + pd.Timedelta(minutes=5 * b) for b in range(bars)]
            d += 1
        day = day + pd.Timedelta(days=1)
    n = len(idx)
    c = 15000.0 + np.cumsum(rng.normal(0, 3.0, n))
    arrays = {"open": c.copy(), "high": c + 2, "low": c - 2, "close": c,
              "volume": np.full(n, 1000.0), "day_id": np.repeat(np.arange(n_days), bars),
              "index": pd.DatetimeIndex(idx)}
    trades, pos = [], 3
    while pos < n - 3 and len(trades) < 120:
        ex = pos + int(rng.randint(1, 4))
        trades.append((pos, ex, float(rng.normal(0.5, 5.0))))
        pos = ex + 1
    logged = []
    before = sorted(os.listdir(tmp_path))
    r = kls.check_state_matches_walk(None, leg="NOISE_422", n_cuts=3, log=logged.append,
                                     arrays=arrays, trades=trades)
    assert r["ok"] is True and not r["mismatches"], r
    assert r["leg"] == "NOISE_422" and r["n_trades"] == len(trades)
    assert r["cuts"] == kls.walk_cut_points(len(trades), 3)
    assert r["max_abs_diff"] <= 1e-12
    assert any("PASS" in line for line in logged)
    assert sorted(os.listdir(tmp_path)) == before
