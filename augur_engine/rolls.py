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
