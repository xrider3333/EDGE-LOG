"""
ROUND 63 - which ORB leg should BOOK #463 carry, judged on the owner yardstick? PRE-REGISTERED. (2026-09-30)

WHY. BOOK #463 (adopted 2026-09-28 as book #449) carries the ORB CONTROL #234 as its ORB leg, while the ORB
crown is #314 and the owner-starred money pick #257 now runs as a shadow paper leg. Round 53 (2026-09-09)
found #314 worse than #234 inside the then-adopted book, but that was a different book (the old NOISE and
TTM legs) and a different measure (return over drawdown, closed-trade drawdown). The owner's yardstick since
2026-09-28 is ROC %/yr at a $30k worst drawdown valued DAILY, walk-forward and lockbox read apart, with
Sortino. This re-asks the question on today's book and today's yardstick, changing ONLY the ORB leg.

WRITTEN BEFORE ANY NUMBER. The legs are #463's own, read from its job document; each variant replaces the
ORB leg's strategy/params only (same instrument, costs, weight). Each leg's daily-valued series comes from
the house book engine (augur_engine.book._leg_trades, the function run_book itself calls), so ENGU-Q's
multi-day holds are valued at every close. PARITY FIRST: the #463 legs as stored must reproduce #463's
closed-trade figures (pre-lockbox $1,358,771.79 / lockbox $273,608.73) or the round stops.

VARIANTS (ORB leg only): #234 as stored (the incumbent), #314 (crown), #257 (money pick, frozen cell),
#239 (control with breakeven 0.8).

STRETCHES. #463's lockbox is 2025-06-30 .. 2026-06-30 (12 months to its date_to). The walk-forward-like
stretch is 2016-07-13 .. 2025-06-29 (the family's walk-forward years, before that lockbox). The whole
pre-lockbox stretch 2010-06-07 .. 2025-06-29 is printed for context. NOTE: #463's lockbox has been read
(the book was adopted on it), so it is a veto here, not evidence.

PRE-REGISTERED BAR. A swap is recommended ONLY if the swapped book
  1. beats the incumbent's ROC at a $30k worst drawdown (daily-valued) on the WF-like stretch AND the lockbox;
  2. beats the incumbent's daily Sortino on both;
  3. is not behind the incumbent in total money by calendar year (2011-2025, the house rule for book changes).
Otherwise the book keeps #234. The recommendation is the owner's call either way.
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

WF = ("2016-07-13", "2025-06-29")
LB = ("2025-06-30", "2026-06-30")
PRE = ("2010-06-07", "2025-06-29")
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
            flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0, target_R=5.5,
            be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
SWAPS = {"#314 crown": dict(BASE, stop_frac=2.5, target_R=5.0, be_after_R=0.5, atr_filter=0.75, vpace_filter=0.8),
         "#257 money pick": dict(BASE, stop_frac=2.5, breakout_buf=0.30, atr_filter=0.5),
         "#239 breakeven 0.8": dict(BASE, be_after_R=0.8)}


def load_463():
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter as FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    d = list(u.collection("backtests").where(filter=FF("run_id", "==", 463)).limit(1).stream())[0].to_dict()
    return d["legs"], d["date_from"], d["date_to"]


def main():
    import numpy as np
    import pandas as pd
    from augur_engine import book as B

    legs, dfrom, dto = load_463()
    oi = [i for i, l in enumerate(legs) if str(l["strategy"]).startswith("ORB")]
    assert len(oi) == 1
    oi = oi[0]

    def series(pairs):
        s = pd.Series([float(a) for _, a in pairs], index=pd.to_datetime([str(d)[:10] for d, _ in pairs]))
        return s.groupby(level=0).sum().sort_index()

    closed, marked = [], []
    for leg in legs:
        tr, info = B._leg_trades(leg, dfrom, dto)
        m = info.get("_mtm_day")
        closed.append(series(tr))
        marked.append(series(m if m is not None else tr))
    lb0 = pd.Timestamp(LB[0])
    tot = pd.concat(closed, axis=1).fillna(0).sum(axis=1)
    pre, lbv = tot[tot.index < lb0].sum(), tot[tot.index >= lb0].sum()
    ok = abs(pre - 1358771.79) < 5 and abs(lbv - 273608.73) < 5
    print("PARITY vs #463 closed trades: pre $%.2f (stored $1,358,771.79) | lockbox $%.2f (stored $273,608.73) -> %s"
          % (pre, lbv, "EXACT" if ok else "MISMATCH - stop"), flush=True)
    if not ok:
        sys.exit(2)

    rest = pd.concat([m for i, m in enumerate(marked) if i != oi], axis=1).fillna(0).sum(axis=1)
    books = {"#234 incumbent (as stored)": rest.add(marked[oi], fill_value=0).sort_index()}
    for name, p in SWAPS.items():
        leg = dict(legs[oi], strategy="ORB_3_6.py", params=p)
        tr, info = B._leg_trades(leg, dfrom, dto)
        books[name] = rest.add(series(tr), fill_value=0).sort_index()

    def score(s, lo, hi):
        z = s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
        cum = z.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = (pd.Timestamp(hi) - pd.Timestamp(lo)).days / 365.25
        neg = z[z < 0]
        return 30.0 * (z.sum() / yrs) / dd, float(z.mean() / np.sqrt((neg ** 2).sum() / len(z)) * np.sqrt(252)), z.sum(), dd

    inc = books["#234 incumbent (as stored)"]
    inc_sc = {k: score(inc, *w) for k, w in (("WF", WF), ("LB", LB), ("PRE", PRE))}
    inc_y = inc.groupby(inc.index.year).sum()
    for name, s in books.items():
        sc = {k: score(s, *w) for k, w in (("WF", WF), ("LB", LB), ("PRE", PRE))}
        y = s.groupby(s.index.year).sum()
        dy = (y - inc_y).reindex(range(2011, 2026)).fillna(0)
        print("\n%s" % name)
        for k in ("WF", "LB", "PRE"):
            print("  %-3s ROC@$30k %6.1f%%/yr  Sortino %5.2f  net $%10.0f  daily-valued DD $%7.0f"
                  % ((k,) + sc[k]))
        if name.startswith("#234"):
            continue
        bars = [sc["WF"][0] > inc_sc["WF"][0] and sc["LB"][0] > inc_sc["LB"][0],
                sc["WF"][1] > inc_sc["WF"][1] and sc["LB"][1] > inc_sc["LB"][1],
                dy.sum() >= 0]
        print("  vs incumbent by calendar year 2011-2025: $%+.0f, %d of 15 years better"
              % (dy.sum(), int((dy > 0).sum())))
        print("  BAR: ROC both %s | Sortino both %s | calendar years %s -> %s"
              % tuple(["PASS" if b else "FAIL" for b in bars] + ["RECOMMEND SWAP (owner call)" if all(bars)
                                                                 else "KEEP #234"]))


if __name__ == "__main__":
    main()
