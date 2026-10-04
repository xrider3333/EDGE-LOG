# point_score.py - the owner's POINT SCORE (spec v1.2, `ps1.2`): nine yes/no points read at the signal bar of a
# trade, for futures from 2026-01 onward (stocks: stub until the Alpaca keys are saved). REFERENCE IMPLEMENTATION
# of docs/POINT_SCORE_SPEC.md - that file is the ONE definition; pine/POINT_SCORE_1_0.pine is a line-by-line port
# of it, and `parity` (below) compares the two. If this file and the spec disagree, THIS FILE is wrong.
#
#   python tools/point_score.py trade --sym MNQ --side LONG --fill "2026-09-30 09:32:21"
#   python tools/point_score.py series --root NQ --side LONG --from 2026-09-30 --to 2026-09-30 [--out f.csv]
#   python tools/point_score.py backfill --out C:\EdgeLog\point_score\backfill_scores.csv
#   python tools/point_score.py parity <tradingview_export.csv> --root NQ
#
# THE NINE POINTS (LONG; SHORT mirrors each one): close above the 200 moving average (SMA by default, EMA by
# choice - v1.2) on 10s / 1m / 5m / 30m bars, close above
# yesterday's regular-session low / close / high, a green candle with the largest body since today's low, and the
# largest volume since today's low. The signal bar S is the last CLOSED 1-minute bar before the entry fill
# (S.start = floor(fill, 1 min) - 1 min). NA is never 0: the maximum drops. A tenth point (daily trend up) is
# reported beside the score, not inside it.
#
# v1.1 (2026-10-01, review of 2026-09-30): "yesterday" is a REGULAR session. A listed CME holiday (CME_HOLIDAYS) is
# skipped even when Globex printed a stub that day, and a session whose last regular bar is not 15:59 (13:14 on a listed
# early-close day) gives NA 'prior session incomplete' instead of a wrong level (it is NOT skipped). The 10-second point
# is NA '10-second data gap' when the capture lost 3+ minutes the master traded, inside the EMA's 600-bar memory.
#
# v1.2 (2026-10-02, owner correction): the four '200' lines are a plain MOVING AVERAGE (SMA, the mean of the last 200
# closes of that timeframe) by DEFAULT; ma='ema' keeps the v1.1 EMA. An SMA point is NA until its timeframe has a full
# 200-bar window up to the reference bar (an EMA still needs 600). The 10-second capture-gap rule looks back over the
# average's own memory: 200 10-second bars for the SMA, 600 for the EMA. Every record carries ma = 'sma' | 'ema'.
#
# TWO CODE PATHS, ON PURPOSE. score_trade() is the LITERAL path: it slices the bars to S, re-adjusts them for the
# contract rolls relative to THIS trade, and runs the spec one point at a time, so nothing at or after t_close can
# reach it. score_series() is the VECTORISED path: every 1-minute bar of a range in one pass (this is what the
# TradingView parity test and the algo-signal annotation use). tests/test_point_score.py checks that the two agree
# bar for bar on real data (skipped when augur_uploads is absent) and on synthetic bars (always runs).
#
# DATA (spec section 3; all times America/New_York, bars stamped at their START):
#   1m  = augur_uploads/NOADJ_<ROOT>_1m_ETH.csv (epoch seconds), plus the NinjaTrader 10-second capture resampled to
#         1m where the master has a >= 30 minute hole inside 2026-06-30..2026-08-06 (the summer hole) and after the
#         master's last bar. The capture (master_c279374a.csv ES / master_b1335b7e.csv NQ) is stamped at bar END, so
#         10 s is subtracted on load. MES reads ES bars, MNQ reads NQ bars.
#   ROLLS: the master is NON-adjusted. Bars are back-adjusted with the roll table (augur_engine/rolls.py, real
#         switches only) RELATIVE TO THE TRADE: adjusted(t) = raw(t) + sum(offsets of switches after t) -
#         sum(offsets of switches after t_close). Every comparison is shift-invariant, so the hit never depends on the
#         anchor, and the val / ref the record shows are real prices at the trade. A bar with a switch INSIDE it
#         is rebuilt the way rolls.back_adjust rebuilds it (open on the old contract, close on the new one, no wick).
#   5m / 30m = resampled from the adjusted 1m series; 10s = the capture, raw, NA before 2026-06-23 and NA within 48 h
#         after a real switch (the capture rolls about a day after the master).
#   The loaded history starts 2026-01-01 (speed): every EMA is seeded with the first close of the loaded history and
#         needs >= 600 bars of its own timeframe up to the reference bar, else the point is NA ("EMA warming up").
# Files are read from the repo's augur_uploads, else from the shared checkout (worktrees have none). Nothing here
# writes anywhere but the CSV / output path you name; Firestore (backfill) is read-only.
import argparse
import csv
import datetime as dt
import importlib.util
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'tools', 'data')
ET = 'America/New_York'
VERSION = 'ps1.2'

SHARED = os.path.join(os.path.expanduser('~'), 'OneDrive', 'Desktop', 'EDGE-LOG')
FILLS_CSV = os.path.join('C:' + os.sep, 'EdgeLog', 'fills.csv')
OUT_DIR = os.path.join('C:' + os.sep, 'EdgeLog', 'point_score')

ROOT_OF = {'MES': 'ES', 'ES': 'ES', 'MNQ': 'NQ', 'NQ': 'NQ'}
TICK = {'ES': 0.25, 'NQ': 0.25}
MASTER_1M = {'ES': 'NOADJ_ES_1m_ETH.csv', 'NQ': 'NOADJ_NQ_1m_ETH.csv'}
MASTER_10S = {'ES': 'master_c279374a.csv', 'NQ': 'master_b1335b7e.csv'}
HISTORY_FROM = '2026-01-01'          # loaded history (speed); every EMA is seeded with its first close
HOLE_FROM, HOLE_TO = '2026-06-30', '2026-08-06'      # the summer hole: the master has no bars, the capture does
HOLE_MIN_SECS = 30 * 60              # a master gap of >= 30 minutes inside the hole window is filled from the capture
TEN_SEC_FROM = '2026-06-23'
NEAR_ROLL_SECS = 48 * 3600           # the capture rolls about a day after the master: NA for 48 h after a switch
EMA_SPAN = 200
MA_LEN = 200                         # the moving average's length (SMA window / EMA span)
MIN_BARS = 600                       # EMA: bars of its own timeframe needed up to the reference bar
MA_TYPES = ('sma', 'ema')
DEFAULT_MA = 'sma'                   # v1.2: the owner's '200' lines are a simple moving average
RTH_OPEN, RTH_CLOSE = 9 * 60 + 30, 16 * 60          # regular session [09:30, 16:00) ET, in minutes of the day
WINDOW_OPEN = {'futures': 9 * 60 + 30, 'stock': 4 * 60}
MAX_SESSION_GAP_DAYS = 7
SESSION_LAST_MIN = RTH_CLOSE - 1     # a complete regular session ends with its 15:59 bar ...
EARLY_LAST_MIN = 13 * 60 + 14        # ... or, on a listed early-close day, with its 13:14 bar
GAP10_MIN_MINUTES = 3                # a capture gap: >= 3 master minutes with volume > 0 and no 10-second bar at all
ROLL_SKIP_SESSIONS = 15              # parity: sessions after a real switch whose 30m EMA still carries the roll gap

# CME equity-index holidays, spec v1.1 section 7 - THE ONE LIST (pine/POINT_SCORE_1_0.pine carries the same dates).
#   full : no regular session. Globex may print a short 09:30-13:00 stub; the stub is never "yesterday".
#   early: a regular session that ends with its 13:14 bar (the day after Thanksgiving, Christmas Eve ...).
# EXTEND IT EACH DECEMBER from the CME holiday calendar. A day missing from the list cannot give a wrong level: its
# stub fails the completeness rule (the last regular bar is not 15:59) and reads NA.
CME_HOLIDAYS = dict(
    full=('2025-01-01', '2025-01-09', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26', '2025-06-19',
          '2025-07-04', '2025-09-01', '2025-11-27', '2025-12-25',
          '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03',
          '2026-09-07', '2026-11-26', '2026-12-25',
          '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05',
          '2027-09-06', '2027-11-25', '2027-12-24'),
    early=('2025-07-03', '2025-11-28', '2025-12-24', '2026-11-27', '2026-12-24', '2027-11-26'),
)
HOLIDAY_ORD = np.array(sorted(int(np.datetime64(d, 'D').astype('int64')) for d in CME_HOLIDAYS['full']), dtype='int64')
EARLY_ORD = np.array(sorted(int(np.datetime64(d, 'D').astype('int64')) for d in CME_HOLIDAYS['early']), dtype='int64')
HOLIDAY_SET = set(int(x) for x in HOLIDAY_ORD)

# the nine points, in fixed order: key, label when long, label when short
POINTS = [
    ('ma200_10s', 'Above 200 EMA (10s)', 'Below 200 EMA (10s)'),
    ('ma200_1m', 'Above 200 EMA (1m)', 'Below 200 EMA (1m)'),
    ('ma200_5m', 'Above 200 EMA (5m)', 'Below 200 EMA (5m)'),
    ('ma200_30m', 'Above 200 EMA (30m)', 'Below 200 EMA (30m)'),
    ('y_low', "Above yesterday's low", "Below yesterday's low"),
    ('y_close', "Above yesterday's close", "Below yesterday's close"),
    ('y_high', "Above yesterday's high", "Below yesterday's high"),
    ('big_body', "Largest body since today's low", "Largest body since today's high"),
    ('big_vol', "Largest volume since today's low", "Largest volume since today's high"),
]
KEYS = [p[0] for p in POINTS]
TREND = ('d_trend', 'Daily trend up', 'Daily trend down')

NA_WARM = 'moving average warming up'
NA_NO10 = 'no 10-second data'
NA_ROLL = 'near a contract roll'
NA_NO10BAR = 'no 10-second bar in the signal minute'
NA_NOY = 'no regular session within 7 days before'
NA_WIN = "signal before today's window"
NA_NOVOL = 'no volume in the window'
NA_NOBAR = 'no 1-minute bar for the signal minute'
NA_PRE = 'before the loaded history'
NA_STOCK10 = 'no 10-second bars for stocks'
NA_NOSTOCK = 'no stock bars (Alpaca key not saved)'
NA_INCOMPLETE = 'prior session incomplete'
NA_GAP10 = '10-second data gap'
_REASONS = [None, NA_WARM, NA_NO10, NA_ROLL, NA_NO10BAR, NA_NOY, NA_WIN, NA_NOVOL, NA_NOBAR, NA_PRE, NA_STOCK10,
            NA_NOSTOCK, NA_INCOMPLETE, NA_GAP10]
_CODE = {r: i for i, r in enumerate(_REASONS)}


# ------------------------------------------------------------------ small helpers

def _load_rolls():
    """augur_engine/rolls.py loaded BY PATH: the package __init__ drags in the whole engine (1.6 s, numba)."""
    try:
        spec = importlib.util.spec_from_file_location('_ps_rolls', os.path.join(ROOT, 'augur_engine', 'rolls.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except Exception:
        from augur_engine import rolls as m      # pragma: no cover
        return m


rolls = _load_rolls()


def uploads_dir():
    """The augur_uploads folder that actually holds the masters: $EDGELOG_UPLOADS, else this checkout's, else the
    shared checkout's. A worktree can own an EMPTY augur_uploads (a test run creates augur_uploads/_context there), so
    a folder only counts when it has the NQ master in it."""
    cands = [d for d in (os.environ.get('EDGELOG_UPLOADS'), os.path.join(ROOT, 'augur_uploads'),
                         os.path.join(SHARED, 'augur_uploads')) if d]
    for d in cands:
        if os.path.exists(os.path.join(d, MASTER_1M['NQ'])):
            return d
    for d in cands:
        if os.path.isdir(d):
            return d
    return os.path.join(ROOT, 'augur_uploads')


def data_available(root='NQ'):
    d = uploads_dir()
    return os.path.exists(os.path.join(d, MASTER_1M[root]))


def _ema(x):
    """pandas ewm(span=200, adjust=False) == Pine's ta.ema: alpha 2/201, seeded with the first value."""
    x = np.asarray(x, dtype='float64')
    if len(x) == 0:
        return x.copy()
    return pd.Series(x).ewm(span=EMA_SPAN, adjust=False).mean().to_numpy()


def _ma_type(ma):
    m = str(ma or DEFAULT_MA).strip().lower()
    if m not in MA_TYPES:
        raise ValueError("ma must be 'sma' or 'ema' (got %r)" % ma)
    return m


def _ma(x, ma=DEFAULT_MA):
    """The point's moving average of x, element i using x[:i+1]: SMA = mean of the last 200 (Pine ta.sma; NaN until 200
    values), EMA = _ema."""
    x = np.asarray(x, dtype='float64')
    if _ma_type(ma) == 'ema':
        return _ema(x)
    if len(x) == 0:
        return x.copy()
    return pd.Series(x).rolling(MA_LEN, min_periods=MA_LEN).mean().to_numpy()


def _warm(ma=DEFAULT_MA):
    """Bars of its own timeframe a moving-average point needs up to the reference bar (and the 10-second
    capture-gap memory): 200 for the SMA (a full window), 600 for the EMA."""
    return MA_LEN if _ma_type(ma) == 'sma' else MIN_BARS


def _et_fields(t):
    """(ET calendar date as days since 1970-01-01, minute of the ET day) for epoch-second bar starts."""
    idx = pd.DatetimeIndex(pd.to_datetime(np.asarray(t, dtype='int64'), unit='s', utc=True)).tz_convert(ET)
    local = idx.tz_localize(None)
    dord = local.normalize().values.astype('datetime64[D]').astype('int64')
    mod = (local.hour * 60 + local.minute).to_numpy().astype('int64')
    return dord, mod


def _epoch(ts):
    """epoch seconds of a 'YYYY-MM-DD HH:MM[:SS]' ET string / ET-naive datetime / aware datetime."""
    if isinstance(ts, str):
        ts = pd.Timestamp(ts)
    elif not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(ET, ambiguous=False, nonexistent='shift_forward')
    return int(ts.tz_convert('UTC').timestamp())


def _idx_epoch(idx):
    """epoch seconds (int64 array) of a tz-aware DatetimeIndex / Series, whatever its time unit."""
    idx = pd.DatetimeIndex(idx).tz_convert('UTC')
    return ((idx - pd.Timestamp(0, tz='UTC')) // pd.Timedelta(seconds=1)).to_numpy().astype('int64')


def _et_str(epoch, fmt='%Y-%m-%d %H:%M'):
    return pd.Timestamp(int(epoch), unit='s', tz='UTC').tz_convert(ET).strftime(fmt)


def _bucketize(t, o, h, l, c, v, secs):
    """OHLCV of consecutive `secs`-second buckets (label left, closed left; ET hour offsets are whole, so epoch
    buckets line up with the ET clock). Returns (dict of bucket arrays, bucket id of every input bar)."""
    n = len(t)
    key = t // secs
    flag = np.ones(n, dtype=bool)
    flag[1:] = key[1:] != key[:-1]
    starts = np.flatnonzero(flag)
    ends = np.r_[starts[1:], n] - 1
    gid = np.cumsum(flag) - 1
    return dict(t=key[starts] * secs, o=o[starts], h=np.maximum.reduceat(h, starts),
                l=np.minimum.reduceat(l, starts), c=c[ends], v=np.add.reduceat(v, starts)), gid


def _shifts(t, tf, inst, off):
    """rolls.roll_map's arithmetic for switch arrays: (shift at the bar's open, shift at its close).
    shift = sum of the offsets of the switches still ahead of that instant."""
    if not len(inst):
        z = np.zeros(len(t))
        return z, z.copy()
    suf = np.zeros(len(off) + 1)
    suf[:-1] = np.cumsum(off[::-1])[::-1]
    so = suf[np.searchsorted(inst, t, side='right')]
    sc = suf[np.searchsorted(inst, t + tf, side='left')]
    return so, sc


def _near_roll(inst, tclose):
    """True where a real switch lies within 48 h before (or at) t_close. tclose: scalar or array."""
    tclose = np.asarray(tclose, dtype='int64')
    if not len(inst):
        return np.zeros(tclose.shape, dtype=bool)
    j = np.searchsorted(inst, tclose, side='right') - 1
    ok = j >= 0
    dtm = tclose - inst[np.clip(j, 0, None)]
    return ok & (dtm <= NEAR_ROLL_SECS)


def _complete(dates, last_min):
    """True where a regular session (date as a day ordinal) is complete: its last regular-session bar is the 15:59 bar,
    or the 13:14 bar on a listed early-close day. dates / last_min: scalars or arrays."""
    dates = np.asarray(dates)
    last_min = np.asarray(last_min)
    return (last_min == SESSION_LAST_MIN) | (np.isin(dates, EARLY_ORD) & (last_min == EARLY_LAST_MIN))


def _side(s):
    s = str(s).strip().upper()
    if s in ('LONG', 'L', 'BUY'):
        return 'LONG'
    if s in ('SHORT', 'S', 'SELL'):
        return 'SHORT'
    raise ValueError('side must be LONG or SHORT, got %r' % s)


def _r(x, nd=4):
    if x is None:
        return None
    x = float(x)
    return None if x != x else round(x, nd)


# ------------------------------------------------------------------ the bar store

class Bars:
    """One instrument's bars, ready to score: raw 1-minute OHLCV (start-stamped epoch seconds), optional 10-second
    closes, and the real contract switches. Everything derived (adjusted prices, EMAs, per-bar scores) is computed
    lazily and cached on the object, so scoring 60 trades loads each root once."""

    def __init__(self, t, o, h, l, c, v, root=None, asset='futures', from_cap=None, t10=None, c10=None,
                 switches=None, source='master'):
        order = np.argsort(np.asarray(t, dtype='int64'), kind='stable')
        self.t = np.asarray(t, dtype='int64')[order]
        self.o = np.asarray(o, dtype='float64')[order]
        self.h = np.asarray(h, dtype='float64')[order]
        self.l = np.asarray(l, dtype='float64')[order]
        self.c = np.asarray(c, dtype='float64')[order]
        self.v = np.asarray(v, dtype='float64')[order]
        self.from_cap = (np.zeros(len(self.t), dtype=bool) if from_cap is None
                         else np.asarray(from_cap, dtype=bool)[order])
        self.root = root
        self.asset = asset
        self.source = source
        t10 = np.zeros(0, dtype='int64') if t10 is None else np.asarray(t10, dtype='int64')
        c10 = np.zeros(0) if c10 is None else np.asarray(c10, dtype='float64')
        o10 = np.argsort(t10, kind='stable')
        self.t10, self.c10 = t10[o10], c10[o10]
        # real switches: (instant, offset, status, switch_et, kind). An in_bar switch happens strictly inside its
        # bar, so its instant is nudged one second later (rolls._switch_arrays does the same).
        if switches is None:
            rows = rolls.real_switches(root) if (asset == 'futures' and root) else []
            switches = [dict(inst=r['switch_sec'] + (1 if r['kind'] == 'in_bar' else 0), offset=r['offset_pts'],
                             status=r['status'], et=r['switch_et'], kind=r['kind']) for r in rows]
        sw = sorted(switches, key=lambda s: s['inst'])
        self.sw_rows = sw
        self.sw_inst = np.array([s['inst'] for s in sw], dtype='int64')
        self.sw_off = np.array([s['offset'] for s in sw], dtype='float64')
        self._fields_c = None
        self._adj_c = None
        self._full_c = {}

    @classmethod
    def from_frame(cls, df, **kw):
        """df: columns open/high/low/close/volume and an ET (or naive-ET) DatetimeIndex of bar STARTS, or a 'time'
        column of epoch seconds."""
        if 'time' in df.columns:
            t = df['time'].to_numpy(dtype='int64')
        else:
            idx = pd.DatetimeIndex(df.index)
            if idx.tz is None:
                idx = idx.tz_localize(ET, ambiguous=False, nonexistent='shift_forward')
            t = _idx_epoch(idx)
        return cls(t, df['open'], df['high'], df['low'], df['close'], df['volume'], **kw)

    def __len__(self):
        return len(self.t)

    # ---- cached pieces
    def fields(self):
        if self._fields_c is None:
            self._fields_c = _et_fields(self.t)
        return self._fields_c

    def adjusted(self):
        """Panama (newest segment real) adjusted 1m prices: (po, ph, pl, pc, sc) with sc = each bar's CLOSE shift,
        which is the anchor A of a trade whose signal bar is that bar. Real price at the trade = P - sc."""
        if self._adj_c is None:
            so, sc = _shifts(self.t, 60, self.sw_inst, self.sw_off)
            mixed = so != sc
            po = self.o + np.where(mixed, so, sc)
            pc = self.c + sc
            ph = np.where(mixed, np.maximum(po, pc), self.h + sc)
            pl = np.where(mixed, np.minimum(po, pc), self.l + sc)
            self._adj_c = tuple(np.round(a, 6) for a in (po, ph, pl, pc)) + (sc,)
        return self._adj_c

    def src_label(self, i, ten_s_used):
        if self.asset != 'futures':
            return 'alpaca1m'
        s = ('capture1m' if self.from_cap[i] else 'master1m')
        return s + ('+capture10s' if ten_s_used else '')

    # ---- the vectorised pass (every 1-minute bar at once)
    def full(self, side, ma=DEFAULT_MA):
        side, ma = _side(side), _ma_type(ma)
        if (side, ma) not in self._full_c:
            self._full_c[(side, ma)] = self._compute_full(side, ma)
        return self._full_c[(side, ma)]

    def _compute_full(self, side, ma=DEFAULT_MA):
        sg = 1.0 if side == 'LONG' else -1.0
        W = _warm(ma)
        n = len(self.t)
        t = self.t
        po, ph, pl, pc, A = self.adjusted()
        v = np.nan_to_num(self.v)
        dord, mod = self.fields()
        nan = np.full(n, np.nan)
        out = {}

        def mk():
            return dict(val=nan.copy(), ref=nan.copy(), hit=nan.copy(), na=np.zeros(n, dtype=np.int8))

        def put(d, hit, val, ref, na_arrays):
            """na_arrays: [(mask, code)] lowest priority first. Hit / val / ref are NaN where NA."""
            for m, code in na_arrays:
                d['na'][m] = code
            ok = d['na'] == 0
            d['hit'] = np.where(ok, np.asarray(hit, dtype='float64'), np.nan)
            d['val'] = np.where(ok, val, np.nan)
            d['ref'] = np.where(ok, ref, np.nan)

        idx = np.arange(n)
        # --- 10 second EMA (raw capture; NA before the capture, near a roll, without a bar in the minute)
        d = mk()
        if self.asset != 'futures':
            put(d, np.zeros(n), pc - A, nan, [(np.ones(n, dtype=bool), _CODE[NA_STOCK10])])
        elif len(self.t10) == 0:
            put(d, np.zeros(n), pc - A, nan, [(np.ones(n, dtype=bool), _CODE[NA_NO10])])
        else:
            ema10 = _ma(self.c10, ma)
            lo = np.searchsorted(self.t10, t, side='left')
            hi = np.searchsorted(self.t10, t + 60, side='left')
            ref = ema10[np.clip(hi - 1, 0, None)]
            # capture gap (v1.1): >= 3 one-minute bars that traded (volume > 0) but have no 10-second bar at all, from the
            # minute of the 600th-latest 10-second bar before t_close through the signal minute
            miss = (v > 0) & (hi <= lo)
            cs = np.r_[0, np.cumsum(miss)]
            j0 = np.searchsorted(t, self.t10[np.clip(hi - W, 0, None)] // 60 * 60, side='left')
            gap = (hi >= W) & ((cs[idx + 1] - cs[j0]) >= GAP10_MIN_MINUTES)
            put(d, sg * ((pc - A) - ref) > 0, pc - A, ref,          # the capture is raw: compare the REAL close
                [(hi < W, _CODE[NA_WARM]), (gap, _CODE[NA_GAP10]), (hi <= lo, _CODE[NA_NO10BAR]),
                 (_near_roll(self.sw_inst, t + 60), _CODE[NA_ROLL]), (t < self.t10[0], _CODE[NA_NO10])])
        out['ma200_10s'] = d
        # --- 1m EMA (S itself, so the EMA includes C)
        d = mk()
        ema1 = _ma(pc, ma)
        put(d, sg * (pc - ema1) > 0, pc - A, ema1 - A, [(idx + 1 < W, _CODE[NA_WARM])])
        out['ma200_1m'] = d
        # --- 5m / 30m EMA: the bar BEFORE the one containing S.start, by position in the resampled series
        for key, secs in (('ma200_5m', 300), ('ma200_30m', 1800)):
            d = mk()
            bk, gid = _bucketize(t, po, ph, pl, pc, v, secs)
            emab = _ma(bk['c'], ma)
            r = gid - 1
            ref = emab[np.clip(r, 0, None)]
            put(d, sg * (pc - ref) > 0, pc - A, ref - A, [((r < 0) | (r + 1 < W), _CODE[NA_WARM])])
            out[key] = d
        # --- yesterday's regular-session low / close / high (and the session before, for the trend point)
        # a listed CME holiday is never a regular session (v1.1), whatever Globex printed that day
        rth = (mod >= RTH_OPEN) & (mod < RTH_CLOSE)
        ri = np.flatnonzero(rth & ~np.isin(dord, HOLIDAY_ORD))
        rd = dord[ri]
        flag = np.ones(len(ri), dtype=bool)
        flag[1:] = rd[1:] != rd[:-1]
        st = np.flatnonzero(flag)
        en = np.r_[st[1:], len(ri)] - 1
        sdate = rd[st]
        if len(st):
            sH = np.maximum.reduceat(ph[ri], st)
            sL = np.minimum.reduceat(pl[ri], st)
            sC = pc[ri][en]
            sOK = _complete(sdate, mod[ri][en])                  # the session ran to its last regular bar (v1.1)
        else:
            sH = sL = sC = np.zeros(0)
            sOK = np.zeros(0, dtype=bool)
        k = np.searchsorted(sdate, dord, side='left')        # sessions dated strictly before the bar's date
        yi, yyi = k - 1, k - 2
        if len(st):
            yc, yyc = np.clip(yi, 0, None), np.clip(yyi, 0, None)
            okY = (yi >= 0) & ((dord - sdate[yc]) <= MAX_SESSION_GAP_DAYS)
            okYY = okY & (yyi >= 0) & ((sdate[yc] - sdate[yyc]) <= MAX_SESSION_GAP_DAYS)
            cY, cYY = sOK[yc], sOK[yyc]
        else:
            okY = okYY = cY = cYY = np.zeros(n, dtype=bool)
        for key, arr in (('y_low', sL), ('y_close', sC), ('y_high', sH)):
            d = mk()
            lvl = arr[np.clip(yi, 0, None)] if len(arr) else nan
            put(d, sg * (pc - lvl) > 0, pc - A, lvl - A,
                [(~okY, _CODE[NA_NOY]), (okY & ~cY, _CODE[NA_INCOMPLETE])])
            out[key] = d
        # --- largest body / volume since today's low (high): the window restarts at every new-or-equal extreme
        wopen = WINDOW_OPEN.get(self.asset, RTH_OPEN)
        wi = np.flatnonzero(mod >= wopen)
        d8, d9 = mk(), mk()
        body_s = sg * (pc - po)                                  # signed in the trade's direction (green for long)
        if len(wi):
            dd = dord[wi]
            first = np.ones(len(wi), dtype=bool)
            first[1:] = dd[1:] != dd[:-1]
            z = (pl if sg > 0 else -ph)[wi]
            cm = pd.Series(z).groupby(dd).cummin().to_numpy()
            prev = np.r_[np.inf, cm[:-1]]
            prev[first] = np.inf
            ev = z <= prev                                       # first bar of the day is always an event
            gk = np.cumsum(ev)
            absb = np.abs(pc - po)[wi]
            mb = pd.Series(absb).groupby(gk).cummax().to_numpy()
            mv = pd.Series(v[wi]).groupby(gk).cummax().to_numpy()
            bval, bref, bhit = nan.copy(), nan.copy(), nan.copy()
            bval[wi], bref[wi] = body_s[wi], mb
            bhit[wi] = ((body_s[wi] > 0) & (absb >= mb)).astype('float64')
            vval, vref, vhit = nan.copy(), nan.copy(), nan.copy()
            vval[wi], vref[wi] = v[wi], mv
            vhit[wi] = (v[wi] >= mv).astype('float64')
        else:
            bval = bref = bhit = vval = vref = vhit = nan
        inwin = np.zeros(n, dtype=bool)
        inwin[wi] = True
        put(d8, bhit, bval, bref, [(~inwin, _CODE[NA_WIN])])
        put(d9, vhit, vval, vref, [(~inwin, _CODE[NA_WIN]), (inwin & ~(np.nan_to_num(vref) > 0), _CODE[NA_NOVOL])])
        out['big_body'], out['big_vol'] = d8, d9
        # --- trend (separate): yesterday made a higher high AND a higher low than the session before
        d = mk()
        if len(st):
            yH, yL = sH[np.clip(yi, 0, None)], sL[np.clip(yi, 0, None)]
            yyH, yyL = sH[np.clip(yyi, 0, None)], sL[np.clip(yyi, 0, None)]
        else:
            yH = yL = yyH = yyL = nan
        # NA reason, in the literal path's order: no y -> y incomplete -> no yy -> yy incomplete
        put(d, (sg * (yH - yyH) > 0) & (sg * (yL - yyL) > 0), yH - A, yyH - A,
            [(~okY | (okY & cY & ~okYY), _CODE[NA_NOY]), ((okY & ~cY) | (okYY & cY & ~cYY), _CODE[NA_INCOMPLETE])])
        d['val2'] = np.where(d['na'] == 0, yL - A, np.nan)
        d['ref2'] = np.where(d['na'] == 0, yyL - A, np.nan)
        out['d_trend'] = d
        out['_ohlcv'] = dict(open=po - A, high=ph - A, low=pl - A, close=pc - A, volume=self.v)
        out['_ma'] = ma
        return out

    def find(self, s_start):
        """Index of the 1-minute bar starting at epoch s_start, or -1."""
        i = int(np.searchsorted(self.t, s_start, side='left'))
        return i if i < len(self.t) and self.t[i] == s_start else -1


# ------------------------------------------------------------------ loading (futures)

def _read_tail_csv(path, min_time):
    """Rows of a time-sorted master CSV with time >= min_time, reading only the file's tail (the masters are 300 MB
    back to 2010; 2026 is the last ~14 MB)."""
    size = os.path.getsize(path)
    with open(path, 'rb') as fh:
        head = fh.readline()
        names = head.decode('utf-8').strip().split(',')
        chunk = 24 * 1024 * 1024
        while True:
            start = max(len(head), size - chunk)
            fh.seek(start)
            if start > len(head):
                fh.readline()                                   # drop the partial line we landed in
            raw = fh.read()
            df = pd.read_csv(io.BytesIO(raw), names=names, header=None)
            if start <= len(head) or (len(df) and df['time'].iloc[0] <= min_time):
                break
            chunk *= 2
    df = df.dropna(subset=['time', 'open', 'high', 'low', 'close'])      # a writer may be mid-append
    df = df[df['time'] >= min_time]
    return df.drop_duplicates('time').sort_values('time').reset_index(drop=True)


_BARS_CACHE = {}


def load_bars(root, history_from=HISTORY_FROM, uploads=None, use_capture=True):
    """The scoring bars for one futures root ('NQ' or 'ES'), cached per process: NOADJ 1m master from
    `history_from`, the capture's 1m in the summer hole and after the master's end, and the 10-second capture."""
    root = ROOT_OF.get(str(root).upper(), str(root).upper())
    up = uploads or uploads_dir()
    key = (root, history_from, up, use_capture)
    if key in _BARS_CACHE:
        return _BARS_CACHE[key]
    min_t = _epoch(history_from)
    m = _read_tail_csv(os.path.join(up, MASTER_1M[root]), min_t)
    if len(m) and float(m['volume'].iloc[-1]) == 0:
        m = m.iloc[:-1]                                         # the last row is a partial bar
    tm = m['time'].to_numpy('int64')
    cols = ['open', 'high', 'low', 'close', 'volume']
    t10 = c10 = None
    add = None
    cap_path = os.path.join(up, MASTER_10S[root])
    if use_capture and os.path.exists(cap_path):
        cap = pd.read_csv(cap_path, usecols=['time', 'open', 'high', 'low', 'close', 'volume'])
        cap = cap.drop_duplicates('time').sort_values('time')
        cap['start'] = cap['time'] - 10                         # the capture is stamped at bar END
        cap = cap[cap['start'] >= min_t]
        t10, c10 = cap['start'].to_numpy('int64'), cap['close'].to_numpy('float64')
        g = cap.groupby(cap['start'] // 60 * 60)
        c1 = pd.DataFrame({'open': g['open'].first(), 'high': g['high'].max(), 'low': g['low'].min(),
                           'close': g['close'].last(), 'volume': g['volume'].sum(), 'last10': g['start'].max()})
        c1.index.name = 'time'
        c1 = c1.reset_index()
        if len(c1) and c1['last10'].iloc[-1] < c1['time'].iloc[-1] + 50:
            c1 = c1.iloc[:-1]                                   # the capture's final minute is incomplete
        ct = c1['time'].to_numpy('int64')
        if len(ct):
            ix = np.searchsorted(tm, ct, side='right')          # master bars at or before each capture minute
            in_master = (ix > 0) & (tm[np.clip(ix - 1, 0, None)] == ct)
            after_end = ix >= len(tm)
            nxt = tm[np.clip(ix, 0, len(tm) - 1)] if len(tm) else ct
            prv = tm[np.clip(ix - 1, 0, None)] if len(tm) else ct
            gap = (nxt - prv - 60) >= HOLE_MIN_SECS
            dct, _ = _et_fields(ct)
            d0 = np.datetime64(HOLE_FROM, 'D').astype('int64')
            d1 = np.datetime64(HOLE_TO, 'D').astype('int64')
            in_hole = gap & (dct >= d0) & (dct <= d1) & (ix > 0) & ~after_end
            take = ~in_master & (after_end | in_hole)
            add = c1[take]
    if add is not None and len(add):
        t = np.r_[tm, add['time'].to_numpy('int64')]
        o = np.r_[m['open'], add['open']]
        h = np.r_[m['high'], add['high']]
        l = np.r_[m['low'], add['low']]
        c = np.r_[m['close'], add['close']]
        v = np.r_[m['volume'], add['volume']]
        fc = np.r_[np.zeros(len(tm), dtype=bool), np.ones(len(add), dtype=bool)]
    else:
        t, o, h, l, c, v = tm, m['open'], m['high'], m['low'], m['close'], m['volume']
        fc = np.zeros(len(tm), dtype=bool)
    b = Bars(t, o, h, l, c, v, root=root, asset='futures', from_cap=fc, t10=t10, c10=c10, source='master1m')
    _BARS_CACHE[key] = b
    return b


# ------------------------------------------------------------------ loading (stocks: stub until the keys exist)

_STOCK_CACHE = {}


_ALPACA_MOD = []


def _alpaca():
    """(module, key, secret) when the staged Alpaca loader (tools/import_alpaca_stocks.py) imports AND keys exist
    (env ALPACA_API_KEY / ALPACA_SECRET_KEY, else its two config files), else None. Nothing is fetched here."""
    try:
        if not _ALPACA_MOD:
            spec = importlib.util.spec_from_file_location('_ps_alpaca', os.path.join(TOOLS, 'import_alpaca_stocks.py'))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            _ALPACA_MOD.append(m)
        m = _ALPACA_MOD[0]
        k, s = m.load_keys()
    except Exception:
        return None
    return (m, k, s) if (k and s) else None


def load_stock_bars(sym, date):
    """1-minute extended-hours bars for a stock (split-adjusted, Alpaca SIP) ending the day after `date`, or None when
    the loader cannot run (no keys saved). With no keys this NEVER touches the network."""
    a = _alpaca()
    if a is None:
        return None
    key = (sym, str(date)[:10])
    if key in _STOCK_CACHE:
        return _STOCK_CACHE[key]
    m, k, s = a
    d = pd.Timestamp(str(date)[:10])
    start = (d - pd.Timedelta(days=45)).strftime('%Y-%m-%dT00:00:00Z')
    # Alpaca's free plan needs `end` >= 15 minutes old: stop at the end of the day or 20 minutes ago, whichever is first
    end_ts = min(pd.Timestamp(d + pd.Timedelta(days=1), tz='UTC'), pd.Timestamp.now(tz='UTC') - pd.Timedelta(minutes=20))
    end = end_ts.strftime('%Y-%m-%dT%H:%M:%SZ')
    df = m.fetch_bars(sym, '1Min', start, end, k, s)
    b = None
    if df is not None and len(df):
        b = Bars(df['time'], df['open'], df['high'], df['low'], df['close'], df['volume'], root=sym, asset='stock',
                 source='alpaca1m')
    _STOCK_CACHE[key] = b
    return b


# ------------------------------------------------------------------ the record

def _label(k, side):
    for kk, lo, sh in POINTS:
        if kk == k:
            return lo if side == 'LONG' else sh
    return TREND[1] if side == 'LONG' else TREND[2]


def _pt(k, side, hit, val, ref, na, **extra):
    d = dict(k=k, label=_label(k, side), hit=hit, val=_r(val), ref=_r(ref), na_reason=na)
    if na is not None:
        d['hit'], d['val'], d['ref'] = None, None, None
    d.update(extra)
    return d


def _assemble(side, s_start, pts, trend, src, notes, ma=DEFAULT_MA):
    ma = _ma_type(ma)
    if ma == 'sma':                                             # the four moving-average labels name the average used
        for p in pts:
            if p['k'].startswith('ma200_'):
                p['label'] = p['label'].replace('EMA', 'SMA')
    total = sum(1 for p in pts if p['hit'] is True)
    mx = sum(1 for p in pts if p['hit'] is not None)
    return dict(v=VERSION, ma=ma, side=side, signal_bar=_et_str(s_start), tf='1m', tf_note='1-minute default',
                total=total, max=mx, na_count=9 - mx, points=pts, trend=trend, src=src, notes=notes)


def _all_na(side, s_start, reason, src='none', notes=None, ma=DEFAULT_MA):
    pts = [_pt(k, side, None, None, None, reason) for k in KEYS]
    tr = _pt('d_trend', side, None, None, None, reason)
    return _assemble(side, s_start, pts, tr, src, notes or [], ma)


# ------------------------------------------------------------------ the LITERAL path (one trade)

def _literal(bars, s_start, side, ma=DEFAULT_MA):
    """Score one signal bar exactly as the spec reads, using ONLY bars that start before t_close = s_start + 60.
    Returns (record, S) where S = the signal bar's real-price OHLCV (or None). ma: 'sma' (default) | 'ema'."""
    ma = _ma_type(ma)
    W = _warm(ma)
    sg = 1.0 if side == 'LONG' else -1.0
    notes = []
    t_close = s_start + 60
    n = int(np.searchsorted(bars.t, t_close, side='left'))     # bars that started before t_close: nothing later is read
    if len(bars) == 0 or s_start < bars.t[0]:
        return _all_na(side, s_start, NA_PRE, 'none', ['signal bar is before the loaded history'], ma), None
    if n == 0 or bars.t[n - 1] != s_start:
        return _all_na(side, s_start, NA_NOBAR, 'none', ['no 1-minute bar starts at the signal minute'], ma), None
    t = bars.t[:n]
    raw = [a[:n] for a in (bars.o, bars.h, bars.l, bars.c)]
    v = np.nan_to_num(bars.v[:n])
    # roll adjustment relative to THIS trade: raw + (sum of offsets after the bar) - (sum of offsets after t_close)
    so, sc = _shifts(t, 60, bars.sw_inst, bars.sw_off)
    A = sc[-1]                                                  # sum of the offsets of switches at or after t_close
    mixed = so != sc
    ao = raw[0] + np.where(mixed, so, sc) - A
    ac = raw[3] + sc - A
    ah = np.where(mixed, np.maximum(ao, ac), raw[1] + sc - A)
    al = np.where(mixed, np.minimum(ao, ac), raw[2] + sc - A)
    ao, ah, al, ac = (np.round(a, 6) for a in (ao, ah, al, ac))
    C, O, V = ac[-1], ao[-1], v[-1]
    S = dict(open=O, high=ah[-1], low=al[-1], close=C, volume=V)
    dord, mod = (a[:n] for a in bars.fields())
    dS, mS = dord[-1], mod[-1]
    pts = []

    def ema_pt(k, ema, count):
        if count < W:
            return _pt(k, side, None, None, None, NA_WARM)
        return _pt(k, side, bool(sg * (C - ema) > 0), C, ema, None)

    # 1. 10-second EMA (raw capture; the spec's C is the signal bar's close)
    if bars.asset != 'futures':
        pts.append(_pt('ma200_10s', side, None, None, None, NA_STOCK10))
    elif len(bars.t10) == 0 or s_start < bars.t10[0]:
        pts.append(_pt('ma200_10s', side, None, None, None, NA_NO10))
    elif bool(_near_roll(bars.sw_inst, t_close)):
        pts.append(_pt('ma200_10s', side, None, None, None, NA_ROLL))
    else:
        n10 = int(np.searchsorted(bars.t10, t_close, side='left'))
        if n10 == 0 or bars.t10[n10 - 1] < s_start:
            pts.append(_pt('ma200_10s', side, None, None, None, NA_NO10BAR))
        elif n10 < W:
            pts.append(_pt('ma200_10s', side, None, None, None, NA_WARM))
        else:
            # capture gap (v1.1): minutes that traded (volume > 0) with no 10-second bar at all, from the minute of the
            # W-th latest 10-second bar before t_close (the average's memory) through the signal minute
            j0 = int(np.searchsorted(t, int(bars.t10[n10 - W]) // 60 * 60, side='left'))
            t10 = bars.t10[:n10]
            has10 = np.searchsorted(t10, t[j0:] + 60, side='left') > np.searchsorted(t10, t[j0:], side='left')
            if int(((v[j0:] > 0) & ~has10).sum()) >= GAP10_MIN_MINUTES:
                pts.append(_pt('ma200_10s', side, None, None, None, NA_GAP10))
            else:
                pts.append(ema_pt('ma200_10s', _ma(bars.c10[:n10], ma)[-1], n10))
    # 2. 1-minute EMA
    pts.append(ema_pt('ma200_1m', _ma(ac, ma)[-1], n))
    # 3-4. 5m / 30m EMA: the bar BEFORE the one containing S.start
    for k, secs in (('ma200_5m', 300), ('ma200_30m', 1800)):
        bk, _ = _bucketize(t, ao, ah, al, ac, v, secs)
        nb = len(bk['t'])                                       # the last bucket contains S (partial, never read)
        if nb < 2:
            pts.append(_pt(k, side, None, None, None, NA_WARM))
        else:
            pts.append(ema_pt(k, _ma(bk['c'][:nb - 1], ma)[-1], nb - 1))
    # 5-7. yesterday's regular-session low / close / high (and the session before it, for the trend point)
    rth = (mod >= RTH_OPEN) & (mod < RTH_CLOSE)
    past = rth & (dord < dS)
    days = np.unique(dord[past & ~np.isin(dord, HOLIDAY_ORD)])      # a listed CME holiday is never a regular session (v1.1)
    yd = yyd = None
    if len(days) and dS - days[-1] <= MAX_SESSION_GAP_DAYS:
        yd = days[-1]
        if len(days) > 1 and yd - days[-2] <= MAX_SESSION_GAP_DAYS:
            yyd = days[-2]

    def sess(d):
        sel = past & (dord == d)
        return ah[sel].max(), al[sel].min(), ac[sel][-1]

    def complete(d):                                            # the session ran to its last regular bar (v1.1)
        return bool(_complete(d, mod[past & (dord == d)][-1]))

    if yd is None:
        for k in ('y_low', 'y_close', 'y_high'):
            pts.append(_pt(k, side, None, None, None, NA_NOY))
    elif not complete(yd):
        for k in ('y_low', 'y_close', 'y_high'):
            pts.append(_pt(k, side, None, None, None, NA_INCOMPLETE))
    else:
        yH, yL, yC = sess(yd)
        for k, lvl in (('y_low', yL), ('y_close', yC), ('y_high', yH)):
            pts.append(_pt(k, side, bool(sg * (C - lvl) > 0), C, lvl, None))
    # 8-9. largest body / volume since today's low (high)
    wopen = WINDOW_OPEN.get(bars.asset, RTH_OPEN)
    if mS < wopen:
        pts.append(_pt('big_body', side, None, None, None, NA_WIN))
        pts.append(_pt('big_vol', side, None, None, None, NA_WIN))
    else:
        wi = np.flatnonzero((dord == dS) & (mod >= wopen))      # today's window, through S (S is its last bar)
        z = (al if sg > 0 else -ah)[wi]
        j = int(np.flatnonzero(z == z.min())[-1])               # the LATEST bar holding the extreme
        win = wi[j:]
        maxb = float(np.max(np.abs(ac[win] - ao[win])))
        maxv = float(np.max(v[win]))
        body = sg * (C - O)
        pts.append(_pt('big_body', side, bool(body > 0 and abs(C - O) >= maxb), body, maxb, None))
        if maxv <= 0:
            pts.append(_pt('big_vol', side, None, None, None, NA_NOVOL))
        else:
            pts.append(_pt('big_vol', side, bool(V >= maxv), V, maxv, None))
    # 10. trend (separate)
    if yd is None:
        trend = _pt('d_trend', side, None, None, None, NA_NOY)
    elif not complete(yd):
        trend = _pt('d_trend', side, None, None, None, NA_INCOMPLETE)
    elif yyd is None:
        trend = _pt('d_trend', side, None, None, None, NA_NOY)
    elif not complete(yyd):
        trend = _pt('d_trend', side, None, None, None, NA_INCOMPLETE)
    else:
        yH, yL, _ = sess(yd)
        yyH, yyL, _ = sess(yyd)
        trend = _pt('d_trend', side, bool(sg * (yH - yyH) > 0 and sg * (yL - yyL) > 0), yH, yyH, None,
                    val2=_r(yL), ref2=_r(yyL))
    # notes: an estimated / unmeasured roll close to S
    if len(bars.sw_rows) and len(days):
        d3 = days[-3] if len(days) >= 3 else days[0]
        lo = _epoch(pd.Timestamp('1970-01-01') + pd.Timedelta(days=int(d3)))
        for r in bars.sw_rows:
            if not rolls.is_trustworthy(r) and lo <= r['inst'] <= t_close:
                notes.append('roll %s (status %s) is within 3 sessions before the signal bar' % (r['et'], r['status']))
    if bars.from_cap[n - 1]:
        notes.append('signal bar comes from the 10-second capture (the master has no bar there)')
    ten = pts[0]['hit'] is not None
    return _assemble(side, s_start, pts, trend, bars.src_label(n - 1, ten), notes, ma), S


# ------------------------------------------------------------------ public API

def _fill_epoch(fill):
    return _epoch(fill)


def signal_start(fill):
    """Epoch seconds of S.start for an entry fill: floor(fill, 1 min) - 1 min."""
    return (_fill_epoch(fill) // 60) * 60 - 60


def _bars_for(trade, bars):
    """(bars, root) for a trade dict. Returns (None, sym) when a stock has no bars (no Alpaca key)."""
    sym = str(trade['sym']).strip().upper()
    if bars is not None:
        return bars, sym
    if sym in ROOT_OF:
        return load_bars(ROOT_OF[sym]), ROOT_OF[sym]
    return load_stock_bars(sym, str(trade['fill'])[:10]), sym


def _score(trade, bars=None, ma=DEFAULT_MA):
    """(record, S): score_trade plus the signal bar's real-price OHLCV (None when it has none)."""
    tf = str(trade.get('tf') or '1m').strip().lower()
    if tf not in ('1m', '1', '1min'):
        raise ValueError('only the 1-minute signal bar is supported in ps1 (got %r)' % tf)
    side = _side(trade['side'])
    s_start = signal_start(trade['fill'])
    b, sym = _bars_for(trade, bars)
    if b is None:
        return _all_na(side, s_start, NA_NOSTOCK, 'none', ['no stock bars: the Alpaca key is not saved'], ma), None
    return _literal(b, s_start, side, ma)


def score_trade(trade, bars=None, ma=DEFAULT_MA):
    """The spec-section-4 record for one trade. trade = dict(sym, side 'LONG'/'SHORT', fill ET datetime or
    'YYYY-MM-DD HH:MM[:SS]', optional tf '1m'). bars: a Bars object (default: load the root's bars, cached).
    ma: 'sma' (default, v1.2) or 'ema' - the moving average of the four '200' points; the record says which (ma).
    Points that cannot be computed come back with hit None and an na_reason - never 0."""
    return _score(trade, bars, ma)[0]


def signal_bar_ohlc(trade, bars=None):
    """Real-price OHLCV of the signal bar (dict), or None - for stop candidates, never for scoring."""
    return _score(trade, bars)[1]


def score_series(root, side, start_date, end_date, bars=None, ma=DEFAULT_MA):
    """The same points for EVERY 1-minute bar with start in [start_date 00:00, end_date + 1 day) ET.
    Columns: open/high/low/close/volume (real at the bar), then per point <k>_val, <k>_ref, <k>_hit (1.0 / 0.0 /
    NaN = NA), <k>_na (reason or ''), for the nine keys and d_trend, then total, max, na_count, pct."""
    side = _side(side)
    b = bars if bars is not None else load_bars(ROOT_OF.get(str(root).upper(), root))
    f = b.full(side, ma)
    lo = np.searchsorted(b.t, _epoch(str(start_date)[:10]), side='left')
    nxt = (pd.Timestamp(str(end_date)[:10]) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')   # ET date, not 24 h (DST)
    hi = np.searchsorted(b.t, _epoch(nxt), side='left')
    sl = slice(int(lo), int(hi))
    idx = pd.DatetimeIndex(pd.to_datetime(b.t[sl], unit='s', utc=True)).tz_convert(ET)
    cols = {}
    for name, arr in f['_ohlcv'].items():
        cols[name] = np.asarray(arr)[sl]
    hits, nas = [], []
    for k in KEYS + ['d_trend']:
        d = f[k]
        cols[k + '_val'] = d['val'][sl]
        cols[k + '_ref'] = d['ref'][sl]
        cols[k + '_hit'] = d['hit'][sl]
        cols[k + '_na'] = np.array([_REASONS[c] or '' for c in d['na'][sl]], dtype=object)
        if k != 'd_trend':
            hits.append(d['hit'][sl])
    H = np.vstack(hits)
    cols['total'] = np.nansum(H, axis=0).astype(int)
    cols['max'] = (~np.isnan(H)).sum(axis=0).astype(int)
    cols['na_count'] = 9 - cols['max']
    with np.errstate(invalid='ignore', divide='ignore'):
        cols['pct'] = np.where(cols['max'] > 0, cols['total'] / np.maximum(cols['max'], 1), np.nan)
    cols['d_trend_val2'] = f['d_trend']['val2'][sl]
    cols['d_trend_ref2'] = f['d_trend']['ref2'][sl]
    return pd.DataFrame(cols, index=idx)


def format_record(rec, show_notes=True):
    """Plain-text breakdown of a record."""
    L = ['%s (%s)  %s  signal bar %s ET (%s)  src %s' % (rec['v'], rec.get('ma', 'ema').upper(), rec['side'], rec['signal_bar'], rec['tf_note'], rec['src']),
         'SCORE %d / %d%s' % (rec['total'], rec['max'], ('  (%d NA)' % rec['na_count']) if rec['na_count'] else '')]
    for p in rec['points'] + [rec['trend']]:
        tag = 'NA  ' if p['hit'] is None else ('HIT ' if p['hit'] else 'miss')
        extra = '' if p['hit'] is None else '  val %s  ref %s' % (p['val'], p['ref'])
        L.append('  %-4s %-36s%s%s' % (tag, p['label'] + ('  [not in the score]' if p['k'] == 'd_trend' else ''), extra,
                                     ('  - ' + p['na_reason']) if p['na_reason'] else ''))
    if show_notes:
        for n in rec.get('notes') or []:
            L.append('  note: ' + n)
    return '\n'.join(L)


# ------------------------------------------------------------------ backfill (scores only; never outcomes)

def _journal():
    d = json.load(io.open(os.path.join(DATA, 'setup_journal.json'), encoding='utf-8'))
    return {t['trade_id']: t for t in d['trades'] if t.get('asset', 'futures') == 'futures' and t.get('trade_id')}


def _hm(s):
    s = str(s or '')[:5]
    return s if len(s) == 5 and s[2] == ':' else None


def _minutes_between(hm_a, hm_b):
    a = int(hm_a[:2]) * 60 + int(hm_a[3:5])
    b = int(hm_b[:2]) * 60 + int(hm_b[3:5])
    return abs(a - b)


def load_fills(path=FILLS_CSV):
    """fills.csv rows: dict(time naive, root, action, qty, price, acct, exec_id)."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            try:
                inst = str(r['Instrument']).split()[0].upper()
                rows.append(dict(time=pd.Timestamp(r['Time']), root=inst, action=str(r['Action']).upper(),
                                 qty=int(float(r['Qty'])), price=float(r['Price']), acct=str(r.get('Account', '')),
                                 exec_id=r.get('ExecutionId')))
            except Exception:
                continue
    return rows


def match_fill(trade, fills, ref_hm):
    """The fills.csv row for this trade's ENTRY: same instrument root, side (BUY=LONG entry), price and quantity, on
    the trade's date. Its clock is read as UTC (-> ET); a few early rows were logged in Pacific time, so when the
    UTC reading disagrees with the trade's known entry minute by more than 2 minutes the Pacific reading is tried.
    Returns (ET timestamp or None, note)."""
    want = 'BUY' if trade['type'].upper() == 'LONG' else 'SELL'
    cands = []
    for r in fills:
        if r['root'] != trade['symbol'].upper() or r['action'] != want:
            continue
        if abs(r['price'] - float(trade['entry'])) > 1e-6 or r['qty'] != int(trade.get('size') or 1):
            continue
        for tz_name, tz in (('UTC', 'UTC'), ('Pacific', 'America/Los_Angeles')):
            et = r['time'].tz_localize(tz, ambiguous=False, nonexistent='shift_forward').tz_convert(ET)
            if et.strftime('%Y-%m-%d') != trade['date']:
                continue
            gap = _minutes_between(et.strftime('%H:%M'), ref_hm) if ref_hm else 0
            cands.append((tz_name != 'UTC', gap, et, tz_name, r['acct'].upper().startswith('DEMO')))
    ok = [c for c in cands if c[1] <= 2]
    if not ok:
        return None, ('fills.csv row(s) found but the clock disagrees with the known entry minute' if cands else
                      'no fills.csv row')
    ok.sort(key=lambda c: (c[4], c[0], c[1]))          # real account first, UTC reading first, then the closest minute
    et, tz_name = ok[0][2], ok[0][3]
    return et, ('fills.csv read as %s' % tz_name) + ('; %d candidates' % len(ok) if len(ok) > 1 else '')


def _hits_at(bars, date, hm, price):
    """score_day's rule: is the fill price inside the 1m bar at the logged minute (+-1 tick)?"""
    e = _epoch('%s %s' % (date, hm))
    i = bars.find(e)
    if i < 0:
        return False
    return bars.l[i] - 0.25 <= price <= bars.h[i] + 0.25


def resolve_fill(tr, jr, fills, bars):
    """(fill string ET, source, shift_min, note) per spec section 5: fills.csv, else the journal entry_time, else EL's
    entryTime (with the score_day Pacific/Central shift check when the fill price is not inside the logged minute)."""
    j_hm = _hm((jr or {}).get('entry_time'))
    el_hm = _hm(tr.get('entryTime'))
    et, note = match_fill(tr, fills, j_hm or el_hm)
    if et is not None:
        return et.strftime('%Y-%m-%d %H:%M:%S'), 'fills.csv', 0, note
    if j_hm:
        return '%s %s' % (tr['date'], j_hm), 'journal', 0, note
    if el_hm:
        shift = 0
        if bars is not None and not _hits_at(bars, tr['date'], el_hm, float(tr['entry'])):
            for m in (-180, -60, 180, 60):
                hm = (pd.Timestamp('%s %s' % (tr['date'], el_hm)) + pd.Timedelta(minutes=m)).strftime('%H:%M')
                if _hits_at(bars, tr['date'], hm, float(tr['entry'])):
                    shift = m
                    break
        hm = (pd.Timestamp('%s %s' % (tr['date'], el_hm)) + pd.Timedelta(minutes=shift)).strftime('%H:%M')
        return '%s %s' % (tr['date'], hm), 'el', shift, note
    return None, 'none', 0, note


def backfill(out, el_trades=None, fills_path=FILLS_CSV, quiet=False, ma=DEFAULT_MA):
    """One row per real futures trade in EDGE LOG (read-only): the score and the raw stop candidates. NO outcome
    (R, P&L, win/loss) is computed or printed here."""
    if el_trades is None:
        sys.path.insert(0, TOOLS)
        import setup_journal as sj
        el_trades = sj.load_el_trades()
    journal = _journal()
    fills = load_fills(fills_path)
    rows = []
    for tr in el_trades:
        if tr.get('assetType') != 'futures':
            continue
        root = ROOT_OF.get(str(tr['symbol']).upper())
        jr = journal.get(tr['_id'])
        bars = load_bars(root) if root else None
        fill, src, shift, note = resolve_fill(tr, jr, fills, bars)
        side = _side(tr['type'])
        row = dict(trade_id=tr['_id'], date=tr['date'], sym=tr['symbol'], side=side, qty=tr.get('size'),
                   entry=tr.get('entry'), exit=tr.get('exit'), fill_used=fill, fill_source=src, shift_min=shift,
                   fill_note=note)
        if fill is None or root is None:
            rec, S = _all_na(side, _epoch(tr['date'] + ' 00:00'), 'no entry time', 'none', None, ma), None
        else:
            rec, S = _score(dict(sym=tr['symbol'], side=side, fill=fill), bars, ma)
        row['signal_bar'] = rec['signal_bar']
        row['v'], row['ma'] = rec['v'], rec['ma']
        row['journal_signal_candle'] = (jr or {}).get('signal_candle')
        row['journal_signal_iv'] = (jr or {}).get('signal_iv') or (jr or {}).get('interval')
        jc = row['journal_signal_candle']
        row['signal_matches_journal'] = (None if not jc else int(rec['signal_bar'][11:16] == jc))
        row.update(total=rec['total'], max=rec['max'], na_count=rec['na_count'],
                   pct=(rec['total'] / rec['max']) if rec['max'] else None)
        for p in rec['points']:
            row[p['k'] + '_hit'] = None if p['hit'] is None else int(p['hit'])
            row[p['k'] + '_na'] = p['na_reason'] or ''
        tp = rec['trend']
        row['d_trend_hit'] = None if tp['hit'] is None else int(tp['hit'])
        row['d_trend_na'] = tp['na_reason'] or ''
        row['drawn_stop'] = ((jr or {}).get('drawn') or {}).get('stop')
        row['journal_stop'] = (jr or {}).get('stop')
        row['px_offset'] = (jr or {}).get('px_offset')
        row['sig_low'] = None if S is None else round(float(S['low']), 6)
        row['sig_high'] = None if S is None else round(float(S['high']), 6)
        row['src'] = rec['src']
        row['notes'] = ' | '.join(rec.get('notes') or [])
        rows.append(row)
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    df.to_csv(out, index=False)
    if not quiet:
        _print_backfill_summary(df, out)
    return df


def _print_backfill_summary(df, out):
    print('wrote %d trades -> %s' % (len(df), out))
    print('fill source:', df['fill_source'].value_counts().to_dict())
    print('signal bar equals the journal signal candle: %d of %d with a journal candle'
          % (int(df['signal_matches_journal'].fillna(0).sum()), int(df['signal_matches_journal'].notna().sum())))
    print('score (total of max):')
    for (tot, mx), k in df.groupby(['total', 'max']).size().sort_index(ascending=False).items():
        print('  %d/%d : %d trades' % (tot, mx, k))
    p = df['pct'].dropna()
    if len(p):
        print('pct  n=%d  min %.3f  q25 %.3f  median %.3f  q75 %.3f  max %.3f' % (
            len(p), p.min(), p.quantile(.25), p.median(), p.quantile(.75), p.max()))
    print('per point: hits / misses / NA')
    for k in KEYS + ['d_trend']:
        h = df[k + '_hit']
        print('  %-10s hit %2d  miss %2d  NA %2d   %s' % (
            k, int((h == 1).sum()), int((h == 0).sum()), int(h.isna().sum()),
            ', '.join('%s x%d' % (r, c) for r, c in df[k + '_na'][df[k + '_na'] != ''].value_counts().items())))


# ------------------------------------------------------------------ parity (TradingView export vs this file)

def _tv_times(col):
    if pd.api.types.is_numeric_dtype(col):
        x = col.astype('float64')
        if x.abs().max() > 1e11:
            x = x / 1000.0
        return x.round().astype('int64').to_numpy()
    ts = pd.to_datetime(col, utc=True, errors='coerce')
    if ts.isna().all():
        ts = pd.to_datetime(col, errors='coerce').dt.tz_localize(ET)
    return _idx_epoch(pd.DatetimeIndex(ts))


def _prev_sessions(d, k):
    """The k latest EXPECTED regular sessions before the day ordinal d: weekdays that are not listed CME holidays."""
    out, x = [], int(d)
    while len(out) < k:
        x -= 1
        if np.datetime64(x, 'D').astype(dt.date).weekday() >= 5 or x in HOLIDAY_SET:
            continue
        out.append(x)
    return out


def parity(path, root='NQ', skip_sessions=ROLL_SKIP_SESSIONS, max_list=40, bars=None, ma=DEFAULT_MA):
    df = pd.read_csv(path)
    low = {str(c).strip().lower().replace('"', ''): c for c in df.columns}
    tcol = low.get('time') or low.get('datetime') or df.columns[0]
    t = _tv_times(df[tcol])
    bars = bars if bars is not None else load_bars(root)
    tick = TICK.get(ROOT_OF.get(root, root), 0.25)
    dord, mod = _et_fields(t)
    rth = (mod >= RTH_OPEN) & (mod < RTH_CLOSE)
    # skip the switch day and the `skip_sessions` regular sessions after it (v1.1: 15). On an unadjusted TradingView chart
    # the 30-minute EMA carries the roll gap for about two weeks, and TradingView rolls a few days after we do.
    # sess_days = OUR regular sessions: dates with regular-session bars, listed holidays (stubs) excluded.
    f_d, f_m = bars.fields()
    sess_days = np.unique(f_d[(f_m >= RTH_OPEN) & (f_m < RTH_CLOSE) & ~np.isin(f_d, HOLIDAY_ORD)])
    skip = np.zeros(len(t), dtype=bool)
    for r in bars.sw_rows:
        d0 = int(_et_fields(np.array([r['inst']]))[0][0])
        after = sess_days[sess_days > d0][:skip_sessions]
        bad = set([d0]) | set(int(x) for x in after)
        skip |= np.isin(dord, list(bad))
    # ...and a session whose "yesterday" or the session before it is a weekday our master has NO regular-session bars for
    # that is not a listed holiday (a data hole): TradingView may have that session, so the two can differ. A LISTED
    # holiday is not skipped: both implementations carry the same list (spec section 7), so the session after a holiday
    # is exactly what this test should measure.
    sdset = set(int(x) for x in sess_days)
    n_hole = 0
    for d in np.unique(dord):
        if sess_days.size and any(p not in sdset and p > sess_days[0] for p in _prev_sessions(int(d), 2)):
            skip |= (dord == d)
            n_hole += 1
    use = rth & ~skip
    d_from = _et_str(int(t.min()), '%Y-%m-%d')
    d_to = _et_str(int(t.max()), '%Y-%m-%d')
    print('parity: %s  %d export bars, %d in the regular session outside the roll window  (%s .. %s)' % (
        os.path.basename(path), len(t), int(use.sum()), d_from, d_to))
    print('  roll window skipped: the switch day plus %d regular sessions after each of the %d real switches; '
          '%d session(s) after a data hole skipped; listed CME holidays are NOT skipped (both sides skip them)'
          % (skip_sessions, len(bars.sw_rows), n_hole))
    tot_both = tot_agree = 0
    bad_all = []
    for sd, sname in (('LONG', 'L'), ('SHORT', 'S')):
        ser = score_series(root, sd, d_from, d_to, bars=bars, ma=ma)
        epoch = _idx_epoch(ser.index)
        for k in KEYS + ['d_trend']:
            names = [sname + ' ' + k] + ([sname + ' trend'] if k == 'd_trend' else [])
            col = next((low[n.lower()] for n in names if n.lower() in low), None)
            if col is None:
                print('  %s %-10s column not in the export' % (sd[0], k))
                continue
            tv = pd.to_numeric(df[col], errors='coerce').to_numpy()
            ti = np.flatnonzero(use)
            si = np.searchsorted(epoch, t[ti])                 # epoch is sorted ascending
            ok = (si < len(epoch)) & (epoch[np.clip(si, 0, len(epoch) - 1)] == t[ti])
            ti, si = ti[ok], si[ok]
            tvv = tv[ti]
            elh = ser[k + '_hit'].to_numpy()[si]
            both = ~np.isnan(tvv) & ~np.isnan(elh)
            agree = both & (tvv == elh)
            dis = both & ~agree
            na_tv = int(np.isnan(tvv).sum())
            na_el = int(np.isnan(elh).sum())
            tot_both += int(both.sum())
            tot_agree += int(agree.sum())
            print('  %s %-10s compared %5d  agree %5d (%6.2f%%)  TV NA %4d  EL NA %4d' % (
                sd[0], k, int(both.sum()), int(agree.sum()), 100.0 * agree.sum() / max(both.sum(), 1), na_tv, na_el))
            for q in np.flatnonzero(dis):
                v_, r_ = ser[k + '_val'].to_numpy()[si[q]], ser[k + '_ref'].to_numpy()[si[q]]
                if k == 'big_vol':
                    kind = 'volume tie' if v_ == r_ else 'volume %+.0f' % (v_ - r_)
                    within = v_ == r_
                else:
                    ticks = abs(v_ - r_) / tick
                    kind = '%.2f ticks from the threshold' % ticks
                    within = ticks <= 1.0
                bad_all.append((sd[0], k, _et_str(t[ti[q]]), 'TV %d / EL %d' % (tvv[q], elh[q]), kind, within))
    pct = 100.0 * tot_agree / max(tot_both, 1)
    far = [b for b in bad_all if not b[5]]
    print('overall: %d of %d bar-points agree (%.2f%%); %d disagreements, %d beyond 1 tick / not a volume tie' % (
        tot_agree, tot_both, pct, len(bad_all), len(far)))
    for b in bad_all[:max_list]:
        print('    %s %-10s %s  %s  %s%s' % (b[0], b[1], b[2], b[3], b[4], '' if b[5] else '   <-- BEYOND 1 TICK'))
    if len(bad_all) > max_list:
        print('    ... %d more' % (len(bad_all) - max_list))
    verdict = pct >= 98.0 and not far
    print('PARITY %s (pass: >= 98%% agree where both sides are non-NA, every disagreement within 1 tick or a volume tie)'
          % ('PASS' if verdict else 'FAIL'))
    return verdict


# ------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description='the owner\'s point score (spec ps1.2)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('trade', help='score one trade')
    a.add_argument('--sym', required=True)
    a.add_argument('--side', required=True)
    a.add_argument('--fill', required=True, help='ET "YYYY-MM-DD HH:MM[:SS]"')
    a.add_argument('--json', action='store_true')
    a.add_argument('--ma', default=DEFAULT_MA, choices=MA_TYPES)
    s = sub.add_parser('series', help='every 1-minute bar of a range')
    s.add_argument('--root', required=True)
    s.add_argument('--side', required=True)
    s.add_argument('--from', dest='d0', required=True)
    s.add_argument('--to', dest='d1', required=True)
    s.add_argument('--out')
    s.add_argument('--ma', default=DEFAULT_MA, choices=MA_TYPES)
    b = sub.add_parser('backfill', help='scores only, every real futures trade in EL (read-only)')
    b.add_argument('--out', default=os.path.join(OUT_DIR, 'backfill_scores.csv'))
    b.add_argument('--fills', default=FILLS_CSV)
    b.add_argument('--ma', default=DEFAULT_MA, choices=MA_TYPES)
    p = sub.add_parser('parity', help='TradingView "Export chart data" CSV vs this implementation')
    p.add_argument('csv')
    p.add_argument('--root', default='NQ')
    p.add_argument('--ma', default=DEFAULT_MA, choices=MA_TYPES)
    args = ap.parse_args(argv)
    if args.cmd == 'trade':
        rec = score_trade(dict(sym=args.sym, side=args.side, fill=args.fill), ma=args.ma)
        print(json.dumps(rec, indent=1) if args.json else format_record(rec))
    elif args.cmd == 'series':
        ser = score_series(args.root, args.side, args.d0, args.d1, ma=args.ma)
        if args.out:
            ser.to_csv(args.out)
            print('wrote %d bars -> %s' % (len(ser), args.out))
        else:
            cols = ['close', 'total', 'max'] + [k + '_hit' for k in KEYS]
            print(ser[cols].to_string())
    elif args.cmd == 'backfill':
        t0 = dt.datetime.now()
        backfill(args.out, fills_path=args.fills, ma=args.ma)
        print('backfill runtime %.1f s' % (dt.datetime.now() - t0).total_seconds())
    else:
        sys.exit(0 if parity(args.csv, args.root, ma=args.ma) else 1)


if __name__ == '__main__':
    main()
