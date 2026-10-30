"""tools/nt_fill_reconcile.py - NinjaTrader demo fills vs the book (B1 NT side), on fixture files only."""
import datetime as dt

from tools import nt_fill_reconcile as N

HEAD = "ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId,SignalName\n"
DAY = dt.date(2026, 10, 28)


def _book(**kw):
    row = {"leg": "ENGUQ_335", "side": "1", "size": "1.0", "open": "False",
           "entryIso": "2026-10-28T11:46:00-04:00", "exitIso": "2026-10-28T16:10:00-04:00",
           "entry_px": "29859.72", "exit_px": "29946.04", "pnl_usd": "1726.51"}
    row.update(kw)
    return row


def _fills(tmp_path, rows):
    p = tmp_path / "fills.csv"
    p.write_text(HEAD + "".join(r + "\n" for r in rows), encoding="utf-8")
    return str(p)


def test_a_filled_enguq_trade_is_clean_and_priced_per_nq_point(tmp_path):
    f = _fills(tmp_path, ["e1,2026-10-28 15:46:25,DEMO7240108,NQ 12-26,BUY,1,29859.75,0,o1,EQ",
                          "e2,2026-10-28 20:10:13,DEMO7240108,NQ 12-26,SELL,1,29946,0,o2,EQx"])
    rep = N.run(DAY, [_book()], fills_path=f)
    assert rep["status"] == "clean"
    assert round(rep["broker_usd"], 2) == 1725.0 and round(rep["book_usd"], 2) == 1726.51


def test_a_book_trade_the_demo_never_took_is_missing(tmp_path):
    f = _fills(tmp_path, ["e9,2026-10-27 15:00:00,DEMO7240108,NQ 12-26,BUY,1,29000,0,o9,EQ"])
    rep = N.run(DAY, [_book()], fills_path=f)
    assert rep["status"] == "missing" and rep["no_fill"][0]["leg"] == "ENGUQ_335"
    assert "1 trade(s) not filled" in N.words(DAY, rep)


def test_the_real_account_is_never_read_as_a_demo_fill(tmp_path):
    f = _fills(tmp_path, ["e1,2026-10-28 15:46:25,1810769,NQ 12-26,BUY,1,29859.75,0,o1,EQ",
                          "e2,2026-10-28 20:10:13,1810769,NQ 12-26,SELL,1,29946,0,o2,EQx"])
    assert N.run(DAY, [_book()], fills_path=f)["status"] == "missing"


def test_noise_sizes_are_mnq_contracts_and_a_session_close_exit_belongs_to_noise(tmp_path):
    book = _book(leg="NOISE_H_RF", size="3.58", side="1", entryIso="2026-10-27T09:40:00-04:00",
                 exitIso="2026-10-27T15:55:00-04:00", entry_px="29674.25", exit_px="29683.25",
                 pnl_usd=str(9 * 20 * 3.58))
    f = _fills(tmp_path, ["a,2026-10-27 13:40:00,DEMO7240108,MNQ 12-26,BUY,11,29674.25,0,o1,NZ",
                          "b,2026-10-27 19:59:30,DEMO7240108,MNQ 12-26,SELL,6,29683.25,0,o2,Exit on session close",
                          "c,2026-10-27 19:59:31,DEMO7240108,MNQ 12-26,SELL,5,29683.25,0,o2,Exit on session close"])
    rep = N.run(dt.date(2026, 10, 27), [book], fills_path=f)
    assert rep["status"] == "clean", rep
    assert round(rep["broker_usd"], 2) == 9 * 2 * 11 == round(rep["book_usd"], 2)
