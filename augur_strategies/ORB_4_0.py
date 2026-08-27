"""
ORB 4.0 — THE ENTRY WINDOW, on the run #234 crown (2026-08-26 hunt, round 5).

One new question the legal base has never been asked: does it matter WHEN in the
session the breakout happens? The crown scans every bar from the end of the opening
range to the close, so a 15:30 break is taken on the same terms as a 10:05 one.

  * entry_from_bar — ignore breakouts before this bar index (0 = off, the crown).
  * entry_to_bar   — take no NEW entry at or after this bar index (0 = off). A position
                     already open is managed to its normal exit; only the SCAN stops.

Both default OFF, and with both off this file is asserted bit-identical to ORB_3_6 —
same assertion ORB_3_9 carries, run by the smoke test at the bottom.

LIVE-LEGAL: a bar index inside the session is knowable in advance (it is the clock), so
nothing here reads the future. This is a schedule, not a signal.
"""
import numpy as np

STRATEGY_NAME = 'ORB 4.0 · legal base + breakeven'
DESCRIPTION   = ("The legal ORB base (close-confirm capable, v-pace/ATR-regime gates, "
                 "partial+trail scale-out) plus ONE new lever: move the stop to entry "
                 "once a bar CLOSES beyond be_after_R x risk. Armed on a finished bar, "
                 "acts from the next bar - live-legal. be_after_R=0 reproduces ORB_3_4 "
                 "exactly. Built to offer run #230's champion the -33%-DD lever the "
                 "old (voided) touch-entry family proved out.")

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
                   "opening-range candle closed (the grail hunt's sole aggregate survivor).",
    },
    "stop_frac": {
        "default": 2.0, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": "Stop distance from entry as a multiple of the opening-range width. "
                   "FLOOR is 0.5 on purpose: below that the exact-stop-fill assumption "
                   "inflates PF.",
    },
    "vpace_filter": {
        "default": 0.7, "min": 0.0, "max": 1.4, "step": 0.1, "type": "float",
        "label": "Volume-pace gate (× trailing norm)",
        "tooltip": "Require the session's volume SO FAR (bars before this one) to be at "
                   "least this multiple of the same-length prefix averaged over the prior "
                   "20 sessions. LIVE-LEGAL: the fill bar's own volume is never read. 0=off.",
    },
    "breakout_buf": {
        "default": 0.25, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range)",
        "tooltip": "Require price to clear the range edge by this fraction of the range "
                   "width before entering. 0 = trade the touch.",
    },
    "close_confirm": {
        "default": True, "type": "bool",
        "label": "Close-confirmed entry (skip false wicks)",
        "tooltip": "ON (default) = only enter when a bar CLOSES beyond the edge, filling at "
                   "that close - the live-legal entry the grail hunt certified. OFF = touch "
                   "entry (models a resting stop; legal fill, but pairs with intrabar "
                   "quantities in ways the audit flagged - keep ON unless researching).",
    },
    "partial_exit_R": {
        "default": 3.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Partial exit / lot-1 TP (× risk, 0=off)",
        "tooltip": "Exit HALF at this R-multiple of initial risk. Remaining half trails / "
                   "rides. 0 = single lot.",
    },
    "trail_bars": {
        "default": 3, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low/high (prior bars only). If a "
                   "partial is set, activates after it fires. 0 = fixed stop.",
    },
    # ── THE new lever ─────────────────────────────────────────────────────────
    "be_after_R": {
        "default": 0.0, "min": 0.0, "max": 4.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, "
                   "move the stop to ENTRY from the next bar on. The voided touch-entry "
                   "study found a robust 0.9-1.3R plateau (DD −33%); this re-asks that "
                   "question on the legal base. 0 = off (= ORB_3_4 exactly).",
    },
    # ── Inherited 3.0/3.4 knobs ───────────────────────────────────────────────
    "atr_filter": {
        "default": 0.7, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
        "label": "Vol-regime filter (× trailing median, 0=off)",
        "tooltip": "Skip a session when its recent 5-session avg range is BELOW this "
                   "multiple of the trailing 60-session median session range. Trailing-only.",
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
        "tooltip": "Skip early-close sessions, detected by session LENGTH. Calendar-known.",
    },
    "entry_from_bar": {
        "default": 0, "min": 0, "max": 60, "step": 1, "type": "int",
        "label": "No entries before bar",
        "tooltip": "Ignore breakouts before this bar index inside the session (0 = off). "
                   "Bar 6 on 5-minute data is 10:00 ET.",
    },
    "entry_to_bar": {
        "default": 0, "min": 0, "max": 90, "step": 1, "type": "int",
        "label": "No new entries from bar",
        "tooltip": "Stop scanning for NEW breakouts at this bar index (0 = off). A trade "
                   "already open is still managed to its normal exit. Bar 54 on 5-minute "
                   "data is 14:00 ET.",
    },
}

PARAM_GRID_PRESETS = {
    # THE hypothesis test: hold run #230's champion FIXED, sweep ONLY the new lever.
    # 9 combos incl. the be=0 control (= the champion itself, bit-identical).
    "Short  (BE scan on the #230 champion)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.0],
        "vpace_filter": [0.7], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [3.0], "trail_bars": [3], "target_R": [5.5],
        "atr_filter": [0.7], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0],
    },
    # Adds modest base breadth around the BE scan for an auto search.
    "Medium (BE + nearby base)": {
        "or_bars": [2, 3], "trade_mode": ["First-candle dir"], "stop_frac": [1.5, 2.0],
        "vpace_filter": [0.7], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [2.5, 3.0], "trail_bars": [3, 5], "target_R": [5.5],
        "atr_filter": [0.7], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.0, 0.8, 1.0, 1.2, 1.5],
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
    entry_from_bar: int = 0, entry_to_bar: int = 0,
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
            rng   = or_hi - or_lo
            if rng > 0:
                or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
                buf    = breakout_buf * rng
                up_lvl = or_hi + buf
                dn_lvl = or_lo - buf
                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                be_armed = False; be_lvl = np.nan
                for k in range(or_bars, m):
                    if pos == 0:
                        # ── ENTRY WINDOW (the 4.0 lever) ───────────────────────────
                        #    A schedule, not a signal: the bar index inside a session is
                        #    the clock, knowable before the bar exists. Once the scan is
                        #    past entry_to_bar and we are flat, no entry can happen for
                        #    the rest of this session, so stop walking it.
                        if entry_from_bar > 0 and k < entry_from_bar:
                            continue
                        if entry_to_bar > 0 and k >= entry_to_bar:
                            break
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
                        # ── BREAKEVEN (the 3.6 lever): armed on a PRIOR bar's close,
                        #    applied here — i.e. from the bar AFTER the arming close.
                        #    Legal: only finished bars are read.
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
                            # arm BE off this bar's CLOSE — takes effect next bar.
                            # (checked before the partial's `continue` so a partial-fire
                            #  bar can still arm; ordering is state-neutral this bar.)
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
# Smoke test: with both new knobs OFF this file must be BIT-IDENTICAL to ORB_3_6 on
# the run #234 crown params, and switching a knob ON must actually change the result.
# Run:  python augur_strategies/ORB_4_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    import sys
    import importlib.util

    import pandas as pd

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # masters live in the primary checkout; a worktree has none of its own.
    CSV = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(CSV):
        CSV = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG",
                           "augur_uploads", "NOADJ_NQ_5m_RTH.csv")

    def _load(path):
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    base = _load(os.path.join(ROOT, "augur_strategies", "ORB_3_6.py"))
    df = pd.read_csv(CSV)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    day_id = pd.factorize(df["_dt"].dt.date)[0]
    args = dict(volumes=df["volume"].values.astype(float), day_id=day_id, return_trades=True)
    P = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, breakout_buf=0.25,
             close_confirm=True, partial_exit_R=0.0, trail_bars=0, target_R=5.5,
             atr_filter=0.7, vpace_filter=0.7, flat_eod=True, skip_holidays=True,
             be_after_R=1.0)
    O, H, L, C = (df[c].values.astype(float) for c in ("open", "high", "low", "close"))

    a = base.run_backtest(O, H, L, C, **args, **P)
    b = run_backtest(O, H, L, C, **args, **P)
    same = (len(a["trades"]) == len(b["trades"])
            and all(x == y for x, y in zip(a["trades"], b["trades"])))
    print("knobs OFF vs ORB_3_6: %d/%d trades identical -> %s"
          % (len(b["trades"]), len(a["trades"]), "PASS" if same else "FAIL"))
    assert same, "ORB_4_0 with both knobs off must reproduce ORB_3_6 exactly"

    c = run_backtest(O, H, L, C, **args, **dict(P, entry_to_bar=54))
    print("entry_to_bar=54: %d trades, $%.0f (base %d trades, $%.0f)"
          % (c["num_trades"], c["total_pnl"] * 20, a["num_trades"], a["total_pnl"] * 20))
    assert c["num_trades"] != a["num_trades"], "the entry window must change something"
    print("ORB_4_0 smoke: PASS")
