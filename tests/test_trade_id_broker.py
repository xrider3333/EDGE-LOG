"""BROKER ORDER IDS for slot trade ids (DIP #424 live leg, OWNER GO 2026-10-10, MANAGER #115).

api/trade_id.py broker_signal_base is the ONE rule that turns a trade id into the broker signal id
base ("qx" + the id's letters and digits + O/C) -- api/qqq_exec.py _broker_signal_id,
tools/qqq_reprice.py _signal_base and tools/qqq_bars_publish.py signal_id_base all go through it.

Pinned here:
  * an id WITHOUT a slot is byte-identical to the rule it always was (the legacy formula is
    written out below, not imported);
  * every DIP mechanism slot is a ONE-character code: every DIP id is 27 characters, 29 with a
    resend R1-R3 -- inside Webull's 32, so api/webull_orders.py's sanitizer never hashes one;
  * a split order's part ids (webull_orders._part_client_order_id) are distinct between a DIP
    trade's OPEN and CLOSE, for the plain id and for every resend (with the slot NAME, STREAK's
    base was 32 characters: its split parts trimmed to "...LSTREA-1" for both sides);
  * the executor and both tools derive the SAME id for every slot and intent;
  * a slot that is not a known mechanism keeps the old rule.
No network, no files.
"""
import re

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO
import tools.qqq_bars_publish as qb
import tools.qqq_reprice as R

STAMP = "2026-10-13T09:30:00-04:00"          # Tuesday 10-13, the DIP leg's first session open
SLOTS = ("RSI", "DBL", "PB", "CAP", "IBS", "STREAK", "GAPDN")


def _legacy(trade_id, intent):
    """The rule before 2026-10-10, written out: "qx" + every letter/digit of the id + O/C."""
    return "qx" + re.sub(r"[^A-Za-z0-9]", "", str(trade_id)) + {"OPEN": "O", "CLOSE": "C"}[intent]


def _dip_tid(slot, when=STAMP):
    return T.make("DIP_424", when, "long", slot=slot)


def test_the_slot_codes_cover_dip_s_seven_mechanisms_in_order():
    assert tuple(T.BROKER_SLOT_CODES) == SLOTS == tuple(m for m, _flag in cs.DIP_MECHS)
    assert list(T.BROKER_SLOT_CODES.values()) == ["R", "D", "P", "C", "I", "S", "G"]
    assert len(set(T.BROKER_SLOT_CODES.values())) == 7, "one code per mechanism"
    assert qe.DIP_SLOTS == SLOTS


@pytest.mark.parametrize("tid", [
    "NOISE_382-20261008T143000Z-L", "ORB_R6-20261008T144000Z-S", "ENGUQ_335-20260924T161700Z-L",
    "NOISE_304-20260915T135500Z-L", "NT_ORB-20260903T150000Z-S"])
@pytest.mark.parametrize("intent", ["OPEN", "CLOSE"])
def test_an_id_without_a_slot_is_byte_identical(tid, intent):
    want = _legacy(tid, intent)
    assert T.broker_signal_base(tid, intent) == want
    assert qe._broker_signal_id("X", "t", intent, trade_id=tid) == want
    assert qb.signal_id_base(tid, intent) == want
    assert R._signal_base(tid, intent) == want
    # the reduce number and the pre-trade-id fallback are untouched
    assert qe._broker_signal_id("X", "t", intent, seq=2, trade_id=tid) == want + "2"
    assert qe._broker_signal_id("ORB", "2026-09-03 10:00:00", "OPEN") == "qqqexec-ORB-2026-09-03 10:00:00-OPEN"


def test_known_ids_keep_their_exact_text():
    assert qe._broker_signal_id(None, None, "OPEN", trade_id="NOISE_304-20260915T135500Z-L") == \
        "qxNOISE30420260915T135500ZLO"
    assert qe._broker_signal_id(None, None, "CLOSE", trade_id="ENGUQ_335-20261008T150000Z-L") == \
        "qxENGUQ33520261008T150000ZLC"


@pytest.mark.parametrize("slot", SLOTS)
def test_every_dip_slot_id_is_27_characters_and_29_with_a_resend(slot):
    tid = _dip_tid(slot)
    assert tid == f"DIP_424-20261013T133000Z-L-{slot}"
    for intent, code in (("OPEN", "O"), ("CLOSE", "C")):
        base = qe._broker_signal_id("DIP_" + slot, None, intent, trade_id=tid)
        assert base == f"qxDIP42420261013T133000ZL{T.BROKER_SLOT_CODES[slot]}{code}"
        assert len(base) == 27
        for n in (1, 2, 3):
            rid = f"{base}R{n}"                        # _mirror_to_broker's resend form
            assert len(rid) == 29 <= WO.CLIENT_ORDER_ID_MAX
            assert WO._sanitize_client_order_id(rid) == rid, "never hashed"
            assert qe._signal_id_base(rid) == base, "the resend groups under its base"


def test_with_the_slot_name_streak_would_have_collided_and_now_does_not():
    tid = _dip_tid("STREAK")
    old_open, old_close = _legacy(tid, "OPEN"), _legacy(tid, "CLOSE")
    assert len(old_open) == 32
    assert WO._part_client_order_id(old_open, 1, 2) == WO._part_client_order_id(old_close, 1, 2), \
        "the defect: both sides' first split part was ...LSTREA-1"
    new_open = qe._broker_signal_id(None, None, "OPEN", trade_id=tid)
    new_close = qe._broker_signal_id(None, None, "CLOSE", trade_id=tid)
    assert WO._part_client_order_id(new_open, 1, 2) != WO._part_client_order_id(new_close, 1, 2)


def test_every_split_part_of_every_dip_id_is_distinct_and_untrimmed():
    seen = set()
    for slot in SLOTS:
        tid = _dip_tid(slot)
        for intent in ("OPEN", "CLOSE"):
            base = qe._broker_signal_id(None, None, intent, trade_id=tid)
            for sid in [base] + [f"{base}R{n}" for n in (1, 2, 3)]:
                coid = WO._sanitize_client_order_id(sid)
                assert coid == sid
                for i in (1, 2):
                    part = WO._part_client_order_id(coid, i, 2)
                    assert part == f"{coid}-{i}", "no trim: the whole id survives"
                    assert len(part) <= WO.CLIENT_ORDER_ID_MAX
                    assert part not in seen
                    seen.add(part)
                assert coid not in seen
                seen.add(coid)
    assert len(seen) == 7 * 2 * 4 * 3


def test_two_trades_of_one_slot_and_one_trade_of_two_slots_never_share_an_id():
    a = qe._broker_signal_id(None, None, "OPEN", trade_id=_dip_tid("RSI"))
    b = qe._broker_signal_id(None, None, "OPEN", trade_id=_dip_tid("RSI", "2026-10-14T09:30:00-04:00"))
    c = qe._broker_signal_id(None, None, "OPEN", trade_id=_dip_tid("DBL"))
    unslotted = qe._broker_signal_id(None, None, "OPEN", trade_id=T.make("DIP_424", STAMP, "long"))
    assert len({a, b, c, unslotted}) == 4


@pytest.mark.parametrize("slot", SLOTS)
@pytest.mark.parametrize("intent", ["OPEN", "CLOSE"])
def test_the_executor_and_both_tools_derive_the_same_dip_id(slot, intent):
    tid = _dip_tid(slot)
    want = qe._broker_signal_id(None, None, intent, trade_id=tid)
    assert qb.signal_id_base(tid, intent) == want
    assert R._signal_base(tid, intent) == want
    assert T.broker_signal_base(tid, intent) == want


def test_an_unknown_slot_keeps_the_old_rule_and_junk_never_raises():
    tid = "DIP_424K-20261009T133000Z-L-XYZ"      # a valid id; XYZ is no mechanism
    assert T.broker_signal_base(tid, "OPEN") == _legacy(tid, "OPEN")
    assert T.broker_id_body("FIX-DIP_RSI-20261013093105") == "FIXDIPRSI20261013093105"
    for junk in (None, "", "not an id", 42):
        assert T.broker_signal_base(junk, "CLOSE").startswith("qx")
    assert R._signal_base("", "OPEN") is None
    with pytest.raises(KeyError):
        qb.signal_id_base(_dip_tid("RSI"), "LEVELS")
