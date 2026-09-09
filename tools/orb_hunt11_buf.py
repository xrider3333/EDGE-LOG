"""
ORB ROUND 11 — fork BUF: adaptive breakout buffer / multi-bar confirmation.

The #314 crown's entry buffer (breakout_buf x opening-range width) is the SAME one
number that also sets the stop and the target. This driver sweeps the fork
ORB_3_6_BUF.py (augur_strategies/ORB_3_6_BUF.py) across:

  buf_mode              range (crown) | atr | hybrid
  buf_atr_mult          0.1, 0.2, 0.3, 0.5   (buf = this x a trailing session-range
                                              ATR proxy — the same trailing-60-session
                                              median atr_filter already computes)
  confirm_bars          1 (crown), 2, 3      (consecutive confirming closes required)
  confirm_close_beyond  off / on            (monotone push through the zone)

skipping meaningless cells (buf_atr_mult only matters in atr/hybrid; confirm_close_beyond
only matters when confirm_bars > 1). Every config is run ONCE on the whole master, then
sliced by date so every window shares the identical warm-up / filter history
(tools/orb_pick.py pattern).

    python tools/orb_hunt11_buf.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import IS_END, LB_END                            # noqa: E402
from tools.orb_hunt3 import robustness                               # noqa: E402
import importlib.util as ilu                                         # noqa: E402

COST, MULT = 0.533, 20.0
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

# ── the #314 crown params (fork knobs at their OFF/default values) ───────────
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
             partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
             breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
             atr_filter=0.75, vpace_filter=0.8,
             buf_mode="range", buf_atr_mult=0.0, confirm_bars=1, confirm_close_beyond=False)

FIVE_Y_START = "2021-08-13"
WINDOWS = [("FULL", "2010-06-07", LB_END), ("IS", "2010-06-07", IS_END),
           ("OOS", IS_END, LB_END), ("5y", FIVE_Y_START, LB_END)]

# ── build the grid ────────────────────────────────────────────────────────────
def build_grid():
    grid = [("CROWN", {})]                          # crown row first, always
    # buf_mode=range: sweep confirmation depth only (buf_atr_mult stays 0 — irrelevant)
    for cb_bars in (2, 3):
        for cb_beyond in (False, True):
            lab = "range/confirm%d%s" % (cb_bars, "/mono" if cb_beyond else "")
            grid.append((lab, dict(confirm_bars=cb_bars, confirm_close_beyond=cb_beyond)))
    # buf_mode=atr / hybrid: buf_atr_mult x confirm_bars x confirm_close_beyond
    for mode in ("atr", "hybrid"):
        for mult in (0.1, 0.2, 0.3, 0.5):
            for cb_bars in (1, 2, 3):
                beyonds = (False,) if cb_bars == 1 else (False, True)
                for cb_beyond in beyonds:
                    lab = "%s/%.1f/confirm%d%s" % (mode, mult, cb_bars, "/mono" if cb_beyond else "")
                    grid.append((lab, dict(buf_mode=mode, buf_atr_mult=mult,
                                            confirm_bars=cb_bars, confirm_close_beyond=cb_beyond)))
    return grid


GRID = build_grid()

_B = None


def bars():
    global _B
    if _B is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        _B = dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                  low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                  volume=df["volume"].values.astype(float),
                  day_id=pd.factorize(df["_dt"].dt.date)[0],
                  index=pd.DatetimeIndex(df["_dt"]))
    return _B


def sessions():
    b = bars()
    return pd.Series(b["index"].date).drop_duplicates().values


_FORK = None


def fork():
    global _FORK
    if _FORK is None:
        path = os.path.join(ROOT, "augur_strategies", "ORB_3_6_BUF.py")
        spec = ilu.spec_from_file_location("_orb36buf", path)
        _FORK = ilu.module_from_spec(spec)
        spec.loader.exec_module(_FORK)
    return _FORK


def run_of(over, want_confirm_dist=False):
    """Run one config ONCE on the whole master. Returns (trades, confirm_dist_atr)
    where trades = [(entry_datetime, net$)] up to LB_END, confirm_dist_atr parallel
    list of the ATR-normalised confirm-close distance (nan when not close_confirm or
    ATR unavailable)."""
    b = bars()
    params = dict(CROWN, **over)
    r = fork().run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **params)
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out, dist = [], []
    trades = (r or {}).get("trades") or []
    dists = (r or {}).get("confirm_dist_atr") or [np.nan] * len(trades)
    for t, dd in zip(trades, dists):
        d = idx[t[0]]
        if d <= le:
            out.append((d.tz_localize(None), (t[2] - COST) * MULT))
            dist.append(dd)
    return out, dist


def stats(tr, win_start, win_end, all_days):
    if len(tr) < 20:
        return None
    dts = [d for d, _ in tr]
    p = np.array([x for _, x in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    if yrs <= 0:
        return None
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    d0 = pd.Timestamp(win_start).date()
    d1 = pd.Timestamp(win_end).date()
    win_days = [d for d in all_days if d >= d0 and d <= d1]
    return dict(n=len(p), net=p.sum(), dd=dd,
                pf=(wins.sum() / abs(losses.sum())) if len(losses) else np.inf,
                evr=evr, ryr=(evr * len(p) / yrs) if (evr == evr and yrs > 0) else np.nan,
                tpy=len(p) / yrs if yrs > 0 else np.nan,
                mar=(p.sum() / yrs) / dd if dd else np.nan,
                worst12=rob["worst"], win12=rob["win_pct"], yrs=yrs,
                sess=100.0 * len({d.date() for d in dts}) / len(win_days) if win_days else np.nan)


def gate_check(rows, crown_row):
    """rows: dict window-label -> stats. crown_row: same shape for CROWN.
    Returns (pass_bool, list_of_fail_reasons)."""
    fails = []
    r5, c5 = rows.get("5y"), crown_row.get("5y")
    rF, cF = rows.get("FULL"), crown_row.get("FULL")
    rO, cO = rows.get("OOS"), crown_row.get("OOS")
    if r5 is None or c5 is None or rF is None or cF is None or rO is None or cO is None:
        return False, ["insufficient trades in one or more windows"]
    if not (r5["mar"] > 2.79):
        fails.append("G1 (5y MAR %.2f <= 2.79)" % r5["mar"])
    if not (rF["mar"] > 0.85):
        fails.append("G1 (FULL MAR %.2f <= 0.85)" % rF["mar"])
    if not (rF["net"] >= 0.95 * 397150):
        fails.append("G2 (FULL net $%.0f < 95%% of $397,150)" % rF["net"])
    if not (rO["net"] >= cO["net"]):
        fails.append("G3 (OOS net $%.0f < crown $%.0f)" % (rO["net"], cO["net"]))
    if not (rO["pf"] >= cO["pf"]):
        fails.append("G3 (OOS PF %.3f < crown %.3f)" % (rO["pf"], cO["pf"]))
    if rF["tpy"] < 120:
        fails.append("G5 (trades/yr %.0f < 120)" % rF["tpy"])
    return (len(fails) == 0), fails


def main():
    all_days = sessions()
    print("=" * 148)
    print("ORB ROUND 11 — fork BUF: adaptive breakout buffer / multi-bar confirmation")
    print("  master NQ 5m RTH no-adj, $0.533/RT, one contract. FULL<=%s, IS<=%s, OOS %s..%s, 5y from %s"
          % (LB_END, IS_END, IS_END, LB_END, FIVE_Y_START))
    print("=" * 148)

    cache = {}
    dist_cache = {}
    for lab, over in GRID:
        tr, dist = run_of(over)
        cache[lab] = tr
        dist_cache[lab] = dist

    # per-window stats table, one window at a time, crown row first always
    all_rows = {lab: {} for lab, _ in GRID}
    for wlab, wstart, wend in WINDOWS:
        s0 = pd.Timestamp(wstart); s1 = pd.Timestamp(wend)
        for lab, _ in GRID:
            tr = [(d, v) for d, v in cache[lab] if s0 <= d <= s1]
            s = stats(tr, wstart, wend, all_days)
            if s:
                all_rows[lab][wlab] = s

    for wlab, wstart, wend in WINDOWS:
        print("\n" + "-" * 148)
        print("%s window   (%s .. %s)" % (wlab, wstart, wend))
        print("%-28s %6s %10s %9s %6s %6s %6s %6s %5s %6s"
              % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "wst12", "win12%"))
        print("-" * 148)
        for lab, _ in GRID:
            s = all_rows[lab].get(wlab)
            if not s:
                print("%-28s  (fewer than 20 trades in this window)" % lab)
                continue
            print("%-28s %6d %10s %9s %6.3f %6.2f %6.3f %6.1f %5s %6.1f"
                  % (lab, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"],
                     s["evr"], s["ryr"], f"{s['worst12']:,.0f}", s["win12"]))

    # ── gates, honestly, every config ────────────────────────────────────────
    print("\n" + "=" * 148)
    print("GATE CHECK  (G1 5y MAR>2.79 & FULL MAR>0.85 | G2 FULL net>=95%% of $397,150 | "
          "G3 OOS net & PF >= crown | G4 plateau | G5 trades/yr>=120)")
    print("=" * 148)
    crown_row = all_rows["CROWN"]
    verdicts = {}
    for lab, _ in GRID:
        ok, fails = gate_check(all_rows[lab], crown_row)
        verdicts[lab] = (ok, fails)
        tag = "PASS" if ok else "FAIL: " + "; ".join(fails)
        print("%-28s %s" % (lab, tag if lab != "CROWN" else "(baseline, not gated against itself)"))

    # ── plateau read on the best-by-5y-MAR non-crown config ─────────────────
    print("\n" + "-" * 148)
    print("PLATEAU READ")
    cands = [(lab, all_rows[lab]["5y"]["mar"]) for lab, _ in GRID
             if lab != "CROWN" and "5y" in all_rows[lab]]
    if not cands:
        print("No config had >=20 trades in the 5y window - no plateau read possible.")
    else:
        best_lab, best_mar = max(cands, key=lambda x: x[1])
        crown_mar = crown_row["5y"]["mar"] if "5y" in crown_row else np.nan
        gain = best_mar - crown_mar
        print("Best (non-crown) by 5y MAR: %-28s MAR %.2f  (crown %.2f, gain %+.2f)"
              % (best_lab, best_mar, crown_mar, gain))
        # neighbours = same buf_mode/mode family, one step off on confirm_bars or buf_atr_mult
        best_over = dict(GRID)[best_lab]
        neigh_labs = []
        for lab, over in GRID:
            if lab == best_lab or lab == "CROWN":
                continue
            same_mode = over.get("buf_mode", "range") == best_over.get("buf_mode", "range")
            close_mult = abs(over.get("buf_atr_mult", 0.0) - best_over.get("buf_atr_mult", 0.0)) <= 0.1 + 1e-9
            close_bars = abs(over.get("confirm_bars", 1) - best_over.get("confirm_bars", 1)) <= 1
            if same_mode and close_mult and close_bars:
                neigh_labs.append(lab)
        if gain <= 0:
            print("Best config does not beat the crown's 5y MAR at all - NOT A PLATEAU, NOT A FIND.")
        elif not neigh_labs:
            print("No immediate neighbours found in the grid for %s - NOT PLATEAU (isolated point)." % best_lab)
        else:
            bad = []
            for nl in neigh_labs:
                nmar = all_rows[nl]["5y"]["mar"] if "5y" in all_rows[nl] else np.nan
                if nmar != nmar:
                    bad.append((nl, "no trades"))
                    continue
                ngain = nmar - crown_mar
                if ngain < 0.70 * gain:
                    bad.append((nl, "%.2f (%.0f%% of gain)" % (nmar, 100 * ngain / gain if gain else 0)))
            for nl in neigh_labs:
                nmar = all_rows[nl]["5y"]["mar"] if "5y" in all_rows[nl] else np.nan
                print("   neighbour %-28s 5y MAR %s" % (nl, ("%.2f" % nmar) if nmar == nmar else "n/a"))
            if bad:
                print("NOT PLATEAU: neighbour(s) %s fall below 70%% of the gain." % [b[0] for b in bad])
            else:
                print("PLATEAU: every immediate neighbour keeps >=70%% of the 5y MAR gain over the crown.")

    # ── diagnostic: crown's own trades, bucketed by confirm-close distance/ATR ─
    print("\n" + "=" * 148)
    print("DIAGNOSTIC (not gated): CROWN's own confirming-close distance beyond the level, in ATR units,")
    print("bucketed - does a bigger or smaller entry threshold have anything to bite on? (5y window)")
    print("=" * 148)
    crown_tr = cache["CROWN"]
    crown_dist = dist_cache["CROWN"]
    s0 = pd.Timestamp(FIVE_Y_START)
    rows5 = [(d, v, dd) for (d, v), dd in zip(crown_tr, crown_dist) if d >= s0]
    valid = [(d, v, dd) for d, v, dd in rows5 if dd == dd]
    n_novalid = len(rows5) - len(valid)
    if not valid:
        print("No trades with a valid ATR-normalised confirm distance in the 5y window "
              "(ATR proxy needs >=6 warm-up sessions) - diagnostic empty.")
    else:
        dists = np.array([dd for _, _, dd in valid])
        edges = np.quantile(dists, [0.0, 0.25, 0.5, 0.75, 1.0])
        # de-dup edges (can collide on ties) and build quartile buckets
        edges = np.unique(edges)
        if len(edges) < 2:
            print("Distances have no spread (all equal ~%.3f ATR) - cannot bucket." % dists[0])
        else:
            print("%-24s %6s %10s %6s %7s" % ("bucket (ATR units)", "n", "net$", "PF", "EV R"))
            print("-" * 60)
            qs = np.quantile(dists, [0.0, 0.25, 0.5, 0.75, 1.0])
            for qi in range(4):
                lo, hi = qs[qi], qs[qi + 1]
                if qi == 0:
                    sel = [(v) for _, v, dd in valid if lo <= dd <= hi]
                else:
                    sel = [(v) for _, v, dd in valid if lo < dd <= hi]
                if not sel:
                    continue
                p = np.array(sel, float)
                wins, losses = p[p > 0], p[p < 0]
                pf = wins.sum() / abs(losses.sum()) if len(losses) else np.inf
                al = abs(losses.mean()) if len(losses) else np.nan
                evr = p.mean() / al if al == al and al > 0 else np.nan
                print("Q%d  [%.3f, %.3f]%-8s %6d %10s %6.3f %7.3f"
                      % (qi + 1, lo, hi, "", len(p), f"{p.sum():,.0f}", pf, evr))
        if n_novalid:
            print("(%d of %d crown trades in the 5y window had no valid ATR proxy - excluded.)"
                  % (n_novalid, len(rows5)))


if __name__ == "__main__":
    main()
