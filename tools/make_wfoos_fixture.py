#!/usr/bin/env python3
"""
tools/make_wfoos_fixture.py -- builds the walk-forward-detail fixtures the web probes read.

WHY THIS EXISTS (2026-09-15)
----------------------------
The engine now saves one small block per validated run, `validate.wf_oos`: every fold's
own out-of-sample trades joined in fold order (net, PF, win rate, drawdown, Sharpe,
Sortino, a <=200-point equity curve, fold boundaries). The web reads it on the run
report, Past Runs and (later) COMPARE / RUNBOARD / EXPLORE. The probes need a run that
CARRIES that block, and the only captured run fixture (tools/fixtures/run_report.json,
run #306) was saved before the block existed. Capturing a live one needs Firestore, so
this script builds the block locally, from #306's own fold rows, and never touches the
database.

WHAT IT WRITES
--------------
  tools/fixtures/run_wfoos.json       run #306 + validate.wf_oos (the "block present" case)
  tools/fixtures/run_book_synth.json  run #306 turned into a synthetic BOOK: a `book` block
                                      with legs / whole / pre_lockbox / lockbox, and no
                                      validate.wf_oos (a book tunes nothing, so it has no
                                      walk-forward detail by design). A real captured book
                                      needs Firestore; this synthetic copy is the stand-in.

HOW THE BLOCK IS BUILT
----------------------
The engine's block builder wants each fold's per-trade out-of-sample pnls, which no saved
run carries. So per fold, a DETERMINISTIC synthetic trade sequence is made that honours
every saved fold figure exactly:

  * count      = the fold's oos_trades
  * winners    = the fold's oos_wins (strictly > 0); every other trade is strictly < 0
  * grosses    = sized from the fold's own oos_pnl and oos_pf:
                   gross_loss = oos_pnl / (oos_pf - 1),  gross_win = oos_pnl + gross_loss
                 (when oos_pf <= 1 or oos_pnl <= 0 this is undefined, and a fallback of
                  gross_loss = |oos_pnl| + 1 point is used instead -- not hit on #306)
  * shapes     = winner i weighs 1 + ((7*i) % 5) / 4, loser j weighs 1 + ((3*j) % 4) / 3,
                 each set scaled to its gross
  * order      = winners are spread through the fold Bresenham-style (trade k is a winner
                 when floor((k+1)*w/n) > floor(k*w/n)), losers fill the rest in order
  * rounding   = every pnl rounded to 4 dp (as validate.py does), then the largest-magnitude
                 trade absorbs the rounding residual so sum(pnls) == oos_pnl to 4 dp

Fold dates: #306's fold rows carry bar counts, not dates, and its validate.windows has no
wf_split. Each fold's test window is placed across the optimize window by bar fraction
(fold 1 starts after fold 1's train_bars; each fold spans its test_bars), the same
approximation the report's 1C hover has always used. A fold's `to` is the day before the
next fold's `from`; the last fold ends on the optimize end date. The probes never hard-code
any of the resulting numbers: they read them back out of the JSON this script writes.

ENGINE OR FALLBACK
------------------
The block itself comes from the engine's own `analytics.wf_oos_block`, loaded read-only
from the wfoos engine worktree (the module file alone, never the package, and with byte-
code writing switched off so nothing is written into that worktree). When that file is not
importable (no worktree, no numpy), a pure-Python mirror of the same function below builds
it instead, and the block carries `src_note: 'fallback'` so nobody mistakes it for an
engine-built one. The mirror follows the engine as read on 2026-09-15: drawdown peak
seeded at $0 before the first trade, population deviation, Sharpe / Sortino annualised by
sqrt(trades per year), years floored at 0.1, money rounded to dp=1, PF to 3 dp.

Usage:
  python tools/make_wfoos_fixture.py                   # engine from the default wfoos worktree
  python tools/make_wfoos_fixture.py --engine DIR      # a different engine checkout root
  python tools/make_wfoos_fixture.py --force-fallback  # build with the pure-Python mirror
Stdlib only (plus numpy/scipy when the engine module is used).
"""
import argparse
import copy
import datetime as _dt
import importlib.util
import io
import json
import math
import os
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
FIX_DIR = os.path.join(HERE, 'fixtures')
SRC_FIX = os.path.join(FIX_DIR, 'run_report.json')
OUT_WFOOS = os.path.join(FIX_DIR, 'run_wfoos.json')
OUT_BOOK = os.path.join(FIX_DIR, 'run_book_synth.json')
#    The block builder now lives in the SHIPPED engine (the runner's own checkout), so the
#    fixture is built against exactly the code that writes real runs. The module file is read
#    and executed in isolation, never the package, and byte-code writing is off, so nothing is
#    written into that checkout.
DEFAULT_ENGINE = r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG'


# ── synthetic per-trade pnls ────────────────────────────────────────────────────────────
def fold_pnls(n, w, pnl, pf):
    """Deterministic per-trade pnls for one fold: n trades, w winners (>0), n-w losers (<0),
    summing to `pnl` (to 4 dp). See the module docstring for the rule."""
    n = int(n or 0)
    w = max(0, min(int(w or 0), n))
    if n == 0:
        return []
    L = n - w
    pnl = float(pnl)
    if w and L:
        if pf is not None and float(pf) > 1 and pnl > 0:
            gl = pnl / (float(pf) - 1.0)
        else:
            gl = abs(pnl) + 1.0
        gw = pnl + gl
        if gw <= 0:            # cannot happen with gl = |pnl| + 1, kept as a guard
            gl, gw = abs(pnl) + 1.0, abs(pnl) + 1.0 + pnl
    elif w:                    # all winners
        gw, gl = pnl, 0.0
    else:                      # all losers
        gw, gl = 0.0, -pnl
    ww = [1 + ((7 * i) % 5) / 4.0 for i in range(w)]
    lw = [1 + ((3 * j) % 4) / 3.0 for j in range(L)]
    wins = [gw * x / sum(ww) for x in ww] if w else []
    losses = [-gl * x / sum(lw) for x in lw] if L else []
    out, wi, li = [], 0, 0
    for k in range(n):
        is_win = (w > 0) and ((k + 1) * w // n > k * w // n)
        if is_win and wi < w:
            out.append(wins[wi]); wi += 1
        elif li < L:
            out.append(losses[li]); li += 1
        else:
            out.append(wins[wi]); wi += 1
    out = [round(x, 4) for x in out]
    resid = round(pnl - sum(out), 4)
    if resid:
        j = max(range(n), key=lambda i: abs(out[i]))
        out[j] = round(out[j] + resid, 4)
    return out


def fold_dates(folds, opt_from, opt_to):
    """(from, to) per fold, by bar fraction across the optimize window (see docstring)."""
    try:
        a = _dt.date.fromisoformat(str(opt_from)[:10])
        b = _dt.date.fromisoformat(str(opt_to)[:10])
    except Exception:
        return [(None, None)] * len(folds)
    tr0 = float(folds[0].get('train_bars') or 0)
    span = tr0 + sum(float(f.get('test_bars') or 0) for f in folds)
    if span <= 0:
        return [(None, None)] * len(folds)
    days = (b - a).days
    starts, acc = [], tr0
    for f in folds:
        starts.append(a + _dt.timedelta(days=int(round(days * acc / span))))
        acc += float(f.get('test_bars') or 0)
    out = []
    for i, s in enumerate(starts):
        e = (starts[i + 1] - _dt.timedelta(days=1)) if i + 1 < len(starts) else b
        out.append((s.isoformat(), e.isoformat()))
    return out


# ── pure-Python mirror of analytics.wf_oos_block (used only when the engine is absent) ──
def _ds(cum, cap, ndp):
    xs = [float(x) for x in cum]
    n = len(xs)
    if n == 0:
        return []
    if n <= int(cap):
        return [int(round(x)) for x in xs] if ndp is None else [round(x, ndp) for x in xs]
    st = n / float(cap)
    out = [xs[int(i * st)] for i in range(int(cap))]
    out[-1] = xs[-1]
    return [int(round(x)) for x in out] if ndp is None else [round(x, ndp) for x in out]


def _sh(p, years, down):
    n = len(p)
    if n < 3 or not years or years <= 0:
        return None
    m = sum(p) / n
    sd = ((sum(min(0.0, x) ** 2 for x in p) / n) ** 0.5) if down else ((sum((x - m) ** 2 for x in p) / n) ** 0.5)
    if sd <= 0:
        return None
    return (m / sd) * ((n / years) ** 0.5)


def wf_oos_block_fallback(folds, mode, dp=1, cap=200, src='validate'):
    folds = list(folds or [])
    if not folds:
        return None
    allp, offsets, rows = [], [], []
    for fr in folds:
        offsets.append(len(allp))
        pnls = [float(x) for x in (fr.get('pnls') or [])]
        oos = float(fr.get('oos_pnl'))
        if not math.isfinite(oos) or any(not math.isfinite(x) for x in pnls):
            return None
        nt = int(fr.get('oos_trades') or 0)
        if len(pnls) != nt or abs(sum(pnls) - oos) > 1e-3 * max(1, nt):
            return None
        allp.extend(pnls)
        rows.append({'f': fr.get('fold'), 'from': fr.get('from'), 'to': fr.get('to'), 'trades': nt,
                     'net': round(oos, dp)})
    t = len(allp)
    wins = sum(1 for x in allp if x > 0)
    gw = float(sum(x for x in allp if x > 0))
    gl = float(-sum(x for x in allp if x < 0))
    wl = [x for x in allp if x > 0]
    ll = [-x for x in allp if x < 0]
    cum, s, pk, mdd = [], 0.0, 0.0, 0.0
    for x in allp:
        s += x
        cum.append(s)
        pk = max(pk, s)
        mdd = min(mdd, s - pk)
    d0 = folds[0].get('from')
    d1 = folds[-1].get('to')
    try:
        years = max(0.1, (_dt.date.fromisoformat(str(d1)[:10]) - _dt.date.fromisoformat(str(d0)[:10])).days / 365.25)
    except Exception:
        years = None
    idx = _ds(list(range(t)), cap, None) if t else []

    def _start(off):
        for j, v in enumerate(idx):
            if v >= off:
                return j
        return (len(idx) - 1) if idx else 0
    pf = (gw / gl) if gl > 0 else None
    return {
        'v': 1, 'mode': mode, 'n_folds': len(folds), 'from': d0, 'to': d1,
        'years': (round(years, 3) if years is not None else None),
        'trades': t, 'wins': wins, 'win_rate': (round(100.0 * wins / t, 2) if t else 0.0),
        'net': round(float(sum(allp)), dp), 'gross_win': round(gw, dp), 'gross_loss': round(gl, dp),
        'profit_factor': (round(pf, 3) if pf is not None else None),
        'avg_win': (round(sum(wl) / len(wl), dp) if wl else None),
        'avg_loss': (round(sum(ll) / len(ll), dp) if ll else None),
        'max_drawdown': round(abs(mdd), dp),
        'sharpe': (_sh(allp, years, False) if years else None),
        'sortino': (_sh(allp, years, True) if years else None),
        'equity': _ds(cum, cap, dp), 'equity_n': t,
        'fold_idx': ([_start(o) for o in offsets] if t else [0] * len(folds)),
        'folds': rows, 'src': src, 'src_note': 'fallback',
    }


def load_engine(root):
    path = os.path.join(root, 'augur_engine', 'analytics.py')
    if not os.path.isfile(path):
        return None, 'engine module not found at %s' % path
    try:
        spec = importlib.util.spec_from_file_location('_wfoos_engine_analytics', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, 'wf_oos_block', None)
        if fn is None:
            return None, 'engine module has no wf_oos_block'
        return fn, path
    except Exception as e:           # numpy / scipy missing, syntax mid-edit, ...
        return None, 'engine import failed: %s' % e


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--engine', default=DEFAULT_ENGINE, help='engine checkout root (holds augur_engine/)')
    ap.add_argument('--force-fallback', action='store_true', help='build with the pure-Python mirror')
    a = ap.parse_args(argv)

    F = json.load(io.open(SRC_FIX, encoding='utf-8'))
    V = F['validate']
    folds = sorted([f for f in (F.get('top10_results') or []) if f and f.get('fold') is not None],
                   key=lambda f: f['fold'])
    opt = (V.get('windows') or {}).get('optimize') or [None, None]
    dates = fold_dates(folds, opt[0], opt[1])
    rows = []
    for f, (d0, d1) in zip(folds, dates):
        p = fold_pnls(f.get('oos_trades'), f.get('oos_wins'), f.get('oos_pnl'), f.get('oos_pf'))
        rows.append({'fold': f['fold'], 'pnls': p, 'oos_pnl': f.get('oos_pnl'),
                     'oos_trades': int(f.get('oos_trades') or 0), 'oos_wins': f.get('oos_wins'),
                     'oos_pf': f.get('oos_pf'), 'from': d0, 'to': d1})

    fn, where = (None, 'forced fallback') if a.force_fallback else load_engine(a.engine)
    mode = V.get('wf_best_mode')
    if fn is not None:
        blk = fn(rows, mode=mode, src='validate')
        how = 'engine analytics.wf_oos_block (%s)' % where
    else:
        blk = wf_oos_block_fallback(rows, mode, src='validate')
        how = 'pure-Python fallback mirror (%s)' % where
    if blk is None:
        print('MAKE_WFOOS: FAIL -- the block builder refused the synthetic folds (%s)' % how)
        return 1

    out = copy.deepcopy(F)
    out['validate']['wf_oos'] = blk
    out['_fixture'] = {'builder': 'tools/make_wfoos_fixture.py', 'block_from': how,
                       'base': 'tools/fixtures/run_report.json (run #306)',
                       'pnls': 'synthetic, deterministic, per-fold; see the builder docstring',
                       'fold_dates': 'bar fraction across the optimize window'}
    io.open(OUT_WFOOS, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False))

    bk = copy.deepcopy(F)
    bk['validate'].pop('wf_oos', None)
    bk['id'] = 90306
    bk['strategy'] = 'BOOK: synthetic probe book'
    bk['scope'] = 'Book'
    lbv = V.get('lockbox') or {}
    tot = float((F.get('equity') or {}).get('final') or 0) if isinstance(F.get('equity'), dict) else 0.0
    bk['book'] = {
        'name': 'SYNTHETIC PROBE BOOK', 'slices_held': 8, 'slices_n': 8,
        'legs': [{'strategy': 'NOISE_1_0.py', 'mult': 20}, {'strategy': 'ORB_3_1.py', 'mult': 20}],
        'whole': {'total_pnl': round(tot + 5000.0, 1), 'profit_factor': 1.41, 'max_drawdown': 1400.0,
                  'num_trades': 4100},
        'pre_lockbox': {'total_pnl': round(tot + 4400.0, 1), 'profit_factor': 1.43, 'max_drawdown': 1400.0,
                        'num_trades': 3700},
        'lockbox': {'total_pnl': round(float(lbv.get('pnl') or 0) + 600.0, 1), 'profit_factor': 1.12,
                    'max_drawdown': 1100.0, 'num_trades': 400},
    }
    bk['_fixture'] = {'builder': 'tools/make_wfoos_fixture.py',
                      'base': 'tools/fixtures/run_report.json (run #306)',
                      'note': 'synthetic book: a book block added, fold rows kept on purpose (the book '
                              'test must win before any fold check), no validate.wf_oos'}
    io.open(OUT_BOOK, 'w', encoding='utf-8', newline='\n').write(json.dumps(bk, ensure_ascii=False))

    print('MAKE_WFOOS: OK -- %s' % how)
    print('  run_wfoos.json : net %s pts, trades %s, wins %s, n_folds %s, mode %s, years %s, pf %s, '
          'max_dd %s, sharpe %s, sortino %s, equity %d pts, fold_idx %s'
          % (blk['net'], blk['trades'], blk['wins'], blk['n_folds'], blk['mode'], blk['years'],
             blk['profit_factor'], blk['max_drawdown'], blk['sharpe'], blk['sortino'],
             len(blk['equity']), blk['fold_idx']))
    print('  run_book_synth.json : id %s, %d legs, no wf_oos' % (bk['id'], len(bk['book']['legs'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
