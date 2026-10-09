# -*- coding: utf-8 -*-
"""HARM MONITOR - the weekly forward read of #463's legs (FRONTIER; BOOK.md 10aq, MANAGER #139 / #140). READ-ONLY: it never changes a leg,
never pushes to a phone, reads no Firestore; its only output is one inbox post to MANAGER (or a print) and a copy of it on disk.

Each leg's forward daily $ is the ENGINE SHADOW: #463's own leg definitions (api/book_shadow.BOOK463_LEGS) re-run through augur_engine.book on
#463's pinned masters - the code path the walk-forward bands were built on (marked to market, book UTC day stamps, #463's sizes). The runner's
paper layer-0 shadow is not used: it runs ORB / TTM on the no-adjust master, not #463's (tools/guard_r1.py), and lives in Firestore.
The forward record starts 2026-07-01 (the first day after the backtests' last bar), except ENGU-Q and the #463 total: the NQ 1m ETH master has
no bars 2026-07-01..08-05 (free sources keep 7 days of 1m; unrecoverable), ENGU-Q's 06-29 trade is carried across that hole and books its
whole loss on 08-06, so they read from 08-07, the first day ENGU-Q starts flat after it.
Rows = the book's calendar: every regular session (dates in at least two of the three RTH masters) plus any day a leg has $ (ENGU-Q's Sunday
evenings), zero where a leg is flat - as the walk-forward rows were. The record ends at the last session before the run day that every RTH
master holds. A gap of 2+ sessions in a leg's master after its start PAUSES that leg (and the #463 total) instead of reading it.
Two alarms per leg, frozen from the walk-forward (bookq/q33_harm_spec.py, 2,000 three-year block-bootstrap paths):
  A1 SHORTFALL  S = sum over forward rows of (day $ - WF daily mean); tripped when S < -c x WF daily sd x sqrt(rows) at a weekly check (every
                6th row from the start, as calibrated); a trip stays a trip
  A2 DRAWDOWN   the forward running drawdown deeper than the 2.5% depth of a three-year path of the backtested leg
A trip is "worse than the backtested leg does 2.5% of the time" - harm shown, not decay proven. ORB / TTM also carry a big-day WATCH line
(days above their WF 99th percentile, ~3 a year expected) - shown, never an alarm. Order: ORB, TTM, NOISE, ENGU-Q, #463.

    python tools/harm_monitor.py               # compute and print the Monday post
    python tools/harm_monitor.py --post        # ... and post it to MANAGER's inbox (tools/chat_inbox.py)
    python tools/harm_monitor.py --asof 2026-10-12
"""
import argparse
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORWARD_START = pd.Timestamp("2026-07-01")
LEG_START = {"ENGU-Q": pd.Timestamp("2026-08-07"), "#463": pd.Timestamp("2026-08-07")}   # the NQ 1m hole (above)
WEEK_ROWS = 6                     # book rows a week on the walk-forward (24.3 a month); A1 is checked every 6 forward rows
SPEC = "BOOK.md 10aq"
ORDER = ("ORB", "TTM x3", "NOISE", "ENGU-Q", "#463")
RTH_LEGS = ("ORB", "TTM x3", "NOISE")
# frozen from bookq/q33_harm_spec.py on the S1 WF (2016-07-01..2025-06-29): WF daily mean / sd per book row, the A1 constant c, the A2
# drawdown alarm, and (ORB / TTM) the big-day threshold = the leg's WF 99th percentile day
BANDS = {
    "ORB": {"mu": 114.6947, "sd": 1711.9917, "c": 2.5276, "dd_alarm": 48721.06, "big": 5898.09, "big_per_year": 3.002},
    "TTM x3": {"mu": 50.3762, "sd": 1176.3535, "c": 2.2034, "dd_alarm": 35583.03, "big": 3032.49, "big_per_year": 3.002},
    "NOISE": {"mu": 170.4663, "sd": 1457.5755, "c": 2.441, "dd_alarm": 23067.81, "big": None, "big_per_year": None},
    "ENGU-Q": {"mu": 144.7574, "sd": 2273.4109, "c": 2.3988, "dd_alarm": 63754.45, "big": None, "big_per_year": None},
    "#463": {"mu": 480.2945, "sd": 4138.5655, "c": 2.234, "dd_alarm": 62640.21, "big": None, "big_per_year": None},
}
LEG_NAME = {"ORB": "ORB", "ENGUQ": "ENGU-Q", "TTMSQZ": "TTM x3", "NOISE": "NOISE"}
fmt = "{:,.0f}".format


# ------------------------------------------------------------------ the read (pure)
def evaluate(x, band, days_per_year=292.0):
    """x = the forward daily $ (book rows, in order), band = one BANDS entry -> the leg's read"""
    x = np.asarray(x, float)
    n = len(x)
    out = {"days": n, "net": float(x.sum())}
    if n == 0:
        out.update({"a1": False, "a2": False, "a1_z": None, "dd": 0.0, "a1_text": "no forward days yet", "a2_text": "no forward days yet"})
        return out
    s = np.cumsum(x - band["mu"])
    chk = np.arange(WEEK_ROWS, n + 1, WEEK_ROWS)        # the alarm looks only at every 6th row from the start, as calibrated (q33 `checks`)
    z = s[chk - 1] / (band["sd"] * np.sqrt(chk))
    q = np.cumsum(x)
    dd = np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q
    a1 = bool((z < -band["c"]).any())
    a2 = bool((dd > band["dd_alarm"]).any())
    line_now = -band["c"] * band["sd"] * math.sqrt(n)
    out.update({"a1": a1, "a2": a2, "a1_z": float(s[-1] / (band["sd"] * math.sqrt(n))), "a1_worst_z": float(z.min()) if len(z) else None,
                "a1_checks": int(len(z)), "a1_first_trip_row": int(chk[np.argmax(z < -band["c"])]) if a1 else None,
                "shortfall": float(s[-1]), "a1_line": line_now,
                "dd": float(dd[-1]), "dd_max": float(dd.max()), "expected_net": float(band["mu"] * n)})
    if a1:
        out["a1_text"] = ("TRIPPED (check of row %d: %.2f vs line -%.2f; worst %.2f; it stays tripped) - now %s the backtest's pace by $%s"
                          % (out["a1_first_trip_row"], z[np.argmax(z < -band["c"])], band["c"], z.min(),
                             "behind" if s[-1] < 0 else "ahead of", fmt(abs(s[-1]))))
    elif s[-1] < 0:
        out["a1_text"] = ("behind the backtest's pace by $%s; the alarm sits at $%s behind (%.0f%% of the way there)"
                          % (fmt(-s[-1]), fmt(-line_now), 100.0 * s[-1] / line_now))
    else:
        out["a1_text"] = "ahead of the backtest's pace by $%s (the alarm sits at $%s under pace)" % (fmt(s[-1]), fmt(-line_now))
    out["a2_text"] = ("TRIPPED (drawdown $%s vs alarm $%s)" % (fmt(dd.max()), fmt(band["dd_alarm"])) if a2 else
                      "drawdown now $%s, deepest $%s; the alarm is at $%s" % (fmt(dd[-1]), fmt(dd.max()), fmt(band["dd_alarm"])))
    if band.get("big"):
        k = int((x > band["big"]).sum())
        exp = band["big_per_year"] * n / days_per_year
        out.update({"big_days": k, "big_expected": exp})
        out["watch_text"] = "big days (> $%s): %d so far, about %.1f expected - a watch line only" % (fmt(band["big"]), k, exp)
    return out


def find_holes(have, ref):
    """have / ref = sets of session dates -> (runs of 2+ consecutive ref sessions missing from `have`, single missing sessions). A lone
    missing date can be a CME holiday short session one master keeps; a run of two or more is a data hole."""
    ref = sorted(ref)
    runs, cur = [], []
    for d in ref:
        if d in have:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(d)
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) >= 2], [r[0] for r in runs if len(r) == 1]


def format_post(reads, asof, meta=None):
    """the Monday post: trips first, then paused legs and data notes, then each leg's distance to A1 / A2 in plain words"""
    meta = meta or {}
    trips = [(nm, r) for nm, r in reads.items() if r.get("a1") or r.get("a2")]
    head = "FRONTIER HARM MONITOR %s (%s; engine shadow" % (asof, SPEC)
    if meta.get("end") is not None:
        head += ", data through %s" % pd.Timestamp(meta["end"]).date()
    lines = [head + "; read-only - nothing changes without the owner):"]
    if trips:
        for nm, r in trips:
            which = " and ".join(a for a, f in (("A1 shortfall", r.get("a1")), ("A2 drawdown", r.get("a2"))) if f)
            lines.append("- TRIP: %s - %s. A1 %s. A2 %s. Forward net $%s over %d days from %s (the backtest's pace: $%s)."
                         % (nm, which, r["a1_text"], r["a2_text"], fmt(r["net"]), r["days"], r.get("start", "?"), fmt(r.get("expected_net", 0.0))))
    else:
        lines.append("- No alarm tripped.")
    for nm in ORDER:
        r = reads.get(nm)
        if r is not None and r.get("paused"):
            lines.append("- PAUSED: %s - %s. Not read this week." % (nm, r["why"]))
    for note in meta.get("notes", []):
        lines.append("- Data note: " + note)
    for nm in ORDER:
        r = reads.get(nm)
        if r is None or r.get("paused") or r.get("a1") or r.get("a2"):
            continue
        txt = "- %s (%d days from %s, net $%s): A1 %s. A2 %s." % (nm, r["days"], r.get("start", "?"), fmt(r["net"]), r["a1_text"], r["a2_text"])
        if r.get("watch_text"):
            txt += " " + r["watch_text"].capitalize() + "."
        lines.append(txt)
    lines.append("- Power reminder (10aq): a leg that starts losing is caught within about a year; a halved edge is invisible within 36 months; "
                 "a quiet 36 months for ORB / TTM / ENGU-Q means 'not shown', never 'fine'.")
    return "\n".join(lines)


def read_all(fw, meta):
    """{leg: forward Series} + meta (starts, paused) -> {leg: read}"""
    reads = {}
    for nm in ORDER:
        if nm in meta.get("paused", {}):
            reads[nm] = {"paused": True, "why": meta["paused"][nm]}
            continue
        r = evaluate(fw[nm].to_numpy(float), BANDS[nm])
        r["start"] = str(pd.Timestamp(meta.get("starts", {}).get(nm, FORWARD_START)).date())
        reads[nm] = r
    return reads


# ------------------------------------------------------------------ the data
def forward_daily(asof):
    """#463's legs re-run through augur_engine.book on their pinned masters (read-only: masters are read, nothing is written)
    -> ({leg: daily $ Series on the book calendar, each from its start}, meta)"""
    sys.path.insert(0, ROOT)
    from api.book_shadow import BOOK463_LEGS
    from augur_engine import book
    from augur_engine.data import find_master, load_master_arrays
    run_day = pd.Timestamp(asof).normalize()
    raw, have = {}, {}
    for leg in BOOK463_LEGS:
        nm = LEG_NAME[leg["strategy"].split("_")[0]]
        m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg.get("source"))
        arr = load_master_arrays(m, date_from=str(FORWARD_START.date()), date_to=str(run_day.date()))
        have[nm] = set(pd.DatetimeIndex(arr["index"].tz_localize(None).normalize()))
        tr, inf = book._leg_trades(dict(leg), "2010-06-07", str(run_day.date()))
        d_, v_ = book._daily(inf.pop("_mtm_day", None) or tr)
        s = pd.Series(v_, index=pd.to_datetime(d_)).groupby(level=0).sum()
        raw[nm] = raw.get(nm, 0.0) + s[(s.index >= FORWARD_START) & (s.index < run_day)]
    votes = pd.Series([d for nm in RTH_LEGS for d in have[nm]]).value_counts()
    ref = {d for d, k in votes.items() if k >= 2 and d.dayofweek < 5 and d < run_day}
    end = min(max(d for d in have[nm] if d < run_day) for nm in RTH_LEGS)
    ref = {d for d in ref if d <= end}
    starts = {nm: LEG_START.get(nm, FORWARD_START) for nm in ORDER}
    paused, notes = {}, []
    for nm in LEG_NAME.values():
        runs, singles = find_holes(have[nm], {d for d in ref if d >= starts[nm]})
        if runs:
            paused[nm] = "its master has no bars on %s" % "; ".join("%s..%s (%d sessions)" % (r[0].date(), r[-1].date(), len(r)) for r in runs)
        if singles:
            notes.append("%s's master lacks %s (single sessions - a holiday short session or a gap; look before trusting that day)"
                         % (nm, ", ".join(str(d.date()) for d in singles)))
    if paused:
        paused["#463"] = "a leg is paused (%s)" % ", ".join(sorted(paused))
    lag = int(np.busday_count((end + pd.Timedelta(days=1)).date(), run_day.date()))
    if lag > 0:
        notes.append("data ends %s, %d weekday(s) before the run day (a holiday, or a master not updated)" % (end.date(), lag))
    valued = set().union(*[set(s.index[s != 0]) for s in raw.values()])
    cal = pd.DatetimeIndex(sorted(d for d in (ref | valued) if FORWARD_START <= d <= end))
    out = {nm: s.reindex(cal).fillna(0.0) for nm, s in raw.items()}
    out["#463"] = sum(out.values())
    out = {nm: s[s.index >= starts[nm]] for nm, s in out.items()}
    return out, {"end": end, "starts": starts, "paused": paused, "notes": notes, "sessions": len(ref)}


def _post(txt):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import chat_inbox
    if chat_inbox.norm("MANAGER") not in chat_inbox.known():       # post() itself does not check the name (the CLI does)
        raise SystemExit("refused: no MANAGER inbox file")
    return chat_inbox.post("MANAGER", txt, "FRONTIER")              # post(chat, text, frm) -> the item id


def main(argv=None):
    ap = argparse.ArgumentParser(description="FRONTIER weekly harm monitor (read-only)")
    ap.add_argument("--asof", default=str(pd.Timestamp.now().date()), help="the run day; the record ends at the last session before it")
    ap.add_argument("--post", action="store_true", help="post the read to MANAGER's inbox")
    a = ap.parse_args(argv)
    try:
        fw, meta = forward_daily(a.asof)
        reads = read_all(fw, meta)
        txt = format_post(reads, a.asof, meta)
    except Exception as e:                                          # a silent failure is the worst outcome for a monitor: say so
        if a.post:
            _post("FRONTIER HARM MONITOR %s FAILED (%s: %s) - no read this week; FRONTIER to look." % (a.asof, type(e).__name__, e))
        raise
    print(txt)
    out_dir = os.environ.get("EDGELOG_HARM_DIR", r"C:\EdgeLog\harm_monitor")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "read_%s.txt" % a.asof), "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    except OSError:
        pass
    if a.post:
        print("posted to MANAGER as #%d" % _post(txt))
    return reads


if __name__ == "__main__":
    main(sys.argv[1:])
