"""tools/run_record.py - the JSONL line a lane or the Qwen Lab appends when a run finishes (W47).

WHY THESE TESTS. The record is what puts a lane's or the lab's run on the COMPARE scatter, and
nothing downstream can tell a good figure from a wrong one: a Sortino measured per trade, a ROC
measured on a different curve than the dollars beside it, or a record filed against the runner's
PROVISIONAL run id all plot without complaint. So the refusals are the feature, and each test below
names the mistake it keeps out.

The four numbers are never typed into this file. The expectation for the happy path is computed by
calling augur_engine.drawdowns.four_numbers - the one definition (MANAGER #170) - on the same series
the tool is given, so a test cannot quietly bless a figure the house convention would not.

Offline and synthetic: the records directory is always tmp_path (EDGELOG_RUN_RECORDS), every sha is
handed in so nothing runs git, and no credential, master or Firestore client is touched. A test that
wrote to the real C:/EdgeLog/run_records would be failed by tests/conftest.py's live-system guard.
"""
import json
import math
import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.drawdowns import four_numbers  # noqa: E402
import tools.run_record as RR  # noqa: E402

LANE = "STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y"
TS = "2026-10-18 14:30"                  # fixed: the month file comes from ts, so never flake at midnight
SHA = "9f1c2ab"


# ── the series the lane would hand in ────────────────────────────────────────────────────────
def daily_series(n=300, seed=4701):
    """A valued-daily $ curve on business days: every day present, zero days included, with several
    drawdown episodes so DD5 averages five of them and the one-episode flag can be False."""
    import numpy as np
    days = pd.bdate_range("2024-01-01", periods=n)
    r = np.random.default_rng(seed).normal(45.0, 420.0, n)
    r[::7] = 0.0                                     # the zero days a daily curve has and a trade list does not
    for cut in (40, 95, 150, 205, 260):              # five dips, so n=5 episodes behind DD5
        r[cut:cut + 6] -= 900.0
    return pd.Series(r, index=days)


@pytest.fixture
def daily():
    return daily_series()


@pytest.fixture
def recdir(tmp_path, monkeypatch):
    """The records directory for every test - the env var the tool reads at call time, so the real
    C:/EdgeLog/run_records is never a candidate."""
    d = tmp_path / "run_records"
    monkeypatch.setenv("EDGELOG_RUN_RECORDS", str(d))
    monkeypatch.setenv("EDGELOG_HOST_ID", "test-box")
    return d


def base(**over):
    """The keyword arguments every call carries; `over` replaces or adds."""
    kw = dict(strategy="disc_ctxshort_r1", family="DISC", instrument="NQ", timeframe="1m",
              trades=210, gross_pt=1.433, cost_pt=0.533, ledger_row="2.195", sha=SHA, ts=TS,
              note="ctxshort r1 primary rule")
    kw.update(over)
    return kw


def write(where="lane", stage="WF", strict=True, **over):
    return RR.write_record(LANE, where, stage, strict=strict, **base(**over))


def _jsonl(recdir):
    """The record files only: the append lock sits beside them as <file>.jsonl.lock, which a
    *.jsonl glob (the sync tool's) never picks up."""
    names = sorted(os.listdir(recdir)) if os.path.isdir(recdir) else []
    assert not [n for n in names if n.endswith(".jsonl") and ".lock" in n]
    return [n for n in names if n.endswith(".jsonl")]


def lines(recdir, lane=LANE, ts=TS):
    p = RR.record_path(lane, ts, str(recdir))
    return [json.loads(x) for x in open(p, encoding="utf-8").read().splitlines()]


# the figures a tail hands in when it already has them: the lab's own four_numbers keys, and
# 30 x (net / years) / worst drawdown = 30 x (36000 / 9) / 12000 = 10.0, as every producer computes it
#
# EVERY FIGURE HERE IS POSSIBLE TOGETHER, which a fixture has to be or it blesses the very mix-up the
# tool exists to refuse. On a $100,000 account a worst drawdown of $12,000 bounds the DD % at
# 100 x 12000 / 100000 = 12.00% (dd_pct_peak's high-water mark starts AT the account and only rises),
# and bounds DD5 from below at 12000 / 5 = $2,400 (DD5 averages at most 5 depths, one of them the
# worst). Hence 11.37% - and not the 13.09% this fixture carried until W47's review, which no $100k
# account with a $12k worst drawdown can show.
LAB = {"roc_30k": 10.0, "dd5_usd": 9000.0, "dd_pct_peak": 11.37, "sortino": 1.42,
       "one_episode": False, "net_usd": 36000.0, "max_dd_usd": 12000.0, "years": 9.0,
       "trades": 133, "gross_pts_per_trade": 1.2, "cost_pts": 0.533}

# The honest over-100% reading the ceiling must keep letting through, with the dollars that make it
# possible: a $100,000 account taken to -$200,000 fell $200,000 from a $100,000 high, so its bound is
# 100 x 200000 / 100000 = 200%. 30 x (-240000 / 8) / 200000 = -4.5; DD5 sits between 200000 / 5 and
# 200000; the worst episode is more than 1.3 x DD5, so the one-episode flag says so.
BLOWUP = {"roc_30k": -4.5, "dd5_usd": 140000.0, "dd_pct_peak": 117.4, "sortino": -0.81,
          "one_episode": True, "net_usd": -240000.0, "max_dd_usd": 200000.0, "years": 8.0}


# ══════════════════════════════════════════════════════════ the happy path
def test_a_daily_series_in_gives_four_numbers_out_the_one_definition_computed(recdir, daily):
    """The four numbers on the record are four_numbers' own output, re-keyed - nothing re-derived."""
    f = four_numbers(daily)
    path = write(daily=daily)
    assert path == str(recdir / "strategy-beating-frontier-models-on-roc-y_202610.jsonl")
    (rec,) = lines(recdir)

    # == not approx: json round-trips a float through repr, so an exact match is available and a
    # near-match would hide a figure that had been rounded or recomputed on the way in.
    assert rec["roc30k"] == f["roc30"]
    assert rec["dd5"] == f["dd5_usd"]
    assert rec["ddpct"] == f["dd_pct_peak"]
    assert rec["sortino"] == f["sortino"]
    assert rec["one_episode"] == f["one_episode"]
    # and the additive fields come off the same call
    assert (rec["net_usd"], rec["max_dd_usd"], rec["years"]) == (f["net"], f["max_dd"], f["years"])
    assert (rec["win_start"], rec["win_end"]) == (f["from"], f["to"]) == ("2024-01-01", "2025-02-21")
    # the figures are real, not a flat curve that would pass every check vacuously
    assert rec["dd5"] > 0 and rec["ddpct"] > 0 and rec["roc30k"] is not None


def test_the_record_carries_the_frozen_schema_and_nothing_else(recdir, daily):
    write(daily=daily)
    (rec,) = lines(recdir)
    assert list(rec) == list(RR.FIELDS), "the schema is frozen: same fields, same order, every record"
    assert rec["schema_v"] == 1
    assert rec["lane"] == LANE, "the lane name is kept verbatim; only the FILENAME is slugged"
    assert (rec["where"], rec["stage"], rec["host"]) == ("lane", "WF", "test-box")
    assert (rec["trades"], rec["gross_pt"], rec["cost_pt"]) == (210, 1.433, 0.533)
    assert (rec["ledger_row"], rec["sha"], rec["start_usd"]) == ("2.195", SHA, 100000.0)
    assert rec["run_id"] is None, "a lane run has no engine run number, and null says so"
    assert rec["ts"] == TS


def test_the_note_says_whether_the_numbers_were_measured_here_or_handed_in(recdir, daily):
    """A reader has to know which before trusting the figures. The schema is frozen, so the
    provenance rides in the free-text field rather than in a field of its own."""
    write(daily=daily)
    assert lines(recdir)[0]["note"] == "ctxshort r1 primary rule | numbers: computed"
    write(numbers=LAB, trades=133)
    assert lines(recdir)[1]["note"].endswith("| numbers: given")


def test_a_lane_read_dict_and_the_labs_own_keys_are_both_understood(recdir):
    """The lab keys its ROC 'roc_30k' (tools/qwen_lab.py:3280) and a lane read dict keys it 'roc30'
    with 'dd5' for the dollars. A tail hands in the dict it already has; re-keying at the call site
    is where a typo writes a null."""
    write(numbers=LAB, trades=None, gross_pt=None, cost_pt=None, where="lab")
    lane_read = {"roc30": 10.0, "dd5": 9000.0, "dd_pct_peak": 11.37, "sortino": 1.42,
                 "one_episode": True, "net_usd": 36000.0, "max_dd": 12000.0, "years": 9.0}
    write(numbers=lane_read, trades=210)
    a, b = lines(recdir)
    assert (a["roc30k"], a["dd5"], a["ddpct"], a["sortino"]) == (10.0, 9000.0, 11.37, 1.42)
    assert (a["trades"], a["gross_pt"], a["cost_pt"]) == (133, 1.2, 0.533), "read out of the same dict"
    assert (b["roc30k"], b["max_dd_usd"]) == (10.0, 12000.0)


def test_a_handed_in_figure_is_stored_never_re_derived(recdir):
    """The rule from tools/runboard_watch.py stretch_numbers: a percentage is never derived from
    dollars - the worst % drop need not be the worst $ drop. 11.37 goes in, 11.37 comes out, even
    though 100 x 12000 / 100000 would have been 12.0 (that figure is the CEILING the percent has to
    sit under, never the percent itself)."""
    write(numbers=LAB, trades=133)
    assert lines(recdir)[0]["ddpct"] == 11.37


def test_the_daily_path_reads_drawdowns_as_a_file_and_not_the_whole_engine(recdir, daily, monkeypatch):
    """A HARNESS TAIL MUST NOT IMPORT THE TRADING ENGINE to append a line. `from
    augur_engine.drawdowns import ...` runs augur_engine/__init__.py: MEASURED on this box, 2.80 s and
    46 -> 1335 modules, pulling numpy, pandas, requests, scipy and sqlite3 - to reach a module whose
    own docstring says "Stdlib only". Speed is the smaller half: write_record is forgiving by default
    and swallows ANY exception, so one unrelated ImportError anywhere in the engine silently loses a
    lane's record. run_record.host_id() already refuses this coupling on the same ground.

    So the engine PACKAGE is broken here on purpose. The record still lands, because drawdowns.py is
    loaded as a file, and the figures are still four_numbers' own."""
    f = four_numbers(daily)                              # the one definition, imported before the break
    monkeypatch.setattr(RR, "_DRAWDOWNS", None, raising=False)       # never answer from an earlier test
    monkeypatch.setitem(sys.modules, "augur_engine", None)
    monkeypatch.setitem(sys.modules, "augur_engine.drawdowns", None)
    with pytest.raises(ImportError):                     # the break is real - not a vacuous pass
        __import__("augur_engine.drawdowns")

    assert write(daily=daily) is not None
    rec = lines(recdir)[0]
    assert (rec["dd5"], rec["ddpct"], rec["sortino"]) == (f["dd5_usd"], f["dd_pct_peak"], f["sortino"])

    mod = RR.drawdowns_module()
    assert mod.__file__.replace("\\", "/").endswith("augur_engine/drawdowns.py"), "the same file"
    assert mod.__name__ not in sys.modules, "a private handle, never a second augur_engine.drawdowns"


# ══════════════════════════════════════════════════════════ per-trade P&L is refused
def test_per_trade_pnl_is_refused_by_its_duplicate_dates(recdir):
    """THE MISTAKE four_numbers EXISTS TO STOP (its docstring; ENGU-Q's hold-cap rows, 10-15):
    valued per trade the Sortino is a different number. Two trades on one day give it away."""
    days = pd.bdate_range("2024-01-01", periods=60)
    per_trade = [(str(d.date()), 120.0) for d in days] + [(str(days[10].date()), -80.0)]
    per_trade.sort()
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=per_trade)
    assert "two rows share" in str(e.value) and "per-trade" in str(e.value)


def test_a_trade_list_with_most_of_the_days_missing_is_refused(recdir):
    """One trade a week, each on its own date: no duplicate gives it away, but a daily curve has
    EVERY day of the stretch present (zero days included) and this has a fifth of them."""
    days = pd.bdate_range("2024-01-01", periods=250)[::5]
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=[(str(d.date()), 300.0) for d in days])
    msg = str(e.value)
    assert "cover" in msg and "zero days included" in msg


def test_an_undated_series_is_refused_because_nothing_in_it_is_a_day(recdir):
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=[10.0, -5.0, 3.0, 0.0, 7.0])
    assert "no dates" in str(e.value)


def test_an_unsorted_series_is_refused(recdir, daily):
    """Rows are taken in the order given (four_numbers' docstring), so an unsorted curve measures a
    drawdown that never happened."""
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily.iloc[::-1])
    assert "not sorted" in str(e.value)


def test_a_one_row_stretch_is_refused(recdir):
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=[("2024-01-02", 100.0)])
    assert "at least 2 daily rows" in str(e.value)


def test_a_genuine_daily_series_of_sessions_passes_the_coverage_bar(recdir):
    """The bar has to let an honest curve through: sessions only, holidays missing, zero days in."""
    days = [d for d in pd.bdate_range("2024-01-01", periods=250)
            if str(d.date()) not in ("2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27")]
    rows = [(str(d.date()), 0.0 if i % 3 else 110.0 - (900.0 if i in (40, 41, 42) else 0.0))
            for i, d in enumerate(days)]
    assert write(daily=rows) is not None


# ══════════════════════════════════════════════════════════ a provisional run id is refused
def test_a_provisional_run_id_is_refused(recdir, daily):
    """api/runner.py falls back to int(time.time()) when the run-id counter cannot be read, and
    repair_provisional_run_ids later re-saves that run under its real number. A record filed against
    the provisional id would point at a run number that never exists, forever."""
    import time as _time
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily, run_id=int(_time.time()))
    msg = str(e.value)
    assert "PROVISIONAL" in msg and "plausible run number" in msg


def test_a_real_run_number_is_kept_and_a_silly_one_refused(recdir, daily):
    write(daily=daily, run_id=491)                       # today's newest
    assert lines(recdir)[0]["run_id"] == 491
    for bad in (0, -5, RR.MAX_RUN_ID + 1, 491.5, True, "four-ninety-one"):
        with pytest.raises(RR.RunRecordError):
            write(daily=daily, run_id=bad)
    write(daily=daily, run_id="492")                     # a shell hands its numbers over as text
    assert lines(recdir)[1]["run_id"] == 492


# ══════════════════════════════════════════════════════════ the vocabularies
def test_the_where_vocabulary_is_closed(recdir, daily):
    for w in RR.WHERE:
        assert write(daily=daily, where=w) is not None
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily, where="laptop")
    assert "where must be one of" in str(e.value)


def test_the_stage_vocabulary_is_closed(recdir, daily):
    # SEVEN STRETCHES, including the two the lanes were already writing before this tool existed: full (the
    #   whole run as one) and preLB (everything before the lockbox). Each has its own mark on the page.
    assert RR.STAGES == ("IS", "WF", "LB", "preWF", "forward", "full", "preLB")
    for s in RR.STAGES:
        assert write(daily=daily, stage=s) is not None
    for bad in ("wf", "walkforward", "lockbox", "PRE-WF", ""):
        with pytest.raises(RR.RunRecordError) as e:
            write(daily=daily, stage=bad)
        assert "stage" in str(e.value)


def test_the_four_strings_a_record_is_filed_under_are_required(recdir, daily):
    for field in ("strategy", "family", "instrument", "timeframe"):
        with pytest.raises(RR.RunRecordError) as e:
            write(daily=daily, **{field: " "})
        assert field in str(e.value)
    with pytest.raises(RR.RunRecordError):
        RR.write_record("", "lane", "WF", strict=True, **base(daily=daily))


# ══════════════════════════════════════════════════════════ one_episode stays a boolean
def test_one_episode_is_a_boolean_and_a_dollar_figure_is_refused(recdir, daily):
    """A dollar figure here reads as truthy and would flag every record as one-episode - the plot
    would be wrong and nothing would say so."""
    write(daily=daily)
    v = lines(recdir)[0]["one_episode"]
    assert isinstance(v, bool), "a bool, never a number and never a string"
    for bad in (33612.0, 1, 0, "yes", None):
        with pytest.raises(RR.RunRecordError) as e:
            write(numbers=dict(LAB, one_episode=bad), trades=133)
        assert "one_episode" in str(e.value)


def test_a_true_flag_survives_as_true(recdir):
    write(numbers=dict(LAB, one_episode=True), trades=133)
    assert lines(recdir)[0]["one_episode"] is True


def test_the_labs_not_testable_sentinel_is_written_as_null_not_false(recdir):
    """MANAGER #160a: with one episode (or a curve that never makes a new high) one drawdown cannot
    be compared with others. False would claim the opposite was tested, so it is written as null."""
    write(numbers=dict(LAB, one_episode=RR.LAB_NOT_TESTABLE), trades=133, where="lab")
    assert lines(recdir)[0]["one_episode"] is None


# ══════════════════════════════════════════════════════════ units
def test_dd5_deeper_than_the_worst_drawdown_is_refused(recdir):
    """An average of the 5 worst drawdowns cannot beat the worst one, so these came off two curves
    (the same check tools/runboard_watch.py stretch_numbers makes)."""
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=dict(LAB, dd5_usd=13000.0), trades=133)
    assert "cannot beat the worst one" in str(e.value)


def test_a_roc_that_does_not_match_its_own_dollars_is_refused(recdir):
    """30 x (net / years) / worst drawdown is the identity in four_numbers, book_sizing
    stretch_reading and power_line.roc30 alike - a ROC that misses it was measured elsewhere."""
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=dict(LAB, roc_30k=94.0), trades=133)
    assert "came off" in str(e.value) and "different curves" in str(e.value)


def test_a_zero_dd_percent_beside_a_real_drawdown_is_refused(recdir):
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=dict(LAB, dd_pct_peak=0.0), trades=133)
    assert "percent drawdown too" in str(e.value)


def test_the_measured_path_never_refuses_its_own_four_numbers_output(recdir):
    """THE PAIR CHECK ABOVE MUST NOT REFUSE THE ONE DEFINITION. dd_pct_peak rounds to 4 dp and DD5
    rounds to the CENT, so a one-cent drawdown on a $100,000 account measures ddpct 0.0 beside dd5
    $0.01 - four_numbers' own output, and the old clause called that pair impossible and lost the
    record. Only a zero under dd_pct_peak's rounding floor is read as rounding; the handed-in 0.0
    beside a $9,000 drawdown above is still refused."""
    days = pd.bdate_range("2024-01-02", periods=260)
    vals = [0.0] * 260
    vals[100] = -0.01                                    # the whole drawdown: one cent
    vals[200] = 100.0                                    # so the stretch nets something
    f = four_numbers(list(vals), dates=[str(d.date()) for d in days])
    assert (f["dd5_usd"], f["max_dd"], f["dd_pct_peak"]) == (0.01, 0.01, 0.0), \
        "the engine's own figures: a cent of drawdown rounds to 0.0% at 4 dp"
    assert f["sortino"] is not None

    write(daily=list(zip([str(d.date()) for d in days], vals)))
    rec = lines(recdir)[0]
    assert (rec["dd5"], rec["ddpct"]) == (0.01, 0.0), "stored as four_numbers measured them"


def test_a_dd_percent_over_100_is_allowed_because_an_account_really_can_fall_that_far(recdir):
    """augur_engine.drawdowns.dd_pct_peak is deliberately not capped: equity below zero fell more
    than 100% from the high that preceded it, and that is the honest reading. It gets through on its
    OWN dollars - a $200,000 fall on a $100,000 account bounds the percent at 200, not at 100."""
    write(numbers=BLOWUP, trades=133)
    assert lines(recdir)[0]["ddpct"] == 117.4
    write(numbers=dict(BLOWUP, dd_pct_peak=200.0), trades=133)        # exactly at its own bound
    assert lines(recdir)[1]["ddpct"] == 200.0


def test_a_dollar_figure_in_the_percent_field_is_refused(recdir):
    """The honest over-100 reading above has to get through, but the two fields are a dollar depth
    and a percent of the high - swapped, 33612 would plot as a drawdown and nothing would say so."""
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=dict(LAB, dd_pct_peak=33612.0), trades=133)
    assert "dollar figure in the percent field" in str(e.value)


def test_the_dd_percent_ceiling_is_the_records_own_dollars_not_a_flat_1000(recdir):
    """THE INVARIANT: dd_pct_peak's high-water mark starts AT start_usd and only rises, so every fall
    is measured against a peak >= the account and ddpct <= 100 x max_dd_usd / start_usd (measured
    over 400 series from four_numbers: the worst excess over that bound was +0.00005, dd_pct_peak's
    own rounding to 4 dp). The old flat DDPCT_ABSURD=1000 bar let a 117.4% reading sit beside a
    $12,000 worst drawdown on a $100,000 account, which is 10x what that account can fall."""
    for impossible in (117.4, 13.09, 999.0):             # all under the old 1000 bar
        with pytest.raises(RR.RunRecordError) as e:
            write(numbers=dict(LAB, dd_pct_peak=impossible), trades=133, start_usd=100_000.0)
        msg = str(e.value)
        assert "impossible beside a worst drawdown" in msg and "12.0000%" in msg
        assert "dollar figure in the percent field" in msg

    # the bound is a ceiling, not a cap: everything up to it is written as given
    for honest in (2.5, 11.37, 12.0):
        write(numbers=dict(LAB, dd_pct_peak=honest), trades=133, start_usd=100_000.0)
    assert [r["ddpct"] for r in lines(recdir)] == [2.5, 11.37, 12.0]


def test_a_dd_percent_the_account_makes_impossible_asks_for_the_account(recdir):
    """start_usd silently defaulted to $100k on the numbers= path, and THAT is what made the bound
    unsafe: the ceiling would be computed from an account nobody named. A record the assumed account
    would refuse is sent back for the real one instead of refused on a guess - and the real one lets
    the same figures through when the run really was on a smaller account."""
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=dict(LAB, dd_pct_peak=13.09), trades=133)       # no start_usd=
    msg = str(e.value)
    assert "start_usd was NOT passed" in msg and "DEFAULT" in msg

    write(numbers=dict(LAB, dd_pct_peak=13.09), trades=133, start_usd=90_000.0)
    rec = lines(recdir)[0]
    assert (rec["ddpct"], rec["start_usd"]) == (13.09, 90_000.0), \
        "100 x 12000 / 90000 = 13.33%, so a $90k account really can show 13.09"


def test_the_flat_bar_is_the_backstop_only_when_there_are_no_dollars_to_bound_it(recdir):
    """A handed-in record need not carry max_dd_usd (calmtape's read dicts do not), and then there is
    nothing to take the ceiling from. tools/run_records_sync.py's settled 1000 bar stays as the
    backstop for exactly that line - it is what the READER half of W47 has to work with."""
    nums = {k: v for k, v in LAB.items() if k != "max_dd_usd"}
    write(numbers=dict(nums, dd_pct_peak=117.4), trades=133)
    assert lines(recdir)[0]["ddpct"] == 117.4
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=dict(nums, dd_pct_peak=33612.0), trades=133)
    assert "no max_dd_usd beside it" in str(e.value)


def test_a_percent_in_the_dd5_dollars_field_is_refused_by_the_max_dd_over_5_floor(recdir):
    """THE INVARIANT: DD5 averages AT MOST 5 episode depths and the worst one IS one of them, so
    dd5 >= max_dd / 5 always (measured over 400 series from four_numbers: the smallest dd5/max_dd was
    0.2004). dd5 is the DOLLARS field, so a DD % landing in it - 13.09, or 0.1309, against a worst
    drawdown of $12,000 whose floor is $2,400 - is the mistake this floor catches. It plotted as a
    drawdown of thirteen dollars and nothing said so."""
    for percent_in_dollars in (13.09, 0.1309, 2399.9):
        with pytest.raises(RR.RunRecordError) as e:
            write(numbers=dict(LAB, dd5_usd=percent_in_dollars), trades=133)
        msg = str(e.value)
        assert "shallower than $2400.00" in msg and "PERCENT in the DOLLARS field" in msg

    # the floor itself is honest: five episodes of equal depth average exactly max_dd / 5
    write(numbers=dict(LAB, dd5_usd=2400.0, one_episode=True), trades=133)
    assert lines(recdir)[0]["dd5"] == 2400.0


def test_a_null_sortino_beside_a_real_drawdown_is_refused_like_a_null_roc(recdir):
    """THE INVARIANT: a stretch that drew down HAS a losing day, so four_numbers' Sortino denominator
    sqrt(mean(min(x,0)^2)) is positive and sortino is never None when dd5 > 0 (measured over 400
    random daily series: 0 counterexamples). The roc30k half of this was already refused by name,
    which is how a record reached the scatter carrying THREE of the four numbers."""
    for null in (None, float("nan")):                    # None, and the nan the numpy producers use
        with pytest.raises(RR.RunRecordError) as e:
            write(numbers=dict(LAB, sortino=null), trades=133)
        msg = str(e.value)
        assert "sortino is null but the stretch drew down" in msg
        assert "four numbers travel together" in msg

    with pytest.raises(RR.RunRecordError) as e:          # the mirror, unchanged
        write(numbers=dict(LAB, roc_30k=None), trades=133)
    assert "roc30k is null but the stretch drew down" in str(e.value)


def test_a_nan_sortino_from_a_numpy_producer_is_read_as_no_value(recdir):
    """calmtape's figs() returns a nan Sortino when no day loses and power_line.roc30 a nan ROC when
    the curve never draws down; four_numbers says the same state with None. A bare NaN in the file
    would not even be JSON, so these two fields take it as 'no value'."""
    write(numbers=dict(LAB, sortino=float("nan"), roc_30k=float("nan"), dd5_usd=0.0,
                       max_dd_usd=0.0, dd_pct_peak=0.0), trades=133)
    rec = lines(recdir)[0]
    assert rec["sortino"] is None and rec["roc30k"] is None
    assert "NaN" not in open(RR.record_path(LANE, TS, str(recdir)), encoding="utf-8").read()


def test_a_nan_in_any_other_field_is_refused(recdir):
    for field in ("dd5_usd", "dd_pct_peak", "net_usd"):
        with pytest.raises(RR.RunRecordError) as e:
            write(numbers=dict(LAB, **{field: float("nan")}), trades=133)
        assert "NaN" in str(e.value)


def test_a_missing_number_is_refused_rather_than_filled_in_from_the_others(recdir):
    """calmtape's figs() has no DD % from peak, so that tail cannot use this path - it holds the
    daily array and should pass daily= instead. The refusal has to say which figure is missing."""
    figs_like = {"roc30": 10.0, "sortino": 1.42, "dd": 12000.0, "dd5": 9000.0, "one_episode": False}
    with pytest.raises(RR.RunRecordError) as e:
        write(numbers=figs_like, trades=210)
    assert "ddpct" in str(e.value) and "dd_pct_peak" in str(e.value)


def test_trades_is_a_whole_count_and_is_required(recdir, daily):
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily, trades=None)
    assert "trades is required" in str(e.value)
    for bad in (-1, 2.5, True, "lots"):
        with pytest.raises(RR.RunRecordError):
            write(daily=daily, trades=bad)


def test_a_negative_cost_and_a_missing_one_are_told_apart(recdir, daily):
    """null means the tail did not hold the cost; 0 is a claim that the run was costless."""
    write(daily=daily, cost_pt=None, gross_pt=None)
    rec = lines(recdir)[0]
    assert rec["cost_pt"] is None and rec["gross_pt"] is None
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily, cost_pt=-0.533)
    assert "POINTS" in str(e.value)


def test_a_ledger_row_handed_over_as_a_number_is_refused(recdir, daily):
    """Row 2.20 as the float 2.20 stringifies to '2.2' - a different row, and nothing downstream
    could tell it had been renamed."""
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily, ledger_row=2.20)
    assert "becomes '2.2'" in str(e.value)
    write(daily=daily, ledger_row="2.20")
    assert lines(recdir)[0]["ledger_row"] == "2.20"


def test_the_timestamp_must_have_the_runs_docs_own_shape(recdir, daily):
    for bad in ("2026-10-18", "18/10/2026 14:30", "2026-10-18T14:30", "2026-10-18 14:30:00"):
        with pytest.raises(RR.RunRecordError) as e:
            write(daily=daily, ts=bad)
        assert "ts must be local" in str(e.value)


def test_the_sha_must_look_like_a_commit_not_a_hash_of_the_line(recdir, daily):
    for bad in ("abc", "zzzzzzz", "not a sha at all"):
        with pytest.raises(RR.RunRecordError) as e:
            write(daily=daily, sha=bad)
        assert "git commit sha" in str(e.value)
    write(daily=daily, sha="9F1C2AB3D4E5F60718293A4B5C6D7E8F90123456")
    assert lines(recdir)[0]["sha"] == "9f1c2ab3d4e5f60718293a4b5c6d7e8f90123456"


def test_the_code_sha_is_the_checkouts_head_when_the_caller_passes_none(recdir, daily, monkeypatch):
    """Not a hash of the record: the field exists to say which engine produced the numbers."""
    monkeypatch.setattr(RR, "_SHA_CACHE", {})
    monkeypatch.setattr(RR.subprocess, "run", lambda *a, **k: _Proc("7e2f1c9\n"))
    write(daily=daily, sha=None)
    assert lines(recdir)[0]["sha"] == "7e2f1c9"

    monkeypatch.setattr(RR, "_SHA_CACHE", {})
    monkeypatch.setattr(RR.subprocess, "run", lambda *a, **k: _Proc("", code=128))
    with pytest.raises(RR.RunRecordError) as e:
        write(daily=daily, sha=None)
    assert "could not read the code sha" in str(e.value)


class _Proc:
    def __init__(self, out, code=0):
        self.stdout, self.returncode = out, code


# ══════════════════════════════════════════════════════════ the file, the month and the appends
def test_one_call_appends_exactly_one_line_to_the_months_file(recdir, daily):
    for i in range(3):
        write(daily=daily, note="run %d" % i)
    p = RR.record_path(LANE, TS, str(recdir))
    raw = open(p, encoding="utf-8").read()
    assert raw.count("\n") == 3 and raw.endswith("\n"), "one line per call, every line terminated"
    assert [json.loads(x)["note"].split(" |")[0] for x in raw.splitlines()] == ["run 0", "run 1", "run 2"]


def test_the_month_comes_from_the_records_own_ts_not_from_today(recdir, daily):
    """A record written just after midnight for a run that finished before it belongs in the run's
    month, so the file is chosen by the record's own timestamp."""
    write(daily=daily, ts="2026-09-30 23:58")
    write(daily=daily, ts="2026-10-01 00:02")
    assert sorted(_jsonl(recdir)) == ["strategy-beating-frontier-models-on-roc-y_202609.jsonl",
                                      "strategy-beating-frontier-models-on-roc-y_202610.jsonl"]


def test_the_lane_name_becomes_a_safe_filename_and_two_spellings_share_one_file(recdir, daily):
    assert RR.lane_slug("QWEN LAB / ideas (r3)") == "qwen-lab-ideas-r3"
    assert RR.lane_slug(LANE) == RR.lane_slug(LANE.lower()) == "strategy-beating-frontier-models-on-roc-y"
    assert len(RR.lane_slug("X" * 400)) <= 80, "a lane name has no length limit; a Windows path does"
    for bad in ("", "   ", "///"):
        with pytest.raises(RR.RunRecordError):
            RR.lane_slug(bad)
    RR.write_record("Qwen Lab", "lab", "WF", strict=True, **base(daily=daily))
    RR.write_record("QWEN  LAB", "lab", "WF", strict=True, **base(daily=daily))
    assert _jsonl(recdir) == ["qwen-lab_202610.jsonl"], "one file, however the lane was spelled"
    assert len(lines(recdir, "Qwen Lab")) == 2


def test_the_records_directory_is_made_and_is_never_the_real_one_by_accident(tmp_path, monkeypatch):
    monkeypatch.delenv("EDGELOG_RUN_RECORDS", raising=False)
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "home"))
    assert RR.records_root() == os.path.join(str(tmp_path / "home"), "run_records")
    monkeypatch.setenv("EDGELOG_RUN_RECORDS", str(tmp_path / "elsewhere"))
    assert RR.records_root() == str(tmp_path / "elsewhere")
    assert not os.path.isdir(tmp_path / "elsewhere")
    RR.write_record(LANE, "lane", "WF", strict=True, **base(daily=daily_series()))
    assert os.path.isdir(tmp_path / "elsewhere"), "the directory is created on the first append"


# The appender the concurrency test below runs as its own PROCESS. A file, not `python -c`, so the
# failure reads like a traceback in a lane tail; argv carries everything (the records dir included)
# so nothing depends on the parent's environment surviving into the child.
APPENDER = '''\
import sys
sys.path.insert(0, sys.argv[1])
import tools.run_record as RR
recdir, lane, ts, tag, rows = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6])
for i in range(rows):
    # strict: a refusal or a lost lock has to come back as a nonzero exit, not a swallowed None.
    # lock_timeout is generous because 4 processes really do queue behind each other here.
    RR.write_record(lane, "lane", "WF", strict=True, records_dir=recdir, lock_timeout=120.0,
                    strategy="disc_ctxshort_r1", family="DISC", instrument="NQ", timeframe="1m",
                    trades=133, cost_pt=0.533, sha="9f1c2ab", ts=ts, note="%s row %d" % (tag, i),
                    numbers={"roc_30k": 10.0, "dd5_usd": 9000.0, "dd_pct_peak": 11.37,
                             "sortino": 1.42, "one_episode": False, "net_usd": 36000.0,
                             "max_dd_usd": 12000.0, "years": 9.0})
'''


def test_four_lane_processes_appending_at_once_each_land_a_whole_line(recdir, tmp_path):
    """SEPARATE PROCESSES, because that is the thing being tested. Several tails of one lane (a
    process per trial, and the Qwen Lab beside them) share a month file, and only an OS lock can
    make their appends atomic to each other - threads of one process cannot show that, since the GIL
    serialises the write and a THREADED version of this test passed with the lock removed. With four
    real processes and the lock nopped out, 219 of 240 lines survived; here all 240 must.

    240 = 4 x 60: enough appends to lose lines without a lock, few enough to run in seconds."""
    script = tmp_path / "appender.py"
    script.write_text(APPENDER, encoding="utf-8")
    procs = [subprocess.Popen([sys.executable, str(script), ROOT, str(recdir), LANE, TS,
                               "proc %d" % k, "60"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for k in range(4)]
    for p in procs:
        out, err = p.communicate(timeout=600)
        assert p.returncode == 0, "an appender process failed: %s\n%s" % (out, err)

    raw = open(RR.record_path(LANE, TS, str(recdir)), encoding="utf-8").read()
    assert raw.endswith("\n") and raw.count("\n") == 240, "every append landed as its own line"
    recs = [json.loads(x) for x in raw.splitlines()]     # a torn line is not JSON
    assert len({r["note"] for r in recs}) == 240, "and none overwrote or interleaved into another"
    assert all(r["schema_v"] == 1 and r["lane"] == LANE for r in recs), "no line is torn"


def test_an_append_refuses_rather_than_interleaving_when_another_lane_holds_the_lock(recdir, daily):
    """Nothing is written when the lock cannot be taken - a half-line in the file would be worse."""
    os.makedirs(recdir, exist_ok=True)
    path = RR.record_path(LANE, TS, str(recdir))
    fd = os.open(path + ".lock", os.O_CREAT | os.O_RDWR)
    RR._lock_fd(fd)
    try:
        with pytest.raises(RR.RunRecordError) as e:
            write(daily=daily, lock_timeout=0.2)
        assert "append lock" in str(e.value) and "nothing written" in str(e.value)
        assert not os.path.exists(path), "the record file is only opened once the lock is held"
    finally:
        RR._unlock_fd(fd)
        os.close(fd)


# ══════════════════════════════════════════════════════════ the harness tail must not die
def test_the_forgiving_mode_swallows_a_refusal_and_says_why_on_stderr(recdir, daily, capsys):
    """THE CALLER IS A HARNESS TAIL - the line after a run's own results were saved. A records write
    that raised there would cost the run. strict=False is the default for exactly that reason."""
    assert RR.write_record(LANE, "lane", "WF", **base(daily=daily, run_id=1792000000)) is None
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("[run-record] refused:")
    assert "PROVISIONAL" in err
    assert not os.path.exists(RR.record_path(LANE, TS, str(recdir)))


def test_the_forgiving_mode_swallows_an_unexpected_failure_too(recdir, daily, monkeypatch, capsys):
    """Not just the refusals this module raises: a bug anywhere under write_record must not reach
    the caller's save path either."""
    def boom(*a, **k):
        raise RuntimeError("disk fell over")
    monkeypatch.setattr(RR, "append_record", boom)
    assert RR.write_record(LANE, "lane", "WF", **base(daily=daily)) is None
    assert "unexpected RuntimeError: disk fell over" in capsys.readouterr().err
    with pytest.raises(RuntimeError):
        RR.write_record(LANE, "lane", "WF", strict=True, **base(daily=daily))


def test_neither_path_or_both_paths_is_refused(recdir, daily):
    with pytest.raises(RR.RunRecordError) as e:
        write()
    assert "not both and not neither" in str(e.value)
    with pytest.raises(RR.RunRecordError):
        write(daily=daily, numbers=LAB)


# ══════════════════════════════════════════════════════════ the shell entry point
def test_the_cli_appends_from_a_daily_csv(recdir, tmp_path, daily):
    csv_path = tmp_path / "daily.csv"
    with open(csv_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("date,usd\n")
        for d, v in daily.items():
            f.write("%s,%r\n" % (str(d.date()), float(v)))   # repr: the CSV round-trips the float exactly
    code = RR.main(["--lane", LANE, "--where", "lane", "--stage", "WF", "--strategy", "s",
                    "--family", "DISC", "--instrument", "NQ", "--timeframe", "1m",
                    "--daily-csv", str(csv_path), "--trades", "210", "--cost-pt", "0.533",
                    "--sha", SHA, "--ts", TS, "--note", "from a shell"])
    assert code == 0
    (rec,) = lines(recdir)
    assert rec["roc30k"] == four_numbers(daily)["roc30"]
    assert rec["note"] == "from a shell | numbers: computed"


def test_the_cli_dry_run_writes_nothing(recdir, tmp_path, capsys, daily):
    csv_path = tmp_path / "daily.csv"
    with open(csv_path, "w", encoding="utf-8", newline="\n") as f:
        for d, v in daily.items():
            f.write("%s,%r\n" % (str(d.date()), float(v)))   # repr: the CSV round-trips the float exactly
    code = RR.main(["--lane", LANE, "--where", "lane", "--stage", "LB", "--strategy", "s",
                    "--family", "DISC", "--instrument", "NQ", "--timeframe", "1m",
                    "--daily-csv", str(csv_path), "--trades", "9", "--sha", SHA, "--dry"])
    out = capsys.readouterr().out
    assert code == 0 and "DRY - would append to" in out
    assert json.loads(out[:out.index("\n[run-record]")])["stage"] == "LB"
    assert not os.path.isdir(recdir) or _jsonl(recdir) == []


def test_the_cli_refuses_without_killing_a_shell_tail_unless_strict(recdir, capsys):
    """A lane tail calls this from a shell; a nonzero exit there can take the harness with it. So a
    refusal prints and exits 0, and --strict is how a human asks for the failure."""
    args = ["--lane", LANE, "--where", "lane", "--stage", "WF", "--strategy", "s", "--family", "F",
            "--instrument", "NQ", "--timeframe", "1m", "--trades", "10", "--sha", SHA, "--ts", TS,
            "--roc30k", "10", "--dd5", "9000", "--ddpct", "13.09", "--sortino", "1.4",
            "--one-episode", "false", "--run-id", "1792000000"]
    assert RR.main(args) == 0
    assert "PROVISIONAL" in capsys.readouterr().err
    assert RR.main(args + ["--strict"]) == 2
    assert not os.path.exists(RR.record_path(LANE, TS, str(recdir)))


def test_the_cli_will_not_take_handed_in_numbers_beside_a_daily_csv(recdir, tmp_path, capsys, daily):
    csv_path = tmp_path / "daily.csv"
    with open(csv_path, "w", encoding="utf-8", newline="\n") as f:
        for d, v in daily.items():
            f.write("%s,%r\n" % (str(d.date()), float(v)))   # repr: the CSV round-trips the float exactly
    code = RR.main(["--lane", LANE, "--where", "lane", "--stage", "WF", "--strategy", "s",
                    "--family", "F", "--instrument", "NQ", "--timeframe", "1m", "--trades", "10",
                    "--sha", SHA, "--daily-csv", str(csv_path), "--roc30k", "94.0", "--strict"])
    assert code == 2 and "do not hand them in as well" in capsys.readouterr().err


def test_the_cli_one_episode_flag_takes_the_labs_sentinel(recdir, capsys):
    assert RR._flag_one_episode("NOT TESTABLE") == RR.LAB_NOT_TESTABLE
    assert RR._flag_one_episode("true") is True and RR._flag_one_episode("FALSE") is False
    with pytest.raises(Exception):
        RR._flag_one_episode("maybe")


def test_a_csv_with_one_column_or_no_rows_is_refused(tmp_path):
    bad = tmp_path / "one.csv"
    bad.write_text("2024-01-02\n2024-01-03\n", encoding="utf-8")
    with pytest.raises(RR.RunRecordError) as e:
        RR.daily_from_csv(str(bad))
    assert "one column" in str(e.value)
    empty = tmp_path / "empty.csv"
    empty.write_text("date,usd\n", encoding="utf-8")
    with pytest.raises(RR.RunRecordError) as e:
        RR.daily_from_csv(str(empty))
    assert "no rows" in str(e.value)


def test_the_daily_csv_header_is_skipped_but_a_bad_row_is_not(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("date,usd\n2024-01-02,100\n2024-01-03,-50.5\n", encoding="utf-8")
    assert RR.daily_from_csv(str(p)) == [("2024-01-02", 100.0), ("2024-01-03", -50.5)]
    p.write_text("date,usd\n2024-01-02,100\n2024-01-03,oops\n", encoding="utf-8")
    with pytest.raises(RR.RunRecordError) as e:
        RR.daily_from_csv(str(p))
    assert "line 3" in str(e.value)


def test_the_module_never_writes_a_nan_or_an_infinity(recdir, daily):
    """json's default would write the bare tokens NaN / Infinity, which no JSON reader accepts: the
    line would be lost at sync time rather than refused here."""
    rec = RR.build_record(LANE, "lane", "WF", **base(daily=daily))
    rec["sortino"] = float("inf")
    with pytest.raises(RR.RunRecordError) as e:
        RR.append_record(rec, records_dir=str(recdir))
    assert "not JSON" in str(e.value)
    assert not math.isnan(RR.build_record(LANE, "lane", "WF", **base(daily=daily))["dd5"])
