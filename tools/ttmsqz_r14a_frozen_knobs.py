"""
TTM SQUEEZE ROUND 14a - the two knobs nobody has ever searched, on the NEW (structural-stop) base.

Twelve rounds tuned the stop, the exit, the entry style, the verification length (gate_len) and
the size. Nothing ever moved these, on ANY base:
  1. `length`      - the BASE-timeframe squeeze length (Bollinger/Keltner/momentum window on the
                     traded 30-minute bars). Frozen at Carter's 20 in every fenced file ever written.
  2. `gate_tf_min` - the verification frame. Frozen at 60 minutes. Round 8 tried 120 and it FAILED,
                     but that was on run #299's ATR-stop base, before the structural stop (run #353)
                     existed - re-asked here on the base the book now carries.
Also never isolated at the base:
  3. `bb_mult`     - the Bollinger stdev multiplier (2.0), shared today between the base fire and
                     the hourly gate's own squeeze construction inside TTMSQZ_3_0._htf_gate.
  4. base `kc_mult` decoupled from the GATE's kc_mult - same sharing problem. TTMSQZ_3_0.py's
                     run_backtest hands `_htf_gate` the same bb_mult/kc_mult it uses for the base
                     fire, so a base-only knob needs its own construction. This file does that the
                     way tools/ttmsqz_r12a_squeeze_pro.py did for kc_mult: reuse `_t3.squeeze_indicators`
                     and `_t3._htf_gate` UNCHANGED, but call the gate with its own (bb_mult, kc_mult)
                     independent of what the fire uses. Nothing internal is rewritten; only the
                     wrapper that decides which numbers go where.

THE INCUMBENT (quoted from TTM.md / run #353, not re-derived): `TTMSQZ_3_0_ES30SS20.py`, ES 30m
RTH, kc_mult 1.5 (fire and gate, coupled), eod_cutoff 1, gate_len 20 - the structural stop (buffer
0) plus the validated 1.5x deep-squeeze tilt. Whole run: 357 trades, PF 2.91, net $101,017, DD
$4,338. Lockbox (>= 2025-07-01): $16,977 at PF 6.72. This is the leg the paper book carries.

MECHANISM REUSED, NOT REWRITTEN. This file imports TTMSQZ_3_0_ES30SS.py (`_ss`) and calls its own
`_simulate` (the structural-stop trade loop), `_deep_state` (the tilt's fixed 20/2.0/1.5/60m
definition - untouched, because the tilt is a separately validated mechanism, not one of the four
knobs under test here) and `_rescore` verbatim. The ONLY new code is `_build_arrays_gen`, a
generalised version of `_ss._build_arrays` that exposes `length`, `bb_mult`, `kc_mult` for the base
fire and `gate_tf_min`, `gate_len`, `gate_bb_mult`, `gate_kc_mult` for the gate as independent
arguments, built from `_t3.squeeze_indicators` / `_t3._htf_gate` / `_t3._session_last_bar` exactly
as `_ss._build_arrays` builds them - same order, same warm-up, same causal construction.

SANITY CHECK (this study's own version of the look-ahead audit the family caught a bug with
today): before any grid runs, this file calls the REAL fenced strategy file
TTMSQZ_3_0_ES30SS20.run_backtest at its own default knobs and checks the result is bit-identical
to this file's `_run_cell` at the matching config. If they disagree, the run stops - a disagreement
here would mean the "reused" harness silently diverged from the audited file, which is exactly the
kind of bug this family has caught before by turning a scan into a strategy file.

INFORMATION TIME (stated once, holds for every cell in this file, because the causal construction
is never touched): the base 30-minute fire is decided on bar u's CLOSE; the entry fills at bar
u+1's OPEN. The gate's state at bar u comes from the last COMPLETE higher-timeframe group as of
u's close (`_t3._htf_gate`'s own `searchsorted` construction) - never a group still forming. The
protective stop is set from the fire bar's own already-closed range. The tilt's compression ratio
is read from the last complete 60-minute group as of the bar before the fill (`eb - 1`), exactly as
`_ss.run_backtest` reads it. Nothing in this file reads a bar that has not yet closed.

RULES: pinned window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES cost 0.363 pts round
trip, $50/pt (from tools/ttmsqz_round6_parts.py - not re-derived). One knob at a time, ES 30m RTH
only (the incumbent's own tape - this is a SCAN, not a re-run of the whole family's timeframe
grid). No config is crowned, queued, or pushed to index.html.

Usage:  python tools/ttmsqz_r14a_frozen_knobs.py
Output: tools/data/ttmsqz_r14a_frozen_knobs.txt
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


r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r6")
_ss = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS.py"), "ttm_ss")
_ss20 = _mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SS20.py"), "ttm_ss20")
_t3 = _ss._t3    # TTMSQZ_3_0.py, unchanged

DATE_FROM, LB_FROM, DATE_TO = r6.DATE_FROM, r6.LB_FROM, r6.DATE_TO
COST, MULT = r6.COST, r6.MULT
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r14a_frozen_knobs.txt")

INCUMBENT = dict(n=357, pf=2.91, net=101017.0, dd=4338.0, lb=16977.0, lbpf=6.72)

# incumbent's own frozen knobs (matches _ss._FROZEN + the SS20 pin)
BASE = dict(length=20, bb_mult=2.0, kc_mult=1.5, gate_tf_min=60, gate_len=20,
            gate_bb_mult=2.0, gate_kc_mult=1.5, eod_cutoff=1, fade_bars=1, struct_buf=0.0)


# ---------------------------------------------------------------------------
# THE ONLY NEW CODE: a generalised _build_arrays that decouples (length, bb_mult, kc_mult) at
# the base fire from (gate_tf_min, gate_len, gate_bb_mult, gate_kc_mult) at the gate. Reuses
# _t3.squeeze_indicators / _t3._htf_gate / _t3._session_last_bar UNCHANGED - same functions the
# audited engine and _ss._build_arrays call, just handed independent numbers for the two roles.
# ---------------------------------------------------------------------------

def _build_arrays_gen(o, h, l, c, did, index, length, bb_mult, kc_mult,
                      gate_tf_min, gate_len, gate_bb_mult, gate_kc_mult):
    n = len(c)
    length = int(length)
    sq_on, mom, atr = _t3.squeeze_indicators(h, l, c, length, float(bb_mult), float(kc_mult))
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= 1)   # min_sq_bars = 1, frozen (incumbent value)
    warm = length * 2 + 5
    fire[:warm] = False
    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()
    gate_long, gate_short = _t3._htf_gate(
        h, l, c, did, index, 0, int(gate_tf_min), int(gate_len),
        float(gate_bb_mult), float(gate_kc_mult), "sq_on", 3, 1.0)
    last_bar = _t3._session_last_bar(did, n)
    return dict(n=n, warm=warm, mom=mom, atr=atr, fire=fire, rng_hi=rng_hi, rng_lo=rng_lo,
                gate_long=gate_long, gate_short=gate_short, last_bar=last_bar)


def _run_cell(df, length=20, bb_mult=2.0, kc_mult=1.5, gate_tf_min=60, gate_len=20,
             gate_bb_mult=None, gate_kc_mult=None, eod_cutoff=1, fade_bars=1,
             struct_buf=0.0, apply_tilt=True):
    """One cell of the structural-stop + tilt mechanism, base and gate knobs independent.
    gate_bb_mult/gate_kc_mult default to the BASE's own values (the incumbent's coupled
    behaviour) when not given - so callers that don't ask for decoupling reproduce the
    coupled engine exactly."""
    if gate_bb_mult is None:
        gate_bb_mult = bb_mult
    if gate_kc_mult is None:
        gate_kc_mult = kc_mult
    o = df["open"].values.astype(float); h = df["high"].values.astype(float)
    l = df["low"].values.astype(float); c = df["close"].values.astype(float)
    did = df["day_id"].values; index = df["_dt"]
    A = _build_arrays_gen(o, h, l, c, did, index, length, bb_mult, kc_mult,
                          gate_tf_min, gate_len, gate_bb_mult, gate_kc_mult)
    trade_log = _ss._simulate(o, h, l, c, A["n"], A["warm"], A["mom"], A["atr"], A["fire"],
                              A["rng_hi"], A["rng_lo"], A["gate_long"], A["gate_short"],
                              A["last_bar"], int(fade_bars), int(eod_cutoff), float(struct_buf), "both")
    if not trade_log:
        return None
    if apply_tilt:
        deep = _ss._deep_state(h, l, c, did, index)     # fixed 20/2.0/1.5/60m - untouched
        nn = len(deep)
        out = []
        for t in trade_log:
            eb = int(t[0])
            d = bool(deep[min(max(eb - 1, 0), nn - 1)])
            s = float(_ss._TILT_MULT) if d else 1.0
            pnl = s * float(t[2]) - (s - 1.0) * float(_ss._COST_PTS)
            out.append((eb, int(t[1]), pnl) + tuple(t[3:]))
        trade_log = out
    return trade_log


def _score_cell(df, trade_log, inst="ES"):
    if not trade_log:
        return None, None
    t = pd.DataFrame(trade_log, columns=["eb", "xb", "pnl", "side", "epx", "xpx"])
    usd = (t["pnl"].values - COST[inst]) * MULT[inst]
    dates = pd.DatetimeIndex(df["_dt"])[t["xb"].values].date
    s = r6.score(usd, dates)
    if s is None:
        return None, None
    yrs = max((max(dates) - min(dates)).days / 365.25, 1e-9)
    s["mar"] = (s["net"] / yrs) / s["dd"] if s["dd"] > 0 else float("nan")
    lbmask = np.array([d >= pd.Timestamp(LB_FROM).date() for d in dates])
    slb = r6.score(usd[lbmask], np.array(dates)[lbmask]) if lbmask.any() else None
    return s, slb


H = "  %-42s %5s %7s %12s %9s %7s | %11s %7s %6s"
HDR = H % ("cell", "n", "PF", "net $", "DD $", "MAR", "lockbox $", "LB PF", "LB n")


def _fmt_money(v):
    return "{:,.0f}".format(v)


def emit(lines, name, s, slb, flag=""):
    if s is None:
        lines.append("  %-42s  no trades" % name); print(lines[-1], flush=True); return
    row = H % (name, s["n"], "%.2f" % min(s["pf"], 99), _fmt_money(s["net"]), _fmt_money(s["dd"]),
              "%.3f" % s["mar"],
              _fmt_money(slb["net"]) if slb else "n/a",
              "%.2f" % min(slb["pf"], 99) if slb else "n/a",
              slb["n"] if slb else 0)
    if flag:
        row += "   " + flag
    lines.append(row)
    print(lines[-1], flush=True)


def beats_incumbent(s, slb):
    if s is None or slb is None:
        return False
    return s["pf"] >= INCUMBENT["pf"] and slb["net"] >= INCUMBENT["lb"]


def main():
    L = []
    L.append("TTM SQUEEZE ROUND 14a - the two frozen knobs (base length, gate_tf_min) + bb_mult + decoupled base "
             "kc_mult, on the STRUCTURAL-STOP base   %s" % time.strftime("%Y-%m-%d %H:%M"))
    L.append("window %s..%s, lockbox from %s, ES 30m RTH, cost %.3f pts, $%d/pt; mechanism = run #353's "
             "structural stop (buffer 0) + run #340's validated 1.5x deep-squeeze tilt (tilt definition FIXED "
             "at 20/2.0/1.5/60m throughout - not one of the knobs under test)"
             % (DATE_FROM, DATE_TO, LB_FROM, COST["ES"], MULT["ES"]))
    L.append("INCUMBENT (TTMSQZ_3_0_ES30SS20.py, quoted from TTM.md): n=%d PF=%.2f net=$%s DD=$%s | "
             "lockbox $%s PF=%.2f"
             % (INCUMBENT["n"], INCUMBENT["pf"], _fmt_money(INCUMBENT["net"]), _fmt_money(INCUMBENT["dd"]),
                _fmt_money(INCUMBENT["lb"]), INCUMBENT["lbpf"]))
    print("\n".join(L), flush=True)

    df = r6.load("ES", "30m", "RTH")

    # ---- SANITY CHECK: the real fenced file vs this file's _run_cell, bit for bit ----
    L.append("")
    L.append("=" * 118)
    L.append("SANITY CHECK - TTMSQZ_3_0_ES30SS20.run_backtest (the real fenced file) vs this file's _run_cell "
             "at the matching config")
    L.append("=" * 118)
    real = _ss20.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                              day_id=df["day_id"].values, index=df["_dt"], return_trades=True,
                              kc_mult=1.5, eod_cutoff=1, gate_len=20)
    mine = _run_cell(df, **BASE)
    real_trades = real["trades"] if real else None
    real_usd = (np.array([t[2] for t in real_trades]) - COST["ES"]) * MULT["ES"] if real_trades else None
    mine_usd = (np.array([t[2] for t in mine]) - COST["ES"]) * MULT["ES"] if mine else None
    match = (real_trades is not None and mine is not None and len(real_trades) == len(mine)
            and np.allclose(real_usd, mine_usd))
    s_real, slb_real = _score_cell(df, real_trades)
    L.append("  fenced file : n=%d PF=%.2f net=$%s DD=$%s | lockbox $%s PF %.2f" % (
        s_real["n"], s_real["pf"], _fmt_money(s_real["net"]), _fmt_money(s_real["dd"]),
        _fmt_money(slb_real["net"]), slb_real["pf"]))
    s_mine, slb_mine = _score_cell(df, mine)
    L.append("  this file   : n=%d PF=%.2f net=$%s DD=$%s | lockbox $%s PF %.2f" % (
        s_mine["n"], s_mine["pf"], _fmt_money(s_mine["net"]), _fmt_money(s_mine["dd"]),
        _fmt_money(slb_mine["net"]), slb_mine["pf"]))
    L.append("  IDENTICAL TRADES: %s   |   matches TTM.md's quoted incumbent (n=%d net=$%s): %s" % (
        match, INCUMBENT["n"], _fmt_money(INCUMBENT["net"]),
        s_mine["n"] == INCUMBENT["n"] and abs(s_mine["net"] - INCUMBENT["net"]) < 1.0))
    print("\n".join(L[-4:]), flush=True)
    if not match:
        L.append("")
        L.append("  STOP - the harness disagrees with the fenced file. Not proceeding on a scan that cannot "
                 "reproduce its own incumbent.")
        print(L[-1], flush=True)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
        return

    results = []   # (name, s, slb, info-time note)

    def run_and_record(section, name, **over):
        kw = dict(BASE); kw.update(over)
        tl = _run_cell(df, **kw)
        s, slb = _score_cell(df, tl)
        flag = "BEATS INCUMBENT (PF & lockbox net)" if beats_incumbent(s, slb) else ""
        emit(L, name, s, slb, flag)
        results.append((section, name, s, slb, kw))

    # ================= GRID 1: base length =================
    L.append("")
    L.append("=" * 118)
    L.append("GRID 1 - base squeeze length (Bollinger/Keltner/momentum window on the traded 30m bars). "
             "Gate untouched (60m, gate_len 20, coupled bb/kc at the incumbent's own values).")
    L.append("=" * 118)
    L.append(HDR)
    for length in (8, 10, 14, 20, 26, 34, 40):
        run_and_record("length", "length = %d%s" % (length, "  [incumbent]" if length == 20 else ""),
                       length=length)

    # ================= GRID 2: gate_tf_min =================
    L.append("")
    L.append("=" * 118)
    L.append("GRID 2 - verification frame (gate_tf_min), re-asked on the structural-stop base. Round 8 tried "
             "120 on the OLD (ATR-stop) base and it failed; base length stays 20, gate_len stays 20 (same "
             "convention round 8 used: the gate always reads 20 bars of ITS OWN frame).")
    L.append("=" * 118)
    L.append(HDR)
    for gtf in (30, 60, 120, 240):
        run_and_record("gate_tf_min", "gate_tf_min = %d%s" % (gtf, "  [incumbent]" if gtf == 60 else ""),
                       gate_tf_min=gtf)

    # ================= GRID 3: base bb_mult (decoupled from the gate's) =================
    L.append("")
    L.append("=" * 118)
    L.append("GRID 3 - base Bollinger multiplier, DECOUPLED from the gate's (gate_bb_mult pinned at the "
             "published 2.0 in every row here, via _build_arrays_gen's separate gate_bb_mult argument).")
    L.append("=" * 118)
    L.append(HDR)
    for bb in (1.5, 2.0, 2.5):
        run_and_record("bb_mult", "base bb_mult = %.2f (gate bb_mult fixed 2.0)%s" % (
                       bb, "  [incumbent]" if bb == 2.0 else ""),
                       bb_mult=bb, gate_bb_mult=2.0)

    # ================= GRID 4: base kc_mult decoupled from the gate's =================
    L.append("")
    L.append("=" * 118)
    L.append("GRID 4 - base Keltner multiplier, DECOUPLED from the gate's (gate_kc_mult pinned at the "
             "published 1.5 in every row here). TTMSQZ_3_0.py shares one kc_mult between the fire and the "
             "hourly gate; this grid asks what the FIRE alone wants once the gate's own coil definition is "
             "held fixed.")
    L.append("=" * 118)
    L.append(HDR)
    for kc in (1.0, 1.25, 1.5, 1.75, 2.0):
        run_and_record("kc_mult", "base kc_mult = %.2f (gate kc_mult fixed 1.5)%s" % (
                       kc, "  [incumbent, still coupled here]" if kc == 1.5 else ""),
                       kc_mult=kc, gate_kc_mult=1.5)

    # ================= best single-knob values, combined =================
    L.append("")
    L.append("=" * 118)
    L.append("COMBINATIONS - the best value(s) from each grid above, stacked. THESE ARE A SECOND LOOK AT THE "
             "SAME ~357 TRADES, not an independent test: any apparent win here is much weaker evidence than "
             "an equal-looking win in a single grid above, because the search space just grew and the same "
             "12 lockbox months are being asked again.")
    L.append("=" * 118)
    by_section = {}
    for section, name, s, slb, kw in results:
        if s is None:
            continue
        by_section.setdefault(section, []).append((s["pf"], name, kw))
    best = {}
    for section, rows in by_section.items():
        rows.sort(key=lambda r: r[0], reverse=True)
        best[section] = rows[0]
    L.append("  best cell per grid, by whole-run PF:")
    for section, (pf, name, kw) in best.items():
        L.append("    %-14s %s (PF %.2f)" % (section, name, pf))
    print("\n".join(L[-1 - len(best):]), flush=True)

    combo_kw = dict(BASE)
    for section in ("length", "gate_tf_min", "bb_mult", "kc_mult"):
        if section in best:
            combo_kw.update(best[section][2])
    L.append("")
    L.append(HDR)
    over = {k: v for k, v in combo_kw.items() if BASE.get(k) != v}
    run_and_record("COMBO", "all four best values stacked", **over)

    # pairwise: the two headline knobs only (length + gate_tf_min), holding bb/kc at incumbent
    pair_kw = dict(BASE)
    if "length" in best:
        pair_kw.update(best["length"][2])
    if "gate_tf_min" in best:
        pair_kw.update(best["gate_tf_min"][2])
    run_and_record("COMBO", "best length + best gate_tf_min only (headline pair)", **pair_kw)

    # ---- verdict ----
    L.append("")
    L.append("=" * 118)
    L.append("VERDICT - cells beating the incumbent on BOTH whole-run PF (>=%.2f) AND lockbox net (>=$%s)"
             % (INCUMBENT["pf"], _fmt_money(INCUMBENT["lb"])))
    L.append("=" * 118)
    winners = [(section, name, s, slb) for section, name, s, slb, kw in results if beats_incumbent(s, slb)]
    single_winners = [w for w in winners if w[0] != "COMBO"]
    combo_winners = [w for w in winners if w[0] == "COMBO"]
    if single_winners:
        for section, name, s, slb in single_winners:
            L.append("  SINGLE-KNOB WIN [%s]: %-42s PF %.2f (vs %.2f)  lockbox $%s (vs $%s)" % (
                section, name, s["pf"], INCUMBENT["pf"], _fmt_money(slb["net"]), _fmt_money(INCUMBENT["lb"])))
    else:
        L.append("  no single-knob cell beats the incumbent on both PF and lockbox net.")
    if combo_winners:
        for section, name, s, slb in combo_winners:
            L.append("  COMBO WIN (treat with suspicion - same trades, re-asked): %-42s PF %.2f  lockbox $%s"
                     % (name, s["pf"], _fmt_money(slb["net"])))
    else:
        L.append("  no combination cell beats the incumbent on both PF and lockbox net either.")
    print("\n".join(L[-(len(winners) + 3):]), flush=True)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\nlog ->", LOG)


if __name__ == "__main__":
    main()
