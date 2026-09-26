"""REFUSE TO WRITE A CONTRACT ROLL INTO THE MIDDLE OF A BAR.

WHY THIS EXISTS (2026-09-26). Our NQ/ES non-adjusted masters stop being Databento on
2026-06-05 and are Yahoo NQ=F / ES=F from there on. Yahoo's continuous front-month
series switches contract WHENEVER IT LIKES, including mid-session, and it does not mark
the switch. Twice now the switch landed INSIDE one bar, so a single bar opens on the
expiring contract and closes on the next one:

    2026-06-15 03:30 ET  NQ 1m/5m 24h   open 30,252.00 -> close 30,545.75   (carry ~ +293)
    2026-06-15 05:30 ET  ES 1m/5m 24h   open  7,521.50 -> close  7,586.50   (carry ~ +64)
    2026-09-14 11:30 ET  every Yahoo-fed NQ/ES master, 1m and 5m, RTH and 24h
                         NQ open 29,077.00 -> close 29,381.50               (carry ~ +295)
                         ES open  7,612.00 -> close  7,691.50               (carry ~ +68)

A bar like that is not a price. It is two contracts glued together, and nothing
downstream can tell: it books fake profit for anything holding through it, it triggers
fake stops and trailing exits, and every indicator that reads the bar's range is wrong
for as long as its lookback holds it. ROLL_AUDIT.md measures the damage (section 2.7).
The next quarterly roll is December 2026, expiry Friday 2026-12-18, and without this
guard the same thing happens again on a Monday inside expiry week.

WHAT THE GUARD DOES. It is a REFUSAL, not a repair. When a refresh is about to append
a bar that looks like an in-bar contract switch, the append STOPS at the last clean bar
and says so loudly. Nothing is fabricated, nothing already stored is touched, and no
bar is lost - the bars after the suspect one are still there next time, once a human
has looked at it and either confirmed the roll or cleared the false alarm.

HOW A SUSPECT BAR IS RECOGNISED. Three things have to hold at once:
  1. The bar's ET date falls in the ten days before a quarterly expiry (the third
     Friday of March, June, September or December). All 128 contract switches in the
     raw Databento history came 4-8 days before expiry, and both 2026 splices did too.
     Outside that window this guard is silent, so ordinary news bars are never touched.
  2. The bar's body (close minus open) is at least half of the expected carry between
     the two contracts. The carry has run about 0.9% of price per quarter (NQ +0.97%
     June and +1.02% September; ES +0.85% and +0.89%), so the test is scaled to price
     rather than a fixed number of points.
  3. The body is at least ten standard deviations of the recent bars' own bodies, so
     the same rule works on a 1m bar and a 30m bar without tuning.

WHAT IT DELIBERATELY DOES NOT DO.
  - It does not try to tell a contract roll from a big news bar. A CPI print inside
    expiry week can trip it. That is the cheap side of the trade: a false alarm costs
    a paused append and one look by a human, while a missed splice quietly poisons
    every backtest that reads the tail. Volume is reported alongside each hit because
    it settles most cases at a glance - the 2026-06-15 NQ splice bar carried volume
    13,914 against an hourly median of 76.
  - It does not use "the other root did not move" as a test. The two roots often roll
    in the same window, and in June 2026 they rolled two hours apart, so that signal
    is not dependable. The other root's body is reported as evidence, never gated on.
  - It does not catch a roll that happens cleanly between two bars. That is a normal
    non-adjusted gap and is correct for this series; ROLL_AUDIT.md section 6 covers
    the separate question of back-adjusting.

This module is pure arithmetic on arrays - no files, no network, no database - so the
refresh paths and the tests can both use it.
"""
import datetime as _dt

import numpy as np

# Quarterly futures cycle for the equity index roots: March, June, September, December.
QUARTER_MONTHS = (3, 6, 9, 12)

# How far ahead of expiry a switch can happen. Every raw switch we have ground truth
# for came 4-8 days before the third Friday; ten days is that with room to spare.
WINDOW_DAYS_BEFORE = 10

# Expected carry between consecutive quarterly contracts, as a fraction of price.
# Measured: NQ +0.967% (June 2026) and +1.02% (September 2026); ES +0.826% and +0.89%.
# 0.9% sits in the middle of both roots' range; the test uses HALF of it, so the guard
# still fires on a roll whose carry is only half what we expect.
CARRY_FRAC = 0.009
BODY_FRAC_OF_CARRY = 0.5

# WHICH WAY A ROLL MOVES THE PRICE. While financing costs more than the index pays in
# dividends, the next quarterly contract trades ABOVE the expiring one, so switching to
# it steps the price UP. All four in-bar splices we have seen stepped up (NQ +311 and ES
# +63 in June 2026, NQ +377.50 and ES +79.50 in September). Requiring that direction
# roughly halves the false alarms on sixteen years of real masters, because the bars that
# otherwise trip the test are FOMC 14:00 and CPI 08:30 prints inside expiry week, which
# go either way. If short rates ever fall back below the dividend yield the deferred
# contract trades BELOW the front one and this constant has to flip to -1; the historical
# masters from the near-zero-rate years do contain such quarters, which is why this is a
# named constant and not an inline `> 0`.
CARRY_SIGN = 1

# The body also has to be an extreme move for THIS bar size, measured against the
# recent bars' own bodies. Ten sigma is far outside anything normal price action does.
# Ten is not a round number picked for looks: on the real masters the 2026-06-15 03:30
# NQ splice clears its own ten-sigma floor by only 1.08x, because the two volatile
# sessions before it inflate the spread. Raising this would MISS that splice.
SD_MULT = 10.0
SD_LOOKBACK = 200
SD_MIN_BARS = 30       # below this there is no usable spread; the carry test alone decides
SD_FLOOR_FRAC = 1e-5   # keeps a dead-flat overnight stretch from making SD zero


def third_friday(year, month):
    """The date of the third Friday of a month - the expiry of a quarterly contract."""
    d = _dt.date(int(year), int(month), 1)
    # weekday(): Monday 0 ... Friday 4. Step to the first Friday, then add two weeks.
    first_friday = 1 + ((4 - d.weekday()) % 7)
    return _dt.date(int(year), int(month), first_friday + 14)


def quarterly_expiries(year):
    """Every quarterly expiry in a calendar year, in order."""
    return [third_friday(year, m) for m in QUARTER_MONTHS]


def roll_window_for(day):
    """The (start, expiry) roll window a date falls in, or None if it falls outside.

    The window is the ten days before expiry, up to and including the day before it.
    Expiry day itself is excluded: by then the switch has already happened.
    """
    for y in (day.year - 1, day.year, day.year + 1):
        for exp in quarterly_expiries(y):
            if exp - _dt.timedelta(days=WINDOW_DAYS_BEFORE) <= day < exp:
                return (exp - _dt.timedelta(days=WINDOW_DAYS_BEFORE), exp)
    return None


def in_roll_window(day):
    """True when a date sits in the ten days before a quarterly expiry."""
    return roll_window_for(day) is not None


def _et_dates(times):
    """ET calendar date per bar, from unix-second bar-start stamps.

    The window is a calendar prior, so a few hours either side of midnight does not
    change the answer; converting through UTC keeps this dependency-free.
    """
    out = []
    for t in np.asarray(times, dtype="int64"):
        # US/Eastern is UTC-5 in December and UTC-4 in June. A fixed -5 is off by at
        # most one hour in summer, which can only move a bar stamped within that hour
        # of midnight to the previous calendar date - immaterial against a ten-day
        # window, and it avoids a timezone dependency in a module the engine imports.
        out.append(_dt.datetime.fromtimestamp(int(t) - 5 * 3600, _dt.timezone.utc).date())
    return out


def carry_prior_pts(price):
    """Expected points between consecutive quarterly contracts at this price level."""
    return abs(float(price)) * CARRY_FRAC


def suspect_bars(times, opens, closes, volumes=None, other_closes=None,
                 other_opens=None):
    """Indices of bars that look like an in-bar contract switch, with the evidence.

    `times` are bar-START stamps in unix seconds. `other_closes`/`other_opens`, when
    given, are the OTHER root's bars aligned one-for-one with these; their body is
    recorded as evidence and never gates the decision (see the module docstring).

    Returns a list of dicts, earliest bar first, each carrying the bar index, its ET
    date, the body, the thresholds it cleared and the volume - enough for a human to
    settle it without re-deriving anything.
    """
    o = np.asarray(opens, dtype="float64")
    c = np.asarray(closes, dtype="float64")
    n = len(c)
    if n == 0 or len(o) != n:
        return []
    signed = (c - o) * CARRY_SIGN     # positive means the bar moved the way a roll moves it
    body = np.abs(c - o)
    dates = _et_dates(times)
    vol = None if volumes is None else np.asarray(volumes, dtype="float64")

    hits = []
    for i in range(n):
        if not in_roll_window(dates[i]):
            continue
        if signed[i] <= 0:
            continue                  # moved against the carry, so it is not a roll step
        carry = carry_prior_pts(o[i] if o[i] else c[i])
        carry_floor = carry * BODY_FRAC_OF_CARRY
        if body[i] < carry_floor:
            continue
        # Spread of the bars BEFORE this one, so the suspect bar cannot inflate its own
        # threshold. Anything this large is not price action at this bar size.
        lo = max(0, i - SD_LOOKBACK)
        prior = body[lo:i]
        sd_floor = None
        if len(prior) >= SD_MIN_BARS:
            sd = float(np.std(prior))
            sd = max(sd, abs(float(o[i] or c[i])) * SD_FLOOR_FRAC)
            sd_floor = sd * SD_MULT
            if body[i] < sd_floor:
                continue
        win = roll_window_for(dates[i])
        hit = dict(index=int(i), time=int(np.asarray(times)[i]), et_date=str(dates[i]),
                   expiry=str(win[1]) if win else None,
                   open=float(o[i]), close=float(c[i]), body=float(body[i]),
                   carry_prior=float(carry), body_floor=float(carry_floor),
                   sd_floor=(None if sd_floor is None else float(sd_floor)),
                   sd_bars=int(len(prior)),
                   volume=(None if vol is None else float(vol[i])),
                   volume_median=(None if vol is None or not len(vol[lo:i])
                                  else float(np.median(vol[lo:i]))),
                   other_body=None)
        if other_closes is not None and other_opens is not None:
            oc = np.asarray(other_closes, dtype="float64")
            oo = np.asarray(other_opens, dtype="float64")
            if len(oc) == n and len(oo) == n:
                hit["other_body"] = float(abs(oc[i] - oo[i]))
        hits.append(hit)
    return hits


def first_suspect_after(times, opens, closes, after_time, **kw):
    """The earliest suspect bar STRICTLY AFTER `after_time`, or None.

    This is what a refresh asks: the master already ends at `after_time`, and the
    question is whether any bar it is about to append is a glued-together bar. Bars at
    or before `after_time` are already stored - re-flagging them would stall every
    refresh forever, and ROLL_AUDIT.md tracks the ones we already have.
    """
    t = np.asarray(times, dtype="int64")
    for hit in suspect_bars(times, opens, closes, **kw):
        if t[hit["index"]] > int(after_time):
            return hit
    return None


def describe(hit):
    """One plain-English line for a log or a UI message."""
    if not hit:
        return ""
    vol = ""
    if hit.get("volume") is not None and hit.get("volume_median"):
        vol = " Its volume is %s against a recent median of %s." % (
            format(int(hit["volume"]), ","), format(int(hit["volume_median"]), ","))
    return ("%s ET: this bar opens at %s and closes at %s, a move of %s points inside one "
            "bar, against an expected contract carry of about %s points and expiry on %s."
            "%s This is what a contract switch inside a bar looks like, so the append "
            "stopped here instead of gluing two contracts into one bar."
            % (hit["et_date"], format(hit["open"], ",.2f"), format(hit["close"], ",.2f"),
               format(hit["body"], ",.2f"), format(hit["carry_prior"], ",.0f"),
               hit["expiry"], vol))


# --------------------------------------------------------------------------------------
# Adapters for the two shapes the refresh paths actually hold data in. Both return
# (rows_that_are_safe_to_store, hit_or_None) and NEVER drop a bar silently: when a hit
# comes back, the caller keeps only the bars before it and has to say so out loud.
# --------------------------------------------------------------------------------------

def _col(df, name):
    """Fetch a column whatever case the frame uses ('open' in the CSVs, 'Open' in memory)."""
    for cand in (name, name.capitalize(), name.upper()):
        if cand in df.columns:
            return df[cand].values
    return None


def split_tv_frame(df, after_time, other=None):
    """Split a TV-format frame (a `time` column of unix seconds) at the first suspect bar.

    This is the shape `tools/refresh_noadj_yahoo.py` builds from a Yahoo pull.
    """
    if df is None or not len(df):
        return df, None
    kw = {}
    if other is not None and len(other) == len(df):
        kw["other_opens"] = _col(other, "open")
        kw["other_closes"] = _col(other, "close")
    hit = first_suspect_after(df["time"].values, _col(df, "open"), _col(df, "close"),
                              after_time=after_time, volumes=_col(df, "volume"), **kw)
    if hit is None:
        return df, None
    return df[df["time"] < hit["time"]].reset_index(drop=True), hit


def split_indexed_frame(df, after_ts):
    """Split a datetime-indexed OHLCV frame at the first suspect bar.

    This is the shape `optimizer.auto_refresh_masters` holds after `combine_ohlcv_frames`,
    so the guard sits between the merge and the save. `after_ts` is the master's last
    stored bar; pass None to consider every bar in the frame.
    """
    if df is None or not len(df):
        return df, None
    try:
        idx = df.index
        secs = (idx.view("int64") // 1_000_000_000) if hasattr(idx, "view") \
            else np.array([int(x.timestamp()) for x in idx], dtype="int64")
    except Exception:
        return df, None
    after = -1 if after_ts is None else int(after_ts)
    hit = first_suspect_after(secs, _col(df, "open"), _col(df, "close"),
                              after_time=after, volumes=_col(df, "volume"))
    if hit is None:
        return df, None
    return df.iloc[:hit["index"]], hit


# The alert sink. A refused append has to be visible without reading a log: the runner
# prints the line, and this drops one small JSON file per event next to the other EdgeLog
# state so a human (or the data-health check) finds it later. Writing it must never be
# able to fail a refresh, so every error here is swallowed.
ALERT_DIR = r"C:\EdgeLog\roll_alerts"


def write_alert(master, timeframe, hit, alert_dir=None):
    """Record a refused append. Returns the path written, or None."""
    import json
    import os
    if not hit:
        return None
    d = alert_dir or ALERT_DIR
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "%s_%s.json" % (str(master).replace(".csv", ""),
                                               hit.get("et_date")))
        payload = dict(hit)
        payload.update(master=str(master), timeframe=str(timeframe),
                       message=describe(hit))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return path
    except Exception as e:
        # Say so rather than losing the record in silence. The caller still prints the
        # refusal itself, so the append stays safe whether or not this file lands.
        print("  roll_guard: could not write the alert file (%s)" % e)
        return None
