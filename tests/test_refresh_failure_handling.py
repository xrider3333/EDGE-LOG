"""A refresh that half-worked must not report success, skip the rest, or burn the day's slot.

FROM MANAGER's read-only build review of 2026-09-30 (findings 1, 2, 7, 8, 9), all against code
I shipped on 09-29/30. The nightly refresh chain went live that evening and these are the ways
it could lose data quietly:

  1. ONE REFUSED OR LOCKED WRITE KILLED THE REST. build_adjusted_masters wrote 19 masters in a
     loop with no try. os.replace onto a master a backtest has open raises PermissionError after
     the 4s retry budget, and the write guard raises when a parent legitimately shrank. Either
     ended the loop - and because the "-> ADJ_" line prints BEFORE the write, the log still read
     like success. The caller then ignored the exit code, threw stderr away, and marked the day
     done, so the retry was blocked until the next evening. Same shape in the Yahoo refresher
     (finding 7), where NQ 5m RTH - the master pushed to the box for live KEEL sizing - sorts
     late enough to be a likely casualty.

  2. A FORCED STARTUP RUN ATE THE EVENING SLOT. A restart at 15:08 ET marked the day done, so
     the post-close refresh was skipped and every coarse and roll-corrected master missed the
     last hour of the session until the following night.

  9. THE DAILY .bak COPIES WERE NEVER PRUNED - a full copy of each coarse master every night,
     inside the OneDrive-synced uploads folder.

Also: data-health only ever checked the no-adjust family, so a stale roll-corrected twin - the
exact thing the nightly rebuild exists to prevent - was never flagged.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import augur_refresh as ar  # noqa: E402


class _Out:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


ET = "US/Eastern"


def _t(stamp):
    return pd.Timestamp(stamp, tz=ET)


# ================================================= 1. a failed tool is never a silent success

def test_a_nonzero_exit_produces_a_loud_line():
    lines = ar._trouble(_Out(returncode=1, stderr="MasterShrank: refusing to write ADJ_NQ_5m_RTH"))
    assert lines and "FAILED" in lines[0] and "INCOMPLETE" in lines[0]
    assert any("MasterShrank" in l for l in lines), "stderr must reach the caller"


def test_a_clean_exit_adds_nothing():
    assert ar._trouble(_Out(returncode=0, stderr="noise")) == []


def test_the_stderr_tail_is_included_not_discarded():
    """The refusal message only ever appears on stderr. Throwing it away is what made a
    half-finished build indistinguishable from a whole one."""
    err = "\n".join("line %d" % i for i in range(20))
    lines = ar._trouble(_Out(returncode=2, stderr=err))
    assert any("line 19" in l for l in lines)


def test_a_failed_run_does_NOT_mark_the_day_done(tmp_path):
    """This is the part that blocked the retry until the next evening."""
    st = str(tmp_path / "s.json")
    assert ar._mark_done_if_it_counts(1, _t("2026-09-30 18:00"), st) is False
    assert not os.path.exists(st)
    assert ar.coarse_refresh_due(_t("2026-09-30 18:30"), st), "the next pass must try again"


def test_a_successful_evening_run_marks_the_day_done(tmp_path):
    st = str(tmp_path / "s.json")
    assert ar._mark_done_if_it_counts(0, _t("2026-09-30 18:00"), st) is True
    assert not ar.coarse_refresh_due(_t("2026-09-30 20:00"), st)


# ========================================== 2. a forced run before the cutoff is not the day's

def test_a_forced_midsession_run_leaves_the_evening_slot_open(tmp_path):
    """A restart at 15:08 ET used to consume the slot, so every coarse and roll-corrected
    master then missed the last hour of the session for a whole day."""
    st = str(tmp_path / "s.json")
    assert ar._mark_done_if_it_counts(0, _t("2026-09-30 15:08"), st) is False
    assert ar.coarse_refresh_due(_t("2026-09-30 17:30"), st), "the post-close refresh must run"


def test_a_forced_run_AFTER_the_cutoff_does_count(tmp_path):
    """Otherwise an evening restart would rebuild twice in a row for no reason."""
    st = str(tmp_path / "s.json")
    assert ar._mark_done_if_it_counts(0, _t("2026-09-30 19:00"), st) is True


def test_the_cutoff_used_here_is_the_same_one_the_gate_uses(tmp_path):
    """Two different cutoffs would leave a window that is neither due nor markable."""
    st = str(tmp_path / "s.json")
    h, m = ar.COARSE_AFTER_ET
    just_before = _t("2026-09-30 %02d:%02d" % (h, m)) - pd.Timedelta(minutes=1)
    assert not ar.coarse_refresh_due(just_before, st)
    assert ar._mark_done_if_it_counts(0, just_before, st) is False


# ============================================ the tools themselves carry on and then complain

@pytest.mark.parametrize("rel,marker", [
    ("tools/build_adjusted_masters.py", "Carrying on with the next master"),
    ("tools/refresh_noadj_yahoo.py", "Carrying on with the next master"),
])
def test_each_writer_loop_continues_past_one_failure(rel, marker):
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    assert marker in src
    assert "failures.append" in src, "%s must remember what it skipped" % rel
    assert "return 1 if failures else 0" in src, "%s must say so in its exit code" % rel


def test_the_failure_report_goes_to_stdout_where_the_caller_reads_it():
    """The caller keeps stdout and (now) the stderr tail. A report only on stderr was how the
    first version hid a refusal."""
    for rel in ("tools/build_adjusted_masters.py", "tools/refresh_noadj_yahoo.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "were NOT written" in src or "NOT WRITTEN" in src


def test_the_yahoo_tool_exits_with_its_own_code():
    src = open(os.path.join(ROOT, "tools", "refresh_noadj_yahoo.py"), encoding="utf-8").read()
    assert "sys.exit(main() or 0)" in src, "main's code must leave the process"


def test_the_caller_keeps_the_new_failure_lines():
    src = open(os.path.join(ROOT, "api", "augur_refresh.py"), encoding="utf-8").read()
    assert "_trouble(out)" in src and "_mark_done_if_it_counts(out.returncode" in src
    assert "_mark_coarse_done(now, state_path)\n    return lines" not in src, (
        "the unconditional marker call must be gone")


# ===================================================== 9. the nightly .bak copies are pruned

def test_backups_are_pruned_and_a_few_are_kept():
    src = open(os.path.join(ROOT, "tools", "refresh_resampled_masters.py"),
               encoding="utf-8").read()
    assert "KEEP_BACKUPS" in src and "os.remove(p)" in src
    import tools.refresh_resampled_masters as rrm
    assert 1 <= rrm.KEEP_BACKUPS <= 5, "a nightly full copy per master cannot be unbounded"


def test_the_copy_is_made_before_anything_is_pruned():
    """Pruning first would leave a moment with no backup at all - the moment it matters."""
    src = open(os.path.join(ROOT, "tools", "refresh_resampled_masters.py"),
               encoding="utf-8").read()
    i = src.index("shutil.copy2(mpath, bak)")
    assert i < src.index("os.remove(p)", i)


# ======================================= data-health now sees the roll-corrected family too

def test_data_health_checks_the_adjusted_masters_as_well():
    """A stale ADJ_ master was invisible to the health check, which is how two days of
    staleness went unnoticed until another lane spotted it."""
    src = open(os.path.join(ROOT, "api", "data_health.py"), encoding="utf-8").read()
    assert "db_adj_%" in src and "db_fadj_%" in src
