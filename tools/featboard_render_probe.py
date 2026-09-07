#!/usr/bin/env python3
"""
tools/featboard_render_probe.py -- render gate for COMPARE > FEATURE BOARD.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. It never enters COMPARE, let alone the
new FEATURE BOARD mode (v73.536), which is a large self-contained branch of its own --
the same kind of branch the STUDIES and RUNBOARD probes exist to catch (see
tools/studies_render_probe.py). FEATURE BOARD reads two build-script outputs
(docs/feature_board.json, docs/exit_autopsy.json) that may not exist yet on a fresh
checkout, or may be mid-write by tools/feature_board.py / tools/exit_autopsy.py, so this
probe never depends on the real files -- it injects window.__FEATBOARD_FIXTURE and
window.__EXIT_FIXTURE instead, which the render branch honours in place of the fetch
(see index.html, "FEATURE BOARD" search block). A page served over file:// could not
fetch anyway; this probe serves the repo over loopback the same way the other render
probes do, and the fixtures keep it independent of whatever is on disk in docs/.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe, and inside the iframe's
own global scope (top-level `let`/`const` bindings in index.html's classic script are
NOT window properties, so everything happens via w.eval(), never w.prop=):

  1. sets window.__FEATBOARD_FIXTURE / window.__EXIT_FIXTURE to realistic fixtures built
     below (6 legs across 4 families, 12 features across 5 groups, 3 verdicts: 2
     PROMOTED + 1 WATCH, cells for every feature x leg pair, at least one lb_agrees).
  2. sets augurPrefs to {cmpMode:'featboard', fbRowMode:'all'} so the matrix shows every
     row deterministically rather than depending on which fixture cells happen to
     survive.
  3. sets activeTab='augur'; augurSub='cmp'; and calls renderApp().

WHAT IT ASSERTS
---------------
  * renderApp returns without throwing
  * the header block renders ([data-fbheader])
  * exactly 3 verdict cards ([data-fbverdict]) -- 2 PROMOTED + 1 WATCH from the fixture
  * the matrix has 12 feature rows (tr[data-fbrow]) x 6 leg columns (one <td data-fbcell>
    per row per leg, so 72 total)
  * at least one lockbox-agreement diamond ([data-fbdiamond])
  * the EXITS section has 6 cards ([data-fbexitcard]), each with its own hold-curve chart
    (>=1 [data-fbholdbar] inside it)
  * no horizontal overflow (document.documentElement.scrollWidth <= clientWidth)
  * no console.error and no uncaught exception / unhandled rejection during the render

LIFT (v73.539): the default fixture now carries lift_r/lift_lo/lift_hi/lift_p/lift_q/
lift_beats_probe/lift_survives/lb_lift_r/lb_lift_agrees on every cell (~1/3 lift_survives,
a subset with lb_lift_agrees) and a verdict.basis on all three verdicts (one 'rank', one
'lift', one 'both'). Against that fixture the probe additionally asserts one [data-fblift]
per [data-fbcell], at least one [data-fbliftdiamond] triangle, at least one [data-fbbasis]
pill, and the legend carrying the "lift reading that repeats in the lockbox" line plus a
bare "▲" glyph somewhere on the page. `--nolift` builds the SAME fixture with every
lift-related key stripped (from cells, verdicts, and rule) to prove the old-format path:
zero [data-fblift]/[data-fbliftdiamond]/[data-fbbasis], no legend line, no "▲" glyph
-- byte-for-byte the pre-lift render. `--real` reads whatever is actually in docs/ and
applies the SAME has-lift branch automatically (has_lift is detected from the loaded JSON,
not from the CLI flag), so it self-adapts whether the backend has shipped lift fields yet
or not.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks a push
on tooling trouble -- no chrome found, timeout, etc).

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

try:
    # Windows consoles default to cp1252, which cannot print the U+25B2 (▲) glyph in a
    # FAIL line below; UTF-8 stdout matches every other render probe in tools/.
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
PROBE_FILENAME = '_featboard_probe.html'

FAMILIES = ['ORB', 'NOISE', 'ENGU-Q', 'TTM']

LEGS = [
    {'key': 'ORB_314', 'family': 'ORB', 'label': 'ORB #314 (crown)', 'file': 'ORB_6_0.py',
     'run': 314, 'instrument': 'NQ', 'timeframe': '5m', 'session': 'RTH', 'window': ['2010-06-07', '2026-08-13'],
     'lockbox_from': '2025-08-13', 'n_pre': 4670, 'n_lb': 278, 'net_pre': 649186.0, 'net_lb': 194202.0,
     'parity': {'source': 'doc', 'expected_net': 843388.0, 'got_net': 843388.0, 'ok': True}},
    {'key': 'ORB_234', 'family': 'ORB', 'label': 'ORB #234 C2 ride+BE', 'file': 'ORB_3_6.py',
     'run': 234, 'instrument': 'NQ', 'timeframe': '5m', 'session': 'RTH', 'window': ['2010-06-07', '2026-08-13'],
     'lockbox_from': '2025-08-13', 'n_pre': 5087, 'n_lb': 372, 'net_pre': 646128.0, 'net_lb': 164454.0,
     'parity': {'source': 'defaults', 'expected_net': None, 'got_net': 810582.0, 'ok': True}},
    {'key': 'NOISE_304', 'family': 'NOISE', 'label': 'NOISE #304 crown', 'file': 'NOISE_SBS_V90.py',
     'run': 304, 'instrument': 'NQ', 'timeframe': '1m', 'session': '24h', 'window': ['2010-01-04', '2026-08-13'],
     'lockbox_from': '2025-08-13', 'n_pre': 3612, 'n_lb': 409, 'net_pre': 512340.0, 'net_lb': 82123.0,
     'parity': {'source': 'doc', 'expected_net': 594463.0, 'got_net': 594463.0, 'ok': True}},
    {'key': 'NOISE_243', 'family': 'NOISE', 'label': 'NOISE #243 (control)', 'file': 'NOISE_SBS_V90.py',
     'run': 243, 'instrument': 'NQ', 'timeframe': '1m', 'session': '24h', 'window': ['2010-01-04', '2026-08-13'],
     'lockbox_from': '2025-08-13', 'n_pre': 3204, 'n_lb': 375, 'net_pre': 476102.0, 'net_lb': 60615.0,
     'parity': {'source': 'doc', 'expected_net': 536717.0, 'got_net': 536717.0, 'ok': True}},
    {'key': 'ENGUQ_226', 'family': 'ENGU-Q', 'label': 'ENGU-Q ETH #226', 'file': 'ENGUQ_1M_ETH.py',
     'run': 226, 'instrument': 'NQ', 'timeframe': '1m', 'session': 'ETH', 'window': ['2010-01-04', '2026-06-30'],
     'lockbox_from': '2025-06-30', 'n_pre': 2658, 'n_lb': 194, 'net_pre': 345196.0, 'net_lb': 75512.0,
     'parity': {'source': 'doc', 'expected_net': 420708.0, 'got_net': 420708.0, 'ok': True}},
    {'key': 'TTM_299', 'family': 'TTM', 'label': 'TTM squeeze #299', 'file': 'TTM_SQUEEZE.py',
     'run': 299, 'instrument': 'NQ', 'timeframe': '60m', 'session': 'RTH', 'window': ['2012-01-03', '2026-06-30'],
     'lockbox_from': '2025-06-30', 'n_pre': 890, 'n_lb': 61, 'net_pre': 41200.0, 'net_lb': 2900.0,
     'parity': {'source': 'defaults', 'expected_net': None, 'got_net': 44100.0, 'ok': True}},
]
LEG_KEYS = [l['key'] for l in LEGS]

FEATURES = [
    {'name': 'vix_pctile', 'label': 'VIX percentile (prior day)', 'group': 'bar', 'desc': 'where the prior day\u2019s VIX close sits in its own trailing history'},
    {'name': 'atr_ratio', 'label': 'ATR ratio (bar / 20-bar)', 'group': 'bar', 'desc': 'this bar\u2019s range against its own 20-bar average range'},
    {'name': 'volume_zscore', 'label': 'volume z-score', 'group': 'bar', 'desc': 'this bar\u2019s volume against its own trailing mean and stdev'},
    {'name': 'gap_pct', 'label': 'overnight gap %', 'group': 'daily', 'desc': 'percent gap between yesterday\u2019s close and today\u2019s open'},
    {'name': 'prior_day_range', 'label': 'prior day range (ATR units)', 'group': 'daily', 'desc': 'yesterday\u2019s high-low range in units of its own 20-day ATR'},
    {'name': 'overnight_gap_dir', 'label': 'overnight gap direction', 'group': 'daily', 'desc': 'sign of the overnight gap, up or down'},
    {'name': 'dxy_chg', 'label': 'dollar index change (prior day)', 'group': 'macro', 'desc': 'DXY percent change over the prior session'},
    {'name': 'vix_level', 'label': 'VIX level (raw)', 'group': 'macro', 'desc': 'the raw VIX close, not percentile-ranked'},
    {'name': 'compression_60m', 'label': '60-minute compression', 'group': 'structure', 'desc': 'whether the hourly chart was coiled (narrow Bollinger inside Keltner) at entry'},
    {'name': 'trend_slope', 'label': 'daily trend slope (20d)', 'group': 'structure', 'desc': 'slope of a 20-day linear fit through daily closes'},
    {'name': 'day_of_week', 'label': 'day of week', 'group': 'state', 'desc': 'Monday through Friday, encoded 0-4'},
    {'name': 'session_time_bucket', 'label': 'time of day bucket', 'group': 'state', 'desc': 'which 30-minute bucket of the session the entry bar falls in'},
]
FEATURE_NAMES = [f['name'] for f in FEATURES]


def _cell(seed, survives, lb_agrees, n=1500, lb_n=90, with_lift=True):
    # deterministic, no RNG import needed -- a simple hash-ish spread is enough for a fixture
    rho = ((seed * 37) % 21 - 10) / 40.0  # roughly -0.25..0.25
    if survives:
        rho = abs(rho) + 0.06
        if seed % 2 == 0:
            rho = -rho
        half = 0.03 + (seed % 5) * 0.004
    else:
        rho = rho * 0.35
        half = abs(rho) + 0.05 + (seed % 4) * 0.01
    ci_lo, ci_hi = rho - half, rho + half
    if survives:
        # keep the interval off zero on the same side as rho
        if rho >= 0 and ci_lo < 0.01:
            ci_lo = 0.01
        if rho < 0 and ci_hi > -0.01:
            ci_hi = -0.01
    q = 0.02 if survives else 0.35 + (seed % 5) * 0.05
    lb_rho = rho * (0.7 if lb_agrees else -0.6) if lb_agrees is not None else None
    out = {
        'rho': round(rho, 4), 'ci_lo': round(ci_lo, 4), 'ci_hi': round(ci_hi, 4),
        'q': round(q, 4), 'n': n, 'survives': bool(survives), 'beats_probe': bool(survives),
        'lb_rho': (round(lb_rho, 4) if lb_rho is not None else None), 'lb_n': lb_n,
        'lb_agrees': lb_agrees,
    }
    if with_lift:
        # LIFT (v73.539): a second, tail-aware statistic -- independent spread from rho above,
        # roughly 1/3 of cells survive (seed % 3 == 0), a subset of those repeat in the lockbox
        # (lb_lift_agrees) so at least one data-fbliftdiamond is guaranteed on screen.
        lift_r = ((seed * 53) % 27 - 13) / 20.0  # roughly -0.65..0.65
        lift_survives = (seed % 3 == 0)
        if lift_survives:
            lift_r = abs(lift_r) + 0.15
            if seed % 2 == 1:
                lift_r = -lift_r
        else:
            lift_r = lift_r * 0.4
        lift_half = 0.05 + (seed % 5) * 0.01
        lift_lo, lift_hi = lift_r - lift_half, lift_r + lift_half
        if lift_survives:
            if lift_r >= 0 and lift_lo < 0.02:
                lift_lo = 0.02
            if lift_r < 0 and lift_hi > -0.02:
                lift_hi = -0.02
        lift_p = 0.004 if lift_survives else 0.28 + (seed % 4) * 0.05
        lb_lift_agrees = None
        lb_lift_r = None
        if lift_survives:
            lb_lift_agrees = (seed % 2 == 0)
            lb_lift_r = lift_r * (0.75 if lb_lift_agrees else -0.55)
        out.update({
            'lift_r': round(lift_r, 4), 'lift_lo': round(lift_lo, 4), 'lift_hi': round(lift_hi, 4),
            'lift_p': round(lift_p, 4), 'lift_q': round(min(0.4, lift_p * 1.5), 4),
            'lift_beats_probe': bool(lift_survives), 'lift_survives': bool(lift_survives),
            'lb_lift_r': (round(lb_lift_r, 4) if lb_lift_r is not None else None),
            'lb_lift_agrees': lb_lift_agrees,
        })
    return out


def build_feature_board_fixture(with_lift=True):
    cells = {}
    diamond_planted = False
    lift_diamond_planted = False
    for fi, feat in enumerate(FEATURES):
        row = {}
        for li, leg in enumerate(LEGS):
            seed = fi * 7 + li * 3 + 1
            survives = ((fi + li) % 3 == 0)
            lb_agrees = None
            if survives:
                lb_agrees = True if (fi == 0 and li in (0, 1)) or (fi == 3 and li == 2) else ((seed % 2) == 0)
            row[leg['key']] = _cell(seed, survives, lb_agrees, with_lift=with_lift)
            if row[leg['key']].get('lb_agrees'):
                diamond_planted = True
            if row[leg['key']].get('lift_survives') and row[leg['key']].get('lb_lift_agrees'):
                lift_diamond_planted = True
        cells[feat['name']] = row
    if not diamond_planted:
        # belt and braces: force at least one diamond so the probe's own assertion is
        # never accidentally starved by the deterministic spread above
        cells[FEATURES[0]['name']][LEGS[0]['key']]['lb_agrees'] = True
        cells[FEATURES[0]['name']][LEGS[0]['key']]['survives'] = True
    if with_lift and not lift_diamond_planted:
        # same belt-and-braces guard, for the lift triangle (data-fbliftdiamond)
        cells[FEATURES[1]['name']][LEGS[1]['key']]['lift_survives'] = True
        cells[FEATURES[1]['name']][LEGS[1]['key']]['lb_lift_agrees'] = True

    verdicts = [
        {'feature': 'compression_60m', 'tier': 'PROMOTED', 'sign': '+',
         'families_agree': ['ORB', 'NOISE', 'TTM'], 'legs_agree': ['ORB_314', 'NOISE_304', 'TTM_299'],
         'lb_agree_count': 3,
         'reason': 'A coiled hourly chart at entry lines up with better expectancy on three unrelated families, and the lockbox year repeats it on all three.'},
        {'feature': 'vix_pctile', 'tier': 'PROMOTED', 'sign': '-',
         'families_agree': ['ORB', 'ENGU-Q'], 'legs_agree': ['ORB_314', 'ORB_234', 'ENGUQ_226'],
         'lb_agree_count': 2,
         'reason': 'A high VIX percentile the prior day lines up with worse outcomes on both ORB legs and the ENGU-Q leg, and the lockbox year agrees on two of the three.'},
        {'feature': 'gap_pct', 'tier': 'WATCH', 'sign': 'mixed',
         'families_agree': ['NOISE'], 'legs_agree': ['NOISE_304'],
         'lb_agree_count': 1,
         'reason': 'The overnight gap lines up with an effect on one leg only so far; worth tracking, not yet promoted.'},
    ]
    if with_lift:
        # basis: rank-only, lift-only and both -- one of each, so the probe can prove the
        # basis pill (data-fbbasis) actually threads the real value through, not a stub.
        verdicts[0]['basis'] = 'both'
        verdicts[1]['basis'] = 'rank'
        verdicts[2]['basis'] = 'lift'

    rule = {
        'promote_families': 3, 'fdr_q': 0.10, 'lockbox_min_trades': 30,
        'note': 'A feature is PROMOTED only when at least three unrelated strategy families clear the significance bar on the same sign, after a false-discovery-rate correction; the lockbox year is read for agreement only, never for promotion.',
    }
    if with_lift:
        rule['lift_note'] = ('lift = average R per trade when the feature is high minus when it is low; '
                              'it catches big-winner effects the rank test cannot see')

    return {
        'generated': '2026-09-07T09:00:00Z',
        'version': 1,
        'rule': rule,
        'legs': LEGS,
        'features': FEATURES,
        'cells': cells,
        'verdicts': verdicts,
    }


def _hold_curve():
    buckets = []
    edges = [0, 5, 10, 15, 20, 25, 30, 40, 50, 65, 90]
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        mfe = round(0.4 + i * 0.11, 3)
        fin = round(0.15 + (i % 4) * 0.05 - (0.02 if i > 6 else 0), 3)
        buckets.append({
            'bucket': '%d-%d' % (lo, hi), 'bars_lo': lo, 'bars_hi': hi,
            'n': max(5, 220 - i * 18), 'mfe_r_med': mfe, 'final_r_med': fin,
            'win_pct': round(0.55 - i * 0.015, 3),
        })
    return buckets


def _stage(n, capture_med=0.58, mfe_w=1.35, mfe_l=0.62, r1=0.22, r05=0.41, gb_r=0.71, gb_usd=38000):
    return {
        'n': n,
        'winners': {'n': int(n * 0.42), 'mfe_r_med': mfe_w, 'mfe_r_p25': round(mfe_w * 0.6, 2),
                    'mfe_r_p75': round(mfe_w * 1.6, 2), 'mae_r_med': 0.18,
                    'capture_med': capture_med, 'capture_p25': round(capture_med * 0.6, 3)},
        'losers': {'n': int(n * 0.58), 'mfe_r_med': mfe_l, 'mae_r_med': 0.95,
                   'share_reached_0_5r': r05, 'share_reached_1r': r1},
        'hold_curve': _hold_curve(),
        'peak_timing': {'med_peak_frac': 0.44, 'share_peak_first_half': 0.61},
        'give_back': {'med_r': gb_r, 'usd_per_year': gb_usd},
    }


def build_exit_autopsy_fixture():
    reads = {
        'ORB_314': 'The exit gives back about 40 cents of R on the median winner; tightening it would trade a small amount of give-back for a real risk of cutting the rare big trend trade short.',
        'ORB_234': 'Similar profile to #314 with a slightly earlier scale-out, which shows up as a smaller theoretical give-back but a lower median best move too.',
        'NOISE_304': 'Losers reach half an R more often than winners keep of their own best move, which is the ordinary shape of a mean-reversion exit, not a red flag.',
        'NOISE_243': 'Nearly identical to #304 -- the two are one parameter apart, and the exit read does not distinguish them.',
        'ENGUQ_226': 'The ETH session exit holds through more chop than the RTH-only variant, which shows up as a wider hold curve and a larger theoretical give-back that is not realistically reachable.',
        'TTM_299': 'Smallest sample of the six; the exit numbers are directionally consistent with the other families but should not be treated as settled on 61 lockbox trades.',
    }
    legs = []
    for i, leg in enumerate(LEGS):
        pre = _stage(leg['n_pre'], capture_med=0.55 + i * 0.02, mfe_w=1.2 + i * 0.08,
                     mfe_l=0.6 + i * 0.03, r1=0.20 + i * 0.01, r05=0.38 + i * 0.01,
                     gb_r=0.65 + i * 0.03, gb_usd=30000 + i * 4200)
        lb = _stage(leg['n_lb'], capture_med=0.50 + i * 0.02, mfe_w=1.05 + i * 0.07,
                    mfe_l=0.55 + i * 0.03, r1=0.18 + i * 0.01, r05=0.35 + i * 0.01,
                    gb_r=0.55 + i * 0.03, gb_usd=5200 + i * 900)
        legs.append({
            'key': leg['key'], 'family': leg['family'], 'label': leg['label'], 'file': leg['file'],
            'run': leg['run'], 'instrument': leg['instrument'], 'timeframe': leg['timeframe'],
            'session': leg['session'], 'window': leg['window'], 'lockbox_from': leg['lockbox_from'],
            'side_source': 'engine', 'r_unit_usd': 50.0 + i * 5,
            'parity': {'expected_net': leg['net_pre'] + leg['net_lb'], 'got_net': leg['net_pre'] + leg['net_lb'], 'ok': True},
            'pre': pre, 'lb': lb, 'read': reads[leg['key']],
        })
    return {
        'generated': '2026-09-07T09:00:00Z', 'version': 1,
        'r_note': 'R is defined per strategy as its own initial stop distance; dollar figures divide by r_unit_usd to compare across instruments.',
        'legs': legs,
    }


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>featboard probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var FB=__FB__, EX=__EX__, NFEAT=__NFEAT__, NLEG=__NLEG__;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      var sink={errors:[],uncaught:[]};
      var origErr=w.console.error;
      w.console.error=function(){var parts=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];
        parts.push(a&&a.stack?String(a.stack):String(a));}
        sink.errors.push(parts.join(' '));try{origErr.apply(w.console,arguments);}catch(_){}};
      w.addEventListener('error',function(ev){sink.uncaught.push(String(ev&&ev.message||ev));});
      w.addEventListener('unhandledrejection',function(ev){var r=ev&&ev.reason;
        sink.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.call=w.eval("(function(){try{"
        +"window.__FEATBOARD_FIXTURE="+JSON.stringify(FB)+";"
        +"window.__EXIT_FIXTURE="+JSON.stringify(EX)+";"
        +"window._fbData=null;window._exitData=null;window._fbFetching=0;window._exFetching=0;"
        +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify({cmpMode:'featboard',fbRowMode:'all'}))+");"
        +"activeTab='augur';augurSub='cmp';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      out.header=d.querySelectorAll('[data-fbheader]').length;
      out.verdicts=d.querySelectorAll('[data-fbverdict]').length;
      out.rows=d.querySelectorAll('tr[data-fbrow]').length;
      out.cells=d.querySelectorAll('td[data-fbcell]').length;
      out.diamonds=d.querySelectorAll('[data-fbdiamond]').length;
      out.liftCells=d.querySelectorAll('[data-fblift]').length;
      out.liftDiamonds=d.querySelectorAll('[data-fbliftdiamond]').length;
      out.basisPills=d.querySelectorAll('[data-fbbasis]').length;
      // scoped to #app (the render root), NOT document.body -- index.html's whole source
      // lives in one inline <script> under <body>, and textContent walks INTO script tags,
      // so body.textContent would always contain this JS file's own string literals
      // regardless of what actually rendered. #app holds only rendered output, no <script>.
      var appEl=d.getElementById('app');
      var appTxt=(appEl&&appEl.textContent)||'';
      out.legendHasLift=appTxt.indexOf('lift reading that repeats in the lockbox')>=0;
      out.legendHasLiftGlyph=appTxt.indexOf('▲')>=0;
      var exitCards=d.querySelectorAll('[data-fbexitcard]');
      out.exitCards=exitCards.length;
      out.exitCardsWithChart=0;
      for(var i=0;i<exitCards.length;i++){
        if(exitCards[i].querySelectorAll('[data-fbholdbar]').length>0)out.exitCardsWithChart++;
      }
      out.scrollWidth=d.documentElement.scrollWidth;
      out.clientWidth=d.documentElement.clientWidth;
      out.errors=sink.errors.slice(0,20);
      out.uncaught=sink.uncaught.slice(0,20);
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='FEATBOARDPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
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


def _fb_has_lift(fb):
    """True if ANY cell in fb['cells'] carries a lift_r key -- mirrors index.html's own
    _fbAnyLift gate, so this probe checks the render against the same rule the app uses."""
    for row in (fb.get('cells') or {}).values():
        for c in (row or {}).values():
            if c and 'lift_r' in c:
                return True
    return False


def clean(ppath, pdir):
    try:
        os.remove(ppath)
        os.rmdir(pdir)
    except OSError:
        pass


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chrome = find_chrome()
    if not chrome:
        print('FEATBOARD PROBE: INCONCLUSIVE (no chrome found)')
        return INCONCLUSIVE

    real = '--real' in sys.argv
    nolift = '--nolift' in sys.argv
    if real:
        # render the ACTUAL docs/*.json the site will fetch, not the fixture
        with open(os.path.join(root, 'docs', 'feature_board.json'), encoding='utf-8') as f:
            fb = json.load(f)
        with open(os.path.join(root, 'docs', 'exit_autopsy.json'), encoding='utf-8') as f:
            ex = json.load(f)
        exp_verdicts = len([v for v in fb.get('verdicts', []) if v.get('tier') != 'NONE'])
    else:
        fb = build_feature_board_fixture(with_lift=not nolift)
        ex = build_exit_autopsy_fixture()
        assert len(fb['features']) == 12, len(fb['features'])
        assert len(fb['legs']) == 6, len(fb['legs'])
        assert len(ex['legs']) == 6, len(ex['legs'])
        exp_verdicts = 3

    pdir = os.path.join(root, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    html = (PROBE_HTML.replace('__FB__', json.dumps(fb))
                       .replace('__EX__', json.dumps(ex))
                       .replace('__NFEAT__', str(len(fb['features'])))
                       .replace('__NLEG__', str(len(fb['legs']))))
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(html)
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    with tempfile.TemporaryDirectory() as ud:
        args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                '--hide-scrollbars', '--virtual-time-budget=30000',
                '--user-data-dir=' + ud, '--dump-dom', url]
        try:
            out = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=120).stdout or ''
        except subprocess.TimeoutExpired:
            clean(ppath, pdir)
            print('FEATBOARD PROBE: INCONCLUSIVE (chrome timed out)')
            return INCONCLUSIVE
    clean(ppath, pdir)
    m = re.search(r'FEATBOARDPROBE: (\{.*?\})\s*<', out, re.S)
    if not m:
        print('FEATBOARD PROBE: INCONCLUSIVE (probe produced no reading)')
        return INCONCLUSIVE
    d = json.loads(m.group(1))
    if d.get('err'):
        print('FEATBOARD PROBE: INCONCLUSIVE (%s)' % d.get('err'))
        return INCONCLUSIVE

    n_feat, n_leg = len(fb['features']), len(fb['legs'])
    exp_cells = n_feat * n_leg
    has_lift = _fb_has_lift(fb)
    exp_lift_cells = exp_cells if has_lift else 0
    print('FEATBOARD PROBE: version %s, why=%s' % (d.get('VERSION'), d.get('why')))
    print('  call=%s' % str(d.get('call'))[:200])
    print('  header=%s verdicts=%s rows=%s(/%s) cells=%s(/%s) diamonds=%s'
          % (d.get('header'), d.get('verdicts'), d.get('rows'), n_feat,
             d.get('cells'), exp_cells, d.get('diamonds')))
    print('  has_lift=%s liftCells=%s(/%s) liftDiamonds=%s basisPills=%s legendHasLift=%s'
          % (has_lift, d.get('liftCells'), exp_lift_cells, d.get('liftDiamonds'),
             d.get('basisPills'), d.get('legendHasLift')))
    print('  exitCards=%s(/%s) exitCardsWithChart=%s scrollWidth=%s clientWidth=%s'
          % (d.get('exitCards'), n_leg, d.get('exitCardsWithChart'),
             d.get('scrollWidth'), d.get('clientWidth')))

    bad = []
    if d.get('call') != 'OK':
        bad.append('renderApp threw: ' + str(d.get('call'))[:300])
    if not d.get('header'):
        bad.append('header block did not render ([data-fbheader] missing)')
    if d.get('verdicts') != exp_verdicts:
        bad.append('expected exactly %d verdict cards, got %s' % (exp_verdicts, d.get('verdicts')))
    if d.get('rows') != n_feat:
        bad.append('expected %d feature rows, got %s' % (n_feat, d.get('rows')))
    if d.get('cells') != n_feat * n_leg:
        bad.append('expected %d matrix cells (%d features x %d legs), got %s'
                    % (n_feat * n_leg, n_feat, n_leg, d.get('cells')))
    if not d.get('diamonds'):
        bad.append('no lockbox-agreement diamonds ([data-fbdiamond]) rendered')
    if d.get('liftCells') != exp_lift_cells:
        bad.append('expected %d [data-fblift] lines (has_lift=%s), got %s'
                    % (exp_lift_cells, has_lift, d.get('liftCells')))
    if has_lift and not d.get('liftDiamonds'):
        bad.append('no lift-agreement triangles ([data-fbliftdiamond]) rendered despite lift keys present')
    if not has_lift and d.get('liftDiamonds'):
        bad.append('lift-agreement triangles rendered with no lift keys in the data (backward-compat breach)')
    if has_lift and not d.get('legendHasLift'):
        bad.append('legend is missing the lift line ("lift reading that repeats in the lockbox")')
    if not has_lift and d.get('legendHasLift'):
        bad.append('legend shows the lift line with no lift keys in the data (backward-compat breach)')
    if has_lift and not d.get('legendHasLiftGlyph'):
        bad.append('legend/matrix carries no ▲ glyph despite lift keys present')
    if not has_lift and d.get('legendHasLiftGlyph'):
        bad.append('a ▲ glyph rendered with no lift keys in the data (backward-compat breach)')
    if has_lift and not d.get('basisPills'):
        bad.append('no basis pill ([data-fbbasis]) rendered on any verdict card despite verdict.basis present')
    if not has_lift and d.get('basisPills'):
        bad.append('basis pill rendered with no basis field on any verdict (backward-compat breach)')
    if d.get('exitCards') != n_leg:
        bad.append('expected %d exit cards, got %s' % (n_leg, d.get('exitCards')))
    if d.get('exitCardsWithChart') != d.get('exitCards'):
        bad.append('not every exit card carries a hold-curve chart (%s of %s)'
                    % (d.get('exitCardsWithChart'), d.get('exitCards')))
    sw, cw = d.get('scrollWidth'), d.get('clientWidth')
    if sw is not None and cw is not None and sw > cw:
        bad.append('horizontal overflow: scrollWidth %s > clientWidth %s' % (sw, cw))
    if d.get('errors'):
        bad.append('console.error fired: ' + '; '.join(d['errors'][:3]))
    if d.get('uncaught'):
        bad.append('uncaught exception / unhandled rejection: ' + '; '.join(d['uncaught'][:3]))

    if bad:
        print('FEATBOARD PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('FEATBOARD PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
