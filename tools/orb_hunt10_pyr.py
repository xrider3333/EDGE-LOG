"""
ROUND 10 — PYRAMIDING fork sweep (ORB_3_6_PYR.py) vs the #314 crown.

Adds a unit into a WORKING trade once price closes pyr_add_R x risk past entry (shared
or own stop, up to pyr_max adds), same original target for every unit. Every config is
run ONCE on the whole master, sliced by date afterwards so FULL/IS/OOS/5y all see the
identical warm-up and filter history (tools/orb_pick.py pattern).

Reports, per window: config | n | net | maxDD | PF | MAR | EV R | R/YR | worst12 | win12%
Then, because pyramiding raises average exposure, a SECOND read scales each config's own
net/DD by its own average units-per-trade — this leaves MAR bit-for-bit unchanged (both
numerator and denominator divide by the same constant) so it isolates: did MAR actually
improve (real edge), or did only raw net improve (pure leverage)?  Finally reports the
ADDED units' own PnL in isolation (n adds fired, net $ of adds only, PF of adds only).

Pre-registered gates (ROUND10_SPEC.md), evaluated against the FULL/IS/OOS/5y numbers
computed by THIS harness:
  G1: 5y MAR > 2.79  AND  full MAR > 0.85
  G2: full net >= 95% of $397,150
  G3: OOS net >= crown's OOS net (this harness)  AND  OOS PF >= crown's OOS PF
  G4: plateau — immediate neighbours of the best config keep >=70% of its 5y MAR
      gain over the crown
  G5: trades/yr (FULL window) >= 120

Usage:  python tools/orb_hunt10_pyr.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END          # noqa: E402
from tools.orb_hunt3 import robustness                    # noqa: E402

COST, MULT = 0.533, 20.0
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
             partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
             breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
             atr_filter=0.75, vpace_filter=0.8)

FIVE_Y_START = "2021-08-13"
WINDOWS = [("FULL", None, LB_END), ("IS", None, IS_END), ("OOS", IS_END, LB_END),
           ("5y", FIVE_Y_START, LB_END)]

# Pre-registered gate constants (run #314's own numbers, ROUND10_SPEC.md).
G1_5Y_MAR, G1_FULL_MAR = 2.79, 0.85
G2_FULL_NET_FLOOR = 0.95 * 397150.0
G5_TPY_FLOOR = 120.0

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


def trades_of(over):
    """Run ORB_3_6_PYR ONCE on the whole master; slice by date afterwards."""
    b = bars()
    r = strat("ORB_3_6_PYR.py").run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **dict(CROWN, **over))
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        entry_i, exit_i, total_pnl, dirn, entry_px, n_units, avg_pu, add_pnls = t
        d = idx[entry_i]
        if d > le:
            continue
        net = (total_pnl - COST * n_units) * MULT
        add_net = [(p - COST) * MULT for p in add_pnls]
        out.append(dict(dt=d.tz_localize(None), net=net, n_units=n_units, add_net=add_net))
    return out


def stats(tr, start):
    """tr = list of trade dicts already inside the window."""
    if len(tr) < 15:
        return None
    dts = [t["dt"] for t in tr]
    p = np.array([t["net"] for t in tr], float)
    units = np.array([t["n_units"] for t in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    if yrs <= 0:
        return None
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    avg_units = float(units.mean())
    all_adds = [x for t in tr for x in t["add_net"]]
    aw = [x for x in all_adds if x > 0]; al_ = [x for x in all_adds if x < 0]
    add_pf = (sum(aw) / abs(sum(al_))) if al_ else (np.inf if aw else np.nan)
    return dict(
        n=len(p), net=float(p.sum()), dd=dd,
        pf=(wins.sum() / abs(losses.sum())) if len(losses) else np.inf,
        mar=(p.sum() / yrs) / dd if dd else np.nan,
        evr=evr, ryr=evr * len(p) / yrs if yrs > 0 and evr == evr else np.nan,
        tpy=len(p) / yrs, worst12=rob["worst"], win12=rob["win_pct"],
        avg_units=avg_units,
        scaled_net=float(p.sum()) / avg_units if avg_units else np.nan,
        scaled_dd=dd / avg_units if avg_units else np.nan,
        n_adds=len(all_adds), add_net=float(sum(all_adds)), add_pf=add_pf,
    )


def _row(cfg_lab, s):
    return ("%-30s %6d %11s %10s %6.3f %6.2f %6.3f %6.1f %9s %5.1f"
            % (cfg_lab, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"],
               s["evr"], s["ryr"], f"{s['worst12']:,.0f}", s["win12"]))


def build_configs():
    configs = [("CROWN (pyr_add_R=0)", {})]
    for add_r in (0.5, 1.0, 1.5, 2.0, 3.0):
        for stop_mode in ("shared", "own"):
            for pmax in (1, 2):
                over = dict(pyr_add_R=add_r, pyr_stop=stop_mode, pyr_max=pmax)
                if stop_mode == "own":
                    over["pyr_stop_frac"] = CROWN["stop_frac"]
                lab = "addR=%.1f/%s/max%d" % (add_r, stop_mode, pmax)
                configs.append((lab, over))
    return configs


def main():
    lines = []

    def P(s=""):
        print(s); lines.append(s)

    configs = build_configs()
    P("=" * 132)
    P("ROUND 10 — ORB_3_6_PYR pyramiding sweep vs the #314 crown")
    P("  master NQ 5m RTH no-adj, %.3f pts/RT PER UNIT, $%d/pt, entries to %s" % (COST, MULT, LB_END))
    P("=" * 132)

    cache = {lab: trades_of(over) for lab, over in configs}

    win_stats = {}   # window_label -> {cfg_lab: stats}
    for wlab, wstart, wend in WINDOWS:
        P("\n" + "-" * 132)
        P("%s window  (from %s to %s)" % (wlab, wstart or "start", wend))
        P("-" * 132)
        P("%-30s %6s %11s %10s %6s %6s %6s %6s %9s %5s"
          % ("config", "n", "net$", "maxDD$", "PF", "MAR", "EV R", "R/YR", "worst12", "w12%"))
        rows = {}
        for lab, over in configs:
            tr = cache[lab]
            if wstart:
                tr = [t for t in tr if t["dt"] >= pd.Timestamp(wstart)]
            if wend:
                tr = [t for t in tr if t["dt"] < pd.Timestamp(wend)]
            s = stats(tr, wstart)
            if s:
                rows[lab] = s
                P(_row(lab, s))
            else:
                P("%-30s   (too few trades in window)" % lab)
        win_stats[wlab] = rows

    # ── Fairness read: scale net/DD by each config's own avg units/trade ──────
    P("\n" + "=" * 132)
    P("FAIRNESS READ — FULL window, net/DD divided by the CONFIG'S OWN avg units-per-trade")
    P("  (MAR is bit-identical to the raw table above: both numerator and denominator")
    P("   are divided by the same constant, so this isolates leverage from real edge.)")
    P("=" * 132)
    P("%-30s %8s %11s %10s %6s   %s" % ("config", "avgUnit", "net/unit$", "DD/unit$", "MAR", "read"))
    crown_full = win_stats["FULL"].get("CROWN (pyr_add_R=0)")
    for lab, _ in configs:
        s = win_stats["FULL"].get(lab)
        if not s:
            continue
        if lab.startswith("CROWN"):
            read = "baseline"
        else:
            mar_better = s["mar"] > crown_full["mar"]
            net_better = s["net"] > crown_full["net"]
            if mar_better:
                read = "MAR IMPROVES (real edge)"
            elif net_better:
                read = "net only (leverage)"
            else:
                read = "worse on both"
        P("%-30s %8.2f %11s %10s %6.2f   %s" % (
            lab, s["avg_units"], f"{s['scaled_net']:,.0f}", f"{s['scaled_dd']:,.0f}",
            s["mar"], read))

    # ── Added units' own PnL, FULL window ──────────────────────────────────────
    P("\n" + "=" * 132)
    P("ADDED UNITS ONLY — FULL window (excludes unit 1 / the original entry)")
    P("=" * 132)
    P("%-30s %8s %11s %8s" % ("config", "n adds", "net$ adds", "PF adds"))
    for lab, _ in configs:
        s = win_stats["FULL"].get(lab)
        if not s or lab.startswith("CROWN"):
            continue
        P("%-30s %8d %11s %8s" % (lab, s["n_adds"], f"{s['add_net']:,.0f}",
                                   ("inf" if s["add_pf"] == np.inf else
                                    ("n/a" if s["add_pf"] != s["add_pf"] else "%.3f" % s["add_pf"]))))

    # ── Gates ───────────────────────────────────────────────────────────────────
    P("\n" + "=" * 132)
    P("GATES (pre-registered, ROUND10_SPEC.md)")
    P("=" * 132)
    crown_oos = win_stats["OOS"].get("CROWN (pyr_add_R=0)")
    gate_results = {}
    for lab, _ in configs:
        if lab.startswith("CROWN"):
            continue
        s_full = win_stats["FULL"].get(lab)
        s_5y = win_stats["5y"].get(lab)
        s_oos = win_stats["OOS"].get(lab)
        if not (s_full and s_5y and s_oos):
            gate_results[lab] = ("FAIL", "insufficient trades")
            continue
        fails = []
        if not (s_5y["mar"] > G1_5Y_MAR and s_full["mar"] > G1_FULL_MAR):
            fails.append("G1(5yMAR=%.2f,fullMAR=%.2f)" % (s_5y["mar"], s_full["mar"]))
        if not (s_full["net"] >= G2_FULL_NET_FLOOR):
            fails.append("G2(fullNet=%.0f<%.0f)" % (s_full["net"], G2_FULL_NET_FLOOR))
        if not (s_oos["net"] >= crown_oos["net"] and s_oos["pf"] >= crown_oos["pf"]):
            fails.append("G3(oosNet=%.0f/%.0f,oosPF=%.2f/%.2f)" % (
                s_oos["net"], crown_oos["net"], s_oos["pf"], crown_oos["pf"]))
        if not (s_full["tpy"] >= G5_TPY_FLOOR):
            fails.append("G5(tpy=%.0f<%.0f)" % (s_full["tpy"], G5_TPY_FLOOR))
        gate_results[lab] = ("PASS", "-") if not fails else ("FAIL", ", ".join(fails))

    # best config for the plateau check (G4) = best 5y MAR among configs that
    # already PASS G1/G2/G3/G5 (a config that fails those on its own merits isn't
    # "the best config" just because it has a big 5y number).
    ranked = sorted(
        [(lab, win_stats["5y"][lab]["mar"]) for lab, _ in configs
         if lab in win_stats["5y"] and not lab.startswith("CROWN")
         and gate_results.get(lab, ("FAIL",))[0] == "PASS"],
        key=lambda x: -x[1])
    best_lab = ranked[0][0] if ranked else None
    crown_5y_mar = win_stats["5y"]["CROWN (pyr_add_R=0)"]["mar"]

    plateau_note = "no best config found"
    if best_lab:
        add_r, stop_mode, pmax = None, None, None
        for tok in best_lab.replace("addR=", "").split("/"):
            pass
        parts = best_lab.split("/")
        add_r = float(parts[0].split("=")[1])
        stop_mode = parts[1]
        pmax = int(parts[2].replace("max", ""))
        best_gain = win_stats["5y"][best_lab]["mar"] - crown_5y_mar

        def cfg_lab(a, s_, m):
            return "addR=%.1f/%s/max%d" % (a, s_, m)

        neighbours = []
        adds = [0.5, 1.0, 1.5, 2.0, 3.0]
        ai = adds.index(add_r)
        if ai > 0:
            neighbours.append(cfg_lab(adds[ai - 1], stop_mode, pmax))
        if ai < len(adds) - 1:
            neighbours.append(cfg_lab(adds[ai + 1], stop_mode, pmax))
        other_stop = "own" if stop_mode == "shared" else "shared"
        neighbours.append(cfg_lab(add_r, other_stop, pmax))
        other_pmax = 2 if pmax == 1 else 1
        neighbours.append(cfg_lab(add_r, stop_mode, other_pmax))

        if best_gain <= 0:
            plateau_note = "best config (%s) does NOT beat crown 5y MAR (%.2f vs %.2f) -> NOT PLATEAU (no gain to hold)" % (
                best_lab, win_stats["5y"][best_lab]["mar"], crown_5y_mar)
        else:
            worst_ratio = None
            detail = []
            for nb in neighbours:
                if nb not in win_stats["5y"]:
                    detail.append("%s: no trades" % nb)
                    worst_ratio = -1
                    continue
                nb_gain = win_stats["5y"][nb]["mar"] - crown_5y_mar
                ratio = nb_gain / best_gain
                detail.append("%s: keeps %.0f%%" % (nb, 100 * ratio))
                if worst_ratio is None or ratio < worst_ratio:
                    worst_ratio = ratio
            ok = worst_ratio is not None and worst_ratio >= 0.70
            plateau_note = "%s best=%s (5yMAR %.2f, gain %.2f over crown %.2f); neighbours: %s" % (
                "PLATEAU" if ok else "NOT PLATEAU", best_lab, win_stats["5y"][best_lab]["mar"],
                best_gain, crown_5y_mar, "; ".join(detail))

    P("%-30s %-6s %s" % ("config", "gate", "detail"))
    for lab, _ in configs:
        if lab.startswith("CROWN"):
            continue
        g, detail = gate_results.get(lab, ("FAIL", "not run"))
        P("%-30s %-6s %s" % (lab, g, detail))
    P("\nG4 PLATEAU CHECK (best config by 5y MAR): %s" % plateau_note)

    n_pass = sum(1 for g, _ in gate_results.values() if g == "PASS")
    P("\n%d / %d configs PASS all gates." % (n_pass, len(gate_results)))

    return "\n".join(lines)


if __name__ == "__main__":
    text = main()
    out_path = os.path.join(ROOT, "ROUND10_pyr.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\nwritten -> %s" % out_path)
