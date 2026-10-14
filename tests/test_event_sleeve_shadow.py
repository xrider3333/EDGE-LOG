"""EVENT SLEEVE forward shadow scorer (tools/event_sleeve_shadow.py): the pure pieces - scale-factor arithmetic, the staleness
refusal, the seeded harm-bar simulation, and the small forward rules. Synthetic inputs only: no house data, no network."""
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import event_sleeve_shadow as S  # noqa: E402


# ------------------------------------------------------------------ section 3: scale factors
def test_scale_factor_is_risk_unit_over_sample_sd():
    pnls = [1000.0, -1000.0, 3000.0, -3000.0]
    sd = math.sqrt((2 * 1000.0 ** 2 + 2 * 3000.0 ** 2) / 3)        # mean 0, ddof 1
    assert S.trade_sd(pnls) == pytest.approx(sd)
    assert S.scale_factor(pnls) == pytest.approx(1000.0 / sd)
    # scaled trades have exactly one risk unit of per-trade SD
    assert np.std(np.array(pnls) * S.scale_factor(pnls), ddof=1) == pytest.approx(S.RISK_UNIT)


def test_scale_factor_refuses_degenerate_input():
    with pytest.raises(ValueError):
        S.scale_factor([500.0])
    with pytest.raises(ValueError):
        S.scale_factor([250.0, 250.0, 250.0])


def test_sd_window_keeps_trades_wholly_inside():
    e = pd.Series(pd.to_datetime(["2016-07-15", "2016-07-16", "2025-06-23", "2025-06-27"]))
    x = pd.Series(pd.to_datetime(["2016-07-15", "2016-07-16", "2025-06-30", "2025-07-01"]))
    assert list(S.in_window(e, x)) == [False, True, True, False]


# ------------------------------------------------------------------ staleness refusal
def test_business_days_behind():
    wed = "2026-10-14"
    assert S.bdays_behind("2026-10-14", wed) == 0
    assert S.bdays_behind("2026-10-13", wed) == 1
    assert S.bdays_behind("2026-10-09", wed) == 3            # Fri -> Wed: Fri, Mon, Tue
    assert S.bdays_behind("2026-10-08", wed) == 4
    assert S.bdays_behind("2026-10-20", wed) == 0            # data stamped after today is not "behind"


def test_staleness_refuses_a_part_with_one_stale_input():
    ok, why, lag = S.staleness({"fund closes": pd.Timestamp("2026-09-23"), "calendar": pd.Timestamp("2026-10-13")},
                               pd.Timestamp("2026-10-14"))
    assert not ok and lag == 15
    assert "fund closes ends 2026-09-23" in why and "calendar ends" not in why


def test_staleness_passes_at_exactly_three_business_days():
    ok, why, lag = S.staleness({"NQ 1m": pd.Timestamp("2026-10-09")}, pd.Timestamp("2026-10-14"))
    assert ok and lag == 3
    ok, _, _ = S.staleness({"NQ 1m": pd.Timestamp("2026-10-08")}, pd.Timestamp("2026-10-14"))
    assert not ok


def test_forward_refuses_without_frozen_constants(tmp_path):
    with pytest.raises(SystemExit, match="constants"):
        S.mode_forward("2026-10-14", out_dir=str(tmp_path))


# ------------------------------------------------------------------ section 5: harm bar
def test_harm_threshold_is_deterministic_with_its_seed():
    a, sa = S.harm_threshold()
    b, sb = S.harm_threshold()
    assert a == b and sa == sb
    c, _ = S.harm_threshold(seed=S.HARM["seed"] + 1)
    assert c != a
    # the prior-predictive mean is 50 x 0.64 / sqrt(55); the 5th percentile sits well below zero
    assert sa["mean"] == pytest.approx(50 * 0.64 / math.sqrt(55), abs=0.15)
    assert -9.0 < a < -6.0


def test_harm_noise_has_unit_variance():
    e = S.draw_unit_noise(np.random.default_rng(1), (400_000,), "t3")
    assert np.median(np.abs(e)) * math.sqrt(3.0) == pytest.approx(0.7649, rel=0.02)   # t3 median |x| = 0.7649


# ------------------------------------------------------------------ forward rules
def test_runs_matches_contiguous_position_runs():
    pos = np.array([0, -1, -1, 1, 1, 1, 0, 0, -1, 0], float)
    assert S.runs(pos) == [(1, 2, -1.0), (3, 5, 1.0), (8, 8, -1.0)]


def test_auction_trade_settles_only_inside_data_and_calendar():
    n, K = 100, 5
    assert S.auction_settled(88, n, cal_idx=95, K=K)            # 88 + 11 = 99 = last index
    assert not S.auction_settled(89, n, cal_idx=95, K=K)
    assert not S.auction_settled(88, n, cal_idx=88, K=K)        # must end before the calendar's fetch session


def test_complete_months_drops_the_open_month():
    idx = pd.bdate_range("2026-09-24", "2026-10-14")
    keep = S.complete_months(idx, "2026-10-14")
    assert keep[-1] == pd.Timestamp("2026-09-30") and (keep.month == 9).all()
    keep = S.complete_months(idx, "2026-09-29")                 # an input ending mid-month closes nothing in September
    assert len(keep) == 0


def test_release_days_take_0830_cpi_and_payrolls_only(tmp_path):
    p = tmp_path / "bls.txt"
    p.write_text("# header\nEMP|2026-10-02|08:30\nCPI|2026-10-14|08:30\nCPI|2026-11-10|10:00\nEMP|2026-11-10|08:30\n"
                 "PPI|2026-10-15|08:30\n", encoding="utf-8")
    days = S.release_days(S.parse_bls(str(p)))
    assert days == [pd.Timestamp("2026-10-02"), pd.Timestamp("2026-10-14")]   # 11-10 carries another release time


def _bars(day, first="08:29", n=91, drop=None, up=True):
    idx = pd.date_range(pd.Timestamp("%s %s" % (day, first), tz="US/Eastern"), periods=n, freq="1min")
    c = pd.Series(20000.0 + np.arange(n) * (1.0 if up else -1.0), index=idx)
    o = c - 0.25
    if drop is not None:
        keep = ~idx.isin([pd.Timestamp("%s %s" % (day, drop), tz="US/Eastern")])
        o, c = o[keep], c[keep]
    return o, c


def test_fade_day_trades_against_the_0830_move():
    o, c = _bars("2026-10-14", up=True)                          # m > 0 -> the fade is SHORT
    r, why = S.fade_day(o, c, pd.Timestamp("2026-10-14"), 20.0, 0.533)
    assert why is None and r["side"] == -1.0
    en, ex = float(o.iloc[6]), float(c.iloc[-1])                 # 08:35 open, 09:59 close
    assert r["pnl"] == pytest.approx(-(ex - en) * 20.0 - 0.533 * 20.0)
    o, c = _bars("2026-10-14", up=False)
    r, _ = S.fade_day(o, c, pd.Timestamp("2026-10-14"), 20.0, 0.533)
    assert r["side"] == 1.0


def test_fade_day_skips_a_day_with_any_bar_missing():
    o, c = _bars("2026-10-14", drop="09:12")
    r, why = S.fade_day(o, c, pd.Timestamp("2026-10-14"), 20.0, 0.533)
    assert r is None and "90 of 91" in why
    idx = pd.date_range(pd.Timestamp("2026-10-14 08:29", tz="US/Eastern"), periods=91, freq="1min")
    flat = pd.Series(20000.0, index=idx)
    r, why = S.fade_day(flat, flat, pd.Timestamp("2026-10-14"), 20.0, 0.533)
    assert r is None and why == "zero move"


def test_lf_sha_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_bytes(b"x = 1\r\ny = 2\r\n")
    b.write_bytes(b"x = 1\ny = 2\n")
    assert S.sha256_lf(str(a)) == S.sha256_lf(str(b))
