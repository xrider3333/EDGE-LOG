"""
ROUND 40 (2026-09-09) - is 2 minutes the RIGHT bar, and is the 2m edge a DIFFERENT edge?

Rounds 37/38 established: no new short-hold mechanism survives on NQ 1m, the NOISE band on
2-minute bars is the shorter side that pays, run #334 (full-space 2m Auto-Validate) PASSES,
and a $40-a-trade 2m scalp is cost-sensitive (one extra tick each way halves its MAR). Two
questions were left open and both decide whether any of this becomes a leg:

  A. IS 2 MINUTES THE OPTIMUM, or just the first bar that was searched? Round 5 walked the
     bar ladder on the #243 crown at the house cost only, and read it on money. This walks
     1 / 2 / 3 / 5 / 10 minutes at the house cost AND at one extra tick (0.783), for three
     configurations, and reads it on net-over-drawdown - the number that decides a leg.
  B. IS THE 2m EDGE A DIFFERENT EDGE from the 5m crown, or the same trades chopped finer?
     If the two trade the same days in the same direction, a 2m leg adds nothing the crown
     does not already own, and rounds 37/38 are a refinement of #243 rather than a candidate.

PRE-REGISTRATION (fixed before any cell ran)
  data     ONE source tape - the NQ 1m RTH master (db_noadj_rth) - resampled inside this file
           to 2 / 3 / 5 / 10 minutes, so no cell can differ because of how its master was
           built. GATE G1: the resampled 5m must reproduce the REGISTERED 5m master's own
           #243 read to within 1% on net and trade count, or nothing below is printed.
  window   2010-06-07 .. 2025-06-29 (selection). The NOISE lockbox is SPENT and is NOT opened
           by this file at all.
  costs    0.533 pts/RT ($10.66, the house number: ~2 ticks + commissions) and 0.783 ($15.66,
           one extra tick each way). Both printed for every cell; no cell is ranked on 0.533
           alone.
  configs  C1 = run #243's crown geometry (the paper leg, confirm 1, bands 0.75/1.5,
                bandwidth stop 1.75, all day)
           C2 = run #334's champion (the 2m validate's own pick: bands 0.5/1.0, VWAP exit,
                fixed stop 3.0, confirm 4, lookback 104, afternoon block)
           C3 = the cost-robust corner (round-38 search rank 8: band exit, ATR stop 0.75,
                confirm 3, afternoon block, lookback 74, bands 1.0/1.75, vol-skip 93)
  honesty  `confirm_bars` is BAR-counted, so its clock meaning changes with the bar size and
           a verbatim ladder is confounded by it (round-37 lesson). The knob caps at 4, so a
           clock-matched ladder is impossible for C1 (confirm 1 on 5m = 5 bars on 1m > 4).
           Every ladder row is therefore VERBATIM and says so; C1's 1m/2m rows carry the
           confound explicitly. `lookback` counts SESSIONS and travels cleanly (NOISE.md
           round 5), and every other knob is scale-free.
  bar      unchanged house bar: PF >= 1.25, MAR >= 8, n >= 300, >= 6 of 8 chronological
           slices, top-10 share < 90% with a positive ex-top-10 net, $/trade >= 2x the cost
           IN FORCE for that cell ($21.32 at 0.533, $31.32 at 0.783).

    python tools/r40_bar_ladder_overlap.py         -> tools/r37_results/r40_bar_ladder.csv
                                                      tools/r37_results/r40_overlap.txt
"""
import os, sys, csv, time
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_REPO)
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.data import find_master, load_master_arrays    # noqa: E402

MULT = 20.0
WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
COSTS = (0.533, 0.783)
OUT_CSV = os.path.join(HERE, "r37_results", "r40_bar_ladder.csv")
OUT_TXT = os.path.join(HERE, "r37_results", "r40_overlap.txt")

C1 = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
          window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
          confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=90.0)
C2 = dict(lookback=104, band_mult_long=0.5, band_mult_short=1.0, exit_mode="vwap", side="Both",
          window="afternoon_block", flat_eod=True, skip_holidays=True, stop_mode="fixed", stop_k=3.0,
          confirm_bars=4, daytype_mode="skip_bot_short", daytype_lo=0.3, daytype_hi=0.95, vol_skip_pct=96.0)
C3 = dict(lookback=74, band_mult_long=1.0, band_mult_short=1.75, exit_mode="band", side="Both",
          window="afternoon_block", flat_eod=False, skip_holidays=False, stop_mode="atr", stop_k=0.75,
          confirm_bars=3, daytype_mode="skip_bot_short", daytype_lo=0.1, daytype_hi=0.95, vol_skip_pct=93.0)
CONFIGS = (("C1 #243 crown", C1), ("C2 #334 champion", C2), ("C3 cost-robust corner", C3))
BARS = (1, 2, 3, 5, 10)
ROWS = []


def resample(A, k):
    """Aggregate the 1m arrays into k-minute buckets WITHIN each session (never across the
    session boundary), open=first, high=max, low=min, close=last, volume=sum. A session whose
    bar count is not a multiple of k keeps a short final bucket - the same thing a real k-minute
    feed does at 15:59."""
    if k == 1:
        return A
    did = np.asarray(A["day_id"]); n = len(did)
    o, h, l, c, v = A["open"], A["high"], A["low"], A["close"], A["volume"]
    idx = pd.DatetimeIndex(A["index"])
    starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
    ends = np.r_[starts[1:], n]
    O = []; H = []; L = []; C = []; V = []; D = []; I = []
    for a, b in zip(starts, ends):
        for s in range(a, b, k):
            e = min(s + k, b)
            O.append(o[s]); H.append(h[s:e].max()); L.append(l[s:e].min()); C.append(c[e - 1])
            V.append(v[s:e].sum() if v is not None else 0.0); D.append(did[s]); I.append(idx[s])
    return dict(open=np.array(O), high=np.array(H), low=np.array(L), close=np.array(C),
                volume=np.array(V), day_id=np.array(D), index=pd.DatetimeIndex(I))


def read(r, bar_min, cost):
    tr = sorted(r["trades"], key=lambda z: z[0])
    p = np.array([t[2] for t in tr]) * MULT
    if len(p) == 0:
        return None
    k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k else 0
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); w = float((p > 0).mean()); pf = float(r["profit_factor"])
    evr = (1 - w) * (pf - 1)
    srt = sorted(p, reverse=True); top = 100 * sum(srt[:10]) / net if net > 0 else 999
    ex = np.array(srt[10:]); exgw = ex[ex > 0].sum(); exgl = -ex[ex < 0].sum()
    hold = np.array([t[1] - t[0] for t in tr]) * bar_min
    per = net / len(p)
    mar = net / -dd if dd < 0 else 99
    ok = (pf >= 1.25 and mar >= 8 and len(p) >= 300 and folds >= 6 and top < 90
          and ex.sum() > 0 and per >= 2 * cost * MULT)
    return dict(n=len(p), net=round(net), pf=round(pf, 3), dd=round(-dd), mar=round(mar, 2),
                win=round(100 * w, 1), evr=round(evr, 3), ryr=round(evr * len(p) / 15.06, 1),
                folds8=folds, top10_pct=round(top), exnet=round(float(ex.sum())),
                expf=round(exgw / exgl, 3) if exgl > 0 else 99, per_trade=round(per, 2),
                hold_med=round(float(np.median(hold)), 1), hold_mean=round(float(hold.mean()), 1),
                PASS=int(ok))


def main():
    t0 = time.time()
    A1 = load_master_arrays(find_master("NQ", "1m", "rth", "db_noadj_rth"), **WIN)
    print("1m source tape: %d bars, %d sessions, loaded in %.1fs"
          % (len(A1["close"]), len(np.unique(A1["day_id"])), time.time() - t0), flush=True)
    tapes = {k: resample(A1, k) for k in BARS}
    for k in BARS:
        print("  %2dm -> %d bars" % (k, len(tapes[k]["close"])), flush=True)

    # ---- GATE G1: resampled 5m must reproduce the REGISTERED 5m master on C1 ----
    reg5 = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
    a = run_backtest("NOISE_1_0.py", arrays=reg5, params=C1, cost_pts=0.533, return_trades=True)
    b = run_backtest("NOISE_1_0.py", arrays=tapes[5], params=C1, cost_pts=0.533, return_trades=True)
    dn = abs(a["num_trades"] - b["num_trades"]) / a["num_trades"]
    dnet = abs(a["total_pnl"] - b["total_pnl"]) / abs(a["total_pnl"])
    print("\nG1 resampler parity on C1 @5m: registered n=%d net=$%s | resampled n=%d net=$%s "
          "| dn=%.2f%% dnet=%.2f%%  %s"
          % (a["num_trades"], format(round(a["total_pnl"] * MULT), ","), b["num_trades"],
             format(round(b["total_pnl"] * MULT), ","), 100 * dn, 100 * dnet,
             "PASS" if (dn <= 0.01 and dnet <= 0.01) else "*** FAIL ***"), flush=True)
    if dn > 0.01 or dnet > 0.01:
        sys.exit("G1 FAILED - the resampled tape does not reproduce the registered master; nothing printed.")

    # ---- PART A: the cost-robust bar ladder ----
    print("\nPART A - THE BAR LADDER, VERBATIM CONFIGS, AT TWO COSTS")
    print("%-22s %4s %6s | %5s %9s %6s %8s %6s %6s %2s %4s %7s %6s"
          % ("config", "bar", "cost$", "n", "net$", "PF", "DD$", "MAR", "R/YR", "f8", "top", "$/trd", "hold"))
    for label, P in CONFIGS:
        for k in BARS:
            for cost in COSTS:
                r = run_backtest("NOISE_1_0.py", arrays=tapes[k], params=P, cost_pts=cost, return_trades=True)
                m = read(r, k, cost) if r and r.get("trades") else None
                if m is None:
                    print("%-22s %3dm %6.2f | NO TRADES" % (label, k, cost * MULT)); continue
                m.update(config=label, bar_min=k, cost_pts=cost, cost_usd=round(cost * MULT, 2))
                ROWS.append(m)
                print("%-22s %3dm %6.2f | %5d %9s %6.3f %8s %6.2f %6.1f %2d %3d%% %7.1f %6.0f %s"
                      % (label, k, cost * MULT, m["n"], format(m["net"], ","), m["pf"],
                         format(m["dd"], ","), min(m["mar"], 99), m["ryr"], m["folds8"],
                         min(m["top10_pct"], 999), m["per_trade"], m["hold_med"],
                         "PASS" if m["PASS"] else ""), flush=True)
        print("", flush=True)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    keys = ["config", "bar_min", "cost_pts", "cost_usd"] + [k for k in ROWS[0] if k not in
                                                            ("config", "bar_min", "cost_pts", "cost_usd")]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(ROWS)

    # best bar per config on the STRESSED cost
    print("BEST BAR PER CONFIG, ranked on net-over-drawdown at $15.66 (the decision basis):")
    for label, _ in CONFIGS:
        cells = [r for r in ROWS if r["config"] == label and r["cost_pts"] == 0.783]
        cells.sort(key=lambda z: -z["mar"])
        print("  %-22s " % label + " > ".join("%dm(%.1f)" % (c["bar_min"], min(c["mar"], 99)) for c in cells))

    # ---- PART B: is the 2m edge a different edge? ----
    lines = []

    def daily(P, tape, k, cost=0.533):
        r = run_backtest("NOISE_1_0.py", arrays=tape, params=P, cost_pts=cost, return_trades=True)
        idx = pd.DatetimeIndex(tape["index"]); d = np.array([idx[t[0]].date() for t in r["trades"]])
        return pd.DataFrame({"day": d, "pnl": [t[2] * MULT for t in r["trades"]],
                             "side": [t[3] for t in r["trades"]]}), r

    def emit(s):
        print(s, flush=True); lines.append(s)

    emit("\nPART B - IS THE 2m EDGE A DIFFERENT EDGE FROM THE 5m CROWN?")
    pairs = [("#334 champion on 2m", C2, tapes[2], 2), ("#243 crown on 5m (the paper leg)", C1, tapes[5], 5),
             ("cost-robust corner on 2m", C3, tapes[2], 2)]
    frames = {}
    for name, P, tape, k in pairs:
        df, r = daily(P, tape, k)
        frames[name] = df
        emit("  %-34s n=%5d net=$%10s PF=%.3f DD=$%s"
             % (name, len(df), format(round(df.pnl.sum()), ","), r["profit_factor"],
                format(round(-r["max_drawdown"] * MULT), ",")))

    def compare(a_name, b_name):
        a = frames[a_name].groupby("day").pnl.sum(); b = frames[b_name].groupby("day").pnl.sum()
        both = a.index.intersection(b.index)
        sa = frames[a_name].groupby("day").side.first().reindex(both)
        sb = frames[b_name].groupby("day").side.first().reindex(both)
        # SORT_INDEX IS LOAD-BEARING: pd.concat on two date-object indexes returns the UNION
        # in an unsorted order, so a cumsum over it walks the calendar out of order and the
        # "drawdown" it reports is meaningless. Measured 2026-09-09: the C3-vs-crown pool read
        # DD $222,772 / n-per-DD 2.62 unsorted against $23,899 / 24.40 sorted - and a sum's
        # drawdown can never exceed the sum of its parts' ($31,522 here), which is what made
        # the bug visible. tools/gapgo_vs_orb_overlap.py carries the same pattern.
        al = pd.concat([a, b], axis=1).sort_index().fillna(0); al.columns = ["a", "b"]
        pooled = al.a + al.b
        assert al.index.is_monotonic_increasing, "pooled daily index is not in calendar order"
        cum = pooled.cumsum(); dd = float((cum - cum.cummax()).min()); net = float(pooled.sum())
        ca = a.cumsum(); da = float((ca - ca.cummax()).min())
        cb = b.cumsum(); db = float((cb - cb.cummax()).min())
        emit("\n  %s  vs  %s" % (a_name, b_name))
        emit("    shared trade days: %d of %d and %d (%.0f%% of the first)"
             % (len(both), len(a), len(b), 100 * len(both) / len(a)))
        emit("    same direction on shared days: %.0f%%" % (100 * float((sa == sb).mean())))
        emit("    daily-PnL correlation: %.3f all days, %.3f shared days only"
             % (al.a.corr(al.b), al.loc[both].a.corr(al.loc[both].b)))
        emit("    net earned on days the OTHER does not trade: $%s of $%s"
             % (format(round(float(a[~a.index.isin(both)].sum())), ","), format(round(float(a.sum())), ",")))
        emit("    pooled 1:1  net=$%s DD=$%s n/DD=%.2f   vs alone %.2f and %.2f"
             % (format(round(net), ","), format(round(-dd), ","), net / -dd if dd < 0 else 99,
                float(a.sum()) / -da if da < 0 else 99, float(b.sum()) / -db if db < 0 else 99))

    compare("#334 champion on 2m", "#243 crown on 5m (the paper leg)")
    compare("cost-robust corner on 2m", "#243 crown on 5m (the paper leg)")
    compare("cost-robust corner on 2m", "#334 champion on 2m")
    with open(OUT_TXT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n%d ladder cells, %d PASS, %.1f min -> %s + %s"
          % (len(ROWS), sum(r["PASS"] for r in ROWS), (time.time() - t0) / 60, OUT_CSV, OUT_TXT), flush=True)


if __name__ == "__main__":
    main()
