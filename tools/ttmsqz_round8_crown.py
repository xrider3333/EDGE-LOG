"""TTM Squeeze round 8 - IMPROVING THE CROWN (run 299 = TTMSQZ_3_0_ES30N, ES 30m, hourly-verified).

Owner 2026-09-08: "keep improving our best ttm model." The crown's real use is as a BOOK LEG (round 7,
BOOK run 336 vs 337: +16% annualised MAR at identical drawdown), so every variant is judged TWICE:
  ALONE  - on its own tape, against run 299 itself (full window + lockbox), and
  STACKED - as 3 ES contracts on the house baseline (ORB 234 + ENGU-Q 309, one NQ each), against
            the CURRENT book leg (baseline + 3 ES of run 299), which is the thing to beat.

BAR, WRITTEN DOWN BEFORE THE RUN (a variant is a lead only if all three hold):
  1. alone: lockbox net > 0 and profit factor >= run 299's own;
  2. stacked: annualised MAR at least 5% above the run-299 stack at a whole-run drawdown within 5%;
  3. stacked lockbox net >= the run-299 stack's lockbox net.
Anything short is recorded and NOT crowned. A lead goes to a fenced Auto-Validate (4-knob
neighbourhood, the variant frozen in the wrapper) before anything else happens.

Variants are ONE change each on the 299 config (frozen: length 20, bb 2.0, kc 1.5, min squeeze 1,
entry next open, fade exit 1 bar, stop 1.5 ATR, eod cutoff 1, hourly sq_on gate, length 20):
  engine knobs   - fade 2 / fade 3 / ride exit / min squeeze 2, 3 / range-break entry / long only /
                   short only / 2-hour verification (120m)
  post-hoc reads - hourly AND 2-hour both coiled (filter); 1.5x size when the hourly squeeze is DEEP
                   (ratio <= 0.85) - a tilt, every trade kept
  new tape       - QQQ 30m (resampled from the QQQ 5m master; 100,000 dollars a trade, 20 a round
                   trip) at the exact 299 config: a stocks-account leg candidate
Every number is a SCAN of one run per cell, pinned window 2010-06-07..2026-06-30, lockbox from
2025-07-01 - the round-6/7 window. Log: tools/data/ttmsqz_round8_crown.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
r6 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r6", os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py")))
r6.__spec__.loader.exec_module(r6)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest as engine_run

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_round8_crown.txt")
BASE_CACHE = os.path.join(ROOT, "tools", "data", "ttmsqz_round8_base.npz")
TTM_WEIGHT = 3.0
ETF_NOTIONAL, ETF_RT = 100_000.0, 20.0

CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open", exit_mode="fade",
             fade_bars=1, stop_atr=1.5, eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20,
             gate_bars=0, gate_ratio=1.0, gate_fired_k=3, direction="both")
VARIANTS = [
    ("fade exit after 2 bars", dict(fade_bars=2)),
    ("fade exit after 3 bars", dict(fade_bars=3)),
    ("ride exit (stop or close only)", dict(exit_mode="ride")),
    ("min 2-bar squeeze", dict(min_sq_bars=2)),
    ("min 3-bar squeeze", dict(min_sq_bars=3)),
    ("range-break entry", dict(entry_fill="range_break")),
    ("long only", dict(direction="long")),
    ("short only", dict(direction="short")),
    ("2-hour verification", dict(gate_tf_min=120)),
]

ttm3 = r6._mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "ttm3")


def _lines_to(lines, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _daily(usd, dates):
    s = pd.Series(usd, index=pd.to_datetime(list(dates))).groupby(level=0).sum()
    return s


def book_score(daily):
    """daily: Series of dollars per calendar day (all legs summed)."""
    cum = daily.cumsum().values
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    yrs = max((daily.index[-1] - daily.index[0]).days / 365.25, 1e-9)
    net = float(daily.sum())
    lb = daily[daily.index >= pd.Timestamp(LB_FROM)]
    lcum = lb.cumsum().values
    ldd = -float((lcum - np.maximum.accumulate(lcum)).min()) if len(lb) else float("nan")
    ypos = int((daily.groupby(daily.index.year).sum() > 0).sum())
    ny = daily.index.year.nunique()
    return dict(net=net, dd=dd, mar=(net / yrs) / dd if dd > 0 else float("nan"),
                lb=float(lb.sum()), lbdd=ldd, ypos=ypos, ny=ny)


def baseline_daily():
    """ORB 234 + ENGU-Q 309, one NQ contract each, cost-inclusive dollars per day (cached)."""
    if os.path.exists(BASE_CACHE):
        z = np.load(BASE_CACHE, allow_pickle=True)
        return pd.Series(z["usd"], index=pd.to_datetime(z["dates"]))
    from api import paper as P
    legs = [("ORB_3_6_C2.py", "NQ", "5m", "rth", P.ORB_234),
            ("ENGUQ_1M_ETH_ER_1_0.py", "NQ", "1m", "eth", P.ENGUQ_309)]
    parts = []
    for fn, inst, tf, sess, params in legs:
        t0 = time.time()
        m = find_master(inst, tf, sess)
        arrays = load_master_arrays(m, date_from=DATE_FROM, date_to=DATE_TO)
        res = engine_run(fn, arrays=arrays, params=dict(params), cost_pts=COST[inst], return_trades=True)
        tr = [(int(t[0]), int(t[1]), float(t[2])) for t in (res or {}).get("trades") or []]
        usd = np.array([t[2] for t in tr]) * MULT[inst]
        dates = pd.DatetimeIndex(arrays["index"])[[t[1] for t in tr]].tz_localize(None).normalize()
        parts.append(pd.Series(usd, index=dates).groupby(level=0).sum())
        print("  baseline %s: %d trades, $%s, %.0fs" % (fn, len(tr), "{:,.0f}".format(usd.sum()), time.time() - t0),
              flush=True)
    daily = pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).sort_index()
    np.savez(BASE_CACHE, usd=daily.values, dates=daily.index.values.astype("datetime64[ns]"))
    return daily


def run_ttm(df, kw, inst="ES"):
    r = ttm3.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                          day_id=df["day_id"].values, index=df["_dt"], return_trades=True, **kw)
    if not r or not r.get("trades"):
        return None
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2]), int(x[3]), float(x[4])) for x in r["trades"]],
                     columns=["eb", "xb", "pnl", "side", "epx"])
    t["usd"] = (t["pnl"] - COST[inst]) * MULT[inst]
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()
    return t


def compression_ratio(df, gate_tf_min=60, length=20, bb_mult=2.0, kc_mult=1.5):
    """Bollinger half-width over Keltner half-width of the gate frame, mapped causally onto the
    base bars (last COMPLETE group) - the same construction as r6.hourly_compression, as a dial."""
    first = df.groupby("day_id")["_dt"].transform("first")
    off = ((df["_dt"] - first).dt.total_seconds() // 60).astype("int64")
    key = df["day_id"].astype(str) + "_" + (off // int(gate_tf_min)).astype(str).str.zfill(4)
    g = df.groupby(key, sort=True)
    hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
    end = g["_end"].last().values
    order = np.argsort(end)
    hh, ll, cc, end = hh[order], ll[order], cc[order], end[order]
    s = pd.Series(cc)
    dev = s.rolling(length).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(length).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((bb_mult * dev) / (kc_mult * atr)).to_numpy()
    warm = length * 2 + 5
    j = np.searchsorted(end, df["_end"].values, side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    return np.where(ok, ratio[jj], np.nan)


def alone_score(t):
    usd = t["usd"].values
    s = r6.score(usd, t["date"].dt.date.values)
    lb = t[t["date"] >= pd.Timestamp(LB_FROM)]
    sl = r6.score(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
    yrs = max((t["date"].max() - t["date"].min()).days / 365.25, 1e-9)
    s["mar"] = (s["net"] / yrs) / s["dd"] if s["dd"] > 0 else float("nan")
    s["lb"] = sl["net"] if sl else 0.0
    s["lbpf"] = sl["pf"] if sl else float("nan")
    s["lbdd"] = sl["dd"] if sl else float("nan")
    s["lbn"] = sl["n"] if sl else 0
    return s


def qqq_30m():
    m = find_master("QQQ", "5m", "rth")
    a = load_master_arrays(m, date_from=DATE_FROM, date_to=DATE_TO)
    df = pd.DataFrame(dict(open=a["open"], high=a["high"], low=a["low"], close=a["close"],
                           _dt=pd.DatetimeIndex(a["index"])))
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    first = df.groupby("day_id")["_dt"].transform("first")
    off = ((df["_dt"] - first).dt.total_seconds() // 60).astype("int64")
    key = df["day_id"] * 1000 + off // 30
    g = df.groupby(key, sort=True)
    out = pd.DataFrame(dict(open=g["open"].first(), high=g["high"].max(), low=g["low"].min(),
                            close=g["close"].last(), _dt=g["_dt"].first())).reset_index(drop=True)
    out["day_id"] = pd.factorize(out["_dt"].dt.date)[0]
    out["_end"] = out["_dt"] + pd.Timedelta(minutes=30)
    return out


def main():
    L = []
    L.append("TTM SQUEEZE ROUND 8 - improving the crown (run 299, ES 30m hourly-verified)   %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("window %s..%s, lockbox from %s; ES cost %.3f pts, mult %d; book = ORB 234 + ENGU-Q 309 (1 NQ each) + %d ES of the TTM cell"
             % (DATE_FROM, DATE_TO, LB_FROM, COST["ES"], MULT["ES"], TTM_WEIGHT))
    L.append("BAR (pre-registered): alone LB>0 and PF>=crown; stacked ann. MAR >= crown-stack x1.05 at DD within 5%; stacked LB >= crown-stack LB")
    print("\n".join(L), flush=True)

    print("baseline legs...", flush=True)
    base = baseline_daily()
    sb = book_score(base)
    df = r6.load("ES", "30m", "RTH")
    crown = run_ttm(df, CROWN)
    sc = alone_score(crown)
    crown_stack = base.add(_daily(crown["usd"].values * TTM_WEIGHT, crown["date"]), fill_value=0.0).sort_index()
    scs = book_score(crown_stack)

    H = "  %-38s %5s %6s %10s %8s %6s %9s %6s %8s | %11s %8s %6s %10s %8s %5s  %s"
    L.append("")
    L.append(H % ("cell", "n", "PF", "net $", "DD $", "MAR", "LB $", "LB PF", "LB DD $",
                  "BOOK net $", "BOOK DD", "MAR", "BOOK LB $", "LB DD", "yrs+", "verdict"))

    def _emit(name, s, sk, verdict):
        L.append(H % (name, s["n"], "%.2f" % min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
                      "%.2f" % s["mar"], "{:,.0f}".format(s["lb"]), "%.2f" % min(s["lbpf"], 99) if s["lbpf"] == s["lbpf"] else "n/a",
                      "{:,.0f}".format(s["lbdd"]) if s["lbdd"] == s["lbdd"] else "n/a",
                      "{:,.0f}".format(sk["net"]), "{:,.0f}".format(sk["dd"]), "%.2f" % sk["mar"],
                      "{:,.0f}".format(sk["lb"]), "{:,.0f}".format(sk["lbdd"]), "%d/%d" % (sk["ypos"], sk["ny"]), verdict))
        print(L[-1], flush=True)

    L.append(H % ("BASELINE book alone (no TTM)", 0, 0, "0", "0", "0.00", "0", "n/a", "n/a",
                  "{:,.0f}".format(sb["net"]), "{:,.0f}".format(sb["dd"]), "%.2f" % sb["mar"],
                  "{:,.0f}".format(sb["lb"]), "{:,.0f}".format(sb["lbdd"]), "%d/%d" % (sb["ypos"], sb["ny"]), "reference"))
    _emit("CROWN run 299 (the thing to beat)", sc, scs, "crown")

    def judge(s, sk):
        c1 = s["lb"] > 0 and s["pf"] >= sc["pf"]
        c2 = sk["mar"] >= scs["mar"] * 1.05 and sk["dd"] <= scs["dd"] * 1.05
        c3 = sk["lb"] >= scs["lb"]
        if c1 and c2 and c3:
            return "LEAD - all three clauses"
        why = []
        if not c1: why.append("alone")
        if not c2: why.append("book MAR/DD")
        if not c3: why.append("book LB")
        return "no (%s)" % ", ".join(why)

    results = []
    for name, over in VARIANTS:
        kw = dict(CROWN); kw.update(over)
        t = run_ttm(df, kw)
        if t is None:
            L.append("  %-38s  no trades" % name); print(L[-1], flush=True); continue
        s = alone_score(t)
        sk = book_score(base.add(_daily(t["usd"].values * TTM_WEIGHT, t["date"]), fill_value=0.0).sort_index())
        v = judge(s, sk); _emit(name, s, sk, v); results.append((name, s, sk, v))

    # post-hoc reads on the crown's own trades
    r120 = r6.hourly_compression(df, gate_tf_min=120)
    on120 = r120[np.clip(crown["eb"].values - 1, 0, len(r120) - 1)]
    t = crown[on120].reset_index(drop=True)
    if len(t):
        s = alone_score(t)
        sk = book_score(base.add(_daily(t["usd"].values * TTM_WEIGHT, t["date"]), fill_value=0.0).sort_index())
        v = judge(s, sk); _emit("hourly AND 2-hour coiled (filter)", s, sk, v); results.append(("h+2h filter", s, sk, v))
    ratio = compression_ratio(df, 60)
    rr = ratio[np.clip(crown["eb"].values - 1, 0, len(ratio) - 1)]
    for thr in (0.85, 0.7):
        deep = np.isfinite(rr) & (rr <= thr)
        # 1.5x on a cost-inclusive dollar trade = 1.5 x (pnl - cost): the extra half contract pays its own cost
        t = crown.copy()
        t["usd"] = np.where(deep, 1.5 * crown["usd"].values, crown["usd"].values)
        s = alone_score(t)
        sk = book_score(base.add(_daily(t["usd"].values * TTM_WEIGHT, t["date"]), fill_value=0.0).sort_index())
        v = judge(s, sk)
        _emit("1.5x when hourly ratio <= %.2f (%d of %d)" % (thr, int(deep.sum()), len(deep)), s, sk, v)
        results.append(("deep tilt %.2f" % thr, s, sk, v))

    # QQQ 30m at the crown config - a stocks-account leg candidate (alone only; different account)
    L.append("")
    try:
        q = qqq_30m()
        r = ttm3.run_backtest(q["open"].values, q["high"].values, q["low"].values, q["close"].values,
                              day_id=q["day_id"].values, index=q["_dt"], return_trades=True, **CROWN)
        if r and r.get("trades"):
            t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2]), float(x[4])) for x in r["trades"]],
                             columns=["eb", "xb", "pnl", "epx"])
            sh = ETF_NOTIONAL / t["epx"]
            t["usd"] = t["pnl"] * sh - ETF_RT
            t["date"] = pd.DatetimeIndex(q["_dt"])[t["xb"].values].tz_localize(None).normalize()
            s = alone_score(t)
            L.append("  QQQ 30m at the 299 config (%s..%s, $%s a trade, $%d RT): n %d PF %.2f net $%s DD $%s MAR %.2f | LB $%s PF %s on %d"
                     % (q["_dt"].iloc[0].date(), q["_dt"].iloc[-1].date(), "{:,.0f}".format(ETF_NOTIONAL), ETF_RT, s["n"], s["pf"],
                        "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]), s["mar"], "{:,.0f}".format(s["lb"]),
                        "%.2f" % s["lbpf"] if s["lbpf"] == s["lbpf"] else "n/a", s["lbn"]))
        else:
            L.append("  QQQ 30m at the 299 config: no trades - the QQQ 5m master holds only 2026-06-08..06-30 (3 weeks), NO TAPE to test on; not a finding")
    except Exception as e:
        L.append("  QQQ 30m: could not run (%s: %s)" % (type(e).__name__, str(e)[:80]))
    print(L[-1], flush=True)

    leads = [r for r in results if r[3].startswith("LEAD")]
    L.append("")
    L.append("LEADS: %d of %d cells clear all three clauses%s" % (
        len(leads), len(results), (": " + ", ".join(r[0] for r in leads)) if leads else " - the crown stands"))
    print(L[-1], flush=True)
    _lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
