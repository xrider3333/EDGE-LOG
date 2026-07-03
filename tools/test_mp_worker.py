# Headless validation of augur_mp_worker: result IDENTITY vs single-thread + speedup.
# Run: python tools/test_mp_worker.py
import os, sys, time, math, itertools
import importlib.util
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
STRAT = os.path.join(ROOT, "augur_strategies", "ORB_3_0.py")
MASTER = os.path.join(ROOT, "augur_uploads", "master_00c66966.csv")
COST_PTS = 5.66 / 20 + 0.25       # NQ commission->pts + slippage
MIN_T = 30
N_WORKERS = 6


def build_grid():
    grid = {
        "or_bars": [1, 2, 3, 6],
        "trade_mode": ["Both", "First-candle dir"],
        "stop_frac": [0.5, 0.75, 1.0],
        "vol_filter": [0.0, 1.0, 1.5],
        "breakout_buf": [0.0, 0.05],
        "target_R": [0.0, 3.0, 5.0],
        "flat_eod": [True],
    }
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*grid.values())]


def main():
    import augur_mp_worker as mpw

    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    O = df["open"].to_numpy(float); H = df["high"].to_numpy(float)
    L = df["low"].to_numpy(float);  C = df["close"].to_numpy(float)
    V = df["volume"].to_numpy(float)
    DAY = pd.factorize(pd.Series(dt).dt.date)[0].astype("int64")

    combos = build_grid()
    n = len(combos)
    print(f"{n} combos on {len(C):,} bars, cost={COST_PTS:.4f} pts/RT")

    # ── Single-thread reference (exactly the app's path: costs in-eval) ──────
    spec = importlib.util.spec_from_file_location("s1", STRAT)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    t0 = time.time()
    ref = {}
    for i, p in enumerate(combos):
        m = mod.run_backtest(O, H, L, C, volumes=V, day_id=DAY,
                             return_trades=True, **p)
        if m:
            m = mpw._apply_costs(m, COST_PTS); m.pop("trades", None)
        if m and m["num_trades"] >= MIN_T:
            ref[i] = m
    t_seq = time.time() - t0
    print(f"single-thread: {t_seq:.1f}s, {len(ref)} valid")

    # ── MP path (exactly the app's wiring) ───────────────────────────────────
    t0 = time.time()
    chunk_sz = max(8, math.ceil(n / (N_WORKERS * 6)))
    idx_combos = list(enumerate(combos))
    chunks = [idx_combos[i:i + chunk_sz] for i in range(0, n, chunk_sz)]
    got, errs = {}, 0
    with ProcessPoolExecutor(max_workers=N_WORKERS,
                             initializer=mpw.init_worker,
                             initargs=(STRAT, O, H, L, C, V, DAY, COST_PTS)) as pool:
        futs = [pool.submit(mpw.eval_chunk, ch) for ch in chunks]
        for f in as_completed(futs):
            for ci, cm, cerr in f.result():
                if cerr is not None:
                    errs += 1
                elif cm and cm["num_trades"] >= MIN_T:
                    got[ci] = cm
    t_mp = time.time() - t0
    print(f"MP x{N_WORKERS}:      {t_mp:.1f}s, {len(got)} valid, {errs} errors  "
          f"-> speedup {t_seq / t_mp:.1f}x")

    # ── Identity check ────────────────────────────────────────────────────────
    assert set(ref) == set(got), f"valid-set mismatch: {len(ref)} vs {len(got)}"
    worst = 0.0
    for i in ref:
        for k in ("total_pnl", "num_trades", "win_rate", "profit_factor",
                  "max_drawdown", "avg_pnl", "wins", "losses"):
            a, b = ref[i][k], got[i][k]
            if a == b:
                continue
            d = abs(float(a) - float(b))
            worst = max(worst, d)
            assert d < 1e-9, f"combo {i} key {k}: {a} != {b}"
    print(f"IDENTITY OK — {len(ref)} valid combos byte-equal (worst delta {worst:.2e})")


if __name__ == "__main__":
    main()
