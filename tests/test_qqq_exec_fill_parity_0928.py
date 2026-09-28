"""FILL PARITY + P&L OF RECORD on the REAL 2026-09-28 rows (owner decisions 2026-09-28,
after the 09-28 parity audit). tests/fixtures/parity0928/ holds copies of the box's own
trades.csv, broker_orders.csv, reprice.csv and orders.csv and the engine's signals.csv as
they stood after the 09-28 close (read-only copies; nothing here touches C:\\EdgeLog).

Expected numbers are worked by hand from those rows, against the backtest's own fill
(owner, 2026-09-28: "fill price vs the backtest's assumed fill"). Decide-at-close NOISE
rows: the engine's row carries the DECISION close, but the backtest fills at the OPEN of
the next bar -- read from the box's own 1-minute bars in the fixture folder (a bar's
open is its first minute's open; the box's 5-minute file agrees, e.g. the 12:05 bar
opened 735.18). ORB: the 10:45 bar's close; ENGU-Q: its 738.0295 limit.
"""
import os

import pytest

from api import qqq_exec as qe

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "parity0928")
NOOP = lambda *a, **k: None  # noqa: E731


def _build(monkeypatch, bars_dir):
    monkeypatch.setattr(qe, "TRADES_CSV", os.path.join(FIX, "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", os.path.join(FIX, "broker_orders.csv"))
    qe._ENGINE_PX_CACHE["key"] = None
    rows = [dict(r) for r in reversed(qe._all_trades_from_csv())]
    qe._merge_reprice(rows, log=NOOP)
    eng = qe._engine_prices_by_trade(path=os.path.join(FIX, "signals.csv"), bars_dir=bars_dir,
                                     log=NOOP)
    by_base = qe._broker_orders_by_base(qe._all_broker_orders_from_csv())
    qe._apply_broker_parity(rows, by_base, engine_px=eng, log=NOOP)
    return {r["trade_id"] or (r["leg"] + r["entry_ts"]): r for r in rows}, rows, eng


@pytest.fixture
def book(monkeypatch):
    by_id, rows, _eng = _build(monkeypatch, FIX)
    return by_id, rows


def test_decide_at_close_rows_are_priced_at_the_next_bars_open(monkeypatch):
    _, _, eng = _build(monkeypatch, FIX)
    en = eng["NOISE_382-20260928T160500Z-S"]["ENTRY"]
    assert en["dec_px"] == pytest.approx(735.31)     # the 12:00 bar's close (the decision)
    assert en["px"] == pytest.approx(735.18)         # the 12:05 bar's open (the backtest's fill)
    # a row that is not decide-at-close keeps its own ref_price (ORB's signal-bar close)
    orb = eng["ORB_R6-20260928T144500Z-S"]["ENTRY"]
    assert orb["px"] == pytest.approx(732.33) and orb["dec_px"] is None


def test_noise_trade_1_webull_beat_the_backtest_and_is_not_flagged(book):
    by_id, _ = book
    r = by_id["NOISE_382-20260928T141500Z-S"]            # short 20, decided 10:10
    fp = r["fp"]
    assert fp["en"]["bt"] == pytest.approx(735.66)       # the 10:15 bar's open
    assert fp["en"]["wb"] == pytest.approx(735.87)
    assert fp["en"]["edge"] == pytest.approx(0.21)       # sold higher: better
    assert fp["ex"]["bt"] == pytest.approx(735.73)       # the 11:40 bar's open
    assert fp["ex"]["edge"] == pytest.approx(0.16)       # covered lower: better
    assert fp["gap_usd"] == pytest.approx(7.40)
    assert r["broker_parity_ok"] is True
    assert r["pnl_record"] == pytest.approx(6.00) and r["pnl_record_src"] == "webull"
    assert r["pnl_backtest"] == pytest.approx(-1.40)
    assert r["pnl"] == "-1.1", "the stored book figure is never rewritten"


def test_noise_trade_3_is_3_cents_worse_than_the_backtests_fill_not_flagged(book):
    """The 12:05 short: 16 cents worse than the DECISION close (735.31) but only 3 cents
    worse than the backtest's own fill, the 12:05 bar's open (735.18) -- not flagged."""
    by_id, _ = book
    r = by_id["NOISE_382-20260928T160500Z-S"]
    assert r["fp"]["en"]["bt"] == pytest.approx(735.18)
    assert r["fp"]["en"]["edge"] == pytest.approx(-0.03)
    assert r["broker_parity_ok"] is True
    assert r["pnl_record"] == pytest.approx(-5.80)


def test_without_the_next_bar_on_file_it_falls_back_to_the_decision_close(monkeypatch, tmp_path):
    by_id, _, _ = _build(monkeypatch, str(tmp_path))     # no bar files at all
    r = by_id["NOISE_382-20260928T160500Z-S"]
    assert r["fp"]["en"]["bt"] == pytest.approx(735.31)
    assert r["fp"]["en"]["edge"] == pytest.approx(-0.16)
    assert r["broker_parity_ok"] is False


def test_orb_entry_only_until_the_backtest_exit_lands(book):
    by_id, _ = book
    r = by_id["ORB_R6-20260928T144500Z-S"]
    assert r["fp"]["st"] == "entry only"
    assert r["fp"]["en"]["edge"] == pytest.approx(0.25)
    assert r["fp"]["en"]["slp"] == pytest.approx(0.25)
    assert r["pnl_record"] == pytest.approx(-39.90)       # Webull's real fills
    assert r["pnl"] == "-44.4"                            # the book, kept
    assert r["pnl_backtest"] is None


def test_enguq_limit_vs_market_is_all_design(book):
    by_id, _ = book
    r = by_id["ENGUQ_335-20260928T163200Z-L"]
    en = r["fp"]["en"]
    assert en["bt"] == pytest.approx(738.0295)
    assert en["dsg"] == pytest.approx(-0.5305) and en["slp"] == pytest.approx(0.0)
    assert r["broker_parity_ok"] is True
    assert r["pnl_record"] == pytest.approx(-19.80)       # 738.56 -> 736.58 (the R1 resend)


def test_enguq_0924_suspect_capture_is_marked_not_rewritten(book):
    by_id, _ = book
    r = by_id["ENGUQ_335-20260924T161700Z-L"]
    assert r["fp"]["en"]["fs"] == "suspect"
    assert r["broker_parity_ok"] is False
    assert r["pnl_record_src"] == "part"
    assert r["pnl_record"] == pytest.approx(round((741.32 - 739.3817) * 10, 2))
    # the backtest's own exit came four days later (the 09-28 10:42 stop): design gap
    assert r["fp"]["ex"]["bt"] == pytest.approx(734.6301)
    assert r["pnl_backtest"] == pytest.approx(-47.42)
    with open(os.path.join(FIX, "broker_orders.csv"), encoding="utf-8") as f:
        assert "737.88" in f.read(), "the historical row itself stays as captured"


def test_noise_0925_eod_flatten_design_vs_slippage(book):
    by_id, _ = book
    r = by_id["NOISE_382-20260925T161000Z-L"]      # long 15, flattened 15:59 at 744.92
    ex = r["fp"]["ex"]
    assert ex["bt"] == pytest.approx(744.50)       # engine's own day-end exit (09-28 09:35 row)
    assert ex["dsg"] == pytest.approx(0.42)        # the 15:59 quote was 42c above the close
    assert ex["slp"] == pytest.approx(-0.32)       # Webull sold 32c under that quote
    assert r["broker_parity_ok"] is False          # 32c worse than the flatten quote


def test_book_only_row_is_book_price_labelled(book):
    by_id, _ = book
    r = by_id["NOISE_304-20260923T140500Z-S"]      # Webull refused the short (HTTP 417)
    assert r["broker_parity_ok"] is None
    assert r["pnl_record_src"] == "book"
    assert r["pnl_record_note"] == "book price, no Webull fill"
    assert r["pnl_record"] == pytest.approx(float(r["pnl"]))


def test_board_summary_on_the_real_rows(book):
    _, rows = book
    s = qe._broker_parity_summary(rows)
    assert s["checked"] == 10
    noise = s["legs"]["NOISE"]
    assert noise["n"] == 7
    assert s["board_flag"] is False
    assert s["failed"] == 2              # 09-25 12:15 (15:59 flatten 32c under), 09-24 suspect
    assert "36 of 36" not in s["note"] and "miss" not in s["note"]
    # P&L where both are known: Webull's fills vs the backtest
    assert s["n_both"] == 7
    assert s["webull_usd"] == pytest.approx(-54.30)
    assert s["backtest_usd"] == pytest.approx(-70.15)


def test_running_average_leaves_out_the_suspect_fill_and_all_design_sides(book):
    """Review 2026-09-28: the 09-24 ENGU-Q capture (737.88, +1.4917/sh unexplained) made
    up nearly all of an '8.6 cents a share better' board read. It is out of the running
    average now (its trade keeps its own CHECK FILL flag), and so is every side whose gap
    is all design by construction (limit / level / late, slippage fixed at 0)."""
    _, rows = book
    s = qe._broker_parity_summary(rows)
    b = s["board"]
    assert b["suspect_fills"] == 1
    assert b["design_only_fills"] == 6   # 1 ENGU-Q limit, 5 NOISE before 09-26
    assert b["fills"] == 11              # 8 NOISE 09-28 + NOISE 09-25 15:59 + ENGU-Q 15:59 + ORB
    # 8 NOISE 09-28 fills (+0.21 +0.16 -0.09 -0.0837 -0.03 -0.09 +0.14 +0.125) + the 09-25
    # flatten (-0.32) + the 09-24 ENGU-Q flatten (-0.025) + ORB (+0.25), over 11
    assert b["avg_exec_ps"] == pytest.approx(0.0224, abs=1e-4)
    assert "do not fit the tape left out" in s["note"]
    enguq = s["legs"]["ENGUQ"]
    # the suspect entry is out; its limit entry is all design; only the 09-24 15:59
    # flatten's slippage is left
    assert enguq["suspect_fills"] == 1 and enguq["fills"] == 1
    assert enguq["avg_exec_ps"] == pytest.approx(-0.025)
    assert enguq["flag"] is False


def _fp_trade(edge_en, edge_ex, why_en="", why_ex="", fs_en="ok", flag=False):
    def side(edge, why, fs):
        dsg = edge if why in qe.DESIGN_ONLY_WHY else 0.0
        unx = edge if fs == "suspect" else 0.0
        return {"bt": 100.0, "wb": 100.0, "fs": fs, "edge": edge, "dsg": dsg,
                "slp": edge - dsg - unx, "unx": unx, "why": "suspect" if fs == "suspect" else why}
    return {"en": side(edge_en, why_en, fs_en), "ex": side(edge_ex, why_ex, "ok"),
            "exec_ps": 0.0, "flag": flag}


def test_one_helpful_suspect_fill_cannot_hide_a_leg_running_6_cents_worse():
    rows = [_fp_trade(-0.06, -0.06) for _ in range(5)]
    rows.append(_fp_trade(2.00, -0.06, fs_en="suspect", flag=True))
    blk = qe._roll_block(rows)
    assert blk["suspect_fills"] == 1 and blk["fills"] == 11
    assert blk["avg_exec_ps"] == pytest.approx(-0.06)
    assert blk["flag"] is True


def test_all_design_sides_do_not_dilute_the_average_and_a_leg_with_none_says_so():
    # ENGU-Q-like: limit entries and level exits only -> no slippage to compare
    blk = qe._roll_block([_fp_trade(-0.50, 0.30, "limit", "level") for _ in range(3)])
    assert blk["fills"] == 0 and blk["design_only_fills"] == 6
    assert blk["avg_exec_ps"] is None and blk["flag"] is False
    assert blk["avg_dsg_ps"] == pytest.approx(-0.10)
    # 2 fills 6 cents worse among 6 all-design sides: still 6 cents worse, still flags
    rows = [_fp_trade(-0.06, -0.06)] + [_fp_trade(0.0, 0.0, "late", "late") for _ in range(3)]
    blk = qe._roll_block(rows)
    assert blk["fills"] == 2 and blk["avg_exec_ps"] == pytest.approx(-0.06) and blk["flag"]


def test_published_rows_are_packed_and_the_tab_reads_them_back(book):
    """Firestore caps (1 MiB, 40,000 index entries) with up to 500 rows in one doc: each
    fp side rides as one string, and an in-band row drops its note sentence."""
    _, rows = book
    r_ok = next(r for r in rows if r["trade_id"] == "NOISE_382-20260928T141500Z-S")
    r_bad = next(r for r in rows if r["trade_id"] == "ENGUQ_335-20260924T161700Z-L")
    en_before = dict(r_ok["fp"]["en"])
    qe._compact_published_trades(rows)
    assert r_ok["fp"]["en"] == "735.66|735.87|o|0.21|0|0.21|0|"
    assert r_bad["fp"]["en"].split("|")[2] == "s" and r_bad["fp"]["en"].endswith("|suspect")
    assert r_ok["fp"]["ex"].split("|")[0] == "735.73"
    assert "broker_parity_note" not in r_ok, "an in-band row needs no hover sentence"
    assert r_bad["broker_parity_note"].startswith("FLAGGED"), "a flagged row keeps its hover"
    parts = r_ok["fp"]["en"].split("|")
    assert float(parts[0]) == en_before["bt"] and float(parts[3]) == en_before["edge"]


def test_doc_budget_trims_the_oldest_rows_only_when_over(book):
    import copy
    _, rows = book
    comp = [r for r in rows if (r.get("fp") or {}).get("exec_ps") is not None]
    big = [copy.deepcopy(comp[i % len(comp)]) for i in range(500)]
    qe._compact_published_trades(big)
    per_row = qe._fs_size(big) / 500
    assert per_row < 1200, f"a packed row is {per_row:.0f} bytes"
    assert qe._fs_leaves(big) / 500 <= 61
    doc = {"trades_all": list(big)}
    qe._fit_doc_budget(doc, log=NOOP)
    assert doc["trades_all_trimmed"] == 0 and len(doc["trades_all"]) == 500
    # a budget the doc does not fit: the OLDEST rows (the end of a newest-first list) go
    logs = []
    newest = doc["trades_all"][0]
    orig = qe.FS_DOC_BUDGET_LEAVES
    try:
        qe.FS_DOC_BUDGET_LEAVES = 12_000
        qe._fit_doc_budget(doc, log=logs.append)
    finally:
        qe.FS_DOC_BUDGET_LEAVES = orig
    assert doc["trades_all_trimmed"] > 0 and doc["trades_all"][0] is newest
    assert qe._fs_leaves(doc) <= 12_000 and logs


def test_curve_and_today_use_the_pnl_of_record(book):
    _, rows = book
    today = [r for r in rows if r["exit_ts"].startswith("2026-09-28")]
    rec = round(sum(qe._curve_pnl(r) for r in today), 2)
    book_sum = round(sum(float(r["pnl"]) for r in today), 2)
    assert rec == pytest.approx(-84.50)      # the audit's Webull total for 09-28
    assert book_sum == pytest.approx(-88.95)  # the audit's book ledger total
    cum = qe._cum_pnl_by_leg(rows)
    assert cum["total"][-1]["cum_pnl"] == pytest.approx(round(sum(qe._curve_pnl(r) for r in rows), 2))
