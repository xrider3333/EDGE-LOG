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


def test_incremental_read_does_not_misalign_columns(world):
    """A real capture row has 11 fields (time..rt); the incremental (headerless) read
    used to be told only the 6 kept names, so pandas treated the 5 extra leading fields
    as an index and shifted every value one column over -- `time` silently became
    `volume`'s value. This went unnoticed because the >60s self-heal reset almost always
    fired first and threw the corrupted read away (see _refresh_live_arrays); polling
    every few seconds (2026-09-26) makes the incremental path the common case, which is
    what surfaced it. A distinctive close price on the SECOND incremental append (after
    the cache is already warm, i.e. the buggy headerless branch) must come through
    unchanged."""
    g._refresh_live_arrays(LEG)             # first call: warms the cache (header parse)
    f = world["file"]
    with f.open("a", encoding="utf-8") as fh:
        t = _unix("2026-09-21 10:40:10")
        fh.write(f"{t},12345,12345,12345,12345,7,0,0,0,1,1\n")   # a second, real 11-field row
    arr = g._refresh_live_arrays(LEG)
    tdf = g._cache_for(LEG)["tick_df"]
    row = tdf[tdf["time"] == t]
    assert len(row) == 1, "the appended row went missing or was mis-keyed"
    assert row.iloc[0]["close"] == 12345, "close was corrupted by a column-misaligned parse"
    assert row.iloc[0]["volume"] == 7, "volume was corrupted by a column-misaligned parse"


def test_refresh_holds_back_an_incomplete_trailing_bucket(world):
    """The 09-22 09:45 ET ORDERED take was scored on a 09:40 bar missing its last ~50s
    of ticks (ROLL_AUDIT.md 4.5.2) -- the capture had not reached the bucket's END yet.
    A resampled bucket must only be appended once the capture covers it fully."""
    f = world["file"]
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines[-1].split(",")[0] == str(_unix("2026-09-21 10:40:00"))
    f.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")   # drop the boundary row

    arr = g._refresh_live_arrays(LEG)
    assert arr["index"][-1] == pd.Timestamp("2026-09-21 10:30", tz=ET), \
        "the incomplete 10:35 bucket must not be appended"
    assert g._cache_for(LEG)["covered_through"] == _unix("2026-09-21 10:39:50")

    # the capture catches up: the row that completes the bucket lands
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"{_unix('2026-09-21 10:40:00')},2,2,2,2,1,0,0,0,1,1\n")
    arr2 = g._refresh_live_arrays(LEG)
    assert arr2["index"][-1] == pd.Timestamp("2026-09-21 10:35", tz=ET), \
        "the now-complete bucket should be picked up whole on the next call"
    assert g._cache_for(LEG)["covered_through"] == _unix("2026-09-21 10:40:00")


# ── decide() reads a ready snapshot only -- no I/O, no rebuild (2026-09-26 fix) ────────
class _StubPipe:
    def predict_proba(self, x):
        return np.array([[0.4, 0.6]])


DLEG = {"key": "TEST_LEG", "instrument": "NQ", "timeframe": "5m", "session": "rth"}


def _synthetic_arrays(n, end_ts, step_min=5):
    idx = pd.date_range(end=pd.Timestamp(end_ts, tz=ET), periods=n, freq=f"{step_min}min")
    return {"index": idx, "open": np.ones(n), "high": np.ones(n), "low": np.ones(n),
            "close": np.ones(n), "volume": np.ones(n), "day_id": np.zeros(n, dtype="int64")}


def _seed_decide_cache(covered_through, end_ts="2026-09-22 09:40:00", n=250):
    c = g._cache_for(DLEG)
    c["arrays"] = _synthetic_arrays(n, end_ts)
    c["covered_through"] = covered_through
    return c


@pytest.fixture
def decide_world(monkeypatch):
    monkeypatch.setattr(g, "_gated_legs", lambda: [DLEG])
    art = {"model": "rf", "mode": "cut", "threshold": 0.5, "pipe": _StubPipe(),
           "feature_names": ["f0"], "recycle_factor": 1.0,
           "trained_through": "2026-09-01"}
    monkeypatch.setattr(g, "_load_artifact", lambda key: art)
    import augur_engine.ml_gate as mlg
    monkeypatch.setattr(mlg, "entry_features_causal",
                        lambda arr2: (np.zeros((len(arr2["index"]), 1)), ["f0"]))
    monkeypatch.setattr(g, "_log", lambda *a, **k: None)
    g._live_caches.clear()
    yield {"art": art}
    g._live_caches.clear()


def test_decide_never_touches_disk(decide_world):
    _seed_decide_cache(covered_through=_unix("2026-09-22 09:45:00"))

    def _boom(*a, **k):
        raise AssertionError("decide() must never call _refresh_live_arrays")
    orig = g._refresh_live_arrays
    g._refresh_live_arrays = _boom
    try:
        out = g.decide("TEST_LEG")
    finally:
        g._refresh_live_arrays = orig
    assert "error" not in out
    assert out["prob"] is not None
    assert out["ungated_fallback"] is False


def test_decide_is_fast_against_a_ready_cache(decide_world):
    _seed_decide_cache(covered_through=_unix("2026-09-22 09:45:00"))
    out = g.decide("TEST_LEG")
    assert out["elapsed_ms"] < 100, f"decide() took {out['elapsed_ms']}ms against a warm cache"


def test_stale_cache_is_not_rebuilt_by_decide(decide_world):
    # The cache is far behind (7342cc4's stale-Friday-bar shape), but decide() must use
    # it exactly as handed to it -- rebuilding is _bg_refresh_loop's job now, never
    # decide()'s (ROLL_AUDIT.md 4.5.2: the four 09-23 timeouts were this rebuild running
    # inside NinjaTrader's 300ms budget).
    _seed_decide_cache(covered_through=_unix("2026-08-14 15:55:00"), end_ts="2026-08-14 15:55:00")
    resets = []
    orig = g._reset_live_cache
    g._reset_live_cache = lambda leg, why: resets.append(why) or orig(leg, why)
    try:
        out = g.decide("TEST_LEG")     # no nt_bar -> no interlock, but still no rebuild
    finally:
        g._reset_live_cache = orig
    assert resets == [], "decide() must never trigger a cache reset/rebuild itself"
    assert out["prob"] is not None


def test_incomplete_bar_is_never_scored(decide_world):
    end_ts = "2026-09-22 09:40:00"           # last bucket the cache currently holds
    nt_bar = "2026-09-22T09:40:00-04:00"     # NinjaTrader believes THIS bar just closed
    # the capture covers only through 09:44:50 -- 10s short of the bar's 09:45:00 end
    _seed_decide_cache(covered_through=_unix("2026-09-22 09:44:50"), end_ts=end_ts)
    out = g.decide("TEST_LEG", nt_bar)
    assert out["bar_check"] == "incomplete"
    assert out["prob"] is None, "a partial bar must never be scored"
    assert out["take"] is True and out["ungated_fallback"] is True
    assert "INCOMPLETE_BAR" in out["error"]


def test_complete_bar_is_scored_normally(decide_world):
    end_ts = "2026-09-22 09:40:00"
    nt_bar = "2026-09-22T09:40:00-04:00"
    # the capture covers exactly through the bar's end -- safe to score
    _seed_decide_cache(covered_through=_unix("2026-09-22 09:45:00"), end_ts=end_ts)
    out = g.decide("TEST_LEG", nt_bar)
    assert out["bar_check"] == "ok"
    assert out["prob"] is not None
