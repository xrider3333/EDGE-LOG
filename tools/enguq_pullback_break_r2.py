"""ENGU-Q pullback-break scan r2 - ES 5m ETH.

Prereg C:\\EdgeLog\\manager\\prereg\\PREREG_enguq_pullback_break_2026-11-04.md, section 9 (the r2
definition and my challenge to MANAGER's scan r1). The sha of that document is checked at start.

What this is for, in one paragraph. MANAGER's scan r1 evaluated 399 cells and found no gross edge,
but EVERY one of those cells goes flat at the session close (its own caveat: "no overnight-specific
exits tested").  That is arm C, and arm C stripped 76% of the ROC off this family's own crown
(26.09 -> 6.17) in the Webull round.  So r1 cannot separate "this entry has no edge" from "this exit
destroyed the edge this entry has".  X4 below is the cell r1 has no equivalent of: the crown's own
exit, multi-day hold.  Every cell is also reported risk-normalised, because r1 judged the context
filter in DOLLARS AT FIXED CONTRACT while this house sizes on risk, and in R terms r1's own table
has the context adding in three of four pairs.

Nothing here touches live, paper, the box or any account.  Pre-lockbox only; the lockbox is read
once at the end and can only kill.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys

import numpy as np
import pandas as pd

# python puts the SCRIPT's directory on sys.path, not the cwd, so tools/ lands on the path
# and the repo root does not - which is why 'import augur_engine' failed under detach.py.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PREREG = r"C:\EdgeLog\manager\prereg\PREREG_enguq_pullback_break_2026-11-04.md"
PREREG_SHA = "2786c829ff1a4f840217640b3aa5683634cb4b1bd00a97c2ddcf15c5efbc5ba6"

ES_CSV = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads\ADJ_ES_5m_ETH.csv"
OUT_DIR = r"C:\EdgeLog\_anatomy_cache\enguq_pullback_break_r2"

DOLLARS_PER_POINT = 50.0
TICK = 0.25
COST_LADDER = (0.08, 0.10, 0.25, 0.533, 0.75, 1.25)   # ES points a round trip
# 0.533 = the house ES figure and the HEADLINE.  0.08 and 0.10 are MY ESTIMATE of an
# ES commission-only round trip ($4-5 RT at $50 a point), added for owner standing order
# 11-06 (#142) which gives a commission-only figure for NQ (0.283) but not for ES.  They are
# LABELLED AS AN ESTIMATE, not the owner's number, and I have asked MANAGER for the real one.
# NOTE they are MARKET-fill rows: #142's limit rule ("count a fill only when price trades
# THROUGH the level by 1 tick") is NOT implemented and is a separate pre-declared arm.
HEADLINE_COST = 0.533
LOCKBOX_FROM = "2025-07-01"
PRE_LOCKBOX_TO = "2025-06-30"

# Pre-declared, section 9.5.  k is NOT chosen to make the owner's 14:00 bar fire.
K_TICKS = (1, 2, 4)              # k=8 STRUCK by addendum 2: 93% of bars pass, no information
D_ATR = (0.5, 1.0, 1.5)          # net decline across the run, in ATR20 - addendum 2
ATR_LEN = 20
N_DRIFT = (6, 8)                  # N>=10 struck by r1 (33 signals in 15 years); N=12 struck
SLOPE_WINDOWS = (10, 15, 20)
BODY_RATIOS = (0.0, 2.0)          # 0.0 = B0, the no-body-test CONTROL
TRADES_A_YEAR_FLOOR = 50.0

# The crown's own exit, ENGUQ_1M_ETH_R2_1_0.py DEFAULT_PARAMS defaults, pinned not tuned.
CROWN_STOP_MULT = 1.0
CROWN_ACT_R = 2.5
CROWN_TRAIL_FRAC = 2.5
CROWN_BREAKEVEN_R = 1.5
CROWN_SWING_LOOKBACK = 20

# #335's own 8 folds, as frozen in docs/PREREG_enguq_executor_r1_2026-10-18.md.
FOLDS = (
    ("2016-10-12", "2017-11-07"), ("2017-11-08", "2018-12-05"),
    ("2018-12-06", "2020-01-02"), ("2020-01-03", "2021-01-29"),
    ("2021-01-30", "2022-02-26"), ("2022-02-27", "2023-03-26"),
    ("2023-03-27", "2024-04-22"), ("2024-04-23", "2025-06-27"),
)


# ---------------------------------------------------------------- helpers

def lf_sha256(path):
    return hashlib.sha256(io.open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def usd(x):
    """format(x, ',.0f').  '%,.0f' RAISES - it is not valid %-formatting."""
    return format(float(x), ",.0f")


def power_n(sd, delta, per_group=True):
    """80% power, two-sided 5%.  delta == 0 returns None (infinite), never a huge number."""
    if not delta:
        return None
    k = 15.7 if per_group else 7.85
    return int(round(k * (float(sd) ** 2) / (float(delta) ** 2)))


# ---------------------------------------------------------------- entry definitions

def drift_run_tolerant(close, k_ticks):
    """Length of the run of 'not meaningfully higher' closes ENDING AT bar i-1.

    A bar counts in the run when close <= prior close + k_ticks * TICK.  This is the owner's eye
    as MANAGER's scan r1 reverse-engineered it from the 14:00 bar of 11-04: 13:55 closed +0.25 UP,
    so a STRICT lower-close count scores that run as zero and never fires.  r1's own variant also
    required bar i-1 to be a strictly lower close; this does not, which is the point.
    """
    c = np.asarray(close, float)
    tol = k_ticks * TICK
    step_ok = np.zeros(len(c), bool)
    step_ok[1:] = c[1:] <= c[:-1] + tol
    run = np.zeros(len(c), int)
    for i in range(1, len(c)):
        run[i] = run[i - 1] + 1 if step_ok[i] else 0
    out = np.zeros(len(c), int)
    out[1:] = run[:-1]          # the run ENDING at i-1, seen from bar i
    return out


def drift_slope(close, win):
    """OLS slope of the trailing `win` closes ending at bar i-1, in points a bar.

    A drift definition with NO COUNT in it, as the cross-check section 9.5 asks for: if D1 and D2
    disagree, the answer was about counting, not about drift.
    """
    c = np.asarray(close, float)
    n = len(c)
    x = np.arange(win, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())
    out = np.full(n, np.nan)
    if n <= win:
        return out
    # sum(x_j * y_j) over each window; sum(x)=0 so the y-mean term drops out entirely
    num = np.convolve(c, x[::-1], mode="valid")      # num[i] covers c[i:i+win]
    out[win:] = num[: n - win] / denom               # the window ENDING at i-1
    return out


def body_ratio(open_, high, low, close, n_prior):
    """breakout body / mean |body| of the n_prior bars before i.  NaN where undefined."""
    o = np.asarray(open_, float)
    c = np.asarray(close, float)
    body = np.abs(c - o)
    n = len(c)
    out = np.full(n, np.nan)
    if n <= n_prior:
        return out
    csum = np.concatenate([[0.0], np.cumsum(body)])
    mean_prior = (csum[n_prior:n] - csum[0:n - n_prior]) / n_prior   # bars before i, for i>=n_prior
    with np.errstate(divide="ignore", invalid="ignore"):
        out[n_prior:] = np.where(mean_prior > 0, (c[n_prior:] - o[n_prior:]) / mean_prior, np.nan)
    return out


def atr(high, low, close, length=ATR_LEN):
    """Wilder-style true range, simple mean, shifted so bar i sees only bars BEFORE it."""
    h = np.asarray(high, float); l = np.asarray(low, float); c = np.asarray(close, float)
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(length).mean().shift(1).to_numpy()


def net_decline(close, run):
    """How far price actually FELL across the run ending at i-1.

    close[i-1-run] - close[i-1].  Positive = it fell.  This is the half of "net drift with small
    up-ticks allowed" that addendum 2 records me having omitted: without it the per-bar tolerance
    admits chop (93% of bars at k=8) and the drift condition selects nothing.
    """
    c = np.asarray(close, float)
    n = len(c)
    out = np.full(n, np.nan)
    i = np.arange(n)
    start = i - 1 - run
    ok = (run > 0) & (start >= 0)
    out[ok] = c[start[ok]] - c[i[ok] - 1]
    return out


# ---------------------------------------------------------------- exits

def exit_fixed_r(high, low, entry_px, entry_bar, stop_px, r_mult, last_bar_of_day, day_of_bar,
                 flat_at_close, time_stop=0):
    """Target = entry + r_mult * (entry - stop).  STOP WINS TIES.

    If a single bar's range contains both the target and the stop we take the STOP.  A scan that
    lets the target win ties is how look-ahead enters this house quietly.
    """
    risk = entry_px - stop_px
    if risk <= 0:
        return None
    target = entry_px + r_mult * risk
    n = len(high)
    stop_i = last_bar_of_day[day_of_bar[entry_bar]] if flat_at_close else n - 1
    if time_stop:
        stop_i = min(stop_i, entry_bar + time_stop)
    stop_i = min(stop_i, n - 1)
    for i in range(entry_bar, stop_i + 1):
        if low[i] <= stop_px:                      # stop first, always
            return i, stop_px, "stop"
        if high[i] >= target:
            return i, target, "target"
    return stop_i, None, "timeout"                 # None price = mark at close


def exit_crown(high, low, close, entry_px, entry_bar, stop_px, n):
    """The crown's exit: stop_mult x entry-to-swing-low, trail trail_frac R below the running
    high once act_R is reached, stop to entry at breakeven_R, MULTI-DAY HOLD.

    This is the cell MANAGER's 399 have no equivalent of.  Stop wins ties here too.
    """
    risk = entry_px - stop_px
    if risk <= 0:
        return None
    stop = stop_px
    run_high = entry_px
    armed = False
    for i in range(entry_bar, n):
        if low[i] <= stop:
            return i, stop, "stop"
        run_high = max(run_high, high[i])
        gain_r = (run_high - entry_px) / risk
        if CROWN_BREAKEVEN_R > 0 and gain_r >= CROWN_BREAKEVEN_R:
            stop = max(stop, entry_px)
        if gain_r >= CROWN_ACT_R:
            armed = True
        if armed:
            stop = max(stop, run_high - CROWN_TRAIL_FRAC * risk)
    return n - 1, None, "open"


# ---------------------------------------------------------------- four numbers

def four(daily, dates, years=None):
    """Four numbers through the house helper, on a DAILY series with zero days included."""
    from augur_engine.drawdowns import four_numbers
    s = pd.Series(np.asarray(daily, float), index=pd.to_datetime(dates))
    kw = {"years": years} if years else {}
    return four_numbers(s, **kw)


def daily_series(exit_dates, pnl_usd, all_dates):
    """$ per calendar session, EVERY session present, zero days included."""
    s = pd.Series(0.0, index=pd.to_datetime(all_dates))
    for d, v in zip(exit_dates, pnl_usd):
        key = pd.Timestamp(d)
        if key in s.index:
            s.loc[key] += v
    return s


# ---------------------------------------------------------------- selftest

def selftest():
    ok = True

    def chk(name, cond):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + name)
        ok = ok and bool(cond)

    # 1. the tolerant drift counter: the owner's own bar.  13:55 closes +0.25 UP, so a STRICT
    #    count scores 0 and never fires; k=2 ticks (0.50) must carry the run through it.
    c = np.array([7736.75, 7734.0, 7731.5, 7729.0, 7728.0, 7727.50, 7727.75, 7732.75])
    strict = drift_run_tolerant(c, 0)
    tol2 = drift_run_tolerant(c, 2)
    chk("strict count is blocked by the +0.25 up-tick (run at the breakout bar == 0)", strict[-1] == 0)
    chk("k=2 ticks carries the run through the up-tick (run == 6)", tol2[-1] == 6)
    chk("the run is the one ENDING AT i-1, so the breakout bar is not in its own run",
        drift_run_tolerant(np.array([5.0, 4.0, 3.0, 9.0]), 0)[3] == 2)

    # 2. no look-ahead: a bar's run may not depend on any later bar.
    c2 = np.concatenate([c, [9999.0]])
    chk("appending a future bar does not change an earlier bar's run",
        drift_run_tolerant(c2, 2)[7] == tol2[7])

    # 3. slope: a clean downward ramp must give a negative slope, a flat line zero.
    ramp = np.arange(30, 0, -1).astype(float)
    sl = drift_slope(ramp, 10)
    chk("a falling ramp has a negative slope", sl[20] < 0)
    chk("a flat series has a zero slope", abs(drift_slope(np.full(30, 7.0), 10)[20]) < 1e-9)

    # 4. body ratio.
    o = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
    cl = np.array([11.0, 11.0, 11.0, 11.0, 13.0])     # prior bodies 1, breakout body 3
    br = body_ratio(o, cl + 1, o - 1, cl, 4)
    chk("body ratio = body / mean prior body (3.0)", abs(br[4] - 3.0) < 1e-9)

    # 5. STOP WINS TIES - a bar containing both the target and the stop resolves to the stop.
    hi = np.array([100.0, 110.0]); lo = np.array([100.0, 90.0])
    r = exit_fixed_r(hi, lo, 100.0, 1, 95.0, 1.0, [1], [0, 0], True)
    chk("a bar holding both target and stop resolves to the STOP", r is not None and r[2] == "stop")

    # 5b. THE BUG THAT MADE gross R == -1.0000 IN ALL 54 CELLS.  With the stop set to the
    #     signal bar's low, scanning from the signal bar itself stops instantly, because that
    #     bar's low IS the stop.  A trade filled at the NEXT bar's open must survive a next
    #     bar that never trades down to the breakout low.
    sig_lo = 90.0
    hi_b = np.array([100.0, 101.0, 105.0])     # bar 0 = signal (low 90), bars 1-2 go up
    lo_b = np.array([sig_lo, 99.0, 100.0])
    rb = exit_fixed_r(hi_b, lo_b, 99.5, 1, sig_lo, 1.0, [2], [0, 0, 0], True)
    chk("a next-open fill does NOT stop on the signal bar's own low",
        rb is not None and rb[2] != "stop")
    chk("the same trade scanned from the SIGNAL bar stops instantly (the old bug)",
        exit_fixed_r(hi_b, lo_b, 99.5, 0, sig_lo, 1.0, [2], [0, 0, 0], True)[2] == "stop")

    # 6. a non-positive risk is refused rather than dividing by zero.
    chk("entry at or below its own stop is refused",
        exit_fixed_r(hi, lo, 100.0, 1, 100.0, 1.0, [1], [0, 0], True) is None)

    # 7. the crown exit holds past the session close - that is the whole point of X4.
    n = 40
    hi2 = np.concatenate([[100.0], np.linspace(101, 140, n - 1)])
    lo2 = hi2 - 1.0
    cl2 = hi2 - 0.5
    rc = exit_crown(hi2, lo2, cl2, 100.0, 1, 95.0, n)
    chk("the crown exit survives past bar 5 (multi-day hold, not flat at close)", rc[0] > 5)

    # 8. the crown's breakeven cannot let a winner finish below entry.
    hi3 = np.array([100.0, 108.0, 108.0, 108.0, 99.0, 99.0])
    lo3 = np.array([100.0, 100.0, 100.0, 100.0, 90.0, 90.0])
    rc2 = exit_crown(hi3, lo3, hi3 - 0.5, 100.0, 1, 95.0, 6)
    chk("once breakeven arms, the exit is not below entry", rc2[1] is None or rc2[1] >= 100.0)

    # 8b. net_decline measures the FALL across the run, and is NaN when there is no run.
    cnd = np.array([100.0, 98.0, 96.0, 94.0, 97.0])
    rr = drift_run_tolerant(cnd, 0)
    nd = net_decline(cnd, rr)
    chk("net decline across a 3-bar fall from 100 to 94 is 6.0", abs(nd[4] - 6.0) < 1e-9)
    chk("net decline is NaN where the run is 0", np.isnan(net_decline(cnd, np.zeros(5, int))[4]))
    chk("a SIDEWAYS run inside tolerance has a net decline near 0, so d>0 rejects it",
        abs(net_decline(np.array([100.0, 100.0, 100.0, 100.0, 101.0]),
                        drift_run_tolerant(np.array([100.0, 100.0, 100.0, 100.0, 101.0]), 1))[4]) < 1e-9)

    # 8c. ATR looks only backwards.
    a = atr(np.arange(60.0) + 1, np.arange(60.0), np.arange(60.0) + 0.5, 20)
    a2 = atr(np.concatenate([np.arange(60.0) + 1, [999.0]]),
             np.concatenate([np.arange(60.0), [0.0]]),
             np.concatenate([np.arange(60.0) + 0.5, [500.0]]), 20)
    chk("ATR at bar 40 does not change when a wild future bar is appended",
        abs(a[40] - a2[40]) < 1e-9)

    # 9. the power line refuses an infinite answer.
    chk("delta 0 gives None, not a huge n", power_n(1.0, 0.0) is None)
    chk("the power line is the house formula", power_n(10.0, 5.0) == int(round(15.7 * 100 / 25)))

    # 10. usd() must not use the invalid %-format.
    chk("usd formats with format(), not '%,.0f'", usd(1234567.4) == "1,234,567")

    print("\nSELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------- main

def load_es():
    df = pd.read_csv(ES_CSV)
    rows = len(df)
    ts = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
    df = df.assign(ts=ts)
    df = df.sort_values("ts").reset_index(drop=True)
    return df, rows


def main():
    if "selftest" in sys.argv:
        return selftest()

    sha = lf_sha256(PREREG)
    print("prereg " + PREREG)
    print("  LF sha256 " + sha)
    if sha != PREREG_SHA:
        print("  MISMATCH against the frozen sha " + PREREG_SHA + " - refusing to run")
        return 2
    print("  matches the frozen sha")
    print("harness LF sha256 " + lf_sha256(os.path.abspath(__file__)))

    df, rows = load_es()
    print("ES   ADJ_ES_5m_ETH.csv rows " + usd(rows) + "  first " + str(df["ts"].iloc[0])
          + "  last " + str(df["ts"].iloc[-1]))

    pre = df[df["ts"] <= pd.Timestamp(PRE_LOCKBOX_TO + " 18:00", tz="America/New_York")]
    print("pre-lockbox bars " + usd(len(pre)) + " (ETH session cut 18:00 ET of date_to)")

    o = pre["open"].to_numpy(float); h = pre["high"].to_numpy(float)
    lo = pre["low"].to_numpy(float); c = pre["close"].to_numpy(float)
    ts = pre["ts"].to_numpy()
    n = len(c)

    tsi = pd.DatetimeIndex(pre["ts"])
    # trade date: the ETH session rolls at 18:00 ET, so a bar at or after 18:00 belongs to the
    # NEXT trade date.  Getting this wrong is what cost 24 ENGU-Q runs their parity.
    trade_date = (tsi + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    codes, uniq = pd.factorize(trade_date)
    last_bar_of_day = np.zeros(len(uniq), int)
    for i, k in enumerate(codes):
        last_bar_of_day[k] = i

    rth = (tsi.hour * 60 + tsi.minute >= 9 * 60 + 30) & (tsi.hour * 60 + tsi.minute <= 15 * 60 + 30)
    sma200 = pd.Series(c).rolling(200).mean().shift(1).to_numpy()
    prev_sess_close = np.full(n, np.nan)
    for k in range(1, len(uniq)):
        prev_sess_close[np.flatnonzero(codes == k)] = c[last_bar_of_day[k - 1]]

    higher_close = np.zeros(n, bool)
    higher_close[1:] = (c[1:] > c[:-1]) & (c[1:] > o[1:])

    swing_low = pd.Series(lo).rolling(CROWN_SWING_LOOKBACK).min().shift(1).to_numpy()

    print("\nG0 - counts and gross vs cost, pre-lockbox.  Floor " + str(TRADES_A_YEAR_FLOOR)
          + " trades a year; gross must beat 2 x " + str(HEADLINE_COST) + " pts.")
    years = (tsi[-1] - tsi[0]).days / 365.25
    print("stretch " + str(tsi[0].date()) + " .. " + str(tsi[-1].date())
          + "  " + format(years, ".2f") + " years\n")

    cells = []
    atr20 = atr(h, lo, c, ATR_LEN)
    for k in K_TICKS:
        run = drift_run_tolerant(c, k)
        nd = net_decline(c, run)
        for ndrift in N_DRIFT:
            for d in D_ATR:
                for br_min in BODY_RATIOS:
                    br = body_ratio(o, h, lo, c, ndrift)
                    sig = ((run >= ndrift) & higher_close & rth
                           & ~np.isnan(sma200) & ~np.isnan(atr20) & ~np.isnan(nd)
                           & (nd >= d * atr20))
                    if br_min > 0:
                        sig &= (br >= br_min)
                    cells.append(("D1' k=" + str(k) + "t N>=" + str(ndrift)
                                  + " d=" + format(d, ".1f")
                                  + (" b2" if br_min else " B0"),
                                  np.flatnonzero(sig)))
    for w in SLOPE_WINDOWS:
        sl = drift_slope(c, w)
        for d in D_ATR:
            for br_min in BODY_RATIOS:
                br = body_ratio(o, h, lo, c, w)
                sig = (higher_close & rth & ~np.isnan(sma200) & ~np.isnan(atr20) & ~np.isnan(sl)
                       & (sl <= -(d * atr20) / w))
                if br_min > 0:
                    sig &= (br >= br_min)
                cells.append(("D2' w=" + str(w) + " d=" + format(d, ".1f")
                              + (" b2" if br_min else " B0"),
                              np.flatnonzero(sig)))

    report = {}
    print(format("cell", "<30") + format("n", ">7") + format("a yr", ">8")
          + format("gross pt", ">10") + format("gross R", ">9") + format("cost R", ">8")
          + format("net R", ">8") + format("risk pt", ">9") + format("G0", ">6"))
    for name, idx in cells:
        cnt = len(idx)
        a_yr = cnt / years if years else 0.0
        gp, gr, rk = [], [], []
        for i in idx:
            # Section 7: tagged at the SIGNAL bar, FILLED AT THE NEXT BAR'S OPEN.  The earlier
            # version passed the signal bar itself as the entry bar with that bar's own low as
            # the stop, so `low[entry_bar] <= stop` was true by construction and every trade
            # recorded a full -1R stop-out.  That is what made gross R exactly -1.0000 in all
            # 54 cells - a constant across cells is a bug signature, never a result.
            e = i + 1
            if e >= n:
                continue
            entry_px = o[e]
            stop = lo[i]                     # the BREAKOUT bar's low, per the owner's sketch
            risk = entry_px - stop
            if risk <= 0:                    # the next open gapped to or below the stop
                continue
            r = exit_fixed_r(h, lo, entry_px, e, stop, 1.0, last_bar_of_day, codes, True)
            if r is None:
                continue
            px = r[1] if r[1] is not None else c[r[0]]
            gp.append(px - entry_px)
            gr.append((px - entry_px) / risk)
            rk.append(risk)
        gross = float(np.mean(gp)) if gp else np.nan
        grossR = float(np.mean(gr)) if gr else np.nan
        risk_pt = float(np.mean(rk)) if rk else np.nan
        # cost expressed in R, per trade, because R = the body and therefore VARIES.  Screening
        # a points gross across cells with different risk sizes compares position sizes, not
        # edges - which is the objection section 9.3 raises against MANAGER's scan r1, so it
        # would be indefensible to repeat it here.
        costR = float(np.mean([HEADLINE_COST / x for x in rk])) if rk else np.nan
        netR = grossR - costR if grossR == grossR else np.nan
        verdict = "grey"
        if a_yr < TRADES_A_YEAR_FLOOR:
            verdict = "n"
        elif netR == netR and netR > 0:
            verdict = "LIVE"
        else:
            verdict = "cost"
        report[name] = {"n": cnt, "a_year": round(a_yr, 1),
                        "gross_pts": None if gross != gross else round(gross, 3),
                        "gross_R": None if grossR != grossR else round(grossR, 4),
                        "cost_R": None if costR != costR else round(costR, 4),
                        "net_R": None if netR != netR else round(netR, 4),
                        "risk_pts": None if risk_pt != risk_pt else round(risk_pt, 2),
                        "g0": verdict}
        f = lambda v, w, d=3: format("-" if v != v else format(v, "." + str(d) + "f"), ">" + str(w))
        print(format(name, "<30") + format(usd(cnt), ">7") + format(format(a_yr, ".1f"), ">8")
              + f(gross, 10) + f(grossR, 9, 4) + f(costR, 8, 4) + f(netR, 8, 4)
              + f(risk_pt, 9, 2) + format(verdict, ">6"))

    live = [k for k, v in report.items() if v["g0"] == "LIVE"]
    print("\nG0 cells clearing both screens: " + (", ".join(live) if live else "NONE"))

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "g0.json")
    json.dump({"prereg_sha": sha, "es_rows": rows, "pre_lockbox_bars": int(n),
               "years": round(years, 3), "cells": report, "live": live},
              io.open(out, "w", encoding="utf-8"), indent=1)
    print("wrote " + out)

    # ------------------------------------------------------------------ STAGE 1: THE EXITS
    #
    # G0 greyed every cell on COST, not on sample.  My own note below says a cell greyed on cost
    # is greyed UNDER THE OWNER'S FLAT-AT-CLOSE 1R EXIT ONLY - and that exit is exactly the one
    # section 9.2 charges MANAGER's 399 cells with sharing.  Closing the round here would repeat
    # the flaw I raised, so X4 runs before anything is closed.
    #
    # X1 = the owner's sketch, 1R off the body, stop at the breakout low, flat at the close.
    # X4 = the crown's own exit, swing-low stop, trail from act_R, breakeven, MULTI-DAY HOLD.
    print("\nSTAGE 1 - the exits.  X1 = the owner's 1R flat-at-close; X4 = the crown's")
    print("multi-day exit, the cell MANAGER's 399 have no equivalent of.  One position at a")
    print("time; a signal arriving while a position is open is DROPPED, not queued.\n")

    scored = [(k, idx) for (k, idx) in cells if report[k]["g0"] != "n"]
    print(str(len(scored)) + " cells clear the " + str(TRADES_A_YEAR_FLOOR)
          + "-a-year floor and are scored on both exits.\n")

    all_dates = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(trade_date))))

    def walk(idx, which):
        """One position at a time.  Returns exit trade-dates and gross points per trade."""
        out_d, out_pts, out_r = [], [], []
        busy_until = -1
        for i in idx:
            e = i + 1
            if e >= n or e <= busy_until:
                continue
            entry_px = o[e]
            if which == "X1":
                stop = lo[i]
                risk = entry_px - stop
                if risk <= 0:
                    continue
                r = exit_fixed_r(h, lo, entry_px, e, stop, 1.0, last_bar_of_day, codes, True)
            else:
                sw = swing_low[i]
                if sw != sw:
                    continue
                stop = entry_px - CROWN_STOP_MULT * (entry_px - sw)
                risk = entry_px - stop
                if risk <= 0:
                    continue
                r = exit_crown(h, lo, c, entry_px, e, stop, n)
            if r is None:
                continue
            xi, px, _why = r
            px = px if px is not None else c[xi]
            busy_until = xi
            out_d.append(trade_date[xi])
            out_pts.append(px - entry_px)
            out_r.append(risk)
        # datetime64 explicitly: trade_date[xi] is a pandas Timestamp, so a bare np.array
        # of them comes out OBJECT dtype and will not compare against np.datetime64.
        return (np.array(out_d, dtype="datetime64[ns]"),
                np.array(out_pts, float), np.array(out_r, float))

    def score(name, which, idx):
        d, pts, risk = walk(idx, which)
        if len(pts) < 30:
            return None
        row = {"cell": name, "exit": which, "trades": int(len(pts)),
               "a_year": round(len(pts) / years, 1),
               "mean_risk_pts": round(float(risk.mean()), 2),
               "gross_R": round(float((pts / risk).mean()), 4),
               "ladder": {}}
        for cost in COST_LADDER:
            net_usd = (pts - cost) * DOLLARS_PER_POINT
            ser = daily_series(d, net_usd, all_dates)
            f = four(ser.to_numpy(), ser.index)
            net_r = float(((pts - cost) / risk).mean())
            def rnd(key, nd):
                v = f.get(key)
                return None if v is None else round(float(v), nd)
            row["ladder"][str(cost)] = {
                "roc30": rnd("roc30", 2),          # None on a losing stretch, and that is honest
                "dd5_usd": rnd("dd5_usd", 0),
                "dd_pct_peak": rnd("dd_pct_peak", 2),
                "sortino": rnd("sortino", 3),
                "net_usd": round(float(net_usd.sum()), 0),
                "one_episode": bool(f.get("one_episode")),
                "net_R": round(net_r, 4),
            }
        # folds, at the headline cost, net $ per fold
        net_usd = (pts - HEADLINE_COST) * DOLLARS_PER_POINT
        fl = []
        for a, b in FOLDS:
            m = (d >= np.datetime64(a)) & (d <= np.datetime64(b + "T23:59:59"))
            fl.append(round(float(net_usd[m].sum()), 0))
        row["folds"] = fl
        row["folds_positive"] = int(sum(1 for v in fl if v > 0))
        tot = float(net_usd.sum())
        row["max_fold_share"] = (round(max(fl) / tot, 3) if tot > 0 else None)
        return row

    rows = []
    hdr = (format("cell", "<30") + format("exit", ">4") + format("n", ">7")
           + format("grossR", ">8") + format("netR", ">8") + format("ROC@30k", ">9")
           + format("DD5", ">9") + format("DD%", ">7") + format("Sortino", ">8")
           + format("fold+", ">6") + format("1ep", ">5") + format("net $", ">12"))
    print(hdr)
    for name, idx in scored:
        for which in ("X1", "X4"):
            r = score(name, which, idx)
            if r is None:
                continue
            rows.append(r)
            hl = r["ladder"][str(HEADLINE_COST)]
            def sh(v, w, nd=2, money=False):
                if v is None:
                    return format("-", ">" + str(w))
                t = usd(v) if money else format(float(v), "." + str(nd) + "f")
                return format(t, ">" + str(w))
            print(format(name, "<30") + format(which, ">4") + format(usd(r["trades"]), ">7")
                  + sh(r["gross_R"], 8, 4) + sh(hl["net_R"], 8, 4)
                  + sh(hl["roc30"], 9, 2) + sh(hl["dd5_usd"], 9, 0, True)
                  + sh(hl["dd_pct_peak"], 7, 2) + sh(hl["sortino"], 8, 3)
                  + format(str(r["folds_positive"]) + "/8", ">6")
                  + format(("YES" if hl["one_episode"] else "no"), ">5")
                  + sh(hl["net_usd"], 12, 0, True))

    out1 = os.path.join(OUT_DIR, "stage1.json")
    json.dump({"prereg_sha": sha, "rows": rows}, io.open(out1, "w", encoding="utf-8"), indent=1)
    print("\nwrote " + out1)

    # ------------------------------------------------------------------ the bar, section 5
    print("\nTHE BAR (section 5, written before any of this):")
    cand = []
    for r in rows:
        hl = r["ladder"][str(HEADLINE_COST)]
        c1 = r["a_year"] >= TRADES_A_YEAR_FLOOR
        c2 = r["folds_positive"] >= 7
        c3 = not hl["one_episode"]
        c4 = r["ladder"]["0.75"]["net_usd"] > 0
        c5 = (r["max_fold_share"] is not None and r["max_fold_share"] <= 0.40)
        if c1 and c2 and c3 and c4 and c5:
            cand.append(r)
    if cand:
        print("  CANDIDATES (clauses 1-5): " + ", ".join(x["cell"] + " " + x["exit"] for x in cand))
    else:
        best = max(rows, key=lambda r: r["folds_positive"]) if rows else None
        print("  NO CELL CLEARS CLAUSES 1-5 on either exit.  The lockbox is NOT opened - it is")
        print("  veto-only and cannot rescue a walk-forward failure.")
        if best:
            print("  best fold count on the grid: " + best["cell"] + " " + best["exit"]
                  + " at " + str(best["folds_positive"]) + "/8 (the bar is 7/8)")
        x4 = [r for r in rows if r["exit"] == "X4"]
        x1 = [r for r in rows if r["exit"] == "X1"]
        if x4 and x1:
            print("  X4 vs X1 across the grid, mean net R at the headline cost: X4 "
                  + format(float(np.mean([r["ladder"][str(HEADLINE_COST)]["net_R"] for r in x4])), ".4f")
                  + "  X1 " + format(float(np.mean([r["ladder"][str(HEADLINE_COST)]["net_R"] for r in x1])), ".4f"))
            print("  That comparison is the one MANAGER's scan r1 could not make.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
