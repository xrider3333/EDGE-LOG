"""api/qqq_exec.py's BOOK-ONLY marking (2026-09-23).

WHY. The QQQ/Webull book records every trade its own engine takes, even when the
matching order never actually reached Webull -- 2026-09-23 10:10 ET, NOISE signalled a
SHORT and Webull refused it (HTTP 417 OPENAPI_GENERATE_NEW_SHORT_POSITION: stock orders
were still on the cash account, since switched to margin), yet the book still booked
that trade at +$4.90 as though the broker had made it too. _book_only_status/
_apply_book_only mark exactly those trades -- an OPEN that reached the broker path and
was refused or failed -- and _book_only_summary totals the book vs the broker with those
trades excluded. This is a SEPARATE read from _broker_trade_parity/_broker_parity_summary
(feature #56, "did the price match") -- book-only asks "did the broker ever hold any
shares at all" -- and reuses the exact same by_base join those tests build with
_broker_orders_by_base / the real _broker_signal_id, never a second joiner.

No network, no real EDGELOG_HOME: every test builds its own trades.csv-shaped row dicts
and broker_orders.csv-shaped lookup dicts by hand, exactly like
test_qqq_exec_broker_parity.py.
"""
from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


# ── helpers (mirrors test_qqq_exec_broker_parity.py) ───────────────────────────────────

def _trade_id(leg="NOISE", stamp="20260923T101000Z", side="S"):
    return f"{leg}-{stamp}-{side}"


def _engine_row(trade_id, pnl="4.90", signal_source="engine", **extra):
    row = {"leg": "NOISE", "trade_id": trade_id, "side": "short", "shares": "10",
          "entry_px": "600.0", "exit_px": "599.51", "pnl": pnl,
          "signal_source": signal_source}
    row.update(extra)
    return row


def _broker_row(trade_id, intent, *, mode, ok, sent=True, reason="", resend=0):
    """One broker_orders.csv-shaped row, using the REAL _broker_signal_id so it groups
    under exactly the key production code would derive."""
    signal_id = qe._broker_signal_id(None, None, intent, trade_id=trade_id)
    if resend:
        signal_id = f"{signal_id}R{resend}"
    return {"signal_id": signal_id, "leg": "NOISE", "intent": intent, "mode": mode,
           "ok": "True" if ok else "False", "sent": "True" if sent else "False",
           "reason": reason}


def _by_base(*rows):
    return qe._broker_orders_by_base(list(rows))


# ── _book_only_status: the six named cases from the build brief ────────────────────────

def test_refused_open_is_book_only():
    """A real Webull rejection: the send reached the broker (sent=True) and the broker
    itself refused it -- today's HTTP 417 short-sale rejection."""
    tid = _trade_id()
    row = _engine_row(tid)
    reason = ("HTTPError: 417 OPENAPI_GENERATE_NEW_SHORT_POSITION -- This order will "
             "generate new short stock positions, which do not match your account type")
    by_base = _by_base(_broker_row(tid, "OPEN", mode="PAPER", ok=False, sent=True,
                                   reason=reason))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is True
    assert out["book_only_reason"] == reason


def test_blocked_by_rails_open_is_book_only():
    """A pre-send BLOCKED (this module's lease gate, or webull_orders' own rails) never
    reaches the network at all -- sent=False, ok=False -- and is still book-only: no
    shares were ever held either way."""
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", mode="BLOCKED", ok=False, sent=False,
                                   reason="lease unverifiable -- shadow record stands"))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is True
    assert out["book_only_reason"] == "lease unverifiable -- shadow record stands"


def test_adapter_error_open_is_book_only():
    """mode=ERROR (an exception before any network call, e.g. the adapter itself failed
    to construct) is a third failure shape beyond BLOCKED/refused -- still book-only."""
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", mode="ERROR", ok=False, sent=False,
                                   reason="RuntimeError: adapter init failed"))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is True
    assert out["book_only_reason"] == "RuntimeError: adapter init failed"


def test_successful_open_is_not_book_only():
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", mode="PAPER", ok=True, sent=True))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is False
    assert out["book_only_reason"] == ""


def test_missing_broker_row_is_unknown_not_book_only():
    """No broker_orders.csv row at all for this trade id (pre-dates trade ids, or its
    OPEN aged out of the file's own ORDERS_KEEP trim) -- UNKNOWN, never marked."""
    row = _engine_row(_trade_id())
    out = qe._book_only_status(row, _by_base(), log=NOOP)
    assert out["book_only"] is False
    assert out["book_only_reason"] == ""


def test_trade_with_no_trade_id_is_unknown_not_book_only():
    row = _engine_row("")
    by_base = _by_base(_broker_row(_trade_id(), "OPEN", mode="BLOCKED", ok=False))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is False


def test_adapter_off_is_not_book_only():
    """mode=OFF means the book was not mirroring to Webull AT ALL that day -- a
    deliberate config-level no-op, distinct from a refusal. ok is True on every OFF row
    (nothing was ever attempted), so this must NOT read as a successful mirror either --
    it is its own third, unknown-by-design state."""
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", mode="OFF", ok=True, sent=False,
                                   reason="mode=OFF (default)"))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is False
    assert out["book_only_reason"] == ""


def test_partial_mirror_open_ok_close_blocked_is_not_book_only():
    """THE PARTIAL-MIRROR RULE (documented on _book_only_status): book_only is decided
    from the OPEN leg ONLY. An OPEN that reached the broker and succeeded means shares
    really were held there, even if the matching CLOSE later failed, was blocked, or
    never mirrored -- that is a different (position-reconciliation) problem, not this
    flag. Calling the whole trade book-only here would understate that the entry really
    happened at the broker."""
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(
        _broker_row(tid, "OPEN", mode="PAPER", ok=True, sent=True),
        _broker_row(tid, "CLOSE", mode="BLOCKED", ok=False, sent=False,
                   reason="nothing to close at the broker for leg 'NOISE'"))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is False
    assert out["book_only_reason"] == ""


def test_resend_landing_ok_after_a_blocked_first_try_is_not_book_only():
    """_broker_order_for/_best_broker_row (the SAME join _broker_trade_parity uses)
    prefers the last successful attempt among an original try and its resends -- a
    trade whose OPEN was blocked once but landed on resend was never actually book-only,
    and must not be reported as such just because an earlier attempt failed."""
    tid = _trade_id()
    row = _engine_row(tid)
    blocked = _broker_row(tid, "OPEN", mode="BLOCKED", ok=False, sent=False,
                          reason="lease unverifiable")
    resent_ok = _broker_row(tid, "OPEN", mode="PAPER", ok=True, sent=True, resend=1)
    out = qe._book_only_status(row, _by_base(blocked, resent_ok), log=NOOP)
    assert out["book_only"] is False


def test_book_only_status_never_raises_on_garbage_row():
    out = qe._book_only_status({}, {}, log=NOOP)
    assert out["book_only"] is False
    out2 = qe._book_only_status({"trade_id": None}, {}, log=NOOP)
    assert out2["book_only"] is False


def test_book_only_reason_falls_back_when_broker_row_has_no_reason_text():
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", mode="BLOCKED", ok=False, reason=""))
    out = qe._book_only_status(row, by_base, log=NOOP)
    assert out["book_only"] is True
    assert "BLOCKED" in out["book_only_reason"]


# ── _apply_book_only: the NT-mirror row dispatch rule ───────────────────────────────────

def test_apply_book_only_leaves_ninjatrader_rows_untouched():
    """A row whose signal_source is "ninjatrader" is never looked up against
    broker_orders.csv at all -- see _broker_parity's own identical dispatch rule."""
    tid = _trade_id()
    nt_row = {"signal_source": "ninjatrader", "trade_id": tid}
    by_base = _by_base(_broker_row(tid, "OPEN", mode="BLOCKED", ok=False))
    trades_all = [dict(nt_row)]
    qe._apply_book_only(trades_all, by_base, log=NOOP)
    assert trades_all[0]["book_only"] is False
    assert trades_all[0]["book_only_reason"] == ""


def test_apply_book_only_marks_engine_rows_in_place():
    tid = _trade_id()
    row = _engine_row(tid)
    by_base = _by_base(_broker_row(tid, "OPEN", mode="BLOCKED", ok=False,
                                   reason="halted: reconcile"))
    trades_all = [row]
    qe._apply_book_only(trades_all, by_base, log=NOOP)
    assert trades_all[0]["book_only"] is True
    assert trades_all[0]["book_only_reason"] == "halted: reconcile"


# ── _book_only_summary: book vs broker totals ───────────────────────────────────────────

def test_book_only_summary_excludes_book_only_trades_from_broker_net():
    trades_all = [
        {"pnl": "4.90", "book_only": True},     # refused short -- never at the broker
        {"pnl": "50.00", "book_only": False},   # a genuine, mirrored trade
        {"pnl": "-10.00", "book_only": False},  # another genuine trade
    ]
    out = qe._book_only_summary(trades_all)
    assert out["book_net"] == 44.90
    assert out["broker_net"] == 40.00
    assert out["book_only_count"] == 1


def test_book_only_summary_equal_when_nothing_is_book_only():
    trades_all = [{"pnl": "12.34", "book_only": False}, {"pnl": "-2.34", "book_only": False}]
    out = qe._book_only_summary(trades_all)
    assert out["book_net"] == out["broker_net"] == 10.00
    assert out["book_only_count"] == 0


def test_book_only_summary_on_all_book_only_trades_is_zero_broker_net():
    trades_all = [{"pnl": "4.90", "book_only": True}, {"pnl": "1.10", "book_only": True}]
    out = qe._book_only_summary(trades_all)
    assert out["book_net"] == 6.00
    assert out["broker_net"] == 0.00
    assert out["book_only_count"] == 2


def test_book_only_summary_empty_trades_all():
    out = qe._book_only_summary([])
    assert out == {"book_net": 0.0, "broker_net": 0.0, "book_only_count": 0}


def test_book_only_summary_uses_real_pnl_fallback_like_the_curve():
    """_book_only_summary must total exactly what the equity curve/table/calendar do
    (_curve_pnl's own pnl-else-real_pnl-else-0 rule) -- an exit the adapter could not
    mark (pnl="nan") must fall back to the tape-repriced real_pnl, not silently zero
    out or poison the total the way a bare float(pnl) once did (2026-09-21 NaN bug)."""
    trades_all = [
        {"pnl": "nan", "real_pnl": "7.25", "book_only": False},
        {"pnl": "3.00", "book_only": False},
    ]
    out = qe._book_only_summary(trades_all)
    assert out["book_net"] == 10.25
    assert out["broker_net"] == 10.25


def test_book_only_summary_never_raises_on_garbage_pnl():
    out = qe._book_only_summary([{"pnl": "not-a-number", "book_only": False}])
    assert out == {"book_net": 0.0, "broker_net": 0.0, "book_only_count": 0}
