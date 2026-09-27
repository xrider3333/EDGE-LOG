"""Export the NOISE ML-sized legs and their raw twins as daily + per-trade P&L (2026-09-27, owner ask via MANAGER,
for the combined frontier-book test). Output: C:\\EdgeLog\\book_legs\\<LEG>_daily.csv and <LEG>_trades.csv.

Legs: NOISE422_raw, NOISE422_fixed (compression 1.5x, Friday 1.5x, cap 3, FOMC-morning 0.5x, no model),
NOISE422_keel_s42, NOISE422_keel_bag7 (seeds 90001-90007), NOISE382_raw, NOISE382_keel_s42 (the live stack),
and with --382-fixed: NOISE382_fixed (the same fixed tilts on #382).
Tape = round-60 (NQ 5m RTH no-adj, 2010-06-07 .. 2026-09-16, cost 0.533, x20); stages by ENTRY date:
IS < 2016-06-30 <= WF < 2025-07-16 <= LB.

FROZEN AT THE LOCKBOX. IS/WF sizes come from KEEL's causal walk (each trade sized from trades already
closed). LOCKBOX sizes are scored by a model FROZEN at the lockbox start: ml_keel.keel_build_state on the
pre-lockbox trades, then keel_score_from_state per lockbox trade - no lockbox trade ever trains the model
that sizes another. The fixed tilts need no freeze (a-priori rules). NOISE is flat by the close, so a
trade's P&L lands on its entry session and daily = sum of that session's trades.

    python tools/export_noise_ml_legs.py          (~25 min; reads the KEEL caches from keel_bag_check.py /
                                                    keel_422_stack_check.py, rebuilding nothing it can reuse)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import keel_bag_check as B                                            # noqa: E402
import keel_422_stack_check as S                                      # noqa: E402
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.analytics import sortino_from_pnls                  # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

OUT = r"C:\EdgeLog\book_legs"
EVENT = dict(K.CFG["v12"]["event"])
DOW = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}
CAP = float(K.CFG["v12"]["comp"]["cap"])


def leg_trades(A, fn, params):
    r = run_backtest(B.mod(fn), arrays=A, params=params, cost_pts=B.COST, return_trades=True)
    order = np.argsort([t[0] for t in r["trades"]], kind="stable")
    T = [r["trades"][i] for i in order]
    plug = S.plugin_sizes(r, len(r["trades"]))[order]
    return T, plug


def frozen_keel(A, T, F, seed, causal, lb):
    """Causal sizes before the lockbox; lockbox trades scored by the state frozen at its start."""
    pre = [t for t, m in zip(T, lb) if not m]
    st = K.keel_build_state(A, pre, feats=F, seed=seed, version="v12")
    out = np.array(causal, float)
    for i in np.where(lb)[0]:
        out[i] = K.keel_score_from_state(st, A, int(T[i][0]), feats=F)[0]
    return out


def stage_of(ts):
    return np.where(ts < B.WF0, "IS", np.where(ts < B.LB0, "WF", "LB"))


def write(name, idx, T, pnl, size, stage):
    ent = idx[[int(t[0]) for t in T]]
    ext = idx[[int(t[1]) for t in T]]
    side = ["long" if (len(t) > 3 and int(t[3]) > 0) else "short" for t in T]
    tr = pd.DataFrame({"entry_time": ent, "exit_time": ext, "side": side, "pnl_usd": np.round(pnl, 2),
                       "size": np.round(size, 4), "stage": stage})
    tr.to_csv(os.path.join(OUT, name + "_trades.csv"), index=False)
    g = tr.assign(date=tr.entry_time.dt.date).groupby("date")
    daily = pd.DataFrame({"pnl_usd": g.pnl_usd.sum().round(2), "trades": g.size(), "size": g["size"].mean().round(4),
                          "stage": g.stage.first()}).reset_index()
    assert abs(daily.pnl_usd.sum() - tr.pnl_usd.sum()) < 1.0, name
    daily.to_csv(os.path.join(OUT, name + "_daily.csv"), index=False)
    return tr


def summary(tr_raw, tr_ml, end):
    rows = []
    for st, a, b in (("WF", B.WF0, B.LB0), ("LB", B.LB0, None)):
        d_raw, d_ml = pd.DatetimeIndex(tr_raw.entry_time), pd.DatetimeIndex(tr_ml.entry_time)
        r = B.stats(d_raw, tr_raw.pnl_usd.to_numpy(), a, b, end)
        m = B.stats(d_ml, tr_ml.pnl_usd.to_numpy(), a, b, end)
        matched = m["net"] * (r["dd"] / m["dd"]) if m["dd"] > 0 else float("nan")
        rows.append((st, r, m, matched))
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    A, idx = S.tape()
    end = idx[-1]
    F = K.keel_features(A)
    report = []
    for leg, fn, params in (("422", "NOISE_1_8_CT304H.py", S.P422), ("382", "NOISE_1_8_CT304.py", B.LEGS["382"][2])):
        T, plug = leg_trades(A, fn, params)
        z = np.load(os.path.join(B.CACHE, "leg%s.npz" % leg))
        P = np.array([float(t[2]) for t in T]) * B.MULT
        assert np.allclose(P, z["P"]), "trade list moved since the KEEL cache was built"
        ts = idx[[max(int(t[0]) - 1, 0) for t in T]]
        stage = stage_of(ts)
        lb = stage == "LB"
        legs = {"raw": np.ones(len(T))}
        if leg == "422":
            legs["fixed"] = K.compression_sizes(A, T, mult=1.5, dow=DOW, cap=CAP, event=EVENT)
            legs["keel_bag7"] = np.mean([frozen_keel(A, T, F, s, z["s%d" % s], lb) for s in S.BAG], axis=0)
        legs["keel_s42"] = frozen_keel(A, T, F, 42, z["s42"], lb)
        out = {k: write(f"NOISE{leg}_{k}", idx, T, P * v, plug * v, stage) for k, v in legs.items()}
        for k in [x for x in legs if x != "raw"]:
            for st, r, m, matched in summary(out["raw"], out[k], end):
                report.append(f"| NOISE #{leg} {k} | {st} | {r['mar']:.2f} | {m['mar']:.2f} | {r['sortino']:.2f} | "
                              f"{m['sortino']:.2f} | {r['net']:,.0f} | {matched:,.0f} |")
        print(f"NOISE #{leg}: exported {', '.join(legs)}", flush=True)
    head = ["| leg | stretch | raw ret/DD | ML ret/DD | raw Sortino | ML Sortino | raw net $ | ML net at raw's DD $ |",
            "|---|---|---|---|---|---|---|---|"]
    body = "\n".join(head + report)
    readme = f"""# NOISE ML legs for the combined frontier-book test (2026-09-27, Custom ML chat)

Built by `tools/export_noise_ml_legs.py`. Tape: NQ 5m RTH NO-ADJUST master (db_noadj_rth), 2010-06-07 ..
{end.date()}, cost 0.533 pts, $20/pt. NOISE is flat by the close, so no trade crosses a contract roll and
no-adjust P&L is exact; roll-corrected masters exist (FADJ_/ADJ_) and were not needed.
Stages by ENTRY date: IS < 2016-06-30 <= WF < 2025-07-16 <= LB (the round-60 stretches).

Files per leg: `<LEG>_trades.csv` (entry_time, exit_time, side, pnl_usd, size, stage) and `<LEG>_daily.csv`
(date, pnl_usd, trades, size, stage; one row per session with a trade; daily sums equal the trade file).
`size` = total contract multiple (the strategy's own sizing x the overlay).

Legs: NOISE422_raw (run #422, NOISE_1_8_CT304H.py 20/1.15/1.75x) - NOISE422_fixed (+ compression 1.5x, Friday
1.5x, cap 3, FOMC pre-statement 0.5x, no model) - NOISE422_keel_s42 - NOISE422_keel_bag7 (mean of seeds
90001-90007) - NOISE382_raw (run #382, NOISE_1_8_CT304.py 30/16/1.15/2.0x) - NOISE382_keel_s42 (the live stack).

FREEZE: IS/WF sizes from KEEL v12's causal walk (leak-fixed engine, 85be1b8+); LB sizes scored by a model
FROZEN at 2025-07-16 (keel_build_state on pre-LB trades, keel_score_from_state per LB trade), so no lockbox
trade trains the model that sizes another. These LB figures therefore differ slightly from the walk-forward-
refit ones quoted earlier (docs/PREREG_keel_422_parts_2026-09-27.md).

OWNER'S YARDSTICK (ML is an edge when it beats raw at matched drawdown out of sample):

{body}
"""
    open(os.path.join(OUT, "README_ml_legs_NOISE.md"), "w", encoding="utf-8").write(readme)
    print(readme)
    return 0


def add_382_fixed():
    """#382 + the fixed tilts and nothing else (no model, so nothing to freeze); appends its rows to the
    README the full run wrote. Asked for after the first export (MANAGER inbox #15, 2026-09-27)."""
    A, idx = S.tape()
    end = idx[-1]
    T, plug = leg_trades(A, "NOISE_1_8_CT304.py", B.LEGS["382"][2])
    P = np.array([float(t[2]) for t in T]) * B.MULT
    stage = stage_of(idx[[max(int(t[0]) - 1, 0) for t in T]])
    raw = write("NOISE382_raw", idx, T, P, plug, stage)
    k = K.compression_sizes(A, T, mult=1.5, dow=DOW, cap=CAP, event=EVENT)
    fx = write("NOISE382_fixed", idx, T, P * k, plug * k, stage)
    rows = [f"| NOISE #382 fixed | {st} | {r['mar']:.2f} | {m['mar']:.2f} | {r['sortino']:.2f} | "
            f"{m['sortino']:.2f} | {r['net']:,.0f} | {matched:,.0f} |" for st, r, m, matched in summary(raw, fx, end)]
    path = os.path.join(OUT, "README_ml_legs_NOISE.md")
    nl = chr(10)
    txt = open(path, encoding="utf-8").read().rstrip(nl)
    open(path, "w", encoding="utf-8").write(txt + nl + nl.join(rows) + nl)
    print(nl.join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(add_382_fixed() if "--382-fixed" in sys.argv else main())
