"""Layer 3 — the daily three-way reconcile: which layer diverged today?

The PAPER system runs the same strategies in three places (see PAPER_TRADING.md):

  Layer 0 SHADOW    the engine re-run on fresh data — what we BELIEVE should happen
  Layer 1 NT DEMO   NinjaScript on the broker demo account — what a broker ACTUALLY filled
  Layer 2 TV        an independent engine — periodic, manual, not part of this file

Layers 0 and 1 disagree for exactly four reasons, and telling them apart is the whole
job here:

  * shadow trade with no live counterpart  -> the demo did not take a signal we expected
    (strategy disabled, order rejected, NinjaScript logic differs, data feed gap)
  * live trade with no shadow counterpart  -> the demo took something the engine did not
    (this is the one that caught the 2026-08-13 NinjaTrader bar-of-day bug in backtest:
    322 trades against the engine's 191)
  * matched pair, different PRICE          -> slippage. This is the number the whole
    PAPER exercise exists to measure, and it is only meaningful on MATCHED trades.
  * matched pair, different SIZE           -> added 2026-08-26. Slippage answers "did the
    broker fill where we expected"; nothing answered "did the broker trade the QUANTITY the
    strategy asked for". A gated leg's whole claim is that it sizes by model score, so a
    matched pair at the right price and the wrong size is a leg whose headline number is
    fiction. See _grade_sizes for what this file can and cannot prove about that.

ATTRIBUTION IS BY SIGNAL NAME, WITH A TIMING FALLBACK — read this before trusting a
leg-level verdict. `C:\\EdgeLog\\fills.csv` records ExecutionId, Time, Account, Instrument,
Action, Qty, Price, Commission, OrderId and — since 2026-08-13 — SignalName
(tools/EdgeLogExport.cs:79-80). That column IS the strategy naming itself, so attribution is
a fact whenever it is present: nt_sync.parse_fills reads it by header name
(api/nt_sync.py:238 — a csv.DictReader, not a positional split) and build_trades carries the
OPENING fill's name onto the finished round-turn as `signal` (api/nt_sync.py:352).

The timing matcher is now only the FALLBACK, for the two cases where no name exists: rows
written before 2026-08-13, and manual/discretionary fills. Both live legs trade NQ, so a
nameless fill cannot be attributed with certainty; it is assigned to whichever leg has the
nearest unmatched shadow entry in time, and when two legs both have a candidate inside the
tolerance the trade is reported as AMBIGUOUS rather than assigned, because a wrong
attribution would quietly move slippage from one strategy's ledger to another's — the kind
of error that looks like a result.

Never raises: this runs inside the runner's watch loop.
"""
from datetime import datetime, timedelta

# How far apart a shadow entry and a live entry may be and still be the same trade.
# The demo fills at the next bar's open on a 1m/5m chart, and the AddOn stamps the
# broker's fill time, so a couple of minutes of drift is normal. Wider than this and a
# "match" starts being a coincidence between two nearby signals.
TOL_MIN = 3

NY = "America/New_York"

# NinjaTrader turns the engine's size multiplier into whole contracts with
# q = (int)Math.Round(size * Qty), floored at 1 (tools/nt/EdgeLogNOISE.cs:138-139), so even a
# perfectly obedient broker lands up to half a contract either side of the intent. Anything
# inside that slack is rounding; anything outside it is the size dial doing something the
# engine did not ask for.
_SIZE_SLACK = 0.5 + 1e-9

# Signal-name prefix -> leg. EdgeLogExport.cs began logging the signal name on
# 2026-08-13, which turns attribution from a timing GUESS into a fact. Rows written
# before that carry an empty signal, and so do manual/discretionary fills, so an empty
# value means "unknown" and falls back to the timing matcher - it never silently picks
# a leg. Keep these in step with the NinjaScripts' EnterLong/ExitLong signal names.
# 2026-08-26: NZ and EQ pointed at "NOISE" and "ENGUQ", leg keys that stopped producing
# shadow trades when those legs were retired (NOISE on 08-16, ENGUQ on 08-21). A fill whose
# signal maps to a leg that is not in today's report matches NOTHING -- the candidate filter
# below requires c["leg"] == known_leg -- so it lands in `ambiguous` while EVERY leg of that
# family is left in shadow_only, i.e. the board would paint a red "NinjaTrader never took it"
# cross on the very leg NinjaTrader had just filled. No NZ fill has landed since the rename,
# so nothing recorded is wrong; the next one would have been. These now name the legs whose
# `nt` field claims those NinjaScripts: EdgeLogNOISE -> NOISE_H_RF, EdgeLogENGUQ1m -> ENGUQ_ER.
SIGNAL_PREFIX = {"NZ": "NOISE_H_RF", "EQ": "ENGUQ_ER", "ORB": "ORB"}


def _map_signal(sig):
    """(prefix, leg) for a fill's signal name, or (None, None) when it cannot be known.

    The PREFIX comes back too so a rejection can quote the rule that produced it. A reason
    that says only "not in today's report" sends the next reader hunting for the mapping;
    one that names the prefix and the leg it resolved to explains itself.
    """
    s = (sig or "").strip().upper()
    if not s:
        return None, None
    # Longest prefix first so "ORB" is never shadowed by a shorter key.
    for pre in sorted(SIGNAL_PREFIX, key=len, reverse=True):
        if s.startswith(pre):
            return pre, SIGNAL_PREFIX[pre]
    return None, None


def leg_from_signal(sig):
    """Exact leg for a fill's signal name, or None when it cannot be known."""
    return _map_signal(sig)[1]


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


def _num(v):
    """float(v) or None. None means UNKNOWN and must stay None all the way to the board —
    defaulting a missing size to 1.0 would invent the exact number this is measuring."""
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _grade_sizes(matched):
    """Fill in decision_agree for ONE leg's matched rows. Mutates them in place.

    The two sizes are in different units and that is the whole difficulty. The shadow side
    is a MULTIPLIER (api/paper.py:858 — 1.0 for every raw leg, the model's score for a
    hybrid); the live side is a CONTRACT COUNT (api/nt_sync.py:341). Turning one into the
    other needs NinjaTrader's `Qty` parameter, which never reaches this file, so there is no
    honest per-row "expected 11, got 9" available here.

    What IS available without inventing anything: the ratio live/shadow is the contracts the
    broker gave per unit of intended size, and `Qty` is a constant for a NinjaScript across a
    day — so on a leg whose dial is working that ratio is the SAME on every trade. The leg's
    own median ratio becomes the reference and each row is judged against it, floored at one
    contract exactly as NinjaTrader floors it. A leg that traded a flat size all day while
    the engine asked for varying ones scatters those ratios and gets flagged.

    Two limits, stated so nobody reads more into a "yes" than is there: with one matched
    trade there is nothing to compare against, and this test cannot see the Qty*3 cap
    (tools/nt/EdgeLogNOISE.cs:140) at all, because a day that was capped on every trade
    simply drags the reference down with it. The definitive per-decision answer is
    q_intended vs q_ordered in C:\\EdgeLog\\gate_decisions.csv; this is the after-the-fact
    check that works on the fills alone.
    """
    ratios = sorted(r["size_ratio"] for r in matched if r["size_ratio"] is not None)
    n = len(ratios)
    ref = None
    if n >= 2:
        ref = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2.0
    for r in matched:
        if r["shadow_size"] is None:
            r["decision_agree"] = "unknown: shadow trade carries no size"
        elif r["live_size"] is None:
            r["decision_agree"] = "unknown: live fill carries no size"
        elif r["shadow_size"] <= 0:
            r["decision_agree"] = "unknown: engine asked for size 0"
        elif ref is None:
            r["decision_agree"] = "unknown: one matched trade, no ratio to compare against"
        else:
            # max(1, ...) mirrors NinjaTrader's own floor: an intent that rounds below one
            # contract still trades one, and that is obedience, not a mismatch.
            expect = max(1.0, r["shadow_size"] * ref)
            # THE SLACK HAS TO SCALE WITH THE ROW. `ref` is a median of ratios estimated
            # from the fills themselves, so its error is a PERCENTAGE, and multiplying it
            # by a bigger shadow size produces a bigger absolute error. A flat half-contract
            # tolerance therefore passes small trades and fails large ones for the same
            # underlying agreement -- it would have reported the biggest, most consequential
            # positions as mismatches while waving through the small ones.
            # Half a contract OR 10% of what we expect, whichever is more forgiving, plus
            # the rounding NinjaTrader itself does on the way to whole contracts.
            slack = max(_SIZE_SLACK, 0.10 * expect)
            r["decision_agree"] = "yes" if abs(r["live_size"] - expect) <= slack else "no"


def match_day(shadow_by_leg, live_trades, *, tol_min=TOL_MIN):
    """Pair shadow trades against live round-turns for ONE day.

    shadow_by_leg : {leg_key: [ {side, entryIso, entry_px, exit_px, pnl_usd, size}, ... ]}
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
    # Named once so every rejection reason can list what the fill COULD have been matched
    # to. "maps to a leg not in today's report" is only useful next to the report's legs.
    legs_today = ", ".join(sorted(results)) or "none"

    for lv in live_trades or []:
        ldt = _live_entry_dt(lv)
        if ldt is None:
            continue
        lside = _side_of(lv)
        # Prefer the signal name when the fill carries one: that is the strategy telling
        # us which leg it is, rather than us inferring it from the clock.
        sig = lv.get("signal")
        pre, known_leg = _map_signal(sig)
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
                # Spell the whole chain out. This is the failure the 2026-08-26 rename fixed
                # and it is silent by nature: the fill is real, the leg is real, only the
                # mapping is stale, and the board shows the leg as never traded. Naming the
                # prefix, the table it came from and the legs that WERE on the board turns
                # the next occurrence into a one-line read instead of a re-investigation.
                ambiguous.append({"kind": "live_only", "live": lv,
                                  "reason": f"signal {sig!r} matched SIGNAL_PREFIX "
                                            f"{pre!r} -> leg {known_leg}, which is not in "
                                            f"today's report (legs today: {legs_today}); "
                                            f"fix the mapping in paper_reconcile."
                                            f"SIGNAL_PREFIX, not the fill"})
            continue
        if not near:
            # No shadow trade explains this fill. Which leg it belongs to is unknowable,
            # so it is reported globally rather than blamed on one strategy. Say WHICH
            # unknowable it is: an unmapped signal is a one-line fix in SIGNAL_PREFIX, a
            # nameless fill is a genuinely undecidable manual/pre-2026-08-13 row.
            why = ("fill carries no signal name (manual, or written before 2026-08-13)"
                   if not (sig or "").strip()
                   else f"signal {sig!r} matches no SIGNAL_PREFIX key "
                        f"({', '.join(sorted(SIGNAL_PREFIX))})")
            ambiguous.append({"kind": "live_only", "live": lv,
                              "reason": f"no shadow signal within {tol_min}m; {why}"})
            continue
        legs_in_reach = {c["leg"] for c in near}
        if known_leg is None and len(legs_in_reach) > 1:
            ambiguous.append({"kind": "ambiguous", "live": lv,
                              "candidate_legs": sorted(legs_in_reach),
                              "reason": f"two legs have a signal inside the tolerance and "
                                        f"the fill's signal {sig!r} names no leg"})
            continue
        best = min(near, key=lambda c: abs(c["dt"] - ldt))
        best["taken"] = True
        s = best["s"]
        # Sizes ride with the pair from here on. shadow_size is the engine's intended
        # multiplier (api/paper.py:858), live_size is the contracts that actually filled
        # (api/nt_sync.py:341); size_ratio is contracts-per-unit-of-intent, and
        # decision_agree is graded per leg once the day's rows are all in (_grade_sizes).
        ssz = _num(s.get("size"))
        lsz = _num(lv.get("size"))
        # Contracts are whole things. Writing 9.0 where the broker traded 9 invites a
        # reader to wonder whether the extra precision means something.
        if lsz is not None and lsz.is_integer():
            lsz = int(lsz)
        results[best["leg"]]["matched"].append({
            "shadow_entry": s.get("entryIso"), "live_entry": lv.get("entryTime"),
            "drift_min": round((ldt - best["dt"]).total_seconds() / 60.0, 1),
            # Slippage signed AGAINST us: positive means the live fill was worse.
            "entry_slip_pts": round(
                (lv.get("entry", 0) - s.get("entry_px", 0)) * (1 if lside > 0 else -1), 2),
            "shadow_pnl_usd": s.get("pnl_usd"), "live_pnl_usd": lv.get("pnl"),
            "pnl_diff_usd": round((lv.get("pnl") or 0) - (s.get("pnl_usd") or 0), 2),
            "shadow_size": ssz, "live_size": lsz,
            "size_ratio": (round(lsz / ssz, 3) if (ssz and lsz is not None) else None),
            "decision_agree": None,
        })

    for r in results.values():
        _grade_sizes(r["matched"])

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
        # A right-price/wrong-size pair reads as a clean match everywhere else on the board,
        # so it has to be said out loud here or it is invisible.
        bad = sum(1 for x in r["matched"] if x.get("decision_agree") == "no")
        if bad:
            line += f", {bad} SIZE-MISMATCH"
            out["problems"].append(
                f"{leg}: {bad} matched trade(s) where the broker's size did not follow "
                f"the engine's")
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
    # Says why every decision_agree is a dash on days paper.py's Layer-3 hand-off does not
    # carry the shadow multiplier. Better a stated gap than a column nobody trusts.
    if any(x.get("shadow_size") is None
           for blk in rec["legs"].values() for x in blk["matched"]):
        rec["size_note"] = ("shadow size missing on at least one matched trade: paper.py's "
                            "_emit hands Layer 3 side/entryIso/prices/pnl only, so the "
                            "gate multiplier it writes to Firestore (api/paper.py:1160) "
                            "never reaches this file")
    return rec
