"""TTM SQUEEZE ROUND 14b - the exit, RE-ASKED on the new (structural-stop) base.

Round 12b answered the same question — momentum-fade vs time exits vs an ATR trail vs
scaling out — on the OLD base, a 1.5x-ATR protective stop. Every alternative lost to the
1-bar fade there. Since then the stop itself changed: run #353 replaced it with a
STRUCTURAL stop at the far side of the squeeze range that produced the fire, validated,
carrying the paper book (memory `edgelog-ttm-squeeze-study`, `TTM.md`). That stop is
~76% wider per contract than the ATR stop it replaced (round 12b's own gap-stress number),
so trades now survive noise the tight stop used to cut off — the exit question is open
again on a base round 12b never tested, and it is asked here.

NEW IDEA NOBODY HAS TRIED: if the far side of the coil is where the setup is WRONG (that is
the whole logic of the structural stop), the same distance on the OTHER side is a natural
TARGET — a structural target, not an arbitrary R-multiple.

INCUMBENT (quote in every table) — run #353 `TTMSQZ_3_0_ES30SS20.py`, ES 30m RTH, pinned
window, 0.363 pts/round-trip, $50/pt, kc_mult 1.5, gate_len 20, eod_cutoff 1, structural stop
buffer 0, 1-bar fade exit, 1.5x deep-squeeze tilt:
    n 357, PF 2.91, net $101,017, DD $4,338, lockbox $16,977 at PF 6.72.

WHAT VARIES (structural stop kept throughout — the base every cell below shares):
  1. Momentum-fade after 2 and 3 bars instead of 1 (round 8 mildly favoured 2-3 on the OLD
     base; re-asked here).
  2. Ride to the session close with no momentum exit at all (stop or EOD only).
  3. A STRUCTURAL TARGET: entry +/- (1.0/1.5/2.0/3.0) x the fire bar's squeeze-range width,
     with and without the fade exit still armed underneath.
  4. A break-even move: once price has travelled one range-width in favour, pull the stop to
     entry. Judged on NET and drawdown ONLY — this shop has already learned an early
     breakeven flatters EV R/expectancy metrics while losing money (memory
     `edgelog-evr-gameable-by-breakeven`); it is not used to judge anything here.
  5. Half off at the 1.0x structural target, the rest to the fade exit — asks whether this
     repeats the shop's standing finding that scaling out is risk-adjusted, not richer (same
     conclusion on ORB and on round 12b's own 1R scale-out test).

NO LOOK-AHEAD, and how it is enforced:
  - A decision made on bar u's close can only be acted on from bar u+1 onward (fade signal
    detected on bar u fills at bar u+1's open — unchanged from every prior round).
  - The protective stop and the structural target are both anchored at ENTRY from the FIRE
    bar's squeeze range, which closed strictly before the entry bar — no future information.
  - Breakeven is armed using max-favourable-excursion accumulated only through the PRIOR bar's
    own high/low (mirrors round 12b's ATR-trail update, which uses atr[u-1] / extreme at
    u-1): the stop can move to entry starting the bar AFTER price first reached one
    range-width in favour, never on the same bar that reached it.
  - WHENEVER A TARGET AND A STOP BOTH FALL INSIDE THE SAME BAR, THE STOP IS ASSUMED HIT
    FIRST — pessimistic resolution, checked in that order in `simulate()` below, and called
    out again at the point in the code where it happens.

Harness: tools/ttmsqz_round6_parts.py (load/score/COST/MULT/window, unchanged), engine
augur_strategies/TTMSQZ_3_0.py (squeeze_indicators via TTMSQZ_1_0, _htf_gate,
_session_last_bar — reused verbatim, not re-derived), augur_strategies/TTMSQZ_3_0_ES30SS.py
(the structural-stop cell this round is based on — its fire/range/gate construction and its
_deep_state size-tilt are imported and reused unchanged so the entry side of every cell here
is bit-identical to the incumbent's). Pattern follows tools/ttmsqz_r12b_entry_exit.py.

Pinned window 2010-06-07..2026-06-30, lockbox = trades exiting on/after 2025-07-01, ES cost
0.363 pts/round-trip, mult 50, one contract before the tilt. SCAN ONLY: crowns nothing,
queues nothing, touches no index.html, no commit made from this file.

Usage:  python tools/ttmsqz_r14b_exits_on_new_base.py
Output: tools/data/ttmsqz_r14b_exits_on_new_base.txt
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


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6_r14b")
ttm1 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"), "ttm1_r14b")
ttm3 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0.py"), "ttm3_r14b")
ss = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS.py"), "ss_r14b")

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
INST = "ES"
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r14b_exits_on_new_base.txt")

# The structural-stop cell run #353 crowned (TTMSQZ_3_0_ES30SS20.py): kc_mult 1.5, gate_len
# 20, eod_cutoff 1, buffer 0.0. Reused verbatim from the ES30SS module (ss._FROZEN,
# ss._STRUCT_BUF) rather than re-typed, so a future edit to the crowned cell cannot silently
# desync this file from it.
KC_MULT = 1.5                               # kc_mult is not in ss._FROZEN (it's searched); pin it here
GATE_LEN = 20
EOD_CUTOFF = 1
STRUCT_BUF = ss._STRUCT_BUF                 # 0.0
LENGTH, BB_MULT = ss._FROZEN['length'], ss._FROZEN['bb_mult']
MIN_SQ_BARS = ss._FROZEN['min_sq_bars']
GATE_TF_MIN, GATE_MODE = ss._FROZEN['gate_tf_min'], ss._FROZEN['gate_mode']
GATE_FIRED_K, GATE_BARS_KW, GATE_RATIO = ss._FROZEN['gate_fired_k'], ss._FROZEN['gate_bars'], ss._FROZEN['gate_ratio']

INCUMBENT_QUOTE = dict(n=357, pf=2.91, net=101017, dd=4338, lb_net=16977, lb_pf=6.72)


# --------------------------------------------------------------------------------------
# Shared, causal setup — copied verbatim from TTMSQZ_3_0_ES30SS._build_arrays so the
# fire/range/gate arrays are bit-identical to the incumbent's.
# --------------------------------------------------------------------------------------
def _prep(df):
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float);  c = df["close"].values.astype(float)
    did = df["day_id"].values
    n = len(c)
    sq_on, mom, atr = ttm1.squeeze_indicators(h, l, c, LENGTH, BB_MULT, KC_MULT)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= MIN_SQ_BARS)
    warm = LENGTH * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()
    gate_long, gate_short = ttm3._htf_gate(
        h, l, c, did, df["_dt"], GATE_BARS_KW, GATE_TF_MIN, GATE_LEN, BB_MULT, KC_MULT,
        GATE_MODE, GATE_FIRED_K, GATE_RATIO)
    last_bar = ttm3._session_last_bar(did, n)
    return dict(o=o, h=h, l=l, c=c, n=n, warm=warm, mom=mom, atr=atr,
                fire=fire, rng_hi=rng_hi, rng_lo=rng_lo, gate_long=gate_long,
                gate_short=gate_short, last_bar=last_bar)


# --------------------------------------------------------------------------------------
# THE LOOP. Structural stop (buffer 0) and next-open entry are FIXED throughout — that is
# the whole point of this round. What varies is what happens once a trade is open:
#
#   fade_active   - is the momentum-fade exit ever armed at all (False = ride to close/stop)
#   fade_bars     - how many consecutive fading bars trigger it (1/2/3)
#   target_mult   - None, or the structural target as a multiple of the fire bar's squeeze-
#                   range width, projected from ENTRY (not from the fire bar's own close)
#   target_frac   - 1.0 = full exit at target; 0.5 = scale out half, rest rides to the fade
#   breakeven     - once max-favourable-excursion (measured causally, one bar in arrears)
#                   reaches 1x the range width, the stop moves to entry
#
# PESSIMISTIC SAME-BAR RESOLUTION: within a single bar, the stop is always checked BEFORE
# the target (see the block below marked "STOP FIRST"). If both levels fall inside that
# bar's high-low range, the stop is assumed hit and the target is never reached — this is
# the one place a look-ahead could otherwise creep in, and it is resolved conservatively.
# --------------------------------------------------------------------------------------
def simulate(P, fade_active=True, fade_bars=1, target_mult=None, target_frac=1.0,
            breakeven=False, eod_cutoff=EOD_CUTOFF):
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    n, warm = P["n"], P["warm"]
    mom = P["mom"]
    fire, rng_hi, rng_lo = P["fire"], P["rng_hi"], P["rng_lo"]
    gate_long, gate_short, last_bar = P["gate_long"], P["gate_short"], P["last_bar"]

    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
    stop_px = None; target_px = None; range_width = 0.0
    mfe = 0.0; breakeven_armed = False; half_booked = False
    fade_cnt = 0
    pending = None   # ("exit",) | ("mkt", side, rh, rl)
    trades = []      # (entry_bar, exit_bar, pnl_pts, side, entry_px, frac, kind)
    exit_counts = {"stop": 0, "target": 0, "fade": 0, "close": 0, "target_partial": 0}  # FINAL leg
    # only, except "target_partial" which counts scale-out HALF-exits (final=False) separately
    # so they are not silently invisible in a variant where every entry keeps its final leg.

    def book(exit_i, px, sd, ep, eb, frac, kind, final):
        p = (px - ep) if sd > 0 else (ep - px)
        trades.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(frac), kind))
        if final:
            exit_counts[kind] += 1
        elif kind == "target":
            exit_counts["target_partial"] += 1

    def reset():
        nonlocal pos, stop_px, target_px, mfe, breakeven_armed, half_booked
        pos = 0; stop_px = None; target_px = None; mfe = 0.0
        breakeven_armed = False; half_booked = False

    for u in range(warm, n):
        eod = u == last_bar[u]

        # 1. resolve any pending order (from the PRIOR bar's decision)
        if pending is not None:
            kind0 = pending[0]
            if kind0 == "exit":                      # delayed fade exit, fills at this open
                if pos != 0:
                    frac = 0.5 if half_booked else 1.0
                    book(u, o[u], side, entry_px, entry_bar, frac, "fade", True)
                    reset()
                pending = None
            else:                                      # "mkt" — new entry
                if pos == 0:
                    side = pending[1]; rh, rl = pending[2], pending[3]
                    entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    range_width = rh - rl
                    # STRUCTURAL STOP — fixed throughout, buffer 0, anchored at the fire
                    # bar's own range (closed strictly before this entry bar: no look-ahead).
                    stop_px = (rl - STRUCT_BUF) if side > 0 else (rh + STRUCT_BUF)
                    target_px = (entry_px + side * target_mult * range_width
                                if target_mult is not None else None)
                    mfe = 0.0; breakeven_armed = False; half_booked = False
                    pos = side
                    # same-bar stop on the fill bar itself (mirrors ES30SS's own convention)
                    if (side > 0 and l[u] <= stop_px) or (side < 0 and h[u] >= stop_px):
                        book(u, stop_px, pos, entry_px, entry_bar, 1.0, "stop", True)
                        reset()
                pending = None

        # 2. in-position management (bars after the entry bar only)
        if pos != 0 and u > entry_bar:
            # breakeven arms from favourable excursion accumulated through bar u-1 ONLY
            # (mfe is updated at the END of this block using bar u's own range, so a move
            # that first reaches 1x range-width on bar u cannot move the stop until u+1).
            if breakeven and not breakeven_armed and mfe >= range_width:
                stop_px = entry_px
                breakeven_armed = True

            # --- STOP FIRST: pessimistic same-bar resolution (see docstring) ---
            stopped = (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px)
            if stopped:
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                frac = 0.5 if half_booked else 1.0
                book(u, px, pos, entry_px, entry_bar, frac, "stop", True)
                reset()
            elif target_px is not None:
                hit = (pos > 0 and h[u] >= target_px) or (pos < 0 and l[u] <= target_px)
                if hit:
                    gapped = (pos > 0 and o[u] >= target_px) or (pos < 0 and o[u] <= target_px)
                    px = o[u] if gapped else target_px
                    if target_frac < 1.0 and not half_booked:
                        # SCALE-OUT: half off at the structural target; the rest keeps riding
                        # (fade stays armed below, same stop/breakeven logic continues).
                        book(u, px, pos, entry_px, entry_bar, target_frac, "target", False)
                        half_booked = True
                        target_px = None       # one shot at the target; no second partial
                    else:
                        frac = 1.0 - target_frac if half_booked else 1.0
                        book(u, px, pos, entry_px, entry_bar, frac, "target", True)
                        reset()

            if pos != 0:
                fav = (h[u] - entry_px) if side > 0 else (entry_px - l[u])
                mfe = max(mfe, fav)

        # 3. session close
        if eod:
            if pos != 0:
                frac = (1.0 - target_frac) if half_booked else 1.0
                book(u, c[u], pos, entry_px, entry_bar, frac, "close", True)
                reset()
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]

        # 4. fade exit (delayed one bar — the engine's own convention, unchanged)
        if pos != 0 and fade_active and np.isfinite(m) and np.isfinite(m1):
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
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
            pending = ("mkt", sd, rng_hi[u], rng_lo[u])

    t = pd.DataFrame(trades, columns=["eb", "xb", "pnl", "side", "epx", "frac", "kind"])
    return t, exit_counts


# --------------------------------------------------------------------------------------
# Scoring — sized by ES30SS's own 1.5x deep-squeeze tilt (_deep_state, imported unchanged),
# same cost convention: a trade sized s returns s*raw - (s-1)*cost, so partial (frac<1) legs
# of a scale-out are tilted and cost-adjusted exactly like a full trade would be.
# --------------------------------------------------------------------------------------
def score_trades(t, df):
    if t is None or len(t) == 0:
        return None, None, None
    deep = ss._deep_state(df["high"].values, df["low"].values, df["close"].values,
                          df["day_id"].values, df["_dt"])
    nn = len(deep)
    eb = t["eb"].values
    d = deep[np.clip(eb - 1, 0, nn - 1)]     # decision bar = one before the fill, per ES30SS
    s_mult = np.where(d, ss._TILT_MULT, 1.0)
    raw = t["pnl"].values * t["frac"].values
    usd_pts = s_mult * raw - (s_mult - 1.0) * ss._COST_PTS * t["frac"].values
    usd = (usd_pts - COST[INST] * t["frac"].values) * MULT[INST]
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
    s = r6.score(usd, dates)
    lbmask = np.array([dt >= pd.Timestamp(LB_FROM).date() for dt in dates])
    sl = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
    n_entries = t["eb"].nunique()
    return s, sl, n_entries


HDR = "  %-46s %5s %6s %11s %9s | %11s %6s %5s  %s"


def row(name, s, sl, n_entries=None, exit_counts=None, note=""):
    if s is None:
        return "  %-46s  no trades" % name
    lb_net = "{:,.0f}".format(sl["net"]) if sl else "n/a"
    lb_pf = "%.2f" % min(sl["pf"], 99) if sl else "n/a"
    lb_n = str(sl["n"]) if sl else "0"
    tail = note
    if exit_counts is not None and n_entries is not None:
        ex = "exits: stop %d / target %d / fade %d / close %d  (entries %d)" % (
            exit_counts["stop"], exit_counts["target"], exit_counts["fade"],
            exit_counts["close"], n_entries)
        if exit_counts.get("target_partial"):
            ex += "  [+%d half-off @target, final leg counted above]" % exit_counts["target_partial"]
        tail = (tail + "   " + ex).strip()
    return HDR % (name, s["n"], "%.2f" % min(s["pf"], 99), "{:,.0f}".format(s["net"]),
                 "{:,.0f}".format(s["dd"]), lb_net, lb_pf, lb_n, tail)


def beats_incumbent(s, sl, sc, scl):
    """BOTH whole-run PF and lockbox net must beat the incumbent — the family's standing bar."""
    if s is None or sl is None:
        return False
    return (s["pf"] >= sc["pf"]) and (sl["net"] >= scl["net"])


def main():
    t0 = time.time()
    L = []
    L.append("TTM SQUEEZE ROUND 14b - the exit, re-asked on the structural-stop base   %s"
             % time.strftime("%Y-%m-%d %H:%M"))
    L.append("ES 30m RTH, window %s..%s, lockbox from %s, house cost %.3f pts, mult %d, 1 contract"
             % (DATE_FROM, DATE_TO, LB_FROM, COST[INST], MULT[INST]))
    L.append("STRUCTURAL STOP kept throughout (buffer 0, run #353's own cell): kc_mult %.2f, gate_len %d, "
             "eod_cutoff %d. 1.5x deep-squeeze tilt applied throughout, exactly as ES30SS20 applies it."
             % (KC_MULT, GATE_LEN, EOD_CUTOFF))
    L.append("Same-bar stop/target conflicts resolved pessimistically (STOP CHECKED FIRST) throughout — see")
    L.append("simulate()'s \"STOP FIRST\" block. Breakeven arms only from favourable excursion through the")
    L.append("PRIOR bar (one bar in arrears) — never off the same bar that first reached it. No look-ahead.")

    df = r6.load(INST, "30m", "RTH")
    P = _prep(df)

    # ---- reproduction check: this file's own loop vs the engine's run_backtest on the ----
    # ---- incumbent config (fade_bars=1, no target, no breakeven) ----
    t_base, exc_base = simulate(P, fade_active=True, fade_bars=1, target_mult=None, breakeven=False)
    sc, scl, ne_base = score_trades(t_base, df)
    L.append("")
    L.append("REPRODUCTION CHECK (this file's loop vs run #353 / ES30SS20 on the incumbent config):")
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    L.append(row("incumbent (run #353, quoted)",
                 dict(n=INCUMBENT_QUOTE['n'], pf=INCUMBENT_QUOTE['pf'], net=INCUMBENT_QUOTE['net'],
                      dd=INCUMBENT_QUOTE['dd']),
                 dict(net=INCUMBENT_QUOTE['lb_net'], pf=INCUMBENT_QUOTE['lb_pf'], n=None),
                 note="quoted, not recomputed"))
    match = (sc is not None and sc["n"] == INCUMBENT_QUOTE['n']
            and abs(sc["net"] - INCUMBENT_QUOTE['net']) < 5
            and abs(sc["dd"] - INCUMBENT_QUOTE['dd']) < 5)
    L.append(row("incumbent (this file's own loop)", sc, scl, ne_base, exc_base,
                 "MATCH" if match else "MISMATCH - investigate before trusting anything below"))
    print("\n".join(L), flush=True)
    if not match:
        L.append("")
        L.append("*** reproduction did not match to the cent/trade-count — halting before running variants. ***")
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print("\n".join(L))
        return

    results = []   # (family, name, s, sl, n_entries, exit_counts)

    # ============================================================================
    # 1. MOMENTUM-FADE AFTER 2 AND 3 BARS
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("1. MOMENTUM-FADE after 2 and 3 bars instead of 1 (round 8 re-asked on the new base)")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    for fb in (1, 2, 3):
        t, exc = simulate(P, fade_active=True, fade_bars=fb, target_mult=None, breakeven=False)
        s, sl, ne = score_trades(t, df)
        name = "fade after %d bar%s%s" % (fb, "s" if fb != 1 else "", "  (incumbent)" if fb == 1 else "")
        b = beats_incumbent(s, sl, sc, scl)
        L.append(row(name, s, sl, ne, exc, "<-- BEATS incumbent (PF+LB)" if b and fb != 1 else ""))
        if fb != 1:
            results.append(("1 fade timing", name, s, sl, ne, exc))
    print("\n".join(L[-5:]), flush=True)

    # ============================================================================
    # 2. RIDE TO CLOSE, NO MOMENTUM EXIT
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("2. RIDE TO SESSION CLOSE - no momentum exit at all (stop or EOD only)")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    t, exc = simulate(P, fade_active=False, target_mult=None, breakeven=False)
    s, sl, ne = score_trades(t, df)
    name = "ride to close (stop/EOD only, no fade)"
    b = beats_incumbent(s, sl, sc, scl)
    L.append(row(name, s, sl, ne, exc, "<-- BEATS incumbent (PF+LB)" if b else ""))
    results.append(("2 ride to close", name, s, sl, ne, exc))
    print("\n".join(L[-4:]), flush=True)

    # ============================================================================
    # 3. STRUCTURAL TARGET
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("3. STRUCTURAL TARGET - entry +/- Nx the fire bar's squeeze-range width, with and without")
    L.append("   the fade exit still armed underneath (stop unchanged: structural, buffer 0)")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    for mult in (1.0, 1.5, 2.0, 3.0):
        for with_fade in (True, False):
            t, exc = simulate(P, fade_active=with_fade, fade_bars=1, target_mult=mult,
                              target_frac=1.0, breakeven=False)
            s, sl, ne = score_trades(t, df)
            name = "%.1fx range target, fade %s" % (mult, "ARMED" if with_fade else "off")
            b = beats_incumbent(s, sl, sc, scl)
            L.append(row(name, s, sl, ne, exc, "<-- BEATS incumbent (PF+LB)" if b else ""))
            results.append(("3 structural target", name, s, sl, ne, exc))
    print("\n".join(L[-9:]), flush=True)

    # ============================================================================
    # 4. BREAK-EVEN MOVE
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("4. BREAK-EVEN - once price has travelled 1x the range width in favour, stop moves to")
    L.append("   entry. Judged on NET and DRAWDOWN ONLY (never EV R — an early breakeven flatters it")
    L.append("   while losing money, memory edgelog-evr-gameable-by-breakeven). Fade exit (1 bar) stays armed.")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    t, exc = simulate(P, fade_active=True, fade_bars=1, target_mult=None, breakeven=True)
    s, sl, ne = score_trades(t, df)
    name = "breakeven at 1x range MFE, fade underneath"
    b = beats_incumbent(s, sl, sc, scl)
    L.append(row(name, s, sl, ne, exc, "<-- BEATS incumbent (PF+LB)" if b else ""))
    results.append(("4 breakeven", name, s, sl, ne, exc))
    if s and sc:
        L.append("  NET vs incumbent: %s vs %s (%.1f%%)   DD vs incumbent: %s vs %s (%.1f%%)  -- judge on these two"
                 % ("{:,.0f}".format(s["net"]), "{:,.0f}".format(sc["net"]), 100 * s["net"] / sc["net"],
                    "{:,.0f}".format(s["dd"]), "{:,.0f}".format(sc["dd"]), 100 * s["dd"] / sc["dd"]))
    print("\n".join(L[-6:]), flush=True)

    # ============================================================================
    # 5. SCALE OUT AT THE STRUCTURAL TARGET
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("5. SCALE OUT - half off at the 1.0x structural target, the rest rides to the fade exit")
    L.append("=" * 100)
    L.append(HDR % ("cell", "n", "PF", "net $", "DD $", "LB $", "LB PF", "LB n", ""))
    t, exc = simulate(P, fade_active=True, fade_bars=1, target_mult=1.0, target_frac=0.5, breakeven=False)
    s, sl, ne = score_trades(t, df)
    name = "half off @1.0x target, rest to fade"
    b = beats_incumbent(s, sl, sc, scl)
    L.append(row(name, s, sl, ne, exc, "<-- BEATS incumbent (PF+LB)" if b else ""))
    results.append(("5 scale-out", name, s, sl, ne, exc))
    if s and sc:
        L.append("  net $ vs incumbent: %s vs %s (%.1f%%)   DD $ vs incumbent: %s vs %s (%.1f%%)"
                 % ("{:,.0f}".format(s["net"]), "{:,.0f}".format(sc["net"]), 100 * s["net"] / sc["net"],
                    "{:,.0f}".format(s["dd"]), "{:,.0f}".format(sc["dd"]), 100 * s["dd"] / sc["dd"]))
        verdict = ("RISK-ADJUSTED (lower DD, not richer)" if s["dd"] <= sc["dd"] and s["net"] < sc["net"]
                  else "RICHER (both net and DD improved)" if s["net"] >= sc["net"] and s["dd"] <= sc["dd"]
                  else "NEITHER cleanly - read the two numbers above")
        L.append("  repeats the standing scale-out finding (ORB, round 12b's own 1R test)? -> %s" % verdict)
    print("\n".join(L[-7:]), flush=True)

    # ============================================================================
    # summary
    # ============================================================================
    L.append("")
    L.append("=" * 100)
    L.append("SUMMARY - incumbent (run #353): n %d, PF %.2f, net $%s, DD $%s, lockbox $%s at PF %.2f"
             % (INCUMBENT_QUOTE['n'], INCUMBENT_QUOTE['pf'], "{:,.0f}".format(INCUMBENT_QUOTE['net']),
                "{:,.0f}".format(INCUMBENT_QUOTE['dd']), "{:,.0f}".format(INCUMBENT_QUOTE['lb_net']),
                INCUMBENT_QUOTE['lb_pf']))
    L.append("=" * 100)
    leads = [(fam, name) for fam, name, s, sl, ne, exc in results if beats_incumbent(s, sl, sc, scl)]
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
    print("\n".join(L[-40:]))
    print("\nwrote " + LOG)


if __name__ == "__main__":
    main()
