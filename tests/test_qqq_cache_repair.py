r"""tools/qqq_cache_repair.py -- drops torn-write rows from the QQQ bar cache.

The rows here are the REAL ones seen in C:\EdgeLog\ohlc on 2026-09-18, not invented
shapes: time=812 / 9990234375 / 99877929688 with shifted OHLC columns, which made
pd.to_datetime(unit="s") raise OutOfBoundsDatetime and failed every test in
tests/test_cloud_signal.py.
"""
import os

import pandas as pd
import pytest

from tools import qqq_cache_repair as R


GOOD = [
    # time, open, high, low, close, volume
    (1789761420, 721.10, 721.40, 721.00, 721.28, 1_900_000.0),
    (1789761480, 721.28, 721.45, 721.10, 721.36, 2_252_861.0),
]
# exactly the shapes found on 2026-09-18
TORN = [
    (812,         716.505005, 55003.0, None,     None, None),
    (9990234375,  710.859985, 711.289978, 194722.0, None, None),
    (99877929688, 710.460022, 60669.0, None,     None, None),
]
COLS = ["time", "open", "high", "low", "close", "volume"]


def _write(path, rows):
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)


def _home(tmp_path, rows_1m, rows_5m=None):
    ohlc = tmp_path / "ohlc"
    ohlc.mkdir(parents=True, exist_ok=True)
    _write(ohlc / "QQQ_1m.csv", rows_1m)
    _write(ohlc / "QQQ_5m.csv", rows_5m if rows_5m is not None else GOOD)
    return ohlc


# ── classification ────────────────────────────────────────────────────────────────

def test_torn_rows_are_rejected_and_good_rows_kept():
    df = pd.DataFrame(GOOD + TORN, columns=COLS)
    keep, reasons = R.classify(df)
    assert list(keep) == [True, True, False, False, False]
    assert all("not an epoch second" in reasons[i] for i in (2, 3, 4))


def test_a_row_missing_a_close_is_rejected_even_with_a_sane_time():
    df = pd.DataFrame(GOOD + [(1789761540, 721.0, 721.5, 720.9, None, 10.0)], columns=COLS)
    keep, reasons = R.classify(df)
    assert list(keep) == [True, True, False]
    assert "missing open/high/low/close" in reasons[2]


def test_a_millisecond_epoch_is_rejected():
    """The pandas-3 drift class: seconds x 1000 must never pass as a timestamp."""
    df = pd.DataFrame([(1789761480000, 721.0, 721.5, 720.9, 721.2, 10.0)], columns=COLS)
    assert list(R.classify(df)[0]) == [False]


def test_repair_sorts_and_collapses_duplicate_timestamps():
    rows = [GOOD[1], GOOD[0], (GOOD[0][0], 1.0, 2.0, 0.5, 1.5, 1.0)]
    out = R.repair_frame(pd.DataFrame(rows, columns=COLS))
    assert list(out["time"]) == [GOOD[0][0], GOOD[1][0]]
    assert out.iloc[0]["close"] == 1.5      # last write for that timestamp wins
    assert str(out["time"].dtype) == "int64"


# ── the tool end to end ───────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(tmp_path, capsys):
    ohlc = _home(tmp_path, GOOD + TORN)
    before = (ohlc / "QQQ_1m.csv").read_bytes()

    assert R.main(["--home", str(tmp_path)]) == 0

    assert (ohlc / "QQQ_1m.csv").read_bytes() == before
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "3 malformed" in out
    assert not [p for p in ohlc.iterdir() if ".corrupt-" in p.name]


def test_apply_backs_up_then_rewrites(tmp_path, capsys):
    ohlc = _home(tmp_path, GOOD + TORN)

    assert R.main(["--home", str(tmp_path), "--apply"]) == 0

    kept = pd.read_csv(ohlc / "QQQ_1m.csv")
    assert list(kept["time"]) == [GOOD[0][0], GOOD[1][0]]
    backups = [p for p in ohlc.iterdir() if ".corrupt-" in p.name]
    assert len(backups) == 1
    assert len(pd.read_csv(backups[0])) == len(GOOD) + len(TORN)   # original preserved
    assert not [p for p in ohlc.iterdir() if p.name.endswith(".tmp")]


def test_a_clean_cache_is_left_completely_alone(tmp_path, capsys):
    ohlc = _home(tmp_path, GOOD)
    before = (ohlc / "QQQ_1m.csv").read_bytes()

    assert R.main(["--home", str(tmp_path), "--apply"]) == 0

    assert (ohlc / "QQQ_1m.csv").read_bytes() == before
    assert "nothing to repair" in capsys.readouterr().out
    assert not [p for p in ohlc.iterdir() if ".corrupt-" in p.name]


def test_a_missing_cache_file_is_reported_not_fatal(tmp_path, capsys):
    ohlc = _home(tmp_path, GOOD + TORN)
    os.remove(ohlc / "QQQ_5m.csv")

    assert R.main(["--home", str(tmp_path), "--apply"]) == 0
    assert "not present" in capsys.readouterr().out
