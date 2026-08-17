"""
NOISE variant research engine — 2026-08-17 campaign.

Forked from augur_strategies/NOISE_1_0.py's run_backtest (byte-identical logic when
every new knob is at its default), plus new RESEARCH KNOBS, all default-off:

  rv_mode        'off' | 'exit_eod' | 'exit_band' | 'skip_hi' | 'skip_lo' | 'stop_scale'
                 Vol-regime behavior for a session whose PRIOR-day vol percentile is
                 extreme. Causal: measure = prior session's (H-L)/C, percentile-ranked
                 against the 252 sessions strictly before it (min 60 obs else inactive).
  rv_pct         high-tail threshold (default 90.0)
  rv_pct_lo      low-tail threshold for skip_lo (default 10.0)
  rv_stop_mult   stop_k multiplier when stop_scale regime active (default 1.0)
  confirm_bars   consecutive closes outside the band required to enter (default 1)
  time_stop_bars flat after this many bars in trade, exit next open (default 0 = off)
  stop_k_short   separate stop_k for shorts (default None = stop_k)
  daytype_mode   'off'|'skip_top_long'|'skip_top_all'|'skip_bot_short'|'skip_bot_all'
                 gate on PRIOR day's close-position-in-range (causal)
  daytype_hi/lo  0.8 / 0.2
  skip_after_loss block new entries the session after a net-losing traded session

All signals from FINISHED bars, fills at next bar open — NOISE's clean convention kept.
"""
import os, sys
import numpy as np

EDGELOG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if EDGELOG_ROOT not in sys.path:
    sys.path.insert(0, EDGELOG_ROOT)

from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.engine import _apply_costs                    # noqa: E402

FEE, MULT = 0.533, 20.0
SEL_DATE_TO = "2025-02-10"          # run #231 optimize-window end (selection window)
FULL_DATE_TO = "2026-08-12"         # confirmatory only

CHAMPION = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                exit_mode="vwap", side="Both", window="all_day",
                stop_mode="bandwidth", stop_k=1.75)


def _session_bounds(day_id, n):
    bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b)); a = b
    return bounds


def _sigma_matrix(o, c, sess_bounds, lookback):
    n_sess = len(sess_bounds)
    max_len = max((b - a) for a, b in sess_bounds) if sess_bounds else 0
    AD = np.full((n_sess, max_len), np.nan, dtype=float)
    for si, (a, b) in enumerate(sess_bounds):
        o0 = o[a]
        m = b - a
        AD[si, :m] = np.abs(c[a:b] - o0) / o0
    sigma = np.full((n_sess, max_len), np.nan, dtype=float)
    with np.errstate(invalid="ignore"):
        for si in range(lookback, n_sess):
            sigma[si, :] = np.nanmean(AD[si - lookback:si, :], axis=0)
    return sigma


def _vol_percentile(h, l, c, sess_bounds, ref_n=252, min_obs=60):
    """pct[si] = percentile rank of PRIOR session's (H-L)/C among the ref_n sessions
    strictly before that prior session. NaN when unavailable (treated as inactive)."""
    n_sess = len(sess_bounds)
    vals = np.array([(h[a:b].max() - l[a:b].min()) / c[b - 1] for a, b in sess_bounds], float)
    pct = np.full(n_sess, np.nan, dtype=float)
    for si in range(1, n_sess):
        j = si - 1                        # prior session (finished before si trades)
        lo = max(0, j - ref_n)
        ref = vals[lo:j]                  # strictly before session j
        if len(ref) >= min_obs:
            pct[si] = 100.0 * np.mean(ref < vals[j])
    return pct


def _daytype_pos(h, l, c, sess_bounds):
    """pos[si] = PRIOR session's (C-L)/(H-L). NaN when unavailable or zero-range."""
    n_sess = len(sess_bounds)
    cp = np.full(n_sess, np.nan, dtype=float)
    for si in range(1, n_sess):
        a, b = sess_bounds[si - 1]
        rng = h[a:b].max() - l[a:b].min()
        if rng > 1e-12:
            cp[si] = (c[b - 1] - l[a:b].min()) / rng
    return cp


def run_variant(opens, highs, lows, closes, volumes=None, day_id=None,
                lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                exit_mode="vwap", side="Both", window="all_day",
                stop_mode="off", stop_k=1.0,
                rv_mode="off", rv_pct=90.0, rv_pct_lo=10.0, rv_stop_mult=1.0,
                confirm_bars=1, time_stop_bars=0, stop_k_short=None,
                daytype_mode="off", daytype_hi=0.8, daytype_lo=0.2,
                skip_after_loss=False):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float) if volumes is not None else None
    n = len(c)
    did = np.asarray(day_id)
    if exit_mode == "vwap" and v is None:
        exit_mode = "band"
    allow_long  = side in ("Both", "Long Only")
    allow_short = side in ("Both", "Short Only")

    sess_bounds = _session_bounds(did, n)
    sigma = _sigma_matrix(o, c, sess_bounds, lookback)

    vol_pct = _vol_percentile(h, l, c, sess_bounds) if rv_mode != "off" else None
    dt_pos = _daytype_pos(h, l, c, sess_bounds) if daytype_mode != "off" else None

    sk_long = float(stop_k)
    sk_short = float(stop_k if stop_k_short is None else stop_k_short)

    trades = []          # (entry_bar, exit_bar, pnl_pts_gross, pos, entry_px) global idx
    prev_close = None
    prev_traded_net = 0.0   # prior TRADED session's gross net (for skip_after_loss)
    for si, (a, b) in enumerate(sess_bounds):
        m = b - a
        if prev_close is None or si < lookback:
            prev_close = c[b - 1]
            continue

        so, sh, sl, sc = o[a:b], h[a:b], l[a:b], c[a:b]
        sv = v[a:b] if v is not None else None
        ref_hi = max(so[0], prev_close)
        ref_lo = min(so[0], prev_close)
        sigma_row = sigma[si, :]
        with np.errstate(invalid="ignore"):
            UB = ref_hi * (1.0 + band_mult_long * sigma_row[:m])
            LB = ref_lo * (1.0 - band_mult_short * sigma_row[:m])

        # ── session-level regime resolution (all causal, prior-session data only) ──
        sess_exit_mode = exit_mode
        sess_block_entries = False
        sess_stop_scale = 1.0
        if rv_mode != "off" and vol_pct is not None and not np.isnan(vol_pct[si]):
            p = vol_pct[si]
            if rv_mode == "exit_eod" and p >= rv_pct:
                sess_exit_mode = "none"
            elif rv_mode == "exit_band" and p >= rv_pct:
                sess_exit_mode = "band"
            elif rv_mode == "skip_hi" and p >= rv_pct:
                sess_block_entries = True
            elif rv_mode == "skip_lo" and p <= rv_pct_lo:
                sess_block_entries = True
            elif rv_mode == "stop_scale" and p >= rv_pct:
                sess_stop_scale = rv_stop_mult
        block_long, block_short = False, False
        if daytype_mode != "off" and dt_pos is not None and not np.isnan(dt_pos[si]):
            dp = dt_pos[si]
            if daytype_mode == "skip_top_long" and dp >= daytype_hi:
                block_long = True
            elif daytype_mode == "skip_top_all" and dp >= daytype_hi:
                block_long = block_short = True
            elif daytype_mode == "skip_bot_short" and dp <= daytype_lo:
                block_short = True
            elif daytype_mode == "skip_bot_all" and dp <= daytype_lo:
                block_long = block_short = True
        if skip_after_loss and prev_traded_net < 0.0:
            sess_block_entries = True
            prev_traded_net = 0.0   # block exactly ONE session, then reset

        VWAP = None
        if sess_exit_mode == "vwap" and sv is not None:
            typical = (sh + sl + sc) / 3.0
            cum_tpv = np.cumsum(typical * sv)
            cum_v = np.cumsum(sv)
            with np.errstate(invalid="ignore", divide="ignore"):
                VWAP = cum_tpv / cum_v

        pos = 0; entry_px = 0.0; entry_k = -1
        entry_pending = 0
        exit_pending = False
        stop_level = None
        streak_long = 0; streak_short = 0
        sess_net = 0.0; sess_traded = False

        def _book(ek, xk, pnl, p, epx):
            nonlocal sess_net, sess_traded
            trades.append((a + ek, a + xk, pnl, p, epx))
            sess_net += pnl; sess_traded = True

        for k in range(m):
            is_last = (k == m - 1)

            # STEP A — execute fills queued from the PREVIOUS bar's close signal.
            if exit_pending:
                ex_px = so[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                _book(entry_k, k, pnl, pos, entry_px)
                pos = 0; exit_pending = False
            if entry_pending != 0 and pos == 0:
                pos = entry_pending; entry_px = so[k]; entry_k = k; entry_pending = 0
                stop_level = None
                sk = (sk_long if pos > 0 else sk_short) * sess_stop_scale
                if stop_mode == "bandwidth":
                    band_val = UB[k] if pos > 0 else LB[k]
                    if not np.isnan(band_val):
                        stop_level = (entry_px - sk * (band_val - ref_hi)) if pos > 0 \
                            else (entry_px + sk * (ref_lo - band_val))
                elif stop_mode == "fixed":
                    P = sk * 100.0
                    stop_level = (entry_px - P) if pos > 0 else (entry_px + P)

            # STEP A2 — protective stop, intrabar, never on the entry bar.
            if pos != 0 and k != entry_k and stop_level is not None and not np.isnan(stop_level):
                if pos > 0:
                    if so[k] < stop_level:
                        _book(entry_k, k, so[k] - entry_px, 1, entry_px); pos = 0
                    elif sl[k] <= stop_level:
                        _book(entry_k, k, stop_level - entry_px, 1, entry_px); pos = 0
                else:
                    if so[k] > stop_level:
                        _book(entry_k, k, entry_px - so[k], -1, entry_px); pos = 0
                    elif sh[k] >= stop_level:
                        _book(entry_k, k, entry_px - stop_level, -1, entry_px); pos = 0

            # STEP C — vwap/band exit trigger at THIS bar's close.
            if pos != 0 and sess_exit_mode in ("vwap", "band"):
                trig = False
                if sess_exit_mode == "vwap" and VWAP is not None and not np.isnan(VWAP[k]):
                    if pos > 0 and sc[k] < VWAP[k]:
                        trig = True
                    elif pos < 0 and sc[k] > VWAP[k]:
                        trig = True
                elif sess_exit_mode == "band":
                    if pos > 0 and not np.isnan(UB[k]) and sc[k] < UB[k]:
                        trig = True
                    elif pos < 0 and not np.isnan(LB[k]) and sc[k] > LB[k]:
                        trig = True
                if trig:
                    if is_last:
                        ex_px = sc[k]
                        pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                        _book(entry_k, k, pnl, pos, entry_px)
                        pos = 0
                    else:
                        exit_pending = True

            # STEP C2 — time-decay exit trigger at THIS bar's close (fills next open).
            if pos != 0 and not exit_pending and time_stop_bars > 0 and (k - entry_k) >= time_stop_bars:
                if is_last:
                    ex_px = sc[k]
                    pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                    _book(entry_k, k, pnl, pos, entry_px)
                    pos = 0
                else:
                    exit_pending = True

            # streak bookkeeping for confirm_bars (uses THIS bar's close vs THIS bar's band)
            if confirm_bars > 1:
                ub_k, lb_k = UB[k], LB[k]
                streak_long = streak_long + 1 if (not np.isnan(ub_k)) and sc[k] > ub_k else 0
                streak_short = streak_short + 1 if (not np.isnan(lb_k)) and sc[k] < lb_k else 0

            # STEP D — new-entry signal at THIS bar's close (only if now flat).
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

            # STEP E — EOD backstop.
            if is_last and pos != 0:
                ex_px = sc[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                _book(entry_k, k, pnl, pos, entry_px)
                pos = 0

        prev_close = sc[-1]
        if sess_traded:
            prev_traded_net = sess_net

    trades.sort(key=lambda t: t[0])
    return trades


def metrics(trades, index, cost_pts=FEE, mult=MULT):
    if not trades:
        return None
    res = _apply_costs({"trades": list(trades)}, cost_pts)
    net_trades = res["trades"]
    net_usd = res["total_pnl"] * mult
    dd_usd = res["max_drawdown"] * mult
    mar = (net_usd / abs(dd_usd)) if abs(dd_usd) > 1e-9 else float("inf")
    pyear = {}
    for (eb, xb, pnl, p, epx) in net_trades:
        yr = int(index[eb].year)
        pyear[yr] = pyear.get(yr, 0.0) + pnl * mult
    era_2010_17 = sum(vv for yy, vv in pyear.items() if 2010 <= yy <= 2017)
    worst_yr = min(pyear.items(), key=lambda kv: kv[1]) if pyear else (None, 0.0)
    return {
        "n": res["num_trades"], "net": net_usd, "pf": res["profit_factor"],
        "dd": dd_usd, "mar": mar, "win_rate": res["win_rate"],
        "pyear": pyear, "era_2010_17": era_2010_17,
        "worst_year": worst_yr[0], "worst_year_net": worst_yr[1],
    }


_ARR_CACHE = {}

def load_arrays(date_to=SEL_DATE_TO):
    if date_to in _ARR_CACHE:
        return _ARR_CACHE[date_to]
    master = find_master("NQ", "5m", "rth", "db_noadj_rth")
    if master is None:
        raise SystemExit("NO MASTER for NQ/5m/rth/db_noadj_rth")
    arr = load_master_arrays(master, date_from=None, date_to=date_to)
    _ARR_CACHE[date_to] = arr
    return arr


def run_cfg(params, date_to=SEL_DATE_TO):
    arr = load_arrays(date_to)
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    return metrics(tr, arr["index"])


def fmt(label, m):
    if m is None:
        return "%-42s NO TRADES" % label
    return ("%-42s n=%-5d net=$%-11s PF=%.3f DD=$%-10s MAR=%-6.2f "
            "2010-17=$%-9s worst=%s:$%s" % (
        label, m["n"], format(m["net"], ",.0f"), m["pf"], format(m["dd"], ",.0f"),
        m["mar"], format(m["era_2010_17"], ",.0f"),
        m["worst_year"], format(m["worst_year_net"], ",.0f")))


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint-gated smoke test (2026-08-17 campaign reference numbers)
#   Run:  python tools/noise_variant_research.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _chk(label, m, en, enet, edd):
        ok = m is not None and m["n"] == en and abs(m["net"] - enet) < 1 and abs(m["dd"] - edd) < 1
        print("%s\n  -> %s" % (fmt(label, m), "PASS" if ok else "FAIL (exp n=%d net=%.2f dd=%.2f)" % (en, enet, edd)))
        return ok

    print("Selection window = 2010-06-07 -> %s (run #231 optimize window; lockbox SPENT)\n" % SEL_DATE_TO)
    ok1 = _chk("BASELINE #231 champion", run_cfg(dict(CHAMPION)), 5113, 277123.31, -19482.27)
    ok2 = _chk("WINNER confirm2 + skip_bot_short",
               run_cfg(dict(CHAMPION, confirm_bars=2, daytype_mode="skip_bot_short")),
               4010, 332699.25, -14076.45)
    ok3 = _chk("Banked single vol_skip (skip_hi 90)",
               run_cfg(dict(CHAMPION, rv_mode="skip_hi", rv_pct=90.0)),
               4309, 310689.59, -19040.79)
    print("\nOVERALL: %s" % ("PASS" if (ok1 and ok2 and ok3) else "FAIL"))
    sys.exit(0 if (ok1 and ok2 and ok3) else 1)
