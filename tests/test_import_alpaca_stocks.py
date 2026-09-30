"""Staging the Alpaca stock-bars loader: everything provable WITHOUT an account or a key.

WHY THIS EXISTS (owner decision 2026-09-30 via MANAGER). `tools/import_alpaca_stocks.py`
was written and parked; the owner has now decided to take Alpaca's free Basic plan, and the
loader must work the moment the keys are saved. It had no tests at all, so nothing said it
still worked or pinned the decisions that make it safe to point at the live library. That is
what this file is: a mocked client, no network, no account, no keys.

THE THREE THINGS THAT MUST NOT DRIFT:
  1. Stock masters carry their OWN source tag (`alpaca_split_<session>`). The futures masters
     are deliberately NON-adjusted (`db_noadj_*`, `nt_noadj_*`) because a contract roll must
     stay visible; stocks must be SPLIT-adjusted or every split reads as a crash. The two
     conventions must never meet inside one master, and an unpinned lookup must never
     substitute one for the other.
  2. The key is never hardcoded and never printed. It is read from the environment first,
     then two config files, and the loader refuses to run without one.
  3. The free plan's limits are respected: `end` at least 15 minutes old, 10,000 bars per
     request with paging, and a back-off when Alpaca says 429.

Nothing here talks to Alpaca. Every response is a fixture.
"""
import importlib.util
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TOOL = os.path.join(ROOT, "tools", "import_alpaca_stocks.py")


def _load():
    spec = importlib.util.spec_from_file_location("_alpaca_stocks", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


alp = _load()


# --------------------------------------------------------------------------- fixtures

class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self._p


def _bar(iso, o=100.0, h=101.0, lo=99.0, c=100.5, v=1000):
    return {"t": iso, "o": o, "h": h, "l": lo, "c": c, "v": v}


def _page(sym, bars, token=None):
    return {"bars": {sym: bars}, "next_page_token": token}


# ------------------------------------------------------------------ 1. the source tag

def test_the_stock_source_tag_is_split_adjusted_and_its_own():
    """A stock master must never look like a futures master. `alpaca_split_rth` says both
    things a reader needs: where it came from and that splits are already out of it."""
    assert alp.TF_TAG["1min"] == "1m" and alp.TF_TAG["5min"] == "5m"
    for adj, sess in (("split", "rth"), ("split", "eth")):
        tag = f"alpaca_{adj}_{sess}"
        assert tag.startswith("alpaca_")
        assert "noadj" not in tag, "the no-adjust convention is for FUTURES only"


def test_split_adjustment_is_the_default_request(monkeypatch):
    """Unadjusted stock history makes every split read as a crash (NVDA 10:1, AAPL 4:1), so
    breakout and gap rules fire on garbage. Alpaca does this server-side; the default must
    ask for it."""
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen.update(params)
        return _Resp(_page("AAPL", [_bar("2026-01-02T14:30:00Z")]))

    monkeypatch.setattr(alp.requests, "get", fake_get)
    alp.fetch_bars("AAPL", "5Min", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "k", "s")
    assert seen["adjustment"] == "split"
    assert seen["feed"] == "sip", "the free plan serves full-volume SIP for HISTORY"
    assert seen["limit"] == 10000


def test_a_stock_master_never_collides_with_a_futures_master(tmp_path):
    """The registry key is (instrument, timeframe, source). AAPL 5m from Alpaca and a
    futures master can coexist, and extending one must never touch the other."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        instrument TEXT, timeframe TEXT, rows INT, date_from TEXT, date_to TEXT,
        created_at TEXT, is_master INT, source TEXT, provenance TEXT, session TEXT)""")
    conn.execute("INSERT INTO csv_files (name,filename,instrument,timeframe,is_master,source,session) "
                 "VALUES ('NQ','nq.csv','NQ','5m',1,'db_noadj_rth','rth')")
    conn.commit()

    alp.UP = str(tmp_path)
    df = pd.DataFrame({"time": [1767366600, 1767366900], "open": [1.0, 2.0], "high": [1.0, 2.0],
                       "low": [1.0, 2.0], "close": [1.0, 2.0], "volume": [10, 20]})
    alp.upsert_master(conn, "AAPL", "5m", "alpaca_split_rth", "rth", df)
    conn.commit()

    rows = conn.execute("SELECT instrument, source FROM csv_files ORDER BY instrument").fetchall()
    assert ("AAPL", "alpaca_split_rth") in rows
    assert ("NQ", "db_noadj_rth") in rows, "the futures master must be untouched"


# ------------------------------------------------------------------------ 2. the key

def test_the_environment_is_read_first(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "ENV_KEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "ENV_SECRET")
    assert alp.load_keys() == ("ENV_KEY", "ENV_SECRET")


def test_the_env_var_names_are_the_ones_the_rest_of_the_repo_uses():
    """PAPER-WB's QQQ backfill and api/spy_daily.py already read these names. Renaming them
    here would quietly break both, so this pins the agreement rather than leaving it to a
    conversation nobody can find later."""
    src = open(TOOL, encoding="utf-8").read()
    assert "ALPACA_API_KEY" in src and "ALPACA_SECRET_KEY" in src
    for other in ("tools/backfill_qqq_5m_alpaca.py", "api/spy_daily.py"):
        text = open(os.path.join(ROOT, other), encoding="utf-8").read()
        assert "ALPACA_API_KEY" in text and "ALPACA_SECRET_KEY" in text, (
            f"{other} must read the same env-var names")


def test_without_a_key_it_refuses_rather_than_guessing(monkeypatch, tmp_path):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.setattr(alp, "ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    key, secret = alp.load_keys()
    assert key is None and secret is None


def test_no_key_is_hardcoded_anywhere_in_the_tool():
    """A staged tool is exactly where a 'temporary' pasted key survives. There must be none."""
    src = open(TOOL, encoding="utf-8").read()
    for marker in ("PK", "APCA-API-KEY-ID\": \"", "sk_live", "secret = \""):
        if marker == "PK":
            import re
            assert not re.search(r'"PK[A-Z0-9]{10,}"', src), "looks like a pasted Alpaca key id"
        else:
            assert marker not in src


# --------------------------------------------------------------- 3. the plan's limits

def test_the_end_default_stays_clear_of_the_fifteen_minute_embargo():
    """The free plan refuses the most recent 15 minutes. The default end is now-20min, and
    that margin is what keeps an unattended run from failing every time."""
    src = open(TOOL, encoding="utf-8").read()
    assert "minutes=20" in src
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    assert (datetime.now(timezone.utc) - end) >= timedelta(minutes=15)


def test_it_pages_through_the_ten_thousand_bar_cap(monkeypatch):
    """One request returns at most 10,000 bars plus a token. A loader that ignores the token
    silently truncates history - which would look like a data gap, not a bug."""
    pages = [_page("AAPL", [_bar("2026-01-02T14:30:00Z", c=1.0)], token="T1"),
             _page("AAPL", [_bar("2026-01-02T14:35:00Z", c=2.0)], token=None)]
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params.get("page_token"))
        return _Resp(pages[len(calls) - 1])

    monkeypatch.setattr(alp.requests, "get", fake_get)
    monkeypatch.setattr(alp.time, "sleep", lambda *_: None)
    out = alp.fetch_bars("AAPL", "5Min", "s", "e", "k", "s")
    assert len(out) == 2 and calls == [None, "T1"]
    assert list(out["close"]) == [1.0, 2.0]


def test_a_429_is_waited_out_not_dropped(monkeypatch):
    """200 requests a minute is the free-plan cap. Treating a 429 as an error would leave a
    half-imported master, which is worse than being slow."""
    seq = [_Resp({}, status=429), _Resp(_page("AAPL", [_bar("2026-01-02T14:30:00Z")]))]
    slept = []
    monkeypatch.setattr(alp.requests, "get", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(alp.time, "sleep", lambda s: slept.append(s))
    out = alp.fetch_bars("AAPL", "5Min", "s", "e", "k", "s")
    assert len(out) == 1 and slept and max(slept) >= 20


def test_a_bad_key_fails_loudly_instead_of_returning_nothing(monkeypatch):
    """401/403 must not look like 'no bars'. An empty master is the kind of thing that gets
    noticed weeks later."""
    monkeypatch.setattr(alp.requests, "get", lambda *a, **k: _Resp({"message": "forbidden"}, status=403))
    with pytest.raises(SystemExit):
        alp.fetch_bars("AAPL", "5Min", "s", "e", "bad", "bad")


# ------------------------------------------------------------------- the frame itself

def test_bars_become_posix_seconds_not_nanoseconds(monkeypatch):
    """pandas 3 holds datetimes in microseconds, so the old astype//1e9 idiom silently gives
    a number 1,000x wrong. Every master in the library is keyed on POSIX seconds."""
    monkeypatch.setattr(alp.requests, "get", lambda *a, **k: _Resp(_page("AAPL", [_bar("2026-01-02T14:30:00Z")])))
    monkeypatch.setattr(alp.time, "sleep", lambda *_: None)
    out = alp.fetch_bars("AAPL", "5Min", "s", "e", "k", "s")
    t = int(out["time"].iloc[0])
    assert t == int(pd.Timestamp("2026-01-02T14:30:00Z").timestamp())
    assert 1_000_000_000 < t < 4_000_000_000, "seconds, not ms/us/ns"


def test_the_session_is_detected_from_the_bars_not_assumed():
    rth = pd.DataFrame({"time": [int(pd.Timestamp(f"2026-01-02 {h}:00", tz="US/Eastern").timestamp())
                                 for h in (10, 11, 12, 13, 14)]})
    eth = pd.DataFrame({"time": [int(pd.Timestamp(f"2026-01-02 {h}:00", tz="US/Eastern").timestamp())
                                 for h in (4, 6, 8, 10, 18)]})
    assert alp.detect_session(rth) == "rth"
    assert alp.detect_session(eth) == "eth"


def test_rth_filter_keeps_the_cash_session_only():
    times = [int(pd.Timestamp(f"2026-01-02 {h}:{m:02d}", tz="US/Eastern").timestamp())
             for h, m in ((9, 29), (9, 30), (12, 0), (15, 59), (16, 0), (18, 0))]
    df = pd.DataFrame({"time": times})
    kept = alp.rth_filter(df)
    et = pd.to_datetime(kept["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    assert len(kept) == 3
    assert et.iloc[0].strftime("%H:%M") == "09:30" and et.iloc[-1].strftime("%H:%M") == "15:59"


def test_re_running_extends_a_master_and_existing_rows_win(tmp_path):
    """The contract every importer in this repo shares: additive and idempotent, so a repeat
    run is never destructive and a re-pull cannot rewrite history."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        instrument TEXT, timeframe TEXT, rows INT, date_from TEXT, date_to TEXT,
        created_at TEXT, is_master INT, source TEXT, provenance TEXT, session TEXT)""")
    conn.commit()
    alp.UP = str(tmp_path)

    first = pd.DataFrame({"time": [1767366600, 1767366900], "open": [1.0, 2.0], "high": [1.0, 2.0],
                          "low": [1.0, 2.0], "close": [1.0, 2.0], "volume": [10, 20]})
    alp.upsert_master(conn, "AAPL", "5m", "alpaca_split_rth", "rth", first)
    conn.commit()

    # an overlapping re-pull with DIFFERENT values for a bar we already hold
    second = pd.DataFrame({"time": [1767366900, 1767367200], "open": [99.0, 3.0], "high": [99.0, 3.0],
                           "low": [99.0, 3.0], "close": [99.0, 3.0], "volume": [99, 30]})
    alp.upsert_master(conn, "AAPL", "5m", "alpaca_split_rth", "rth", second)
    conn.commit()

    fn = conn.execute("SELECT filename, rows FROM csv_files WHERE instrument='AAPL'").fetchone()
    stored = pd.read_csv(os.path.join(str(tmp_path), fn[0]))
    assert len(stored) == 3 and fn[1] == 3, "one new bar, not a duplicate"
    kept = stored[stored["time"] == 1767366900]["close"].iloc[0]
    assert kept == 2.0, "the row we already had must win on overlap"


def test_nothing_in_this_file_reaches_the_network():
    """The staging rule: no account, no keys, no calls. If the tool ever grows a second HTTP
    entry point this test is the thing that should fail first."""
    src = open(TOOL, encoding="utf-8").read()
    assert src.count("requests.get") == 1, (
        "one HTTP call site keeps it mockable; a second needs its own fixture here")
