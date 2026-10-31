r"""TEST 239 (was 75) PHASE B - ORB #314 half: 5 trailing / breakeven exits vs hold. Prereg (locked v1, sha 0cb05bb6,
checked with tools/prereg_lock.py before anything runs): docs/PREREG_t75b_exits_2026-10-31.md. The overlay, stretches
and numbers are NOISE's tool's (tools/noise_t75b_exits.py) unchanged; only the leg (ORB #314, one contract) differs.

Trades: #314's crowned config (run doc cached by test 238) run ONCE on its own NQ 5m RTH master (db_noadj_rth) cut at the
optimize end 2025-08-12 - the lockbox (2025-08-13 .. 2026-08-13) is never loaded. IS = decision days 2010-06-07 ..
2021-12-31, OOS = 2022-01-01 .. 2025-08-12. Second line: the same overlay on test 238's WF-chain rebuild (2016-07 .. 2025-08).

    python tools/orb_t239b_exits.py         -> C:\EdgeLog\_anatomy_cache\t239b_orb\{full,chain}_grid.csv
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orb_t74_giveback as t74  # noqa: E402
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.drawdowns import four_numbers                        # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from augur_engine.strategies import load_strategy                      # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t239b_orb"
PREREG = "docs/PREREG_t75b_exits_2026-10-31.md"
LOCK_SHA = "0cb05bb6"
IS_END = pd.Timestamp("2021-12-31")
VARIANTS = {"E1": "ATR trail 3x14", "E2": "Chandelier 3x22", "E3": "6-bar trail", "E4": "Time-decay ATR trail",
            "E5": "BE 1R + 2 ATR trail"}
KEYS = ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode", "max_dd", "net")


def full_trades():
    d = json.load(open(t74.RUN))
    v, win = d["validate"], d["validate"]["windows"]
    strat = load_strategy(os.path.join(t74.REPO, "augur_strategies", d["strategy"]))
    cost, mult = float(d["cost_pts"]), float(d.get("multiplier") or 20.0)
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    A = load_master_arrays(m, date_from=d["date_from"], date_to=win["optimize"][1])     # lockbox never loaded
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    assert idx[-1] <= pd.Timestamp(win["lockbox"][0]), "master reaches into the lockbox"
    res = run_backtest(strat, arrays=A, params=dict(v["champion"], return_levels=True), cost_pts=cost, return_trades=True)
    tr = []
    for t, s, l in zip(res["trades"], res.get("trade_sizes") or [1.0] * len(res["trades"]), res["levels"]):
        s = float(s)
        raw = float(t[2]) / s + cost
        tr.append((idx[int(t[1]) - 1].year, int(t[0]), int(t[1]), int(t[3]), float(t[4]), raw, s, float(l["risk"])))
    print("full run: %d trades %s .. %s" % (len(tr), idx[0].date(), idx[-1].date()), flush=True)
    return tr, A, idx, dict(cost=cost, mult=mult)


def atr(H, L, C, n):
    pc = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    return pd.Series(tr).rolling(n, min_periods=n).mean().bfill().to_numpy()


def simulate(tr, A, idx, var):
    O, H, L, C = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    a14, a22 = atr(H, L, C, 14), atr(H, L, C, 22)
    mins_left = ((idx.normalize() + pd.Timedelta(hours=16)) - (idx + pd.Timedelta(minutes=5))).total_seconds().to_numpy() / 60
    out = []
    for f, e, x, sd, ep, raw, s, risk in tr:
        at_open = abs((ep + sd * raw) - O[x]) < 1e-9
        last = x - 1 if at_open else x
        stop, best_c, mfe, be, res = None, ep, 0.0, False, raw
        for j in range(e, last + 1):
            if j > e and stop is not None:
                hit = None
                if sd * (O[j] - stop) <= 0:
                    hit = sd * (O[j] - ep)
                elif sd * ((L[j] if sd > 0 else H[j]) - stop) <= 0:
                    hit = sd * (stop - ep)
                if hit is not None:
                    res = min(hit, raw) if j == x else hit          # same bar as the leg's own exit: the worse fill
                    break
            if j >= x:
                break
            mfe = max(mfe, sd * ((H[j] if sd > 0 else L[j]) - ep))
            best_c = max(best_c, C[j]) if sd > 0 else min(best_c, C[j])
            if var == "E1":
                stop = best_c - sd * 3 * a14[j]
            elif var == "E2":
                ext = H[e:j + 1].max() if sd > 0 else L[e:j + 1].min()
                stop = ext - sd * 3 * a22[j]
            elif var == "E3":
                w0 = max(0, j - 5)
                stop = L[w0:j + 1].min() if sd > 0 else H[w0:j + 1].max()
            elif var == "E4":
                stop = best_c - sd * max(1.0, 3.0 * mins_left[j] / 390.0) * a14[j]
            elif var == "E5":
                if risk > 0 and mfe >= risk:
                    be = True
                if be:
                    t2 = best_c - sd * 2 * a14[j]
                    stop = max(ep, t2) if sd > 0 else min(ep, t2)
        out.append(res)
    return np.asarray(out)


def stretch(tr, raws, idx, meta, d0, d1, mfe, risk):
    s = np.asarray([t[6] for t in tr])
    usd = s * (np.asarray(raws) - meta["cost"]) * meta["mult"]
    dates = pd.DatetimeIndex([idx[t[2] - 1].normalize() for t in tr])
    m = (dates >= d0) & (dates <= d1)
    sess = pd.Index(sorted({x for x in idx.normalize() if d0 <= x <= d1}))
    daily = pd.Series(usd[m], index=dates[m]).groupby(level=0).sum().reindex(sess, fill_value=0.0)
    f = four_numbers(daily, years=(sess[-1] - sess[0]).days / 365.25)
    yrs = pd.Series(usd[m]).groupby(dates[m].year).sum()
    r = np.asarray(raws)[m]
    pos = mfe[m] > 0
    cap = float(r[pos].sum() / mfe[m][pos].sum()) if pos.any() else np.nan
    give = float(np.median((mfe[m] - r) / np.where(risk[m] > 0, risk[m], np.nan)))
    return f, yrs, cap, give, m


def grid(tr, A, idx, meta, stretches, label):
    p = t74.paths(tr, A)
    mfe, risk = p.mfe.to_numpy(), p.risk.to_numpy()
    raw0 = np.asarray([t[5] for t in tr])
    rows = []
    base = {}
    for sname, d0, d1 in stretches:
        f, yrs, cap, give, m = stretch(tr, raw0, idx, meta, d0, d1, mfe, risk)
        base[sname] = yrs
        rows.append(dict(line=label, stretch=sname, variant="HOLD", **{k: f[k] for k in KEYS}, years_won="-",
                         mfe_captured=cap, giveback_med_R=give, changed=0, trades=int(m.sum())))
    for v, name in VARIANTS.items():
        r = simulate(tr, A, idx, v)
        for sname, d0, d1 in stretches:
            f, yrs, cap, give, m = stretch(tr, r, idx, meta, d0, d1, mfe, risk)
            won = int((yrs > base[sname].reindex(yrs.index) + 1e-9).sum())
            rows.append(dict(line=label, stretch=sname, variant="%s %s" % (v, name), **{k: f[k] for k in KEYS},
                             years_won="%d/%d" % (won, len(yrs)), mfe_captured=cap, giveback_med_R=give,
                             changed=int((np.abs(r - raw0)[m] > 1e-9).sum()), trades=int(m.sum())))
        print("  %s %s done" % (label, v), flush=True)
    return pd.DataFrame(rows)


def check_lock():
    """Refuse to run unless the prereg is still the locked v1 (prereg_lock check exits 0 and lists sha 0cb05bb6)."""
    import subprocess
    rc = subprocess.run([sys.executable, os.path.join(t74.REPO, "tools", "prereg_lock.py"), "check", PREREG],
                        cwd=t74.REPO, capture_output=True, text=True)
    ls = subprocess.run([sys.executable, os.path.join(t74.REPO, "tools", "prereg_lock.py"), "list"],
                        cwd=t74.REPO, capture_output=True, text=True).stdout
    row = [ln for ln in ls.splitlines() if ln.startswith("PREREG_t75b_exits_2026-10-31")]
    if rc.returncode != 0 or not row or LOCK_SHA not in row[0]:
        raise SystemExit("refused: prereg lock mismatch (nothing computed)\n" + rc.stdout + rc.stderr)
    print("PREREG LOCK OK: %s" % row[0].strip(), flush=True)


def main():
    check_lock()
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 240)
    tr, A, idx, meta = full_trades()
    g = grid(tr, A, idx, meta, [("IS 2010-21", idx[0].normalize(), IS_END),
                                 ("OOS 2022-25.08", pd.Timestamp("2022-01-01"), idx[-1].normalize())], "full")
    g.to_csv(os.path.join(OUT, "full_grid.csv"), index=False)
    print(g.round(3).to_string(index=False), flush=True)
    ctr, cA, cidx, cmeta = t74.chain()
    wf = cmeta["wf"]
    c = grid(ctr, cA, cidx, dict(cost=cmeta["cost"], mult=cmeta["mult"]),
             [("WF chain", pd.Timestamp(wf["from"]), pd.Timestamp(wf["to"]))], "chain")
    c.to_csv(os.path.join(OUT, "chain_grid.csv"), index=False)
    print(c.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
