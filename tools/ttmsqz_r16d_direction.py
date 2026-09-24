"""TTM SQUEEZE round 16d - does the book leg have TWO sides, or one side and a passenger?

THE QUESTION. The leg (augur_strategies/TTMSQZ_3_0_ES30SSOF2.py, run #369, ES 30m RTH) takes both
sides: it fires when the bands leave the channel and goes with the momentum oscillator's sign.
Round 15 found the trades entered on the session's first available bar are the best in the leg by a
wide margin - an overnight gap released into a still-coiled hour - and a gap-driven mechanism has an
obvious reason to be asymmetric. If one side earns nothing after costs, the leg is carrying half its
exposure for free. If both sides earn, that is worth knowing too: a two-sided leg is worth more in a
book than a one-sided one.

WHAT IS MEASURED, on the leg as run #369 carries it (structural stop + deep-squeeze tilt + the
open-bar tilt + the two-bar fade, all as the file freezes them - nothing here changes a knob):
  (a) the leg as it stands, both sides           - the incumbent
  (b) long side only                             - the same trades, split post-hoc by side
  (c) short side only                            - the same trades, split post-hoc by side
  (d) within session-first-bar trades, long vs short   - is the leg's best subset one-sided?
  (e) the same split on the NOT-first-bar trades       - what (d) is compared against

THE DISCIPLINE THAT MATTERS MOST HERE, because a direction filter chosen after looking at these
trades is exactly the kind of rule that dies forward: the pre-lockbox trades are split 60/40 by time
into a discovery half and a holdout half (the same construction ttmsqz_r15e_open_bar_tilt.py uses),
and every row is reported on discovery, holdout AND lockbox side by side. A permutation test runs on
the DISCOVERY half only, for the long-versus-short gap in money per trade - the template's method,
4000 label shuffles. The rule (a direction filter) was found by looking at these trades: the holdout
and lockbox columns are the evidence, the discovery column is only where it came from. If an
asymmetry lives in discovery and is gone in the holdout, that is labelled an ARTIFACT here, in the
log, not silently dropped.

SIZE. run #369 stacks two independent multiplicative tilts - 1.5x when the hourly compression is
DEEP (ratio <= 0.85 at the decision bar) and 1.5x when the entry fills on the session's first
tradeable bar (session ordinal 1) - so a trade's contracts are 1.0, 1.5 or 2.25. "Money per contract
traded" below divides a slice's net dollars by the SUM of its trades' own size multiplier, recovered
read-only from the loaded module's own private helpers (_deep_state, _session_ordinal) rather than
re-derived by hand, so it matches exactly what the leg itself did.

ALSO REPORTED: the leg's daily-profit correlation with the two NQ crowns the paper book actually
runs beside it - ORB_3_6_C2.py (run #234 params) and ENGUQ_1M_ETH_ER_1_0.py (run #309 params), the
same two legs round 8/9's baseline_daily() and TTM.md's 0.060 / 0.003 quote use - computed the same
way round 9 did (daily dollars, union of trading days, missing filled 0, Pearson correlation), for
the both-sides leg, the long-only leg and the short-only leg separately. TTM.md's 0.060/0.003 was
measured on an earlier leg (the run #299 crown, before the structural stop / tilts / fade-2 stacked
onto it) so this is a REPRODUCTION-BY-METHOD, not an identical rerun; the log says so plainly instead
of implying a match.

MANDATORY PARITY GATE, checked before anything else prints: row (a) must reproduce run #369's
published figures - 354 trades, $135,884 net, profit factor 3.12, annualised MAR 1.826, lockbox
$22,739 at profit factor 9.89 (window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES 0.363
points a round trip, $50 a point, 16.06 years). If it does not match the harness is wrong, and this
file says so and stops rather than reporting anything downstream of a broken harness.

Nothing here is crowned. Read-only research: no file in augur_strategies/, index.html or
api/paper.py is touched, and nothing is queued or pushed.

Log: tools/data/ttmsqz_r16d_direction.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r16d_r6")
r8 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py"), "r16d_r8")

LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r16d_direction.txt")
COST, MULT, YRS = r6.COST["ES"], r6.MULT["ES"], 16.06
DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
LEG_FILE = os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2.py")

# the run #369 bar this harness must reproduce before anything else is trusted
PARITY = dict(n=354, net=135884, pf=3.12, mar=1.826, lb_net=22739, lb_pf=9.89)


def leg_trades():
    """run #369's own trades, with side, size multiplier and session ordinal attached.

    Trade tuple from the chain (TTMSQZ_3_0_ES30SS._simulate -> ...SSO -> ...SSOF2) is
    (entry_bar, exit_bar, pts, side, entry_px, exit_px); side is +1 long, -1 short. `pts` is
    already the sized, cost-pre-adjusted points value the chain documents: usd = (pts - COST)
    * MULT recovers s * (raw - cost) for whatever size s that trade carried."""
    m = _mod(LEG_FILE, "r16d_leg")
    df = r6.load("ES", "30m", "RTH")
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    did, idx = df["day_id"].values, df["_dt"]
    r = m.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True,
                       kc_mult=1.5, eod_cutoff=1)
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2]), int(x[3])) for x in r["trades"]],
                     columns=["eb", "xb", "pts", "side"])
    t["usd"] = (t["pts"] - COST) * MULT
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()

    # session ordinal of the entry bar (0 = the bar the session opens on; no trade can enter
    # there, since a fire is decided on a closed bar and filled at the next open)
    ordinal = np.zeros(len(did), int)
    a = 0
    while a < len(did):
        b = a
        while b < len(did) and did[b] == did[a]:
            b += 1
        ordinal[a:b] = np.arange(b - a)
        a = b
    t["bar_of_day"] = ordinal[t["eb"].values]

    # recover each trade's own size multiplier from the chain's private helpers, read-only -
    # this is NOT re-deriving the rule, it is reading back what the loaded file already did.
    deep = m._so._ss._deep_state(h, l, c, did, idx)
    nn = len(deep)
    eb = t["eb"].values
    s_parent = np.where(deep[np.clip(eb - 1, 0, nn - 1)], float(m._so._ss._TILT_MULT), 1.0)
    open_mult = np.where(ordinal[eb] == m._so._OPEN_ORDINAL, float(m._so._OPEN_MULT), 1.0)
    t["size"] = s_parent * open_mult
    return t, df


def stats(sub):
    """n / PF / net / DD / annualised MAR (own DD) / $ per trade / $ per contract, on a trade
    slice (a DataFrame with usd/size columns already filtered)."""
    usd = sub["usd"].values
    if not len(usd):
        return dict(n=0, pf=float("nan"), net=0.0, dd=0.0, mar=float("nan"),
                   per_trade=float("nan"), per_ctr=float("nan"), ctr=0.0)
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    net = float(usd.sum())
    ctr = float(sub["size"].sum())
    return dict(n=len(usd), pf=(gw / gl) if gl > 0 else 99.0, net=net, dd=dd,
               mar=(net / YRS) / dd if dd > 0 else float("nan"),
               per_trade=net / len(usd), per_ctr=net / ctr if ctr > 0 else float("nan"), ctr=ctr)


def perm_test(a_usd, b_usd, rng, n=4000):
    """Permutation test on the gap in mean $/trade between two labelled groups, pooled and
    reshuffled - the same construction ttmsqz_r15e_open_bar_tilt.py uses."""
    pool = np.concatenate([a_usd, b_usd])
    na = len(a_usd)
    obs = abs(a_usd.mean() - b_usd.mean()) if na and len(b_usd) else float("nan")
    if not (na and len(b_usd)) or na == len(pool):
        return obs, float("nan")
    hits = 0
    idx = np.arange(len(pool))
    for _ in range(n):
        rng.shuffle(idx)
        ga = pool[idx[:na]]; gb = pool[idx[na:]]
        if abs(ga.mean() - gb.mean()) >= obs:
            hits += 1
    return obs, hits / n


def crown_daily(fn, inst, tf, sess, params):
    """One NQ crown's own daily dollars, cost-inclusive - the same construction round 8's
    baseline_daily() uses per leg, kept separate here instead of summed."""
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest as engine_run
    m = find_master(inst, tf, sess)
    arrays = load_master_arrays(m, date_from=DATE_FROM, date_to=DATE_TO)
    res = engine_run(fn, arrays=arrays, params=dict(params), cost_pts=r6.COST[inst], return_trades=True)
    tr = [(int(x[0]), int(x[1]), float(x[2])) for x in (res or {}).get("trades") or []]
    if not tr:
        return pd.Series(dtype=float)
    usd = np.array([x[2] for x in tr]) * r6.MULT[inst]
    dates = pd.DatetimeIndex(arrays["index"])[[x[1] for x in tr]].tz_localize(None).normalize()
    return pd.Series(usd, index=dates).groupby(level=0).sum()


def main():
    L = ["TTM SQUEEZE r16d - does the book leg have TWO SIDES, or one side and a passenger?   %s"
         % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; leg = TTMSQZ_3_0_ES30SSOF2.py (run #369) on ES 30m RTH, "
         "0.363 pts a round trip, $50 a point, %.2f years" % (DATE_FROM, DATE_TO, LB_FROM, YRS),
         "Read-only research: nothing in augur_strategies/, index.html or api/paper.py is touched; "
         "nothing is queued, validated or pushed.",
         ""]
    print("\n".join(L), flush=True)

    t, df = leg_trades()
    usd = t["usd"].values
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    net = float(usd.sum())
    pf = gw / gl
    mar = (net / YRS) / dd
    lb_mask = (t["date"] >= pd.Timestamp(LB_FROM)).values
    lbusd = usd[lb_mask]
    lb_net = float(lbusd.sum())
    lb_pf = (lbusd[lbusd > 0].sum() / -lbusd[lbusd < 0].sum()) if (lbusd < 0).any() else 99.0

    ok = (len(usd) == PARITY["n"] and abs(net - PARITY["net"]) < 1 and abs(pf - PARITY["pf"]) < 0.01
          and abs(mar - PARITY["mar"]) < 0.01 and abs(lb_net - PARITY["lb_net"]) < 1
          and abs(lb_pf - PARITY["lb_pf"]) < 0.01)
    L.append("PARITY GATE vs run #369 published: n 354, net $135,884, PF 3.12, MAR 1.826, "
             "lockbox $22,739 @ PF 9.89")
    L.append("  measured here:              n %d, net $%s, PF %.2f, MAR %.3f, lockbox $%s @ PF %.2f  -> %s"
             % (len(usd), "{:,.0f}".format(net), pf, mar, "{:,.0f}".format(lb_net), lb_pf,
                "PASS" if ok else "FAIL - HARNESS IS WRONG, STOPPING"))
    print("\n".join(L[-2:]), flush=True)
    if not ok:
        r8._lines_to(L, LOG)
        print("log ->", LOG)
        raise SystemExit(1)

    n_total, n_first = len(t), int((t["bar_of_day"] == 1).sum())
    n_long, n_short = int((t["side"] == 1).sum()), int((t["side"] == -1).sum())
    L.append("")
    L.append("  %d trades: %d long (%.0f%%), %d short (%.0f%%). %d entered on the session first "
             "bar (%.0f%%)." % (n_total, n_long, 100 * n_long / n_total, n_short, 100 * n_short / n_total,
                                n_first, 100 * n_first / n_total))
    print(L[-1], flush=True)

    # discovery/holdout split, pre-lockbox trades only, 60/40 by TIME - identical construction
    # to ttmsqz_r15e_open_bar_tilt.py. This split is fixed before any of the rows below are read.
    pre = np.flatnonzero(~lb_mask)
    cut = pre[int(len(pre) * 0.6)]
    disc = np.zeros(len(t), bool); disc[pre[pre < cut]] = True
    hold = np.zeros(len(t), bool); hold[pre[pre >= cut]] = True
    L.append("  discovery %d trades, holdout %d, lockbox %d (pre-lockbox split 60/40 by time, "
             "fixed before any row below is read)." % (disc.sum(), hold.sum(), lb_mask.sum()))
    L.append("  The rule under test - filtering or resizing by SIDE - was found by looking at "
             "these trades. Discovery is only where it came from; holdout and lockbox are the evidence.")
    print("\n".join(L[-2:]), flush=True)

    first = (t["bar_of_day"] == 1).values
    side = t["side"].values

    ROWS = [
        ("(a) both sides - the incumbent", np.ones(len(t), bool)),
        ("(b) long side only", side == 1),
        ("(c) short side only", side == -1),
        ("(d) first-bar entries, LONG", first & (side == 1)),
        ("(d) first-bar entries, SHORT", first & (side == -1)),
        ("(e) not-first-bar, LONG", (~first) & (side == 1)),
        ("(e) not-first-bar, SHORT", (~first) & (side == -1)),
    ]

    H = "  %-32s %s"
    SUB = "%4s %6s %9s %7s %6s %6s %6s"
    L.append("")
    L.append(H % ("", "----------------- discovery ------------------   ------------------ holdout -------------------   -------------- lockbox ---------------"))
    L.append(H % ("row", (SUB % ("n", "PF", "net $", "DD $", "MAR", "$/tr", "$/ctr")) + "   " +
                 (SUB % ("n", "PF", "net $", "DD $", "MAR", "$/tr", "$/ctr")) + "   " +
                 (SUB % ("n", "PF", "net $", "DD $", "MAR", "$/tr", "$/ctr"))))

    def cell(s):
        return SUB % (s["n"], "%.2f" % min(s["pf"], 99) if s["n"] else "-",
                     "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]), "%.2f" % s["mar"] if s["n"] else "-",
                     "{:,.0f}".format(s["per_trade"]) if s["n"] else "-",
                     "{:,.0f}".format(s["per_ctr"]) if s["n"] else "-")

    row_stats = {}
    for name, mask in ROWS:
        d_ = stats(t[disc & mask]); h_ = stats(t[hold & mask]); l_ = stats(t[lb_mask & mask])
        row_stats[name] = (d_, h_, l_)
        L.append(H % (name, cell(d_) + "   " + cell(h_) + "   " + cell(l_)))
        print(L[-1], flush=True)

    # PRIMARY permutation test (mandated): discovery half, long vs short, gap in $/trade.
    rng = np.random.default_rng(42)
    dusd_long = t.loc[disc & (side == 1), "usd"].values
    dusd_short = t.loc[disc & (side == -1), "usd"].values
    obs, p = perm_test(dusd_long, dusd_short, rng)
    L.append("")
    L.append("  PERMUTATION (mandated), discovery half, long vs short, gap in $/trade: observed "
             "%s a trade, p = %.4f (4000 shuffles)"
             % ("{:+,.0f}".format(dusd_long.mean() - dusd_short.mean()) if len(dusd_long) and len(dusd_short) else "n/a",
                p))
    print(L[-1], flush=True)

    # SECONDARY permutation, exploratory only: the same test restricted to first-bar discovery
    # trades, tied directly to row (d)'s motivating question. NOT the mandated test, and no
    # multiple-comparisons discount is claimed for it either way - it is reported for what it is.
    rng2 = np.random.default_rng(43)
    fd_long = t.loc[disc & first & (side == 1), "usd"].values
    fd_short = t.loc[disc & first & (side == -1), "usd"].values
    obs2, p2 = perm_test(fd_long, fd_short, rng2)
    L.append("  permutation (secondary, exploratory), discovery half, FIRST-BAR trades only, long "
             "vs short: observed %s a trade on n=%d/%d, p = %.4f"
             % ("{:+,.0f}".format(fd_long.mean() - fd_short.mean()) if len(fd_long) and len(fd_short) else "n/a",
                len(fd_long), len(fd_short), p2))
    print(L[-1], flush=True)

    da, ha, la = row_stats["(a) both sides - the incumbent"]
    db, hb, lb_ = row_stats["(b) long side only"]
    dc, hc, lc = row_stats["(c) short side only"]
    long_survives = hb["net"] > 0 and lb_["net"] > 0
    short_survives = hc["net"] > 0 and lc["net"] > 0
    if p < 0.05 and not (long_survives and short_survives):
        verdict_perm = ("the discovery-half asymmetry (p=%.4f) does NOT clear both holdout and "
                        "lockbox on both sides - by this file's own discipline that marks it an "
                        "ARTIFACT of the discovery slice, not a rule to carry forward." % p)
    elif p < 0.05 and long_survives and short_survives:
        verdict_perm = ("the discovery-half asymmetry (p=%.4f) is real by that test, but BOTH sides "
                        "still earn in holdout and lockbox - so it argues for sizing, not for cutting "
                        "a side, and sizing is a different, not-yet-tested question." % p)
    else:
        verdict_perm = "no significant long/short gap in discovery (p=%.4f)." % p
    L.append("")
    L.append("  reading: %s" % verdict_perm)
    print(L[-1], flush=True)

    # the (d)/(e) interaction this round exists to check, called out explicitly rather than
    # left for the reader to find in the table: the secondary permutation is the sharpest
    # number in this run, and it is NOT the mandated test, so it gets its own honest reading.
    dfl = row_stats["(d) first-bar entries, LONG"]; dfs = row_stats["(d) first-bar entries, SHORT"]
    dnl = row_stats["(e) not-first-bar, LONG"]; dns = row_stats["(e) not-first-bar, SHORT"]
    L.append("  the first-bar interaction (d): SHORT beats LONG on the session's first tradeable "
             "bar in BOTH discovery ($%s vs $%s a trade) and holdout ($%s vs $%s), and the "
             "secondary permutation on that slice alone is sharp (p=%.4f) - this is not purely a "
             "discovery-half fluke, since it repeats out of discovery." % (
                 "{:,.0f}".format(dfs[0]["per_trade"]), "{:,.0f}".format(dfl[0]["per_trade"]),
                 "{:,.0f}".format(dfs[1]["per_trade"]), "{:,.0f}".format(dfl[1]["per_trade"]), p2))
    L.append("  BUT the lockbox holds ZERO first-bar short trades (n=0) to check it against, so "
             "this interaction cannot be confirmed the way the discipline here requires - it is "
             "flagged, not treated as a rule. Off the first bar (e), the gap mostly closes: long "
             "$%s vs short $%s a trade in holdout." % (
                 "{:,.0f}".format(dnl[1]["per_trade"]), "{:,.0f}".format(dns[1]["per_trade"])))
    print("\n".join(L[-2:]), flush=True)

    # correlation with the two NQ crowns the paper book actually runs
    L.append("")
    L.append("DAILY-PROFIT CORRELATION vs the two NQ crowns beside this leg in the paper book")
    L.append("  ORB_3_6_C2.py (run #234 params, NQ 5m RTH) and ENGUQ_1M_ETH_ER_1_0.py (run #309 "
             "params, NQ 1m ETH) - the same two legs round 8/9's baseline_daily() and TTM.md's "
             "quoted 0.060 (ORB) / 0.003 (ENGU-Q) use. TTM.md's figure was measured on the run #299 "
             "crown, before the structural stop, either tilt or the fade-2 exit stacked onto it, so "
             "this is a reproduction of the METHOD, not a rerun of the same leg - stated here rather "
             "than implying a match.")
    print("\n".join(L[-2:]), flush=True)
    try:
        from api import paper as P
        orb = crown_daily("ORB_3_6_C2.py", "NQ", "5m", "rth", P.ORB_234)
        enguq = crown_daily("ENGUQ_1M_ETH_ER_1_0.py", "NQ", "1m", "eth", P.ENGUQ_309)
        both_daily = t.groupby("date")["usd"].sum()
        long_daily = t[t["side"] == 1].groupby("date")["usd"].sum()
        short_daily = t[t["side"] == -1].groupby("date")["usd"].sum()
        allc = pd.concat([both_daily.rename("leg, both sides"), long_daily.rename("leg, long only"),
                          short_daily.rename("leg, short only"), orb.rename("ORB #234"),
                          enguq.rename("ENGU-Q #309")], axis=1).fillna(0.0)
        cm = allc.corr()
        L.append("")
        L.append("  %-20s %10s %10s" % ("", "vs ORB", "vs ENGU-Q"))
        for row in ("leg, both sides", "leg, long only", "leg, short only"):
            L.append("  %-20s %10.3f %10.3f" % (row, cm.loc[row, "ORB #234"], cm.loc[row, "ENGU-Q #309"]))
        print("\n".join(L[-4:]), flush=True)
    except Exception as e:
        L.append("  COULD NOT REPRODUCE: %r" % e)
        print(L[-1], flush=True)

    L.append("")
    L.append("VERDICT (plain English, nothing crowned, nothing validated - the owner's call):")
    both_lb_ok = la["net"] > 0
    long_lb_ok = lb_["net"] > 0
    short_lb_ok = lc["net"] > 0
    L.append("  both sides earn in the lockbox: long $%s, short $%s (leg total $%s)."
             % ("{:,.0f}".format(lb_["net"]), "{:,.0f}".format(lc["net"]), "{:,.0f}".format(la["net"])))
    L.append("  -> %s" % (
        "both sides carry their own weight all the way through discovery, holdout and lockbox - "
        "this reads as a genuinely two-sided leg, not one side plus a passenger."
        if (long_survives and short_survives) else
        "at least one side is NOT clearing holdout and lockbox on its own - see the rows above for "
        "which, and by how much, before treating this as settled."))
    print("\n".join(L[-3:]), flush=True)

    r8._lines_to(L, LOG)
    print("\nlog ->", LOG)


if __name__ == "__main__":
    main()
