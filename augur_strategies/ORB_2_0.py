"""
OPENING RANGE BREAKOUT v2 — three alpha levers added over v1.

The core mechanics are identical (opening range, breakout entry, EOD flat,
one trade/session). What changes is HOW the position is managed and filtered:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. TRAILING STOP + PARTIAL EXIT                         (partial_exit_R, trail_bars)
   v1 rides to EOD, giving back 30-50% of trend-day moves before the close.
   v2 options:
     • partial_exit_R > 0  → exit HALF at that R-multiple of initial risk,
       then trail the remainder on an N-bar low/high until EOD or target_R.
     • trail_bars > 0 alone → trail the full position from entry on an N-bar
       low (long) / high (short) — stop moves only in the favorable direction.
     • Both together        → fixed stop until partial fires, then trail kicks
       in on the second half. Classic "scale out and trail the runners."

2. ATR-NORMALIZED STOP                                  (use_atr_stop, stop_atr_mult, atr_period)
   v1's stop = stop_frac × today's opening-range width. On a quiet day the
   range is 15pts; on a volatile day 80pts — you're risking 5× more dollars
   in volatile conditions. v2 can instead set stop = stop_atr_mult × rolling
   average daily range of the prior atr_period sessions (ATR proxy). Same
   dollar risk every day regardless of how compressed the opening range is.

3. VOLUME FILTER                                        (vol_filter)
   Most fake breakouts happen on thin volume — price pokes through the range
   edge but nobody follows. Require the breakout bar's volume >= vol_filter ×
   mean bar volume in the current session up to that bar. 0 = off.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Inherited from v1: OR length, direction bias, buffer, EOD flat, ATR-frac stop
fallback, 2022 anti-beta signature. PNL = SHARES*(EXIT-ENTRY), no fees.
"""
import numpy as np

STRATEGY_NAME = 'ORB 2.0 · trail + ATR stop + vol filter'
DESCRIPTION   = (
    "ORB v1 + three alpha levers: (1) partial exit at R + trailing stop on "
    "the remainder, (2) ATR-normalized stop for risk-consistency across vol "
    "regimes, (3) volume filter to skip fake breakouts on thin volume. "
    "Anti-beta: 2022 bear is best year on every config. NQ 5m default."
)

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    # ── Opening range ─────────────────────────────────────────────────────────
    "or_bars": {
        "default": 6, "min": 1, "max": 24, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": ("Length of the opening range in BARS. On 5-min data: "
                    "3=15min, 6=30min, 12=60min. Longer = fewer, higher-quality breaks."),
    },
    "trade_mode": {
        "default": "First-candle dir", "type": "str",
        "options": ["First-candle dir", "Both", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": ("First-candle dir = trade only the way the opening-range candle "
                    "closed (best NQ Sharpe in test). Both = either break (most two-sided). "
                    "Long/Short Only for research."),
    },
    "breakout_buf": {
        "default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range)",
        "tooltip": ("Require price to clear the range edge by this fraction of range width "
                    "before entering — filters marginal pokes. 0 = trade the touch."),
    },
    # ── Stop — range-frac (v1 default) ───────────────────────────────────────
    "stop_frac": {
        "default": 1.0, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": ("Stop distance from entry as a multiple of the opening-range width. "
                    "1.0 = the opposite extreme. Used when ATR stop is OFF. FLOOR 0.5: "
                    "below it the exact-stop-fill assumption inflates PF (artifact)."),
    },
    # ── Stop — ATR-normalized (new) ───────────────────────────────────────────
    "use_atr_stop": {
        "default": False, "type": "bool",
        "label": "ATR stop (replaces range-frac stop)",
        "tooltip": ("ON: stop = entry ± stop_atr_mult × avg daily range of the prior "
                    "atr_period sessions. Same dollar risk every day regardless of how wide "
                    "or narrow today's opening range is. OFF: use stop_frac × range (v1)."),
    },
    "stop_atr_mult": {
        "default": 1.5, "min": 0.25, "max": 5.0, "step": 0.25, "type": "float",
        "label": "ATR stop multiplier",
        "tooltip": ("Stop = entry ± stop_atr_mult × rolling ATR. 1.0–2.0 is the typical "
                    "range; larger = fewer stops but bigger losers when hit."),
        "depends_on": {"use_atr_stop": True},
    },
    "atr_period": {
        "default": 5, "min": 2, "max": 20, "step": 1, "type": "int",
        "label": "ATR lookback (sessions)",
        "tooltip": "Rolling average of the prior N session ranges (max-high – min-low).",
        "depends_on": {"use_atr_stop": True},
    },
    # ── Exits — target + partial + trail (new) ────────────────────────────────
    "target_R": {
        "default": 0.0, "min": 0.0, "max": 10.0, "step": 0.5, "type": "float",
        "label": "Full target (× risk, 0=EOD only)",
        "tooltip": ("Take-profit for the full position (or second half after a partial "
                    "exit). 0 = ride to the session close. Set partial_exit_R ≤ this for "
                    "a two-stage exit plan."),
    },
    "partial_exit_R": {
        "default": 0.0, "min": 0.0, "max": 8.0, "step": 0.5, "type": "float",
        "label": "Partial exit (× risk, 0=off)",
        "tooltip": ("Exit HALF the position at this R-multiple of initial risk. The "
                    "remaining half is then trailed (if trail_bars > 0) or held to EOD / "
                    "target_R. 0 = no partial exit — trade the full position all the way. "
                    "Set lower than target_R for a two-stage plan."),
    },
    "trail_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop (bars, 0=off)",
        "tooltip": ("Trail the stop to the rolling N-bar low (long) / high (short). "
                    "If partial_exit_R > 0, trailing activates on the second half after "
                    "the partial fires. If no partial, trails the full position from entry. "
                    "Stop can only move in the favorable direction. 0 = fixed stop."),
    },
    # ── Volume filter (new) ───────────────────────────────────────────────────
    "vol_filter": {
        "default": 0.0, "min": 0.0, "max": 5.0, "step": 0.25, "type": "float",
        "label": "Volume filter (× session avg, 0=off)",
        "tooltip": ("Require the breakout bar's volume ≥ this multiple of the mean bar "
                    "volume of the current session up to that bar. Filters fake pokes on "
                    "thin volume. 0 = off. Try 1.25–2.0 to start."),
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
}

PARAM_GRID_PRESETS = {
    # ~16 combos — quick directional + exit shape comparison
    "Short  (exit shapes)": {
        "or_bars":         [3, 6],
        "trade_mode":      ["First-candle dir", "Both"],
        "breakout_buf":    [0.0],
        "use_atr_stop":    [False],
        "stop_frac":       [1.0],
        "stop_atr_mult":   [1.5],
        "atr_period":      [5],
        "target_R":        [0.0],
        "partial_exit_R":  [0.0, 2.0],
        "trail_bars":      [0, 3],
        "vol_filter":      [0.0],
        "flat_eod":        [True],
    },
    # ~128 combos — sweep the three new levers independently
    "Medium (new levers)": {
        "or_bars":         [3, 6],
        "trade_mode":      ["First-candle dir", "Both"],
        "breakout_buf":    [0.0],
        "use_atr_stop":    [False, True],
        "stop_frac":       [0.75, 1.0],
        "stop_atr_mult":   [1.5],
        "atr_period":      [5],
        "target_R":        [0.0, 3.0],
        "partial_exit_R":  [0.0, 2.0],
        "trail_bars":      [0, 3],
        "vol_filter":      [0.0],
        "flat_eod":        [True],
    },
    # ~1500 combos — full v2 cross-product (good for XL/Auto)
    "Long   (full v2 sweep)": {
        "or_bars":         [3, 6, 12],
        "trade_mode":      ["First-candle dir", "Both"],
        "breakout_buf":    [0.0, 0.05],
        "use_atr_stop":    [False, True],
        "stop_frac":       [0.75, 1.0],
        "stop_atr_mult":   [1.0, 1.5, 2.0],
        "atr_period":      [5],
        "target_R":        [0.0, 3.0],
        "partial_exit_R":  [0.0, 2.0],
        "trail_bars":      [0, 3, 5],
        "vol_filter":      [0.0, 1.5],
        "flat_eod":        [True],
    },
}


# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 6,
    trade_mode: str = "First-candle dir",
    breakout_buf: float = 0.0,
    use_atr_stop: bool = False,
    stop_frac: float = 1.0,
    stop_atr_mult: float = 1.5,
    atr_period: int = 5,
    target_R: float = 0.0,
    partial_exit_R: float = 0.0,
    trail_bars: int = 0,
    vol_filter: float = 0.0,
    flat_eod: bool = True,
    day_id=None,
    return_trades: bool = False,
    _stop_event=None,
    _pause_event=None,
):
    o = np.asarray(opens,  dtype=float)
    h = np.asarray(highs,  dtype=float)
    l = np.asarray(lows,   dtype=float)
    c = np.asarray(closes, dtype=float)
    v = np.asarray(volumes, dtype=float) if volumes is not None else None
    n = len(c)
    if n < 10:
        return None

    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None                          # ORB needs session structure

    # ── Pre-compute session boundaries ───────────────────────────────────────
    sessions = []                            # list of (global_start, global_end)
    idx = 0
    while idx < n:
        jj = idx
        while jj < n and did[jj] == did[idx]:
            jj += 1
        sessions.append((idx, jj))
        idx = jj

    # ── Per-session range (for ATR) ───────────────────────────────────────────
    # Use max-high – min-low of the session as a simple daily-range proxy.
    sess_ranges = np.array([h[s:e].max() - l[s:e].min() for s, e in sessions],
                           dtype=float)

    allow_long  = trade_mode in ("First-candle dir", "Both", "Long Only")
    allow_short = trade_mode in ("First-candle dir", "Both", "Short Only")

    pnl_list   = []
    trade_log  = []

    for sess_idx, (si, ei) in enumerate(sessions):
        if _stop_event is not None and _stop_event.is_set():
            break

        m = ei - si
        if m <= or_bars + 1 or or_bars < 1:
            continue

        so = o[si:ei]; sh = h[si:ei]; sl = l[si:ei]; sc = c[si:ei]
        sv = v[si:ei] if v is not None else None

        or_hi = sh[:or_bars].max()
        or_lo = sl[:or_bars].min()
        rng   = or_hi - or_lo
        if rng <= 0:
            continue

        # ── ATR for this session (prior sessions only) ────────────────────────
        session_atr = None
        if use_atr_stop and sess_idx >= 1:
            atr_start   = max(0, sess_idx - atr_period)
            session_atr = float(sess_ranges[atr_start:sess_idx].mean())

        # ── Direction constraints ─────────────────────────────────────────────
        or_dir   = 1 if sc[or_bars - 1] >= so[0] else -1
        buf      = breakout_buf * rng
        up_lvl   = or_hi + buf
        dn_lvl   = or_lo - buf
        long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
        short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

        # ── Session loop ──────────────────────────────────────────────────────
        pos          = 0        # 0=flat, +1=long, -1=short
        entry        = 0.0
        stop_px      = 0.0
        tgt_px       = 0.0      # full exit target price (np.inf / -np.inf if off)
        partial_tgt  = 0.0      # partial exit price (np.inf / -np.inf if off)
        partial_done = False    # whether the half-exit has already fired
        partial_pnl  = 0.0      # points earned on the first half
        ek           = -1       # session-local index of entry bar

        for k in range(or_bars, m):

            # ── Entry ─────────────────────────────────────────────────────────
            if pos == 0:
                up = sh[k] >= up_lvl
                dn = sl[k] <= dn_lvl

                if long_ok and up:
                    side = 1
                    cand = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                elif short_ok and dn:
                    side = -1
                    cand = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                else:
                    continue

                # ── Volume filter ─────────────────────────────────────────────
                if vol_filter > 0 and sv is not None and k > 0:
                    mean_vol = sv[:k].mean()
                    if mean_vol > 0 and sv[k] < vol_filter * mean_vol:
                        continue           # thin-volume poke — skip

                # ── Accept trade, compute stops / targets ─────────────────────
                entry = cand
                if use_atr_stop and session_atr is not None and session_atr > 0:
                    raw_stop_dist = stop_atr_mult * session_atr
                else:
                    raw_stop_dist = stop_frac * rng
                raw_stop_dist = max(raw_stop_dist, 1e-6)   # safety floor

                if side > 0:
                    stop_px     = entry - raw_stop_dist
                    risk        = raw_stop_dist
                    tgt_px      = entry + target_R    * risk if target_R    > 0 else  np.inf
                    partial_tgt = entry + partial_exit_R * risk if partial_exit_R > 0 else  np.inf
                else:
                    stop_px     = entry + raw_stop_dist
                    risk        = raw_stop_dist
                    tgt_px      = entry - target_R    * risk if target_R    > 0 else -np.inf
                    partial_tgt = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf

                pos = side; ek = k; partial_done = False; partial_pnl = 0.0
                continue                # don't process exits on the entry bar

            # ── Manage open position ──────────────────────────────────────────
            # When to trail: always if trail_bars>0 AND (no partial planned
            # OR the partial has already fired).
            if trail_bars > 0 and (partial_exit_R == 0 or partial_done):
                trail_start = max(ek, k - trail_bars)
                if pos > 0:
                    trail_low = sl[trail_start:k].min() if k > trail_start else sl[ek]
                    stop_px   = max(stop_px, trail_low)   # only move up
                else:
                    trail_high = sh[trail_start:k].max() if k > trail_start else sh[ek]
                    stop_px    = min(stop_px, trail_high)  # only move down

            # ── Long position ─────────────────────────────────────────────────
            if pos > 0:
                # Stop (pessimistic — check before target)
                if sl[k] <= stop_px:
                    # Gap-through realism: bar opened below the stop → fill at the open.
                    exit_px = so[k] if so[k] < stop_px else stop_px
                    raw     = exit_px - entry
                    pnl     = (partial_pnl * 0.5 + raw * 0.5) if partial_done else raw
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((si + ek, si + k, pnl))
                    pos = 0; break

                # Partial exit
                if not partial_done and partial_exit_R > 0 and sh[k] >= partial_tgt:
                    partial_pnl  = partial_tgt - entry
                    partial_done = True
                    continue

                # Full / remainder target
                if target_R > 0 and sh[k] >= tgt_px:
                    raw = tgt_px - entry
                    pnl = (partial_pnl * 0.5 + raw * 0.5) if partial_done else raw
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((si + ek, si + k, pnl))
                    pos = 0; break

            # ── Short position ────────────────────────────────────────────────
            else:
                if sh[k] >= stop_px:
                    # Gap-through realism: bar opened above the stop → fill at the open.
                    exit_px = so[k] if so[k] > stop_px else stop_px
                    raw     = entry - exit_px
                    pnl     = (partial_pnl * 0.5 + raw * 0.5) if partial_done else raw
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((si + ek, si + k, pnl))
                    pos = 0; break

                if not partial_done and partial_exit_R > 0 and sl[k] <= partial_tgt:
                    partial_pnl  = entry - partial_tgt
                    partial_done = True
                    continue

                if target_R > 0 and sl[k] <= tgt_px:
                    raw = entry - tgt_px
                    pnl = (partial_pnl * 0.5 + raw * 0.5) if partial_done else raw
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((si + ek, si + k, pnl))
                    pos = 0; break

        # ── EOD flat ──────────────────────────────────────────────────────────
        if pos != 0:
            raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
            pnl = (partial_pnl * 0.5 + raw * 0.5) if partial_done else raw
            pnl_list.append(pnl)
            if return_trades:
                trade_log.append((si + ek, ei - 1, pnl))

    # ── Aggregate ─────────────────────────────────────────────────────────────
    if not pnl_list:
        return None
    pnls  = np.array(pnl_list, dtype=float)
    wins  = pnls[pnls > 0]
    losses= pnls[pnls < 0]
    gw    = float(wins.sum());  gl = float(-losses.sum())
    cum   = np.cumsum(pnls);    peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl":     float(pnls.sum()),
        "num_trades":    int(len(pnls)),
        "win_rate":      float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown":  float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl":       float(pnls.mean()),
        "wins":          int(len(wins)),
        "losses":        int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — reproduces v1 default (or_bars=6, first-candle dir, stop_frac=1.0,
# no new levers) on the NQ master.  Run:  python augur_strategies/ORB_2_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOADS = os.path.join(ROOT, "augur_uploads")
    MASTER  = os.path.join(UPLOADS, "master_00c66966.csv")   # NQ 5m RTH
    MULT    = 20

    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = dt.dt.hour * 60 + dt.dt.minute
    df   = df[(mins >= 570) & (mins < 960)].copy()
    dt   = dt[(mins >= 570) & (mins < 960)]
    df["date"]   = dt.dt.date
    df["day_id"] = pd.factorize(df["date"])[0]
    df = df.sort_values("time").reset_index(drop=True)

    print("NQ 5m RTH master: %d bars, %d sessions" %
          (len(df), df["day_id"].nunique()))

    configs = [
        # label,  or_bars, mode,              v2_kwargs
        ("v1-default  (or=6, first-dir, stop=1.0, no extras)",
            6, "First-candle dir", {}),
        ("trail only  (or=6, first-dir, trail=4)",
            6, "First-candle dir", {"trail_bars": 4}),
        ("partial+trail (or=6, first-dir, partial=2R, trail=4)",
            6, "First-candle dir", {"partial_exit_R": 2.0, "trail_bars": 4}),
        ("ATR stop    (or=6, first-dir, atr=1.5x5sess)",
            6, "First-candle dir", {"use_atr_stop": True, "stop_atr_mult": 1.5, "atr_period": 5}),
        ("vol filter  (or=6, first-dir, vol>=1.5x)",
            6, "First-candle dir", {"vol_filter": 1.5}),
        ("v1-best     (or=3, first-dir, stop=1.0)",
            3, "First-candle dir", {}),
    ]

    print()
    print("%-58s %7s %5s %5s %12s %9s" %
          ("config", "trades", "WR%", "PF", "net $", "avg $/T"))
    print("-" * 100)
    for label, orb, mode, kwargs in configs:
        r = run_backtest(
            df["open"].values, df["high"].values,
            df["low"].values,  df["close"].values,
            volumes=df["volume"].values if "volume" in df.columns else None,
            or_bars=orb, trade_mode=mode,
            day_id=df["day_id"].values,
            **kwargs,
        )
        if r is None:
            print("%-58s  NO TRADES" % label); continue
        usd = r["total_pnl"] * MULT
        avg = r["avg_pnl"]   * MULT
        print("%-58s %7d %4.0f%% %5.2f %12s %9.1f" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(usd), avg))

    print()
    print("Expected v1-default: ~3515 trades, ~40% WR, ~PF 1.19, ~+$303k")
    print("  (v1-best or=3:  ~3640 trades, ~40% WR, ~PF 1.21, ~+$352k)")
