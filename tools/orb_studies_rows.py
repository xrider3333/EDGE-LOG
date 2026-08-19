"""
Generate the STUDIES-board rows for the ORB research that was measured LOCALLY and never
persisted as an Auto-Validate run.

Read STUDIES_BOARD.md first. This script only produces the `rows:[...]` JS for two new
studies; a human pastes them into RESEARCH_STUDIES in index.html.

Every figure here is recomputed from the master on the SAME window as run #230
(2010-06-07 .. 2026-08-13), so the DATA WINDOW column can state it honestly instead of
showing a dash. Nothing is copied from chat.

    python tools/orb_studies_rows.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from tools.orb_hunt import run, score, C221, IS_END, LB_END, COST_PTS, MULT

INCUMBENT = dict(C221, be_after_R=1.0, partial_exit_R=0.0, trail_bars=0)
WIN = "{from:'2010-06-07',to:'2026-08-13'}"


def stats(strategy, params):
    _, tr, b = run(strategy, params, None, LB_END)
    if not tr:
        return None
    idx = b["index"]
    ie = pd.Timestamp(IS_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(IS_END)
    raw = [t[2] for t in tr]
    is_raw = [t[2] for t in tr if idx[t[0]] <= ie]
    lb_raw = [t[2] for t in tr if idx[t[0]] > ie]
    f = score(raw)
    return dict(is_=score(is_raw)["net"], lb=score(lb_raw)["net"],
                tot=f["net"], dd=f["dd"], pf=f["pf"], trd=f["n"])


def blend(pa, pb):
    """50/50 per-session book of two exit plans on identical entries."""
    _, ta, b = run("ORB_3_6.py", pa, None, LB_END)
    _, tb, _ = run("ORB_3_6.py", pb, None, LB_END)
    idx = b["index"]
    ie = pd.Timestamp(IS_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(IS_END)
    da = {idx[t[0]].date(): t[2] for t in ta}
    db = {idx[t[0]].date(): t[2] for t in tb}
    days = sorted(set(da) | set(db))
    mixed = [(d, 0.5 * da.get(d, 0.0) + 0.5 * db.get(d, 0.0)) for d in days]
    # a blended session still pays cost on both legs -> average of two round turns = one
    raw = [p for d, p in mixed]
    f = score(raw)
    ied = ie.date()
    return dict(is_=score([p for d, p in mixed if d <= ied])["net"],
                lb=score([p for d, p in mixed if d > ied])["net"],
                tot=f["net"], dd=f["dd"], pf=f["pf"], trd=f["n"])


B3 = dict(INCUMBENT, target_R=0.0, trail_bars=3)
B5 = dict(INCUMBENT, target_R=0.0, trail_bars=5)

# ── the two studies. (n, name, what, tone, read, strategy, params) ────────────────
ENTRY = [
 (100, "OR 1 Bar", "Opening range from the first 5-minute bar instead of two.", "fail",
  "Halves the money", "ORB_3_6.py", dict(INCUMBENT, or_bars=1)),
 (101, "OR 3 Bars", "Opening range from the first fifteen minutes.", "fail",
  "Best in-sample, loses the lockbox", "ORB_3_6.py", dict(INCUMBENT, or_bars=3)),
 (102, "OR 4 Bars", "Opening range from the first twenty minutes.", "fail",
  "Worst drawdown of the scan", "ORB_3_6.py", dict(INCUMBENT, or_bars=4)),
 (103, "OR 6 Bars", "Opening range from the first half hour.", "fail",
  "Nearly all the edge gone", "ORB_3_6.py", dict(INCUMBENT, or_bars=6)),
 (104, "Both Directions", "Trade either side of the range instead of the opening candle direction.", "fail",
  "Loses money in the lockbox", "ORB_3_6.py", dict(INCUMBENT, trade_mode="Both")),
 (105, "Long Only", "Only take upside breakouts.", "fail",
  "Half the edge, more drawdown", "ORB_3_6.py", dict(INCUMBENT, trade_mode="Long Only")),
 (106, "Short Only", "Only take downside breakouts.", "fail",
  "Half the edge, more drawdown", "ORB_3_6.py", dict(INCUMBENT, trade_mode="Short Only")),
 (107, "No Buffer", "Trigger the moment price touches the range edge.", "fail",
  "Drawdown nearly doubles", "ORB_3_6.py", dict(INCUMBENT, breakout_buf=0.0)),
 (108, "Buffer 0.40", "Require price to clear the edge by 40 percent of the range.", "frag",
  "Lowest drawdown, less money", "ORB_3_6.py", dict(INCUMBENT, breakout_buf=0.40)),
 (109, "Volume Gate Off", "Remove the pre-entry volume-pace requirement.", "frag",
  "More money, much more drawdown", "ORB_3_6.py", dict(INCUMBENT, vpace_filter=0.0)),
 (110, "Volume Gate 1.1", "Only trade sessions running well above normal volume.", "fail",
  "Too strict, halves the money", "ORB_3_6.py", dict(INCUMBENT, vpace_filter=1.1)),
 (111, "Regime Filter Off", "Remove the quiet-market skip.", "frag",
  "More money, more drawdown", "ORB_3_6.py", dict(INCUMBENT, atr_filter=0.0)),
 (112, "Regime Filter 0.5", "Skip only the very quietest stretches.", "frag",
  "Most money of the whole scan", "ORB_3_6.py", dict(INCUMBENT, atr_filter=0.5)),
 (113, "Stop 1.5", "Stop at 1.5 times the range width.", "frag",
  "Tighter stop, less money", "ORB_3_6.py", dict(INCUMBENT, stop_frac=1.5)),
 (114, "Stop 2.5", "Stop at 2.5 times the range width.", "frag",
  "More money, more drawdown", "ORB_3_6.py", dict(INCUMBENT, stop_frac=2.5)),
 (115, "Grid Survivor", "Regime filter off, buffer 0.30, stop 2.50 - the survivor never validated.",
  "frag", "Cleared the gate, never run", "ORB_3_6.py",
  dict(INCUMBENT, atr_filter=0.0, breakout_buf=0.30, stop_frac=2.50)),
]

KILLED = [
 (116, "Prior-Day Gate", "Only fill beyond the previous day high or low.", "fail",
  "Loses a third of the money", "ORB_4_0.py", dict(INCUMBENT, pdr_gate=1)),
 (117, "Prior-Day Gate Loose", "Fill anywhere except inside the previous day range.", "fail",
  "Worse again on drawdown", "ORB_4_0.py", dict(INCUMBENT, pdr_gate=2)),
 (118, "Re-entry Once", "Allow one more entry after a breakeven scratch.", "fail",
  "More trades, worse result", "ORB_3_7.py", dict(INCUMBENT, reenter_scratch=1)),
 (119, "Re-entry Twice", "Allow two more entries after a breakeven scratch.", "fail",
  "Same failure, more of it", "ORB_3_7.py", dict(INCUMBENT, reenter_scratch=2)),
 (120, "Cutoff 15:00", "Refuse new entries after 3pm.", "fail",
  "No gain over trading all day", "ORB_3_6.py", None),
 (121, "Cutoff 13:00", "Refuse new entries after 1pm.", "fail",
  "Costs money, adds drawdown", "ORB_3_6.py", None),
 (122, "Cutoff 11:00", "Morning entries only.", "fail",
  "Cuts a fifth of the money", "ORB_3_6.py", None),
 (123, "Trail From Entry 3", "Replace the target with a 3-bar trailing stop.", "fail",
  "The trail is dead weight", "ORB_3_6.py", B3),
 (124, "Trail From Entry 5", "Replace the target with a 5-bar trailing stop.", "fail",
  "Earns a fraction of riding", "ORB_3_6.py", B5),
 (125, "Two-Lot Ride+Trail3", "Two contracts: one rides to target, one trails 3 bars.", "fail",
  "Blends ruled out by owner", None, None),
 (126, "Two-Lot Ride+Trail5", "Two contracts: one rides to target, one trails 5 bars.", "fail",
  "Blends ruled out by owner", None, None),
 (127, "Fade OR1", "Trade the failed breakout in reverse, 5-minute range.", "fail",
  "Loses money in both windows", "ORB_FADE_1_0.py",
  dict(or_bars=1, trade_mode="Both", vol_gate=0.0, stop_pad=0.15, target_R=0.0)),
 (128, "Fade OR2", "Trade the failed breakout in reverse, 10-minute range.", "fail",
  "Loses money in both windows", "ORB_FADE_1_0.py",
  dict(or_bars=2, trade_mode="Both", vol_gate=0.0, stop_pad=0.15, target_R=0.0)),
]

CUTOFF_MIN = {120: 15 * 60, 121: 13 * 60, 122: 11 * 60}


def cutoff_stats(limit):
    _, tr, b = run("ORB_3_6.py", INCUMBENT, None, LB_END)
    idx = b["index"]
    ie = pd.Timestamp(IS_END).tz_localize(idx.tz) if idx.tz is not None else pd.Timestamp(IS_END)
    keep = [t for t in tr if (idx[t[0]].hour * 60 + idx[t[0]].minute) < limit]
    f = score([t[2] for t in keep])
    return dict(is_=score([t[2] for t in keep if idx[t[0]] <= ie])["net"],
                lb=score([t[2] for t in keep if idx[t[0]] > ie])["net"],
                tot=f["net"], dd=f["dd"], pf=f["pf"], trd=f["n"])


def js(n, name, what, tone, read, s):
    return ("  {n:%d,name:'%s',what:'%s',tone:'%s',read:'%s',win:%s,"
            "is:%d,lb:%d,tot:%d,dd:%d,pf:%.2f,trd:%d}," % (
                n, name, what.replace("'", "\\'"), tone, read, WIN,
                round(s["is_"]), round(s["lb"]), round(s["tot"]), round(s["dd"]),
                s["pf"], s["trd"]))


if __name__ == "__main__":
    print("// ---- STUDY A rows (entry re-opened) ----")
    for n, name, what, tone, read, strat, p in ENTRY:
        print(js(n, name, what, tone, read, stats(strat, p)))
    print()
    print("// ---- STUDY B rows (tested and killed) ----")
    for n, name, what, tone, read, strat, p in KILLED:
        if n in CUTOFF_MIN:
            s = cutoff_stats(CUTOFF_MIN[n])
        elif n == 125:
            s = blend(INCUMBENT, B3)
        elif n == 126:
            s = blend(INCUMBENT, B5)
        else:
            s = stats(strat, p)
        print(js(n, name, what, tone, read, s))
    print()
    print("// row 129 (ATR-floor stop) carries no figures on purpose - it was killed by a")
    print("// diagnostic before any config existed. Add it by hand with a `why` for each dash.")
