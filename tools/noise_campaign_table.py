#!/usr/bin/env python3
"""
NOISE 2026-08-17 variant campaign -- one results table with IS / WF / LB dollar
splits + drawdown for EVERY config in the campaign.

Why this exists
---------------
Run #236 (the controlled 12-cell comparison GRID) saves only a FULL-window
pnl/dd per cell -- no IS/WF/LB structure -- and the local round-log cells
(A1..D4) were never saved as runs at all. This script recomputes all of them
on the same three stretches the app's 1E MATRIX RAW tab shows, using the
campaign harness `tools/noise_variant_research.py` (parity vs the real engine
proven exact to the cent).

Conventions (all pinned to run #231's saved `validate.windows`)
---------------------------------------------------------------
  IS + WF  = one CONTINUOUS backtest over the optimize window
             2010-06-07 -> 2025-02-10, cut in two at a DATE boundary.
             The boundary is derived from #231's own crowned candidate:
             is_rng.num_trades = 1921, wf_rng.num_trades = 3192 (sum 5113).
             That is the same cut `_rawFrac` in index.html (~line 10252) uses
             to split the RAW curve, just resolved to a calendar instant here
             so every variant is cut at the SAME point in time rather than at
             its own trade-count fraction.
  LB       = a FRESH backtest over 2025-02-11 -> 2026-08-12 only. This is the
             engine's own lockbox convention (it burns the strategy's warm-up
             inside the lockbox window), and it is what reconciles to
             `validate.lockbox` (441 trades / 1814.2363 pts on #231).
             The CONTINUOUS-run slice of the same dates is also reported
             ("LB cont") because IS + WF + LB(cont) == TOTAL exactly, while
             IS + WF + LB(fresh) does not -- the fresh pass drops the ~79
             warm-up trades.
  TOTAL    = one CONTINUOUS backtest 2010-06-07 -> 2026-08-12. This is the
             number run #236's saved `points` carry and what #231's
             `validate.total_*` describes.

Every drawdown is measured on its own stretch with the peak reset at that
stretch's first trade (same as the engine's cal blocks / `_rawDdSlice`), and
is PRINTED POSITIVE.

Source PINNED: db_noadj_rth, NQ 5m rth, cost_pts 0.533, multiplier 20.
No master import/refresh, no runner jobs -- local library calls only.

  python tools/noise_campaign_table.py            # reconciliation + full table
  python tools/noise_campaign_table.py --check    # reconciliation gate only
"""
import os
import sys
import json
import argparse

EDGELOG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if EDGELOG_ROOT not in sys.path:
    sys.path.insert(0, EDGELOG_ROOT)

from augur_engine.data import find_master, load_master_arrays              # noqa: E402
from tools.noise_variant_research import run_variant, CHAMPION, FEE, MULT  # noqa: E402

OPT_FROM, OPT_TO = "2010-06-07", "2025-02-10"
LB_FROM, LB_TO = "2025-02-11", "2026-08-12"

# run #231 crowned candidate, verbatim from Firestore (POINTS, not dollars)
R231 = {
    "is":   dict(n=1921, pnl=309.4836,    dd=-382.9997),
    "wf":   dict(n=3192, pnl=13546.6818,  dd=-974.1137),
    "pre":  dict(n=5113, pnl=13856.1654,  dd=-974.1137),
    "lb":   dict(n=441,  pnl=1814.2363,   dd=-1639.6985),
    "full": dict(n=5633, pnl=16799.0415,  dd=-1639.6985),
}

_ARR = {}


def arrays(date_from, date_to):
    key = (date_from, date_to)
    if key not in _ARR:
        m = find_master("NQ", "5m", "rth", "db_noadj_rth")
        if m is None:
            raise SystemExit("NO MASTER for NQ/5m/rth/db_noadj_rth")
        _ARR[key] = load_master_arrays(m, date_from=date_from, date_to=date_to)
    return _ARR[key]


def _net_trades(arr, params):
    """Run one config; return [(entry_datetime, net_pnl_pts), ...] in time order."""
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    idx = arr["index"]
    return [(idx[t[0]], t[2] - FEE) for t in tr]


def stats(seq):
    """Dollars / PF / DD for one stretch. seq = [(dt, net_pnl_pts), ...]. DD POSITIVE."""
    if not seq:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, mar=0.0, pts=0.0)
    p = [x[1] for x in seq]
    gw = sum(x for x in p if x > 0)
    gl = -sum(x for x in p if x < 0)
    pf = (gw / gl) if gl > 1e-9 else float("inf")
    cum = peak = mdd = 0.0
    for x in p:
        cum += x
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    net = sum(p) * MULT
    dd = abs(mdd) * MULT
    return dict(n=len(p), net=net, pf=pf, dd=dd, pts=sum(p),
                mar=(net / dd) if dd > 1e-9 else float("inf"))


def _boundary():
    """Resolve #231's IS/WF trade-count cut (1921 | 3192) to a calendar instant."""
    seq = _net_trades(arrays(None, OPT_TO), dict(CHAMPION))
    if len(seq) != R231["pre"]["n"]:
        raise SystemExit("BOUNDARY: optimize-window n=%d, expected %d"
                         % (len(seq), R231["pre"]["n"]))
    return seq[R231["is"]["n"] - 1][0], seq[R231["is"]["n"]][0]


def _ts(s, like=None):
    """Timestamp in the master index's own tz (the masters are ET-aware)."""
    import pandas as pd
    t = pd.Timestamp(s)
    tz = getattr(like, "tzinfo", None) if like is not None else None
    if tz is not None and t.tzinfo is None:
        t = t.tz_localize(tz)
    return t


def evaluate(params, cut):
    """Full IS / WF / LB / TOTAL row for one config."""
    opt = _net_trades(arrays(None, OPT_TO), params)
    full = _net_trades(arrays(None, LB_TO), params)
    lb = _net_trades(arrays(LB_FROM, LB_TO), params)
    lb0 = _ts(LB_FROM, full[0][0] if full else None)
    is_seq = [t for t in opt if t[0] <= cut]
    wf_seq = [t for t in opt if t[0] > cut]
    lb_cont = [t for t in full if t[0] >= lb0]
    return dict(IS=stats(is_seq), WF=stats(wf_seq), LB=stats(lb),
                LBC=stats(lb_cont), OPT=stats(opt), TOTAL=stats(full))


# -- the campaign's configs -------------------------------------------------
def C(**kw):
    return dict(CHAMPION, **kw)


def VS(pct):
    """NOISE_1_0's `vol_skip_pct` knob == the harness's skip_hi vol-regime mode."""
    return dict(rv_mode="skip_hi", rv_pct=float(pct))


CONFIGS = [
    # (key, label, what-it-is, params)
    ("#231",   "#231 champion (baseline)",
     "confirm 1 - daytype off - vol-skip off", C()),
    ("D3",     "D3 WINNER confirm2 + skip_bot_short",
     "2 closes outside the band + no shorts after a weak close",
     C(confirm_bars=2, daytype_mode="skip_bot_short")),

    # -- run #236, the 12-cell comparison GRID --
    ("236-01", "#236 c1 / off / no-skip", "= the champion cell", C()),
    ("236-02", "#236 c1 / off / skip90", "vol-skip 90 only", C(**VS(90))),
    ("236-03", "#236 c1 / skip_bot_short / no-skip", "daytype only",
     C(daytype_mode="skip_bot_short")),
    ("236-04", "#236 c1 / skip_bot_short / skip90", "daytype + vol-skip",
     C(daytype_mode="skip_bot_short", **VS(90))),
    ("236-05", "#236 c2 / off / no-skip", "confirm 2 only", C(confirm_bars=2)),
    ("236-06", "#236 c2 / off / skip90", "confirm 2 + vol-skip",
     C(confirm_bars=2, **VS(90))),
    ("236-07", "#236 c2 / skip_bot_short / no-skip", "THE WINNER cell (= D3)",
     C(confirm_bars=2, daytype_mode="skip_bot_short")),
    ("236-08", "#236 c2 / skip_bot_short / skip90", "the triple",
     C(confirm_bars=2, daytype_mode="skip_bot_short", **VS(90))),
    ("236-09", "#236 c3 / off / no-skip", "confirm 3 only", C(confirm_bars=3)),
    ("236-10", "#236 c3 / off / skip90", "confirm 3 + vol-skip",
     C(confirm_bars=3, **VS(90))),
    ("236-11", "#236 c3 / skip_bot_short / no-skip", "confirm 3 + daytype",
     C(confirm_bars=3, daytype_mode="skip_bot_short")),
    ("236-12", "#236 c3 / skip_bot_short / skip90", "confirm 3 triple",
     C(confirm_bars=3, daytype_mode="skip_bot_short", **VS(90))),

    # -- local round log: cells that CLEARED the pre-registered bar --
    ("A2-90",  "A2 vol_skip 90", "skip the day after a top-decile-vol session",
     C(**VS(90))),
    ("A2-95",  "A2 vol_skip 95", "skip the day after a top-5% vol session",
     C(**VS(95))),
    ("A2-98",  "A2 vol_skip 98", "skip the day after a top-2% vol session",
     C(**VS(98))),
    ("B1-2",   "B1 confirm_bars 2", "2 consecutive closes outside the band",
     C(confirm_bars=2)),
    ("B1-3",   "B1 confirm_bars 3", "3 consecutive closes outside the band",
     C(confirm_bars=3)),
    ("B4-bs",  "B4 skip_bot_short", "no SHORTs after a bottom-20% close",
     C(daytype_mode="skip_bot_short")),
    ("B4-ba",  "B4 skip_bot_all", "no trades at all after a bottom-20% close",
     C(daytype_mode="skip_bot_all")),
    ("A3-90",  "A3 stop x0.75 @ vol pct 90", "tighten the stop in high vol",
     C(rv_mode="stop_scale", rv_pct=90.0, rv_stop_mult=0.75)),

    # -- DEAD families, one representative each --
    ("A1-eod", "A1 vol-cond exit_eod @90 (DEAD)", "hold to EOD on high-vol days",
     C(rv_mode="exit_eod", rv_pct=90.0)),
    ("A1-bnd", "A1 vol-cond exit_band @90 (DEAD)", "band exit on high-vol days",
     C(rv_mode="exit_band", rv_pct=90.0)),
    ("A2-lo",  "A2 skip LOW-vol days (DEAD)", "no plateau",
     C(rv_mode="skip_lo", rv_pct_lo=10.0)),
    ("B2-36",  "B2 time-decay exit 36 bars (DEAD)", "flat after 36 bars in trade",
     C(time_stop_bars=36)),
    ("B3-125", "B3 asym stop_k_long 1.25 (DEAD)",
     "cleared net+MAR, its declared neighbor failed -> no plateau",
     C(stop_k=1.25, stop_k_short=1.75)),
    ("B4-tl",  "B4 skip_top_long (DEAD)", "no LONGs after a top-20% close",
     C(daytype_mode="skip_top_long")),
    ("B4-ta",  "B4 skip_top_all (DEAD)", "no trades after a top-20% close",
     C(daytype_mode="skip_top_all")),
    ("B5",     "B5 skip-after-loss (DEAD)",
     "sit out the session after a losing session", C(skip_after_loss=True)),
    ("D1",     "D combo confirm2 + vol_skip90",
     "failed the beat-best-component rule", C(confirm_bars=2, **VS(90))),
    ("D2",     "D combo skip_bot_short + vol_skip90",
     "failed the beat-best-component rule",
     C(daytype_mode="skip_bot_short", **VS(90))),
    ("D4",     "D triple confirm2 + skip_bot_short + vs90",
     "failed the beat-best-component rule",
     C(confirm_bars=2, daytype_mode="skip_bot_short", **VS(90))),
]


# Run #236's saved `points`, verbatim from Firestore (FULL-window pnl / dd, POINTS).
# Second gate: the computed TOTAL column has to land on the runner's own GRID numbers.
R236 = {
    "236-01": (16799.0, 1639.7), "236-02": (18614.3, 1184.9),
    "236-03": (19409.0, 1559.6), "236-04": (19037.2, 1104.8),
    "236-05": (16045.7, 2209.4), "236-06": (16718.5, 1060.3),
    "236-07": (18398.0, 1886.5), "236-08": (17488.7, 971.6),
    "236-09": (17248.6, 1566.6), "236-10": (16019.7, 831.5),
    "236-11": (18255.2, 1309.5), "236-12": (16078.0, 888.1),
}


def reconcile236(rows):
    """Cross-check the 12 computed GRID cells against run #236's saved points."""
    print("\nGRID CROSS-CHECK -- computed TOTAL vs run #236 saved points (POINTS, 0.1 tol)")
    ok = True
    for key, (pnl, dd) in sorted(R236.items()):
        t = rows[key]["TOTAL"]
        gp, gd = t["pts"], t["dd"] / MULT
        good = abs(gp - pnl) < 0.1 and abs(gd - dd) < 0.1
        ok = ok and good
        print("  %-7s pnl %10.1f vs %10.1f | dd %8.1f vs %8.1f -> %s"
              % (key, gp, pnl, gd, dd, "MATCH" if good else "MISMATCH"))
    print("  GRID OVERALL: %s" % ("PASS" if ok else "FAIL"))
    return ok


def reconcile(cut):
    print("RECONCILIATION GATE -- run #231 crowned config, POINTS")
    r = evaluate(dict(CHAMPION), cut)
    ok = [True]

    def chk(tag, got, exp_n, exp_pts, exp_dd):
        gp, gd = got["pts"], got["dd"] / MULT
        good = (got["n"] == exp_n and abs(gp - exp_pts) < 0.01
                and abs(gd - abs(exp_dd)) < 0.01)
        ok[0] = ok[0] and good
        print("  %-5s n=%-5d pnl=%11.4f dd=%10.4f  |  saved n=%-5d pnl=%11.4f "
              "dd=%10.4f  -> %s"
              % (tag, got["n"], gp, gd, exp_n, exp_pts, abs(exp_dd),
                 "MATCH" if good else "MISMATCH"))

    chk("IS", r["IS"], R231["is"]["n"], R231["is"]["pnl"], R231["is"]["dd"])
    chk("WF", r["WF"], R231["wf"]["n"], R231["wf"]["pnl"], R231["wf"]["dd"])
    chk("OPT", r["OPT"], R231["pre"]["n"], R231["pre"]["pnl"], R231["pre"]["dd"])
    chk("LB", r["LB"], R231["lb"]["n"], R231["lb"]["pnl"], R231["lb"]["dd"])
    chk("FULL", r["TOTAL"], R231["full"]["n"], R231["full"]["pnl"], R231["full"]["dd"])

    add = r["IS"]["pts"] + r["WF"]["pts"]
    print("  IS+WF = %.4f pts vs OPT %.4f pts -> %s"
          % (add, r["OPT"]["pts"], "MATCH" if abs(add - r["OPT"]["pts"]) < 1e-6 else "MISMATCH"))
    add2 = r["IS"]["net"] + r["WF"]["net"] + r["LBC"]["net"]
    print("  IS+WF+LB(cont) = $%s vs TOTAL $%s -> %s"
          % (format(add2, ",.0f"), format(r["TOTAL"]["net"], ",.0f"),
             "MATCH" if abs(add2 - r["TOTAL"]["net"]) < 1 else "MISMATCH"))
    print("  LB(fresh) $%s  |  LB(continuous slice) $%s"
          % (format(r["LB"]["net"], ",.0f"), format(r["LBC"]["net"], ",.0f")))
    print("  OVERALL: %s\n" % ("PASS" if ok[0] else "FAIL"))
    return ok[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    c0, c1 = _boundary()
    print("IS/WF cut from #231 (trade 1921 | 1922): last IS trade %s, first WF trade %s\n"
          % (c0, c1))
    if not reconcile(c0):
        raise SystemExit("RECONCILIATION FAILED -- not publishing numbers")
    if a.check:
        return

    out = {}
    hdr = ("%-8s %-40s|%11s %8s|%11s %8s|%11s %8s %11s|%11s %8s %6s %6s"
           % ("key", "label", "IS $", "IS DD", "WF $", "WF DD", "LB $", "LB DD",
              "LBcont $", "TOTAL $", "TOT DD", "PF", "MAR"))
    print(hdr)
    print("-" * len(hdr))
    for key, label, what, params in CONFIGS:
        r = evaluate(params, c0)
        out[key] = dict(
            label=label, what=what,
            params={k: v for k, v in params.items()},
            **{s: {kk: (None if r[s][kk] == float("inf") else r[s][kk]) for kk in r[s]}
               for s in r})
        print("%-8s %-40s|%11s %8s|%11s %8s|%11s %8s %11s|%11s %8s %6.2f %6.2f"
              % (key, label,
                 format(r["IS"]["net"], ",.0f"), format(r["IS"]["dd"], ",.0f"),
                 format(r["WF"]["net"], ",.0f"), format(r["WF"]["dd"], ",.0f"),
                 format(r["LB"]["net"], ",.0f"), format(r["LB"]["dd"], ",.0f"),
                 format(r["LBC"]["net"], ",.0f"),
                 format(r["TOTAL"]["net"], ",.0f"), format(r["TOTAL"]["dd"], ",.0f"),
                 r["TOTAL"]["pf"], r["TOTAL"]["mar"]))
        print("%-8s %-40s| n IS %-5d WF %-5d LB %-4d (cont %-4d) TOT %-5d | OPT $%s "
              "PF %.3f DD $%s MAR %.2f | IS PF %.3f WF PF %.3f LB PF %.3f"
              % ("", "", r["IS"]["n"], r["WF"]["n"], r["LB"]["n"], r["LBC"]["n"],
                 r["TOTAL"]["n"], format(r["OPT"]["net"], ",.0f"), r["OPT"]["pf"],
                 format(r["OPT"]["dd"], ",.0f"), r["OPT"]["mar"],
                 r["IS"]["pf"], r["WF"]["pf"], r["LB"]["pf"]))
    reconcile236(out)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1, default=str)
        print("\nwrote %s" % a.json)


if __name__ == "__main__":
    main()
