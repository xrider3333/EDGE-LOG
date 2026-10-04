"""POINT SCORE (spec v1.2 `ps1.2`, docs/POINT_SCORE_SPEC.md): tools/point_score.py, the reference implementation.

Two kinds of test, both against the SPEC, never against the code's own opinion:

  1. SYNTHETIC bars - run everywhere, CI included, no data files. Every rule in the spec that can go
     quietly wrong has a case here: the signal-bar rule, no look-ahead, the since-low window tie rule, the green
     candle, the 5m / 30m reference bar, yesterday's levels across weekends / holidays / half days, the
     600-bar warm-up, NA never being 0, the long / short mirror, the trade-relative roll adjustment (checked against
     a brute-force reading of the spec formula) and the 10-second rules. v1.1 (review 2026-09-30): listed CME holidays
     are never "yesterday", an incomplete prior session reads NA (never a wrong level), a capture gap inside the 10s
     EMA's memory reads NA, and the parity test skips 15 sessions after a roll but not the session after a holiday.
  2. DATA-BACKED - skipped when augur_uploads is absent (it is untracked): the owner's worked example
     (2026-09-30 09:32:21 MNQ LONG = 9 of 9 on the 09:31 bar), and score_series == score_trade on 200 random bars.

score_trade() is the literal per-trade path and score_series() the vectorised path; the agreement test is what
lets the Pine port and the TradingView parity test lean on score_series.
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load():
    spec = importlib.util.spec_from_file_location('point_score', os.path.join(ROOT, 'tools', 'point_score.py'))
    m = importlib.util.module_from_spec(spec)
    sys.modules['point_score'] = m
    spec.loader.exec_module(m)
    return m


ps = _load()
ET = ps.ET


# ------------------------------------------------------------------ synthetic bars

def _minutes(first_day, n_days):
    """ET-naive minute stamps of 24-hour futures sessions for n_days weekdays from first_day: each session runs
    18:00 of the day before to 16:59 of its own date (17:00-17:59 is the daily break; Monday's starts Sunday 18:00)."""
    out = []
    for d in pd.bdate_range(first_day, periods=n_days):
        a = pd.Timestamp(d) - pd.Timedelta(hours=6)              # 18:00 the evening before
        b = pd.Timestamp(d) + pd.Timedelta(hours=17)             # 17:00 of the date (exclusive)
        out.append(pd.date_range(a, b, freq='1min', inclusive='left'))
    return pd.DatetimeIndex(np.concatenate([o.values for o in out]))


def walk(first_day='2026-01-05', n_days=30, seed=0, p0=20000.0):
    """A random-walk 1m OHLCV frame on the quarter-point grid, 24-hour sessions."""
    idx = _minutes(first_day, n_days)
    n = len(idx)
    rng = np.random.default_rng(seed)
    c = p0 + np.cumsum(np.round(rng.normal(0, 4, n))) * 0.25
    o = np.r_[p0, c[:-1]]
    h = np.maximum(o, c) + np.round(np.abs(rng.normal(0, 3, n))) * 0.25
    l = np.minimum(o, c) - np.round(np.abs(rng.normal(0, 3, n))) * 0.25
    v = rng.integers(50, 3000, n).astype(float)
    return pd.DataFrame(dict(open=o, high=h, low=l, close=c, volume=v), index=idx)


def ten_sec(df, from_ts, seed=1):
    """10-second bar starts/closes for every minute of df from from_ts on: six bars per minute whose last close is
    the minute's close (the capture agrees with the master)."""
    rng = np.random.default_rng(seed)
    sub = df[df.index >= pd.Timestamp(from_ts)]
    t0 = ps._idx_epoch(sub.index.tz_localize(ET, ambiguous=False, nonexistent='shift_forward'))
    t = (t0[:, None] + np.arange(6)[None, :] * 10).ravel()
    c = np.repeat(sub['close'].to_numpy(), 6).astype(float)
    mid = np.round(rng.normal(0, 2, len(c))) * 0.25
    mid.reshape(-1, 6)[:, 5] = 0.0
    return t, c + mid


def bars_of(df, **kw):
    kw.setdefault('switches', [])
    return ps.Bars.from_frame(df, **kw)


def hand(rows):
    """rows: (stamp, o, h, l, c, v) -> frame. Bars stamped at their START, ET."""
    df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop('ts')))
    return df


def rec_of(b, fill, side='LONG', sym='NQ', ma=ps.DEFAULT_MA):
    return ps.score_trade(dict(sym=sym, side=side, fill=fill), bars=b, ma=ma)


def ma_of(series, ma):
    """The independent reference moving average: SMA = pandas rolling(200).mean(), EMA = ewm(span 200, adjust False)."""
    series = pd.Series(series)
    return series.rolling(200).mean() if ma == 'sma' else series.ewm(span=200, adjust=False).mean()


def pt(rec, k):
    return next(p for p in rec['points'] if p['k'] == k)


def same(a, b):
    return json.dumps(a, sort_keys=True, default=float) == json.dumps(b, sort_keys=True, default=float)


@pytest.fixture(scope='module')
def long_series():
    df = walk(n_days=30, seed=3)
    return df, bars_of(df)


# ------------------------------------------------------------------ the signal bar

def test_signal_bar_rule_seconds_minute_only_and_boundary(long_series):
    df, b = long_series
    day = '2026-02-10'
    for fill in (day + ' 09:32:21', day + ' 09:32:00', day + ' 09:32', day + ' 09:32:59'):
        assert rec_of(b, fill)['signal_bar'] == day + ' 09:31'
    assert rec_of(b, day + ' 09:31:59')['signal_bar'] == day + ' 09:30'
    assert rec_of(b, pd.Timestamp(day + ' 09:32:21'))['signal_bar'] == day + ' 09:31'
    assert rec_of(b, pd.Timestamp(day + ' 14:32:21', tz='UTC').tz_convert(ET))['signal_bar'] == day + ' 09:31'


def test_signal_bar_uses_that_bars_close_open_volume(long_series):
    df, b = long_series
    row = df.loc['2026-02-10 09:31']
    p = pt(rec_of(b, '2026-02-10 09:32:21'), 'ma200_1m')
    assert p['val'] == pytest.approx(row['close'])
    body = pt(rec_of(b, '2026-02-10 09:32:21'), 'big_body')
    assert body['val'] == pytest.approx(row['close'] - row['open'])
    assert pt(rec_of(b, '2026-02-10 09:32:21'), 'big_vol')['val'] == row['volume']


def test_only_1m_is_supported(long_series):
    _, b = long_series
    with pytest.raises(ValueError):
        ps.score_trade(dict(sym='NQ', side='LONG', fill='2026-02-10 09:32', tf='5m'), bars=b)
    assert ps.score_trade(dict(sym='NQ', side='LONG', fill='2026-02-10 09:32', tf='1m'), bars=b)['tf'] == '1m'


def test_record_shape_is_the_agreed_contract(long_series):
    _, b = long_series
    r = rec_of(b, '2026-02-10 09:32:21')
    assert r['v'] == 'ps1.2' and r['ma'] == 'sma' and r['side'] == 'LONG' and r['tf'] == '1m' and r['tf_note'] == '1-minute default'
    assert [p['k'] for p in r['points']] == ['ma200_10s', 'ma200_1m', 'ma200_5m', 'ma200_30m', 'y_low', 'y_close',
                                             'y_high', 'big_body', 'big_vol']
    assert r['trend']['k'] == 'd_trend'
    for p in r['points'] + [r['trend']]:
        assert set(['k', 'label', 'hit', 'val', 'ref', 'na_reason']) <= set(p)
    assert r['points'][0]['label'] == 'Above 200 SMA (10s)'
    assert r['points'][4]['label'] == "Above yesterday's low"
    assert r['points'][7]['label'] == "Largest body since today's low"
    s = rec_of(b, '2026-02-10 09:32:21', side='SHORT')
    assert s['points'][0]['label'] == 'Below 200 SMA (10s)'
    e = rec_of(b, '2026-02-10 09:32:21', ma='ema')
    assert e['ma'] == 'ema' and e['points'][3]['label'] == 'Above 200 EMA (30m)'
    with pytest.raises(ValueError):
        rec_of(b, '2026-02-10 09:32:21', ma='wma')
    assert s['points'][7]['label'] == "Largest body since today's high"
    assert s['points'][8]['label'] == "Largest volume since today's high"
    assert r['total'] == sum(1 for p in r['points'] if p['hit'] is True)
    assert r['max'] == sum(1 for p in r['points'] if p['hit'] is not None)
    assert r['na_count'] == 9 - r['max']


# ------------------------------------------------------------------ no look-ahead

def _mutate_after(b, i, seed=9):
    """A copy of the bars where every 1m bar after index i (start >= t_close) and every 10s bar at or after t_close
    is garbage."""
    rng = np.random.default_rng(seed)
    t_close = b.t[i] + 60
    o, h, l, c, v = (a.copy() for a in (b.o, b.h, b.l, b.c, b.v))
    junk = rng.uniform(-5000, 5000, len(b.t))
    for a in (o, h, l, c):
        a[i + 1:] = a[i + 1:] + junk[i + 1:]
    v[i + 1:] = v[i + 1:] * 50 + 1e6
    c10 = b.c10.copy()
    m = b.t10 >= t_close
    c10[m] = c10[m] + 4000.0
    return ps.Bars(b.t, o, h, l, c, v, root=b.root, t10=b.t10, c10=c10, switches=[])


def test_no_lookahead_literal_path():
    df = walk(n_days=30, seed=4)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    b = bars_of(df, t10=t10, c10=c10)
    for side in ('LONG', 'SHORT'):
        for hm in ('09:31', '10:04', '12:30', '15:59', '03:10'):
            s_start = ps._epoch('2026-02-10 ' + hm)
            i = b.find(s_start)
            assert i > 0
            fill = pd.Timestamp('2026-02-10 ' + hm) + pd.Timedelta(seconds=75)
            a = ps.score_trade(dict(sym='NQ', side=side, fill=fill), bars=b)
            m = ps.score_trade(dict(sym='NQ', side=side, fill=fill), bars=_mutate_after(b, i))
            assert same(a, m), (side, hm)


def test_no_lookahead_vectorised_path():
    df = walk(n_days=30, seed=5)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    b = bars_of(df, t10=t10, c10=c10)
    i = b.find(ps._epoch('2026-02-10 11:07'))
    b2 = _mutate_after(b, i)
    for side in ('LONG', 'SHORT'):
        f1, f2 = b.full(side), b2.full(side)
        for k in ps.KEYS + ['d_trend']:
            for field in ('val', 'ref', 'hit', 'na'):
                assert np.array_equal(f1[k][field][:i + 1], f2[k][field][:i + 1], equal_nan=True), (side, k, field)


# ------------------------------------------------------------------ mirror (invert the prices)

def _invert(df, K=40000.0):
    out = df.copy()
    out['open'], out['close'] = K - df['open'], K - df['close']
    out['high'], out['low'] = K - df['low'], K - df['high']
    return out


@pytest.mark.parametrize('seed', [11, 12, 13])
def test_long_short_mirror(seed):
    df = walk(n_days=30, seed=seed)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    K = 40000.0
    b = bars_of(df, t10=t10, c10=c10)
    bi = bars_of(_invert(df, K), t10=t10, c10=K - c10)
    swap = dict(y_low='y_high', y_high='y_low')                 # "above yesterday's low" mirrors "below yesterday's high"
    for hm in ('09:31', '09:30', '10:44', '13:13', '15:58'):
        fill = pd.Timestamp('2026-02-11 ' + hm) + pd.Timedelta(seconds=30)
        a = ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=b)
        m = ps.score_trade(dict(sym='NQ', side='SHORT', fill=fill), bars=bi)
        assert a['total'] == m['total'] and a['max'] == m['max']
        for p in a['points']:
            q = pt(m, swap.get(p['k'], p['k']))
            assert p['hit'] == q['hit'], (hm, p['k'])
        assert a['trend']['hit'] == m['trend']['hit']
    # the vectorised path mirrors too
    fa, fm = b.full('LONG'), bi.full('SHORT')
    for k in ps.KEYS:
        assert np.array_equal(fa[k]['hit'], fm[swap.get(k, k)]['hit'], equal_nan=True), k


# ------------------------------------------------------------------ NA is never 0

def test_na_is_never_zero_and_max_drops():
    # a short history: every EMA is warming up, but the day points still work
    df = walk(first_day='2026-02-09', n_days=3, seed=2)
    b = bars_of(df)
    r = rec_of(b, '2026-02-11 10:15:30')
    for k in ('ma200_10s', 'ma200_30m'):
        p = pt(r, k)
        assert p['hit'] is None and p['na_reason'] and p['val'] is None
    assert pt(r, 'ma200_10s')['na_reason'] == ps.NA_NO10
    assert pt(r, 'ma200_30m')['na_reason'] == ps.NA_WARM
    assert r['max'] == 9 - r['na_count'] and r['na_count'] >= 2
    assert r['total'] <= r['max']
    # NA points are in neither the hit count nor the maximum
    assert r['total'] == sum(1 for p in r['points'] if p['hit'] is True)


def test_signal_before_the_window_makes_points_8_and_9_na():
    df = walk(n_days=30, seed=6)
    b = bars_of(df)
    r = rec_of(b, '2026-02-10 08:45:10')                        # S = 08:44, before 09:30
    assert pt(r, 'big_body')['hit'] is None and pt(r, 'big_body')['na_reason'] == ps.NA_WIN
    assert pt(r, 'big_vol')['hit'] is None and pt(r, 'big_vol')['na_reason'] == ps.NA_WIN
    assert r['na_count'] >= 3                                   # the two window points + the 10s point (no capture)
    r2 = rec_of(b, '2026-02-10 09:31:05')                       # S = 09:30: the first bar of the window
    assert pt(r2, 'big_body')['na_reason'] is None and pt(r2, 'big_body')['hit'] is not None
    r3 = rec_of(b, '2026-02-10 09:30:05')                       # S = 09:29: still before
    assert pt(r3, 'big_body')['na_reason'] == ps.NA_WIN


def test_no_bar_at_the_signal_minute_is_all_na(long_series):
    _, b = long_series
    r = rec_of(b, '2026-02-10 17:30:10')                        # inside the 17:00-18:00 break
    assert r['total'] == 0 and r['max'] == 0 and r['na_count'] == 9
    assert all(p['hit'] is None and p['na_reason'] == ps.NA_NOBAR for p in r['points'])
    r = rec_of(b, '2025-12-01 10:00:10')
    assert r['max'] == 0 and r['points'][0]['na_reason'] == ps.NA_PRE


def test_volume_all_zero_window_is_na_not_zero():
    rows = [('2026-02-10 09:30', 100, 101, 99, 100.5, 0), ('2026-02-10 09:31', 100.5, 102, 100, 101.5, 0),
            ('2026-02-10 09:32', 101.5, 103, 101, 102.5, 0)]
    b = bars_of(hand(rows))
    r = rec_of(b, '2026-02-10 09:33:05')
    assert pt(r, 'big_vol')['hit'] is None and pt(r, 'big_vol')['na_reason'] == ps.NA_NOVOL
    assert pt(r, 'big_body')['hit'] is True


# ------------------------------------------------------------------ the since-low window

def _day_rows(date, specs, start='09:30'):
    """specs: list of (o, h, l, c, v); one bar per minute from `start`."""
    t = pd.Timestamp('%s %s' % (date, start))
    return [((t + pd.Timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M'),) + tuple(s) for i, s in enumerate(specs)]


def test_since_low_window_tie_restarts_at_the_later_bar():
    # B0 has the biggest body (5) and the day's low 100; B1 ties the low, so the window restarts at B1.
    # S (B2) has body 3: larger than B1 (2), smaller than B0 (5). Tie rule -> window = B1..S -> HIT.
    rows = _day_rows('2026-02-10', [(100, 106, 100, 105, 500), (105, 105.5, 100, 102, 300), (102, 106, 102, 105, 400),
                                    (105, 106, 104.5, 105.5, 50)])
    b = bars_of(hand(rows))
    r = rec_of(b, '2026-02-10 09:33:10')                        # S = 09:32 (third bar)
    assert r['signal_bar'] == '2026-02-10 09:32'
    body = pt(r, 'big_body')
    assert body['hit'] is True and body['ref'] == 3.0 and body['val'] == 3.0
    # without the tie (B1's low one tick higher) the window starts at B0 and the same bar misses
    rows2 = _day_rows('2026-02-10', [(100, 106, 100, 105, 500), (105, 105.5, 100.25, 102, 300), (102, 106, 102, 105, 400),
                                     (105, 106, 104.5, 105.5, 50)])
    r2 = rec_of(bars_of(hand(rows2)), '2026-02-10 09:33:10')
    assert pt(r2, 'big_body')['hit'] is False and pt(r2, 'big_body')['ref'] == 5.0
    # volume uses the same window: S volume 400 vs B1 300 (window from B1) -> hit; B0 500 is outside it
    assert pt(r, 'big_vol')['hit'] is True and pt(r, 'big_vol')['ref'] == 400.0
    assert pt(r2, 'big_vol')['hit'] is False and pt(r2, 'big_vol')['ref'] == 500.0


def test_a_new_low_inside_the_window_restarts_it_and_equal_body_scores():
    # the window restarts at every new-or-equal low, so the big body BEFORE the low no longer counts
    rows = _day_rows('2026-02-10', [(100, 110, 100, 109, 100), (109, 109, 95, 96, 100), (96, 99, 96, 98, 100),
                                    (98, 101, 98, 100, 100)])
    b = bars_of(hand(rows))
    r = rec_of(b, '2026-02-10 09:33:10')                        # S = third bar: body 2 vs the bar at the low (body 13)
    assert pt(r, 'big_body')['hit'] is False
    r = rec_of(b, '2026-02-10 09:34:10')                        # S = fourth bar body 2, window = bar2 (low 95) .. S
    assert pt(r, 'big_body')['hit'] is False and pt(r, 'big_body')['ref'] == 13.0
    # an EQUAL body is enough (>=)
    rows = _day_rows('2026-02-10', [(100, 103, 99, 102, 100), (102, 105, 101, 104, 100)])
    r = rec_of(bars_of(hand(rows)), '2026-02-10 09:32:10')
    assert pt(r, 'big_body')['hit'] is True and pt(r, 'big_body')['val'] == pt(r, 'big_body')['ref'] == 2.0


def test_big_body_must_be_green_for_a_long_and_red_for_a_short():
    # the biggest body of the window is a RED candle that also makes the low: a long misses, a short hits
    rows = _day_rows('2026-02-10', [(100, 101, 99, 100.5, 100), (100.5, 101, 90, 91, 100)])
    b = bars_of(hand(rows))
    long_r = rec_of(b, '2026-02-10 09:32:10', 'LONG')
    short_r = rec_of(b, '2026-02-10 09:32:10', 'SHORT')
    assert pt(long_r, 'big_body')['hit'] is False and pt(long_r, 'big_body')['val'] == -9.5
    # short: window from the latest HIGH (bar 0 high 101 ties bar 1 high 101 -> bar 1), body 9.5 red
    assert pt(short_r, 'big_body')['hit'] is True and pt(short_r, 'big_body')['val'] == 9.5
    assert pt(short_r, 'big_body')['label'] == "Largest body since today's high"


def test_short_window_starts_at_the_latest_high():
    rows = _day_rows('2026-02-10', [(100, 110, 99, 101, 500), (101, 110, 100, 99, 300), (99, 104, 97, 98, 200),
                                    (98, 99, 90, 92, 250)])
    b = bars_of(hand(rows))
    r = rec_of(b, '2026-02-10 09:34:10', 'SHORT')               # S = 4th bar (red, body 6); highs: 110, 110 (tie)
    body = pt(r, 'big_body')
    assert body['hit'] is True and body['ref'] == 6.0           # window = bar 1 (latest high 110) .. S: bodies 2, 1, 6
    assert pt(r, 'big_vol')['hit'] is False and pt(r, 'big_vol')['ref'] == 300.0


# ------------------------------------------------------------------ 5m / 30m reference bar

def _indep_ema_ref(df, secs_label, s_start, ma='sma'):
    """The spec's reference value, recomputed with pandas resample: the moving average of the bar BEFORE the one
    containing S.start."""
    rs = df.resample(secs_label, label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    ema = ma_of(rs['close'], ma)
    containing = pd.Timestamp(s_start).floor(secs_label)
    pos = rs.index.get_loc(containing)
    return ema.iloc[pos - 1], rs.index[pos - 1], len(rs.iloc[:pos])


@pytest.mark.parametrize('hm,ref5,ref30', [('09:31', '09:25', '09:00'), ('09:34', '09:25', '09:00'),
                                           ('09:35', '09:30', '09:00'), ('09:29', '09:20', '08:30'),
                                           ('10:00', '09:55', '09:30'), ('09:59', '09:50', '09:00')])
@pytest.mark.parametrize('ma', ['sma', 'ema'])
def test_5m_30m_reference_bar_is_the_bar_before_the_one_containing_S(hm, ref5, ref30, ma):
    df = walk(n_days=30, seed=21)
    b = bars_of(df)
    day = '2026-02-12'
    fill = pd.Timestamp('%s %s' % (day, hm)) + pd.Timedelta(minutes=1, seconds=12)
    r = ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=b, ma=ma)
    assert r['signal_bar'] == '%s %s' % (day, hm)
    for k, lab, want in (('ma200_5m', '5min', ref5), ('ma200_30m', '30min', ref30)):
        ema, stamp, count = _indep_ema_ref(df, lab, '%s %s' % (day, hm), ma)
        assert stamp == pd.Timestamp('%s %s' % (day, want))
        p = pt(r, k)
        assert p['ref'] == pytest.approx(ema, abs=1e-3), (k, hm)
        assert count >= 600
        assert p['hit'] == bool(df.loc['%s %s' % (day, hm), 'close'] > ema)


def test_the_boundary_case_S_0934_is_the_0925_5m_bar_and_S_0935_is_0930():
    # make the two candidates differ so the test cannot pass by accident
    df = walk(n_days=30, seed=22)
    b = bars_of(df)
    a = rec_of(b, '2026-02-12 09:35:30')                        # S = 09:34 -> 5m bar 09:25
    c = rec_of(b, '2026-02-12 09:36:30')                        # S = 09:35 -> 5m bar 09:30
    assert pt(a, 'ma200_5m')['ref'] != pt(c, 'ma200_5m')['ref']
    e1, s1, _ = _indep_ema_ref(df, '5min', '2026-02-12 09:34')
    e2, s2, _ = _indep_ema_ref(df, '5min', '2026-02-12 09:35')
    assert (s1, s2) == (pd.Timestamp('2026-02-12 09:25'), pd.Timestamp('2026-02-12 09:30'))
    assert pt(a, 'ma200_5m')['ref'] == pytest.approx(e1, abs=1e-3)
    assert pt(c, 'ma200_5m')['ref'] == pytest.approx(e2, abs=1e-3)


@pytest.mark.parametrize('ma', ['sma', 'ema'])
def test_1m_ema_includes_the_signal_bar_itself(ma):
    df = walk(n_days=30, seed=23)
    b = bars_of(df)
    r = rec_of(b, '2026-02-12 10:20:40', ma=ma)
    ema = ma_of(df['close'], ma).loc['2026-02-12 10:19']
    assert pt(r, 'ma200_1m')['ref'] == pytest.approx(ema, abs=1e-3)


# ------------------------------------------------------------------ warm-up

def test_600_bar_warmup_1m():
    df = walk(first_day='2026-01-05', n_days=3, seed=30)
    b = bars_of(df)
    stamp599 = df.index[598]                                    # the 599th bar: 599 bars including S
    stamp600 = df.index[599]
    a = ps.score_trade(dict(sym='NQ', side='LONG', fill=stamp599 + pd.Timedelta(seconds=70)), bars=b, ma='ema')
    c = ps.score_trade(dict(sym='NQ', side='LONG', fill=stamp600 + pd.Timedelta(seconds=70)), bars=b, ma='ema')
    assert a['signal_bar'] == stamp599.strftime('%Y-%m-%d %H:%M')
    assert pt(a, 'ma200_1m')['hit'] is None and pt(a, 'ma200_1m')['na_reason'] == ps.NA_WARM
    assert pt(c, 'ma200_1m')['hit'] is not None and pt(c, 'ma200_1m')['na_reason'] is None


def test_sma_needs_a_full_200_bar_window_1m_and_5m():
    df = walk(first_day='2026-01-05', n_days=3, seed=30)
    b = bars_of(df)
    for pos, ok in ((198, False), (199, True)):                 # the 199th / 200th bar, counting S
        r = ps.score_trade(dict(sym='NQ', side='LONG', fill=df.index[pos] + pd.Timedelta(seconds=70)), bars=b)
        assert (pt(r, 'ma200_1m')['hit'] is not None) == ok, pos
        if ok:
            assert pt(r, 'ma200_1m')['ref'] == pytest.approx(df['close'].iloc[:200].mean(), abs=1e-3)   # records keep 4 dp
    rs = df.resample('5min', label='left', closed='left').agg({'close': 'last'}).dropna()
    for pos, ok in ((199, False), (200, True)):                 # 199 / 200 complete 5m bars before S's own bar
        s = rs.index[pos] + pd.Timedelta(minutes=2)
        r = ps.score_trade(dict(sym='NQ', side='LONG', fill=s + pd.Timedelta(seconds=70)), bars=b)
        assert (pt(r, 'ma200_5m')['hit'] is not None) == ok, pos


def test_600_bar_warmup_5m_counts_bars_through_the_reference_bar():
    df = walk(first_day='2026-01-05', n_days=8, seed=31)
    b = bars_of(df)
    rs = df.resample('5min', label='left', closed='left').agg({'close': 'last'}).dropna()
    # S in the 5m bar at position 600 (0-based) has 600 complete bars before it -> reference bar is the 600th -> valid;
    # S in the bar at position 599 has 599 before it -> NA
    for pos, ok in ((599, False), (600, True)):
        s = rs.index[pos] + pd.Timedelta(minutes=2)             # a minute inside that 5m bar
        r = ps.score_trade(dict(sym='NQ', side='LONG', fill=s + pd.Timedelta(seconds=70)), bars=b, ma='ema')
        assert (pt(r, 'ma200_5m')['hit'] is not None) == ok, pos


def test_10s_ema_warmup_and_reference_bar():
    df = walk(n_days=30, seed=32)
    t10, c10 = ten_sec(df, '2026-02-10 07:30')
    b = bars_of(df, t10=t10, c10=c10)
    # 600 10-second bars = 100 minutes: a signal bar at 09:31 (121 minutes after 07:30) has 726 of them
    r = rec_of(b, '2026-02-10 09:32:21', ma='ema')
    p = pt(r, 'ma200_10s')
    assert p['hit'] is not None
    ema = pd.Series(c10).ewm(span=200, adjust=False).mean()
    e = ps._epoch('2026-02-10 09:31')
    last = int(np.searchsorted(t10, e + 60, side='left')) - 1
    assert t10[last] == e + 50                                   # the last 10s bar of the signal minute
    assert p['ref'] == pytest.approx(ema.iloc[last], abs=1e-3)
    early = rec_of(b, '2026-02-10 08:30:10', ma='ema')           # only 60 minutes = 360 bars in
    assert pt(early, 'ma200_10s')['na_reason'] == ps.NA_WARM
    before = rec_of(b, '2026-02-10 07:00:10')
    assert pt(before, 'ma200_10s')['na_reason'] == ps.NA_NO10


def test_10s_sma_warmup_and_reference_bar():
    df = walk(n_days=30, seed=32)
    t10, c10 = ten_sec(df, '2026-02-10 07:30')
    b = bars_of(df, t10=t10, c10=c10)
    # 200 10-second bars = 33 1/3 minutes: S = 08:02 has 33 x 6 = 198 bars through its own minute (NA), 08:03 has 204
    assert pt(rec_of(b, '2026-02-10 08:03:10'), 'ma200_10s')['na_reason'] == ps.NA_WARM
    p = pt(rec_of(b, '2026-02-10 08:04:10'), 'ma200_10s')
    assert p['hit'] is not None
    e = ps._epoch('2026-02-10 08:03')
    last = int(np.searchsorted(t10, e + 60, side='left')) - 1
    assert p['ref'] == pytest.approx(pd.Series(c10).rolling(200).mean().iloc[last], abs=1e-3)


def test_10s_is_na_when_the_signal_minute_has_no_10s_bar():
    df = walk(n_days=30, seed=33)
    t10, c10 = ten_sec(df, '2026-02-02 08:00')
    e = ps._epoch('2026-02-10 09:31')
    keep = ~((t10 >= e) & (t10 < e + 60))
    b = bars_of(df, t10=t10[keep], c10=c10[keep])
    r = rec_of(b, '2026-02-10 09:32:21')
    assert pt(r, 'ma200_10s')['na_reason'] == ps.NA_NO10BAR


def test_10s_is_na_within_48h_after_a_real_switch():
    df = walk(n_days=30, seed=34)
    t10, c10 = ten_sec(df, '2026-01-20 08:00')
    sw = [dict(inst=ps._epoch('2026-02-09 11:30'), offset=50.0, status='measured', et='2026-02-09 11:30', kind='mid_session')]
    b = bars_of(df, t10=t10, c10=c10, switches=sw)
    inside = rec_of(b, '2026-02-11 11:00:10')                   # 47.5 h after the switch -> NA
    outside = rec_of(b, '2026-02-11 12:00:10')                  # 48.5 h after -> scored
    assert pt(inside, 'ma200_10s')['na_reason'] == ps.NA_ROLL
    assert pt(outside, 'ma200_10s')['hit'] is not None
    assert pt(rec_of(b, '2026-02-09 11:00:10'), 'ma200_10s')['hit'] is not None    # before the switch: fine
    f = b.full('LONG')
    i = b.find(ps._epoch('2026-02-11 10:59'))
    assert ps._REASONS[f['ma200_10s']['na'][i]] == ps.NA_ROLL


# ------------------------------------------------------------------ yesterday's levels

def _block(rows, rng, date, start, n, base, vol=100):
    """Append n one-minute random-walk bars from `start` on `date` (stamped at their START); returns the last close."""
    t = pd.Timestamp('%s %s' % (date, start))
    px = base
    for i in range(n):
        o = px
        c = o + rng.choice([-1.0, 1.0, 0.5, -0.5])
        rows.append(((t + pd.Timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M'), o, max(o, c) + 0.25, min(o, c) - 0.25, c, vol))
        px = c
    return px


def _thanksgiving_week():
    """Wed 2026-11-25 full RTH, Thu 11-26 Thanksgiving (a listed holiday: NO bars), Fri 11-27 a listed EARLY CLOSE
    (09:30-13:14) plus 16:00 / 16:01 post bars at wild prices that must not count, Sunday-evening bars (no regular
    bars that day), Monday 11-30 S."""
    rows = []
    rng = np.random.default_rng(5)
    px = _block(rows, rng, '2026-11-25', '09:30', 390, 100.0)    # Wed 09:30-15:59
    px = _block(rows, rng, '2026-11-27', '09:30', 225, px)       # Fri 09:30-13:14 (early close)
    rows.append(('2026-11-27 16:00', 500.0, 600.0, 400.0, 555.0, 100))
    rows.append(('2026-11-27 16:01', 555.0, 700.0, 300.0, 444.0, 100))
    px2 = _block(rows, rng, '2026-11-29', '18:00', 60, px)       # Sunday evening bars, no regular-session bars that day
    _block(rows, rng, '2026-11-30', '09:30', 40, px2)            # Monday
    return hand(rows)


def _short_day_week():
    """Tue 2026-02-03 full, Wed 02-04 an UNLISTED short day (09:30-12:59), Thu 02-05 full, Fri 02-06 S."""
    rows = []
    rng = np.random.default_rng(6)
    px = _block(rows, rng, '2026-02-03', '09:30', 390, 100.0)
    px = _block(rows, rng, '2026-02-04', '09:30', 210, px)
    px = _block(rows, rng, '2026-02-05', '09:30', 390, px)
    _block(rows, rng, '2026-02-06', '09:30', 40, px)
    return hand(rows)


def _holiday_stub_week():
    """Thu 2026-05-21 and Fri 05-22 full, Mon 05-25 Memorial Day: a Globex STUB (09:30-12:59) at prices far from Friday's,
    Tue 05-26 S."""
    rows = []
    rng = np.random.default_rng(7)
    px = _block(rows, rng, '2026-05-21', '09:30', 390, 100.0)
    px = _block(rows, rng, '2026-05-22', '09:30', 390, px)
    px = _block(rows, rng, '2026-05-25', '09:30', 210, px + 200.0)
    _block(rows, rng, '2026-05-26', '09:30', 40, px)
    return hand(rows)


def _agree(b, idx, sides=('LONG', 'SHORT'), ma=ps.DEFAULT_MA):
    """The literal path and the vectorised path give the same record (hit, NA reason, val, ref) at every index in idx."""
    for side in sides:
        f = b.full(side, ma)
        for i in idx:
            rec, _ = ps._literal(b, int(b.t[i]), side, ma)
            for k, p in zip(ps.KEYS + ['d_trend'], rec['points'] + [rec['trend']]):
                d = f[k]
                ha = None if np.isnan(d['hit'][i]) else bool(d['hit'][i])
                assert ha == p['hit'] and ps._REASONS[d['na'][i]] == p['na_reason'], (side, ps._et_str(b.t[i]), k)
                if ha is not None:
                    assert d['val'][i] == pytest.approx(p['val'], abs=1e-3)
                    assert d['ref'][i] == pytest.approx(p['ref'], abs=1e-3)


def test_yesterday_skips_days_without_regular_session_bars_and_uses_the_last_bar_before_1600():
    df = _thanksgiving_week()
    b = bars_of(df)
    # S on Monday 2026-11-30 09:35; Sunday has only evening bars, Saturday none -> yesterday = Friday, a listed EARLY CLOSE
    # whose last regular bar is 13:14: it counts as complete (v1.1)
    r = rec_of(b, '2026-11-30 09:36:10')
    fri = df.loc['2026-11-27 09:30':'2026-11-27 13:14']
    assert pt(r, 'y_high')['na_reason'] is None and pt(r, 'y_close')['na_reason'] is None
    assert pt(r, 'y_high')['ref'] == fri['high'].max()
    assert pt(r, 'y_low')['ref'] == fri['low'].min()
    assert pt(r, 'y_close')['ref'] == fri['close'].iloc[-1]     # the 13:14 bar, not the 16:00 / 16:01 post bars
    assert pt(r, 'y_high')['ref'] < 500                          # the post bars at 600 / 700 are excluded
    # the session before it = Wednesday (Thursday was Thanksgiving: no bars, and listed): drives the trend point
    wed = df.loc['2026-11-25 09:30':'2026-11-25 15:59']
    tr = r['trend']
    assert tr['na_reason'] is None and tr['val'] == fri['high'].max() and tr['ref'] == wed['high'].max()
    assert tr['hit'] == bool(fri['high'].max() > wed['high'].max() and fri['low'].min() > wed['low'].min())
    # S on the early-close Friday itself uses Wednesday
    r2 = rec_of(b, '2026-11-27 10:00:10')
    assert pt(r2, 'y_close')['ref'] == wed['close'].iloc[-1]


def test_yesterday_beyond_7_calendar_days_is_na():
    full = [(100, 101, 99, 100.5, 10)] * 390                      # a complete 09:30-15:59 session
    rows = _day_rows('2026-02-02', full) + _day_rows('2026-02-12', [(100, 101, 99, 100.5, 10)] * 60)
    b = bars_of(hand(rows))
    r = rec_of(b, '2026-02-12 09:45:10')
    for k in ('y_low', 'y_close', 'y_high'):
        assert pt(r, k)['hit'] is None and pt(r, k)['na_reason'] == ps.NA_NOY
    assert r['trend']['hit'] is None and r['max'] <= 6
    rows = _day_rows('2026-02-02', full) + _day_rows('2026-02-09', [(100, 101, 99, 100.5, 10)] * 60)
    r = rec_of(bars_of(hand(rows)), '2026-02-09 09:45:10')      # exactly 7 days: still found
    assert pt(r, 'y_low')['na_reason'] is None


def test_short_compares_below_the_same_levels():
    df = _thanksgiving_week()
    b = bars_of(df)
    rl = rec_of(b, '2026-11-30 09:36:10', 'LONG')
    rs = rec_of(b, '2026-11-30 09:36:10', 'SHORT')
    for k in ('y_low', 'y_close', 'y_high'):
        pl, psh = pt(rl, k), pt(rs, k)
        assert pl['ref'] == psh['ref'] and pl['val'] == psh['val']
        assert pl['hit'] != psh['hit']                          # no tie in this data: above XOR below


def test_a_listed_holiday_stub_is_never_yesterday():
    df = _holiday_stub_week()
    b = bars_of(df)
    thu, fri = df.loc['2026-05-21 09:30':'2026-05-21 15:59'], df.loc['2026-05-22 09:30':'2026-05-22 15:59']
    stub = df.loc['2026-05-25 09:30':'2026-05-25 12:59']
    assert stub['low'].min() > fri['high'].max()                 # the stub sits far above Friday: a wrong pick is obvious
    for fill in ('2026-05-26 10:00:30', '2026-05-26 09:31:00', '2026-05-26 10:05:12'):
        r = rec_of(b, fill)
        assert (pt(r, 'y_low')['ref'], pt(r, 'y_close')['ref'], pt(r, 'y_high')['ref']) == (
            fri['low'].min(), fri['close'].iloc[-1], fri['high'].max()), fill
        assert r['trend']['val'] == fri['high'].max() and r['trend']['ref'] == thu['high'].max()   # the stub is no yy either
    # the stub's own date still scores (its yesterday is Friday); the vectorised path agrees everywhere
    r = rec_of(b, '2026-05-25 10:00:30')
    assert pt(r, 'y_high')['ref'] == fri['high'].max()
    n = len(b)
    _agree(b, [i for i in range(n) if b.t[i] >= ps._epoch('2026-05-25 09:30') and i % 7 == 0])
    assert '2026-05-25' in ps.CME_HOLIDAYS['full']                # the list is what does the work


def test_incomplete_prior_session_is_na_not_a_wrong_level_and_is_not_skipped():
    df = _short_day_week()
    b = bars_of(df)
    tue, wed, thu = (df.loc['2026-02-0%d 09:30:00' % d:'2026-02-0%d 15:59' % d] for d in (3, 4, 5))
    assert len(wed) == 210                                      # an unlisted short day: last regular bar 12:59
    # S on Thursday: yesterday = Wednesday (incomplete) -> NA for all three levels AND the trend; Tuesday is NOT used
    r = rec_of(b, '2026-02-05 10:00:30')
    for k in ('y_low', 'y_close', 'y_high'):
        p = pt(r, k)
        assert p['hit'] is None and p['na_reason'] == ps.NA_INCOMPLETE and p['ref'] is None and p['val'] is None
    assert r['trend']['hit'] is None and r['trend']['na_reason'] == ps.NA_INCOMPLETE
    assert r['max'] == 9 - r['na_count'] and r['na_count'] >= 3
    # S on Friday: yesterday = Thursday (complete) -> the levels are Thursday's; the session before it (Wednesday) is
    # incomplete -> only the trend point is NA
    r = rec_of(b, '2026-02-06 10:00:30')
    assert pt(r, 'y_close')['na_reason'] is None and pt(r, 'y_close')['ref'] == thu['close'].iloc[-1]
    assert pt(r, 'y_high')['ref'] == thu['high'].max() and pt(r, 'y_low')['ref'] == thu['low'].min()
    assert r['trend']['hit'] is None and r['trend']['na_reason'] == ps.NA_INCOMPLETE
    # both paths agree on every bar of the three days
    _agree(b, [i for i in range(len(b)) if b.t[i] >= ps._epoch('2026-02-04 09:30') and i % 5 == 0])


def test_early_close_day_ending_before_1314_or_an_unlisted_early_day_is_incomplete():
    # 2026-11-27 is a listed early close: ending at 13:13 (one bar short) is incomplete; 2026-12-04 is not listed, so a
    # 13:14 end is incomplete there
    for day, nxt, n_bars, want_na in (('2026-11-27', '2026-11-30', 224, True), ('2026-12-04', '2026-12-07', 225, True),
                                      ('2026-11-27', '2026-11-30', 225, False)):
        rows = []
        rng = np.random.default_rng(8)
        px = _block(rows, rng, day, '09:30', n_bars, 100.0)
        _block(rows, rng, nxt, '09:30', 40, px)
        b = bars_of(hand(rows))
        r = rec_of(b, nxt + ' 10:00:30')
        assert (pt(r, 'y_close')['na_reason'] == ps.NA_INCOMPLETE) == want_na, (day, n_bars)
        assert (pt(r, 'y_close')['hit'] is None) == want_na


# ------------------------------------------------------------------ the 10-second capture gap (v1.1)

def _gap_world(gap_minutes, quiet=None, seed=70):
    """30 weekdays of 1-minute bars with a 10-second capture from 2026-01-28 18:00 that LOST the minutes
    10:00 .. 10:00 + gap_minutes - 1 on 2026-02-10. quiet='volume0': the master also traded nothing in those minutes;
    quiet='nobars': the master has no bars there at all."""
    df = walk(n_days=30, seed=seed)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    e0 = ps._epoch('2026-02-10 10:00')
    keep = ~((t10 >= e0) & (t10 < e0 + 60 * gap_minutes))
    if quiet == 'volume0':
        m = (df.index >= pd.Timestamp('2026-02-10 10:00')) & (df.index < pd.Timestamp('2026-02-10 10:00') + pd.Timedelta(minutes=gap_minutes))
        df = df.copy()
        df.loc[m, 'volume'] = 0.0
    elif quiet == 'nobars':
        m = (df.index >= pd.Timestamp('2026-02-10 10:00')) & (df.index < pd.Timestamp('2026-02-10 10:00') + pd.Timedelta(minutes=gap_minutes))
        df = df[~m]
    return df, bars_of(df, t10=t10[keep], c10=c10[keep])


def _p10(b, hm, side='LONG', ma=ps.DEFAULT_MA):
    """The 10-second point of the bar that STARTS at hm on 2026-02-10 (fill = 30 s into the next minute)."""
    fill = pd.Timestamp('2026-02-10 ' + hm) + pd.Timedelta(seconds=90)
    return pt(ps.score_trade(dict(sym='NQ', side=side, fill=fill), bars=b, ma=ma), 'ma200_10s')


def test_10s_capture_gap_inside_the_ema_memory_is_na():
    df, b = _gap_world(31)                                       # the capture lost 10:00-10:30 (31 minutes that traded)
    E = 'ema'
    assert _p10(b, '09:59', ma=E)['hit'] is not None            # the window has not reached the gap yet
    assert _p10(b, '10:00', ma=E)['na_reason'] == ps.NA_NO10BAR  # the signal minute itself has no 10s bar
    assert _p10(b, '10:45', ma=E)['na_reason'] == ps.NA_GAP10   # the gap is inside the last 600 10s bars
    # 600 10s bars = 100 minutes of the capture AFTER the gap: 10:31 .. 12:10 inclusive. One minute earlier, the
    # 600th-latest bar still lies before the gap -> NA; at 12:10 the window starts at 10:31 -> scored again
    assert _p10(b, '12:09', ma=E)['na_reason'] == ps.NA_GAP10
    assert _p10(b, '12:10', ma=E)['hit'] is not None and _p10(b, '12:10', ma=E)['na_reason'] is None
    # the vectorised path says the same on every bar of the day
    i0, i1 = b.find(ps._epoch('2026-02-10 09:50')), b.find(ps._epoch('2026-02-10 12:30'))
    _agree(b, list(range(i0, i1 + 1, 3)) + [b.find(ps._epoch('2026-02-10 12:09')), b.find(ps._epoch('2026-02-10 12:10'))], ma=E)
    f = b.full('SHORT', E)
    assert ps._REASONS[f['ma200_10s']['na'][b.find(ps._epoch('2026-02-10 12:09'))]] == ps.NA_GAP10


def test_10s_capture_gap_inside_the_sma_memory_is_na():
    df, b = _gap_world(31)
    assert _p10(b, '10:45')['na_reason'] == ps.NA_GAP10          # inside the last 200 10s bars
    # 200 10s bars = 33 1/3 minutes AFTER the gap: at 11:03 (198 bars since 10:31) the 200th-latest bar still lies
    # before the gap -> NA; at 11:04 (204 bars) the window starts at 10:31 -> scored again
    assert _p10(b, '11:03')['na_reason'] == ps.NA_GAP10
    assert _p10(b, '11:04')['hit'] is not None and _p10(b, '11:04')['na_reason'] is None
    i0, i1 = b.find(ps._epoch('2026-02-10 09:50')), b.find(ps._epoch('2026-02-10 11:30'))
    _agree(b, list(range(i0, i1 + 1, 3)) + [b.find(ps._epoch('2026-02-10 11:03')), b.find(ps._epoch('2026-02-10 11:04'))])


def test_10s_capture_gap_needs_three_lost_minutes():
    _, b2 = _gap_world(2)                                        # two lost minutes: tolerated
    assert _p10(b2, '10:45')['hit'] is not None and _p10(b2, '10:45')['na_reason'] is None
    _, b3 = _gap_world(3)                                        # three lost minutes (10:00-10:02): a gap ...
    assert _p10(b3, '10:20')['na_reason'] == ps.NA_GAP10          # ... inside the SMA's 200-bar memory
    assert _p10(b3, '10:45')['na_reason'] is None                # 10:45's 200 bars start ~10:12: the gap is behind it
    assert _p10(b3, '10:45', ma='ema')['na_reason'] == ps.NA_GAP10   # the EMA's 600-bar memory still holds it
    _agree(b3, [b3.find(ps._epoch('2026-02-10 10:45')), b3.find(ps._epoch('2026-02-10 10:03'))])
    _agree(b2, [b2.find(ps._epoch('2026-02-10 10:45'))])


@pytest.mark.parametrize('quiet', ['volume0', 'nobars'])
def test_10s_a_quiet_market_is_not_a_gap(quiet):
    # the capture has no bars for 31 minutes, but the master did not trade then either: nothing was lost
    df, b = _gap_world(31, quiet=quiet)
    for hm in ('10:45', '12:09', '12:10'):
        p = _p10(b, hm)
        assert p['hit'] is not None and p['na_reason'] is None, hm
    _agree(b, [b.find(ps._epoch('2026-02-10 10:45')), b.find(ps._epoch('2026-02-10 12:09'))])


def test_10s_the_daily_break_and_the_weekend_are_never_a_gap():
    df = walk(n_days=30, seed=71)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    b = bars_of(df, t10=t10, c10=c10)
    # Sunday 02-08 19:00 is an hour after the week's open, so the 10s window spans the weekend; the 18:30 ones span the
    # 17:00-18:00 break: none of them may read as a gap
    for hm in ('2026-02-08 19:00', '2026-02-09 18:30', '2026-02-10 18:30'):
        fill = pd.Timestamp(hm) + pd.Timedelta(seconds=75)
        p = pt(ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=b), 'ma200_10s')
        assert p['na_reason'] is None and p['hit'] is not None, hm


# ------------------------------------------------------------------ rolls: trade-relative adjustment

def _brute(df, sw, fill, side, ma='sma'):
    """The spec formula read literally, bar by bar, on clean (between-bars) switches:
    adjusted(t) = raw(t) + sum(offsets of switches after t) - sum(offsets of switches after t_close)."""
    s_start = (ps._epoch(fill) // 60) * 60 - 60
    t_close = s_start + 60
    t = ps._idx_epoch(df.index.tz_localize(ET))
    keep = t < t_close
    t, d = t[keep], df[keep]
    after_t = np.array([sum(s['offset'] for s in sw if s['inst'] > x) for x in t])
    after_c = sum(s['offset'] for s in sw if s['inst'] > t_close)
    adj = d[['open', 'high', 'low', 'close']].to_numpy() + (after_t - after_c)[:, None]
    a = pd.DataFrame(adj, columns=['open', 'high', 'low', 'close'], index=d.index)
    a['volume'] = d['volume'].to_numpy()
    out = dict(ema1=ma_of(a['close'], ma).iloc[-1])
    rs = a.resample('5min', label='left', closed='left').agg({'close': 'last'}).dropna()
    out['ema5'] = ma_of(rs['close'], ma).iloc[-2]
    rs = a.resample('30min', label='left', closed='left').agg({'close': 'last'}).dropna()
    out['ema30'] = ma_of(rs['close'], ma).iloc[-2]
    day = a.index[-1].normalize()
    rth = a[(a.index.hour * 60 + a.index.minute >= 570) & (a.index.hour * 60 + a.index.minute < 960) & (a.index < day)]
    ydate = rth.index.normalize().max()
    y = rth[rth.index.normalize() == ydate]
    out.update(yH=y['high'].max(), yL=y['low'].min(), yC=y['close'].iloc[-1], C=a['close'].iloc[-1])
    return out


@pytest.mark.parametrize('fill', ['2026-02-13 10:15:20', '2026-02-11 10:15:20', '2026-02-12 09:45:20', '2026-02-09 14:00:20'])
@pytest.mark.parametrize('ma', ['sma', 'ema'])
def test_roll_adjustment_is_relative_to_the_trade(fill, ma):
    df = walk(n_days=30, seed=40)
    # a real switch between two bars on Feb 11 10:00 (offset -37.25) and one on Jan 27 (offset +12.5)
    sw = [dict(inst=ps._epoch('2026-02-11 10:00'), offset=-37.25, status='exact', et='2026-02-11 10:00', kind='mid_session'),
          dict(inst=ps._epoch('2026-01-27 08:00'), offset=12.5, status='exact', et='2026-01-27 08:00', kind='mid_session')]
    b = bars_of(df, switches=sw)
    want = _brute(df, sw, fill, 'LONG', ma)
    r = ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=b, ma=ma)
    assert pt(r, 'ma200_1m')['ref'] == pytest.approx(want['ema1'], abs=1e-3)
    assert pt(r, 'ma200_5m')['ref'] == pytest.approx(want['ema5'], abs=1e-3)
    assert pt(r, 'ma200_30m')['ref'] == pytest.approx(want['ema30'], abs=1e-3)
    assert pt(r, 'y_high')['ref'] == pytest.approx(want['yH'], abs=1e-6)
    assert pt(r, 'y_low')['ref'] == pytest.approx(want['yL'], abs=1e-6)
    assert pt(r, 'y_close')['ref'] == pytest.approx(want['yC'], abs=1e-6)
    # prices at the trade stay REAL: val is the raw close of the signal bar
    s_start = pd.Timestamp(fill).floor('1min') - pd.Timedelta(minutes=1)
    assert pt(r, 'ma200_1m')['val'] == df.loc[s_start, 'close'] == want['C']
    # and the vectorised path agrees
    f = b.full('LONG', ma)
    i = b.find(ps._epoch(s_start.strftime('%Y-%m-%d %H:%M')))
    for k, w in (('ma200_1m', want['ema1']), ('ma200_5m', want['ema5']), ('ma200_30m', want['ema30']),
                 ('y_high', want['yH']), ('y_low', want['yL']), ('y_close', want['yC'])):
        assert f[k]['ref'][i] == pytest.approx(w, abs=1e-3), k


def test_a_roll_does_not_change_any_hit_only_the_reference_prices():
    df = walk(n_days=30, seed=41)
    sw = [dict(inst=ps._epoch('2026-02-10 10:00'), offset=25.0, status='exact', et='2026-02-10 10:00', kind='mid_session')]
    # the same market, but with the pre-switch bars cut down by the offset (an unadjusted feed): adjusting must undo it
    raw = df.copy()
    t = pd.DatetimeIndex(raw.index)
    m = t < pd.Timestamp('2026-02-10 10:00')
    for c in ('open', 'high', 'low', 'close'):
        raw.loc[m, c] = raw.loc[m, c] - 25.0
    flat = bars_of(df)
    rolled = bars_of(raw, switches=sw)
    for hm in ('09:45', '10:30', '15:00'):
        fill = pd.Timestamp('2026-02-12 ' + hm) + pd.Timedelta(seconds=40)
        a = ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=flat)
        c = ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=rolled)
        assert [p['hit'] for p in a['points']] == [p['hit'] for p in c['points']]
        for p, q in zip(a['points'], c['points']):
            if p['hit'] is not None:
                assert p['ref'] == pytest.approx(q['ref'], abs=1e-3), p['k']
    # a signal bar BEFORE the switch sees the pre-switch contract: its prices are its real ones
    fill = '2026-02-10 09:45:20'
    c = ps.score_trade(dict(sym='NQ', side='LONG', fill=fill), bars=rolled)
    assert pt(c, 'ma200_1m')['val'] == raw.loc['2026-02-10 09:44', 'close']


def test_estimated_roll_within_three_sessions_adds_a_note():
    df = walk(n_days=30, seed=42)
    sw = [dict(inst=ps._epoch('2026-02-10 03:30'), offset=30.0, status='estimated', et='2026-02-10 03:30', kind='in_bar'),
          dict(inst=ps._epoch('2026-01-20 03:30'), offset=30.0, status='estimated', et='2026-01-20 03:30', kind='in_bar')]
    b = bars_of(df, switches=sw)
    near = rec_of(b, '2026-02-11 10:00:10')
    far = rec_of(b, '2026-02-20 10:00:10')
    assert any('2026-02-10 03:30' in n for n in near['notes'])
    assert not any('2026-02-10' in n for n in far['notes'])
    trusted = [dict(sw[0], status='measured')]
    assert not rec_of(bars_of(df, switches=trusted), '2026-02-11 10:00:10')['notes']


def test_in_bar_switch_bar_is_rebuilt_with_no_wick_and_the_close_stays_real():
    # one clean day, then a bar whose open is on the old contract and whose close is on the new one (+100 jump)
    rows = _day_rows('2026-02-10', [(100, 101, 99, 100, 10)] * 5, start='09:30')
    rows.append(('2026-02-10 09:35', 100, 205, 99, 203, 5000))   # jump bar: open old contract, close new (+100 offset)
    rows.append(('2026-02-10 09:36', 203, 204, 202, 203.5, 100))
    sw = [dict(inst=ps._epoch('2026-02-10 09:35') + 1, offset=100.0, status='exact', et='2026-02-10 09:35', kind='in_bar')]
    b = bars_of(hand(rows), switches=sw)
    r = rec_of(b, '2026-02-10 09:36:10')                          # S = the jump bar
    body = pt(r, 'big_body')
    assert pt(r, 'y_low')['na_reason'] == ps.NA_NOY
    assert body['val'] == 3.0                                     # 203 - (100 + 100): a real 3-point body, not 103
    assert body['hit'] is True
    sb = ps.signal_bar_ohlc(dict(sym='NQ', side='LONG', fill='2026-02-10 09:36:10'), bars=b)
    assert sb['close'] == 203.0 and sb['open'] == 200.0 and sb['high'] == 203.0 and sb['low'] == 200.0   # no wick, real close


# ------------------------------------------------------------------ the vectorised path agrees with the literal path

def test_series_equals_trade_on_synthetic_bars():
    df = walk(n_days=30, seed=50)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    sw = [dict(inst=ps._epoch('2026-02-06 10:00'), offset=-41.5, status='exact', et='2026-02-06 10:00', kind='mid_session')]
    b = bars_of(df, t10=t10, c10=c10, switches=sw)
    rng = np.random.default_rng(7)
    idx = rng.choice(np.arange(700, len(b) - 1), size=120, replace=False)
    for side in ('LONG', 'SHORT'):
        f = b.full(side)
        for i in idx:
            rec, _ = ps._literal(b, int(b.t[i]), side)
            for k, p in zip(ps.KEYS, rec['points']):
                d = f[k]
                ha = None if np.isnan(d['hit'][i]) else bool(d['hit'][i])
                assert ha == p['hit'] and ps._REASONS[d['na'][i]] == p['na_reason'], (side, i, k)
                if ha is not None:
                    assert d['val'][i] == pytest.approx(p['val'], abs=1e-3)
                    assert d['ref'][i] == pytest.approx(p['ref'], abs=1e-3)
            tr = f['d_trend']
            ht = None if np.isnan(tr['hit'][i]) else bool(tr['hit'][i])
            assert ht == rec['trend']['hit']


def test_score_series_frame_shape_and_totals():
    df = walk(n_days=30, seed=51)
    b = bars_of(df)
    ser = ps.score_series('NQ', 'LONG', '2026-02-10', '2026-02-10', bars=b)
    assert ser.index.tz is not None and str(ser.index.tz) == ET
    assert ser.index.min() >= pd.Timestamp('2026-02-10 00:00', tz=ET) and ser.index.max() < pd.Timestamp('2026-02-11', tz=ET)
    assert (ser['max'] + ser['na_count'] == 9).all()
    assert (ser['total'] <= ser['max']).all()
    for k in ps.KEYS:
        assert (ser[k + '_hit'].isna() == (ser[k + '_na'] != '')).all()
    row = ser.loc['2026-02-10 09:31']
    rec = rec_of(b, '2026-02-10 09:32:21')
    assert row['total'] == rec['total'] and row['max'] == rec['max']


# ------------------------------------------------------------------ stocks (stub until the Alpaca key exists)

def test_stock_without_keys_is_all_na_and_fetches_nothing(monkeypatch):
    monkeypatch.setattr(ps, '_alpaca', lambda: None)
    ps._STOCK_CACHE.clear()

    def boom(*a, **k):
        raise AssertionError('must not fetch without keys')
    r = ps.score_trade(dict(sym='AAPL', side='LONG', fill='2026-09-30 09:32:21'))
    assert r['total'] == 0 and r['max'] == 0 and r['na_count'] == 9
    assert all(p['na_reason'] == 'no stock bars (Alpaca key not saved)' and p['hit'] is None for p in r['points'])
    assert r['trend']['hit'] is None
    assert ps.load_stock_bars('AAPL', '2026-09-30') is None


def test_stock_bars_use_a_0400_window_and_never_have_a_10s_point():
    # extended-hours bars from 04:00: the day window opens at 04:00 for stocks
    df = walk(n_days=30, seed=52)
    b = ps.Bars.from_frame(df, root='AAPL', asset='stock', switches=[])
    r = rec_of(b, '2026-02-10 05:10:10', sym='AAPL')
    assert pt(r, 'ma200_10s')['na_reason'] == ps.NA_STOCK10
    assert pt(r, 'big_body')['na_reason'] is None                # 05:09 is inside a 04:00 window
    fut = rec_of(bars_of(df), '2026-02-10 05:10:10')
    assert pt(fut, 'big_body')['na_reason'] == ps.NA_WIN         # but before a futures 09:30 window
    assert r['src'] == 'alpaca1m'



def test_stock_path_with_keys_fetches_once_and_scores(monkeypatch):
    import types
    df = walk(n_days=30, seed=53)
    frame = pd.DataFrame(dict(time=ps._idx_epoch(df.index.tz_localize(ET)), open=df['open'].to_numpy(),
                              high=df['high'].to_numpy(), low=df['low'].to_numpy(), close=df['close'].to_numpy(),
                              volume=df['volume'].to_numpy().astype('int64')))
    calls = []

    def fetch(sym, tf, start, end, k, s):
        calls.append((sym, tf, start, end))
        return frame
    fake = types.SimpleNamespace(fetch_bars=fetch, load_keys=lambda: ('k', 's'))
    monkeypatch.setattr(ps, '_alpaca', lambda: (fake, 'k', 's'))
    ps._STOCK_CACHE.clear()
    r = ps.score_trade(dict(sym='AAPL', side='LONG', fill='2026-02-10 09:32:21'))
    r2 = ps.score_trade(dict(sym='AAPL', side='SHORT', fill='2026-02-10 10:32:21'))
    assert len(calls) == 1 and calls[0][:2] == ('AAPL', '1Min')       # cached per (symbol, date)
    assert pt(r, 'ma200_10s')['na_reason'] == ps.NA_STOCK10 and pt(r, 'ma200_1m')['hit'] is not None
    assert r['src'] == 'alpaca1m' and r2['side'] == 'SHORT'
    ps._STOCK_CACHE.clear()



def test_uploads_dir_skips_an_empty_augur_uploads_in_a_worktree(tmp_path, monkeypatch):
    empty = tmp_path / 'augur_uploads'
    (empty / '_context').mkdir(parents=True)
    full = tmp_path / 'shared' / 'augur_uploads'
    full.mkdir(parents=True)
    (full / ps.MASTER_1M['NQ']).write_text('time,open,high,low,close,volume,source')
    monkeypatch.delenv('EDGELOG_UPLOADS', raising=False)
    monkeypatch.setattr(ps, 'ROOT', str(tmp_path))
    monkeypatch.setattr(ps, 'SHARED', str(tmp_path / 'shared'))
    assert ps.uploads_dir() == str(full)
    monkeypatch.setenv('EDGELOG_UPLOADS', str(empty))
    assert ps.uploads_dir() == str(full)                        # an empty override does not hide the real masters


# ------------------------------------------------------------------ loader (tiny files, no real data)

def _write_master(path, rows):
    with open(path, 'w', newline='') as fh:
        fh.write('time,open,high,low,close,volume,source\n')
        for r in rows:
            fh.write(','.join(str(x) for x in r) + ',existing\n')


def _write_capture(path, rows):
    with open(path, 'w', newline='') as fh:
        fh.write('time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n')
        for r in rows:
            fh.write(','.join(str(x) for x in r) + ',0,0,0,0,1\n')


def test_loader_fills_the_summer_hole_and_the_tail_from_the_capture(tmp_path):
    e = lambda s: ps._epoch(s)
    master = []
    for base in ('2026-06-29 10:00', '2026-08-06 10:00'):       # before and after the hole
        t0 = e(base)
        master += [(t0 + 60 * i, 100 + i, 101 + i, 99 + i, 100.5 + i, 10 + i) for i in range(3)]
    tail = e('2026-09-30 10:00')
    master += [(tail, 200, 201, 199, 200.5, 50), (tail + 60, 200.5, 201, 200, 200.75, 60), (tail + 120, 201, 202, 200, 201, 0)]
    _write_master(tmp_path / 'NOADJ_NQ_1m_ETH.csv', master)           # last row volume 0 = partial bar: dropped
    cap = []

    def minute(start, o, c, vol_each):                          # six 10s bars stamped at their END
        for k in range(6):
            cap.append((start + 10 * k + 10, o, max(o, c) + 1, min(o, c) - 1, c if k == 5 else o, vol_each))
    minute(e('2026-07-10 10:00'), 120.0, 121.0, 5)              # inside the hole -> used
    minute(e('2026-07-10 10:01'), 121.0, 122.0, 5)
    minute(e('2026-06-29 10:01'), 50.0, 51.0, 5)                # overlaps a master bar: the master wins
    minute(e('2026-08-07 10:05'), 50.0, 51.0, 5)                # after the hole window (date > 2026-08-06): not used
    minute(e('2026-09-30 10:02'), 300.0, 301.0, 7)              # after the master's last kept bar (10:01) -> used
    cap.append((e('2026-09-30 10:03') + 10, 301.0, 302.0, 300.0, 301.5, 7))     # a partial final minute: dropped
    _write_capture(tmp_path / 'master_b1335b7e.csv', cap)
    b = ps.load_bars('NQ', history_from='2026-06-01', uploads=str(tmp_path))
    starts = {int(t): bool(fc) for t, fc in zip(b.t, b.from_cap)}
    assert starts[e('2026-07-10 10:00')] is True and starts[e('2026-07-10 10:01')] is True
    assert starts[e('2026-06-29 10:01')] is False
    assert e('2026-08-07 10:05') not in starts
    assert starts[e('2026-09-30 10:02')] is True
    assert e('2026-09-30 10:02') + 60 not in starts                       # the incomplete minute
    assert e('2026-09-30 10:02') - 60 in starts and e('2026-09-30 10:01') in starts
    assert e('2026-09-30 10:02') not in [int(x) for x in b.t[~b.from_cap]]   # the master's 10:02 row was the dropped partial
    i = b.find(e('2026-07-10 10:00'))
    assert (b.o[i], b.c[i], b.v[i]) == (120.0, 121.0, 30.0)
    # the capture is stamped at bar END: the 10s series is shifted back 10 seconds
    assert b.t10[0] == e('2026-06-29 10:01')
    assert len(b.t10) == len(cap)


def test_read_tail_csv_reads_only_the_tail(tmp_path):
    rows = [(1000 + 60 * i, 1, 2, 0, 1, 5) for i in range(5000)]
    _write_master(tmp_path / 'm.csv', rows)
    df = ps._read_tail_csv(str(tmp_path / 'm.csv'), 1000 + 60 * 4000)
    assert int(df['time'].iloc[0]) == 1000 + 60 * 4000 and len(df) == 1000


# ------------------------------------------------------------------ backfill helpers

def test_match_fill_reads_utc_and_falls_back_to_pacific_when_the_minute_disagrees():
    fills = [dict(time=pd.Timestamp('2026-09-30 13:32:21'), root='MNQ', action='BUY', qty=1, price=30784.5, acct='1810769', exec_id='a'),
             dict(time=pd.Timestamp('2026-06-30 06:31:00'), root='MNQ', action='BUY', qty=1, price=30085.5, acct='1810769', exec_id='b'),
             dict(time=pd.Timestamp('2026-09-30 13:32:21'), root='MNQ', action='BUY', qty=3, price=30784.5, acct='DEMO1', exec_id='c')]
    tr = dict(date='2026-09-30', symbol='MNQ', type='LONG', entry=30784.5, size=1)
    et, note = ps.match_fill(tr, fills, '09:32')
    assert et.strftime('%Y-%m-%d %H:%M:%S') == '2026-09-30 09:32:21' and 'UTC' in note
    tr2 = dict(date='2026-06-30', symbol='MNQ', type='LONG', entry=30085.5, size=1)
    et, note = ps.match_fill(tr2, fills, '09:31')                # the row is Pacific clock: UTC would say 02:31
    assert et.strftime('%H:%M:%S') == '09:31:00' and 'Pacific' in note
    et, note = ps.match_fill(tr2, fills, '11:00')                # neither reading fits the known minute: no match
    assert et is None
    assert ps.match_fill(dict(tr, entry=1.0), fills, '09:32')[0] is None
    assert ps.match_fill(dict(tr, type='SHORT'), fills, '09:32')[0] is None     # a SELL row is needed for a short entry


def test_resolve_fill_order_fills_then_journal_then_el():
    tr = dict(date='2026-09-30', symbol='MNQ', type='LONG', entry=30784.5, size=1, entryTime='09:32')
    fills = [dict(time=pd.Timestamp('2026-09-30 13:32:21'), root='MNQ', action='BUY', qty=1, price=30784.5, acct='1', exec_id='a')]
    assert ps.resolve_fill(tr, dict(entry_time='09:32'), fills, None)[:2] == ('2026-09-30 09:32:21', 'fills.csv')
    assert ps.resolve_fill(tr, dict(entry_time='09:33'), [], None)[:2] == ('2026-09-30 09:33', 'journal')
    assert ps.resolve_fill(tr, None, [], None)[:2] == ('2026-09-30 09:32', 'el')


# ------------------------------------------------------------------ parity command (synthetic TradingView export)

def _tv_export(tmp_path, b, side_frames, flip=None, time_fmt='unix'):
    ser = {sd: b.full(sd) for sd in ('LONG', 'SHORT')}
    idx = np.arange(len(b))
    m = (b.t >= ps._epoch('2026-02-10')) & (b.t < ps._epoch('2026-02-13'))
    sel = idx[m]
    data = {'time': b.t[sel] if time_fmt == 'unix' else [ps._et_str(x, '%Y-%m-%dT%H:%M:%S') + '-05:00' for x in b.t[sel]]}
    for sd, pre in (('LONG', 'L'), ('SHORT', 'S')):
        for k in ps.KEYS:
            data['%s %s' % (pre, k)] = ser[sd][k]['hit'][sel]
        data['%s trend' % pre] = ser[sd]['d_trend']['hit'][sel]
    df = pd.DataFrame(data)
    if flip:
        col, n = flip
        mod = ps._et_fields(df['time'].to_numpy() if time_fmt == 'unix' else b.t[sel])[1]
        ok = np.flatnonzero(~df[col].isna().to_numpy() & (mod >= 600) & (mod < 660))[:n]      # regular-session rows
        df.loc[df.index[ok], col] = 1 - df.loc[df.index[ok], col]
    p = tmp_path / 'tv.csv'
    df.to_csv(p, index=False)
    return str(p)


def test_parity_command_passes_on_identical_exports_and_flags_real_disagreements(tmp_path, capsys):
    df = walk(n_days=30, seed=60)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    b = bars_of(df, t10=t10, c10=c10)
    good = _tv_export(tmp_path, b, None)
    assert ps.parity(good, 'NQ', bars=b) is True
    out = capsys.readouterr().out
    assert 'PARITY PASS' in out
    iso = _tv_export(tmp_path, b, None, time_fmt='iso')
    assert ps.parity(iso, 'NQ', bars=b) is True
    bad = _tv_export(tmp_path, b, None, flip=('L y_high', 30))
    assert ps.parity(bad, 'NQ', bars=b) is False
    out = capsys.readouterr().out
    assert 'PARITY FAIL' in out and 'y_high' in out



def test_parity_skips_the_session_after_a_weekday_with_no_bars(tmp_path, capsys):
    df = walk(n_days=30, seed=61)
    df = df[df.index.normalize() != pd.Timestamp('2026-02-11')]        # a "holiday": no bars on Wed 02-11
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    b = bars_of(df, t10=t10, c10=c10)
    path = _tv_export(tmp_path, b, None)                               # exports Tue 02-10 .. Thu 02-12
    assert ps.parity(path, 'NQ', bars=b) is True
    out = capsys.readouterr().out
    assert '390 in the regular session' in out                        # Tue only; Thursday follows the empty Wednesday


def _tv_export_span(tmp_path, b, d0, d1):
    """A parity export (the exact scores of b.full) for the dates [d0, d1] inclusive."""
    ser = {sd: b.full(sd) for sd in ('LONG', 'SHORT')}
    sel = np.flatnonzero((b.t >= ps._epoch(d0)) & (b.t < ps._epoch((pd.Timestamp(d1) + pd.Timedelta(days=1)).strftime('%Y-%m-%d'))))
    data = {'time': b.t[sel]}
    for sd, pre in (('LONG', 'L'), ('SHORT', 'S')):
        for k in ps.KEYS:
            data['%s %s' % (pre, k)] = ser[sd][k]['hit'][sel]
        data['%s trend' % pre] = ser[sd]['d_trend']['hit'][sel]
    p = tmp_path / 'tv_span.csv'
    pd.DataFrame(data).to_csv(p, index=False)
    return str(p)


def test_parity_skips_the_switch_day_and_15_sessions_after_it(tmp_path, capsys):
    df = walk(n_days=30, seed=62)
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    sw = [dict(inst=ps._epoch('2026-01-20 11:00'), offset=40.0, status='exact', et='2026-01-20 11:00', kind='mid_session')]
    b = bars_of(df, t10=t10, c10=c10, switches=sw)
    # sessions after the switch day 01-20: 21 22 23 26 27 28 29 30 | 02-02 03 04 05 06 | 09 10  = 15 -> 02-10 is the last skipped
    path = _tv_export_span(tmp_path, b, '2026-02-09', '2026-02-12')
    assert ps.parity(path, 'NQ', bars=b) is True
    out = capsys.readouterr().out
    assert '780 in the regular session' in out                         # 02-11 and 02-12 only
    assert 'plus 15 regular sessions after each' in out
    assert ps.ROLL_SKIP_SESSIONS == 15
    assert ps.parity(path, 'NQ', bars=b, skip_sessions=5) is True      # the parameter still works
    assert '1560 in the regular session' in capsys.readouterr().out    # 02-09 .. 02-12


@pytest.mark.parametrize('holiday_has_bars,n_days', [(True, 1560), (False, 1170)])
def test_parity_does_not_skip_the_session_after_a_listed_holiday(tmp_path, capsys, holiday_has_bars, n_days):
    # 2026-02-16 (Presidents Day) is in CME_HOLIDAYS, so both sides skip it as "yesterday": the Tuesday is measured, not
    # skipped. (An UNLISTED weekday with no bars is skipped: see the test above.)
    df = walk(n_days=34, seed=63)
    if not holiday_has_bars:
        df = df[df.index.normalize() != pd.Timestamp('2026-02-16')]
    t10, c10 = ten_sec(df, '2026-01-28 18:00')
    b = bars_of(df, t10=t10, c10=c10)
    path = _tv_export_span(tmp_path, b, '2026-02-13', '2026-02-18')    # Fri, Mon (holiday), Tue, Wed
    assert ps.parity(path, 'NQ', bars=b) is True
    out = capsys.readouterr().out
    assert '%d in the regular session' % n_days in out
    assert 'listed CME holidays are NOT skipped' in out


# ================================================================== DATA-BACKED (skipped without augur_uploads)

needs_data = pytest.mark.skipif(not (ps.data_available('NQ') and ps.data_available('ES')),
                                reason='augur_uploads (NOADJ masters) not present')


@needs_data
def test_worked_example_2026_09_30_0932_mnq_long_scores_9_of_9():
    # the v1.1 worked example and the owner's pre-check are EMA numbers: pinned to ma='ema'
    r = ps.score_trade(dict(sym='MNQ', side='LONG', fill='2026-09-30 09:32:21'), ma='ema')
    assert r['signal_bar'] == '2026-09-30 09:31'
    assert (r['total'], r['max'], r['na_count']) == (9, 9, 0)
    assert all(p['hit'] is True for p in r['points'])
    by = {p['k']: p for p in r['points']}
    assert by['ma200_1m']['val'] == pytest.approx(30795.25)
    # the owner's independent pre-check (raw capture bars): master / capture / roll-adjust choices move the EMAs a little
    assert by['ma200_1m']['ref'] == pytest.approx(30650.75, abs=1.0)
    assert by['ma200_5m']['ref'] == pytest.approx(30627.9, abs=1.0)
    assert by['ma200_30m']['ref'] == pytest.approx(30625.9, abs=5.0)
    assert by['ma200_10s']['ref'] == pytest.approx(30719.7, abs=1.0)
    assert by['y_low']['ref'] == 30504.5 and by['y_high']['ref'] == 30725.5
    assert by['y_close']['ref'] == pytest.approx(30617.0, abs=0.5)
    assert by['big_body']['val'] == pytest.approx(70.5) and by['big_vol']['val'] == 7945
    t = r['trend']
    assert t['hit'] is False and t['val'] == 30725.5 and t['ref'] == 30759.25     # 09-29 high below 09-28 high
    assert r['src'] == 'master1m+capture10s'
    # the same trade as a short misses almost everything
    s = ps.score_trade(dict(sym='MNQ', side='SHORT', fill='2026-09-30 09:32:21'), ma='ema')
    assert s['max'] == 9
    assert [p['hit'] for p in s['points'][:7]] == [False] * 7       # above every average and level: no short point
    assert s['points'][7]['hit'] is False                           # a green candle is not a short candle


@needs_data
def test_review_0930_findings_on_the_real_bars():
    # finding 2: the day after Memorial Day uses Friday 05-22's regular session, not the 09:30-12:59 Globex stub
    r = ps.score_trade(dict(sym='MES', side='LONG', fill='2026-05-26 10:00:30'))
    by = {p['k']: p for p in r['points']}
    assert (by['y_low']['ref'], by['y_close']['ref'], by['y_high']['ref']) == (7478.75, 7490.75, 7524.0)
    assert by['y_low']['hit'] is True and by['y_close']['hit'] is True and by['y_high']['hit'] is True
    # finding 1: 2026-07-24's capture stops at 10:46, so Monday 07-27 has NO yesterday levels (and no trend), not wrong ones
    r = ps.score_trade(dict(sym='MES', side='LONG', fill='2026-07-27 12:25:37'))
    by = {p['k']: p for p in r['points']}
    for k in ('y_low', 'y_close', 'y_high'):
        assert by[k]['hit'] is None and by[k]['na_reason'] == ps.NA_INCOMPLETE
    assert r['trend']['hit'] is None and r['trend']['na_reason'] == ps.NA_INCOMPLETE
    assert r['max'] == 9 - r['na_count'] and r['na_count'] >= 3
    # finding 4: NQ's capture lost 13:34:50-15:39:30 on 2026-08-26, so the 10s point of 15:39-15:59 is NA...
    b = ps.load_bars('NQ')
    ser = ps.score_series('NQ', 'LONG', '2026-08-26', '2026-08-26', bars=b)
    late = ser.loc['2026-08-26 15:39':'2026-08-26 15:59']
    assert len(late) == 21 and (late['ma200_10s_na'] == ps.NA_GAP10).all() and late['ma200_10s_hit'].isna().all()
    # ...while an ordinary regular session still scores it on every bar
    for root in ('NQ', 'ES'):
        day = ps.score_series(root, 'LONG', '2026-09-02', '2026-09-02').between_time('09:30', '15:59')
        assert len(day) == 390 and day['ma200_10s_hit'].notna().all()


@needs_data
@pytest.mark.parametrize('root', ['NQ', 'ES'])
def test_score_series_equals_score_trade_around_holidays_incomplete_days_and_gaps(root):
    b = ps.load_bars(root)
    stamps = ['2026-01-20 10:00', '2026-02-17 10:00', '2026-04-06 10:00', '2026-05-26 10:00', '2026-05-26 09:31',
              '2026-06-22 10:00', '2026-07-06 10:00', '2026-07-26 19:00', '2026-07-27 09:31', '2026-07-27 12:24',
              '2026-07-28 10:00', '2026-08-26 13:40', '2026-08-26 15:39', '2026-08-26 15:59', '2026-08-31 03:30',
              '2026-09-08 10:00', '2026-09-11 11:30', '2026-09-24 14:15']
    idx = [b.find(ps._epoch(s)) for s in stamps]
    idx = [i for i in idx if i >= 0]
    assert len(idx) >= 12
    _agree(b, idx)


@needs_data
def test_master_and_capture_bars_load_with_the_expected_shape():
    for root in ('NQ', 'ES'):
        b = ps.load_bars(root)
        assert b.t[0] >= ps._epoch(ps.HISTORY_FROM) and np.all(np.diff(b.t) > 0)
        assert b.from_cap.sum() > 30000                          # the summer hole is filled from the capture
        assert len(b.t10) > 500000 and b.t10[0] >= ps._epoch(ps.TEN_SEC_FROM) - 86400
        f_hole = b.find(ps._epoch('2026-07-15 10:00'))
        assert f_hole >= 0 and b.from_cap[f_hole]
        assert not b.from_cap[b.find(ps._epoch('2026-05-15 10:00'))]


@needs_data
@pytest.mark.parametrize('root', ['NQ', 'ES'])
def test_score_series_equals_score_trade_on_200_random_real_bars(root):
    b = ps.load_bars(root)
    rng = np.random.default_rng(2026 + len(root))
    # 100 random bars anywhere after the warm-up (evenings and weekends included) + the bars around every real switch
    idx = list(rng.choice(np.arange(1200, len(b) - 1), size=100, replace=False))
    for r in b.sw_rows:
        if r['inst'] > b.t[0]:
            j = int(np.searchsorted(b.t, r['inst']))
            idx += list(range(j - 3, j + 4))
    n_checked = 0
    for side in ('LONG', 'SHORT'):
        f = b.full(side)
        for i in idx:
            rec, _ = ps._literal(b, int(b.t[i]), side)
            for k, p in zip(ps.KEYS, rec['points']):
                d = f[k]
                ha = None if np.isnan(d['hit'][i]) else bool(d['hit'][i])
                assert ha == p['hit'] and ps._REASONS[d['na'][i]] == p['na_reason'], (root, side, ps._et_str(b.t[i]), k)
                if ha is not None:
                    assert d['val'][i] == pytest.approx(p['val'], abs=1e-3)
                    assert d['ref'][i] == pytest.approx(p['ref'], abs=1e-3)
                n_checked += 1
            ht = None if np.isnan(f['d_trend']['hit'][i]) else bool(f['d_trend']['hit'][i])
            assert ht == rec['trend']['hit']
    assert n_checked >= 200 * 9


@needs_data
def test_warmup_is_complete_for_every_timeframe_from_march():
    for root in ('NQ', 'ES'):
        b = ps.load_bars(root)
        f = b.full('LONG')
        i = b.find(ps._epoch('2026-03-02 10:00'))
        for k in ('ma200_1m', 'ma200_5m', 'ma200_30m'):
            assert f[k]['na'][i] == 0, (root, k)
        first30 = int(np.flatnonzero(f['ma200_30m']['na'] == 0)[0])
        assert b.t[first30] < ps._epoch('2026-02-01')             # >= 600 30m bars well before the first 2026-03 trade


@needs_data
def test_trade_relative_adjustment_matches_the_roll_table_on_roll_day():
    b = ps.load_bars('NQ')
    before = ps.score_trade(dict(sym='NQ', side='LONG', fill='2026-09-14 11:20:05'), bars=b)
    after = ps.score_trade(dict(sym='NQ', side='LONG', fill='2026-09-14 12:00:05'), bars=b)
    i = b.find(ps._epoch('2026-09-11 15:59'))
    raw_close = float(b.c[i])
    assert pt(before, 'y_close')['ref'] == pytest.approx(raw_close)                 # old contract: real
    assert pt(after, 'y_close')['ref'] == pytest.approx(raw_close + 296.5)          # new contract: shifted by the switch
    assert pt(before, 'ma200_10s')['na_reason'] == ps.NA_NO10BAR or pt(before, 'ma200_10s')['na_reason'] is None
    assert pt(after, 'ma200_10s')['na_reason'] == ps.NA_ROLL
