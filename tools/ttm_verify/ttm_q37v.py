"""TTM (house verifier, MANAGER #89 / #108): BLIND re-check of Q37's QQQ arm - DIP #424 on QQQ 5m prints, the leg that
runs LIVE on Webull as DIP_424F (fixed 1.245x) since 2026-10-13. Built from the pre-data note
docs/PREDATA_frontier_dipqqq_2026-10-09.txt and the strategy file only; q37_dip_qqq.py / q37_dip_qqq.json are NOT read
until this script's output sha256 is posted. Prereg: prereg/ttm-verify-q37 (docs/PREREG_TTM_VERIFY_Q37_2026-10-14.txt).

Own path (not Q37's r28 decompose()): the engine's run_backtest on the pinned master with api/cloud_signal.DIP_424_PARAMS
+ asset "ETF"; $ booked on each trade's EXIT session, zero days kept; my own ROC / Sortino code, the house's dd5 /
dd_pct_peak. NQ arm = the PURE roll-restated list (pinned sha), same booking, same window.
Read-only: writes only into C:/EdgeLog/_anatomy_cache/ttm_q37v/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_q37v"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import load_master_arrays           # noqa: E402
from augur_engine.engine import run_backtest               # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak         # noqa: E402
from api import cloud_signal as CS                          # noqa: E402

MASTER = "master_ac263357.csv"
PIN_MASTER = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
PURE = "C:/EdgeLog/_anatomy_cache/restate_roll/dip424_pure_trades.csv"
PIN_PURE = "ce5750975ed07ca935c4e602d037ddf8c95916f07ed44da874ad1c101a1e46e0"
END = pd.Timestamp("2025-08-24")
F_SIZE = CS.DIP_424_CONST_SIZE          # 1.245
REAL_PER_SHARE_RT = 0.02                # owner rule: commission ($0 on Webull) + 1 tick ($0.01) each side
SORT_DAYS = 252.0


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def stats(x, days):
    """x = daily $ on `days` (zero days kept)."""
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    net = float(x.sum())
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net": net, "per_yr": net / yrs, "years": yrs, "max_dd": mdd, "roc30": 30.0 * (net / yrs) / mdd,
            "dd5": float(r["dd5_usd"]), "one_episode": bool(r["one_episode"]),
            "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(SORT_DAYS)) if down > 0 else float("nan")}


def daily(exit_days, pnl, days):
    return pd.Series(np.asarray(pnl, float), index=pd.DatetimeIndex(exit_days)).groupby(level=0).sum() \
        .reindex(days, fill_value=0.0).to_numpy()


def main():
    mp = os.path.join(REPO, "augur_uploads", MASTER)
    assert sha(mp) == PIN_MASTER, "QQQ master pin"
    assert sha(PURE) == PIN_PURE, "PURE list pin"
    fp = os.path.join(REPO, "augur_strategies", "NQDIP_1_1.py")
    print("NQDIP_1_1.py sha256", sha(fp))
    A = load_master_arrays({"filename": MASTER})
    idx = pd.DatetimeIndex(A["index"])
    sessions = pd.DatetimeIndex(sorted(set(idx.tz_localize(None).normalize())))
    m = types.ModuleType("ttm_q37v_dip")
    m.__file__ = fp
    exec(compile(open(fp, encoding="utf-8").read(), fp, "exec"), m.__dict__)
    P = dict(CS.DIP_424_PARAMS)
    P["asset"] = "ETF"
    print("params", json.dumps(P, sort_keys=True))
    r = run_backtest(m, instrument="QQQ", arrays=A, params=P, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    eb = np.array([t[0] for t in T]); xb = np.array([t[1] for t in T])
    pnl = np.array([t[2] for t in T], float); epx = np.array([t[4] for t in T], float)
    ent = idx[eb].tz_localize(None); ext = idx[xb].tz_localize(None)
    print("QQQ trades (whole master): %d, first entry %s, last exit %s" % (len(T), ent.min(), ext.max()))
    first = ent.min().normalize()
    keep = np.asarray(ext.normalize() <= END)
    days = sessions[(sessions >= first) & (sessions <= END)]
    ex_d = ext.normalize()[keep]
    shares = P["notional"] / epx[keep]
    house = pnl[keep]
    real = house + P["notional"] * P["cost_bps"] / 1e4 - REAL_PER_SHARE_RT * shares
    res = {"window": [str(first.date()), str(END.date())], "n_sessions": len(days),
           "qqq_trades_in_window": int(keep.sum()), "qqq_trades_entry_in_but_exit_after": int(((ent.normalize() <= END) & ~keep).sum()),
           "real_cost_per_trade_mean": float((REAL_PER_SHARE_RT * shares).mean())}
    for nm, v, sz in (("QQQ RAW house (2 bp RT)", house, 1.0), ("QQQ F 1.245x house", house, F_SIZE),
                      ("QQQ RAW real (1 tick each side)", real, 1.0), ("QQQ F 1.245x real", real, F_SIZE)):
        res[nm] = stats(daily(ex_d, v * sz, days), days)
    N = pd.read_csv(PURE, parse_dates=["entry", "exit"])
    nk = (N.exit.dt.normalize() >= first) & (N.exit.dt.normalize() <= END) & (N.entry.dt.normalize() >= first)
    res["nq_trades_in_window"] = int(nk.sum())
    nd = N.exit.dt.normalize()[nk]
    nq_days = days   # same session calendar (QQQ RTH); NQ exit days off it are reported
    res["nq_exit_days_off_calendar"] = int((~pd.Index(nd).isin(nq_days)).sum())
    res["NQ RAW (PURE list)"] = stats(daily(nd, N.pnl[nk], nq_days), nq_days)
    res["QQQ $ / NQ $ a year"] = res["QQQ RAW house (2 bp RT)"]["per_yr"] / res["NQ RAW (PURE list)"]["per_yr"]
    s = json.dumps(res, indent=1, sort_keys=True)
    print(s)
    open(os.path.join(OUT, "ttm_q37v.json"), "w", encoding="utf-8", newline="\n").write(s + "\n")
    print("output sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


if __name__ == "__main__":
    main()
