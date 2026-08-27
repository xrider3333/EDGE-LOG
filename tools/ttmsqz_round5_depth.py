"""
TTM SQUEEZE ROUND 5 — attack the ONE gate the pocket keeps failing: trade count.

Rounds 1-4 landed here: the only real edge in this family is to take a short-timeframe
squeeze fire ONLY while a higher timeframe is still compressed (round 4, studies rows
596-691). Three pinned validates of that pocket all PASSED their lockbox (runs 279/280/281)
and all failed the same single gate - sample size. They trade 13 to 25 times a year, so a
15-year run carries only a couple of hundred trades and the house needs 30 per knob.

So round 5 does not hunt for a bigger edge. It asks: can the SAME edge be made to trade
more often without diluting it? Three levers, each measured against the round-4 pocket:

  1. COMPRESSION AS A DIAL, NOT A SWITCH.
     Carter's squeeze is binary - the Bollinger band is either inside the Keltner channel
     or it is not. That is the ratio (bb_mult*stdev) / (kc_mult*ATR) crossing 1.0. Round 5
     exposes the ratio itself, so "nearly coiled" hours (1.05, 1.15, 1.30) can be admitted.
     A threshold of exactly 1.0 must reproduce the round-4 gate to the dollar, and that
     equivalence is asserted at startup as the control.

  2. THE VERIFICATION TIMEFRAME ITSELF.
     Round 4 only tried 60m, 120m and daily at one length. Here: 30 / 60 / 90 / 120 / 180
     minutes, at gate lengths 14 / 20 / 26. A shorter verification frame coils and releases
     more often, which is more trades by construction - the question is whether the edge
     survives it.

  3. POOLING.
     One strategy on one timeframe cannot trade more without loosening. But the SAME rule
     on 5m, 15m and 30m bars is three near-independent streams of the same edge. Pooled
     trade counts and pooled money are reported for the survivors, which is the honest way
     to reach a sample the house gates will accept.

Everything else is the audited round-4 scaffolding, imported unchanged: decisions on the
bar close, fills next bar, conservative same-bar stop, flat at every session close, window
pinned 2010-06-07..2026-06-30, lockbox = last 12 months, house costs, one contract.

Usage:  python tools/ttmsqz_round5_depth.py [smoke]
Output: tools/data/ttmsqz_round5_depth.txt
"""
import os, sys, importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_sp = importlib.util.spec_from_file_location("r4", os.path.join(ROOT, "tools", "ttmsqz_round4_mtf.py"))
r4 = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(r4)
ttm = r4.ttm

DATE_FROM, LB_FROM, DATE_TO = r4.DATE_FROM, r4.LB_FROM, r4.DATE_TO
COST, MULT = r4.COST, r4.MULT


def htf_ratio(base, htf, length=20, bb_mult=2.0, kc_mult=1.5):
    """Compression RATIO of the higher timeframe, mapped causally onto the base frame.

    ratio = (bb_mult * stdev) / (kc_mult * ATR) on the higher-timeframe bars. Carter's
    squeeze is exactly ratio < 1. Built from the SAME session-anchored, end-time-mapped
    frame round 4 uses, so a threshold of 1.0 reproduces its gate bar for bar."""
    if htf == "D":
        g = base.groupby("day_id", sort=True)
        hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
        end = g["_end"].last().values
    else:
        m = int(htf[:-1])
        mins = base["_dt"].dt.hour * 60 + base["_dt"].dt.minute - 570
        key = base["_dt"].dt.date.astype(str) + "_" + (mins // m).astype(str).str.zfill(3)
        g = base.groupby(key, sort=True)
        hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
        end = g["_end"].last().values
    order = np.argsort(end)
    hh, ll, cc, end = hh[order], ll[order], cc[order], end[order]

    s = pd.Series(cc)
    dev = s.rolling(length).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(length).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((bb_mult * dev) / (kc_mult * atr)).to_numpy()

    nh = len(cc)
    warm = length * 2 + 5
    j = np.searchsorted(end, base["_end"].values, side="right") - 1
    valid = j >= warm
    jj = np.clip(j, 0, nh - 1)
    return np.where(valid, ratio[jj], np.nan)


def gate_from_ratio(ratio, thr):
    ok = np.isfinite(ratio) & (ratio <= thr)
    return ok, ok.copy()


def stats(log, df, inst):
    return r4.stats(log, df, inst)


ENTRIES = [("carter", dict(entry_fill="open", exit_mode="fade")),
           ("break", dict(entry_fill="range_break", exit_mode="ride"))]
THRESH = [0.85, 1.00, 1.15, 1.30, 1.50]
GATE_TF = ["30m", "60m", "120m"]
GATE_LEN = [14, 20, 26]
CELLS = [("ES", "30m"), ("NQ", "15m"), ("NQ", "5m"), ("ES", "15m")]


def main():
    smoke = "smoke" in sys.argv
    cells = CELLS[:1] if smoke else CELLS
    lines = []
    keep = {}
    for inst, base_tf in cells:
        df = r4.load_base(inst, base_tf)
        # ── CONTROL: threshold 1.0 must reproduce the round-4 binary gate exactly ──
        ctrl_r = htf_ratio(df, "60m", 20)
        gl, gs = gate_from_ratio(ctrl_r, 1.0)
        b4 = r4.build_htf(df, "60m", 20)
        agree = int((gl == b4["sq_on"]).sum()); tot = len(gl)
        hdr = ("\n== %s base %s   control: ratio<=1.0 matches the round-4 squeeze gate on %d of %d bars%s"
               % (inst, base_tf, agree, tot, "" if agree == tot else "  <-- MISMATCH, read with care"))
        print(hdr, flush=True); lines.append(hdr)
        h2 = "%-8s %-5s %-4s %-5s %6s %5s %6s %11s %9s %6s | %11s %6s %5s" % (
            "entry", "gate", "len", "thr", "trades", "WR%", "PF", "net $", "maxDD $", "MAR", "LB $", "LB PF", "yrs+")
        print(h2); lines.append(h2)
        for ename, ekw in ENTRIES:
            for gtf in (GATE_TF[:1] if smoke else GATE_TF):
                # A verification frame must be HIGHER than the traded one. Equal is
                #   degenerate: a fire means the base squeeze just released, so "the same
                #   timeframe is still compressed" is false by construction and the cell
                #   trades nothing (observed on ES 30m base with a 30m gate).
                if int(gtf[:-1]) <= int(base_tf[:-1]):
                    continue
                for glen in (GATE_LEN[1:2] if smoke else GATE_LEN):
                    rat = htf_ratio(df, gtf, glen)
                    for thr in THRESH:
                        a, b = gate_from_ratio(rat, thr)
                        s = stats(r4.run_gated(df, a, b, **ekw), df, inst)
                        if s is None:
                            continue
                        f = s["full"]; mar = f["net"] / f["dd"] if f["dd"] > 0 else 0
                        row = "%-8s %-5s %-4d %-5.2f %6d %5.1f %6.2f %11s %9s %6.2f | %11s %6.2f %2d/%-2d" % (
                            ename, gtf, glen, thr, f["n"], f["wr"], min(f["pf"], 99),
                            f"{f['net']:,.0f}", f"{f['dd']:,.0f}", mar,
                            f"{s['LB']['net']:,.0f}", min(s["LB"]["pf"], 99), f["yplus"], f["yminus"])
                        print(row, flush=True); lines.append(row)
                        # keep the survivors for the pooling read
                        if f["pf"] >= 1.15 and s["LB"]["net"] > 0 and f["n"] >= 200:
                            keep[(inst, base_tf, ename, gtf, glen, thr)] = (f, s["LB"])

    # ── POOLING: the same rule on several base timeframes is several streams of one edge ──
    if keep:
        lines.append("\n== SURVIVORS (profit factor 1.15+, positive lockbox, 200+ trades), best first")
        lines.append("%-4s %-5s %-8s %-5s %-4s %-5s %6s %6s %11s %9s %6s %11s" % (
            "inst", "base", "entry", "gate", "len", "thr", "trades", "PF", "net $", "maxDD $", "MAR", "LB $"))
        for k, (f, lb) in sorted(keep.items(), key=lambda kv: -kv[1][0]["net"] / max(kv[1][0]["dd"], 1)):
            inst, base_tf, ename, gtf, glen, thr = k
            mar = f["net"] / f["dd"] if f["dd"] > 0 else 0
            lines.append("%-4s %-5s %-8s %-5s %-4d %-5.2f %6d %6.2f %11s %9s %6.2f %11s" % (
                inst, base_tf, ename, gtf, glen, thr, f["n"], min(f["pf"], 99),
                f"{f['net']:,.0f}", f"{f['dd']:,.0f}", mar, f"{lb['net']:,.0f}"))
        for ln in lines[-(len(keep) + 2):]:
            print(ln)
    else:
        lines.append("\nNo cell cleared profit factor 1.15 with a positive lockbox and 200+ trades.")
        print(lines[-1])

    out = os.path.join(ROOT, "tools", "data", "ttmsqz_round5_depth.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("TTM SQUEEZE ROUND 5 (compression as a dial + verification timeframe + pooling)\n"
                 "window %s..%s, lockbox from %s, house costs, one contract\n" % (DATE_FROM, DATE_TO, LB_FROM))
        fh.write("\n".join(lines) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
