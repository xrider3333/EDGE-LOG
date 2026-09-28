"""tests/test_noise_422_shadow.py -- OWNER DECISION 2026-09-28 (via MANAGER): the Webull paper
book's PRIMARY NOISE leg stays NOISE #382 + KEEL v12 (live, unchanged), and NOISE #422 runs
beside it as THREE background SHADOW legs -- no orders -- so the Custom ML chat can score
their would-be trades: NOISE_422_PLAIN, NOISE_422_FIXED (KEEL v12's fixed tilts, no model,
research arm A3) and NOISE_422_KEEL (KEEL v12 learned, its own nightly state).
NOISE #422 = NOISE_1_8_CT304H.py (the #304 crown's own core, frozen literally inside the
file, sized by the HOURLY squeeze -- frame frozen at 60 inside the file) at run #422's
crowned cell {"gate_len": 20, "gate_ratio": 1.15, "tilt_mult": 1.75}.

Rewritten from origin/prep/noise-422's tests/test_noise_422_switch.py, which assumed #422
REPLACED #382 as the live leg -- the swap was not shipped. The engine hooks it proved
(CT304H's REQUIRED_LOOKBACK_SESSIONS re-export and vol_prior_ranges pass-through) are
carried over unchanged; everything about the live leg is now the opposite assertion.

COVERS:
  1. SHADOW_LEGS carries the three #422 variants with every field NOISE_382 carries (5m,
     the same warm-up, decide_at_close) plus "shadow": True; CROWN_LEGS is untouched
     (ORB_R6 + NOISE_382 exactly) and no #422 key is in qqq_exec's ENGINE_LEG_MAP.
  2. The cell is admissible in NOISE_1_8_CT304H.py's OWN fence (and a one-step-off value
     is refused), and the file trades a synthetic series with sizes {1.0, 1.75} only.
  3. The two live-engine hooks on CT304H (262-session window; vol_prior_ranges reaches
     NOISE_1_0.py's _vol_percentile, and changes nothing when absent).
  4. qqq_exec's reverse lookup still resolves NOISE to the live NOISE_382 key.
  5. The three shadow variants end to end through cloud_signal.step() over one synthetic
     session: the expected sizes for each (plain 1.0/1.75, fixed = plain x the A3 tilt at
     the real entry bar, learned = plain x a real KEEL score), and the learned leg with NO
     state scores 1.0 silently.
  6. On the owner's real QQQ 5m cache (skips cleanly without it): the leg trades and
     sizes through run_leg_trades, and a fresh shadow key cold-starts with one SEED.
"""
import importlib.util as _ilu
import json
import os
import shutil
import sys
import unittest.mock as mock

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                       # noqa: E402
from api import market_calendar as mc               # noqa: E402
from api import qqq_exec as qe                      # noqa: E402
from augur_engine import ml_keel as K               # noqa: E402
from augur_engine.engine import run_backtest        # noqa: E402
from augur_engine.strategies import load_strategy   # noqa: E402

NOISE_422_PARAMS = {"gate_len": 20, "gate_ratio": 1.15, "tilt_mult": 1.75}
VARIANTS = ("NOISE_422_PLAIN", "NOISE_422_FIXED", "NOISE_422_KEEL")
STRAT_DIR = os.path.join(ROOT, "augur_strategies")

REAL_CACHE_5M = r"C:\EdgeLog\ohlc\QQQ_5m.csv"


def _cache_state(path):
    try:
        return True, os.path.getsize(path) == 0
    except OSError:
        return False, False


_PRESENT, _EMPTY = _cache_state(REAL_CACHE_5M)
HAS_REAL_5M_CACHE = _PRESENT and not _EMPTY
_CACHE_SKIP = "no local QQQ 5m bar cache on this machine: %s" % REAL_CACHE_5M


def _load_fresh(name, alias):
    """A private copy of a strategy module, so a test can patch its internals without
    touching the engine's own cached load of the same file."""
    spec = _ilu.spec_from_file_location(alias, os.path.join(STRAT_DIR, name))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── a synthetic QQQ-shaped 5m series on REAL session days ─────────────────────────────────
def _sessions(n, end="2026-09-25"):
    """The last `n` full (not half-day) sessions up to `end`, oldest first -- real
    calendar days, so step()'s session logic and KEEL's staleness count read them as
    genuine sessions."""
    out = []
    d = pd.Timestamp(end).date()
    while len(out) < n:
        if mc.is_session(d) and not mc._is_half_day(d):
            out.append(d)
        d = d - pd.Timedelta(days=1)
    return out[::-1]


def _synthetic_epoch(days, seed=3, bars=78, price=700.0):
    """Epoch-schema 5m RTH bars (QQQ_5m.csv's own on-disk shape): a random walk whose
    volatility alternates hour by hour, so the hourly squeeze really turns on and off."""
    rng = np.random.RandomState(seed)
    rows = []
    p = price
    for d in days:
        start = pd.Timestamp(f"{d} 09:30:00", tz=cs.TZ)
        for b in range(bars):
            sig = 0.2 if (b // 12) % 3 else 0.07
            o = p
            c = p + rng.normal(0, sig)
            h = max(o, c) + abs(rng.normal(0, sig * 0.4))
            l = min(o, c) - abs(rng.normal(0, sig * 0.4))
            ts = int((start + pd.Timedelta(minutes=5 * b)).tz_convert("UTC").timestamp())
            rows.append((ts, o, h, l, c, 1000.0))
            p = c
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


_DAYS = _sessions(70)
_EPOCH = _synthetic_epoch(_DAYS)


def _arrays_through(day, n_sessions=300):
    now = pd.Timestamp(f"{day} 17:00", tz=cs.TZ).to_pydatetime()
    return cs.closed_arrays(_EPOCH, now, "5m", n_sessions)


# ── 1. SHADOW_LEGS carries #422; the live legs are untouched ─────────────────────────────
def test_live_legs_are_exactly_orb_and_noise_382():
    assert list(cs.CROWN_LEGS) == ["ORB_R6", "NOISE_382"]
    live = cs.CROWN_LEGS["NOISE_382"]
    assert live["strategy"] == "NOISE_1_8_CT304.py" and live["params"] == cs.NOISE_382_PARAMS
    assert live["keel"] == dict(version="v12", **cs.keel_paths("NOISE_382", "v12"))
    assert live["decide_at_close"] is True and "shadow" not in live
    noise_keys = [k for k in cs.CROWN_LEGS if qe.ENGINE_LEG_MAP.get(k) == "NOISE"]
    assert noise_keys == ["NOISE_382"], "exactly ONE live engine key may feed the NOISE exec leg"


def test_three_noise_422_shadow_variants_carry_every_field_noise_382_does():
    for key in VARIANTS:
        leg = cs.SHADOW_LEGS[key]
        assert key not in cs.CROWN_LEGS and key not in qe.ENGINE_LEG_MAP, key
        assert leg["strategy"] == "NOISE_1_8_CT304H.py"
        assert leg["timeframe"] == "5m"
        assert leg["params"] == NOISE_422_PARAMS == cs.NOISE_422_PARAMS
        assert "gate_tf_min" not in leg["params"], "the file freezes the frame at 60 itself"
        assert leg["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS
        assert leg["decide_at_close"] is True
        assert leg["shadow"] is True
        assert leg["eod_flat"] is True    # flat at the close like NOISE_382 (EOD SETTLE)
        assert set(leg) - {"keel"} == {"strategy", "timeframe", "params", "warmup_sessions",
                                       "decide_at_close", "eod_flat", "shadow"}, key
    assert "keel" not in cs.SHADOW_LEGS["NOISE_422_PLAIN"]
    assert cs.SHADOW_LEGS["NOISE_422_FIXED"]["keel"] == dict(version="v12", mode="fixed")
    kl = cs.SHADOW_LEGS["NOISE_422_KEEL"]["keel"]
    assert kl == dict(version="v12", **cs.keel_paths("NOISE_422_KEEL", "v12"))
    assert os.path.basename(kl["state_path"]) == "NOISE_422_KEEL_v12_state.joblib"
    # never the live leg's files
    assert kl["state_path"] != cs.CROWN_LEGS["NOISE_382"]["keel"]["state_path"]


# ── 2. the cell is admissible and the file trades ────────────────────────────────────────
def test_noise_422_params_are_inside_ct304h_own_fence():
    mod = load_strategy("NOISE_1_8_CT304H.py")
    assert mod._in_neighbourhood(cs.NOISE_422_PARAMS) is True
    assert mod._GATE_TF_MIN == 60
    # one step outside the declared set is REFUSED (None), never clamped -- so the check
    # above is not vacuously true. 2.0 was #382's tilt; CT304H fences it out on purpose.
    assert mod._in_neighbourhood(dict(cs.NOISE_422_PARAMS, tilt_mult=2.0)) is False
    arr = _arrays_through(_DAYS[-1])
    assert mod.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"],
                            day_id=arr["day_id"], index=arr["index"],
                            **dict(cs.NOISE_422_PARAMS, gate_ratio=1.3)) is None


def test_noise_422_cell_trades_a_synthetic_series_through_the_engine():
    arr = _arrays_through(_DAYS[-1])
    res = run_backtest("NOISE_1_8_CT304H.py", arrays=arr, params=cs.NOISE_422_PARAMS,
                       cost_pts=0.533, return_trades=True)
    assert res and res["trades"], "the #422 cell must trade the synthetic series"
    sizes = set(res["trade_sizes"])
    assert sizes <= {1.0, 1.75} and 1.75 in sizes, sizes
    assert res["size_cost_pts"] == 0.533


# ── 3. the live-engine hooks ────────────────────────────────────────────────────────────
def test_ct304h_exposes_the_same_required_lookback_as_noise_1_0():
    ct304h = load_strategy("NOISE_1_8_CT304H.py")
    noise10 = load_strategy("NOISE_1_0.py")
    assert ct304h.REQUIRED_LOOKBACK_SESSIONS == noise10.REQUIRED_LOOKBACK_SESSIONS == 252
    assert cs.required_lookback_sessions("NOISE_1_8_CT304H.py") == 252
    for key in VARIANTS:
        assert cs.leg_warmup_sessions(cs.SHADOW_LEGS[key]) == 262, key
    assert cs._leg_accepts_vol_prior_ranges("NOISE_1_8_CT304H.py") is True


def test_vol_prior_ranges_reaches_noise_1_0_through_ct304h():
    """End to end down the REAL chain CT304H -> NOISE_1_1_NBHD -> NOISE_1_0: the kwarg
    the engine passes arrives at NOISE_1_0.py's _vol_percentile as prior_ranges. Before the
    2026-09-27 hook CT304H had no pass-through, so this arrived as nothing while
    _leg_accepts_vol_prior_ranges (which reads only the bottom module's signature) still
    said yes."""
    ct304h = _load_fresh("NOISE_1_8_CT304H.py", "t422s_ct304h_vpr")
    noise10 = ct304h._base._base
    assert noise10.__file__.endswith("NOISE_1_0.py")
    seen = []
    orig = noise10._vol_percentile

    def spy(*a, **kw):
        seen.append(kw.get("prior_ranges"))
        return orig(*a, **kw)
    arr = _arrays_through(_DAYS[-1])
    prior = [0.01] * 30
    with mock.patch.object(noise10, "_vol_percentile", spy):
        ct304h.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"],
                            day_id=arr["day_id"], index=arr["index"],
                            vol_prior_ranges=prior, **cs.NOISE_422_PARAMS)
    assert seen and all(p == prior for p in seen), seen[:3]


def test_vol_prior_ranges_absent_changes_nothing():
    """The normal backtest path never passes the kwarg: the base call then carries no
    vol_prior_ranges key at all (additive, not defaulting), and CT304H takes exactly its
    core's trades."""
    ct304h = _load_fresh("NOISE_1_8_CT304H.py", "t422s_ct304h_absent")
    captured = []
    orig = ct304h._base.run_backtest

    def spy(*a, **kw):
        captured.append(dict(kw))
        return orig(*a, **kw)
    arr = _arrays_through(_DAYS[-1])
    args = (arr["open"], arr["high"], arr["low"], arr["close"])
    with mock.patch.object(ct304h._base, "run_backtest", spy):
        out = ct304h.run_backtest(*args, day_id=arr["day_id"], index=arr["index"],
                                  return_trades=True, **cs.NOISE_422_PARAMS)
    assert captured and "vol_prior_ranges" not in captured[0]
    base = orig(*args, day_id=arr["day_id"], index=arr["index"], return_trades=True,
                **ct304h._FROZEN)
    assert [t[:2] for t in out["trades"]] == [t[:2] for t in base["trades"]], \
        "CT304H must take exactly its core's trades -- the tilt sizes, never selects"
    again = ct304h.run_backtest(*args, day_id=arr["day_id"], index=arr["index"],
                                return_trades=True, **cs.NOISE_422_PARAMS)
    assert again["trades"] == out["trades"] and again["total_pnl"] == out["total_pnl"]


# ── 4. qqq_exec's leg map still resolves the LIVE NOISE key ─────────────────────────────
def test_engine_key_for_noise_is_still_the_live_382():
    assert qe._engine_key_for_leg("NOISE", cs) == "NOISE_382"
    assert qe.ENGINE_LEG_MAP["ENGUQ_335"] == "ENGUQ", "kept so an old live row still resolves"


# ── 5. the three variants end to end through step() ─────────────────────────────────────
def _write_keel_state(home, leg_key="NOISE_422_KEEL"):
    """A real fitted KEEL v12 state from the #422 cell's own trades on the synthetic
    series, under the file names keel_paths(leg_key) reads, dated like a fresh build."""
    arr = _arrays_through(_DAYS[-2])
    res = run_backtest("NOISE_1_8_CT304H.py", arrays=arr, params=cs.NOISE_422_PARAMS,
                       cost_pts=0.533, return_trades=True)
    state = K.keel_build_state(arr, res["trades"], version="v12")
    kp = cs.keel_paths(leg_key, "v12", home=home)
    os.makedirs(kp["dir"], exist_ok=True)
    import joblib
    joblib.dump(state, kp["state_path"])
    with open(kp["summary_path"], "w", encoding="utf-8") as f:
        json.dump({"version": "v12", "data_through": str(_DAYS[-2]), "n_trades": state["n"],
                   "last_nq_session": str(_DAYS[-2])}, f)
    return dict(version="v12", **kp)


def _shadow_cfgs(home, keel_state=True):
    """The three SHIPPED shadow cfgs, the learned one pointed at `home`'s KEEL files."""
    cfgs = {k: dict(cs.SHADOW_LEGS[k]) for k in VARIANTS}
    kp = cs.keel_paths("NOISE_422_KEEL", "v12", home=home)
    cfgs["NOISE_422_KEEL"]["keel"] = (_write_keel_state(home) if keel_state
                                      else dict(version="v12", **kp))
    return cfgs


def run_session(home, legs, fetch=False):
    """SEED at the previous close, then every 5m bar of the last synthetic session."""
    paths = cs._paths(home=home)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _EPOCH.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    seed = cs.step(now=pd.Timestamp(f"{_DAYS[-2]} 17:00", tz=cs.TZ).to_pydatetime(),
                   legs=legs, paths=paths, fetch=fetch)
    events = []
    for b in range(1, 79):
        now = pd.Timestamp(f"{_DAYS[-1]} 09:30", tz=cs.TZ) + pd.Timedelta(minutes=5 * b, seconds=10)
        events += cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=fetch)
    return seed, events


def _full_history_trades(cfg):
    """entry_time -> the trade the full-history run gives (no probe, no stand-ins), with
    its arrays -- the backtest reference every live/shadow size must equal."""
    end = pd.Timestamp(f"{_DAYS[-1]} 17:00", tz=cs.TZ).to_pydatetime()
    arr = cs.closed_arrays(_EPOCH, end, "5m", cs.leg_warmup_sessions(cfg))
    return arr, {str(t["entry_time"]): t for t in cs.run_leg_trades(cfg, arr, leg_key="X")}


def test_three_variants_size_as_designed_on_one_synthetic_session(tmp_path):
    home = str(tmp_path / "home")
    legs = _shadow_cfgs(home)
    seed, events = run_session(home, legs)
    assert sorted(e["leg"] for e in seed) == sorted(VARIANTS)
    assert all(e["event"] == "SEED" and e["keel_size"] == "" for e in seed)
    by_leg = {k: [e for e in events if e["leg"] == k and e["event"] == "ENTRY"] for k in VARIANTS}
    # same signal stream: every variant enters the same trades at the same bar and side
    stamps = {k: [(e["ref_time"], e["side"]) for e in v] for k, v in by_leg.items()}
    assert stamps["NOISE_422_PLAIN"] and stamps["NOISE_422_PLAIN"] == stamps["NOISE_422_FIXED"] \
        == stamps["NOISE_422_KEEL"]
    arr, full = _full_history_trades(legs["NOISE_422_PLAIN"])
    for e in by_leg["NOISE_422_PLAIN"]:
        assert e["keel_size"] == "" and e["size"] in (1.0, 1.75)
        assert e["size"] == full[str(e["ref_time"])]["size"], "plain = the backtest's own size"
        assert e["trade_id"].startswith("NOISE_422_PLAIN-")
    plain = {e["ref_time"]: e["size"] for e in by_leg["NOISE_422_PLAIN"]}
    for e in by_leg["NOISE_422_FIXED"]:
        want = float(K.fixed_tilt_sizes_v12(arr, [full[str(e["ref_time"])]["entry_bar"]])[0])
        assert e["keel_size"] == want
        assert e["size"] == pytest.approx(plain[e["ref_time"]] * want, rel=1e-12)
    for e in by_leg["NOISE_422_KEEL"]:
        assert isinstance(e["keel_size"], float) and e["keel_size"] > 0
        assert e["size"] == pytest.approx(plain[e["ref_time"]] * e["keel_size"], rel=1e-12)
    assert any(e["keel_size"] != 1.0 for e in by_leg["NOISE_422_KEEL"]), \
        "a real KEEL score, not the 1.0 fallback, must reach at least one entry"


def test_learned_shadow_leg_with_no_state_scores_one_silently_even_on_a_cloud_live_tick(
        tmp_path, monkeypatch):
    """The first session after deploy, before the keel-state service has built
    NOISE_422_KEEL: every entry sizes plugin x 1.0 and NO push goes out -- even with
    EDGELOG_HOST_ROLE=cloud and a FETCHING step (the "shadow": True guard on its own; the
    shadow runner's fetch=False is the other guard, see tests/test_shadow_legs.py)."""
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    monkeypatch.setattr(cs, "fetch_and_merge", lambda tf, paths=None, log=print: (
        cs.historical_bars(tf, paths), "webull", True))
    monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)
    home = str(tmp_path / "home")
    cfg = _shadow_cfgs(home, keel_state=False)["NOISE_422_KEEL"]
    assert not os.path.exists(cfg["keel"]["state_path"])
    _seed, events = run_session(home, {"NOISE_422_KEEL": cfg}, fetch=True)
    entries = [e for e in events if e["event"] == "ENTRY"]
    assert entries and all(e["keel_size"] == 1.0 and e["size"] in (1.0, 1.75) for e in entries)
    assert sent == []
    # ... and the SAME cfg without the shadow flag (a live leg) WOULD have paged: the
    # silence above is the flag's doing, not an accident of the fixture
    live_cfg = {k: v for k, v in cfg.items() if k != "shadow"}
    run_session(str(tmp_path / "home2"), {"NOISE_422_KEEL": live_cfg}, fetch=True)
    assert sent, "control: a live KEEL leg with no state does page"


# ── 6. real QQQ cache (skips without it) ────────────────────────────────────────────────
def _real_bar_frame():
    df = cs.load_cached_bars("5m", cs._paths(home=os.path.dirname(os.path.dirname(REAL_CACHE_5M))))
    if df is None or not len(df):
        pytest.skip("real 5m cache present but unreadable/empty")
    return df


def _now_past_the_newest_bar(df):
    newest_open = pd.Timestamp(int(df["time"].max()), unit="s", tz="UTC").tz_convert(cs.TZ)
    return newest_open + pd.Timedelta(hours=1)


@pytest.mark.skipif(not HAS_REAL_5M_CACHE, reason=_CACHE_SKIP)
def test_noise_422_runs_through_run_leg_trades_on_real_bars_and_sizes_its_trades():
    df = _real_bar_frame()
    now = _now_past_the_newest_bar(df)
    arrays = cs.closed_arrays(df, now.to_pydatetime(), "5m", cs.DEFAULT_WARMUP_SESSIONS)
    assert arrays is not None
    trades = cs.run_leg_trades(cs.SHADOW_LEGS["NOISE_422_PLAIN"], arrays, leg_key="NOISE_422_PLAIN")
    assert trades, "NOISE_1_8_CT304H.py must take at least one real trade over 60 sessions"
    for t in trades:
        assert t["size"] == pytest.approx(1.0) or t["size"] == pytest.approx(1.75), t["size"]


@pytest.mark.skipif(not HAS_REAL_5M_CACHE, reason=_CACHE_SKIP)
def test_fresh_shadow_key_cold_starts_without_an_entry_exit_burst(tmp_path):
    """A shadow key's first tick re-derives the whole window: exactly one SEED, however many
    historical trades it absorbs, and nothing on a repeat of the same tick. KEEL is taken
    off the cfg here -- SEED never scores KEEL and the box's state is not on this machine."""
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    shutil.copy(REAL_CACHE_5M, os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"))
    cfg = {k: v for k, v in cs.SHADOW_LEGS["NOISE_422_PLAIN"].items() if k != "keel"}
    legs = {"NOISE_422_PLAIN": cfg}
    df = _real_bar_frame()
    now = _now_past_the_newest_bar(df)
    events = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in events] == ["SEED"]
    leg_state = cs._load_state(paths)["legs"]["NOISE_422_PLAIN"]
    assert leg_state["seeded"] is True and len(leg_state["trades"]) > 0
    assert all(rec.get("exit_emitted") for rec in leg_state["trades"].values())
    assert cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False) == []
