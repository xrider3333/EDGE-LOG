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
    return [run_doc(901, main), run_doc(902, partial), run_doc(903, bare),
            run_doc(904, modern), kpi]


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
        var ap=d.getElementById('app'); r.appLen=ap?ap.innerHTML.length:-1;
        r.nMtxCol=d.querySelectorAll('[data-mtxcol]').length;
        r.nSvg=d.querySelectorAll('svg').length;
        r.nCirc=d.querySelectorAll('circle').length;
        r.body=(ap?ap.textContent:'').replace(/[^ -~]/g,'.').slice(0,300);
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

    if bad:
        print('1E AXES PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('1E AXES PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
