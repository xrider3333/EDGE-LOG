"""No master write may lose rows, and none may be left half-written.

WHAT HAPPENED (2026-09-30). NOADJ_NQ_5m_ETH went from 1,144,508 rows to 627,287 - the whole
span 2019-05-21 to 2026-09-22 gone - and the registry agreed it was correct for a day. Two
defects, one after the other:

  1. `tools/refresh_noadj_yahoo.py` wrote each master with a bare `df.to_csv(path)` straight
     over the live file. Cut short, a ~34 MB write leaves a VALID CSV that simply stops early:
     625,491 of 1,144,508 rows. (`optimizer.save_master_csv` had been made atomic for exactly
     this reason years earlier; the fix never reached the standalone tools.)
  2. Nothing anywhere noticed a master SHRINKING. The next refresh read the stump, appended
     Yahoo's 7-day window on top, and wrote the registry row to match - turning a bad write
     into a blessed master. Only luck stopped a job reading it: no run started that night.

These tests hold both doors shut. The restore itself is not re-testable (the data is back), so
what is pinned here is the behaviour that makes the next one impossible.
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

def _discover_writers():
    """Every tool that writes a registered master, found by reading the tree.

    A hard-coded list was the first version of this and it was already wrong within a day:
    tools/backfill_1m_from_10s.py and tools/build_etf_masters.py both wrote masters with a bare
    to_csv and neither was listed (MANAGER review 2026-09-30, finding 8). A new writer must
    fail this file by existing, not by someone remembering to add it.
    """
    import glob
    found = []
    for p in sorted(glob.glob(os.path.join(ROOT, "tools", "*.py"))):
        src = open(p, encoding="utf-8", errors="replace").read()
        touches_registry = ("is_master" in src or "csv_files" in src)
        writes_a_frame = (".to_csv(" in src or "write_master_csv(" in src)
        if touches_registry and writes_a_frame:
            found.append("tools/" + os.path.basename(p))
    return found


WRITERS = _discover_writers()


def _frame(n, start=1_700_000_000):
    return pd.DataFrame({"time": [start + i * 300 for i in range(n)],
                         "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10})


# ------------------------------------------------------------------ losing rows is refused

def test_a_write_that_would_lose_rows_is_refused(tmp_path):
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(1000), p)
    with pytest.raises(MasterShrank):
        write_master_csv(_frame(500), p)


def test_the_old_master_is_still_intact_after_a_refusal(tmp_path):
    """The whole point: a refused write must cost nothing. If it left the file damaged the
    guard would be worse than no guard."""
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(1000), p)
    before = open(p, encoding="utf-8").read()
    with pytest.raises(MasterShrank):
        write_master_csv(_frame(10), p)
    assert open(p, encoding="utf-8").read() == before
    assert read_row_count(p) == 1000


def test_the_exact_shape_of_the_2026_09_30_loss_is_refused(tmp_path):
    """The real numbers, so this test names the incident it came from."""
    p = str(tmp_path / "NOADJ_NQ_5m_ETH.csv")
    write_master_csv(_frame(1_144_508 // 1000), p)          # scaled; the ratio is what matters
    with pytest.raises(MasterShrank) as e:
        write_master_csv(_frame(627_287 // 1000), p)
    assert "losing" in str(e.value)


def test_writing_zero_rows_is_always_refused(tmp_path):
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(10), p)
    with pytest.raises(MasterShrank):
        write_master_csv(_frame(0), p)


def test_growing_is_normal_and_unchanged(tmp_path):
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(100), p)
    assert write_master_csv(_frame(120), p) == 120
    assert read_row_count(p) == 120


def test_the_same_row_count_is_allowed(tmp_path):
    """A re-write that only corrects values (the partial-bucket repair does this) must pass."""
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(50), p)
    f = _frame(50)
    f.loc[49, "close"] = 9.0
    assert write_master_csv(f, p) == 50
    assert pd.read_csv(p)["close"].iloc[-1] == 9.0


def test_a_first_write_has_nothing_to_compare_against(tmp_path):
    assert write_master_csv(_frame(7), str(tmp_path / "new.csv")) == 7


# ------------------------------------------------- a deliberate shrink must say why in words

def test_a_deliberate_shrink_needs_a_stated_reason(tmp_path):
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(100), p)
    with pytest.raises(ValueError):
        write_master_csv(_frame(40), p, allow_shrink=True)      # no reason given
    assert write_master_csv(_frame(40), p, allow_shrink=True,
                            shrink_reason="rebuilt from a corrected parent") == 40


# ------------------------------------------------------------------------- atomic, always

def test_no_temp_file_is_left_behind(tmp_path):
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(20), p)
    assert [f for f in os.listdir(tmp_path) if ".tmp-" in f] == []


def test_a_refused_write_leaves_no_temp_file_either(tmp_path):
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(20), p)
    with pytest.raises(MasterShrank):
        write_master_csv(_frame(2), p)
    assert [f for f in os.listdir(tmp_path) if ".tmp-" in f] == []


def test_the_file_is_read_back_and_counted_before_it_is_installed(monkeypatch, tmp_path):
    """The defect was a write that stopped early but still parsed. Counting rows on the temp
    file - not on the frame in memory - is the only check that catches that, so if the
    readback disagrees the target must not be touched."""
    p = str(tmp_path / "m.csv")
    write_master_csv(_frame(100), p)
    before = open(p, encoding="utf-8").read()

    import augur_engine.master_write as mw
    real = mw.read_row_count

    def lying_count(path):
        return 3 if ".tmp-" in str(path) else real(path)      # pretend the write came up short

    monkeypatch.setattr(mw, "read_row_count", lying_count)
    with pytest.raises(IOError):
        mw.write_master_csv(_frame(200), p)
    assert open(p, encoding="utf-8").read() == before, "a short write must not be installed"


def test_an_unreadable_target_is_unknown_not_zero(tmp_path):
    """`read_row_count` returning 0 for an unreadable file would make every write look like
    growth - the opposite of what the guard is for."""
    p = tmp_path / "broken.csv"
    p.write_bytes(b"\x00\x01\x02 not a csv")
    assert read_row_count(str(p)) is None


# ------------------------------------------------------- every writer goes through the door

@pytest.mark.parametrize("rel", WRITERS)
def test_every_master_writer_uses_the_guard(rel):
    """A writer added later that calls to_csv on a master path directly would reopen exactly
    the hole this closes, so the check is on the source, not on behaviour."""
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    assert "write_master_csv" in src, f"{rel} must write masters through the guard"


@pytest.mark.parametrize("rel", WRITERS)
def test_no_writer_still_writes_a_master_with_a_bare_to_csv(rel):
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#") or ".to_csv(" not in s:
            continue
        # a to_csv into a master path is the thing being banned; writing a side report is fine
        assert not any(tok in s for tok in ("mpath", "os.path.join(UP", "(p, index", "(path,")), (
            f"{rel}: bare to_csv onto a master path -> {s}")


def test_the_optimizer_master_save_is_still_atomic():
    """optimizer.save_master_csv was already atomic and is the fourth writer; if someone
    simplifies it back to a direct write, the same incident returns by another door."""
    src = open(os.path.join(ROOT, "optimizer.py"), encoding="utf-8").read()
    i = src.index("def save_master_csv")
    body = src[i:i + 4000]
    assert "os.replace" in body and "fsync" in body
