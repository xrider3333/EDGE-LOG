# -*- coding: utf-8 -*-
"""NOISE ROUND 55 -- THE FRONTIER, LIKE FOR LIKE.

Owner, 2026-09-13: which NOISE configuration is most worthy of forward or live testing, and is
there anything approaching the frontier config that might beat it if tested further -- an
internal test or a sweep that was never auto-validated?

Every NOISE validate reported its numbers on its OWN window (three different end dates), its own
75% in-sample split and its own lockbox, so no two headline rows on the board are comparable. This
replays every distinct candidate -- validated champions, validated add-ons, and the configurations
that were measured by hand or by sweep but never validated -- on ONE tape, ONE window, TWO costs,
the same eras, the same concentration test.

PRE-REGISTERED, written before any candidate below was run:

  APPROACHES the crown  at BOTH costs: profit factor within 0.02 of the crown's in BOTH eras
                        (2010-2023 and 2024 to the common end), full-window net-over-drawdown at
                        least 90% of the crown's, positive net once the ten biggest winners are
                        removed, and a top-ten share no more than 3 points above the crown's.
  BEATS the crown       at BOTH costs: profit factor ABOVE the crown's in BOTH eras, and
                        net-over-drawdown at least the crown's, and the concentration clauses.

  For a SIZE TILT the same clauses are exactly the exposure-matched control: trading the crown
  k times bigger leaves its profit factor and its net-over-drawdown unchanged, so a tilt that does
  not beat the crown on both IS flat leverage.

  Eras compare on profit factor, never raw dollars (the tape's amplitude grew about seven-fold,
  round 46). The two tails after the common end are REPORTED, never judged: the first was seen by
  the validates that ran to 2026-08-12, the second by no validate at all, and together they are
  about forty sessions -- a sanity column, not evidence.

  Tilt sizes are applied to NET trades (the engine returns trades net of cost, and a size-s trade
  honestly nets s times that). Gate G2 checks this against the re-based tilt strategy file run
  through the engine itself.
"""
import os, sys, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402

MULT = 20.0
COSTS = (0.533, 0.783)
START = "2010-06-07"
END = pd.Timestamp("2026-07-16").date()          # common end: first day NOT in the judged window
ERA_B0 = pd.Timestamp("2024-01-01").date()
TAIL2_0 = pd.Timestamp("2026-08-12").date()      # nothing validated has seen a bar from here on
SEALED0 = pd.Timestamp("2025-07-16").date()      # run 382 / 334 / 374 lockbox, for reference


def load(fn, alias):
    sp = ilu.spec_from_file_location(alias, os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


N10 = load("NOISE_1_0.py", "N10")
NBHD = load("NOISE_1_1_NBHD.py", "NBHD")
SQ = load("NOISE_1_1_SBS_V90_SQ.py", "SQ")
MT = load("NOISE_1_1_SBS_V90_MT.py", "MT")
EXIT = load("NOISE_1_7_EXIT.py", "EXIT")
CT304 = load("NOISE_1_8_CT304.py", "CT304")

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
             daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
V243 = dict(CROWN, lookback=44, vol_skip_pct=90.0)

GEOMETRIES = [
    ("#304 LIVE CROWN", "5m", N10, CROWN, "validated, crowned"),
    ("#243 retired crown", "5m", N10, V243, "validated, retired 09-05"),
    ("#305", "5m", N10, dict(CROWN, lookback=51, band_mult_short=1.25, stop_k=1.25, confirm_bars=4,
                             vol_skip_pct=99.0, daytype_lo=0.25, daytype_hi=0.6), "validated PASS, never crowned"),
    ("#316 slower confirm", "5m", N10, dict(CROWN, lookback=37, stop_k=2.0, confirm_bars=2,
                                            vol_skip_pct=90.0), "validated PASS 7/7"),
    ("#322 short lookback", "5m", N10, dict(CROWN, lookback=16, stop_k=1.5, confirm_bars=2,
                                            vol_skip_pct=90.0), "validated PASS"),
    ("#256 skip 98, no day rule", "5m", N10, dict(V243, vol_skip_pct=98.0, daytype_mode="off"),
     "validated PASS"),
    ("#241 no volatility skip", "5m", N10, dict(V243, vol_skip_pct=0.0), "validated PASS"),
    ("#245 skip bottom-all", "5m", N10, dict(V243, vol_skip_pct=0.0, daytype_mode="skip_bot_all"),
     "validated PASS"),
    ("C3 cost-robust corner", "5m", N10,
     dict(lookback=74, band_mult_long=1.0, band_mult_short=1.75, exit_mode="band", side="Both",
          window="afternoon_block", flat_eod=False, skip_holidays=False, stop_mode="atr",
          stop_k=0.75, confirm_bars=3, daytype_mode="skip_bot_short", daytype_lo=0.1,
          daytype_hi=0.95, vol_skip_pct=93.0), "hand-measured r38-43, NEVER validated"),
    ("#334 2-minute card", "2m", N10,
     dict(lookback=104, band_mult_long=0.5, band_mult_short=1.0, exit_mode="vwap", side="Both",
          window="afternoon_block", flat_eod=True, skip_holidays=True, stop_mode="fixed", stop_k=3.0,
          confirm_bars=4, daytype_mode="skip_bot_short", daytype_lo=0.3, daytype_hi=0.95,
          vol_skip_pct=96.0), "validated PASS"),
    ("#362 15-minute card", "15m", N10,
     dict(lookback=16, band_mult_long=0.5, band_mult_short=1.75, exit_mode="vwap", side="Both",
          window="morning", flat_eod=True, skip_holidays=True, stop_mode="atr", stop_k=0.25,
          confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.55,
          vol_skip_pct=96.0), "validated PASS"),
    ("#345 1-minute card", "1m", N10,
     dict(lookback=87, band_mult_long=1.0, band_mult_short=1.5, exit_mode="vwap", side="Both",
          window="all_day", flat_eod=True, skip_holidays=False, stop_mode="atr", stop_k=3.25,
          confirm_bars=4, daytype_mode="off", daytype_lo=0.4, daytype_hi=0.75,
          vol_skip_pct=89.0), "validated PASS"),
]

ARR = {}


def arrays(tf):
    if tf not in ARR:
        ARR[tf] = load_master_arrays(find_master("NQ", tf, "rth", "db_noadj_rth"), date_from=START)
    return ARR[tf]


def trades(mod, params, tf, cost):
    A = arrays(tf)
    r = run_backtest(mod, arrays=A, params=params, cost_pts=cost, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0]) if r and r.get("trades") else []
    idx = pd.DatetimeIndex(A["index"])
    bars = np.array([int(x[0]) for x in t], int)
    return dict(bars=bars, pnl=np.array([x[2] * MULT for x in t], float),
                date=np.array([idx[b].date() for b in bars]), trades=t, tf=tf)


def stat(p):
    p = np.asarray(p, float)
    if len(p) < 2:
        return dict(n=len(p), net=float(p.sum()), pf=float("nan"), dd=0.0, ndd=float("nan"),
                    ex10=float("nan"), top10=float("nan"))
    w, l_ = p[p > 0].sum(), -p[p < 0].sum()
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    t10 = float(np.sort(p)[-10:].sum())
    return dict(n=len(p), net=net, pf=(w / l_ if l_ > 0 else 99.0), dd=dd,
                ndd=(net / dd if dd > 0 else 99.0), ex10=net - t10,
                top10=(100.0 * t10 / net if net > 0 else float("nan")))


def slices(T, pnl=None, clip_end=None):
    p = T["pnl"] if pnl is None else pnl
    d = T["date"]
    end = END if clip_end is None else min(END, clip_end)
    full = (d < end)
    out = dict(full=stat(p[full]), a=stat(p[d < min(ERA_B0, end)]),
               b=stat(p[(d >= ERA_B0) & (d < end)]), sealed=stat(p[(d >= SEALED0) & (d < end)]),
               tail1=stat(p[(d >= END) & (d < TAIL2_0)]), tail2=stat(p[d >= TAIL2_0]))
    years = {}
    for y in range(2010, 2027):
        m = full & (np.array([x.year for x in d]) == y)
        if m.sum() >= 10:
            years[y] = stat(p[m])["pf"]
    out["years"] = years
    daily = pd.Series(p[full], index=pd.to_datetime(d[full])).groupby(level=0).sum()
    out["daily"] = daily
    return out


def compression_mask(T, tf_min, glen, ratio):
    A = arrays(T["tf"])
    comp = SQ._compression(np.asarray(A["high"], float), np.asarray(A["low"], float),
                           np.asarray(A["close"], float), A["day_id"], A["index"], tf_min, glen, ratio)
    return np.array([bool(comp[b - 1]) if b >= 1 else False for b in T["bars"]])


def momentum_mask(T, mom_bars, mom_atr):
    A = arrays(T["tf"])
    h = np.asarray(A["high"], float); l = np.asarray(A["low"], float); c = np.asarray(A["close"], float)
    atr = MT._atr14(h, l, c)
    out = []
    for t, b in zip(T["trades"], T["bars"]):
        dec = b - 1
        ok = False
        if dec - mom_bars >= 0 and atr[dec] > 0 and np.isfinite(atr[dec]):
            ok = (c[dec] - c[dec - mom_bars]) / atr[dec] * MT._side_of(t) >= mom_atr
        out.append(bool(ok))
    return np.array(out)


# ------------------------------------------------------------------------------ run everything
R = {}       # R[(label, cost)] = slices
CROWN_TS = {}
META = {}
for cost in COSTS:
    for label, tf, mod, params, status in GEOMETRIES:
        T = trades(mod, params, tf, cost)
        clip = None
        if tf != "5m":
            clip = T["date"].max() if len(T["date"]) else None
        R[(label, cost)] = slices(T, clip_end=(pd.Timestamp(clip).date() if clip is not None and clip < END else None))
        META[label] = (tf, status, clip)
        if label.startswith("#304"):
            CROWN_T = T
            CROWN_TS[cost] = T
        if label.startswith("#243"):
            V243_T = T
    # size tilts, applied to net trades of their base
    for base_label, BT in (("#304", CROWN_T), ("#243", V243_T)):
        cm = compression_mask(BT, 30, 16, 1.15)
        for s in (1.5, 2.0):
            lab = "%s + compression %.1fx" % (base_label, s)
            size = np.where(cm, s, 1.0)
            R[(lab, cost)] = slices(BT, BT["pnl"] * size)
            R[(lab, cost)]["mean_size"] = float(size[BT["date"] < END].mean())
            st = ("validated PASS run 382 (2.0x chosen)" if base_label == "#304"
                  else ("validated PASS run 333, paper C15G" if s == 1.5 else "validated PASS run 331"))
            META[lab] = ("5m", st, None)
        cm60 = compression_mask(BT, 60, 20, 1.0)
        if base_label == "#304":
            lab = "#304 + hourly Carter squeeze 2.0x"
            size = np.where(cm60, 2.0, 1.0)
            R[(lab, cost)] = slices(BT, BT["pnl"] * size)
            R[(lab, cost)]["mean_size"] = float(size[BT["date"] < END].mean())
            META[lab] = ("5m", "best net/DD cell of run 382 cloud, not its pick", None)
        mm = momentum_mask(BT, 30, 3.5)
        lab = "%s + momentum 2.0x" % base_label
        size = np.where(mm, 2.0, 1.0)
        R[(lab, cost)] = slices(BT, BT["pnl"] * size)
        R[(lab, cost)]["mean_size"] = float(size[BT["date"] < END].mean())
        META[lab] = ("5m", "WEAK run 327" if base_label == "#243" else "NEVER validated on the crown", None)
        if base_label == "#304":
            lab = "#304 + compression 1.5x + momentum 1.5x"
            size = np.where(cm, 1.5, 1.0) * np.where(mm, 1.5, 1.0)
            R[(lab, cost)] = slices(BT, BT["pnl"] * size)
            R[(lab, cost)]["mean_size"] = float(size[BT["date"] < END].mean())
            META[lab] = ("5m", "NEVER tested - two tilts stacked", None)
    # exit management fork, its own search pick
    T = trades(EXIT, dict(CROWN, be_r=0.0, trail_frac=2.75), "5m", cost)
    R[("#304 + trail 2.75R (run 374 pick)", cost)] = slices(T)
    META["#304 + trail 2.75R (run 374 pick)"] = ("5m", "WEAK run 374", None)

    if cost == COSTS[0]:
        # G1: NOISE_1_0 with the crown dict reproduces the crowned file to the cent
        TB = trades(NBHD, CROWN, "5m", cost)
        g1 = len(TB["pnl"]) == len(CROWN_T["pnl"]) and np.allclose(TB["pnl"], CROWN_T["pnl"], atol=0.01)
        print("G1 parity  NOISE_1_0 + crown params vs the crowned file: %d vs %d trades -> %s"
              % (len(CROWN_T["pnl"]), len(TB["pnl"]), "PASS" if g1 else "FAIL"))
        # G2: the harness tilt equals the re-based strategy file run through the engine
        TC = trades(CT304, dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0), "5m", cost)
        cm = compression_mask(CROWN_T, 30, 16, 1.15)
        hp = CROWN_T["pnl"] * np.where(cm, 2.0, 1.0)
        g2 = len(TC["pnl"]) == len(hp) and np.allclose(TC["pnl"], hp, atol=0.02)
        print("G2 parity  harness 2.0x tilt vs the strategy file through the engine: $%s vs $%s -> %s"
              % (format(int(hp.sum()), ","), format(int(TC["pnl"].sum()), ","), "PASS" if g2 else "FAIL"))
        if not (g1 and g2):
            sys.exit("parity failed - nothing below would mean anything")
        print()

# ------------------------------------------------------------------------------ report
LABELS = []
for k in R:
    if k[0] not in LABELS:
        LABELS.append(k[0])

crown = {c: R[("#304 LIVE CROWN", c)] for c in COSTS}
for cost in COSTS:
    print("=" * 196)
    print("COST %.3f pts a round turn   window %s .. %s   (other bar sizes clipped to their own master's last bar; crown re-clipped to match)"
          % (cost, START, END))
    print("%-42s %-4s | %5s %9s %6s %8s %6s | %6s %6s %7s | %7s %6s | %9s %6s | %6s %6s | %s"
          % ("candidate", "bar", "n", "net $", "PF", "DD $", "n/DD", "PF<24", "PF24+", "sealPF", "ex10 $", "top10",
             "yrs>crown", "corr", "tail1", "tail2", "status"))
    for lab in LABELS:
        S = R[(lab, cost)]
        tf, status, clip = META[lab]
        C = crown[cost]
        if clip is not None and pd.Timestamp(clip).date() < END:
            # re-slice the crown on the same calendar so the comparison is honest
            C = slices(CROWN_TS[cost], clip_end=pd.Timestamp(clip).date())
        yrs = sum(1 for y, v in S["years"].items() if y in C["years"] and v > C["years"][y])
        ny = sum(1 for y in S["years"] if y in C["years"])
        j = pd.concat([S["daily"], C["daily"]], axis=1).fillna(0.0)
        corr = float(j.corr().iloc[0, 1]) if len(j) > 30 else float("nan")
        f = S["full"]
        print("%-42s %-4s | %5d %9s %6.3f %8s %6.2f | %6.3f %6.3f %7.3f | %7s %5.0f%% | %4d of %-2d %6.2f | %6.2f %6.2f | %s"
              % (lab[:42], tf, f["n"], format(int(f["net"]), ","), f["pf"], format(int(f["dd"]), ","), f["ndd"],
                 S["a"]["pf"], S["b"]["pf"], S["sealed"]["pf"], format(int(f["ex10"]), ","), f["top10"],
                 yrs, ny, corr, S["tail1"]["pf"], S["tail2"]["pf"], status))
    print()

# ------------------------------------------------------------------------------ verdicts
print("=" * 196)
print("VERDICTS against the pre-registered clauses (both costs must hold)")
for lab in LABELS:
    if lab.startswith("#304 LIVE"):
        continue
    ok_app, ok_beat, why = True, True, []
    for cost in COSTS:
        S = R[(lab, cost)]
        tf, status, clip = META[lab]
        C = crown[cost]
        if clip is not None and pd.Timestamp(clip).date() < END:
            C = slices(CROWN_TS[cost], clip_end=pd.Timestamp(clip).date())
        for era in ("a", "b"):
            if not (S[era]["pf"] >= C[era]["pf"] - 0.02):
                ok_app = False; why.append("%s era %s PF %.3f vs %.3f" % (cost, "<24" if era == "a" else "24+", S[era]["pf"], C[era]["pf"]))
            if not (S[era]["pf"] > C[era]["pf"]):
                ok_beat = False
        if not (S["full"]["ndd"] >= 0.9 * C["full"]["ndd"]):
            ok_app = False; why.append("%s net/DD %.2f vs crown %.2f" % (cost, S["full"]["ndd"], C["full"]["ndd"]))
        if not (S["full"]["ndd"] >= C["full"]["ndd"]):
            ok_beat = False
        if not (S["full"]["ex10"] > 0 and S["full"]["top10"] <= C["full"]["top10"] + 3):
            ok_app = False; ok_beat = False
            why.append("%s concentration ex10 $%s top10 %.0f%% vs %.0f%%" % (cost, format(int(S["full"]["ex10"]), ","), S["full"]["top10"], C["full"]["top10"]))
    v = "BEATS" if (ok_app and ok_beat) else ("APPROACHES" if ok_app else "short")
    print("  %-42s %-10s %s" % (lab[:42], v, "; ".join(why[:3])))
