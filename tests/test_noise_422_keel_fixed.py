"""tests/test_noise_422_keel_fixed.py -- the NOISE_422_FIXED shadow leg's "keel" shape
(owner 2026-09-28, api/cloud_signal.py SHADOW_LEGS): v12's fixed tilts with NO model,
dict(version="v12", mode="fixed").

Pre-registered research (docs/PREREG_keel_422_parts_2026-09-27.md RESULT,
tools/keel_422_parts_check.py arm A3) found those tilts alone beat full KEEL v12 on #422's
walk-forward return per drawdown and Sortino; the forward test of that
(docs/PREREG_noise_shadow_forward_2026-09-28.md) runs it as a shadow leg beside the live
NOISE #382 + KEEL primary. Ported from origin/prep/noise-422, where it was a dormant
go-day line on the live leg; the Webull-tab tests there are not ported (no web change here).

COVERS:
  1. augur_engine.ml_keel.fixed_tilt_sizes_v12 == the research tool's own A3 call, on the
     same inputs (a synthetic series that crosses two FOMC days, and the real NQ master
     when one is on this machine), and its constants are the tool's.
  2. cloud_signal.step() end to end with the SHIPPED NOISE_422_FIXED cfg: each ENTRY sized
     at the helper's value with no state file anywhere, and a decide_at_close probe entry
     gets exactly the full-history run's value at the real entry bar; EXIT reuses the
     ENTRY's size.
  3. No staleness push for fixed; a broken fixed score or a bad mode still falls back to
     1.0 -- and pushes only for a LIVE leg (a shadow leg never pages).
  4. tools/keel_live_state.py builds nothing for the fixed leg, stays loud for an explicit
     --leg on it or an unknown mode, and exits 0 ("nothing to build") when every KEEL leg
     is fixed.
"""
import importlib
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                       # noqa: E402
from augur_engine import ml_keel as K               # noqa: E402
from augur_engine.engine import run_backtest        # noqa: E402
import tools.keel_live_state as kls                 # noqa: E402
import test_noise_422_shadow as T422               # noqa: E402  (its synthetic series + helpers)

FIXED = dict(version="v12", mode="fixed")
A3_LINE = ('"A3 + fixed tilts only": K.compression_sizes(A, T, mult=1.5, dow=DOW, cap=cap, '
           'event=EVENT),')
TOOL_PATH = os.path.join(ROOT, "tools", "keel_422_parts_check.py")


_TOOL = []


def _research_tool():
    """tools/keel_422_parts_check.py imported as-is, ONCE, with what its import does to the
    rest of the session undone: it puts tools/ on sys.path, adds K.CFG["_v12_nocomp"] to
    the shared ml_keel.CFG, and leaves its tools-level modules (itself, keel_bag_check,
    keel_422_stack_check) in sys.modules. The module object handed back keeps working --
    only its DOW / EVENT constants are read."""
    if _TOOL:
        return _TOOL[0]
    tools_dir = os.path.join(ROOT, "tools")
    saved_path, saved_cfg, saved_mods = list(sys.path), dict(K.CFG), set(sys.modules)
    try:
        sys.path.insert(0, tools_dir)
        _TOOL.append(importlib.import_module("keel_422_parts_check"))
    finally:
        sys.path[:] = saved_path
        K.CFG.clear()
        K.CFG.update(saved_cfg)
        for name in set(sys.modules) - saved_mods:
            f = getattr(sys.modules[name], "__file__", None)
            if f and os.path.dirname(os.path.abspath(f)) == tools_dir:
                del sys.modules[name]
    return _TOOL[0]


def _a3(P, A, trades):
    """The research tool's A3 arm, written exactly as its own line (A3_LINE) reads."""
    cap = float(K.CFG["v12"]["comp"]["cap"])
    return K.compression_sizes(A, trades, mult=1.5, dow=P.DOW, cap=cap, event=P.EVENT)


# ── 1. the helper is the research arm ────────────────────────────────────────────────────
def test_fixed_constants_are_the_research_tools():
    P = _research_tool()
    # nothing of the tool's import leaks into the rest of the session
    assert "_v12_nocomp" not in K.CFG
    assert not {"keel_422_parts_check", "keel_bag_check", "keel_422_stack_check"} & set(sys.modules)
    with open(TOOL_PATH, encoding="utf-8") as f:
        assert A3_LINE in f.read(), "the research tool's A3 line moved -- re-check the helper"
    assert K.FIXED_V12_MULT == 1.5
    assert K.FIXED_V12_CAP == float(K.CFG["v12"]["comp"]["cap"]) == 3.0
    assert K.FIXED_V12_DOW == P.DOW == {"4": 1.5}
    assert K.FIXED_V12_EVENT == P.EVENT == {"mult": 0.5, "cut_hour": 14}


def test_helper_equals_research_a3_on_a_synthetic_series():
    """Every bar of a 70-session series that crosses the 2026-07-29 and 2026-09-16 FOMC
    days, as an entry, plus the #422 cell's own trades -- exactly equal, and each tilt
    really fires somewhere (compression, Friday, the cap, the FOMC half)."""
    P = _research_tool()
    A = T422._arrays_through(T422._DAYS[-1])
    n = len(A["close"])
    every = [(e, e, 0.0) for e in range(n)]
    got = K.fixed_tilt_sizes_v12(A, np.arange(n))
    np.testing.assert_array_equal(got, _a3(P, A, every))
    vals = set(np.round(got, 9))
    assert {1.0, 1.5, 2.25, 0.5, 0.75} <= vals, vals

    r = run_backtest("NOISE_1_8_CT304H.py", arrays=A, params=cs.NOISE_422_PARAMS,
                     cost_pts=0.533, return_trades=True)
    trades = sorted(r["trades"], key=lambda z: z[0])
    assert trades
    np.testing.assert_array_equal(K.fixed_tilt_sizes_v12(A, [t[0] for t in trades]),
                                  _a3(P, A, trades))
    # order-preserving: the helper answers in the order it is asked, unlike compression_sizes
    rev = [t[0] for t in trades][::-1]
    np.testing.assert_array_equal(K.fixed_tilt_sizes_v12(A, rev),
                                  _a3(P, A, trades)[::-1])
    assert len(K.fixed_tilt_sizes_v12(A, [])) == 0


def _nq_master():
    p = os.environ.get("KEEL_TEST_NQ_MASTER") or os.path.join(ROOT, "augur_uploads",
                                                              "NOADJ_NQ_5m_RTH.csv")
    return p if os.path.exists(p) else None


@pytest.mark.skipif(_nq_master() is None, reason="no NQ 5m RTH master on this machine "
                    "(set KEEL_TEST_NQ_MASTER to point at one)")
def test_helper_equals_research_a3_on_the_real_nq_master():
    P = _research_tool()
    A, _dropped = kls.load_nq_arrays(_nq_master(), date_from="2025-01-01", log=lambda *a, **k: None)
    r = run_backtest("NOISE_1_8_CT304H.py", arrays=A, params=cs.NOISE_422_PARAMS,
                     cost_pts=0.533, return_trades=True)
    trades = sorted(r["trades"], key=lambda z: z[0])
    assert len(trades) > 100
    got = K.fixed_tilt_sizes_v12(A, [t[0] for t in trades])
    np.testing.assert_array_equal(got, _a3(P, A, trades))
    assert (got < 1.0).any() and (got > 1.5).any(), "FOMC half and comp x Friday both fire"


# ── 2. step() end to end, the shipped NOISE_422_FIXED shadow cfg ─────────────────────────
def _run_fixed_session(tmp_path):
    home = str(tmp_path / "home")
    cfg = dict(cs.SHADOW_LEGS["NOISE_422_FIXED"])
    assert cfg["keel"] == FIXED
    seed, events = T422.run_session(home, {"NOISE_422_FIXED": cfg})
    assert [e["event"] for e in seed] == ["SEED"] and seed[0]["keel_size"] == ""
    return cfg, home, events


def _full_history_fixed_sizes(cfg):
    """entry_time -> the fixed tilt the full-history run gives at the REAL entry bar, from
    the whole session's closed bars (no probe, no stand-ins)."""
    end = pd.Timestamp(f"{T422._DAYS[-1]} 17:00", tz=cs.TZ).to_pydatetime()
    arr = cs.closed_arrays(T422._EPOCH, end, "5m", cs.leg_warmup_sessions(cfg))
    trades = cs.run_leg_trades(cfg, arr, leg_key="NOISE_422_FIXED")
    out = {}
    for t in trades:
        out[str(t["entry_time"])] = (float(K.fixed_tilt_sizes_v12(arr, [t["entry_bar"]])[0]),
                                     t.get("size", 1.0))
    return out


def test_noise_422_fixed_shadow_leg_through_step(tmp_path):
    cfg, home, events = _run_fixed_session(tmp_path)
    entries = [e for e in events if e["event"] == "ENTRY"]
    assert entries
    assert all(isinstance(e["keel_size"], float) and e["keel_size"] > 0 for e in entries)
    # no KEEL file was ever written or needed
    assert not os.path.exists(cs.keel_paths("NOISE_422_FIXED", "v12", home=home)["dir"])
    full = _full_history_fixed_sizes(cfg)
    probe_entries = 0
    for e in entries:
        want_keel, plugin = full[str(e["ref_time"])]
        assert e["keel_size"] == want_keel, (e, want_keel)
        assert e["size"] == pytest.approx(plugin * want_keel, rel=1e-12)
        probe_entries += cs.DECIDE_AT_CLOSE_TAG in str(e["reason"])
    assert probe_entries, "at least one entry must come from the decide_at_close probe"
    assert {e["keel_size"] for e in entries} - {1.0}, "a real tilt must reach an entry"
    # EXIT reuses the ENTRY's size
    by_tid = {e["trade_id"]: e for e in entries}
    for x in (e for e in events if e["event"] == "EXIT" and e["trade_id"] in by_tid):
        assert (x["size"], x["keel_size"]) == (by_tid[x["trade_id"]]["size"],
                                               by_tid[x["trade_id"]]["keel_size"])


def test_probe_arrays_give_the_full_history_tilt_at_the_real_entry_bar():
    """Directly: for EVERY bar D of the last session (not only the ones a trade fired
    after), the fixed tilt at stand-in S1 of the probe arrays equals the full-history
    tilt at the real D+1 bar -- including D at the end of an hourly group, where S1 opens
    a new group."""
    end = pd.Timestamp(f"{T422._DAYS[-1]} 17:00", tz=cs.TZ).to_pydatetime()
    full = cs.closed_arrays(T422._EPOCH, end, "5m", 300)
    n_full = len(full["close"])
    first_today = n_full - 78
    for d in range(first_today, n_full - 1):
        now = pd.Timestamp(full["index"][d]).to_pydatetime() + pd.Timedelta(minutes=5, seconds=10)
        closed = cs.closed_arrays(T422._EPOCH, now, "5m", 300)
        n = len(closed["close"])
        assert n == d + 1
        probe = cs._stand_in_arrays(closed, "5m")
        assert probe["index"][n] == full["index"][d + 1]
        s1 = float(K.fixed_tilt_sizes_v12(probe, [n])[0])
        real = float(K.fixed_tilt_sizes_v12(full, [d + 1])[0])
        assert s1 == real, (d, str(full["index"][d + 1]), s1, real)


# ── 3. fallbacks and pushes ─────────────────────────────────────────────────────────────
def test_fixed_mode_never_reports_staleness_and_never_pushes(monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    far = pd.Timestamp("2031-01-06 10:00", tz=cs.TZ).to_pydatetime()
    assert cs._keel_fallback_reason(FIXED, far) is None
    state = {}
    cs._maybe_push_keel_fallback("NOISE_422", FIXED, far, state)
    assert sent == [] and "keel_alerts" not in state


def test_bad_fixed_config_or_unknown_mode_falls_back_and_pushes(monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    now = pd.Timestamp("2026-09-25 10:00", tz=cs.TZ).to_pydatetime()
    A = T422._arrays_through(T422._DAYS[-1])
    for bad, why in ((dict(version="v11", mode="fixed"), "unsupported version"),
                     (dict(version="v12", mode="fixd"), "unknown keel mode")):
        ks, diag = cs._keel_size_for_entry(bad, A, 10, now.isoformat())
        assert ks == 1.0 and why in diag
        assert why in cs._keel_fallback_reason(bad, now)
        cs._maybe_push_keel_fallback("NOISE_422", bad, now, {})
    assert len(sent) == 2
    # an entry_bar outside the arrays falls back with its reason, never clamped and scored
    for out_of_range in (-1, len(A["close"])):
        ks, diag = cs._keel_size_for_entry(FIXED, A, out_of_range, now.isoformat())
        assert ks == 1.0 and "out of range" in diag


def test_hand_typed_near_misses_fall_back_and_never_raise(monkeypatch):
    """The go-day operation is typing ONE line by hand, so its likeliest slips: a keel dict
    with no mode and no paths (reads as learned, has no state file), a misspelt "mode"
    KEY (same), and a keel value that is not a dict at all. Each sizes 1.0 with a reason,
    reports the same reason to the push check, and _diff_leg still emits the ENTRY --
    never a KeyError out of step(), which would stop every leg's tick."""
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    A = T422._arrays_through(T422._DAYS[-1])
    bar = len(A["close"]) - 10
    now = pd.Timestamp(A["index"][bar]).to_pydatetime() + pd.Timedelta(minutes=5)
    for bad, why in ((dict(version="v12"), "keel config has no state_path"),
                     (dict(version="v12", mod="fixed"), "keel config has no state_path"),
                     (True, "unknown keel mode '?'")):
        ks, diag = cs._keel_size_for_entry(bad, A, bar, now.isoformat())
        assert (ks, diag) == (1.0, why)
        assert cs._keel_fallback_reason(bad, now) == why
        ev = cs._diff_leg("NOISE_422", [_one_new_entry(A, bar)], {"seeded": True, "trades": {}},
                          now, max_entry_age_sec=900, cfg={"keel": bad}, arrays=A, fetch=True,
                          log=lambda *a, **k: None)
        # the same slip on a SHADOW leg: same 1.0 fallback, never a push
        ev_sh = cs._diff_leg("NOISE_422", [_one_new_entry(A, bar)], {"seeded": True, "trades": {}},
                             now, max_entry_age_sec=900, cfg={"keel": bad, "shadow": True},
                             arrays=A, fetch=True, log=lambda *a, **k: None)
        assert ev_sh[0]["keel_size"] == 1.0
        assert [e["event"] for e in ev] == ["ENTRY"]
        assert ev[0]["keel_size"] == 1.0 and ev[0]["size"] == 1.75
    assert len(sent) == 3 and all("no state_path" in m or "unknown keel mode" in m for m in sent)


def _one_new_entry(A, bar):
    return {"entry_time": pd.Timestamp(A["index"][bar]).isoformat(), "side": "long",
            "entry_px": 700.0, "shares": 1, "still_open": True, "exit_time": None,
            "exit_px": None, "entry_bar": bar, "size": 1.75}


def test_fixed_scoring_error_is_one_point_zero_with_the_learned_paths_push(monkeypatch):
    """A fixed score that blows up at entry time: size = plugin x 1.0, and the same
    once-a-day "KEEL fell back to 1.0" push the learned path sends (cloud box, live tick)."""
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append((msg, title)))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)

    def boom(*a, **k):
        raise ValueError("synthetic")
    monkeypatch.setattr(K, "fixed_tilt_sizes_v12", boom)
    A = T422._arrays_through(T422._DAYS[-1])
    bar = len(A["close"]) - 10
    t = _one_new_entry(A, bar)
    now = pd.Timestamp(t["entry_time"]).to_pydatetime() + pd.Timedelta(minutes=5)
    leg_state = {"seeded": True, "trades": {}}
    ev = cs._diff_leg("NOISE_422", [t], leg_state, now, max_entry_age_sec=900,
                      cfg={"keel": dict(FIXED)}, arrays=A, fetch=True, log=lambda *a, **k: None)
    assert [e["event"] for e in ev] == ["ENTRY"]
    assert ev[0]["keel_size"] == 1.0 and ev[0]["size"] == 1.75
    assert len(sent) == 1 and "keel fixed tilts error" in sent[0][0]
    assert "KEEL fell back to 1.0" in sent[0][1]
    # the shipped NOISE_422_FIXED cfg is a SHADOW leg: same 1.0 fallback, no push at all
    ev = cs._diff_leg("NOISE_422_FIXED", [t], {"seeded": True, "trades": {}}, now,
                      max_entry_age_sec=900, cfg=cs.SHADOW_LEGS["NOISE_422_FIXED"], arrays=A,
                      fetch=True, log=lambda *a, **k: None)
    assert ev[0]["keel_size"] == 1.0 and len(sent) == 1


def test_fixed_scoring_at_entry_matches_the_helper_without_a_push(monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    A = T422._arrays_through(T422._DAYS[-1])
    bar = len(A["close"]) - 10
    t = _one_new_entry(A, bar)
    now = pd.Timestamp(t["entry_time"]).to_pydatetime() + pd.Timedelta(minutes=5)
    ev = cs._diff_leg("NOISE_422", [t], {"seeded": True, "trades": {}}, now,
                      max_entry_age_sec=900, cfg={"keel": dict(FIXED)}, arrays=A, fetch=True)
    want = float(K.fixed_tilt_sizes_v12(A, [bar])[0])
    assert ev[0]["keel_size"] == want and ev[0]["size"] == pytest.approx(1.75 * want)
    assert sent == []


# ── 4. the nightly KEEL build ───────────────────────────────────────────────────────────
def test_keel_live_state_builds_nothing_for_the_fixed_leg():
    assert "NOISE_422_FIXED" not in [l["leg_key"] for l in kls.resolve_legs()]
    with pytest.raises(kls.LegResolutionError, match="not a learned model"):
        kls.resolve_leg("NOISE_422_FIXED")


def test_keel_live_state_default_exits_zero_when_every_keel_leg_is_fixed(tmp_path, monkeypatch, capsys):
    fix = lambda legs: {k: (dict(v, keel=dict(FIXED)) if v.get("keel") else v)   # noqa: E731
                        for k, v in legs.items()}
    monkeypatch.setattr(cs, "CROWN_LEGS", fix(cs.CROWN_LEGS))
    monkeypatch.setattr(cs, "SHADOW_LEGS", fix(cs.SHADOW_LEGS))
    with pytest.raises(kls.NothingToBuild, match="fixed tilts"):
        kls.resolve_legs()
    old_argv = sys.argv
    # the box unit's own argv; the NQ file need not even exist -- nothing is read
    sys.argv = ["keel_live_state.py", "--nq-file", str(tmp_path / "missing.csv"),
                "--out-dir", str(tmp_path / "out"), "--defer-in-session"]
    try:
        monkeypatch.setattr(kls, "should_defer_in_session", lambda now: False)
        assert kls.main() is None          # returns -> exit status 0
    finally:
        sys.argv = old_argv
    out = capsys.readouterr().out
    assert "use v12's fixed tilts (no model) -- nothing to build" in out
    assert not (tmp_path / "out").exists()


def test_keel_live_state_stays_loud_for_a_bad_live_mode_and_drops_a_bad_shadow_one():
    bad = dict(cs.SHADOW_LEGS, NOISE_422_FIXED=dict(cs.SHADOW_LEGS["NOISE_422_FIXED"],
                                                    keel=dict(version="v12", mode="fixd")))
    # a shadow typo never blocks the live build: that leg is dropped (logged), the rest build
    assert [l["leg_key"] for l in kls.resolve_legs(shadow_legs=bad)] == ["NOISE_382", "NOISE_422_KEEL"]
    bad_live = dict(cs.CROWN_LEGS, NOISE_382=dict(cs.CROWN_LEGS["NOISE_382"],
                                                  keel=dict(version="v12", mode="fixd")))
    with pytest.raises(kls.LegResolutionError, match="unknown keel mode"):
        kls.resolve_legs(crown_legs=bad_live)
    # a learned leg next to a fixed one: the learned one is built, the fixed one ignored
    mixed = {"A": {"strategy": "a.py", "keel": {"version": "v12"}},
             "B": {"strategy": "b.py", "keel": dict(FIXED)}}
    assert [l["leg_key"] for l in kls.resolve_legs(crown_legs=mixed, shadow_legs={})] == ["A"]
