#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GUARD r1 - a monthly cold check of the paper record (lane PAPER-NT8; MANAGER inbox #54, 2026-10-05).

WHAT IT DOES. At a month-end cut-off it reads the paper pipeline's forward record READ-ONLY (users/<uid>/paper_bundle,
the compact copy of every paper_trades doc, and the nightly users/<uid>/paper_reports docs), rebuilds each of the 13
registered legs COLD on its pinned master through the paper pipeline's own trade extraction (api.paper.run_shadow with
the master pinned and the capture tail removed), and checks, per leg: >= 99% of forward trades on the same bars within
the price band (>= 95% exact), zero unexplained missing / extra trades, zero post-close changes; and per line: stored
dollars = the sum of its legs within $0.01, and the VT multiplier recomputed cold.

THE BAR IS docs/GUARD_R1_PREREG.md, written and shipped before any record was read. Every constant below is mirrored in
that file's JSON block and tests/test_guard_r1.py fails if the two drift. Read the prereg before judging the code.

NEVER PRINTS a line's cumulative P&L, ROC or Sortino, and never stores one: counts, percentages, price differences in
points, dollar DIFFERENCES between two stored figures, trade ids. The one exception is cold_<cutoff>.json, which holds the
cold trade rows of a NON-PASSING leg only (the cold reference its forward read is computed from until it passes).

WRITES: stdout and one JSON under C:\\EdgeLog\\guard\\. Firestore is wrapped read-only; nothing here touches the runner,
NinjaTrader, a live strategy or a master.

    python tools/guard_r1.py --dry-run                    # latest month-end, not the binding read
    python tools/guard_r1.py --cutoff 2026-09-30 --dry-run
    python tools/guard_r1.py --cutoff 2026-10-30          # the first binding read

Run it from the SHARED checkout (a worktree has no master registry and no serviceAccount.json; BACKTEST_SPEED.md rule 3).
Exit code: 0 all PASS (or NO TRADES), 1 any FAIL, 2 no FAIL but something INCOMPLETE.
"""
import argparse
import bisect
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The engine, the paper pipeline and the master registry normally come from this checkout. A worktree has no master
# registry, so GUARD_R1_ENGINE_ROOT may point at the shared checkout while the harness file itself stays in the worktree.
ENGINE_ROOT = os.environ.get("GUARD_R1_ENGINE_ROOT") or ROOT
for _p in (ROOT, ENGINE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
GUARD_DIR = r"C:\EdgeLog\guard"
PREREG_PATH = os.path.join(ROOT, "docs", "GUARD_R1_PREREG.md")
SHARED_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"

# ---------------------------------------------------------------------------------------------------------------
# CONSTANTS - mirrored in docs/GUARD_R1_PREREG.md section 11 (tests/test_guard_r1.py pins them equal)
# ---------------------------------------------------------------------------------------------------------------
VERSION = "GUARD_R1_v1"
FIRST_BINDING_CUTOFF = "2026-10-30"
HISTORY_FROM = "2010-06-07"
PAPER_START = "2026-08-11"                       # api/paper.py PAPER_START (a test pins it)
BAND_PTS = {"NQ": 1.0, "ES": 0.5}
EXACT_TOL = {"px": 1e-06, "size": 1e-06, "pnl_usd": 0.01}
BAND_SIZE_TOL = 1e-4
PNL_BAND_FLOOR_USD = 0.01
IN_BAND_MIN = 0.99
EXACT_MIN = 0.95
UNEXPLAINED_MISSING_MAX = 0
UNEXPLAINED_EXTRA_MAX = 0
POST_CLOSE_CHANGES_MAX = 0
LINE_TOL_USD = 0.01
VT_MULTIPLIER_SLACK = 0.055
EXITDAY_CUTOVER = "2026-10-02"
VT_FIRST_DAY = "2026-09-30"
LINE_FROM = {"book": "2026-09-28", "book_shadow": "2026-09-29", "book_shadow_q4": "2026-10-01",
             "book_shadow_orb314": "2026-10-01", "book_shadow_orb239": "2026-10-01", "book_shadow_noise125": "2026-10-06"}

# (leg key, pinned source, max contracts per trade for the dollar band)
LEGS = [
    ("ORB", "db_adj_rth", 1),
    ("ENGUQ_335", "db_adj_eth", 1),
    ("TTM_299_SSOF2", "db_adj_rth", 7),
    ("NOISE_422", "db_noadj_rth", 1),
    ("TTM_458_KEEL", "db_noadj_rth", 7),
    ("ORB_R6", "db_adj_rth", 1),
    ("ENGUQ_335_S1", "db_adj_eth", 1),
    ("ORB_239", "db_adj_rth", 1),
    ("DIP_ES_452", "db_noadj_rth", 17),
    ("DIP_NQ_433", "db_noadj_rth", 5),
    ("ORB_257", "db_adj_rth", 1),
    ("ENGUQ_335_S2", "db_adj_eth", 1),
    ("NOISE_304", "db_noadj_rth", 1),
]
LEG_KEYS = [k for k, _, _ in LEGS]
PINNED = {k: s for k, s, _ in LEGS}
N_CONTRACTS = {k: n for k, _, n in LEGS}

LINES = {
    "book": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_458_KEEL": 1.0, "NOISE_422": 1.0},
    "book_shadow_q4": {"ORB_R6": 1.0, "ENGUQ_335_S1": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow_orb314": {"ORB_R6": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow_orb239": {"ORB_239": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
    "book_shadow_noise125": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.25},
    "book_shadow_vt": {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0},
}
SUM_LINES = [k for k in LINES if k != "book_shadow_vt"]

# the two warnings a cold run (no capture tail) is expected to raise; anything else is a cold failure
_EXPECTED_COLD_WARNINGS = ("10s data file missing/empty", "zero fresh bars appended")

TIMEFRAME_SECONDS = {"1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800, "60m": 3600}


def constants_dict():
    """The constants block exactly as docs/GUARD_R1_PREREG.md section 11 prints it."""
    return {
        "version": VERSION,
        "first_binding_cutoff": FIRST_BINDING_CUTOFF,
        "history_from": HISTORY_FROM,
        "band_pts": dict(BAND_PTS),
        "exact_tol": dict(EXACT_TOL),
        "band_size_tol": BAND_SIZE_TOL,
        "pnl_band_floor_usd": PNL_BAND_FLOOR_USD,
        "in_band_min": IN_BAND_MIN,
        "exact_min": EXACT_MIN,
        "unexplained_missing_max": UNEXPLAINED_MISSING_MAX,
        "unexplained_extra_max": UNEXPLAINED_EXTRA_MAX,
        "post_close_changes_max": POST_CLOSE_CHANGES_MAX,
        "line_tol_usd": LINE_TOL_USD,
        "vt_multiplier_slack": VT_MULTIPLIER_SLACK,
        "exitday_cutover": EXITDAY_CUTOVER,
        "vt_first_day": VT_FIRST_DAY,
        "line_from": dict(LINE_FROM),
        "legs": [{"key": k, "pinned_source": s, "n_contracts": n} for k, s, n in LEGS],
        "lines": {k: dict(v) for k, v in LINES.items()},
    }


def prereg_constants(path=None):
    """The JSON constants block parsed out of the prereg file."""
    with open(path or PREREG_PATH, "r", encoding="utf-8") as f:
        s = f.read()
    m = re.search(r"GUARD_R1_CONSTANTS_BEGIN -->\s*```json\n(.*?)```", s, re.S)
    if not m:
        raise ValueError("no constants block in the prereg")
    return json.loads(m.group(1))


def prereg_sha256(path=None):
    with open(path or PREREG_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------------------------
def _et_date(unix):
    import pandas as pd
    return pd.Timestamp(int(unix), unit="s", tz="UTC").tz_convert("US/Eastern").date()


def _to_date(d):
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, dt.date):
        return d
    return dt.date.fromisoformat(str(d)[:10])


def _cutoff_end_unix(cutoff):
    """Unix second of 16:00 US/Eastern on the cut-off day: the earliest the nightly run could have closed it."""
    import pandas as pd
    return int(pd.Timestamp(f"{_to_date(cutoff).isoformat()} 16:00:00", tz="US/Eastern").timestamp())


def default_cutoff(today=None, is_session=None):
    """Last trading day of the latest month that ended strictly before `today`."""
    today = _to_date(today or dt.date.today())
    d = today.replace(day=1) - dt.timedelta(days=1)
    if is_session is None:
        try:
            from api.market_calendar import is_session as _is
            is_session = _is
        except Exception:
            is_session = lambda x: x.weekday() < 5  # noqa: E731
    while not is_session(d):
        d -= dt.timedelta(days=1)
    return d


def trade_id(leg, entry_unix):
    return f"pt_{leg}_{int(entry_unix)}"


# ---------------------------------------------------------------------------------------------------------------
# read-only Firestore
# ---------------------------------------------------------------------------------------------------------------
class ReadOnlyViolation(Exception):
    pass


class _ROSnap:
    def __init__(self, snap, counter):
        self._s = snap
        self._c = counter

    @property
    def exists(self):
        return self._s.exists

    @property
    def id(self):
        return self._s.id

    def to_dict(self):
        return self._s.to_dict()


class _RODoc:
    def __init__(self, ref, counter):
        self._r = ref
        self._c = counter

    def get(self):
        self._c[0] += 1
        return _ROSnap(self._r.get(), self._c)

    def collection(self, name):
        return _ROColl(self._r.collection(name), self._c)

    def __getattr__(self, name):
        raise ReadOnlyViolation(f"GUARD r1 is read-only: document.{name} is not available")


class _ROColl:
    def __init__(self, ref, counter):
        self._r = ref
        self._c = counter

    def document(self, doc_id):
        return _RODoc(self._r.document(doc_id), self._c)

    def stream(self):
        for s in self._r.stream():
            self._c[0] += 1
            yield _ROSnap(s, self._c)

    def __getattr__(self, name):
        raise ReadOnlyViolation(f"GUARD r1 is read-only: collection.{name} is not available")


class ReadOnlyDB:
    """A Firestore client that can only collection().document().get() / .stream(); every write method raises."""

    def __init__(self, inner):
        self._inner = inner
        self.reads = [0]

    def collection(self, name):
        return _ROColl(self._inner.collection(name), self.reads)

    def __getattr__(self, name):
        raise ReadOnlyViolation(f"GUARD r1 is read-only: client.{name} is not available")


class FirestoreSource:
    """Pulls the paper record. `db` is a ReadOnlyDB (or anything with the same read surface)."""

    def __init__(self, db, uid=UID):
        self.db = db
        self.uid = uid

    def reads(self):
        return int(getattr(self.db, "reads", [0])[0])

    def paper_trades(self):
        """(rows, meta): the bundle if it is whole, else every trade doc. Rows are dicts shaped like trade docs."""
        from api import paper_bundle as pb
        rows, meta = pb.read_bundle(self.db, self.uid)
        if rows is not None:
            return rows, {"via": "bundle", "gen": meta.get("gen"), "n_total": meta.get("n_total"), "parts": meta.get("parts")}
        out = []
        for s in self.db.collection("users").document(self.uid).collection("paper_trades").stream():
            d = s.to_dict() or {}
            d["id"] = s.id
            out.append(d)
        return out, {"via": "direct", "gen": None, "n_total": len(out), "parts": None}

    def report(self, day_iso):
        s = self.db.collection("users").document(self.uid).collection("paper_reports").document(day_iso).get()
        return (s.to_dict() or {}) if s.exists else None


# ---------------------------------------------------------------------------------------------------------------
# normalised trades
# ---------------------------------------------------------------------------------------------------------------
def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def norm_paper_row(row, mult):
    """A trade doc / bundle row -> the plain dict the comparison uses, or None if it has no entry time."""
    et = row.get("entryTime")
    if et is None:
        return None
    entry_unix = int(et)
    exit_unix = int(row["exitTime"]) if row.get("exitTime") is not None else None
    pnl_usd = _f(row.get("pnl_usd"), 0.0)
    pnl_pts = _f(row.get("pnl_pts"), 0.0)
    size = _f(row.get("size"))
    if size is None:
        size = (pnl_usd / (pnl_pts * float(mult))) if abs(pnl_pts) > 1e-9 and float(mult) else 1.0
    is_open = bool(row.get("open"))
    cd = row.get("close_day")
    if cd is None and not is_open and exit_unix is not None:
        from api import paper_exitday as xd
        import pandas as pd
        cd = xd.close_day(pd.Timestamp(exit_unix, unit="s", tz="UTC").tz_convert("US/Eastern")).isoformat()
    return {"id": row.get("id") or trade_id(row.get("leg"), entry_unix), "leg": row.get("leg"),
            "side": int(row.get("side") or 0), "entry_unix": entry_unix, "exit_unix": exit_unix,
            "entry_px": _f(row.get("entry_px")), "exit_px": _f(row.get("exit_px")),
            "size": size, "pnl_pts": pnl_pts, "pnl_usd": pnl_usd, "open": is_open,
            "close_day": None if is_open else cd, "backfill": row.get("backfill"),
            "entry_day": _et_date(entry_unix).isoformat()}


def norm_cold_trade(t, leg_key, offsets=None):
    """A trade dict from api.paper._extract_trades -> the plain dict. `offsets` (BasisOffsets) moves the prices
    of a back-adjusted master onto the paper record's raw basis (prereg section 3)."""
    import pandas as pd
    from api import paper_exitday as xd
    entry_unix = int(pd.Timestamp(t["entry_dt"]).timestamp())
    exit_unix = int(pd.Timestamp(t["exit_dt"]).timestamp())
    ep, xp = _f(t.get("entry_px")), _f(t.get("exit_px"))
    if offsets is not None:
        if ep is not None:
            ep -= offsets.at(entry_unix)
        if xp is not None:
            xp -= offsets.at(exit_unix)
    is_open = bool(t.get("open"))
    return {"id": trade_id(leg_key, entry_unix), "leg": leg_key, "side": int(t.get("side") or 0),
            "entry_unix": entry_unix, "exit_unix": exit_unix, "entry_px": ep, "exit_px": xp,
            "size": _f(t.get("size"), 1.0), "pnl_pts": _f(t.get("pnl_pts"), 0.0), "pnl_usd": _f(t.get("pnl_usd"), 0.0),
            "open": is_open,
            "close_day": None if is_open else xd.close_day(pd.Timestamp(t["exit_dt"])).isoformat(),
            "backfill": None, "entry_day": _et_date(entry_unix).isoformat()}


class BasisOffsets:
    """adj close - noadj close at the last bar common to both masters at or before a time (additive back-adjustment)."""

    def __init__(self, times, offsets):
        self.t = list(times)
        self.o = list(offsets)

    @classmethod
    def zero(cls):
        return cls([], [])

    def at(self, unix):
        if not self.t:
            return 0.0
        i = bisect.bisect_right(self.t, int(unix)) - 1
        return self.o[max(i, 0)]

    @classmethod
    def from_arrays(cls, adj_t, adj_close, noadj_t, noadj_close):
        """Inputs are parallel sequences of Unix seconds and closes."""
        n_map = {int(t): float(c) for t, c in zip(noadj_t, noadj_close)}
        ts, os_ = [], []
        for t, c in zip(adj_t, adj_close):
            t = int(t)
            if t in n_map:
                ts.append(t)
                os_.append(float(c) - n_map[t])
        order = sorted(range(len(ts)), key=lambda i: ts[i])
        return cls([ts[i] for i in order], [os_[i] for i in order])


# ---------------------------------------------------------------------------------------------------------------
# the per-leg comparison (pure)
# ---------------------------------------------------------------------------------------------------------------
def _px_close(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def classify_pair(p, c, *, band, mult, n_contracts):
    """Compare one matched (same leg, entry bar, side) pair. Returns (status, reasons, max_px_diff) with status
    'exact' | 'band' | 'out'. Open-either trades compare on entry only (prereg section 4)."""
    reasons = []
    d_e = None if p["entry_px"] is None or c["entry_px"] is None else abs(p["entry_px"] - c["entry_px"])
    both_closed = not p["open"] and not c["open"]
    d_x = None
    if both_closed and p["exit_px"] is not None and c["exit_px"] is not None:
        d_x = abs(p["exit_px"] - c["exit_px"])
    in_band, exact = True, True
    if d_e is None and not (p["entry_px"] is None and c["entry_px"] is None):
        reasons.append("entry price missing on one side")
        in_band = exact = False
    elif d_e is not None:
        if d_e > band:
            reasons.append(f"entry price differs by {d_e:.4f} pts (band {band})")
            in_band = False
        if d_e > EXACT_TOL["px"]:
            exact = False
    if both_closed:
        if p["exit_unix"] != c["exit_unix"]:
            reasons.append("exit bar differs")
            in_band = exact = False
        if d_x is None and not (p["exit_px"] is None and c["exit_px"] is None):
            reasons.append("exit price missing on one side")
            in_band = exact = False
        elif d_x is not None:
            if d_x > band:
                reasons.append(f"exit price differs by {d_x:.4f} pts (band {band})")
                in_band = False
            if d_x > EXACT_TOL["px"]:
                exact = False
        ds = abs(p["size"] - c["size"])
        if ds > BAND_SIZE_TOL:
            reasons.append(f"size differs by {ds:.4f}")
            in_band = False
        if ds > EXACT_TOL["size"]:
            exact = False
        dp = abs(p["pnl_usd"] - c["pnl_usd"])
        allow = ((d_e or 0.0) + (d_x or 0.0)) * float(mult) * float(n_contracts) * max(p["size"], c["size"], 1e-9) \
            + PNL_BAND_FLOOR_USD
        if dp > allow:
            reasons.append(f"dollars differ by {dp:.2f}, more than the price differences allow ({allow:.2f})")
            in_band = False
        if dp > EXACT_TOL["pnl_usd"]:
            exact = False
    mx = max([x for x in (d_e, d_x) if x is not None], default=0.0)
    if not in_band:
        return "out", reasons, mx
    return ("exact" if exact else "band"), reasons, mx


def _match_window(paper, cold, *, key, mult, n_contracts, band, artifacts, bar_seconds, covered_until_unix):
    """Match one population. Returns the stats dict (counts + id lists). `artifacts` = set of (leg, entry_unix)."""
    cold_by_unix = {}
    for c in cold:
        cold_by_unix.setdefault(c["entry_unix"], c)
    art_days = {_et_date(u).isoformat() for (lg, u) in artifacts if lg == key}
    matched, used = [], set()
    st = {"n_paper": len(paper), "n_cold": len(cold), "uncovered": [], "matched": 0, "exact": 0, "band": 0, "out": 0,
          "open_either": 0, "explained": [], "missing": [], "extra": [], "out_ids": [], "out_detail": [],
          "explained_missing": [], "side_mismatch": [], "band_ids": []}
    eligible = 0
    in_band = 0
    exact = 0
    for p in paper:
        if covered_until_unix is not None and p["entry_unix"] > covered_until_unix:
            st["uncovered"].append(p["id"])
            continue
        c = cold_by_unix.get(p["entry_unix"])
        is_art = (key, p["entry_unix"]) in artifacts
        if c is not None and c["side"] != p["side"]:
            st["side_mismatch"].append(p["id"])
            c = None
        if c is None:
            if is_art:
                st["explained"].append(p["id"])
            else:
                st["extra"].append(p["id"])
                eligible += 1
            continue
        used.add(c["entry_unix"])
        status, reasons, mx = classify_pair(p, c, band=band, mult=mult, n_contracts=n_contracts)
        st["matched"] += 1
        if p["open"] or c["open"]:
            st["open_either"] += 1
        if status == "out" and is_art:
            st["explained"].append(p["id"])
            continue
        eligible += 1
        if status == "out":
            st["out"] += 1
            st["out_ids"].append(p["id"])
            st["out_detail"].append({"id": p["id"], "reasons": reasons, "max_px_diff_pts": round(mx, 4)})
        else:
            in_band += 1
            if status == "exact":
                exact += 1
                st["exact"] += 1
            else:
                st["band"] += 1
                st["band_ids"].append(p["id"])
    for u, c in cold_by_unix.items():
        if u in used:
            continue
        if _et_date(u).isoformat() in art_days:
            st["explained_missing"].append(c["id"])
        else:
            st["missing"].append(c["id"])
    # one-bar-apart pairs among the unexplained (the signature of a stamping shift)
    extra_u = {int(i.rsplit("_", 1)[1]) for i in st["extra"]}
    miss_u = {int(i.rsplit("_", 1)[1]) for i in st["missing"]}
    st["adjacent_pairs"] = sum(1 for u in miss_u if (u - bar_seconds) in extra_u or (u + bar_seconds) in extra_u)
    st["denominator"] = eligible
    st["in_band"] = in_band
    st["exact_n"] = exact
    return st


def compare_leg(leg_key, *, mult, n_contracts, instrument, timeframe, live_from, cutoff, paper, cold,
                master_through_unix, artifacts):
    """Compare one leg's paper record with its cold reference. Pure: lists of normalised trade dicts in."""
    band = BAND_PTS[instrument]
    cutoff_d, live_d = _to_date(cutoff), _to_date(live_from)
    bar_seconds = TIMEFRAME_SECONDS.get(timeframe, 60)

    def window(trades, lo, hi):
        return [t for t in trades if (lo is None or _to_date(t["entry_day"]) >= lo) and _to_date(t["entry_day"]) <= hi]

    paper_fwd = window(paper, live_d, cutoff_d)
    cold_fwd = window(cold, live_d, cutoff_d)
    day_before = live_d - dt.timedelta(days=1)
    paper_bf = [t for t in window(paper, None, min(day_before, cutoff_d)) if t["entry_day"] >= PAPER_START]
    cold_bf = [t for t in window(cold, None, min(day_before, cutoff_d)) if t["entry_day"] >= PAPER_START]

    fwd = _match_window(paper_fwd, cold_fwd, key=leg_key, mult=mult, n_contracts=n_contracts, band=band,
                        artifacts=artifacts, bar_seconds=bar_seconds, covered_until_unix=master_through_unix)
    bf = _match_window(paper_bf, cold_bf, key=leg_key, mult=mult, n_contracts=n_contracts, band=band,
                       artifacts=artifacts, bar_seconds=bar_seconds, covered_until_unix=master_through_unix)

    # the document's own backfill flag must agree with LEG_LIVE_FROM
    flag_bad = [t["id"] for t in paper
                if t.get("backfill") is not None and PAPER_START <= t["entry_day"] <= cutoff_d.isoformat()
                and bool(t["backfill"]) != (_to_date(t["entry_day"]) < live_d)]
    master_short = master_through_unix is not None and _et_date(master_through_unix) < cutoff_d
    out = {"leg": leg_key, "forward": fwd, "backfill": bf, "backfill_flag_mismatch": flag_bad,
           "master_through_unix": master_through_unix, "n_paper_forward": len(paper_fwd), "n_cold_forward": len(cold_fwd)}
    out["master_short_of_cutoff"] = master_short
    return out


def evaluate_leg(res, *, post_close_ids, cold_failed=None, bundle_stale=False):
    """Turn a compare_leg result + the post-close findings into the verdict, the conditions and the defect list."""
    f = res["forward"]
    den = f["denominator"]
    defects = []
    c1 = (f["in_band"] * 100 >= IN_BAND_MIN * 100 * den) if den else True
    c2 = (f["exact_n"] * 100 >= EXACT_MIN * 100 * den) if den else True
    if not c1:
        defects.append({"cond": "C1 in-band", "stat": f"{f['in_band']}/{den} in band (needs >= 99%)", "trade_ids": f["out_ids"],
                        "detail": f["out_detail"]})
    if not c2:
        defects.append({"cond": "C2 exact", "stat": f"{f['exact_n']}/{den} exact (needs >= 95%)",
                        "trade_ids": list(f["band_ids"]) + list(f["out_ids"]), "detail": []})
    if len(f["missing"]) > UNEXPLAINED_MISSING_MAX:
        defects.append({"cond": "C3 missing", "stat": f"{len(f['missing'])} cold trade(s) absent from the paper record",
                        "trade_ids": f["missing"], "detail": [], "adjacent_pairs": f["adjacent_pairs"]})
    if len(f["extra"]) > UNEXPLAINED_EXTRA_MAX:
        defects.append({"cond": "C4 extra", "stat": f"{len(f['extra'])} paper trade(s) absent from the cold reference",
                        "trade_ids": f["extra"], "detail": [], "adjacent_pairs": f["adjacent_pairs"]})
    if f["side_mismatch"]:
        defects.append({"cond": "C4 side", "stat": f"{len(f['side_mismatch'])} trade(s) on the same bar with the opposite side",
                        "trade_ids": f["side_mismatch"], "detail": []})
    if len(post_close_ids) > POST_CLOSE_CHANGES_MAX:
        defects.append({"cond": "C5 post-close", "stat": f"{len(post_close_ids)} closed trade(s) changed after their close day",
                        "trade_ids": list(post_close_ids), "detail": []})
    if res["backfill_flag_mismatch"]:
        defects.append({"cond": "backfill flag", "stat": f"{len(res['backfill_flag_mismatch'])} trade doc(s) whose backfill flag disagrees with LEG_LIVE_FROM",
                        "trade_ids": res["backfill_flag_mismatch"], "detail": []})
    incomplete = []
    if cold_failed:
        incomplete.append(f"cold run failed: {cold_failed}")
    if f["uncovered"]:
        incomplete.append(f"{len(f['uncovered'])} paper trade(s) entered after the cold master's last bar")
    if res["master_short_of_cutoff"]:
        incomplete.append("the pinned master ends before the cut-off")
    if bundle_stale:
        incomplete.append("the paper bundle was written before the cut-off day closed")
    if defects:
        verdict = "FAIL"
    elif incomplete:
        verdict = "INCOMPLETE"
    elif den == 0 and res["n_paper_forward"] == 0 and res["n_cold_forward"] == 0:
        verdict = "NO TRADES"
    elif den == 0:
        verdict = "NO TRADES"          # everything the paper record holds is explained; nothing assessable remains
    else:
        verdict = "PASS"
    return {"verdict": verdict, "defects": defects, "incomplete": incomplete,
            "c1_ok": c1, "c2_ok": c2}


# ---------------------------------------------------------------------------------------------------------------
# post-close changes
# ---------------------------------------------------------------------------------------------------------------
def check_report_vs_docs(reports, paper_by_leg, legs, cutoff, cutover=EXITDAY_CUTOVER):
    """Detector 1: each report day's per-leg money must equal the sum of the leg's CLOSED trade docs closing that day.
    Returns {leg: {"mismatches": [...], "legacy": [...], "days_checked": n}}; legacy = days before the exit-day cut-over."""
    cutoff_d = _to_date(cutoff)
    out = {k: {"mismatches": [], "legacy": [], "days_checked": 0} for k in legs}
    by_leg_day = {}
    for k in legs:
        for t in paper_by_leg.get(k, []):
            if t["open"] or not t.get("close_day"):
                continue
            by_leg_day.setdefault((k, t["close_day"]), []).append(t)
    for day, doc in sorted(reports.items()):
        if _to_date(day) > cutoff_d or not doc:
            continue
        legs_doc = doc.get("legs") or {}
        for k in legs:
            blk = legs_doc.get(k)
            if not isinstance(blk, dict) or "pnl_usd" not in blk:
                continue
            trades = by_leg_day.get((k, day), [])
            doc_sum = sum(t["pnl_usd"] for t in trades)
            delta = _f(blk.get("pnl_usd"), 0.0) - doc_sum
            out[k]["days_checked"] += 1
            if abs(delta) > LINE_TOL_USD:
                rec = {"day": day, "diff_usd": round(delta, 2), "trade_ids": [t["id"] for t in trades]}
                (out[k]["legacy"] if _to_date(day) < _to_date(cutover) else out[k]["mismatches"]).append(rec)
    return out


def trade_digest(t):
    return hashlib.sha1(f"{t['exit_unix']}|{t['exit_px']:.6f}|{t['pnl_usd']:.4f}".encode()).hexdigest()[:16] \
        if t.get("exit_px") is not None else hashlib.sha1(f"{t['exit_unix']}|none|{t['pnl_usd']:.4f}".encode()).hexdigest()[:16]


def make_snapshot(paper_by_leg, legs, cutoff):
    """{trade id: digest} of every CLOSED trade of the given legs that closed on or before the cut-off."""
    cutoff_d = _to_date(cutoff)
    snap = {}
    for k in legs:
        for t in paper_by_leg.get(k, []):
            if t["open"] or not t.get("close_day") or _to_date(t["close_day"]) > cutoff_d:
                continue
            snap[t["id"]] = trade_digest(t)
    return snap


def diff_snapshot(prev, paper_by_leg, legs):
    """Detector 2: trades closed in the previous snapshot that are now different, open or absent.
    Returns {leg: [(trade id, 'changed'|'absent')]}."""
    now = {}
    for k in legs:
        for t in paper_by_leg.get(k, []):
            now[t["id"]] = t
    out = {k: [] for k in legs}
    for tid, dig in (prev or {}).items():
        leg = tid[len("pt_"):].rsplit("_", 1)[0]
        if leg not in out:
            continue
        t = now.get(tid)
        if t is None:
            out[leg].append((tid, "absent"))
        elif t["open"] or t.get("exit_unix") is None or trade_digest(t) != dig:
            out[leg].append((tid, "changed"))
    return out


def load_prior_snapshot(out_dir, cutoff):
    """The newest earlier snapshot (cut-off strictly smaller) in the guard folder, or (None, None)."""
    best = None
    try:
        names = os.listdir(out_dir)
    except OSError:
        return None, None
    cutoff_d = _to_date(cutoff)
    for n in names:
        m = re.match(r"guard_r1_(\d{4}-\d{2}-\d{2})_.*\.json$", n)
        if not m or dt.date.fromisoformat(m.group(1)) >= cutoff_d:
            continue
        key = (m.group(1), n)
        if best is None or key > best[0]:
            best = (key, n)
    if best is None:
        return None, None
    try:
        with open(os.path.join(out_dir, best[1]), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("snapshot"), {"file": best[1], "cutoff": d.get("cutoff")}
    except (OSError, ValueError):
        return None, None


# ---------------------------------------------------------------------------------------------------------------
# lines
# ---------------------------------------------------------------------------------------------------------------
def vt_unrounded(M):
    """api.book_shadow.vt_multipliers without the final rounding (same arithmetic; a test pins the equality)."""
    from api.book_shadow import VT_HI, VT_LO, VT_LOOKBACK, VT_REF
    vol = M.shift(1).rolling(VT_LOOKBACK, min_periods=VT_LOOKBACK).std()
    ref = vol.shift(1).rolling(VT_REF, min_periods=VT_REF // 2).median()
    return (ref / vol).clip(VT_LO, VT_HI).fillna(1.0)


def check_lines(reports, cutoff, *, cold_vt=None, session_days=None):
    """L1 / L1b / L2 / L3 over the report days. `cold_vt` = {day iso: unrounded cold multiplier}.
    `session_days` = callable(start_date, end_date) -> list of dates, to find report days that are missing.
    Returns {line: {"days": n, "defects": [...], "missing_days": [...]}} (dollar DIFFERENCES only)."""
    cutoff_d = _to_date(cutoff)
    out = {}
    for line, w_reg in LINES.items():
        rec = {"days": 0, "defects": [], "missing_days": []}
        start = _to_date(LINE_FROM.get(line, VT_FIRST_DAY if line == "book_shadow_vt" else PAPER_START))
        if session_days is not None:
            for d in session_days(start, cutoff_d):
                if not reports.get(d.isoformat()):
                    rec["missing_days"].append(d.isoformat())
        for day, doc in sorted(reports.items()):
            dd = _to_date(day)
            if not doc or dd > cutoff_d:
                continue
            blk = doc.get(line)
            if not isinstance(blk, dict):
                continue
            legs_doc = doc.get("legs") or {}
            if line == "book_shadow_vt":
                if dd < _to_date(VT_FIRST_DAY):
                    continue
                rec["days"] += 1
                if blk.get("error") or blk.get("multiplier") is None or blk.get("pnl_usd") is None:
                    rec["defects"].append({"day": day, "kind": "L2 no figure", "detail": f"stored line has no number ({str(blk.get('error'))[:80]})"})
                    continue
                book = (doc.get("book") or {})
                diff = _f(blk["pnl_usd"], 0.0) - _f(blk["multiplier"], 0.0) * _f(book.get("pnl_usd"), 0.0)
                if abs(diff) > LINE_TOL_USD:
                    rec["defects"].append({"day": day, "kind": "L2 identity", "diff_usd": round(diff, 2)})
                if cold_vt is not None:
                    cm = cold_vt.get(day)
                    sm = _f(blk["multiplier"])
                    if cm is None:
                        rec["defects"].append({"day": day, "kind": "L3 no cold multiplier"})
                    elif abs(round(cm, 1) - sm) > 1e-9 and abs(cm - sm) > VT_MULTIPLIER_SLACK:
                        rec["defects"].append({"day": day, "kind": "L3 multiplier", "stored": sm, "cold": round(cm, 3)})
                continue
            if "pnl_usd" not in blk:
                continue
            rec["days"] += 1
            w_doc = blk.get("weights") if isinstance(blk.get("weights"), dict) else w_reg
            expected = sum(_f(x, 0.0) * _f((legs_doc.get(k) or {}).get("pnl_usd"), 0.0) for k, x in w_doc.items())
            diff = _f(blk["pnl_usd"], 0.0) - expected
            if abs(diff) > LINE_TOL_USD:
                rec["defects"].append({"day": day, "kind": "L1 sum of legs", "diff_usd": round(diff, 2)})
            if dd >= start and {k: float(v) for k, v in w_doc.items()} != {k: float(v) for k, v in w_reg.items()}:
                rec["defects"].append({"day": day, "kind": "L1b composition", "stored": {k: float(v) for k, v in w_doc.items()},
                                       "registered": dict(w_reg)})
        out[line] = rec
    return out


def line_verdict(rec):
    if rec["defects"]:
        return "FAIL"
    if rec["missing_days"]:
        return "INCOMPLETE"
    if rec["days"] == 0:
        return "NO DAYS"
    return "PASS"


def lines_read_source(line_res, leg_res):
    """Which source a line's forward read must use: the paper record only when its legs are PASS / NO TRADES and
    its own checks passed; otherwise the cold reference (prereg section 8)."""
    out = {}
    for line, legs in LINES.items():
        bad_legs = [k for k in legs if leg_res.get(k, {}).get("verdict") not in ("PASS", "NO TRADES")]
        lv = line_verdict(line_res.get(line, {"defects": [], "missing_days": [], "days": 0}))
        ok = not bad_legs and lv in ("PASS", "NO DAYS")
        out[line] = {"source": "paper record" if ok else "COLD REFERENCE (until it passes)", "legs_not_clean": bad_legs,
                     "line_verdict": lv}
    return out


# ---------------------------------------------------------------------------------------------------------------
# cold rebuild (needs the shared checkout: master registry, engine)
# ---------------------------------------------------------------------------------------------------------------
class patched_pipeline:
    """Context manager: pin the master and remove the capture tail inside api.paper for the duration of a call,
    restoring both in a finally. `paper_mod` is api.paper in a real run and a stand-in in tests."""

    def __init__(self, paper_mod, master):
        self.p, self.master = paper_mod, master
        self._saved = None

    def __enter__(self):
        self._saved = (self.p.find_master, self.p._load_fresh_ticks)
        master = self.master
        self.p.find_master = lambda instrument, timeframe, session=None, *a, **k: master
        self.p._load_fresh_ticks = lambda instrument="NQ": (None, "GUARD r1 cold run: capture tail removed")
        return self

    def __exit__(self, *exc):
        self.p.find_master, self.p._load_fresh_ticks = self._saved
        return False


def run_cold_leg(paper_mod, leg, master, cutoff):
    """Run api.paper.run_shadow on the pinned master with no capture tail, full history. Returns
    (extracted trade dicts, warnings, ran_ok)."""
    leg = dict(leg)
    leg["history_from"] = HISTORY_FROM
    with patched_pipeline(paper_mod, master):
        r = paper_mod.run_shadow(leg, _to_date(cutoff))
    return list(r.get("trades") or []), list(r.get("warnings") or []), bool(r.get("ran_ok"))


def real_cold_provider(cutoff, only=None):
    """callable(leg_key) -> {"trades": [...normalised], "master_through_unix", "master": {...}, "failed": str|None}"""
    import numpy as np
    import pandas as pd
    from api import paper
    from augur_engine import data
    legs = {l["key"]: l for l in paper.PAPER_LEGS}
    cache = {}
    through_cache = {}

    def provider(key):
        leg = legs[key]
        pinned = PINNED[key]
        master = data.find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"), pinned)
        if master is None:
            return {"trades": [], "master_through_unix": None, "master": None,
                    "failed": f"no master registered for {leg['instrument']} {leg['timeframe']} {leg.get('session')} source {pinned}"}
        path = os.path.join(data.UPLOADS, master["filename"])
        st = os.stat(path)
        if master["filename"] not in through_cache:
            tail = data.load_master_arrays(master, date_from=(_to_date(cutoff) - dt.timedelta(days=45)).isoformat())
            idx = tail["index"]
            through_cache[master["filename"]] = (int(pd.Timestamp(idx[-1]).timestamp()) if len(idx) else None,
                                                 str(idx[-1]) if len(idx) else None)
        through, last_bar = through_cache[master["filename"]]
        info = {"source": pinned, "filename": master["filename"], "size": st.st_size, "mtime": int(st.st_mtime),
                "last_bar_et": last_bar}
        offsets = BasisOffsets.zero()
        if pinned.startswith("db_adj_"):
            n_src = pinned.replace("db_adj_", "db_noadj_", 1)
            nm = data.find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"), n_src)
            if nm is None:
                return {"trades": [], "master_through_unix": through, "master": info,
                        "failed": f"no sibling no-adjust master ({n_src}) to put prices on the paper basis"}
            ck = (master["filename"], nm["filename"])
            if ck not in cache:
                lo = (pd.Timestamp(PAPER_START) - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
                a = data.load_master_arrays(master, date_from=lo)
                n = data.load_master_arrays(nm, date_from=lo)
                to_u = lambda ix: (pd.DatetimeIndex(ix).asi8 // 10 ** 9).tolist()   # noqa: E731
                cache[ck] = BasisOffsets.from_arrays(to_u(a["index"]), a["close"], to_u(n["index"]), n["close"])
            offsets = cache[ck]
            info["noadj_sibling"] = nm["filename"]
        raw, warns, ok = run_cold_leg(paper, leg, master, cutoff)
        other = [w for w in warns if not any(w.startswith(p) for p in _EXPECTED_COLD_WARNINGS)]
        failed = None
        if not ok or other:
            failed = "; ".join(other)[:300] or "run_shadow returned ran_ok false"
        trades = [norm_cold_trade(t, key, offsets) for t in raw]
        return {"trades": trades, "master_through_unix": through, "master": info, "failed": failed}

    return provider


def real_vt_provider(cutoff):
    """callable(first_day) -> {day iso: unrounded cold multiplier} from #463's pinned job legs."""
    import pandas as pd
    from api import book_shadow as bs

    def provider(first_day):
        start = (pd.Timestamp(first_day) - pd.Timedelta(days=bs.VT_WARMUP_DAYS)).strftime("%Y-%m-%d")
        M = bs.book463_valued_daily(start, _to_date(cutoff).isoformat())
        r = vt_unrounded(M)
        return {d.date().isoformat(): float(v) for d, v in r.items()}

    return provider


def config_drift_notes(paper_legs, book463_legs):
    """NOTE lines: the paper leg's configuration versus the registered BOOK #463 job leg of the same strategy file."""
    notes = []
    by_strategy = {l["strategy"]: l for l in book463_legs}
    for key in ("ORB", "ENGUQ_335", "TTM_299_SSOF2", "NOISE_422"):
        pl = next((l for l in paper_legs if l["key"] == key), None)
        if pl is None:
            continue
        reg = by_strategy.get(pl["strategy"])
        if reg is None:
            notes.append(f"{key}: strategy {pl['strategy']} is not in BOOK463_LEGS")
            continue
        diffs = []
        for fld in ("instrument", "timeframe", "session", "cost_pts", "mult"):
            a, b = pl.get(fld), reg.get(fld)
            if fld in ("cost_pts", "mult"):
                same = _f(a) == _f(b)
            else:
                same = a == b
            if not same:
                diffs.append(f"{fld}: paper {a} vs registered {b}")
        pp, rp = pl.get("params") or {}, reg.get("params") or {}
        for k in sorted(set(pp) | set(rp)):
            if pp.get(k) != rp.get(k):
                diffs.append(f"param {k}: paper {pp.get(k)} vs registered {rp.get(k)}")
        if diffs:
            notes.append(f"CONFIG DRIFT {key} vs BOOK463_LEGS: " + "; ".join(diffs))
    return notes


# ---------------------------------------------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------------------------------------------
def run_guard(cutoff, *, dry_run, source, cold_provider, vt_provider, leg_info, artifacts, out_dir=None,
              session_days=None, only=None, prior_snapshot=None, notes=None, now=None, git_rev=None, prereg_hash=None):
    """The whole check. Everything external is injected (source, cold_provider, vt_provider, leg_info, ...) so the
    tests run on synthetic data. Returns the result dict (no P&L level anywhere in it)."""
    cutoff_d = _to_date(cutoff)
    legs_run = [k for k in LEG_KEYS if (not only or k in only)]
    started = time.time() if now is None else now
    rows, bmeta = source.paper_trades()
    paper_by_leg = {k: [] for k in LEG_KEYS}
    for r in rows:
        k = r.get("leg")
        if k in paper_by_leg:
            nt = norm_paper_row(r, leg_info[k]["mult"])
            if nt is not None:
                paper_by_leg[k].append(nt)
    bundle_stale = False
    if bmeta.get("gen") is not None:
        try:
            bundle_stale = int(float(bmeta["gen"])) < _cutoff_end_unix(cutoff_d)
        except (TypeError, ValueError):
            bundle_stale = True

    # reports: every weekday from PAPER_START to the cut-off (one read each)
    reports = {}
    d = _to_date(PAPER_START)
    while d <= cutoff_d:
        if d.weekday() < 5:
            doc = source.report(d.isoformat())
            if doc:
                reports[d.isoformat()] = doc
        d += dt.timedelta(days=1)

    # post-close detectors
    rpt = check_report_vs_docs(reports, paper_by_leg, legs_run, cutoff_d)
    snap_prev, snap_meta = (prior_snapshot if prior_snapshot is not None else (None, None))
    snap_diff = diff_snapshot(snap_prev, paper_by_leg, legs_run) if snap_prev else {k: [] for k in legs_run}

    leg_res, leg_detail = {}, {}
    cold_rows_for_failures = {}
    for k in legs_run:
        info = leg_info[k]
        cold = cold_provider(k)
        post_ids = []
        for m in rpt[k]["mismatches"]:
            post_ids.extend(m["trade_ids"] or [f"report {m['day']}"])
        post_ids.extend(tid for tid, _ in snap_diff.get(k, []))
        res = compare_leg(k, mult=info["mult"], n_contracts=N_CONTRACTS[k], instrument=info["instrument"],
                          timeframe=info["timeframe"], live_from=info["live_from"], cutoff=cutoff_d,
                          paper=paper_by_leg[k], cold=cold["trades"],
                          master_through_unix=cold.get("master_through_unix"), artifacts=artifacts)
        ev = evaluate_leg(res, post_close_ids=sorted(set(post_ids)), cold_failed=cold.get("failed"), bundle_stale=bundle_stale)
        leg_res[k] = {"verdict": ev["verdict"]}
        leg_detail[k] = {"verdict": ev["verdict"], "defects": ev["defects"], "incomplete": ev["incomplete"],
                         "pinned_source": PINNED[k], "master": cold.get("master"),
                         "instrument": info["instrument"], "timeframe": info["timeframe"], "session": info.get("session"),
                         "live_from": info["live_from"], "counts": _counts(res["forward"], res),
                         "backfill_info": _bf_counts(res["backfill"]),
                         "post_close": {"report_vs_docs": rpt[k]["mismatches"], "snapshot_diff": snap_diff.get(k, []),
                                        "report_days_checked": rpt[k]["days_checked"], "legacy_days_mismatched": len(rpt[k]["legacy"])}}
        if ev["verdict"] in ("FAIL", "INCOMPLETE"):
            cold_rows_for_failures[k] = [{kk: t[kk] for kk in ("id", "side", "entry_unix", "exit_unix", "entry_px", "exit_px",
                                                              "size", "pnl_pts", "pnl_usd", "open", "close_day")}
                                         for t in cold["trades"]]

    cold_vt = None
    vt_error = None
    try:
        first = VT_FIRST_DAY
        cold_vt = vt_provider(first) if vt_provider else None
    except Exception as e:      # the cold VT build failing is INCOMPLETE for the VT line, not a crash
        vt_error = f"{type(e).__name__}: {e}"
    line_res = check_lines(reports, cutoff_d, cold_vt=cold_vt, session_days=session_days)
    if vt_error and "book_shadow_vt" in line_res:
        line_res["book_shadow_vt"]["missing_days"].append(f"cold multiplier unavailable ({vt_error[:120]})")
    sources = lines_read_source(line_res, leg_res)
    notes = list(notes or [])
    unknown = sorted({k for doc in reports.values() for k, v in doc.items()
                      if isinstance(v, dict) and isinstance(v.get("weights"), dict) and "pnl_usd" in v and k not in LINES and k != "legs"})
    for k in unknown:
        notes.append(f"NOTE: line {k} is in the reports but not registered in GUARD r1 (prereg section 11); it was NOT checked")

    verdicts = [v["verdict"] for v in leg_res.values()] + [line_verdict(r) for r in line_res.values()]
    overall = "FAIL" if "FAIL" in verdicts else ("INCOMPLETE" if "INCOMPLETE" in verdicts else "PASS")
    binding = (not dry_run) and cutoff_d >= _to_date(FIRST_BINDING_CUTOFF) and not only
    result = {
        "guard": VERSION, "cutoff": cutoff_d.isoformat(), "dry_run": bool(dry_run), "binding": bool(binding),
        "subset": sorted(only) if only else None, "overall": overall,
        "prereg_sha256": prereg_hash, "harness_rev": git_rev, "generated_unix": int(started),
        "bundle": {k: v for k, v in bmeta.items()}, "bundle_stale": bundle_stale,
        "legs": leg_detail, "lines": {k: {"verdict": line_verdict(v), **v, "forward_read_source": sources[k]["source"],
                                          "legs_not_clean": sources[k]["legs_not_clean"]} for k, v in line_res.items()},
        "report_days_read": len(reports),
        "prior_snapshot": snap_meta, "notes": notes,
        "firestore_reads": source.reads() if hasattr(source, "reads") else None,
        "snapshot": make_snapshot(paper_by_leg, legs_run, cutoff_d),
    }
    result["cold_reference_rows"] = cold_rows_for_failures
    return result


def _counts(f, res):
    return {"forward_paper": res["n_paper_forward"], "forward_cold": res["n_cold_forward"], "matched": f["matched"],
            "in_band": f["in_band"], "exact": f["exact_n"], "denominator": f["denominator"], "out_of_band": f["out"],
            "missing": len(f["missing"]), "extra": len(f["extra"]), "open_either": f["open_either"],
            "explained": len(f["explained"]) + len(f["explained_missing"]), "uncovered": len(f["uncovered"]),
            "adjacent_pairs": f["adjacent_pairs"]}


def _bf_counts(b):
    return {"paper": b["n_paper"], "cold": b["n_cold"], "matched": b["matched"], "in_band": b["in_band"],
            "denominator": b["denominator"], "missing": len(b["missing"]), "extra": len(b["extra"])}


# ---------------------------------------------------------------------------------------------------------------
# rendering (no P&L level, ever)
# ---------------------------------------------------------------------------------------------------------------
FORBIDDEN_KEYS = ("roc", "sortino", "cumulative", "cum_pnl", "net_pnl", "equity", "total_pnl")


def _pct(a, b):
    return "n/a" if not b else f"{100.0 * a / b:.1f}%"


def render(result):
    L = []
    hdr = ("BINDING READ" if result["binding"] else
           f"DRY RUN - NOT THE BINDING READ (first binding read {FIRST_BINDING_CUTOFF})")
    L.append(f"GUARD r1 {hdr}")
    L.append(f"cut-off {result['cutoff']}   overall {result['overall']}"
             + (f"   SUBSET {','.join(result['subset'])}" if result.get("subset") else ""))
    L.append(f"prereg sha256 {result.get('prereg_sha256')}   harness {result.get('harness_rev')}   "
             f"trial cache OFF (cold)   firestore reads {result.get('firestore_reads')} (read-only)")
    b = result.get("bundle") or {}
    L.append(f"paper record via {b.get('via')} (n_total {b.get('n_total')}, written {b.get('gen')}, "
             f"{'STALE vs the cut-off day' if result.get('bundle_stale') else 'after the cut-off day closed'}); "
             f"{result.get('report_days_read')} report day(s) read")
    L.append("No cumulative P&L, ROC or Sortino is printed or stored by this tool.")
    L.append("")
    L.append("LEGS (forward trades only; backfill is information)")
    for k, d in result["legs"].items():
        c = d["counts"]
        m = d.get("master") or {}
        L.append(f"{k:15s} {d['instrument']} {d['timeframe']:3s} {d['pinned_source']:13s} thru {str(m.get('last_bar_et'))[:10]:10s} | "
                 f"fwd {c['forward_paper']:3d} matched {c['matched']:3d} in-band {_pct(c['in_band'], c['denominator']):>6s} "
                 f"exact {_pct(c['exact'], c['denominator']):>6s} | missing {c['missing']} extra {c['extra']} "
                 f"open {c['open_either']} expl {c['explained']} uncov {c['uncovered']} "
                 f"postclose {len(d['post_close']['report_vs_docs']) + len(d['post_close']['snapshot_diff'])} | {d['verdict']}")
        for df in d["defects"]:
            ids = ", ".join(df["trade_ids"][:12]) + (f" (+{len(df['trade_ids']) - 12} more)" if len(df["trade_ids"]) > 12 else "")
            L.append(f"    FAIL {df['cond']}: {df['stat']}; leg {k}; trade ids: {ids or '-'}")
            for x in (df.get("detail") or [])[:6]:
                L.append(f"      {x['id']}: {'; '.join(x['reasons'])}")
            if df.get("adjacent_pairs"):
                L.append(f"      {df['adjacent_pairs']} missing/extra pair(s) sit exactly one bar apart (stamping-shift signature)")
        for pc in d["post_close"]["report_vs_docs"][:6]:
            L.append(f"    post-close (report vs trade docs): {pc['day']} differs by ${pc['diff_usd']:+.2f}; ids {', '.join(pc['trade_ids'][:8]) or '-'}")
        for tid, why in d["post_close"]["snapshot_diff"][:6]:
            L.append(f"    post-close (snapshot): {tid} {why}")
        for why in d["incomplete"]:
            L.append(f"    INCOMPLETE: {why}")
        bf = d["backfill_info"]
        if bf["paper"] or bf["cold"]:
            L.append(f"    backfill (information only): paper {bf['paper']} cold {bf['cold']} matched {bf['matched']} "
                     f"in-band {_pct(bf['in_band'], bf['denominator'])} missing {bf['missing']} extra {bf['extra']}")
    L.append("")
    L.append("LINES (stored dollars = sum of legs within $%.2f; only differences are printed)" % LINE_TOL_USD)
    for k, d in result["lines"].items():
        L.append(f"{k:19s} days {d['days']:3d} defects {len(d['defects'])} missing report days {len(d['missing_days'])} | "
                 f"{d['verdict']} | forward read from: {d['forward_read_source']}")
        for x in d["defects"][:6]:
            extra = {kk: vv for kk, vv in x.items() if kk not in ("day", "kind")}
            L.append(f"    FAIL {x['kind']} on {x['day']} {extra}")
        for md in d["missing_days"][:4]:
            L.append(f"    INCOMPLETE: no report document for {md}")
    sn = result.get("prior_snapshot")
    L.append("")
    L.append("NOTES")
    L.append(f"post-close snapshot: " + (f"compared with {sn['file']} (cut-off {sn['cutoff']})" if sn else "no prior snapshot - baseline written"))
    legacy = sum(d["post_close"]["legacy_days_mismatched"] for d in result["legs"].values())
    L.append(f"report days before {EXITDAY_CUTOVER} (entry-day convention) mismatching their trade docs: {legacy} leg-day(s) - information, not a verdict")
    for n in result.get("notes") or []:
        L.append(n)
    return "\n".join(L)


def assert_no_pnl_level(obj, _path=""):
    """Raise if a forbidden key appears in the structure (the cold reference rows are exempt: written separately)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS or str(k) in ("pnl_usd", "pnl_pts"):
                raise AssertionError(f"P&L-like key {k!r} at {_path}")
            assert_no_pnl_level(v, f"{_path}/{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            assert_no_pnl_level(v, f"{_path}[{i}]")


def write_outputs(result, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cold = result.pop("cold_reference_rows", {})
    assert_no_pnl_level(result)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(result["generated_unix"]))
    path = os.path.join(out_dir, f"guard_r1_{result['cutoff']}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    cpath = None
    if cold:
        cpath = os.path.join(out_dir, f"cold_{result['cutoff']}.json")
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump({"cutoff": result["cutoff"], "note": "cold reference trade rows of NON-PASSING legs only (prereg section 8)",
                       "legs": cold}, f, indent=1, sort_keys=True)
    return path, cpath


# ---------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------
def _git_rev():
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:
        return None


def _real_firestore():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred):
        cred = os.path.join(SHARED_CHECKOUT, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return ReadOnlyDB(firestore.client())


def main(argv=None):
    ap = argparse.ArgumentParser(description="GUARD r1: monthly cold check of the paper record (read-only).")
    ap.add_argument("--cutoff", help="YYYY-MM-DD month-end cut-off (default: last trading day of the latest ended month)")
    ap.add_argument("--dry-run", action="store_true", help="never the binding read; stdout + one local JSON only")
    ap.add_argument("--only", help="comma-separated leg keys (debugging; the run is then never binding)")
    ap.add_argument("--out-dir", default=GUARD_DIR)
    args = ap.parse_args(argv)
    if not os.path.exists(os.path.join(ENGINE_ROOT, "optimizer_history.db")):
        raise SystemExit("no master registry in this checkout (a worktree has none): run guard_r1.py from the shared checkout, "
                         + SHARED_CHECKOUT)
    os.environ.pop("AUGUR_TRIAL_CACHE", None)          # cold: no cached trial replay
    cutoff = _to_date(args.cutoff) if args.cutoff else default_cutoff()
    only = {s.strip() for s in args.only.split(",")} if args.only else None
    if only and not only <= set(LEG_KEYS):
        raise SystemExit(f"unknown leg(s): {sorted(only - set(LEG_KEYS))}")

    from api import paper, book_shadow
    from api.market_calendar import sessions_between
    paper_legs = {l["key"]: l for l in paper.PAPER_LEGS}
    leg_info = {k: {"mult": float(paper_legs[k].get("mult") or 20.0), "instrument": paper_legs[k]["instrument"],
                    "timeframe": paper_legs[k]["timeframe"], "session": paper_legs[k].get("session"),
                    "live_from": paper.LEG_LIVE_FROM.get(k, paper.PAPER_START)} for k in LEG_KEYS}
    artifacts = set(paper.ROLL_ARTIFACTS.keys())
    notes = config_drift_notes(list(paper_legs.values()), book_shadow.BOOK463_LEGS)
    prior = load_prior_snapshot(args.out_dir, cutoff)
    src = FirestoreSource(_real_firestore())
    result = run_guard(cutoff, dry_run=args.dry_run, source=src, cold_provider=real_cold_provider(cutoff),
                       vt_provider=real_vt_provider(cutoff), leg_info=leg_info, artifacts=artifacts,
                       out_dir=args.out_dir, session_days=sessions_between, only=only, prior_snapshot=prior,
                       notes=notes, git_rev=_git_rev(), prereg_hash=prereg_sha256())
    print(render(result))
    path, cpath = write_outputs(result, args.out_dir)
    print(f"\nresult JSON: {path}" + (f"\ncold reference (non-passing legs only): {cpath}" if cpath else ""))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[result["overall"]]


if __name__ == "__main__":
    sys.exit(main())
