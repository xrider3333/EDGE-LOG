"""
ORB expiry-week ("roll week") size tilt - FORWARD READ scorer (pre-registered 2026-10-04, MANAGER GO #32).
Rule: docs/PREREG_orb_rollweek_forward_2026-10-04.md. Written before the first calendar-E week (2026-12-14..18).

    python tools/orb_rollweek_forward.py              counts; the paired stop at each look; the final rule when due
    python tools/orb_rollweek_forward.py --selftest   synthetic trades only (no market data is read)

Calendar E = the Monday-Friday week holding the third Friday of Mar / Jun / Sep / Dec. Arm = crown #314's trades
(the ORB_R6 rules, regenerated on the house NQ 5m master as tools/orb_orderflow_shadow.py does) at 1.5x inside E,
1x outside; twin = the same trades at 1x. Forward trades = entries on or after 2026-10-05.

MANAGER condition 1: NO backtest number on this calendar, ever - the trade window starts at FORWARD_FROM and nothing
earlier is scored. Until the first look (20 calendar-E trades) the scorer prints COUNTS ONLY. The reported-only lines
(calendar R; the same rule on #234 / #257 / #239) print only at the final read, so the #239 shadow stays unpeeked.
Run from the shared checkout (BACKTEST_SPEED rule 3: worktrees have no master registry).
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
FN = "augur_strategies/ORB_3_6.py"
COST, MULT = 0.533, 20.0
FORWARD_FROM, FINAL_N, FINAL_DATE = "2026-10-05", 50, "2031-12-31"
ARM, NULL_REPS, NULL_PCT, SEED = 1.5, 1000, 98.3, 20261004
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
            flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0, target_R=5.5,
            be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)                       # #234
LEGS = {"#314 (ORB_R6, the test)": dict(BASE, stop_frac=2.5, target_R=5.0, be_after_R=0.5, atr_filter=0.75,
                                         vpace_filter=0.8),
        "#234 (reported only)": dict(BASE),
        "#257 (reported only)": dict(BASE, stop_frac=2.5, breakout_buf=0.30, atr_filter=0.5),
        "#239 (reported only)": dict(BASE, be_after_R=0.8)}


def third_friday(y, m):
    import datetime as dt
    d = dt.date(y, m, 15)                                  # the third Friday is the first Friday on or after the 15th
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def calendar_e(days):
    """True for sessions in the Monday-Friday week holding a quarterly third Friday."""
    import datetime as dt
    weeks = set()
    for y in range(min(days).year, max(days).year + 1):
        for m in (3, 6, 9, 12):
            f = third_friday(y, m)
            weeks.add(f - dt.timedelta(days=4))            # that week's Monday
    return [d.weekday() < 5 and (d - dt.timedelta(days=d.weekday())) in weeks for d in days]


def calendar_r(days, sessions):
    """REPORTED ONLY: the five sessions after the CME roll Thursday (8 calendar days before the third Friday)."""
    import datetime as dt
    out = set()
    ss = sorted(sessions)
    for y in range(min(days).year, max(days).year + 1):
        for m in (3, 6, 9, 12):
            thu = third_friday(y, m) - dt.timedelta(days=8)
            after = [s for s in ss if s > thu][:5]
            out.update(after)
    return [d in out for d in days]


def null_s(T, sessions, rng, reps=NULL_REPS):
    """S for random calendars of the same shape: one random 5-session block per calendar quarter, placed uniformly
    among that quarter's sessions, scored on the same forward trades."""
    import numpy as np
    by_q = {}
    for s in sorted(sessions):
        by_q.setdefault((s.year, (s.month - 1) // 3), []).append(s)
    days = T.day.values
    out = []
    for _ in range(reps):
        cal = set()
        for q in by_q.values():
            if len(q) >= 5:
                k = int(rng.integers(0, len(q) - 4))
                cal.update(q[k:k + 5])
        inside = np.array([d in cal for d in days])
        if inside.any() and (~inside).any():
            out.append(T.u.values[inside].mean() - T.u.values[~inside].mean())
    return np.array(out)


def score(T, sessions, final, rng, lead=True):
    """T: forward trades of one leg (day, u, inE) sorted by entry. Prints the stop / final rule. Returns a dict."""
    import numpy as np
    import pandas as pd
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from paired_seq_stop import tstat, FIRST, EVERY, BOUND, BOUND_EX
    nE = int(T.inE.sum())
    m = np.where(T.inE, ARM, 1.0)
    u = T.u.values
    res = dict(nE=nE, status="counts only")
    if lead and nE >= FIRST:
        cumE = np.cumsum(T.inE.values)
        status = "continue"
        for k in range(FIRST, nE + 1, EVERY):
            n = int(np.searchsorted(cumE, k) + 1)          # all forward trades through the k-th calendar-E trade
            x = (m[:n] - m[:n].mean()) * u[:n]             # c = the running mean size (house paired stop)
            t = tstat(x)
            if t <= -BOUND and tstat(np.delete(x, int(np.argmin(x)))) <= -BOUND_EX:
                status = "EARLY FAIL at %d calendar-E trades (t %.2f)" % (k, t)
                break
            if t >= BOUND and tstat(np.delete(x, int(np.argmax(x)))) >= BOUND_EX:
                status = "EARLY PASS at %d calendar-E trades (t %.2f) - read the final rule now" % (k, t)
                final = True
                break
            status = "continue (look at %d calendar-E trades, t %.2f)" % (k, t)
        res["status"] = status
        print("  PAIRED SEQUENTIAL STOP: %s" % status)
    if not final:
        return res
    inE = T.inE.values
    S = u[inE].mean() - u[~inE].mean() if inE.any() and (~inE).any() else float("nan")
    nul = null_s(T, sessions, rng)
    p_cut = float(np.percentile(nul, NULL_PCT)) if len(nul) else float("inf")
    d = (m - m.mean()) * u
    arm, twin = pd.Series(m * u, index=T.day), pd.Series(u, index=T.day)

    def roc_sor(s):
        s = s.groupby(level=0).sum().reindex(sorted(sessions), fill_value=0.0)   # valued daily, every session
        cum = s.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = max((s.index[-1] - s.index[0]).days / 365.25, 1 / 12)
        neg = s[s < 0]
        sor = s.mean() / np.sqrt((neg ** 2).sum() / len(s)) * np.sqrt(252) if len(neg) else np.inf
        return (30.0 * (s.sum() / yrs) / dd if dd > 0 else np.inf), sor

    (ra, sa), (rt, st) = roc_sor(arm), roc_sor(twin)
    gain = (m - 1.0) * u                                   # nonzero on calendar-E trades only
    gE = gain[inE]
    ex_top = gain.sum() - (gE.max() if len(gE) else 0.0)
    yr = pd.Series(gain, index=pd.DatetimeIndex(T.day).year)
    nyE = pd.Series(inE.astype(int), index=yr.index).groupby(level=0).sum()
    yrs_ok = nyE[nyE >= 5].index
    breadth = float((yr.groupby(level=0).sum().reindex(yrs_ok) > 0).mean()) if len(yrs_ok) else float("nan")
    rules = {"1 calendar null": S > p_cut,
             "2 paired t": d.mean() > 0 and tstat(d) >= 1.645,
             "3 ROC and Sortino": ra > rt and sa >= st,
             "4 ex biggest E trade": ex_top > 0,
             "5 breadth 60%": breadth >= 0.6 if breadth == breadth else False}
    print("  S (mean $ in E - mean $ outside) %+.1f vs null %.1f pct %+.1f | paired d mean %+.1f t %.2f"
          % (S, NULL_PCT, p_cut, d.mean(), tstat(d)))
    print("  arm ROC@$30k %.1f Sortino %.2f vs twin %.1f / %.2f | gain ex biggest E trade $%+.0f | breadth %.2f over %d years"
          % (ra, sa, rt, st, ex_top, breadth, len(yrs_ok)))
    print("  FINAL RULE: %s  (%s)" % ("PASS" if all(rules.values()) else "FAIL",
                                       " | ".join("%s %s" % (k, "ok" if v else "no") for k, v in rules.items())))
    res.update(S=S, cut=p_cut, rules=rules, passed=all(rules.values()))
    return res


def main():
    import numpy as np
    import pandas as pd
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays

    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2025-06-01", date_to=None)
    idx = pd.DatetimeIndex(A["index"])
    lo = pd.Timestamp(FORWARD_FROM, tz=idx.tz)
    sess = sorted({d.date() for d in idx[idx >= lo].tz_localize(None).normalize()})
    print("FORWARD window %s .. | NQ 5m master to %s | %d forward sessions, %d in calendar E"
          % (FORWARD_FROM, idx.max(), len(sess), sum(calendar_e(sess)) if sess else 0))
    final_due = pd.Timestamp.now() >= pd.Timestamp(FINAL_DATE)
    rng = np.random.default_rng(SEED)
    lead = None
    for leg, params in LEGS.items():
        is_lead = leg.startswith("#314")
        if not is_lead and not (lead and lead.get("final")):
            continue                                       # reported-only legs print at the final read only
        r = run_backtest(FN, arrays=A, params=params, cost_pts=COST, return_trades=True)
        rows = [dict(day=idx[ei].tz_localize(None).normalize().date(), u=pnl * MULT)
                for (ei, xi, pnl, side, entry) in r["trades"] if idx[ei] >= lo]
        T = pd.DataFrame(rows, columns=["day", "u"])
        if len(T):
            T["inE"] = calendar_e(list(T.day))
            T["inR"] = calendar_r(list(T.day), sess)
        else:
            T["inE"], T["inR"] = [], []
        nE = int(T.inE.sum()) if len(T) else 0
        print("\n== %s: %d forward trades, %d in calendar E (read at %d or %s)" % (leg, len(T), nE, FINAL_N, FINAL_DATE))
        if not len(T):
            continue
        final = nE >= FINAL_N or final_due
        res = score(T, sess, final if is_lead else True, rng, lead=is_lead)
        if is_lead:
            lead = dict(res, final=final or "EARLY PASS" in str(res.get("status")))
            if lead["final"]:
                print("  (reported only) calendar R, the CME roll week: %d trades, mean $%+.1f vs outside $%+.1f"
                      % (int(T.inR.sum()), T.u[T.inR].mean() if T.inR.any() else 0.0,
                         T.u[~T.inR].mean() if (~T.inR).any() else 0.0))


def selftest():
    """Synthetic only: calendar construction, the stop's look indexing, the null and the five rules."""
    import datetime as dt
    import numpy as np
    import pandas as pd
    assert third_friday(2026, 12) == dt.date(2026, 12, 18)
    assert third_friday(2027, 3) == dt.date(2027, 3, 19)
    assert third_friday(2027, 9) == dt.date(2027, 9, 17)
    wk = [dt.date(2026, 12, 14) + dt.timedelta(days=i) for i in range(7)]
    assert calendar_e(wk) == [True] * 5 + [False] * 2, calendar_e(wk)
    assert calendar_e([dt.date(2026, 12, 11), dt.date(2026, 12, 21)]) == [False, False]
    sess = [d.date() for d in pd.bdate_range("2026-10-05", "2031-12-31")]
    # CME roll Thursday for Dec 2026 = 12-10; the five sessions after it = 12-11, 12-14 .. 12-17
    r = calendar_r([dt.date(2026, 12, 11), dt.date(2026, 12, 17), dt.date(2026, 12, 18)], sess)
    assert r == [True, True, False], r
    rng = np.random.default_rng(1)
    days = sorted(rng.choice(sess, size=1300, replace=False))
    T = pd.DataFrame(dict(day=days))
    T["inE"] = calendar_e(list(T.day))
    base = rng.normal(150.0, 2500.0, len(T))
    print("selftest: %d synthetic trades, %d in calendar E" % (len(T), int(T.inE.sum())))
    T["u"] = base + np.where(T.inE, 4000.0, 0.0)           # a planted large E effect must PASS
    big = score(T, sess, True, np.random.default_rng(2))
    assert big["passed"], big
    T["u"] = base                                          # no effect must not pass the null
    none = score(T, sess, True, np.random.default_rng(3))
    assert not none["rules"]["1 calendar null"] or not none["passed"], none
    T["u"] = base - np.where(T.inE, 9000.0, 0.0)           # a large harm must stop early
    harm = score(T, sess, False, np.random.default_rng(4))
    assert harm["status"].startswith("EARLY FAIL"), harm
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
