r"""tools/book_asif_series.py -- AS-IF daily P&L for every leg of every book config (owner 11-21, v91.71).

WHY. The owner wants every book in the book table (C:/EdgeLog/manager/open_board/book_legs.json) as a dropdown on the
NT8 PAPER and WEBULL PAPER ledgers, each leg with a switch that draws "how it would have done" on the paper chart.
Most legs are not traded anywhere (no paper, no box shadow), so their as-if series is a SIMULATION: the leg's pinned
champion parameters (the run number the book table names), the repo engine and that run's own cost, on current data,
over the paper window. Never the account.

WHAT IT DOES
  1. reads the book table, dedupes the legs (19 distinct ids across 24 books on 11-21);
  2. for each leg resolves its spec (strategy file, champion params, instrument / timeframe / session / source, cost,
     multiplier, book weight) from LEG_SPECS + the cached run docs (C:/EdgeLog/_anatomy_cache/runs, luckbar/runs,
     bookshadow_rundocs.json; a missing one is read from Firestore ONCE and cached);
  3. runs it through augur_engine.book._leg_trades (the code path a BOOK job uses) from WARM days before the window,
     keeps the trades that CLOSED on or after WINDOW_FROM, stamps them on the New York session day, and writes
       {d: [dates], p: [usd a day], n: [trades a day]}
     A trade whose exit is the master's LAST bar may still be open: it is left out of the days and reported as
     last_bar_usd (it lands on its real day on a later run);
  4. writes C:/EdgeLog/shadow_asif/book_asif.json and publishes Firestore users/<uid>/meta/book_asif (the page reads it).
A leg that cannot be simulated (no strategy file, no data, the run doc missing) gets {"reason": "..."} instead of a
series, and the page shows that reason.

INCREMENTAL. Each leg is cached under C:/EdgeLog/shadow_asif/cache/<ID>.json keyed by its spec + the master's last bar;
an unchanged leg is not re-run. A run with nothing new does not publish (a book-table change or --force does).
The page may also ask for legs it has no series for (meta/book_asif_req, written when a switch is flipped on a leg the
doc does not carry); those are built on the next run.

    python tools/book_asif_series.py               # build what changed, publish
    python tools/book_asif_series.py --no-publish  # local file only
    python tools/book_asif_series.py --force       # rebuild every leg
    python tools/book_asif_series.py --legs NOISE422,ORB234
    python tools/book_asif_series.py --panels-only # just re-pull the stale PICK6 / OPUS86a / GLDNIGHT panels

PANELS. Every run (the 30-min scheduled one too) first re-pulls an extension panel (tools/asif_ext_panels.py) whose
last day is before the SPY 5m stock master's last COMPLETED session, once per panel per master day
(C:/EdgeLog/shadow_asif/panel_refresh.json); the new panel's sha changes that leg's cache key, so it rebuilds.
--no-panel-refresh skips it. SIZES: a trade's per-trade size (a gate's multiplier, a file's own size such as NOISE's
tilt) is applied in the NQ series and the qqq block. ML: see ML_LEGS (the leak guard).

Run from anywhere: the engine and its master registry are imported from the SHARED checkout (the worktree registry
trap). Read-only on the registry; never touches optimizer_history.db writes, orders or api/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import traceback

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SHARED)          # the shared checkout's augur_engine + registry first

BOOK_TABLE = r"C:/EdgeLog/manager/open_board/book_legs.json"
OUT_DIR = os.environ.get("EDGELOG_BOOK_ASIF_DIR", r"C:\EdgeLog\shadow_asif")
RUNS_CACHE = r"C:\EdgeLog\_anatomy_cache\runs"
LUCK_CACHE = r"C:\EdgeLog\_anatomy_cache\luckbar\runs"
EXTRA_CACHE = r"C:\EdgeLog\_anatomy_cache\bookshadow_rundocs.json"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
# the paper window: NT8 PAPER starts 2026-08-11, WEBULL PAPER earlier legs from the summer; the page clips to each
# board's own first ledger day, so the series starts early enough for both
WINDOW_FROM = "2026-06-01"
WARM_DAYS = 330                      # NOISE's 104-day lookback, EODREV's 180-day beta, ENGU-Q's 1340-bar EMA
SCHEMA = 4                           # 2 = 11-21 owner-review fixes (PICK6 paper size, NOISE398 #528, unit check); 3 = the qqq block (v91.74); 4 = per-trade sizes in the qqq block + ML guard + panel ext

# Book-table leg id -> which run's champion it is, and anything the run doc does not say. `run` is the run the book
# table names (the label); `params_run` (if set) is the run whose champion is replayed (NOISE398 = #528's PASS pick);
# `weight` is the book's size (TTMx3 = 3 ES, OPUS58c_h = half size); `paper_usd_per_side` sizes a dollars leg to the
# paper account (PICK6 trades $10k a side on Webull paper, api/eodrev_exec.py usd_per_side; the plugin is $100k a
# side); `params` pins a config when the run stored no champion (only where every knob of the file is pinned anyway).
# 11-21 owner review: every leg's cost_pts / mult is checked against how its strategy reports P&L (unit_check): a
# "points" file needs the run's cost and the contract multiplier, a "usd" file charges its own cost inside and must
# run at job cost 0, mult 1.
# Side-panel legs: the plugin's pinned panel ends 2026-06-30 (runs #511 / #526 / #541 reproduce from it). `panel_ext`
# names the plugin's PANEL_EXT_ENV hook and a fresher panel; sessions after the pinned end are scored on that panel
# alone (augur_strategies/MISC_*: unset = the pinned behaviour byte for byte). Panels: tools/asif_ext_panels.py
# eodrev / auchabit / gldnight (fresh Alpaca pulls from a fixed start; re-run them to move the series forward -
# refresh_ext_panels() below does that once per new stock-master day).
_PANEL_EXT = {
    "PICK6": ("MISC_EODREV_1_2_PANEL_EXT", r"C:/EdgeLog/alpaca_cache/eodrev_panel/eodrev_u100_panel_asif.npz"),
    "OPUS86a": ("MISC_AUCHABIT_1_0_PANEL_EXT", r"C:/EdgeLog/alpaca_cache/auchabit_panel/auchabit_panel_asif.npz"),
    "GLDNIGHT": ("MISC_GLDNIGHT_1_0_PANEL_EXT", r"C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_asif.npz"),
}
_PANEL_BUILD = {"PICK6": "eodrev", "OPUS86a": "auchabit", "GLDNIGHT": "gldnight"}   # tools/asif_ext_panels.py <what>
PANEL_STAMP = os.path.join(OUT_DIR, "panel_refresh.json")
PANEL_BUILD_TIMEOUT = 20 * 60

# ── ML LEGS (owner promise 11-21, MANAGER): a book leg whose strategy scores trades with a TRAINED MODEL ──
ML_LEGS = {}
"""Registry of book legs whose strategy loads a trained model file, for legs whose run doc / strategy file do not say
so themselves. leg_id -> {"model_path": str, "sha256": "<hex, >= 12 chars: the artifact pinned to the leg's run>",
"trained_through": "YYYY-MM-DD"}. Empty on 11-21: no current book leg loads a model (grep of augur_strategies for
joblib / .pkl / MODEL_PATH / trained_through finds only research panels, never a fitted model).

A leg is an ML leg when ANY of these says so (first wins for each field):
  1. the run doc: model_path, model_sha256 (the pin), model_trained_through / trained_through;
  2. ML_LEGS[leg_id] (this dict);
  3. the strategy file's module constants: MODEL_PATH, MODEL_SHA256, TRAINED_THROUGH, ML = True / USES_MODEL = True.
LEAK GUARD (ml_guard): the series is REFUSED, with the reason on the page, when the model path or its pin is missing,
the file on disk does not hash to the pin, the training end is unknown, or the training end is on or after
WINDOW_FROM (a model that saw the as-if window would draw an in-sample line). A passing leg replays with the EXACT
pinned file: its path is handed to the strategy in MODEL_ENV, set only while that leg replays.
A `gate` block in LEG_SPECS (augur_engine.book's ML gate, api/paper_gate.apply_gate) is not a stored model: it refits
walk-forward on the leg's own earlier trades inside the replay, so it needs no pin; its per-trade size is applied."""
MODEL_ENV = "EDGELOG_ASIF_MODEL_PATH"
TRADES_PER_DOC = 2500                 # board 147: ~200 bytes a row -> ~0.5 MB a doc, under Firestore's 1 MiB
_EXPCAL_ONLY = {"cost_pts": 0.533, "point_value": 20}
_EXPCAL_FROM = ("the file's only config (every knob pinned: NQ 0.533 pts a round trip at $20 a point, charged inside "
                "the file); run #543 stored no champion")
LEG_SPECS = {
    "ENGUQ335":  {"run": 335},
    "NOISE422":  {"run": 422},
    "ORB234":    {"run": 234, "note": "book seat = run #547 walk-forward of the #234 exit; the #234 champion is replayed"},
    "TTMx3":     {"run": 369, "weight": 3.0, "note": "3 ES, the #369 seat"},
    "NOISE406":  {"run": 406},
    "NOISE304":  {"run": 304},
    "NOISE398":  {"run": 398, "params_run": 528,
                  "note": "#398's file with engine PASS run #528's champion (gate_len 16; #398's own pick was 20)"},
    "NOISE382":  {"run": 382},
    "ORB546":    {"run": 546},
    "ORB314":    {"run": 314},
    "ORB421":    {"run": 421, "note": "= #257 seat"},
    "TTIBS300":  {"run": 300},
    "OPUS55a":   {"run": 524, "note": "up to 2 NQ = one 1-NQ trade tuple per leg trade, legs can overlap; weight 1"},
    "OPUS107a":  {"run": 518},
    "OPUS58c":   {"run": 543, "params": _EXPCAL_ONLY, "params_from": _EXPCAL_FROM},
    "OPUS58c_h": {"run": 543, "weight": 0.5, "note": "half size", "params": _EXPCAL_ONLY,
                  "params_from": _EXPCAL_FROM},
    "OPUS86a":   {"run": 526, "note": "$100k a side = the file's pinned notional; cost charged inside the file"},
    "PICK6":     {"run": 511, "paper_usd_per_side": 10000.0, "size": "$10k a side (paper size)",
                  "note": "Webull paper PICK6 trades $10k a side (api/eodrev_exec.py); the #511 champion is $100k a "
                          "side, so the as-if runs at 0.1x",
                  "stale_fix": "re-run python tools/asif_ext_panels.py eodrev"},
    "GLDNIGHT":  {"run": 541, "note": "$100k a trade = the file's pinned notional; cost charged inside the file"},
    # ── board 142 ML legs (11-22, MANAGER GO): the raw leg + a gate block; nothing stored, nothing leaks ──
    # fixed tilts = v12's a-priori sizes (no model); KEEL = the continuous causal walk seeded from 2010 (owner 11-22:
    # behave as live - learn from all earlier trades, keep learning as each closes; paper_gate modes comp / keel).
    "NOISE422_fixed": {"run": 422, "label": "NOISE #422 fixed tilts",
                       "note": "v12 fixed tilts, no model: compression 1.5x, Friday 1.5x, cap 3, 0.5x before FOMC",
                       "gate": {"mode": "comp", "mult": 1.5, "dow": {"4": 1.5},
                                "event": {"mult": 0.5, "cut_hour": 14}}},
    "NOISE382_fixed": {"run": 382, "label": "NOISE #382 fixed tilts",
                       "note": "v12 fixed tilts, no model: compression 1.5x, Friday 1.5x, cap 3, 0.5x before FOMC",
                       "gate": {"mode": "comp", "mult": 1.5, "dow": {"4": 1.5},
                                "event": {"mult": 0.5, "cut_hour": 14}}},
    "NOISE422_keel":  {"run": 422, "label": "NOISE #422 KEEL",
                       "note": "KEEL v12 causal walk from 2010: each trade sized only from trades already closed, keeps learning (owner 11-22)",
                       "warm_from": "2010-06-07",
                       "gate": {"mode": "keel", "version": "v12"}},
    "NOISE382_keel":  {"run": 382, "label": "NOISE #382.2 KEEL",
                       "note": "the live Webull stack: KEEL v12 causal walk from 2010, keeps learning as trades close (owner 11-22)",
                       "warm_from": "2010-06-07",
                       "gate": {"mode": "keel", "version": "v12"}},
}
SOURCE_MAP = {   # a run doc's source_name -> (session, registry source)
    "rth - no-adj": ("rth", "db_noadj_rth"), "eth - no-adj": ("eth", "db_noadj_eth"),
    "rth - back-adjusted": ("rth", "db_adj_rth"), "eth - back-adjusted": ("eth", "db_adj_eth"),
    "(alpaca rth)": ("rth", "alpaca_split_rth"),
}
MULT = {"NQ": 20.0, "ES": 50.0, "YM": 5.0, "RTY": 50.0, "ZN": 1000.0, "MNQ": 2.0, "MES": 5.0}
STOCKS = {"SPY", "QQQ", "GLD", "IWM", "DIA"}


def _now_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, p)


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(SHARED, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


# ── run docs ─────────────────────────────────────────────────────────────────────────────────────────────
_EXTRA = None


def run_doc(rid, allow_fetch=True):
    """The run's doc (strategy, source_name, cost_pts, multiplier, champion) from the local caches, else Firestore once."""
    global _EXTRA
    for d in (RUNS_CACHE, LUCK_CACHE):
        p = os.path.join(d, "%d.json" % rid)
        if os.path.exists(p):
            doc = _load_json(p)
            if isinstance(doc, dict) and doc.get("strategy"):
                return doc
    if _EXTRA is None:
        _EXTRA = _load_json(EXTRA_CACHE, {}) or {}
    doc = _EXTRA.get(str(rid))
    if isinstance(doc, dict) and doc.get("strategy"):
        return doc
    if not allow_fetch:
        return None
    sys.path.insert(0, SHARED)
    import tools.runboard_watch as rw   # noqa: E402  (UID, real_client, run_ref)
    snap = rw.run_ref(rw.real_client(), rid).get(field_paths=[
        "id", "strategy", "scope", "best_params", "instrument", "timeframe", "session", "source_name", "cost_pts",
        "multiplier", "date_from", "date_to", "validate.champion"])
    doc = snap.to_dict() if getattr(snap, "exists", False) else None
    _EXTRA[str(rid)] = doc
    _write_json(EXTRA_CACHE, _EXTRA)
    return doc


def _session_source(doc):
    sn = str(doc.get("source_name") or "").lower()
    for k, v in SOURCE_MAP.items():
        if k in sn:
            return v
    return (str(doc.get("session") or "rth").lower(), None)


def leg_spec(leg_id, book_leg):
    """{strategy, params, instrument, timeframe, session, source, cost_pts, mult, weight, run} or raise ValueError(why)."""
    s = LEG_SPECS.get(leg_id)
    if not s:
        raise ValueError("no replay spec for this leg yet (add it to LEG_SPECS in tools/book_asif_series.py)")
    prun = int(s.get("params_run") or s["run"])
    doc = run_doc(prun)
    if not doc:
        raise ValueError("run #%d doc not found" % prun)
    champ = ((doc.get("validate") or {}).get("champion")) or doc.get("best_params") or {}
    if not isinstance(champ, dict):
        champ = {}
    if champ:
        params_from = "champion of run #%d" % prun
    elif s.get("params"):
        champ, params_from = dict(s["params"]), s.get("params_from") or "pinned in LEG_SPECS"
    else:
        params_from = "strategy defaults (the run stored no champion)"
    inst = str(doc.get("instrument") or "").upper()
    sess, src = _session_source(doc)
    mult = doc.get("multiplier")
    try:
        mult = float(mult) if mult and float(mult) > 0 else None
    except (TypeError, ValueError):
        mult = None
    if mult is None:
        mult = MULT.get(inst, 1.0)
    weight = float(s["weight"]) if "weight" in s else size_weight((book_leg or {}).get("size"), s, champ)
    spec = {"run": s["run"], "params_run": prun, "strategy": doc["strategy"], "params": dict(champ),
            "instrument": inst, "timeframe": doc.get("timeframe") or "5m", "session": sess, "source": src,
            "cost_pts": float(doc.get("cost_pts") or 0), "mult": mult, "weight": weight,
            "params_from": params_from, "note": s.get("note", ""), "size": s.get("size") or "",
            "stale_fix": s.get("stale_fix", "")}
    if s.get("gate"):
        spec["gate"] = dict(s["gate"])
    if s.get("warm_from"):       # KEEL legs: the pre-freeze state is built on the leg's whole trade history
        spec["warm_from"] = s["warm_from"]
    if leg_id in _PANEL_EXT:
        spec["panel_ext"] = panel_ext_info(*_PANEL_EXT[leg_id])
    spec["pnl_units"] = strategy_pnl_units(spec["strategy"])
    bad = unit_check(spec, spec["pnl_units"])
    if bad:
        raise ValueError("cost / mult do not fit the strategy's P&L units (%s): %s" % (spec["pnl_units"], bad))
    ml = ml_guard(leg_id, spec, doc)            # raises ValueError("ML leak guard: ...") on a refused model
    if ml:
        spec["ml"] = ml
    return spec


def panel_ext_info(env, path):
    """{env, path, sha12, end} of a side-panel leg's as-if extension panel; {} when the file is not on this machine
    (the leg then runs on the pinned panel alone and stops at its end, as before)."""
    if not os.path.exists(path):
        return {}
    import numpy as np
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()[:12]
    with np.load(path, allow_pickle=False) as z:
        end = str(int(z["dates"][-1]))
    return {"env": env, "path": path, "sha12": sha, "end": "%s-%s-%s" % (end[:4], end[4:6], end[6:])}


# ── the ML leak guard (see ML_LEGS) ──────────────────────────────────────────────────────────────────────
def _strategy_path(strategy):
    for root in (HERE, SHARED):
        p = os.path.join(root, "augur_strategies", os.path.basename(str(strategy)))
        if os.path.exists(p):
            return p
    return None


def strategy_ml_markers(strategy):
    """The file's ML module constants (MODEL_PATH, MODEL_SHA256, TRAINED_THROUGH, ML, USES_MODEL) read from its
    source text as literals - the file is never imported for this."""
    import ast
    import re
    p = _strategy_path(strategy)
    if not p:
        return {}
    with open(p, encoding="utf-8", errors="replace") as f:
        src = f.read()
    out = {}
    for m in re.finditer(r"^(MODEL_PATH|MODEL_SHA256|TRAINED_THROUGH|ML|USES_MODEL)\s*=\s*(.+?)\s*(?:#.*)?$", src, re.M):
        try:
            out[m.group(1)] = ast.literal_eval(m.group(2))
        except Exception:
            out[m.group(1)] = m.group(2)
    return out


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar_trained_through(path):
    """trained_through from a JSON sidecar next to the model (<path>.json or <stem>.meta.json); the pickle itself is
    never unpickled to read it."""
    stem = os.path.splitext(path)[0]
    for side in (path + ".json", stem + ".meta.json", stem + ".json"):
        d = _load_json(side)
        if isinstance(d, dict) and d.get("trained_through"):
            return str(d["trained_through"])
    return None


def ml_guard(leg_id, spec, doc, registry=None):
    """None for a leg with no trained model; else {model_path, sha12, trained_through, from} for a model that passes
    the leak guard; raises ValueError('ML leak guard: ...') when the series must be refused (see ML_LEGS)."""
    reg = (ML_LEGS if registry is None else registry).get(leg_id) or {}
    doc = doc or {}
    mk = strategy_ml_markers(spec.get("strategy"))
    flagged = bool(reg or doc.get("model_path") or doc.get("model_sha256") or mk.get("MODEL_PATH")
                   or mk.get("ML") is True or mk.get("USES_MODEL") is True)
    if not flagged:
        return None
    run = spec.get("params_run") or spec.get("run")

    def first(*pairs):
        for v, where in pairs:
            if v:
                return str(v), where
        return None, None
    path, path_from = first((doc.get("model_path"), "run #%s doc" % run), (reg.get("model_path"), "ML_LEGS"),
                            (mk.get("MODEL_PATH"), "the strategy file"))
    pin, pin_from = first((doc.get("model_sha256"), "run #%s doc" % run), (reg.get("sha256"), "ML_LEGS"),
                          (mk.get("MODEL_SHA256"), "the strategy file"))
    if not path:
        raise ValueError("ML leak guard: the strategy uses a trained model but no model file is named (run doc "
                         "model_path, ML_LEGS or the file's MODEL_PATH)")
    if not pin or len(pin) < 12:
        raise ValueError("ML leak guard: model %s is not pinned to run #%s (no model_sha256 on the run doc, in "
                         "ML_LEGS or in the file) - cannot prove the replay uses the run's own model"
                         % (os.path.basename(path), run))
    if not os.path.exists(path):
        raise ValueError("ML leak guard: pinned model %s is not on this machine" % path)
    sha = _sha256_file(path)
    if not sha.startswith(pin.lower()):
        raise ValueError("ML leak guard: model %s hashes %s, run #%s pins %s - not the run's model"
                         % (os.path.basename(path), sha[:12], run, pin[:12]))
    tt, tt_from = first((doc.get("model_trained_through") or doc.get("trained_through"), "run #%s doc" % run),
                        (reg.get("trained_through"), "ML_LEGS"), (mk.get("TRAINED_THROUGH"), "the strategy file"),
                        (_sidecar_trained_through(path), "the model's sidecar json"))
    if not tt:
        raise ValueError("ML leak guard: the training end of model %s is unknown - refused (an unknown end may "
                         "overlap the as-if window from %s)" % (os.path.basename(path), WINDOW_FROM))
    if str(tt)[:10] >= WINDOW_FROM:
        raise ValueError("ML leak guard: model %s was trained through %s, on or after the as-if window start %s - "
                         "its as-if line would be in-sample" % (os.path.basename(path), str(tt)[:10], WINDOW_FROM))
    return {"model_path": path, "sha12": sha[:12], "trained_through": str(tt)[:10],
            "from": "path: %s; pin: %s; training end: %s" % (path_from, pin_from, tt_from)}


def strategy_pnl_units(strategy):
    """The file's PNL_UNITS constant ("points" when absent) read from its source text, None if no file."""
    import re
    for root in (HERE, SHARED):
        p = os.path.join(root, "augur_strategies", os.path.basename(str(strategy)))
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                m = re.search(r"""^PNL_UNITS\s*=\s*["']([A-Za-z]+)["']""", f.read(), re.M)
            return m.group(1).lower() if m else "points"
    return None


def unit_check(spec, units):
    """'' when cost_pts / mult fit how the strategy reports P&L, else what is wrong."""
    if units is None:
        return "strategy file not found"
    bad = []
    if units == "usd":
        if spec["cost_pts"] != 0:
            bad.append("job cost_pts %s on a dollars file (it charges its own cost; must be 0)" % spec["cost_pts"])
        if spec["mult"] != 1.0:
            bad.append("mult %s on a dollars file (must be 1)" % spec["mult"])
        return "; ".join(bad)
    if not spec["cost_pts"] > 0:
        bad.append("cost_pts 0 on a points file (no cost charged)")
    want = MULT.get(spec["instrument"])
    if want is not None and spec["mult"] != want:
        bad.append("mult %s on a points %s file (the contract is %s)" % (spec["mult"], spec["instrument"], want))
    return "; ".join(bad)


def size_weight(book_size, s, params):
    """The weight the book row's size implies: 'x N' / 'N ES' -> N, 'half' -> 0.5, a paper dollars size -> it over
    the file's notional; anything else (1 NQ; up to 2 NQ = per-tuple contracts; $100k = the pinned notional) -> 1."""
    import re
    if s.get("paper_usd_per_side"):
        return float(s["paper_usd_per_side"]) / float((params or {}).get("notional") or 100000)
    t = str(book_size or "").lower()
    if "half" in t:
        return 0.5
    m = re.search(r"\bx\s*(\d+(?:\.\d+)?)\b", t) or re.search(r"^\s*(\d+(?:\.\d+)?)\s*(?:es|ym|rty)\b", t)
    return float(m.group(1)) if m else 1.0


def leg_kind(book_leg, spec=None):
    ins = str((book_leg or {}).get("instrument") or (spec or {}).get("instrument") or "").upper()
    if "STOCK" in ins or "ETF" in ins or ins in STOCKS or (spec and spec.get("instrument") in STOCKS):
        return "stock"
    return "futures"


# ── QQQ conversion for WEBULL PAPER (owner 11-21: "the configs, while tested on EL with NQ futures, should be webull/QQQ
# compatible", v91.74) ──────────────────────────────────────────────────────────────────────────────────────────────
# The Webull box (api/qqq_exec.py) trades QQQ SHARES, never contracts. Its sizing rule is size_mode "fixed" (the default,
# api/qqq_exec.py:328; the else branch of _open_lot, ~:9530): a lot is cfg["shares"][exec_leg] shares (DEFAULT_CONFIG
# :279 = 5 each; the box's config.json, C:/EdgeLog/qqq_exec/config.json, sets ORB / ENGUQ / NOISE = 10), one lot per
# signal whatever the NQ quantity. Every fill pays slippage_per_share (:323, $0.01) against us on entry AND exit
# (_apply_slippage, :8679). Its old NinjaTrader mirror priced QQQ as NQ / (NQ:QQQ ratio calibrated each day, :7617).
# So one NQ trade, as the box would have traded it:
#     QQQ $ = gross NQ points x (QQQ close / NQ close on the entry day) x shares - 2 x slippage x shares
# gross = the replay's net points + the run's cost_pts (the NQ cost is not a QQQ cost; Webull charges no commission,
# the SEC / TAF sell fees are under a cent at this size, docs/WEBULL_LIVE_RUNBOOK.md section 5). The box trades no SPY,
# so an ES leg maps to QQQ through the QQQ-on-ES daily beta (SPY daily as a fallback): gross ES points / ES close x beta x QQQ close x shares.
# A leg the box does not trade is sized like the box's 1-NQ lot (its ORB / NOISE / ENGUQ share count) x the book weight.
# Stock legs (PICK6, GLDNIGHT, OPUS86a) are already dollars at paper size and stay as they are.
QQQ_EXEC_CFG = r"C:\EdgeLog\qqq_exec\config.json"
EXEC_DEFAULT_SHARES = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}      # api/qqq_exec.py DEFAULT_CONFIG["shares"]
EXEC_DEFAULT_SLIP = 0.01                                       # api/qqq_exec.py DEFAULT_CONFIG["slippage_per_share"]
EXEC_DEFAULT_MAX = 10                                          # api/qqq_exec.py DEFAULT_CONFIG["max_shares_per_leg"]
QQQ_DAILY_FILES = (   # priority order; a 5m file gives the close of each ET day's last RTH bar
    (r"C:\EdgeLog\qqq_bars\QQQ_ext_alpaca_5m.csv", "5m"),
    (r"C:\EdgeLog\ohlc\QQQ_5m.csv", "5m"),
    (r"C:\EdgeLog\alpaca_cache\etf_daily\QQQ_1Day_raw.csv", "1d"),
)
SPY_DAILY = r"C:\EdgeLog\alpaca_cache\etf_daily\SPY_1Day_raw.csv"
QQQ_DAILY_RAW = r"C:\EdgeLog\alpaca_cache\etf_daily\QQQ_1Day_raw.csv"
BETA_DAYS = 252


def exec_leg_for(leg_id):
    """The box's exec leg a book leg rides on (the ENGINE_LEG_MAP families), None when the box does not trade it."""
    u = str(leg_id or "").upper()
    for fam in ("ORB", "ENGUQ", "NOISE"):
        if u.startswith(fam):
            return fam
    return None


def exec_sizing(cfg_path=QQQ_EXEC_CFG):
    """{shares: {leg: n}, slip, src}: the box executor's fixed share table and slippage, its config over code defaults."""
    shares, slip, src = dict(EXEC_DEFAULT_SHARES), EXEC_DEFAULT_SLIP, "api/qqq_exec.py DEFAULT_CONFIG"
    mx = EXEC_DEFAULT_MAX
    cfg = _load_json(cfg_path) if cfg_path else None
    if isinstance(cfg, dict):
        for k, v in (cfg.get("shares") or {}).items():
            try:
                shares[k] = int(v)
            except (TypeError, ValueError):
                pass
        if cfg.get("slippage_per_share") is not None:
            slip = float(cfg["slippage_per_share"])
        try:
            mx = int(cfg.get("max_shares_per_leg", mx) or 0)
        except (TypeError, ValueError):
            pass
        src = "qqq_exec/config.json over api/qqq_exec.py DEFAULT_CONFIG"
    return {"shares": shares, "slip": slip, "src": src, "max": mx}


def box_sized_shares(base, size, cap):
    """The box's PAPER lot for a signal carrying a per-trade size (api/qqq_exec.py _open_lot, size_mode "fixed"):
    size 1 -> the base lot; else max(1, round(base x size)) (_sized_shares), CLAMPED to max_shares_per_leg (the
    SIZED branch clamps, it does not refuse). Returns (shares, clamped?)."""
    base = int(base)
    if base <= 0:
        return 0, False
    s = float(size)
    if abs(s - 1.0) < 1e-12:
        return base, False
    want = max(1, int(round(base * s)))
    if cap and want > cap:
        return int(cap), True
    return want, False


def qqq_shares(leg_id, weight, sizing):
    """(shares a 1-contract trade, how): the box's lot for its own legs, else the box's 1-NQ lot x the book weight."""
    fam = exec_leg_for(leg_id)
    if fam and fam in sizing["shares"]:
        return int(sizing["shares"][fam]), "the box's %s lot" % fam
    lots = sorted(int(sizing["shares"][k]) for k in ("ORB", "NOISE", "ENGUQ") if k in sizing["shares"])
    base = lots[len(lots) // 2] if lots else 10
    w = float(weight or 1)
    return int(round(base * w)), "not on the box: the box's 1-NQ lot (%d sh) x %g" % (base, w)


def qqq_trade_usd(gross_pts, ref_px, qqq_px, shares, slip, beta=1.0):
    """One trade in QQQ dollars: gross points x (QQQ / ref close) x beta x shares - slippage on both sides x shares."""
    return float(gross_pts) * (float(qqq_px) / float(ref_px)) * float(beta) * shares - 2.0 * float(slip) * shares


def _daily_close_csv(path, kind):
    """{YYYY-MM-DD: close} from a daily csv (date,...,close) or a 5m csv (epoch time: last bar starting 09:30-15:55 ET)."""
    import csv
    out = {}
    if not os.path.exists(path):
        return out
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:
        ny = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                c = float(row.get("close") or "nan")
                if not c > 0:
                    continue
                if kind == "1d":
                    out[str(row["date"])[:10]] = c
                    continue
                t = float(row["time"])
                if t < 1.0e9 or ny is None:
                    continue
                x = dt.datetime.fromtimestamp(t, ny)
                if not (dt.time(9, 30) <= x.time() < dt.time(16, 0)):
                    continue
                out[x.date().isoformat()] = c          # time-ordered rows: the day's last RTH bar wins
            except Exception:
                continue
    return out


def _beta(y, x, days=BETA_DAYS):
    """OLS beta of y's daily returns on x's over their last `days` shared days (None if under 20)."""
    ds = sorted(set(y) & set(x))[-(days + 1):]
    ry = [y[ds[i]] / y[ds[i - 1]] - 1 for i in range(1, len(ds))]
    rx = [x[ds[i]] / x[ds[i - 1]] - 1 for i in range(1, len(ds))]
    if len(rx) < 20:
        return None
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    vx = sum((a - mx) ** 2 for a in rx)
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / vx if vx else None


def _et_days(index):
    import pandas as pd
    di = pd.DatetimeIndex(index)
    if di.tz is not None:
        di = di.tz_convert("America/New_York").tz_localize(None)
    return list(di.normalize().strftime("%Y-%m-%d"))


_QREFS = None


def qqq_refs():
    """{qqq, NQ, ES: {day: close}, beta_es, beta_src, sizing} - built once a run."""
    global _QREFS
    if _QREFS is not None:
        return _QREFS
    qqq = {}
    for path, kind in reversed(QQQ_DAILY_FILES):    # lowest priority first, so the better file overwrites
        qqq.update(_daily_close_csv(path, kind))
    refs = {"qqq": qqq, "sizing": exec_sizing()}
    from augur_engine.data import find_master, load_master_arrays
    start = (dt.date.fromisoformat(WINDOW_FROM) - dt.timedelta(days=WARM_DAYS + 10)).isoformat()
    for inst in ("NQ", "ES"):
        m = find_master(inst, "5m", "rth", "db_noadj_rth") or find_master(inst, "5m", "rth", None)
        d = {}
        if m is not None:
            arr = load_master_arrays(m, date_from=start)
            for day, c in zip(_et_days(arr["index"]), arr["close"]):
                d[day] = float(c)                     # the day's last RTH bar wins
        refs[inst] = d
    # the beta that maps an ES leg to QQQ: QQQ's daily returns on ES's (the ES RTH master's last bar each day), the last
    # BETA_DAYS shared days - the same closes the conversion uses, so it covers the as-if window; SPY as the fallback
    b, both, what = _beta(qqq, refs["ES"]), sorted(set(qqq) & set(refs["ES"])), "ES RTH no-adj"
    if not b:
        spy, qd = _daily_close_csv(SPY_DAILY, "1d"), _daily_close_csv(QQQ_DAILY_RAW, "1d")
        b, both, what = _beta(qd, spy), sorted(set(qd) & set(spy)), "SPY, Alpaca raw"
    refs["beta_es"] = round(b, 3) if b else None
    refs["beta_src"] = "QQQ on %s daily returns, %d days to %s" % (what, min(BETA_DAYS, max(len(both) - 1, 0)),
                                                                   both[-1] if both else "?")
    _QREFS = refs
    return refs


def _on_or_before(dmap, day, keys_sorted):
    import bisect
    if day in dmap:
        return dmap[day]
    i = bisect.bisect_right(keys_sorted, day) - 1
    return dmap[keys_sorted[i]] if i >= 0 else None


def size_cost_units(spec, units, cost, prm):
    """The cost a size-folding file used in its fold, in the file's P&L units: its _COST_PTS constant (NOISE CT304 /
    CT304H = 0.533, the run's cost) when the file has one, else the run's cost (points) or the file's cost x
    point_value (dollars)."""
    import re
    p = _strategy_path(spec.get("strategy")) if spec.get("strategy") else None
    if p:
        with open(p, encoding="utf-8", errors="replace") as f:
            m = re.search(r"^_COST_PTS\s*=\s*([0-9.]+)", f.read(), re.M)
        if m:
            c = float(m.group(1))
            return c * float(prm.get("point_value") or 1) if units == "usd" else c
    return float(cost) * float(prm.get("point_value") or 1) if units == "usd" else float(cost)


def qqq_block(spec, st, refs=None, per_trade=None):
    """The leg's as-if in QQQ dollars as the Webull box would have traded it: {d, p, n, net, trades, shares, rule, ...};
    {reason} when it cannot be converted; {same: True, rule} for a stock leg (already dollars)."""
    import numpy as np
    inst, leg_id = spec["instrument"], spec.get("_leg_id")
    if inst in STOCKS or leg_kind({}, spec) == "stock" or (inst not in MULT and spec.get("pnl_units") == "usd"):
        return {"same": True, "rule": "stock leg: already dollars at paper size, unchanged on Webull"}
    if inst not in ("NQ", "ES", "MNQ", "MES"):
        return {"reason": "no QQQ map for %s (the box trades QQQ only; NQ and ES legs convert)" % inst}
    refs = refs or qqq_refs()
    sz = refs["sizing"]
    root = "NQ" if inst in ("NQ", "MNQ") else "ES"
    beta = 1.0
    if root == "ES":
        beta = refs.get("beta_es")
        if not beta:
            return {"reason": "no QQQ-on-ES beta (the QQQ / ES daily closes are missing)"}
    units = spec.get("pnl_units") or "points"
    prm = spec.get("params") or {}
    if units == "usd":
        pv = float(prm.get("point_value") or 0)
        if not pv:
            return {"reason": "a dollars file with no point_value: its points cannot be recovered"}
        cost = float(prm.get("cost_pts") or 0)
        to_pts = lambda x: float(x) / pv + cost          # noqa: E731
    else:
        cost = float(spec.get("cost_pts") or 0)
        to_pts = lambda x: float(x) + cost               # noqa: E731
    per, how = qqq_shares(leg_id, spec.get("weight"), sz)
    q, r = refs["qqq"], refs[root]
    if not q or not r:
        return {"reason": "no %s daily closes for the QQQ ratio" % ("QQQ" if not q else root)}
    qk, rk = sorted(q), sorted(r)
    sess_idx, last, days_idx = st.get("sess_idx"), st.get("last"), st.get("days_idx")

    def dayf(i):
        return str(np.datetime_as_string(sess_idx[i], unit="D")) if sess_idx is not None else str(days_idx[i])

    # PER-TRADE SIZE (11-21 asifml). Two sources, multiplied: the gate's size (`sized`, 1.0 ungated) and the file's
    # own size (st["file_sizes"], NOISE CT304 / CT304H tilt: run_backtest's trade_sizes). The file FOLDS its size into
    # t[2] as s x raw - (s - 1) x its cost, the engine then charges its cost once, so one contract's raw move is
    # (t[2] + (s - 1) x file cost + engine cost) / s (= t[2] / s + cost when the two costs agree, NOISE CT304 / CT304H);
    # the box trades that per share and carries the size in its share count.
    fsz = st.get("file_sizes") or {}
    fcost = size_cost_units(spec, units, cost, prm)
    ecost = float(spec.get("cost_pts") or 0)           # the engine's own cost, charged once a trade (0 on a $ file)
    cap = int(sz.get("max") or 0)
    days, lb_usd, lb_n, miss, seen, n_sized, n_clamp = {}, 0.0, 0, 0, set(), 0, 0
    for t, size in st.get("sized") or []:
        ei, xi = min(int(t[0]), last), min(int(t[1]), last)
        ed = dayf(ei)
        qp, rp = _on_or_before(q, ed, qk), _on_or_before(r, ed, rk)
        if not qp or not rp:
            miss += 1
            continue
        fs = float(fsz.get(id(t), 1.0) or 1.0)
        tot = float(size) * fs
        n, clamped = box_sized_shares(per, tot, cap)
        if n <= 0:
            continue
        one = (float(t[2]) + (fs - 1.0) * fcost + ecost) / fs - ecost if fs != 1.0 else float(t[2])
        usd = qqq_trade_usd(to_pts(one), rp, qp, n, sz["slip"], beta)
        if per_trade is not None:
            per_trade[id(t)] = {"sh": int(n), "usd": round(usd, 2)}
        if xi >= last:
            lb_usd += usd
            lb_n += 1
            continue
        d = dayf(xi)
        if d < WINDOW_FROM:
            continue
        seen.add(n)
        n_sized += int(abs(tot - 1.0) > 1e-12)
        n_clamp += int(clamped)
        a = days.setdefault(d, [0.0, 0])
        a[0] += usd
        a[1] += 1
    ds = sorted(days)
    ratio = ("x (QQQ close / NQ close on the entry day)" if root == "NQ"
             else "/ ES close on the entry day x beta %.3f (%s) x QQQ close" % (beta, refs.get("beta_src")))
    rule = ("QQQ $ = gross %s points (net + %s cost %g pts) %s x %d sh - 2 x $%g slippage x sh. Shares: %s (%s). "
            "No Webull commission; SEC / TAF under a cent at this size." % (
                inst, "the file's" if units == "usd" else "the run's", cost, ratio, per, sz["slip"], how, sz["src"]))
    out = {"d": ds, "p": [round(days[x][0], 2) for x in ds], "n": [int(days[x][1]) for x in ds],
           "net": round(sum(days[x][0] for x in ds), 2), "trades": int(sum(days[x][1] for x in ds)),
           "shares": per, "rule": rule, "exec_leg": exec_leg_for(leg_id),
           "via": "QQQ-on-ES beta" if root == "ES" else "QQQ/NQ ratio", "qqq_data_end": qk[-1],
           "last_bar_usd": round(lb_usd, 2), "last_bar_n": lb_n}
    if root == "ES":
        out["beta"] = beta
    if len(seen) > 1:
        out["shares_range"] = [min(seen), max(seen)]
    if n_sized:
        out["sized"] = ("%d trade(s) carry a per-trade size: the box lot x size (round, min 1)%s; points per contract "
                        "unfolded from the file's size at %g cost" % (
                            n_sized, ", %d clamped to max_shares_per_leg %d" % (n_clamp, cap) if n_clamp else "",
                            fcost))
    if miss:
        out["skipped"] = "%d trade(s) with no QQQ or %s close on or before the entry day" % (miss, root)
    return out


# ── one leg ──────────────────────────────────────────────────────────────────────────────────────────────
def master_end(spec):
    from augur_engine.data import find_master
    m = find_master(spec["instrument"], spec["timeframe"], spec["session"], spec["source"])
    if m is None and spec["source"]:
        m = find_master(spec["instrument"], spec["timeframe"], spec["session"], None)
    if m is None:
        return None, None
    return m, str(m.get("date_to") or "")


def simulate(spec, date_to=None):
    """Closed trades by New York session day from WINDOW_FROM: (days {d: [usd, n]}, info)."""
    import numpy as np
    from augur_engine.book import _leg_trades
    warm = spec.get("warm_from") or (dt.date.fromisoformat(WINDOW_FROM) - dt.timedelta(days=WARM_DAYS)).isoformat()
    leg = {k: spec[k] for k in ("strategy", "params", "instrument", "timeframe", "session", "source", "cost_pts",
                                "mult", "weight")}
    if spec.get("gate"):
        leg["gate"] = spec["gate"]
    with leg_env(spec):                                 # panel / model env vars: this leg's replay only
        _out, info = _leg_trades(leg, warm, date_to, keep_state=True)
    st = info.get("_state") or {}
    sess_idx, last = st.get("sess_idx"), st.get("last")
    fsz = st.get("file_sizes") or {}
    days, last_bar_usd, last_bar_n, n_sized = {}, 0.0, 0, 0
    for t, size in st.get("sized") or []:
        i = min(int(t[1]), last)
        # size = the gate's per-trade size (1.0 ungated); a file's own size (NOISE tilt) is already folded into t[2]
        usd = float(t[2]) * float(st["mult"]) * float(st["weight"]) * float(size)
        if i >= last:                       # exits on the master's last bar: may still be open
            last_bar_usd += usd
            last_bar_n += 1
            continue
        d = str(np.datetime_as_string(sess_idx[i], unit="D")) if sess_idx is not None else str(st["days_idx"][i])
        if d < WINDOW_FROM:
            continue
        n_sized += int(abs(float(size) * float(fsz.get(id(t), 1.0) or 1.0) - 1.0) > 1e-12)
        a = days.setdefault(d, [0.0, 0])
        a[0] += usd
        a[1] += 1
    last_day = None
    try:
        last_day = str(np.datetime_as_string(sess_idx[last], unit="D")) if sess_idx is not None else None
    except Exception:
        pass
    pq = {}
    try:
        qb = qqq_block(spec, st, per_trade=pq)
    except Exception as e:
        qb = {"reason": "QQQ conversion failed: %s: %s" % (type(e).__name__, str(e)[:200])}
    out = {"master": info.get("master"), "last_bar_usd": round(last_bar_usd, 2), "last_bar_n": last_bar_n,
           "data_end": last_day, "qqq": qb}
    try:
        out["tr"] = trade_rows(spec, st, pq)
    except Exception as e:                   # a reporting extra must never fail the series
        out["tr_error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    if n_sized:
        out["sized"] = ("%d trade(s) carry a per-trade size (%s); applied" % (
            n_sized, "the file's own size, folded into its P&L" if fsz else "the gate's size multiplier"))
    if info.get("gate"):
        out["gate"] = info["gate"]
    return days, out


def _ts(idx, i):
    import pandas as pd
    t = pd.Timestamp(idx[i])
    if t.tzinfo is not None:
        t = t.tz_convert("America/New_York")
    return t.strftime("%Y-%m-%dT%H:%M")


def trade_rows(spec, st, pq=None):
    """Board 147 (11-22): every as-if trade of the leg from WINDOW_FROM, one row each, for the ledger trade table.
    Fields: et / xt = entry / exit bar time (New York, minute), d = exit NY session day, side ("long" / "short"),
    ep = entry price, xp = exit price (reconstructed: entry +/- the gross points a contract moved; null when the file
    reports dollars), size = contracts (gate size x the file's own size), pnl = $ at the leg's book size (what the daily
    series sums), open = true when it exits on the master's last bar (may still be open), stop = null (the replay does
    not return stop levels), q = {sh, usd} the QQQ terms the Webull box would have traded (absent when no QQQ map)."""
    import numpy as np
    idx, last, sess_idx = st.get("index"), st.get("last"), st.get("sess_idx")
    if idx is None:
        return []
    fsz = st.get("file_sizes") or {}
    units = spec.get("pnl_units") or "points"
    ecost = float(spec.get("cost_pts") or 0)
    rows = []
    for t, size in st.get("sized") or []:
        ei, xi = min(int(t[0]), last), min(int(t[1]), last)
        d = str(np.datetime_as_string(sess_idx[xi], unit="D")) if sess_idx is not None else str(st["days_idx"][xi])
        if d < WINDOW_FROM:
            continue
        fs = float(fsz.get(id(t), 1.0) or 1.0)
        side = t[3] if len(t) > 3 else None
        sg = 1 if str(side).lower() in ("1", "long", "buy", "1.0") else (-1 if side is not None else None)
        ep = float(t[4]) if len(t) > 4 and t[4] is not None else None
        xp = None
        if ep is not None and sg is not None and units != "usd":
            one = (float(t[2]) + (fs - 1.0) * ecost) / fs        # one contract's net points (unfold the file's size)
            xp = round(ep + sg * (one + ecost), 2)
        r = {"et": _ts(idx, ei), "xt": _ts(idx, xi), "d": d, "side": "long" if sg == 1 else ("short" if sg == -1 else None),
             "ep": None if ep is None else round(ep, 2), "xp": xp, "size": round(float(size) * fs * float(st["weight"]), 3),
             "pnl": round(float(t[2]) * float(st["mult"]) * float(st["weight"]) * float(size), 2), "stop": None}
        if xi >= last:
            r["open"] = True
        if pq and id(t) in pq:
            r["q"] = pq[id(t)]
        rows.append(r)
    return rows


class leg_env:
    """Sets one leg's replay env vars (side-panel extension, pinned ML model) for the `with` block only and restores
    whatever was there before - another leg never sees them."""

    def __init__(self, spec):
        self.set = {}
        ext = spec.get("panel_ext") or {}
        if ext.get("env") and ext.get("path"):
            self.set[ext["env"]] = ext["path"]
        ml = spec.get("ml") or {}
        if ml.get("model_path"):
            self.set[MODEL_ENV] = ml["model_path"]
        self.prev = {}

    def __enter__(self):
        for k, v in self.set.items():
            self.prev[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def spec_key(spec, mend):
    blob = json.dumps({"s": spec, "end": mend, "w": WINDOW_FROM, "v": SCHEMA}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def build_leg(leg_id, book_leg, force=False, say=print):
    rec = {"id": leg_id, "name": book_leg.get("name") or leg_id, "run": book_leg.get("run") or "",
           "instrument": book_leg.get("instrument") or "", "size": book_leg.get("size") or "",
           "usd_per_year": book_leg.get("usd_per_year"), "src": "replay"}
    try:
        spec = leg_spec(leg_id, book_leg)
    except Exception as e:
        rec.update(kind=leg_kind(book_leg), reason=str(e))
        return rec, False
    rec["kind"] = leg_kind(book_leg, spec)
    rec.update(strategy=spec["strategy"], params_run=spec["params_run"], cost_pts=spec["cost_pts"], mult=spec["mult"],
               weight=spec["weight"], params_from=spec["params_from"], tf=spec["timeframe"], session=spec["session"],
               pnl_units=spec["pnl_units"], params=spec["params"])
    if spec.get("size"):
        rec["size"] = spec["size"]
    if spec.get("note"):
        rec["note"] = spec["note"]
    m, mend = master_end(spec)
    if m is None:
        rec["reason"] = "no %s %s %s master in the registry" % (spec["instrument"], spec["timeframe"], spec["session"].upper())
        return rec, False
    key = spec_key(spec, mend)
    cpath = os.path.join(OUT_DIR, "cache", "%s.json" % leg_id)
    cached = _load_json(cpath)
    if not force and isinstance(cached, dict) and cached.get("key") == key and "series" in cached:
        rec.update(cached["series"])
        return rec, False
    t0 = time.time()
    try:
        days, info = simulate(dict(spec, _leg_id=leg_id))
    except Exception as e:
        rec["reason"] = "replay failed: %s: %s" % (type(e).__name__, str(e)[:240])
        say("  %s FAILED %s" % (leg_id, rec["reason"]))
        traceback.print_exc()
        return rec, True
    ds = sorted(days)
    series = {"d": ds, "p": [round(days[d][0], 2) for d in ds], "n": [int(days[d][1]) for d in ds],
              "net": round(sum(days[d][0] for d in ds), 2), "trades": int(sum(days[d][1] for d in ds)),
              "data_end": info.get("data_end") or mend[:10], "master": info.get("master"),
              "last_bar_usd": info.get("last_bar_usd"), "last_bar_n": info.get("last_bar_n"),
              "built_at": _now_utc(), "secs": round(time.time() - t0, 1), "qqq": info.get("qqq")}
    ext = spec.get("panel_ext") or {}
    if ext:
        series["panel_ext"] = "%s (sha %s, to %s)" % (os.path.basename(ext["path"]), ext["sha12"], ext["end"])
        series["data_end"] = min(series["data_end"][:10], ext["end"])
    for k in ("sized", "gate", "tr", "tr_error"):
        if info.get(k):
            series[k] = info[k]
    if spec.get("ml"):
        series["ml"] = "model %s (sha %s) trained through %s, before the window from %s (%s)" % (
            os.path.basename(spec["ml"]["model_path"]), spec["ml"]["sha12"], spec["ml"]["trained_through"],
            WINDOW_FROM, spec["ml"]["from"])
    if not ds:
        series["empty"] = "no trades closed since %s" % WINDOW_FROM
    try:
        lag = (dt.date.today() - dt.date.fromisoformat(series["data_end"][:10])).days
    except Exception:
        lag = None
    if lag is not None and lag > 7:
        series["stale"] = "the %s %s master ends %s, so this series stops there (the data needs a refresh)" % (
            spec["instrument"], spec["timeframe"], series["data_end"][:10])
        if spec.get("stale_fix"):
            series["stale"] += "; " + spec["stale_fix"]
    rec.update(series)
    _write_json(cpath, {"key": key, "series": series})
    say("  %-10s %s  %3d trades  net %+10.2f  data to %s  (%.1fs)" % (
        leg_id, spec["strategy"], series["trades"], series["net"], series["data_end"], series["secs"]))
    return rec, True


# ── the whole table ──────────────────────────────────────────────────────────────────────────────────────
def distinct_legs(table):
    legs = {}
    for _k, b in (table.get("books") or {}).items():
        for l in b.get("legs") or []:
            if l.get("id") and l["id"] not in legs:
                legs[l["id"]] = l
    return legs


def requested_legs(db):
    try:
        snap = db.collection("users").document(UID).collection("meta").document("book_asif_req").get()
        d = snap.to_dict() if snap.exists else None
        return [str(x) for x in ((d or {}).get("legs") or [])]
    except Exception:
        return []


# ── nightly refresh of the side-panel extension panels ───────────────────────────────────────────────────
def stock_master_end():
    """The last session (YYYY-MM-DD) of the SPY 5m RTH stock master (alpaca_split_rth) - the clock PICK6 runs on and
    the stocks the three panels are pulled with; None when not registered."""
    from augur_engine.data import find_master
    m = find_master("SPY", "5m", "rth", "alpaca_split_rth")
    return str(m.get("date_to") or "")[:10] or None if m else None


def _last_completed_session_et(now=None):
    """Yesterday in New York: the panel builders pull daily bars of COMPLETED sessions only (before midnight ET)."""
    from zoneinfo import ZoneInfo
    now = now or dt.datetime.now(ZoneInfo("America/New_York"))
    return (now.date() - dt.timedelta(days=1)).isoformat()


def panels_to_refresh(leg_ids, master_end, stamp, today_cap):
    """[(leg, what)] whose extension panel ends before the stock master's last COMPLETED session and that were not
    already tried for that session (the stamp: one try per panel per master day, so the 30-min task never loops)."""
    if not master_end:
        return []
    target = min(master_end, today_cap)
    out = []
    for lid in leg_ids:
        if lid not in _PANEL_EXT:
            continue
        info = panel_ext_info(*_PANEL_EXT[lid])
        end = info.get("end") or ""
        if end >= target or (stamp or {}).get(lid) == target:
            continue
        out.append((lid, _PANEL_BUILD[lid]))
    return out


def refresh_ext_panels(leg_ids, say=print, runner=None):
    """Re-run tools/asif_ext_panels.py for each stale panel (see panels_to_refresh). A failure is logged, never fatal:
    the leg then reads the older panel and its data_end says how far it got."""
    import subprocess
    try:
        mend = stock_master_end()
    except Exception as e:
        say("panel refresh: no stock master (%s) - skipped" % e)
        return []
    stamp = _load_json(PANEL_STAMP, {}) or {}
    target = min(mend or "", _last_completed_session_et())
    todo = panels_to_refresh(leg_ids, mend, stamp, _last_completed_session_et())
    done = []
    for lid, what in todo:
        cmd = [sys.executable, os.path.join(HERE, "tools", "asif_ext_panels.py"), what]
        say("panel refresh: %s panel ends before %s - %s" % (lid, target, " ".join(cmd[1:])))
        t0 = time.time()
        try:
            if runner:
                rc = runner(cmd)
            else:
                rc = subprocess.run(cmd, cwd=HERE, timeout=PANEL_BUILD_TIMEOUT).returncode
        except Exception as e:
            rc = "%s: %s" % (type(e).__name__, e)
        say("panel refresh: %s -> %s (%.0fs)" % (what, rc, time.time() - t0))
        stamp[lid] = target
        stamp[lid + "_rc"] = str(rc)
        stamp[lid + "_at"] = _now_utc()
        done.append((lid, rc))
    if todo:
        _write_json(PANEL_STAMP, stamp)
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=BOOK_TABLE)
    ap.add_argument("--legs", default="", help="comma list of leg ids (default: every leg of every book)")
    ap.add_argument("--force", action="store_true", help="rebuild every leg and publish")
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--no-panel-refresh", action="store_true",
                    help="skip re-pulling the PICK6 / OPUS86a / GLDNIGHT extension panels")
    ap.add_argument("--panels-only", action="store_true",
                    help="only refresh the stale extension panels, then exit")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    table = _load_json(a.src)
    if not isinstance(table, dict) or not table.get("books"):
        print("book table missing or empty: %s" % a.src)
        return 2
    legs = distinct_legs(table)
    db = None
    if not a.no_publish:
        try:
            db = _db()
            for r in requested_legs(db):
                if r not in legs:
                    print("requested leg %s is not in the book table - skipped" % r)
        except Exception as e:
            print("Firestore not reachable (%s) - local file only" % e)
            db = None
    want = [x.strip() for x in a.legs.split(",") if x.strip()] or list(legs)
    if not a.no_panel_refresh:
        refresh_ext_panels([x for x in want if x in legs])
    if a.panels_only:
        return 0
    prev =_load_json(os.path.join(OUT_DIR, "book_asif.json"), {}) or {}
    out_legs = dict(prev.get("legs") or {})
    changed = False
    print("book as-if: %d distinct legs in %d books, window from %s" % (len(legs), len(table["books"]), WINDOW_FROM))
    for lid in want:
        if lid not in legs:
            print("  %s not in the book table" % lid)
            continue
        rec, ch = build_leg(lid, legs[lid], force=a.force)
        if out_legs.get(lid) != rec:
            changed = True
        out_legs[lid] = rec
    for lid in list(out_legs):          # a leg no longer in any book drops out
        if lid not in legs:
            del out_legs[lid]
            changed = True
    th = hashlib.sha1(json.dumps(table.get("books"), sort_keys=True, default=str).encode()).hexdigest()[:12]
    if th != prev.get("book_table_hash"):
        changed = True
    ends = sorted(r.get("data_end") for r in out_legs.values() if r.get("data_end"))
    doc = {"schema": SCHEMA, "generated_at": _now_utc() if changed or a.force else prev.get("generated_at", _now_utc()),
           "window_from": WINDOW_FROM, "data_end": ends[-1] if ends else None,
           "data_end_min": ends[0] if ends else None, "book_table_hash": th,
           "note": "simulated as-if: each leg's pinned champion on current data with its run's cost, closed trades by "
                   "New York day; never the account",
           "legs": out_legs}
    _write_json(os.path.join(OUT_DIR, "book_asif.json"), doc)
    ok = sum(1 for r in out_legs.values() if r.get("d") is not None)
    bad = {k: r.get("reason") for k, r in out_legs.items() if r.get("reason")}
    print("wrote %s: %d legs with a series, %d without%s" % (os.path.join(OUT_DIR, "book_asif.json"), ok, len(bad),
          "".join("\n  %s: %s" % kv for kv in bad.items())))
    if db is not None and (changed or a.force):
        ref = db.collection("users").document(UID).collection("meta")
        trs = {lid: r.get("tr") for lid, r in out_legs.items() if r.get("tr") is not None}
        slim = dict(doc, legs={lid: {k: v for k, v in r.items() if k != "tr"} for lid, r in out_legs.items()})
        ref.document("book_asif").set(slim)
        for lid, rows in trs.items():      # board 147: per-trade rows, one doc per leg (book_asif_trades_<leg>)
            for j in range(0, max(len(rows), 1), TRADES_PER_DOC):
                ref.document("book_asif_trades_%s%s" % (lid, "" if j == 0 else "_%d" % (j // TRADES_PER_DOC))).set(
                    {"leg": lid, "window_from": WINDOW_FROM, "generated_at": doc["generated_at"], "part": j // TRADES_PER_DOC,
                     "parts": -(-len(rows) // TRADES_PER_DOC) or 1, "rows": rows[j:j + TRADES_PER_DOC]})
        try:
            ref.document("book_asif_req").set({"legs": [], "cleared_at": _now_utc()})
        except Exception:
            pass
        print("published users/<uid>/meta/book_asif (%d bytes) + %d per-leg trade docs" % (len(json.dumps(slim, default=str)), len(trs)))
    elif db is not None:
        print("nothing changed - not published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
