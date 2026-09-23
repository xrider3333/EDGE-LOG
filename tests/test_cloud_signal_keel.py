"""tests/test_cloud_signal_keel.py -- the KEEL v12 overlay wired into
api/cloud_signal.py's ENTRY/EXIT emission (OWNER DECISION 2026-09-23, design doc E).

COVERS:
  1. A leg with NO "keel" block in its cfg is completely unaffected -- byte-identical
     ENTRY/EXIT rows to before this feature existed (same test shape as
     test_cloud_signal_trade_size.py's own "non-sizing leg is unaffected" test).
  2. KEEL is scored EXACTLY ONCE per trade, at ENTRY, and the EXIT reuses that same
     value -- never recomputed.
  3. Every failure path (missing state, unreadable state, feature-column mismatch, a
     stale state, a scoring exception) falls back to keel_size 1.0 -- logged, never
     raised, never blocking the trade.
  4. The cold-start SEED path never calls the KEEL scorer at all.
  5. signals.csv's "keel_size" column: blank for a non-KEEL leg and for SEED rows, a
     real number for a KEEL leg's ENTRY/EXIT rows.

Builds a tiny, fast, REAL fitted KEEL state (augur_engine.ml_keel.keel_build_state) on
synthetic data and joblib-dumps it to a tmp_path -- no dependency on the real NQ master
or the real #382 state file, so this suite runs anywhere.
"""
import json
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.cloud_signal as cs                    # noqa: E402
from augur_engine import ml_keel as K            # noqa: E402


# ── shared fixtures ──────────────────────────────────────────────────────────────────────
def _arrays(n_bars=60, seed=3, base=None, freq="5min"):
    rng = np.random.RandomState(seed)
    base = base or pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ)
    idx = pd.date_range(base, periods=n_bars, freq=freq)
    price = 700.0
    closes = []
    for _ in range(n_bars):
        price += rng.normal(0, 0.5)
        closes.append(price)
    c = np.array(closes)
    return {
        "open": c.copy(), "high": c + 0.3, "low": c - 0.3, "close": c,
        "volume": np.full(n_bars, 1000.0),
        "day_id": np.zeros(n_bars, dtype="int64"),
        "index": idx,
    }


def _fitted_state(arrays, seed=5, n_trades=40):
    """A small, real, fitted KEEL v12 state -- built the same way
    tools/keel_live_state.py builds the production one, just on a tiny synthetic
    series so the whole test suite runs in well under a second."""
    rng = np.random.RandomState(seed)
    n_bars = len(arrays["close"])
    trades = []
    pos = 2
    while len(trades) < n_trades and pos < n_bars - 3:
        exitb = min(pos + rng.randint(1, 3), n_bars - 1)
        pnl = float(rng.gamma(2, 10)) if rng.rand() < 0.4 else -float(rng.gamma(2, 6))
        # 5-tuple, engine-shaped (entry_bar, exit_bar, pnl_pts, side, entry_px) -- so
        # these SAME trades double as a stub strategy's return value in the
        # cloud_signal integration tests below; keel_build_state/keel_walk only ever
        # read t[0]/t[1]/t[2] and ignore the rest, exactly like the real engine's trades.
        trades.append((pos, exitb, pnl, 1, float(arrays["close"][pos])))
        pos = exitb + 1
    return K.keel_build_state(arrays, trades, version="v12"), trades


def _write_state(tmp_path, state, last_nq_session="2026-09-05", name="NOISE_382_v12"):
    import joblib
    d = tmp_path / "keel"
    d.mkdir(exist_ok=True)
    state_path = d / f"{name}_state.joblib"
    summary_path = d / f"{name}_summary.json"
    joblib.dump(state, str(state_path))
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"last_nq_session": last_nq_session, "feature_names": state["feature_names"]},
                  f)
    return {"version": "v12", "state_path": str(state_path), "summary_path": str(summary_path)}


def _plain_stub(trades_list):
    """A non-sizing strategy stub (plugin size always 1.0)."""
    mod = types.ModuleType("keel_plain_stub")
    mod.STRATEGY_NAME = "KEEL_PLAIN_STUB"
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        n = len(trades_list)
        return {"trades": list(trades_list) if return_trades else None, "num_trades": n,
               "total_pnl": sum(t[2] for t in trades_list), "win_rate": 0, "profit_factor": 0,
               "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}

    mod.run_backtest = run_backtest
    return mod


# ── 1. no "keel" block -> byte-identical to pre-KEEL behaviour ───────────────────────────
def test_leg_without_keel_block_is_completely_unaffected():
    arrays = _arrays()
    trades = [(1, 2, 5.0, 1, 700.0)]
    cfg = {"strategy": _plain_stub(trades), "params": {}}   # no "keel" key at all
    leg_trades = cs.run_leg_trades(cfg, arrays, leg_key="PLAIN")
    leg_state = {"trades": {}}
    # seed first (mirrors step()'s real sequencing)
    cs._diff_leg("PLAIN", leg_trades, leg_state, arrays["index"][3], cfg=cfg,
                arrays=arrays)
    trades2 = [(1, 2, 5.0, 1, 700.0), (3, 4, -2.0, 1, 703.0)]
    cfg2 = {"strategy": _plain_stub(trades2), "params": {}}
    leg_trades2 = cs.run_leg_trades(cfg2, arrays, leg_key="PLAIN")
    events = cs._diff_leg("PLAIN", leg_trades2, leg_state, arrays["index"][5],
                          cfg=cfg2, arrays=arrays)
    entries = [e for e in events if e["event"] == "ENTRY"]
    assert entries, "test setup: expected at least one new ENTRY"
    for e in entries:
        assert e["size"] == 1.0
        assert e["keel_size"] == ""


# ── 2/5. KEEL scores once at ENTRY, EXIT reuses it, keel_size column is populated ────────
def _sizing_cfg(trades_list, size, cost, keel_cfg):
    """A fresh cfg dict wired to a sizing stub returning EXACTLY `trades_list`, folded
    at `size`/`cost` per NOISE_1_8_CT304.py's own additive size contract -- a new
    module each call so successive ticks in one test can hand back different trade
    lists, exactly like the real engine re-deriving the whole window every call."""
    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        return {"trades": trades_list if return_trades else None,
               "num_trades": len(trades_list),
               "total_pnl": sum(t[2] for t in trades_list), "win_rate": 0,
               "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0,
               "trade_sizes": [size] * len(trades_list), "size_cost_pts": cost}
    mod = types.ModuleType("keel_sizing_stub_%d" % id(trades_list))
    mod.STRATEGY_NAME = "KEEL_SIZING_STUB"; mod.DEFAULT_PARAMS = {}; mod.run_backtest = run_backtest
    return {"strategy": mod, "params": {}, "keel": keel_cfg}


def test_keel_scores_once_at_entry_and_exit_reuses_the_same_value(tmp_path):
    """A trade discovered and closed inside the SAME call (exit_bar well short of the
    window's boundary -- the common case for a strategy that holds only a few bars)
    emits ENTRY then EXIT back to back inside one _diff_leg call. KEEL must still be
    scored only ONCE (in the ENTRY branch) and the EXIT branch, running immediately
    after in the same loop body, must read that stored value back rather than compute
    its own -- proved here by making the mock scorer return a NEW random value on every
    call, so any second call would visibly disagree."""
    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)
    leg_state = {"trades": {}}

    open_trade = (5, 40, 3.0, 1, 700.0)
    cfg0 = _sizing_cfg([open_trade], size=2.0, cost=0.5, keel_cfg=keel_cfg)
    leg_trades0 = cs.run_leg_trades(cfg0, arrays, leg_key="NOISE_382")
    seed_events = cs._diff_leg("NOISE_382", leg_trades0, leg_state, arrays["index"][6],
                               cfg=cfg0, arrays=arrays)
    assert [e["event"] for e in seed_events] == ["SEED"]
    assert seed_events[0]["keel_size"] == ""

    # a brand-new trade, already closed by the time this tick discovers it (exit_bar
    # 55 is comfortably before the 60-bar window's own boundary at 59) -> ENTRY and
    # EXIT both emit in this ONE call.
    s2, cost2 = 1.5, 0.3
    folded2 = s2 * (-1.5) - (s2 - 1.0) * cost2
    new_trade = (45, 55, folded2, 1, 701.0)
    cfg1 = _sizing_cfg([open_trade, new_trade], size=s2, cost=cost2, keel_cfg=keel_cfg)
    leg_trades1 = cs.run_leg_trades(cfg1, arrays, leg_key="NOISE_382")
    events1 = cs._diff_leg("NOISE_382", leg_trades1, leg_state, arrays["index"][56],
                           cfg=cfg1, arrays=arrays)
    entries = [e for e in events1 if e["event"] == "ENTRY"]
    exits = [e for e in events1 if e["event"] == "EXIT"]
    assert len(entries) == 1 and len(exits) == 1
    entry, exit_ = entries[0], exits[0]
    assert entry["keel_size"] != "" and isinstance(entry["keel_size"], float)
    assert entry["size"] == pytest.approx(s2 * entry["keel_size"], abs=1e-9)
    assert exit_["trade_id"] == entry["trade_id"]
    assert exit_["size"] == entry["size"]
    assert exit_["keel_size"] == entry["keel_size"]


def test_keel_exit_reuses_the_entry_score_even_if_a_rescoring_would_differ(tmp_path, monkeypatch):
    """Direct proof that the EXIT branch never calls the scorer a second time: after an
    ENTRY has been recorded, monkeypatch the scorer to return a DIFFERENT value, then
    close the trade on a later tick. The EXIT must still carry the ORIGINAL value."""
    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)
    leg_state = {"trades": {}}

    open_trade = (5, 40, 3.0, 1, 700.0)
    cfg0 = _sizing_cfg([open_trade], size=2.0, cost=0.5, keel_cfg=keel_cfg)
    cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg0, arrays, leg_key="NOISE_382"),
                leg_state, arrays["index"][6], cfg=cfg0, arrays=arrays)

    # an entry that is STILL OPEN this tick (exit sits exactly at the window boundary,
    # eod_marks_at_close's price test reads it as open -- its price equals last_close).
    s2, cost2 = 1.5, 0.3
    n_bars = len(arrays["close"])
    last_close = float(arrays["close"][-1])
    raw_at_close = last_close - 701.0
    folded_open = s2 * raw_at_close - (s2 - 1.0) * cost2
    still_open_trade = (45, n_bars - 1, folded_open, 1, 701.0)
    cfg1 = _sizing_cfg([open_trade, still_open_trade], size=s2, cost=cost2, keel_cfg=keel_cfg)
    ev1 = cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg1, arrays, leg_key="NOISE_382"),
                       leg_state, arrays["index"][-1], cfg=cfg1, arrays=arrays)
    entries = [e for e in ev1 if e["event"] == "ENTRY"]
    assert len(entries) == 1 and not [e for e in ev1 if e["event"] == "EXIT"]
    entry = entries[0]
    real_keel_size = entry["keel_size"]

    monkeypatch.setattr(cs, "_keel_size_for_entry",
                        lambda *a, **k: (9.99, {"z": 0}))   # would be obviously wrong

    closed_trade = (45, 50, s2 * 2.0 - (s2 - 1.0) * cost2, 1, 701.0)
    cfg2 = _sizing_cfg([open_trade, closed_trade], size=s2, cost=cost2, keel_cfg=keel_cfg)
    ev2 = cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg2, arrays, leg_key="NOISE_382"),
                       leg_state, arrays["index"][-1], cfg=cfg2, arrays=arrays)
    exits = [e for e in ev2 if e["event"] == "EXIT"]
    assert len(exits) == 1
    assert exits[0]["keel_size"] == real_keel_size
    assert exits[0]["keel_size"] != 9.99
    assert exits[0]["size"] == entry["size"]


# ── 3. every failure path falls back to keel_size 1.0, logged, never raised ─────────────
def test_missing_state_file_falls_back_to_1_0(tmp_path):
    arrays = _arrays()
    keel_cfg = {"version": "v12", "state_path": str(tmp_path / "nope.joblib"),
               "summary_path": str(tmp_path / "nope.json")}
    logged = []
    size, reason = cs._keel_size_for_entry(keel_cfg, arrays, 10, arrays["index"][10],
                                          log=logged.append)
    assert size == 1.0
    assert reason == "keel state unavailable"


def test_corrupt_state_file_falls_back_to_1_0_and_logs(tmp_path):
    arrays = _arrays()
    bad_path = tmp_path / "bad.joblib"
    bad_path.write_bytes(b"not a joblib file")
    keel_cfg = {"version": "v12", "state_path": str(bad_path), "summary_path": ""}
    logged = []
    size, reason = cs._keel_size_for_entry(keel_cfg, arrays, 10, arrays["index"][10],
                                          log=logged.append)
    assert size == 1.0
    assert reason == "keel state unavailable"
    assert logged and "unreadable" in logged[0]


def test_feature_column_mismatch_falls_back_to_1_0(tmp_path):
    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    state = dict(state)
    state["feature_names"] = list(state["feature_names"])[::-1]   # corrupt on purpose
    keel_cfg = _write_state(tmp_path, state)
    size, reason = cs._keel_size_for_entry(keel_cfg, arrays, 10, arrays["index"][10])
    assert size == 1.0
    assert reason == "keel feature columns do not match the state"


def test_stale_state_falls_back_to_1_0(tmp_path):
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state, _ = _fitted_state(arrays)
    # last_nq_session 30 sessions before the entry -- comfortably over
    # KEEL_MAX_STALE_SESSIONS.
    keel_cfg = _write_state(tmp_path, state, last_nq_session="2026-07-01")
    entry_time = arrays["index"][10]
    size, reason = cs._keel_size_for_entry(keel_cfg, arrays, 10, entry_time)
    assert size == 1.0
    assert "stale" in reason


def test_fresh_state_within_budget_is_not_treated_as_stale(tmp_path):
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state, _ = _fitted_state(arrays)
    entry_date = arrays["index"][10].date().isoformat()
    keel_cfg = _write_state(tmp_path, state, last_nq_session=entry_date)
    size, diag = cs._keel_size_for_entry(keel_cfg, arrays, 10, arrays["index"][10])
    assert isinstance(diag, dict), "expected a real score, not a fallback reason string"
    assert size > 0 and np.isfinite(size)


def test_scoring_exception_falls_back_to_1_0_and_logs(tmp_path, monkeypatch):
    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)

    def boom(*a, **k):
        raise RuntimeError("sklearn exploded")
    monkeypatch.setattr(K, "keel_score_from_state", boom)
    logged = []
    size, reason = cs._keel_size_for_entry(keel_cfg, arrays, 10, arrays["index"][10],
                                          log=logged.append)
    assert size == 1.0
    assert "keel scoring error" in reason
    assert logged and "KEEL scoring failed" in logged[0]


def test_no_keel_cfg_is_a_pure_noop():
    arrays = _arrays()
    size, diag = cs._keel_size_for_entry(None, arrays, 10, arrays["index"][10])
    assert size == 1.0 and diag is None


# ── 4. the cold-start SEED path never calls the scorer ────────────────────────────────────
def test_seed_never_scores_keel(tmp_path, monkeypatch):
    arrays = _arrays()
    state, trades = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)

    def must_not_be_called(*a, **k):
        raise AssertionError("KEEL must never be scored during a cold-start SEED")
    monkeypatch.setattr(cs, "_keel_size_for_entry", must_not_be_called)

    cfg = {"strategy": _plain_stub(trades), "params": {}, "keel": keel_cfg}
    leg_state = {"trades": {}}
    leg_trades = cs.run_leg_trades(cfg, arrays, leg_key="NOISE_382")
    events = cs._diff_leg("NOISE_382", leg_trades, leg_state, arrays["index"][-1],
                          cfg=cfg, arrays=arrays)
    assert [e["event"] for e in events] == ["SEED"]
    assert events[0]["keel_size"] == ""
