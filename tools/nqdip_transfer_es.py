"""
NQDIP TRANSFER TEST - does the dip timing work on the S&P, a market it was never tuned on? (2026-09-24)

The dip strategy's selling point is its TIMING: against a same-exposure always-long control on NQ it
doubles the dollars per day held and wins 11 of 15 years (tools/nqdip_beta_check.py). But every setting
it carries was picked on NQ. The cheapest honest test of whether that timing is a real market effect or
a fit to one tape is to run the SAME settings, untouched, on ES - the textbook home of these rules
(Connors' short RSI, the N-day low, the pullback and the capitulation day were all published on the S&P).

Sizing transfers exactly: the file sizes every entry to a constant $100,000 of notional (units rounded
to whole contracts of $2 a point), so its profit is notional x return on whatever tape it reads. Costs
are charged in NQ's convention (0.783 points x $2 per unit, about 1.6 basis points of notional per round
trip), close enough to an S&P micro round trip to change no conclusion.

Configs, both fixed (no tuning on ES): run #307's crown (the old PASS) and the file defaults.
Control, per market: long the same unit-days whenever the close is above the same trend average, no costs.
PRE-REGISTERED: the timing TRANSFERS if, on ES, the dip book beats its same-exposure control on dollars
per unit-day by at least 1.5x AND in at least 10 of 15 full years. Anything less = the NQ edge is not a
general dip effect, and that counts against the NQ result too.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2026-08-24")
C307 = {"rsi_len": 5, "pb_hold": 14, "cap_mult": 1.0, "pb_ema": 5, "cost_pts_rt": 0.783, "trend_len": 100,
        "rsi_exit": 9, "cost_bps": 2.0, "notional": 100000, "use_pb": True, "cap_hold": 5, "use_rsi": True,
        "cap_q": 0.3, "rsi_thr": 30, "dbl_n": 10, "use_cap": True, "use_dbl": True}
sp = ilu.spec_from_file_location("nqdip", "augur_strategies/NQDIP_1_0.py")
M = ilu.module_from_spec(sp); sp.loader.exec_module(M)
DEF = {k: v["default"] for k, v in M.DEFAULT_PARAMS.items()}


def study(inst, params, label):
    A = load_master_arrays(find_master(inst, "5m", "rth", "db_noadj_rth"), **WIN)
    idx = pd.DatetimeIndex(A["index"])
    r = run_backtest("augur_strategies/NQDIP_1_0.py", arrays=A, params=params, cost_pts=0.0, return_trades=True)
    T = pd.DataFrame({"ent": [t[0] for t in r["trades"]], "ex": [t[1] for t in r["trades"]],
                      "pnl": [t[2] for t in r["trades"]]})
    bounds = M._session_bounds(np.asarray(A["day_id"]), len(A["close"]))
    o, c = np.asarray(A["open"], float), np.asarray(A["close"], float)
    do = np.array([o[a] for a, b in bounds]); dc = np.array([c[b - 1] for a, b in bounds])
    days = pd.DatetimeIndex([idx[a].tz_localize(None).normalize() for a, b in bounds])
    pos = {d: i for i, d in enumerate(days)}
    T["eday"] = [idx[i].tz_localize(None).normalize() for i in T.ent]
    T["xday"] = [idx[i].tz_localize(None).normalize() for i in T.ex]
    seams = set(M.detect_roll_seams(do, dc, [idx[a] for a, b in bounds]))
    trend = M._sma(dc, int(params["trend_len"]))
    unit_days = sum(pos[x] - pos[e] for e, x in zip(T.eday, T.xday))
    first = int(params["trend_len"]) + 1
    ctl = np.zeros(len(days)); inm = 0
    for d in range(first, len(days) - 1):
        if not dc[d - 1] > trend[d - 1]:
            continue
        pts = (dc[d] - do[d]) if (d + 1) in seams else (do[d + 1] - do[d])
        k = max(1, int(round(100000.0 / (do[d] * 2.0))))
        ctl[d] = pts * 2.0 * k; inm += 1
    ctl_s = pd.Series(ctl * (unit_days / inm), index=days)
    dip_s = pd.Series(T.pnl.values, index=T.xday.values).groupby(level=0).sum().reindex(days, fill_value=0.0)

    def dd(s):
        cum = s.cumsum(); return float(-(cum - cum.cummax()).min())
    yrs = list(range(2011, 2026))
    wins = sum(dip_s[dip_s.index.year == y].sum() > ctl_s[ctl_s.index.year == y].sum() for y in yrs)
    per_dip, per_ctl = T.pnl.sum() / unit_days, ctl_s.sum() / unit_days
    ratio = per_dip / per_ctl if per_ctl > 0 else float("inf")
    print(f"  {inst} {label:22} trades {len(T):4}  net ${T.pnl.sum():>9,.0f}  DD ${dd(dip_s):>7,.0f}  PF "
          f"{T.pnl[T.pnl>0].sum()/-T.pnl[T.pnl<0].sum():.2f} | control net ${ctl_s.sum():>9,.0f} DD ${dd(ctl_s):>7,.0f}"
          f" | $/unit-day {per_dip:6.1f} vs {per_ctl:6.1f} = x{ratio:4.2f} | beats control {wins}/15 yrs"
          f" | 2022 dip ${dip_s[dip_s.index.year==2022].sum():>8,.0f}")
    return dict(inst=inst, cfg=label, trades=len(T), net=round(T.pnl.sum()), ratio=round(ratio, 2), yrs=int(wins))


if __name__ == "__main__":
    out = []
    for inst in ("NQ", "ES"):
        for params, label in ((C307, "run #307 crown"), (DEF, "file defaults")):
            out.append(study(inst, params, label))
    print()
    for o in out:
        if o["inst"] == "ES":
            ok = o["ratio"] >= 1.5 and o["yrs"] >= 10
            print(f"  ES {o['cfg']:16} -> {'TRANSFERS' if ok else 'DOES NOT TRANSFER'} by the pre-registered bar "
                  f"(x{o['ratio']} per unit-day, {o['yrs']}/15 years)")
    pd.DataFrame(out).to_csv("tools/r16_results/nqdip_transfer_es.csv", index=False)
