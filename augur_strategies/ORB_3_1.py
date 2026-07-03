"""
OPENING RANGE BREAKOUT 3.1 — low-DOF base + a TWO-LOT scale-out.

This is ORB 3.0's clean, low-degrees-of-freedom base with EXACTLY TWO levers added
back from v2 — the only two needed to run a 2-contract "book one, ride one" plan:

    • partial_exit_R  → exit the FIRST lot (half) at this R-multiple of initial risk.
                        Books a win frequently → lifts realized win rate, smooths equity.
                        (the "take-profit early" contract — 119's DNA.)
    • trail_bars      → after the partial fires, TRAIL the runner (second lot) on the
                        rolling N-bar low (long) / high (short); stop only moves in the
                        favorable direction, ride to trail-out / target_R / EOD flat.
                        (the "trailing TP on the additional contract" — 121's DNA, but
                        de-artifacted: no sub-0.5 stop, no overnight gap risk.)

DELIBERATELY NOT re-added from v2: the ATR-normalized stop (use_atr_stop / stop_atr_mult
/ atr_period). Keeping only the range-frac stop holds this at 8 knobs — barely above 3.0
— so a walk-forward + lockbox can test the scale-out HYPOTHESIS in isolation instead of
wandering an over-parameterized surface. The whole point of forking 3.0 (not just
re-opening 2.0) is to sweep ONLY the two runner levers against a fixed, validated base.

Accounting mirrors v2 exactly: a scaled-out session books ONE trade whose PnL is the
average of the two half-legs (partial_pnl*0.5 + runner_pnl*0.5), so win_rate / num_trades
stay comparable to the single-lot 3.0 runs and the existing 2.0 history.

Knobs (7 active + optional target): or_bars · trade_mode · stop_frac · vol_filter ·
breakout_buf · partial_exit_R · trail_bars (+ optional target_R, atr_filter, flat_eod,
skip_holidays). PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.1 · low-DOF + scale-out (partial + trail)'
DESCRIPTION   = ("ORB 3.0's clean low-DOF base with the two runner levers added back: "
                 "book the first lot at partial_exit_R, trail the second lot on an N-bar "
                 "low/high. Built to walk-forward the scale-out in isolation against a "
                 "fixed base (no ATR stop, no sub-0.5 stop). NQ 5m default; transfers to ES.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Lineage: forked from the locked-down deployable 3.0, which itself forked v2. The
# validation roadmap inherits 3.0's ticked steps (flagged "inherited — re-confirm").
_AUGUR_PARENT = "ORB_3_0.py"

DEFAULT_PARAMS = {
    "or_bars": {
        "default": 1, "min": 1, "max": 12, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": "Opening-range length in BARS. On 5-min data: 1=5min, 3=15min, 6=30min, 12=60min.",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Both", "First-candle dir", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade either break (most two-sided). First-candle dir = only the "
                   "way the opening-range candle closed. Long/Short Only for research.",
    },
    "stop_frac": {
        "default": 0.75, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": "Stop distance from entry as a multiple of the opening-range width. "
                   "1.0 = the opposite extreme; 0.75 validated. FLOOR is 0.5 on purpose: "
                   "below that the backtest's exact-stop-fill assumption inflates PF "
                   "(stop 0.1 → fake PF 4.5) — tight stops get whipsawed/gapped in reality.",
    },
    "vol_filter": {
        "default": 1.25, "min": 0.0, "max": 3.0, "step": 0.25, "type": "float",
        "label": "Volume filter (× session avg, 0=off)",
        "tooltip": "Require the breakout bar's volume ≥ this multiple of the mean bar volume "
                   "of the session so far. Filters thin-volume fake breakouts. 1.25–1.5 validated.",
    },
    "breakout_buf": {
        "default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range)",
        "tooltip": "Require price to clear the range edge by this fraction of the range width "
                   "before entering. 0 = trade the touch.",
    },
    # ── The two re-added runner levers ────────────────────────────────────────
    "partial_exit_R": {
        "default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Partial exit / lot-1 TP (× risk, 0=off)",
        "tooltip": "Exit HALF the position (the first lot) at this R-multiple of initial risk "
                   "(entry-to-stop). The remaining half is trailed (if trail_bars > 0) or held "
                   "to EOD / target_R. 0 = no partial, single lot all the way (= 3.0 behaviour). "
                   "This is the 'take-profit early' contract. Try 1.5–2.5.",
    },
    "trail_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low (long) / high (short). If "
                   "partial_exit_R > 0, trailing activates on the SECOND lot after the partial "
                   "fires (scale-out-and-trail-the-runner). If no partial, trails the full "
                   "position from entry. Stop only moves favorably. 0 = fixed stop. Try 3–8.",
    },
    # ── Inherited 3.0 knobs ───────────────────────────────────────────────────
    "atr_filter": {
        "default": 0.0, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
        "label": "Vol-regime filter (× trailing median, 0=off)",
        "tooltip": "Skip a session when its recent 5-session avg range is BELOW this "
                   "multiple of the trailing 60-session median session range. Skips the "
                   "low-vol days the regime report card flagged as ORB's bleeding bucket. "
                   "0 = off (validated default). ~0.8-1.0 skips below-normal-vol days.",
    },
    "target_R": {
        "default": 0.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Runner target (× risk, 0=EOD/trail only)",
        "tooltip": "Optional hard take-profit for the runner (second lot, or the full "
                   "position if no partial) at this multiple of initial risk. 0 = let the "
                   "runner ride to the trail-out or the session close. Set ≥ partial_exit_R.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
    "skip_holidays": {
        "default": False, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close / half-day sessions (Thanksgiving, Christmas Eve, "
                   "Memorial Day, July-3, etc). Detected by session LENGTH (a half-day "
                   "has far fewer bars than a normal RTH day) — no calendar needed. These "
                   "sessions are thin/low-quality. OFF by default = no change.",
    },
}

PARAM_GRID_PRESETS = {
    # ── THE hypothesis test: fix a clean validated base (119-flavour, stop 0.75,
    #    vol 1.25, ride-to-close) and sweep ONLY the two runner levers. 6×4 = 24
    #    combos. This is the lockbox-friendly, minimal-DOF walk-forward. The
    #    partial=0 / trail=0 corner IS the single-lot 3.0 control to beat.
    "Short  (scale-out core — 2 knobs only)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75],
        "vol_filter": [1.25], "breakout_buf": [0.0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True],
        "partial_exit_R": [0.0, 1.0, 1.5, 2.0, 2.5, 3.0],
        "trail_bars":     [0, 3, 5, 8],
    },
    # ── Adds a little base breadth (OR length, stop, vol) around the scale-out
    #    sweep for an XL / auto search. 2×2×2 base × 4×4 exits = 128 combos.
    "Medium (base + scale-out)": {
        "or_bars": [1, 3], "trade_mode": ["Both"], "stop_frac": [0.5, 0.75],
        "vol_filter": [1.0, 1.25], "breakout_buf": [0.0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True],
        "partial_exit_R": [0.0, 1.5, 2.0, 3.0],
        "trail_bars":     [0, 3, 5, 8],
    },
    # ── Full sweep incl. a runner cap (target_R) and vol-regime filter. For XXL /
    #    auto only — this is broad enough to overfit, so trust it ONLY through a
    #    walk-forward + lockbox, never a single in-sample best.
    "Long   (full — cap + regime)": {
        "or_bars": [1, 3, 6], "trade_mode": ["Both", "First-candle dir"],
        "stop_frac": [0.5, 0.75, 1.0], "vol_filter": [1.0, 1.25, 1.5],
        "breakout_buf": [0.0], "atr_filter": [0.0, 0.8],
        "target_R": [0.0, 3.0, 4.5], "flat_eod": [True],
        "partial_exit_R": [0.0, 1.5, 2.0, 3.0],
        "trail_bars":     [0, 3, 5, 8],
    },
    # ── Holds the best-guess scale-out base fixed and sweeps ONLY partial_exit_R
    #    so you can read the lot-1 take-profit level in isolation (trail fixed at 5).
    "Partial (lot-1 TP scan)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75],
        "vol_filter": [1.25], "breakout_buf": [0.0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "trail_bars": [5],
        "partial_exit_R": [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 0.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0,
    partial_exit_R: float = 0.0, trail_bars: int = 0,
    atr_filter: float = 0.0, target_R: float = 0.0,
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
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= up_lvl
                        dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        # volume filter — skip thin-volume pokes
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                            risk  = stop_frac * rng
                            stop  = entry - risk
                            tgt   = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt  = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; continue
                    else:
                        # ── Trailing stop: active if trail_bars>0 AND (no partial
                        #    planned OR the partial has already fired). Uses PRIOR
                        #    bars' extremes (sl/sh[ts:k], excluding k) → no look-ahead.
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
                                # Gap-through realism: if the bar OPENED below the stop,
                                # a stop order fills at the open, not the stop price.
                                ex_px = so[k] if so[k] < stop else stop
                                raw   = ex_px - entry
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
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
# Smoke test — proves the two runner levers actually change results, using the
# clean NQ 5m RTH master.   Run:  python augur_strategies/ORB_3_1.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOADS = os.path.join(ROOT, "augur_uploads")
    MASTER  = os.path.join(UPLOADS, "NOADJ_NQ_5m_RTH.csv")   # already RTH-filtered
    MULT    = 20                                             # NQ $/point

    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)
    print("NQ 5m RTH master: %d bars, %d sessions" % (len(df), df["day_id"].nunique()))

    # Base = 119-flavour clean base (stop 0.75, vol 1.25, ride-to-close). We vary
    # ONLY partial_exit_R / trail_bars so the deltas are attributable to the scale-out.
    base = dict(or_bars=1, trade_mode="Both", stop_frac=0.75,
                vol_filter=1.25, breakout_buf=0.0, target_R=0.0, flat_eod=True)
    configs = [
        ("single-lot control (partial=0, trail=0)  [= 3.0]", {}),
        ("trail only            (trail=5)",                   {"trail_bars": 5}),
        ("book 1.5R + trail     (partial=1.5, trail=5)",      {"partial_exit_R": 1.5, "trail_bars": 5}),
        ("book 2.0R + trail     (partial=2.0, trail=5)",      {"partial_exit_R": 2.0, "trail_bars": 5}),
        ("book 2.0R + tight tr  (partial=2.0, trail=3)",      {"partial_exit_R": 2.0, "trail_bars": 3}),
        ("book 2.0R, hold EOD   (partial=2.0, trail=0)",      {"partial_exit_R": 2.0, "trail_bars": 0}),
    ]

    print()
    print("%-52s %7s %5s %5s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD $"))
    print("-" * 100)
    for label, kw in configs:
        r = run_backtest(
            df["open"].values, df["high"].values, df["low"].values, df["close"].values,
            volumes=df["volume"].values if "volume" in df.columns else None,
            day_id=df["day_id"].values, **{**base, **kw},
        )
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        print("%-52s %7d %4.0f%% %5.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(r["total_pnl"] * MULT),
            "${:,.0f}".format(r["max_drawdown"] * MULT)))
    print()
    print("Gross of fees (PNL=SHARES*(EXIT-ENTRY)); the app nets ~$5.66+0.25pt/trade.")
    print("Read: does 'book + trail' lift WR / cut DD vs the single-lot control,")
    print("      and at what cost to net $? Trust it only through WF + lockbox.")
