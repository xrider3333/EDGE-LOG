"""
DIP DRAWDOWNS VALUED DAILY (2026-09-28, MANAGER inbox #13).

A validate's drawdown (whole run, lockbox) is built from CLOSED trades in exit order, so a multi-day DIP hold
that sinks and recovers never shows its open loss - the same blind spot the books had for ENGU-Q (v73.899).
This re-runs each DIP run's champion with its own strategy file on its own master and window, values every
open trade at every session close with the file's mark_open_trades() hook, and reports the drawdown both
ways for the whole run and for the lockbox (trades entered on/after the lockbox start).
    python tools/dip_mtm_restate.py 452 432 433 434
"""
import importlib.util, os, sys
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED); sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def runs(ids):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    return {s.id: s.to_dict() for s in firestore.client().get_all([u.collection("runs").document(str(i)) for i in ids])}


def dd(x):
    x = np.asarray(x, float)
    return float((np.maximum.accumulate(np.concatenate([[0.0], x]))[1:] - x).max()) if len(x) else 0.0


def restate(D):
    sp = importlib.util.spec_from_file_location("m", os.path.join("augur_strategies", D["strategy"]))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    A = load_master_arrays(find_master(D["instrument"], D["timeframe"], "rth", D["data_source"]),
                           date_from=D["date_from"], date_to=D["date_to"])
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    did, idx = np.asarray(A["day_id"]), pd.DatetimeIndex(A["index"])
    P = dict(D["best_params"])
    r = m.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True, **P)
    tr = r["trades"]; marks = m.mark_open_trades(tr, o, h, l, c, day_id=did, index=idx, **P)
    bounds = m._session_bounds(did, len(c)); close_bar = np.array([b - 1 for a, b in bounds])
    lb0 = pd.Timestamp(D["validate"]["windows"]["lockbox"][0], tz=idx.tz)

    def curves(sel):
        closed = np.zeros(len(bounds)); openv = np.zeros(len(bounds))
        pos = {int(b): j for j, b in enumerate(close_bar)}
        bar_sess = np.searchsorted(close_bar, np.arange(len(c)))       # session of any bar
        for t, mk in zip(tr, marks):
            if not sel(t):
                continue
            closed[bar_sess[int(t[1])]:] += t[2]                        # realised on its exit session
            for bar, v in (mk or []):
                openv[pos[int(bar)]] += v
        return closed, closed + openv
    c_all, m_all = curves(lambda t: True)
    c_lb, m_lb = curves(lambda t: idx[int(t[0])] >= lb0)
    keep = np.array([idx[a] >= lb0 for a, b in bounds])
    return dict(n=len(tr), net=r["total_pnl"], dd_closed=dd(c_all), dd_daily=dd(m_all),
                lb_closed=dd(c_lb[keep]), lb_daily=dd(m_lb[keep]), stored_dd=abs(D["validate"]["total_dd"]),
                stored_lb=(D["validate"].get("lockbox") or {}).get("dd"))


if __name__ == "__main__":
    ids = sys.argv[1:] or ["452", "432", "433", "434"]
    R = runs(ids)
    for i in ids:
        D = R[str(i)]; x = restate(D)
        print("#%s %s on %s: %d trades, net $%s | WHOLE DD closed $%s (stored $%s) -> valued daily $%s (x%.2f)"
              " | LOCKBOX DD closed $%s (stored $%s) -> daily $%s (x%.2f)"
              % (i, D["strategy"], D["instrument"], x["n"], f"{x['net']:,.0f}", f"{x['dd_closed']:,.0f}",
                 f"{x['stored_dd']:,.0f}", f"{x['dd_daily']:,.0f}", x["dd_daily"] / max(x["dd_closed"], 1),
                 f"{x['lb_closed']:,.0f}", f"{(x['stored_lb'] or 0):,.0f}", f"{x['lb_daily']:,.0f}",
                 x["lb_daily"] / max(x["lb_closed"], 1)), flush=True)
