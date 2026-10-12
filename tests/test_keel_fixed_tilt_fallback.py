r"""KEEL FIXED-TILT FALLBACK (2026-10-11, owner via MANAGER #96 -- item 4 of Custom ML's
C:\EdgeLog\manager\KEEL_LIVE_VS_BACKTEST_2026-10-11.md). The backtest that adopted KEEL v12 on
NOISE #382 never falls back: every trade gets v12's fixed tilts (Friday 1.5x, 60-minute squeeze
1.5x, cap 3.0, FOMC pre-statement 0.5x). Live, a LEARNED leg whose model could not be used sized
1.0 -- dropping the fixed tilts too. Now every learned-path fallback sizes on the fixed tilts
alone (api/cloud_signal._keel_learned_fallback), still reported as a fallback.

COVERS: every learned failure path on a Friday bar sizes the fixed tilts (not 1.0) with a reason
that says so and why; the fixed tilts failing too is still 1.0; const / fixed untouched; a live
_diff_leg ENTRY carries the tilt in keel_size / size / keel_branch "fallback-fixed", its EXIT
reuses it, the phone still pages (worded "fixed size tilts only"), no size-diff record; the
step-time push and its reason; the reason parsers (stale count, real, cause); the NOISE forward
log's fallback reader. Synthetic bars and a tiny real fitted state (tests/test_cloud_signal_keel.py
fixtures) -- no NQ master, no network.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for p in (ROOT, THIS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import api.cloud_signal as cs  # noqa: E402
from api import noise_forward as nf  # noqa: E402
from api import ntfy_push  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
from test_cloud_signal_keel import _arrays, _fitted_state, _sizing_cfg, _write_state  # noqa: E402

FRIDAY = pd.Timestamp("2026-09-11 09:30:00", tz=cs.TZ)
BAR = 10
FIXED = {"version": "v12", "mode": "fixed"}
QUIET = lambda *a, **k: None  # noqa: E731


def _friday(bar=BAR):
    """Friday bars and v12's fixed-tilt size at `bar` -- at least the Friday 1.5x, so a 1.0
    fallback can never pass for it."""
    assert FRIDAY.dayofweek == 4
    arrays = _arrays(base=FRIDAY)
    want, diag = cs._keel_fixed_size_for_entry(FIXED, arrays, bar)
    assert isinstance(diag, dict) and want >= 1.5
    return arrays, want


def _missing(tmp_path, arrays, monkeypatch):
    return ({"version": "v12", "state_path": str(tmp_path / "nope.joblib"),
             "summary_path": str(tmp_path / "nope.json")}, "keel state unavailable")


def _unreadable(tmp_path, arrays, monkeypatch):
    bad = tmp_path / "bad.joblib"
    bad.write_bytes(b"not a joblib file")
    return {"version": "v12", "state_path": str(bad), "summary_path": ""}, "keel state unavailable"


def _no_state_path(tmp_path, arrays, monkeypatch):
    return {"version": "v12"}, "keel config has no state_path"


def _stale(tmp_path, arrays, monkeypatch):
    state, _ = _fitted_state(arrays)
    return _write_state(tmp_path, state, last_nq_session="2026-07-01"), "keel state stale: "


def _mismatch(tmp_path, arrays, monkeypatch):
    state, _ = _fitted_state(arrays)
    state = dict(state, feature_names=list(state["feature_names"])[::-1])
    # trained through the entry's own Friday: since 2026-10-11 (KEEL_MAX_STALE_SESSIONS 1) the
    # helper's default 2026-09-05 is 3 sessions back -- a stale state, which is checked first
    return _write_state(tmp_path, state, last_nq_session="2026-09-11"), \
        "keel feature columns do not match the state"


def _non_finite(tmp_path, arrays, monkeypatch):
    state, _ = _fitted_state(arrays)
    monkeypatch.setattr(K, "keel_score_from_state", lambda *a, **k: (float("nan"), {}))
    return _write_state(tmp_path, state, last_nq_session="2026-09-11"), \
        "keel scoring returned a non-finite/non-positive size"


def _raises(tmp_path, arrays, monkeypatch):
    state, _ = _fitted_state(arrays)

    def boom(*a, **k):
        raise RuntimeError("sklearn exploded")
    monkeypatch.setattr(K, "keel_score_from_state", boom)
    return _write_state(tmp_path, state, last_nq_session="2026-09-11"), "keel scoring error"


@pytest.mark.parametrize("make", [_missing, _unreadable, _no_state_path, _stale, _mismatch,
                                  _non_finite, _raises], ids=lambda f: f.__name__.strip("_"))
def test_every_learned_fallback_sizes_the_fixed_tilts_not_one(make, tmp_path, monkeypatch):
    arrays, want = _friday()
    keel_cfg, cause = make(tmp_path, arrays, monkeypatch)
    ks, why = cs._keel_size_for_entry(keel_cfg, arrays, BAR, arrays["index"][BAR], log=QUIET)
    assert ks == want, "the backtest never drops the fixed tilts"
    assert isinstance(why, str), "still a FALLBACK (a reason string, not a diag dict)"
    assert why.startswith(cause) and f"; {cs.KEEL_FIXED_FALLBACK_NOTE} ({want:g}x)" in why
    assert cs._keel_fell_back_to_fixed(why) and cs._keel_fallback_is_real(why)
    assert cs._keel_fallback_cause(why).startswith(cause)
    assert cs.KEEL_FIXED_FALLBACK_NOTE not in cs._keel_fallback_cause(why)


def test_when_the_fixed_tilts_fail_too_it_is_one_as_before(tmp_path):
    arrays, _want = _friday()
    for cfg in ({"version": "v11", "state_path": str(tmp_path / "nope.joblib")},   # no tilts
                {"state_path": str(tmp_path / "nope.joblib")}):                    # no version
        ks, why = cs._keel_size_for_entry(cfg, arrays, BAR, arrays["index"][BAR], log=QUIET)
        assert ks == 1.0
        assert why.startswith("keel state unavailable; the fixed tilts could not be scored "
                              "either (keel fixed tilts: unsupported version")
        assert why.endswith("-- sized 1.0") and not cs._keel_fell_back_to_fixed(why)
        assert cs._keel_fallback_cause(why) == "keel state unavailable"
    ks, why = cs._keel_size_for_entry({"version": "v12", "state_path": str(tmp_path / "x")},
                                      arrays, 10_000, arrays["index"][BAR], log=QUIET)
    assert ks == 1.0 and "out of range" in why
    # unchanged: no block / no entry bar, the const and fixed modes, an unknown mode
    assert cs._keel_size_for_entry(None, arrays, BAR, arrays["index"][BAR]) == (1.0, None)
    assert cs._keel_size_for_entry({"version": "v12"}, arrays, None, None) == (1.0, None)
    assert cs._keel_size_for_entry({"mode": "const", "size": 1.245}, None, None, None)[0] == 1.245
    assert cs._keel_size_for_entry(FIXED, arrays, BAR, None) == \
        cs._keel_fixed_size_for_entry(FIXED, arrays, BAR)
    assert cs._keel_size_for_entry({"mode": "nope", "version": "v12"}, arrays, BAR, None) == \
        (1.0, "unknown keel mode 'nope'")


def test_a_live_entry_on_a_friday_with_no_state_trades_the_tilt_and_still_pages(tmp_path,
                                                                               monkeypatch):
    """The live path end to end: the ENTRY row (size = plugin x tilt, keel_size = tilt,
    branch fallback-fixed, keel_fixed_size = the same tilt), the EXIT reusing it, ONE high page
    worded for the fixed tilts, the reason on the leg's record -- and no size-diff record
    (KEEL sized exactly what the fixed rule would)."""
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    arrays, want = _friday(bar=45)
    keel_cfg = {"version": "v12", "state_path": str(tmp_path / "nope.joblib"),
                "summary_path": str(tmp_path / "nope.json")}
    leg_state = {"trades": {}}
    open_trade, new_trade = (5, 40, 3.0, 1, 700.0), (45, 55, -2.0, 1, 701.0)
    cfg0 = _sizing_cfg([open_trade], size=2.0, cost=0.5, keel_cfg=keel_cfg)
    seed = cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg0, arrays, leg_key="NOISE_382"),
                        leg_state, arrays["index"][6], cfg=cfg0, arrays=arrays, fetch=True,
                        log=QUIET)
    assert [e["event"] for e in seed] == ["SEED"] and pushed == [], "SEED never scores"
    cfg1 = _sizing_cfg([open_trade, new_trade], size=2.0, cost=0.3, keel_cfg=keel_cfg)
    ev = cs._diff_leg("NOISE_382", cs.run_leg_trades(cfg1, arrays, leg_key="NOISE_382"),
                      leg_state, arrays["index"][56], cfg=cfg1, arrays=arrays, fetch=True,
                      log=QUIET)
    entry, exit_ = ([e for e in ev if e["event"] == kind][0] for kind in ("ENTRY", "EXIT"))
    assert entry["keel_size"] == want and entry["size"] == pytest.approx(2.0 * want)
    assert entry["keel_branch"] == cs.KEEL_BRANCH_FALLBACK_FIXED == "fallback-fixed"
    assert entry["keel_fixed_size"] == want
    assert entry["keel_t_fast"] == entry["keel_trust"] == entry["keel_score"] == ""
    assert (exit_["keel_size"], exit_["size"]) == (entry["keel_size"], entry["size"])
    assert len(pushed) == 1
    assert "Trading: AFFECTED - NOISE trades on the fixed size tilts only, without its sizing " \
           "model." in pushed[0]
    assert "The KEEL sizing model could not be read on the cloud box." in pushed[0]
    assert leg_state["keel_alert"]["last_reason"].startswith(
        "keel state unavailable; fell back to the fixed tilts only")
    paths = cs._paths(home=str(tmp_path / "home"))
    logs, notes = [], []
    cs._note_keel_entries(ev, {"NOISE_382": cfg1}, paths, True, log=logs.append,
                          push=lambda *a, **k: notes.append(a))
    assert cs.read_keel_diffs(cs._keel_diffs_path(paths)) == [] and notes == []
    assert any("branch=fallback-fixed" in ln and "DIFFERS" not in ln for ln in logs)


def test_the_step_time_push_says_fixed_tilts_for_a_learned_v12_leg(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: sent.append(msg))
    now = pd.Timestamp("2026-09-11 12:00:00", tz=cs.TZ)
    st = {}
    cs._maybe_push_keel_fallback("NOISE_382", {"version": "v12",
                                               "state_path": str(tmp_path / "nope.joblib")},
                                 now, st, log=QUIET)
    assert len(sent) == 1 and "NOISE trades on the fixed size tilts only" in sent[0]
    rec = st["keel_alerts"]["NOISE_382"]
    assert rec["last_reason"] == "keel state unavailable; fell back to the fixed tilts only"
    assert rec["last_pushed_date"] == "2026-09-11"
    # a learned block with no version has no fixed tilts: base size, as before
    sent.clear()
    cs._maybe_push_keel_fallback("NOISE_382", {"state_path": str(tmp_path / "nope.joblib")},
                                 now, {}, log=QUIET)
    assert len(sent) == 1 and "NOISE trades at base size without its sizing model" in sent[0]


def test_the_reason_parsers_read_through_the_fixed_tilt_suffix():
    stale = "keel state stale: 7 session(s) since 2026-09-01; fell back to the fixed tilts only (1.5x)"
    assert cs._keel_stale_sessions(stale) == 7 and cs._keel_fallback_is_real(stale)
    # a count within KEEL_MAX_STALE_SESSIONS (1 since 2026-10-11: _keel_stale_reason never
    # gives one any more) would still size on the model; one past it is real
    assert not cs._keel_fallback_is_real(
        f"keel state stale: {cs.KEEL_MAX_STALE_SESSIONS} session(s) since 2026-09-01; fell back "
        f"to the fixed tilts only")
    assert cs._keel_fallback_is_real(
        "keel state stale: 2 session(s) since 2026-09-01; fell back to the fixed tilts only")
    for reason, problem in (
            (stale, "The KEEL sizing model is 7 trading sessions old, too old to use."),
            ("keel feature columns do not match the state; fell back to the fixed tilts only "
             "(1x)", "The KEEL sizing model does not match the price data it is given."),
            ("keel scoring error: RuntimeError: x; fell back to the fixed tilts only (2.25x)",
             "The KEEL sizing model failed to size a NOISE trade.")):
        note = cs._keel_fallback_note("NOISE_382", reason)
        assert ntfy_push.lint(note) == [] and note["priority"] == "high"
        assert note["message"].split("\n")[:2] == [
            "Trading: AFFECTED - NOISE trades on the fixed size tilts only, without its sizing "
            "model.", problem]
    # the fixed tilts failing too names the model's cause, never "the fixed sizing failed"
    both = ("keel state unavailable; the fixed tilts could not be scored either (keel fixed "
            "tilts error: ValueError: x) -- sized 1.0")
    note = cs._keel_fallback_note("NOISE_382", both)
    assert note["message"].split("\n")[:2] == [
        "Trading: AFFECTED - NOISE trades at base size without its sizing model.",
        "The KEEL sizing model could not be read on the cloud box."]
    # the entry extras: a fixed-tilt fallback is "fallback-fixed", any other one "fallback-1.0"
    arrays, want = _friday()
    out = cs._keel_entry_extras({"version": "v12", "state_path": "x"}, arrays, BAR,
                                f"keel state unavailable; fell back to the fixed tilts only "
                                f"({want:g}x)", log=QUIET)
    assert (out["keel_branch"], out["keel_fixed_size"]) == ("fallback-fixed", want)
    out = cs._keel_entry_extras({"version": "v12", "state_path": "x"}, arrays, BAR, both,
                                log=QUIET)
    assert out["keel_branch"] == "fallback-1.0"


def test_the_noise_forward_log_names_a_fixed_tilt_fallback(tmp_path, monkeypatch):
    """api/noise_forward.keel_fallback used to check only a keel_size of exactly 1.0 -- a
    fixed-tilt fallback (1.5 on a Friday) would read as a real score."""
    monkeypatch.setattr(cs, "_KEEL_STATE_CACHE", {})
    kp = dict(version="v12", **cs.keel_paths("NOISE_382", "v12", home=str(tmp_path)))
    entry = "2026-09-11T10:15:00-04:00"
    assert nf.keel_fallback(kp, entry, 1.5, fixed_size=1.5) == "keel state unavailable (no state file)"
    assert nf.keel_fallback(kp, entry, 1.0, fixed_size=1.5) == "keel state unavailable (no state file)"
    assert nf.keel_fallback(kp, entry, 1.3, fixed_size=1.5) == ""
    assert nf.keel_fallback(kp, entry, 1.5) == "", "no fixed size given: only 1.0 is checked"
