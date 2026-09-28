"""api/qqq_exec.py's FILL PARITY (rebuilt 2026-09-28 on the owner's decisions after the
09-28 parity audit; first built 2026-09-22 as feature #56).

WHAT CHANGED. The PARITY NOTE compared each Webull fill with the BOOK's send-time price,
called that "engine booked", judged it against 2% of the trade's P&L, ignored direction
and fell back to the re-price minute close -- "36 of 36 trades miss" on a day Webull beat
the backtest. It now compares each Webull fill with the BACKTEST's own price for that
side (the engine's ref_price, joined by trade id), signed (+ = Webull better), per share,
split into design gap / slippage / unexplained; flags a trade when one fill is more than
15 cents a share worse once design is taken out (or a fill does not fit the tape); flags
a leg / the board when the signed per-fill average over the last 20 trades is worse than
-5 cents a share; and never uses the minute close.

These tests are synthetic (hand-built rows); tests/test_qqq_exec_fill_parity_0928.py
runs the same code on the real 2026-09-28 rows.
"""
import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


def _tid(leg="NOISE_382", stamp="20260928T141500Z", side="S"):
    return f"{leg}-{stamp}-{side}"


def _row(trade_id, leg="NOISE", side="short", shares="10", entry_px="100.00",
         exit_px="99.00", pnl="10.0", exit_reason="signal exit", signal_source="engine",
         **extra):
    r = {"leg": leg, "trade_id": trade_id, "side": side, "shares": shares,
         "entry_px": entry_px, "exit_px": exit_px, "pnl": pnl, "exit_reason": exit_reason,
         "signal_source": signal_source, "entry_ts": "2026-09-28 10:15:11",
         "exit_ts": "2026-09-28 11:40:09"}
    r.update(extra)
    return r


def _broker(trade_id, intent, px, ok=True, resend=0):
    sid = qe._broker_signal_id(None, None, intent, trade_id=trade_id)
    if resend:
        sid = f"{sid}R{resend}"
    return {"signal_id": sid, "intent": intent, "ok": "True" if ok else "False",
            "broker_fill_px": "" if px is None else str(px)}


def _eng(entry=None, exit_=None, dac=True):
    reason = "decide_at_close: decided at the close" if dac else ""
    out = {}
    if entry is not None:
        out["ENTRY"] = {"px": entry, "ref_time": "", "reason": reason}
    if exit_ is not None:
        out["EXIT"] = {"px": exit_, "ref_time": "", "reason": "strategy_exit; " + reason}
    return out


def _run(row, brokers, eng):
    by_base = qe._broker_orders_by_base(brokers)
    return qe._broker_trade_parity(row, by_base, engine_px={row["trade_id"]: eng}, log=NOOP)


# ── signs ────────────────────────────────────────────────────────────────────────────
def test_short_better_fills_read_positive_and_never_flag():
    """Short: SELL entry higher than the backtest and BUY exit lower are both BETTER."""
    t = _tid()
    out = _run(_row(t), [_broker(t, "OPEN", 100.30), _broker(t, "CLOSE", 98.80)],
               _eng(100.00, 99.00))
    fp = out["fp"]
    assert fp["en"]["edge"] == pytest.approx(0.30)
    assert fp["ex"]["edge"] == pytest.approx(0.20)
    assert fp["gap_usd"] == pytest.approx(5.00)
    assert out["broker_parity_ok"] is True, "a better fill must never flag"
    assert "better" in out["broker_parity_note"]


def test_long_signs_buy_lower_sell_higher_is_better():
    t = _tid(side="L")
    out = _run(_row(t, side="long"), [_broker(t, "OPEN", 99.95), _broker(t, "CLOSE", 99.05)],
               _eng(100.00, 99.00))
    assert out["fp"]["en"]["edge"] == pytest.approx(0.05)
    assert out["fp"]["ex"]["edge"] == pytest.approx(0.05)


def test_one_fill_16_cents_worse_flags_14_cents_does_not():
    t = _tid()
    worse = _run(_row(t), [_broker(t, "OPEN", 99.84), _broker(t, "CLOSE", 99.00)],
                 _eng(100.00, 99.00))
    assert worse["broker_parity_ok"] is False
    assert "over 15c a share worse" in worse["broker_parity_note"]
    ok = _run(_row(t), [_broker(t, "OPEN", 99.86), _broker(t, "CLOSE", 99.14)],
              _eng(100.00, 99.00))
    # two fills 14 cents worse each: 28 cents on the round trip, but the band is per fill
    assert ok["broker_parity_ok"] is True
    assert ok["fp"]["exec_ps"] == pytest.approx(-0.28)


# ── design gap split ─────────────────────────────────────────────────────────────────
def test_eod_flatten_splits_design_and_slippage():
    """The book flattened at 15:59 at a quote of 99.50; the backtest's own exit was
    99.00; Webull filled the buy-to-cover at 99.60. Design = backtest vs the book's
    flatten price (-0.50), slippage = the flatten price vs the fill (-0.10)."""
    t = _tid()
    out = _run(_row(t, exit_px="99.50", exit_reason="EOD (px: live_stream)"),
               [_broker(t, "OPEN", 100.00), _broker(t, "CLOSE", 99.60)], _eng(100.00, 99.00))
    ex = out["fp"]["ex"]
    assert ex["edge"] == pytest.approx(-0.60)
    assert ex["dsg"] == pytest.approx(-0.50)
    assert ex["slp"] == pytest.approx(-0.10)
    assert ex["unx"] == pytest.approx(0.0)
    assert ex["why"] == "eod" and "15:59" in qe.FP_WHY["eod"]
    assert out["broker_parity_ok"] is True, "design gaps never flag on their own"


def test_limit_entry_leg_whole_entry_gap_is_design():
    t = _tid(leg="ENGUQ_335", side="L")
    out = _run(_row(t, leg="ENGUQ", side="long"), [_broker(t, "OPEN", 100.53)],
               _eng(100.00, None))
    en = out["fp"]["en"]
    assert en["edge"] == pytest.approx(-0.53)
    assert en["dsg"] == pytest.approx(-0.53)
    assert en["slp"] == pytest.approx(0.0)
    assert out["fp"]["st"] == "entry only"
    assert out["broker_parity_ok"] is True


def test_orb_level_exit_is_design_orb_entry_is_slippage():
    t = _tid(leg="ORB_R6", side="S")
    out = _run(_row(t, leg="ORB", exit_reason="signal exit"),
               [_broker(t, "OPEN", 99.70), _broker(t, "CLOSE", 101.30)],
               _eng(100.00, 101.00, dac=False))
    assert out["fp"]["en"]["slp"] == pytest.approx(-0.30)
    assert out["fp"]["ex"]["dsg"] == pytest.approx(-0.30)
    assert out["broker_parity_ok"] is False   # the entry is 30 cents worse: slippage


def test_noise_before_decide_at_close_is_design():
    t = _tid(stamp="20260925T141500Z", side="S")
    out = _run(_row(t, entry_ts="2026-09-25 10:15:11", exit_ts="2026-09-25 11:40:09"),
               [_broker(t, "OPEN", 99.50), _broker(t, "CLOSE", 99.00)],
               _eng(100.00, 99.00, dac=False))
    assert out["fp"]["en"]["dsg"] == pytest.approx(-0.50)
    assert out["fp"]["en"]["why"] == "late" and out["fp"]["ex"]["why"] == "late"
    assert out["broker_parity_ok"] is True


# ── suspect fills ────────────────────────────────────────────────────────────────────
def test_suspect_fill_is_unexplained_flagged_and_left_out_of_pnl_of_record():
    tid = "ENGUQ_335-20260924T161700Z-L"
    assert qe._broker_signal_id(None, None, "OPEN", trade_id=tid) in qe.SUSPECT_BROKER_FILLS
    row = _row(tid, leg="ENGUQ", side="long", entry_px="739.3817", exit_px="741.345",
               pnl="19.63", exit_reason="EOD")
    out = _run(row, [_broker(tid, "OPEN", 737.88), _broker(tid, "CLOSE", 741.32)],
               _eng(739.3717, 734.6301, dac=False))
    en = out["fp"]["en"]
    assert en["fs"] == "suspect"
    assert en["unx"] == pytest.approx(739.3717 - 737.88)
    assert en["dsg"] == 0.0 and en["slp"] == 0.0
    assert out["broker_parity_ok"] is False
    assert "does not fit the tape" in out["broker_parity_note"]
    # P&L of record: the suspect entry is NOT used -- book entry + Webull exit
    assert out["pnl_record"] == pytest.approx(round((741.32 - 739.3817) * 10, 2))
    assert out["pnl_record_src"] == "part"
    assert "looks wrong" in out["pnl_record_note"]


def test_reprice_range_check_marks_a_fill_suspect():
    t = _tid()
    out = _run(_row(t, entry_fill_check="suspect"),
               [_broker(t, "OPEN", 100.00), _broker(t, "CLOSE", 99.00)], _eng(100.00, 99.00))
    assert out["fp"]["en"]["fs"] == "suspect"


# ── never the minute close ───────────────────────────────────────────────────────────
def test_no_fill_side_is_not_compared_never_the_minute_close():
    t = _tid()
    row = _row(t, real_entry_px="100.40", real_exit_px="98.60",
               entry_px_source="webull_stream_1m", exit_px_source="webull_stream_1m")
    out = _run(row, [], _eng(100.00, 99.00))
    assert out["broker_parity_ok"] is None
    assert out["fp"]["en"]["edge"] is None
    assert "no Webull fill" in out["broker_parity_note"]
    assert out["pnl_record"] == pytest.approx(10.0)          # the book's own figure
    assert out["pnl_record_src"] == "book"
    assert out["pnl_record_note"] == "book price, no Webull fill"


def test_persisted_fill_in_reprice_sidecar_is_used_when_broker_row_aged_out():
    t = _tid()
    row = _row(t, real_entry_px="100.30", real_exit_px="98.80",
               entry_px_source="webull_fill", exit_px_source="webull_fill")
    out = _run(row, [], _eng(100.00, 99.00))
    assert out["fp"]["en"]["wb"] == pytest.approx(100.30)
    assert out["pnl_record_src"] == "webull"
    assert out["pnl_record"] == pytest.approx(15.0)


def test_failed_broker_row_fill_ignored_and_resend_wins():
    t = _tid()
    brokers = [_broker(t, "OPEN", 100.00), _broker(t, "CLOSE", 98.00, ok=False),
               _broker(t, "CLOSE", 98.90, resend=1)]
    out = _run(_row(t), brokers, _eng(100.00, 99.00))
    assert out["fp"]["ex"]["wb"] == pytest.approx(98.90)


def test_backtest_exit_unknown_compares_entry_only():
    t = _tid()
    out = _run(_row(t, exit_reason="EOD"), [_broker(t, "OPEN", 100.10), _broker(t, "CLOSE", 99.0)],
               _eng(100.00, None))
    assert out["fp"]["st"] == "entry only"
    assert "has not exited" in out["broker_parity_note"]
    assert out["pnl_backtest"] is None


def test_voided_entry_says_the_backtest_never_took_it():
    t = _tid(leg="ENGUQ_335", side="L")
    eng = {"VOID": {"px": 100.0, "ref_time": "", "reason": "ghost"}}
    out = _run(_row(t, leg="ENGUQ", side="long"), [_broker(t, "OPEN", 100.0),
                                                   _broker(t, "CLOSE", 101.0)], eng)
    assert out["broker_parity_ok"] is None
    assert "never took" in out["broker_parity_note"]


def test_no_trade_id_is_not_compared():
    out = qe._broker_trade_parity(_row(""), {}, engine_px={}, log=NOOP)
    assert out["broker_parity_ok"] is None
    assert "no trade id" in out["broker_parity_note"]


def test_never_raises_on_garbage():
    out = qe._broker_trade_parity({"shares": "x", "side": None, "trade_id": 5}, None,
                                  engine_px="nonsense", log=NOOP)
    assert out["broker_parity_ok"] is None


# ── P&L of record ────────────────────────────────────────────────────────────────────
def test_pnl_of_record_uses_fills_and_backtest_alongside():
    t = _tid()
    out = _run(_row(t), [_broker(t, "OPEN", 100.30), _broker(t, "CLOSE", 98.80)],
               _eng(100.00, 99.00))
    assert out["pnl_record"] == pytest.approx(15.0)
    assert out["pnl_record_src"] == "webull"
    assert out["pnl_record_note"] == ""
    assert out["pnl_backtest"] == pytest.approx(10.0)


def test_pnl_of_record_unmarked_exit_uses_minute_close_labelled():
    t = _tid()
    row = _row(t, exit_px="nan", pnl="nan", real_exit_px="98.50", real_pnl="15.0")
    out = _run(row, [_broker(t, "OPEN", 100.10)], _eng(100.00, None))
    assert out["pnl_record"] == pytest.approx(round((98.50 - 100.10) * -10, 2))
    assert out["pnl_record_src"] == "part"
    assert "minute close" in out["pnl_record_note"]


def test_curve_pnl_prefers_pnl_record_then_book():
    assert qe._curve_pnl({"pnl_record": 6.0, "pnl": "-1.1"}) == 6.0
    assert qe._curve_pnl({"pnl_record": None, "pnl": "-1.1"}) == -1.1
    assert qe._curve_pnl({"pnl": "nan", "real_pnl": "0.65"}) == 0.65
    assert qe._curve_pnl_book({"pnl_record": 6.0, "pnl": "-1.1"}) == -1.1


# ── summary: window, rolling average, flags ─────────────────────────────────────────
def _fp_row(leg, exec_ps_per_fill, ts, flag=False, dsg=0.0):
    side = {"bt": 1.0, "wb": 1.0, "bk": 1.0, "fs": "ok", "edge": exec_ps_per_fill + dsg,
            "dsg": dsg, "slp": exec_ps_per_fill, "unx": 0.0, "why": ""}
    return {"leg": leg, "signal_source": "engine", "exit_ts": ts, "broker_parity_ok": not flag,
            "broker_parity_note": "n", "pnl_record": 1.0, "pnl_record_src": "webull",
            "pnl_backtest": 0.5,
            "fp": {"en": dict(side), "ex": dict(side), "exec_ps": 2 * exec_ps_per_fill,
                   "gap_ps": 2 * (exec_ps_per_fill + dsg), "dsg_ps": 2 * dsg, "flag": flag}}


def test_rolling_average_flags_at_minus_5_cents_per_fill_only_adverse():
    bad = [_fp_row("NOISE", -0.06, f"2026-09-{10 + i:02d} 10:00:00") for i in range(20)]
    s = qe._broker_parity_summary(bad)
    assert s["board"]["avg_exec_ps"] == pytest.approx(-0.06)
    assert s["board"]["fills"] == 40
    assert s["board_flag"] is True and s["legs"]["NOISE"]["flag"] is True
    fine = [_fp_row("NOISE", -0.04, f"2026-09-{10 + i:02d} 10:00:00") for i in range(20)]
    assert qe._broker_parity_summary(fine)["board_flag"] is False
    better = [_fp_row("NOISE", +0.30, f"2026-09-{10 + i:02d} 10:00:00") for i in range(20)]
    assert qe._broker_parity_summary(better)["board_flag"] is False


def test_rolling_window_is_the_last_20_by_exit_time():
    old_bad = [_fp_row("ORB", -0.50, f"2026-08-{10 + i:02d} 10:00:00", flag=True) for i in range(5)]
    new_ok = [_fp_row("ORB", 0.0, f"2026-09-{10 + i:02d} 10:00:00") for i in range(20)]
    s = qe._broker_parity_summary(list(reversed(old_bad + new_ok)))  # newest-first like the doc
    assert s["checked"] == 20 and s["failed"] == 0 and s["ok"] == 20
    assert s["flagged_all"] == 5 and s["checked_all"] == 25
    assert s["board_flag"] is False


def test_summary_counts_skip_ninjatrader_and_not_compared():
    rows = [_fp_row("NOISE", 0.0, "2026-09-28 10:00:00"),
            {"signal_source": "ninjatrader", "broker_parity_ok": False},
            {"signal_source": "engine", "broker_parity_ok": None, "fp": None}]
    s = qe._broker_parity_summary(rows)
    assert s["checked"] == 1 and s["not_checked"] == 1


def test_summary_all_not_compared_note_is_not_an_error():
    s = qe._broker_parity_summary([{"broker_parity_ok": None, "signal_source": "engine"}] * 3)
    assert s["checked"] == 0 and s["failed"] == 0
    assert "not an error" in s["note"]


def test_readiness_blocks_on_the_rolling_flag():
    feed = [{"valid": True, "uptime_pct": 1.0}] * 12
    parity = {"checked": 12, "failed": 0, "board_flag": True}
    r = qe._build_readiness(feed, parity, {"total": 0}, {"events": []}, log=NOOP)
    assert r["ready"] is False
    assert any("running average" in m for m in r["missing"])
    parity["board_flag"] = False
    assert qe._build_readiness(feed, parity, {"total": 0}, {"events": []}, log=NOOP)["ready"] is True


# ── helpers kept from feature #56 ────────────────────────────────────────────────────
def test_signal_id_base_strips_resend_suffix_only():
    assert qe._signal_id_base("qxORBR620260921T093100ZLOR2") == "qxORBR620260921T093100ZLO"
    assert qe._signal_id_base("qqqexec-ORB-x-OPEN-2") == "qqqexec-ORB-x-OPEN-2"


def test_apply_broker_parity_leaves_ninjatrader_rows_with_nt_parity_intact():
    nt_row = {"signal_source": "ninjatrader", "parity_ok": True, "parity_note": "", "pnl": "3.0"}
    t = _tid()
    rows = [dict(nt_row), _row(t)]
    qe._apply_broker_parity(rows, qe._broker_orders_by_base([_broker(t, "OPEN", 100.0),
                                                              _broker(t, "CLOSE", 99.0)]),
                            engine_px={t: _eng(100.0, 99.0)}, log=NOOP)
    assert rows[0]["parity_ok"] is True and rows[0]["parity_note"] == ""
    assert rows[0]["broker_parity_ok"] is None
    assert rows[0]["broker_parity_note"] == qe._NT_MIRROR_NOTE
    assert rows[0]["pnl_record"] == 3.0
    assert rows[1]["broker_parity_ok"] is True


# ── engine price ledger ──────────────────────────────────────────────────────────────
def test_engine_prices_by_trade_first_row_wins_void_kept_missing_file_empty(tmp_path):
    p = tmp_path / "signals.csv"
    p.write_text(
        "emitted_at,leg,event,side,ref_time,ref_price,shares,reason,bar_source,trade_id\n"
        "a,NOISE_382,SEED,,,,,,,\n"
        "b,NOISE_382,ENTRY,short,t1,100.5,135,decide_at_close,webull,T1\n"
        "c,NOISE_382,ENTRY,short,t1,999,135,,webull,T1\n"
        "d,NOISE_382,EXIT,short,t2,99.5,135,strategy_exit,webull,T1\n"
        "e,ENGUQ_335,VOID_ENTRY,long,t3,50,135,ghost,webull,T2\n", encoding="utf-8")
    qe._ENGINE_PX_CACHE["key"] = None
    out = qe._engine_prices_by_trade(path=str(p))
    assert out["T1"]["ENTRY"]["px"] == 100.5
    assert out["T1"]["EXIT"]["px"] == 99.5
    assert "decide_at_close" in out["T1"]["ENTRY"]["reason"]
    assert "VOID" in out["T2"] and "ENTRY" not in out["T2"]
    assert qe._engine_prices_by_trade(path=str(tmp_path / "nope.csv")) == {}
