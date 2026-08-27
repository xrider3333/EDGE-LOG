"""
ORB HUNT ROUND 5 (2026-08-26) — owner: "do more testing while im away. new / better
params / versions of this".

Three studies on the run #234 crown, all destined for COMPARE > STUDIES.

A. THE TWO FILTERS (`filters`). The crown carries atr_filter=0.7 and vpace_filter=0.7
   and has never been asked whether those numbers are right — they came along with the
   config that won. This matters today: the vol-regime filter stood the paper leg down
   for ten straight sessions from 2026-08-13 (recent-5 daily range ~275 vs a 60-session
   median ~448, and 0.7 x 448 = 314 was never cleared), so the owner is looking at a
   silent strategy and reasonably asking whether the threshold is doing work or just
   sitting out good days. The grid measures both knobs together, including OFF.

B. THE ENTRY WINDOW (`window`, needs ORB_4_1.py). The crown scans every bar from the end
   of the opening range to the close, so a 15:30 breakout is taken on the same terms as
   a 10:05 one. Two new knobs ask whether that is wise: entry_from_bar (ignore early
   breaks) and entry_to_bar (stop taking NEW breaks late in the day; an open trade is
   still managed normally). A bar index inside a session is the clock, so this is a
   schedule and cannot look ahead.

C. THE GEOMETRY NEIGHBOURHOOD (`geom`). or_bars / breakout_buf / stop_frac / target_R
   one step either side of the crown — a plateau read, not a search. If the crown sits
   on a spike rather than a ridge, that is worth knowing even though nothing here would
   be adopted on it.

PRE-REGISTERED GATE — written here BEFORE any of this was run, unchanged from rounds 3
and 4 so the bar cannot drift to fit a result. A cell is adopt-worthy only if it beats
run #234 on all three robustness legs at once:
    rolling-12-month win rate >= 72.7%
    worst rolling-12-month    >= -$22,050
    sliced lockbox net        >= $88,943
Anything clearing all three goes to a PINNED Auto-Validate and is judged there by the
walk-forward, exactly as #273 and #271 were in round 4. Nothing is adopted from this
file's numbers alone.

    python tools/orb_hunt5.py filters
    python tools/orb_hunt5.py window
    python tools/orb_hunt5.py geom
"""
import os
import sys
import itertools

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, score, IS_END, LB_END              # noqa: E402
from tools.orb_hunt3 import INCUMBENT, robustness                     # noqa: E402

GATE = dict(win_pct=72.7, worst=-22050.0, lb_net=88943.0)
COST, MULT = 0.533, 20.0

# The crown's own numbers on this window, for the header line every sweep prints.
BASE_NET, BASE_LB, BASE_DD = 389874.0, 88943.0, 29142.0

# masters live in the primary checkout; a worktree has none of its own.
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

_BARS = None


def bars():
    """Load the pinned NQ 5-minute RTH master once and reuse it — every sweep in this
    file measures the SAME tape, which is what makes the rows comparable."""
    global _BARS
    if _BARS is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        _BARS = dict(
            open=df["open"].values.astype(float), high=df["high"].values.astype(float),
            low=df["low"].values.astype(float), close=df["close"].values.astype(float),
            volume=df["volume"].values.astype(float),
            day_id=pd.factorize(df["_dt"].dt.date)[0],
            index=pd.DatetimeIndex(df["_dt"]))
    return _BARS


def run(params, strategy="ORB_3_6.py"):
    """One config on the pinned master -> IS / LB / FULL + rolling-12 robustness.
    Window pinned to LB_END so every row covers the identical span (the HARD RULE)."""
    b = bars()
    mod = strat(strategy)
    r = mod.run_backtest(b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
                         day_id=b["day_id"], return_trades=True, **params)
    tr = (r or {}).get("trades") or []
    if not tr:
        return None
    idx = b["index"]
    tz = idx.tz
    ie = pd.Timestamp(IS_END).tz_localize(tz) if tz is not None else pd.Timestamp(IS_END)
    le = pd.Timestamp(LB_END).tz_localize(tz) if tz is not None else pd.Timestamp(LB_END)
    keep = [t for t in tr if idx[t[0]] <= le]
    if not keep:
        return None
    raw = [t[2] for t in keep]
    dts = [idx[t[0]] for t in keep]
    pnl = [(x - COST) * MULT for x in raw]
    f = score(raw, mult=MULT, cost=COST)
    return dict(full=f,
                is_net=sum(p for d, p in zip(dts, pnl) if d <= ie),
                lb_net=sum(p for d, p in zip(dts, pnl) if d > ie),
                rob=robustness([d.tz_localize(None) for d in dts], pnl),
                n=len(keep))


def passes(m):
    """The pre-registered gate, all three legs at once."""
    if not m:
        return False
    return (m["rob"]["win_pct"] >= GATE["win_pct"]
            and m["rob"]["worst"] >= GATE["worst"]
            and m["lb_net"] >= GATE["lb_net"])


def header(title):
    print("=" * 108)
    print(title)
    print("  gate: roll12 win >= %.1f%%  AND  worst roll12 >= $%s  AND  lockbox >= $%s"
          % (GATE["win_pct"], f"{GATE['worst']:,.0f}", f"{GATE['lb_net']:,.0f}"))
    print("  crown #234 reference: net $%s | LB $%s | DD $%s"
          % (f"{BASE_NET:,.0f}", f"{BASE_LB:,.0f}", f"{BASE_DD:,.0f}"))
    print("=" * 108)
    print("%-34s %10s %10s %10s %8s %7s %6s %9s %5s"
          % ("config", "NET $", "IS $", "LB $", "DD $", "PF", "trd", "worst12", "win%"))
    print("-" * 108)


def line(label, m, flag=""):
    if not m:
        print("%-34s %10s" % (label[:34], "no trades"))
        return
    f = m["full"]
    print("%-34s %10s %10s %10s %8s %7.3f %6d %9s %5.1f %s"
          % (label[:34], f"{f['net']:,.0f}", f"{m['is_net']:,.0f}", f"{m['lb_net']:,.0f}",
             f"{abs(f['dd']):,.0f}", f["pf"], m["n"],
             f"{m['rob']['worst']:,.0f}", m["rob"]["win_pct"], flag))


def sweep(cells, strategy="ORB_3_6.py"):
    """cells: [(label, param-overrides)]. Runs each, prints a row, returns the winners."""
    hits = []
    for label, over in cells:
        p = dict(INCUMBENT, **over)
        try:
            m = run(p, strategy=strategy)
        except Exception as e:                       # a bad cell must not kill the sweep
            print("%-34s ERROR %s: %s" % (label[:34], type(e).__name__, e))
            continue
        ok = passes(m)
        line(label, m, "  <== CLEARS GATE" if ok else "")
        if ok:
            hits.append((label, dict(over), m))
    print("-" * 108)
    print("cells: %d | cleared the gate: %d" % (len(cells), len(hits)))
    for label, over, m in hits:
        print("   %s  ->  %s" % (label, over))
    return hits


# ── A. the two filters ───────────────────────────────────────────────────────────
def sweep_filters():
    header("A. THE TWO FILTERS - is 0.7 / 0.7 the right pair, or just the one that came along?")
    atrs = [0.0, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.00]
    vps = [0.0, 0.50, 0.60, 0.70, 0.80, 0.90]

    print("\n-- one knob at a time (the other held at the crown's value) --")
    cells = [("atr %.2f (vpace 0.70)" % a, dict(atr_filter=a)) for a in atrs]
    cells += [("vpace %.2f (atr 0.70)" % v, dict(vpace_filter=v)) for v in vps]
    hits = sweep(cells)

    print("\n-- the full grid --")
    grid = [("atr %.2f x vpace %.2f" % (a, v), dict(atr_filter=a, vpace_filter=v))
            for a, v in itertools.product(atrs, vps)]
    hits += sweep(grid)
    return hits


# ── B. the entry window ──────────────────────────────────────────────────────────
def sweep_window():
    header("B. THE ENTRY WINDOW - does it matter WHEN in the session the break happens?")
    # 5-minute bars, RTH: bar 0 opens 09:30, so bar k opens 09:30 + 5k minutes.
    def clock(k):
        mins = 9 * 60 + 30 + 5 * k
        return "%02d:%02d" % (mins // 60, mins % 60)

    print("\n-- stop taking NEW breakouts from bar N (open trades still managed) --")
    tos = [12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72]
    cells = [("no new entry from %s (bar %d)" % (clock(k), k), dict(entry_to_bar=k)) for k in tos]
    hits = sweep(cells, strategy="ORB_4_1.py")

    print("\n-- ignore breakouts before bar N --")
    froms = [3, 4, 5, 6, 8, 10, 12, 18, 24]
    cells = [("no entry before %s (bar %d)" % (clock(k), k), dict(entry_from_bar=k)) for k in froms]
    hits += sweep(cells, strategy="ORB_4_1.py")

    print("\n-- both ends together (the best few of each, crossed) --")
    both = [("%s..%s" % (clock(a), clock(b)), dict(entry_from_bar=a, entry_to_bar=b))
            for a, b in itertools.product([3, 4, 6, 8], [36, 48, 54, 60, 66])]
    hits += sweep(both, strategy="ORB_4_1.py")
    return hits


# ── C. the geometry neighbourhood ────────────────────────────────────────────────
def sweep_geom():
    header("C. GEOMETRY NEIGHBOURHOOD - is the crown on a ridge or a spike?")
    cells = []
    cells += [("or_bars %d" % k, dict(or_bars=k)) for k in [1, 2, 3, 4, 5, 6]]
    cells += [("breakout_buf %.2f" % v, dict(breakout_buf=v))
              for v in [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]]
    cells += [("stop_frac %.2f" % v, dict(stop_frac=v))
              for v in [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]]
    cells += [("target_R %.1f" % v, dict(target_R=v))
              for v in [3.0, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 0.0]]
    cells += [("be_after_R %.2f" % v, dict(be_after_R=v))
              for v in [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]]
    return sweep(cells)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "filters"
    fn = {"filters": sweep_filters, "window": sweep_window, "geom": sweep_geom}.get(what)
    if fn is None:
        sys.exit("usage: orb_hunt5.py [filters|window|geom]")
    hits = fn()
    print()
    print("=" * 108)
    print("ROUND 5 / %s: %d cell(s) cleared the pre-registered gate." % (what.upper(), len(hits)))
    if hits:
        print("Next step for each is a PINNED Auto-Validate - the walk-forward is the judge,")
        print("not these numbers. Nothing here is adopted on this file's output alone.")
    print("=" * 108)
