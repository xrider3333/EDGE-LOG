"""
ROUND 24 — two genuinely new axes: CALENDAR effects and IMPLIED VOLATILITY (VIX).
Pre-registered 2026-08-25 before any results.

Nothing in the 144 dead cells used a calendar rule or an external volatility series.
VIX comes free from Yahoo (^VIX daily) and is the first non-price input this library
has ever tested.

A. CALENDAR (NQ 5m RTH, intraday only - flat by the close, cost 0.533):
   Long the whole RTH session (buy 09:30 open, sell 16:00 close) on days matching a
   calendar rule. Cells (whole grid):
     tom_last3    - the last 3 trading days of the month
     tom_first3   - the first 3 trading days of the month
     tom_window   - last 3 + first 3 (the classic turn-of-month window)
     mon / tue / wed / thu / fri  - single weekday
     opex_week    - the week containing the 3rd Friday
     opex_friday  - the 3rd Friday itself
   Gate: PF >= 1.25, MAR >= 8, n >= 150 (calendar subsets are small by construction;
   this floor is pre-registered here, before results).
B. VIX REGIME FILTER on the two validated legs (the owner's "filters on champions"
   direction, with a NEW input):
   B1. ORB crown #234 (NQ 5m RTH, cost 0.533, full window to 2026-08-13).
   B2. ENGU-Q ETH #226 (NQ 1m ETH, cost 0.783, window to 2025-06-29).
   For each leg, split its trades by the PRIOR day's VIX close (strictly causal -
   yesterday's close is known before today's open) into terciles computed on a
   252-day trailing window (also causal - no full-sample percentile). Cells: keep
   only LOW / MID / HIGH tercile days, plus the unfiltered baseline.
   Adopt bar (fixed now): a tercile filter is adopted only if MAR rises >= 15% AND
   net falls <= 10% versus that leg's own unfiltered baseline.
Window: A and B2 end 2025-06-29; B1 uses the crown's full window (its lockbox is
already spent - this is an overlay comparison, not a new validation). One look.
"""
import os, sys, csv
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest

RESULTS = []


def score(pnl, fam, cell, floor, mult=20.0):
    p = np.asarray(pnl, float) * mult
    if len(p) == 0:
        RESULTS.append(dict(fam=fam, cell=cell, n=0, net=0, pf=0, dd=0, mar=0, floor=floor)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else float('inf')
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); mar = net / -dd if dd < -1e-9 else float('inf')
    RESULTS.append(dict(fam=fam, cell=cell, n=int(len(p)), net=round(net), pf=round(float(pf), 3),
                        dd=round(float(-dd)), mar=round(float(mar), 2), floor=floor))


def get_vix():
    import yfinance as yf
    v = yf.download("^VIX", start="2009-01-01", end="2026-08-26", interval="1d",
                    auto_adjust=False, progress=False)
    if isinstance(v.columns, pd.MultiIndex):
        v.columns = v.columns.get_level_values(0)
    s = v["Close"].dropna()
    s.index = [d.date() for d in s.index]
    return s


def main():
    m5 = find_master("NQ", "5m", "rth", "db_noadj_rth")
    R = load_master_arrays(m5, date_to="2026-08-13")
    o5, h5, l5, c5, did5 = R["open"], R["high"], R["low"], R["close"], R["day_id"]
    idx5 = R["index"]
    sess = []; a = 0; n5 = len(c5)
    while a < n5:
        b = a
        while b < n5 and did5[b] == did5[a]:
            b += 1
        sess.append((a, b)); a = b
    do = np.array([o5[x] for x, y in sess]); dc = np.array([c5[y - 1] for x, y in sess])
    dates = [idx5[x].date() for x, y in sess]
    nd = len(sess)
    ts = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])

    # ---------- A: calendar ----------
    cutoff = pd.Timestamp("2025-06-29").date()
    ym = np.array([d.year * 12 + d.month for d in dates])
    is_first3 = np.zeros(nd, bool); is_last3 = np.zeros(nd, bool)
    i = 0
    while i < nd:
        j = i
        while j < nd and ym[j] == ym[i]:
            j += 1
        is_first3[i:min(i + 3, j)] = True
        is_last3[max(i, j - 3):j] = True
        i = j
    dow = np.array([d.weekday() for d in dates])
    third_fri = np.zeros(nd, bool); opex_week = np.zeros(nd, bool)
    for k in range(nd):
        d = dates[k]
        if d.weekday() == 4 and 15 <= d.day <= 21:
            third_fri[k] = True
    for k in np.where(third_fri)[0]:
        lo = k
        while lo > 0 and dates[lo - 1].weekday() < dates[lo].weekday():
            lo -= 1
        opex_week[lo:k + 1] = True
    CAL = {"tom_last3": is_last3, "tom_first3": is_first3,
           "tom_window": is_last3 | is_first3,
           "mon": dow == 0, "tue": dow == 1, "wed": dow == 2, "thu": dow == 3, "fri": dow == 4,
           "opex_week": opex_week, "opex_friday": third_fri}
    for name, mask in CAL.items():
        pnl = [(dc[d] - do[d]) - 0.533 for d in range(nd)
               if mask[d] and dates[d] <= cutoff]
        score(pnl, "A-CAL", name, 150)
    print("A done", flush=True)

    # ---------- B: VIX regime on the two legs ----------
    vix = get_vix()
    vdates = list(vix.index); vvals = np.asarray(vix.values, float)
    vmap = {d: v for d, v in zip(vdates, vvals)}
    prev_vix = np.full(nd, np.nan)
    hist = []
    for k in range(nd):
        pv = None
        for back in range(1, 6):
            cand = dates[k] - pd.Timedelta(days=back).to_pytimedelta()
            if cand in vmap:
                pv = vmap[cand]; break
        prev_vix[k] = pv if pv is not None else np.nan
    # causal terciles on a trailing 252-day window of prior-day VIX
    lo_th = np.full(nd, np.nan); hi_th = np.full(nd, np.nan)
    for k in range(nd):
        w = prev_vix[max(0, k - 252):k]
        w = w[~np.isnan(w)]
        if len(w) >= 100:
            lo_th[k] = np.percentile(w, 33.3); hi_th[k] = np.percentile(w, 66.7)

    starts = np.array([x for x, y in sess])

    def bucket(dayix):
        v = prev_vix[dayix]
        if np.isnan(v) or np.isnan(lo_th[dayix]):
            return None
        return "low" if v <= lo_th[dayix] else ("high" if v >= hi_th[dayix] else "mid")

    import importlib.util as _ilu
    _sp = _ilu.spec_from_file_location("c2", os.path.join(ROOT, "augur_strategies", "ORB_3_6_C2.py"))
    c2 = _ilu.module_from_spec(_sp); _sp.loader.exec_module(c2)
    P2 = {k: v["default"] for k, v in c2.DEFAULT_PARAMS.items()}
    r = run_backtest("ORB_3_6_C2.py", instrument="NQ", timeframe="5m", session="rth",
                     source="db_noadj_rth", date_from="2010-06-07", date_to="2026-08-13",
                     params=P2, cost_pts=0.533, return_trades=True)
    tr = r["trades"]
    print(f"ORB parity n={r['num_trades']} net=${r['total_pnl']*20:,.0f} PF={r['profit_factor']:.3f}", flush=True)
    tday = np.searchsorted(starts, [t[0] for t in tr], side="right") - 1
    buckets = [bucket(int(d)) for d in tday]
    score([t[2] for t in tr], "B1-ORBVIX", "baseline", 300)
    for b in ("low", "mid", "high"):
        score([t[2] for i, t in enumerate(tr) if buckets[i] == b], "B1-ORBVIX", "keep_" + b, 150)

    me = find_master("NQ", "1m", "eth", "db_noadj_eth")
    _sp2 = _ilu.spec_from_file_location("eq", os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_ETH_1_0.py"))
    eq = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(eq)
    PE = {k: v["default"] for k, v in eq.DEFAULT_PARAMS.items()}
    re_ = run_backtest("ENGUQ_1M_ETH_1_0.py", instrument="NQ", timeframe="1m", session="eth",
                       source="db_noadj_eth", date_from="2010-06-07", date_to="2025-06-29",
                       params=PE, cost_pts=0.783, return_trades=True)
    E = load_master_arrays(me, date_from="2010-06-07", date_to="2025-06-29")
    eidx = E["index"]
    tre = re_["trades"]
    print(f"ENGUQ parity n={re_['num_trades']} net=${re_['total_pnl']*20:,.0f} PF={re_['profit_factor']:.3f}", flush=True)
    date_to_ix = {d: i for i, d in enumerate(dates)}
    eb = []
    for t in tre:
        d = eidx[t[0]].date()
        ix = date_to_ix.get(d)
        eb.append(bucket(ix) if ix is not None else None)
    score([t[2] for t in tre], "B2-EQVIX", "baseline", 300)
    for b in ("low", "mid", "high"):
        score([t[2] for i, t in enumerate(tre) if eb[i] == b], "B2-EQVIX", "keep_" + b, 150)
    print("B done", flush=True)

    print(f"\n{'fam':11}{'cell':14}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'MAR':>7}  gate")
    for r_ in RESULTS:
        g = "PASS" if (r_['pf'] >= 1.25 and r_['mar'] >= 8 and r_['n'] >= r_['floor']) else "fail"
        print(f"{r_['fam']:11}{r_['cell']:14}{r_['n']:>6}{r_['net']:>11,}{r_['pf']:>7.3f}{r_['dd']:>10,}{r_['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r24_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r24_triage.csv")


if __name__ == "__main__":
    main()
