"""
NOISE 1.0 — EXIT / STOP research engine (PROMOTED from scratchpad 2026-08-08).

This is the round-16 exit/stop study driver: it tested 25 exit/stop variants
against the frozen NOISE 1.0 baseline (protective stops, time stops, and three
"replaces vwap" primary-exit alternatives) under a pre-registered adoption
rule, and found the winner shipped into augur_strategies/NOISE_1_0.py as
stop_mode='bandwidth' (k=1.0) -- see that file's 2026-08-08 docstring block
and docs/samples/noise_exits_report.md for the full writeup and results table.

Promoted here (not left in scratchpad) per the standing EDGELOG lesson that
scratchpads are VOLATILE — the temp working directory they live in gets wiped
between sessions, and this driver + its numbers are worth keeping reproducible
in the repo. Originally: scratchpad/noise_exits.py.

Forked from tools/noise_research.py (NOT edited in place — that file + the
augur_strategies/NOISE_1_0.py plugin stay untouched by this file). Entry logic and band math
(_session_bounds, compute_sigma_matrix, UB/LB formula, STEP A/D/E of the bar loop,
the sigma warmup) are copied BYTE-IDENTICAL from that file. The only thing this
file adds is exit/stop machinery: an optional ADDITIONAL protective stop checked
intrabar each bar (stop-first pessimism, gap-through fill at the bar's open —
same convention as ORB_3_1/ORB_2_0's trailing/ATR stops), an optional time stop,
and three "replaces vwap" primary-exit alternatives (EMA cross, chandelier trail,
N-bar prior-extreme trail).

SANITY GATE: with no protective stop / no time stop / primary='vwap', this engine
must reproduce the frozen NOISE_1_0 numbers exactly: n=3147, net=$254,382.98,
PF=1.3110, DD=-$31,239.80, MAR=8.1429 (checked at the top of __main__ below,
hard-fails the run if it doesn't match).

CONVENTIONS (stated once, applied uniformly):
  - ATR20d = average of (session high - session low) over the PRIOR 20 sessions
    (strictly prior, no lookahead) — same convention as ORB_2_0/ORB_3_2's
    session_atr (atr_period sessions of session range, not a Wilder bar-ATR).
    Sessions before 20 prior sessions exist -> ATR is NaN -> protective stop is
    skipped for that specific trade (falls back to no-stop; affects only the
    handful of trades between session index 14 (sigma warmup) and 20 (ATR
    warmup) if lookback=14, ATR period=20).
  - Protective/trailing intrabar stops (A, B, C, D, G, H) NEVER check on the bar
    the position was just filled (k == entry_k) — mirrors ORB_3_1's `continue`
    after setting up a new position, which defers the first stop check to the
    NEXT bar. The primary vwap/band/ema close-cross exit (STEP C) has no such
    exclusion (matches the original engine's own behaviour, unchanged).
  - Stop-first pessimism + gap-through: if the bar's OPEN is already through the
    stop level, fill at the open (can't get the stop price); else if the bar's
    low/high touches the level intrabar, fill AT the level.
  - Band-width stop (B): "t_entry" = the FILL bar (entry_k), matching every other
    entry_px/entry_k bookkeeping convention already in this engine.
  - EMA(n) (F) is a standard continuous indicator computed over the WHOLE closes
    series (not reset per session) — pandas .ewm(span=n, adjust=False).mean().
  - Chandelier (G) / N-bar trail (H): ratchet-only, using PRIOR bars since entry
    (excludes the current bar k) — identical windowing convention to ORB_3_1's
    trail_bars.
  - Time stop (E): checked every bar once (k - entry_k) >= N; the first bar at or
    after N bars where the position is not profitable at that bar's CLOSE, exit
    immediately AT that close (no next-open queue, unlike vwap/band/ema).
  - "Shadow" counterfactual (for the why-paragraph cost metric): whenever a trade
    closes via 'stop' or 'time' (not 'primary'/'eod'), a side computation
    continues the SAME position forward from that same bar using ONLY the vwap
    close-cross rule (ignoring the stop/time condition) to see what it would
    eventually have realized. This only applies to variants A/B/C/D/E/I, which
    keep vwap as the primary exit; it doesn't apply to F/G/H, which replace vwap
    entirely (there is no "stopped out of the vwap exit" concept there).

ALL data loads in this file are pinned date_to="2025-06-29" (pre-lockbox only)
EXCEPT the single clearly-labelled SPENT-YEAR OBSERVATION block at the very end
of __main__, which is informational-only and never feeds back into selection.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.engine import _apply_costs                    # noqa: E402

FEE, MULT = 0.533, 20.0
DATE_TO_PRELOCKBOX = "2025-06-29"
LOCKBOX_FROM = "2025-06-30"
LOCKBOX_TO = "2026-06-30"

FROZEN_PARAMS = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                      side="Both", window="all_day")
ATR_PERIOD = 20


# ─────────────────────────────────────────────────────────────────────────────
# Byte-identical entry/band machinery (copied from tools/noise_research.py)
# ─────────────────────────────────────────────────────────────────────────────
def _session_bounds(day_id):
    bounds = []
    n = len(day_id)
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b))
        a = b
    return bounds


def compute_sigma_matrix(opens, closes, sess_bounds, lookback):
    n_sess = len(sess_bounds)
    max_len = max(b - a for a, b in sess_bounds) if sess_bounds else 0
    AD = np.full((n_sess, max_len), np.nan, dtype=float)
    for si, (a, b) in enumerate(sess_bounds):
        o0 = opens[a]
        m = b - a
        AD[si, :m] = np.abs(closes[a:b] - o0) / o0
    sigma = np.full((n_sess, max_len), np.nan, dtype=float)
    with np.errstate(invalid="ignore"):
        for si in range(lookback, n_sess):
            window = AD[si - lookback:si, :]
            sigma[si, :] = np.nanmean(window, axis=0)
    return sigma


def compute_atr_by_session(highs, lows, sess_bounds, period):
    """ATR20d convention: mean of (session high - session low) over the PRIOR
    `period` sessions (strictly prior, no lookahead). NaN until `period` prior
    sessions exist."""
    n_sess = len(sess_bounds)
    sess_range = np.array([highs[a:b].max() - lows[a:b].min() for a, b in sess_bounds], float)
    atr = np.full(n_sess, np.nan, dtype=float)
    for si in range(period, n_sess):
        atr[si] = sess_range[si - period:si].mean()
    return atr


def compute_ema_full(closes, n):
    return pd.Series(closes).ewm(span=n, adjust=False).mean().to_numpy()


# ─────────────────────────────────────────────────────────────────────────────
# Protective-stop level initialization (computed once at entry, except 'oppband'
# which is dynamic and read live from LB/UB each bar)
# ─────────────────────────────────────────────────────────────────────────────
def _init_stop_level(kind, k_mult, P, pos, entry_px, entry_k, UB, LB, ref_hi, ref_lo, atr_pts):
    if kind == "atr":
        if atr_pts is None or np.isnan(atr_pts):
            return None
        return (entry_px - k_mult * atr_pts) if pos > 0 else (entry_px + k_mult * atr_pts)
    if kind == "bandwidth":
        if pos > 0:
            band_val = UB[entry_k]
            if np.isnan(band_val):
                return None
            return entry_px - k_mult * (band_val - ref_hi)
        else:
            band_val = LB[entry_k]
            if np.isnan(band_val):
                return None
            return entry_px + k_mult * (ref_lo - band_val)
    if kind == "fixed":
        return (entry_px - P) if pos > 0 else (entry_px + P)
    if kind == "oppband":
        return None  # dynamic — read live each bar
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Shadow counterfactual: "if the stop/time-exit hadn't fired at bar k, what would
# the vwap exit eventually have realized (gross pts), continuing from bar k?"
# ─────────────────────────────────────────────────────────────────────────────
def _shadow_vwap_forward(k, m, so, sc, VWAP, entry_px, pos):
    kk = k
    while kk < m:
        is_last = (kk == m - 1)
        trig = False
        if VWAP is not None and not np.isnan(VWAP[kk]):
            if pos > 0 and sc[kk] < VWAP[kk]:
                trig = True
            elif pos < 0 and sc[kk] > VWAP[kk]:
                trig = True
        if trig:
            ex = sc[kk] if is_last else so[kk + 1]
            return (ex - entry_px) if pos > 0 else (entry_px - ex)
        if is_last:
            ex = sc[kk]
            return (ex - entry_px) if pos > 0 else (entry_px - ex)
        kk += 1
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Per-session simulator (generalized). primary in {'vwap','ema','chandelier','nbar_trail'}
# protective: dict {'kind': 'atr'|'bandwidth'|'oppband'|'fixed', 'k':.., 'P':..} or None
# time_stop_n: int or None
# ─────────────────────────────────────────────────────────────────────────────
def _simulate_session(so, sh, sl, sc, sv, sigma_row, ref_hi, ref_lo,
                       band_mult_long, band_mult_short, side, window,
                       primary="vwap", ema_row=None, atr_pts=None,
                       protective=None, time_stop_n=None,
                       trail_k=None, trail_bars_n=None):
    m = len(sc)
    with np.errstate(invalid="ignore"):
        UB = ref_hi * (1.0 + band_mult_long * sigma_row[:m])
        LB = ref_lo * (1.0 - band_mult_short * sigma_row[:m])

    VWAP = None
    if primary == "vwap" and sv is not None:
        typical = (sh + sl + sc) / 3.0
        cum_tpv = np.cumsum(typical * sv)
        cum_v = np.cumsum(sv)
        with np.errstate(invalid="ignore", divide="ignore"):
            VWAP = cum_tpv / cum_v
    # vwap is also needed as the SHADOW counterfactual reference even when the
    # primary exit is being augmented by a protective/time stop (primary=='vwap'
    # in that case anyway, so VWAP above already covers it).

    allow_long = side in ("Both", "Long Only")
    allow_short = side in ("Both", "Short Only")

    trades = []  # (entry_bar, exit_bar, pnl_pts_gross, pos, entry_px, exit_kind, shadow_pnl_or_None)
    pos = 0
    entry_px = 0.0
    entry_k = -1
    entry_pending = 0
    exit_pending = False
    stop_level = None
    chand_extreme = None  # running favorable extreme since entry, for chandelier

    for k in range(m):
        is_last = (k == m - 1)

        # STEP A — execute fills queued from the PREVIOUS bar's close signal.
        if exit_pending:
            ex_px = so[k]
            pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
            trades.append((entry_k, k, pnl, pos, entry_px, "primary", None))
            pos = 0
            exit_pending = False
            stop_level = None
            chand_extreme = None
        if entry_pending != 0 and pos == 0:
            pos = entry_pending
            entry_px = so[k]
            entry_k = k
            entry_pending = 0
            if protective is not None:
                stop_level = _init_stop_level(protective["kind"], protective.get("k"),
                                               protective.get("P"), pos, entry_px, entry_k,
                                               UB, LB, ref_hi, ref_lo, atr_pts)
            if primary == "chandelier":
                chand_extreme = sh[entry_k] if pos > 0 else sl[entry_k]

        # STEP B — protective stop / primary trailing-stop intrabar check.
        # NEVER checked on the bar the position was just filled (k == entry_k) —
        # ORB convention (first check deferred to k == entry_k + 1).
        if pos != 0 and k != entry_k:
            level = None
            if protective is not None:
                if protective["kind"] == "oppband":
                    level = LB[k] if pos > 0 else UB[k]
                else:
                    level = stop_level
            elif primary == "chandelier":
                if pos > 0:
                    hh = sh[entry_k:k].max()
                    chand_extreme = max(chand_extreme, hh) if chand_extreme is not None else hh
                    level = chand_extreme - trail_k * atr_pts if atr_pts is not None and not np.isnan(atr_pts) else None
                else:
                    ll = sl[entry_k:k].min()
                    chand_extreme = min(chand_extreme, ll) if chand_extreme is not None else ll
                    level = chand_extreme + trail_k * atr_pts if atr_pts is not None and not np.isnan(atr_pts) else None
            elif primary == "nbar_trail":
                ts = max(entry_k, k - trail_bars_n)
                if pos > 0:
                    lvl = sl[ts:k].min()
                    stop_level = max(stop_level, lvl) if stop_level is not None else lvl
                else:
                    lvl = sh[ts:k].max()
                    stop_level = min(stop_level, lvl) if stop_level is not None else lvl
                level = stop_level

            if level is not None and not np.isnan(level):
                if pos > 0:
                    if so[k] < level:
                        ex_px = so[k]
                        pnl = ex_px - entry_px
                        shadow = _shadow_vwap_forward(k, m, so, sc, VWAP, entry_px, pos) if protective is not None else None
                        trades.append((entry_k, k, pnl, 1, entry_px, "stop", shadow))
                        pos = 0
                    elif sl[k] <= level:
                        ex_px = level
                        pnl = ex_px - entry_px
                        shadow = _shadow_vwap_forward(k, m, so, sc, VWAP, entry_px, pos) if protective is not None else None
                        trades.append((entry_k, k, pnl, 1, entry_px, "stop", shadow))
                        pos = 0
                else:
                    if so[k] > level:
                        ex_px = so[k]
                        pnl = entry_px - ex_px
                        shadow = _shadow_vwap_forward(k, m, so, sc, VWAP, entry_px, pos) if protective is not None else None
                        trades.append((entry_k, k, pnl, -1, entry_px, "stop", shadow))
                        pos = 0
                    elif sh[k] >= level:
                        ex_px = level
                        pnl = entry_px - ex_px
                        shadow = _shadow_vwap_forward(k, m, so, sc, VWAP, entry_px, pos) if protective is not None else None
                        trades.append((entry_k, k, pnl, -1, entry_px, "stop", shadow))
                        pos = 0

        # STEP B2 — time stop (checked every bar once N bars have elapsed).
        if pos != 0 and time_stop_n is not None and (k - entry_k) >= time_stop_n:
            cur = (sc[k] - entry_px) if pos > 0 else (entry_px - sc[k])
            if cur <= 0:
                pnl = cur
                shadow = _shadow_vwap_forward(k, m, so, sc, VWAP, entry_px, pos)
                trades.append((entry_k, k, pnl, pos, entry_px, "time", shadow))
                pos = 0

        # STEP C — primary close-cross exit trigger (vwap / ema).
        if pos != 0 and primary in ("vwap", "ema"):
            trig = False
            if primary == "vwap" and VWAP is not None and not np.isnan(VWAP[k]):
                if pos > 0 and sc[k] < VWAP[k]:
                    trig = True
                elif pos < 0 and sc[k] > VWAP[k]:
                    trig = True
            elif primary == "ema" and ema_row is not None and not np.isnan(ema_row[k]):
                if pos > 0 and sc[k] < ema_row[k]:
                    trig = True
                elif pos < 0 and sc[k] > ema_row[k]:
                    trig = True
            if trig:
                if is_last:
                    ex_px = sc[k]
                    pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                    trades.append((entry_k, k, pnl, pos, entry_px, "primary", None))
                    pos = 0
                else:
                    exit_pending = True

        # STEP D — new-entry signal at THIS bar's close (only if now flat).
        if pos == 0 and not is_last and 1 <= k <= m - 2:
            in_window = True
            if window == "morning":
                in_window = (k <= 29)
            elif window == "afternoon_block":
                in_window = (k <= m - 26)
            if in_window:
                ub_k, lb_k = UB[k], LB[k]
                long_trig = allow_long and (not np.isnan(ub_k)) and (sc[k] > ub_k)
                short_trig = allow_short and (not np.isnan(lb_k)) and (sc[k] < lb_k)
                if long_trig and short_trig:
                    entry_pending = 1 if (sc[k] - ub_k) >= (lb_k - sc[k]) else -1
                elif long_trig:
                    entry_pending = 1
                elif short_trig:
                    entry_pending = -1

        # STEP E — EOD backstop.
        if is_last and pos != 0:
            ex_px = sc[k]
            pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
            trades.append((entry_k, k, pnl, pos, entry_px, "eod", None))
            pos = 0

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Top-level driver
# ─────────────────────────────────────────────────────────────────────────────
def run_variant(O, H, L, C, V, DID, sigma, atr_by_session, sess_bounds,
                lookback, band_mult_long, band_mult_short, side, window,
                primary="vwap", ema_full=None, protective=None, time_stop_n=None,
                trail_k=None, trail_bars_n=None):
    all_trades = []
    prev_close = None
    for si, (a, b) in enumerate(sess_bounds):
        so, sh, sl, sc = O[a:b], H[a:b], L[a:b], C[a:b]
        sv = V[a:b] if V is not None else None
        ema_row = ema_full[a:b] if ema_full is not None else None
        if prev_close is not None and si >= lookback:
            ref_hi = max(so[0], prev_close)
            ref_lo = min(so[0], prev_close)
            sigma_row = sigma[si, :]
            atr_pts = atr_by_session[si] if atr_by_session is not None else None
            local = _simulate_session(
                so, sh, sl, sc, sv, sigma_row, ref_hi, ref_lo,
                band_mult_long, band_mult_short, side, window,
                primary=primary, ema_row=ema_row, atr_pts=atr_pts,
                protective=protective, time_stop_n=time_stop_n,
                trail_k=trail_k, trail_bars_n=trail_bars_n)
            for (ek, xk, pnl, p, epx, kind, shadow) in local:
                all_trades.append((a + ek, a + xk, pnl, p, epx, kind, shadow))
        prev_close = sc[-1]
    all_trades.sort(key=lambda t: t[0])
    return all_trades


def metrics_from_trades(trades, cost_pts, mult, bar_index):
    """Full metrics dict incl. worst trade, p99/median loss, 2010-2017 subtotal,
    per-year net, and the % of stopped/time-exited trades that would have
    recovered without the stop (shadow counterfactual)."""
    res = _apply_costs({"trades": list(trades)}, cost_pts)
    net_trades = res["trades"]
    pnls_usd = np.array([t[2] * mult for t in net_trades], float)
    wins = pnls_usd[pnls_usd > 0]
    losses = pnls_usd[pnls_usd < 0]
    dd_usd = res["max_drawdown"] * mult
    net_usd = res["total_pnl"] * mult
    mar = (net_usd / abs(dd_usd)) if abs(dd_usd) > 1e-9 else float("inf")
    avg_loss_pts = (-sum(t[2] for t in net_trades if t[2] < 0) / len(losses)) if len(losses) else 0.0
    worst_trade = float(pnls_usd.min()) if len(pnls_usd) else 0.0
    p99_loss = float(np.percentile(np.abs(losses), 99)) if len(losses) else 0.0
    median_loss = float(np.median(np.abs(losses))) if len(losses) else 0.0

    per_year = {}
    for t in net_trades:
        entry_bar = t[0]
        yr = int(bar_index[entry_bar].year)
        per_year[yr] = per_year.get(yr, 0.0) + float(t[2]) * mult
    subtotal_2010_17 = float(sum(v for y, v in per_year.items() if 2010 <= y <= 2017))

    # shadow counterfactual: among trades closed via 'stop' or 'time' (index 5),
    # what fraction would have ended net-profitable (shadow pnl - cost_pts > 0)?
    stopped = [t for t in net_trades if t[5] in ("stop", "time")]
    n_stopped = len(stopped)
    n_would_recover = 0
    for t in stopped:
        shadow_gross = t[6]
        if shadow_gross is not None:
            shadow_net = shadow_gross - cost_pts
            if shadow_net > 0:
                n_would_recover += 1
    pct_would_recover = (100.0 * n_would_recover / n_stopped) if n_stopped else None

    worst5 = sorted(net_trades, key=lambda t: t[2] * mult)[:5]
    worst5_fmt = [{"entry_bar": int(t[0]), "date": str(bar_index[t[0]])[:16],
                    "pnl_usd": round(t[2] * mult, 2), "exit_kind": t[5]} for t in worst5]

    return {
        "num_trades": res["num_trades"], "net_usd": net_usd,
        "profit_factor": res["profit_factor"], "win_rate": res["win_rate"],
        "max_drawdown_usd": dd_usd, "mar": mar, "avg_loss_pts": avg_loss_pts,
        "worst_trade_usd": worst_trade, "p99_loss_usd": p99_loss,
        "median_loss_usd": median_loss, "subtotal_2010_2017": subtotal_2010_17,
        "per_year": {str(y): round(v, 2) for y, v in sorted(per_year.items())},
        "n_stopped": n_stopped, "n_would_recover": n_would_recover,
        "pct_would_recover": pct_would_recover,
        "worst5": worst5_fmt,
        "net_trades": net_trades,
    }


BASELINE_WORST_TRADE = -15465.66
BASELINE_NET = 254382.98
BASELINE_MAR = 8.1429


def check_conditions(m):
    """Pre-registered adoption rule, applied mechanically. Returns dict of
    cond1..cond4 booleans + overall adoptable/risk_only flags."""
    cond1 = bool(abs(m["worst_trade_usd"]) <= 0.60 * abs(BASELINE_WORST_TRADE))  # reduced >=40%
    cond2 = bool(m["net_usd"] >= 0.85 * BASELINE_NET)
    cond3 = bool(m["mar"] >= BASELINE_MAR)
    cond4 = bool(m["subtotal_2010_2017"] >= 0.0)
    adoptable = bool(cond1 and cond2 and cond3 and cond4)
    risk_only = bool(cond1 and not adoptable)
    return {"cond1_worst_reduced_40pct": cond1, "cond2_net_ge_85pct": cond2,
            "cond3_mar_ge_baseline": cond3, "cond4_2010_17_nonneg": cond4,
            "adoptable": adoptable, "risk_only": risk_only}


if __name__ == "__main__":
    OUT_DIR = os.path.dirname(os.path.abspath(__file__))

    master = find_master("NQ", "5m", "rth", "db_noadj_rth")
    if master is None:
        print("NO MASTER FOUND"); sys.exit(1)

    print("=== Loading pre-lockbox data (date_to=%s) ===" % DATE_TO_PRELOCKBOX)
    arrays = load_master_arrays(master, date_from=None, date_to=DATE_TO_PRELOCKBOX)
    O, H, L, C, V, DID, IDX = (arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                               arrays.get("volume"), arrays["day_id"], arrays["index"])
    print("bars=%d volume=%s" % (len(C), "present" if V is not None else "MISSING"))

    sess_bounds = _session_bounds(DID)
    sigma = compute_sigma_matrix(O, C, sess_bounds, FROZEN_PARAMS["lookback"])
    atr20 = compute_atr_by_session(H, L, sess_bounds, ATR_PERIOD)
    n_atr_nan_but_sigma_ok = sum(
        1 for si in range(FROZEN_PARAMS["lookback"], len(sess_bounds)) if np.isnan(atr20[si]))
    print("sessions=%d, ATR20-NaN-but-sigma-valid sessions=%d (early warmup window)" %
          (len(sess_bounds), n_atr_nan_but_sigma_ok))

    ema_cache = {n: compute_ema_full(C, n) for n in (9, 20, 50)}

    # ── SANITY GATE ──────────────────────────────────────────────────────────
    base_trades = run_variant(O, H, L, C, V, DID, sigma, atr20, sess_bounds,
                               primary="vwap", **FROZEN_PARAMS)
    base_m = metrics_from_trades(base_trades, FEE, MULT, IDX)
    ok = (base_m["num_trades"] == 3147 and abs(base_m["net_usd"] - 254382.98) < 1.0
          and abs(base_m["profit_factor"] - 1.3110) < 0.001
          and abs(base_m["max_drawdown_usd"] + 31239.80) < 1.0
          and abs(base_m["mar"] - 8.1429) < 0.001)
    print("\n=== SANITY GATE (must match frozen baseline exactly) ===")
    print("  n=%d net=$%s PF=%.4f DD=$%s MAR=%.4f" % (
        base_m["num_trades"], format(base_m["net_usd"], ",.2f"), base_m["profit_factor"],
        format(base_m["max_drawdown_usd"], ",.2f"), base_m["mar"]))
    print("  SANITY GATE: %s" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("  ABORTING — the generalized engine does not reduce to the exact baseline.")
        sys.exit(1)

    results = {"baseline": base_m}
    all_rows = []

    def _run(vid, label, group, **kw):
        trades = run_variant(O, H, L, C, V, DID, sigma, atr20, sess_bounds, **FROZEN_PARAMS, **kw)
        m = metrics_from_trades(trades, FEE, MULT, IDX)
        cond = check_conditions(m)
        row = {"id": vid, "label": label, "group": group, "kw": {k: v for k, v in kw.items()
               if k not in ("ema_full",)}, **m, **cond}
        all_rows.append(row)
        print("  [%s] %-40s n=%-5d net=$%-12s PF=%-6.3f MAR=%-6.3f worst=$%-10s adoptable=%s risk_only=%s" % (
            vid, label, m["num_trades"], format(m["net_usd"], ",.0f"), m["profit_factor"], m["mar"],
            format(m["worst_trade_usd"], ",.0f"), cond["adoptable"], cond["risk_only"]))
        return row

    print("\n=== A. ATR catastrophic stop ===")
    for k in (1.0, 1.5, 2.0, 3.0, 4.0):
        _run("A_k%.1f" % k, "A: ATR20d stop k=%.1f" % k, "A",
             primary="vwap", protective={"kind": "atr", "k": k})

    print("\n=== B. Band-width stop ===")
    for k in (0.5, 1.0, 2.0):
        _run("B_k%.1f" % k, "B: band-width stop k=%.1f" % k, "B",
             primary="vwap", protective={"kind": "bandwidth", "k": k})

    print("\n=== C. Opposite-band structural stop ===")
    _run("C", "C: opposite-band stop", "C", primary="vwap", protective={"kind": "oppband"})

    print("\n=== D. Fixed-point stop ===")
    for P in (50, 100, 150, 250):
        _run("D_P%d" % P, "D: fixed stop P=%dpt" % P, "D",
             primary="vwap", protective={"kind": "fixed", "P": float(P)})

    print("\n=== E. Time stop ===")
    for N in (6, 12, 24):
        _run("E_N%d" % N, "E: time stop N=%d bars" % N, "E",
             primary="vwap", time_stop_n=N)

    print("\n=== F. EMA cross exit (REPLACES vwap) ===")
    for n in (9, 20, 50):
        _run("F_n%d" % n, "F: EMA(%d) cross exit" % n, "F",
             primary="ema", ema_full=ema_cache[n])

    print("\n=== G. Chandelier trail (REPLACES vwap) ===")
    for k in (2.0, 3.0):
        _run("G_k%.1f" % k, "G: chandelier trail k=%.1f x ATR20d" % k, "G",
             primary="chandelier", trail_k=k)

    print("\n=== H. N-bar prior-extreme trail (REPLACES vwap) ===")
    for nb in (5, 10, 20):
        _run("H_n%d" % nb, "H: %d-bar prior-extreme trail" % nb, "H",
             primary="nbar_trail", trail_bars_n=nb)

    # ── I. best-of-A + best-of-E, selected by the pre-registered rule ─────────
    a_rows = [r for r in all_rows if r["group"] == "A"]
    e_rows = [r for r in all_rows if r["group"] == "E"]
    a_adopt = [r for r in a_rows if r["adoptable"]]
    e_adopt = [r for r in e_rows if r["adoptable"]]
    a_pick = max(a_adopt, key=lambda r: r["mar"]) if a_adopt else max(a_rows, key=lambda r: r["mar"])
    e_pick = max(e_adopt, key=lambda r: r["mar"]) if e_adopt else max(e_rows, key=lambda r: r["mar"])
    a_fallback = len(a_adopt) == 0
    e_fallback = len(e_adopt) == 0
    print("\n=== I. Best-of-A + best-of-E composed ===")
    print("  A pick: %s (fallback-to-best-MAR-overall=%s)" % (a_pick["id"], a_fallback))
    print("  E pick: %s (fallback-to-best-MAR-overall=%s)" % (e_pick["id"], e_fallback))
    a_k = a_pick["kw"]["protective"]["k"]
    e_n = e_pick["kw"]["time_stop_n"]
    i_row = _run("I", "I: ATR stop k=%.1f + time stop N=%d" % (a_k, e_n), "I",
                  primary="vwap", protective={"kind": "atr", "k": a_k}, time_stop_n=e_n)
    i_row["a_pick_id"] = a_pick["id"]; i_row["e_pick_id"] = e_pick["id"]
    i_row["a_fallback"] = a_fallback; i_row["e_fallback"] = e_fallback

    # ── selection for the featured ADOPTABLE / RISK-ONLY variants ─────────────
    adoptable_rows = [r for r in all_rows if r["adoptable"]]
    risk_only_rows = [r for r in all_rows if r["risk_only"]]
    best_adoptable = max(adoptable_rows, key=lambda r: r["mar"]) if adoptable_rows else None
    best_risk_only = max(risk_only_rows, key=lambda r: r["mar"]) if risk_only_rows else None

    print("\n=== SELECTION ===")
    print("  ADOPTABLE variants: %d -> best = %s" %
          (len(adoptable_rows), best_adoptable["id"] if best_adoptable else "NONE"))
    print("  RISK-ONLY variants: %d -> best = %s" %
          (len(risk_only_rows), best_risk_only["id"] if best_risk_only else "NONE"))

    # ── tail comparison: top 5 by MAR (incl baseline reference) ───────────────
    top5_by_mar = sorted(all_rows, key=lambda r: r["mar"], reverse=True)[:5]

    # ── SPENT-YEAR OBSERVATION (single look, informational only) ──────────────
    featured = best_adoptable if best_adoptable is not None else best_risk_only
    spent_year_block = None
    if featured is not None:
        print("\n=== SPENT-YEAR OBSERVATION (one look, NOT evidence, does not change any verdict) ===")
        arrays_full = load_master_arrays(master, date_from=None, date_to=LOCKBOX_TO)
        Of, Hf, Lf, Cf, Vf, DIDf, IDXf = (arrays_full["open"], arrays_full["high"], arrays_full["low"],
                                          arrays_full["close"], arrays_full.get("volume"),
                                          arrays_full["day_id"], arrays_full["index"])
        sess_bounds_f = _session_bounds(DIDf)
        sigma_f = compute_sigma_matrix(Of, Cf, sess_bounds_f, FROZEN_PARAMS["lookback"])
        atr20_f = compute_atr_by_session(Hf, Lf, sess_bounds_f, ATR_PERIOD)
        kw = dict(featured["kw"])
        if kw.get("primary") == "ema":
            n_ema = None
            for cand_n, arr in ema_cache.items():
                pass
            # re-derive n from label
            import re
            mobj = re.search(r"EMA\((\d+)\)", featured["label"])
            n_ema = int(mobj.group(1)) if mobj else 20
            kw["ema_full"] = compute_ema_full(Cf, n_ema)
        full_trades = run_variant(Of, Hf, Lf, Cf, Vf, DIDf, sigma_f, atr20_f, sess_bounds_f,
                                   **FROZEN_PARAMS, **kw)
        full_m = metrics_from_trades(full_trades, FEE, MULT, IDXf)
        # isolate just the sealed year's trades (entry year >= mid-2025)
        sealed_net = sum(v for y, v in full_m["per_year"].items() if int(y) >= 2025) - \
                     sum(v for y, v in featured["per_year"].items() if int(y) >= 2025)
        spent_year_block = {
            "featured_variant": featured["id"], "featured_label": featured["label"],
            "full_window_2025_net_incl_sealed": full_m["per_year"].get("2025"),
            "prelockbox_2025_net_partial_year": featured["per_year"].get("2025"),
            "full_period_metrics": {k: full_m[k] for k in
                ("num_trades", "net_usd", "profit_factor", "win_rate", "max_drawdown_usd", "mar")},
        }
        print("  featured=%s full-window(incl sealed yr) net=$%s PF=%.3f MAR=%.3f" % (
            featured["id"], format(full_m["net_usd"], ",.0f"), full_m["profit_factor"], full_m["mar"]))

    # ── dump results json ──────────────────────────────────────────────────
    def _clean(row):
        r = dict(row)
        r.pop("net_trades", None)
        return r

    out = {
        "baseline": _clean(base_m),
        "variants": [_clean(r) for r in all_rows],
        "best_adoptable_id": best_adoptable["id"] if best_adoptable else None,
        "best_risk_only_id": best_risk_only["id"] if best_risk_only else None,
        "top5_by_mar_ids": [r["id"] for r in top5_by_mar],
        "variant_I_detail": {"a_pick": a_pick["id"], "e_pick": e_pick["id"],
                              "a_fallback": a_fallback, "e_fallback": e_fallback},
        "spent_year_observation": spent_year_block,
    }
    out_path = os.path.join(OUT_DIR, "noise_exits_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nWrote %s" % out_path)
