"""
ORB HUNT — one consolidated results table for EVERY config run in the 2026-08-17 hunt.

Owner asked for IS / LB / FULL net + drawdown on all of it, top config pinned first.
WF exists ONLY for configs that went through the validate pipeline (runs 230/233/234);
every other row says so rather than inventing a number.

Speed note: IS is an exact PREFIX of FULL (same data, same warm-up), so IS is sliced
out of the FULL run instead of re-backtesting. LB needs its own run because the
engine's lockbox re-warms at the boundary (this is what makes our LB match the
pipeline's lockbox to the dollar). 2 backtests per config, not 3.

    python tools/orb_hunt_table.py            # full table
    python tools/orb_hunt_table.py --check    # prove IS-prefix == IS-separate
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from tools.orb_hunt import (C221, IS_END, LB_END, run, score, bars, MULT, COST_PTS)

A_RIDE = dict(C221, be_after_R=1.0, partial_exit_R=0.0, trail_bars=0)   # = C2 / run 234
C1     = dict(C221, be_after_R=1.0)                                     # = run 233

_cache = {}


def _full_and_lb(strategy, params):
    key = (strategy, tuple(sorted(params.items())))
    if key in _cache:
        return _cache[key]
    _, tr_f, b_f = run(strategy, params, None, LB_END)
    _, tr_l, b_l = run(strategy, params, IS_END, LB_END)
    idx_f = b_f["index"]
    is_end = pd.Timestamp(IS_END).date()
    full = [(idx_f[t[0]].date(), t[2], t[3], idx_f[t[0]]) for t in tr_f]
    lb = [(b_l["index"][t[0]].date(), t[2], t[3], b_l["index"][t[0]]) for t in tr_l]
    out = (full, lb)
    _cache[key] = out
    return out


def stats(strategy, params, tfilter=None):
    """-> dict of IS/LB/FULL score dicts. tfilter(entry_ts, side) -> keep?"""
    full, lb = _full_and_lb(strategy, params)
    is_end = pd.Timestamp(IS_END).date()
    if tfilter:
        full = [r for r in full if tfilter(r[3], r[2])]
        lb = [r for r in lb if tfilter(r[3], r[2])]
    return dict(IS=score([p for d, p, s, t in full if d <= is_end]),
                LB=score([p for d, p, s, t in lb]),
                FULL=score([p for d, p, s, t in full]))


def blend(strategy, pa, pb):
    """50/50 per-session blend of two exit plans on identical entries = the 2-lot book."""
    fa, la = _full_and_lb(strategy, pa)
    fb, lb_ = _full_and_lb(strategy, pb)
    is_end = pd.Timestamp(IS_END).date()

    def mix(x, y):
        dx = {d: p for d, p, s, t in x}
        dy = {d: p for d, p, s, t in y}
        return [(d, 0.5 * dx.get(d, 0.0) + 0.5 * dy.get(d, 0.0)) for d in sorted(set(dx) | set(dy))]
    f = mix(fa, fb); l = mix(la, lb_)
    return dict(IS=score([p for d, p in f if d <= is_end]),
                LB=score([p for d, p in l]),
                FULL=score([p for d, p in f]))


# ── the full run list ────────────────────────────────────────────────────────────
ROWS = []


def add(group, label, strategy, params, wf="not run", tfilter=None, blend_with=None):
    ROWS.append(dict(group=group, label=label, strategy=strategy, params=params,
                     wf=wf, tfilter=tfilter, blend_with=blend_with))


# certified
add("CERTIFIED", "#234 C2 ride+BE  (be 1.0, no partial, no trail)", "ORB_3_6.py", A_RIDE,
    wf="4.649 | 7/8 | OOS 15,534 pts")
add("CERTIFIED", "#233 C1 champion + be 1.0", "ORB_3_6.py", C1,
    wf="4.530 | 7/8 | OOS 15,023 pts")
add("CERTIFIED", "#230 C221 champion (prior crown)", "ORB_3_4.py", C221,
    wf="4.635 | 7/8 | OOS 14,792 pts")

# BE scan on the champion base
for be in (0.5, 0.8, 1.2, 1.5, 2.0, 2.5, 3.0):
    add("BE SCAN (on #230 base)", "champion + be %.1f" % be, "ORB_3_6.py", dict(C221, be_after_R=be))

# ride+BE characterization
for be in (0.8, 1.2, 1.5):
    add("RIDE+BE VARIANTS", "ride+BE  be %.1f" % be, "ORB_3_6.py", dict(A_RIDE, be_after_R=be))
for tR in (0.0, 4.5, 5.0, 6.0):
    add("RIDE+BE VARIANTS", "ride+BE  target %.1fR" % tR, "ORB_3_6.py", dict(A_RIDE, target_R=tR))
for sf in (1.75, 2.25):
    add("RIDE+BE VARIANTS", "ride+BE  stop %.2f" % sf, "ORB_3_6.py", dict(A_RIDE, stop_frac=sf))

# neighbors, be off vs on
for name, delta in (("stop 1.75", dict(stop_frac=1.75)), ("stop 1.50", dict(stop_frac=1.5)),
                    ("trail 5", dict(trail_bars=5)), ("partial 2.5", dict(partial_exit_R=2.5)),
                    ("target 5.0", dict(target_R=5.0)), ("or_bars 3", dict(or_bars=3)),
                    ("buf 0.20", dict(breakout_buf=0.20))):
    add("NEIGHBORS be OFF", "%s (be 0)" % name, "ORB_3_6.py", dict(C221, **delta))
    add("NEIGHBORS be ON", "%s (be 1.0)" % name, "ORB_3_6.py", dict(C221, be_after_R=1.0, **delta))

# ensemble legs + blends
B3 = dict(A_RIDE, target_R=0.0, trail_bars=3)
B5 = dict(A_RIDE, target_R=0.0, trail_bars=5)
add("ENSEMBLE LEGS", "leg B  trail-from-entry 3", "ORB_3_6.py", B3)
add("ENSEMBLE LEGS", "leg B5 trail-from-entry 5", "ORB_3_6.py", B5)
add("ENSEMBLE BLENDS", "BLEND ride+BE + trail3", "ORB_3_6.py", A_RIDE, blend_with=B3)
add("ENSEMBLE BLENDS", "BLEND ride+BE + trail5", "ORB_3_6.py", A_RIDE, blend_with=B5)
add("ENSEMBLE BLENDS", "BLEND C1 + trail3", "ORB_3_6.py", C1, blend_with=B3)

# re-entry after BE scratch
for re_ in (0, 1, 2):
    add("RE-ENTRY (3.7)", "reenter after scratch = %d" % re_, "ORB_3_7.py",
        dict(A_RIDE, reenter_scratch=re_))

# entry-time cutoff (exact emulation: one trade/session, drop late entries)
def _cut(lim):
    return lambda ts, side: (ts.hour * 60 + ts.minute) < lim
for cut in ("15:00", "14:00", "13:00", "12:00", "11:30", "11:00", "10:30"):
    hh, mm = map(int, cut.split(":"))
    add("ENTRY CUTOFF (on ride+BE)", "entries before %s ET" % cut, "ORB_3_6.py", A_RIDE,
        tfilter=_cut(hh * 60 + mm))

# side split
add("SIDE SPLIT (ride+BE)", "LONG only", "ORB_3_6.py", A_RIDE, tfilter=lambda ts, s: s == 1)
add("SIDE SPLIT (ride+BE)", "SHORT only", "ORB_3_6.py", A_RIDE, tfilter=lambda ts, s: s == -1)

# failed-break fade
for ob in (1, 2):
    for tR in (0.0, 1.0, 1.5, 2.0):
        add("FADE (ORB_FADE_1_0)", "fade OR%d target %.1fR" % (ob, tR), "ORB_FADE_1_0.py",
            dict(or_bars=ob, trade_mode="Both", vol_gate=0.0, stop_pad=0.15, target_R=tR))


def money(x):
    return ("-$" if x < 0 else "$") + format(int(round(abs(x))), ",")


def main():
    print("%-44s | %11s %10s | %10s %9s | %11s %10s %6s %7s | %s" % (
        "config", "IS net", "IS DD", "LB net", "LB DD", "TOTAL net", "TOTAL DD", "PF", "net/DD", "WF (wfe|folds|OOS)"))
    print("-" * 175)
    last = None
    for r in ROWS:
        if r["group"] != last:
            print("--- %s ---" % r["group"])
            last = r["group"]
        if r["blend_with"] is not None:
            s = blend(r["strategy"], r["params"], r["blend_with"])
        else:
            s = stats(r["strategy"], r["params"], r["tfilter"])
        i, l, f = s["IS"], s["LB"], s["FULL"]
        print("%-44s | %11s %10s | %10s %9s | %11s %10s %6.3f %7.2f | %s" % (
            r["label"][:44], money(i["net"]), money(i["dd"]), money(l["net"]), money(l["dd"]),
            money(f["net"]), money(f["dd"]), min(f["pf"], 9.999),
            min(f["mar"], 99.99) if f["dd"] else 0, r["wf"]))
        sys.stdout.flush()


if __name__ == "__main__":
    if "--check" in sys.argv:
        s = stats("ORB_3_4.py", C221)
        print("IS-prefix net =", money(s["IS"]["net"]), "(separate-run value was $283,554)")
        print("LB net        =", money(s["LB"]["net"]), "(engine lockbox $64,575)")
        print("FULL net      =", money(s["FULL"]["net"]), "(run #230 $348,129)")
    else:
        main()
