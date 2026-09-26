"""tests/test_qqq_deadman.py -- tools/qqq_deadman.py, the off-box dead-man's-switch for
the Webull QQQ paper book (deadman/deadman_keel_guard, 2026-09-26).

Every test drives evaluate() directly on a FAKE doc, per the task spec ("Include
--dry-run and a test with a fake doc") -- no Firestore, no network, no live files (see
tests/conftest.py's live-system guard, which this suite never goes near). main()'s own
Firestore/ntfy wiring is covered by a monkeypatched-client smoke test at the bottom.
"""
import datetime
import os
import sys
import zoneinfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.qqq_deadman as dm  # noqa: E402

ET = zoneinfo.ZoneInfo("America/New_York")


def _et(y, mo, d, h, mi, s=0):
    return datetime.datetime(y, mo, d, h, mi, s, tzinfo=ET)


# A real trading Tuesday, well inside the window, per api/market_calendar.
INSIDE = _et(2026, 9, 22, 12, 0)          # 2026-09-22 12:00 ET
BEFORE_OPEN = _et(2026, 9, 22, 9, 0)      # before 09:25 ET
AFTER_CLOSE = _et(2026, 9, 22, 17, 0)     # after 16:10 ET
WEEKEND = _et(2026, 9, 26, 12, 0)         # a Saturday
NEAR_CLOSE = _et(2026, 9, 22, 16, 9)      # inside SESSION_END (16:10) but past
                                          # qqq_exec's own _in_market_window (16:05)


def _book_doc(updated_at=None, leased_at=None, feed_stale=None, positions=None,
             renew_every_sec=None):
    doc = {}
    if updated_at is not None:
        doc["updated_at"] = updated_at
    if leased_at is not None:
        doc["lease"] = {"host_id": "test-host", "leased_at": leased_at}
        if renew_every_sec is not None:
            doc["lease"]["renew_every_sec"] = renew_every_sec
    if feed_stale is not None:
        doc["feed_stale"] = feed_stale
    if positions is not None:
        doc["positions"] = positions
    return doc


# ── window gate ──────────────────────────────────────────────────────────────────────────
def test_outside_window_skips_every_check():
    for now in (BEFORE_OPEN, AFTER_CLOSE, WEEKEND):
        rep = dm.evaluate(_book_doc(leased_at=now.timestamp()), now)
        assert rep["in_window"] is False
        assert rep["pushes"] == []


def test_inside_window_on_a_trading_day_is_armed():
    rep = dm.evaluate(_book_doc(leased_at=INSIDE.timestamp()), INSIDE)
    assert rep["in_window"] is True


# ── condition 1: book heartbeat ──────────────────────────────────────────────────────────
def test_fresh_lease_heartbeat_is_not_stale():
    doc = _book_doc(leased_at=INSIDE.timestamp() - 10)
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["heartbeat_stale"] is False
    assert rep["pushes"] == []


def test_stale_lease_heartbeat_pushes_urgent():
    doc = _book_doc(leased_at=INSIDE.timestamp() - (dm.HEARTBEAT_STALE_SEC + 30))
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["heartbeat_stale"] is True
    pushes = [p for p in rep["pushes"] if p["severity"] == "urgent"]
    assert len(pushes) == 1
    assert "heartbeat" in pushes[0]["message"].lower()


def test_updated_at_fallback_used_when_no_lease():
    ts_txt = (INSIDE - datetime.timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S")
    doc = _book_doc(updated_at=ts_txt)
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["heartbeat_age_sec"] == pytest.approx(30, abs=5)
    assert rep["checks"]["heartbeat_stale"] is False


def test_missing_doc_entirely_is_treated_as_stale():
    rep = dm.evaluate(None, INSIDE)
    assert rep["checks"]["heartbeat_age_sec"] is None
    assert rep["checks"]["heartbeat_stale"] is True
    assert any(p["severity"] == "urgent" for p in rep["pushes"])


def test_widened_publish_cadence_after_hours_does_not_false_page_at_16_09():
    """Review fix (minor, 2026-09-26): qqq_exec's own _in_market_window ends at 16:05,
    five minutes before this switch's SESSION_END (16:10). When the broker is not
    armed, qqq_exec's publish interval widens to 600s after 16:05 -- so the LAST
    in-session publish lands around 16:05, and a plain HEARTBEAT_STALE_SEC=180 bound
    would read that as stale by 16:09. lease["renew_every_sec"]=600 (the book's own
    advertised cadence) must widen the threshold instead (see
    _heartbeat_stale_threshold) so this does not false-page every day the broker is
    off."""
    last_publish = NEAR_CLOSE - datetime.timedelta(seconds=240)   # ~16:05:00
    doc = _book_doc(leased_at=last_publish.timestamp(), renew_every_sec=600)
    rep = dm.evaluate(doc, NEAR_CLOSE)
    assert rep["checks"]["heartbeat_age_sec"] == pytest.approx(240, abs=5)
    assert rep["checks"]["heartbeat_stale"] is False
    assert rep["pushes"] == []


def test_no_renew_every_sec_falls_back_to_the_plain_floor():
    """Sanity check that the fix above is additive: a doc with no renew_every_sec at
    all (an older doc shape, or the broker armed and publishing on its normal fast
    cadence) still uses the plain HEARTBEAT_STALE_SEC floor, unchanged from before."""
    doc = _book_doc(leased_at=(INSIDE.timestamp() - (dm.HEARTBEAT_STALE_SEC + 30)))
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["heartbeat_stale"] is True


def test_dedupe_pages_on_crossing_then_at_most_every_30_minutes():
    doc = _book_doc(leased_at=0.0)   # always stale relative to any `now` used below
    rep1 = dm.evaluate(doc, INSIDE)
    assert len(rep1["pushes"]) == 1, "first observation of a stale heartbeat must page"

    # same crossing, 5 minutes later -- must NOT page again
    rep2 = dm.evaluate(doc, INSIDE + datetime.timedelta(minutes=5), prior_state=rep1["state"])
    assert rep2["pushes"] == [], "must not re-page inside the 30-minute repeat window"

    # 31 minutes after the FIRST page -- must page again
    rep3 = dm.evaluate(doc, INSIDE + datetime.timedelta(minutes=31), prior_state=rep2["state"])
    assert len(rep3["pushes"]) == 1, "must re-page once the repeat window has elapsed"


def test_recovery_clears_dedupe_so_the_next_crossing_pages_immediately():
    bad = _book_doc(leased_at=0.0)
    rep1 = dm.evaluate(bad, INSIDE)
    assert len(rep1["pushes"]) == 1

    good = _book_doc(leased_at=(INSIDE + datetime.timedelta(minutes=1)).timestamp())
    rep2 = dm.evaluate(good, INSIDE + datetime.timedelta(minutes=1), prior_state=rep1["state"])
    assert rep2["pushes"] == []

    rep3 = dm.evaluate(bad, INSIDE + datetime.timedelta(minutes=2), prior_state=rep2["state"])
    assert len(rep3["pushes"]) == 1, "a fresh crossing after a recovery must page immediately"


# ── condition 2: open position + stale signal engine ────────────────────────────────────
def test_open_position_with_fresh_signal_engine_does_not_page():
    doc = _book_doc(leased_at=INSIDE.timestamp(), feed_stale=False,
                    positions={"NOISE": {"side": "long", "shares": 10}})
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["open_position"] is True
    assert not [p for p in rep["pushes"] if p["severity"] == "high"]


def test_open_position_with_stale_signal_engine_pages_high():
    doc = _book_doc(leased_at=INSIDE.timestamp(), feed_stale=True,
                    positions={"NOISE": {"side": "long", "shares": 10}})
    rep = dm.evaluate(doc, INSIDE)
    highs = [p for p in rep["pushes"] if p["severity"] == "high"]
    assert len(highs) == 1
    assert "position" in highs[0]["message"].lower()


def test_flat_book_with_stale_signal_engine_does_not_page():
    doc = _book_doc(leased_at=INSIDE.timestamp(), feed_stale=True, positions={})
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["open_position"] is False
    assert not [p for p in rep["pushes"] if p["severity"] == "high"]


def test_feed_stale_absent_degrades_to_unknown_never_a_false_alarm():
    """An older doc shape / a mode that never sets feed_stale must never be read as
    "signal engine confirmed stale" -- only an explicit True counts."""
    doc = _book_doc(leased_at=INSIDE.timestamp(),
                    positions={"NOISE": {"side": "long", "shares": 10}})
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["signal_engine_known"] is False
    assert not [p for p in rep["pushes"] if p["severity"] == "high"]


def test_zero_shares_position_row_is_not_open():
    doc = _book_doc(leased_at=INSIDE.timestamp(), feed_stale=True,
                    positions={"NOISE": {"side": "long", "shares": 0}})
    rep = dm.evaluate(doc, INSIDE)
    assert rep["checks"]["open_position"] is False


def test_printed_report_omits_open_position_but_keeps_other_checks(monkeypatch, capsys):
    """Minor fix (2026-09-26): this repo is public, so Actions logs are world-readable
    -- the printed [qqq-deadman] JSON line drops the open_position boolean but keeps
    every other check (evaluate()'s own return value is untouched -- see
    test_zero_shares_position_row_is_not_open above, which still reads
    rep["checks"]["open_position"] directly)."""
    class _FakeDb:
        pass

    monkeypatch.setattr(dm, "_get_firestore_client", lambda: _FakeDb())
    monkeypatch.setattr(dm, "_read_meta_doc", lambda db, uid, name: (
        _book_doc(leased_at=INSIDE.timestamp(), feed_stale=False,
                 positions={"NOISE": {"side": "long", "shares": 10}})
        if name == "qqq_exec" else {}))
    monkeypatch.setattr(dm, "_write_meta_doc", lambda *a, **k: None)
    monkeypatch.setenv("EDGELOG_UID", "test-uid")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)

    class _FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return INSIDE
    monkeypatch.setattr(dm._dt, "datetime", _FixedDatetime)

    rc = dm.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "open_position" not in out
    assert "heartbeat_stale" in out


# ── main() wiring (monkeypatched Firestore/ntfy -- no network, no live files) ───────────
def test_main_dry_run_never_writes_or_pushes(monkeypatch, capsys):
    class _FakeDb:
        pass

    monkeypatch.setattr(dm, "_get_firestore_client", lambda: _FakeDb())
    monkeypatch.setattr(dm, "_read_meta_doc", lambda db, uid, name: (
        _book_doc(leased_at=0.0) if name == "qqq_exec" else {}))

    pushed = []
    written = []
    monkeypatch.setattr(dm, "_ntfy_post", lambda *a, **k: pushed.append((a, k)) or True)
    monkeypatch.setattr(dm, "_write_meta_doc", lambda *a, **k: written.append((a, k)))
    monkeypatch.setenv("EDGELOG_UID", "test-uid")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)

    # Fix "now" inside the window regardless of when this test actually runs.
    class _FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return INSIDE

    monkeypatch.setattr(dm._dt, "datetime", _FixedDatetime)

    rc = dm.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert not pushed, "dry-run must never actually push"
    assert not written, "dry-run must never write the state doc"
    assert "DRY-RUN would push" in out


def test_print_secrets_lists_the_required_names(capsys):
    rc = dm.main(["--print-secrets"])
    out = capsys.readouterr().out
    assert rc == 0
    for name in dm.REQUIRED_SECRETS:
        assert name in out
