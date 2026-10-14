"""LIVE KEEL vs its NQ reference -- the nightly checks (owner call 10-12 via MANAGER #143; the alert
rules: Custom ML 10-12, docs/KEEL_PERTRADE_SPEC_2026-10-12.md addendum 1). The nightly build
(tools/keel_live_state.py) keeps rebuilding the NQ state as the REFERENCE, never writes, moves or
resets the LIVE state, and after the rebuild runs two checks:
  * DRIFT, REPORT ONLY (a QQQ feed drifts from the NQ backtest by design): keel/keel_drift.json every
    night -- both states' trust_now / t_fast_now / branch_now and the day's live entries scored with
    both, notes outside the envelope (trust gap > 0.41 in months 0-3, > 0.56 in months 3-6, none
    after; an entry sized > 1.5x apart). Never pushed.
  * THE ALERTS: keel/keel_live_check.json -- EXACT (live state == cut + append-log replay to 1e-9 on
    n, n_fits, fitted_on, trust_now, t_fast_now, the last z), UNITS (median |P| of the last 20 QQQ
    trades within 0.5x-2x of the NQ reference's last 600; skipped below 20), CHAIN (the handler's
    missed / doubled close alerts since the last check). The box monitor (tools/webull_freshness.py
    keel_live:<leg>) pushes ONE plain default note per episode.

COVERS: a real nightly build with a live state leaves every live file byte for byte and writes both
reports; a check that raises never fails the build; no live state -> no files (stale ones removed);
the drift report's day, figures, branches and notes (trust envelope by months, the 1.5x size note);
EXACT (1e-9, a missing cut), UNITS (skipped, inside, outside, the band edges), CHAIN (new alerts
since the last check, then clear); an unreadable live state; the monitor's episode and wording, and
the drift report never pushing.
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import cloud_signal as cs  # noqa: E402
from api import ntfy_push  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
import tools.keel_intraday as KI  # noqa: E402
import tools.keel_live_state as L  # noqa: E402
import tools.webull_freshness as wf  # noqa: E402
from _keel_live_world import LEG, QUIET, VERSION, LiveWorld  # noqa: E402
from test_webull_freshness import MON_1030, Home, _wj, failing  # noqa: E402

LIVE_FILES = ("live_path", "live_prev_path", "live_cut_path", "appends_path", "live_ack_path",
              "xrows_path")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return LiveWorld(tmp_path_factory.mktemp("keel_live_drift") / "w")


@pytest.fixture
def w(base, tmp_path):
    return base.clone(tmp_path / "w")


def _grow(w, ts, **over):
    for t in ts:
        w.write_xrow(w.xrow_record(t, 1.0))
        w.drop(w.inbox_trade(t, **over))
    assert all(r["status"] == "appended" for r in w.run())
    return w.load("live_path")


def _fp(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest(), os.stat(path).st_mtime_ns


def _read(w, name):
    with open(os.path.join(w.files["dir"], name), encoding="utf-8") as f:
        return json.load(f)


def _drift(w, ref, **kw):
    return L.drift_check(ref, w.files["dir"], LEG, VERSION, log=QUIET, **kw)


def _check(w, ref, **kw):
    return L.live_check(ref, w.files["dir"], LEG, VERSION, log=QUIET, **kw)


def _plus_months(day, months):
    return str((pd.Timestamp(str(day)) + pd.DateOffset(months=months)).date())


# ── the nightly never touches the live state ────────────────────────────────────────────────────
def test_the_nightly_build_leaves_the_live_state_alone_and_writes_both_reports(w, monkeypatch):
    monkeypatch.setattr(cs, "KEEL_LIVE_FEED", cs.KEEL_LIVE_FEED_QQQ)   # the qqq feed: no re-cut
    live = _grow(w, w.live_trades[:3])
    day1 = w.live_trades[4:6]                         # entries of the build's last session, open
    assert {t["entry_time"].date() for t in day1} == {w.live_days[1]}
    for t in day1:
        w.write_xrow(w.xrow_record(t, 1.0))
    before = {k: _fp(w.files[k]) for k in LIVE_FILES}
    nightly_before = _fp(w.files["state_path"])
    logs = []
    state, summary = L.build(w.nq_master, w.files["dir"], leg=LEG, log=logs.append)
    assert _fp(w.files["state_path"]) != nightly_before, "the reference was rebuilt"
    assert {k: _fp(w.files[k]) for k in LIVE_FILES} == before
    assert w.load("live_path")["n"] == live["n"]
    rep = _read(w, L.DRIFT_FILE)
    assert rep["report_only"] is True and rep["live"] is True and rep["day"] == summary["data_through"]
    assert rep["live_n"] == live["n"] and rep["reference_n"] == state["n"]
    assert [e["trade_id"] for e in rep["entries"]] == [t["trade_id"] for t in day1]
    for k in ("trust_now_live", "trust_now_reference", "t_fast_now_live", "t_fast_now_reference",
              "branch_now_live", "branch_now_reference"):
        assert k in rep, k
    chk = _read(w, L.LIVE_CHECK_FILE)
    assert chk["ok"] is True and chk["reasons"] == [] and chk["exact"]["ok"] is True
    assert chk["units"]["ok"] is None and "skipped" in chk["units"]["details"]
    assert chk["chain"]["ok"] is True
    assert any("[keel-live-state] drift NOISE_382 (report only)" in s for s in logs)
    assert any("[keel-live-state] live check NOISE_382: OK" in s for s in logs)


def test_a_check_that_raises_never_fails_the_build(w, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("check exploded")
    monkeypatch.setattr(L, "drift_check", boom)
    monkeypatch.setattr(L, "live_check", boom)
    logs = []
    state, summary = L.build(w.nq_master, w.files["dir"], leg=LEG, log=logs.append)
    assert summary["leg"] == LEG and os.path.exists(w.files["state_path"])
    assert any("drift report raised" in s for s in logs)
    assert any("live check raised" in s for s in logs)


def test_no_live_state_yet_writes_no_files_and_clears_stale_ones(w):
    for name, fn in ((L.DRIFT_FILE, _drift), (L.LIVE_CHECK_FILE, _check)):
        path = os.path.join(w.files["dir"], name)
        rep = fn(w, w.nightly)
        assert rep["live"] is False and not os.path.exists(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ok": False, "leg": LEG}, f)          # from an earlier live state
        fn(w, w.nightly)
        assert not os.path.exists(path), name


# ── DRIFT: report only ──────────────────────────────────────────────────────────────────────────
def test_the_drift_report_scores_the_days_entries_with_both_states(w):
    live = _grow(w, w.live_trades[:4])
    later = w.live_trades[4:6]
    for t in later:
        w.write_xrow(w.xrow_record(t, 1.0))
    ref = w.nightly
    rep = _drift(w, ref, day=str(w.live_days[0]))
    assert [e["trade_id"] for e in rep["entries"]] == [t["trade_id"] for t in w.live_trades[:4]]
    cfg = live.get("cfg") or K.CFG[live["version"]]
    for e, t in zip(rep["entries"], w.live_trades[:4]):
        s_l, d_l = K.keel_score_from_state(live, w.q_arrays, t["e"], x_row=w.x_row(t["e"]),
                                           cross_series=True)
        s_r, d_r = K.keel_score_from_state(ref, w.q_arrays, t["e"], x_row=w.x_row(t["e"]),
                                           cross_series=True)
        assert e["size_live"] == pytest.approx(s_l, abs=1e-12)
        assert e["size_reference"] == pytest.approx(s_r, abs=1e-12)
        assert e["branch_live"] == K.keel_branch(d_l, cfg)
        assert e["branch_reference"] == K.keel_branch(d_r, cfg)
    assert rep["trust_now_live"] == live["trust_now"] and rep["trust_now_reference"] == ref["trust_now"]
    assert rep["t_fast_now_live"] == live["t_fast_now"]
    assert rep["branch_now_live"] == L.state_branch_now(live)
    assert rep["months_band"] == "0-3" and rep["trust_note_above"] == 0.41
    assert _read(w, L.DRIFT_FILE)["entries"] == rep["entries"]
    # no day given: the latest day with an entry record
    rep = _drift(w, ref)
    assert rep["day"] == str(w.live_days[1])
    assert [e["trade_id"] for e in rep["entries"]] == [t["trade_id"] for t in later]


def test_the_trust_note_follows_the_envelope_for_the_months_since_the_cut(w):
    live = _grow(w, w.live_trades[:2])
    cut_day = cs.keel_live_meta(live)["cut"]["data_through"]
    t0 = float(live["trust_now"])

    def notes(gap, months):
        rep = _drift(w, dict(live, trust_now=t0 + gap), day=_plus_months(cut_day, months))
        return [n for n in rep["notes"] if "trust_now" in n]

    assert notes(0.40, 1) == [] and len(notes(0.42, 1)) == 1        # months 0-3: 0.41
    assert notes(0.55, 4) == [] and len(notes(0.57, 4)) == 1        # months 3-6: 0.56
    assert notes(0.95, 7) == []                                     # after 6 months: none
    rep = _drift(w, dict(live, trust_now=t0 + 0.42), day=_plus_months(cut_day, 1))
    assert rep["noted"] is True and "past 0.41 for months 0-3" in rep["notes"][0]
    assert "ok" not in rep, "a report, never a verdict"


def test_an_entry_sized_more_than_1_5x_apart_is_noted(w, monkeypatch):
    live = _grow(w, w.live_trades[:3])
    ref = dict(live)
    real = K.keel_score_from_state
    skew = [1.6]

    def skewed(state, *a, **k):
        size, diag = real(state, *a, **k)
        return (size + skew[0] if state is ref else size), diag
    monkeypatch.setattr(K, "keel_score_from_state", skewed)
    rep = _drift(w, ref, day=str(w.live_days[0]))
    assert rep["max_size_diff"] == pytest.approx(1.6)
    assert rep["notes"] == ["3 of the day's 3 entries sized more than 1.5x apart (up to 1.60x)"]
    skew[0] = 1.4
    rep = _drift(w, ref, day=str(w.live_days[0]))
    assert rep["notes"] == [] and rep["noted"] is False and rep["max_size_diff"] == pytest.approx(1.4)


def test_an_unreadable_live_state(w):
    os.makedirs(w.files["dir"], exist_ok=True)
    with open(w.files["live_path"], "wb") as f:
        f.write(b"torn")
    rep = _drift(w, w.nightly)
    assert rep["noted"] is None and "error" in rep and "error" in _read(w, L.DRIFT_FILE)
    chk = _check(w, w.nightly)
    assert chk["ok"] is False and chk["reasons"] == ["exact"]
    assert "cannot be read" in chk["exact"]["mismatches"][0]


# ── THE ALERTS ──────────────────────────────────────────────────────────────────────────────────
def test_exact_is_the_cut_plus_the_log_to_1e9(w):
    import joblib
    live = _grow(w, w.live_trades[:3])
    assert _check(w, w.nightly)["exact"]["ok"] is True
    joblib.dump(dict(live, t_fast_now=float(live["t_fast_now"]) + 1e-10), w.files["live_path"])
    assert _check(w, w.nightly)["ok"] is True
    joblib.dump(dict(live, t_fast_now=float(live["t_fast_now"]) + 1e-8), w.files["live_path"])
    chk = _check(w, w.nightly)
    assert chk["ok"] is False and chk["reasons"] == ["exact"]
    assert chk["exact"]["mismatches"] == ["t_fast_now"]
    joblib.dump(dict(live, fitted_on=int(live["fitted_on"]) - 1), w.files["live_path"])
    assert _check(w, w.nightly)["exact"]["mismatches"] == ["fitted_on"]
    joblib.dump(live, w.files["live_path"])
    os.remove(w.files["live_cut_path"])
    chk = _check(w, w.nightly)
    assert chk["ok"] is False and chk["exact"]["mismatches"][0].startswith("not rebuilt")


def test_the_nightly_reads_the_live_files_under_the_handlers_lock(w, monkeypatch):
    _grow(w, w.live_trades[:1])
    seen = []
    real = KI._Lock

    class Spy(real):
        def __enter__(self):
            seen.append(os.path.normcase(os.path.abspath(self.path)))
            return super().__enter__()
    monkeypatch.setattr(KI, "_Lock", Spy)
    assert _check(w, w.nightly)["ok"] is True
    assert seen == [os.path.normcase(os.path.abspath(w.paths["lock"]))]


def test_units_compares_the_last_qqq_trades_with_the_nq_ledger(w, monkeypatch):
    live = _grow(w, w.live_trades[:3])
    cut_n = cs.keel_live_meta(live)["cut"]["n"]
    chk = _check(w, w.nightly)
    assert chk["units"]["ok"] is None and chk["units"]["n_qqq"] == 3, "below 20: skipped"
    monkeypatch.setattr(L, "UNITS_LAST", 2)
    chk = _check(w, w.nightly)
    mq = float(np.median(np.abs(live["P"][cut_n:][-2:])))
    mn = float(np.median(np.abs(w.nightly["P"][-600:])))
    assert chk["units"]["median_qqq"] == mq and chk["units"]["median_nq"] == mn
    assert chk["units"]["ratio"] == mq / mn
    # an NQ ledger on another scale: the QQQ trades read far outside 0.5x-2x
    big = dict(w.nightly, P=np.asarray(w.nightly["P"], float) * (10.0 * (mq / mn)))
    chk = _check(w, big)
    assert chk["ok"] is False and chk["reasons"] == ["units"]
    assert chk["units"]["ratio"] == pytest.approx(0.1)


@pytest.mark.parametrize("scale, ok", [(1.0, True), (0.5, True), (2.0, True), (0.49, False),
                                       (2.01, False)])
def test_the_units_band_edges(scale, ok):
    # the NQ ledger's LAST 600 (|P| 10) -- not its whole history (mostly |P| 100); the LAST 20 QQQ
    # trades -- not the earlier ones (999) nor the cut's NQ part (0)
    ref = {"P": np.array([100.0] * 1000 + [10.0] * 300 + [-10.0] * 300)}
    live = {"P": np.concatenate([np.zeros(50), np.full(30, 999.0),
                                 np.full(L.UNITS_LAST, 10.0 * scale)])}
    u = L._units(live, ref, {"cut": {"n": 50}})
    assert u["ok"] is ok and u["ratio"] == pytest.approx(scale) and u["n_qqq"] == 50
    short = {"P": np.concatenate([np.zeros(50), np.full(L.UNITS_LAST - 1, 99.0)])}
    assert L._units(short, ref, {"cut": {"n": 50}})["ok"] is None
    assert L.UNITS_LAST == 20 and L.UNITS_REF == 600 and L.UNITS_BAND == (0.5, 2.0)


def test_chain_alerts_since_the_last_check_then_clear(w):
    t0, t1, t2 = w.live_trades[:3]
    _grow(w, [t0], prev_trade_id=None)
    w.write_xrow(w.xrow_record(t2, 1.0))
    w.drop(w.inbox_trade(t2, prev_trade_id=t1["trade_id"]))          # t1 never arrived
    (r,) = w.run()
    assert r["status"] == "rejected" and r["alert"] is True
    at = pd.Timestamp(w.ack()["alerts"][0]["at"])
    first = (at + pd.Timedelta(hours=2)).isoformat()
    chk = _check(w, w.nightly, now_iso=first)
    assert chk["ok"] is False and chk["reasons"] == ["chain"]
    assert [a["trade_id"] for a in chk["chain"]["alerts"]] == [t2["trade_id"]]
    # a hand re-run the same evening still sees it; the next night's check does not
    again = _check(w, w.nightly, now_iso=(at + pd.Timedelta(hours=3)).isoformat())
    assert again["reasons"] == ["chain"]
    nxt = _check(w, w.nightly, now_iso=(at + pd.Timedelta(hours=27)).isoformat())
    assert nxt["ok"] is True and nxt["chain"]["alerts"] == []


# ── the box monitor ─────────────────────────────────────────────────────────────────────────────
def test_the_monitor_pushes_one_plain_default_note_per_episode_and_never_for_drift(tmp_path):
    h = Home(tmp_path, MON_1030)
    out = h.run()
    assert "keel_live" not in out["status"]["groups_checked"] and h.pushes == []
    # the drift report never pushes, whatever it notes
    _wj(os.path.join(h.paths["keel_dir"], L.DRIFT_FILE),
        {"report_only": True, "leg": LEG, "noted": True, "notes": ["trust gap 0.9"]})
    out = h.run()
    assert h.pushes == [] and not [k for k in failing(out) if "keel" in k]
    path = os.path.join(h.paths["keel_dir"], wf.KEEL_LIVE_CHECK_FILE)
    assert wf.KEEL_LIVE_CHECK_FILE == L.LIVE_CHECK_FILE
    bad = {"ok": False, "leg": LEG, "reasons": ["exact"], "checked_at": "x",
           "exact": {"ok": False, "mismatches": ["trust_now"]}, "units": {"ok": None},
           "chain": {"ok": True, "alerts": []}}
    _wj(path, bad)
    out = h.run()
    assert "keel_live:NOISE_382" in failing(out)
    (p,) = h.pushes
    assert p["priority"] == "default" and ntfy_push.lint(p) == []
    assert p["message"].split("\n") == [
        "Trading: not affected.",
        "KEEL's live model no longer matches a rebuild from its own trade record.",
        "Do: ask Claude (PAPER-WB chat)."]
    h.run()
    assert len(h.pushes) == 1, "one push per episode"
    _wj(path, dict(bad, ok=None))                        # the check could not tell: no change
    h.run()
    assert len(h.pushes) == 1 and "keel_live:NOISE_382" in {a["key"] for a in h.status()["open_alerts"]}
    _wj(path, dict(bad, ok=True, reasons=[]))
    h.run()
    assert len(h.pushes) == 1, "a default episode closes without an OK push"
    assert h.status()["open_alerts"] == []
    _wj(path, dict(bad, reasons=["units", "chain"], units={"ok": False, "ratio": 0.61}))
    h.run()
    assert len(h.pushes) == 2, "a new episode pushes again"
    assert h.pushes[-1]["message"].split("\n")[1] == (
        "KEEL's live trades are on a different scale from its NQ trades (0.6x), so it may be "
        "learning wrong numbers.")
    assert ntfy_push.lint(h.pushes[-1]) == []
    _wj(path, dict(bad, ok=True, reasons=[]))
    h.run()
    _wj(path, dict(bad, reasons=["chain"]))
    h.run()
    assert len(h.pushes) == 3
    assert h.pushes[-1]["message"].split("\n")[1] == (
        "KEEL's live model skipped a NOISE trade: a close before it was missing or doubled.")
