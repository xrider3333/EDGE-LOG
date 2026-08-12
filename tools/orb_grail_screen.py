"""ORB grail screen — mass random search over the ALL-LEGAL ORB_3_5 space.

Protocol (pre-registered in this docstring before the first result was seen):
  * Space: exactly ORB_3_5.py's DEFAULT_PARAMS ranges — every filter input exists
    strictly before the fill bar (vol_filter does not exist here at all).
  * Sample: N seeded random configs, deduped.
  * Each config runs ONCE over 2010-06-07 -> lockbox start; its trades are sliced
    into 8 equal SESSION eras. Score = (# profitable eras, net/DD, net). A config
    must put >= 400 trades on the board — low-trade grails are traps.
  * The LOCKBOX (last 252 sessions) is quarantined: computed but written to a
    separate column that the ranking never reads. It is revealed only for the
    shortlist, once, after the ranking is frozen.
  * Levels here use cost 0.533 pts/RT. The production Auto-Validate is the
    arbiter of record for anything this screen nominates.

Run:  python3.13.exe tools/orb_grail_screen.py [N]  (default 24000)
Out:  tools/data/orb_grail_screen.csv  (+ console top-20)
"""
import csv
import os
import pathlib
import random
import sys
import importlib.util as I

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

COST = 0.533
MULT = 20
LB_SESS = 252
ERAS = 8
MIN_TRADES = 400
SEED = 42

SPACE = {
    "or_bars":        ("int",   1, 6, 1),
    "trade_mode":     ("cat",   ["Both", "First-candle dir", "Long Only", "Short Only"]),
    "stop_frac":      ("float", 0.5, 2.0, 0.25),
    "breakout_buf":   ("float", 0.0, 0.3, 0.05),
    "close_confirm":  ("cat",   [False, True]),
    "partial_exit_R": ("float", 0.0, 4.0, 0.5),
    "trail_bars":     ("int",   0, 12, 1),
    "target_R":       ("float", 0.0, 6.0, 0.5),
    "atr_filter":     ("float", 0.0, 1.1, 0.1),
    "vpace_filter":   ("float", 0.0, 1.2, 0.1),
    "gap_min":        ("float", 0.0, 0.5, 0.05),
    "orw_min":        ("float", 0.0, 0.7, 0.1),
    "entry_cutoff":   ("int",   0, 24, 2),
}

_G = {}


def _init():
    from augur_engine import data as D
    mm = [x for x in D.list_masters() if x.get("instrument") == "NQ"
          and x.get("timeframe") == "5m" and x.get("source") == "db_noadj_rth"][0]
    a = D.load_master_arrays(mm)
    sp = I.spec_from_file_location("orb35", str(REPO / "augur_strategies" / "ORB_3_5.py"))
    m = I.module_from_spec(sp)
    sp.loader.exec_module(m)
    day = a["day_id"]
    nb = len(a["open"])
    edges = np.concatenate(([0], np.flatnonzero(np.diff(day) != 0) + 1, [nb]))
    sess_of = np.zeros(nb, dtype=np.int32)
    for i in range(len(edges) - 1):
        sess_of[edges[i]:edges[i + 1]] = i
    nsess = len(edges) - 1
    _G.update(a=a, run=m.run_backtest, sess_of=sess_of, nsess=nsess)


def _sample(rng):
    cfg = {}
    for k, spec in SPACE.items():
        if spec[0] == "cat":
            cfg[k] = rng.choice(spec[1])
        elif spec[0] == "int":
            lo, hi, st = spec[1:]
            cfg[k] = int(rng.randrange(lo, hi + 1, st))
        else:
            lo, hi, st = spec[1:]
            n = int(round((hi - lo) / st))
            cfg[k] = round(lo + st * rng.randint(0, n), 4)
    cfg["flat_eod"] = True
    cfg["skip_holidays"] = False
    return cfg


def _eval(cfg):
    a = _G["a"]
    r = _G["run"](a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                  day_id=a["day_id"], return_trades=True, **cfg)
    tr = r.get("trades") or []
    if len(tr) < 50:
        return None
    sess_of, nsess = _G["sess_of"], _G["nsess"]
    cut = nsess - LB_SESS
    ek = np.array([t[0] for t in tr], dtype=np.int64)
    pnl = np.array([float(t[2]) for t in tr]) - COST
    s = sess_of[ek]
    is_m = s < cut
    p_is = pnl[is_m]
    n_is = len(p_is)
    if n_is < MIN_TRADES:
        return None
    # eras: 8 equal session blocks across [21, cut)
    era = np.clip(((s - 21) * ERAS) // max(1, (cut - 21)), 0, ERAS - 1)
    held = 0
    for e in range(ERAS):
        m2 = is_m & (era == e)
        if m2.any() and pnl[m2].sum() > 0:
            held += 1
    net = float(p_is.sum())
    eq = np.cumsum(p_is)
    dd = abs(float(np.min(eq - np.maximum.accumulate(eq))) or 1e-9)
    gw = p_is[p_is > 0].sum()
    gl = -p_is[p_is < 0].sum()
    p_lb = pnl[~is_m]                      # QUARANTINED — never read by the ranking
    return dict(cfg=cfg, n=n_is, held=held, net_usd=round(net * MULT),
                dd_usd=round(dd * MULT), mar=round(net / dd, 2) if dd else 0.0,
                pf=round(float(gw / gl), 3) if gl > 1e-9 else 99.0,
                lb_n=int(len(p_lb)), lb_usd=round(float(p_lb.sum()) * MULT))


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 24000
    NW = int(sys.argv[2]) if len(sys.argv) > 2 else None
    _init()
    rng = random.Random(SEED)
    seen, cfgs = set(), []
    while len(cfgs) < N:
        c = _sample(rng)
        key = tuple(c[k] for k in SPACE)
        if key not in seen:
            seen.add(key)
            cfgs.append(c)
    print(f"screening {len(cfgs)} configs, {ERAS} eras, lockbox quarantined", flush=True)

    from multiprocessing import Pool, cpu_count
    keys = list(SPACE)
    os.makedirs(REPO / "tools" / "data", exist_ok=True)
    path = REPO / "tools" / "data" / "orb_grail_screen.csv"
    rows = []
    # rows stream to disk as they land — a killed process keeps every finished config
    with open(path, "w", newline="", buffering=1) as f:
        w = csv.writer(f)
        w.writerow(["held", "n", "net_usd", "dd_usd", "mar", "pf", "lb_n", "lb_usd"] + keys)
        with Pool(NW or max(2, cpu_count() - 2), initializer=_init) as pool:
            for i, out in enumerate(pool.imap_unordered(_eval, cfgs, chunksize=16)):
                if out:
                    rows.append(out)
                    w.writerow([out["held"], out["n"], out["net_usd"], out["dd_usd"],
                                out["mar"], out["pf"], out["lb_n"], out["lb_usd"]]
                               + [out["cfg"][k] for k in keys])
                if (i + 1) % 1000 == 0:
                    print(f"  {i+1}/{len(cfgs)} done, {len(rows)} qualified", flush=True)
    rows.sort(key=lambda r: (r["held"], r["mar"], r["net_usd"]), reverse=True)
    print(f"\nwrote {len(rows)} rows -> {path}\n", flush=True)
    print("TOP 20 (ranked WITHOUT the lockbox; lb column shown for the record only):")
    for r in rows[:20]:
        c = r["cfg"]
        print(f"  held {r['held']}/8  n{r['n']:>5}  net ${r['net_usd']:>8,}  DD ${r['dd_usd']:>7,}"
              f"  MAR {r['mar']:>5.1f}  PF {r['pf']:>5.3f}  | LB ${r['lb_usd']:>7,}/{r['lb_n']}"
              f"  | or{c['or_bars']} {c['trade_mode'][:5]} stop{c['stop_frac']}"
              f" tr{c['trail_bars']} tgt{c['target_R']} pe{c['partial_exit_R']}"
              f" cc{int(c['close_confirm'])} vp{c['vpace_filter']} gap{c['gap_min']}"
              f" orw{c['orw_min']} atr{c['atr_filter']} cut{c['entry_cutoff']}", flush=True)


if __name__ == "__main__":
    main()
