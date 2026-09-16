#!/usr/bin/env python3
"""
tools/make_wfoos_zero_fixture.py -- a run whose saved walk-forward test took NO trades.

WHY THIS EXISTS (2026-09-16)
----------------------------
A walk-forward in which every re-tuned fold traded nothing is a real engine outcome, and the
screens disagreed about it: four of them dashed the walk-forward money with "took no trades in
the walk-forward folds" while the run report and EXPLORE printed $0 and 0 trades. The rule is
now one rule everywhere: the pooled NET ($0) and TRADES (0) are real readings; every ratio and
the drawdown dash with that sentence; the $0 and the empty drawdown never take a best mark or
a heat shade, and sort after the runs that traded. The probe needs that run in the exact shape
the engine saves, so the block is built by the engine's own helper, not typed in by hand.

WHAT IT WRITES
--------------
  tools/fixtures/run_wfoos_zero.json   run #306 (tools/fixtures/run_report.json) given its own id
                                       and strategy name, every fold row turned into a fold that
                                       tested no trade (oos_trades 0, oos_pnl 0.0, oos_wins 0,
                                       oos_pf 0.0 - what the engine writes for an empty test), and
                                       validate.wf_oos built by analytics.wf_oos_block from those
                                       folds with an empty trade list each.

The engine module is loaded READ-ONLY from the runner's checkout (the module file alone, with
byte-code writing switched off, so nothing is written there). There is no fallback: if the
engine cannot be imported this script fails, because the whole point is the engine's shape.

Usage:
  python tools/make_wfoos_zero_fixture.py                 # engine from the default checkout
  python tools/make_wfoos_zero_fixture.py --engine DIR    # a different engine checkout root
Stdlib only (plus numpy/scipy, which the engine module imports).
"""
import argparse
import copy
import importlib.util
import io
import json
import os
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
FIX_DIR = os.path.join(HERE, 'fixtures')
SRC_FIX = os.path.join(FIX_DIR, 'run_report.json')
OUT = os.path.join(FIX_DIR, 'run_wfoos_zero.json')
DEFAULT_ENGINE = r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG'
ZERO_ID = 90308
ZERO_STRATEGY = 'ZEROWF_1_0.py'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--engine', default=DEFAULT_ENGINE, help='engine checkout root (holds augur_engine/)')
    a = ap.parse_args(argv)
    eng_path = os.path.join(a.engine, 'augur_engine', 'analytics.py')
    if not os.path.isfile(eng_path):
        print('MAKE_WFOOS_ZERO: FAIL -- engine module not found at %s' % eng_path)
        return 1
    try:
        eng = _load('_wfoos_zero_engine_analytics', eng_path)
        block_fn = eng.wf_oos_block
    except Exception as e:
        print('MAKE_WFOOS_ZERO: FAIL -- engine import failed: %s' % e)
        return 1
    # the fold dates come from the same bar-fraction rule the main fixture uses
    mk = _load('_wfoos_fixture_builder', os.path.join(HERE, 'make_wfoos_fixture.py'))

    F = json.load(io.open(SRC_FIX, encoding='utf-8'))
    V = F['validate']
    out = copy.deepcopy(F)
    out['id'] = ZERO_ID
    out['strategy'] = ZERO_STRATEGY
    out['starred'] = False
    for f in out.get('top10_results') or []:
        if f and f.get('fold') is not None:
            f['oos_trades'] = 0
            f['oos_pnl'] = 0.0
            f['oos_wins'] = 0
            f['oos_win_rate'] = 0.0
            f['oos_pf'] = 0.0
    folds = sorted([f for f in (out.get('top10_results') or []) if f and f.get('fold') is not None],
                   key=lambda f: f['fold'])
    opt = (V.get('windows') or {}).get('optimize') or [None, None]
    dates = mk.fold_dates(folds, opt[0], opt[1])
    rows = [{'fold': f['fold'], 'pnls': [], 'oos_pnl': f['oos_pnl'], 'oos_trades': 0, 'oos_wins': 0,
             'oos_pf': f['oos_pf'], 'from': d0, 'to': d1} for f, (d0, d1) in zip(folds, dates)]
    blk = block_fn(rows, mode=V.get('wf_best_mode'), src='validate')
    if blk is None:
        print('MAKE_WFOOS_ZERO: FAIL -- the engine refused the empty folds')
        return 1
    out['validate']['wf_oos'] = blk
    out['_fixture'] = {'builder': 'tools/make_wfoos_zero_fixture.py',
                       'block_from': 'engine analytics.wf_oos_block (%s)' % eng_path,
                       'base': 'tools/fixtures/run_report.json (run #306)',
                       'folds': 'every fold tested no trade (oos_trades 0, oos_pnl 0.0, oos_wins 0, oos_pf 0.0)',
                       'fold_dates': 'bar fraction across the optimize window'}
    io.open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False))
    show = {k: blk[k] for k in ('v', 'mode', 'n_folds', 'from', 'to', 'years', 'trades', 'wins', 'win_rate',
                                'net', 'gross_win', 'gross_loss', 'profit_factor', 'avg_win', 'avg_loss',
                                'max_drawdown', 'sharpe', 'sortino', 'equity', 'equity_n', 'fold_idx', 'src')}
    print('MAKE_WFOOS_ZERO: OK -- id %s, %d folds, block %s' % (ZERO_ID, len(rows), json.dumps(show)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
