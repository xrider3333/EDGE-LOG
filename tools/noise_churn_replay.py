r"""NOISE churn r1 - replay of one live QQQ session through each cell (MANAGER #278). QQQ_1m.csv resampled to 5m RTH.
Knobs off must reproduce the live round trips before a cell count is read.

    python tools/noise_churn_replay.py 2026-11-04
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_churn_r1 as nc  # noqa: E402

QQQ1M = r"C:\EdgeLog\ohlc\QQQ_1m.csv"


def bars():
    b = pd.read_csv(QQQ1M).dropna(subset=["open", "high", "low", "close"])
    b["ts"] = pd.to_datetime(b.time, unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    b = b.set_index("ts").sort_index().between_time("09:30", "15:59")
    r = b.resample("5min", label="left", closed="left").agg(dict(open="first", high="max", low="min", close="last", volume="sum")).dropna()
    return r.between_time("09:30", "15:55")


def main(day):
    r = bars()
    r = r[r.index <= pd.Timestamp(day) + pd.Timedelta(days=1)].iloc[-78 * 140:]
    days = pd.factorize(r.index.normalize())[0]
    A = dict(open=r.open.values, high=r.high.values, low=r.low.values, close=r.close.values, volume=r.volume.values,
             day_id=days, index=r.index.values)
    s = nc.strat("NOISE_1_8_CT304_CHURN.py")
    for name, cell in nc.CELLS:
        res = s.run_backtest(A["open"], A["high"], A["low"], A["close"], volumes=A["volume"], day_id=A["day_id"], index=r.index, return_trades=True, **cell)
        tr = [t for t in res["trades"] if r.index[int(t[0])].normalize() == pd.Timestamp(day)]
        one = sum(int(t[1]) - int(t[0]) <= 1 for t in tr)
        print("%-9s round trips %2d  one bar %2d  sum raw $/sh %+.2f" % (name, len(tr), one, sum(float(t[2]) for t in tr)))
        if name == "HOLD":
            for t in tr:
                print("   ", r.index[int(t[0])], r.index[int(t[1])], "%+.2f" % float(t[2]), t[3:])


if __name__ == "__main__":
    main(sys.argv[1])
