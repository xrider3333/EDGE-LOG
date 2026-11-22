r"""tools/run_trades_series.py -- one run's WALK-FORWARD OOS TRADE LIST + DAILY SERIES (owner 11-22, board 131 / 132).

WHY. The past-run view wants (131) a DAILY P&L chart and (132) a "what if it traded 1 / 2 / 3 % of the account per
trade" sizing table. Both need the run's walk-forward out-of-sample chain as TRADES WITH TIMES, and the run doc
cannot give that: validate.wf_oos.equity is DOWNSAMPLED (~200 points for any trade count), fold xi/ei (when present)
are SLICE offsets, and old docs carry neither. So the chain is REPLAYED - every fold's saved champion on that fold's
own out-of-sample slice - and kept only when it reproduces the doc.

HOW (the same discipline as tools/backfill_wf_oos.py, whose plan/fold-match helpers this reuses):
  * plan      backfill_wf_oos.rebuild_plan(doc): window PINNED to validate.windows.optimize, fold bounds from the
              doc's own train_bars / test_bars, params off each fold's own row.
  * tape      today's master first. Fold rows that carry test_start_ts / test_end_ts are re-located BY TIMESTAMP
              (resolve_fold_bounds). Rows with bar indices only need a tape whose window has EXACTLY the doc's
              bar count (expect_n): a fill since the run shifts every later index (FOLD BOUNDS = BAR INDICES), so
              when today's master no longer matches, the dated backups under TAPE_DIRS with the master's own file
              name are tried (newest first) and the first one whose window count equals expect_n is used. A tape is
              never chosen by anything but the count, and the replay must still reproduce every fold on it.
  * arms      the run's own era first (warm 300 sessions from 2026-09-20, cold before), then the other arm.
  * verify    EVERY fold must match the doc's oos_trades / oos_pnl / oos_pf / oos_wins (backfill tolerances), AND
              the chain total must equal the doc's fold sum to the DOLLAR (|replay - doc| x multiplier <= $1).
              One miss = nothing written for the run, and the log says which fold and by how much.
  * code      --engine-root <dir> puts a pinned checkout first on sys.path (REPLAY A RUN = PIN THE CODE): a
              `git worktree add --detach <dir> <commit before the run>` copy. Without it today's code replays.

WHAT EACH TRADE CARRIES (columnar, so the Firestore doc stays small):
  e / x   entry / exit bar time, epoch SECONDS (UTC)        s   side +1 / -1 (null when the tuple has none)
  p       NET points at the run's own 1-contract unit, after the run's cost_pts (exactly the engine's chain value)
  z       the file's own per-trade size where it reports one (NOISE's tilt), else 1 - so p / z is per contract
  r       initial risk in points (|entry - initial stop|) from the strategy's return_levels rows, else null.
          A pinned replay from before return_levels (2026-10-31) takes r from the CURRENT file run on the same tape,
          folds, arm and params, matched on entry time + side (>= 95 pct must match or the run is refused);
          risk_source on the doc and on sizing says which: stop / stop_from_current_file / median
  f       walk-forward fold number
DAILY: {d: [YYYY-MM-DD], p: [$ a day at 1 contract], n: [trades closed that day]}, every weekday of the WF span,
zero days included (the house four-numbers convention). A trade is dated by its EXIT on the New York session day
(an ETH exit at or after 18:00 ET belongs to the next session).

WHERE IT GOES
  local    C:/EdgeLog/run_series/<run>_wf.json   (always; the cache the desktop backfill fills)
  --write  Firestore users/<uid>/runs/<run>/series/wf  (+ wf_t1, wf_t2 ... trade chunks if the doc would pass
           ~900 KB - the 1 MiB doc cap). Written only after the verify passes. Never the run doc itself.
  --requests  reads users/<uid>/meta/run_series_req {runs: [...]} (the page writes it from "build daily series"),
           builds those runs, and removes the ones it settled (built, or refused with a reason stored on
           series/wf_status so the page can say why instead of asking again).

    python tools/run_trades_series.py 314 422 532                dry: replay, verify, write the local json only
    python tools/run_trades_series.py 314 422 532 --write        ...and publish to Firestore
    python tools/run_trades_series.py --requests --write         serve the page's requests
    python tools/run_trades_series.py 335 --engine-root C:/EdgeLog/replay_wt/f681adb7 --tape <csv>

Read-only on the master registry (find_master reads it; nothing writes it) and on optimizer_history.db. Never prints
serviceAccount.json. Heavy: a 1m ETH run replays 8 folds of ~400k bars, minutes each; run many on the desktop.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import sys
import time


def _early_engine_root(argv):
    """--engine-root must be on sys.path BEFORE augur_engine is imported anywhere."""
    for i, a in enumerate(argv):
        if a == "--engine-root" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--engine-root="):
            return a.split("=", 1)[1]
    return None


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# EDGELOG_SHARED = the data checkout (uploads, db, --pin git dir) on a box other than the Razer (desktop: C:\EdgeLog\repo)
SHARED = os.environ.get("EDGELOG_SHARED") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
_ER = _early_engine_root(sys.argv) if __name__ == "__main__" else None
for _p in ([ROOT] + ([_ER] if _ER else [])):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
    elif _p == _ER:
        sys.path.remove(_p)
        sys.path.insert(0, _p)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
OUT_DIR = os.environ.get("EDGELOG_RUN_SERIES_DIR", r"C:\EdgeLog\run_series")
TAPE_DIRS = (r"C:\EdgeLog\_research_cache", r"C:\EdgeLog\_anatomy_cache\prefill",
             r"C:\EdgeLog\manager\paperwb_1007")
TOOL = "tools/run_trades_series.py v1"
WARM_STARTS_FROM = "2026-09-20"   # = backfill_wf_oos.WARM_STARTS_FROM (7a95b816)
REPLAY_WT = r"C:/EdgeLog/replay_wt"   # pinned detached checkouts, one per commit (git worktree add --detach)
RUN_TZ = "-07:00"                 # run docs stamp the runner PC's local time (MST, no DST)
USD_TOL = 1.0                 # chain total vs the doc's fold sum, dollars
DOC_BUDGET = 900_000          # bytes of JSON per Firestore doc (cap 1 MiB)
ENTRY_BUDGET = 15_000         # index_entries() per doc: Firestore caps a doc at 40,000 index entries and counts about
                              # twice this estimate (#422 at 20.4k estimated was refused, at 17.6k it was taken)
ETH_ROLL_H = 18               # ET hour an ETH session rolls to the next day


# ── pure helpers (tested) ────────────────────────────────────────────────────────────────────────────────
def session_day(ts, eth=False):
    """New York session date (YYYY-MM-DD) of a bar time. On an ETH tape a bar at/after 18:00 ET opens the NEXT
    session; RTH and daily tapes use the calendar date."""
    import pandas as pd
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("US/Eastern")
    t = t.tz_convert("US/Eastern")
    d = t.normalize()
    if eth and t.hour >= ETH_ROLL_H:
        d = d + pd.Timedelta(days=1)
        while d.weekday() >= 5:
            d = d + pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def daily_from_trades(exit_days, usd, span_from, span_to):
    """{d, p, n}: every weekday from span_from to span_to (plus any non-weekday a trade closed on), zero-filled."""
    import pandas as pd
    acc, cnt = {}, {}
    for d, u in zip(exit_days, usd):
        acc[d] = acc.get(d, 0.0) + float(u)
        cnt[d] = cnt.get(d, 0) + 1
    days = set(pd.bdate_range(span_from, span_to).strftime("%Y-%m-%d")) | set(acc)
    ds = sorted(days)
    return {"d": ds, "p": [round(acc.get(d, 0.0), 2) for d in ds], "n": [cnt.get(d, 0) for d in ds]}


def risk_from_levels(levels, n_trades, entry_bars=None):
    """Initial risk (points) per trade from a strategy's return_levels rows, or None when they do not line up.
    A warm replay trims trades that entered before the stretch but may leave `levels` whole, so a longer levels
    list is aligned on its TAIL and checked against the trades' own entry bars when given (offset-free: the gaps
    between consecutive entry bars must agree)."""
    if not isinstance(levels, list) or n_trades == 0:
        return None
    if len(levels) < n_trades:
        return None
    rows = levels[-n_trades:]
    if entry_bars is not None and len(entry_bars) == n_trades and n_trades > 1:
        try:
            lb = [int(r.get("entry_bar")) for r in rows]
            if [b - lb[0] for b in lb] != [int(e) - int(entry_bars[0]) for e in entry_bars]:
                return None
        except Exception:
            return None
    out = []
    for r in rows:
        try:
            rk = r.get("risk")
            if rk is None and r.get("entry") is not None and r.get("stop") is not None:
                rk = float(r["entry"]) - float(r["stop"])
            rk = abs(float(rk))
            out.append(rk if math.isfinite(rk) and rk > 0 else None)
        except Exception:
            out.append(None)
    return out

STOP_MATCH_MIN = 0.95         # current file's trades must line up with the pinned replay's on this share (entry, side)


def match_stops(trades, current):
    """Stops for a pinned replay whose code returned none (REPLAY A RUN = PIN THE CODE: a pin from before the
    2026-10-31 return_levels overlay), read off the CURRENT strategy file's own trades on the same bars and params.
    `trades`: the payload's trades (dicts with e, s); `current`: dicts with e, s, r from the current file.
    A trade matches on the same entry time AND side (side compared only when both carry one); several current trades
    at one entry are taken in order. -> (risks list aligned to `trades` (None = unmatched), matched count)."""
    pool = {}
    for c in current:
        pool.setdefault(int(c["e"]), []).append(c)
    out, hit = [], 0
    for t in trades:
        cands = pool.get(int(t["e"]), [])
        k = next((i for i, c in enumerate(cands)
                  if t.get("s") is None or c.get("s") is None or int(c["s"]) == int(t["s"])), None)
        if k is None:
            out.append(None)
            continue
        c = cands.pop(k)
        hit += 1
        rk = c.get("r")
        out.append(round(float(rk), 6) if rk is not None and float(rk) > 0 else None)
    return out, hit


def apply_current_stops(payload, current, source, min_match=STOP_MATCH_MIN):
    """Fill payload trades' missing r from `current` (match_stops). Refuses (Refused) when fewer than `min_match` of
    the trades line up - then the current file is not the run's rule and its stops would be a guess. Trades that do
    not match keep r null (the sizing falls back to the median losing trade for them and counts them)."""
    tr = payload["trades"]
    n = len(tr["e"])
    rows = [{"e": tr["e"][i], "s": tr["s"][i]} for i in range(n)]
    risks, hit = match_stops(rows, current)
    pct = (hit / n) if n else 0.0
    if n == 0 or pct < min_match:
        raise Refused("stops from the current file refused: %d of %d trades (%.1f pct) match on entry time and side, "
                      "below %.0f pct - the current %s is not the rule the run traded"
                      % (hit, n, 100.0 * pct, 100.0 * min_match, source))
    tr["r"] = [tr["r"][i] if tr["r"][i] is not None else risks[i] for i in range(n)]
    nz = sum(1 for v in tr["r"] if v is not None)
    info = {"source": source, "matched": hit, "n": n, "pct": round(100.0 * pct, 2), "current_trades": len(current),
            "with_stop": nz, "median_fallback": n - nz}
    payload["risk_n"] = nz
    payload["risk_src"] = "stop_from_current_file" if nz else None
    payload["risk_source"] = "stop_from_current_file" if nz else "median"
    payload["risk_match"] = info
    return info


def verify_chain(matches, mult, wf_net_pts=None):
    """-> (ok, info). Every fold ok AND |sum(replayed) - sum(saved)| x mult <= USD_TOL. `wf_net_pts`, the doc's
    validate.wf_oos.net (rounded to 0.1 pts), is checked too when present (within its rounding + 0.01)."""
    folds = []
    rep = doc = 0.0
    for m in matches:
        sv = m.get("saved") or {}
        rep += float(m.get("oos_pnl") or 0.0)
        doc += float(sv.get("net") or 0.0)
        folds.append({"f": m["fold"], "ok": bool(m["ok"]), "trades": m.get("oos_trades"),
                      "doc_trades": sv.get("trades"), "net": round(float(m.get("oos_pnl") or 0.0), 6),
                      "doc_net": round(float(sv.get("net") or 0.0), 6), "why": m.get("reason")})
    d_usd = (rep - doc) * float(mult)
    ok = all(f["ok"] for f in folds) and abs(d_usd) <= USD_TOL
    why = None
    if not all(f["ok"] for f in folds):
        bad = [f for f in folds if not f["ok"]]
        why = "%d of %d fold(s) do not reproduce: %s" % (len(bad), len(folds),
                                                         "; ".join("fold %s %s" % (f["f"], f["why"]) for f in bad))
    elif abs(d_usd) > USD_TOL:
        why = "chain total off by $%.2f (> $%.0f)" % (d_usd, USD_TOL)
    if ok and wf_net_pts is not None:
        try:
            if abs(rep - float(wf_net_pts)) > 0.06:
                ok, why = False, "replayed %.3f pts vs validate.wf_oos.net %.1f" % (rep, float(wf_net_pts))
        except (TypeError, ValueError):
            pass
    return ok, {"replay_pts": round(rep, 6), "doc_pts": round(doc, 6), "replay_usd": round(rep * mult, 2),
                "doc_usd": round(doc * mult, 2), "d_usd": round(d_usd, 4), "wf_oos_net_pts": wf_net_pts,
                "folds": folds, "why": why}


def series_payload(run_id, plan, mult, trades, daily, verify, src, tape, arm, risk_src, engine_root=None):
    """The stored shape (see the module docstring)."""
    cols = {k: [] for k in ("e", "x", "s", "p", "z", "r", "f", "d")}
    for t in trades:
        for k in cols:
            cols[k].append(t.get(k))
    nz = sum(1 for v in cols["r"] if v is not None)
    return {"v": 1, "run": int(run_id), "tool": TOOL, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "src": src, "tape": tape, "arm": arm, "engine_root": engine_root,
            "strategy": plan.get("strategy"), "instrument": plan.get("instrument"),
            "timeframe": plan.get("timeframe"), "mult": float(mult), "cost_pts": float(plan.get("cost_pts") or 0.0),
            "from": daily["d"][0] if daily["d"] else None, "to": daily["d"][-1] if daily["d"] else None,
            "n_trades": len(trades), "risk_src": (risk_src if nz else None), "risk_n": nz,
            "risk_source": ("stop" if nz else "median"),
            "verify": verify, "daily": daily, "trades": cols}


def add_sizing(payload):
    """payload["sizing"]: FIXED 1 / RISK 1 / 2 / 3 % read through augur_engine.risk_sizing (board 132), every column
    on the series' own days (the curve is `eq`, one value per payload["daily"]["d"] entry)."""
    from augur_engine.risk_sizing import sizing_table
    tr = payload["trades"]
    trades = [{"e": tr["e"][i], "x": tr["x"][i], "p": tr["p"][i], "z": tr["z"][i], "r": tr["r"][i], "d": tr["d"][i]}
              for i in range(len(tr["p"]))]
    days = payload["daily"]["d"]
    tab = sizing_table(trades, days, point_value=payload["mult"], cost_pts=payload["cost_pts"])
    for c in tab["cols"].values():
        if c.pop("d", None) != days:
            raise Refused("sizing curve days do not line up with the daily series")
    rs = payload.get("risk_source") or ("stop" if payload.get("risk_n") else "median")
    tab["risk_source"] = rs                       # stop / stop_from_current_file / median (where r came from)
    tab["risk_match"] = payload.get("risk_match")
    payload["sizing"] = tab
    return payload


def index_entries(o):
    """Rough Firestore index-entry count of a doc: 2 per scalar, distinct values + 2 per array (array-contains
    indexes each DISTINCT element - a column of real stops costs ~1 entry a trade where an all-null one cost 1)."""
    if isinstance(o, dict):
        return sum(index_entries(v) for v in o.values())
    if isinstance(o, list):
        return len(set(json.dumps(x, sort_keys=True, default=str) for x in o)) + 2
    return 2


def chunk_payload(payload, budget=DOC_BUDGET, entry_budget=ENTRY_BUDGET):
    """-> [(doc_id, dict)]: 'wf' alone when it fits (bytes AND index entries), else 'wf' (everything but the trades,
    plus t_chunks) and wf_t1..wf_tk each holding a contiguous slice of the trade columns."""
    size = len(json.dumps(payload, separators=(",", ":"), default=str))
    if size <= budget and index_entries(payload) <= entry_budget:
        return [("wf", dict(payload, t_chunks=0, bytes=size))]
    tr = payload["trades"]
    n = len(tr["p"])
    head = {k: v for k, v in payload.items() if k != "trades"}
    per_trade = max(1, (size - len(json.dumps(head, default=str))) // max(1, n))
    per_entry = max(1.0, index_entries(tr) / max(1, n))
    step = max(1, min(int(budget * 0.9) // per_trade, int(entry_budget * 0.9 / per_entry)))
    chunks = []
    for i, a in enumerate(range(0, n, step), 1):
        chunks.append(("wf_t%d" % i, {"run": payload["run"], "i": i, "a": a,
                                       "trades": {k: v[a:a + step] for k, v in tr.items()}}))
    head["t_chunks"] = len(chunks)
    head["bytes"] = size
    return [("wf", head)] + chunks


# ── replay ───────────────────────────────────────────────────────────────────────────────────────────────
class Refused(Exception):
    pass


def _say(*a):
    print(*a, flush=True)


def _setup_data_env():
    import augur_engine.data as _data
    import augur_engine.paths as _paths
    up = os.environ.get("EDGELOG_UPLOADS") or os.path.join(SHARED, "augur_uploads")
    dbp = os.environ.get("EDGELOG_DB_PATH") or os.path.join(SHARED, "optimizer_history.db")
    _data.UPLOADS = up
    _paths.DB_PATH = _data.DB_PATH = dbp
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")


def candidate_tapes(master, explicit=None):
    """Today's master first, then (newest first) every backup under TAPE_DIRS carrying the master's own file name
    (or a name starting with its stem): the dated copies the data chats take before each fill / splice."""
    import augur_engine.data as _data
    if explicit:
        return [("given", p) for p in explicit]
    out = [("today", os.path.join(_data.UPLOADS, master["filename"]))]
    stem = os.path.splitext(master["filename"])[0]
    seen = set()
    found = []
    for d in TAPE_DIRS:
        for p in glob.glob(os.path.join(d, "**", stem + "*.csv"), recursive=True):
            rp = os.path.normcase(os.path.abspath(p))
            if rp in seen:
                continue
            seen.add(rp)
            found.append(p)
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return out + [("backup", p) for p in found]


def _evaluator(mod, arrays, cost_pts, warm_days):
    import inspect
    from augur_engine.auto import make_slice_evaluator
    if "warm_days" in inspect.signature(make_slice_evaluator).parameters:
        return make_slice_evaluator(mod, arrays, cost_pts, warm_days=warm_days)
    if warm_days:
        return None                       # a pre-warm build cannot score a warm era
    return make_slice_evaluator(mod, arrays, cost_pts)


def _wants_levels(mod):
    import inspect
    try:
        return "return_levels" in inspect.signature(mod.run_backtest).parameters
    except Exception:
        return False


def replay_run(doc, tapes=None, log=_say):
    """-> dict(plan, matches, trades, verify, tape, arm, risk_src, index_eth). Raises Refused with the reason."""
    import pandas as pd
    from tools import backfill_wf_oos as B
    from augur_engine.strategies import load_strategy
    from augur_engine.auto import _auto_space_from_params
    from augur_engine.data import find_master
    plan, reason = B.rebuild_plan(doc)
    if reason:
        raise Refused(reason)
    plan.setdefault("timestamp", doc.get("timestamp"))
    mult = float(doc.get("multiplier") or 0.0)
    if mult <= 0:
        raise Refused("no multiplier on the doc")
    mod = load_strategy(plan["strategy"])
    pkeys = list(_auto_space_from_params(getattr(mod, "DEFAULT_PARAMS", {}) or {}).keys())
    params_list, reason = B.fold_params(pkeys, [fb["row"] for fb in plan["folds"]])
    if reason:
        raise Refused(reason)
    levels = _wants_levels(mod)
    master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        raise Refused("no master for %s %s %s %s" % (plan["instrument"], plan["timeframe"], plan["session"],
                                                     plan["source"]))
    eth = str(plan["session"]).lower() == "eth"
    has_ts = all(fb["row"].get("test_start_ts") is not None and fb["row"].get("test_end_ts") is not None
                 for fb in plan["folds"])
    tried = []
    for kind, path in candidate_tapes(master, tapes):
        try:
            arrays, folds = _tape_folds(plan, master, path, has_ts)
        except ValueError as e:
            tried.append("%s (%s): %s" % (kind, path, e))
            continue
        n = len(arrays["close"])
        log("  tape %s %s: %d bars %s..%s" % (kind, path, n, plan["date_from"], plan["date_to"]))
        res = _replay_on(plan, mod, arrays, folds, params_list, levels, mult, eth, log)
        if res is not None:
            res.update(tape=(None if kind == "today" else path), tape_kind=kind, plan=plan, mult=mult)
            return res
        tried.append("%s (%s): the tape matched but the folds did not reproduce" % (kind, path))
    raise Refused("no tape reproduces the run | " + " | ".join(tried[-6:]))


def _tape_folds(plan, master, path, has_ts):
    """-> (arrays, folds) for one tape, or ValueError(why): rows with timestamps are re-located by time, rows with bar
    indices only need the window to hold EXACTLY the doc's bar count (FOLD BOUNDS = BAR INDICES)."""
    from tools import backfill_wf_oos as B
    from augur_engine.data import load_master_arrays
    m2 = dict(master, filename=os.path.abspath(path))
    try:
        arrays = load_master_arrays(m2, date_from=plan["date_from"], date_to=plan["date_to"])
    except Exception as e:
        raise ValueError("load failed %s" % e)
    n = len(arrays["close"])
    if has_ts:
        try:
            return arrays, B.resolve_fold_bounds(dict(plan, today_fp=None), arrays.get("index"), n)
        except Exception as e:
            raise ValueError(str(e)[:160])
    if n != plan["expect_n"]:
        raise ValueError("%d bars, doc expects %d" % (n, plan["expect_n"]))
    return arrays, plan["folds"]


def _replay_on(plan, mod, arrays, folds, params_list, levels, mult, eth, log):
    import pandas as pd
    from tools import backfill_wf_oos as B
    index = pd.DatetimeIndex(arrays["index"])
    primary = plan.get("warm_days")
    if primary is None:                  # a pinned (pre-v2) rebuild_plan carries no era: read it off the stamp
        primary = 300 if str(plan.get("timestamp") or "")[:10] >= WARM_STARTS_FROM else 0
    primary = int(primary or 0)
    arms = [primary, 0 if primary else 300]
    for wd in arms:
        ev = _evaluator(mod, arrays, plan["cost_pts"], wd)
        if ev is None:
            continue
        cap = {}

        def ev2(a, b, params, keep_trades=True, warm=False, _ev=ev, _wd=wd):
            # the arm decides warm vs cold, not the caller: a pinned (pre-v2) build_fold_match never asks
            om = (_ev(a, b, params, keep_trades=keep_trades, warm=True) if _wd > 0
                  else _ev(a, b, params, keep_trades=keep_trades))
            cap["om"] = om
            return om
        import inspect
        bfm_warm = "warm_days" in inspect.signature(B.build_fold_match).parameters
        matches, raw = [], []
        for fb, params in zip(folds, params_list):
            p = dict(params, return_levels=True) if levels else params
            cap.clear()
            m = (B.build_fold_match(ev2, index, fb, p, warm_days=wd) if bfm_warm
                 else B.build_fold_match(ev2, index, fb, p))
            matches.append(m)
            raw.append((fb, cap.get("om")))
            log("    [%s] fold %d  doc %5s tr %12.3f | replay %5s tr %12.3f  %s"
                % ("warm" if wd else "cold", m["fold"], (m["saved"] or {}).get("trades"),
                   float((m["saved"] or {}).get("net") or 0.0), m["oos_trades"], float(m["oos_pnl"] or 0.0),
                   "OK" if m["ok"] else "MISS"))
            if not m["ok"]:
                break
        ok, info = verify_chain(matches, mult, ((plan.get("_wf_net"))))
        if len(matches) == len(folds) and ok:
            trades, rsrc = _trades_from(raw, index, eth, levels)
            return {"matches": matches, "trades": trades, "verify": info,
                    "arm": ("warm %d" % wd) if wd else "cold", "risk_src": rsrc, "eth": eth}
        log("    arm %s: %s" % ("warm" if wd else "cold", info.get("why") or "fold miss"))
    return None


def _trades_from(raw, index, eth, levels):
    import pandas as pd
    out = []
    any_risk = False
    n = len(index)
    for fb, om in raw:
        tl = list((om or {}).get("trades") or [])
        sizes = (om or {}).get("trade_sizes")
        sizes = sizes if isinstance(sizes, list) and len(sizes) == len(tl) else None
        rk = risk_from_levels((om or {}).get("levels"), len(tl), [t[0] for t in tl]) if levels else None
        any_risk = any_risk or bool(rk and any(v is not None for v in rk))
        a, b = int(fb["te_s"]), int(fb["te_e"])
        for k, t in enumerate(tl):
            i, j = a + int(t[0]), a + int(t[1])
            if not (a <= i < b):
                raise Refused("fold %s trade %d enters at bar %d outside its slice [%d, %d)" % (fb["fold"], k, i, a, b))
            et, xt = pd.Timestamp(index[min(i, n - 1)]), pd.Timestamp(index[min(j, n - 1)])
            side = None
            if len(t) > 3:
                try:
                    sv = int(t[3])
                    side = sv if sv in (1, -1) else None
                except (TypeError, ValueError):
                    side = None
            out.append({"e": int(et.timestamp()), "x": int(xt.timestamp()), "s": side,
                        "p": round(float(t[2]), 6), "z": (round(float(sizes[k]), 6) if sizes else 1),
                        "r": (round(rk[k], 6) if rk and rk[k] is not None else None), "f": int(fb["fold"]),
                        "d": session_day(xt, eth)})
    return out, ("stop" if any_risk else None)


def current_file_stops(doc, payload, log=_say):
    """Run TODAY's strategy file with return_levels on the SAME tape, folds, arm and champion params the payload was
    replayed on, and return its trades as [{e, s, r}] (no verify: the match against the pinned trades is the check).
    Raises Refused when the current file exposes no stop levels or the tape does not line up."""
    import pandas as pd
    from tools import backfill_wf_oos as B
    import augur_engine.data as _data
    from augur_engine.strategies import load_strategy
    from augur_engine.auto import _auto_space_from_params
    plan, reason = B.rebuild_plan(doc)
    if reason:
        raise Refused(reason)
    mod = load_strategy(plan["strategy"])
    if not _wants_levels(mod):
        raise Refused("the current %s has no return_levels" % plan["strategy"])
    pkeys = list(_auto_space_from_params(getattr(mod, "DEFAULT_PARAMS", {}) or {}).keys())
    params_list, reason = B.fold_params(pkeys, [fb["row"] for fb in plan["folds"]])
    if reason:
        raise Refused(reason)
    master = _data.find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        raise Refused("no master for the current-file stop pass")
    path = payload.get("tape") or os.path.join(_data.UPLOADS, master["filename"])
    has_ts = all(fb["row"].get("test_start_ts") is not None and fb["row"].get("test_end_ts") is not None
                 for fb in plan["folds"])
    try:
        arrays, folds = _tape_folds(plan, master, path, has_ts)
    except ValueError as e:
        raise Refused("current-file stop pass: tape %s: %s" % (path, e))
    arm = str(payload.get("arm") or "cold")
    wd = int(arm.split()[1]) if arm.startswith("warm") else 0
    ev = _evaluator(mod, arrays, plan["cost_pts"], wd)
    if ev is None:
        raise Refused("current-file stop pass: no evaluator for arm %s" % arm)
    index = pd.DatetimeIndex(arrays["index"])
    raw = []
    for fb, params in zip(folds, params_list):
        p = dict(params, return_levels=True)
        om = (ev(fb["te_s"], fb["te_e"], p, keep_trades=True, warm=True) if wd
              else ev(fb["te_s"], fb["te_e"], p, keep_trades=True))
        raw.append((fb, om))
    trades, _ = _trades_from(raw, index, str(plan["session"]).lower() == "eth", True)
    log("  current %s (%s, %s): %d trades, %d with a stop"
        % (plan["strategy"], arm, os.path.basename(path), len(trades), sum(1 for t in trades if t["r"] is not None)))
    return [{"e": t["e"], "s": t["s"], "r": t["r"]} for t in trades], plan["strategy"]


def fill_missing_stops(doc, payload, log=_say):
    """When the replay's code returned no stop for some trades (a pin from before return_levels), take them from the
    CURRENT file (current_file_stops + apply_current_stops). No-op when every trade already has one, or when the
    current file has no stop rule either (the median fallback is then the honest read)."""
    tr = payload["trades"]
    if all(v is not None for v in tr["r"]):
        return None
    try:
        cur, name = current_file_stops(doc, payload, log)
    except Refused as e:
        if "has no return_levels" in str(e):
            log("  %s - risk stays the median losing trade" % e)
            return None
        raise
    info = apply_current_stops(payload, cur, "current " + name)
    log("  stops from the current file: %d of %d trades matched (%.2f pct), %d carry a stop, %d on the median"
        % (info["matched"], info["n"], info["pct"], info["with_stop"], info["median_fallback"]))
    return info


# ── Firestore ────────────────────────────────────────────────────────────────────────────────────────────
def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = next((p for p in (os.path.join(ROOT, "serviceAccount.json"), os.path.join(SHARED, "serviceAccount.json"))
                 if os.path.isfile(p)), None)
    if not cred:
        raise SystemExit("serviceAccount.json not found (checked this checkout and the shared one)")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def _run_ref(db, rid):
    return db.collection("users").document(UID).collection("runs").document(str(rid))


def publish(db, rid, docs, log=_say):
    col = _run_ref(db, rid).collection("series")
    for doc_id, body in docs:
        col.document(doc_id).set(body)
    col.document("wf_status").set({"state": "built", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                   "tool": TOOL, "docs": [d for d, _ in docs]})
    log("  published users/<uid>/runs/%s/series/{%s}" % (rid, ",".join(d for d, _ in docs)))


def publish_refusal(db, rid, why):
    _run_ref(db, rid).collection("series").document("wf_status").set(
        {"state": "refused", "why": str(why)[:1500], "at": dt.datetime.now(dt.timezone.utc).isoformat(), "tool": TOOL})


def requested_runs(db):
    snap = db.collection("users").document(UID).collection("meta").document("run_series_req").get()
    d = snap.to_dict() if getattr(snap, "exists", False) else None
    out = []
    for x in ((d or {}).get("runs") or []):
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return sorted(set(out))


def clear_requests(db, settled):
    if not settled:
        return
    from google.cloud import firestore as gfs
    db.collection("users").document(UID).collection("meta").document("run_series_req").set(
        {"runs": gfs.ArrayRemove([int(r) for r in settled] + [str(r) for r in settled]),
         "served_at": dt.datetime.now(dt.timezone.utc).isoformat()}, merge=True)


# ── one run ──────────────────────────────────────────────────────────────────────────────────────────────
def pin_commit_for(doc, git_dir=SHARED):
    """The newest origin/main commit before the run STARTED (its timestamp minus elapsed_s, runner-local time):
    the code the runner had when it picked the job up. -> full sha or None."""
    import subprocess
    import pandas as pd
    ts = str(doc.get("timestamp") or "").strip()
    if not ts:
        return None
    try:
        t = pd.Timestamp(ts[:16] + ":00" + RUN_TZ) - pd.Timedelta(seconds=float(doc.get("elapsed_s") or 0.0))
    except Exception:
        return None
    r = subprocess.run(["git", "-C", git_dir, "log", "origin/main", "--before=" + t.isoformat(), "-1", "--format=%H"],
                       capture_output=True, text=True)
    sha = (r.stdout or "").strip()
    return sha or None


def ensure_pinned_root(sha, git_dir=SHARED, log=_say):
    """C:/EdgeLog/replay_wt/<sha8>, created as a DETACHED worktree when missing (read-only use; never committed to)."""
    import subprocess
    path = os.path.join(REPLAY_WT, sha[:8])
    if os.path.isdir(os.path.join(path, "augur_engine")):
        return path
    log("  creating pinned checkout %s at %s" % (path, sha[:8]))
    r = subprocess.run(["git", "-C", git_dir, "worktree", "add", "--detach", path, sha], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isdir(os.path.join(path, "augur_engine")):
        raise Refused("could not create the pinned checkout at %s: %s" % (sha[:8], (r.stderr or "").strip()[-300:]))
    return path


def build_one(db, rid, tapes=None, write=False, engine_root=None, log=_say, publish_refused=True):
    """-> ('built'|'refused'|'nodoc', payload-or-reason)."""
    snap = _run_ref(db, rid).get()
    if not getattr(snap, "exists", False):
        return "nodoc", "no run doc #%s" % rid
    doc = snap.to_dict() or {}
    doc.setdefault("id", rid)
    log("#%s %s %s %s %s (validated %s)" % (rid, doc.get("strategy"), doc.get("instrument"), doc.get("timeframe"),
                                            doc.get("data_source"), doc.get("timestamp")))
    t0 = time.time()
    try:
        wf = ((doc.get("validate") or {}).get("wf_oos") or {})
        from tools import backfill_wf_oos as B
        plan, reason = B.rebuild_plan(doc)
        if reason:
            raise Refused(reason)
        res = replay_run(dict(doc), tapes=tapes, log=log)
        plan = res["plan"]
        ok, info = verify_chain(res["matches"], res["mult"], wf.get("net"))
        if not ok:
            raise Refused(info["why"])
        tr = res["trades"]
        f0 = min(m["from"] for m in res["matches"] if m.get("from"))
        f1 = max(m["to"] for m in res["matches"] if m.get("to"))
        days = [t["d"] for t in tr]
        if days and (min(days) < f0 or max(days) > _next_bday(f1)):
            raise Refused("trade exit days %s..%s fall outside the fold span %s..%s" % (min(days), max(days), f0, f1))
        usd = [t["p"] * res["mult"] for t in tr]
        daily = daily_from_trades(days, usd, f0, f1)
        payload = series_payload(rid, plan, res["mult"], tr, daily, info,
                                 "replay", res.get("tape"), res["arm"], res["risk_src"], engine_root)
        if engine_root is None:
            add_sizing(payload)          # a pinned child leaves this to its parent (today's risk_sizing)
    except Refused as e:
        log("  REFUSED: %s" % e)
        if write and publish_refused and db is not None:
            publish_refusal(db, rid, e)
        return "refused", str(e)
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "%s_wf.json" % rid)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(p + ".tmp", p)
    docs = chunk_payload(payload)
    v = payload["verify"]
    log("  VERIFIED %d folds: replay $%.2f vs doc $%.2f (d $%.4f) | %d trades, %d days, risk on %d trades | %s"
        % (len(v["folds"]), v["replay_usd"], v["doc_usd"], v["d_usd"], payload["n_trades"], len(payload["daily"]["d"]),
           payload["risk_n"], res["arm"]))
    log("  local %s (%d bytes, %d Firestore doc(s)) in %.0f s" % (p, os.path.getsize(p), len(docs), time.time() - t0))
    if write:
        publish(db, rid, docs, log)
    return "built", payload


def _next_bday(d):
    import pandas as pd
    t = pd.Timestamp(d) + pd.Timedelta(days=1)
    while t.weekday() >= 5:
        t = t + pd.Timedelta(days=1)
    return t.strftime("%Y-%m-%d")


def _pinned_child(db, rid, a, why_today):
    import subprocess
    try:
        snap = _run_ref(db, rid).get()
        doc = snap.to_dict() or {}
        sha = pin_commit_for(doc)
        if not sha:
            raise Refused("no commit found before the run's start")
        root = ensure_pinned_root(sha)
    except Refused as e:
        why = "%s | pin: %s" % (why_today, e)
        if a.write:
            publish_refusal(db, rid, why)
        return "refused", why
    _say("  today's code refused; replaying #%s on the pinned checkout %s" % (rid, root))
    cmd = [sys.executable, "-u", os.path.abspath(__file__), str(rid), "--engine-root", root]
    cmd += sum((["--tape", t] for t in (a.tape or [])), [])
    r = subprocess.run(cmd)              # the child writes the local json only (no --write)
    if r.returncode == 0:
        p = os.path.join(OUT_DIR, "%s_wf.json" % rid)
        payload = json.load(open(p, encoding="utf-8"))
        try:
            fill_missing_stops(dict(doc, id=rid), payload)
        except Refused as e:
            why = "%s | pinned %s replayed, but %s" % (why_today, sha[:8], e)
            _say("  REFUSED: %s" % e)
            if a.write:
                publish_refusal(db, rid, why)
            return "refused", why
        payload = add_sizing(payload)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(p + ".tmp", p)
        if a.write:
            publish(db, rid, chunk_payload(payload))
        return "built", None
    return "refused", "%s | pinned %s also refused" % (why_today, sha[:8])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_trades_series.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=int)
    ap.add_argument("--write", action="store_true", help="publish to Firestore (default: local json only)")
    ap.add_argument("--requests", action="store_true", help="also build the runs the page asked for")
    ap.add_argument("--tape", action="append", help="replay on this tape csv only (repeatable)")
    ap.add_argument("--engine-root", help="a pinned checkout to import augur_engine / tools / strategies from")
    ap.add_argument("--skip-built", action="store_true", help="skip runs whose local json already exists")
    ap.add_argument("--local", action="store_true",
                    help="no replay: re-read the local <run>_wf.json, recompute the sizing block, (with --write) publish")
    ap.add_argument("--pin", action="store_true",
                    help="when today's code refuses a run, replay it again on a detached checkout of the commit the "
                         "run started on (C:/EdgeLog/replay_wt/<sha8>, created when missing) in a child process")
    a = ap.parse_args(argv)
    _setup_data_env()
    import augur_engine
    _say("engine from %s" % os.path.dirname(augur_engine.__file__))
    db = _db()
    runs = list(a.runs)
    req = []
    if a.requests:
        req = requested_runs(db)
        _say("page requests: %s" % (req or "none"))
        runs += [r for r in req if r not in runs]
    rc, settled = 0, []
    if a.local:
        for rid in runs:
            p = os.path.join(OUT_DIR, "%s_wf.json" % rid)
            if not os.path.exists(p):
                _say("#%s: no local series %s" % (rid, p))
                rc = 1
                continue
            payload = json.load(open(p, encoding="utf-8"))
            if payload.get("engine_root") and not all(v is not None for v in payload["trades"]["r"]):
                snap = _run_ref(db, rid).get()
                try:
                    fill_missing_stops(dict(snap.to_dict() or {}, id=rid), payload)
                except Refused as e:
                    _say("#%s: REFUSED %s" % (rid, e))
                    rc = 1
                    continue
            payload = add_sizing(payload)
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
            os.replace(p + ".tmp", p)
            _say("#%s: sizing recomputed from %s" % (rid, p))
            if a.write:
                publish(db, rid, chunk_payload(payload))
        return rc
    for rid in runs:
        if a.skip_built and os.path.exists(os.path.join(OUT_DIR, "%s_wf.json" % rid)):
            _say("#%s: local series exists, skipped" % rid)
            continue
        pin = a.pin and not a.engine_root
        try:
            st, why = build_one(db, rid, tapes=a.tape, write=a.write, engine_root=a.engine_root,
                                publish_refused=not pin)
        except Exception as e:
            _say("#%s: FAILED %s: %s" % (rid, type(e).__name__, e))
            st, why = "failed", str(e)
        if st == "refused" and pin:
            st, why = _pinned_child(db, rid, a, why)
        if st != "built":
            rc = 1
        if st in ("built", "refused", "nodoc"):
            settled.append(rid)
    if a.write and req:
        clear_requests(db, [r for r in settled if r in req])
    return rc


if __name__ == "__main__":
    sys.exit(main())
