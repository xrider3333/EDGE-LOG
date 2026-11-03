r"""w93 LOSER ANATOMY, NOISE #382 (MANAGER #162, scope SCOPE_RESEARCH_LOOP_2026-11-03 E8 feed) - DISCOVERY HALF ONLY.

Which condition, KNOWN AT THE ENTRY BAR, marks #382's losing trades? Read on the #382 WF chain (the t74 rebuild,
C:\EdgeLog\_anatomy_cache\t74_giveback\chain_382_mfe.csv, 2,345 trades) - but ONLY folds 1-4 (2016-2020, 1,207 trades).
Folds 5-8 (1,138 trades) are NEVER READ here: the script drops them before any feature is computed, so the one condition
picked from this table can be pre-registered and then tested on folds 5-8 as a clean holdout inside the chain. The lockbox
is past the chain's end (2025-07-15) and is never loaded (bars stop at the optimize end).

Features, all from bars up to and including the entry bar's close and from completed prior sessions:
  tod       entry time bucket (open 09:30-10:30 / mid 10:30-14:00 / late 14:00-16:00)
  gap       |RTH open - prior RTH close| / ATR14 of prior daily ranges (tercile)
  gap_side  trade with the gap (+1) or against it (-1)
  prior_rng prior RTH high-low / ATR14 (tercile)
  vixy_chg  prior session VIXY close-to-close % (tercile) - VIX proxy (VIXY daily, Alpaca, from 2011)
  esnq_div  NQ minus ES return since today's RTH open, at the entry bar, x trade side (tercile; + = NQ led in the trade's way)
  dow       day of week
  fomc      FOMC decision day (tools/data/fomc_dates.txt via augur_engine.ml_keel)
  vwap_dist |entry - session VWAP| / ATR14 (tercile)
  prev_loss previous chain trade closed net < 0
Each feature row: trades, loser share, mean net pts, net $ in the bucket - beside the all-trades base rate. Python computes.

    python tools/noise_w93_loser_anatomy.py   -> C:\EdgeLog\_anatomy_cache\w93_loser\anatomy_folds1to4.csv + .json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

CHAIN = r"C:\EdgeLog\_anatomy_cache\t74_giveback\chain_382_mfe.csv"
RUN = r"C:\EdgeLog\_anatomy_cache\t74_giveback\run382.json"
VIXY = r"C:\EdgeLog\alpaca_cache\etf_daily\VIXY_1Day_split.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\w93_loser"
DISCOVERY_FOLDS = {1, 2, 3, 4}
COST, MULT = 0.533, 20.0


def bars(instr, src, d0, d1):
    m = find_master(instr, "5m", "rth", src)
    A = load_master_arrays(m, date_from=d0, date_to=d1)
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    return pd.DataFrame({"o": A["open"], "h": A["high"], "l": A["low"], "c": A["close"],
                         "v": A.get("volume", np.ones(len(idx)))}, index=idx)


def daily(b):
    g = b.groupby(b.index.normalize())
    d = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last()})
    tr = pd.concat([d.h - d.l, (d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()], axis=1).max(axis=1)
    d["atr_prior"] = tr.rolling(14).mean().shift(1)          # known before today's open
    d["prev_c"], d["prev_rng"] = d.c.shift(1), (d.h - d.l).shift(1)
    return d


def tercile(s, ref):
    q = ref.quantile([1 / 3, 2 / 3]).values
    return pd.cut(s, [-np.inf, q[0], q[1], np.inf], labels=["low", "mid", "high"])


def main():
    run = json.load(open(RUN))
    end = run["validate"]["windows"]["optimize"][1]           # chain end; the lockbox lies after it, never loaded
    ch = pd.read_csv(CHAIN)
    ch = ch[ch.fold.isin(DISCOVERY_FOLDS)].copy()            # folds 5-8 dropped BEFORE any feature: the holdout
    nq = bars("NQ", run["data_source"], run["date_from"], end)
    es = bars("ES", run["data_source"], run["date_from"], end)
    if nq.index[-1].normalize() > pd.Timestamp(end):
        raise SystemExit("REFUSED - bars past the optimize end %s (lockbox)" % end)
    dn = daily(nq)
    t = nq.index[ch.e.values]
    ch["ts"], ch["day"] = t, t.normalize()
    ch["net"] = ch["size"] * (ch["raw"] - COST)
    ch["loser"] = ch.net < 0
    D = dn.reindex(ch.day)
    atr = D.atr_prior.values
    h = t.hour + t.minute / 60.0
    ch["tod"] = np.where(h < 10.5, "open", np.where(h < 14, "mid", "late"))
    gap = (D.o.values - D.prev_c.values)
    ch["gap_abs"] = np.abs(gap) / atr
    ch["gap_side"] = np.where(np.sign(gap) * ch.side > 0, "with", "against")
    ch["prior_rng"] = D.prev_rng.values / atr
    # session VWAP to the entry bar (typical price x volume)
    tp = (nq.h + nq.l + nq.c) / 3
    pv = (tp * nq.v).groupby(nq.index.normalize()).cumsum()
    vv = nq.v.groupby(nq.index.normalize()).cumsum()
    vwap = (pv / vv.replace(0, np.nan)).values
    ch["vwap_dist"] = np.abs(ch.entry.values - vwap[ch.e.values]) / atr
    # ES/NQ divergence since today's open, at the entry bar's close
    nq_open = nq.o.groupby(nq.index.normalize()).transform("first")
    es_open = es.o.groupby(es.index.normalize()).transform("first")
    r_nq = (nq.c / nq_open - 1).reindex(t).values
    r_es = (es.c / es_open - 1).reindex(t).values
    ch["esnq_div"] = (r_nq - r_es) * ch.side.values
    vx = pd.read_csv(VIXY)
    tcol = [c for c in vx.columns if c.lower() in ("timestamp", "date", "t", "time")][0]
    vx.index = pd.to_datetime(vx[tcol], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    ccol = [c for c in vx.columns if c.lower() in ("close", "c")][0]
    vchg = vx[ccol].pct_change().shift(1)                     # the PRIOR session's change: known at today's open
    ch["vixy_chg"] = vchg.reindex(ch.day).values
    ch["dow"] = t.day_name().str[:3]
    from augur_engine.ml_keel import fomc_decision_days
    fd = {pd.Timestamp(x).normalize() for x in fomc_decision_days()}
    ch["fomc"] = np.where(ch.day.isin(fd), "fomc", "other")
    ch = ch.sort_values("e")
    ch["prev_loss"] = np.where(ch.net.shift(1) < 0, "after_loss", "after_win")
    cuts = {}
    for col in ("gap_abs", "prior_rng", "vwap_dist", "esnq_div", "vixy_chg"):
        ch[col + "_t"] = tercile(ch[col], ch[col].dropna())
        cuts[col] = [float(x) for x in ch[col].dropna().quantile([1 / 3, 2 / 3]).values]   # FIXED from folds 1-4
    base = dict(trades=len(ch), loser=round(ch.loser.mean(), 3), mean_pts=round(ch.net.mean(), 2),
                net_usd=round(ch.net.sum() * MULT))
    rows = []
    for f in ("tod", "gap_abs_t", "gap_side", "prior_rng_t", "vixy_chg_t", "esnq_div_t", "dow", "fomc", "vwap_dist_t",
              "prev_loss"):
        for k, g in ch.groupby(f, observed=True):
            se = g.net.std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan
            rows.append(dict(feature=f, bucket=str(k), trades=len(g), loser=round(g.loser.mean(), 3),
                             mean_pts=round(g.net.mean(), 2), t_vs_zero=round(g.net.mean() / se, 2) if se else None,
                             net_usd=round(g.net.sum() * MULT), folds_neg=int((g.groupby("fold").net.sum() < 0).sum())))
    df = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, "anatomy_folds1to4.csv"), index=False)
    json.dump({"base": base, "folds_read": sorted(DISCOVERY_FOLDS), "holdout_folds_unread": [5, 6, 7, 8],
               "chain_end": end, "tercile_cuts": cuts, "rows": rows}, open(os.path.join(OUT, "anatomy_folds1to4.json"), "w"), indent=1,
              default=str)
    print("BASE", base)
    print("CUTS", cuts)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
