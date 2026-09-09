"""WHOSE DRAWDOWN IS THE BOOK'S DRAWDOWN? - the risk-clause diagnostic for BOOK adoptions.

WHY THIS FILE EXISTS (2026-09-09). Every book bar written in this repo so far carries a risk
clause of the shape "whole-run drawdown within X percent of the adopted book". The TTM round-10
sizing sweep discovered that clause cannot bind: the house baseline book (ORB #234 + ENGU-Q #309,
one NQ contract each) takes its whole-run maximum drawdown in ONE stretch, and a candidate leg
that took no trades in that stretch leaves the number bit for bit unchanged no matter how large
it is. The clause measures one month of tape, not the risk of the thing being added. The
diagnostic that proves it lived in the last twenty lines of tools/ttmsqz_round10_weights.py;
this module is that diagnostic, reusable, plus the replacement clause it argues for.

WHICH MONTH that stretch is depends on how a trade is stamped to a day, and the two conventions
in this repo disagree - see `day_mode` on leg_daily below and section 0 of the audit driver. The
FINDING does not depend on it: under either convention the TTM leg traded there zero times.

WHAT IT COMPUTES
  worst_stretch(daily)     the book's peak-to-trough stretch, EXACTLY decomposed: the per-day
                           dollars strictly AFTER the peak day through the trough day sum to the
                           drawdown to the cent, so per-leg contributions are a true decomposition
                           and not an approximation. (The TTM driver used `>= peak_day`, which
                           double-counts the peak day's own P&L; the difference is one day.)
  attribute(parts, ws)     per leg: dollars inside that stretch, and how many days it traded there.
                           A leg with zero trading days inside the stretch is INERT under any
                           whole-run drawdown clause - that is the finding, stated per leg.
  score(daily, lb_from)    net / drawdown / annualised MAR, and the same three on the lockbox.
  clause_check(...)        the OLD clause (whole-run drawdown) and the REPLACEMENT clause
                           (lockbox drawdown + the candidate actually traded in the worst stretch)
                           evaluated side by side on the same pair of books.

THE REPLACEMENT CLAUSE (what a book bar should say from now on)
  A candidate book is adopted over the incumbent when
    1. annualised MAR >= incumbent x (1 + mar_gain)                    [unchanged]
    2. LOCKBOX drawdown within dd_tol of the incumbent's               [was: whole-run drawdown]
    3. lockbox net >= the incumbent's                                  [unchanged]
  and the whole-run drawdown comparison is reported as a CHECK, not a gate, carrying the verdict
  of clause 2's participation test: whether the leg being added traded at all inside the book's
  worst stretch. When it did not, the whole-run number is stated as inert rather than as evidence.
  Rationale: the lockbox drawdown is measured on the one stretch of tape the legs' parameters
  never saw, it moves monotonically with leg weight (TTM: $26,235 -> $29,128 from 3 to 6
  contracts, while the whole-run number never moved at all), and it cannot be satisfied by an
  accident of which month happens to hold the all-time trough.

USE IT AS A LIBRARY (the audit driver tools/book_clause_audit.py does exactly this):
    from tools.book_dd_attribution import book_parts, worst_stretch, attribute, score, clause_check
    parts = book_parts(legs, "2010-06-07", "2026-06-30")     # {label: daily $ Series}
    ws    = worst_stretch(sum_parts(parts))
    rows  = attribute(parts, ws)

OR FROM THE COMMAND LINE (legs read straight from a stored BOOK run's own job doc, so the
numbers are the run's, not a re-specification of it):
    python tools/book_dd_attribution.py --run 336                 # attribution of one book
    python tools/book_dd_attribution.py --run 341 --vs 336        # candidate vs incumbent, both clauses
    python tools/book_dd_attribution.py --run 342 --vs 336 --new-legs 3
        # ... --new-legs N marks the LAST N legs as the candidate addition, so the participation
        #     test is asked of the leg being added rather than of the whole book.

Read-only against Firestore. Needs serviceAccount.json in the repo root only for --run.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

# The canonical wording of a book bar, so the next queue driver states the clause instead of
# re-inventing it. Print it into the job note / docstring with bar_text().
RISK_CLAUSE = (
    "BAR (pre-registered) against %(inc)s: (1) annualised MAR at least %(mar).2fx it; "
    "(2) LOCKBOX drawdown within %(dd)d percent of it; (3) lockbox net at least as large. "
    "The WHOLE-RUN drawdown is reported as a check, not a gate: it is set by one stretch of "
    "tape, so a leg that took no trades in that stretch cannot move it at any weight and the "
    "comparison says nothing about the risk being added. tools/book_dd_attribution.py prints "
    "who paid for the stretch and names any leg that was absent.")


def bar_text(incumbent="the adopted book", mar_gain=0.05, dd_tol=0.05):
    return RISK_CLAUSE % dict(inc=incumbent, mar=1 + mar_gain, dd=int(round(dd_tol * 100)))


# ─────────────────────────────────────────────────────────────────────────────
# building daily series
# ─────────────────────────────────────────────────────────────────────────────
def leg_daily(leg, date_from=None, date_to=None, day_mode="book"):
    """One book leg -> a Series of dollars per calendar day, indexed by EXIT date.

    day_mode="book"    the day-stamp a BOOK job uses: numpy truncates the master's US/Eastern
                       index to datetime64[D], which numpy does in UTC - so an ETH trade exiting
                       at or after 20:00 ET (19:00 in winter) is booked on the NEXT day. Every
                       stored book run's drawdown is on this convention, so it is the default.
    day_mode="session" the ET calendar day the account would write on the ticket.

    NET IS IDENTICAL EITHER WAY; the DAILY CURVE, and therefore the DRAWDOWN, is not. On the
    house baseline the two conventions disagree about which month is the worst stretch at all
    (May 2022 / $34,329 under "book", Feb-Mar 2020 / $34,903 under "session") - see section 0
    of tools/book_clause_audit.py. Day-session legs are unaffected; only 24h legs move.

    Runs through augur_engine.book._leg_trades, the SAME code path a BOOK job uses, so the
    per-leg dollars here are the run's own numbers and not a second implementation of them.
    """
    from augur_engine.book import _leg_trades
    trades, info = _leg_trades(leg, date_from, date_to)
    if not trades:
        return pd.Series(dtype=float), info
    if day_mode == "session":
        # re-stamp from the master's own tz-aware index instead of the pooled UTC-truncated day
        from augur_engine.data import find_master, load_master_arrays
        arr = load_master_arrays(find_master(info.get("instrument"), info.get("timeframe"),
                                             info.get("session"), info.get("source")),
                                 date_from=date_from, date_to=date_to)
        idx = pd.DatetimeIndex(arr["index"])
        idx = idx.tz_localize(None).normalize() if idx.tz is not None else idx.normalize()
        from augur_engine.engine import run_backtest
        res = run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {},
                           cost_pts=float(leg.get("cost_pts", 0) or 0), return_trades=True) or {}
        mult = float(info.get("mult") or 1) * float(info.get("weight") or 1)
        tr = [(idx[min(int(t[1]), len(idx) - 1)], float(t[2]) * mult) for t in (res.get("trades") or [])]
        s = pd.Series([p for _, p in tr], index=[d for d, _ in tr]).groupby(level=0).sum()
        return s.sort_index(), info
    s = pd.Series([p for _, p in trades],
                  index=pd.to_datetime([d for d, _ in trades])).groupby(level=0).sum()
    return s.sort_index(), info


def book_parts(legs, date_from=None, date_to=None, labels=None, verbose=True):
    """[leg, ...] -> {label: daily $ Series}. Labels default to strategy + instrument + weight."""
    parts, order = {}, []
    for i, leg in enumerate(legs):
        s, info = leg_daily(leg, date_from, date_to)
        lab = (labels or {}).get(i) if isinstance(labels, dict) else (
            labels[i] if labels else None)
        if not lab:
            w = float(leg.get("weight", 1) or 1)
            lab = "%s %s %s%s" % (str(leg.get("strategy", "?")).replace(".py", ""),
                                  leg.get("instrument"), leg.get("timeframe"),
                                  (" x%g" % w) if w != 1 else "")
        while lab in parts:            # two identical legs on the same tape (QQQ RSI2 long/both)
            lab += "'"
        parts[lab] = s
        order.append(lab)
        if verbose:
            print("  leg %-46s %5d days  $%12s" % (lab[:46], len(s),
                                                   "{:,.0f}".format(float(s.sum()))), flush=True)
    return {k: parts[k] for k in order}


def series_from_rows(rows, date_key="date", pnl_key="pnl", group_key=None):
    """[(dict|tuple)] -> one Series, or {group: Series} when group_key is given.

    For offline books whose daily P&L is already saved as a CSV (the NASDAQ walk-forward book's
    OOS series, the champion legs' daily file) rather than re-runnable as engine legs.
    """
    df = pd.DataFrame(list(rows))
    df[date_key] = pd.to_datetime(df[date_key])
    df[pnl_key] = df[pnl_key].astype(float)
    if group_key is None:
        return df.groupby(date_key)[pnl_key].sum().sort_index()
    return {str(g): d.groupby(date_key)[pnl_key].sum().sort_index()
            for g, d in df.groupby(group_key)}


def sum_parts(parts):
    """{label: Series} -> the book's daily $ Series (a day either leg traded is a day)."""
    parts = {k: v for k, v in parts.items() if len(v)}
    if not parts:
        return pd.Series(dtype=float)
    out = None
    for s in parts.values():
        out = s if out is None else out.add(s, fill_value=0.0)
    return out.sort_index()


# ─────────────────────────────────────────────────────────────────────────────
# the diagnostic
# ─────────────────────────────────────────────────────────────────────────────
def worst_stretch(daily, from_date=None):
    """The peak-to-trough stretch of a daily $ series.

    Returns {peak_day, start, trough, depth, days, span_days} where `start` is the FIRST day
    that belongs to the drawdown (the day after the peak) - so summing the series over
    start..trough gives -depth exactly, and per-leg sums over the same span decompose it.
    """
    d = daily if from_date is None else daily[daily.index >= pd.Timestamp(from_date)]
    d = d.sort_index()
    if not len(d):
        return None
    cum = d.cumsum()
    ddown = cum - cum.cummax()
    trough = ddown.idxmin()
    depth = -float(ddown.loc[trough])
    pre = cum.loc[:trough]
    peak_day = pre.idxmax()
    after = d.loc[d.index > peak_day]
    after = after.loc[after.index <= trough]
    return dict(peak_day=peak_day, start=(after.index[0] if len(after) else trough),
                trough=trough, depth=depth, days=int(len(after)),
                span_days=int((trough - peak_day).days))


def attribute(parts, ws):
    """Per-leg decomposition of a worst stretch. Rows sum to -depth (to the cent)."""
    if not ws:
        return []
    lo, hi = ws["peak_day"], ws["trough"]
    rows = []
    for lab, s in parts.items():
        w = s[(s.index > lo) & (s.index <= hi)]
        rows.append(dict(leg=lab, usd=float(w.sum()), days=int((w != 0).sum()),
                         share=(float(w.sum()) / -ws["depth"] if ws["depth"] else float("nan"))))
    return rows


def score(daily, lb_from=None):
    """net / drawdown / annualised MAR over the whole series, and the same on the lockbox."""
    d = daily.sort_index()
    if not len(d):
        return None
    cum = d.cumsum().values
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    yrs = max((d.index[-1] - d.index[0]).days / 365.25, 1e-9)
    net = float(d.sum())
    out = dict(net=net, dd=dd, years=yrs, mar=((net / yrs) / dd if dd > 0 else float("nan")),
               ypos=int((d.groupby(d.index.year).sum() > 0).sum()), ny=int(d.index.year.nunique()))
    lb = d[d.index >= pd.Timestamp(lb_from)] if lb_from else d.iloc[0:0]
    if len(lb):
        lcum = lb.cumsum().values
        ldd = -float((lcum - np.maximum.accumulate(lcum)).min())
        lyrs = max((lb.index[-1] - lb.index[0]).days / 365.25, 1e-9)
        out.update(lb=float(lb.sum()), lbdd=ldd, lbyears=lyrs,
                   lbmar=((float(lb.sum()) / lyrs) / ldd if ldd > 0 else float("nan")))
    else:
        out.update(lb=float("nan"), lbdd=float("nan"), lbyears=float("nan"), lbmar=float("nan"))
    return out


def clause_check(base_daily, cand_daily, cand_parts=None, new_legs=None, lb_from=None,
                 mar_gain=0.05, dd_tol=0.05):
    """The OLD and the REPLACEMENT risk clause, evaluated on the same pair of books.

    base_daily / cand_daily : incumbent and candidate book daily $ Series.
    cand_parts              : {label: Series} for the candidate, used for the participation test.
    new_legs                : labels (or an int = the last N labels) that are the ADDITION. The
                              participation test is asked of these; with None it is asked of every
                              leg and reported per leg.
    """
    sb, sc = score(base_daily, lb_from), score(cand_daily, lb_from)
    wsb = worst_stretch(base_daily)
    wslb = worst_stretch(base_daily, from_date=lb_from) if lb_from else None
    labels = None
    if cand_parts:
        labels = list(cand_parts.keys())
        if isinstance(new_legs, int):
            labels = labels[-new_legs:] if new_legs > 0 else labels
        elif new_legs:
            labels = [x for x in new_legs if x in cand_parts]
    part = []
    if cand_parts and wsb:
        for r in attribute({k: cand_parts[k] for k in labels}, wsb):
            part.append(r)
    inert = bool(part) and all(r["days"] == 0 for r in part)

    old_dd_ok = sc["dd"] <= sb["dd"] * (1 + dd_tol)
    new_dd_ok = bool(sc["lbdd"] == sc["lbdd"] and sb["lbdd"] == sb["lbdd"]
                     and sc["lbdd"] <= sb["lbdd"] * (1 + dd_tol))
    mar_ok = sc["mar"] >= sb["mar"] * (1 + mar_gain)
    lb_ok = bool(sc["lb"] == sc["lb"] and sb["lb"] == sb["lb"] and sc["lb"] >= sb["lb"])
    return dict(base=sb, cand=sc, ws_whole=wsb, ws_lockbox=wslb, participation=part,
                inert=inert, mar_ok=mar_ok, lb_ok=lb_ok,
                old_dd_ok=old_dd_ok, new_dd_ok=new_dd_ok,
                old_pass=bool(mar_ok and lb_ok and old_dd_ok),
                new_pass=bool(mar_ok and lb_ok and new_dd_ok),
                dd_ratio=(sc["dd"] / sb["dd"] if sb["dd"] else float("nan")),
                lbdd_ratio=(sc["lbdd"] / sb["lbdd"] if sb["lbdd"] else float("nan")),
                mar_ratio=(sc["mar"] / sb["mar"] if sb["mar"] else float("nan")))


# ─────────────────────────────────────────────────────────────────────────────
# printing
# ─────────────────────────────────────────────────────────────────────────────
def _m(x):
    try:
        return "{:,.0f}".format(float(x))
    except Exception:
        return str(x)


def format_stretch(parts, ws, title="", indent="  "):
    """The diagnostic as text: the stretch, then who paid for it, then the inert legs."""
    L = []
    if not ws:
        return ["%sno trades - no stretch to attribute" % indent]
    L.append("%s%sworst stretch %s .. %s (peak %s), $%s over %d trading days"
             % (indent, (title + ": ") if title else "", ws["start"].date(), ws["trough"].date(),
                ws["peak_day"].date(), _m(ws["depth"]), ws["days"]))
    rows = sorted(attribute(parts, ws), key=lambda r: r["usd"])
    for r in rows:
        tag = "  <- NEVER TRADED in the stretch: inert under a whole-run drawdown clause" if r["days"] == 0 else ""
        L.append("%s  %-44s %+11s  %3d days  %6.1f%% of it%s"
                 % (indent, r["leg"][:44], _m(r["usd"]), r["days"], 100.0 * r["share"], tag))
    L.append("%s  %-44s %+11s   (decomposition check: must equal the stretch)"
             % (indent, "TOTAL", _m(sum(r["usd"] for r in rows))))
    return L


def format_clause(res, base_name="incumbent", cand_name="candidate", mar_gain=0.05, dd_tol=0.05):
    sb, sc = res["base"], res["cand"]
    L = ["  %-22s %12s %11s %8s %11s %11s" % ("book", "net $", "whole DD", "ann.MAR", "lockbox $", "LB DD"),
         "  %-22s %12s %11s %8.3f %11s %11s" % (base_name[:22], _m(sb["net"]), _m(sb["dd"]), sb["mar"], _m(sb["lb"]), _m(sb["lbdd"])),
         "  %-22s %12s %11s %8.3f %11s %11s" % (cand_name[:22], _m(sc["net"]), _m(sc["dd"]), sc["mar"], _m(sc["lb"]), _m(sc["lbdd"])),
         "  ratios                        %10.3fx %7.3fx %10.3fx %10.3fx"
         % (res["dd_ratio"], res["mar_ratio"],
            (sc["lb"] / sb["lb"] if sb["lb"] else float("nan")), res["lbdd_ratio"])]
    if res["participation"]:
        L.append("  participation of the ADDED leg(s) in the incumbent's worst stretch:")
        for r in res["participation"]:
            L.append("    %-42s %+11s over %3d trading days%s"
                     % (r["leg"][:42], _m(r["usd"]), r["days"],
                        "   <- ZERO: the whole-run drawdown clause is INERT here" if r["days"] == 0 else ""))
    L.append("  OLD clause  (MAR x%.2f, WHOLE-RUN DD within %d%%, lockbox >=): %s   [MAR %s, DD %s, LB %s]"
             % (1 + mar_gain, int(dd_tol * 100), "PASS" if res["old_pass"] else "MISS",
                "ok" if res["mar_ok"] else "no", "ok" if res["old_dd_ok"] else "no",
                "ok" if res["lb_ok"] else "no"))
    L.append("  NEW clause  (MAR x%.2f, LOCKBOX  DD within %d%%, lockbox >=): %s   [MAR %s, DD %s, LB %s]"
             % (1 + mar_gain, int(dd_tol * 100), "PASS" if res["new_pass"] else "MISS",
                "ok" if res["mar_ok"] else "no", "ok" if res["new_dd_ok"] else "no",
                "ok" if res["lb_ok"] else "no"))
    if res["inert"]:
        L.append("  VERDICT: this adoption's drawdown clause could not have failed - the leg it was "
                 "asked about took NO trades in the book's worst stretch.")
    return L


# ─────────────────────────────────────────────────────────────────────────────
# Firestore (read-only, only for --run)
# ─────────────────────────────────────────────────────────────────────────────
# The backtests collection has no run_id index, so a lookup is a full scan. On the Spark plan
# that is a real cost (memory: 50k reads/day), and this module is used from drivers that ask for
# five or six runs in a row. Scan ONCE per process and keep the map.
_JOBS = {}


def all_jobs(uid=DEFAULT_UID, cred=None):
    """Every stored job doc keyed by run number, scanned once per process and cached.

    Callers that want to FILTER runs (by note, type, strategy) need the whole map rather than one
    lookup at a time; without this they end up calling run_job with a bogus id just to warm the
    cache, which is exactly the sort of thing that reads as a bug six months later.
    """
    _ensure_jobs(uid, cred)
    return _JOBS[uid]


def _ensure_jobs(uid, cred=None):
    if uid not in _JOBS:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(
                cred or os.path.join(ROOT, "serviceAccount.json")))
        u = firestore.client().collection("users").document(uid)
        m = {}
        for d in u.collection("backtests").stream():
            j = d.to_dict() or {}
            try:
                j["_id"] = d.id
                m[int(j.get("run_id"))] = j
            except Exception:
                continue
        _JOBS[uid] = m


def run_job(run_id, uid=DEFAULT_UID, cred=None):
    """The stored job doc for a run number: its legs, window and recorded book result."""
    _ensure_jobs(uid, cred)
    try:
        return _JOBS[uid][int(run_id)]
    except KeyError:
        raise SystemExit("run #%s not found" % run_id)


def _lb_from(job):
    b = ((job.get("result") or {}).get("book") or {})
    if b.get("lockbox_from"):
        return str(b["lockbox_from"])[:10]
    months = int(job.get("lockbox_months") or 12)
    return str((pd.Timestamp(job.get("date_to")) - pd.Timedelta(days=int(round(months * 30.44)))).date())


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", type=int, required=True, help="BOOK run number to attribute")
    ap.add_argument("--vs", type=int, help="incumbent BOOK run number to judge --run against")
    ap.add_argument("--new-legs", type=int, default=0,
                    help="how many of --run's trailing legs are the ADDITION (participation test)")
    ap.add_argument("--mar-gain", type=float, default=0.05)
    ap.add_argument("--dd-tol", type=float, default=0.05)
    ap.add_argument("--uid", default=DEFAULT_UID)
    a = ap.parse_args()

    job = run_job(a.run, a.uid)
    df, dt, lb = job.get("date_from"), job.get("date_to"), _lb_from(job)
    print("run #%s  %s" % (a.run, str(job.get("strategy"))[:90]))
    print("window %s .. %s, lockbox from %s" % (df, dt, lb))
    parts = book_parts(job.get("legs") or [], df, dt)
    daily = sum_parts(parts)
    print("\n".join(format_stretch(parts, worst_stretch(daily), "whole run")))
    print("\n".join(format_stretch(parts, worst_stretch(daily, from_date=lb), "lockbox")))
    s = score(daily, lb)
    print("  net $%s  DD $%s  ann.MAR %.3f  lockbox $%s  LB DD $%s  %d/%d years"
          % (_m(s["net"]), _m(s["dd"]), s["mar"], _m(s["lb"]), _m(s["lbdd"]), s["ypos"], s["ny"]))

    if a.vs:
        bj = run_job(a.vs, a.uid)
        print("\nvs run #%s  %s" % (a.vs, str(bj.get("strategy"))[:80]))
        bparts = book_parts(bj.get("legs") or [], bj.get("date_from"), bj.get("date_to"))
        bdaily = sum_parts(bparts)
        res = clause_check(bdaily, daily, parts, a.new_legs or None, lb,
                           mar_gain=a.mar_gain, dd_tol=a.dd_tol)
        print("\n".join(format_clause(res, "#%s" % a.vs, "#%s" % a.run, a.mar_gain, a.dd_tol)))


if __name__ == "__main__":
    main()
