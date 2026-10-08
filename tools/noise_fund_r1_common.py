# -*- coding: utf-8 -*-
"""Shared pieces for the NOISE habitat rounds that reuse IWM r1's design on other funds (scope A2 sector funds, A4 TLT
fade): docs/PREREG_noise_sectors_r1_2026-10-08.md and docs/PREREG_noise_tltfade_r1_2026-10-08.md.

The IWM r1 harness (tools/noise_iwm_r1_stageA.py) is imported unchanged; its module globals FUND and BASE are set per
call, so the 54-cell grid, the unit rule (floor($100k / the 2016-06-30 close)), the cost as traded and the walk-forward
window are IWM r1's to the letter. Masters come from the NOISE fund pull (C:\\EdgeLog\\_anatomy_cache\\noise_funds_r1).
"""
import math
import os
import sys
import zlib

import numpy as np
import pandas as pd

os.environ.setdefault("EDGELOG_ROCFRONTIER_R8", r"C:\EdgeLog\_anatomy_cache\noise_funds_r1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import noise_iwm_r1_stageA as M                                       # noqa: E402
from augur_engine.drawdowns import dd5                                # noqa: E402

R8, HH = M.R8, M.HH
GRID, CENTRE, SEED, NULL_DRAWS, COST_BPS = M.GRID, M.CENTRE, M.SEED, M.NULL_DRAWS, M.COST_BPS
AXES = ((20, 40, 60), (0.5, 0.75, 1.0), (0.75, 1.0, 1.5), (1.25, 1.75))
INHERITED = dict(M.BASE)
FILTERS_OFF = dict(M.BASE, daytype_mode="off", vol_skip_pct=0.0)
DRY = False                                                           # --dry: every cell's directions replaced by a coin flip


def load(fund):
    M.FUND = fund
    return M.load()


def cell(fund, c, a5, unit, q, base=None, fade=False):
    """One grid cell's WF trades on `fund`, cost as traded. base: the BASE settings (inherited filters by default).
    fade: the MIRROR of every trade (same bars, opposite direction): pnl = -(gross) - cost."""
    M.FUND = fund
    M.BASE = INHERITED if base is None else base
    try:
        df = M.cell(c, a5, unit, q)
    finally:
        M.BASE = INHERITED
    if fade:
        cst = R8.COST * unit * df.ratio.to_numpy()
        gross = df.pnl.to_numpy() + cst
        df = df.assign(pnl=-gross - cst, side=-df.side.to_numpy())
    if DRY:                                                           # smoke test of the whole path with no real direction
        cst = R8.COST * unit * df.ratio.to_numpy()
        coin = np.random.default_rng(zlib.crc32(repr((fund, c, fade)).encode())).choice([-1.0, 1.0], size=len(df))
        df = df.assign(pnl=coin * (df.pnl.to_numpy() + cst) - cst, side=coin * df.side.to_numpy())
    return df


def daily(df, bdays):
    return M.daily(df, bdays)


def own(df, bdays):
    return HH.own(daily(df, bdays), bdays)


def dd5_line(df, bdays):
    d = dd5(pd.Series(daily(df, bdays), index=bdays))
    if not d["dd5_usd"]:
        return "DD5 n/a"
    return "DD5 $%s, worst $%s (worst / DD5 %.2f%s)" % (format(int(d["dd5_usd"]), ","), format(int(d["max_dd"]), ","),
                                                       d["max_dd"] / d["dd5_usd"],
                                                       ", driven by one episode" if d["one_episode"] else "")


NULL_DRAWS_R1 = 2000                                                  # review #73: 2,000 draws (IWM r1 used 200)
BOOK_TRADES = os.path.join("C:/EdgeLog/_anatomy_cache/rocfrontier/r4", "book463_trades.csv")
DD_EPISODE = 14950.0                                                  # the house rule: #463's 28 episodes / 460 days


def session_signs(bdays, draws=NULL_DRAWS_R1, seed=SEED):
    """ONE random sign per SESSION per draw, shared by every cell and every fund (review #73 item 1): it keeps the
    re-entries' within-day dependence and the cross-cell / cross-fund correlation, so the max over cells is calibrated.
    NOISE trades are flat by the close, so a trade's session is its exit day (= the daily row it lands on)."""
    return np.random.default_rng(seed).choice(np.array([-1.0, 1.0]), size=(draws, len(bdays)))


def roc_draws(df, unit, bdays, S):
    """Own ROC@$30k of one cell under every draw of S (draws x days): daily gross x the day's sign, cost kept.
    The same arithmetic as r11_risk.stats (peak starts at 0; ROC = 30 x net a year / max drawdown)."""
    cst = R8.COST * unit * df.ratio.to_numpy()
    g = pd.Series(df.pnl.to_numpy() + cst, index=df.date).groupby(level=0).sum().reindex(bdays, fill_value=0.0).to_numpy()
    c = pd.Series(cst, index=df.date).groupby(level=0).sum().reindex(bdays, fill_value=0.0).to_numpy()
    x = S * g - c
    cum = np.cumsum(x, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.zeros((len(x), 1)), cum], axis=1), axis=1)[:, 1:]
    mdd = (peak - cum).max(axis=1)
    yrs = (bdays[-1] - bdays[0]).days / 365.25
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(mdd > 0, 30.0 * (x.sum(axis=1) / yrs) / mdd, np.nan)


def book_series(bdays):
    """#422's daily P&L (the book's NOISE leg) and helpers for the correlation report (review #73 item 6)."""
    t = pd.read_csv(BOOK_TRADES, parse_dates=["date"])
    n = t[t.strategy == "NOISE_1_8_CT304H.py"].groupby("date").pnl.sum()
    return n.reindex(bdays, fill_value=0.0)


def dd_episodes(book_daily):
    """#463's drawdown episodes by the house rule: (first day after the peak, trough day) for every episode >= $14,950."""
    eq = book_daily.to_numpy().cumsum()
    out, peak, peak_i, j, n = [], 0.0, -1, 0, len(eq)
    while j < n:
        if eq[j] >= peak:
            peak, peak_i = eq[j], j
            j += 1
            continue
        k = j
        while k < n and eq[k] < peak:
            k += 1
        tr = j + int(np.argmin(eq[j:k]))
        if peak - eq[tr] >= DD_EPISODE:
            out.append((book_daily.index[peak_i + 1], book_daily.index[tr]))
        j = k
    return out


def ex_dividend_days(sym):
    """Ex-dividend sessions for `sym` from the ETF dividend calendar MANAGER pulls (review #73 item 3); None if absent."""
    p = os.path.join(os.environ["EDGELOG_ROCFRONTIER_R8"], "etf_dividends.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p, parse_dates=["ex_date"])
    return pd.DatetimeIndex(d.loc[d.symbol == sym, "ex_date"]).normalize()


def ex_dividend_line(df, sym):
    ex = ex_dividend_days(sym)
    if ex is None and DRY:
        return "ex-dividend calendar missing (dry run only - a real run stops here)"
    if ex is None:
        raise SystemExit("STOP: no ETF dividend calendar (%s) - the review #73 item 3 report needs it before any run" % sym)
    m = pd.DatetimeIndex(df["entry"]).normalize().isin(ex)
    return "ex-dividend sessions: %d in the calendar; %d trades on them, net $%s (prior close not dividend-adjusted)" % (
        len(ex), int(m.sum()), format(int(df.pnl[m].sum()), ","))


def neighbours(best):
    nb = []
    for i, ax in enumerate(AXES):
        j = ax.index(best[i])
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(ax):
                c = list(best)
                c[i] = ax[jj]
                nb.append(tuple(c))
    return nb


def day_structure(df, label):
    """MANAGER #67's check: single-trade sessions vs multi-break sessions (first breaks / later breaks)."""
    df = df.sort_values("entry")
    sess = pd.Series(pd.DatetimeIndex(df["entry"]).normalize())
    k = sess.map(sess.value_counts()).to_numpy()
    one, first = k == 1, ~sess.duplicated().to_numpy()
    p = df.pnl.to_numpy()
    print("  DAY STRUCTURE %s: %d trades in %d sessions; single-trade sessions %d (%.1f%% of trades) net $%s; multi-break "
          "%d trades net $%s (first breaks $%s, later $%s)   [NQ #422: 28.6%% of trades, 97.4%% of unit $]" % (
              label, len(df), sess.nunique(), int(one.sum()), 100 * one.mean(), format(int(p[one].sum()), ","),
              int((~one).sum()), format(int(p[~one].sum()), ","), format(int(p[~one & first].sum()), ","),
              format(int(p[~first].sum()), ",")))


def held_to_close(df, a5):
    """True where the trade exits on its session's LAST bar (held to the close) - the trade table does not separate a VWAP
    exit from a stop, so every other exit is 'exited earlier'."""
    idx = pd.DatetimeIndex(a5["index"])
    if idx.tz is not None:
        idx = idx.tz_localize(None)                                   # the trade table's times are Eastern wall clock
    last = pd.Series(idx, index=idx.normalize()).groupby(level=0).max()
    ex = pd.DatetimeIndex(df["exit"])
    if ex.tz is not None:
        ex = ex.tz_localize(None)
    return np.asarray(ex == pd.DatetimeIndex(last.reindex(ex.normalize()).to_numpy()))


def reports(df, unit, bdays, years, x):
    """IWM r1's report rows (amendment 1 included) on one crown."""
    h1 = df[df.date < pd.Timestamp("2022-01-01")]
    h2 = df[df.date >= pd.Timestamp("2022-01-01")]
    for lab, h in (("H1 2016-21", h1), ("H2 2022-25", h2), ("longs", df[df.side > 0]), ("shorts", df[df.side < 0])):
        hp = h.pnl[h.pnl > 0].sum() / -h.pnl[h.pnl < 0].sum() if (h.pnl < 0).any() else np.inf
        print("  REPORT %-11s n %5d  net $%10s  PF %.3f" % (lab, len(h), format(int(h.pnl.sum()), ","), hp))
    yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
    print("  REPORT per July-June year $: %s" % ", ".join(format(int(v), ",") for v in yrs))
    notional = df.px.to_numpy() * unit
    fy = np.where(df.date.dt.month >= 7, df.date.dt.year, df.date.dt.year - 1)
    print("  REPORT per July-June year: trades / mean notional a trade: %s" % ", ".join(
        "%d: %d / $%s" % (y, int((fy == y).sum()), format(int(notional[fy == y].mean()), ",")) for y in range(2016, 2025)
        if (fy == y).any()))
    cost_usd = R8.COST * unit * df.ratio.to_numpy()
    print("  REPORT trades a year %.0f; realised cost %.1f bps of notional a round trip (median %.1f)" % (
        len(df) / years, 1e4 * cost_usd.sum() / notional.sum(), float(np.median(1e4 * cost_usd / notional))))
    for bps in COST_BPS:
        g = df.pnl.to_numpy() + cost_usd
        s2 = HH.own(pd.Series(g - bps / 1e4 * notional, index=df.date).groupby(level=0).sum()
                    .reindex(bdays, fill_value=0.0).to_numpy(), bdays)
        print("  REPORT cost %2d bps round trip: net $%s  own ROC@30k %.2f" % (bps, format(int(s2["net"]), ","), s2["roc"]))
    return yrs


def history_share(a5):
    sess = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(a5["index"]).tz_localize(None).normalize())))
    wfs = sess[(sess >= R8.WF0) & (sess < R8.LB0)]
    pos = sess.get_indexer(wfs)
    return int((pos < 252).sum()), len(wfs)


def bars(st, pf, n, years, yrs, x, bdays, B, label, q95, nbr):
    a1, no2020, route = HH.standalone(st, pf, n, years, yrs, x, bdays, B, label)
    a2 = st["roc"] > q95
    a3 = sum(v >= 0.5 * st["roc"] for v in nbr) >= math.ceil(len(nbr) / 2)
    for lab, ok in (("A1 own ROC@30k >= 15 or earner route (%s), PF > 1, >= 100 and 50/yr, >= 6 of 9 years" % route, a1),
                    ("A1b no-2020: the same route holds without calendar 2020", no2020),
                    ("A2 crown above the sign-flip null's p95 (prices the selection)", a2),
                    ("A3 plateau: at least half the one-step neighbours keep half the crown's ROC", a3)):
        print("  %-80s %s" % (lab, "PASS" if ok else "FAIL"))
    return all((a1, no2020, a2, a3))
