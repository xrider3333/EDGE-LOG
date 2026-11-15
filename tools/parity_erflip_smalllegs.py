"""Parity of MISC_ERFLIP_1_0 (hunt 44d) and MISC_SMALLLEGS_1_0 (hunt 55a = 30a + 36d + 44d) against the hunt series.

    python tools/parity_erflip_smalllegs.py [--json out.json]

Reads the NQ 5m masters on disk only (engine + registry of the shared checkout, EDGELOG_DATA_REPO; the strategy
files of this checkout) (no download), cut at 2025-06-30 17:00 ET straight after the load, and the
hunt's stored daily series (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S30, S36, S44, S55 series.pkl), cut at
2025-06-30. Compares trade DAYS and per-day net dollars (one contract, 0.533 pt round trip, $20 a point) on
2016-07-01..2025-06-30 at the files' defaults, three ways:
  direct  - the plugin's own leg functions on the master the hunt leg read (ERFLIP: noadj RTH; PREFADE: adj ETH;
            LATE30: adj RTH-of-ETH), no engine in between: the logic gap alone;
  engine  - augur_engine.run_backtest on the job's master (ERFLIP db_noadj_rth, SMALLLEGS db_noadj_eth) with the
            engine's roll plan (ratio-adjusted signals, fills re-priced raw) and cost_pts 0.533: what a validate scores;
  warm    - the engine path on a slice that starts `warm_days` day_ids before 2019-01-02, trades entering on or
            after 2019-01-02 compared with the full run (the validate's warm-start setting is enough).
Prints only match counts, per-day differences and net sums; nothing after 2025-06-30 is loaded.
"""
import argparse
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# masters + registry live in the shared checkout; a worktree has none. The ENGINE and DATA come from there (read
# only; the trial cache is pointed at a scratch file), the two strategy files from THIS checkout, by absolute path.
DATA_REPO = os.environ.get('EDGELOG_DATA_REPO', r'C:/Users/xride/OneDrive/Desktop/EDGE-LOG')
os.environ.setdefault('AUGUR_TRIAL_CACHE_DB', os.path.join(os.environ.get('TEMP', '.'), 'parity_erflip_trial_cache.db'))
sys.path.insert(0, DATA_REPO)
from augur_engine import data as D                     # noqa: E402
from augur_engine import engine as E                   # noqa: E402
from augur_engine import load_strategy                 # noqa: E402

FUT = 'C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/'
SEAL = '2025-06-30'
A0, A1 = '2016-07-01', '2025-06-30'
COST, MULT = 0.533, 20.0
WARM = {'MISC_ERFLIP_1_0.py': 480, 'MISC_SMALLLEGS_1_0.py': 520}
WARM_AT = '2019-01-02'


def load(source, session):
    m = D.find_master('NQ', '5m', session, source)
    a = D.load_master_arrays(m, date_from='2010-06-07', date_to=SEAL)
    idx = a['index']
    keep = np.asarray(idx <= pd.Timestamp(SEAL + ' 17:00', tz=idx.tz))
    out = {k: (np.asarray(v)[keep] if k in ('open', 'high', 'low', 'close', 'volume', 'day_id') else v) for k, v in a.items()}
    out['index'] = idx[keep]
    assert out['index'].max() <= pd.Timestamp(SEAL + ' 17:00', tz=idx.tz), 'SEAL'
    return out


def hunt(n, key):
    s = pickle.load(open(FUT + 'S%d/series.pkl' % n, 'rb'))[key]
    s = s.copy()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None) if getattr(s.index, 'tz', None) is not None else pd.DatetimeIndex(s.index)
    s = s.loc[:SEAL].astype(float)
    return s[s != 0].loc[A0:A1]


def daily(trades, index, net=False):
    """Trades -> net $ per session date of the exit bar (session date = bar start ET + 6 h)."""
    if not trades:
        return pd.Series(dtype=float)
    ix = pd.DatetimeIndex(index)
    ix = ix.tz_convert('US/Eastern').tz_localize(None) if ix.tz is not None else ix
    d = (ix[[int(t[1]) for t in trades]] + pd.Timedelta(hours=6)).normalize()
    v = np.array([float(t[2]) for t in trades]) - (0.0 if net else COST)
    s = pd.Series(v * MULT, index=d).groupby(level=0).sum()
    return s.loc[A0:A1]


def compare(name, mine, ref):
    """Day-level parity of two {date: net $} series (trade days only)."""
    a, b = set(mine.index), set(ref.index)
    both = sorted(a & b)
    diff = (mine.reindex(both) - ref.reindex(both)).abs()
    same = int((diff < 0.02).sum())
    o = {'cell': name, 'hunt_days': len(b), 'file_days': len(a), 'both': len(both), 'same_usd': same,
         'only_hunt': len(b - a), 'only_file': len(a - b),
         'day_match_pct': round(100.0 * same / max(len(a | b), 1), 2),
         'hunt_net': round(float(ref.sum()), 2), 'file_net': round(float(mine.sum()), 2),
         'net_gap': round(float(mine.sum() - ref.sum()), 2),
         'only_hunt_dates': [str(x.date()) for x in sorted(b - a)][:12],
         'only_file_dates': [str(x.date()) for x in sorted(a - b)][:12],
         'diff_usd_dates': [(str(x.date()), round(float(mine[x]), 2), round(float(ref[x]), 2)) for x in both
                            if abs(mine[x] - ref[x]) >= 0.02][:12]}
    print('%-34s hunt %4d file %4d both %4d same$ %4d only-hunt %3d only-file %3d match %6.2f%% net hunt %10.2f file %10.2f'
          % (name, o['hunt_days'], o['file_days'], o['both'], o['same_usd'], o['only_hunt'], o['only_file'], o['day_match_pct'],
             o['hunt_net'], o['file_net']), flush=True)
    return o


def leg_of(t, index):
    ix = pd.DatetimeIndex(index)
    ts = ix[int(t[0])].tz_convert('US/Eastern') if ix.tz is not None else ix[int(t[0])]
    hm = ts.hour * 100 + ts.minute
    return {930: '30a', 1500: '36d', 1200: '44d'}.get(hm, '?')


def strat(fname):
    return load_strategy(os.path.join(HERE, 'augur_strategies', fname))


def engine_trades(fname, arrays, params=None):
    mod = strat(fname)
    r = E.run_backtest(mod, arrays=arrays, params=params or {}, cost_pts=COST, return_trades=True)
    return (r or {}).get('trades') or [], (r or {}).get('_meta', {}).get('roll_stamp')


def warm_check(fname, arrays, full_trades):
    did = np.asarray(arrays['day_id'])
    ix = pd.DatetimeIndex(arrays['index'])
    a = int(np.searchsorted(ix, pd.Timestamp(WARM_AT + ' 00:00', tz=ix.tz)))
    w = int(np.searchsorted(did, int(did[a]) - WARM[fname], side='left'))
    sl = {k: (v[w:] if k in ('open', 'high', 'low', 'close', 'volume', 'day_id', 'index') else v) for k, v in arrays.items()}
    sl['day_id'] = sl['day_id'] - sl['day_id'][0]
    tr, _ = engine_trades(fname, sl)
    k_full = sorted((int(t[0]), int(t[1]), round(float(t[2]), 6)) for t in full_trades if int(t[0]) >= a)
    k_warm = sorted((int(t[0]) + w, int(t[1]) + w, round(float(t[2]), 6)) for t in tr if int(t[0]) + w >= a)
    same = len(set(k_full) & set(k_warm))
    o = {'file': fname, 'warm_days': WARM[fname], 'from': WARM_AT, 'full': len(k_full), 'warm': len(k_warm), 'same': same}
    print('WARM %-24s warm_days %d: full-run trades from %s %d, warm-slice %d, identical %d' % (fname, WARM[fname], WARM_AT,
                                                                                               len(k_full), len(k_warm), same), flush=True)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    args = ap.parse_args()
    out = {}
    ref = {'44d': hunt(44, '44d'), '30a': hunt(30, '30a'), '36d': hunt(36, '36d'), '55a': hunt(55, '55a')}

    # ---------------- ERFLIP
    erf = strat('MISC_ERFLIP_1_0.py')
    rth = load('db_noadj_rth', 'rth')
    g = erf._grid(rth['open'], rth['close'], rth['index'], len(rth['close']))
    out['erflip_direct'] = compare('ERFLIP 44d direct (noadj RTH)', daily(erf.erflip_trades(*g), rth['index']), ref['44d'])
    tr, stamp = engine_trades('MISC_ERFLIP_1_0.py', rth)
    out['erflip_engine'] = compare('ERFLIP 44d engine (ratio plan)', daily(tr, rth['index'], net=True), ref['44d'])
    out['erflip_roll'] = {k: (stamp or {}).get(k) for k in ('calendar', 'method', 'method_source')}
    print('  roll plan:', out['erflip_roll'], flush=True)
    out['erflip_warm'] = warm_check('MISC_ERFLIP_1_0.py', rth, tr)
    del rth, g

    # ---------------- SMALLLEGS
    sl = strat('MISC_SMALLLEGS_1_0.py')
    eth_adj = load('db_adj_eth', 'eth')
    days, G = sl._grid(eth_adj['open'], eth_adj['high'], eth_adj['low'], eth_adj['close'], eth_adj['index'], len(eth_adj['close']))
    out['30a_direct_adj'] = compare('PREFADE 30a direct (adj ETH)', daily(sl.prefade_trades(days, G), eth_adj['index']), ref['30a'])
    out['36d_direct_adj'] = compare('LATE30 36d direct (adj ETH)', daily(sl.late30_trades(days, G), eth_adj['index']), ref['36d'])
    del eth_adj, G
    eth = load('db_noadj_eth', 'eth')
    days, G = sl._grid(eth['open'], eth['high'], eth['low'], eth['close'], eth['index'], len(eth['close']))
    rs = slice(sl._RTH0, sl._RTH0 + sl._NRTH)
    out['44d_direct_eth'] = compare('ERFLIP 44d direct (noadj ETH)', daily(sl.erflip_trades(days, G['B'][:, rs], G['O'][:, rs], G['C'][:, rs]), eth['index']), ref['44d'])
    del G
    tr, stamp = engine_trades('MISC_SMALLLEGS_1_0.py', eth)
    out['smalllegs_roll'] = {k: (stamp or {}).get(k) for k in ('calendar', 'method', 'method_source')}
    print('  roll plan:', out['smalllegs_roll'], flush=True)
    by = {'30a': [], '36d': [], '44d': [], '?': []}
    for t in tr:
        by[leg_of(t, eth['index'])].append(t)
    assert not by['?'], 'a tuple that is no leg'
    for k in ('30a', '36d', '44d'):
        out[k + '_engine'] = compare('leg %s engine (ratio plan, ETH)' % k, daily(by[k], eth['index'], net=True), ref[k])
    out['55a_engine'] = compare('BASKET 55a engine (ratio plan)', daily(tr, eth['index'], net=True), ref['55a'])
    out['smalllegs_warm'] = warm_check('MISC_SMALLLEGS_1_0.py', eth, tr)
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(out, f, indent=1, default=str)


if __name__ == '__main__':
    main()
