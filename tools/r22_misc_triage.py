"""
ROUND 22 — the crown risk-engine (tight stop + breakeven + ride) applied to the two
entry contexts that keep showing real PF but failing MAR. Pre-registered 2026-08-24.

Motivation (126 dead cells of evidence): the two validated house edges (ORB #234,
ENGU-Q #226) both clear MAR 8 through RISK TRUNCATION - tight initial stop, breakeven
armed on a close and acted on the NEXT bar, then ride - not through entry magic.
The dip-buy family shows PF 1.4-2.3 everywhere but dies on MAR with no stop.
This round marries them.

A. PULLTRIG - dip + trigger + crown risk engine (NQ 5m RTH):
   Setup day t (in uptrend, close > SMA200): a dip fires -
     dip=ema20 : day t's low touches the 20-day EMA
     dip=rsi2  : RSI(2) of daily closes < 10
   Trigger day t+1: first 5m CLOSE above day t's high -> enter long at the next
   bar's OPEN (close-confirmed, next-bar fill - the #234 convention).
   Risk engine: initial stop = entry - k x (entry - dl[t]) with k in {0.75, 1.0}
   (risk anchored at the setup day's low); breakeven armed when a 5m close reaches
   entry + 1R, stop moves to entry on the NEXT bar; exit at session close of the
   ENTRY day (flat by close - no overnight). Gap-honest stop fills.
   Cells: 2 dips x 2 stops = 4. Cost 0.533. Floor n >= 300.
B. PMBRK - midday-consolidation break with the same risk engine (NQ 5m RTH):
   Range = 12:00-14:00 ET high/low. After 14:00, first 5m CLOSE beyond the range
   (either side) -> enter at next bar OPEN in that direction. Initial stop =
   entry -/+ k x range with k in {0.75, 1.0}; breakeven at +1R (same arm/act
   rule); exit at session close. Cells: 2 stops x {both-dir} = 2. Cost 0.533.
   Floor n >= 300.
C. ENGU-Q 5m ETH RELOCATION: ENGUQ_5M_1_0.py (the 5m port of the mechanism) on
   the NQ 5m ETH master, params = the #226 1m-ETH frozen config clock-scaled /5
   (tl_len 34, ema_len 276, atr_len 21, others unchanged). ONE cell, overnight
   cost 0.783. Transfer evidence bar PF >= 1.15; candidate bar PF >= 1.25 &
   MAR >= 8 & n >= 300.
Window ends 2025-06-29; lockbox never loaded. Whole grid above; one look.
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest

DATE_TO = "2025-06-29"; MULT = 20.0; RT = 0.533
RESULTS = []


def score(pnl, fam, cell, floor=300):
    p = np.asarray(pnl, float) * MULT
    if len(p) == 0:
        RESULTS.append(dict(fam=fam, cell=cell, n=0, net=0, pf=0, dd=0, mar=0, floor=floor)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else float('inf')
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); mar = net / -dd if dd < -1e-9 else float('inf')
    RESULTS.append(dict(fam=fam, cell=cell, n=int(len(p)), net=round(net), pf=round(float(pf), 3),
                        dd=round(float(-dd)), mar=round(float(mar), 2), floor=floor))


def wilder_rsi(x, per):
    d = np.diff(x, prepend=x[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


def ride_long(o5, h5, l5, c5, ei_open, b1, entry, stop0):
    """enter at o5[ei_open]; BE armed on close >= entry+1R, acts next bar; exit close."""
    R = entry - stop0
    stop = stop0; be_armed = False; be_next = False
    for i in range(ei_open, b1):
        if be_next:
            stop = max(stop, entry); be_next = False
        if o5[i] <= stop:
            return o5[i]
        if l5[i] <= stop:
            return stop
        if not be_armed and c5[i] >= entry + R:
            be_armed = True; be_next = True
    return c5[b1 - 1]


def ride_short(o5, h5, l5, c5, ei_open, b1, entry, stop0):
    R = stop0 - entry
    stop = stop0; be_armed = False; be_next = False
    for i in range(ei_open, b1):
        if be_next:
            stop = min(stop, entry); be_next = False
        if o5[i] >= stop:
            return o5[i]
        if h5[i] >= stop:
            return stop
        if not be_armed and c5[i] <= entry - R:
            be_armed = True; be_next = True
    return c5[b1 - 1]


def main():
    m5 = find_master("NQ", "5m", "rth", "db_noadj_rth")
    Rr = load_master_arrays(m5, date_to=DATE_TO)
    o5, h5, l5, c5, did5 = Rr["open"], Rr["high"], Rr["low"], Rr["close"], Rr["day_id"]
    idx5 = Rr["index"]; mins = (idx5.hour * 60 + idx5.minute).values
    sess = []; a = 0; n5 = len(c5)
    while a < n5:
        b = a
        while b < n5 and did5[b] == did5[a]:
            b += 1
        sess.append((a, b)); a = b
    do = np.array([o5[x] for x, y in sess]); dh = np.array([h5[x:y].max() for x, y in sess])
    dl = np.array([l5[x:y].min() for x, y in sess]); dc = np.array([c5[y - 1] for x, y in sess])
    nd = len(sess)
    sma200 = np.full(nd, np.nan)
    for d in range(199, nd):
        sma200[d] = dc[d - 199:d + 1].mean()
    k20 = 2 / 21; ema20 = np.full(nd, np.nan); ema20[19] = dc[:20].mean()
    for d in range(20, nd):
        ema20[d] = ema20[d - 1] + k20 * (dc[d] - ema20[d - 1])
    rsi2 = wilder_rsi(dc, 2)

    # ---------- A: PULLTRIG ----------
    for dip in ("ema20", "rsi2"):
        for kstop in (0.75, 1.0):
            pnl = []
            for t in range(210, nd - 1):
                if not dc[t] > sma200[t]:
                    continue
                if dip == "ema20" and not (dl[t] <= ema20[t] and dc[t - 1] > ema20[t - 1]):
                    continue
                if dip == "rsi2" and not rsi2[t] < 10:
                    continue
                a1, b1 = sess[t + 1]
                trig = dh[t]; ei = None
                for k in range(a1, b1 - 1):
                    if c5[k] > trig:
                        ei = k + 1; break
                if ei is None:
                    continue
                entry = o5[ei]
                stop0 = entry - kstop * max(entry - dl[t], 1e-9)
                ex = ride_long(o5, h5, l5, c5, ei, b1, entry, stop0)
                pnl.append((ex - entry) - RT)
            score(pnl, "A-PULLTRIG", f"{dip}/k{kstop}")
    print("A done", flush=True)

    # ---------- B: PMBRK ----------
    for kstop in (0.75, 1.0):
        pnl = []
        for d in range(210, nd):
            a1, b1 = sess[d]
            hi = None; lo = None; kk = None
            for k in range(a1, b1):
                if 720 <= mins[k] < 840:
                    hi = h5[k] if hi is None else max(hi, h5[k])
                    lo = l5[k] if lo is None else min(lo, l5[k])
                elif mins[k] >= 840:
                    kk = k; break
            if kk is None or hi is None or hi <= lo:
                continue
            rng = hi - lo
            for k in range(kk, b1 - 1):
                if c5[k] > hi:
                    entry = o5[k + 1]
                    ex = ride_long(o5, h5, l5, c5, k + 1, b1, entry, entry - kstop * rng)
                    pnl.append((ex - entry) - RT); break
                if c5[k] < lo:
                    entry = o5[k + 1]
                    ex = ride_short(o5, h5, l5, c5, k + 1, b1, entry, entry + kstop * rng)
                    pnl.append(-(ex - entry) - RT); break
        score(pnl, "B-PMBRK", f"k{kstop}")
    print("B done", flush=True)

    # ---------- C: ENGU-Q 5m ETH relocation ----------
    import importlib.util as _ilu
    _sp = _ilu.spec_from_file_location("eq5", os.path.join(ROOT, "augur_strategies", "ENGUQ_5M_1_0.py"))
    eq5 = _ilu.module_from_spec(_sp); _sp.loader.exec_module(eq5)
    P = {k: v["default"] for k, v in eq5.DEFAULT_PARAMS.items()}
    P.update({"tl_len": 34, "ema_len": 276, "atr_len": 21})
    try:
        r = run_backtest("ENGUQ_5M_1_0.py", instrument="NQ", timeframe="5m", session="eth",
                         source="db_noadj_eth", date_from="2010-06-07", date_to=DATE_TO,
                         params=P, cost_pts=0.783, return_trades=False)
    except Exception as e:
        print("C failed:", e); r = None
    if r:
        net = r["total_pnl"] * MULT; dd = -r["max_drawdown"] * MULT
        RESULTS.append(dict(fam="C-EQ5ETH", cell="scaled#226/5", n=r["num_trades"],
                            net=round(net), pf=round(r["profit_factor"], 3),
                            dd=round(dd), mar=round(net / dd, 2) if dd > 0 else 0, floor=300))
    print("C done", flush=True)

    print(f"\n{'fam':11}{'cell':14}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'MAR':>7}  gate")
    for r_ in RESULTS:
        g = "PASS" if (r_['pf'] >= 1.25 and r_['mar'] >= 8 and r_['n'] >= r_['floor']) else "fail"
        if r_["fam"] == "C-EQ5ETH" and g == "fail" and r_['pf'] >= 1.15 and r_['net'] > 0:
            g = "transfer-ok"
        print(f"{r_['fam']:11}{r_['cell']:14}{r_['n']:>6}{r_['net']:>11,}{r_['pf']:>7.3f}{r_['dd']:>10,}{r_['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r22_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r22_triage.csv")


if __name__ == "__main__":
    main()
