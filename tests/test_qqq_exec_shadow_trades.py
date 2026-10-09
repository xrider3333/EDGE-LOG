"""SHADOW TRADES block (2026-10-09, MANAGER #87 (d)) -- api/qqq_exec.py _build_shadow_trades /
_fit_shadow_trades, the status doc's separate, display-only "shadow_trades" key for the WEBULL
PAPER board's "Shadow - not counted" fold.

The shadow legs (api/cloud_signal.py SHADOW_LEGS) write only to <state_dir>/shadow/signals.csv.
The block is built from that ledger with tools/shadow_legs_report.py's own read_rows/pair_trades,
priced at round(base_shares x size) shares, newest entry first, capped, and it never reaches
trades_all or any P&L/stat figure of the doc.

COVERS:
  1. the block is present with the contract's keys, separate from trades_all;
  2. the seeded flag (ENTRY reason starts "seeded=1");
  3. an open trade: mark_px from the doc's own price (positions_live, else the stream, else the
     newest closed bar), unreal_usd; no price anywhere -> both None;
  4. closed P&L sign, long and short;
  5. size scaling and the base_shares source (config, else the report's BASE_SHARES);
  6. the count cap and the Firestore-budget fit, both recorded in "capped", trades_all untouched,
     and neither ever cuts a still-open trade (ENGU-Q's old hold) while a closed one is left;
  7. a missing / garbage / unreadable (cannot be opened) ledger or a failing pairing -> "error",
     trades [], and the doc still builds;
  8. an unchanged ledger (and bar file) is not re-parsed;
  9. the shadow rows never appear in trades_all or change any other field of the doc.
"""
import csv
import json
import os
from datetime import datetime

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
import tools.shadow_legs_report as slr

NOOP = lambda *a, **k: None  # noqa: E731
DAY = "2026-10-08"
CFG = {"shares": {"ORB": 5, "ENGUQ": 10, "NOISE": 10}}
CONTRACT_KEYS = {"leg", "trade_id", "side", "entry_time", "entry_px", "exit_time", "exit_px",
                 "size", "shares", "seeded", "pnl_usd", "mark_px", "unreal_usd"}
SEED_TID = "ENGUQ_335-20260928T163200Z-L"
SEED_REASON = "seeded=1; open at this shadow leg's cold start, carried on 2026-10-08"


def _row(leg, event, ref_time, px, tid, side="long", size="", reason="", keel_size=""):
    return {"emitted_at": ref_time, "leg": leg, "event": event, "side": side,
            "ref_time": ref_time, "ref_price": px, "shares": "135", "reason": reason,
            "bar_source": "webull", "trade_id": tid, "size": size, "keel_size": keel_size}


def _trade(leg, tid, entry_time, entry_px, exit_time=None, exit_px=None, side="long", size="",
           reason="entry"):
    rows = [_row(leg, "ENTRY", entry_time, entry_px, tid, side=side, size=size, reason=reason)]
    if exit_time is not None:
        rows.append(_row(leg, "EXIT", exit_time, exit_px, tid, side=side, size=size, reason="exit"))
    return rows


def _write_ledger(path, rows, mode="w"):
    """The shadow ledger exactly as api/cloud_signal writes it: SIGNAL_COLS header."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = mode == "w" or not os.path.exists(path)
    with open(path, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS, restval="")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def _book_rows():
    """The box's own shape: ENGU-Q's seeded 09-28 long, now closed, plus NOISE_422 trades,
    a SEED row (no trade id) and one still-open NOISE_422_KEEL short."""
    rows = [_row("ENGUQ_335", "SEED", "", "", "", side="",
                 reason="cold start: absorbed 12 historical trade(s) without emitting")]
    rows += _trade("ENGUQ_335", SEED_TID, "2026-09-28T12:32:00-04:00", "738.0295",
                   "2026-10-08T13:01:00-04:00", "746.8612", reason=SEED_REASON)
    rows += _trade("NOISE_422_PLAIN", "NOISE_422_PLAIN-20261007T143500Z-S", "2026-10-07T10:35:00-04:00",
                   "741.00", "2026-10-07T11:10:00-04:00", "739.50", side="short", size="1.0")
    rows += _trade("NOISE_422_KEEL", "NOISE_422_KEEL-20261008T150500Z-S", "2026-10-08T11:05:00-04:00",
                   "747.20", side="short", size="1.37")
    return rows


@pytest.fixture
def box(tmp_path, monkeypatch):
    """Every file _build_doc reads -> tmp (the qqq_exec book AND cloud_signal's store, so the
    shadow ledger is <tmp>/home/cloud_signal/shadow/signals.csv); the slow or outside-world
    builders stubbed like tests/test_qqq_exec_ledger13.py. Returns a small helper object."""
    out = tmp_path / "qqq_exec_out"
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    home = tmp_path / "home"
    paths = cs._paths(home=str(home))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(qe, "_notify", NOOP)
    monkeypatch.setattr(qe, "_trade_parity", lambda row, log=print: {})
    monkeypatch.setattr(qe, "_load_reprice_sidecar", lambda log=print: {})
    monkeypatch.setattr(qe, "_engine_prices_by_trade", lambda *a, **k: {})
    monkeypatch.setattr(qe, "_build_price_status", lambda cfg, state, log=print: {})
    monkeypatch.setattr(qe, "_build_run_location", lambda: {})
    monkeypatch.setattr(qe, "_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {})
    monkeypatch.setattr(qe, "_build_broker_status", lambda state, log=print: {})
    monkeypatch.setattr(qe, "_build_trade_id_status", lambda state, day: {})
    monkeypatch.setattr(qe, "_build_keel_status", lambda log=print: {})
    live = {"legs": [], "total_open_pnl": 0.0, "legs_net_qty": 0, "broker_net_qty": None,
            "mismatch": False}
    monkeypatch.setattr(qe, "_build_positions_live", lambda state, cfg, log=print: live)
    qe._BREAKER_ADJ_CACHE["key"] = None
    monkeypatch.setattr(qe, "_SHADOW_TRADES_CACHE", {"key": None, "value": None, "logged": None})
    monkeypatch.setattr(qe, "_SHADOW_MARK_CACHE", {})

    class Box:
        ledger = cs.shadow_paths(paths)["signals_path"]
        ohlc_dir = paths["ohlc_dir"]
        positions_live = live

        def doc(self, cfg=CFG, state=None):
            st = {"trading_day": DAY, "legs": {}}
            st.update(state or {})
            return qe._build_doc(cfg, st, False, 0.0, log=NOOP)

        def ledger_rows(self, rows, mode="w"):
            _write_ledger(self.ledger, rows, mode=mode)

        def live_trades(self, rows):
            with open(qe.TRADES_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=qe.TRADE_COLS, restval="")
                w.writeheader()
                for r in rows:
                    w.writerow(r)

        def bars(self, tf, rows):
            os.makedirs(self.ohlc_dir, exist_ok=True)
            with open(os.path.join(self.ohlc_dir, f"QQQ_{tf}.csv"), "w", newline="",
                      encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["time", "open", "high", "low", "close", "volume"])
                for t, c in rows:
                    w.writerow([t, c, c, c, c, 1000])

    return Box()


def _by_tid(block):
    return {t["trade_id"]: t for t in block["trades"]}


LIVE_ROW = {"leg": "NOISE", "entry_ts": f"{DAY} 10:15:00", "exit_ts": f"{DAY} 11:40:00",
            "side": "long", "shares": "10", "entry_px": "745.00", "exit_px": "746.00", "pnl": "10.0",
            "exit_reason": "signal exit", "signal_source": "engine",
            "trade_id": "NOISE_382-20261008T141500Z-L"}


# ── 1. present, contract-shaped, separate from trades_all ──────────────────────────────────
def test_block_present_with_the_contract_keys_and_separate_from_trades_all(box):
    box.live_trades([LIVE_ROW])
    box.ledger_rows(_book_rows())
    doc = box.doc()
    st = doc["shadow_trades"]
    assert set(st) == {"as_of", "source", "base_shares", "legs", "capped", "trades"}
    assert st["source"] == "cloud_signal/shadow/signals.csv"
    assert datetime.fromisoformat(st["as_of"])
    assert st["base_shares"] == 10 and st["capped"] == 0
    # SHADOW_LEGS order, only legs with trades; the SEED row makes no trade
    assert st["legs"] == ["NOISE_422_PLAIN", "NOISE_422_KEEL", "ENGUQ_335"]
    assert len(st["trades"]) == 3
    assert all(set(t) == CONTRACT_KEYS for t in st["trades"])
    # newest ENTRY first
    assert [t["entry_time"] for t in st["trades"]] == sorted(
        (t["entry_time"] for t in st["trades"]), reverse=True)
    # trades_all is the live book only
    assert [r["trade_id"] for r in doc["trades_all"]] == [LIVE_ROW["trade_id"]]
    shadow_ids = {t["trade_id"] for t in st["trades"]}
    assert not shadow_ids & {r.get("trade_id") for r in doc["trades_all"]}
    json.dumps(st, allow_nan=False)   # publishable as-is
    # the box's ENGU-Q seed trade, closed 10-08: (746.8612 - 738.0295) x 10 = +88.32
    seed = _by_tid(st)[SEED_TID]
    assert seed["seeded"] is True and seed["shares"] == 10 and seed["size"] == 1.0
    assert seed["exit_time"] == "2026-10-08T13:01:00-04:00" and seed["exit_px"] == 746.8612
    assert seed["pnl_usd"] == 88.32 and seed["mark_px"] is None and seed["unreal_usd"] is None


def test_block_agrees_with_the_shadow_legs_report(box):
    """Same pairing, same dollars: the board's block and tools/shadow_legs_report.py's
    numbers come from the same functions (whole shares only differ for a fractional size)."""
    rows = _book_rows()
    rows += _trade("NOISE_422_FIXED", "NOISE_422_FIXED-20261006T150000Z-L", "2026-10-06T11:00:00-04:00",
                   "740.10", "2026-10-06T12:30:00-04:00", "742.35", size="2.0")
    box.ledger_rows(rows)
    st = box.doc()["shadow_trades"]
    rep = slr.pair_trades(slr.read_rows(box.ledger))
    for leg, trades in rep.items():
        for t in trades:
            mine = _by_tid(st)[t["trade_id"]]
            assert mine["leg"] == leg and mine["entry_px"] == t["entry_px"]
            assert mine["exit_px"] == t["exit_px"] and mine["seeded"] == t["seeded"]
            if t["exit_px"] is not None and float(t["size"]).is_integer():
                assert mine["pnl_usd"] == round(slr.trade_dollars(t, 10), 2)


# ── 2. seeded flag ─────────────────────────────────────────────────────────────────────────
def test_seeded_flag_reads_the_entry_reason_prefix(box):
    rows = _trade("ENGUQ_335", "E-1", "2026-09-28T12:32:00-04:00", "738.0295", reason=SEED_REASON)
    rows += _trade("ENGUQ_335", "E-2", "2026-10-01T10:00:00-04:00", "740.0",
                   "2026-10-01T11:00:00-04:00", "741.0", reason="engulfing long")
    rows += _trade("ENGUQ_335", "E-3", "2026-10-02T10:00:00-04:00", "740.0",
                   "2026-10-02T11:00:00-04:00", "741.0", reason="note: seeded=1 is not a prefix here")
    box.ledger_rows(rows)
    got = {tid: t["seeded"] for tid, t in _by_tid(box.doc()["shadow_trades"]).items()}
    assert got == {"E-1": True, "E-2": False, "E-3": False}


# ── 3. open trade: mark + unrealised ───────────────────────────────────────────────────────
def test_open_trade_marked_at_the_docs_own_live_price(box):
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-09-28T12:32:00-04:00", "738.0295",
                           reason=SEED_REASON)
                    + _trade("NOISE_422_PLAIN", "S-1", "2026-10-08T10:00:00-04:00", "750.00",
                             side="short"))
    box.positions_live["legs"] = [{"leg": "NOISE", "live_px": 746.8612, "live_source": "stream"}]
    st = box.doc()["shadow_trades"]
    long_, short = _by_tid(st)["L-1"], _by_tid(st)["S-1"]
    for t in (long_, short):
        assert t["exit_time"] is None and t["exit_px"] is None and t["pnl_usd"] is None
        assert t["mark_px"] == 746.8612
    assert long_["unreal_usd"] == 88.32               # (746.8612 - 738.0295) x 10
    assert short["unreal_usd"] == 31.39               # (750.00 - 746.8612) x 10, short


def test_open_trade_falls_back_to_the_newest_closed_bar(box):
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-10-08T10:00:00-04:00", "740.00"))
    box.bars("5m", [(1791460800, 744.0), (1791461100, 745.0)])
    box.bars("1m", [(1791461100, 745.0), (1791461340, 745.5)])   # the newer bar
    t = _by_tid(box.doc()["shadow_trades"])["L-1"]
    assert t["mark_px"] == 745.5 and t["unreal_usd"] == 55.0


class _Stream:
    def __init__(self, price, fresh=True):
        self._price, self._fresh = price, fresh

    def is_fresh(self):
        return self._fresh

    def last_trade(self):
        return {"price": self._price}   # a stale stream still has a print: it must not be used


class _BoomStream:
    def is_fresh(self):
        raise RuntimeError("stream boom")


def test_open_trade_marked_at_a_fresh_stream_print_before_the_bar_cache(box, monkeypatch):
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-10-08T10:00:00-04:00", "740.00"))
    box.bars("1m", [(1791461340, 745.5)])
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _Stream(744.0))
    monkeypatch.setattr(cs, "load_cached_bars", lambda *a, **k: pytest.fail("read the bar cache"))
    t = _by_tid(box.doc()["shadow_trades"])["L-1"]
    assert t["mark_px"] == 744.0 and t["unreal_usd"] == 40.0


@pytest.mark.parametrize("stream", [None, _Stream(744.0, fresh=False), _BoomStream()],
                         ids=["no-stream", "stale", "failing"])
def test_open_trade_skips_a_missing_stale_or_failing_stream_for_the_bar(box, monkeypatch, stream):
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-10-08T10:00:00-04:00", "740.00"))
    box.bars("1m", [(1791461340, 745.5)])
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: stream)
    st = box.doc()["shadow_trades"]
    t = _by_tid(st)["L-1"]
    assert t["mark_px"] == 745.5 and t["unreal_usd"] == 55.0 and "error" not in st


def test_open_trade_with_no_price_anywhere_is_unmarked(box):
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-10-08T10:00:00-04:00", "740.00"))
    st = box.doc()["shadow_trades"]
    t = _by_tid(st)["L-1"]
    assert t["mark_px"] is None and t["unreal_usd"] is None and t["pnl_usd"] is None
    assert "error" not in st


# ── 4. closed P&L sign ─────────────────────────────────────────────────────────────────────
def test_closed_pnl_sign_long_and_short(box):
    rows = _trade("NOISE_422_PLAIN", "LW", "2026-10-01T10:00:00-04:00", "100.00",
                  "2026-10-01T10:30:00-04:00", "101.25")
    rows += _trade("NOISE_422_PLAIN", "LL", "2026-10-02T10:00:00-04:00", "100.00",
                   "2026-10-02T10:30:00-04:00", "99.50")
    rows += _trade("NOISE_422_PLAIN", "SL", "2026-10-03T10:00:00-04:00", "100.00",
                   "2026-10-03T10:30:00-04:00", "101.25", side="short")
    rows += _trade("NOISE_422_PLAIN", "SW", "2026-10-04T10:00:00-04:00", "100.00",
                   "2026-10-04T10:30:00-04:00", "99.50", side="short")
    box.ledger_rows(rows)
    got = {tid: t["pnl_usd"] for tid, t in _by_tid(box.doc()["shadow_trades"]).items()}
    assert got == {"LW": 12.5, "LL": -5.0, "SL": -12.5, "SW": 5.0}


# ── 5. size scaling + base shares ──────────────────────────────────────────────────────────
def test_size_scales_whole_shares_and_pnl(box):
    rows = _trade("NOISE_422_KEEL", "K15", "2026-10-01T10:00:00-04:00", "100.00",
                  "2026-10-01T10:30:00-04:00", "102.00", size="1.5")
    rows += _trade("NOISE_422_KEEL", "K037", "2026-10-02T10:00:00-04:00", "100.00",
                   "2026-10-02T10:30:00-04:00", "102.00", size="0.37")
    rows += _trade("NOISE_422_PLAIN", "BLANK", "2026-10-03T10:00:00-04:00", "100.00",
                   "2026-10-03T10:30:00-04:00", "102.00", size="")
    box.ledger_rows(rows)
    got = _by_tid(box.doc()["shadow_trades"])
    assert (got["K15"]["size"], got["K15"]["shares"], got["K15"]["pnl_usd"]) == (1.5, 15, 30.0)
    assert (got["K037"]["size"], got["K037"]["shares"], got["K037"]["pnl_usd"]) == (0.37, 4, 8.0)
    assert (got["BLANK"]["size"], got["BLANK"]["shares"], got["BLANK"]["pnl_usd"]) == (1.0, 10, 20.0)
    assert all(isinstance(t["shares"], int) and isinstance(t["size"], float) for t in got.values())


def test_base_shares_from_config_else_the_reports_default(box):
    box.ledger_rows(_trade("ENGUQ_335", "E-1", "2026-10-01T10:00:00-04:00", "100.00",
                           "2026-10-01T10:30:00-04:00", "101.00"))
    st = box.doc(cfg={"shares": {"ENGUQ": 7, "NOISE": 10}})["shadow_trades"]
    assert st["base_shares"] == 7 and st["trades"][0]["shares"] == 7 and st["trades"][0]["pnl_usd"] == 7.0
    st = box.doc(cfg={"shares": {"ENGUQ": 0, "NOISE": 12}})["shadow_trades"]
    assert st["base_shares"] == 12
    st = box.doc(cfg={})["shadow_trades"]
    assert st["base_shares"] == slr.BASE_SHARES == 10 and st["trades"][0]["pnl_usd"] == 10.0


# ── 6. cap + budget ────────────────────────────────────────────────────────────────────────
def test_count_cap_keeps_the_newest_and_records_capped(box, monkeypatch):
    monkeypatch.setattr(qe, "SHADOW_TRADES_CAP", 5)
    rows = []
    for i in range(8):
        rows += _trade("NOISE_422_PLAIN", f"T{i}", f"2026-10-0{i + 1}T10:00:00-04:00", "100.00",
                       f"2026-10-0{i + 1}T10:30:00-04:00", "101.00")
    box.ledger_rows(rows)
    st = box.doc()["shadow_trades"]
    assert [t["trade_id"] for t in st["trades"]] == ["T7", "T6", "T5", "T4", "T3"]
    assert st["capped"] == 3 and st["legs"] == ["NOISE_422_PLAIN"]


def test_budget_fit_drops_only_the_blocks_own_oldest_trades(monkeypatch):
    trades_all = [{"trade_id": f"LIVE-{i}", "pnl": "1.0", "note": "x" * 50} for i in range(20)]
    doc = {"trades_all": [dict(r) for r in trades_all], "trades_all_trimmed": 0}
    rows = [{k: None for k in CONTRACT_KEYS} | {"trade_id": f"SH-{i}", "leg": "NOISE_422_PLAIN"}
            for i in range(10)]
    block = {"as_of": "2026-10-09T10:00:00-04:00", "source": qe.SHADOW_TRADES_SOURCE,
             "base_shares": 10, "legs": ["NOISE_422_PLAIN"], "capped": 2, "trades": list(rows)}
    full = qe._fs_size(doc) + 232 + len("shadow_trades") + 1 + qe._fs_size(block)
    monkeypatch.setattr(qe, "FS_DOC_BUDGET_BYTES", full - 3 * qe._fs_size(rows[0]) + 1)
    logs = []
    qe._fit_shadow_trades(doc, block, log=logs.append)
    st = doc["shadow_trades"]
    assert [t["trade_id"] for t in st["trades"]] == [f"SH-{i}" for i in range(7)]
    assert st["capped"] == 2 + 3
    assert doc["trades_all"] == trades_all and doc["trades_all_trimmed"] == 0
    assert logs and "trades_all untouched" in logs[0]


def test_count_cap_never_drops_a_still_open_trade(box, monkeypatch):
    """ENGU-Q's multi-day hold has the OLDEST entry in the ledger: a plain newest-first cut
    would drop exactly the trade the leg still holds, and the board would show it flat."""
    monkeypatch.setattr(qe, "SHADOW_TRADES_CAP", 5)
    rows = _trade("ENGUQ_335", SEED_TID, "2026-09-28T12:32:00-04:00", "738.0295", reason=SEED_REASON)
    for i in range(8):
        rows += _trade("NOISE_422_PLAIN", f"T{i}", f"2026-10-0{i + 1}T10:00:00-04:00", "100.00",
                       f"2026-10-0{i + 1}T10:30:00-04:00", "101.00")
    box.ledger_rows(rows)
    box.positions_live["legs"] = [{"live_px": 751.73}]
    st = box.doc()["shadow_trades"]
    assert [t["trade_id"] for t in st["trades"]] == ["T7", "T6", "T5", "T4", SEED_TID]
    assert st["capped"] == 4 and st["legs"] == ["NOISE_422_PLAIN", "ENGUQ_335"]
    seed = st["trades"][-1]
    assert seed["exit_time"] is None and seed["seeded"] is True
    assert seed["mark_px"] == 751.73 and seed["unreal_usd"] == 137.01


def test_cap_keeps_the_newest_open_trades_when_open_alone_exceed_it():
    trades = [{"trade_id": f"O{i}", "exit_time": None} for i in range(4)]
    trades.insert(1, {"trade_id": "C", "exit_time": "2026-10-08T11:00:00-04:00"})
    assert [t["trade_id"] for t in qe._cap_shadow_trades(trades, 3)] == ["O0", "O1", "O2"]
    assert qe._cap_shadow_trades(trades, 300) == trades


def test_budget_fit_drops_closed_trades_before_a_still_open_one(monkeypatch):
    doc = {"trades_all": [], "trades_all_trimmed": 0}
    rows = [{k: None for k in CONTRACT_KEYS} | {"trade_id": f"SH-{i}", "leg": "NOISE_422_PLAIN",
                                               "exit_time": "2026-10-08T11:00:00-04:00"}
            for i in range(9)]
    # newest entry first, so the open seeded hold (the oldest entry) is the LAST row
    rows.append({k: None for k in CONTRACT_KEYS} | {"trade_id": SEED_TID, "leg": "ENGUQ_335",
                                                   "seeded": True})
    block = {"as_of": "2026-10-09T10:00:00-04:00", "source": qe.SHADOW_TRADES_SOURCE,
             "base_shares": 10, "legs": ["NOISE_422_PLAIN", "ENGUQ_335"], "capped": 0,
             "trades": list(rows)}
    full = qe._fs_size(doc) + 232 + len("shadow_trades") + 1 + qe._fs_size(block)
    monkeypatch.setattr(qe, "FS_DOC_BUDGET_BYTES", full - 3 * qe._fs_size(rows[0]) + 1)
    qe._fit_shadow_trades(doc, block, log=NOOP)
    st = doc["shadow_trades"]
    assert [t["trade_id"] for t in st["trades"]] == [f"SH-{i}" for i in range(6)] + [SEED_TID]
    assert st["capped"] == 3 and "error" not in st


def test_budget_trim_of_trades_all_is_the_same_with_or_without_the_shadow_block(box, monkeypatch):
    """trades_all's own budget fit runs before the block exists: the shadow ledger can never
    cost trades_all a row."""
    live = []
    for i in range(30):
        live.append(dict(LIVE_ROW, trade_id=f"NOISE_382-202610{i:02d}-L", exit_ts=f"{DAY} 11:{i:02d}:00"))
    box.live_trades(live)
    probe = box.doc()
    base = qe._fs_size({k: v for k, v in probe.items() if k != "shadow_trades"}) + 232
    monkeypatch.setattr(qe, "FS_DOC_BUDGET_BYTES", base - 2000)   # forces a trades_all trim
    without = box.doc()
    rows = []
    for i in range(40):
        rows += _trade("NOISE_422_PLAIN", f"T{i:02d}", f"2026-10-01T10:{i:02d}:00-04:00", "100.00",
                       f"2026-10-01T11:{i:02d}:00-04:00", "101.00")
    box.ledger_rows(rows)
    with_ = box.doc()
    assert with_["trades_all_trimmed"] == without["trades_all_trimmed"] > 0
    assert with_["trades_all"] == without["trades_all"]
    # the block only gets what trades_all left: its own oldest trades dropped and counted
    st = with_["shadow_trades"]
    assert len(st["trades"]) < 40 and st["capped"] == 40 - len(st["trades"]) and "error" not in st
    assert [t["trade_id"] for t in st["trades"]] == [f"T{i:02d}" for i in range(39, 39 - len(st["trades"]), -1)]


def test_a_full_cap_block_estimate_fits_the_firestore_caps():
    """~300 bytes / 15 index entries a trade: the 300-trade cap is well inside the doc's
    budget beside a full trades_all (~565 KB at 500 rows, see FS_DOC_BUDGET_BYTES)."""
    t = {"leg": "NOISE_422_KEEL", "trade_id": "NOISE_422_KEEL-20261008T150500Z-S", "side": "short",
         "entry_time": "2026-10-08T11:05:00-04:00", "entry_px": 747.2,
         "exit_time": "2026-10-08T15:55:00-04:00", "exit_px": 745.1, "size": 1.37, "shares": 14,
         "seeded": False, "pnl_usd": 29.4, "mark_px": None, "unreal_usd": None}
    block = {"as_of": "2026-10-09T10:00:00-04:00", "source": qe.SHADOW_TRADES_SOURCE,
             "base_shares": 10, "legs": list(cs.SHADOW_LEGS), "capped": 0,
             "trades": [dict(t) for _ in range(qe.SHADOW_TRADES_CAP)]}
    assert qe._fs_size(block) < 100_000
    assert qe._fs_leaves(block) <= 15 * qe.SHADOW_TRADES_CAP + 20


# ── 7. missing / garbage / failing -> error, the doc still builds ──────────────────────────
def _assert_error_block(doc, needle):
    st = doc["shadow_trades"]
    assert st["trades"] == [] and needle in st["error"]
    assert {"as_of", "source", "base_shares", "legs", "capped"} <= set(st)
    assert isinstance(doc["trades_all"], list) and "cum_pnl" in doc and "readiness" in doc


def test_missing_ledger_is_an_error_and_the_doc_builds(box):
    box.live_trades([LIVE_ROW])
    doc = box.doc()
    _assert_error_block(doc, "not found")
    assert len(doc["trades_all"]) == 1


def test_garbage_text_ledger_is_an_error(box):
    os.makedirs(os.path.dirname(box.ledger), exist_ok=True)
    with open(box.ledger, "w", encoding="utf-8") as f:
        f.write("this is not,a signals ledger\n1,2\n{json: maybe}\n")
    _assert_error_block(box.doc(), "header not recognised")


def test_binary_garbage_ledger_is_an_error(box):
    os.makedirs(os.path.dirname(box.ledger), exist_ok=True)
    with open(box.ledger, "wb") as f:
        f.write(b"\xff\xfe\x00\x81garbage\x00\x9c" * 50)
    _assert_error_block(box.doc(), "unreadable")


def test_a_ledger_that_cannot_be_opened_is_an_error_not_an_empty_list(box):
    """read_rows(strict=True) re-raises the OSError: a ledger path that stats but cannot be
    opened (here a directory) says so, instead of publishing as if the ledger were empty."""
    os.makedirs(box.ledger)
    doc = box.doc()
    _assert_error_block(doc, "unreadable")
    assert doc["shadow_trades"]["error"].startswith("shadow ledger unreadable (")


def test_a_failing_pairing_or_report_import_is_an_error(box, monkeypatch):
    box.ledger_rows(_book_rows())

    def boom(*a, **k):
        raise RuntimeError("pairing exploded")
    monkeypatch.setattr(slr, "pair_trades", boom)
    _assert_error_block(box.doc(), "pairing exploded")


def test_a_report_module_that_will_not_import_is_an_error(box, monkeypatch):
    box.ledger_rows(_book_rows())

    def no_module():
        raise ImportError("no tools.shadow_legs_report here")
    monkeypatch.setattr(qe, "_shadow_report", no_module)
    doc = box.doc()
    _assert_error_block(doc, "ImportError")
    assert doc["shadow_trades"]["base_shares"] == qe.SHADOW_BASE_SHARES_FALLBACK


def test_a_failing_fit_publishes_the_error_form(box, monkeypatch):
    box.ledger_rows(_book_rows())
    real = qe._fs_size

    def picky(v):
        if isinstance(v, dict) and "base_shares" in v:
            raise ValueError("size probe failed")
        return real(v)
    monkeypatch.setattr(qe, "_fs_size", picky)
    _assert_error_block(box.doc(), "size probe failed")


# ── 8. cache ───────────────────────────────────────────────────────────────────────────────
def test_unchanged_ledger_is_not_reparsed(box, monkeypatch):
    calls = []
    real = slr.read_rows

    def counting(path, strict=False):
        calls.append(path)
        return real(path, strict=strict)
    monkeypatch.setattr(slr, "read_rows", counting)
    box.ledger_rows(_book_rows())
    first = box.doc()["shadow_trades"]
    second = box.doc()["shadow_trades"]
    third = box.doc()["shadow_trades"]
    assert len(calls) == 1
    assert first["trades"] == second["trades"] == third["trades"]
    # the ledger grows (a new ENTRY) -> read once more, the new trade shows
    box.ledger_rows(_trade("NOISE_422_FIXED", "NEW-1", "2026-10-09T09:45:00-04:00", "748.00"),
                    mode="a")
    fourth = box.doc()["shadow_trades"]
    assert len(calls) == 2 and fourth["trades"][0]["trade_id"] == "NEW-1"
    box.doc()
    assert len(calls) == 2


def test_cached_value_is_not_mutated_by_a_build(box):
    """Each build makes fresh rows: a mark on one tick is never left in the cache."""
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-10-08T10:00:00-04:00", "740.00"))
    box.positions_live["legs"] = [{"live_px": 741.0}]
    assert _by_tid(box.doc()["shadow_trades"])["L-1"]["unreal_usd"] == 10.0
    box.positions_live["legs"] = []
    t = _by_tid(box.doc()["shadow_trades"])["L-1"]
    assert t["mark_px"] is None and t["unreal_usd"] is None


def test_unchanged_bar_file_is_not_reread_for_the_mark(box, monkeypatch):
    box.ledger_rows(_trade("ENGUQ_335", "L-1", "2026-10-08T10:00:00-04:00", "740.00"))
    box.bars("1m", [(1791461340, 745.5)])
    loads = []
    real = cs.load_cached_bars

    def counting(tf, paths=None):
        loads.append(tf)
        return real(tf, paths)
    monkeypatch.setattr(cs, "load_cached_bars", counting)
    for _ in range(3):
        assert _by_tid(box.doc()["shadow_trades"])["L-1"]["mark_px"] == 745.5
    assert loads == ["1m"]


def test_no_open_trade_reads_no_price_at_all(box, monkeypatch):
    box.ledger_rows(_trade("NOISE_422_PLAIN", "C-1", "2026-10-01T10:00:00-04:00", "100.00",
                           "2026-10-01T10:30:00-04:00", "101.00"))
    box.bars("1m", [(1791461340, 745.5)])
    monkeypatch.setattr(cs, "load_cached_bars", lambda *a, **k: pytest.fail("read bars"))
    assert box.doc()["shadow_trades"]["trades"][0]["pnl_usd"] == 10.0


# ── 9. never counted ───────────────────────────────────────────────────────────────────────
def _comparable(doc):
    d = {k: v for k, v in doc.items() if k not in ("shadow_trades", "updated_at", "lease")}
    return json.loads(json.dumps(d, default=str, sort_keys=True))


def test_shadow_rows_never_reach_trades_all_or_any_pnl_or_stat_field(box):
    """The whole doc, minus its own clock fields and the block itself, is identical with and
    without a busy shadow ledger -- trades_all, cum_pnl, today (P&L of record, legs_record,
    breaker input), positions, parity, book-only, readiness, rails ... -- and trades.csv is
    not written."""
    box.live_trades([LIVE_ROW])
    with open(qe.TRADES_CSV, "rb") as f:
        trades_csv = f.read()
    without = box.doc()
    rows = _book_rows()
    for i in range(25):
        rows += _trade("NOISE_422_PLAIN", f"NOISE_422_PLAIN-{i:02d}", f"{DAY}T10:{i:02d}:00-04:00",
                       "700.00", f"{DAY}T11:{i:02d}:00-04:00", "760.00")
    box.ledger_rows(rows)
    with_ = box.doc()
    assert len(with_["shadow_trades"]["trades"]) == 28
    assert _comparable(with_) == _comparable(without)
    assert [r["trade_id"] for r in with_["trades_all"]] == [LIVE_ROW["trade_id"]]
    assert with_["today"]["realized_pnl_record"] == without["today"]["realized_pnl_record"] == 10.0
    with open(qe.TRADES_CSV, "rb") as f:
        assert f.read() == trades_csv
    blob = json.dumps(_comparable(with_))
    assert "NOISE_422" not in blob and "ENGUQ_335-2026" not in blob
