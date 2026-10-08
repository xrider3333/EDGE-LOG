"""DD5 - the average of the five worst drawdowns (augur_engine/drawdowns.py, owner GO 2026-10-07).

The house yardstick (ROC %/yr at a $30k worst drawdown) divides by ONE episode, so DD5 is reported beside it
and a figure whose worst drawdown is more than 1.3x DD5 is called driven by one episode. These tests pin the
one definition: episodes never overlap (a bounce that does not regain the peak is the same episode), an episode
still open at the end counts with its depth so far, fewer than five episodes average what is there, a flat
curve has none, the curve starts from a flat account, and the worst episode equals the yardstick's own
drawdown (book_sizing.stretch_reading) to the cent.
"""
import math

import numpy as np
import pandas as pd
import pytest

from augur_engine.drawdowns import dd5, episodes


def _daily(path):
    """Daily P&L whose running sum walks through `path` (the equity after each day)."""
    out, prev = [], 0.0
    for v in path:
        out.append(float(v) - prev)
        prev = float(v)
    return out


# ------------------------------------------------------------------ overlap handling
def test_a_bounce_that_does_not_regain_the_peak_is_the_same_episode():
    # peak 100 -> 60 -> bounce to 90 (no new high) -> 40 -> back to 100: ONE episode, depth 60
    eps = episodes(_daily([100, 60, 90, 40, 100]))
    assert len(eps) == 1
    assert eps[0]["depth"] == pytest.approx(60.0)
    assert eps[0]["peak_i"] == 0 and eps[0]["trough_i"] == 3 and eps[0]["open"] is False


def test_regaining_the_peak_exactly_closes_an_episode_and_starts_the_next():
    # 100 -> 80 -> 100 (equal = regained) -> 70 -> 120: two episodes, 20 and 30
    eps = episodes(_daily([100, 80, 100, 70, 120]))
    assert [round(e["depth"], 6) for e in eps] == [20.0, 30.0]
    r = dd5(_daily([100, 80, 100, 70, 120]))
    assert r["n"] == 2 and r["dd5_usd"] == pytest.approx(25.0) and r["max_dd"] == pytest.approx(30.0)
    assert [e["depth"] for e in r["episodes"]] == [30.0, 20.0]          # deepest first


def test_only_the_five_deepest_count_and_they_never_share_days():
    path, lvl = [], 0.0
    for depth in (10, 50, 20, 40, 30, 5, 60):                          # seven separate dips, each recovered
        lvl += 100
        path += [lvl, lvl - depth]
    path.append(lvl + 100)
    r = dd5(_daily(path))
    assert r["episodes_total"] == 7 and r["n"] == 5
    assert [e["depth"] for e in r["episodes"]] == [60.0, 50.0, 40.0, 30.0, 20.0]
    assert r["dd5_usd"] == pytest.approx(40.0)
    spans = sorted((e["peak_i"], e["trough_i"]) for e in r["episodes"])
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))          # no two episodes overlap


# ------------------------------------------------------------------ open episode at the end
def test_an_episode_still_open_at_the_end_counts_with_its_depth_so_far():
    r = dd5(_daily([100, 70, 110, 105, 60]), dates=["2020-01-0%d" % d for d in range(1, 6)])
    assert r["n"] == 2
    open_ep = [e for e in r["episodes"] if e["open"]][0]
    assert open_ep["depth"] == pytest.approx(50.0) and open_ep["recovered"] is None
    assert open_ep["peak"] == "2020-01-03" and open_ep["trough"] == "2020-01-05"
    closed = [e for e in r["episodes"] if not e["open"]][0]
    assert closed["recovered"] == "2020-01-03"


# ------------------------------------------------------------------ fewer than five, flat, from a flat start
def test_fewer_than_five_episodes_average_what_is_there():
    r = dd5(_daily([100, 70, 110, 100, 130, 90, 140]))
    assert r["n"] == 3 and r["episodes_total"] == 3
    assert r["dd5_usd"] == pytest.approx((30 + 10 + 40) / 3.0, abs=0.01)


def test_a_flat_curve_has_no_episode():
    for flat in ([0.0] * 30, [], [5.0, 0.0, 3.0, 0.0]):              # never below its running peak
        r = dd5(flat)
        assert r["n"] == 0 and r["dd5_usd"] == 0.0 and r["max_dd"] == 0.0
        assert r["one_episode"] is False and r["episodes"] == []


def test_the_curve_starts_from_a_flat_account():
    # a first-day loss is a drawdown from the flat start, the same rule as stretch_reading's peak-from-zero
    r = dd5([-500.0, 200.0, 400.0])
    assert r["n"] == 1 and r["max_dd"] == pytest.approx(500.0)
    assert r["episodes"][0]["peak_i"] == -1 and r["episodes"][0]["peak"] is None


# ------------------------------------------------------------------ the one-episode flag
def test_one_crash_and_four_small_dips_is_flagged():
    path, lvl = [], 0.0
    for depth in (5000, 5000, 40000, 5000, 5000):
        lvl += 10000
        path += [lvl, lvl - depth]
    path.append(lvl + 10000)
    r = dd5(_daily(path))
    assert r["dd5_usd"] == pytest.approx(12000.0) and r["max_dd"] == pytest.approx(40000.0)
    assert r["one_episode"] is True                                     # 40k > 1.3 x 12k


def test_even_drawdowns_are_not_flagged_and_one_episode_alone_cannot_be():
    path, lvl = [], 0.0
    for depth in (9000, 10000, 11000, 10000, 9500):
        lvl += 20000
        path += [lvl, lvl - depth]
    assert dd5(_daily(path))["one_episode"] is False
    single = dd5(_daily([100, 20, 30]))
    assert single["n"] == 1 and single["one_episode"] is False         # the worst drawdown IS DD5


def test_the_flag_sits_exactly_on_the_1_3_line():
    # depths 13 and 7: DD5 10, worst 13 = 1.3 x DD5 -> not MORE than 1.3x
    r = dd5(_daily([100, 87, 100, 93, 100]))
    assert r["dd5_usd"] == pytest.approx(10.0) and r["one_episode"] is False
    assert dd5(_daily([100, 86.9, 100, 93, 100]))["one_episode"] is True


# ------------------------------------------------------------------ the yardstick's own drawdown, inputs
def test_the_worst_episode_is_the_yardsticks_own_drawdown():
    from augur_engine.book_sizing import stretch_reading
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2016-07-01", periods=900)
    s = pd.Series(rng.normal(150, 900, len(idx)), index=idx)
    r = dd5(s)
    ref = stretch_reading(s, idx[0], idx[-1])
    assert r["max_dd"] == pytest.approx(ref["max_drawdown"], abs=0.01)
    assert r["n"] == 5 and 0 < r["dd5_usd"] <= r["max_dd"]
    assert r["episodes"][0]["peak"] is None or r["episodes"][0]["peak"] >= "2016-07-01"
    assert all(len(e["trough"]) == 10 for e in r["episodes"])          # dates come off the index


def test_pairs_and_plain_numbers_read_the_same():
    vals = [100.0, -30.0, 50.0, -80.0, 10.0]
    days = ["2021-03-0%d" % d for d in range(1, 6)]
    a, b = dd5(vals, dates=days), dd5(list(zip(days, vals)))
    assert a == b
    assert dd5(vals)["dd5_usd"] == a["dd5_usd"] and dd5(vals)["episodes"][0]["peak"] is None


def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        dd5([1.0, float("nan"), 2.0])
    with pytest.raises(ValueError):
        dd5([1.0, 2.0], dates=["2020-01-01"])
    with pytest.raises(ValueError):
        dd5([1.0], n=0)
    assert math.isfinite(dd5([1.0, -2.0])["dd5_usd"])


# ═════════════════════════ DD% as a broker states it (owner ask 2026-10-08)
# dd_pct used to be dd_usd / 100k - a share of the STARTING account, not a drawdown. Run #424's
# worst drop of $116.9k read about 117% while its P&L never went below zero, and no open account
# can fall 117%. dd_pct_peak is the fall from the high-water mark.
from augur_engine.drawdowns import DEFAULT_START_USD, dd_pct_peak


def test_the_owners_example_reads_ten_percent():
    """Peak $1M, drop $100k = 10%. The figure the ask was written around."""
    assert dd_pct_peak([900_000.0, -100_000.0]) == 10.0


def test_a_curve_that_never_makes_a_new_high_is_measured_against_the_start():
    """The flat account is its own first peak, matching the peak-from-zero convention the dollar
    figures use. Losing $50k of a $100k account is 50%, not 50% of something larger."""
    assert dd_pct_peak([-50_000.0]) == 50.0
    assert dd_pct_peak([-10_000.0, -10_000.0, -5_000.0]) == 25.0


def test_the_worst_percent_is_not_always_the_worst_dollar_episode():
    """WHY THIS IS ITS OWN PASS over the curve. The denominator grows with the account, so an
    early $40k fall from a $200k high (20%) is worse in percent than a late $90k fall from a
    $900k high (10%) - while the LATE one is worse in dollars. Dividing the worst dollar
    drawdown by its own peak would report 10% and miss the 20%."""
    curve = [100_000.0, -40_000.0, 40_000.0, 700_000.0, -90_000.0]
    assert dd_pct_peak(curve) == 20.0
    # the worst DOLLAR drawdown on the same curve is the later one, and it is only 10%
    assert dd5(pd.Series(curve))["max_dd"] == 90_000.0


def test_it_is_not_the_old_share_of_the_starting_account():
    """THE MUTANT TARGET. #424's shape: a drop larger than the starting account, on a curve whose
    P&L never goes below zero. The old formula gives 117%; the drop is from a high of $1.1M, so a
    broker calls it about 10.6%."""
    pct = dd_pct_peak([1_000_000.0, -116_900.0])
    assert 10.0 < pct < 11.0, pct
    old = 116_900.0 / DEFAULT_START_USD * 100.0
    assert old > 100.0 and abs(pct - old) > 100.0, "still reading as a share of the start"


def test_a_fall_below_zero_passes_one_hundred_percent_and_is_not_capped():
    """An account that lost more than it ever held has fallen more than 100% from its high, and
    saying so is the honest reading. Capping would hide a blown account."""
    assert dd_pct_peak([-140_000.0]) == 140.0


def test_no_drawdown_and_no_rows_are_both_zero():
    assert dd_pct_peak([]) == 0.0
    assert dd_pct_peak([1_000.0, 2_000.0, 3_000.0]) == 0.0


def test_the_start_is_configurable_and_must_be_positive():
    """The $100k start is the house default, not a law - a reader comparing a different account
    size passes its own. Zero or negative would divide by a peak that is not an account."""
    assert dd_pct_peak([-25_000.0], start=50_000.0) == 50.0
    assert DEFAULT_START_USD == 100_000.0
    for bad in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            dd_pct_peak([-1.0], start=bad)


def test_it_accepts_the_same_input_shapes_dd5_does():
    """One definition, one set of callers: a Series, a bare sequence, or (date, $) pairs."""
    want = 10.0
    rows = [900_000.0, -100_000.0]
    assert dd_pct_peak(pd.Series(rows, index=pd.to_datetime(["2020-01-02", "2020-01-03"]))) == want
    assert dd_pct_peak(rows) == want
    assert dd_pct_peak([("2020-01-02", rows[0]), ("2020-01-03", rows[1])]) == want


def test_a_non_finite_row_is_refused_rather_than_silently_skipped():
    with pytest.raises(ValueError):
        dd_pct_peak([1.0, float("nan"), -2.0])
    with pytest.raises(ValueError):
        dd_pct_peak([1.0, float("inf")])
