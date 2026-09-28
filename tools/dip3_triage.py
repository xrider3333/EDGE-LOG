"""
DIP ROUND 3 TRIAGE (2026-09-28) - pre-registered in docs/DIP_ROUND3.md (commit 58578494) before any number.

Cells on the frozen champions of #452 (NQDIP_1_3 on ES) and #433 (NQDIP_1_2 on NQ), true rolls, db_noadj_rth:
  RAW; CAP1 / CAP2 (at most 1 / 2 open positions across all legs, applied to the trade list in entry order);
  TBX (trend-break exit: a trade in a trend-filtered leg exits at the next open after a close below the trend
  SMA; the capitulation leg has no trend premise and is exempt); CAP1+TBX; CAP2+TBX.
Yardstick (owner rule 2026-09-28): ROC %/yr at a $30k worst drawdown = 30 x (net per year) / worst drawdown,
drawdown valued DAILY; WF (entries 2016-07-18..2025-08-22) and LB (entries 2025-08-24..2026-08-24) apart;
daily Sortino; >= 100 WF / >= 50 LB trades; LB net > 0 without its biggest trade.
    python tools/dip3_triage.py
"""
import importlib.util, os, sys
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED); sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
WF = ("2016-07-18", "2025-08-22"); LB = ("2025-08-24", "2026-08-24")
LEGS = [("RSI", "use_rsi"), ("DBL", "use_dbl"), ("PB", "use_pb"), ("CAP", "use_cap"),
        ("IBS", "use_ibs"), ("STREAK", "use_streak"), ("GAPDN", "use_gapdn")]
CELLS = [("RAW", 0, False), ("CAP1", 1, False), ("CAP2", 2, False), ("TBX", 0, True),
         ("CAP1+TBX", 1, True), ("CAP2+TBX", 2, True)]


def run_doc(rid):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    return firestore.client().collection("users").document(UID).collection("runs").document(str(rid)).get().to_dict()


class Market:
    def __init__(self, rid):
        D = run_doc(rid); self.rid = rid; self.D = D
        sp = importlib.util.spec_from_file_location("m%s" % rid, os.path.join("augur_strategies", D["strategy"]))
        m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); self.m = m
        A = load_master_arrays(find_master(D["instrument"], "5m", "rth", "db_noadj_rth"),
                               date_from=D["date_from"], date_to=D["date_to"])
        self.o, self.h, self.l, self.c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
        self.did, self.idx = np.asarray(A["day_id"]), pd.DatetimeIndex(A["index"])
        self.P = dict(D["best_params"])
        oa, ha, la, ca, ev = m.roll_adjust(self.o, self.h, self.l, self.c, self.idx)
        self.rb = np.array([b for b, _ in ev])
        self.bounds = m._session_bounds(self.did, len(self.c))
        self.open_bar = np.array([a for a, b in self.bounds])
        self.doa = np.array([oa[a] for a, b in self.bounds]); self.dca = np.array([ca[b - 1] for a, b in self.bounds])
        self.day = pd.DatetimeIndex([self.idx[a] for a, b in self.bounds]).tz_localize(None).normalize()
        self.trend = pd.Series(self.dca).rolling(int(self.P["trend_len"])).mean().values
        self.sess = {int(a): j for j, (a, b) in enumerate(self.bounds)}
        self.trades = []                                   # (leg, de, dx, entry_px)
        for leg, flag in LEGS:
            if not self.P.get(flag, False) and flag in self.P:
                continue
            if flag not in self.P:
                continue
            p = dict(self.P); p.update({f: (f == flag) for _, f in LEGS if f in self.P})
            r = self.m.run_backtest(self.o, self.h, self.l, self.c, day_id=self.did, index=self.idx,
                                    return_trades=True, **p)
            for t in (r or {}).get("trades") or []:
                self.trades.append((leg, self.sess[int(t[0])], self.sess[int(t[1])], float(t[4])))
        full = self.m.run_backtest(self.o, self.h, self.l, self.c, day_id=self.did, index=self.idx,
                                   return_trades=True, **self.P)
        self.full_n, self.full_net = full["num_trades"], full["total_pnl"]

    def pnl(self, de, dx, ep):
        dpp = 2.0 * max(1, int(round(float(self.P.get("notional", 100000)) / (ep * 2.0))))
        cross = int(((self.rb > self.open_bar[de]) & (self.rb <= self.open_bar[dx])).sum())
        return dpp, (self.doa[dx] - self.doa[de]) * dpp - float(self.P.get("cost_pts_rt", 0.783)) * dpp - 0.25 * dpp * cross

    def cell(self, cap, tbx):
        tr = []
        for leg, de, dx, ep in self.trades:
            if tbx and leg != "CAP":
                for j in range(de, dx):
                    if not np.isnan(self.trend[j]) and self.dca[j] < self.trend[j]:
                        dx = min(dx, j + 1); break
            tr.append((de, dx, ep))
        tr.sort(key=lambda t: (t[0], t[1]))
        if cap:
            kept, open_x = [], []
            for de, dx, ep in tr:
                open_x = [x for x in open_x if x > de]
                if len(open_x) < cap:
                    kept.append((de, dx, ep)); open_x.append(dx)
            tr = kept
        return tr

    def stretch(self, tr, a, b):
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        sel = [t for t in tr if a <= self.day[t[0]] <= b]
        n = len(self.bounds); eq = np.zeros(n); nets = []
        for de, dx, ep in sel:
            dpp, p = self.pnl(de, dx, ep); nets.append(p)
            eq[de:dx] += (self.dca[de:dx] - self.doa[de]) * dpp
            eq[dx:] += p
        k = (self.day >= a) & (self.day <= b + pd.Timedelta(days=400))
        k &= np.arange(n) <= max([t[1] for t in sel], default=0)
        k &= self.day >= a
        e = eq[k]
        if len(e) == 0:
            return dict(n=0)
        e = np.concatenate([[0.0], e])
        dd = float((np.maximum.accumulate(e) - e).max())
        yrs = max((min(b, self.day[-1]) - a).days / 365.25, 0.25)
        net = float(sum(nets))
        r = np.diff(e) / 100000.0; dn = np.sqrt(np.mean(np.minimum(r, 0) ** 2))
        return dict(n=len(sel), net=net, dd=dd, roc30=30.0 * (net / yrs) / dd if dd > 0 else float("nan"),
                    sortino=float(r.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan"),
                    ex_top=net - max(nets) if nets else 0.0)

    def whole_dd(self, tr):
        s = self.stretch(tr, self.day[0].strftime("%Y-%m-%d"), self.day[-1].strftime("%Y-%m-%d"))
        return s["dd"], s["net"], s["n"]


if __name__ == "__main__":
    out = {}
    for rid in (452, 433):
        M = Market(rid)
        raw = M.cell(0, False)
        _dd, _net, _n = M.whole_dd(raw)
        print("\n#%d %s on %s | leg-split parity: %d trades $%s vs file %d trades $%s | whole DD daily $%s"
              % (rid, M.D["strategy"], M.D["instrument"], _n, f"{_net:,.0f}", M.full_n, f"{M.full_net:,.0f}", f"{_dd:,.0f}"))
        print("  %-9s | %-44s | %-44s | whole DD" % ("cell", "WF: trades  ROC@30k  Sortino", "LB: trades  ROC@30k  Sortino  ex-top $"))
        res = {}
        for name, cap, tbx in CELLS:
            tr = M.cell(cap, tbx)
            w, l = M.stretch(tr, *WF), M.stretch(tr, *LB)
            wdd = M.whole_dd(tr)[0]
            res[name] = (w, l, wdd)
            print("  %-9s | %5d  %7.1f  %6.2f  (net $%9s DD $%7s) | %4d  %7.1f  %6.2f  %9s | $%s"
                  % (name, w["n"], w["roc30"], w["sortino"], f"{w['net']:,.0f}", f"{w['dd']:,.0f}",
                     l["n"], l["roc30"], l["sortino"], f"{l['ex_top']:,.0f}", f"{wdd:,.0f}"))
        out[rid] = res
    print("\nVERDICTS (docs/DIP_ROUND3.md: must beat RAW on ROC@30k and Sortino in WF and LB on BOTH markets,"
          " >=100 WF / >=50 LB trades, LB > 0 without its biggest trade)")
    for name, _, _ in CELLS[1:]:
        ok = True; why = []
        for rid in (452, 433):
            (w, l, _), (w0, l0, _) = out[rid][name], out[rid]["RAW"]
            checks = {"WF ROC": w["roc30"] > w0["roc30"], "LB ROC": l["roc30"] > l0["roc30"],
                      "WF Sortino": w["sortino"] > w0["sortino"], "LB Sortino": l["sortino"] > l0["sortino"],
                      "WF n": w["n"] >= 100, "LB n": l["n"] >= 50, "LB ex-top": l["ex_top"] > 0}
            bad = [k for k, v in checks.items() if not v]
            if bad:
                ok = False; why.append("#%d fails %s" % (rid, ", ".join(bad)))
        print("  %-9s %s" % (name, "SURVIVES" if ok else "dead - " + "; ".join(why)))
