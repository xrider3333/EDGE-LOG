# SUPERSCALPER r4 (MANAGER #189, prereg C:/EdgeLog/manager/prereg/PREREG_tv_superscalper_limit_r4_2026-11-06.md).
# PRE-WF rows only. Limit entry at the signal close, exits re-walked from the fill, market exits pay 1 tick in the REAL row.
#   PYTHONPATH=. python tools/superscalper_limit_r4.py
import importlib.util, json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import superscalper_validate_read as R
import superscalper_regime_r3 as S

OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\limit_r4.json"
TICK, SLIP, CUT = 0.25, 0.25, "2016-06-30"


def walk(x, o, h, l, c, flat_bars, flat_px, be, hold):
    e, sd, lim, sl, tp = int(x["entry_bar"]), int(x["side"]), float(x["signal_close"]), float(x["ticket_sl"]), float(x["ticket_tp"])
    if not (l[e] <= lim - TICK if sd > 0 else h[e] >= lim + TICK):
        return None
    fill = min(o[e], lim) if sd > 0 else max(o[e], lim)
    risk = (fill - sl) * sd
    trig = fill + sd * be * risk if be > 0 and risk > 0 else None
    k = np.searchsorted(flat_bars, e)
    end = int(flat_bars[k]) if k < len(flat_bars) else len(c) - 1
    end_px = float(flat_px[k]) if k < len(flat_bars) else float(c[-1])
    stop = sl
    for j in range(e, end + 1):
        if hold > 0 and j == e + hold:
            return fill, float(o[j]), "market", j
        if j > e and ((o[j] <= stop) if sd > 0 else (o[j] >= stop)):
            return fill, float(o[j]), "market", j
        if (l[j] <= stop) if sd > 0 else (h[j] >= stop):
            return fill, stop, "market", j
        if j > e and ((o[j] >= tp + TICK) if sd > 0 else (o[j] <= tp - TICK)):
            return fill, float(o[j]), "limit", j
        if (h[j] >= tp + TICK) if sd > 0 else (l[j] <= tp - TICK):
            return fill, tp, "limit", j
        if trig is not None and ((h[j] >= trig) if sd > 0 else (l[j] <= trig)):
            stop = fill
    return fill, end_px, "market", end


def main():
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    rdoc, jdoc, jid = R.fetch(496, None)
    N = R.normalize(rdoc, jdoc, jid)
    rows = sorted([r for r in N["top"] if r.get("fold") is not None], key=lambda r: int(r["fold"]))
    spec = importlib.util.spec_from_file_location("ss11", S.F11)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    params = {k: rows[4][k] for k in mod.DEFAULT_PARAMS if k in rows[4]}
    params.update(intrabar="worst", close_rule="fifo", _detail=True)
    be, hold = float(params.get("be_trigger", 0) or 0), int(params.get("max_hold_bars", 0) or 0)
    print("be", be, "hold", hold, flush=True)
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    out, offered, days = [], 0, []
    for d0, d1 in S.PERIODS:
        a = load_master_arrays(m, date_from=d0, date_to=d1)
        dd = R.bar_dates(a["index"])
        days += list(dd.uniq)
        o, h, l, c = (np.asarray(a[k], float) for k in ("open", "high", "low", "close"))
        r = run_backtest(S.F11, arrays=a, master=m, params=dict(params), cost_pts=0.0, return_trades=True)
        td = (r or {}).get("trade_detail") or []
        fl = sorted({(int(x["exit_bar"]), float(x["exit_price"])) for x in td if x["exit_reason"] == "roll_flat"})
        fb, fp = np.array([f[0] for f in fl], int), np.array([f[1] for f in fl], float)
        for x in td:
            offered += 1
            w = walk(x, o, h, l, c, fb, fp, be, hold)
            if w:
                sd = int(x["side"])
                out.append(dict(xday=dd[w[3]], gross=(w[1] - w[0]) * sd, slip=SLIP if w[2] == "market" else 0.0))
        print(d0, len(td), len(out), flush=True)
        del a
    g = pd.DataFrame(out)
    g["xday"] = pd.to_datetime(g.xday)
    cal = pd.to_datetime(pd.Series(days)).drop_duplicates().sort_values()
    cal = pd.DatetimeIndex(cal[cal.dt.dayofweek < 5])
    res = dict(offered=offered, filled=len(g), market_exit_share=round(float((g.slip > 0).mean()), 3), gross_pt=round(float(g.gross.mean()), 3),
               trades_yr=round(len(g) / ((cal[-1] - cal[0]).days / 365.25), 1))
    edges = pd.date_range(cal[0], cal[-1] + pd.Timedelta(days=1), periods=9)
    for name, cost, extra in (("house", 0.783, 0), ("comm", 0.283, 0), ("real", 0.283, 1)):
        p = pd.DataFrame(dict(xday=g.xday, pts=g.gross - extra * g.slip - S.RUN_COST))
        rw = S.row(p, cal, cost, "pre-WF")
        net = (p.pts + S.RUN_COST - cost) * S.MULT
        rw["folds"] = [round(float(net[(p.xday >= edges[i]) & (p.xday < edges[i + 1])].sum())) for i in range(8)]
        rw["folds_pos"] = sum(f > 0 for f in rw["folds"])
        res[name] = rw
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print(json.dumps(res, default=str))
    print("DONE")


if __name__ == "__main__":
    main()
