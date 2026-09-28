"""tools/qqq_reprice.py -- WEBULL FILLS FIRST (owner decision 2026-09-28 (C)) and the
fill-vs-tape range check (audit item E). A side with a captured Webull fill is priced
at it (no slippage charged); only a side without one falls back to the minute close,
labelled per side; a fill outside what traded in its minute is marked suspect and not
used. Same network discipline as tests/test_qqq_reprice.py: every run() gets a
webull_keys_path that does not exist and a stream_home under tmp_path, and yfinance is
monkeypatched away.
"""
import csv
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.qqq_reprice as R

FIX = os.path.join(ROOT, "tests", "fixtures", "parity0928")
NOOP = lambda *a, **k: None  # noqa: E731


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """A copy of the real 09-28 trades.csv / broker_orders.csv, the box's 1-minute
    stream bars for 09-24 and 09-28 under a fake EDGELOG home, and an EMPTY sidecar."""
    d = tmp_path / "qqq_exec"
    d.mkdir()
    for f in ("trades.csv", "broker_orders.csv"):
        shutil.copy(os.path.join(FIX, f), d / f)
    home = tmp_path / "home"
    (home / "ohlc_stream").mkdir(parents=True)
    shutil.copy(os.path.join(FIX, "QQQ_1m.csv"), home / "ohlc_stream" / "QQQ_1m.csv")
    (d / "config.json").write_text('{"slippage_per_share": 0.01}', encoding="utf-8")
    monkeypatch.setattr(R, "fetch_day_bars", lambda day, log=print: None)
    return {"dir": str(d), "home": str(home), "keys": str(tmp_path / "no_keys.json"),
            "tok": str(tmp_path / "tok")}


def _run(rig, sidecar=None, force=False, broker_orders_csv=None):
    d = rig["dir"]
    sc = sidecar or os.path.join(d, "reprice.csv")
    R.run(os.path.join(d, "trades.csv"), sc, os.path.join(d, "config.json"), apply=True,
          force=force, stream_home=rig["home"], webull_keys_path=rig["keys"],
          webull_token_dir=rig["tok"], log=NOOP, broker_orders_csv=broker_orders_csv)
    with open(sc, encoding="utf-8", newline="") as f:
        return {(r["leg"], r["entry_ts"]): r for r in csv.DictReader(f)}


def test_both_sides_filled_use_the_fills_and_no_slippage(rig):
    out = _run(rig)
    orb = out[("ORB", "2026-09-28 10:50:06")]
    assert orb["price_source"] == "webull_fill"
    assert orb["entry_px_source"] == "webull_fill" and orb["exit_px_source"] == "webull_fill"
    assert float(orb["real_entry_px"]) == pytest.approx(732.58)
    assert float(orb["real_exit_px"]) == pytest.approx(736.57)
    assert float(orb["real_pnl"]) == pytest.approx(-39.90)   # was -37.60 from minute closes
    noise = out[("NOISE", "2026-09-28 10:15:11")]
    assert float(noise["real_pnl"]) == pytest.approx(6.00)   # was +22.00
    enguq = out[("ENGUQ", "2026-09-28 12:33:38")]
    assert float(enguq["real_exit_px"]) == pytest.approx(736.58)  # the R1 resend, not the refusal
    assert noise["entry_fill_check"] == "ok"


def test_suspect_fill_falls_back_to_the_minute_close_labelled(rig):
    out = _run(rig)
    r = out[("ENGUQ", "2026-09-24 12:18:25")]
    assert r["entry_fill_check"] == "suspect"
    assert r["entry_px_source"] == R.SOURCE_STREAM          # minute close, labelled
    assert r["exit_px_source"] == "webull_fill"
    assert r["price_source"] == "webull_fill+" + R.SOURCE_STREAM
    assert float(r["real_entry_px"]) == pytest.approx(739.49)   # the 12:18 bar's close
    assert "737.88" in r["note"] and "outside" in r["note"]
    # one minute-close side -> one side of slippage: (741.32-739.49)*10 - 0.01*10
    assert float(r["real_pnl"]) == pytest.approx(round((741.32 - 739.49) * 10 - 0.10, 2))


def test_no_fill_on_record_prices_from_bars_as_before(rig, tmp_path):
    empty = tmp_path / "no_broker_orders.csv"
    out = _run(rig, broker_orders_csv=str(empty))
    orb = out[("ORB", "2026-09-28 10:50:06")]
    assert orb["price_source"] == R.SOURCE_STREAM
    assert orb["entry_px_source"] == R.SOURCE_STREAM
    assert orb["entry_fill_check"] == ""


def test_old_minute_close_rows_upgrade_to_fills_without_force(rig):
    """The box's own 09-28 reprice.csv (written before this change) priced ORB at the
    minute closes (-37.60). The next plain run re-prices it at the fills; a row already
    written by the new code is left alone."""
    sc = os.path.join(rig["dir"], "reprice.csv")
    shutil.copy(os.path.join(FIX, "reprice.csv"), sc)
    out = _run(rig, sidecar=sc)
    assert float(out[("ORB", "2026-09-28 10:50:06")]["real_pnl"]) == pytest.approx(-39.90)
    stamp = out[("ORB", "2026-09-28 10:50:06")]["repriced_at"]
    out2 = _run(rig, sidecar=sc)
    assert out2[("ORB", "2026-09-28 10:50:06")]["repriced_at"] == stamp
    # a pre-trade-id row with no fill keeps its old minute-close pricing untouched
    old = [k for k, v in out2.items() if not v.get("entry_px_source")]
    assert old, "rows with no fill on record are not re-priced"


def test_read_broker_fills_last_ok_attempt_wins():
    fills = R.read_broker_fills(os.path.join(FIX, "broker_orders.csv"))
    assert fills["qxENGUQ33520260928T163200ZLC"] == pytest.approx(736.58)
    assert R._signal_base("ENGUQ_335-20260928T163200Z-L", "CLOSE") == "qxENGUQ33520260928T163200ZLC"
    assert "qxNOISE30420260923T140500ZSO" not in fills     # refused by Webull, no fill


def test_check_fill_range():
    from datetime import datetime
    day = "2026-09-24"
    ranges = {day: {datetime(2026, 9, 24, 12, 18): (739.45, 740.77),
                    datetime(2026, 9, 24, 12, 19): (738.77, 739.85)}}
    ts = datetime(2026, 9, 24, 12, 18, 26)
    assert R.check_fill(ranges, ts, 737.88)[0] == "suspect"
    assert R.check_fill(ranges, ts, 739.00)[0] == "ok"
    assert R.check_fill(ranges, ts, 738.76)[0] == "ok"       # within the 2-cent tolerance
    assert R.check_fill({}, ts, 737.88) == ("", "")


def test_suspect_list_matches_the_exec_and_holds_without_the_stream_day():
    """The box's rolling 1-minute file holds about three sessions: once 09-24 rolls off,
    the range check alone could no longer see that the 09-24 ENGU-Q capture is wrong (it
    would return "not checked" and the fill would be used). The known-suspect list, kept
    in step with api/qqq_exec.py, marks it regardless."""
    from api import qqq_exec as qe
    assert set(R.SUSPECT_BROKER_FILLS) == set(qe.SUSPECT_BROKER_FILLS)
    fills = R.read_broker_fills(os.path.join(FIX, "broker_orders.csv"))
    trade = {"trade_id": "ENGUQ_335-20260924T161700Z-L", "entry_ts": "2026-09-24 12:18:25",
             "exit_ts": "2026-09-24 15:59:00"}
    use, checks, notes = R._fill_plan(trade, fills, {})    # no stream bars for 09-24 at all
    assert checks["entry"] == "suspect" and "entry" not in use
    assert any("known-suspect" in n for n in notes)
    assert use["exit"] == pytest.approx(741.32)              # the other side is fine


def test_fill_check_runs_at_the_winning_resends_own_time():
    """A resend can go out minutes after the first try: the range check reads the minute
    the fill actually used was SENT, not the trade's first-attempt time."""
    from datetime import datetime
    day = "2026-09-28"
    ranges = {day: {datetime(2026, 9, 28, 15, 59): (736.00, 736.40),
                    datetime(2026, 9, 28, 16, 0): (736.10, 736.30),
                    datetime(2026, 9, 28, 16, 3): (736.60, 736.90)}}
    trade = {"trade_id": "ENGUQ_335-20260928T163200Z-L", "entry_ts": "2026-09-28 12:33:38",
             "exit_ts": "2026-09-28 15:59:01"}
    base = R._signal_base(trade["trade_id"], "CLOSE")
    fills = {base: 736.75}
    # judged at the trade's own exit minute the resend's fill would look wrong...
    _use, checks, _n = R._fill_plan(trade, fills, ranges)
    assert checks["exit"] == "suspect"
    # ...at the resend's own send time (16:03) it fits the tape and is used
    use, checks, _n = R._fill_plan(trade, fills, ranges, {base: "2026-09-28 16:03:10"})
    assert checks["exit"] == "ok" and use["exit"] == pytest.approx(736.75)


def test_read_broker_fills_reports_the_winning_attempts_time():
    times = {}
    R.read_broker_fills(os.path.join(FIX, "broker_orders.csv"), times=times)
    assert times["qxENGUQ33520260928T163200ZLC"] == "2026-09-28 15:59:06"   # the R1 resend
