"""Round 15e - the open-bar tilt, the follow-up round 15b's negative result demands.

Round 15b asked whether the strategy should skip the noisy first bars of the session, the way it
already skips the last. The answer was not merely no, it was INVERTED: blocking just the 09:30 bar
removes 87 trades worth +$70,053 - an average of $805 against $283 across the whole population, 65
percent winners. The overnight gap released into a coiled hour is where this mechanism's edge sits.

If those trades are that much better, the shop's own preferred shape says to SIZE them rather than
admire them - a tilt, never a filter. That is what this measures.

THE DISCIPLINE, because this rule was found by looking at the same trades it would be applied to:
the pre-lockbox trades are split 60/40 by time into a discovery half and a holdout half. The rule
is fixed - first bar of the session, no threshold to tune - and reported on discovery, holdout and
the lockbox side by side. A rule that lives only in discovery is an artifact and is labelled one.
The tilt is judged on RISK-ADJUSTED terms, because more size is always more money: annualised MAR on
the leg's own drawdown, and money per contract traded, with a flat 1.5x leverage control beside it.

Log: tools/data/ttmsqz_r15e_open_bar_tilt.txt
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
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r15e_open_bar_tilt.txt")
COST, MULT, YRS = r6.COST["ES"], r6.MULT["ES"], 16.06


def leg_trades():
    """The book leg's own trades, with the entry bar's ordinal within its session."""
    m = r6._mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS20.py"), "ss20_r15e")
    df = r6.load("ES", "30m", "RTH")
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                       day_id=df["day_id"].values, index=df["_dt"], return_trades=True,
                       kc_mult=1.5, eod_cutoff=1)
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]], columns=["eb", "xb", "pts"])
    did = np.asarray(df["day_id"])
    ordinal = np.zeros(len(did), int)
    a = 0
    while a < len(did):
        b = a
        while b < len(did) and did[b] == did[a]:
            b += 1
        ordinal[a:b] = np.arange(b - a)
        a = b
    t["bar_of_day"] = ordinal[t["eb"].values]
    t["usd"] = (t["pts"] - COST) * MULT
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()
    return t


def stats(usd, contracts=None):
    if not len(usd):
        return None
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    out = dict(n=len(usd), net=float(usd.sum()), pf=(gw / gl) if gl > 0 else 99.0, dd=dd,
               mar=(float(usd.sum()) / YRS) / dd if dd > 0 else float("nan"))
    out["per_contract"] = float(usd.sum()) / contracts if contracts else float("nan")
    return out


def main():
    L = ["TTM SQUEEZE r15e - the OPEN-BAR TILT, the follow-up round 15b demands   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; the book leg (ES30SS20) on ES 30m RTH, 0.363 pts a round trip, 50 a point"
         % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM),
         "Discovery = the first 60 percent of pre-lockbox trades by time; the rule has no threshold to tune.",
         "Judged risk-adjusted, with a flat 1.5x leverage control beside it. Nothing is crowned here."]
    print("\n".join(L), flush=True)
    t = leg_trades()
    lb = (t["date"] >= pd.Timestamp(r6.LB_FROM)).values
    pre = np.flatnonzero(~lb)
    cut = pre[int(len(pre) * 0.6)]
    disc = np.zeros(len(t), bool); disc[pre[pre < cut]] = True
    hold = np.zeros(len(t), bool); hold[pre[pre >= cut]] = True
    usd = t["usd"].values
    # "the open bar" means the EARLIEST BAR AN ENTRY CAN HAPPEN ON, which is ordinal 1, not 0: a fire
    # is decided on a closed bar and filled at the next open, so no trade can ever enter on the
    # session's first bar. The first version of this file used ordinal 0 and found zero trades -
    # worth keeping as a note, because round 15b's "block the first bar" is the same off-by-one and
    # its 87 removed trades are these.
    first = (t["bar_of_day"].values == 1)
    L.append("")
    L.append("  %d trades, %d entered on the session first bar (%.0f percent). Discovery %d, holdout %d, lockbox %d."
             % (len(t), int(first.sum()), 100 * first.mean(), disc.sum(), hold.sum(), lb.sum()))
    L.append("  mean dollars a trade: first bar %s, every other bar %s"
             % ("{:,.0f}".format(usd[first].mean()), "{:,.0f}".format(usd[~first].mean())))
    print("\n".join(L[-2:]), flush=True)

    H = "  %-34s %5s %6s %10s %8s %6s %8s   %5s %6s %10s %8s %6s   %5s %6s %10s %8s"
    L.append("")
    L.append("  %-34s %s" % ("", "----------------- discovery -----------------   ------------- holdout -------------   ------------- lockbox -------------"))
    L.append(H % ("variant", "n", "PF", "net $", "DD $", "MAR", "$/ctr", "n", "PF", "net $", "DD $", "MAR", "n", "PF", "net $", "DD $"))

    def emit(name, sized):
        cells = []
        for m in (disc, hold, lb):
            c = float(np.where(first, 1.0, 1.0).sum())  # replaced per-variant below
            s = stats(sized[m], contracts=None)
            cells.append(s)
        d_, h_, l_ = cells
        ctr_d = float(np.where(sized[disc] == usd[disc], 1.0, 1.5).sum())
        L.append(H % (name, d_["n"], "%.2f" % min(d_["pf"], 99), "{:,.0f}".format(d_["net"]),
                      "{:,.0f}".format(d_["dd"]), "%.2f" % d_["mar"], "{:,.0f}".format(d_["net"] / max(ctr_d, 1)),
                      h_["n"], "%.2f" % min(h_["pf"], 99), "{:,.0f}".format(h_["net"]),
                      "{:,.0f}".format(h_["dd"]), "%.2f" % h_["mar"],
                      l_["n"], "%.2f" % min(l_["pf"], 99), "{:,.0f}".format(l_["net"]), "{:,.0f}".format(l_["dd"])))
        print(L[-1], flush=True)

    emit("the book leg, unchanged", usd)
    emit("1.5x on session-first-bar entries", np.where(first, 1.5 * usd, usd))
    emit("2.0x on session-first-bar entries", np.where(first, 2.0 * usd, usd))
    emit("flat 1.5x (leverage control)", 1.5 * usd)

    rng = np.random.default_rng(42)
    obs = abs(usd[disc & first].mean() - usd[disc & ~first].mean())
    lab = first[disc].copy()
    hits = 0
    for _ in range(4000):
        rng.shuffle(lab)
        if abs(usd[disc][lab].mean() - usd[disc][~lab].mean()) >= obs:
            hits += 1
    L.append("")
    L.append("  permutation on the discovery half, first bar against the rest: gap %s a trade, p = %.4f"
             % ("{:+,.0f}".format(usd[disc & first].mean() - usd[disc & ~first].mean()), hits / 4000))
    L.append("  ONE rule was tested here, chosen by round 15b rather than by searching this table, so there is no")
    L.append("  multiple-comparisons discount to apply - but the rule was still found by looking at these trades.")
    L.append("  The holdout and lockbox columns are the evidence; the discovery column is where it came from.")
    print("\n".join(L[-4:]), flush=True)
    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
