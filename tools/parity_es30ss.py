"""
Parity check: does augur_strategies/TTMSQZ_3_0_ES30SS.py actually reproduce the round-12b
scan's STRUCTURAL STOP finding (tools/ttmsqz_r12b_entry_exit.py, buffer 0.00 row) — the only
thing in that scan that cleared the family's bar (whole-run PF AND lockbox net both >= the
incumbent)?

A scan can be wrong in ways a strategy file cannot hide (this exact study once reported a
pre-session filter that turned out to read the close of the day being traded — look-ahead —
and the strategy file is what caught it). This script is the check, not a formality: it does
NOT tune the file to agree with the scan, and a disagreement is printed loudly, not massaged.

TWO comparisons, because the file layers the round-8 deep-squeeze SIZE TILT on top of the
structural stop (the same tilt TTMSQZ_3_0_ES30T.py carries), which the round-12b scan never
tested:
  1. MECHANISM PARITY — the file's own trade loop (_build_arrays + _simulate), size 1
     throughout, no tilt, scored exactly the way the scan scored it. This is the actual
     reproduction check against the scan's buffer-0.00 row.
  2. FILE AS SHIPPED — run_backtest() at the crowned cell, tilt included, for the record.
     This is EXPECTED to differ from the scan (the tilt sizes roughly half the trades at
     1.5x) — that is not a disagreement, it is a separately-validated addition (round 8),
     reported here so the shipped number is visible next to the raw mechanism.

Also reports, straight from the file's own realized trades (not the scan's aggregate over
all eligible fires): the average and worst per-contract stop distance in dollars, and how
the worst single trade compares against the incumbent's own worst single trade (both run
size-1, cost-adjusted, same window).

SCAN ONLY: this reproduces existing numbers, it crowns nothing, queues no validate, and
commits nothing.

Usage:  python tools/parity_es30ss.py
"""
import os, sys, importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6_parity_ss")
ss = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS.py"), "ss_parity")
t3 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "t3_parity_ss")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
INST = "ES"

# The crowned cell (round 8 / ES30T's own default cell).
CELL = dict(kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20)

# Full incumbent config (ATR stop), exactly the scan's CROWN dict, for the direct engine run.
CROWN_FULL = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
                   exit_mode="fade", fade_bars=1, stop_atr=1.5, eod_cutoff=1, gate_tf_min=60,
                   gate_mode="sq_on", gate_len=20, gate_bars=0, gate_ratio=1.0, gate_fired_k=3,
                   direction="both")

HDR = "  %-42s %5s %7s %11s %9s | %11s %7s"


def score_pts_trades(trade_log, df):
    """Score a raw (points, no cost baked in) trade list the way the scan scored it:
    subtract COST once per trade, multiply by MULT, split lockbox by exit date."""
    if not trade_log:
        return None, None
    pnl = np.array([t[2] for t in trade_log], float)
    xb = np.array([t[1] for t in trade_log], int)
    usd = (pnl - COST[INST]) * MULT[INST]
    dates = pd.DatetimeIndex(df["_dt"])[xb].date
    s = r6.score(usd, dates)
    lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
    sl = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
    return s, sl


def row(name, s, sl):
    if s is None:
        return "  %-42s  no trades" % name
    lb_net = "{:,.0f}".format(sl["net"]) if sl else "n/a"
    lb_pf = "%.2f" % min(sl["pf"], 99) if sl else "n/a"
    return HDR % (name, s["n"], "%.2f" % min(s["pf"], 99), "{:,.0f}".format(s["net"]),
                  "{:,.0f}".format(s["dd"]), lb_net, lb_pf)


def main():
    df = r6.load(INST, "30m", "RTH")
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float);  c = df["close"].values.astype(float)
    day_id = df["day_id"].values
    index = df["_dt"]

    # ---- 1. mechanism parity: the file's own raw structural-stop trades, size 1, no tilt ----
    A = ss._build_arrays(o, h, l, c, day_id, index, CELL["kc_mult"], CELL["gate_len"])
    raw_trades = ss._simulate(o, h, l, c, A["n"], A["warm"], A["mom"], A["atr"], A["fire"],
                              A["rng_hi"], A["rng_lo"], A["gate_long"], A["gate_short"],
                              A["last_bar"], ss._FROZEN["fade_bars"], CELL["eod_cutoff"],
                              ss._STRUCT_BUF, ss._FROZEN["direction"])
    s_raw, sl_raw = score_pts_trades(raw_trades, df)

    # ---- 2. file as shipped: run_backtest() at the crowned cell, tilt included ----
    res = ss.run_backtest(o, h, l, c, day_id=day_id, index=index, return_trades=True, **CELL)
    s_file, sl_file = (None, None)
    file_trades = res["trades"] if res else []
    if res is not None:
        # res["trades"] pnl is already s*raw - (s-1)*cost, still in POINTS; the caller's
        # single downstream COST subtraction still applies once per trade on top of that,
        # same contract as ES30T.
        s_file, sl_file = score_pts_trades(file_trades, df)

    # ---- incumbent, run through the real engine directly (for the worst-trade comparison) ----
    inc_res = t3.run_backtest(o, h, l, c, day_id=day_id, index=index, return_trades=True,
                              **CROWN_FULL)
    inc_trades = inc_res["trades"] if inc_res else []

    print("TTMSQZ_3_0_ES30SS parity check   %s" % pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
    print("ES 30m RTH, window %s..%s, lockbox from %s, house cost %.3f pts, mult %d, 1 contract"
          % (DATE_FROM, DATE_TO, LB_FROM, COST[INST], MULT[INST]))
    print()
    print(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF"))
    print(row("incumbent (ATR 1.5x stop, engine quoted)", dict(n=359, pf=2.12, net=51709, dd=3740),
              dict(net=4992, pf=2.22)))
    print(row("incumbent (ATR 1.5x stop, engine re-run here)",
              *score_pts_trades(inc_trades, df)))
    print(row("scan: structural stop, buf 0.00 (quoted)", dict(n=357, pf=2.70, net=73720, dd=3642),
              dict(net=11710, pf=5.38)))
    print(row("FILE mechanism-only (no tilt, size 1)", s_raw, sl_raw))
    print(row("FILE as shipped (with 1.5x deep-squeeze tilt)", s_file, sl_file))
    print()

    ok = (s_raw is not None and sl_raw is not None and
          s_raw["n"] == 357 and abs(s_raw["net"] - 73720) < 300 and
          abs(s_raw["dd"] - 3642) < 300 and abs(sl_raw["net"] - 11710) < 300 and
          abs(sl_raw["pf"] - 5.38) < 0.15)
    if ok:
        print("PARITY OK — the file's structural-stop mechanism (no tilt) reproduces the scan's")
        print("buffer-0.00 row within a few hundred dollars. The tilt-included 'as shipped' row")
        print("above is EXPECTED to differ from the scan (the scan never tested the tilt).")
    else:
        print("PARITY FAILED — the file's structural-stop mechanism does NOT reproduce the scan")
        print("within tolerance. This is a RESULT, not a bug to tune away — do not trust the file")
        print("or the scan finding until the disagreement is understood. See the rows above.")

    # ---- stop-distance report, computed straight from the file's own realized trades ----
    print()
    if raw_trades:
        dists = []
        for t in raw_trades:
            eb, xb, pnl, sd, ep, xp = t
            fb = eb - 1  # the fire/decision bar the range was measured on
            rh, rl = A["rng_hi"][fb], A["rng_lo"][fb]
            d = (ep - rl) if sd > 0 else (rh - ep)
            dists.append(d * MULT[INST])
        dists = np.array(dists)
        print("structural stop distance, %d realized trades (this file, no tilt): avg $%s, worst $%s per contract"
              % (len(dists), "{:,.0f}".format(dists.mean()), "{:,.0f}".format(dists.max())))
    else:
        dists = np.array([])
        print("structural stop distance: no trades to measure")
    print("scan's own caveat (all 360 eligible fires, not just realized trades): mean $586 (ATR) vs $1,033 (range-edge), 76% wider")

    print()
    if raw_trades:
        worst_file_pts = min(t[2] for t in raw_trades)
        worst_file_usd = (worst_file_pts - COST[INST]) * MULT[INST]
    else:
        worst_file_usd = None
    if inc_trades:
        worst_inc_pts = min(t[2] for t in inc_trades)
        worst_inc_usd = (worst_inc_pts - COST[INST]) * MULT[INST]
    else:
        worst_inc_usd = None
    print("worst single trade, size 1, cost-adjusted:")
    print("  incumbent (ATR 1.5x stop):     $%s" % ("{:,.0f}".format(worst_inc_usd) if worst_inc_usd is not None else "n/a"))
    print("  this file (structural stop):   $%s" % ("{:,.0f}".format(worst_file_usd) if worst_file_usd is not None else "n/a"))
    if worst_inc_usd is not None and worst_file_usd is not None and worst_inc_usd != 0:
        print("  file's worst trade is %.0f%% of the incumbent's worst trade"
              % (100.0 * worst_file_usd / worst_inc_usd))


if __name__ == "__main__":
    main()
