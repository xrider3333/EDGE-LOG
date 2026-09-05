"""ENGU-Q HUNT 6 -- can one config beat the family on BOTH EV R and R / YR?

EV R  = expectancy in R, R = the average LOSING trade (leverage-blind).
R/YR  = EV R x trades per year (the cross-strategy rank read).

TWO LEADERS (pinned window 2010-06-07 .. 2026-06-30, NQ 1m ETH, cost 0.533 pts/RT, $20/pt):
  LEADER_EVR = run #310  (~749 trades, PF ~2.2, EV R ~0.9)
  LEADER_RYR = run #249  (~2924 trades, PF ~1.46, R/YR ~62)

PRE-REGISTERED GATE (written before any cell ran; never changed):
  FULL candidate  <=>  ryr   >  LEADER_RYR.ryr
                  AND  evr   >  LEADER_EVR.evr
                  AND  lb_net >= LEADER_RYR.lb_net          (lockbox = entries >= 2025-06-30)
                  AND  roll12_worst >= min(LEADER_EVR.roll12_worst, LEADER_RYR.roll12_worst)
  SOFT tier       <=>  beats the better of the two leaders on ONE of (evr, ryr) while the
                       other metric is within 10% of the better leader's value
                       (evr >= 0.9*LEADER_EVR.evr or ryr >= 0.9*LEADER_RYR.ryr respectively),
                       AND the same lb_net + roll12_worst legs as FULL.
  Legs are reported per cell so a near-miss is visible.

HARD RULE: date_to = 2026-06-30 (NQ 1m master hole 2026-07-01..08-05 is unrecoverable).

Subcommands: leaders | bridge | filters | limit | exits | all
Each writes  <scratch>/enguq6_<sub>.json  (one record per cell).
"""
import sys, os, json, time, itertools
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"      # masters + sqlite live only here
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_strategies.ENGUQ_1M_ETH_LIM_1_0 import run_backtest         # noqa: E402
from augur_engine.analytics import sharpe_from_pnls, sortino_from_pnls  # noqa: E402
from tools.orb_hunt3 import robustness                                  # noqa: E402

MULT, COST, LB_START, DATE_TO = 20.0, 0.533, "2025-06-30", "2026-06-30"
SCRATCH = (r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop"
           r"\a9e4eec9-eca2-494f-9f8f-ef843d44c8b9\scratchpad")

LEADER_EVR = {"act_R": 3.0, "atr_len": 44, "breakeven_R": 1.5, "buf_atr": 1.0, "ema_len": 420,
              "limit_atr": 0.7, "min_brk": 0.4, "regime_len": 5, "stop_mult": 1.7,
              "tl_len": 238, "trail_frac": 4.0, "vol_mult": 0.8}
LEADER_RYR = {"act_R": 2.5, "atr_len": 106, "breakeven_R": 1.5, "buf_atr": 0.9, "ema_len": 1380,
              "limit_atr": 0.5, "min_brk": 1.3, "regime_len": 0, "stop_mult": 1.0,
              "tl_len": 170, "trail_frac": 2.5, "vol_mult": 0.8}

ARR = None
def data():
    global ARR
    if ARR is None:
        m = find_master("NQ", "1m", "eth", "db_noadj_eth")
        ARR = load_master_arrays(m, date_from=None, date_to=DATE_TO)
        idx = ARR["index"]
        ARR["_years"] = (pd.Timestamp(idx[-1]) - pd.Timestamp(idx[0])).days / 365.25
        print(f"[data] {len(idx)} bars {idx[0]} .. {idx[-1]}  years={ARR['_years']:.2f}", flush=True)
    return ARR


def measure(name, params):
    a = data()
    r = run_backtest(a["open"], a["high"], a["low"], a["close"], volumes=a["volume"],
                     day_id=a["day_id"], index=a["index"], return_trades=True, **params)
    if not r or not r.get("trades"):
        return None
    tr = r["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])            # $ net of cost
    ent = pd.to_datetime([a["index"][int(t[0])] for t in tr]).tz_localize(None)
    yrs = a["_years"]
    cum = np.cumsum(d); dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = d[d > 0], d[d < 0]
    pf = wins.sum() / max(abs(losses.sum()), 1e-9)
    avg_loss = float(abs(losses.mean())) if len(losses) else float("nan")
    evr = float(d.mean() / avg_loss) if avg_loss and avg_loss > 0 else float("nan")
    ryr = evr * len(d) / yrs
    lb = d[ent >= pd.Timestamp(LB_START)]
    rob = robustness(list(ent), list(d))
    return dict(name=name, params=dict(params), n=int(len(d)), net=float(d.sum()),
                lb_net=float(lb.sum()), lb_n=int(len(lb)), dd=dd, pf=float(pf),
                wr=float(len(wins) / len(d) * 100),
                sharpe=sharpe_from_pnls(list(d), yrs), sortino=sortino_from_pnls(list(d), yrs),
                avg_loss_usd=avg_loss, avg_win_usd=float(wins.mean()) if len(wins) else float("nan"),
                evr=evr, ryr=float(ryr), tpy=len(d) / yrs,
                roll12_win=rob["win_pct"], roll12_worst=rob["worst"], roll12_n=rob["n_win"])


_LEAD = {}
def leaders():
    if not _LEAD:
        _LEAD["EVR"] = measure("LEADER_EVR(#310)", LEADER_EVR)
        _LEAD["RYR"] = measure("LEADER_RYR(#249)", LEADER_RYR)
    return _LEAD


def gate(m):
    L = leaders(); E, R = L["EVR"], L["RYR"]
    worst_floor = min(E["roll12_worst"], R["roll12_worst"])
    legs = dict(ryr=m["ryr"] > R["ryr"], evr=m["evr"] > E["evr"],
                lb=m["lb_net"] >= R["lb_net"], worst=m["roll12_worst"] >= worst_floor)
    m["gate_legs"] = legs
    m["passes"] = all(legs.values())
    soft_evr = legs["evr"] and m["ryr"] >= 0.9 * R["ryr"]
    soft_ryr = legs["ryr"] and m["evr"] >= 0.9 * E["evr"]
    m["soft"] = (soft_evr or soft_ryr) and legs["lb"] and legs["worst"] and not m["passes"]
    return m


HDR = (f"{'name':<44} {'n':>5} {'net$':>9} {'LB$':>8} {'DD$':>8} {'PF':>5} {'WR%':>5} "
       f"{'EVR':>6} {'R/YR':>6} {'r12w%':>5} {'r12worst':>9} legs")
def line(m):
    if m is None:
        return "  (no trades)"
    lg = m.get("gate_legs", {})
    tag = "FULL" if m.get("passes") else ("soft" if m.get("soft") else "")
    legs = "".join(k[0].upper() if v else "." for k, v in lg.items())
    return (f"{m['name']:<44} {m['n']:>5} {m['net']:>9,.0f} {m['lb_net']:>8,.0f} {m['dd']:>8,.0f} "
            f"{m['pf']:>5.2f} {m['wr']:>5.1f} {m['evr']:>6.3f} {m['ryr']:>6.1f} "
            f"{m['roll12_win']:>5.1f} {m['roll12_worst']:>9,.0f} {legs} {tag}")


def run_cells(sub, cells):
    L = leaders()
    print("\n== LEADERS ==\n" + HDR)
    for k in ("EVR", "RYR"):
        print(line(gate(L[k])), flush=True)
    out = [gate(dict(L["EVR"])), gate(dict(L["RYR"]))]
    print(f"\n== {sub}: {len(cells)} cells ==\n" + HDR, flush=True)
    t0 = time.time()
    for i, (name, p) in enumerate(cells, 1):
        try:
            m = measure(name, p)
            if m is None:
                print(f"{name:<44} (no trades)", flush=True); continue
            gate(m); out.append(m)
            print(line(m), flush=True)
        except Exception as e:                       # noqa: BLE001
            print(f"{name:<44} ERROR {e!r}", flush=True)
        if i % 10 == 0:
            print(f"  .. {i}/{len(cells)} {time.time()-t0:.0f}s", flush=True)
    path = os.path.join(SCRATCH, f"enguq6_{sub}.json")
    os.makedirs(SCRATCH, exist_ok=True)
    json.dump(out, open(path, "w"), indent=1, default=float)
    print(f"\nSAVED {path}", flush=True)
    summary(out)
    return out


def summary(out):
    cells = [m for m in out if not m["name"].startswith("LEADER")]
    print("\n-- top 10 by R/YR --\n" + HDR)
    for m in sorted(cells, key=lambda m: -m["ryr"])[:10]:
        print(line(m))
    print("\n-- top 10 by EV R --\n" + HDR)
    for m in sorted(cells, key=lambda m: -m["evr"])[:10]:
        print(line(m))
    full = [m for m in cells if m["passes"]]; soft = [m for m in cells if m["soft"]]
    print(f"\nFULL clearers: {len(full)}   SOFT clearers: {len(soft)}")
    for m in full + soft:
        print(line(m)); print("   ", json.dumps(m["params"]))


# ── sweeps ──────────────────────────────────────────────────────────────────────
KNOB_ORDER = ["limit_atr", "min_brk", "ema_len", "tl_len", "atr_len", "stop_mult",
              "trail_frac", "act_R", "regime_len", "buf_atr"]

def cells_bridge():
    cells = []
    for src, dst, tag in ((LEADER_RYR, LEADER_EVR, "RYR->EVR"), (LEADER_EVR, LEADER_RYR, "EVR->RYR")):
        for k in KNOB_ORDER:
            if src[k] == dst[k]:
                continue
            p = dict(src); p[k] = dst[k]
            cells.append((f"{tag} {k}={dst[k]}", p))
    # cumulative walk RYR -> EVR in KNOB_ORDER (which step carries the jump?)
    p = dict(LEADER_RYR)
    for k in KNOB_ORDER:
        if p[k] == LEADER_EVR[k]:
            continue
        p = dict(p); p[k] = LEADER_EVR[k]
        cells.append((f"CUM RYR->EVR ..{k}", p))
    return cells

def cells_filters():
    cells = []
    for base, tag in ((LEADER_EVR, "EVR"), (LEADER_RYR, "RYR")):
        mb0 = base["min_brk"]
        for vm, dmb, rl in itertools.product((0.0, 0.5, 0.8, 1.0, 1.2, 1.5),
                                             (0.0, 0.3, 0.6, -0.3), (0, 5, 10, 20)):
            mb = round(mb0 + dmb, 2)
            if mb < 0:
                continue
            p = dict(base, vol_mult=vm, min_brk=mb, regime_len=rl)
            if p == base:
                continue
            cells.append((f"{tag} vol={vm} brk={mb} reg={rl}", p))
    return cells

def cells_limit():
    return [(f"RYR lim={la} stop={sm}", dict(LEADER_RYR, limit_atr=la, stop_mult=sm))
            for la, sm in itertools.product((0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
                                            (0.8, 1.0, 1.3, 1.7, 2.0))
            if not (la == 0.5 and sm == 1.0)]

def cells_exits():
    return [(f"EVR be={be} trail={tf} act={ar}",
             dict(LEADER_EVR, breakeven_R=be, trail_frac=tf, act_R=ar))
            for be, tf, ar in itertools.product((0.0, 1.0, 1.5, 2.0), (2.0, 2.5, 3.0, 4.0),
                                                (2.0, 2.5, 3.0))
            if not (be == 1.5 and tf == 4.0 and ar == 3.0)]

SWEEPS = dict(bridge=cells_bridge, filters=cells_filters, limit=cells_limit, exits=cells_exits)

if __name__ == "__main__":
    sub = sys.argv[1] if len(sys.argv) > 1 else "leaders"
    if sub == "leaders":
        run_cells("leaders", [])
    elif sub == "all":
        for s in ("bridge", "limit", "exits", "filters"):
            run_cells(s, SWEEPS[s]())
    else:
        run_cells(sub, SWEEPS[sub]())
