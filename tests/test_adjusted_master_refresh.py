"""The roll-corrected (ADJ_/FADJ_) masters must refresh on their own, and refresh LAST.

WHY THIS EXISTS (2026-09-30, flagged by the ROC-frontier lane). The 19 ADJ_/FADJ_ masters are
rebuilt from the no-adjust ones, and NOTHING scheduled that rebuild - it had been run by hand
exactly once, on 09-28. Two days later the no-adjust masters were current and the corrected
twins were not, so anything pinned to them was quietly reading stale bars: Frontier's
vol-target shadow signal, and any ES book run past 2026-09-14. No guard refused them and
nothing failed; the tool simply never ran again.

The three things pinned here:
  1. They are on the once-an-evening refresh, with their OWN day marker, so a failure in the
     coarse step cannot make them skip a day or run twice.
  2. They run LAST - after the Yahoo pull and after the coarse resample - because each step
     reads what the one before it wrote.
  3. An unpinned master lookup still returns no-adjust data. Registering these masters once
     re-pointed every unpinned lookup at back-adjusted prices, including the live NT gate
     (see docs/ROLL_ADJUSTED_MASTERS.md); touching this refresh must never reopen that.
"""
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import augur_refresh  # noqa: E402


# ------------------------------------------------------------------- 1. when it runs

def test_it_has_its_own_day_marker_not_the_coarse_one():
    """Sharing a marker would mean a coarse failure silently skipped the rebuild for the day,
    or a rebuild marked the coarse step done. Separate files, one job each."""
    assert augur_refresh.ADJUSTED_STATE != augur_refresh.COARSE_STATE
    assert "adjusted" in os.path.basename(augur_refresh.ADJUSTED_STATE)


def test_not_due_before_the_evening_cutoff(tmp_path):
    st = str(tmp_path / "adj.json")
    for t in ("2026-09-30 09:35", "2026-09-30 16:10", "2026-09-30 17:24"):
        assert not augur_refresh.adjusted_refresh_due(pd.Timestamp(t, tz="US/Eastern"), st)


def test_due_after_the_cutoff(tmp_path):
    st = str(tmp_path / "adj.json")
    assert augur_refresh.adjusted_refresh_due(
        pd.Timestamp("2026-09-30 17:26", tz="US/Eastern"), st)


def test_once_a_day_not_once_a_pass(tmp_path):
    """A full rewrite of 19 files, some with five million rows. Every pass would be absurd."""
    st = str(tmp_path / "adj.json")
    evening = pd.Timestamp("2026-09-30 18:00", tz="US/Eastern")
    assert augur_refresh.adjusted_refresh_due(evening, st)
    augur_refresh._mark_coarse_done(evening, st)
    assert not augur_refresh.adjusted_refresh_due(evening, st)
    assert augur_refresh.adjusted_refresh_due(
        pd.Timestamp("2026-10-01 18:00", tz="US/Eastern"), st)


def test_the_marker_records_the_ET_day(tmp_path):
    st = str(tmp_path / "adj.json")
    augur_refresh._mark_coarse_done(pd.Timestamp("2026-09-30 23:45", tz="US/Eastern"), st)
    assert json.load(open(st, encoding="utf-8"))["last_et_date"] == "2026-09-30"


def test_a_normal_pass_consults_the_gate(monkeypatch):
    calls = []
    monkeypatch.setattr(augur_refresh, "coarse_refresh_due",
                        lambda *a, **k: calls.append("gated") or False)
    assert augur_refresh.run_adjusted_refresh(force=False) == []
    assert calls == ["gated"]


# ------------------------------------------------------------------- 2. it runs LAST

def test_the_runner_rebuilds_the_twins_after_both_parents_are_written():
    """Order is the whole correctness argument: Yahoo -> coarse resample -> adjusted rebuild.
    Rebuilding first would bake yesterday's tail into today's corrected bars."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    i_yahoo = src.index("changes = run_auto_refresh()")
    i_coarse = src.index("run_coarse_refresh(force=")
    i_adj = src.index("run_adjusted_refresh(force=")
    assert i_yahoo < i_coarse < i_adj


def test_the_command_line_entry_point_keeps_the_same_order():
    src = open(os.path.join(ROOT, "api", "augur_refresh.py"), encoding="utf-8").read()
    tail = src[src.index('if __name__ == "__main__":'):]
    assert tail.index("run_coarse_refresh(") < tail.index("run_adjusted_refresh(")


def test_a_failure_in_the_rebuild_cannot_kill_the_refresh():
    """The refresh keeps the runner's data current; a rebuild that throws must be reported and
    stepped over, not allowed to stop the pass."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    i = src.index("run_adjusted_refresh(force=")
    window = src[i - 400:i + 600]
    assert "try:" in window and "except Exception" in window
    assert "adjusted rebuild skipped" in window


def test_the_runner_forces_it_at_startup():
    """A freshly restarted fleet must not serve a stale corrected master while it waits for
    the evening."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    assert 'run_adjusted_refresh(force=(tag == "startup"))' in src


# ------------------------------------------------- 3. the regression this must never reopen

def test_an_unpinned_lookup_still_returns_no_adjust_data():
    """Registering the adjusted masters once re-pointed EVERY unpinned lookup at back-adjusted
    prices, including the live NT gate. Rebuilding them re-registers rows, so this stays
    pinned right next to the refresh that does it."""
    from augur_engine import data
    for inst, tf, sess in (("NQ", "5m", "rth"), ("NQ", "1m", "eth"), ("ES", "30m", "rth")):
        m = data.find_master(inst, tf, session=sess)
        if m is None:
            pytest.skip("no %s %s %s master in this checkout" % (inst, tf, sess))
        assert not data.is_adjusted_source(m.get("source")), (
            "%s %s %s unpinned lookup returned %s" % (inst, tf, sess, m.get("filename")))


def test_the_rebuild_is_the_committed_tool_not_a_copy():
    """Two implementations of the adjustment would drift. The refresh shells out to the same
    tool a human runs, so there is one behaviour to reason about."""
    src = open(os.path.join(ROOT, "api", "augur_refresh.py"), encoding="utf-8").read()
    assert "build_adjusted_masters.py" in src
    assert '"--apply"' in src
