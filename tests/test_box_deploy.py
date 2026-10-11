"""tests/test_box_deploy.py -- pure decision-function tests for tools/box_deploy.py
(the box deploy/change-control tool, WEBULL_GO_LIVE.md 1.9). Exercises the time-window
and flatness decisions, the strategy-chain text parser, the NRestarts crash-loop guard
(_n_restarts/_restarts_stable) and the boot-verification poll loop (_verify_boot) --
all with fake clocks/state/text, plus every small remote-git/config helper
(_read_remote_json, _remote_resolve_commit, _remote_git_clean, _remote_broker_mode)
with `_ssh` monkeypatched to a fake result (never a real subprocess). No test in this
module opens an ssh connection or touches the network; importing tools.box_deploy
itself performs no I/O.
"""
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import box_deploy  # noqa: E402


# ── _in_protected_window ──────────────────────────────────────────────────────────────
def test_inside_window_on_a_trading_day_is_protected():
    # Wednesday 2026-09-23, 10:00 ET -- an ordinary trading session, mid-window.
    now = dt.datetime(2026, 9, 23, 10, 0)
    assert box_deploy._in_protected_window(now) is True


def test_before_open_is_not_protected():
    now = dt.datetime(2026, 9, 23, 9, 24, 59)
    assert box_deploy._in_protected_window(now) is False


def test_at_0925_is_protected_boundary_inclusive():
    now = dt.datetime(2026, 9, 23, 9, 25, 0)
    assert box_deploy._in_protected_window(now) is True


def test_at_1605_is_not_protected_boundary_exclusive():
    now = dt.datetime(2026, 9, 23, 16, 5, 0)
    assert box_deploy._in_protected_window(now) is False


def test_just_before_1605_is_still_protected():
    now = dt.datetime(2026, 9, 23, 16, 4, 59)
    assert box_deploy._in_protected_window(now) is True


def test_weekend_is_never_protected_even_at_1000():
    # Saturday 2026-09-26.
    now = dt.datetime(2026, 9, 26, 10, 0)
    assert box_deploy._in_protected_window(now) is False


def test_market_holiday_is_never_protected():
    # Labor Day 2026-09-07 (Monday) -- a weekday but not a session.
    now = dt.datetime(2026, 9, 7, 10, 0)
    assert box_deploy._in_protected_window(now) is False


def test_half_day_afternoon_is_still_a_session_and_protected():
    # Day after Thanksgiving 2026-11-27 closes at 13:00 ET, but 10:00 ET is still a
    # normal trading session and still inside the protected window -- _in_protected_window
    # only ever checks is_session + the fixed clock window, never the half-day close time.
    now = dt.datetime(2026, 11, 27, 10, 0)
    assert box_deploy._in_protected_window(now) is True


# ── _book_is_flat ──────────────────────────────────────────────────────────────────────
def test_refuses_when_qqq_state_is_unreadable():
    # None means "couldn't read/parse it" (see _read_remote_json) -- it must never be
    # treated as an empty, flat book. This is the case the pre-fix bug got wrong:
    # _read_remote_json used to return {} on any ssh failure, and _book_is_flat({}, ...)
    # trusted that as flat.
    flat, reasons = box_deploy._book_is_flat(None, {})
    assert flat is False
    assert any("qqq_exec state.json unreadable" in r for r in reasons)


def test_refuses_when_webull_state_is_unreadable():
    flat, reasons = box_deploy._book_is_flat({}, None)
    assert flat is False
    assert any("webull_orders state.json unreadable" in r for r in reasons)


def test_refuses_when_both_states_are_unreadable():
    flat, reasons = box_deploy._book_is_flat(None, None)
    assert flat is False
    assert len(reasons) == 2


def test_flat_with_explicitly_empty_structures():
    qqq = {"legs": {}, "_broker_resend": {}, "_broker_fill_capture": {}}
    webull = {"broker_sent_positions": {}}
    flat, reasons = box_deploy._book_is_flat(qqq, webull)
    assert flat is True
    assert reasons == []


def test_not_flat_with_an_open_leg():
    qqq = {"legs": {"NOISE_382": {"side": "long", "qty": 5}}}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("open legs" in r for r in reasons)


def test_not_flat_with_nonzero_broker_position():
    webull = {"broker_sent_positions": {"NOISE_382": {"qty": 15}}}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is False
    assert any("broker_sent_positions" in r for r in reasons)


def test_flat_with_zero_qty_broker_position():
    # a leftover 0-qty entry (the go-live audit's "ORB on a different account" case)
    # must NOT block a deploy.
    webull = {"broker_sent_positions": {"ORB_R6": {"qty": 0}}}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is True
    assert reasons == []


def test_not_flat_with_pending_resend():
    qqq = {"_broker_resend": {"NOISE_382:OPEN": {"tries": 1}}}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("resend" in r for r in reasons)


def test_not_flat_with_pending_fill_capture():
    qqq = {"_broker_fill_capture": {"ORB_R6:OPEN": {"leg": "ORB_R6"}}}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("fill-capture" in r for r in reasons)


def test_not_flat_reports_every_reason_at_once():
    qqq = {"legs": {"NOISE_382": {}}, "_broker_resend": {"x": {}}}
    webull = {"broker_sent_positions": {"NOISE_382": {"qty": 3}}}
    flat, reasons = box_deploy._book_is_flat(qqq, webull)
    assert flat is False
    assert len(reasons) == 3


# ── _book_is_flat: malformed shapes must fail closed, never raise ─────────────────────
def test_malformed_broker_position_value_does_not_raise():
    # A broker_sent_positions entry that is a bare int (not {"qty": ...}) used to
    # blow up with AttributeError inside (v or {}).get("qty") -- must now be reported
    # as a reason, not crash, and the book must be treated as not flat.
    webull = {"broker_sent_positions": {"NOISE_382": 5}}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is False
    assert any("not a mapping" in r for r in reasons)


def test_malformed_legs_value_does_not_raise():
    # "legs" itself as a list (not a dict) used to blow up in sorted(legs) after the
    # truthy check, or otherwise be silently misread -- must fail closed instead.
    qqq = {"legs": ["NOISE_382"]}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("'legs' is not a mapping" in r for r in reasons)


def test_malformed_broker_sent_positions_container_does_not_raise():
    webull = {"broker_sent_positions": "not-a-dict"}
    flat, reasons = box_deploy._book_is_flat({}, webull)
    assert flat is False
    assert any("broker_sent_positions' is not a mapping" in r for r in reasons)


def test_malformed_resend_and_fillcap_do_not_raise():
    qqq = {"_broker_resend": 1, "_broker_fill_capture": [1, 2]}
    flat, reasons = box_deploy._book_is_flat(qqq, {})
    assert flat is False
    assert any("_broker_resend' is not a mapping" in r for r in reasons)
    assert any("_broker_fill_capture' is not a mapping" in r for r in reasons)


def test_well_formed_flat_state_is_unaffected_by_the_malformed_shape_guard():
    # The hardening above must not change the result for ordinary, well-formed
    # input -- re-asserts the original flat/not-flat behaviour still holds.
    qqq = {"legs": {}, "_broker_resend": {}, "_broker_fill_capture": {}}
    webull = {"broker_sent_positions": {"ORB_R6": {"qty": 0}}}
    flat, reasons = box_deploy._book_is_flat(qqq, webull)
    assert flat is True
    assert reasons == []


def test_none_states_refuse_rather_than_count_as_empty():
    # Renamed/inverted from the pre-fix version of this test, which asserted flat is
    # True -- exactly the fail-open behaviour the go-live review flagged.
    flat, reasons = box_deploy._book_is_flat(None, None)
    assert flat is False
    assert reasons != []


# ── _book_check / _book_is_flat: HOLD-AWARE (DIP #424 live, OWNER GO 2026-10-10) ────────
# DIP's seven one-lot legs hold overnight and some are open on most days: a lot the executor
# holds on purpose, with no pending close and matching Webull exactly, is accepted; anything
# else still refuses, and nothing unreadable is guessed.
DIP_HOLD = ("ENGUQ", "DIP_RSI", "DIP_DBL", "DIP_PB", "DIP_CAP", "DIP_IBS", "DIP_STREAK", "DIP_GAPDN")


def _held_lot(shares=6, side="long", hold=True, **over):
    lot = {"side": side, "shares_remaining": shares, "entry_px": 600.0,
           "entry_ts": "2026-10-13 09:35:20", "trade_id": "DIP_424-20261013T133000Z-L-RSI"}
    if hold:
        lot["hold"] = {"since": "2026-10-13", "close_mark_px": 601.0}
    lot.update(over)
    return lot


def _pos(qty, symbol="QQQ"):
    return {"symbol": symbol, "qty": qty, "account_id": "ACCT-must-never-print-0001"}


def _dip_book(*legs, shares=6):
    qqq = {"legs": {leg: _held_lot(shares) for leg in legs}, "_broker_resend": {},
           "_broker_fill_capture": {}}
    webull = {"broker_sent_positions": dict({leg: _pos(shares) for leg in legs},
                                            ORB={"symbol": "QQQ", "qty": 0})}
    return qqq, webull


def test_held_dip_lots_matching_webull_are_accepted():
    qqq, webull = _dip_book("DIP_RSI", "DIP_PB", "DIP_CAP")
    ok, reasons, held = box_deploy._book_check(qqq, webull, DIP_HOLD)
    assert ok is True and reasons == []
    assert held == [{"leg": "DIP_CAP", "side": "long", "shares": 6, "since": "2026-10-13"},
                    {"leg": "DIP_PB", "side": "long", "shares": 6, "since": "2026-10-13"},
                    {"leg": "DIP_RSI", "side": "long", "shares": 6, "since": "2026-10-13"}]
    assert box_deploy._book_is_flat(qqq, webull, DIP_HOLD) == (True, [])
    # the hold block alone is enough (no hold list given / config unreadable)
    assert box_deploy._book_is_flat(qqq, webull) == (True, [])
    assert box_deploy._held_lot_words(held[0]) == ("DIP_CAP long 6 (held since 2026-10-13, "
                                                   "Webull holds 6 for it)")


def test_all_seven_dip_lots_held_are_accepted():
    legs = DIP_HOLD[1:]
    qqq, webull = _dip_book(*legs)
    ok, reasons, held = box_deploy._book_check(qqq, webull, DIP_HOLD)
    assert ok is True and len(held) == 7 and sum(x["shares"] for x in held) == 42


def test_a_lot_on_the_hold_list_without_its_hold_block_is_accepted():
    qqq = {"legs": {"DIP_IBS": _held_lot(hold=False)}}
    webull = {"broker_sent_positions": {"DIP_IBS": _pos(6)}}
    ok, reasons, held = box_deploy._book_check(qqq, webull, DIP_HOLD)
    assert ok is True and held == [{"leg": "DIP_IBS", "side": "long", "shares": 6, "since": None}]
    assert "held overnight, Webull holds 6" in box_deploy._held_lot_words(held[0])
    # ...but not when the hold list is unknown or switched off: then it is an open leg
    for hl in (None, ()):
        ok, reasons, held = box_deploy._book_check(qqq, webull, hl)
        assert ok is False and held == []
        assert any("open legs that are not held overnight: ['DIP_IBS']" in r for r in reasons)
        assert any("broker_sent_positions not flat" in r for r in reasons)


def test_a_non_held_open_lot_beside_held_dip_lots_refuses():
    qqq, webull = _dip_book("DIP_RSI", "DIP_PB")
    qqq["legs"]["NOISE"] = {"side": "long", "shares_remaining": 10}
    webull["broker_sent_positions"]["NOISE"] = _pos(10)
    ok, reasons, held = box_deploy._book_check(qqq, webull, DIP_HOLD)
    assert ok is False
    assert any("open legs that are not held overnight: ['NOISE']" in r for r in reasons)
    assert any("broker_sent_positions not flat: {'NOISE': 10}" in r for r in reasons)
    # the held lots were fine on their own (main prints them beside the refusal)
    assert [x["leg"] for x in held] == ["DIP_PB", "DIP_RSI"]
    assert box_deploy._book_is_flat(qqq, webull, DIP_HOLD)[0] is False


def test_pending_resend_or_fill_capture_refuses_with_held_lots():
    for key, entry in (("_broker_resend", {"DIP_DBL:OPEN": {"tries": 1}}),
                       ("_broker_fill_capture", {"DIP_RSI:CLOSE": {"leg": "DIP_RSI"}})):
        qqq, webull = _dip_book("DIP_RSI", "DIP_PB")
        qqq[key] = entry
        ok, reasons, _held = box_deploy._book_check(qqq, webull, DIP_HOLD)
        assert ok is False
        assert any(("resend" if key == "_broker_resend" else "fill-capture") in r for r in reasons)


def test_a_held_lot_with_a_pending_close_refuses():
    qqq, webull = _dip_book("DIP_RSI", "DIP_PB")
    qqq["legs"]["DIP_PB"]["close_pending"] = {"reason": "exit", "at": "2026-10-13 16:20:00"}
    ok, reasons, held = box_deploy._book_check(qqq, webull, DIP_HOLD)
    assert ok is False
    assert any("held lot DIP_PB has a pending close (exit)" in r for r in reasons)
    # its Webull shares are then not "accepted" either
    assert any("broker_sent_positions not flat: {'DIP_PB': 6}" in r for r in reasons)
    assert [x["leg"] for x in held] == ["DIP_RSI"]
    # an empty close_pending block is still the executor's pending-close marker
    qqq["legs"]["DIP_PB"]["close_pending"] = {}
    ok, reasons, _held = box_deploy._book_check(qqq, webull, DIP_HOLD)
    assert ok is False and any("held lot DIP_PB has a pending close --" in r for r in reasons)


def test_a_held_lot_that_does_not_match_webull_refuses():
    cases = [
        ({"DIP_RSI": _pos(5)}, "qty 5"),                       # fewer shares at Webull
        ({"DIP_RSI": _pos(12)}, "qty 12"),                     # more
        ({}, "missing"),                                        # nothing booked at Webull
        ({"DIP_RSI": _pos(0)}, "qty 0"),
        ({"DIP_RSI": _pos(-6)}, "qty -6"),                     # the other side
        ({"DIP_RSI": _pos(6, symbol="SPY")}, "of 'SPY'"),      # another symbol
        ({"DIP_RSI": {"symbol": "QQQ", "qty": "six"}}, "qty 'six'"),
        ({"DIP_RSI": 6}, "not a mapping"),
    ]
    for positions, words in cases:
        qqq = {"legs": {"DIP_RSI": _held_lot()}}
        ok, reasons, held = box_deploy._book_check(qqq, {"broker_sent_positions": positions}, DIP_HOLD)
        assert ok is False and held == [], positions
        r = [x for x in reasons if x.startswith("held lot DIP_RSI long 6 does not match Webull")]
        assert r and words in r[0] and "want qty 6" in r[0], (positions, reasons)
        # never the position's account field
        assert not any("ACCT" in x for x in reasons)


def test_a_held_short_lot_matches_a_negative_broker_qty():
    qqq = {"legs": {"ENGUQ": _held_lot(10, side="short")}}
    ok, _reasons, held = box_deploy._book_check(qqq, {"broker_sent_positions": {"ENGUQ": _pos(-10)}},
                                                DIP_HOLD)
    assert ok is True and held[0]["side"] == "short" and held[0]["shares"] == 10
    ok, _reasons, _held = box_deploy._book_check(qqq, {"broker_sent_positions": {"ENGUQ": _pos(10)}},
                                                 DIP_HOLD)
    assert ok is False


def test_a_held_lot_with_unreadable_side_or_shares_refuses():
    for over in ({"side": "flat"}, {"side": None}, {"shares_remaining": None},
                 {"shares_remaining": "x"}, {"shares_remaining": 0}, {"shares_remaining": -6},
                 {"shares_remaining": 6.5}, {"shares_remaining": float("nan")}):
        qqq = {"legs": {"DIP_RSI": _held_lot(**over)}}
        ok, reasons, held = box_deploy._book_check(qqq, {"broker_sent_positions": {"DIP_RSI": _pos(6)}},
                                                   DIP_HOLD)
        assert ok is False and held == [], over
        assert any("unreadable side/shares" in r for r in reasons), (over, reasons)
    # "shares" is read when shares_remaining is absent
    lot = _held_lot()
    lot["shares"] = lot.pop("shares_remaining")
    assert box_deploy._book_check({"legs": {"DIP_RSI": lot}},
                                  {"broker_sent_positions": {"DIP_RSI": _pos(6)}}, DIP_HOLD)[0] is True


def test_held_lots_with_unreadable_or_malformed_state_refuse():
    qqq, webull = _dip_book("DIP_RSI")
    assert box_deploy._book_check(None, webull, DIP_HOLD) == (
        False, ["qqq_exec state.json unreadable"], [])
    assert box_deploy._book_check(qqq, None, DIP_HOLD) == (
        False, ["webull_orders state.json unreadable"], [])
    ok, reasons, held = box_deploy._book_check(qqq, {"broker_sent_positions": "junk"}, DIP_HOLD)
    assert ok is False and held == []
    assert any("cannot be checked against Webull" in r for r in reasons)
    ok, reasons, _held = box_deploy._book_check({"legs": {"DIP_RSI": "junk"}}, webull, DIP_HOLD)
    assert ok is False and any("legs['DIP_RSI'] is not a mapping" in r for r in reasons)


def test_hold_legs_from_the_box_config():
    from tools import webull_freshness as wf
    assert box_deploy._hold_legs_from_config(None) == ()            # unreadable: blocks only
    assert box_deploy._hold_legs_from_config("junk") == ()
    assert box_deploy._hold_legs_from_config({}) == wf.HOLD_OVERNIGHT_LEGS
    assert set(DIP_HOLD) <= set(box_deploy._hold_legs_from_config({"session": {}}))
    assert box_deploy._hold_legs_from_config(
        {"session": {"hold_overnight_legs": ["DIP_RSI"]}}) == ("DIP_RSI",)
    assert box_deploy._hold_legs_from_config({"session": {"hold_overnight_legs": []}}) == ()
    assert box_deploy._hold_legs_from_config({"signal_source": "ninjatrader"}) == ()


class _Stop(Exception):
    pass


def _run_main_to_the_git_step(monkeypatch, qqq, webull, exec_cfg):
    """main() up to its first box-git call with every ssh read faked (no network): returns
    what it printed before the git step (which raises _Stop) or its return code."""
    files = {f"{box_deploy.REMOTE_HOME}/qqq_exec/state.json": qqq,
             f"{box_deploy.REMOTE_HOME}/webull_orders/state.json": webull,
             f"{box_deploy.REMOTE_HOME}/qqq_exec/config.json": exec_cfg}
    monkeypatch.setattr(box_deploy, "_read_remote_json", lambda path: files.get(path))
    monkeypatch.setattr(box_deploy, "_in_protected_window", lambda now: False)

    def stop():
        raise _Stop()
    monkeypatch.setattr(box_deploy, "_remote_head_sha", stop)
    return box_deploy.main(["--commit", "abc1234", "--dry-run"])


def test_main_prints_the_accepted_held_lots_plainly(monkeypatch, capsys):
    qqq, webull = _dip_book("DIP_RSI", "DIP_PB")
    try:
        _run_main_to_the_git_step(monkeypatch, qqq, webull, {"session": {}})
    except _Stop:
        pass
    out = capsys.readouterr().out
    assert ("book is flat on the box except 2 lot(s) held overnight on purpose, each matching "
            "Webull -- ACCEPTED (they stay open through the restart):") in out
    assert "  - DIP_PB long 6 (held since 2026-10-13, Webull holds 6 for it)" in out
    assert "  - DIP_RSI long 6 (held since 2026-10-13, Webull holds 6 for it)" in out
    assert "ACCT" not in out


def test_main_refuses_a_mismatched_held_lot_and_names_the_good_ones(monkeypatch, capsys):
    qqq, webull = _dip_book("DIP_RSI", "DIP_PB")
    webull["broker_sent_positions"]["DIP_PB"] = _pos(3)
    rc = _run_main_to_the_git_step(monkeypatch, qqq, webull, None)
    out = capsys.readouterr().out
    assert rc == 1
    assert "REFUSED: the book is not flat on the box:" in out
    assert "held lot DIP_PB long 6 does not match Webull" in out
    assert "(held overnight and matching Webull, fine on its own: DIP_RSI long 6" in out
    assert "could not read qqq_exec/config.json" in out          # hold blocks alone counted
    assert "ACCT" not in out


# ── strategy-chain parsing (pure text, no ssh) ────────────────────────────────────────
def test_book_pathspecs_cover_the_dip_runner_and_the_broker_id_helper():
    """FIXER 10-10: api/dip_live.py decides the live DIP leg's orders and api/trade_id.py builds
    every Webull client_order_id (broker_signal_base) -- a deploy that changes either must list
    it under the book's code paths."""
    got = box_deploy._book_pathspecs(lambda relpath: None)
    for path in ("api/dip_live.py", "api/trade_id.py", "api/qqq_exec.py", "api/cloud_signal.py"):
        assert path in got, path


def test_parse_crown_strategy_files_from_cloud_signal_source():
    src = '''
CROWN_LEGS = {
    "ORB_R6": {"strategy": "ORB_3_6_R6.py", "timeframe": "5m"},
    "NOISE_382": {"strategy": "NOISE_1_8_CT304.py", "timeframe": "5m"},
    "ENGUQ_335": {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "timeframe": "1m"},
}
'''
    got = box_deploy.parse_crown_strategy_files(src)
    assert got == ["ENGUQ_1M_ETH_R2_1_0.py", "NOISE_1_8_CT304.py", "ORB_3_6_R6.py"]


def test_strategy_chain_follows_augur_parent():
    files = {
        "ORB_3_6_R6.py": '_AUGUR_PARENT = "ORB_3_6.py"\n',
        "ORB_3_6.py": "# base strategy, no parent\n",
    }
    got = box_deploy.strategy_chain("ORB_3_6_R6.py", lambda n: files.get(n))
    assert got == ["ORB_3_6.py", "ORB_3_6_R6.py"]


def test_strategy_chain_stops_when_a_parent_file_is_missing():
    files = {"ORB_3_6_R6.py": '_AUGUR_PARENT = "GONE.py"\n'}
    got = box_deploy.strategy_chain("ORB_3_6_R6.py", lambda n: files.get(n))
    assert got == ["ORB_3_6_R6.py"]


def test_strategy_chain_guards_against_a_cycle():
    files = {
        "A.py": '_AUGUR_PARENT = "B.py"\n',
        "B.py": '_AUGUR_PARENT = "A.py"\n',
    }
    got = box_deploy.strategy_chain("A.py", lambda n: files.get(n))
    assert got == ["A.py", "B.py"]


def test_strategy_chain_with_no_parent_returns_just_itself():
    got = box_deploy.strategy_chain("ORB_3_6.py", lambda n: "# no parent here\n")
    assert got == ["ORB_3_6.py"]


# ── _read_remote_json (ssh mocked out -- no real subprocess anywhere here) ─────────────
class _FakeResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def test_read_remote_json_returns_none_on_ssh_failure(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=1, stdout=""))
    assert box_deploy._read_remote_json("/home/ubuntu/edgelog/qqq_exec/state.json") is None


def test_read_remote_json_returns_none_on_empty_output(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout=""))
    assert box_deploy._read_remote_json("/some/missing/file.json") is None


def test_read_remote_json_returns_none_on_bad_json(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout="{not valid json"))
    assert box_deploy._read_remote_json("/some/file.json") is None


def test_read_remote_json_returns_none_when_top_level_is_not_a_dict(monkeypatch):
    # A state.json is always an object -- a list or scalar means something is very
    # wrong, and must refuse exactly like an unreadable file, not be treated as flat.
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout="[1, 2, 3]"))
    assert box_deploy._read_remote_json("/some/file.json") is None


def test_read_remote_json_returns_the_parsed_dict_on_success(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout='{"legs": {}}'))
    assert box_deploy._read_remote_json("/some/file.json") == {"legs": {}}


# ── _n_restarts / _restarts_stable (NRestarts crash-loop guard) ────────────────────────
def test_n_restarts_queries_each_service_in_its_own_ssh_call(monkeypatch):
    # Regression for the real bug: a single combined
    # `systemctl show A B -p NRestarts --value` call printed a blank line between the
    # two units' values on the box ('0', '', '0'), so zipping by position always read
    # edgelog-cloud-signal's count off the blank line. Querying one unit per call
    # sidesteps that shape entirely -- assert exactly one ssh call per service, each
    # naming only that service.
    calls = []

    def fake_ssh(cmd, **kw):
        calls.append(cmd)
        # Return a distinct, correct value per unit -- proves no cross-unit mixup.
        if "edgelog-qqq-exec" in cmd:
            return _FakeResult(returncode=0, stdout="3\n")
        if "edgelog-cloud-signal" in cmd:
            return _FakeResult(returncode=0, stdout="7\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    out = box_deploy._n_restarts()
    assert out == {"edgelog-qqq-exec": 3, "edgelog-cloud-signal": 7}
    assert len(calls) == len(box_deploy.SERVICES)


def test_n_restarts_returns_none_for_blank_output_rather_than_crashing(monkeypatch):
    # The exact real-world shape that broke the old parser: this unit's own call
    # comes back blank.
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout="\n"))
    out = box_deploy._n_restarts()
    assert out == {name: None for name in box_deploy.SERVICES}


def test_restarts_stable_true_when_all_unchanged_and_known():
    before = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 5}
    after = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 5}
    assert box_deploy._restarts_stable(before, after) is True


def test_restarts_stable_false_when_a_count_increased():
    before = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 5}
    after = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": 6}
    assert box_deploy._restarts_stable(before, after) is False


def test_restarts_stable_fails_closed_on_a_none_value():
    # This is the exact inversion the go-live review flagged: None == None used to
    # read as "stable" for the service whose value couldn't be parsed. A None on
    # either side must now read as NOT stable.
    before = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": None}
    after = {"edgelog-qqq-exec": 2, "edgelog-cloud-signal": None}
    assert box_deploy._restarts_stable(before, after) is False


def test_restarts_stable_fails_closed_on_a_missing_service_key():
    before = {"edgelog-qqq-exec": 2}
    after = {"edgelog-qqq-exec": 2}
    assert box_deploy._restarts_stable(before, after) is False


# ── _verify_boot: polls the whole window, stops early only on a bad signal ────────────
class _FakeClock:
    """A controllable fake for time.time()/time.sleep() so _verify_boot's tests run
    instantly and can assert exactly how many polls happened, instead of a real
    60-second sleep loop."""
    def __init__(self):
        self.now = 0.0
        self.sleeps = 0

    def time(self):
        return self.now

    def sleep(self, secs):
        self.sleeps += 1
        self.now += secs


def test_verify_boot_polls_the_full_window_even_after_good_lines_appear(monkeypatch):
    # The pre-fix bug: the loop broke the instant it saw SERVING + (lease OR
    # reconcile_ok), so a crash later in the window was never observed. It must now
    # keep polling for the whole timeout_sec, seeing good lines on the very first
    # poll, and MUST NOT stop early because of them.
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    calls = {"n": 0}

    def fake_ssh(cmd, **kw):
        calls["n"] += 1
        return _FakeResult(returncode=0, stdout="SERVING\nlease claimed\n"
                                                  "broker reconcile OK at boot\n")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["serving"] and seen["lease"] and seen["reconcile_ok"]
    assert not seen["traceback"] and seen["reconcile_fail"] is None
    # 60s / 3s poll interval = 20 polls -- it must have used (approximately) the
    # whole window, not returned after the first poll.
    assert calls["n"] >= 19


def test_verify_boot_stops_early_on_traceback(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    calls = {"n": 0}

    def fake_ssh(cmd, **kw):
        calls["n"] += 1
        return _FakeResult(returncode=0, stdout="SERVING\nTraceback (most recent call last)\n")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["traceback"] is True
    assert calls["n"] == 1  # stopped on the very first poll, not the whole window


def test_verify_boot_stops_early_on_reconcile_mismatch(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    calls = {"n": 0}

    def fake_ssh(cmd, **kw):
        calls["n"] += 1
        return _FakeResult(returncode=0,
                           stdout="SERVING\nlease claimed\n"
                                  "BROKER RECONCILE MISMATCH at boot -- halted\n")

    monkeypatch.setattr(box_deploy, "_ssh", fake_ssh)
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["reconcile_fail"] == "BROKER RECONCILE MISMATCH at boot"
    assert calls["n"] == 1


def test_verify_boot_never_saw_reconcile_ok_when_it_never_appeared(monkeypatch):
    # Simulates OFF mode: SERVING and lease claimed show up, but no reconcile line
    # ever appears (the adapter never logs one -- see _reconcile_broker_at_boot).
    # _verify_boot itself makes no OFF-mode decision -- it just reports what it saw.
    clock = _FakeClock()
    monkeypatch.setattr(box_deploy.time, "time", clock.time)
    monkeypatch.setattr(box_deploy.time, "sleep", clock.sleep)
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout="SERVING\nlease claimed\n"))
    seen = box_deploy._verify_boot("/fake/log", 0, timeout_sec=60, poll_sec=3)
    assert seen["serving"] and seen["lease"]
    assert seen["reconcile_ok"] is False
    assert seen["reconcile_fail"] is None
    assert not seen["traceback"]


# ── _remote_resolve_commit / _remote_git_clean / _remote_broker_mode ───────────────────
def test_remote_resolve_commit_returns_the_full_sha(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout="abc123def456\n"))
    assert box_deploy._remote_resolve_commit("main") == "abc123def456"


def test_remote_resolve_commit_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=128, stdout=""))
    assert box_deploy._remote_resolve_commit("not-a-real-ref") is None


def test_remote_git_clean_true_on_empty_status(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout=""))
    assert box_deploy._remote_git_clean() is True


def test_remote_git_clean_false_when_status_reports_changes(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout=" M api/qqq_exec.py\n"))
    assert box_deploy._remote_git_clean() is False


def test_remote_git_clean_false_when_ssh_itself_fails(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=255, stdout=""))
    assert box_deploy._remote_git_clean() is False


def test_remote_broker_mode_defaults_to_off_when_config_missing(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh", lambda *a, **k: _FakeResult(returncode=0, stdout=""))
    assert box_deploy._remote_broker_mode() == "OFF"


def test_remote_broker_mode_reads_paper(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout='{"mode": "PAPER"}'))
    assert box_deploy._remote_broker_mode() == "PAPER"


def test_remote_broker_mode_defaults_to_off_on_malformed_config(monkeypatch):
    monkeypatch.setattr(box_deploy, "_ssh",
                        lambda *a, **k: _FakeResult(returncode=0, stdout="[1, 2]"))
    assert box_deploy._remote_broker_mode() == "OFF"


# ── _UNIT_OR_DEPS_RE (deploy/cloud unit-template/deps-change warning) ──────────────────
def test_unit_or_deps_pattern_matches_only_the_expected_files():
    candidates = [
        "deploy/cloud/edgelog-qqq-exec.service",
        "deploy/cloud/edgelog-keel-state.timer",
        "deploy/cloud/edgelog-keel-state.path",
        "deploy/cloud/requirements-cloud.txt",
        "deploy/cloud/edgelog.logrotate",
        "deploy/cloud/README.md",
        "deploy/cloud/install.sh",
        "api/qqq_exec.py",
        "requirements-cloud.txt",  # not under deploy/cloud/ -- must not match
    ]
    hits = [n for n in candidates if box_deploy._UNIT_OR_DEPS_RE.match(n)]
    assert hits == [
        "deploy/cloud/edgelog-qqq-exec.service",
        "deploy/cloud/edgelog-keel-state.timer",
        "deploy/cloud/edgelog-keel-state.path",
        "deploy/cloud/requirements-cloud.txt",
        "deploy/cloud/edgelog.logrotate",
    ]
