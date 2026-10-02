"""paper_exitday.py - the PAPER board counts a trade's money on the day it CLOSES.

OWNER GO 2026-10-02 (via MANAGER, FRONTIER inbox #29). Until now `_run_one_uid` counted a
trade on its ENTRY date, which is wrong in three ways the FRONTIER lane measured on the ENGU-Q
crown #335 since 2023 (380 trades):

  * 190 of 380 outlive their entry day, and a multi-day hold was booked on its entry day at
    whatever its exit looked like at 16:10 that night (an in-progress trade's exit moves as bars
    arrive), so the day figure was a mark, not a result;
  * 79 of 380 enter after 16:10 ET - after the nightly report ran - so they landed on NO day:
    the 2026-09-15 22:28 ET entry, +$3,751 at its 09-16 exit, was in no day's figure.

THE RULES (one definition, used by the nightly run, the board and the backfill script):

  1. A trade counts on the US/Eastern calendar date of its EXIT. A Saturday or Sunday exit (the
     ENGU-Q leg trades the Sunday-evening session) counts on the Monday that follows - there is no
     report on a weekend, and a trade must never fall on a day with no report. That roll is the
     only departure from the calendar date, and it is written on the trade as `close_day`.
  2. A trade still OPEN when the run happens counts on NO day yet. The strategy files close a
     position that is still held when the data ends at the LAST BAR (exit index == n - 1, at that
     bar's close), so "open" is exactly: the exit is the last bar AND that bar is not the end of
     the leg's own session. An RTH leg whose last bar is the final bar of the cash session (15:55
     of 5m, 15:30 of 30m) has closed - its strategies flatten at the session end. An ETH leg never
     ends a session at the run time, so a last-bar exit is open. The one false positive is a trade
     that really does close ON the last bar (a stop hit on the final minute): it reads open for one
     night and is picked up by the re-merge below the next night. Nothing is lost, only late.
  3. NO LOSS, NO DOUBLE COUNT. Every night's run rebuilds the day figures from the FULL trade list,
     so a day's figure is a pure function of that list - never an accumulation. The day being
     reported is written by the normal path; the previous LOOKBACK_DAYS report docs are re-merged
     (merge=True, only the pnl fields) so a trade that closed after 16:10 on day D is in D's
     figure from the next nightly run on. See remerge_prior_days.

Pure functions only (no Firestore, no clock) except remerge_prior_days, which takes the db handle.
"""
import datetime as dt

import pandas as pd

LOOKBACK_DAYS = 7           # report days re-merged each night (calendar days before the target)
_TOL = 0.005                # dollars: a re-bucketed figure inside this of the stored one is "same"


# ── dates ────────────────────────────────────────────────────────────────────────────────
def et_date(ts):
    """The US/Eastern calendar date of a Timestamp. A tz-aware stamp is converted; a naive one is
    read as Eastern wall time (the engine's naive bar index is Eastern)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("US/Eastern")
    return t.date()


def roll_weekend(d):
    """A Saturday/Sunday date moves forward to the Monday after it; any other date is unchanged."""
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def close_day(ts):
    """The report day a trade that exited at `ts` counts on (see rule 1)."""
    return roll_weekend(et_date(ts))


# ── open detection ───────────────────────────────────────────────────────────────────────
def _tf_minutes(leg):
    digits = "".join(ch for ch in str((leg or {}).get("timeframe") or "") if ch.isdigit())
    return int(digits) if digits else 1


def session_complete(leg, last_ts):
    """True when the data's last bar is the final bar of the leg's own session - i.e. nothing
    more can arrive for that session, so a position closed on that bar is closed, not held.
    Only an RTH leg has such a bar (cash session ends 16:00 ET); an ETH leg does not."""
    if str((leg or {}).get("session", "rth")).lower() != "rth":
        return False
    t = pd.Timestamp(last_ts)
    if t.tzinfo is not None:
        t = t.tz_convert("US/Eastern")
    return t.hour * 60 + t.minute + _tf_minutes(leg) >= 16 * 60


def is_open(leg, index, exit_bar):
    """Is the trade whose exit is bar `exit_bar` of `index` still open at the end of the data?"""
    n = len(index)
    if n == 0 or int(exit_bar) < n - 1:
        return False
    return not session_complete(leg, index[int(exit_bar)])


# ── trade-level fields and per-day tables ────────────────────────────────────────────────
def trade_fields(t):
    """The three fields written on every trade doc: open, exit_date (calendar date of the exit
    in ET) and close_day (the report day it counts on, None while open)."""
    op = bool(t.get("open"))
    xd = et_date(t["exit_dt"])
    return {"open": op, "exit_date": xd.isoformat(),
            "close_day": None if op else roll_weekend(xd).isoformat()}


def bucket(trades):
    """Closed trades by close day. Returns (pnl_by_day, n_by_day, open_n, open_pnl): the first two
    are {iso day: value} over CLOSED trades only; the last two describe the open ones, whose money
    is an unrealised mark and belongs to no day."""
    pnl, cnt = {}, {}
    open_n, open_pnl = 0, 0.0
    for t in trades:
        p = float(t["pnl_usd"])
        if t.get("open"):
            open_n += 1
            open_pnl += p
            continue
        d = close_day(t["exit_dt"]).isoformat()
        pnl[d] = pnl.get(d, 0.0) + p
        cnt[d] = cnt.get(d, 0) + 1
    return pnl, cnt, open_n, open_pnl


# ── re-bucketing a stored report doc ─────────────────────────────────────────────────────
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def rebucket_payload(old, by_day_by_leg, day_iso):
    """The merge payload that moves a stored report doc to exit-day figures, or None if nothing
    changes. `old` is the stored doc; `by_day_by_leg` is {leg key: {iso day: pnl}} built from the
    full trade list; a leg absent from it keeps its stored figure (never zeroed on missing data).

    Only fields already in the doc are touched: legs the doc has, the blend, every block that
    carries its own `weights` (the book and the weighted-sum shadows - the doc's OWN weights, so a
    historical composition is respected), and the volatility-sized shadow (its stored multiplier
    times the new book figure). Nothing is created that the doc did not have."""
    legs_old = old.get("legs") or {}
    new = {}
    legs_payload = {}
    for k, blk in legs_old.items():
        if not isinstance(blk, dict):
            continue
        if k in by_day_by_leg:
            v = float(by_day_by_leg[k].get(day_iso, 0.0))
            new[k] = v
            if abs(v - _f(blk.get("pnl_usd"))) > _TOL:
                legs_payload[k] = {"pnl_usd": v}
        else:
            new[k] = _f(blk.get("pnl_usd"))
    payload = {}
    if legs_payload:
        payload["legs"] = legs_payload

    def _put(key, val):
        if abs(val - _f((old.get(key) or {}).get("pnl_usd"))) > _TOL:
            payload[key] = {"pnl_usd": val}

    if isinstance(old.get("blend"), dict) and "pnl_usd" in old["blend"]:
        _put("blend", sum(new[k] for k in ("ORB", "ENGUQ") if k in new))
    book_new = None
    for key, blk in old.items():
        if key == "legs" or not isinstance(blk, dict):
            continue
        w = blk.get("weights")
        if isinstance(w, dict) and "pnl_usd" in blk:
            val = sum(new[k] * _f(x) for k, x in w.items() if k in new)
            _put(key, val)
            if key == "book":
                book_new = val
    vt = old.get("book_shadow_vt")
    if book_new is not None and isinstance(vt, dict) and vt.get("multiplier") is not None:
        _put("book_shadow_vt", _f(vt["multiplier"]) * book_new)
    return payload or None


def remerge_prior_days(db, uid, target_date, by_day_by_leg, *, log=print, note_reads=None,
                       dry_run=False, lookback=LOOKBACK_DAYS):
    """Re-merge the previous `lookback` calendar days' report docs (those that exist) with figures
    rebuilt from the full trade list. Returns [(day iso, payload)] for the days that changed.
    Fail-soft per day: one unreadable doc never stops the others or the nightly report."""
    out = []
    col = db.collection("users").document(uid).collection("paper_reports")
    for back in range(1, int(lookback) + 1):
        d = target_date - dt.timedelta(days=back)
        if d.weekday() >= 5:
            continue                      # no report is ever written for a weekend
        day_iso = d.isoformat()
        try:
            snap = col.document(day_iso).get()
            if note_reads:
                note_reads(1)
            if not snap.exists:
                continue
            payload = rebucket_payload(snap.to_dict() or {}, by_day_by_leg, day_iso)
            if not payload:
                continue
            out.append((day_iso, payload))
            if not dry_run:
                col.document(day_iso).set(payload, merge=True)
        except Exception as e:
            log(f"uid={uid} exit-day re-merge of {day_iso} skipped: {type(e).__name__}: {e}")
    return out
