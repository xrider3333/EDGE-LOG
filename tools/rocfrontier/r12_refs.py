# MDL r1 (2026-10-04) - the REFERENCE LEGS the map places as points (PREREG_MDL_R1.txt, OUTPUTS: "reference points ... reported,
# never judged"). Builds one daily P&L series per leg and writes them to OUT/refs as CSV (date, pnl):
#   * paper legs, defined exactly as api/paper.py's PAPER_LEGS runs them (same strategy file, params, cost and multiplier, and the same
#     DEFAULT master - the paper system calls find_master without a source pin), run through the engine's own leg runner over #463's
#     window and valued daily on the engine's day stamps (rule U, r11_risk.trade_records - the same construction as #463's records);
#     each series is checked against the engine's own daily-valued series to the cent (the P1 check of r11_risk).
#   * seat SWAPS are reference legs only as DIFFERENCE series (the shadow book = #463 with one leg swapped): ORB #239 / #257 minus the
#     paper ORB #234 control; ENGU-Q S1 / S2 minus the paper ENGU-Q #335 control - both sides on the same default master.
#   * NQBRD theta 0.70 (dead at Stage A, lockbox SEALED): walk-forward days only, rebuilt from r5_nqbrd's own functions with the
#     cut at 2025-06-30 applied before anything is computed - its sealed year is never read here.
#   python r12_refs.py build
# Results go to OUT/refs (outside git). Nothing here commits, pushes, queues a job or downloads anything.
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r11_risk as R11                                       # puts the shared checkout (REPO) on sys.path
import numpy as np, pandas as pd

OUT = os.environ.get("EDGELOG_ROCFRONTIER_MDL", r"C:\EdgeLog\_anatomy_cache\rocfrontier\mdl_r1")
REFS = os.path.join(OUT, "refs")
PAPER_KEYS = ["DIP_ES_452", "DIP_NQ_433", "ORB", "ORB_239", "ORB_257", "ENGUQ_335", "ENGUQ_335_S1", "ENGUQ_335_S2"]
DIFFS = {"ORB_239_swap": ("ORB_239", "ORB"), "ORB_257_swap": ("ORB_257", "ORB"),
         "ENGUQ_S1_swap": ("ENGUQ_335_S1", "ENGUQ_335"), "ENGUQ_S2_swap": ("ENGUQ_335_S2", "ENGUQ_335")}
ADDS = ["DIP_ES_452", "DIP_NQ_433"]                          # new legs (not in #463): the leg itself is the reference


def book_leg(pl):
    """a PAPER_LEGS entry -> the engine's book-leg dict; no source pin (the paper system loads the default master)"""
    leg = {"strategy": pl["strategy"], "instrument": pl["instrument"], "timeframe": pl.get("timeframe", "5m"),
           "session": pl.get("session") or "rth", "cost_pts": float(pl.get("cost_pts") or 0.0), "mult": float(pl.get("mult") or 1.0),
           "weight": 1, "params": dict(pl.get("params") or {})}
    if pl.get("gate"):
        leg["gate"] = pl["gate"]
    return leg


def leg_daily(leg):
    from augur_engine import book as BK
    tr, info = BK._leg_trades(dict(leg), R11.W0, R11.W1, keep_state=True)
    st = info.pop("_state")
    mtm = info.pop("_mtm_day")
    info.pop("_session_day", None)
    r = R11.trade_records(st, st["days_idx"])                 # rule U: the engine's own day stamps
    s = R11.by_day(r["inc_d"], r["inc_v"])
    ok, dmax = R11.series_equal(s, R11.by_day([d for d, _ in mtm], [v for _, v in mtm]))
    okc, dc = R11.series_equal(R11.by_day(r["exit"], r["closed"]), R11.by_day([d for d, _ in tr], [v for _, v in tr]))
    meta = {"trades": int(len(r["closed"])), "closed_net": float(r["closed"].sum()), "mtm_check": ok, "mtm_maxdiff": dmax,
            "closed_check": okc, "closed_maxdiff": dc, "master": info.get("master"), "source": info.get("source"),
            "first": str(s.index.min().date()) if len(s) else None, "last": str(s.index.max().date()) if len(s) else None}
    return s, meta


def nqbrd_wf(theta=0.70):
    """NQBRD's walk-forward trades only; the cut at LB0 is applied by r5_nqbrd itself before anything is computed"""
    import r5_nqbrd as N
    nq = N.nq_days(N.WF0, N.LB0)
    br, _ = N.breadth(N.LB0)
    br = br.reindex(nq.index)
    sign = pd.Series(N.side(br.B, theta), index=nq.index)
    tr = N.trades(nq, sign)
    tr = tr[(tr["date"] >= N.WF0) & (tr["date"] < N.LB0)]
    assert not (tr["date"] >= pd.Timestamp("2025-06-30")).any(), "NQBRD's sealed year must not be read"
    s = tr.groupby("date")["pnl"].sum()
    s.index = pd.to_datetime(s.index)
    return s, {"trades": int(len(tr)), "net": float(tr["pnl"].sum()), "stretch": "WF only (lockbox sealed)"}


def save(name, s):
    os.makedirs(REFS, exist_ok=True)
    pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in s.index], "pnl": s.to_numpy(float)}).to_csv(os.path.join(REFS, name + ".csv"), index=False)


def build():
    from api import paper as P
    legs = {pl["key"]: pl for pl in P.PAPER_LEGS if pl.get("key") in PAPER_KEYS}
    missing = [k for k in PAPER_KEYS if k not in legs]
    if missing:
        raise SystemExit(f"refused: PAPER_LEGS has no {missing}")
    series, meta = {}, {}
    for k in PAPER_KEYS:
        s, m = leg_daily(book_leg(legs[k]))
        series[k], meta[k] = s, m
        print(f"{k}: {m['trades']} trades, closed net ${m['closed_net']:,.0f}, daily check {m['mtm_check'] and m['closed_check']}, master {m['master']}", flush=True)
        if not (m["mtm_check"] and m["closed_check"]):
            raise SystemExit(f"refused: {k}'s daily records do not re-sum to the engine's own series (max diff {m['mtm_maxdiff']:.2f})")
    out = {}
    for k in ADDS:
        out[k] = series[k]
    for name, (a, b) in DIFFS.items():
        ix = series[a].index.union(series[b].index)
        out[name] = series[a].reindex(ix).fillna(0.0) - series[b].reindex(ix).fillna(0.0)
        meta[name] = {"difference": f"{a} - {b}", "net": float(out[name].sum())}
    s, m = nqbrd_wf(0.70)
    out["NQBRD_070"], meta["NQBRD_070"] = s, m
    for name, s in out.items():
        save(name, s)
    for k in PAPER_KEYS:                                       # the raw legs too, for anyone re-checking a difference
        save("leg_" + k, series[k])
    with open(os.path.join(REFS, "refs_meta.json"), "w") as f:
        json.dump({"built": pd.Timestamp.now().isoformat(), "window": [R11.W0, R11.W1], "references": sorted(out), "meta": meta}, f, indent=1)
    print("refs written:", ", ".join(sorted(out)), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        print(__doc__ or "usage: python r12_refs.py build")
