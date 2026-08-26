"""
TTM SQUEEZE ROUND 4 — higher-timeframe VERIFICATION of shorter-timeframe entries.

Owner directive 2026-08-23: "keep going and find a version of this that works. use higher
time frames for verification on the shorter time frames." This is Carter's own stacked-
timeframe method, done properly (round 2's daily_sq gate was a crude on/off version).

MECHANICS
  Entries happen on a BASE timeframe (5m / 15m / 30m) exactly as in round 2:
    - carter entry: squeeze fires on the base timeframe, market at next open, fade exit
    - break entry:  squeeze fires, stop order at the squeeze range edge, ride exit
      (the round-2 NQ 60m pocket shape)
  A HIGHER timeframe (30m / 60m / 120m / daily) must CONFIRM the trade at decision time:
    sign     the higher timeframe momentum histogram agrees with the trade direction
    rising   sign agrees AND the histogram strengthened on its last completed bar
    sq_on    the higher timeframe squeeze is currently ON (compression regime)
    fired    the higher timeframe itself fired in the trade direction within its last
             K completed bars (trade the shorter-timeframe continuation of a big release)
    stack2   60m AND 120m momentum signs both agree

CAUSALITY (the thing that must survive audit)
  Higher-timeframe bars are built session-anchored (09:30 ET) from the base frame. A
  higher-timeframe bar is usable on base bar u only if its END time <= base bar u's END
  time (both ends fall on the same completed price history, so a 60m bar ending 10:30
  is legal on the 15m bar ending 10:30). The mapping is precomputed with searchsorted on
  END times; a bar's own values never include price after the base bar's close. Entries
  fill on bar u+1 (open or resting stop), never on the decision bar.

Window PINNED 2010-06-07..2026-06-30, LB = last 12 months, house costs, one contract,
flat at every session close.

Usage:  python tools/ttmsqz_round4_mtf.py [smoke]
Output: tools/data/ttmsqz_round4_mtf.txt
"""
import os, sys, importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP = os.path.join(ROOT, "augur_uploads")
if not os.path.exists(os.path.join(UP, "NOADJ_NQ_5m_RTH.csv")):
    UP = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads"

DATE_FROM, LB_FROM, DATE_TO = "2010-06-07", "2025-07-01", "2026-06-30"
COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

_sp = importlib.util.spec_from_file_location("ttm", os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"))
ttm = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(ttm)

BASE_MIN = {"5m": 5, "15m": 15, "30m": 30}


def load_base(inst, tf):
    """Base frame at tf, built from the finest master that carries it. Adds _end (bar
    END timestamp) — the moment the bar's close becomes knowable."""
    src_tf = tf if tf in ("1m", "5m", "15m") else "5m"
    df = pd.read_csv(os.path.join(UP, f"NOADJ_{inst}_{src_tf}_RTH.csv"))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(DATE_FROM).date()) & (df["_dt"].dt.date <= pd.Timestamp(DATE_TO).date())]
    src_m = int(src_tf[:-1])
    if tf != src_tf:
        m = int(tf[:-1])
        mins = df["_dt"].dt.hour * 60 + df["_dt"].dt.minute - 570
        key = df["_dt"].dt.date.astype(str) + "_" + (mins // m).astype(str).str.zfill(3)
        g = df.groupby(key, sort=True)
        df = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                           "close": g["close"].last(), "_dt": g["_dt"].first(),
                           "_end": g["_dt"].last() + pd.Timedelta(minutes=src_m)}).reset_index(drop=True)
    else:
        df = df[["open", "high", "low", "close", "_dt"]].copy()
        df["_end"] = df["_dt"] + pd.Timedelta(minutes=src_m)
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    return df.reset_index(drop=True)


def build_htf(base, htf, length=20, bb_mult=2.0, kc_mult=1.5):
    """Higher-timeframe squeeze state, mapped onto the base frame CAUSALLY.

    Returns dict of base-length arrays: mom (last completed HTF bar's momentum),
    mom_prev (the bar before it), sq_on, fired_dir (+1/-1/0: direction of the most
    recent HTF fire and how many completed HTF bars ago it happened via fired_age).
    Base bars before the first completed, warmed-up HTF bar get NaN/0 and never trade."""
    if htf == "D":
        g = base.groupby("day_id", sort=True)
        hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
        end = g["_end"].last().values
    else:
        m = int(htf[:-1])
        mins = base["_dt"].dt.hour * 60 + base["_dt"].dt.minute - 570
        key = base["_dt"].dt.date.astype(str) + "_" + (mins // m).astype(str).str.zfill(3)
        g = base.groupby(key, sort=True)
        hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
        end = g["_end"].last().values
    order = np.argsort(end)
    hh, ll, cc, end = hh[order], ll[order], cc[order], end[order]
    sq, mom, _ = ttm.squeeze_indicators(hh, ll, cc, length, bb_mult, kc_mult)
    nh = len(cc)
    run = np.zeros(nh, int)
    for i in range(1, nh):
        run[i] = run[i - 1] + 1 if sq[i] else 0
    fire = np.zeros(nh, bool)
    fire[1:] = (~sq[1:]) & (run[:-1] >= 1)
    warm = length * 2 + 5
    fire[:warm] = False
    fire_dir = np.where(fire, np.sign(np.nan_to_num(mom)), 0.0)
    last_fire_idx = np.full(nh, -1)
    last = -1
    for i in range(nh):
        if fire[i] and fire_dir[i] != 0:
            last = i
        last_fire_idx[i] = last

    # causal map: for base bar u (end e_u), j = latest HTF bar with end <= e_u
    base_end = base["_end"].values
    j = np.searchsorted(end, base_end, side="right") - 1
    valid = j >= warm
    jj = np.clip(j, 0, nh - 1)
    out = {
        "mom": np.where(valid, mom[jj], np.nan),
        "mom_prev": np.where(valid & (jj >= 1), mom[np.clip(jj - 1, 0, nh - 1)], np.nan),
        "sq_on": np.where(valid, sq[jj], False).astype(bool),
        "fire_dir": np.where(valid & (last_fire_idx[jj] >= 0), fire_dir[np.clip(last_fire_idx[jj], 0, nh - 1)], 0.0),
        "fire_age": np.where(valid & (last_fire_idx[jj] >= 0), jj - last_fire_idx[jj], 10 ** 9),
    }
    return out


def gate_mask(htfs, mode, K=3):
    """(gate_long, gate_short) boolean arrays from prepared HTF dict(s)."""
    if mode == "none":
        n = len(htfs[0]["mom"])
        return np.ones(n, bool), np.ones(n, bool)
    a = htfs[0]
    if mode == "sign":
        return (a["mom"] > 0), (a["mom"] < 0)
    if mode == "rising":
        return (a["mom"] > 0) & (a["mom"] >= a["mom_prev"]), (a["mom"] < 0) & (a["mom"] <= a["mom_prev"])
    if mode == "sq_on":
        return a["sq_on"].copy(), a["sq_on"].copy()
    if mode == "fired":
        ok = a["fire_age"] <= K
        return ok & (a["fire_dir"] > 0), ok & (a["fire_dir"] < 0)
    if mode == "stack2":
        b = htfs[1]
        return (a["mom"] > 0) & (b["mom"] > 0), (a["mom"] < 0) & (b["mom"] < 0)
    raise ValueError(mode)


def run_gated(df, gate_long, gate_short, *, length=20, bb_mult=2.0, kc_mult=1.5, min_sq=1,
              entry_fill="open", exit_mode="fade", fade_bars=1, stop_atr=2.0, eod_cutoff=3):
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c); did = df["day_id"].values
    sq_on, mom, atr = ttm.squeeze_indicators(h, l, c, length, bb_mult, kc_mult)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= min_sq)
    warm = length * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]; a0 = max(0, i - k)
        rng_hi[i] = h[a0:i].max(); rng_lo[i] = l[a0:i].min()
    last_bar = np.empty(n, int)
    a0 = 0
    while a0 < n:
        b0 = a0
        while b0 < n and did[b0] == did[a0]:
            b0 += 1
        last_bar[a0:b0] = b0 - 1; a0 = b0

    pos = 0; ep = 0.0; eb = -1; stop_px = None
    pending = None
    fade_cnt = 0
    log = []

    def book(i, px, side, ep_, eb_):
        log.append((eb_, i, (px - ep_) if side > 0 else (ep_ - px), side, ep_, px))

    for u in range(warm, n):
        eod = u == last_bar[u]
        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    book(u, o[u], pos, ep, eb); pos = 0; stop_px = None
                pending = None
            elif kind == "mkt":
                if pos == 0:
                    side = pending[1]
                    pos = side; ep = o[u]; eb = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = ep - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        book(u, stop_px, pos, ep, eb); pos = 0; stop_px = None
                pending = None
            else:
                _, side, lvl, expiry = pending
                fill = None
                if side > 0:
                    if o[u] >= lvl: fill = o[u]
                    elif h[u] >= lvl: fill = lvl
                else:
                    if o[u] <= lvl: fill = o[u]
                    elif l[u] <= lvl: fill = lvl
                if fill is not None and pos == 0:
                    pos = side; ep = fill; eb = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = ep - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        book(u, stop_px, pos, ep, eb); pos = 0; stop_px = None
                    pending = None
                elif u >= expiry or eod:
                    pending = None
        if pos != 0 and u > eb and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                book(u, px, pos, ep, eb); pos = 0; stop_px = None
        if eod:
            if pos != 0:
                book(u, c[u], pos, ep, eb); pos = 0; stop_px = None
            pending = None
            continue
        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue
        if pos != 0 and exit_mode == "fade":
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
                continue
        if pos == 0 and pending is None and fire[u] and m != 0:
            side = 1 if m > 0 else -1
            if side > 0 and not gate_long[u]:
                continue
            if side < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            if entry_fill == "open":
                pending = ("mkt", side)
            else:
                if not np.isfinite(rng_hi[u]):
                    continue
                lvl = rng_hi[u] if side > 0 else rng_lo[u]
                pending = ("stop", side, lvl, u + 4)
    return log


def stats(log, df, inst):
    if not log:
        return None
    mult, cost = MULT[inst], COST[inst]
    t = pd.DataFrame(log, columns=["eb", "xb", "pnl", "side", "ep", "xp"])
    t["usd"] = (t["pnl"] - cost) * mult
    dts = pd.DatetimeIndex(df["_dt"])
    t["date"] = dts[t["xb"].values].date; t["year"] = dts[t["xb"].values].year
    def block(x):
        if not len(x): return dict(net=0, pf=0, dd=0, n=0)
        v = x["usd"].values; cum = np.concatenate([[0.0], np.cumsum(v)])
        dd = -float((cum - np.maximum.accumulate(cum)).min())
        gw = v[v > 0].sum(); gl = -v[v < 0].sum()
        return dict(net=float(v.sum()), pf=float(gw / gl) if gl > 0 else 99.0, dd=dd, n=len(v))
    lb = block(t[t["date"] >= pd.Timestamp(LB_FROM).date()])
    is_ = block(t[t["date"] < pd.Timestamp(LB_FROM).date()])
    yr = t.groupby("year")["usd"].sum()
    f = block(t); f.update(yplus=int((yr > 0).sum()), yminus=int((yr <= 0).sum()),
                           wr=float(100 * (t["usd"] > 0).mean()))
    return dict(full=f, IS=is_, LB=lb)


ENTRY_STYLES = [
    ("carter", dict(entry_fill="open", exit_mode="fade")),
    ("break",  dict(entry_fill="range_break", exit_mode="ride")),
]
GATES = [("none", None), ("60m sign", ("60m", "sign")), ("60m rising", ("60m", "rising")),
         ("120m sign", ("120m", "sign")), ("daily sign", ("D", "sign")),
         ("60m squeeze on", ("60m", "sq_on")), ("60m fired<=3", ("60m", "fired")),
         ("60m+120m stack", ("stack", None))]
BASES = ["5m", "15m", "30m"]


def main():
    smoke = "smoke" in sys.argv
    insts = ["NQ"] if smoke else ["NQ", "ES"]
    lines = []
    for inst in insts:
        for base_tf in (BASES[:1] if smoke else BASES):
            df = load_base(inst, base_tf)
            pre = {tf: build_htf(df, tf) for tf in ("60m", "120m", "D")}
            hdr = f"\n== {inst} base {base_tf}  bars={len(df):,}"
            print(hdr, flush=True); lines.append(hdr)
            h2 = "%-10s %-16s %6s %5s %6s %11s %9s %6s | %11s %6s | %11s %6s %5s" % (
                "entry", "HTF gate", "trades", "WR%", "PF", "net $", "maxDD $", "MAR", "IS $", "IS PF", "LB $", "LB PF", "yrs+")
            print(h2); lines.append(h2)
            for ename, ekw in ENTRY_STYLES:
                for gname, gspec in GATES:
                    if gspec is None and gname == "none":
                        gl = gs = np.ones(len(df), bool)
                    elif gname == "60m+120m stack":
                        gl, gs = gate_mask([pre["60m"], pre["120m"]], "stack2")
                    else:
                        tf, mode = gspec
                        gl, gs = gate_mask([pre[tf]], mode)
                    s = stats(run_gated(df, gl, gs, **ekw), df, inst)
                    if s is None:
                        row = "%-10s %-16s  NO TRADES" % (ename, gname)
                    else:
                        f = s["full"]; mar = f["net"] / f["dd"] if f["dd"] > 0 else 0
                        row = "%-10s %-16s %6d %5.1f %6.2f %11s %9s %6.2f | %11s %6.2f | %11s %6.2f %2d/%-2d" % (
                            ename, gname, f["n"], f["wr"], min(f["pf"], 99), f"{f['net']:,.0f}", f"{f['dd']:,.0f}", mar,
                            f"{s['IS']['net']:,.0f}", min(s["IS"]["pf"], 99),
                            f"{s['LB']['net']:,.0f}", min(s["LB"]["pf"], 99), f["yplus"], f["yminus"])
                    print(row, flush=True); lines.append(row)
    out = os.path.join(ROOT, "tools", "data", "ttmsqz_round4_mtf.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("TTM SQUEEZE ROUND 4 (higher-TF verification of shorter-TF entries) - "
                 "window %s..%s, LB from %s\n" % (DATE_FROM, DATE_TO, LB_FROM))
        fh.write("\n".join(lines) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
