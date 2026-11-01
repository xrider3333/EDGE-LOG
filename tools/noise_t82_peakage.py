r"""t82 M6 PEAK-AGE VALIDATE - NOISE #382 (owner 11-01, MANAGER #159). Prereg (locked before this ran):
docs/PREREG_noise_m6_peakage_2026-11-01.md.

Fresh engine runs: every WF fold of #382's chain is re-run through augur_engine.engine.run_backtest with
augur_strategies/NOISE_1_8_CT304_PA.py, the fold's own champion params and one cell's pa_* knobs (test 74's chain loop,
same splice mapping and warm starts). Parity gate first: pa_mode off must equal test 74's chain rebuild trade for trade.
Second line (descriptive): #382's crown run once, IS 2010-06-07..2021-12-31 / OOS 2022-01-01..2025-07-15. Lockbox never loaded.

    python tools/noise_t82_peakage.py      -> C:\EdgeLog\_anatomy_cache\t82_peakage\{chain,full}.csv
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as t74  # noqa: E402
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.drawdowns import four_numbers                        # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from augur_engine.strategies import load_strategy                      # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t82_peakage"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELLS = [("HOLD", dict(pa_mode="off")),
         ("M6 w0.50", dict(pa_mode="peak_age", pa_n=10, pa_arm_r=0.5, pa_weight=0.5)),
         ("M6 w1.00", dict(pa_mode="peak_age", pa_n=10, pa_arm_r=0.5, pa_weight=1.0)),
         ("TIME w0.50", dict(pa_mode="time_exit", pa_n=10, pa_weight=0.5)),
         ("TIME w1.00", dict(pa_mode="time_exit", pa_n=10, pa_weight=1.0))]
KEYS = ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode", "max_dd", "net")


def setup():
    d = json.load(open(t74.RUN))
    v, win = d["validate"], d["validate"]["windows"]
    cost, mult = float(d["cost_pts"]), float(d.get("multiplier") or 20.0)
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    A = load_master_arrays(m, date_from=d["date_from"], date_to=win["optimize"][1])     # stops at the optimize end
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    assert idx[-1] < pd.Timestamp(win["lockbox"][0]), "master reaches into the lockbox"
    return d, v, win, cost, mult, A, idx


def chain_trades(strat, cell, d, v, win, cost, A, idx):
    """[(fold, entry_bar, exit_bar, pts_costed, size)] - test 74's chain loop with the PA file and one cell."""
    did = np.asarray(A["day_id"])
    warm = int(win.get("warm_days") or 0)
    pkeys = list(v["champion"].keys())
    rows = sorted([r for r in d["top10_results"] if "fold" in r], key=lambda r: int(r["fold"]))
    expect = int(rows[-1]["train_bars"]) + int(rows[-1]["test_bars"])
    ins = [(pd.Timestamp("2020-02-28"), 60), (pd.Timestamp("2020-06-30"), 69)]
    assert len(idx) - expect == sum(n for _, n in ins), "bar drift is not the two known splices"
    first = {dd: int(np.searchsorted(idx.normalize(), dd, side="left")) for dd, _ in ins}

    def shift(b):
        k = b
        for dd, n in ins:
            if k >= first[dd] and idx[min(k, len(idx) - 1)].normalize() > dd:
                k += n
        return k

    def warm_start(a0):
        if warm <= 0 or a0 <= 0:
            return a0
        tgt = int(did[a0]) - warm
        return 0 if tgt <= int(did[0]) else int(np.searchsorted(did, tgt, side="left"))

    out = []
    for r in rows:
        s0, s1 = shift(int(r["train_bars"])), shift(int(r["train_bars"]) + int(r["test_bars"]))
        w = warm_start(s0)
        S = {k: (x[w:s1] if hasattr(x, "__len__") and not isinstance(x, (str, dict)) and len(x) == len(idx) else x)
             for k, x in A.items()}
        res = run_backtest(strat, arrays=S, params=dict({k: r[k] for k in pkeys}, **cell), cost_pts=cost,
                           return_trades=True)
        for t, s in zip(res["trades"], res["trade_sizes"]):
            if int(t[0]) >= s0 - w:
                out.append((int(r["fold"]), int(t[0]) + w, int(t[1]) + w, float(t[2]), float(s)))
    return out


def measure(tr, idx, mult, d0, d1, base_folds=None):
    usd = np.asarray([t[3] for t in tr]) * mult
    ent = pd.DatetimeIndex([idx[t[1]].normalize() for t in tr])
    m = (ent >= d0) & (ent <= d1)
    sess = pd.Index(sorted({x for x in idx.normalize() if d0 <= x <= d1}))
    daily = pd.Series(usd[m], index=ent[m]).groupby(level=0).sum().reindex(sess, fill_value=0.0)
    f = four_numbers(daily, years=(sess[-1] - sess[0]).days / 365.25)
    folds = pd.Series(usd[m]).groupby(np.asarray([t[0] for t in tr])[m]).sum()
    return f, folds, int(m.sum())


def main():
    os.makedirs(OUT, exist_ok=True)
    d, v, win, cost, mult, A, idx = setup()
    strat = load_strategy(os.path.join(REPO, "augur_strategies", "NOISE_1_8_CT304_PA.py"))
    # parity gate: off == test 74's chain rebuild
    ref, _, _, _ = t74.chain()
    runs = {}
    for name, cell in CELLS:
        runs[name] = chain_trades(strat, cell, d, v, win, cost, A, idx)
        print("%s: %d trades" % (name, len(runs[name])), flush=True)
    hold = runs["HOLD"]
    refpts = sum(s * (raw - cost) for *_, raw, s, _ in ref)
    hp = sum(t[3] for t in hold)
    ok = len(hold) == len(ref) and abs(hp - refpts) < 1e-6 * max(1.0, abs(refpts)) + 1e-6 and \
        all(a[1] == b[1] and a[2] == b[2] for a, b in zip(hold, ref))
    print("PARITY %s: off %d trades / %.2f pts vs chain rebuild %d / %.2f" % ("PASS" if ok else "FAIL", len(hold), hp,
                                                                            len(ref), refpts), flush=True)
    if not ok:
        raise SystemExit("parity failed - no verdict")
    wf = d["validate"]["wf_oos"]
    d0, d1 = pd.Timestamp(wf["from"]), pd.Timestamp(wf["to"])
    rows, base = [], None
    for name, _ in CELLS:
        tr = runs[name]
        f, folds, n = measure(tr, idx, mult, d0, d1)
        if base is None:
            base = folds
        won = "-" if name == "HOLD" else "%d/%d" % (int((folds > base.reindex(folds.index) + 1e-9).sum()), len(folds))
        changed = sum(1 for a, b in zip(tr, hold) if abs(a[3] - b[3]) > 1e-9)
        rows.append(dict(cell=name, **{k: f[k] for k in KEYS}, folds_won=won, trades=n, changed=changed,
                         **{"fold%d" % k: round(float(x), 0) for k, x in folds.items()}))
    g = pd.DataFrame(rows)
    g.to_csv(os.path.join(OUT, "chain.csv"), index=False)
    pd.set_option("display.width", 250)
    print(g.round(3).to_string(index=False))
    json.dump({"parity": ok, "wf_from": str(d0.date()), "wf_to": str(d1.date())}, open(os.path.join(OUT, "meta.json"), "w"))
    return 0


if __name__ == "__main__" and "--full" not in sys.argv:
    sys.exit(main())


def full_line():
    """Second line (descriptive): #382's crown run once per cell, IS to 2021-12-31 / OOS 2022-01-01..optimize end."""
    d, v, win, cost, mult, A, idx = setup()
    strat = load_strategy(os.path.join(REPO, "augur_strategies", "NOISE_1_8_CT304_PA.py"))
    rows, base = [], {}
    for name, cell in CELLS:
        res = run_backtest(strat, arrays=A, params=dict(v["champion"], **cell), cost_pts=cost, return_trades=True)
        tr = [(pd.Timestamp(idx[int(t[0])]).year, int(t[0]), int(t[1]), float(t[2]), float(s))
              for t, s in zip(res["trades"], res["trade_sizes"])]
        for sname, d0, d1 in (("IS 2010-21", idx[0].normalize(), pd.Timestamp("2021-12-31")),
                              ("OOS 2022-25.07", pd.Timestamp("2022-01-01"), idx[-1].normalize())):
            f, yrs, n = measure(tr, idx, mult, d0, d1)
            if name == "HOLD":
                base[sname] = yrs
            won = "-" if name == "HOLD" else "%d/%d" % (int((yrs > base[sname].reindex(yrs.index) + 1e-9).sum()), len(yrs))
            rows.append(dict(cell=name, stretch=sname, **{k: f[k] for k in KEYS}, years_won=won, trades=n))
    g = pd.DataFrame(rows)
    g.to_csv(os.path.join(OUT, "full.csv"), index=False)
    print(g.round(3).to_string(index=False))


if __name__ == "__main__" and "--full" in sys.argv:
    full_line()
