# -*- coding: utf-8 -*-
"""NOISE ROUND 56 -- THE SCORECARD: every NOISE configuration run so far, one tape, one window.

Owner, 2026-09-13: rank the NOISE configs, with their metrics, and say which are auto-validated,
which are not, and which need to be.

Same basis as round 55, widened to the whole family: one continuous run per configuration over
2010-06-07 to 2026-07-16 (other bar sizes to their own master's last bar), trades sliced by ENTRY
time, house cost and the stressed cost. The sealed year is 2025-07-16 to 2026-07-16 on a continuous
run -- NOT the validates' cold-restart lockbox, which for NOISE drops about a quarter of the trades.
Duplicate runs (identical settings re-validated) are one row.
"""
import os, sys, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402

START = "2010-06-07"
END = pd.Timestamp("2026-07-16").date()
B0 = pd.Timestamp("2024-01-01").date()
S0 = pd.Timestamp("2025-07-16").date()


def load(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


N10, RYR, SQ, MT, EXIT = (load(f) for f in ("NOISE_1_0.py", "NOISE_1_2_RYR.py", "NOISE_1_1_SBS_V90_SQ.py",
                                           "NOISE_1_1_SBS_V90_MT.py", "NOISE_1_7_EXIT.py"))

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
V243 = dict(CROWN, lookback=44, vol_skip_pct=90.0)
RAW = dict(V243, daytype_mode="off", vol_skip_pct=0.0)

# (label, instrument, bar, module, params, cost, multiplier, validation status)
CONFIGS = [
    ("#304 live crown", "NQ", "5m", N10, CROWN, 0.533, 20, "PASS 6/6, folds 8/8, PBO 0.135 (#304)"),
    ("#243 retired crown", "NQ", "5m", N10, V243, 0.533, 20, "PASS 6/6, folds 7/8 (#243, #252)"),
    ("#316 confirm 2 bars", "NQ", "5m", N10, dict(CROWN, lookback=37, stop_k=2.0, confirm_bars=2, vol_skip_pct=90.0),
     0.533, 20, "PASS 7/7, folds 8/8, PBO 0.464 (#316)"),
    ("#322 lookback 16", "NQ", "5m", N10, dict(CROWN, lookback=16, stop_k=1.5, confirm_bars=2, vol_skip_pct=90.0),
     0.533, 20, "PASS 6/6, folds 8/8, PBO 0.425 (#322)"),
    ("#305", "NQ", "5m", N10, dict(CROWN, lookback=51, band_mult_short=1.25, stop_k=1.25, confirm_bars=4,
                                   vol_skip_pct=99.0, daytype_lo=0.25, daytype_hi=0.6),
     0.533, 20, "PASS 6/6, folds 8/8, PBO 0.274 (#305)"),
    ("#256 skip 98, no day rule", "NQ", "5m", N10, dict(V243, vol_skip_pct=98.0, daytype_mode="off"),
     0.533, 20, "PASS 6/6, folds 7/8 (#256)"),
    ("#241 no volatility skip", "NQ", "5m", N10, dict(V243, vol_skip_pct=0.0), 0.533, 20,
     "PASS 6/6, folds 7/8 (#241, #253; sweep #236)"),
    ("#245 skip bottom, both sides", "NQ", "5m", N10, dict(V243, vol_skip_pct=0.0, daytype_mode="skip_bot_all"),
     0.533, 20, "PASS 6/6, folds 7/8 (#245, #251)"),
    ("#225 raw NOISE, no filters", "NQ", "5m", N10, RAW, 0.533, 20,
     "PASS 7/7, folds 8/8, PBO 0.365 (#202 #203 #225 #231 #242 #254)"),
    ("#321 squeeze FILTER on #243", "NQ", "5m", SQ, dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15),
     0.533, 20, "PASS 6/6, folds 7/8, PBO 0.099 (#321)"),
    ("#374 crown + trail 2.75R", "NQ", "5m", EXIT, dict(CROWN, be_r=0.0, trail_frac=2.75), 0.533, 20,
     "WEAK 5/6, PBO 0.615 (#374)"),
    ("#237", "NQ", "5m", N10, dict(lookback=64, band_mult_long=0.5, band_mult_short=1.5, exit_mode="vwap",
                                   side="Both", window="all_day", flat_eod=True, skip_holidays=True, stop_mode="fixed",
                                   stop_k=1.25, confirm_bars=2, daytype_mode="off", daytype_lo=0.15, daytype_hi=0.9,
                                   vol_skip_pct=89.0), 0.533, 20, "WEAK 6/7, PBO 0.599 (#237, #302)"),
    ("#306", "NQ", "5m", N10, dict(lookback=44, band_mult_long=0.5, band_mult_short=1.5, exit_mode="band",
                                   side="Both", window="all_day", flat_eod=False, skip_holidays=True, stop_mode="fixed",
                                   stop_k=3.5, confirm_bars=3, daytype_mode="skip_top_long", daytype_lo=0.25,
                                   daytype_hi=0.9, vol_skip_pct=91.0), 0.533, 20, "WEAK 5/6, PBO 0.437 (#306)"),
    ("#319 afternoon, boundary exit", "NQ", "5m", RYR,
     dict(lookback=24, band_mult_long=0.75, band_mult_short=1.5, exit_mode="boundary", side="Both",
          window="afternoon_block", flat_eod=True, skip_holidays=True, stop_mode="bandwidth", stop_k=1.25,
          confirm_bars=1, daytype_mode="off", daytype_lo=0.25, daytype_hi=0.7, vol_skip_pct=82.0),
     0.533, 20, "WEAK 5/6, PBO 0.579 (#319)"),
    ("#334 2-minute card", "NQ", "2m", N10,
     dict(lookback=104, band_mult_long=0.5, band_mult_short=1.0, exit_mode="vwap", side="Both",
          window="afternoon_block", flat_eod=True, skip_holidays=True, stop_mode="fixed", stop_k=3.0, confirm_bars=4,
          daytype_mode="skip_bot_short", daytype_lo=0.3, daytype_hi=0.95, vol_skip_pct=96.0),
     0.533, 20, "PASS 6/6, folds 7/8, PBO 0.460 (#334)"),
    ("#362 15-minute card", "NQ", "15m", N10,
     dict(lookback=16, band_mult_long=0.5, band_mult_short=1.75, exit_mode="vwap", side="Both", window="morning",
          flat_eod=True, skip_holidays=True, stop_mode="atr", stop_k=0.25, confirm_bars=1,
          daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.55, vol_skip_pct=96.0),
     0.533, 20, "PASS 6/6, folds 7/8, PBO 0.464, WFE 0.6 (#362)"),
    ("#345 1-minute card", "NQ", "1m", N10,
     dict(lookback=87, band_mult_long=1.0, band_mult_short=1.5, exit_mode="vwap", side="Both", window="all_day",
          flat_eod=True, skip_holidays=False, stop_mode="atr", stop_k=3.25, confirm_bars=4, daytype_mode="off",
          daytype_lo=0.4, daytype_hi=0.75, vol_skip_pct=89.0),
     0.533, 20, "PASS 6/6, folds 8/8, PBO 0.210 (#345, #360)"),
    ("#344 on ES", "ES", "5m", N10,
     dict(lookback=32, band_mult_long=0.5, band_mult_short=2.0, exit_mode="band", side="Both",
          window="afternoon_block", flat_eod=True, skip_holidays=True, stop_mode="off", stop_k=1.5, confirm_bars=3,
          daytype_mode="off", daytype_lo=0.3, daytype_hi=0.85, vol_skip_pct=93.0),
     0.3, 50, "WEAK 5/6, PBO 0.675 (#344)"),
    ("C3 cost-robust corner", "NQ", "5m", N10,
     dict(lookback=74, band_mult_long=1.0, band_mult_short=1.75, exit_mode="band", side="Both",
          window="afternoon_block", flat_eod=False, skip_holidays=False, stop_mode="atr", stop_k=0.75,
          confirm_bars=3, daytype_mode="skip_bot_short", daytype_lo=0.1, daytype_hi=0.95, vol_skip_pct=93.0),
     0.533, 20, "NOT validated (hand test, rounds 38-43)"),
    ("Crown settings on 15-minute bars", "NQ", "15m", N10, CROWN, 0.533, 20, "NOT validated (hand test, round 44)"),
    ("Crown + confirm 2 bars", "NQ", "5m", N10, dict(CROWN, confirm_bars=2), 0.533, 20,
     "NOT validated (hand test, round 45)"),
]

ARR = {}


def arrays(ins, tf):
    if (ins, tf) not in ARR:
        ARR[(ins, tf)] = load_master_arrays(find_master(ins, tf, "rth", "db_noadj_rth"), date_from=START)
    return ARR[(ins, tf)]


def run(mod, params, ins, tf, cost, mult):
    A = arrays(ins, tf)
    r = run_backtest(mod, arrays=A, params=params, cost_pts=cost, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0]) if r and r.get("trades") else []
    idx = pd.DatetimeIndex(A["index"])
    bars = np.array([int(x[0]) for x in t], int)
    d = np.array([idx[b].date() for b in bars])
    keep = d < END
    return dict(bars=bars[keep], d=d[keep], p=np.array([x[2] * mult for x in t], float)[keep],
                t=[x for x, k in zip(t, keep) if k], ins=ins, tf=tf, last=idx[-1].date())


def pf(q):
    l_ = -q[q < 0].sum()
    return q[q > 0].sum() / l_ if l_ > 0 else float("nan")


def dd(q):
    if not len(q):
        return 0.0
    e = np.cumsum(q)
    return float(np.max(np.maximum.accumulate(e) - e))


def card(T, Ts):
    p, d = T["p"], T["d"]
    s = d >= S0
    t10 = np.sort(p)[-10:].sum()
    return dict(n=len(p), win=100.0 * (p > 0).mean(), net=p.sum(), per=p.mean(), pf=pf(p), dd=dd(p),
                ndd=p.sum() / dd(p), pfa=pf(p[d < B0]), pfb=pf(p[d >= B0]), pfs=pf(p[s]), nets=p[s].sum(),
                ns=int(s.sum()), top10=100.0 * t10 / p.sum(), pf_stress=pf(Ts["p"]), last=T["last"])


CARDS = []
BASES = {}
for lab, ins, tf, mod, params, cost, mult, status in CONFIGS:
    T = run(mod, params, ins, tf, cost, mult)
    Ts = run(mod, params, ins, tf, cost + 0.25, mult)
    CARDS.append(("config", lab, ins + " " + tf, status, card(T, Ts)))
    if lab.startswith("#304") or lab.startswith("#243"):
        BASES[lab[:4]] = (T, Ts)
    print("done", lab, flush=True)

A5 = arrays("NQ", "5m")
H, L, C = (np.asarray(A5[k], float) for k in ("high", "low", "close"))
COMP = {}


def tagged(T, kind):
    if kind == "mom":
        atr = MT._atr14(H, L, C)
        out = []
        for t, b in zip(T["t"], T["bars"]):
            dec = b - 1
            out.append(bool(dec - 30 >= 0 and atr[dec] > 0 and np.isfinite(atr[dec]) and
                            (C[dec] - C[dec - 30]) / atr[dec] * MT._side_of(t) >= 3.5))
        return np.array(out)
    if kind not in COMP:
        COMP[kind] = SQ._compression(H, L, C, A5["day_id"], A5["index"], *kind)
    return np.array([bool(COMP[kind][b - 1]) for b in T["bars"]])


TILTS = [
    ("#243 + squeeze 1.5x (30-min gate)", "#243", (30, 16, 1.15), 1.5, "PASS 6/6, folds 8/8, PBO 0.222 (#333) - on paper"),
    ("#243 + squeeze 2.0x (30-min gate)", "#243", (30, 16, 1.15), 2.0, "PASS 6/6, folds 8/8, PBO 0.194 (#331)"),
    ("#243 + hourly squeeze 1.5x", "#243", (60, 20, 1.0), 1.5, "NOT validated as itself - on paper"),
    ("#304 + squeeze 2.0x (30-min gate)", "#304", (30, 16, 1.15), 2.0, "PASS 6/6, folds 8/8, PBO 0.111 (#382)"),
    ("#304 + hourly squeeze 1.5x", "#304", (60, 20, 1.0), 1.5, "Cell inside #382, never picked - NEEDS VALIDATE"),
    ("#243 + momentum 2.0x", "#243", "mom", 2.0, "WEAK 5/6, PBO 0.599 (#327)"),
    ("#304 + momentum 2.0x", "#304", "mom", 2.0, "NOT validated"),
]
for lab, base, kind, size, status in TILTS:
    T, Ts = BASES[base]
    m, ms = tagged(T, kind), tagged(Ts, kind)
    TT = dict(T, p=T["p"] * np.where(m, size, 1.0))
    TTs = dict(Ts, p=Ts["p"] * np.where(ms, size, 1.0))
    CARDS.append(("tilt", lab, "NQ 5m", status, card(TT, TTs)))

hdr = ("%-4s %-34s %-6s | %5s %5s %9s %6s %6s %8s %6s | %6s %6s %6s %8s | %5s %6s | %s"
       % ("kind", "config", "bar", "n", "win%", "net $", "$/trd", "PF", "DD $", "n/DD", "PF<24", "PF24+", "sealPF",
          "seal $", "top10", "PFstr", "validation"))
print()
print(hdr)
for kind, lab, bar, status, c in CARDS:
    print("%-4s %-34s %-6s | %5d %5.1f %9s %6.0f %6.3f %8s %6.2f | %6.3f %6.3f %6.3f %8s | %4.0f%% %6.3f | %s%s"
          % (kind, lab[:34], bar, c["n"], c["win"], format(int(c["net"]), ","), c["per"], c["pf"],
             format(int(c["dd"]), ","), c["ndd"], c["pfa"], c["pfb"], c["pfs"], format(int(c["nets"]), ","),
             c["top10"], c["pf_stress"], status, "" if c["last"] >= END else "  [tape ends %s]" % c["last"]))
