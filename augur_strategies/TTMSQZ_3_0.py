"""
TTMSQZ 3.0 — TTM Squeeze with HIGHER-TIMEFRAME verification (round 4 of the family).

Owner directive 2026-08-23: "use higher time frames for verification on the shorter time
frames." Round 4 (tools/ttmsqz_round4_mtf.py) found the family's one consistent pocket:
base-timeframe squeeze fires taken ONLY while a higher timeframe agrees — and above all
the `sq_on` gate (the 60-minute squeeze is currently COMPRESSED), which was net-positive
in all 12 tested cells across NQ/ES x 5m/15m/30m x both entry styles.

The higher-timeframe frame is built INTERNALLY from the job's own bars (session-anchored
at the first bar of each session), so the strategy runs on any intraday master with no
extra data. Causality: a higher-timeframe bar is usable on base bar u only once COMPLETE —
its last member bar is at or before u — and entries fill on bar u+1, never the decision
bar. (On the base grid a HTF bar "ends" exactly when its last base bar ends, so equality
means both closes are the same timestamped information.)

Everything else is the round-2 scaffolding unchanged: decisions on bar t's close, fills
at t+1 open or a resting stop at the squeeze-range edge (gap-throughs pay the open),
intrabar ATR stop, flat at every session close, PNL in points, costs downstream.

Needs day_id AND index (session boundaries + HTF resample); returns None without.
"""
import numpy as np
import pandas as pd

from importlib import util as _u
import os as _os
_sp = _u.spec_from_file_location(
    "TTMSQZ_1_0", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "TTMSQZ_1_0.py"))
_ttm1 = _u.module_from_spec(_sp); _sp.loader.exec_module(_ttm1)
squeeze_indicators = _ttm1.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 3.0 · TTM Squeeze, higher-timeframe verified (Carter stack)'
DESCRIPTION = ("Round-4 pocket: base-timeframe squeeze fires taken only when a higher "
               "timeframe (default: the 60-minute squeeze being COMPRESSED) verifies the "
               "trade. Carter or range-break entry, fade or ride exit, ATR stop, flat at "
               "the close. The higher-timeframe state is built from the job's own bars, "
               "last-completed-bar causal.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "15m"}
# TTM family round 4 (owner 2026-08-23: higher timeframes verify the shorter ones).

DEFAULT_PARAMS = {
    "length": {
        "default": 20, "min": 12, "max": 32, "step": 2, "type": "int",
        "label": "Base squeeze length (BB / Keltner / momentum)",
        "tooltip": "Carter default 20, on the traded timeframe.",
    },
    "bb_mult": {
        "default": 2.0, "min": 1.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Bollinger stdev multiplier", "tooltip": "Carter default 2.0.",
    },
    "kc_mult": {
        "default": 1.5, "min": 1.0, "max": 2.0, "step": 0.25, "type": "float",
        "label": "Keltner ATR multiplier", "tooltip": "Carter default 1.5.",
    },
    "min_sq_bars": {
        "default": 1, "min": 1, "max": 8, "step": 1, "type": "int",
        "label": "Minimum bars in squeeze before a fire counts",
        "tooltip": "1 = every fire (published).",
    },
    "entry_fill": {
        "default": "open", "type": "str", "options": ["open", "range_break"],
        "label": "Entry fill",
        "tooltip": "open = market at next open (Carter). range_break = stop order at the "
                   "squeeze range edge, resting up to 4 bars.",
    },
    "exit_mode": {
        "default": "fade", "type": "str", "options": ["fade", "ride"],
        "label": "Exit rule",
        "tooltip": "fade = exit after fade_bars fading momentum bars (Carter). "
                   "ride = protective stop / session close only.",
    },
    "fade_bars": {
        "default": 1, "min": 1, "max": 3, "step": 1, "type": "int",
        "label": "Consecutive fading bars to exit (fade mode)", "tooltip": "1 = strict Carter.",
    },
    "stop_atr": {
        "default": 2.0, "min": 1.0, "max": 3.5, "step": 0.25, "type": "float",
        "label": "Protective stop, ATR multiples", "tooltip": "0 disables.",
    },
    "eod_cutoff": {
        "default": 3, "min": 0, "max": 8, "step": 1, "type": "int",
        "label": "No entries inside the last N bars of the session",
        "tooltip": "Flat at the session's final bar close regardless.",
    },
    "gate_tf_min": {
        "default": 60, "min": 30, "max": 240, "step": 30, "type": "int",
        "label": "Verification timeframe, minutes",
        "tooltip": "The higher timeframe whose state must verify each entry. 60 = hourly "
                   "(the round-4 pocket). Must exceed the traded timeframe.",
    },
    "gate_mode": {
        "default": "sq_on", "type": "str",
        "options": ["sq_on", "sign", "rising", "fired", "none"],
        "label": "Verification rule",
        "tooltip": "sq_on = the higher timeframe squeeze is currently compressed (the "
                   "round-4 pocket: trade small releases inside the big coil). sign / "
                   "rising = its momentum agrees / agrees and strengthens. fired = it "
                   "fired in the trade direction within gate_fired_k bars. none = no gate.",
    },
    "gate_len": {
        "default": 20, "min": 12, "max": 32, "step": 2, "type": "int",
        "label": "Verification squeeze length",
        "tooltip": "Length of the squeeze computed on the verification timeframe.",
    },
    "gate_fired_k": {
        "default": 3, "min": 1, "max": 6, "step": 1, "type": "int",
        "label": "Max bars since the higher-timeframe fire (fired mode)",
        "tooltip": "Only used by gate_mode = fired.",
    },
    "direction": {
        "default": "both", "type": "str", "options": ["both", "long", "short"],
        "label": "Trade direction", "tooltip": "Filter on the entry side.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (round-4 pocket: 60m squeeze-on gate)": {
        "length": [20], "bb_mult": [2.0], "kc_mult": [1.5], "min_sq_bars": [1],
        "entry_fill": ["open", "range_break"], "exit_mode": ["fade", "ride"],
        "fade_bars": [1], "stop_atr": [2.0], "eod_cutoff": [3],
        "gate_tf_min": [60], "gate_mode": ["sq_on"], "gate_len": [20],
        "gate_fired_k": [3], "direction": ["both"],
    },
    "Medium (gate rule x timeframe)": {
        "length": [20], "bb_mult": [2.0], "kc_mult": [1.5], "min_sq_bars": [1, 3],
        "entry_fill": ["open", "range_break"], "exit_mode": ["fade", "ride"],
        "fade_bars": [1], "stop_atr": [1.5, 2.0, 2.5], "eod_cutoff": [3],
        "gate_tf_min": [60, 120], "gate_mode": ["sq_on", "sign", "rising"],
        "gate_len": [16, 20, 24], "gate_fired_k": [3], "direction": ["both"],
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


def _htf_gate(h, l, c, did, index, base_minutes, gate_tf_min, gate_len, bb_mult, kc_mult,
              gate_mode, gate_fired_k):
    """(gate_long, gate_short) on the base grid, from the last COMPLETED higher-TF bar.

    HTF bars are session-anchored: within each session, base bars are grouped by
    minutes-since-session-open // gate_tf_min (the session's own first bar is the anchor,
    so RTH and ETH masters both work). A HTF bar's end index = its last base bar; its
    state becomes usable from that base bar's close onward (same information time)."""
    n = len(c)
    idx = pd.DatetimeIndex(index)
    mins = idx.hour.values * 60 + idx.minute.values
    first_of_day = np.zeros(n, int)
    a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]:
            b += 1
        first_of_day[a:b] = mins[a]
        a = b
    bucket = (mins - first_of_day) // int(gate_tf_min)
    grp = did.astype(np.int64) * 10000 + bucket.astype(np.int64)
    # group boundaries (grp is non-decreasing within a day; days ascend)
    change = np.empty(n, bool)
    change[0] = True
    change[1:] = grp[1:] != grp[:-1]
    gstart = np.flatnonzero(change)
    gend = np.append(gstart[1:], n) - 1          # index of each HTF bar's LAST base bar
    nh = len(gstart)
    hh = np.array([h[s:e + 1].max() for s, e in zip(gstart, gend)])
    ll = np.array([l[s:e + 1].min() for s, e in zip(gstart, gend)])
    cc = c[gend]
    sq, mom, _ = squeeze_indicators(hh, ll, cc, int(gate_len), float(bb_mult), float(kc_mult))
    warm_h = int(gate_len) * 2 + 5
    run = np.zeros(nh, int)
    for i in range(1, nh):
        run[i] = run[i - 1] + 1 if sq[i] else 0
    fire = np.zeros(nh, bool)
    fire[1:] = (~sq[1:]) & (run[:-1] >= 1)
    fire[:warm_h] = False
    fire_dir = np.where(fire, np.sign(np.nan_to_num(mom)), 0.0)
    last_fire = np.full(nh, -1)
    lastf = -1
    for i in range(nh):
        if fire[i] and fire_dir[i] != 0:
            lastf = i
        last_fire[i] = lastf

    # map: base bar u -> latest HTF bar j with gend[j] <= u
    j = np.searchsorted(gend, np.arange(n), side="right") - 1
    valid = j >= warm_h
    jj = np.clip(j, 0, nh - 1)
    m_ = np.where(valid, mom[jj], np.nan)
    if gate_mode == "none":
        return np.ones(n, bool), np.ones(n, bool)
    if gate_mode == "sq_on":
        g = np.where(valid, sq[jj], False).astype(bool)
        return g, g.copy()
    if gate_mode == "sign":
        with np.errstate(invalid="ignore"):
            return (m_ > 0), (m_ < 0)
    if gate_mode == "rising":
        mp = np.where(valid & (jj >= 1), mom[np.clip(jj - 1, 0, nh - 1)], np.nan)
        with np.errstate(invalid="ignore"):
            return (m_ > 0) & (m_ >= mp), (m_ < 0) & (m_ <= mp)
    # fired
    lf = np.where(valid, last_fire[jj], -1)
    age = np.where(lf >= 0, jj - lf, 10 ** 9)
    fd = np.where(lf >= 0, fire_dir[np.clip(lf, 0, nh - 1)], 0.0)
    ok = age <= int(gate_fired_k)
    return ok & (fd > 0), ok & (fd < 0)


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    length: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5, min_sq_bars: int = 1,
    entry_fill: str = "open", exit_mode: str = "fade", fade_bars: int = 1,
    stop_atr: float = 2.0, eod_cutoff: int = 3,
    gate_tf_min: int = 60, gate_mode: str = "sq_on", gate_len: int = 20,
    gate_fired_k: int = 3, direction: str = "both",
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 300:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None or index is None:
        return None
    length = int(length); min_sq_bars = int(min_sq_bars); fade_bars = int(fade_bars)
    eod_cutoff = int(eod_cutoff)
    bb_mult = float(bb_mult); kc_mult = float(kc_mult); stop_atr = float(stop_atr)

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

    gate_long, gate_short = _htf_gate(h, l, c, did, index, None, gate_tf_min, gate_len,
                                      bb_mult, kc_mult, gate_mode, gate_fired_k)
    if direction != "both":
        if direction == "long":
            gate_short = np.zeros(n, bool)
        else:
            gate_long = np.zeros(n, bool)

    last_bar = _session_last_bar(did, n)

    pos = 0; entry_px = 0.0; entry_bar = -1; stop_px = None
    pending = None      # ("exit",) / ("mkt",side) / ("stop",side,level,expiry)
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
                    _book(u, o[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
                pending = None
            elif kind == "mkt":
                if pos == 0:
                    side = pending[1]
                    pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                    aa = atr[u - 1]
                    stop_px = entry_px - side * stop_atr * aa if (stop_atr > 0 and np.isfinite(aa)) else None
                    # conservative same-bar stop (audit 2026-08-23): the fill bar's own
                    # range can take out the protective stop; assume it does.
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar); pos = 0; stop_px = None
                pending = None
            else:
                # resting stop-entry order; live on the decision bar + 4 bars (fill is
                # checked before expiry, so the expiry bar itself can still fill).
                _, side, lvl, expiry = pending
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
                    # conservative same-bar stop: entry level and stop both inside this
                    # bar's range -> assume the adverse ordering and take the stop.
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                               (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar); pos = 0; stop_px = None
                    pending = None
                elif u >= expiry or eod:
                    pending = None
        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar); pos = 0; stop_px = None
        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar); pos = 0; stop_px = None
            pending = None
            continue
        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue
        if pos != 0 and exit_mode == "fade":
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
                continue
        if pos == 0 and pending is None and fire[u] and m != 0:
            side = 1 if m > 0 else -1
            if side > 0 and not gate_long[u]:
                continue
            if side < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            if entry_fill == "open":
                pending = ("mkt", side)
            else:
                if not np.isfinite(rng_hi[u]):
                    continue
                lvl = rng_hi[u] if side > 0 else rng_lo[u]
                pending = ("stop", side, lvl, u + 4)

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
