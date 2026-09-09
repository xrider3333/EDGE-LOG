"""Four fast synthetic tests for tools/event_size_scan.py — no market data, no network.

They guard the four things that would silently invalidate the whole scan:
  1. the calendar builders land on dates we can check by hand;
  2. a SIZE multiplier never changes the trade COUNT (this is a size rule, not a filter);
  3. the permutation harness is unbiased under the null (a real p-value, not a rubber stamp);
  4. the pre-lockbox path never touches the sealed slice.
"""
import datetime as dt
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "tools"))
import event_size_scan as ES                                            # noqa: E402


def _weekday_calendar(y0=2020, y1=2023):
    """Every weekday in [y0, y1] — a stand-in trading calendar."""
    d, end, out = dt.date(y0, 1, 1), dt.date(y1, 12, 31), []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ── 1. calendar builders hit known dates ────────────────────────────────────────────────

def test_calendar_builders_hit_known_dates():
    # quad witching: the 3rd Friday of Mar/Jun/Sep/Dec, checked against a hand calendar
    assert ES.third_friday(2024, 3) == dt.date(2024, 3, 15)
    assert ES.third_friday(2024, 6) == dt.date(2024, 6, 21)
    assert ES.third_friday(2024, 9) == dt.date(2024, 9, 20)
    assert ES.third_friday(2024, 12) == dt.date(2024, 12, 20)
    assert ES.third_friday(2021, 1) == dt.date(2021, 1, 15)     # month starting on a Friday
    assert ES.third_friday(2021, 5) == dt.date(2021, 5, 21)     # month starting on a Saturday
    qw = ES.build_quad_witching(2024, 2024)
    assert qw == [dt.date(2024, 3, 15), dt.date(2024, 6, 21),
                  dt.date(2024, 9, 20), dt.date(2024, 12, 20)]
    assert all(d.weekday() == 4 for d in ES.build_quad_witching(2010, 2025))

    # FOMC minutes: exactly 3 weeks after the decision
    dec = [dt.date(2024, 1, 31), dt.date(2024, 3, 20)]
    assert ES.build_fomc_minutes(dec) == [dt.date(2024, 2, 21), dt.date(2024, 4, 10)]

    # Fed blackout: the 10 calendar days before a decision, decision day itself excluded
    td = _weekday_calendar(2024, 2024)
    bl = ES.build_fed_blackout([dt.date(2024, 3, 20)], td)
    assert dt.date(2024, 3, 20) not in bl                        # never the decision day
    assert dt.date(2024, 3, 19) in bl and dt.date(2024, 3, 11) in bl
    assert dt.date(2024, 3, 8) not in bl                         # 12 days out, outside the 10
    assert all(d.weekday() < 5 for d in bl)                      # trading days only

    # month / quarter edges from the tape's own session dates
    m_start, m_end = ES.build_period_edges(td, "M", 2)
    # this synthetic calendar has no holidays, so Jan 2024 opens Mon 1st / Tue 2nd
    assert dt.date(2024, 1, 1) in m_start and dt.date(2024, 1, 2) in m_start
    assert dt.date(2024, 1, 3) not in m_start                    # only the FIRST TWO
    assert dt.date(2024, 1, 30) in m_end and dt.date(2024, 1, 31) in m_end
    assert dt.date(2024, 1, 29) not in m_end                     # only the LAST TWO
    assert len(m_start) == len(m_end) == 24                      # 12 months x 2 days
    # drop a day from the tape and the edge moves with it — these come from the TAPE,
    # not from the wall calendar
    td_gap = [d for d in td if d != dt.date(2024, 1, 1)]
    assert dt.date(2024, 1, 3) in ES.build_period_edges(td_gap, "M", 2)[0]
    q_start, q_end = ES.build_period_edges(td, "Q", 2)
    assert dt.date(2024, 4, 1) in q_start and dt.date(2024, 4, 2) in q_start
    assert dt.date(2024, 3, 28) in q_end and dt.date(2024, 3, 29) in q_end
    assert len(q_start) == 8 and len(q_end) == 8                 # 4 quarters x 2 days

    # the hard-coded published schedules contain the dates we transcribed them for
    assert "2024-01-11" in ES.CPI_RELEASES and "2013-10-30" in ES.CPI_RELEASES
    assert "2024-01-05" in ES.NFP_RELEASES and "2015-05-08" in ES.NFP_RELEASES
    assert len(ES.CPI_RELEASES) == len(set(ES.CPI_RELEASES))
    assert len(ES.NFP_RELEASES) == len(set(ES.NFP_RELEASES))

    # a trading-day shift moves by trading days, not calendar days
    fri, mon = dt.date(2024, 3, 15), dt.date(2024, 3, 18)
    assert ES.shift_to_trading_days([fri], td, 1) == [mon]
    assert ES.shift_to_trading_days([fri], td, -1) == [dt.date(2024, 3, 14)]
    assert ES.shift_to_trading_days([fri], td, 0) == [fri]


# ── 2. a SIZE multiplier never changes the trade COUNT ───────────────────────────────────

@pytest.mark.parametrize("m", ES.MULTIPLIERS)
def test_size_multiplier_never_changes_trade_count(m):
    rng = np.random.default_rng(7)
    n = 500
    pnl = rng.normal(40, 500, n)
    dates = np.array([dt.date(2022, 1, 3) + dt.timedelta(days=int(i) % 700) for i in range(n)])
    hours = rng.integers(9, 17, n)
    rec = dict(key="T", pnl=pnl, date=dates, hour=hours)
    dayset = set(dates[::7].tolist())
    for w in ES.CLOCK_WINDOWS:
        mask = ES.cell_mask(rec, dayset, w)
        sized = ES.apply_size(pnl, mask, m)
        assert len(sized) == len(pnl) == n                       # no trade is ever dropped
        assert ES.metrics(sized, 1.0)["n"] == ES.metrics(pnl, 1.0)["n"] == n
        # only the affected trades move, and only by the multiplier
        assert np.allclose(sized[~mask], pnl[~mask])
        assert np.allclose(sized[mask], pnl[mask] * m)
        if m == 0.0:
            # a zero SIZE still leaves the trade in the ledger, it just carries no contracts
            assert np.all(sized[mask] == 0.0)
            assert len(sized) == n


# ── 3. the permutation harness is unbiased under the null ────────────────────────────────

def test_permutation_harness_is_unbiased_under_the_null():
    """PnL independent of the calendar => the real calendar's p-value must be ~Uniform(0,1).

    Cheap, exact check: over many independent null trials the mean p should sit near 0.5 and
    the fraction of trials rejecting at 0.05 should sit near 0.05. A harness that always
    'finds' an effect (or never does) fails this."""
    rng = np.random.default_rng(11)
    n_days, n_trials, n_perm = 240, 400, 199
    day_year = np.zeros(n_days, int)                            # one year, one stratum
    ps = []
    for _ in range(n_trials):
        daysum = rng.normal(0, 1000, n_days)                    # PnL, independent of the calendar
        idx = rng.choice(n_days, size=20, replace=False)        # an arbitrary "calendar"
        s_real, draws = ES.permute_sums(daysum, day_year, idx, n_perm, rng)
        assert np.isclose(s_real, daysum[idx].sum())            # the real statistic is the real one
        assert len(draws) == n_perm
        p, rank, ntot, _ = ES.perm_pvalue(s_real, draws, m=0.5)
        assert 0.0 < p <= 1.0 and 1 <= rank <= ntot == n_perm + 1
        ps.append(p)
    ps = np.array(ps)
    assert 0.42 < ps.mean() < 0.58, f"p-values not centred: mean {ps.mean():.3f}"
    assert 0.01 < (ps <= 0.05).mean() < 0.12, \
        f"rejection rate at alpha=0.05 is {(ps <= 0.05).mean():.3f}, expected ~0.05"

    # and the per-year stratification really is per-year: draws respect the year counts
    day_year2 = np.repeat([2020, 2021, 2022], 80)
    daysum2 = np.zeros(240)
    daysum2[day_year2 == 2021] = 1.0                            # only 2021 days carry value
    idx2 = np.flatnonzero(day_year2 == 2021)[:5]                # 5 days, all in 2021
    s_real2, draws2 = ES.permute_sums(daysum2, day_year2, idx2, 200, rng)
    assert s_real2 == 5.0
    assert np.all(draws2 == 5.0), "a same-days-per-year draw must stay inside 2021"


# ── 4. the lockbox slice is untouched until the final step ───────────────────────────────

def test_lockbox_slice_is_untouched_until_the_final_step():
    rng = np.random.default_rng(3)
    days = [dt.date(2023, 1, 2) + dt.timedelta(days=i) for i in range(0, 900, 3)]
    n = len(days)
    rec = dict(key="T", label="synthetic", n=n, pnl=rng.normal(0, 300, n),
               date=np.array(days), hour=rng.integers(9, 17, n),
               ts=np.arange(n), trading_days=days)
    pre = ES.slice_pre_lockbox(rec)
    lb = ES.slice_lockbox(rec)

    # the two slices partition the record, and neither leaks into the other
    assert pre["n"] + lb["n"] == n and pre["n"] > 0 and lb["n"] > 0
    assert pre["date"].max() < ES.LOCKBOX_FROM
    assert lb["date"].min() >= ES.LOCKBOX_FROM
    assert np.isclose(pre["pnl"].sum() + lb["pnl"].sum(), rec["pnl"].sum())
    assert pre["stage"] == "pre-lockbox" and lb["stage"] == "lockbox"

    # the scan run on the pre-lockbox slice produces numbers that depend on NO lockbox trade:
    # corrupting every lockbox PnL must leave every pre-lockbox cell bit-identical.
    td = [d for d in days if d < ES.LOCKBOX_FROM]
    cals = {"synthetic": td[::11]}
    args = (cals, td, 99, )
    rows_a, base_a = ES.scan_leg(pre, cals, td, 99, np.random.default_rng(5), 1.0)

    rec2 = dict(rec, pnl=rec["pnl"].copy())
    rec2["pnl"][rec2["date"] >= ES.LOCKBOX_FROM] = 1e9          # poison the sealed year
    pre2 = ES.slice_pre_lockbox(rec2)
    rows_b, base_b = ES.scan_leg(pre2, cals, td, 99, np.random.default_rng(5), 1.0)

    assert base_a == base_b
    assert len(rows_a) == len(rows_b) == len(cals) * len(ES.OFFSETS) \
        * len(ES.CLOCK_WINDOWS) * len(ES.MULTIPLIERS)
    for a, b in zip(rows_a, rows_b):
        assert a["net"] == b["net"] and a["mar"] == b["mar"] and a["d_net"] == b["d_net"]
        assert a["survives"] == b["survives"] and a["ydeltas"] == b["ydeltas"]
    assert args                                                  # (kept explicit for clarity)
