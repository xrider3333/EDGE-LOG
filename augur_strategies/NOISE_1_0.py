"""
NOISE 1.0 — wide-band intraday momentum envelope (VWAP-exit variant).

Concept credit: Zarattini/Aziz/Barbon "Beat the Market" — trade a session-relative
envelope: UB/LB anchored to the wider of {today's open, yesterday's close}, band
WIDTH scaled by a rolling realized-noise estimate (sigma = mean |close-open| /
open over the prior LOOKBACK sessions, read at the SAME bar-of-day index every
time). A CLOSE outside the band is the momentum entry, filled next bar's open; a
CLOSE back inside a reference (VWAP, by default) is the mean-reversion exit.
EDGELOG's challenger rounds 10-12 (2026-07) found the paper's own tight bands
(~1.0x, 14-day lookback) choppy/regime-fragile on NQ 5m — widening to 1.5x
SYMMETRIC bands + switching the exit from "back inside the entry band" to "back
below session VWAP" made the edge regime-healthy across the whole 2010-2025 span
instead of just a concentrated slice of it.

Full engine spec + the checkpoint-gated research build lives in
tools/noise_research.py (the "sigma[t] / ref_hi / ref_lo / signals at bar closes,
fills at next open / vwap-band-boundary exits / EOD flat" contract, INCLUDING the
warmup and re-entry rules) — this file is a straight, byte-for-byte port of that
engine into the house run_backtest(opens,highs,lows,closes,...) contract. Read
that file first if you're touching the entry/exit math; this docstring only
covers the plugin-specific surface (params, presets, validation status).

VALIDATION STATUS (stated honestly — read before treating this as "validated"):
  PASSED the IS/WF battery 4/5 (walk-forward 5/6 folds green, neighborhood
  stability, family-level consistency, bootstrap P ~ 0 on the in-sample edge).
  FAILED the ES-transfer gate (PF 1.12 on ES — doesn't survive the cross-
  instrument check the crowned strategies clear).
  The lockbox for this family has NEVER been spent.
  Net: this is an OWNER-DIRECTED BACKEND-TESTING PROMOTION, not a crowned
  strategy — it clears the owner's stated IS/WF bar, but it has NOT cleared the
  full validation roadmap (ES-transfer + lockbox are open items), and it is not
  in the current book. Runnable in Builder -> Auto-Validate for further work.

Reference numbers (frozen defaults, NQ 5m RTH, source=db_noadj_rth, cost_pts=0.533,
data <= 2025-06-29): n=3,147 trades, net $254,383, PF 1.31, DD -$31,240, MAR 8.14.
2010-2017 (the paper's own tighter-config era): +$15.8k net — the wide-band/VWAP-
exit config is what keeps that early stretch from being a drag, not a highlight.

Known weakness (banked autopsy): 2020 is the softest year in the per-year P&L —
the VWAP exit whipsaws hardest in extreme-volatility regimes (COVID crash/recovery)
because VWAP itself is at its noisiest exactly then. Not fixed here; a vol-regime
filter is the natural next lever if this gets picked up again.

PNL = SHARES*(EXIT-ENTRY); fees (cost_pts) are applied downstream by the engine,
not inside this file (see tools/noise_research.py's docstring for why that
convention matters: it's the same _apply_costs() every plugin goes through).
"""
import numpy as np

STRATEGY_NAME = 'NOISE 1.0 · intraday momentum envelope'
DESCRIPTION   = ("Wide symmetric bands (1.5x a rolling realized-noise estimate) around "
                 "the wider of today's open / yesterday's close. Momentum breakout entry "
                 "at the next bar's open, VWAP mean-reversion exit by default. NQ 5m "
                 "default. Owner-directed backend-testing promotion — passes the IS/WF "
                 "bar, has NOT cleared ES-transfer or the lockbox.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# From-scratch concept (Zarattini/Aziz/Barbon), not a fork of an existing EDGELOG
# family -- deliberately no _AUGUR_PARENT.

DEFAULT_PARAMS = {
    "lookback": {
        "default": 14, "min": 5, "max": 120, "step": 1, "type": "int",
        "label": "Noise lookback (sessions)",
        "tooltip": "How many PRIOR days feed the band-width estimate (how 'noisy' this "
                   "time of day usually is). 14 = the frozen/validated setting. Shorter "
                   "reacts faster to a changing regime but is a noisier estimate itself.",
    },
    "band_mult_long": {
        "default": 1.5, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Upper band width (x noise)",
        "tooltip": "How far above the reference level the long-side band sits, as a "
                   "multiple of the noise estimate. 1.5 validated -- WIDE on purpose. "
                   "Widths BELOW ~1.25 revert toward the original paper's config, which "
                   "EDGELOG's own testing found choppier / regime-concentrated (only "
                   "worked well in a slice of years) rather than robust across the full "
                   "2010-2025 span.",
    },
    "band_mult_short": {
        "default": 1.5, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Lower band width (x noise)",
        "tooltip": "Same as the upper band width, mirrored for the short side. 1.5 "
                   "validated (symmetric). Widths BELOW ~1.25 revert toward the original "
                   "paper's narrower, regime-concentrated config -- see the upper-band "
                   "tooltip.",
    },
    "exit_mode": {
        "default": "vwap", "type": "str",
        "options": ["vwap", "band", "boundary"],
        "label": "Exit rule",
        "tooltip": "vwap (validated default) = exit when price closes back across the "
                   "session's running VWAP -- needs volume data; silently falls back to "
                   "'band' if this master has none. band = exit when price closes back "
                   "INSIDE the entry band (the original paper's exit). boundary = a "
                   "tighter intrabar stop right at the band level (fills immediately on "
                   "a touch, not on the next bar's open) -- more trades, smaller ones, "
                   "unvalidated at scale.",
    },
    "side": {
        "default": "Both", "type": "str",
        "options": ["Both", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade either band break (validated). Long/Short Only for "
                   "research -- band math is unchanged, this only suppresses entries on "
                   "the disallowed side.",
    },
    "window": {
        "default": "all_day", "type": "str",
        "options": ["all_day", "morning", "afternoon_block"],
        "label": "Entry window",
        "tooltip": "all_day (validated) = new entries allowed any time. morning = only "
                   "take NEW entries in roughly the first 2.5 hours of the session. "
                   "afternoon_block = block NEW entries in roughly the last 2 hours. "
                   "Either way, a position already open keeps being managed normally -- "
                   "this only gates fresh signals.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight) -- this is a "
                   "hard rule of the engine itself (always applied, every session), not "
                   "actually a toggle. Keep ON; present for contract consistency with "
                   "the other EDGELOG strategy files.",
    },
    "skip_holidays": {
        "default": False, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close / half-day sessions (Thanksgiving, Christmas Eve, "
                   "Memorial Day, July-3, etc) -- detected by session LENGTH (a half-day "
                   "has far fewer bars than a normal RTH day), same helper as ORB_3_0. "
                   "OFF by default = no change (matches the validated numbers above); "
                   "turn ON to avoid them. The rolling noise estimate still LEARNS from "
                   "a skipped half-day (it's real market data); this only stops the "
                   "engine from trading it.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (frozen + near plateau)": {
        "lookback": [10, 14, 21], "band_mult_long": [1.4, 1.5, 1.6],
        "band_mult_short": [1.5], "exit_mode": ["vwap"], "side": ["Both"],
        "window": ["all_day"],
    },
    "Medium (round-11 core)": {
        "lookback": [14, 30], "band_mult_long": [1.0, 1.25, 1.5],
        "band_mult_short": [1.25, 1.5], "exit_mode": ["vwap", "band"],
        "side": ["Both", "Long Only"], "window": ["all_day"],
    },
    "Long   (full round-11 grid)": {
        # 3 lookback x 3 bml x 3 bms x 2 exit x 2 window = 108 cells (side held at
        # 'Both'; boundary exit excluded -- it's a different/unvalidated fill model,
        # kept out of the round-11-style vwap-vs-band sweep).
        "lookback": [10, 14, 21], "band_mult_long": [1.0, 1.25, 1.5],
        "band_mult_short": [1.0, 1.25, 1.5], "exit_mode": ["vwap", "band"],
        "side": ["Both"], "window": ["all_day", "morning"],
    },
}


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


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    lookback: int = 14, band_mult_long: float = 1.5, band_mult_short: float = 1.5,
    exit_mode: str = "vwap", side: str = "Both", window: str = "all_day",
    flat_eod: bool = True, skip_holidays: bool = False,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float) if volumes is not None else None
    n = len(c)
    if n < 10:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None

    # vwap needs volume -- silently fall back to the band exit if this master has none
    # (documented above; keeps the strategy usable on a volumeless master rather than
    # erroring out).
    if exit_mode == "vwap" and v is None:
        exit_mode = "band"

    allow_long  = side in ("Both", "Long Only")
    allow_short = side in ("Both", "Short Only")

    sess_bounds = _session_bounds(did, n)

    # Half-day / holiday skip (skip_holidays): identical helper to ORB_3_0/DRIVE_1_0 --
    # a session shorter than 70% of the MEDIAN session length is a half-day. OFF by
    # default = no change. The sigma estimate below still uses EVERY session's bars
    # (a half-day is real market data for the noise estimate) -- this flag only skips
    # TRADING it, same as ORB_3_0's convention.
    _holiday_start = set()
    if skip_holidays and len(sess_bounds) > 4:
        _lens = np.array([b - a for a, b in sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    sigma = _sigma_matrix(o, c, sess_bounds, lookback)

    pnl_list, trade_log = [], []
    prev_close = None
    for si, (a, b) in enumerate(sess_bounds):
        if _stop_event is not None and _stop_event.is_set():
            break
        m = b - a
        if a in _holiday_start:
            continue                                # skip trading AND state update, ORB-style
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

        VWAP = None
        if exit_mode == "vwap" and sv is not None:
            typical = (sh + sl + sc) / 3.0
            cum_tpv = np.cumsum(typical * sv)
            cum_v = np.cumsum(sv)
            with np.errstate(invalid="ignore", divide="ignore"):
                VWAP = cum_tpv / cum_v

        pos = 0; entry_px = 0.0; entry_k = -1
        entry_pending = 0        # queued long(+1)/short(-1) entry, fills at THIS bar's open
        exit_pending = False     # queued exit, fills at THIS bar's open

        for k in range(m):
            is_last = (k == m - 1)

            # STEP A -- execute fills queued from the PREVIOUS bar's close signal.
            if exit_pending:
                ex_px = so[k]
                pnl = (ex_px - entry_px) if pos > 0 else (entry_px - ex_px)
                pnl_list.append(pnl)
                if return_trades: trade_log.append((a + entry_k, a + k, pnl, pos, entry_px))
                pos = 0; exit_pending = False
            if entry_pending != 0 and pos == 0:
                pos = entry_pending; entry_px = so[k]; entry_k = k; entry_pending = 0

            # STEP B -- boundary-mode intrabar exit (checked while in a position).
            if pos != 0 and exit_mode == "boundary":
                if pos > 0:
                    band = UB[k]
                    if not np.isnan(band):
                        if so[k] < band:
                            pnl_list.append(so[k] - entry_px)
                            if return_trades: trade_log.append((a + entry_k, a + k, so[k] - entry_px, 1, entry_px))
                            pos = 0
                        elif sl[k] <= band:
                            pnl_list.append(band - entry_px)
                            if return_trades: trade_log.append((a + entry_k, a + k, band - entry_px, 1, entry_px))
                            pos = 0
                elif pos < 0:
                    band = LB[k]
                    if not np.isnan(band):
                        if so[k] > band:
                            pnl_list.append(entry_px - so[k])
                            if return_trades: trade_log.append((a + entry_k, a + k, entry_px - so[k], -1, entry_px))
                            pos = 0
                        elif sh[k] >= band:
                            pnl_list.append(entry_px - band)
                            if return_trades: trade_log.append((a + entry_k, a + k, entry_px - band, -1, entry_px))
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
                        pnl_list.append(pnl)
                        if return_trades: trade_log.append((a + entry_k, a + k, pnl, pos, entry_px))
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
                pnl_list.append(pnl)
                if return_trades: trade_log.append((a + entry_k, a + k, pnl, pos, entry_px))
                pos = 0

        prev_close = sc[-1]

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — runs the frozen defaults on the NQ 5m RTH master through the real
# engine (source PINNED to db_noadj_rth, matching tools/noise_research.py) and
# checks it against the checkpoint-gated reference numbers.
#   Run:  python augur_strategies/NOISE_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from augur_engine.engine import run_backtest as eng_bt

    DATE_TO = "2025-06-29"        # matches tools/noise_research.py's checkpoint window
    FEE, MULT = 0.533, 20.0       # NQ costs: 0.533 pts/RT, $20/pt

    frozen = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                  exit_mode="vwap", side="Both", window="all_day",
                  flat_eod=True, skip_holidays=False)

    r = eng_bt("NOISE_1_0.py", instrument="NQ", timeframe="5m", session="rth",
               source="db_noadj_rth", cost_pts=FEE, date_to=DATE_TO, params=frozen)

    if r is None:
        print("NO TRADES / no master found — check augur_uploads/ + optimizer_history.db")
        sys.exit(1)

    n   = r["num_trades"]
    net = r["total_pnl"] * MULT
    pf  = r["profit_factor"]
    dd  = r["max_drawdown"] * MULT

    print("NOISE 1.0 frozen defaults - NQ 5m RTH, source=db_noadj_rth (<= %s)" % DATE_TO)
    print("  params: %s" % frozen)
    print("  got:      n=%d net=$%s PF=%.4f DD=$%s" % (n, format(net, ",.2f"), pf, format(dd, ",.2f")))
    print("  expected: n=3147 net=$254,382.98 PF=1.311 DD=-$31,239.80")

    ok = (n == 3147 and abs(net - 254382.98) < 1 and abs(pf - 1.311) < 0.01 and abs(dd + 31239.80) < 1)
    print("  SMOKE TEST: %s" % ("PASS" if ok else "FAIL"))
