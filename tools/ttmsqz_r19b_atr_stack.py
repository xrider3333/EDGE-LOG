"""TTM round 19b - IDEA 2 from tools/TTM_R19_PREREG.txt ("THE HONEST STACK ON THE ATR ENGINE").

Pre-registered mechanism: the structural-stop lineage's advantage was the same-bar gap-stop bug
(fixed 2026-09-27). Two OTHER validated changes to that lineage - 1.5x size on the session's
open-bar entry (run #368) and leaving on the second fading bar instead of the first (run #364) -
were validated there but never tried on the CLEAN engine, the ATR-stop TTMSQZ_3_0.py wrapped by
TTMSQZ_3_0_ES30N.py (run #299) / TTMSQZ_3_0_ES30T.py (run #340, deep-squeeze 1.5x). This driver
puts both changes on that clean engine, one at a time and stacked, and checks the pre-registered
pass bar for row F (the full stack) against the raw twin (row A / #299) and against the book's
current TTM leg (the #459 cell, TTMSQZ_3_0_ES30SSOF2.py on the structural-stop lineage).

READ-ONLY RESEARCH DRIVER: no commits, no pushes, no queued jobs, augur_strategies/ untouched.

Data: ES 30m RTH.
  - Parity checks run on the NO-adjust master (source db_noadj_rth) to confirm this driver's data
    load + engine calls reproduce the stored run numbers before anything new is trusted.
  - Every other row (A-F and the #459 twin) runs on the back-adjusted master (source db_adj_rth),
    named EXPLICITLY via find_master (an unpinned lookup returns the no-adjust master).
Window 2010-06-07..2026-06-30, lockbox from 2025-07-01. Cost 0.363 pts / $50 a point (ES).

Tilt / fade handling matches tools/ttmsqz_r15d_fade2_across_bases.py: trades come straight out of
TTMSQZ_3_0.run_backtest via return_trades=True (raw points, pre-cost), and every tilt is applied
by re-pricing those raw points in numpy rather than re-simulating anything. Cost convention
(TTMSQZ_3_0_ES30T.py's docstring, verified against r15d): a trade sized s is worth
s*(raw_pts - cost)*mult in dollars, so usd = size_mult * (raw_pts - cost) * mult composes tilts by
multiplying size_mult (1.0 / 1.5 / 2.25 when both the deep-squeeze and open-bar tilts apply).

The deep-squeeze state (TTMSQZ_3_0_ES30T._deep_state) and the open-bar ordinal test
(TTMSQZ_3_0_ES30SSO._session_ordinal / _OPEN_ORDINAL / _OPEN_MULT) are imported and called
directly from those files rather than reimplemented, so this driver cannot drift from what the
production wrapper files actually do.

Output: tools/data/ttmsqz_r19b_atr_stack.txt
"""
import os
import sys
from importlib import util as _u

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays  # noqa: E402

COST = 0.363          # ES points, round trip
MULT = 50.0            # dollars a point
DATE_FROM = "2010-06-07"
LB_FROM = "2025-07-01"
DATE_TO = "2026-06-30"
WF_TO = "2025-06-30"   # inclusive day before LB_FROM


def _mod(path, name):
    sp = _u.spec_from_file_location(name, path)
    m = _u.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


STRAT_DIR = os.path.join(ROOT, "augur_strategies")
t3 = _mod(os.path.join(STRAT_DIR, "TTMSQZ_3_0.py"), "r19b_t3")
es30n = _mod(os.path.join(STRAT_DIR, "TTMSQZ_3_0_ES30N.py"), "r19b_es30n")
es30t = _mod(os.path.join(STRAT_DIR, "TTMSQZ_3_0_ES30T.py"), "r19b_es30t")
es30sso = _mod(os.path.join(STRAT_DIR, "TTMSQZ_3_0_ES30SSO.py"), "r19b_es30sso")
es30ssof2 = _mod(os.path.join(STRAT_DIR, "TTMSQZ_3_0_ES30SSOF2.py"), "r19b_es30ssof2")

# The crown's frozen mechanism (run #299 / #340's neighbourhood centre), identical to the CROWN
# dict in tools/ttmsqz_r15d_fade2_across_bases.py. fade_bars is set per-row below.
CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open", exit_mode="fade",
             stop_atr=1.5, eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20, gate_bars=2,
             gate_ratio=1.0, gate_fired_k=3, direction="both")

L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load(source):
    m = find_master("ES", "30m", "rth", source=source)
    if m is None:
        raise SystemExit("no ES 30m RTH master with source=%r registered" % source)
    return load_master_arrays(m, date_from=DATE_FROM, date_to=DATE_TO)


def whole_run_usd(trades, size_mult=None):
    pts = np.array([t[2] for t in trades], float)
    if size_mult is None:
        size_mult = np.ones(len(pts))
    return size_mult * (pts - COST) * MULT


def trading_days(index):
    d = np.asarray(pd.DatetimeIndex(index).date)
    return sorted(set(d))


def stretch_stats(usd, exit_dates, days_in_stretch, years):
    """Daily P&L by exit date, zero-filled on every trading day in the stretch that had no
    exit. Drawdown valued on that daily curve. MAR = (net/years)/drawdown. ROC@$30k = 30 x MAR.
    Sortino = mean / downside-deviation of the daily series x sqrt(252), target 0."""
    n = int(len(usd))
    net = float(usd.sum()) if n else 0.0
    if not len(days_in_stretch):
        dd = 1e-9
    else:
        s = pd.Series(usd, index=pd.to_datetime(exit_dates)) if n else pd.Series(dtype=float)
        daily = s.groupby(s.index).sum() if n else pd.Series(dtype=float)
        full_idx = pd.to_datetime(sorted(days_in_stretch))
        daily = daily.reindex(full_idx, fill_value=0.0)
        cum = daily.cumsum()
        peak = cum.cummax()
        dd = float(-(cum - peak).min())
        dd = max(dd, 1e-9)
        mean = float(daily.mean())
        downside = daily.clip(upper=0.0)
        ddev = float(np.sqrt((downside ** 2).mean())) if len(daily) else float("nan")
        sortino = (mean / ddev * np.sqrt(252.0)) if ddev > 1e-12 else float("nan")
    if not len(days_in_stretch):
        sortino = float("nan")
    mar = (net / years) / dd if years > 0 else float("nan")
    roc30 = 30.0 * mar
    wins = usd[usd > 0] if n else np.array([])
    losses = usd[usd < 0] if n else np.array([])
    gl = float(-losses.sum())
    pf = (float(wins.sum()) / gl) if gl > 1e-9 else (float("inf") if wins.sum() > 0 else 0.0)
    biggest = float(usd.max()) if n else 0.0
    net_ex_biggest = net - biggest
    return dict(n=n, net=net, dd=dd, mar=mar, roc30=roc30, sortino=sortino, pf=pf,
                net_ex_biggest=net_ex_biggest)


def split_wf_lb(trades_or_usd_dates, index):
    """Return boolean masks (wf, lb) for an array of exit-bar positions, by exit calendar date."""
    pass


def score_row(trades, size_mult, index, day_id_index_dates, wf_days, lb_days, yrs_wf, yrs_lb):
    """trades: list of (eb, xb, raw_pts, side, entry_px, exit_px). size_mult: per-trade array."""
    usd = whole_run_usd(trades, size_mult)
    xb = np.array([int(t[1]) for t in trades], int)
    exit_dates = np.asarray(pd.DatetimeIndex(index)[xb].date)
    lb_from_d = pd.Timestamp(LB_FROM).date()
    is_lb = exit_dates >= lb_from_d
    is_wf = ~is_lb
    wf = stretch_stats(usd[is_wf], exit_dates[is_wf], wf_days, yrs_wf)
    lb = stretch_stats(usd[is_lb], exit_dates[is_lb], lb_days, yrs_lb)
    return dict(wf=wf, lb=lb, whole_n=int(len(trades)), whole_net=float(usd.sum()))


# ---------------------------------------------------------------------------
# Tilts (called from the production wrapper files, not reimplemented)
# ---------------------------------------------------------------------------

def deep_mult(trades, highs, lows, closes, day_id, index):
    deep = es30t._deep_state(highs, lows, closes, day_id, index)
    n = len(deep)
    mult = np.ones(len(trades))
    for i, t in enumerate(trades):
        eb = int(t[0])
        if bool(deep[min(max(eb - 1, 0), n - 1)]):
            mult[i] = 1.5
    return mult


def openbar_mult(trades, day_id):
    ordinal = es30sso._session_ordinal(day_id)
    mult = np.ones(len(trades))
    for i, t in enumerate(trades):
        eb = int(t[0])
        if ordinal[eb] == es30sso._OPEN_ORDINAL:
            mult[i] = es30sso._OPEN_MULT
    return mult


def main():
    emit("TTM round 19b - IDEA 2, the honest stack on the ATR engine (TTM_R19_PREREG.txt)")
    emit("ES 30m RTH, window %s..%s, lockbox from %s, cost %.3f pts, $%.0f/pt"
         % (DATE_FROM, DATE_TO, LB_FROM, COST, MULT))
    emit("")

    # -----------------------------------------------------------------
    # PARITY (NO-adjust master, exact run #299 / #340 params)
    # -----------------------------------------------------------------
    emit("=" * 100)
    emit("PARITY CHECK - NO-adjust master (db_noadj_rth), ES30N/ES30T params kc 1.5, stop_atr 1.5, "
         "eod 1, gate_len 20")
    emit("=" * 100)
    noadj = load("db_noadj_rth")
    pkw = dict(kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20)
    r299 = es30n.run_backtest(noadj["open"], noadj["high"], noadj["low"], noadj["close"],
                              day_id=noadj["day_id"], index=noadj["index"], return_trades=True, **pkw)
    n299 = len(r299["trades"]); net299 = float(whole_run_usd(r299["trades"]).sum())
    ok299 = (n299 == 359) and (abs(net299 - 51709) < 1.0)
    emit("#299 (ES30N)  got n=%d net=$%s   expect n=359 net=$51,709   %s"
         % (n299, "{:,.0f}".format(net299), "MATCH" if ok299 else "MISMATCH"))

    r340 = es30t.run_backtest(noadj["open"], noadj["high"], noadj["low"], noadj["close"],
                              day_id=noadj["day_id"], index=noadj["index"], return_trades=True, **pkw)
    n340 = len(r340["trades"]); net340 = float(whole_run_usd(r340["trades"]).sum())
    ok340 = abs(net340 - 69884) < 1.0
    emit("#340 (ES30T)  got n=%d net=$%s   expect net=$69,884   %s"
         % (n340, "{:,.0f}".format(net340), "MATCH" if ok340 else "MISMATCH"))
    emit("")
    if not (ok299 and ok340):
        emit("*** PARITY FAILED - the data load or engine call does not reproduce the stored runs. ***")
        emit("*** Continuing anyway so the mismatch is visible, but treat everything below as suspect. ***")
        emit("")

    # -----------------------------------------------------------------
    # ADJ master for every other row
    # -----------------------------------------------------------------
    adj = load("db_adj_rth")
    o, h, l, c = adj["open"], adj["high"], adj["low"], adj["close"]
    did, idx = adj["day_id"], adj["index"]
    all_days = trading_days(idx)
    lb_from_d = pd.Timestamp(LB_FROM).date()
    wf_days = [d for d in all_days if d < lb_from_d]
    lb_days = [d for d in all_days if d >= lb_from_d]
    yrs_wf = (pd.Timestamp(WF_TO) - pd.Timestamp(DATE_FROM)).days / 365.25
    yrs_lb = (pd.Timestamp(DATE_TO) - pd.Timestamp(LB_FROM)).days / 365.25
    emit("ADJ master (db_adj_rth): %d bars, %d trading days (WF %d days / %.2f yrs, LB %d days / %.2f yrs)"
         % (len(c), len(all_days), len(wf_days), yrs_wf, len(lb_days), yrs_lb))
    emit("")

    def engine_trades(fade_bars):
        r = t3.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True,
                             fade_bars=fade_bars, **CROWN)
        return r["trades"] if r else []

    trades_f1 = engine_trades(1)
    trades_f2 = engine_trades(2)
    emit("engine trade counts: fade_bars=1 -> %d trades, fade_bars=2 -> %d trades (%s)"
         % (len(trades_f1), len(trades_f2),
            "engine honours fade_bars" if len(trades_f1) != len(trades_f2) else "NO CHANGE - check wiring"))
    emit("")

    deep_f1 = deep_mult(trades_f1, h, l, c, did, idx)
    open_f1 = openbar_mult(trades_f1, did)
    deep_f2 = deep_mult(trades_f2, h, l, c, did, idx)
    open_f2 = openbar_mult(trades_f2, did)

    rows = {}
    ones1 = np.ones(len(trades_f1))
    ones2 = np.ones(len(trades_f2))
    rows["A raw twin (#299 cell, no tilt, fade 1)"] = (trades_f1, ones1)
    rows["B + deep-squeeze 1.5x (#340)"] = (trades_f1, deep_f1)
    rows["C + open-bar 1.5x only"] = (trades_f1, open_f1)
    rows["D + fade after 2 only"] = (trades_f2, ones2)
    rows["E  B + C (tilts multiply)"] = (trades_f1, deep_f1 * open_f1)
    rows["F  E + fade 2 = FULL STACK"] = (trades_f2, deep_f2 * open_f2)

    scored = {}
    for label, (trades, mult) in rows.items():
        scored[label] = score_row(trades, mult, idx, None, wf_days, lb_days, yrs_wf, yrs_lb)

    # internal consistency: row A should equal ES30N run directly on the ADJ master
    r_es30n_adj = es30n.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True, **pkw)
    a_direct_net = float(whole_run_usd(r_es30n_adj["trades"]).sum()) if r_es30n_adj else float("nan")
    a_row_net = scored["A raw twin (#299 cell, no tilt, fade 1)"]["wf"]["net"] + \
                scored["A raw twin (#299 cell, no tilt, fade 1)"]["lb"]["net"]
    emit("internal check: row A whole-run net $%s vs ES30N run direct on ADJ master $%s  (%s)"
         % ("{:,.0f}".format(a_row_net), "{:,.0f}".format(a_direct_net),
            "MATCH" if abs(a_row_net - a_direct_net) < 1.0 else "MISMATCH"))
    emit("")

    # -----------------------------------------------------------------
    # #459 twin (TTMSQZ_3_0_ES30SSOF2.py on the ADJ master)
    # -----------------------------------------------------------------
    emit("=" * 100)
    emit("TWIN CHECK - #459 cell, TTMSQZ_3_0_ES30SSOF2.py (kc 1.5, eod 1), ADJ master")
    emit("=" * 100)
    twin_kw = dict(kc_mult=1.5, eod_cutoff=1)
    r459 = es30ssof2.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True, **twin_kw)
    twin_trades = r459["trades"] if r459 else []
    twin_n = len(twin_trades)
    twin_net = float(whole_run_usd(twin_trades).sum())
    ok459 = (twin_n == 355) and (abs(twin_net - 72716) < 1.0)
    emit("#459 (ES30SSOF2)  got n=%d net=$%s   expect n=355 net=$72,716   %s"
         % (twin_n, "{:,.0f}".format(twin_net), "MATCH" if ok459 else "MISMATCH"))
    emit("")
    twin_scored = score_row(twin_trades, np.ones(twin_n), idx, None, wf_days, lb_days, yrs_wf, yrs_lb)

    # -----------------------------------------------------------------
    # YARDSTICK TABLE
    # -----------------------------------------------------------------
    emit("=" * 100)
    emit("YARDSTICK - daily P&L by exit date, zero-filled within each stretch, drawdown valued daily")
    emit("=" * 100)
    hdr = "%-42s %-3s %5s %11s %9s %6s %8s %8s %6s %13s"
    emit(hdr % ("row", "stg", "n", "net $", "DD $", "MAR", "ROC@30k", "Sortino", "PF", "LB net ex-big"))

    def line(label, stg, s, show_exbig=False):
        exbig = "{:,.0f}".format(s["net_ex_biggest"]) if show_exbig else ""
        emit(hdr % (label, stg, s["n"], "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
                    "%.2f" % s["mar"], "%.1f%%" % s["roc30"],
                    "%.2f" % s["sortino"] if s["sortino"] == s["sortino"] else "nan",
                    "%.2f" % min(s["pf"], 99), exbig))

    for label in ["A raw twin (#299 cell, no tilt, fade 1)", "B + deep-squeeze 1.5x (#340)",
                  "C + open-bar 1.5x only", "D + fade after 2 only", "E  B + C (tilts multiply)",
                  "F  E + fade 2 = FULL STACK"]:
        s = scored[label]
        line(label, "WF", s["wf"])
        line(label, "LB", s["lb"], show_exbig=True)
    line("#459 twin (ES30SSOF2, book leg)", "WF", twin_scored["wf"])
    line("#459 twin (ES30SSOF2, book leg)", "LB", twin_scored["lb"], show_exbig=True)
    emit("")

    # -----------------------------------------------------------------
    # VERDICT
    # -----------------------------------------------------------------
    emit("=" * 100)
    emit("VERDICT - pre-registered pass bar for row F (clause by clause)")
    emit("=" * 100)
    A = scored["A raw twin (#299 cell, no tilt, fade 1)"]
    B = scored["B + deep-squeeze 1.5x (#340)"]
    C = scored["C + open-bar 1.5x only"]
    F = scored["F  E + fade 2 = FULL STACK"]
    T = twin_scored

    def beats(f_val, other_val):
        return f_val >= other_val

    c1a = beats(F["wf"]["roc30"], A["wf"]["roc30"])
    c1b = beats(F["lb"]["roc30"], A["lb"]["roc30"])
    c2a = beats(F["wf"]["sortino"], A["wf"]["sortino"])
    c2b = beats(F["lb"]["sortino"], A["lb"]["sortino"])
    c3a = beats(F["wf"]["roc30"], T["wf"]["roc30"])
    c3b = beats(F["lb"]["roc30"], T["lb"]["roc30"])
    c4a = beats(F["wf"]["sortino"], T["wf"]["sortino"])
    c4b = beats(F["lb"]["sortino"], T["lb"]["sortino"])
    c5 = F["lb"]["net_ex_biggest"] > 0

    emit("(a) F beats A on ROC@30k -- WF %.1f%% vs %.1f%% (%s); LB %.1f%% vs %.1f%% (%s)"
         % (F["wf"]["roc30"], A["wf"]["roc30"], "PASS" if c1a else "FAIL",
            F["lb"]["roc30"], A["lb"]["roc30"], "PASS" if c1b else "FAIL"))
    emit("(b) F beats A on Sortino -- WF %.2f vs %.2f (%s); LB %.2f vs %.2f (%s)"
         % (F["wf"]["sortino"], A["wf"]["sortino"], "PASS" if c2a else "FAIL",
            F["lb"]["sortino"], A["lb"]["sortino"], "PASS" if c2b else "FAIL"))
    emit("(c) F beats #459 on ROC@30k -- WF %.1f%% vs %.1f%% (%s); LB %.1f%% vs %.1f%% (%s)"
         % (F["wf"]["roc30"], T["wf"]["roc30"], "PASS" if c3a else "FAIL",
            F["lb"]["roc30"], T["lb"]["roc30"], "PASS" if c3b else "FAIL"))
    emit("(d) F beats #459 on Sortino -- WF %.2f vs %.2f (%s); LB %.2f vs %.2f (%s)"
         % (F["wf"]["sortino"], T["wf"]["sortino"], "PASS" if c4a else "FAIL",
            F["lb"]["sortino"], T["lb"]["sortino"], "PASS" if c4b else "FAIL"))
    emit("(e) LB profitable without its biggest trade -- $%s (%s); LB trade count = %d"
         % ("{:,.0f}".format(F["lb"]["net_ex_biggest"]), "PASS" if c5 else "FAIL", F["lb"]["n"]))
    emit("(note) LB trade floor of 50 is NOT expected to be met by this leg alone per the pre-reg "
         "(\"it cannot reach 50 LB trades alone - report the count; it is judged as a book leg\").")
    emit("")

    overall = c1a and c1b and c2a and c2b and c3a and c3b and c4a and c4b and c5
    emit("OVERALL: %s" % ("PASS -- full stack clears every clause of the row-F bar; goes to a fenced "
                           "validate, nothing crowned by this scan." if overall else
                           "NOT a clean pass -- at least one clause above failed; nothing crowned by this scan."))
    emit("")

    # which SINGLE change carries the effect, on the clean engine -- compare only the three
    # one-change rows (B, C, D) against A, never the cumulative stack itself (F would trivially
    # "win" that comparison since it contains all three).
    D = scored["D + fade after 2 only"]

    def delta(field, stretch):
        return {
            "deep-squeeze tilt alone (B-A)": B[stretch][field] - A[stretch][field],
            "open-bar tilt alone (C-A)": C[stretch][field] - A[stretch][field],
            "fade-after-2 alone (D-A)": D[stretch][field] - A[stretch][field],
        }

    d_wf = delta("roc30", "wf"); d_lb = delta("roc30", "lb")
    f_wf = F["wf"]["roc30"] - A["wf"]["roc30"]; f_lb = F["lb"]["roc30"] - A["lb"]["roc30"]
    emit("ROC@30k delta over A -- WF: deep %+.1fpp, open-bar %+.1fpp, fade-2 %+.1fpp (full stack %+.1fpp) | "
         "LB: deep %+.1fpp, open-bar %+.1fpp, fade-2 %+.1fpp (full stack %+.1fpp)"
         % (d_wf["deep-squeeze tilt alone (B-A)"], d_wf["open-bar tilt alone (C-A)"], d_wf["fade-after-2 alone (D-A)"], f_wf,
            d_lb["deep-squeeze tilt alone (B-A)"], d_lb["open-bar tilt alone (C-A)"], d_lb["fade-after-2 alone (D-A)"], f_lb))
    biggest_wf = max(d_wf, key=lambda k: abs(d_wf[k]))
    biggest_lb = max(d_lb, key=lambda k: abs(d_lb[k]))
    emit("Largest SINGLE-change contribution to the stack's edge on the clean engine (of the three "
         "components, not the stack itself): %s in WF, %s in LB." % (biggest_wf, biggest_lb))

    out_path = os.path.join(ROOT, "tools", "data", "ttmsqz_r19b_atr_stack.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\nlog -> " + out_path)


if __name__ == "__main__":
    main()
