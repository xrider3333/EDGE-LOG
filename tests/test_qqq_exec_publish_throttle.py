"""api/qqq_exec.py's Firestore write/read throttle (2026-09-14, FIX 1).

THE BUG THIS FIXES: publish_async -> ref.set(doc) used to run on every 5s tick,
24/7 (~17,280/day), because the old _should_publish hashed the WHOLE doc and
doc["updated_at"] / doc["lease"]["leased_at"] are reassigned to "now" every tick --
so the hash differed every tick regardless of whether anything real happened. This
covers: the new content FINGERPRINT (an explicit allowlist, not "whole doc minus
timestamps" -- several other fields, like feed_days' per-tick counters and live
price marks, are just as volatile and would have silently re-defeated a naive
timestamp-only exclusion), the interval fallback, and the Firestore usage counters.

INTERVAL DEPENDS ON WHETHER THE BROKER IS ARMED. This module was originally written
against a design with a SEPARATE lease-only heartbeat write and a fixed 600s
off-session interval, before api/qqq_exec.py's cross-host lease got a full
claim/renewal protocol (commit aaca82b, landed concurrently) whose _LeaseHolder ties
lease renewal to every REAL publish and self-blocks a broker send once this host's
own last renewal is older than LEASE_SEND_MAX_AGE_SEC (30s). Widening the
off-session interval to 600s once armed would starve that renewal and self-block
every order overnight -- so _should_publish now uses the original session(60s)/
off-session(600s) split ONLY while broker.effective_mode is OFF, and a single tight
publish_interval_armed_sec (default 20s, safely under that 30s bound) once armed,
regardless of session. See _should_publish's own docstring in api/qqq_exec.py.

No real Firestore anywhere -- a small hand-rolled fake records every .set() call
(doc + merge flag) so tests can assert exactly what was written and how often.
"""
import copy
import datetime as _dt
import json

import pytest

from api import qqq_exec as qe


# ── fake Firestore -- records every ref.set() call, no network ─────────────────────

class _FakeRef:
    def __init__(self, calls):
        self.calls = calls

    def set(self, doc, merge=False, timeout=None):
        self.calls.append({"doc": copy.deepcopy(doc), "merge": merge})


class _FakeDb:
    """Every .collection()/.document() hop returns self except the final
    .document("qqq_exec"), which returns the recording ref -- mirrors the real
    users/{uid}/meta/qqq_exec chain without needing a real Firestore client."""
    def __init__(self):
        self.calls = []
        self._ref = _FakeRef(self.calls)

    def collection(self, name):
        return self

    def document(self, name):
        return self._ref if name == "qqq_exec" else self


def _base_doc(**overrides):
    doc = {
        "mode": "SHADOW", "signal_source": "engine",
        "updated_at": "2026-09-14 09:31:00",
        "feed_stale": False, "px_feed_stale": False, "breaker_tripped": False,
        "kill": False,
        "positions": {},
        "today": {"orders": [], "trades": [], "realized_pnl": 0.0, "unrealized_pnl": 0.0},
        "events": [],
        "broker": {"requested_mode": "OFF", "effective_mode": "OFF", "halted": False,
                   "halt_reason": None, "lease_ok_to_send": True,
                   "last_order": {"leg": None, "side": None, "qty": None,
                                 "intent": None, "mode": None, "ok": None, "sent": None},
                   "last_reconcile_result": None},
        "lease": {"host_id": "test-host", "leased_at": 1000.0},
        "health": {"tick_gap_max_s_today": 0.0},
        "feed_days": {"2026-09-14": {"ticks": 1}},
    }
    doc.update(overrides)
    return doc


# ── _publish_fingerprint: the allowlist, not "whole doc minus timestamps" ──────────

def test_fingerprint_ignores_updated_at_and_lease_timestamp():
    a = _base_doc(updated_at="09:31:00", lease={"host_id": "h", "leased_at": 111.0})
    b = _base_doc(updated_at="09:31:05", lease={"host_id": "h", "leased_at": 222.0})
    assert qe._publish_fingerprint(a) == qe._publish_fingerprint(b)


def test_fingerprint_ignores_price_and_health_noise():
    """The bug-that-would-recur: excluding ONLY updated_at/leased_at is not enough --
    live-quote-derived numbers change almost every tick too and must also ride the
    interval, not force an immediate publish."""
    a = _base_doc(today={"orders": [], "trades": [], "realized_pnl": 0.0, "unrealized_pnl": 0.0},
                 health={"tick_gap_max_s_today": 0.0},
                 feed_days={"2026-09-14": {"ticks": 1}})
    b = _base_doc(today={"orders": [], "trades": [], "realized_pnl": 0.0, "unrealized_pnl": 41.37},
                 health={"tick_gap_max_s_today": 3.2},
                 feed_days={"2026-09-14": {"ticks": 187}})
    assert qe._publish_fingerprint(a) == qe._publish_fingerprint(b)


def test_fingerprint_changes_on_lot_opened():
    a = _base_doc(positions={})
    b = _base_doc(positions={"ORB": {"side": "long", "shares": 5}})
    assert qe._publish_fingerprint(a) != qe._publish_fingerprint(b)


def test_fingerprint_changes_on_order_sent_today():
    a = _base_doc()
    b = _base_doc(today={"orders": [{"ts_et": "x"}], "trades": [], "realized_pnl": 0.0,
                        "unrealized_pnl": 0.0})
    assert qe._publish_fingerprint(a) != qe._publish_fingerprint(b)


def test_fingerprint_changes_on_halt_toggle():
    a = _base_doc()
    b = _base_doc(broker={**a["broker"], "halted": True, "halt_reason": "reconcile mismatch"})
    assert qe._publish_fingerprint(a) != qe._publish_fingerprint(b)


def test_fingerprint_changes_on_mode_change():
    a = _base_doc(mode="SHADOW")
    b = _base_doc(mode="OTHER")
    assert qe._publish_fingerprint(a) != qe._publish_fingerprint(b)


def test_fingerprint_changes_on_staleness_flip():
    a = _base_doc(feed_stale=False)
    b = _base_doc(feed_stale=True)
    assert qe._publish_fingerprint(a) != qe._publish_fingerprint(b)


# ── _should_publish: session vs off-session interval, force, fingerprint ───────────

_IN_SESSION_ET = _dt.datetime(2026, 9, 14, 10, 0, 0)     # Monday, 10:00 ET
_OFF_SESSION_ET = _dt.datetime(2026, 9, 14, 22, 0, 0)    # Monday, 22:00 ET


def test_should_publish_true_on_first_ever_call(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    should, h, now = qe._should_publish({}, _base_doc())
    assert should is True


def test_should_publish_false_within_interval_no_change(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _base_doc()
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1030.0)   # +30s, under the 60s session default
    should, _, _ = qe._should_publish(state, doc)
    assert should is False


def test_should_publish_true_once_session_interval_elapses(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _base_doc()
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 61.0)
    should, _, _ = qe._should_publish(state, doc)
    assert should is True


def test_should_publish_off_session_uses_longer_interval(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _OFF_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _base_doc()
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    # 90s later: well past the 60s session interval, but under the 600s off-session one.
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 90.0)
    should, _, _ = qe._should_publish(state, doc)
    assert should is False
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 601.0)
    should2, _, _ = qe._should_publish(state, doc)
    assert should2 is True


def test_should_publish_respects_cfg_override(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _base_doc()
    cfg = {"publish_interval_session_sec": 5}
    _, h, now = qe._should_publish({}, doc, cfg=cfg)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 6.0)
    should, _, _ = qe._should_publish(state, doc, cfg=cfg)
    assert should is True, "a 5s configured interval must not wait for the 60s default"


def test_should_publish_meaningful_change_ignores_interval(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc_a = _base_doc(positions={})
    _, h, now = qe._should_publish({}, doc_a)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.5)   # half a second later
    doc_b = _base_doc(positions={"ORB": {"side": "long", "shares": 5}})
    should, _, _ = qe._should_publish(state, doc_b)
    assert should is True, "a lot opening must publish immediately, not wait for the interval"


def test_should_publish_force_always_true(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _base_doc()
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    should, _, _ = qe._should_publish(state, doc, force=True)
    assert should is True


# ── ARMED interval (2026-09-14, revised after aaca82b's lease-renewal protocol) ─────
#
# Once broker.effective_mode is PAPER/LIVE, every ACTUAL publish also renews this
# process's cross-host lease (_Publisher._do_set / _LeaseHolder, landed in aaca82b),
# and a real broker send self-blocks the moment that renewal is older than
# LEASE_SEND_MAX_AGE_SEC (30s, see _LeaseHolder.send_gate). So while armed,
# _should_publish must ignore the session/off-session knobs entirely and fall back to
# publish_interval_armed_sec (default 20s) regardless of session -- these tests are
# the direct guard against silently re-introducing the 600s off-session interval into
# the armed path, which would starve the lease and self-block every order overnight.

def _armed_doc(**overrides):
    return _base_doc(broker={"requested_mode": "PAPER", "effective_mode": "PAPER",
                             "halted": False, "halt_reason": None, "lease_ok_to_send": True,
                             "last_order": {"leg": None, "side": None, "qty": None,
                                           "intent": None, "mode": None, "ok": None,
                                           "sent": None},
                             "last_reconcile_result": None},
                     **overrides)


def test_should_publish_armed_ignores_off_session_interval(monkeypatch):
    """The core regression guard: armed + off-session must NOT wait anywhere near the
    600s off-session interval -- it must use publish_interval_armed_sec instead."""
    monkeypatch.setattr(qe, "_now_et", lambda: _OFF_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _armed_doc()
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 25.0)   # past the 20s armed default
    should, _, _ = qe._should_publish(state, doc)
    assert should is True, ("armed + off-session must publish at the tight armed interval, "
                            "not wait for the 600s off-session one")


def test_should_publish_armed_ignores_in_session_interval_too(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _armed_doc()
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 21.0)
    should, _, _ = qe._should_publish(state, doc)
    assert should is True


def test_should_publish_armed_respects_cfg_override(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _OFF_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = _armed_doc()
    cfg = {"publish_interval_armed_sec": 5}
    _, h, now = qe._should_publish({}, doc, cfg=cfg)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 6.0)
    should, _, _ = qe._should_publish(state, doc, cfg=cfg)
    assert should is True


def test_should_publish_armed_default_is_safely_under_lease_send_max_age():
    """The whole reason this interval exists: it must never approach the 30s bound
    _LeaseHolder.send_gate uses to block a real order over a stale renewal."""
    assert qe.PUBLISH_INTERVAL_ARMED_SEC < 30.0


def test_should_publish_off_mode_unaffected_by_armed_default(monkeypatch):
    """A doc with no broker.effective_mode at all (an older-shaped doc, or a fresh
    default state) must fall back to the OFF-mode session/off-session behaviour, not
    the armed one."""
    monkeypatch.setattr(qe, "_now_et", lambda: _OFF_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    doc = {}   # no "broker" key at all
    _, h, now = qe._should_publish({}, doc)
    state = {"last_doc_hash": h, "last_publish": now}
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0 + 25.0)   # past armed, under off-session
    should, _, _ = qe._should_publish(state, doc)
    assert should is False


# ── publish_async / publish_now: every write flows through the EXISTING _Publisher /
# _LeaseHolder machinery unchanged -- FIX 1 never bypasses it with a side-channel
# write. Driven through publish_now (writes synchronously by design) so these tests
# don't depend on the background publisher thread's own timing.

def test_publish_now_writes_full_doc_synchronously(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    db = _FakeDb()
    state = {}
    qe.publish_now(db, "uid1", _base_doc(), state, log=lambda *a, **k: None)
    assert len(db.calls) == 1
    assert db.calls[0]["merge"] is False


def test_publish_now_skips_when_not_due(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    monkeypatch.setattr(qe.time, "time", lambda: 1000.0)
    db = _FakeDb()
    doc = _base_doc()
    state = {}
    qe.publish_now(db, "uid1", doc, state, force=True, log=lambda *a, **k: None)
    assert len(db.calls) == 1
    monkeypatch.setattr(qe.time, "time", lambda: 1005.0)
    qe.publish_now(db, "uid1", doc, state, force=False, log=lambda *a, **k: None)
    assert len(db.calls) == 1, "unchanged content, 5s later, force=False must not write again"


# ── the two headline volume tests from the fix's own TESTS section ─────────────────

def test_one_hour_of_steady_ticks_bounds_writes(monkeypatch):
    """1 hour of steady 5s ticks with NOTHING meaningful changing must produce at most
    (3600/interval + 1) full-doc writes -- driven through _should_publish directly
    (the decision under test), then applied to the fake db so the count is exact and
    not dependent on the background publisher thread's own timing."""
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    db = _FakeDb()
    doc = _base_doc()
    state = {}
    t = [0.0]
    monkeypatch.setattr(qe.time, "time", lambda: t[0])
    writes = 0
    for _ in range(int(3600 / 5)):     # 720 ticks at the real TICK_SEC cadence
        should, h, now = qe._should_publish(state, doc)
        if should:
            db._ref.set(doc, merge=False)
            state["last_doc_hash"] = h
            state["last_publish"] = now
            writes += 1
        t[0] += 5.0
    interval = qe.PUBLISH_INTERVAL_SESSION_SEC
    assert writes <= (3600 / interval) + 1
    assert writes >= 1


def test_lease_never_goes_stale_overnight_once_armed(monkeypatch):
    """Simulates an 8-hour OFF-SESSION stretch (content never changes) while the
    broker is ARMED, purely through _should_publish's own decision logic -- asserts
    the gap between any two consecutive would-be publishes (each one a lease renewal,
    see _Publisher._do_set) never approaches LEASE_SEND_MAX_AGE_SEC (30s), the bound
    _LeaseHolder.send_gate uses to block a real order. This is the regression this
    fix must never reintroduce: an off-session content interval that starves the
    lease renewal once real orders can flow."""
    monkeypatch.setattr(qe, "_now_et", lambda: _OFF_SESSION_ET)
    doc = _armed_doc()
    state = {}
    t = [0.0]
    monkeypatch.setattr(qe.time, "time", lambda: t[0])
    publish_times = []

    for _ in range(int(8 * 3600 / 5)):   # 8 hours of 5s ticks
        should, h, now = qe._should_publish(state, doc)
        if should:
            state["last_doc_hash"] = h
            state["last_publish"] = now
            publish_times.append(now)
        t[0] += 5.0

    assert publish_times, "at least one publish must have gone out"
    gaps = [b - a for a, b in zip(publish_times, publish_times[1:])]
    assert max(gaps) < qe.LEASE_SEND_MAX_AGE_SEC, (
        f"a {max(gaps):.0f}s gap between publishes while armed would let this host's "
        f"own lease renewal go stale past LEASE_SEND_MAX_AGE_SEC "
        f"({qe.LEASE_SEND_MAX_AGE_SEC}s) and self-block every broker send")


def test_off_mode_overnight_uses_the_relaxed_off_session_interval(monkeypatch):
    """The complement of the armed test above: while OFF (no send-gate risk at all),
    the original, much longer off-session interval is exactly what should govern --
    this is where FIX 1's write-volume savings actually apply."""
    monkeypatch.setattr(qe, "_now_et", lambda: _OFF_SESSION_ET)
    doc = _base_doc()   # effective_mode OFF
    state = {}
    t = [0.0]
    monkeypatch.setattr(qe.time, "time", lambda: t[0])
    publish_times = []

    for _ in range(int(8 * 3600 / 5)):
        should, h, now = qe._should_publish(state, doc)
        if should:
            state["last_doc_hash"] = h
            state["last_publish"] = now
            publish_times.append(now)
        t[0] += 5.0

    gaps = [b - a for a, b in zip(publish_times, publish_times[1:])]
    assert gaps, "at least two publishes expected over 8 hours"
    assert min(gaps) >= qe.PUBLISH_INTERVAL_OFFHOURS_SEC - 1e-6, (
        "OFF mode overnight must use the relaxed off-session interval, not the tight "
        "armed one")


# ── Firestore usage counters ─────────────────────────────────────────────────────────

def test_track_fs_write_and_read_increment_both_buckets():
    state = {}
    qe._track_fs_write(state)
    qe._track_fs_write(state)
    qe._track_fs_read(state)
    assert state["_fs_writes_today"] == 2
    assert state["_fs_writes_hour"] == 2
    assert state["_fs_reads_today"] == 1
    assert state["_fs_reads_hour"] == 1


def test_usage_log_fires_once_per_hour_and_resets_hour_bucket(monkeypatch):
    logged = []
    state = {}
    monkeypatch.setattr(qe, "_now_et", lambda: _IN_SESSION_ET)
    t = [0.0]
    monkeypatch.setattr(qe.time, "time", lambda: t[0])

    qe._track_fs_write(state, n=5)
    qe._maybe_log_fs_usage(state, log=logged.append)   # first call only seeds the window
    assert not logged
    assert state["_fs_writes_hour"] == 5   # not reset yet -- this call only seeded _at

    t[0] = 3601.0
    qe._track_fs_write(state, n=3)
    qe._maybe_log_fs_usage(state, log=logged.append)
    assert len(logged) == 1
    assert "writes=8" in logged[0]          # 5 from before the seed + 3 after
    assert state["_fs_writes_hour"] == 0    # hour bucket reset after logging
    assert state["_fs_writes_today"] == 8   # day bucket NOT reset mid-day


def test_usage_day_bucket_resets_on_a_new_et_date(monkeypatch):
    state = {}
    monkeypatch.setattr(qe, "_now_et", lambda: _dt.datetime(2026, 9, 14, 23, 0, 0))
    qe._track_fs_write(state, n=4)
    qe._maybe_log_fs_usage(state, log=lambda *a: None)
    assert state["_fs_writes_today"] == 4

    monkeypatch.setattr(qe, "_now_et", lambda: _dt.datetime(2026, 9, 15, 0, 5, 0))
    qe._maybe_log_fs_usage(state, log=lambda *a: None)
    assert state["_fs_writes_today"] == 0
