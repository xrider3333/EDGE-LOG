"""LENS: statistical power of the lockbox length (2026-09-16 wfdive deep dive).

Owner questions this lens serves: is a 12-month lockbox long enough to trust its
PASS/FAIL, would a longer lockbox (18/24/36mo) separate a real edge from no edge,
what would that longer lockbox cost the tuning search (the newest years disappear
from Stage A/B), and how much of a long-warm-up strategy's lockbox is cold-start
noise rather than edge decay.

METHOD (every number here comes from replaying the SAVED crowned champion's FIXED
params through augur_engine.engine.run_backtest on the SHARED checkout's market
data -- never a second optimization, never a guess):

  1. Pick the 3 owner-starred crowns (#257 ORB, #335 ENGU-Q, #243 NOISE) plus the
     NEWEST run in every OTHER (strategy-file, instrument, timeframe) family that
     carries both a champion and a lockbox on a known/replayable data source
     (db_noadj_rth / db_noadj_eth / yahoo_adj) -- 17 more, cap 20, books excluded.
  2. For each: THREE backtests with the doc's own validate.champion params,
     cost_pts, instrument/timeframe/session/source --
       (a) CONTINUOUS whole-run  [doc.date_from .. doc.date_to]      (warm)
       (b) COLD 12mo lockbox     [windows.lockbox[0] .. date_to]     (cold; this is
           validate.py's OWN lockbox call byte-for-byte -- the reproduction check)
       (c) COLD 24mo lockbox     [date_to - 24mo .. date_to]         (cold; not
           saved anywhere, run fresh, for the 12-vs-24 cold-start comparison)
     Every trade's entry bar index is mapped back to a real timestamp via the
     loaded arrays["index"], so every stat below is sliced by REAL calendar dates,
     never a bar count.
  3. VERIFY: (b) must reproduce validate.lockbox (trades within 1, net within
     max($5, 2%), PF within 0.02) or the run is DROPPED and the reason logged --
     this is the strong, universal check (present on every selected run by
     construction). Where gate_validate exists, (a) sliced full-window is also
     compared to gate_validate.ungated_full as a secondary, logged-only check.
  4. HONEST EDGE = continuous replay (a)'s trades with entry date >= the doc's own
     Stage-A 75/25 split (validate.windows.wf_split, else
     gate_validate.wf_range[0], else the crowned candidate's own
     selection.candidates[].is_rng.to, else an approximate 75%-of-calendar-days
     fallback, flagged as such) -- i.e. every trade the champion search never
     used to pick or score itself. This pool covers the real WF years AND the
     real lockbox year in one continuous (never cold-restarted) series.
  5. POWER TABLE: month-block bootstrap (2,500 resamples) of the honest-edge pool
     at lockbox lengths 12/18/24/36 months -- draw L calendar months WITH
     REPLACEMENT from the pool's own available months, sum their trades, report
     P(net>0), P(PF>1.2), P(app's lockbox verdict passes) = P(net>0 AND PF>=1.0)
     (validate.py line ~805: `lb_pass = lb_pnl > 0 and lb_pf >= 1.0` -- the only
     part of the PASS/WEAK/FAIL verdict that is a function of the lockbox window
     itself; the other four gates (sample/plateau/wfe/consistency/luck) are
     properties of the ORIGINAL Stage A/B run and do not change with a
     hypothetical lockbox length, so they are not simulated here). SAME bootstrap
     re-run on the pool with every trade's pnl shifted by a constant so the pool's
     OWN mean is exactly zero (a "no real edge" control with the same trade
     density/skew) -> the false-pass rate at each length.
  6. RECENCY: Spearman rho of per-calendar-year PF vs year (continuous replay),
     and the net/PF of the specific years that would move from "tuning-visible"
     to "lockbox-only" if the lockbox grew from 12 to 24 or 36 months.
  7. COLD-START SHARE: 1 - cold_trades/warm_trades at 12mo (validate.lockbox vs
     the continuous replay's own lockbox-window slice) and at 24mo (fresh cold
     backtest vs the continuous replay's last-24-months slice).

Run from the WORKTREE root:
    python tools/wfdive/lens_lblen.py
Writes: _wfdive_data/lens_lblen.json
Single process, no multiprocessing pools, BELOW_NORMAL priority, one cpu_lock
held for the whole batch (a plain run_backtest over each of these strategies
measures well under a few seconds -- see BACKTEST_SPEED.md section 4 -- so one
lock for ~60 backtests is a short hold, not a monopoly).
"""
import datetime as _dt
import json
import math
import os
import sys
import traceback
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats as _sps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> tools/
from wfdive.common import (  # noqa: E402
    setup_data_env, low_priority, cpu_lock, family_key, load_runs, DATA_DIR,
)

os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

OUT_PATH = os.path.join(DATA_DIR, "lens_lblen.json")

# data_source -> session, exactly tools/backfill_wf_oos.py's SESSION map
SESSION_MAP = {"db_noadj_rth": "rth", "db_noadj_eth": "eth", "yahoo_adj": "rth"}

CROWN_IDS = [257, 335, 243]      # owner stars: ORB, ENGU-Q, NOISE (book #366 excluded)
N_OTHER = 17                      # cap 20 total
N_RESAMPLES = 2500
LOCKBOX_LENGTHS_MONTHS = [12, 18, 24, 36]
RNG_SEED = 20260916

NET_REL_TOL = 0.02
NET_ABS_TOL = 5.0
PF_TOL = 0.02
TRADE_TOL = 1


def log(*a):
    print("[lens_lblen]", *a, flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# selection
# ─────────────────────────────────────────────────────────────────────────────
def select_runs(runs):
    by_id = {r["id"]: r for r in runs}
    book_ids = set()
    try:
        cov = json.load(open(os.path.join(DATA_DIR, "coverage.json"), encoding="utf-8"))
        book_ids = set(cov.get("books", {}).get("ids") or [])
    except Exception:
        pass
    known_src = set(SESSION_MAP)

    crowns = [by_id[i] for i in CROWN_IDS if i in by_id]
    missing_crowns = [i for i in CROWN_IDS if i not in by_id]
    crown_fams = {family_key(r) for r in crowns}

    fam_runs = defaultdict(list)
    for r in runs:
        if r["id"] in book_ids:
            continue
        v = r.get("validate") or {}
        if not v.get("champion") or not v.get("lockbox"):
            continue
        if r.get("data_source") not in known_src:
            continue
        fam_runs[family_key(r)].append(r)

    others = []
    for fam, rs in fam_runs.items():
        if fam in crown_fams:
            continue
        others.append(sorted(rs, key=lambda r: r["id"], reverse=True)[0])
    others_sorted = sorted(others, key=lambda r: r["id"], reverse=True)
    picked = others_sorted[:N_OTHER]

    selected = crowns + picked
    meta = {
        "missing_crowns": missing_crowns,
        "n_candidate_other_families": len(others_sorted),
        "n_other_picked": len(picked),
        "selection_rule": "newest run id per (strategy-file, instrument, timeframe) "
                           "family with a champion + lockbox on a known data source, "
                           "excluding books and the 3 crown families, sorted by run id "
                           "desc, top 17",
    }
    return selected, meta


# ─────────────────────────────────────────────────────────────────────────────
# replay plumbing
# ─────────────────────────────────────────────────────────────────────────────
def _loc_ts(date_str, idx):
    if not date_str:
        return None
    ts = pd.Timestamp(date_str)
    if ts.tzinfo is None:
        tz = getattr(idx, "tz", None)
        if tz is not None:
            ts = ts.tz_localize(tz)
    return ts


_FULL_ARRAYS_CACHE = {}   # (instrument, timeframe, session, source) -> (arrays|None, err|None)


def _load_full_arrays(instrument, timeframe, session, source):
    """Load one master CSV's FULL (unsliced) arrays exactly once per process, via
    the real augur_engine.data.load_master_arrays (so the CSV read + US/Eastern
    tz conversion is byte-identical to a live validate). load_arrays_for() below
    then does its OWN date-window slice + day_id re-factorization on the cached
    numpy arrays -- replicating load_master_arrays' own slicing logic (its lines
    ~134-139: date_from inclusive, date_to inclusive of the whole calendar day,
    day_id factorized fresh per slice) so every window this script asks for is
    IDENTICAL to what a fresh load_master_arrays(date_from=.., date_to=..) call
    would return. This exists only to avoid re-reading the same multi-year CSV
    off disk 3x per run x 20 runs when several selected runs share one master
    (all the NQ 5m RTH families, all four ENGU-Q 1m ETH R2-R5 variants, ...)."""
    key = (instrument, timeframe, session, source)
    if key in _FULL_ARRAYS_CACHE:
        return _FULL_ARRAYS_CACHE[key]
    from augur_engine.data import find_master, load_master_arrays
    master = find_master(instrument, timeframe, session, source)
    if master is None:
        result = (None, f"no master for {instrument} {timeframe} {session} {source!r}")
    else:
        arrays = load_master_arrays(master, date_from=None, date_to=None)
        result = (arrays, None)
    _FULL_ARRAYS_CACHE[key] = result
    return result


def load_arrays_for(doc, date_from, date_to):
    src = doc.get("data_source")
    sess = SESSION_MAP.get(src)
    if sess is None:
        return None, f"unknown data_source {src!r}"
    full, err = _load_full_arrays(doc["instrument"], doc["timeframe"], sess, src)
    if err:
        return None, err
    idx = full["index"]
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz=idx.tz))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz=idx.tz) + pd.Timedelta(days=1))
    sub_index = idx[mask]
    day_id = pd.factorize(pd.Series(sub_index).dt.date)[0].astype("int64")
    arrays = {
        "open": full["open"][mask], "high": full["high"][mask],
        "low": full["low"][mask], "close": full["close"][mask],
        "volume": (full["volume"][mask] if full.get("volume") is not None else None),
        "day_id": day_id, "index": sub_index, "meta": full.get("meta"),
    }
    return arrays, None


def run_champion(doc, arrays, params):
    from augur_engine.engine import run_backtest
    cost_pts = doc.get("cost_pts")
    return run_backtest(doc["strategy"], arrays=arrays, params=params,
                         cost_pts=float(cost_pts), return_trades=True)


def pairs_from_result(res, arrays):
    """[(pd.Timestamp entry, float net pnl), ...] in trade order, sorted by entry."""
    if not res or not res.get("trades"):
        return []
    idx = arrays["index"]
    nb = len(idx)
    out = []
    for t in res["trades"]:
        try:
            eb = int(t[0]); pnl = float(t[2])
        except Exception:
            continue
        ts = pd.Timestamp(idx[min(max(eb, 0), nb - 1)])
        out.append((ts, pnl))
    out.sort(key=lambda x: x[0])
    return out


def metrics_from(pairs):
    n = len(pairs)
    if n == 0:
        return {"trades": 0, "net": 0.0, "pf": 0.0, "win_rate": None, "wins": 0, "losses": 0}
    pnls = [p for _, p in pairs]
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    net = float(sum(pnls))
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    return {"trades": n, "net": net, "pf": pf,
            "win_rate": (100.0 * wins / n), "wins": wins, "losses": losses}


def slice_pairs(pairs, t0=None, t1=None):
    """[t0, t1] inclusive both ends (calendar-date semantics used everywhere here)."""
    out = []
    for ts, pnl in pairs:
        if t0 is not None and ts < t0:
            continue
        if t1 is not None and ts > t1:
            continue
        out.append((ts, pnl))
    return out


def _pf_close(a, b, tol=PF_TOL):
    if a is None or b is None:
        return True
    fa, fb = float(a), float(b)
    if math.isinf(fa) or math.isinf(fb):
        return fa == fb
    return abs(fa - fb) <= tol


# ─────────────────────────────────────────────────────────────────────────────
# wf_split (Stage-A 75/25 cut) resolution
# ─────────────────────────────────────────────────────────────────────────────
def get_wf_split(doc):
    v = doc.get("validate") or {}
    w = v.get("windows") or {}
    if w.get("wf_split"):
        return w["wf_split"], "windows.wf_split"
    gv = doc.get("gate_validate") or {}
    wr = gv.get("wf_range")
    if isinstance(wr, list) and wr and wr[0]:
        return wr[0], "gate_validate.wf_range[0]"
    sel = doc.get("selection") or {}
    for c in (sel.get("candidates") or []):
        if c.get("crowned"):
            isr = c.get("is_rng") or {}
            if isr.get("to"):
                return isr["to"], "selection.candidates[crowned].is_rng.to"
    opt = w.get("optimize")
    if isinstance(opt, list) and len(opt) == 2 and opt[0] and opt[1]:
        try:
            d0 = _dt.date.fromisoformat(str(opt[0])[:10])
            d1 = _dt.date.fromisoformat(str(opt[1])[:10])
            days = (d1 - d0).days
            split = d0 + _dt.timedelta(days=int(days * 0.75))
            return split.isoformat(), "approx_75pct_calendar_days(windows.optimize)"
        except Exception:
            pass
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# month-block bootstrap
# ─────────────────────────────────────────────────────────────────────────────
def build_month_table(pairs):
    buckets = defaultdict(list)
    for ts, p in pairs:
        buckets[(ts.year, ts.month)].append(p)
    months = sorted(buckets.keys())
    net = np.array([sum(buckets[m]) for m in months], float)
    n = np.array([len(buckets[m]) for m in months], float)
    gw = np.array([sum(x for x in buckets[m] if x > 0) for m in months], float)
    gl = np.array([-sum(x for x in buckets[m] if x < 0) for m in months], float)
    return months, net, n, gw, gl


def bootstrap_lockbox(month_table, months_per_lockbox, n_resamples, rng):
    months, net, n, gw, gl = month_table
    n_avail = len(months)
    if n_avail == 0:
        return None
    idxs = rng.integers(0, n_avail, size=(n_resamples, months_per_lockbox))
    r_net = net[idxs].sum(axis=1)
    r_gw = gw[idxs].sum(axis=1)
    r_gl = gl[idxs].sum(axis=1)
    r_n = n[idxs].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r_pf = np.where(r_gl > 1e-9, r_gw / r_gl, np.where(r_gw > 0, np.inf, 0.0))
    return {
        "n_resamples": int(n_resamples),
        "n_months_available": int(n_avail),
        "months_per_lockbox": int(months_per_lockbox),
        "p_net_gt_0": float(np.mean(r_net > 0)),
        "p_pf_gt_1.2": float(np.mean(np.isfinite(r_pf) & (r_pf > 1.2) | np.isinf(r_pf))),
        "p_verdict_pass": float(np.mean((r_net > 0) & (r_pf >= 1.0))),
        "median_net": float(np.median(r_net)),
        "median_trades": float(np.median(r_n)),
    }


def demeaned(pairs):
    if not pairs:
        return pairs
    mean_pnl = sum(p for _, p in pairs) / len(pairs)
    return [(ts, p - mean_pnl) for ts, p in pairs]


# ─────────────────────────────────────────────────────────────────────────────
# per-run pipeline
# ─────────────────────────────────────────────────────────────────────────────
def process_run(doc, rng):
    rid = doc["id"]
    fam = family_key(doc)
    out = {"id": rid, "family": fam, "strategy": doc.get("strategy"),
           "instrument": doc.get("instrument"), "timeframe": doc.get("timeframe"),
           "data_source": doc.get("data_source"), "starred": bool(doc.get("starred")),
           "crown": rid in CROWN_IDS}

    v = doc.get("validate") or {}
    champ = v.get("champion") or {}
    windows = v.get("windows") or {}
    lb_window = windows.get("lockbox") or [None, None]
    lb_from, lb_to_saved = lb_window[0], (lb_window[1] if len(lb_window) > 1 else None)
    date_from = doc.get("date_from")
    date_to = doc.get("date_to") or lb_to_saved
    out["date_from"], out["date_to"] = date_from, date_to
    out["lockbox_window"] = [lb_from, lb_to_saved]
    out["lockbox_months_doc"] = windows.get("lockbox_months")

    if not champ or not date_from or not date_to or not lb_from:
        out["ok"] = False
        out["drop_reason"] = "missing champion/date_from/date_to/lockbox window on doc"
        return out

    # (a) continuous whole-run replay
    try:
        arr_a, err = load_arrays_for(doc, date_from, date_to)
        if err:
            out["ok"] = False; out["drop_reason"] = f"load_arrays(continuous): {err}"
            return out
        res_a = run_champion(doc, arr_a, champ)
        pairs_a = pairs_from_result(res_a, arr_a)
    except Exception as e:
        out["ok"] = False
        out["drop_reason"] = f"continuous replay raised {type(e).__name__}: {e}"
        return out
    if not pairs_a:
        out["ok"] = False; out["drop_reason"] = "continuous replay produced 0 trades"
        return out

    # (b) cold 12mo lockbox replay -- validate.py's own construction, byte for byte
    try:
        arr_b, err = load_arrays_for(doc, lb_from, date_to)
        if err:
            out["ok"] = False; out["drop_reason"] = f"load_arrays(cold12): {err}"
            return out
        res_b = run_champion(doc, arr_b, champ)
        pairs_b = pairs_from_result(res_b, arr_b)
    except Exception as e:
        out["ok"] = False
        out["drop_reason"] = f"cold-12 replay raised {type(e).__name__}: {e}"
        return out
    cold12_metrics = metrics_from(pairs_b)

    # verify against validate.lockbox (universal, strong check)
    lb_saved = v.get("lockbox") or {}
    saved_trades = int(lb_saved.get("trades") or 0)
    saved_net = float(lb_saved.get("pnl") or 0.0)
    saved_pf = lb_saved.get("pf")
    reasons = []
    ok = True
    if abs(cold12_metrics["trades"] - saved_trades) > TRADE_TOL:
        ok = False
        reasons.append(f"cold-12 lockbox trades {cold12_metrics['trades']} vs saved {saved_trades}")
    tol = max(NET_ABS_TOL, NET_REL_TOL * abs(saved_net))
    if abs(cold12_metrics["net"] - saved_net) > tol:
        ok = False
        reasons.append(f"cold-12 lockbox net {cold12_metrics['net']:.1f} vs saved "
                        f"{saved_net:.1f} (tol {tol:.1f})")
    if saved_pf is not None and not _pf_close(cold12_metrics["pf"], saved_pf, max(PF_TOL, 0.02)):
        ok = False
        reasons.append(f"cold-12 lockbox pf {cold12_metrics['pf']:.3f} vs saved {saved_pf}")
    out["verify_lockbox_reproduction"] = {"ok": ok, "reasons": reasons,
                                           "replayed": cold12_metrics,
                                           "saved": {"trades": saved_trades, "net": saved_net,
                                                     "pf": saved_pf}}

    # secondary, logged-only check vs gate_validate.ungated_full (continuous, warm)
    gv = doc.get("gate_validate") or {}
    ung_full = gv.get("ungated_full")
    if ung_full:
        full_m = metrics_from(pairs_a)
        sn = float(ung_full.get("total_pnl") or 0.0)
        st_ = int(ung_full.get("num_trades") or 0)
        gtol = max(NET_ABS_TOL, NET_REL_TOL * abs(sn))
        gv_ok = (abs(full_m["trades"] - st_) <= max(TRADE_TOL, 2) and abs(full_m["net"] - sn) <= gtol)
        out["verify_ungated_full_secondary"] = {
            "ok": gv_ok, "replayed": full_m,
            "saved": {"trades": st_, "net": sn, "pf": ung_full.get("profit_factor")},
        }
        if not gv_ok:
            reasons.append(f"[secondary,non-fatal] continuous full {full_m['trades']}tr/"
                            f"{full_m['net']:.0f}pt vs ungated_full {st_}tr/{sn:.0f}pt")

    if not ok:
        out["ok"] = False
        out["drop_reason"] = "; ".join(reasons)
        return out
    out["ok"] = True
    if reasons:
        out["verify_warnings"] = reasons

    # (c) cold 24mo lockbox replay (fresh, not saved anywhere)
    date_to_ts = _loc_ts(date_to, arr_a["index"])
    from_24 = (date_to_ts - pd.DateOffset(months=24)).date().isoformat()
    try:
        arr_c, err = load_arrays_for(doc, from_24, date_to)
        pairs_c = pairs_from_result(run_champion(doc, arr_c, champ), arr_c) if not err else []
        if err:
            out["cold24_error"] = err
    except Exception as e:
        pairs_c = []
        out["cold24_error"] = f"{type(e).__name__}: {e}"
    cold24_metrics = metrics_from(pairs_c)

    # ── per-calendar-year table (continuous replay) ──────────────────────────
    wf_split_date, wf_split_src = get_wf_split(doc)
    out["wf_split"] = {"date": wf_split_date, "source": wf_split_src}
    wf_split_ts = _loc_ts(wf_split_date, arr_a["index"]) if wf_split_date else None

    by_year = defaultdict(list)
    for ts, p in pairs_a:
        by_year[ts.year].append(p)
    years_table = []
    for yr in sorted(by_year):
        m = metrics_from([(None, p) for p in by_year[yr]])
        crowned_on = (wf_split_ts is not None and
                      pd.Timestamp(yr, 12, 31, tz=wf_split_ts.tz) < wf_split_ts)
        years_table.append({"year": yr, "trades": m["trades"], "net": round(m["net"], 1),
                             "pf": (round(m["pf"], 3) if math.isfinite(m["pf"]) else None),
                             "win_rate": (round(m["win_rate"], 1) if m["win_rate"] is not None else None),
                             "crowned_on": bool(crowned_on) if wf_split_ts is not None else None})
    out["by_year"] = years_table

    # Spearman rho of PF vs year (years with >=5 trades only)
    yrs_for_rho = [(r["year"], r["pf"]) for r in years_table if r["trades"] >= 5 and r["pf"] is not None]
    if len(yrs_for_rho) >= 4:
        yy = [a for a, _ in yrs_for_rho]; pp = [b for _, b in yrs_for_rho]
        rho, pval = _sps.spearmanr(yy, pp)
        out["recency_pf_trend"] = {"spearman_rho": float(rho), "p_value": float(pval),
                                    "n_years": len(yrs_for_rho)}
    else:
        out["recency_pf_trend"] = {"spearman_rho": None, "p_value": None,
                                    "n_years": len(yrs_for_rho),
                                    "note": "fewer than 4 qualifying years (>=5 trades) -- not computed"}

    # honest-edge pool + power table
    if wf_split_ts is None:
        out["power_table"] = None
        out["honest_edge_note"] = "no wf_split resolvable -- power table skipped"
    else:
        honest_pairs = slice_pairs(pairs_a, t0=wf_split_ts)
        honest_m = metrics_from(honest_pairs)
        out["honest_edge"] = {"from": wf_split_date, "to": date_to, "source": wf_split_src,
                               **honest_m}
        if honest_m["trades"] < 20:
            out["power_table"] = None
            out["honest_edge_note"] = (f"only {honest_m['trades']} honest-edge trades -- "
                                        "too few for a meaningful bootstrap, skipped")
        else:
            table_real = build_month_table(honest_pairs)
            table_noedge = build_month_table(demeaned(honest_pairs))
            power = {}
            for L in LOCKBOX_LENGTHS_MONTHS:
                real = bootstrap_lockbox(table_real, L, N_RESAMPLES, rng)
                noedge = bootstrap_lockbox(table_noedge, L, N_RESAMPLES, rng)
                power[str(L)] = {"real_edge": real, "no_edge_control": noedge}
            out["power_table"] = power
            # length at which real edge passes >=80% AND no-edge false-pass <=20%
            crossing = None
            for L in LOCKBOX_LENGTHS_MONTHS:
                r = power[str(L)]["real_edge"]["p_verdict_pass"]
                f = power[str(L)]["no_edge_control"]["p_verdict_pass"]
                if r >= 0.80 and f <= 0.20:
                    crossing = L
                    break
            out["power_crossing_months"] = crossing

    # ── cold-start share at 12mo and 24mo ────────────────────────────────────
    lb_from_ts = _loc_ts(lb_from, arr_a["index"])
    warm12 = metrics_from(slice_pairs(pairs_a, t0=lb_from_ts, t1=date_to_ts))
    from_24_ts = _loc_ts(from_24, arr_a["index"])
    warm24 = metrics_from(slice_pairs(pairs_a, t0=from_24_ts, t1=date_to_ts))
    cold_start = {
        "12mo": {"warm_trades": warm12["trades"], "cold_trades": cold12_metrics["trades"],
                 "share_lost": (round(1 - cold12_metrics["trades"] / warm12["trades"], 3)
                                if warm12["trades"] else None)},
        "24mo": {"warm_trades": warm24["trades"], "cold_trades": cold24_metrics["trades"],
                 "share_lost": (round(1 - cold24_metrics["trades"] / warm24["trades"], 3)
                                if warm24["trades"] else None)},
    }
    out["cold_start_share"] = cold_start

    # ── recency cost: years that would move from tuning-visible to lockbox-only ──
    if wf_split_ts is not None:
        cur_lb_start = lb_from_ts
        extra_24 = metrics_from(slice_pairs(pairs_a, t0=from_24_ts, t1=cur_lb_start))
        from_36_ts = _loc_ts((date_to_ts - pd.DateOffset(months=36)).date().isoformat(), arr_a["index"])
        extra_36 = metrics_from(slice_pairs(pairs_a, t0=from_36_ts, t1=cur_lb_start))
        rest_before = metrics_from(slice_pairs(pairs_a, t1=from_36_ts))
        out["recency_cost"] = {
            "note": "trades that would move from tuning-visible (IS+WF) to lockbox-only "
                    "if the lockbox grew from its current 12mo to 24 or 36mo",
            "extra_12mo_if_lockbox_to_24": {k: (round(v, 3) if isinstance(v, float) else v)
                                             for k, v in extra_24.items()},
            "extra_24mo_if_lockbox_to_36": {k: (round(v, 3) if isinstance(v, float) else v)
                                             for k, v in extra_36.items()},
            "remaining_tuning_pool_if_lockbox_36": {k: (round(v, 3) if isinstance(v, float) else v)
                                                     for k, v in rest_before.items()},
        }

    return out


# ─────────────────────────────────────────────────────────────────────────────
def main():
    low_priority()
    setup_data_env()
    runs = load_runs()
    selected, sel_meta = select_runs(runs)
    log(f"selected {len(selected)} runs: {[r['id'] for r in selected]}")
    log("selection meta:", sel_meta)

    rng = np.random.default_rng(RNG_SEED)
    results = []
    dropped = []
    with cpu_lock("lens_lblen: crown/family champion replays (single-threaded, low-priority)"):
        for doc in selected:
            rid = doc["id"]
            log(f"--- run #{rid} ({family_key(doc)}) {doc.get('strategy')} "
                f"{doc.get('instrument')} {doc.get('timeframe')} ---")
            try:
                r = process_run(doc, rng)
            except Exception as e:
                r = {"id": rid, "ok": False,
                     "drop_reason": f"unhandled {type(e).__name__}: {e}",
                     "traceback": traceback.format_exc()}
            if r.get("ok"):
                log(f"  ok  ({len(r.get('by_year', []))} years, "
                    f"honest_edge_trades={((r.get('honest_edge') or {}).get('trades'))}, "
                    f"power_crossing={r.get('power_crossing_months')})")
                results.append(r)
            else:
                log(f"  DROPPED: {r.get('drop_reason')}")
                dropped.append(r)

    payload = {
        "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
        "n_resamples": N_RESAMPLES,
        "lockbox_lengths_months": LOCKBOX_LENGTHS_MONTHS,
        "rng_seed": RNG_SEED,
        "selection_meta": sel_meta,
        "n_selected": len(selected),
        "n_ok": len(results),
        "n_dropped": len(dropped),
        "dropped": dropped,
        "runs": results,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    log(f"wrote {OUT_PATH} ({len(results)} ok, {len(dropped)} dropped)")


if __name__ == "__main__":
    main()
