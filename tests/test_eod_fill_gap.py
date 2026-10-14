"""tools/eod_fill_gap.py -- the end-of-day fill gap log (MANAGER #152, ORB COSTSTRESS r1):
every EOD exit beside the engine's own 15:55-bar price and the 16:00 close. Exact gaps and
their sign (positive = live did worse), the resend join, a leg with no engine exit, a half
day, a bar not in the cache yet (blank, then filled), non-EOD exits left out, idempotent
rewrites, trimmed-ledger history, and the hook in tools/qqq_bars_publish.py that must never
affect the publisher. Every fixture is synthetic and lives in tmp_path."""
import csv
import datetime as dt
import io
import os
import sys
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from tools import eod_fill_gap as efg  # noqa: E402
import qqq_bars_publish as qb  # noqa: E402  (as tests/test_qqq_bars_publish.py imports it)

ET = ZoneInfo("America/New_York")

BAR_HDR = ["time", "open", "high", "low", "close", "volume"]
SIG_HDR = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares", "reason",
           "bar_source", "trade_id"]
TR_HDR = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px", "pnl",
          "nq_pnl_points", "exit_reason", "signal_source", "trade_id"]
BO_HDR = ["ts_et", "leg", "intent", "side", "shares", "signal_id", "client_order_id", "mode",
          "ok", "sent", "shadow_px", "broker_fill_px", "slippage", "reason", "duplicate",
          "host_id", "outcome"]

ORB_L = "ORB_R6-20261013T140000Z-L"      # long, 10-13
ORB_S = "ORB_R6-20261008T164500Z-S"      # short, 10-08, first close refused then resent
NOISE_S = "NOISE_382-20261008T165500Z-S"  # 10-08, the engine wrote no EXIT for it
ENGU_L = "ENGUQ_335-20261013T163200Z-L"  # 10-13, the engine held it to 10-15
HALF = "ORB_R6-20241129T150000Z-L"       # 2024-11-29, a 13:00 half day
LATE = "NOISE_382-20261014T151500Z-S"    # 10-14, its 15:55 bar not in the cache yet


def _epoch(day, hhmm):
    y, mo, d = map(int, day.split("-"))
    h, m = map(int, hhmm.split(":"))
    return int(dt.datetime(y, mo, d, h, m, tzinfo=ET).timestamp())


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _day_bars(day, last, special, filler=(700.0, 700.5, 699.5, 700.0)):
    rows, m = [], 9 * 60 + 30
    lh, lm = map(int, last.split(":"))
    while m <= lh * 60 + lm:
        hhmm = f"{m // 60:02d}:{m % 60:02d}"
        o, h, lo, c = special.get(hhmm, filler)
        rows.append([_epoch(day, hhmm), o, h, lo, c, 1000.0])
        m += 5
    return rows


def _bars(late_last="15:50"):
    rows = _day_bars("2026-10-08", "15:55", {"15:55": (746.85, 747.815, 746.69, 747.50)})
    rows += _day_bars("2026-10-13", "15:55", {"15:55": (743.26, 743.7, 743.2, 743.60)})
    rows += _day_bars("2026-10-14", late_last, {"15:55": (728.94, 729.05, 728.0, 728.90)})
    # the half day: 12:55 is the session's last bar; the after-hours bars up to 15:55 that
    # the cache also holds (load_bars keeps everything before 16:00) must never be picked
    rows += _day_bars("2024-11-29", "15:55", {"12:55": (599.5, 600.2, 599.4, 600.05)},
                      filler=(1.0, 1.0, 1.0, 1.0))
    return rows


def _make_home(tmp_path, late_last="15:50"):
    home = str(tmp_path / "home")
    _write_csv(os.path.join(home, "ohlc", "QQQ_5m.csv"), BAR_HDR, _bars(late_last))
    _write_csv(os.path.join(home, "cloud_signal", "signals.csv"), SIG_HDR, [
        ["2026-10-08T12:50:05-04:00", "ORB_R6", "ENTRY", "short", "2026-10-08T12:45:00-04:00",
         "749.97", "133", "", "webull", ORB_S],
        ["2026-10-08T16:00:31.046673-04:00", "ORB_R6", "EXIT", "short",
         "2026-10-08T15:55:00-04:00", "747.58", "133", "strategy_exit; eod_settle", "webull",
         ORB_S],
        ["2026-10-08T12:55:05-04:00", "NOISE_382", "ENTRY", "short",
         "2026-10-08T12:55:00-04:00", "748.5", "133", "", "webull", NOISE_S],
        ["2026-10-13T16:00:30.946845-04:00", "ORB_R6", "EXIT", "long",
         "2026-10-13T15:55:00-04:00", "743.57", "134", "strategy_exit; eod_settle", "webull",
         ORB_L],
        ["2026-10-15T10:43:33-04:00", "ENGUQ_335", "EXIT", "long", "2026-10-15T10:42:00-04:00",
         "751.2", "135", "strategy_exit", "webull", ENGU_L],
        ["2024-11-29T13:00:30-05:00", "ORB_R6", "EXIT", "long", "2024-11-29T12:55:00-05:00",
         "600.05", "134", "strategy_exit; eod_settle", "webull", HALF],
        ["2026-10-14T16:00:32-04:00", "NOISE_382", "EXIT", "short",
         "2026-10-14T15:55:00-04:00", "728.95", "136", "strategy_exit; eod_settle", "webull",
         LATE],
    ])
    _write_csv(os.path.join(home, "qqq_exec", "trades.csv"), TR_HDR, [
        ["ORB", "2024-11-29 10:00:05", "2024-11-29 12:59:02", "long", "10", "598.0", "600.0",
         "20", "", "EOD (px: live_stream)", "engine", HALF],
        ["ORB", "2026-10-08 12:50:11", "2026-10-08 15:59:03", "short", "10", "749.97", "747.76",
         "22.1", "", "EOD (px: live_stream)", "engine", ORB_S],
        ["NOISE", "2026-10-08 12:55:07", "2026-10-08 15:59:03", "short", "20", "748.515",
         "747.76", "15.1", "", "EOD (px: live_stream)", "engine", NOISE_S],
        ["NOISE", "2026-10-13 10:10:07", "2026-10-13 11:45:10", "short", "20", "745.725",
         "747.06", "-26.7", "", "signal exit", "engine", "NOISE_382-20261013T141000Z-S"],
        ["ORB", "2026-10-13 10:05:10", "2026-10-13 15:59:03", "long", "10", "743.95", "743.48",
         "-4.7", "", "EOD (px: live_stream)", "engine", ORB_L],
        ["ENGUQ", "2026-10-13 12:33:38", "2026-10-13 15:59:03", "long", "10", "740.0", "743.48",
         "34.8", "", "EOD (px: live_stream)", "engine", ENGU_L],
        ["NOISE", "2026-10-14 11:15:12", "2026-10-14 15:59:00", "short", "10", "733.975",
         "728.2", "57.75", "", "EOD (px: live_stream)", "engine", LATE],
    ])
    _write_csv(os.path.join(home, "qqq_exec", "broker_orders.csv"), BO_HDR, [
        ["2026-10-08 15:59:03", "ORB", "CLOSE", "BUY", "10", "qxORBR620261008T164500ZSC", "c",
         "PAPER", "False", "True", "747.76", "", "",
         "ServerException: HTTP Status: 417, Code: X, Msg: Duplicate Order.", "False",
         "edgelog", "REFUSED"],
        ["2026-10-08 15:59:08", "ORB", "CLOSE", "BUY", "10", "qxORBR620261008T164500ZSCR1", "c",
         "PAPER", "True", "True", "747.76", "747.71", "-0.05", "", "False", "edgelog", "OK"],
        ["2026-10-13 15:59:03", "ORB", "CLOSE", "SELL", "10", "qxORBR620261013T140000ZLC", "c",
         "PAPER", "True", "True", "743.48", "743.5", "0.02", "", "False", "edgelog", "OK"],
        # ENGU-Q crossed internally against nothing real here: a NETTED row is not a fill
        ["2026-10-13 15:59:03", "ENGUQ", "CLOSE", "SELL", "10", "qxENGUQ33520261013T163200ZLC",
         "", "PAPER", "True", "False", "743.48", "743.48", "0", "EOD: crossed internally",
         "False", "edgelog", "NETTED"],
        ["2026-10-14 15:59:00", "NOISE", "CLOSE", "BUY", "10", "qxNOISE38220261014T151500ZSC",
         "c", "PAPER", "True", "True", "728.2", "728.11", "-0.09", "", "False", "edgelog", "OK"],
    ])
    return home


def _out_path(home):
    return os.path.join(home, "qqq_exec", "eod_fill_gap.csv")


def _read(home):
    with open(_out_path(home), newline="", encoding="utf-8") as f:
        return {r["trade_id"]: r for r in csv.DictReader(f)}


def _run(home, **kw):
    buf = io.StringIO()
    rows = efg.write_for_home(home, log=lambda s: print(s, file=buf), **kw)
    return rows, buf.getvalue()


def _f(v):
    return float(v) if v != "" else None


# -- the rows --------------------------------------------------------------------------
def test_long_and_short_orb_gaps_exact_and_signed(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    rows = _read(home)
    lo = rows[ORB_L]
    assert (lo["day"], lo["leg"], lo["side"], lo["shares"]) == ("2026-10-13", "ORB", "long", "10")
    assert lo["exit_ts"] == "2026-10-13 15:59:03" and lo["book_exit_px"] == "743.48"
    assert lo["broker_fill_px"] == "743.5" and lo["px_source"] == "broker"
    assert lo["engine_exit_px"] == "743.57"
    assert lo["engine_exit_bar"] == "2026-10-13 15:55:00"
    assert lo["engine_exit_emitted_at"] == "2026-10-13 16:00:30"
    assert lo["engine_exit_reason"] == "strategy_exit; eod_settle"
    assert (lo["bar_1555_open"], lo["bar_1555_close"], lo["close_1600"]) == ("743.26", "743.6", "743.6")
    # long: a sell 7 cents under the engine's 15:55-bar price = live WORSE = positive
    assert lo["fill_vs_engine"] == "0.07" and lo["fill_vs_close_1600"] == "0.1"
    sh = rows[ORB_S]
    # the refused first try is not a fill; its resend (R1) is
    assert sh["broker_fill_px"] == "747.71" and sh["px_source"] == "broker"
    assert sh["engine_exit_px"] == "747.58" and sh["close_1600"] == "747.5"
    # short: a buy 13 cents over the engine = live WORSE = positive
    assert sh["fill_vs_engine"] == "0.13" and sh["fill_vs_close_1600"] == "0.21"


def test_sign_rule_both_ways():
    assert efg.signed_gap("long", 99.0, 100.0) == pytest.approx(1.0)     # sold lower: worse
    assert efg.signed_gap("long", 101.0, 100.0) == pytest.approx(-1.0)   # sold higher: better
    assert efg.signed_gap("short", 101.0, 100.0) == pytest.approx(1.0)   # bought higher: worse
    assert efg.signed_gap("short", 99.0, 100.0) == pytest.approx(-1.0)
    assert efg.signed_gap("long", None, 100.0) is None
    assert efg.signed_gap("", 99.0, 100.0) is None


def test_leg_with_no_engine_exit_keeps_the_close_fields(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    r = _read(home)[NOISE_S]
    for c in ("engine_exit_px", "engine_exit_bar", "engine_exit_emitted_at",
              "engine_exit_reason", "fill_vs_engine", "broker_fill_px"):
        assert r[c] == "", c
    assert r["px_source"] == "book" and r["book_exit_px"] == "747.76"
    assert (r["bar_1555_open"], r["bar_1555_close"], r["close_1600"]) == ("746.85", "747.5", "747.5")
    assert r["fill_vs_close_1600"] == "0.26"            # short: bought 26 cents over the close


def test_engine_exit_on_another_bar_is_shown_but_not_gapped(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    r = _read(home)[ENGU_L]
    assert r["engine_exit_px"] == "751.2" and r["engine_exit_bar"] == "2026-10-15 10:42:00"
    assert r["fill_vs_engine"] == ""                    # the engine held it: not the EOD gap
    # a NETTED (internally crossed) row never reached Webull: not a broker fill
    assert r["broker_fill_px"] == "" and r["px_source"] == "book"
    assert r["fill_vs_close_1600"] == "0.12"            # long: 743.60 close - 743.48 book


def test_half_day_uses_the_sessions_last_bar(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    r = _read(home)[HALF]
    assert efg.last_bar_minute("2024-11-29") == 12 * 60 + 55
    assert (r["bar_1555_open"], r["bar_1555_close"], r["close_1600"]) == ("599.5", "600.05", "600.05")
    assert r["engine_exit_bar"] == "2024-11-29 12:55:00"
    assert r["px_source"] == "book"
    assert r["fill_vs_engine"] == "0.05" and r["fill_vs_close_1600"] == "0.05"


def test_bar_not_cached_yet_is_blank_then_filled(tmp_path):
    home = _make_home(tmp_path, late_last="15:50")
    _rows, log = _run(home)
    r = _read(home)[LATE]
    for c in ("bar_1555_open", "bar_1555_close", "close_1600", "fill_vs_close_1600"):
        assert r[c] == "", c
    assert r["fill_vs_engine"] == "-0.84"               # short: bought 84 cents under the engine
    assert "1 without their last bar yet" in log
    _write_csv(os.path.join(home, "ohlc", "QQQ_5m.csv"), BAR_HDR, _bars("15:55"))
    _run(home)
    r = _read(home)[LATE]
    assert (r["bar_1555_open"], r["bar_1555_close"], r["close_1600"]) == ("728.94", "728.9", "728.9")
    assert r["fill_vs_close_1600"] == "-0.79"


def test_only_eod_exits_are_listed_oldest_first(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    with open(_out_path(home), newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        assert rd.fieldnames == efg.COLS
        rows = list(rd)
    assert "NOISE_382-20261013T141000Z-S" not in {r["trade_id"] for r in rows}
    # by exit_ts, then leg (same-second flattens: ENGUQ, NOISE before ORB)
    assert [r["trade_id"] for r in rows] == [HALF, NOISE_S, ORB_S, ENGU_L, ORB_L, LATE]
    assert all(r["exit_reason"].startswith("EOD") for r in rows)


def test_two_runs_write_identical_files(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    first = open(_out_path(home), "rb").read()
    _run(home)
    assert open(_out_path(home), "rb").read() == first
    assert not os.path.exists(_out_path(home) + ".tmp")


def test_trimmed_ledgers_keep_history(tmp_path):
    home = _make_home(tmp_path)
    _run(home)
    before = _read(home)
    tr = os.path.join(home, "qqq_exec", "trades.csv")
    with open(tr, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    # trades.csv trimmed at the top (the 2024 half-day row gone), broker_orders.csv and the
    # bar cache lose the 10-08 rows: the old row stays, the 10-08 fills and bars are kept
    _write_csv(tr, rows[0], rows[2:])
    bo = os.path.join(home, "qqq_exec", "broker_orders.csv")
    with open(bo, newline="", encoding="utf-8") as f:
        brows = list(csv.reader(f))
    _write_csv(bo, brows[0], brows[3:])
    _write_csv(os.path.join(home, "ohlc", "QQQ_5m.csv"), BAR_HDR,
               [b for b in _bars() if b[0] > _epoch("2026-10-09", "00:00")])
    _run(home)
    after = _read(home)
    assert after[HALF] == before[HALF]
    assert after[ORB_S] == before[ORB_S]
    assert after[ORB_S]["broker_fill_px"] == "747.71" and after[ORB_S]["close_1600"] == "747.5"


def test_dry_run_writes_nothing(tmp_path):
    home = _make_home(tmp_path)
    rows, log = _run(home, dry_run=True)
    assert len(rows) == 6 and "DRY RUN" in log
    assert not os.path.exists(_out_path(home))


def test_torn_ledger_writes_nothing(tmp_path):
    home = _make_home(tmp_path)
    with open(os.path.join(home, "qqq_exec", "trades.csv"), "a", encoding="utf-8") as f:
        f.write("ORB,2026-10-15 10:00:00\n")             # a row cut off mid-write
    rows, log = _run(home, sleep=lambda s: None)
    assert rows is None and "mid-rewrite" in log
    assert not os.path.exists(_out_path(home))


def test_main_exit_codes_and_missing_inputs(tmp_path, capsys):
    assert efg.main(["--no-such-flag"]) == 1
    buf = io.StringIO()
    assert efg.main(["--home", str(tmp_path / "empty")], out=buf) == 0
    assert "no trades.csv" in buf.getvalue()
    home = _make_home(tmp_path)
    buf = io.StringIO()
    assert efg.main(["--home", home], out=buf) == 0
    assert "wrote 6 EOD exit row(s)" in buf.getvalue()
    assert buf.getvalue().isascii()


def test_main_never_raises(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(efg, "write_for_home", boom)
    buf = io.StringIO()
    assert efg.main(["--home", str(tmp_path)], out=buf) == 0
    assert "failed (RuntimeError: bug)" in buf.getvalue()


# -- the hook in tools/qqq_bars_publish.py ----------------------------------------------
class _FakeRef:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, name):
        return type(self)(self.store, self.path + [name])

    def document(self, name):
        return type(self)(self.store, self.path + [name])

    def set(self, doc):
        self.store["/".join(self.path)] = doc


NOW = dt.datetime(2026, 10, 13, 16, 10, tzinfo=ET)
PUB = ["--date", "2026-10-13", "--uid", "U1"]


def test_publish_run_refreshes_the_log(tmp_path):
    home = _make_home(tmp_path)
    store, buf = {}, io.StringIO()
    rc = qb.main(["--home", home] + PUB, db_factory=lambda c: _FakeRef(store, []), now=NOW,
                 out=buf)
    assert rc == 0 and list(store) == ["users/U1/qqq_bars/2026-10-13"]
    assert ORB_L in _read(home)
    text = buf.getvalue()
    assert text.index("[qqq-bars] PUBLISHED") < text.index("[eod-gap] wrote 6")


def test_hook_swallows_an_eod_fill_gap_error(tmp_path, monkeypatch):
    home = _make_home(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(efg, "write_for_home", boom)
    store, buf = {}, io.StringIO()
    rc = qb.main(["--home", home] + PUB, db_factory=lambda c: _FakeRef(store, []), now=NOW,
                 out=buf)
    assert rc == 0 and list(store) == ["users/U1/qqq_bars/2026-10-13"]
    text = buf.getvalue()
    assert "[qqq-bars] PUBLISHED" in text
    assert "EOD fill gap log not refreshed (RuntimeError: boom)" in text


def test_hook_still_runs_when_the_publisher_stops_early(tmp_path):
    home = _make_home(tmp_path)

    def no_creds(_cred):
        raise ValueError("no credentials")
    with pytest.raises(ValueError):          # the publisher's own failure is unchanged
        qb.main(["--home", home] + PUB, db_factory=no_creds, now=NOW, out=io.StringIO())
    assert ORB_L in _read(home)


def test_dry_run_publish_does_not_run_the_hook(tmp_path, monkeypatch):
    home = _make_home(tmp_path)
    calls = []
    monkeypatch.setattr(efg, "write_for_home", lambda *a, **k: calls.append(1))
    rc = qb.main(["--dry-run", "--home", home, "--date", "2026-10-13"], db_factory=None,
                 now=NOW, out=io.StringIO())
    assert rc == 0 and calls == []
    assert not os.path.exists(_out_path(home))
