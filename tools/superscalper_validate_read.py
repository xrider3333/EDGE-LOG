# -*- coding: utf-8 -*-
"""SUPERSCALPER Auto-Validate READER - prints the pre-registered reading of a finished 900-trial validate of
MISC_SUPERSCALPER_1_0.py from the SAVED run. READ-ONLY: Firestore document reads by id (plus one field-masked equality
query with limit 1 when only --run is given, to name the job); never a queue, never a write. Without --replay it runs no
backtest and re-states only what the validate stored; with --replay it re-runs the validate's OWN folds and lockbox stretch
(see the REPLAY note below) to get the daily series the run does not keep.

  python tools/superscalper_validate_read.py --run 495 [--json out.json]
  python tools/superscalper_validate_read.py --job <job id>
  python tools/superscalper_validate_read.py --run 495 --replay [--repo <checkout with the masters>] [--strategy-file <port .py>]
                                            [--port-sha <LF sha256>] [--session eth|rth]
  python tools/superscalper_validate_read.py --selftest        (synthetic run, no Firestore, no engine)

WHAT THE RUN STORES (augur_engine/validate.py run_validate -> api/runner.py _persist_run -> users/{uid}/runs/{run#}):
  top10_results   PRIMARY walk-forward scheme, one FULL row per fold: the fold champion's params, fold, train_bars, test_bars,
                  oos_from/oos_to, oos_trades, oos_pnl (points, net of cost), oos_pf, oos_wins, oos_win_rate (auto.py _wf_fold_row)
  wf_alt_folds    the OTHER scheme, COMPACT rows only: fold, total_pnl (train window), oos_pnl, oos_pf, train_bars, test_bars -
                  NO params, NO trades, NO dates (validate.py _alt_folds). Both schemes share the same test windows, so the
                  dates here come from the primary row of the same fold number (auto.py run_auto: te_s = init + f * tsize).
  validate.wf_oos stitched PRIMARY-scheme OOS block: net/trades/PF/win%/avg win/avg loss, per-trade max_drawdown, per-trade
                  Sharpe/Sortino, years, a <= 200-point per-TRADE equity curve (points), fold_idx, folds[{f, from, to, trades, net}]
  validate.lockbox  pnl, pf, trades, win_rate, sharpe, sortino, dd (per-trade, points), avg_win, avg_loss, from, to
  selection.candidates[crowned].lb_equity  <= 80 dated points of the crown's lockbox curve (cum, base, t)
  validate.pbo / dsr / checks / verdict / windows / champion; run doc: best_params, multiplier, cost_pts, date window, data_source.
WHAT IT DOES NOT STORE: any DAILY P&L series (WF or LB), per-fold params for the alt scheme, trades per alt fold. So ROC @ $30k
  is read at the best stored resolution and LABELLED: the validate's exact per-trade max DD (a daily DD can only be smaller, so
  that ROC is a FLOOR) next to the same ROC on the stored curve; DD5 / DD% from peak / the 1-EPISODE flag come from the stored
  curve; the daily Sortino x sqrt(252) needs a daily series and prints n/a. If a later validate saves
  wf_oos.daily / lockbox.daily as [[date, usd], ...] this reader uses it (exact house four()) and cuts the fold groups by day.

REPLAY (--replay, modelled on tools/noise_chain_read.py; run it from a box with the masters, ONE process, check
`python tools/queue_truth.py` first - a full-window trial of this port peaks ~4.4 GB, a fold slice far less): each primary
fold's champion params (top10_results) run through the engine's own slice evaluator on the validate's optimize-window arrays
(find_master by the run's data_source + session, window = validate.windows.optimize, bar count checked against the fold rows),
from the fold's WARM start (validate.windows.warm_days sessions before the test start; the validate does the same in
auto.make_slice_evaluator), keeping the trades that ENTER inside the fold's test slice [te_s, te_e). te_s = init + the earlier
folds' test bars (the same in both schemes; 'te_s = train_bars' is the ANCHORED case only). The crown re-runs over the whole
window and keeps the trades entering inside validate.windows.lockbox (the validate's own lockbox stretch). PARITY: every fold
and the lockbox must equal the stored oos_pnl / oos_trades (lockbox pnl / trades), the chain must equal validate.wf_oos
net / trades; a stretch that fails prints its mismatch and gets NO daily four numbers (exit code 4). Super Scalper holds across
midnight, so each trade's $ is booked on its EXIT bar's New York date; size is 1 contract at the run's cost_pts. Daily $ =
points x the run's multiplier over every NY date that has bars in the stretch (zeros included; Sunday-evening bars make a
date). The strategy file's LF sha256 and the run's stored strategy name are printed; --port-sha refuses a different file.
"""
import argparse
import bisect
import datetime
import gc
import hashlib
import importlib.util
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
SUPERSCALP_WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\superscalp"      # holds the port until it ships
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
DEV0, DEV1 = datetime.date(2023, 1, 1), datetime.date(2024, 12, 31)      # the two development years
ROC_BAR = 15.0
FOLD_PARAMS = ("session_filter", "sl_scale", "tp_scale", "max_hold_bars", "be_trigger", "sl_cap_atr", "vix_feed")
PICK_RULE = "picks change fold to fold = noise, not a session edge"


# ---------------------------------------------------------------- small helpers
def _d(x):
    try:
        return datetime.date.fromisoformat(str(x)[:10])
    except Exception:
        return None


def _f(x):
    try:
        y = float(x)
    except (TypeError, ValueError):
        return None
    return y if math.isfinite(y) else None


def money(x):
    return "-" if x is None else ("-$" if x < 0 else "$") + format(int(round(abs(x))), ",")


def num(x, nd=2):
    if x is None:
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return ("%." + str(nd) + "f") % x


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (datetime.date, datetime.datetime)):
        return str(o)
    return o


def _dd():
    """augur_engine/drawdowns.py (stdlib only) loaded by path: the house dd5 / dd_pct_peak without importing the engine."""
    for base in (ROOT, SHARED):
        p = os.path.join(base, "augur_engine", "drawdowns.py")
        if os.path.isfile(p):
            spec = importlib.util.spec_from_file_location("_edgelog_drawdowns", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise SystemExit("augur_engine/drawdowns.py not found")


# ---------------------------------------------------------------- the four numbers (house pattern: tools/orb_relay_r1.py four())
def four(v, yrs, dd_exact=None, net=None, daily=True):
    """ROC %/yr at a $30k worst DD, DD5 and DD% from peak at that sizing, daily Sortino, on v = $ per period in time order.
    daily=True: v is the DAILY P&L, zero days included (the house four()). daily=False: v is a coarser stored curve's
    increments; dd_exact (the validate's own worst DD in $) then drives the ROC and the sizing, net is the stored net."""
    if not v or not yrs or yrs <= 0:
        return None
    D = _dd()
    cum = peak = dd = 0.0
    for x in v:
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)                                   # peak from a flat account, as the house DD
    net = float(sum(v)) if net is None else float(net)
    dd_roc = float(dd_exact) if dd_exact else dd
    roc = 30.0 * (net / yrs) / dd_roc if dd_roc > 0 else float("inf")
    k = 30000.0 / dd_roc if dd_roc > 0 else 1.0
    d5 = D.dd5(v)
    so = None
    if daily:
        ds = math.sqrt(sum(min(x, 0.0) ** 2 for x in v) / len(v))
        so = (sum(v) / len(v)) / ds * math.sqrt(252) if ds > 0 else float("inf")
    return {"roc30": roc, "roc30_curve": (30.0 * (net / yrs) / dd if (not daily and dd > 0) else None),
            "dd5_at_30k": float(d5["dd5_usd"]) * k, "dd5_n": d5["n"], "one_episode": bool(d5["one_episode"]),
            "dd5_ratio": (d5["max_dd"] / d5["dd5_usd"]) if d5["dd5_usd"] > 0 else None,
            "dd_pct_peak_at_30k": D.dd_pct_peak([x * k for x in v], start=100000.0),
            "sortino": so, "net_usd": net, "years": yrs, "worst_dd_usd": dd_roc, "curve_dd_usd": dd}


def verdict(f):
    """PRE-REGISTERED: DEAD if WF ROC@30k < 15 or the WF figure is 1 EPISODE; otherwise read the LB."""
    if not f or f.get("roc30") is None:
        return "NO WF FIGURE - the rule cannot be applied"
    if f["roc30"] < ROC_BAR or f.get("one_episode"):
        return "DEAD"
    return "WF clears ROC 15 - read LB"


# ---------------------------------------------------------------- fold windows and the pre-registered groups
def fold_group(tf, tt, rf, rt):
    """'a' CLEAN: the test slice ends before 2023-01-01. 'b': the test slice overlaps 2023-01-01..2024-12-31 OR the train
    window (rf..rt) includes those years. 'other': after the development years with a train window that never touches
    them (counts in the chain without (b)). None: no dates stored. An unknown train window after 2024 is never called clean."""
    if tf is None or tt is None:
        return None
    if tt < DEV0:
        return "a"
    if tf <= DEV1 and tt >= DEV0:
        return "b"
    if rf is None or rt is None:
        return "b"
    return "b" if (rf <= DEV1 and rt >= DEV0) else "other"


def group_reason(r):
    g = r.get("group")
    if g == "a":
        return "test ends %s, before 2023" % r["test_to"]
    if g == "b" and r["test_from"] <= DEV1 and r["test_to"] >= DEV0:
        return "test %s..%s overlaps 2023-24" % (r["test_from"], r["test_to"])
    if g == "b":
        if r.get("train_from") and r.get("train_to"):
            return "train ~%s..%s includes 2023-24" % (r["train_from"], r["train_to"])
        return "train window unknown after 2024"
    if g == "other":
        return "after 2024, train never touches 2023-24"
    return "no test dates stored"


def infer_mode(raw):
    tb = [r.get("train_bars") for r in raw if isinstance(r, dict)]
    if len(tb) < 2 or any(t is None for t in tb):
        return None
    return "rolling" if len(set(tb)) == 1 else "anchored"


def fold_rows(raw, mult, dates_by_fold=None):
    """One normalized row per stored fold, in fold order (null PF = +inf, as the runner's json_safe saves it)."""
    out = []
    for r in sorted([x for x in (raw or []) if isinstance(x, dict) and x.get("fold") is not None], key=lambda x: int(x["fold"])):
        f = int(r["fold"])
        d0, d1 = _d(r.get("oos_from")), _d(r.get("oos_to"))
        if (d0 is None or d1 is None) and dates_by_fold and f in dates_by_fold:
            d0, d1 = dates_by_fold[f]
        net, pf, tr = _f(r.get("oos_pnl")), _f(r.get("oos_pf")), _f(r.get("oos_trades"))
        out.append({"fold": f, "test_from": d0, "test_to": d1, "trades": (int(tr) if tr is not None else None),
                    "net_pts": net, "net_usd": (net * mult if net is not None else None), "pf": pf,
                    "held": ((pf > 1) if pf is not None else bool(net is not None and net > 0)),
                    "train_bars": r.get("train_bars"), "test_bars": r.get("test_bars"),
                    "params": {k: r.get(k) for k in FOLD_PARAMS if k in r},
                    "keys": sorted(k for k in r if not str(k).startswith("_"))})
    return out


def fold_bounds(rows):
    """({fold: (te_s, te_e)}, init, n_total) from rows carrying fold / train_bars / test_bars; None unless the fold numbers are
    1..n and every bar count is there. te_s(f) = init + the test bars of the folds before f, init = fold 1's train_bars: the
    SAME formula in both schemes (tools/backfill_wf_oos.py fold_bounds_from_rows). 'te_s = train_bars' holds only for the
    ANCHORED scheme (train from bar 0); a rolling fold's train_bars is the constant init."""
    try:
        rs = sorted(rows, key=lambda r: int(r["fold"]))
        if not rs or [int(r["fold"]) for r in rs] != list(range(1, len(rs) + 1)):
            return None
        init, tb = int(rs[0]["train_bars"]), [int(r["test_bars"]) for r in rs]
    except (TypeError, ValueError, KeyError):
        return None
    if init <= 0 or any(t <= 0 for t in tb):
        return None
    out, acc = {}, init
    for r, t in zip(rs, tb):
        out[int(r["fold"])] = (acc, acc + t)
        acc += t
    return out, init, acc


def _date_at(bar, anchors):
    """Linear bar -> date through (bar, ordinal) anchors sorted by bar; clamps outside them."""
    if bar <= anchors[0][0]:
        return datetime.date.fromordinal(int(round(anchors[0][1])))
    for (b0, d0), (b1, d1) in zip(anchors, anchors[1:]):
        if bar <= b1:
            return datetime.date.fromordinal(int(round(d0 + (d1 - d0) * (bar - b0) / float(b1 - b0))))
    return datetime.date.fromordinal(int(round(anchors[-1][1])))


def set_train_windows(prim, alt, prim_mode, alt_mode, opt_from):
    """Estimate each fold's TRAIN window dates. Test windows are identical in both schemes: te_s(f) = init + the test bars of
    the folds before f (init = fold 1's train_bars); train ends at te_s; anchored trains from bar 0, rolling from te_s - init.
    Bar -> date is interpolated through the dated test starts (error: days to a few weeks, only the rolling start). Needs
    fold numbers 1..n; otherwise the windows stay None (and fold_group then refuses to call a post-2024 fold clean)."""
    for r in prim + alt:
        r["train_from"] = r["train_to"] = None
    fb = fold_bounds(prim)
    if fb is None:
        return
    bounds, init, n_total = fb
    te_s = {f: s for f, (s, _e) in bounds.items()}
    rs = sorted(prim, key=lambda r: r["fold"])
    pts = {}
    if opt_from:
        pts[0] = opt_from.toordinal()
    for r in rs:
        if r["test_from"]:
            pts[te_s[r["fold"]]] = r["test_from"].toordinal()
    if rs[-1]["test_to"]:
        pts[n_total - 1] = rs[-1]["test_to"].toordinal()
    anchors = sorted(pts.items())
    if len(anchors) < 2:
        return
    for rows, mode in ((prim, prim_mode), (alt, alt_mode)):
        for r in rows:
            f = r["fold"]
            if f not in te_s or not r["test_from"]:
                continue
            r["train_to"] = r["test_from"] - datetime.timedelta(days=1)
            if mode == "anchored":
                r["train_from"] = _date_at(0, anchors)
            elif mode == "rolling":
                r["train_from"] = _date_at(max(0, te_s[f] - init), anchors)


def split_groups(rows):
    return {"a": [r for r in rows if r["group"] == "a"], "b": [r for r in rows if r["group"] == "b"],
            "c": [r for r in rows if r["group"] in ("a", "other")], "none": [r for r in rows if r["group"] is None]}


def daily_of(block):
    """[(date, usd)] when a validate saved a daily series under block['daily'] (none does today), else None."""
    d = (block or {}).get("daily")
    try:
        out = sorted((_d(a), float(b)) for a, b in (d.items() if isinstance(d, dict) else d))
    except Exception:
        return None
    return out if out and all(x[0] for x in out) else None


def group_stat(rows, daily=None):
    g = {"folds": [r["fold"] for r in rows], "n": len(rows),
         "net_pts": sum(r["net_pts"] or 0.0 for r in rows), "net_usd": sum(r["net_usd"] or 0.0 for r in rows),
         "trades": (sum(r["trades"] for r in rows) if rows and all(r["trades"] is not None for r in rows) else None),
         "held": sum(1 for r in rows if r["held"]), "four": None}
    spans = [(r["test_from"], r["test_to"]) for r in rows if r["test_from"] and r["test_to"]]
    if daily and spans:
        days = [x for d, x in daily if any(a <= d <= b for a, b in spans)]
        g["four"] = four(days, sum((b - a).days + 1 for a, b in spans) / 365.25, daily=True)
    return g


# ---------------------------------------------------------------- the WF and LB stretches
def read_stretch(daily, curve, net_pts, dd_pts, yrs, mult, label=None):
    """(four dict, resolution text): the exact daily series when there is one, else the stored curve with the validate's DD."""
    if daily:
        v = [x for _d0, x in daily]
        r = four(v, max((daily[-1][0] - daily[0][0]).days, 1) / 365.25, daily=True)
        return r, label or "daily series stored: the exact house reading"
    if curve and len(curve) >= 2 and dd_pts and yrs and net_pts is not None:
        inc, prev = [], 0.0
        for c in curve:
            inc.append(c * mult - prev)
            prev = c * mult
        r = four(inc, yrs, dd_exact=dd_pts * mult, net=net_pts * mult, daily=False)
        return r, ("NOT DAILY: %d-point stored curve; ROC uses the validate's exact per-trade max DD (a FLOOR, a daily DD is "
                   "never larger), DD5 / DD%% / 1-EPISODE come from the curve" % len(curve))
    return None, "no curve / drawdown stored"


def _wl(win, loss, mult):
    return (win * mult if win is not None else None), (loss * mult if loss is not None else None)


def wf_stretch(N):
    v, mult = N["v"], N["mult"]
    wo = v.get("wf_oos") or {}
    if not wo:
        return None
    yrs = _f(wo.get("years"))
    if yrs is None and _d(wo.get("from")) and _d(wo.get("to")):
        yrs = max((_d(wo["to"]) - _d(wo["from"])).days, 1) / 365.25
    r, res = read_stretch(daily_of(wo), wo.get("equity"), _f(wo.get("net")), _f(wo.get("max_drawdown")), yrs, mult, N.get("daily_label"))
    aw, al = _wl(_f(wo.get("avg_win")), _f(wo.get("avg_loss")), mult)
    return {"mode": wo.get("mode"), "from": wo.get("from"), "to": wo.get("to"), "years": yrs, "n_folds": wo.get("n_folds"),
            "trades": wo.get("trades"), "net_usd": (_f(wo.get("net")) or 0.0) * mult, "pf": _f(wo.get("profit_factor")),
            "win_rate": _f(wo.get("win_rate")), "avg_win_usd": aw, "avg_loss_usd": al,
            "sortino_trade": _f(wo.get("sortino")), "sharpe_trade": _f(wo.get("sharpe")),
            "dd_exact_usd": (_f(wo.get("max_drawdown")) or 0.0) * mult, "four": r, "resolution": res,
            "curve_points": len(wo.get("equity") or []), "equity_n": wo.get("equity_n")}


def lb_curve(N):
    """(cumulative points from a flat start, source) for the lockbox: the crown's dated lb_equity, else the whole-run tail."""
    sel = N.get("selection") or {}
    cands = (sel.get("candidates") or []) + (sel.get("robust") or [])
    c = next((x for x in cands if x.get("crowned")), None) or next(
        (x for x in cands if x.get("params") == N.get("best_params")), None)
    le = (c or {}).get("lb_equity") or {}
    if le.get("cum") and _f(le.get("base")) is not None:
        base = float(le["base"])
        cur = [float(x) - base for x in le["cum"]]
        if _f(le.get("final")) is not None and abs(float(le["final"]) - base - cur[-1]) > 1e-6:
            cur.append(float(le["final"]) - base)                          # the stride sample leaves the last trades out
        return cur, "selection crowned lb_equity (%d dated points)" % len(cur)
    eq, i = N["v"].get("equity"), N["v"].get("lb_idx")
    if isinstance(eq, list) and isinstance(i, int) and 0 < i < len(eq) - 1:
        return [float(x) - float(eq[i - 1]) for x in eq[i:]], "whole-run curve tail (%d points)" % (len(eq) - i)
    return None, "none"


def lb_stretch(N):
    v, mult = N["v"], N["mult"]
    lb = v.get("lockbox") or {}
    if not lb or not lb.get("trades"):
        return None
    d0, d1 = _d(lb.get("from")), _d(lb.get("to"))
    yrs = max((d1 - d0).days, 1) / 365.25 if (d0 and d1) else None
    cur, src = lb_curve(N)
    r, res = read_stretch(daily_of(lb), cur, _f(lb.get("pnl")), _f(lb.get("dd")), yrs, mult, N.get("daily_label"))
    aw, al = _wl(_f(lb.get("avg_win")), _f(lb.get("avg_loss")), mult)
    return {"from": lb.get("from"), "to": lb.get("to"), "years": yrs, "trades": lb.get("trades"),
            "net_usd": (_f(lb.get("pnl")) or 0.0) * mult, "pf": _f(lb.get("pf")), "win_rate": _f(lb.get("win_rate")),
            "avg_win_usd": aw, "avg_loss_usd": al, "sortino_trade": _f(lb.get("sortino")), "sharpe_trade": _f(lb.get("sharpe")),
            "dd_exact_usd": (_f(lb.get("dd")) or 0.0) * mult, "four": r, "resolution": res + "; curve: " + src}


# ---------------------------------------------------------------- session rule, run header
def session_lines(crown, picks):
    """picks = [(fold, session_filter or None)] of the primary scheme. The pre-registered session reading rule."""
    if crown is None:
        return ["crown session_filter not stored - session rule cannot be read"]
    if crown == "all":
        return ["crown session_filter = all - the session rule is not triggered"]
    known = [(f, s) for f, s in picks if s is not None]
    out = ["crown session_filter = %s" % crown]
    if not known:
        return out + ["per-fold session picks NOT STORED on the fold rows"]
    out.append("per-fold picks: " + ", ".join("f%d %s" % (f, s) for f, s in known))
    if len(set(s for _f0, s in known)) > 1:
        out.append(PICK_RULE)
    else:
        out.append("picks are the same in every fold (%s)" % known[0][1])
    return out


def normalize(run, job=None, job_id=None):
    """One flat view over a runs/{run#} doc (top10_results) or, when it is missing, a job doc's result (top)."""
    job = job or {}
    src = run if run else (job.get("result") or {})
    v = src.get("validate") if isinstance(src.get("validate"), dict) else {}
    mult = _f(src.get("multiplier")) or _f(job.get("mult"))
    nco = _f(src.get("n_combos"))
    return {"run_no": (run or {}).get("id") if run else job.get("run_id"), "job_id": job_id, "src": src, "v": v,
            "scope": src.get("scope"), "saved": src.get("timestamp"), "elapsed_s": _f(src.get("elapsed_s") or job.get("elapsed_s")),
            "strategy": src.get("strategy") or job.get("strategy"), "instrument": src.get("instrument") or job.get("instrument"),
            "timeframe": src.get("timeframe") or job.get("timeframe"), "session": job.get("session"),
            "data_source": src.get("data_source") or job.get("source"), "source_name": src.get("source_name"),
            "date_from": src.get("date_from") or job.get("date_from"), "date_to": src.get("date_to") or job.get("date_to"),
            "cost_pts": (src.get("cost_pts") if src.get("cost_pts") is not None else job.get("cost_pts")),
            "commission_usd": src.get("commission_usd"), "slippage_pts": src.get("slippage_pts"),
            "mult": mult or 20.0, "mult_assumed": not mult,
            "trials": job.get("n_trials") or (int(nco // 2) if nco else None), "trials_derived": not job.get("n_trials"),
            "top": src.get("top10_results") or src.get("top") or [], "alt": src.get("wf_alt_folds") or [],
            "alt_mode": src.get("wf_alt_mode"), "best_params": src.get("best_params") or v.get("champion") or {},
            "selection": src.get("selection"), "dsr": src.get("dsr"), "dropped": src.get("fields_dropped"),
            "daily_label": None}


def build_reading(N):
    v, mult = N["v"], N["mult"]
    wo = v.get("wf_oos") or {}
    prim_mode = v.get("wf_best_mode") or infer_mode(N["top"])
    alt_mode = N.get("alt_mode") or {"rolling": "anchored", "anchored": "rolling"}.get(prim_mode)
    wf_dates = {int(x["f"]): (_d(x.get("from")), _d(x.get("to"))) for x in (wo.get("folds") or []) if x.get("f") is not None}
    prim = fold_rows(N["top"], mult, wf_dates)
    alt = fold_rows(N["alt"], mult, {r["fold"]: (r["test_from"], r["test_to"]) for r in prim})
    opt = (v.get("windows") or {}).get("optimize") or [None, None]
    set_train_windows(prim, alt, prim_mode, alt_mode, _d(opt[0]) or _d(N.get("date_from")))
    for r in prim + alt:
        r["group"] = fold_group(r["test_from"], r["test_to"], r.get("train_from"), r.get("train_to"))
    daily = daily_of(wo)
    groups = {}
    for name, rows, dly in (("primary", prim, daily), ("alt", alt, None)):
        sp = split_groups(rows)
        groups[name] = {k: group_stat(sp[k], dly) for k in ("a", "b", "c", "none")}
        groups[name]["all"] = group_stat(rows, dly)
    wf, lb = wf_stretch(N), lb_stretch(N)
    wf4 = (wf or {}).get("four")
    cav = None
    if wf4 and wf4.get("roc30_curve") is not None:
        lo, hi = wf4["roc30"], wf4["roc30_curve"]
        cav = ("the pre-registered DAILY ROC is not stored. ROC floor %s (exact per-trade DD) .. %s (stored curve DD); "
               "the verdict above uses the floor." % (num(lo, 1), num(hi, 1)))
        if min(lo, hi) < ROC_BAR <= max(lo, hi):
            cav += " The bracket STRADDLES 15 - treat the verdict as NOT FINAL until a daily replay."
    # the stored stitched block must agree with the stored fold rows (analytics.wf_oos_block's own guard): say so either way
    recon = None
    if wo and _f(wo.get("net")) is not None and prim:
        s = sum(r["net_pts"] or 0.0 for r in prim)
        recon = {"fold_sum_pts": s, "wf_oos_net_pts": float(wo["net"]), "ok": abs(s - float(wo["net"])) <= 0.2 + 1e-4 * abs(s)}
    eng = {"verdict": v.get("verdict"), "n_pass": v.get("n_pass"), "n_gates": v.get("n_gates"),
           "failed": sorted(k for k, ok in (v.get("checks") or {}).items() if not ok),
           "pbo": (v.get("pbo") or {}).get("pbo"), "pbo_configs": (v.get("pbo") or {}).get("n_configs"),
           "dsr": (N["dsr"] or {}).get("dsr") if isinstance(N["dsr"], dict) else v.get("dsr"),
           "luck_bar": (N["dsr"] or {}).get("luck_bar") if isinstance(N["dsr"], dict) else None,
           "wfe": v.get("wfe"), "folds_held": v.get("folds_held"), "n_folds": v.get("n_folds"),
           "total_trades": v.get("total_trades"), "total_win_rate": v.get("total_win_rate"),
           "total_avg_win_usd": _wl(_f(v.get("total_avg_win")), _f(v.get("total_avg_loss")), mult)[0],
           "total_avg_loss_usd": _wl(_f(v.get("total_avg_win")), _f(v.get("total_avg_loss")), mult)[1]}
    return {"header": {k: N[k] for k in ("run_no", "job_id", "scope", "saved", "elapsed_s", "strategy", "instrument", "timeframe",
                                          "session", "data_source", "source_name", "date_from", "date_to", "cost_pts",
                                          "commission_usd", "slippage_pts", "mult", "mult_assumed", "trials", "trials_derived")},
            "windows": v.get("windows"), "engine": eng, "wf": wf, "lb": lb, "recon": recon,
            "modes": {"primary": prim_mode, "alt": alt_mode}, "folds": {"primary": prim, "alt": alt},
            "groups": groups, "session": session_lines(N["best_params"].get("session_filter") if N["best_params"] else None,
                                                       [(r["fold"], r["params"].get("session_filter")) for r in prim]),
            "crown": N["best_params"], "verdict": verdict(wf4), "caveat": cav, "dropped": N["dropped"]}


# ---------------------------------------------------------------- printing
def _table(head, rows):
    w = [max(len(str(x)) for x in col) for col in zip(head, *rows)] if rows else [len(h) for h in head]
    fmt = lambda r: "  ".join(str(x).ljust(w[i]) for i, x in enumerate(r)).rstrip()
    return [fmt(head)] + [fmt(r) for r in rows]


def _four_lines(name, s):
    if not s:
        return ["%s: nothing stored (no walk-forward block / no lockbox trades)" % name]
    f = s["four"]
    out = ["%s  %s..%s  %s yr  trades %s  net %s  PF %s  win %s%%  avg win %s / avg loss %s" % (
        name, s.get("from"), s.get("to"), num(s.get("years"), 2), s.get("trades"), money(s.get("net_usd")), num(s.get("pf"), 2),
        num(s.get("win_rate"), 1), money(s.get("avg_win_usd")), money(s.get("avg_loss_usd")))]
    if not f:
        return out + ["   four numbers: n/a (%s)" % s.get("resolution")]
    n5 = "" if f["dd5_n"] >= 5 else " (n=%d)" % f["dd5_n"]
    out.append("   ROC@30k %s %%/yr%s   DD5@30k %s%s   DD%% from peak @30k %s%%   Sortino x sqrt(252): %s%s" % (
        num(f["roc30"], 1), (" (floor; on the curve %s)" % num(f["roc30_curve"], 1)) if f["roc30_curve"] is not None else "",
        money(f["dd5_at_30k"]), n5, num(f["dd_pct_peak_at_30k"], 1),
        num(f["sortino"], 2) if f["sortino"] is not None else "n/a (no daily series)",
        (" | per-trade Sortino stored %s" % num(s.get("sortino_trade"), 2)) if f["sortino"] is None else ""))
    out.append("   worst DD %s%s   worst/DD5 %s  %s" % (
        money(s.get("dd_exact_usd") if f["roc30_curve"] is not None else f["worst_dd_usd"]),
        (" (curve %s)" % money(f["curve_dd_usd"])) if f["roc30_curve"] is not None else "", num(f["dd5_ratio"], 2),
        "1 EPISODE" if f["one_episode"] else ("(n=1: the flag cannot fire)" if f["dd5_n"] == 1 else "spread over episodes")))
    out.append("   resolution: " + s["resolution"])
    return out


def _fold_table(rows, show_params):
    head = ["fold", "test from", "test to", "trades", "OOS net", "PF", "grp"] + (list(FOLD_PARAMS) if show_params else [])
    body = []
    for r in rows:
        line = [r["fold"], r["test_from"] or "-", r["test_to"] or "-", "-" if r["trades"] is None else r["trades"],
                money(r["net_usd"]), "inf" if (r["pf"] is None and r["held"]) else num(r["pf"], 2), r["group"] or "-"]
        if show_params:
            line += [r["params"].get(k, "-") if r["params"].get(k) is not None else "-" for k in FOLD_PARAMS]
        body.append(line)
    return _table(head, body)


def _group_lines(title, g):
    out = ["%s: %d fold(s) %s | OOS net %s | trades %s | folds with PF > 1: %d of %d" % (
        title, g["n"], g["folds"], money(g["net_usd"]), "-" if g["trades"] is None else g["trades"], g["held"], g["n"])]
    f = g["four"]
    if f:
        out.append("     four numbers (daily OOS days of these folds): ROC@30k %s  DD5@30k %s  DD%% from peak %s%%  Sortino %s  %s" % (
            num(f["roc30"], 1), money(f["dd5_at_30k"]), num(f["dd_pct_peak_at_30k"], 1), num(f["sortino"], 2),
            "1 EPISODE" if f["one_episode"] else ""))
    elif g["n"]:
        out.append("     four numbers: n/a - no daily OOS series stored (the 200-point curve cannot be cut at fold edges)")
    return out


def render(R):
    h, e, L = R["header"], R["engine"], []
    L.append("SUPERSCALPER Auto-Validate - pre-registered reading (read-only, from the saved run)")
    L.append("")
    L.append("1. RUN")
    L.append("run #%s   job %s   %s   saved %s   elapsed %s" % (
        h["run_no"], h["job_id"] or "(not looked up)", h["scope"] or "-", h["saved"] or "-",
        ("%.0f min" % (h["elapsed_s"] / 60.0)) if h["elapsed_s"] else "-"))
    L.append("strategy %s   %s %s   session %s   trials %s%s" % (
        h["strategy"], h["instrument"], h["timeframe"], h["session"] or "(job doc only)", h["trials"] or "-",
        " (from n_combos / 2)" if h["trials_derived"] and h["trials"] else ""))
    L.append("window %s .. %s   master/source %s%s   cost %s pts%s   $ per point %s%s" % (
        h["date_from"], h["date_to"], h["data_source"], (' ("%s")' % h["source_name"]) if h["source_name"] else "",
        h["cost_pts"], (" + commission %s, slippage %s pts" % (h["commission_usd"], h["slippage_pts"]))
        if (h["commission_usd"] or h["slippage_pts"]) else "", h["mult"], " (ASSUMED - not stored)" if h["mult_assumed"] else ""))
    w = R.get("windows") or {}
    span = lambda x: "%s..%s" % tuple(x) if isinstance(x, (list, tuple)) and len(x) == 2 else str(x)
    if w:
        L.append("validate windows: optimize %s, lockbox %s (%s mo), warm_days %s, WF starts %s" % (
            span(w.get("optimize")), span(w.get("lockbox")), w.get("lockbox_months"), w.get("warm_days"), w.get("wf_split")))
    L.append("engine verdict %s (%s of %s gates%s)   PBO %s (%s configs)   DSR %s (luck bar %s)   WFE %s   folds held %s of %s" % (
        e["verdict"], e["n_pass"], e["n_gates"], (", failed: " + ", ".join(e["failed"])) if e["failed"] else "", num(e["pbo"], 3),
        e["pbo_configs"], num(e["dsr"], 3), num(e["luck_bar"], 2), num(e["wfe"], 3), e["folds_held"], e["n_folds"]))
    L.append("whole run: trades %s  win %s%%  avg win %s / avg loss %s" % (
        e["total_trades"], num(e["total_win_rate"], 1), money(e["total_avg_win_usd"]), money(e["total_avg_loss_usd"])))
    L.append("crown: " + json.dumps(R["crown"], sort_keys=True))
    if R.get("dropped"):
        L.append("WARNING: the runner dropped fields to fit the doc: %s" % R["dropped"])
    L += ["", "2. THE FOUR NUMBERS - WF and LB apart (WF = the primary scheme, %s)" % R["modes"]["primary"]]
    L += _four_lines("WF", R["wf"])
    if R.get("recon"):
        rc = R["recon"]
        L.append("   check: the fold rows' OOS nets sum to %s pts, wf_oos.net is %s pts - %s" % (
            num(rc["fold_sum_pts"], 1), num(rc["wf_oos_net_pts"], 1), "agree" if rc["ok"] else "WARNING: THEY DISAGREE"))
    L += _four_lines("LB", R["lb"])
    L += ["", "3. PER-FOLD (test windows identical in both schemes)"]
    pst = any(r["params"] for r in R["folds"]["primary"])
    L.append("PRIMARY scheme = %s (full rows)%s" % (R["modes"]["primary"], "" if pst else " - per-fold params NOT STORED"))
    L += _fold_table(R["folds"]["primary"], pst)
    if not pst and R["folds"]["primary"]:
        L.append("stored on these rows instead: " + ", ".join(R["folds"]["primary"][0]["keys"]))
    alt = R["folds"]["alt"]
    ast = any(r["params"] for r in alt)
    L.append("OTHER scheme = %s (compact rows; trades and params %s; test dates taken from the primary row of the same fold)" % (
        R["modes"]["alt"], "stored" if ast else "NOT STORED"))
    L += _fold_table(alt, ast) if alt else ["(no alt-scheme rows stored)"]
    if alt:
        L.append("stored on the alt rows: " + ", ".join(alt[0]["keys"]))
    L += ["", "4. SESSION READING RULE"] + R["session"]
    L += ["", "5. FOLD GROUPS (a) CLEAN = test ends before 2023-01-01; (b) test overlaps 2023-01-01..2024-12-31 or the train "
          "window includes them; (c) the chain without (b)"]
    for name in ("primary", "alt"):
        rows = R["folds"][name]
        if not rows:
            continue
        G = R["groups"][name]
        L.append("-- %s scheme (%s); train windows estimated by bar interpolation" % (name, R["modes"][name]))
        L += _group_lines("(a) CLEAN", G["a"]) + _group_lines("(b) DEV-YEAR", G["b"])
        L += _group_lines("(c) CHAIN without (b)", G["c"]) + _group_lines("whole chain", G["all"])
        if G["none"]["n"]:
            L.append("   folds with no dates stored (in no group): %s" % G["none"]["folds"])
        for r in rows:
            L.append("   f%d -> %s  (%s)" % (r["fold"], r["group"] or "-", group_reason(r)))
    L += ["", "6. PRE-SET VERDICT", R["verdict"]]
    if R.get("replay") and not R["replay"]["ok"]:
        L.append("REPLAY PARITY FAILED - the stretch(es) that failed carry the stored-curve (NOT daily) reading above; see the "
                 "MISMATCH lines")
    if R["caveat"]:
        L.append("RESOLUTION CAVEAT: " + R["caveat"])
    return L


# ---------------------------------------------------------------- Firestore (read only)
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


def fetch(run=None, job=None):
    """-> (run doc or None, job doc or None, job id). Reads by id; one field-masked equality query (limit 1) for --run."""
    u = _db().collection("users").document(UID)
    light = ["status", "progress", "run_id", "strategy", "type", "instrument", "timeframe", "session", "source", "date_from",
             "date_to", "cost_pts", "n_trials", "mult", "elapsed_s", "error"]
    jdoc, jid, rdoc = None, job, None
    if job:
        s = u.collection("backtests").document(job).get(field_paths=light)
        jdoc = (s.to_dict() or None) if s.exists else None
        if jdoc is None:
            raise SystemExit("no job doc %s" % job)
        if jdoc.get("status") != "done":
            raise SystemExit("job %s is %s (progress %s) %s" % (job, jdoc.get("status"), jdoc.get("progress"),
                                                                str(jdoc.get("error") or "")[:300]))
        run = jdoc.get("run_id")
    if run:
        s = u.collection("runs").document(str(run)).get()
        rdoc = (s.to_dict() or None) if s.exists else None
        if rdoc is None and not job:
            raise SystemExit("no run doc %s" % run)
    if job and rdoc is None:                       # persist failed: the job doc's own result carries the same validate
        s = u.collection("backtests").document(job).get(field_paths=["result"] + light)
        jdoc = s.to_dict() or jdoc
    if run and not job:
        from google.cloud.firestore_v1.base_query import FieldFilter
        for s in (u.collection("backtests").where(filter=FieldFilter("run_id", "==", int(run))).select(light).limit(1).stream()):
            jid, jdoc = s.id, (s.to_dict() or None)
    return rdoc, jdoc, jid


# ---------------------------------------------------------------- --replay: the daily series, rebuilt and parity-checked
# The validate saves no daily P&L, so the house answer (tools/noise_chain_read.py) is to re-run what it ran: each primary fold's
# champion on the validate's own optimize-window arrays, from the fold's WARM start, keeping the trades that ENTER inside the
# fold's test slice; every fold and the lockbox must reproduce the stored net points and trade count before anything is printed.
# Super Scalper differences: it holds across midnight, so a trade's $ is booked on its EXIT bar's New York date (NOISE books
# the entry date); size is 1 contract at the run's cost_pts, so there is no tilt / re-costing.
class BarDates(object):
    """NY calendar date of every bar without a Python object per bar: codes into the sorted unique dates (`uniq`)."""

    def __init__(self, codes, uniq):
        self.codes, self.uniq = codes, uniq

    def __len__(self):
        return len(self.codes)

    def __getitem__(self, i):
        return self.uniq[int(self.codes[i])]


def bar_dates(index):
    import pandas as pd
    ix = pd.DatetimeIndex(index)
    if ix.tz is not None:
        ix = ix.tz_convert("America/New_York").tz_localize(None)
    codes, uniq = pd.factorize(ix.normalize(), sort=True)
    return BarDates(codes.astype("int32"), [u.date() for u in uniq])


def lf_sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()


def rss_mb():
    """(current, peak) resident MB when psutil is available, else None."""
    try:
        import psutil
        mi = psutil.Process().memory_info()
        return mi.rss / 2.0 ** 20, getattr(mi, "peak_wset", mi.rss) / 2.0 ** 20
    except Exception:
        return None


def warm_start_bar(did, a0, warm):
    """auto.make_slice_evaluator's warm_start_bar: the first bar of the session `warm` sessions before bar a0 (day ids)."""
    if warm <= 0 or a0 <= 0 or len(did) == 0:
        return a0
    target = int(did[a0]) - warm
    return 0 if target <= int(did[0]) else bisect.bisect_left(did, target)


def fold_trades(trades, w, s0, s1):
    """Trades of a run over the slice that STARTS at bar w (their bar indices are relative to w), kept only if they ENTER inside
    [s0, s1); returned with ABSOLUTE entry / exit bars, entry order."""
    out = []
    for t in trades:
        e, x = int(t[0]) + w, int(t[1]) + w
        if s0 <= e < s1:
            out.append((e, x) + tuple(t[2:]))
    return sorted(out, key=lambda t: t[0])


def book_by_exit(trades, dates, mult):
    """[(NY date of the EXIT bar, $)] for absolute-index trades (exit clamped to the last bar)."""
    last = len(dates) - 1
    return [(dates[min(int(t[1]), last)], float(t[2]) * mult) for t in trades]


def daily_series(booked, calendar):
    """([(date, $)] over EVERY date of `calendar` (sorted), zeros included; the $ booked on a date outside it)."""
    acc, outside = {d: 0.0 for d in calendar}, 0.0
    for d, x in booked:
        if d in acc:
            acc[d] += x
        else:
            outside += x
    return [(d, acc[d]) for d in calendar], outside


def parity(net, n, saved_net, saved_n, tol=None):
    """(ok, text): replayed net points / trade count against the stored ones. Default tolerance = noise_chain_read's fold one."""
    saved_net, saved_n = float(saved_net or 0.0), int(saved_n or 0)
    tol = (1e-6 * max(1.0, abs(net)) + 1e-6) if tol is None else tol
    return (abs(net - saved_net) < tol and int(n) == saved_n,
            "%d trades / %.4f pts (stored %d / %.4f)" % (n, net, saved_n, saved_net))


def replay_chain(ev, dates, did, rows, pkeys, warm, mult, log=print):
    """Re-run every PRIMARY fold, one after the other: the fold champion's params on the slice [w, te_e) (w = the warm start of
    te_s) with the engine's own slice evaluator `ev(a, b, params, keep_trades=True)`, keeping the trades that ENTER inside
    [te_s, te_e). Frees the fold's trades between folds. -> {ok, folds, booked, net_pts, trades}"""
    bounds = fold_bounds(rows)[0]
    folds, booked, net_all, n_all, ok = [], [], 0.0, 0, True
    for r in sorted(rows, key=lambda r: int(r["fold"])):
        f = int(r["fold"])
        s0, s1 = bounds[f]
        w = warm_start_bar(did, s0, warm)
        m = ev(w, s1, {k: r[k] for k in pkeys}, keep_trades=True)
        tr = fold_trades((m or {}).get("trades") or [], w, s0, s1)
        net = sum(float(t[2]) for t in tr)
        good, txt = parity(net, len(tr), r.get("oos_pnl"), r.get("oos_trades"))
        ok = ok and good
        rss = rss_mb()
        log("  fold %d  bars %d..%d (warm start %d)  %s  %s%s" % (f, s0, s1, w, txt, "OK" if good else "MISMATCH",
                                                                  ("  rss %.0f MB (peak %.0f)" % rss) if rss else ""))
        if m is None:
            log("    the evaluator returned nothing for this slice (a swallowed backtest error)")
        booked += book_by_exit(tr, dates, mult)
        net_all += net
        n_all += len(tr)
        folds.append({"fold": f, "te_s": s0, "te_e": s1, "warm_start": w, "trades": len(tr), "net_pts": net, "ok": good,
                      "text": txt})
        del m, tr
        gc.collect()
    return {"ok": ok, "folds": folds, "booked": booked, "net_pts": net_all, "trades": n_all}


def chain_parity(rep, wo):
    """The chain's total against validate.wf_oos (net within 0.1 pts, as noise_chain_read; trade count equal)."""
    ok, txt = parity(rep["net_pts"], rep["trades"], wo.get("net"), wo.get("trades"), tol=0.1)
    return ok, "chain " + txt


def replay_lockbox(ev, dates, did, n, lb_i, crown, warm, mult, saved):
    """The crown over the whole window, keeping trades that ENTER inside the lockbox [lb_i, n) - the validate's own lockbox
    stretch (_make_lockbox_runner: warm only when 0 < lb_i < n). Parity against validate.lockbox pnl / trades."""
    w = warm_start_bar(did, lb_i, warm) if 0 < lb_i < n else lb_i
    m = ev(w, n, crown, keep_trades=True)
    tr = fold_trades((m or {}).get("trades") or [], w, lb_i, n)
    net = sum(float(t[2]) for t in tr)
    ok, txt = parity(net, len(tr), saved.get("pnl"), saved.get("trades"))
    return {"ok": ok, "text": "lockbox " + txt, "booked": book_by_exit(tr, dates, mult), "net_pts": net, "trades": len(tr),
            "lb_i": lb_i, "warm_start": w}


def replay(N, repo, strategy_file=None, port_sha=None, log=print):
    """Rebuild the WF chain and the lockbox as daily $ and check parity. Engine and masters come from `repo` (the shared
    checkout: the master registry lives there). A refusal here raises SystemExit; a parity failure is returned, not hidden."""
    v = N["v"]
    wo, win = v.get("wf_oos") or {}, v.get("windows") or {}
    rows = sorted([r for r in N["top"] if isinstance(r, dict) and r.get("fold") is not None], key=lambda r: int(r["fold"]))
    opt, lbw = win.get("optimize") or [], win.get("lockbox") or []
    if not wo or not rows or len(opt) < 2 or len(lbw) < 2 or not (opt[0] and opt[1] and lbw[0] and lbw[1]):
        raise SystemExit("replay needs validate.wf_oos, the fold rows and validate.windows.optimize / lockbox on the run")
    if v.get("evolved_file") or N["src"].get("evolved_file"):
        raise SystemExit("this run validated an AI-evolved copy of the strategy - the saved file is not the code that ran")
    fb = fold_bounds(rows)
    if fb is None:
        raise SystemExit("the fold rows are not 1..n with train_bars / test_bars (a fold with no trained trial is dropped, not "
                         "saved) - the bar bounds cannot be rebuilt")
    bounds, init, n_total = fb
    d0, d1 = _d(wo.get("from")), _d(wo.get("to"))
    ld0, ld1 = _d(lbw[0]), _d(lbw[1])
    if not (d0 and d1 and ld0 and ld1):
        raise SystemExit("no WF / lockbox calendar dates on the run")
    ds = str(N["data_source"] or "").lower()
    session = N.get("session") or (ds[-3:] if ds.endswith(("_eth", "_rth")) else None)
    if not session:
        raise SystemExit("cannot tell the session (rth / eth) from data_source %r - pass --session" % N["data_source"])
    warm, cost, mult = int(win.get("warm_days") or 0), float(N["cost_pts"] or 0.0), N["mult"]
    sys.path.insert(0, repo)
    os.environ.pop("AUGUR_TRIAL_CACHE", None)
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.auto import make_slice_evaluator, _auto_space_from_params
    from augur_engine.strategies import load_strategy
    cands = [strategy_file] if strategy_file else [os.path.join(repo, "augur_strategies", str(N["strategy"])),
                                                   os.path.join(SUPERSCALP_WT, "augur_strategies", str(N["strategy"]))]
    path = next((p for p in cands if p and os.path.isfile(p)), None)
    if not path:
        raise SystemExit("strategy file %s not found (looked in %s) - pass --strategy-file" % (N["strategy"], cands))
    sha = lf_sha(path)
    log("REPLAY  strategy file %s" % path)
    log("        LF sha256 %s   run stored strategy name: %s%s" % (sha, N["strategy"],
                                                                  "  (not in --repo: a worktree copy)" if not strategy_file and not path.startswith(repo) else ""))
    if port_sha and sha != port_sha.lower():
        raise SystemExit("the strategy file's LF sha256 is not the pinned --port-sha %s" % port_sha)
    mod = load_strategy(path)
    pkeys = list(_auto_space_from_params(getattr(mod, "DEFAULT_PARAMS", {}) or {}).keys())
    champ = dict(v.get("champion") or N["best_params"] or {})
    bad = sorted(set(champ) ^ set(pkeys))
    gaps = [(int(r["fold"]), sorted(set(pkeys) - set(r))) for r in rows if set(pkeys) - set(r)]
    if bad or gaps:
        raise SystemExit("the file's searched knobs differ from the run's (champion vs file: %s; fold rows missing: %s) - not the "
                         "port that ran, nothing replayed" % (bad, gaps))
    m = find_master(N["instrument"], N["timeframe"], session, N["data_source"])
    if m is None:
        raise SystemExit("no master for %s %s %s %s in %s" % (N["instrument"], N["timeframe"], session, N["data_source"], repo))
    log("        master %s (id %s, %s, %s)  window %s..%s  warm_days %d  cost %s pts  x%s $/pt" % (
        m.get("filename"), m.get("id"), m.get("name"), m.get("source"), opt[0], opt[1], warm, cost, mult))
    if N.get("source_name") and m.get("name") and N["source_name"] != m.get("name"):
        log("        NOTE: the run saved master name %r, the registry now says %r" % (N["source_name"], m.get("name")))
    A = load_master_arrays(m, date_from=opt[0], date_to=opt[1])
    n = len(A["close"])
    if n != n_total:
        raise SystemExit("bars_mismatch: the window has %d bars, the fold rows expect %d - the data changed since the run "
                         "validated (or trailing folds were dropped); nothing replayed" % (n, n_total))
    dates, did = bar_dates(A["index"]), A["day_id"]
    log("        %d bars loaded; WF chain, folds one at a time, rolling-safe bounds te_s = init %d + earlier test bars" % (n, init))
    wf = replay_chain(make_slice_evaluator(mod, A, cost, warm_days=0), dates, did, rows, pkeys, warm, mult, log)
    ok_c, txt_c = chain_parity(wf, wo)
    wf_cal = [d for d in dates.uniq if d0 <= d <= d1]
    wf_daily, wf_out = daily_series(wf["booked"], wf_cal)
    wf_ok = wf["ok"] and ok_c and abs(wf_out) < 1e-9
    log("  PARITY %s: %s vs stored wf_oos %d trades / %.1f pts%s" % (
        "PASS" if wf_ok else "FAIL", txt_c, wo.get("trades") or 0, wo.get("net") or 0.0,
        ("" if abs(wf_out) < 1e-9 else "  (%.2f $ booked outside the WF calendar)" % wf_out)))
    del A, dates, did, wf["booked"]
    gc.collect()
    import pandas as pd
    B = load_master_arrays(m, date_from=opt[0], date_to=lbw[1])
    nb, ix = len(B["close"]), pd.DatetimeIndex(B["index"])
    ts = pd.Timestamp(lbw[0])
    lb_i = int(ix.searchsorted(ts.tz_localize(ix.tz) if ix.tz is not None else ts))
    datesB = bar_dates(B["index"])
    lb = replay_lockbox(make_slice_evaluator(mod, B, cost, warm_days=0), datesB, B["day_id"], nb, lb_i, champ, warm, mult,
                        v.get("lockbox") or {})
    lb_daily, lb_out = daily_series(lb["booked"], [d for d in datesB.uniq if ld0 <= d <= ld1])
    lb_ok = lb["ok"] and abs(lb_out) < 1e-9
    log("  PARITY %s: %s (lockbox from bar %d, warm start %d)%s" % ("PASS" if lb_ok else "FAIL", lb["text"], lb_i, lb["warm_start"],
                                                                 "" if abs(lb_out) < 1e-9 else "  (%.2f $ outside the calendar)" % lb_out))
    rss = rss_mb()
    if rss:
        log("  peak RSS %.0f MB" % rss[1])
    return {"ok": wf_ok and lb_ok, "strategy": {"path": path, "lf_sha256": sha, "stored_name": N["strategy"]},
            "master": {"filename": m.get("filename"), "id": m.get("id"), "name": m.get("name"), "source": m.get("source")},
            "bars": n, "warm_days": warm,
            "wf": {"ok": wf_ok, "folds": wf["folds"], "chain": txt_c, "daily": (wf_daily if wf_ok else None)},
            "lb": {"ok": lb_ok, "text": lb["text"], "daily": (lb_daily if lb_ok else None)}}


def attach_daily(N, rep):
    """Put each parity-checked daily series where daily_of() looks (in memory only), so the whole reading runs on it. A stretch
    whose parity failed gets none: its four numbers stay the stored-curve ones, labelled NOT DAILY."""
    v = N["v"]
    for key, blk in (("wf", "wf_oos"), ("lb", "lockbox")):
        if rep[key]["daily"] and isinstance(v.get(blk), dict):
            v[blk]["daily"] = [[str(a), x] for a, x in rep[key]["daily"]]
    N["daily_label"] = "daily $ rebuilt by --replay (parity-checked), each trade booked on its EXIT bar's NY date"


# ---------------------------------------------------------------- selftest (synthetic run, no Firestore)
def synthetic_run(up=15, picks=None, crown_session="rth", daily=False, dd_pts=330.0):
    """A run doc shaped like users/{uid}/runs/{n}: 8 folds, window 2016-01-04..2026-06-30, 8000 bars (init 3200, test 600).
    The WF curve is 10 cycles of +40 x `up`, -60 x5 (ten equal 300-point episodes): up=15 nets 3000 pts (healthy), up=9 nets
    600 (ROC ~9). Fold nets sum to the curve's net, as the real wf_oos block guarantees."""
    start, span, n, init, ts = datetime.date(2016, 1, 4), (datetime.date(2026, 6, 30) - datetime.date(2016, 1, 4)).days, 8000, 3200, 600
    day = lambda b: start + datetime.timedelta(days=int(round(b * span / float(n))))
    picks = picks or ["rth", "all", "rth", "outside_rth", "all", "rth", "all", "all"]
    cur, c = [], 0.0
    for _cyc in range(10):
        for x in [40.0] * up + [-60.0] * 5:
            c += x
            cur.append(c)
    net, w = cur[-1], [-3, -1, 1, 3, 5, 7, 9, 11]                      # fold weights sum to 32
    top, alt, wfolds = [], [], []
    for f in range(1, 9):
        s = init + ts * (f - 1)
        d0, d1, fnet = day(s), day(s + ts - 1), net * w[f - 1] / 32.0
        top.append({"fold": f, "session_filter": picks[f - 1], "sl_scale": 0.9, "tp_scale": 2.0, "max_hold_bars": 60,
                    "be_trigger": 1.0, "sl_cap_atr": "off", "vix_feed": "daily", "total_pnl": 900.0, "train_bars": init,
                    "test_bars": ts, "oos_pnl": fnet, "oos_trades": 200 + f, "oos_pf": 1.2 if fnet > 0 else 0.9,
                    "oos_wins": 90, "oos_win_rate": 45.0, "oos_from": str(d0), "oos_to": str(d1)})
        alt.append({"fold": f, "total_pnl": 800.0, "oos_pnl": 50.0 * f - 100.0, "oos_pf": 1.1 if f > 3 else 0.8,
                    "train_bars": s, "test_bars": ts})
        wfolds.append({"f": f, "from": str(d0), "to": str(d1), "trades": 200 + f, "net": fnet})
    wo = {"v": 1, "mode": "rolling", "n_folds": 8, "from": top[0]["oos_from"], "to": top[-1]["oos_to"],
          "years": round((datetime.date.fromisoformat(top[-1]["oos_to"]) - datetime.date.fromisoformat(top[0]["oos_from"])).days
                         / 365.25, 3), "trades": 1636, "wins": 780, "win_rate": 45.9, "net": net, "profit_factor": 1.05,
          "avg_win": 40.0, "avg_loss": 33.0, "max_drawdown": dd_pts, "sharpe": 0.9, "sortino": 1.2, "equity": cur,
          "equity_n": 1636, "folds": wfolds}
    if daily:
        days, d = [], datetime.date.fromisoformat(top[0]["oos_from"])
        while d <= datetime.date.fromisoformat(top[-1]["oos_to"]):
            if d.weekday() < 5:
                days.append([str(d), 60.0 if (d.toordinal() % 7) else -140.0])
            d += datetime.timedelta(days=1)
        wo["daily"] = days
    inc = [40.0, 40.0, -30.0] * 13 + [40.0]                              # lockbox: 40 stored points, crown curve with dips
    lcum, base = [], 1000.0
    for x in inc:
        base += x
        lcum.append(base)
    sel = {"candidates": [{"params": {"session_filter": crown_session}, "crowned": True,
                           "lb_equity": {"cum": lcum, "final": lcum[-1], "base": 1000.0, "t": ["2025-07-01"] * len(lcum)}}]}
    return {"id": 999, "scope": "Auto-Validate", "timestamp": "2026-10-16 14:03", "strategy": "MISC_SUPERSCALPER_1_0.py",
            "instrument": "NQ", "timeframe": "1m", "data_source": "db_noadj_eth", "source_name": "NQ 1m ETH synthetic",
            "date_from": "2016-01-04", "date_to": "2026-06-30", "cost_pts": 0.706, "multiplier": 20.0, "n_combos": 1800,
            "best_params": {"session_filter": crown_session, "sl_scale": 0.9}, "top10_results": top, "wf_alt_folds": alt,
            "wf_alt_mode": "anchored", "selection": sel, "dsr": {"dsr": 0.9, "luck_bar": 1.1},
            "validate": {"verdict": "WEAK", "n_pass": 5, "n_gates": 6, "checks": {"pbo": False, "wfe": True},
                         "pbo": {"pbo": 0.4, "n_configs": 24}, "dsr": 0.9, "wfe": 0.7, "folds_held": 4, "n_folds": 8,
                         "wf_best_mode": "rolling", "windows": {"optimize": ["2016-01-04", "2025-06-29"],
                                                                "lockbox": ["2025-06-30", "2026-06-30"], "lockbox_months": 12,
                                                                "warm_days": 20, "wf_split": top[0]["oos_from"]},
                         "wf_oos": wo, "total_trades": 2600, "total_win_rate": 46.0, "total_avg_win": 41.0,
                         "total_avg_loss": 34.0,
                         "lockbox": {"pnl": sum(inc), "pf": 1.1, "trades": 300, "win_rate": 47.0, "sharpe": 0.8, "sortino": 1.0,
                                     "dd": 33.0, "avg_win": 38.0, "avg_loss": 31.0, "from": "2025-06-30", "to": "2026-06-30"}}}


def selftest():
    bad, n = [], [0]

    def check(cond, msg):
        n[0] += 1
        if not cond:
            bad.append(msg)
            print("FAIL:", msg)

    D = datetime.date
    # groups, pure
    check(fold_group(D(2022, 7, 1), D(2022, 12, 31), D(2016, 1, 4), D(2022, 6, 30)) == "a", "fold ending 2022-12-31 is CLEAN")
    check(fold_group(D(2022, 10, 3), D(2023, 6, 30), D(2016, 1, 4), D(2022, 10, 2)) == "b", "fold 2022-10..2023-06 is (b)")
    check(fold_group(D(2025, 2, 3), D(2025, 8, 29), D(2021, 3, 1), D(2025, 2, 2)) == "b", "train covering 2023 is (b)")
    check(fold_group(D(2026, 3, 2), D(2026, 6, 30), D(2025, 2, 3), D(2026, 3, 1)) == "other", "post-2024 clean train is 'other'")
    check(fold_group(D(2026, 3, 2), D(2026, 6, 30), None, None) == "b", "unknown train after 2024 is never clean")
    check(fold_group(None, None, None, None) is None, "no dates -> no group")
    # four() on a hand-checked series: cum 100,200,50,-100,0,100,200,300 -> worst DD 300, one episode, ROC 30, k 100
    f = four([100.0, 100.0, -150.0, -150.0, 100.0, 100.0, 100.0, 100.0], 1.0)
    check(abs(f["roc30"] - 30.0) < 1e-9 and f["dd5_n"] == 1 and abs(f["dd5_at_30k"] - 30000.0) < 1e-6, "four(): ROC 30, DD5 30000")
    check(abs(f["dd_pct_peak_at_30k"] - 25.0) < 1e-6 and not f["one_episode"] and f["sortino"] > 0, "four(): DD% 25, n=1 flag silent")
    one = four([20.0] * 100 + [-1500.0] + [20.0] * 120 + [-10.0, 20.0] * 20, 3.0, daily=False)
    check(one["one_episode"], "one deep episode among small ones flags 1 EPISODE")
    # verdict
    check(verdict({"roc30": 12.0, "one_episode": False}) == "DEAD", "verdict DEAD when ROC < 15")
    check(verdict({"roc30": 40.0, "one_episode": True}) == "DEAD", "verdict DEAD when 1 EPISODE")
    check(verdict({"roc30": 20.0, "one_episode": False}) == "WF clears ROC 15 - read LB", "verdict clears at ROC 20")
    check(verdict(None).startswith("NO WF FIGURE"), "verdict without a WF figure says so")
    # a whole synthetic run (up=9: ROC ~9)
    R = build_reading(normalize(synthetic_run(up=9), None, "JOBX"))
    grp = {r["fold"]: r["group"] for r in R["folds"]["primary"]}
    check(grp == {1: "a", 2: "a", 3: "a", 4: "b", 5: "b", 6: "b", 7: "b", 8: "b"}, "pipeline groups %s" % grp)
    f8 = R["folds"]["primary"][-1]
    check(f8["test_from"] > DEV1 and f8["train_from"] <= DEV1 and group_reason(f8).startswith("train"), "fold 8 is (b) via its TRAIN window")
    check({r["fold"]: r["group"] for r in R["folds"]["alt"]} == grp, "alt scheme groups follow the same test windows")
    ga = R["groups"]["primary"]
    check(ga["a"]["folds"] == [1, 2, 3] and ga["c"]["folds"] == [1, 2, 3] and ga["b"]["folds"] == [4, 5, 6, 7, 8], "(a) (b) (c) folds")
    check(abs(ga["a"]["net_usd"] - 20.0 * 600.0 * (-3 - 1 + 1) / 32.0) < 1e-6, "(a) summed OOS net in $")
    check(abs(ga["a"]["net_usd"] + ga["b"]["net_usd"] - ga["all"]["net_usd"]) < 1e-6 and ga["all"]["n"] == 8, "(a) + (b) = whole chain")
    check(ga["a"]["held"] == 1 and ga["b"]["held"] == 5 and ga["a"]["four"] is None, "folds with PF>1 counted; no daily -> no four")
    check(R["verdict"] == "DEAD" and R["wf"]["four"]["roc30"] < ROC_BAR, "synthetic WF ROC < 15 -> DEAD (%s)" % num(R["wf"]["four"]["roc30"], 1))
    check(PICK_RULE in R["session"], "session rule line appears when picks differ")
    check(R["wf"]["four"]["roc30_curve"] >= R["wf"]["four"]["roc30"], "floor ROC <= curve ROC")
    check(R["recon"]["ok"], "fold nets reconcile with wf_oos.net")
    check(R["lb"]["four"] is not None and abs(R["lb"]["four"]["net_usd"] - 690.0 * 20.0) < 1e-6, "LB read from the crowned lb_equity")
    check(bool(json.dumps(_jsonable(R))), "reading is JSON-able")
    text = "\n".join(render(R))
    for needle in ("1. RUN", "2. THE FOUR NUMBERS", "3. PER-FOLD", "4. SESSION READING RULE", "5. FOLD GROUPS", "6. PRE-SET VERDICT",
                   "run #999", "job JOBX", "db_noadj_eth", PICK_RULE, "NOT DAILY", "agree"):
        check(needle in text, "render has %r" % needle)
    # session rule variants
    same = build_reading(normalize(synthetic_run(picks=["rth"] * 8), None, None))
    check(PICK_RULE not in same["session"] and any("same in every fold" in s for s in same["session"]), "same picks -> no noise line")
    allc = build_reading(normalize(synthetic_run(crown_session="all"), None, None))
    check(PICK_RULE not in allc["session"] and "not triggered" in allc["session"][0], "crown 'all' -> rule not triggered")
    # a healthy WF: ten equal episodes, big net -> clears, flag silent, no straddle note
    ok = build_reading(normalize(synthetic_run(up=15), None, None))
    check(ok["verdict"] == "WF clears ROC 15 - read LB" and not ok["wf"]["four"]["one_episode"], "healthy WF clears (%s)" % ok["verdict"])
    check("STRADDLES" not in (ok["caveat"] or ""), "no straddle note when both readings clear")
    # floor below 15 <= curve reading -> the caveat says the verdict is not final
    st = build_reading(normalize(synthetic_run(up=15, dd_pts=1000.0), None, None))
    check(st["verdict"] == "DEAD" and "STRADDLES" in st["caveat"], "bracket straddling 15 is called NOT FINAL")
    # a stored-net mismatch is flagged
    bd = synthetic_run()
    bd["validate"]["wf_oos"]["net"] += 50.0
    check(not build_reading(normalize(bd, None, None))["recon"]["ok"], "net mismatch flagged")
    # per-fold params missing -> said explicitly
    run = synthetic_run()
    for r in run["top10_results"]:
        for k in FOLD_PARAMS:
            r.pop(k, None)
    nop = "\n".join(render(build_reading(normalize(run, None, None))))
    check("per-fold params NOT STORED" in nop and "stored on these rows instead" in nop, "missing params are reported")
    # a stored daily series is used exactly, and the groups get the four numbers
    dr = build_reading(normalize(synthetic_run(daily=True), None, None))
    check("daily series stored" in dr["wf"]["resolution"] and dr["wf"]["four"]["sortino"] is not None, "daily series -> house four()")
    check(dr["groups"]["primary"]["a"]["four"] is not None and dr["groups"]["primary"]["b"]["four"] is not None, "group four numbers on daily days")
    # the doc shape of a job result (top, no run doc) reads too
    jr = synthetic_run()
    jr["top"] = jr.pop("top10_results")
    jn = normalize(None, {"run_id": 77, "n_trials": 900, "session": "eth", "result": jr}, "J77")
    check(jn["run_no"] == 77 and len(build_reading(jn)["folds"]["primary"]) == 8 and jn["trials"] == 900, "job-result fallback shape")
    # ---- --replay, the pure parts, on a synthetic world (no engine, no data): 1000 bars, 10 a day (day id = bar // 10), a trade
    #      every 25 bars that closes 12 bars later (so every trade crosses a date), and a fake slice evaluator with the engine's contract
    nb = 1000
    dts = [D(2020, 1, 1) + datetime.timedelta(days=b // 10) for b in range(nb)]
    dids = [b // 10 for b in range(nb)]
    world = [(e, e + 12, (e % 7) - 2.5) for e in range(0, 990, 25)]

    def fake_ev(a, b, params, keep_trades=False, warm=False):
        tr = [(e - a, min(x, b - 1) - a, p, 1, 100.0) for e, x, p in world if a <= e < b]       # indices relative to a
        return {"trades": tr, "total_pnl": sum(t[2] for t in tr)}

    check(warm_start_bar(dids, 400, 20) == 200 and warm_start_bar(dids, 100, 20) == 0, "warm start: 20 sessions back, or bar 0")
    check(warm_start_bar(dids, 400, 0) == 400 and warm_start_bar(dids, 0, 20) == 0, "no warm-up -> the stretch's own first bar")
    sl = fake_ev(200, 600, {}, keep_trades=True)["trades"]
    kept = fold_trades(sl, 200, 400, 600)
    check(0 < len(kept) < len(sl) and all(400 <= t[0] < 600 for t in kept), "fold filter keeps only trades ENTERING in [400, 600)")
    check(kept[0][0] == min(e for e, _x, _p in world if e >= 400) and kept[0][1] == kept[0][0] + 12, "kept trades carry absolute bars")
    check(fold_trades(sl, 200, 400, 425) == [t for t in kept if t[0] < 425], "the upper bound is exclusive")
    bk = book_by_exit(kept, dts, 20.0)
    check(all(d == dts[t[1]] and d != dts[t[0]] for (d, _u), t in zip(bk, kept)), "booked on the EXIT bar's date, not the entry's")
    check(abs(sum(u for _d0, u in bk) - 20.0 * sum(t[2] for t in kept)) < 1e-9, "booked $ = points x multiplier")
    check(book_by_exit([(990, 5000, 1.0)], dts, 20.0) == [(dts[-1], 20.0)], "an exit past the last bar books on the last date")
    cal = sorted(set(dts[400:600]))
    ds_, out_ = daily_series(bk, cal)
    check(len(ds_) == len(cal) and any(u == 0.0 for _d0, u in ds_) and out_ == 0.0, "daily series: every calendar date, zeros included")
    check(abs(sum(u for _d0, u in ds_) - sum(u for _d0, u in bk)) < 1e-9, "daily series keeps every booked $")
    check(daily_series(bk + [(D(2030, 1, 1), 5.0)], cal)[1] == 5.0, "$ booked outside the calendar is reported")
    # parity
    check(parity(5.0, 3, 5.0, 3)[0] and not parity(5.0, 3, 5.5, 3)[0] and not parity(5.0, 4, 5.0, 3)[0], "fold parity needs net AND count")
    check(parity(10.05, 4, 10.0, 4, tol=0.1)[0] and not parity(10.2, 4, 10.0, 4, tol=0.1)[0], "chain parity tolerance is 0.1 pts")
    check(not parity(float("nan"), 3, 1.0, 3)[0], "a NaN net never passes")
    # the fold chain: rolling-style rows (train_bars is the constant init 400, so te_s must come from the cumulative test bars)
    frows = []
    for f in (1, 2, 3):
        s0 = 400 + 200 * (f - 1)
        inn = [p for e, _x, p in world if s0 <= e < s0 + 200]
        frows.append({"fold": f, "train_bars": 400, "test_bars": 200, "oos_pnl": sum(inn), "oos_trades": len(inn), "sl_scale": 1.0})
    logs = []
    rep = replay_chain(fake_ev, dts, dids, frows, ["sl_scale"], 20, 20.0, logs.append)
    check(rep["ok"] and [f["te_s"] for f in rep["folds"]] == [400, 600, 800], "replay chain PASS; rolling bounds te_s = init + earlier tests")
    check(rep["trades"] == sum(r["oos_trades"] for r in frows) and abs(rep["net_pts"] - sum(r["oos_pnl"] for r in frows)) < 1e-9, "chain totals = the stored folds'")
    check(len(logs) == 3 and all("OK" in x for x in logs), "one parity line per fold")
    badrows = [dict(r) for r in frows]
    badrows[1]["oos_pnl"] += 1.0
    repb = replay_chain(fake_ev, dts, dids, badrows, ["sl_scale"], 20, 20.0, logs.append)
    check(not repb["ok"] and [f["ok"] for f in repb["folds"]] == [True, False, True] and "MISMATCH" in logs[-2], "a mismatch on fold 2 is caught and named")
    wo_ = {"net": round(rep["net_pts"], 1), "trades": rep["trades"]}
    check(chain_parity(rep, wo_)[0] and not chain_parity(rep, dict(wo_, net=wo_["net"] + 1.0))[0]
          and not chain_parity(rep, dict(wo_, trades=wo_["trades"] + 1))[0], "chain parity vs validate.wf_oos net and trades")
    # the lockbox stretch
    inlb = [p for e, _x, p in world if 800 <= e < 1000]
    saved = {"pnl": sum(inlb), "trades": len(inlb)}
    lbr = replay_lockbox(fake_ev, dts, dids, nb, 800, {}, 20, 20.0, saved)
    check(lbr["ok"] and lbr["trades"] == len(inlb) and lbr["lb_i"] == 800 and lbr["warm_start"] < 800, "lockbox replay matches the stored stretch")
    check(not replay_lockbox(fake_ev, dts, dids, nb, 800, {}, 20, 20.0, dict(saved, trades=len(inlb) + 1))["ok"], "a lockbox count mismatch fails")
    # bar bounds: rolling te_s is NOT train_bars
    fbs = fold_bounds(synthetic_run()["top10_results"])
    check(fbs[0][3] == (4400, 5000) and fbs[1] == 3200 and fbs[2] == 8000, "fold_bounds: rolling fold 3 tests from 4400, not train_bars 3200")
    check(fold_bounds([{"fold": 1, "train_bars": 10, "test_bars": 5}, {"fold": 3, "train_bars": 10, "test_bars": 5}]) is None, "a fold gap -> no bounds")
    # an attached replay series drives the reading; a stretch without one keeps the labelled stored-curve reading
    rn = synthetic_run(up=15)
    N2 = normalize(rn, None, None)
    t0, t1 = _d(rn["validate"]["wf_oos"]["from"]), _d(rn["validate"]["wf_oos"]["to"])
    wdays = [t0 + datetime.timedelta(days=i) for i in range((t1 - t0).days + 1) if (t0 + datetime.timedelta(days=i)).weekday() < 5]
    attach_daily(N2, {"wf": {"daily": [(d, 60.0 if d.toordinal() % 7 else -140.0) for d in wdays]}, "lb": {"daily": None}})
    Rr = build_reading(N2)
    check("--replay" in Rr["wf"]["resolution"] and Rr["wf"]["four"]["sortino"] is not None and Rr["wf"]["four"]["roc30_curve"] is None, "replay daily drives the WF four numbers")
    check(Rr["groups"]["primary"]["a"]["four"] is not None and Rr["groups"]["primary"]["b"]["four"] is not None and Rr["caveat"] is None, "fold groups cut by day")
    check(Rr["lb"]["resolution"].startswith("NOT DAILY"), "a stretch with no replay series keeps the labelled stored reading")
    check(Rr["verdict"] == verdict(Rr["wf"]["four"]), "the verdict is read on the daily WF ROC")
    Rr["replay"] = {"ok": False}
    check("REPLAY PARITY FAILED" in "\n".join(render(Rr)), "a failed replay says so under the verdict")
    print("SELFTEST %s (%d checks)" % ("FAIL" if bad else "PASS", n[0]))
    return 1 if bad else 0


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only pre-registered reading of a finished SUPERSCALPER Auto-Validate run.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--run", type=int, help="run number (Past Runs)")
    g.add_argument("--job", help="job id (queue backtests doc)")
    ap.add_argument("--json", help="also write the reading to this file")
    ap.add_argument("--selftest", action="store_true", help="synthetic run, no Firestore, no engine")
    ap.add_argument("--replay", action="store_true", help="rebuild the daily $ series by re-running the validate's folds and "
                    "lockbox stretch (read-only; needs the masters)")
    ap.add_argument("--repo", default=SHARED, help="checkout whose engine + master registry --replay uses (default: the shared one)")
    ap.add_argument("--strategy-file", help="the port .py to replay (default: <repo>/augur_strategies/<run's strategy>)")
    ap.add_argument("--port-sha", help="refuse unless the strategy file's LF sha256 is this")
    ap.add_argument("--session", help="rth | eth for the master lookup (default: from the job doc / the data_source suffix)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.run or a.job):
        ap.error("give --run N or --job ID (or --selftest)")
    rdoc, jdoc, jid = fetch(a.run, a.job)
    N = normalize(rdoc, jdoc, jid)
    if not N["v"]:
        print("run #%s is not a finished Auto-Validate (no validate block; scope %s)" % (N["run_no"], N["scope"]))
        return 3
    if a.session:
        N["session"] = a.session
    rep = None
    if a.replay:
        rep = replay(N, a.repo, a.strategy_file, a.port_sha)
        attach_daily(N, rep)
        print("")
    R = build_reading(N)
    if rep:
        R["replay"] = {"ok": rep["ok"], "strategy": rep["strategy"], "master": rep["master"], "bars": rep["bars"],
                       "warm_days": rep["warm_days"],
                       "wf": {"ok": rep["wf"]["ok"], "chain": rep["wf"]["chain"], "folds": rep["wf"]["folds"]},
                       "lb": {"ok": rep["lb"]["ok"], "text": rep["lb"]["text"]}}
    print("\n".join(render(R)))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(_jsonable(R), fh, indent=1)
    return 0 if (rep is None or rep["ok"]) else 4


if __name__ == "__main__":
    sys.exit(main())
