"""TTM SQUEEZE ROUND 12b - entry, protection and exit: the three things a discretionary
trader would change first, and the three this family (rounds 1-11) has barely touched.

Every prior round kept the fill/stop/exit scaffolding fixed and searched the squeeze and
gate knobs instead. This round holds the hourly squeeze-on gate FIXED (the family's one
durable finding) and varies only mechanics:

  1. PULLBACK ENTRY   - after the fire, wait for a retrace of X% of the squeeze range and
                         enter there with a limit order that expires after N bars.
  2. STRUCTURAL STOP  - stop at the opposite side of the squeeze range (+/- a small buffer)
                         instead of an ATR multiple.
  3. TIME EXIT        - hold a fixed N bars, exit at the next bar's open; with and without
                         the protective stop live underneath.
  4. TRAIL            - an ATR trailing stop instead of the momentum-fade exit.
  5. SCALE-OUT        - exit half the position at 1R, let the rest run to the fade exit.

INCUMBENT (crown cell, ES 30m RTH, quoted in every table):
  kc_mult 1.5, stop_atr 1.5, eod_cutoff 1, gate_len 20, gate_tf_min 60, gate_mode sq_on,
  entry_fill open, exit_mode fade, fade_bars 1, length 20, bb_mult 2.0, min_sq_bars 1
  -> n 359, PF 2.12, net $51,709, DD $3,740, lockbox $4,992 at PF 2.22.

THE HARNESS: tools/ttmsqz_round6_parts.py (load/score/COST/MULT/window/_mod, unchanged),
augur_strategies/TTMSQZ_3_0.py (engine, read for the fire/gate/same-bar-stop construction),
tools/ttmsqz_round8_crown.py (run_ttm/alone_score/compression_ratio, unchanged).

This file writes its OWN trade loop (`simulate`) rather than reusing run_backtest, because
none of the five questions above are exposed as knobs on the engine. It reuses the engine's
fire/range/gate arrays verbatim (copied from TTMSQZ_3_0.run_backtest and augur_strategies/
TTMSQZ_1_0.squeeze_indicators, not re-derived) and mirrors its causal + conservative-same-
bar-stop conventions exactly:
  - a decision made on bar u's close can only be acted on from bar u+1 onward;
  - a resting order (pullback limit / range-break stop) is checked against the bar's own
    range for a fill, at the open when the bar gaps through, else at the resting level;
  - whenever a stop and a target/exit both fall inside the same bar, the STOP is assumed to
    have been hit first (pessimistic resolution) - verified against the crown reproduction
    below, which matches the incumbent's n/PF/net/DD/lockbox exactly before any variant runs.

Pinned window 2010-06-07..2026-06-30, lockbox = trades exiting on/after 2025-07-01, house
ES cost (0.363 pts) and multiplier (50), one contract. SCAN ONLY: nothing here is crowned,
queued for Auto-Validate, or written to index.html, and no commit is made from this file.

Usage:  python tools/ttmsqz_r12b_entry_exit.py
Output: tools/data/ttmsqz_r12b_entry_exit.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6")
ttm1 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"), "ttm1_r12b")
ttm3 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "ttm3_r12b")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
INST = "ES"
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r12b_entry_exit.txt")

CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
             exit_mode="fade", fade_bars=1, stop_atr=1.5, eod_cutoff=1, gate_tf_min=60,
             gate_mode="sq_on", gate_len=20, gate_bars=0, gate_ratio=1.0, gate_fired_k=3,
             direction="both")
# ES tick = 0.25 pt
TICK = 0.25


# --------------------------------------------------------------------------------------
# Shared, causal setup - copied verbatim from TTMSQZ_3_0.run_backtest / _htf_gate so the
# fire/range/gate arrays are bit-identical to what the incumbent trades on.
# --------------------------------------------------------------------------------------
def _prep(df):
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float);  c = df["close"].values.astype(float)
    did = df["day_id"].values
    n = len(c)
    length, bb_mult, kc_mult = CROWN["length"], CROWN["bb_mult"], CROWN["kc_mult"]
    sq_on, mom, atr = ttm1.squeeze_indicators(h, l, c, length, bb_mult, kc_mult)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= CROWN["min_sq_bars"])
    warm = length * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()
    gate_long, gate_short = ttm3._htf_gate(
        h, l, c, did, df["_dt"], CROWN["gate_bars"], CROWN["gate_tf_min"], CROWN["gate_len"],
        bb_mult, kc_mult, CROWN["gate_mode"], CROWN["gate_fired_k"], CROWN["gate_ratio"])
    last_bar = ttm3._session_last_bar(did, n)
    return dict(o=o, h=h, l=l, c=c, n=n, warm=warm, sq_on=sq_on, mom=mom, atr=atr,
                fire=fire, rng_hi=rng_hi, rng_lo=rng_lo, gate_long=gate_long,
                gate_short=gate_short, last_bar=last_bar)


# --------------------------------------------------------------------------------------
# The generalized loop. entry_mode: "open" | "pullback". stop_mode: "atr" | "structural".
# exit_mode: "fade" | "time" | "trail". scale_out: bool (layers on top of exit_mode="fade").
# --------------------------------------------------------------------------------------
def simulate(P, entry_mode="open", pullback_pct=0.0, pullback_n=4,
             stop_mode="atr", stop_atr=1.5, struct_buf=0.0,
             exit_mode="fade", fade_bars=1, time_n=0, use_stop=True, trail_atr=1.5,
             scale_out=False, eod_cutoff=1):
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    n, warm = P["n"], P["warm"]
    mom, atr = P["mom"], P["atr"]
    fire, rng_hi, rng_lo = P["fire"], P["rng_hi"], P["rng_lo"]
    gate_long, gate_short, last_bar = P["gate_long"], P["gate_short"], P["last_bar"]

    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
    stop_px = None; target_px = None; half_booked = False; half_pnl = 0.0
    time_exit_bar = None; fade_cnt = 0
    pending = None   # dict(kind=..., side=..., ...)
    eligible_fires = 0; filled_fires = 0
    trades = []      # (entry_bar, exit_bar, pnl_pts, side, entry_px)

    def book(exit_i, px, sd, ep, eb, frac=1.0):
        p = (px - ep) if sd > 0 else (ep - px)
        trades.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(frac)))

    for u in range(warm, n):
        eod = u == last_bar[u]

        # 1. resolve any pending order
        if pending is not None:
            kind = pending["kind"]
            if kind == "exit":
                if pos != 0:
                    frac = 0.5 if half_booked else 1.0
                    book(u, o[u], side, entry_px, entry_bar, frac)
                    pos = 0; stop_px = None; target_px = None; half_booked = False
                pending = None
            elif kind == "mkt":
                if pos == 0:
                    side = pending["side"]
                    entry_px = o[u]; entry_bar = u; fade_cnt = 0; half_booked = False
                    aa = atr[u - 1]
                    if stop_mode == "atr":
                        stop_px = (entry_px - side * stop_atr * aa) if (stop_atr > 0 and np.isfinite(aa)) else None
                    else:  # structural: opposite side of the ORIGINAL squeeze range, +/- buffer
                        rh, rl = pending["rng_hi_f"], pending["rng_lo_f"]
                        stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                    if exit_mode == "trail":
                        stop_px = (entry_px - side * trail_atr * aa) if np.isfinite(aa) else None
                    if scale_out and stop_px is not None:
                        R = abs(entry_px - stop_px)
                        target_px = entry_px + side * R
                    if time_n > 0:
                        time_exit_bar = entry_bar + time_n
                    pos = side
                    if not use_stop and exit_mode == "time":
                        stop_px = None
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or (side < 0 and h[u] >= stop_px)):
                        book(u, stop_px, pos, entry_px, entry_bar, 1.0)
                        pos = 0; stop_px = None; target_px = None
                pending = None
            elif kind == "pullback":
                sd, lvl, expiry, rh, rl = pending["side"], pending["lvl"], pending["expiry"], pending["rng_hi_f"], pending["rng_lo_f"]
                fill = None
                if sd > 0:
                    if o[u] <= lvl: fill = o[u]
                    elif l[u] <= lvl: fill = lvl
                else:
                    if o[u] >= lvl: fill = o[u]
                    elif h[u] >= lvl: fill = lvl
                if fill is not None and pos == 0:
                    filled_fires += 1
                    side = sd; entry_px = fill; entry_bar = u; fade_cnt = 0; half_booked = False
                    aa = atr[u - 1]
                    stop_px = (entry_px - side * stop_atr * aa) if (stop_atr > 0 and np.isfinite(aa)) else None
                    if time_n > 0:
                        time_exit_bar = entry_bar + time_n
                    pos = side
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or (side < 0 and h[u] >= stop_px)):
                        book(u, stop_px, pos, entry_px, entry_bar, 1.0)
                        pos = 0; stop_px = None
                    pending = None
                elif u >= expiry or eod:
                    pending = None   # gives up unfilled; counted as (eligible - filled) below

        # 2. in-position management (only bars after the entry bar)
        if pos != 0 and u > entry_bar:
            if exit_mode == "trail" and stop_px is not None:
                extreme = h[u - 1] if pos > 0 else l[u - 1]
                aa = atr[u - 1]
                if np.isfinite(aa) and np.isfinite(extreme):
                    cand = extreme - pos * trail_atr * aa
                    stop_px = max(stop_px, cand) if pos > 0 else min(stop_px, cand)
            stopped = stop_px is not None and ((pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px))
            if stopped:
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                frac = 0.5 if half_booked else 1.0
                book(u, px, pos, entry_px, entry_bar, frac)
                pos = 0; stop_px = None; target_px = None; half_booked = False
            else:
                if scale_out and not half_booked and target_px is not None:
                    hit = (pos > 0 and h[u] >= target_px) or (pos < 0 and l[u] <= target_px)
                    if hit:
                        fillT = o[u] if ((pos > 0 and o[u] >= target_px) or (pos < 0 and o[u] <= target_px)) else target_px
                        book(u, fillT, pos, entry_px, entry_bar, 0.5)
                        half_booked = True
                if pos != 0 and exit_mode == "time" and time_exit_bar is not None and u >= time_exit_bar:
                    frac = 0.5 if half_booked else 1.0
                    book(u, o[u], pos, entry_px, entry_bar, frac)
                    pos = 0; stop_px = None; target_px = None; half_booked = False

        # 3. session close
        if eod:
            if pos != 0:
                frac = 0.5 if half_booked else 1.0
                book(u, c[u], pos, entry_px, entry_bar, frac)
                pos = 0; stop_px = None; target_px = None; half_booked = False
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]
        # 4. fade exit (delayed one bar, matching the engine's own "exit" pending kind)
        if pos != 0 and exit_mode == "fade" and np.isfinite(m) and np.isfinite(m1):
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = dict(kind="exit")
                continue

        # 5. new entries
        if pos == 0 and pending is None and fire[u] and np.isfinite(m) and m != 0:
            sd = 1 if m > 0 else -1
            if sd > 0 and not gate_long[u]:
                continue
            if sd < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            if entry_mode == "open":
                pending = dict(kind="mkt", side=sd, rng_hi_f=rng_hi[u], rng_lo_f=rng_lo[u])
            else:  # pullback
                if not np.isfinite(rng_hi[u]):
                    continue
                width = rng_hi[u] - rng_lo[u]
                if width <= 0:
                    continue
                lvl = rng_hi[u] - pullback_pct * width if sd > 0 else rng_lo[u] + pullback_pct * width
                pending = dict(kind="pullback", side=sd, lvl=lvl, expiry=u + pullback_n,
                               rng_hi_f=rng_hi[u], rng_lo_f=rng_lo[u])
                eligible_fires += 1

    t = pd.DataFrame(trades, columns=["eb", "xb", "pnl", "side", "epx", "frac"])
    return t, eligible_fires, filled_fires


def score_trades(t, df):
    if t is None or len(t) == 0:
        return None, None
    usd = (t["pnl"].values - COST[INST]) * MULT[INST] * t["frac"].values
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
    s = r6.score(usd, dates)
    lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
    sl = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
    return s, sl


HDR = "  %-42s %5s %7s %11s %9s | %11s %7s %7s  %s"


def row(name, s, sl, note=""):
    if s is None:
        return "  %-42s  no trades" % name
    lb_net = "{:,.0f}".format(sl["net"]) if sl else "n/a"
    lb_pf = "%.2f" % min(sl["pf"], 99) if sl else "n/a"
    lb_n = str(sl["n"]) if sl else "0"
    return HDR % (name, s["n"], "%.2f" % min(s["pf"], 99), "{:,.0f}".format(s["net"]),
                  "{:,.0f}".format(s["dd"]), lb_net, lb_pf, lb_n, note)


def beats(s, sl, sc, scl):
    """BOTH whole-run PF and lockbox net must beat the incumbent."""
    if s is None or sl is None:
        return False
    return (s["pf"] >= sc["pf"]) and (sl["net"] >= scl["net"])


def main():
    t0 = time.time()
    L = []
    L.append("TTM SQUEEZE ROUND 12b - entry, protection, exit   %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("ES 30m RTH, window %s..%s, lockbox from %s, house cost %.3f pts, mult %d, 1 contract"
             % (DATE_FROM, DATE_TO, LB_FROM, COST[INST], MULT[INST]))
    L.append("hourly squeeze-on gate held ON throughout (gate_tf_min 60, gate_mode sq_on, gate_len 20) - the")
    L.append("family's one durable finding across 11 rounds. Only entry/stop/exit mechanics vary below.")
    L.append("Same-bar stop/target conflicts resolved pessimistically (stop wins) throughout; no look-ahead:")
    L.append("every decision uses only bars closed at or before it, mirroring TTMSQZ_3_0.run_backtest exactly.")

    df = r6.load(INST, "30m", "RTH")
    P = _prep(df)

    # ---- sanity: reproduce the incumbent with THIS file's own loop, not the engine's ----
    t_base, _, _ = simulate(P, entry_mode="open", stop_mode="atr", stop_atr=1.5,
                            exit_mode="fade", fade_bars=1, eod_cutoff=1)
    sc, scl = score_trades(t_base, df)
    L.append("")
    L.append("REPRODUCTION CHECK (this file's loop vs the engine's run_backtest on the incumbent config):")
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    L.append(row("incumbent (engine, quoted)", dict(n=359, pf=2.12, net=51709, dd=3740),
                 dict(net=4992, pf=2.22, n=16), "engine numbers as stated"))
    L.append(row("incumbent (this file's own loop)", sc, scl,
                 "MATCH" if (sc["n"] == 359 and abs(sc["net"] - 51708.5) < 1 and abs(sc["dd"] - 3739.9) < 1)
                 else "MISMATCH - investigate before trusting anything below"))
    print("\n".join(L), flush=True)

    results = []   # (family, name, s, sl, extra_note)

    # ============================================================================
    # 1. PULLBACK ENTRY
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("1. PULLBACK ENTRY - wait for a retrace of X% of the squeeze range, limit order expires after N bars")
    L.append("   stop/exit unchanged from the incumbent (1.5 ATR stop, 1-bar fade exit)")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", "fires elig/filled/miss%"))
    for pct in (0.25, 0.38, 0.50):
        for pn in (4, 8):
            t, elig, filled = simulate(P, entry_mode="pullback", pullback_pct=pct, pullback_n=pn,
                                       stop_mode="atr", stop_atr=1.5, exit_mode="fade", fade_bars=1,
                                       eod_cutoff=1)
            s, sl = score_trades(t, df)
            miss = 100 * (elig - filled) / elig if elig else float("nan")
            name = "retrace %d%%, order lives %d bars" % (int(pct * 100), pn)
            note = "%d/%d/%.0f%%" % (elig, filled, miss)
            b = beats(s, sl, sc, scl)
            L.append(row(name, s, sl, note + ("  <-- BEATS incumbent (PF+LB)" if b else "")))
            results.append(("1 pullback entry", name, s, sl, note))
    print("\n".join(L[-9:]), flush=True)

    # ============================================================================
    # 2. STRUCTURAL STOP
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("2. STRUCTURAL STOP - opposite side of the squeeze range (+/- buffer) instead of 1.5x ATR")
    L.append("   entry/exit unchanged from the incumbent (next-open entry, 1-bar fade exit)")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    for buf in (0.0, 0.5, 1.0):
        t, _, _ = simulate(P, entry_mode="open", stop_mode="structural", struct_buf=buf,
                           exit_mode="fade", fade_bars=1, eod_cutoff=1)
        s, sl = score_trades(t, df)
        name = "range-edge stop, buffer %.2f pts" % buf
        b = beats(s, sl, sc, scl)
        L.append(row(name, s, sl, "<-- BEATS incumbent (PF+LB)" if b else ""))
        results.append(("2 structural stop", name, s, sl, ""))
    # caveat: the structural stop is materially WIDER than the 1.5 ATR incumbent stop, and the
    # realized max drawdown above does not by itself prove the wider per-trade tail risk is safe -
    # it only proves this window never punished it. Quantify the gap directly.
    n, warm = P["n"], P["warm"]
    o, atr_a = P["o"], P["atr"]
    fire, rng_hi, rng_lo = P["fire"], P["rng_hi"], P["rng_lo"]
    gate_long, gate_short, last_bar, mom_a = P["gate_long"], P["gate_short"], P["last_bar"], P["mom"]
    da, ds = [], []
    for u in range(warm, n - 1):
        if not (fire[u] and np.isfinite(mom_a[u]) and mom_a[u] != 0):
            continue
        sd = 1 if mom_a[u] > 0 else -1
        if sd > 0 and not gate_long[u]:
            continue
        if sd < 0 and not gate_short[u]:
            continue
        if last_bar[u] - u <= 1:
            continue
        ep = o[u + 1]
        aa = atr_a[u]
        if not np.isfinite(aa) or not np.isfinite(rng_hi[u]) or not np.isfinite(rng_lo[u]):
            continue
        da.append(1.5 * aa)
        ds.append(ep - rng_lo[u] if sd > 0 else rng_hi[u] - ep)
    da, ds = np.array(da), np.array(ds)
    if len(da):
        L.append("  caveat: mean stop distance 1.5xATR $%s vs range-edge $%s per contract (%.0f%% wider, %d fires) -"
                 % ("{:,.0f}".format(da.mean() * MULT[INST]), "{:,.0f}".format(ds.mean() * MULT[INST]),
                    100 * (ds.mean() / da.mean() - 1), len(da)))
        L.append("  the wider stop is what stops fewer good trades from being cut early, but it also means a bigger loss")
        L.append("  on whichever trade DOES eventually hit it; this window's max DD does not certify that tail is safe.")
    print("\n".join(L[-8:]), flush=True)

    # ============================================================================
    # 3. TIME EXIT
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("3. TIME EXIT - hold N bars, exit at the next bar's open; with and without the protective stop")
    L.append("   entry unchanged (next-open); no fade exit in this family (time or stop or EOD only)")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    for nbars in (2, 4, 6, 8, 12):
        for use_stop in (True, False):
            t, _, _ = simulate(P, entry_mode="open", stop_mode="atr", stop_atr=1.5,
                               exit_mode="time", time_n=nbars, use_stop=use_stop, eod_cutoff=1)
            s, sl = score_trades(t, df)
            name = "hold %d bars, %s stop" % (nbars, "WITH 1.5 ATR" if use_stop else "NO")
            b = beats(s, sl, sc, scl)
            L.append(row(name, s, sl, "<-- BEATS incumbent (PF+LB)" if b else ""))
            results.append(("3 time exit", name, s, sl, ""))
    print("\n".join(L[-11:]), flush=True)

    # ============================================================================
    # 4. TRAIL
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("4. TRAIL - an ATR trailing stop instead of the momentum-fade exit")
    L.append("   entry unchanged (next-open); trail starts at entry x ATR mult, only ratchets in favor")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    for k in (1.0, 1.5, 2.0):
        t, _, _ = simulate(P, entry_mode="open", stop_mode="atr", exit_mode="trail", trail_atr=k,
                           eod_cutoff=1)
        s, sl = score_trades(t, df)
        name = "%.1fx ATR trail" % k
        b = beats(s, sl, sc, scl)
        L.append(row(name, s, sl, "<-- BEATS incumbent (PF+LB)" if b else ""))
        results.append(("4 trail", name, s, sl, ""))
    print("\n".join(L[-5:]), flush=True)

    # ============================================================================
    # 5. FIRST-TARGET SCALE
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("5. FIRST-TARGET SCALE - exit half at 1R (R = entry-to-1.5-ATR-stop distance), let the rest run to the fade")
    L.append("   cost split 50/50 across the two legs so the total cost budget per original trade is unchanged")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    t, _, _ = simulate(P, entry_mode="open", stop_mode="atr", stop_atr=1.5, exit_mode="fade",
                       fade_bars=1, scale_out=True, eod_cutoff=1)
    s, sl = score_trades(t, df)
    b = beats(s, sl, sc, scl)
    L.append(row("scale half at 1R, rest to fade", s, sl, "<-- BEATS incumbent (PF+LB)" if b else ""))
    results.append(("5 scale-out", "scale half at 1R, rest to fade", s, sl, ""))
    L.append("  prior finding on another family (ORB): scale-outs were risk-adjusted (lower DD), not")
    L.append("  richer (not higher net). Read below whether that repeats here.")
    if s and sc:
        L.append("  net $ vs incumbent: %s vs %s (%.1f%%)   DD $ vs incumbent: %s vs %s (%.1f%%)"
                 % ("{:,.0f}".format(s["net"]), "{:,.0f}".format(sc["net"]), 100 * s["net"] / sc["net"],
                    "{:,.0f}".format(s["dd"]), "{:,.0f}".format(sc["dd"]), 100 * s["dd"] / sc["dd"]))
    print("\n".join(L[-6:]), flush=True)

    # ============================================================================
    # summary
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("SUMMARY - incumbent: n 359, PF 2.12, net $51,709, DD $3,740, lockbox $4,992 at PF 2.22")
    L.append("=" * 100)
    leads = [(fam, name) for fam, name, s, sl, note in results if beats(s, sl, sc, scl)]
    if leads:
        L.append("cells beating the incumbent on BOTH whole-run PF and lockbox net:")
        for fam, name in leads:
            L.append("  - [%s] %s" % (fam, name))
    else:
        L.append("no cell beats the incumbent on both whole-run PF and lockbox net.")
    L.append("")
    L.append("elapsed %.0fs" % (time.time() - t0))

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[-30:]))
    print("\nwrote " + LOG)


if __name__ == "__main__":
    main()
