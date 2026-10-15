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
Two alarms per leg, calibrated as bookq/q33_harm_spec.py does (2,000 three-year block-bootstrap paths) but on the LAST THREE walk-forward
years only, 2022-07-01..2025-06-29 (BOOK.md 10at, MANAGER #141): the legs trade fixed contracts, so their daily $ grows with the index, and
the whole-walk-forward bands of 10aq ran 0.57-0.70x the forward spread. That fix was drafted after NOISE's first trip was seen; the trip,
read under the frozen 10aq bands, stays on the record (RECORDED_TRIPS, printed in every post).
  A1 SHORTFALL  S = sum over forward rows of (day $ - WF daily mean); tripped when S < -c x WF daily sd x sqrt(rows) at a weekly check (every
                6th row from the start, as calibrated); a trip stays a trip
  A2 DRAWDOWN   the forward running drawdown deeper than the 2.5% depth of a three-year path of the backtested leg
A trip is "worse than the backtested leg does 2.5% of the time" - harm shown, not decay proven. ORB / TTM also carry a big-day WATCH line
(days above their WF 99th percentile, ~3 a year expected) - shown, never an alarm. Order: ORB, TTM, NOISE, ENGU-Q, #463.
WEBULL LEGS (BOOK.md 10ax, MANAGER #146 / #147): the Webull paper book's ORB_R6, NOISE_382 and DIP_424F, read from the newest copy of the
box ledgers that the pull job (tools/pull_box_ledgers.py) left in the box_backup folder - nothing here connects to the box. Bands PER SHARE
(bookq/q38_webull_bands.py + addendum 1) on QQQ 2022-07-01..2025-06-29 at $0.02 a share a round trip, printed at each leg's unit; A1 is
checked every 5 RTH sessions; each trade is booked on its exit day. NOISE_382 is read at its plugin size (KEEL x1.0), with KEEL's extra printed
as a scale term. A failed Webull read is named in the post and never stops the #463 read.

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
SPEC = "BOOK.md 10aq + 10at"
RECORDED_TRIPS = ("NOISE A1 at the 07-17 check under the frozen 10aq bands (-2.71 vs -2.44), reported to MANAGER #805; it stays on the "
                  "record (10at)",)
ORDER = ("ORB", "TTM x3", "NOISE", "ENGU-Q", "#463")
RTH_LEGS = ("ORB", "TTM x3", "NOISE")
# frozen from bookq/q35_recent_bands.py (option 2, MANAGER #141) on the last three WF years 2022-07-01..2025-06-29 (872 book rows): daily
# mean / sd per book row, the A1 constant c, the A2 drawdown alarm, and (ORB / TTM) the big-day threshold = the leg's 99th percentile day there
BANDS = {
    "ORB": {"mu": 209.1858, "sd": 2335.4450, "c": 2.4543, "dd_alarm": 52173.56, "big": 7334.44, "big_per_year": 3.005},
    "TTM x3": {"mu": 49.9952, "sd": 1118.2017, "c": 2.2922, "dd_alarm": 34761.55, "big": 4887.10, "big_per_year": 3.005},
    "NOISE": {"mu": 251.5922, "sd": 1882.0775, "c": 2.3267, "dd_alarm": 28266.63, "big": None, "big_per_year": None},
    "ENGU-Q": {"mu": 215.7006, "sd": 3098.7943, "c": 2.2033, "dd_alarm": 74225.31, "big": None, "big_per_year": None},
    "#463": {"mu": 726.4738, "sd": 5564.1697, "c": 2.2031, "dd_alarm": 74023.59, "big": None, "big_per_year": None},
}
LEG_NAME = {"ORB": "ORB", "ENGUQ": "ENGU-Q", "TTMSQZ": "TTM x3", "NOISE": "NOISE"}
# ---- the Webull legs (above). Bands frozen from bookq/q38_webull_bands.py run 2 (addendum 1), per SESSION at each leg's unit of shares:
# ORB 10 sh, NOISE 10 sh x its plugin size (KEEL x1.0), DIP 6 sh a lot. DIP's c is large because up to 7 lots book on one exit day (worst day
# 14 sd): its weekly z-line is weak (12% power at 36 months) - stated in the post, never hidden.
WEBULL_ORDER = ("ORB_R6", "NOISE_382", "DIP_424F")
WEBULL_UNIT = {"ORB_R6": 10, "NOISE_382": 10, "DIP_424F": 6}
WEBULL_UNIT_WORDS = {"ORB_R6": "10 sh", "NOISE_382": "10 sh x plugin size", "DIP_424F": "6 sh a lot"}
# the box names the trades of a leg by its ENGINE key: trade ids "<key>-<UTC>-<side>[-<slot>]" and the engine rows in signals.csv. DIP_424F (the
# constant-size shadow) went live as engine key DIP_424, one executor leg per mechanism slot (DIP_RSI .. DIP_GAPDN; box 10-12/13)
WEBULL_ENGINE_KEY = {"ORB_R6": "ORB_R6", "NOISE_382": "NOISE_382", "DIP_424F": "DIP_424"}
WEBULL_EXEC_LEG = {"ORB_R6": "ORB", "NOISE_382": "NOISE", "DIP_424F": "DIP_"}    # trades.csv leg column (DIP: the prefix of its slot legs), for a row with no trade_id
WEBULL_START = {"ORB_R6": "2026-09-09", "NOISE_382": "2026-09-24", "DIP_424F": "2026-10-13"}   # DIP: live_since 10-13 (its first lots)
WEBULL_WEEK_ROWS = 5
WEBULL_BANDS = {
    "ORB_R6": {"mu": 2.5041, "sd": 28.0281, "c": 2.3369, "dd_alarm": 560.12, "big": 90.99, "big_per_year": 2.671},
    "NOISE_382": {"mu": 3.6116, "sd": 30.5142, "c": 2.2758, "dd_alarm": 506.11, "big": None, "big_per_year": None},
    "DIP_424F": {"mu": 6.3861, "sd": 120.0606, "c": 3.9496, "dd_alarm": 5991.10, "big": None, "big_per_year": None},   # Q42: marked to market
}
WEBULL_POWER = ("power if the edge is gone, by 36 months: ORB_R6 88%, NOISE_382 96%, DIP_424F 13% (marked to market; a dead DIP is "
                "barely visible inside 36 months, its A2 sees open-lot losses)")
# Q42 (BOOK.md 10ba, prereg/frontier-dipmtm-1014): DIP holds lots for days, so it is read MARKED TO MARKET - each pull folder's state.json
# carries every open lot's mark_px at the close; a lot's daily $ = (mark - its previous mark, or its entry) x shares, and the day it
# closes (exit price - its previous mark). The band is Q42's, calibrated the same way on the same window.
WEBULL_MTM = ("DIP_424F",)
MARK_AFTER = (14, 30)                # a pull folder stamped before 14:30 MST (16:30 ET) holds intraday marks, not the close
NYSE_CLOSED = {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26",
               "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
               "2027-11-25", "2027-12-24"}                         # NYSE full closes 2026-27 (the Webull legs' session calendar)
fmt = "{:,.0f}".format


# ------------------------------------------------------------------ the read (pure)
def evaluate(x, band, days_per_year=292.0, week_rows=None):
    """x = the forward daily $ (book rows, in order), band = one BANDS entry -> the leg's read. week_rows = the A1 check spacing (WEEK_ROWS for
    #463's book rows, WEBULL_WEEK_ROWS for the Webull legs' RTH sessions)"""
    x = np.asarray(x, float)
    n = len(x)
    out = {"days": n, "net": float(x.sum())}
    if n == 0:
        out.update({"a1": False, "a2": False, "a1_z": None, "dd": 0.0, "a1_text": "no forward days yet", "a2_text": "no forward days yet"})
        return out
    s = np.cumsum(x - band["mu"])
    w = week_rows or WEEK_ROWS
    chk = np.arange(w, n + 1, w)                        # the alarm looks only at every w-th row from the start, as calibrated (q33 `checks`)
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


def format_post(reads, asof, meta=None, webull=None):
    """the Monday post: trips first, then paused legs and data notes, then each leg's distance to A1 / A2 in plain words, then the Webull
    legs block (webull = (reads, meta) from read_webull / webull_forward, or None)"""
    meta = meta or {}
    wreads, wmeta = webull if webull else ({}, {})
    trips = [(nm, r) for nm, r in reads.items() if r.get("a1") or r.get("a2")]
    trips += [("Webull " + nm, r) for nm, r in wreads.items() if r.get("a1") or r.get("a2")]
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
    if webull:
        lines += webull_lines(wreads, wmeta)
    for rec in RECORDED_TRIPS:
        lines.append("- On record: " + rec + ".")
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


def webull_lines(wreads, wmeta):
    """the Webull legs block (trips are already at the top of the post)"""
    if wmeta.get("error"):
        return ["- Webull legs not read: %s." % wmeta["error"]]
    out = ["- Webull legs (per share at each leg's unit; pull-job folder %s, data through %s; %s):"
           % (wmeta.get("folder", "?"), wmeta.get("end", "?"), WEBULL_POWER)]
    for note in wmeta.get("notes", []):
        out.append("- Webull data note: " + note)
    for nm in WEBULL_ORDER:
        r = wreads.get(nm)
        if r is None:
            continue
        if r.get("no_trades"):
            out.append("- Webull %s at %s: no trades yet." % (nm, WEBULL_UNIT_WORDS[nm]))
            continue
        if r.get("a1") or r.get("a2"):
            continue
        txt = ("- Webull %s at %s (%d sessions from %s, %d trades, net $%s): A1 %s. A2 %s."
               % (nm, WEBULL_UNIT_WORDS[nm], r["days"], r.get("start", "?"), r.get("trades", 0), fmt(r["net"]), r["a1_text"], r["a2_text"]))
        if r.get("watch_text"):
            txt += " " + r["watch_text"].capitalize() + "."
        if r.get("keel_scale") is not None:
            txt += " KEEL scale term %.2f (the $ as sent / the $ at plugin size)." % r["keel_scale"]
        out.append(txt)
    return out


def webull_sessions(d0, d1):
    return pd.DatetimeIndex([d for d in pd.bdate_range(d0, d1) if str(d.date()) not in NYSE_CLOSED])


def webull_folder(run_day, root=None):
    """the newest pull-job folder (<root>/<YYYY-MM-DD_HHMM>/ with qqq_exec/trades.csv) dated on or before the run day -> (path, stamp) or None"""
    import glob
    root = root or os.environ.get("EDGELOG_BOX_BACKUP", r"C:\EdgeLog\box_backup")
    best = None
    for p in sorted(glob.glob(os.path.join(root, "20??-??-??_????"))):
        try:
            stamp = pd.to_datetime(os.path.basename(p), format="%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if stamp.normalize() <= run_day and os.path.exists(os.path.join(p, "qqq_exec", "trades.csv")):
            best = (p, stamp)
    return best


def webull_folders(run_day, root=None):
    """every pull-job folder dated on or before the run day -> [(path, stamp)], the LAST one of each date, oldest first"""
    import glob
    root = root or os.environ.get("EDGELOG_BOX_BACKUP", r"C:\EdgeLog\box_backup")
    by_day = {}
    for p in sorted(glob.glob(os.path.join(root, "20??-??-??_????"))):
        try:
            stamp = pd.to_datetime(os.path.basename(p), format="%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if stamp.normalize() <= run_day and os.path.exists(os.path.join(p, "qqq_exec", "state.json")):
            by_day[stamp.normalize()] = (p, stamp)
    return [by_day[d] for d in sorted(by_day)]


def webull_mtm(closed, folders, exec_prefix, unit, start, end, cal):
    """Q42: a holding leg's daily $ at its unit, marked to market. closed = its trades.csv rows (trade_id, day, entry_px, exit_px, shares);
    folders = webull_folders(); open lots come from each folder's state.json legs with the exec_prefix. -> (daily Series on cal, notes)"""
    import json
    daily = pd.Series(0.0, index=cal)
    marks, notes, skipped, seen = {}, [], [], set()
    for path, stamp in folders:
        d = stamp.normalize()
        if (stamp.hour, stamp.minute) < MARK_AFTER:
            skipped.append(str(d.date()))
            continue
        if d < start or d > end:
            continue
        seen.add(d)
        try:
            st = json.load(open(os.path.join(path, "qqq_exec", "state.json"), encoding="utf-8"))
        except (OSError, ValueError):
            notes.append("%s: state.json unreadable - its marks are not read" % os.path.basename(path))
            continue
        for k, v in (st.get("legs") or {}).items():
            if not str(k).startswith(exec_prefix) or not v.get("shares_remaining") or v.get("mark_px") is None:
                continue
            tid = v.get("trade_id") or k
            prev = marks.get(tid, float(v["entry_px"]))
            if d in daily.index:
                daily[d] += (float(v["mark_px"]) - prev) * unit
            marks[tid] = float(v["mark_px"])
    for _, r in closed.iterrows():
        d = r["day"]
        if d < start or d > end or d not in daily.index:
            continue
        prev = marks.get(r["trade_id"], float(r["entry_px"]))
        daily[d] += (float(r["exit_px"]) - prev) * unit
    held = [d for d in cal if d not in seen and daily.index.min() <= d]
    if skipped:
        notes.append("pull folder(s) %s were taken before the close - their marks are not read" % ", ".join(skipped))
    if held and len(seen):
        notes.append("%d session(s) with no pull folder - the next folder's marks carry their change" % len(held))
    return daily, notes


def webull_forward(asof, root=None):
    """the Webull legs' forward unit $ from the newest pull-job folder (read-only) -> ({leg: daily Series on NYSE sessions}, meta)"""
    run_day = pd.Timestamp(asof).normalize()
    f = webull_folder(run_day, root)
    if f is None:
        return {}, {"error": "no pull-job folder on or before %s in the box backup" % run_day.date()}
    path, stamp = f
    last = stamp.normalize() if (stamp.hour, stamp.minute) >= (14, 30) else stamp.normalize() - pd.Timedelta(days=1)   # 14:30 MST = 16:30 ET
    last = min(last, run_day - pd.Timedelta(days=1))
    T = pd.read_csv(os.path.join(path, "qqq_exec", "trades.csv"))
    sp = os.path.join(path, "cloud_signal", "signals.csv")
    S = pd.read_csv(sp) if os.path.exists(sp) else pd.DataFrame(columns=["leg", "event", "trade_id", "keel_size", "ref_time"])
    T["day"] = pd.to_datetime(T["exit_ts"]).dt.normalize()
    pre = T["trade_id"].fillna("").astype(str).str.split("-").str[0]
    meta = {"folder": os.path.basename(path), "starts": {}, "trades": {}, "keel_scale": {}, "notes": []}
    age = int(np.busday_count(stamp.date(), run_day.date()))
    if age > 2:
        meta["notes"].append("the newest pull-job folder is %s, %d weekdays before the run day - the box ledger read is stale" % (meta["folder"], age))
    cal_all = webull_sessions("2026-01-01", last)
    end = cal_all[-1] if len(cal_all) else last
    meta["end"] = str(end.date())
    eng_k = S[(S["event"] == "ENTRY") & S["trade_id"].notna()].drop_duplicates("trade_id", keep="last").set_index("trade_id")["keel_size"]
    out = {}
    for nm in WEBULL_ORDER:
        key = WEBULL_ENGINE_KEY[nm]
        m = pre.eq(key)
        start = WEBULL_START[nm] or (str(T.loc[m, "day"].min().date()) if m.any() else None)
        if start is None or pd.Timestamp(start) > end:                 # not live yet in this folder's data = "no trades yet"
            continue
        el = WEBULL_EXEC_LEG[nm]
        legcol = T["leg"].astype(str)
        loose = pre.eq("") & (legcol.str.startswith(el) if el.endswith("_") else legcol.eq(el)) & (T["day"] >= start)
        x = T[(m | loose) & (T["day"] >= start) & (T["day"] <= end)].copy()
        if nm == "NOISE_382":                                      # the size column is the SENT size (plugin x KEEL): plugin = size / keel
            k = x["keel_size"].where(x["keel_size"].notna(), x["trade_id"].map(eng_k))
            if k.isna().any():
                meta["notes"].append("%d %s row(s) carry no KEEL size anywhere - read at KEEL 1.0" % (int(k.isna().sum()), nm))
            size = x["size"].fillna(1.0) / k.fillna(1.0)
        else:
            size = 1.0
        x["unit"] = x["pnl"] / x["shares"] * WEBULL_UNIT[nm] * size
        cal = webull_sessions(start, end)
        if nm in WEBULL_MTM:                                       # Q42: marked to market from the folders' marks
            out[nm], mnotes = webull_mtm(x.assign(trade_id=x["trade_id"].fillna("")), webull_folders(run_day, root),
                                         WEBULL_EXEC_LEG[nm], WEBULL_UNIT[nm], pd.Timestamp(start), end, cal)
            meta["notes"] += ["%s: %s" % (nm, t) for t in mnotes]
        else:
            out[nm] = x.groupby("day")["unit"].sum().reindex(cal).fillna(0.0)
        meta["starts"][nm], meta["trades"][nm] = start, int(len(x))
        if int(loose[x.index].sum()):
            meta["notes"].append("%d %s trade(s) have no trade id (assigned by leg and date)" % (int(loose[x.index].sum()), nm))
        off = sorted(set(x["day"]) - set(cal))
        if off:
            meta["notes"].append("%s has trades on %s, off the NYSE calendar - look first" % (nm, ", ".join(str(d.date()) for d in off)))
        ex = S[(S["leg"] == key) & (S["event"] == "EXIT")]
        if len(ex):
            ed = pd.to_datetime(ex["ref_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
            n_eng = int(((ed >= start) & (ed <= end)).sum())
            if n_eng != len(x):
                meta["notes"].append("%s: %d engine exits vs %d executor trades - reconcile before trusting the read" % (nm, n_eng, len(x)))
        if nm == "NOISE_382" and len(x) and abs(float(x["unit"].sum())) > 1e-9:
            meta["keel_scale"][nm] = float(x["pnl"].sum() / x["unit"].sum())
    return out, meta


def read_webull(fw, meta):
    """{leg: forward Series} + meta -> {leg: read}, A1 checked every WEBULL_WEEK_ROWS sessions"""
    reads = {}
    for nm in WEBULL_ORDER:
        if nm not in fw:
            reads[nm] = {"no_trades": True}
            continue
        r = evaluate(fw[nm].to_numpy(float), WEBULL_BANDS[nm], days_per_year=252.0, week_rows=WEBULL_WEEK_ROWS)
        r["start"], r["trades"] = meta.get("starts", {}).get(nm, "?"), meta.get("trades", {}).get(nm, 0)
        if nm in meta.get("keel_scale", {}):
            r["keel_scale"] = meta["keel_scale"][nm]
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
        try:                                                        # the Webull read never stops the #463 read
            wf, wmeta = webull_forward(a.asof)
            webull = (read_webull(wf, wmeta), wmeta)
        except Exception as e:
            webull = ({}, {"error": "%s: %s" % (type(e).__name__, e)})
        txt = format_post(reads, a.asof, meta, webull)
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
