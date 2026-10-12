"""LIVE KEEL close hook (api/qqq_exec.py, owner call 10-12 via MANAGER #143): every FULLY closed live
NOISE_382 lot -- whatever closed it -- drops ONE JSON into cloud_signal/keel_inbox with its P&L of
record; nothing for ORB / DIP / ENGU-Q, nothing off the box; never blocks or breaks the executor.

The single site: api/qqq_exec._reduce_lot's `if lot["shares_remaining"] <= 0:` branch, right after
_record_trade -- every close path below goes through it. Driven the way the box drives it: the
Env / FakeAccount of tests/test_qqq_exec_dip_live.py (a real PAPER OrderAdapter on a fake Webull
account), engine rows routed through api/qqq_exec.tick.

COVERS: strategy exit (Webull fills -> pnl_source webull_fill, the inbox file the handler reads),
the end-of-day flatten, the daily loss breaker, KILL, a late exit (a held lot's exit consumed late,
sold at market by the next tick), ORB / DIP never, off the box never, the wait for Webull's fills
and close order (FIFO), the "book" / "webull_part" sources, the chain (prev_trade_id, kept across
a restart), a failing inbox write (retried, the tick unharmed) and a failing hook (one log line).
"""
import csv
import json
import os
import sys

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import cloud_signal as cs  # noqa: E402
from api import qqq_exec as qe  # noqa: E402
import tools.keel_intraday as KI  # noqa: E402
from test_qqq_exec_dip_live import (DAY, DAY2, Env, _ref, at, dip_entry, dip_exit,  # noqa: E402
                                    noise_entry, orb_entry)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    return Env(tmp_path, monkeypatch)


def noise_exit(entry, day, hh, mm, px):
    return dict(entry, event="EXIT", ref_time=_ref(day, hh, mm), ref_price=px,
                reason="strategy_exit")


def inbox():
    d = os.path.join(cs.DEFAULT_PATHS["state_dir"], qe.KEEL_INBOX_DIR)
    if not os.path.isdir(d):
        return {}
    out = {}
    for n in sorted(os.listdir(d)):
        with open(os.path.join(d, n), encoding="utf-8") as f:
            out[n] = json.load(f)
    return out


def enter_noise(e, hh=10, mm=30, side="long", px=700.0, size=2.0, wb=None, day=DAY):
    """A NOISE_382 entry at the engine's price `px`, filled at Webull at `wb` (default px)."""
    e.price = px
    e.fake.fill_px = px if wb is None else wb
    row = noise_entry(day, hh, mm, side, px, size)
    e.tick(at(day, hh, mm + 5, 5), events=[row])
    assert e.lot("NOISE")["trade_id"] == row["trade_id"]
    return row


def _one(row):
    files = inbox()
    assert list(files) == [f"{row['trade_id']}.json"], files
    return files[f"{row['trade_id']}.json"]


# ── each close path -> one inbox file ───────────────────────────────────────────────────────────
def test_a_strategy_exit_drops_one_file_with_the_webull_pnl_of_record(env):
    e = env
    row = enter_noise(e, wb=700.10)                     # book 700.00, Webull 700.10
    assert e.lot("NOISE")["shares_total"] == 20
    e.fake.fill_px = 702.05
    e.px["NOISE"] = 702.0
    e.tick(at(DAY, 10, 50, 5), events=[noise_exit(row, DAY, 10, 45, 702.0)])
    assert "NOISE" not in e.state["legs"]
    rec = _one(row)
    (t,) = e.trades()
    assert (rec["leg"], rec["trade_id"], rec["side"], rec["shares"]) == ("NOISE_382", row["trade_id"],
                                                                          "long", 20)
    assert (rec["entry_ts"], rec["exit_ts"]) == (t["entry_ts"], t["exit_ts"])
    assert rec["pnl_source"] == "webull_fill"
    assert (rec["entry_px"], rec["exit_px"]) == (700.1, 702.05)
    assert rec["pnl_usd"] == round((702.05 - 700.10) * 20, 2) == 39.0
    assert rec["pnl_book"] == float(t["pnl"]) == 40.0 and rec["exit_reason"] == "signal exit"
    assert e.state["_keel_closes"] == []
    assert any("KEEL close sent to the keel inbox" in s for s in e.lines)
    # the file is exactly what the handler reads
    tr = KI.read_trade(os.path.join(cs.DEFAULT_PATHS["state_dir"], qe.KEEL_INBOX_DIR,
                                    f"{row['trade_id']}.json"))
    assert tr["pnl_usd"] == 39.0
    # the tmp dir is left empty
    assert os.listdir(os.path.join(cs.DEFAULT_PATHS["state_dir"], qe.KEEL_INBOX_TMP_DIR)) == []


def test_the_end_of_day_flatten_drops_one_file(env):
    e = env
    row = enter_noise(e, hh=15, mm=30)
    e.px["NOISE"] = e.fake.fill_px = 701.0
    e.tick(at(DAY, 15, 59, 5))
    assert "NOISE" not in e.state["legs"]
    rec = _one(row)
    assert rec["exit_reason"].startswith("EOD") and rec["pnl_usd"] == 20.0
    assert rec["pnl_source"] == "webull_fill"


def test_the_daily_loss_breaker_drops_one_file(env):
    e = env
    row = enter_noise(e)
    e.px["NOISE"] = e.fake.fill_px = 675.0                # 20 x -25 = -500 > the $400 rail
    e.tick(at(DAY, 11, 0, 5))
    assert e.state["breaker_tripped"] is True and "NOISE" not in e.state["legs"]
    rec = _one(row)
    assert rec["exit_reason"].startswith("BREAKER") and rec["pnl_usd"] == -500.0


def test_kill_drops_one_file(env):
    e = env
    row = enter_noise(e, side="short")
    e.kill(True)
    e.px["NOISE"] = e.fake.fill_px = 699.0
    e.tick(at(DAY, 11, 0, 5))
    assert "NOISE" not in e.state["legs"]
    rec = _one(row)
    assert rec["exit_reason"].startswith("KILL") and rec["side"] == "short"
    assert rec["pnl_usd"] == 20.0


def test_a_late_exit_sold_by_the_next_tick_drops_one_file(env):
    """A held lot's strategy exit consumed late is not sold at its old price: the next tick sells
    it at market (_run_deferred_held_closes -> _reduce_lot, LATE_EXIT_REASON)."""
    e = env
    e.cfg["session"] = dict(e.cfg["session"], hold_overnight_legs=["NOISE"])
    row = enter_noise(e)
    late = dict(noise_exit(row, DAY, 10, 45, 702.0), late=True)
    e.tick(at(DAY, 11, 30, 5), events=[late])
    assert e.lot("NOISE")["close_pending"]["late"] is True and inbox() == {}
    e.px["NOISE"] = e.fake.fill_px = 701.5
    e.tick(at(DAY, 11, 30, 30))
    assert "NOISE" not in e.state["legs"]
    rec = _one(row)
    assert rec["exit_reason"] == qe.LATE_EXIT_REASON and rec["pnl_usd"] == 30.0


def test_each_close_names_the_close_before_it_across_a_restart(env):
    # THE CHAIN (Custom ML 10-12, MUST d): KEEL's n is not known here, so every record carries the
    # previous live NOISE_382 close this book queued -- the handler refuses a missed / doubled one
    e = env
    r1 = enter_noise(e, hh=10, mm=30)
    e.px["NOISE"] = e.fake.fill_px = 701.0
    e.tick(at(DAY, 10, 50, 5), events=[noise_exit(r1, DAY, 10, 45, 701.0)])
    e.restart()                                         # state.json keeps the chain
    r2 = enter_noise(e, hh=11, mm=0, px=701.0)
    e.px["NOISE"] = e.fake.fill_px = 702.0
    e.tick(at(DAY, 11, 20, 5), events=[noise_exit(r2, DAY, 11, 15, 702.0)])
    files = inbox()
    assert files[f"{r1['trade_id']}.json"]["prev_trade_id"] is None
    assert files[f"{r2['trade_id']}.json"]["prev_trade_id"] == r1["trade_id"]
    assert e.state["_keel_last_tid"] == r2["trade_id"]


def test_orb_and_dip_closes_drop_nothing(env):
    e = env
    e.enter_dip(["RSI"], DAY, 700.0)
    e.tick(at(DAY, 10, 5, 5), events=[orb_entry(DAY, 10, 0, "long", 700.0)])
    e.tick(at(DAY, 15, 59, 5))                                 # ORB flattened, DIP held
    e.marks.update(prior_close=700.0, today_open=700.0, today_last=700.0)
    e.tick(at(DAY2, 9, 35, 10), events=[dip_exit(dip_entry("RSI", DAY, 700.0), DAY2, 700.0)])
    assert e.state["legs"] == {} and len(e.trades()) == 2
    assert inbox() == {} and not e.state.get("_keel_closes")


def test_off_the_box_nothing_is_queued(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    e = Env(tmp_path, monkeypatch)
    row = enter_noise(e)
    e.tick(at(DAY, 10, 50, 5), events=[noise_exit(row, DAY, 10, 45, 702.0)])
    assert "NOISE" not in e.state["legs"] and len(e.trades()) == 1
    assert inbox() == {} and "_keel_closes" not in e.state


def test_who_learns():
    lot = {"leg": "NOISE", "trade_id": "NOISE_382-20261013T143000Z-L"}
    assert qe._keel_learns_from(lot)
    assert not qe._keel_learns_from(dict(lot, trade_id="NOISE_304-20261013T143000Z-L"))
    assert not qe._keel_learns_from(dict(lot, trade_id="NT_NOISE-20261013T143000Z-L"))
    assert not qe._keel_learns_from(dict(lot, leg="ORB"))
    assert not qe._keel_learns_from(dict(lot, trade_id=None))


# ── waiting for Webull's fills, close order ─────────────────────────────────────────────────────
def _lot(tid, entry_ts, exit_ts, px=700.0, shares=10, side="long"):
    return {"leg": "NOISE", "trade_id": tid, "entry_ts": entry_ts, "_exit_ts": exit_ts,
            "side": side, "shares_total": shares, "entry_px": px}


def _broker(rows):
    with open(qe.BROKER_ORDERS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        for tid, intent, px in rows:
            w.writerow({"ts_et": "2026-10-13 10:00:00", "leg": "NOISE", "intent": intent,
                        "side": "BUY" if intent == "OPEN" else "SELL", "shares": 10,
                        "signal_id": qe._broker_signal_id(None, None, intent, trade_id=tid),
                        "mode": "PAPER", "ok": "True", "sent": "True", "shadow_px": "700",
                        "broker_fill_px": "" if px is None else px})


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(tmp_path / "cs_home")))
    monkeypatch.setattr(qe, "_now_et", lambda: at(DAY, 11, 0))
    return []


A = "NOISE_382-20261013T143000Z-L"
B = "NOISE_382-20261013T150000Z-L"


def test_a_close_waits_for_its_webull_fill_and_a_later_close_never_overtakes_it(box):
    logs = box
    _broker([(A, "OPEN", "700.1"), (A, "CLOSE", None)])        # A's sell has no price yet
    st = {}
    qe._queue_keel_close(st, _lot(A, "2026-10-13 10:30:05", "2026-10-13 10:45:05"), 702.0, 20.0,
                         "signal exit", log=logs.append)
    qe._queue_keel_close(st, _lot(B, "2026-10-13 11:00:05", "2026-10-13 11:10:05"), 699.0, -10.0,
                         "signal exit", log=logs.append)
    qe._queue_keel_close(st, _lot(B, "x", "y"), 1.0, 0.0, "dup", log=logs.append)   # queued once
    assert [i["trade_id"] for i in st["_keel_closes"]] == [A, B]
    qe._maybe_emit_keel_closes(st, log=logs.append)
    assert inbox() == {}, "A waits for its fill; B (no Webull order at all) waits behind it"
    _broker([(A, "OPEN", "700.1"), (A, "CLOSE", "702.05")])
    qe._maybe_emit_keel_closes(st, log=logs.append)
    got = inbox()
    assert [got[f"{t}.json"]["pnl_source"] for t in (A, B)] == ["webull_fill", "book"]
    assert got[f"{A}.json"]["pnl_usd"] == 19.5 and got[f"{B}.json"]["pnl_usd"] == -10.0
    assert st["_keel_closes"] == []


def test_a_fill_that_never_comes_goes_with_the_book_price_after_the_wait(box, monkeypatch):
    _broker([(A, "OPEN", "700.1"), (A, "CLOSE", None)])
    st = {}
    qe._queue_keel_close(st, _lot(A, "2026-10-13 10:30:05", "2026-10-13 10:45:05"), 702.0, 20.0,
                         "signal exit", log=box.append)
    qe._maybe_emit_keel_closes(st, log=box.append)
    assert inbox() == {}
    st["_keel_closes"][0]["queued_at"] -= qe.KEEL_CLOSE_FILL_WAIT_SEC + 1
    qe._maybe_emit_keel_closes(st, log=box.append)
    rec = inbox()[f"{A}.json"]
    assert rec["pnl_source"] == "webull_part" and rec["entry_px"] == 700.1 and rec["exit_px"] == 702.0
    assert rec["pnl_usd"] == 19.0


def test_an_unmarked_exit_goes_as_null_for_the_handler_to_refuse(box):
    st = {}
    qe._queue_keel_close(st, _lot(A, "2026-10-13 10:30:05", "2026-10-13 10:45:05"),
                         float("nan"), float("nan"), "EOD", log=box.append)
    qe._maybe_emit_keel_closes(st, log=box.append)
    rec = inbox()[f"{A}.json"]
    assert rec["pnl_usd"] is None and rec["exit_px"] is None and st["_keel_closes"] == []


def test_the_inbox_file_is_complete_before_it_lands(box, monkeypatch):
    """Written in keel_inbox_tmp (a sibling, unwatched), then os.replace'd into the inbox: the
    path unit never sees a half-written file."""
    moves = []
    real = os.replace

    def spy(src, dst):
        moves.append((os.path.dirname(src), os.path.dirname(dst)))
        return real(src, dst)
    monkeypatch.setattr(qe.os, "replace", spy)
    assert qe._write_keel_inbox({"trade_id": A, "pnl_usd": 1.0}, log=box.append) is True
    inbox_dir, tmp_dir = qe._keel_inbox_dirs()
    assert moves == [(tmp_dir, inbox_dir)]
    assert os.path.dirname(tmp_dir) == os.path.dirname(inbox_dir)
    assert os.listdir(tmp_dir) == [] and os.listdir(inbox_dir) == [f"{A}.json"]


# ── never blocks, never breaks ──────────────────────────────────────────────────────────────────
def test_a_failing_inbox_write_is_retried_and_never_breaks_the_tick(env, monkeypatch):
    e = env
    row = enter_noise(e)
    real = qe._keel_inbox_dirs

    def boom():
        raise OSError("read-only file system")
    monkeypatch.setattr(qe, "_keel_inbox_dirs", boom)
    e.tick(at(DAY, 10, 50, 5), events=[noise_exit(row, DAY, 10, 45, 702.0)])
    assert "NOISE" not in e.state["legs"] and len(e.trades()) == 1
    (item,) = e.state["_keel_closes"]
    assert item["retry_at"] > 0 and inbox() == {}
    assert sum("KEEL inbox write failed" in s for s in e.lines) == 1
    e.tick(at(DAY, 10, 50, 10))
    assert sum("KEEL inbox write failed" in s for s in e.lines) == 1, "retried once a minute, not every tick"
    e.restart()                                           # state.json keeps the queue
    assert e.state["_keel_closes"][0]["trade_id"] == row["trade_id"]
    monkeypatch.setattr(qe, "_keel_inbox_dirs", real)
    e.state["_keel_closes"][0]["retry_at"] = 0.0
    e.tick(at(DAY, 10, 52, 5))
    assert _one(row)["trade_id"] == row["trade_id"] and e.state["_keel_closes"] == []


def test_a_failing_hook_or_emit_is_one_log_line(box, monkeypatch):
    st = {}
    qe._queue_keel_close(st, {"leg": "NOISE", "trade_id": A}, 1.0, 0.0, "x", log=box.append)
    assert "_keel_closes" not in st or st["_keel_closes"] == []
    assert len(box) == 1 and "KEEL close hook failed" in box[0]
    qe._queue_keel_close(st, _lot(A, "2026-10-13 10:30:05", "2026-10-13 10:45:05"), 702.0, 20.0,
                         "signal exit", log=box.append)
    monkeypatch.setattr(qe, "_all_broker_orders_from_csv",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("csv gone")))
    qe._maybe_emit_keel_closes(st, log=box.append)
    assert "KEEL close emit failed" in box[-1] and len(st["_keel_closes"]) == 1
