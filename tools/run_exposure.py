# -*- coding: utf-8 -*-
"""RUN EXPOSURE TABLE - the runner side (MANAGER #41 phase 2, DISC's recipe #42).

RSIDIV #163 looked great but was a leveraged buy-and-hold: in the market 96% of the sessions, 3.65 lots on average,
0.84x what a constant-exposure buy-and-hold of NQ would have made. The board must flag that kind of run and the run
report must show its buy-and-hold twin. The web cannot compute it (it needs every trade and a price series), so this
tool does, and writes ONE small Firestore doc the web reads once per load:

    users/{uid}/meta/run_exposure = {
      "v": 1, "updated_at": "<UTC ISO>", "updated_by": "<lane>",
      "runs": { "163": { in_mkt_pct, lots_mean_all, lots_mean_in, lots_max, hold_med_sessions, n_trades,
                         strat_pts, twin_pts, ratio, ratio_why?, sessions, first, last,
                         window: [date_from, date_to], master: "<registry name> [<source>]", inst, tf, mult,
                         curve? },
                "424": { "why": "no saved trade list" }, ... } }

The maths lives in augur_engine/exposure.py (pure, tested); the recipe is documented there. This tool only does the
plumbing: read the run docs, find each run's saved trade list, find the price master, write the doc.

- run docs: users/{uid}/runs (uid as in tools/runboard_watch.py), PROJECTED to the 13 fields needed. Firestore bills one
  read per document returned, projection or not, so a pass costs about one read per run plus one for the target doc:
  `--ids 163` = 2 reads; `--all` = about the number of runs on the board (a few hundred) - well under 1k of the Spark
  tier's 50k a day. The reads are counted and printed.
- trade lists: the cached CSV <repo>/blotters/run{id}_{INST}_{TF}.csv (api/blotter.load_blotter_rows's names), ALL rows
  (the web's 6000-row cap is for the wire, not for this). A missing one is {"why": "no saved trade list"}; with --regen
  only, it is rebuilt through api.blotter with the payload the web builds and cached there as api.blotter caches it.
  Books are skipped (a book pools several strategies; there is no single trade list) and said so.
- price series: the instrument's house BACK-ADJUSTED RTH master (source db_adj_rth) at the run's timeframe, so the twin
  carries no roll gaps; for an instrument with no adjusted master (ETFs, stocks: no rolls) the run's own master, else
  the plain one. The output says which. No master at all -> twin null with a plain `why`.
- `curve` (augur_engine.exposure.twin_curve, 120 points) is stored ONLY for a run in the market more than 50% of the
  sessions - for an intraday run the twin is a near-zero line that says nothing - and is stored as a JSON TEXT STRING
  of [["YYYY-MM-DD", twin_pts_cum, strat_pts_cum], ...]: Firestore rejects an array inside an array, and it would index
  every element of a real array (Firestore caps a document at 40,000 index entries). JSON.parse it.
- flags are the web's job; this tool stores numbers only.

    python tools/run_exposure.py --ids 163 424 --dry                  (a table + the JSON size; writes nothing)
    python tools/run_exposure.py --all --dry
    python tools/run_exposure.py --all --write --from MANAGER         (merge: entries for runs not in this pass stay)
    python tools/run_exposure.py --ids 163 --regen --write --from DISC (rebuild a missing trade list first - slow)
    --root DIR  where blotters/ and augur_strategies/ live (default: this checkout). A git worktree has neither the
                master registry nor the blotters, so run it from the shared checkout, or from a worktree through
                C:\\EdgeLog\\_anatomy_cache\\bookq\\run_shared.py with --root pointing at the shared checkout.

Safety: the doc is checked before every write - refused over 900 KB (Firestore's own hard cap is 1,048,576 B), refused
over 38,000 estimated index entries (Firestore's is 40,000), and a nested array is refused outright. Credentials: as
runboard_watch.py (serviceAccount.json; never printed). os._exit after the work (gRPC shutdown hang).
"""
import argparse
import csv
import datetime
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)   # appended, not inserted: run through run_shared.py the SHARED augur_engine must stay first

import tools.runboard_watch as rw  # noqa: E402  (UID, real_client, the transaction helper, ToolError)

try:
    from augur_engine import exposure as X
except ImportError:   # run through run_shared.py: the shared checkout's augur_engine has no exposure.py until this ships
    _spec = importlib.util.spec_from_file_location("exposure", os.path.join(ROOT, "augur_engine", "exposure.py"))
    X = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(X)

ToolError = rw.ToolError
DOC_ID = "run_exposure"
VERSION = 1
# the run-doc fields this tool needs and nothing else (code_snapshot, equity curves, validate blocks stay on the server)
FIELDS = ["id", "strategy", "scope", "book.legs", "best_params", "instrument", "timeframe", "session",
          "cost_pts", "multiplier", "date_from", "date_to", "data_source"]
CURVE_MIN_IN_MKT = 50.0        # a curve is stored only above this in-market % (DISC)
CURVE_POINTS = 120
SIZE_WARN = 600_000            # bytes, Firestore's own size rules
SIZE_REFUSE = 900_000
INDEX_WARN = 30_000            # estimated index entries; Firestore's hard cap is 40,000 per document
INDEX_REFUSE = 38_000
# contract $ per point, as augur_engine/book.py and the web's INSTRUMENTS table; used only when the run doc has no multiplier
_MULT = {"ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "RTY": 50, "M2K": 5, "YM": 5, "MYM": 0.5, "CL": 1000, "MCL": 100,
         "GC": 100, "MGC": 10, "SI": 5000, "ZB": 1000, "ZN": 1000, "6E": 125000, "BTC": 5, "MBT": 0.1}
_QUIET = lambda *a, **k: None   # noqa: E731


# ── Firestore plumbing ───────────────────────────────────────────────────────────────────────
class Reads:
    """Firestore document reads this pass paid for (Spark tier: 50,000 a day)."""
    def __init__(self):
        self.runs = 0
        self.meta = 0

    @property
    def total(self):
        return self.runs + self.meta

    def line(self):
        return "[reads] %d run doc(s) + %d target-doc read(s) = %d Firestore reads (Spark quota 50,000 a day)" % (
            self.runs, self.meta, self.total)


def exposure_ref(db):
    return rw._user(db).collection("meta").document(DOC_ID)


def fetch_run_docs(db, ids, reads):
    """{id: projected run doc or None} for the ids, or for every run when ids is None. One read per document."""
    out = {}
    if ids is None:
        for snap in rw._user(db).collection("runs").select(FIELDS).stream():
            reads.runs += 1
            d = snap.to_dict() or {}
            rid = d.get("id", getattr(snap, "id", None))
            try:
                rid = int(rid)
            except (TypeError, ValueError):
                continue
            out[rid] = d
        return out
    for rid in ids:
        snap = rw.run_ref(db, rid).get(field_paths=FIELDS)
        reads.runs += 1
        out[rid] = snap.to_dict() if getattr(snap, "exists", False) else None
    return out


# ── which runs ───────────────────────────────────────────────────────────────────────────────
def is_book(d):
    """The web's own test (index.html, the cost-readings card): a book pools several strategies."""
    strat = str(d.get("strategy") or "")
    legs = (d.get("book") or {}).get("legs") if isinstance(d.get("book"), dict) else None
    return (isinstance(legs, list) or "Book" in str(d.get("scope") or "")
            or strat.startswith("BOOK:") or strat.startswith("COMBINED"))


def run_mult(d):
    try:
        m = float(d.get("multiplier"))
        if m > 0:
            return m
    except (TypeError, ValueError):
        pass
    return _MULT.get(str(d.get("instrument") or "").upper())   # None for an instrument nobody has a table row for


# ── trade lists ──────────────────────────────────────────────────────────────────────────────
def blotter_paths(root, rid, inst, tf):
    """The cached trade-list CSVs, in api/blotter.load_blotter_rows's search order and names."""
    name = f"run{rid}_{inst}_{tf}.csv"
    return [os.path.join(root, "blotters", name),
            os.path.join(os.path.dirname(root), "Trading", "ENGUQ_DB", "blotters", name)]


def read_blotter_all(root, rid, inst, tf):
    """(ALL rows as dicts, path) from the first cached CSV that has any, else (None, None). Never capped."""
    for pth in blotter_paths(root, rid, inst, tf):
        if os.path.isfile(pth):
            with open(pth, newline="", encoding="utf-8") as f:
                rows = [dict(r) for r in csv.DictReader(f)]
            if rows:
                return rows, pth
    return None, None


def regen_blotter(root, rid, d, log=_QUIET):
    """Rebuild a missing trade list through api.blotter (the same payload the web builds) and cache it there as it
    does. (rows, None) on success, (None, reason) when it cannot be done. Slow: it re-runs the champion."""
    if d.get("cost_pts") is None:
        return None, "the run recorded no cost, so its trades cannot be rebuilt honestly"
    if not (isinstance(d.get("best_params"), dict) and d["best_params"]):
        return None, "the run saved no champion configuration to rebuild the trades from"
    if not d.get("strategy"):
        return None, "the run names no strategy"
    from api.blotter import load_blotter_rows
    inst, tf = d.get("instrument") or "", d.get("timeframe") or "5m"
    payload = {"run_id": rid, "instrument": inst, "timeframe": tf, "session": d.get("session") or "rth",
               "strategy": d["strategy"], "params": d["best_params"], "cost_pts": float(d["cost_pts"]),
               "mult": run_mult(d) or 20.0, "date_from": d.get("date_from") or None, "date_to": d.get("date_to") or None,
               "source": d.get("data_source") or None}
    res = load_blotter_rows(root, payload, log)
    if not res.get("ok"):
        return None, str(res.get("error") or "regeneration failed")
    rows, _ = read_blotter_all(root, rid, inst, tf)       # the full cached copy, never the capped reply
    if rows is None:
        if res.get("capped"):
            return None, "rebuilt, but the trade list could not be cached and the reply is capped"
        rows = res.get("rows") or []
    return (rows, None) if rows else (None, "the champion re-run produced no trades")


# ── price series ─────────────────────────────────────────────────────────────────────────────
def _tf_minutes(tf):
    m = re.fullmatch(r"(\d+)\s*([smhdw])", str(tf or "").strip().lower())
    if not m:
        return 10 ** 6
    return int(m.group(1)) * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440, "w": 10080}[m.group(2)]


def _nearest(masters, tf):
    """The master whose timeframe is the run's, else the closest one (coarser wins a tie: fewer rows to read)."""
    want = _tf_minutes(tf)
    return min(masters, key=lambda m: (abs(_tf_minutes(m.get("timeframe")) - want),
                                       -_tf_minutes(m.get("timeframe")))) if masters else None


def choose_master(masters, inst, tf, data_source=None):
    """(registry row, plain-words reason or None). masters = the registry's list of master rows."""
    rth = [m for m in masters if str(m.get("instrument")) == str(inst) and str(m.get("session", "")).lower() == "rth"]
    adj = [m for m in rth if str(m.get("source")) == "db_adj_rth"]
    if adj:   # a rolling future: the back-adjusted master, at the run's timeframe if there is one
        same = [m for m in adj if str(m.get("timeframe")) == str(tf)]
        return (same or [_nearest(adj, tf)])[0], None
    # no rolls: the master the run itself was made on, then split-adjusted stock bars, then any plain RTH master
    def pick(pool):
        for pref in ((lambda m: str(m.get("source")) == str(data_source or "\0")),
                     (lambda m: str(m.get("source")) == "alpaca_split_rth"),
                     (lambda m: not str(m.get("source") or "").startswith(("db_adj", "db_fadj")))):
            hit = [m for m in pool if pref(m)]
            if hit:
                return hit
        return []
    same = pick([m for m in rth if str(m.get("timeframe")) == str(tf)])
    if same:
        return same[0], None
    other = pick(rth)
    if other:
        return _nearest(other, tf), None
    return None, "no RTH price master for %s in the registry, so the buy-and-hold twin cannot be built" % (inst or "?")


class MasterCloses:
    """Session closes from the master registry. Each master is read ONCE per process and boiled down to one close per
    session (the last bar of each New York date, as twin_163.py's groupby(...).last()); a run's window is then a slice
    of that, so a pass over hundreds of runs does not re-read a 300,000-bar CSV hundreds of times."""
    def __init__(self):
        self._daily = {}

    def __call__(self, inst, tf, date_from, date_to, data_source=None):
        """{closes, master, adjusted, rolls} or {why}."""
        import pandas as pd
        from augur_engine.data import list_masters, load_master_arrays
        m, why = choose_master(list_masters(), inst, tf, data_source)
        if m is None:
            return {"why": why}
        fn = m.get("filename")
        if fn not in self._daily:
            try:
                A = load_master_arrays(m)
                ix = pd.DatetimeIndex(A["index"])
                ix = ix.tz_localize(None) if ix.tz is not None else ix      # New York wall-clock, as twin_163.py
                bars = pd.Series(A["close"], index=ix)
                self._daily[fn] = bars.groupby(ix.normalize()).last()
            except Exception as e:
                return {"why": "the price master %s failed to load: %s: %s" % (m.get("name"), type(e).__name__, e)}
        daily = self._daily[fn]
        if date_from:       # load_master_arrays's own window rule: from date_from's midnight, through all of date_to
            daily = daily[daily.index >= pd.Timestamp(date_from)]
        if date_to:
            daily = daily[daily.index <= pd.Timestamp(date_to)]
        if not len(daily):
            return {"why": "the price master %s has no sessions in the run's window" % m.get("name")}
        src = str(m.get("source") or "")
        return {"closes": daily, "master": "%s [%s]" % (m.get("name") or fn, src),
                "adjusted": src == "db_adj_rth", "rolls": src == "db_adj_rth"}


# ── one run -> one entry ─────────────────────────────────────────────────────────────────────
def _day(x):
    return str(x)[:10] if x else None


_USD_RE = re.compile(r"^PNL_UNITS\s*=\s*['\"]usd['\"]", re.M | re.I)


def pnl_in_dollars(root, strategy):
    """True when the run's strategy file reports P&L in DOLLARS (PNL_UNITS = "usd": NQDIP / ETFDIP size every trade to a
    fixed notional). Its blotter's pnl_pts column then holds dollars and its contracts per trade vary, so one row is not
    one lot and a constant-lot twin compares the wrong things (the 10-09 dry run read DIP #424 at 15.8x its twin)."""
    name = os.path.basename(str(strategy or ""))
    if not name:
        return False
    try:
        with open(os.path.join(root, "augur_strategies", name), encoding="utf-8", errors="replace") as f:
            return bool(_USD_RE.search(f.read()))
    except OSError:
        return False


def build_entry(rid, d, root, closes_for, regen=None, curve_points=CURVE_POINTS):
    """The exposure entry for one single-strategy run doc `d`, or {"why": ...}. regen(rid, d) -> (rows, reason) is
    called only for a run with no cached trade list, and only when the caller passes it (the CLI's --regen)."""
    inst, tf = d.get("instrument") or "", d.get("timeframe") or "5m"
    a, b = _day(d.get("date_from")), _day(d.get("date_to"))
    rows, _ = read_blotter_all(root, rid, inst, tf)
    if rows is None:
        why = "no saved trade list"
        if regen is not None:
            rows, reason = regen(rid, d)
            if rows is None:
                return {"why": "%s (rebuild failed: %s)" % (why, reason)}
        else:
            return {"why": why}
    c = closes_for(inst, tf, a, b, d.get("data_source"))
    if c.get("why"):
        pts = sum(float(r["pnl_pts"]) for r in rows if str(r.get("pnl_pts", "")).strip() not in ("", "nan"))
        return {"why": c["why"], "n_trades": len(rows), "strat_pts": round(pts, 2), "twin_pts": None, "ratio": None,
                "ratio_why": c["why"], "inst": inst, "tf": tf}
    # an ETH futures run: a trade entered after 18:00 New York belongs to the next trading day (module docstring)
    roll_hour = 18 if (str(d.get("session") or "rth").lower() != "rth" and c.get("rolls")) else None
    e = X.exposure(rows, c["closes"], roll_hour=roll_hour)
    if pnl_in_dollars(root, d.get("strategy")):
        # a fixed-dollar sizer: keep what the session clock measures honestly (time in the market, holds), drop the lots,
        #   the points and the twin - the web shows the why line and no tag
        return {"why": ("this strategy sizes every trade to a fixed dollar amount and reports its result in dollars, so "
                        "counting lots and a constant-lot buy-and-hold twin do not fit it; it holds a position at %.1f%% "
                        "of session closes" % (e.get("in_mkt_pct") or 0.0))
                       + ("" if e.get("hold_med_sessions") is None else
                          ", median hold %s sessions" % e["hold_med_sessions"]),
                "sizing": "fixed dollars", "in_mkt_pct": e.get("in_mkt_pct"),
                "hold_med_sessions": e.get("hold_med_sessions"), "n_trades": e.get("n_trades"),
                "sessions": e.get("sessions"), "window": [a or e["first"], b or e["last"]], "master": c["master"],
                "inst": inst, "tf": tf}
    e["window"] = [a or e["first"], b or e["last"]]
    e["master"] = c["master"]
    e["inst"], e["tf"], e["mult"] = inst, tf, run_mult(d)
    if (e["in_mkt_pct"] or 0) > CURVE_MIN_IN_MKT:
        e["curve"] = json.dumps(X.twin_curve(rows, c["closes"], n=curve_points, roll_hour=roll_hour),
                                separators=(",", ":"))
    return e


# ── the doc, its size, its checks ────────────────────────────────────────────────────────────
def fs_size(v):
    """Firestore's storage size of one value (api/runner.py _fs_value_size's rules): string = UTF-8 bytes + 1, number
    = 8, bool / null = 1, array = its elements, map = key bytes + 1 + value. json.dumps UNDER-counts numbers."""
    if v is None or isinstance(v, bool):
        return 1
    if isinstance(v, (int, float)):
        return 8
    if isinstance(v, str):
        return len(v.encode("utf-8", "replace")) + 1
    if isinstance(v, dict):
        return sum(len(str(k).encode("utf-8", "replace")) + 1 + fs_size(x) for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return sum(fs_size(x) for x in v)
    return len(str(v).encode("utf-8", "replace")) + 1


def doc_bytes(doc):
    return fs_size(doc) + 32 + 200   # the same document-name / per-document allowance api/runner._doc_size uses


def index_entries(doc):
    """A conservative estimate of the doc's Firestore index entries (the cap is 40,000 a document): every field,
    including a map itself, costs 2 (ascending + descending); an array costs 2 plus one per element."""
    def cost(v):
        if isinstance(v, dict):
            return 2 + sum(cost(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return 2 + sum(cost(x) if isinstance(x, (dict, list, tuple)) else 1 for x in v)
        return 2
    return sum(cost(v) for v in doc.values())


def _has_nested_array(v, inside=False):
    if isinstance(v, (list, tuple)):
        return inside or any(_has_nested_array(x, True) for x in v)
    if isinstance(v, dict):
        return any(_has_nested_array(x, inside) for x in v.values())
    return False


def check_doc(doc):
    """Raise ToolError when the doc must not be written; return the numbers otherwise."""
    size, idx = doc_bytes(doc), index_entries(doc)
    if _has_nested_array(doc):
        raise ToolError("the doc holds an array inside an array, which Firestore rejects - store it as a JSON string")
    if size > SIZE_REFUSE:
        raise ToolError("run_exposure would be %s bytes - over the %s refusal line (Firestore's hard cap is "
                        "1,048,576). Nothing written. Drop curves or split the table." % (f"{size:,}", f"{SIZE_REFUSE:,}"))
    if idx > INDEX_REFUSE:
        raise ToolError("run_exposure would need about %s index entries - over the %s refusal line (Firestore's "
                        "hard cap is 40,000 a document). Nothing written." % (f"{idx:,}", f"{INDEX_REFUSE:,}"))
    return {"bytes": size, "index_entries": idx, "warn": size > SIZE_WARN or idx > INDEX_WARN}


def merge_doc(existing, new_runs, frm):
    """The doc to write: the entries already there stay unless this pass re-did that run."""
    runs = dict((existing or {}).get("runs") or {})
    runs.update(new_runs)
    return {"v": VERSION, "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_by": frm or "(dry)", "runs": runs}


# ── the pass ─────────────────────────────────────────────────────────────────────────────────
def compute_pass(docs, root, closes_for, regen=None, out=print):
    """({str(id): entry}, [skipped notes]) for the fetched run docs. A run that cannot be measured still gets its
    {"why": ...} entry; a book or a missing run gets none and a note."""
    entries, notes = {}, []
    for rid in sorted(docs):
        d = docs[rid]
        if d is None:
            notes.append("#%s: no such run in Firestore - skipped" % rid)
            continue
        if is_book(d):
            notes.append("#%s: a book (pools several strategies, no single trade list) - skipped" % rid)
            continue
        try:
            entries[str(rid)] = build_entry(rid, d, root, closes_for, regen)
        except Exception as e:   # one bad run must not sink the pass
            entries[str(rid)] = {"why": "exposure failed: %s: %s" % (type(e).__name__, e)}
    return entries, notes


def _f(x, spec, dash="-"):
    return dash if x is None else format(x, spec)


def print_table(entries, out=print):
    out("%-6s %-5s %-4s %-23s %7s %7s %8s %7s %5s %7s %11s %11s %7s  %s" % (
        "run", "inst", "tf", "window", "trades", "inMkt%", "lotsAll", "lotsIn", "max", "holdMed", "strat_pts",
        "twin_pts", "ratio", "master / note"))
    for rid in sorted(entries, key=lambda k: int(k)):
        e = entries[rid]
        if "in_mkt_pct" not in e or e.get("why"):
            out("%-6s %-5s %-4s %-23s %7s %7s %8s %7s %5s %7s %11s %11s %7s  %s" % (
                rid, e.get("inst", "-"), e.get("tf", "-"), "-", _f(e.get("n_trades"), "d"),
                _f(e.get("in_mkt_pct"), ".1f"), "-", "-", "-", _f(e.get("hold_med_sessions"), ".1f"),
                _f(e.get("strat_pts"), ",.0f"), "-", "-", e.get("why")))
            continue
        note = e["master"] + ("" if e.get("ratio") is not None else "  [ratio null: %s]" % e.get("ratio_why"))
        if "curve" in e:
            note += "  +curve"
        out("%-6s %-5s %-4s %-23s %7d %7.1f %8.2f %7.2f %5d %7s %11s %11s %7s  %s" % (
            rid, e["inst"], e["tf"], "%s..%s" % tuple(e["window"]), e["n_trades"], e["in_mkt_pct"], e["lots_mean_all"],
            e["lots_mean_in"], e["lots_max"], _f(e["hold_med_sessions"], ".1f"), _f(e["strat_pts"], ",.0f"),
            _f(e["twin_pts"], ",.0f"), _f(e["ratio"], ".2f"), note))


def run(args, db, closes_for, regen=None, root=ROOT, out=print):
    """The whole pass; returns (exit code, the doc that was / would be written or None, Reads)."""
    reads = Reads()
    docs = fetch_run_docs(db, None if args.all else sorted(set(args.ids)), reads)
    entries, notes = compute_pass(docs, root, closes_for, regen if args.regen else None, out)
    for n in notes:
        out("note: " + n)
    if not entries:
        out("nothing to write: no measurable single-strategy run in this pass")
        out(reads.line())
        return 1, None, reads
    print_table(entries, out)
    if len(entries) <= 3:
        for rid, e in sorted(entries.items(), key=lambda kv: int(kv[0])):
            shown = dict(e)
            if "curve" in shown:
                shown["curve"] = "<JSON text, %d chars, %d points>" % (len(e["curve"]), e["curve"].count("],[") + 1)
            out("entry %s: %s" % (rid, json.dumps(shown, ensure_ascii=False)))
    holder = {}

    def mutate(cur):
        reads.meta += 1
        doc = merge_doc(cur, entries, args.frm)
        holder["info"] = check_doc(doc)
        return doc

    ref = exposure_ref(db)
    new = mutate(rw._read(ref)) if args.dry else rw._apply(db, ref, mutate)
    info = holder["info"]
    out("doc users/%s/meta/%s: %d run entries, %s bytes by Firestore's size rules (json %s), ~%s index entries%s" % (
        rw.UID, DOC_ID, len(new["runs"]), f"{info['bytes']:,}", f"{len(json.dumps(new)):,}",
        f"{info['index_entries']:,}", "  [WARN: past the soft line, plan to trim]" if info["warn"] else ""))
    out(reads.line())
    out("--dry: wrote nothing" if args.dry else "wrote %d entr(ies) by %s" % (len(entries), args.frm))
    return 0, new, reads


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--ids", nargs="+", type=int, help="run numbers to measure")
    sel.add_argument("--all", action="store_true", help="every run on the board (books are skipped)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry", action="store_true", help="print the table + the doc size; write nothing")
    mode.add_argument("--write", action="store_true", help="merge the entries into the Firestore doc")
    ap.add_argument("--regen", action="store_true", help="rebuild a MISSING trade list through api.blotter (slow)")
    ap.add_argument("--from", dest="frm", help="the lane writing this (required with --write)")
    ap.add_argument("--root", default=ROOT, help="where blotters/ lives (default: this checkout)")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.write and not args.frm:
        ap.error("--write needs --from <LANE>")
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except Exception:
            pass
    code = 1
    try:
        db = rw.real_client()
        root = os.path.abspath(args.root)
        code, _, _ = run(args, db, MasterCloses(), lambda rid, d: regen_blotter(root, rid, d), root)
    except ToolError as e:
        print("error: %s" % e, file=sys.stderr)
    # the SDK returns only after the commit, so leave now: the gRPC channel's own shutdown wait otherwise holds the
    #   process open for a minute or more (same as runboard_watch.py)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
