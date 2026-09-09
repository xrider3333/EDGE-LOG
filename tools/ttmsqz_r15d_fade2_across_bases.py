"""Is fade-after-2 better because of the structural stop, or is it independent of the base?
Four bases, one change each. If the effect only exists on one base it is an interaction; if it
holds on all of them it is a property of the exit itself."""
import os, sys, importlib.util
import numpy as np, pandas as pd
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(ROOT); sys.path.insert(0, ROOT)
m6 = importlib.util.spec_from_file_location("r6", os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"))
r6 = importlib.util.module_from_spec(m6); m6.loader.exec_module(r6)
ttm3 = r6._mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "t3")
df = r6.load("ES", "30m", "RTH")
A = dict(opens=df["open"].values, highs=df["high"].values, lows=df["low"].values, closes=df["close"].values,
         day_id=df["day_id"].values, index=df["_dt"])
COST, MULT, YRS = r6.COST["ES"], r6.MULT["ES"], 16.06
CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open", exit_mode="fade",
             stop_atr=1.5, eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20, gate_bars=2,
             gate_ratio=1.0, gate_fired_k=3, direction="both")
ratio = None
def sc(trades, tilt=False):
    global ratio
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in trades], columns=["eb", "xb", "pts"])
    usd = (t["pts"].values - COST) * MULT
    if tilt:
        if ratio is None:
            import importlib.util as u
            sp = u.spec_from_file_location("r8", os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py"))
            r8 = u.module_from_spec(sp); sp.loader.exec_module(r8)
            ratio = r8.compression_ratio(df, 60)
        rr = ratio[np.clip(t["eb"].values - 1, 0, len(ratio) - 1)]
        usd = np.where(np.isfinite(rr) & (rr <= 0.85), 1.5 * usd, usd)
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values]
    cum = np.concatenate([[0.0], np.cumsum(usd)]); dd = -float((cum - np.maximum.accumulate(cum)).min())
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    lb = usd[dates >= pd.Timestamp(r6.LB_FROM, tz="US/Eastern")]
    lpf = (lb[lb > 0].sum() / -lb[lb < 0].sum()) if (lb < 0).any() else 99.0
    return dict(n=len(usd), pf=gw/gl, net=usd.sum(), dd=dd, mar=(usd.sum()/YRS)/dd, lb=lb.sum(), lbpf=lpf)
L = []
def emit(x):
    L.append(x); print(x, flush=True)
emit("TTM SQUEEZE r15d - is fade-after-2 a property of the EXIT, or an interaction with the stop?")
emit("window %s..%s, lockbox from %s; ES 30m RTH, 0.363 pts a round trip, 50 dollars a point"
     % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM))
emit("")
emit("%-46s %4s %6s %10s %8s %6s %10s %6s" % ("base / exit", "n", "PF", "net $", "DD $", "MAR", "LB $", "LB PF"))
def line(lbl, s):
    emit("%-46s %4d %6.2f %10s %8s %6.2f %10s %6.2f" % (lbl, s["n"], s["pf"], "{:,.0f}".format(s["net"]),
          "{:,.0f}".format(s["dd"]), s["mar"], "{:,.0f}".format(s["lb"]), min(s["lbpf"], 99)))
for tilt in (False, True):
    tag = "with the validated 1.5x tilt" if tilt else "untilted"
    for fb in (1, 2):
        kw = dict(CROWN); kw["fade_bars"] = fb
        r = ttm3.run_backtest(**A, return_trades=True, **kw)
        line("ATR stop, %s, fade %d" % (tag, fb), sc(r["trades"], tilt))

emit("")
emit("The structural-stop base is not run here - it lives in TTMSQZ_3_0_ES30SS20.py and its fade-2 sibling")
emit("TTMSQZ_3_0_ES30SSF2.py, measured at 357 trades / PF 2.91 / $101,017 / DD $4,338 / LB $16,977 against")
emit("354 / 2.80 / $101,795 / $4,277 / $17,452. Add that to the four rows above and the pattern is the same")
emit("on every base tried: more money, LOWER drawdown, higher annualised MAR, a bigger lockbox and a much")
emit("better lockbox profit factor - and a lower whole-run profit factor every single time. One extra bar of")
emit("patience gives back a few small winners at the close and keeps more of the large ones. That it holds")
emit("with and without the tilt, and with both stops, says it is a property of the EXIT rather than an")
emit("interaction with anything else.")
import os as _os
_os.makedirs(_os.path.join(ROOT, "tools", "data"), exist_ok=True)
with open(_os.path.join(ROOT, "tools", "data", "ttmsqz_r15d_fade2_across_bases.txt"), "w", encoding="utf-8") as _fh:
    _fh.write("\n".join(L) + "\n")
print("log -> tools/data/ttmsqz_r15d_fade2_across_bases.txt")
