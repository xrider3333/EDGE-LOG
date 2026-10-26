"""api/cloud_signal.py's NEXT ENTRY PREVIEW (item 53, owner 2026-10-20).

Once per new closed 5-min bar, cloud_signal_thread works out what NOISE_382 and ORB_R6 would do
if they fired at the NEXT bar's close and writes <state_dir>/next_entry.json -- display only,
after the tick's rows, never on a tick that wrote an order row (step()'s or a stream commit's)
nor in the two executor ticks after it, once per bar even when it fails, never into state.json /
signals.csv / KEEL files.
These tests drive the REAL strategy files (NOISE_1_8_CT304.py, ORB_3_6_R6.py) on synthetic bars
in scratch stores, with a KEEL block pointed at an empty dir (the fixed-tilt fallback, as on the
PC). Two tests also replay the box's real NOISE entries against the PC's 5m cache when both
files exist locally (read-only, skipped elsewhere).
"""
import csv
import datetime as _dt
import json
import os
import shutil

import numpy as np
import pandas as pd
import pytest

import api.cloud_signal as cs
from api import market_calendar

LAST = "2026-10-20"                       # a Tuesday; the next session is Wed 10-21, no FOMC
BOX_SIGNALS = r"C:\EdgeLog\box_backup\2026-10-20_1445\cloud_signal\signals.csv"
PC_5M = r"C:\EdgeLog\ohlc\QQQ_5m.csv"
_LOCAL = os.path.exists(BOX_SIGNALS) and os.path.exists(PC_5M)


@pytest.fixture(autouse=True)
def _clear_memo(monkeypatch):
    cs._NEXT_ENTRY_MEMO.clear()
    # the vol_prior_ranges once-a-day log latches: a quiet preview call must not eat another
    # test's line
    monkeypatch.setattr(cs, "_DAILY_CALIBRATION_LOG", {})
    yield
    cs._NEXT_ENTRY_MEMO.clear()


# ── builders ────────────────────────────────────────────────────────────────────────────

def _sessions(n, last=LAST):
    out, d = [], _dt.date.fromisoformat(last)
    while len(out) < n:
        if market_calendar.is_session(d):
            out.append(d)
        d -= _dt.timedelta(days=1)
    return out[::-1]


def _tape(n=45, last=LAST, seed=5, today=None, prior=None, quiet=0, vol=1000.0, sd=0.001):
    """`n` sessions of 5-min bars ending on `last`: a seeded random walk, then `last` flat at the
    prior close unless today(i, px) -> (o, h, l, c[, volume]) says otherwise for its i-th bar.
    prior(i, px) reshapes the session before `last` the same way; the `quiet` sessions before
    `last` walk at a tenth of the step."""
    rng = np.random.default_rng(seed)
    days = _sessions(n, last)
    rows, px = [], 500.0
    for di, d in enumerate(days):
        base = pd.Timestamp(f"{d} 09:30", tz=cs.TZ)
        is_today, is_prior = di == len(days) - 1, di == len(days) - 2
        step = sd / 10.0 if len(days) - 1 - quiet <= di < len(days) - 1 else sd
        for i in range(cs._ne_session_bars(d, "5m")):
            got = None
            if is_today and today is not None:
                got = today(i, px)
            elif is_prior and prior is not None:
                got = prior(i, px)
            if got is not None:
                o, h, l, c = got[:4]
                v = got[4] if len(got) > 4 else vol
            elif is_today:
                o = h = l = c = px
                v = vol
            else:
                o = px
                c = o * (1 + rng.normal(0, step))
                h = max(o, c) * (1 + abs(rng.normal(0, step / 3)))
                l = min(o, c) * (1 - abs(rng.normal(0, step / 3)))
                v = vol
            t = base + pd.Timedelta(minutes=5 * i)
            rows.append({"time": int(t.tz_convert("UTC").timestamp()), "open": o, "high": h,
                         "low": l, "close": c, "volume": v})
            px = c
    return pd.DataFrame(rows)


def _home(tmp_path, df, name="home"):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)
    return paths


def _noise_cfg(paths):
    """NOISE_382 as live, its KEEL block pointed at an empty dir -> the fixed-tilt fallback."""
    return dict(cs.CROWN_LEGS["NOISE_382"],
                keel=dict(version="v12", **cs.keel_paths("NOISE_382", "v12", home=paths["home"])))


def _legs(paths, orb=True):
    legs = {"NOISE_382": _noise_cfg(paths)}
    if orb:
        legs["ORB_R6"] = dict(cs.CROWN_LEGS["ORB_R6"])
    return legs


def _after(hhmm, day=LAST, sec=310):
    """`sec` after the bar starting at hhmm opened -- 310: 10 s after it closed."""
    return (pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ) + pd.Timedelta(seconds=sec)).to_pydatetime()


def _arrays(df, hhmm, cfg, day=LAST):
    return cs.closed_arrays(df, _after(hhmm, day), "5m", cs.leg_warmup_sessions(cfg))


def _stash(paths, df, hhmm, legs, day=LAST):
    """What step() would stash after the bar starting at hhmm closed."""
    now = _after(hhmm, day)
    kept = {}
    for k, cfg in legs.items():
        arrays = _arrays(df, hhmm, cfg, day)
        trades, _ = cs.leg_decision_trades(cfg, arrays, k, "5m", now, paths, fetch=False,
                                           log=cs._ne_quiet)
        kept[k] = {"cfg": cfg, "arrays": arrays, "trades": trades, "tf": "5m",
                   "bar_epoch": int(arrays["index"][-1].timestamp()), "now": now}
    cs._stash_next_entry_inputs(kept, paths)
    return now, kept


def _epoch(hhmm, day=LAST):
    return int(pd.Timestamp(f"{day} {hhmm}", tz=cs.TZ).timestamp())


def _health(hhmm, day=LAST):
    return {"bar_health": {"5m": {"newest_closed_bar_epoch": _epoch(hhmm, day)}}}


def _jump(at, pct):
    """today(): flat at the prior close, the bar starting `at` closes `pct` away."""
    k = (pd.Timestamp(f"2000-01-01 {at}") - pd.Timestamp("2000-01-01 09:30")).seconds // 300

    def fn(i, px):
        if i == k:
            c = px * (1 + pct)
            return px, max(px, c), min(px, c), c
        return None
    return fn


# ── 1. preview == actual, through the real step() ───────────────────────────────────────

def test_preview_equals_the_real_entry_size(tmp_path):
    df = _tape(today=_jump("10:00", 0.01))
    paths = _home(tmp_path, df)
    legs = _legs(paths, orb=False)
    logs = []
    assert [e["event"] for e in cs.step(now=_after("09:50"), legs=legs, paths=paths,
                                        fetch=False)] == ["SEED"]
    w = {}
    assert cs.step(now=_after("09:55"), legs=legs, paths=paths, fetch=False, warnings=w) == []
    first = cs._next_entry_tick(_after("09:55"), [], warnings=w, paths=paths, log=logs.append)
    nx = first["legs"]["NOISE_382"]["next"]
    assert first["legs"]["NOISE_382"]["status"] == "ok"
    assert (nx["decide_bar"], nx["decide_close"], nx["may_change"]) == ("10:00", "10:05", [])
    assert nx["keel_src"] == "fallback" and nx["branch"] == "fallback"

    w = {}
    events = cs.step(now=_after("10:00"), legs=legs, paths=paths, fetch=False, warnings=w)
    assert [e["event"] for e in events] == ["ENTRY"]
    entry = events[0]
    before = os.path.getmtime(cs.next_entry_path(paths))
    assert cs._next_entry_tick(_after("10:00"), events, warnings=w, paths=paths,
                               log=logs.append) is None            # the order tick: deferred
    assert os.path.getmtime(cs.next_entry_path(paths)) == before
    assert cs._next_entry_tick(_after("10:00", sec=311), [], warnings=w, paths=paths,
                               log=logs.append) is None            # the executor's tick has not come
    doc = cs._next_entry_tick(_after("10:00", sec=320), [], warnings=w, paths=paths,
                              log=logs.append)
    leg = doc["legs"]["NOISE_382"]
    assert leg["status"] == "in_trade"                               # it fired this bar
    chk = leg["check"]
    assert chk["tid"] == entry["trade_id"] and chk["bar"] == "10:00"
    assert chk["match"] is True and chk["actual"] == pytest.approx(float(entry["size"]))
    assert chk["preview"] == pytest.approx(float(entry["size"]))
    assert chk["board"] == pytest.approx(float(entry["size"])) and chk["board_match"] is True
    assert nx["size"] == pytest.approx(float(entry["size"]), abs=1e-12)
    assert [m for m in logs if "next-entry check" in m] == [
        f"[cloud-signal] next-entry check NOISE_382 {entry['trade_id']}: preview "
        f"{chk['preview']:g} vs actual {chk['actual']} -- match"]
    assert cs.read_next_entry(paths) == doc


# ── 2. preview == actual on the box's own entries (local only) ──────────────────────────

def _box_rows():
    with open(BOX_SIGNALS, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["leg"] == "NOISE_382" and r["event"] == "ENTRY"]


def _pc_home(tmp_path):
    paths = cs._paths(home=str(tmp_path / "pc"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    shutil.copy(PC_5M, paths["ohlc_dir"])                  # read-only: a copy in the scratch store
    return paths


@pytest.mark.skipif(not _LOCAL, reason="the box backup and the PC 5m cache are local files")
def test_box_entries_this_bar_and_next_bar_sizes(tmp_path):
    paths = _pc_home(tmp_path)
    cfg = _noise_cfg(paths)
    df = cs.historical_bars("5m", paths)
    rows = _box_rows()
    assert len(rows) == 27
    exact = checked = 0
    for r in rows:
        ref = pd.Timestamp(r["ref_time"])
        d = ref - pd.Timedelta(minutes=5)
        size, keel = float(r["size"]), float(r["keel_size"])
        arrays = cs.closed_arrays(df, (ref + pd.Timedelta(seconds=10)).to_pydatetime(), "5m",
                                  cs.leg_warmup_sessions(cfg))
        assert arrays["index"][-1] == d
        n = len(arrays["close"])
        parts = cs._noise_size_parts(cfg, cs._stand_in_arrays(arrays, "5m"), n - 1, n)
        assert parts["size"] == pytest.approx(size, abs=1e-9), r["ref_time"]
        assert parts["plugin"] == pytest.approx(size / keel), r["ref_time"]
        # the NEXT-bar preview one bar earlier: exact whenever nothing may still change
        now1 = (d + pd.Timedelta(seconds=10)).to_pydatetime()
        arr1 = cs.closed_arrays(df, now1, "5m", cs.leg_warmup_sessions(cfg))
        leg = cs._noise_next_entry(cfg, arr1, [], "5m", now1, paths)
        if leg["status"] == "ok":
            assert leg["next"]["decide_bar"] == d.strftime("%H:%M")
            checked += 1
            if not leg["next"]["may_change"]:
                exact += 1
                assert leg["next"]["size"] == pytest.approx(size, abs=1e-9), r["ref_time"]
    print(f"\nnext-bar preview: {exact} of {checked} previews exact (may_change empty), "
          f"all {exact} equal to the real size")
    assert exact >= 15


TRAP = ("2026-09-28T10:15", "2026-10-08T12:55", "2026-10-12T10:10", "2026-10-16T09:40")


def _comp(cfg, arrays):
    mod = cs._strategy_module_for_sizing(cfg["strategy"])
    p = cfg["params"]
    return mod._sq._compression(np.asarray(arrays["high"], float), np.asarray(arrays["low"], float),
                                np.asarray(arrays["close"], float), arrays["day_id"],
                                arrays["index"], p["gate_tf_min"], p["gate_len"], p["gate_ratio"])


@pytest.mark.skipif(not _LOCAL, reason="the box backup and the PC 5m cache are local files")
def test_the_30_min_trap_on_the_four_real_entries(tmp_path):
    paths = _pc_home(tmp_path)
    cfg = _noise_cfg(paths)
    df = cs.historical_bars("5m", paths)
    rows = {r["ref_time"][:16]: r for r in _box_rows()}
    for key in TRAP:
        r = rows[key]
        ref = pd.Timestamp(r["ref_time"])
        arrays = cs.closed_arrays(df, (ref + pd.Timedelta(seconds=10)).to_pydatetime(), "5m",
                                  cs.leg_warmup_sessions(cfg))
        n = len(arrays["close"])
        probe = cs._stand_in_arrays(arrays, "5m")
        closed, stand_in = bool(_comp(cfg, arrays)[n - 1]), bool(_comp(cfg, probe)[n - 1])
        assert closed != stand_in, key
        parts = cs._noise_size_parts(cfg, probe, n - 1, n)
        assert parts["sq30"] is stand_in
        assert parts["plugin"] == pytest.approx(float(r["size"]) / float(r["keel_size"])), key


# ── 3. the 30-min trap, synthetic ───────────────────────────────────────────────────────

def test_the_30_min_trap_synthetic():
    """A random tape whose volatility changes by the half hour: some mid-group bar D reads a
    different 30-min squeeze on the closed arrays than on the stand-ins; the preview made one
    bar earlier and this bar's own size both read the stand-in value."""
    rng = np.random.default_rng(11)
    rows, px = [], 500.0
    for d in _sessions(8):
        base = pd.Timestamp(f"{d} 09:30", tz=cs.TZ)
        for i in range(78):
            sd = 0.0003 if (i // 6) % 3 else 0.004
            o, c = px, px * (1 + rng.normal(0, sd))
            rows.append({"time": int((base + pd.Timedelta(minutes=5 * i)).timestamp()),
                         "open": o, "high": max(o, c) * 1.0002, "low": min(o, c) * 0.9998,
                         "close": c, "volume": 1000.0})
            px = c
    df = pd.DataFrame(rows)
    cfg = _noise_cfg(cs._paths(home="unused"))
    found = 0
    for day in _sessions(3):
        for i in range(2, 77):
            if (i + 1) % 6 == 0:
                continue                                        # D closes its group: no trap
            hhmm = (pd.Timestamp("2000-01-01 09:30") + pd.Timedelta(minutes=5 * i)).strftime("%H:%M")
            arrays = cs.closed_arrays(df, _after(hhmm, str(day)), "5m", 20)
            n = len(arrays["close"])
            probe2 = cs._stand_in_arrays(arrays, "5m")
            closed, stand_in = bool(_comp(cfg, arrays)[n - 1]), bool(_comp(cfg, probe2)[n - 1])
            if closed == stand_in:
                continue
            found += 1
            assert cs._noise_size_parts(cfg, probe2, n - 1, n)["plugin"] == (2.0 if stand_in else 1.0)
            prev = (pd.Timestamp(f"2000-01-01 {hhmm}") - pd.Timedelta(minutes=5)).strftime("%H:%M")
            arr1 = cs.closed_arrays(df, _after(prev, str(day)), "5m", 20)
            n1 = len(arr1["close"])
            nxt = cs._noise_size_parts(cfg, cs._stand_in_arrays(arr1, "5m", pads=3), n1, n1 + 1)
            assert nxt["sq30"] is stand_in
    assert found >= 3, "the tape never sprang the trap -- nothing was proven"


# ── 4. no side effects ──────────────────────────────────────────────────────────────────

def test_the_tick_writes_only_the_sidecar(tmp_path, monkeypatch):
    df = _tape(n=65, today=_jump("10:00", 0.01))
    paths = _home(tmp_path, df)
    legs = _legs(paths)
    cs.step(now=_after("09:50"), legs=legs, paths=paths, fetch=False)
    cs.step(now=_after("09:55"), legs=legs, paths=paths, fetch=False)
    w = {}
    events = cs.step(now=_after("10:00"), legs=legs, paths=paths, fetch=False, warnings=w)
    assert [e["event"] for e in events] == ["ENTRY"]
    sd = paths["state_dir"]
    before = {f: open(os.path.join(sd, f), "rb").read() for f in os.listdir(sd)}

    def boom(*_a, **_k):
        raise AssertionError("the preview must never call this")
    for name in ("_record_keel_xrows", "_note_keel_entries", "_keel_entry_extras",
                 "_keel_xrow_record", "_append_signals", "_write_state", "_diff_leg"):
        monkeypatch.setattr(cs, name, boom)
    seen = []
    real = cs._keel_size_for_entry

    def spy(*a, **k):
        seen.append(k.get("log"))
        return real(*a, **k)
    monkeypatch.setattr(cs, "_keel_size_for_entry", spy)
    assert cs._next_entry_tick(_after("10:00"), events, warnings=w, paths=paths) is None
    doc = cs._next_entry_tick(_after("10:00", sec=320), [], warnings=w, paths=paths)
    assert doc["legs"]["NOISE_382"]["check"]["match"] is True
    assert set(doc["legs"]) == {"NOISE_382", "ORB_R6"}
    after = set(os.listdir(sd))
    assert after - set(before) == {cs.NEXT_ENTRY_FILE}
    for f, raw in before.items():
        assert open(os.path.join(sd, f), "rb").read() == raw, f
    assert seen and all(lg is cs._ne_quiet for lg in seen)


# ── 5. exception isolation ──────────────────────────────────────────────────────────────

def test_a_failing_leg_is_an_error_row_and_the_other_leg_is_still_written(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "10:20", _legs(paths))

    def boom(*_a, **_k):
        raise RuntimeError("kaboom\nsecond line")
    monkeypatch.setattr(cs, "_noise_next_entry", boom)
    doc = cs._next_entry_tick(now, [], paths=paths)
    noise = doc["legs"]["NOISE_382"]
    assert noise == {"status": "error", "why": "RuntimeError: kaboom second line",
                     "bar": "2026-10-20T10:20:00-04:00", "bar_close": "2026-10-20T10:25:00-04:00"}
    assert doc["legs"]["ORB_R6"]["status"] not in ("error", None)
    assert cs.read_next_entry(paths) == doc


def test_a_failing_preview_writes_nothing_and_logs_once_per_ten_minutes(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    old = {"v": 1, "computed_at": "2026-10-20T10:15:31-04:00", "legs": {}}
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(cs.next_entry_path(paths), "w", encoding="utf-8") as f:
        json.dump(old, f)
    raw = open(cs.next_entry_path(paths), "rb").read()
    now, _ = _stash(paths, df, "10:20", _legs(paths))

    calls = []

    def boom(*_a, **_k):
        calls.append(1)
        raise RuntimeError("kaboom")
    monkeypatch.setattr(cs, "next_entry_preview", boom)
    logs = []
    for _ in range(3):                      # one try per bar: the same bar is never retried
        assert cs._next_entry_tick(now, [], paths=paths, log=logs.append) is None
    assert len(calls) == 1
    assert open(cs.next_entry_path(paths), "rb").read() == raw
    assert logs == ["[cloud-signal] next-entry preview failed (RuntimeError: kaboom) -- the "
                    "board keeps the last estimate"]
    for hhmm in ("10:25", "10:30"):        # each new bar tries once, inside the 10 min
        now, _ = _stash(paths, df, hhmm, _legs(paths))
        cs._next_entry_tick(now, [], paths=paths, log=logs.append)
    assert len(calls) == 3 and len(logs) == 1
    cs._NEXT_ENTRY_MEMO[paths["state_dir"]]["err"]["last"] -= cs.NEXT_ENTRY_ERROR_LOG_EVERY_SEC
    now, _ = _stash(paths, df, "10:35", _legs(paths))
    cs._next_entry_tick(now, [], paths=paths, log=logs.append)
    assert len(logs) == 2 and logs[1].endswith("[+2 more since the last line]")


def test_a_failed_replace_is_logged_and_never_raises(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "10:20", _legs(paths))
    budgets = []
    monkeypatch.setattr(cs.qp, "_replace_with_retry",
                        lambda *a, **k: budgets.append(k.get("retries")) or False)
    logs = []
    assert cs._next_entry_tick(now, [], paths=paths, log=logs.append) is None
    assert len(logs) == 1 and "could not replace" in logs[0]
    assert not os.path.exists(cs.next_entry_path(paths))
    # a display file gets a short budget (0.2 s), never the shared 2.5 s one
    assert budgets == [cs.NEXT_ENTRY_REPLACE_RETRIES] and cs.NEXT_ENTRY_REPLACE_RETRIES * 0.05 <= 0.2


def test_a_failed_write_is_tried_once_per_bar_and_logs_no_check(tmp_path, monkeypatch):
    """A failed sidecar write after a NOISE entry: the 1-s ticks of that bar never recompute
    (one preview), the parity line is never logged for a file that was not written, and the
    next bar computes again."""
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "10:20", _legs(paths))
    calls = []
    real = cs.next_entry_preview

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(cs, "next_entry_preview", spy)
    real_write = cs._write_next_entry
    monkeypatch.setattr(cs, "_write_next_entry", lambda *_a, **_k: False)
    entry = {"leg": "NOISE_382", "event": "ENTRY", "trade_id": "NOISE_382-T1",
             "ref_time": "2026-10-20T10:25:00-04:00", "size": 1.0, "keel_size": 1.0,
             "reason": "decide_at_close: ..."}
    logs = []
    assert cs._next_entry_tick(now, [entry], paths=paths, log=logs.append) is None
    for s in range(10):
        later = now + _dt.timedelta(seconds=cs.NEXT_ENTRY_ORDER_HOLD_SEC + s)
        assert cs._next_entry_tick(later, [], paths=paths, log=logs.append) is None
    mem = cs._NEXT_ENTRY_MEMO[paths["state_dir"]]
    assert len(calls) == 1 and mem["pending"] == []
    assert [m for m in logs if "next-entry check" in m] == []
    assert len([m for m in logs if "preview failed" in m]) == 1
    monkeypatch.setattr(cs, "_write_next_entry", real_write)
    now, _ = _stash(paths, df, "10:25", _legs(paths))
    assert cs._next_entry_tick(now, [], paths=paths, log=logs.append) is not None
    assert len(calls) == 2


# ── 6. the order-tick rule ──────────────────────────────────────────────────────────────

def test_an_order_tick_defers_and_the_next_tick_records_the_check(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, kept = _stash(paths, df, "10:20", _legs(paths))
    calls = []
    real = cs.next_entry_preview

    def spy(*a, **k):
        calls.append(k.get("pending"))
        return real(*a, **k)
    monkeypatch.setattr(cs, "next_entry_preview", spy)
    entry = {"leg": "NOISE_382", "event": "ENTRY", "trade_id": "NOISE_382-T1",
             "ref_time": "2026-10-20T10:25:00-04:00", "size": 99.0, "keel_size": 1.0,
             "reason": "decide_at_close: ..."}
    for rows in ([entry], [{"leg": "ORB_R6", "event": "EXIT"}],
                 [{"leg": "DIP_424", "event": "ENTRY"}], [{"leg": "ORB_R6", "event": "LEVELS"}]):
        assert cs._next_entry_tick(now, rows, paths=paths) is None
    assert calls == [] and not os.path.exists(cs.next_entry_path(paths))
    mem = cs._NEXT_ENTRY_MEMO[paths["state_dir"]]
    assert [p["trade_id"] for p in mem["pending"]] == ["NOISE_382-T1"]
    # the 1-s hand-off ticks inside two executor ticks (2 x 5 s) of the last order row wait
    hold = cs.NEXT_ENTRY_ORDER_HOLD_SEC
    for s in (1, 5, hold - 1):
        assert cs._next_entry_tick(now + _dt.timedelta(seconds=s), [], paths=paths) is None
    assert calls == [] and [p["trade_id"] for p in mem["pending"]] == ["NOISE_382-T1"]
    logs = []
    doc = cs._next_entry_tick(now + _dt.timedelta(seconds=hold), [], paths=paths, log=logs.append)
    assert len(calls) == 1 and mem["pending"] == []
    chk = doc["legs"]["NOISE_382"]["check"]
    arrays = kept["NOISE_382"]["arrays"]
    n = len(arrays["close"])
    this_bar = cs._noise_size_parts(kept["NOISE_382"]["cfg"], cs._stand_in_arrays(arrays, "5m"),
                                    n - 1, n)["size"]
    assert chk["preview"] == pytest.approx(this_bar) and chk["actual"] == 99.0
    assert chk["match"] is False and chk["bar"] == "10:20" and chk["board"] is None
    assert logs[-1].endswith("vs actual 99.0 -- MISMATCH")
    # a later preview with no new entry carries the newest record forward
    _stash(paths, df, "10:25", _legs(paths))
    later = cs._next_entry_tick(_after("10:25"), [], paths=paths)
    assert later["legs"]["NOISE_382"]["check"] == chk


def test_a_clock_that_steps_back_never_stretches_the_hold(tmp_path):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "10:20", _legs(paths, orb=False))
    ahead = now + _dt.timedelta(hours=1)           # the order tick read a clock an hour fast
    assert cs._next_entry_tick(ahead, [{"leg": "ORB_R6", "event": "EXIT"}], paths=paths) is None
    assert cs._next_entry_tick(now, [], paths=paths) is not None


def test_an_entry_from_another_bar_gets_no_preview(tmp_path):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "10:20", _legs(paths, orb=False))
    cs._next_entry_tick(now, [{"leg": "NOISE_382", "event": "ENTRY", "trade_id": "T0",
                               "ref_time": "2026-10-20T10:15:00-04:00", "size": 1.0}],
                        paths=paths)
    later = now + _dt.timedelta(seconds=cs.NEXT_ENTRY_ORDER_HOLD_SEC)
    chk = cs._next_entry_tick(later, [], paths=paths)["legs"]["NOISE_382"]["check"]
    assert chk["preview"] is None and chk["match"] is None and chk["bar"] == "10:10"


def _seed_ledger(paths):
    """signals.csv as the box has it before an order row: a SEED line under the full header."""
    cs._append_signals([{"emitted_at": "2026-10-20T09:31:00-04:00", "leg": "NOISE_382",
                         "event": "SEED", "reason": "cold start"}], paths)


def _stream_entry(paths, df, hhmm, tid="NOISE_382-T9"):
    """The ENTRY row a stream commit writes for a NOISE decision at the close of the bar
    starting hhmm: straight into signals.csv (cloud_signal_stream.py), never through step()'s
    events -- sized exactly as _diff_leg sizes it."""
    cfg = _noise_cfg(paths)
    arrays = _arrays(df, hhmm, cfg)
    n = len(arrays["close"])
    probe = cs._stand_in_arrays(arrays, "5m")
    row = {"emitted_at": _after(hhmm).isoformat(), "leg": "NOISE_382", "event": "ENTRY",
           "side": "long", "ref_time": probe["index"][n].isoformat(), "ref_price": 500.0,
           "reason": "decide_at_close: ...", "bar_source": "stream", "trade_id": tid,
           "size": cs._noise_size_parts(cfg, probe, n - 1, n)["size"], "keel_size": 1.0}
    cs._append_signals([row], paths)
    return row


def test_a_stream_commit_defers_like_an_order_tick(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    _seed_ledger(paths)
    now, _ = _stash(paths, df, "10:15", _legs(paths))
    assert cs._next_entry_tick(now, [], warnings=_health("10:15"), paths=paths) is not None
    mem = cs._NEXT_ENTRY_MEMO[paths["state_dir"]]
    assert mem["sig_size"] == os.path.getsize(paths["signals_path"])
    calls, loads = [], []
    real_preview, real_load = cs.next_entry_preview, cs._next_entry_self_load
    monkeypatch.setattr(cs, "next_entry_preview",
                        lambda *a, **k: calls.append(sorted(a[1])) or real_preview(*a, **k))
    monkeypatch.setattr(cs, "_next_entry_self_load",
                        lambda *a, **k: loads.append(a[0]) or real_load(*a, **k))
    # the stream committed the 10:20 bar: its ENTRY is in signals.csv, step() returned no
    # events and stashed nothing new, and bar_health already shows the 10:20 bar
    row = _stream_entry(paths, df, "10:20")
    logs = []
    assert cs._next_entry_tick(_after("10:20"), [], warnings=_health("10:20"), paths=paths,
                               log=logs.append) is None
    assert calls == [] and loads == [] and mem["loaded"] == {}
    assert [p["trade_id"] for p in mem["pending"]] == [row["trade_id"]]
    assert mem["pending"][0]["size"] == str(row["size"])            # the CSV copy: text
    # 1 s and 9 s later (the hand-off polling): still inside the hold, no self-load either
    for sec in (311, 319):
        assert cs._next_entry_tick(_after("10:20", sec=sec), [], warnings=_health("10:20"),
                                   paths=paths, log=logs.append) is None
    assert calls == [] and loads == [] and mem["loaded"] == {}
    doc = cs._next_entry_tick(_after("10:20", sec=320), [], warnings=_health("10:20"),
                              paths=paths, log=logs.append)
    assert loads == ["NOISE_382", "ORB_R6"] and len(calls) == 1 and mem["pending"] == []
    chk = doc["legs"]["NOISE_382"]["check"]
    assert chk["tid"] == row["trade_id"] and chk["bar"] == "10:20" and chk["match"] is True
    assert chk["preview"] == pytest.approx(row["size"]) and chk["actual"] == pytest.approx(row["size"])
    assert [m for m in logs if "next-entry check" in m] == [
        f"[cloud-signal] next-entry check NOISE_382 {row['trade_id']}: preview "
        f"{chk['preview']:g} vs actual {chk['actual']} -- match"]
    # the same ENTRY in both this tick's events and the file is kept once, the events copy
    row2 = _stream_entry(paths, df, "10:20", tid="NOISE_382-T10")
    assert cs._next_entry_tick(_after("10:20", sec=322), [dict(row2)], paths=paths) is None
    assert mem["pending"] == [{k: row2[k] for k in ("trade_id", "ref_time", "size", "keel_size",
                                                    "reason")}]


def test_a_non_order_row_does_not_defer(tmp_path):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    _seed_ledger(paths)
    now, _ = _stash(paths, df, "10:15", _legs(paths))
    assert cs._next_entry_tick(now, [], paths=paths) is not None
    _seed_ledger(paths)                                       # grown, but by a SEED row
    now, _ = _stash(paths, df, "10:20", _legs(paths))
    doc = cs._next_entry_tick(now, [], paths=paths)
    assert doc is not None and doc["legs"]["NOISE_382"]["bar"] == "2026-10-20T10:20:00-04:00"
    assert cs._NEXT_ENTRY_MEMO[paths["state_dir"]]["pending"] == []


def test_a_shrunk_or_rewritten_signals_file_is_read_quietly(tmp_path):
    paths = cs._paths(home=str(tmp_path / "sig"))
    path = paths["signals_path"]
    mem = {}
    assert cs._ne_new_signal_rows(paths, mem) == [] and mem["sig_size"] is None   # no file
    _seed_ledger(paths)
    assert cs._ne_new_signal_rows(paths, mem) == []                               # first call
    assert mem["sig_size"] == os.path.getsize(path)
    assert cs._ne_new_signal_rows(paths, mem) == []                               # no growth

    def ledger(rows):
        cs._append_signals([{"leg": "NOISE_382", "event": e, "trade_id": t} for e, t in rows], paths)
    ledger([("ENTRY", "T1"), ("EXIT", "T1")])
    assert [(r["event"], r["trade_id"]) for r in cs._ne_new_signal_rows(paths, mem)] == [
        ("ENTRY", "T1"), ("EXIT", "T1")]
    # truncated smaller (a rewrite): nothing, and the new size is the baseline
    raw = open(path, "rb").read()
    with open(path, "wb") as f:
        f.write(raw[:raw.index(b"\n") + 1])
    assert cs._ne_new_signal_rows(paths, mem) == [] and mem["sig_size"] == os.path.getsize(path)
    # growth that starts mid-line (rows moved under it): the partial first line is dropped
    ledger([("ENTRY", "T2")])
    mid = os.path.getsize(path) - 5
    ledger([("ENTRY", "T3")])
    mem["sig_size"] = mid
    assert [r["trade_id"] for r in cs._ne_new_signal_rows(paths, mem)] == ["T3"]
    # a real header upgrade: an older (prefix) header is rewritten under the new one, which
    # moves every row; whatever comes back is whole rows, the new one last
    old = cs.SIGNAL_COLS[:10]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        for i in range(5):
            w.writerow({"emitted_at": f"2026-10-20T09:3{i}:00-04:00", "leg": "ORB_R6",
                        "event": "SEED", "trade_id": ""})
    cs._ne_new_signal_rows(paths, mem)
    ledger([("ENTRY", "T4")])
    assert cs._read_signals_header(path) == cs.SIGNAL_COLS
    got = cs._ne_new_signal_rows(paths, mem)
    assert got and got[-1]["trade_id"] == "T4"
    assert all(r["leg"] in ("ORB_R6", "NOISE_382") and r["event"] in ("SEED", "ENTRY") for r in got)
    # growth that cannot be read: None, and the tick waits once, as for an order row
    df = _tape(n=65)
    home = _home(tmp_path, df, "tick")
    _seed_ledger(home)
    now, _ = _stash(home, df, "10:15", _legs(home, orb=False))
    assert cs._next_entry_tick(now, [], paths=home) is not None
    with open(home["signals_path"], "ab") as f:
        f.write(b"\xff\xfe not utf-8\n")
    hm = cs._NEXT_ENTRY_MEMO[home["state_dir"]]
    before = hm["sig_size"]
    assert cs._ne_new_signal_rows(home, dict(hm, sig_size=before)) is None
    now, _ = _stash(home, df, "10:20", _legs(home, orb=False))
    logs = []
    assert cs._next_entry_tick(now, [], paths=home, log=logs.append) is None
    assert logs == [] and hm["sig_size"] == os.path.getsize(home["signals_path"])
    later = now + _dt.timedelta(seconds=cs.NEXT_ENTRY_ORDER_HOLD_SEC)
    doc = cs._next_entry_tick(later, [], paths=home, log=logs.append)
    assert doc["legs"]["NOISE_382"]["bar"] == "2026-10-20T10:20:00-04:00" and logs == []


# ── 7. cadence ──────────────────────────────────────────────────────────────────────────

def test_once_per_bar_and_one_self_load_for_a_stream_gap(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    legs = _legs(paths)
    calls, loads = [], []
    real_preview, real_load = cs.next_entry_preview, cs._next_entry_self_load
    monkeypatch.setattr(cs, "next_entry_preview",
                        lambda *a, **k: calls.append(sorted(a[1])) or real_preview(*a, **k))
    monkeypatch.setattr(cs, "_next_entry_self_load",
                        lambda *a, **k: loads.append(a[0]) or real_load(*a, **k))
    now, _ = _stash(paths, df, "10:20", legs)
    cs._next_entry_tick(now, [], warnings=_health("10:20"), paths=paths)
    cs._next_entry_tick(now, [], warnings=_health("10:20"), paths=paths)
    assert calls == [["NOISE_382", "ORB_R6"]] and loads == []
    now, _ = _stash(paths, df, "10:25", legs)
    cs._next_entry_tick(now, [], warnings=_health("10:25"), paths=paths)
    assert len(calls) == 2
    # the stream committed 10:30 first: step() skipped both legs, the stash is a bar behind
    now = _after("10:30")
    for _ in range(3):
        doc = cs._next_entry_tick(now, [], warnings=_health("10:30"), paths=paths)
    assert loads == ["NOISE_382", "ORB_R6"] and len(calls) == 3
    assert doc is None
    doc = cs.read_next_entry(paths)
    assert doc["legs"]["NOISE_382"]["bar"] == "2026-10-20T10:30:00-04:00"
    assert doc["legs"]["ORB_R6"]["bar"] == "2026-10-20T10:30:00-04:00"


def test_a_bar_from_another_day_is_never_previewed(tmp_path, monkeypatch):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    _stash(paths, df, "15:50", _legs(paths), day="2026-10-19")
    loads = []
    monkeypatch.setattr(cs, "_next_entry_self_load", lambda *a, **k: loads.append(a) or None)
    morning = pd.Timestamp(f"{LAST} 09:31", tz=cs.TZ).to_pydatetime()
    assert cs._next_entry_tick(morning, [], warnings=_health("15:55", "2026-10-19"),
                               paths=paths) is None
    assert loads == [] and not os.path.exists(cs.next_entry_path(paths))


def test_a_leg_not_due_is_copied_from_the_last_file(tmp_path):
    df = _tape(n=65)
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "10:20", _legs(paths))
    first = cs._next_entry_tick(now, [], paths=paths)
    now, _ = _stash(paths, df, "10:25", {"NOISE_382": _noise_cfg(paths)})
    second = cs._next_entry_tick(now, [], paths=paths)
    assert second["legs"]["ORB_R6"] == first["legs"]["ORB_R6"]
    assert second["legs"]["NOISE_382"]["bar"] == "2026-10-20T10:25:00-04:00"


# ── 8. the status machine ───────────────────────────────────────────────────────────────

def _noise(df, hhmm, paths, trades=(), day=LAST):
    cfg = _noise_cfg(paths)
    return cs._noise_next_entry(cfg, _arrays(df, hhmm, cfg, day), list(trades), "5m",
                                _after(hhmm, day), paths)


def _orb(df, hhmm, paths, trades=(), day=LAST):
    cfg = dict(cs.CROWN_LEGS["ORB_R6"])
    return cs._orb_next_entry(cfg, _arrays(df, hhmm, cfg, day), list(trades), "5m",
                              _after(hhmm, day), paths)


def test_noise_ok_fields_follow_the_strategy(tmp_path):
    df = _tape()
    paths = _home(tmp_path, df)
    leg = _noise(df, "10:35", paths)
    assert leg["status"] == "ok" and leg["why"] is None
    assert (leg["bar"], leg["bar_close"]) == ("2026-10-20T10:35:00-04:00", "2026-10-20T10:40:00-04:00")
    nx = leg["next"]
    assert (nx["decide_bar"], nx["decide_close"], nx["fill_bar"]) == ("10:40", "10:45", "10:45")
    assert nx["size"] == pytest.approx(nx["plugin"] * nx["keel"])
    assert leg["range_today"] == {"lo": 1.0, "hi": 3.0}
    assert leg["next_session"] == {"date": "2026-10-21", "lo": 1.0, "hi": 3.0, "fri": False,
                                   "fomc": False}
    # the bands and the stop set at the fill, by NOISE_1_0.py's own arithmetic
    cfg = _noise_cfg(paths)
    mod = cs._strategy_module_for_sizing(cfg["strategy"])
    n10, F = mod._base._base, mod._FROZEN
    arrays = _arrays(df, "10:35", cfg)
    o, c = arrays["open"], arrays["close"]
    sb = n10._session_bounds(arrays["day_id"], len(c))
    si, (a, _b) = len(sb) - 1, sb[-1]
    sig = n10._sigma_matrix(o, c, sb, F["lookback"])
    ref = max(o[a], c[sb[si - 1][1] - 1])
    kn = len(c) - a
    assert leg["long"]["trigger"] == round(ref * (1 + 0.75 * sig[si, kn]), 2)
    assert leg["long"]["stop_dist"] == round(1.75 * ref * 0.75 * sig[si, kn + 1], 4)
    assert leg["short"]["stop_dist"] == pytest.approx(2 * leg["long"]["stop_dist"] * leg["ref_lo"]
                                                      / leg["ref_hi"], abs=2e-4)
    assert leg["long"]["stop_est"] == pytest.approx(leg["long"]["trigger"] - leg["long"]["stop_dist"],
                                                    abs=0.0101)        # from the unrounded trigger
    assert leg["vwap"] == pytest.approx(c[-1], abs=0.01) and leg["px"] == round(c[-1], 2)
    assert leg["exit_rule"] == (f"Out at the next open after a 5-min close back across VWAP (now "
                                f"{leg['vwap']:.2f}), after a bar touches the stop (1.75x the band "
                                f"width), or at the close. No target.")
    assert leg["long"]["basis"] == leg["short"]["basis"] == (
        "1.75x the band width from the fill (the next bar open); not checked on the fill bar")
    for txt in (leg["exit_rule"], leg["long"]["basis"]):
        assert len(txt) <= cs.NEXT_ENTRY_TEXT_MAX and "\n" not in txt


def test_noise_may_change_names_the_groups_that_close_with_the_bar(tmp_path):
    df = _tape()
    paths = _home(tmp_path, df)
    assert _noise(df, "09:50", paths)["next"]["may_change"] == ["sq30"]          # D+1 = 09:55
    assert _noise(df, "10:20", paths)["next"]["may_change"] == ["sq30", "sq60"]  # D+1 = 10:25
    assert _noise(df, "10:50", paths)["next"]["may_change"] == ["sq30"]          # D+1 = 10:55
    for hhmm in ("10:15", "10:30", "10:45"):
        assert _noise(df, hhmm, paths)["next"]["may_change"] == [], hhmm


def test_noise_last_decision_and_no_more_today(tmp_path):
    df = _tape()
    paths = _home(tmp_path, df)
    leg = _noise(df, "15:45", paths)
    assert leg["status"] == "ok" and leg["next"]["decide_bar"] == "15:50"
    assert leg["range_today"]["lo"] == 1.0
    leg = _noise(df, "15:50", paths)
    assert (leg["status"], leg["next"], leg["long"], leg["range_today"]) == ("no_more_today", None, None, None)
    assert leg["next_session"]["date"] == "2026-10-21"


def test_noise_in_trade_and_warming(tmp_path):
    df = _tape()
    paths = _home(tmp_path, df)
    leg = _noise(df, "10:35", paths, trades=[{"still_open": True}])
    assert leg["status"] == "in_trade" and leg["next"] is None and leg["vwap"] is not None
    short = _tape(n=30)
    leg = _noise(short, "10:35", _home(tmp_path, short, "short"))
    assert (leg["status"], leg["why"]) == ("warming", "history")


def _trend_day(pct):
    def fn(i, px):
        c = px * (1 + pct / 78)
        return px, max(px, c), min(px, c), c
    return fn


def test_noise_vol_skip_day_is_blocked(tmp_path):
    df = _tape(n=66, prior=_trend_day(0.06))
    paths = _home(tmp_path, df)
    leg = _noise(df, "10:35", paths)
    assert (leg["status"], leg["why"]) == ("day_blocked", "vol_skip")
    assert leg["vol_pct"] >= 95 and leg["next"] is None and leg["long"] is None


def test_noise_no_shorts_after_a_close_at_the_bottom_of_the_range(tmp_path):
    df = _tape(prior=_trend_day(-0.02))
    paths = _home(tmp_path, df)
    leg = _noise(df, "10:35", paths)
    assert leg["status"] == "ok" and leg["long"]["ok"] is True
    assert (leg["short"]["ok"], leg["short"]["why"]) == (False, "longs_only")


def _orb_day(direction=1, breakout_at=None, vol=1000.0):
    """today(): a 09:30 / 09:35 opening range around the prior close (first candle up for
    direction 1), flat at its middle, then the bar starting `breakout_at` closing far past it."""
    k_out = None if breakout_at is None else (
        pd.Timestamp(f"2000-01-01 {breakout_at}") - pd.Timestamp("2000-01-01 09:30")).seconds // 300

    def fn(i, px0):
        base = fn.base = getattr(fn, "base", None) or px0
        if i == 0:
            return base, base + 0.6, base - 0.6, base + 0.5 * direction, vol
        if i == 1:
            return base + 0.5 * direction, base + 0.8, base - 0.6, base + 0.3 * direction, vol
        if k_out is not None and i == k_out:
            c = base + 5.0 * direction
            return base + 0.1, max(base, c), min(base, c), c, vol
        return base + 0.1, base + 0.15, base + 0.05, base + 0.1, vol
    return fn


def test_orb_range_pending_then_the_level(tmp_path):
    df = _tape(n=65, today=_orb_day(1))
    paths = _home(tmp_path, df)
    leg = _orb(df, "09:30", paths)
    assert leg["status"] == "range_pending"
    assert leg["next"] == {"decide_bar": "09:35", "decide_close": "09:40"}
    assert all(leg[k] is None for k in ("dir", "trigger", "risk", "stop_est", "target_est", "be_est"))
    # the side is not known before the range sets: the breakeven move is "in its favour"
    assert leg["exit_rule"] == ("Stop 2.5x the opening range from the entry close, target 5x "
                                "that; stop to the entry once a close is 0.5x that in its favour. "
                                "Out at the close.")
    assert leg["basis"] == "2.5x the opening range from the entry close"
    leg = _orb(df, "09:40", paths)
    base = df["open"].iloc[-78]
    or_hi, or_lo = base + 0.8, base - 0.6
    rng = or_hi - or_lo
    assert leg["dir"] == "long" and leg["rng"] == pytest.approx(rng, abs=1e-4)
    assert leg["trigger"] == round(or_hi + 0.25 * rng, 2)
    assert leg["risk"] == pytest.approx(2.5 * rng, abs=1e-4)
    trig = or_hi + 0.25 * rng
    assert leg["stop_est"] == cs._cent_level(trig - 2.5 * rng, up=False)
    assert leg["target_est"] == cs._cent_level(trig + 5 * 2.5 * rng, up=True)
    assert leg["be_est"] == round(trig + 0.5 * 2.5 * rng, 2)
    assert (leg["size"], leg["target_r"], leg["be_r"]) == (1.0, 5.0, 0.5)
    assert leg["exit_rule"] == (f"Stop {2.5 * rng:.2f} a share from the entry close (2.5x the "
                                f"opening range), target 5x that; stop to the entry once a close "
                                f"is {1.25 * rng:.2f} up. Out at the close.")
    assert leg["basis"] == "2.5x the opening range from the entry close"
    # where the stop lives is the executor's orb_resting mode (log_only on the box), never
    # this text's to say
    assert "rest" not in (leg["exit_rule"] + leg["basis"]).lower()
    assert leg["next"] == {"decide_bar": "09:45", "decide_close": "09:50"}
    # a short day: the breakeven arms on a close that far DOWN (ORB_3_6.py: sc[k] <= be_lvl)
    short = _tape(n=65, today=_orb_day(-1))
    leg = _orb(short, "09:40", _home(tmp_path, short, "s"))
    assert (leg["dir"], leg["risk"]) == ("short", 3.5)
    assert leg["be_est"] == pytest.approx(leg["trigger"] - 1.75, abs=0.011)
    assert leg["exit_rule"] == ("Stop 3.50 a share from the entry close (2.5x the opening range), "
                                "target 5x that; stop to the entry once a close is 1.75 down. Out "
                                "at the close.")


def test_orb_s_risk_is_worked_out_from_the_4dp_range(tmp_path):
    """A half-cent opening range with a tail past 4 dp (Webull's bars carry sub-cent prices):
    the range at 4 dp (1.83504 -> 1.835), the risk a share FROM it (2.5 x 1.835 = 4.5875, never
    2.5 x 1.83504 = 4.5876), and the exit rule in the board's own up-to-4-dp form, so the Max
    loss row's "2.5x the opening range of 1.835", its $4.5875 and the exit rule's "Stop 4.5875"
    all agree. The levels keep the UNROUNDED range, as the live engine's (ORB_3_6.py: risk =
    stop_frac * rng): here that is a cent lower than the rounded risk would give."""
    def half_cent(i, px):
        base = half_cent.base = getattr(half_cent, "base", None) or round(px, 2)
        if i == 0:                                 # or_hi base + 1.00872, or_lo base - 0.82632
            return base, base + 1.00872, base - 0.82632, base + 0.5
        if i == 1:
            return base, base + 0.1, base - 0.2, base + 0.1
        return None
    df = _tape(n=65, today=half_cent)
    leg = _orb(df, "09:40", _home(tmp_path, df))
    assert (leg["dir"], leg["rng"], leg["risk"]) == ("long", 1.835, 4.5875)
    assert leg["exit_rule"] == ("Stop 4.5875 a share from the entry close (2.5x the opening range), "
                                "target 5x that; stop to the entry once a close is 2.2938 up. Out "
                                "at the close.")
    base = half_cent.base
    rng = 1.00872 + 0.82632
    trig = base + 1.00872 + 0.25 * rng
    # trig - 4.5876 = base - 3.12012 floors to base - 3.13; trig - 4.5875 would snap to base - 3.12
    assert leg["stop_est"] == cs._cent_level(trig - 2.5 * rng, up=False) == round(base - 3.13, 2)
    assert cs._cent_level(trig - leg["risk"], up=False) == round(base - 3.12, 2)
    assert [cs._ne_dist(v) for v in (4.6, 4.575, 4.5875, 5.725, 4.0, 123.45)] == [
        "4.60", "4.575", "4.5875", "5.725", "4.00", "123.45"]


def test_orb_can_fire_matches_the_real_later_entry(tmp_path):
    df = _tape(n=65, today=_orb_day(1, breakout_at="10:00"))
    paths = _home(tmp_path, df)
    for hhmm in ("09:40", "09:50", "09:55"):
        leg = _orb(df, hhmm, paths)
        assert (leg["status"], leg["why"]) == ("ok", None), hhmm
        assert leg["pace"] == pytest.approx(1.0)
    cfg = dict(cs.CROWN_LEGS["ORB_R6"])
    arrays = _arrays(df, "10:00", cfg)
    got = cs.run_leg_trades(cfg, arrays, leg_key="ORB_R6", log=cs._ne_quiet, now=_after("10:00"),
                            paths=paths, fetch=False)
    n = len(arrays["close"])
    assert [(t["entry_bar"], t["side"]) for t in got if t["entry_time"].startswith(LAST)] == [(n - 1, "long")]
    assert arrays["close"][-1] > leg["trigger"] > max(arrays["close"][-6:-1])
    # once it traded, the day is done
    trades = [t for t in got if t["entry_time"].startswith(LAST)]
    assert _orb(df, "10:05", paths, trades=trades)["status"] in ("in_trade", "traded_today")
    closed = [dict(t, still_open=False) for t in trades]
    leg = _orb(df, "10:05", paths, trades=closed)
    assert leg["status"] == "traded_today" and leg["next"] is None
    assert _orb(df, "10:05", paths, trades=[dict(t, still_open=True) for t in trades])["status"] == "in_trade"


def test_orb_paused_on_a_thin_tape_and_never_on_the_last_bar(tmp_path):
    df = _tape(n=65, today=_orb_day(1, vol=300.0))
    paths = _home(tmp_path, df)
    leg = _orb(df, "09:50", paths)
    assert (leg["status"], leg["why"]) == ("paused", "pace") and leg["pace"] == pytest.approx(0.3)
    assert leg["next"] == {"decide_bar": "09:55", "decide_close": "10:00"}
    full = _tape(n=65, today=_orb_day(1))
    leg = _orb(full, "15:50", _home(tmp_path, full, "f"))
    assert leg["status"] == "no_more_today" and leg["next"] is None


def test_orb_day_gates(tmp_path):
    quiet = _tape(n=65, quiet=5, today=_orb_day(1))
    leg = _orb(quiet, "09:50", _home(tmp_path, quiet, "q"))
    assert (leg["status"], leg["why"]) == ("day_blocked", "low_range")
    half = _tape(n=65, last="2026-11-27", today=_orb_day(1))
    leg = _orb(half, "09:50", _home(tmp_path, half, "h"), day="2026-11-27")
    assert (leg["status"], leg["why"]) == ("day_blocked", "half_day")


def _scaled(df, last_close):
    """`df` with every price scaled so its last close is `last_close`."""
    out = df.copy()
    k = last_close / float(df["close"].iloc[-1])
    for col in ("open", "high", "low", "close"):
        out[col] = out[col] * k
    return out


def test_the_texts_fit_at_the_widest_numbers(tmp_path):
    """Every text the board shows is one line the engine never has to cut: the ORB exit at a
    123.45 risk (breakeven 61.725 up) and a short one at a 4-dp risk (123.4568, breakeven
    61.728x down), its range-pending text, the NOISE exit at a 9999.99 VWAP
    and with no VWAP, and both stop bases -- each drawn from the real functions."""
    def wide_range(i, px):                         # a 49.38-point opening range, first candle up
        if i == 0:
            return px, px + 30.0, px - 19.38, px + 10.0
        if i == 1:
            return px, px + 5.0, px - 5.0, px + 1.0
        return None
    def wide_short(i, px):                         # 49.3827: a 4-dp risk, first candle down
        if i == 0:
            return px, px + 19.3827, px - 30.0, px - 10.0
        if i == 1:
            return px, px + 5.0, px - 5.0, px - 1.0
        return None
    orb_df = _tape(n=65, today=wide_range)
    orb_home = _home(tmp_path, orb_df, "orb")
    orb = _orb(orb_df, "09:40", orb_home)
    assert f"{orb['risk']:.2f}" == "123.45"
    short_df = _tape(n=65, today=wide_short)
    orb_short = _orb(short_df, "09:40", _home(tmp_path, short_df, "orbs"))
    assert orb_short["dir"] == "short" and orb_short["rng"] == 49.3827
    assert "61.728" in orb_short["exit_rule"] and orb_short["exit_rule"].endswith(" down. Out at the close.")
    pending = _orb(orb_df, "09:30", orb_home)
    assert pending["risk"] is None
    big = _scaled(_tape(), 9999.99)
    noise = _noise(big, "10:35", _home(tmp_path, big, "big"))
    assert noise["status"] == "ok" and "(now 9999.99)" in noise["exit_rule"]
    dry = _tape(today=lambda i, px: (px, px, px, px, 0.0))          # no volume today: no VWAP
    no_vwap = _noise(dry, "10:35", _home(tmp_path, dry, "dry"))
    assert no_vwap["vwap"] is None and "(now" not in no_vwap["exit_rule"]
    texts = {"orb exit": orb["exit_rule"], "orb exit, short at 4 dp": orb_short["exit_rule"],
             "orb pending": pending["exit_rule"],
             "noise exit": noise["exit_rule"], "noise exit, no vwap": no_vwap["exit_rule"],
             "orb basis": orb["basis"], "noise basis": noise["long"]["basis"]}
    for name, s in texts.items():
        assert len(s) <= cs.NEXT_ENTRY_TEXT_MAX and cs._ne_text(s) == s, (name, len(s), s)
    assert "; stop to the entry once a close is 61.7" in orb["exit_rule"]
    assert noise["long"]["basis"] == noise["short"]["basis"]


# ── 9. the gates match what the engine decides ──────────────────────────────────────────

@pytest.mark.parametrize("prior", [None, _trend_day(-0.02), "vol"])
def test_noise_gates_match_the_engine_with_far_stand_ins(tmp_path, prior):
    n = 66 if prior == "vol" else 45
    df = _tape(n=n, prior=_trend_day(0.06) if prior == "vol" else prior)
    paths = _home(tmp_path, df)
    cfg = _noise_cfg(paths)
    for hhmm in ("09:45", "11:10", "14:30"):
        leg = _noise(df, hhmm, paths)
        arrays = _arrays(df, hhmm, cfg)
        n_bars = len(arrays["close"])
        fired = {}
        for side, mult in (("long", 1.2), ("short", 0.8)):
            probe = cs._stand_in_arrays(arrays, "5m", pads=3, price=float(arrays["close"][-1]) * mult)
            got = cs.run_leg_trades(cfg, probe, leg_key="NOISE_382", log=cs._ne_quiet,
                                    now=_after(hhmm), paths=paths, fetch=False)
            fired[side] = any(t["entry_bar"] == n_bars + 1 and t["side"] == side for t in got)
        if leg["status"] == "ok":
            assert fired == {"long": leg["long"]["ok"], "short": leg["short"]["ok"]}, hhmm
        else:
            assert leg["status"] == "day_blocked" and fired == {"long": False, "short": False}
    assert (leg["status"] == "day_blocked") == (prior == "vol")


# ── 10. ranges ──────────────────────────────────────────────────────────────────────────

def test_size_ranges_follow_keel_v12():
    from augur_engine import ml_keel
    r = cs._noise_size_range
    tue, fri, fomc = _dt.date(2026, 10, 20), _dt.date(2026, 10, 23), _dt.date(2026, 10, 28)
    assert fomc in ml_keel.fomc_decision_days()
    assert r(tue, "09:40", "15:55", "fixed-only", None) == (1.0, 3.0)
    assert r(fri, "09:40", "15:55", "fixed-only", None) == (1.5, 4.5)
    assert r(fomc, "09:40", "15:55", "fixed-only", None) == (0.5, 3.0)
    assert r(fomc, "14:05", "15:55", "fixed-only", None) == (1.0, 3.0)
    assert r(fomc, "09:40", "12:55", "fixed-only", None) == (0.5, 1.5)       # a half-day FOMC
    assert r(tue, "09:40", "15:55", "shade", None) == (0.5, 4.5)
    assert r(tue, "09:40", "15:55", "trust", None) == (0.75, 6.0)
    assert r(tue, "09:40", "15:55", "fallback", None) == (1.0, 3.0)
    assert r(tue, "09:40", "15:55", "fixed-only", None, tilt_mult=1.0) == (1.0, 1.5)


# ── 11. read / write ────────────────────────────────────────────────────────────────────

def test_read_and_write_the_sidecar(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "rw"))
    assert cs.read_next_entry(paths) == {}
    os.makedirs(paths["state_dir"])
    for raw in ("{not json", json.dumps([1, 2]), json.dumps({"v": 2, "legs": {}})):
        with open(cs.next_entry_path(paths), "w", encoding="utf-8") as f:
            f.write(raw)
        assert cs.read_next_entry(paths) == {}
    doc = {"v": 1, "computed_at": "2026-10-20T10:40:31-04:00", "legs": {"ORB_R6": {"px": 722.12}}}
    used = []
    real = cs.qp._replace_with_retry
    monkeypatch.setattr(cs.qp, "_replace_with_retry",
                        lambda *a, **k: used.append(a) or real(*a, **k))
    assert cs._write_next_entry(doc, paths) is True and len(used) == 1
    assert cs.read_next_entry(paths) == doc
    assert os.listdir(paths["state_dir"]) == [cs.NEXT_ENTRY_FILE]
    monkeypatch.setattr(cs.qp, "_replace_with_retry", lambda *a, **k: False)
    assert cs._write_next_entry(doc, paths) is False
    assert cs._write_next_entry({"v": 1, "x": float("nan")}, paths) is False   # never NaN
    assert os.listdir(paths["state_dir"]) == [cs.NEXT_ENTRY_FILE]
    assert cs.read_next_entry(paths) == doc


# ── 12. size ────────────────────────────────────────────────────────────────────────────

def test_the_worst_case_sidecar_is_under_4_kb(tmp_path):
    df = _tape(n=65, today=_jump("10:00", 0.01))
    paths = _home(tmp_path, df)
    now, _ = _stash(paths, df, "09:55", _legs(paths))
    doc = cs._next_entry_tick(now, [], paths=paths)
    orb = cs._orb_next_entry(dict(cs.CROWN_LEGS["ORB_R6"]),
                             _arrays(_tape(n=65, today=_orb_day(1)), "09:50",
                                     cs.CROWN_LEGS["ORB_R6"]),
                             [], "5m", _after("09:50"), paths)
    doc["legs"]["ORB_R6"] = orb
    noise = doc["legs"]["NOISE_382"]
    assert noise["status"] == "ok" and orb["status"] == "ok"
    noise["check"] = {"tid": "NOISE_382-20261020T143000Z-L", "bar": "10:25",
                      "at": "2026-10-20T10:30:41.123456-04:00", "preview": 4.123456,
                      "actual": 4.123456, "match": True, "board": 4.123456, "board_match": True}
    noise["next"]["may_change"] = ["sq30", "sq60", "model"]

    def worst(x):
        if isinstance(x, dict):
            return {k: worst(v) for k, v in x.items()}
        if isinstance(x, list):
            return [worst(v) for v in x]
        if isinstance(x, bool) or x is None:
            return x
        if isinstance(x, str):
            return "x" * cs.NEXT_ENTRY_TEXT_MAX if len(x) > 30 else x
        return 12345.678901 if isinstance(x, float) else x
    big = worst(doc)
    for leg in big["legs"].values():
        for k in ("why", "keel_fb"):
            leg[k] = "y" * cs.NEXT_ENTRY_TEXT_MAX
    raw = json.dumps(big, separators=(",", ":"), allow_nan=False)
    assert len(raw.encode("utf-8")) < 4096, len(raw)
    json.dumps(doc, allow_nan=False)
    # the keys are the frozen schema api/qqq_exec.py reads (contract 1.9), no more, no fewer
    assert set(doc) == {"v", "computed_at", "host", "cost_ms", "next_session", "legs"}
    assert set(noise) == {"status", "why", "bar", "bar_close", "next", "range_today",
                          "next_session", "px", "vwap", "vwap_dist", "ref_hi", "ref_lo",
                          "vol_pct", "long", "short", "exit_rule", "check"}
    assert set(noise["next"]) == {"decide_bar", "decide_close", "fill_bar", "size", "plugin",
                                  "sq30", "keel", "fri", "sq60", "fomc", "branch", "model_on",
                                  "trust", "t_fast", "z", "keel_src", "keel_fb", "may_change"}
    for side in ("long", "short"):
        assert set(noise[side]) == {"ok", "why", "trigger", "stop_dist", "stop_est", "basis"}
    assert set(noise["range_today"]) == {"lo", "hi"}
    assert set(noise["next_session"]) == {"date", "lo", "hi", "fri", "fomc"}
    assert set(orb) == {"status", "why", "bar", "bar_close", "next", "size", "dir", "or_hi",
                        "or_lo", "rng", "trigger", "px", "risk", "stop_est", "target_est",
                        "be_est", "target_r", "be_r", "pace", "basis", "exit_rule"}
    assert set(orb["next"]) == {"decide_bar", "decide_close"}


# ── 13. step() never writes it ──────────────────────────────────────────────────────────

def test_step_alone_never_writes_the_sidecar(tmp_path):
    df = _tape(n=65, today=_jump("10:00", 0.01))
    paths = _home(tmp_path, df)
    legs = _legs(paths)
    for hhmm in ("09:50", "09:55", "10:00", "10:05"):
        cs.step(now=_after(hhmm), legs=legs, paths=paths, fetch=False, warnings={})
    assert not os.path.exists(cs.next_entry_path(paths))
    mem = cs._NEXT_ENTRY_MEMO[paths["state_dir"]]
    assert set(mem["inputs"]) == {"NOISE_382", "ORB_R6"}
    assert mem["inputs"]["NOISE_382"]["bar_epoch"] == _epoch("10:05")
    # a shadow cfg under a preview key, or any other leg, is never stashed
    other = cs._paths(home=str(tmp_path / "other"))
    shutil.copytree(paths["ohlc_dir"], other["ohlc_dir"])
    cs.step(now=_after("10:10"), legs={"ORB_R6": dict(cs.CROWN_LEGS["ORB_R6"], shadow=True),
                                       "ORB_X": dict(cs.CROWN_LEGS["ORB_R6"])},
            paths=other, fetch=False)
    assert other["state_dir"] not in cs._NEXT_ENTRY_MEMO


def test_the_thread_calls_the_tick_after_the_heartbeat_and_nowhere_else():
    import inspect
    body = inspect.getsource(cs._engine_thread_run)
    hb = body.index("_write_heartbeat(DEFAULT_PATHS, ok=True, note=note")
    tick = body.index("_next_entry_tick(now_et, events, warnings=warnings")
    shadow = body.index("_shadow_tick(now_et, fetch=True")
    assert hb < tick < shadow and body.count("_next_entry_tick(") == 1
    for fn in (cs.step, cs._eod_settle_tick, cs.cmd_once, cs.run_shadow_step, cs.replay):
        assert "_next_entry_tick(" not in inspect.getsource(fn), fn.__name__
