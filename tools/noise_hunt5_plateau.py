"""
NOISE STUDY B -- is the crowned run #243 a PLATEAU or a SPIKE?   (2026-08-27)

Self-contained driver.  Usage:
    python tools/noise_hunt5_plateau.py            full study
    python tools/noise_hunt5_plateau.py --gate     reproduction gate only

Sits on tools/noise_variant_research.py's run_variant (parity vs the real engine proven
to the cent; its rv_mode='skip_hi'/rv_pct is NOISE_1_0.py's vol_skip_pct).  Queues NO
runner job, restarts nothing, imports/registers no data master, and does NOT open the
spent lockbox.

===============================================================================
 PRE-REGISTRATION -- written in full BEFORE any cell of Study B was run
===============================================================================

PROVENANCE NOTE, stated so it cannot be mistaken for a goalpost move: the round's
master pre-registration was handed to this driver TRUNCATED -- it ended inside Study
A's cell table and Study B's own section never arrived.  Everything below was
therefore written here, before the first cell ran, following the house pattern of the
2026-08-21 NOISE pre-registration (scratchpad prereg.md) and the neighbourhood
convention already banked in augur_strategies/NOISE_1_0.py's docstring
("daytype_lo 0.15/0.25, confirm 3, lookback 36/52, band_mult_long 0.5/1.0,
band_mult_short 1.25/1.75, stop_k 1.5/2.0 ... a plateau, not a magic cell").  If the
orchestrator's Study B section differs from this, THIS document is the one that was
binding on the numbers below, and the difference must be reported as such.

-------------------------------------------------------------------------------
B1.  THE CLAIM, IN ONE SENTENCE
-------------------------------------------------------------------------------
Run #243 sits on a PLATEAU: each of its own knobs, moved one step off the crown with
every other knob pinned, leaves a configuration that is recognisably the same
strategy -- not a single lucky cell surrounded by cliffs.

-------------------------------------------------------------------------------
B2.  WHAT IS SWEPT (the exact cells; crown value in [brackets])
-------------------------------------------------------------------------------
Pinned crown = NOISE_225 core + the two causal filters:
   lookback 44 . band 0.75/1.50 . exit vwap . Both . all_day . flat_eod
   . stop bandwidth k 1.75 . daytype_mode skip_bot_short lo 0.20 . vol_skip_pct 90

ORDINAL AXES (a plateau/spike verdict is defined only for these):
  A1 lookback          28, 36, 40, [44], 48, 52, 60          immediate 40 / 48
  A2 band_mult_long    0.50, [0.75], 1.00, 1.25, 1.50        immediate 0.50 / 1.00
  A3 band_mult_short   1.00, 1.25, [1.50], 1.75, 2.00        immediate 1.25 / 1.75
  A4 stop_k            1.00, 1.25, 1.50, [1.75], 2.00, 2.25, 2.50   immediate 1.50/2.00
  A5 daytype_lo        0.10, 0.15, [0.20], 0.25, 0.30        immediate 0.15 / 0.25
  A6 vol_skip_pct      80, 85, [90], 95, 98                  immediate 85 / 95
  A7 confirm_bars      [1], 2, 3                             immediate 2 (EDGE cell)

  Grid choices are the strategy file's own step sizes (band 0.25, daytype_lo 0.05,
  confirm 1) and its own banked neighbourhood for lookback.  band_mult_long 0.25 is
  below the file's min of 0.50 and is not run.

OFF-ENDPOINTS (the knob switched off entirely; reported on its axis, NOT counted as
an immediate neighbour, because "off" is a different strategy rather than one step):
  E1 stop_mode='off'        no protective stop at all
  E2 daytype_mode='off'     = vol-skip 90 alone
  E3 vol_skip_pct off       = run #241 (SBS lo0.20)

CATEGORICAL BLOCK (reported for completeness; NO plateau/spike verdict -- these knobs
have no ordering, so "one step off" is undefined):
  C1 exit_mode   [vwap], band
  C2 side        [Both], Long Only, Short Only
  C3 window      [all_day], morning, afternoon_block

NOT MEASURABLE -- printed as a dash with a reason, never as a zero:
  exit_mode='boundary'  -- an intrabar touch-fill model that run_variant does not
                           implement; a different fill convention, not a knob step.
  stop_mode='atr'       -- not implemented in run_variant.
  stop_mode='fixed'     -- implemented, but k is 100-point units there, so k=1.75
                           means a 175-point stop; it is not one step off a
                           bandwidth stop and comparing them would be a category error.
  skip_holidays=True    -- not implemented in run_variant.

-------------------------------------------------------------------------------
B3.  THE BAR -- what PLATEAU and SPIKE mean, fixed before the numbers
-------------------------------------------------------------------------------
All on the SELECTION window only (2010-06-07 -> 2025-02-10, run #231's saved
optimize window).  Let the crown's own measured figures be net*, MAR* (= net /
|max drawdown|) and PF*.  For each ORDINAL axis, judged on its two IMMEDIATE
neighbours (the one neighbour that exists, for an edge cell, which is then flagged):

  PLATEAU  every immediate neighbour keeps  net >= 0.80 x net*
                                       AND  MAR >= 0.80 x MAR*
                                       AND  PF  >= 1.20
  SPIKE    any immediate neighbour falls to net < 0.60 x net*
                                        or  MAR < 0.60 x MAR*
                                        or  PF  < 1.20
  SLOPE    anything in between (declared NOW so the study is not forced into a
           binary it cannot honestly make after seeing the numbers)

  0.80 is the house floor already in use for gate crowning ("NET $ within 80%-of-best
  MAR"); 1.20 is NOISE's standing promotion bar, used verbatim in the 2026-08-21 and
  2026-08-22 pre-registrations.  Neither number was invented for this round.

OVERALL VERDICT ON THE CROWN
  PLATEAU  no ordinal axis is SPIKE, and at least 5 of the 7 are PLATEAU
  RIDGE    otherwise -- and the offending axes are named

ALSO REPORTED ON EVERY AXIS (not part of the verdict):
  whether the crown is the argmax of that axis on net, and on MAR.  A neighbour that
  BEATS the crown is not a plateau failure; it is a statement that the crown is not
  the local best on that axis, and it is reported as such.

NOTHING HERE IS CROWNED.  Study B is a stability read, not a search.  A cell that
beats the crown is named as a candidate for a FUTURE pre-registered head-to-head with
its own window discipline.  The lockbox (2025-02-11 -> 2026-08-12) is SPENT and is
NOT OPENED AT ALL in this study -- no cell is proposed for adoption, so there is
nothing to confirm, and reading it to break a tie would be lockbox shopping.

-------------------------------------------------------------------------------
B4.  THE "WHICH DAYS TRADE" PROBLEM -- A5 and A6, handled explicitly
-------------------------------------------------------------------------------
daytype_lo and vol_skip_pct do not perturb a trade set; they change WHICH SESSIONS
trade at all.  Their neighbours are therefore not small perturbations of the same
trades, and a naive net comparison silently mixes "better trades" with "fewer
trades".  Pre-registered decomposition, run on every cell of A5 and A6 against the
crown:

  keys are (entry bar, direction).  Because the filters gate entries and nothing
  downstream, a trade present in both runs is the IDENTICAL trade with the identical
  exit, so:
      net(cell) - net(crown)  ==  $(trades only in cell)  -  $(trades only in crown)
  exactly, and the whole difference between any two cells on these axes IS "a
  different number of trades".  What is NOT automatic, and is what gets reported, is
  whether those days deserved to be dropped:
      $/trade of the REMOVED set        (clearly negative => the filter is working)
      $/trade of the ADDED set
      drawdown change alongside the trade-count change, because trading fewer days
      lowers drawdown mechanically.

-------------------------------------------------------------------------------
B5.  CONCENTRATION RE-CHECK ON THE VOL AXIS (carried rule, applied per value)
-------------------------------------------------------------------------------
Run #243's own crowning card records the caveat that the volatility skip's gains
concentrate in its ten best avoided trades.  Rule 5 of the 2026-08-21
pre-registration is carried here VERBATIM and applied at every value of the axis, not
just at 90:

  For each vol_skip_pct value p, reference = the same config with the vol skip OFF
  (i.e. #241, SBS lo0.20 -- the in-crown reference, not the standalone one the
  2026-08-23 card used; both readings are reported).  Removed = trades in the
  reference that the value p suppresses.  top10_avoided = minus the sum of the ten
  MOST NEGATIVE removed trades.
      SURVIVES      d_net - top10_avoided > 0
      DISQUALIFIED  otherwise
  A value whose benefit survives removing its ten best avoided trades is a different
  animal from one whose does not, and the two are labelled differently.
  The same decomposition is run on the day-type axis, free, for symmetry.

-------------------------------------------------------------------------------
B6.  REPRODUCTION GATE -- nothing prints unless both pass
-------------------------------------------------------------------------------
  #231 champion core, filters off : 5,113 / $277,123.31 / DD $19,482.27
  crown #243 (SBS lo0.20 + vs90)  : 4,054 / $320,130    / DD $18,425
  (tools/noise_combo_study.py BANKED, campaign table in NOISE.md)

-------------------------------------------------------------------------------
B7.  WHAT WOULD FALSIFY THE CLAIM / WHAT IS ALREADY OFF LIMITS
-------------------------------------------------------------------------------
The claim fails the moment ONE ordinal axis is SPIKE.  That is a perfectly good
result and is reported as such -- a crown on a ridge is a real finding about the live
configuration, not a failure of the round.

CLOSED GROUND, flagged in place rather than silently avoided: axis A7 (confirm_bars)
moves the crown from two causal filters to THREE.  Filter STACKING on NOISE is closed
ground (18 cells, clean negative, 2026-08-21) and NOISE.md forbids re-proposing a
filter stack without new forward data.  A7 is therefore run and reported ONLY as a
stability curve for a knob that is already in the live configuration at its default
of 1.  No value of A7 may be proposed for adoption by this study under any outcome,
whatever the numbers say.
===============================================================================
"""
import os, sys, json, time
import datetime as _dt
_dtp = lambda t: _dt.datetime.strptime(t, '%Y-%m-%d')

# The master-CSV registry lives only in the shared checkout, not in a worktree.
EDGELOG_ROOT = os.environ.get("EDGELOG_DATA_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(EDGELOG_ROOT, "tools"), EDGELOG_ROOT):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import numpy as np                                                    # noqa: E402
from noise_variant_research import (CHAMPION, SEL_DATE_TO, FEE, MULT,  # noqa: E402
                                    run_variant, metrics, load_arrays)
from augur_engine.engine import _apply_costs                          # noqa: E402
from augur_engine.analytics import (sharpe_from_trades, sortino_from_trades,  # noqa: E402
                                    avg_win_loss, expectancy_r)               # noqa: E402

# ---------------------------------------------------------------- the crown --
CROWN = dict(CHAMPION, daytype_mode="skip_bot_short", daytype_lo=0.20,
             rv_mode="skip_hi", rv_pct=90.0)

GATE_CELLS = [
    ("#231 champion core (filters off)", dict(CHAMPION), 5113, 277123.31, -19482.27),
    ("crown #243 (SBS lo0.20 + vs90)",   dict(CROWN),    4054, 320130.0,  -18425.0),
]
TOL = 1.0

# pre-registered thresholds (B3)
PLATEAU_KEEP = 0.80
SPIKE_KEEP = 0.60
PF_FLOOR = 1.20

NOT_MEASURABLE = [
    ("exit_mode='boundary'",
     "run_variant does not implement it -- an intrabar touch-fill model, a different "
     "fill convention rather than one step off 'vwap'"),
    ("stop_mode='atr'", "not implemented in run_variant"),
    ("stop_mode='fixed'",
     "implemented, but stop_k there is 100-point units, so k=1.75 = a 175-point stop; "
     "not one step off a bandwidth stop -- comparing them is a category error"),
    ("skip_holidays=True", "not implemented in run_variant"),
]


# ------------------------------------------------------------------ plumbing --
_RUN_CACHE = {}


def _key(params):
    return tuple(sorted((k, v) for k, v in params.items()))


def run_cell(params):
    """metrics + raw trade list for one config, cached."""
    k = _key(params)
    if k in _RUN_CACHE:
        return _RUN_CACHE[k]
    arr = load_arrays(SEL_DATE_TO)
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    m = metrics(tr, arr["index"])
    out = {"m": m, "trades": tr}
    _RUN_CACHE[k] = out
    return out


def net_trades(trades):
    return _apply_costs({"trades": list(trades)}, FEE)["trades"]


def gate(verbose=True):
    ok = True
    for label, params, en, enet, edd in GATE_CELLS:
        m = run_cell(params)["m"]
        good = (m["n"] == en and abs(m["net"] - enet) < TOL and abs(m["dd"] - edd) < TOL)
        ok = ok and good
        if verbose:
            print("  %-36s n=%-5d net=$%-11s DD=$%-10s  %s" % (
                label, m["n"], format(m["net"], ",.0f"), format(abs(m["dd"]), ",.0f"),
                "PASS" if good else "FAIL exp n=%d net=%.2f dd=%.2f" % (en, enet, edd)))
    return ok


# --------------------------------------------------------------- axis specs --
def axes():
    """Exactly the cells of B2.  crown_at = the value that IS the crown."""
    A = []
    A.append(dict(
        key="A1", knob="lookback", label="lookback (sessions)", kind="ordinal",
        grid=[28, 36, 40, 44, 48, 52, 60], crown_at=44, immediate=[40, 48],
        mk=lambda v: dict(CROWN, lookback=v), disp=lambda v: "%d" % v,
        note="warm-up scales with the knob: a cell starts trading `lookback` sessions "
             "into the window, so lookback 60 forfeits 16 sessions that 44 trades"))
    A.append(dict(
        key="A2", knob="band_mult_long", label="upper band width (x noise)",
        kind="ordinal", grid=[0.50, 0.75, 1.00, 1.25, 1.50], crown_at=0.75,
        immediate=[0.50, 1.00], mk=lambda v: dict(CROWN, band_mult_long=v),
        disp=lambda v: "%.2f" % v,
        note="0.25 is below the strategy file's min of 0.50 and is not run"))
    A.append(dict(
        key="A3", knob="band_mult_short", label="lower band width (x noise)",
        kind="ordinal", grid=[1.00, 1.25, 1.50, 1.75, 2.00], crown_at=1.50,
        immediate=[1.25, 1.75], mk=lambda v: dict(CROWN, band_mult_short=v),
        disp=lambda v: "%.2f" % v, note=""))
    A.append(dict(
        key="A4", knob="stop_k", label="bandwidth stop size (x band excursion)",
        kind="ordinal", grid=[1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50],
        crown_at=1.75, immediate=[1.50, 2.00],
        mk=lambda v: dict(CROWN, stop_k=v), disp=lambda v: "%.2f" % v,
        endpoints=[("stop OFF (stop_mode='off')", dict(CROWN, stop_mode="off"))],
        note=""))
    A.append(dict(
        key="A5", knob="daytype_lo", label="bottom close-position threshold",
        kind="ordinal", grid=[0.10, 0.15, 0.20, 0.25, 0.30], crown_at=0.20,
        immediate=[0.15, 0.25], mk=lambda v: dict(CROWN, daytype_lo=v),
        disp=lambda v: "%.2f" % v,
        endpoints=[("day-type OFF (= vs90 alone)", dict(CROWN, daytype_mode="off"))],
        which_days=True, note="changes WHICH DAYS trade -- see the decomposition"))
    A.append(dict(
        key="A6", knob="rv_pct", label="vol_skip_pct (skip above prior-day vol pct)",
        kind="ordinal", grid=[80.0, 85.0, 90.0, 95.0, 98.0], crown_at=90.0,
        immediate=[85.0, 95.0], mk=lambda v: dict(CROWN, rv_pct=v),
        disp=lambda v: "%.0f" % v,
        endpoints=[("vol-skip OFF (= run #241)", dict(CROWN, rv_mode="off"))],
        which_days=True, note="changes WHICH DAYS trade -- see the decomposition"))
    A.append(dict(
        key="A7", knob="confirm_bars", label="entry confirmation (closes outside band)",
        kind="ordinal", grid=[1, 2, 3], crown_at=1, immediate=[2],
        mk=lambda v: dict(CROWN, confirm_bars=v), disp=lambda v: "%d" % v,
        edge=True, closed_ground=True,
        note="EDGE cell (crown sits at the grid minimum, one neighbour only). "
             "CLOSED GROUND for adoption: any value > 1 makes #243 a THREE-filter "
             "stack, and filter stacking on NOISE was closed 2026-08-21"))
    return A


def categorical():
    return [
        dict(key="C1", knob="exit_mode", label="exit rule", crown_at="vwap",
             grid=["vwap", "band"], mk=lambda v: dict(CROWN, exit_mode=v),
             disp=lambda v: v),
        dict(key="C2", knob="side", label="direction", crown_at="Both",
             grid=["Both", "Long Only", "Short Only"],
             mk=lambda v: dict(CROWN, side=v), disp=lambda v: v),
        dict(key="C3", knob="window", label="entry window", crown_at="all_day",
             grid=["all_day", "morning", "afternoon_block"],
             mk=lambda v: dict(CROWN, window=v), disp=lambda v: v),
    ]


# ------------------------------------------------------- verdict machinery ---
SEL_YEARS = (_dtp(SEL_DATE_TO) - _dtp("2010-06-07")).days / 365.25


def row_of(m, trades=None):
    """The cell's figures for the JSON. `trades` is the RAW (pre-cost) trade list.

    THE FOUR EXTRA FIGURES (added 2026-08-28, owner: "can you backfill this info").
    Nothing ever recorded a win rate, a Sharpe, a Sortino or an average loss for a
    local sweep, which is why those four axes on COMPARE > STUDIES read `not
    recorded` for every stage-1 row. They are not looked up - nothing stored them -
    they are recomputed here from the cell's own trades, net of cost, using the SAME
    functions augur_engine/analytics.py gives run_backtest and validate. One
    definition of Sharpe across the whole project, so a sweep row and an
    Auto-Validate row can sit on one axis honestly.

    Money figures stay in DOLLARS (x MULT) as the rest of this file reports them;
    avg_loss is therefore dollars too, and positive, as validate has always stored it.
    """
    r = {"n": m["n"], "net": m["net"], "pf": m["pf"], "dd": abs(m["dd"]),
         "mar": m["mar"], "era_2010_17": m["era_2010_17"],
         "worst_year": m["worst_year"], "worst_year_net": m["worst_year_net"]}
    if trades:
        nt = net_trades(trades)
        pnls = [t[2] for t in nt if len(t) >= 3]
        if pnls:
            r["win"] = 100.0 * sum(1 for x in pnls if x > 0) / len(pnls)
        sh = sharpe_from_trades(nt, SEL_YEARS)
        so = sortino_from_trades(nt, SEL_YEARS)
        aw, al = avg_win_loss(nt)
        er = expectancy_r(nt)
        if sh is not None:
            r["sharpe"] = sh
        if so is not None:
            r["sortino"] = so
        if aw is not None:
            r["avg_win"] = aw * MULT
        if al is not None:
            r["avg_loss"] = al * MULT
        if er is not None:
            r["evr"] = er
    return r


def judge_axis(ax, rows, crown_row):
    """B3, applied verbatim."""
    net_s, mar_s = crown_row["net"], crown_row["mar"]
    verdict = "PLATEAU"
    detail = []
    for v in ax["immediate"]:
        r = rows[v]
        keep_net = r["net"] / net_s if net_s else float("nan")
        keep_mar = r["mar"] / mar_s if mar_s else float("nan")
        if keep_net < SPIKE_KEEP or keep_mar < SPIKE_KEEP or r["pf"] < PF_FLOOR:
            cell = "SPIKE"
        elif keep_net >= PLATEAU_KEEP and keep_mar >= PLATEAU_KEEP and r["pf"] >= PF_FLOOR:
            cell = "PLATEAU"
        else:
            cell = "SLOPE"
        detail.append({"value": v, "keep_net": keep_net, "keep_mar": keep_mar,
                       "pf": r["pf"], "cell": cell})
        if cell == "SPIKE":
            verdict = "SPIKE"
        elif cell == "SLOPE" and verdict != "SPIKE":
            verdict = "SLOPE"
    best_net = max(ax["grid"], key=lambda v: rows[v]["net"])
    best_mar = max(ax["grid"], key=lambda v: rows[v]["mar"])
    return {"verdict": verdict, "detail": detail,
            "argmax_net": best_net, "argmax_mar": best_mar,
            "crown_is_argmax_net": best_net == ax["crown_at"],
            "crown_is_argmax_mar": best_mar == ax["crown_at"]}


# ------------------------------------------------- which-days decomposition --
def decompose(cell_trades, crown_trades):
    """B4.  Keys = (entry bar, direction).  Shared trades are identical trades."""
    ct = net_trades(cell_trades)
    kt = net_trades(crown_trades)
    ck = {(t[0], t[3]): t[2] * MULT for t in ct}
    kk = {(t[0], t[3]): t[2] * MULT for t in kt}
    only_cell = [v for k, v in ck.items() if k not in kk]
    only_crown = [v for k, v in kk.items() if k not in ck]
    shared = [k for k in ck if k in kk]
    return {
        "n_shared": len(shared),
        "n_added": len(only_cell), "usd_added": sum(only_cell),
        "n_removed": len(only_crown), "usd_removed": sum(only_crown),
        "per_added": (sum(only_cell) / len(only_cell)) if only_cell else None,
        "per_removed": (sum(only_crown) / len(only_crown)) if only_crown else None,
        "identity": sum(only_cell) - sum(only_crown),
    }


def concentration(cell_trades, ref_trades):
    """B5.  Carried verbatim from the 2026-08-21 rule 5."""
    ct = net_trades(cell_trades)
    rt = net_trades(ref_trades)
    ckeys = {(t[0], t[3]) for t in ct}
    removed = sorted(t[2] * MULT for t in rt if (t[0], t[3]) not in ckeys)
    d_net = sum(t[2] * MULT for t in ct) - sum(t[2] * MULT for t in rt)
    top10 = -sum(removed[:10])
    return {"d_net": d_net, "n_removed": len(removed), "top10_avoided": top10,
            "top10_share": (top10 / d_net) if abs(d_net) > 1e-9 else float("nan"),
            "d_ex_top10": d_net - top10,
            "survives": (d_net - top10) > 0,
            "worst_removed": removed[:10]}


# ---------------------------------------------------------------- printing ---
HDR = ("%-10s %7s %13s %7s %12s %8s %11s %12s" %
       ("value", "trades", "net $", "PF", "maxDD $", "net/DD", "2010-17 $", "worst yr $"))


def prow(tag, r, mark=""):
    return ("%-10s %7d %13s %7.3f %12s %8.2f %11s %12s %s" % (
        tag, r["n"], format(r["net"], ",.0f"), r["pf"], format(r["dd"], ",.0f"),
        r["mar"], format(r["era_2010_17"], ",.0f"),
        "%s %s" % (r["worst_year"], format(r["worst_year_net"], ",.0f")), mark))


def main():
    t0 = time.time()
    print("NOISE STUDY B -- plateau or spike around the crowned run #243")
    print("selection window 2010-06-07 -> %s | NQ 5m RTH db_noadj_rth | "
          "cost %.3f pts round-turn | $%.0f/pt | 1 contract" % (SEL_DATE_TO, FEE, MULT))
    print("lockbox 2025-02-11..2026-08-12 is SPENT and is NOT read anywhere in this study\n")

    print("[GATE] B6 reproduction gate:")
    if not gate():
        print("\nGATE FAILED -- refusing to proceed.")
        sys.exit(1)
    print("  GATE PASS\n")
    if "--gate" in sys.argv:
        return

    crown = run_cell(dict(CROWN))
    crown_row = row_of(crown["m"], crown["trades"])
    print("[CROWN] net $%s | PF %.3f | maxDD $%s | net/DD %.2f | %d trades | "
          "$%.2f per trade" % (
              format(crown_row["net"], ",.0f"), crown_row["pf"],
              format(crown_row["dd"], ",.0f"), crown_row["mar"], crown_row["n"],
              crown_row["net"] / crown_row["n"]))
    print("        pre-registered bar: PLATEAU needs both immediate neighbours at "
          ">= %.0f%% of net ($%s) AND >= %.0f%% of net/DD (%.2f) AND PF >= %.2f; "
          "SPIKE at < %.0f%%." % (
              100 * PLATEAU_KEEP, format(PLATEAU_KEEP * crown_row["net"], ",.0f"),
              100 * PLATEAU_KEEP, PLATEAU_KEEP * crown_row["mar"], PF_FLOOR,
              100 * SPIKE_KEEP))

    out = {"crown": crown_row, "axes": {}, "categorical": {},
           "bar": {"plateau_keep": PLATEAU_KEEP, "spike_keep": SPIKE_KEEP,
                   "pf_floor": PF_FLOOR}}

    verdicts = {}
    for ax in axes():
        print("\n" + "=" * 118)
        print("%s  %s  --  %s" % (ax["key"], ax["knob"], ax["label"]))
        if ax.get("note"):
            print("    note: %s" % ax["note"])
        print("-" * 118)
        print(HDR)
        rows = {}
        traces = {}
        for v in ax["grid"]:
            d = run_cell(ax["mk"](v))
            rows[v] = row_of(d["m"], d["trades"])
            traces[v] = d["trades"]
            mark = "<-- CROWN" if v == ax["crown_at"] else (
                "  (immediate neighbour)" if v in ax["immediate"] else "")
            print(prow(ax["disp"](v), rows[v], mark))
        for lab, params in ax.get("endpoints", []):
            d = run_cell(params)
            r = row_of(d["m"], d["trades"])
            traces[lab] = d["trades"]
            rows[lab] = r
            print(prow("OFF", r, "  [%s -- endpoint, not a neighbour]" % lab))

        j = judge_axis(ax, rows, crown_row)
        verdicts[ax["key"]] = j
        print("-" * 118)
        for d in j["detail"]:
            print("    neighbour %-6s keeps %5.1f%% of net, %5.1f%% of net/DD, "
                  "PF %.3f -> %s" % (ax["disp"](d["value"]), 100 * d["keep_net"],
                                     100 * d["keep_mar"], d["pf"], d["cell"]))
        print("    AXIS VERDICT: %s%s" % (
            j["verdict"], "   (EDGE cell -- one neighbour only)" if ax.get("edge") else ""))
        print("    best on net across this axis = %s%s ; best on net/DD = %s%s" % (
            ax["disp"](j["argmax_net"]),
            " (the crown)" if j["crown_is_argmax_net"] else " -- NOT the crown",
            ax["disp"](j["argmax_mar"]),
            " (the crown)" if j["crown_is_argmax_mar"] else " -- NOT the crown"))
        if ax.get("closed_ground"):
            print("    ** CLOSED GROUND: no value on this axis may be proposed for "
                  "adoption, whatever the numbers say. **")

        axout = {"knob": ax["knob"], "grid": [ax["disp"](v) for v in ax["grid"]],
                 "rows": {ax["disp"](v): rows[v] for v in ax["grid"]},
                 "endpoints": {lab: rows[lab] for lab, _ in ax.get("endpoints", [])},
                 "judge": j, "note": ax.get("note", "")}

        # ---- B4 which-days decomposition (A5, A6 only) ----
        if ax.get("which_days"):
            print("\n    [WHICH DAYS TRADE] vs the crown -- shared trades are the "
                  "IDENTICAL trade, so net(cell)-net(crown) is exactly")
            print("    $(only in cell) - $(only in crown).  The question is whether the "
                  "dropped days deserved dropping.")
            print("    %-10s %8s %8s %14s %12s %8s %14s %12s %11s" % (
                "value", "trades", "d trades", "d net $", "removed n", "$/removed",
                "added $", "added n", "d maxDD $"))
            dec = {}
            for v in list(ax["grid"]) + [lab for lab, _ in ax.get("endpoints", [])]:
                dd = decompose(traces[v], crown["trades"])
                dec[str(ax["disp"](v)) if v in ax["grid"] else v] = dd
                r = rows[v]
                print("    %-10s %8d %8d %14s %12d %8s %14s %12d %11s" % (
                    ax["disp"](v) if v in ax["grid"] else "OFF",
                    r["n"], r["n"] - crown_row["n"],
                    format(r["net"] - crown_row["net"], ",.0f"),
                    dd["n_removed"],
                    ("%.0f" % dd["per_removed"]) if dd["per_removed"] is not None else "-",
                    format(dd["usd_added"], ",.0f"), dd["n_added"],
                    format(r["dd"] - crown_row["dd"], ",.0f")))
            axout["which_days"] = dec

        # ---- B5 concentration re-check (A6 primary, A5 for symmetry) ----
        if ax.get("endpoints") and ax.get("which_days"):
            ref_lab = ax["endpoints"][0][0]
            hdr = ("    %-10s %14s %12s %16s %10s %16s %s" % (
                "value", "d net $", "removed n", "top-10 avoided", "share",
                "d net ex-top10", "verdict"))

            def _conc_block(title, pairs):
                print("\n    %s" % title)
                print(hdr)
                got = {}
                for tag, cell_tr, ref_tr in pairs:
                    c = concentration(cell_tr, ref_tr)
                    got[tag] = c
                    # share is undefined when the improvement it divides is ~zero
                    share = ("%9.0f%%" % (100 * c["top10_share"])
                             if abs(c["d_net"]) > 1000 else "        -")
                    print("    %-10s %14s %12d %16s %s %16s %s" % (
                        tag, format(c["d_net"], ",.0f"), c["n_removed"],
                        format(c["top10_avoided"], ",.0f"), share,
                        format(c["d_ex_top10"], ",.0f"),
                        "SURVIVES" if c["survives"] else "DISQUALIFIED"))
                if any(abs(c["d_net"]) <= 1000 for c in got.values()):
                    print("    share is a dash where |d net| <= $1,000: it divides by an "
                          "improvement that is ~zero, so the ratio is not a figure that "
                          "exists.")
                return got

            # (i) IN-CROWN: the knob moving inside the live configuration.
            con = _conc_block(
                "[CONCENTRATION i -- IN-CROWN] each value vs the knob-OFF reference "
                "(%s); pre-registered rule 5" % ref_lab,
                [(ax["disp"](v), traces[v], traces[ref_lab]) for v in ax["grid"]])
            axout["concentration_in_crown"] = con

            # (ii) STANDALONE: the knob alone on the #231 champion core, which is how
            # the 2026-08-23 crowning card measured it.  B5 promised both readings.
            if ax["key"] == "A6":
                pairs = [(ax["disp"](v),
                          run_cell(dict(CHAMPION, rv_mode="skip_hi", rv_pct=v))["trades"],
                          run_cell(dict(CHAMPION))["trades"]) for v in ax["grid"]]
            else:
                pairs = [(ax["disp"](v),
                          run_cell(dict(CHAMPION, daytype_mode="skip_bot_short",
                                        daytype_lo=v))["trades"],
                          run_cell(dict(CHAMPION))["trades"]) for v in ax["grid"]]
            axout["concentration_standalone"] = _conc_block(
                "[CONCENTRATION ii -- STANDALONE] each value alone on the #231 champion "
                "core vs that core: the reading the 2026-08-23 crowning card used",
                pairs)
        out["axes"][ax["key"]] = axout

    # ------------------------------------------------ categorical block ------
    print("\n" + "=" * 118)
    print("CATEGORICAL BLOCK -- reported, NO plateau/spike verdict (these knobs have "
          "no ordering, so 'one step off' is undefined)")
    print("=" * 118)
    for cx in categorical():
        print("\n%s  %s  --  %s" % (cx["key"], cx["knob"], cx["label"]))
        print(HDR)
        crows = {}
        for v in cx["grid"]:
            _c = run_cell(cx["mk"](v)); r = row_of(_c["m"], _c["trades"])
            crows[v] = r
            print(prow(cx["disp"](v), r, "<-- CROWN" if v == cx["crown_at"] else ""))
        out["categorical"][cx["key"]] = {"knob": cx["knob"], "rows": crows}

    print("\n" + "=" * 118)
    print("NOT MEASURABLE -- reported as a dash with a reason, never as a zero")
    print("=" * 118)
    for lab, why in NOT_MEASURABLE:
        print("  %-24s  -   %s" % (lab, why))

    # ---------------------------------------------------- overall verdict ----
    print("\n" + "=" * 118)
    ordinal = [a["key"] for a in axes()]
    n_plat = sum(1 for k in ordinal if verdicts[k]["verdict"] == "PLATEAU")
    n_slope = sum(1 for k in ordinal if verdicts[k]["verdict"] == "SLOPE")
    spikes = [k for k in ordinal if verdicts[k]["verdict"] == "SPIKE"]
    overall = "PLATEAU" if (not spikes and n_plat >= 5) else "RIDGE"
    print("OVERALL (pre-registered B3): %d of %d ordinal axes PLATEAU, %d SLOPE, "
          "%d SPIKE%s" % (n_plat, len(ordinal), n_slope, len(spikes),
                          (" [%s]" % ", ".join(spikes)) if spikes else ""))
    print("  -> the crown sits on a %s" % overall)
    for k in ordinal:
        print("     %-4s %-16s %s" % (k, [a["knob"] for a in axes() if a["key"] == k][0],
                                      verdicts[k]["verdict"]))
    out["overall"] = {"verdict": overall, "n_plateau": n_plat, "n_slope": n_slope,
                      "spikes": spikes,
                      "per_axis": {k: verdicts[k]["verdict"] for k in ordinal}}
    print("\nNothing above is crowned.  The spent lockbox was not opened.")
    print("elapsed %.0fs" % (time.time() - t0))

    p = os.path.join(EDGELOG_ROOT, "_noise_plateau_243.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=float)
    print("wrote %s" % p)


if __name__ == "__main__":
    main()
