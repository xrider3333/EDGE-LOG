"""Tests for tools/reconcile.py — the EDGELOG ↔ TradingView / NinjaTrader blotter
reconciler. Builds tiny synthetic TV/NT exports (no real data files, no streamlit) and
checks the parsers, the timezone-offset detector, the matcher, and the diagnosis engine.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import reconcile as R  # noqa: E402


# ── Realistic export fixtures ────────────────────────────────────────────────
TV_CSV = (
    "Trade #,Type,Date/Time,Signal,Price USD,Position size (qty),"
    "Net P&L USD,Net P&L %,Cumulative P&L USD,Cumulative P&L %\n"
    "3,Exit short,2026-05-05 15:55,Close,27912.50,1,\"1,029.34\",3.62,\"858.02\",3.0\n"
    "3,Entry short,2026-05-05 09:45,Short,27963.75,1,,,,\n"
    "2,Exit long,2026-05-04 11:20,Stop,27502.00,1,\"(1,201.91)\",-4.2,\"(171.32)\",-0.6\n"
    "2,Entry long,2026-05-04 09:45,Long,27562.00,1,,,,\n"
    "1,Exit long,2026-05-01 10:00,Close,27837.25,1,839.34,3.04,\"1,030.59\",3.7\n"
    "1,Entry long,2026-05-01 09:50,Long,27795.00,1,,,,\n"
)

NT_CSV = (
    "Trade number;Instrument;Market pos.;Quantity;Entry price;Exit price;"
    "Entry time;Exit time;Profit;Cum. net profit;Commission\n"
    "1;NQ 06-26;Long;1;27795.00;27837.25;5/1/2026 9:50:00 AM;5/1/2026 10:00:00 AM;$839.34;$839.34;$5.66\n"
    "2;NQ 06-26;Long;1;27562.00;27502.00;5/4/2026 9:45:00 AM;5/4/2026 11:20:00 AM;($1,201.91);($362.57);$5.66\n"
    "3;NQ 06-26;Short;1;27963.75;27912.50;5/5/2026 9:45:00 AM;5/5/2026 3:55:00 PM;$1,029.34;$666.77;$5.66\n"
)


@pytest.fixture
def tv_file(tmp_path):
    p = tmp_path / "tv.csv"
    p.write_text(TV_CSV, encoding="utf-8")
    return str(p)


@pytest.fixture
def nt_file(tmp_path):
    p = tmp_path / "nt.csv"
    p.write_text(NT_CSV, encoding="utf-8")
    return str(p)


def _mk(entry, side, pnl, entry_px=None):
    """A minimal EDGELOG-side Trade at an ET wall-clock entry time."""
    return R.Trade(entry_dt=pd.Timestamp(entry), exit_dt=None, side=side,
                   entry_px=entry_px, pnl_usd=pnl)


# ── _num numeric cleaner ─────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("$1,234.50", 1234.50), ("(50.00)", -50.0), ("1.2%", 1.2),
    ("—", None), ("", None), ("−12.5", -12.5), (42, 42.0),
])
def test_num_cleaner(raw, expected):
    assert R._num(raw) == expected


# ── TradingView parser ───────────────────────────────────────────────────────
def test_parse_tv_pairs_entry_and_exit_rows(tv_file):
    trades, meta = R.parse_tv(tv_file, mult=20)
    assert meta["num_trades"] == 3
    # sorted ascending by entry time; two rows/trade collapsed into one Trade
    t0 = trades[0]
    assert t0.entry_dt == pd.Timestamp("2026-05-01 09:50")
    assert t0.exit_dt == pd.Timestamp("2026-05-01 10:00")
    assert t0.side == 1 and t0.entry_px == 27795.00 and t0.exit_px == 27837.25
    assert t0.pnl_usd == pytest.approx(839.34)
    # quoted-comma + parentheses-negative on trade #2
    t1 = trades[1]
    assert t1.side == 1 and t1.pnl_usd == pytest.approx(-1201.91)
    # short trade parsed from "Entry short"
    assert trades[2].side == -1 and trades[2].pnl_usd == pytest.approx(1029.34)


# ── NinjaTrader parser ───────────────────────────────────────────────────────
def test_parse_nt_semicolon_currency_ampm(nt_file):
    trades, meta = R.parse_nt(nt_file, mult=20)
    assert meta["num_trades"] == 3
    t = trades[0]
    assert t.entry_dt == pd.Timestamp("2026-05-01 09:50")
    assert t.side == 1 and t.pnl_usd == pytest.approx(839.34)
    # parentheses currency → negative
    assert trades[1].pnl_usd == pytest.approx(-1201.91)
    # 3:55 PM parsed to 15:55, Short side
    assert trades[2].exit_dt == pd.Timestamp("2026-05-05 15:55")
    assert trades[2].side == -1


# ── TV and NT describe the SAME three trades → they reconcile to each other ───
def test_tv_and_nt_agree(tv_file, nt_file):
    tv, _ = R.parse_tv(tv_file, 20)
    nt, _ = R.parse_nt(nt_file, 20)
    off = R.best_offset(tv, nt, tol_min=10)
    matched, ua, ub = R.match(tv, nt, off, tol_min=10)
    assert off == 0 and len(matched) == 3 and not ua and not ub


# ── Offset detector: a whole-hour tz shift is recovered, not flagged as mismatch ─
def test_offset_detection_recovers_tz_shift():
    a = [_mk("2026-05-01 09:45", 1, 100.0), _mk("2026-05-02 09:45", -1, -50.0),
         _mk("2026-05-03 10:15", 1, 200.0)]
    b = [R.Trade(entry_dt=t.entry_dt + pd.Timedelta(hours=4), exit_dt=None,
                 side=t.side, pnl_usd=t.pnl_usd) for t in a]
    off = R.best_offset(a, b, tol_min=10)
    assert off == 240
    matched, ua, ub = R.match(a, b, off, tol_min=10)
    assert len(matched) == 3 and not ua and not ub


# ── Diagnosis: a constant per-trade $5.66 gap is named as FEES ────────────────
def test_diagnose_flags_fee_gap():
    a = [_mk("2026-05-01 09:45", 1, 100.0), _mk("2026-05-02 09:45", -1, -50.0),
         _mk("2026-05-03 09:45", 1, 200.0), _mk("2026-05-04 09:45", 1, 30.0)]
    b = [R.Trade(entry_dt=t.entry_dt, exit_dt=None, side=t.side,
                 pnl_usd=t.pnl_usd - 5.66) for t in a]
    matched, ua, ub = R.match(a, b, 0, tol_min=10)
    tags = {tag for tag, _ in R.diagnose(matched, ua, ub, 0, "EDGELOG", "TV", 10)}
    assert "FEES" in tags


# ── Diagnosis: an extra ETH (outside 09:30–16:00) trade on one side is flagged ─
def test_diagnose_flags_eth_extra():
    a = [_mk("2026-05-01 09:45", 1, 100.0), _mk("2026-05-02 09:45", -1, -50.0)]
    b = [R.Trade(entry_dt=t.entry_dt, exit_dt=None, side=t.side, pnl_usd=t.pnl_usd) for t in a]
    b.append(_mk("2026-05-02 04:30", 1, 75.0))   # pre-market ETH breakout
    matched, ua, ub = R.match(a, b, 0, tol_min=10)
    findings = R.diagnose(matched, ua, ub, 0, "EDGELOG", "TV", 10)
    text = " ".join(m for _, m in findings)
    assert any(tag == "UNMATCHED" for tag, _ in findings)
    assert "extended-hours" in text or "ETH" in text


# ── Diagnosis: identical blotters report CLEAN ───────────────────────────────
def test_diagnose_clean_when_identical():
    a = [_mk("2026-05-01 09:45", 1, 100.0, 27795.0), _mk("2026-05-02 09:45", -1, -50.0, 27800.0)]
    b = [R.Trade(entry_dt=t.entry_dt, exit_dt=None, side=t.side,
                 entry_px=t.entry_px, pnl_usd=t.pnl_usd) for t in a]
    matched, ua, ub = R.match(a, b, 0, tol_min=10)
    tags = {tag for tag, _ in R.diagnose(matched, ua, ub, 0, "EDGELOG", "TV", 10)}
    assert tags == {"CLEAN"}
