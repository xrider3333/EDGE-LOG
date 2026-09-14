# -*- coding: utf-8 -*-
"""NOISE ROUND 55b -- the battery on what the frontier replay surfaced.

Three candidates came out of r55_frontier.py and none of them has been judged the way a crown is:

  1. The live crown with the PUBLISHED hourly squeeze (60-minute frame, length 20, Bollinger/Keltner
     ratio 1.0 -- every gate knob at its textbook value, the setting the round-6 scan and the deployed
     raw compression paper leg read). It sat inside run #382's 24-cell grid and the search chose a
     tuned cell instead (30 / 16 / 1.15). On the frontier window it beat the crown in both eras at
     both costs, including a 2024-onward profit factor of 1.434 against 1.357.
     THE RISK IS SELECTION: it was noticed as the best net-over-drawdown cell of a cloud, on the same
     years it is now being judged on. Part A asks whether it is a plateau or an outlier; Part B asks
     the shift null, which does not care how it was found.
  2. The live crown with the momentum tilt (never validated on this base; WEAK on the retired one).
  3. Run #316 raw -- confirm 2 bars, lookback 37, stop 2.0, volatility skip 90. Same recent profit
     factor as the crown, 43% less maximum drawdown. Drawdown is the least reliable statistic in the
     house (its confidence interval is wider than the number), so Part C re-measures it by era and by
     resampling before anyone believes it.

PRE-REGISTERED, before any of the parts below ran:
  A. PLATEAU: the published cell is an outlier if fewer than 5 of the 8 gate cells at the same size
     beat the crown on 2024-onward profit factor at the stressed cost. It is the TOP of a plateau if it
     leads and at least 5 of 8 beat the crown.
  B. The house tilt battery (tools/tilt_guard.py, permute="shift", 2000 shifts): walk-forward = entries
     before 2025-07-16, lockbox = 2025-07-16 to 2026-07-16. PASS as the battery defines it.
  C. #316's drawdown advantage is REAL only if its resampled 95th-percentile drawdown is lower than the
     crown's in BOTH eras, not just the realised maximum over the whole window.
"""
import os, sys, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from tilt_guard import guard                                           # noqa: E402


def load(fn, alias):
    sp = ilu.spec_from_file_location(alias, os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


N10 = load("NOISE_1_0.py", "N10")
SQ = load("NOISE_1_1_SBS_V90_SQ.py", "SQ")
MT = load("NOISE_1_1_SBS_V90_MT.py", "MT")

A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-16")
IDX = pd.DatetimeIndex(A["index"])
H, L, C = (np.asarray(A[k], float) for k in ("high", "low", "close"))
END = pd.Timestamp("2026-07-16").date()
B0 = pd.Timestamp("2024-01-01").date()
LB0 = pd.Timestamp("2025-07-16").date()

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
             daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
V243 = dict(CROWN, lookback=44, vol_skip_pct=90.0)
R316 = dict(CROWN, lookback=37, stop_k=2.0, confirm_bars=2, vol_skip_pct=90.0)


def tr(params, cost):
    r = run_backtest(N10, arrays=A, params=params, cost_pts=cost, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0])
    bars = np.array([int(x[0]) for x in t])
    d = np.array([IDX[b].date() for b in bars])
    m = d < END
    return dict(t=[x for x, k in zip(t, m) if k], bars=bars[m], d=d[m],
                p=np.array([x[2] * 20.0 for x in t])[m], ts=pd.DatetimeIndex([IDX[b] for b in bars[m]]))


def pf(p):
    w, l_ = p[p > 0].sum(), -p[p < 0].sum()
    return w / l_ if l_ > 0 else 99.0


def dd(p):
    e = np.cumsum(p)
    return float(np.max(np.maximum.accumulate(e) - e)) if len(p) else 0.0


def p95dd(p, n=3000, seed=11):
    rng = np.random.default_rng(seed)
    return float(np.percentile([dd(rng.permutation(p)) for _ in range(n)], 95))


COMP = {}


def comp_mask(T, tf, ln, ra):
    key = (tf, ln, ra)
    if key not in COMP:
        COMP[key] = SQ._compression(H, L, C, A["day_id"], A["index"], tf, ln, ra)
    c = COMP[key]
    return np.array([bool(c[b - 1]) for b in T["bars"]])


def mom_mask(T, mb=30, ma=3.5):
    atr = MT._atr14(H, L, C)
    out = []
    for t, b in zip(T["t"], T["bars"]):
        dec = b - 1
        ok = dec - mb >= 0 and atr[dec] > 0 and np.isfinite(atr[dec]) and \
            (C[dec] - C[dec - mb]) / atr[dec] * MT._side_of(t) >= ma
        out.append(bool(ok))
    return np.array(out)


# ============================================================================ PART A
print("=" * 130)
print("PART A - is the published squeeze a plateau or an outlier?   stressed cost 0.783, 8 gate cells x 2 sizes, two bases")
for base_lab, base in (("LIVE CROWN #304", CROWN), ("RETIRED #243", V243)):
    T = tr(base, 0.783)
    a, b = T["d"] < B0, T["d"] >= B0
    s = T["d"] >= LB0
    print("\n  %s raw: PF<24 %.3f  PF24+ %.3f  sealed PF %.3f  net/DD %.2f"
          % (base_lab, pf(T["p"][a]), pf(T["p"][b]), pf(T["p"][s]), T["p"].sum() / dd(T["p"])))
    print("  %-26s %5s | %6s %6s %7s %6s %6s | %s" % ("gate (tf / len / ratio)", "size", "PF<24", "PF24+", "sealPF", "n/DD", "fires", "2024+ beats raw?"))
    for size in (1.5, 2.0):
        beats = 0
        for tf in (30, 60):
            for ln in (16, 20):
                for ra in (1.0, 1.15):
                    m = comp_mask(T, tf, ln, ra)
                    q = T["p"] * np.where(m, size, 1.0)
                    ok = pf(q[b]) > pf(T["p"][b])
                    beats += ok
                    tag = "  <- PUBLISHED" if (tf, ln, ra) == (60, 20, 1.0) else ("  <- run 382 pick" if (tf, ln, ra) == (30, 16, 1.15) else "")
                    print("  %-26s %5.1f | %6.3f %6.3f %7.3f %6.2f %5.0f%% | %s%s"
                          % ("%d / %d / %.2f" % (tf, ln, ra), size, pf(q[a]), pf(q[b]), pf(q[s]), q.sum() / dd(q),
                             100 * m.mean(), "yes" if ok else "no", tag))
        print("  -> %d of 8 cells beat the raw base on 2024+ profit factor at %.1fx" % (beats, size))

# ============================================================================ PART B
print()
print("=" * 130)
print("PART B - the house tilt battery, shift null, 2000 shifts   (walk-forward < 2025-07-16, lockbox 2025-07-16..2026-07-16)")
for cost in (0.533, 0.783):
    T = tr(CROWN, cost)
    wf, lb = T["d"] < LB0, T["d"] >= LB0
    ones = np.ones(len(T["p"]))
    pub = comp_mask(T, 60, 20, 1.0)
    pick = comp_mask(T, 30, 16, 1.15)
    mom = mom_mask(T)
    cases = [("published squeeze 1.5x", ones, pub, 1.5), ("published squeeze 2.0x", ones, pub, 2.0),
             ("run 382 pick 2.0x", ones, pick, 2.0), ("momentum 2.0x", ones, mom, 2.0),
             ("momentum 1.5x ON TOP OF published squeeze 1.5x", np.where(pub, 1.5, 1.0), mom, 1.5)]
    for lab, base, mask, mult in cases:
        res = guard(T["p"], T["ts"], base, mask, mult, wf, lb, permute="shift", perm=2000,
                    label="%s on the live crown @ cost %.3f" % (lab, cost))
        print()
        print(res["report"])
        print("  >>> %s" % ("PASS" if res["passed"] else "FAIL"))

# ============================================================================ PART C
print()
print("=" * 130)
print("PART C - is run #316's lower drawdown real?   realised and resampled-95th drawdown, per era, stressed cost 0.783")
Tc, T3 = tr(CROWN, 0.783), tr(R316, 0.783)
print("  %-22s %-9s | %5s %9s %6s %8s %9s %6s" % ("config", "era", "n", "net $", "PF", "DD $", "p95 DD $", "n/p95"))
for lab, T in (("#304 live crown", Tc), ("#316 confirm 2", T3)):
    for era, m in (("<2024", T["d"] < B0), ("2024+", T["d"] >= B0), ("sealed", T["d"] >= LB0), ("full", T["d"] < END)):
        q = T["p"][m]
        p95 = p95dd(q)
        print("  %-22s %-9s | %5d %9s %6.3f %8s %9s %6.2f"
              % (lab, era, len(q), format(int(q.sum()), ","), pf(q), format(int(dd(q)), ","), format(int(p95), ","), q.sum() / p95))
    print()
# where the crown's worst drawdown sits, and what #316 did over the same dates
e = np.cumsum(Tc["p"]); pk = np.maximum.accumulate(e); i1 = int(np.argmax(pk - e)); i0 = int(np.argmax(e[:i1 + 1]))
d0, d1 = Tc["d"][i0], Tc["d"][i1]
m3 = (T3["d"] >= d0) & (T3["d"] <= d1)
mc = (Tc["d"] >= d0) & (Tc["d"] <= d1)
print("  crown's worst drawdown: %s -> %s, %d trades, $%s" % (d0, d1, int(mc.sum()), format(int(Tc["p"][mc].sum()), ",")))
print("  #316 over the same dates: %d trades, $%s" % (int(m3.sum()), format(int(T3["p"][m3].sum()), ",")))
days_c = set(Tc["d"]); days_3 = set(T3["d"])
print("  trading days: crown %d, #316 %d, shared %d (%.0f%% of #316's)" % (len(days_c), len(days_3), len(days_c & days_3), 100 * len(days_c & days_3) / len(days_3)))
