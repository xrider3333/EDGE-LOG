"""
ORB ROUND 12 — does the crown diversify across BAR SIZES / opening-range length?
(2026-09-09, per ROUND12_SPEC-style brief: "test whether the ORB crown diversifies
across bar sizes and report honestly.")

BACKGROUND THIS RUN MUST HONOUR:
  * A meta walk-forward showed re-optimising ORB params has NO forward skill
    (re-picked configs earned $166k over 11 forward years vs $377k leaving the
    parent defaults alone). So this file does NOT hunt parameters — it holds every
    crown parameter fixed and moves ONLY or_bars (the opening-range length).
  * Several ORB findings were retracted this week for being one lucky year, a
    leverage win, or a scan that failed its null. Assume any positive first result
    here is one of those until the per-unit / per-year tests below say otherwise.

THE QUESTION: the crown trades a 2-bar (10-minute) opening range on 5-minute bars.
Is a 3/4/6/9/12-bar range (15/20/30/45/60 min) a genuinely different bet — different
days, low correlation, a real drawdown cut when pooled — or the same bet in a
different hat?

METHOD:
  1. Ladder: or_bars in {2 (crown), 3, 4, 6, 9, 12} on the 5-minute master, every
     other CROWN param held fixed (atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5,
     target_R=5.0, be_after_R=0.5, breakout_buf=0.25 unchanged, close_confirm=True,
     flat_eod=True, skip_holidays=True, trade_mode="First-candle dir",
     partial_exit_R=0, trail_bars=0). Standard table on FULL/IS/OOS/5y, crown first.
  2. Overlap + correlation: for every pair, the fraction of trading days BOTH take
     >=1 trade, and correlation of daily net $ (days with no trade from either = 0,
     i.e. correlation of the full daily P&L series, not just the intersection —
     that is the honest number for "does pooling smooth anything").
  3. Pooling: crown + each other variant, ONE UNIT EACH, scored PER UNIT (divide
     pooled net/DD by 2). Passes only if per-unit MAR beats the crown's AND per-unit
     DD is genuinely lower (not just a rounding wiggle — require >=5% lower).
     Anything that only raises net is flagged as a leverage artefact, not a win.
  4. Year-by-year: repeat the per-unit pooled-vs-crown comparison for each of the
     16 calendar years and count how many years the pool actually wins on both
     axes. A win living in <=2 years is not a win.

No resampling cross-check: the harness's bars() master is fixed at 5-minute
resolution and the strategy consumes raw OHLCV arrays with no resample utility in
tools/orb_pick.py or orb_hunt.py, so building a clean, no-look-ahead 10/15/30-minute
resample of the master is out of scope for this pass and was skipped; the required
deliverable is the or_bars ladder on 5-minute bars, which is what follows. Said here
plainly per the "say which you did" instruction.

Usage:
    python tools/orb_hunt12_tf.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END        # noqa: E402
from tools.orb_hunt3 import robustness                   # noqa: E402

COST, MULT = 0.533, 20.0
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

# CROWN (run #314) params, per shared spec — everything fixed except or_bars.
CROWN_PARAMS = dict(
    or_bars=2, trade_mode="First-candle dir", close_confirm=True,
    partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
    breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
    atr_filter=0.75, vpace_filter=0.8,
)

LADDER = [2, 3, 4, 6, 9, 12]   # bars -> 10, 15, 20, 30, 45, 60 minutes
MIN_LABEL = {2: "10min (CROWN)", 3: "15min", 4: "20min", 6: "30min", 9: "45min", 12: "60min"}

WINDOWS = [("FULL", None, LB_END), ("IS", None, IS_END), ("OOS", IS_END, LB_END),
           ("5y", "2021-08-13", LB_END)]

_B = None


def bars():
    global _B
    if _B is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        _B = dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                  low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                  volume=df["volume"].values.astype(float),
                  day_id=pd.factorize(df["_dt"].dt.date)[0],
                  index=pd.DatetimeIndex(df["_dt"]))
    return _B


def trades_of(or_bars_val):
    """Run ORB_3_6 ONCE per config on the whole master (through LB_END); slice
    afterwards so every window shares warm-up + filter history."""
    b = bars()
    over = dict(CROWN_PARAMS, or_bars=or_bars_val)
    r = strat("ORB_3_6.py").run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **over)
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d <= le:
            out.append((d.tz_localize(None), (t[2] - COST) * MULT, t[3]))
    return out


def stats(tr):
    """tr = [(entry_datetime, net$, dir)] already sliced to window."""
    if len(tr) < 5:
        return None
    dts = [d for d, _, _ in tr]
    p = np.array([x for _, x, _ in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    if yrs <= 0:
        return None
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    return dict(n=len(p), net=p.sum(), dd=dd,
                pf=(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.inf,
                mar=(p.sum() / yrs) / dd if dd else np.inf,
                evr=evr, ryr=(evr * len(p) / yrs) if yrs > 0 else np.nan,
                tpy=len(p) / yrs, worst12=rob["worst"], win12=rob["win_pct"], yrs=yrs)


def slice_window(tr, start, end):
    s = pd.Timestamp(start) if start else None
    e = pd.Timestamp(end) if end else None
    out = []
    for d, v, dirn in tr:
        if s is not None and d < s:
            continue
        if e is not None and d > e:
            continue
        out.append((d, v, dirn))
    return out


def print_table(cache, title):
    print("\n" + "=" * 132)
    print(title)
    print("=" * 132)
    for wlab, wstart, wend in WINDOWS:
        print("\n%-16s (from %s to %s)" % (wlab, wstart or "start", wend))
        print("%-16s %6s %10s %10s %6s %7s %7s %7s %6s"
              % ("config", "n", "net$", "DD$", "PF", "MAR", "EV R", "R/YR", "tr/yr"))
        print("-" * 100)
        for ob in LADDER:
            tr = slice_window(cache[ob], wstart, wend)
            s = stats(tr)
            if s is None:
                print("%-16s   (insufficient trades)" % MIN_LABEL[ob])
                continue
            print("%-16s %6d %10s %10s %6.2f %7.2f %7.3f %7.1f %6.0f"
                  % (MIN_LABEL[ob], s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}",
                     s["pf"], s["mar"], s["evr"], s["ryr"], s["tpy"]))


def daily_series(tr, all_days):
    """Return a pd.Series of net$ indexed by calendar date over the FULL window
    (through LB_END), zero-filled on non-trading days AND on traded-but-empty days,
    so correlation is computed over the identical, aligned daily index."""
    s = pd.Series(0.0, index=pd.DatetimeIndex(sorted(all_days)))
    by_day = {}
    for d, v, _ in tr:
        dd = pd.Timestamp(d.date())
        by_day[dd] = by_day.get(dd, 0.0) + v
    for dd, v in by_day.items():
        if dd in s.index:
            s.loc[dd] = v
    return s


def overlap_and_corr(cache, all_days, start=None, end=None):
    print("\n" + "=" * 132)
    print("OVERLAP + CORRELATION  (day both take >=1 trade / correlation of daily $ series)"
          + ("  window=%s..%s" % (start or "start", end or "end") if (start or end) else "  FULL window"))
    print("=" * 132)
    day_sets = {}
    series = {}
    for ob in LADDER:
        tr = slice_window(cache[ob], start, end)
        days = set()
        for d, v, _ in tr:
            days.add(d.date())
        day_sets[ob] = days
        series[ob] = daily_series(tr, [d for d in all_days if
                                        (start is None or pd.Timestamp(d) >= pd.Timestamp(start)) and
                                        (end is None or pd.Timestamp(d) <= pd.Timestamp(end))])
    print("%-16s" % "config", end="")
    for ob in LADDER:
        print("%14s" % MIN_LABEL[ob], end="")
    print()
    for ob1 in LADDER:
        print("%-16s" % MIN_LABEL[ob1], end="")
        for ob2 in LADDER:
            if ob1 == ob2:
                print("%14s" % "-", end="")
                continue
            both = len(day_sets[ob1] & day_sets[ob2])
            either = len(day_sets[ob1] | day_sets[ob2]) or 1
            corr = np.corrcoef(series[ob1].values, series[ob2].values)[0, 1]
            print("%6.1f%%/%5.2f" % (100.0 * both / max(len(day_sets[ob1]), 1), corr), end="")
        print()
    print("(cell = %% of config-A's trade days that OB also traded / correlation of daily $)")
    return day_sets, series


def pool_per_unit(tr_a, tr_b):
    """Pool two trade lists 1 unit each; return per-unit stats keyed on the union
    calendar-day P&L stream (sum both legs' pnl per day, /2 units)."""
    by_day = {}
    for d, v, _ in tr_a:
        dd = d.date()
        by_day[dd] = by_day.get(dd, 0.0) + v
    for d, v, _ in tr_b:
        dd = d.date()
        by_day[dd] = by_day.get(dd, 0.0) + v
    if not by_day:
        return None
    days = sorted(by_day)
    p = np.array([by_day[d] / 2.0 for d in days], float)  # per unit
    dts = pd.DatetimeIndex(days)
    yrs = (dts[-1] - dts[0]).days / 365.25
    if yrs <= 0:
        return None
    cum = np.cumsum(p)
    dd_ = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    net = p.sum()
    mar = (net / yrs) / dd_ if dd_ else np.inf
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    return dict(net=net, dd=dd_, mar=mar, pf=pf, n=len(p), yrs=yrs)


def single_per_unit(tr):
    by_day = {}
    for d, v, _ in tr:
        dd = d.date()
        by_day[dd] = by_day.get(dd, 0.0) + v
    if not by_day:
        return None
    days = sorted(by_day)
    p = np.array([by_day[d] for d in days], float)
    dts = pd.DatetimeIndex(days)
    yrs = (dts[-1] - dts[0]).days / 365.25
    if yrs <= 0:
        return None
    cum = np.cumsum(p)
    dd_ = abs(float((cum - np.maximum.accumulate(cum)).min()))
    net = p.sum()
    mar = (net / yrs) / dd_ if dd_ else np.inf
    return dict(net=net, dd=dd_, mar=mar, yrs=yrs)


def pooling_test(cache):
    print("\n" + "=" * 132)
    print("POOLING TEST  crown (10min) + each variant, ONE UNIT EACH, scored PER UNIT (net/DD /2)")
    print("=" * 132)
    crown_tr = cache[2]
    crown_solo = single_per_unit(crown_tr)
    print("crown alone (per unit): net=$%s  DD=$%s  MAR=%.3f"
          % (f"{crown_solo['net']:,.0f}", f"{crown_solo['dd']:,.0f}", crown_solo["mar"]))
    print("\n%-16s %10s %10s %7s %8s %8s %10s" %
          ("pooled with", "net$/unit", "DD$/unit", "MAR", "MAR>crown", "DD<crown-5%", "VERDICT"))
    print("-" * 90)
    results = {}
    for ob in LADDER:
        if ob == 2:
            continue
        pooled = pool_per_unit(crown_tr, cache[ob])
        mar_beats = pooled["mar"] > crown_solo["mar"]
        dd_beats = pooled["dd"] <= crown_solo["dd"] * 0.95
        verdict = "PASS" if (mar_beats and dd_beats) else "FAIL (leverage/no real cut)"
        results[ob] = (pooled, mar_beats, dd_beats, verdict)
        print("%-16s %10s %10s %7.3f %8s %8s %10s" %
              (MIN_LABEL[ob], f"{pooled['net']:,.0f}", f"{pooled['dd']:,.0f}", pooled["mar"],
               str(mar_beats), str(dd_beats), verdict))
    return crown_solo, results


def year_by_year(cache):
    print("\n" + "=" * 132)
    print("YEAR-BY-YEAR  per-unit pooled-vs-crown, each pooled pair, 16 calendar years")
    print("=" * 132)
    crown_tr = cache[2]
    years = list(range(2010, 2026))
    for ob in LADDER:
        if ob == 2:
            continue
        wins = 0
        checked = 0
        detail = []
        for y in years:
            start, end = "%d-01-01" % y, "%d-12-31" % y
            ca = slice_window(crown_tr, start, end)
            cb = slice_window(cache[ob], start, end)
            if len(ca) < 5 and len(cb) < 5:
                continue
            solo = single_per_unit(ca)
            pooled = pool_per_unit(ca, cb)
            if solo is None or pooled is None:
                continue
            checked += 1
            win = (pooled["mar"] > solo["mar"]) and (pooled["dd"] <= solo["dd"] * 0.95)
            wins += int(win)
            detail.append((y, win, solo["mar"], pooled["mar"], solo["dd"], pooled["dd"]))
        print("\n%s pooled with crown: %d/%d years pass BOTH tests" % (MIN_LABEL[ob], wins, checked))
        for y, win, sm, pm, sd, pd_ in detail:
            print("   %d  crown MAR=%.2f DD=$%s  pooled MAR=%.2f DD=$%s  %s"
                  % (y, sm, f"{sd:,.0f}", pm, f"{pd_:,.0f}", "PASS" if win else "fail"))


def main():
    b = bars()
    all_days = sorted(set(pd.Series(b["index"]).dt.date))
    print("ROUND 12 — ORB crown across bar sizes / opening-range length (or_bars ladder)")
    print("Master: NQ 5m RTH, %d bars, %d sessions. COST=%.3f pts/RT MULT=%.0f" %
          (len(b["close"]), len(all_days), COST, MULT))
    print("CROWN params (fixed except or_bars): %s" % CROWN_PARAMS)

    cache = {}
    for ob in LADDER:
        cache[ob] = trades_of(ob)
        print("  or_bars=%-3d (%s): %d trades through LB_END" % (ob, MIN_LABEL[ob], len(cache[ob])))

    print_table(cache, "STANDARD TABLE — crown row first, then the ladder")

    overlap_and_corr(cache, all_days)

    crown_solo, pool_results = pooling_test(cache)

    year_by_year(cache)

    print("\n" + "=" * 132)
    print("READ")
    print("=" * 132)
    any_pass = any(v[3] == "PASS" for v in pool_results.values())
    if any_pass:
        print("At least one variant PASSED the per-unit pooling test on both MAR and DD.")
    else:
        print("NO variant passed the per-unit pooling test on both MAR and DD. Any variant that only")
        print("raised pooled NET is a leverage artefact (two units of correlated risk), not a real")
        print("drawdown cut, and is rejected per the pre-registered rule.")


if __name__ == "__main__":
    main()
