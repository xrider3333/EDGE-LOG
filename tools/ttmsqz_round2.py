"""
TTM SQUEEZE ROUND 2 — unique/different mechanisms, owner ask 2026-08-22 ("keep exploring
unique and different options for this").

Round 1 (tools/ttmsqz_baselines.py, studies rows 251-340, validates #268/#269 FAIL) showed:
below 15m costs win, 15m marginal, 30m/60m the only positive ground. Round 2 therefore runs
on NQ/ES 15m, 30m, 60m only, and instead of re-tuning Carter's knobs it changes the MECHANISM:

  ENTRY DIRECTION   mom (Carter) · inverse (fade the fire) · slope (momentum turning, not sign)
  ENTRY FILL        open (next open, Carter) · range_break (stop order at the squeeze range
                    edge in the trade direction; rests up to 3 bars, gap-through pays the open)
  CONFIRMATION      confirm_bars: enter only after N bars with momentum still strengthening
  GATES             trend (200-bar EMA side) · morning (entries before 12:00 ET) ·
                    daily_sq (yesterday's DAILY-bar squeeze was ON — Carter's MTF stack)
  EXITS             fade (Carter) · ride (stop/EOD only) · target (squeeze range height
                    projected from the break; Carter's own price-target idea)

All legal: every decision on bar t's close, fills on bar t+1 (open or intrabar stop level,
gap-through pays the open, never the level). Flat at session close. Window PINNED
2010-06-07..2026-06-30, LB = last 12 months, same as round 1. House costs.

Usage:  python tools/ttmsqz_round2.py [smoke]
Output: tools/data/ttmsqz_round2.txt (+ .csv, untracked by the *.csv rule)
"""
import os, sys, time, importlib.util
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


# ── data (same loader as round 1) ──────────────────────────────────────────────
def load(inst, tf):
    src_tf = tf if tf in ("1m", "2m", "5m", "15m") else "5m"
    df = pd.read_csv(os.path.join(UP, f"NOADJ_{inst}_{src_tf}_RTH.csv"))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(DATE_FROM).date()) & (df["_dt"].dt.date <= pd.Timestamp(DATE_TO).date())]
    if tf in ("30m", "60m"):
        m = int(tf[:-1])
        mins = df["_dt"].dt.hour * 60 + df["_dt"].dt.minute - 570
        key = df["_dt"].dt.date.astype(str) + "_" + (mins // m).astype(str).str.zfill(3)
        g = df.groupby(key, sort=True)
        df = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                           "close": g["close"].last(), "volume": g["volume"].sum(), "_dt": g["_dt"].first()}).reset_index(drop=True)
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    return df.reset_index(drop=True)


def daily_sq_gate(df, length=20, bb_mult=2.0, kc_mult=1.5):
    """Per-bar bool: was the DAILY-bar squeeze ON as of the PRIOR session's close?
    Daily bars are built from this timeframe's sessions (prior-day causal)."""
    g = df.groupby("day_id", sort=True)
    dh, dl, dc = g["high"].max().values, g["low"].min().values, g["close"].last().values
    sq, _, _ = ttm.squeeze_indicators(dh, dl, dc, length, bb_mult, kc_mult)
    prior = np.concatenate([[False], sq[:-1]])          # day d reads day d-1's state
    return prior[df["day_id"].values]


def run_variant(df, *, length=20, bb_mult=2.0, kc_mult=1.5, min_sq=1,
                entry_dir="mom", entry_fill="open", confirm_bars=0,
                gate="none", exit_mode="fade", fade_bars=1, target_mult=1.0,
                stop_atr=2.0, eod_cutoff=3):
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

    # squeeze range (hi/lo over the just-ended squeeze, recorded at the fire bar)
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()

    ema = pd.Series(c).ewm(span=200, adjust=False).mean().to_numpy()
    hourmin = df["_dt"].dt.hour.values * 100 + df["_dt"].dt.minute.values
    dsq = daily_sq_gate(df) if gate == "daily_sq" else None

    last_bar = np.empty(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        last_bar[a:b] = b - 1; a = b

    pos = 0; entry_px = 0.0; entry_bar = -1; stop_px = None; tgt_px = None
    pending = None          # ("mkt",side) / ("stop",side,level,expiry) / ("exit",)
    fade_cnt = 0
    pnl, log = [], []

    def book(i, px, side, ep, eb):
        pnl.append((px - ep) if side > 0 else (ep - px))
        log.append((eb, i, pnl[-1], side, ep, px))

    for u in range(warm, n):
        eod = u == last_bar[u]
        # fills
        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    book(u, o[u], pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
                pending = None
            elif kind == "mkt":
                if pos == 0:
                    side = pending[1]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                pending = None
            else:                                    # resting stop order
                _, side, lvl, expiry, rh, rl = pending
                fill = None
                if side > 0:
                    if o[u] >= lvl: fill = o[u]
                    elif h[u] >= lvl: fill = lvl
                else:
                    if o[u] <= lvl: fill = o[u]
                    elif l[u] <= lvl: fill = lvl
                if fill is not None and pos == 0:
                    pos = side; entry_px = fill; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    if exit_mode == "target":
                        height = rh - rl
                        tgt_px = entry_px + side * target_mult * height
                    pending = None
                elif u >= expiry or eod:
                    pending = None
        # target / stop intrabar
        if pos != 0 and u > entry_bar:
            if stop_px is not None and ((pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px)):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
            elif tgt_px is not None and ((pos > 0 and h[u] >= tgt_px) or (pos < 0 and l[u] <= tgt_px)):
                px = max(o[u], tgt_px) if pos > 0 else min(o[u], tgt_px)
                book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
        if eod:
            if pos != 0:
                book(u, c[u], pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
            pending = None
            continue
        # decisions at u's close
        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue
        if pos != 0 and exit_mode in ("fade", "zero"):
            if exit_mode == "fade":
                fading = (m < m1) if pos > 0 else (m > m1)
                fade_cnt = fade_cnt + 1 if fading else 0
                if fade_cnt >= fade_bars:
                    pending = ("exit",); continue
            else:
                if (m <= 0) if pos > 0 else (m >= 0):
                    pending = ("exit",); continue
        if pos == 0 and pending is None:
            # signal bar = fire (possibly confirmed)
            sig = False; i0 = u
            if confirm_bars > 0:
                i0 = u - confirm_bars
                if i0 > warm and fire[i0]:
                    seg = mom[i0:u + 1]
                    side0 = 1 if mom[i0] > 0 else -1
                    ok = np.all(np.diff(seg) > 0) if side0 > 0 else np.all(np.diff(seg) < 0)
                    sig = ok
            else:
                sig = fire[u]
            if not sig:
                continue
            mm = mom[i0]
            if entry_dir == "mom":
                side = 1 if mm > 0 else -1
            elif entry_dir == "inverse":
                side = -1 if mm > 0 else 1
            else:                                     # slope: momentum turning direction
                side = 1 if mom[i0] > mom[i0 - 1] else -1
            if side == 0:
                continue
            if gate == "trend" and ((side > 0) != (c[u] > ema[u])):
                continue
            if gate == "morning" and hourmin[u] >= 1200:
                continue
            if gate == "daily_sq" and not dsq[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            if entry_fill == "open":
                pending = ("mkt", side)      # target exit needs the range -> range_break only
            else:                                     # range_break stop order
                if not np.isfinite(rng_hi[i0]):
                    continue
                lvl = rng_hi[i0] if side > 0 else rng_lo[i0]
                pending = ("stop", side, lvl, u + 4, rng_hi[i0], rng_lo[i0])

    if not pnl:
        return None
    t = pd.DataFrame(log, columns=["eb", "xb", "pnl", "side", "ep", "xp"])
    return t


# target for open-fill entries: handled only in range_break mode (target needs the range);
# open-fill target uses the fire bar's range via a wrapper below.

def stats(t, df, inst):
    if t is None or not len(t):
        return None
    mult, cost = MULT[inst], COST[inst]
    t = t.copy(); t["usd"] = (t["pnl"] - cost) * mult
    dts = pd.DatetimeIndex(df["_dt"])
    t["date"] = dts[t["xb"].values].date; t["year"] = dts[t["xb"].values].year

    def block(x):
        if not len(x):
            return dict(net=0, pf=0, dd=0, n=0)
        u = x["usd"].values; cum = np.cumsum(u)
        dd = -float((cum - np.maximum.accumulate(cum)).min())
        gw = u[u > 0].sum(); gl = -u[u < 0].sum()
        return dict(net=float(u.sum()), pf=float(gw / gl) if gl > 0 else 99.0, dd=dd, n=len(u))
    lb = block(t[t["date"] >= pd.Timestamp(LB_FROM).date()])
    is_ = block(t[t["date"] < pd.Timestamp(LB_FROM).date()])
    yr = t.groupby("year")["usd"].sum()
    f = block(t); f.update(yplus=int((yr > 0).sum()), yminus=int((yr <= 0).sum()),
                           wr=float(100 * (t["usd"] > 0).mean()))
    return dict(full=f, IS=is_, LB=lb)


VARIANTS = [
    ("control: Carter kc2.0",            dict(kc_mult=2.0)),
    ("fade the fire (inverse)",          dict(entry_dir="inverse")),
    ("fade the fire, tight kc2.0",       dict(entry_dir="inverse", kc_mult=2.0)),
    ("slope direction",                  dict(entry_dir="slope")),
    ("confirm 2 bars strengthening",     dict(confirm_bars=2)),
    ("range-break stop entry",           dict(entry_fill="range_break")),
    ("range-break + ride exit",          dict(entry_fill="range_break", exit_mode="ride")),
    ("range-break + 1x range target",    dict(entry_fill="range_break", exit_mode="target", target_mult=1.0)),
    ("range-break + 2x range target",    dict(entry_fill="range_break", exit_mode="target", target_mult=2.0)),
    ("trend gate (200 EMA side)",        dict(gate="trend")),
    ("trend gate + kc2.0",               dict(gate="trend", kc_mult=2.0)),
    ("morning fires only",               dict(gate="morning")),
    ("daily-squeeze MTF gate",           dict(gate="daily_sq")),
    ("ride exit (stop/EOD only)",        dict(exit_mode="ride")),
    ("long squeeze only (min 12)",       dict(min_sq=12)),
    ("long squeeze 12 + ride",           dict(min_sq=12, exit_mode="ride")),
]

GRID = [("NQ", "15m"), ("NQ", "30m"), ("NQ", "60m"), ("ES", "15m"), ("ES", "30m"), ("ES", "60m")]


def main():
    smoke = "smoke" in sys.argv
    grid = GRID[:1] if smoke else GRID
    lines = []
    for inst, tf in grid:
        df = load(inst, tf)
        hdr = f"\n== {inst} {tf}  bars={len(df):,}  sessions={df['day_id'].max()+1:,}"
        print(hdr, flush=True); lines.append(hdr)
        h2 = "%-34s %6s %5s %6s %11s %9s %6s | %11s %6s | %11s %6s %5s" % (
            "variant", "trades", "WR%", "PF", "net $", "maxDD $", "MAR", "IS $", "IS PF", "LB $", "LB PF", "yrs+")
        print(h2); lines.append(h2)
        for label, kw in (VARIANTS[:4] if smoke else VARIANTS):
            t = run_variant(df, **kw)
            s = stats(t, df, inst)
            if s is None:
                row = "%-34s  NO TRADES" % label
            else:
                f = s["full"]; mar = f["net"] / f["dd"] if f["dd"] > 0 else 0
                row = "%-34s %6d %5.1f %6.2f %11s %9s %6.2f | %11s %6.2f | %11s %6.2f %2d/%-2d" % (
                    label, f["n"], f["wr"], min(f["pf"], 99), f"{f['net']:,.0f}", f"{f['dd']:,.0f}", mar,
                    f"{s['IS']['net']:,.0f}", min(s["IS"]["pf"], 99),
                    f"{s['LB']['net']:,.0f}", min(s["LB"]["pf"], 99), f["yplus"], f["yminus"])
            print(row, flush=True); lines.append(row)
    out = os.path.join(ROOT, "tools", "data", "ttmsqz_round2.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("TTM SQUEEZE ROUND 2 (mechanism variants) - window %s..%s, LB from %s\n" % (DATE_FROM, DATE_TO, LB_FROM))
        fh.write("\n".join(lines) + "\n")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
