"""tests/test_noise_422_switch.py -- OWNER DECISION 2026-09-27 (via MANAGER): swap the
Webull paper book's NOISE leg from NOISE #382 + KEEL v12 to NOISE #422 + KEEL v12.
NOISE #422 = NOISE_1_8_CT304H.py (the #304 crown's own core, frozen literally inside the
file, sized by the HOURLY squeeze -- frame frozen at 60 inside the file) at run #422's
crowned cell {"gate_len": 20, "gate_ratio": 1.15, "tilt_mult": 1.75} (NOISE.md "NOISE #422
(NOISE-55, CT304H)"). Same trades as #382, sized by the hourly squeeze instead of the
30-minute one. Modelled on tests/test_noise_382_switch.py (the #304 -> #382 swap), which
now keeps run #382's leg as history.

COVERS:
  1. CROWN_LEGS carries NOISE_422 and NOT NOISE_382 (replaced, never doubled -- two NOISE
     engine keys would each emit their own ENTRY and double every NOISE order), with
     every field NOISE_382 carried: 5m, the same warm-up, decide_at_close, KEEL v12 under
     NOISE_422's own file names.
  2. The cell is admissible in NOISE_1_8_CT304H.py's OWN fence (and a one-step-off value
     is refused), and the file trades a synthetic series through the engine with sizes
     {1.0, 1.75} only.
  3. The two live-engine hooks NOISE_1_8_CT304.py gained on 2026-09-26, now also on
     CT304H: the REQUIRED_LOOKBACK_SESSIONS re-export (-> the 262-session live window)
     and the vol_prior_ranges pass-through -- proved to reach NOISE_1_0.py's
     _vol_percentile, and to change nothing when absent.
  4. api/qqq_exec.py's ENGINE_LEG_MAP maps NOISE_422, NOISE_382 and NOISE_304 all to
     "NOISE", and the reverse lookup picks the LIVE key.
  5. tools/keel_live_state.py builds NOISE_422 by default on the learned line, and does
     the right thing for whichever of the three "keel" lines is live in the file.
  6. The leg end to end through cloud_signal.step(), WITH and WITHOUT the "keel" key --
     the no-KEEL alternative MANAGER may choose is a one-line delete of that key, so both
     shapes are exercised: sizes, keel_size column, the KEEL status the tab reads, and
     what the nightly KEEL build does in each case.
  7. On the owner's real QQQ 5m cache (skips cleanly without it): the leg trades and
     sizes through run_leg_trades, and a fresh NOISE_422 key cold-starts with one SEED.
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
import tools.keel_live_state as kls                 # noqa: E402

NOISE_422_PARAMS = {"gate_len": 20, "gate_ratio": 1.15, "tilt_mult": 1.75}
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


def _learned_crown_legs():
    """CROWN_LEGS with NOISE_422 on the LEARNED go-day line, whichever of the three lines
    (api/cloud_signal.py's THREE SHAPES) is live in the file. The build tests here are about
    the learned build itself; which line is live is checked by
    test_noise_422_leg_carries_every_field_noise_382_did and
    test_nightly_keel_build_on_the_line_that_is_live_now below, so these must not go red
    when MANAGER picks the fixed or the no-KEEL line."""
    return dict(cs.CROWN_LEGS, NOISE_422=dict(
        cs.CROWN_LEGS["NOISE_422"], keel=dict(version="v12", **cs.keel_paths("NOISE_422", "v12"))))


def _arrays_through(day, n_sessions=300):
    now = pd.Timestamp(f"{day} 17:00", tz=cs.TZ).to_pydatetime()
    return cs.closed_arrays(_EPOCH, now, "5m", n_sessions)


# ── 1. CROWN_LEGS: replaced, not doubled ─────────────────────────────────────────────────
def test_crown_legs_carry_noise_422_and_not_noise_382():
    assert "NOISE_422" in cs.CROWN_LEGS
    assert "NOISE_382" not in cs.CROWN_LEGS and "NOISE_304" not in cs.CROWN_LEGS
    noise_keys = [k for k in cs.CROWN_LEGS if qe.ENGINE_LEG_MAP.get(k) == "NOISE"]
    assert noise_keys == ["NOISE_422"], (
        "exactly ONE live engine key may feed the NOISE exec leg -- two would each emit "
        "an ENTRY for the same trade and double every NOISE order; got %r" % noise_keys)


def test_noise_422_leg_carries_every_field_noise_382_did():
    leg = cs.CROWN_LEGS["NOISE_422"]
    assert leg["strategy"] == "NOISE_1_8_CT304H.py"
    assert leg["timeframe"] == "5m"
    assert leg["params"] == NOISE_422_PARAMS == cs.NOISE_422_PARAMS
    assert "gate_tf_min" not in leg["params"], "the file freezes the frame at 60 itself"
    assert leg["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS
    assert leg["decide_at_close"] is True
    # "keel" is whichever of the THREE SHAPES (cloud_signal, above keel_paths) MANAGER put
    # live on go day -- each passes here exactly as written, and nothing else does
    mode = cs.keel_mode(leg.get("keel"))
    if mode == cs.KEEL_MODE_LEARNED:
        assert leg["keel"] == dict(version="v12", **cs.keel_paths("NOISE_422", "v12"))
        assert os.path.basename(leg["keel"]["state_path"]) == "NOISE_422_v12_state.joblib"
        assert os.path.basename(leg["keel"]["summary_path"]) == "NOISE_422_v12_summary.json"
    elif mode == cs.KEEL_MODE_FIXED:
        assert leg["keel"] == dict(version="v12", mode="fixed")
    else:
        assert "keel" not in leg, ("not one of the three go-day lines", leg.get("keel"))
    # the SAME keys as run #382's leg had -- nothing dropped, nothing new ("keel" only
    # when a KEEL line is live)
    assert set(leg) - {"keel"} == {"strategy", "timeframe", "params", "warmup_sessions",
                                   "decide_at_close"}
    # run #382's cell stays importable (history tools, --leg NOISE_382)
    assert cs.NOISE_382_PARAMS == {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16,
                                   "gate_ratio": 1.15}


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
    assert cs.leg_warmup_sessions(cs.CROWN_LEGS["NOISE_422"]) == 262
    assert cs._leg_accepts_vol_prior_ranges("NOISE_1_8_CT304H.py") is True


def test_vol_prior_ranges_reaches_noise_1_0_through_ct304h():
    """End to end down the REAL chain CT304H -> NOISE_1_1_NBHD -> NOISE_1_0: the kwarg
    the live engine passes arrives at NOISE_1_0.py's _vol_percentile as prior_ranges.
    Before the 2026-09-27 swap CT304H had no pass-through, so this arrived as nothing
    while _leg_accepts_vol_prior_ranges (which reads only the bottom module's signature)
    still said yes."""
    ct304h = _load_fresh("NOISE_1_8_CT304H.py", "t422_ct304h_vpr")
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
    vol_prior_ranges key at all (additive, not defaulting), and the result is
    byte-identical to calling NOISE_1_1_NBHD directly with CT304H's frozen core."""
    ct304h = _load_fresh("NOISE_1_8_CT304H.py", "t422_ct304h_absent")
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


# ── 4. qqq_exec's leg map ────────────────────────────────────────────────────────────────
def test_engine_leg_map_maps_live_and_retired_noise_keys_to_noise():
    for k in ("NOISE_422", "NOISE_382", "NOISE_304"):
        assert qe.ENGINE_LEG_MAP[k] == "NOISE", k
    assert qe._engine_key_for_leg("NOISE", cs) == "NOISE_422"


def test_engine_mark_price_resolves_through_the_live_noise_422_key(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    pd.DataFrame({"time": [1_758_000_000, 1_758_000_300], "open": [700.0, 701.0],
                  "high": [700.5, 701.5], "low": [699.5, 700.5], "close": [700.25, 701.4],
                  "volume": [1000.0, 1000.0]}).to_csv(
        os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    px, src = qe._engine_mark_price("NOISE")
    assert px == pytest.approx(701.4) and src == "engine_cache"
    assert qe._leg_timeframe_seconds("NOISE") == 300


# ── 5. the nightly KEEL build follows the live leg ──────────────────────────────────────
def test_keel_live_state_resolves_noise_422_by_default(monkeypatch):
    """On the learned line (pinned here -- see _learned_crown_legs)."""
    monkeypatch.setattr(cs, "CROWN_LEGS", _learned_crown_legs())
    leg = kls.resolve_leg()
    assert leg["leg_key"] == "NOISE_422"
    assert leg["strategy"] == "NOISE_1_8_CT304H.py"
    assert leg["params"] == cs.NOISE_422_PARAMS
    assert leg["version"] == "v12" and leg["live"] is True


def test_nightly_keel_build_on_the_line_that_is_live_now():
    """The LIVE line itself, in whichever of the three shapes it is: learned -> the
    nightly build resolves NOISE_422; fixed -> NothingToBuild (main() exits 0, the units
    stay green); none -> refuses loudly ("found 0" -- disable the two units, see
    deploy/cloud/README.md)."""
    mode = cs.keel_mode(cs.CROWN_LEGS["NOISE_422"].get("keel"))
    if mode == cs.KEEL_MODE_LEARNED:
        assert kls.resolve_leg()["leg_key"] == "NOISE_422"
    elif mode == cs.KEEL_MODE_FIXED:
        with pytest.raises(kls.NothingToBuild, match="NOISE_422"):
            kls.resolve_leg()
    else:
        with pytest.raises(kls.LegResolutionError, match="found 0"):
            kls.resolve_leg()


# ── 6. end to end through step(), with and without the "keel" key ───────────────────────
def _write_keel_state(home):
    """A real fitted KEEL v12 state from the #422 cell's own trades on the synthetic
    series, under the file names keel_paths(NOISE_422) reads, dated like a fresh build."""
    arr = _arrays_through(_DAYS[-2])
    res = run_backtest("NOISE_1_8_CT304H.py", arrays=arr, params=cs.NOISE_422_PARAMS,
                       cost_pts=0.533, return_trades=True)
    state = K.keel_build_state(arr, res["trades"], version="v12")
    kp = cs.keel_paths("NOISE_422", "v12", home=home)
    os.makedirs(kp["dir"], exist_ok=True)
    import joblib
    joblib.dump(state, kp["state_path"])
    with open(kp["summary_path"], "w", encoding="utf-8") as f:
        json.dump({"version": "v12", "data_through": str(_DAYS[-2]), "n_trades": state["n"],
                   "last_nq_session": str(_DAYS[-2])}, f)
    return dict(version="v12", **kp)


@pytest.mark.parametrize("with_keel", [True, False], ids=["keel", "no_keel"])
def test_noise_422_leg_end_to_end_with_and_without_keel(tmp_path, monkeypatch, with_keel):
    """The shipped cfg (decide_at_close probe, 262-session window sizing, the size
    contract) through step() over one session, bar by bar, from a cold SEED. WITH the
    "keel" key: every ENTRY carries a real keel_size and size = plugin size x keel_size,
    the tab's KEEL status reads the NOISE_422 summary, and the nightly build resolves
    NOISE_422. WITHOUT it (MANAGER's no-KEEL option = delete that one key): keel_size is
    blank, size is the plugin's own 1.0/1.75, there is no KEEL status, and the nightly
    build refuses loudly rather than build a state nobody reads."""
    home = str(tmp_path / "home")
    paths = cs._paths(home=home)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _EPOCH.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)

    cfg = dict(cs.CROWN_LEGS["NOISE_422"])
    if with_keel:
        cfg["keel"] = _write_keel_state(home)
    else:
        cfg.pop("keel", None)   # already absent when the no-KEEL line is the live one
    legs = {"NOISE_422": cfg}
    monkeypatch.setattr(cs, "CROWN_LEGS", dict(cs.CROWN_LEGS, NOISE_422=cfg))

    seed = cs.step(now=pd.Timestamp(f"{_DAYS[-2]} 17:00", tz=cs.TZ).to_pydatetime(),
                   legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in seed] == ["SEED"]
    events = []
    for b in range(1, 79):
        now = pd.Timestamp(f"{_DAYS[-1]} 09:30", tz=cs.TZ) + pd.Timedelta(minutes=5 * b, seconds=10)
        events += cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)
    entries = [e for e in events if e["event"] == "ENTRY"]
    assert entries, "the synthetic session must produce at least one NOISE_422 entry"
    assert all(e["leg"] == "NOISE_422" and e["trade_id"].startswith("NOISE_422-") for e in events)
    plugin_sizes = set()
    for e in entries:
        if with_keel:
            assert isinstance(e["keel_size"], float) and e["keel_size"] > 0
            plugin = e["size"] / e["keel_size"]
        else:
            assert e["keel_size"] == ""
            plugin = e["size"]
        plugin_sizes.add(round(plugin, 9))
    assert plugin_sizes <= {1.0, 1.75}, plugin_sizes
    if with_keel:
        assert any(e["keel_size"] != 1.0 for e in entries), \
            "a real score, not the 1.0 fallback, must reach at least one entry"

    status = qe._build_keel_status(log=lambda *a, **k: None)
    if with_keel:
        assert status["NOISE"]["version"] == "v12"
        assert status["NOISE"]["trained_through"] == str(_DAYS[-2])
        assert kls.resolve_leg()["leg_key"] == "NOISE_422"
    else:
        assert status == {}
        with pytest.raises(kls.LegResolutionError, match="found 0"):
            kls.resolve_leg()


# ── 7. real QQQ cache (skips without it) ────────────────────────────────────────────────
def _real_bar_frame():
    df = cs.load_cached_bars("5m", cs.DEFAULT_PATHS)
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
    trades = cs.run_leg_trades(cs.CROWN_LEGS["NOISE_422"], arrays, leg_key="NOISE_422")
    assert trades, "NOISE_1_8_CT304H.py must take at least one real trade over 60 sessions"
    for t in trades:
        assert t["size"] == pytest.approx(1.0) or t["size"] == pytest.approx(1.75), t["size"]


@pytest.mark.skipif(not HAS_REAL_5M_CACHE, reason=_CACHE_SKIP)
def test_fresh_noise_422_key_cold_starts_without_an_entry_exit_burst(tmp_path):
    """NOISE_422 has never existed as an engine key, so its first tick after the switch
    re-derives the whole window: exactly one SEED, however many historical trades it
    absorbs, and nothing on a repeat of the same tick. KEEL is taken off the cfg here --
    SEED never scores KEEL (tests/test_cloud_signal_keel.py) and the box's state is not
    on this machine."""
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    shutil.copy(REAL_CACHE_5M, os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"))
    cfg = {k: v for k, v in cs.CROWN_LEGS["NOISE_422"].items() if k != "keel"}
    legs = {"NOISE_422": cfg}
    df = _real_bar_frame()
    now = _now_past_the_newest_bar(df)
    events = cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False)
    assert [e["event"] for e in events] == ["SEED"]
    leg_state = cs._load_state(paths)["legs"]["NOISE_422"]
    assert leg_state["seeded"] is True and len(leg_state["trades"]) > 0
    assert all(rec.get("exit_emitted") for rec in leg_state["trades"].values())
    assert cs.step(now=now.to_pydatetime(), legs=legs, paths=paths, fetch=False) == []
