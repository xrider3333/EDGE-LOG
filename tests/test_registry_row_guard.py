"""A truncation must not launder itself through one bad read (MANAGER review finding 6).

WHAT ACTUALLY HAPPENED ON 2026-09-29, corrected. My first account blamed an unfinished write by
the 17:20 ET box push. The push log says otherwise - "REFRESH ok: NOADJ_NQ_5m_RTH.csv: +40 bars"
at 14:20:39 local - so that write completed. The tail the damaged file then grew starts
2026-09-22, a SEVEN-day Yahoo window, which is optimizer's pull; the box-push tool pulls sixty.

So the sequence was: refresh_noadj_yahoo was rewriting NOADJ_NQ_5m_ETH IN PLACE with a bare
to_csv when the runner's own startup refresh read the same file, got 625,491 of 1,144,508 rows -
a valid CSV that simply stopped early - appended a 7-day window to that stump, and
save_master_csv atomically installed it and re-registered it at 627,069 rows.

Two consequences the first fix missed:
  - save_master_csv was ALREADY atomic, so it never left a half file - but nothing stopped it
    INSTALLING a short one. It had no row guard at all.
  - write_master_csv compared the new frame against the FILE ON DISK. The stump was already on
    disk, so appending to it read as growth. The registry's count is the last size a complete
    write recorded, which is the comparison that catches this.

Also: the runner logged only the first 12 change lines, so on the night it mattered the line
showing the row count collapsing was the evidence that got cut.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.master_write import (MasterShrank, read_row_count,  # noqa: E402
                                       write_master_csv)


def _frame(n, start=1_700_000_000):
    return pd.DataFrame({"time": [start + i * 300 for i in range(n)],
                         "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10})


# ============================================ the registry count, not just the file on disk

def test_appending_to_a_stump_on_disk_is_refused_when_the_registry_knows_better():
    """THE 09-29 SHAPE, scaled down. The file on disk is already short; the new frame is
    bigger than the file but far smaller than the master really was. A disk-only comparison
    calls that growth and installs it."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "NOADJ_NQ_5m_ETH.csv")
        write_master_csv(_frame(625), p)                      # the stump, already on disk
        # a disk-only check would accept this: 627 > 625
        assert write_master_csv(_frame(627), p, known_rows=None) == 627
        # with the registry's real count it must refuse
        write_master_csv(_frame(625), p, allow_shrink=True, shrink_reason="reset for the test")
        with pytest.raises(MasterShrank) as e:
            write_master_csv(_frame(627), p, known_rows=1_144)
        assert "registry" in str(e.value)


def test_the_message_says_which_count_it_compared_against():
    """A refusal a human cannot act on is only half a guard."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.csv")
        write_master_csv(_frame(100), p)
        with pytest.raises(MasterShrank) as e:
            write_master_csv(_frame(50), p)
        assert "on disk" in str(e.value)


def test_the_larger_of_disk_and_registry_wins():
    """Either source can be the stale one: the registry can lag a legitimate append, and the
    file can be a stump. Taking the larger is the only safe reading."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.csv")
        write_master_csv(_frame(500), p)
        # registry behind the file: the file still protects
        with pytest.raises(MasterShrank):
            write_master_csv(_frame(400), p, known_rows=100)
        # registry ahead of the file: the registry protects
        with pytest.raises(MasterShrank):
            write_master_csv(_frame(600), p, known_rows=900)


def test_a_missing_registry_count_falls_back_to_the_file():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.csv")
        write_master_csv(_frame(100), p)
        with pytest.raises(MasterShrank):
            write_master_csv(_frame(40), p, known_rows=None)
        assert read_row_count(p) == 100


def test_a_deliberate_rebuild_still_passes_both_checks():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.csv")
        write_master_csv(_frame(500), p)
        assert write_master_csv(_frame(50), p, known_rows=900, allow_shrink=True,
                               shrink_reason="rebuilt from a corrected parent") == 50


# ======================================= the path that actually installed the stump

def test_the_optimizer_master_save_now_has_a_row_guard():
    """save_master_csv was atomic but unguarded - it could not leave a half file, and nothing
    stopped it installing one."""
    src = open(os.path.join(ROOT, "optimizer.py"), encoding="utf-8").read()
    i = src.index("def save_master_csv")
    body = src[i:i + 6000]
    assert "SELECT rows FROM csv_files WHERE filename=?" in body
    assert "REFUSED to save" in body
    assert "os.replace" in body and "fsync" in body, "and it must still be atomic"


def test_the_guard_runs_before_any_bytes_are_written():
    """Refusing after the temp file exists would leave litter and, worse, imply the write was
    attempted. The check belongs before df_to_tv_csv_bytes."""
    src = open(os.path.join(ROOT, "optimizer.py"), encoding="utf-8").read()
    i = src.index("def save_master_csv")
    body = src[i:i + 6000]
    assert body.index("REFUSED to save") < body.index("raw = df_to_tv_csv_bytes(df)")


def test_an_unknown_registry_count_is_not_treated_as_zero():
    """Unknown must never read as 'it had no rows', which would wave every write through."""
    src = open(os.path.join(ROOT, "optimizer.py"), encoding="utf-8").read()
    i = src.index("def save_master_csv")
    body = src[i:i + 6000]
    assert "_known = None" in body and "if _known and len(df) < _known" in body


def test_the_yahoo_refresher_passes_the_registry_count():
    src = open(os.path.join(ROOT, "tools", "refresh_noadj_yahoo.py"), encoding="utf-8").read()
    assert "known_rows=known_rows" in src
    assert "session,rows FROM csv_files" in src, "it has to select the count to pass it"


# ================================================= the evidence must not fall off the log

def test_every_change_line_is_logged_not_the_first_twelve():
    """On the night NOADJ_NQ_5m_ETH was truncated the pass logged '15 master(s) updated' and
    only 12 change lines - the row count collapsing was in the three that were cut."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    assert "for line in changes[:12]:" not in src
    assert "for line in changes:" in src
