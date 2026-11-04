"""ENGU-Q FOR WEBULL LIVE r1 - arms A, C and D (MANAGER #136 / #137, owner GO 2026-11-04 12:00).

Pre-registered in C:\\EdgeLog\\manager\\prereg\\PREREG_enguq_webull_live_2026-11-04.md (frozen with
addendum 1; its LF sha256 is pinned below and checked at start). Arm B is a 900-trial co-tuned
Auto-Validate on the runner and is NOT run here - TBIS owns that slot.

    A  NQ #335's own signals, filled on real QQQ prints, held overnight   (= Q36 arm B / exec r1 T07)
    C  the same signals, REGULAR HOURS ONLY, FLAT AT THE SESSION CLOSE    (new; NOT exec r1's T08,
                                                                           which held through it)
    D  the NT8 demo's live ENGU-Q configuration, run on QQQ's own bars    (needs the dict from
                                                                           PAPER-NT8 - addendum 2)

Every fill rule is IMPORTED from the frozen harnesses of Q34, Q36 and executor r1 rather than
retyped, so the four rounds cannot drift apart. Nothing here touches the live account.

    python tools/enguq_webull_live_r1.py selftest
    python tools/enguq_webull_live_r1.py                     # arms A and C
    python tools/enguq_webull_live_r1.py --armd <config.json> # adds arm D once PAPER-NT8 answers
"""
import hashlib
import json
import os
import sys

PREREG = r"C:\EdgeLog\manager\prereg\PREREG_enguq_webull_live_2026-11-04.md"
PREREG_SHA = "e4892a6a96d3e9ec817839394d58f8850a8371fee2981c19f6f1f77a767bc177"
REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"          # where q34_enguq_timing / q36_enguq_qqq live
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_webull_live_r1"

D0, D1 = "2010-06-07", "2025-06-30"              # loaded; the LOCKBOX (2025-07-01..) is never loaded
S_SHARES = 822.0                                 # QQQ shares per NQ contract (Q36's own figure)
COST_LADDER = (0.01, 0.02, 0.04, 0.06)           # $ a share a round trip; 0.02 is the headline
HEADLINE_COST = 0.02

# #335's own 8 walk-forward folds, frozen in docs/PREREG_enguq_executor_r1_2026-10-18.md
FOLDS = (("2016-10-12", "2017-11-23"), ("2017-11-23", "2018-12-30"),
         ("2018-12-30", "2020-02-03"), ("2020-02-03", "2021-03-08"),
         ("2021-03-08", "2022-04-04"), ("2022-04-04", "2023-05-02"),
         ("2023-05-02", "2024-05-29"), ("2024-05-29", "2025-06-27"))
WF0, WF1 = FOLDS[0][0], FOLDS[-1][1]
LEG_ROC_NQ = 26.09                               # the NQ futures leg's own WF ROC@30k (exec r1)
RELAY_TOL = 2.0                                  # clause 1: within 2 ROC points of the futures leg


def lf(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def usd(x):
    """$ with thousands separators. (%-formatting has no "," flag - %,.0f RAISES, it does not
    format. This bit executor r1 once, mid-run, after the numbers were computed.)"""
    try:
        return format(float(x), ",.0f")
    except (TypeError, ValueError):
        return "-"


# ---------------------------------------------------------------- pure pieces (selftested)

def flat_at_close(entry_bars, day_codes, last_bar_of_day, n):
    """Arm C's exit rule: a trade entered on a bar exits at the LAST bar of that same session.

    Returns (exit_bars, kept) where `kept` is False for an entry whose session has no later bar
    (the entry IS the last bar) - such a signal is DROPPED rather than exited at its own entry
    price, because a same-bar round trip is not a trade, it is a cost.
    """
    import numpy as np
    ent = np.asarray(entry_bars, int)
    code = np.asarray(day_codes, int)[np.clip(ent, 0, n - 1)]
    last = np.where(code >= 0, np.asarray(last_bar_of_day, int)[np.clip(code, 0, None)], -1)
    kept = (code >= 0) & (last > ent)
    return last, kept


def no_overlap(entries, exits, kept):
    """One position at a time, which is what both the leg and a cash account do: an entry that
    falls at or before the previous KEPT trade's exit is skipped. Returns the kept mask, tightened.
    """
    import numpy as np
    out = np.asarray(kept).copy()
    prev_exit = -1
    for i in np.flatnonzero(out):
        if int(entries[i]) <= prev_exit:
            out[i] = False
        else:
            prev_exit = int(exits[i])
    return out


def fold_table(daily, dates, folds):
    """Per-fold net of a daily $ series. Fold bounds are DATES here (not bar indices) because the
    series is daily and every arm shares one calendar - the bar-index trap only bites a bar series.
    """
    import numpy as np
    import pandas as pd
    s = pd.Series(list(daily), index=pd.DatetimeIndex(dates))
    out = []
    for a, b in folds:
        w = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
        out.append(float(np.nansum(w.to_numpy())))
    return out


def selftest():
    import numpy as np
    # flat_at_close: exit at the session's last bar; an entry ON that bar is dropped
    last_of_day = [2, 5]                      # session 0 ends at bar 2, session 1 at bar 5
    codes = [0, 0, 0, 1, 1, 1]
    ex, kept = flat_at_close([0, 2, 3, 5], codes, last_of_day, 6)
    assert list(ex) == [2, 2, 5, 5], list(ex)
    assert list(kept) == [True, False, True, False], list(kept)

    # no_overlap: the second entry sits inside the first trade -> skipped
    k = no_overlap([0, 1, 4], [3, 2, 6], [True, True, True])
    assert list(k) == [True, False, True], list(k)
    # and a skipped trade does not extend the block
    k = no_overlap([0, 1, 3], [2, 9, 5], [True, True, True])
    assert list(k) == [True, False, True], list(k)

    # fold_table sums the right days and nothing else
    d = [1.0, 2.0, 4.0, 8.0]
    ft = fold_table(d, ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"],
                    (("2020-01-01", "2020-01-02"), ("2020-01-03", "2020-01-04")))
    assert ft == [3.0, 12.0], ft

    # usd never raises on junk, and never silently prints a wrong number
    assert usd(1234.6) == "1,235" and usd(None) == "-"
    print("selftest PASS - flat-at-close exit, dropped same-bar entry, one-position-at-a-time, "
          "fold sums, money formatter")


# ---------------------------------------------------------------- the run

def main(armd_path=None):
    import numpy as np
    import pandas as pd
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    sys.path.insert(0, BQ)
    os.chdir(REPO)
    from q36_enguq_qqq import qqq_fill
    from q34_enguq_timing import holding_pnl
    from api.book_shadow import BOOK463_LEGS
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import four_numbers
    from augur_engine.engine import run_backtest

    got = lf(PREREG)
    print("prereg %s\n  LF sha256 %s" % (PREREG, got))
    if got != PREREG_SHA:
        sys.exit("PREREG SHA MISMATCH - expected %s. Write an addendum; do not run on a moved "
                 "target." % PREREG_SHA)
    print("  matches the frozen sha")
    print("harness LF sha256 %s" % lf(os.path.abspath(__file__)))
    os.makedirs(OUT, exist_ok=True)

    leg = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]
    m_nq = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    arr = load_master_arrays(m_nq, date_from=D0, date_to=D1)
    res = run_backtest(leg["strategy"], arrays=arr, params=leg["params"],
                       cost_pts=float(leg["cost_pts"]), return_trades=True)
    tr = sorted((int(t[0]), int(t[1])) for t in res["trades"])
    et = arr["index"]
    print("NQ   %s rows %s bars %d -> %d signals"
          % (m_nq["filename"], usd(m_nq.get("rows", 0)), len(et), len(tr)))

    qm = find_master("QQQ", "1m", "rth", "alpaca_split_rth")
    qa = load_master_arrays(qm, date_from="2016-01-01", date_to=D1)
    qts = qa["index"]
    qn = len(qa["close"])
    qc = np.asarray(qa["close"], float)
    qo = np.asarray(qa["open"], float)
    print("QQQ  %s rows %s bars %d (the QQQ tape starts 2016-01-04 - a 2010-16 read is impossible)"
          % (qm["filename"], usd(qm.get("rows", 0)), qn))

    qday = pd.DatetimeIndex(np.asarray(qts, dtype="datetime64[D]"))
    sess = pd.DatetimeIndex(sorted(set(qday)))
    qcodes = sess.get_indexer(qday)
    last_bar = pd.Series(np.arange(qn), index=qday).groupby(level=0).max().to_numpy()

    A = np.array([a for a, _ in tr])
    Bx = np.array([b for _, b in tr])
    ke, eo = qqq_fill(et[A].asi8, qts.asi8)       # entry bar on the QQQ tape (same minute, else next open)
    kx, xo = qqq_fill(et[Bx].asi8, qts.asi8)

    def clip(k, ko):
        return (qn - 1, False) if k >= qn else (int(k), bool(ko))

    arms = {}

    # ---- arm A: overnight hold, QQQ fills ------------------------------------------------------
    fx, ent_a, ex_a = [], [], []
    for k, ko, mm, mo in zip(ke, eo, kx, xo):
        k, ko = clip(k, ko)
        mm, mo = clip(mm, mo)
        fx.append((S_SHARES, k, ko, mm, mo))
        ent_a.append(k)
        ex_a.append(mm)
    keep_a = no_overlap(ent_a, ex_a, [True] * len(fx))
    arms["A"] = ("NQ signals -> QQQ fills, overnight", fx, np.array(ent_a), np.array(ex_a), keep_a)

    # ---- arm C: regular hours, flat at the session close ---------------------------------------
    ex_c, keep_c0 = flat_at_close(ent_a, qcodes, last_bar, qn)
    keep_c = no_overlap(ent_a, ex_c, keep_c0)
    fx_c = [(S_SHARES, int(e), False, int(x), False) for e, x in zip(ent_a, ex_c)]
    arms["C"] = ("regular hours, FLAT at the session close", fx_c, np.array(ent_a), np.asarray(ex_c),
                 keep_c)

    # ---- arm D: the NT8 demo's own configuration on QQQ bars -----------------------------------
    if armd_path:
        cfg = json.load(open(armd_path))
        sfile, params = cfg["strategy"], cfg["params"]
        print("\narm D config from %s: %s with %d knobs (pinned as addendum 2)"
              % (armd_path, sfile, len(params)))
        rd = run_backtest(sfile, arrays=qa, params=params, cost_pts=HEADLINE_COST,
                          return_trades=True)
        td = sorted((int(t[0]), int(t[1])) for t in rd["trades"])
        ed = np.array([a for a, _ in td])
        xd = np.array([b for _, b in td])
        fx_d = [(S_SHARES, int(a), False, int(b), False) for a, b in td]
        arms["D"] = ("NT8 demo config on QQQ's own bars", fx_d, ed, xd,
                     no_overlap(ed, xd, [True] * len(td)))
    else:
        print("\narm D NOT RUN - no config supplied. PAPER-NT8 owes the live parameter dict "
              "(prereg addendum 1). A missing config is not a licence to substitute #335's.")

    # ---- four numbers, folds and the cost ladder ------------------------------------------------
    yrs = (pd.Timestamp(WF1) - pd.Timestamp(WF0)).days / 365.25
    wf_mask = (sess >= pd.Timestamp(WF0)) & (sess <= pd.Timestamp(WF1))
    wf_idx = sess[wf_mask]
    report = {}

    for key in ("A", "C", "D"):
        if key not in arms:
            continue
        label, fx, ent, ex, keep = arms[key]
        fx_keep = [f for f, k in zip(fx, keep) if k]
        pts, done = holding_pnl(qc, qo, fx_keep)      # $ a share x shares, bar by bar
        ex_keep = np.array([f[3] for f in fx_keep])
        gross = np.bincount(qcodes, weights=pts, minlength=len(sess))
        cx = qcodes[ex_keep[np.asarray(done)]]
        n_exit = np.bincount(cx[cx >= 0], minlength=len(sess))
        ntr = int(n_exit[wf_mask].sum())
        print("\nARM %s - %s" % (key, label))
        print("  %d entries kept of %d, %d closed inside the folds, %.1f a year"
              % (int(np.sum(keep)), len(keep), ntr, ntr / yrs))
        ladder = {}
        for c in COST_LADDER:
            d = (gross - n_exit * c * S_SHARES)[wf_mask]
            f = four_numbers(list(d), years=yrs)
            ladder[c] = f
            tag = "  <- headline" if c == HEADLINE_COST else ""
            print("  cost $%.2f/share  ROC@30k %7.2f | DD5 %9s | DD%% %6.2f | Sortino %6.3f | "
                  "net %10s%s"
                  % (c, f["roc30"] or 0.0, usd(f["dd5_usd"]), f["dd_pct_peak"],
                     f["sortino"] or 0.0, usd(f["net"]), tag))
        d = (gross - n_exit * HEADLINE_COST * S_SHARES)[wf_mask]
        ft = fold_table(d, wf_idx, FOLDS)
        print("  folds (net $ at the headline cost): " + " ".join(usd(x) for x in ft))
        report[key] = {"label": label, "trades": ntr, "per_yr": ntr / yrs,
                       "folds_usd": ft, "ladder": {str(k): v for k, v in ladder.items()},
                       "four": ladder[HEADLINE_COST]}

    # ---- the six clauses, and crown by folds ---------------------------------------------------
    print("\nTHE BAR (section 3 of the prereg, written before any of this):")
    keys = [k for k in ("A", "C", "D") if k in report]
    for k in keys:
        r = report[k]
        f = r["four"]
        roc = f["roc30"] or 0.0
        wins = sum(1 for i in range(len(FOLDS))
                   if all(r["folds_usd"][i] >= report[o]["folds_usd"][i] for o in keys if o != k))
        r["folds_won"] = wins
        c1 = roc >= LEG_ROC_NQ - RELAY_TOL
        c2 = wins >= 6
        c3 = not f.get("one_episode")
        c4 = r["per_yr"] >= 50.0
        c5 = (r["ladder"]["0.04"]["net"] or 0.0) > 0
        print("  ARM %s  ROC %7.2f (clause1 within %.0f of %.2f: %s) | folds won vs the other arms "
              "%d of 8 (>=6: %s) | one episode %s | %.1f tr/yr (>=50: %s) | net at $0.04 %s (>0: %s)"
              % (k, roc, RELAY_TOL, LEG_ROC_NQ, "PASS" if c1 else "FAIL", wins,
                 "PASS" if c2 else "FAIL", "YES - FAIL" if not c3 else "no",
                 r["per_yr"], "PASS" if c4 else "FAIL", usd(r["ladder"]["0.04"]["net"]),
                 "PASS" if c5 else "FAIL"))
        r["clauses"] = {"c1_relay": c1, "c2_folds": c2, "c3_not_one_episode": c3,
                        "c4_trades": c4, "c5_cost_004": c5}
    clear = [k for k in keys if all(report[k]["clauses"].values())]
    print("\n  clauses 1-5 cleared by: %s" % (", ".join(clear) if clear else "NO ARM"))
    if clear:
        best = max(clear, key=lambda k: report[k]["folds_won"])
        print("  CROWN BY FOLDS (#137, scope C5): arm %s, %d of 8 folds. Clause 6, the lockbox "
              "veto, is read ONCE after this and can only kill." % (best, report[best]["folds_won"]))
    else:
        print("  RECOMMENDATION: do not take ENGU-Q live on Webull in any of these shapes. That is "
              "a result, not a failure, and the lockbox is not read - it cannot rescue an arm that "
              "failed the walk-forward bar.")

    p = os.path.join(OUT, "webull_live_r1.json")
    json.dump({"report": report, "folds": [list(f) for f in FOLDS], "years": yrs,
               "shares": S_SHARES, "cost_ladder": list(COST_LADDER),
               "prereg_sha": PREREG_SHA, "nq_master": m_nq["filename"],
               "qqq_master": qm["filename"]}, open(p, "w"), indent=1, default=str)
    print("\nwrote %s" % p)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    else:
        d = None
        if "--armd" in sys.argv:
            d = sys.argv[sys.argv.index("--armd") + 1]
        main(d)
