"""
orb_feas.py -- Opening Range Breakout FEASIBILITY sweep (not a strategy yet).

Measure before building. Tests the core ORB idea on 16yr ES/NQ 5m RTH:
  * Opening range = high/low of the first K minutes of the RTH session.
  * After the range, the FIRST break of the range high (long) / low (short) enters.
  * Stop = opposite extreme of the opening range.
  * Exit = stop, or flat at the session's last bar (no overnight).
  * One position per day (first break only).

Modes:
  both        -- trade either break
  long        -- only the up-break
  first_dir   -- trade only in the direction of the opening-range candle
                 (range close vs range open)

Gross of costs (1 trade/day so costs are minor). 1 contract: ES x50, NQ x20.

Run:  python tools/orb_feas.py
"""
import os
import numpy as np
import pandas as pd

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS = os.path.join(ROOT, "augur_uploads")
MASTERS = {"ES": ("master_a85a0438.csv", 50), "NQ": ("master_00c66966.csv", 20)}


def load(fname):
    df = pd.read_csv(os.path.join(UPLOADS, fname))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = dt.dt.hour * 60 + dt.dt.minute
    df = df[(mins >= 570) & (mins < 960)].copy()          # RTH
    dt = dt[(mins >= 570) & (mins < 960)]
    df["date"] = dt.dt.date
    df["day_id"] = pd.factorize(df["date"])[0]
    return df.sort_values("time").reset_index(drop=True)


def sim(df, or_bars, mode, mult):
    """One pass over all sessions. Returns list of trade PnLs (points)."""
    o = df["open"].values; h = df["high"].values
    l = df["low"].values;  c = df["close"].values
    did = df["day_id"].values
    n = len(df)
    pnls = []
    i = 0
    while i < n:
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        # session is [i, j)
        s_o, s_h, s_l, s_c = o[i:j], h[i:j], l[i:j], c[i:j]
        m = j - i
        if m > or_bars + 1:
            or_hi = s_h[:or_bars].max()
            or_lo = s_l[:or_bars].min()
            or_dir = 1 if s_c[or_bars - 1] >= s_o[0] else -1
            pos = 0; entry = 0.0
            for k in range(or_bars, m):
                if pos == 0:
                    up = s_h[k] >= or_hi
                    dn = s_l[k] <= or_lo
                    take_long  = up and (mode in ("both", "long") or (mode == "first_dir" and or_dir > 0))
                    take_short = dn and (mode in ("both",)      or (mode == "first_dir" and or_dir < 0))
                    if take_long and (not dn or up):     # prefer the side actually broken
                        pos = 1; entry = max(or_hi, s_o[k]) if s_o[k] > or_hi else or_hi
                    elif take_short:
                        pos = -1; entry = min(or_lo, s_o[k]) if s_o[k] < or_lo else or_lo
                    if pos != 0:
                        continue
                else:
                    if pos > 0:
                        if s_l[k] <= or_lo:              # stop (pessimistic)
                            pnls.append(or_lo - entry); pos = 0; break
                    else:
                        if s_h[k] >= or_hi:
                            pnls.append(entry - or_hi); pos = 0; break
            if pos != 0:                                  # EOD flat at last close
                pnls.append((s_c[-1] - entry) if pos > 0 else (entry - s_c[-1]))
        i = j
    return np.array(pnls, dtype=float)


def report(inst, df, mult):
    print("=" * 70)
    print("  %s  --  %d sessions  ($%d/pt)   [ORB feasibility, EOD-flat, stop=opp extreme]" % (
        inst, df["day_id"].nunique(), mult))
    print("=" * 70)
    print("  %-10s %-10s %7s %6s %6s %12s %12s" % (
        "OR-len", "mode", "trades", "WR%", "PF", "net $", "avg $/trade"))
    for or_min, or_bars in [("15min", 3), ("30min", 6), ("60min", 12)]:
        for mode in ["both", "long", "first_dir"]:
            p = sim(df, or_bars, mode, mult)
            if len(p) == 0:
                continue
            usd = p * mult
            w = p[p > 0]; ls = p[p < 0]
            pf = w.sum() / -ls.sum() if ls.sum() < 0 else float("inf")
            print("  %-10s %-10s %7d %5.0f%% %6.2f %12s %12.1f" % (
                or_min, mode, len(p), 100 * (p > 0).mean(), min(pf, 99),
                "${:+,.0f}".format(usd.sum()), usd.mean()))
    print()


def main():
    for inst, (fname, mult) in MASTERS.items():
        df = load(fname)
        report(inst, df, mult)


if __name__ == "__main__":
    main()
