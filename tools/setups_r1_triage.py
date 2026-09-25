"""SETUPS round 1 - triage driver (pre-registered in SETUPS_PREREG.md section 6).

Runs every pre-declared triage cell (each file's PARAM_GRID_PRESETS['Triage (pre-registered)'],
full cartesian product) on NQ and ES 1-minute 24-hour bars over the SELECTION window only
(2010-06-07 .. 2025-07-06), through each strategy file's own run_backtest, and scores every cell
on the house bar (the round-37 score(), in dollars) at the house cost and the stress cost.

A file ADVANCES only if a cell passes the house bar at house cost, keeps PF >= 1.10 at the stress
cost, and >= 2 one-step neighbours (one knob moved to the adjacent declared value, declared order)
keep PF >= 1.15 at house cost. Cells with PF >= 2 or net/DD >= 20 are flagged as look-ahead alarms.

    python tools/setups_r1_triage.py            (from the shared checkout; ~10-20 min)
    -> tools/setups_r1_results/triage.csv, triage_summary.txt
"""
import os, sys, csv, time, itertools, importlib.util as ilu
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
if DATA_REPO != ROOT:
    sys.path.insert(1, DATA_REPO)

FILES = ["CBUQ_1M_1_0.py", "CBDQ_1M_1_0.py", "EBUQ_1M_1_0.py", "ENGU_2_0.py", "ENGU_2_0_D.py"]
PRESET = "Triage (pre-registered)"
WIN = dict(date_from="2010-06-07", date_to="2025-07-06")
YEARS = (np.datetime64("2025-07-06") - np.datetime64("2010-06-07")).astype(int) / 365.25
INSTR = {"NQ": dict(mult=20.0, cost=0.533, stress=0.783),
         "ES": dict(mult=50.0, cost=0.363, stress=0.613)}
OUTDIR = os.path.join(HERE, "setups_r1_results")
TIMEFRAME = os.environ.get("SETUPS_TF", "1m")          # wave 2 (pre-declared) = 5m

_ARR = {}
_MODS = {}


def _load_mod(fn):
    if fn not in _MODS:
        sp = ilu.spec_from_file_location("setups_r1_" + fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
        m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
        _MODS[fn] = m
    return _MODS[fn]


def _arrays(inst):
    if inst not in _ARR:
        from augur_engine.data import find_master, load_master_arrays
        m = find_master(inst, TIMEFRAME, "eth", "db_noadj_eth")
        a = load_master_arrays(m, **WIN)
        _ARR[inst] = a
    return _ARR[inst]


def cells_for(mod):
    g = mod.PARAM_GRID_PRESETS[PRESET]
    keys = list(g.keys())
    return keys, [dict(zip(keys, vals)) for vals in itertools.product(*[g[k] for k in keys])]


def score(pts, holds, cost, mult):
    """round-37 score() (tools/r37_scalp_triage.py), parameterised by cost/mult/years."""
    p = (np.asarray(pts, float) - cost) * mult
    n = len(p)
    if n == 0:
        return dict(n=0, net=0, pf=0, dd=0, mar=0, win=0, folds8=0, top10_pct=999, exnet=0,
                    per_trade=0, hold_med=0, PASS=0)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else 99.0
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); w = float((p > 0).mean())
    k = n // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0) if k else 0
    srt = sorted(p, reverse=True); top10 = sum(srt[:10]); exnet = float(np.sum(srt[10:]))
    per = net / n
    mar = round(net / -dd, 2) if dd < 0 else 99.0
    top = round(100 * top10 / net) if net > 0 else 999
    ok = (pf >= 1.25 and mar >= 8 and n >= 300 and folds >= 6 and top < 90 and exnet > 0
          and per >= 2 * cost * mult)
    return dict(n=n, net=round(net), pf=round(pf, 3), dd=round(-dd), mar=mar, win=round(100 * w, 1),
                folds8=folds, top10_pct=top, exnet=round(exnet), per_trade=round(per, 2),
                hold_med=float(np.median(holds)) if len(holds) else 0, PASS=int(ok))


def run_cell(job):
    inst, fn, cell = job
    a = _arrays(inst); mod = _load_mod(fn)
    t0 = time.time()
    r = mod.run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                         index=a["index"], return_trades=True, **cell)
    secs = time.time() - t0
    tr = (r or {}).get("trades") or []
    pts = [t[2] for t in tr]; holds = [t[1] - t[0] for t in tr]
    spec = INSTR[inst]
    h = score(pts, holds, spec["cost"], spec["mult"])
    s = score(pts, holds, spec["stress"], spec["mult"])
    alarm = int(h["n"] > 0 and (h["pf"] >= 2 or h["mar"] >= 20))
    row = dict(inst=inst, file=fn, cell=";".join("%s=%s" % kv for kv in cell.items()), secs=round(secs, 2),
               **h, stress_pf=s["pf"], stress_net=s["net"], alarm=alarm)
    return row


def neighbours(rows, keys_by_file, grids):
    """>=2 one-step neighbours with PF >= 1.15 (house cost)."""
    by = {(r["inst"], r["file"], r["cell"]): r for r in rows}
    for r in rows:
        if not r["PASS"]:
            r["nb_ok"] = ""; continue
        keys = keys_by_file[r["file"]]; g = grids[r["file"]]
        cell = dict(kv.split("=", 1) for kv in r["cell"].split(";"))
        good = tot = 0
        for k in keys:
            vals = [str(v) for v in g[k]]
            i = vals.index(cell[k])
            for j in (i - 1, i + 1):
                if 0 <= j < len(vals):
                    c2 = dict(cell); c2[k] = vals[j]
                    key = (r["inst"], r["file"], ";".join("%s=%s" % (kk, c2[kk]) for kk in keys))
                    if key in by:
                        tot += 1; good += int(by[key]["n"] > 0 and by[key]["pf"] >= 1.15)
        r["nb_ok"] = "%d/%d" % (good, tot)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    keys_by_file, grids, jobs = {}, {}, []
    for fn in FILES:
        mod = _load_mod(fn)
        keys, cells = cells_for(mod)
        keys_by_file[fn] = keys; grids[fn] = mod.PARAM_GRID_PRESETS[PRESET]
        for inst in INSTR:
            jobs += [(inst, fn, c) for c in cells]
    # one process per instrument keeps each process's arrays + strategy caches warm
    jobs.sort(key=lambda j: (j[0], j[1]))
    print("cells:", len(jobs), "timeframe:", TIMEFRAME, flush=True)
    try:
        sys.path.insert(0, HERE)
        from research_beacon import beacon
    except Exception:
        beacon = None
    rows = []
    groups = {inst: [j for j in jobs if j[0] == inst] for inst in INSTR}

    def _drain(b=None):
        with ProcessPoolExecutor(max_workers=len(groups)) as ex:
            futs = [ex.submit(_run_group, g) for g in groups.values()]
            for f in futs:
                rows.extend(f.result())
                if b is not None:
                    b.step(len(rows))

    if beacon is not None:
        with beacon("SETUPS r1 triage (%s)" % TIMEFRAME, total=len(jobs)) as b:
            _drain(b)
    else:
        _drain()
    neighbours(rows, keys_by_file, grids)
    tag = "" if TIMEFRAME == "1m" else "_" + TIMEFRAME
    out = os.path.join(OUTDIR, "triage%s.csv" % tag)
    cols = list(rows[0].keys())
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    lines = []
    for fn in FILES:
        for inst in INSTR:
            rr = [r for r in rows if r["file"] == fn and r["inst"] == inst and r["n"] > 0]
            best = sorted(rr, key=lambda r: (r["PASS"], r["pf"]), reverse=True)[:3]
            adv = [r for r in rr if r["PASS"] and r["stress_pf"] >= 1.10 and int(r["nb_ok"].split("/")[0] or 0) >= 2]
            lines.append("%s %s: %d cells, %d pass house bar, %d ADVANCE, %d alarms" % (
                fn, inst, len(rr), sum(r["PASS"] for r in rr), len(adv), sum(r["alarm"] for r in rr)))
            for r in best:
                lines.append("   %-70s n=%5d net=%9s PF=%.3f MAR=%.2f f8=%d top10=%s%% ex=%s $/tr=%.2f stressPF=%.3f nb=%s %s" % (
                    r["cell"], r["n"], format(r["net"], ","), r["pf"], min(r["mar"], 99), r["folds8"], r["top10_pct"],
                    format(r["exnet"], ","), r["per_trade"], r["stress_pf"], r["nb_ok"], "PASS" if r["PASS"] else ""))
    txt = "\n".join(lines)
    with open(os.path.join(OUTDIR, "triage%s_summary.txt" % tag), "w") as fh:
        fh.write(txt + "\n")
    print(txt)


def _run_group(group):
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    out = []
    for j in group:
        r = run_cell(j)
        print("%s %-16s %-80s n=%5d PF=%.3f net=%s %s%s" % (r["inst"], r["file"], r["cell"], r["n"], r["pf"],
              format(r["net"], ","), "PASS" if r["PASS"] else "", " ALARM" if r["alarm"] else ""), flush=True)
        out.append(r)
    return out


if __name__ == "__main__":
    main()
