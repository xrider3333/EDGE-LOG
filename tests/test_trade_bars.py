"""api/trade_bars.py - the byte-seeking master reader, the roll-week shift and the packing."""
import pandas as pd

from api import trade_bars as tb


def _master(tmp_path, n=5000, t0=1_790_000_000):
    p = tmp_path / "m.csv"
    with open(p, "w") as f:
        f.write("time,open,high,low,close,volume,source\n")
        for i in range(n):
            px = 100 + i * 0.25
            f.write(f"{t0 + i * 60},{px},{px + 1},{px - 1},{px + 0.5},{i},x\n")
    return str(p), t0


def test_read_window_matches_a_full_read(tmp_path):
    path, t0 = _master(tmp_path)
    lo, hi = t0 + 1234 * 60, t0 + 1300 * 60
    got = tb._read_window(path, lo, hi)
    full = pd.read_csv(path)
    want = full[(full.time >= lo) & (full.time <= hi)]
    assert list(got["time"]) == list(want["time"])
    assert list(got["close"]) == list(want["close"])


def test_read_window_edges(tmp_path):
    path, t0 = _master(tmp_path, n=50)
    assert tb._read_window(path, t0, t0)["time"].tolist() == [t0]
    assert tb._read_window(path, t0 + 10_000 * 60, t0 + 20_000 * 60) is None


def test_shift_only_when_the_fill_misses_its_bar():
    df = pd.DataFrame({"time": [0, 60], "open": [10, 11], "high": [12, 13], "low": [9, 10], "close": [11, 12], "volume": [1, 1]})
    assert tb._shift_onto_fill(df, 11.5, 30, 60) == 0.0          # inside the bar
    assert tb._shift_onto_fill(df, 76.0, 30, 60) == 65.0         # a roll week: the other contract month


def test_pack_offsets_and_shift():
    df = pd.DataFrame({"time": [600, 660, 780], "open": [1.0, 2.0, 3.0], "high": [1.5, 2.5, 3.5],
                       "low": [0.5, 1.5, 2.5], "close": [1.25, 2.25, 3.25], "volume": [5, 6, 7]})
    pk = tb._pack(df, 60, shift=1.0)
    assert pk["t0"] == 600 and pk["step"] == 60
    assert pk["s"].split(";")[2] == "3,4,4.5,3.5,4.25,7"


def test_signature_ignores_notes_but_not_prices():
    a = {"date": "2026-09-30", "entryTime": "09:32", "exitTime": "09:45", "entry": 1, "exit": 2, "type": "LONG", "symbol": "MNQ", "size": 1, "notes": "x"}
    b = dict(a, notes="changed")
    c = dict(a, exit=3)
    assert tb.signature(a) == tb.signature(b) != tb.signature(c)


def test_same_score_needs_the_same_signature():
    a = {"total": 7, "max": 9, "na_count": 0, "points": [1], "trend": None, "sig": "x", "signal_bar": "s"}
    assert tb._same_score(a, dict(a))
    assert not tb._same_score(a, dict(a, sig="y"))
    assert not tb._same_score(a, None)
