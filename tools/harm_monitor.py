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
ORB TREND-DAY CAPTURE (ORB lane #857 item 1, MANAGER #70 GO 10-11; report-only, no rule change, #314 untouched): ORB makes its money on
NQ's big trend days (24 of the ORB leg's 26 best walk-forward days are NQ top-5% move days), so this reads whether ORB still catches them -
a decay alarm that has power long before the leg's own dollars do. A trend day = |last RTH close - first RTH open| / first open >= 1.73% on
the NQ 5m RTH NO-ADJUST master (raw prices: a true %), the walk-forward's top 10% (2016-07-01..2025-06-29, 232 of 2,318 days, 25.8 a year);
a hit = the ORB leg's forward day $ > 0 on it (walk-forward 60.8%). Forward trend days are cut into NON-overlapping blocks of 26 from
2026-07-01; a block with <= 11 hits is a TREND TRIP (false alarm 4.35% a block, 93.4% power if the hit rate halves). A trip stays on the
record. A failed trend read is named in the post and never stops the #463 read.
ORB_R6 EXECUTION (ORB lane #857 item 2, MANAGER #70 GO; report-only): the Webull ORB_R6 executor against the cloud engine's own signals, trade
by trade on trade_id - engine $ = side x (EXIT ref_price - ENTRY ref_price) at the unit, executor $ = its fill P&L at the unit. ORB's year
lives in a few big days, so a big engine day (>= the band's big-day line, $90.99 at 10 sh, ~2.7 a year) must be booked at >= 80% by the
executor, and an engine trade with no executor fill is a MISS. Also printed: fills vs the engine's prices over every matched trade.
ORB_R6 parity with the live engine is tools/live_parity_check.py's job (nightly on the box, every live leg, the live engine's
own code) - not repeated here.
ORB RELAY SHADOW (ORB-RELAY r1 forward, MANAGER #80 GO; report-only): the same ORB settings on NQ's 5m bars (back-adjusted master), filled on
the box's OWN live QQQ 1m bar cache (pulled read-only into each box_backup folder as ohlc/QQQ_1m.csv; every folder's copy is merged, the
newest winning) the way RELAY r1 did it - entry at the open of the first QQQ minute after the NQ signal bar (one minute of executor lag), exit
at the QQQ close of the first NQ 1m minute that reaches the NQ exit level, EOD at the close of the session's last minute - at 10 shares and
$0.02 a share a round trip, beside the live ORB_R6 leg over the same days. No new data pull. A harm / parity line, never a decider: a
forward gap between two one-episode ROCs is unreadable for years (BOOK.md 10y).

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
EXEC_LEG, EXEC_SHARE = "ORB_R6", 0.80   # a big engine day must be booked at >= 80% by the executor
RELAY_COST = 0.02                 # $ a share a round trip, as the leg's bands
TREND_MASTER = ("NQ", "5m", "rth", "db_noadj_rth")
TREND_THR = 0.017319              # the walk-forward's 90th percentile of |close - open| / open (frozen 10-12, scratchpad trendcap_freeze.py)
TREND_BASE = 0.6078               # the ORB leg up on 141 of those 232 walk-forward days
TREND_BLOCK, TREND_ALARM = 26, 11  # non-overlapping blocks of 26 trend days; a block with <= 11 hits trips
TREND_POWER = "alarm at <= 11 of a block of 26 (backtest 61%: false alarm 4% a block, 93% power if the hit rate halves)"
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


def trend_capture(moves, orb):
    """moves = forward day |close - open| / open (NQ RTH, raw); orb = the ORB leg's forward day $ -> the trend-day read: every trend day
    with its $, the closed blocks of TREND_BLOCK (hits, tripped) and the open block's count so far"""
    q = moves[moves >= TREND_THR].sort_index()
    usd = orb.reindex(q.index).fillna(0.0)
    hit = (usd > 0).astype(int)
    blocks = []
    for b in range(len(hit) // TREND_BLOCK):
        h = int(hit.iloc[b * TREND_BLOCK:(b + 1) * TREND_BLOCK].sum())
        blocks.append({"end": str(hit.index[(b + 1) * TREND_BLOCK - 1].date()), "hits": h, "tripped": h <= TREND_ALARM})
    rest = hit.iloc[len(blocks) * TREND_BLOCK:]
    return {"days": int(len(hit)), "hits": int(hit.sum()), "blocks": blocks, "open_days": int(len(rest)), "open_hits": int(rest.sum()),
            "tripped": any(b["tripped"] for b in blocks),
            "recent": [(str(d.date()), round(float(q[d]) * 100, 2), float(usd[d])) for d in q.index[-3:]]}


def trend_line(t, start):
    """the trend-day read in plain words (report-only)"""
    if t.get("error"):
        return "- ORB trend-day capture not read: %s." % t["error"]
    if not t["days"]:
        return ("- ORB trend-day capture (report-only): no NQ trend day (>= %.2f%% open to close) since %s; %s."
                % (TREND_THR * 100, start, TREND_POWER))
    txt = ("- ORB trend-day capture (report-only): NQ moved >= %.2f%% open to close on %d day(s) since %s; ORB was up on %d (%.0f%%; backtest %.0f%%)."
           % (TREND_THR * 100, t["days"], start, t["hits"], 100.0 * t["hits"] / t["days"], TREND_BASE * 100))
    for b in t["blocks"]:
        txt += (" TREND TRIP: the block of %d ending %s had %d up." if b["tripped"] else " Block of %d ending %s: %d up.") % (TREND_BLOCK, b["end"], b["hits"])
    txt += " Open block: %d up of %d so far; %s." % (t["open_hits"], t["open_days"], TREND_POWER)
    txt += " Latest: %s." % ", ".join("%s %.2f%% ORB $%s" % (d, m, fmt(u)) for d, m, u in t["recent"])
    return txt


def trend_read(asof, fw, meta):
    """the forward trend days on the no-adjust NQ RTH master, read against the ORB leg's forward day $ (read-only)"""
    sys.path.insert(0, ROOT)
    from augur_engine.data import find_master, load_master_arrays
    run_day = pd.Timestamp(asof).normalize()
    m = find_master(*TREND_MASTER)
    arr = load_master_arrays(m, date_from=str(FORWARD_START.date()), date_to=str(run_day.date()))
    idx = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    df = pd.DataFrame({"o": np.asarray(arr["open"], float), "c": np.asarray(arr["close"], float)}, index=idx)
    day = df.groupby(df.index.normalize()).agg(o=("o", "first"), c=("c", "last"))
    end = meta.get("end")
    day = day[(day.index >= FORWARD_START) & (day.index < run_day) & ((day.index <= end) if end is not None else True)]
    return trend_capture((day["c"] - day["o"]).abs() / day["o"], fw["ORB"])


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
    if meta.get("trend") is not None:
        lines.append(trend_line(meta["trend"], str(FORWARD_START.date())))
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


def webull_exec_check(S, T, start, end, nm=EXEC_LEG):
    """engine signals (signals.csv rows) vs executor fills (trades.csv rows) for one leg, matched on trade_id, at the leg's unit
    -> {engine, filled, missed [(day, engine $)], big [(day, engine $, executor $ or None, ok)], slip_mean, slip_n}"""
    unit = WEBULL_UNIT[nm]
    if not len(S) or not {"leg", "event", "side", "ref_price", "ref_time", "trade_id"} <= set(S.columns):
        return {"engine": 0, "filled": 0, "missed": [], "big": [], "slip_mean": None, "slip_n": 0}
    s = S[(S["leg"] == nm) & S["trade_id"].notna()]
    en = s[s["event"] == "ENTRY"].drop_duplicates("trade_id", keep="last").set_index("trade_id")
    ex = s[s["event"] == "EXIT"].drop_duplicates("trade_id", keep="last").set_index("trade_id")
    e = en[["side", "ref_price"]].join(ex[["ref_price", "ref_time"]], rsuffix="_x", how="inner")
    if not len(e):
        return {"engine": 0, "filled": 0, "missed": [], "big": [], "slip_mean": None, "slip_n": 0}
    sg = np.where(e["side"].astype(str).str.lower().str.startswith("s"), -1.0, 1.0)
    e["eng"] = sg * (e["ref_price_x"].astype(float) - e["ref_price"].astype(float)) * unit
    e["day"] = pd.to_datetime(e["ref_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    e = e[(e["day"] >= pd.Timestamp(start)) & (e["day"] <= pd.Timestamp(end))]
    t = T[T["trade_id"].astype(str).isin(set(e.index))].drop_duplicates("trade_id", keep="last").set_index("trade_id")
    e["exe"] = (t["pnl"].astype(float) / t["shares"].astype(float) * unit).reindex(e.index)
    big_line = WEBULL_BANDS[nm]["big"]
    big = [(str(d.date()), float(g), None if pd.isna(x) else float(x), (not pd.isna(x)) and float(x) >= EXEC_SHARE * float(g))
           for d, g, x in zip(e["day"], e["eng"], e["exe"]) if big_line is not None and g >= big_line]
    missed = [(str(d.date()), float(g)) for d, g, x in zip(e["day"], e["eng"], e["exe"]) if pd.isna(x)]
    slip = (e["exe"] - e["eng"]).dropna()
    return {"engine": int(len(e)), "filled": int(e["exe"].notna().sum()), "missed": missed, "big": big,
            "slip_mean": float(slip.mean()) if len(slip) else None, "slip_n": int(len(slip))}


def exec_line(c, nm=EXEC_LEG):
    """the execution check in plain words (report-only)"""
    if c.get("error"):
        return "- Webull %s execution not read: %s." % (nm, c["error"])
    if not c["engine"]:
        return "- Webull %s execution (report-only): no closed engine trade in the ledgers yet." % nm
    txt = "- Webull %s execution (report-only): %d engine trade(s), %d filled" % (nm, c["engine"], c["filled"])
    txt += (", MISSED %s." % ", ".join("%s (engine $%s)" % (d, fmt(g)) for d, g in c["missed"])) if c["missed"] else "."
    if c["slip_n"]:
        txt += (" Fills ran $%.2f a trade %s the engine's prices at %s (%d trade(s))."
                % (abs(c["slip_mean"]), "below" if c["slip_mean"] < 0 else "above", WEBULL_UNIT_WORDS[nm], c["slip_n"]))
    if c["big"]:
        for d, g, x, ok in c["big"]:
            txt += (" Big day %s: engine $%s, executor $%s (%s)." % (d, fmt(g), "none" if x is None else fmt(x),
                                                                     "booked" if ok else "SHORT of 80%"))
    else:
        txt += " No big engine day yet (>= $%s at %s, ~%.1f a year)." % (fmt(WEBULL_BANDS[nm]["big"]), WEBULL_UNIT_WORDS[nm],
                                                                         WEBULL_BANDS[nm]["big_per_year"])
    return txt


def box_qqq_1m(root=None, tf="1m", full=False):
    """every box_backup folder's ohlc/QQQ_<tf>.csv (the box's own live bar cache, copied read-only by tools/pull_box_ledgers.py), merged
    with the newest copy winning -> DataFrame (o, c; with `full` also h, l, v) on US/Eastern bar starts, or None"""
    root = root or os.environ.get("EDGELOG_BOX_BACKUP", r"C:\EdgeLog\box_backup")
    parts = []
    for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        f = os.path.join(root, d, "ohlc", "QQQ_%s.csv" % tf)
        if os.path.exists(f):
            x = pd.read_csv(f)
            x["rank"] = d
            parts.append(x)
    if not parts:
        return None
    x = pd.concat(parts).sort_values(["time", "rank"]).drop_duplicates("time", keep="last")
    ix = pd.to_datetime(x["time"].astype("int64"), unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    cols = {"o": "open", "c": "close"}
    if full:
        cols.update(h="high", l="low", v="volume")
    return pd.DataFrame({k: x[c].astype(float).to_numpy() for k, c in cols.items()}, index=pd.DatetimeIndex(ix))


def relay_trades(q1, start, end):
    """the ORB_R6 settings on NQ 5m (back-adjusted) through the engine, each trade filled on QQQ 1m prints (q1) -> list of
    (day, side, $ at 10 sh) for trades entering on or after `start` and exiting on or before `end`; trades with no QQQ minute are skipped"""
    sys.path.insert(0, ROOT)
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    leg = cs.CROWN_LEGS["ORB_R6"]
    s0, s1 = pd.Timestamp(start), pd.Timestamp(end)
    warm = str((s0 - pd.Timedelta(days=150)).date())
    a5 = load_master_arrays(find_master("NQ", "5m", "rth", "db_adj_rth"), date_from=warm, date_to=str(s1.date()))
    a1 = load_master_arrays(find_master("NQ", "1m", "rth", "db_adj_rth"), date_from=str(s0.date()), date_to=str(s1.date()))
    r = run_backtest(leg["strategy"], arrays=a5, params=dict(leg["params"]), cost_pts=0.0, return_trades=True)

    def et(ix):
        ix = pd.DatetimeIndex(ix)
        return ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix

    ix5 = et(a5["index"])
    n1 = pd.DataFrame({"h": np.asarray(a1["high"], float), "l": np.asarray(a1["low"], float)}, index=et(a1["index"]))
    close5 = np.asarray(a5["close"], float)
    last = pd.Series(np.arange(len(ix5)), index=ix5).groupby(ix5.normalize()).max()
    one = pd.Timedelta(minutes=1)
    out = []
    for t in (r or {}).get("trades") or []:
        ei, xi, pts, d, e = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        te, tx = ix5[ei], ix5[min(xi, len(ix5) - 1)]
        if te.normalize() < s0 or tx.normalize() > s1:
            continue
        lvl = e + pts * d
        if xi == int(last[tx.normalize()]) and abs(lvl - close5[xi]) < 1e-6:
            xt = tx + 4 * one
        else:
            mins = n1.loc[tx:tx + 4 * one]
            if d > 0:
                hit = mins.index[(mins["l"] <= lvl).to_numpy()] if lvl <= e else mins.index[(mins["h"] >= lvl).to_numpy()]
            else:
                hit = mins.index[(mins["h"] >= lvl).to_numpy()] if lvl >= e else mins.index[(mins["l"] <= lvl).to_numpy()]
            xt = hit[0] if len(hit) else tx + 4 * one
        if (te + 5 * one) not in q1.index or xt not in q1.index:
            continue
        qe, qx = float(q1.at[te + 5 * one, "o"]), float(q1.at[xt, "c"])
        out.append((str(tx.normalize().date()), d, WEBULL_UNIT[EXEC_LEG] * (d * (qx - qe) - RELAY_COST)))
    return out


def relay_line(rl, live_net, live_n, start):
    """the relay shadow in plain words (report-only)"""
    if rl.get("error"):
        return "- ORB relay shadow not read: %s." % rl["error"]
    return ("- ORB relay shadow (report-only, NQ signals on the box's QQQ 1m bars, one-minute lag, 10 sh): %d trade(s) since %s, net $%s; "
            "the live ORB_R6 leg over the same days: %d trade(s), net $%s. A parity line, not a decider."
            % (rl["n"], start, fmt(rl["net"]), live_n, fmt(live_net)))


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
    if wmeta.get("exec") is not None:
        out.append(exec_line(wmeta["exec"]))
    if wmeta.get("relay") is not None:
        r = wreads.get(EXEC_LEG) or {}
        out.append(relay_line(wmeta["relay"], r.get("net", 0.0), r.get("trades", 0), wmeta.get("starts", {}).get(EXEC_LEG, "?")))
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
    if EXEC_LEG in meta["starts"]:
        try:                                                        # report-only; never stops the Webull read
            meta["exec"] = webull_exec_check(S, T, meta["starts"][EXEC_LEG], end)
        except Exception as e:
            meta["exec"] = {"error": "%s: %s" % (type(e).__name__, e)}
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
        try:                                                        # the ORB trend-day read never stops the #463 read either
            meta["trend"] = trend_read(a.asof, fw, meta)
        except Exception as e:
            meta["trend"] = {"error": "%s: %s" % (type(e).__name__, e)}
        try:                                                        # the Webull read never stops the #463 read
            wf, wmeta = webull_forward(a.asof)
            if EXEC_LEG in wmeta.get("starts", {}):
                try:                                                # report-only; never stops the Webull read
                    q1 = box_qqq_1m()
                    if q1 is None:
                        raise RuntimeError("no ohlc/QQQ_1m.csv in any box_backup folder yet (the pull job copies it nightly)")
                    rt = relay_trades(q1, wmeta["starts"][EXEC_LEG], wmeta["end"])
                    wmeta["relay"] = {"n": len(rt), "net": float(sum(v for _d, _s, v in rt)), "trades": rt}
                except Exception as e:
                    wmeta["relay"] = {"error": "%s: %s" % (type(e).__name__, e)}
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
