"""CBU rules v1 alert check (tools/cbu_v1_alerts.py, SETUPS_PREREG_R3_CBU_V1.md section 5): every decision at bar i
reads only bars <= i, the held-base and 09:30-level readings are as written."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import cbu_v1_alerts as C  # noqa: E402
import point_score as P  # noqa: E402

COLS = ['ctx', 'level', 'candle', 'vol', 'core', 'held'] + ['sig_%s_%s' % v for v in C.VARIANTS]


def _tape(seed=0, days=16):
    """A 24-hour one-minute tape (2026-03-02.., no CME holiday) that drifts up, with a big green volume-spike bar
    every 97 minutes, so every rule fires somewhere."""
    rng = np.random.default_rng(seed)
    t0 = P._epoch('2026-03-02 00:00')
    n = days * 1440
    t = t0 + 60 * np.arange(n, dtype='int64')
    step = 0.02 + rng.normal(0, 0.5, n)
    big = (np.arange(n) % 97) == 0
    step[big] = 4.0
    c = 1000 + np.cumsum(step)
    o = c - step
    h = np.maximum(o, c) + rng.uniform(0, 0.3, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.3, n)
    v = rng.uniform(80, 120, n)
    v[big] = 600
    return t, o, h, l, c, v


def _bars(t, o, h, l, c, v):
    return P.Bars(t, o, h, l, c, v, root='NQ', switches=[])


def _equal(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype.kind == 'f':
        return np.array_equal(a, b, equal_nan=True)
    return np.array_equal(a, b)


def test_rules_fire_on_the_synthetic_tape():
    d = C.decisions(_bars(*_tape()))
    for base, win in C.VARIANTS:
        assert d['sig_%s_%s' % (base, win)].sum() > 0, (base, win)


@pytest.mark.parametrize('seed', [0, 1])
def test_decision_at_i_ignores_every_later_bar(seed):
    t, o, h, l, c, v = _tape(seed)
    full = C.decisions(_bars(t, o, h, l, c, v))
    sig = np.flatnonzero(full['core'].to_numpy())
    rng = np.random.default_rng(99)
    cuts = list(sig[[len(sig) // 4, len(sig) // 2, -2]]) + [int(np.flatnonzero(full['mod'].to_numpy() == 570)[-3])]
    for cut in cuts:
        k = cut + 1                                     # bars 0..cut stay; bars >= cut+1 are scrambled
        o2, h2, l2, c2, v2 = (x.copy() for x in (o, h, l, c, v))
        m = len(t) - k
        c2[k:] = c[k:] + rng.normal(0, 25, m)
        o2[k:] = c2[k:] - rng.normal(0, 5, m)
        h2[k:] = np.maximum(o2[k:], c2[k:]) + 3
        l2[k:] = np.minimum(o2[k:], c2[k:]) - 3
        v2[k:] = rng.uniform(1, 5000, m)
        mut = C.decisions(_bars(t, o2, h2, l2, c2, v2))
        for col in COLS + ['range_atr', 'body_atr', 'vol_x', 'bars_held', 'base_atr']:
            assert _equal(full[col].to_numpy()[:k], mut[col].to_numpy()[:k]), (col, cut)
        # and a truncated tape gives the same decisions
        tr = C.decisions(_bars(t[:k], o[:k], h[:k], l[:k], c[:k], v[:k]))
        for col in COLS:
            assert _equal(full[col].to_numpy()[:k], tr[col].to_numpy()), (col, cut)


def test_held_base_equal_touch_does_not_reset_and_height_cap():
    ph = np.full(40, 100.0)
    pl = np.full(40, 99.0)
    ph[5] = 105.0                                       # the 30-bar high, set 35 bars before i=40... outside
    ph[15] = 104.0                                      # inside the lookback (i-30 = 10): set 25 bars before i
    ph[30] = 104.0                                      # an equal touch 10 bars later must not reset the hold
    held, nb, base = C.held_base(ph, pl, 40, 1.0)
    assert nb == 25 and held and base == pytest.approx(5.0)
    pl[20] = 98.9                                       # base now 5.1 ATR tall -> not a held base
    held, nb, base = C.held_base(ph, pl, 40, 1.0)
    assert not held and base == pytest.approx(5.1)
    ph[35] = 104.5                                      # a new 30-bar high 5 bars before i -> not held
    held, nb, _ = C.held_base(ph, pl, 40, 1.0)
    assert nb == 5 and not held


def test_level_0930_uses_premarket_high_and_later_bars_use_todays_high():
    t = P._epoch('2026-03-03 04:00') + 60 * np.arange(0, 6 * 60, dtype='int64')     # 04:00..09:59
    dord, mod = P._et_fields(t)
    ph = np.full(len(t), 100.0)
    ph[mod == 8 * 60] = 110.0                           # premarket high 110 at 08:00
    ph[mod == 570] = 112.0                              # the 09:30 bar
    ph[mod == 571] = 111.0
    ref = C.level_ref(ph, dord, mod)
    assert ref[mod == 570][0] == 110.0                  # 09:30: the premarket high
    assert ref[mod == 571][0] == 112.0                  # 09:31: today's regular-session high before it
    assert ref[mod == 572][0] == 112.0
    assert np.isnan(ref[mod == 9 * 60]).all()           # premarket bars have no level


def test_episodes_merge_consecutive_bars_only():
    assert list(C.episodes([5, 6, 7, 9, 12, 13])) == [5, 9, 12]


def test_pulled_should_have_traded_entries_join_recall_out_of_sample(tmp_path, monkeypatch):
    import json
    import missed_pull as MP
    assert MP.signal_candle('10:00') == '09:59' and MP.signal_candle('09:31') == '09:30'
    rec = MP.to_record('NEW1', {'setup': 'CBU', 'symbol': 'MES', 'type': 'LONG', 'date': '2026-10-05',
                                'entryTime': '09:45', 'entry': 1.0, 'pointScore': {'v': 'ps1.1', 'total': 6, 'max': 9}})
    assert rec['signal_candle'] == '09:44' and rec['point_score']['total'] == 6
    cache = {'pulled_at': None, 'entries': {
        'NEW1': rec,
        'KHwkzW9C': MP.to_record('KHwkzW9C', {'setup': 'CBU', 'symbol': 'MNQ', 'type': 'LONG', 'date': '2026-09-30',
                                              'entryTime': '10:00'}),
        'S1': MP.to_record('S1', {'setup': 'CBD', 'symbol': 'MNQ', 'type': 'SHORT', 'date': '2026-10-05',
                                  'entryTime': '10:00'})}}
    p = tmp_path / 'missed.json'
    p.write_text(json.dumps(cache), encoding='utf-8')
    monkeypatch.setattr(C, 'MISSED_CACHE', str(p))
    ex = {e['id']: e for e in C.load_examples()}
    assert ex['missed NEW1']['sample'] == 'out' and ex['missed NEW1']['root'] == 'ES' and ex['missed NEW1']['S'] == '09:44'
    assert ex['missed KHwkzW9C']['sample'] == 'in'
    assert sum(1 for k in ex if k == 'missed KHwkzW9C') == 1 and 'missed S1' not in ex
