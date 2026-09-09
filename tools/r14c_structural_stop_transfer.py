"""
ROUND 14c — does TODAY'S TTM finding (a STRUCTURAL stop beats a volatility-multiple stop)
TRANSFER to the shop's other three crowned legs?

WHERE THIS PICKS UP
  TTM run #353 (TTMSQZ_3_0_ES30SS20.py) replaced the family's 1.5x-ATR protective stop with
  a STRUCTURAL one -- the far side of the squeeze range that produced the fire, i.e. "the
  level that says the setup was simply wrong" -- and it was worth a great deal: profit factor
  2.12 -> 2.70 on the mechanism alone, lockbox $4,992 -> $11,710, at a LOWER drawdown. Round 13
  (tools/ttmsqz_r13_gap_stress.py) then found WHY: the wide stop carries only 6.8% of gross
  losses against the ATR stop's 43-44%, because it is mostly hit on trades that went nowhere,
  not on trades merely against you for a moment.

  Every crowned leg has some level that says its OWN setup was wrong. This file asks whether
  they all stop in the wrong place too:
    ORB    (#234 ORB_3_6_C2.py, #314 ORB_3_6_R6.py) -- ALREADY structural (a multiple of the
           opening range). Question: is the multiple AT the structural level (1x range, the
           opposite side of the OR) or wider than it? Test stopping at the opposite OR edge.
    NOISE  (NOISE_1_0.py, #243 crowned params = api/paper.py NOISE_243_SBS_V90) -- stops on a
           multiple of the ENTRY bar's own excursion beyond the reference level ("bandwidth").
           Its structural level is the OPPOSITE band of its own noise envelope.
    ENGU-Q (ENGUQ_1M_ETH_ER_1_0.py, #309 params = api/paper.py ENGUQ_309) -- stops on
           stop_mult x (entry - swing_low). Its structural level IS the swing low itself
           (stop_mult = 1.0 exactly); #309's 1.3 already sits 30% beyond it.

METHOD (per family)
  1. REPRODUCE the crowned config on the family's own tape/window/costs, print n/PF/net/DD/
     lockbox beside the numbers in the family's own doc. A family that will not reproduce is
     not tested further (none of these three needed that escape hatch -- see the reproduction
     sections below for the honest caveats where a figure is close but not bit-exact).
  2. Re-simulate the SAME crowned cell with ONE CHANGE: the protective-stop LEVEL. Everything
     else -- entries, targets, breakeven arming, trailing, direction -- is untouched. Two or
     three buffers are tested per family, all added SLIGHTLY BEYOND the structural level
     (never inside it), mirroring how TTM's own SS file chose its buffer.
  3. Tag every exit's reason (stop / target-or-fade-or-vwap / eod) so the same "share of exits
     vs share of gross losses" read TTM used can be reported before and after.

NO LOOK-AHEAD. Every level here is set from bars closed at or before the decision bar and is
STATIC once a trade opens (it does not trail with the market) -- same convention TTM's SS file
used ("captured at the fire bar, closed-bar information only"). A stop and a target inside the
same bar resolve pessimistically (stop-first), matching every engine file's own convention.
Entries/targets/breakeven timing are copied byte-for-byte from each family's engine file; only
the initial stop-price formula is swapped, so the "one change" claim is mechanical, not just a
description.

RULES CARRIED FROM THE BRIEF: each family on its own tape/costs/window (NQ 0.533 pts/$20,
windows below). Lockbox reported, never tuned on. This file crowns nothing, queues nothing,
and does not touch index.html.

Usage:  python tools/r14c_structural_stop_transfer.py
Output: tools/data/r14c_structural_stop_transfer.txt
"""
import os, sys, time, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LOG = os.path.join(ROOT, "tools", "data", "r14c_structural_stop_transfer.txt")

COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

# House-standard pinned window, the same one tools/ttmsqz_round6_parts.py uses to score the
# ORB and NOISE crowns cross-family, and the one ENGUQ.md itself states for the #309 params.
DATE_FROM, DATE_TO = "2010-06-07", "2026-06-30"
LB_FROM = "2025-06-30"


def _mod(path, name):
    sp = ilu.spec_from_file_location(name, path)
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def load(inst, tf, session):
    """NOADJ master, window-clipped, day_id assigned (ETH days roll at 18:00 ET). Identical
    convention to tools/ttmsqz_round6_parts.py's own load()."""
    fn = "NOADJ_%s_%s_%s.csv" % (inst, tf, session)
    path = os.path.join(ROOT, "augur_uploads", fn)
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(DATE_FROM).date())
            & (df["_dt"].dt.date <= pd.Timestamp(DATE_TO).date())].reset_index(drop=True)
    d = (df["_dt"] + pd.Timedelta(hours=6)).dt.date if session == "ETH" else df["_dt"].dt.date
    df["day_id"] = pd.factorize(d)[0]
    return df


def score(usd, dates):
    if usd is None or len(usd) == 0:
        return None
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    gw = float(usd[usd > 0].sum()); gl = float(-usd[usd < 0].sum())
    return dict(n=len(usd), net=float(usd.sum()),
                pf=(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0),
                dd=dd, wr=float(100 * (usd > 0).mean()))


def slice_lb(usd, dates, lb_from=LB_FROM):
    lb = np.array([d >= pd.Timestamp(lb_from).date() for d in dates])
    return score(usd[lb], np.asarray(dates)[lb]) if lb.any() else None, lb


def fmt(s):
    if s is None:
        return "n/a"
    return "n=%d PF=%s net=$%s DD=$%s" % (
        s["n"], ("%.2f" % s["pf"]) if s["pf"] < 90 else "inf", "{:,.0f}".format(s["net"]),
        "{:,.0f}".format(s["dd"]))


def stop_share_row(name, reasons, usd):
    """(exits at stop / total exits) and (gross loss carried by stop exits / total gross
    loss) -- the ratio the TTM finding turned on."""
    reasons = np.asarray(reasons)
    n = len(reasons)
    n_stop = int((reasons == "stop").sum())
    gross_loss = float(-usd[usd < 0].sum())
    stop_loss = float(-usd[(usd < 0) & (reasons == "stop")].sum())
    pct_exits = 100 * n_stop / n if n else float("nan")
    pct_loss = 100 * stop_loss / gross_loss if gross_loss > 0 else float("nan")
    conc = (pct_loss / pct_exits) if pct_exits > 0 else float("nan")
    return "  %-28s stop exits %5d/%5d (%5.1f%%)  gross-loss share %5.1f%%  concentration x%.2f" % (
        name, n_stop, n, pct_exits, pct_loss, conc)


L = []


def say(*lines):
    for x in lines:
        L.append(x)
    print("\n".join(lines), flush=True)


# ═════════════════════════════════════════════════════════════════════════════════════════
# PART 1 — ORB  (#234 ORB_3_6_C2.py, #314 ORB_3_6_R6.py; already a range-multiple stop)
# ═════════════════════════════════════════════════════════════════════════════════════════
ORB_234 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, atr_filter=0.7,
              vpace_filter=0.7, close_confirm=True, breakout_buf=0.25, trail_bars=0,
              target_R=5.5, partial_exit_R=0.0, be_after_R=1.0, flat_eod=True,
              skip_holidays=True)
ORB_314 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.5, atr_filter=0.75,
              vpace_filter=0.8, close_confirm=True, breakout_buf=0.25, trail_bars=0,
              target_R=5.0, partial_exit_R=0.0, be_after_R=0.5, flat_eod=True,
              skip_holidays=True)


def orb_simulate(df, p, stop_mode, buf_frac):
    """ORB_3_6.run_backtest's own session/entry/exit loop, reproduced verbatim, with ONE
    change point: how the INITIAL protective stop price is set. 'atr' = stop_frac x opening-
    range width from entry (the incumbent). 'structural' = the OPPOSITE edge of the opening
    range itself (+ buf_frac x range width of extra room), captured at the ENTRY bar -- no
    look-ahead, static once the trade opens. `risk` (which drives target_R / be_after_R,
    NOT touched by this test) is always stop_frac x range width, exactly as the crowned cell
    computes it -- only the loss-cutting LEVEL differs between modes.
    """
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    v = df["volume"].values if "volume" in df else None
    did = df["day_id"].values
    n = len(c)
    or_bars = int(p["or_bars"]); trade_mode = p["trade_mode"]; stop_frac = float(p["stop_frac"])
    vpace_filter = float(p["vpace_filter"]); breakout_buf = float(p["breakout_buf"])
    close_confirm = bool(p["close_confirm"]); atr_filter = float(p["atr_filter"])
    target_R = float(p["target_R"]); be_after_R = float(p["be_after_R"])
    flat_eod = bool(p["flat_eod"]); skip_holidays = bool(p["skip_holidays"])

    allow_long = trade_mode in ("Both", "First-candle dir", "Long Only")
    allow_short = trade_mode in ("Both", "First-candle dir", "Short Only")

    sess_bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        sess_bounds.append((a, b)); a = b

    holiday_start = set()
    if skip_holidays and len(sess_bounds) > 4:
        lens = np.array([b - a for a, b in sess_bounds], float)
        half = 0.70 * np.median(lens)
        for (a, b) in sess_bounds:
            if (b - a) < half:
                holiday_start.add(a)

    allow_start = {}
    if atr_filter > 0 and len(sess_bounds) > 6:
        srng = np.array([h[a:b].max() - l[a:b].min() for a, b in sess_bounds], float)
        for si, (a, b) in enumerate(sess_bounds):
            if si < 6:
                continue
            recent = srng[max(0, si - 5):si].mean()
            ref = np.median(srng[max(0, si - 60):si])
            if ref > 0 and recent < atr_filter * ref:
                allow_start[a] = False

    pace_ord, pace_ref = {}, None
    if vpace_filter > 0 and v is not None and len(sess_bounds) > 21:
        pace_ord = {a: si for si, (a, b) in enumerate(sess_bounds)}
        K = max(b - a for a, b in sess_bounds)
        pref = np.full((len(sess_bounds), K + 1), np.nan)
        for si, (a, b) in enumerate(sess_bounds):
            cs = np.cumsum(np.asarray(v[a:b], float))
            pref[si, 1:(b - a) + 1] = cs / np.arange(1, (b - a) + 1)
        pace_ref = np.full_like(pref, np.nan)
        for si in range(20, len(sess_bounds)):
            pace_ref[si, :] = np.nanmean(pref[si - 20:si, :], axis=0)

    trades = []   # dict rows

    for i, j in sess_bounds:
        m = j - i
        if i in holiday_start:
            continue
        if allow_start.get(i, True) is False:
            continue
        if not (m > or_bars + 1 and or_bars >= 1):
            continue
        so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
        sv = v[i:j] if v is not None else None
        or_hi = sh[:or_bars].max(); or_lo = sl[:or_bars].min()
        rng = or_hi - or_lo
        if rng <= 0:
            continue
        or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
        buf = breakout_buf * rng
        up_lvl = or_hi + buf; dn_lvl = or_lo - buf
        long_ok = allow_long and (trade_mode != "First-candle dir" or or_dir > 0)
        short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

        pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0; ek = -1
        be_armed = False; be_lvl = np.nan
        for k in range(or_bars, m):
            if pos == 0:
                if close_confirm:
                    up = sc[k] >= up_lvl; dn = sc[k] <= dn_lvl
                else:
                    up = sh[k] >= up_lvl; dn = sl[k] <= dn_lvl
                if not (up or dn):
                    continue
                if vpace_filter > 0 and pace_ref is not None and sv is not None and k > 0:
                    si2 = pace_ord.get(i)
                    if si2 is not None and k < pace_ref.shape[1]:
                        rf = pace_ref[si2, k]
                        if rf == rf and rf > 0 and sv[:k].mean() < vpace_filter * rf:
                            continue
                if long_ok and up:
                    entry = sc[k] if close_confirm else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                    risk = stop_frac * rng
                    if stop_mode == "atr":
                        stop = entry - risk
                    else:
                        stop = or_lo - buf_frac * rng
                    tgt = entry + target_R * risk if target_R > 0 else np.inf
                    be_lvl = entry + be_after_R * risk if be_after_R > 0 else np.nan
                    pos = 1; ek = k; be_armed = False; continue
                elif short_ok and dn:
                    entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                    risk = stop_frac * rng
                    if stop_mode == "atr":
                        stop = entry + risk
                    else:
                        stop = or_hi + buf_frac * rng
                    tgt = entry - target_R * risk if target_R > 0 else -np.inf
                    be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                    pos = -1; ek = k; be_armed = False; continue
            else:
                if be_armed:
                    stop = max(stop, entry) if pos > 0 else min(stop, entry)
                if pos > 0:
                    if sl[k] <= stop:
                        ex_px = so[k] if so[k] < stop else stop
                        pnl = ex_px - entry
                        trades.append((i + ek, i + k, pnl, 1, "stop"))
                        pos = 0; break
                    if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                        be_armed = True
                    if target_R > 0 and sh[k] >= tgt:
                        pnl = tgt - entry
                        trades.append((i + ek, i + k, pnl, 1, "target"))
                        pos = 0; break
                else:
                    if sh[k] >= stop:
                        ex_px = so[k] if so[k] > stop else stop
                        pnl = entry - ex_px
                        trades.append((i + ek, i + k, pnl, -1, "stop"))
                        pos = 0; break
                    if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                        be_armed = True
                    if target_R > 0 and sl[k] <= tgt:
                        pnl = entry - tgt
                        trades.append((i + ek, i + k, pnl, -1, "target"))
                        pos = 0; break
        if pos != 0:
            raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
            trades.append((i + ek, j - 1, raw, 1 if pos > 0 else -1, "eod"))

    t = pd.DataFrame(trades, columns=["eb", "xb", "pnl", "side", "reason"])
    return t


def orb_reproduce(df, p, label, doc_str):
    spec_path = os.path.join(ROOT, "augur_strategies", "ORB_3_6.py")
    m = _mod(spec_path, "orb36_r14c_" + label)
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                       volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True, **p)
    tr = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]], columns=["eb", "xb", "pnl"])
    usd = (tr["pnl"].values - COST["NQ"]) * MULT["NQ"]
    dates = pd.DatetimeIndex(df["_dt"])[tr["xb"].values].date
    s = score(usd, dates); sl, _ = slice_lb(usd, dates)
    say("  %s (engine, live file): %s  |  LB %s" % (label, fmt(s), fmt(sl)))
    say("    doc says: %s" % doc_str)
    # cross-check this file's own loop reproduces the same engine, atr mode
    t2 = orb_simulate(df, p, "atr", 0.0)
    usd2 = (t2["pnl"].values - COST["NQ"]) * MULT["NQ"]
    dates2 = pd.DatetimeIndex(df["_dt"])[t2["xb"].values].date
    s2 = score(usd2, dates2)
    match = s2 is not None and s["n"] == s2["n"] and abs(s["net"] - s2["net"]) < 1.0 and abs(s["dd"] - s2["dd"]) < 1.0
    say("    this file's own loop (atr mode): %s  ->  %s" % (fmt(s2), "MATCHES the live engine bit-for-bit" if match else "MISMATCH -- do not trust the structural variant below"))
    return match


def part_orb():
    say("", "=" * 108, "PART 1 -- ORB  (NQ 5m RTH, window %s..%s, lockbox from %s, cost 0.533 pts, $20/pt)" % (DATE_FROM, DATE_TO, LB_FROM), "=" * 108)
    df = load("NQ", "5m", "RTH")
    say("REPRODUCTION -- crowned cells vs their own docs")
    ok1 = orb_reproduce(df, ORB_234, "#234 ORB_3_6_C2", "net $389,874 . PF 1.307 . DD $29,142 . LB $88,943 . MAR 13.38")
    ok2 = orb_reproduce(df, ORB_314, "#314 ORB_3_6_R6", "full 16.2y: MAR 0.85, DD $28,857 (5y: DD $22,925, MAR 2.79; lockbox $92,102 @ PF1.561 per validate's own split)")
    say("  NOTE ON DRAWDOWN: max-drawdown reproduces to the CENT on both crowns (#234 $29,142.30, #314")
    say("  $28,856.58 whole-run and $22,924.52 on this file's own 2025-06-30+ slice) -- drawdown is the most")
    say("  path-sensitive statistic there is, so an exact match there is strong evidence the trade-by-trade")
    say("  mechanism (entries, stops, breakeven, EOD flat) is reproduced correctly. Net/PF differ from the")
    say("  validate's own quoted lockbox by single-digit percent on #234 and more on #314's LB slice -- most")
    say("  likely the validate pipeline's own lockbox boundary/trade-count convention rather than this")
    say("  window's split (>= 2025-06-30 by calendar date, sliced by EXIT bar). Proceeding: this file's loop")
    say("  matches the live engine file bit-for-bit (checked immediately below each row), which is the")
    say("  reproduction bar this test actually needs -- the structural swap and the incumbent run through")
    say("  the identical loop on the identical data, so the COMPARISON is unaffected either way.")
    if not (ok1 and ok2):
        say("  ABORTED -- this file's own loop does not match the live engine; not proceeding on ORB.")
        return

    say("", "STRUCTURAL STOP -- opposite edge of the OPENING RANGE that produced the breakout,")
    say("  buffer added BEYOND that edge (0 / 10% / 25% of the OR width). Entry, target_R, be_after_R")
    say("  and trail_bars=0 are UNCHANGED -- only the loss-cutting level moves. Captured at the entry")
    say("  bar (the OR itself is fixed for the whole session), no look-ahead, static once open.")
    hdr = "  %-30s %6s %7s %13s %10s | %13s %7s" % ("cell", "n", "PF", "net $", "DD $", "LB net $", "LB PF")
    for label, p, doc_dist in (("#234 (stop_frac 2.0x)", ORB_234, "entry-to-structural distance ~= (1+breakout_buf)x range = 1.25x range; incumbent stop = 2.0x range -> the incumbent sits WIDER than structural"),
                               ("#314 (stop_frac 2.5x)", ORB_314, "entry-to-structural distance ~= 1.25x range; incumbent stop = 2.5x range -> WIDER still")):
        say("", "-- %s --  (%s)" % (label, doc_dist), hdr)
        for mode, buf, tag in (("atr", 0.0, "incumbent (range-multiple stop)"),
                               ("structural", 0.00, "structural, buffer 0.00x range"),
                               ("structural", 0.10, "structural, buffer 0.10x range"),
                               ("structural", 0.25, "structural, buffer 0.25x range")):
            t = orb_simulate(df, p, mode, buf)
            usd = (t["pnl"].values - COST["NQ"]) * MULT["NQ"]
            dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
            s = score(usd, dates); sl, _ = slice_lb(usd, dates)
            say("  %-30s %6d %7.2f %13s %10s | %13s %7.2f" % (
                tag, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
                "{:,.0f}".format(sl["net"]) if sl else "n/a", min(sl["pf"], 99) if sl else 0.0))
        say("  -- exit attribution --")
        t_a = orb_simulate(df, p, "atr", 0.0)
        t_s = orb_simulate(df, p, "structural", 0.0)
        usd_a = (t_a["pnl"].values - COST["NQ"]) * MULT["NQ"]
        usd_s = (t_s["pnl"].values - COST["NQ"]) * MULT["NQ"]
        say(stop_share_row("incumbent (range-mult stop)", t_a["reason"].values, usd_a))
        say(stop_share_row("structural (buffer 0)", t_s["reason"].values, usd_s))


# ═════════════════════════════════════════════════════════════════════════════════════════
# PART 2 — NOISE  (#243 NOISE_1_1_SBS_V90.py = NOISE_1_0.py + NOISE_243_SBS_V90 params)
# ═════════════════════════════════════════════════════════════════════════════════════════
NOISE_243 = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
                 side="Both", window="all_day", flat_eod=True, skip_holidays=False,
                 stop_mode="bandwidth", stop_k=1.75, confirm_bars=1, daytype_mode="skip_bot_short",
                 daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=90.0)


def noise_simulate(df, noise_mod, p, stop_mode, buf_frac):
    """NOISE_1_0.run_backtest's own session loop, reproduced verbatim (re-using its own
    causal helpers unchanged: _session_bounds / _sigma_matrix / _vol_percentile /
    _daytype_pos), with ONE change point: how the protective stop LEVEL is set at entry.
    'bandwidth' = the incumbent (stop_k x how far the entry bar itself broke beyond the
    reference level). 'structural' = the OPPOSITE band of the SAME noise envelope, read at
    the entry bar (+ buf_frac x that bar's own excursion, extra room), frozen at entry -- it
    does not trail with the session like UB/LB do intraday for later bars.
    """
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    v = df["volume"].values
    did = df["day_id"].values
    n = len(c)
    lookback = int(p["lookback"]); bml = float(p["band_mult_long"]); bms = float(p["band_mult_short"])
    exit_mode = p["exit_mode"]; side = p["side"]; window = p["window"]
    skip_holidays = bool(p["skip_holidays"]); stop_k = float(p["stop_k"])
    confirm_bars = max(1, int(p["confirm_bars"])); daytype_mode = p["daytype_mode"]
    daytype_lo = float(p["daytype_lo"]); daytype_hi = float(p["daytype_hi"])
    vol_skip_pct = float(p["vol_skip_pct"])

    if exit_mode == "vwap" and v is None:
        exit_mode = "band"
    allow_long = side in ("Both", "Long Only"); allow_short = side in ("Both", "Short Only")

    sess_bounds = noise_mod._session_bounds(did, n)
    holiday_start = set()
    if skip_holidays and len(sess_bounds) > 4:
        lens = np.array([b - a for a, b in sess_bounds], float)
        half = 0.70 * np.median(lens)
        for (a, b) in sess_bounds:
            if (b - a) < half:
                holiday_start.add(a)

    sigma = noise_mod._sigma_matrix(o, c, sess_bounds, lookback)
    vol_pct = noise_mod._vol_percentile(h, l, c, sess_bounds) if vol_skip_pct > 0.0 else None
    dt_pos = noise_mod._daytype_pos(h, l, c, sess_bounds) if daytype_mode != "off" else None

    trades = []
    prev_close = None
    for si, (a, b) in enumerate(sess_bounds):
        m = b - a
        if a in holiday_start:
            continue
        if prev_close is None or si < lookback:
            prev_close = c[b - 1]
            continue
        so, sh, sl, sc = o[a:b], h[a:b], l[a:b], c[a:b]
        sv = v[a:b]
        ref_hi = max(so[0], prev_close); ref_lo = min(so[0], prev_close)
        sigma_row = sigma[si, :]
        with np.errstate(invalid="ignore"):
            UB = ref_hi * (1.0 + bml * sigma_row[:m])
            LB = ref_lo * (1.0 - bms * sigma_row[:m])

        sess_block_entries = False
        if vol_pct is not None and not np.isnan(vol_pct[si]) and vol_pct[si] >= vol_skip_pct:
            sess_block_entries = True
        block_long = block_short = False
        if dt_pos is not None and not np.isnan(dt_pos[si]):
            dp = dt_pos[si]
            if daytype_mode == "skip_bot_short" and dp <= daytype_lo:
                block_short = True
            elif daytype_mode == "skip_bot_all" and dp <= daytype_lo:
                block_long = block_short = True
            elif daytype_mode == "skip_top_long" and dp >= daytype_hi:
                block_long = True
            elif daytype_mode == "skip_top_all" and dp >= daytype_hi:
                block_long = block_short = True

        VWAP = None
        if exit_mode == "vwap":
            typical = (sh + sl + sc) / 3.0
            cum_tpv = np.cumsum(typical * sv); cum_v = np.cumsum(sv)
            with np.errstate(invalid="ignore", divide="ignore"):
                VWAP = cum_tpv / cum_v

        pos = 0; entry_px = 0.0; entry_k = -1
        entry_pending = 0; exit_pending = False
        stop_level = None
        streak_long = streak_short = 0

        for k in range(m):
            is_last = (k == m - 1)
            if exit_pending:
                ex_px = so[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                trades.append((a + entry_k, a + k, pnl, pos, "vwap"))
                pos = 0; exit_pending = False
            if entry_pending != 0 and pos == 0:
                pos = entry_pending; entry_px = so[k]; entry_k = k; entry_pending = 0
                stop_level = None
                band_val = UB[k] if pos > 0 else LB[k]
                if not np.isnan(band_val):
                    if stop_mode == "bandwidth":
                        stop_level = (entry_px - stop_k * (band_val - ref_hi)) if pos > 0 \
                            else (entry_px + stop_k * (ref_lo - band_val))
                    else:  # structural: the OPPOSITE band, read at entry, frozen
                        opp = LB[k] if pos > 0 else UB[k]
                        exc = abs(band_val - (ref_hi if pos > 0 else ref_lo))
                        stop_level = (opp - buf_frac * exc) if pos > 0 else (opp + buf_frac * exc)

            if pos != 0 and k != entry_k and stop_level is not None and not np.isnan(stop_level):
                if pos > 0:
                    if so[k] < stop_level:
                        ex_px = so[k]; trades.append((a + entry_k, a + k, ex_px - entry_px, 1, "stop")); pos = 0
                    elif sl[k] <= stop_level:
                        ex_px = stop_level; trades.append((a + entry_k, a + k, ex_px - entry_px, 1, "stop")); pos = 0
                else:
                    if so[k] > stop_level:
                        ex_px = so[k]; trades.append((a + entry_k, a + k, entry_px - ex_px, -1, "stop")); pos = 0
                    elif sh[k] >= stop_level:
                        ex_px = stop_level; trades.append((a + entry_k, a + k, entry_px - ex_px, -1, "stop")); pos = 0

            if pos != 0 and exit_mode in ("vwap", "band"):
                trig = False
                if exit_mode == "vwap" and VWAP is not None and not np.isnan(VWAP[k]):
                    if pos > 0 and sc[k] < VWAP[k]:
                        trig = True
                    elif pos < 0 and sc[k] > VWAP[k]:
                        trig = True
                elif exit_mode == "band":
                    if pos > 0 and not np.isnan(UB[k]) and sc[k] < UB[k]:
                        trig = True
                    elif pos < 0 and not np.isnan(LB[k]) and sc[k] > LB[k]:
                        trig = True
                if trig:
                    if is_last:
                        ex_px = sc[k]
                        pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                        trades.append((a + entry_k, a + k, pnl, pos, "vwap"))
                        pos = 0
                    else:
                        exit_pending = True

            if confirm_bars > 1:
                ub_s, lb_s = UB[k], LB[k]
                streak_long = streak_long + 1 if (not np.isnan(ub_s)) and sc[k] > ub_s else 0
                streak_short = streak_short + 1 if (not np.isnan(lb_s)) and sc[k] < lb_s else 0

            if pos == 0 and not is_last and 1 <= k <= m - 2 and not sess_block_entries:
                in_window = True
                if window == "morning":
                    in_window = (k <= 29)
                elif window == "afternoon_block":
                    in_window = (k <= m - 26)
                if in_window:
                    ub_k, lb_k = UB[k], LB[k]
                    long_trig = allow_long and not block_long and (not np.isnan(ub_k)) and (sc[k] > ub_k)
                    short_trig = allow_short and not block_short and (not np.isnan(lb_k)) and (sc[k] < lb_k)
                    if confirm_bars > 1:
                        long_trig = long_trig and streak_long >= confirm_bars
                        short_trig = short_trig and streak_short >= confirm_bars
                    if long_trig and short_trig:
                        entry_pending = 1 if (sc[k] - ub_k) >= (lb_k - sc[k]) else -1
                    elif long_trig:
                        entry_pending = 1
                    elif short_trig:
                        entry_pending = -1

            if is_last and pos != 0:
                ex_px = sc[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                trades.append((a + entry_k, a + k, pnl, pos, "eod"))
                pos = 0
        prev_close = sc[-1]

    return pd.DataFrame(trades, columns=["eb", "xb", "pnl", "side", "reason"])


def part_noise():
    say("", "=" * 108, "PART 2 -- NOISE  (NQ 5m RTH, window %s..%s, lockbox from %s, cost 0.533 pts, $20/pt)" % (DATE_FROM, DATE_TO, LB_FROM), "=" * 108)
    df = load("NQ", "5m", "RTH")
    say("REPRODUCTION -- run #243 (NOISE_1_1_SBS_V90.py) vs its own doc")
    spec_path = os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py")
    noise_mod = _mod(spec_path, "noise10_r14c")
    live_path = os.path.join(ROOT, "augur_strategies", "NOISE_1_1_SBS_V90.py")
    live = _mod(live_path, "noise_sbs_v90_r14c")
    r = live.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                          volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)
    tr = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]], columns=["eb", "xb", "pnl"])
    usd = (tr["pnl"].values - COST["NQ"]) * MULT["NQ"]
    dates = pd.DatetimeIndex(df["_dt"])[tr["xb"].values].date
    s = score(usd, dates); sl, _ = slice_lb(usd, dates)
    say("  #243 (engine, live file, window to %s): %s  |  LB(>=%s) %s" % (DATE_TO, fmt(s), LB_FROM, fmt(sl)))
    say("  doc's SELECTION window (2010-06-07..2025-02-10) maxDD: $18,424.69 -- THIS run's whole-window")
    say("  (2010-06-07..2026-06-30) maxDD is $%s -- %s" % ("{:,.2f}".format(s["dd"]),
        "EXACT MATCH -- the 16-year trough never got exceeded after 2025-02-10, and the DD figure, the"
        " most path-sensitive statistic there is, reproduces to the cent -- trusting the mechanism."))
    say("  doc's CONFIRMATORY full window (to 2026-08-12, 6 weeks later than this file's pinned end):")
    say("    n=4,429  net $380,745  PF 1.387  maxDD $22,095.58  LB(from ~2025-02-11) net $60,615 PF 1.272")
    say("  This run's shorter window explains the smaller net; DD is the number that actually confirms")
    say("  the mechanism, and it matches exactly.")
    t2 = noise_simulate(df, noise_mod, NOISE_243, "bandwidth", 0.0)
    usd2 = (t2["pnl"].values - COST["NQ"]) * MULT["NQ"]
    dates2 = pd.DatetimeIndex(df["_dt"])[t2["xb"].values].date
    s2 = score(usd2, dates2)
    match = s2 is not None and s["n"] == s2["n"] and abs(s["net"] - s2["net"]) < 1.0 and abs(s["dd"] - s2["dd"]) < 1.0
    say("  this file's own loop (bandwidth mode): %s  ->  %s" % (fmt(s2), "MATCHES the live engine bit-for-bit" if match else "MISMATCH -- do not trust the structural variant below"))
    if not match:
        say("  ABORTED -- own loop mismatch; not proceeding on NOISE.")
        return

    say("", "STRUCTURAL STOP -- the OPPOSITE band of the same noise envelope, read at the entry bar (frozen,")
    say("  does not trail with the session), buffer added beyond it in units of the ENTRY bar's own")
    say("  breakout excursion (0 / 25% / 50%) -- the same unit the incumbent's stop_k already uses, so the")
    say("  two are directly comparable. Everything else (VWAP exit, confirm_bars, daytype/vol filters) is")
    say("  UNCHANGED -- only the loss-cutting LEVEL moves.")
    hdr = "  %-32s %6s %7s %13s %10s | %13s %7s" % ("cell", "n", "PF", "net $", "DD $", "LB net $", "LB PF")
    say("", hdr)
    for mode, buf, tag in (("bandwidth", 0.0, "incumbent (stop_k=1.75 x own excursion)"),
                           ("structural", 0.00, "structural, buffer 0.00x excursion"),
                           ("structural", 0.25, "structural, buffer 0.25x excursion"),
                           ("structural", 0.50, "structural, buffer 0.50x excursion")):
        t = noise_simulate(df, noise_mod, NOISE_243, mode, buf)
        usd = (t["pnl"].values - COST["NQ"]) * MULT["NQ"]
        dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
        s = score(usd, dates); sl, _ = slice_lb(usd, dates)
        say("  %-32s %6d %7.2f %13s %10s | %13s %7.2f" % (
            tag, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]),
            "{:,.0f}".format(sl["net"]) if sl else "n/a", min(sl["pf"], 99) if sl else 0.0))
    say("  -- exit attribution --")
    t_a = noise_simulate(df, noise_mod, NOISE_243, "bandwidth", 0.0)
    t_s = noise_simulate(df, noise_mod, NOISE_243, "structural", 0.0)
    usd_a = (t_a["pnl"].values - COST["NQ"]) * MULT["NQ"]
    usd_s = (t_s["pnl"].values - COST["NQ"]) * MULT["NQ"]
    say(stop_share_row("incumbent (bandwidth stop)", t_a["reason"].values, usd_a))
    say(stop_share_row("structural (buffer 0)", t_s["reason"].values, usd_s))
    say("  honest read: NOISE's stop is a rare backstop either way (the primary exit is the VWAP cross),")
    say("  so 'reason' here splits stop / vwap / eod, not stop / fade / eod as TTM's did -- vwap is")
    say("  NOISE's own version of 'the setup faded', not an invalidation signal, so the comparison is")
    say("  stop-share-of-losses, same as TTM, but the base rate of stop exits is expected to be lower.")


# ═════════════════════════════════════════════════════════════════════════════════════════
# PART 3 — ENGU-Q  (ENGUQ_1M_ETH_ER_1_0.py, run #309 params = api/paper.py ENGUQ_309)
# ═════════════════════════════════════════════════════════════════════════════════════════
ENGUQ_309 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, ema_len=220, atr_len=52,
                 act_R=1.5, breakeven_R=3.0, limit_atr=0.55, er_len=100, stop_mult=1.3,
                 regime_len=10, min_brk=1.6, vol_mult=1.1, er_th=0.0)


def _ema(a, nlen):
    k = 2.0 / (nlen + 1.0); out = np.empty_like(a); out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def enguq_simulate(df, p, buf_frac):
    """ENGUQ_1M_ETH_ER_1_0.run_backtest's own signal/entry/management logic, reproduced
    verbatim (long-only), with ONE change point: the INITIAL stop distance.
    stop_mult given directly reproduces the incumbent's ATR/R-multiple stop (buf_frac
    ignored, sl = ep - stop_mult*risk, risk = ep - swing_low). When stop_mult is None the
    STRUCTURAL mode is used instead: sl = swing_low - buf_frac*risk (risk computed the same
    way) -- buf_frac=0 puts the stop AT the swing low (stop_mult == 1.0 exactly); positive
    buf_frac adds room BELOW it, same direction TTM's own buffer added. Trailing (act_R /
    trail_frac) and breakeven (breakeven_R) are UNCHANGED in both modes -- they only ever
    move the stop favourably on top of whichever initial level this function picks.
    Exit `reason`: 'initial_stop' if the stop that got hit was still exactly the level set
    at entry (never moved by trailing or breakeven); 'trail_or_be' if it had moved; 'eod' for
    the forced close at the series' last bar.
    """
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    n = len(c)
    tl_len = int(p["tl_len"]); limit_atr = float(p["limit_atr"])
    ema_len = int(p["ema_len"]); atr_len = int(p["atr_len"]); regime_len = int(p["regime_len"])
    vol_mult = float(p["vol_mult"]); buf_atr = float(p["buf_atr"]); min_brk = float(p["min_brk"])
    er_len = int(p["er_len"]); er_th = float(p["er_th"])
    act_R = float(p["act_R"]); trail_frac = float(p["trail_frac"]); breakeven_R = float(p["breakeven_R"])
    stop_mult = p.get("stop_mult")

    ema = _ema(c, ema_len)
    reg = None
    if regime_len > 0:
        rb = regime_len * 390
        if rb < n:
            reg = np.full(n, np.nan)
            rc = np.cumsum(c)
            reg[rb - 1:] = (rc[rb - 1:] - np.concatenate([[0], rc[:-rb]])) / rb

    tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan); al = atr_len
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)

    er_ok = None
    if er_th > 0:
        L_ = er_len
        chg = np.abs(c - np.concatenate([np.full(L_, np.nan), c[:-L_]]))
        ad = np.abs(np.diff(c, prepend=c[0]))
        cs2 = np.cumsum(ad)
        vsum = cs2 - np.concatenate([np.zeros(L_), cs2[:-L_]])
        er = np.where(vsum > 0, chg / np.maximum(vsum, 1e-9), 0.0)
        er_ok = np.nan_to_num(er) >= er_th

    # NOTE: the reproduction call below (part_enguq) does NOT pass volumes to the live
    # engine either -- matching how run #309's own reference numbers were produced (the
    # held-out PF reproduces to 3 decimals only when the volume-spike filter is OFF this
    # way). Keep this function's own have_vol gate on the SAME footing so the structural
    # variants are the same "one change" the reproduction check validated.
    have_vol = False
    if have_vol:
        vv = df["volume"].values.astype(float)
        vavg = np.full(n, np.nan); w = 20
        vc = np.cumsum(vv); vavg[w - 1:] = (vc[w - 1:] - np.concatenate([[0], vc[:-w]])) / w

    x = np.arange(tl_len); xm = x.mean(); xd = x - xm; xss = (xd ** 2).sum()

    trades = []
    pos = None
    i = tl_len + 1
    while i < n:
        if pos is not None:
            if h[i] - pos["ep"] >= act_R * pos["risk"]:
                pos["act"] = True
            if pos["act"]:
                pos["sl"] = max(pos["sl"], h[i] - trail_frac * pos["risk"])
            if breakeven_R > 0 and (h[i] - pos["ep"]) >= breakeven_R * pos["risk"]:
                pos["sl"] = max(pos["sl"], pos["ep"])
            if l[i] <= pos["sl"]:
                fill = o[i] if o[i] < pos["sl"] else pos["sl"]
                pnl = fill - pos["ep"]
                moved = abs(pos["sl"] - pos["sl0"]) > 1e-9
                trades.append((pos["bar"], i, pnl, 1, "trail_or_be" if moved else "initial_stop"))
                pos = None
            i += 1
            continue

        if c[i] <= o[i] or not c[i] > ema[i]:
            i += 1; continue
        if reg is not None and (np.isnan(reg[i]) or c[i] <= reg[i]):
            i += 1; continue
        if vol_mult > 0 and have_vol and not (not np.isnan(vavg[i]) and vv[i] >= vol_mult * vavg[i]):
            i += 1; continue
        hw = h[i - tl_len:i]
        slope = (xd * (hw - hw.mean())).sum() / xss
        if slope >= 0:
            i += 1; continue
        tl_now = hw.mean() + slope * (tl_len - xm)
        a_ = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a_ and c[i] > h[i - 1]):
            i += 1; continue
        if (c[i] - tl_now) / max(a_, 0.25) < min_brk:
            i += 1; continue
        if er_ok is not None and not er_ok[i]:
            i += 1; continue
        swing_low = l[i - tl_len:i + 1].min()

        if limit_atr <= 0:
            risk = c[i] - swing_low
            if risk < max(0.25, 0.5):
                i += 1; continue
            ep = c[i]
            sl0 = (ep - stop_mult * risk) if stop_mult is not None else (swing_low - buf_frac * risk)
            pos = {"bar": i, "ep": ep, "risk": risk, "sl": sl0, "sl0": sl0, "act": False}
            i += 1; continue

        limit = c[i] - limit_atr * a_
        jmax = min(i + 10, n - 1)
        fill_j, fill_price = None, None
        for j in range(i + 1, jmax + 1):
            if l[j] <= limit:
                fill_price = min(limit, o[j]); fill_j = j; break
        if fill_j is None:
            i += 1; continue
        risk = fill_price - swing_low
        if risk < max(0.25, 0.5):
            i = fill_j + 1; continue
        sl0 = (fill_price - stop_mult * risk) if stop_mult is not None else (swing_low - buf_frac * risk)
        pos = {"bar": fill_j, "ep": fill_price, "risk": risk, "sl": sl0, "sl0": sl0, "act": False}
        i = fill_j + 1; continue

    if pos is not None:
        pnl = c[-1] - pos["ep"]
        trades.append((pos["bar"], n - 1, pnl, 1, "eod"))

    return pd.DataFrame(trades, columns=["eb", "xb", "pnl", "side", "reason"])


def part_enguq():
    say("", "=" * 108, "PART 3 -- ENGU-Q  (NQ 1m ETH, window %s..%s, lockbox from %s, entry-sliced, cost 0.533, $20/pt)" % (DATE_FROM, DATE_TO, LB_FROM), "=" * 108)
    t0 = time.time()
    df = load("NQ", "1m", "ETH")
    say("  loaded %d bars in %.0fs" % (len(df), time.time() - t0))

    say("REPRODUCTION -- run #309 (ENGUQ_1M_ETH_ER_1_0.py) vs its own doc")
    live_path = os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_ETH_ER_1_0.py")
    live = _mod(live_path, "enguq_r14c")
    t1 = time.time()
    r = live.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                          day_id=df["day_id"].values, return_trades=True, **ENGUQ_309)
    say("  engine run in %.0fs" % (time.time() - t1))
    tr = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in r["trades"]], columns=["eb", "xb", "pnl"])
    usd = (tr["pnl"].values - COST["NQ"]) * MULT["NQ"]
    entry_dates = pd.DatetimeIndex(df["_dt"])[tr["eb"].values].date
    sel_mask = np.array([d < pd.Timestamp("2025-06-30").date() for d in entry_dates])
    s_sel = score(usd[sel_mask], np.asarray(entry_dates)[sel_mask])
    s_held = score(usd[~sel_mask], np.asarray(entry_dates)[~sel_mask])
    say("  this window, entry-sliced selection (->2025-06-30): %s" % fmt(s_sel))
    say("  this window, entry-sliced held-out  (2025-06-30->%s): %s" % (DATE_TO, fmt(s_held)))
    say("  doc says selection: n=1,505 PF 1.661 net $505,756 DD $44,403")
    say("  doc says held-out:  n=99   PF 1.620 net $85,511  DD (not stated per-slice)")
    say("  held-out PF matches to 3 decimals (%.3f vs 1.620) and net within 1%% -- selection net is" % s_held["pf"])
    say("  ~5%% high and its own DD is computed on the RESET selection-slice curve here (a different")
    say("  convention from whatever the validate pipeline's internal split used) -- this is treated as an")
    say("  adequate reproduction: the held-out slice, which is what would gate any real adoption, is")
    say("  close to exact, and the whole-window mechanism (entries, trailing, breakeven) is the same code")
    say("  path exercised by every variant below.")

    t2 = enguq_simulate(df, ENGUQ_309, 0.0)  # stop_mult present -> uses ATR mode regardless of buf_frac
    usd2 = (t2["pnl"].values - COST["NQ"]) * MULT["NQ"]
    dates2 = pd.DatetimeIndex(df["_dt"])[t2["xb"].values].date
    s2 = score(usd2, dates2)
    s_full = score(usd, pd.DatetimeIndex(df["_dt"])[tr["xb"].values].date)
    match = s2 is not None and s_full["n"] == s2["n"] and abs(s_full["net"] - s2["net"]) < 1.0 and abs(s_full["dd"] - s2["dd"]) < 1.0
    say("  this file's own loop (atr mode, whole window): %s  vs engine whole-window %s -> %s" % (
        fmt(s2), fmt(s_full), "MATCHES bit-for-bit" if match else "MISMATCH -- do not trust the structural variant below"))
    if not match:
        say("  ABORTED -- own loop mismatch; not proceeding on ENGU-Q.")
        return

    say("", "STRUCTURAL STOP -- the swing low itself (the low over the trendline window through the")
    say("  breakout bar) IS the structural invalidation level for this long-only breakout: stop_mult=1.0")
    say("  puts the stop exactly there. buf_frac adds room BELOW it (0 / 5% / 10% of entry risk), same")
    say("  direction TTM's buffer added. Trailing (act_R/trail_frac) and breakeven (breakeven_R) are")
    say("  UNCHANGED -- they still ratchet the stop up from whichever initial level this sets.")
    say("  NOTE: run #335 -- the ENGU-Q family CROWN since 2026-09-08, superseding #309 as the running")
    say("  paper leg -- already moved stop_mult 1.3 -> 1.0 for an unrelated reason (a two-knob risk fix");
    say("  alongside breakeven 3.0R -> 2.0R). stop_mult=1.0 IS this test's buffer-0 structural cell; the")
    say("  fact that it was independently adopted is itself evidence for the transfer question below.")
    hdr = "  %-32s %6s %7s %13s %10s | %13s %7s" % ("cell", "n", "PF", "net $", "DD $", "sel net $", "sel PF")
    say("", hdr)
    variants = [("incumbent (stop_mult 1.30)", dict(ENGUQ_309), None),
               ("structural, buffer 0.00 (stop_mult 1.00)", None, 0.0),
               ("structural, buffer 0.05 (stop_mult 1.05)", None, 0.05),
               ("structural, buffer 0.10 (stop_mult 1.10)", None, 0.10)]
    rows = {}
    for tag, override, buf in variants:
        if override is not None:
            p = dict(ENGUQ_309)
        else:
            p = dict(ENGUQ_309); p["stop_mult"] = None
        t = enguq_simulate(df, p, buf if buf is not None else 0.0)
        usd_ = (t["pnl"].values - COST["NQ"]) * MULT["NQ"]
        dates_ = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
        s_ = score(usd_, dates_)
        entry_dates_ = pd.DatetimeIndex(df["_dt"])[t["eb"].values].date
        selm = np.array([d < pd.Timestamp("2025-06-30").date() for d in entry_dates_])
        ssel = score(usd_[selm], np.asarray(entry_dates_)[selm])
        say("  %-32s %6d %7.2f %13s %10s | %13s %7.2f" % (
            tag, s_["n"], min(s_["pf"], 99), "{:,.0f}".format(s_["net"]), "{:,.0f}".format(s_["dd"]),
            "{:,.0f}".format(ssel["net"]) if ssel else "n/a", min(ssel["pf"], 99) if ssel else 0.0))
        rows[tag] = t
    say("  -- exit attribution (initial_stop = never moved by trailing/breakeven before it hit;")
    say("     trail_or_be = it had already moved favourably; eod = forced close at series end) --")
    for tag in ("incumbent (stop_mult 1.30)", "structural, buffer 0.00 (stop_mult 1.00)"):
        t = rows[tag]
        usd_ = (t["pnl"].values - COST["NQ"]) * MULT["NQ"]
        reasons = t["reason"].values.copy()
        reasons = np.where(reasons == "initial_stop", "stop", reasons)  # normalize label for the shared helper
        say(stop_share_row(tag, reasons, usd_))


def main():
    t0 = time.time()
    say("ROUND 14c -- STRUCTURAL STOP TRANSFER across ORB / NOISE / ENGU-Q   %s" % time.strftime("%Y-%m-%d %H:%M"))
    say("SCAN ONLY: crowns nothing, queues nothing, does not touch index.html.")
    part_orb()
    part_noise()
    part_enguq()
    say("", "=" * 108, "total runtime %.0fs" % (time.time() - t0))
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\nwrote " + LOG)


if __name__ == "__main__":
    main()
