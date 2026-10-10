# -*- coding: utf-8 -*-
"""GAMMA r1 - dealer gamma as the ES day-type switch, ONE shared prereg for two arms (docs/PREREG_gamma_r1_2026-10-07.md;
MANAGER #67: TTM's GEXEXP expansion arm + DISC's GEXREV reversion arm, one family null). THIS FILE = the shared frame,
the GEXEXP arm (ARM A) and the GEXREV arm's schedule (ARM B; counts, parity and power only).

GEX = SqueezeMetrics' public daily dealer-gamma estimate (S&P 500 options), the 2026-10-07 photograph
C:/EdgeLog/_research_cache/squeezemetrics/DIX.csv, re-hashed against squeezemetrics_provenance.json; rows after 2025-06-29
dropped on read; only the value dated strictly BEFORE a session is read (end-of-day value, publication time unstated).
State per session: the prior GEX's percentile among the 252 GEX days before it. Bottom tercile = SHORT-GAMMA day (GEXEXP),
top tercile = LONG-GAMMA day (GEXREV).

GEXEXP (short-gamma days): ES 30m RTH; range = high / low of the 10:00 and 10:30 bars; the first 30m close beyond it from
the 11:00 bar to the 15:00 bar -> 1 ES in that direction at the next bar's open, out at the 15:30 bar's close; one trade a
session; no stop. Cost 0.363 pt, $50 a point. Intra-session only, so the no-adjust master is exact.

GEXREV (long-gamma days; DISC's text, prereg ARM B): BALANCE r1 sections 3.2-3.7 on the ES 5m RTH no-adjust master 33,
IMPORTED from tools/balance_r1_stageA.py (band, VWAP, stretch, the walk sim_session and simulate; nothing re-typed), with
two changes: (1) the long-gamma state REPLACES the noon classifier, and BALANCE 3.4's second half is kept (the day is open
only until its first raw break of either band, any bar from k = 1 - sim_session's own rule); (2) signal stamps 10:00 ..
15:25. BALANCE's ES roll sessions are never traded (its trading mask). $50 a point, cost 0.363, stress 1.363. Cells B1
x >= 1/2 (PRIMARY), B2 x >= 2/3 (neighbour). NO real-direction GAMMA number is computed here: the owner's GO for Stage A
has not been relayed. The per-trade gross / net columns that the imported simulate() fills are dropped at the call
boundary, unread.

  python tools/gamma_r1_stageA.py            -> state days and GEXEXP trades per year (no returns), as before
  python tools/gamma_r1_stageA.py --parity   -> ARM B item 6: BALANCE's own noon classifier on ES reproduces BALANCE r1's
                                                published ES transfer exactly (aborts on a mismatch); no gamma
  python tools/gamma_r1_stageA.py --counts   -> parity first, then GEXEXP's counts, then GEXREV's schedule COUNTS
  python tools/gamma_r1_stageA.py --power    -> as --counts, plus the power lines from COIN-FLIP sides on GEXEXP's and on
                                                GEXREV B1's real schedules
  python tools/gamma_r1_stageA.py --armc-parity -> ARM C's parity only: #463's four legs rebuilt through
                                                augur_engine.book on #463's pinned masters, summed to the book's daily
                                                column to the cent, WF ROC@30k 93.81 / Sortino 3.816; no gamma
  python tools/gamma_r1_stageA.py --stageA   -> STAGE A for arms A, B and C (owner GO 2026-10-10, docs/SCOPE_CALMDAY
                                                section 7): every parity first, then the real-label cells, then ONE
                                                shuffled-label family null (1,000 draws, seed 20261007). WF only.
  python tools/gamma_r1_stageA.py --stageA --dry -> the same code path with the REAL labels replaced by one shuffled
                                                draw (a plumbing check that reads no real gamma-conditioned return)

ARM C (GEXGATE, docs/SCOPE_CALMDAY_2026-10-10.md section 4): #463's ORB #234 and NOISE #422 take no entry (C1, C3) or
enter at 0.5x (C2) on long-gamma days (C1 / C2: p >= 2/3; C3: p >= 3/4); ENGU-Q and TTM unchanged. The legs are
rebuilt with augur_engine.book._leg_trades on #463's pinned legs (api/book_shadow.BOOK463_LEGS) and re-priced through
augur_engine.book_sizing.resize (the engine's own closed / valued-daily formulas), entry day = the ET session day of
the entry bar. The null's fast path (book minus the removed-day leg dollars) is asserted equal to the engine path to
the cent on the real cells.
"""
import contextlib
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HOME = os.environ.get("EDGELOG_HOME") or "C:/EdgeLog"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import halfhour_r1_stageA as HH                                         # noqa: E402
import balance_r1_stageA as BL                                          # noqa: E402  (ARM B: band / VWAP / walk / simulate)

COST, M = 0.363, 50.0
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
SEED = 20261007
GEXDIR = os.path.join(HOME, "_research_cache", "squeezemetrics")

# ARM B (GEXREV): the clock is the only rule constant that differs from BALANCE r1 (prereg ARM B item 4). Stamps are
# START stamps in minutes after midnight ET, as in BALANCE (a bar stamped t closes at t + 5).
B_SIG_FIRST, B_SIG_LAST = 600, 925                                      # signal stamps 10:00 .. 15:25 (last fill 15:30)
STAGE_A_MSG = "GAMMA Stage A waits for the owner GO via MANAGER"          # (kept for history; the GO came 2026-10-10)
NULL_DRAWS = 1000
H1_END, H2_START = pd.Timestamp("2021-12-31"), pd.Timestamp("2022-01-01")
# RUN-BEFORE-MAIN (#77): LF sha256 of the frozen prereg and the Arm C scope; the run stops on a mismatch.
PREREG_SHA = {"docs/PREREG_gamma_r1_2026-10-07.md": "fd3091040344279c140da4444c14cd9aa075e1e6099ed93c8070b1235a457c90",
              "docs/SCOPE_CALMDAY_2026-10-10.md": "190b3f8e87582008cca7b5ef06ea8dba15841830bbabcb18edbeded421da3729"}
C_LEGS = ("ORB", "NOISE")                                               # the two legs ARM C gates (ENGU-Q, TTM untouched)
C_CELLS = (("C1", 2.0 / 3.0, 0.0), ("C2", 2.0 / 3.0, 0.5), ("C3", 0.75, 0.0))   # (cell, p threshold, size on the day)
LOOK_BAND = "ORB seat +49%, NOISE seat +64%, ORB + ENGU-Q +78% (BOOK.md 10z, K = 71 looks)"
THIN = 25                                                               # a July-June year under 25 trades is flagged thin
# BALANCE r1's PUBLISHED ES transfer (docs/PREREG_balance_r1_2026-10-06.md RESULTS: "B1 592 trades, PF 0.99, own ROC
# -0.28; B2 PF 0.995"; full rows in tools/r37_results/balance_r1_stageA.txt lines 306-312): per cell n, PF (3 dp), net $
# (to the dollar), own ROC@$30k (2 dp), re-entries, sessions with a trade. Public, so reproducing it is not a new read.
BAL_ES_PUBLISHED = {"B1": (592, 0.992, -1245, -0.28, 55, 537), "B2": (378, 0.995, -398, -0.12, 17, 361)}
BAL_ES_PARITY_BARS, BAL_ES_SESSIONS, BAL_ES_SWITCHES = 5452, 3868, 61
# Only these columns of the imported simulate()'s output are kept for ARM B: the schedule and the SIDE (side counts).
# gross_pts / net_usd / stress_usd / marks (real-direction P&L) and exit_reason / R0 / x are dropped unread.
B_KEEP = ["session", "stretch", "si", "sig_hm", "fill_stamp", "exit_stamp", "side", "entry", "exit", "order"]


def gex():
    raw = os.path.join(GEXDIR, "DIX.csv")
    prov = json.load(open(os.path.join(GEXDIR, "squeezemetrics_provenance.json"), encoding="utf-8"))["DIX.csv"]
    assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == prov["sha256"], "DIX.csv is not the photograph - abort"
    g = pd.read_csv(raw, parse_dates=["date"])
    g = g[g["date"] <= WF1].set_index("date")["gex"].astype(float).dropna()
    return g, prov


def state(days, g):
    """Per session: -1 short-gamma (bottom tercile), +1 long-gamma (top tercile), 0 middle / unknown."""
    gv, gi = g.to_numpy(), g.index
    out = np.zeros(len(days), int)
    pct = np.full(len(days), np.nan)
    for i, d in enumerate(days):
        k = gi.searchsorted(d) - 1                                      # the latest GEX dated strictly before session d
        if k < 252:
            continue
        p = float((gv[k - 252:k] < gv[k]).mean())
        pct[i] = p
        out[i] = -1 if p <= 1.0 / 3.0 else (1 if p >= 2.0 / 3.0 else 0)
    return out, pct


def es30():
    A = load_master_arrays(find_master("ES", "30m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 30)
    day = pd.DatetimeIndex(pd.Index(ts.date))
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    G = {}
    ok = (k >= 0) & (k < 13)
    for f in ("open", "high", "low", "close"):
        X = np.full((len(days), 13), np.nan)
        X[di[ok], k[ok]] = np.asarray(A[f], float)[ok]
        G[f] = X
    full = np.isfinite(G["close"]).all(axis=1) & np.isfinite(G["open"]).all(axis=1)
    return days[full], {f: X[full] for f, X in G.items()}


def gexexp_schedule(G, on):
    """(side, entry bar) per session: the first close of bars 3..11 (11:00 .. 15:00) beyond the 10:00-11:00 range."""
    hi = np.maximum(G["high"][:, 1], G["high"][:, 2])
    lo = np.minimum(G["low"][:, 1], G["low"][:, 2])
    side = np.zeros(len(hi))
    ent = np.full(len(hi), -1)
    for i in np.flatnonzero(on):
        for b in range(3, 12):
            c = G["close"][i, b]
            if c > hi[i] or c < lo[i]:
                side[i], ent[i] = (1.0 if c > hi[i] else -1.0), b + 1
                break
    return side, ent


def gexexp_pnl(G, side, ent):
    x = np.zeros(len(side))
    m = side != 0
    x[m] = side[m] * (G["close"][m, 12] - G["open"][m, ent[m]]) * M - COST * M
    return x


def r_days():
    return pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))


def arm_a(argv, g, prov, B, ref):
    """ARM A (GEXEXP): the counts block and, with --power, its power line - unchanged. -> (30m days, GEXEXP sides)."""
    days, G = es30()
    st, pct = state(days, g)
    wf = np.asarray((days >= WF0) & (days <= WF1))
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("GAMMA r1 - GEX photograph %s fetched %s sha256 %s.. verified, %d GEX days to %s; ES 30m RTH no-adjust %d full "
          "sessions (%s .. %s)" % (prov["url"], prov["fetched_at_utc"], prov["sha256"][:8], len(g), g.index[-1].date(),
                                   len(days), days[0].date(), days[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    neg = int((g[g.index >= WF0] < 0).sum())
    print("  WF sessions with a state: %d; short-gamma (bottom tercile) %d (%.0f a year), long-gamma (top tercile) %d (%.0f a "
          "year); raw GEX < 0 on %d WF GEX days" % (int((wf & np.isfinite(pct)).sum()), int((wf & (st == -1)).sum()),
                                                  (wf & (st == -1)).sum() / years, int((wf & (st == 1)).sum()),
                                                  (wf & (st == 1)).sum() / years, neg))
    side, ent = gexexp_schedule(G, wf & (st == -1))
    yb = pd.Series(days.year[side != 0]).value_counts().sort_index()
    print("  COUNTS GEXEXP: %d WF trades (%.0f a year), long %d / short %d; per calendar year %s" % (
        int((side != 0).sum()), (side != 0).sum() / years, int((side > 0).sum()), int((side < 0).sum()),
        {int(k): int(v) for k, v in yb.items()}))
    for lab, a, b in (("2016-21", WF0, pd.Timestamp("2021-12-31")), ("2022-25", pd.Timestamp("2022-01-01"), WF1)):
        m = np.asarray((days >= a) & (days <= b))
        print("    %s: short-gamma days %d, long-gamma days %d, GEXEXP trades %d" % (
            lab, int((m & (st == -1)).sum()), int((m & (st == 1)).sum()), int((m & (side != 0)).sum())))
    RD = np.asarray(days.isin(r_days()))
    print("  R days among GEXEXP trade days %d; among long-gamma days %d" % (int((RD & (side != 0)).sum()),
                                                                            int((RD & wf & (st == 1)).sum())))
    if "--power" in argv:
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(side))
        x = gexexp_pnl(G, np.where(side != 0, coin, 0.0), ent)
        print("POWER LINES (coin-flip sides on GEXEXP's schedule; no real direction is computed)")
        HH.power_lines(pd.Series(x, index=days).reindex(bdays, fill_value=0.0).to_numpy(), B, years)
    return days, side


# ================================================================== ARM B - GEXREV (BALANCE r1's fade, imported)
def es5():
    """BALANCE's ES context: master 33 (id / file / source asserted, nothing after 2025-06-29), #304's _FROZEN band and
    VWAP, rolls_ES (36 WF switches asserted), trading sessions (15:55 bar, not warm-up, not roll), the noon classifier
    and NOISE_1_0's #304 run on ES - all BALANCE's own code (balance_r1_stageA.prepare)."""
    inst = BL.INST["ES"]
    if not (inst["mult"] == M and inst["cost"] == COST and inst["stress"] == 1.363):
        raise SystemExit("BALANCE's ES constants are not $50 / 0.363 / 1.363 - abort")
    if not (BL.MASTERS["ES"][0] == 33 and BL.SIG_FIRST == 715 and BL.SIG_LAST == B_SIG_LAST):
        raise SystemExit("balance_r1_stageA's ES master / clock is not master 33, 11:55 .. 15:25 - abort")
    return BL.prepare("ES", BL.frozen())


def balance_parity(es, bdays):
    """PARITY FIRST (prereg ARM B item 6): BALANCE's own noon classifier and clock on ES, through balance_r1_stageA's
    parity_304 / simulate / daily / own / pf, must reproduce BALANCE r1's published ES transfer exactly. No gamma."""
    if BL.SIG_FIRST != 715:
        raise SystemExit("BALANCE's clock is patched during parity - abort")
    BL.assert_balance_on_index(es, bdays)
    pi = BL.parity_304(es)
    print("PARITY FIRST (GAMMA prereg ARM B item 6): BALANCE r1's own noon classifier and clock (11:55 .. 15:25) on ES "
          "master 33, through tools/balance_r1_stageA.py; no gamma")
    print("  ES band / VWAP parity at %d #304 decision bars (max |diff| %.3g); eligible first break on %d sessions, "
          "0 mismatches; %d roll switches (%d in WF)" % (pi["bars"], pi["max_diff"], pi["sessions"], len(es.switches),
                                                         es.n_wf_switches))
    bad = []
    if (pi["bars"], pi["sessions"], len(es.switches)) != (BAL_ES_PARITY_BARS, BAL_ES_SESSIONS, BAL_ES_SWITCHES):
        bad.append("band parity bars / sessions / switches %s vs published %s" % (
            (pi["bars"], pi["sessions"], len(es.switches)), (BAL_ES_PARITY_BARS, BAL_ES_SESSIONS, BAL_ES_SWITCHES)))
    for nm, k in BL.CELLS:
        tr = BL.simulate(es.S, es.balance, k / 12.0, es.cost, es.mult, es.stress)
        wf = tr[tr.stretch == "WF"]
        x = BL.daily(wf, bdays).to_numpy()
        tps = wf.groupby("session").size()
        got = (len(wf), round(BL.pf(wf["net_usd"]), 3), int(round(float(x.sum()))), round(BL.own(x, bdays)["roc"], 2),
               int((wf.order >= 2).sum()), len(tps))
        pub = BAL_ES_PUBLISHED[nm]
        ok = got[0] == pub[0] and abs(got[1] - pub[1]) < 1e-9 and got[2] == pub[2] and abs(got[3] - pub[3]) < 1e-9 \
            and got[4:] == pub[4:]
        print("  ES %s  n %d  PF %.3f  net %s  own ROC@$30k %.2f  re-entries %d  sessions with a trade %d   "
              "(published %d / %.3f / %s / %.2f / %d / %d)  %s" % (
                  nm, got[0], got[1], BL.fm(got[2]), got[3], got[4], got[5], pub[0], pub[1], BL.fm(pub[2]), pub[3],
                  pub[4], pub[5], "MATCH" if ok else "MISMATCH"))
        if not ok:
            bad.append("%s %s vs published %s" % (nm, got, pub))
    if bad:
        raise SystemExit("PARITY FAILED - BALANCE r1's ES transfer is not reproduced: %s - abort" % "; ".join(bad))
    print("  PARITY OK: B1 592 trades PF 0.99 (0.992), B2 PF 0.995 - BALANCE r1's printed ES transfer, reproduced exactly")


@contextlib.contextmanager
def _clock(first):
    """ARM B's clock change (signal stamps from 10:00), applied to the IMPORTED simulate(), which reads its first signal
    stamp from balance_r1_stageA.SIG_FIRST at call time; restored on exit."""
    old = BL.SIG_FIRST
    BL.SIG_FIRST = int(first)
    try:
        yield
    finally:
        BL.SIG_FIRST = old


def gexrev_schedule(es, days_on, thr):
    """GEXREV's trade SCHEDULE on the sessions in `days_on`: balance_r1_stageA.simulate (BALANCE 3.5-3.7 through its
    sim_session walk) with the day mask in place of the noon classifier and signal stamps 10:00 .. 15:25. sim_session
    closes the day for new entries at its first raw break on any bar with k >= 1 (BALANCE 3.4's second half). Only
    B_KEEP columns are returned; the real-direction P&L columns are dropped here, unread."""
    with _clock(B_SIG_FIRST):
        tr = BL.simulate(es.S, np.asarray(days_on, bool), thr, es.cost, es.mult, es.stress, B_SIG_LAST)
    if BL.SIG_FIRST != 715:
        raise SystemExit("BALANCE's clock was not restored - abort")
    tr = tr[B_KEEP].reset_index(drop=True)
    if len(tr) and not ((tr.sig_hm >= B_SIG_FIRST) & (tr.sig_hm <= B_SIG_LAST)).all():
        raise SystemExit("a GEXREV signal stamp outside 10:00 .. 15:25 - abort")
    if len(tr) and not np.asarray(days_on, bool)[tr.si.to_numpy(int)].all():
        raise SystemExit("a GEXREV trade on a session outside its day mask - abort")
    return tr


def jy_counts(wf):
    jy = BL.jy(wf["session"]) if len(wf) else np.array([], int)
    return [(y, int((jy == y).sum())) for y in range(2016, 2025)]


def arm_b_counts(es, st5, pct5, bdays, years, days_a, side_a):
    """ARM B COUNTS (prereg ARM B items 7-8; no P&L): per cell the WF trades, per calendar and July-June year (thin
    years flagged), side counts, long-gamma days with a trade, R days among trade days; the twins' trade counts."""
    S = es.S
    dates = pd.DatetimeIndex(S.dates)
    wf5 = np.asarray((dates >= WF0) & (dates <= WF1))
    trd = es.trading & wf5
    if not np.isfinite(pct5[trd]).all():
        raise SystemExit("a WF trading session has no GEX state - abort")
    lg, sg = es.trading & (st5 == 1), es.trading & (st5 == -1)
    RD = r_days()
    print("\nARM B - GEXREV COUNTS (ES 5m RTH no-adjust master 33; BALANCE r1 3.2-3.7 imported from "
          "tools/balance_r1_stageA.py; day filter = the long-gamma state, the day open only until its first raw break "
          "from k = 1; signal stamps 10:00 .. 15:25; BALANCE's ES roll sessions never traded; no P&L computed)")
    print("  WF sessions in master 33: %d; trading sessions (15:55 bar, not warm-up, not roll) %d; long-gamma: %d WF "
          "sessions, %d of them trading (left out: %d roll sessions, %d sessions without a 15:55 bar); short-gamma "
          "trading %d" % (
              int(wf5.sum()), int(trd.sum()), int((wf5 & (st5 == 1)).sum()), int((lg & wf5).sum()),
              int((wf5 & (st5 == 1) & es.roll & S.has1555).sum()), int((wf5 & (st5 == 1) & ~S.has1555).sum()),
              int((sg & wf5).sum())))
    print("  R days among long-gamma trading days %d (of %d); among all WF trading days %d" % (
        int(dates[lg & wf5].isin(RD).sum()), int((lg & wf5).sum()), int(dates[trd].isin(RD).sum())))
    print("  (trades include re-entries, which follow only a TARGET exit, so a trade count bounds target hits from below "
          "- BALANCE section 5's disclosure; counts are what prereg ARM B item 7 asks for)")
    out = {}
    for nm, k in BL.CELLS:
        tr = gexrev_schedule(es, lg, k / 12.0)
        wf = tr[tr.stretch == "WF"]
        out[nm] = wf
        n = len(wf)
        sess = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(wf["session"]))))
        lab = "B1 (x >= 1/2, PRIMARY)" if nm == "B1" else "B2 (x >= 2/3, neighbour)"
        meets = n >= 100 and n / years >= 50
        print("  %s: %d WF trades (%.1f a year over %.3f years) on %d sessions (re-entries %d); long %d / short %d (side "
              "counts); counts line >= 100 AND >= 50 a year: %s" % (
                  lab, n, n / years, years, len(sess), n - len(sess), int((wf.side > 0).sum()), int((wf.side < 0).sum()),
                  "MET" if meets else "MISSED (a count-only miss is a RESEARCH ROW)"))
        cy = pd.Series(pd.DatetimeIndex(wf["session"]).year).value_counts().sort_index()
        print("    per calendar year %s" % {int(y): int(v) for y, v in cy.items()})
        jj = jy_counts(wf)
        thin = [BL.jy_label(y) for y, v in jj if v < THIN]
        print("    per July-June year: " + ", ".join("%s %d%s" % (BL.jy_label(y), v, " THIN" if v < THIN else "")
                                                     for y, v in jj)
              + "; thin years (< %d): %s" % (THIN, ", ".join(thin) if thin else "none"))
        for hl, a, b in (("2016-21", WF0, pd.Timestamp("2021-12-31")), ("2022-25", pd.Timestamp("2022-01-01"), WF1)):
            sd = pd.DatetimeIndex(wf["session"])
            m = (sd >= a) & (sd <= b)
            dm = (dates >= a) & (dates <= b)
            print("    %s: trades %d on %d sessions; long-gamma trading days %d" % (
                hl, int(m.sum()), len(set(sd[m])), int((lg & dm).sum())))
        print("    long-gamma trading days with any trade %d of %d (%.3f); R days among its trade days %d" % (
            len(sess), int((lg & wf5).sum()), len(sess) / max(1, int((lg & wf5).sum())), int(sess.isin(RD).sum())))
        early = int((wf.sig_hm < BL.NOON_LAST).sum())
        if n and not early:
            raise SystemExit("no GEXREV signal before 11:55 - the 10:00 clock did not take effect - abort")
        print("    signal stamps %s .. %s; %d trades signalled before BALANCE's 11:55 start (the clock change)" % (
            "%02d:%02d" % divmod(int(wf.sig_hm.min()), 60) if n else "-",
            "%02d:%02d" % divmod(int(wf.sig_hm.max()), 60) if n else "-", early))
        ovl = set(sess) & set(pd.DatetimeIndex(days_a[side_a != 0]))
        if ovl:
            raise SystemExit("GEXREV %s and GEXEXP share %d trade days - the arms must be disjoint - abort" % (nm, len(ovl)))
    print("  arms A and B on disjoint days: asserted (no GEXREV B1 / B2 trade day is a GEXEXP trade day)")
    print("  TWINS (reports, counts only; same fade, same clock, same first-break rule):")
    for tlab, mask in (("ALL sessions", es.trading), ("SHORT-gamma days", sg)):
        parts = []
        for nm, k in BL.CELLS:
            tr = gexrev_schedule(es, mask, k / 12.0)
            wf = tr[tr.stretch == "WF"]
            parts.append("%s %d trades (%.1f a year) on %d sessions, long %d / short %d" % (
                nm, len(wf), len(wf) / years, len(set(wf["session"])), int((wf.side > 0).sum()), int((wf.side < 0).sum())))
        print("    %-17s %s" % (tlab, "; ".join(parts)))
    return out


def arm_b_power(b1wf, B, years):
    """GEXREV's power line (prereg ARM B item 9): COIN-FLIP sides on B1's real WF schedule (one coin per trade in trade
    order, seed 20261007); net = coin x (exit - entry) x $50 - 0.363 x $50; fed to HH.power_lines exactly as ARM A."""
    bdays = pd.DatetimeIndex(B.index)
    coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(b1wf))
    net = coin * (b1wf["exit"].to_numpy(float) - b1wf["entry"].to_numpy(float)) * M - COST * M
    x = BL.daily(pd.DataFrame({"session": b1wf["session"].to_numpy(), "net_usd": net}), bdays).to_numpy()
    print("POWER LINES ARM B (coin-flip sides on GEXREV B1's real WF schedule, %d trades, seed %d; no real direction is "
          "computed)" % (len(b1wf), SEED))
    HH.power_lines(x, B, years)


# ================================================================== STAGE A (owner GO 2026-10-10; arms A, B and C)
def lf_sha(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def check_hashes():
    """RUN-BEFORE-MAIN (#77): the prereg and the Arm C scope must be the frozen text; the harness hash is printed."""
    base = os.path.dirname(HERE)
    print("FROZEN TEXT CHECK (#77)")
    for rel, want in PREREG_SHA.items():
        got = lf_sha(os.path.join(base, rel))
        print("  %s LF sha256 %s %s" % (rel, got, "OK" if got == want else "MISMATCH"))
        if got != want:
            raise SystemExit("%s is not the frozen text - abort" % rel)
    print("  harness tools/%s LF sha256 %s" % (os.path.basename(__file__), lf_sha(os.path.abspath(__file__))))


def dd5_txt(x, bdays):
    from augur_engine.drawdowns import dd5
    r = dd5(pd.Series(np.asarray(x, float), index=pd.DatetimeIndex(bdays)))
    return "DD5 $%s%s" % (format(int(round(r["dd5_usd"])), ","), ", 1 EPISODE" if r["one_episode"] else "")


def roc_txt(x, bdays, st=None):
    st = st or BL.own(x, bdays)
    return "ROC@30k %.2f (%s)" % (st["roc"], dd5_txt(x, bdays))


def fm(v):
    return ("-$" if v < 0 else "$") + format(int(round(abs(v))), ",")


def pf_of(v):
    return BL.pf(np.asarray(v, float))


def _marks_series(marks, bdays):
    from augur_engine import book as BK
    d, v = BK._daily(marks)
    s = pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum() if len(d) else pd.Series(dtype=float)
    s = s[(s.index >= WF0) & (s.index <= WF1)]
    if (~s.index.isin(bdays)).any():
        raise SystemExit("a leg mark day is not on the book's WF index - abort")
    return s.reindex(bdays, fill_value=0.0).to_numpy()


def book_legs(B, ref):
    """ARM C PARITY: #463's four pinned legs through augur_engine.book._leg_trades (keep_state, for re-pricing), each
    leg's valued-daily marks on the book's WF index, summed and compared with the book's daily column to the cent;
    plus each gated leg's trades (entry ET session day, $, side), asserted intra-session."""
    # The legs are CAPTURED from api.book_shadow.book463_valued_daily's own build - the function HH.book() scores
    # (93.81 / 3.816). That call path is report-only for the engine roll guard (augur_engine/rolls.py
    # REPORT_ONLY_MODULES), so NOISE's no-adjust leg runs as #463 was adopted; a direct call from a tools/ script
    # would re-price NOISE's signals under the guard (a different book, reported separately as a side note).
    import api.book_shadow as BSH
    from augur_engine import book as BK
    bdays = pd.DatetimeIndex(B.index)
    legs, X, T, cap = {}, {}, {}, []
    orig = BK._leg_trades

    def _capture(leg, date_from, date_to, keep_state=False):
        tr, inf = orig(leg, date_from, date_to, keep_state=True)
        cap.append((dict(leg), inf, list(inf.get("_mtm_day") or tr)))
        return tr, inf
    BK._leg_trades = _capture
    try:
        B2 = BSH.book463_valued_daily(D0, WF1.strftime("%Y-%m-%d"))
    finally:
        BK._leg_trades = orig
    B2 = B2[(B2.index >= WF0) & (B2.index <= WF1)]
    if not (B2.index.equals(B.index) and np.array_equal(B2.to_numpy(), B.to_numpy())):
        raise SystemExit("the captured build is not the book HH.book() scored - abort")
    for leg, inf, marks in cap:
        key = next(k for k in ("ORB", "ENGUQ", "TTMSQZ", "NOISE") if leg["strategy"].startswith(k))
        if inf.get("source") != leg["source"] or inf.get("mtm_error"):
            raise SystemExit("leg %s ran on %r (pinned %r), valuation error %r - abort" % (
                leg["strategy"], inf.get("source"), leg["source"], inf.get("mtm_error")))
        legs[key], X[key] = inf, _marks_series(marks, bdays)
    tot = np.zeros(len(bdays))
    for k in X:
        tot = tot + X[k]
    diff = float(np.abs(tot - B.to_numpy()).max())
    print("ARM C PARITY (#463's legs rebuilt through augur_engine.book on the pinned masters; no gamma)")
    for k, inf in legs.items():
        print("  %-6s %-28s master %-24s source %-13s WF net %s" % (k, inf["strategy"], inf.get("master"), inf["source"],
                                                                     fm(X[k].sum())))
    print("  legs summed vs the book's daily column: max |diff| $%.6f over %d WF days; book WF ROC@30k %.2f Sortino %.3f "
          "(%s)" % (diff, len(bdays), ref["roc"], ref["sort"], dd5_txt(B.to_numpy(), bdays)))
    if diff >= 0.005:
        raise SystemExit("ARM C PARITY FAILED - the legs do not sum to the book to the cent - abort")
    for k in C_LEGS:
        st = legs[k]["_state"]
        sidx = st["sess_idx"] if st["sess_idx"] is not None else st["days_idx"]
        rows = []
        for t, s in st["sized"]:
            i0, i1 = int(t[0]), min(int(t[1]), st["last"])
            if sidx[i0] != sidx[i1] or st["days_idx"][i1] != sidx[i1]:
                raise SystemExit("%s trade not intra-session / not stamped on its session day - abort" % k)
            rows.append((sidx[i0], float(t[2]) * st["mult"] * st["weight"] * float(s), float(np.sign(t[3]))))
        df = pd.DataFrame(rows, columns=["day", "usd", "side"])
        df["day"] = pd.to_datetime(df["day"])
        df = df[(df.day >= WF0) & (df.day <= WF1)].reset_index(drop=True)
        df["bi"] = bdays.get_indexer(df.day)
        if (df.bi < 0).any():
            raise SystemExit("%s entry day not on the book index - abort" % k)
        T[k] = df
        print("  %s: %d WF trades, all intra-session (entry and exit on one ET session day, stamped there)" % (k, len(df)))
    print("  PARITY OK")
    return legs, X, T


def gated_engine(B, legs, X, removed, size, keys=C_LEGS):
    """The gated book through the ENGINE: augur_engine.book_sizing.resize re-prices ORB / NOISE with size `size` on
    entries whose ET session day is in `removed` (book's own _closed_series / _mtm_increments)."""
    from augur_engine import book_sizing as BS
    bdays = pd.DatetimeIndex(B.index)
    rem = set(pd.DatetimeIndex(removed).values.astype("datetime64[D]").astype("int64").tolist())
    out = B.to_numpy().copy()
    for k in keys:
        st = legs[k]["_state"]
        sidx = (st["sess_idx"] if st["sess_idx"] is not None else st["days_idx"]).astype("int64")
        _, _, mtm, _ = BS.resize(st, lambda t, sidx=sidx: size if int(sidx[int(t[0])]) in rem else 1.0)
        out += _marks_series(mtm, bdays) - X[k]
    return out


def gexrev_trades(es, days_on, thr):
    """GEXREV's trades WITH their P&L (Stage A; owner GO): the same imported simulate() as gexrev_schedule."""
    with _clock(B_SIG_FIRST):
        tr = BL.simulate(es.S, np.asarray(days_on, bool), thr, es.cost, es.mult, es.stress, B_SIG_LAST)
    if BL.SIG_FIRST != 715:
        raise SystemExit("BALANCE's clock was not restored - abort")
    return tr


def vix_prior(days):
    pub = os.path.join(HOME, "_research_cache", "public_series")
    raw = os.path.join(pub, "cboe", "VIX_History.csv")
    prov = json.load(open(os.path.join(pub, "public_series_provenance.json"), encoding="utf-8"))["cboe\\VIX_History.csv"]
    if hashlib.sha256(open(raw, "rb").read()).hexdigest() != prov["sha256"]:
        raise SystemExit("VIX_History.csv is not the photograph - abort")
    v = pd.read_csv(raw)
    s = pd.Series(v["CLOSE"].astype(float).to_numpy(), index=pd.to_datetime(v["DATE"], format="%m/%d/%Y")).sort_index()
    s = s[s.index <= WF1]
    k = s.index.searchsorted(pd.DatetimeIndex(days)) - 1                # the close dated strictly before the session
    return np.where(k >= 0, s.to_numpy()[np.maximum(k, 0)], np.nan)


def build(B, ref, es, g):
    """Everything the cells need, computed ONCE with no state applied: GEXEXP's outcome on every WF session, GEXREV's
    trades on every trading session (both walks are per-session, so a state mask only selects), #463's legs. The
    state then enters only as a percentile per session on one union calendar U, which the null shuffles."""
    F = type("F", (), {})()
    F.B = B
    F.bdays = bdays = pd.DatetimeIndex(B.index)
    F.Bx = B.to_numpy()
    F.years = (bdays[-1] - bdays[0]).days / 365.25
    days, G = es30()
    wf = np.asarray((days >= WF0) & (days <= WF1))
    side, ent = gexexp_schedule(G, wf)
    F.a_days, F.a_side, F.a_trade = days, side, wf & (side != 0)
    F.a_pnl = gexexp_pnl(G, side, ent)
    F.a_price = np.where(side != 0, G["open"][np.arange(len(side)), np.maximum(ent, 0)], np.nan)
    F.a_bi = bdays.get_indexer(days)
    if (F.a_bi[F.a_trade] < 0).any():
        raise SystemExit("a GEXEXP trade day is not on the book index - abort")
    F.b, F.b_bi = {}, {}
    for nm, k in BL.CELLS:
        tr = gexrev_trades(es, es.trading, k / 12.0)
        F.b[nm] = tr[tr.stretch == "WF"].reset_index(drop=True)
        F.b_bi[nm] = bdays.get_indexer(pd.DatetimeIndex(F.b[nm]["session"]))
        if (F.b_bi[nm] < 0).any():
            raise SystemExit("a GEXREV session is not on the book index - abort")
    dates5 = pd.DatetimeIndex(es.S.dates)
    wf5 = np.asarray((dates5 >= WF0) & (dates5 <= WF1))
    F.legs, F.X, F.T = book_legs(B, ref)
    F.U = U = pd.DatetimeIndex(sorted(set(days[wf]) | set(dates5[wf5])))
    F.pU = state(U, g)[1]
    if not np.isfinite(F.pU).all():
        raise SystemExit("a WF ES session has no GEX state - abort")
    F.yU = {y: np.flatnonzero(U.year == y) for y in sorted(set(U.year))}
    F.ia = U.get_indexer(days)
    F.ib = {nm: U.get_indexer(pd.DatetimeIndex(t["session"])) for nm, t in F.b.items()}
    F.ic = U.get_indexer(bdays)
    for k, df in F.T.items():
        off = int((F.ic[df.bi.to_numpy()] < 0).sum())
        print("  %s WF trades on a day outside the ES session calendar (never gated): %d" % (k, off))
    F.L = {k: np.bincount(df.bi.to_numpy(), weights=df.usd.to_numpy(), minlength=len(bdays)) for k, df in F.T.items()}
    for k in F.L:
        if np.abs(F.L[k] - F.X[k]).max() >= 0.005:
            raise SystemExit("%s: entry-day dollars differ from its valued-daily marks - abort" % k)
    return F


def pmap(pU, idx):
    return np.where(idx >= 0, pU[np.maximum(idx, 0)], np.nan)


def cell_a(F, pU, thr):
    sel = F.a_trade & (pmap(pU, F.ia) <= thr)
    return np.bincount(F.a_bi[sel], weights=F.a_pnl[sel], minlength=len(F.bdays)), sel


def cell_b(F, pU, nm):
    sel = pmap(pU, F.ib[nm]) >= 2.0 / 3.0
    return np.bincount(F.b_bi[nm][sel], weights=F.b[nm]["net_usd"].to_numpy(float)[sel], minlength=len(F.bdays)), sel


def cell_c(F, pU, thr, size, keys=C_LEGS):
    rem = pmap(pU, F.ic) >= thr
    L = sum(F.L[k] for k in keys)
    return F.Bx - (1.0 - size) * L * rem, rem


def family(F, pU):
    """Own ROC@30k of the four A / B cells and ROC gain over #463 of the three C cells, on one labelling."""
    bd = F.bdays
    r0 = BL.own(F.Bx, bd)["roc"]
    v = {"A primary": BL.own(cell_a(F, pU, 1.0 / 3.0)[0], bd)["roc"],
         "A neighbour": BL.own(cell_a(F, pU, 0.25)[0], bd)["roc"],
         "B1": BL.own(cell_b(F, pU, "B1")[0], bd)["roc"], "B2": BL.own(cell_b(F, pU, "B2")[0], bd)["roc"]}
    for nm, thr, size in C_CELLS:
        v[nm] = BL.own(cell_c(F, pU, thr, size)[0], bd)["roc"] - r0
    return v


def shuffle(F, pU, rng):
    out = pU.copy()
    for y, ix in F.yU.items():
        out[ix] = pU[ix][rng.permutation(len(ix))]
    return out


def run_null(F):
    from research_beacon import beacon
    rng = np.random.default_rng(SEED)
    rows = []
    with beacon("GAMMA r1 Stage A family null", total=NULL_DRAWS) as b:
        for i in range(NULL_DRAWS):
            rows.append(family(F, shuffle(F, F.pU, rng)))
            b.step(i + 1)
    return pd.DataFrame(rows)


def jy_n(days):
    j = BL.jy(pd.DatetimeIndex(days)) if len(days) else np.array([], int)
    return [int((j == y).sum()) for y in range(2016, 2025)]


def judge_ab(F, name, x, xn, tusd, tdays, tside, tprice, p95):
    """Stage A bars A1, A1b, A2, A3, A4 and the counts line for one arm's primary (prereg 'Stage A bars'), then the
    reported diagnostics. Returns the verdict string."""
    bd, B, years = F.bdays, F.B, F.years
    st = BL.own(x, bd)
    n, pf = len(tusd), pf_of(tusd)
    yrs = BL.july_june(x, bd)
    ny = jy_n(tdays)
    print("  %s: %d WF trades (%.1f a year), net %s, PF %.3f, $/trade %.0f, own %s, Sortino %.3f, $ a year %s" % (
        name, n, n / years, fm(st["net"]), pf, st["net"] / max(n, 1), roc_txt(x, bd, st), st["sort"],
        fm(st["net"] / st["years"])))
    print("    per July-June year net: " + ", ".join("%s %s (%d%s)" % (BL.jy_label(y), fm(v), c, " THIN" if c < THIN else "")
                                                   for y, v, c in zip(range(2016, 2025), yrs, ny)))
    a1, no2020, route = HH.standalone(st, pf, n, years, yrs, x, bd, B, name)
    counts = n >= 100 and n / years >= 50
    a1_rest = route != "neither route" and pf > 1 and sum(v > 0 for v in yrs) >= 6
    a2 = st["roc"] > p95
    a3 = float(np.sum(xn)) > 0
    exbest = st["net"] - (float(np.max(tusd)) if n else 0.0)
    cost2 = st["net"] - n * COST * M
    a4 = exbest > 0 and cost2 > 0
    print("    A1 standalone (%s; PF %.3f > 1; %d of 9 July-June years positive >= 6; counts >= 100 and >= 50 a year %s): %s"
          % (route, pf, sum(v > 0 for v in yrs), "MET" if counts else "MISSED", "PASS" if a1 else "FAIL"))
    print("    A1b without 2020: %s" % ("PASS" if no2020 else "FAIL"))
    print("    A2 own ROC %.2f > family null p95 %.2f: %s" % (st["roc"], p95, "PASS" if a2 else "FAIL"))
    print("    A3 neighbour net %s > 0: %s" % (fm(float(np.sum(xn))), "PASS" if a3 else "FAIL"))
    print("    A4 net without the best trade %s; net at 2x cost %s: %s" % (fm(exbest), fm(cost2), "PASS" if a4 else "FAIL"))
    ok = a1 and no2020 and a2 and a3 and a4
    if ok:
        verdict = "PASS"
    elif (not counts) and a1_rest and no2020 and a2 and a3 and a4:
        verdict = "RESEARCH ROW (count-only miss)"
    else:
        verdict = "FAIL"
    print("    VERDICT %s: %s" % (name, verdict))
    print("    reported (no verdict):")
    for lab, a, b_ in (("2016-21", WF0, H1_END), ("2022-25", H2_START, WF1)):
        m = np.asarray((bd >= a) & (bd <= b_))
        s2 = BL.own(x[m], bd[m])
        print("      %s: net %s, own %s" % (lab, fm(float(x[m].sum())), roc_txt(x[m], bd[m], s2)))
    print("      long %d trades net %s / short %d trades net %s" % (
        int((tside > 0).sum()), fm(float(tusd[tside > 0].sum())), int((tside < 0).sum()), fm(float(tusd[tside < 0].sum()))))
    print("      cost curve (extra cost per trade = bps x entry price x $50): " + ", ".join(
        "%d bps net %s" % (bps, fm(float(tusd.sum() - (bps / 1e4 * tprice * M).sum()))) for bps in (0, 5, 10, 20)))
    RD = r_days()
    print("      dollars on R days %s" % fm(float(x[np.asarray(bd.isin(RD))].sum())))
    HH.book_report(x, B, years, name)
    sides = {}
    for k, df in F.T.items():
        for d, s in zip(df.day, df.side):
            sides.setdefault((k, d), set()).add(s)
    same = [any(s in sides.get((k, d), ()) for k in C_LEGS) for d, s in zip(pd.DatetimeIndex(tdays), tside)]
    print("      day-level overlap: %.0f%% of its trades fall on a day ORB or NOISE entered the same side" % (
        100.0 * np.mean(same) if len(same) else 0.0))
    return verdict


def leg_split_rows(F, rem, label):
    print("  %s - each leg's WF trades by ENTRY day: removed (long-gamma) days vs other days" % label)
    for k in C_LEGS + ("ORB+NOISE",):
        df = pd.concat([F.T[j] for j in C_LEGS]) if k == "ORB+NOISE" else F.T[k]
        on = rem[df.bi.to_numpy()]
        for lab, m in (("long-gamma", on), ("other", ~on)):
            u = df.usd.to_numpy()[m]
            print("    %-10s %-10s net %10s  trades %5d  PF %6.3f  $/trade %7.1f" % (
                k, lab, fm(float(u.sum())), len(u), pf_of(u), float(u.mean()) if len(u) else float("nan")))


def judge_c(F, pU, p95, ref):
    bd, years = F.bdays, F.years
    r0 = ref["roc"]
    s0 = BL.own(F.Bx, bd)
    print("\nARM C - GEXGATE (ORB #234 and NOISE #422 stand down on long-gamma days; ENGU-Q and TTM unchanged)")
    xC1, rem = cell_c(F, pU, 2.0 / 3.0, 0.0)
    _, rem3 = cell_c(F, pU, 0.75, 0.0)
    print("  removed days: C1 / C2 (p >= 2/3) %d WF book days, C3 (p >= 3/4) %d" % (int(rem.sum()), int(rem3.sum())))
    leg_split_rows(F, rem, "FIRST NUMBER (binding), C1 days")
    leg_split_rows(F, rem3, "C3 days (top quartile)")
    for nm, thr, size in C_CELLS:                                       # the fast path equals the engine path
        xf, rm = cell_c(F, pU, thr, size)
        xe = gated_engine(F.B, F.legs, F.X, bd[rm], size)
        d = float(np.abs(xf - xe).max())
        if d >= 0.005:
            raise SystemExit("ARM C %s: the fast path differs from the engine path by $%.4f - abort" % (nm, d))
    print("  engine path (augur_engine.book_sizing.resize) == the null's fast path to the cent on C1, C2, C3: asserted")
    L = F.L["ORB"] + F.L["NOISE"]
    on_net = float((L * rem).sum())
    a1 = on_net < 0
    s1 = BL.own(xC1, bd)
    a2 = s1["roc"] > r0 and s1["net"] / s1["years"] > s0["net"] / s0["years"]
    gain = s1["roc"] - r0
    a3 = gain > p95
    hh = []
    for lab, a, b_ in (("2016-21", WF0, H1_END), ("2022-25", H2_START, WF1)):
        m = np.asarray((bd >= a) & (bd <= b_))
        hh.append((lab, float((L * rem)[m].sum())))
    ex20 = float((L * rem)[np.asarray(bd.year != 2020)].sum())
    dayv = (L * rem)[rem]
    exworst = float(dayv.sum() - dayv.min()) if len(dayv) else 0.0
    a4 = all(v < 0 for _, v in hh) and ex20 < 0 and exworst < 0
    trd = pd.concat([F.T[j] for j in C_LEGS])
    rtr = trd[rem[trd.bi.to_numpy()]]
    ny = jy_n(rtr.day)
    a5 = len(rtr) >= 100 and min(ny) >= 25
    on3 = float((L * rem3).sum())
    a6 = on3 < 0
    print("  #463          WF %s  Sortino %.3f  net %s  $ a year %s" % (roc_txt(F.Bx, bd, s0), s0["sort"], fm(s0["net"]),
                                                                       fm(s0["net"] / s0["years"])))
    for nm, thr, size in C_CELLS:
        x, _ = cell_c(F, pU, thr, size)
        s = BL.own(x, bd)
        print("  #463 + %s     WF %s  Sortino %.3f  net %s  $ a year %s  gain %+.2f%s" % (
            nm, roc_txt(x, bd, s), s["sort"], fm(s["net"]), fm(s["net"] / s["years"]), s["roc"] - r0,
            "  (judged)" if nm == "C1" else ""))
    for k in C_LEGS:
        x, _ = cell_c(F, pU, 2.0 / 3.0, 0.0, keys=(k,))
        s = BL.own(x, bd)
        print("  REPORT %-5s only, C1 days: WF %s  Sortino %.3f  net %s  gain %+.2f" % (
            k, roc_txt(x, bd, s), s["sort"], fm(s["net"]), s["roc"] - r0))
    print("  C-A1 ORB + NOISE WF net on long-gamma days %s < 0: %s" % (fm(on_net), "PASS" if a1 else "FAIL"))
    print("  C-A2 #463+C1 ROC %.2f > %.2f AND $ a year %s > %s: %s" % (
        s1["roc"], r0, fm(s1["net"] / s1["years"]), fm(s0["net"] / s0["years"]), "PASS" if a2 else "FAIL"))
    print("  C-A3 gain %+.2f > family null p95 %.2f: %s   (71-look chance band, report: %s; gain %+.1f%%)" % (
        gain, p95, "PASS" if a3 else "FAIL", LOOK_BAND, 100.0 * gain / r0))
    print("  C-A4 removed-day net: %s; without 2020 %s; without the single worst removed day %s: %s" % (
        ", ".join("%s %s" % (a, fm(v)) for a, v in hh), fm(ex20), fm(exworst), "PASS" if a4 else "FAIL"))
    print("  C-A5 removed WF trades %d (>= 100); per July-June year %s (each >= 25): %s" % (
        len(rtr), ", ".join("%s %d%s" % (BL.jy_label(y), c, " THIN" if c < 25 else "") for y, c in zip(range(2016, 2025), ny)),
        "PASS" if a5 else "FAIL"))
    print("  C-A6 C3 removed-day net %s < 0: %s" % (fm(on3), "PASS" if a6 else "FAIL"))
    verdict = "PASS" if (a1 and a2 and a3 and a4 and a5 and a6) else "FAIL"
    print("  VERDICT ARM C (C1): %s" % verdict)
    v = vix_prior(bd)
    wfv = v[np.isfinite(v)]
    q1, q2 = np.quantile(wfv, [1 / 3.0, 2 / 3.0])
    tv = np.where(v <= q1, 0, np.where(v <= q2, 1, 2))
    print("  VIX confound (report): prior-close VIX terciles over WF book days, cuts %.2f / %.2f" % (q1, q2))
    for i, lab in enumerate(("low VIX", "mid VIX", "high VIX")):
        m = tv == i
        print("    %-8s long-gamma days %4d of %4d; ORB+NOISE net long-gamma %10s, other days %10s" % (
            lab, int((rem & m).sum()), int(m.sum()), fm(float((L * (rem & m)).sum())), fm(float((L * (~rem & m)).sum()))))
    return verdict


def stage_a(argv):
    dry = "--dry" in argv
    check_hashes()
    B, ref = HH.book()
    bd = pd.DatetimeIndex(B.index)
    print("BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f  (%s)" % (ref["roc"], ref["sort"], dd5_txt(B.to_numpy(), bd)))
    es = es5()
    balance_parity(es, bd)
    g, prov = gex()
    print("GEX photograph sha256 %s.. verified, %d GEX days to %s" % (prov["sha256"][:8], len(g), g.index[-1].date()))
    F = build(B, ref, es, g)
    pU = F.pU
    if dry:
        pU = shuffle(F, F.pU, np.random.default_rng(SEED + 99))
        print("*** DRY RUN: the real labels are REPLACED by one shuffled draw - no real gamma-conditioned return ***")
    else:                                                               # the counts the prereg froze, re-derived
        st = np.where(pU <= 1 / 3.0, -1, np.where(pU >= 2 / 3.0, 1, 0))
        nA = int(cell_a(F, pU, 1.0 / 3.0)[1].sum())
        nB = int(cell_b(F, pU, "B1")[1].sum())
        if (nA, nB) != (582, 608):
            raise SystemExit("counts drift: GEXEXP %d (582), GEXREV B1 %d (608) - abort" % (nA, nB))
        sch = gexrev_schedule(es, es.trading & (state(pd.DatetimeIndex(es.S.dates), g)[0] == 1), 0.5)
        sd = pd.DatetimeIndex(sch.session)
        sch = sch[np.asarray((sd >= WF0) & (sd <= WF1))]
        sel = F.b["B1"][cell_b(F, pU, "B1")[1]]
        if not (np.array_equal(pd.DatetimeIndex(sch.session).values, pd.DatetimeIndex(sel.session).values)
                and np.array_equal(sch.fill_stamp.values, sel.fill_stamp.values)):
            raise SystemExit("GEXREV selected-from-all differs from the masked run - abort")
        print("  counts re-derived: GEXEXP 582, GEXREV B1 608; GEXREV select-from-all == masked run; ES state days: short "
              "%d, long %d" % (int((st == -1).sum()), int((st == 1).sum())))
    print("\nFAMILY NULL: within-calendar-year shuffles of the session percentile on the ES WF calendar (%d sessions), "
          "%d draws, seed %d; family max over A primary, A neighbour, B1, B2 (own ROC@30k) and C1, C2, C3 (ROC gain over "
          "#463)" % (len(F.U), NULL_DRAWS, SEED))
    N = run_null(F)
    fam = N.max(axis=1, skipna=True)
    fam_ab = N[["A primary", "A neighbour", "B1", "B2"]].max(axis=1, skipna=True)
    p95 = float(np.percentile(fam, 95))
    print("  family max p95 %.2f (median %.2f); without the C cells p95 %.2f (report)" % (
        p95, float(fam.median()), float(np.percentile(fam_ab, 95))))
    print("  per-cell null p95 (report): " + ", ".join("%s %.2f" % (c, float(np.nanpercentile(N[c], 95))) for c in N.columns))
    real = family(F, pU)
    print("  real (%s): " % ("DRY draw" if dry else "real labels") + ", ".join("%s %.2f" % (c, v) for c, v in real.items()))
    print("\nARM A - GEXEXP (ES 30m, short-gamma days)")
    xa, sa = cell_a(F, pU, 1.0 / 3.0)
    xn, _ = cell_a(F, pU, 0.25)
    va = judge_ab(F, "GEXEXP primary", xa, xn, F.a_pnl[sa], F.a_days[sa], F.a_side[sa], F.a_price[sa], p95)
    print("  neighbour (bottom quartile): own %s, net %s" % (roc_txt(xn, bd), fm(float(xn.sum()))))
    for lab, m in (("ALL sessions", F.a_trade), ("LONG-gamma days", F.a_trade & (pmap(pU, F.ia) >= 2 / 3.0))):
        xt = np.bincount(F.a_bi[m], weights=F.a_pnl[m], minlength=len(bd))
        print("  TWIN %s: %d trades, net %s, own %s" % (lab, int(m.sum()), fm(float(xt.sum())), roc_txt(xt, bd)))
    print("\nARM B - GEXREV (ES 5m, long-gamma days)")
    xb, sb = cell_b(F, pU, "B1")
    xb2, _ = cell_b(F, pU, "B2")
    t1 = F.b["B1"][sb]
    vb = judge_ab(F, "GEXREV B1", xb, xb2, t1.net_usd.to_numpy(float), t1.session, t1.side.to_numpy(float),
                  t1.entry.to_numpy(float), p95)
    print("  neighbour B2: own %s, net %s" % (roc_txt(xb2, bd), fm(float(xb2.sum()))))
    pb = pmap(pU, F.ib["B1"])
    for lab, m in (("ALL sessions", np.ones(len(pb), bool)), ("SHORT-gamma days", pb <= 1 / 3.0)):
        xt = np.bincount(F.b_bi["B1"][m], weights=F.b["B1"].net_usd.to_numpy(float)[m], minlength=len(bd))
        print("  TWIN %s B1: %d trades, net %s, own %s" % (lab, int(m.sum()), fm(float(xt.sum())), roc_txt(xt, bd)))
    vc = judge_c(F, pU, p95, ref)
    print("\nSUMMARY%s: ARM A GEXEXP %s; ARM B GEXREV %s; ARM C GEXGATE %s" % (" (DRY)" if dry else "", va, vb, vc))


def main(argv):
    if "--stageA" in argv:
        stage_a(argv)
        return
    if "--armc-parity" in argv:
        B, ref = HH.book()
        book_legs(B, ref)
        return
    arm_b = any(a in argv for a in ("--parity", "--counts", "--power"))
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    es = None
    if arm_b:                                                           # PARITY FIRST, before any gamma number
        es = es5()
        balance_parity(es, bdays)
        if not any(a in argv for a in ("--counts", "--power")):
            return
    g, prov = gex()
    days_a, side_a = arm_a(argv, g, prov, B, ref)
    if es is None:
        return
    st5, pct5 = state(pd.DatetimeIndex(es.S.dates), g)
    cells = arm_b_counts(es, st5, pct5, bdays, years, days_a, side_a)
    if "--power" in argv:
        arm_b_power(cells["B1"], B, years)


if __name__ == "__main__":
    main(sys.argv[1:])
