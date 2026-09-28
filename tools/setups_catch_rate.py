"""tools/setups_catch_rate.py -- READ-ONLY measurement: of the owner's 44 labelled discretionary
futures journal trades (CBU/ENGU/EBU/CBD/ENGD on MES/MNQ), how many would three CODED rules have
flagged at (about) the same moment, and how many alerts per day each rule fires. No tuning, no
parameter search -- exactly three fixed parameter sets (R1, R2, R3 below). Nothing here edits a
strategy file, queues a job, writes Firestore, or pushes.

PRE-REGISTERED MATCHING RULE (written before this script was ever run against real numbers --
this is the contract; do not tune the windows below after seeing results):

  For each journal trade with signal candle S (1m start time, ET) on session date D:
  - EXACT catch: an alert bar of the same-direction rule in session D whose bar start is in
    [S-1min, S+1min].
  - NEAR catch: alert bar start in [S-5min, S+5min].
  - DAY catch: any alert bar of that rule in session D (upper bound, not a real catch).
  - TAKEN: the backtest's own single trade that session has its signal bar (fill bar - 1) in
    [S-5, S+5].
  - ELIGIBLE: S falls inside the rule's own decision window (setup_kit.decision_mask): RTH bars
    whose close is no later than end_min minutes after 09:30 (e.g. R2 end_min=30 -> signal bars
    09:30..09:59). Report catches over all 44 AND over the eligible ones.
  One exception, pre-registered because it is in the input spec, not a result-driven tweak: the
  2026-09-08 trade (n=48) was traded off a 5-minute chart, signal candle 13:00; its "5-minute
  candle" is the five 1-minute bars 13:00..13:04, so its EXACT/NEAR/precision windows are widened
  by +4 minutes on the RIGHT edge only ([S-1, S+1+4] and [S-5, S+5+4]). Every other trade uses the
  plain 1-minute S.
  Session = the house 18:00 ET session convention used by setup_kit.sessions; D = the RTH date of
  that session (the calendar date its 09:30-15:59 bars fall on).

DEFINITION OF AN ALERT BAR (also pre-registered, replicated verbatim from setup_kit.run, NOT from
a hand-written copy): a bar i is a CANDIDATE if the strategy file's own vectorised rule fires there
(candidate_mask). It is an ALERT if it ALSO passes setup_kit.run's per-bar risk check, evaluated
independently for EVERY candidate bar (not just the first one of the session -- that "one trade per
session" restriction is a backtest/bookkeeping artifact, not something a live alert would respect):
    k0 = i + 1                                   # entry bar = next bar's open
    if k0 >= n: not an alert
    a_atr = atr14[i]
    if (stop_buf_atr>0 or min_risk_atr>0) and not isfinite(a_atr): not an alert
    buf = stop_buf_atr * a_atr if stop_buf_atr>0 else 0.0
    stop = l[i] - buf                            # (this is the MIRROR-TAPE l[i] for a short --
                                                   #  mirror_short inverts o/h/l/c before setup_kit.run
                                                   #  ever sees them, so "signal low" here already IS
                                                   #  "signal high, mirrored" for CBDQ/ENGU_2_0_D)
    entry = o[k0]
    risk = entry - stop
    floor = min_risk_atr * a_atr if min_risk_atr>0 else 0.0
    if not (risk > max(0.0, floor)): not an alert
    (kend = last RTH bar of the session; if kend < k0: not an alert -- decision_mask already
     excludes this in practice)
This is captured by monkeypatching the augur_engine.setup_kit module-level function `run` (the
exact call site every strategy file's `_core` uses, `SK.run(...)`, including CBDQ_1M_1_0.py's and
ENGU_2_0_D.py's dynamically-loaded copies of the long file's `_core`, since all of them resolve
`SK` to the one shared `augur_engine.setup_kit` module object) to record (o, h, l, c, P,
candidate_mask, stop_buf_atr, min_risk_atr) on every call, then calling the original unpatched
`run` so the real backtest (one trade per session) still executes untouched. The patch is restored
in a `finally` block.

THE THREE RULES (fixed, pre-specified -- everything else is the file's own DEFAULT_PARAMS):
  R1 "#427 crown"    (CBU-Q):  level_mode='pm',  base_k=3.0, be_R=1.5, target_R=2.0, trail_bars=15,
                                end_min=60,  stop_buf_atr=0.25, first_bar='allow', base_bars=6,
                                exit_mode='ride', min_risk_atr=0.5, vol_mult=0.0.
  R2 "triage cell"   (CBU-Q):  level_mode='pdh', end_min=30, vol_mult=2.0, exit_mode='ride',
                                be_R=1.0, trail_bars=15, target_R=2.0, first_bar='allow',
                                base_bars=0, base_k=2.0, stop_buf_atr=0.0, min_risk_atr=0.0.
  R3 "ENGU 2.0":  ENGU_2_0.py DEFAULT_PARAMS, unchanged.
Long rules (CBUQ_1M_1_0.py, ENGU_2_0.py) are judged against the owner's LONG trades. As a SIDE
LINE ONLY, the exact short mirrors (CBDQ_1M_1_0.py for R1/R2, ENGU_2_0_D.py for R3), same params,
are run against his SHORT trades and reported separately, never mixed into the main long counts.
In the per-trade CSV, each trade is checked against the rule variant matching ITS OWN direction
(long trades vs the long rule, short trades vs the mirror) under the same R1/R2/R3 column names --
the summary splits long (38) vs short (6) explicitly so this never conflates the two populations.

DATA RECIPE:
  Bars: augur_uploads/FADJ_ES_1m_ETH.csv and FADJ_NQ_1m_ETH.csv (forward-adjusted 1-minute 24h ETH
  masters, bar-START stamped, epoch-seconds UTC). Loaded from 2025-06-01 ET onward (warm-up for
  ATR14 / the 20-session first-bar volume baseline) via a byte-offset binary search on the sorted
  CSV (finds the tail's byte offset in a handful of seeks, then one pandas.read_csv over just the
  tail -- never parses the 15 years of history before it).
  These masters have a HOLE 2026-06-30 ~10:49 ET .. 2026-08-06 (confirmed below: last bar before
  the hole is the 10:48 ET bar on 2026-06-30, data resumes at the 00:09 ET bar on 2026-08-06).
  Filled from the NinjaTrader 10-second capture masters (augur_uploads/master_c279374a.csv = ES,
  master_b1335b7e.csv = NQ): bar-END stamped (repo convention -- see tools/setup_journal.py
  day_bars()), so shifted back 10 seconds, then resampled to 1-minute bar-START OHLCV
  (label='left', closed='left'; open=first, high=max, low=min, close=last, volume=sum -- same
  recipe as tools/setup_journal.py's bars_1m()). These captures are RAW (unadjusted) prices, so a
  constant offset = median(FADJ close - resampled-10s close) is measured on overlapping minutes
  twice, independently -- 2026-06-23..2026-06-29 (just before the hole) and 2026-08-06..2026-09-11
  (just after it) -- printed and checked to agree (no roll should sit between them); the MEAN of
  the two is added to the 10-second-derived open/high/low/close before splicing them into the gap.
  Any other run of >3 calendar days with no FADJ bar is filled the same way (harmless: the only
  other one found is the Labor Day long weekend, where the capture's data is simply a few extra
  Globex minutes tools/setup_journal.py also documents).
  Merged bars are trimmed to strictly before 2026-09-25 18:00 ET (the next session's 18:00 roll),
  so the last COMPLETE session is RTH date 2026-09-25 and no run's "last RTH bar of the session"
  bookkeeping is corrupted by a mid-day truncation of today's still-live data.
  Sanity checks printed: no 1-minute close-to-close jump > 150 pts NQ / 40 pts ES within a day of
  2026-06-15 or 2026-09-14 (the FADJ roll-adjustment should have already removed those); no
  remaining gap > 4 calendar days anywhere in 2026 after the hole-fill, other than weekends/
  holidays.

HOW TO RUN:
    cd C:\\Users\\xride\\AppData\\Local\\EdgeLog-worktrees\\catchrate
    PYTHONIOENCODING=utf-8 python tools/setups_catch_rate.py
  Reads bars from the SHARED checkout (C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG\\augur_uploads
  -- this worktree has none, per BACKTEST_SPEED.md rule 3) but imports the strategy/engine code
  from THIS worktree. Runs in well under 2 minutes. Writes, under C:\\EdgeLog\\_anatomy_cache\\
  catchrate\\ (never inside a worktree -- caches get wiped):
    per_trade.csv   one row per journal trade (+ 1 extra row for the un-journalled 2026-09-24
                    trade), eligible/exact/near/day/taken per rule, nearest alert bar + offset.
    summary.md      the catch-rate tables, alerts-per-day tables, and every caveat hit.
  Read-only: no strategy file is edited, no job is queued, nothing is written to Firestore, and
  nothing is pushed.
"""
import io
import os
import sys
import json
import importlib.util
from collections import defaultdict

import numpy as np
import pandas as pd

ET = "America/New_York"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
STRAT_DIR = os.path.join(ROOT, "augur_strategies")
JOURNAL = os.path.join(ROOT, "tools", "data", "setup_journal.json")

UPLOADS = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "EDGE-LOG", "augur_uploads")
OUT_DIR = r"C:\EdgeLog\_anatomy_cache\catchrate"

FADJ_1M = {"ES": "FADJ_ES_1m_ETH.csv", "NQ": "FADJ_NQ_1m_ETH.csv"}
NT_10S = {"ES": "master_c279374a.csv", "NQ": "master_b1335b7e.csv"}
ROOT_OF = {"MES": "ES", "MNQ": "NQ"}
SETUP_LABELS = {"CBU", "ENGU", "EBU", "CBD", "ENGD"}

LOAD_FROM = "2025-06-01"
END_CUTOFF = pd.Timestamp("2026-09-25 18:00:00", tz=ET)   # exclusive -- next session's roll
JOURNAL_PERIOD = ("2026-04-07", "2026-09-25")
LOOKBACK_PERIOD = ("2025-09-26", "2026-09-25")

EXTRA_TRADE = dict(date="2026-09-24", sym="MNQ", dir="LONG", label="EBU",
                    signal_candle="12:19", entry_time="12:20", entry=30687.00, exit=30700.00)

RULES = {
    "R1": dict(name="#427 crown", long_file="CBUQ_1M_1_0", short_file="CBDQ_1M_1_0",
               params=dict(level_mode="pm", base_k=3.0, be_R=1.5, target_R=2.0, trail_bars=15,
                           end_min=60, stop_buf_atr=0.25, first_bar="allow", base_bars=6,
                           exit_mode="ride", min_risk_atr=0.5, vol_mult=0.0)),
    "R2": dict(name="triage cell", long_file="CBUQ_1M_1_0", short_file="CBDQ_1M_1_0",
               params=dict(level_mode="pdh", end_min=30, vol_mult=2.0, exit_mode="ride",
                           be_R=1.0, trail_bars=15, target_R=2.0, first_bar="allow",
                           base_bars=0, base_k=2.0, stop_buf_atr=0.0, min_risk_atr=0.0)),
    "R3": dict(name="ENGU 2.0", long_file="ENGU_2_0", short_file="ENGU_2_0_D", params={}),
}


# ─────────────────────────────────────────────────────────────────────────────
# data loading: fast tail read + hole fill
# ─────────────────────────────────────────────────────────────────────────────
def _find_offset(path, target_epoch):
    """Byte offset of the first data line (after the header) whose epoch >= target_epoch, via
    binary search directly on the sorted CSV -- a few seeks, never a scan of the whole file."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        f.readline()                       # header
        lo, hi = f.tell(), size
        while lo < hi:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()                   # discard the partial line straddling mid
            pos = f.tell()
            if pos >= hi:
                hi = mid
                continue
            line = f.readline()
            if not line:
                hi = mid
                continue
            try:
                epoch = int(line.split(b",", 1)[0])
            except ValueError:
                hi = mid
                continue
            if epoch < target_epoch:
                lo = pos + len(line)
            else:
                hi = pos
        return lo


def load_fadj_tail(root, start_date):
    path = os.path.join(UPLOADS, FADJ_1M[root])
    target = int(pd.Timestamp(start_date, tz=ET).timestamp())
    off = _find_offset(path, target)
    with open(path, "rb") as f:
        f.seek(off)
        df = pd.read_csv(f, header=None,
                          names=["time", "open", "high", "low", "close", "volume", "source", "synthetic"],
                          usecols=[0, 1, 2, 3, 4, 5])
    df = df.sort_values("time").drop_duplicates("time")
    idx = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s", utc=True)).tz_convert(ET)
    out = df.set_index(idx)[["time", "open", "high", "low", "close", "volume"]]
    out.index.name = None
    return out


def load_nt10s_resampled(root):
    """NT 10-second capture -> shifted back 10s (bar-END -> bar-START) -> resampled to 1-minute
    bar-START OHLCV. Raw (unadjusted) prices -- caller applies the hole-fill offset."""
    path = os.path.join(UPLOADS, NT_10S[root])
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close", "volume"])
    df = df.sort_values("time").drop_duplicates("time")
    shifted = df["time"] - 10
    idx = pd.DatetimeIndex(pd.to_datetime(shifted, unit="s", utc=True)).tz_convert(ET)
    b = df.set_index(idx)[["open", "high", "low", "close", "volume"]]
    b.index.name = None
    r = b.resample("1min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    r["time"] = r.index.astype("int64") // 10 ** 9
    return r


def hole_fill_offset(fadj, res10, d0, d1, label, report):
    m = (res10.index >= pd.Timestamp(d0, tz=ET)) & (res10.index < pd.Timestamp(d1, tz=ET))
    r = res10[m]
    joined = fadj[["close"]].join(r[["close"]], how="inner", lsuffix="_fadj", rsuffix="_10s")
    diff = joined["close_fadj"] - joined["close_10s"]
    med = float(diff.median())
    report.append("  %s: n=%d overlapping minutes, median offset=%.3f, std=%.3f"
                   % (label, len(joined), med, float(diff.std())))
    return med, len(joined)


def find_holes(fadj, min_gap_s=3 * 86400):
    t = fadj["time"].values
    d = np.diff(t)
    idxs = np.flatnonzero(d > min_gap_s)
    return [(int(t[i]), int(t[i + 1])) for i in idxs]


def build_merged(root, report):
    fadj = load_fadj_tail(root, LOAD_FROM)
    res10 = load_nt10s_resampled(root)

    report.append("%s hole-fill offset (FADJ close - 10s-resampled close, unadjusted):" % root)
    offA, nA = hole_fill_offset(fadj, res10, "2026-06-23", "2026-06-30", "window A (06-23..06-29, pre-hole)", report)
    offB, nB = hole_fill_offset(fadj, res10, "2026-08-06", "2026-09-12", "window B (08-06..09-11, post-hole)", report)
    agree = abs(offA - offB)
    report.append("  agreement: |A-B| = %.3f pts (%s)" % (agree, "OK, no roll between them" if agree < 2.0 else "MISMATCH -- check for a roll"))
    offset = (offA + offB) / 2.0

    holes = find_holes(fadj)
    fills = []
    filled_bars = 0
    for a, b in holes:
        seg = res10[(res10["time"] > a) & (res10["time"] < b)].copy()
        for col in ("open", "high", "low", "close"):
            seg[col] = seg[col] + offset
        fills.append(seg[["time", "open", "high", "low", "close", "volume"]])
        filled_bars += len(seg)
        a_ts = pd.Timestamp(a, unit="s", tz="UTC").tz_convert(ET)
        b_ts = pd.Timestamp(b, unit="s", tz="UTC").tz_convert(ET)
        report.append("  %s hole %s -> %s (%.1f days): filled %d bars from the 10s capture (+%.3f pts)"
                       % (root, a_ts, b_ts, (b - a) / 86400.0, len(seg), offset))

    if fills:
        fill_df = pd.concat(fills)
        merged = pd.concat([fadj[["time", "open", "high", "low", "close", "volume"]], fill_df]).sort_index()
        merged = merged[~merged.index.duplicated(keep="first")]
    else:
        merged = fadj[["time", "open", "high", "low", "close", "volume"]]

    merged = merged[merged.index < END_CUTOFF]
    return merged, offset, report


def sanity_checks(merged, root, report):
    ts = merged.index
    close = merged["close"].values
    t = merged["time"].values

    for date in ("2026-06-15", "2026-09-14"):
        window = (ts >= pd.Timestamp(date, tz=ET) - pd.Timedelta(days=1)) & (ts < pd.Timestamp(date, tz=ET) + pd.Timedelta(days=2))
        sub = np.abs(np.diff(close[window]))
        mx = float(sub.max()) if len(sub) else float("nan")
        thresh = 150.0 if root == "NQ" else 40.0
        report.append("  %s roll-jump check %s: max 1-min close jump = %.2f pts (threshold %.0f) -> %s"
                       % (root, date, mx, thresh, "OK" if mx <= thresh else "FAIL -- roll not removed"))

    d = np.diff(t)
    big = np.flatnonzero(d > 4 * 86400)
    if len(big) == 0:
        report.append("  %s: no gap > 4 calendar days remains after hole-fill" % root)
    for i in big:
        a = pd.Timestamp(int(t[i]), unit="s", tz="UTC").tz_convert(ET)
        b = pd.Timestamp(int(t[i + 1]), unit="s", tz="UTC").tz_convert(ET)
        report.append("  %s: REMAINING GAP %s -> %s (%.1f days)" % (root, a, b, (b - a).total_seconds() / 86400.0))


# ─────────────────────────────────────────────────────────────────────────────
# strategy loading + the SK.run capture
# ─────────────────────────────────────────────────────────────────────────────
def load_strategy(name):
    path = os.path.join(STRAT_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("_catchrate_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class RunRecorder:
    """Monkeypatches augur_engine.setup_kit.run (the exact call site every strategy file's `_core`
    uses -- CBDQ_1M_1_0.py and ENGU_2_0_D.py's dynamically-loaded copies of the long file's `_core`
    resolve `SK` to this SAME shared module object) to record every call's (o, h, l, c, P,
    candidate_mask, stop_buf_atr, min_risk_atr), then calls the original unpatched `run` so the
    real backtest executes untouched. Restores the original on exit even if the caller raises."""

    def __init__(self):
        self.calls = []

    def __enter__(self):
        import augur_engine.setup_kit as SK
        self._SK = SK
        self._orig = SK.run

        def wrapped(o, h, l, c, P, candidate_mask, exit_mode, be_R, trail_bars, target_R,
                    stop_buf_atr, min_risk_atr):
            self.calls.append(dict(o=o, h=h, l=l, c=c, P=P, mask=candidate_mask.copy(),
                                    stop_buf_atr=stop_buf_atr, min_risk_atr=min_risk_atr))
            return self._orig(o, h, l, c, P, candidate_mask, exit_mode, be_R, trail_bars, target_R,
                              stop_buf_atr, min_risk_atr)

        SK.run = wrapped
        return self

    def __exit__(self, exc_type, exc, tb):
        self._SK.run = self._orig
        return False


def alert_bar_indices(call, n):
    """Replicates setup_kit.run's per-bar risk check EXACTLY, for every candidate bar (not just
    the first-of-session one the real backtest keeps) -- see the module docstring."""
    o, h, l = call["o"], call["h"], call["l"]
    P = call["P"]
    atr14 = P["atr14"]; sess = P["sess"]; last_rth_idx = P["last_rth_idx"]
    stop_buf_atr = call["stop_buf_atr"]; min_risk_atr = call["min_risk_atr"]
    cand_idx = np.flatnonzero(call["mask"])
    out = []
    for i in cand_idx:
        i = int(i)
        k0 = i + 1
        if k0 >= n:
            continue
        a_atr = atr14[i]
        if (stop_buf_atr > 0 or min_risk_atr > 0) and not np.isfinite(a_atr):
            continue
        buf = stop_buf_atr * a_atr if stop_buf_atr > 0 else 0.0
        stop = l[i] - buf
        entry = o[k0]
        risk = entry - stop
        floor = min_risk_atr * a_atr if min_risk_atr > 0 else 0.0
        if not (risk > max(0.0, floor)):
            continue
        s = int(sess[i])
        kend = int(last_rth_idx[s])
        if kend < k0:
            continue
        out.append(i)
    return np.array(out, dtype=int)


def session_date_map(P, idx):
    """sess id -> RTH date string, for sessions that actually have RTH bars (others carry no
    entry and are excluded from every per-day stat -- 'sessions with data')."""
    first_rth = np.flatnonzero(P["is_first_rth"])
    return {int(P["sess"][i]): idx[i].strftime("%Y-%m-%d") for i in first_rth}


def run_rule(mod, o, h, l, c, v, idx, params):
    """One run_backtest call under the recorder. Returns (alert_idx, P, trades, sess_date)."""
    rec = RunRecorder()
    with rec:
        res = mod.run_backtest(o, h, l, c, volumes=v, index=idx, return_trades=True, **params)
    call = rec.calls[0]
    alerts = alert_bar_indices(call, len(c))
    trades = res["trades"] if res else []
    sess_date = session_date_map(call["P"], idx)
    return alerts, call["P"], trades, sess_date


# ─────────────────────────────────────────────────────────────────────────────
# journal trades
# ─────────────────────────────────────────────────────────────────────────────
def load_journal_trades():
    d = json.load(io.open(JOURNAL, encoding="utf-8"))
    out = []
    for t in d["trades"]:
        if t.get("asset") != "futures" or t.get("label") not in SETUP_LABELS:
            continue
        sc = t.get("signal_candle") or t.get("entry_time")
        widen = 4 if t.get("tf") == "5m" else 0
        out.append(dict(n=t["n"], date=t["date"], sym=t["sym"], root=ROOT_OF[t["sym"]],
                        dir=t["dir"], label=t["label"], S=sc, entry_time=t.get("entry_time"),
                        widen=widen, tf=t.get("tf")))
    out.sort(key=lambda r: (r["date"], r["entry_time"] or ""))
    return out


def hhmm_to_ts(date, hhmm):
    return pd.Timestamp("%s %s" % (date, hhmm), tz=ET)


# ─────────────────────────────────────────────────────────────────────────────
# matching (the pre-registered rule)
# ─────────────────────────────────────────────────────────────────────────────
def match_trade(trade, idx, alerts_ts, alert_dates, trades_list, sess_date_by_idx, decision_ok):
    """alerts_ts: sorted np.datetime64 array of that (rule,side,root)'s alert bar timestamps.
    alert_dates: parallel array of 'YYYY-MM-DD' strings (RTH date) per alert bar.
    trades_list: the rule's own (fill_bar, exit_bar, pnl, side, entry) trades, this root.
    decision_ok: bool array, same length as idx, True where S would be an eligible decision bar.
    """
    date = trade["date"]
    S = hhmm_to_ts(date, trade["S"])
    right = trade["widen"]
    exact_lo, exact_hi = S - pd.Timedelta(minutes=1), S + pd.Timedelta(minutes=1 + right)
    near_lo, near_hi = S - pd.Timedelta(minutes=5), S + pd.Timedelta(minutes=5 + right)

    day_mask = alert_dates == date
    day_ts = alerts_ts[day_mask]
    day_catch = bool(len(day_ts))

    near_ts = day_ts[(day_ts >= near_lo.to_datetime64()) & (day_ts <= near_hi.to_datetime64())]
    near_catch = bool(len(near_ts))
    exact_ts = day_ts[(day_ts >= exact_lo.to_datetime64()) & (day_ts <= exact_hi.to_datetime64())]
    exact_catch = bool(len(exact_ts))

    if len(day_ts):
        offs = (day_ts - S.to_datetime64()) / np.timedelta64(1, "m")
        j = int(np.argmin(np.abs(offs)))
        # day_ts entries are UTC-instant numpy datetime64 (DatetimeIndex.values semantics) --
        # re-attach UTC then convert to ET before formatting, or this prints UTC digits mislabelled
        # as ET wall-clock (off by the ET-UTC offset).
        nearest_ts = pd.Timestamp(day_ts[j], tz="UTC").tz_convert(ET).strftime("%H:%M")
        nearest_off = float(offs[j])
    else:
        nearest_ts, nearest_off = None, None

    taken_lo, taken_hi = S - pd.Timedelta(minutes=5), S + pd.Timedelta(minutes=5 + right)
    taken = False
    for (fb, xb, pnl, side, entry) in trades_list:
        sig_bar = fb - 1
        if sig_bar < 0 or sig_bar >= len(idx):
            continue
        if idx[sig_bar].strftime("%Y-%m-%d") != date:
            continue
        t_sig = idx[sig_bar]
        if taken_lo <= t_sig <= taken_hi:
            taken = True
            break

    try:
        s_loc = idx.get_loc(S)
        eligible = bool(decision_ok[s_loc])
    except KeyError:
        eligible = None            # S's own bar not present (should not happen post hole-fill)

    return dict(eligible=eligible, exact=exact_catch, near=near_catch, day=day_catch, taken=taken,
                nearest_alert=nearest_ts, nearest_off_min=nearest_off)


# ─────────────────────────────────────────────────────────────────────────────
# alerts-per-day
# ─────────────────────────────────────────────────────────────────────────────
def episodes(sorted_idx):
    """Consecutive alert-bar indices, gaps of <=1 bar merged into one episode. Returns a list of
    (start_idx, end_idx) pairs."""
    if len(sorted_idx) == 0:
        return []
    out = []
    s = sorted_idx[0]
    prev = sorted_idx[0]
    for x in sorted_idx[1:]:
        if x - prev > 2:                 # more than 1 bar gap -> new episode
            out.append((s, prev))
            s = x
        prev = x
    out.append((s, prev))
    return out


def per_session_counts(alert_idx, P, idx, sess_date, trades_list, date_lo, date_hi):
    """-> {date: (raw_alert_bars, n_episodes, n_trades)} for sessions with RTH data in
    [date_lo, date_hi]."""
    starts, ends, sess = P["starts"], P["ends"], P["sess"]
    by_sess_alerts = defaultdict(list)
    for i in alert_idx:
        by_sess_alerts[int(sess[i])].append(int(i))
    by_sess_trades = defaultdict(int)
    for (fb, xb, pnl, side, entry) in trades_list:
        by_sess_trades[int(sess[fb])] += 1

    out = {}
    for s, date in sess_date.items():
        if not (date_lo <= date <= date_hi):
            continue
        a = sorted(by_sess_alerts.get(s, []))
        eps = episodes(a)
        out[date] = (len(a), len(eps), by_sess_trades.get(s, 0))
    return out


def stat_row(values):
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return dict(mean=float("nan"), median=float("nan"), p90=float("nan"), pct_ge1=float("nan"), n=0)
    return dict(mean=float(v.mean()), median=float(np.median(v)),
                p90=float(np.percentile(v, 90)), pct_ge1=float(100.0 * (v >= 1).mean()), n=len(v))


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    report = []

    report.append("=== data load + hole fill + sanity checks ===")
    merged = {}
    offsets = {}
    for root in ("ES", "NQ"):
        m, off, report = build_merged(root, report)
        merged[root] = m
        offsets[root] = off
        sanity_checks(m, root, report)

    arrays = {}
    for root, m in merged.items():
        idx = m.index
        o = m["open"].to_numpy(float); h = m["high"].to_numpy(float)
        l = m["low"].to_numpy(float); c = m["close"].to_numpy(float)
        v = m["volume"].to_numpy(float)
        arrays[root] = dict(o=o, h=h, l=l, c=c, v=v, idx=idx)
        report.append("%s: %d bars loaded, %s -> %s" % (root, len(m), idx.min(), idx.max()))

    print("\n".join(report))
    print()

    import augur_engine.setup_kit as SK

    modules = {name: load_strategy(name) for name in
               ("CBUQ_1M_1_0", "CBDQ_1M_1_0", "ENGU_2_0", "ENGU_2_0_D")}

    # ── run every (rule, side, root) once, grouped by (root, side) to reuse setup_kit's 2-slot
    # prep() cache across the 3 rules that share the same price array. ──
    results = {}   # (rule, side, root) -> dict(alerts, P, trades, sess_date, idx)
    for root in ("ES", "NQ"):
        a = arrays[root]
        for side, file_key in (("long", "long_file"), ("short", "short_file")):
            for rk, rule in RULES.items():
                mod = modules[rule[file_key]]
                alerts, P, trades, sess_date = run_rule(mod, a["o"], a["h"], a["l"], a["c"], a["v"],
                                                        a["idx"], rule["params"])
                results[(rk, side, root)] = dict(alerts=alerts, P=P, trades=trades,
                                                 sess_date=sess_date, idx=a["idx"])

    # eligibility per rule/side/root, from setup_kit.decision_mask directly on the captured P
    def decision_ok_for(rk, side, root):
        rule = RULES[rk]
        P = results[(rk, side, root)]["P"]
        if rk == "R3":
            end_min = 360
            first_bar = "skip"          # hardcoded inside ENGU_2_0._core
        else:
            end_min = rule["params"]["end_min"]
            first_bar = rule["params"]["first_bar"]
        return SK.decision_mask(P, end_min, first_bar=first_bar)

    # ── the 44 journal trades ──
    trades44 = load_journal_trades()
    assert len(trades44) == 44, "expected 44 labelled futures trades, got %d" % len(trades44)
    n_long = sum(1 for t in trades44 if t["dir"] == "LONG")
    n_short = sum(1 for t in trades44 if t["dir"] == "SHORT")
    report.append("\n44 labelled futures trades: %d LONG, %d SHORT" % (n_long, n_short))

    per_trade_rows = []
    catch = defaultdict(lambda: defaultdict(lambda: dict(exact=0, near=0, day=0, taken=0,
                                                          exact_e=0, near_e=0, day_e=0, taken_e=0, n=0, n_e=0)))
    # catch[rule][label] accumulates; 'label' also has a synthetic 'ALL' key and per-direction split

    for t in trades44:
        side = "long" if t["dir"] == "LONG" else "short"
        row = dict(date=t["date"], sym=t["sym"], dir=t["dir"], label=t["label"], S=t["S"], widen=t["widen"])
        for rk in ("R1", "R2", "R3"):
            res = results[(rk, side, t["root"])]
            dok = decision_ok_for(rk, side, t["root"])
            alerts_ts = res["idx"].values[res["alerts"]]
            alert_dates = np.array([res["idx"][i].strftime("%Y-%m-%d") for i in res["alerts"]])
            m = match_trade(t, res["idx"], alerts_ts, alert_dates, res["trades"], res["sess_date"], dok)
            row["%s_eligible" % rk] = m["eligible"]
            row["%s_exact" % rk] = m["exact"]
            row["%s_near" % rk] = m["near"]
            row["%s_day" % rk] = m["day"]
            row["%s_taken" % rk] = m["taken"]
            row["%s_nearest_alert" % rk] = m["nearest_alert"]
            row["%s_nearest_off_min" % rk] = m["nearest_off_min"]

            bucket = catch[rk][t["label"]]
            bucket["n"] += 1
            bucket["exact"] += int(m["exact"]); bucket["near"] += int(m["near"])
            bucket["day"] += int(m["day"]); bucket["taken"] += int(m["taken"])
            if m["eligible"]:
                bucket["n_e"] += 1
                bucket["exact_e"] += int(m["exact"]); bucket["near_e"] += int(m["near"])
                bucket["day_e"] += int(m["day"]); bucket["taken_e"] += int(m["taken"])
            allb = catch[rk]["ALL_%s" % side]
            allb["n"] += 1
            allb["exact"] += int(m["exact"]); allb["near"] += int(m["near"])
            allb["day"] += int(m["day"]); allb["taken"] += int(m["taken"])
            if m["eligible"]:
                allb["n_e"] += 1
                allb["exact_e"] += int(m["exact"]); allb["near_e"] += int(m["near"])
                allb["day_e"] += int(m["day"]); allb["taken_e"] += int(m["taken"])
        per_trade_rows.append(row)

    # ── the extra, un-journalled 2026-09-24 trade, reported separately ──
    extra = dict(n=None, date=EXTRA_TRADE["date"], sym=EXTRA_TRADE["sym"],
                 root=ROOT_OF[EXTRA_TRADE["sym"]], dir=EXTRA_TRADE["dir"], label=EXTRA_TRADE["label"],
                 S=EXTRA_TRADE["signal_candle"], entry_time=EXTRA_TRADE["entry_time"], widen=0, tf="1m")
    extra_row = dict(date=extra["date"], sym=extra["sym"], dir=extra["dir"], label=extra["label"],
                     S=extra["S"], widen=0, extra=True)
    side = "long"
    for rk in ("R1", "R2", "R3"):
        res = results[(rk, side, extra["root"])]
        dok = decision_ok_for(rk, side, extra["root"])
        alerts_ts = res["idx"].values[res["alerts"]]
        alert_dates = np.array([res["idx"][i].strftime("%Y-%m-%d") for i in res["alerts"]])
        m = match_trade(extra, res["idx"], alerts_ts, alert_dates, res["trades"], res["sess_date"], dok)
        extra_row["%s_eligible" % rk] = m["eligible"]
        extra_row["%s_exact" % rk] = m["exact"]
        extra_row["%s_near" % rk] = m["near"]
        extra_row["%s_day" % rk] = m["day"]
        extra_row["%s_taken" % rk] = m["taken"]
        extra_row["%s_nearest_alert" % rk] = m["nearest_alert"]
        extra_row["%s_nearest_off_min" % rk] = m["nearest_off_min"]

    # ── write per_trade.csv (44 + the 1 extra, flagged) ──
    cols = ["date", "sym", "dir", "label", "S", "widen"] + \
           ["%s_%s" % (rk, f) for rk in ("R1", "R2", "R3")
            for f in ("eligible", "exact", "near", "day", "taken", "nearest_alert", "nearest_off_min")]
    all_rows = [dict(r) for r in per_trade_rows]
    for r in all_rows:
        r["extra"] = False
    extra_row["extra"] = True
    all_rows.append(extra_row)
    df_out = pd.DataFrame(all_rows, columns=cols + ["extra"])
    df_out.to_csv(os.path.join(OUT_DIR, "per_trade.csv"), index=False)

    # ── alerts-per-day ──
    def period_stats(rk, root, lo, hi):
        res = results[(rk, "long", root)]
        return per_session_counts(res["alerts"], res["P"], res["idx"], res["sess_date"],
                                  res["trades"], lo, hi)

    apd = {}   # apd[rk][period][root_or_combined] = {date: (raw, eps, trades)}
    for rk in ("R1", "R2", "R3"):
        apd[rk] = {}
        for pname, (lo, hi) in (("journal", JOURNAL_PERIOD), ("lookback", LOOKBACK_PERIOD)):
            es_d = period_stats(rk, "ES", lo, hi)
            nq_d = period_stats(rk, "NQ", lo, hi)
            comb = {}
            for d in set(es_d) | set(nq_d):
                er = es_d.get(d, (0, 0, 0))
                nr = nq_d.get(d, (0, 0, 0))
                comb[d] = (er[0] + nr[0], er[1] + nr[1], er[2] + nr[2])
            apd[rk][pname] = dict(ES=es_d, NQ=nq_d, COMBINED=comb)

    # ── precision on the owner's trading days (journal period; every journal trade date falls
    # inside it) ──
    trade_dates_by_root = defaultdict(set)
    for t in trades44:
        trade_dates_by_root[t["root"]].add(t["date"])

    def precision(rk, root):
        res = results[(rk, "long", root)]
        by_sess_alerts = defaultdict(list)
        for i in res["alerts"]:
            by_sess_alerts[int(res["P"]["sess"][i])].append(int(i))
        idx = res["idx"]
        trade_days = trade_dates_by_root[root] if root != "COMBINED" else (trade_dates_by_root["ES"] | trade_dates_by_root["NQ"])
        # per-day trade S windows (near = +-5 min, widened where flagged) for this root
        day_windows = defaultdict(list)
        for t in trades44:
            if root != "COMBINED" and t["root"] != root:
                continue
            S = hhmm_to_ts(t["date"], t["S"])
            day_windows[t["date"]].append((S - pd.Timedelta(minutes=5), S + pd.Timedelta(minutes=5 + t["widen"])))
        n_eps = 0
        n_catch = 0
        for s, date in res["sess_date"].items():
            if date not in trade_days:
                continue
            a = sorted(by_sess_alerts.get(s, []))
            for (a0, a1) in episodes(a):
                n_eps += 1
                t0, t1 = idx[a0], idx[a1]
                hit = any(not (t1 < w0 or t0 > w1) for (w0, w1) in day_windows.get(date, []))
                if hit:
                    n_catch += 1
        return n_catch, n_eps

    precision_rows = {}
    for rk in ("R1", "R2", "R3"):
        precision_rows[rk] = {}
        for root in ("ES", "NQ"):
            c, n = precision(rk, root)
            precision_rows[rk][root] = (c, n)
        # combined: union alerts across roots by date -- approximate by summing hit/total across roots
        # (an episode belongs to exactly one root, so summing is exact, not approximate)
        c_es, n_es = precision_rows[rk]["ES"]
        c_nq, n_nq = precision_rows[rk]["NQ"]
        precision_rows[rk]["COMBINED"] = (c_es + c_nq, n_es + n_nq)

    # ── write summary.md ──
    L = []
    L.append("# Setup catch-rate study -- summary\n")
    L.append("Generated by `tools/setups_catch_rate.py`. Read-only research measurement; see the "
             "script docstring for the pre-registered matching rule and data recipe.\n")

    L.append("## Data load, hole fill, sanity checks\n")
    L.append("```\n" + "\n".join(report) + "\n```\n")

    L.append("## Catch rate over the 44 labelled trades (%d long, %d short)\n" % (n_long, n_short))
    L.append("Long rules judged on the 38 LONG trades; the 6 SHORT trades are a SIDE LINE via the "
             "short mirrors (CBDQ_1M_1_0 for R1/R2, ENGU_2_0_D for R3), reported separately below.\n")
    for rk in ("R1", "R2", "R3"):
        L.append("### %s (%s)\n" % (rk, RULES[rk]["name"]))
        L.append("| Label | n | eligible | exact | near | day | taken | exact(elig) | near(elig) | day(elig) | taken(elig) |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for label in ("CBU", "ENGU", "EBU", "CBD", "ENGD"):
            b = catch[rk].get(label)
            if not b or b["n"] == 0:
                continue
            L.append("| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
                label, b["n"], b["n_e"], b["exact"], b["near"], b["day"], b["taken"],
                b["exact_e"], b["near_e"], b["day_e"], b["taken_e"]))
        bl = catch[rk]["ALL_long"]
        L.append("| **ALL LONG** | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
            bl["n"], bl["n_e"], bl["exact"], bl["near"], bl["day"], bl["taken"],
            bl["exact_e"], bl["near_e"], bl["day_e"], bl["taken_e"]))
        bs = catch[rk]["ALL_short"]
        L.append("| ALL SHORT (side line, mirror rule) | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
            bs["n"], bs["n_e"], bs["exact"], bs["near"], bs["day"], bs["taken"],
            bs["exact_e"], bs["near_e"], bs["day_e"], bs["taken_e"]))
        L.append("")

    L.append("## The extra 2026-09-24 MNQ LONG EBU trade (not among the 44), 12:20 ET, 30687.00 -> 30700.00\n")
    L.append("| Rule | eligible | exact | near | day | nearest alert | offset (min) |")
    L.append("|---|---|---|---|---|---|---|")
    for rk in ("R1", "R2", "R3"):
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            rk, extra_row["%s_eligible" % rk], extra_row["%s_exact" % rk], extra_row["%s_near" % rk],
            extra_row["%s_day" % rk], extra_row["%s_nearest_alert" % rk], extra_row["%s_nearest_off_min" % rk]))
    L.append("")

    L.append("## Alerts per day\n")
    for pname, (lo, hi) in (("journal", JOURNAL_PERIOD), ("lookback", LOOKBACK_PERIOD)):
        L.append("### Period: %s (%s .. %s)\n" % (pname, lo, hi))
        for rk in ("R1", "R2", "R3"):
            L.append("**%s (%s)**\n" % (rk, RULES[rk]["name"]))
            L.append("| Root | raw/session mean | median | p90 | %>=1 | episodes/session mean | median | p90 | %>=1 | trades/session mean | median | p90 | %>=1 | n sessions |")
            L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for root in ("ES", "NQ", "COMBINED"):
                d = apd[rk][pname][root]
                raws = [v[0] for v in d.values()]
                eps = [v[1] for v in d.values()]
                trs = [v[2] for v in d.values()]
                sr, se, st = stat_row(raws), stat_row(eps), stat_row(trs)
                L.append("| %s | %.2f | %.1f | %.1f | %.0f%% | %.2f | %.1f | %.1f | %.0f%% | %.2f | %.1f | %.1f | %.0f%% | %d |" % (
                    root, sr["mean"], sr["median"], sr["p90"], sr["pct_ge1"],
                    se["mean"], se["median"], se["p90"], se["pct_ge1"],
                    st["mean"], st["median"], st["p90"], st["pct_ge1"], sr["n"]))
            L.append("")

    L.append("## Precision on the owner's trading days (episodes that are a NEAR catch of one of his same-day, same-root trades)\n")
    L.append("| Rule | Root | catching episodes | total episodes | precision |")
    L.append("|---|---|---|---|---|")
    for rk in ("R1", "R2", "R3"):
        for root in ("ES", "NQ", "COMBINED"):
            c, n = precision_rows[rk][root]
            pct = (100.0 * c / n) if n else float("nan")
            L.append("| %s | %s | %d | %d | %.1f%% |" % (rk, root, c, n, pct))
    L.append("")

    summary_text = "\n".join(L)
    io.open(os.path.join(OUT_DIR, "summary.md"), "w", encoding="utf-8").write(summary_text)

    print(summary_text)
    print("\nwrote:")
    print("  " + os.path.join(OUT_DIR, "per_trade.csv"))
    print("  " + os.path.join(OUT_DIR, "summary.md"))


if __name__ == "__main__":
    main()
