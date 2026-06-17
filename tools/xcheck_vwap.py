"""
xcheck_vwap.py -- Augur-side of the TradingView cross-check for VWAP_FADE_1.

Runs VWAP_FADE_1_0.py on a SHORT, RECENT window of the ES RTH master and dumps a
trade-by-trade blotter with US/Eastern timestamps + prices, so the same trades
can be eyeballed on a TradingView ES RTH 5m chart over the same dates.

Why the recent window: the 16yr master is a Panama back-adjusted continuous, so
OLD history is offset from real prices. The most-recent contract is pinned to
actual front-month prices, so a recent month ~= what TV's ES front month shows.

Config is deliberately simple + ZERO costs (match TV strategy commission=0):
  band 2.0, stop 2.5, warmup 6, Both, no cooldown, no max-hold, flat_eod on.

Run:  python tools/xcheck_vwap.py [N_DAYS]   (default 30 calendar days)
"""
import os, sys, importlib.util
import numpy as np
import pandas as pd

HERE    = os.path.dirname(os.path.abspath(__file__))
ROOT    = os.path.dirname(HERE)
STRATS  = os.path.join(ROOT, "augur_strategies")
UPLOADS = os.path.join(ROOT, "augur_uploads")

ES_MASTER = "master_a85a0438.csv"   # ES 5m RTH, Databento continuous
MULT      = 50

TRADE_MODE = os.environ.get("XC_DIR", "Both")
PARAMS = dict(band_mult=2.0, stop_mult=2.5, warmup_bars=6, max_hold=0,
              trade_mode=TRADE_MODE, bias_mode="off", cooldown_bars=0, flat_eod=True)


def _load(name):
    path = os.path.join(STRATS, name + ".py")
    spec = importlib.util.spec_from_file_location("_strat", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    n_days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    df = pd.read_csv(os.path.join(UPLOADS, ES_MASTER))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["dt"]     = dt
    df["datekey"] = dt.dt.date.astype(str)
    uniq = {d: i for i, d in enumerate(df["datekey"].unique())}
    df["day_id"] = df["datekey"].map(uniq).astype(int)
    df = df.sort_values("time").reset_index(drop=True)

    cutoff = df["dt"].iloc[-1] - pd.Timedelta(days=n_days)
    w = df[df["dt"] >= cutoff].reset_index(drop=True)

    print("=" * 70)
    print("  VWAP_FADE_1  TV cross-check  --  ES 5m RTH  (ZERO costs)")
    print("=" * 70)
    print("  window : %s  ->  %s" % (w["dt"].iloc[0], w["dt"].iloc[-1]))
    print("  bars   : %d   sessions: %d" % (len(w), w["day_id"].nunique()))
    print("  params : %s" % PARAMS)
    print("-" * 70)

    mod = _load("VWAP_FADE_1_0")
    r = mod.run_backtest(
        w["open"].values, w["high"].values, w["low"].values, w["close"].values,
        volumes=w["volume"].values, day_id=w["day_id"].values,
        return_trades=True, **PARAMS)

    if r is None:
        print("  No trades in this window. Try a longer N_DAYS, e.g. 90.")
        return

    print("  %-3s  %-17s  %-17s  %-5s  %8s  %8s  %10s" % (
        "#", "ENTRY (ET)", "EXIT (ET)", "DIR", "ENTRY", "EXIT", "PNL $"))
    for k, (be, bx, pnl) in enumerate(r["trades"], 1):
        ep = w["close"].iloc[be]
        # reconstruct direction from sign of pnl vs price move is ambiguous;
        # infer: entry below VWAP => long. Use close move vs exit price instead.
        xp = w["close"].iloc[bx]
        usd = pnl * MULT
        # direction: long if exit>entry implies +pnl; recover from pnl sign + prices
        dirn = "LONG" if (pnl > 0) == (xp >= ep) else "SHORT"
        print("  %-3d  %-17s  %-17s  %-5s  %8.2f  %8.2f  %+10.2f" % (
            k, str(w["dt"].iloc[be])[:16], str(w["dt"].iloc[bx])[:16],
            dirn, ep, xp, usd))

    print("-" * 70)
    print("  TRADES: %d   WIN%%: %.0f   PF: %.2f   NET $ (x%d): %s" % (
        r["num_trades"], r["win_rate"], r["profit_factor"], MULT,
        "${:+,.0f}".format(r["total_pnl"] * MULT)))
    print("=" * 70)
    print("  To cross-check: open ES (front month) 5m, RTH session only, in")
    print("  TradingView; add the VWAP FADE 1.0 strategy (pine/VWAP_FADE_1_0.pine)")
    print("  with the SAME inputs + commission 0; set the chart range to the")
    print("  window above. Compare trade count, direction, and PNL.")


if __name__ == "__main__":
    main()
