"""
TTMSQZ 1.0 — John Carter's TTM Squeeze (Simpler Trading / "Mastering the Trade").

Published mechanics (Carter, Mastering the Trade ch. 8; the Pine/TOS "TTM_Squeeze"):
  Bollinger Bands  = SMA(close, 20) +/- 2.0 x stdev(close, 20)
  Keltner Channels = SMA(close, 20) +/- 1.5 x ATR(20)      (ATR = SMA of true range)
  SQUEEZE ON  (red dots)   : BOTH Bollinger bands sit INSIDE the Keltner channel
                             (lower_bb > lower_kc AND upper_bb < upper_kc) -- volatility
                             has compressed, energy is building.
  SQUEEZE FIRES (green dot): the first bar the bands move back OUTSIDE the channel.
  MOMENTUM histogram       : linreg( close - avg( avg(highest(high,20), lowest(low,20)),
                                                 sma(close,20) ), 20 )  -- Carter's
                             momentum oscillator; its SIGN is the trade direction, its
                             bar-to-bar change is the "colour" (brightening / fading).
  TRADE  : when the squeeze FIRES, go with the momentum sign. Carter's exit is
           discretionary -- "when the histogram loses steam" (first bar it fades) --
           with the common mechanical reads being (a) exit on the first fading bar,
           (b) exit when momentum crosses zero, (c) time/ATR stop. All three are knobs.

Port semantics (house-honest, legal):
  - Everything is decided on bar t's CLOSE from bar-t indicator values; fills happen on
    bar t+1 (entries and momentum exits at the NEXT bar's OPEN). No fill ever uses
    information from its own bar's close.
  - Protective stop = stop_atr x ATR(20) from entry, checked INTRABAR on every bar after
    the fill bar; a gap through the stop pays the OPEN (never the stop price).
  - INTRADAY ONLY: the position is flattened at the session's last bar close
    (flat_eod) and no entry is taken inside the final `eod_cutoff` bars. The
    indicators themselves roll across sessions, exactly as they do on a TradingView /
    ThinkOrSwim RTH chart. Holding overnight on a no-adjust continuous master would
    cross quarterly roll seams, so it is deliberately not offered in 1.0.
  - min_sq_bars: the squeeze must have been ON for at least this many bars before the
    fire counts (Carter: "the longer the squeeze, the bigger the move").
  - direction: both / long / short.
  - PNL = points only; costs applied downstream by the engine (0.533 pts/RT NQ,
    0.363 ES), same as every library strategy.

Needs day_id (session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'TTMSQZ 1.0 · John Carter TTM Squeeze (BB-inside-Keltner fire + momentum)'
DESCRIPTION = ("Carter's TTM Squeeze: Bollinger(20,2) compressed inside Keltner(20,1.5xATR) = "
               "squeeze ON; enter at the next open when the squeeze FIRES, in the direction of "
               "the linear-regression momentum histogram. Exit on momentum fade / zero-cross, "
               "ATR stop, flat at session end. Timeframe-neutral; run it on 1m-15m masters.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# New challenger family TTM (2026-08-22 owner ask: assess Carter's squeeze across timeframes).

DEFAULT_PARAMS = {
    "length": {
        "default": 20, "min": 10, "max": 40, "step": 2, "type": "int",
        "label": "Squeeze length (BB / Keltner / momentum)",
        "tooltip": "Carter default 20, shared by the bands, channel, ATR and momentum regression.",
    },
    "bb_mult": {
        "default": 2.0, "min": 1.0, "max": 3.0, "step": 0.25, "type": "float",
        "label": "Bollinger stdev multiplier",
        "tooltip": "Carter default 2.0.",
    },
    "kc_mult": {
        "default": 1.5, "min": 1.0, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Keltner ATR multiplier",
        "tooltip": "Carter default 1.5. Larger = tighter squeeze definition (fewer, longer squeezes).",
    },
    "min_sq_bars": {
        "default": 1, "min": 1, "max": 12, "step": 1, "type": "int",
        "label": "Minimum bars in squeeze before a fire counts",
        "tooltip": "1 = every fire trades (published). Higher = only fires after a long compression.",
    },
    "exit_mode": {
        "default": "fade", "type": "str",
        "options": ["fade", "zero", "flip"],
        "label": "Momentum exit rule",
        "tooltip": "fade = exit when the histogram loses steam for fade_bars bars (Carter's read). "
                   "zero = exit when momentum crosses zero. flip = exit only on an opposite-side fire "
                   "or stop/EOD.",
    },
    "fade_bars": {
        "default": 1, "min": 1, "max": 4, "step": 1, "type": "int",
        "label": "Consecutive fading histogram bars to exit (fade mode)",
        "tooltip": "1 = first lighter bar exits (strict Carter). 2-3 tolerate a one-bar wobble.",
    },
    "stop_atr": {
        "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Protective stop, ATR multiples",
        "tooltip": "Intrabar stop at entry -/+ stop_atr x ATR(length). 0 disables.",
    },
    "eod_cutoff": {
        "default": 3, "min": 0, "max": 12, "step": 1, "type": "int",
        "label": "No entries inside the last N bars of the session",
        "tooltip": "Position is flattened at the session's final bar close regardless.",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published. long / short = one side only.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (Carter published defaults)": {
        "length": [20], "bb_mult": [2.0], "kc_mult": [1.5], "min_sq_bars": [1],
        "exit_mode": ["fade"], "fade_bars": [1], "stop_atr": [2.0], "eod_cutoff": [3],
        "direction": ["both"],
    },
    "Medium (exit rule + squeeze tightness)": {
        "length": [20], "bb_mult": [2.0], "kc_mult": [1.0, 1.5, 2.0],
        "min_sq_bars": [1, 3, 6], "exit_mode": ["fade", "zero", "flip"], "fade_bars": [1, 2],
        "stop_atr": [1.5, 2.0, 3.0], "eod_cutoff": [3], "direction": ["both"],
    },
    "Long   (adds length + direction)": {
        "length": [14, 20, 30], "bb_mult": [1.5, 2.0, 2.5], "kc_mult": [1.0, 1.5, 2.0],
        "min_sq_bars": [1, 3, 6], "exit_mode": ["fade", "zero", "flip"], "fade_bars": [1, 2],
        "stop_atr": [1.5, 2.0, 3.0], "eod_cutoff": [3], "direction": ["both", "long", "short"],
    },
}


def _session_bounds(day_id, n):
    bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b))
        a = b
    return bounds


def _linreg_last(x, length):
    """Pine linreg(src, length, 0): value of the least-squares line at the LAST bar of
    each rolling window. Vectorised via rolling dot-products."""
    s = pd.Series(x)
    k = np.arange(length, dtype=float)
    kbar = k.mean()
    denom = ((k - kbar) ** 2).sum()
    # slope = sum((k-kbar)*(y-ybar)) / denom ; intercept at last bar = ybar + slope*(length-1-kbar)
    ybar = s.rolling(length).mean()
    xs = np.nan_to_num(np.asarray(x, float))
    conv = np.convolve(xs, k[::-1], mode="valid")          # sum_k k*y over each window
    sum_ky = np.full(len(xs), np.nan); sum_ky[length - 1:] = conv
    sum_ky = pd.Series(sum_ky)
    slope = (sum_ky - length * kbar * ybar) / denom
    return (ybar + slope * (length - 1 - kbar)).to_numpy()


def squeeze_indicators(h, l, c, length, bb_mult, kc_mult):
    """Returns (sq_on[bool], mom[float], atr[float]) with Carter/TOS conventions."""
    s = pd.Series(c)
    basis = s.rolling(length).mean()
    dev = s.rolling(length).std(ddof=0)
    upper_bb = basis + bb_mult * dev
    lower_bb = basis - bb_mult * dev
    prev_c = np.concatenate([[np.nan], c[:-1]])
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr = pd.Series(tr).rolling(length).mean()
    upper_kc = basis + kc_mult * atr
    lower_kc = basis - kc_mult * atr
    with np.errstate(invalid="ignore"):
        sq_on = ((lower_bb > lower_kc) & (upper_bb < upper_kc)).to_numpy()
    hh = pd.Series(h).rolling(length).max()
    ll = pd.Series(l).rolling(length).min()
    mid = ((hh + ll) / 2.0 + basis) / 2.0
    mom = _linreg_last((s - mid).to_numpy(), length)
    sq_on = np.where(np.isnan(basis.to_numpy()) | np.isnan(atr.to_numpy()), False, sq_on)
    return sq_on.astype(bool), mom, atr.to_numpy()


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    length: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5,
    min_sq_bars: int = 1, exit_mode: str = "fade", fade_bars: int = 1,
    stop_atr: float = 2.0, eod_cutoff: int = 3, direction: str = "both",
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 300:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None

    length = int(length); min_sq_bars = int(min_sq_bars); fade_bars = int(fade_bars)
    stop_atr = float(stop_atr); eod_cutoff = int(eod_cutoff)
    bb_mult = float(bb_mult); kc_mult = float(kc_mult)

    sq_on, mom, atr = squeeze_indicators(h, l, c, length, bb_mult, kc_mult)

    # squeeze run length and FIRE flag (first bar OFF after >= min_sq_bars ON)
    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= min_sq_bars)

    warm = length * 2 + 5
    fire[:warm] = False

    bounds = _session_bounds(did, n)
    last_bar = np.empty(n, int)
    for a, b in bounds:
        last_bar[a:b] = b - 1

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both", "short")

    pos = 0; entry_px = 0.0; entry_bar = -1; stop_px = None
    pending = None           # (side,) entry at next open, or ("exit",) flat at next open
    fade_cnt = 0
    pnl_list, trade_log = [], []

    def _book(exit_i, px, side, ep, eb):
        pnl = (px - ep) if side > 0 else (ep - px)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(eb), int(exit_i), float(pnl), int(side), float(ep), float(px)))

    for u in range(warm, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        eod = (u == last_bar[u])

        # 1) pending order placed at u-1's close fills at u's OPEN
        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
            elif pos == 0:
                pos = kind; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                a = atr[u - 1]
                stop_px = (entry_px - pos * stop_atr * a) if (stop_atr > 0 and np.isfinite(a)) else None
            pending = None

        # 2) intrabar protective stop (bars after the fill bar; gap-through pays the open)
        if pos != 0 and stop_px is not None and u > entry_bar:
            if pos > 0 and l[u] <= stop_px:
                _book(u, min(o[u], stop_px), pos, entry_px, entry_bar); pos = 0; stop_px = None
            elif pos < 0 and h[u] >= stop_px:
                _book(u, max(o[u], stop_px), pos, entry_px, entry_bar); pos = 0; stop_px = None

        # 3) session end: flat at this bar's close, nothing carried
        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
            pending = None
            continue

        # 4) decisions on u's close
        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue
        if pos != 0:
            want_exit = False
            if exit_mode == "fade":
                fading = (m < m1) if pos > 0 else (m > m1)
                fade_cnt = fade_cnt + 1 if fading else 0
                want_exit = fade_cnt >= fade_bars
            elif exit_mode == "zero":
                want_exit = (m <= 0) if pos > 0 else (m >= 0)
            else:   # flip: opposite-side fire
                want_exit = fire[u] and ((m < 0) if pos > 0 else (m > 0))
            if want_exit:
                pending = ("exit",)
                continue
        if pos == 0 and fire[u] and m != 0:
            bars_left = last_bar[u] - u
            if bars_left > eod_cutoff:
                side = 1 if m > 0 else -1
                if (side > 0 and allow_long) or (side < 0 and allow_short):
                    pending = (side,)

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


if __name__ == "__main__":
    import os, sys
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)
    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))].sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
    for label, kw in [("published fade", {}), ("zero-cross exit", dict(exit_mode="zero")),
                      ("flip exit", dict(exit_mode="flip")), ("min 6 bars squeeze", dict(min_sq_bars=6))]:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                         day_id=day_id, index=df.index, **kw)
        print(label, None if r is None else {k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()})
