"""continuous_lb_check.py -- grade a config's LOCKBOX the way it would actually have traded.

WHY THIS EXISTS
---------------
`run_validate` grades the lockbox by RELOADING the master from `lockbox_from` with no prior
history, so a config whose state is path-dependent gets a lockbox verdict that does not
correspond to trading it continuously. BACKTESTING_STACK.md banked two confirmed cases on
2026-08-08 and proposed this guard -- "run the champion continuously over the full window,
slice the lockbox by ENTRY time, report BOTH counts, flag material divergence" -- and then
nobody built it. This is that guard.

The motivating case is run #198 (ENGU-Q ETH): the reload read 126 lockbox trades / PF 1.46 and
the engine stamped it PASS, while the continuous run took its last entry in 2025-04 and held one
position 449 days -- zero lockbox trades, and an accidental buy-and-hold worth 38.9% of that
run's profit. #198 was written up as NOT DEPLOYABLE on that basis.

THAT VERDICT IS PRE-FIX AND NO LONGER REPRODUCES (measured here 2026-09-05). #198's champion
carries `regime_len 5`, and commit 6da54db (2026-08-26) fixed an ETH mis-scaling in this very
file: the regime lookback multiplied by RTH's 390 bars/day on a 24h tape that has 1,091, so
`regime_len 5` meant ~1.8 days and now means 5. Run today, #198's params give 1,795 trades
(the run doc says 1,304), PF 1.76 (2.24), longest hold 156 days (449) and 100 continuous
lockbox entries (0). So the runaway hold was partly an artifact of the scaling bug, and run
#198's SAVED METRICS NO LONGER DESCRIBE WHAT ITS OWN FILE DOES. Any run older than 2026-08-26
whose params set regime_len > 0 is in the same position -- re-run it before quoting it.

Because of that, #198 cannot serve as the self-test. The self-test is the frozen #226 control,
which the house re-certifies to the cent: n=2,843 / $434,721.12 over 2010-06-07..2026-06-30 at
cost 0.533. If that does not reproduce, the data or the plugin moved and nothing below is safe.

WHAT IT REPORTS, per config, on ONE continuous backtest of the full window
-------------------------------------------------------------------------
  * per stretch (selection / lockbox, split on ENTRY time): n, PF, win %, net $, maxDD $,
    MAR ((net/years)/DD), EV R, R / YR
  * EV R cross-checked against the engine's own `expectancy_r` on the whole run
  * top-10 concentration: net, EV R and R / YR after deleting the ten best trades -- for a
    fat-tailed family this is a DESCRIPTION, not a kill (ENGUQ.md section 1), so the number
    printed beside it is the top-10 SHARE of net, which is what the family is judged on
  * the longest hold in calendar days, which is what catches a runaway buy-and-hold
  * RELOAD vs CONTINUOUS lockbox trade counts side by side, with a DIVERGENCE flag

EV R = (1 - win_rate) * (PF - 1) exactly; R / YR = EV R x trades per year of that stretch.

Run:  python tools/continuous_lb_check.py                 (the ENGU-Q ETH R/YR candidates)
      python tools/continuous_lb_check.py --selftest      (run #198 only -- must show 0)
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
# augur_engine.paths derives the master registry + uploads from the PACKAGE's own location,
# and a git worktree carries the code but not the (gitignored) optimizer_history.db or
# augur_uploads. Import the engine from whichever checkout actually holds the data, so this
# tool runs identically from a worktree and from the shared checkout.
def _has_registry(root: pathlib.Path) -> bool:
    # NOT a bare .exists(): sqlite3.connect() CREATES a zero-byte file, so one failed run from
    # a worktree leaves an empty optimizer_history.db behind that then shadows the real one.
    db = root / "optimizer_history.db"
    return db.exists() and db.stat().st_size > 0


_DATA_REPO = REPO if _has_registry(REPO) else pathlib.Path(
    r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, str(_DATA_REPO))
import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from augur_engine.data import find_master, load_master_arrays          # noqa: E402

# ── the configs under test ────────────────────────────────────────────────────────────
# Every one is NQ 1m ETH (db_noadj_eth), mult 20, family cost 0.533, ENGU-Q windows:
# selection 2010-06-07 -> 2025-06-29, lockbox 2025-06-30 -> 2026-06-30.
SPLIT = "2025-06-30"
WIN = ("2010-06-07", "2026-06-30")
COST, MULT = 0.533, 20.0

CASES = [
    # B14 -- the uncrowned candidate mined out of run #309's population, R / YR 93 on the
    # selection window (BOOKMARKS B14). Card run = #313.
    ("B14 mined #309 cand", "ENGUQ_1M_ETH_ER_1_0.py", {
        "buf_atr": 0.45, "tl_len": 206, "trail_frac": 3.0, "ema_len": 220, "atr_len": 52,
        "act_R": 1.5, "breakeven_R": 0.5, "limit_atr": 0.4, "er_len": 50, "stop_mult": 1.8,
        "regime_len": 5, "min_brk": 1.3, "vol_mult": 1.1, "er_th": 0.1}),
    # #309's own crowned config (the MAR rule's pick out of the same search).
    # RELABELLED 2026-09-05. This row said "#309 crown" and carried run #265's params -- they
    # were lifted from the wrong run doc, the same best_params-not-defaults trap this file
    # warns about below. The numbers it produced were right FOR #265 (selection EV R 0.342 /
    # R-YR 28.8, lockbox 67 trades at PF 2.645, top-10 share 61%); only the name was wrong.
    ("#265 ER25 (NOT #309)", "ENGUQ_1M_ETH_ER25_1_0.py", {
        "buf_atr": 0.9, "tl_len": 170, "trail_frac": 2.5, "ema_len": 1380, "atr_len": 106,
        "act_R": 2.5, "breakeven_R": 1.5, "limit_atr": 0.0, "er_len": 60, "stop_mult": 1.0,
        "regime_len": 0, "min_brk": 1.3, "vol_mult": 0.8, "er_th": 0.25}),
    # THE ACTUAL #309 CROWN -- the ENGU-Q champion since 2026-09-05. Its own run doc's
    # best_params. Measured here: selection n=1,505 / PF 1.661 / EV R 0.439 / R-YR 43.9;
    # lockbox n=99 / PF 1.620 / EV R 0.407 / R-YR 40.4; top-10 share 53%, the least
    # tail-dependent ENGU-Q configuration measured; longest hold 282 days across 99 held-out
    # entries, so it is a slow exit inside a working config, not a runaway buy-and-hold.
    ("#309 crown (DEPLOYED)", "ENGUQ_1M_ETH_ER_1_0.py", {
        "buf_atr": 0.3, "tl_len": 206, "trail_frac": 2.5, "ema_len": 220, "atr_len": 52,
        "act_R": 1.5, "breakeven_R": 3.0, "limit_atr": 0.55, "er_len": 100, "stop_mult": 1.3,
        "regime_len": 10, "min_brk": 1.6, "vol_mult": 1.1, "er_th": 0.0}),
    # the DEPLOYED leg, for scale.
    ("#226 frozen (deployed)", "ENGUQ_1M_ETH_1_0.py", {
        "buf_atr": 0.9, "vol_mult": 0.8, "ema_len": 1380, "tl_len": 170, "stop_mult": 1.0,
        "trail_frac": 2.5, "regime_len": 0, "min_brk": 1.3, "breakeven_R": 1.5,
        "atr_len": 106, "act_R": 2.5}),
    # #310's let-it-run limit entry -- EV R 0.94 on the run doc, and its continuous lockbox
    # block is EMPTY, which is the #198 fingerprint. Tested here to find out which it is.
    # ITS OWN CHAMPION PARAMS, not the file's defaults: LIM's DEFAULT_PARAMS are the parity
    # anchor (limit_atr 0 = fill at the signal close = byte-identical to the frozen #226), so
    # passing {} silently re-runs #226 under a #310 label. It did exactly that on the first
    # pass here, and the two rows came out identical to the dollar -- which is how it was caught.
    ("#310 LIM (let-it-run)", "ENGUQ_1M_ETH_LIM_1_0.py", {
        "buf_atr": 1.0, "breakeven_R": 1.5, "ema_len": 420, "tl_len": 238, "vol_mult": 0.8,
        "stop_mult": 1.7, "trail_frac": 4.0, "regime_len": 5, "min_brk": 0.4,
        "limit_atr": 0.7, "atr_len": 44, "act_R": 3.0}),
]
# PARITY: the frozen #226 control, re-certified by the house to the cent.
SELFTEST_EXPECT = dict(n=2843, net=434721.12)
SELFTEST = [
    ("#226 frozen PARITY", "ENGUQ_1M_ETH_1_0.py", {
        "buf_atr": 0.9, "vol_mult": 0.8, "ema_len": 1380, "tl_len": 170, "stop_mult": 1.0,
        "trail_frac": 2.5, "regime_len": 0, "min_brk": 1.3, "breakeven_R": 1.5,
        "atr_len": 106, "act_R": 2.5}),
    # kept as a WITNESS, not a gate: #198's champion, whose "runaway hold / not deployable"
    # write-up predates the 2026-08-26 regime rescale. See the header.
    ("#198 champion (pre-fix note)", "ENGUQ_1M_ETH_1_0.py", {
        "buf_atr": 0.6, "vol_mult": 0.1, "ema_len": 380, "tl_len": 238, "stop_mult": 1.0,
        "trail_frac": 4.0, "regime_len": 5, "min_brk": 1.0, "breakeven_R": 1.0,
        "atr_len": 108, "act_R": 2.5}),
]


def _stats(pnls, years, mult=MULT):
    """n / PF / win% / net$ / maxDD$ / MAR / EV R / R-YR from a list of point P&Ls."""
    n = len(pnls)
    if not n:
        return dict(n=0, pf=None, wr=None, net=0.0, dd=0.0, mar=None, evr=None, ryr=None)
    a = np.asarray(pnls, dtype=float)
    gp = float(a[a > 0].sum())
    gl = float(-a[a < 0].sum())
    pf = (gp / gl) if gl > 0 else None
    wr = 100.0 * float((a > 0).sum()) / n
    net = float(a.sum()) * mult
    cum = np.cumsum(a)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) * mult
    evr = (1 - wr / 100.0) * (pf - 1) if pf is not None else None
    ryr = (evr * n / years) if (evr is not None and years) else None
    mar = ((net / years) / dd) if (years and dd > 0) else None
    return dict(n=n, pf=pf, wr=wr, net=net, dd=dd, mar=mar, evr=evr, ryr=ryr)


def _fmt(d):
    def g(k, f, w):
        v = d.get(k)
        return (f % v).rjust(w) if v is not None else "-".rjust(w)
    return ("n=%-5d PF=%s wr=%s net=$%s DD=$%s MAR=%s EV R=%s R/YR=%s"
            % (d["n"], g("pf", "%.3f", 6), g("wr", "%.1f", 5), g("net", "%.0f", 9),
               g("dd", "%.0f", 8), g("mar", "%.2f", 6), g("evr", "%.3f", 6),
               g("ryr", "%.1f", 6)))


def run_case(label, plugin, params, out):
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    if not m:
        raise SystemExit("no NQ 1m ETH master")
    arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    idx = pd.DatetimeIndex(arr["index"])
    r = run_backtest(plugin, arrays=arr, params=(dict(params) if params else {}),
                     cost_pts=COST, return_trades=True)
    trades = r.get("trades") or []          # (entry_i, exit_i, pnl_pts, side, entry_price)
    if not trades:
        print("%-24s NO TRADES" % label)
        return

    # the master's index is tz-aware ET (load_master_arrays factorizes day_id on the ET
    # calendar date); every boundary below is stamped into the SAME zone so a comparison
    # never silently compares naive to aware -- or, worse, shifts a boundary by hours.
    tz = idx.tz
    def _ts(s):
        t = pd.Timestamp(s)
        return t.tz_localize(tz) if (tz is not None and t.tz is None) else t

    split = _ts(SPLIT)
    rows = []
    for t in trades:
        ei, xi, pnl = int(t[0]), int(t[1]), float(t[2])
        rows.append((idx[ei], idx[min(xi, len(idx) - 1)], pnl))
    ent = pd.DatetimeIndex([x[0] for x in rows])
    ext = pd.DatetimeIndex([x[1] for x in rows])
    pnl = [x[2] for x in rows]
    hold_days = (ext - ent).days if hasattr(ext - ent, "days") else \
        [(b - a).days for a, b in zip(ent, ext)]

    sel_m = ent < split
    lb_m = ~sel_m
    y_sel = max((split - ent.min()).days, 1) / 365.25
    y_lb = max((_ts(WIN[1]) - split).days, 1) / 365.25
    y_all = max((_ts(WIN[1]) - _ts(WIN[0])).days, 1) / 365.25

    S = _stats([p for p, k in zip(pnl, sel_m) if k], y_sel)
    L = _stats([p for p, k in zip(pnl, lb_m) if k], y_lb)
    A = _stats(pnl, y_all)

    # top-10 concentration on the SELECTION stretch (never chosen on the lockbox)
    sp = sorted([p for p, k in zip(pnl, sel_m) if k])
    S10 = _stats(sp[:-10] if len(sp) > 10 else sp, y_sel)
    share = (1 - S10["net"] / S["net"]) * 100.0 if S["net"] else None

    # the RELOAD the engine grades on, for the divergence flag
    rl = run_backtest(plugin, instrument="NQ", timeframe="1m", session="eth",
                      source="db_noadj_eth", params=(dict(params) if params else {}),
                      cost_pts=COST, date_from=SPLIT, date_to=WIN[1])
    rl_n = int(rl.get("num_trades") or 0)
    longest = int(max(hold_days)) if len(hold_days) else 0
    diverge = (rl_n - L["n"])

    print("=" * 118)
    print("%s   [%s]" % (label, plugin))
    print("  SELECTION  %s..%s  %s" % (WIN[0], SPLIT, _fmt(S)))
    print("  LOCKBOX    %s..%s  %s   <- CONTINUOUS, sliced by ENTRY time" % (SPLIT, WIN[1], _fmt(L)))
    print("  WHOLE RUN                         %s" % _fmt(A))
    print("  engine expectancy_r=%.3f (my EV R whole-run %.3f)  |  longest hold %d days"
          % (float(r.get("expectancy_r") or 0), A["evr"] or 0, longest))
    print("  ex-top-10 (selection): net=$%.0f  EV R=%.3f  R/YR=%.1f   -> top-10 share of net %s"
          % (S10["net"], S10["evr"] or 0, S10["ryr"] or 0,
             ("%.0f%%" % share) if share is not None else "-"))
    print("  RELOAD lockbox n=%d vs CONTINUOUS n=%d  ->  %s"
          % (rl_n, L["n"],
             "AGREE" if abs(diverge) <= max(5, 0.1 * max(rl_n, 1))
             else "*** DIVERGENCE %+d -- the engine's lockbox verdict is not what this config would have traded ***" % diverge))
    out.append(dict(label=label, plugin=plugin, sel=S, lb=L, all=A, sel_ex10=S10,
                    top10_share=share, reload_n=rl_n, longest_hold_days=longest,
                    params=params))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="run #198 only; it MUST report 0 continuous lockbox trades")
    a = ap.parse_args()
    cases = SELFTEST if a.selftest else CASES
    out = []
    for label, plugin, params in cases:
        try:
            run_case(label, plugin, params, out)
        except Exception as e:
            print("%-24s FAILED: %s: %s" % (label, type(e).__name__, e))
    d = REPO / "tools" / "contlb_results"
    d.mkdir(exist_ok=True)
    p = d / ("selftest.json" if a.selftest else "enguq_eth.json")
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("\nwrote", p)
    if a.selftest and out:
        got_n, got_net = out[0]["all"]["n"], out[0]["all"]["net"]
        ok = (got_n == SELFTEST_EXPECT["n"] and abs(got_net - SELFTEST_EXPECT["net"]) < 0.01)
        print("SELFTEST %s -- #226 frozen control: n=%d (want %d), net=$%.2f (want $%.2f)"
              % ("PASS" if ok else "FAIL", got_n, SELFTEST_EXPECT["n"],
                 got_net, SELFTEST_EXPECT["net"]))
        if not ok:
            print("  the data or the plugin has moved since the control was certified -- "
                  "every number this tool prints is suspect until that is explained.")


if __name__ == "__main__":
    main()
