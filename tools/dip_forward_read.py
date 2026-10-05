"""
DIP FORWARD READ (docs/DIP_FORWARD.md + addendum A) - the two no-order paper shadows DIP_ES_452 / DIP_NQ_433, live from
2026-10-05. Rebuilds each shadow exactly as the nightly paper run does (same file, same frozen params from api/paper.py,
same no-adjust master and full history), keeps the trades ENTERED on/after the live date, values open ones at every
session close with the file's own mark_open_trades, and:
  - before the judging point prints COUNTS ONLY (closed trades / sessions live) - no P&L, so nobody reads the forward
    stretch early;
  - at the FIRST of 50 closed trades or 9 months after the live date, prints the four-point bar per market:
      1. ROC %/yr at a $30k worst drawdown (valued daily) >= half the walk-forward figure (ES 6.6, NQ 13.5)
      2. daily Sortino > 0.5        3. net > 0 without the single biggest trade
      4. worst daily-valued drawdown no deeper than the walk-forward's (ES $71,941, NQ $53,267)
    plus addendum A (the drawdown-week seat measurement) when the forward book's daily file exists.
The DIP files return CLOSED trades only - a position still open at the read is not in the list until it exits (the
paper board shows it as an open mark); the bar is read on closed trades valued daily, as the backtest was.
--firestore also counts the leg's non-backfill paper_trades docs (a few reads by query) as a parity check.

    python tools/dip_forward_read.py [--asof YYYY-MM-DD] [--firestore]
"""
import argparse, importlib.util, os, sys
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
FORWARD_BOOK = r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4\book463_forward_daily.csv"   # date,pnl - the paper lanes' file
LEGS = {"DIP_ES_452": dict(bar_roc=6.6, bar_dd=71941.0), "DIP_NQ_433": dict(bar_roc=13.5, bar_dd=53267.0)}
JUDGE_TRADES, JUDGE_MONTHS, DD_EPISODE = 50, 9, 14950.0


def yard(daily):
    d = daily.sort_index(); eq = np.concatenate([[0.0], d.values.cumsum()])
    dd = float((np.maximum.accumulate(eq) - eq).max()); yrs = max((d.index[-1] - d.index[0]).days / 365.25, 1 / 365.25)
    net = float(d.sum()); neg = np.minimum(d.values, 0.0); rms = float(np.sqrt(np.mean(neg ** 2)))
    return dict(net=net, dd=dd, roc30=30.0 * (net / yrs) / dd if dd > 0 else float("nan"),
                sortino=float(d.values.mean() / rms * np.sqrt(252)) if rms > 0 else float("nan"))


def dd_days(daily):
    d = daily.sort_index(); eq = d.values.cumsum(); out = []; peak, pi, j, n = 0.0, -1, 0, len(eq)
    while j < n:
        if eq[j] >= peak:
            peak, pi = eq[j], j; j += 1; continue
        k = j
        while k < n and eq[k] < peak:
            k += 1
        t = j + int(np.argmin(eq[j:k]))
        if peak - eq[t] >= DD_EPISODE:
            out.extend(d.index[pi + 1: t + 1])
        j = k
    return pd.DatetimeIndex(out)


def forward(leg, live_from, asof=None):
    """(closed trades df, daily valued P&L series) for trades entered on/after live_from, through asof."""
    from api import paper as P
    from augur_engine.data import find_master, load_master_arrays
    spec = next(l for l in P.PAPER_LEGS if l["key"] == leg)
    sp = importlib.util.spec_from_file_location(leg, os.path.join(SHARED, "augur_strategies", spec["strategy"]))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    A = load_master_arrays(find_master(spec["instrument"], spec["timeframe"], spec.get("session", "rth")),
                           date_from=spec.get("history_from"), date_to=asof)
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    did, idx = np.asarray(A["day_id"]), pd.DatetimeIndex(A["index"])
    r = m.run_backtest(o, h, l, c, day_id=did, index=idx, return_trades=True, **spec["params"])
    tr = (r or {}).get("trades") or []
    marks = m.mark_open_trades(tr, o, h, l, c, day_id=did, index=idx, **spec["params"])
    bounds = m._session_bounds(did, len(c)); close_bar = np.array([b - 1 for a, b in bounds])
    day = pd.DatetimeIndex([idx[b - 1] for a, b in bounds]).tz_localize(None).normalize()
    lf = pd.Timestamp(live_from)
    sess_of = np.searchsorted(close_bar, np.arange(len(c)))
    pos = {int(b): j for j, b in enumerate(close_bar)}
    closed = np.zeros(len(bounds)); openv = np.zeros(len(bounds)); rows = []
    for t, mk in zip(tr, marks or [None] * len(tr)):
        ent_day = day[sess_of[int(t[0])]]
        if ent_day < lf:
            continue
        rows.append(dict(entry=ent_day, exit=day[sess_of[int(t[1])]], pnl=float(t[2])))
        closed[sess_of[int(t[1])]:] += float(t[2])
        for bar, v in (mk or []):
            if int(bar) in pos:
                openv[pos[int(bar)]] += v
    eq = pd.Series(closed + openv, index=day)
    eq = eq[eq.index >= lf]
    daily = eq.diff().fillna(eq.iloc[0] if len(eq) else 0.0)
    return pd.DataFrame(rows, columns=["entry", "exit", "pnl"]), daily


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--asof"); ap.add_argument("--firestore", action="store_true")
    a = ap.parse_args(argv)
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from api import paper as P
    for leg, bar in LEGS.items():
        lf = P.LEG_LIVE_FROM[leg]
        T, daily = forward(leg, lf, a.asof)
        n_closed = len(T)
        days = int((daily.index >= pd.Timestamp(lf)).sum())
        due_by_time = pd.Timestamp(a.asof or pd.Timestamp.now().normalize()) >= pd.Timestamp(lf) + pd.DateOffset(months=JUDGE_MONTHS)
        due = n_closed >= JUDGE_TRADES or due_by_time
        print("%s (live from %s): %d sessions live, %d closed trades - %s"
              % (leg, lf, days, n_closed, "JUDGE NOW" if due else "counts only until %d closed trades or %s"
                 % (JUDGE_TRADES, (pd.Timestamp(lf) + pd.DateOffset(months=JUDGE_MONTHS)).date())))
        if a.firestore:
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(os.path.join(SHARED, "serviceAccount.json")))
            uid = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
            docs = list(firestore.client().collection("users").document(uid).collection("paper_trades")
                        .where("leg", "==", leg).stream())
            fwd = [d.to_dict() for d in docs if not (d.to_dict() or {}).get("backfill")]
            print("   Firestore paper_trades (non-backfill): %d docs vs rebuilt %d trades" % (len(fwd), len(T)))
        if not due or len(daily) < 2:
            continue
        y = yard(daily); nets = T["pnl"].values
        ex_top = float(nets.sum() - nets.max()) if len(nets) else 0.0
        chk = {"1 ROC@30k >= %.1f" % bar["bar_roc"]: y["roc30"] >= bar["bar_roc"], "2 Sortino > 0.5": y["sortino"] > 0.5,
               "3 net ex biggest > 0": ex_top > 0, "4 DD <= $%s" % f"{bar['bar_dd']:,.0f}": y["dd"] <= bar["bar_dd"]}
        print("   ROC@30k %.1f  Sortino %.2f  net $%s  ex-top $%s  DD $%s  -> %s" % (
            y["roc30"], y["sortino"], f"{y['net']:,.0f}", f"{ex_top:,.0f}", f"{y['dd']:,.0f}",
            "CLEARS the bar" if all(chk.values()) else "fails " + ", ".join(k for k, v in chk.items() if not v)))
        if not os.path.exists(FORWARD_BOOK):
            print("   addendum A: forward book file %s not found - the seat measurement waits for it" % FORWARD_BOOK)
            continue
        fb = pd.read_csv(FORWARD_BOOK, parse_dates=["date"]).set_index("date")["pnl"]
        fb = fb[fb.index >= pd.Timestamp(lf)]
        ddd = dd_days(fb)
        if not len(ddd):
            print("   addendum A: the forward book never fell $%s - UNREADABLE (map rule); seat question waits" % f"{DD_EPISODE:,.0f}")
            continue
        x = daily.reindex(ddd).fillna(0.0)
        print("   addendum A: %d forward-book drawdown days; shadow P&L there $%s; daily corr with the book there %.2f"
              % (len(ddd), f"{x.sum():,.0f}", float(np.corrcoef(x, fb.reindex(ddd).fillna(0.0))[0, 1]) if len(ddd) > 2 else float("nan")))


if __name__ == "__main__":
    main()
