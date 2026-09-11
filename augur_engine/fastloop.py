"""COMPILED HOT LOOPS - the same arithmetic, in machine code instead of interpreted Python.

WHY THIS EXISTS. A full-window ENGU-Q backtest walks 5,439,594 one-minute bars. Measured on
the owner's machine 2026-09-11, one backtest took 15.7 seconds, of which essentially ALL was
three plain-Python loops:

    the exponential moving average        3.1s   one multiply-add per bar
    the true range                        ~5.5s  three comparisons per bar
    the trade walk                        7.1s   the strategy proper

A validate runs roughly 300 trials x 8 folds of that, so those three loops cost about
thirteen BILLION interpreted iterations per run. Nothing else in the system is close.

WHAT WAS TRIED FIRST, so nobody repeats it: narrowing the price arrays from 64-bit to 32-bit
floats measured 0.98x - no gain at all. That result is the useful one: it says the cost is NOT
memory traffic, it is the interpreter's per-iteration overhead, which is exactly what a
compiler removes. The prototype of the trade walk measured 15.67s -> 0.06s (247x) with every
one of 1,949 trades identical - same entry bar, same exit bar, P&L equal to within 1e-10
points.

THE RULE THIS MODULE LIVES BY: byte-for-byte agreement with the interpreted code, or it does
not run. Every crowned run, paper leg and book card in this project was earned by the Python
loops; a "faster" engine that disagrees with them would silently invalidate the entire run
history. So:

  * Numba missing or refusing to compile -> the caller keeps its own Python loop. There is no
    degraded fast path and no silent approximation.
  * The compiled walk is used ONLY when the caller asks for nothing it cannot do - no research
    probes, no stop/pause events. Those paths stay interpreted, because they are used by
    drivers and the UI, never in the hot search.
  * EDGELOG_NO_FASTLOOP=1 in the environment turns the whole thing off, so a suspicious result
    can be re-run through the original code without editing anything.

The arithmetic below is transcribed line for line from ENGUQ_1M_ETH_R2_1_0.py / R3. It is
deliberately NOT tidied up: where the original writes `max(a, 0.25)` or compares with `>=`
rather than `>`, so does this, because those choices decide trades at the boundary.
"""
from __future__ import annotations

import os

import numpy as np

__all__ = ["HAVE_NUMBA", "enabled", "ema", "true_range", "engu_walk"]


def _off() -> bool:
    return str(os.environ.get("EDGELOG_NO_FASTLOOP", "")).strip().lower() in ("1", "true", "yes")


try:                                                               # pragma: no cover
    from numba import njit
    HAVE_NUMBA = True
except Exception:                                                  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*a, **k):                                             # type: ignore
        def deco(f):
            return f
        return deco if not a else a[0]


def enabled() -> bool:
    """True when the compiled path may be used at all."""
    return HAVE_NUMBA and not _off()


@njit(cache=True)
def _ema_jit(a, n):
    k = 2.0 / (n + 1.0)
    out = np.empty_like(a)
    out[0] = a[0]
    for i in range(1, a.shape[0]):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


@njit(cache=True)
def _tr_jit(h, l, c):
    n = c.shape[0]
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        x = h[i] - l[i]
        y = abs(h[i] - c[i - 1])
        z = abs(l[i] - c[i - 1])
        if y > x:
            x = y
        if z > x:
            x = z
        tr[i] = x
    return tr


@njit(cache=True)
def _walk_jit(o, h, l, c, ema_a, reg, has_reg, atr, tr, er_ok, has_er, vv, vavg, has_vol,
              tl_len, buf_atr, min_brk, vol_mult, limit_atr, stop_mult, act_R, trail_frac,
              breakeven_R, n_scan, max_hold_bars):
    """The strategy's trade walk. `max_hold_bars` 0 = no time cap (the R2 shape)."""
    n = c.shape[0]
    cap = n // 8 + 64
    e_bar = np.empty(cap, np.int64)
    x_bar = np.empty(cap, np.int64)
    pnl_a = np.empty(cap, np.float64)
    ep_a = np.empty(cap, np.float64)
    k = 0

    xm = (tl_len - 1) / 2.0
    xss = 0.0
    for t in range(tl_len):
        d = t - xm
        xss += d * d

    in_pos = False
    p_bar = 0
    p_ep = 0.0
    p_risk = 0.0
    p_sl = 0.0
    p_act = False

    i = tl_len + 1
    while i < n:
        if in_pos:
            # TIME CAP first, exactly as the R3 file has it: a capped exit takes the bar's
            # close rather than racing a stop touch on the same bar.
            if max_hold_bars > 0 and (i - p_bar) >= max_hold_bars:
                pnl = c[i] - p_ep
                e_bar[k] = p_bar
                x_bar[k] = i
                pnl_a[k] = pnl
                ep_a[k] = p_ep
                k += 1
                in_pos = False
                i += 1
                continue
            if h[i] - p_ep >= act_R * p_risk:
                p_act = True
            if p_act:
                v = h[i] - trail_frac * p_risk
                if v > p_sl:
                    p_sl = v
            if breakeven_R > 0 and (h[i] - p_ep) >= breakeven_R * p_risk:
                if p_ep > p_sl:
                    p_sl = p_ep
            if l[i] <= p_sl:
                fill = o[i] if o[i] < p_sl else p_sl
                pnl = fill - p_ep
                e_bar[k] = p_bar
                x_bar[k] = i
                pnl_a[k] = pnl
                ep_a[k] = p_ep
                k += 1
                in_pos = False
            i += 1
            continue

        if c[i] <= o[i] or not (c[i] > ema_a[i]):
            i += 1
            continue
        if has_reg and (np.isnan(reg[i]) or c[i] <= reg[i]):
            i += 1
            continue
        if vol_mult > 0 and has_vol:
            if np.isnan(vavg[i]) or vv[i] < vol_mult * vavg[i]:
                i += 1
                continue

        s = 0.0
        for t in range(tl_len):
            s += h[i - tl_len + t]
        hmean = s / tl_len
        slope = 0.0
        for t in range(tl_len):
            slope += (t - xm) * (h[i - tl_len + t] - hmean)
        slope /= xss
        if slope >= 0:
            i += 1
            continue
        tl_now = hmean + slope * (tl_len - xm)
        a = atr[i] if not np.isnan(atr[i]) else tr[i]
        if not (c[i] > tl_now + buf_atr * a and c[i] > h[i - 1]):
            i += 1
            continue
        den = a if a > 0.25 else 0.25
        if (c[i] - tl_now) / den < min_brk:
            i += 1
            continue
        if has_er and not er_ok[i]:
            i += 1
            continue

        swing_low = l[i - tl_len]
        for t in range(i - tl_len, i + 1):
            if l[t] < swing_low:
                swing_low = l[t]

        if limit_atr <= 0:
            risk = c[i] - swing_low
            if risk < 0.5:
                i += 1
                continue
            in_pos = True
            p_bar = i
            p_ep = c[i]
            p_risk = risk
            p_sl = c[i] - stop_mult * risk
            p_act = False
            i += 1
            continue

        limit = c[i] - limit_atr * a
        jmax = i + n_scan
        if jmax > n - 1:
            jmax = n - 1
        fill_j = -1
        fill_price = 0.0
        for j in range(i + 1, jmax + 1):
            if l[j] <= limit:
                fill_price = limit if limit < o[j] else o[j]
                fill_j = j
                break
        if fill_j < 0:
            i += 1
            continue
        risk = fill_price - swing_low
        if risk < 0.5:
            i = fill_j + 1
            continue
        in_pos = True
        p_bar = fill_j
        p_ep = fill_price
        p_risk = risk
        p_sl = fill_price - stop_mult * risk
        p_act = False
        i = fill_j + 1

    if in_pos:
        pnl = c[n - 1] - p_ep
        e_bar[k] = p_bar
        x_bar[k] = n - 1
        pnl_a[k] = pnl
        ep_a[k] = p_ep
        k += 1

    return e_bar[:k], x_bar[:k], pnl_a[:k], ep_a[:k]


# ── the three public entry points. Each returns None when the compiled path is unavailable,
#    so a caller writes `out = fastloop.ema(...)` and falls back to its own loop on None.

def ema(a, n):
    if not enabled():
        return None
    return _ema_jit(np.asarray(a, float), float(n))


def true_range(h, l, c):
    if not enabled():
        return None
    return _tr_jit(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float))


def engu_walk(o, h, l, c, ema_a, reg, atr, tr, er_ok, vv, vavg, *, tl_len, buf_atr, min_brk,
              vol_mult, limit_atr, stop_mult, act_R, trail_frac, breakeven_R, n_scan,
              max_hold_bars=0):
    """Returns (entry_bars, exit_bars, pnls, entry_prices) or None if unavailable.

    `reg`, `er_ok`, `vv`/`vavg` may be None - the flags below tell the compiled code to skip
    those gates, which is how the interpreted version behaves when the same inputs are None.
    """
    if not enabled():
        return None
    n = len(c)
    has_reg = reg is not None
    has_er = er_ok is not None
    has_vol = vv is not None and vavg is not None
    return _walk_jit(
        np.asarray(o, float), np.asarray(h, float), np.asarray(l, float),
        np.asarray(c, float), np.asarray(ema_a, float),
        np.asarray(reg, float) if has_reg else np.zeros(n), has_reg,
        np.asarray(atr, float), np.asarray(tr, float),
        np.asarray(er_ok, np.bool_) if has_er else np.ones(n, np.bool_), has_er,
        np.asarray(vv, float) if has_vol else np.zeros(n),
        np.asarray(vavg, float) if has_vol else np.zeros(n), has_vol,
        int(tl_len), float(buf_atr), float(min_brk), float(vol_mult), float(limit_atr),
        float(stop_mult), float(act_R), float(trail_frac), float(breakeven_R),
        int(n_scan), int(max_hold_bars))
