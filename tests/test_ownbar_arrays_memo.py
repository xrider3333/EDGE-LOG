"""FAST NOISE (2026-11-25): the own-bar pass builds closed_arrays ONCE per warm-up for all its
legs (arrays_memo in api/cloud_signal_stream._dry_run_decision) and every leg still gets a
private copy -- a strategy that writes into its inputs can never reach another leg.
Plus the per-stage text on the own-bar log line."""
import numpy as np
import pandas as pd

from api import cloud_signal as cs
from api import cloud_signal_stream as css


def _frame(days=4):
    rows = []
    for d in pd.bdate_range("2026-09-01", periods=days):
        for i in range(78):
            t = pd.Timestamp(f"{d.date()} 09:30", tz=cs.TZ) + pd.Timedelta(minutes=5 * i)
            px = 600.0 + i * 0.1
            rows.append({"time": int(t.timestamp()), "open": px, "high": px + 0.2,
                         "low": px - 0.2, "close": px + 0.05, "volume": 1000 + i})
    return pd.DataFrame(rows)


_REAL_CLOSED_ARRAYS = cs.closed_arrays


def _patch(monkeypatch, seen, calls):
    def counting_ca(*a, **k):
        calls.append(a[3])
        return _REAL_CLOSED_ARRAYS(*a, **k)

    def ldt(cfg, arrays, leg_key, tf, now, paths, fetch, log=print):
        seen.append((leg_key, float(np.sum(arrays["close"])), len(arrays["close"])))
        arrays["close"] *= 2.0          # a strategy scribbling on its inputs
        arrays["meta"]["scribbled"] = leg_key
        return [{"leg": leg_key, "n": len(arrays["close"])}], arrays

    monkeypatch.setattr(cs, "closed_arrays", counting_ca)
    monkeypatch.setattr(cs, "leg_decision_trades", ldt)
    monkeypatch.setattr(cs, "leg_warmup_sessions", lambda cfg: cfg["warmup_sessions"])
    monkeypatch.setattr(cs, "_diff_leg", lambda leg_key, trades, st, now, **k: list(trades))


def _run(df, legs, memo):
    now = css._effective_now_for_bar(int(df["time"].iloc[-1]) + 300, cs.CLOSE_GRACE_SECONDS)
    out = {}
    for k, cfg in legs.items():
        st = {} if memo is not None else None
        out[k] = css._dry_run_decision(k, cfg, df, now, {"trades": {}}, "ownbar", print,
                                       arrays_memo=memo, stages=st)[0]
        if st is not None:
            assert {"arrays_ms", "engine_ms", "diff_ms"} <= set(st)
    return out


LEGS = {"A": {"warmup_sessions": 3}, "B": {"warmup_sessions": 3}, "C": {"warmup_sessions": 2},
        "D": {"warmup_sessions": 3}}


def test_memo_builds_once_per_warmup_and_every_leg_sees_pristine_arrays(monkeypatch):
    df = _frame()
    seen_old, calls_old = [], []
    _patch(monkeypatch, seen_old, calls_old)
    old = _run(df, LEGS, None)
    seen_new, calls_new = [], []
    _patch(monkeypatch, seen_new, calls_new)
    new = _run(df, LEGS, {})
    assert calls_old == [3, 3, 2, 3]
    assert calls_new == [3, 2]                    # one build per warm-up
    assert seen_new == seen_old                   # B and D saw A's arrays UNSCRIBBLED
    assert new == old


def test_memo_none_is_todays_path(monkeypatch):
    seen, calls = [], []
    _patch(monkeypatch, seen, calls)
    _run(_frame(), LEGS, None)
    assert len(calls) == len(LEGS)


def test_copy_arrays_is_private():
    a = {"close": np.array([1.0, 2.0]), "index": pd.DatetimeIndex(["2026-09-01"] * 2),
         "meta": {"x": 1}, "n": 3}
    b = css._copy_arrays(a)
    b["close"][0] = 9.0
    b["meta"]["x"] = 2
    assert a["close"][0] == 1.0 and a["meta"]["x"] == 1 and b["n"] == 3
    assert css._copy_arrays(None) is None


def test_stage_text():
    st = {"start_ms": 410.0, "arrays_ms": 21.0, "engine_ms": 380.0, "diff_ms": 6.0}
    txt = css._stage_text(st, 0.372, 0.821)
    assert txt == (" [stages: wake 372 ms, queue 410, arrays 21, engine 380, diff 6, "
                   "commit 4]")
    assert css._stage_text(None, 0.3, 0.5) == ""
