"""ENGU-Q SWING STRUCTURE BREAK - the 36-cell POWER-FIRST GATE, NQ 1h / 4h / daily, multi-day holds.

Owner order 11-13 (MANAGER, board w121 PRICE-ACTION HUNT), prereg
docs/PREREG_enguq_swingbreak_2026-11-13.md, LF-normalised body sha
fd0820c6bde7c9b4a00fea9d3235b5ecf5298d146e42585ac25910ebd5979b1b.

A confirmed-pivot HH/HL state machine, long only, entering on a close above the last confirmed swing
high, stopping at the last confirmed swing low, exiting on a close below the swing low that TRAILS
upward as new pivots confirm.  Multi-day holds, no time cap, no target.

THE HEADLINE IS THE PAIRED DIFFERENCE AGAINST AN AFTER-SIGNAL-ONLY RANDOM CONTROL.  The control
enters at a randomly chosen bar ON OR AFTER the signal bar inside the same move and runs the
IDENTICAL stop, gap rule and structure exit, so it can never see information the real arm did not
have - the defect that inflated STRONGBAR's control (MANAGER #153).  A strategy whose structure
break adds nothing over "enter somewhere in this move" scores delta 0.

THE DEAD CATALOGUE HITS THIS LENS TWICE (prereg section 1): "SWING 2.0 N-day Donchian long-only,
NQ+ES, days-weeks" FAILED ITS LOCKBOX with blow-up losses, and ENGU-Q's own HIGHER LOWS gate was one
of six that died.  Declared prior: under 12%.

COST IS NOT THE BINDING CONSTRAINT HERE and that is deliberate - on a 1h/4h/daily swing, R is tens to
hundreds of NQ points, so the 0.783 pt book round trip is under 2% of 1R.  This round cannot fail on
arithmetic; if it dies, it dies on the market.

    python tools/enguq_swingbreak_gate.py --selftest
    python tools/enguq_swingbreak_gate.py
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

MASTER = "ADJ_NQ_60m_RTH.csv"
PREREG = "docs/PREREG_enguq_swingbreak_2026-11-13.md"
PREREG_COMMIT = "68a886c4"   # the commit that froze the body, before ADDENDUM 1
PREREG_SHA = "fd0820c6bde7c9b4a00fea9d3235b5ecf5298d146e42585ac25910ebd5979b1b"
PRE_LOCKBOX_TO = "2025-06-30"
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_swingbreak_gate"

TFS = ("1h", "4h", "1d")
KS = (2, 3, 5)
TRENDS = ("HH_AND_HL", "HH_ONLY")
STOPS = ("STRUCT", "STRUCT_ATR")
EXITS = ("TRAIL_STOP", "CLOSE_ONLY")   # prereg ADDENDUM 1 - see run_trade()
ATR_LEN = 20
DRAWS = 20
SEED = 20261113
HORIZONS = (5, 10, 20)      # ADDENDUM 2 - the control window, in bars, FIXED and outcome-blind
H_JUDGE = 10                # the verdict runs on this one; the others are the sensitivity
DOLLARS_PER_POINT = 20.0
COST_HOUSE = 0.533          # house NQ round trip, $20/pt
COST_BOOK = 0.783           # BOOK #463's registered 24-hour ENGU-Q convention
COST_STRESS = 1.566         # double the book convention - a multi-day gap is where slippage lands
TRADES_A_YEAR_FLOOR = 20.0  # declared in the prereg BEFORE any count was seen
N_FOLDS = 8
NOMINAL_ACCOUNT = 100000.0


def mde_one(sd, n):
    if not n or sd is None or not np.isfinite(sd) or sd <= 0:
        return None
    return float(sd) * math.sqrt(7.85 / float(n))


def mde_two(sd, n):
    """Two-sample MDE for a DIFFERENCE of means - the one the verdict turns on."""
    if not n or sd is None or not np.isfinite(sd) or sd <= 0:
        return None
    return float(sd) * math.sqrt(15.7 / float(n))


def atr_wilder(high, low, close, length=ATR_LEN):
    """SHIFTED one bar, so nothing reads its own bar's range."""
    h, l_, c = (np.asarray(a, float) for a in (high, low, close))
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum(h - l_, np.maximum(np.abs(h - pc), np.abs(l_ - pc)))
    return pd.Series(tr).rolling(length).mean().shift(1).to_numpy()


def resample(df, tf):
    """1h is the master itself.  4h = two blocks a session (09:30-13:29, 13:30-close).  1d = one bar.

    EMPTY BINS ARE DROPPED, NEVER FORWARD FILLED - a bar that did not trade must not become a signal
    bar or a pivot.  Everything is built from ONE tape; there is no registered NQ 4h or 1d master and
    manufacturing one from a second source would be a splice."""
    if tf == "1h":
        return df.reset_index(drop=True)
    ts = pd.DatetimeIndex(df["ts"])
    day = ts.normalize()
    if tf == "1d":
        key = day
    elif tf == "4h":
        mins = ts.hour * 60 + ts.minute
        key = day + pd.to_timedelta(np.where(mins < 13 * 60 + 30, 9 * 60 + 30, 13 * 60 + 30), unit="m")
    else:
        raise ValueError(tf)
    g = df.assign(_k=key).groupby("_k", sort=True)
    out = pd.DataFrame({"ts": g["ts"].first(), "open": g["open"].first(), "high": g["high"].max(),
                        "low": g["low"].min(), "close": g["close"].last(),
                        "n": g["close"].count()})
    return out[out["n"] > 0].drop(columns="n").reset_index(drop=True)


def confirmed_pivots(high, low, k):
    """pivot_hi[t] / pivot_lo[t] = the price of the most recent pivot CONFIRMED STRICTLY BEFORE t.

    A pivot at bar i is the strict extreme of [i-k, i+k].  It cannot be known until bar i+k, so it is
    published into the arrays from i+k+1 onward.  THIS IS THE WHOLE LOOK-AHEAD SURFACE OF THE DESIGN.
    Returns the last two highs and the last two lows as of each bar."""
    n = len(high)
    H1 = np.full(n, np.nan); H2 = np.full(n, np.nan)
    L1 = np.full(n, np.nan); L2 = np.full(n, np.nan)
    h1 = h2 = l1 = l2 = np.nan
    for t in range(n):
        i = t - k - 1                      # the bar whose pivot status becomes usable at t
        if i >= k:
            if high[i] == np.max(high[i - k:i + k + 1]) and np.sum(high[i - k:i + k + 1] == high[i]) == 1:
                h2, h1 = h1, high[i]
            if low[i] == np.min(low[i - k:i + k + 1]) and np.sum(low[i - k:i + k + 1] == low[i]) == 1:
                l2, l1 = l1, low[i]
        H1[t], H2[t], L1[t], L2[t] = h1, h2, l1, l2
    return H1, H2, L1, L2


def run_trade(o, h, lo, c, entry_bar, stop0, L1, n, exit_mode="TRAIL_STOP"):
    """Long from entry_bar's OPEN.  TWO exit arms - prereg ADDENDUM 1 says why there are two.

    A DEFECT IN MY OWN PREREG, FOUND BEFORE ANY NUMBER WAS MEASURED AND FIXED BY ADDENDUM: section 4
    specified an intrabar stop AT the trailing pivot low AND an exit on a CLOSE below that same
    level, "whichever comes first".  Those are not two rules.  A close below the level implies the
    bar's low was below it, so the intrabar stop ALWAYS fires first and the close clause can NEVER
    fire - satisfied-by-construction in the dead direction, the same near-vacuity that made BBRF's
    ceiling clause worthless (ledger 2.220).  So the two readings become two arms and BOTH are run:

      TRAIL_STOP - the literal reading.  The stop RATCHETS UP to each newly confirmed pivot low and
                   is taken INTRABAR.  Tight: it exits the moment structure is touched.
      CLOSE_ONLY - the swing-trading reading.  The ORIGINAL pivot low stays as the disaster stop,
                   taken intrabar, but the TRAIL is honoured only on a CLOSE below it.  Loose: it
                   gives a multi-day hold room to breathe, which is the arm this lane's seven
                   hold-finding confirmations predict should win.

    GAP REALISM (both arms): a stop fills at min(stop, that bar's open).  On an RTH tape a multi-day
    position is unwatched overnight, so a session that gaps through the stop fills at the gap open,
    NOT at the stop price.  Naive stop fills would hand this design free money on exactly the days it
    should lose most, and SWING 2.0's recorded failure mode was BLOW-UP LOSSES."""
    entry = o[entry_bar]
    stop = stop0
    for i in range(entry_bar, n):
        trail = L1[i]
        # L1[i] is the last pivot low CONFIRMED STRICTLY BEFORE bar i, so it is already known at
        # bar i's open and the ratchet must happen BEFORE this bar's stop check - deferring it a bar
        # would quietly give the trade a free bar below its own structure.  The trail is only ever
        # raised to a level under the last price we actually knew (the previous close), so a pivot
        # that has already been exceeded can never stop the trade out at its own entry.
        if not np.isnan(trail) and trail > stop and i > 0 and trail < c[i - 1]:
            if exit_mode == "TRAIL_STOP":
                stop = trail                      # ratchets UP, never down
                if lo[i] <= stop:
                    return i, min(stop, o[i]), "stop"
            elif i > entry_bar and c[i] < trail:
                if lo[i] <= stop:                 # the ORIGINAL stop still bites first intrabar
                    return i, min(stop, o[i]), "stop"
                return i, c[i], "structure"       # the trail is honoured only on a CLOSE
        if lo[i] <= stop:
            return i, min(stop, o[i]), "stop"
    return n - 1, c[n - 1], "end"


def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  MISMATCH: " + name)

    chk("one-sample MDE is sd*sqrt(7.85/n)", abs(mde_one(1.0, 500) - math.sqrt(7.85 / 500)) < 1e-12)
    chk("two-sample MDE is sd*sqrt(15.7/n)", abs(mde_two(1.0, 500) - math.sqrt(15.7 / 500)) < 1e-12)
    chk("a difference needs a bigger edge than a mean", mde_two(1.0, 500) > mde_one(1.0, 500))
    chk("zero n has no MDE", mde_one(1.0, 0) is None)

    # --- pivots are published LATE and never early
    hi = np.array([1, 2, 5, 2, 1, 2, 6, 2, 1, 1, 1, 1], float)
    lo_ = hi - 1.0
    H1, H2, L1, L2 = confirmed_pivots(hi, lo_, 2)
    chk("the bar-2 pivot high is NOT known at bar 4", np.isnan(H1[4]))
    chk("the bar-2 pivot high IS known at bar 5", H1[5] == 5.0)
    chk("no pivot is published before its confirmation bar", np.isnan(H1[3]))
    chk("the second pivot high lands in H2", H1[9] == 6.0 and H2[9] == 5.0)

    # --- a plateau is not a pivot (strictness)
    hp = np.array([1, 2, 5, 5, 1, 1, 1, 1], float)
    Hp, _, _, _ = confirmed_pivots(hp, hp - 1.0, 2)
    chk("a tied double top is not a pivot", np.isnan(Hp[-1]))

    # --- the trade engine
    n = 6
    o = np.array([0, 10.0, 11, 12, 13, 14]); h = np.array([0, 11.0, 12, 13, 14, 15])
    lo2 = np.array([0, 9.5, 10.5, 11.5, 12.5, 13.5]); c = np.array([0, 10.8, 11.8, 12.8, 13.8, 14.8])
    noL = np.full(n, np.nan)
    b, px, why = run_trade(o, h, lo2, c, 1, 8.0, noL, n)
    chk("an untouched trade runs to the end of the tape", (b, why) == (n - 1, "end"))
    b, px, why = run_trade(o, h, lo2, c, 1, 9.6, noL, n)
    chk("a touched stop books the stop", (px, why) == (9.6, "stop"))

    # GAP: the bar opens BELOW the stop -> fill at the open, not the stop
    og = np.array([0, 10.0, 7.0]); hg = np.array([0, 11.0, 7.5])
    log = np.array([0, 9.8, 6.0]); cg = np.array([0, 10.8, 7.2])
    b, px, why = run_trade(og, hg, log, cg, 1, 9.0, np.full(3, np.nan), 3)
    chk("a gap THROUGH the stop fills at the OPEN, not the stop", (px, why) == (7.0, "stop"))

    # --- the two exit arms.  THE PREVIOUS FIXTURE HERE WAS WRONG, NOT THE CODE: its price path rose
    # throughout, so nothing could ever close below the trail.  This one actually falls through it.
    of = np.array([0, 10.0, 12.0, 13.0, 13.0]); hf = np.array([0, 11.0, 13.0, 13.5, 13.2])
    lof = np.array([0, 9.8, 11.8, 11.5, 11.4]); cf = np.array([0, 10.9, 12.9, 11.6, 11.5])
    Lf = np.array([np.nan, 9.0, 9.0, 12.0, 12.0])
    b, px, why = run_trade(of, hf, lof, cf, 1, 9.0, Lf, 5, "TRAIL_STOP")
    chk("TRAIL_STOP takes the ratcheted level INTRABAR, on the bar it becomes usable",
        (b, px, why) == (3, 12.0, "stop"))
    b2, px2, why2 = run_trade(of, hf, lof, cf, 1, 9.0, Lf, 5, "CLOSE_ONLY")
    chk("CLOSE_ONLY ignores the intrabar touch and waits for the CLOSE", why2 == "structure")
    chk("CLOSE_ONLY exits AT the close", px2 == cf[b2])
    chk("the two arms are genuinely different rules", px != px2)
    chk("CLOSE_ONLY still honours the ORIGINAL stop intrabar",
        run_trade(of, hf, np.array([0, 9.8, 11.8, 8.0, 8.0]), cf, 1, 9.0, Lf, 5, "CLOSE_ONLY")[2] == "stop")
    chk("CLOSE_ONLY holds past a touch that TRAIL_STOP would take", b2 == 3 and px2 == 11.6)
    # a pivot that price has ALREADY run past must not arm a stop above the market
    chk("the trail is never raised above the last known price",
        run_trade(np.array([0, 10.0, 10.0]), np.array([0, 11.0, 11.0]), np.array([0, 9.9, 9.9]),
                  np.array([0, 10.5, 10.5]), 1, 9.0, np.array([np.nan, 99.0, 99.0]), 3)[2] == "end")
    Ld = np.array([np.nan, 9.0, 9.0, 5.0, 5.0])
    chk("the trail never RATCHETS DOWN on a lower pivot",
        run_trade(of, hf, lof, cf, 1, 9.0, Ld, 5, "TRAIL_STOP")[2] == "end")

    # --- resampling drops empty bins and keeps OHLC honest
    ts = pd.date_range("2024-01-02 09:30", periods=7, freq="60min", tz="America/New_York")
    df = pd.DataFrame({"ts": ts, "open": np.arange(7.0), "high": np.arange(7.0) + 1,
                       "low": np.arange(7.0) - 1, "close": np.arange(7.0) + 0.5})
    d4 = resample(df, "4h")
    chk("4h makes two blocks from one session", len(d4) == 2)
    chk("the 4h high is the max of its members", d4["high"].iloc[0] == 4.0)
    d1 = resample(df, "1d")
    chk("1d makes one bar a session", len(d1) == 1 and d1["close"].iloc[0] == 6.5)
    chk("1d low is the min of the session", d1["low"].iloc[0] == -1.0)

    chk("the gate screens exactly 72 cells after addendum 1",
        len(TFS) * len(KS) * len(TRENDS) * len(STOPS) * len(EXITS) == 72)
    chk("the trades-a-year floor was declared as 20", TRADES_A_YEAR_FLOOR == 20.0)
    chk("the control seed is fixed", SEED == 20261113)

    print("selftest: %d checks PASS, %d MISMATCH" % (ok, fail))
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    os.makedirs(OUT, exist_ok=True)
    # The frozen BODY is verified against its own commit, not against the working file, because
    # ADDENDUM 1 was appended after the freeze and legitimately changes the file's sha.  Checking
    # the live file would either fail forever or tempt me to re-freeze a body I have already
    # published - so the body is read back from 68a886c4 and the addendum carries its own sha.
    import subprocess
    try:
        blob = subprocess.run(["git", "show", "%s:%s" % (PREREG_COMMIT, PREREG)],
                              cwd=SHARED_CHECKOUT, capture_output=True).stdout
        got = hashlib.sha256(blob.replace(b"\r\n", b"\n")).hexdigest()
        print("frozen prereg body (%s) sha %s  %s"
              % (PREREG_COMMIT, got, "MATCHES" if got == PREREG_SHA else "DIFFERS"))
    except Exception as e:                                        # noqa: BLE001
        print("could not verify the frozen body: %s" % e)
    pr = PREREG if os.path.exists(PREREG) else os.path.join(SHARED_CHECKOUT, PREREG)
    if os.path.exists(pr):
        cur = hashlib.sha256(open(pr, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
        print("prereg WITH addendum 1 sha %s" % cur)

    base = os.path.join(_ROOT, "augur_uploads", MASTER)
    if not os.path.exists(base):
        base = os.path.join(SHARED_CHECKOUT, "augur_uploads", MASTER)
    raw = pd.read_csv(base)
    raw["ts"] = pd.to_datetime(raw["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
    raw = raw[["ts", "open", "high", "low", "close"]].sort_values("ts").reset_index(drop=True)
    print("%s rows %s" % (MASTER, format(len(raw), ",")))
    raw = raw[raw["ts"] <= pd.Timestamp(PRE_LOCKBOX_TO + " 23:59", tz="America/New_York")].reset_index(drop=True)
    tsa = pd.DatetimeIndex(raw["ts"])
    years = (tsa[-1] - tsa[0]).days / 365.25
    print("pre-lockbox %s 60m bars  %s .. %s  %.2f yr (LOCKBOX NOT OPENED)"
          % (format(len(raw), ","), tsa[0].date(), tsa[-1].date(), years))

    rng = np.random.default_rng(SEED)
    print("\nGATE - 72 cells (36 x two exit arms, prereg ADDENDUM 1).  DELTA = signal R minus an AFTER-SIGNAL-ONLY random entry in the SAME")
    print("  move, identical stop, gap rule and structure exit, %d draws, seed %d." % (DRAWS, SEED))
    print("  Judged on EV R and ROC/yr (owner w121); ROC@30k and DD are carried but NOT judged.\n")
    print(format("cell", "<32") + format("n", ">6") + format("a yr", ">6") + format("R pt", ">8")
          + format("hold", ">7") + format("EV R", ">8") + format("rand R", ">8")
          + format("DELTA", ">8") + format("MDE2", ">8") + format("ROC/yr", ">8")
          + format("fold+", ">7") + format("verdict", ">18"))

    report = []
    for tf in TFS:
        d = resample(raw, tf)
        o = d["open"].to_numpy(float); h = d["high"].to_numpy(float)
        lo = d["low"].to_numpy(float); c = d["close"].to_numpy(float)
        n = len(c)
        bts = pd.DatetimeIndex(d["ts"])
        atr = atr_wilder(h, lo, c, ATR_LEN)
        for k in KS:
            H1, H2, L1, L2 = confirmed_pivots(h, lo, k)
            for tr in TRENDS:
                up = (H1 > H2) if tr == "HH_ONLY" else ((H1 > H2) & (L1 > L2))
                up = np.nan_to_num(up, nan=False).astype(bool)
                brk = up & ~np.isnan(H1) & (c > H1) & ~np.isnan(L1)
                for st in STOPS:
                  for xm in EXITS:
                    name = "%s k=%d %s %s %s" % (tf, k, "HH" if tr == "HH_ONLY" else "HH+HL",
                                                 "S" if st == "STRUCT" else "S+ATR",
                                                 "trail" if xm == "TRAIL_STOP" else "close")
                    sR, risks, holds, pnl, ex_ts = [], [], [], [], []
                    rR = {H: [] for H in HORIZONS}
                    t = 0
                    while t < n - 2:
                        if not brk[t]:
                            t += 1
                            continue
                        e = t + 1
                        entry = o[e]
                        s0 = L1[t]
                        if st == "STRUCT_ATR" and not np.isnan(atr[t]):
                            s0 = min(s0, entry - 1.0 * atr[t])   # only ever LOOSENS a tight stop
                        risk = entry - s0
                        if not np.isfinite(risk) or risk <= 0:
                            t += 1
                            continue
                        xb, xpx, _ = run_trade(o, h, lo, c, e, s0, L1, n, xm)
                        sR.append((xpx - entry) / risk)
                        risks.append(risk)
                        holds.append(xb - e + 1)
                        pnl.append((xpx - entry - COST_BOOK) * DOLLARS_PER_POINT)
                        ex_ts.append(bts[xb])
                        # CONTROL: enter at a random bar ON OR AFTER the signal bar, inside this
                        # same move, with the SAME stop, gap rule and structure exit.  It can never
                        # draw a bar before the signal, so it sees nothing the real arm did not.
                        # THE CONTROL WINDOW IS A FIXED HORIZON, NOT THE REALISED HOLD.
                        # Second defect in this harness, found before reporting: the window was
                        # [signal bar, THE TRADE'S OWN EXIT BAR].  That upper bound is the future -
                        # winners ran long so their controls were drawn deep into an extended move
                        # and bought the top, losers stopped out fast so their controls had 1-2 bars
                        # to pick from.  The control was conditioned on the outcome it was meant to
                        # be compared against, and it printed a uniformly negative control and 13
                        # OPENs.  A horizon fixed in advance cannot know any of that.
                        for H in HORIZONS:
                            hi_b = min(e + H, n - 2)
                            if hi_b < e:
                                continue
                            for j in rng.integers(e, hi_b + 1, DRAWS):
                                e2 = int(j)
                                en2 = o[e2]
                                # THE CONTROL CARRIES THE SIGNAL TRADE'S OWN RISK, IN POINTS.
                                # First version of this harness gave the control its own structure
                                # stop (the trail as of its entry bar).  That is NOT a timing
                                # control: a control entering mid-move inherits a trail that has
                                # already ratcheted up to just under price, so its R is far smaller
                                # than the signal arm's, it stops out at -1R almost every time, and
                                # the delta measures STOP WIDTH rather than ENTRY TIMING.  It
                                # produced a control mean of -0.27..-0.50 R in all 72 cells and
                                # 13 false OPENs.  Matching R by construction is also the literal
                                # reading of section 7's "run the IDENTICAL stop".
                                s2 = en2 - risk
                                _, xp2, _ = run_trade(o, h, lo, c, e2, s2, L1, n, xm)
                                rR[H].append((xp2 - en2) / risk)
                        t = xb + 1                                # one position at a time
                    cnt = len(sR)
                    a_yr = cnt / years if years else 0.0
                    if cnt < 2 or len(rR[H_JUDGE]) < 2:
                        report.append({"cell": name, "trades": cnt, "verdict": "NO TRADES"})
                        print(format(name, "<32") + format(format(cnt, ","), ">6")
                              + format(format(a_yr, ".1f"), ">6") + format("-", ">8") * 9
                              + format("NO TRADES", ">18"))
                        continue
                    s_m = float(np.mean(sR)); s_sd = float(np.std(sR, ddof=1))
                    r_by_h = {H: (float(np.mean(v)) if len(v) > 1 else None) for H, v in rR.items()}
                    r_m = r_by_h[H_JUDGE]
                    rk = float(np.mean(risks))
                    delta = s_m - r_m
                    m2 = mde_two(s_sd, cnt)
                    net = float(np.sum(pnl))
                    roc_yr = net / years / NOMINAL_ACCOUNT * 100.0
                    ev_book = s_m - COST_BOOK / rk
                    ev_stress = s_m - COST_STRESS / rk
                    fb = np.linspace(0, cnt, N_FOLDS + 1).astype(int)
                    fsum = [float(np.sum(pnl[fb[i]:fb[i + 1]])) for i in range(N_FOLDS)]
                    fpos = sum(1 for v in fsum if v > 0)
                    share = (max(fsum) / net) if net > 0 else None
                    if m2 is None or delta <= m2:
                        v = "TIMING IS NOTHING"
                    elif a_yr < TRADES_A_YEAR_FLOOR:
                        v = "THIN"
                    elif ev_book <= 0:
                        v = "UNDER COST"
                    else:
                        v = "OPEN"
                    report.append({
                        "cell": name, "tf": tf, "k": k, "trend": tr, "stop": st, "exit": xm,
                        "trades": cnt, "a_year": round(a_yr, 1), "control_draws": len(rR[H_JUDGE]),
                        "mean_risk_pt": round(rk, 2), "mean_hold_bars": round(float(np.mean(holds)), 1),
                        "ev_R_gross": round(s_m, 4), "sd_R": round(s_sd, 4),
                        "ev_R_book": round(ev_book, 4), "ev_R_stress": round(ev_stress, 4),
                        "cost_R_house": round(COST_HOUSE / rk, 5), "cost_R_book": round(COST_BOOK / rk, 5),
                        "random_R": round(r_m, 4), "delta_R": round(delta, 4),
                        "random_R_by_horizon": {str(H): (None if v is None else round(v, 4))
                                                for H, v in r_by_h.items()},
                        "delta_R_by_horizon": {str(H): (None if v is None else round(s_m - v, 4))
                                               for H, v in r_by_h.items()},
                        "mde2_R": None if m2 is None else round(m2, 4),
                        "net_usd_book": round(net, 0), "roc_per_year_pct": round(roc_yr, 2),
                        "folds_positive": fpos,
                        "max_fold_share": None if share is None else round(share, 3),
                        "verdict": v})
                    print(format(name, "<32") + format(format(cnt, ","), ">6")
                          + format(format(a_yr, ".1f"), ">6") + format(format(rk, ".1f"), ">8")
                          + format(format(float(np.mean(holds)), ".1f"), ">7")
                          + format(format(ev_book, ".4f"), ">8") + format(format(r_m, ".4f"), ">8")
                          + format(format(delta, ".4f"), ">8")
                          + format("-" if m2 is None else format(m2, ".4f"), ">8")
                          + format(format(roc_yr, ".2f"), ">8")
                          + format("%d/8" % fpos, ">7") + format(v, ">18"))

    vs = [r["verdict"] for r in report]
    print("\nVERDICT COUNTS: %s" % json.dumps({x: vs.count(x) for x in sorted(set(vs))}))
    R = [r for r in report if "delta_R" in r]
    if R:
        print("cells where the SIGNAL IS WORSE THAN A LATER RANDOM ENTRY: %d of %d"
              % (sum(1 for r in R if r["delta_R"] < 0), len(R)))
        b = max(R, key=lambda r: r["delta_R"])
        print("best delta: %s  %.4f R vs MDE2 %.4f (signal %.4f, random %.4f)"
              % (b["cell"], b["delta_R"], b["mde2_R"] or 0, b["ev_R_gross"], b["random_R"]))
        e = max(R, key=lambda r: r["ev_R_book"])
        print("best EV R after the 0.783 book cost: %s  %.4f R, ROC/yr %.2f%%, %d/8 folds, %s a year"
              % (e["cell"], e["ev_R_book"], e["roc_per_year_pct"], e["folds_positive"], e["a_year"]))
        print("control mean R across cells: %.4f .. %.4f  (a CONSTANT here would mean a broken control)"
              % (min(r["random_R"] for r in R), max(r["random_R"] for r in R)))
        print("\nSENSITIVITY to the control horizon - if the verdict moves with H, the horizon is")
        print("  doing the work and no verdict from this gate can be trusted:")
        for H in HORIZONS:
            d = [r["delta_R_by_horizon"][str(H)] for r in R if r["delta_R_by_horizon"].get(str(H)) is not None]
            beat = sum(1 for r in R
                       if r["delta_R_by_horizon"].get(str(H)) is not None and r["mde2_R"] is not None
                       and r["delta_R_by_horizon"][str(H)] > r["mde2_R"])
            tag = "  <-- the judged horizon" if H == H_JUDGE else ""
            print("  H=%-3d control mean %+.4f R, delta %+.4f R, %d of %d cells beat their MDE2%s"
                  % (H, float(np.mean([r["random_R_by_horizon"][str(H)] for r in R
                                       if r["random_R_by_horizon"].get(str(H)) is not None])),
                     float(np.mean(d)), beat, len(R), tag))
    if "OPEN" not in vs:
        print("NO CELL IS OPEN - THE ROUND CLOSES AT DRAFT, no trial budget spent.")
    p = os.path.join(OUT, "gate.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"prereg_sha": PREREG_SHA, "master": MASTER, "years": round(years, 2),
                   "stretch": [str(tsa[0].date()), str(tsa[-1].date())], "seed": SEED,
                   "draws": DRAWS, "cost_pts": {"house": COST_HOUSE, "book": COST_BOOK,
                                                "stress": COST_STRESS},
                   "yardstick": "owner w121: EV R + ROC/yr + book lift; ROC@30k and DD NOT judged",
                   "rows": report}, f, indent=1)
    print("wrote " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
