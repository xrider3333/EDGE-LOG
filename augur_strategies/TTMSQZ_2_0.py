"""
TTMSQZ 2.0 — TTM Squeeze mechanism variants (round 2 of the Carter squeeze study).

TTMSQZ_1_0 is Carter's published shape with tuning knobs. Round 2 (tools/ttmsqz_round2.py,
2026-08-22) changed the MECHANISM instead and found the only lockbox-positive pockets of the
family, so 2.0 exposes those mechanisms as first-class knobs:

  entry_dir    mom (Carter: momentum sign) · inverse (fade the fire) · slope (momentum
               turning direction, not sign)
  entry_fill   open (market at next open) · range_break (stop order at the squeeze range's
               edge in the trade direction; rests up to 4 bars, gap-through pays the open)
  confirm_bars enter only confirm_bars bars after the fire, and only if the momentum
               histogram strengthened every bar since
  gate         none · trend (long only above / short only below the 200-bar EMA) ·
               morning (no entries at/after 12:00 ET) · daily_sq (yesterday's DAILY-bar
               squeeze was ON — Carter's multi-timeframe stack, prior-day causal)
  exit_mode    fade · zero (as 1.0) · ride (stop/target/EOD only) · target (exit at
               target_mult x the squeeze range height projected from entry)

Everything else is 1.0's honest scaffolding, unchanged: decisions on bar t's close, fills
on bar t+1 (open, or intrabar at a resting level with gap-throughs paying the open),
intrabar ATR stop, intraday only (flat at session close, no entries inside eod_cutoff
bars), PNL in points with costs applied downstream.

Needs day_id (session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

from importlib import util as _u
import os as _os
_sp = _u.spec_from_file_location(
    "TTMSQZ_1_0", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "TTMSQZ_1_0.py"))
_ttm1 = _u.module_from_spec(_sp); _sp.loader.exec_module(_ttm1)
squeeze_indicators = _ttm1.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 2.0 · TTM Squeeze mechanism variants (range-break / slope / gates)'
DESCRIPTION = ("Round-2 rebuild of Carter's TTM Squeeze: entry direction (momentum sign, "
               "inverse, or slope), entry fill (next open or a stop order at the squeeze "
               "range edge), momentum-strengthening confirmation, trend / morning / "
               "daily-squeeze gates, and ride / range-projection exits. Intraday, legal "
               "fills, flat at the close.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "60m"}
# TTM family, round 2 (owner ask 2026-08-22: keep exploring unique/different options).

DEFAULT_PARAMS = {
    "length": {
        "default": 20, "min": 10, "max": 40, "step": 2, "type": "int",
        "label": "Squeeze length (BB / Keltner / momentum)",
        "tooltip": "Carter default 20.",
    },
    "bb_mult": {
        "default": 2.0, "min": 1.0, "max": 3.0, "step": 0.25, "type": "float",
        "label": "Bollinger stdev multiplier", "tooltip": "Carter default 2.0.",
    },
    "kc_mult": {
        "default": 1.5, "min": 1.0, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Keltner ATR multiplier",
        "tooltip": "Carter default 1.5; 2.0+ = tighter squeeze definition.",
    },
    "min_sq_bars": {
        "default": 1, "min": 1, "max": 14, "step": 1, "type": "int",
        "label": "Minimum bars in squeeze before a fire counts",
        "tooltip": "Round 2's ES 30m pocket lives at 12 (only long compressions traded).",
    },
    "entry_dir": {
        "default": "mom", "type": "str", "options": ["mom", "inverse", "slope"],
        "label": "Entry direction",
        "tooltip": "mom = Carter (momentum sign). inverse = fade the fire. slope = trade the "
                   "direction the momentum histogram is TURNING, whatever its sign.",
    },
    "entry_fill": {
        "default": "open", "type": "str", "options": ["open", "range_break"],
        "label": "Entry fill",
        "tooltip": "open = market at the next open (Carter). range_break = stop order at the "
                   "squeeze range's edge in the trade direction, resting up to 4 bars.",
    },
    "confirm_bars": {
        "default": 0, "min": 0, "max": 3, "step": 1, "type": "int",
        "label": "Momentum-strengthening confirmation bars",
        "tooltip": "0 = enter on the fire itself. N = enter N bars later, only if momentum "
                   "strengthened every bar since the fire.",
    },
    "gate": {
        "default": "none", "type": "str", "options": ["none", "trend", "morning", "daily_sq"],
        "label": "Entry gate",
        "tooltip": "trend = 200-bar EMA side. morning = no entries at/after 12:00 ET. "
                   "daily_sq = yesterday's daily-bar squeeze was ON (Carter's MTF stack).",
    },
    "exit_mode": {
        "default": "fade", "type": "str", "options": ["fade", "zero", "ride", "target"],
        "label": "Exit rule",
        "tooltip": "fade / zero as in 1.0. ride = stop / EOD only. target = exit at "
                   "target_mult x the squeeze range height projected from entry (range_break "
                   "entries only; with open fills it behaves like ride).",
    },
    "fade_bars": {
        "default": 1, "min": 1, "max": 4, "step": 1, "type": "int",
        "label": "Consecutive fading bars to exit (fade mode)",
        "tooltip": "1 = strict Carter.",
    },
    "target_mult": {
        "default": 1.0, "min": 0.5, "max": 3.0, "step": 0.5, "type": "float",
        "label": "Range-projection target multiple (target mode)",
        "tooltip": "Exit at entry +/- target_mult x squeeze range height.",
    },
    "stop_atr": {
        "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Protective stop, ATR multiples", "tooltip": "0 disables.",
    },
    "eod_cutoff": {
        "default": 3, "min": 0, "max": 12, "step": 1, "type": "int",
        "label": "No entries inside the last N bars of the session",
        "tooltip": "Flat at the session's final bar close regardless.",
    },
    "direction": {
        "default": "both", "type": "str", "options": ["both", "long", "short"],
        "label": "Trade direction", "tooltip": "Filter applied after entry_dir picks a side.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (round-2 NQ 60m range-break pocket)": {
        "length": [20], "bb_mult": [2.0], "kc_mult": [1.5], "min_sq_bars": [1],
        "entry_dir": ["mom"], "entry_fill": ["range_break"], "confirm_bars": [0],
        "gate": ["none"], "exit_mode": ["ride", "target"], "fade_bars": [1],
        "target_mult": [1.0, 2.0], "stop_atr": [2.0], "eod_cutoff": [3], "direction": ["both"],
    },
    "Medium (mechanism cross)": {
        "length": [20], "bb_mult": [2.0], "kc_mult": [1.5, 2.0], "min_sq_bars": [1, 6, 12],
        "entry_dir": ["mom", "slope"], "entry_fill": ["open", "range_break"],
        "confirm_bars": [0, 2], "gate": ["none", "trend", "morning"],
        "exit_mode": ["fade", "ride", "target"], "fade_bars": [1], "target_mult": [1.0, 2.0],
        "stop_atr": [2.0, 3.0], "eod_cutoff": [3], "direction": ["both"],
    },
}


def _session_last_bar(did, n):
    last = np.empty(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        last[a:b] = b - 1
        a = b
    return last


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    length: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5, min_sq_bars: int = 1,
    entry_dir: str = "mom", entry_fill: str = "open", confirm_bars: int = 0,
    gate: str = "none", exit_mode: str = "fade", fade_bars: int = 1,
    target_mult: float = 1.0, stop_atr: float = 2.0, eod_cutoff: int = 3,
    direction: str = "both",
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
    length = int(length); min_sq_bars = int(min_sq_bars); confirm_bars = int(confirm_bars)
    fade_bars = int(fade_bars); eod_cutoff = int(eod_cutoff)
    bb_mult = float(bb_mult); kc_mult = float(kc_mult)
    target_mult = float(target_mult); stop_atr = float(stop_atr)

    sq_on, mom, atr = squeeze_indicators(h, l, c, length, bb_mult, kc_mult)

    run_len = np.zeros(n, int)
    for i in range(1, n):
        run_len[i] = run_len[i - 1] + 1 if sq_on[i] else 0
    fire = np.zeros(n, bool)
    fire[1:] = (~sq_on[1:]) & (run_len[:-1] >= min_sq_bars)
    warm = length * 2 + 5
    fire[:warm] = False

    rng_hi = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    for i in np.flatnonzero(fire):
        k = run_len[i - 1]
        a = max(0, i - k)
        rng_hi[i] = h[a:i].max(); rng_lo[i] = l[a:i].min()

    ema = pd.Series(c).ewm(span=200, adjust=False).mean().to_numpy() if gate == "trend" else None
    if gate == "morning":
        if index is None:
            return None
        idx = pd.DatetimeIndex(index)
        hourmin = idx.hour.values * 100 + idx.minute.values
    else:
        hourmin = None
    if gate == "daily_sq":
        # daily bars from this timeframe's sessions; day d reads day d-1's squeeze state
        dfd = pd.DataFrame({"h": h, "l": l, "c": c, "d": did})
        g = dfd.groupby("d", sort=True)
        dsq_daily, _, _ = squeeze_indicators(g["h"].max().values, g["l"].min().values,
                                             g["c"].last().values, length, bb_mult, kc_mult)
        prior = np.concatenate([[False], dsq_daily[:-1]])
        dsq = prior[did]
    else:
        dsq = None

    last_bar = _session_last_bar(did, n)
    allow_long = direction in ("both", "long")
    allow_short = direction in ("both", "short")

    pos = 0; entry_px = 0.0; entry_bar = -1; stop_px = None; tgt_px = None
    pending = None      # ("exit",) / ("mkt",side) / ("stop",side,level,expiry,rh,rl)
    fade_cnt = 0
    pnl_list, trade_log = [], []

    def _book(exit_i, px, side, ep, eb):
        p = (px - ep) if side > 0 else (ep - px)
        pnl_list.append(p)
        if return_trades:
            trade_log.append((int(eb), int(exit_i), float(p), int(side), float(ep), float(px)))

    for u in range(warm, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        eod = u == last_bar[u]

        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
                pending = None
            elif kind == "mkt":
                if pos == 0:
                    side = pending[1]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                pending = None
            else:
                _, side, lvl, expiry, rh, rl = pending
                fill = None
                if side > 0:
                    if o[u] >= lvl: fill = o[u]
                    elif h[u] >= lvl: fill = lvl
                else:
                    if o[u] <= lvl: fill = o[u]
                    elif l[u] <= lvl: fill = lvl
                if fill is not None and pos == 0:
                    pos = side; entry_px = fill; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    if exit_mode == "target" and np.isfinite(rh) and np.isfinite(rl):
                        tgt_px = entry_px + side * target_mult * (rh - rl)
                    pending = None
                elif u >= expiry or eod:
                    pending = None

        if pos != 0 and u > entry_bar:
            if stop_px is not None and ((pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px)):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
            elif tgt_px is not None and ((pos > 0 and h[u] >= tgt_px) or (pos < 0 and l[u] <= tgt_px)):
                px = max(o[u], tgt_px) if pos > 0 else min(o[u], tgt_px)
                _book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None

        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar); pos = 0; stop_px = tgt_px = None
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue

        if pos != 0 and exit_mode in ("fade", "zero"):
            if exit_mode == "fade":
                fading = (m < m1) if pos > 0 else (m > m1)
                fade_cnt = fade_cnt + 1 if fading else 0
                if fade_cnt >= fade_bars:
                    pending = ("exit",)
                    continue
            else:
                if (m <= 0) if pos > 0 else (m >= 0):
                    pending = ("exit",)
                    continue

        if pos == 0 and pending is None:
            sig = False; i0 = u
            if confirm_bars > 0:
                i0 = u - confirm_bars
                if i0 > warm and fire[i0]:
                    seg = mom[i0:u + 1]
                    side0 = 1 if mom[i0] > 0 else -1
                    sig = bool(np.all(np.diff(seg) > 0)) if side0 > 0 else bool(np.all(np.diff(seg) < 0))
            else:
                sig = bool(fire[u])
            if not sig:
                continue
            mm = mom[i0]
            if entry_dir == "mom":
                side = 1 if mm > 0 else (-1 if mm < 0 else 0)
            elif entry_dir == "inverse":
                side = -1 if mm > 0 else (1 if mm < 0 else 0)
            else:
                side = 1 if mom[i0] > mom[i0 - 1] else -1
            if side == 0:
                continue
            if (side > 0 and not allow_long) or (side < 0 and not allow_short):
                continue
            if gate == "trend" and ((side > 0) != (c[u] > ema[u])):
                continue
            if gate == "morning" and hourmin[u] >= 1200:
                continue
            if gate == "daily_sq" and not dsq[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            if entry_fill == "open":
                pending = ("mkt", side)
            else:
                if not np.isfinite(rng_hi[i0]):
                    continue
                lvl = rng_hi[i0] if side > 0 else rng_lo[i0]
                pending = ("stop", side, lvl, u + 4, rng_hi[i0], rng_lo[i0])

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
