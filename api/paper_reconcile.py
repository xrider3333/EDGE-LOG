"""Layer 3 — the daily three-way reconcile: which layer diverged today?

The PAPER system runs the same strategies in three places (see PAPER_TRADING.md):

  Layer 0 SHADOW    the engine re-run on fresh data — what we BELIEVE should happen
  Layer 1 NT DEMO   NinjaScript on the broker demo account — what a broker ACTUALLY filled
  Layer 2 TV        an independent engine — periodic, manual, not part of this file

Layers 0 and 1 disagree for exactly three reasons, and telling them apart is the whole
job here:

  * shadow trade with no live counterpart  -> the demo did not take a signal we expected
    (strategy disabled, order rejected, NinjaScript logic differs, data feed gap)
  * live trade with no shadow counterpart  -> the demo took something the engine did not
    (this is the one that caught the 2026-08-13 NinjaTrader bar-of-day bug in backtest:
    322 trades against the engine's 191)
  * matched pair, different prices         -> slippage. This is the number the whole
    PAPER exercise exists to measure, and it is only meaningful on MATCHED trades.

ATTRIBUTION IS INFERRED, NOT KNOWN — read this before trusting a leg-level verdict.
`C:\\EdgeLog\\fills.csv` records ExecutionId, Time, Account, Instrument, Action, Qty,
Price, Commission, OrderId. There is no strategy name. Both live legs trade NQ, so a fill
cannot be attributed with certainty; it is assigned to whichever leg has the nearest
unmatched shadow entry in time. When two legs both have a candidate inside the tolerance
the trade is reported as AMBIGUOUS rather than assigned, because a wrong attribution would
quietly move slippage from one strategy's ledger to another's — the kind of error that
looks like a result. The permanent fix is a Strategy column in the AddOn's fills.csv;
appending it is safe for the positional parsers in nt_sync.

Never raises: this runs inside the runner's watch loop.
"""
from datetime import datetime, timedelta

# How far apart a shadow entry and a live entry may be and still be the same trade.
# The demo fills at the next bar's open on a 1m/5m chart, and the AddOn stamps the
# broker's fill time, so a couple of minutes of drift is normal. Wider than this and a
# "match" starts being a coincidence between two nearby signals.
TOL_MIN = 3

NY = "America/New_York"

# Signal-name prefix -> leg. EdgeLogExport.cs began logging the signal name on
# 2026-08-13, which turns attribution from a timing GUESS into a fact. Rows written
# before that carry an empty signal, and so do manual/discretionary fills, so an empty
# value means "unknown" and falls back to the timing matcher - it never silently picks
# a leg. Keep these in step with the NinjaScripts' EnterLong/ExitLong signal names.
SIGNAL_PREFIX = {"NZ": "NOISE", "EQ": "ENGUQ", "ORB": "ORB"}


def leg_from_signal(sig):
    """Exact leg for a fill's signal name, or None when it cannot be known."""
    s = (sig or "").strip().upper()
    if not s:
        return None
    # Longest prefix first so "ORB" is never shadowed by a shorter key.
    for pre in sorted(SIGNAL_PREFIX, key=len, reverse=True):
        if s.startswith(pre):
            return SIGNAL_PREFIX[pre]
    return None


def _parse_iso(s):
    """paper_trades stores tz-aware ISO (America/New_York). Return naive NY."""
    try:
        dt = datetime.fromisoformat(str(s))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _live_entry_dt(t):
    """build_trades gives date=YYYY-MM-DD and entryTime=HH:MM, both already NY."""
    try:
        return datetime.strptime(f"{t['date']} {t['entryTime']}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _side_of(live):
    return 1 if str(live.get("type", "")).lower().startswith("long") else -1


def match_day(shadow_by_leg, live_trades, *, tol_min=TOL_MIN):
    """Pair shadow trades against live round-turns for ONE day.

    shadow_by_leg : {leg_key: [ {side, entryIso, entry_px, exit_px, pnl_usd}, ... ]}
    live_trades   : nt_sync.build_trades output, already filtered to the paper account
                    and this date.

    Returns a dict per leg plus an `unattributed` list. A live trade that could belong to
    more than one leg is never assigned — see the module docstring."""
    # Flatten every shadow trade into one candidate pool, tagged with its leg, so a live
    # fill is competed for across legs rather than greedily claimed by whichever leg
    # happens to be iterated first.
    cands = []
    for leg, trades in (shadow_by_leg or {}).items():
        for s in trades or []:
            dt = _parse_iso(s.get("entryIso"))
            if dt is not None:
                cands.append({"leg": leg, "dt": dt, "s": s, "taken": False})

    results = {leg: {"matched": [], "shadow_only": [], "live_only": []}
               for leg in (shadow_by_leg or {})}
    ambiguous = []
    tol = timedelta(minutes=tol_min)

    for lv in live_trades or []:
        ldt = _live_entry_dt(lv)
        if ldt is None:
            continue
        lside = _side_of(lv)
        # Prefer the signal name when the fill carries one: that is the strategy telling
        # us which leg it is, rather than us inferring it from the clock.
        known_leg = leg_from_signal(lv.get("signal"))
        near = [c for c in cands
                if not c["taken"] and c["s"].get("side") == lside
                and abs(c["dt"] - ldt) <= tol
                and (known_leg is None or c["leg"] == known_leg)]
        if known_leg is not None and not near:
            # The strategy named itself but the engine has no matching signal. That is a
            # real divergence in a known leg, not an attribution puzzle, so it belongs in
            # that leg's ledger rather than the unattributed pile.
            if known_leg in results:
                results[known_leg]["live_only"].append(lv)
            else:
                ambiguous.append({"kind": "live_only", "live": lv,
                                  "reason": f"signal {lv.get('signal')} maps to leg "
                                            f"{known_leg}, which is not in today's report"})
            continue
        if not near:
            # No shadow trade explains this fill. Which leg it belongs to is unknowable,
            # so it is reported globally rather than blamed on one strategy.
            ambiguous.append({"kind": "live_only", "live": lv,
                              "reason": "no shadow signal within tolerance"})
            continue
        legs_in_reach = {c["leg"] for c in near}
        if known_leg is None and len(legs_in_reach) > 1:
            ambiguous.append({"kind": "ambiguous", "live": lv,
                              "candidate_legs": sorted(legs_in_reach),
                              "reason": "two legs have a signal inside the tolerance"})
            continue
        best = min(near, key=lambda c: abs(c["dt"] - ldt))
        best["taken"] = True
        s = best["s"]
        results[best["leg"]]["matched"].append({
            "shadow_entry": s.get("entryIso"), "live_entry": lv.get("entryTime"),
            "drift_min": round((ldt - best["dt"]).total_seconds() / 60.0, 1),
            # Slippage signed AGAINST us: positive means the live fill was worse.
            "entry_slip_pts": round(
                (lv.get("entry", 0) - s.get("entry_px", 0)) * (1 if lside > 0 else -1), 2),
            "shadow_pnl_usd": s.get("pnl_usd"), "live_pnl_usd": lv.get("pnl"),
            "pnl_diff_usd": round((lv.get("pnl") or 0) - (s.get("pnl_usd") or 0), 2),
        })

    for c in cands:
        if not c["taken"]:
            results[c["leg"]]["shadow_only"].append({
                "entry": c["s"].get("entryIso"), "side": c["s"].get("side"),
                "pnl_usd": c["s"].get("pnl_usd"),
            })
    return {"legs": results, "unattributed": ambiguous, "tol_min": tol_min}


def verdict(rec, *, live_expected=True):
    """One line per leg plus an overall call, in the terms the owner reads.

    live_expected=False means the NinjaScript strategies are not enabled on charts yet —
    in that state 'shadow trades with no live counterpart' is the DESIGNED state, not a
    divergence, and saying otherwise would train everyone to ignore this field."""
    out = {"legs": {}, "problems": []}
    for leg, r in (rec.get("legs") or {}).items():
        m, so, lo = len(r["matched"]), len(r["shadow_only"]), len(r["live_only"])
        if not live_expected:
            # Count matched too: a fill can still exist from manual testing, and reporting
            # only shadow_only would understate how many signals the engine produced.
            out["legs"][leg] = (f"{m + so} shadow signal(s), {m} coincided with a demo "
                                f"fill; strategies not enabled on charts")
            continue
        if m == 0 and so == 0 and lo == 0:
            out["legs"][leg] = "no signals"
            continue
        slips = [x["entry_slip_pts"] for x in r["matched"] if x.get("entry_slip_pts") is not None]
        avg = (sum(slips) / len(slips)) if slips else 0.0
        line = f"{m} matched (avg entry slip {avg:+.2f} pts)"
        if so:
            line += f", {so} SHADOW-ONLY"
            out["problems"].append(f"{leg}: {so} expected trade(s) the demo never took")
        if lo:
            line += f", {lo} LIVE-ONLY"
            out["problems"].append(
                f"{leg}: {lo} demo trade(s) the engine never signalled")
        out["legs"][leg] = line
    n_un = len(rec.get("unattributed") or [])
    if n_un and live_expected:
        out["problems"].append(f"{n_un} live trade(s) could not be attributed to a leg")
    out["ok"] = not out["problems"]
    return out


def run(target_date, report, *, fills_path=None, live_expected=True):
    """Build the reconcile block for one day's paper report. Never raises.

    `report` is the dict api.paper.maybe_run_eod has just assembled; this reads its
    shadow trades and its already-collected live fills rather than re-reading Firestore."""
    try:
        from . import nt_sync
        from .paper import PAPER_LIVE_ACCOUNT, _FILLS_CSV
        path = fills_path or _FILLS_CSV
        fills = [f for f in nt_sync.parse_fills(path)
                 if f.get("account") == PAPER_LIVE_ACCOUNT]
        live = [t for t in nt_sync.build_trades(fills)
                if t.get("date") == target_date.isoformat()]
    except Exception as e:
        return {"ok": None, "error": f"{type(e).__name__}: {e}",
                "note": "could not read live fills; shadow side is unaffected"}

    # The report's leg block holds trade_ids, not the trades; paper.py hands the trades in
    # under _trades when it calls us so this stays a pure function of what it already has.
    shadow_by_leg = {leg: (blk.get("_trades") or [])
                     for leg, blk in (report.get("legs") or {}).items()}
    rec = match_day(shadow_by_leg, live)
    rec["verdict"] = verdict(rec, live_expected=live_expected)
    rec["n_live_trades"] = len(live)
    return rec
