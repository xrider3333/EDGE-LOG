"""tools/live_parity_check.py -- the WITHDRAWN-ROW audit (ENGU-Q hardening, 2026-11-18).

WHY. "Were any withdrawn signals ordered?" was a question nothing answered: VOID_* rows are
written retrospectively by a repair tool, so their own stamps cannot settle it, and the nightly
parity check looked only at a day's ENTRY/EXIT rows. void_audit() counts every withdrawn row in
the ledger and, per row, whether an order carrying its trade id was actually SENT -- separating
the ones whose order was blocked or failed, which are not exposure.

The fixtures are the real 2026-09 shapes: the two ENGU-Q ghosts (orders SENT) and the
2026-09-21 NOISE duplicate (order written BLOCKED, sent False).
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import live_parity_check as lpc     # noqa: E402


def _sig(leg, event, ref_time, trade_id="", side="long"):
    return {"leg": leg, "event": event, "side": side, "ref_time": ref_time,
            "trade_id": trade_id, "ref_price": "716.8592"}


def _order(leg, intent, signal_id, sent, ts_et, mode="PAPER"):
    return {"ts_et": ts_et, "leg": leg, "intent": intent, "side": "BUY", "shares": "10",
            "signal_id": signal_id, "mode": mode, "ok": str(bool(sent)), "sent": str(bool(sent)),
            "reason": "" if sent else "halted: reconcile mismatch vs Webull"}


GHOST_TID = "ENGUQ_335-20260917T190700Z-L"
GHOST_SID = "qxENGUQ33520260917T190700ZLO"
DUP_TID = "NOISE_304-20260921T134000Z-L"
DUP_SID = "qxNOISE30420260921T134000ZLO"


def test_signal_id_shapes_match_the_executor_convention():
    """The join key: "qx" + the trade id with separators stripped + O or C. If this drifts
    from api/qqq_exec.py's own _broker_signal_id the audit silently reads zero."""
    assert lpc._signal_id_shapes(GHOST_TID) == {GHOST_SID, GHOST_SID[:-1] + "C"}


def test_a_withdrawn_row_whose_order_was_sent_is_a_finding():
    sig = [_sig("ENGUQ_335", "VOID_ENTRY", "2026-09-17T15:07:00-04:00", GHOST_TID)]
    broker = [_order("ENGUQ", "OPEN", GHOST_SID, True, "2026-09-17 15:08:25")]
    summary, findings = lpc.void_audit(sig, broker)

    assert summary["rows"] == 1 and summary["with_trade_id"] == 1
    assert summary["ordered_sent"] == 1 and summary["ordered_blocked"] == 0
    assert summary["ordered"][0]["trade_id"] == GHOST_TID
    assert summary["ordered"][0]["first_order_ts_et"] == "2026-09-17 15:08:25"
    assert [f["kind"] for f in findings] == ["VOID_ORDERED"]
    assert "SENT" in findings[0]["detail"]
    assert "AFTER" in findings[0]["detail"], (
        "the finding must say the void label may post-date the order -- otherwise it reads as "
        "a live mis-order, which is exactly the mistake this audit exists to prevent")


def test_a_withdrawn_row_whose_order_was_blocked_is_counted_apart():
    sig = [_sig("NOISE_304", "VOID_ENTRY", "2026-09-21T09:40:00-04:00", DUP_TID)]
    broker = [_order("NOISE", "OPEN", DUP_SID, False, "2026-09-21 09:45:12", mode="BLOCKED")]
    summary, findings = lpc.void_audit(sig, broker)

    assert summary["ordered_blocked"] == 1 and summary["ordered_sent"] == 0
    assert findings == [], "a blocked order is not exposure and must not raise a finding"


def test_rows_without_a_trade_id_are_counted_but_never_joined():
    """Pre-trade-id rows (the 2026-09-14 NOISE replay voids) have no id to join an order on;
    they must count as withdrawn rows and claim nothing about orders."""
    sig = [_sig("NOISE_304", "VOID_SEED", ""),
           _sig("NOISE_304", "VOID_ENTRY", "2026-09-03T09:40:00-04:00")]
    summary, findings = lpc.void_audit(sig, [_order("NOISE", "OPEN", "qxSOMETHINGO", True, "x")])

    assert summary["rows"] == 2 and summary["with_trade_id"] == 0
    assert summary["ordered_sent"] == 0 and findings == []
    assert summary["by_event"] == {"VOID_SEED": 1, "VOID_ENTRY": 1}


def test_an_unwithdrawn_ledger_produces_nothing():
    sig = [_sig("ORB_R6", "ENTRY", "2026-09-17T09:40:00-04:00", "ORB_R6-20260917T134000Z-L"),
           _sig("ORB_R6", "EXIT", "2026-09-17T10:00:00-04:00", "ORB_R6-20260917T134000Z-L")]
    summary, findings = lpc.void_audit(sig, [_order("ORB", "OPEN", "qxORBR620260917T134000ZLO",
                                                    True, "2026-09-17 09:41:02")])
    assert summary["rows"] == 0 and findings == []


def test_a_sent_order_for_a_DIFFERENT_trade_is_not_attributed():
    """The join is the exact signal id, never a substring: a neighbouring trade's order must
    not be read as an order for the withdrawn one."""
    sig = [_sig("ENGUQ_335", "VOID_ENTRY", "2026-09-17T15:07:00-04:00", GHOST_TID)]
    other = "qxENGUQ33520260917T190900ZLO"          # the REAL 15:09 entry
    summary, findings = lpc.void_audit(sig, [_order("ENGUQ", "OPEN", other, True, "x")])
    assert summary["ordered_sent"] == 0 and findings == []


def test_void_ordered_is_a_declared_kind_and_pushes_as_affected():
    """A finding kind the push does not know about would be sent as a bare name at low
    priority -- an order for a withdrawn signal is 'trading affected'."""
    assert "VOID_ORDERED" in lpc.KINDS
    f = lpc._finding("VOID_ORDERED", "ENGUQ_335", "VOID_ENTRY", "long", None, None,
                     "detail", plain="an order was sent for a signal the engine later withdrew")
    item = lpc._push_item(f)
    assert "withdrawn" in item
    note = lpc.build_push([f])
    assert note is not None and note["priority"] == "high"


def test_a_malformed_broker_ledger_does_not_raise():
    sig = [_sig("ENGUQ_335", "VOID_ENTRY", "2026-09-17T15:07:00-04:00", GHOST_TID)]
    summary, findings = lpc.void_audit(sig, [{}, {"signal_id": ""}, {"signal_id": GHOST_SID}])
    assert summary["rows"] == 1
    assert summary["ordered_sent"] == 0 and summary["ordered_blocked"] == 1, (
        "a row with no `sent` value is not evidence that anything was sent")


def test_an_empty_ledger_is_handled():
    assert lpc.void_audit(None, None) == ({"rows": 0, "by_event": {}, "with_trade_id": 0,
                                           "ordered_sent": 0, "ordered_blocked": 0,
                                           "ordered": []}, [])
