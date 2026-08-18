"""
ORB HUNT ROUND 3 — new directions, not more knobs around run #234.

Owner 2026-08-18: "try new things".

Rounds 1-2 changed ONLY the exit. Every one of the 65+ configs tested so far carried
run #230's entry verbatim (OR 2 / first-candle dir / close-confirm / buf 0.25 / v-pace
0.7 / ATR 0.7). But that entry was chosen when the exit was partial-3R + trail-3. The
exit has since changed completely (ride to 5.5R with breakeven at 1.0R), so the entry
that was optimal under the old exit need not be optimal under the new one. That whole
surface is unexamined. This module opens it.

THE SCREEN IS ROBUSTNESS, NOT TOTAL DOLLARS.
  Owner 2026-08-17: "WF is our judge". A fixed config cannot have a walk-forward in the
  selection sense (nothing is being re-fit), but it can be asked the question WF is
  really asking: does this hold up across TIME, or does it live in a few good stretches?
  So every config here is scored on rolling 12-month windows stepped monthly:
      win_pct  - share of rolling years that are profitable
      worst    - the worst rolling year (the number that actually hurts)
      median   - the typical rolling year
  Ranking on total net is what crowned the kitchen-sink config and or_bars 3, both of
  which had the best in-sample net in their sweep and a negative lockbox. Not again.

SCREEN FAST, VERIFY PROPERLY.
  For speed the screen slices IS/LB out of ONE full-history run. That is exact for IS
  (a prefix shares the warm-up) but NOT identical to the engine's lockbox, which re-warms
  its filters at the boundary. So finalists are re-measured with real windowed runs via
  tools/orb_hunt.py before anything is proposed for validation.
"""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from tools.orb_hunt import run, score, C221, IS_END, LB_END, MULT, COST_PTS

# the incumbent exit — run #234. Entry knobs are what we vary.
EXIT = dict(be_after_R=1.0, partial_exit_R=0.0, trail_bars=0, target_R=5.5,
            close_confirm=True, flat_eod=True, skip_holidays=True)
INCUMBENT = dict(C221, **EXIT)


def robustness(dates, pnls, window_months=12, step_months=1):
    """Rolling-window robustness of a fixed config. Returns win_pct / worst / median
    over every `window_months` window stepped monthly across the whole history."""
    if not len(dates):
        return dict(win_pct=0.0, worst=0.0, median=0.0, n_win=0)
    s = pd.Series(pnls, index=pd.DatetimeIndex(dates).tz_localize(None)).sort_index()
    first, last = s.index[0], s.index[-1]
    outs = []
    t = pd.Timestamp(first).normalize().replace(day=1)
    while t + pd.DateOffset(months=window_months) <= last + pd.DateOffset(days=1):
        w = s[(s.index >= t) & (s.index < t + pd.DateOffset(months=window_months))]
        if len(w):
            outs.append(float(w.sum()))
        t = t + pd.DateOffset(months=step_months)
    if not outs:
        return dict(win_pct=0.0, worst=0.0, median=0.0, n_win=0)
    a = np.array(outs)
    return dict(win_pct=100.0 * float((a > 0).mean()), worst=float(a.min()),
                median=float(np.median(a)), n_win=len(a))


def measure(strategy, params):
    """One full-history run -> IS / LB / FULL / robustness. LB here is SLICED (screen
    only); finalists get a real windowed LB run before anything is claimed."""
    _, tr, b = run(strategy, params, None, LB_END)
    if not tr:
        return None
    idx = b["index"]
    d = [idx[t[0]] for t in tr]
    pnl = [(t[2] - COST_PTS) * MULT for t in tr]
    ie = pd.Timestamp(IS_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(IS_END)
    is_p = [p for dd, p in zip(d, pnl) if dd <= ie]
    lb_p = [p for dd, p in zip(d, pnl) if dd > ie]
    raw = [t[2] for t in tr]
    return dict(n=len(tr), full=score(raw),
                is_net=sum(is_p), lb_net=sum(lb_p),
                rob=robustness(d, pnl))


def line(label, m):
    f, r = m["full"], m["rob"]
    return ("%-42s n=%-5d IS $%9s  LB $%8s | TOT $%9s DD $%8s MAR %5.2f | "
            "roll12 win %5.1f%%  worst $%9s  med $%8s" % (
                label[:42], m["n"], format(int(m["is_net"]), ","), format(int(m["lb_net"]), ","),
                format(int(f["net"]), ","), format(int(f["dd"]), ","), min(f["mar"], 99.99),
                r["win_pct"], format(int(r["worst"]), ","), format(int(r["median"]), ",")))


# ── stage 1: one-at-a-time — which entry knobs even move under the new exit? ──────
OAT = {
    "or_bars":      [1, 2, 3, 4, 6],
    "trade_mode":   ["Both", "First-candle dir", "Long Only", "Short Only"],
    "breakout_buf": [0.0, 0.1, 0.25, 0.4],
    "vpace_filter": [0.0, 0.5, 0.7, 0.9, 1.1],
    "atr_filter":   [0.0, 0.5, 0.7, 0.9, 1.1],
    "stop_frac":    [1.5, 1.75, 2.0, 2.25, 2.5],
}


def sweep_oat():
    base = measure("ORB_3_6.py", INCUMBENT)
    print("INCUMBENT (run #234) — the bar every row has to clear")
    print("  " + line("run #234 ride+BE", base))
    print()
    for knob, vals in OAT.items():
        print("--- %s ---" % knob)
        for v in vals:
            p = dict(INCUMBENT); p[knob] = v
            m = measure("ORB_3_6.py", p)
            if m is None:
                print("  %-40s NO TRADES" % ("%s=%s" % (knob, v))); continue
            star = " <= incumbent" if v == INCUMBENT[knob] else ""
            print("  " + line("%s = %s%s" % (knob, v, star), m))
            sys.stdout.flush()
        print()


SWEEPS = {"oat": sweep_oat}



# ── stage 2: focused grid on the knobs that MOVED in the OAT sweep ────────────────
#
# OAT verdict (2026-08-18): or_bars=2 and trade_mode="First-candle dir" are confirmed
# dominant and are held FIXED (or_bars 3 posts the best IS in its column and a NEGATIVE
# lockbox for the third time; "Both" posts a negative lockbox too). The four knobs that
# genuinely moved are atr_filter, breakout_buf, stop_frac, vpace_filter.
#
# PRE-REGISTERED SELECTION RULE — written before the grid was run, so the bar cannot be
# moved to fit whatever comes out. To be proposed for validation a config must clear the
# incumbent on ALL THREE robustness/holdout legs:
#     (1) rolling-12mo win rate  >= 72.7%      (incumbent's)
#     (2) worst rolling 12mo     >= -$22,050   (incumbent's — i.e. strictly less bad)
#     (3) sliced-LB net          >= $88,942    (incumbent's)
# Survivors are then ranked by MAR (net / max drawdown). Total net is NOT a criterion —
# ranking on it is what produced the kitchen-sink config and or_bars 3.
GATE = dict(win_pct=72.7, worst=-22050.0, lb_net=88942.0)


def sweep_grid():
    grid = dict(atr_filter=[0.0, 0.3, 0.5, 0.7],
                breakout_buf=[0.25, 0.3, 0.4, 0.5],
                stop_frac=[1.75, 2.0, 2.25, 2.5],
                vpace_filter=[0.5, 0.7, 0.9])
    keys = list(grid)
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print("focused grid: %d configs (or_bars=2, first-candle dir, ride+BE exit held)" % len(combos))
    print("PRE-REGISTERED GATE: roll12 win >= %.1f%%  AND  worst >= $%s  AND  LB >= $%s"
          % (GATE["win_pct"], format(int(GATE["worst"]), ","), format(int(GATE["lb_net"]), ",")))
    print()
    rows = []
    for i, c in enumerate(combos):
        p = dict(INCUMBENT); p.update(dict(zip(keys, c)))
        m = measure("ORB_3_6.py", p)
        if m is None:
            continue
        m["cfg"] = dict(zip(keys, c))
        rows.append(m)
        if (i + 1) % 24 == 0:
            print("  ...%d/%d" % (i + 1, len(combos))); sys.stdout.flush()
    print()
    surv = [m for m in rows
            if m["rob"]["win_pct"] >= GATE["win_pct"]
            and m["rob"]["worst"] >= GATE["worst"]
            and m["lb_net"] >= GATE["lb_net"]]
    surv.sort(key=lambda m: -m["full"]["mar"])
    print("=== SURVIVORS OF THE PRE-REGISTERED GATE: %d of %d ===" % (len(surv), len(rows)))
    for m in surv[:15]:
        lab = "atr%.1f buf%.2f stop%.2f vp%.1f" % (
            m["cfg"]["atr_filter"], m["cfg"]["breakout_buf"],
            m["cfg"]["stop_frac"], m["cfg"]["vpace_filter"])
        print("  " + line(lab, m))
    if not surv:
        print("  (none — the incumbent is not beaten on all three legs)")
    print()
    print("=== for reference: top 10 by TOTAL NET (the ranking we do NOT use) ===")
    for m in sorted(rows, key=lambda m: -m["full"]["net"])[:10]:
        lab = "atr%.1f buf%.2f stop%.2f vp%.1f" % (
            m["cfg"]["atr_filter"], m["cfg"]["breakout_buf"],
            m["cfg"]["stop_frac"], m["cfg"]["vpace_filter"])
        gate = "PASS" if m in surv else "fails gate"
        print("  %-8s %s" % (gate, line(lab, m)))


SWEEPS["grid"] = sweep_grid


if __name__ == "__main__":
    w = sys.argv[1] if len(sys.argv) > 1 else "oat"
    SWEEPS[w]()
