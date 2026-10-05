r"""DOES THIS STRATEGY READ PRICE LEVELS? Ask the strategy, do not read its source.

WHY THIS EXISTS (2026-10-05, MANAGER #45/#48). The ADJ_/FADJ_ masters are back-adjusted: the
panama/difference method ADDS A CONSTANT to every price before each roll, so that the series has
no artificial step at a switch. On NQ the constant reaching the oldest bars is 3,733.75 points -
the 2010 bars sit nearly four thousand points away from the prices that actually traded.

A strategy built only from price DIFFERENCES cannot tell an adjusted series from a raw one:
`h - l`, `c - entry`, a stop in points, a Bollinger width over a Keltner width are all unchanged
by adding a constant. A strategy that divides a difference by a LEVEL is not. NOISE_1_0's volatility
filter ranks each session by `(H - L) / C` (`_vol_percentile`, augur_strategies/NOISE_1_0.py) - the
numerator survives back-adjustment and the denominator does not, so the percentile ranking changes,
different days are skipped, and different trades are taken. Measured on NOISE_1_8_CT304H over
ADJ_NQ_5m_RTH: 342 of 408 differing trades, 6.0% of the walk-forward net.

WHY THIS IS A BEHAVIOURAL PROBE AND NOT A GREP. The source text cannot separate the two cases.
NOISE's `(H-L)/C` and TTM's squeeze ratio (Bollinger width / Keltner width) are both "a division
involving price"; only the first is level-dependent, because the second divides a difference by
another difference. Any pattern loose enough to catch NOISE also catches TTM, which MANAGER
explicitly wants left alone. So this module adds the instrument's real cumulative roll offset to
every price and asks whether the TRADES change. That question has one right answer and no
threshold to tune.

WHAT IT DELIBERATELY DOES NOT DO. It does not say the result is wrong. A level-dependent strategy
on a back-adjusted master is a strategy whose decisions depend on an artefact of the adjustment -
that is worth knowing before the number is quoted, and it is the owner's call, not this module's.
It warns and gets out of the way: every failure path returns "no warning" rather than blocking a
run, for the same reason the push lock fails open.

THE FLOOR IS NOT COSMETIC. NOISE's vol filter needs 60 reference sessions before it judges a day
at all, so on a short window it stays inactive and the strategy LOOKS level-invariant. Measured on
ADJ_NQ_5m_RTH: 65 sessions caught the dependence by a single trade out of 29, 131 sessions by 86
of 106. Below MIN_SESSIONS this module returns "unknown" and says so, because reporting "clean"
on a window too short to judge is the one answer that would do real damage.
"""
import hashlib
import inspect
import os
import re

import numpy as np

# The probe window. Long enough that a real dependence is unmissable (see the floor note above),
# short enough to cost a couple of seconds. Taken from the END of the master: the newest bars are
# the ones a current run cares about, and a back-adjusted series' offset is already fully
# accumulated there.
PROBE_SESSIONS = 400
MIN_SESSIONS = 120

# Fallback shift, in points, when the roll table cannot be read. Chosen to be the same order as
# NQ's real cumulative offset rather than a round number with no meaning.
FALLBACK_OFFSET_PTS = 2000.0

_VERDICT_CACHE = {}


def _basename(filename):
    """The file name after the last separator of EITHER kind: a Windows path from the box
    (C:\\EdgeLog\\augur_uploads\\ADJ_NQ_1m_ETH.csv) must parse the same on the Linux CI runner,
    where os.path.basename stops only at '/'."""
    return re.split(r"[\\/]", str(filename or ""))[-1]


def is_back_adjusted(filename):
    """Is this master's price series back-adjusted?

    Named by convention: the ADJ_/FADJ_ prefixes are what makes these masters opt-in
    ([[edgelog-adjusted-masters-optin]]). A raw master needs no warning, because there is no
    adjustment for a strategy's level reads to be distorted by.
    """
    base = _basename(filename).upper()
    return base.startswith("ADJ_") or base.startswith("FADJ_")


def _root_of(filename):
    """NQ / ES / ... out of 'ADJ_NQ_5m_RTH.csv'. None when it does not parse."""
    base = _basename(filename)
    parts = base.split("_")
    if len(parts) >= 2 and parts[0].upper() in ("ADJ", "FADJ"):
        return parts[1].upper()
    return None


def adjustment_offset_pts(filename):
    """How far back-adjustment actually moves this instrument's oldest prices, in points.

    This is the shift the probe applies, so the question asked is the real one - "do this
    strategy's decisions change under the adjustment this master carries" - rather than a
    question about an arbitrary number.
    """
    root = _root_of(filename)
    if not root:
        return FALLBACK_OFFSET_PTS
    try:
        from . import rolls
        offs = [float(r.get("offset_pts") or 0.0) for r in rolls.real_switches(root)]
        total = abs(sum(offs))
        return total if total > 1.0 else FALLBACK_OFFSET_PTS
    except Exception:
        return FALLBACK_OFFSET_PTS


def _fingerprint(res):
    """What adding a constant to every price MUST NOT change.

    Entry and exit PRICES are excluded on purpose: those move with the offset in a level-invariant
    strategy too, by definition. What must not move is WHICH trades happened and what each one
    made in points.
    """
    if not res or not res.get("trades"):
        return None
    out = []
    for t in res["trades"]:
        try:
            out.append((int(t[0]), int(t[1]), round(float(t[2]), 6)))
        except (TypeError, ValueError, IndexError):
            return None
    return out


def _call(mod, arrays, offset, params):
    """Run the strategy's own run_backtest, passing only what its signature accepts.

    Calling the strategy rather than re-implementing its walk is BACKTEST_SPEED.md rule 1: a
    hand-written copy of the loop is not the parity-tested arithmetic and gets none of the
    compiled speed.
    """
    sp = inspect.signature(mod.run_backtest).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    kw = {"return_trades": True}
    for key in (params or {}):
        if key in sp or has_kw:
            kw[key] = params[key]
    for key, val in (("volumes", arrays.get("volume")),
                     ("day_id", arrays.get("day_id")),
                     ("index", arrays.get("index"))):
        if val is not None and (key in sp or has_kw):
            kw[key] = val
    return mod.run_backtest(np.asarray(arrays["open"], float) + offset,
                            np.asarray(arrays["high"], float) + offset,
                            np.asarray(arrays["low"], float) + offset,
                            np.asarray(arrays["close"], float) + offset, **kw)


def _tail_sessions(arrays, n_sessions):
    """The last `n_sessions` sessions of `arrays`, with day_id re-based to stay 0-based.

    Re-basing matters: the day_id-aware strategies treat it as an index into their own session
    tables, so a slice that keeps the original numbering would read off the end.
    """
    did = arrays.get("day_id")
    if did is None:
        return None, 0
    did = np.asarray(did)
    days = np.unique(did)
    if len(days) == 0:
        return None, 0
    keep = days[-int(n_sessions):] if len(days) > n_sessions else days
    mask = np.isin(did, keep)
    out = {}
    for key in ("open", "high", "low", "close", "volume", "index"):
        val = arrays.get(key)
        if val is not None:
            out[key] = np.asarray(val)[mask]
    sliced = did[mask]
    _, out["day_id"] = np.unique(sliced, return_inverse=True)
    return out, int(len(keep))


def verdict(mod, arrays, master_filename, params=None):
    """("dependent" | "invariant" | "unknown", detail) for this strategy on this master.

    "unknown" is a real answer and is returned whenever the probe cannot establish either of the
    others - too few sessions, no trades, a strategy that refuses the slice. It never becomes
    "invariant" by default.
    """
    probe, n_sessions = _tail_sessions(arrays, PROBE_SESSIONS)
    if probe is None:
        return "unknown", "the master has no day_id, so a session window cannot be taken"
    if n_sessions < MIN_SESSIONS:
        return "unknown", ("only %d sessions available; %d are needed before a quiet result means "
                           "anything (a filter with a 60-session warm-up stays inactive below "
                           "that and looks level-invariant)" % (n_sessions, MIN_SESSIONS))
    offset = adjustment_offset_pts(master_filename)
    try:
        base = _fingerprint(_call(mod, probe, 0.0, params))
        shifted = _fingerprint(_call(mod, probe, offset, params))
    except Exception as e:
        return "unknown", "the probe could not run the strategy (%s: %s)" % (type(e).__name__, e)
    if base is None or shifted is None:
        return "unknown", "the strategy returned no trades over the probe window"
    if base == shifted:
        return "invariant", ("%d trades over %d sessions are identical when every price moves "
                             "%.0f points" % (len(base), n_sessions, offset))
    n_diff = sum(1 for a, b in zip(base, shifted) if a != b) + abs(len(base) - len(shifted))
    net_b = sum(t[2] for t in base)
    net_s = sum(t[2] for t in shifted)
    pct = (100.0 * (net_s - net_b) / abs(net_b)) if net_b else float("nan")
    return "dependent", ("%d of %d trades change when every price moves %.0f points "
                         "(net %.0f -> %.0f points, %+.1f%%)"
                         % (n_diff, max(len(base), len(shifted)), offset, net_b, net_s, pct))


def _cache_key(mod, master_filename):
    """Deliberately NOT keyed on the run's params.

    Whether a strategy reads price levels is a property of its CODE, not of the cell being
    searched. Keying on params would make a 900-trial validate miss the cache 900 times and probe
    900 times - the warning would then cost more than the thing it is warning about.
    """
    try:
        src = inspect.getsource(mod)
        h = hashlib.sha1(src.encode("utf-8", "replace")).hexdigest()[:16]
    except Exception:
        h = getattr(mod, "__name__", "?")
    return (h, os.path.basename(str(master_filename or "")))


def warning_for(mod, arrays, master_filename, cache=True):
    """The one-line warning to show, or None when there is nothing to say.

    Probed at the strategy's DEFAULT params and cached per (strategy source, master), so a long
    search probes once per process. Every failure path returns None: this must never be the reason
    a run does not finish.
    """
    try:
        if not is_back_adjusted(master_filename):
            return None
        if not hasattr(mod, "run_backtest"):
            return None
        key = _cache_key(mod, master_filename) if cache else None
        if key is not None and key in _VERDICT_CACHE:
            kind, detail = _VERDICT_CACHE[key]
        else:
            kind, detail = verdict(mod, arrays, master_filename, None)
            if key is not None:
                _VERDICT_CACHE[key] = (kind, detail)
        if kind != "dependent":
            return None
        return ("BACK-ADJUSTED MASTER + LEVEL-DEPENDENT STRATEGY: %s is back-adjusted, and this "
                "strategy's decisions move with the price level - %s. Back-adjustment shifts old "
                "price levels without shifting the differences, so any percentage-of-price or "
                "absolute-level read is measuring the adjustment as well as the market. Check the "
                "result against the raw master before quoting it."
                % (os.path.basename(str(master_filename)), detail))
    except Exception:
        return None


def clear_cache():
    """Test-only. Production never needs this - the key already covers a changed strategy."""
    _VERDICT_CACHE.clear()
