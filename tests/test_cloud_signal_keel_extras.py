"""tests/test_cloud_signal_keel_extras.py -- KEEL ENTRY EXTRAS + the KEEL SIZE DIFF ALERT
(api/cloud_signal.py, 2026-10-05, MANAGER #76).

COVERS:
  1. augur_engine.ml_keel.keel_branch names the branch keel_score_from_state really took, with
     t_fast just above and just below the shade line (and the size proves it), plus warm-up
     and the fallback reason string.
  2. _diff_leg: a LEARNED KEEL leg's ENTRY row carries keel_branch / keel_fixed_size /
     keel_t_fast / keel_trust / keel_score from the same score; the EXIT row and every other
     leg (no KEEL, fixed-mode KEEL) get no such keys; a failure blanks only the field it hit.
  3. NO BEHAVIOUR CHANGE: a whole fixture day stepped with the extras on and off writes the
     same signal rows (every decision / size column) and the same state.json.
  4. The diff alert: once per entry (a re-run tick or a second note never repeats it), never
     for a shadow leg, never on equal sizes, never off the box or on an offline tick; the
     jsonl record and the push carry the entry's figures; the file stays bounded; a
     fallback-1.0 difference is recorded but not pushed (the fallback alert pages it).
  5. Review 10-05: the extras reuse the score's own keel_features (no second pass on the
     entry path); a stream-committed entry notes once -- one push (in the background), one
     record -- and the following step() on the same tick adds neither.
"""
import csv
import json
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import api.cloud_signal as cs  # noqa: E402
import api.cloud_signal_stream as css  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
from _threadwait import wait_for  # noqa: E402
from test_cloud_signal_keel import _arrays, _fitted_state, _write_state, _sizing_cfg  # noqa: E402

DAY = "2026-09-08"        # a Tuesday session


# ── a fitted state whose model really leans (so trust / shade both reachable) ────────────
_STATE_CACHE = {}


def _base_state():
    if "s" not in _STATE_CACHE:
        arrays = _arrays(n_bars=400, seed=7)
        state, _ = _fitted_state(arrays, n_trades=120)
        _STATE_CACHE["s"] = (arrays, state)
    return _STATE_CACHE["s"]


def _leaning_state(shade_t):
    """The fitted state with a rule that always trusts the model (equal stack, trust and fast
    bounds far below any t) and the shade line at `shade_t` -- so which branch fires depends
    only on t_fast vs `shade_t`, exactly the comparison under test."""
    arrays, state = _base_state()
    s = dict(state)
    c = dict(state["cfg"])
    c["stack"] = "equal"
    c["t_lo"], c["t_hi"] = -100.0, -99.0
    c["fast"] = dict(c["fast"], lo=-100.0, hi=-99.0)
    c["shade"] = dict(c["shade"], t=float(shade_t))
    s["cfg"] = c
    return arrays, s


# ── 1. keel_branch matches the rule ──────────────────────────────────────────────────────
@pytest.mark.parametrize("side", ["below", "above"])
def test_branch_label_matches_the_rule_either_side_of_the_shade_line(side):
    arrays, state = _base_state()
    t_fast = float(state["t_fast_now"])
    # t_fast BELOW the line -> shade; ABOVE it -> the trust branch
    line = t_fast + 0.01 if side == "below" else t_fast - 0.01
    arrays, s = _leaning_state(line)
    c = s["cfg"]
    for bar in (390, 395):
        size, diag = K.keel_score_from_state(s, arrays, bar)
        assert diag["t_fast"] == pytest.approx(t_fast)
        assert diag["z"] != 0 and diag["trust"] > 0
        fixed = float(K.fixed_tilt_sizes_v12(arrays, [bar])[0])
        branch = K.keel_branch(diag, c)
        if side == "below":
            assert branch == K.KEEL_BRANCH_SHADE
            expect = np.clip(1.0 - c["shade"]["k"] * diag["z"], c["shade"]["lo"], c["shade"]["hi"])
        else:
            assert branch == K.KEEL_BRANCH_TRUST
            expect = np.clip(1.0 + c["K"] * diag["trust"] * diag["z"], c["LO"], c["HI"])
        assert size == pytest.approx(min(expect * fixed, 3.0), abs=1e-9)


def test_branch_fixed_only_when_the_model_leans_nothing_and_equals_the_fixed_size():
    """The real v12 rule on this fixture: member trusts are 0, so z = 0 -> the shade test
    (z != 0) fails even below the line and the model part is 1.0: fixed-only, and the size
    is exactly the fixed tilts' (seen on the box 10-05 for NOISE_382)."""
    arrays, state = _base_state()
    for bar in (390, 395):
        size, diag = K.keel_score_from_state(state, arrays, bar)
        assert diag["t_fast"] < state["cfg"]["shade"]["t"]   # below the line ...
        assert diag["z"] == 0                                # ... but nothing to shade
        assert K.keel_branch(diag, state["cfg"]) == K.KEEL_BRANCH_FIXED_ONLY
        assert size == pytest.approx(float(K.fixed_tilt_sizes_v12(arrays, [bar])[0]))


def test_branch_warmup_and_fallback():
    assert K.keel_branch({"nd": K.MIN_HISTORY - 1, "z": float("nan"), "trust": 0.0,
                          "t_fast": None}, K.CFG["v12"]) == K.KEEL_BRANCH_FIXED_ONLY
    assert K.keel_branch("keel state unavailable", K.CFG["v12"]) == K.KEEL_BRANCH_FALLBACK
    assert K.keel_branch(None, K.CFG["v12"]) == K.KEEL_BRANCH_FALLBACK


# ── 2. _diff_leg rows ────────────────────────────────────────────────────────────────────
def _diff_arrays():
    """400 bars whose bars 390-394 are 09:30-09:50 on DAY: the entry lands inside a session
    (an entry first seen after the close is never emitted)."""
    base = pd.Timestamp(f"{DAY} 09:30:00", tz=cs.TZ) - pd.Timedelta(minutes=5 * 390)
    return _arrays(n_bars=400, seed=7, base=base)


def _learned_cfg(tmp_path, shade_t=None):
    if shade_t is None:
        _a, state = _base_state()
    else:
        _a, state = _leaning_state(shade_t)
    return _diff_arrays(), _write_state(tmp_path, state, data_through="2026-09-04",
                                        name=f"NOISE_382_v12_{abs(hash(shade_t)) % 10**6}")


def _two_ticks(arrays, keel_cfg, leg="NOISE_382"):
    """Seed on one open trade, then a tick that discovers a new entry (closed in the same
    call -> ENTRY + EXIT). Returns the second tick's events."""
    leg_state = {"trades": {}}
    open_trade = (300, 399, 3.0, 1, 700.0)
    cfg0 = _sizing_cfg([open_trade], size=1.0, cost=0.0, keel_cfg=keel_cfg)
    cs._diff_leg(leg, cs.run_leg_trades(cfg0, arrays, leg_key=leg), leg_state,
                 arrays["index"][301], cfg=cfg0, arrays=arrays, fetch=False)
    new_trade = (390, 393, -1.0, 1, float(arrays["close"][390]))
    cfg1 = _sizing_cfg([open_trade, new_trade], size=1.0, cost=0.0, keel_cfg=keel_cfg)
    return cs._diff_leg(leg, cs.run_leg_trades(cfg1, arrays, leg_key=leg), leg_state,
                        arrays["index"][394], cfg=cfg1, arrays=arrays, fetch=False,
                        max_entry_age_sec=10 ** 9)


def test_learned_entry_row_carries_the_extras_from_the_same_score(tmp_path):
    arrays, state = _base_state()
    t_fast = float(state["t_fast_now"])
    arrays, keel_cfg = _learned_cfg(tmp_path, shade_t=t_fast + 0.01)
    events = _two_ticks(arrays, keel_cfg)
    entry = [e for e in events if e["event"] == "ENTRY"][0]
    exit_ = [e for e in events if e["event"] == "EXIT"][0]
    ks, diag = cs._keel_size_for_entry(keel_cfg, arrays, 390, entry["ref_time"])
    assert entry["keel_size"] == pytest.approx(ks)
    assert entry["keel_branch"] == "shade"
    assert entry["keel_t_fast"] == pytest.approx(diag["t_fast"], abs=1e-6)
    assert entry["keel_trust"] == pytest.approx(diag["trust"], abs=1e-6)
    assert entry["keel_score"] == pytest.approx(diag["z"], abs=1e-6)
    fixed, _ = cs._keel_fixed_size_for_entry({"version": "v12", "mode": "fixed"}, arrays, 390)
    assert entry["keel_fixed_size"] == pytest.approx(fixed)
    assert not any(k in exit_ for k in cs.KEEL_EXTRA_COLS), "extras ride on the ENTRY row only"


def test_no_extras_keys_on_a_plain_or_fixed_mode_leg(tmp_path):
    arrays = _diff_arrays()
    for keel_cfg in (None, {"version": "v12", "mode": "fixed"}):
        events = _two_ticks(arrays, keel_cfg, leg="NOISE_422_FIXED")
        entry = [e for e in events if e["event"] == "ENTRY"][0]
        assert not any(k in entry for k in cs.KEEL_EXTRA_COLS)


def test_a_failing_fixed_size_blanks_only_that_field(tmp_path, monkeypatch):
    arrays, keel_cfg = _learned_cfg(tmp_path)
    ref = _two_ticks(arrays, keel_cfg)
    ref_entry = [e for e in ref if e["event"] == "ENTRY"][0]

    real = K.fixed_tilt_sizes_v12
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("tilts exploded")
    monkeypatch.setattr(K, "fixed_tilt_sizes_v12", boom)
    events = _two_ticks(arrays, keel_cfg)
    entry = [e for e in events if e["event"] == "ENTRY"][0]
    assert calls["n"] >= 1
    assert entry["keel_fixed_size"] == ""
    assert entry["keel_branch"] == ref_entry["keel_branch"] != ""
    for k in ("size", "keel_size", "shares", "ref_price", "trade_id", "side"):
        assert entry[k] == ref_entry[k]
    monkeypatch.setattr(K, "fixed_tilt_sizes_v12", real)

    monkeypatch.setattr(K, "keel_branch", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    events = _two_ticks(arrays, keel_cfg)
    entry = [e for e in events if e["event"] == "ENTRY"][0]
    assert entry["keel_branch"] == "" and entry["keel_t_fast"] == ""
    assert entry["keel_fixed_size"] == ref_entry["keel_fixed_size"]
    for k in ("size", "keel_size", "shares", "ref_price", "trade_id"):
        assert entry[k] == ref_entry[k]


# ── 3. a whole fixture day: extras on vs off ─────────────────────────────────────────────
def _day_bars(seed=11):
    rng = np.random.RandomState(seed)
    base = pd.Timestamp(f"{DAY} 09:30:00", tz=cs.TZ)
    times = [base + pd.Timedelta(minutes=5 * i) for i in range(78)]
    px, rows = 700.0, []
    for t in times:
        o = px
        px += rng.normal(0, 0.6)
        rows.append({"time": int(t.tz_convert("UTC").timestamp()), "open": o,
                     "high": max(o, px) + 0.2, "low": min(o, px) - 0.2, "close": px,
                     "volume": 1000.0})
    return pd.DataFrame(rows), times


def _every_half_hour_stub():
    """Long at every :00/:30 bar from 10:00, held two bars (open at the window's end)."""
    mod = types.ModuleType("keel_extras_day_stub")
    mod.STRATEGY_NAME = "KEEL_EXTRAS_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        idx = pd.DatetimeIndex(index)
        n = len(closes)
        trades = []
        for i in range(n):
            ts = idx[i]
            if ts.minute % 30 or ts.hour < 10:
                continue
            x = min(i + 2, n - 1)
            trades.append((i, x, float(closes[x] - closes[i]), 1, float(closes[i])))
        return {"trades": trades if return_trades else None, "num_trades": len(trades),
                "total_pnl": 0.0, "win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "avg_pnl": 0, "wins": 0, "losses": 0}
    mod.run_backtest = run_backtest
    return mod


def _day_legs(keel_cfg, shadow=False):
    cfg = {"strategy": _every_half_hour_stub(), "timeframe": "5m", "params": {},
           "warmup_sessions": 1, "keel": keel_cfg}
    if shadow:
        cfg["shadow"] = True
    return {"NOISE_382": cfg}


def _ticks(times):
    return [(t + pd.Timedelta(minutes=5, seconds=6)).to_pydatetime() for t in times]


def _rows(paths):
    with open(paths["signals_path"], encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _run_day(home, legs, epoch_df, times, fetch=False):
    paths = cs._paths(home=home)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    for now in _ticks(times):
        cs.step(now=now, legs=legs, paths=paths, fetch=fetch)
    return paths


def test_whole_day_with_and_without_the_extras_decides_and_sizes_the_same(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    arrays, state = _base_state()
    _a, lean = _leaning_state(float(state["t_fast_now"]) + 0.01)     # the shade branch
    keel_cfg = _write_state(tmp_path, lean, data_through="2026-09-04", name="DAY_v12")
    epoch_df, times = _day_bars()

    monkeypatch.setattr(cs, "KEEL_ENTRY_EXTRAS", True)
    p_on = _run_day(str(tmp_path / "on"), _day_legs(keel_cfg), epoch_df, times)
    monkeypatch.setattr(cs, "KEEL_ENTRY_EXTRAS", False)
    p_off = _run_day(str(tmp_path / "off"), _day_legs(keel_cfg), epoch_df, times)

    on, off = _rows(p_on), _rows(p_off)
    entries_on = [r for r in on if r["event"] == "ENTRY"]
    assert len(entries_on) >= 5, "fixture: expected a day of entries"
    assert all(r["keel_branch"] == "shade" and r["keel_fixed_size"] != "" for r in entries_on)
    assert any(abs(float(r["keel_size"]) - 1.0) > 0.01 for r in entries_on), \
        "fixture: KEEL must really size something, or the comparison proves nothing"
    assert all(r[c] == "" for r in off for c in cs.KEEL_EXTRA_COLS)

    keep = [c for c in cs.SIGNAL_COLS if c != "emitted_at" and c not in cs.KEEL_EXTRA_COLS]
    assert [{c: r[c] for c in keep} for r in on] == [{c: r[c] for c in keep} for r in off]
    with open(p_on["state_path"], encoding="utf-8") as f:
        s_on = json.load(f)
    with open(p_off["state_path"], encoding="utf-8") as f:
        s_off = json.load(f)
    assert s_on == s_off


# ── 4. the diff alert ────────────────────────────────────────────────────────────────────
def _entry(leg="NOISE_382", t="2026-10-06T10:05:00-04:00", ks=0.62, fs=1.5, branch="shade"):
    return {"event": "ENTRY", "leg": leg, "side": "long", "ref_time": t, "size": ks,
            "keel_size": ks, "trade_id": f"{leg}-x", "keel_branch": branch,
            "keel_fixed_size": fs, "keel_t_fast": -1.33, "keel_trust": 0.0, "keel_score": 0.38}


@pytest.fixture
def pushes(monkeypatch):
    out = []
    monkeypatch.setattr(cs, "_engine_push",
                        lambda msg, title, priority="high", paths=None, log=print:
                        out.append((title, msg, priority)) or True)
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    return out


def test_diff_alert_fires_once_per_entry_with_its_figures(tmp_path, pushes):
    paths = cs._paths(home=str(tmp_path))
    legs = {"NOISE_382": {"keel": {"version": "v12"}}}
    ev = [_entry()]
    cs._note_keel_entries(ev, legs, paths, True, log=lambda s: None)
    cs._note_keel_entries(ev, legs, paths, True, log=lambda s: None)     # a repeat
    assert len(pushes) == 1
    title, msg, prio = pushes[0]
    # the plain phone format (api/ntfy_push): a heads-up, trading not affected -> low
    from api import ntfy_push
    assert prio == "low" and title == "NOISE: KEEL size differs"
    assert ntfy_push.lint({"title": title, "message": msg, "priority": prio}) == []
    # 10:05 ET is 07:05 on the owner's clock; ONE number on the problem line (0.62 vs 1.50 =
    # 59% smaller) -- both sizes and the branch stay in the record, not the push
    assert "KEEL sized the long entry (" in msg and "07:05) 59% smaller than the fixed rule "         "would." in msg
    assert "0.62" not in msg and "1.50" not in msg and "shade" not in msg
    assert msg.startswith("Trading: not affected (the order used KEEL's size")
    recs = cs.read_keel_diffs(cs._keel_diffs_path(paths))
    assert len(recs) == 1
    r = recs[0]
    assert (r["date"], r["leg"], r["entry_time"], r["side"]) == \
        ("2026-10-06", "NOISE_382", "2026-10-06T10:05:00-04:00", "long")
    assert r["keel_size"] == 0.62 and r["keel_fixed_size"] == 1.5 and r["branch"] == "shade"
    assert r["t_fast"] == -1.33

    # a second entry the same day is its own event
    cs._note_keel_entries([_entry(t="2026-10-06T11:30:00-04:00")], legs, paths, True,
                          log=lambda s: None)
    assert len(pushes) == 2 and len(cs.read_keel_diffs(cs._keel_diffs_path(paths))) == 2


def test_no_alert_on_equal_sizes_a_shadow_leg_offline_or_off_the_box(tmp_path, pushes, monkeypatch):
    paths = cs._paths(home=str(tmp_path))
    live = {"NOISE_382": {"keel": {"version": "v12"}}}
    shadow = {"NOISE_422_KEEL": {"keel": {"version": "v12"}, "shadow": True}}
    lines = []
    cs._note_keel_entries([_entry(ks=1.5, fs=1.5), _entry(t="2026-10-06T11:00:00-04:00",
                                                          ks=1.505, fs=1.5)],
                          live, paths, True, log=lines.append)
    cs._note_keel_entries([_entry(leg="NOISE_422_KEEL")], shadow, paths, True, log=lines.append)
    cs._note_keel_entries([_entry(t="2026-10-06T12:00:00-04:00")], live, paths, False,
                          log=lines.append)                                   # offline tick
    monkeypatch.delenv("EDGELOG_HOST_ROLE")
    cs._note_keel_entries([_entry(t="2026-10-06T13:00:00-04:00")], live, paths, True,
                          log=lines.append)                                   # the PC
    assert pushes == []
    assert cs.read_keel_diffs(cs._keel_diffs_path(paths)) == []
    # ... but every one of them is logged, the shadow difference marked as such
    assert sum("KEEL ENTRY" in ln for ln in lines) == 5
    assert any("NOISE_422_KEEL" in ln and "DIFFERS" in ln and "shadow" in ln for ln in lines)


def test_step_level_alert_once_per_entry_and_never_on_a_rerun(tmp_path, pushes, monkeypatch):
    arrays, state = _base_state()
    _a, lean = _leaning_state(float(state["t_fast_now"]) + 0.01)
    keel_cfg = _write_state(tmp_path, lean, data_through="2026-09-04", name="STEP_v12")
    epoch_df, times = _day_bars()
    monkeypatch.setattr(cs, "fetch_and_merge",
                        lambda tf, paths=None, log=print: (epoch_df, "webull", True))
    legs = _day_legs(keel_cfg)
    paths = _run_day(str(tmp_path / "live"), legs, epoch_df, times, fetch=True)
    entries = [r for r in _rows(paths) if r["event"] == "ENTRY"]
    differ = [r for r in entries
              if abs(float(r["keel_size"]) - float(r["keel_fixed_size"])) > cs.KEEL_DIFF_TOL]
    assert differ, "fixture: the shade branch must size something differently"
    # step() pushes on a daemon thread (review 10-05): wait for them, never a fixed join
    assert wait_for(lambda: len(pushes) == len(differ))
    recs = cs.read_keel_diffs(cs._keel_diffs_path(paths))
    assert sorted(r["entry_time"] for r in recs) == sorted(r["ref_time"] for r in differ)

    # the same ticks again: no new entry, so no new push and no new record
    for now in _ticks(times):
        cs.step(now=now, legs=legs, paths=paths, fetch=True)
    assert len(pushes) == len(differ)
    assert len(cs.read_keel_diffs(cs._keel_diffs_path(paths))) == len(differ)

    # the same day on a SHADOW leg: logged, never pushed, never recorded
    spaths = _run_day(str(tmp_path / "shadow"), _day_legs(keel_cfg, shadow=True), epoch_df,
                      times, fetch=True)
    assert len(pushes) == len(differ)
    assert cs.read_keel_diffs(cs._keel_diffs_path(spaths)) == []


def test_diff_file_stays_bounded_and_skips_torn_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "KEEL_DIFFS_KEEP", 5)
    paths = cs._paths(home=str(tmp_path))
    path = cs._keel_diffs_path(paths)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"date": "2026-10-01", "leg": "NOISE_382", "entry_time": "a"}\n{"torn": \n')
    for i in range(8):
        assert cs._record_keel_diff(paths, {"date": "2026-10-06", "leg": "NOISE_382",
                                            "entry_time": f"t{i}"}) is True
    assert cs._record_keel_diff(paths, {"date": "2026-10-06", "leg": "NOISE_382",
                                        "entry_time": "t7"}) is False
    recs = cs.read_keel_diffs(path)
    assert [r["entry_time"] for r in recs] == ["t3", "t4", "t5", "t6", "t7"]
    assert cs.read_keel_diffs(path, last=2) == recs[-2:]


def test_signal_cols_append_the_extras_at_the_end_and_decision_cols_unchanged():
    assert cs.SIGNAL_COLS[-5:] == ["keel_branch", "keel_fixed_size", "keel_t_fast",
                                   "keel_trust", "keel_score"]
    assert cs.KEEL_EXTRA_COLS == cs.SIGNAL_COLS[-5:]
    assert cs.DECISION_COLS[0] == "dec_bar_start" and cs.DECISION_COLS[-1] == "dec_bar_source"
    assert not set(cs.DECISION_COLS) & set(cs.KEEL_EXTRA_COLS)


def test_a_fallback_difference_is_recorded_but_not_pushed_twice(tmp_path, pushes):
    paths = cs._paths(home=str(tmp_path))
    legs = {"NOISE_382": {"keel": {"version": "v12"}}}
    lines = []
    ev = _entry(ks=1.0, fs=1.5, branch="fallback-1.0")
    cs._note_keel_entries([ev], legs, paths, True, log=lines.append)
    cs._note_keel_entries([ev], legs, paths, True, log=lines.append)
    assert pushes == []
    recs = cs.read_keel_diffs(cs._keel_diffs_path(paths))
    assert len(recs) == 1 and recs[0]["branch"] == "fallback-1.0"
    assert sum("no second push" in ln for ln in lines) == 1


# -- 5. review 10-05: cost on the entry path, and the stream commit ---------------------------
def test_step_pushes_the_diff_off_the_engine_thread():
    """Review 10-05: step() hands _note_keel_entries the background sender, so a slow
    'default' ntfy try never holds the engine tick / heartbeat."""
    import inspect
    src = inspect.getsource(cs.step)
    assert "_note_keel_entries(all_events, legs, paths, fetch, push=_engine_push_background)" \
        in src


def test_a_fallback_score_does_not_load_the_rule_cfg(monkeypatch):
    """Review 10-05: on a fallback score the branch is 'fallback-1.0' without reading cfg --
    no state load on the entry path in the degraded case; the fixed size is still computed."""
    arrays = _diff_arrays()

    def no_load(*a, **k):
        raise AssertionError("_keel_rule_cfg must not run on a fallback score")
    monkeypatch.setattr(cs, "_keel_rule_cfg", no_load)
    out = cs._keel_entry_extras({"version": "v12", "state_path": "missing.joblib"}, arrays,
                                390, "keel state unavailable", log=lambda s: None)
    assert out["keel_branch"] == "fallback-1.0"
    assert out["keel_t_fast"] == "" and out["keel_score"] == ""
    fixed, _ = cs._keel_fixed_size_for_entry({"version": "v12", "mode": "fixed"}, arrays, 390)
    assert out["keel_fixed_size"] == pytest.approx(fixed)


def test_extras_reuse_the_scores_features_no_second_pass(tmp_path, monkeypatch):
    arrays, state = _base_state()
    arrays, keel_cfg = _learned_cfg(tmp_path, shade_t=float(state["t_fast_now"]) + 0.01)
    real = K.keel_features
    calls = {"n": 0}

    def counting(a):
        calls["n"] += 1
        return real(a)
    monkeypatch.setattr(K, "keel_features", counting)
    monkeypatch.setattr(cs, "KEEL_ENTRY_EXTRAS", False)
    off = [e for e in _two_ticks(arrays, keel_cfg) if e["event"] == "ENTRY"][0]
    n_off = calls["n"]
    calls["n"] = 0
    monkeypatch.setattr(cs, "KEEL_ENTRY_EXTRAS", True)
    on = [e for e in _two_ticks(arrays, keel_cfg) if e["event"] == "ENTRY"][0]
    assert n_off >= 1 and calls["n"] == n_off, "the extras must not recompute keel_features"
    assert on["keel_fixed_size"] != "" and on["keel_branch"] == "shade"
    fixed, _ = cs._keel_fixed_size_for_entry({"version": "v12", "mode": "fixed"}, arrays, 390)
    assert on["keel_fixed_size"] == pytest.approx(fixed)
    for k in ("size", "keel_size", "shares", "ref_price", "trade_id", "side"):
        assert on[k] == off[k]


def test_stream_commit_notes_a_differing_entry_once_including_the_following_step(
        tmp_path, monkeypatch):
    import test_cloud_signal_stream as TS
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    sent = []
    monkeypatch.setattr(cs, "_engine_push",
                        lambda msg, title, priority="high", paths=None, log=print:
                        sent.append((title, msg, priority)) or True)
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda *a, **k: None)
    keel_cfg = {"version": "v12", "state_path": str(tmp_path / "none.joblib")}
    monkeypatch.setattr(cs, "_keel_size_for_entry",
                        lambda *a, **k: (0.62, {"z": 0.4, "trust": 0.0, "t_fast": -1.33,
                                                "nd": 999}))
    monkeypatch.setattr(cs, "_keel_entry_extras",
                        lambda *a, **k: {"keel_branch": "shade", "keel_fixed_size": 1.5,
                                         "keel_t_fast": -1.33, "keel_trust": 0.0,
                                         "keel_score": 0.4})
    legs = {TS.LEG_KEY: dict(TS._leg_cfg(), keel=keel_cfg)}
    paths, base, bar4_epoch = TS._setup(tmp_path)
    TS._write_handoff(paths, bar4_epoch, close=710.0)
    with open(css._stream_config_path(paths), "w", encoding="utf-8") as f:
        f.write('{"bar_close_from_stream": true}')
    TS._append_rest_bar(paths, bar4_epoch, close=710.0)      # REST has the bar too
    monkeypatch.setattr(cs, "fetch_and_merge",
                        lambda tf, paths=None, log=print:
                        (cs.historical_bars(tf, paths), "webull", True))
    now = TS._now_after(base)
    lines = []

    css._handle_handoff_window(now, legs, paths, {"bar_close_from_stream": True}, lines.append)
    rows = _rows(paths)
    assert [r["event"] for r in rows] == ["ENTRY"] and rows[0]["bar_source"] == "stream"
    assert rows[0]["keel_fixed_size"] == "1.5" and rows[0]["keel_branch"] == "shade"
    diff_pushes = lambda: [x for x in sent if "KEEL size differs" in x[0]]
    assert wait_for(lambda: len(diff_pushes()) == 1), "one push for the differing live entry"
    recs = cs.read_keel_diffs(cs._keel_diffs_path(paths))
    assert len(recs) == 1 and recs[0]["leg"] == TS.LEG_KEY and recs[0]["branch"] == "shade"
    assert sum("KEEL ENTRY" in ln for ln in lines) == 1

    # the same tick's step(): the committed entry is not emitted again -> nothing new
    cs.step(now=now, legs=legs, paths=paths, fetch=True)
    assert [r["event"] for r in _rows(paths)] == ["ENTRY"]
    assert len(cs.read_keel_diffs(cs._keel_diffs_path(paths))) == 1
    assert len(diff_pushes()) == 1


def test_diff_problem_line_carries_one_number():
    f = cs._keel_diff_problem
    assert f("10:35", "long", 0.85, 1.0) ==         "KEEL sized the long entry (10:35) 15% smaller than the fixed rule would."
    assert f("10:35", "short", 1.2, 1.0) ==         "KEEL sized the short entry (10:35) 20% larger than the fixed rule would."
    # no usable ratio (fixed size 0 / unreadable): words only, no number
    assert f("10:35", "", 0.5, 0) == "KEEL sized the entry (10:35) differently from the fixed rule."
    assert f("10:35", "long", "x", 1.0).endswith("differently from the fixed rule.")
