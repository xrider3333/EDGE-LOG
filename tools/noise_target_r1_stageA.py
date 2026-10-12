# -*- coding: utf-8 -*-
"""NOISE TARGET r1 - Stage A (docs/PREREG_noise_target_r1_2026-10-12.md; owner order 10-12 via MANAGER #86, OWNER OVERRIDE of the
power-first gate 10-12 via MANAGER #89). WF ONLY.

Can a profit target buy NOISE a higher win rate without cutting ROC? NOISE_1_0.py (the #304 core that NOISE #382 and #422
share) is patched IN MEMORY (nothing on disk changes) with a resting profit target at TP_R x R from the fill, R = fill to
the trade's own initial bandwidth stop:
  T25   full exit at +0.25R (the scalp)          SO25  half off at +0.25R, the other half rides NOISE's normal exit
  T100  full exit at +1.0R (round 37's 1R)       neighbours: T25 <-> SO25, T100 <-> T200 (+2.0R, printed for the plateau)
Fill rules: the target is checked inside every bar AFTER the fill bar (the engine's own stop rule), after the stop - a bar
that touches both fills the stop. A bar opening through the target fills at that open. A full exit frees the slot for the
next break (re-simulated). SO25's half is recorded at its touch while the position stays open; the trade's P&L is then
0.5 x the half + 0.5 x the rest, each half paying its own exit (cost per contract unchanged).
Legs keep their size rule (s x net per trade): #382 = 2.0x on the 30-minute gate (16, 1.15); #422 = 1.75x on the 60-minute
gate (20, 1.15). Cost 0.783 pt (commission + one tick each side; the bar's cost) and 0.533 (house, reported).
Signal dates 2016-07-01 .. 2025-06-29 (the book's WF); the lockbox is not read.

BARS (per leg, cost 0.783): beat the leg's own WF ROC@30k AND daily Sortino; month-block bootstrap P(delta ROC > 0) >= 0.90
(2,000 draws, seed 20261012, paired: the same months for both); its neighbour's delta ROC > 0. Printed beside every cell:
the four numbers (ROC@30k, DD5, DD% from the peak on $100k, Sortino), win rate, avg win / avg loss, trades, PF.

  python noise_target_r1_stageA.py --parity     the patched file at target = off must rebuild #304 / #382 / #422 (sizes too,
                                                addendum 1: the gate read on the engine's own ratio-adjusted arrays)
  python noise_target_r1_stageA.py              Stage A (refuses unless the prereg's LF hash matches its pin; the harness's own hash is posted)
"""
import argparse
import hashlib
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DRAFT = os.path.join(os.path.dirname(HERE), "docs", "PREREG_noise_target_r1_2026-10-12.md")
PINS = {"draft": "619f6ef083111fef52e047783501f3c45aba41bd5489deaf48bb7e1971fb092b"}   # the prereg's LF sha256 (witness branch prereg/noise-target-1012)
W0, W1 = pd.Timestamp("2016-07-01").date(), pd.Timestamp("2025-06-29").date()
YRS = 8.994
COST, COST_HOUSE = 0.783, 0.533
CELLS = (("base", None, "full"), ("T25", 0.25, "full"), ("SO25", 0.25, "half"), ("T100", 1.0, "full"),
         ("T200", 2.0, "full"))
NEIGHBOUR = {"T25": "SO25", "SO25": "T25", "T100": "T200"}
SEED, DRAWS = 20261012, 2000
SRC_PATH = os.path.join(REPO, "augur_strategies", "NOISE_1_0.py")
SRC = open(SRC_PATH, encoding="utf-8").read()
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def build(tp_r, mode):
    s = SRC
    if tp_r:
        anchor = "            # STEP B -- boundary-mode intrabar exit (checked while in a position).\n"
        assert s.count(anchor) == 1, "STEP B anchor not unique"
        patch = (
            "            if pos != 0 and k != entry_k and stop_level is not None and not np.isnan(stop_level):\n"
            "                _tgt = entry_px + pos * TP_R * abs(entry_px - stop_level)\n"
            "                _hit = (so[k] >= _tgt or sh[k] >= _tgt) if pos > 0 else (so[k] <= _tgt or sl[k] <= _tgt)\n"
            "                if _hit and abs(entry_px - stop_level) > 0:\n"
            "                    _px = (so[k] if so[k] >= _tgt else _tgt) if pos > 0 else (so[k] if so[k] <= _tgt else _tgt)\n"
            "                    _pnl = (_px - entry_px) if pos > 0 else (entry_px - _px)\n"
            "                    if TP_MODE == 'half':\n"
            "                        _TP['half'].setdefault(a + entry_k, _pnl)\n"
            "                    else:\n"
            "                        pnl_list.append(_pnl)\n"
            "                        if return_trades: trade_log.append((a + entry_k, a + k, _pnl, pos, entry_px))\n"
            "                        _TP['n'] += 1\n"
            "                        pos = 0\n")
        s = s.replace(anchor, patch + anchor)
    m = types.ModuleType("noise_target_r1_%s_%s" % (tp_r, mode))
    m.__file__ = SRC_PATH
    exec(compile(s, SRC_PATH, "exec"), m.__dict__)
    m.TP_R, m.TP_MODE = tp_r, mode
    m._TP = {"half": {}, "n": 0}
    return m


def run(m, cost):
    r = run_backtest(m, arrays=R.A, params=R.CROWN, cost_pts=cost, return_trades=True)
    tr = sorted(r["trades"], key=lambda z: int(z[0]))
    if getattr(m, "TP_MODE", "full") == "half":
        h = m._TP["half"]
        tr = [(t[0], t[1], 0.5 * (h[int(t[0])] - cost) + 0.5 * float(t[2]) if int(t[0]) in h else float(t[2])) + tuple(t[3:])
              for t in tr]
    return tr


CAP = {}


def engine_arrays():
    """ADDENDUM 1 (post-data parity fix, disclosed): the arrays the engine actually hands a strategy. Since the 10-08 roll
    guard it runs signals on a ratio-adjusted series, so the squeeze gate (and so each leg's size) must be read on those
    arrays, not on the raw master - run 1 read it on raw prices and mis-sized 9 (#422) / 14 (#382) WF trades."""
    if CAP:
        return CAP
    import functools
    m = build(None, "full")
    orig = m.run_backtest

    @functools.wraps(orig)
    def probe(opens, highs, lows, closes, *args, **kw):
        CAP.update(high=np.asarray(highs, float), low=np.asarray(lows, float), close=np.asarray(closes, float),
                   day_id=kw.get("day_id"), index=kw.get("index"))
        return orig(opens, highs, lows, closes, *args, **kw)
    m.run_backtest = probe
    run_backtest(m, arrays=R.A, params=R.CROWN, cost_pts=0.0, return_trades=True)
    assert CAP and CAP["day_id"] is not None, "could not capture the engine's strategy arrays"
    if CAP["index"] is None:
        CAP["index"] = R.A["index"]
    return CAP


def sizes(tr, gate):
    if gate is None:
        return np.ones(len(tr))
    tf, ln, ratio, tilt = gate
    E = engine_arrays()
    comp = R.SQ._compression(E["high"], E["low"], E["close"], np.asarray(E["day_id"]), E["index"], tf, ln, ratio)
    return np.array([tilt if bool(comp[int(t[0]) - 1]) else 1.0 for t in tr])


def wf(tr, s):
    d = np.array([R.IDX[int(t[0]) - 1].date() for t in tr])
    m = (d >= W0) & (d <= W1)
    return d[m], (s * np.array([float(t[2]) for t in tr]))[m] * R.M


SESS = None


def four(dates, pnl):
    daily = pd.Series(pnl, index=dates).groupby(level=0).sum().reindex(SESS, fill_value=0.0)
    x = daily.to_numpy()
    cum = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum))
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    w, l = pnl[pnl > 0], pnl[pnl < 0]
    return dict(roc=30 * (cum[-1] / YRS) / mdd, dd5=dd5(daily), ddp=dd_pct_peak(daily), so=x.mean() / dn * np.sqrt(len(x) / YRS),
                n=len(pnl), win=100 * len(w) / len(pnl), aw=w.mean(), al=-l.mean(), pf=w.sum() / -l.sum(), daily=x)


def line(lab, f):
    return ("  %-6s ROC@30k %6.2f  DD5 $%6.0f%s  DD%% %5.2f  Sortino %4.2f | trades %4d  win %4.1f%%  avg win $%5.0f  avg loss"
            " $%5.0f (%.2fx)  PF %.3f" % (lab, f["roc"], f["dd5"]["dd5_usd"], " (1 EP)" if f["dd5"]["one_episode"] else "     ",
                                          f["ddp"], f["so"], f["n"], f["win"], f["aw"], f["al"], f["aw"] / f["al"], f["pf"]))


def boot(xb, xv):
    m = pd.PeriodIndex(pd.DatetimeIndex(SESS), freq="M")
    blocks = [np.flatnonzero(m == u) for u in m.unique()]
    rng = np.random.default_rng(SEED)

    def roc(x):
        c = np.cumsum(x)
        return 30 * (c[-1] / YRS) / max(np.max(np.maximum.accumulate(np.r_[0., c])[1:] - c), 1.0)
    out = []
    for _ in range(DRAWS):
        ix = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
        out.append(roc(xv[ix]) - roc(xb[ix]))
    return float((np.array(out) > 0).mean()), float(np.std(out))


def main():
    global SESS
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity", action="store_true")
    a = ap.parse_args()
    SESS = pd.Index(sorted({R.IDX[i].date() for i in range(len(R.IDX)) if W0 <= R.IDX[i].date() <= W1}))
    base = build(None, "full")
    tb = run(base, COST_HOUSE)
    ref = sorted(run_backtest(R.load("NOISE_1_0.py"), arrays=R.A, params=R.CROWN, cost_pts=COST_HOUSE,
                              return_trades=True)["trades"], key=lambda z: int(z[0]))
    assert [(int(x[0]), int(x[1]), round(float(x[2]), 6)) for x in tb] == \
           [(int(x[0]), int(x[1]), round(float(x[2]), 6)) for x in ref], "PARITY: patched-off != NOISE_1_0 #304"
    for name, fn, params, gate in ((nm, fn, p, g) for nm, fn, p, g in R.LEGS):
        e = sorted(run_backtest(R.load(fn), arrays=R.A, params=params, cost_pts=COST_HOUSE, return_trades=True)["trades"],
                   key=lambda z: int(z[0]))
        assert [(int(x[0]), int(x[1])) for x in e] == [(int(x[0]), int(x[1])) for x in tb], "PARITY: %s entries/exits" % name
        sz = sizes(tb, gate)
        es = np.array([float(x) for x in run_backtest(R.load(fn), arrays=R.A, params=params, cost_pts=0.0,
                                                       return_trades=True)["trade_sizes"]])
        eo = np.argsort([int(x[0]) for x in run_backtest(R.load(fn), arrays=R.A, params=params, cost_pts=0.0,
                                                          return_trades=True)["trades"]], kind="stable")
        assert np.array_equal(es[eo], sz), "PARITY: %s sizes differ from the engine's (%d)" % (name, int((es[eo] != sz).sum()))
        print("PARITY %s: %d trades, entries, exits and sizes identical to the engine; sizes %s" % (
            name, len(e), dict(zip(*np.unique(sz, return_counts=True)))))
    print("PARITY #304 core: %d trades identical to the cent (patched file, target off)" % len(tb))
    if a.parity:
        return
    pins = {"draft": lf(DRAFT), "harness": lf(os.path.abspath(__file__))}
    print("PINS: draft LF %s; harness LF %s" % (pins["draft"], pins["harness"]))
    if PINS["draft"] is None or pins["draft"] != PINS["draft"]:
        raise SystemExit("refused: the draft is not the frozen one (nothing computed)")
    for name, fn, params, gate in R.LEGS:
        print("\n%s - WF %s .. %s, cost %.3f (house %.3f in brackets for base)" % (name, W0, W1, COST, COST_HOUSE))
        res = {}
        for lab, tp, mode in CELLS:
            tr = run(build(tp, mode), COST)
            d, p = wf(tr, sizes(tr, gate))
            res[lab] = four(d, p)
            print(line(lab, res[lab]))
        d, p = wf(tb, sizes(tb, gate))
        print("  (base at the house cost: ROC@30k %.2f, Sortino %.2f)" % (four(d, p)["roc"], four(d, p)["so"]))
        for lab in ("T25", "SO25", "T100"):
            pr, sd = boot(res["base"]["daily"], res[lab]["daily"])
            v, b = res[lab], res["base"]
            nb = res[NEIGHBOUR[lab]]["roc"] - b["roc"]
            ok = v["roc"] > b["roc"] and v["so"] > b["so"] and pr >= 0.90 and nb > 0
            print("  %-5s delta ROC %+6.2f  delta Sortino %+5.2f  P(delta>0) %.2f (SD %.1f)  neighbour delta %+6.2f  win %+5.1f pts"
                  "  -> %s" % (lab, v["roc"] - b["roc"], v["so"] - b["so"], pr, sd, nb, v["win"] - b["win"],
                               "PASS" if ok else "FAIL"))


if __name__ == "__main__":
    main()
