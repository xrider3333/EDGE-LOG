import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import push_qqq_ext_alpaca as px  # noqa: E402
import qqq_bars_publish as qb  # noqa: E402


def _ep(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=qb.ET).timestamp())


def test_ext_rows_keeps_only_pre_and_post():
    df = pd.DataFrame({"time": [_ep("2026-10-30 08:00"), _ep("2026-10-30 10:00"), _ep("2026-10-30 17:00"),
                                _ep("2026-10-30 21:00")],
                       "open": [1, 2, 3, 4], "high": [1, 2, 3, 4], "low": [1, 2, 3, 4],
                       "close": [1, 2, 3, 4], "volume": [5, 6, 7, 8]})
    assert [r[1] for r in px.ext_rows(df)] == [1.0, 3.0]


def test_pull_asks_raw_sip_and_both_timeframes():
    seen = []

    def fetch(sym, tf, start, end, key, secret, feed, adjustment):
        seen.append((sym, tf, feed, adjustment))
        return pd.DataFrame()
    got = px.pull(3, fetch=fetch, keys=("k", "s"), now=dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc))
    assert got == {"1m": [], "5m": []}
    assert seen == [("QQQ", "1Min", "sip", "raw"), ("QQQ", "5Min", "sip", "raw")]


def test_load_ext_prefers_alpaca_per_day(tmp_path):
    def write(p, rows):
        qb.merge_bar_csv(str(p), rows)
    yf1, al1 = tmp_path / "y1.csv", tmp_path / "a1.csv"
    write(yf1, [(_ep("2026-10-29 08:00"), 1, 1, 1, 1, 1), (_ep("2026-10-30 08:00"), 2, 2, 2, 2, 2)])
    write(al1, [(_ep("2026-10-30 08:00"), 9, 9, 9, 9, 9)])
    paths = {"ext": {"1m": str(yf1), "5m": str(tmp_path / "y5.csv")},
             "ext_alpaca": {"1m": str(al1), "5m": str(tmp_path / "a5.csv")}}
    out = qb.load_ext(paths)
    assert out["1m"]["2026-10-30"][0][4] == 9.0 and out["1m"]["2026-10-29"][0][4] == 1.0
    assert out["_src"]["2026-10-30"] == qb.EXT_SRC_ALPACA and out["_src"]["2026-10-29"] == qb.EXT_SRC_YF
