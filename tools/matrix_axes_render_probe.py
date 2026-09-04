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

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.
Stdlib only, plus a subprocess call to local Chrome.
"""
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

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
    """One TILT (scheme set) or HYBRID (scheme None) column."""
    c = {'model': model, 'n_trades': ntr, 'max_size': 1,
         'equity': {'cum': cum},
         'is_rng': blk(66000, 560, 1.56, 46.0, 8100, 1.22, 1.92),
         'wf_rng': blk(56000, 460, 1.46, 44.0, 9100, 1.03, 1.62),
         'lockbox': (ZERO_BLK if zerolb else blk(9500, 95, 1.36, 43.0, 2600, 0.88, so_lb)),
         'full': blk(131500, full_n, 1.49, 44.7, 11100, 1.10, 1.73),
         'pre': blk(122000, 1020, 1.51, 45.0, 10200, 1.12, 1.78)}
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
    return [run_doc(901, main), run_doc(902, partial), run_doc(903, bare),
            run_doc(904, modern), kpi, r906, r907]


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
    # -- the 1A CONFIG FUNNEL, ALL CONFIGS on.
    ('funnel-gatecand', 906, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1}),
    ('funnel-hybrcy', 907, {'repCols': '3', 'eqTab': 'funnel', 'a2cfgAll': 1}),
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
          var f={pt:pt,axisMax:(xh&&xh.y1!=null)?+xh.y1:null,groups:{}};
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
    m = re.search(re.escape(axis) + r' <b>' + _TIPNUM + r'</b>', tip or '')
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
                      ('funnel-hybrcy', 'the recycle line of the hybrid that was NOT picked')):
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
        print('  %-16s dashes: %s' % (fnm, {k: v.get('dash') for k, v in
                                            (fr.get('groups') or {}).items()
                                            if k in ('crown', 'lb', 'gate', 'tilt', 'hyb', 'hyb2', 'allcfg')}))

    if bad:
        print('1E AXES PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('1E AXES PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
