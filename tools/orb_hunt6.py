"""
ORB HUNT ROUND 6 (2026-09-04) - owner: "find an ORB configuration that beats the crown
on BOTH EV R and R / YR without giving up robustness".

Two new columns join the round-5 table, both leverage-blind:
    EV R   = (net $ / trades) / average losing trade $   (expectancy in R, R = avg loser)
    R / YR = EV R x trades per year                       (how much of that per calendar year)
They are the same arithmetic augur_engine/analytics.py uses for a real Auto-Validate
(expectancy_r / avg_win_loss / sharpe / sortino), called here on the cost-adjusted
dollar trade list so a row in this file matches what the STUDIES board would print.
When a config scales out (partial_exit_R > 0) the plugin logs TWO legs per trade; the
legs are merged by entry bar before scoring so "a trade" and "R" mean one thing across
every sweep - otherwise the partial sweep would count 2x trades at half the size.

CROWN = run #234 = INCUMBENT in tools/orb_hunt3 (or_bars 2, first-candle dir, stop 2.0,
buf 0.25, close-confirm, no partial, no trail, target 5.5R, BE after 1.0R, atr 0.7,
vpace 0.7) on ORB_3_6.py.  F8080 = the validated tighter-filter variant (#298 PASS).

PRE-REGISTERED GATE - written here BEFORE any sweep was run and not changed after.
A cell is a CANDIDATE only if, on the pinned window (entries <= 2026-08-13, IS_END
2025-08-13, cost 0.533 pts/RT, $20/pt), it clears ALL FOUR legs at once:
    1. EV R    >  the crown's measured EV R
    2. R / YR  >  the crown's measured R / YR
    3. lockbox net (entries after 2025-08-13)  >=  $88,943   (the crown's)
    4. worst rolling-12-month result          >=  -$22,050  (the crown's)
Legs 1-2 are measured against the crown ON THIS HARNESS (printed first, sanity: crown
net $389,874, F8080 $367,833); legs 3-4 are the fixed numbers from rounds 3-5. A cell
that clears the gate goes to a PINNED Auto-Validate; nothing is adopted from this file.

SWEEPS
    A. interact  - re-tune exits under tighter filters (filters x stop x target x BE)
    B. direction - trade_mode Both / Long Only / Short Only x filters x breakout_buf
    C. partial   - partial_exit_R x trail_bars at crown filters and (0.8, 0.8)
    D. ridge     - the far end of the validated filter ridge (atr x vpace x stop)

    python tools/orb_hunt6.py base            # crown + F8080 only
    python tools/orb_hunt6.py interact|direction|partial|ridge
    python tools/orb_hunt6.py all
Every sweep writes scratchpad/orb6_<sub>.json with one record per cell.
"""
import os
import sys
import json
import itertools

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, score, IS_END, LB_END              # noqa: E402
from tools.orb_hunt3 import INCUMBENT, robustness                     # noqa: E402
from tools.orb_hunt5 import bars, MASTER                              # noqa: E402,F401
from augur_engine.analytics import (sharpe_from_pnls, sortino_from_pnls)  # noqa: E402

COST, MULT = 0.533, 20.0
GATE_LB, GATE_WORST = 88943.0, -22050.0          # legs 3-4, fixed since round 3
F8080 = dict(INCUMBENT, atr_filter=0.8, vpace_filter=0.8)

OUT_DIR = os.environ.get("ORB6_OUT") or (
    r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop"
    r"\a9e4eec9-eca2-494f-9f8f-ef843d44c8b9\scratchpad")

# filled by measure_base(); legs 1-2 of the gate compare against these
CROWN = {}


def _window_years():
    """Calendar years from the first bar to LB_END - the same span every cell covers."""
    idx = bars()["index"]
    end = pd.Timestamp(LB_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(LB_END)
    return (min(idx[-1], end) - idx[0]).total_seconds() / 86400.0 / 365.25


def run(params, strategy="ORB_3_6.py"):
    """One config on the pinned master -> full / IS / LB / robustness / EV R / R-YR."""
    b = bars()
    mod = strat(strategy)
    r = mod.run_backtest(b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
                         day_id=b["day_id"], return_trades=True, **params)
    tr = (r or {}).get("trades") or []
    if not tr:
        return None
    idx = b["index"]
    le = pd.Timestamp(LB_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(LB_END)
    ie = pd.Timestamp(IS_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(IS_END)
    keep = [t for t in tr if idx[t[0]] <= le]
    if not keep:
        return None
    # merge scale-out legs that share an entry bar -> one trade, one cost
    merged = {}
    for t in keep:
        merged[t[0]] = merged.get(t[0], 0.0) + float(t[2])
    ents = sorted(merged)
    raw = [merged[e] for e in ents]
    dts = [idx[e] for e in ents]
    pnl = [(x - COST) * MULT for x in raw]
    f = score(raw, mult=MULT, cost=COST)
    years = _window_years()
    losses = [-p for p in pnl if p < 0]
    avg_loss = (sum(losses) / len(losses)) if losses else None
    wins = [p for p in pnl if p > 0]
    avg_win = (sum(wins) / len(wins)) if wins else None
    evr = (f["net"] / len(pnl)) / avg_loss if avg_loss else None
    n = len(pnl)
    return dict(full=f, n=n,
                is_net=sum(p for d, p in zip(dts, pnl) if d <= ie),
                lb_net=sum(p for d, p in zip(dts, pnl) if d > ie),
                rob=robustness([d.tz_localize(None) for d in dts], pnl),
                avg_win=avg_win, avg_loss=avg_loss, evr=evr,
                ryr=(evr * n / years) if evr is not None else None,
                tpy=n / years, years=years,
                sharpe=sharpe_from_pnls(pnl, years), sortino=sortino_from_pnls(pnl, years))


def gate_legs(m):
    """Which of the four pre-registered legs a cell clears."""
    if not m or m["evr"] is None:
        return dict(evr=False, ryr=False, lb=False, worst=False)
    return dict(evr=m["evr"] > CROWN["evr"], ryr=m["ryr"] > CROWN["ryr"],
                lb=m["lb_net"] >= GATE_LB, worst=m["rob"]["worst"] >= GATE_WORST)


def passes(m):
    return all(gate_legs(m).values())


def record(name, over, m):
    if not m:
        return dict(name=name, params=over, n=0, passes=False, gate_legs={})
    f = m["full"]
    legs = gate_legs(m)
    return dict(name=name, params=over, n=m["n"], net=f["net"], is_net=m["is_net"],
                lb_net=m["lb_net"], dd=abs(f["dd"]), pf=f["pf"], wr=f["wr"],
                sharpe=m["sharpe"], sortino=m["sortino"], avg_loss_usd=m["avg_loss"],
                avg_win_usd=m["avg_win"], evr=m["evr"], ryr=m["ryr"], tpy=m["tpy"],
                roll12_win=m["rob"]["win_pct"], roll12_worst=m["rob"]["worst"],
                gate_legs=legs, passes=all(legs.values()))


def header(title):
    print("=" * 132)
    print(title)
    print("  gate: EV R > %.3f  AND  R/YR > %.2f  AND  lockbox >= $%s  AND  worst roll12 >= $%s"
          % (CROWN["evr"], CROWN["ryr"], f"{GATE_LB:,.0f}", f"{GATE_WORST:,.0f}"))
    print("=" * 132)
    print("%-36s %10s %9s %8s %6s %5s %6s %6s %9s %5s %6s %6s %-5s"
          % ("config", "NET $", "LB $", "DD $", "PF", "trd", "EV R", "R/YR",
             "worst12", "win%", "avgL$", "sharpe", "legs"))
    print("-" * 132)


def line(label, m, flag=""):
    if not m:
        print("%-36s %10s" % (label[:36], "no trades"))
        return
    f = m["full"]
    legs = gate_legs(m)
    lg = "".join(k[0].upper() if v else "." for k, v in legs.items())
    print("%-36s %10s %9s %8s %6.3f %5d %6.3f %6.2f %9s %5.1f %6.0f %6.2f %-5s %s"
          % (label[:36], f"{f['net']:,.0f}", f"{m['lb_net']:,.0f}", f"{abs(f['dd']):,.0f}",
             f["pf"], m["n"], m["evr"], m["ryr"], f"{m['rob']['worst']:,.0f}",
             m["rob"]["win_pct"], m["avg_loss"] or 0, m["sharpe"] or 0, lg, flag))


def measure_base():
    """The crown and F8080 on this harness. Sets CROWN for gate legs 1-2."""
    global CROWN
    c = run(INCUMBENT)
    CROWN = dict(evr=c["evr"], ryr=c["ryr"])
    header("BASELINES on this harness (sanity: crown $389,874 / F8080 $367,833)")
    line("CROWN #234", c)
    f = run(F8080)
    line("F8080 (#298, atr .8 / vpace .8)", f)
    for lab, m in (("CROWN", c), ("F8080", f)):
        print("  %s: EV R %.4f | R/YR %.3f | net $%s | DD $%s | PF %.3f | LB $%s | roll12 win %.1f%% "
              "worst $%s | avg loss $%.0f | avg win $%.0f | trades %d (%.1f/yr, %.2f yrs) | sharpe %.2f sortino %.2f"
              % (lab, m["evr"], m["ryr"], f"{m['full']['net']:,.0f}", f"{abs(m['full']['dd']):,.0f}",
                 m["full"]["pf"], f"{m['lb_net']:,.0f}", m["rob"]["win_pct"], f"{m['rob']['worst']:,.0f}",
                 m["avg_loss"], m["avg_win"], m["n"], m["tpy"], m["years"], m["sharpe"], m["sortino"]))
    return c, f


def sweep(sub, cells, strategy="ORB_3_6.py"):
    """cells: [(label, overrides)]. Prints a row per cell, writes the JSON, returns hits."""
    recs, hits = [], []
    for label, over in cells:
        p = dict(INCUMBENT, **over)
        try:
            m = run(p, strategy=strategy)
        except Exception as e:                       # a bad cell must not kill the sweep
            print("%-36s ERROR %s: %s" % (label[:36], type(e).__name__, e))
            recs.append(dict(name=label, params=over, error="%s: %s" % (type(e).__name__, e),
                             passes=False, gate_legs={}))
            continue
        ok = passes(m)
        line(label, m, "  <== CLEARS GATE" if ok else "")
        sys.stdout.flush()
        recs.append(record(label, over, m))
        if ok:
            hits.append((label, dict(over), m))
    print("-" * 132)
    print("cells: %d | cleared the full gate: %d" % (len(cells), len(hits)))
    for label, over, m in hits:
        print("   %s  ->  %s" % (label, over))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "orb6_%s.json" % sub)
    with open(path, "w") as fh:
        json.dump(dict(crown=CROWN, gate_lb=GATE_LB, gate_worst=GATE_WORST, cells=recs), fh, indent=1)
    print("wrote %s" % path)
    return hits


# -- A. exits under tighter filters ---------------------------------------------------
def sweep_interact():
    header("A. INTERACT - re-tune stop / target / BE under tighter filters")
    cells = []
    for (a, v), sf, tr, be in itertools.product([(0.70, 0.70), (0.75, 0.80), (0.80, 0.80)],
                                                 [1.5, 1.75, 2.0, 2.5],
                                                 [4.5, 5.0, 5.5, 6.5, 0.0],
                                                 [0.5, 0.75, 1.0, 1.25]):
        cells.append(("f%.2f/%.2f sf%.2f tR%.1f be%.2f" % (a, v, sf, tr, be),
                      dict(atr_filter=a, vpace_filter=v, stop_frac=sf, target_R=tr, be_after_R=be)))
    return sweep("interact", cells)


# -- B. direction ---------------------------------------------------------------------
def sweep_direction():
    header("B. DIRECTION - Both / Long Only / Short Only")
    cells = []
    for mode, (a, v), buf in itertools.product(["Both", "Long Only", "Short Only"],
                                               [(0.7, 0.7), (0.8, 0.8)], [0.25, 0.30, 0.40]):
        cells.append(("%s f%.1f/%.1f buf%.2f" % (mode, a, v, buf),
                      dict(trade_mode=mode, atr_filter=a, vpace_filter=v, breakout_buf=buf)))
    return sweep("direction", cells)


# -- C. partial / trail ---------------------------------------------------------------
def sweep_partial():
    header("C. PARTIAL - does scaling out raise EV R? (legs merged per trade)")
    cells = []
    for (a, v), pr, tb in itertools.product([(0.7, 0.7), (0.8, 0.8)], [2.0, 3.0, 4.0], [0, 3, 5]):
        cells.append(("f%.1f/%.1f partial%.0fR trail%d" % (a, v, pr, tb),
                      dict(atr_filter=a, vpace_filter=v, partial_exit_R=pr, trail_bars=tb)))
    return sweep("partial", cells)


# -- D. ridge -------------------------------------------------------------------------
def sweep_ridge():
    header("D. RIDGE - the far end of the validated filter ridge")
    cells = []
    for a, v, sf in itertools.product([0.75, 0.80, 0.85, 0.90, 1.0], [0.80, 0.90, 1.0, 1.1], [2.0, 2.5]):
        cells.append(("atr%.2f vpace%.2f sf%.1f" % (a, v, sf),
                      dict(atr_filter=a, vpace_filter=v, stop_frac=sf)))
    return sweep("ridge", cells)


SWEEPS = {"interact": sweep_interact, "direction": sweep_direction,
          "partial": sweep_partial, "ridge": sweep_ridge}

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "base"
    if what not in SWEEPS and what not in ("base", "all"):
        sys.exit("usage: orb_hunt6.py [base|interact|direction|partial|ridge|all]")
    measure_base()
    todo = list(SWEEPS) if what == "all" else ([] if what == "base" else [what])
    total = []
    for sub in todo:
        print()
        total += SWEEPS[sub]()
    print()
    print("=" * 132)
    print("ROUND 6 / %s: %d cell(s) cleared the pre-registered gate." % (what.upper(), len(total)))
    print("=" * 132)
