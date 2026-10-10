"""tools/capture_qa.py - the 10s files' QA list (TV #862 / MANAGER #154, 2026-10-10)."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from tools import capture_qa as Q
from tools import nt8_freshness_sweep as S

ET = ZoneInfo("America/New_York")
HDR = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n"


def _t(y, m, d, hh, mm, ss=10):
    return int(dt.datetime(y, m, d, hh, mm, ss, tzinfo=ET).timestamp())


def _session(day, zero_share, rt="1"):
    """390 one-minute-apart traded RTH bars; the first zero_share of them carry no buy/sell split."""
    rows, n = [], 390
    for i in range(n):
        t = _t(2026, 9, day, 9, 30) + 60 * i
        zero = i < zero_share * n
        rows.append((t, 50.0, 0.0 if zero else 50.0, 0.0 if zero else 20.0, rt))
    return rows


def test_zero_split_session_is_flagged_with_what_the_rows_claimed():
    ss, bb = Q.scan_rows(_session(22, 0.96) + _session(23, 0.10))
    assert [s["date"] for s in ss] == ["2026-09-22"] and ss[0]["rows_claimed"] == "live (rt 1/2)"
    ss, _ = Q.scan_rows(_session(24, 0.9, rt="3"))
    assert ss[0]["rows_claimed"] == "no ticks (rt 3)"
    assert bb == []


def test_spikes_need_volume_without_the_trades_behind_it():
    t = _t(2026, 9, 24, 13, 1, 20)
    rows = [(t, 412745.0, 0.0, 0.0, "1"),                 # the 09-24 reconnect bar: flagged
            (t + 10, 23208.0, 23000.0, 10345.0, "1"),     # a real quarter-end burst: kept
            (t + 20, 30000.0, 0.0, 0.0, "1"),             # a closing print in a tick-dead session: kept
            (t + 30, 232668.0, 100.0, 252.0, "1")]        # 923 contracts per trade: flagged
    _, bb = Q.scan_rows(rows)
    assert [b["volume"] for b in bb] == [412745.0, 232668.0]
    assert bb[0]["et"] == "2026-09-24 13:01:20"


def test_files_are_read_not_written_and_the_list_round_trips(tmp_path):
    d = tmp_path / "ohlc"
    d.mkdir()
    body = "".join(f"{t},1,1,1,1,{v:.0f},0,{f / 2},{f / 2},{tc:.0f},{rt}\n" for t, v, f, tc, rt in _session(22, 0.96))
    (d / "NQ_10s.csv").write_text(HDR + body)
    before = (d / "NQ_10s.csv").read_bytes()
    data = Q.build(str(d))
    out = tmp_path / "qa.json"
    Q.write(data, str(out))
    assert (d / "NQ_10s.csv").read_bytes() == before                    # rows are never edited
    assert Q.bad_sessions("NQ", str(out)) == {"2026-09-22"} and Q.bad_sessions("ES", str(out)) == set()
    assert json.load(open(out))["ES"] == {"bad_sessions": [], "bad_bars": []}


def test_sweep_warns_only_for_the_last_three_days(tmp_path):
    d = tmp_path / "ohlc"
    d.mkdir()
    body = "".join(f"{t},1,1,1,1,{v:.0f},0,{f / 2},{f / 2},{tc:.0f},{rt}\n" for t, v, f, tc, rt in _session(22, 0.96))
    (d / "NQ_10s.csv").write_text(HDR + body)
    (d / "ES_10s.csv").write_text(HDR)
    near = S.check_capture_qa(_t(2026, 9, 23, 12, 0), str(d))
    far = S.check_capture_qa(_t(2026, 9, 30, 12, 0), str(d))
    assert near[0]["status"] == "warn" and "2026-09-22" in near[0]["detail"]
    assert far[0]["status"] == "pass" and "1 older bad sessions" in far[0]["detail"]
    assert all(i["status"] != "fail" for i in near + far)                  # inbox only, never the phone
