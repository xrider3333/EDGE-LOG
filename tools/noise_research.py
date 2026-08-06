"""
NOISE-2 RESEARCH ENGINE — intraday momentum envelope (Zarattini/Aziz/Barbon
"Beat the Market" concept: an envelope around the wider of {session open, prior
session close}, band width scaled by a rolling realized-noise estimate, momentum
breakout entries, mean-reversion-to-VWAP exits).

PROVENANCE / WHY THIS FILE EXISTS: the original round-11 research scratchpad
(scratchpad/r11_common.py + r11_noise2.py) was permanently lost to a temp-directory
cleanup 2026-08 — the July transcripts that could have reconstructed it are also
gone. This is a FAITHFUL REBUILD FROM SPEC, written directly against a written-out
engine description the reviewer (coordinator) held from the July work, and gated
against 20+ independent numeric checkpoints from that record (frozen config: n,
net $, PF, WR, maxDD, MAR, avg loss, turnover, and all 16 per-year net figures;
secondary config: n, net $, MAR). See tools/noise_research_checkpoints.md-equivalent
notes in the __main__ block below for the exact target numbers and the pass/fail
verdict from the most recent run.

Per the CLAUDE.md lesson memorialized 2026-08-06 ("scratchpad-only research code is
now banned"), this lives in tools/ as a first-class, committed repo module — NOT in
scratchpad/. augur_strategies/NOISE_1_0.py (the house-contract plugin) is PORTED
FROM and stays parity-gated against this file's numbers, not the other way around.

─────────────────────────────────────────────────────────────────────────────────
ENGINE SPEC (as specified by the coordinator, 2026-08-06 — implemented verbatim)
─────────────────────────────────────────────────────────────────────────────────
Data: NQ 5m RTH master, find_master("NQ","5m","rth","db_noadj_rth"),
load_master_arrays(..., date_to="2025-06-29"). Sessions = day_id blocks.

sigma[t] (per bar-index t within a session) = mean over the prior LOOKBACK sessions
i of |close_{i,t} - open_{i,0}| / open_{i,0}. Sessions shorter than t+1 bars do not
contribute at that t. If no prior session contributes at t -> no signal at t. The
first LOOKBACK sessions produce no trades (warmup) -- this falls out for free here
since sigma is all-NaN for si < LOOKBACK (no prior sessions exist yet).

prev_close = the immediately prior session's last close (unconditional -- every
session updates it, not just ones that traded). ref_hi = max(open[0], prev_close);
ref_lo = min(open[0], prev_close).

UB[t] = ref_hi x (1 + band_mult_long x sigma[t])
LB[t] = ref_lo x (1 - band_mult_short x sigma[t])

Signals evaluated at bar CLOSES, t from 1 to m-2 (no signal on bar 0 or the last
bar). If FLAT and close[t] > UB[t] -> LONG at open[t+1]. If FLAT and close[t] <
LB[t] -> SHORT at open[t+1]. If both true simultaneously, take the side whose band
was exceeded by more (in points). Opposite-side signals while in a position are
IGNORED (no flip). Re-entry after an exit within the same session IS allowed (one
position at a time).

side knob: 'Long Only'/'Short Only' suppress the other side's ENTRIES (band math
unchanged). window knob: 'morning' = signals only for t <= 29; 'afternoon_block' =
signals only for t <= m-26; open positions manage normally regardless of window.

Exits (checked each bar k while in a position, before any new entry logic -- i.e.
exit-processing for bar k always runs before that same bar's entry-signal check,
so a same-bar exit-then-re-entry is possible):
  vwap:      VWAP_k = cumulative(typical x volume) / cumulative(volume) over the
             session INCLUDING bar k, typical=(H+L+C)/3. Long: close[k] < VWAP_k
             -> exit at open[k+1] (if k is the last bar, exit at close[k]). Short
             mirrors (close[k] > VWAP_k).
  band:      long exits when close[k] < UB[k] -> exit at open[k+1]; short when
             close[k] > LB[k] -> open[k+1]. (Same last-bar exception as vwap.)
  boundary:  long -- intrabar stop at UB[k]: if open[k] < UB[k] -> fill at open[k]
             (gap-through), elif low[k] <= UB[k] -> fill at UB[k]. Short mirrors at
             LB[k] (open[k] > LB[k] -> open[k]; high[k] >= LB[k] -> LB[k]).
  Always flat at the session's last bar close (EOD backstop, regardless of mode).

Costs: this engine returns GROSS pnl_pts trades (exit-entry)*side, no cost baked
in. Net $ = (pnl_pts - cost_pts) x $mult applied DOWNSTREAM, via the exact same
augur_engine.engine._apply_costs() the house engine uses for every strategy plugin
(imported here, not reimplemented) -- so this research script's cost/metrics
convention is byte-identical to the plugin/engine path by construction.
─────────────────────────────────────────────────────────────────────────────────
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.engine import _apply_costs                    # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Session bookkeeping + the rolling sigma estimator
# ─────────────────────────────────────────────────────────────────────────────
def _session_bounds(day_id):
    """[(start_idx, end_idx_exclusive), ...] contiguous day_id blocks."""
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
    """sigma[si, t] = nanmean over sessions (si-lookback .. si-1) of
    |close_{i,t} - open_{i,0}| / open_{i,0}, where session i only contributes at
    position t if it has a bar there (i.e. its length > t). NaN wherever no prior
    session in that lookback window has a bar at t (including all si < lookback,
    which have no lookback window at all -> the documented warmup)."""
    n_sess = len(sess_bounds)
    max_len = max(b - a for a, b in sess_bounds) if sess_bounds else 0
    # AD[si, t] = |close - session_open| / session_open at bar t of session si,
    # NaN past that session's own length.
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


# ─────────────────────────────────────────────────────────────────────────────
# Per-session simulation
# ─────────────────────────────────────────────────────────────────────────────
def _simulate_session(so, sh, sl, sc, sv, sigma_row, ref_hi, ref_lo,
                       band_mult_long, band_mult_short, exit_mode, side, window):
    m = len(sc)
    with np.errstate(invalid="ignore"):
        UB = ref_hi * (1.0 + band_mult_long * sigma_row[:m])
        LB = ref_lo * (1.0 - band_mult_short * sigma_row[:m])

    VWAP = None
    if exit_mode == "vwap" and sv is not None:
        typical = (sh + sl + sc) / 3.0
        cum_tpv = np.cumsum(typical * sv)
        cum_v = np.cumsum(sv)
        with np.errstate(invalid="ignore", divide="ignore"):
            VWAP = cum_tpv / cum_v

    allow_long = side in ("Both", "Long Only")
    allow_short = side in ("Both", "Short Only")

    trades = []          # (entry_k, exit_k, pnl_pts_gross, pos, entry_px) -- session-local idx
    pos = 0
    entry_px = 0.0
    entry_k = -1
    entry_pending = 0    # 0 none, +1/-1 pending long/short, fills at THIS bar's open
    exit_pending = False # fills at THIS bar's open

    for k in range(m):
        is_last = (k == m - 1)

        # STEP A -- execute fills queued from the PREVIOUS bar's close signal.
        if exit_pending:
            ex_px = so[k]
            pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
            trades.append((entry_k, k, pnl, pos, entry_px))
            pos = 0
            exit_pending = False
        if entry_pending != 0 and pos == 0:
            pos = entry_pending
            entry_px = so[k]
            entry_k = k
            entry_pending = 0

        # STEP B -- boundary-mode intrabar exit (checked while in a position).
        if pos != 0 and exit_mode == "boundary":
            if pos > 0:
                band = UB[k]
                if not np.isnan(band):
                    if so[k] < band:
                        trades.append((entry_k, k, so[k] - entry_px, 1, entry_px))
                        pos = 0
                    elif sl[k] <= band:
                        trades.append((entry_k, k, band - entry_px, 1, entry_px))
                        pos = 0
            elif pos < 0:
                band = LB[k]
                if not np.isnan(band):
                    if so[k] > band:
                        trades.append((entry_k, k, entry_px - so[k], -1, entry_px))
                        pos = 0
                    elif sh[k] >= band:
                        trades.append((entry_k, k, entry_px - band, -1, entry_px))
                        pos = 0

        # STEP C -- vwap/band exit trigger evaluated at THIS bar's close.
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
                    trades.append((entry_k, k, pnl, pos, entry_px))
                    pos = 0
                else:
                    exit_pending = True

        # STEP D -- new-entry signal at THIS bar's close (only if now flat).
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

        # STEP E -- EOD backstop: force flat at the session's last bar close.
        if is_last and pos != 0:
            ex_px = sc[k]
            pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
            trades.append((entry_k, k, pnl, pos, entry_px))
            pos = 0

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Top-level driver
# ─────────────────────────────────────────────────────────────────────────────
def run_noise2(opens, highs, lows, closes, volumes=None, day_id=None,
               lookback=14, band_mult_long=1.5, band_mult_short=1.5,
               exit_mode="vwap", side="Both", window="all_day"):
    """Returns (gross_trades, sigma, sess_bounds, fell_back_to_band: bool).
    gross_trades: list of (entry_bar, exit_bar, pnl_pts_gross, side, entry_px)
    with GLOBAL bar indices, sorted by entry_bar."""
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float) if volumes is not None else None
    did = np.asarray(day_id)
    n = len(c)
    if did is None or len(did) != n:
        raise ValueError("day_id is required and must match the bar arrays' length")

    fell_back = False
    if exit_mode == "vwap" and v is None:
        exit_mode = "band"
        fell_back = True

    sess_bounds = _session_bounds(did)
    sigma = compute_sigma_matrix(o, c, sess_bounds, lookback)

    all_trades = []
    prev_close = None
    for si, (a, b) in enumerate(sess_bounds):
        m = b - a
        so, sh, sl, sc = o[a:b], h[a:b], l[a:b], c[a:b]
        sv = v[a:b] if v is not None else None
        if prev_close is not None and si >= lookback:
            ref_hi = max(so[0], prev_close)
            ref_lo = min(so[0], prev_close)
            sigma_row = sigma[si, :]
            local_trades = _simulate_session(
                so, sh, sl, sc, sv, sigma_row, ref_hi, ref_lo,
                band_mult_long, band_mult_short, exit_mode, side, window)
            for (ek, xk, pnl, pos, epx) in local_trades:
                all_trades.append((a + ek, a + xk, pnl, pos, epx))
        prev_close = sc[-1]

    all_trades.sort(key=lambda t: t[0])
    return all_trades, sigma, sess_bounds, fell_back


def backtest_metrics(trades, cost_pts, mult=20.0):
    """Apply the house cost/metrics convention (augur_engine.engine._apply_costs)
    to a gross trade list, scale to dollars, and return the headline dict."""
    res = _apply_costs({"trades": list(trades)}, cost_pts)
    net_trades = res["trades"]
    pnls_usd = [t[2] * mult for t in net_trades]
    wins = [x for x in pnls_usd if x > 0]
    losses = [x for x in pnls_usd if x < 0]
    dd_usd = res["max_drawdown"] * mult
    net_usd = res["total_pnl"] * mult
    mar = (net_usd / abs(dd_usd)) if abs(dd_usd) > 1e-9 else float("inf")
    avg_loss_pts = (-sum(t[2] for t in net_trades if t[2] < 0) / len(losses)) if losses else 0.0
    return {
        "num_trades": res["num_trades"],
        "net_usd": net_usd,
        "profit_factor": res["profit_factor"],
        "win_rate": res["win_rate"],
        "max_drawdown_usd": dd_usd,
        "mar": mar,
        "avg_loss_pts": avg_loss_pts,
        "trades_net": net_trades,
    }


def per_year_net(net_trades, bar_index, mult=20.0):
    """{year: net_usd} keyed by the ENTRY bar's calendar year (ET). Every NOISE-2
    trade opens and closes within the same RTH session, so entry-year vs exit-year
    is never ambiguous."""
    out = {}
    for (entry_bar, exit_bar, pnl_pts, pos, epx) in net_trades:
        yr = int(bar_index[entry_bar].year)
        out[yr] = out.get(yr, 0.0) + pnl_pts * mult
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint-gated smoke test
#   Run:  python tools/noise_research.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    DATE_TO = "2025-06-29"
    FEE, MULT = 0.533, 20.0

    master = find_master("NQ", "5m", "rth", "db_noadj_rth")
    if master is None:
        print("NO MASTER FOUND for NQ/5m/rth/db_noadj_rth -- check optimizer_history.db / augur_uploads/")
        sys.exit(1)
    arrays = load_master_arrays(master, date_from=None, date_to=DATE_TO)
    O, H, L, C, V, DID, IDX = (arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                               arrays.get("volume"), arrays["day_id"], arrays["index"])
    print("Loaded master: %s bars=%d volume=%s window ends %s" %
          (master.get("filename"), len(C), "present" if V is not None else "MISSING", DATE_TO))

    # ── Frozen config checkpoint ────────────────────────────────────────────
    FROZEN = dict(lookback=14, band_mult_long=1.50, band_mult_short=1.50,
                  exit_mode="vwap", side="Both", window="all_day")
    EXPECTED_FROZEN = {
        "num_trades": 3147, "net_usd": 254382.98, "profit_factor": 1.3110,
        "win_rate": 37.53, "max_drawdown_usd": -31239.80, "mar": 8.1429,
        "avg_loss_pts": 20.80, "turnover": 0.817,
    }
    EXPECTED_PER_YEAR = {
        2010: -2825, 2011: 236, 2012: 1421, 2013: 372, 2014: 4345, 2015: 6189,
        2016: 6443, 2017: -337, 2018: 36071, 2019: 6595, 2020: -7589, 2021: 42538,
        2022: 67713, 2023: 19429, 2024: 58085, 2025: 15695,
    }

    trades, sigma, sess_bounds, fell_back = run_noise2(O, H, L, C, V, DID, **FROZEN)
    m = backtest_metrics(trades, FEE, MULT)
    n_sessions = len(sess_bounds)
    n_qualifying = max(n_sessions - FROZEN["lookback"], 0)
    turnover = (m["num_trades"] / n_qualifying) if n_qualifying else 0.0
    pyear = per_year_net(m["trades_net"], IDX, MULT)

    print("\n=== FROZEN CONFIG (lookback=14, bml=bms=1.50, vwap, Both, all_day) ===")
    if fell_back:
        print("  WARNING: volumes missing -- vwap silently fell back to band exit")
    print("  n_sessions=%d  n_qualifying(sessions-lookback)=%d" % (n_sessions, n_qualifying))
    row_fmt = "  %-16s got=%-14s expected=%-14s delta"
    def _cmp(label, got, exp, is_pct=False):
        d = got - exp
        rel = (d / exp * 100.0) if exp else float("nan")
        print("  %-16s got=%-16s expected=%-16s delta=%+.4g (%.3f%%)" %
              (label, format(got, ",.4f") if isinstance(got, float) else got,
               format(exp, ",.4f") if isinstance(exp, float) else exp, d, rel))
    _cmp("n", m["num_trades"], EXPECTED_FROZEN["num_trades"])
    _cmp("net_usd", m["net_usd"], EXPECTED_FROZEN["net_usd"])
    _cmp("profit_factor", m["profit_factor"], EXPECTED_FROZEN["profit_factor"])
    _cmp("win_rate", m["win_rate"], EXPECTED_FROZEN["win_rate"])
    _cmp("max_dd_usd", m["max_drawdown_usd"], EXPECTED_FROZEN["max_drawdown_usd"])
    _cmp("mar", m["mar"], EXPECTED_FROZEN["mar"])
    _cmp("avg_loss_pts", m["avg_loss_pts"], EXPECTED_FROZEN["avg_loss_pts"])
    _cmp("turnover", turnover, EXPECTED_FROZEN["turnover"])

    print("\n  --- per-year net ($) ---")
    n_within_2000 = 0
    for yr in sorted(EXPECTED_PER_YEAR):
        got = pyear.get(yr, 0.0)
        exp = EXPECTED_PER_YEAR[yr]
        d = got - exp
        ok = abs(d) < 2000
        n_within_2000 += int(ok)
        print("  %d  got=$%-12s expected=$%-12s delta=$%+.0f  %s" %
              (yr, format(got, ",.0f"), format(exp, ",.0f"), d, "OK" if ok else "MISS"))
    print("  years within +/-$2000: %d/16" % n_within_2000)

    n_exact = (m["num_trades"] == EXPECTED_FROZEN["num_trades"])
    net_exact = abs(m["net_usd"] - EXPECTED_FROZEN["net_usd"]) < 1.0
    net_near = abs(m["net_usd"] - EXPECTED_FROZEN["net_usd"]) / EXPECTED_FROZEN["net_usd"] <= 0.02
    n_near = abs(m["num_trades"] - EXPECTED_FROZEN["num_trades"]) / EXPECTED_FROZEN["num_trades"] <= 0.01

    # ── Secondary checkpoint config ─────────────────────────────────────────
    SECONDARY = dict(lookback=14, band_mult_long=1.25, band_mult_short=1.25,
                      exit_mode="vwap", side="Both", window="all_day")
    EXPECTED_SECONDARY = {"num_trades": 4306, "net_usd": 253803.0, "mar": 6.90}

    trades2, *_ = run_noise2(O, H, L, C, V, DID, **SECONDARY)
    m2 = backtest_metrics(trades2, FEE, MULT)
    print("\n=== SECONDARY CONFIG (lookback=14, bml=bms=1.25, vwap, Both, all_day) ===")
    _cmp("n", m2["num_trades"], EXPECTED_SECONDARY["num_trades"])
    _cmp("net_usd", m2["net_usd"], EXPECTED_SECONDARY["net_usd"])
    _cmp("mar", m2["mar"], EXPECTED_SECONDARY["mar"])

    print("\n=== VERDICT ===")
    exact_both = (n_exact and net_exact and
                  m2["num_trades"] == EXPECTED_SECONDARY["num_trades"] and
                  abs(m2["net_usd"] - EXPECTED_SECONDARY["net_usd"]) < 1.0)
    if exact_both:
        print("  EXACT — both configs match to spec tolerance. Branch (a).")
    elif n_near and net_near and n_within_2000 >= 14:
        print("  NEAR — spec likely missing a micro-detail. Branch (b): try the 5 probe variants.")
    else:
        print("  FAR — outside NEAR tolerance. Branch (c): do not ship; report deltas for review.")
