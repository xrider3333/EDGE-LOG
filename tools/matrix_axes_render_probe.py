#!/usr/bin/env python3
"""
tools/matrix_axes_render_probe.py -- render gate for the 1E ALL-CONFIGS axis set.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS; it never opens a run report, and
the report builders are the part of this file that keeps breaking (v64.24 and
v73.62 both shipped a crash straight past the boot gate). The 1E card's TABLE /
PARALLEL / SCATTER rail is built from ONE axis array inside poolParallelHtml, so
an axis added there lands on both drawings at once -- and an axis that throws,
prints an Infinity, or silently drops every point looks exactly like a chart that
simply has no data.

This gate seeds run documents whose win_rate / profit_factor / equity curves are
chosen BY HAND, renders the real report through renderApp() in a headless iframe,
and reads the numbers back off the drawn SVG.

WHAT IT ASSERTS
---------------
  * the PARALLEL view names EV R and SORTINO among its axes
  * the SCATTER view offers both in its two axis pickers and plots them
  * EV R equals (1 - winRate) * (profitFactor - 1) for every config, checked
    against values computed here in Python from the same seeded fields
  * a config with win_rate = 100 has NO EV R point -- not Infinity, not zero --
    and the chart says so in words
  * SORTINO is finite and ranks a smooth curve above a choppy one of the same mean
  * an axis fewer than 60% of the configs can fill still draws, marked with the
    degree sign
  * a run whose configs carry none of it still draws the chart on what is left
  * SORTINO is a ROW on every 1E family table -- GATE, TILT, HYBRID and RAW --
    and not only on the pooled ALL table (it was on neither family table before,
    which is the whole reason the owner's v73.409 ask never reached the tab he
    reads)
  * the family table and the pooled ALL table print the SAME SHARPE and SORTINO
    for the same config. They used to differ by up to 4x: the family tables
    derived them from a ~160-point saved curve while the pooled views plotted the
    engine's per-trade scalar, so ONE metric name carried TWO numbers on screen
  * a stretch the engine measured as ZERO TRADES dashes its PF / WIN % / EV R /
    DD instead of printing 0.00 / 0% / -1.00 / -$0 as measurements
  * a pooled view that had to drop configs says how many, and one that can place
    none of them says so instead of quietly reverting to a different view
  * ON THE 1A CONFIG FUNNEL: no candidate line is drawn above the plot top. The
    ALL CONFIGS overlay is built ~350 lines below the y-scale, so its 37 curves
    never reached the extent pass and the tallest was clipped off the frame
  * the GATE / TILT / HYBRID-recycle top lines are SOLID. A full-length dash read
    as "walk-forward" under the funnel's own published line procedure
  * THE ML LINES' LOCKBOX IS DRAWN FROM THE DENSE LOCKBOX TAIL (v73.761). Every ML
    curve is one 300-point sample of the whole run, which left the held-out year
    about 20 points - long straight strokes once the lockbox has a quarter of the
    width. Run 909 carries tails built by the REAL engine helpers (analytics.py,
    loaded on its own so the engine package is not imported), with a lockbox spike
    the 300-point stride steps over. Every ML line must put the tail's points past
    the door, at the tail's x positions and the true running totals; DOORS must
    still equal ONE CURVE less the door value; a tail whose door count is off by one
    (910) must draw exactly what no tail (911) draws; and the explorer payload must
    carry the stitched line on the piecewise calendar
  * EVERY OTHER TAIL GUARD IS LOAD-BEARING (review, 2026-09-13). 912 breaks each ML
    line's tail a different way - format, saved-point count, trade count, door index,
    length, door value, a value, end value, and a tail that adds no points - and must
    draw exactly 913 (no tails); good tails on a run with no lockbox panel (914) must
    draw 915; a 500-trade lockbox whose saved curves out-draw any tail (918) must draw
    919; a 4-trade lockbox with the door on the LAST saved point (916) must be stitched
  * THE DEFAULT VIEW'S FAMILY Y-SCALE FOLDS (920-922, ALL CONFIGS off): a gate, tilt,
    KEEL, hybrid or recycle top line whose lockbox tail holds the chart's peak or
    trough stays inside the plot - the ALL CONFIGS fold cannot mask a broken one there
  * IS+WF and WF+LB on the TILT / KEEL / HYBRID tables (v73.763, run #384: 32 of 32
    cells read low) read the drawdown off the engine own combined-span block, not
    the saved equity curve, the larger of the two per-stretch drawdowns, or their
    sum - a run saved before the engine wrote that block keeps the curve read,
    marked with the degree sign

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.
Stdlib plus a subprocess call to local Chrome - and augur_engine/analytics.py (numpy,
scipy) for the lockbox-tail fixtures, loaded straight from its file.
"""
import calendar
import copy
import http.server
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
PROBE_FILENAME = '_mtxaxes_probe.html'
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OPT_WIN = ['2010-01-01', '2024-01-01']          # 14.0 years, shared by every seeded run
MULT = 1                                        # dollars == points, so hand-checks stay readable


# -- seeded equity curves ------------------------------------------------------
#    cum = cumulative PnL. The SORTINO axis is derived from the period-to-period
#    CHANGES in this series, so the two curves below carry nearly the same mean
#    change and very different downside.
def _cum(diffs):
    out, run = [0.0], 0.0
    for x in diffs:
        run += x
        out.append(round(run, 6))
    return out


SMOOTH = _cum(([12.0] * 9 + [-3.0]) * 6)        # mean 10.5/period, tiny downside
CHOPPY = _cum(([40.0] * 5 + [-19.5] * 5) * 6)   # mean 10.25/period, deep downside
SHORT = [0.0, 500.0]                            # 2 points: a drawdown, but no Sortino
LB_CUM = _cum([30.0] * 9 + [-10.0])            # a lockbox tail, starting on its base
LB_GAP, LB_TAIL = 50.0, 40.0                    # what each saved curve leaves off its end


def cfg(name, is_pnl, wf_pnl, cum, wr, pf, ntr, crowned=False, metrics=True, rng=False):
    """One crown-pool candidate.

    `metrics`  -> the whole-optimize-window block every engine version saves.
    `rng`      -> the per-stretch is_rng / wf_rng blocks the v73.47 engine added.
                  With both stretches carrying the same PF and the same win rate,
                  the combined IS+WF read the report computes is that same pair,
                  so the hand calculation is unchanged.
    """
    c = {
        'params': {'knob': name},
        'is_pnl': is_pnl, 'wf_oos_pnl': wf_pnl,
        'equity': {'cum': cum, 'final': cum[-1]},
        'crowned': crowned,
    }
    if metrics:
        c['metrics'] = {'profit_factor': pf, 'win_rate': wr, 'num_trades': ntr,
                        'total_pnl': is_pnl + wf_pnl, 'avg_pnl': (is_pnl + wf_pnl) / float(ntr),
                        'max_drawdown': 400}
    if rng:
        def blk(net, n):
            return {'total_pnl': net, 'num_trades': n, 'profit_factor': pf, 'win_rate': wr,
                    'avg_pnl': net / float(n), 'max_drawdown': 200}
        c['is_rng'] = blk(is_pnl, int(ntr * 0.6))
        c['wf_rng'] = blk(wf_pnl, ntr - int(ntr * 0.6))
    return c


# -- THE HAND-CHECK TABLE ------------------------------------------------------
#    label -> (win_rate %, profit factor). EV R must come back as (1-wr)*(pf-1).
MAIN_WR_PF = [
    ('A', 40.0, 1.80),      # 0.60 * 0.80 = 0.48
    ('B', 25.0, 2.50),      # 0.75 * 1.50 = 1.125 -> 1.13 at 2dp
    ('C', 60.0, 1.20),      # 0.40 * 0.20 = 0.08
    ('D', 100.0, 3.00),     # no losing trade -> NO POINT (never Infinity, never 0)
    ('E', 50.0, 0.90),      # 0.50 * -0.10 = -0.05 (a losing config still has an EV R)
]
SMOOTH_CFGS = ('A', 'C')
CHOPPY_CFGS = ('B', 'E')


# -- ML-family fixtures (GATE / TILT / HYBRID) ---------------------------------
#    These carry the engine-written per-block SHARPE / SORTINO scalars that the
#    v73.419 engine saves, so the family tables and the pooled views can be checked
#    against each other AND against the seeded number.
GATE_SPAN = ['2010-01-01', '2025-01-01']      # 15 years: IS 7 + WF 7 + LB 1
GATE_WF0 = '2017-01-01'
GATE_LB0 = '2024-01-01'

# NOT a straight line on purpose: a perfectly linear curve has zero deviation, so the
#   OLD curve-derived SHARPE came back null and a gate watching for the wrong number
#   would have had nothing to compare. These wobble, so a curve-derived reading is a
#   real (and different) number from the engine scalar seeded on the blocks below.
FLAT = _cum(([12.0] * 9 + [-3.0]) * 6)         # ends 630
TALL = _cum(([120.0] * 9 + [-30.0]) * 6)       # ends 6300 -- 10x anything else in the run


def blk(net, n, pf, wr, dd, sh=None, so=None):
    b = {'total_pnl': net, 'num_trades': n, 'profit_factor': pf, 'win_rate': wr,
         'max_drawdown': dd, 'avg_pnl': (net / float(n) if n else 0.0)}
    if sh is not None:
        b['sharpe'] = sh
    if so is not None:
        b['sortino'] = so
    return b


ZERO_BLK = blk(0, 0, 0.0, 0.0, 0.0)            # the engine's zero-trade placeholder, verbatim


def gcand(model, th, cum, zerolb=False, so_lb=1.42):
    """One ML-gate candidate as the engine saves it."""
    return {
        'model': model, 'threshold': th,
        'pre_pnl': 120000, 'pre_rec': 10.0, 'pre_pf': 1.50, 'pre_wr': 45.0,
        'kept_pre': 1000, 'pre_sharpe': 1.11, 'pre_sortino': 1.77,
        'equity': {'cum': cum},
        'is_rng': blk(65000, 550, 1.55, 46.0, 8000, 1.21, 1.91),
        'wf_rng': blk(55000, 450, 1.45, 44.0, 9000, 1.02, 1.61),
        'lockbox': (ZERO_BLK if zerolb else blk(9000, 90, 1.35, 43.0, 2500, 0.87, so_lb)),
        'full': blk(129000, 1090, 1.48, 44.6, 11000, 1.09, 1.72),
    }


def szcand(model, cum, ntr, full_n, so_lb, scheme=None, zerolb=False):
    """One TILT (scheme set) or HYBRID (scheme None) column.

    pre / wf_lb carry the engine's own IS+WF / WF+LB blocks. Their drawdowns are
    deliberately NOT the sum of the per-stretch drawdowns above (17200 / 11700), the
    larger of the two (9100), or the saved FLAT curve own -$3 drop (each cycle dips
    3) - all four land on a different $k-rounded figure than the engine block (-$13k /
    -$10k, fmtAx: >=10000 rounds to whole thousands), so whichever wrong method a
    broken build takes is visible.
    """
    c = {'model': model, 'n_trades': ntr, 'max_size': 1,
         'equity': {'cum': cum},
         'is_rng': blk(66000, 560, 1.56, 46.0, 8100, 1.22, 1.92),
         'wf_rng': blk(56000, 460, 1.46, 44.0, 9100, 1.03, 1.62),
         'lockbox': (ZERO_BLK if zerolb else blk(9500, 95, 1.36, 43.0, 2600, 0.88, so_lb)),
         'full': blk(131500, full_n, 1.49, 44.7, 11100, 1.10, 1.73),
         'pre': blk(122000, 1020, 1.51, 45.0, 12800, 1.12, 1.78),
         'wf_lb': (blk(56000, 460, 1.46, 44.0, 10200, 1.03, 1.62) if zerolb
                   else blk(65500, 555, 1.44, 43.8, 10200, 1.01, 1.60))}
    if scheme:
        c['scheme'] = scheme
    return c


def gate_validate(tall_gate, hyb_recycle_tall):
    """The ML block. `tall_gate` gives one gate CANDIDATE a curve ten times the rest
       (the old y-scale never saw candidate curves at all). `hyb_recycle_tall` gives
       the NON-picked hybrid a tiny trade count, so its recycle factor - which is per
       hybrid - lifts it above the picked one, which is the only hybrid the old
       pre-pass ever measured."""
    return {
        'span': GATE_SPAN, 'wf_range': [GATE_WF0, GATE_LB0], 'lockbox_from': GATE_LB0,
        'thresholds': [0.5, 0.6], 'chosen': {'model': 'rf', 'threshold': 0.5},
        'selection_rule': 'net_dollars_mar_floor_80_minkeep',
        'equity': {'cum_ungated': FLAT, 'cum_gated': FLAT},
        'ungated_is': blk(70000, 700, 1.50, 45.0, 9000),
        'ungated_wf': blk(60000, 600, 1.40, 43.0, 10000),
        'ungated_lockbox': blk(10000, 100, 1.30, 42.0, 3000),
        'ungated_pre': blk(130000, 1300, 1.45, 44.0, 12000),
        'ungated_wf_lb': blk(70000, 700, 1.39, 43.0, 11000),
        'ungated_full': blk(140000, 1400, 1.44, 44.0, 12000),
        'candidates': [gcand('rf', 0.5, FLAT, so_lb=1.42),
                       gcand('logit', 0.6, (TALL if tall_gate else FLAT), so_lb=2.31),
                       gcand('xgb', 0.7, FLAT, zerolb=True)],
        'tilts': [szcand('rf', FLAT, 1400, 1400, 1.55, scheme='tier'),
                  szcand('xgb', FLAT, 1400, 1400, 1.66, scheme='linear')],
        # rf keeps 1200 of the 1400 ungated trades -> recycle 1.17x (this one is picked,
        #   on net dollars); xgb keeps only 400 -> recycle 3.50x, which is what escapes.
        'hybrids': [szcand('rf', FLAT, 1200, 1200, 1.44),
                    szcand('xgb', (_cum(([9.6] * 9 + [-2.4]) * 6) if hyb_recycle_tall else FLAT), 400, 400, 1.88)],
    }


def run_doc(rid, cands):
    return {
        'id': rid, '_lite': False, 'strategy': 'PROBE_1_0.py', 'instrument': 'NQ',
        'timeframe': '5m', 'multiplier': MULT, 'timestamp': '2026-08-31T00:00:00Z',
        'scope': 'validate', 'date_from': OPT_WIN[0], 'date_to': OPT_WIN[1],
        'best_pnl_usd': 1000, 'best_pf': 1.5, 'best_trades': 500, 'best_win_rate': 40,
        'best_dd_usd': 100, 'days_in_test': 5113,
        'selection': {'candidates': cands},
        'validate': {'windows': {'optimize': OPT_WIN}, 'verdict': 'PASS', 'n_folds': 4},
    }


def _pool3():
    """908's raw pool: the five ML-run configs, each WITH a lockbox tail, every saved curve
       stopping short of its true total the way the engine's sampled curves do."""
    ml3 = [cfg(n, i, w, cu, wr, pf, ntr, crowned=(n == 'A'), rng=True)
           for (n, wr, pf), (i, w, cu, ntr) in zip(
               MAIN_WR_PF,
               [(4000, 3000, SMOOTH, 500), (3500, 2600, CHOPPY, 400),
                (3000, 2200, SMOOTH, 620), (2500, 1800, SMOOTH, 90),
                (2000, 1400, CHOPPY, 300)])]
    for c in ml3:
        base = c['equity']['cum'][-1] + LB_GAP
        c['equity']['final'] = base
        c['lb_equity'] = {'cum': [base + v for v in LB_CUM], 'base': base,
                          'final': base + LB_CUM[-1] + LB_TAIL}
    return ml3


# -- 909 / 910 / 911: THE ML LOCKBOX TAIL (v73.761) ------------------------------
#    An engine-faithful ML block on 908's raw pool. 1,400 trades, the first 1,300 before the
#    lockbox (908's ungated counts), so every 300-point saved curve keeps 21 points past the
#    door - the #384 shape. Each row's curve AND its lockbox tail are built by the real
#    augur_engine/analytics.py helpers from one per-trade series, exactly as ml_gate does.
#    The lockbox trades swing in blocks of six (+400 / -330), so a line bent at the wrong
#    point, or drawn from the sparse sample, reads visibly off the true running total.
#    One non-top gate candidate books +SPIKE on trade 1336 and gives it back on 1337: the
#    300-point stride samples 1334 and 1339 and never sees it, the tail keeps it, and it is
#    the tallest value on the chart - so a y-scale that folds the saved curve instead of the
#    drawn one puts that line off the top.
LBT_N, LBT_I0 = 1400, 1300
LBT_SPIKE_AT = 1336
_LBT = {'mod': None, 'err': None, 'block': None, 'built': {}}


def _analytics():
    """augur_engine/analytics.py loaded from its own file (the package __init__ pulls in the
       whole engine), or None with the reason in _LBT['err']."""
    if _LBT['mod'] is None and _LBT['err'] is None:
        try:
            spec = importlib.util.spec_from_file_location(
                '_mtxaxes_analytics', os.path.join(REPO, 'augur_engine', 'analytics.py'))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for nm in ('downsample_curve', 'lockbox_tail', 'LB_TAIL_CAP'):
                if not hasattr(mod, nm):
                    raise AttributeError('analytics.py has no %s' % nm)
            _LBT['mod'] = mod
        except Exception as e:
            _LBT['err'] = '%s: %s' % (type(e).__name__, e)
    return _LBT['mod']


def _lbt_u(i, i0=LBT_I0):
    """The ungated per-trade PnL. Sub-dollar parts so the gate's 1-decimal curve is exercised."""
    frac = ((i * 37) % 10) * 0.037
    if i < i0:
        return (40.0 if i % 10 != 9 else -60.0) + frac
    return (400.0 if ((i - i0) // 6) % 2 == 0 else -330.0) + frac


def _lbt_build(i0=LBT_I0, spikes=('gc-logit-60',), troughs=(), no_recycle=False, only_if_denser=True):
    """(gate_validate block, expectations, spike size) for one lockbox-tail run. Each expectation
       is one drawn ML line: its family, payload id, full per-trade cumulative curve, saved equity
       dict and the factor the funnel multiplies it by.
       i0          - the door (pre-lockbox trades of LBT_N);
       spikes      - line ids ('gate' is the chosen gate) that book +SPIKE on trade LBT_SPIKE_AT and
                     give it back on the next trade: the 300-point stride steps over it, the tail
                     keeps it; troughs do the same downwards;
       no_recycle  - every hybrid keeps all trades, so the funnel draws no recycle line;
       only_if_denser=False - tails even where they add no points (a tail the funnel must refuse)."""
    key = (i0, tuple(spikes), tuple(troughs), no_recycle, only_if_denser)
    if key in _LBT['built']:
        return _LBT['built'][key]
    A = _analytics()
    if A is None:
        return None
    np = A.np
    ii = np.arange(LBT_N)
    u = np.array([_lbt_u(int(i), i0) for i in ii])
    cap = int(A.LB_TAIL_CAP)
    g = gate_validate(tall_gate=False, hyb_recycle_tall=False)
    g['ungated_pre'] = blk(130000, i0, 1.45, 44.0, 12000)
    g['ungated_lockbox'] = blk(10000, LBT_N - i0, 1.30, 42.0, 3000)
    g['ungated_full'] = blk(140000, LBT_N, 1.44, 44.0, 12000)
    series = []          # (family, payload id, per-trade pnl array, row template, factor)
    keep_g = ii % 7 != 3
    for model, th, keep in (('rf', 0.5, keep_g), ('logit', 0.6, ii % 5 != 4), ('xgb', 0.7, ii % 3 != 0)):
        series.append(('cand', 'gc-%s-%d' % (model, round(th * 100)), np.where(keep, u, 0.0),
                       gcand(model, th, [0.0]), 1.0))
    for model, scheme, size in (('rf', 'tier', np.array([0.5, 1.0, 1.0, 2.0])[ii % 4]),
                                ('xgb', 'linear', 0.75 + 0.125 * (ii % 5))):
        t = szcand(model, [0.0], LBT_N, LBT_N, 1.55 if model == 'rf' else 1.66, scheme=scheme)
        t['kept_pre'] = i0
        series.append(('tilt', 'tilt-%s-%s' % (model, scheme), size * u, t, 1.0))
    for model, keep, size, so_lb in (('rf', keep_g, 1.25, 1.44),
                                     ('xgb', ii % 4 != 0, 0.9 + 0.1 * (ii % 3), 1.88)):
        kept = int(keep.sum())
        full_n = LBT_N if no_recycle else kept
        h = szcand(model, [0.0], full_n, full_n, so_lb)
        h['kept_pre'] = int(keep[:i0].sum())
        series.append(('hyb', 'hyb-%s' % model, np.where(keep, size * u, 0.0), h,
                       1.0 if no_recycle else float(LBT_N) / kept))
    k = szcand('keel', [0.0], LBT_N, LBT_N, 1.5, scheme='skill-gated expectancy tilt')
    k.update({'version': 'v12', 'kept_pre': i0, 'crownable': False, 'avg_size': 1.0, 'max_size': 1.3,
              'trust_mean': 0.1, 'trust_on': 0.2, 'member_trust': {}, 'sizes': {}, 'cutoff': None,
              'rule': 'probe keel', 'wf_lb': blk(9600, 96, 1.37, 43.0, 2600, 0.89, 1.5)})
    series.append(('keel', 'keel', (0.7 + 0.12 * (ii % 6)) * u, k, 1.0))
    # the spike: taller than anything else the chart draws, recycle lines and raw pool included
    tallest = max([float(np.cumsum(p).max()) * f for (_fm, _id, p, _t, f) in series] + [10000.0])
    spike = float(round(1.6 * tallest, -3))

    def _bump(sid, p):
        if sid in spikes or sid in troughs:
            s = spike if sid in spikes else -spike
            p = p.copy()
            p[LBT_SPIKE_AT] += s
            p[LBT_SPIKE_AT + 1] -= s
        return p
    rows = []
    cands, tilts, hybs = [], [], []
    for fam, sid, p, row, f in series:
        p = _bump(sid, p)
        cf = np.cumsum(p)
        cum = A.downsample_curve(cf, cap=300, ndp=None)
        eq = {'cum': cum, 'n': LBT_N}
        tail = A.lockbox_tail(cf, i0, len(cum), cap, None, only_if_denser=only_if_denser)
        if tail is not None:
            eq['lb_tail'] = tail
        row['equity'] = eq
        {'cand': cands, 'tilt': tilts, 'hyb': hybs}.get(fam, []).append(row)
        if fam == 'keel':
            g['keel'] = row
        ex = {'fam': fam, 'id': sid, 'cf': cf.tolist(), 'eq': eq, 'ck': 'cum', 'lk': 'lb_tail', 'f': 1.0,
              'spiked': sid in spikes}
        rows.append(ex)
        if fam == 'hyb' and not no_recycle:
            rows.append(dict(ex, fam='hyb2', id='hybr-' + sid[4:], f=f))
    # the chosen gate: rf @ 50%, on the curve's own 1-decimal rounding, as ml_gate saves it
    cfg_ = np.cumsum(_bump('gate', np.where(keep_g, u, 0.0)))
    geq = {'cum_ungated': A.downsample_curve(np.cumsum(u)), 'cum_gated': A.downsample_curve(cfg_), 'n': LBT_N}
    gt = A.lockbox_tail(cfg_, i0, len(geq['cum_gated']), cap, 1, only_if_denser=only_if_denser)
    if gt is not None:
        geq['lb_tail_gated'] = gt
    rows.append({'fam': 'gate', 'id': 'gate', 'cf': cfg_.tolist(), 'eq': geq, 'ck': 'cum_gated',
                 'lk': 'lb_tail_gated', 'f': 1.0, 'spiked': 'gate' in spikes})
    g.update({'equity': geq, 'candidates': cands, 'tilts': tilts, 'hybrids': hybs,
              'thresholds': [0.5, 0.6, 0.7]})
    _LBT['built'][key] = (g, rows, spike)
    return _LBT['built'][key]


def lbt_block():
    """909's block: the #384 shape, good tails, the spike on one non-top gate candidate."""
    if _LBT['block'] is None:
        _LBT['block'] = _lbt_build()
    return _LBT['block']


# -- 912 / 913: THE GUARD GAUNTLET. Every tail holder of 909's block carries a tail broken in
#    exactly ONE way that one _mlTail guard - and only that guard - refuses, so a later edit
#    that drops any of them draws a line 913 (the same run with no tails) does not.
#    The broken tails stay otherwise engine-real: the too-long one and the thin one are cut by
#    the real helper, the rest are 909's tails with one field changed.
GAUNTLET = (
    ('gate', 'end', 'last tail value 0.1 off the saved final value'),
    ('gc-rf-50', 'v', 'unknown tail format v=2'),
    ('gc-logit-60', 'pts', 'cut for 299 saved points, the curve has 300'),
    ('gc-xgb-70', 'n', 'the curve says 1,401 trades, the block 1,400'),
    ('tilt-rf-tier', 'j0', 'door index 6 before the one the saved sampling rule gives'),
    ('tilt-xgb-linear', 'long', 'more tail points than lockbox trades'),
    ('hyb-rf', 'base', 'door value saved as text'),
    ('hyb-xgb', 'value', 'one tail value saved as text'),
    ('keel', 'thin', 'a 20-point tail where the saved curve already has 21 points past the door'),
)


def _lbt_gauntlet(gv, rows):
    """-> (the gauntlet block for 912, its no-tail control for 913)."""
    A = _analytics()
    out = copy.deepcopy(gv)
    by_id = {r['id']: r for r in rows}
    holders = {'gate': out['equity'], 'keel': out['keel']['equity']}
    for r in out['candidates']:
        holders['gc-%s-%d' % (r['model'], round(r['threshold'] * 100))] = r['equity']
    for r in out['tilts']:
        holders['tilt-%s-%s' % (r['model'], r['scheme'])] = r['equity']
    for r in out['hybrids']:
        holders['hyb-%s' % r['model']] = r['equity']
    L = LBT_N - LBT_I0
    for sid, how, _why in GAUNTLET:
        e, ex = holders[sid], by_id[sid]
        tk = ex['lk']
        t = e[tk]
        if how == 'end':
            t['cum'][-1] = round(t['cum'][-1] + 0.1, 1)
        elif how == 'v':
            t['v'] = 2
        elif how == 'pts':
            t['pts'] = t['pts'] - 1
        elif how == 'n':
            e['n'] = LBT_N + 1
        elif how == 'j0':
            t['j0'] = t['j0'] - 6
        elif how == 'long':
            full = A.lockbox_tail(A.np.array(ex['cf']), LBT_I0, len(e[ex['ck']]), L, None, only_if_denser=False)
            e[tk] = dict(full, cum=[full['base']] + full['cum'])
        elif how == 'base':
            t['base'] = str(t['base'])
        elif how == 'value':
            t['cum'][40] = str(t['cum'][40])
        elif how == 'thin':
            e[tk] = A.lockbox_tail(A.np.array(ex['cf']), LBT_I0, len(e[ex['ck']]), 20, None,
                                   only_if_denser=False)

    def _drop(e, key):
        del e[key]
    return out, _lbt_edit(out, _drop)


def _lbt_edit(gv, fn):
    """A deep copy of a gate_validate block with fn applied to every lockbox-tail holder:
       fn(equity_dict, key) for each lb_tail* key found."""
    out = copy.deepcopy(gv)
    holders = [out.get('equity')] + [r.get('equity') for r in
                                     (out.get('candidates') or []) + (out.get('tilts') or []) +
                                     (out.get('hybrids') or []) + [out.get('keel') or {}]]
    for e in holders:
        if isinstance(e, dict):
            for key in [x for x in e if str(x).startswith('lb_tail')]:
                fn(e, key)
    return out


def build_runs():
    main = [
        cfg('A', 4000, 3000, SMOOTH, 40.0, 1.80, 500, crowned=True),
        cfg('B', 3500, 2600, CHOPPY, 25.0, 2.50, 400),
        cfg('C', 3000, 2200, SMOOTH, 60.0, 1.20, 620),
        cfg('D', 2500, 1800, SMOOTH, 100.0, 3.00, 90),
        cfg('E', 2000, 1400, CHOPPY, 50.0, 0.90, 300),
    ]
    # PARTIAL: only 2 of 5 configs carry a curve long enough to have a Sortino, so
    #   the axis is kept (two is the minimum) but wears the degree sign (< 60%).
    partial = [
        cfg('P1', 4000, 3000, SMOOTH, 40.0, 1.80, 500, crowned=True),
        cfg('P2', 3500, 2600, CHOPPY, 30.0, 2.00, 400),
        cfg('P3', 3000, 2200, SHORT, 45.0, 1.50, 300),
        cfg('P4', 2500, 1800, SHORT, 35.0, 1.70, 250),
        cfg('P5', 2000, 1400, SHORT, 55.0, 1.10, 220),
    ]
    # BARE: no metrics block at all and 2-point curves -> no PF, no WIN %, no EV R,
    #   no SORTINO. The chart must still draw on NET $ / MAX DD / MAR.
    bare = [
        cfg('N1', 4000, 3000, SHORT, None, None, 1, crowned=True, metrics=False),
        cfg('N2', 3500, 2600, SHORT, None, None, 1, metrics=False),
        cfg('N3', 3000, 2200, SHORT, None, None, 1, metrics=False),
    ]
    # MODERN: the same five configs as a v73.47+ engine saves them - per-stretch
    #   is_rng / wf_rng blocks - so the report reads PF and WIN % through _rawP
    #   rather than through the whole-window fallback the legacy run exercises.
    modern = [cfg(n, i, w, cu, wr, pf, ntr, crowned=(n == 'A'), rng=True)
              for (n, wr, pf), (i, w, cu, ntr) in zip(
                  MAIN_WR_PF,
                  [(4000, 3000, SMOOTH, 500), (3500, 2600, CHOPPY, 400),
                   (3000, 2200, SMOOTH, 620), (2500, 1800, SMOOTH, 90),
                   (2000, 1400, CHOPPY, 300)])]
    kpi = run_doc(905, main)
    # KPI: the OTHER 1E chart on the same card - one line per PHASE (IS / WF / LB /
    #   TOTAL) rather than per config. It already carried SORTINO; v73.405 gives it
    #   EV R, so the two charts describe the same measures.
    kpi['top10_results'] = [
        {'fold': 1, 'train_bars': 6000, 'test_bars': 2000, 'oos_pnl': 1500,
         'profit_factor': 1.60, 'win_rate': 45.0, 'num_trades': 300},
        {'fold': 2, 'train_bars': 6000, 'test_bars': 2000, 'oos_pnl': 1800,
         'profit_factor': 1.70, 'win_rate': 44.0, 'num_trades': 320},
    ]
    kpi['validate'] = {
        'windows': {'optimize': OPT_WIN, 'lockbox': ['2024-01-01', '2025-01-01']},
        'verdict': 'PASS', 'n_folds': 2, 'lb_idx': 48,
        'equity': SMOOTH,
        'is_dd': 300, 'total_dd': 500,
        'is_sharpe': 1.4, 'total_sharpe': 1.6, 'total_sortino': 2.3,
        'total_win_rate': 40.0, 'is_pf': 1.8,
        'total_avg_win': 260.0, 'total_avg_loss': 140.0,
        'total_trades': 620, 'is_trades': 400,
        'lockbox': {'pnl': 900, 'pf': 1.45, 'win_rate': 38.0, 'trades': 120,
                    'sharpe': 1.1, 'sortino': 1.9, 'dd': 250,
                    'avg_win': 240.0, 'avg_loss': 150.0, 'bars': 2000},
    }
    # 906 / 907: the same raw pool with a real ML block hung off it. 906 has a gate
    #   CANDIDATE curve ten times the rest; 907 has none, so the tallest thing on its
    #   funnel is the RECYCLE line of the hybrid that was NOT picked. Both were drawn
    #   off the top of the plot before the y-scale learned to fold them in.
    ml = [cfg(n, i, w, cu, wr, pf, ntr, crowned=(n == 'A'), rng=True)
          for (n, wr, pf), (i, w, cu, ntr) in zip(
              MAIN_WR_PF,
              [(4000, 3000, SMOOTH, 500), (3500, 2600, CHOPPY, 400),
               (3000, 2200, SMOOTH, 620), (2500, 1800, SMOOTH, 90),
               (2000, 1400, CHOPPY, 300)])]
    r906 = run_doc(906, ml)
    r906['gate_validate'] = gate_validate(tall_gate=True, hyb_recycle_tall=False)
    r906['equity_top'] = [{'cum': SMOOTH}, {'cum': CHOPPY}]
    r906['validate']['windows']['lockbox'] = [GATE_LB0, GATE_SPAN[1]]
    r907 = run_doc(907, ml)
    r907['gate_validate'] = gate_validate(tall_gate=False, hyb_recycle_tall=True)
    r907['equity_top'] = [{'cum': SMOOTH}, {'cum': CHOPPY}]
    r907['validate']['windows']['lockbox'] = [GATE_LB0, GATE_SPAN[1]]
    # 908: 906's pool WITH lockbox tails on the raw configs, so the funnel has all three panels
    #   (906 / 907 have none, so DOORS draws two). Every saved curve stops short of its true
    #   total, as the engine's sampled curves do: the raw curve by LB_GAP, the lockbox tail by
    #   LB_TAIL. The tilt / hybrid blocks carry the trade counts that place their lockbox door.
    r908 = run_doc(908, _pool3())
    g908 = gate_validate(tall_gate=False, hyb_recycle_tall=False)
    for blk_ in g908['tilts']:
        blk_['kept_pre'] = 1300
        blk_['equity']['n'] = 1400
    for blk_ in g908['hybrids']:
        blk_['equity']['n'] = 1400
    r908['gate_validate'] = g908
    r908['equity_top'] = [{'cum': SMOOTH}, {'cum': CHOPPY}]
    r908['validate']['windows']['lockbox'] = [GATE_LB0, GATE_SPAN[1]]
    runs = [run_doc(901, main), run_doc(902, partial), run_doc(903, bare),
            run_doc(904, modern), kpi, r906, r907, r908]
    # 923: 908's pool saved as an OLD run - before the engine wrote pre / wf_lb
    #   blocks onto tilt / hybrid columns, so a two-stretch pick must still fall back
    #   to the saved curve (marked with the degree sign) rather than go blank or crash.
    r923 = copy.deepcopy(r908)
    r923['id'] = 923
    for _row923 in r923['gate_validate']['tilts'] + r923['gate_validate']['hybrids']:
        _row923.pop('pre', None)
        _row923.pop('wf_lb', None)
    runs.append(r923)
    # 909: the lockbox-tail block; 910: the same with every tail's door count off by one, which
    #   the web must refuse; 911: the same with the tails removed - an old run
    lb = lbt_block()
    if lb is not None:
        def _i0_off(e, key):
            e[key]['i0'] = e[key]['i0'] + 1

        def _drop(e, key):
            del e[key]
        def _lbt_run(rid, gv, pool=None):
            r = run_doc(rid, pool if pool is not None else _pool3())
            r['gate_validate'] = copy.deepcopy(gv)
            r['equity_top'] = [{'cum': SMOOTH}, {'cum': CHOPPY}]
            r['validate']['windows']['lockbox'] = [GATE_LB0, GATE_SPAN[1]]
            return r
        for rid, gv in ((909, lb[0]), (910, _lbt_edit(lb[0], _i0_off)), (911, _lbt_edit(lb[0], _drop))):
            runs.append(_lbt_run(rid, gv))
        # 912 / 913: the guard gauntlet and its no-tail twin
        gnt, gnt0 = _lbt_gauntlet(lb[0], lb[1])
        runs += [_lbt_run(912, gnt), _lbt_run(913, gnt0)]
        # 914 / 915: good tails on a run whose RAW configs have no lockbox panel (906's pool) - the
        #   funnel has no lockbox stretch to put them in, so they must change nothing
        runs += [_lbt_run(914, lb[0], pool=ml), _lbt_run(915, _lbt_edit(lb[0], _drop), pool=ml)]
        # 916 / 917: a lockbox of 4 trades, so only the final saved point is past the door (j0 = 299 =
        #   pts-1). The most stretched line there is: its tail must be drawn
        tiny = _lbt_build(i0=LBT_N - 4, spikes=())
        runs += [_lbt_run(916, tiny[0]), _lbt_run(917, _lbt_edit(tiny[0], _drop))]
        # 918 / 919: a lockbox of 500 of the 1,400 trades. Each saved curve already has 107 points
        #   past the door against 81 for a tail, so the engine writes none; 918 carries tails cut
        #   anyway, and the funnel must refuse every one of them (draw exactly 919)
        short = _lbt_build(i0=900, spikes=(), only_if_denser=False)
        runs += [_lbt_run(918, short[0]), _lbt_run(919, _lbt_edit(short[0], _drop))]
        # 920-922: the DEFAULT view (ALL CONFIGS off), where only the family top lines draw and only
        #   the family y-scale folds size the axis. Each run gives one family top the chart's peak
        #   and (920, 921) another its deepest trough, in the lockbox tail only
        runs.append(_lbt_run(920, _lbt_build(spikes=('gate',), troughs=('keel',))[0]))
        runs.append(_lbt_run(921, _lbt_build(spikes=('tilt-rf-tier', 'tilt-xgb-linear'),
                                             troughs=('hyb-rf', 'hyb-xgb'), no_recycle=True)[0]))
        runs.append(_lbt_run(922, _lbt_build(spikes=('hyb-rf', 'hyb-xgb'))[0]))
    return runs


CASES = [
    # name, run id, prefs written into augurPrefs before renderApp()
    ('main-parallel', 901, {'cfgTab': 'raw', 'mtxView': 'parallel', 'mtxCols': 'both'}),
    ('main-scatter-evr-so', 901, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both',
                                  'mtxSX': 'EV R', 'mtxSY': 'SORTINO'}),
    ('main-scatter-so-evr', 901, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both',
                                  'mtxSX': 'SORTINO', 'mtxSY': 'EV R'}),
    # v73.7x: MAR is annualised and R / YR is new -- plot them so their dot values can be
    #   hand-checked (a scatter tooltip carries only the two axes it draws).
    ('main-scatter-mar-rpy', 901, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both',
                                   'mtxSX': 'MAR', 'mtxSY': 'R / YR'}),
    # v73.50x: ROC % / YR is the one axis that is NOT leverage-blind, so its arithmetic is
    #   worth gating too -- net per year over the ACCT account, default $100,000.
    ('main-scatter-roc', 901, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both',
                               'mtxSX': 'MAR', 'mtxSY': 'ROC % / YR'}),
    ('main-ratios-only', 901, {'cfgTab': 'raw', 'mtxView': 'parallel', 'mtxCols': 'ratio'}),
    ('main-numbers-only', 901, {'cfgTab': 'raw', 'mtxView': 'parallel', 'mtxCols': 'num'}),
    ('partial-parallel', 902, {'cfgTab': 'raw', 'mtxView': 'parallel', 'mtxCols': 'both'}),
    ('partial-scatter', 902, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both',
                              'mtxSX': 'EV R', 'mtxSY': 'SORTINO'}),
    ('bare-parallel', 903, {'cfgTab': 'raw', 'mtxView': 'parallel', 'mtxCols': 'both'}),
    ('bare-scatter', 903, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both'}),
    ('bare-table', 903, {'cfgTab': 'raw', 'mtxView': 'table', 'mtxCols': 'both'}),
    ('modern-parallel', 904, {'cfgTab': 'raw', 'mtxView': 'parallel', 'mtxCols': 'both'}),
    ('modern-scatter', 904, {'cfgTab': 'raw', 'mtxView': 'scatter', 'mtxCols': 'both',
                             'mtxSX': 'EV R', 'mtxSY': 'SORTINO'}),
    ('kpi-parallel', 905, {'cfgTab': 'kpi', 'mtxView': 'parallel', 'mtxCols': 'both'}),
    ('kpi-scatter', 905, {'cfgTab': 'kpi', 'mtxView': 'scatter', 'mtxCols': 'both',
                          'mtxSX': 'EV R', 'mtxSY': 'SORTINO'}),
    # -- the ML family TABLES. SORTINO must be a row on each, filled from the engine
    #    block, and equal to what the pooled ALL table prints for the same config.
    ('ml-gate-lb', 906, {'cfgTab': 'gate', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'lb'}),
    ('ml-tilt-lb', 906, {'cfgTab': 'tilt', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'lb'}),
    ('ml-hyb-lb', 906, {'cfgTab': 'hyb', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'lb'}),
    ('ml-raw-lb', 906, {'cfgTab': 'raw', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'lb'}),
    ('ml-all-lb', 906, {'cfgTab': 'all', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'lb'}),
    # a pick that SKIPS a stretch can pool nothing - it must say so, not silently
    #   fall through to a different view.
    ('ml-all-islb', 906, {'cfgTab': 'all', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'is,lb'}),
    # v73.763: IS+WF / WF+LB must read the engine's pre / wf_lb blocks, not the
    #   saved curve - on 908 (new run, carries both blocks) and on 923 (an old run
    #   with those blocks stripped off, which must keep the marked curve read).
    ('ml-tilt-iswf', 908, {'cfgTab': 'tilt', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'is,wf'}),
    ('ml-tilt-wflb', 908, {'cfgTab': 'tilt', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'wf,lb'}),
    ('ml-hyb-iswf', 908, {'cfgTab': 'hyb', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'is,wf'}),
    ('ml-hyb-wflb', 908, {'cfgTab': 'hyb', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'wf,lb'}),
    ('ml-tilt-iswf-old', 923, {'cfgTab': 'tilt', 'mtxView': 'table', 'mtxCols': 'both', 'g2samp': 'is,wf'}),
    # -- the 1A CONFIG FUNNEL, ALL CONFIGS on.
    ('funnel-gatecand', 906, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1}),
    ('funnel-hybrcy', 907, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1}),
    # the same two funnels in DOORS: each stretch its own panel, every line restarting at $0
    ('funnel-doors-gatecand', 906, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2doors': 1}),
    ('funnel-doors-hybrcy', 907, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2doors': 1}),
    # and a run WITH a lockbox panel, drawn both ways so DOORS can be checked against ONE CURVE
    ('funnel-3p', 908, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-doors-3p', 908, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1, 'a2doors': 1}),
    # the ML lockbox tail: good tails (909), tails whose door count is off by one (910), none (911)
    ('funnel-3p-lb', 909, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-doors-3p-lb', 909, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1, 'a2doors': 1}),
    ('funnel-3p-lbbad', 910, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-doors-3p-lbbad', 910, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1, 'a2doors': 1}),
    ('funnel-3p-lbnone', 911, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-doors-3p-lbnone', 911, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1, 'a2doors': 1}),
    # every _mlTail guard, one broken tail each (912) against the same run with no tails (913)
    ('funnel-lb-gauntlet', 912, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-lb-gauntlet0', 913, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    # good tails with no RAW lockbox panel (914) against none (915)
    ('funnel-lb-nopanel', 914, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-lb-nopanel0', 915, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    # a 4-trade lockbox, door on the last saved point (916) against none (917)
    ('funnel-lb-tiny', 916, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-lb-tiny0', 917, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    # a 500-trade lockbox whose saved curves out-draw any tail (918) against none (919)
    ('funnel-lb-short', 918, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    ('funnel-lb-short0', 919, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1, 'a2kAll': 1}),
    # the default view, ALL CONFIGS off: family top lines holding the chart's peak / trough
    ('funnel-ft-gate-keel', 920, {'repCols': '3', 'eqTab': 'funnel'}),
    ('funnel-ft-tilt-hyb', 921, {'repCols': '3', 'eqTab': 'funnel'}),
    ('funnel-ft-recycle', 922, {'repCols': '3', 'eqTab': 'funnel'}),
]

PROBE_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>1E axes probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var RUNS  = __RUNS__;
var CASES = __CASES__;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow, d=w.document;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      w.eval('window.__PROBE_RUNS='+JSON.stringify(RUNS)+';');
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], rid=CASES[i][1], pref=CASES[i][2];
        var r={axes:[],dots:[],pickers:[],warn:'',degTitle:'',headline:''};
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(pref))+");"
          +"runHistory=JSON.parse(JSON.stringify(window.__PROBE_RUNS));"
          +"activeTab='augur';augurSub='runs';augurRunSel="+JSON.stringify(rid)+";"
          +"renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        // The ALL-CONFIGS chart is the ONE wrapper carrying the "ALL CONFIGS . N"
        //   headline; both PARALLEL and SCATTER print it. Anchor on it rather than
        //   guessing which of the report's many <svg>s is the right one.
        var wrap=null, sp=d.querySelectorAll('span');
        // the KPI (phase) chart carries no "ALL CONFIGS" headline, so find it by the
        //   one axis caption only it and the all-configs chart draw.
        if(pref.cfgTab==='kpi'){
          var svs=d.querySelectorAll('svg');
          for(var y=0;y<svs.length;y++){
            if((svs[y].textContent||'').indexOf('SORTINO')>=0){wrap=svs[y].parentElement;break;}}
        }
        for(var q=0;q<sp.length;q++){
          var tx=sp[q].textContent||'';
          if(tx.indexOf('ALL CONFIGS')===0&&!wrap&&pref.cfgTab!=='kpi'){r.headline=tx.trim();wrap=sp[q].parentElement&&sp[q].parentElement.parentElement;}
          if(tx.indexOf('not plotted')>=0)r.warn=tx.trim();
          if(tx.indexOf('only some configs carry')>=0)r.degTitle=sp[q].getAttribute('title')||'';
        }
        if(wrap){
          var sv=wrap.querySelector('svg');
          if(sv){var t=sv.querySelectorAll('text');
            for(var k=0;k<t.length;k++){
              var fw=t[k].getAttribute('font-weight');
              if(fw!=='700'&&fw!=='800')continue;
              // an axis carrying its own explanation hangs it on an SVG <title>, which
              //   renders nothing but DOES land in textContent. Drop it before reading.
              var cl=t[k].cloneNode(true), ti=cl.querySelectorAll('title');
              for(var ttl=0;ttl<ti.length;ttl++)ti[ttl].parentNode.removeChild(ti[ttl]);
              r.axes.push(cl.textContent);
              if(t[k].querySelector('title')){
                r.axTips=(r.axTips||[]).concat([cl.textContent.trim()]);
                // and prove the <title> is NOT being painted: the caption's drawn width
                //   must match its visible name, not the paragraph hanging off it.
                var wpx=0; try{wpx=t[k].getComputedTextLength();}catch(e){wpx=-1;}
                r.axTipW=(r.axTipW||[]).concat([[cl.textContent.trim(),Math.round(wpx)]]);}}}
          // SCATTER: every dot carries its label and BOTH rendered values on data-tip.
          var cs=wrap.querySelectorAll('circle[data-tip]');
          for(var c2=0;c2<cs.length;c2++)r.dots.push(cs[c2].getAttribute('data-tip'));
          var sc=wrap.querySelectorAll('[data-distview]');
          for(var pz=0;pz<sc.length;pz++){
            var key=sc[pz].getAttribute('data-distview')||'';
            if(key.indexOf('mtxS')===0)r.pickers.push(key.split(':')[0]+'='+sc[pz].textContent.trim());}
        }
        // ---- 1E FAMILY TABLES: every [data-mtxcol] cell, keyed column -> row label.
        //      A family table row and the pooled ALL table row for the same config must
        //      print the same number; they did not, for SHARPE, by up to 4x.
        r.cells={}; r.hdr={};
        (function(){
          var trs=d.querySelectorAll('tr');
          for(var a=0;a<trs.length;a++){
            var tds=trs[a].querySelectorAll('td');
            if(tds.length<2)continue;
            var lbl=(tds[0].innerText||tds[0].textContent||'').trim();
            if(!lbl)continue;
            for(var b=1;b<tds.length;b++){
              var k=tds[b].getAttribute('data-mtxcol');
              if(!k)continue;
              (r.cells[k]=r.cells[k]||{})[lbl]=(tds[b].innerText||tds[b].textContent||'').trim();}}
          var ths=d.querySelectorAll('th[data-mtxcol]');
          for(var c3=0;c3<ths.length;c3++)r.hdr[ths[c3].getAttribute('data-mtxcol')]=(ths[c3].innerText||'').trim();
          // the pooled ALL table: the one table whose first header cell is FAMILY
          var tbs=d.querySelectorAll('table');
          for(var t2=0;t2<tbs.length;t2++){
            var hs=tbs[t2].querySelectorAll('thead th');
            if(!hs.length||(hs[0].innerText||'').trim().toUpperCase().indexOf('FAMILY')!==0)continue;
            var hd=[];for(var t3=0;t3<hs.length;t3++)hd.push((hs[t3].innerText||'').trim());
            var rr=tbs[t2].querySelectorAll('tbody tr'),outR=[];
            for(var t4=0;t4<rr.length;t4++){var cc=rr[t4].querySelectorAll('td'),row={};
              for(var t5=0;t5<cc.length&&t5<hd.length;t5++)row[hd[t5]]=(cc[t5].innerText||'').trim();
              outR.push(row);}
            r.allTable={head:hd,rows:outR};break;}
        })();
        // ---- 1A CONFIG FUNNEL geometry, in SVG user units.
        //      The plot top edge is py, straight off the chart's own axis header, so a
        //      point with y < py is a value drawn ABOVE the axis maximum.
        r.funnel=null;
        (function(){
          var box=d.querySelector('div[data-a2eqx]');
          if(!box)return;
          var sv=box.querySelector('svg'); if(!sv)return;
          var xh=null;
          try{var a2=sv.getAttribute('data-xh'); if(a2)xh=JSON.parse(decodeURIComponent(a2));}catch(e){}
          var pt=(xh&&xh.py!=null)?+xh.py:6;
          var f={pt:pt,axisMax:(xh&&xh.y1!=null)?+xh.y1:null,axisMin:(xh&&xh.y0!=null)?+xh.y0:null,groups:{},lines:[]};
          f.H=+((sv.getAttribute('viewBox')||'').split(/[\s,]+/)[3])||140;
          var els=sv.querySelectorAll('polyline,path');
          for(var i2=0;i2<els.length;i2++){
            var el=els[i2],kg=null,p=el,hidden=false;
            while(p&&p!==sv){if(p.getAttribute&&p.getAttribute('data-kg')){kg=p.getAttribute('data-kg');break;}p=p.parentNode;}
            var q3=el; while(q3&&q3!==sv){if(q3.getAttribute&&/display:\s*none/.test(q3.getAttribute('style')||'')){hidden=true;break;}q3=q3.parentNode;}
            var key=(kg||'(untagged)')+(hidden?' [HIDDEN]':'');
            var nums;
            if(el.tagName.toLowerCase()==='polyline')nums=(el.getAttribute('points')||'').trim().split(/[\s,]+/).map(Number);
            else nums=(el.getAttribute('d')||'').replace(/[MLC]/g,' ').trim().split(/[\s,]+/).map(Number);
            var g=f.groups[key]||(f.groups[key]={n:0,minY:null,over:0,dash:''});
            for(var j2=0;j2+1<nums.length;j2+=2){var yv=nums[j2+1];
              if(!isFinite(yv))continue;
              g.n++; if(g.minY===null||yv<g.minY)g.minY=yv;
              if(yv<pt-0.05)g.over++;}
            if(kg&&el.tagName.toLowerCase()==='polyline'&&!/dd$/.test(kg)){
              var mk=/dzc[^)]*?(\d)\)$/.exec(el.getAttribute('clip-path')||''),se=el.closest?el.closest('[data-selidx]'):null;
              f.lines.push({kg:kg,k:mk?+mk[1]:null,sel:se?se.getAttribute('data-selidx'):null,pts:nums});}
            var ds=el.getAttribute('stroke-dasharray')||'(solid)';
            g.dash=g.dash?(g.dash.indexOf(ds)>=0?g.dash:(g.dash+' | '+ds)):ds;}
          // what the fullscreen explorer payload says each ALL CONFIGS line ends at -
          //   the population the tile draws, measured against the axis it drew them on.
          try{var ser=w._a2EqSeries||[],lim=f.axisMax,over=[],peak=-1e18,peakId=null;
            ser.forEach(function(s){if(!s||!s.eq||!s.eq.length)return;
              if(s.famTop||s.dim)return;
              if(!(s.gateCand||s.tiltCand||s.hybCand||s.hybRcy))return;
              var e=Math.max.apply(null,s.eq);
              if(e>peak){peak=e;peakId=s.id;}
              if(lim!=null&&e>lim+0.5)over.push({id:s.id,peak:Math.round(e)});});
            f.drawnMax=(peak>-1e17)?peak:null; f.drawnMaxId=peakId; f.overSeries=over;
          }catch(e){f.serErr=String(e);}
          // DOORS: the panel scales ride the crosshair payload; every walk-forward / lockbox piece
          //   must begin on its own panel's $0 line
          try{var wrp=sv.parentElement,a3=wrp&&wrp.getAttribute('data-a2dz'),x3=a3?JSON.parse(decodeURIComponent(a3)):null;
            var vb3=(sv.getAttribute('viewBox')||'').split(/[\s,]+/).map(Number),VH3=vb3[3]||140;
            f.dz=(x3&&x3.s)||null;f.dzEbF=(x3&&x3.ebF!=null)?+x3.ebF:null;f.dzClips=sv.querySelectorAll('clipPath[id^="dzc"]').length;f.dzStartBad=[];f.dzPieces=0;
            if(f.dz){var pT3=x3.ptF*VH3,pB3=x3.ebF*VH3;
              sv.querySelectorAll('polyline[clip-path]').forEach(function(el){
                var m3=/dzc[^)]*?(\d)\)$/.exec(el.getAttribute('clip-path')||'');if(!m3)return;
                var k3=+m3[1],z3=f.dz[k3];if(k3<1||!z3)return;f.dzPieces++;
                var y03=pB3-(pB3-pT3)*(0-z3[2])/(z3[3]-z3[2]);
                var nn3=(el.getAttribute('points')||'').trim().split(/[\s,]+/).map(Number);
                if(nn3.length>=2&&Math.abs(nn3[1]-y03)>0.35&&f.dzStartBad.length<6)f.dzStartBad.push({panel:k3,y:nn3[1],zero:+y03.toFixed(2)});});}
          }catch(e){f.dzErr=String(e);}
          // THE LOCKBOX STRIPE: its x span is the lockbox door and the right edge, and its foot is
          //   the equity pane's floor - enough to read any vertex back into dollars
          try{var lbr=sv.querySelector('rect[fill="rgba(167,139,250,.16)"]');
            if(lbr){f.lbX0=+lbr.getAttribute('x');f.lbX1=f.lbX0+(+lbr.getAttribute('width'));
              f.eqB=(+lbr.getAttribute('y'))+(+lbr.getAttribute('height'));}}catch(e){f.lbErr=String(e);}
          // the lockbox-tail runs: every polyline as drawn (points, stroke, dash - no clip ids, they
          //   carry the run id) and the explorer payload's ML series in full
          if(rid>=909){
            f.polys=[];sv.querySelectorAll('polyline').forEach(function(el){
              f.polys.push((el.getAttribute('points')||'')+'|'+(el.getAttribute('stroke')||'')+'|'+(el.getAttribute('stroke-dasharray')||''));});
            f.ser=[];(w._a2EqSeries||[]).forEach(function(s){
              if(!s||s.dim||!(s.gateChosen||s.gateCand||s.tiltCand||s.hybCand||s.hybRcy||s.id==='keel'))return;
              f.ser.push({id:s.id,famTop:!!s.famTop,hasSp:Object.prototype.hasOwnProperty.call(s,'sp'),
                          sp:(s.sp==null?null:s.sp),li:s.li,wfi:s.wfi,eq:s.eq,ts:s.ts});});}
          r.funnel=f;
        })();
        var ap=d.getElementById('app'); r.appLen=ap?ap.innerHTML.length:-1;
        r.nMtxCol=d.querySelectorAll('[data-mtxcol]').length;
        r.nSvg=d.querySelectorAll('svg').length;
        r.nCirc=d.querySelectorAll('circle').length;
        var _bt=(ap?ap.textContent:'');
        r.hasDrop=_bt.indexOf('not shown - no drawdown')>=0;
        r.hasTile=_bt.indexOf('nothing to pool on this SAMPLE')>=0;
        r.body=_bt.replace(/[^ -~]/g,'.').slice(0,300);
        r.tabs=(function(){var o=[];var e=d.querySelectorAll('[data-cfgtab]');for(var z=0;z<e.length;z++)o.push(e[z].textContent.trim());return o;})();
        r.err=(d.body.textContent.indexOf("couldn't render")>=0)?'runDetail threw':'';
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e)+' '+(e&&e.stack);}
    document.getElementById('o').textContent='MTXAXES: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},3500);});
  setTimeout(function(){report('backstop');},40000);
})();
</script>
</body></html>
"""


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def make_handler(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass
    return H


def render(keep=False):
    chrome = find_chrome()
    if not chrome:
        return None, 'no chrome found', ''
    pdir = os.path.join(REPO, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    html = (PROBE_HTML.replace('__RUNS__', json.dumps(build_runs()))
                      .replace('__CASES__', json.dumps(CASES)))
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(html)
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(REPO))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    out = ''
    try:
        with tempfile.TemporaryDirectory() as ud:
            args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                    '--hide-scrollbars', '--virtual-time-budget=40000',
                    '--user-data-dir=' + ud, '--dump-dom', url]
            try:
                out = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                     errors='replace', timeout=180).stdout or ''
            except subprocess.TimeoutExpired:
                return None, 'chrome timed out', ''
    finally:
        if not keep:
            try:
                os.remove(ppath)
                os.rmdir(pdir)
            except OSError:
                pass
    m = re.search(r'MTXAXES: (\{.*?\})\s*<', out, re.S)
    if not m:
        return None, 'probe produced no reading', out
    # --dump-dom serialises the <pre> text node, so one level of HTML escaping sits
    #   over the JSON. Undo exactly that one level (lt/gt before amp) - a blanket
    #   html.unescape would also eat the &middot; entities inside the tooltips.
    txt = m.group(1).replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return json.loads(txt), None, out


_TIPNUM = r'([-+]?[0-9]*\.?[0-9]+|Infinity|-Infinity|NaN)'


def tip_val(tip, axis):
    # the trailing '%' matters: a percentage axis renders <b>3%</b>, and without this the
    # parser silently returned None -- which reads as "the dot did not draw" rather than
    # "the probe cannot read it". ROC % / YR and DD % are both this shape.
    m = re.search(re.escape(axis) + r' <b>' + _TIPNUM + r'%?</b>', tip or '')
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return m.group(1)


def tip_label(tip):
    """The dot's printed label, e.g. '<b>RAW</b> &middot; R2 &middot; -'."""
    m = re.search(r'</b>\s*(?:&middot;|·)\s*(.*?)<br>', tip or '')
    return (m.group(1).strip() if m else (tip or '')[:60])


def _plain(t):
    """A rendered column header or CONFIG cell, stripped to its comparable name."""
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z0-9%() /.]+', ' ', t or '')).strip().upper()


def _row(rows, label):
    """One metric row out of a scraped [data-mtxcol] column, by its printed label."""
    for k, v in (rows or {}).items():
        if _plain(k).split('\u00b7')[0].strip() == label.upper():
            return v
    return None


def _num(t):
    if t is None:
        return None
    t = str(t).replace('\u00b0', '').replace(',', '').replace('%', '').replace('$', '').strip()
    if t in ('', '-', '\u2014', '\u2013'):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _rnd(v):
    return ('%.0f' % v) if isinstance(v, (int, float)) else v


def which_cfg(label, names):
    """Map a rendered dot back to a seeded config.

    The 1E column label is the WALK-FORWARD RANK ("R1", "R2", ...), not the knob
    name, and the candidates are ranked by wf_oos_pnl - which the fixture seeds in
    descending order, so rank N is the Nth entry of MAIN_WR_PF.
    """
    m = re.search(r'R(\d+)', label or '')
    if not m:
        return None
    i = int(m.group(1)) - 1
    return names[i] if 0 <= i < len(names) else None


def main():
    # the axis captions carry the inverted-arrow and degree-sign glyphs; a cp1252
    #   console would raise on the first print rather than report a result.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    keep = '--keep' in sys.argv
    d, why, raw = render(keep)
    if d is None:
        print('1E AXES PROBE: INCONCLUSIVE (%s)' % why)
        if keep and raw:
            print(raw[:4000])
        return INCONCLUSIVE
    cs = d.get('cases') or {}
    if d.get('err') or not cs:
        print('1E AXES PROBE: INCONCLUSIVE (%s)' % (d.get('err') or 'no cases ran'))
        return INCONCLUSIVE
    print('1E AXES PROBE: version %s, %d cases' % (d.get('VERSION'), len(cs)))
    bad = []
    names = [x[0] for x in MAIN_WR_PF]

    for nm, _rid, _pref in CASES:
        r = cs.get(nm)
        if not r:
            bad.append(nm + ': never ran')
            continue
        print('  %-22s axes=%s' % (nm, r['axes']))
        # the parallel view hangs a hover target on every vertex; only the scatter's
        #   dots carry a config and its two rendered values, so only those are listed.
        for t in (r['dots'] if _pref.get('mtxView') == 'scatter' else []):
            print('      dot %-24s EV R=%-8s SORTINO=%-8s'
                  % (tip_label(t)[:24], tip_val(t, 'EV R'), tip_val(t, 'SORTINO')))
        if r.get('warn'):
            print('      warn: %s' % r['warn'])
        if r.get('degTitle'):
            print('      deg:  %s' % r['degTitle'])
        if r['call'] != 'OK':
            bad.append(nm + ': ' + str(r['call'])[:400])
        if r.get('err'):
            bad.append(nm + ': ' + r['err'])
        if r['appLen'] < 2000:
            bad.append('%s: app rendered almost nothing (%s chars)' % (nm, r['appLen']))

    # -- 1. both axes exist, on both views ------------------------------------
    mp = cs.get('main-parallel') or {}
    for want in ('EV R', 'SORTINO'):
        if want not in (mp.get('axes') or []):
            bad.append('main-parallel: no %s axis (drew %s)' % (want, mp.get('axes')))
    tips = (cs.get('main-parallel') or {}).get('axTips') or []
    for nmw, wpx in ((cs.get('main-parallel') or {}).get('axTipW') or []):
        # roughly 6px per character at font-size 10; a painted tooltip paragraph would
        #   be hundreds of pixels wide.
        if wpx < 0 or wpx > max(40, len(nmw) * 12):
            bad.append('main-parallel: caption %r is drawn %spx wide - the hover text is '
                       'being painted into the chart' % (nmw, wpx))
        else:
            print('  caption    %-10s drawn %spx wide (visible name only)' % (nmw, wpx))
    for want in ('EV R', 'SORTINO'):
        if not any(t.startswith(want) for t in tips):
            bad.append('main-parallel: %s carries no explanation on hover (tips on %s)'
                       % (want, tips))
    ms = cs.get('main-scatter-evr-so') or {}
    caps = ms.get('axes') or []
    if not (len(caps) == 2 and caps[0].startswith('EV R') and caps[1].startswith('SORTINO')):
        bad.append('main-scatter: the pair asked for was not drawn (captions %s)' % caps)
    for c in caps:
        if 'higher is better' not in c:
            bad.append('main-scatter: %r does not say which end is good' % c)
    pk = ms.get('pickers') or []
    # v73.405 made the picker append how many configs record each measure, so the option
    # label is "EV R 4" rather than "EV R". Match the measure NAME, not the decoration.
    for want in ('mtxSX=EV R', 'mtxSY=EV R', 'mtxSX=SORTINO', 'mtxSY=SORTINO'):
        if not any(o == want or o.startswith(want + ' ') for o in pk):
            bad.append('main-scatter: axis picker missing %s (has %s)' % (want, pk))

    # -- 2. EV R is exactly (1-wr)*(pf-1) for every config that has one --------
    got = {}
    for t in ms.get('dots') or []:
        n = which_cfg(tip_label(t), names)
        if n:
            got[n] = (tip_val(t, 'EV R'), tip_val(t, 'SORTINO'))
    print('  rendered by config: %s' % got)
    for lbl, wr, pf in MAIN_WR_PF:
        if wr >= 100:
            continue
        exact = (1 - wr / 100.0) * (pf - 1)
        if lbl not in got:
            bad.append('EV R: config %s drew no point at all' % lbl)
            continue
        gotv = got[lbl][0]
        # the axis prints two decimals, so the rendered figure must sit within half
        #   a display unit of the closed form -- which settles the exact-half cases
        #   (0.75 * 1.50 = 1.125) without arguing about a rounding convention.
        if not isinstance(gotv, float) or abs(gotv - exact) > 0.005 + 1e-9:
            bad.append('EV R: config %s rendered %s, hand calculation says %.4f'
                       % (lbl, gotv, exact))
        else:
            print('  hand-check %-3s  (1 - %.2f) * (%.2f - 1) = %-8.4f  rendered %.2f   OK'
                  % (lbl, wr / 100.0, pf, exact, gotv))

    # -- 3. the 100%-win-rate config is ABSENT, not Infinity and not zero ------
    for lbl, wr, _pf in MAIN_WR_PF:
        if wr >= 100 and lbl in got:
            bad.append('EV R: config %s (win_rate 100) drew a point %s - with no losing trade '
                       'there is no R to measure by' % (lbl, got[lbl]))
    joined = ' '.join(ms.get('dots') or [])
    if 'Infinity' in joined or 'NaN' in joined:
        bad.append('EV R / SORTINO: an Infinity or NaN reached the drawing')
    if 'not plotted' not in (ms.get('warn') or ''):
        bad.append('main-scatter: the dropped config is not named under the chart (warn=%r)'
                   % ms.get('warn'))

    # -- 4. SORTINO is finite and ranks smooth above choppy -------------------
    sos = {k: v[1] for k, v in got.items() if isinstance(v[1], float)}
    if len(sos) < 3:
        bad.append('SORTINO: only %d configs plotted a value (%s)' % (len(sos), sos))
    smooth = [v for k, v in sos.items() if k in SMOOTH_CFGS]
    choppy = [v for k, v in sos.items() if k in CHOPPY_CFGS]
    if smooth and choppy and not (min(smooth) > max(choppy)):
        bad.append('SORTINO: the smooth curves (%s) did not outrank the choppy ones (%s)'
                   % (smooth, choppy))
    else:
        print('  sortino    smooth=%s  choppy=%s  (smooth must sit higher)' % (smooth, choppy))

    # -- 4b. MAR is ANNUALISED and R / YR is EV R x trades / years (v73.7x) ------
    #    The fixture run spans OPT_WIN; the RAW points read that window's years. Config A
    #    has net = is_pnl + wf_pnl = 7000 (points), DD 400 (the whole-window metrics
    #    block, the fallback a fixture without per-stretch cal blocks lands on), 500
    #    trades, EV R 0.48. Both figures are checked to the display precision.
    import datetime as _dt
    _d0 = _dt.date.fromisoformat(OPT_WIN[0]); _d1 = _dt.date.fromisoformat(OPT_WIN[1])
    _yrs = (_d1 - _d0).days / 365.25
    mar_got = None; rpy_got = None
    msm = cs.get('main-scatter-mar-rpy') or {}
    for t in msm.get('dots') or []:
        if which_cfg(tip_label(t), names) == 'A':
            mar_got = tip_val(t, 'MAR'); rpy_got = tip_val(t, 'R / YR')
    exp_mar = (7000.0 / _yrs) / 400.0
    exp_rpy = 0.48 * 500 / _yrs
    if not isinstance(mar_got, float) or abs(mar_got - exp_mar) > 0.005 + 1e-9:
        bad.append('MAR: config A rendered %s, annualised hand calculation (7000/%.3f yrs)/400 = %.4f'
                   % (mar_got, _yrs, exp_mar))
    else:
        print('  hand-check MAR  (7000 / %.2f yr) / 400 = %.4f  rendered %.2f   OK' % (_yrs, exp_mar, mar_got))
    if not isinstance(rpy_got, float) or abs(rpy_got - exp_rpy) > 0.05 + 1e-9:
        bad.append('R / YR: config A rendered %s, hand calculation 0.48 * 500 / %.3f = %.4f'
                   % (rpy_got, _yrs, exp_rpy))
    else:
        print('  hand-check R/YR 0.48 * 500 / %.2f yr = %.4f  rendered %.1f   OK' % (_yrs, exp_rpy, rpy_got))

    # -- 4c. ROC % / YR = (net / years) / account x 100 -------------------------
    #    Same config A, same 7,000 over the same window, against the default $100,000
    #    account: (7000 / yrs) / 100000 * 100. At a ~14-year window that is ~0.5 %/yr.
    #    This one is deliberately NOT leverage-blind -- it is the only measure on the
    #    board that re-sizing moves -- so a silent change of basis would be invisible
    #    everywhere else. Hence a gate.
    roc_got = None
    for t in ((cs.get('main-scatter-roc') or {}).get('dots') or []):
        if which_cfg(tip_label(t), names) == 'A':
            roc_got = tip_val(t, 'ROC % / YR')
    exp_roc = (7000.0 / _yrs) / 100000.0 * 100.0
    if not isinstance(roc_got, float) or abs(roc_got - exp_roc) > 0.5 + 1e-9:
        bad.append('ROC %% / YR: config A rendered %s, hand calculation (7000/%.3f yrs)/100000*100 = %.4f'
                   % (roc_got, _yrs, exp_roc))
    else:
        print('  hand-check ROC  (7000 / %.2f yr) / 100000 = %.4f %%/yr  rendered %s   OK'
              % (_yrs, exp_roc, roc_got))

    # -- 5. NUMBERS / RATIOS / BOTH governs both new axes ---------------------
    # an inverted axis wears a ' ↓' and a sparse one a ' °' -- match the measure NAME.
    _bare = lambda a: str(a).replace(' ↓', '').replace(' °', '').strip()
    ra = [_bare(a) for a in ((cs.get('main-ratios-only') or {}).get('axes') or [])]
    nu = [_bare(a) for a in ((cs.get('main-numbers-only') or {}).get('axes') or [])]
    for want in ('EV R', 'SORTINO', 'R / YR', 'DD (R)'):
        if want not in ra:
            bad.append('RATIOS: %s should be a ratio but was filtered out (%s)' % (want, ra))
        if want in nu:
            bad.append('NUMBERS: %s is a ratio and should not appear (%s)' % (want, nu))
    if 'NET $' in ra:
        bad.append('RATIOS: NET $ leaked into the ratios-only axis set (%s)' % ra)
    if 'EV' not in nu:
        bad.append('NUMBERS: plain EV (dollars) should still be a number axis (%s)' % nu)
    if 'EV' in ra:
        bad.append('RATIOS: the EV R rule swallowed the plain dollar EV axis too (%s)' % ra)

    # -- 5b. the same two axes on a modern-engine run (PF / WIN % via is_rng blocks)
    mo = (cs.get('modern-parallel') or {}).get('axes') or []
    for want in ('EV R', 'SORTINO'):
        if want not in mo:
            bad.append('modern-parallel: no %s axis (drew %s)' % (want, mo))
    mos = cs.get('modern-scatter') or {}
    if not any(a.startswith('EV R') for a in (mos.get('axes') or [])):
        bad.append('modern-scatter: EV R was not drawn as the chosen X axis (%s)' % mos.get('axes'))

    # -- 6. a partly-filled axis still draws, with the degree marker ----------
    pp = cs.get('partial-parallel') or {}
    pax = pp.get('axes') or []
    deg = [a for a in pax if u'\u00b0' in a]
    if not any(a.startswith('SORTINO') for a in pax):
        bad.append('partial: SORTINO dropped even though 2 configs carry it (%s)' % pax)
    elif not any(a.startswith('SORTINO') and u'\u00b0' in a for a in pax):
        bad.append('partial: SORTINO filled by 2 of 5 configs but wears no degree sign (%s)' % pax)
    else:
        print('  degree-sign axes=%s' % deg)

    # -- 7. a run carrying none of it must not break the chart ---------------
    for nm in ('bare-parallel', 'bare-scatter', 'bare-table'):
        b = cs.get(nm) or {}
        if b.get('err') or b.get('call') != 'OK':
            bad.append('%s: %s' % (nm, b.get('err') or b.get('call')))
        if b.get('appLen', 0) < 2000:
            bad.append('%s: the chart broke the report (%s chars)' % (nm, b.get('appLen')))
    bp = (cs.get('bare-parallel') or {}).get('axes') or []
    if 'NET $' not in bp:
        bad.append('bare-parallel: the chart lost its NET $ axis too (%s)' % bp)
    if any(a.startswith('EV R') or a.startswith('SORTINO') for a in bp):
        bad.append('bare-parallel: drew an axis no config can fill (%s)' % bp)

    # -- 8. the KPI (phase) chart on the same card carries the pair too -------
    kp = (cs.get('kpi-parallel') or {}).get('axes') or []
    for want in ('EV R', 'SORTINO'):
        if not any(a.startswith(want) for a in kp):
            bad.append('kpi-parallel: no %s axis (drew %s)' % (want, kp))
    ks = cs.get('kpi-scatter') or {}
    kdots = ks.get('dots') or []
    if not kdots:
        bad.append('kpi-scatter: no phase plotted on EV R against SORTINO')
    for t in kdots:
        v = tip_val(t, 'EV R')
        if not isinstance(v, float):
            bad.append('kpi-scatter: a phase plotted a non-numeric EV R (%r)' % v)
    # the LOCKBOX phase reads its PF and win rate verbatim off validate.lockbox, so
    #   its EV R is hand-checkable the same way a config's is: (1-.38)*(1.45-1).
    lbt = [t for t in kdots if '<b>LB</b>' in t]
    if not lbt:
        bad.append('kpi-scatter: the LOCKBOX phase drew no point')
    else:
        exact, gotv = (1 - 0.38) * (1.45 - 1), tip_val(lbt[0], 'EV R')
        if not isinstance(gotv, float) or abs(gotv - exact) > 0.005 + 1e-9:
            bad.append('kpi-scatter: LOCKBOX EV R rendered %s, hand calculation says %.4f'
                       % (gotv, exact))
        else:
            print('  hand-check LB   (1 - 0.38) * (1.45 - 1) = %-8.4f  rendered %.2f   OK'
                  % (exact, gotv))

    # -- 9. SORTINO is a ROW on every 1E family table, filled from the engine block
    #       and equal to what the pooled ALL table prints for the same config.
    #       Before this gate existed the row was on NO family table at all, and the
    #       SHARPE that WAS there disagreed with the pooled views by up to 4x.
    SEED_SO = {'GATE': {'RF 50%': 1.42, 'LOGIT 60%': 2.31},
               'TILT': {'RF (ST)': 1.55, 'XGB (SL)': 1.66},
               'HYBRID': {'RF': 1.44, 'XGB': 1.88}}
    # every seeded lockbox block carries this SHARPE. A table reading it off the saved
    #   ~160-point curve instead lands somewhere else entirely - which is exactly what
    #   run 307's LOGIT 60% did: 2.51 in the table against the engine's 1.84.
    SEED_SH = {'GATE': 0.87, 'TILT': 0.88, 'HYBRID': 0.88}
    fam_cells = {}          # (FAMILY, normalised config label) -> {row label: text}
    for cnm, fam in (('ml-gate-lb', 'GATE'), ('ml-tilt-lb', 'TILT'),
                     ('ml-hyb-lb', 'HYBRID'), ('ml-raw-lb', 'RAW')):
        r = cs.get(cnm) or {}
        cells, hdr = (r.get('cells') or {}), (r.get('hdr') or {})
        if not cells:
            bad.append('%s: the family table rendered no [data-mtxcol] cells' % cnm)
            continue
        n_so = 0
        for key, rows in cells.items():
            lbl = _plain(hdr.get(key, ''))
            fam_cells[(fam, lbl)] = rows
            # SHARPE is checked on EVERY column, whether or not a SORTINO row exists -
            #   before this gate the row did not exist and the check would have skipped
            #   the very defect it is here for.
            wsh, gsh = SEED_SH.get(fam), _num(_row(rows, 'SHARPE'))
            if wsh is not None and gsh is not None and abs(gsh - wsh) > 0.005:
                bad.append('%s: %s SHARPE rendered %s, the engine block says %.2f - the table '
                           'is deriving it from the sampled curve instead of reading the '
                           'measured scalar the pooled views plot' % (cnm, lbl, gsh, wsh))
            got = _row(rows, 'SORTINO')
            if got is None:
                continue
            n_so += 1
            want = SEED_SO.get(fam, {}).get(lbl)
            if want is not None and _num(got) is not None and abs(_num(got) - want) > 0.005:
                bad.append('%s: %s SORTINO rendered %s, the engine block says %.2f'
                           % (cnm, lbl, got, want))
        if not n_so:
            bad.append('%s: no SORTINO row on the family table (rows: %s)'
                       % (cnm, sorted({k for v in cells.values() for k in v})))
        else:
            print('  %-16s SORTINO on %d columns' % (cnm, n_so))

    # -- 9b. a stretch the engine measured as ZERO TRADES must dash, not print zeros
    zg = (cs.get('ml-gate-lb') or {})
    zcells, zhdr = (zg.get('cells') or {}), (zg.get('hdr') or {})
    zfound = False
    for key, rows in zcells.items():
        if _row(rows, 'TRADES') not in ('0', '0.0'):
            continue
        zfound = True
        for rl in ('PF', 'WIN %', 'EV R', 'DD'):
            v = _row(rows, rl)
            if v is not None and _num(v) is not None:
                bad.append('ml-gate-lb: %s took ZERO trades in the lockbox yet %s rendered %r '
                           '- the engine saved a placeholder, not a measurement'
                           % (_plain(zhdr.get(key, key)), rl, v))
        print('  zero-trade col   %-12s PF/WIN %%/EV R/DD = %s'
              % (_plain(zhdr.get(key, key)),
                 [_row(rows, x) for x in ('PF', 'WIN %', 'EV R', 'DD')]))
    if not zfound:
        bad.append('ml-gate-lb: the seeded zero-trade lockbox column never rendered')

    # -- 9c. one metric name, one number: the family table and the pooled ALL table
    at = (cs.get('ml-all-lb') or {}).get('allTable')
    if not at:
        bad.append('ml-all-lb: the pooled ALL table did not render')
    else:
        if 'SORTINO' not in at['head']:
            bad.append('ml-all-lb: the pooled ALL table has no SORTINO column (%s)' % at['head'])
        joined = 0
        for row in at['rows']:
            k = (row.get('FAMILY', '').strip(), _plain(row.get('CONFIG', '')))
            fc = fam_cells.get(k)
            if not fc:
                continue
            for m in ('SHARPE', 'SORTINO'):
                a, b = _num(_row(fc, m)), _num(row.get(m))
                if a is None or b is None:
                    continue
                joined += 1
                if abs(a - b) > 0.02:
                    bad.append('%s %s: the %s tab prints %s and the pooled ALL table prints %s '
                               '- one metric name, two numbers' % (k[0], k[1], m, a, b))
        if joined < 8:
            bad.append('ml-all-lb: only %d family/pooled cells could be joined - the check '
                       'did not actually run' % joined)
        else:
            print('  %-16s %d family cells match the pooled ALL table exactly' % ('ml-all-lb', joined))
        if not (cs.get('ml-all-lb') or {}).get('hasDrop'):
            bad.append('ml-all-lb: a config was dropped from the pool (the zero-trade column) '
                       'and nothing on screen said so')
        else:
            print('  %-16s says how many configs it could not place' % 'ml-all-lb')

    # -- 9d. a pick that skips a stretch pools nothing: say so, do not quietly
    #        revert to a different view
    il = cs.get('ml-all-islb') or {}
    if not il.get('hasTile'):
        bad.append('ml-all-islb: IS+LB can pool nothing, and the ALL tab said nothing about it')
    elif il.get('nMtxCol'):
        bad.append('ml-all-islb: the ALL tab fell back to the stacked family tables '
                   '(%d [data-mtxcol] cells) under a rail that says otherwise' % il['nMtxCol'])
    else:
        print('  %-16s renders the honest empty-pool tile, not another view' % 'ml-all-islb')

    # -- 10. THE 1A CONFIG FUNNEL: no candidate line drawn above the plot top -----
    for fnm, what in (('funnel-gatecand', 'a gate candidate curve'),
                      ('funnel-hybrcy', 'the recycle line of the hybrid that was NOT picked'),
                      ('funnel-doors-gatecand', 'a gate candidate curve in DOORS'),
                      ('funnel-doors-hybrcy', 'the recycle line of the unpicked hybrid in DOORS'),
                      ('funnel-3p-lb', 'a lockbox spike only the dense lockbox tail carries'),
                      ('funnel-doors-3p-lb', 'a lockbox spike only the dense lockbox tail carries, in DOORS')):
        fr = (cs.get(fnm) or {}).get('funnel')
        if not fr:
            bad.append('%s: the 1A funnel did not render (no [data-a2eqx] chart)' % fnm)
            continue
        ac = (fr.get('groups') or {}).get('allcfg')
        if not ac or not ac.get('n'):
            bad.append('%s: ALL CONFIGS drew no lines, so nothing was tested' % fnm)
            continue
        print('  %-16s axis max %s / drawn max %s (%s)  allcfg minY %s, plot top %s'
              % (fnm, _rnd(fr.get('axisMax')), _rnd(fr.get('drawnMax')),
                 fr.get('drawnMaxId'), ac.get('minY'), fr.get('pt')))
        for kg, g in (fr.get('groups') or {}).items():
            if g.get('over'):
                bad.append('%s: %d points of the %r line are drawn above the plot top '
                           '(minY %s, top %s) - %s is off the chart'
                           % (fnm, g['over'], kg, g.get('minY'), fr.get('pt'), what))
        for o in (fr.get('overSeries') or []):
            bad.append('%s: %r peaks at %s against an axis max of %s'
                       % (fnm, o.get('id'), o.get('peak'), _rnd(fr.get('axisMax'))))
        # -- 10b. and the family top lines are SOLID; only the lines whose dash MEANS
        #         something (RAW's in-sample / walk-forward split, the lockbox tail) keep one
        for kg in ('gate', 'tilt', 'hyb2', 'hyb', 'allcfg'):
            g = (fr.get('groups') or {}).get(kg)
            if g and g.get('dash') and g['dash'] != '(solid)':
                bad.append('%s: the %r line is dashed (%s). A full-length dash reads as '
                           '"walk-forward" under this chart own published line procedure'
                           % (fnm, kg, g['dash']))
        for kg, want in (('crown', '2.2 1.6'), ('lb', '0.5 1.6')):
            g = (fr.get('groups') or {}).get(kg)
            if g and want not in (g.get('dash') or ''):
                bad.append('%s: the %r line lost its %s dash - that one carries meaning '
                           '(walk-forward / lockbox) and must stay' % (fnm, kg, want))
        if 'doors' in fnm:
            # -- 10c. DOORS really drew panels (it falls back to ONE CURVE on any error)
            if not fr.get('dz') or (fr.get('dzClips') or 0) < 2:
                bad.append('%s: DOORS drew no panels (%s clip regions, scales %s%s) - it fell back '
                           'to ONE CURVE' % (fnm, fr.get('dzClips'), fr.get('dz'),
                                             (', ' + fr['dzErr']) if fr.get('dzErr') else ''))
            elif not fr.get('dzPieces'):
                bad.append('%s: DOORS drew panels but no line after a door' % fnm)
            elif fr.get('dzStartBad'):
                bad.append('%s: %d line pieces after a door do not start on that panel\'s $0: %s'
                           % (fnm, len(fr['dzStartBad']), fr['dzStartBad'][:3]))
            else:
                print('  %-16s %d panels, %d pieces after a door, all start at $0'
                      % (fnm, len(fr['dz']), fr['dzPieces']))
        print('  %-16s dashes: %s' % (fnm, {k: v.get('dash') for k, v in
                                            (fr.get('groups') or {}).items()
                                            if k in ('crown', 'lb', 'gate', 'tilt', 'hyb', 'hyb2', 'allcfg')}))

    # -- 10d. DOORS against ONE CURVE on the three-panel run. Every DOORS piece must be its ONE
    #         CURVE line less ONE constant (none in-sample), that constant must be the line's value
    #         AT the door, and the raw walk-forward pieces and lockbox tails must end on their TRUE
    #         totals, not on the last point of the sampled curve.
    def _xy(flat):
        return [(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]

    def _at(pts, x):
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            if xa - 1e-6 <= x <= xb + 1e-6:
                if xb - xa < 1e-6:
                    return ya, abs(yb - ya)
                return ya + (yb - ya) * (x - xa) / (xb - xa), abs(yb - ya)
        return None, None

    def _doors_parity(one_nm, doors_nm, ml_ends=None, ml_need=0):
        """10d / 10g. ml_ends = {family: [lockbox totals]}: each ML lockbox piece must also end
           on one of its family's true lockbox totals, and at least ml_need of them must."""
        fo = (cs.get(one_nm) or {}).get('funnel') or {}
        fd = (cs.get(doors_nm) or {}).get('funnel') or {}
        if not fo.get('lines') or not fd.get('lines') or not fd.get('dz') or fd.get('dzEbF') is None:
            bad.append('%s / %s: no funnel lines or no DOORS panel scales to compare' % (one_nm, doors_nm))
            return
        if len(fd['dz']) != 3:
            bad.append('%s: %d panels on a run with a lockbox - expected 3' % (doors_nm, len(fd['dz'])))
            return
        ptv, eqB = fo['pt'], fd['dzEbF'] * fd['H']
        y0, y1 = fo['axisMin'], fo['axisMax']
        u1 = (y1 - y0) / (eqB - ptv)

        def v1(y):
            return y1 - (y - ptv) * u1

        def vk(y, k):
            lo, hi = fd['dz'][k][2], fd['dz'][k][3]
            return hi - (y - ptv) * (hi - lo) / (eqB - ptv)

        ones = [dict(o, xy=_xy(o['pts'])) for o in fo['lines'] if o.get('k') is None]
        n_ok, n_ml, fails = 0, 0, []
        for L in fd['lines']:
            k = L.get('k')
            if k is None:
                continue
            xy = _xy(L['pts'])
            inner = xy[1:-1]
            if len(xy) < 3 or not inner:
                continue
            uk = (fd['dz'][k][3] - fd['dz'][k][2]) / (eqB - ptv)
            tol = 0.06 * (u1 + uk) + 2.0
            best = None
            for O in ones:
                if O['kg'] != L['kg'] or (L.get('sel') is not None and O.get('sel') != L.get('sel')):
                    continue
                offs = []
                for (x, y) in inner:
                    yo, _s = _at(O['xy'], x)
                    if yo is None:
                        break
                    offs.append(v1(yo) - vk(y, k))
                if len(offs) != len(inner):
                    continue
                spread = max(offs) - min(offs)
                if best is None or spread < best[0]:
                    best = (spread, sorted(offs)[len(offs) // 2], O)
            if best is None:
                fails.append('%s panel %d: no ONE CURVE line lies under it' % (L['kg'], k))
                continue
            spread, off, O = best
            if spread > 2 * tol:
                fails.append('%s panel %d: not its ONE CURVE line less a constant (spread $%.0f, allowed $%.0f)'
                             % (L['kg'], k, spread, 2 * tol))
                continue
            xd, yd = xy[0]
            if k == 0:
                if abs(off) > tol:
                    fails.append('%s in-sample: moved by $%.0f - the in-sample panel is never rebased' % (L['kg'], off))
                    continue
            else:
                yo, step = _at(O['xy'], xd)
                want = v1(yo) if yo is not None else None
                got = vk(yd, k) + off
                if want is None or abs(got - want) > tol + (step or 0) * u1:
                    fails.append('%s panel %d: restarts from $%s where ONE CURVE is at $%s on the door'
                                 % (L['kg'], k, round(got), None if want is None else round(want)))
                    continue
            # the true totals: every seeded raw curve stops LB_GAP short of its total, and every
            #   lockbox tail LB_TAIL short of its own
            if k == 1 and L['kg'] in ('crown', 'ismax', 'wf'):
                end, want = vk(xy[-1][1], 1) + off, v1(O['xy'][-1][1]) + LB_GAP
                if abs(end - want) > tol:
                    fails.append('%s walk-forward ends at $%.0f, not on the config total $%.0f - the '
                                 'trades the saved curve leaves off its end are missing' % (L['kg'], end, want))
                    continue
            if k == 2 and L['kg'] == 'lb':
                want = LB_CUM[-1] + LB_TAIL
                if abs(vk(xy[-1][1], 2) - want) > tol:
                    fails.append('lockbox tail ends at $%.0f, not its true total $%.0f'
                                 % (vk(xy[-1][1], 2), want))
                    continue
            # an ML line's lockbox piece starts on the door value (checked above) and must end on
            #   its line's true lockbox total - the last tail point less the value on the door
            if k == 2 and ml_ends and L['kg'] in ml_ends:
                end = vk(xy[-1][1], 2)
                near = min(abs(end - t) for t in ml_ends[L['kg']])
                if near > tol:
                    fails.append('%s lockbox piece ends at $%.0f, on none of its family lockbox totals %s'
                                 % (L['kg'], end, [round(t) for t in ml_ends[L['kg']]]))
                    continue
                n_ml += 1
            n_ok += 1
        for fl in fails[:8]:
            bad.append(doors_nm + ': ' + fl)
        if not fails and n_ok < 20:
            bad.append('%s: only %d DOORS pieces could be checked against ONE CURVE' % (doors_nm, n_ok))
        elif not fails and n_ml < ml_need:
            bad.append('%s: only %d ML lockbox pieces could be checked against their true totals (%d drawn '
                       'ML lines expected)' % (doors_nm, n_ml, ml_need))
        elif not fails:
            print('  %-16s %d DOORS pieces = ONE CURVE less the value at their door; totals kept%s'
                  % (doors_nm, n_ok, ('; %d ML lockbox pieces end on their true lockbox totals' % n_ml)
                     if ml_ends else ''))

    _doors_parity('funnel-3p', 'funnel-doors-3p')

    # -- 10e..10i. THE ML LOCKBOX TAIL (v73.761). Every ML line (gate, tilt, KEEL, hybrid,
    #    recycle, ALL CONFIGS) saves one 300-point sample of the whole run, so the held-out year
    #    had about 20 points and drew as straight strokes. Run 909 carries a dense tail per line,
    #    built by the real engine helpers; 910 carries the same tails with the door count off by
    #    one; 911 carries none.
    lbt = lbt_block()
    if lbt is None:
        bad.append('lockbox-tail fixtures (runs 909-911) could not be built - augur_engine/analytics.py did '
                   'not load (%s), so nothing about the ML lockbox tail was checked' % _LBT['err'])
    else:
        _gv9, rows, spike = lbt
        M = min(int(_analytics().LB_TAIL_CAP), LBT_N - LBT_I0)
        t_offs = [((q + 1) * (LBT_N - LBT_I0)) // M for q in range(M)]
        by_id = {r['id']: r for r in rows}
        ML_KG = ('gate', 'tilt', 'keel', 'hyb', 'hyb2', 'allcfg')
        pool = {'gate': ('gate',), 'tilt': ('tilt',), 'keel': ('keel',), 'hyb': ('hyb',), 'hyb2': ('hyb2',),
                'allcfg': ('cand', 'tilt', 'hyb', 'hyb2')}   # ALL CONFIGS = every non-top candidate line
        spike_row = by_id['gc-logit-60']
        spike_v = spike_row['cf'][LBT_SPIKE_AT] * MULT

        def _true_tail(ex):
            """the line's real running totals at the tail's trades, scaled as the funnel draws it"""
            return [ex['cf'][LBT_I0 - 1 + o] * MULT * ex['f'] for o in t_offs]

        def _geo(fr):
            if not fr or fr.get('lbX0') is None or fr.get('eqB') is None or fr.get('axisMax') is None:
                return None
            ptv, eb, ya, yb = fr['pt'], fr['eqB'], fr['axisMin'], fr['axisMax']
            u = (yb - ya) / (eb - ptv)
            return {'x0': fr['lbX0'], 'x1': fr['lbX1'], 'u': u, 'v': (lambda y: yb - (y - ptv) * u)}

        def _lbv(G, pts):
            """the vertices past the lockbox door, left to right (the door vertex itself excluded)"""
            half = 0.5 * (G['x1'] - G['x0']) / M
            return [(x, y) for (x, y) in _xy(pts) if x > G['x0'] + half]

        def _fit(G, lv, ex):
            """(worst x miss, worst $ miss) of the lockbox vertices against one line's tail, whatever
               their count - 10e owns the count. Each vertex is read as the tail point nearest its x,
               so a sparse or mis-bent line misses the tail's x grid, its running totals, or both.
               None when the line does not end on the right edge."""
            want = _true_tail(ex)
            if not lv or abs(lv[-1][0] - G['x1']) > 0.16:
                return None
            wx = wv = 0.0
            step = (G['x1'] - G['x0']) / M
            for (x, y) in lv:
                q = min(M - 1, max(0, int(round((x - G['x0']) / step)) - 1))
                wx = max(wx, abs(x - (G['x0'] + step * (q + 1))))
                wv = max(wv, abs(G['v'](y) - want[q]))
            return wx, wv

        def _mlines(fr):
            out = {}
            for L in (fr or {}).get('lines') or []:
                if L.get('k') is None and L['kg'] in ML_KG:
                    out.setdefault(L['kg'], []).append(L)
            return out

        # the fixture itself: the stride really does step over the spike, and the tails are the cap
        _sv = spike_row['eq']['cum']
        if max(_sv) * MULT > spike_v - 0.5 * spike:
            bad.append('lockbox-tail fixture: the saved 300-point curve of %s already holds the spike '
                       '(max %s vs spike %s) - 10e/10f would not tell a tail from a sample'
                       % (spike_row['id'], max(_sv), round(spike_v)))
        for ex in rows:
            q = ex['eq'].get(ex['lk'])
            if not q or len(q.get('cum') or []) != M or q.get('i0') != LBT_I0:
                bad.append('lockbox-tail fixture: %s has no %d-point tail at door %d (%s)'
                           % (ex['id'], M, LBT_I0, None if not q else (len(q.get('cum') or []), q.get('i0'))))

        # -- 10e / 10f on 909 ONE CURVE: every ML line puts exactly the tail's points past the door,
        #    at the tail's x positions and on the true running totals, ending on the true total
        lo = (cs.get('funnel-3p-lb') or {}).get('funnel') or {}
        G = _geo(lo)
        if G is None:
            bad.append('funnel-3p-lb: no lockbox stripe or axis to read the ML lines against (lbErr %s)'
                       % lo.get('lbErr'))
        else:
            tolv = 0.06 * G['u'] + 1.0
            fam = _mlines(lo)
            n_e = n_f = n_l = 0
            used = {}
            for kg in ML_KG:
                Ls = fam.get(kg) or []
                if not Ls:
                    bad.append('funnel-3p-lb: no %r line drawn at all - nothing to check' % kg)
                    continue
                if kg == 'allcfg' and len(Ls) != 6:
                    bad.append('funnel-3p-lb: ALL CONFIGS drew %d lines, expected 6 (3 gate candidates + the '
                               'non-top tilt, hybrid and hybrid recycle)' % len(Ls))
                for L in Ls:
                    n_l += 1
                    lv = _lbv(G, L['pts'])
                    if len(lv) < M:
                        bad.append('funnel-3p-lb (10e): the %r line has %d points past the lockbox door, '
                                   'expected at least %d - it is still drawn from the sparse 300-point sample'
                                   % (kg, len(lv), M))
                    else:
                        n_e += 1
                    best = None
                    for ex in rows:
                        if ex['fam'] not in pool[kg] or (kg == 'allcfg' and used.get(ex['id'])):
                            continue
                        ft = _fit(G, lv, ex)
                        if ft is not None and (best is None or ft[1] < best[0][1]):
                            best = (ft, ex)
                    if best is None or best[0][0] > 0.16 or best[0][1] > tolv:
                        bad.append('funnel-3p-lb (10f): the %r line lockbox points match no %s tail - worst '
                                   'x miss %s, worst $ miss %s (allowed 0.16 / $%.0f)'
                                   % (kg, '/'.join(pool[kg]), None if best is None else round(best[0][0], 3),
                                      None if best is None else round(best[0][1]), tolv))
                        continue
                    n_f += 1
                    if kg == 'allcfg':
                        used[best[1]['id']] = True
                    if best[1]['spiked']:
                        top = max(G['v'](y) for (_x, y) in lv)
                        if abs(top - spike_v) > tolv:
                            bad.append('funnel-3p-lb (10f): the spiked line peaks at $%.0f, not the $%.0f its '
                                       'lockbox tail carries' % (top, spike_v))
            if not used.get(spike_row['id']):
                bad.append('funnel-3p-lb (10f): no ALL CONFIGS line carried the lockbox spike of %s'
                           % spike_row['id'])
            if n_l and n_e == n_l and n_f == n_l:
                print('  %-16s %d ML lines, each with its %d-point lockbox tail at the true running totals '
                      '(spike $%.0f drawn)' % ('funnel-3p-lb', n_f, M, spike_v))

        # -- 10e control on 911: the same lines with no tail stay sparse, and never see the spike
        ln = (cs.get('funnel-3p-lbnone') or {}).get('funnel') or {}
        Gn = _geo(ln)
        if Gn is None:
            bad.append('funnel-3p-lbnone: no lockbox stripe or axis to read the ML lines against')
        else:
            famn = _mlines(ln)
            n_c, top_n = 0, None
            for kg in ML_KG:
                for L in famn.get(kg) or []:
                    lv = _lbv(Gn, L['pts'])
                    n_c += 1
                    if len(lv) >= M / 2.0:
                        bad.append('funnel-3p-lbnone (10e): with NO tail saved the %r line still has %d points '
                                   'past the door - the control is not sparse, so 10e proves nothing'
                                   % (kg, len(lv)))
                    for (_x, y) in lv:
                        top_n = Gn['v'](y) if top_n is None else max(top_n, Gn['v'](y))
            if n_c < 11:
                bad.append('funnel-3p-lbnone: only %d ML lines drawn, expected 11' % n_c)
            elif top_n is not None and top_n > spike_v - 0.5 * spike:
                bad.append('funnel-3p-lbnone: a line with no tail reaches $%.0f - the 300-point sample was '
                           'meant to step over the $%.0f spike' % (top_n, spike_v))
            else:
                print('  %-16s %d ML lines with no tail keep under %d lockbox points; none reaches the spike'
                      % ('funnel-3p-lbnone', n_c, M // 2))

        # -- 10g: DOORS still equals ONE CURVE less the door value, with the stitched lines, and every
        #    ML lockbox piece ends on its line's true lockbox total
        ends = {}
        for kg in ML_KG:
            ends[kg] = [(ex['cf'][-1] - ex['cf'][LBT_I0 - 1]) * MULT * ex['f'] for ex in rows
                        if ex['fam'] in pool[kg]]
        _doors_parity('funnel-3p-lb', 'funnel-doors-3p-lb', ml_ends=ends, ml_need=11)

        # -- 10h: a tail whose door count is off by one is refused, so 910 draws exactly what 911
        #    (no tail) draws - in both layouts and in the explorer payload - and 909 does not
        def _ser_key(fr):
            return [(s.get('id'), s.get('hasSp'), s.get('eq'), s.get('ts'), s.get('li'), s.get('wfi'))
                    for s in (fr or {}).get('ser') or []]
        for a_nm, b_nm in (('funnel-3p-lbbad', 'funnel-3p-lbnone'),
                           ('funnel-doors-3p-lbbad', 'funnel-doors-3p-lbnone')):
            fa = (cs.get(a_nm) or {}).get('funnel') or {}
            fb = (cs.get(b_nm) or {}).get('funnel') or {}
            pa, pb = fa.get('polys'), fb.get('polys')
            if not pa or not pb:
                bad.append('%s / %s: no polylines harvested to compare' % (a_nm, b_nm))
            elif pa != pb:
                nd_ = sum(1 for x, y in zip(pa, pb) if x != y) + abs(len(pa) - len(pb))
                bad.append('%s (10h): %d of %d polylines differ from %s - a tail whose door count is off by '
                           'one was drawn instead of refused' % (a_nm, nd_, len(pa), b_nm))
            elif _ser_key(fa) != _ser_key(fb) or not _ser_key(fa):
                bad.append('%s (10h): the explorer payload ML series differ from %s (or are empty)' % (a_nm, b_nm))
            else:
                print('  %-16s %d polylines and %d ML payload series identical to %s'
                      % (a_nm, len(pa), len(_ser_key(fa)), b_nm))
        if (lo.get('polys') or 1) == (ln.get('polys') or 2):
            bad.append('funnel-3p-lb (10h): 909 draws the same polylines as 911 - the tails changed nothing, '
                       'so the refusal check proves nothing')

        # -- 10i: the explorer payload. A stitched ML series carries sp, one timestamp per point on
        #    the piecewise calendar (optimize window, then the lockbox from its own start), its door
        #    index on the lockbox start, and exactly the saved points + door value + tail. The same
        #    series with no tail keeps the saved curve evenly spread over the whole span, no sp.
        def _ms(s):
            return calendar.timegm(time.strptime(s, '%Y-%m-%d')) * 1000
        o0, o1, l0, l1 = _ms(OPT_WIN[0]), _ms(OPT_WIN[1]), _ms(GATE_LB0), _ms(GATE_SPAN[1])
        n_i = 0
        for cnm, stitched in (('funnel-3p-lb', True), ('funnel-3p-lbnone', False)):
            ser = ((cs.get(cnm) or {}).get('funnel') or {}).get('ser') or []
            seen = set()
            for s in ser:
                ex = by_id.get(s.get('id'))
                if ex is None:
                    continue
                seen.add(s['id'])
                sid, eqv, ts = s['id'], s.get('eq') or [], s.get('ts') or []
                cum, q = ex['eq'][ex['ck']], ex['eq'].get(ex['lk'])
                errs = []
                if s.get('li') is not None or s.get('wfi') is not None:
                    errs.append('li/wfi %s/%s set - the line would draw dashed' % (s.get('li'), s.get('wfi')))
                if stitched:
                    want = [v * MULT * ex['f'] for v in cum[:q['j0']] + [q['base']] + q['cum']]
                    if not s.get('hasSp') or s.get('sp') is None:
                        errs.append('no sp')
                    else:
                        di = int(round(s['sp'] * (len(eqv) - 1)))
                        if di != q['j0']:
                            errs.append('sp puts the door at point %d, the tail says %d' % (di, q['j0']))
                        elif len(ts) == len(eqv) and ts and None not in ts:
                            if abs(ts[di] - l0) > 1 or abs(ts[di - 1] - o1) > 1:
                                errs.append('door stamps %s / %s, want optimize end %s then lockbox start %s'
                                            % (ts[di - 1], ts[di], o1, l0))
                else:
                    want = [v * MULT * ex['f'] for v in cum]
                    if s.get('hasSp'):
                        errs.append('carries sp with no tail saved')
                    elif len(ts) == len(eqv) and len(ts) > 1 and None not in ts:
                        lin = max(abs(t - (o0 + (l1 - o0) * i / (len(ts) - 1))) for i, t in enumerate(ts))
                        if lin > 1:
                            errs.append('timestamps not an even spread over the span (off by %.0f ms)' % lin)
                if len(eqv) != len(want) or any(abs(a - b) > 1e-6 * max(1.0, abs(b)) for a, b in zip(eqv, want)):
                    errs.append('values are not %s (%d points vs %d)'
                                % ('saved points + door value + tail' if stitched else 'the saved curve',
                                   len(eqv), len(want)))
                if len(ts) != len(eqv) or not ts or None in ts:
                    errs.append('%d timestamps for %d points' % (len(ts), len(eqv)))
                elif any(b < a for a, b in zip(ts, ts[1:])):
                    errs.append('timestamps run backwards')
                elif abs(ts[0] - o0) > 1 or abs(ts[-1] - l1) > 1:
                    errs.append('span %s..%s, want %s..%s' % (ts[0], ts[-1], o0, l1))
                if errs:
                    bad.append('%s (10i): payload series %s: %s' % (cnm, sid, '; '.join(errs)))
                else:
                    n_i += 1
            if seen != set(by_id):
                bad.append('%s (10i): the explorer payload is missing ML series %s'
                           % (cnm, sorted(set(by_id) - seen)))
        if n_i == 2 * len(by_id):
            print('  %-16s %d ML payload series stitched on the piecewise calendar, %d unstitched controls intact'
                  % ('funnel-3p-lb', len(by_id), len(by_id)))

        # -- 10j..10m: A TAIL THE FUNNEL MUST REFUSE DRAWS EXACTLY WHAT NO TAIL DRAWS. One pair per
        #    guard family: the gauntlet (a different broken tail on every ML line, each caught by
        #    exactly one guard), good tails on a run with no RAW lockbox panel, and tails on a run
        #    whose saved curves already draw the lockbox more densely than any tail would.
        def _same(a_nm, b_nm, what):
            fa = (cs.get(a_nm) or {}).get('funnel') or {}
            fb = (cs.get(b_nm) or {}).get('funnel') or {}
            pa, pb = fa.get('polys'), fb.get('polys')
            if not pa or not pb:
                bad.append('%s / %s: no polylines harvested to compare' % (a_nm, b_nm))
            elif pa != pb:
                nd_ = sum(1 for x, y in zip(pa, pb) if x != y) + abs(len(pa) - len(pb))
                bad.append('%s: %d of %d polylines differ from %s - %s was drawn instead of refused'
                           % (a_nm, nd_, len(pa), b_nm, what))
            elif _ser_key(fa) != _ser_key(fb) or len(_ser_key(fa)) < 9:
                bad.append('%s: the explorer payload ML series differ from %s (or are missing) - %s'
                           % (a_nm, b_nm, what))
            else:
                print('  %-16s %d polylines and %d ML payload series identical to %s'
                      % (a_nm, len(pa), len(_ser_key(fa)), b_nm))
        _same('funnel-lb-gauntlet', 'funnel-lb-gauntlet0',
              'a broken tail (%s)' % ', '.join(h for _s, h, _w in GAUNTLET))
        _same('funnel-lb-nopanel', 'funnel-lb-nopanel0', 'a tail on a run with no lockbox panel')
        _same('funnel-lb-short', 'funnel-lb-short0', 'a tail that adds no lockbox points')
        # the fixtures really are what those checks claim
        short = _lbt_build(i0=900, spikes=(), only_if_denser=False)
        A_ = _analytics()
        for ex in short[1]:
            q = ex['eq'].get(ex['lk'])
            ndp = 1 if ex['fam'] == 'gate' else None
            if not q or A_.lockbox_tail(A_.np.array(ex['cf']), 900, len(ex['eq'][ex['ck']]),
                                        int(A_.LB_TAIL_CAP), ndp) is not None:
                bad.append('lockbox-tail fixture 918: %s should carry a tail the engine itself would not write'
                           % ex['id'])

        # -- 10l: a lockbox of 4 trades puts the door on the LAST saved point (j0 = pts-1): the most
        #    stretched line of all must get its tail - in the payload, and on the drawn lines
        tiny = _lbt_build(i0=LBT_N - 4, spikes=())
        t_by = {r['id']: r for r in tiny[1]}
        ft = (cs.get('funnel-lb-tiny') or {}).get('funnel') or {}
        ft0 = (cs.get('funnel-lb-tiny0') or {}).get('funnel') or {}
        n_t, errs_t = 0, []
        for s in ft.get('ser') or []:
            ex = t_by.get(s.get('id'))
            if ex is None:
                continue
            cum, q = ex['eq'][ex['ck']], ex['eq'].get(ex['lk'])
            if not q or q.get('j0') != len(cum) - 1:
                errs_t.append('%s: fixture tail j0 %s, want %d' % (s['id'], None if not q else q.get('j0'), len(cum) - 1))
                continue
            want = [v * MULT * ex['f'] for v in cum[:q['j0']] + [q['base']] + q['cum']]
            eqv = s.get('eq') or []
            if not s.get('hasSp') or s.get('sp') is None:
                errs_t.append('%s: not stitched (no sp)' % s['id'])
            elif int(round(s['sp'] * (len(eqv) - 1))) != q['j0']:
                errs_t.append('%s: door at point %d, want %d' % (s['id'], int(round(s['sp'] * (len(eqv) - 1))), q['j0']))
            elif len(eqv) != len(want) or any(abs(a - b) > 1e-6 * max(1.0, abs(b)) for a, b in zip(eqv, want)):
                errs_t.append('%s: values are not saved points + door value + tail' % s['id'])
            else:
                n_t += 1
        if errs_t or n_t < len(t_by):
            bad.append('funnel-lb-tiny (10l): %d of %d ML series drew their tail with the door on the last saved '
                       'point%s' % (n_t, len(t_by), (': ' + '; '.join(errs_t[:4])) if errs_t else ''))
        elif not ft.get('polys') or ft.get('polys') == ft0.get('polys'):
            bad.append('funnel-lb-tiny (10l): the lines draw the same as with no tail - the tails were refused')
        else:
            print('  %-16s %d ML series stitched with the door on the last saved point (j0 = 299)'
                  % ('funnel-lb-tiny', n_t))

        # -- 10n: THE DEFAULT VIEW'S Y-SCALE. With ALL CONFIGS off only the family y-scale folds see
        #    the gate / tilt / KEEL / hybrid / recycle lines. Each run hands one family top the chart's
        #    peak (and one its trough) inside its lockbox tail; every family line must sit inside the
        #    plot, and the named line must be the one touching the top (or the floor) - otherwise
        #    another line sized the axis and a broken fold would pass unseen.
        FAM = ('gate', 'tilt', 'keel', 'hyb', 'hyb2')
        for cnm, peak, trough, absent in (('funnel-ft-gate-keel', 'gate', 'keel', None),
                                          ('funnel-ft-tilt-hyb', 'tilt', 'hyb', 'hyb2'),
                                          ('funnel-ft-recycle', 'hyb2', None, None)):
            fr = (cs.get(cnm) or {}).get('funnel') or {}
            Gf = _geo(fr)
            if Gf is None:
                bad.append('%s: no lockbox stripe or axis to read the family lines against' % cnm)
                continue
            ptv, flo = fr['pt'], fr['eqB']
            ys = {}
            for L in fr.get('lines') or []:
                if L.get('k') is None and L['kg'] in FAM:
                    ys.setdefault(L['kg'], []).extend(y for (_x, y) in _xy(L['pts']))
            errs = []
            for kg in FAM:
                v = ys.get(kg) or []
                if not v:
                    continue
                if min(v) < ptv - 0.05:
                    errs.append('the %r line is drawn above the plot top (y %.1f, top %.1f)' % (kg, min(v), ptv))
                if max(v) > flo + 0.05:
                    errs.append('the %r line is drawn below the plot floor (y %.1f, floor %.1f)' % (kg, max(v), flo))
            for kg, edge, nm_ in ((peak, ptv, 'top'), (trough, flo, 'floor')):
                if kg is None:
                    continue
                v = ys.get(kg) or []
                if not v:
                    errs.append('no %r line drawn - nothing to check' % kg)
                elif abs((min(v) if nm_ == 'top' else max(v)) - edge) > 0.2:
                    errs.append('the %r line does not touch the plot %s (%.1f vs %.1f) - another line sized the '
                                'axis, so this run does not test its fold' % (kg, nm_, min(v) if nm_ == 'top' else max(v), edge))
            if absent and ys.get(absent):
                errs.append('a %r line was drawn on a run with no recycle factor' % absent)
            if errs:
                for e_ in errs:
                    bad.append('%s (10n): %s' % (cnm, e_))
            else:
                print('  %-16s ALL CONFIGS off: %s holds the peak%s, every family line inside the plot'
                      % (cnm, peak, (', %s the trough' % trough) if trough else ''))

    # -- 11. TWO-STRETCH SAMPLE PICKS READ THE ENGINE'S COMBINED BLOCK (v73.763,
    #    run #384: 32 of 32 cells read low). Drawdown is path-dependent: it cannot be
    #    reconstructed from the per-stretch drawdowns either by summing them or by
    #    taking the larger, and the ~300-point saved curve only sees a drop that
    #    happens to straddle two of the points it kept. IS+WF and WF+LB must read
    #    pre / wf_lb - the engine own combined-span blocks, measured trade by trade -
    #    the way an all-three pick already reads full. The szcand fixture is built so
    #    a curve read (-$3), the larger part (-$9.1k) and the sum of the parts (-$17k /
    #    -$12k) each land on a different $k-rounded figure from the engine block
    #    (-$13k / -$10k), so whichever wrong method a broken build takes is visible.
    for cnm, prefix, want_dd, want_tr in (('ml-tilt-iswf', 'tilt:', '-$13k', '1,020'),
                                          ('ml-tilt-wflb', 'tilt:', '-$10k', '555'),
                                          ('ml-hyb-iswf', 'hyb:', '-$13k', '1,020'),
                                          ('ml-hyb-wflb', 'hyb:', '-$10k', '555')):
        r = cs.get(cnm) or {}
        cells = r.get('cells') or {}
        cols = [k for k in cells if k.startswith(prefix)]
        if len(cols) < 2:
            bad.append('%s: no columns rendered (%s)' % (cnm, sorted(cells.keys())))
            continue
        n_ok = 0
        for k in cols:
            rows = cells[k]
            dd = _row(rows, 'DD')
            if dd is None:
                bad.append('%s: column %s printed no DD row' % (cnm, k))
                continue
            dd = dd.strip()
            dd_bare = dd.replace(u'\u00b0', '')
            hint = ''
            if dd_bare == '-$3':
                hint = ' (matches the saved curve read)'
            elif dd_bare == '-$9.1k':
                hint = ' (matches the larger of the two parts)'
            elif dd_bare in ('-$17k', '-$12k'):
                hint = ' (matches the sum of the two parts)'
            if u'\u00b0' in dd or dd != want_dd:
                bad.append('%s: column %s DD rendered %r, expected %r%s'
                           % (cnm, k, dd, want_dd, hint))
                continue
            tr = (_row(rows, 'TRADES') or '').strip()
            if tr != want_tr:
                bad.append('%s: column %s TRADES rendered %r, expected %r'
                           % (cnm, k, tr, want_tr))
                continue
            n_ok += 1
        if n_ok:
            print('  %-16s %d of %d columns read DD %s, TRADES %s off the engine block'
                  % (cnm, n_ok, len(cols), want_dd, want_tr))

    # the old-run twin (923: 908's pool with pre / wf_lb stripped off every tilt /
    #   hybrid row) must keep reading the saved curve on the same pick, marked with
    #   the degree sign - proof the fallback still works for a run saved before the
    #   engine wrote those blocks, rather than the pick going blank or crashing.
    ro = cs.get('ml-tilt-iswf-old') or {}
    rcols = [k for k in (ro.get('cells') or {}) if k.startswith('tilt:')]
    if len(rcols) < 2:
        bad.append('ml-tilt-iswf-old: no columns rendered (%s)' % sorted((ro.get('cells') or {}).keys()))
    else:
        n_ok = 0
        for k in rcols:
            dd = (_row(ro['cells'][k], 'DD') or '').strip()
            if not dd or dd in ('-', u'\u2014', u'\u2013'):
                bad.append('ml-tilt-iswf-old: column %s printed no DD (%r)' % (k, dd))
            elif u'\u00b0' not in dd:
                bad.append('ml-tilt-iswf-old: column %s DD rendered %r with no degree sign - '
                           'an old run must keep the curve-read marker' % (k, dd))
            else:
                n_ok += 1
        if n_ok == len(rcols):
            print('  %-16s %d of %d columns keep the marked curve read on an old run'
                  % ('ml-tilt-iswf-old', n_ok, len(rcols)))

    if bad:
        print('1E AXES PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('1E AXES PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
