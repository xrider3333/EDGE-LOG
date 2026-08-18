"""t8 - NOISE-in-the-BOOK: does a better NOISE leg make a better BOOK, and does NOISE
earn a permanent slot next to the owner's ORB x ENGU-Q baseline?

Everything here is computed LOCALLY through the same engine the runner uses, pooling
per-leg trades by EXIT DATE into one account exactly the way augur_engine/book.py does
(verified against augur_engine.run_book on run #238's exact legs - see --verify).

WINDOWS (pinned, never blank):
  5m-only books (ORB + NOISE)          : 2010-06-07 -> 2026-08-12   (run #238's window)
  books containing an ENGU-Q 1m leg    : 2010-06-07 -> 2026-06-30   (the 1m RTH master
      has a REAL 3-week hole 2026-07-17 -> 2026-08-05; anything spanning it is invalid)

LOCKBOX SLICES (both reported; a BOOK lockbox is only as unseen as its most-recently
frozen leg):
  LB238 = from 2025-02-10  - run #238's own boundary (NOISE's 18-month lockbox)
  LB234 = from 2025-08-13  - ORB crown #234's lockbox start = the STRICTEST date by
                              which every leg's params were already frozen

Run:  python tools/t8_noise_book.py            (full round)
      python tools/t8_noise_book.py --verify   (engine-parity gates only)
"""
from __future__ import annotations
import sys
import pathlib
import importlib.util
import argparse
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402

COST, MULT = 0.533, 20.0
W5_TO = "2026-08-12"      # 5m-only books
W1_TO = "2026-06-30"      # books with a 1m leg (data hole guard)
FROM = "2010-06-07"
LB238 = pd.Timestamp("2025-02-10")
LB234 = pd.Timestamp("2025-08-13")


def _defaults(fn):
    sp = importlib.util.spec_from_file_location("m", REPO / "augur_strategies" / fn)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def _mod(fn):
    sp = importlib.util.spec_from_file_location("m2", REPO / "augur_strategies" / fn)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


ENG149 = _mod("ENGUQ_1M_1_0.py").NQ_DEPLOY_PARAMS_149
# run #238's NOISE leg (the D3 filter winner) is NOT one of the pinned NOISE_1_1_* files,
# so it is expressed here as NOISE_1_0 + #238's own saved params, verbatim from the job doc.
D3 = {"lookback": 44, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
      "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
      "stop_mode": "bandwidth", "stop_k": 1.75, "confirm_bars": 2,
      "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
      "vol_skip_pct": 0.0}
C221 = {"skip_holidays": True, "close_confirm": True, "vpace_filter": 0.7,
        "breakout_buf": 0.25, "flat_eod": True, "or_bars": 2, "stop_frac": 2.0,
        "trail_bars": 3, "target_R": 5.5, "partial_exit_R": 3.0,
        "trade_mode": "First-candle dir", "atr_filter": 0.7}

LEGS = {
    "ORB_C2":   ("ORB_3_6_C2.py",        "NQ", "5m", "rth", None),   # run #234 = the crown
    "ORB_C221": ("ORB_3_4_C221.py",      "NQ", "5m", "rth", C221),   # run #230, #238's leg
    "ENGQ_RTH": ("ENGUQ_1M_1_0.py",      "NQ", "1m", "rth", ENG149),
    "N_BASE":   ("NOISE_1_1_BASE.py",    "NQ", "5m", "rth", None),
    "N_SBS":    ("NOISE_1_1_SBS.py",     "NQ", "5m", "rth", None),
    "N_SBSV90": ("NOISE_1_1_SBS_V90.py", "NQ", "5m", "rth", None),
    "N_SBA":    ("NOISE_1_1_SBA.py",     "NQ", "5m", "rth", None),
    "N_V98":    ("NOISE_1_1_V98.py",     "NQ", "5m", "rth", None),
    "N_D3":     ("NOISE_1_0.py",         "NQ", "5m", "rth", D3),     # run #238's NOISE leg
}

_CACHE = {}


def run_leg(key, date_to):
    """One leg over one window -> (daily $ Series, list of per-trade $, raw result)."""
    ck = (key, date_to)
    if ck in _CACHE:
        return _CACHE[ck]
    fn, inst, tf, sess, prm = LEGS[key]
    prm = prm if prm is not None else _defaults(fn)
    arr = load_master_arrays(find_master(inst, tf, sess), date_from=FROM, date_to=date_to)
    r = run_backtest(fn, arrays=arr, params=prm, cost_pts=COST, return_trades=True)
    idx = np.asarray(arr["index"], dtype="datetime64[D]")
    last = len(idx) - 1
    days, dollars = [], []
    for t in (r.get("trades") or []):
        days.append(idx[min(int(t[1]), last)])
        dollars.append(float(t[2]) * MULT)
    s = pd.Series(dollars, index=pd.to_datetime(days)).groupby(level=0).sum().sort_index()
    out = (s, dollars, r)
    _CACHE[ck] = out
    return out


def _stats(daily, pnls, lb_from):
    """Book metrics the same way augur_engine/book.py computes them: PF trade-level over
    the pooled pile, drawdown on the DAILY account curve, reported positive."""
    cum = daily.cumsum()
    dd = abs(float((cum - cum.cummax()).min())) if len(cum) else 0.0
    net = float(daily.sum())
    gw = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    lb = daily[daily.index >= lb_from]
    lbc = lb.cumsum()
    lbdd = abs(float((lbc - lbc.cummax()).min())) if len(lb) else float("nan")
    pre = daily[daily.index < lb_from]
    parts = np.array_split(np.arange(len(daily)), 8)
    sl = [float(daily.iloc[p].sum()) for p in parts]
    return {"net": net, "pf": (gw / gl if gl > 1e-9 else float("inf")),
            "dd": dd, "mar": (net / dd if dd else float("nan")),
            "n": len(pnls), "held": sum(1 for x in sl if x > 0),
            "pre_net": float(pre.sum()),
            "lb_net": float(lb.sum()), "lb_dd": lbdd,
            "lb_mar": (float(lb.sum()) / lbdd if lbdd and lbdd == lbdd else float("nan"))}


def book(keys, date_to, lb_from, weights=None):
    weights = weights or {k: 1.0 for k in keys}
    ser, pnls = [], []
    for k in keys:
        s, p, _ = run_leg(k, date_to)
        w = float(weights.get(k, 1.0))
        ser.append(s * w)
        pnls.extend([x * w for x in p])
    daily = pd.concat(ser, axis=1).fillna(0.0).sum(axis=1).sort_index()
    return _stats(daily, pnls, lb_from), daily


def corr(keys, date_to):
    cols = {k: run_leg(k, date_to)[0] for k in keys}
    return pd.DataFrame(cols).fillna(0.0).corr()


def row(label, st):
    print(f"{label:<46} ${st['net']:>10,.0f}  {st['pf']:5.3f}  ${st['dd']:>8,.0f}  "
          f"{st['mar']:6.2f}  {st['held']}/8  ${st['lb_net']:>9,.0f}  ${st['lb_dd']:>8,.0f}  "
          f"{st['lb_mar']:5.2f}  {st['n']:>6,}")


HDR = (f"{'book / leg':<46} {'net':>11}  {'PF':>5}  {'maxDD':>9}  {'MAR':>6}  "
       f"{'sl':>3}  {'LB net':>10}  {'LB DD':>9}  {'LBMAR':>5}  {'n':>6}")

NOISE_KEYS = ["N_BASE", "N_D3", "N_SBS", "N_SBSV90", "N_SBA", "N_V98"]
NICE = {"N_BASE": "plain champion (control)", "N_D3": "run #238 leg (confirm2+SBS)",
        "N_SBS": "skip shorts after weak close", "N_SBSV90": "SBS + skip wildest 10%",
        "N_SBA": "skip ALL after weak close", "N_V98": "skip wildest 2% days"}


def verify():
    """Gate 1: every leg reproduces its published number.
       Gate 2: this harness's pooling == augur_engine.run_book on #238's exact legs."""
    ok = True
    checks = [
        ("ORB_C2",   W5_TO, 2607, 389874, 900),
        ("ORB_C221", W5_TO, 2607, 348129, 900),
        ("N_D3",     W5_TO, 4418, 367959, 500),
        ("N_SBS",    W5_TO, 5214, 388181, 500),
        ("N_BASE",   W5_TO, 5633, 335981, 500),
        ("N_SBA",    W5_TO, 4404, 366855, 500),
        ("N_V98",    W5_TO, 5347, 384690, 500),
        ("N_SBSV90", W5_TO, 4429, 380745, 500),
    ]
    for key, dto, en, enet, tol in checks:
        s, p, r = run_leg(key, dto)
        net, n = sum(p), len(p)
        good = abs(n - en) <= 2 and abs(net - enet) < tol
        ok &= good
        print(f"  {'OK ' if good else 'BAD'} {key:<10} n={n:<6} (exp {en:<6}) "
              f"net=${net:>11,.0f} (exp ${enet:,})")
    s, p, r = run_leg("ENGQ_RTH", W1_TO)
    good = len(p) == 2048 and abs(sum(p) - 477520.82) < 2
    ok &= good
    print(f"  {'OK ' if good else 'BAD'} {'ENGQ_RTH':<10} n={len(p):<6} (exp 2048  ) "
          f"net=${sum(p):>11,.0f} (exp $477,521)")

    from augur_engine import run_book
    legs = [{"strategy": "ORB_3_4_C221.py", "params": C221, "instrument": "NQ",
             "timeframe": "5m", "session": "rth", "source": "db_noadj_rth",
             "cost_pts": COST, "mult": 20},
            {"strategy": "NOISE_1_0.py", "params": D3, "instrument": "NQ",
             "timeframe": "5m", "session": "rth", "source": "db_noadj_rth",
             "cost_pts": COST, "mult": 20}]
    rb = run_book(legs, date_from=FROM, date_to=W5_TO, lockbox_months=18, slices=8)
    st, _ = book(["ORB_C221", "N_D3"], W5_TO, LB238)
    w, lbk = rb["book"]["whole"], rb["book"]["lockbox"]
    same = (abs(w["total_pnl"] - st["net"]) < 2 and w["num_trades"] == st["n"]
            and abs(w["max_drawdown"] - st["dd"]) < 2
            and abs(lbk["total_pnl"] - st["lb_net"]) < 2)
    ok &= same
    print(f"  {'OK ' if same else 'BAD'} harness == augur_engine.run_book on #238 legs: "
          f"engine ${w['total_pnl']:,.0f}/{w['num_trades']}/DD ${w['max_drawdown']:,.0f}/"
          f"LB ${lbk['total_pnl']:,.0f}  vs  harness ${st['net']:,.0f}/{st['n']}/"
          f"DD ${st['dd']:,.0f}/LB ${st['lb_net']:,.0f}")
    print("  #238 saved doc: $716,089 / 7,025 tr / DD $39,809 / LB $168,845")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    print("PARITY GATES")
    ok = verify()
    print(f"  => {'ALL PARITY PASS' if ok else 'PARITY FAIL'}\n")
    if a.verify:
        return 0 if ok else 1
    if not ok:
        print("refusing to print results on a failed parity gate")
        return 1

    print(f"\nROUND 1 - STANDALONE LEGS  ({FROM} -> {W5_TO}, LB from {LB238.date()})")
    print(HDR)
    for k in ["ORB_C221", "ORB_C2"] + NOISE_KEYS:
        s, p, _ = run_leg(k, W5_TO)
        row(f"{k}  {NICE.get(k, '')}", _stats(s, p, LB238))

    for orb, tag in (("ORB_C221", "#238 replication: ORB #230 crown"),
                     ("ORB_C2", "current ORB crown #234")):
        for lbf, lbl in ((LB238, "LB from 2025-02-10 (#238 boundary)"),
                         (LB234, "LB from 2025-08-13 (all legs frozen)")):
            print(f"\nROUND 2 - 2-LEG BOOKS  {tag}  [{lbl}]  ({FROM} -> {W5_TO})")
            print(HDR)
            for nk in NOISE_KEYS:
                st, _ = book([orb, nk], W5_TO, lbf)
                row(f"{orb} + {nk}   {NICE[nk]}", st)
            st, _ = book([orb], W5_TO, lbf)
            row(f"{orb} ALONE (no NOISE leg)", st)

    print(f"\nLEG CORRELATIONS (daily $, {FROM} -> {W5_TO}, union of days, 0-filled)")
    print(corr(["ORB_C221", "ORB_C2"] + NOISE_KEYS, W5_TO).round(3).to_string())

    print(f"\nROUND 3 - vs THE OWNER'S BASELINE  ({FROM} -> {W1_TO}, LB from {LB234.date()})")
    print("  window ends 2026-06-30: the NQ 1m RTH master has a real hole "
          "2026-07-17 -> 2026-08-05")
    print(HDR)
    for k in ["ORB_C2", "ENGQ_RTH"]:
        s, p, _ = run_leg(k, W1_TO)
        row(f"{k} ALONE", _stats(s, p, LB234))
    st, _ = book(["ORB_C2", "ENGQ_RTH"], W1_TO, LB234)
    row("BASELINE  ORB #234 + ENGU-Q RTH (1:1)", st)
    base_mar = st["mar"]
    for nk in NOISE_KEYS:
        st3, _ = book(["ORB_C2", "ENGQ_RTH", nk], W1_TO, LB234)
        flag = "BETTER MAR" if st3["mar"] > base_mar else "worse MAR"
        row(f"3-LEG  + {nk}  [{flag}]", st3)
    print(f"\nLEG CORRELATIONS (daily $, {FROM} -> {W1_TO})")
    print(corr(["ORB_C2", "ENGQ_RTH"] + NOISE_KEYS, W1_TO).round(3).to_string())

    # PRE-REGISTERED weighting rule, declared before any weighted result was looked at:
    #   * candidate weights 0.5 / 1.0 / 1.5 / 2.0 on the ENGU-Q and NOISE legs, the ORB
    #     leg fixed at 1.0 as the numeraire
    #   * SELECTION metric: MAR on the PRE-LOCKBOX stretch ONLY (2010-06-07 -> 2025-08-12)
    #   * the 2025-08-13 -> 2026-06-30 stretch is read ONCE, after the pick, and reported
    #     whatever it says
    print(f"\nROUND 4 - PER-LEG WEIGHTING (pre-registered: weights picked on "
          f"{FROM} -> 2025-08-12 by MAR only; LB read once, after)")
    keys3 = ["ORB_C2", "ENGQ_RTH", "N_SBS"]
    grid = [0.5, 1.0, 1.5, 2.0]
    res = []
    for we in grid:
        for wn in grid:
            w = {"ORB_C2": 1.0, "ENGQ_RTH": we, "N_SBS": wn}
            st4, daily = book(keys3, W1_TO, LB234, weights=w)
            pre = daily[daily.index < LB234]
            pc = pre.cumsum()
            pdd = abs(float((pc - pc.cummax()).min()))
            res.append((float(pre.sum()) / pdd if pdd else 0.0, we, wn, st4,
                        float(pre.sum())))
    res.sort(reverse=True, key=lambda x: x[0])
    print(f"{'ENGQ w':>7} {'NOISE w':>8} {'pre-LB MAR':>11} {'pre-LB net':>12} "
          f"{'full net':>12} {'full MAR':>9} {'LB net':>11} {'LB MAR':>8}")
    for mar, we, wn, st4, pn in res:
        print(f"{we:>7.1f} {wn:>8.1f} {mar:>11.2f} ${pn:>11,.0f} ${st4['net']:>11,.0f} "
              f"{st4['mar']:>9.2f} ${st4['lb_net']:>10,.0f} {st4['lb_mar']:>8.2f}")
    print("\nPICK = top row by pre-lockbox MAR. Equal weighting is the 1.0/1.0 row.")

    # ── ROUND 5: year-by-year, and is the ORB-NOISE correlation stable? ──────
    print(f"\nROUND 5 - YEAR BY YEAR  ({FROM} -> {W1_TO})")
    _, dbase = book(["ORB_C2", "ENGQ_RTH"], W1_TO, LB234)
    _, d3leg = book(["ORB_C2", "ENGQ_RTH", "N_SBSV90"], W1_TO, LB234)
    yb = dbase.groupby(dbase.index.year).sum()
    y3 = d3leg.groupby(d3leg.index.year).sum()
    print(f"{'year':>6} {'baseline 2-leg':>16} {'3-leg + SBS_V90':>17} {'delta':>13}")
    for y in sorted(set(yb.index) | set(y3.index)):
        b, t = float(yb.get(y, 0.0)), float(y3.get(y, 0.0))
        print(f"{y:>6} ${b:>15,.0f} ${t:>16,.0f} ${t - b:>12,.0f}")
    print(f"{'losing':>6} {int((yb < 0).sum()):>16} {int((y3 < 0).sum()):>17}")

    print("\nROUND 5b - CORRELATION STABILITY (ORB #234 vs each NOISE leg, daily $)")
    df = pd.DataFrame({k: run_leg(k, W1_TO)[0] for k in ["ORB_C2"] + NOISE_KEYS}).fillna(0.0)
    for lo, hi, lbl in ((None, "2018-01-01", "2010-2017"),
                        ("2018-01-01", None, "2018-2026"),
                        (str(LB234.date()), None, "2025-08-13+")):
        d = df
        if lo:
            d = d[d.index >= pd.Timestamp(lo)]
        if hi:
            d = d[d.index < pd.Timestamp(hi)]
        vals = " ".join(f"{k}={d['ORB_C2'].corr(d[k]):.3f}" for k in NOISE_KEYS)
        print(f"  {lbl:<12} n_days={len(d):<5} {vals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
