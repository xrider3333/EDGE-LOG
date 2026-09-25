"""tools/refresh_noadj_yahoo.py must never save a still-forming Yahoo bar into a non-adjusted
master. Yahoo's history() always hands back the CURRENT, in-progress bar as its last row, and
the script only ever appends bars past the master's last saved timestamp -- so a partial bar
saved once stays wrong forever (2026-09-24: the NQ 5m bar stamped 15:05 ET was saved mid-bar
with close 30742.00/volume 1708 against Yahoo's eventual final 30738.75/2502, and every later
run just skipped past it; the lead fixed it by hand). No network anywhere in this file: the
pure guard (_drop_unclosed) is tested directly, and main() is exercised end to end against a
monkeypatched yfinance.Ticker, a temp CSV master, and a temp sqlite registry.
"""
import os
import sqlite3
import sys
import types

import pandas as pd
import pytest

import importlib.util

# Load THIS checkout's file by path, not `from tools import ...`: earlier tests in a full run can
# leave a `tools` package from another checkout (the shared one, for its data) in sys.modules,
# and the import would then quietly test that copy instead of this one.
_SPEC = importlib.util.spec_from_file_location(
    "_refresh_noadj_yahoo_under_test",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "refresh_noadj_yahoo.py"))
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


def _tv(times):
    """A minimal `_to_tv`-shaped frame: unix-second bar-start times, flat OHLCV."""
    n = len(times)
    return pd.DataFrame({
        "time": list(times), "open": [100.0] * n, "high": [100.0] * n,
        "low": [100.0] * n, "close": [100.0] * n, "volume": [10] * n,
    })


# ── _drop_unclosed: pure, no network ──────────────────────────────────────────────────
def test_forming_5m_bar_dropped_closed_bar_kept():
    now = 1_700_000_000
    closed_start = now - 300 - 60      # closed well past the margin
    forming_start = now - 120          # started 2 min ago, 5m bar nowhere near closed
    out = R._drop_unclosed(_tv([closed_start, forming_start]), "5m", now, margin_s=30)
    assert out["time"].tolist() == [closed_start]


def test_boundary_at_the_margin():
    now = 1_700_000_000
    tf_s, margin_s = 300, 30
    edge = now - tf_s - margin_s                 # time + tf_s + margin_s == now -> kept (<=)
    kept = R._drop_unclosed(_tv([edge]), "5m", now, margin_s=margin_s)
    assert kept["time"].tolist() == [edge]

    one_late = edge + 1                          # time + tf_s + margin_s == now + 1 -> dropped
    dropped = R._drop_unclosed(_tv([one_late]), "5m", now, margin_s=margin_s)
    assert dropped["time"].tolist() == []


def test_1m_timeframe_uses_60_second_bars():
    now = 1_700_000_000
    closed_start = now - 60 - 30
    forming_start = now - 10
    out = R._drop_unclosed(_tv([closed_start, forming_start]), "1m", now, margin_s=30)
    assert out["time"].tolist() == [closed_start]


def test_empty_frame_is_a_no_op():
    out = R._drop_unclosed(_tv([]), "5m", 1_700_000_000)
    assert len(out) == 0
    assert list(out.columns) == ["time", "open", "high", "low", "close", "volume"]


# ── main(): end to end, no network ────────────────────────────────────────────────────
def test_main_never_appends_the_forming_bar(tmp_path, monkeypatch, capsys):
    """Reproduces the 2026-09-24 shape: a mid-session run (15:22 ET here) sees Yahoo's still-forming 15:05 ET
    5m bar as the last row of history(). main() must append the prior, already-closed 15:00 ET
    bar and leave the forming one out entirely -- not save it and hope a later run fixes it,
    which is exactly how the bad bar got stuck in the real master."""
    last_existing = 1790276100   # 2026-09-24 14:55:00 ET -- already the master's last bar
    bar1_start = 1790276400      # 2026-09-24 15:00:00 ET -- closed + settled by 15:22 -> must be appended
    bar2_start = 1790276700      # 2026-09-24 15:05:00 ET -- the real incident bar, still forming
    now_s = 1790277720           # 2026-09-24 15:22:00 ET -- 15:00 bar settled, 15:05 still inside Yahoo's delay

    up_dir = tmp_path / "augur_uploads"
    up_dir.mkdir()
    fn = "NOADJ_NQ_5m_RTH.csv"
    pd.DataFrame({"time": [last_existing], "open": [30690.0], "high": [30695.0],
                  "low": [30685.0], "close": [30692.0], "volume": [1200]}
                 ).to_csv(up_dir / fn, index=False)

    db_path = tmp_path / "optimizer_history.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,"
                 " instrument TEXT, rows INTEGER, date_from TEXT, date_to TEXT,"
                 " created_at TEXT, timeframe TEXT, is_master INTEGER, source TEXT,"
                 " provenance TEXT, session TEXT)")
    conn.execute("INSERT INTO csv_files (name, filename, instrument, rows, timeframe,"
                 " is_master, source, session) VALUES (?,?,?,?,?,?,?,?)",
                 ("NQ 5m (Yahoo non-adj)", fn, "NQ", 1, "5m", 1, "db_noadj", "rth"))
    conn.commit()
    conn.close()

    idx = pd.to_datetime([bar1_start, bar2_start], unit="s", utc=True)
    hist = pd.DataFrame({"Open": [30693.0, 30740.0], "High": [30700.0, 30745.0],
                         "Low": [30688.0, 30735.0], "Close": [30699.0, 30742.0],
                         "Volume": [2502, 1708]}, index=idx)

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, interval=None):
            assert self.symbol == "NQ=F" and period == "60d" and interval == "5m"
            return hist

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_FakeTicker))
    monkeypatch.setattr(R, "UP", str(up_dir))
    monkeypatch.setattr(R, "DB", str(db_path))

    R.main(now_s=now_s)

    out = pd.read_csv(up_dir / fn)
    assert out["time"].tolist() == [last_existing, bar1_start]   # the forming bar never lands
    assert bar2_start not in out["time"].values

    conn = sqlite3.connect(str(db_path))
    rows, date_to = conn.execute("SELECT rows, date_to FROM csv_files WHERE filename=?",
                                 (fn,)).fetchone()
    conn.close()
    assert rows == 2
    assert date_to == "2026-09-24"

    captured = capsys.readouterr().out
    assert f"  {fn}: skipped 1 unfinished bar(s) (still forming)" in captured


def test_default_margin_covers_yahoo_futures_delay():
    # Yahoo's CME futures run ~10 min behind: 11 minutes after a 5m bar's close it must still be held back.
    now = 1_700_000_000
    start = now - 300 - 11 * 60
    assert R._drop_unclosed(_tv([start]), "5m", now)["time"].tolist() == []
    assert R._drop_unclosed(_tv([now - 300 - R.YAHOO_SETTLE_S]), "5m", now)["time"].tolist() == [now - 300 - R.YAHOO_SETTLE_S]
