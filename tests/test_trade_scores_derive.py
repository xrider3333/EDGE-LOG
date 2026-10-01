"""tools/trade_scores.py derive(): CLOSED THAT DAY and MAE / MFE measured between the fills.

MANAGER review 2026-09-30 (TRADING-LOG findings 9 and 10):
  * dayClose took the close of the 16:00 bar. Bars are stamped at their START, so that is the first
    bar AFTER the cash close (an after-hours bar for a stock).
  * MAE / MFE took the full range of the entry and exit bars, so a flush that printed after the
    exit fill counted as heat (MAE USED 280 percent on a trade that never touched its stop).

Synthetic bars only: no network, no C:\\EdgeLog, nothing outside tmp_path.
"""
import importlib.util
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load():
    spec = importlib.util.spec_from_file_location('trade_scores_under_test',
                                                  os.path.join(ROOT, 'tools', 'trade_scores.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ts = _load()
ET = 'America/New_York'
DATE = '2026-09-30'


def _stamp(hms):
    return pd.Timestamp('%s %s' % (DATE, hms), tz=ET)


def bars_1m(overrides=None, start='09:30', end='16:02', price=100.0):
    """A flat 1-minute session (one bar per minute, stamped at its START) with per-minute
    overrides {'HH:MM': (o, h, l, c)}."""
    overrides = overrides or {}
    idx = pd.date_range(_stamp(start + ':00'), _stamp(end + ':00'), freq='1min')
    rows = [overrides.get(k.strftime('%H:%M'), (price, price, price, price)) for k in idx]
    return pd.DataFrame(rows, index=idx, columns=['Open', 'High', 'Low', 'Close']).assign(Volume=1000)


def bars_10s(overrides=None, start='11:51:00', end='11:56:00', price=100.0):
    """A flat 10-second tape stamped at bar START with overrides {'HH:MM:SS': (o, h, l, c)}."""
    overrides = overrides or {}
    idx = pd.date_range(_stamp(start), _stamp(end), freq='10s')
    rows = [overrides.get(k.strftime('%H:%M:%S'), (price, price, price, price)) for k in idx]
    return pd.DataFrame(rows, index=idx, columns=['Open', 'High', 'Low', 'Close']).assign(Volume=10)


def trade(**kw):
    t = {'sym': 'MNQ', 'date': DATE, 'interval': '1m', 'dir': 'LONG', 'key_time': True,
         'entry_time': '11:52', 'exit_time': '11:54', 'entry': 100.0, 'exit': 100.5, 'stop': 94.0,
         'breakout_candle': '11:49'}
    t.update(kw)
    return t


# ---------------------------------------------------------------------------------- CLOSED THAT DAY
def test_day_close_is_the_last_bar_that_starts_before_1600_on_1m_bars():
    d = bars_1m({'15:59': (100, 100, 100, 50.0), '16:00': (60, 60, 60, 99.0), '16:01': (99, 99, 99, 98.0)})
    s = ts.derive_from(trade(), d)
    assert s['dayClose'] == 50.0          # the 15:59 bar's close, not the 16:00 bar's 99.0


def test_day_close_on_5m_bars_uses_the_1555_bar_not_the_after_hours_1600_bar():
    idx = pd.date_range(_stamp('09:30:00'), _stamp('16:05:00'), freq='5min')
    d = pd.DataFrame(100.0, index=idx, columns=['Open', 'High', 'Low', 'Close']).assign(Volume=1000)
    d.loc[_stamp('15:55:00'), 'Close'] = 70.0
    d.loc[_stamp('16:00:00'), 'Close'] = 99.0          # an after-hours print
    s = ts.derive_from(trade(interval='5m', entry_time='11:50', exit_time='11:55',
                             breakout_candle='11:45'), d)
    assert s['dayClose'] == 70.0


def test_day_close_keeps_the_0930_bar_and_ignores_premarket():
    d = bars_1m({'09:29': (1, 1, 1, 1.0), '09:30': (100, 100, 100, 100.0)}, start='09:00', end='09:31')
    s = ts.derive_from(trade(entry_time='09:30', exit_time='09:30', breakout_candle='09:30'), d)
    assert s['dayClose'] is not None and s['dayClose'] == 100.0


# ------------------------------------------------------------------------------------------ hold_to
FLUSH = {'11:54': (100.5, 101.0, 80.0, 81.0)}           # the flush prints in the exit minute


def test_without_hold_to_the_whole_exit_bar_counts_as_heat():
    s = ts.derive_from(trade(), bars_1m(FLUSH))
    assert s['maePct'] == 333 and s['heat'] == '1m'      # (100 - 80) / 6


def test_hold_to_trims_the_exit_bar_out_of_the_heat():
    d = bars_1m(dict(FLUSH, **{'11:53': (100, 100.5, 97.0, 100)}))
    s = ts.derive_from(trade(hold_to='11:53'), d)
    assert s['maePct'] == 50                             # (100 - 97) / 6, the 11:54 low is ignored
    assert s['mfeCap'] == 100                            # reward 0.5 of a 0.5 best move


def test_hold_to_and_hold_from_are_both_bar_start_stamps_inclusive():
    d = bars_1m({'11:52': (100, 100, 90, 100), '11:53': (100, 103, 99, 100), '11:54': (100, 110, 70, 100)})
    s = ts.derive_from(trade(hold_from='11:53', hold_to='11:53'), d)
    assert s['maePct'] == round((100 - 99) / 6 * 100)    # only the 11:53 bar
    assert s['mfeCap'] == round(0.5 / 3 * 100)


# ---------------------------------------------------------------------------------- 10-second heat
# LONG 100.0 -> 100.5, filled 11:52:37, out 11:54:40, stop 94 (risk 6).
T10 = {'entry_ts': '11:52:37', 'exit_ts': '11:54:40'}


def tape(extra=None):
    ov = {
        '11:52:20': (100, 120.0, 10.0, 100),     # ENDS 11:52:30, before the fill: a high and a low that
                                                 # printed before you were in. Must not count.
        '11:52:30': (100, 101.0, 95.5, 100),     # holds the fill second: counts (worst heat 4.5)
        '11:54:30': (100, 104.0, 99.0, 100),     # starts before the exit second: counts (best 4.0)
        '11:54:40': (100, 100.0, 70.0, 71),      # holds the exit second, starts AT it: the flush.
        '11:54:50': (71, 71.0, 60.0, 61),        # after the exit: must not count
    }
    ov.update(extra or {})
    return bars_10s(ov)


def test_10s_heat_excludes_a_high_before_the_entry_second_and_a_flush_after_the_exit():
    s = ts.derive_from(trade(**T10), bars_1m(FLUSH), tape())
    assert s['heat'] == '10s'
    assert s['maePct'] == 75                      # (100 - 95.5) / 6, NOT the 70 low or the 10 low
    assert s['mfeCap'] == round(0.5 / 4.0 * 100)  # best 104, NOT the 120 before the fill


def test_the_1m_path_on_the_same_day_shows_the_bug_the_10s_path_fixes():
    s = ts.derive_from(trade(), bars_1m(FLUSH))
    assert s['maePct'] == 333                     # the flush in the exit minute


def test_10s_bar_holding_the_entry_second_is_included_and_the_one_before_it_is_not():
    # fill at :37 -> the :30 bar (ends :40) counts, the :20 bar (ends :30) does not
    s = ts.derive_from(trade(**T10), bars_1m(), tape({'11:52:20': (100, 100, 50.0, 100),
                                                     '11:52:30': (100, 101, 99.0, 100),
                                                     '11:54:40': (100, 100, 100, 100),
                                                     '11:54:50': (100, 100, 100, 100)}))
    assert s['heat'] == '10s' and s['maePct'] == round(1 / 6 * 100)


def test_exit_bar_that_starts_at_the_exit_second_is_excluded_but_one_second_later_it_counts():
    ov = {'11:54:40': (100, 100, 70.0, 71)}
    s = ts.derive_from(trade(**T10), bars_1m(), tape(ov))
    assert s['maePct'] == 75                      # exit_ts 11:54:40: the bar starting at :40 is out
    s = ts.derive_from(trade(entry_ts='11:52:37', exit_ts='11:54:41'), bars_1m(), tape(ov))
    assert s['maePct'] == 500                     # exit_ts :41: the :40 bar started before it


def test_short_trade_mirrors_the_10s_window():
    t = trade(dir='SHORT', entry=100.0, exit=99.5, stop=106.0, **T10)
    ov = {'11:52:20': (100, 100, 10.0, 100),      # a low before the fill: best price, must not count
          '11:52:30': (100, 104.5, 99.0, 100),    # the heat: 4.5 against a short
          '11:54:30': (100, 100, 96.0, 100),      # the best while in: 4.0 in favour
          '11:54:40': (100, 130.0, 100, 129),     # a squeeze after the exit
          '11:54:50': (129, 140.0, 129, 139)}
    s = ts.derive_from(t, bars_1m(), bars_10s(ov))
    assert s['heat'] == '10s'
    assert s['maePct'] == 75 and s['mfeCap'] == round(0.5 / 4.0 * 100)


def test_a_fill_never_shows_better_than_the_fill_price():
    # nothing traded below the entry inside the window: maePct is 0, never negative
    s = ts.derive_from(trade(**T10), bars_1m(), tape({'11:52:30': (100, 101.0, 100.0, 100),
                                                     '11:54:30': (100, 104.0, 100.0, 100)}))
    assert s['heat'] == '10s' and s['maePct'] == 0


# ------------------------------------------------ the 10s slice must cover the fills, else 1m is used
def test_slice_that_stops_before_the_exit_second_falls_back_to_1m(capsys):
    short = tape().loc[:_stamp('11:54:10')]       # the capture stopped
    s = ts.derive_from(trade(**T10, hold_to='11:53'), bars_1m(FLUSH), short)
    assert s['heat'] == '1m'
    assert 'does not cover' in capsys.readouterr().err


def test_slice_with_a_hole_falls_back_to_1m():
    t10 = tape()
    t10 = t10[(t10.index < _stamp('11:53:00')) | (t10.index >= _stamp('11:53:40') + pd.Timedelta(seconds=90))]
    s = ts.derive_from(trade(**T10), bars_1m(FLUSH), t10)
    assert s['heat'] == '1m'


def test_capture_on_another_contract_month_falls_back_to_1m():
    off = tape() + 250.0                          # the capture is on the other month: fill not in its bar
    s = ts.derive_from(trade(**T10), bars_1m(FLUSH), off)
    assert s['heat'] == '1m'


def test_px_offset_is_applied_to_the_10s_bars_like_the_1m_bars():
    off = tape() + 250.0
    s = ts.derive_from(trade(px_offset=-250.0, **T10), bars_1m(FLUSH), off)
    assert s['heat'] == '10s' and s['maePct'] == 75


def test_trade_without_fill_seconds_never_uses_a_10s_slice():
    s = ts.derive_from(trade(), bars_1m(FLUSH), tape())
    assert s['heat'] == '1m'


# ------------------------------------------------------------ fill seconds from the fills log
FILLS = (
    'ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId,SignalName\n'
    '1,2026-09-30 13:32:21,1810769,MNQ 12-26,BUY,1,30784.5,0,11,\n'
    '2,2026-09-30 13:45:01,1810769,MNQ 12-26,SELL,1,30785.5,0,12,\n'
    '3,2026-09-30 15:52:37,1810769,MNQ 12-26,BUY,2,30872.25,0,13,\n'
    '4,2026-09-30 15:54:10,1810769,MNQ 12-26,SELL,1,30875.0,0,14,\n'
    '5,2026-09-30 15:54:40,1810769,MNQ 12-26,SELL,1,30872.75,0,15,\n'
    '6,2026-09-30 15:52:37,DEMO1,NQ 12-26,BUY,1,30872.25,0,16,\n'
    '7,2026-06-30 06:31:00,1810769,MNQ 09-26,BUY,1,30085.5,0,17,\n'
    '8,2026-06-30 06:31:10,1810769,MNQ 09-26,SELL,1,30117,0,18,\n')


@pytest.fixture
def fills_csv(tmp_path):
    p = tmp_path / 'fills.csv'
    p.write_text(FILLS)
    return str(p)


def test_find_fills_reads_the_fill_seconds_in_utc_and_converts_to_eastern(fills_csv):
    t = trade(entry_time='09:32', exit_time='09:45', entry=30784.5, exit=30785.5)
    assert ts.find_fills(t, fills_csv) == ('09:32:21', '09:45:01')


def test_find_fills_takes_the_last_exit_fill_of_a_scaled_exit(fills_csv):
    t = trade(entry_time='11:52', exit_time='11:54', entry=30872.25, exit=30873.875)
    assert ts.find_fills(t, fills_csv) == ('11:52:37', '11:54:40')


def test_find_fills_does_not_match_another_instrument_root(fills_csv):
    t = trade(sym='MES', entry_time='11:52', exit_time='11:54', entry=30872.25)
    assert ts.find_fills(t, fills_csv) is None


def test_find_fills_retries_the_pacific_clock_rows_of_2026_06_30(fills_csv):
    t = trade(date='2026-06-30', entry_time='09:31', exit_time='09:31', entry=30085.5, exit=30117.0)
    assert ts.find_fills(t, fills_csv) == ('09:31:00', '09:31:10')


def test_find_fills_without_a_log_or_a_match_is_none(tmp_path, fills_csv):
    assert ts.find_fills(trade(), str(tmp_path / 'missing.csv')) is None
    assert ts.find_fills(trade(entry=1.0), fills_csv) is None
    assert ts.find_fills(trade(sym='XRX'), fills_csv) is None       # a stock has no capture


# --------------------------------------------- slice from the capture -> cache -> derive, end to end
def _capture_file(dirpath, rows):
    """rows: {'HH:MM:SS' bar START: (o, h, l, c)}. NinjaTrader stamps a row at its bar END."""
    os.makedirs(dirpath, exist_ok=True)
    lines = ['time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt']
    for k in sorted(rows):
        o, h, l, c = rows[k]
        end = int(_stamp(k).timestamp()) + 10
        lines.append('%d,%s,%s,%s,%s,10,0,0,0,0,0' % (end, o, h, l, c))
    with open(os.path.join(dirpath, 'NQ_10s.csv'), 'w') as f:
        f.write('\n'.join(lines) + '\n')


def _tape_rows():
    t10 = tape()
    return {k.strftime('%H:%M:%S'): tuple(r[:4]) for k, r in t10.iterrows()}


def test_slice_is_built_from_end_stamped_capture_cached_and_reused_without_the_capture(tmp_path, monkeypatch):
    cap = str(tmp_path / 'ohlc')
    _capture_file(cap, _tape_rows())
    monkeypatch.setattr(ts, 'CACHE', str(tmp_path / 'score_bars'))
    monkeypatch.setattr(ts, 'OHLC_DIRS', (cap,))
    t = trade(**T10)
    d = ts.load_10s(t)
    assert d is not None and os.path.exists(ts.cache_path_10s(t))
    assert os.path.basename(ts.cache_path_10s(t)) == 'MNQ_2026-09-30_1152_10s.csv'
    # END stamps were moved back to bar START: the flat bar that ENDED 11:52:40 is stamped 11:52:30
    assert _stamp('11:52:30') in d.index and _stamp('11:52:40') in d.index
    assert d.loc[_stamp('11:52:30'), 'Low'] == 95.5
    # another machine: no capture at all, the committed slice is enough and gives the same frame
    monkeypatch.setattr(ts, 'OHLC_DIRS', (str(tmp_path / 'nothing_here'),))
    d2 = ts.load_10s(t)
    assert list(d2.Low) == list(d.Low) and list(d2.index) == list(d.index)


def test_derive_uses_the_cached_10s_slice_and_the_cached_1m_bars(tmp_path, monkeypatch):
    cache = tmp_path / 'score_bars'
    cache.mkdir()
    monkeypatch.setattr(ts, 'CACHE', str(cache))
    monkeypatch.setattr(ts, 'OHLC_DIRS', (str(tmp_path / 'none'),))
    bars_1m(FLUSH).to_csv(ts.cache_path('MNQ', DATE, '1m'))
    tape().to_csv(ts.cache_path_10s(trade(**T10)))
    s = ts.derive(trade(**T10))
    assert s['heat'] == '10s' and s['maePct'] == 75
    assert s['dayClose'] == 100.0
    # the same trade without stamps reads the 1m bars and shows the old inflated heat
    assert ts.derive(trade())['maePct'] == 333


def test_load_10s_is_none_when_nothing_is_cached_and_no_capture_is_here(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ts, 'CACHE', str(tmp_path / 'score_bars'))
    monkeypatch.setattr(ts, 'OHLC_DIRS', (str(tmp_path / 'none'),))
    assert ts.load_10s(trade(**T10)) is None
    assert 'no 10s slice' in capsys.readouterr().err
    assert ts.load_10s(trade()) is None               # no fill seconds: silently none


def test_attach_10s_stamps_the_fills_and_caches_the_slice(tmp_path, monkeypatch, fills_csv):
    cap = str(tmp_path / 'ohlc')
    _capture_file(cap, _tape_rows())
    monkeypatch.setattr(ts, 'CACHE', str(tmp_path / 'score_bars'))
    monkeypatch.setattr(ts, 'OHLC_DIRS', (cap,))
    t = trade(entry=30872.25, exit=30873.875)
    # the tape is priced around 100 but the fills log is priced like NQ; only the stamps matter here
    msg = ts.attach_10s(t, fills_csv)
    assert (t['entry_ts'], t['exit_ts']) == ('11:52:37', '11:54:40')
    assert 'slice cached' in msg and os.path.exists(ts.cache_path_10s(t))
    assert ts.attach_10s(trade(sym='XRX'), fills_csv) == 'no 10s capture for this trade'
    assert ts.attach_10s(trade(date='2026-06-01'), fills_csv) == 'no 10s capture for this trade'


# ------------------------------------------------------------- the daily routine hands them through
def _routine():
    spec = importlib.util.spec_from_file_location('score_routine_under_test',
                                                  os.path.join(ROOT, 'tools', 'score_routine.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _scored(sr, **kw):
    rows = lambda rub: [{'label': l, 'weight': w, 'score': w // 2, 'note': 'a short factual note'}
                        for l, w in rub]
    s = {'date': DATE, 'sym': 'MNQ', 'entry_time': '11:52', 'breakout_candle': '11:49', 'stop': 94.0,
         'setup': rows(sr.FUT_SETUP), 'exec': rows(sr.EXEC), 'overall': 50,
         'summary': 'You took a quick scalp and were out before the flush. Fine discipline overall.'}
    s.update(kw)
    return s


def test_routine_copies_fill_seconds_from_pending_and_accepts_hold_to():
    sr = _routine()
    pending = [{'sym': 'MNQ', 'date': DATE, 'dir': 'LONG', 'asset': 'futures', 'interval': '1m',
                'entry_time': '11:52', 'exit_time': '11:54', 'entry': 100.0, 'exit': 100.5, 'qty': 1,
                'entry_ts': '11:52:37', 'exit_ts': '11:54:40', 'trade_id': None}]
    fix = []
    out = sr.build_entries(pending, [_scored(sr, hold_to='11:53')], fix)
    assert fix == [] and len(out) == 1
    assert out[0]['entry_ts'] == '11:52:37' and out[0]['exit_ts'] == '11:54:40'
    assert out[0]['hold_to'] == '11:53'


def test_routine_rejects_a_malformed_hold_to_and_ignores_malformed_fill_seconds():
    sr = _routine()
    pending = [{'sym': 'MNQ', 'date': DATE, 'dir': 'LONG', 'asset': 'futures', 'interval': '1m',
                'entry_time': '11:52', 'exit_time': '11:54', 'entry': 100.0, 'exit': 100.5, 'qty': 1,
                'entry_ts': '11:52', 'exit_ts': None}]
    fix = []
    out = sr.build_entries(pending, [_scored(sr, hold_to='noon')], fix)
    assert any('hold_to must be HH:MM' in f for f in fix)
    assert 'entry_ts' not in (out[0] if out else {})
