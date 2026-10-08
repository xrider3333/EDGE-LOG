"""APPLY THE ROLL TABLE TO A PRICE SERIES - one implementation, used by every consumer.

WHY (owner GO on ROLL_AUDIT.md decision 13, 2026-09-26). Our NQ and ES masters are
NON-ADJUSTED: each quarterly contract change leaves a step in the price that is not a price
move. A strategy that holds across one books the step as profit or loss, its stops and
trails fire on it, and every indicator with a lookback over it reads a range that never
traded. ROLL_AUDIT measures the damage; this module is the correction.

It reads `tools/data/rolls_<root>.csv` (built by `tools/build_roll_table.py`) and nothing
else. No detector, no per-file copy of a seam finder, no 60-session warm-up before it can
see a switch - the switches are known and written down.

THE TWO ADJUSTMENTS, AND WHICH ONE YOU WANT.

  `back_adjust` (Panama). Every bar gets the sum of all LATER switches' offsets added to it.
  The most recent segment is untouched, so the series ends at today's real prices and the
  history is shifted to match. This is the one for anything that HOLDS a position across a
  roll - ENGU-Q, TTM, ORB - because a price difference between two bars is then a real price
  difference. It is what "back-adjusted" means everywhere else in the industry.

  `forward_adjust`. The mirror image: the OLDEST segment is untouched and later bars are
  shifted down. Price differences are equally correct, but the levels are the 2010 contract's
  levels. Use this when something is keyed to an absolute level learned from history - a
  model feature, a fixed-dollar threshold - because back-adjusting moves sixteen years of
  history under it. ROLL_AUDIT 6.5 makes this point for the ML gates and KEEL.

  Both give identical bar-to-bar differences. They differ only in where the anchor sits, and
  therefore in the absolute numbers a level-based rule sees.

MIXED BARS: THE ONE PLACE AN ADJUSTMENT CANNOT BE HONEST. When a switch happens INSIDE a bar
- twice in 2026 - that bar's open is on the old contract and its close is on the new one. Its
high and low are a blend of two instruments and cannot be recovered. `back_adjust` rebuilds
such a bar as open + the old-contract shift, close + the new-contract shift, and high/low as
the max/min of just those two, then marks it `synthetic` and `no_fill`. That is deliberately
a body with no wick: it is not what traded, it is the smallest honest claim we can make, and
the `no_fill` mask exists so nothing fills an order inside it.

ESTIMATED OFFSETS, AND HOW FAR THEY REACH. The four 2026 tail switches carry
`status=estimated` - they were measured against another root and against the NinjaTrader
capture, not against the raw feed, which stops 2026-06-07. `estimated_switches()` lists them
and `guard_masks(..., block_estimated=True)` keeps a caller flat across them.

They reach further than 2026, and this surprised us. BACK-adjusting shifts a bar by the sum of
every LATER switch, so a 2020 bar's price LEVEL carries the two estimated 2026 offsets even
though no estimated switch falls anywhere near it - a 200-bar 2020 series comes back shifted
+3,628.00, and about 12 of those points are estimate. FORWARD adjustment subtracts a constant
containing the same terms, so they cancel and its pre-2026 levels are fully measured. That is
what `info["levels_rest_on_estimate"]` reports, and it is method-dependent for exactly this
reason. `has_estimated` is the narrower question: does an estimated switch fall inside the
series you hold. A Databento re-pull for 2026-06..09 replaces the estimates with measured
values (docs/DATA_TAIL_2026.md).

SIGN. `offset_pts` is NEW minus OLD, so it is negative in backwardation, which is the
majority of our history: 33 of 64 NQ switches and 39 of 64 ES switches. Nothing here assumes
a direction.
"""
import csv
import os

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
TABLE_DIR = os.path.join(ROOT, "tools", "data")

_CACHE = {}


def load_table(root, table_dir=None):
    """Every row of one root's roll table, earliest first, values already typed.

    Cached by (root, directory) because a backtest asks for this once per slice.
    """
    d = table_dir or TABLE_DIR
    key = (str(root).upper(), d)
    if key in _CACHE:
        return _CACHE[key]
    path = os.path.join(d, "rolls_%s.csv" % str(root).upper())
    if not os.path.exists(path):
        raise FileNotFoundError(
            "no roll table for %s at %s - run tools/build_roll_table.py" % (root, path))
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(dict(
                root=r["root"], old=r["old"], new=r["new"],
                switch_sec=int(r["switch_sec"]), switch_et=r["switch_et"],
                offset_pts=float(r["offset_pts"] or 0.0),
                offset_ci_pts=r.get("offset_ci_pts", ""),
                kind=r["kind"], source=r["source"], status=r["status"],
                note=r.get("note", "")))
    rows.sort(key=lambda r: r["switch_sec"])
    _CACHE[key] = rows
    return rows


def real_switches(root, table_dir=None):
    """The rows that are actual contract changes - the not-a-roll rows are excluded.

    The not-a-roll rows exist so that a feed seam, a weekend gap, a holiday or the end of the
    summer hole is never mistaken for a switch again (ROLL_AUDIT 2.7 found two of them
    already sitting in the ground-truth file). They carry offset 0 and must never adjust
    anything, so every caller here filters them out rather than relying on the zero.
    """
    return [r for r in load_table(root, table_dir) if r["kind"] != "not_a_roll"]


# HOW MUCH A ROW'S OFFSET CAN BE TRUSTED. Three values, weakest last:
#
#   exact     - measured from contract-level raw data (databento_raw). The 64 switches to
#               2026-06-05. Nothing else will ever be `exact` unless the raw feed returns.
#   measured  - measured from two independent feeds that rolled at different times: the step
#               in the Yahoo master minus the NinjaTrader capture, with a stated sample size
#               and spread. Produced by tools/roll_watch.py. Strong enough to adjust on.
#   estimated - inferred, with no second feed to check it against. Today this is only the
#               June 2026 pair: the capture starts 2026-06-23, after that switch, so nothing
#               we still hold can measure it.
#
# A CALLER SHOULD ASK is_trustworthy(row), NOT compare the string. The vocabulary can grow -
# it already has, on 2026-09-28 - and a guard that tests `status == "exact"` silently starts
# refusing rows that are perfectly good, or worse, keeps trusting one that was downgraded.
TRUSTWORTHY_STATUSES = ("exact", "measured")


def is_trustworthy(row):
    """True when this row's offset was measured rather than inferred.

    This is the question a roll guard actually wants answered before it removes an offset or
    decides whether to stay flat across a switch.
    """
    return str((row or {}).get("status", "")) in TRUSTWORTHY_STATUSES


def estimated_switches(root, table_dir=None):
    """Switches whose offset is an estimate rather than a measurement.

    These are the ones worth staying flat across, and the ones a reported result has to
    mention. `guard_masks(..., block_estimated=True)` uses the same test.
    """
    return [r for r in real_switches(root, table_dir) if not is_trustworthy(r)]


def _switch_arrays(root, table_dir=None):
    """(instants, offsets, is_in_bar) for the real switches, as arrays.

    An `in_bar` row's `switch_sec` is the START of the bar the switch happened inside - that
    is what we can observe. The switch itself happened somewhere strictly inside that bar, so
    the instant is nudged one second later here. Without the nudge a bar starting exactly at
    `switch_sec` would be treated as wholly on the new contract, which is precisely wrong for
    an in-bar splice: its open is on the old one. One second is enough for every timeframe,
    since these timestamps are bar starts on every grid we hold.
    """
    rows = real_switches(root, table_dir)
    if not rows:
        return (np.zeros(0, dtype="int64"), np.zeros(0), np.zeros(0, dtype=bool))
    inst = np.array([r["switch_sec"] + (1 if r["kind"] == "in_bar" else 0) for r in rows],
                    dtype="int64")
    off = np.array([r["offset_pts"] for r in rows], dtype="float64")
    in_bar = np.array([r["kind"] == "in_bar" for r in rows], dtype=bool)
    order = np.argsort(inst, kind="stable")
    return inst[order], off[order], in_bar[order]


def _suffix_sums(offsets):
    """suffix[i] = sum(offsets[i:]) - the shift a bar sitting before switch i needs."""
    if not len(offsets):
        return np.zeros(1)
    s = np.zeros(len(offsets) + 1)
    s[:-1] = np.cumsum(offsets[::-1])[::-1]
    return s


def roll_map(times, root, tf_seconds, table_dir=None):
    """How the roll table lands on THIS series' own bar grid.

    `times` are bar-START stamps in unix seconds; `tf_seconds` is the bar length, which is
    what decides whether a switch falls between two bars or inside one. The masters' grids
    differ (1m, 2m, 5m, 15m, 30m, 60m, RTH and 24h), so this has to be recomputed per series
    rather than stored.

    Returns a dict with, per bar: `shift_open` and `shift_close` (the back-adjust shift for
    each end of the bar), `mixed` (a switch falls strictly inside this bar), plus the bar
    indices of each switch and whether any of them is an estimate.
    """
    t = np.asarray(times, dtype="int64")
    inst, off, in_bar = _switch_arrays(root, table_dir)
    n = len(t)
    if n == 0 or not len(inst):
        # An empty series, or a root with no table rows. Every field still has to be present
        # and the right length, because callers index them without checking - a missing key
        # here is an exception in the middle of a backtest.
        z = np.zeros(n)
        return dict(shift_open=z, shift_close=z.copy(), mixed=np.zeros(n, dtype=bool),
                    switch_bars=np.zeros(0, dtype="int64"), switch_rows=[],
                    in_series=np.zeros(0, dtype=bool),
                    has_estimated=False, has_estimated_after=False,
                    n_switches=0, n_switches_total=len(real_switches(root, table_dir)))
    suf = _suffix_sums(off)
    tf = int(tf_seconds)
    # a switch is still ahead of the bar's OPEN when it happens after the bar starts, and
    # still ahead of the bar's CLOSE when it happens at or after the bar ends
    shift_open = suf[np.searchsorted(inst, t, side="right")]
    shift_close = suf[np.searchsorted(inst, t + tf, side="left")]
    mixed = shift_open != shift_close

    rows = real_switches(root, table_dir)
    rows = sorted(rows, key=lambda r: r["switch_sec"] + (1 if r["kind"] == "in_bar" else 0))

    # WHICH SWITCH LANDS ON WHICH BAR - and which lands on no bar at all.
    # searchsorted alone is not enough. A switch AFTER this series ends gets clamped to
    # len(t) - 1, i.e. the last bar, and a caller then guards the last bar of a 2020 series
    # because of a roll in 2026. A switch BEFORE the series starts gets -1. Both have to be
    # reported as "not in this series" rather than silently attached to an end bar.
    in_series = (inst >= t[0]) & (inst < t[-1] + tf)
    switch_bars = np.where(in_series, np.searchsorted(t, inst, side="right") - 1, -1)
    switch_bars[inst >= t[-1] + tf] = n                 # past the end, so no bar to guard

    # `n_switches` and `has_estimated` describe THIS SERIES, so a caller can ask "does the
    # data I hold contain a switch, or an estimated one" and get an answer about its own bars.
    est = np.array([not is_trustworthy(r) for r in rows], dtype=bool) if rows else np.zeros(0, dtype=bool)
    # ...and separately: the back-adjust SHIFT on this series is the sum of every switch that
    # comes after it, so an old series' absolute LEVELS still depend on the 2026 estimates even
    # though no estimated switch falls inside it. Forward adjustment cancels those, so it does
    # not. `has_estimated_after` is what tells a caller its levels rest on an estimate.
    after = inst >= t[0]
    return dict(shift_open=shift_open, shift_close=shift_close, mixed=mixed,
                switch_bars=switch_bars, switch_rows=rows, in_series=in_series,
                has_estimated=bool((est & in_series).any()) if len(est) else False,
                has_estimated_after=bool((est & after).any()) if len(est) else False,
                n_switches=int(in_series.sum()), n_switches_total=len(rows))


def back_adjust(times, opens, highs, lows, closes, root, tf_seconds, table_dir=None):
    """Panama back-adjustment: the newest segment keeps its real prices.

    Returns (opens, highs, lows, closes, info) with new arrays; the inputs are not modified.
    `info["synthetic"]` marks bars rebuilt because a switch fell inside them, and
    `info["no_fill"]` is the mask nothing should fill an order inside.
    """
    return _adjust(times, opens, highs, lows, closes, root, tf_seconds, table_dir, forward=False)


def forward_adjust(times, opens, highs, lows, closes, root, tf_seconds, table_dir=None):
    """Forward adjustment: the OLDEST segment keeps its real prices.

    Same bar-to-bar differences as `back_adjust`, different absolute levels. Use it when a
    rule or a model feature is keyed to a level learned from history (ROLL_AUDIT 6.5).
    """
    return _adjust(times, opens, highs, lows, closes, root, tf_seconds, table_dir, forward=True)


def _adjust(times, opens, highs, lows, closes, root, tf_seconds, table_dir, forward):
    o = np.asarray(opens, dtype="float64").copy()
    h = np.asarray(highs, dtype="float64").copy()
    l = np.asarray(lows, dtype="float64").copy()
    c = np.asarray(closes, dtype="float64").copy()
    m = roll_map(times, root, tf_seconds, table_dir)
    so, sc = m["shift_open"], m["shift_close"]
    if forward:
        # anchor on the oldest bar instead of the newest: subtract the total of every switch
        # in the table, which leaves the first segment at zero shift
        total = so[0] if len(so) else 0.0
        so = so - total
        sc = sc - total
    mixed = m["mixed"]
    clean = ~mixed
    # An ordinary bar is wholly on one contract, so all four prices take the same shift.
    h[clean] += sc[clean]
    l[clean] += sc[clean]
    o[clean] += sc[clean]
    c[clean] += sc[clean]
    # A mixed bar opened on one contract and closed on another. Its high and low blend the
    # two and cannot be recovered, so the bar is rebuilt as a body with no wick and flagged.
    if mixed.any():
        o[mixed] += so[mixed]
        c[mixed] += sc[mixed]
        h[mixed] = np.maximum(o[mixed], c[mixed])
        l[mixed] = np.minimum(o[mixed], c[mixed])
    # Whether the RESULT rests on an estimated offset depends on the method. Back-adjusting
    # shifts a bar by the sum of every later switch, so a 2020 bar's level carries the 2026
    # estimates. Forward-adjusting subtracts a constant that contains the same terms, so they
    # cancel for any bar before them and only a switch INSIDE the series still matters.
    info = dict(synthetic=mixed, no_fill=mixed.copy(), shift_open=so, shift_close=sc,
                n_switches=m["n_switches"], n_switches_total=m["n_switches_total"],
                has_estimated=m["has_estimated"],
                levels_rest_on_estimate=(m["has_estimated"] if forward
                                         else m["has_estimated_after"]),
                switch_bars=m["switch_bars"], switch_rows=m["switch_rows"],
                in_series=m["in_series"],
                method="forward" if forward else "back")
    return o, h, l, c, info


def guard_masks(times, root, tf_seconds, table_dir=None, block_estimated=False):
    """Bars a caller should not hold or enter across.

    `no_fill` is every mixed bar - nothing traded at those prices. `flat_by` is the last bar
    wholly on the old contract before each switch, and `no_entry` covers the mixed bar and
    the first clean bar after it, so a position is never opened straddling a switch. With
    `block_estimated`, the same protection is extended around the four 2026 switches whose
    offset is an estimate rather than a measurement, which is how a caller declines to trust
    a number the raw feed never confirmed.
    """
    t = np.asarray(times, dtype="int64")
    m = roll_map(t, root, tf_seconds, table_dir)
    n = len(t)
    no_fill = m["mixed"].copy()
    no_entry = m["mixed"].copy()
    flat_by = np.zeros(n, dtype=bool)
    rows = m["switch_rows"]
    for i, b in enumerate(m["switch_bars"]):
        b = int(b)
        # -1 means the switch is before this series and n means it is after it; in both cases
        # there is no bar here to keep flat, and guarding an end bar because of a roll years
        # away is a false positive a caller cannot tell from a real one.
        if b < 0 or b >= n:
            continue
        est = i < len(rows) and not is_trustworthy(rows[i])
        if b - 1 >= 0:
            flat_by[b - 1] = True
        no_entry[b] = True
        if b + 1 < n:
            no_entry[b + 1] = True
        if block_estimated and est:
            lo, hi = max(0, b - 1), min(n, b + 2)
            no_entry[lo:hi] = True
            no_fill[lo:hi] = True
    return dict(no_fill=no_fill, no_entry=no_entry, flat_by=flat_by)


def stitch_usd(times, root, tf_seconds, entry_idx, exit_idx, side, mult, table_dir=None):
    """The dollars a trade booked purely from contract switches it held across.

    For auditing an unadjusted backtest: how much of a trade's profit was never a price move.
    `side` is +1 long, -1 short. Positive means the switches flattered the trade.
    """
    t = np.asarray(times, dtype="int64")
    inst, off, _ = _switch_arrays(root, table_dir)
    if not len(inst) or entry_idx is None or exit_idx is None:
        return 0.0
    a, b = int(entry_idx), int(exit_idx)
    if a > b or a < 0 or b >= len(t):
        return 0.0
    lo, hi = int(t[a]), int(t[b]) + int(tf_seconds)
    held = off[(inst > lo) & (inst < hi)]
    return float(held.sum() * int(side) * float(mult))


# ══════════════════════════════════════════════════════════════════════════════════════════
# THE ENGINE ROLL GUARD (owner ask 2026-10-08 via MANAGER #54: "fix so this doesn't happen again")
#
# ROLL_AUDIT (09-25) fixed the masters, but 25 strategy files still carried their own copy of a
# day-level `detect_roll_seams`: it found 19 of 64 NQ and 16 of 64 ES switches, flagged ~33 news
# gaps per root, and could not see the first roll of a short window - so positions rode real
# switches and booked the contract step as profit or loss (DISC's RSIDIV #163 audit: ~4-5%).
#
# Everything below is the ONE seam calendar and the guard the engine applies around every
# strategy call on an unadjusted NQ / ES master:
#   * `seam_days` - the copies' exact signature, answered from the table. The strategy files
#     import it under their old name, so their logic is untouched and only the calendar is true.
#   * `roll_context` - what `seam_days` needs and a strategy never passes: the root and the bar
#     grid. Thread-local, so parallel folds and NQ / ES runs side by side cannot see each other's.
#   * `crossing_trades` - trades whose position was open over a switch instant. On an unadjusted
#     tape every one of them booked the step; the engine refuses such a run (`RollGuardError`)
#     unless the strategy is ROLL_AWARE (it removes the offset itself, tested).
#   * `roll_stamp` - what every new saved run records about rolls.
# The ship lint (tests/test_roll_detector_lint.py) fails any new code that defines its own detector.
# ══════════════════════════════════════════════════════════════════════════════════════════
import contextlib
import hashlib
import threading

_CTX = threading.local()

ROLL_ROOTS = {"NQ": "NQ", "MNQ": "NQ", "ES": "ES", "MES": "ES"}
POINT_VALUE = {"NQ": 20.0, "MNQ": 2.0, "ES": 50.0, "MES": 5.0}   # $ per point, for the stamp


def normalize_instrument(instrument):
    """'NQ1!' / '/NQ' / 'NQ=F' / 'nq ' -> 'NQ'; a contract code ('NQZ6', 'MNQH2026') -> its root.
    Anything else comes back upper-cased and stripped (TTM attack 4, 2026-10-08)."""
    import re
    s = str(instrument or "").upper().strip().lstrip("/@")
    s = re.sub(r"\s+(INDEX|COMDTY|CURNCY)$", "", s)              # Bloomberg 'NQ1 Index'
    s = re.sub(r"\.[A-Z]\.\d+$", "", s)                         # Databento continuous 'NQ.c.0' / 'NQ.v.0'
    s = re.sub(r"(=F|#|_CONT|_CONTINUOUS|\d*!)$", "", s)          # Yahoo, IQFeed/TS, house, TradingView
    if s in CQG_ROOTS:
        return CQG_ROOTS[s]                                        # CQG 'ENQ' = NQ, 'EP' = ES
    m = re.match(r"^([A-Z0-9]{1,4}?)\d{1,2}$", s)                 # bare continuous 'NQ1', 'ES2'
    if m and (m.group(1) in ROLL_ROOTS or m.group(1) in NO_TABLE_FUTURES):
        return m.group(1)
    m = re.match(r"^([A-Z0-9]{1,4}?)[FGHJKMNQUVXZ]\d{1,4}$", s)   # contract 'NQZ6', 'NQZ2026'
    if m and (m.group(1) in ROLL_ROOTS or m.group(1) in NO_TABLE_FUTURES):
        return m.group(1)
    return s


CQG_ROOTS = {"ENQ": "NQ"}    # CQG's ES code 'EP' is also a stock ticker: not mapped (refused on a futures source)
# sources that hold futures prices only (the registry: db_* and merged are NQ / ES); an
# unregistered tape on one of these with an instrument the guard does not know is refused
FUTURES_SOURCE_PREFIXES = ("db_noadj", "db_adj", "db_fadj", "merged")


def futures_like(instrument):
    """True when the raw instrument string is written like a futures symbol (continuous '!', '/',
    '=F', or a month code on a futures root) - whatever its root."""
    import re
    s = str(instrument or "").upper().strip()
    return bool(s.startswith(("/", "@")) or s.endswith(("=F", "#", "_CONT")) or re.search(r"\d*!$", s) or
                re.search(r"\.[A-Z]\.\d+$", s) or s.endswith(" INDEX") or
                normalize_instrument(s) in NO_TABLE_FUTURES or
                re.match(r"^[A-Z0-9]{1,4}?[FGHJKMNQUVXZ]\d{1,4}$", s) and
                normalize_instrument(s) != s)


def point_value(instrument):
    return POINT_VALUE.get(normalize_instrument(instrument), 1.0)


REPORT_MODE_TOOLS = frozenset({"roll_guard_probe"})     # tools/<name>.py allowed to waive refusals


@contextlib.contextmanager
def guard_mode(mode):
    """'refuse' (the default) or 'report'. 'report' waives the refusals (they become warnings and
    the stamp says the result is not a research result); signals are still planned. Only the roll
    audit tool (tools/roll_guard_probe.py) and the test suite may ask for it - a research script
    that wraps itself in report mode is refused (TTM attack 8). Thread-local."""
    if str(mode) == "report" and not _report_mode_allowed():
        raise RollGuardError("guard_mode('report') is for the roll audit tool (tools/roll_guard_probe.py) "
                             "and the tests only; a research run takes the guard's answer.")
    prev = getattr(_CTX, "mode", None)
    _CTX.mode = str(mode)
    try:
        yield
    finally:
        _CTX.mode = prev


def current_guard_mode():
    return getattr(_CTX, "mode", None) or "refuse"


# LIVE, PAPER AND NIGHTLY-SHADOW PATHS NEVER REFUSE (MANAGER D2, 2026-10-08). A refusal there would
# stop a paper leg or a harm-monitor line - NOISE's unadjusted paper leg held a trade across the
# 2026-09-14 in-bar splice, and every rolling window that includes that day would trip. So a call
# that comes THROUGH one of these api/ modules is reported (stamp + one warning line), not refused.
# Moving those legs to adjusted masters is the owning lanes' call; research runs refuse.
REPORT_ONLY_MODULES = frozenset({"cloud_signal", "paper", "gate_live", "book_shadow",
                                 "etf_book_shadow", "noise_forward", "qqq_exec", "nt_sync"})
# ...and the tools/ scripts that BUILD live state or read a live / paper leg forward: the live KEEL
# state (fitted on the NQ legs' backtest trades - a planned run would change live sizing), its
# backfill, the paper / QQQ paper legs, the paper gate calibration, and the forward reads (harm
# monitors that must see what the live leg sees). Changing any of them is the owner's call.
REPORT_ONLY_TOOLS = frozenset({"keel_live_state", "backfill_keel", "paper_forward", "paper_gate_calibrate",
                               "qqq_paper", "noise_forward_log", "dip_forward_read", "orb_rollweek_forward",
                               "orb_orderflow_shadow"})
_WARNED = set()


def _report_only_caller():
    """True when the current call stack passes through a live / paper / nightly-shadow api module,
    or a tools/ script that builds live state or reads a live leg forward."""
    import sys
    allowed = _report_only_paths()
    f = sys._getframe(1)
    while f is not None:
        p = _frame_module_path(f)
        if p and p in allowed:
            return True
        f = f.f_back
    return False


def _frame_module_path(frame):
    """The real file of the module a frame runs in: its globals must BE the __dict__ of a module in
    sys.modules, and the path is that module's __spec__.origin (for the script run as __main__,
    sys.argv[0]). Code exec'd with a hand-made globals dict that merely says __file__ = ... has no
    path here (TTM attacks 8b / 8c / 11b)."""
    import sys
    g = frame.f_globals
    name = g.get("__name__")
    mod = sys.modules.get(name) if isinstance(name, str) else None
    if mod is None or getattr(mod, "__dict__", None) is not g:
        return None
    if name == "__main__":
        path = sys.argv[0] if sys.argv and sys.argv[0] else None
    else:
        spec = getattr(mod, "__spec__", None)
        path = getattr(spec, "origin", None) if spec is not None else None
    if not path or path in ("built-in", "frozen"):
        return None
    return os.path.normcase(os.path.abspath(path))


def _report_mode_allowed():
    """The roll audit tool, or a test module of this checkout's suite running under pytest -
    both by the real module path of a frame on the stack (_frame_module_path)."""
    import sys
    tools = {os.path.normcase(os.path.join(ROOT, "tools", m + ".py")) for m in REPORT_MODE_TOOLS}
    tests = os.path.normcase(os.path.join(ROOT, "tests")) + os.sep
    under_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    f = sys._getframe(1)
    while f is not None:
        ap = _frame_module_path(f)
        if ap and (ap in tools or (under_pytest and ap.startswith(tests) and
                                   os.path.basename(ap).startswith(("test_", "conftest")))):
            return True
        f = f.f_back
    return False


def _report_only_paths():
    """The absolute paths of the report-only modules IN THIS CHECKOUT - a file elsewhere with the
    same name gets no exemption (TTM attack 11)."""
    return frozenset([os.path.normcase(os.path.join(ROOT, "api", m + ".py")) for m in REPORT_ONLY_MODULES] +
                     [os.path.normcase(os.path.join(ROOT, "tools", m + ".py")) for m in REPORT_ONLY_TOOLS])


def bind(fn, root, times, tf_seconds, strategy=None, table_dir=None, plan=None):
    """`fn` wrapped so every call runs inside this series' roll context (one line at a call site
    instead of re-indenting it). With a `plan` whose signals are adjusted, every result's trades are
    re-priced to raw contract prices (`reprice_result`, MANAGER #58) - for a slice of the planned
    series too, located by its place in the planned close array."""
    adj = bool(plan and plan.get("adjust"))
    ratio = adj and plan.get("method") == "ratio"
    if plan and plan.get("trusted_path"):
        fn = trusted_module(plan["trusted_path"]).run_backtest      # roll-aware: the pinned file itself

    def call(*args, **kwargs):
        want = bool(kwargs.get("return_trades"))
        if ratio:
            kwargs["return_trades"] = True        # the headline P&L is re-derived from the trades
        with roll_context(root, times, tf_seconds, table_dir=table_dir, strategy=strategy):
            res = fn(*args, **kwargs)
        if not adj or not isinstance(res, dict):
            return res
        if res.get("trades"):
            close = args[3] if len(args) > 3 else kwargs.get("close")
            off = _slice_offset(close, plan.get("close_ref"))
            if off is None:
                if ratio:
                    raise RollGuardError(
                        "%s: could not place these prices on the planned series, so their fills cannot "
                        "be re-priced to raw contract prices." % (os.path.basename(str(strategy or "")) or "strategy"))
            else:
                res = reprice_result(res, plan, off)
        if ratio and not want:
            res = dict(res)
            res.pop("trades", None)
        return res
    return call

# Strategies that HOLD across a switch on an unadjusted master but remove the contract offset
# themselves, from this same table. The guard lets their crossing trades stand; each entry has a
# test (tests/test_roll_detector_lint.py::test_roll_aware_files_adjust_from_the_table) proving the
# file reads rolls_<ROOT>.csv and never calls a seam detector. Add a file here only with such a test.
ROLL_AWARE = frozenset({"NQDIP_1_2.py", "NQDIP_1_3.py", "NQDIP_1_4.py"})


class RollGuardError(RuntimeError):
    """A run on an unadjusted NQ / ES master held a position across a contract switch."""


class RollContextMissing(RuntimeError):
    """`seam_days` was called with no roll context - i.e. not through the engine."""


def roll_root(instrument):
    """'NQ' / 'ES' for an NQ- or ES-family futures instrument (any alias - normalize_instrument),
    else None."""
    return ROLL_ROOTS.get(normalize_instrument(instrument))


def unadjusted_futures_root(meta):
    """The roll root when `meta` (a master row) is an UNADJUSTED NQ / ES futures master, else None.

    Adjusted masters (db_adj_* / db_fadj_*) are built from this table already; stock and fund
    masters have no contract rolls."""
    meta = meta or {}
    root = roll_root(meta.get("instrument"))
    if root is None:
        return None
    src = str(meta.get("source") or "")
    if src.startswith(("db_adj", "db_fadj", "alpaca")):
        return None
    return root


def tf_seconds_of(meta, times):
    """Bar length in seconds: from the master's timeframe ('5m', '1h', '30s'), else the grid."""
    tf = str((meta or {}).get("timeframe") or "").strip().lower()
    unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if tf[:-1].isdigit() and tf[-1:] in unit:
        return int(tf[:-1]) * unit[tf[-1]]
    t = np.asarray(times, dtype="int64")
    if len(t) > 1:
        d = np.diff(t)
        d = d[d > 0]
        if len(d):
            return int(np.median(d))
    return 60


def epoch_seconds(stamps):
    """Bar / session timestamps (pandas index, datetime64, Timestamps or epoch numbers) -> int64 s."""
    if stamps is None:
        return np.zeros(0, dtype="int64")
    a = np.asarray(stamps)
    if a.dtype.kind in "iuf":
        a = a.astype("int64")
        return a // 1000 if len(a) and a.max() > 10 ** 11 else a     # ms stamps -> s
    import pandas as pd
    idx = pd.DatetimeIndex(stamps)
    if idx.tz is None:
        # a naive stamp is an Eastern wall time in every EDGE-LOG master
        idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    return (idx.tz_convert("UTC").asi8 // 10 ** 9).astype("int64")


@contextlib.contextmanager
def roll_context(root, times, tf_seconds, table_dir=None, strategy=None):
    """Make `seam_days` answer for this series while the block runs (thread-local, nestable)."""
    prev = getattr(_CTX, "ctx", None)
    _CTX.ctx = dict(root=root, times=epoch_seconds(times), tf=int(tf_seconds),
                    table_dir=table_dir, strategy=strategy)
    try:
        yield _CTX.ctx
    finally:
        _CTX.ctx = prev


def current_roll_context():
    return getattr(_CTX, "ctx", None)


def seam_days_for(day_ts, root, times, tf_seconds, table_dir=None):
    """Indices s into `day_ts` (one entry per session, the session's FIRST bar) of the sessions a
    strategy must not hold into: the first session on the new contract.

    A switch INSIDE a session (24h masters switch at 00:00 UTC; the 2026 in-bar splices) marks that
    session itself - both contracts traded in it. A switch BETWEEN sessions marks the next session.
    Session ends come from the bar grid `times`, so a weekday-evening switch on an RTH master is
    not put a day early. A switch before the first session or after the last is in no session of
    this series and marks nothing. No warm-up: a one-quarter window sees its own roll.
    """
    ds = epoch_seconds(day_ts)
    t = np.asarray(times, dtype="int64")
    if not len(ds) or not len(t):
        return []
    inst, _off, _ib = _switch_arrays(root, table_dir)
    if not len(inst):
        return []
    tf = int(tf_seconds)
    pos = np.searchsorted(t, ds, side="left")
    nxt = np.r_[pos[1:], len(t)]
    last_bar = t[np.clip(nxt - 1, 0, len(t) - 1)]
    end = last_bar + tf                                   # each session ends when its last bar does
    out = set()
    for x in inst:
        k = int(np.searchsorted(ds, x, side="right")) - 1
        if k >= 0 and x < end[k]:
            out.add(k)                                    # the switch happened during session k
        elif k + 1 < len(ds) and k >= 0:
            out.add(k + 1)                                # between k and k+1: k+1 opens on the new one
    return sorted(out)


def seam_days(day_open, day_close, day_ts, *detector_args, **detector_kwargs):
    """THE seam calendar, with the signature of the 25 retired copies of `detect_roll_seams`.

    The copies' tuning knobs (ratio_th, abs_th, base_win, pre_days, post_days) are accepted and
    ignored - there is nothing to tune when the switches are written down. The root and the bar
    grid come from `roll_context`, which the engine sets around every strategy call."""
    ctx = current_roll_context()
    if ctx is None:
        raise RollContextMissing(
            "the roll calendar needs to know which market and bar grid it is answering for. "
            "Run the strategy through augur_engine.run_backtest (or Auto-Validate / sweeps), or wrap "
            "the call in augur_engine.rolls.roll_context(root, bar_times, bar_seconds).")
    ctx["calls"] = ctx.get("calls", 0) + 1
    if ctx.get("root") is None:
        return []                                         # no contract rolls on this series
    return seam_days_for(day_ts, ctx["root"], ctx["times"], ctx["tf"], ctx.get("table_dir"))


def trade_bounds(trades):
    """(entry_idx, exit_idx, side) arrays from an engine trade list - tuples
    (entry_idx, exit_idx, pnl, side, ...) or dicts with those keys. Unreadable rows are skipped."""
    ei, xi, sd = [], [], []
    for tr in trades or []:
        try:
            if isinstance(tr, dict):
                a = tr.get("entry_idx", tr.get("ei"))
                b = tr.get("exit_idx", tr.get("xi"))
                s = tr.get("side", tr.get("dir", 1))
            else:
                a, b, s = tr[0], tr[1], (tr[3] if len(tr) > 3 else 1)
            if a is None or b is None:
                continue
            ei.append(int(a)); xi.append(int(b)); sd.append(1 if float(s) >= 0 else -1)
        except (TypeError, ValueError, IndexError):
            continue
    return (np.asarray(ei, dtype="int64"), np.asarray(xi, dtype="int64"),
            np.asarray(sd, dtype="int64"))


def crossing_trades(times, root, tf_seconds, entry_idx, exit_idx, table_dir=None):
    """Boolean per trade: a switch instant fell while the position was open.

    Same holding window as `stitch_usd` - from the entry bar's start to the exit bar's end - so the
    trades counted here are exactly the ones whose P&L carries a contract step."""
    t = np.asarray(times, dtype="int64")
    a = np.asarray(entry_idx, dtype="int64")
    b = np.asarray(exit_idx, dtype="int64")
    if not len(a) or not len(t):
        return np.zeros(len(a), dtype=bool)
    inst, _off, _ib = _switch_arrays(root, table_dir)
    if not len(inst):
        return np.zeros(len(a), dtype=bool)
    a = np.clip(a, 0, len(t) - 1)
    b = np.clip(b, 0, len(t) - 1)
    lo = t[a]
    hi = t[b] + int(tf_seconds)
    n_in = np.searchsorted(inst, hi, side="left") - np.searchsorted(inst, lo, side="right")
    return (n_in > 0) & (b >= a)


def table_sha(root, table_dir=None):
    """sha256 (first 12 hex) of rolls_<ROOT>.csv, for the stamp and the trial-cache key."""
    p = os.path.join(table_dir or TABLE_DIR, "rolls_%s.csv" % str(root).upper())
    try:
        with open(p, "rb") as fh:
            return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()[:12]
    except OSError:
        return ""


def check_crossings(strategy_name, meta, times, trades, table_dir=None, roll_aware=None):
    """The guard: raise RollGuardError if a run on an unadjusted NQ / ES master held any trade
    across a switch and the strategy is not ROLL_AWARE. Returns the number of crossing trades.
    The engine paths call it only for plans that refuse crossings, so they pass roll_aware=False:
    the plan already decided (by the code that runs, not the file name)."""
    if roll_aware is None:
        roll_aware = is_roll_aware(strategy_name)
    root = unadjusted_futures_root(meta)
    if root is None or not trades:
        return 0
    tf = tf_seconds_of(meta, times)
    t = epoch_seconds(times)
    ei, xi, _sd = trade_bounds(trades)
    cross = crossing_trades(t, root, tf, ei, xi, table_dir)
    n = int(cross.sum())
    base = os.path.basename(str(strategy_name or ""))
    if n and not roll_aware and (current_guard_mode() == "report" or _report_only_caller()):
        key = (base, root)
        if key not in _WARNED:
            _WARNED.add(key)
            import sys
            print("ROLL GUARD (report only, live/paper/shadow path): %s held %d trade(s) across a %s "
                  "contract switch on the unadjusted master - the roll stamp records it; a research "
                  "run of the same thing is refused." % (base or "strategy", n, root), file=sys.stderr)
        return n
    if n and not roll_aware:
        import pandas as pd
        days = sorted({str(pd.Timestamp(int(t[int(i)]), unit="s", tz="UTC")
                           .tz_convert("America/New_York").date()) for i in ei[cross][:6]})
        raise RollGuardError(
            "%s held %d trade%s across a %s contract switch on the unadjusted master (entries %s%s). "
            "Its profit would include the roll step, which is not a price move. Run it on the "
            "adjusted master (source db_adj_*), or use a roll-aware version of the strategy."
            % (base or "this strategy", n, "" if n == 1 else "s", root, ", ".join(days),
               ", ..." if n > len(days) else ""))
    return n


def combine_stamps(stamps):
    """One stamp for a book: counts and dollars summed over the legs that have one; the master
    types, sources and calendars listed. None when no leg carried a stamp."""
    st = [s for s in (stamps or []) if isinstance(s, dict)]
    if not st:
        return None
    out = dict(legs_stamped=len(st))
    for k in ("switches_in_window", "switches_estimated", "trades_crossing"):
        out[k] = int(sum(int(s.get(k) or 0) for s in st))
    for k in ("usd_crossing_trades", "usd_roll_step", "usd_switch_sessions"):
        out[k] = float(sum(float(s.get(k) or 0.0) for s in st))
    for k in ("master_type", "source", "calendar", "roll_source"):
        out[k] = sorted({str(s.get(k) or "") for s in st})
    return out


def roll_stamp(meta, times, trades, mult, strategy_name=None, table_dir=None, day_pnl=None,
               pnl_in_usd=False, kind=None):
    """What a saved run records about contract rolls (owner ask 10-08, item 3).

    master_type / source, roll_source (table + sha), calendar used, switches in the window
    (estimated ones counted), trades crossing a true switch, $ net of those trades, $ of pure roll
    step they booked (0 on an adjusted master by construction), and $ booked on switch sessions."""
    meta = meta or {}
    root = roll_root(meta.get("instrument"))
    src = str(meta.get("source") or "")
    if root is None:
        return dict(master_type="no contract rolls", source=src, roll_source="", calendar="not used",
                    switches_in_window=0, switches_estimated=0, trades_crossing=0,
                    usd_crossing_trades=0.0, usd_roll_step=0.0, usd_switch_sessions=0.0)
    adjusted = src.startswith(("db_adj", "db_fadj"))
    otf = "otf" in src
    tf = tf_seconds_of(meta, times)
    t = epoch_seconds(times)
    m = roll_map(t, root, tf, table_dir) if len(t) else None
    n_sw = int(m["n_switches"]) if m else 0
    est = 0
    if m:
        rows = m["switch_rows"]
        est = int(sum(1 for i, r in enumerate(rows)
                      if i < len(m["in_series"]) and m["in_series"][i] and not is_trustworthy(r)))
    ei, xi, sd = trade_bounds(trades)
    cross = crossing_trades(t, root, tf, ei, xi, table_dir) if len(t) else np.zeros(0, dtype=bool)
    pnl = []
    for tr in trades or []:
        try:
            pnl.append(float(tr.get("pnl") if isinstance(tr, dict) else tr[2]))
        except (TypeError, ValueError, IndexError, AttributeError):
            pnl.append(0.0)
    # a file that reports P&L in dollars (PNL_UNITS = "usd", e.g. NQDIP) is already in dollars
    pnl = np.asarray(pnl[:len(ei)], dtype="float64") * (1.0 if pnl_in_usd else float(mult))
    step = 0.0
    if not adjusted:
        for k in np.flatnonzero(cross):
            step += stitch_usd(t, root, tf, int(ei[k]), int(xi[k]), int(sd[k]),
                               point_value(meta.get("instrument")), table_dir)
    roll_aware = (kind == "roll-aware strategy") if kind else is_roll_aware(strategy_name)
    # $ booked on switch sessions: trades whose holding window touches a session that contains or
    # first follows a switch (the sessions the old detector was meant to keep a strategy out of)
    usd_sess = 0.0
    if len(t) and len(ei) and len(pnl):
        # a session starts after any gap longer than one bar (overnight on RTH, the daily break on 24h)
        ss = np.r_[0, np.flatnonzero(np.diff(t) > tf) + 1]
        se = np.r_[ss[1:] - 1, len(t) - 1]
        flagged = np.asarray(seam_days_for(t[ss], root, t, tf, table_dir), dtype="int64")
        if len(flagged):
            fa, fb = ss[flagged], se[flagged]               # bar spans of the switch sessions, sorted
            k = np.searchsorted(fb, ei[:len(pnl)], side="left")   # first switch session ending at/after entry
            ok = k < len(fb)
            hit = np.zeros(len(pnl), dtype=bool)
            hit[ok] = fa[k[ok]] <= xi[:len(pnl)][ok]
            usd_sess = float(pnl[hit].sum())
    calendar = kind or ("adjusted master" if adjusted else
                        "roll-aware strategy" if roll_aware else "true roll table")
    return dict(master_type=(("unadjusted, signals %s-adjusted on the fly, fills raw"
                              % ("ratio" if "otf_ratio" in src else "difference")) if otf else
                             "adjusted" if adjusted else "unadjusted"), source=src,
                roll_source=("rolls_%s.csv %s" % (root, table_sha(root, table_dir))) if (otf or not adjusted)
                else ("adjusted master built from rolls_%s.csv (table now %s)" % (root, table_sha(root, table_dir))),
                calendar=calendar, switches_in_window=n_sw, switches_estimated=est,
                trades_crossing=int(cross.sum()),
                usd_crossing_trades=float(pnl[cross[:len(pnl)]].sum()) if len(pnl) else 0.0,
                # the step a trade BOOKED; a roll-aware file removes it itself, so it booked none -
                # what it held across is reported separately, per one contract
                usd_roll_step=0.0 if roll_aware else float(step),
                roll_step_removed_by_strategy_per_contract_usd=float(step) if roll_aware else 0.0,
                usd_switch_sessions=float(usd_sess))


# ── THE ROLL PLAN (v4 - MANAGER ruling #58 on TTM's review #56, 2026-10-08) ──────────────────────
#
# #58 (B): FILLS, P&L and SIZING on RAW contract prices; SIGNALS on a jump-free series, with the
# method declared per strategy - RATIO-adjust for %/ratio logic, DIFFERENCE-adjust for point logic.
# A global difference back-adjust feeding level- or %-reading logic is wrong (NQ 2010 = 3.05x).
# #58 (A): FAIL CLOSED - price arrays that do not say what market they are get refused.
#
# How a run on an unadjusted NQ / ES master gets there:
#   1. THE METHOD. The file's ROLL_SIGNAL = "difference" | "ratio" | "raw" when it declares one,
#      else found by test over the run's whole window: trades unchanged when every price is shifted
#      by +C -> difference; else unchanged when every price is scaled by k -> ratio; else neither ->
#      raw (level-dependent). A declared method is checked by the same test and REFUSED when more
#      than 1% of the file's trades move under it. The test is run once per (file content, master,
#      window) with the first parameter set it sees - a sweep pays for it once, not per trial; the
#      saved run's raw-vs-adjusted check (`raw_vs_adjusted`) is the backstop for a parameter that
#      switches level logic on.
#   2. SIGNALS. The strategy runs on the series adjusted by that method: difference = Panama back-
#      adjust from the table (the same series as the db_adj master); ratio = each switch's offset
#      turned into a ratio to the old contract's last close, anchored on the window's newest segment.
#   3. FILLS, P&L, SIZING. Every trade is re-priced to the raw contract prices it filled at, and a
#      trade held across a switch has the roll step taken out (the roll is a trade, not a profit).
#      Difference: exact, P&L unchanged, entry prices mapped back to raw. Ratio: entry and exit are
#      divided back by the bar's factor and the P&L re-derived. Sizing reads the raw arrays.
#   4. RAW (level-dependent, ROLL_SIGNAL="raw", or params roll_treatment="raw"): raw prices, the true
#      seam calendar, and any trade held across a switch is REFUSED.
#
# Kinds (the stamp's `calendar`):
#   "difference-adjusted signals" / "ratio-adjusted signals"   steps 1-3 above
#   "raw: level-dependent" / "raw (declared)" / "raw (opted out)" / "raw: untested (...)"   step 4
#   "roll-aware strategy"          file removes the offset itself (ROLL_AWARE, pinned by sha256)
#   "raw (live/paper path)"        report only - never refused, never changed (MANAGER D2)
#   "adjusted master"              db_adj_* / db_fadj_* (refused if stale for the window; a file that
#                                  reads levels is warned - its signals read shifted levels)
#   "no contract rolls"            stocks, funds; futures roots WITHOUT a table are refused
#   "declared: no contract rolls"  arrays with no instrument whose meta says roll_mode = "none"
#   "live bar builder: ..."        arrays from api/cloud_signal.closed_arrays (roll_mode = "live"):
#                                  live / paper / shadow legs, reported only (MANAGER D2)
#   "undeclared"                   no instrument, live / paper path only (research paths refuse)
NO_TABLE_FUTURES = frozenset({"CL", "MCL", "GC", "MGC", "SI", "HG", "NG", "ZN", "ZB", "ZF", "ZT",
                              "6E", "6J", "6B", "RTY", "M2K", "YM", "MYM"})
ROLL_AWARE_SHA = {          # basename -> sha256 of the file's LF content (re-pin only with the parity test)
    "NQDIP_1_2.py": "c3a2e34249a77ce8ad423b71fc11da8687695f2dcfd37ddfdf64c7ed63df242b",
    "NQDIP_1_3.py": "c6ba58a423cdc56127cbbb3fdbb7ea01579518767f8518db8f11d7c7dec8aba3",
    "NQDIP_1_4.py": "14e3b6e3a2a4c0cb068d07b8c937c03702a5953e8ccb8e1a06609558a8fd336c",
}
SIGNAL_METHODS = ("difference", "ratio", "raw")
ADJUSTED_KINDS = ("difference-adjusted signals", "ratio-adjusted signals")
_CLASS_CACHE = {}
SAMPLE_SESSIONS = None      # sessions the method test runs over, ending at the window's end; None = all
SCALE_K = 1.5               # the scale test multiplies prices by at least this
DECLARED_MATCH_MIN = 0.99   # a declared method may move at most 1% of trades under its own test
NEAR_SESSIONS = 20          # TTM's L: sessions after a switch a lookback can still carry the step


def file_sha(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()
    except (OSError, TypeError):
        return ""


def is_roll_aware(strategy_name, mod=None):
    """ROLL_AWARE by name AND by content: an edited or copied file is not trusted until its sha is
    re-pinned (and its parity-to-adjusted test re-run) - TTM review #56 point 4. With the module
    that will run, its code must also BE that file's code: every function defined in it and every
    module-level constant must match a fresh compile of the pinned file, so a module rebuilt in
    memory that only borrows the file's name and __file__ is not trusted (TTM attack 7)."""
    base = os.path.basename(str(strategy_name or ""))
    if base not in ROLL_AWARE:
        return False
    want = ROLL_AWARE_SHA.get(base)
    if not want or file_sha(strategy_name) != want:
        return False
    return mod is None or _module_is_file(mod, strategy_name)


_TRUSTED = {}


def trusted_module(path):
    """A FRESH load of a sha-pinned roll-aware file - never the caller's module object, whose module-
    level state (a roll cache, a level table) may have been edited (TTM attacks 7b / 7c). Cached per
    (file content, roll tables), so a table row added by the roll watch gets a clean load."""
    import importlib.util
    sha = file_sha(path)
    base = os.path.basename(str(path))
    if not sha or ROLL_AWARE_SHA.get(base) != sha:
        raise RollGuardError("%s is not the pinned roll-aware file any more; it cannot be trusted." % base)
    key = (sha, table_sha("NQ"), table_sha("ES"))
    mod = _TRUSTED.get(key)
    if mod is None:
        spec = importlib.util.spec_from_file_location("augur_rolls_trusted_" + sha[:12], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TRUSTED[key] = mod
    return mod


def _module_is_file(mod, path):
    import ast
    import types
    try:
        with open(path, "rb") as fh:
            src = fh.read().decode("utf-8")
        code = compile(src, getattr(mod, "__file__", None) or path, "exec")
        fresh = {c.co_name: c for c in code.co_consts if isinstance(c, types.CodeType)}
        name = getattr(mod, "__name__", None)
        fns = {k: v for k, v in vars(mod).items()
               if isinstance(getattr(v, "__code__", None), types.CodeType) and getattr(v, "__module__", None) == name}
        if "run_backtest" not in fns or set(fns) - set(fresh):
            return False
        if any(fresh[k] != v.__code__ for k, v in fns.items()):
            return False
        for node in ast.parse(src).body:                      # module-level constants as written
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for tg in node.targets:
                    if isinstance(tg, ast.Name) and vars(mod).get(tg.id, node.value.value) != node.value.value:
                        return False
        return True
    except Exception:
        return False


def _module_code_sha(mod):
    """sha256 of the code that will run: every function defined in the module (bytecode, constants)
    and its simple module-level constants - so two modules built in memory never share a cached
    method test (TTM attack 2c)."""
    import marshal
    import types
    h = hashlib.sha256()
    name = getattr(mod, "__name__", None)
    try:
        ns = vars(mod)
    except TypeError:
        return ""
    for k in sorted(ns):
        v = ns[k]
        co = getattr(v, "__code__", None)
        if isinstance(co, types.CodeType) and getattr(v, "__module__", None) == name:
            h.update(k.encode() + b"=" + marshal.dumps(co))
            h.update(("%r|%r;" % (getattr(v, "__defaults__", None), getattr(v, "__kwdefaults__", None))).encode())
        elif isinstance(v, (int, float, str, bool, type(None))) and not k.startswith("__"):
            h.update(("%s=%r;" % (k, v)).encode())
    return h.hexdigest()


def stale_after(meta, root, table_dir=None):
    """For an adjusted master: the epoch of the first table switch its build did NOT apply (a roll
    added to the table after the master was built), else None. From the master's provenance."""
    import json
    prov = (meta or {}).get("provenance")
    if isinstance(prov, str):
        try:
            prov = json.loads(prov) if prov.strip() else {}
        except ValueError:
            prov = {}
    if not isinstance(prov, dict) or "switches_applied" not in prov:
        return None
    rows = real_switches(root, table_dir)
    applied = int(prov.get("switches_applied") or 0)
    # switches inside the master's span, earliest first; the build applies them in order
    df = str((meta or {}).get("date_from") or "")[:10]
    lo = epoch_seconds([df])[0] if df else -1
    inside = [r for r in rows if r["switch_sec"] >= lo]
    if applied >= len(inside):
        return None
    return int(inside[applied]["switch_sec"])


def _extras_for(fn, arrays):
    import inspect
    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    ex = {}
    if arrays.get("volume") is not None and (has_kw or "volumes" in sp):
        ex["volumes"] = arrays["volume"]
    if arrays.get("day_id") is not None and (has_kw or "day_id" in sp):
        ex["day_id"] = arrays["day_id"]
    if arrays.get("index") is not None and "index" in sp:
        ex["index"] = arrays["index"]
    return ex


def _trade_rows(trades):
    """[(key, trade)] for readable trade rows; key = (entry_idx, exit_idx, side)."""
    out = []
    for t in trades or []:
        try:
            out.append(((int(t[0]), int(t[1]), 1 if float(t[3] if len(t) > 3 else 1) >= 0 else -1), t))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    return out


def _trade_keys(res):
    tr = (res or {}).get("trades") if isinstance(res, dict) else None
    return [k for k, _t in _trade_rows(tr)]


def _match(k0, k1):
    """Share of trades unchanged between two runs (1.0 when both are empty)."""
    a, b = set(k0), set(k1)
    if not a and not b:
        return 1.0
    return len(a & b) / float(max(len(a), len(b)))


def ratio_factors(times, closes, root, tf_seconds, table_dir=None):
    """Per-bar multiplicative back-adjust factors (open-end, close-end) anchored on the window's
    NEWEST segment: each switch inside the window becomes (old_last_close + offset) / old_last_close,
    where old_last_close is the close of the last bar that ENDS at or before the switch."""
    t = np.asarray(times, dtype="int64")
    n = len(t)
    ko, kc = np.ones(n), np.ones(n)
    inst, off, _ib = _switch_arrays(root, table_dir)
    if n == 0 or not len(inst):
        return ko, kc
    tf = int(tf_seconds)
    keep = (inst > t[0]) & (inst < t[-1] + tf)
    inst, off = inst[keep], off[keep]
    if not len(inst):
        return ko, kc
    c = np.asarray(closes, dtype="float64")
    q = np.searchsorted(t + tf, inst, side="right") - 1
    base = np.where(q >= 0, c[np.clip(q, 0, n - 1)], np.nan)
    ratio = np.where((q >= 0) & (base > 0), (base + off) / np.where(base > 0, base, 1.0), 1.0)
    logr = np.log(np.where(ratio > 0, ratio, 1.0))
    suf = np.r_[np.cumsum(logr[::-1])[::-1], 0.0]           # suf[j] = sum of log ratios j..end
    ko = np.exp(suf[np.searchsorted(inst, t, side="right")])
    kc = np.exp(suf[np.searchsorted(inst, t + tf, side="left")])
    return ko, kc


def ratio_adjust(times, opens, highs, lows, closes, root, tf_seconds, table_dir=None):
    """Ratio back-adjustment (see `ratio_factors`). Same shape as `back_adjust`: a bar a switch falls
    inside is rebuilt as a body with no wick and flagged no-fill."""
    ko, kc = ratio_factors(times, closes, root, tf_seconds, table_dir)
    o = np.asarray(opens, dtype="float64") * kc
    h = np.asarray(highs, dtype="float64") * kc
    l = np.asarray(lows, dtype="float64") * kc
    c = np.asarray(closes, dtype="float64") * kc
    mixed = ko != kc
    if mixed.any():
        o[mixed] = np.asarray(opens, dtype="float64")[mixed] * ko[mixed]
        h[mixed] = np.maximum(o[mixed], c[mixed])
        l[mixed] = np.minimum(o[mixed], c[mixed])
    return o, h, l, c, dict(ko=ko, kc=kc, no_fill=mixed.copy(), synthetic=mixed, method="ratio")


LABEL_MIN_SWITCHES = 6         # switches with a step >= 5x the gap noise needed to judge a label
LABEL_CONTRADICT = 0.70        # share of them that must contradict the label to refuse it


_REGISTRY = {}


def _registry_rows():
    """The master registry rows (augur_engine.data.list_masters), cached per process by the
    registry file's mtime. [] when this checkout has no registry."""
    try:
        from . import data as _D
        p = _D.DB_PATH
        st = os.stat(p).st_mtime if os.path.exists(p) else None
        hit = _REGISTRY.get(p)
        if hit and hit[0] == st:
            return hit[1]
        rows = _D.list_masters() if st is not None else []
        _REGISTRY[p] = (st, rows)
        return rows
    except Exception:
        return []


def registry_check(meta):
    """(row, problem). Prices loaded by load_master_arrays carry their registry id and filename; the
    registry row - not the meta strings - says what market and what kind of master they are. A claim
    that differs from the row (a no-adj file labelled db_adj, an alias, another instrument) is a
    problem; so is an id or filename the registry does not have. No id and no filename = an
    unregistered tape (row None, problem None) - TTM attacks 5 and 4f-p."""
    meta = meta or {}
    mid, fname = meta.get("id"), meta.get("filename")
    if mid in (None, "") and not fname:
        return None, None
    rows = _registry_rows()
    if not rows:
        return None, None
    by_id = [r for r in rows if mid not in (None, "") and str(r.get("id")) == str(mid)]
    by_fn = [r for r in rows if fname and str(r.get("filename")) == str(fname)]
    row = (by_id or by_fn or [None])[0]
    if row is None:
        return None, ("these prices name registry master id %r / file %r, which the registry does not "
                      "have" % (mid, fname))
    if by_id and by_fn and by_id[0] is not by_fn[0] and str(by_id[0].get("id")) != str(by_fn[0].get("id")):
        return row, ("these prices name registry id %r but file %r, which belong to different masters"
                     % (mid, fname))
    claim_src = str(meta.get("source") or "")
    claim_inst = normalize_instrument(meta.get("instrument"))
    if claim_src != str(row.get("source") or "") or claim_inst != normalize_instrument(row.get("instrument")):
        return row, ("these prices say source %r, instrument %r, but they come from registry master id %s "
                     "(%s): source %r, instrument %r. Load the master you mean with load_master_arrays."
                     % (claim_src, meta.get("instrument"), row.get("id"), row.get("filename"),
                        row.get("source"), row.get("instrument")))
    return row, None


def label_check(times, opens, closes, root, tf_seconds, table_dir=None):
    """Do the prices carry the roll steps? At every real switch in the window that falls between
    two bars, the gap from the last close before it to the first open after it is compared with the
    switch's offset: an unadjusted series jumps by about the offset, an adjusted one does not. Only
    switches whose offset is at least 5x the ordinary gap noise vote. Returns dict(eligible,
    raw_like, adjusted_like). On the house masters, full history: no-adj 86-97% raw-like, adj 67-97%
    adjusted-like (the rest are real weekend / overnight moves) - TTM attack 5."""
    t = np.asarray(times, dtype="int64")
    o = np.asarray(opens, dtype="float64")
    c = np.asarray(closes, dtype="float64")
    out = dict(eligible=0, raw_like=0, adjusted_like=0)
    if len(t) < 3:
        return out
    tf = int(tf_seconds)
    d = np.abs(o[1:] - c[:-1])
    bar_noise = float(np.median(d[d > 0])) if (d > 0).any() else 0.0
    starts = np.flatnonzero(np.diff(t) > tf) + 1
    gap_noise = float(np.median(np.abs(o[starts] - c[starts - 1]))) if len(starts) else bar_noise
    for r in real_switches(root, table_dir):
        if r.get("kind") == "in_bar":
            continue
        s, off = int(r["switch_sec"]), float(r["offset_pts"])
        if s <= t[0] or s >= t[-1]:
            continue
        b = int(np.searchsorted(t, s, side="left"))
        if b <= 0 or b >= len(t) or t[b - 1] + tf > s:
            continue
        noise = gap_noise if (t[b] - t[b - 1]) > tf else bar_noise
        if abs(off) < 5.0 * max(noise, 1e-9):
            continue
        gap = o[b] - c[b - 1]
        out["eligible"] += 1
        if abs(gap - off) < abs(gap):
            out["raw_like"] += 1
        else:
            out["adjusted_like"] += 1
    return out


def declared_method(mod):
    m = str(getattr(mod, "ROLL_SIGNAL", "") or "").strip().lower()
    return m if m in SIGNAL_METHODS else None


def invariance(mod, arrays, root, times, tf, params=None, strategy_name=None, want_scale=False):
    """THE TESTS. Over the window (or its last SAMPLE_SESSIONS sessions): the share of the file's
    trades unchanged when every price is (shift) moved by +C - C a whole number of points, the
    largest back-adjust shift in the window and at least 500 - and (scale) multiplied by k - at least
    SCALE_K and at least the largest ratio factor in the window. The scale test runs only when the
    shift test fails or `want_scale`. Cached per (file sha, instrument, source, timeframe, window)
    with the first parameter set seen. Any failure scores both 0.0 - toward the guard."""
    meta = arrays.get("meta") or {}
    t_ = np.asarray(times, dtype="int64")
    key = (file_sha(strategy_name), _module_code_sha(mod), str(meta.get("instrument")), str(meta.get("source")),
           str(meta.get("timeframe")), tf, int(t_[0]) if len(t_) else 0, int(t_[-1]) if len(t_) else 0,
           len(t_))
    hit = _CLASS_CACHE.get(key)
    if hit is not None and (hit.get("scale") is not None or not want_scale):
        return hit
    out = dict(shift=0.0, scale=0.0, trades=0)
    try:
        n = len(arrays["close"])
        did = arrays.get("day_id")
        a = 0
        if SAMPLE_SESSIONS and did is not None and n:
            d = np.asarray(did)
            first = int(d[-1]) - int(SAMPLE_SESSIONS)
            a = int(np.searchsorted(d, first, side="left")) if first > int(d[0]) else 0
        m = roll_map(times, root, tf)
        so = np.abs(m["shift_open"]) if len(m["shift_open"]) else np.zeros(1)
        C = float(np.ceil(max(500.0, float(np.max(so)))))
        _ko, kc = ratio_factors(times, arrays["close"], root, tf)
        k = max(SCALE_K, float(np.max(kc)) if len(kc) else 1.0,
                (1.0 / float(np.min(kc))) if len(kc) and np.min(kc) > 0 else 1.0)
        sl = {kk: (v[a:] if hasattr(v, "__len__") and not isinstance(v, (dict, str)) and len(v) == n else v)
              for kk, v in arrays.items()}
        fn = mod.run_backtest
        ex = _extras_for(fn, sl)
        p = dict(params or {})
        p.pop("roll_treatment", None)
        O, H, L, Cl = (np.asarray(sl[kk], dtype="float64") for kk in ("open", "high", "low", "close"))
        with roll_context(root, times[a:], tf, strategy=strategy_name):
            k0 = _trade_keys(fn(O, H, L, Cl, return_trades=True, **ex, **p))
            k1 = _trade_keys(fn(O + C, H + C, L + C, Cl + C, return_trades=True, **ex, **p))
            out["shift"] = _match(k0, k1)
            if out["shift"] < 1.0 or want_scale:
                k2 = _trade_keys(fn(O * k, H * k, L * k, Cl * k, return_trades=True, **ex, **p))
                out["scale"] = _match(k0, k2)
            else:
                out["scale"] = None
        out["trades"] = len(k0)
    except Exception:
        out = dict(shift=0.0, scale=0.0, trades=0)
    _CLASS_CACHE[key] = out
    return out


def level_dependent(mod, arrays, root, times, tf, params=None, strategy_name=None):
    """True when a constant shift moves any of the file's trades (the v3 question, kept for callers)."""
    return invariance(mod, arrays, root, times, tf, params, strategy_name)["shift"] < 1.0


def _pct(x):
    return "%.0f%%" % (100.0 * (1.0 - float(x or 0.0)))


def plan_for(mod, arrays, strategy_name=None, params=None):
    """Decide what this run gets (see the kinds above). Raises RollGuardError - on research paths
    only - for arrays that do not say what market they are, a futures root with no roll table, a
    stale adjusted master, and a declared signal method its own test contradicts."""
    meta = (arrays or {}).get("meta") or {}
    if meta.get("roll_plan"):
        stored = meta["roll_plan"]
        if stored.get("adjust"):                           # adjusted already: never adjust twice -
            return _checked_stored_plan(arrays, stored)    # but only a plan that fits these arrays
        meta = {k: v for k, v in meta.items() if k != "roll_plan"}   # anything else: plan afresh
        arrays = dict(arrays, meta=meta)
    idx = (arrays or {}).get("index")
    times = epoch_seconds(idx) if idx is not None else np.zeros(0, dtype="int64")
    tf = tf_seconds_of(meta, times)
    # LIVE callers (api / tools live modules, by real path) keep raw prices and are never refused.
    # guard_mode("report") from anywhere else only WAIVES the refusals (they become warnings and
    # the stamp says so) - the signals and fills are planned as usual (TTM attack 8).
    report_only = _report_only_caller()
    waived = current_guard_mode() == "report"
    raw_inst = meta.get("instrument")
    inst = normalize_instrument(raw_inst)
    src = str(meta.get("source") or "")
    plan = dict(kind="undeclared", method=None, method_source=None, ctx_root=None, adjust=False,
                refuse_crossings=False, root=None, times=times, tf=tf, warn=None, tests=None)
    reg_row, reg_problem = (None, None) if report_only else registry_check(meta)
    if reg_problem:
        if not waived:
            raise RollGuardError(reg_problem)
        plan["warn"] = reg_problem
    plan["registry"] = ("master id %s (%s)" % (reg_row.get("id"), reg_row.get("filename")) if reg_row else
                        "not checked (live / paper path)" if report_only else
                        "unregistered tape" if meta.get("id") in (None, "") and not meta.get("filename") else
                        "registry not available here")
    base = os.path.basename(str(strategy_name or "")) or "this strategy"
    if not inst:
        rmode = str(meta.get("roll_mode") or "").strip().lower()
        if rmode == "none":
            plan["kind"] = "declared: no contract rolls"
            return plan
        if rmode == "live":
            # built by the live bar builder (api/cloud_signal.closed_arrays) for a live / paper /
            # shadow leg: reported, never refused or changed - the same rule as a live caller (D2)
            plan["kind"] = "live bar builder: not roll-checked"
            return plan
        if report_only or waived:
            plan["warn"] = ("arrays carry no instrument in meta, so this run was not roll-checked; "
                            "load them with load_master_arrays (or set meta['instrument'/'source'])")
            plan["report_mode"] = waived and not report_only
            return plan
        raise RollGuardError(
            "these price arrays do not say which market they are (no instrument in their meta), so "
            "the run cannot be checked for contract rolls. Load them with load_master_arrays, or set "
            "meta['instrument'] and meta['source'] (for example 'NQ' and 'db_noadj_rth'); a synthetic "
            "or stock tape sets meta['roll_mode'] = 'none'.")
    root = roll_root(inst)
    if root is None:
        unknown_on_futures_source = src.startswith(FUTURES_SOURCE_PREFIXES) and inst not in ("", )
        if (inst in NO_TABLE_FUTURES or futures_like(raw_inst) or unknown_on_futures_source) and not report_only:
            msg = ("%s is a futures market with no roll table (tools/data/rolls_%s.csv), so a run on it "
                   "cannot be checked for contract switches. Build the table with tools/build_roll_table.py "
                   "or run on an adjusted master." % (raw_inst, inst))
            if not waived:
                raise RollGuardError(msg)
            plan.update(warn=msg, report_mode=True)
        plan["kind"] = "no contract rolls"
        return plan
    plan["root"] = root
    plan["report_mode"] = waived and not report_only
    if not report_only and len(times):
        lc = label_check(times, arrays["open"], arrays["close"], root, tf)
        plan["label_check"] = lc
        adjusted_label = src.startswith(("db_adj", "db_fadj"))
        against = lc["raw_like"] if adjusted_label else lc["adjusted_like"]
        lc["verdict"] = ("not verifiable here (%d switch(es) with a step clear of the gap noise; %d needed)"
                         % (lc["eligible"], LABEL_MIN_SWITCHES) if lc["eligible"] < LABEL_MIN_SWITCHES else
                         "contradicts the label" if against >= LABEL_CONTRADICT * lc["eligible"] else
                         "agrees with the label")
        if lc["eligible"] >= LABEL_MIN_SWITCHES and against >= LABEL_CONTRADICT * lc["eligible"]:
            msg = ("these prices are labelled %s (source %r) but at %d of %d contract switches in the "
                   "window they %s the roll step, so the label is wrong. Load the master the label names."
                   % ("adjusted" if adjusted_label else "unadjusted", src, against, lc["eligible"],
                      "carry" if adjusted_label else "do not carry"))
            if not waived:
                raise RollGuardError(msg)
            plan["warn"] = msg
    if src.startswith(("db_adj", "db_fadj")):
        plan.update(kind="adjusted master", method="difference", method_source="master")
        st = stale_after(meta, root)
        if st is not None and len(times) and times[-1] >= st and not report_only:
            msg = ("the adjusted master %s was built before the %s contract switch of %s, so its bars "
                   "after that switch are NOT adjusted. Rebuild the adjusted masters "
                   "(tools/build_adjusted_masters.py) or end the run before that date."
                   % (meta.get("name") or src, root,
                      str(np.datetime64(int(st), "s"))[:16].replace("T", " ") + " UTC"))
            if not waived:
                raise RollGuardError(msg)
            plan["warn"] = msg
        if not report_only and not is_roll_aware(strategy_name, mod) and declared_method(mod) != "difference":
            inv = invariance(mod, arrays, root, times, tf, params, strategy_name)
            plan["tests"] = inv
            if inv["shift"] < 1.0:
                plan["warn"] = ("this file's trades move when every price shifts by a constant (it reads "
                                "levels or %%: %s of them moved), and this master is difference-adjusted, "
                                "so its signals read shifted levels. Run it on the unadjusted master: the "
                                "engine then picks its signal method and prices fills raw." % _pct(inv["shift"]))
        return plan
    plan["ctx_root"] = root
    treatment = str((params or {}).get("roll_treatment") or "").lower()
    if is_roll_aware(strategy_name, mod):
        plan["kind"] = "roll-aware strategy"
        plan["trusted_path"] = os.path.abspath(str(strategy_name))
        return plan
    if report_only:
        plan["kind"] = "raw (live/paper path)"
        return plan
    if treatment == "raw":
        plan.update(kind="raw (opted out)", method="raw", method_source="params", refuse_crossings=True,
                    warn="roll_treatment=raw: signals read raw prices across contract switches")
        return plan
    decl = declared_method(mod)
    if decl == "raw":
        plan.update(kind="raw (declared)", method="raw", method_source="declared", refuse_crossings=True,
                    warn="ROLL_SIGNAL = 'raw': signals read raw prices; a trade across a switch is refused")
        return plan
    inv = invariance(mod, arrays, root, times, tf, params, strategy_name, want_scale=(decl == "ratio"))
    plan["tests"] = inv
    usd = str(getattr(mod, "PNL_UNITS", "") or "").lower() == "usd"
    if decl in ("difference", "ratio"):
        score = inv["shift"] if decl == "difference" else inv["scale"]
        if (score is None or score < DECLARED_MATCH_MIN) and waived:
            plan.update(kind="raw (declared method failed its test; report mode)", method="raw",
                        method_source="declared", refuse_crossings=True,
                        warn="the declared ROLL_SIGNAL failed its own test")
            return plan
        if score is None or score < DECLARED_MATCH_MIN:
            raise RollGuardError(
                "%s declares ROLL_SIGNAL = %r, but %s of its trades move when every price is %s, so "
                "%s-adjusted signals would change its logic. Declare the method that fits the file "
                "('difference' for point logic, 'ratio' for %% logic, 'raw' for raw prices with the "
                "crossing refusal), or make the file roll-aware."
                % (base, decl, _pct(score), "shifted by a constant" if decl == "difference"
                   else "scaled by a constant", decl))
        method, msrc = decl, "declared"
    elif inv["trades"] == 0:
        plan.update(kind="raw: untested (no trades in the test sample)", method="raw", method_source="test",
                    refuse_crossings=True,
                    warn="the signal-method test saw no trades, so the file runs on raw prices; "
                         "declare ROLL_SIGNAL to choose")
        return plan
    elif inv["shift"] >= 1.0:
        method, msrc = "difference", "test"
    elif inv["scale"] is not None and inv["scale"] >= 1.0:
        method, msrc = "ratio", "test"
    else:
        plan.update(kind="raw: level-dependent", method="raw", method_source="test", refuse_crossings=True,
                    warn="this file's trades move under both a constant shift (%s) and a constant scale "
                         "(%s), so it runs on raw prices; its indicators still read the roll step near "
                         "switches - declare ROLL_SIGNAL, or a roll-aware version of the file is the "
                         "exact fix" % (_pct(inv["shift"]), _pct(inv["scale"])))
        return plan
    if method == "ratio" and usd:
        plan.update(kind="raw: ratio file reports dollars", method="raw", method_source=msrc,
                    refuse_crossings=True,
                    warn="a ratio-logic file that reports P&L in dollars cannot have its fills re-priced, "
                         "so it runs on raw prices")
        return plan
    plan.update(kind="%s-adjusted signals" % method, method=method, method_source=msrc,
                ctx_root=None, adjust=True)
    return plan


def _replan_cut(arrays, stored):
    """The stored plan of already-planned arrays - or, when those arrays were cut afterwards (a
    slice, a boolean mask, an in-sample / out-of-sample split that kept the meta), the same plan
    restricted to the bars that are left, found by their timestamps."""
    st_t = stored.get("times")
    n = len((arrays or {}).get("close", []))
    if st_t is not None and len(st_t) == n:
        return stored
    idx = (arrays or {}).get("index")
    if idx is None or st_t is None:
        raise RollGuardError("these prices were roll-planned and then cut without their bar times, so "
                             "their fills cannot be put back on raw contract prices - cut the arrays "
                             "before running them, or keep 'index'.")
    tt = epoch_seconds(idx)
    pos = np.searchsorted(st_t, tt)
    ok = len(tt) == 0 or (int(pos.max()) < len(st_t) and np.array_equal(np.asarray(st_t)[pos], tt))
    if not ok:
        raise RollGuardError("these prices were roll-planned on another bar grid; load them again "
                             "(load_master_arrays) and run them from there.")
    sub = dict(stored, times=tt)
    for k in ("sc", "kc"):
        if stored.get(k) is not None:
            sub[k] = np.asarray(stored[k])[pos]
    if stored.get("adjust"):
        sub["close_ref"] = arrays["close"]
    return sub


def _checked_stored_plan(arrays, stored):
    """An adjusted plan found on incoming arrays is used only if it fits them: the root is the
    instrument's, the prices say they were adjusted on the fly, and the per-bar factors are the
    table's for these bars. Anything else is refused - a forged or transplanted plan (TTM 6b)."""
    meta = (arrays or {}).get("meta") or {}
    plan = _replan_cut(arrays, stored)
    root = roll_root(meta.get("instrument"))
    src = str(meta.get("source") or "")
    ok = root is not None and plan.get("root") == root and src.startswith("db_adj_otf") and \
        plan.get("method") in ("difference", "ratio") and plan.get("tf") is not None
    try:
        if ok and plan["method"] == "difference":
            m = roll_map(plan["times"], root, plan["tf"])
            ok = plan.get("sc") is not None and np.allclose(np.asarray(plan["sc"]), m["shift_close"], atol=1e-9)
        elif ok:
            kc = np.asarray(plan.get("kc"), dtype="float64")
            raw_c = np.asarray(arrays["close"], dtype="float64") / kc
            _ko, kc2 = ratio_factors(plan["times"], raw_c, root, plan["tf"])
            ok = len(kc) == len(raw_c) and np.allclose(kc, kc2, rtol=1e-9, atol=1e-12)
    except Exception:
        ok = False
    if not ok:
        raise RollGuardError("these arrays carry a roll plan that does not fit them, so it cannot be "
                             "trusted. Load the prices again (load_master_arrays) and run them from there.")
    return plan


def raw_view(arrays):
    """The RAW contract prices behind `arrays`: the arrays themselves unless their signals were
    adjusted by a roll plan, in which case O / H / L / C are put back (a bar a switch fell inside
    keeps its rebuilt body). Sizing and the raw-vs-adjusted check read these."""
    plan = ((arrays or {}).get("meta") or {}).get("roll_plan")
    if not plan or not plan.get("adjust"):
        return arrays
    plan = _replan_cut(arrays, plan)
    out = dict(arrays)
    if plan.get("method") == "ratio" and plan.get("kc") is not None:
        for k in ("open", "high", "low", "close"):
            out[k] = np.asarray(arrays[k], dtype="float64") / plan["kc"]
    elif plan.get("sc") is not None:
        for k in ("open", "high", "low", "close"):
            out[k] = np.asarray(arrays[k], dtype="float64") - plan["sc"]
    meta = dict(arrays.get("meta") or {})
    meta.pop("roll_plan", None)
    meta["source"] = plan.get("raw_source", meta.get("source"))
    out["meta"] = meta
    return out


def apply_plan(arrays, plan):
    """The arrays the strategy actually sees: adjusted by the plan's method when it says so. The
    returned meta carries the plan (with the per-bar factors the re-pricing needs), so planning the
    same arrays again is a no-op - never adjusted twice."""
    if plan.get("kind") in ("undeclared", "no contract rolls", "declared: no contract rolls",
                            "live bar builder: not roll-checked"):
        return arrays
    meta = dict((arrays or {}).get("meta") or {})
    out = dict(arrays)
    if plan.get("adjust") and "close_ref" not in plan:
        t, root, tf = plan["times"], plan["root"], plan["tf"]
        src = str(meta.get("source") or "")
        if plan["method"] == "ratio":
            o, h, l, c, info = ratio_adjust(t, arrays["open"], arrays["high"], arrays["low"],
                                            arrays["close"], root, tf)
            plan["kc"] = info["kc"]
            meta["source"] = "db_adj_otf_ratio:" + src
        else:
            o, h, l, c, info = back_adjust(t, arrays["open"], arrays["high"], arrays["low"],
                                           arrays["close"], root, tf)
            plan["sc"] = np.asarray(info["shift_close"], dtype="float64")
            meta["source"] = "db_adj_otf:" + src
        out.update(open=o, high=h, low=l, close=c)
        plan["no_fill_bars"] = int(np.asarray(info["no_fill"]).sum())
        plan["close_ref"] = c
        plan["raw_source"] = src
    meta["roll_plan"] = plan
    out["meta"] = meta
    return out


def _reaggregate(m):
    """Headline metrics re-derived from a re-priced trade list (engine._apply_costs math, cost 0)."""
    pnls = [float(t[2]) for t in m.get("trades") or [] if isinstance(t, (list, tuple)) and len(t) >= 3]
    n = len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    total = float(sum(pnls))
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    cum = peak = mdd = 0.0
    for x in pnls:
        cum += x
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    out = dict(m)
    out.update({"total_pnl": total, "num_trades": n, "win_rate": (100.0 * wins / n) if n else 0.0,
                "profit_factor": pf, "max_drawdown": float(mdd), "avg_pnl": (total / n) if n else 0.0,
                "wins": wins, "losses": losses})
    return out


def reprice_result(res, plan, offset=0):
    """#58: FILLS and P&L on RAW contract prices. `res` came from a strategy that ran on the plan's
    adjusted series (bar indices relative to `offset`). Difference: entry prices mapped back to raw;
    P&L is already the raw contract P&L with the roll step out, exactly. Ratio: entry and exit
    divided back by their bar's factor, the roll step of a trade held across a switch taken out, and
    the headline metrics re-derived. Trade rows that cannot be read are left as they are."""
    if not plan or not plan.get("adjust") or not isinstance(res, dict) or not res.get("trades"):
        return res
    method = plan.get("method")
    t = np.asarray(plan["times"], dtype="int64")
    n = len(t)
    if not n:
        return res
    tf = int(plan["tf"])
    inst, off, _ib = _switch_arrays(plan["root"])
    cum = np.r_[0.0, np.cumsum(off)] if len(inst) else np.zeros(1)
    sc, kc = plan.get("sc"), plan.get("kc")
    out = []
    for x in res["trades"]:
        if not isinstance(x, (list, tuple)) or len(x) < 4:
            out.append(x)
            continue
        try:
            nt = list(x)
            ei = min(max(int(x[0]) + int(offset), 0), n - 1)
            xi = min(max(int(x[1]) + int(offset), 0), n - 1)
            if method == "difference":
                if len(nt) >= 5 and sc is not None:
                    nt[4] = float(nt[4]) - float(sc[ei])
            elif method == "ratio" and kc is not None:
                d, p = float(x[3]), float(x[2])
                step = 0.0
                if xi >= ei and len(inst):
                    j0 = int(np.searchsorted(inst, t[ei], side="right"))
                    j1 = int(np.searchsorted(inst, t[xi] + tf, side="left"))
                    step = float(cum[j1] - cum[j0]) if j1 > j0 else 0.0
                if len(nt) >= 5 and d != 0:
                    e = float(nt[4])
                    re, rx = e / kc[ei], (e + p / d) / kc[xi]
                    nt[2] = d * (rx - re - step)
                    nt[4] = re
                else:
                    nt[2] = p / kc[ei] - (1.0 if d >= 0 else -1.0) * step
            out.append(tuple(nt) if isinstance(x, tuple) else nt)
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            out.append(x)
    res = dict(res)
    res["trades"] = out
    if method == "ratio":
        res = _reaggregate(res)
    return res


def _slice_offset(arr, ref):
    """Where `arr` (a close array handed to the strategy) starts inside the planned close `ref`:
    0 for the full series, the view offset for a slice of it, None when it is neither."""
    if ref is None or arr is None:
        return None
    if arr is ref:
        return 0
    try:
        a = arr if isinstance(arr, np.ndarray) else np.asarray(arr)
        if a.ndim == 1 and ref.ndim == 1 and np.shares_memory(a, ref) and a.strides == ref.strides:
            d = a.__array_interface__["data"][0] - ref.__array_interface__["data"][0]
            if d % ref.itemsize == 0 and 0 <= d // ref.itemsize <= len(ref) - len(a):
                return int(d // ref.itemsize)
        if len(a) == len(ref):
            return 0
    except Exception:
        pass
    return None


def raw_vs_adjusted(fn, raw_arrays, adj_trades, plan, extras, params, strategy_name=None, mult=1.0,
                    pnl_in_usd=False, near_sessions=NEAR_SESSIONS, adj_arrays=None):
    """TTM's check (#58): the same file on RAW prices with the true seam calendar, trade by trade
    against the planned run. Two causes are told apart. (1) The file's own roll-day skip: on raw
    prices it skips the sessions after a switch, on adjusted prices there is no step to skip - when
    the file asked for seams, it is re-run on the adjusted prices WITH seams and the difference that
    goes away is put down to the skip. (2) Price: what is left, near switches (entry or exit within
    `near_sessions` sessions after one, or held across one) = signals that read the roll step,
    removed by the plan; away from switches = level reading, or a knock-on of an earlier difference
    in a file that carries state from trade to trade."""
    t = np.asarray(plan["times"], dtype="int64")
    root, tf = plan["root"], int(plan["tf"])
    with roll_context(root, t, tf, strategy=strategy_name) as ctx:
        r = fn(raw_arrays["open"], raw_arrays["high"], raw_arrays["low"], raw_arrays["close"],
               return_trades=True, **extras, **params)
        uses_seams = ctx.get("calls", 0) > 0
    raw_rows = dict(_trade_rows((r or {}).get("trades") if isinstance(r, dict) else None))
    adj_rows = dict(_trade_rows(adj_trades))
    seam_rows = adj_rows
    if uses_seams and adj_arrays is not None:
        with roll_context(root, t, tf, strategy=strategy_name):
            r1 = fn(adj_arrays["open"], adj_arrays["high"], adj_arrays["low"], adj_arrays["close"],
                    return_trades=True, **extras, **params)
        seam_rows = dict(_trade_rows((r1 or {}).get("trades") if isinstance(r1, dict) else None))
    same = set(raw_rows) & set(adj_rows)
    only_raw = sorted(set(raw_rows) - same)
    only_adj = sorted(set(adj_rows) - same)
    skip_diff = len(set(adj_rows) ^ set(seam_rows))           # moved by the roll-day skip alone
    p_same = set(raw_rows) & set(seam_rows)
    p_keys = sorted((set(raw_rows) - p_same) | (set(seam_rows) - p_same))
    near = np.zeros(len(t), dtype=bool)
    if len(t):
        ss = np.r_[0, np.flatnonzero(np.diff(t) > tf) + 1]
        se = np.r_[ss[1:], len(t)]
        for f in seam_days_for(t[ss], root, t, tf):
            near[ss[f]:se[min(f + near_sessions, len(ss)) - 1]] = True
    if p_keys:
        ei = np.asarray([k[0] for k in p_keys], dtype="int64")
        xi = np.asarray([k[1] for k in p_keys], dtype="int64")
        cross = crossing_trades(t, root, tf, ei, xi)
        is_near = cross | near[np.clip(ei, 0, len(t) - 1)] | near[np.clip(xi, 0, len(t) - 1)]
    else:
        is_near = np.zeros(0, dtype=bool)
    usd = 1.0 if pnl_in_usd else float(mult)

    def _usd(rows, ks):
        tot = 0.0
        for k in ks:
            try:
                tot += float(rows[k][2])
            except (TypeError, ValueError, IndexError):
                pass
        return tot * usd
    n_near = int(is_near.sum())
    n_else = int(len(p_keys) - n_near)
    if not only_raw and not only_adj:
        verdict = "identical"
    elif not p_keys:
        verdict = "differs only through the file's own roll-day skip (no step to skip on adjusted prices)"
    elif not n_else:
        verdict = "differs near switches (signals that read the roll step - removed by the plan)"
    else:
        verdict = ("differs away from switches too (level reading, or a knock-on of an earlier "
                   "difference in a file that carries state)")
    return dict(trades_raw=len(raw_rows), trades_adjusted=len(adj_rows), same=len(same),
                only_raw=len(only_raw), only_adjusted=len(only_adj), file_skips_roll_days=bool(uses_seams),
                moved_by_roll_day_skip=int(skip_diff), moved_by_price=int(len(p_keys)),
                price_moves_near_switch=n_near, price_moves_elsewhere=n_else, near_sessions=int(near_sessions),
                usd_only_raw=_usd(raw_rows, only_raw), usd_only_adjusted=_usd(adj_rows, only_adj),
                verdict=verdict)


def warn_once(plan, strategy_name):
    """One stderr line per (file, kind) per process for a plan that carries a warning."""
    w = (plan or {}).get("warn")
    if not w:
        return
    key = (os.path.basename(str(strategy_name or "")), plan.get("kind"))
    if key in _WARNED:
        return
    _WARNED.add(key)
    import sys
    print("ROLL GUARD (%s) %s: %s" % (plan.get("kind"), key[0], w), file=sys.stderr)


def assert_no_crossings(entry_times, exit_times, instrument, source, label="this harness"):
    """For research code that simulates positions itself (tools/*_stageA.py) instead of calling the
    engine: raise RollGuardError if any position on an UNADJUSTED NQ / ES tape was open across a
    contract switch. Times are bar timestamps (entry bar start, exit bar END is safest)."""
    root = unadjusted_futures_root(dict(instrument=instrument, source=source))
    if root is None:
        return 0
    inst, _off, _ib = _switch_arrays(root)
    a = epoch_seconds(entry_times)
    b = epoch_seconds(exit_times)
    if not len(a) or not len(inst):
        return 0
    n_in = np.searchsorted(inst, b, side="left") - np.searchsorted(inst, a, side="right")
    n = int((n_in > 0).sum())
    if n:
        raise RollGuardError("%s held %d position(s) across a %s contract switch on the unadjusted "
                             "master %s - use the adjusted master (db_adj_*)." % (label, n, root, source))
    return 0
