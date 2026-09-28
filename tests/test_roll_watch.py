"""Measuring a contract roll the evening it happens (December 2026 and onward).

WHY THIS EXISTS. `databento_raw` stopped on 2026-06-07, so no future switch can be measured
the way the first 64 were. `tools/roll_watch.py` measures one from the two feeds we still
collect - the Yahoo-fed master and the NinjaTrader capture - by reading the step in the
spread between them. TTM's roll guard re-reads the table every run and the fake squeeze it
guards against fires 0-2 days after a roll, so the row has to be right the first time and it
has to land the same evening.

The tool's own `--selftest` re-derives the September 2026 answer from the real masters, which
is the end-to-end proof. These tests cover the parts that can be checked without reading a
gigabyte of CSV: the contract labelling, the appending, and the fact that the tool's
expectations still match what the table records.
"""
import csv
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import rolls  # noqa: E402
from tools import roll_watch as rw  # noqa: E402


def _sec(stamp):
    import pandas as pd
    return int(pd.Timestamp(stamp, tz="US/Eastern").timestamp())


# ------------------------------------------------------------------ contract labelling

def test_the_december_2026_pair_is_labelled_from_the_quarterly_cycle():
    """The December roll is the next one. Neither feed labels the contract, so these come
    from the calendar - but they still have to be right, because a human reads them."""
    assert rw.quarterly_pair("ES", _sec("2026-12-14 18:00")) == ("ESZ6", "ESH7")
    assert rw.quarterly_pair("NQ", _sec("2026-12-14 18:00")) == ("NQZ6", "NQH7")


def test_labels_roll_the_year_over_correctly_from_december_to_march():
    """December's next contract is MARCH OF THE FOLLOWING YEAR. Getting this wrong would put
    a 2027 contract in a 2026 row and nobody would notice until it mattered."""
    old, new = rw.quarterly_pair("ES", _sec("2026-12-14 18:00"))
    assert old.endswith("6") and new.endswith("7")


def test_a_switch_outside_any_roll_window_gets_no_label_rather_than_a_wrong_one():
    """If the measurement ever fires outside a roll window, the honest answer is no label."""
    assert rw.quarterly_pair("ES", _sec("2026-07-15 12:00")) == ("", "")


# ------------------------------------------------------------------------- appending

@pytest.fixture()
def table(tmp_path):
    """A copy of the real ES table, so the append is exercised against the real shape."""
    src = os.path.join(ROOT, "tools", "data", "rolls_ES.csv")
    shutil.copy(src, tmp_path / "rolls_ES.csv")
    return str(tmp_path)


def _best(minute, offset=61.0):
    return dict(minute=minute, offset=offset, med_before=0.0, med_after=offset,
                n_before=600, n_after=540, spread_before=0.0, spread_after=0.5,
                carry_prior=70.0, price=7700.0, n_shared=1140, tightest=0.5, clean=True,
                master_body=80.0, et="")


def test_appending_a_december_row_keeps_the_table_sorted_and_marks_it_measured(table):
    """The table is read in time order by roll_map; an out-of-order append would silently
    mis-map every switch after it."""
    sec = _sec("2026-12-14 18:00")
    row, err = rw.append_row("ES", _best(sec), table_dir=table, dry=False)
    assert err is None and row is not None
    assert row["status"] == "measured", "never 'exact' - that is for contract-level raw data"
    assert row["source"] == "capture_spread"
    assert row["old"] == "ESZ6" and row["new"] == "ESH7"

    with open(os.path.join(table, "rolls_ES.csv"), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    secs = [int(r["switch_sec"]) for r in rows]
    assert secs == sorted(secs), "the table must stay in time order"
    assert any(int(r["switch_sec"]) == sec for r in rows)


def test_appending_the_same_switch_twice_is_refused(table):
    """The nightly job runs every evening of the window. The second night must not add a
    duplicate row for a switch already recorded."""
    sec = _sec("2026-12-14 18:00")
    rw.append_row("ES", _best(sec), table_dir=table, dry=False)
    row, err = rw.append_row("ES", _best(sec), table_dir=table, dry=False)
    assert row is None and "already in the table" in err


def test_a_dry_run_builds_the_row_but_writes_nothing(table):
    sec = _sec("2026-12-14 18:00")
    before = open(os.path.join(table, "rolls_ES.csv"), encoding="utf-8").read()
    row, err = rw.append_row("ES", _best(sec), table_dir=table, dry=True)
    assert row is not None and err is None
    assert open(os.path.join(table, "rolls_ES.csv"), encoding="utf-8").read() == before


def test_a_switch_off_the_minute_boundary_is_recorded_as_in_bar(table):
    """An in-bar switch is the one case the adjustment cannot be honest about, so the kind
    has to be right - it drives the synthetic/no-fill handling in rolls.py."""
    on = _sec("2026-12-14 18:00")
    off = on + 37
    r_on, _ = rw.append_row("ES", _best(on), table_dir=table, dry=True)
    r_off, _ = rw.append_row("ES", _best(off), table_dir=table, dry=True)
    assert r_on["kind"] == "mid_session"
    assert r_off["kind"] == "in_bar"


def test_the_appended_row_says_in_plain_english_where_the_number_came_from(table):
    """Whoever reads this row in a year needs to know it was measured from two feeds, not
    taken from a contract-level source."""
    row, _ = rw.append_row("ES", _best(_sec("2026-12-14 18:00")), table_dir=table, dry=True)
    for piece in ("roll_watch", "NinjaTrader capture", "quarterly cycle"):
        assert piece in row["note"], "missing %r in: %s" % (piece, row["note"])


def test_an_appended_row_is_trustworthy_but_not_exact(table):
    """The whole point of the `measured` status: strong enough for a guard to act on,
    honest that it is not contract-level data."""
    row, _ = rw.append_row("ES", _best(_sec("2026-12-14 18:00")), table_dir=table, dry=True)
    assert rolls.is_trustworthy(row)
    assert row["status"] != "exact"


# --------------------------------------------------------- the selftest stays honest

@pytest.mark.parametrize("root,expected", [("NQ", 296.5), ("ES", 67.75)])
def test_the_selftest_expectation_matches_what_the_table_records(root, expected):
    """`roll_watch --selftest` re-derives the September 2026 offset from the real masters.
    Its expected value must track the table: if someone corrects the table and forgets the
    selftest, the end-to-end proof quietly starts checking the wrong number."""
    row = next(r for r in rolls.real_switches(root) if r["switch_et"] == "2026-09-14 11:30")
    assert row["offset_pts"] == pytest.approx(expected)
    assert rw.SELFTEST[root]["expect"] == pytest.approx(expected)
    assert row["status"] == "measured", (
        "the September switch was measured against the capture on 2026-09-28")


def test_september_is_measured_and_june_cannot_be():
    """June 2026 is permanently an estimate: the NinjaTrader capture begins 2026-06-23, after
    that switch, so there is no second feed to measure it against. Anything that claims to
    have measured June is wrong."""
    for root in ("NQ", "ES"):
        est = rolls.estimated_switches(root)
        assert len(est) == 1 and est[0]["switch_et"].startswith("2026-06")
