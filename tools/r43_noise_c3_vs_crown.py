#!/usr/bin/env python3
"""NOISE ROUND 43 (2026-09-09) -- is round 41's cost-robust GEOMETRY a replacement for the
LIVE NOISE crown on the crown's own 5-minute bar?

WHY THIS RUNS (owner: "keep testing noise")
-------------------------------------------
Round 41 walked the bar ladder and killed the 2-minute leg idea (the 2m cells are the crown
re-expressed: 81-92% shared days, 98% same direction, and run #334's champion LOSES $93k on the
days the crown does not trade). It left exactly one live lead, in its own words:

    "If the crown's exit/stop geometry is ever revisited, C3 at 5m (PF 1.563, 8/8, $104 a trade)
     is the configuration to test against it -- as a REPLACEMENT candidate, never as an addition."

C3 is round 38's cost-robust corner (2m search rank 8): band exit, ATR stop 0.75, confirm 3,
afternoon block, skip-bot-short, lookback 74, bands 1.00/1.75, vol-skip 93. On the crown's own
5m bar round 41 measured it at n 1,956 / $202,725 / PF 1.563 / DD $12,737 / 8-of-8 / $104 a trade
and called it "the best trade in this whole line of work, on far fewer of them".

Nobody has tested it against the crown that actually trades. Round 41 compared it to the **#243**
geometry; the live paper leg and family crown is **#304** (same knob set, lookback 40, vol-skip 95).
Round 41 also reported no concentration read, no held-out read, and no knob plateau for C3 AT 5m
(its plateau was across the BAR dimension). All four are required before a replacement candidate
can be queued, so all four are here.

THE PRE-REGISTERED BAR (written before anything ran)
-----------------------------------------------------
A replacement for a crowned, paper-traded, NinjaTrader-deployed configuration is the highest bar
in this program, so C3 becomes a QUEUEABLE CANDIDATE only if it clears ALL of:

  (a) net-over-drawdown ABOVE the live crown at ALL THREE costs (0.533 house / 0.783 / 1.033) --
      not at one cost, because a cost-fragile winner is what round 38 already caught once;
  (b) profit factor above the crown at all three costs;
  (c) eight-slice chronological consistency at least as good as the crown's at the stressed cost;
  (d) ex-top-10 net positive AND top-10 share no more than 5 points worse than the crown's
      (the standing concentration rule, memory `edgelog-bookmarks` B17/B19 retraction);
  (e) a knob plateau AT 5m: at least 80% of one-step neighbours keep profit factor >= 1.25 and at
      least 70% of C3's own net-over-drawdown. A crown replacement cannot be a spike.

And regardless of (a)-(e), the report must state the PRICE of the swap in plain numbers: C3 trades
roughly half as often as the crown, so a "better" trade can still mean less money and slower
forward evidence. If C3 gives up more than 25% of the crown's net it is a RISK-ADJUSTED case only
and must be labelled that way, never sold as an upgrade.

Clearing the bar queues a FENCED neighbourhood Auto-Validate (the house pipeline: search ->
neighbourhood -> fenced file -> validate). It does NOT crown anything. Crowning is the owner's call.

WINDOW / DATA. One window everywhere: 2010-06-07 -> 2026-07-16 on the REGISTERED NQ 5m RTH master
(db_noadj_rth), trades split by ENTRY time at 2025-02-14 (run #334's own held-out boundary). The
NOISE lockbox is SPENT (read since 2026-08-12), so the post-split stretch here is CONFIRMATORY
ONLY and ranks nothing. Gate G1 first reproduces round 41's C3-at-5m headline on their window
(2010-06-07..2025-06-29) -- they resampled a 1m tape in-file, this uses the registered 5m master,
so a small difference is expected and is printed rather than hidden.

Usage:  python tools/r43_noise_c3_vs_crown.py [--skip-plateau]
Writes: tools/r37_results/r43_c3_vs_crown.csv, r43_plateau.csv, r43_overlap.txt
"""
import argparse
import csv
import os
import sys

import numpy as np
import pandas as pd

# A git worktree has NO master registry (optimizer_history.db is untracked -- memory
# `edgelog-worktree-registry-trap`), so anything that loads a master must run against the
# SHARED checkout. EDGELOG_REPO_ROOT lets this file live in a worktree while importing the
# shared engine and reading the shared registry; unset, it behaves exactly as before.
ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402

MULT = 20.0
SRC = "db_noadj_rth"
FULL = dict(date_from="2010-06-07", date_to="2026-07-16")
R41 = dict(date_from="2010-06-07", date_to="2025-06-29")   # round 41's own selection window
SPLIT = "2025-02-14"                                        # run #334's held-out boundary
COSTS = [0.533, 0.783, 1.033]

# ── the three configurations ────────────────────────────────────────────────────────────
# C3: round 38 cost-robust corner = 2m search rank 8, carried to 5m by round 41
C3 = dict(lookback=74, band_mult_long=1.0, band_mult_short=1.75, exit_mode="band",
          side="Both", window="afternoon_block", flat_eod=False, skip_holidays=False,
          stop_mode="atr", stop_k=0.75, confirm_bars=3, daytype_mode="skip_bot_short",
          daytype_lo=0.1, daytype_hi=0.95, vol_skip_pct=93.0)

# CROWN304: the LIVE family crown and paper leg (api/paper.py NOISE_304_NBHD knobs)
CROWN304 = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
                side="Both", window="all_day", flat_eod=True, skip_holidays=False,
                stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
                daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)

# CROWN243: the older paper leg round 41 actually compared against, kept as the bridge to their table
CROWN243 = dict(CROWN304, lookback=44, vol_skip_pct=90.0)

CFGS = [("C3 corner", C3), ("CROWN #304 (live)", CROWN304), ("CROWN #243", CROWN243)]

FN = "NOISE_1_0.py"


def _load(win):
    return load_master_arrays(find_master("NQ", "5m", "rth", SRC), **win)


def _metrics(pnl_pts, mult=MULT, years=None):
    """House metrics from a list of per-trade P&L in POINTS, in entry order."""
    p = np.asarray(pnl_pts, dtype=float) * mult
    n = len(p)
    if n == 0:
        return dict(n=0)
    wins, losses = p[p > 0], p[p < 0]
    gp, gl = wins.sum(), -losses.sum()
    pf = (gp / gl) if gl > 0 else float("inf")
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    wr = 100.0 * len(wins) / n
    avg_loss = (gl / len(losses)) if len(losses) else 0.0
    evr = (net / n) / avg_loss if avg_loss > 0 else 0.0     # expectancy in R (R = average loss)
    tpy = n / years if years else 0.0
    k = n // 8
    slices8 = sum(1 for i in range(8)
                  if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0) if k > 0 else 0
    top10 = float(np.sort(p)[-10:].sum()) if n >= 10 else net
    return dict(n=n, net=net, pf=pf, dd=dd, ndd=(net / dd if dd > 0 else 99.0),
                mar=((net / years) / dd if (years and dd > 0) else 0.0), wr=wr, evr=evr,
                ryr=evr * tpy, tpy=tpy, slices8=slices8,
                top10_share=(100.0 * top10 / net if net > 0 else float("nan")),
                ex10_net=net - top10, per_trade=net / n)


def measure(arrays, params, cost, split=None):
    """One continuous backtest; metrics for the whole run and, if `split` is given, for the
    stretch before and after it, sliced by ENTRY time (the house convention)."""
    r = run_backtest(FN, arrays=arrays, params=dict(params), cost_pts=cost, return_trades=True)
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    idx = pd.DatetimeIndex(arrays["index"])
    years = (idx[-1] - idx[0]).days / 365.25
    days = np.array([idx[t[0]].date() for t in tr])
    pnl = [t[2] for t in tr]
    out = dict(all=_metrics(pnl, years=years))
    if split:
        cut = pd.Timestamp(split).date()
        pre = [p for d, p in zip(days, pnl) if d < cut]
        post = [p for d, p in zip(days, pnl) if d >= cut]
        # the master index is tz-aware; match it or the subtraction raises
        cut_ts = pd.Timestamp(split, tz=idx.tz) if idx.tz is not None else pd.Timestamp(split)
        yr_pre = (cut_ts - idx[0]).days / 365.25
        yr_post = (idx[-1] - cut_ts).days / 365.25
        out["sel"] = _metrics(pre, years=yr_pre)
        out["held"] = _metrics(post, years=yr_post)
    out["_trades"] = (days, np.asarray(pnl) * MULT, np.array([t[3] for t in tr]))
    return out


def row(label, cost, m):
    s, h = m.get("sel") or {}, m.get("held") or {}
    return dict(cfg=label, cost=cost,
                sel_n=s.get("n"), sel_pf=round(s.get("pf", 0), 3), sel_net=round(s.get("net", 0)),
                sel_dd=round(s.get("dd", 0)), sel_ndd=round(s.get("ndd", 0), 2),
                sel_mar=round(s.get("mar", 0), 2), sel_evr=round(s.get("evr", 0), 3),
                sel_ryr=round(s.get("ryr", 0), 1), sel_slices=s.get("slices8"),
                sel_top10=round(s.get("top10_share", 0), 1), sel_ex10=round(s.get("ex10_net", 0)),
                sel_per_trade=round(s.get("per_trade", 0)),
                held_n=h.get("n"), held_pf=round(h.get("pf", 0), 3), held_net=round(h.get("net", 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-plateau", action="store_true")
    a = ap.parse_args()

    print(__doc__.split("Usage:")[0].split("WHY THIS RUNS")[0].strip())
    print("=" * 104)

    # ── GATE G1: reproduce round 41's C3-at-5m headline on the registered master ─────────
    A41 = _load(R41)
    g = measure(A41, C3, 0.533)["all"]
    print("GATE G1 -- round 41 said C3 on 5m: n 1,956 / $202,725 / PF 1.563 / DD $12,737 / 8-of-8 / $104 a trade")
    print("          this run (registered 5m master):  n %s / $%s / PF %.3f / DD $%s / %d-of-8 / $%.0f a trade"
          % (g["n"], format(round(g["net"]), ","), g["pf"], format(round(g["dd"]), ","),
             g["slices8"], g["per_trade"]))
    dn = 100.0 * (g["n"] - 1956) / 1956
    dnet = 100.0 * (g["net"] - 202725) / 202725
    print("          difference: trades %+.1f%%, net %+.1f%%  (round 41 resampled a 1m tape; this is "
          "the registered 5m master)" % (dn, dnet))
    if abs(dnet) > 15 or abs(dn) > 15:
        print("          *** WARNING: more than 15% apart -- treat every C3 number below as unconfirmed ***")
    print()

    # ── MAIN: the cost ladder, one shared window, entry-sliced ──────────────────────────
    AF = _load(FULL)
    print("COST LADDER -- %s to %s, entry-sliced at %s (post-split stretch is SPENT, confirmatory only)"
          % (FULL["date_from"], FULL["date_to"], SPLIT))
    print("%-19s %6s | %6s %7s %10s %9s %6s %6s %5s %6s %7s %10s | %5s %6s %9s"
          % ("config", "cost", "n", "PF", "net $", "DD $", "n/DD", "MAR", "sl/8", "top10",
             "ex10 $", "$/trade", "n", "PF", "net $"))
    rows, ladder = [], {}
    for label, params in CFGS:
        for cost in COSTS:
            m = measure(AF, params, cost, split=SPLIT)
            ladder[(label, cost)] = m
            r = row(label, cost, m)
            rows.append(r)
            print("%-19s %6.3f | %6s %7.3f %10s %9s %6.2f %6.2f %5s %5.1f%% %10s %8s | %5s %6.3f %9s"
                  % (label, cost, r["sel_n"], r["sel_pf"], format(r["sel_net"], ","),
                     format(r["sel_dd"], ","), r["sel_ndd"], r["sel_mar"], r["sel_slices"],
                     r["sel_top10"], format(r["sel_ex10"], ","), format(r["sel_per_trade"], ","),
                     r["held_n"], r["held_pf"], format(r["held_net"], ",")))
        print()

    out = os.path.join(ROOT, "tools", "r37_results", "r43_c3_vs_crown.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ── the pre-registered read ─────────────────────────────────────────────────────────
    print("=" * 104)
    print("THE BAR (fixed before the run): C3 must beat the LIVE crown #304 on net-over-drawdown AND")
    print("profit factor at ALL THREE costs, match its 8-slice consistency at 0.783, keep ex-top-10")
    print("positive with top-10 share no more than 5 points worse, and sit on a knob plateau at 5m.")
    print("=" * 104)
    verdict = {}
    for cost in COSTS:
        c3 = ladder[("C3 corner", cost)]["sel"]
        cr = ladder[("CROWN #304 (live)", cost)]["sel"]
        verdict[("ndd", cost)] = c3["ndd"] > cr["ndd"]
        verdict[("pf", cost)] = c3["pf"] > cr["pf"]
        print("  %.3f: n/DD %6.2f vs %6.2f %s | PF %.3f vs %.3f %s | slices %d vs %d | net $%s vs $%s (%+.0f%%)"
              % (cost, c3["ndd"], cr["ndd"], "C3" if c3["ndd"] > cr["ndd"] else "crown",
                 c3["pf"], cr["pf"], "C3" if c3["pf"] > cr["pf"] else "crown",
                 c3["slices8"], cr["slices8"], format(round(c3["net"]), ","),
                 format(round(cr["net"]), ","), 100.0 * (c3["net"] - cr["net"]) / cr["net"]))
    c3s = ladder[("C3 corner", 0.783)]["sel"]
    crs = ladder[("CROWN #304 (live)", 0.783)]["sel"]
    conc_ok = c3s["ex10_net"] > 0 and c3s["top10_share"] <= crs["top10_share"] + 5
    slice_ok = c3s["slices8"] >= crs["slices8"]
    print("  concentration at 0.783: C3 top-10 %.1f%% (crown %.1f%%), ex-top-10 $%s -> %s"
          % (c3s["top10_share"], crs["top10_share"], format(round(c3s["ex10_net"]), ","),
             "ok" if conc_ok else "FAILS"))
    print("  slices at 0.783: C3 %d vs crown %d -> %s" % (c3s["slices8"], crs["slices8"],
                                                          "ok" if slice_ok else "FAILS"))
    money = 100.0 * (c3s["net"] - crs["net"]) / crs["net"]
    trades = 100.0 * (c3s["n"] - crs["n"]) / crs["n"]
    print("  THE PRICE OF THE SWAP at 0.783: C3 makes %+.0f%% of the crown's money on %+.0f%% of its "
          "trades ($%s a trade vs $%s)" % (money, trades, format(round(c3s["per_trade"]), ","),
                                           format(round(crs["per_trade"]), ",")))
    if money < -25:
        print("  -> RISK-ADJUSTED CASE ONLY: it gives up more than a quarter of the crown's net. "
              "Never present this as an upgrade.")

    # ── OVERLAP: same days, or a different trade set? (sorted index -- round 41's bug) ───
    c3d = ladder[("C3 corner", 0.533)]["_trades"]
    crd = ladder[("CROWN #304 (live)", 0.533)]["_trades"]
    s3 = pd.Series(c3d[1], index=pd.DatetimeIndex(pd.to_datetime(c3d[0]))).groupby(level=0).sum().sort_index()
    sc = pd.Series(crd[1], index=pd.DatetimeIndex(pd.to_datetime(crd[0]))).groupby(level=0).sum().sort_index()
    shared = s3.index.intersection(sc.index)
    both = pd.concat([s3.rename("c3"), sc.rename("crown")], axis=1).fillna(0.0).sort_index()
    assert both.index.is_monotonic_increasing
    corr_all = both["c3"].corr(both["crown"])
    corr_shared = both.loc[shared, "c3"].corr(both.loc[shared, "crown"]) if len(shared) > 2 else float("nan")
    c3_alone = float(s3[~s3.index.isin(sc.index)].sum())
    print()
    print("OVERLAP with the live crown (house cost, whole window, daily P&L, sorted):")
    print("  C3 trades %d days, crown %d days, shared %d (%.0f%% of C3's days)"
          % (len(s3), len(sc), len(shared), 100.0 * len(shared) / max(len(s3), 1)))
    print("  daily correlation %.3f (shared days %.3f) | C3's net on days the crown is flat: $%s"
          % (corr_all, corr_shared, format(round(c3_alone), ",")))
    print("  reading: a REPLACEMENT is expected to overlap heavily -- that is the point. High overlap "
          "here means the swap is a pure geometry change on the same days, not a different edge.")
    with open(os.path.join(ROOT, "tools", "r37_results", "r43_overlap.txt"), "w", encoding="utf-8") as fh:
        fh.write("C3 days %d, crown days %d, shared %d, corr %.3f (shared %.3f), C3-alone net %.0f\n"
                 % (len(s3), len(sc), len(shared), corr_all, corr_shared, c3_alone))

    # ── PLATEAU at 5m: every knob one step each way ──────────────────────────────────────
    if not a.skip_plateau:
        import importlib.util as ilu
        sp = ilu.spec_from_file_location("m", os.path.join(ROOT, "augur_strategies", FN))
        mod = ilu.module_from_spec(sp)
        sp.loader.exec_module(mod)
        DP = mod.DEFAULT_PARAMS
        base = ladder[("C3 corner", 0.533)]["sel"]
        print()
        print("PLATEAU at 5m (house cost, selection stretch): every knob one step each way; base "
              "PF %.3f, n/DD %.2f" % (base["pf"], base["ndd"]))
        nb, keep = [], 0
        for k, spec in DP.items():
            vals = []
            if spec.get("options"):
                vals = [v for v in spec["options"] if v != C3.get(k)]
            elif spec.get("type") == "bool":
                vals = [not C3.get(k)]
            elif "step" in spec:
                st, lo, hi = spec["step"], spec.get("min"), spec.get("max")
                for d in (-st, st):
                    v = C3.get(k, spec["default"]) + d
                    if (lo is None or v >= lo) and (hi is None or v <= hi):
                        vals.append(round(v, 6) if isinstance(v, float) else int(v))
            for v in vals:
                p = dict(C3); p[k] = v
                m = measure(AF, p, 0.533, split=SPLIT)["sel"]
                ok = (m.get("pf", 0) >= 1.25 and m.get("ndd", 0) >= 0.70 * base["ndd"])
                keep += 1 if ok else 0
                nb.append(dict(knob=k, value=v, n=m.get("n"), pf=round(m.get("pf", 0), 3),
                               net=round(m.get("net", 0)), ndd=round(m.get("ndd", 0), 2),
                               slices=m.get("slices8"), keeps=int(ok)))
        share = 100.0 * keep / max(len(nb), 1)
        print("  %d neighbours, %d keep PF >= 1.25 AND >= 70%% of the base n/DD -> %.0f%% (bar: 80%%) -> %s"
              % (len(nb), keep, share, "PLATEAU" if share >= 80 else "NOT A PLATEAU"))
        worst = sorted(nb, key=lambda r: r["ndd"])[:5]
        for r in worst:
            print("    weakest: %-16s = %-14s n %-5s PF %.3f n/DD %5.2f" %
                  (r["knob"], r["value"], r["n"], r["pf"], r["ndd"]))
        with open(os.path.join(ROOT, "tools", "r37_results", "r43_plateau.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(nb[0]))
            w.writeheader()
            w.writerows(nb)

    print()
    print("wrote tools/r37_results/r43_c3_vs_crown.csv, r43_plateau.csv, r43_overlap.txt")


if __name__ == "__main__":
    main()
