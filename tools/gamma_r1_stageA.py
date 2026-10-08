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
  python tools/gamma_r1_stageA.py --stageA   -> refuses: GAMMA Stage A waits for the owner GO via MANAGER
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
STAGE_A_MSG = "GAMMA Stage A waits for the owner GO via MANAGER"
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


def main(argv):
    if "--stageA" in argv or "--run" in argv:
        print(STAGE_A_MSG)
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
