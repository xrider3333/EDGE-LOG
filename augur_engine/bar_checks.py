"""Board C6: bar-data checks before the engine reads a master's bars.

check_bars() inspects OHLC + timestamp arrays and returns a compact report:
  {ok, n_bad_ohlc, n_dup_ts, n_out_of_order, n_nonfinite, n_high_lt_low, jumps:[...], hard:[...], ...}

Policy (data.load_master_arrays calls check_master()):
  HARD  - non-finite / non-positive prices, duplicate or out-of-order timestamps, high < low.
          The run is refused with one line naming the master and the first bad timestamp.
  SOFT  - OHLC containment misses (high < max(open, close) or low > min(open, close)) and
          split-like close-to-close jumps not inside a quarterly roll window. Logged once,
          attached to the result, never change numbers.
Any class listed in SOFT_OVERRIDE is demoted to soft (set after the real-master scan).
Results are cached per (path, size, mtime). Kill switch: AUGUR_BAR_CHECKS=0.
"""
import datetime as _dt
import os

import numpy as np

JUMP_THRESHOLD = 0.25          # |close[i]/close[i-1] - 1| beyond this is a split-like jump
OHLC_TOL = 1e-6                # relative tolerance for containment
MAX_JUMPS_REPORTED = 5

HARD_CLASSES = ("n_nonfinite", "n_dup_ts", "n_out_of_order", "n_high_lt_low")
# Classes demoted to soft because real masters in use would otherwise be refused (see report).
SOFT_OVERRIDE = set()

_CACHE = {}


class BarCheckError(ValueError):
    pass


def enabled():
    return os.environ.get("AUGUR_BAR_CHECKS", "1").strip() != "0"


def _ts_str(t):
    try:
        return _dt.datetime.fromtimestamp(int(t), _dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return str(t)


def _in_roll_window(t):
    from .roll_guard import in_roll_window
    d = _dt.datetime.fromtimestamp(int(t) - 5 * 3600, _dt.timezone.utc).date()
    # a jump on the first bar after a weekend/holiday right after the window still counts
    return any(in_roll_window(d - _dt.timedelta(days=k)) for k in (0, 1, 2, 3))


def check_bars(times, o, h, l, c, threshold=JUMP_THRESHOLD):
    """Pure check over arrays (times = unix seconds). Never mutates its inputs."""
    t = np.asarray(times, dtype="int64")
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    n = len(t)
    first = {}

    px = np.vstack([o, h, l, c]) if n else np.zeros((4, 0))
    bad_px = ~np.isfinite(px).all(axis=0) | (px <= 0).any(axis=0)
    if bad_px.any():
        first["n_nonfinite"] = int(t[np.argmax(bad_px)])
    dt = np.diff(t)
    dup = np.zeros(n, bool)
    ooo = np.zeros(n, bool)
    dup[1:] = dt == 0
    ooo[1:] = dt < 0
    if dup.any():
        first["n_dup_ts"] = int(t[np.argmax(dup)])
    if ooo.any():
        first["n_out_of_order"] = int(t[np.argmax(ooo)])
    with np.errstate(invalid="ignore"):
        hl = h < l
        tol = OHLC_TOL * np.abs(np.maximum(o, c))
        bad_ohlc = ((h < np.maximum(o, c) - tol) | (l > np.minimum(o, c) + tol)) & ~bad_px
    if hl.any():
        first["n_high_lt_low"] = int(t[np.argmax(hl)])

    jumps = []
    n_jumps = 0
    if n > 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            r = c[1:] / c[:-1]
        cand = np.where(np.isfinite(r) & (np.abs(r - 1.0) > threshold))[0] + 1
        for i in cand:
            if _in_roll_window(t[i]):
                continue
            n_jumps += 1
            if len(jumps) < MAX_JUMPS_REPORTED:
                jumps.append({"ts": _ts_str(t[i]), "ratio": round(float(c[i] / c[i - 1]), 4)})

    rep = {
        "n_bars": int(n),
        "n_bad_ohlc": int(bad_ohlc.sum()),
        "n_dup_ts": int(dup.sum()),
        "n_out_of_order": int(ooo.sum()),
        "n_nonfinite": int(bad_px.sum()),
        "n_high_lt_low": int(hl.sum()),
        "n_jumps": int(n_jumps),
        "jumps": jumps,
    }
    hard = [k for k in HARD_CLASSES if rep[k] and k not in SOFT_OVERRIDE]
    rep["hard"] = hard
    rep["first_bad"] = {k: _ts_str(v) for k, v in first.items()}
    rep["ok"] = not hard
    rep["soft"] = bool(rep["n_bad_ohlc"] or n_jumps or any(rep[k] for k in HARD_CLASSES if k not in hard))
    return rep


def check_master(name, path, times, o, h, l, c):
    """Cached check + policy. Returns the report (or None when disabled); raises BarCheckError on HARD."""
    if not enabled():
        return None
    try:
        st = os.stat(path)
        key = (os.path.abspath(path), st.st_size, st.st_mtime)
    except OSError:
        key = None
    rep = _CACHE.get(key) if key else None
    if rep is None:
        rep = check_bars(times, o, h, l, c)
        if key:
            _CACHE[key] = rep
            if rep["soft"] and rep["ok"]:
                print(f"[bar_checks] WARN {name}: bad_ohlc={rep['n_bad_ohlc']} jumps={rep['n_jumps']} "
                      f"{rep['jumps'][:2]} (soft, numbers unchanged)", flush=True)
    if not rep["ok"]:
        k = rep["hard"][0]
        raise BarCheckError(f"[bar_checks] REFUSED master {name}: {k[2:]} x{rep[k]}, first at "
                            f"{rep['first_bad'].get(k)} (set AUGUR_BAR_CHECKS=0 to bypass)")
    return rep


def _cache_clear():
    _CACHE.clear()
