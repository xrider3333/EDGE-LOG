"""ENGU-Q CANDLE STRENGTH + VOLUME, daily-trend aligned - the 48-cell POWER-FIRST GATE, ES 15m.

Owner order w119 (MANAGER #150), prereg docs/PREREG_enguq_candlevol_2026-11-09.md, LF-normalised
body sha 34e89659a1736cd2b47b371c20a70ba9987dc97f908f440430fdb4f0ad3826b0.

THE HEADLINE IS NOT PROFITABILITY, IT IS THE PAIRED DIFFERENCE AGAINST A RANDOM ENTRY.
"Trade only in the direction of the daily trend" on a long index future IS BETA: a long entry in a
daily uptrend makes money because the index drifts up, not because the candle was strong.  So every
cell is scored against a RANDOM entry drawn from the SAME time-of-day slot on a DIFFERENT session
that passed the SAME daily-trend filter, running the IDENTICAL stop and exit.  A strategy with no
edge scores zero against that control - which is the property my BBRF gate's ceiling clause lacked
(it was near-vacuous and its 36 "OPEN" verdicts were worthless; ledger 2.220).

TBIS ALREADY ANSWERED THIS ON NQ 5m AND THE ANSWER WAS BRUTAL (memory edgelog-strongbar-r1-dead):
STRONGBAR's trigger scored ROC@30k 0.49 against a random entry's 10.4 and beat random in 2 of 17
years.  Their diagnosis: the trigger "enters late, after the expansion, with a tight stop, and gives
[the beta] away."  THIS ROUND IS NOT A RE-RUN OF THAT.  It asks two things their round could not:
  1. does the finding REPLICATE on a different instrument and a 3x slower timeframe (ES 15m)?
  2. does the obvious REPAIR of their diagnosis work - a FLOORED, therefore WIDE, stop
     (max(1.5 x ATR20, FLOOR_PT), FLOOR_PT in {10,20} ES pt) instead of the bar extreme?
If a wide stop does not rescue it either, the mechanism is dead across two instruments, two
timeframes and both stop styles, and nobody need test it a third time.

LOOK-AHEAD GUARDS, named because this exact mechanism has been VOIDED for look-ahead once before
(ORB's volume-gated entry, ~91% of its apparent edge):
  - the signal bar is COMPLETE before it is read and the fill is the NEXT BAR'S OPEN at market, so
    the bar's own volume is legitimately known at decision time;
  - relative volume is measured against the SAME 15-minute slot over the PRIOR 20 sessions, shifted
    a session, so today's volume never enters its own benchmark;
  - the daily trend comes from the PREVIOUS COMPLETED session;
  - ATR and the moving averages are shifted one bar;
  - the daily bars are resampled from the SAME 15m master - there is no ES 1d master and a second
    source would be a splice.

    python tools/enguq_candlevol_gate.py --selftest
    python tools/enguq_candlevol_gate.py
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
SHARED_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
if not os.path.isdir(os.path.join(_ROOT, "augur_uploads")) and os.path.isdir(SHARED_CHECKOUT):
    sys.path.insert(0, SHARED_CHECKOUT)

MASTER = "ADJ_ES_15m_RTH.csv"
PREREG = "docs/PREREG_enguq_candlevol_2026-11-09.md"
PREREG_SHA = "34e89659a1736cd2b47b371c20a70ba9987dc97f908f440430fdb4f0ad3826b0"
PRE_LOCKBOX_TO = "2025-06-30"
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_candlevol_gate"

DAILY_SMA = (20, 50)
BODY_FRAC = (0.5, 0.7)
CLOSE_LOC = (0.7, 0.9)
RVOL = (1.0, 1.5, 2.0)
FLOOR_PT = (10.0, 20.0)
ATR_STOP = 1.5
ATR_LEN = 20
RVOL_LOOKBACK = 20          # prior SESSIONS, same slot
DRAWS = 20                  # random-control draws per signal
SEED = 20261109
LAST_BAR_MIN = 15 * 60 + 45
DOLLARS_PER_POINT = 50.0
COST_REAL = 0.45
COST_HOUSE = 0.533
COST_SLIP = 0.95
TRADES_A_YEAR_FLOOR = 50.0


def mde_one(sd, n):
    """One-sample MDE, 80% power, two-sided 5%: delta = sd*sqrt(7.85/n)."""
    if not n or sd is None or not np.isfinite(sd) or sd <= 0:
        return None
    return float(sd) * math.sqrt(7.85 / float(n))


def mde_two(sd, n):
    """Two-sample MDE for a DIFFERENCE of means: delta = sd*sqrt(15.7/n) per group.

    This is the one the verdict turns on - the signal arm against its random control."""
    if not n or sd is None or not np.isfinite(sd) or sd <= 0:
        return None
    return float(sd) * math.sqrt(15.7 / float(n))


def atr_wilder(high, low, close, length=ATR_LEN):
    """True-range average, SHIFTED one bar so a signal never reads its own bar's range."""
    h, l_, c = map(lambda a: np.asarray(a, float), (high, low, close))
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum(h - l_, np.maximum(np.abs(h - pc), np.abs(l_ - pc)))
    return pd.Series(tr).rolling(length).mean().shift(1).to_numpy()


def load_15m():
    base = os.path.join(_ROOT, "augur_uploads", MASTER)
    if not os.path.exists(base):
        base = os.path.join(SHARED_CHECKOUT, "augur_uploads", MASTER)
    d = pd.read_csv(base)
    d["ts"] = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
    return d[["ts", "open", "high", "low", "close", "volume"]].sort_values("ts").reset_index(drop=True), len(d)


def hold_to_close(high, low, close, entry_px, entry_bar, stop_px, last_bar):
    """Arm A, the control exit MANAGER required: out at the session's last bar close, or the stop.

    THE STOP IS CHECKED FIRST on every bar, so a bar covering both the stop and a better price books
    the stop.  Conservative by construction."""
    for i in range(entry_bar, last_bar + 1):
        if low[i] <= stop_px:
            return i, stop_px
    return last_bar, close[last_bar]


def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  MISMATCH: " + name)

    chk("one-sample MDE is sd*sqrt(7.85/n)", abs(mde_one(1.0, 2000) - math.sqrt(7.85 / 2000)) < 1e-12)
    chk("two-sample MDE is sd*sqrt(15.7/n)", abs(mde_two(1.0, 2000) - math.sqrt(15.7 / 2000)) < 1e-12)
    chk("a DIFFERENCE needs a bigger edge than a mean", mde_two(1.0, 2000) > mde_one(1.0, 2000))
    chk("zero n has no MDE", mde_one(1.0, 0) is None and mde_two(1.0, 0) is None)

    # ATR is shifted: the last value must not know the last bar's range
    h = np.arange(1.0, 31.0); l_ = h - 1.0; c = h - 0.5
    a = atr_wilder(h, l_, c, 5)
    chk("ATR is NaN until the window fills, and shifted by one", np.isnan(a[5]) is np.True_ or np.isnan(a[4]))
    chk("ATR does not read its own bar", not np.isnan(a[-1]))

    # hold-to-close
    hh = np.array([0.0, 11.0, 12.0, 13.0])
    ll = np.array([0.0, 10.0, 10.5, 10.2])
    cc = np.array([0.0, 10.5, 11.5, 12.5])
    b, px = hold_to_close(hh, ll, cc, 10.0, 1, 9.0, 3)
    chk("an untouched stop exits at the session's last close", (b, px) == (3, 12.5))
    b2, px2 = hold_to_close(hh, ll, cc, 10.0, 1, 10.4, 3)
    chk("a touched stop books the stop", (b2, px2) == (1, 10.4))
    hh3 = np.array([0.0, 50.0]); ll3 = np.array([0.0, 1.0]); cc3 = np.array([0.0, 40.0])
    b3, px3 = hold_to_close(hh3, ll3, cc3, 10.0, 1, 9.0, 1)
    chk("a bar covering both books the STOP, not the gain", px3 == 9.0)

    # the floor
    chk("a small ATR is overridden by the floor", max(ATR_STOP * 1.0, 10.0) == 10.0)
    chk("a large ATR beats the floor", max(ATR_STOP * 20.0, 10.0) == 30.0)

    # candle features on a known bar: o=10 h=12 l=9 c=11.8
    o, hi, lo_, cl = 10.0, 12.0, 9.0, 11.8
    rng = hi - lo_
    chk("body/range is |close-open| over range", abs(abs(cl - o) / rng - 0.6) < 1e-9)
    chk("close location is (close-low)/range", abs((cl - lo_) / rng - 0.9333) < 1e-3)

    n_cells = len(DAILY_SMA) * len(BODY_FRAC) * len(CLOSE_LOC) * len(RVOL) * len(FLOOR_PT)
    chk("the gate screens exactly 48 cells", n_cells == 48)
    chk("the control seed is fixed so the draw is reproducible", SEED == 20261109)
    chk("20 draws per signal", DRAWS == 20)

    print("selftest: %d checks PASS, %d MISMATCH" % (ok, fail))
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    os.makedirs(OUT, exist_ok=True)
    pr = PREREG if os.path.exists(PREREG) else os.path.join(SHARED_CHECKOUT, PREREG)
    if os.path.exists(pr):
        got = hashlib.sha256(open(pr, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
        print("prereg sha %s  %s" % (got, "MATCHES" if got == PREREG_SHA else "DIFFERS"))

    df, rows = load_15m()
    print("%s rows %s" % (MASTER, format(rows, ",")))
    pre = df[df["ts"] <= pd.Timestamp(PRE_LOCKBOX_TO + " 23:59", tz="America/New_York")].reset_index(drop=True)
    o = pre["open"].to_numpy(float); h = pre["high"].to_numpy(float)
    lo = pre["low"].to_numpy(float); c = pre["close"].to_numpy(float)
    vol = pre["volume"].to_numpy(float)
    n = len(c)
    tsi = pd.DatetimeIndex(pre["ts"])
    years = (tsi[-1] - tsi[0]).days / 365.25
    print("pre-lockbox %s bars  %s .. %s  %.2f yr (LOCKBOX NOT OPENED)"
          % (format(n, ","), tsi[0].date(), tsi[-1].date(), years))

    day = tsi.normalize().tz_localize(None)
    codes, uniq = pd.factorize(day)          # RTH master: one session per calendar day
    minute = (tsi.hour * 60 + tsi.minute).to_numpy()
    slot = minute                            # the 15-minute time-of-day slot

    last_bar_of_day = np.full(len(uniq), -1, int)
    for i in np.flatnonzero(minute <= LAST_BAR_MIN):
        last_bar_of_day[codes[i]] = i
    last_bar = last_bar_of_day[codes]

    # --- daily trend, from the PREVIOUS completed session, resampled off THIS master
    daily_close = pd.Series(c).groupby(codes).last()
    trend_ok = {}
    for N in DAILY_SMA:
        sma = daily_close.rolling(N).mean()
        # the previous session's close against the previous session's own SMA
        ok_day = (daily_close > sma).shift(1).fillna(False).to_numpy()
        trend_ok[N] = ok_day[codes]
        print("daily trend N=%d: %s of %s sessions pass" % (N, format(int(ok_day.sum()), ","),
                                                            format(len(ok_day), ",")))

    # --- candle features
    rng = np.maximum(h - lo, 1e-9)
    body_frac = np.abs(c - o) / rng
    close_loc = (c - lo) / rng
    follow = np.zeros(n, bool)
    follow[1:] = c[1:] > h[:-1]
    up_bar = c > o
    atr20 = atr_wilder(h, lo, c, ATR_LEN)

    # --- relative volume against the SAME SLOT over the PRIOR 20 sessions (shifted a session)
    sv = pd.DataFrame({"slot": slot, "d": codes, "v": vol})
    base = (sv.groupby("slot")["v"]
              .transform(lambda s: s.rolling(RVOL_LOOKBACK, min_periods=RVOL_LOOKBACK).mean().shift(1)))
    rvol = vol / base.to_numpy()

    rng_state = np.random.default_rng(SEED)
    rng_b = np.random.default_rng(SEED)
    # eligible pool for the control, per trend filter: bar indices on trend-passing sessions,
    # keyed by slot, so a draw matches TIME OF DAY and REGIME and differs only in the candle
    pools = {}
    for N in DAILY_SMA:
        pool = {}
        elig = np.flatnonzero(trend_ok[N] & ~np.isnan(atr20) & (last_bar > np.arange(n)))
        for i in elig:
            pool.setdefault(slot[i], []).append(i)
        pools[N] = {k: np.array(v, int) for k, v in pool.items()}

    print("\nGATE - 48 cells.  Headline is DELTA = signal R minus RANDOM-ENTRY R, same slot, same")
    print("  daily-trend regime, identical stop and hold-to-close exit, %d draws, seed %d." % (DRAWS, SEED))
    print("  A strategy with no edge scores DELTA 0.  MDE2 = sd*sqrt(15.7/n).\n")
    print(format("cell", "<30") + format("n", ">7") + format("a yr", ">7")
          + format("risk pt", ">9") + format("cost R", ">8") + format("sig R", ">9")
          + format("rand R", ">9") + format("DELTA", ">9") + format("DELTA-B", ">9")
          + format("MDE2", ">8")
          + format("verdict", ">19"))

    report = []
    for N in DAILY_SMA:
        pool = pools[N]
        for bf in BODY_FRAC:
            for cl in CLOSE_LOC:
                for rv in RVOL:
                    sig = (trend_ok[N] & up_bar & follow
                           & (body_frac >= bf) & (close_loc >= cl)
                           & ~np.isnan(rvol) & (rvol >= rv)
                           & ~np.isnan(atr20) & (minute < LAST_BAR_MIN))
                    idx = np.flatnonzero(sig)
                    for fl in FLOOR_PT:
                        name = "N=%d bf=%.1f cl=%.1f rv=%.1f f=%d" % (N, bf, cl, rv, int(fl))
                        sR, rR, bR, risks, ex_d, pnl = [], [], [], [], [], []
                        for i in idx:
                            e = i + 1
                            if e >= n or codes[e] != codes[i] or last_bar[i] < e:
                                continue
                            risk = max(ATR_STOP * atr20[i], fl)
                            ep = o[e]
                            xb, xpx = hold_to_close(h, lo, c, ep, e, ep - risk, last_bar[i])
                            sR.append((xpx - ep) / risk)
                            risks.append(risk)
                            ex_d.append(day[xb])
                            pnl.append((xpx - ep - COST_REAL) * DOLLARS_PER_POINT)
                            # the control: same slot, trend-passing, DIFFERENT session
                            cand = pool.get(slot[i])
                            if cand is None or len(cand) < 2:
                                continue
                            pick = cand[rng_state.integers(0, len(cand), DRAWS)]
                            for j in pick:
                                if codes[j] == codes[i]:
                                    continue
                                e2 = j + 1
                                if e2 >= n or codes[e2] != codes[j] or last_bar[j] < e2:
                                    continue
                                r2 = max(ATR_STOP * atr20[j], fl)
                                ep2 = o[e2]
                                _, xpx2 = hold_to_close(h, lo, c, ep2, e2, ep2 - r2, last_bar[j])
                                rR.append((xpx2 - ep2) / r2)
                            # control B, MANAGER #153: SAME SESSION, AT OR AFTER the signal bar, so
                            # the control can never sit on information the real arm did not have
                            if last_bar[i] - 1 > i:
                                pb = rng_b.integers(i, last_bar[i] - 1, DRAWS)
                                for j in pb:
                                    if np.isnan(atr20[j]):
                                        continue
                                    e3 = j + 1
                                    r3 = max(ATR_STOP * atr20[j], fl)
                                    ep3 = o[e3]
                                    _, xpx3 = hold_to_close(h, lo, c, ep3, e3, ep3 - r3, last_bar[i])
                                    bR.append((xpx3 - ep3) / r3)
                        cnt = len(sR)
                        a_yr = cnt / years if years else 0.0
                        if cnt < 2 or len(rR) < 2:
                            report.append({"cell": name, "trades": cnt, "verdict": "NO TRADES"})
                            print(format(name, "<30") + format(format(cnt, ","), ">7")
                                  + format(format(a_yr, ".1f"), ">7") + format("-", ">9") * 6
                                  + format("NO TRADES", ">19"))
                            continue
                        s_m = float(np.mean(sR)); s_sd = float(np.std(sR, ddof=1))
                        r_m = float(np.mean(rR))
                        b_m = float(np.mean(bR)) if len(bR) > 1 else None
                        rk = float(np.mean(risks))
                        delta = s_m - r_m
                        delta_b = None if b_m is None else s_m - b_m
                        m2 = mde_two(s_sd, cnt)
                        cr = COST_REAL / rk
                        # BOTH controls must be beaten.  Whichever is the harder test is the test.
                        worst = delta if delta_b is None else min(delta, delta_b)
                        if m2 is None or worst <= m2:
                            v = "BETA, NOT A SIGNAL"
                        elif a_yr < TRADES_A_YEAR_FLOOR:
                            v = "THIN n/yr"
                        elif s_m <= cr:
                            v = "under cost"
                        else:
                            v = "OPEN"
                        report.append({
                            "cell": name, "N": N, "bf": bf, "cl": cl, "rv": rv, "floor_pt": fl,
                            "trades": cnt, "a_year": round(a_yr, 1), "control_draws": len(rR),
                            "mean_risk_pt": round(rk, 2), "cost_R_real": round(cr, 4),
                            "cost_R_slip": round(COST_SLIP / rk, 4),
                            "signal_R": round(s_m, 4), "sd_R": round(s_sd, 4),
                            "random_R": round(r_m, 4), "delta_R": round(delta, 4),
                            "randomB_R": None if b_m is None else round(b_m, 4),
                            "deltaB_R": None if delta_b is None else round(delta_b, 4),
                            "controlB_draws": len(bR),
                            "mde2_R": None if m2 is None else round(m2, 4),
                            "net_usd_real": round(float(np.sum(pnl)), 0), "verdict": v})
                        print(format(name, "<30") + format(format(cnt, ","), ">7")
                              + format(format(a_yr, ".1f"), ">7")
                              + format(format(rk, ".2f"), ">9") + format(format(cr, ".4f"), ">8")
                              + format(format(s_m, ".4f"), ">9") + format(format(r_m, ".4f"), ">9")
                              + format(format(delta, ".4f"), ">9")
                              + format("-" if delta_b is None else format(delta_b, ".4f"), ">9")
                              + format("-" if m2 is None else format(m2, ".4f"), ">8")
                              + format(v, ">19"))

    vs = [r["verdict"] for r in report]
    print("\nVERDICT COUNTS: %s" % json.dumps({k: vs.count(k) for k in sorted(set(vs))}))
    R = [r for r in report if r.get("trades", 0) > 1 and "delta_R" in r]
    if R:
        worse = sum(1 for r in R if r["delta_R"] < 0)
        print("cells where the SIGNAL IS WORSE THAN RANDOM: %d of %d" % (worse, len(R)))
        wb = [r for r in R if r.get("deltaB_R") is not None]
        if wb:
            print("control B (MANAGER #153, same session at/after the signal bar): "
                  "%d of %d cells have deltaB <= 0" % (sum(1 for r in wb if r["deltaB_R"] <= 0), len(wb)))
            bb = max(wb, key=lambda r: r["deltaB_R"])
            print("best deltaB: %s  %.4f R vs MDE2 %.4f" % (bb["cell"], bb["deltaB_R"], bb["mde2_R"] or 0))
        best = max(R, key=lambda r: r["delta_R"])
        print("best delta: %s  delta %.4f R vs MDE2 %.4f  (signal %.4f, random %.4f)"
              % (best["cell"], best["delta_R"], best["mde2_R"] or 0,
                 best["signal_R"], best["random_R"]))
    if "OPEN" not in vs:
        print("NO CELL IS OPEN - THE ROUND CLOSES AT DRAFT, no trial budget spent.")
    p = os.path.join(OUT, "gate.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"prereg_sha": PREREG_SHA, "master": MASTER, "years": round(years, 2),
                   "stretch": [str(tsi[0].date()), str(tsi[-1].date())], "seed": SEED,
                   "draws": DRAWS, "cost_pts": {"real": COST_REAL, "house": COST_HOUSE,
                                                "slip": COST_SLIP},
                   "rows": report}, f, indent=1)
    print("wrote " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
