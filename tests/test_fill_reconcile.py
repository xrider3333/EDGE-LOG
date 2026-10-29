"""DAILY FILL RECONCILE (B1-A): tools/reconcile_core (pure pairing) and the fill_reconcile check
in tools/webull_freshness.py (the box monitor). Real row shapes of qqq_exec/broker_orders.csv
and qqq_exec/trades.csv; the fixture home from tests/test_webull_freshness.py. No push leaves the
process, no Webull call, no live file."""
import csv
import datetime as dt
import importlib.util
import json
import os

import pytest

from api import ntfy_push
from tools import reconcile_core as rc

_spec = importlib.util.spec_from_file_location(
    "webull_freshness_helpers_fr",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_webull_freshness.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
wf = T.wf

DAY = dt.date(2026, 10, 27)                       # Tuesday, a session day
AFTER = T.et(2026, 10, 27, 16, 15)

BROKER_COLS = ["ts_et", "leg", "intent", "side", "shares", "signal_id", "client_order_id",
               "mode", "ok", "sent", "shadow_px", "broker_fill_px", "slippage", "reason",
               "duplicate", "host_id", "outcome"]
TRADE_COLS = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px", "pnl",
              "nq_pnl_points", "exit_reason", "trade_id"]


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _s(day, hms):
    return f"{day.isoformat()} {hms}"


def trade(leg, ent, ext, side, shares, epx, xpx, day=DAY, entry_day=None):
    sign = 1 if side == "long" else -1
    return {"leg": leg, "entry_ts": _s(entry_day or day, ent), "exit_ts": _s(day, ext),
            "side": side, "shares": shares, "entry_px": epx, "exit_px": xpx,
            "pnl": round((xpx - epx) * sign * shares, 2), "nq_pnl_points": "",
            "exit_reason": "signal", "trade_id": f"T{leg}{ent}"}


def order(ts, leg, intent, side, shares, fill, shadow=None, day=DAY, ok=True, mode="PAPER",
          duplicate=False, coid="12345678901234"):
    return {"ts_et": _s(day, ts), "leg": leg, "intent": intent, "side": side, "shares": shares,
            "signal_id": coid, "client_order_id": coid, "mode": mode, "ok": ok, "sent": True,
            "shadow_px": shadow if shadow is not None else fill,
            "broker_fill_px": "" if fill is None else fill, "slippage": "", "reason": "",
            "duplicate": duplicate, "host_id": "box", "outcome": "OK" if ok else "REFUSED"}


def clean_day():
    """The 10-27 shape: NOISE two round trips + ORB, the EOD closes at 15:59."""
    trades = [trade("NOISE", "10:05:02", "11:20:03", "long", 5, 600.00, 601.00),
              trade("NOISE", "13:00:01", "15:59:01", "short", 5, 602.00, 601.50),
              trade("ORB", "09:45:01", "15:59:02", "long", 5, 599.00, 601.20)]
    orders = [order("09:45:03", "ORB", "OPEN", "BUY", 5, 599.02),
              order("10:05:04", "NOISE", "OPEN", "BUY", 5, 600.01),
              order("11:20:05", "NOISE", "CLOSE", "SELL", 5, 600.98),
              order("13:00:03", "NOISE", "OPEN", "SHORT", 5, 601.99),
              order("15:59:03", "NOISE", "CLOSE", "BUY", 5, 601.52),
              order("15:59:04", "ORB", "CLOSE", "SELL", 5, 601.18)]
    return trades, orders


def _write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def home(tmp_path, trades, orders, now=AFTER):
    h = T.Home(tmp_path, now)
    _write_csv(h.paths["exec_trades"], TRADE_COLS, trades)
    _write_csv(h.paths["broker_orders"], BROKER_COLS, orders)
    return h


def core(trades, orders, lots=(), day=DAY, log_start="first"):
    snap = {"fill_trades": [{k: str(v) for k, v in t.items()} for t in trades],
            "fill_orders": [{k: str(v) for k, v in o.items()} for o in orders],
            "exec_state": {"legs": {l["leg"]: l for l in lots}}}
    tr, od, ol, start = wf.webull_fill_inputs(snap)
    return rc.reconcile(day, tr, od, ol, log_start=start if log_start == "first" else log_start)


def fr_pushes(h):
    return [p for p in h.pushes if "Webull vs book" in json.dumps(p)
            or "order log" in json.dumps(p)]


# -- core -------------------------------------------------------------------------------------
def test_core_clean_day_matches_everything_with_slippage_only():
    rep = core(*clean_day())
    assert rep["status"] == "clean" and len(rep["matched"]) == 3
    assert rep["no_fill"] == [] and rep["orphan_fills"] == [] and rep["missing_usd"] == 0
    assert rep["book_usd"] == pytest.approx(5.0 + 2.5 + 11.0)
    assert rep["broker_usd"] == pytest.approx((600.98 - 600.01) * 5 + (601.99 - 601.52) * 5
                                              + (601.18 - 599.02) * 5, abs=0.02)
    assert rep["slippage_usd"] == pytest.approx(rep["broker_usd"] - rep["book_usd"], abs=0.01)
    assert rep["slippage_usd"] < 0


def test_core_fill_with_no_trade_is_missing():
    trades, orders = clean_day()
    orders.append(order("14:10:00", "ORB", "OPEN", "BUY", 5, 600.50))
    rep = core(trades, orders)
    assert rep["status"] == "missing" and len(rep["orphan_fills"]) == 1
    assert rep["missing_usd"] == pytest.approx(5 * 600.50)


def test_core_trade_with_no_fill_is_missing():
    trades, orders = clean_day()
    orders = [o for o in orders if not (o["leg"] == "NOISE" and o["ts_et"].endswith("11:20:05"))]
    rep = core(trades, orders)
    assert rep["status"] == "missing"
    (nf,) = rep["no_fill"]
    assert nf["leg"] == "NOISE" and nf["which"] == "close" and nf["usd"] == pytest.approx(5 * 601.0)


def test_core_dip_close_whose_open_was_three_days_earlier():
    open_day = dt.date(2026, 10, 22)
    trades = [trade("DIP_RSI", "15:55:01", "10:00:02", "long", 3, 590.0, 600.0,
                    entry_day=open_day)]
    orders = [order("15:55:03", "DIP_RSI", "OPEN", "BUY", 3, 590.05, day=open_day),
              order("10:00:04", "DIP_RSI", "CLOSE", "SELL", 3, 599.90)]
    rep = core(trades, orders)
    assert rep["status"] == "clean", rep
    assert rep["matched"][0]["broker_pnl"] == pytest.approx((599.90 - 590.05) * 3, abs=0.01)


def test_core_open_fill_of_a_lot_still_held_is_not_an_orphan():
    trades, orders = clean_day()
    orders.append(order("15:56:00", "DIP_PB", "OPEN", "BUY", 3, 600.0))
    lots = [{"leg": "DIP_PB", "side": "long", "shares_total": 3,
             "entry_ts": _s(DAY, "15:55:58")}]
    assert core(trades, orders, lots)["status"] == "clean"


def test_core_duplicate_and_shadow_rows_are_ignored():
    trades, orders = clean_day()
    orders.append(order("10:05:05", "NOISE", "OPEN", "BUY", 5, 600.01, duplicate=True))
    orders.append(order("12:00:00", "ORB", "OPEN", "BUY", 5, 600.0, mode="SHADOW"))
    assert core(trades, orders)["status"] == "clean"


def test_core_refused_order_is_reported_and_its_trade_missing():
    trades, orders = clean_day()
    orders = [o for o in orders if not o["ts_et"].endswith("09:45:03")]
    orders.append(order("09:45:03", "ORB", "OPEN", "BUY", 5, None, ok=False))
    rep = core(trades, orders)
    assert rep["status"] == "missing" and len(rep["bad_orders"]) == 1
    assert rep["no_fill"][0]["which"] == "open"


def test_core_trimmed_log_cannot_check():
    trades, orders = clean_day()
    orders = orders[2:]                                  # the log starts after the day's opens
    rep = core(trades, orders)
    assert rep["status"] == "cant_check" and rep["reason"] == "order log trimmed"


def test_core_partial_close_shares_one_open():
    trades = [trade("NOISE", "10:05:02", "10:30:02", "long", 2, 600.0, 601.0),
              trade("NOISE", "10:05:02", "11:00:02", "long", 3, 600.0, 602.0)]
    orders = [order("10:05:04", "NOISE", "OPEN", "BUY", 5, 600.0),
              order("10:30:03", "NOISE", "CLOSE", "SELL", 2, 601.0),
              order("11:00:03", "NOISE", "CLOSE", "SELL", 3, 602.0)]
    rep = core(trades, orders)
    assert rep["status"] == "clean" and rep["slippage_usd"] == 0


# -- review fixes ---------------------------------------------------------------------------
def test_fix_webull_filled_more_shares_than_the_book_is_flagged():
    trades = [trade("NOISE", "10:00:00", "11:00:00", "long", 5, 500.0, 501.0)]
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 10, 500.0),
              order("11:00:02", "NOISE", "CLOSE", "SELL", 10, 501.0)]
    rep = core(trades, orders)
    assert rep["status"] == "missing"
    assert rep["matched"][0]["broker_pnl"] == pytest.approx(5.0)
    assert sorted((x["intent"], x["shares"]) for x in rep["orphan_fills"]) ==         [("CLOSE", 5.0), ("OPEN", 5.0)]


def test_fix_resting_partial_plus_market_close_row_is_capped_at_the_lot():
    trades = [trade("ORB", "10:00:00", "11:00:00", "long", 5, 500.0, 500.0)]
    orders = [order("10:00:02", "ORB", "OPEN", "BUY", 5, 500.0),
              order("11:00:01", "ORB", "CLOSE", "SELL", 3, 499.0),
              order("11:00:03", "ORB", "CLOSE", "SELL", 5, 501.0)]
    rep = core(trades, orders)
    assert rep["status"] == "clean", rep
    assert rep["matched"][0]["broker_pnl"] == pytest.approx(-1.0)


def test_fix_resting_fill_booked_late_still_pairs():
    trades = [trade("ORB", "10:00:00", "11:00:00", "long", 5, 500.0, 499.0)]
    orders = [order("10:00:02", "ORB", "OPEN", "BUY", 5, 500.0),
              order("11:03:40", "ORB", "CLOSE", "SELL", 5, 499.0)]
    assert core(trades, orders)["status"] == "clean"


def test_fix_late_open_resend_pairs_not_missing():
    trades = [trade("NOISE", "10:00:00", "11:00:00", "long", 5, 500.0, 501.0)]
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 5, None, ok=False),
              order("10:02:00", "NOISE", "OPEN", "BUY", 5, 500.2),
              order("11:00:02", "NOISE", "CLOSE", "SELL", 5, 501.0)]
    rep = core(trades, orders)
    assert rep["no_fill"] == [] and rep["orphan_fills"] == [] and len(rep["bad_orders"]) == 1
    assert rep["matched"][0]["broker_pnl"] == pytest.approx(4.0)


def test_fix_pairs_by_signal_id_at_any_time():
    tid = "NOISE_304-20261027T140000Z-L"
    from api import trade_id as tmod
    base_o, base_c = tmod.broker_signal_base(tid, "OPEN"), tmod.broker_signal_base(tid, "CLOSE")
    t = trade("NOISE", "10:00:00", "15:59:00", "long", 10, 500.0, 501.0)
    t["trade_id"] = tid
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 10, None, ok=False, coid=base_o),
              order("10:40:00", "NOISE", "OPEN", "BUY", 10, 500.0, coid=base_o + "R2"),
              order("15:59:45", "NOISE", "CLOSE", "SELL", 10, 501.0, coid=base_c)]
    rep = core([t], orders)
    assert rep["status"] == "clean", rep


def test_fix_late_close_retry_and_after_hours_sell_pair():
    trades = [trade("NOISE", "10:00:00", "15:59:00", "long", 10, 500.0, 501.0)]
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 10, 500.0),
              order("15:59:45", "NOISE", "CLOSE", "SELL", 10, 501.0)]
    assert core(trades, orders)["status"] == "clean"
    orders[1] = order("17:30:00", "NOISE", "CLOSE", "SELL", 10, 500.5)
    assert core(trades, orders)["status"] == "clean"


def test_fix_late_close_pass_does_not_steal_the_next_trades_close():
    trades = [trade("NOISE", "10:00:00", "11:00:00", "long", 5, 500.0, 501.0),
              trade("NOISE", "12:00:00", "13:00:00", "long", 5, 500.0, 501.0)]
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 5, 500.0),
              order("12:00:02", "NOISE", "OPEN", "BUY", 5, 500.0),
              order("13:00:02", "NOISE", "CLOSE", "SELL", 5, 501.0)]
    rep = core(trades, orders)
    assert [x["ts"][11:16] for x in rep["no_fill"]] == ["11:00"]


def test_fix_sent_row_with_no_fill_price_pairs_unpriced():
    trades = [trade("NOISE", "10:00:00", "15:59:00", "long", 10, 500.0, 501.0)]
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 10, 500.0),
              order("15:59:02", "NOISE", "CLOSE", "SELL", 10, None)]
    rep = core(trades, orders)
    assert rep["status"] == "clean" and rep["unpriced"] == 1 and rep["bad_orders"] == []
    assert rep["matched"][0]["broker_pnl"] is None and rep["broker_usd"] == 0


def test_fix_missing_usd_is_the_position_size_not_the_pnl():
    trades = [trade("NOISE", "10:00:00", "11:00:00", "long", 5, 500.0, 500.08)]   # pnl $0.40
    rep = core(trades, [order("09:00:00", "ORB", "OPEN", "BUY", 1, None, ok=False)])
    assert rep["no_fill"][0]["which"] == "both"
    assert rep["missing_usd"] == pytest.approx(5 * 500.08)
    orders = [order("10:00:02", "NOISE", "OPEN", "BUY", 5, 500.0),
              order("11:00:02", "NOISE", "CLOSE", "SELL", 2, 500.08)]
    assert core(trades, orders)["missing_usd"] == pytest.approx(3 * 500.08)


def test_fix_trimmed_log_with_only_a_held_lot_opening_that_day():
    lots = [{"leg": "DIP_PB", "side": "long", "shares_total": 3,
             "entry_ts": _s(DAY, "10:00:00")}]
    orders = [order("14:00:00", "NOISE", "OPEN", "BUY", 5, None, ok=False)]
    assert core([], orders, lots)["status"] == "cant_check"


def test_fix_after_hours_sell_working_holds_the_check(tmp_path):
    trades, orders = clean_day()
    orders = orders[:-1]
    h = home(tmp_path, trades, orders)
    st = json.load(open(h.paths["exec_state"], encoding="utf-8"))         if os.path.exists(h.paths["exec_state"]) else {}
    st["after_hours_flatten"] = {DAY.isoformat(): {"ORB": {"status": "working"}}}
    snap = {"fill_trades": trades, "fill_orders": orders, "exec_state": st,
            "broker_mode": "PAPER"}
    assert wf.check_fill_reconcile(snap, AFTER, {}) is None
    st["after_hours_flatten"][DAY.isoformat()]["ORB"]["status"] = "filled"
    assert wf.check_fill_reconcile(snap, AFTER, {})[0]["ok"] is False


def test_fix_stale_open_episode_from_yesterday_does_not_swallow_today():
    trades, orders = clean_day()
    orders = orders[:-1]
    snap = {"fill_trades": trades, "fill_orders": orders, "exec_state": {},
            "broker_mode": "PAPER"}
    mstate = {"alerts": {wf.FILL_REC_KEY: {"key": wf.FILL_REC_KEY, "open": True}},
              "fill_reconcile": {"pushed_day": "2026-10-26"}}
    (v,) = wf.check_fill_reconcile(snap, AFTER, mstate)
    assert v["ok"] is False and wf.FILL_REC_KEY not in mstate["alerts"]
    assert mstate["fill_reconcile"]["pushed_day"] == DAY.isoformat()


# -- the box check ----------------------------------------------------------------------------
def test_clean_day_no_push_and_the_line_is_kept(tmp_path):
    h = home(tmp_path, *clean_day())
    out = h.run()
    assert "fill_reconcile" in out["status"]["groups_checked"]
    assert "fill_reconcile" not in T.failing(out) and fr_pushes(h) == []
    line = out["status"]["fill_reconcile"][DAY.isoformat()]
    assert line["status"] == "clean" and line["matched"] == 3 and line["slippage_usd"] < 0
    st = json.load(open(h.paths["monitor_state"], encoding="utf-8"))
    assert st["fill_reconcile"]["days"][DAY.isoformat()]["book_usd"] == pytest.approx(18.5)


def test_missing_fill_pushes_one_plain_high_note_per_day(tmp_path):
    trades, orders = clean_day()
    orders = [o for o in orders if not o["ts_et"].endswith("11:20:05")]
    h = home(tmp_path, trades, orders)
    out = h.run()
    assert "fill_reconcile" in T.failing(out)
    (p,) = fr_pushes(h)
    title, msg, prio = p["title"], p["message"], p["priority"]
    assert prio == "high"
    assert "Webull vs book: missing $3,005" in msg and "NOISE sell at 11:20" in msg
    assert "PAPER-WB" in msg
    assert ntfy_push.lint({"title": title, "message": msg, "priority": prio}) == []
    assert "12345678" not in msg
    for m in (2, 10, 60, 200):                                  # repeated runs: no new note
        h.advance(AFTER + dt.timedelta(minutes=m))
        h.run()
    assert len(fr_pushes(h)) == 1
    # a late fill clears it: still no second ("OK") note
    _write_csv(h.paths["broker_orders"], BROKER_COLS, clean_day()[1])
    h.advance(AFTER + dt.timedelta(minutes=300))
    h.run()
    assert len(fr_pushes(h)) == 1
    assert not any("back to normal" in json.dumps(p).lower() and "Webull" in json.dumps(p)
                   for p in h.pushes)


def test_fill_with_no_trade_pushes(tmp_path):
    trades, orders = clean_day()
    orders.append(order("14:10:00", "ORB", "OPEN", "BUY", 5, 600.50))
    h = home(tmp_path, trades, orders)
    h.run()
    (p,) = fr_pushes(h)
    assert "Webull filled an ORB buy at 14:10 the book never logged" in p["message"]
    assert "missing $3,002" in p["message"] and p["priority"] == "high"


def test_trimmed_log_says_cant_check_not_missing(tmp_path):
    trades, orders = clean_day()
    h = home(tmp_path, trades, orders[2:])
    out = h.run()
    (p,) = fr_pushes(h)
    assert "order log was trimmed" in p["message"] and "missing $" not in p["message"]
    assert out["status"]["fill_reconcile"][DAY.isoformat()]["status"] == "cant_check"


def test_duplicate_row_is_ignored_in_the_check(tmp_path):
    trades, orders = clean_day()
    orders.append(order("10:05:05", "NOISE", "OPEN", "BUY", 5, 600.01, duplicate=True))
    h = home(tmp_path, trades, orders)
    h.run()
    assert fr_pushes(h) == []


def test_non_session_day_is_not_checked(tmp_path):
    sat = T.et(2026, 10, 31, 16, 30)
    h = home(tmp_path, *clean_day(), now=sat)
    out = h.run()
    assert "fill_reconcile" not in out["status"]["groups_checked"]


def test_before_1610_is_not_checked(tmp_path):
    trades, orders = clean_day()
    orders = orders[:-1]                                  # would be missing
    h = home(tmp_path, trades, orders, now=T.et(2026, 10, 27, 16, 5))
    out = h.run()
    assert "fill_reconcile" not in out["status"]["groups_checked"] and fr_pushes(h) == []


def test_next_day_episode_expires_silently_and_a_new_problem_pushes_again(tmp_path):
    trades, orders = clean_day()
    orders = orders[:-1]
    h = home(tmp_path, trades, orders)
    h.run()
    assert len(fr_pushes(h)) == 1
    wed_am = T.et(2026, 10, 28, 9, 0)
    h.advance(wed_am)
    h.run()
    assert len(fr_pushes(h)) == 1                         # expired, no push
    wed = dt.date(2026, 10, 28)
    t2 = [trade("ORB", "09:45:01", "15:59:02", "long", 5, 599.0, 601.0, day=wed)]
    _write_csv(h.paths["exec_trades"], TRADE_COLS, trades + t2)
    _write_csv(h.paths["broker_orders"], BROKER_COLS, orders)   # no Wed fills
    h.advance(T.et(2026, 10, 28, 16, 12))
    h.exec_state()                                        # Wed's close ran (EOD stays quiet)
    out = h.run()
    assert "fill_reconcile" in T.failing(out)
    assert len(fr_pushes(h)) == 2 and "ORB trade closed at 15:59" in fr_pushes(h)[-1]["message"]


def test_no_files_or_off_mode_is_not_checked(tmp_path):
    h = T.Home(tmp_path, AFTER)
    assert "fill_reconcile" not in h.run()["status"]["groups_checked"]
    h2 = T.Home(tmp_path / "off", AFTER, mode="OFF")
    _write_csv(h2.paths["exec_trades"], TRADE_COLS, clean_day()[0])
    assert "fill_reconcile" not in h2.run()["status"]["groups_checked"]


def test_mask_digits():
    assert wf.mask_digits("order 1234567890123 acct 12345678 px 601.25") == \
        "order **** acct **** px 601.25"


def test_open_of_a_lot_closed_on_a_later_day_is_not_a_stray_fill():
    # real 10-23 shape: a DIP buy at 09:35, sold 10-27; on 10-23 the lot is neither closing nor held
    ent, ext = dt.datetime(2026, 10, 23, 9, 35, 13), dt.datetime(2026, 10, 27, 9, 35, 9)
    trades = [{"leg": "DIP_STREAK", "side": "long", "shares": 6, "entry_ts": ent, "exit_ts": ext,
               "entry_px": 702.11, "exit_px": 715.15, "pnl": 78.24}]
    orders = [{"ts": ent, "leg": "DIP_STREAK", "intent": "OPEN", "side": "BUY", "shares": 6,
               "ok": True, "sent": True, "fill_px": 702.2},
              {"ts": ext, "leg": "DIP_STREAK", "intent": "CLOSE", "side": "SELL", "shares": 6,
               "ok": True, "sent": True, "fill_px": 715.3}]
    rep = rc.reconcile(dt.date(2026, 10, 23), trades, orders, [], log_start=ent)
    assert rep["orphan_fills"] == [] and rep["status"] in ("clean", "no_trades")
    assert rc.reconcile(dt.date(2026, 10, 27), trades, orders, [], log_start=ent)["status"] == "clean"
