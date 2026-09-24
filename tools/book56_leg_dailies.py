r"""book56_leg_dailies.py -- cached per-leg daily P&L table + exact BOOK parity proof (2026-09-24).

Builds ONE table of per-leg daily dollars, at weight 1, for every DISTINCT leg used by the stored
BOOK runs #397 (FRONTIER), #396 (REF: ORB #234 in the ORB slot) and #372 (FRONTIER PENTA), plus
three new candidate legs (ENGU-Q on ES / run #370, the NQ 15m squeeze break / run #280, and the
live-Webull NOISE leg / run #382). Every leg's daily series comes from
tools.book_dd_attribution.leg_daily -> augur_engine.book._leg_trades -- the SAME code path a BOOK
job runs -- so this is a cache of the runs' own numbers, not a re-specification of them.

Then it proves the cache is faithful: for #397/#396/#372, the book's pre-lockbox and lockbox net /
max-drawdown are rebuilt purely from this leg table (weight x column, summed, scored on its own
cumulative curve per stretch) and diffed against the stored run docs
(C:\EdgeLog\_anatomy_cache\runs\<rid>.json -> book.pre_lockbox / book.lockbox / book.lockbox_from).
A single augur_engine.book.run_book() call on #397 is the third, independent check (re-runs the
whole book from scratch through the production function).

Run from the shared checkout (BACKTEST_SPEED.md rule 3); this script chdir's there itself.
Firestore is read exactly ONCE per book run (a filtered run_id query, not a full collection scan)
and then cached to jobs.json -- re-running this script after that reads zero Firestore documents.

    python book56_leg_dailies.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

OUT_DIR = os.environ.get("EDGELOG_BOOK56_DIR", r"C:\EdgeLog\_anatomy_cache\book56")   # data stays outside git
RUNS_CACHE = r"C:\EdgeLog\_anatomy_cache\runs"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
BOOK_RUNS = [397, 396, 372]
WIN_FROM, WIN_TO = "2010-06-07", "2026-06-30"
LB_FROM = "2025-06-30"

os.makedirs(OUT_DIR, exist_ok=True)


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
    except Exception:
        pass
    return str(o)


# ─────────────────────────────────────────────────────────────────────────────
# 1. load the three book jobs -- ONE Firestore query per run, cached to jobs.json
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_job_from_firestore(run_id):
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter as FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    jobs = list(u.collection("backtests").where(filter=FF("run_id", "==", run_id)).stream())
    assert jobs, "run #%s job document was not found" % run_id
    job = jobs[0].to_dict()
    return job


def load_jobs():
    path = os.path.join(OUT_DIR, "jobs.json")
    cached = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
    jobs, dirty = {}, False
    for rid in BOOK_RUNS:
        key = str(rid)
        if key in cached:
            jobs[rid] = cached[key]
            print("run #%s: loaded from jobs.json cache (0 Firestore reads)" % rid)
            continue
        job = _fetch_job_from_firestore(rid)
        rec = {"run_id": rid, "legs": job.get("legs") or [],
               "date_from": job.get("date_from"), "date_to": job.get("date_to"),
               "lockbox_months": job.get("lockbox_months", 12),
               "strategy": job.get("strategy"), "book_name": job.get("book_name")}
        jobs[rid] = rec
        cached[key] = rec
        dirty = True
        print("run #%s: fetched from Firestore (1 query) -- %d legs, window %s..%s"
              % (rid, len(rec["legs"]), rec["date_from"], rec["date_to"]))
    if dirty:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cached, f, indent=1, default=_json_default)
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# 2. the three new candidate legs (params = the cached run docs' champion, verbatim)
# ─────────────────────────────────────────────────────────────────────────────
def _load_run_json(rid):
    with open(os.path.join(RUNS_CACHE, "%s.json" % rid), encoding="utf-8") as f:
        return json.load(f)


def build_extra_legs(shape_keys):
    """The three task-specified candidates, in the SAME leg-dict shape the stored book legs use."""
    champ370 = dict(_load_run_json(370)["validate"]["champion"])
    champ280 = dict(_load_run_json(280)["validate"]["champion"])
    champ382 = dict(_load_run_json(382)["validate"]["champion"])
    raw = {
        "ENGUQ_ES370": dict(strategy="ENGUQ_1M_ETH_R2_1_0.py", params=champ370, instrument="ES",
                             timeframe="1m", session="eth", source="db_noadj_eth", cost_pts=0.4,
                             mult=50.0, weight=1.0),
        "TTM_NQ15B_280": dict(strategy="TTMSQZ_3_0_NQ15B.py", params=champ280, instrument="NQ",
                               timeframe="15m", session="rth", source="db_noadj_rth", cost_pts=0.533,
                               mult=20.0, weight=1.0),
        "NOISE_CT382": dict(strategy="NOISE_1_8_CT304.py", params=champ382, instrument="NQ",
                             timeframe="5m", session="rth", source="db_noadj_rth", cost_pts=0.533,
                             mult=20.0, weight=1.0),
    }
    # mirror the stored legs' own field shape exactly (extra fields like "master", if the stored
    # legs carry one -- book.py's _leg_trades resolves purely from instrument/timeframe/session/
    # source, so an extra field is metadata only, but we still mirror it for shape parity).
    extra_fields = [k for k in shape_keys if k not in
                    ("strategy", "params", "instrument", "timeframe", "session", "source",
                     "cost_pts", "mult", "weight")]
    if extra_fields:
        print("NOTE: stored legs also carry field(s) %s -- not required for resolution "
              "(book.py resolves the master from instrument/timeframe/session/source only), "
              "left off the 3 new candidates unless a value is knowable." % extra_fields)
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# 3. de-duplication + short readable keys
# ─────────────────────────────────────────────────────────────────────────────
def _normv(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 8)
    return v


def leg_identity(leg):
    """Full definition EXCLUDING weight -- what makes two legs "the same" leg."""
    params = leg.get("params") or {}
    norm_params = tuple(sorted((str(k), _normv(v)) for k, v in params.items()))
    return (str(leg.get("strategy")), norm_params, str(leg.get("instrument")),
            str(leg.get("timeframe")), str(leg.get("session") or ""),
            str(leg.get("source") or ""), _normv(leg.get("cost_pts")), _normv(leg.get("mult")))


def build_champion_index():
    """{strategy_filename: [(run_id, champion_params), ...]} over every locally cached run doc.

    Pure local file reads (C:\\EdgeLog\\_anatomy_cache\\runs\\*.json) -- zero Firestore cost --
    used only to name legs (strategy + which run its params came from); never used for the actual
    P&L, which always comes from the leg dict's own params.
    """
    idx = {}
    for fp in glob.glob(os.path.join(RUNS_CACHE, "*.json")):
        base = os.path.basename(fp)[:-5]
        if not base.isdigit():
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        strat = d.get("strategy")
        champ = (d.get("validate") or {}).get("champion")
        if strat and isinstance(champ, dict):
            idx.setdefault(str(strat), []).append((int(base), champ))
    return idx


def _params_match(a, b, loose=False):
    ak, bk = set(a.keys()), set(b.keys())
    common = ak & bk
    if not loose and ak != bk:
        return False
    if loose and (len(ak ^ bk) > 1 or len(common) < max(1, min(len(ak), len(bk)) - 1)):
        return False
    for k in common:
        av, bv = a[k], b[k]
        if isinstance(av, (int, float)) and not isinstance(av, bool) and \
           isinstance(bv, (int, float)) and not isinstance(bv, bool):
            if abs(float(av) - float(bv)) > 1e-6:
                return False
        elif av != bv:
            return False
    return True


def origin_runs_for(strategy, params, champ_index):
    cands = champ_index.get(strategy, [])
    exact = sorted(rid for rid, champ in cands if _params_match(champ, params, loose=False))
    if exact:
        return exact, "exact"
    loose = sorted(rid for rid, champ in cands if _params_match(champ, params, loose=True))
    if loose:
        return loose, "loose (1 param off)"
    return [], None


_FAMILY = [("ORB", "ORB"), ("ENGUQ", "ENGUQ"), ("ENGU", "ENGUQ"), ("TTMSQZ", "TTM"),
           ("TTM", "TTM"), ("NOISE", "NOISE")]


def prefix_for(strategy):
    stem = strategy[:-3] if strategy.lower().endswith(".py") else strategy
    up = stem.upper()
    for pat, pre in _FAMILY:
        if up.startswith(pat):
            return pre, stem
    return re.sub(r"[^A-Z0-9]", "", up)[:10], stem


def fallback_tag(stem):
    """A short descriptive token from the filename, used only when no origin run resolves."""
    parts = [p for p in re.split(r"[_\-]", stem) if p and not re.fullmatch(r"\d+[A-Za-z]?", p)]
    drop = {"ORB", "ENGUQ", "ENGU", "TTMSQZ", "TTM", "NOISE", "1M", "ETH", "RTH", "PY"}
    parts = [p for p in parts if p.upper() not in drop]
    return parts[-1].upper() if parts else "X"


def assign_keys(order, uniq, champ_index):
    used = set()
    for ident in order:
        info = uniq[ident]
        if info["forced_key"]:
            key = info["forced_key"]
        else:
            leg = info["leg"]
            strategy = str(leg.get("strategy"))
            params = leg.get("params") or {}
            prefix, stem = prefix_for(strategy)
            origin, quality = origin_runs_for(strategy, params, champ_index)
            if origin:
                key = "%s%d" % (prefix, origin[0])
                if len(origin) > 1:
                    print("  NOTE: %s champion params match multiple cached runs %s (%s match) -- "
                          "using the smallest, #%d" % (key, origin, quality, origin[0]))
                elif quality != "exact":
                    print("  NOTE: %s matched run #%d on a LOOSE (1-param-off) comparison"
                          % (key, origin[0]))
            else:
                key = "%s_%s" % (prefix, fallback_tag(stem))
                print("  WARNING: could not identify the origin run for %s (%s %s cost=%s) -- "
                      "no cached run doc's champion matches these params; key '%s' is a "
                      "descriptive placeholder, not a run number"
                      % (strategy, leg.get("instrument"), leg.get("timeframe"),
                         leg.get("cost_pts"), key))
        final, n = key, 2
        while final in used:
            # disambiguate same strategy+origin but a different cost/instrument (e.g. a
            # pre-cost-correction leg) with the differing field instead of a blind counter
            cp = uniq[ident]["leg"].get("cost_pts")
            tagged = "%s_C%d" % (key, int(round(float(cp) * 1000))) if cp is not None else None
            final = tagged if tagged and tagged not in used else "%s_%d" % (key, n)
            n += 1
        used.add(final)
        uniq[ident]["key"] = final
    return uniq


# ─────────────────────────────────────────────────────────────────────────────
# 4. per-leg daily $ series (weight forced to 1.0) + parity
# ─────────────────────────────────────────────────────────────────────────────
def _dd(series):
    if not len(series):
        return 0.0
    c = series.cumsum()
    return float(-(c - c.cummax()).min())


def main():
    t0 = time.time()
    jobs = load_jobs()
    for rid in BOOK_RUNS:
        j = jobs[rid]
        print("  #%s window %s..%s lockbox_months=%s legs=%d"
              % (rid, j["date_from"], j["date_to"], j["lockbox_months"], len(j["legs"])))

    # field shape used by the stored legs, so the 3 new candidates mirror it
    shape_keys = set()
    for rid in BOOK_RUNS:
        for leg in jobs[rid]["legs"]:
            shape_keys |= set(leg.keys())
    extra_legs = build_extra_legs(shape_keys)

    # pool every leg with its provenance (book run id + weight, or a forced candidate key)
    # A few legs' exact origin run cannot be recovered from the LOCAL run-doc cache: the cached
    # run doc's own recorded champion has since drifted from what the book actually carries (a
    # later re-validate of the same crown file overwrote runs/<id>.json's champion field with
    # different numbers -- confirmed 2026-09-24 by an exhaustive local scan: no cached run doc's
    # champion/best_params matches these two legs' params bit for bit), or the file was a
    # PINNED single-config variant under a different filename (ORB's case -- resolved below via
    # a family-wide, not exact-strategy-string, search). These three names are corroborated by
    # repo convention instead (book56_analysis.py's own BASE_KEYS, tools/queue_book_four_leg.py's
    # comments, memory edgelog-book-composition.md / engu-q-project.md): ENGU-Q R2 on NQ = crown
    # #335, the opening-range leg here = run #297's filter set. NOISE_1_2_RYR.py's origin run
    # number is not recorded anywhere locally, so it keeps a descriptive (non-numeric) key.
    # NONE of this affects the P&L: every leg's dollars come from its own params dict, verbatim
    # from the stored book job, never from the label.
    NAME_OVERRIDE = {
        ("ORB_3_6.py", "NQ"): "ORB297",                 # exact champion match, family-wide search
        ("ENGUQ_1M_ETH_R2_1_0.py", "NQ"): "ENGUQ335",   # repo convention; local cache has drifted
    }

    pool = []
    for rid in BOOK_RUNS:
        for leg in jobs[rid]["legs"]:
            forced = NAME_OVERRIDE.get((str(leg.get("strategy")), str(leg.get("instrument"))))
            pool.append((str(rid), leg, forced))
    for key, leg in extra_legs.items():
        pool.append((None, leg, key))

    uniq, order = {}, []
    for src, leg, forced_key in pool:
        ident = leg_identity(leg)
        if ident not in uniq:
            leg1 = dict(leg)
            leg1["weight"] = 1.0
            uniq[ident] = {"leg": leg1, "books": {}, "forced_key": None}
            order.append(ident)
        if src is not None:
            uniq[ident]["books"][src] = float(leg.get("weight", 1) or 1)
        if forced_key:
            uniq[ident]["forced_key"] = forced_key

    print("\n%d unique legs across books %s + 3 candidates (%d raw leg entries)"
          % (len(order), BOOK_RUNS, len(pool)))

    print("\nbuilding champion index from local run-doc cache (no Firestore)...")
    t_idx = time.time()
    champ_index = build_champion_index()
    print("  indexed %d run docs with a recorded champion in %.1fs" % (len(champ_index), time.time() - t_idx))

    uniq = assign_keys(order, uniq, champ_index)

    print("\nUNIQUE LEG MAPPING")
    print("  %-16s %-28s %-5s %-4s %-4s %-14s %-7s  books" % (
        "key", "strategy", "instr", "tf", "sess", "source", "cost"))
    for ident in order:
        info = uniq[ident]
        leg = info["leg"]
        print("  %-16s %-28s %-5s %-4s %-4s %-14s %-7s  %s"
              % (info["key"], leg.get("strategy"), leg.get("instrument"), leg.get("timeframe"),
                 leg.get("session"), leg.get("source"), leg.get("cost_pts"), info["books"]))

    # ── per-leg daily series ────────────────────────────────────────────────
    from book_dd_attribution import leg_daily, score as bda_score

    print("\nBUILDING PER-LEG DAILY SERIES  (%s .. %s, day_mode=book)" % (WIN_FROM, WIN_TO))
    daily_map, legs_out = {}, {}
    t_legs = time.time()
    for ident in order:
        info = uniq[ident]
        key, leg = info["key"], info["leg"]
        t1 = time.time()
        try:
            s, linfo = leg_daily(leg, WIN_FROM, WIN_TO, day_mode="book")
        except Exception as e:
            print("  ERROR %-16s %s: %s: %s  -- SKIPPED (not guessing a different master)"
                  % (key, leg.get("strategy"), type(e).__name__, e))
            daily_map[key] = None
            legs_out[key] = {"leg": leg, "trades": None, "net": None, "books": info["books"],
                             "error": "%s: %s" % (type(e).__name__, e)}
            continue
        dt = time.time() - t1
        net = float(s.sum()) if len(s) else 0.0
        trades = int(linfo.get("trades") or 0)
        daily_map[key] = s
        legs_out[key] = {"leg": leg, "trades": trades, "net": round(net, 2), "books": info["books"]}
        print("  %-16s %7.2fs  %6d trades  $%14s   master=%s"
              % (key, dt, trades, "{:,.0f}".format(net), linfo.get("master")))
    print("all legs built in %.1fs" % (time.time() - t_legs))

    # ── write leg_dailies.csv ───────────────────────────────────────────────
    import pandas as pd
    good = {k: v for k, v in daily_map.items() if v is not None}
    all_idx = sorted(set().union(*[set(s.index) for s in good.values() if len(s)])) if good else []
    df = pd.DataFrame(index=pd.DatetimeIndex(all_idx))
    for key, s in good.items():
        df[key] = s.reindex(df.index).fillna(0.0) if len(df.index) else pd.Series(dtype=float)
    df.index.name = "date"
    df = df.sort_index()
    csv_path = os.path.join(OUT_DIR, "leg_dailies.csv")
    df.to_csv(csv_path, date_format="%Y-%m-%d")
    print("\nwrote %s  (%d rows x %d legs)" % (csv_path, len(df), len(df.columns)))

    legs_json_path = os.path.join(OUT_DIR, "legs.json")
    with open(legs_json_path, "w", encoding="utf-8") as f:
        json.dump(legs_out, f, indent=1, default=_json_default)
    print("wrote %s" % legs_json_path)

    # ── PARITY ──────────────────────────────────────────────────────────────
    parity_lines = []

    def pline(s=""):
        print(s)
        parity_lines.append(s)

    pline("BOOK-56 PARITY CHECK  (fixed lockbox split at %s; stored lockbox_from shown for comparison)" % LB_FROM)
    pline("Parity passes only if every |stored - rebuilt| difference is < $1.\n")

    overall_pass = True
    for rid in BOOK_RUNS:
        job = jobs[rid]
        stored = _load_run_json(rid)["book"]
        cols, weights, missing = [], [], []
        for leg in job["legs"]:
            key = uniq[leg_identity(leg)]["key"]
            if daily_map.get(key) is None:
                missing.append(key)
                continue
            cols.append(key)
            weights.append(float(leg.get("weight", 1) or 1))
        pline("run #%s  (%d legs: %s)" % (rid, len(job["legs"]), ", ".join(cols)))
        if missing:
            pline("  CANNOT rebuild -- leg(s) %s failed to resolve, see errors above" % missing)
            overall_pass = False
            continue

        sub = df[cols].fillna(0.0)
        daily = (sub.values * weights).sum(axis=1)
        daily = pd.Series(daily, index=df.index)

        pre = daily[daily.index < pd.Timestamp(LB_FROM)]
        lb = daily[daily.index >= pd.Timestamp(LB_FROM)]
        pre_net, pre_dd = float(pre.sum()), _dd(pre)
        lb_net, lb_dd = float(lb.sum()), _dd(lb)

        sc = bda_score(daily, lb_from=LB_FROM)
        # internal consistency: score()'s own lockbox split must agree with the manual one
        assert abs(sc["lb"] - lb_net) < 1e-6 and abs(sc["lbdd"] - lb_dd) < 1e-6, \
            "score() lockbox split disagrees with the manual split -- investigate before trusting parity"

        st_pre, st_lb = stored.get("pre_lockbox") or {}, stored.get("lockbox") or {}
        st_lbfrom = stored.get("lockbox_from")
        pline("  stored lockbox_from=%s  (ours=%s)%s"
              % (st_lbfrom, LB_FROM, "" if str(st_lbfrom) == LB_FROM else "  <-- DIFFERS, investigate"))

        rows = [("pre  net  ", st_pre.get("total_pnl"), pre_net),
                ("pre  DD   ", st_pre.get("max_drawdown"), pre_dd),
                ("lock net  ", st_lb.get("total_pnl"), lb_net),
                ("lock DD   ", st_lb.get("max_drawdown"), lb_dd)]
        run_pass = True
        for label, stv, rbv in rows:
            d = abs(float(stv) - rbv) if stv is not None else float("nan")
            ok = d < 1.0
            run_pass &= ok
            pline("    %s  stored %14s   rebuilt %14s   diff %8.4f   %s"
                  % (label, "{:,.2f}".format(stv), "{:,.2f}".format(rbv), d, "OK" if ok else "MISMATCH"))
        pline("    score() cross-check: whole net %s  whole DD %s  |  lockbox MAR %.3f"
              % ("{:,.2f}".format(sc["net"]), "{:,.2f}".format(sc["dd"]), sc["lbmar"]))
        pline("  run #%s PARITY: %s\n" % (rid, "PASS" if run_pass else "FAIL"))
        overall_pass &= run_pass

    # ── run_book() check on #397 ────────────────────────────────────────────
    pline("run_book() end-to-end check on #397 (re-runs the whole book through the production function)")
    from augur_engine.book import run_book
    job397 = jobs[397]
    t_rb = time.time()
    res = run_book(job397["legs"], date_from=job397["date_from"], date_to=job397["date_to"],
                   lockbox_months=int(job397.get("lockbox_months") or 12), slices=8)
    pline("  run_book() took %.1fs" % (time.time() - t_rb))
    bk = res.get("book") or {}
    stored397 = _load_run_json(397)["book"]
    rb_rows = [("pre  net  ", stored397.get("pre_lockbox", {}).get("total_pnl"), (bk.get("pre_lockbox") or {}).get("total_pnl")),
               ("pre  DD   ", stored397.get("pre_lockbox", {}).get("max_drawdown"), (bk.get("pre_lockbox") or {}).get("max_drawdown")),
               ("lock net  ", stored397.get("lockbox", {}).get("total_pnl"), (bk.get("lockbox") or {}).get("total_pnl")),
               ("lock DD   ", stored397.get("lockbox", {}).get("max_drawdown"), (bk.get("lockbox") or {}).get("max_drawdown"))]
    rb_pass = True
    for label, stv, rbv in rb_rows:
        d = abs(float(stv) - float(rbv)) if stv is not None and rbv is not None else float("nan")
        ok = d < 1.0
        rb_pass &= ok
        pline("    %s  stored %14s   run_book %14s   diff %8.4f   %s"
              % (label, "{:,.2f}".format(stv), "{:,.2f}".format(rbv), d, "OK" if ok else "MISMATCH"))
    pline("  run_book() PARITY: %s" % ("PASS" if rb_pass else "FAIL"))
    overall_pass &= rb_pass

    pline("\nOVERALL PARITY: %s" % ("PASS" if overall_pass else "FAIL"))

    parity_path = os.path.join(OUT_DIR, "parity.txt")
    with open(parity_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parity_lines) + "\n")
    print("\nwrote %s" % parity_path)
    print("TOTAL RUNTIME %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
