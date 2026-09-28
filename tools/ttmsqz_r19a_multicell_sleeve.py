"""TTM round 19a - IDEA 1, the multi-cell sleeve (tools/TTM_R19_PREREG.txt).

Pre-registration executed exactly as written: frozen #299/ES30N crown settings, identical on
every cell (no re-tuning per cell), on ES 30m / ES 15m / NQ 30m / NQ 15m RTH, ADJ_ masters
(source db_adj_rth, named explicitly - never an unpinned lookup). Window 2010-06-07..2026-06-30,
lockbox from 2025-07-01. Costs ES 0.363 pts / $50, NQ 0.533 pts / $20, one contract.

Two parity checks come first, printed to the log:
  1. ES 30m on the NO-ADJUST master (db_noadj_rth) must reproduce run #299: 359 trades, $51,709.
  2. The #459 twin cell (TTMSQZ_3_0_ES30SSOF2.py, kc_mult 1.5, eod_cutoff 1) on the ES 30m ADJ
     master should equal the roll-guarded #369 cell: 355 trades, $72,716.

Then the four sleeve cells, the 4-cell sleeve, the 2-cell (ES30+NQ30) sleeve, and the twin itself
(same data, same yardstick) are all scored on the pre-registered yardstick, computed identically
on DAILY P&L (summed by exit date, no-trade days = 0 within the stretch), WF and LB apart:
trades, net $, worst drawdown valued daily, MAR, ROC@$30k (=30 x MAR), Sortino, profit factor,
and for LB also the net without its single biggest trade. Sleeve daily-P&L correlation to the
cached NQ book legs (ORB_234 + ENGUQ_309) is reported once per sleeve over the overlapping days.

Verdict: PASS BAR (a)-(e) from IDEA 1, clause by clause, for the 4-cell sleeve AND the 2-cell
sleeve. Nothing crowned here - this is a read-only triage scan.

Output: tools/data/ttmsqz_r19a_multicell_sleeve.txt
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest as engine_run

DATE_FROM, LB_FROM, DATE_TO = "2010-06-07", "2025-07-01", "2026-06-30"
WF_END = "2025-06-30"     # day before LB_FROM - the pre-lockbox stretch is inclusive of this day
COST = {"ES": 0.363, "NQ": 0.533}
MULT = {"ES": 50.0, "NQ": 20.0}

CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
             exit_mode="fade", fade_bars=1, stop_atr=1.5, eod_cutoff=1, gate_tf_min=60,
             gate_mode="sq_on", gate_len=20, gate_bars=2, gate_ratio=1.0, gate_fired_k=3,
             direction="both")

CELLS = [("ES", "30m"), ("ES", "15m"), ("NQ", "30m"), ("NQ", "15m")]

LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r19a_multicell_sleeve.txt")
BOOK_LEGS = os.path.join(ROOT, "tools", "data", "book_crown_refresh_legs.npz")

L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


def years_between(d0, d1):
    """Inclusive calendar-day span, in years (365.25-day convention, matches the
    family's other harnesses, e.g. tools/ttmsqz_r15d_fade2_across_bases.py YRS)."""
    return ((pd.Timestamp(d1) - pd.Timestamp(d0)).days + 1) / 365.25


WF_YEARS = years_between(DATE_FROM, WF_END)
LB_YEARS = years_between(LB_FROM, DATE_TO)


def load_cell(strategy_file, inst, tf, params, source="db_adj_rth"):
    """Run one cell over the full pre-registered window, ADJ master, cost-applied. Returns
    (trades[(eb,xb,pnl_pts,side,entry_px,exit_px)], index, mult, num_trades, total_pnl_pts)."""
    res = engine_run(strategy_file, instrument=inst, timeframe=tf, session="rth", source=source,
                      params=params, cost_pts=COST[inst], date_from=DATE_FROM, date_to=DATE_TO,
                      return_trades=True)
    master = find_master(inst, tf, "rth", source)
    arrays = load_master_arrays(master, date_from=DATE_FROM, date_to=DATE_TO)
    idx = pd.DatetimeIndex(arrays["index"]).tz_localize(None)
    trades = res["trades"] if res else []
    return trades, idx, MULT[inst]


def trade_dollars(trades, idx, mult):
    """Per-trade (exit_date, dollars) list. Exit date = exit bar's timestamp, normalized -
    same convention as tools/book_crown_refresh.py leg_daily()."""
    out = []
    for t in trades:
        eb, xb, pts = int(t[0]), int(t[1]), float(t[2])
        d = idx[xb].normalize()
        out.append((d, pts * mult))
    return out


def daily_series(td_list):
    """(date -> summed dollars) pd.Series, one row per day that had at least one trade."""
    if not td_list:
        return pd.Series(dtype=float)
    df = pd.DataFrame(td_list, columns=["date", "usd"])
    return df.groupby("date")["usd"].sum().sort_index()


def full_calendar(idx_list, d0, d1):
    """Union of trading-day dates across the given indices, restricted to [d0, d1]."""
    days = set()
    for idx in idx_list:
        d = idx.normalize()
        days.update(d[(d >= pd.Timestamp(d0)) & (d <= pd.Timestamp(d1))].unique().tolist())
    return pd.DatetimeIndex(sorted(days))


def zero_fill(s, cal):
    """Daily $ series reindexed onto the full trading-day calendar, no-trade days = 0."""
    return s.reindex(cal, fill_value=0.0)


def stretch_stats(td_list, cal, d0, d1):
    """The pre-registered yardstick for one stretch [d0,d1], on daily P&L (zero-filled).
    Returns dict: n, net, dd, mar, roc, sortino, pf, lb_net_ex_biggest (None outside LB use)."""
    cal_s = cal[(cal >= pd.Timestamp(d0)) & (cal <= pd.Timestamp(d1))]
    trades_s = [(d, u) for d, u in td_list if pd.Timestamp(d0) <= d <= pd.Timestamp(d1)]
    n = len(trades_s)
    s = daily_series(trades_s)
    s = zero_fill(s, cal_s)
    net = float(s.sum())
    # Drawdown seeded from a FLAT account (peak_from_flat=True convention, matching
    # augur_engine.engine._apply_costs / wf_oos_block): the stretch starts at $0, not at
    # the first day's P&L, so a stretch that opens with a loss reports that loss as
    # drawdown instead of silently resetting its own peak to it.
    cum = np.concatenate([[0.0], s.cumsum().values])
    peak = np.maximum.accumulate(cum)
    dd = float((peak - cum).max()) if len(cum) else 0.0
    yrs = years_between(d0, d1)
    mar = (net / yrs) / dd if dd > 1e-9 else float("inf") if net > 0 else 0.0
    roc = 30.0 * mar
    mean = float(s.mean()) if len(s) else 0.0
    downside = np.minimum(s.values, 0.0)
    dd_dev = float(np.sqrt(np.mean(downside ** 2))) if len(s) else 0.0
    sortino = (mean / dd_dev * np.sqrt(252.0)) if dd_dev > 1e-9 else (float("inf") if mean > 0 else 0.0)
    gw = float(s[s > 0].sum()); gl = float(-s[s < 0].sum())
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    biggest = max((u for _, u in trades_s), default=0.0)
    net_ex_biggest = net - biggest
    return dict(n=n, net=net, dd=dd, mar=mar, roc=roc, sortino=sortino, pf=pf,
                net_ex_biggest=net_ex_biggest, yrs=yrs)


def row(label, wf, lb):
    emit("%s" % label)
    emit("  WF  n=%4d  net=$%11s  DD=$%9s  MAR=%6.3f  ROC@30k=%7.1f%%  Sortino=%6.2f  PF=%6.2f"
         % (wf["n"], "{:,.0f}".format(wf["net"]), "{:,.0f}".format(wf["dd"]), wf["mar"], wf["roc"],
            min(wf["sortino"], 99), min(wf["pf"], 99)))
    emit("  LB  n=%4d  net=$%11s  DD=$%9s  MAR=%6.3f  ROC@30k=%7.1f%%  Sortino=%6.2f  PF=%6.2f  "
         "netExBiggest=$%s"
         % (lb["n"], "{:,.0f}".format(lb["net"]), "{:,.0f}".format(lb["dd"]), lb["mar"], lb["roc"],
            min(lb["sortino"], 99), min(lb["pf"], 99), "{:,.0f}".format(lb["net_ex_biggest"])))


def corr_to_book(sleeve_td, cal, book_combined):
    """Pearson correlation of the sleeve's zero-filled daily $ vs the cached book legs'
    zero-filled combined daily $, on the overlap of the two date ranges."""
    s = zero_fill(daily_series(sleeve_td), cal)
    bmin, bmax = book_combined.index.min(), book_combined.index.max()
    smin, smax = cal.min(), cal.max()
    lo, hi = max(bmin, smin), min(bmax, smax)
    if lo > hi:
        return float("nan"), 0
    overlap_cal = cal[(cal >= lo) & (cal <= hi)]
    a = zero_fill(s, overlap_cal).values
    b = zero_fill(book_combined, overlap_cal).values
    if a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan"), len(overlap_cal)
    return float(np.corrcoef(a, b)[0, 1]), len(overlap_cal)


def main():
    emit("TTM ROUND 19a - IDEA 1, the multi-cell sleeve (tools/TTM_R19_PREREG.txt)")
    emit("window %s..%s, lockbox from %s; ADJ_ masters (source db_adj_rth), RTH, one contract"
         % (DATE_FROM, DATE_TO, LB_FROM))
    emit("costs: ES 0.363 pts / $50/pt; NQ 0.533 pts / $20/pt")
    emit("crown (frozen, identical every cell): %s" % CROWN)
    emit("")

    # ---------------------------------------------------------------- parity checks
    emit("PARITY CHECK 1 - ES 30m, NO-ADJUST master (db_noadj_rth), #299 crown -> expect 359 trades, $51,709 net")
    tr, idx, mult = load_cell("TTMSQZ_3_0.py", "ES", "30m", CROWN, source="db_noadj_rth")
    n1 = len(tr); net1 = sum(t[2] for t in tr) * mult
    match1 = (n1 == 359) and (abs(net1 - 51709) < 1.0)
    emit("  actual: %d trades, $%s net -> %s" % (n1, "{:,.2f}".format(net1), "MATCH" if match1 else "NO MATCH"))
    emit("")

    emit("PARITY CHECK 2 - ES 30m ADJ, #459 twin cell (TTMSQZ_3_0_ES30SSOF2.py, kc_mult 1.5, "
         "eod_cutoff 1) -> expect 355 trades, $72,716 net (equals the roll-guarded #369 cell "
         "on back-adjusted data)")
    tr459, idx459, mult459 = load_cell("TTMSQZ_3_0_ES30SSOF2.py", "ES", "30m",
                                        dict(kc_mult=1.5, eod_cutoff=1), source="db_adj_rth")
    n2 = len(tr459); net2 = sum(t[2] for t in tr459) * mult459
    match2 = (n2 == 355) and (abs(net2 - 72716) < 1.0)
    emit("  actual: %d trades, $%s net -> %s" % (n2, "{:,.2f}".format(net2), "MATCH" if match2 else "NO MATCH"))
    emit("")

    # ---------------------------------------------------------------- the four cells + twin
    cell_data = {}     # (inst,tf) -> (trades_dollars list, idx)
    for inst, tf in CELLS:
        tr, idx, mult = load_cell("TTMSQZ_3_0.py", inst, tf, CROWN, source="db_adj_rth")
        td = trade_dollars(tr, idx, mult)
        cell_data[(inst, tf)] = (td, idx)

    twin_td = trade_dollars(tr459, idx459, mult459)

    all_idx = [d[1] for d in cell_data.values()] + [idx459]
    cal = full_calendar(all_idx, DATE_FROM, DATE_TO)

    emit("=" * 100)
    emit("PER-CELL YARDSTICK (WF = %s..%s, %.3f yrs; LB = %s..%s, %.3f yrs)"
         % (DATE_FROM, WF_END, WF_YEARS, LB_FROM, DATE_TO, LB_YEARS))
    emit("=" * 100)
    cell_stats = {}
    for inst, tf in CELLS:
        td, _ = cell_data[(inst, tf)]
        wf = stretch_stats(td, cal, DATE_FROM, WF_END)
        lb = stretch_stats(td, cal, LB_FROM, DATE_TO)
        cell_stats[(inst, tf)] = (wf, lb)
        row("%s %s cell" % (inst, tf), wf, lb)
        emit("")

    twin_wf = stretch_stats(twin_td, cal, DATE_FROM, WF_END)
    twin_lb = stretch_stats(twin_td, cal, LB_FROM, DATE_TO)
    row("TWIN - #459 cell (TTMSQZ_3_0_ES30SSOF2.py, ES 30m ADJ)", twin_wf, twin_lb)
    emit("")

    # ---------------------------------------------------------------- sleeves
    sleeve4_td = []
    for inst, tf in CELLS:
        sleeve4_td.extend(cell_data[(inst, tf)][0])
    sleeve2_td = []
    for inst, tf in [("ES", "30m"), ("NQ", "30m")]:
        sleeve2_td.extend(cell_data[(inst, tf)][0])

    s4_wf = stretch_stats(sleeve4_td, cal, DATE_FROM, WF_END)
    s4_lb = stretch_stats(sleeve4_td, cal, LB_FROM, DATE_TO)
    s2_wf = stretch_stats(sleeve2_td, cal, DATE_FROM, WF_END)
    s2_lb = stretch_stats(sleeve2_td, cal, LB_FROM, DATE_TO)

    emit("=" * 100)
    emit("SLEEVES")
    emit("=" * 100)
    row("4-CELL SLEEVE (ES30+ES15+NQ30+NQ15, one contract each)", s4_wf, s4_lb)
    emit("")
    row("2-CELL SLEEVE (ES30+NQ30, one contract each)", s2_wf, s2_lb)
    emit("")

    # ---------------------------------------------------------------- correlation to the NQ book legs
    emit("=" * 100)
    emit("DAILY-P&L CORRELATION TO THE NQ BOOK LEGS (ORB_234 + ENGUQ_309, cached daily P&L)")
    emit("=" * 100)
    z = np.load(BOOK_LEGS, allow_pickle=True)
    orb = pd.Series(z["ORB_234_v"], index=pd.DatetimeIndex(z["ORB_234_d"]))
    enguq = pd.Series(z["ENGUQ_309_v"], index=pd.DatetimeIndex(z["ENGUQ_309_d"]))
    book_combined = orb.add(enguq, fill_value=0.0).sort_index()

    c4, n4 = corr_to_book(sleeve4_td, cal, book_combined)
    c2, n2o = corr_to_book(sleeve2_td, cal, book_combined)
    emit("  4-cell sleeve vs ORB_234+ENGUQ_309: r = %.3f (%d overlapping trading days)" % (c4, n4))
    emit("  2-cell sleeve vs ORB_234+ENGUQ_309: r = %.3f (%d overlapping trading days)" % (c2, n2o))
    emit("")

    # ---------------------------------------------------------------- verdict
    emit("=" * 100)
    emit("VERDICT - PASS BAR (a)-(e), IDEA 1 - THE MULTI-CELL SLEEVE")
    emit("=" * 100)

    def clause_a(wf, lb):
        ok = (wf["n"] >= 100) and (lb["n"] >= 50)
        return ok, "WF n=%d (need >=100), LB n=%d (need >=50)" % (wf["n"], lb["n"])

    def clause_b(wf, lb, twf, tlb):
        ok = (wf["roc"] >= twf["roc"]) and (lb["roc"] >= tlb["roc"])
        return ok, ("WF ROC@30k %.1f%% vs twin %.1f%%; LB ROC@30k %.1f%% vs twin %.1f%%"
                     % (wf["roc"], twf["roc"], lb["roc"], tlb["roc"]))

    def clause_c(wf, lb, twf, tlb):
        ok = (wf["sortino"] >= twf["sortino"]) and (lb["sortino"] >= tlb["sortino"])
        return ok, ("WF Sortino %.2f vs twin %.2f; LB Sortino %.2f vs twin %.2f"
                     % (wf["sortino"], twf["sortino"], lb["sortino"], tlb["sortino"]))

    def clause_d(lb):
        ok = lb["net_ex_biggest"] > 0
        return ok, "LB net ex-biggest-trade $%s" % "{:,.0f}".format(lb["net_ex_biggest"])

    def clause_e(corr):
        ok = (not np.isnan(corr)) and (corr <= 0.30)
        return ok, "correlation to book legs r=%.3f (need <=0.30)" % corr

    for label, wf, lb, corr in (
        ("4-CELL SLEEVE", s4_wf, s4_lb, c4),
        ("2-CELL SLEEVE (ES30+NQ30)", s2_wf, s2_lb, c2),
    ):
        emit("-- %s --" % label)
        oa, ta = clause_a(wf, lb)
        ob, tb = clause_b(wf, lb, twin_wf, twin_lb)
        oc, tc = clause_c(wf, lb, twin_wf, twin_lb)
        od, td_ = clause_d(lb)
        oe, te = clause_e(corr)
        emit("  (a) %s - trade count: %s" % ("PASS" if oa else "FAIL", ta))
        emit("  (b) %s - ROC@30k vs twin: %s" % ("PASS" if ob else "FAIL", tb))
        emit("  (c) %s - Sortino vs twin: %s" % ("PASS" if oc else "FAIL", tc))
        emit("  (d) %s - LB profitable ex-biggest-trade: %s" % ("PASS" if od else "FAIL", td_))
        emit("  (e) %s - book-leg correlation: %s" % ("PASS" if oe else "FAIL", te))
        overall = oa and ob and oc and od and oe
        emit("  OVERALL: %s" % ("PASS" if overall else "FAIL"))
        emit("")

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("log -> tools/data/ttmsqz_r19a_multicell_sleeve.txt")


if __name__ == "__main__":
    main()
