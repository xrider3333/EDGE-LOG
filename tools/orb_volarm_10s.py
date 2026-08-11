"""THE reconciliation test: can a live order capture ORB's edge fill + volume filter?

Volume accumulates monotonically during a bar. So a live system CAN do this, with no
look-ahead: watch the forming 5m breakout bar's volume-so-far, and the instant it
clears the gate (1.25 x mean of the session's prior 5m bar volumes -- fully known),
place the stop order at the range edge.

  - If the gate cleared BEFORE price touched the edge: the resting stop fills at the
    edge. IDENTICAL fill to the engine. No look-ahead anywhere.
  - If price touched the edge FIRST and volume confirmed later in the bar: the engine
    still counts that trade (it grades the finished bar), but live you can only enter
    AT MARKET the moment the gate clears -- a chased, worse fill ("V2").

This script measures, on REAL 10-second NQ data (C:\\EdgeLog\\ohlc\\NQ_10s.csv), what
fraction of engine trades fall in each bucket and what the chase costs:

  ENGINE : touch fill at edge, gate on finished bar (the backtest)
  V1     : only trades where the gate cleared before the touch (subset, same fills)
  V2     : all engine trades; edge fill when armed in time, else market at gate-clear

5m sessions are built from the same 10s rows, so engine and live see identical data.

Run:  python3.13.exe tools/orb_volarm_10s.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OR_BARS, STOP_FRAC, VOL_FILTER = 1, 0.75, 1.25
MULT, COST_PTS = 20.0, 0.533
SRC = r"C:\EdgeLog\ohlc\NQ_10s.csv"


def load_rth_10s():
    df = pd.read_csv(SRC, usecols=["time", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    tod = et.dt.hour * 60 + et.dt.minute
    m = (tod >= 9 * 60 + 30) & (tod < 16 * 60) & (et.dt.weekday < 5)
    df = df[m].reset_index(drop=True)
    df["date"] = et[m].dt.date.values
    df["bar5"] = (df["time"] // 300) * 300
    return df


def main():
    df = load_rth_10s()
    days = sorted(df["date"].unique())
    print(f"10s source: {SRC}")
    print(f"RTH sessions: {len(days)}  ({days[0]} -> {days[-1]})   10s rows: {len(df):,}")

    n_eng = 0
    armed_in_time = 0
    chased = 0
    eng_pnl, v1_pnl, v2_pnl = [], [], []
    chase_slip_pts = []
    rows = []

    for day in days:
        d = df[df["date"] == day]
        # 5m bars for this session, built from the 10s rows
        g = d.groupby("bar5", sort=True)
        b = pd.DataFrame({
            "t": list(g.groups.keys()),
            "o": g["open"].first().values, "h": g["high"].max().values,
            "l": g["low"].min().values, "c": g["close"].last().values,
            "v": g["volume"].sum().values,
        })
        m = len(b)
        if m <= OR_BARS + 1:
            continue
        or_hi = b["h"][:OR_BARS].max(); or_lo = b["l"][:OR_BARS].min()
        rng = or_hi - or_lo
        if rng <= 0:
            continue

        # engine: first touch bar whose FINISHED volume clears the gate
        for k in range(OR_BARS, m):
            up = b["h"][k] >= or_hi
            dn = b["l"][k] <= or_lo
            if not (up or dn):
                continue
            mv = b["v"][:k].mean()
            gate = VOL_FILTER * mv
            if not (mv > 0 and b["v"][k] >= gate):
                continue

            side = 1 if up else -1
            lvl = or_hi if up else or_lo
            entry_eng = (b["o"][k] if (up and b["o"][k] > lvl) or (dn and b["o"][k] < lvl)
                         else lvl)

            # intrabar sequencing from the 10s rows of bar k
            sub = d[d["bar5"] == b["t"][k]].reset_index(drop=True)
            cum = sub["volume"].cumsum().values
            i_vol = int(np.argmax(cum >= gate)) if (cum >= gate).any() else None
            if up:
                touch = (sub["high"].values >= lvl)
            else:
                touch = (sub["low"].values <= lvl)
            i_touch = int(np.argmax(touch)) if touch.any() else 0

            n_eng += 1
            if i_vol is not None and i_vol <= i_touch:
                armed_in_time += 1
                entry_v2 = entry_eng          # armed stop fills at the edge, like engine
                in_v1 = True
            else:
                chased += 1
                entry_v2 = float(sub["close"].iloc[i_vol])   # market at gate-clear
                chase_slip_pts.append(side * (entry_v2 - entry_eng))
                in_v1 = False

            # exits on the remaining 5m bars: stop at (own entry) -/+ 0.75*rng, else EOD
            def exit_pnl(entry):
                stop = entry - side * STOP_FRAC * rng
                for j in range(k + 1, m):
                    if side > 0 and b["l"][j] <= stop:
                        ex = b["o"][j] if b["o"][j] < stop else stop
                        return ex - entry
                    if side < 0 and b["h"][j] >= stop:
                        ex = b["o"][j] if b["o"][j] > stop else stop
                        return entry - ex
                return side * (b["c"][m - 1] - entry)

            pe = exit_pnl(entry_eng)
            pv = exit_pnl(entry_v2)
            eng_pnl.append(pe)
            v2_pnl.append(pv)
            if in_v1:
                v1_pnl.append(pv)
            rows.append((str(day), "L" if up else "S", round(entry_eng, 2),
                         round(entry_v2, 2), "armed" if in_v1 else "CHASED",
                         round(pe, 2), round(pv, 2)))
            break   # one trade per session

    eng_pnl = np.array(eng_pnl); v2_pnl = np.array(v2_pnl); v1_pnl = np.array(v1_pnl)

    print()
    print(f"{'date':<12}{'side':<5}{'engine fill':>12}{'live fill':>11}{'how':>8}"
          f"{'eng pts':>9}{'live pts':>9}")
    for r in rows:
        print(f"{r[0]:<12}{r[1]:<5}{r[2]:>12,.2f}{r[3]:>11,.2f}{r[4]:>8}{r[5]:>9.2f}{r[6]:>9.2f}")

    def usd(p):
        return float((p - COST_PTS).sum()) * MULT if len(p) else 0.0

    print()
    print(f"engine trades in window:        {n_eng}")
    print(f"  armed BEFORE touch (V1):      {armed_in_time}  "
          f"({100.0 * armed_in_time / max(n_eng, 1):.0f}%)  -> identical fill, no look-ahead")
    print(f"  volume confirmed AFTER touch: {chased}  "
          f"({100.0 * chased / max(n_eng, 1):.0f}%)  -> live must chase at market")
    if chase_slip_pts:
        s = np.array(chase_slip_pts)
        print(f"  chase slippage: mean {s.mean():+.2f} pts (${s.mean() * MULT:+,.0f}), "
              f"median {np.median(s):+.2f}, worst {s.max():+.2f} pts")
    print()
    print(f"window PnL  ENGINE: ${usd(eng_pnl):>10,.0f}")
    print(f"window PnL  V2    : ${usd(v2_pnl):>10,.0f}   (all engine trades, honest fills)")
    print(f"window PnL  V1    : ${usd(v1_pnl):>10,.0f}   ({len(v1_pnl)} trades, armed-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
