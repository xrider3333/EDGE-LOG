#!/usr/bin/env python3
"""
tools/paper_render_probe.py -- render gate for the PAPER and PAPER * boards.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. tools/studies_render_probe.py proves
COMPARE > STUDIES renders. Neither enters the PAPER branch of renderApp, which is one
of the largest views in the file -- and on 2026-08-26 a change to it shipped a
mismatched paren that the boot gate happily reported as PASS right up until the app
white-screened. Same lesson as the studies probe, different view.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe, seeds the board with a
REAL captured fixture (tools/fixtures/paper_board.json -- 87 trades, 13 daily reports,
the NinjaTrader backtest-match doc and a bridge snapshot), then forces the PAPER view
and re-renders it once per control combination. No Firebase sign-in is needed: the
board reads window._paperTrades / _paperReports / _ntBtMatch, and the fixture supplies
all three.

WHAT IT ASSERTS
---------------
  * every case renders without throwing, on BOTH the PAPER and PAPER * layouts
  * every LEGS-table row carries exactly as many cells as the table has headings
    (the v73.190 nested-<td> lesson: a wrong cell count shifts every figure one
    column right under the wrong heading, and the ROW count stays correct)
  * COLUMNS: KEY genuinely shows fewer columns than ALL, and the rows follow the head
  * ARCHIVED LEGS DO NOT LEAK. With SHOW ARCHIVED off, no trade row may belong to a
    leg declared archived:true -- the defect the owner hit on 2026-08-26, where a
    retired leg had no row to switch off yet kept 13 trades in the table, the curve,
    the calendar and the board totals. With SHOW ARCHIVED on, they must come back.
  * NO RED NinjaTrader CROSS ON A LEG NinjaTrader DOES NOT RUN. A red cross means
    "NinjaTrader was running this and refused the trade"; on a leg with no `nt` field
    nothing was ever going to take it, so the claim is unmakeable.
  * the crown glyph appears on exactly the legs declared crown:true and nowhere else
  * sorting by every sortable column renders, and never changes the row count
  * the board never silently empties

The declarations (archived / crown / nt) are read out of index.html's own leg
definitions, so the probe compares what the source DECLARES against what the page
DRAWS rather than against a list that could drift.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.

Stdlib only, plus a subprocess call to local Chrome.
"""
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

# name -> {sub, prefs, win}
#   prefs -> written into localStorage augurPrefs
#   win   -> assigned onto the iframe window before renderApp (lens-style, unsaved state)
CASES = [
    ('base',            {'sub': 'paper',  'prefs': {}, 'win': {}}),
    ('cols-all',        {'sub': 'paper',  'prefs': {'paperCols': 'all'}, 'win': {}}),
    ('paper2',          {'sub': 'paper2', 'prefs': {}, 'win': {}}),
    ('paper2-cols-all', {'sub': 'paper2', 'prefs': {'paperCols': 'all'}, 'win': {}}),
    ('fam-NOISE',       {'sub': 'paper',  'prefs': {'paperFam': 'NOISE'}, 'win': {}}),
    ('fam-ENGUQ',       {'sub': 'paper',  'prefs': {'paperFam': 'ENGU-Q'}, 'win': {}}),
    ('kind-ML',         {'sub': 'paper',  'prefs': {'paperKind': 'ML'}, 'win': {}}),
    ('kind-RAW',        {'sub': 'paper',  'prefs': {'paperKind': 'RAW'}, 'win': {}}),
    ('baselines',       {'sub': 'paper',  'prefs': {'paperBaseOnly': True}, 'win': {}}),
    ('legs-off',        {'sub': 'paper',
                         'prefs': {'paperLegOff': ['ORB', 'ORB_H', 'ENGUQ_ER', 'ENGUQ_ER_H',
                                                   'ENGUQ_L50', 'NOISE_225']}, 'win': {}}),
    ('show-archived',   {'sub': 'paper',  'prefs': {}, 'win': {'_paperShowArchived': True}}),
    ('scope-today',     {'sub': 'paper',  'prefs': {}, 'win': {'_paperMatrixScope': 'TODAY'}}),
    ('detail-open',     {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_paperShowCfg': True}}),
    ('sort-net',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'net', '_legSortDir': 'desc'}}),
    ('sort-net-asc',    {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'net', '_legSortDir': 'asc'}}),
    ('sort-pf',         {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'pf', '_legSortDir': 'desc'}}),
    ('sort-pf-asc',     {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'pf', '_legSortDir': 'asc'}}),
    ('sort-ev',         {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'ev', '_legSortDir': 'desc'}}),
    ('sort-perday',     {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'perday', '_legSortDir': 'desc'}}),
    ('sort-perday-asc', {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'perday', '_legSortDir': 'asc'}}),
    ('sort-fwd',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'fwd', '_legSortDir': 'desc'}}),
    ('sort-bf',         {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'bf', '_legSortDir': 'desc'}}),
    ('sort-leg',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'leg', '_legSortDir': 'asc'}}),
    ('sort-win',        {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'win', '_legSortDir': 'desc'}}),
    ('sort-days',       {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'days', '_legSortDir': 'desc'}}),
    ('sort-last',       {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'last', '_legSortDir': 'desc'}}),
    ('sort-n',          {'sub': 'paper',  'prefs': {'paperCols': 'all'},
                         'win': {'_legSortCol': 'n', '_legSortDir': 'desc'}}),
    # zero state: an empty board must render a clean "no trades yet", not throw.
    ('empty',           {'sub': 'paper',  'prefs': {}, 'win': {'__empty': True}}),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>paper probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__, FIX=__FIX__;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], cfg=CASES[i][1], r={};
        var empty=!!(cfg.win&&cfg.win.__empty);
        var win=JSON.parse(JSON.stringify(cfg.win||{})); delete win.__empty;
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(cfg.prefs||{}))+");"
          +"var F="+JSON.stringify(FIX)+";"
          +"window._paperTrades="+(empty?"[]":"F.trades")+";"
          +"window._paperReports="+(empty?"[]":"F.reports")+";"
          +"window._ntBtMatch=F.ntBt;window._ntBridge=F.ntBridge;"
          +"window._paperLoaded=true;window._paperLoading=false;"
          // every lens-style bit of window state reset per case, so cases cannot bleed
          +"window._paperShowArchived=false;window._paperShowCfg=false;"
          +"window._paperMatrixScope='ALL';window._legSortCol=null;window._legSortDir=null;"
          +"window._paperFam=null;window._paperKind=null;window._paperBaseOnly=null;"
          +"window._paperLegOff=null;window._paperCalMonth=null;window._ptSel=null;"
          +"var W="+JSON.stringify(win)+";for(var k in W)window[k]=W[k];"
          +"activeTab='augur';augurSub="+JSON.stringify(cfg.sub)+";renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        var ap=d.getElementById('app');
        r.appLen=ap?ap.innerHTML.length:-1;
        // ---- the LEGS table: the one whose rows carry data-paperleg
        var legRows=d.querySelectorAll('tr[data-paperleg]');
        r.legRows=legRows.length;
        r.legHead=0; r.colBad=[];
        if(legRows.length){
          var tbl=legRows[0].closest('table');
          var th=tbl?tbl.querySelectorAll('thead th'):[];
          r.legHead=th.length;
          for(var k=0;k<legRows.length;k++){
            if(legRows[k].cells.length!==th.length){
              r.colBad.push(legRows[k].getAttribute('data-paperleg')+' has '+legRows[k].cells.length
                            +' cells against '+th.length+' headings');
              break;}}
        }
        r.sortable=d.querySelectorAll('[data-lsort]').length;
        r.colsCtl=d.querySelectorAll('[data-papercols]').length;
        // ---- the TRADES table
        var body=d.getElementById('ptrades-body');
        var trows=body?body.querySelectorAll('tr[data-ptrow]'):[];
        r.tradeRows=trows.length;
        r.tradeLegs={}; r.redNoNt=[]; r.crowned={};
        for(var j=0;j<trows.length;j++){
          var cells=trows[j].cells;
          var legTxt=cells[2]?cells[2].innerText.trim():'';
          // the crown glyph rides inside the LEG cell, so strip it for the label compare
          legTxt=legTxt.replace(/\\u0001?\\uD83D\\uDC51\\uFE0F?/g,'').trim();
          r.tradeLegs[legTxt]=(r.tradeLegs[legTxt]||0)+1;
          var chips=cells[0]?cells[0].querySelectorAll('span'):[];
          for(var c=0;c<chips.length;c++){
            var t=(chips[c].textContent||'').trim();
            if(t.indexOf('NT')!==0)continue;
            var col=(chips[c].getAttribute('style')||'');
            if(col.indexOf('e24b4a')>=0&&t.indexOf('\\u2717')>0)r.redNoNt.push(legTxt);
          }
        }
        // ---- crowns actually drawn, by leg key, in the LEGS table
        for(var q=0;q<legRows.length;q++){
          var key=legRows[q].getAttribute('data-paperleg');
          r.crowned[key]=(legRows[q].innerHTML.indexOf('\\uD83D\\uDC51')>=0)?1:0;
        }
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='PAPERPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},3500);});
  setTimeout(function(){report('backstop');},45000);
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


def read_leg_defs(index_path):
    """Pull the leg declarations straight out of index.html so the probe checks the render
    against what the source SAYS, not against a hand-kept list that could drift."""
    src = io.open(index_path, encoding='utf-8', newline='').read()
    i = src.find('const PAPER_LEG_DEFS=[')
    j = src.find('\n      ];', i)
    block = src[i:j] if i >= 0 and j > i else ''
    defs = {}
    for m in re.finditer(r"\{k:'([A-Z0-9_]+)'\s*,\s*label:'([^']*)'(.*?)(?=\n\s*(?:\{k:'|//|\])|$)",
                         block, re.S):
        k, label, rest = m.group(1), m.group(2), m.group(3)
        defs[k] = {'label': label,
                   'archived': "archived:true" in rest,
                   'crown': "crown:true" in rest,
                   'nt': bool(re.search(r"\bnt:'", rest))}
    return defs


def main():
    try:                       # leg labels carry non-ASCII; a cp1252 console must not crash the gate
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(root, 'index.html')
    fix_path = os.path.join(root, 'tools', 'fixtures', 'paper_board.json')
    if not os.path.isfile(fix_path):
        print('PAPERPROBE: INCONCLUSIVE -- fixture missing: %s' % fix_path)
        return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print('PAPERPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE

    defs = read_leg_defs(index_path)
    if not defs:
        print('PAPERPROBE: INCONCLUSIVE -- could not read PAPER_LEG_DEFS out of index.html')
        return INCONCLUSIVE
    arch_labels = {d['label'] for d in defs.values() if d['archived']}
    crown_keys = {k for k, d in defs.items() if d['crown']}
    nt_labels = {d['label'] for d in defs.values() if d['nt']}

    fixture = json.load(io.open(fix_path, encoding='utf-8'))

    pdir = os.path.join(root, '_paperprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__CASES__', json.dumps([[n, c] for n, c in CASES]))
            .replace('__FIX__', json.dumps(fixture)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='paperprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=50000',
             '--dump-dom', 'http://127.0.0.1:%d/_paperprobe/probe.html' % port],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180).stdout
    except Exception as e:
        print('PAPERPROBE: INCONCLUSIVE -- chrome failed: %s' % e)
        return INCONCLUSIVE
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'PAPERPROBE: (\{.*?\})</pre>', out, re.S)
    if not m:
        print('PAPERPROBE: INCONCLUSIVE -- probe produced no readout')
        return INCONCLUSIVE
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        print('PAPERPROBE: INCONCLUSIVE -- unreadable readout: %s' % e)
        return INCONCLUSIVE

    if data.get('err'):
        print('PAPERPROBE: FAIL -- probe threw: %s' % data['err'])
        return FAIL

    if os.environ.get('PAPERPROBE_DUMP'):
        io.open(os.path.join(root, '_paperprobe_dump.json'), 'w', encoding='utf-8').write(
            json.dumps(data, indent=1, ensure_ascii=False))
    fails, cases = [], data.get('cases') or {}
    if len(cases) != len(CASES):
        fails.append('only %d of %d cases reported' % (len(cases), len(CASES)))

    for nm, r in cases.items():
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, r.get('call')))
            continue
        if (r.get('appLen') or 0) < 5000:
            fails.append('%s: board rendered almost nothing (appLen=%s)' % (nm, r.get('appLen')))
        if r.get('colBad'):
            fails.append('%s: %s' % (nm, '; '.join(r['colBad'])))
        if nm == 'empty':
            continue
        if not r.get('legRows'):
            fails.append('%s: LEGS table drew no rows' % nm)
        if not r.get('sortable'):
            fails.append('%s: no sortable LEGS headers rendered' % nm)
        if not r.get('colsCtl'):
            fails.append('%s: the COLUMNS control did not render' % nm)
        # ARCHIVED LEGS MUST NOT LEAK unless SHOW ARCHIVED asked for them
        def _is(lbl, pool):
            return any(lbl.startswith(x) for x in pool)
        leaked = [l for l in (r.get('tradeLegs') or {}) if _is(l, arch_labels)]
        if nm == 'show-archived':
            if arch_labels and not leaked:
                fails.append('show-archived: archived legs did not come back into the trades table')
        elif leaked:
            fails.append('%s: archived leg(s) %s still in the trades table with SHOW ARCHIVED off'
                         % (nm, ', '.join(sorted(leaked))))
        # A RED CROSS CLAIMS NinjaTrader REFUSED THE TRADE -- unmakeable for a leg it never runs
        bad_red = sorted({l for l in (r.get('redNoNt') or []) if l and not _is(l, nt_labels)})
        if bad_red:
            fails.append('%s: red NT cross on leg(s) NinjaTrader does not run: %s'
                         % (nm, ', '.join(bad_red)))
        # CROWNS: exactly the declared ones, and only those
        drawn = {k for k, v in (r.get('crowned') or {}).items() if v}
        shown = set((r.get('crowned') or {}).keys())
        want = crown_keys & shown
        if drawn != want:
            fails.append('%s: crown drawn on %s, declared %s'
                         % (nm, sorted(drawn) or '(none)', sorted(want) or '(none)'))

    # COLUMNS: KEY must genuinely be fewer columns than ALL
    b, a = cases.get('base') or {}, cases.get('cols-all') or {}
    if b.get('legHead') and a.get('legHead') and not (b['legHead'] < a['legHead']):
        fails.append('COLUMNS KEY (%s cols) is not shorter than ALL (%s cols)'
                     % (b.get('legHead'), a.get('legHead')))
    # sorting must never lose or gain a row
    base_rows = (cases.get('cols-all') or {}).get('legRows')
    for nm, r in cases.items():
        if nm.startswith('sort-') and base_rows and r.get('legRows') != base_rows:
            fails.append('%s: %s leg rows against %s unsorted' % (nm, r.get('legRows'), base_rows))

    if fails:
        print('PAPERPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return FAIL

    print('PAPERPROBE: PASS (VERSION=%s, %d cases, LEGS %s cols KEY / %s cols ALL, %s trade rows)'
          % (data.get('VERSION'), len(cases), b.get('legHead'), a.get('legHead'),
             (cases.get('base') or {}).get('tradeRows')))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
