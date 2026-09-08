"""
OPENING RANGE BREAKOUT 3.6 RE — the #314 legal crown + SAME-DIRECTION RE-ENTRY.

WHY THIS FILE EXISTS (round 10, 2026-09-08): the base (3.6, inherited from 3.4)
`break`s out of the session's k-loop after ONE exit — win, loss, or EOD flat —
so a day that stops out at 9:45am just sits flat the rest of the session even
though the same first-candle-direction signal could re-trigger. This fork asks
whether a SAME-DIRECTION re-entry after that first exit adds edge or just adds
cost (COST per contract per RT, again, per re-entry).

    reentry_max   → how many ADDITIONAL entries are allowed after an exit, same
                    session (0 = OFF = identical to ORB_3_6).
    reentry_after → "stop" (default): re-enter only after a STOP exit (this
                    includes a breakeven-stop — same `sl[k]<=stop`/`sh[k]>=stop`
                    code path, stop value just happens to equal entry once BE
                    is armed). "any": re-enter after ANY exit, including a
                    target hit.
    reentry_mode  → "rebreak" (default): after the exit, price must first
                    CLOSE back INSIDE the original range (sc < up_lvl for a
                    long, sc > dn_lvl for a short) before a fresh close beyond
                    up_lvl/dn_lvl is honored — a genuine re-break, not the same
                    bar re-triggering. "retest": no inside-range requirement;
                    the very next close beyond the level re-triggers.

Re-entries are FORCED to the same direction as the session's first trade
(tracked via `re_dir`, locked the moment the first entry fires) and reuse the
ORIGINAL or_hi/or_lo/up_lvl/dn_lvl/rng — only the entry price (and therefore
stop/target/BE, computed the same way the base always computes them) is new.
The v-pace / ATR-regime gates already passed once at session start and are
left to run exactly as the base runs them (they read only bars < k, so
re-checking them on a re-entry costs nothing and changes nothing structurally
— we do not special-case them).

LIVE-LEGAL BY CONSTRUCTION: every decision here reads only a FINISHED bar's
close (or high/low for touch mode, same as the base); `awaiting_inside` is
updated using bar k's own close on bar k, same timing the base already uses
for its up/dn breakout test. Nothing on any fill bar is read before it exists.

reentry_max = 0 → OFF → byte-identical behaviour to ORB_3_6.py (asserted in
the __main__ smoke test on the #314 crown params).

Knobs = 3.6's inherited set + reentry_max, reentry_after, reentry_mode.
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.6 RE'
DESCRIPTION   = ("The #314 legal crown (close-confirm capable, v-pace/ATR-regime gates, "
                 "breakeven-after-R) plus SAME-DIRECTION re-entry after the first exit: "
                 "reentry_max additional entries, gated by reentry_after (stop-only or "
                 "any exit) and reentry_mode (rebreak = must close back inside the range "
                 "first, retest = no inside requirement). reentry_max=0 reproduces "
                 "ORB_3_6 exactly.")

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
        "default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Partial exit / lot-1 TP (× risk, 0=off)",
        "tooltip": "Exit HALF at this R-multiple of initial risk. Remaining half trails / "
                   "rides. 0 = single lot.",
    },
    "trail_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low/high (prior bars only). If a "
                   "partial is set, activates after it fires. 0 = fixed stop.",
    },
    "be_after_R": {
        "default": 0.5, "min": 0.0, "max": 4.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, "
                   "move the stop to ENTRY from the next bar on. 0 = off.",
    },
    # ── THE new levers ────────────────────────────────────────────────────────
    "reentry_max": {
        "default": 0, "min": 0, "max": 4, "step": 1, "type": "int",
        "label": "Re-entries allowed (same session, same direction)",
        "tooltip": "How many ADDITIONAL same-direction entries are allowed after the "
                   "first exit, same session. 0 = off (= ORB_3_6 exactly).",
    },
    "reentry_after": {
        "default": "stop", "type": "str",
        "options": ["stop", "any"],
        "label": "Re-enter after",
        "tooltip": "'stop' = only re-enter after a STOP exit (incl. breakeven-stop). "
                   "'any' = re-enter after any exit, including a target hit.",
    },
    "reentry_mode": {
        "default": "rebreak", "type": "str",
        "options": ["rebreak", "retest"],
        "label": "Re-entry trigger",
        "tooltip": "'rebreak' = price must first close back INSIDE the original range "
                   "before a fresh close beyond the level re-triggers (a genuine "
                   "re-break). 'retest' = no inside-range requirement; the very next "
                   "close beyond the level re-triggers.",
    },
    # ── Inherited 3.0/3.4/3.6 knobs ───────────────────────────────────────────
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
}

PARAM_GRID_PRESETS = {
    # THE hypothesis test: hold run #314's champion FIXED, sweep ONLY the new levers.
    "Short  (re-entry scan on the #314 champion)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.5],
        "vpace_filter": [0.8], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [0.0], "trail_bars": [0], "target_R": [5.0],
        "atr_filter": [0.75], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.5],
        "reentry_max": [0, 1, 2], "reentry_after": ["stop", "any"],
        "reentry_mode": ["rebreak", "retest"],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 2, trade_mode: str = "First-candle dir",
    stop_frac: float = 2.0, vol_filter: float = 0.0, vpace_filter: float = 0.7,
    breakout_buf: float = 0.25, close_confirm: bool = True,
    partial_exit_R: float = 0.0, trail_bars: int = 0, be_after_R: float = 0.0,
    atr_filter: float = 0.7, target_R: float = 5.5,
    flat_eod: bool = True, skip_holidays: bool = True,
    reentry_max: int = 0, reentry_after: str = "stop", reentry_mode: str = "rebreak",
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
                # ── RE-ENTRY state (round 10) ─────────────────────────────────
                reentry_count = 0          # additional entries used so far
                re_dir = 0                 # locked to +1/-1 once the first trade fires
                awaiting_inside = False    # "rebreak" mode: must see an inside close first
                for k in range(or_bars, m):
                    if pos == 0:
                        # ── re-entry direction lock + rebreak "inside" gate ────
                        if re_dir != 0:
                            cur_long_ok, cur_short_ok = (re_dir == 1), (re_dir == -1)
                        else:
                            cur_long_ok, cur_short_ok = long_ok, short_ok
                        if awaiting_inside:
                            if re_dir == 1 and sc[k] < up_lvl:
                                awaiting_inside = False
                            elif re_dir == -1 and sc[k] > dn_lvl:
                                awaiting_inside = False
                        if close_confirm:
                            up = sc[k] >= up_lvl
                            dn = sc[k] <= dn_lvl
                        else:
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        if awaiting_inside:
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
                        if cur_long_ok and up:
                            entry = sc[k] if close_confirm else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                            risk  = stop_frac * rng
                            stop  = entry - risk
                            tgt   = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt  = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            be_lvl = entry + be_after_R * risk if be_after_R > 0 else np.nan
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False
                            re_dir = 1; continue
                        elif cur_short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False
                            re_dir = -1; continue
                    else:
                        # ── BREAKEVEN (armed on a PRIOR bar's close, applied here).
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
                                pos = 0
                                if reentry_max > 0 and reentry_count < reentry_max:
                                    reentry_count += 1
                                    if reentry_mode == "rebreak":
                                        awaiting_inside = True
                                    continue
                                break
                            if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                p_pnl = ptgt - entry; p_done = True; continue
                            if target_R > 0 and sh[k] >= tgt:
                                raw = tgt - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0
                                if reentry_max > 0 and reentry_count < reentry_max and reentry_after == "any":
                                    reentry_count += 1
                                    if reentry_mode == "rebreak":
                                        awaiting_inside = True
                                    continue
                                break
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                raw   = entry - ex_px
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0
                                if reentry_max > 0 and reentry_count < reentry_max:
                                    reentry_count += 1
                                    if reentry_mode == "rebreak":
                                        awaiting_inside = True
                                    continue
                                break
                            if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                p_pnl = entry - ptgt; p_done = True; continue
                            if target_R > 0 and sl[k] <= tgt:
                                raw = entry - tgt
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                pos = 0
                                if reentry_max > 0 and reentry_count < reentry_max and reentry_after == "any":
                                    reentry_count += 1
                                    if reentry_mode == "rebreak":
                                        awaiting_inside = True
                                    continue
                                break
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
# Smoke test: (1) reentry_max=0 must be BIT-IDENTICAL to ORB_3_6.py on the #314
# crown params; (2) reentry_max>0 must actually change results.
# Run:  python augur_strategies/ORB_3_6_RE.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import importlib.util as ilu
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER  = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)

    spec = ilu.spec_from_file_location("_orb36", os.path.join(ROOT, "augur_strategies", "ORB_3_6.py"))
    base = ilu.module_from_spec(spec); spec.loader.exec_module(base)

    CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
                 partial_exit_R=0, trail_bars=0, flat_eod=True, skip_holidays=True,
                 breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
                 atr_filter=0.75, vpace_filter=0.8)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r0 = base.run_backtest(*args, **kw, **CROWN)
    r1 = run_backtest(*args, **kw, **CROWN, reentry_max=0)
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("reentry_max=0 parity vs ORB_3_6: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    r2 = run_backtest(*args, **kw, **CROWN, reentry_max=1, reentry_after="stop", reentry_mode="rebreak")
    print("reentry_max=1 changes results: %s  (n %d -> %d, pnl %.1f -> %.1f)" % (
        "PASS" if abs(r2["total_pnl"] - r1["total_pnl"]) > 1e-9 or r2["num_trades"] != r1["num_trades"] else "FAIL",
        r1["num_trades"], r2["num_trades"], r1["total_pnl"], r2["total_pnl"]))
    sys.exit(0 if same else 1)
