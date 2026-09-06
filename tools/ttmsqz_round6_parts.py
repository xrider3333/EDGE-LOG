"""
TTM SQUEEZE ROUND 6 — the two things five rounds never tried, plus what to do about it.

Rounds 1-5 closed the family as a STANDALONE: ceiling R / YR 12, the lowest of any family
measured, about 2,900 dollars a year. The owner asked to keep going, so this round stops
trying to make the strategy bigger and asks different questions.

PART A — IS THE COMPRESSION CHECK WORTH MORE TO SOMEBODY ELSE?
  The durable finding of five rounds is not the squeeze entry, it is the CHECK: only trade
  while the hourly chart is still coiled. On TTM that check sits behind an entry that fires
  20 times a year. Bolted onto a family that fires hundreds of times a year it costs nothing
  to run. Method: take a crowned strategy's OWN trades, unchanged, and split them by the
  hourly compression state at the decision bar. No re-tuning. This asks only whether the
  state SEPARATES trades the family already takes.

PART B — THE 24-HOUR TAPE, never shown to this strategy.

PART C — THE PRACTICAL USE. Filtering on compression throws away ~86% of the trades, which
  guts R / YR. Sizing does not: keep every trade, put more risk on the ones the hourly says
  are worth more.

Honest note: A and C split an existing trade list. That is a SCAN, not a backtest of a new
strategy, and nothing here can be crowned on it. It says whether a full test is warranted.

Window pinned 2010-06-07..2026-06-30, lockbox = last 12 months, house costs, one contract.

Usage:  python tools/ttmsqz_round6_parts.py [A|B|C|ABC]
Output: tools/data/ttmsqz_round6_transfer.txt
"""
import os, sys, importlib.util, inspect
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UP = os.path.join(ROOT, "augur_uploads")

DATE_FROM, LB_FROM, DATE_TO = "2010-06-07", "2025-07-01", "2026-06-30"
COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

CROWNS = [
    ("NOISE short-veto (paper leg)", "NOISE_1_1_SBS_V90.py", "NQ", "5m", "RTH"),
    ("NOISE R/YR record (B18)", "NOISE_1_2_RYR.py", "NQ", "5m", "RTH"),
    ("ORB #234 crown", "ORB_3_6_C2.py", "NQ", "5m", "RTH"),
]


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


ttm = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"), "ttm1")


def load(inst, tf, session="RTH"):
    """Master bars with _dt (bar open) and _end (bar close = when it becomes knowable)."""
    fn = "NOADJ_%s_%s_%s.csv" % (inst, tf, session)
    path = os.path.join(UP, fn)
    if not os.path.exists(path):
        path = os.path.join(SHARED, "augur_uploads", fn)
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(DATE_FROM).date())
            & (df["_dt"].dt.date <= pd.Timestamp(DATE_TO).date())].reset_index(drop=True)
    df["_end"] = df["_dt"] + pd.Timedelta(minutes=int(tf[:-1]))
    # ETH runs 18:00 -> 17:00 next day, so the trading DAY rolls at 18:00 ET.
    d = (df["_dt"] + pd.Timedelta(hours=6)).dt.date if session == "ETH" else df["_dt"].dt.date
    df["day_id"] = pd.factorize(d)[0]
    return df


def hourly_compression(df, gate_tf_min=60, length=20, bb_mult=2.0, kc_mult=1.5):
    """Compression state of the gate_tf_min frame, mapped causally onto df's bars.

    A higher-timeframe bar is usable on bar u only once COMPLETE (its last member bar ends
    at or before u's end) - the construction the audited round-4 harness uses."""
    first = df.groupby("day_id")["_dt"].transform("first")
    off = ((df["_dt"] - first).dt.total_seconds() // 60).astype("int64")
    key = df["day_id"].astype(str) + "_" + (off // int(gate_tf_min)).astype(str).str.zfill(4)
    g = df.groupby(key, sort=True)
    hh, ll, cc = g["high"].max().values, g["low"].min().values, g["close"].last().values
    end = g["_end"].last().values
    order = np.argsort(end)
    hh, ll, cc, end = hh[order], ll[order], cc[order], end[order]
    sq, _, _ = ttm.squeeze_indicators(hh, ll, cc, length, bb_mult, kc_mult)
    warm = length * 2 + 5
    j = np.searchsorted(end, df["_end"].values, side="right") - 1
    ok = j >= warm
    jj = np.clip(j, 0, len(cc) - 1)
    return np.where(ok, sq[jj], False).astype(bool)


def score(usd, dates):
    if len(usd) == 0:
        return None
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    gw = usd[usd > 0].sum()
    gl = -usd[usd < 0].sum()
    losses = usd[usd < 0]
    evr = float(usd.mean() / -losses.mean()) if len(losses) and losses.mean() < 0 else float("nan")
    yrs = max((max(dates) - min(dates)).days / 365.25, 1e-9)
    return dict(n=len(usd), net=float(usd.sum()), pf=float(gw / gl) if gl > 0 else 99.0,
                dd=dd, wr=float(100 * (usd > 0).mean()), evr=evr,
                ryr=evr * len(usd) / yrs if evr == evr else float("nan"))


def run_crown(fn, inst, tf, sess):
    """A crowned strategy on its own tape, with only the optional arrays it declares."""
    path = os.path.join(ROOT, "augur_strategies", fn)
    if not os.path.exists(path):
        path = os.path.join(SHARED, "augur_strategies", fn)
    m = _mod(path, fn.replace(".py", "_x"))
    df = load(inst, tf, sess)
    kw = {k: v["default"] for k, v in getattr(m, "DEFAULT_PARAMS", {}).items()}
    sp = inspect.signature(m.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    ex = {}
    if "volumes" in sp or hk:
        ex["volumes"] = df["volume"].values if "volume" in df else None
    if "day_id" in sp or hk:
        ex["day_id"] = df["day_id"].values
    if "index" in sp or hk:
        ex["index"] = df["_dt"]
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                       df["close"].values, return_trades=True, **ex, **kw)
    if not r or not r.get("trades"):
        return None
    # Trade tuples are not one shape across the library (ORB emits 5 fields, TTM 6), but all
    # of them start (entry_bar, exit_bar, pnl_points), which is all this needs.
    tr = [(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]]
    t = pd.DataFrame(tr, columns=["eb", "xb", "pnl"])
    usd = (t["pnl"].values - COST[inst]) * MULT[inst]
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
    comp = hourly_compression(df)
    on = comp[np.clip(t["eb"].values - 1, 0, len(comp) - 1)]
    lb = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
    return dict(df=df, usd=usd, dates=dates, on=on, lb=lb, n=len(t))


HDR = "  %-24s %6s %6s %7s %11s %9s %7s %8s" % (
    "slice", "n", "WR%", "PF", "net $", "maxDD $", "EV R", "R/YR")


def _row(nm, s):
    return "  %-24s %6d %6.1f %7.2f %11s %9s %7.3f %8.1f" % (
        nm, s["n"], s["wr"], min(s["pf"], 99), "{:,.0f}".format(s["net"]),
        "{:,.0f}".format(s["dd"]), s["evr"], s["ryr"])


def part_a(lines):
    lines.append("")
    lines.append("=" * 104)
    lines.append("PART A - does the hourly-compression state separate ANOTHER family's own trades?")
    lines.append("  A SCAN, not a backtest. Each crowned config runs unchanged; its trades are split")
    lines.append("  by the compression state at the decision bar. Nothing is re-tuned.")
    lines.append("=" * 104)
    for label, fn, inst, tf, sess in CROWNS:
        try:
            d = run_crown(fn, inst, tf, sess)
        except Exception as e:
            lines.append("")
            lines.append("%s: could not run (%s: %s)" % (label, type(e).__name__, str(e)[:60]))
            continue
        if d is None:
            continue
        usd, dates, on, lb = d["usd"], d["dates"], d["on"], d["lb"]
        lines.append("")
        lines.append("%s  (%s %s %s, %d trades)" % (label, inst, tf, sess, d["n"]))
        lines.append(HDR)
        for nm, msk in (("ALL (unfiltered)", np.ones(len(usd), bool)),
                        ("hourly COMPRESSED", on), ("hourly not compressed", ~on)):
            s = score(usd[msk], dates[msk])
            if s:
                lines.append(_row(nm, s))
        # IS THE GAP MORE THAN NOISE? Permutation on the difference in mean dollars per trade:
        #   shuffle the label and see how often chance makes a gap this large. Distribution-free,
        #   which matters because these PnLs are fat-tailed and a t-test would flatter them.
        if on.any() and (~on).any():
            rng = np.random.default_rng(42)
            obs = float(usd[on].mean() - usd[~on].mean())
            lab = on.copy()
            hits = 0
            N = 5000
            for _ in range(N):
                rng.shuffle(lab)
                if abs(float(usd[lab].mean() - usd[~lab].mean())) >= abs(obs):
                    hits += 1
            p = hits / N
            lines.append("  gap in mean $/trade: %s   permutation p = %.4f  (%s)" % (
                "{:+,.0f}".format(obs), p,
                "REAL - chance rarely makes a gap this big" if p < 0.05
                else "NOT significant on its own"))
        # THE CHECK THAT DECIDES IT: the same split on the LOCKBOX year alone, which no search
        #   of any kind has touched. A separation that dies here is an in-sample artefact.
        if lb.any():
            lines.append("  -- LOCKBOX ONLY (%s onward, untouched) --" % LB_FROM)
            for nm, msk in (("LB all", lb), ("LB compressed", lb & on), ("LB not compressed", lb & ~on)):
                s = score(usd[msk], dates[msk])
                if s:
                    lines.append(_row(nm, s))
        lines.append("  compressed share of trades: %.1f%%" % (100 * on.mean()))


def part_b(lines):
    lines.append("")
    lines.append("=" * 104)
    lines.append("PART B - TTM on the 24-HOUR tape (every previous round was regular hours only)")
    lines.append("=" * 104)
    CONFIGS = [("published (fade, 2 ATR)", {}),
               ("kc 2.0 (round-1 best shape)", dict(kc_mult=2.0)),
               ("min 6-bar squeeze", dict(min_sq_bars=6)),
               ("zero-cross exit", dict(exit_mode="zero")),
               ("flip exit", dict(exit_mode="flip")),
               ("long only", dict(direction="long"))]
    for inst, tf in (("NQ", "5m"), ("ES", "5m")):
        try:
            df = load(inst, tf, "ETH")
        except Exception as e:
            lines.append("")
            lines.append("%s %s ETH: master not readable (%s)" % (inst, tf, str(e)[:60]))
            continue
        lines.append("")
        lines.append("== %s %s ETH   bars=%d  sessions=%d" % (inst, tf, len(df), df["day_id"].max() + 1))
        lines.append("  %-28s %6s %6s %7s %11s %9s %7s %8s" % (
            "config", "n", "WR%", "PF", "net $", "maxDD $", "EV R", "R/YR"))
        for label, kw in CONFIGS:
            r = ttm.run_backtest(df["open"].values, df["high"].values, df["low"].values,
                                 df["close"].values, day_id=df["day_id"].values,
                                 index=df["_dt"], return_trades=True, **kw)
            if not r or not r.get("trades"):
                lines.append("  %-28s  no trades" % label)
                continue
            tr = [(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]]
            t = pd.DataFrame(tr, columns=["eb", "xb", "pnl"])
            usd = (t["pnl"].values - COST[inst]) * MULT[inst]
            dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
            s = score(usd, dates)
            lines.append("  %-28s %6d %6.1f %7.2f %11s %9s %7.3f %8.1f" % (
                label, s["n"], s["wr"], min(s["pf"], 99), "{:,.0f}".format(s["net"]),
                "{:,.0f}".format(s["dd"]), s["evr"], s["ryr"]))


def part_c(lines):
    lines.append("")
    lines.append("=" * 104)
    lines.append("PART C - COMPRESSION AS A SIZE TILT, not a filter (every trade kept)")
    lines.append("  A pure risk multiplier on the compressed slice: no trade is added, removed or")
    lines.append("  re-timed, so this cannot smuggle in a look-ahead. Read maxDD, not just net -")
    lines.append("  a tilt raises both.")
    lines.append("=" * 104)
    for label, fn, inst, tf, sess in CROWNS:
        try:
            d = run_crown(fn, inst, tf, sess)
        except Exception as e:
            lines.append("")
            lines.append("%s: could not run (%s)" % (label, type(e).__name__))
            continue
        if d is None:
            continue
        base, dates, on, lb = d["usd"], d["dates"], d["on"], d["lb"]
        lines.append("")
        lines.append("%s" % label)
        lines.append("  %-26s %11s %7s %9s %7s | %11s %7s %7s" % (
            "sizing", "net $", "PF", "maxDD $", "EV R", "LB net $", "LB PF", "LB EVR"))
        for nm, mult in (("flat 1x (as traded)", 1.0), ("2x on compressed", 2.0),
                         ("3x on compressed", 3.0), ("compressed ONLY (filter)", None)):
            if mult is None:
                u, dd_, ll = base[on], dates[on], lb[on]
            else:
                u, dd_, ll = base * np.where(on, mult, 1.0), dates, lb
            s1 = score(u, dd_)
            s2 = score(u[ll], dd_[ll]) if ll.any() else None
            lines.append("  %-26s %11s %7.2f %9s %7.3f | %11s %7.2f %7.3f" % (
                nm, "{:,.0f}".format(s1["net"]), min(s1["pf"], 99),
                "{:,.0f}".format(s1["dd"]), s1["evr"],
                "{:,.0f}".format(s2["net"]) if s2 else "-",
                min(s2["pf"], 99) if s2 else 0.0, s2["evr"] if s2 else 0.0))


def main():
    which = (sys.argv[1].upper() if len(sys.argv) > 1 else "ABC")
    lines = ["TTM SQUEEZE ROUND 6 - the compression check as a cross-family signal, and the 24h tape",
             "window %s..%s, lockbox from %s, house costs, one contract" % (DATE_FROM, DATE_TO, LB_FROM)]
    if "A" in which:
        part_a(lines)
    if "B" in which:
        part_b(lines)
    if "C" in which:
        part_c(lines)
    out = os.path.join(ROOT, "tools", "data", "ttmsqz_round6_transfer.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote " + out)


if __name__ == "__main__":
    main()
