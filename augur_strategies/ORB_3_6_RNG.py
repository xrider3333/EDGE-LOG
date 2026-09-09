"""
ORB 3.6 RNG — round 11: how the OPENING RANGE ITSELF is measured (2026-09-09).

Every level ORB_3_6 trades off — the breakout buffer, the stop, the runner target and
the breakeven trigger — is a fixed multiple of ONE number: the high-minus-low of the
first `or_bars` 5-minute bars ("rng"). That single measurement includes both bars'
wicks, weights each bar equally, and says nothing about where price actually spent its
time. Nobody has tested a different yardstick for the same two bars. This fork keeps
the parent's trade LOGIC (close-confirmed breakout, pessimistic stop-first fills,
gap-through, EOD flat, breakeven armed on a finished close and acting next bar) and
only changes what "rng" (the WIDTH) and what the breakout LEVELS are built from.

Four new knobs, all default OFF = bit-identical to ORB_3_6 / the #314 crown:

  * rng_mode ("hl" default) — how the WIDTH that feeds buffer/stop/target/BE is built:
      "hl"   = high-low of the first or_bars bars (the crown, unchanged).
      "body" = max(open,close) - min(open,close) across those bars — wicks excluded.
      "mid"  = rng_blend * hl_width + (1-rng_blend) * body_width (a dial between them).
      "atr"  = rng_atr_mult * a trailing 5-session average FULL-SESSION range (the same
               trailing quantity the parent's atr_filter already computes internally,
               reused here as the width's yardstick instead of that day's own two bars).
               LIVE-LEGAL: uses only prior, already-closed sessions.
  * rng_blend (0.0..1.0, default 1.0 = pure hl, i.e. off) — the "mid" blend dial.
  * rng_atr_mult (0.0..2.0, default 0.0 = off) — the "atr" mode's multiplier.
  * rng_level_mode ("hl" default) — what the breakout TRIGGER (or_hi/or_lo) is measured
      from, independent of the width knob above:
      "hl"   = the true high/low of the first or_bars bars (the crown, unchanged).
      "body" = the body high/low (max/min of open & close) — a long wick no longer sets
               the trigger, only where the bar actually closed/opened.
  * rng_scope ("all" default) — research-only knob, not part of the main grid: "all"
    (default) lets the new width feed the buffer AND the stop/target/BE risk together
    (the crown's own coupling, unchanged when rng_mode="hl"); "stop_only" keeps the
    ORIGINAL high-low width feeding the breakout buffer and routes ONLY the new width
    into stop/target/BE risk, to separate which use of the number carries the money.

BE CAREFUL, AS INSTRUCTED: in the parent, one number (rng) sets the buffer AND the risk
that the target/breakeven are multiples of. Any width knob above (rng_mode != "hl", or
rng_scope="all") therefore moves the buffer, the stop, the target AND the breakeven
together — that coupling is intentional and is exactly what round 11 is testing, but it
means a change in trade count/PnL from these knobs conflates several effects at once.
The rng_scope="stop_only" variant exists specifically to isolate the stop/target/BE use
of the number from the buffer's use of it.

LIVE-LEGAL BY CONSTRUCTION: all four knobs are decided from the SAME or_bars bars (plus,
for "atr", trailing PRIOR sessions only) that the parent already reads before any entry
decision — no bar beyond what ORB_3_6 already consults is touched.

rng_mode="hl", rng_blend=1.0, rng_atr_mult=0.0, rng_level_mode="hl", rng_scope="all" (all
defaults) reproduces ORB_3_6 exactly (asserted in the __main__ smoke test).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.6 RNG · opening-range yardstick fork'
DESCRIPTION   = ("ORB_3_6 (legal base + breakeven) with the opening-range WIDTH and "
                 "breakout LEVELS made swappable: high-low (crown) vs body vs a "
                 "blend vs a trailing-ATR proxy for the width, and true-high-low vs "
                 "body for the trigger levels. All knobs default OFF = ORB_3_6 exactly.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars": {
        "default": 2, "min": 1, "max": 12, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": "Opening-range length in BARS. On 5-min data: 1=5min, 2=10min, 3=15min.",
    },
    "trade_mode": {
        "default": "First-candle dir", "type": "str",
        "options": ["Both", "First-candle dir", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade either break. First-candle dir = only the way the "
                   "opening-range candle closed.",
    },
    "stop_frac": {
        "default": 2.0, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": "Stop distance from entry as a multiple of the opening-range WIDTH "
                   "(see rng_mode). FLOOR is 0.5 on purpose.",
    },
    "vpace_filter": {
        "default": 0.7, "min": 0.0, "max": 1.4, "step": 0.1, "type": "float",
        "label": "Volume-pace gate (× trailing norm)",
        "tooltip": "Require the session's volume SO FAR to be at least this multiple of "
                   "the same-length prefix averaged over the prior 20 sessions. 0=off.",
    },
    "breakout_buf": {
        "default": 0.25, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range width)",
        "tooltip": "Require price to clear the range edge (see rng_level_mode) by this "
                   "fraction of the range WIDTH (see rng_mode / rng_scope) before entering.",
    },
    "close_confirm": {
        "default": True, "type": "bool",
        "label": "Close-confirmed entry (skip false wicks)",
        "tooltip": "ON (default) = only enter when a bar CLOSES beyond the edge, filling "
                   "at that close. OFF = touch entry.",
    },
    "partial_exit_R": {
        "default": 3.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Partial exit / lot-1 TP (× risk, 0=off)",
        "tooltip": "Exit HALF at this R-multiple of initial risk. 0 = single lot.",
    },
    "trail_bars": {
        "default": 3, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low/high (prior bars only). 0 = "
                   "fixed stop.",
    },
    "be_after_R": {
        "default": 0.0, "min": 0.0, "max": 4.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, "
                   "move the stop to ENTRY from the next bar on. 0 = off.",
    },
    "atr_filter": {
        "default": 0.7, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
        "label": "Vol-regime filter (× trailing median, 0=off)",
        "tooltip": "Skip a session when its recent 5-session avg range is BELOW this "
                   "multiple of the trailing 60-session median session range.",
    },
    "target_R": {
        "default": 5.5, "min": 0.0, "max": 8.0, "step": 0.5, "type": "float",
        "label": "Runner target (× risk, 0=EOD/trail only)",
        "tooltip": "Optional hard take-profit for the runner at this multiple of initial "
                   "risk. 0 = ride to trail-out / close.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
    "skip_holidays": {
        "default": True, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close sessions, detected by session LENGTH.",
    },
    # ── round 11 knobs: the SHAPE of the opening-range yardstick ──────────────
    "rng_mode": {
        "default": "hl", "type": "str",
        "options": ["hl", "body", "mid", "atr"],
        "label": "Range-width yardstick",
        "tooltip": "hl (default) = high-low of the first or_bars bars, the crown. body = "
                   "max/min of open & close only (wicks excluded). mid = rng_blend x hl + "
                   "(1-rng_blend) x body. atr = rng_atr_mult x a trailing 5-session avg "
                   "full-session range (legal, prior sessions only).",
    },
    "rng_blend": {
        "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.25, "type": "float",
        "label": "Width blend (hl vs body, mid mode only)",
        "tooltip": "Only used when rng_mode=mid. 1.0 = pure high-low (=off). 0.0 = pure body.",
    },
    "rng_atr_mult": {
        "default": 0.0, "min": 0.0, "max": 2.0, "step": 0.25, "type": "float",
        "label": "ATR-proxy multiplier (atr mode only)",
        "tooltip": "Only used when rng_mode=atr. Width = this x the trailing 5-session avg "
                   "full-session range. 0 = width collapses to 0 (no trades) — set >0 to use.",
    },
    "rng_level_mode": {
        "default": "hl", "type": "str",
        "options": ["hl", "body"],
        "label": "Breakout-trigger level",
        "tooltip": "hl (default) = trigger off the true high/low of the opening range. "
                   "body = trigger off the body high/low (max/min open & close) — a long "
                   "wick no longer sets the level. Independent of the width knob above.",
    },
    "rng_scope": {
        "default": "all", "type": "str",
        "options": ["all", "stop_only"],
        "label": "Width scope (research knob)",
        "tooltip": "all (default) = the rng_mode width feeds the buffer AND stop/target/BE "
                   "together (the crown's own coupling). stop_only = keep the ORIGINAL "
                   "high-low width feeding the buffer, route only the new width into "
                   "stop/target/BE risk — isolates which use of the number matters.",
    },
}

PARAM_GRID_PRESETS = {
    # OPEN ranges on the new knobs only, base pinned to the #314 crown — for auto-validate.
    "Short  (RNG yardstick scan on the #314 crown)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.5],
        "vpace_filter": [0.8], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [0.0], "trail_bars": [0], "target_R": [5.0],
        "atr_filter": [0.75], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.5],
        "rng_mode": ["hl", "body", "mid", "atr"],
        "rng_blend": [0.0, 0.25, 0.5, 0.75, 1.0],
        "rng_atr_mult": [0.5, 1.0, 1.5, 2.0],
        "rng_level_mode": ["hl", "body"],
        "rng_scope": ["all", "stop_only"],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 2, trade_mode: str = "First-candle dir",
    stop_frac: float = 2.0, vol_filter: float = 0.0, vpace_filter: float = 0.7,
    breakout_buf: float = 0.25, close_confirm: bool = True,
    partial_exit_R: float = 3.0, trail_bars: int = 3, be_after_R: float = 0.0,
    atr_filter: float = 0.7, target_R: float = 5.5,
    flat_eod: bool = True, skip_holidays: bool = True,
    rng_mode: str = "hl", rng_blend: float = 1.0, rng_atr_mult: float = 0.0,
    rng_level_mode: str = "hl", rng_scope: str = "all",
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

    allow_long  = trade_mode in ("Both", "First-candle dir", "Long Only")
    allow_short = trade_mode in ("Both", "First-candle dir", "Short Only")

    # ── Session boundaries ────────────────────────────────────────────────────
    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b

    # ── Half-day / holiday skip (skip_holidays) ───────────────────────────────
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)

    # ── Vol-regime filter (atr_filter > 0): trailing-only, no look-ahead ──────
    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
        _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue                          # warm-up → allow
            _recent = _srng[max(0, _si - 5):_si].mean()
            _ref    = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0 and _recent < atr_filter * _ref:
                _allow_start[a] = False

    # ── round-11 ATR PROXY (rng_mode="atr"): trailing 5-session avg of the FULL
    #    session range — the same trailing quantity atr_filter computes above,
    #    reused here as the width's yardstick. Legal: prior sessions only. ─────
    _atr_proxy = {}
    if rng_mode == "atr" and len(_sess_bounds) > 6:
        _srng2 = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            _atr_proxy[a] = float(_srng2[max(0, _si - 5):_si].mean()) if _si >= 6 else 0.0

    # ── V-PACE filter (legal): prior bars vs prior-20-session prefix norm ─────
    _pace_ord, _pace_ref = {}, None
    if vpace_filter > 0 and v is not None and len(_sess_bounds) > 21:
        _pace_ord = {a: si for si, (a, b) in enumerate(_sess_bounds)}
        _K = max(b - a for a, b in _sess_bounds)
        _pref = np.full((len(_sess_bounds), _K + 1), np.nan)
        for _si, (a, b) in enumerate(_sess_bounds):
            _cs = np.cumsum(np.asarray(v[a:b], dtype=float))
            _pref[_si, 1:(b - a) + 1] = _cs / np.arange(1, (b - a) + 1)
        _pace_ref = np.full_like(_pref, np.nan)
        for _si in range(20, len(_sess_bounds)):
            _pace_ref[_si, :] = np.nanmean(_pref[_si - 20:_si, :], axis=0)

    pnl_list, trade_log = [], []
    i = 0
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        m = j - i
        if i in _holiday_start:                  # half-day / holiday skip
            i = j; continue
        if _allow_start.get(i, True) is False:   # vol-regime filter skipped this session
            i = j; continue
        if m > or_bars + 1 and or_bars >= 1:
            so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
            sv = v[i:j] if v is not None else None
            or_hi = sh[:or_bars].max()
            or_lo = sl[:or_bars].min()
            hl_width = or_hi - or_lo

            # body extremes: max/min of OPEN & CLOSE across the range bars only.
            body_hi = max(so[:or_bars].max(), sc[:or_bars].max())
            body_lo = min(so[:or_bars].min(), sc[:or_bars].min())
            body_width = body_hi - body_lo

            # ── round-11: the WIDTH that feeds buffer/stop/target/BE ──────────
            if rng_mode == "body":
                width = body_width
            elif rng_mode == "mid":
                width = rng_blend * hl_width + (1.0 - rng_blend) * body_width
            elif rng_mode == "atr":
                width = rng_atr_mult * _atr_proxy.get(i, 0.0)
            else:  # "hl" — the crown, unchanged
                width = hl_width

            # ── round-11: the LEVELS the breakout triggers off ────────────────
            if rng_level_mode == "body":
                lvl_hi, lvl_lo = body_hi, body_lo
            else:  # "hl" — the crown, unchanged
                lvl_hi, lvl_lo = or_hi, or_lo

            # ── round-11: which width feeds the BUFFER (rng_scope) ────────────
            if rng_scope == "stop_only" and rng_mode != "hl":
                buf_width = hl_width          # buffer keeps the ORIGINAL yardstick
            else:
                buf_width = width             # crown behaviour: same number everywhere

            rng = width                       # this feeds stop_frac / target_R / be_after_R
            if rng > 0:
                or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
                buf    = breakout_buf * buf_width
                up_lvl = lvl_hi + buf
                dn_lvl = lvl_lo - buf
                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                be_armed = False; be_lvl = np.nan
                for k in range(or_bars, m):
                    if pos == 0:
                        if close_confirm:
                            up = sc[k] >= up_lvl
                            dn = sc[k] <= dn_lvl
                        else:
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        # LEGAL v-pace gate — inputs closed BEFORE this bar.
                        if vpace_filter > 0 and _pace_ref is not None and sv is not None and k > 0:
                            _si2 = _pace_ord.get(i)
                            if _si2 is not None and k < _pace_ref.shape[1]:
                                _rf = _pace_ref[_si2, k]
                                if _rf == _rf and _rf > 0 and sv[:k].mean() < vpace_filter * _rf:
                                    continue
                        # legacy look-ahead filter — OFF, kept only for 3.1 parity by hand.
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = sc[k] if close_confirm else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                            risk  = stop_frac * rng
                            stop  = entry - risk
                            tgt   = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt  = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            be_lvl = entry + be_after_R * risk if be_after_R > 0 else np.nan
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; continue
                        elif short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; continue
                    else:
                        # ── BREAKEVEN: armed on a PRIOR bar's close, applied here.
                        if be_armed:
                            stop = max(stop, entry) if pos > 0 else min(stop, entry)
                        # ── Trailing stop: prior bars' extremes only (excludes k).
                        if trail_bars > 0 and (partial_exit_R == 0 or p_done):
                            ts = max(ek, k - trail_bars)
                            if pos > 0:
                                trail_low = sl[ts:k].min() if k > ts else sl[ek]
                                stop = max(stop, trail_low)   # only move up
                            else:
                                trail_high = sh[ts:k].max() if k > ts else sh[ek]
                                stop = min(stop, trail_high)  # only move down

                        if pos > 0:
                            if sl[k] <= stop:                       # stop first (pessimistic)
                                ex_px = so[k] if so[k] < stop else stop   # gap-through
                                raw   = ex_px - entry
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                            if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                p_pnl = ptgt - entry; p_done = True; continue
                            if target_R > 0 and sh[k] >= tgt:
                                raw = tgt - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                raw   = entry - ex_px
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0; break
                            if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                p_pnl = entry - ptgt; p_done = True; continue
                            if target_R > 0 and sl[k] <= tgt:
                                raw = entry - tgt
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0; break
                if pos != 0:                                        # EOD flat
                    raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
        i = j

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
# Smoke test: ALL round-11 knobs at default must be BIT-IDENTICAL to ORB_3_6.py
# on the #314 crown params; a non-default knob must actually change results.
# Run:  python augur_strategies/ORB_3_6_RNG.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import importlib.util as ilu
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER  = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(MASTER):
        MASTER = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads",
                               "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)

    spec = ilu.spec_from_file_location("_orb36", os.path.join(ROOT, "augur_strategies", "ORB_3_6.py"))
    base = ilu.module_from_spec(spec); spec.loader.exec_module(base)

    CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
                 partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
                 breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
                 atr_filter=0.75, vpace_filter=0.8)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r0 = base.run_backtest(*args, **kw, **CROWN)
    r1 = run_backtest(*args, **kw, **CROWN)   # all round-11 knobs at default
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("defaults parity vs ORB_3_6 (#314 crown): %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    r2 = run_backtest(*args, **kw, **CROWN, rng_mode="body")
    print("rng_mode=body changes results: %s  (pnl %.1f -> %.1f)" % (
        "PASS" if abs(r2["total_pnl"] - r1["total_pnl"]) > 1e-9 else "FAIL",
        r1["total_pnl"], r2["total_pnl"]))

    r3 = run_backtest(*args, **kw, **CROWN, rng_level_mode="body")
    print("rng_level_mode=body changes results: %s  (pnl %.1f -> %.1f, n %d -> %d)" % (
        "PASS" if (abs(r3["total_pnl"] - r1["total_pnl"]) > 1e-9
                    or r3["num_trades"] != r1["num_trades"]) else "FAIL",
        r1["total_pnl"], r3["total_pnl"], r1["num_trades"], r3["num_trades"]))

    r4 = run_backtest(*args, **kw, **CROWN, rng_mode="atr", rng_atr_mult=1.0)
    print("rng_mode=atr,mult=1.0 changes results: %s  (pnl %.1f -> %.1f, n %d -> %d)" % (
        "PASS" if (abs(r4["total_pnl"] - r1["total_pnl"]) > 1e-9
                    or r4["num_trades"] != r1["num_trades"]) else "FAIL",
        r1["total_pnl"], r4["total_pnl"], r1["num_trades"], r4["num_trades"]))

    sys.exit(0 if same else 1)
