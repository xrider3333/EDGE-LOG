"""api/gate_live.py -- the live ML gate must not keep scoring a stale bar window.

WHY (2026-09-21). The gate service started while NinjaTrader was down; when the 10s
capture came back the long-running process kept serving Friday's last bar, so
NinjaTrader's NOISE entry hit the bar interlock and traded UNGATED. A fresh process read
the same files correctly. These tests rebuild that state -- cached ticks far behind the
file on disk -- and pin that a refresh notices and rebuilds from disk.
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from api import gate_live as g
from api import paper as p

ET = "US/Eastern"


def _unix(s):
    return int(pd.Timestamp(s, tz=ET).tz_convert("UTC").timestamp())


@pytest.fixture
def world(tmp_path, monkeypatch):
    # a 3-bar "master" ending Friday 15:55 ET
    idx = pd.DatetimeIndex(pd.to_datetime(["2026-09-18 15:45", "2026-09-18 15:50",
                                           "2026-09-18 15:55"]).tz_localize(ET))
    master = {"index": idx, "open": np.ones(3), "high": np.ones(3), "low": np.ones(3),
              "close": np.ones(3), "volume": np.ones(3)}
    import augur_engine.data as d
    monkeypatch.setattr(d, "find_master", lambda *a, **k: "fake-master")
    monkeypatch.setattr(d, "load_master_arrays",
                        lambda *a, **k: {k2: (v.copy() if hasattr(v, "copy") else v) for k2, v in master.items()})
    # 10s file: one Friday row, then Monday 10:30:10 .. 10:40:00 ET
    f = tmp_path / "NQ_10s.csv"
    rows = ["time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt",
            f"{_unix('2026-09-18 14:06:00')},1,1,1,1,1,0,0,0,1,1"]
    t = _unix("2026-09-21 10:30:10")
    while t <= _unix("2026-09-21 10:40:00"):
        rows.append(f"{t},2,2,2,2,1,0,0,0,1,1")
        t += 10
    f.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(p, "_ticks_path", lambda *a, **k: str(f))
    monkeypatch.setattr(g, "_log", lambda *a, **k: None)
    g._live_caches.clear()
    yield {"file": f, "master": master}
    g._live_caches.clear()


LEG = {"key": "NOISE_H_RF", "instrument": "NQ", "timeframe": "5m", "session": "rth"}


def test_file_last_tick_reads_the_tail(world):
    assert g._file_last_tick(str(world["file"])) == _unix("2026-09-21 10:40:00")
    assert g._file_last_tick(str(world["file"]) + ".missing") is None


def test_a_fresh_refresh_reaches_today(world):
    arr = g._refresh_live_arrays(LEG)
    assert arr["index"][-1] >= pd.Timestamp("2026-09-21 10:30", tz=ET)


def test_stale_incremental_state_is_rebuilt(world):
    # this morning's state: the cache believes it has read the whole file, but holds only Friday
    c = g._cache_for(LEG)
    c["arrays"] = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in world["master"].items()}
    c["loaded_day"] = dt.datetime.now().strftime("%Y-%m-%d")
    c["tick_path"] = str(world["file"])
    c["tick_offset"] = world["file"].stat().st_size
    c["tick_df"] = pd.DataFrame({"time": [_unix("2026-09-18 14:06:00")], "open": [1.0], "high": [1.0],
                                 "low": [1.0], "close": [1.0], "volume": [1]})
    arr = g._refresh_live_arrays(LEG)
    assert arr["index"][-1] >= pd.Timestamp("2026-09-21 10:30", tz=ET), "stale cache was not rebuilt"


def test_up_to_date_cache_is_not_rebuilt(world):
    g._refresh_live_arrays(LEG)
    resets = []
    orig = g._reset_live_cache
    g._reset_live_cache = lambda leg, why: resets.append(why) or orig(leg, why)
    try:
        g._refresh_live_arrays(LEG)
    finally:
        g._reset_live_cache = orig
    assert resets == [], "a cache that matches the file must not be thrown away every request"
