"""
TTM SQUEEZE ROUND 12a - SQUEEZE PRO, the three-level compression grade AS THE SIGNAL.

Carter's classic squeeze is one boolean: Bollinger(20, 2.0) inside Keltner(20, 1.5 ATR).
Squeeze Pro (the version he shipped after the original) grades the same coil into three
levels by the Keltner multiple: LOW compression at kc 2.0 (widest channel, easiest to sit
inside), MID at kc 1.5 (the classic squeeze), HIGH at kc 1.0 (narrowest channel, hardest to
sit inside - "wound tight"). Because a narrower channel is a STRICTER condition, the levels
nest: HIGH implies MID implies LOW at every bar (verified numerically below, not assumed).

A previous round (8) used a continuous compression RATIO as a higher-timeframe GATE. Nobody
has tested the graded, discrete Pro levels as the SIGNAL itself - which bar fires, which
fires get taken, and how big. This round does that, on top of the one durable finding of the
family (round 4): keep the hourly squeeze-on verification ON for every cell here.

FOUR THINGS TESTED, ES 30m RTH (the crown's own tape) and NQ 15m RTH:
  1. FIRE ON RELEASE FROM HIGH instead of the classic MID release - a new entry rule. Needs a
     custom engine because TTMSQZ_3_0 does not expose separate Keltner multiples for the base
     fire vs. the hourly gate (one kc_mult knob drives both) - see run_pro_entry() below,
     which is TTMSQZ_3_0.run_backtest's execution loop unchanged, with only the entry
     squeeze-on/fire construction decoupled from the gate's. The gate stays classic (kc 1.5,
     60-minute, sq_on) in every row of this file.
  2. REACHED HIGH AT ANY POINT during the coil, then fire on the classic MID release - a
     post-hoc SELECTION on the incumbent's own classic trades (same method round 6/8 used:
     split an existing trade list, retune nothing).
  3. LEVEL AT THE FIRE (the compression grade of the last bar still inside the squeeze,
     i.e. one bar before the release) as a SELECTION (only take fires wound to HIGH) and,
     separately, as a 1.5x SIZE TILT keeping every trade - the shape round 8 validated.
  4. DURATION at HIGH before the fire (consecutive bars at HIGH ending on the last squeezed
     bar), bucketed 0 / 1-2 / 3+, as a selection and a tilt (1.5x when duration >= 2).

RULES: pinned window and house costs exactly as tools/ttmsqz_round6_parts.py sets them
(DATE_FROM/LB_FROM/DATE_TO, COST, MULT). Lockbox = trades exiting on/after LB_FROM, reported
separately, never tuned on. No look-ahead: every decision uses bars closed as of that bar;
entries fill at the next bar's open (unchanged from TTMSQZ_3_0). The hourly gate state comes
from the last COMPLETE hourly group as of the decision bar, built with tools/
ttmsqz_round8_crown.py::compression_ratio's exact construction (imported here as
ttm3._htf_gate, the same function TTMSQZ_3_0 itself calls - not reinvented).

THE INCUMBENT (quoted, not re-derived, then cross-checked by re-running it through this
file's own engine as a sanity check): ES 30m RTH crown - kc_mult 1.5, stop_atr 1.5,
eod_cutoff 1, gate_len 20, gate_tf_min 60, gate_mode sq_on, entry_fill open, exit_mode fade,
fade_bars 1, length 20, bb_mult 2.0, min_sq_bars 1 - 359 trades, $51,709, PF 2.12, DD $3,740,
lockbox $4,992 at PF 2.22.

This is a SCAN. Nothing here is crowned, queued to validate, or pushed to index.html.

Usage:  python tools/ttmsqz_r12a_squeeze_pro.py
Output: tools/data/ttmsqz_r12a_squeeze_pro.txt
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
ttm1 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"), "ttm1")
ttm3 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "ttm3")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r12a_squeeze_pro.txt")

CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
             exit_mode="fade", fade_bars=1, stop_atr=1.5, eod_cutoff=1,
             gate_tf_min=60, gate_mode="sq_on", gate_len=20, gate_bars=0,
             gate_ratio=1.0, gate_fired_k=3, direction="both")

INCUMBENT = dict(n=359, net=51709.0, pf=2.12, dd=3740.0, lb=4992.0, lbpf=2.22)

MARKETS = [("ES", "30m"), ("NQ", "15m")]


# ---------------------------------------------------------------------------
# SQUEEZE PRO levels: three kc multiples on the same BB(20,2.0), same base bars.
# ---------------------------------------------------------------------------

def pro_levels(h, l, c, length=20, bb_mult=2.0):
    """(level 0-3, mom, sq_low, sq_mid, sq_high). Level 3=HIGH(kc1.0) 2=MID(kc1.5)
    1=LOW(kc2.0) 0=none. mom/atr are independent of kc_mult (verified below), so one
    momentum series serves all three; only the sq_on boolean differs by kc."""
    sq_low, mom, _ = ttm1.squeeze_indicators(h, l, c, length, bb_mult, 2.0)
    sq_mid, mom2, _ = ttm1.squeeze_indicators(h, l, c, length, bb_mult, 1.5)
    sq_high, mom3, _ = ttm1.squeeze_indicators(h, l, c, length, bb_mult, 1.0)
    assert np.allclose(np.nan_to_num(mom), np.nan_to_num(mom2)) and \
           np.allclose(np.nan_to_num(mom), np.nan_to_num(mom3)), "mom depends on kc_mult?!"
    level = np.where(sq_high, 3, np.where(sq_mid, 2, np.where(sq_low, 1, 0)))
    return level, mom, sq_low, sq_mid, sq_high


def run_len_of(mask):
    n = len(mask)
    run = np.zeros(n, int)
    for i in range(1, n):
        run[i] = run[i - 1] + 1 if mask[i] else 0
    return run


def reached_flag(sq_mid, sq_high):
    """True at bar u if, within the CURRENT consecutive sq_mid run (through u), sq_high was
    True at any bar so far. False once the run breaks."""
    n = len(sq_mid)
    r = np.zeros(n, bool)
    for i in range(n):
        if sq_mid[i]:
            r[i] = bool(sq_high[i]) or (i > 0 and sq_mid[i - 1] and r[i - 1])
    return r


def check_nesting(sq_low, sq_mid, sq_high):
    """HIGH must imply MID must imply LOW at every bar - the premise the whole round rests
    on. Returns (ok, violations)."""
    v1 = int((sq_high & ~sq_mid).sum())
    v2 = int((sq_mid & ~sq_low).sum())
    return (v1 == 0 and v2 == 0), v1, v2


# ---------------------------------------------------------------------------
# Custom engine for test 1: entry fire decoupled from the hourly gate's kc_mult.
# TTMSQZ_3_0.run_backtest's execution loop, UNCHANGED, with only the entry
# squeeze-on/fire construction computed at entry_kc while the gate keeps gate_kc.
# ---------------------------------------------------------------------------

def run_pro_entry(df, entry_kc, gate_kc=1.5, length=20, bb_mult=2.0, min_sq_bars=1,
                   entry_fill="open", exit_mode="fade", fade_bars=1, stop_atr=1.5,
                   eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20,
                   gate_bars=0, gate_ratio=1.0, gate_fired_k=3, direction="both"):
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float); c = df["close"].values.astype(float)
    did = df["day_id"].values; index = df["_dt"]
    n = len(c)
    length = int(length); min_sq_bars = int(min_sq_bars); fade_bars = int(fade_bars)
    eod_cutoff = int(eod_cutoff); bb_mult = float(bb_mult)
    entry_kc = float(entry_kc); stop_atr = float(stop_atr)

    sq_on, mom, atr = ttm1.squeeze_indicators(h, l, c, length, bb_mult, entry_kc)
    run_len = run_len_of(sq_on)
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= min_sq_bars)
    warm = length * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()

    gate_long, gate_short = ttm3._htf_gate(h, l, c, did, index, gate_bars, gate_tf_min,
                                            gate_len, bb_mult, gate_kc, gate_mode,
                                            gate_fired_k, float(gate_ratio))
    if direction != "both":
        if direction == "long":
            gate_short = np.zeros(n, bool)
        else:
            gate_long = np.zeros(n, bool)

    last_bar = ttm3._session_last_bar(did, n)

    pos = 0; entry_px = 0.0; entry_bar = -1; stop_px = None
    pending = None
    fade_cnt = 0
    pnl_list, trade_log = [], []

    def _book(exit_i, px, side, ep, eb):
        p = (px - ep) if side > 0 else (ep - px)
        pnl_list.append(p)
        trade_log.append((int(eb), int(exit_i), float(p), int(side), float(ep), float(px)))

    for u in range(warm, n):
        eod = u == last_bar[u]
        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
                pending = None
            elif kind == "mkt":
                if pos == 0:
                    side = pending[1]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar); pos = 0; stop_px = None
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
                    pos = side; entry_px = fill; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar); pos = 0; stop_px = None
                    pending = None
                elif u >= expiry or eod:
                    pending = None
        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = None
        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
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

    if not pnl_list:
        return None
    return dict(trades=trade_log)


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------

def to_df(r, inst, df):
    if not r or not r.get("trades"):
        return None
    t = pd.DataFrame(r["trades"], columns=["eb", "xb", "pnl", "side", "epx", "xpx"])
    t["usd"] = (t["pnl"].values - COST[inst]) * MULT[inst]
    t["date"] = pd.DatetimeIndex(df["_dt"])[t["xb"].values].tz_localize(None).normalize()
    t["fireb"] = t["eb"].values - 1          # bar the fire was detected on
    t["lastsq"] = np.clip(t["eb"].values - 2, 0, len(df) - 1)   # last bar still inside the coil
    return t


def score_row(usd, dates):
    if len(usd) == 0:
        return None
    s = r6.score(usd, dates)
    return s


def lb_split(t):
    lb = t[t["date"] >= pd.Timestamp(LB_FROM)]
    return lb


def perm_p(usd, mask, n_iter=5000, seed=42):
    if not mask.any() or (~mask).any() is False or (~mask).sum() == 0:
        return float("nan")
    rng = np.random.default_rng(seed)
    obs = float(usd[mask].mean() - usd[~mask].mean())
    lab = mask.copy()
    hits = 0
    for _ in range(n_iter):
        rng.shuffle(lab)
        if abs(float(usd[lab].mean() - usd[~lab].mean())) >= abs(obs):
            hits += 1
    return hits / n_iter


H = "  %-52s %6s %7s %12s %10s %12s %7s"
HDR = H % ("cell", "n", "PF", "net $", "DD $", "lockbox $", "LB PF")


def _fmt(v, money=False, pf=False):
    if v is None or (isinstance(v, float) and v != v):
        return "n/a"
    if money:
        return "{:,.0f}".format(v)
    if pf:
        return "%.2f" % min(v, 99)
    return str(v)


def emit(lines, name, s, slb):
    n = s["n"] if s else 0
    pf = s["pf"] if s else float("nan")
    net = s["net"] if s else float("nan")
    dd = s["dd"] if s else float("nan")
    lbnet = slb["net"] if slb else float("nan")
    lbpf = slb["pf"] if slb else float("nan")
    lines.append(H % (name, n, _fmt(pf, pf=True), _fmt(net, money=True), _fmt(dd, money=True),
                      _fmt(lbnet, money=True), _fmt(lbpf, pf=True)))
    print(lines[-1], flush=True)


def beats_incumbent(s, slb):
    if s is None or slb is None:
        return False
    return s["pf"] >= INCUMBENT["pf"] and slb["net"] >= INCUMBENT["lb"]


# ---------------------------------------------------------------------------

def main():
    L = []
    L.append("TTM SQUEEZE ROUND 12a - Squeeze Pro (graded 3-level compression) as the SIGNAL   %s"
             % time.strftime("%Y-%m-%d %H:%M"))
    L.append("window %s..%s, lockbox from %s, house costs, one contract; hourly (60m) sq_on gate ON in every row"
             % (DATE_FROM, DATE_TO, LB_FROM))
    L.append("INCUMBENT quoted (ES 30m RTH crown): n=%d PF=%.2f net=$%s DD=$%s LB=$%s LB PF=%.2f" % (
        INCUMBENT["n"], INCUMBENT["pf"], "{:,.0f}".format(INCUMBENT["net"]),
        "{:,.0f}".format(INCUMBENT["dd"]), "{:,.0f}".format(INCUMBENT["lb"]), INCUMBENT["lbpf"]))
    print("\n".join(L), flush=True)

    dfs = {}
    for inst, tf in MARKETS:
        dfs[(inst, tf)] = r6.load(inst, tf, "RTH")

    # ---- nesting check (premise of the whole round) ----
    L.append("")
    L.append("=" * 130)
    L.append("PREMISE CHECK - does HIGH(kc1.0) imply MID(kc1.5) imply LOW(kc2.0) at every bar?")
    L.append("=" * 130)
    levels = {}
    for inst, tf in MARKETS:
        df = dfs[(inst, tf)]
        h, l, c = df["high"].values, df["low"].values, df["close"].values
        level, mom, sq_low, sq_mid, sq_high = pro_levels(h, l, c)
        ok, v1, v2 = check_nesting(sq_low, sq_mid, sq_high)
        run_high = run_len_of(sq_high)
        reached = reached_flag(sq_mid, sq_high)
        levels[(inst, tf)] = dict(level=level, sq_low=sq_low, sq_mid=sq_mid, sq_high=sq_high,
                                  run_high=run_high, reached=reached)
        L.append("  %s %s: nesting %s (HIGH-not-MID violations=%d, MID-not-LOW violations=%d); "
                 "HIGH on %.1f%% of bars, MID on %.1f%% of bars, LOW on %.1f%% of bars"
                 % (inst, tf, "OK" if ok else "BROKEN", v1, v2,
                    100 * sq_high.mean(), 100 * sq_mid.mean(), 100 * sq_low.mean()))
        print(L[-1], flush=True)

    # ---- sanity check: this file's own engine reproduces the incumbent bit-for-bit ----
    L.append("")
    L.append("=" * 130)
    L.append("SANITY CHECK - run_pro_entry(entry_kc=1.5, gate_kc=1.5) on ES 30m must reproduce the incumbent")
    L.append("=" * 130)
    df_es = dfs[("ES", "30m")]
    r_direct = ttm3.run_backtest(df_es["open"].values, df_es["high"].values, df_es["low"].values,
                                 df_es["close"].values, day_id=df_es["day_id"].values,
                                 index=df_es["_dt"], return_trades=True, **CROWN)
    t_direct = to_df(r_direct, "ES", df_es)
    r_custom = run_pro_entry(df_es, entry_kc=1.5, gate_kc=1.5, length=20, bb_mult=2.0, min_sq_bars=1,
                             entry_fill="open", exit_mode="fade", fade_bars=1, stop_atr=1.5,
                             eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20)
    t_custom = to_df(r_custom, "ES", df_es)
    match = (t_direct is not None and t_custom is not None and len(t_direct) == len(t_custom)
            and np.allclose(t_direct["usd"].values, t_custom["usd"].values))
    s_d = score_row(t_direct["usd"].values, t_direct["date"].dt.date.values)
    s_c = score_row(t_custom["usd"].values, t_custom["date"].dt.date.values)
    L.append("  TTMSQZ_3_0.run_backtest direct : n=%d PF=%.2f net=$%s" % (
        s_d["n"], s_d["pf"], "{:,.0f}".format(s_d["net"])))
    L.append("  run_pro_entry (this file)      : n=%d PF=%.2f net=$%s" % (
        s_c["n"], s_c["pf"], "{:,.0f}".format(s_c["net"])))
    L.append("  identical trades: %s   |   matches quoted incumbent (n=%d net=$%s): %s" % (
        match, INCUMBENT["n"], "{:,.0f}".format(INCUMBENT["net"]),
        s_c["n"] == INCUMBENT["n"] and abs(s_c["net"] - INCUMBENT["net"]) < 1.0))
    print("\n".join(L[-4:]), flush=True)

    classic_trades = {}   # (inst,tf) -> full trade DataFrame, classic MID release
    classic_score = {}
    for inst, tf in MARKETS:
        df = dfs[(inst, tf)]
        if (inst, tf) == ("ES", "30m"):
            t = t_custom
        else:
            r = run_pro_entry(df, entry_kc=1.5, gate_kc=1.5, length=20, bb_mult=2.0, min_sq_bars=1,
                              entry_fill="open", exit_mode="fade", fade_bars=1, stop_atr=1.5,
                              eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20)
            t = to_df(r, inst, df)
        classic_trades[(inst, tf)] = t
        s = score_row(t["usd"].values, t["date"].dt.date.values)
        lb = lb_split(t)
        slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
        classic_score[(inst, tf)] = (s, slb)

    L.append("")
    L.append("=" * 130)
    L.append("BASELINE - classic MID release (kc 1.5), hourly gate ON, both markets (ES 30m = the incumbent tape)")
    L.append("=" * 130)
    L.append(HDR)
    for inst, tf in MARKETS:
        s, slb = classic_score[(inst, tf)]
        tag = "INCUMBENT config" if (inst, tf) == ("ES", "30m") else "reference (never crowned)"
        emit(L, "%s %s classic MID release  [%s]" % (inst, tf, tag), s, slb)

    results = []   # (name, s, slb)

    # ================= TEST 1: fire on release from HIGH =================
    L.append("")
    L.append("=" * 130)
    L.append("TEST 1 - fire on release from HIGH (kc 1.0) instead of classic MID (kc 1.5); hourly gate stays classic")
    L.append("=" * 130)
    L.append(HDR)
    for inst, tf in MARKETS:
        df = dfs[(inst, tf)]
        r = run_pro_entry(df, entry_kc=1.0, gate_kc=1.5, length=20, bb_mult=2.0, min_sq_bars=1,
                          entry_fill="open", exit_mode="fade", fade_bars=1, stop_atr=1.5,
                          eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20)
        t = to_df(r, inst, df)
        name = "%s %s fire-from-HIGH release" % (inst, tf)
        if t is None:
            L.append("  %-52s  no trades" % name); print(L[-1], flush=True)
            results.append((name, None, None)); continue
        s = score_row(t["usd"].values, t["date"].dt.date.values)
        lb = lb_split(t)
        slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
        emit(L, name, s, slb)
        results.append((name, s, slb))

    # ================= TEST 2: reached HIGH anywhere in the coil, classic release =================
    L.append("")
    L.append("=" * 130)
    L.append("TEST 2 - required HIGH touched at any point during the coil, then fire on the classic MID release")
    L.append("  (post-hoc SELECTION on the classic trade list above - no trade added, removed timing unchanged)")
    L.append("=" * 130)
    L.append(HDR)
    for inst, tf in MARKETS:
        t = classic_trades[(inst, tf)]
        lv = levels[(inst, tf)]
        reached_at_fire = lv["reached"][t["lastsq"].values]
        name = "%s %s SELECT: reached HIGH during coil" % (inst, tf)
        sel = t[reached_at_fire]
        if len(sel) == 0:
            L.append("  %-52s  no trades" % name); print(L[-1], flush=True)
            results.append((name, None, None)); continue
        s = score_row(sel["usd"].values, sel["date"].dt.date.values)
        lb = lb_split(sel)
        slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
        emit(L, name + "  (%d/%d kept)" % (len(sel), len(t)), s, slb)
        results.append((name, s, slb))
        p = perm_p(t["usd"].values, reached_at_fire)
        L.append("    permutation p on mean $/trade gap (reached vs not): %.4f  (%s)" % (
            p, "possibly real" if p == p and p < 0.05 else "not significant on its own"))
        print(L[-1], flush=True)

    # ================= TEST 3: level AT the fire =================
    L.append("")
    L.append("=" * 130)
    L.append("TEST 3 - LEVEL AT THE FIRE (compression grade of the last bar still inside the coil)")
    L.append("  3a SELECTION: only take classic fires that were wound to HIGH at that moment")
    L.append("  3b TILT: keep every classic trade, 1.5x size on the ones wound to HIGH (round-8 shape)")
    L.append("=" * 130)
    L.append(HDR)
    for inst, tf in MARKETS:
        t = classic_trades[(inst, tf)]
        lv = levels[(inst, tf)]
        level_at_fire = lv["level"][t["lastsq"].values]
        is_high = level_at_fire == 3
        L.append("  %s %s: level-at-fire distribution over %d classic trades - MID(2)=%d HIGH(3)=%d"
                 % (inst, tf, len(t), int((level_at_fire == 2).sum()), int(is_high.sum())))
        print(L[-1], flush=True)
        # 3a selection
        name = "%s %s SELECT: level-at-fire == HIGH" % (inst, tf)
        sel = t[is_high]
        if len(sel) == 0:
            L.append("  %-52s  no trades" % name); print(L[-1], flush=True)
            results.append((name, None, None))
        else:
            s = score_row(sel["usd"].values, sel["date"].dt.date.values)
            lb = lb_split(sel)
            slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
            emit(L, name + "  (%d/%d kept)" % (len(sel), len(t)), s, slb)
            results.append((name, s, slb))
            p = perm_p(t["usd"].values, is_high)
            L.append("    permutation p on mean $/trade gap (HIGH-at-fire vs MID-at-fire): %.4f  (%s)" % (
                p, "possibly real" if p == p and p < 0.05 else "not significant on its own"))
            print(L[-1], flush=True)
        # 3b tilt (every trade kept)
        name = "%s %s TILT: 1.5x when level-at-fire == HIGH" % (inst, tf)
        tt = t.copy()
        tt["usd"] = np.where(is_high, 1.5 * t["usd"].values, t["usd"].values)
        s = score_row(tt["usd"].values, tt["date"].dt.date.values)
        lb = lb_split(tt)
        slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
        emit(L, name, s, slb)
        results.append((name, s, slb))

    # ================= TEST 4: DURATION at HIGH before the fire =================
    L.append("")
    L.append("=" * 130)
    L.append("TEST 4 - DURATION at HIGH before the fire (consecutive bars at HIGH ending on the last squeezed bar)")
    L.append("  4a SELECTION buckets: 0 (never reached HIGH) / 1-2 bars / 3+ bars")
    L.append("  4b TILT: keep every classic trade, 1.5x size when duration-at-HIGH >= 2 bars")
    L.append("=" * 130)
    L.append(HDR)
    for inst, tf in MARKETS:
        t = classic_trades[(inst, tf)]
        lv = levels[(inst, tf)]
        dur = lv["run_high"][t["lastsq"].values]
        buckets = [("0 (never HIGH)", dur == 0), ("1-2 bars at HIGH", (dur >= 1) & (dur <= 2)),
                   ("3+ bars at HIGH", dur >= 3)]
        for blabel, bmask in buckets:
            name = "%s %s SELECT: duration-at-HIGH = %s" % (inst, tf, blabel)
            sel = t[bmask]
            if len(sel) == 0:
                L.append("  %-52s  no trades" % name); print(L[-1], flush=True)
                results.append((name, None, None)); continue
            s = score_row(sel["usd"].values, sel["date"].dt.date.values)
            lb = lb_split(sel)
            slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
            emit(L, name + "  (%d/%d kept)" % (len(sel), len(t)), s, slb)
            results.append((name, s, slb))
        name = "%s %s TILT: 1.5x when duration-at-HIGH >= 2" % (inst, tf)
        deep = dur >= 2
        tt = t.copy()
        tt["usd"] = np.where(deep, 1.5 * t["usd"].values, t["usd"].values)
        s = score_row(tt["usd"].values, tt["date"].dt.date.values)
        lb = lb_split(tt)
        slb = score_row(lb["usd"].values, lb["date"].dt.date.values) if len(lb) else None
        emit(L, name, s, slb)
        results.append((name, s, slb))
        p = perm_p(t["usd"].values, deep)
        L.append("    permutation p on mean $/trade gap (duration>=2 vs <2): %.4f  (%s)" % (
            p, "possibly real" if p == p and p < 0.05 else "not significant on its own"))
        print(L[-1], flush=True)

    # ---- verdict ----
    L.append("")
    L.append("=" * 130)
    L.append("VERDICT - cells beating the incumbent on BOTH whole-run PF (>=%.2f) AND lockbox net (>=$%s)"
             % (INCUMBENT["pf"], "{:,.0f}".format(INCUMBENT["lb"])))
    L.append("=" * 130)
    winners = [(name, s, slb) for name, s, slb in results if beats_incumbent(s, slb)]
    if winners:
        for name, s, slb in winners:
            L.append("  BEATS INCUMBENT: %-52s PF %.2f (vs %.2f)  LB $%s (vs $%s)" % (
                name, s["pf"], INCUMBENT["pf"], "{:,.0f}".format(slb["net"]), "{:,.0f}".format(INCUMBENT["lb"])))
    else:
        L.append("  none - every cell in this file falls short on PF, lockbox net, or both.")
    print("\n".join(L[-max(1, len(winners) + 1):]), flush=True)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\nlog ->", LOG)


if __name__ == "__main__":
    main()
