"""tests/test_cloud_signal_keel_fallback_push.py -- the KEEL fallback push
(deadman/deadman_keel_guard, 2026-09-26, task item 3): when NOISE_382's KEEL overlay
would fall back to keel_size 1.0, api/cloud_signal.py pushes ONCE PER DAY with the
reason. See api/cloud_signal.py's _keel_fallback_reason / _maybe_push_keel_fallback.

Reuses tests/test_cloud_signal_keel.py's own fixtures (_arrays / _fitted_state /
_write_state) rather than reinventing a synthetic KEEL state.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import api.cloud_signal as cs  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
from test_cloud_signal_keel import _arrays, _fitted_state, _write_state, _sizing_cfg  # noqa: E402


# ── _keel_fallback_reason: the four fallback conditions ─────────────────────────────────
def test_missing_state_file_gives_a_reason():
    arrays = _arrays()
    keel_cfg = {"state_path": "/nope/nope.joblib", "summary_path": "/nope/nope.json"}
    reason = cs._keel_fallback_reason(keel_cfg, arrays["index"][-1])
    assert reason == "keel state unavailable"


def test_unreadable_state_file_gives_a_reason(tmp_path):
    bad = tmp_path / "bad.joblib"
    bad.write_bytes(b"not a joblib file")
    keel_cfg = {"state_path": str(bad), "summary_path": ""}
    reason = cs._keel_fallback_reason(keel_cfg, pd.Timestamp("2026-09-08", tz=cs.TZ))
    assert reason == "keel state unavailable"


def test_healthy_fresh_state_has_no_reason(tmp_path):
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state, _ = _fitted_state(arrays)
    entry_date = arrays["index"][10].date().isoformat()
    keel_cfg = _write_state(tmp_path, state, last_nq_session=entry_date)
    reason = cs._keel_fallback_reason(keel_cfg, arrays["index"][10])
    assert reason is None


def test_stale_beyond_the_push_threshold_gives_a_reason(tmp_path):
    """KEEL_PUSH_STALE_SESSIONS (1) is deliberately tighter than KEEL_MAX_STALE_SESSIONS
    (5) -- a state 2+ sessions behind must trigger the PUSH even though it is nowhere
    near stale enough to change live SIZING yet (see _keel_size_for_entry's own
    KEEL_MAX_STALE_SESSIONS tests, which stay green: no sizing behaviour changed)."""
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state, _ = _fitted_state(arrays)
    now = arrays["index"][-1]
    keel_cfg = _write_state(tmp_path, state, last_nq_session="2026-08-01")  # weeks stale
    reason = cs._keel_fallback_reason(keel_cfg, now)
    assert reason is not None and "stale" in reason

    # and the underlying SIZING fallback is untouched by this new, tighter push bound
    size, sizing_reason = cs._keel_size_for_entry(keel_cfg, arrays, 10, arrays["index"][10])
    # 2026-08-01 to entry date is comfortably beyond KEEL_MAX_STALE_SESSIONS too in this
    # fixture, so both paths agree it's stale -- the point is they are computed from
    # TWO DIFFERENT thresholds, not that they always disagree.
    assert size == 1.0 and "stale" in sizing_reason


def test_one_stale_session_alone_is_not_over_the_push_threshold(tmp_path):
    """KEEL_PUSH_STALE_SESSIONS=1 -- exactly one session behind must NOT push (only
    STRICTLY more than 1 does, same >, not >=, convention as KEEL_MAX_STALE_SESSIONS).
    2026-09-08 is a Tuesday; 2026-09-07 is Labor Day (not itself a session -- see
    api/market_calendar.py's own self-test), so the trading day immediately before
    2026-09-08 is Friday 2026-09-04 -- sessions_between(2026-09-04, 2026-09-08) is
    exactly [09-04, 09-08], n_stale == 1."""
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ), n_bars=10)
    state, _ = _fitted_state(arrays, n_trades=2)
    now = arrays["index"][-1]
    keel_cfg = _write_state(tmp_path, state, last_nq_session="2026-09-04")
    reason = cs._keel_fallback_reason(keel_cfg, now)
    assert reason is None


def test_feature_mismatch_gives_a_reason_only_when_arrays_are_given(tmp_path):
    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    state = dict(state)
    state["feature_names"] = list(state["feature_names"])[::-1]
    keel_cfg = _write_state(tmp_path, state)

    # no arrays passed -> this specific check is skipped, not a false negative --
    # the state/staleness checks still ran and found nothing wrong on their own.
    assert cs._keel_fallback_reason(keel_cfg, arrays["index"][-1], arrays=None) is None
    # arrays passed -> the mismatch is caught.
    reason = cs._keel_fallback_reason(keel_cfg, arrays["index"][-1], arrays=arrays)
    assert reason == "keel feature columns do not match the state"


def test_exception_during_the_check_gives_a_reason_never_raises(tmp_path, monkeypatch):
    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)

    def boom(*a, **k):
        raise RuntimeError("disk exploded")
    monkeypatch.setattr(cs, "_load_keel_state", boom)
    reason = cs._keel_fallback_reason(keel_cfg, arrays["index"][-1])
    assert reason is not None and "error" in reason


# ── _maybe_push_keel_fallback: once-per-day dedupe ───────────────────────────────────────
def test_pushes_once_and_not_again_the_same_day(monkeypatch):
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    state = {}
    now = pd.Timestamp("2026-09-08 12:00:00", tz=cs.TZ)
    keel_cfg = {"state_path": "/nope.joblib", "summary_path": ""}

    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now, state)
    assert len(pushed) == 1

    later_same_day = pd.Timestamp("2026-09-08 15:00:00", tz=cs.TZ)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, later_same_day, state)
    assert len(pushed) == 1, "must not push twice on the same ET calendar day"

    next_day = pd.Timestamp("2026-09-09 09:30:00", tz=cs.TZ)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, next_day, state)
    assert len(pushed) == 2, "a still-broken state must page again the next day"


def test_no_push_when_keel_is_healthy(tmp_path, monkeypatch):
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state_obj, _ = _fitted_state(arrays)
    entry_date = arrays["index"][10].date().isoformat()
    keel_cfg = _write_state(tmp_path, state_obj, last_nq_session=entry_date)
    state = {}
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, arrays["index"][10], state, arrays=arrays)
    assert pushed == []
    assert "NOISE_382" not in state.get("keel_alerts", {})


def test_recovering_then_breaking_again_same_day_does_not_double_push(monkeypatch):
    """A day with no reason leaves the stamp untouched (never cleared mid-day) -- so a
    leg that breaks, is noticed, and (from this function's point of view) still looks
    broken later the same day does not re-page; only a NEW calendar day does."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    state = {}
    keel_cfg = {"state_path": "/nope.joblib", "summary_path": ""}
    now = pd.Timestamp("2026-09-08 10:00:00", tz=cs.TZ)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now, state)
    assert len(pushed) == 1
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now + pd.Timedelta(hours=2), state)
    assert len(pushed) == 1


def test_never_raises_even_if_ntfy_push_itself_blows_up(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network exploded")
    monkeypatch.setattr(cs, "_keel_ntfy_push", boom)
    state = {}
    keel_cfg = {"state_path": "/nope.joblib", "summary_path": ""}
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, pd.Timestamp("2026-09-08", tz=cs.TZ), state)
    # must not raise -- reaching this line is the assertion


# ── _keel_ntfy_push: topic handling ──────────────────────────────────────────────────────
def test_ntfy_push_skips_when_topic_unset(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    logged = []
    cs._keel_ntfy_push("hello", "title", log=logged.append)
    assert logged and "NTFY_TOPIC unset" in logged[0]


# ── minor fix: a SCORING-TIME fallback (exception) must page too, not just the ───────────
# standalone freshness read above ────────────────────────────────────────────────────────
def test_scoring_exception_at_a_real_entry_pushes_once(tmp_path, monkeypatch):
    """_keel_fallback_reason never calls keel_score_from_state, so it cannot see a
    fallback that only happens AT SCORING TIME. A trade actually sized at 1.0 because
    keel_score_from_state raised must still page -- see _diff_leg's own
    scoring-time-fallback-push block, right after its _keel_size_for_entry call."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")

    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)
    leg_state = {"trades": {}}

    def boom(*a, **k):
        raise RuntimeError("sklearn exploded")
    monkeypatch.setattr(K, "keel_score_from_state", boom)

    open_trade = (5, 40, 3.0, 1, 700.0)
    cfg0 = _sizing_cfg([open_trade], size=2.0, cost=0.5, keel_cfg=keel_cfg)
    leg_trades0 = cs.run_leg_trades(cfg0, arrays, leg_key="NOISE_382")
    cs._diff_leg("NOISE_382", leg_trades0, leg_state, arrays["index"][6],
                cfg=cfg0, arrays=arrays, fetch=True)
    assert pushed == [], "the cold-start SEED never scores KEEL, so it must not push either"

    new_trade = (45, 55, -2.0, 1, 701.0)
    cfg1 = _sizing_cfg([open_trade, new_trade], size=1.5, cost=0.3, keel_cfg=keel_cfg)
    leg_trades1 = cs.run_leg_trades(cfg1, arrays, leg_key="NOISE_382")
    cs._diff_leg("NOISE_382", leg_trades1, leg_state, arrays["index"][56],
                cfg=cfg1, arrays=arrays, fetch=True)

    assert len(pushed) == 1
    assert "NOISE_382" in pushed[0] and "keel scoring error" in pushed[0]


def test_scoring_exception_push_needs_fetch_and_cloud_role_too(tmp_path, monkeypatch):
    """Same gate as the standalone check: no push off the box, and no push during an
    offline/replay tick, even though the scoring exception itself still happens (and
    the trade is still correctly sized at 1.0 -- only the PAGE is gated, never the
    fallback sizing behaviour)."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))

    arrays = _arrays()
    state, _ = _fitted_state(arrays)
    keel_cfg = _write_state(tmp_path, state)

    def boom(*a, **k):
        raise RuntimeError("sklearn exploded")
    monkeypatch.setattr(K, "keel_score_from_state", boom)

    open_trade = (5, 40, 3.0, 1, 700.0)
    new_trade = (45, 55, -2.0, 1, 701.0)
    cfg0 = _sizing_cfg([open_trade], size=2.0, cost=0.5, keel_cfg=keel_cfg)
    cfg1 = _sizing_cfg([open_trade, new_trade], size=1.5, cost=0.3, keel_cfg=keel_cfg)

    # off the box (fetch=True, no EDGELOG_HOST_ROLE=cloud) -- must not push.
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    leg_state = {"trades": {}}
    cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg0, arrays, leg_key="NOISE_382"),
                leg_state, arrays["index"][6], cfg=cfg0, arrays=arrays, fetch=True)
    ev = cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg1, arrays, leg_key="NOISE_382"),
                      leg_state, arrays["index"][56], cfg=cfg1, arrays=arrays, fetch=True)
    entry = [e for e in ev if e["event"] == "ENTRY"][0]
    assert entry["keel_size"] == 1.0, "sizing fallback itself must be unaffected by the gate"
    assert pushed == []

    # on the box, but an offline tick (fetch=False, e.g. a replay) -- must not push.
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    leg_state2 = {"trades": {}}
    cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg0, arrays, leg_key="NOISE_382"),
                leg_state2, arrays["index"][6], cfg=cfg0, arrays=arrays, fetch=False)
    cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg1, arrays, leg_key="NOISE_382"),
                leg_state2, arrays["index"][56], cfg=cfg1, arrays=arrays, fetch=False)
    assert pushed == []


# ── step()-level wiring: the push fires from a real tick, not just direct calls ─────────
def _keel_push_step_fixture(tmp_path):
    """Builds the shared (legs, paths, epoch_df, now) fixture the step()-level tests
    below all need, and monkeypatches cs.fetch_and_merge to hand back the synthetic
    bars in-memory (a live tick with fetch=True must go through fetch_and_merge, never
    load_cached_bars, so a real fetch path is what these tests drive)."""
    import types
    tz = cs.TZ
    base = pd.Timestamp("2026-09-08 09:30:00", tz=tz)
    times = [base + pd.Timedelta(minutes=5 * i) for i in range(4)]
    epoch = [int(t.tz_convert("UTC").timestamp()) for t in times]
    epoch_df = pd.DataFrame({
        "time": epoch, "open": [700.0] * 4, "high": [700.5] * 4, "low": [699.5] * 4,
        "close": [700.0] * 4, "volume": [1000.0] * 4})

    paths = cs._paths(home=str(tmp_path / "keel_push_home"))

    mod = types.ModuleType("keel_push_stub")
    mod.STRATEGY_NAME = "STUB"; mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        return {"trades": [] if return_trades else None, "num_trades": 0, "total_pnl": 0,
               "win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "avg_pnl": 0,
               "wins": 0, "losses": 0}
    mod.run_backtest = run_backtest

    legs = {"NOISE_382": {"strategy": mod, "timeframe": "5m", "params": {},
                          "warmup_sessions": 1,
                          "keel": {"version": "v12",
                                  "state_path": str(tmp_path / "missing_state.joblib"),
                                  "summary_path": str(tmp_path / "missing_summary.json")}}}

    now = (base + pd.Timedelta(minutes=25)).to_pydatetime()
    return legs, paths, epoch_df, now


def test_step_pushes_when_the_wired_leg_keel_state_is_missing(tmp_path, monkeypatch):
    """The major fix, 2026-09-26: the push must only fire on a LIVE tick (fetch=True)
    on the CLOUD BOX (EDGELOG_HOST_ROLE=cloud) -- see api/cloud_signal.py's
    _is_cloud_host and its call site in step(). This drives exactly that combination
    with fetch_and_merge monkeypatched (a real fetch is a network call)."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")

    legs, paths, epoch_df, now = _keel_push_step_fixture(tmp_path)
    monkeypatch.setattr(cs, "fetch_and_merge",
                       lambda tf, paths=None, log=print: (epoch_df, "yfinance", True))

    cs.step(now=now, legs=legs, paths=paths, fetch=True)
    assert pushed, "step() must push once its wired leg's KEEL state is found missing"
    assert "NOISE_382" in pushed[0]


def test_no_push_on_the_pc_even_with_a_live_fetching_tick(tmp_path, monkeypatch):
    """The PC case (major fix): api/runner.py's cloud_signal_thread calls this same
    step() with fetch=True, but EDGELOG_HOST_ROLE is never set to "cloud" there -- the
    push must stay silent, never a false "keel state unavailable" page."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)

    legs, paths, epoch_df, now = _keel_push_step_fixture(tmp_path)
    monkeypatch.setattr(cs, "fetch_and_merge",
                       lambda tf, paths=None, log=print: (epoch_df, "yfinance", True))

    cs.step(now=now, legs=legs, paths=paths, fetch=True)
    assert pushed == [], "the PC (no EDGELOG_HOST_ROLE=cloud) must never push"


def test_no_push_during_replay_even_on_the_cloud_box(tmp_path, monkeypatch):
    """The replay case (major fix): --replay always calls step(fetch=False), and an
    N-day replay with a live NTFY_TOPIC set must never send N false "stale" pushes for
    what is just how far in the past the replay's own `now` is -- even if run ON the
    box, where EDGELOG_HOST_ROLE=cloud really is set."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")

    legs, paths, epoch_df, now = _keel_push_step_fixture(tmp_path)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), index=False)

    cs.step(now=now, legs=legs, paths=paths, fetch=False)
    assert pushed == [], "a replay/offline tick must never push, even on the cloud box"
