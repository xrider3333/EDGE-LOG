"""
NOISE TRADE-CONTEXT scan — feature -> per-trade-PnL, FDR corrected (2026-08-18).

Closes the "TRADE CONTEXT feature->PnL FDR scan on NOISE" gap listed in NOISE.md's
"Still genuinely untested" section. Uses the SHIPPED, generic engine
(`augur_engine/context.py`) exactly as the ORB scan did — no bespoke statistics.

What it does
------------
1. Generates NOISE trade logs locally through the parity-proven campaign harness
   (`tools/noise_variant_research.py`), same PINNED source as every other 2026-08-17
   campaign artefact: db_noadj_rth master, NQ 5-minute RTH, cost 0.533 points,
   multiplier 20, window 2010-06-07 -> 2026-08-12.
       * CHAMPION  = run #231 crowned config (lookback 44, band 0.75/1.5, vwap exit,
                     bandwidth stop k=1.75), all filter knobs OFF.
       * SBS       = the same core + daytype_mode='skip_bot_short' (take no SHORT
                     entries the day after a close in the bottom 20% of the prior
                     day's range) — the campaign's load-bearing variant.
2. Builds the standard causal daily feature frame: 8 internal features from the run's
   own bars + 7 external macro features (VIX/VIX3M/TNX/IRX, CSV-cached offline).
   Every one is prior-day shifted by the engine (gap_pct is causal as defined).
3. Adds ONE extra feature, `close_pos` — the prior session's close position inside its
   own high-low range, i.e. the exact quantity the campaign's skip_bot_short filter
   thresholds at 0.2. It is NOT part of the stock library, so without it the scan
   cannot possibly rediscover the known effect. It is scored like any other feature and
   counted in every multiple-testing correction.
4. Scans ALL trades, LONGS only and SHORTS only, for both configs = 6 scans. The
   campaign's finding was strongly one-sided, so a pooled-only scan could wash it out.
5. Reports raw p, the within-scan BH q-value the engine computes, AND a GLOBAL BH
   q-value recomputed across every feature x side x config test in the whole run —
   because six scans of sixteen features is ninety-six tests, not sixteen.
6. For anything that survives, prints effect size (quintile split) and concentration
   (best-year share, top-10-trade share) so a lead can be judged, not just flagged.

Also runs a DIRECT, single-hypothesis, day-clustered permutation test of the known
day-type effect on the champion's short trades. That is the scan's sanity check: a
feature scan that cannot see a $52k effect we already know is real is underpowered,
and that is worth knowing.

Run:
    python tools/noise_context_scan.py                # full report
    python tools/noise_context_scan.py --json out.json
    python tools/noise_context_scan.py --quick        # 200 bootstrap draws (faster)
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

EDGELOG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if EDGELOG_ROOT not in sys.path:
    sys.path.insert(0, EDGELOG_ROOT)

from augur_engine import context as ctx                                  # noqa: E402
from tools import noise_variant_research as nvr                          # noqa: E402

FULL_DATE_TO = nvr.FULL_DATE_TO          # 2026-08-12
COST_PTS = nvr.FEE                       # 0.533
MULT = nvr.MULT                          # 20.0

CONFIGS = {
    "CHAMPION": dict(nvr.CHAMPION),
    "SBS": dict(nvr.CHAMPION, daytype_mode="skip_bot_short"),
}
SIDES = ("all", "long", "short")


# ─────────────────────────────────────────────────────────────────────────────
# the one extra feature: prior-day close position inside its own range
# ─────────────────────────────────────────────────────────────────────────────
def build_close_pos_daily(index, highs, lows, closes):
    """`close_pos` = (close - low) / (high - low) of the PRIOR calendar trading day,
    i.e. where the session finished inside its own range (0 = on the low, 1 = on the
    high). Shifted +1 day so a trade entering on day D only ever sees day D-1 — the
    same causality the rest of the feature library obeys, and the same quantity the
    campaign's skip_bot_short filter compares against 0.2.
    """
    eix = pd.to_datetime(pd.Series(index))
    dts = eix.dt.date.values
    H = np.asarray(highs, float); L = np.asarray(lows, float); C = np.asarray(closes, float)
    n = min(len(dts), len(H), len(L), len(C))
    df = pd.DataFrame({"d": dts[:n], "h": H[:n], "l": L[:n], "c": C[:n]})
    day = df.groupby("d", sort=True).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    rng = (day["h"] - day["l"]).replace(0.0, np.nan)
    pos = (day["c"] - day["l"]) / rng
    return pd.DataFrame({"close_pos": pos.shift(1)})


def build_daily_features(arr, external=True):
    idx = arr["index"]
    daily = ctx.build_internal_daily(idx, arr["open"], arr["high"], arr["low"], arr["close"])
    if external:
        eix = pd.to_datetime(pd.Series(idx))
        ext = ctx.fetch_external_daily(str(eix.min().date()), str(eix.max().date()))
        if ext is not None and len(ext):
            daily = daily.join(ext, how="left")
    daily = daily.join(build_close_pos_daily(idx, arr["high"], arr["low"], arr["close"]),
                       how="left")
    return daily


# ─────────────────────────────────────────────────────────────────────────────
# trades -> the (entry_i, exit_i, net_usd_pnl, side, entry_px) shape context wants
# ─────────────────────────────────────────────────────────────────────────────
def net_trades_for(trades, side="all"):
    out = []
    for (eb, xb, pnl, pos, epx) in trades:
        if side == "long" and pos <= 0:
            continue
        if side == "short" and pos >= 0:
            continue
        out.append((eb, xb, (float(pnl) - COST_PTS) * MULT, pos, epx))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# effect size + concentration for a lead
# ─────────────────────────────────────────────────────────────────────────────
def describe_feature(trades, index, daily, feat):
    """Quintile split + concentration for one feature over one trade list."""
    dts = pd.to_datetime(pd.Series(index)).dt.date.values
    rows = []
    for (eb, xb, pnl, pos, epx) in trades:
        d = dts[int(eb)]
        if d not in daily.index:
            continue
        v = daily.at[d, feat]
        if pd.isna(v):
            continue
        rows.append((d, float(v), float(pnl)))
    if len(rows) < ctx.MIN_TRADES:
        return None
    df = pd.DataFrame(rows, columns=["date", "x", "pnl"])
    try:
        df["q5"] = pd.qcut(df["x"], 5, labels=False, duplicates="drop")
    except Exception:
        return None
    g = df.groupby("q5")["pnl"].agg(["count", "mean", "sum"])
    lo = int(df["q5"].min()); hi = int(df["q5"].max())
    df["year"] = [d.year for d in df["date"]]
    bot = df[df["q5"] == lo]
    byyear = bot.groupby("year")["pnl"].sum()
    best_year = byyear.idxmin() if len(byyear) else None       # most negative = biggest avoid
    worst10 = bot.nsmallest(10, "pnl")["pnl"].sum() if len(bot) >= 10 else float("nan")
    return {
        "quintiles": [{"bin": int(b), "n": int(r["count"]), "mean": round(float(r["mean"]), 2),
                       "sum": round(float(r["sum"]), 2)} for b, r in g.iterrows()],
        "bottom_bin_n": int(len(bot)),
        "bottom_bin_sum": round(float(bot["pnl"].sum()), 2),
        "bottom_bin_mean": round(float(bot["pnl"].mean()), 2),
        "bottom_bin_worst_year": (int(best_year) if best_year is not None else None),
        "bottom_bin_worst_year_sum": (round(float(byyear.min()), 2) if len(byyear) else None),
        "bottom_bin_top10_sum": (round(float(worst10), 2) if worst10 == worst10 else None),
        "top_bin_n": int((df["q5"] == hi).sum()),
        "top_bin_sum": round(float(df[df["q5"] == hi]["pnl"].sum()), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# the direct, single-hypothesis sanity test (day-clustered permutation)
# ─────────────────────────────────────────────────────────────────────────────
def daytype_direct_test(trades, index, daily, lo=0.2, n_perm=5000, seed=42):
    """`trades` must already be COST-NETTED and in USD (see net_trades_for).

    One pre-specified hypothesis, tested once: are SHORT trades entered the day
    after a bottom-20%-of-range close worse than the strategy's other shorts?
    Statistic = total PnL of the flagged shorts. Null = the bottom-20% DAY LABELS are
    reshuffled across trading days (whole days move together, so trades sharing a day
    stay together), which is the same day-clustering discipline the scan uses.
    """
    dts = pd.to_datetime(pd.Series(index)).dt.date.values
    rows = []
    for (eb, xb, pnl, pos, epx) in trades:
        if pos >= 0:
            continue
        d = dts[int(eb)]
        if d not in daily.index:
            continue
        v = daily.at[d, "close_pos"]
        if pd.isna(v):
            continue
        rows.append((d, float(v), float(pnl)))
    if len(rows) < ctx.MIN_TRADES:
        return None
    df = pd.DataFrame(rows, columns=["date", "x", "pnl"])
    day = df.groupby("date").agg(flag=("x", lambda s: bool(s.iloc[0] <= lo)),
                                 pnl=("pnl", "sum"), n=("pnl", "size"))
    flag = day["flag"].to_numpy()
    pnl = day["pnl"].to_numpy(float)
    obs = float(pnl[flag].sum())
    n_flag = int(flag.sum())
    rng = np.random.default_rng(int(seed))
    nD = len(day)
    hits = 0
    for _ in range(int(n_perm)):
        pick = rng.choice(nD, size=n_flag, replace=False)
        if pnl[pick].sum() <= obs:
            hits += 1
    return {
        "n_short_trades": int(len(df)),
        "n_days": int(nD),
        "n_flagged_days": n_flag,
        "n_flagged_trades": int(df[df["x"] <= lo].shape[0]),
        "flagged_total_pnl": round(obs, 2),
        "flagged_mean_pnl": round(float(df[df["x"] <= lo]["pnl"].mean()), 2),
        "other_mean_pnl": round(float(df[df["x"] > lo]["pnl"].mean()), 2),
        "perm_p_one_sided": round((hits + 1) / (int(n_perm) + 1), 5),
        "n_perm": int(n_perm),
    }


def gap_overlap_audit(arr, trades, daily, thresholds=(-0.5, -0.25, 0.0), vol_pct_hi=90.0):
    """Is the gap-down effect on LONG trades anything NEW, or is it the volatility
    effect the 2026-08-17 campaign already banked as `vol_skip 90`?

    For each gap threshold: the long trades entered on a day that gapped down at
    least that far, split into the ones the banked `vol_skip 90` filter would ALREADY
    have removed (prior session's range percentile >= 90) and the residual it would
    not. `trades` must already be cost-netted USD (see net_trades_for).
    """
    did = np.asarray(arr["day_id"])
    sb = nvr._session_bounds(did, len(did))
    vp = nvr._vol_percentile(arr["high"], arr["low"], arr["close"], sb)
    dts = pd.to_datetime(pd.Series(arr["index"])).dt.date.values
    sess_of_date = {dts[a]: si for si, (a, b) in enumerate(sb)}
    rows = []
    for (eb, xb, pnl, pos, epx) in trades:
        if pos <= 0:
            continue
        d = dts[int(eb)]
        g = daily.at[d, "gap_pct"] if d in daily.index else np.nan
        if pd.isna(g):
            continue
        rows.append((d, float(g), float(vp[sess_of_date[d]]), float(pnl)))
    df = pd.DataFrame(rows, columns=["d", "gap", "volpct", "pnl"])
    out = []
    for thr in thresholds:
        s = df[df["gap"] <= thr]
        if not len(s):
            continue
        caught = s[s["volpct"] >= vol_pct_hi]
        resid = s[~(s["volpct"] >= vol_pct_hi)]
        by = resid.groupby([d.year for d in resid["d"]])["pnl"].sum()
        out.append({
            "gap_threshold_pct": thr,
            "n": int(len(s)), "sum": round(float(s["pnl"].sum()), 2),
            "already_removed_by_vol_skip90_n": int(len(caught)),
            "already_removed_by_vol_skip90_sum": round(float(caught["pnl"].sum()), 2),
            "residual_n": int(len(resid)),
            "residual_sum": round(float(resid["pnl"].sum()), 2),
            "residual_worst_year": (int(by.idxmin()) if len(by) else None),
            "residual_worst_year_sum": (round(float(by.min()), 2) if len(by) else None),
            "residual_years_neg_pos": [int((by < 0).sum()), int((by > 0).sum())],
            "residual_10_worst_sum": (round(float(resid.nsmallest(10, "pnl")["pnl"].sum()), 2)
                                      if len(resid) >= 10 else None),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="write the full result blob here")
    ap.add_argument("--quick", action="store_true", help="200 bootstrap draws instead of 500")
    ap.add_argument("--no-external", action="store_true", help="internal features only")
    args = ap.parse_args()
    n_boot = 200 if args.quick else ctx.DEFAULT_BLOCK_N_BOOT

    arr = nvr.load_arrays(FULL_DATE_TO)
    index = arr["index"]
    print("SOURCE: db_noadj_rth NQ 5m RTH | %s -> %s | cost %.3f pts | mult %.0f"
          % (str(pd.Timestamp(index[0]).date()), str(pd.Timestamp(index[-1]).date()),
             COST_PTS, MULT))

    daily = build_daily_features(arr, external=not args.no_external)
    feat_names = list(daily.columns)
    print("FEATURES (%d): %s\n" % (len(feat_names), ", ".join(feat_names)))

    blob = {"source": "db_noadj_rth NQ 5m RTH",
            "window": [str(pd.Timestamp(index[0]).date()), str(pd.Timestamp(index[-1]).date())],
            "cost_pts": COST_PTS, "mult": MULT, "n_boot": n_boot,
            "features": feat_names, "scans": {}, "direct_test": {}}

    all_tests = []          # (scan_key, feature, p) for the GLOBAL BH correction
    trade_cache = {}

    for cfg_name, params in CONFIGS.items():
        trades = nvr.run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                                 arr.get("volume"), arr["day_id"], **params)
        trade_cache[cfg_name] = trades
        for side in SIDES:
            nt = net_trades_for(trades, side)
            key = "%s/%s" % (cfg_name, side)
            res = ctx.context_scores(nt, index, daily, n_boot=n_boot, seed=42)
            if res is None:
                print("[%s] too few trades to score (%d)" % (key, len(nt)))
                blob["scans"][key] = None
                continue
            blob["scans"][key] = res
            print("=" * 100)
            print("SCAN %-18s trades=%-6d days=%-5d probe floor |rho|=%.4f  external=%s"
                  % (key, res["n_trades"], res["n_days"], res["probe_max_abs_rho"],
                     res["external_available"]))
            print("%-16s %8s %8s %8s %8s %7s %6s %7s %6s %6s %6s"
                  % ("feature", "rho", "p", "q(scan)", "ci_lo", "ci_hi", "slow",
                     "era_t", "probe", "surv", "n"))
            for f in res["features"]:
                all_tests.append((key, f["name"], f["p"]))
                print("%-16s %8.4f %8.4f %8.4f %8.4f %7.4f %6s %7.2f %6s %6s %6d"
                      % (f["name"], f["rho"], f["p"], f["q"], f["ci_lo"], f["ci_hi"],
                         "Y" if f["slow"] else "-", f["era_t"],
                         "Y" if f["beats_probe"] else "-",
                         "YES" if f["survives"] else "-", f["n"]))
            surv = [f["name"] for f in res["features"] if f["survives"]]
            print("  scored %d features | survivors (scan-level FDR+CI+era+probe): %s"
                  % (len(res["features"]), ", ".join(surv) if surv else "NONE"))
            print()

    # ── GLOBAL Benjamini-Hochberg across EVERY test in the whole run ──────────
    if all_tests:
        pv = np.array([t[2] for t in all_tests], float)
        gq = ctx._bh_fdr(pv)
        glob = {}
        for (key, name, p), q in zip(all_tests, gq):
            glob.setdefault(key, {})[name] = round(float(q), 4)
        blob["global_bh"] = {"n_tests": int(len(all_tests)), "q": glob}
        print("=" * 100)
        print("GLOBAL Benjamini-Hochberg across ALL %d tests (%d features x %d scans)"
              % (len(all_tests), len(feat_names), len(CONFIGS) * len(SIDES)))
        surv_any = []
        for key, res in blob["scans"].items():
            if not res:
                continue
            for f in res["features"]:
                gqv = glob[key][f["name"]]
                if f["survives"] or gqv < ctx.FDR_Q or f["p"] < 0.05:
                    surv_any.append((key, f["name"], f["rho"], f["p"], f["q"], gqv,
                                     f["survives"]))
        print("%-18s %-16s %8s %8s %9s %10s %6s"
              % ("scan", "feature", "rho", "p(raw)", "q(scan)", "q(global)", "surv"))
        for row in sorted(surv_any, key=lambda r: r[3]):
            print("%-18s %-16s %8.4f %8.4f %9.4f %10.4f %6s"
                  % (row[0], row[1], row[2], row[3], row[4], row[5],
                     "YES" if row[6] else "-"))
        if not surv_any:
            print("  (nothing at raw p<0.05 anywhere)")
        print()

        # effect size / concentration for anything that survived its own scan
        for key, res in blob["scans"].items():
            if not res:
                continue
            cfg_name, side = key.split("/")
            for f in res["features"]:
                if not f["survives"]:
                    continue
                d = describe_feature(net_trades_for(trade_cache[cfg_name], side),
                                     index, daily, f["name"])
                blob.setdefault("effect_size", {}).setdefault(key, {})[f["name"]] = d
                print("EFFECT SIZE  %s / %s" % (key, f["name"]))
                print("   " + json.dumps(d))
                print()

    # ── direct single-hypothesis sanity check ────────────────────────────────
    print("=" * 100)
    print("SANITY CHECK — direct, pre-specified, day-clustered permutation test of the")
    print("known day-type effect (shorts after a bottom-20%-of-range close), champion trades")
    dt = daytype_direct_test(net_trades_for(trade_cache["CHAMPION"], "all"), index, daily)
    blob["direct_test"]["CHAMPION_short"] = dt
    print("   " + json.dumps(dt))

    print()
    print("=" * 100)
    print("OVERLAP AUDIT — is the gap-down effect on LONG trades new, or is it the")
    print("volatility effect already banked as vol_skip 90? (champion trades)")
    ov = gap_overlap_audit(arr, net_trades_for(trade_cache["CHAMPION"], "all"), daily)
    blob["gap_overlap_audit"] = ov
    for row in ov:
        print("   " + json.dumps(row))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, indent=1, default=str)
        print("\nwrote %s" % args.json)


if __name__ == "__main__":
    main()
