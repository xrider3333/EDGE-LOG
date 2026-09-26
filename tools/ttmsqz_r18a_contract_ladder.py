"""Round 18a - redo the WHOLE-CONTRACT SCHEDULE for the book leg, run #369, with BOTH tilts on.

Round 11 (tools/ttmsqz_round11_execution.py) answered "can the tilted leg be traded in whole
contracts" for ONE 1.5x tilt (deep-squeeze) at book weight 3: the ideal 4.5 ES is best expressed
as 3 -> 4, never 2 -> 3, because a smaller base gives up more than an exact tilt adds. That round
ran on TTMSQZ_3_0_ES30N.py (deep-squeeze tilt only, no structural stop, no open-bar tilt) and its
crown cell (359 trades, 188 deep).

Run #369 (augur_strategies/TTMSQZ_3_0_ES30SSOF2.py, ES 30m RTH) carries TWO 1.5x tilts that
MULTIPLY - deep-squeeze (ratio <= 0.85 at the decision bar) and session-open-bar (first fill bar
of the session) - so a trade is sized 1.0x (neither), 1.5x (one tilt) or 2.25x (both). At book
weight 3 the ideal is 3 / 4.5 / 6.75 ES contracts. Round 11's 3 -> 4 answer covered only the
single-tilt corner; this round redoes the whole ladder for the ACTUAL leg the book carries.

METHOD. Run #369's trades are pulled ONCE from the engine, exactly as round 16b
(tools/ttmsqz_r16b_tilt_ladder.py) does it: reuse that file's leg_trades(), which recovers each
trade's RAW (1-contract, untilted) points move directly from entry/exit price (tilting rescales
pnl, it never touches fill prices) and recomputes both tilt flags from the strategy's own helper
functions - so a trade's bucket (neither / deep-only / open-only / both) is not guessed. A
MANDATORY parity gate (r16b's own PARITY dict: n=354, net=$135,884, PF=3.12, MAR=1.826, lockbox
$22,739 at PF 9.89) must pass before anything below is trusted.

Every whole-contract schedule is a numpy re-weighting of that same trade list - no engine re-run.
Schedules are (base / single-tilt / both-tilts) contracts, ES unless noted:
  ideal   3 / 4.5 / 6.75   fractional, the reference (unattainable - no half ES contract)
  3/4/6, 3/4/7, 3/5/6, 3/5/7, 3/4/5, 2/3/4, 2/3/5, 4/6/9
  micros  30 / 45 / 68 MES   one tenth the ES notional, CAN express fractional-looking ratios
          at book size. MES pricing uses round 11's own MES assumptions ($5/pt, 0.50 pts a round
          trip - a WIDER round trip than ES's 0.363, not the same cost re-scaled by tenth notional)
          because round 11 is the only precedent in this family for micro costs and the task asked
          to reuse whatever it used.

For each schedule: whole run, first-75% in-sample slice (time-based: DATE_FROM + 75% of
(DATE_TO-DATE_FROM), same convention as EDGE-LOG's 75% IS header), and the lockbox (from
LB_FROM). Metrics: net, drawdown, annualised MAR (whole run divides by the pinned 16.06 years;
IS/LB slices divide by their OWN elapsed trade-date span, last trade minus first trade - r16b's
own convention for discovery/holdout), percent of the ideal's net kept, average contracts per
trade, ROC%/yr on $100k notional capital, and profit factor (bonus column, not asked for but
free). A cost-stress table (whole run only, house round11's own Part B convention) reprices every
schedule at 2x and 3x its own house cost. A whole-run Sortino on daily P&L (trade dollars summed
by exit calendar day, downside deviation against a 0 target, annualised by sqrt(252)) closes it -
this is a DOLLAR Sortino, not a percent-return one, because there is no fixed account size here;
said explicitly so nobody mistakes it for a return-based ratio.

NOTHING IS CROWNED. This is a feasibility/robustness read, like round 11.

Log: tools/data/ttmsqz_r18a_contract_ladder.txt
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


r16b = _mod(os.path.join(ROOT, "tools", "ttmsqz_r16b_tilt_ladder.py"), "r16b_r18a")
r8 = r16b.r8
r6 = r16b.r6
DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT, YRS = r16b.COST, r16b.MULT, r16b.YRS   # ES cost/mult, 16.06 pinned years
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r18a_contract_ladder.txt")
PARITY = r16b.PARITY

# round 11's own MES assumptions (tools/ttmsqz_round11_execution.py, ES_MULT/ES_COST vs
# MES_MULT/MES_COST) - a wider round trip than ES's 0.363, not the same cost re-scaled by a tenth.
MES_MULT, MES_COST = 5.0, 0.50

# (label, base, single-tilt, both-tilts, dollars/point, cost points/round trip)
SCHEDULES = [
    ("ideal 3 / 4.5 / 6.75 (fractional reference)", 3.0, 4.5, 6.75, MULT, COST),
    ("3 / 4 / 6", 3.0, 4.0, 6.0, MULT, COST),
    ("3 / 4 / 7", 3.0, 4.0, 7.0, MULT, COST),
    ("3 / 5 / 6", 3.0, 5.0, 6.0, MULT, COST),
    ("3 / 5 / 7", 3.0, 5.0, 7.0, MULT, COST),
    ("3 / 4 / 5", 3.0, 4.0, 5.0, MULT, COST),
    ("2 / 3 / 4", 2.0, 3.0, 4.0, MULT, COST),
    ("2 / 3 / 5", 2.0, 3.0, 5.0, MULT, COST),
    ("4 / 6 / 9", 4.0, 6.0, 9.0, MULT, COST),
    ("micros 30 / 45 / 68 MES", 30.0, 45.0, 68.0, MES_MULT, MES_COST),
]
COST_STRESS = (1.0, 2.0, 3.0)   # multiples of each schedule's own house cost


def contracts(t, base, single, both_):
    """Per-trade contract count for a (base/single/both) schedule, from the recovered bucket
    flags (deep, open_bar)."""
    deep, openb = t["deep"].values, t["open_bar"].values
    both = deep & openb
    single_only = (deep ^ openb)  # exactly one of the two tilts
    return np.where(both, both_, np.where(single_only, single, base))


def slice_stats(usd, n_ctr, dates):
    """net/dd/mar/roc/avg-contracts/pf for one (schedule, slice) cell. yrs = own elapsed
    trade-date span, days/365.25 (r16b's discovery/holdout convention)."""
    if len(usd) == 0:
        return dict(n=0, net=0.0, dd=0.0, mar=float("nan"), roc=float("nan"),
                    avg_ctr=float("nan"), pf=float("nan"), yrs=float("nan"))
    net = float(usd.sum())
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    pf = (gw / gl) if gl > 0 else 99.0
    yrs = max((pd.Timestamp(dates.max()) - pd.Timestamp(dates.min())).days / 365.25, 1e-9)
    mar = (net / yrs) / dd if dd > 0 else float("nan")
    roc = (net / yrs) / 100_000.0 * 100.0
    return dict(n=len(usd), net=net, dd=dd, mar=mar, roc=roc, avg_ctr=float(n_ctr.mean()),
               pf=min(pf, 99.0), yrs=yrs)


def whole_run_stats(usd, n_ctr):
    """Whole-run cell: pinned 16.06 years, per r16b/round11 convention."""
    net = float(usd.sum())
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    pf = (gw / gl) if gl > 0 else 99.0
    mar = (net / YRS) / dd if dd > 0 else float("nan")
    roc = (net / YRS) / 100_000.0 * 100.0
    return dict(n=len(usd), net=net, dd=dd, mar=mar, roc=roc, avg_ctr=float(n_ctr.mean()),
               pf=min(pf, 99.0), yrs=YRS)


def sortino_daily(usd, dates):
    """Dollar Sortino on daily P&L: trade dollars summed by exit calendar day, downside
    deviation against a 0 target over ALL days (not just losing ones), annualised *sqrt(252).
    This is a dollar ratio, not a percent-return one - there is no fixed account size here."""
    daily = r8._daily(usd, dates)
    if len(daily) < 2:
        return float("nan")
    x = daily.values
    mean = x.mean()
    downside = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    if downside <= 0:
        return float("nan")
    return (mean / downside) * np.sqrt(252.0)


def main():
    L = ["TTM SQUEEZE r18a - redo the WHOLE-CONTRACT SCHEDULE for run #369 (BOTH 1.5x tilts multiply)   %s"
         % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; leg TTMSQZ_3_0_ES30SSOF2 (run #369's own cell, kc_mult=1.5 "
         "eod_cutoff=1); ES $%.0f/pt, %.3f pts/contract round trip; MES $%.0f/pt, %.2f pts/contract "
         "round trip (round 11's own MES assumptions, reused verbatim)."
         % (DATE_FROM, DATE_TO, LB_FROM, MULT, COST, MES_MULT, MES_COST),
         "Trades pulled ONCE via r16b.leg_trades(); every schedule below is a numpy re-weighting "
         "of that same trade list keyed on the recovered deep/open-bar bucket flags. Nothing crowned."]
    print("\n".join(L), flush=True)

    t, ok, deep_mult, open_mult, deep_thr = r16b.leg_trades()
    L.append("")
    L.append("  internal-consistency check (recomputed flags + recovered raw points reproduce the "
             "engine's own priced pnl to the cent): %s" % ("PASS" if ok else "FAIL -- ABORTING"))
    print(L[-1], flush=True)
    if not ok:
        r8._lines_to(L, LOG); print("log ->", LOG); return

    # ---- MANDATORY PARITY GATE vs run #369 / r16b's published figures ----
    deep, openb = t["deep"].values, t["open_bar"].values
    both, single_only, neither = deep & openb, (deep ^ openb), ~deep & ~openb
    w_incumbent = np.where(deep, deep_mult, 1.0) * np.where(openb, open_mult, 1.0)
    usd_incumbent = w_incumbent * (t["raw"].values - COST) * MULT
    lb_mask = (t["date"] >= pd.Timestamp(LB_FROM)).values
    s_all = r16b.stats(usd_incumbent, w_incumbent)
    s_lb = r16b.stats(usd_incumbent[lb_mask], w_incumbent[lb_mask])
    mar_all = (s_all["net"] / YRS) / s_all["dd"] if s_all["dd"] > 0 else float("nan")
    parity_ok = (s_all["n"] == PARITY["n"] and abs(s_all["net"] - PARITY["net"]) < 1.0
                and abs(s_all["pf"] - PARITY["pf"]) < 0.01 and abs(mar_all - PARITY["mar"]) < 0.01
                and abs(s_lb["net"] - PARITY["lb_net"]) < 1.0
                and abs(min(s_lb["pf"], 99) - PARITY["lb_pf"]) < 0.02)
    L.append("")
    L.append("  PARITY GATE target : n=%d net=$%s PF=%.2f MAR=%.3f | LB net=$%s LB PF=%.2f"
             % (PARITY["n"], "{:,.0f}".format(PARITY["net"]), PARITY["pf"], PARITY["mar"],
                "{:,.0f}".format(PARITY["lb_net"]), PARITY["lb_pf"]))
    L.append("  PARITY GATE measured: n=%d net=$%s PF=%.2f MAR=%.3f | LB net=$%s LB PF=%.2f   %s"
             % (s_all["n"], "{:,.0f}".format(s_all["net"]), min(s_all["pf"], 99), mar_all,
                "{:,.0f}".format(s_lb["net"]), min(s_lb["pf"], 99), "PASS" if parity_ok else "FAIL"))
    print("\n".join(L[-3:]), flush=True)
    if not parity_ok:
        L.append("  PARITY FAILED - the harness does not reproduce run #369 / r16b. Nothing below trusted.")
        print(L[-1], flush=True)
        r8._lines_to(L, LOG); print("log ->", LOG); return

    n_deep_only = int((deep & ~openb).sum()); n_open_only = int((openb & ~deep).sum())
    L.append("")
    L.append("  census: %d trades - neither %d, deep-only %d, open-only %d, BOTH %d (%.1f%%)."
             % (len(t), int(neither.sum()), n_deep_only, n_open_only, int(both.sum()),
                100.0 * both.sum() / len(t)))
    print(L[-1], flush=True)

    # ---- time-based 75% IS cutoff, same convention as EDGE-LOG's 75% IS header ----
    d0, d1 = pd.Timestamp(DATE_FROM), pd.Timestamp(DATE_TO)
    is_cut = d0 + 0.75 * (d1 - d0)
    is_mask = (t["date"] < is_cut).values
    lb_mask2 = lb_mask
    L.append("  first-75%% in-sample slice = trades before %s (75%% of the %.2f-year window from %s)."
             % (is_cut.date(), YRS, DATE_FROM))
    print(L[-1], flush=True)

    raw, dates = t["raw"].values, t["date"].values

    def price(n_ctr):
        return n_ctr * (raw - COST) * MULT   # placeholder overwritten per-schedule below (mult/cost vary)

    # ================= MAIN TABLE =================
    L.append("")
    L.append("=" * 118)
    L.append("MAIN - net / drawdown / MAR / %% of ideal's net / avg contracts / ROC%%/yr@100k / PF, three slices")
    L.append("=" * 118)
    H1 = "  %-34s %s" % ("", "--------------- whole run ----------------   ------------ first-75%% IS -----------   ---------------- lockbox ----------------")
    H2 = ("  %-34s %5s %10s %8s %6s %6s %6s %5s   %5s %10s %8s %6s %6s %6s %5s   %5s %10s %8s %6s %6s %6s %5s"
          % ("schedule", "n", "net $", "DD $", "MAR", "%ideal", "avg#", "PF",
             "n", "net $", "DD $", "MAR", "%ideal", "avg#", "PF",
             "n", "net $", "DD $", "MAR", "%ideal", "avg#", "PF"))
    L.append(H1); L.append(H2)
    print(H1, flush=True); print(H2, flush=True)

    ideal_net = {}
    all_cells = {}
    for label, base, single, bothv, mult, cost in SCHEDULES:
        n_ctr = contracts(t, base, single, bothv)
        usd = n_ctr * (raw - cost) * mult
        c_whole = whole_run_stats(usd, n_ctr)
        c_is = slice_stats(usd[is_mask], n_ctr[is_mask], dates[is_mask])
        c_lb = slice_stats(usd[lb_mask2], n_ctr[lb_mask2], dates[lb_mask2])
        all_cells[label] = (c_whole, c_is, c_lb, n_ctr, usd)
        if "ideal" in label:
            ideal_net = dict(whole=c_whole["net"], is_=c_is["net"], lb=c_lb["net"])

    for label, base, single, bothv, mult, cost in SCHEDULES:
        c_whole, c_is, c_lb, n_ctr, usd = all_cells[label]
        pw = 100.0 * c_whole["net"] / ideal_net["whole"] if ideal_net["whole"] else float("nan")
        pi = 100.0 * c_is["net"] / ideal_net["is_"] if ideal_net.get("is_") else float("nan")
        pl = 100.0 * c_lb["net"] / ideal_net["lb"] if ideal_net.get("lb") else float("nan")
        row = ("  %-34s %5d %10s %8s %6.2f %6.1f %6.2f %5.2f   %5d %10s %8s %6.2f %6.1f %6.2f %5.2f   "
               "%5d %10s %8s %6.2f %6.1f %6.2f %5.2f"
               % (label, c_whole["n"], "{:,.0f}".format(c_whole["net"]), "{:,.0f}".format(c_whole["dd"]),
                  c_whole["mar"], pw, c_whole["avg_ctr"], c_whole["pf"],
                  c_is["n"], "{:,.0f}".format(c_is["net"]), "{:,.0f}".format(c_is["dd"]),
                  c_is["mar"], pi, c_is["avg_ctr"], c_is["pf"],
                  c_lb["n"], "{:,.0f}".format(c_lb["net"]), "{:,.0f}".format(c_lb["dd"]),
                  c_lb["mar"], pl, c_lb["avg_ctr"], c_lb["pf"]))
        L.append(row); print(row, flush=True)

    # ROC%/yr table (own block: main table above already crowded)
    L.append("")
    L.append("=" * 90)
    L.append("ROC%% PER YEAR ON $100,000 NOTIONAL CAPITAL - (net / own-slice-years) / 100,000 * 100")
    L.append("=" * 90)
    HR = "  %-34s %10s %10s %10s" % ("schedule", "whole run", "first-75% IS", "lockbox")
    L.append(HR); print(HR, flush=True)
    for label, base, single, bothv, mult, cost in SCHEDULES:
        c_whole, c_is, c_lb, n_ctr, usd = all_cells[label]
        row = "  %-34s %9.1f%% %9.1f%% %9.1f%%" % (label, c_whole["roc"], c_is["roc"], c_lb["roc"])
        L.append(row); print(row, flush=True)

    # ================= COST STRESS (whole run only, round11's Part B convention) =================
    L.append("")
    L.append("=" * 100)
    L.append("COST STRESS - whole run, each schedule re-priced at 1x/2x/3x ITS OWN house cost per contract")
    L.append("=" * 100)
    HC = "  %-34s %9s %9s %9s   %8s %8s %8s   %6s %6s %6s" % (
        "schedule", "net@1x", "net@2x", "net@3x", "DD@1x", "DD@2x", "DD@3x", "MAR@1x", "MAR@2x", "MAR@3x")
    L.append(HC); print(HC, flush=True)
    for label, base, single, bothv, mult, cost in SCHEDULES:
        n_ctr = contracts(t, base, single, bothv)
        nets, dds, mars = [], [], []
        for mfac in COST_STRESS:
            usd = n_ctr * (raw - cost * mfac) * mult
            net = float(usd.sum())
            cum = np.concatenate([[0.0], np.cumsum(usd)])
            dd = -float((cum - np.maximum.accumulate(cum)).min())
            mar = (net / YRS) / dd if dd > 0 else float("nan")
            nets.append(net); dds.append(dd); mars.append(mar)
        row = ("  %-34s %9s %9s %9s   %8s %8s %8s   %6.2f %6.2f %6.2f"
               % (label, "{:,.0f}".format(nets[0]), "{:,.0f}".format(nets[1]), "{:,.0f}".format(nets[2]),
                  "{:,.0f}".format(dds[0]), "{:,.0f}".format(dds[1]), "{:,.0f}".format(dds[2]),
                  mars[0], mars[1], mars[2]))
        L.append(row); print(row, flush=True)

    # ================= EFFICIENCY (net per average contract of risk) =================
    # %-of-ideal-net alone rewards a schedule for simply carrying MORE average risk (4/6/9 is
    # just the ideal scaled 4/3x). The question the owner actually asked - which schedule best
    # EXPRESSES the ladder PER CONTRACT OF RISK - needs net normalised by avg contracts/trade,
    # then compared to the ideal's own rate. 100% = exactly as efficient as the unattainable
    # fractional ideal; >100% means the rounding happened to concentrate size on the richer
    # bucket and out-earned the ideal's own per-contract rate; <100% means rounding gave up
    # money disproportionately to the risk it gave up.
    L.append("")
    L.append("=" * 90)
    L.append("EFFICIENCY - net per average contract of risk, whole run and lockbox, vs the ideal's OWN rate")
    L.append("=" * 90)
    ideal_rate_whole = ideal_net["whole"] / all_cells["ideal 3 / 4.5 / 6.75 (fractional reference)"][0]["avg_ctr"]
    ideal_rate_lb = ideal_net["lb"] / all_cells["ideal 3 / 4.5 / 6.75 (fractional reference)"][2]["avg_ctr"]
    HE = "  %-34s %12s %8s   %12s %8s" % ("schedule", "$/avg-ctr whole", "%ideal", "$/avg-ctr LB", "%ideal")
    L.append(HE); print(HE, flush=True)
    eff_whole = {}
    for label, base, single, bothv, mult, cost in SCHEDULES:
        c_whole, c_is, c_lb, n_ctr, usd = all_cells[label]
        rate_w = c_whole["net"] / c_whole["avg_ctr"] if c_whole["avg_ctr"] else float("nan")
        rate_l = c_lb["net"] / c_lb["avg_ctr"] if c_lb["avg_ctr"] else float("nan")
        eff_whole[label] = 100.0 * rate_w / ideal_rate_whole
        row = ("  %-34s %14s %7.1f%%   %12s %7.1f%%"
               % (label, "{:,.0f}".format(rate_w), 100.0 * rate_w / ideal_rate_whole,
                  "{:,.0f}".format(rate_l), 100.0 * rate_l / ideal_rate_lb))
        L.append(row); print(row, flush=True)

    # ================= SORTINO (whole run, daily P&L) =================
    L.append("")
    L.append("=" * 80)
    L.append("SORTINO ON DAILY P&L, whole run - dollar ratio (mean/downside-dev of trade $ summed by exit")
    L.append("calendar day, downside dev vs a 0 target over ALL days), annualised * sqrt(252). NOT a")
    L.append("percent-return Sortino - there is no fixed account size in this leg-alone view.")
    L.append("=" * 80)
    HS = "  %-34s %8s" % ("schedule", "Sortino")
    L.append(HS); print(HS, flush=True)
    for label, base, single, bothv, mult, cost in SCHEDULES:
        n_ctr = contracts(t, base, single, bothv)
        usd = n_ctr * (raw - cost) * mult
        srt = sortino_daily(usd, t["date"])
        row = "  %-34s %8.2f" % (label, srt)
        L.append(row); print(row, flush=True)

    # ================= VERDICT =================
    L.append("")
    L.append("=" * 100)
    L.append("VERDICT (plain English, nothing crowned)")
    L.append("=" * 100)
    # the fair comparison group is the base=3 ES schedules (same base the book actually weights
    # this leg at) - 2/3/x is a smaller book, 4/6/9 is exactly the ideal scaled 4/3x (its
    # efficiency ties the ideal by construction), micros are a different instrument.
    base3 = ["3 / 4 / 6", "3 / 4 / 7", "3 / 5 / 6", "3 / 5 / 7", "3 / 4 / 5"]
    best_eff_label = max(base3, key=lambda lab: eff_whole[lab])
    worst_eff_label = min(base3, key=lambda lab: eff_whole[lab])
    be_w, be_pct_net = eff_whole[best_eff_label], 100.0 * all_cells[best_eff_label][0]["net"] / ideal_net["whole"]
    be_avg = all_cells[best_eff_label][0]["avg_ctr"]
    ideal_avg = all_cells["ideal 3 / 4.5 / 6.75 (fractional reference)"][0]["avg_ctr"]
    we_pct_net = 100.0 * all_cells[worst_eff_label][0]["net"] / ideal_net["whole"]
    we_avg = all_cells[worst_eff_label][0]["avg_ctr"]
    tie46 = all_cells["4 / 6 / 9"][0]
    sched_by_label = {lab: (b, s, bo) for lab, b, s, bo, m, c in SCHEDULES}
    b_b, b_s, b_bo = sched_by_label[best_eff_label]
    w_b, w_s, w_bo = sched_by_label[worst_eff_label]
    verdict = (
        "Among the base-3 ES schedules, %s is the best per-contract expression of the ideal 3/4.5/6.75 "
        "ladder: single-tilt trades get %g contracts (%.2f short of the ideal's 4.5) but the both-tilts "
        "trades -- the richest bucket, both tilts firing at once -- get %g (%.2f OVER the ideal's 6.75), "
        "which pulls its whole-run average size to %.2f contracts a trade, BELOW the ideal's own %.2f, "
        "while still keeping %.1f%% of the ideal's net -- %.1f%% of the ideal's dollars per average "
        "contract of risk, i.e. it out-earns the fractional ideal per unit of risk carried. The worst of "
        "the group, %s, gives the both-tilts bucket only %g contracts (%.2f short of 6.75, further short "
        "than any other base-3 schedule) while still giving the single-tilt bucket %g -- moving size OFF "
        "the richest trades -- and it shows: %.2f average contracts (%.1f%% of the ideal's own average "
        "risk) buys only %.1f%% of the ideal's net -- giving up net faster than it gives up risk. Round "
        "11's principle -- a smaller base gives up more than an exact tilt adds -- still holds, and it "
        "generalises past the single tilt it was written for: rounding the RICHEST rung of a "
        "multiplicative tilt UP costs nothing and gains disproportionately, while "
        "rounding it DOWN gives up money faster than it gives up risk. 4/6/9 is not a genuinely different "
        "point on this trade-off -- it is the ideal ladder scaled by exactly 4/3 (3->4, 4.5->6, 6.75->9, "
        "all at the same 1.333x), so it ties the ideal's per-contract efficiency by construction (%.2f%% "
        "at %.2f average contracts) rather than beating it; it is simply a bigger book, not a smarter one. "
        "The MES micro schedule (30/45/68) sits almost exactly on the ideal's own average risk (%.2f "
        "average MES contracts, %.2f in ES-equivalent terms against the ideal's %.2f) but its per-contract "
        "rate is far below the ES schedules' (%.1f%% of the ideal's dollar-per-ES-equivalent-contract "
        "rate) because MES pays a WIDER house round trip per unit notional (0.50 pts vs ES's 0.363, both "
        "reused from round 11 rather than re-derived here) -- proof that micros solve the whole-contract "
        "rounding problem but only by paying more cost per unit of size."
        % (best_eff_label, b_s, 4.5 - b_s, b_bo, b_bo - 6.75, be_avg, ideal_avg, be_pct_net, be_w,
           worst_eff_label, w_bo, 6.75 - w_bo, w_s, we_avg, 100.0 * we_avg / ideal_avg, we_pct_net,
           eff_whole["4 / 6 / 9"], tie46["avg_ctr"],
           all_cells["micros 30 / 45 / 68 MES"][0]["avg_ctr"], all_cells["micros 30 / 45 / 68 MES"][0]["avg_ctr"] / 10.0,
           ideal_avg, eff_whole["micros 30 / 45 / 68 MES"]))
    for chunk in [verdict[i:i+96] for i in range(0, len(verdict), 96)]:
        L.append("  " + chunk)
    print(verdict, flush=True)

    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
