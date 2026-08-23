"""
TTM SQUEEZE ROUND 3 — the DAILY chart, Carter's original habitat.

Rounds 1-2 (tools/ttmsqz_baselines.py, tools/ttmsqz_round2.py) were intraday: flat at every
close, 1m-60m bars. But Carter's book presents the squeeze on DAILY bars with multi-day
holds. This round tests exactly that:

  - Daily RTH bars built from the 5m masters (open of first bar, hi/lo, close of last).
  - Squeeze + momentum computed on daily bars (length 20 = 20 sessions).
  - Enter at the NEXT session's open after a fire (decision on day close - legal).
  - Hold across days. Protective stop = stop_atr x daily ATR, checked intrabar each day
    (gap-through pays the open). Exits: fade / zero on day close -> next open, or ride
    (stop only).
  - ROLL SEAMS: multi-day holds on a no-adjust continuous contract would pay the quarterly
    roll gap, so positions are force-flattened at the close of the day BEFORE each detected
    seam and no fill may occur that day - identical method + calibration to
    BBRSI_1_0/TTIBS_1_0.detect_roll_seams. A trade still open at data end is DROPPED.

Window pinned 2010-06-07..2026-06-30, LB = last 12 months, house costs, one contract.

Usage:  python tools/ttmsqz_round3_daily.py
Output: tools/data/ttmsqz_round3_daily.txt
"""
import os, sys, importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP = os.path.join(ROOT, "augur_uploads")
if not os.path.exists(os.path.join(UP, "NOADJ_NQ_5m_RTH.csv")):
    UP = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads"

DATE_FROM, LB_FROM, DATE_TO = "2010-06-07", "2025-07-01", "2026-06-30"
COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

def _mod(fn):
    sp = importlib.util.spec_from_file_location(fn, os.path.join(ROOT, "augur_strategies", fn + ".py"))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m

ttm = _mod("TTMSQZ_1_0")
bbrsi = _mod("BBRSI_1_0")            # for detect_roll_seams (house-calibrated)


def load_daily(inst):
    df = pd.read_csv(os.path.join(UP, f"NOADJ_{inst}_5m_RTH.csv"))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(DATE_FROM).date()) & (df["_dt"].dt.date <= pd.Timestamp(DATE_TO).date())]
    g = df.groupby(df["_dt"].dt.date, sort=True)
    d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                      "close": g["close"].last(), "ts": g["_dt"].first()})
    return d.reset_index(drop=True)


def run_daily(d, *, length=20, bb_mult=2.0, kc_mult=1.5, min_sq=1,
              exit_mode="fade", fade_bars=1, stop_atr=2.0, direction="both"):
    o, h, l, c = (d[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    ts = list(pd.DatetimeIndex(d["ts"]))
    sq_on, mom, atr = ttm.squeeze_indicators(h, l, c, length, bb_mult, kc_mult)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= min_sq)
    warm = length * 2 + 5
    fire[:warm] = False

    seams = set(bbrsi.detect_roll_seams(o, c, ts))
    force_exit = {s - 1 for s in seams if s - 1 >= 0}     # flat at close of seam eve

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both", "short")

    pos = 0; ep = 0.0; eb = -1; stop_px = None
    pending = None      # (side,) market at next open / ("exit",)
    fade_cnt = 0
    log = []

    def book(i, px, side, ep_, eb_):
        log.append((eb_, i, (px - ep_) if side > 0 else (ep_ - px), side, ep_, px))

    for u in range(warm, n):
        blocked = u in force_exit or u in seams
        if pending is not None:
            kind = pending[0]
            if not blocked:
                if kind == "exit":
                    if pos != 0:
                        book(u, o[u], pos, ep, eb); pos = 0; stop_px = None
                elif pos == 0:
                    pos = kind; ep = o[u]; eb = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = ep - pos * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
            pending = None
        if pos != 0 and u > eb and stop_px is not None and not blocked:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                book(u, px, pos, ep, eb); pos = 0; stop_px = None
        if u in force_exit:
            if pos != 0:
                book(u, c[u], pos, ep, eb); pos = 0; stop_px = None
            pending = None
            continue
        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue
        if pos != 0 and exit_mode in ("fade", "zero"):
            if exit_mode == "fade":
                fading = (m < m1) if pos > 0 else (m > m1)
                fade_cnt = fade_cnt + 1 if fading else 0
                if fade_cnt >= fade_bars:
                    pending = ("exit",)
                    continue
            elif (m <= 0) if pos > 0 else (m >= 0):
                pending = ("exit",)
                continue
        if pos == 0 and pending is None and fire[u] and m != 0:
            side = 1 if m > 0 else -1
            if (side > 0 and allow_long) or (side < 0 and allow_short):
                pending = (side,)
    # open trade at data end: DROPPED
    return log


def stats(log, d, inst):
    if not log:
        return None
    mult, cost = MULT[inst], COST[inst]
    t = pd.DataFrame(log, columns=["eb", "xb", "pnl", "side", "ep", "xp"])
    t["usd"] = (t["pnl"] - cost) * mult
    dts = pd.DatetimeIndex(d["ts"])
    t["date"] = dts[t["xb"].values].date; t["year"] = dts[t["xb"].values].year
    def block(x):
        if not len(x): return dict(net=0, pf=0, dd=0, n=0)
        v = x["usd"].values; cum = np.cumsum(v)
        dd = -float((cum - np.maximum.accumulate(cum)).min())
        gw = v[v > 0].sum(); gl = -v[v < 0].sum()
        return dict(net=float(v.sum()), pf=float(gw / gl) if gl > 0 else 99.0, dd=dd, n=len(v))
    lb = block(t[t["date"] >= pd.Timestamp(LB_FROM).date()])
    is_ = block(t[t["date"] < pd.Timestamp(LB_FROM).date()])
    yr = t.groupby("year")["usd"].sum()
    f = block(t); f.update(yplus=int((yr > 0).sum()), yminus=int((yr <= 0).sum()),
                           wr=float(100 * (t["usd"] > 0).mean()),
                           hold=float((t["xb"] - t["eb"]).mean()))
    return dict(full=f, IS=is_, LB=lb)


VARIANTS = [
    ("published daily (fade, 2 ATR)", {}),
    ("zero-cross exit",               dict(exit_mode="zero")),
    ("ride (stop only)",              dict(exit_mode="ride")),
    ("ride, wide 3 ATR stop",         dict(exit_mode="ride", stop_atr=3.0)),
    ("min 6-day squeeze",             dict(min_sq=6)),
    ("min 6-day + ride",              dict(min_sq=6, exit_mode="ride")),
    ("tight squeeze kc 2.0",          dict(kc_mult=2.0)),
    ("kc 2.0 + ride",                 dict(kc_mult=2.0, exit_mode="ride")),
    ("long only",                     dict(direction="long")),
    ("long only + ride",              dict(direction="long", exit_mode="ride")),
    ("short only",                    dict(direction="short")),
    ("faster length 14",              dict(length=14)),
]


def main():
    lines = []
    for inst in ("NQ", "ES"):
        d = load_daily(inst)
        hdr = f"\n== {inst} DAILY  sessions={len(d):,}"
        print(hdr, flush=True); lines.append(hdr)
        h2 = "%-30s %6s %5s %6s %6s %11s %9s %6s | %11s %6s | %11s %6s %5s" % (
            "variant", "trades", "WR%", "hold", "PF", "net $", "maxDD $", "MAR", "IS $", "IS PF", "LB $", "LB PF", "yrs+")
        print(h2); lines.append(h2)
        for label, kw in VARIANTS:
            s = stats(run_daily(d, **kw), d, inst)
            if s is None:
                row = "%-30s  NO TRADES" % label
            else:
                f = s["full"]; mar = f["net"] / f["dd"] if f["dd"] > 0 else 0
                row = "%-30s %6d %5.1f %6.1f %6.2f %11s %9s %6.2f | %11s %6.2f | %11s %6.2f %2d/%-2d" % (
                    label, f["n"], f["wr"], f["hold"], min(f["pf"], 99), f"{f['net']:,.0f}", f"{f['dd']:,.0f}",
                    mar, f"{s['IS']['net']:,.0f}", min(s["IS"]["pf"], 99),
                    f"{s['LB']['net']:,.0f}", min(s["LB"]["pf"], 99), f["yplus"], f["yminus"])
            print(row, flush=True); lines.append(row)
    out = os.path.join(ROOT, "tools", "data", "ttmsqz_round3_daily.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("TTM SQUEEZE ROUND 3 (daily swing, roll-seam guarded) - window %s..%s, LB from %s\n" % (DATE_FROM, DATE_TO, LB_FROM))
        fh.write("\n".join(lines) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
