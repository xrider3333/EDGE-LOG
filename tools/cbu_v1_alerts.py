"""cbu_v1_alerts.py - Test 1 of SETUPS_PREREG_R3_CBU_V1.md (CBU rules v1 / CBU-Q 2.0): the ALERT CHECK.

Fires the section 2 entry rules (long, one-minute bars, decision at the close of bar i) on every NQ and ES bar
from 2026-04-07 to the latest closed session and reports, for each base x window variant:
  - alert episodes per session per market and combined (a run of consecutive signal bars counts once);
  - % of sessions with at least one;
  - recall on the 13 labelled examples (the 12 journal CBU futures trades + the 09-30 SHOULD HAVE TRADED entry):
    an alert at the signal minute or the minute after (in-sample - the rules were written from these);
  - recall on SHOULD HAVE TRADED CBU entries added after the prereg commit (out of sample).
    (the journal's 'missed' list plus the entries tools/missed_pull.py pulls from EDGELOG)
No outcome (price after the signal) is read anywhere in this file.

Bars, EMAs and yesterday's high are the POINT SCORE's (tools/point_score.py, spec ps1.1): the NOADJ 1m master plus
the NT capture in the summer hole and after the master's end, back-adjusted at the real contract switches.

    python tools/cbu_v1_alerts.py [--out C:\\EdgeLog\\_anatomy_cache\\cbu_v1_alerts]
"""
import argparse
import io
import json
import os
import sys

import numpy as np
import pandas as pd

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import point_score as P  # noqa: E402

JOURNAL = os.path.join(TOOLS, 'data', 'setup_journal.json')
PREREG_COMMIT = '918059d5'
IN_SAMPLE_MISSED = {'KHwkzW9C'}          # SHOULD HAVE TRADED entries the rules were written from
MISSED_CACHE = r'C:\EdgeLog\missed_trades\missed.json'   # tools/missed_pull.py
DATE_FROM = '2026-04-07'

# section 2, as pre-registered
ATR_N = 14              # ATR14 = mean true range of the 14 bars before i
RANGE_ATR = 1.2         # signal candle range >= 1.2 ATR14
BODY_ATR = 0.7          # green body >= 0.7 ATR14
VOL_N, VOL_MULT = 10, 1.5   # volume >= 1.5 x the mean of the 10 bars before i
HELD_LOOK, HELD_MIN, BASE_MAX_ATR = 30, 10, 5.0
PRE_OPEN = 4 * 60       # premarket 04:00-09:29 (the 09:30 candle's level)
WINDOWS = {'am': (9 * 60 + 30, 10 * 60 + 59), 'day': (9 * 60 + 30, 15 * 60 + 44)}   # signal-bar minute, inclusive
BASES = ('any', 'held')
VARIANTS = [(b, w) for b in BASES for w in WINDOWS]
USEFUL_RECALL, USEFUL_PER_DAY = 5, 3.0


def atr_before(ph, pl, pc, n=ATR_N):
    """ATR at i = mean true range of bars i-n..i-1 (NaN until n bars exist)."""
    prev = np.r_[np.nan, pc[:-1]]
    tr = np.where(np.isnan(prev), ph - pl, np.maximum(ph, prev) - np.minimum(pl, prev))
    return pd.Series(tr).rolling(n).mean().shift(1).to_numpy()


def vol_mean_before(v, n=VOL_N):
    return pd.Series(v).rolling(n).mean().shift(1).to_numpy()


def level_ref(ph, dord, mod):
    """The level bar i must close above: the highest regular-session high of today's bars before i, or on the
    09:30 bar the premarket (04:00-09:29) high. NaN where none exists or i is outside the regular session."""
    n = len(ph)
    ref = np.full(n, np.nan)
    df = pd.DataFrame({'d': dord, 'm': mod, 'h': ph})
    rth = (mod >= P.RTH_OPEN) & (mod < P.RTH_CLOSE)
    ri = np.flatnonzero(rth)
    if len(ri):
        g = df.iloc[ri].groupby('d')['h']
        prior = g.cummax().groupby(df['d'].iloc[ri]).shift(1).to_numpy()   # max of today's RTH bars before i
        ref[ri] = prior
    pre = (mod >= PRE_OPEN) & (mod < P.RTH_OPEN)
    pm = df[pre].groupby('d')['h'].max()
    first = np.flatnonzero(mod == P.RTH_OPEN)
    if len(first):
        ref[first] = pm.reindex(dord[first]).to_numpy()
    return ref


def held_base(ph, pl, i, atr_i):
    """(held, bars_held, base_atr) for bar i: the highest high of bars i-30..i-1 was set at least 10 bars before i
    (its EARLIEST bar - an equal touch later does not reset the hold), and that high minus the lowest low after it
    (up to i-1) is <= 5 ATR14."""
    lo = i - HELD_LOOK
    if lo < 0 or not np.isfinite(atr_i) or atr_i <= 0:
        return False, None, None
    w = ph[lo:i]
    j = lo + int(np.argmax(w))                       # argmax = first occurrence
    held = i - j
    after = pl[j + 1:i]
    base = (ph[j] - after.min()) / atr_i if len(after) else 0.0
    return (held >= HELD_MIN) and (base <= BASE_MAX_ATR), held, base


def decisions(b, ma=None):
    """Per-bar decision columns for one Bars object (point_score.Bars). Every column at i reads bars <= i only.
    ma: the 5m / 30m moving average - 'sma' (point score v1.2 default) or 'ema' (as pre-registered in 918059d5)."""
    f = b.full('LONG', ma or P.DEFAULT_MA)
    po, ph, pl, pc, _A = b.adjusted()
    v = np.nan_to_num(b.v)
    dord, mod = b.fields()
    hit = lambda k: f[k]['hit'] == 1                 # NA (NaN) never passes
    atr = atr_before(ph, pl, pc)
    vm = vol_mean_before(v)
    lvl = level_ref(ph, dord, mod)
    rng, body = ph - pl, pc - po
    with np.errstate(invalid='ignore'):
        d = pd.DataFrame({
            't': b.t, 'dord': dord, 'mod': mod,
            'ctx_5m': hit('ma200_5m'), 'ctx_30m': hit('ma200_30m'), 'ctx_yh': hit('y_high'),
            'level': np.isfinite(lvl) & (pc > lvl),
            'green': body > 0,
            'range_atr': rng / atr, 'body_atr': body / atr, 'vol_x': v / vm,
        })
    d['ctx'] = d.ctx_5m & d.ctx_30m & d.ctx_yh
    d['candle'] = d.green & (d.range_atr >= RANGE_ATR) & (d.body_atr >= BODY_ATR)
    d['vol'] = (d.vol_x >= VOL_MULT) | ((vm == 0) & (v > 0))
    d['session'] = (mod >= P.RTH_OPEN) & (mod < P.RTH_CLOSE) & ~np.isin(dord, P.HOLIDAY_ORD)
    d['core'] = d.ctx & d.level & d.candle & d.vol & d.session
    held = np.zeros(len(d), dtype=bool)
    bars_held = np.full(len(d), np.nan)
    base_atr = np.full(len(d), np.nan)
    for i in np.flatnonzero(d['core'].to_numpy()):
        h, nb, ba = held_base(ph, pl, i, atr[i])
        held[i] = h
        bars_held[i] = np.nan if nb is None else nb
        base_atr[i] = np.nan if ba is None else ba
    d['held'], d['bars_held'], d['base_atr'] = held, bars_held, base_atr
    for base, win in VARIANTS:
        a, z = WINDOWS[win]
        sig = d['core'] & (d['mod'] >= a) & (d['mod'] <= z)
        if base == 'held':
            sig &= d['held']
        d['sig_%s_%s' % (base, win)] = sig
    return d


def diagnose(b, d, i):
    """The conditions at one bar (for the labelled examples): what passed and what failed."""
    _, ph, pl, pc, _ = b.adjusted()
    atr = atr_before(ph, pl, pc)[i]
    h, nb, ba = held_base(ph, pl, i, atr)
    r = d.iloc[i]
    return dict(ctx_5m=bool(r.ctx_5m), ctx_30m=bool(r.ctx_30m), ctx_yh=bool(r.ctx_yh), level=bool(r.level),
                green=bool(r.green), range_atr=round(float(r.range_atr), 2), body_atr=round(float(r.body_atr), 2),
                vol_x=round(float(r.vol_x), 2), held=bool(h), bars_held=nb,
                base_atr=None if ba is None else round(float(ba), 2))


def episodes(idx):
    """Runs of consecutive signal bars -> their first bar index."""
    idx = np.asarray(sorted(idx))
    if not len(idx):
        return idx
    return idx[np.r_[True, np.diff(idx) > 1]]


def load_examples():
    j = json.load(io.open(JOURNAL, encoding='utf-8'))
    out = []
    for t in j['trades']:
        if t.get('label') == 'CBU' and t.get('asset') == 'futures':
            out.append(dict(id='journal #%s' % t['n'], date=t['date'], root=P.ROOT_OF[t['sym']], sym=t['sym'],
                            S=t.get('signal_candle') or t['entry_time'], sample='in'))
    seen = set()
    for m in j.get('missed', []):
        if m.get('setup') == 'CBU' and m.get('asset', 'futures') == 'futures' and m.get('dir', 'LONG') == 'LONG':
            seen.add(m['id'])
            out.append(dict(id='missed %s' % m['id'], date=m['date'], root=P.ROOT_OF[m['sym']], sym=m['sym'],
                            S=m['signal_candle'], sample='in' if m['id'] in IN_SAMPLE_MISSED else 'out'))
    # the owner's SHOULD HAVE TRADED log as pulled from EDGELOG by tools/missed_pull.py (outside git)
    for m in _pulled_missed():
        if (m['id'] not in seen and m.get('setup') == 'CBU' and str(m.get('type', '')).upper() == 'LONG'
                and str(m.get('symbol', '')).upper() in P.ROOT_OF and m.get('date') and m.get('signal_candle')):
            out.append(dict(id='missed %s' % m['id'], date=m['date'], root=P.ROOT_OF[str(m['symbol']).upper()],
                            sym=str(m['symbol']).upper(), S=m['signal_candle'],
                            sample='in' if m['id'] in IN_SAMPLE_MISSED else 'out'))
    return sorted(out, key=lambda r: (r['date'], r['S']))


def _pulled_missed(path=None):
    """Entries cached by tools/missed_pull.py ([] when it has never run)."""
    path = path or MISSED_CACHE
    try:
        return list(json.load(io.open(path, encoding='utf-8')).get('entries', {}).values())
    except (OSError, ValueError):
        return []


def closed_sessions(d):
    """Regular-session dates (day ordinals) from DATE_FROM that ran to their last regular bar."""
    lo = np.datetime64(DATE_FROM, 'D').astype('int64')
    s = d[d['session'] & (d['dord'] >= lo)]
    last = s.groupby('dord')['mod'].max()
    ok = P._complete(last.index.to_numpy(), last.to_numpy())
    return set(int(x) for x in last.index[ok])


def ord_str(o):
    return str(np.datetime64(int(o), 'D'))


def run(out_dir=None, quiet=False, ma=None):
    ma = ma or P.DEFAULT_MA
    res = {}
    for root in ('NQ', 'ES'):
        b = P.load_bars(root)
        d = decisions(b, ma)
        res[root] = (b, d, closed_sessions(d))
    # both markets must have closed the session for it to count in the combined rate
    common = sorted(res['NQ'][2] & res['ES'][2])
    lines = []
    say = lines.append
    say('CBU rules v1 - Test 1, the alert check (no outcomes). Prereg %s. Context lines: 200 %s.' % (PREREG_COMMIT, ma.upper()))
    say('Sessions %s..%s: %d closed regular sessions on both NQ and ES.' % (ord_str(common[0]), ord_str(common[-1]), len(common)))
    for root in ('NQ', 'ES'):
        b = res[root][0]
        say('  %s bars: %d one-minute bars, %d from the NT capture (summer hole / after the master).'
            % (root, len(b), int(b.from_cap.sum())))
    say('')
    ex = load_examples()
    rows, summary, alert_rows = [], {}, []
    cs = set(common)
    for base, win in VARIANTS:
        col = 'sig_%s_%s' % (base, win)
        per = {}
        for root in ('NQ', 'ES'):
            b, d, _ = res[root]
            sig = np.flatnonzero(d[col].to_numpy() & d['dord'].isin(cs).to_numpy())
            ep = episodes(sig)
            per[root] = pd.Series(d['dord'].to_numpy()[ep]).value_counts().reindex(common, fill_value=0)
            for i in ep:
                alert_rows.append(dict(variant='%s+%s' % (base, win), root=root,
                                       time_et=P._et_str(int(d['t'].iat[i])), close=round(float(b.c[i]), 2)))
        comb = per['NQ'] + per['ES']
        caught_in = caught_out = n_in = n_out = 0
        caught_same = 0
        for e in ex:
            b, d, _ = res[e['root']]
            s0 = P._epoch('%s %s' % (e['date'], e['S']))
            i = b.find(s0)
            hit_same = i >= 0 and bool(d[col].iat[i])
            hit_next = i >= 0 and i + 1 < len(d) and bool(d[col].iat[i + 1]) and int(d['t'].iat[i + 1]) == s0 + 60
            caught = hit_same or hit_next
            e.setdefault('caught', {})['%s+%s' % (base, win)] = 'same' if hit_same else ('next' if hit_next else '-')
            if e['sample'] == 'in':
                n_in += 1; caught_in += caught; caught_same += hit_same
            else:
                n_out += 1; caught_out += caught
        summary[(base, win)] = dict(
            nq=per['NQ'].mean(), es=per['ES'].mean(), comb=comb.mean(), comb_med=comb.median(),
            comb_p90=comb.quantile(0.9), comb_max=int(comb.max()), pct_any=100.0 * (comb > 0).mean(),
            recall_in=caught_in, recall_in_same=caught_same, n_in=n_in, recall_out=caught_out, n_out=n_out,
            useful=(caught_in >= USEFUL_RECALL) and (comb.mean() <= USEFUL_PER_DAY))
    say('ALERTS PER SESSION (episodes; a run of consecutive signal bars counts once)')
    say('  %-10s %6s %6s %9s %7s %6s %5s %10s | %-14s %-10s %s' % (
        'variant', 'NQ', 'ES', 'combined', 'median', 'p90', 'max', '%days>=1', 'recall in', 'out', 'useful?'))
    for (base, win), s in summary.items():
        say('  %-10s %6.2f %6.2f %9.2f %7.1f %6.1f %5d %9.0f%% | %2d/%-2d (%d same) %2d/%-7d %s' % (
            '%s+%s' % (base, win), s['nq'], s['es'], s['comb'], s['comb_med'], s['comb_p90'], s['comb_max'],
            s['pct_any'], s['recall_in'], s['n_in'], s['recall_in_same'], s['recall_out'], s['n_out'],
            'YES' if s['useful'] else 'no'))
    say('  useful = in-sample recall >= %d of 13 at <= %.0f alerts a day combined (section 3).' % (USEFUL_RECALL, USEFUL_PER_DAY))
    say('')
    say('THE LABELLED EXAMPLES (alert at the signal minute = same, the minute after = next)')
    for e in ex:
        b, d, _ = res[e['root']]
        i = b.find(P._epoch('%s %s' % (e['date'], e['S'])))
        dg = diagnose(b, d, i) if i >= 0 else {}
        fails = [k for k in ('ctx_5m', 'ctx_30m', 'ctx_yh', 'level', 'green') if dg and not dg[k]]
        if dg and dg['range_atr'] < RANGE_ATR: fails.append('range %.2f' % dg['range_atr'])
        if dg and dg['body_atr'] < BODY_ATR: fails.append('body %.2f' % dg['body_atr'])
        if dg and not (dg['vol_x'] >= VOL_MULT): fails.append('vol %.2fx' % dg['vol_x'])
        say('  %-10s %s %s %-4s %-17s %s | fails at S: %s | held %s (%s bars, base %s ATR)' % (
            e['sample'] + '-sample', e['date'], e['S'], e['sym'], e['id'],
            ' '.join('%s:%s' % (k, v) for k, v in e['caught'].items()),
            ', '.join(fails) or 'none', dg.get('held'), dg.get('bars_held'), dg.get('base_atr')))
    text = '\n'.join(lines)
    if not quiet:
        print(text)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        io.open(os.path.join(out_dir, 'report.txt'), 'w', encoding='utf-8').write(text + '\n')
        pd.DataFrame(alert_rows).to_csv(os.path.join(out_dir, 'alerts.csv'), index=False)
    return summary, ex, text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=r'C:\EdgeLog\_anatomy_cache\cbu_v1_alerts')
    ap.add_argument('--ma', default=None, choices=('sma', 'ema'), help='5m / 30m moving average (default: the point score default, sma)')
    a = ap.parse_args(argv)
    run(a.out, ma=a.ma)


if __name__ == '__main__':
    main()
