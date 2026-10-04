r"""An UNADJUSTED split in a stock master, which Alpaca's split-adjusted feed can still leave in.

FOUND IN THE WILD, after it had already cost a result. TBIS reported (2026-10-03) that
`adjustment=split` did not adjust GE's 1-for-8 REVERSE split of 2021-08-02: the stored history
runs 12.95 on 07-30 and then opens at 104.48, an 8.07x jump with the earlier years never rebased.
Its 10-minute bars read that as a real move and booked a fake +$139k trade. It took a deliberate
scan of 50 large caps across 10 years to find, and that scan found exactly one - rare is precisely
what nobody checks by hand, and a row count or a date span cannot see it at all.

TELLING A MISSED SPLIT FROM REAL NEWS is the whole problem, and the numbers here were chosen
against REAL pulled data, not guessed:

    GE   2021-08-02   8.07x   a 1-for-8 the feed missed        -> must fire
    CELG 2019-01-03   1.32x   the Bristol-Myers takeover pop   -> must NOT fire
    INTC 2024-08      -26%    real news                        -> must NOT fire
    AAPL 2020-08-31   4-for-1 the feed DID adjust              -> must NOT fire
    NVDA 2024-06-10   10-for-1 the feed DID adjust             -> must NOT fire

The first version of this check also accepted fractional ratios (3:2, 4:3, 5:4) and refused CELG,
because 1.32x sits within 2% of 4/3. A 1.3x overnight move is ordinary news; an 8.07x one is not.
So the rule is a big gap - at least a doubling or halving - that lands on a WHOLE ratio. Spin-offs
are unadjusted by design under adjustment=split and are deliberately not caught: their ratios are
not whole.
"""
import importlib.util
import os
import sqlite3
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TOOL = os.path.join(ROOT, "tools", "import_alpaca_stocks.py")


def _load():
    spec = importlib.util.spec_from_file_location("_alpaca_splitgap", TOOL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


alp = _load()


@pytest.fixture(autouse=True)
def _quiet_log(monkeypatch):
    captured = []
    monkeypatch.setattr(alp, "log", lambda msg: captured.append(str(msg)))
    return captured


def _sec(stamp):
    return int(pd.Timestamp(stamp, tz="US/Eastern").timestamp())


def _days(closes, opens=None, start="2021-07-26"):
    """One bar a day, consecutive weekdays, with explicit opens when the gap matters."""
    opens = opens if opens is not None else list(closes)
    times, d = [], pd.Timestamp(start)
    while len(times) < len(closes):
        if d.weekday() < 5:
            times.append(_sec(d.strftime("%Y-%m-%d") + " 10:00"))
        d += pd.Timedelta(days=1)
    return pd.DataFrame({"time": times, "open": opens, "high": [max(o, c) for o, c in
                        zip(opens, closes)], "low": [min(o, c) for o, c in zip(opens, closes)],
                         "close": closes, "volume": [1000] * len(closes)})


# ════════════════════════════════════════════════ the real case, as the numbers actually were
def test_the_GE_reverse_split_is_caught():
    """GE's real bars: 12.95 close, then a 104.48 open."""
    df = _days(closes=[12.92, 13.08, 13.13, 13.29, 12.95, 100.60, 103.06],
               opens=[12.66, 13.33, 13.15, 13.19, 13.16, 104.48, 100.20])
    hits = alp.split_like_gaps(df)
    assert len(hits) == 1
    when, ratio, nearest, name = hits[0]
    assert 8.0 < ratio < 8.2
    assert nearest == 8.0 and name == "8:1"


def test_a_forward_split_the_feed_missed_is_caught_too():
    """The same defect the other way round: a 4-for-1 leaves prices a quarter of what they were."""
    df = _days(closes=[400.0, 404.0, 408.0, 101.0, 102.0], opens=[399.0, 402.0, 406.0, 102.0, 101.5])
    hits = alp.split_like_gaps(df)
    assert len(hits) == 1 and hits[0][3] == "1:4"


# ════════════════════════════════════════════════ real news must not be refused
def test_the_CELG_takeover_pop_is_not_called_a_split():
    """1.32x: within 2% of 4/3, which is why fractional ratios are not accepted."""
    df = _days(closes=[66.0, 65.5, 87.0, 88.0], opens=[66.2, 65.8, 86.5, 87.5])
    assert alp.split_like_gaps(df) == []


def test_a_big_real_fall_is_not_called_a_split():
    df = _days(closes=[35.0, 34.8, 25.8, 26.0], opens=[35.1, 34.9, 25.5, 25.9])
    assert alp.split_like_gaps(df) == []


def test_an_ordinary_day_to_day_move_is_not_called_a_split():
    df = _days(closes=[100.0, 101.0, 99.5, 100.5])
    assert alp.split_like_gaps(df) == []


def test_an_intraday_jump_is_not_an_overnight_gap():
    """Two bars inside ONE session, eight times apart. Only a change of session date counts."""
    t = _sec("2021-08-02 10:00")
    df = pd.DataFrame({"time": [t, t + 600], "open": [12.0, 96.0], "high": [12.0, 96.0],
                       "low": [12.0, 96.0], "close": [12.0, 96.0], "volume": [10, 10]})
    assert alp.split_like_gaps(df) == []


# ════════════════════════════════════════════════ shapes that must not crash it
@pytest.mark.parametrize("df", [None, pd.DataFrame({"time": [], "open": [], "close": []})])
def test_an_empty_frame_is_handled(df):
    assert alp.split_like_gaps(df) == []


def test_a_single_bar_is_handled():
    assert alp.split_like_gaps(_days(closes=[100.0])) == []


def test_a_zero_or_negative_price_is_skipped_not_divided_by():
    df = _days(closes=[0.0, 100.0, 101.0], opens=[0.0, 100.0, 100.5])
    assert alp.split_like_gaps(df) == []


# ════════════════════════════════════════════════ it stops the master being registered
def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("""CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        instrument TEXT, timeframe TEXT, rows INT, date_from TEXT, date_to TEXT,
        created_at TEXT, is_master INT, source TEXT, provenance TEXT, session TEXT)""")
    conn.commit()
    alp.UP = str(tmp_path)
    return conn


def test_a_master_holding_an_unadjusted_split_is_refused(tmp_path, _quiet_log):
    conn = _conn(tmp_path)
    df = _days(closes=[12.95, 100.60, 103.06], opens=[13.16, 104.48, 100.20])
    alp.upsert_master(conn, "GE", "10m", "alpaca_split_rth", "rth", df)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM csv_files").fetchone()[0] == 0, (
        "nothing may be registered")
    msg = " ".join(_quiet_log)
    assert "REFUSED" in msg and "8.07" in msg and "8:1" in msg
    assert "2021-08-02" in msg, "it must name the day, so a human can go and look"
    assert "adjustment=raw" in msg, "and say what to do instead"


def test_a_clean_master_still_registers(tmp_path, _quiet_log):
    conn = _conn(tmp_path)
    alp.upsert_master(conn, "AAPL", "10m", "alpaca_split_rth", "rth",
                      _days(closes=[100.0, 101.0, 99.5]))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM csv_files").fetchone()[0] == 1


def test_the_refusal_can_be_overridden_by_a_caller_that_has_checked(tmp_path, _quiet_log):
    """A real doubling on news would be refused too. The override exists so a human who has
    looked is not stuck - it is a parameter, not a default."""
    conn = _conn(tmp_path)
    df = _days(closes=[12.95, 100.60, 103.06], opens=[13.16, 104.48, 100.20])
    alp.upsert_master(conn, "GE", "10m", "alpaca_split_rth", "rth", df, allow_split_gap=True)
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM csv_files").fetchone()[0] == 1


def test_the_check_runs_before_anything_is_written(tmp_path, _quiet_log):
    """Refusing after the file exists would leave a bad master on disk for the next reader."""
    conn = _conn(tmp_path)
    df = _days(closes=[12.95, 100.60], opens=[13.16, 104.48])
    alp.upsert_master(conn, "GE", "10m", "alpaca_split_rth", "rth", df)
    assert not [f for f in os.listdir(str(tmp_path)) if f.endswith(".csv")]


def test_the_guard_sits_before_the_rebase_branch_in_the_source():
    """Order matters: the split-basis rebase path writes, so the gap check has to come first."""
    src = open(TOOL, encoding="utf-8").read()
    body = src[src.index("def upsert_master"):]
    assert body.index("split_like_gaps(new)") < body.index("rebased_note = None")
