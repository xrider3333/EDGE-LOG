"""Round 16b - is the top rung of the SIZE LADDER real, or an accident of stacking two wrappers?

Two size tilts were validated SEPARATELY on the book leg (TTMSQZ_3_0_ES30SS20.py, structural
stop, gate_len 20): 1.5x on trades entered while the hourly compression ratio is at or under
0.85 (run #340, the deep-squeeze tilt, TTMSQZ_3_0_ES30T.py / _ES30SS.py) and 1.5x on trades that
fill on the session's first available bar (run #368, the open-bar tilt, TTMSQZ_3_0_ES30SSO.py).
The combined leg the paper book carries (run #369, TTMSQZ_3_0_ES30SSOF2.py) stacks BOTH, and the
two conditions are independent, so a trade that qualifies for both gets 1.5 x 1.5 = 2.25
contracts. Nobody ever validated that corner directly - it fell out of composing two wrappers
that were each validated alone.

THIS ROUND asks whether the 2.25 rung earns its keep, on the combined leg's own trades:
  (a) the census - how many trades sit in each of the four buckets (neither / deep only / open
      only / both), and what each bucket earns, in discovery, holdout and lockbox.
  (b) the ladder as it stands - 1.0 / 1.5 / 1.5 / 2.25 (multiplicative, the incumbent)
  (c) capped at 1.5 - either rule -> 1.5, never 2.25
  (d) capped at 2.0
  (e) additive-to-2.0 with a floor - printed only if it differs from (d) on this data
  (f) flat 1.5x on every trade - the leverage control: more size is always more money, so this
      row is what stops the others from fooling anyone
  (g) no tilt at all - the untilted structural-stop leg

METHOD. The leg's trades are pulled ONCE from the engine (TTMSQZ_3_0_ES30SSOF2.run_backtest,
kc_mult 1.5, eod_cutoff 1 - run #299's own cell). Re-weighting is pure numpy from there: tilting
never touches a trade's entry/exit price, only its pnl, so the RAW (1-contract, untilted) points
move is recovered directly from entry_px/exit_px/side - no algebra on the priced pnl, no re-run.
The two tilt flags (deep-squeeze at the decision bar, open-bar at the fill bar) are recomputed
from the same helper functions the engine itself calls, so a trade's bucket membership is not
guessed either.

DISCIPLINE. Window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES 0.363 pts a round trip,
$50 a point, 16.06 years for the whole-run figures. Both multipliers and the 0.85 threshold are
fixed a priori in this family; they are read from the strategy files, never tuned here. Discovery
= the first 60 percent of pre-lockbox trades by time, holdout = the rest - same split the round-
15 templates use. A MANDATORY parity gate reproduces run #369's published whole-run figures
before anything else is trusted; a per-trade internal-consistency check confirms the recovered
bucket flags and raw points reconstruct the engine's own priced pnl exactly.

Log: tools/data/ttmsqz_r16b_tilt_ladder.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
r8 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r8", os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py")))
r8.__spec__.loader.exec_module(r8)
r6 = r8.r6
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r16b_tilt_ladder.txt")
COST, MULT, YRS = r6.COST["ES"], r6.MULT["ES"], 16.06

# The published parity target for run #369 (TTMSQZ_3_0_ES30SSOF2.py docstring), whole run.
PARITY = dict(n=354, net=135884.0, pf=3.12, mar=1.826, lb_net=22739.0, lb_pf=9.89)


def leg_trades():
    """The combined leg's own trades (run #369's cell), with both tilt flags and the raw
    (1-contract, untilted) points move recovered directly - never backed out by algebra on the
    priced pnl, because tilting rescales pnl but never touches the fill prices."""
    m = r6._mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2.py"), "ssof2_r16b")
    df = r6.load("ES", "30m", "RTH")
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                       day_id=df["day_id"].values, index=df["_dt"], return_trades=True,
                       kc_mult=1.5, eod_cutoff=1)
    tr = r["trades"]
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2]), int(x[3]), float(x[4]), float(x[5]))
                      for x in tr], columns=["eb", "xb", "pnl_tilted", "side", "epx", "xpx"])
    t["raw"] = np.where(t["side"] > 0, t["xpx"] - t["epx"], t["epx"] - t["xpx"])

    ss = m._so._ss   # the TTMSQZ_3_0_ES30SS instance this leg actually ran its stop/gate/tilt on
    deep = ss._deep_state(df["high"].values, df["low"].values, df["close"].values,
                          df["day_id"].values, df["_dt"])
    nn = len(deep)
    eb = t["eb"].values
    t["deep"] = deep[np.clip(eb - 1, 0, nn - 1)]
    ordinal = m._so._session_ordinal(df["day_id"].values)
    t["open_bar"] = ordinal[eb] == m._so._OPEN_ORDINAL
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()

    # internal-consistency check: does the multiplicative ladder built from the recomputed flags
    # and the recovered raw points reproduce the engine's own priced pnl, to the cent?
    deep_mult, open_mult = float(ss._TILT_MULT), float(m._so._OPEN_MULT)
    s_expect = np.where(t["deep"], deep_mult, 1.0) * np.where(t["open_bar"], open_mult, 1.0)
    pnl_check = s_expect * t["raw"].values - (s_expect - 1.0) * COST
    ok = np.allclose(pnl_check, t["pnl_tilted"].values, atol=1e-6)
    return t, ok, deep_mult, open_mult, float(ss._DEEP_THR)


def stats(usd, w, dates=None):
    if not len(usd):
        return dict(n=0, pf=float("nan"), net=0.0, dd=0.0, mar=float("nan"), per_ctr=float("nan"))
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    net = float(usd.sum())
    pf = (gw / gl) if gl > 0 else 99.0
    if dates is not None and len(dates):
        yrs = max((pd.Timestamp(dates.max()) - pd.Timestamp(dates.min())).days / 365.25, 1e-9)
    else:
        yrs = YRS
    mar = (net / yrs) / dd if dd > 0 else float("nan")
    ctr = float(w.sum())
    per_ctr = net / ctr if ctr > 0 else float("nan")
    return dict(n=len(usd), pf=pf, net=net, dd=dd, mar=mar, per_ctr=per_ctr, yrs=yrs, ctr=ctr)


def fmt_row(name, d, h, l):
    return ("  %-46s %4d %6s %10s %8s %6s %7s   %4d %6s %10s %8s %6s %7s   %4d %6s %10s %8s %6s %7s"
            % (name, d["n"], "%.2f" % min(d["pf"], 99), "{:,.0f}".format(d["net"]),
               "{:,.0f}".format(d["dd"]), "%.2f" % d["mar"], "{:,.0f}".format(d["per_ctr"]),
               h["n"], "%.2f" % min(h["pf"], 99), "{:,.0f}".format(h["net"]),
               "{:,.0f}".format(h["dd"]), "%.2f" % h["mar"], "{:,.0f}".format(h["per_ctr"]),
               l["n"], "%.2f" % min(l["pf"], 99), "{:,.0f}".format(l["net"]),
               "{:,.0f}".format(l["dd"]), "%.2f" % l["mar"], "{:,.0f}".format(l["per_ctr"])))


def main():
    L = ["TTM SQUEEZE r16b - the top rung of the SIZE LADDER: real, or an accident of stacking?   %s"
         % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; combined leg TTMSQZ_3_0_ES30SSOF2 on ES 30m RTH, cell "
         "kc_mult=1.5 eod_cutoff=1 (run #299's own cell), 0.363 pts a round trip, $50 a point"
         % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM),
         "Trades pulled ONCE from the engine; every variant below is a numpy re-weighting of the same trade list.",
         "Discovery = first 60%% of pre-lockbox trades by time, holdout = the rest. Multipliers and the 0.85",
         "threshold are read from the strategy files, fixed a priori, never tuned here. Nothing is crowned."]
    print("\n".join(L), flush=True)

    t, ok, deep_mult, open_mult, deep_thr = leg_trades()
    L.append("")
    L.append("  internal-consistency check (recomputed flags + recovered raw points reproduce the engine's own "
             "priced pnl to the cent): %s" % ("PASS" if ok else "FAIL -- DO NOT TRUST ANYTHING BELOW"))
    print(L[-1], flush=True)
    if not ok:
        r8._lines_to(L, LOG)
        print("log ->", LOG)
        return

    usd = t["raw"].values  # placeholder name; real pricing happens per-variant below
    raw = t["raw"].values
    deep = t["deep"].values
    openb = t["open_bar"].values
    both = deep & openb
    deep_only = deep & ~openb
    open_only = openb & ~deep
    neither = ~deep & ~openb

    def price(w):
        return w * (raw - COST) * MULT

    w_incumbent = np.where(deep, deep_mult, 1.0) * np.where(openb, open_mult, 1.0)
    usd_incumbent = price(w_incumbent)

    # ---- MANDATORY PARITY GATE, whole population, before anything else is trusted ----
    s_all = stats(usd_incumbent, w_incumbent)
    lb_mask = (t["date"] >= pd.Timestamp(r6.LB_FROM)).values
    s_lb = stats(usd_incumbent[lb_mask], w_incumbent[lb_mask])
    parity_ok = (s_all["n"] == PARITY["n"] and abs(s_all["net"] - PARITY["net"]) < 1.0
                and abs(s_all["pf"] - PARITY["pf"]) < 0.01
                and abs((s_all["net"] / YRS / s_all["dd"]) - PARITY["mar"]) < 0.01
                and abs(s_lb["net"] - PARITY["lb_net"]) < 1.0 and abs(min(s_lb["pf"], 99) - PARITY["lb_pf"]) < 0.02)
    mar_wholerun = (s_all["net"] / YRS) / s_all["dd"] if s_all["dd"] > 0 else float("nan")
    L.append("")
    L.append("  PARITY GATE vs run #369 (published): target n=%d net=$%s PF=%.2f MAR=%.3f | LB net=$%s LB PF=%.2f"
             % (PARITY["n"], "{:,.0f}".format(PARITY["net"]), PARITY["pf"], PARITY["mar"],
                "{:,.0f}".format(PARITY["lb_net"]), PARITY["lb_pf"]))
    L.append("  PARITY GATE measured:               n=%d net=$%s PF=%.2f MAR=%.3f | LB net=$%s LB PF=%.2f   %s"
             % (s_all["n"], "{:,.0f}".format(s_all["net"]), min(s_all["pf"], 99), mar_wholerun,
                "{:,.0f}".format(s_lb["net"]), min(s_lb["pf"], 99), "PASS" if parity_ok else "FAIL"))
    print("\n".join(L[-3:]), flush=True)
    if not parity_ok:
        L.append("  PARITY FAILED - the harness does not reproduce run #369. Nothing below this line is trustworthy.")
        print(L[-1], flush=True)
        r8._lines_to(L, LOG)
        print("log ->", LOG)
        return

    # ---- split: discovery / holdout / lockbox ----
    pre = np.flatnonzero(~lb_mask)
    cut = pre[int(len(pre) * 0.6)]
    disc = np.zeros(len(t), bool); disc[pre[pre < cut]] = True
    hold = np.zeros(len(t), bool); hold[pre[pre >= cut]] = True
    lb = lb_mask
    L.append("")
    L.append("  %d trades total. discovery %d, holdout %d, lockbox %d." % (len(t), disc.sum(), hold.sum(), lb.sum()))
    print(L[-1], flush=True)

    # ================= (a) THE CENSUS =================
    L.append("")
    L.append("=" * 100)
    L.append("(a) THE CENSUS - how many trades sit in each bucket, and what each bucket earns per contract,")
    L.append("    at the weight the INCUMBENT ladder actually puts on it (1.0 / 1.5 / 1.5 / 2.25).")
    L.append("=" * 100)
    buckets = [("neither tilt", neither, 1.0), ("deep-squeeze only", deep_only, 1.5),
               ("open-bar only", open_only, 1.5), ("BOTH (the top rung)", both, 2.25)]
    HC = "  %-22s %-10s %5s %5s %5s | %10s %10s %10s | %8s %8s %8s"
    L.append(HC % ("bucket", "weight", "disc", "hold", "lb", "net disc", "net hold", "net lb",
                   "$/ctr d", "$/ctr h", "$/ctr l"))
    print(L[-1], flush=True)
    census = {}
    for name, msk, w in buckets:
        row = {}
        cells = []
        for slice_name, smsk in (("disc", disc), ("hold", hold), ("lb", lb)):
            m2 = msk & smsk
            n = int(m2.sum())
            net = float(usd_incumbent[m2].sum())
            per_ctr = net / (n * w) if n > 0 else float("nan")
            row[slice_name] = dict(n=n, net=net, per_ctr=per_ctr)
        census[name] = row
        L.append(HC % (name, "%.2fx" % w, row["disc"]["n"], row["hold"]["n"], row["lb"]["n"],
                       "{:,.0f}".format(row["disc"]["net"]), "{:,.0f}".format(row["hold"]["net"]),
                       "{:,.0f}".format(row["lb"]["net"]),
                       "{:,.0f}".format(row["disc"]["per_ctr"]) if row["disc"]["n"] else "-",
                       "{:,.0f}".format(row["hold"]["per_ctr"]) if row["hold"]["n"] else "-",
                       "{:,.0f}".format(row["lb"]["per_ctr"]) if row["lb"]["n"] else "-"))
        print(L[-1], flush=True)
    n_both_total = int(both.sum())
    L.append("")
    if n_both_total < 20:
        L.append("  *** the BOTH bucket is %d trades total (%.1f%% of the leg) - a dozen-trade corner. "
                 "Everything below is commentary on a small sample. ***"
                 % (n_both_total, 100.0 * n_both_total / len(t)))
    else:
        L.append("  the BOTH bucket is %d trades total (%.1f%% of the leg)." % (n_both_total, 100.0 * n_both_total / len(t)))
    print(L[-1], flush=True)

    # ================= (b)-(g) THE LADDER VARIANTS =================
    L.append("")
    L.append("=" * 100)
    L.append("(b)-(g) THE LADDER - same trades, different weights. MAR is annualised on EACH slice's own")
    L.append("    elapsed time and its own drawdown (whole-run parity above used the pinned 16.06 years).")
    L.append("=" * 100)
    H1 = "  %-46s %s" % ("", "--------------- discovery ---------------   ---------------- holdout ----------------   ---------------- lockbox ----------------")
    H2 = "  %-46s %4s %6s %10s %8s %6s %7s   %4s %6s %10s %8s %6s %7s   %4s %6s %10s %8s %6s %7s" % (
        "variant", "n", "PF", "net $", "DD $", "MAR", "$/ctr", "n", "PF", "net $", "DD $", "MAR", "$/ctr",
        "n", "PF", "net $", "DD $", "MAR", "$/ctr")
    L.append(H1); L.append(H2)
    print(H1, flush=True); print(H2, flush=True)

    def emit(name, w):
        u = price(w)
        rows = []
        for smsk in (disc, hold, lb):
            rows.append(stats(u[smsk], w[smsk], dates=t["date"].values[smsk] if smsk.any() else None))
        L.append(fmt_row(name, *rows))
        print(L[-1], flush=True)
        return rows

    w_b = w_incumbent
    w_c = np.where(both | deep_only | open_only, 1.5, 1.0)   # either rule -> 1.5, never 2.25
    w_d = np.where(both, 2.0, np.where(deep_only | open_only, 1.5, 1.0))
    w_e = np.where(both, 2.0, np.where(deep_only | open_only, 1.0 + 0.5, 1.0))  # additive w/ floor 1.0
    w_f = np.full(len(t), 1.5)
    w_g = np.full(len(t), 1.0)

    r_b = emit("(b) incumbent, multiplicative 1.0/1.5/1.5/2.25", w_b)
    r_c = emit("(c) capped at 1.5 (either rule -> 1.5, never 2.25)", w_c)
    r_d = emit("(d) capped at 2.0", w_d)
    if np.array_equal(w_d, w_e):
        L.append("  (e) additive-to-2.0 with a floor: identical weights to (d) on this data (only 4 discrete")
        L.append("      buckets exist, and both formulas give them 1.0 / 1.5 / 1.5 / 2.0) - not printed again.")
        print("\n".join(L[-2:]), flush=True)
        r_e = r_d
    else:
        r_e = emit("(e) additive-to-2.0 with a floor", w_e)
    r_f = emit("(f) flat 1.5x on every trade (leverage control)", w_f)
    r_g = emit("(g) no tilt at all (untilted structural-stop leg)", w_g)

    # ================= what the top rung is worth =================
    L.append("")
    L.append("=" * 100)
    L.append("WHAT THE TOP RUNG (BOTH bucket, 2.25x) IS WORTH - (b) incumbent minus (c) capped-at-1.5,")
    L.append("the only difference between those two rows is the extra 0.75x on the BOTH bucket.")
    L.append("=" * 100)
    for i, nm in enumerate(("discovery", "holdout", "lockbox")):
        db = r_b[i]; dc = r_c[i]
        dnet = db["net"] - dc["net"]
        ddd = db["dd"] - dc["dd"]
        L.append("  %-10s net %s (%.1f%% of the incumbent's net), drawdown %s (%.1f%% of the incumbent's DD)"
                 % (nm, "{:+,.0f}".format(dnet), 100 * dnet / db["net"] if db["net"] else float("nan"),
                    "{:+,.0f}".format(ddd), 100 * ddd / db["dd"] if db["dd"] else float("nan")))
    print("\n".join(L[-3:]), flush=True)
    both_net_share = float(usd_incumbent[both].sum()) / float(usd_incumbent.sum()) if usd_incumbent.sum() else float("nan")
    both_grossloss_share = (float(-usd_incumbent[both & (usd_incumbent < 0)].sum())
                            / float(-usd_incumbent[usd_incumbent < 0].sum())
                            if (usd_incumbent < 0).any() else 0.0)
    L.append("")
    L.append("  whole-run: the BOTH bucket (%d of %d trades, %.1f%%) carries %.1f%% of the leg's total net money "
             "and %.1f%% of its gross losing dollars (a proxy for drawdown share, not the drawdown path itself)."
             % (n_both_total, len(t), 100.0 * n_both_total / len(t), 100 * both_net_share, 100 * both_grossloss_share))
    print(L[-1], flush=True)

    L.append("")
    L.append("  Deep-squeeze threshold %.2f, deep multiplier %.2fx, open-bar multiplier %.2fx - all three read from"
             % (deep_thr, deep_mult, open_mult))
    L.append("  the strategy files, fixed a priori, not tuned by this run. Nothing here is crowned; the cap decision")
    L.append("  belongs to the owner.")
    print("\n".join(L[-3:]), flush=True)

    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
