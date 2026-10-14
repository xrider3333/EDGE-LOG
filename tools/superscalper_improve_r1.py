# SUPERSCALPER improvement round 1 (prereg Amendments 2 + 3 + 4): the 216-cell exit / VIX grid on the 2024 DEVELOPMENT YEAR only
# (NQ 1m ETH no-adjust, lockbox unread), cost 0.706 points a round trip, intrabar 'worst'. OUR PORT, not the published script.
# Selection (Amendment 3): adopt a cell only if its dev net PF >= 1.0 AND the median net PF of its one-step grid neighbours
# > 0.962 (the as-ported cell); otherwise the as-ported defaults stand. The +0.25-point stress line is printed for the chosen cell.
# Cells run in parallel worker processes (BACKTEST_SPEED rule 5: one thread each); each worker loads the 2024 bars once.
# Run from the shared checkout's data:  python tools/superscalper_improve_r1.py [--workers 4]
import argparse, hashlib, itertools, json, os, statistics, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import superscalper_parity as SP

PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_superscalper_r1_2026-10-14.md")
PREREG_LF_SHA = "bd316e49eabf9bc99e241cc54311e7bea099a724d9a5d0063de9122f175744ae"
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\improve_r1_grid.json"
COST, STRESS = 0.706, 0.25
DEV = ("2024-01-01", "2024-12-31")
GRID = dict(sl_cap_atr=["off", "3.0"], sl_scale=[0.5, 0.75, 1.0], tp_scale=[1.0, 1.5, 2.0], max_hold_bars=[0, 30, 90],
            be_trigger=[0.0, 1.0], vix_feed=["none", "daily"])
KEYS = list(GRID)
AS_PORTED = dict(sl_cap_atr="off", sl_scale=1.0, tp_scale=1.0, max_hold_bars=0, be_trigger=0.0, vix_feed="none")
BASE_PF = 0.962
_W = {}


def stats(g, cost):
    g = np.asarray(g, float)
    n = len(g); net = g - cost
    w, l = net[net > 0], net[net <= 0]
    pf = (w.sum() / -l.sum()) if l.sum() < 0 else float("inf")
    return dict(trades=n, win_rate=float((net > 0).mean()) if n else float("nan"), avg_win=float(w.mean()) if len(w) else 0.0,
                avg_loss=float(l.mean()) if len(l) else 0.0, net_pf=float(pf), net_pts=float(net.sum()), gross_pts=float(g.sum()))


def _init():
    for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[v] = "1"
    run_backtest, find_master, load_master_arrays, _root = SP._engine(ROOT)
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    if m is None:
        raise SystemExit("no NQ 1m ETH db_noadj_eth master under %s" % ROOT)
    _W.update(run=run_backtest, m=m, arrays=load_master_arrays(m, date_from=DEV[0], date_to=DEV[1]))


def _cell(vals):
    cell = dict(zip(KEYS, vals))
    t = time.time()
    res = _W["run"](SP.STRATEGY, arrays=_W["arrays"], master=_W["m"], params={**cell, "intrabar": "worst", "_vix_file": "derived", "_detail": True},
                    cost_pts=0.0, return_trades=True)
    g = [r["pnl_pts"] for r in (res or {}).get("trade_detail") or []]
    return vals, g, time.time() - t


def neighbours(cell):
    out = []
    for k in KEYS:
        vals = GRID[k]; i = vals.index(cell[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**cell, k: vals[j]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    got = hashlib.sha256(open(PREREG, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    print("prereg LF sha256", got, "OK" if got == PREREG_LF_SHA else "MISMATCH")
    if got != PREREG_LF_SHA:
        sys.exit("refused: prereg is not the pinned one")
    print("harness LF sha256", hashlib.sha256(open(__file__, "rb").read().replace(b"\r\n", b"\n")).hexdigest())
    print("port sha256", hashlib.sha256(open(SP.STRATEGY, "rb").read()).hexdigest())
    assert DEV[1] < SP.LOCKBOX_FIRST_DAY
    cells = list(itertools.product(*[GRID[k] for k in KEYS]))
    res, pnl = [], {}
    t0 = time.time()
    from research_beacon import beacon
    with beacon("SUPERSCALPER r1 216-cell dev grid", total=len(cells)) as b, \
            ProcessPoolExecutor(max_workers=a.workers, initializer=_init) as ex:
        for f in as_completed([ex.submit(_cell, v) for v in cells]):
            vals, g, dt = f.result()
            s = stats(g, COST); s.update(dict(zip(KEYS, vals))); res.append(s); pnl[vals] = g
            b.step(len(res))
            print("%3d/%d %s -> trades %d net PF %.3f (cell %.0fs, %.0fs total)" % (
                len(res), len(cells), dict(zip(KEYS, vals)), s["trades"], s["net_pf"], dt, time.time() - t0), flush=True)
    json.dump(res, open(OUT, "w"), indent=1)
    key = lambda c: tuple(c[k] for k in KEYS)
    by = {key(r): r for r in res}
    base = by[key(AS_PORTED)]
    cand = []
    for r in res:
        if r["trades"] < 500 or r["net_pf"] < 1.0:
            continue
        med = statistics.median(by[key(n)]["net_pf"] for n in neighbours({k: r[k] for k in KEYS}))
        if med > BASE_PF:
            cand.append((r["net_pf"], med, r))
    show = ("trades", "win_rate", "avg_win", "avg_loss", "net_pf", "net_pts")
    fmt = lambda r: json.dumps({k: round(r[k], 4) if isinstance(r[k], float) else r[k] for k in show})
    print("\nAS-PORTED :", fmt(base), "(as-ported net PF check: %.3f vs 0.962)" % base["net_pf"])
    if cand:
        pf, med, best = max(cand, key=lambda x: x[0])
        st = stats(pnl[key(best)], COST + STRESS)
        print("CHOSEN    :", json.dumps({k: best[k] for k in KEYS}), fmt(best),
              "| neighbour median net PF %.3f | stress +0.25 net PF %.3f" % (med, st["net_pf"]))
        print("DECISION  : IMPROVED defaults")
    else:
        top = max((r for r in res if r["trades"] >= 500), key=lambda r: r["net_pf"])
        print("BEST CELL (not adopted):", json.dumps({k: top[k] for k in KEYS}), fmt(top))
        print("DECISION  : AS-PORTED defaults stand (no cell with net PF >= 1.0 on a plateau above 0.962)")
    print("cells with net PF >= 1.0:", sum(r["net_pf"] >= 1.0 for r in res), "of", len(res), "| wrote", OUT,
          "| %.0f s total" % (time.time() - t0))


if __name__ == "__main__":
    main()
