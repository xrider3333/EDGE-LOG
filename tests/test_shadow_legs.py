"""tests/test_shadow_legs.py -- the Webull paper book's SHADOW LEGS (OWNER DECISION 2026-09-28,
via MANAGER): NOISE #422 plain / + KEEL v12 fixed tilts / + KEEL v12 learned, all logging
would-be trades from the box's own bars into <home>/cloud_signal/shadow/ -- no orders, no
effect on the live legs. ENGU-Q was the fourth shadow leg 2026-09-28..2026-10-09 and is LIVE
again since (OWNER DECISION 2026-10-09, MANAGER #102): its shadow rows stay as history.

COVERS:
  1. The dicts: CROWN_LEGS is ORB_R6 + NOISE_382 + ENGUQ_335 exactly; SHADOW_LEGS has the
     three #422 keys, none colliding with a live key; ENGUQ_335 is back on CROWN_LEGS with
     the phantom-safe cfg it had live before 2026-09-28, plus live_since.
  2. The live step's events, state.json and signals.csv are byte-identical with and without
     the shadow run beside it (emitted_at -- the wall clock -- aside), over one synthetic
     session with every real leg.
  3. Shadow events land ONLY in the shadow store; the live store gains no shadow row, no
     shadow leg state and no heartbeat from the shadow run.
  4. api/qqq_exec.py's engine reader consumes the live ledger only -- an ENGU-Q ENTRY left in
     the shadow ledger (its 09-28..10-09 history) is never read -- and the live step runs
     ENGUQ_335 again (cold start, SEED only) and fetches 1m itself.
  5. No ntfy push from a shadow leg: run_shadow_step on a cloud host, fetch tick, NOISE_422_KEEL
     with no state, a stale/missing everything -- nothing sent.
  6. Fetch discipline: on a fetch tick of cloud_signal_thread, 5m and 1m are each fetched
     exactly once (a timeframe only a shadow leg reads is fetched by the shadow run -- stub
     legs; with the shipped legs every timeframe is a live one, shadow_only_timeframes() is
     empty); the shadow run is skipped on a non-fetch tick; a failing shadow run never breaks
     the live tick, and logs rate-limited.
  7. api/cloud_signal_stream.py stays live-legs-only.
  8. tools/keel_live_state.py's nightly default builds the two learned legs only.
  9. tools/shadow_legs_report.py's arithmetic, and tools/pull_box_ledgers.py copies the
     shadow store.
The three #422 variants' sizes on a synthetic series: tests/test_noise_422_shadow.py.
"""
import csv
import json
import os
import sys
import threading
import types

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import api.cloud_signal as cs                       # noqa: E402
from api import cloud_signal_stream as css          # noqa: E402
from api import qqq_exec as qe                      # noqa: E402
from api.paper import ENGUQ_335                     # noqa: E402
import test_noise_422_shadow as T422               # noqa: E402  (synthetic 5m series + KEEL state)
import tools.keel_live_state as kls                 # noqa: E402
import tools.pull_box_ledgers as pbl                # noqa: E402
import tools.shadow_legs_report as rpt              # noqa: E402

QUIET = lambda *a, **k: None   # noqa: E731
SHADOW_KEYS = ["NOISE_422_PLAIN", "NOISE_422_FIXED", "NOISE_422_KEEL"]
LIVE_KEYS = ["ORB_R6", "NOISE_382", "ENGUQ_335"]


# ── 1. the dicts ─────────────────────────────────────────────────────────────────────────
def test_live_and_shadow_leg_sets():
    assert list(cs.CROWN_LEGS) == LIVE_KEYS
    assert list(cs.SHADOW_LEGS) == SHADOW_KEYS
    assert not set(cs.CROWN_LEGS) & set(cs.SHADOW_LEGS), "a trade id carries the leg key"
    assert all(cfg.get("shadow") is True for cfg in cs.SHADOW_LEGS.values())
    assert not any(cfg.get("shadow") for cfg in cs.CROWN_LEGS.values())
    # every shadow leg is 5m and 1m is a LIVE timeframe again (ENGUQ_335): nothing is
    # fetched by the shadow run alone
    assert cs.shadow_only_timeframes() == []


def test_enguq_335_is_live_again_with_its_pre_0928_cfg():
    """OWNER DECISION 2026-10-09 (MANAGER #102): back on CROWN_LEGS, key for key the cfg it
    had live before 2026-09-28 (fb0f32f0's parent) plus live_since -- phantom_safe kept, no
    eod_flat / decide_at_close / keel, never "shadow"."""
    assert "ENGUQ_335" not in cs.SHADOW_LEGS
    leg = cs.CROWN_LEGS["ENGUQ_335"]
    assert leg["strategy"] == "ENGUQ_1M_ETH_R2_1_0.py" and leg["timeframe"] == "1m"
    assert leg["params"] == dict(ENGUQ_335, phantom_safe=True)
    assert leg["params"]["phantom_safe"] is True
    assert leg["max_entry_age_sec"] == 11 * 60
    assert leg["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS
    assert "caveat" in leg and "keel" not in leg and not leg.get("decide_at_close")
    assert not leg.get("eod_flat") and "shadow" not in leg
    assert leg["live_since"] == cs.ENGUQ_LIVE_SINCE == "2026-10-09"
    assert set(leg) == {"strategy", "timeframe", "params", "max_entry_age_sec",
                        "warmup_sessions", "caveat", "live_since"}
    assert qe.ENGINE_LEG_MAP["ENGUQ_335"] == "ENGUQ"


def test_shadow_paths_share_the_bars_and_nothing_else(tmp_path):
    live = cs._paths(home=str(tmp_path))
    sp = cs.shadow_paths(live)
    assert sp["ohlc_dir"] == live["ohlc_dir"] and sp["home"] == live["home"]
    for k in ("state_dir", "signals_path", "state_path", "heartbeat_path"):
        assert sp[k] != live[k] and sp[k].startswith(os.path.join(live["state_dir"], "shadow")), k


# ── a home with synthetic 5m (all sessions) and 1m (the last few) bars ───────────────────
def _synthetic_1m(days, seed=11, price=700.0):
    rng = np.random.RandomState(seed)
    rows, p = [], price
    for d in days:
        start = pd.Timestamp(f"{d} 09:30:00", tz=cs.TZ)
        for b in range(390):
            o = p
            c = p + rng.normal(0, 0.08)
            h, l = max(o, c) + abs(rng.normal(0, 0.03)), min(o, c) - abs(rng.normal(0, 0.03))
            rows.append((int((start + pd.Timedelta(minutes=b)).tz_convert("UTC").timestamp()),
                         o, h, l, c, 1000.0))
            p = c
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def _make_home(root):
    paths = cs._paths(home=str(root))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    T422._EPOCH.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    _synthetic_1m(T422._DAYS[-4:]).to_csv(os.path.join(paths["ohlc_dir"], "QQQ_1m.csv"), index=False)
    return paths


def _live_legs(home):
    """The SHIPPED live legs, NOISE_382's KEEL pointed at this test home (no state there --
    it scores 1.0, and fetch here is patched so no push can be sent) and ENGU-Q on a
    3-session window (the synthetic 1m tape is short)."""
    return {"ORB_R6": dict(cs.CROWN_LEGS["ORB_R6"]),
            "NOISE_382": dict(cs.CROWN_LEGS["NOISE_382"],
                              keel=dict(version="v12", **cs.keel_paths("NOISE_382", "v12", home=home))),
            "ENGUQ_335": dict(cs.CROWN_LEGS["ENGUQ_335"], warmup_sessions=3)}


def _shadow_legs(home):
    """The SHIPPED shadow legs, NOISE_422_KEEL on a real fitted state in this test home."""
    legs = {k: dict(v) for k, v in cs.SHADOW_LEGS.items()}
    legs["NOISE_422_KEEL"]["keel"] = T422._write_keel_state(home)
    return legs


@pytest.fixture
def offline(monkeypatch):
    """No network anywhere: fetch_and_merge reads the on-disk cache back (as a fetch that
    merged nothing new would) and counts calls per timeframe; every real fetcher raises."""
    calls = []

    def fake_fetch(tf, paths=None, log=print):
        calls.append(tf)
        return cs.historical_bars(tf, paths), "webull", True

    def boom(*a, **k):
        raise AssertionError("network touched")
    monkeypatch.setattr(cs, "fetch_and_merge", fake_fetch)
    monkeypatch.setattr(cs, "_fetch_webull", boom)
    monkeypatch.setattr(cs.qp, "_fetch_yf", boom)
    monkeypatch.setattr(cs, "_fetch_yf_daily", boom)
    monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)
    return calls


def _ticks(n=30):
    yield pd.Timestamp(f"{T422._DAYS[-2]} 17:00", tz=cs.TZ).to_pydatetime()
    for b in range(1, n + 1):
        yield (pd.Timestamp(f"{T422._DAYS[-1]} 09:30", tz=cs.TZ)
               + pd.Timedelta(minutes=5 * b, seconds=10)).to_pydatetime()


def _strip_clock(events):
    return [{k: v for k, v in e.items() if k != "emitted_at"} for e in events]


def _ledger_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _drive(root, with_shadow):
    paths = _make_home(root)
    home = paths["home"]
    live, shadow = _live_legs(home), _shadow_legs(home)
    live_events, shadow_events = [], []
    for now in _ticks():
        live_events += cs.step(now=now, legs=live, paths=paths, fetch=True)
        if with_shadow:
            shadow_events += cs.run_shadow_step(now=now, fetch=True, live_legs=live,
                                                shadow_legs=shadow, live_paths=paths, log=QUIET)
    return paths, live_events, shadow_events


# ── 2 + 3. byte-identical live outputs; shadow rows only in the shadow store ─────────────
def test_live_step_is_byte_identical_with_and_without_the_shadow_run(tmp_path, offline):
    a_paths, a_live, a_shadow = _drive(tmp_path / "with", with_shadow=True)
    n_calls_with = len(offline)
    b_paths, b_live, _ = _drive(tmp_path / "without", with_shadow=False)

    assert a_live and _strip_clock(a_live) == _strip_clock(b_live)
    with open(a_paths["state_path"], "rb") as fa, open(b_paths["state_path"], "rb") as fb:
        assert fa.read() == fb.read(), "live state.json must not change by one byte"
    rows_a, rows_b = _ledger_rows(a_paths["signals_path"]), _ledger_rows(b_paths["signals_path"])
    assert _strip_clock(rows_a) == _strip_clock(rows_b)

    # 3. the shadow run wrote ONLY the shadow store
    assert {r["leg"] for r in rows_a} == set(LIVE_KEYS)
    assert set(json.load(open(a_paths["state_path"], encoding="utf-8"))["legs"]) == set(LIVE_KEYS)
    assert not os.path.exists(a_paths["heartbeat_path"]), "the shadow run never writes the live heartbeat"
    sp = cs.shadow_paths(a_paths)
    shadow_rows = _ledger_rows(sp["signals_path"])
    assert {r["leg"] for r in shadow_rows} == set(SHADOW_KEYS), "every shadow leg at least SEEDs"
    assert set(json.load(open(sp["state_path"], encoding="utf-8"))["legs"]) == set(SHADOW_KEYS)
    hb = json.load(open(sp["heartbeat_path"], encoding="utf-8"))
    assert hb["ok"] is True and "shadow event(s)" in hb["note"]
    assert [r for r in shadow_rows if r["event"] == "ENTRY"], "the #422 legs trade the session"
    assert all(r["bar_source"] == "webull" for r in shadow_rows if r["event"] != "SEED")
    assert len(a_shadow) == len(shadow_rows), "run_shadow_step returns what it wrote"
    # fetch discipline inside the drive: the live step fetched 5m and 1m (ENGU-Q is live
    # again), the shadow run nothing -- each timeframe once per tick
    assert n_calls_with == 2 * len(list(_ticks()))
    assert offline[:n_calls_with].count("1m") == offline[:n_calls_with].count("5m")


# ── 4. qqq_exec reads the live ledger only; ENGU-Q is a live leg again ───────────────────
def test_qqq_exec_reader_ignores_the_shadow_ledger(tmp_path, monkeypatch):
    """An ENGUQ_335 row in the SHADOW ledger (its 09-28..10-09 history) never becomes an order,
    now that ENGUQ_335 is a live key again -- the reader opens the live ledger only."""
    live = cs._paths(home=str(tmp_path))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    now = pd.Timestamp("2026-09-29 10:00:30", tz=cs.TZ).to_pydatetime()
    row = {"emitted_at": now.isoformat(), "event": "ENTRY", "side": "long",
           "ref_time": "2026-09-29T10:00:00-04:00", "ref_price": 700.0, "shares": 10,
           "size": 1.0, "bar_source": "webull"}
    cs._append_signals([dict(row, leg="ORB_R6", trade_id="ORB_R6-20260929T140000Z-L")], live)
    sp = cs.shadow_paths()
    assert sp["state_dir"].startswith(str(tmp_path))
    cs._append_signals([dict(row, leg="ENGUQ_335", trade_id="ENGUQ_335-20260929T140000Z-L"),
                        dict(row, leg="NOISE_422_KEEL", trade_id="NOISE_422_KEEL-20260929T140000Z-L")],
                       sp)
    state = {"engine_cursor": 0}
    got = qe._consume_engine_signals(state, {}, now.replace(tzinfo=None), log=QUIET)
    assert [e["leg"] for e in got] == ["ORB_R6"]
    assert state["engine_cursor"] == 1, "the cursor counts the LIVE ledger's rows only"
    # the reader's only ledger path is the live one
    assert qe._cs_module().DEFAULT_PATHS["signals_path"] == live["signals_path"] != sp["signals_path"]


def test_live_step_runs_enguq_again_and_fetches_1m_itself(tmp_path, offline):
    """ENGUQ_335 is back on CROWN_LEGS (2026-10-09): the SHIPPED live step (default legs)
    steps it, starting with ONE cold-start SEED stamped with its live_since, and fetches 1m
    itself (no shadow leg needs it any more)."""
    paths = _make_home(tmp_path)
    events = []
    for now in _ticks(6):
        events += cs.step(now=now, paths=paths, fetch=True)
    assert events and {e["leg"] for e in events} <= set(LIVE_KEYS)
    enguq = [e for e in events if e["leg"] == "ENGUQ_335"]
    assert enguq and enguq[0]["event"] == "SEED"
    assert [e for e in enguq if e["event"] == "SEED"] == enguq[:1], "ONE seed"
    assert "live_since=2026-10-09" in enguq[0]["reason"]
    st = json.load(open(paths["state_path"], encoding="utf-8"))["legs"]["ENGUQ_335"]
    assert st["live_since"] == "2026-10-09" and st["seeded"] is True
    assert set(offline) == {"5m", "1m"}


# ── 5. no push from a shadow leg ─────────────────────────────────────────────────────────
def test_no_push_from_shadow_legs_even_with_keel_state_missing_on_a_cloud_host(tmp_path, offline,
                                                                            monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: True)
    monkeypatch.setenv("NTFY_TOPIC", "never-used-in-tests")
    paths = _make_home(tmp_path)
    shadow = {k: dict(v) for k, v in cs.SHADOW_LEGS.items()}
    # NOISE_422_KEEL with NO state (the first session after deploy), in this test home
    shadow["NOISE_422_KEEL"]["keel"] = dict(version="v12", **cs.keel_paths("NOISE_422_KEEL", "v12",
                                                                           home=paths["home"]))
    seen_fetch = []
    real_step = cs.step

    def spy_step(*a, **k):
        seen_fetch.append(k.get("fetch"))
        return real_step(*a, **k)
    monkeypatch.setattr(cs, "step", spy_step)
    events = []
    for now in _ticks(12):
        events += cs.run_shadow_step(now=now, fetch=True, live_legs=_live_legs(paths["home"]),
                                     shadow_legs=shadow, live_paths=paths, log=QUIET)
    assert seen_fetch and set(seen_fetch) == {False}, "the shadow step never fetches"
    keel_entries = [e for e in events if e["leg"] == "NOISE_422_KEEL" and e["event"] == "ENTRY"]
    assert keel_entries and all(e["keel_size"] == 1.0 for e in keel_entries)
    assert sent == []
    st = json.load(open(cs.shadow_paths(paths)["state_path"], encoding="utf-8"))
    assert "keel_alerts" not in st and not any("keel_alert" in v for v in st["legs"].values())
    # and _push_allowed itself: a shadow cfg is never allowed, a live one only live+cloud
    assert cs._push_allowed({"shadow": True}, True) is False
    assert cs._push_allowed({}, True) is True and cs._push_allowed({}, False) is False


# ── 6. the thread: fetch once per timeframe, shadow on fetch ticks only, never raises ────
def _stub_strategy():
    mod = types.ModuleType("shadow_test_stub")
    mod.DEFAULT_PARAMS = {}
    mod.run_backtest = lambda *a, return_trades=False, **k: {"trades": [], "num_trades": 0,
                                                              "total_pnl": 0.0}
    return mod


def _run_thread(tmp_path, monkeypatch, iterations, clock):
    """cloud_signal_thread for `iterations` loop passes with stub legs (live 5m; shadow 5m +
    1m), a counting fetch, and `clock()` as the wall clock the fetch throttle reads."""
    paths = _make_home(tmp_path)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    stub = _stub_strategy()
    monkeypatch.setattr(cs, "CROWN_LEGS", {"LIVE5": {"strategy": stub, "timeframe": "5m", "params": {}}})
    monkeypatch.setattr(cs, "SHADOW_LEGS", {
        "SH5": {"strategy": stub, "timeframe": "5m", "params": {}, "shadow": True},
        "SH1": {"strategy": stub, "timeframe": "1m", "params": {}, "shadow": True}})
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: None)
    monkeypatch.setattr(cs.market_calendar, "is_session", lambda d: True)
    monkeypatch.setattr(cs, "RTH_OPEN", cs._dt.time(0, 0))
    monkeypatch.setattr(cs, "RTH_CLOSE", cs._dt.time(23, 59, 59))
    monkeypatch.setattr(cs._time, "time", clock)
    stop = threading.Event()
    left = [iterations]

    def fake_sleep(seconds):
        left[0] -= 1
        if left[0] <= 0:
            stop.set()
    monkeypatch.setattr(cs._time, "sleep", fake_sleep)
    logs = []
    cs.cloud_signal_thread(stop=stop, log=logs.append)
    return paths, logs


def test_thread_fetches_5m_and_1m_exactly_once_per_fetch_tick(tmp_path, offline, monkeypatch):
    shadow_calls = []
    real = cs.run_shadow_step
    monkeypatch.setattr(cs, "run_shadow_step",
                        lambda **k: shadow_calls.append(k.get("fetch")) or real(**k))
    t = [1000.0]
    paths, logs = _run_thread(tmp_path, monkeypatch, 1, lambda: t[0])
    assert sorted(offline) == ["1m", "5m"], offline
    assert shadow_calls == [True]
    hb = json.load(open(paths["heartbeat_path"], encoding="utf-8"))
    assert hb["ok"] is True
    assert json.load(open(cs.shadow_paths(paths)["heartbeat_path"], encoding="utf-8"))["ok"] is True


def test_thread_skips_the_shadow_run_on_a_non_fetch_tick(tmp_path, offline, monkeypatch):
    shadow_calls = []
    monkeypatch.setattr(cs, "run_shadow_step", lambda **k: shadow_calls.append(1) or [])
    # a frozen clock: the second pass is inside THREAD_STEP_SEC of the first -> fetch=False
    paths, _logs = _run_thread(tmp_path, monkeypatch, 2, lambda: 5000.0)
    assert offline == ["5m"], "one fetch tick, then a fast tick with no fetch"
    assert shadow_calls == [1]


def test_a_failing_shadow_run_never_breaks_the_live_tick_and_logs_rate_limited(tmp_path, offline,
                                                                              monkeypatch):
    def boom(**k):
        raise RuntimeError("synthetic shadow failure")
    monkeypatch.setattr(cs, "run_shadow_step", boom)
    monkeypatch.setattr(cs, "_SHADOW_ERR", {"last_logged": 0.0, "suppressed": 0})
    t = [10_000.0]

    def clock():
        t[0] += 31.0           # every pass is a fetch tick
        return t[0]
    paths, logs = _run_thread(tmp_path, monkeypatch, 3, clock)
    hb = json.load(open(paths["heartbeat_path"], encoding="utf-8"))
    assert hb["ok"] is True, "the live heartbeat stays ok"
    fails = [m for m in logs if "shadow step failed" in m]
    assert len(fails) == 1, fails              # 3 failures, one line (rate limit)
    assert cs._SHADOW_ERR["suppressed"] == 2
    sh = json.load(open(cs.shadow_paths(paths)["heartbeat_path"], encoding="utf-8"))
    assert sh["ok"] is False and "synthetic shadow failure" in sh["note"]


# ── 7. the stream module stays live-only ─────────────────────────────────────────────────
def test_stream_wrapper_steps_the_live_legs_only(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cs, "step", lambda **k: seen.append(k.get("legs")) or [])
    now = pd.Timestamp("2026-09-29 10:03:00", tz=cs.TZ).to_pydatetime()   # outside the window
    css.run_stream_aware_step(now=now, fetch=False, paths=cs._paths(home=str(tmp_path)), log=QUIET)
    assert seen and set(seen[0]) == set(cs.CROWN_LEGS)
    assert not set(seen[0]) & set(cs.SHADOW_LEGS)


# ── 8. the nightly KEEL build ────────────────────────────────────────────────────────────
def test_keel_live_state_builds_the_two_learned_legs_only():
    assert [l["leg_key"] for l in kls.resolve_legs()] == ["NOISE_382", "NOISE_422_KEEL"]


# ── 9. the report tool and the backup copy ──────────────────────────────────────────────
def _rows(leg, trades):
    out = []
    for i, (side, e_px, x_px, size, keel) in enumerate(trades):
        tid = f"{leg}-20260929T14{i:02d}00Z-{'L' if side == 'long' else 'S'}"
        base = {"leg": leg, "side": side, "shares": 10, "trade_id": tid, "bar_source": "webull",
                "size": size, "keel_size": "" if keel is None else keel}
        out.append(dict(base, event="ENTRY", ref_time=f"2026-09-29T10:{i:02d}:00-04:00",
                        ref_price=e_px, emitted_at="x", reason=""))
        if x_px is not None:
            out.append(dict(base, event="EXIT", ref_time=f"2026-09-29T11:{i:02d}:00-04:00",
                            ref_price=x_px, emitted_at="x", reason="strategy_exit"))
    return out


def test_shadow_legs_report_numbers(tmp_path, capsys):
    live = cs._paths(home=str(tmp_path))
    sp = cs.shadow_paths(live)
    cs._append_signals([{"leg": "NOISE_382", "event": "SEED"}]
                       + _rows("NOISE_382", [("long", 700.0, 701.0, 2.0, 0.5),     # +20 (plain +40)
                                             ("short", 700.0, 702.0, 1.0, 1.0)]),  # -20
                       live)
    cs._append_signals(_rows("NOISE_422_FIXED", [("long", 700.0, 700.5, 2.5, 1.5),    # +12.5
                                                 ("long", 700.0, 699.0, 1.0, 1.0),     # -10
                                                 ("short", 700.0, None, 1.0, 1.0)])    # open
                       + _rows("ENGUQ_335", [("short", 700.0, 699.0, 1.0, None)]), sp)   # +10
    rep = rpt.build_report(str(tmp_path))
    L = rep["legs"]
    assert L["NOISE_382 (live primary)"] == {"trades": 2, "open": 0, "net_usd": 0.0, "win_rate": 0.5,
                                             "largest_win_usd": 20.0, "largest_loss_usd": -20.0,
                                             "avg_size": 1.5, "seeded": 0}
    assert L[rpt.PRIMARY_PLAIN]["net_usd"] == 20.0     # 1 x 10 x 4.0 - 20: KEEL divided back out
    f = L["NOISE_422_FIXED"]
    assert (f["trades"], f["open"], f["net_usd"]) == (2, 1, 2.5)
    assert f["largest_win_usd"] == 12.5 and f["largest_loss_usd"] == -10.0
    assert L["ENGUQ_335"]["net_usd"] == 10.0 and L["NOISE_422_PLAIN"]["trades"] == 0
    # the shadow legs first, then ENGUQ_335's shadow-ledger history (a leg found in the
    # ledger -- it went live again on 2026-10-09, its old rows stay reported)
    assert list(L)[2:] == SHADOW_KEYS + ["ENGUQ_335"]
    assert rep["keel"]["NOISE_422_KEEL"]["data_through"] is None
    assert rpt.main(["--home", str(tmp_path)]) == 0
    assert "NOISE_422_FIXED" in capsys.readouterr().out


def test_read_rows_missing_file_is_empty_unless_strict(tmp_path):
    """The report reads a missing ledger as no rows; qqq_exec's shadow_trades block asks for
    strict=True so it can say the ledger could not be read."""
    missing = str(tmp_path / "nope" / "signals.csv")
    assert rpt.read_rows(missing) == []
    with pytest.raises(OSError):
        rpt.read_rows(missing, strict=True)
    os.makedirs(tmp_path / "adir")
    assert rpt.read_rows(str(tmp_path / "adir")) == []
    with pytest.raises(OSError):
        rpt.read_rows(str(tmp_path / "adir"), strict=True)


def test_pull_box_ledgers_copies_the_shadow_store_and_the_new_keel_summary():
    for rel in ("cloud_signal/shadow/signals.csv", "cloud_signal/shadow/state.json",
                "cloud_signal/shadow/heartbeat.json",
                "cloud_signal/keel/NOISE_422_KEEL_v12_summary.json",
                "cloud_signal/keel/NOISE_382_v12_summary.json", "cloud_signal/signals.csv"):
        assert rel in pbl.FILES, rel


def test_qqq_exec_resolves_enguq_from_the_live_legs_again(monkeypatch):
    """ENGUQ_335 is on CROWN_LEGS again (2026-10-09): its exec leg resolves to the live cfg
    (1m bars). The SHADOW_LEGS fallback stays for a leg whose every engine key is off the
    live book -- shown here with ENGU-Q's own cfg moved back to the shadow dict."""
    assert qe._engine_key_for_leg("ENGUQ", cs) == "ENGUQ_335"
    assert qe._leg_timeframe_seconds("ENGUQ") == 60
    assert qe._engine_leg_cfg(cs, "ENGUQ_335") is cs.CROWN_LEGS["ENGUQ_335"]
    assert qe._engine_leg_cfg(cs, "NOISE_382") is cs.CROWN_LEGS["NOISE_382"]
    assert qe._engine_leg_cfg(cs, None) is None
    assert qe._leg_timeframe_seconds("NOISE") == qe._leg_timeframe_seconds("ORB") == 300
    off = {k: v for k, v in cs.CROWN_LEGS.items() if k != "ENGUQ_335"}
    monkeypatch.setattr(cs, "CROWN_LEGS", off)
    monkeypatch.setattr(cs, "SHADOW_LEGS", {"ENGUQ_335": {"timeframe": "1m", "shadow": True}})
    assert qe._engine_leg_cfg(cs, "ENGUQ_335")["timeframe"] == "1m"
    assert qe._leg_timeframe_seconds("ENGUQ") == 60
