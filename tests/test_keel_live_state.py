"""tests/test_keel_live_state.py -- tools/keel_live_state.py, the nightly KEEL v12
state builder (OWNER DECISION 2026-09-23, design doc D) -- since 2026-09-28 for EVERY
learned-KEEL leg in api/cloud_signal's CROWN_LEGS and SHADOW_LEGS: the live NOISE_382 leg
and the NOISE_422_KEEL shadow leg, each under its own file names -- and since 2026-10-09
(MANAGER #108) the DIP_424K shadow leg, trained on run #424's OWN NQ walk (its keel "train"
block: #424's params with no asset key, cost 0.0, from 2010-06-07; P&L in dollars), while
DIP_424F (a constant 1.245) has nothing to build.

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


QUIET = lambda *a, **k: None   # noqa: E731


# ── the legs come from CROWN_LEGS / SHADOW_LEGS themselves -- nothing duplicated to drift ─
def test_nightly_default_builds_every_learned_keel_leg_live_first():
    """NOISE_382 (live), then NOISE_422_KEEL and DIP_424K (shadow), in that order, each read
    straight off its own cfg -- a leg with a "train" block trains on ITS params, not the live
    ones; the fixed-tilt, constant-size and plain legs, ORB_R6 and ENGUQ_335 have nothing to
    build and are not listed."""
    legs = kls.resolve_legs()
    assert [(l["leg_key"], l["live"]) for l in legs] == [
        ("NOISE_382", True), ("NOISE_422_KEEL", False), ("DIP_424K", False)]
    for leg in legs:
        cfg = dict(cs.CROWN_LEGS, **cs.SHADOW_LEGS)[leg["leg_key"]]
        assert leg["strategy"] == cfg["strategy"]
        train = cfg["keel"].get("train")
        assert leg["params"] == (train["params"] if train else cfg["params"])
        assert leg["version"] == cfg["keel"]["version"] == kls.VERSION
        # the per-leg training keys exist ONLY on a train leg (NOISE's dicts are unchanged)
        assert ("cost_pts" in leg) == ("date_from" in leg) == bool(train)


def test_live_keel_leg_is_still_run_382_exactly():
    """What this script carried as literals before 2026-09-28 -- unchanged for the live leg."""
    leg = kls.resolve_leg()
    assert leg == {"leg_key": "NOISE_382", "strategy": "NOISE_1_8_CT304.py",
                   "params": {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16,
                              "gate_ratio": 1.15},
                   "version": "v12", "live": True}
    shadow = kls.resolve_leg("NOISE_422_KEEL")
    assert shadow["strategy"] == "NOISE_1_8_CT304H.py" and shadow["live"] is False
    assert shadow["params"] == cs.NOISE_422_PARAMS
    assert set(shadow) == {"leg_key", "strategy", "params", "version", "live"}


def test_dip_424k_trains_on_run_424s_own_nq_walk():
    """DIP_424K: #424's champion EXACTLY, with no asset key (NQDIP_1_1.py's auto mode then
    picks its NQ cost + roll model on the 5m master), cost 0.0 (the file charges its own
    costs), from 2010-06-07 -- while the live QQQ leg's params carry asset="ETF"."""
    dip = kls.resolve_leg("DIP_424K")
    assert dip == {"leg_key": "DIP_424K", "strategy": "NQDIP_1_1.py",
                   "params": cs.DIP_424_PARAMS, "version": "v12", "live": False,
                   "cost_pts": 0.0, "date_from": "2010-06-07"}
    assert "asset" not in dip["params"]
    assert cs.SHADOW_LEGS["DIP_424K"]["params"] == dict(cs.DIP_424_PARAMS, asset="ETF")
    assert dip["params"] is not cs.DIP_424_PARAMS, "a copy -- the builder never mutates the cfg"
    # the constant-size twin has no model, so nothing to build
    with pytest.raises(kls.LegResolutionError, match="not a learned model"):
        kls.resolve_leg("DIP_424F")
    assert kls._pnl_units("NQDIP_1_1.py") == "usd"
    assert kls._pnl_units("NOISE_1_8_CT304.py") == kls._pnl_units("NOISE_1_8_CT304H.py") == "points"
    assert kls._pnl_units("NO_SUCH_FILE.py") == "points"


def test_resolve_refuses_rather_than_guess():
    plain = {"ORB_R6": {"strategy": "ORB_3_6_R6.py", "params": {}}}
    with pytest.raises(kls.LegResolutionError, match="found 0"):
        kls.resolve_legs(crown_legs=plain, shadow_legs={})
    with pytest.raises(kls.LegResolutionError, match="found 0"):
        kls.resolve_leg(crown_legs=plain, shadow_legs={})
    fixed = {"F": {"strategy": "f.py", "keel": {"version": "v12", "mode": "fixed"}}}
    with pytest.raises(kls.NothingToBuild, match="fixed tilts"):
        kls.resolve_legs(crown_legs=plain, shadow_legs=fixed)
    bad = {"B": {"strategy": "b.py", "keel": {"version": "v12", "mode": "fixd"}}}
    with pytest.raises(kls.LegResolutionError, match="unknown keel mode"):
        kls.resolve_legs(crown_legs=dict(plain, **bad), shadow_legs={})
    # on a shadow leg only it is dropped, not raised -- with nothing else to build that is
    # still the loud "found 0" failure
    with pytest.raises(kls.LegResolutionError, match="found 0"):
        kls.resolve_legs(crown_legs=plain, shadow_legs=bad)
    for key, why in (("ORB_R6", "no \"keel\" block"), ("NOISE_422_PLAIN", "no \"keel\" block"),
                     ("NOISE_422_FIXED", "not a learned model"), ("NOT_A_LEG", "unknown leg")):
        with pytest.raises(kls.LegResolutionError, match=why):
            kls.resolve_leg(key)


def test_a_constant_size_leg_has_nothing_to_build_like_a_fixed_one():
    """mode="const" (DIP_424F's one constant size) is a KNOWN no-model mode: never an
    "unknown keel mode", and with only fixed/const legs left the run is NothingToBuild (exit 0)
    naming both kinds."""
    plain = {"ORB_R6": {"strategy": "ORB_3_6_R6.py", "params": {}}}
    const = {"C": {"strategy": "c.py", "keel": {"mode": "const", "size": 1.245}}}
    fixed = {"F": {"strategy": "f.py", "keel": {"version": "v12", "mode": "fixed"}}}
    with pytest.raises(kls.NothingToBuild, match="C use a constant size") as ei:
        kls.resolve_legs(crown_legs=plain, shadow_legs=const)
    assert "fixed tilts" not in str(ei.value)
    with pytest.raises(kls.NothingToBuild) as ei:
        kls.resolve_legs(crown_legs=plain, shadow_legs=dict(fixed, **const))
    assert str(ei.value) == ("KEEL leg(s) F use v12's fixed tilts (no model); KEEL leg(s) C use "
                             "a constant size (no model) -- nothing to build")
    # a const LIVE leg is not an unknown mode either -- just nothing to build
    with pytest.raises(kls.NothingToBuild):
        kls.resolve_legs(crown_legs=const, shadow_legs={})
    learned = {"L": {"strategy": "l.py", "keel": {"version": "v12"}}}
    assert [l["leg_key"] for l in kls.resolve_legs(crown_legs=learned, shadow_legs=const)] == ["L"]


def test_an_unreadable_train_block_drops_a_shadow_leg_and_stays_loud_on_a_live_one(capsys):
    learned = {"L": {"strategy": "l.py", "keel": {"version": "v12"}}}
    for bad in ({"params": "not a dict"}, ["params"], {"params": {}, "cost_pts": "x"},
                {"params": {}, "cost_pts": -1.0}, {"params": {}, "date_from": "June 2010"}):
        shadow = {"D": {"strategy": "d.py", "keel": {"version": "v12", "train": bad}}}
        assert [l["leg_key"] for l in kls.resolve_legs(crown_legs=learned, shadow_legs=shadow)] == ["L"]
        assert "shadow leg D skipped" in capsys.readouterr().out
        with pytest.raises(kls.LegResolutionError, match="train"):
            kls.resolve_legs(crown_legs=dict(learned, D=shadow["D"]), shadow_legs={})
    # a readable one: params replace the live ones; cost / start default to the house literals
    ok = {"D": {"strategy": "d.py", "params": {"asset": "ETF", "x": 1},
                "keel": {"version": "v12", "train": {"params": {"x": 1}}}}}
    leg = kls.resolve_legs(crown_legs=learned, shadow_legs=ok)[1]
    assert leg["params"] == {"x": 1}
    assert (leg["cost_pts"], leg["date_from"]) == (kls.COST_PTS, kls.DATE_FROM)


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
    assert disk_summary["strategy"] == "NOISE_1_8_CT304.py"
    assert disk_summary["params"] == cs.NOISE_382_PARAMS
    assert "leg_live" not in disk_summary, "the live leg's summary keeps exactly its old keys"
    # the model's seed, for the NOISE forward log (api/noise_forward.py keel_meta)
    assert disk_summary["seed"] == reloaded["seed"]
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


# ── the nightly run: every learned leg, one master read, failures isolated ──────────────
def _fake_backtest(seen):
    def fake(arr, leg=None, log=print):
        seen.append(leg["leg_key"])
        return [(5, 8, 12.5), (20, 25, -4.0), (40, 44, 6.25)], {"total_pnl": 14.75}
    return fake


def _run_main(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["keel_live_state.py"] + argv)
    return kls.main()


def test_main_builds_both_learned_legs_under_their_own_names_reading_the_master_once(
        tmp_path, monkeypatch):
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen, loads = [], []
    monkeypatch.setattr(kls, "run_nq_backtest", _fake_backtest(seen))
    real_load = kls.load_master
    monkeypatch.setattr(kls, "load_master",
                        lambda f, log=print, **kw: loads.append(f) or real_load(f, log=QUIET, **kw))
    assert _run_main(["--nq-file", str(nq), "--out-dir", str(out)], monkeypatch) is None
    assert seen == ["NOISE_382", "NOISE_422_KEEL", "DIP_424K"] and len(loads) == 1
    # the synthetic master is years old, so the NQ FRESHNESS ALERT (2026-10-05) also leaves
    # its one-push marker -- not a leg file
    names = sorted(p.name for p in out.iterdir() if p.name != kls.STALE_MARKER)
    assert names == ["DIP_424K_v12_state.joblib", "DIP_424K_v12_summary.json",
                     "NOISE_382_v12_state.joblib", "NOISE_382_v12_summary.json",
                     "NOISE_422_KEEL_v12_state.joblib", "NOISE_422_KEEL_v12_summary.json"]
    # exactly the files the learned legs' cfgs read
    for key, cfg in (("NOISE_382", cs.CROWN_LEGS["NOISE_382"]),
                     ("NOISE_422_KEEL", cs.SHADOW_LEGS["NOISE_422_KEEL"]),
                     ("DIP_424K", cs.SHADOW_LEGS["DIP_424K"])):
        assert os.path.basename(cfg["keel"]["state_path"]) == f"{key}_v12_state.joblib"
        assert os.path.basename(cfg["keel"]["summary_path"]) == f"{key}_v12_summary.json"
    with open(out / "NOISE_422_KEEL_v12_summary.json", encoding="utf-8") as f:
        sh = json.load(f)
    assert sh["leg"] == "NOISE_422_KEEL" and sh["leg_live"] is False
    assert sh["strategy"] == "NOISE_1_8_CT304H.py" and sh["params"] == cs.NOISE_422_PARAMS


def test_a_shadow_build_failure_never_fails_the_run_or_the_live_build(tmp_path, monkeypatch, capsys):
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen = []
    fake = _fake_backtest(seen)

    def shadow_breaks(arr, leg=None, log=print):
        if not leg["live"]:
            raise RuntimeError("synthetic shadow failure")
        return fake(arr, leg=leg, log=log)
    monkeypatch.setattr(kls, "run_nq_backtest", shadow_breaks)
    assert _run_main(["--nq-file", str(nq), "--out-dir", str(out)], monkeypatch) is None   # exit 0
    assert (out / "NOISE_382_v12_state.joblib").exists()
    assert not (out / "NOISE_422_KEEL_v12_state.joblib").exists()
    assert not (out / "DIP_424K_v12_state.joblib").exists()
    assert "shadow leg(s) not built this run: NOISE_422_KEEL, DIP_424K" in capsys.readouterr().out


def test_a_failed_dip_build_fails_neither_noise_build_nor_the_run(tmp_path, monkeypatch, capsys):
    """MANAGER #108: the DIP leg is a shadow leg -- its build breaking (a strategy error, a
    walk that raises) leaves both NOISE states built and the unit green (exit 0)."""
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen = []
    fake = _fake_backtest(seen)

    def dip_breaks(arr, leg=None, log=print):
        if leg["leg_key"] == "DIP_424K":
            raise RuntimeError("synthetic DIP failure")
        return fake(arr, leg=leg, log=log)
    monkeypatch.setattr(kls, "run_nq_backtest", dip_breaks)
    assert _run_main(["--nq-file", str(nq), "--out-dir", str(out)], monkeypatch) is None
    assert seen == ["NOISE_382", "NOISE_422_KEEL"]
    assert (out / "NOISE_382_v12_state.joblib").exists()
    assert (out / "NOISE_422_KEEL_v12_state.joblib").exists()
    assert not (out / "DIP_424K_v12_state.joblib").exists()
    text = capsys.readouterr().out
    assert "DIP_424K FAILED (shadow leg): RuntimeError: synthetic DIP failure" in text
    assert "shadow leg(s) not built this run: DIP_424K" in text


def test_dip_train_settings_reach_the_backtest_and_the_summary(tmp_path, monkeypatch):
    """The real run_nq_backtest -> run_backtest path (spied): NOISE legs keep the house cost
    and their live params; DIP_424K gets #424's params with NO asset key and cost 0.0, from
    the one shared master read. Its summary records cost_pts 0.0, date_from 2010-06-07 and
    pnl_units "usd"; NOISE summaries carry no pnl_units key and the same values as before."""
    import augur_engine.engine as eng
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    calls = []

    def spy(strategy, arrays=None, params=None, cost_pts=None, return_trades=False, **kw):
        calls.append({"strategy": strategy, "params": dict(params), "cost_pts": cost_pts,
                      "first_day": str(pd.DatetimeIndex(arrays["index"])[0].date())})
        c = arrays["close"]
        # 6-field trades like NQDIP_1_1's (entry, exit, pnl, side, entry px, exit px)
        trades = [(e, x, float(c[x] - c[e]), 1, float(c[e]), float(c[x]))
                  for e, x in ((5, 8), (20, 25), (40, 44))]
        return {"trades": trades, "total_pnl": sum(t[2] for t in trades)}
    monkeypatch.setattr(eng, "run_backtest", spy)
    loads = []
    real_load = kls.load_master
    monkeypatch.setattr(kls, "load_master",
                        lambda f, log=print, **kw: loads.append(kw) or real_load(f, log=QUIET, **kw))
    assert _run_main(["--nq-file", str(nq), "--out-dir", str(out)], monkeypatch) is None
    assert [c["strategy"] for c in calls] == ["NOISE_1_8_CT304.py", "NOISE_1_8_CT304H.py",
                                              "NQDIP_1_1.py"]
    noise382, noise422, dip = calls
    assert noise382["params"] == cs.NOISE_382_PARAMS and noise382["cost_pts"] == kls.COST_PTS
    assert noise422["params"] == cs.NOISE_422_PARAMS and noise422["cost_pts"] == kls.COST_PTS
    assert dip["params"] == cs.DIP_424_PARAMS and "asset" not in dip["params"]
    assert dip["cost_pts"] == 0.0
    assert loads == [{"date_from": "2010-06-07"}], "the master is read once for every leg"
    assert noise382["first_day"] == noise422["first_day"] == dip["first_day"]

    def summary(key):
        with open(out / f"{key}_v12_summary.json", encoding="utf-8") as f:
            return json.load(f)
    s = summary("DIP_424K")
    assert (s["cost_pts"], s["date_from"], s["pnl_units"]) == (0.0, "2010-06-07", "usd")
    assert s["leg"] == "DIP_424K" and s["leg_live"] is False and s["strategy"] == "NQDIP_1_1.py"
    assert s["params"] == cs.DIP_424_PARAMS
    for key in ("NOISE_382", "NOISE_422_KEEL"):
        s = summary(key)
        assert (s["cost_pts"], s["date_from"]) == (kls.COST_PTS, kls.DATE_FROM)
        assert "pnl_units" not in s


def test_masters_are_read_once_per_training_start(tmp_path, monkeypatch):
    """A train leg starting on another date gets its OWN master read from that date; legs
    that share a start share one read, and the NQ freshness check runs once a night."""
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    crown = {"A": {"strategy": "NOISE_1_8_CT304.py", "params": {},
                   "keel": {"version": "v12"}}}
    shadow = {"B": {"strategy": "x.py", "keel": {"version": "v12",
                                                "train": {"params": {}, "date_from": "2024-01-05"}}},
              "C": {"strategy": "y.py", "keel": {"version": "v12"}}}
    monkeypatch.setattr(cs, "CROWN_LEGS", crown)
    monkeypatch.setattr(cs, "SHADOW_LEGS", shadow)
    first_day, loads, fresh = {}, [], []

    def fake(arr, leg=None, log=print):
        first_day[leg["leg_key"]] = str(pd.DatetimeIndex(arr["index"])[0].date())
        return [(5, 8, 12.5), (20, 25, -4.0), (40, 44, 6.25)], {"total_pnl": 14.75}
    monkeypatch.setattr(kls, "run_nq_backtest", fake)
    real_load = kls.load_master
    monkeypatch.setattr(kls, "load_master",
                        lambda f, log=print, **kw: loads.append(kw["date_from"]) or real_load(f, log=QUIET, **kw))
    monkeypatch.setattr(kls, "check_nq_freshness", lambda *a, **k: fresh.append(1))
    _run_main(["--nq-file", str(nq), "--out-dir", str(tmp_path / "out")], monkeypatch)
    assert loads == [kls.DATE_FROM, "2024-01-05"]
    assert first_day == {"A": "2024-01-02", "B": "2024-01-05", "C": "2024-01-02"}
    assert fresh == [1]
    # build() refuses a master read from another start rather than train on the wrong span
    m = real_load(str(nq), log=QUIET)
    with pytest.raises(ValueError, match="2024-01-05"):
        kls.build(str(nq), str(tmp_path / "out2"), leg=kls.resolve_leg("B"), master=m, log=QUIET)


def test_a_live_build_failure_fails_the_run_after_the_shadow_leg_is_still_built(tmp_path, monkeypatch):
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen = []
    fake = _fake_backtest(seen)

    def live_breaks(arr, leg=None, log=print):
        if leg["live"]:
            raise RuntimeError("synthetic live failure")
        return fake(arr, leg=leg, log=log)
    monkeypatch.setattr(kls, "run_nq_backtest", live_breaks)
    with pytest.raises(SystemExit) as ei:
        _run_main(["--nq-file", str(nq), "--out-dir", str(out)], monkeypatch)
    assert "NOISE_382" in str(ei.value.code)
    assert (out / "NOISE_422_KEEL_v12_state.joblib").exists()


def test_main_leg_flag_builds_only_that_leg(tmp_path, monkeypatch):
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen = []
    monkeypatch.setattr(kls, "run_nq_backtest", _fake_backtest(seen))
    _run_main(["--nq-file", str(nq), "--out-dir", str(out), "--leg", "NOISE_422_KEEL"], monkeypatch)
    assert seen == ["NOISE_422_KEEL"]
    assert not (out / "NOISE_382_v12_state.joblib").exists()


def test_main_fails_loudly_when_no_leg_carries_a_learned_keel(tmp_path, monkeypatch):
    strip = lambda legs: {k: {kk: vv for kk, vv in v.items() if kk != "keel"}   # noqa: E731
                          for k, v in legs.items()}
    monkeypatch.setattr(cs, "CROWN_LEGS", strip(cs.CROWN_LEGS))
    monkeypatch.setattr(cs, "SHADOW_LEGS", strip(cs.SHADOW_LEGS))
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=3)
    with pytest.raises(SystemExit) as ei:
        _run_main(["--nq-file", str(nq), "--out-dir", str(tmp_path / "out")], monkeypatch)
    assert "found 0" in str(ei.value.code)
    assert not (tmp_path / "out").exists()


def test_a_bad_shadow_keel_mode_is_dropped_and_the_live_leg_still_builds(tmp_path, monkeypatch, capsys):
    """A typo'd mode on a SHADOW leg (e.g. "fixd") drops that leg with a log line; the live
    NOISE_382 state still builds. The same typo on a LIVE leg stays a loud failure."""
    shadow = {k: dict(v) for k, v in cs.SHADOW_LEGS.items()}
    shadow["NOISE_422_KEEL"]["keel"] = dict(shadow["NOISE_422_KEEL"]["keel"], mode="fixd")
    monkeypatch.setattr(cs, "SHADOW_LEGS", shadow)
    assert [leg["leg_key"] for leg in kls.resolve_legs()] == ["NOISE_382", "DIP_424K"]
    assert "NOISE_422_KEEL" in capsys.readouterr().out

    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen = []
    monkeypatch.setattr(kls, "run_nq_backtest", _fake_backtest(seen))
    assert _run_main(["--nq-file", str(nq), "--out-dir", str(out)], monkeypatch) is None
    assert seen == ["NOISE_382", "DIP_424K"] and (out / "NOISE_382_v12_state.joblib").exists()

    crown = {k: dict(v) for k, v in cs.CROWN_LEGS.items()}
    crown["NOISE_382"]["keel"] = dict(crown["NOISE_382"]["keel"], mode="fixd")
    with pytest.raises(kls.LegResolutionError):
        kls.resolve_legs(crown_legs=crown, shadow_legs=cs.SHADOW_LEGS)


def test_defer_in_session_is_rechecked_before_each_shadow_leg(tmp_path, monkeypatch, capsys):
    """A build that starts at 09:24 ET builds the live leg, but if the clock has reached
    09:25 by the shadow leg, that leg is skipped (the 18:30 timer builds it)."""
    import datetime
    import zoneinfo
    et = zoneinfo.ZoneInfo("America/New_York")
    clock = iter([datetime.datetime(2026, 9, 22, 9, 24, tzinfo=et)]
                 + [datetime.datetime(2026, 9, 22, 9, 26, tzinfo=et)] * 5)
    monkeypatch.setattr(kls, "_now_et", lambda: next(clock))
    nq = _write_master_csv(tmp_path / "nq.csv", n_full_days=10, seed=3)
    out = tmp_path / "out"
    seen = []
    monkeypatch.setattr(kls, "run_nq_backtest", _fake_backtest(seen))
    assert _run_main(["--nq-file", str(nq), "--out-dir", str(out), "--defer-in-session"],
                     monkeypatch) is None
    assert seen == ["NOISE_382"]
    assert (out / "NOISE_382_v12_state.joblib").exists()
    assert not (out / "NOISE_422_KEEL_v12_state.joblib").exists()
    assert not (out / "DIP_424K_v12_state.joblib").exists()
    text = capsys.readouterr().out
    assert "NOISE_422_KEEL (shadow) deferred" in text and "DIP_424K (shadow) deferred" in text


# ── the READ-ONLY walk-vs-state check (the #422 reproduction check) ─────────────────────
def test_walk_cut_points_cover_warmup_refit_and_the_last_trade():
    from augur_engine import ml_keel as K
    cuts = kls.walk_cut_points(4861, n_cuts=3)
    assert cuts[0] == K.MIN_HISTORY - 1 and K.MIN_HISTORY in cuts
    assert K.MIN_HISTORY + K.REFIT_EVERY in cuts
    assert cuts[-1] == 4860 and cuts == sorted(set(cuts))
    assert kls.walk_cut_points(10) == [9]
    assert kls.walk_cut_points(0) == []


def _small_series():
    """A 60-session, 16-bar-a-day synthetic series and ~120 non-overlapping trades on it."""
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
    return arrays, trades


def test_check_state_matches_walk_passes_on_a_real_walk(tmp_path):
    """check_state_matches_walk on a small series: state-built scoring equals keel_walk's
    own size at every cut point (the same 1e-12 bar tests/test_ml_keel_state.py holds the
    split to), and it writes nothing."""
    arrays, trades = _small_series()
    logged = []
    before = sorted(os.listdir(tmp_path))
    r = kls.check_state_matches_walk(None, leg="NOISE_422_KEEL", n_cuts=3, log=logged.append,
                                     arrays=arrays, trades=trades)
    assert r["ok"] is True and not r["mismatches"], r
    assert r["leg"] == "NOISE_422_KEEL" and r["n_trades"] == len(trades)
    assert r["cuts"] == kls.walk_cut_points(len(trades), 3)
    assert r["max_abs_diff"] <= 1e-12
    assert any("PASS" in line for line in logged)
    assert sorted(os.listdir(tmp_path)) == before


def test_verify_walk_reads_the_master_from_the_legs_own_start(monkeypatch):
    """--verify-walk on a train leg re-runs ITS walk: the master from its own date_from, the
    backtest through run_nq_backtest (its params and cost)."""
    arrays, trades = _small_series()
    seen = []
    monkeypatch.setattr(kls, "load_nq_arrays",
                        lambda f, date_from=None, log=print, **k: seen.append(date_from) or (arrays, None))
    monkeypatch.setattr(kls, "run_nq_backtest",
                        lambda arr, leg=None, log=print: seen.append(leg["cost_pts"]) or (trades, {}))
    leg = {"leg_key": "D", "strategy": "d.py", "params": {}, "version": "v12", "live": False,
           "cost_pts": 0.0, "date_from": "2011-01-03"}
    r = kls.check_state_matches_walk("nq.csv", leg=leg, n_cuts=2, log=QUIET)
    assert r["ok"] is True and seen == ["2011-01-03", 0.0]


def _nq_master():
    p = os.environ.get("KEEL_TEST_NQ_MASTER") or os.path.join(ROOT, "augur_uploads",
                                                              "NOADJ_NQ_5m_RTH.csv")
    return p if os.path.exists(p) else None


@pytest.mark.skipif(_nq_master() is None, reason="no NQ 5m RTH master on this machine "
                    "(set KEEL_TEST_NQ_MASTER to point at one)")
def test_dip_424k_training_walk_is_run_424s_on_the_real_master():
    """The builder's own path (resolve_leg -> load_nq_arrays -> run_nq_backtest) on run #424's
    pinned window gives #424's 3,431 trades (the run doc's gate_validate.keel n_trades), as
    6-field trades with P&L in dollars."""
    leg = kls.resolve_leg("DIP_424K")
    arr, _dropped = kls.load_nq_arrays(_nq_master(), date_from=leg["date_from"],
                                       date_to="2026-08-24", drop_incomplete=False, log=QUIET)
    trades, res = kls.run_nq_backtest(arr, leg=leg, log=QUIET)
    assert len(trades) == 3431
    assert all(len(t) == 6 for t in trades)
