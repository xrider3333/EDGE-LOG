"""
ORB HUNT ROUND 7 (2026-09-05) - owner: "crown it and follow up by trying more varients of
it and beating it."

The base is the NEW crown, run #314 (ORB_3_6_R6): opening range 2 bars, first-candle
direction, close-confirmed, buffer 0.25, stop 2.5x the range, target 5.0R, breakeven 0.5R,
vol-regime filter 0.75, volume-pace gate 0.80.

PRE-REGISTERED GATE - written here BEFORE a single cell ran, and deliberately NOT the one
round 6 used. Round 6 ranked on EV R and R / YR; tools/orb_pick.py then showed EV R is
gameable across the breakeven knob (it sets the average loss, EV R's own denominator), and
several of the levers below move that knob. So this round ranks on ANNUALISED MAR, the
measure the crown was actually taken on, and a cell is adopt-worthy only if ALL FOUR hold:

    1. annualised MAR on the FULL window        >  #314's
    2. annualised MAR on the LAST 5 YEARS       >  #314's
    3. sliced lockbox net                       >= #314's
    4. worst rolling 12 months                  >= #314's

Both MAR legs are required on purpose: a cell that only wins on the full window is riding
2010-2016, and a cell that only wins on five years is riding a short sample. EV R and R / YR
are still PRINTED - the owner reads them - but they cannot make a cell adopt-worthy, and any
cell whose EV R rises while its average loss collapses is flagged as the artifact it is.

FOUR SWEEPS:
  A `stops`     wider stops and targets. The round-6 plateau check found net still climbing
                at stop 3.0 ($332,219 on a $22,583 drawdown), past the edge of what the
                validate searched - so this looks where nothing has looked.
  B `geometry`  opening-range length and breakout buffer RE-CHECKED under the new exit. Both
                were settled on the #234 exit; a wider stop and an earlier breakeven change
                what a good entry looks like, so the old answer does not automatically carry.
  C `runner`    trailing stop and partial exit, also re-checked under the new exit. Both were
                dead on the #234 base, but they were dead against a 5.5R ride with breakeven
                at 1.0R, which is a different trade.
  D `prevday`   THE UNEXPLOITED LEAD. ORB.md has flagged since 2026-08-18 that ORB's genuinely
                bad population is LONG entries after a prior-day close in the 0.6-0.8 band -
                252 trades averaging -$103 at a 0.79 profit factor - and that it was never
                pre-registered or exploited. ORB_3_8.py already carries the knob
                (daytype_mode='skip_band_long'). It was tested on the #234 exit and did not
                clear; this asks it again on the crown that actually trades.

    python tools/orb_hunt7.py [stops|geometry|runner|prevday|all]
"""
import os
import sys
import itertools

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END                      # noqa: E402
from tools.orb_hunt3 import robustness                                # noqa: E402

COST, MULT = 0.533, 20.0
FIVE_Y = "2021-08-13"
# masters live only in the primary checkout - a worktree has the DIRECTORY but not the
# file, so test for the FILE or a sweep run from a worktree dies on an empty folder.
MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
if not os.path.exists(MASTER):
    MASTER = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG",
                          "augur_uploads", "NOADJ_NQ_5m_RTH.csv")

# the crown, run #314
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
             partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
             breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
             atr_filter=0.75, vpace_filter=0.8)

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


def slice_stats(tr, start=None):
    if start:
        tr = [(d, v) for d, v in tr if d >= pd.Timestamp(start)]
    if len(tr) < 20:
        return None
    dts = [d for d, _ in tr]
    p = np.array([v for _, v in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    W, L = p[p > 0], p[p < 0]
    al = abs(L.mean()) if len(L) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    return dict(n=len(p), net=p.sum(), dd=dd, mar=(p.sum() / yrs) / dd if dd else np.nan,
                pf=W.sum() / abs(L.sum()) if len(L) else np.inf, evr=evr,
                ryr=evr * len(p) / yrs if yrs else np.nan, avgloss=al,
                scratch=int(((p > -50) & (p < 50)).sum()),
                worst=rob["worst"], win12=rob["win_pct"])


def measure(over, strategy="ORB_3_6.py"):
    b = bars()
    r = strat(strategy).run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **dict(CROWN, **over))
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    ie = pd.Timestamp(IS_END, tz=idx.tz)
    tr, lb = [], 0.0
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d > le:
            continue
        v = (t[2] - COST) * MULT
        tr.append((d.tz_localize(None), v))
        if d > ie:
            lb += v
    full = slice_stats(tr)
    five = slice_stats(tr, FIVE_Y)
    if not full or not five:
        return None
    return dict(full=full, five=five, lb=lb)


BASE = None


def gate(m):
    """The four pre-registered legs. Returns (legs dict, passes bool)."""
    legs = dict(mar_full=m["full"]["mar"] > BASE["full"]["mar"],
                mar_5y=m["five"]["mar"] > BASE["five"]["mar"],
                lockbox=m["lb"] >= BASE["lb"],
                worst=m["full"]["worst"] >= BASE["full"]["worst"])
    return legs, all(legs.values())


def artifact(m):
    """True when a rising EV R is bought by a collapsing average loss - the round-6 trap."""
    return (m["five"]["evr"] > BASE["five"]["evr"] * 1.10
            and m["five"]["avgloss"] < BASE["five"]["avgloss"] * 0.85)


HDR = ("%-34s %6s %10s %8s %6s %6s | %10s %8s %6s %6s %6s | %9s %9s %s"
       % ("config", "trd", "net$ 5y", "DD$ 5y", "MAR5", "EVR5", "net$ full", "DD$ full",
          "MARf", "EVRf", "R/YRf", "lockbox", "worst12", "gate"))


def line(label, m, flag=""):
    f, v = m["full"], m["five"]
    print("%-34s %6d %10s %8s %6.2f %6.3f | %10s %8s %6.2f %6.3f %6.1f | %9s %9s %s"
          % (label[:34], f["n"], f"{v['net']:,.0f}", f"{v['dd']:,.0f}", v["mar"], v["evr"],
             f"{f['net']:,.0f}", f"{f['dd']:,.0f}", f["mar"], f["evr"], f["ryr"],
             f"{m['lb']:,.0f}", f"{f['worst']:,.0f}", flag))


def sweep(name, cells, strategy="ORB_3_6.py"):
    print("\n" + "=" * 150)
    print("%s   (%d cells)" % (name, len(cells)))
    print("=" * 150)
    print(HDR)
    print("-" * 150)
    line("BASE crown #314", BASE, "<- the bar")
    print("-" * 150)
    hits = []
    for label, over in cells:
        try:
            m = measure(over, strategy)
        except Exception as e:
            print("%-34s ERROR %s: %s" % (label[:34], type(e).__name__, e))
            continue
        if not m:
            continue
        legs, ok = gate(m)
        tag = "".join(k[0].upper() if v else "." for k, v in legs.items())
        if ok:
            tag += "  <== CLEARS ALL FOUR"
        if artifact(m):
            tag += "  [EV R artifact: avg loss collapsed]"
        line(label, m, tag)
        if ok:
            hits.append((label, over, m))
    print("-" * 150)
    print("cleared the gate: %d of %d" % (len(hits), len(cells)))
    for label, over, m in hits:
        print("   %-32s %s" % (label, over))
    return hits


def cells_stops():
    out = []
    for sf, tr in itertools.product([2.5, 2.75, 3.0, 3.25, 3.5, 4.0],
                                    [4.5, 5.0, 5.5, 6.5, 8.0, 0.0]):
        out.append(("stop %.2f target %.1f" % (sf, tr), dict(stop_frac=sf, target_R=tr)))
    return out


def cells_geometry():
    out = []
    for ob, buf in itertools.product([1, 2, 3, 4], [0.15, 0.20, 0.25, 0.30, 0.35, 0.45]):
        out.append(("or %d buf %.2f" % (ob, buf), dict(or_bars=ob, breakout_buf=buf)))
    return out


def cells_runner():
    out = []
    for tb in [0, 3, 5, 8, 12]:
        for pe in [0.0, 2.0, 3.0, 4.0]:
            out.append(("trail %d partial %.1f" % (tb, pe),
                        dict(trail_bars=tb, partial_exit_R=pe)))
    return out


def cells_prevday():
    """The unexploited lead: skip LONG entries after a prior-day close in a middling band.
    ORB_3_8 carries the knob; every other setting is the crown's."""
    out = [("prevday OFF (crown)", dict(daytype_mode="off"))]
    for lo, hi in [(0.50, 0.75), (0.55, 0.80), (0.60, 0.80), (0.60, 0.85), (0.65, 0.85),
                   (0.55, 0.75), (0.40, 0.75), (0.60, 0.90)]:
        for mode in ("skip_band_long", "skip_band_all"):
            out.append(("%s %.2f-%.2f" % (mode.replace("skip_band_", ""), lo, hi),
                        dict(daytype_mode=mode, daytype_band_lo=lo, daytype_band_hi=hi)))
    return out


SWEEPS = {"stops": (cells_stops, "ORB_3_6.py"), "geometry": (cells_geometry, "ORB_3_6.py"),
          "runner": (cells_runner, "ORB_3_6.py"), "prevday": (cells_prevday, "ORB_3_8.py")}


def main():
    global BASE
    BASE = measure({})
    print("ORB ROUND 7 - beating the new crown, run #314")
    print("  base: %s" % CROWN)
    print("  gate (pre-registered): MAR(full) > %.3f AND MAR(5y) > %.3f AND lockbox >= $%s "
          "AND worst12 >= $%s"
          % (BASE["full"]["mar"], BASE["five"]["mar"], f"{BASE['lb']:,.0f}",
             f"{BASE['full']['worst']:,.0f}"))
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    todo = list(SWEEPS) if what == "all" else [what]
    total = []
    for s in todo:
        fn, strategy = SWEEPS[s]
        total += sweep(s.upper(), fn(), strategy)
    print("\n" + "=" * 150)
    print("ROUND 7: %d cell(s) cleared all four legs." % len(total))
    for label, over, m in total:
        print("   %-32s %s" % (label, over))
    print("=" * 150)


if __name__ == "__main__":
    main()
