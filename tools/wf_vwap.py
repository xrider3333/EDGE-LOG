"""
wf_vwap.py  --  Anchored walk-forward for VWAP_FADE_1 + VWAP_FADE_2
                on 16-year ES/NQ 5m RTH Databento masters.

Key research question:
  Is Long-Only VWAP-dip a real edge, or just 2025 bull-beta?
  Does VWAP_FADE_2's regime gate earn the short side in down years?

Walk-forward design:
  * Anchored: IS window GROWS each fold; OOS window is fixed (equal slices).
  * 40% of total bars -> first-fold IS; remaining 60% split into 6 OOS folds.
  * 200 random trials per fold (seed = 42 + fold_index) drawn from the sweep grid.
  * IS champion = best profit_factor among trials passing gates:
      PF in (1.0, 6.0],  wins >= MIN_T,  losses >= MIN_T,
      trade_rate <= MAX_RATE  (trades per bar).
  * Per-fold champion evaluated on OOS. OOS $ shown at 1 contract (ES*50, NQ*20).
  * Per-YEAR OOS breakdown printed at the end.

Run:  python tools/wf_vwap.py
"""
import os, sys, random, time, json, datetime
import numpy as np
import pandas as pd
import importlib.util

HERE     = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(HERE)
STRATS   = os.path.join(ROOT, "augur_strategies")
UPLOADS  = os.path.join(ROOT, "augur_uploads")
RESEARCH = os.path.join(ROOT, "augur_research")

# WF hyper-params
N_TRIALS   = 200
N_FOLDS    = 6
INIT_FRAC  = 0.40       # first-fold IS fraction
MIN_T      = 5          # minimum wins AND losses in IS
MAX_RATE   = 0.015      # max trades-per-bar in IS
BASE_SEED  = 42

# Instruments
INSTRUMENTS = {
    "ES": {"master": "master_a85a0438.csv", "mult": 50},
    "NQ": {"master": "master_00c66966.csv", "mult": 20},
}

# Parameter grids
GRID_V1 = {
    "band_mult":    [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5],
    "stop_mult":    [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    "warmup_bars":  [0, 3, 6, 12],
    "max_hold":     [0, 12, 24],
    "trade_mode":   ["Long Only", "Both"],
    "bias_mode":    ["off"],
    "cooldown_bars":[0, 4],
    "flat_eod":     [True],
}

GRID_V2 = {
    "band_mult":    [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5],
    "stop_mult":    [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    "warmup_bars":  [0, 3, 6, 12],
    "max_hold":     [0, 12, 24],
    "trade_mode":   ["Long Only", "Both"],
    "cooldown_bars":[0, 4],
    "flat_eod":     [True],
    "regime_mode":  ["off", "with_trend", "against_trend"],
    "regime_len":   [20, 50, 100, 200],
}


def _load_strategy(name):
    path = os.path.join(STRATS, name + ".py")
    spec = importlib.util.spec_from_file_location("_strat", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_master(inst):
    path = os.path.join(UPLOADS, INSTRUMENTS[inst]["master"])
    df   = pd.read_csv(path)
    dt   = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["dt"]      = dt
    df["year"]    = dt.dt.year
    df["datekey"] = dt.dt.date.astype(str)
    uniq          = {d: i for i, d in enumerate(df["datekey"].unique())}
    df["day_id"]  = df["datekey"].map(uniq).astype(int)
    df            = df.sort_values("time").reset_index(drop=True)
    print("  [%s] %d bars  %s -> %s  (%d years)" % (
        inst, len(df),
        df["dt"].iloc[0].date(), df["dt"].iloc[-1].date(),
        df["year"].nunique()))
    return df


def _sample_params(grid, rng):
    return {k: rng.choice(v) for k, v in grid.items()}


def _run(mod, df_slice, params, return_trades=False):
    opens  = df_slice["open"].values
    highs  = df_slice["high"].values
    lows   = df_slice["low"].values
    closes = df_slice["close"].values
    vols   = df_slice["volume"].values
    did    = df_slice["day_id"].values
    return mod.run_backtest(opens, highs, lows, closes,
                            volumes=vols, day_id=did, **params,
                            return_trades=return_trades)


def _is_valid(r, n_bars):
    if r is None:
        return False
    if r["wins"] < MIN_T or r["losses"] < MIN_T:
        return False
    rate = r["num_trades"] / max(n_bars, 1)
    if rate > MAX_RATE:
        return False
    pf = r["profit_factor"]
    if not (1.0 < pf <= 6.0):
        return False
    return True


def run_wf(mod, df, grid, label, mult):
    n        = len(df)
    init_n   = int(n * INIT_FRAC)
    remain_n = n - init_n
    fold_n   = remain_n // N_FOLDS

    print()
    print("-" * 62)
    print("  %s" % label)
    print("  n=%d  init=%d  fold=%d  folds=%d  trials=%d" % (
        n, init_n, fold_n, N_FOLDS, N_TRIALS))
    print("-" * 62)

    oos_pnl_total    = 0.0
    oos_trades_total = 0
    folds_held       = 0
    per_year_pnl     = {}
    fold_rows        = []

    for fi in range(N_FOLDS):
        is_end  = init_n + fi * fold_n
        oos_end = min(is_end + fold_n, n)
        if is_end >= n:
            break

        is_df  = df.iloc[:is_end]
        oos_df = df.iloc[is_end:oos_end]
        is_n   = len(is_df)
        oos_n  = len(oos_df)
        if is_n < 100 or oos_n < 20:
            continue

        rng    = random.Random(BASE_SEED + fi)
        best_r = None
        best_p = None
        best_s = -1e18

        t_fold = time.time()
        for _ in range(N_TRIALS):
            p = _sample_params(grid, rng)
            r = _run(mod, is_df, p)
            if _is_valid(r, is_n) and r["profit_factor"] > best_s:
                best_s = r["profit_factor"]
                best_r = r
                best_p = p
        elapsed = time.time() - t_fold

        if best_p is None:
            print("  Fold %d  IS->%7d  OOS %7d-%7d  -- no IS champion  (%.1fs)" % (
                fi + 1, is_end, is_end, oos_end, elapsed))
            continue

        oos_r = _run(mod, oos_df, best_p, return_trades=True)

        yr0 = str(oos_df["year"].iloc[0])
        yr1 = str(oos_df["year"].iloc[-1])
        yr_label = yr0 if yr0 == yr1 else (yr0 + "-" + yr1[-2:])
        is_pf  = best_r["profit_factor"]
        is_t   = best_r["num_trades"]

        if oos_r is not None:
            oos_pts  = oos_r["total_pnl"]
            oos_usd  = oos_pts * mult
            oos_pf   = oos_r["profit_factor"]
            oos_t    = oos_r["num_trades"]
            held     = oos_usd > 0
            folds_held       += int(held)
            oos_pnl_total    += oos_usd
            oos_trades_total += oos_t
            mark = "+" if held else " "
            print("  Fold %d  IS->%7d  OOS %7d-%7d  (%s)  IS PF=%.2f T=%3d"
                  "  OOS PF=%.2f T=%3d  $%+9.0f  [%s]  (%.1fs)" % (
                fi + 1, is_end, is_end, oos_end, yr_label,
                is_pf, is_t, oos_pf, oos_t, oos_usd, mark, elapsed))
            # per-year attribution of champion params
            for yr, grp in oos_df.groupby("year"):
                sub = _run(mod, grp.reset_index(drop=True), best_p)
                y_pnl = sub["total_pnl"] * mult if sub else 0.0
                y_t   = sub["num_trades"]        if sub else 0
                if yr not in per_year_pnl:
                    per_year_pnl[yr] = [0.0, 0]
                per_year_pnl[yr][0] += y_pnl
                per_year_pnl[yr][1] += y_t
            trades_list = oos_r.get("trades", []) if oos_r else []
            fold_rows.append(dict(fold=fi + 1, held=held,
                                  oos_usd=oos_usd, oos_pf=oos_pf,
                                  oos_t=oos_t, yr_label=yr_label,
                                  is_pf=is_pf, is_t=is_t,
                                  champ={k: (v if not isinstance(v, bool) else bool(v))
                                         for k, v in best_p.items()},
                                  trades=trades_list))
        else:
            print("  Fold %d  IS->%7d  OOS %7d-%7d  (%s)  IS PF=%.2f T=%3d"
                  "  OOS: 0 trades  (%.1fs)" % (
                fi + 1, is_end, is_end, oos_end, yr_label,
                is_pf, is_t, elapsed))

    real_folds = len(fold_rows)
    print()
    usd_str = "${:+,.0f}".format(oos_pnl_total)
    print("  TOTAL OOS   held %d/%d   T=%d   %s" % (
        folds_held, real_folds, oos_trades_total, usd_str))

    if per_year_pnl:
        print()
        print("  Per-year OOS (champion params applied to each calendar year):")
        print("  %6s  %7s  %10s" % ("Year", "Trades", "PNL $"))
        for yr in sorted(per_year_pnl):
            pnl, t = per_year_pnl[yr]
            mark = "+" if pnl > 0 else "-"
            pnl_str = "${:+,.0f}".format(pnl)
            print("  %6d  %7d  %10s  [%s]" % (yr, t, pnl_str, mark))

    return dict(held=folds_held, total=real_folds,
                oos_pnl_usd=oos_pnl_total,
                per_year=per_year_pnl, folds=fold_rows)


def main():
    t0 = time.time()
    print("=" * 62)
    print("  VWAP walk-forward -- 16yr ES/NQ RTH (1-contract)")
    print("=" * 62)

    v1 = _load_strategy("VWAP_FADE_1")
    v2 = _load_strategy("VWAP_FADE_2")

    results = {}
    for inst, cfg in INSTRUMENTS.items():
        mult = cfg["mult"]
        print()
        print("=" * 62)
        print("  INSTRUMENT: %s  (mult=%d, $%d/pt)" % (inst, mult, mult))
        print("=" * 62)
        df = _load_master(inst)
        r1 = run_wf(v1, df, GRID_V1, "VWAP_FADE_1 [%s]" % inst, mult)
        r2 = run_wf(v2, df, GRID_V2, "VWAP_FADE_2 [%s]" % inst, mult)
        results[(inst, "v1")] = r1
        results[(inst, "v2")] = r2

    elapsed = time.time() - t0
    print()
    print("=" * 62)
    print("  SUMMARY  (%.0fs)" % elapsed)
    print("=" * 62)
    print("  %-28s  %6s  %12s" % ("Run", "Held", "OOS $"))
    for inst in INSTRUMENTS:
        for v, tag in [("v1", "VWAP_FADE_1"), ("v2", "VWAP_FADE_2")]:
            r = results[(inst, v)]
            usd_s = "${:+,.0f}".format(r["oos_pnl_usd"])
            print("  %-28s  %d/%d  %12s" % (
                "%s [%s]" % (tag, inst),
                r["held"], r["total"], usd_s))

    # Save to augur_research/ for the AUGUR Research tab
    _save_research(results, elapsed)


def _save_research(results, elapsed_s):
    os.makedirs(RESEARCH, exist_ok=True)
    date_str = datetime.date.today().isoformat()
    fname    = "wf_vwap_%s.json" % date_str.replace("-", "")

    runs_out = []
    for inst, cfg in INSTRUMENTS.items():
        mult = cfg["mult"]
        for v, tag in [("v1", "VWAP_FADE_1"), ("v2", "VWAP_FADE_2")]:
            r = results[(inst, v)]
            runs_out.append({
                "label":         "%s [%s]" % (tag, inst),
                "strategy":      tag,
                "instrument":    inst,
                "mult":          mult,
                "total_held":    r["held"],
                "total_folds":   r["total"],
                "total_oos_usd": round(r["oos_pnl_usd"], 2),
                "per_year":      {str(k): v for k, v in r["per_year"].items()},
                "folds":         r["folds"],
            })

    payload = {
        "meta": {
            "run_date":   date_str,
            "script":     "wf_vwap.py",
            "n_trials":   N_TRIALS,
            "n_folds":    N_FOLDS,
            "init_frac":  INIT_FRAC,
            "elapsed_s":  round(elapsed_s, 0),
        },
        "runs": runs_out,
    }

    out_path = os.path.join(RESEARCH, fname)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print("\n  Saved to %s" % out_path)


if __name__ == "__main__":
    main()
