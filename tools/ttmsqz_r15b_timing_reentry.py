"""
TTM SQUEEZE ROUND 15b - the two mechanical gaps nobody has filled in fourteen rounds.

Both are visible just by reading the trade loop in augur_strategies/TTMSQZ_3_0.py (and its
structural-stop child, TTMSQZ_3_0_ES30SS.py, which this file actually drives, since that is the
book leg's engine as of run #353):

  1. THE OPEN HAS NO CUTOFF. `eod_cutoff` blocks entries inside the last N bars of the session
     and is searched in every fenced file this family has ever written. There is no mirror at
     the open - a fire on the very first bar of RTH (09:30) is taken exactly like one at noon,
     even though the first bars are the noisiest of the day and the squeeze indicators are fed
     a gap. This file adds a `bod_cutoff` (bars-of-day cutoff), symmetric with `eod_cutoff`:
     entries whose FIRE bar sits within the first N bars of the session are skipped. N=1..4.

  2. THERE IS NO RE-ENTRY. One position at a time; a stop-out kills the coil even if price
     turns straight back through the level that stopped it. This file adds ONE optional
     re-entry per coil per session: after a STOP-OUT (not a fade exit, not a session close),
     if price closes back through the SAME level that stopped the trade, one re-entry is taken
     at the next bar's open, same direction, same structural stop (recomputed from the SAME
     original fire-bar range - never a new coil). Two variants: unconditional, and gated on the
     hourly verification still being on at the trigger bar.

THE INCUMBENT (quoted from TTM.md / run #353, not re-derived): TTMSQZ_3_0_ES30SS20.py, ES 30m
RTH, kc_mult 1.5, eod_cutoff 1, gate_len 20 (pinned) - the structural stop (buffer 0) plus the
validated 1.5x deep-squeeze tilt. Whole run: 357 trades, PF 2.91, net $101,017, DD $4,338, MAR
1.450. Lockbox (>= 2025-07-01): $16,977 at PF 6.72. This is the leg the paper book carries.

MECHANISM REUSED, NOT REWRITTEN. `_ss._build_arrays` (the fire/range/gate construction) is
called UNCHANGED. The only new code is the trade loop itself, copied from `_ss._simulate` with
the one addition each gap needs, plus exit-reason tagging (stop / fade / eod) so the report can
show what kind of exit each cell produces. `_ss._deep_state` (the tilt) and `_ss._rescore` /
`_ss._TILT_MULT` / `_ss._COST_PTS` are reused verbatim - the tilt is a separately validated
mechanism, not one of the two gaps under test.

SANITY CHECK FIRST (this family's own standing practice, see TTM.md "Discipline this family
taught the shop"): before any new cell runs, this file reproduces the incumbent bit-for-bit -
both against the real fenced file (TTMSQZ_3_0_ES30SS20.run_backtest) and against this file's own
bod_cutoff=0 / reentry_mode='off' loop, which must degenerate to the exact same trades. If either
disagrees, the run stops.

NO LOOK-AHEAD. The bod_cutoff check reads the FIRE bar's own offset-within-session (bars already
closed at or before the decision bar), exactly like eod_cutoff's own convention. The re-entry
trigger reads only bar u's CLOSE (a closed bar) and fills at bar u+1's OPEN; a stop and a fill
inside the same bar resolve pessimistically (the stop is assumed hit), matching the engine's own
audited same-bar-stop convention.

RULES: pinned window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES cost 0.363 pts round
trip, $50/pt (from tools/ttmsqz_round6_parts.py - not re-derived). Lockbox reported separately,
never tuned on. SCAN ONLY - nothing here is crowned, queued, or written to index.html.

Usage:  python tools/ttmsqz_r15b_timing_reentry.py
Output: tools/data/ttmsqz_r15b_timing_reentry.txt
"""
import os, sys, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _mod(path, name):
    import importlib.util
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6_r15b")
_ss = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS.py"), "ttm_ss_r15b")
_ss20 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS20.py"), "ttm_ss20_r15b")
t3 = _ss._t3

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
INST = "ES"
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r15b_timing_reentry.txt")

INCUMBENT = dict(n=357, pf=2.91, net=101017.0, dd=4338.0, mar=1.450, lb=16977.0, lbpf=6.72)

# the incumbent's own frozen knobs (ES30SS20: gate_len pinned 20, kc_mult 1.5, eod_cutoff 1)
BASE = dict(kc_mult=1.5, gate_len=20, eod_cutoff=1)


# ---------------------------------------------------------------------------------------
# helper: bars-since-session-open, symmetric with TTMSQZ_3_0._session_last_bar
# ---------------------------------------------------------------------------------------
def _session_first_bar(did, n):
    first = np.empty(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        first[a:b] = a
        a = b
    return first


# ---------------------------------------------------------------------------------------
# GAP 1 trade loop - _ss._simulate + one new guard (bod_cutoff), exit reason tagged.
# Every other line is _ss._simulate's own logic, unchanged.
# ---------------------------------------------------------------------------------------
def _simulate_bod(o, h, l, c, n, warm, mom, atr, fire, rng_hi, rng_lo, gate_long, gate_short,
                  last_bar, first_bar, fade_bars, eod_cutoff, bod_cutoff, struct_buf, direction):
    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
    stop_px = None
    fade_cnt = 0
    pending = None
    trade_log = []   # (eb, xb, pnl_pts, side, entry_px, exit_px, reason)

    def _book(exit_i, px, sd, ep, eb, reason):
        p = (px - ep) if sd > 0 else (ep - px)
        trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px), reason))

    for u in range(warm, n):
        eod = u == last_bar[u]

        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar, "fade")
                    pos = 0; stop_px = None
                pending = None
            else:  # "mkt"
                if pos == 0:
                    side = pending[1]; rh, rl = pending[2], pending[3]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar, "stop")
                        pos = 0; stop_px = None
                pending = None

        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar, "stop")
                pos = 0; stop_px = None

        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar, "eod")
                pos = 0; stop_px = None
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue

        if pos != 0:
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
                continue

        if pos == 0 and pending is None and fire[u] and m != 0:
            sd = 1 if m > 0 else -1
            if direction == "long" and sd < 0:
                continue
            if direction == "short" and sd > 0:
                continue
            if sd > 0 and not gate_long[u]:
                continue
            if sd < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            # THE ONE ADDITION: mirror of eod_cutoff at the open. bod_cutoff = N blocks a fire
            # whose bar is one of the first N bars of the session (offset 0 .. N-1).
            if (u - first_bar[u]) < bod_cutoff:
                continue
            pending = ("mkt", sd, rng_hi[u], rng_lo[u])

    return trade_log


# ---------------------------------------------------------------------------------------
# GAP 2 trade loop - _ss._simulate + one-shot re-entry on a stop-out, exit reason + a
# `reentry` flag tagged on every trade.
# ---------------------------------------------------------------------------------------
def _simulate_reentry(o, h, l, c, n, warm, mom, atr, fire, rng_hi, rng_lo, gate_long, gate_short,
                      last_bar, fade_bars, eod_cutoff, struct_buf, direction, reentry_mode):
    """reentry_mode: 'off' (= the incumbent, sanity control), 'any' (re-enter on any stop-out
    once price recrosses the level that stopped it), 'gate' (same, but only if the hourly
    verification is still on for that side at the trigger bar)."""
    pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
    stop_px = None
    fade_cnt = 0
    pending = None
    cur_is_re = False
    coil = None   # {'side','rng_hi','rng_lo','stop_px','stopped_out','reentry_used'}
    trade_log = []   # (eb, xb, pnl_pts, side, entry_px, exit_px, reason, is_reentry)

    def _book(exit_i, px, sd, ep, eb, reason, is_re):
        p = (px - ep) if sd > 0 else (ep - px)
        trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px),
                          reason, bool(is_re)))

    for u in range(warm, n):
        eod = u == last_bar[u]

        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar, "fade", cur_is_re)
                    if coil is not None and coil["side"] == pos:
                        coil["stopped_out"] = False   # a fade exit never earns a re-entry
                    pos = 0; stop_px = None
                pending = None
            else:  # "mkt" - a normal fire entry or a triggered re-entry, tagged in pending[4]
                if pos == 0:
                    side = pending[1]; rh, rl = pending[2], pending[3]; is_re = pending[4]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                    cur_is_re = is_re
                    if not is_re:
                        coil = dict(side=side, rng_hi=rh, rng_lo=rl, stop_px=stop_px,
                                   stopped_out=False, reentry_used=False)
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar, "stop", cur_is_re)
                        if coil is not None and coil["side"] == pos:
                            coil["stopped_out"] = True
                        pos = 0; stop_px = None
                pending = None

        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar, "stop", cur_is_re)
                if coil is not None and coil["side"] == pos:
                    coil["stopped_out"] = True
                pos = 0; stop_px = None

        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar, "eod", cur_is_re)
                if coil is not None and coil["side"] == pos:
                    coil["stopped_out"] = False   # flat-at-close never earns a re-entry
                pos = 0; stop_px = None
            pending = None
            coil = None      # session over: the coil (and its one re-entry shot) dies with it
            continue

        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue

        if pos != 0:
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
                continue

        if pos == 0 and pending is None:
            placed = False
            if fire[u] and m != 0:
                sd = 1 if m > 0 else -1
                ok = True
                if direction == "long" and sd < 0:
                    ok = False
                if direction == "short" and sd > 0:
                    ok = False
                if sd > 0 and not gate_long[u]:
                    ok = False
                if sd < 0 and not gate_short[u]:
                    ok = False
                if last_bar[u] - u <= eod_cutoff:
                    ok = False
                if ok:
                    pending = ("mkt", sd, rng_hi[u], rng_lo[u], False)
                    placed = True
            # THE ONE ADDITION: a new fire always takes priority (the base mechanism); only
            # when there is none does a live re-entry shot get to trigger. Closed-bar only:
            # the trigger reads bar u's CLOSE, the fill is bar u+1's open (same as any entry).
            if (not placed and reentry_mode != "off" and coil is not None
                    and coil["stopped_out"] and not coil["reentry_used"]
                    and last_bar[u] - u > eod_cutoff):
                sd = coil["side"]
                lvl = coil["stop_px"]           # the SAME level that stopped the trade out
                trig = (c[u] > lvl) if sd > 0 else (c[u] < lvl)
                if trig:
                    gate_ok = True
                    if reentry_mode == "gate":
                        gate_ok = bool(gate_long[u]) if sd > 0 else bool(gate_short[u])
                    if gate_ok:
                        pending = ("mkt", sd, coil["rng_hi"], coil["rng_lo"], True)
                        coil["reentry_used"] = True   # once only, hit or miss

    return trade_log


# ---------------------------------------------------------------------------------------
# shared: tilt application + scoring (copied verbatim from _ss.run_backtest / r14a)
# ---------------------------------------------------------------------------------------
def _apply_tilt(trade_log, deep):
    """trade_log rows are (eb, xb, pnl, side, epx, xpx, [reason, [is_re]]) - tilt only
    touches pnl (index 2), everything else passes through unchanged."""
    nn = len(deep)
    out = []
    for t in trade_log:
        eb = int(t[0])
        d = bool(deep[min(max(eb - 1, 0), nn - 1)])
        s = float(_ss._TILT_MULT) if d else 1.0
        pnl = s * float(t[2]) - (s - 1.0) * float(_ss._COST_PTS)
        out.append((t[0], t[1], pnl) + tuple(t[3:]))
    return out


def _score_rows(df, trade_log):
    if not trade_log:
        return None, None, None
    t = pd.DataFrame([(r[0], r[1], r[2]) for r in trade_log], columns=["eb", "xb", "pnl"])
    usd = (t["pnl"].values - COST[INST]) * MULT[INST]
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
    s = r6.score(usd, dates)
    if s is None:
        return None, None, None
    yrs = max((max(dates) - min(dates)).days / 365.25, 1e-9)
    s["mar"] = (s["net"] / yrs) / s["dd"] if s["dd"] > 0 else float("nan")
    lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
    slb = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
    return s, slb, usd


def _reason_breakdown(trade_log, usd):
    """reason column is always at a fixed offset from the end depending on row shape."""
    reasons = [r[6] if len(r) > 6 else None for r in trade_log]
    out = {}
    for i, rs in enumerate(reasons):
        if rs is None:
            continue
        out.setdefault(rs, []).append(usd[i])
    return {k: (len(v), float(np.sum(v))) for k, v in out.items()}


def _fmt(v):
    return "{:,.0f}".format(v)


H = "  %-38s %5s %7s %12s %9s %7s | %11s %7s %6s"
HDR = H % ("cell", "n", "PF", "net $", "DD $", "MAR", "lockbox $", "LB PF", "LB n")


def emit(lines, name, s, slb):
    if s is None:
        lines.append("  %-38s  no trades" % name); print(lines[-1], flush=True); return
    row = H % (name, s["n"], "%.2f" % min(s["pf"], 99), _fmt(s["net"]), _fmt(s["dd"]),
              "%.3f" % s["mar"],
              _fmt(slb["net"]) if slb else "n/a",
              "%.2f" % min(slb["pf"], 99) if slb else "n/a",
              slb["n"] if slb else 0)
    lines.append(row)
    print(lines[-1], flush=True)


def emit_reasons(lines, trade_log, usd, indent="      "):
    br = _reason_breakdown(trade_log, usd)
    parts = []
    for k in ("stop", "fade", "eod"):
        if k in br:
            cnt, net = br[k]
            parts.append("%s %d/$%s" % (k, cnt, _fmt(net)))
    lines.append(indent + "exit reasons: " + ("  ".join(parts) if parts else "n/a"))
    print(lines[-1], flush=True)


def main():
    L = []
    L.append("TTM SQUEEZE ROUND 15b - two mechanical gaps: no cutoff at the session OPEN, and no "
             "RE-ENTRY after a stop-out   %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("window %s..%s, lockbox from %s, ES 30m RTH, cost %.3f pts, $%d/pt; mechanism = run "
             "#353's structural stop (buffer 0) + run #340's validated 1.5x deep-squeeze tilt "
             "(fixed 20/2.0/1.5/60m throughout, not a knob under test)"
             % (DATE_FROM, DATE_TO, LB_FROM, COST["ES"], MULT["ES"]))
    L.append("INCUMBENT (TTMSQZ_3_0_ES30SS20.py, quoted from TTM.md): n=%d PF=%.2f net=$%s DD=$%s "
             "MAR=%.3f | lockbox $%s PF=%.2f"
             % (INCUMBENT["n"], INCUMBENT["pf"], _fmt(INCUMBENT["net"]), _fmt(INCUMBENT["dd"]),
                INCUMBENT["mar"], _fmt(INCUMBENT["lb"]), INCUMBENT["lbpf"]))
    print("\n".join(L), flush=True)

    df = r6.load("ES", "30m", "RTH")
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float); c = df["close"].values.astype(float)
    did = df["day_id"].values; index = df["_dt"]

    A = _ss._build_arrays(o, h, l, c, did, index, BASE["kc_mult"], BASE["gate_len"])
    deep = _ss._deep_state(h, l, c, did, index)
    first_bar = _session_first_bar(did, A["n"])

    # ================================================================================
    # SANITY CHECK - reproduce the incumbent bit for bit before touching anything.
    # (1) the real fenced file  (2) this file's own bod-loop at bod_cutoff=0
    # (3) this file's own reentry-loop at reentry_mode='off'
    # All three must produce IDENTICAL trades.
    # ================================================================================
    L.append("")
    L.append("=" * 116)
    L.append("SANITY CHECK - fenced file vs this file's two loops, both degenerated to the incumbent")
    L.append("=" * 116)
    real = _ss20.run_backtest(o, h, l, c, day_id=did, index=index, return_trades=True,
                              kc_mult=1.5, eod_cutoff=1, gate_len=20)
    real_trades = real["trades"] if real else None

    tl_bod0 = _apply_tilt(_simulate_bod(o, h, l, c, A["n"], A["warm"], A["mom"], A["atr"], A["fire"],
                                        A["rng_hi"], A["rng_lo"], A["gate_long"], A["gate_short"],
                                        A["last_bar"], first_bar, _ss._FROZEN["fade_bars"],
                                        BASE["eod_cutoff"], 0, _ss._STRUCT_BUF,
                                        _ss._FROZEN["direction"]), deep)
    tl_re_off = _apply_tilt(_simulate_reentry(o, h, l, c, A["n"], A["warm"], A["mom"], A["atr"], A["fire"],
                                              A["rng_hi"], A["rng_lo"], A["gate_long"], A["gate_short"],
                                              A["last_bar"], _ss._FROZEN["fade_bars"],
                                              BASE["eod_cutoff"], _ss._STRUCT_BUF,
                                              _ss._FROZEN["direction"], "off"), deep)

    def _usd_of(rows):
        return (np.array([r[2] for r in rows], float) - COST[INST]) * MULT[INST] if rows else np.array([])

    real_usd = _usd_of(real_trades)
    bod0_usd = _usd_of(tl_bod0)
    re_off_usd = _usd_of(tl_re_off)
    match_bod = (real_trades is not None and len(real_trades) == len(tl_bod0)
                and np.allclose(real_usd, bod0_usd))
    match_re = (real_trades is not None and len(real_trades) == len(tl_re_off)
               and np.allclose(real_usd, re_off_usd))
    s_real, slb_real, _ = _score_rows(df, [(t[0], t[1], t[2]) for t in real_trades])
    s_bod0, slb_bod0, _ = _score_rows(df, tl_bod0)
    s_re_off, slb_re_off, _ = _score_rows(df, tl_re_off)
    L.append("  fenced file (TTMSQZ_3_0_ES30SS20)      : n=%d PF=%.2f net=$%s DD=$%s | lockbox $%s PF %.2f"
             % (s_real["n"], s_real["pf"], _fmt(s_real["net"]), _fmt(s_real["dd"]),
                _fmt(slb_real["net"]), slb_real["pf"]))
    L.append("  this file, bod-loop  (bod_cutoff=0)     : n=%d PF=%.2f net=$%s DD=$%s | lockbox $%s PF %.2f  "
             "IDENTICAL: %s" % (s_bod0["n"], s_bod0["pf"], _fmt(s_bod0["net"]), _fmt(s_bod0["dd"]),
                               _fmt(slb_bod0["net"]), slb_bod0["pf"], match_bod))
    L.append("  this file, reentry-loop (mode='off')    : n=%d PF=%.2f net=$%s DD=$%s | lockbox $%s PF %.2f  "
             "IDENTICAL: %s" % (s_re_off["n"], s_re_off["pf"], _fmt(s_re_off["net"]), _fmt(s_re_off["dd"]),
                               _fmt(slb_re_off["net"]), slb_re_off["pf"], match_re))
    matches_ttmmd = (s_bod0["n"] == INCUMBENT["n"] and abs(s_bod0["net"] - INCUMBENT["net"]) < 1.0
                     and abs(s_bod0["dd"] - INCUMBENT["dd"]) < 1.0)
    L.append("  matches TTM.md's quoted incumbent (n=%d net=$%s DD=$%s): %s"
             % (INCUMBENT["n"], _fmt(INCUMBENT["net"]), _fmt(INCUMBENT["dd"]), matches_ttmmd))
    print("\n".join(L[-4:]), flush=True)
    if not (match_bod and match_re and matches_ttmmd):
        L.append("")
        L.append("  STOP - reproduction failed. Not proceeding on a scan that cannot reproduce its own "
                 "incumbent.")
        print(L[-1], flush=True)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
        return
    L.append("  reproduction OK - proceeding.")

    baseline_entry_bars = set(int(r[0]) for r in tl_bod0)
    baseline_usd_by_eb = {int(r[0]): u for r, u in zip(tl_bod0, bod0_usd)}

    # ================================================================================
    # GAP 1 - no cutoff at the session OPEN
    # ================================================================================
    L.append("")
    L.append("=" * 116)
    L.append("GAP 1 - a mirror of eod_cutoff at the open: no entries whose FIRE bar sits in the first N "
             "bars of the session (ES 30m RTH: bar 1 = 09:30-10:00). eod_cutoff stays at the "
             "incumbent's 1.")
    L.append("=" * 116)
    L.append(HDR)
    for N in (0, 1, 2, 3, 4):
        tl = _apply_tilt(_simulate_bod(o, h, l, c, A["n"], A["warm"], A["mom"], A["atr"], A["fire"],
                                       A["rng_hi"], A["rng_lo"], A["gate_long"], A["gate_short"],
                                       A["last_bar"], first_bar, _ss._FROZEN["fade_bars"],
                                       BASE["eod_cutoff"], N, _ss._STRUCT_BUF,
                                       _ss._FROZEN["direction"]), deep)
        s, slb, usd = _score_rows(df, tl)
        name = "bod_cutoff = %d%s" % (N, "  [= incumbent]" if N == 0 else "")
        emit(L, name, s, slb)
        if tl:
            emit_reasons(L, tl, usd)
        if N > 0 and tl:
            these_eb = set(int(r[0]) for r in tl)
            removed = baseline_entry_bars - these_eb
            added = these_eb - baseline_entry_bars
            if removed:
                rm_usd = np.array([baseline_usd_by_eb[eb] for eb in removed])
                rm_wins = int((rm_usd > 0).sum())
                L.append("      removed vs bod_cutoff=0: %d trades, worth $%s as a group "
                         "(%d winners / %d losers, mean $%s/trade)"
                         % (len(removed), _fmt(rm_usd.sum()), rm_wins, len(removed) - rm_wins,
                            _fmt(rm_usd.mean())))
            else:
                L.append("      removed vs bod_cutoff=0: 0 trades")
            if added:
                L.append("      WARNING - %d trade(s) appear that were NOT in bod_cutoff=0 (blocking "
                         "an early entry freed the position for a later fire): entry bars %s"
                         % (len(added), sorted(added)))
            print("\n".join(L[-2:] if not added else L[-3:]), flush=True)

    # ================================================================================
    # GAP 2 - re-entry once, same coil, after a stop-out
    # ================================================================================
    L.append("")
    L.append("=" * 116)
    L.append("GAP 2 - ONE re-entry per coil per session after a STOP-OUT (never after a fade exit or a "
             "session close): triggers when price closes back through the SAME level that stopped the "
             "trade, fills next bar's open, same direction, same structural stop (recomputed from the "
             "SAME original fire-bar range, not a new coil). 'any' = unconditional; 'gate' = only if "
             "the hourly verification is still on for that side at the trigger bar.")
    L.append("=" * 116)
    L.append(HDR)
    for mode, label in (("off", "reentry = off  [= incumbent]"),
                        ("any", "reentry = on, unconditional"),
                        ("gate", "reentry = on, hourly-gate still verifying")):
        tl = _apply_tilt(_simulate_reentry(o, h, l, c, A["n"], A["warm"], A["mom"], A["atr"], A["fire"],
                                           A["rng_hi"], A["rng_lo"], A["gate_long"], A["gate_short"],
                                           A["last_bar"], _ss._FROZEN["fade_bars"],
                                           BASE["eod_cutoff"], _ss._STRUCT_BUF,
                                           _ss._FROZEN["direction"], mode), deep)
        s, slb, usd = _score_rows(df, tl)
        emit(L, label, s, slb)
        if tl:
            emit_reasons(L, tl, usd)
            re_idx = [i for i, r in enumerate(tl) if len(r) > 7 and r[7]]
            if re_idx:
                re_usd = usd[re_idx]
                re_wins = int((re_usd > 0).sum())
                L.append("      second entries taken: %d, worth $%s as a group (%d winners / %d "
                         "losers, mean $%s/trade, PF %.2f)"
                         % (len(re_idx), _fmt(re_usd.sum()), re_wins, len(re_idx) - re_wins,
                            _fmt(re_usd.mean()),
                            min(99, (re_usd[re_usd > 0].sum() / -re_usd[re_usd < 0].sum())
                                if (re_usd < 0).any() else 99)))
            else:
                L.append("      second entries taken: 0")
            print("\n".join(L[-2:]), flush=True)

    # ================================================================================
    # VERDICT
    # ================================================================================
    L.append("")
    L.append("=" * 116)
    L.append("READ")
    L.append("=" * 116)
    print("\n".join(L[-3:]), flush=True)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\nlog ->", LOG)


if __name__ == "__main__":
    main()
