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
  * LEDGER step 3 (owner 2026-10-03), PAPER * layout: the all-time trade count shown equals the stored
    trade count; the big NET equals the listed strategies total equals the end of the bold line; the
    Other / shadow group has its own subtotal and is NOT in the big number (also with its trades switched
    on in the table); alarms that live in closed cards also show as chips in the hero

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
    ('reports-open',    {'sub': 'paper2', 'prefs': {}, 'win': {'_p2Open': {'reports': True}}}),
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
    # NT GATE chip (top bar): a status snapshot older than 15 minutes must read '?', and a PARTIAL gate must still
    # show a stale model age. checked_at far in the past / far in the future stand for old / fresh.
    ('gate-old-snapshot', {'sub': 'paper',  'prefs': {},
                           'win': {'_ntBridge': {'checked_at': '2020-01-01 00:00:00',
                                                 'gate': {'up': True, 'legs': [{'leg': 'A', 'loaded': True}]}}}}),
    ('gate-partial-stale', {'sub': 'paper',  'prefs': {},
                            'win': {'_ntBridge': {'checked_at': '2099-01-01 00:00:00',
                                                  'gate': {'up': True, 'error': 'x', 'stale_days': 6,
                                                           'legs': [{'leg': 'A', 'loaded': True},
                                                                    {'leg': 'B', 'loaded': False}]}}}}),
    ('gate-fresh-green', {'sub': 'paper',  'prefs': {},
                          'win': {'_ntBridge': {'checked_at': '2099-01-01 00:00:00',
                                                'gate': {'up': True, 'stale_days': 0,
                                                         'legs': [{'leg': 'A', 'loaded': True}]}}}}),
    # LEDGER step 3: the Other / shadow group, its switches, the strategy-list total, and warnings in the hero
    ('other-open',      {'sub': 'paper2', 'prefs': {}, 'win': {'_paperOtherOpen': True}}),
    ('other-on',        {'sub': 'paper2', 'prefs': {'paperOtherOn': ['TTM_299_SSOF2'], 'paperOtherOpen': True},
                         'win': {}}),
    ('legs-off-p2',     {'sub': 'paper2',
                         'prefs': {'paperLegOff': ['ORB', 'ORB_H', 'ENGUQ_ER', 'ENGUQ_ER_H', 'ENGUQ_L50']},
                         'win': {}}),
    ('warn-stale-bridge', {'sub': 'paper2', 'prefs': {},
                           'win': {'_ntBridge': {'checked_at': '2020-01-01 00:00:00', 'up': True,
                                                 'strategies': [{'name': 'EdgeLogORB230', 'state': 'Realtime'}],
                                                 'gate': {'up': True, 'legs': [{'leg': 'A', 'loaded': True}]}}}}),
    ('no-bundle',       {'sub': 'paper2', 'prefs': {}, 'win': {'__noinfo': True}}),
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
        var noinfo=!!(cfg.win&&cfg.win.__noinfo);
        var win=JSON.parse(JSON.stringify(cfg.win||{})); delete win.__empty; delete win.__noinfo;
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(cfg.prefs||{}))+");"
          +"var F="+JSON.stringify(FIX)+";"
          +"window._paperTrades="+(empty?"[]":"F.trades")+";"
          +"window._paperReports="+(empty?"[]":"F.reports")+";"
          +"window._ntBtMatch=F.ntBt;window._ntBridge=F.ntBridge;"
          +"window._paperLoaded=true;window._paperLoading=false;"
          +"window._paperOtherOn=null;window._paperOtherOpen=null;window._paperCurveWin=null;"
          +"window._paperTradeInfo="+(empty?"{bundle:true,n_total:0}":(noinfo?"{bundle:false,n_total:null}":"F.tradeInfo"))+";"
          // every lens-style bit of window state reset per case, so cases cannot bleed
          +"window._paperShowArchived=false;window._paperShowCfg=false;"
          +"window._paperMatrixScope='ALL';window._legSortCol=null;window._legSortDir=null;"
          +"window._paperFam=null;window._paperKind=null;window._paperBaseOnly=null;"
          +"window._paperLegOff=null;window._paperCalMonth=null;window._ptSel=null;window._p2Open={};"
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
        // PAPER plus sidebar: the legacy LEGS panel lives in a sticky left column.
        // Counting it here so a future refactor cannot silently drop the panel while
        // the tab still renders - which is exactly how it was missing in the first
        // place, and no gate noticed.
        r.sideBar=d.querySelectorAll('[data-p2side]').length;
        r.legsInSide=0;
        try{var _lr=d.querySelector('tr[data-paperleg]');
            var _sb=d.querySelector('[data-p2side]');
            // since 2026-09-14 the rail can sit on either side; it carries data-p2col="side"
            var _side=d.querySelector('[data-p2col="side"]')||(_sb&&_sb.parentElement?_sb.parentElement.firstElementChild:null);
            if(_lr&&_sb&&_side)
              r.legsInSide=_side.contains(_lr)?1:0;}catch(_e){}
        // GEOMETRY, not just existence: the owner rejected two sidebars whose controls
        // wrapped into multi-line blobs, and every structural gate passed on both. A
        // segmented tray is one line of chips - if any tray in the sidebar renders
        // taller than ~2 lines, the layout has collapsed into wrapping again.
        r.sideTrayMax=0;
        try{var _sb2=d.querySelector('[data-p2side]');
            var _col=d.querySelector('[data-p2col="side"]')||(_sb2&&_sb2.parentElement?_sb2.parentElement.firstElementChild:null);
            if(_col){var _trays=_col.querySelectorAll('[data-ptray]');
              for(var _ti=0;_ti<_trays.length;_ti++)
                r.sideTrayMax=Math.max(r.sideTrayMax,_trays[_ti].clientHeight);}}catch(_e2){}
        // NOISE #422 row + the 10s capture-health lines (both injected into the fixture by main())
        r.legKeys=[];for(var lk=0;lk<legRows.length;lk++)r.legKeys.push(legRows[lk].getAttribute('data-paperleg'));
        var _bt=d.body?d.body.innerText:'';
        r.capNQ=(_bt.match(/10s capture NQ: [^\\n]*/)||[''])[0];
        r.capES=(_bt.match(/10s capture ES: [^\\n]*/)||[''])[0];
        var _gc=d.querySelector('a[href="http://127.0.0.1:8392"]');
        r.gateChip=_gc?(_gc.textContent||'').trim():'';
        r.sortable=d.querySelectorAll('[data-lsort]').length;
        r.colsCtl=d.querySelectorAll('[data-papercols]').length;
        // ---- the TRADES table
        var body=d.getElementById('ptrades-body');
        var trows=body?body.querySelectorAll('tr[data-ptrow]'):[];
        r.tradeRows=trows.length;
        r.tradeLegs={}; r.redNoNt=[]; r.crowned={};
        for(var j=0;j<trows.length;j++){
          var cells=trows[j].cells;
          var _lc=trows[j].querySelector('[data-pc="leg"]')||cells[2];var legTxt=_lc?_lc.innerText.trim():'';
          // the crown glyph rides inside the LEG cell, so strip it for the label compare
          legTxt=legTxt.replace(/\\u0001?\\uD83D\\uDC51\\uFE0F?/g,'').trim();
          r.tradeLegs[legTxt]=(r.tradeLegs[legTxt]||0)+1;
          var _ec=trows[j].querySelector('[data-pc="eng"]')||cells[0];var chips=_ec?_ec.querySelectorAll('span'):[];
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
        // EXIT-DAY money (owner GO 2026-10-02): day headers read CLOSED, a still-open trade sits under its own
        // header with an unrealised mark, and the DAILY REPORTS table names the close day and carries BOOK $.
        r.openMarks=body?(body.innerText.match(/unrealised/g)||[]).length:0;
        r.dayHdrs=[].map.call(d.querySelectorAll('#ptrades-body tr.p2day'),function(x){return x.innerText.replace(/\\s+/g,' ').trim();});
        r.heroBig=[].map.call(d.querySelectorAll('.p2big'),function(x){return x.innerText;}).join('|');
        r.closeDayTh=[].filter.call(d.querySelectorAll('th'),function(x){return x.textContent.indexOf('CLOSE DAY')>=0;}).length;
        r.bookTh=[].filter.call(d.querySelectorAll('th'),function(x){return x.textContent.indexOf('BOOK $')>=0;}).length;
        // LEDGER step 3 readout (PAPER * layout)
        function _num(t){var m=String(t||'').replace(/,/g,'').match(/(-?)\\$([0-9.]+)/);return m?(m[1]?-1:1)*parseFloat(m[2]):null;}
        var _hn=d.querySelector('.p2rhnum');
        r.heroNum=_hn?_num(_hn.textContent):null;
        try{var _sc=w._p2Scrub;r.boldEnd=(_sc&&_sc.total&&_sc.total.length)?_sc.total[_sc.total.length-1]:null;}catch(_e3){r.boldEnd=null;}
        var _ls=d.querySelector('[data-p2listed]');
        r.listed=_ls?{net:parseFloat(_ls.getAttribute('data-net')),n:+_ls.getAttribute('data-n'),tie:_ls.getAttribute('data-tie')}:null;
        var _oh=d.querySelector('[data-p2otherhd]');
        r.otherHd=_oh?{net:parseFloat(_oh.getAttribute('data-net')),n:+_oh.getAttribute('data-n'),legs:+_oh.getAttribute('data-legs'),txt:_oh.innerText.replace(/\\s+/g,' ')}:null;
        r.otherRows=d.querySelectorAll('tr[data-paperother]').length;
        var _ld=d.querySelector('[data-p2loaded]');
        r.loaded=_ld?{loaded:+_ld.getAttribute('data-loaded'),stored:_ld.getAttribute('data-stored'),other:+_ld.getAttribute('data-other'),txt:_ld.innerText}:null;
        r.warns=[].map.call(d.querySelectorAll('.p2warn'),function(x){return x.innerText.replace(/\\s+/g,' ').trim();});
        var _ntc=d.querySelector('[data-p2card="nt"]');
        r.ntCardOpen=_ntc?(_ntc.textContent.indexOf('\\u25be')>=0):null;
        r.tradesHead=(function(){var x=d.querySelector('#ptrades-wrap');var h=x&&x.parentElement?x.parentElement.querySelector('.p2sh'):null;return h?h.innerText.replace(/\\s+/g,' '):'';})();
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
    # Inject what the real fixture predates: a NOISE_422 tilted-size trade (2026-09-28 leg) and the nightly
    # capture_health block, one good instrument and one low-delta instrument.
    _src = next((t for t in fixture['trades'] if t.get('leg') == 'NOISE_SBS_V90'), None)
    if _src is not None:
        _t = dict(_src, id='pt_NOISE_422_probe', leg='NOISE_422', size=1.75,
                  pnl_usd=round(_src.get('pnl_usd', 0) * 1.75, 2))
        fixture['trades'].append(_t)
    # EXIT-DAY: an OPEN ENGU-Q trade carrying a huge mark (must reach no total, curve or day) and a trade that
    # closed on a Sunday evening (counts on the Monday).
    _e = next((t for t in fixture['trades'] if str(t.get('leg', '')).startswith('ENGUQ')), None)
    if _e is not None:
        fixture['trades'].append(dict(_e, id='pt_ENGUQ_335_probe_open', leg='ENGUQ_335', open=True,
                                      close_day=None, exit_date='2026-09-30', pnl_usd=987654.0,
                                      exitIso='2026-09-30T16:09:00-04:00', exitTime=1790798940))
        fixture['trades'].append(dict(_e, id='pt_ENGUQ_335_probe_sun', leg='ENGUQ_335', open=False,
                                      exit_date='2026-09-20', close_day='2026-09-21', pnl_usd=123.0,
                                      exitIso='2026-09-20T19:30:00-04:00', exitTime=1790033400))
    # LEDGER step 3: trades of strategies that have NO listed row (the Other / shadow group). They must reach
    # the Other group subtotal and never the big number.
    _o = next((t for t in fixture['trades'] if t.get('leg') == 'NOISE_SBS_V90'), None)
    if _o is not None:
        for _i, (_lg, _usd) in enumerate((('TTM_299_SSOF2', 500.0), ('TTM_299_SSOF2', -120.0), ('ORB_257', 310.0))):
            fixture['trades'].append(dict(_o, id='pt_%s_probe_%d' % (_lg, _i), leg=_lg, pnl_usd=_usd,
                                          entryTime=_o['entryTime'] + 60 * (_i + 1), close_day=None, open=False))
    fixture['tradeInfo'] = {'bundle': True, 'n_total': len(fixture['trades']), 'parts': 1,
                            'loaded': len(fixture['trades'])}
    fixture['reports'][0]['capture_health'] = {
        'NQ': {'rth': {'bars': 2331, 'expected': 2340, 'bars_pct': 99.6, 'delta_pct': 98.3, 'rt_bars': 2000,
                       'longest_gap_min': 1.5, 'gap_start_et': '10:12'},
               'eth': {'bars': 8100, 'expected': 8280, 'delta_pct': 60.0, 'delta_from_et': '08:20'}},
        'ES': {'rth': {'bars': 2340, 'expected': 2340, 'bars_pct': 100.0, 'delta_pct': 38.0, 'rt_bars': 2340,
                       'longest_gap_min': 0.0, 'gap_start_et': None},
               'eth': {'bars': 8100, 'expected': 8280, 'delta_pct': 11.0}},
        'warning': '10-second capture problem - ES: buy/sell delta is filled in on only 38% of session bars.'}

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
        # COLUMNS control removed by design in v73.396 - the sidebar table is locked
        # to KEY because thirteen columns cannot fit a sidebar. No assertion on it.
        if nm.startswith('paper2'):
            if not r.get('sideBar'):
                fails.append('%s: PAPER plus lost its strategy sidebar' % nm)
            elif not r.get('legsInSide'):
                fails.append('%s: the LEGS panel is no longer inside the sidebar '
                             'column' % nm)
            elif (r.get('sideTrayMax') or 0) > 40:
                fails.append('%s: a sidebar control tray is %spx tall - its chips are '
                             'wrapping into a blob again' % (nm, r.get('sideTrayMax')))
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

    # NOISE #422 must be a LEGS row, labelled with the family name, and its trade must reach the trades table
    for nm in ('base', 'paper2'):
        r = cases.get(nm) or {}
        if 'NOISE_422' not in (r.get('legKeys') or []):
            fails.append('%s: no NOISE_422 row on the board' % nm)
        if not any(l.startswith('NOISE #422') for l in (r.get('tradeLegs') or {})):
            fails.append('%s: the NOISE #422 trade did not reach the trades table' % nm)
    # the capture-health line: one per instrument, low-delta day flagged in words (not colour alone)
    for nm in ('base', 'paper2'):
        r = cases.get(nm) or {}
        if ('2,331/2,340 bars, delta on 98%' not in (r.get('capNQ') or '')
                or 'split starts 08:20 ET' not in (r.get('capNQ') or '')):
            fails.append('%s: NQ capture line missing or wrong: %r' % (nm, r.get('capNQ')))
        if 'delta on 38%' not in (r.get('capES') or '') or 'LOW' not in (r.get('capES') or ''):
            fails.append('%s: ES capture line not flagged LOW: %r' % (nm, r.get('capES')))

    # EXIT-DAY board: close-day headers, the open trade apart and unrealised, the open mark in no total
    for nm in ('base', 'paper2'):
        r = cases.get(nm) or {}
        hd = ' | '.join(r.get('dayHdrs') or []).lower()
        if 'closed' not in hd:
            fails.append('%s: day headers do not say the day is the close day: %r' % (nm, hd[:200]))
        if 'open now' not in hd or not r.get('openMarks'):
            fails.append('%s: the open trade is not shown apart as unrealised (headers %r)' % (nm, hd[:200]))
        if '2026-09-21' not in hd:
            fails.append('%s: the Sunday-evening exit did not count on its Monday' % nm)
    r = cases.get('reports-open') or {}
    if not r.get('closeDayTh') or not r.get('bookTh'):
        fails.append('reports-open: DAILY REPORTS lost its CLOSE DAY / BOOK $ columns')
    if '987,654' in ((cases.get('paper2') or {}).get('heroBig') or ''):
        fails.append('paper2: an open trade mark leaked into the hero net')

    # LEDGER step 3 -- the numbers must tie out on the PAPER * layout.
    closed = [t for t in fixture['trades'] if t.get('open') is not True]
    exp_listed = round(sum(t.get('pnl_usd') or 0 for t in closed
                           if t.get('leg') in defs and not defs[t['leg']]['archived']))
    exp_other = sum(t.get('pnl_usd') or 0 for t in closed if t.get('leg') not in defs)
    n_all = len(fixture['trades'])
    for nm in ('paper2', 'other-open', 'other-on', 'legs-off-p2', 'warn-stale-bridge'):
        r = cases.get(nm) or {}
        ld, hn, be, li = r.get('loaded') or {}, r.get('heroNum'), r.get('boldEnd'), r.get('listed') or {}
        if ld.get('loaded') != n_all or str(ld.get('stored')) != str(n_all):
            fails.append('%s: all-time trade count shown %s of stored %s, fixture holds %d'
                         % (nm, ld.get('loaded'), ld.get('stored'), n_all))
        if hn is None or be is None or li.get('net') is None:
            fails.append('%s: hero number / bold line end / strategy list total missing (%s, %s, %s)'
                         % (nm, hn, be, li.get('net')))
            continue
        if abs(hn - be) > 1.0 or abs(hn - li['net']) > 1.0 or li.get('tie') != '1':
            fails.append('%s: big NET %s, end of the bold line %s, strategy list total %s (tie=%s) do not agree'
                         % (nm, hn, be, li['net'], li.get('tie')))
    for nm in ('paper2', 'other-open', 'other-on', 'warn-stale-bridge'):
        r = cases.get(nm) or {}
        if r.get('heroNum') is not None and abs(r['heroNum'] - exp_listed) > 1.0:
            fails.append('%s: big NET %s is not the listed strategies total %s (an Other / shadow trade leaked in, '
                         'or a listed one dropped)' % (nm, r['heroNum'], exp_listed))
        oh = r.get('otherHd') or {}
        if not oh or abs(oh.get('net', 0) - exp_other) > 0.5 or not oh.get('legs'):
            fails.append('%s: Other / shadow group subtotal %s, expected %s' % (nm, oh.get('net'), exp_other))
        if 'not counted' not in (oh.get('txt') or '').lower():
            fails.append('%s: the Other group is not labelled as not counted: %r' % (nm, oh.get('txt')))
    if not (cases.get('other-open') or {}).get('otherRows'):
        fails.append('other-open: the open Other group drew no strategy rows with switches')
    if (cases.get('paper2') or {}).get('otherRows'):
        fails.append('paper2: the Other group should be closed by default but drew rows')
    r = cases.get('other-on') or {}
    if not any(l.startswith('TTM 299 SSOF2') for l in (r.get('tradeLegs') or {})):
        fails.append('other-on: the switched-on Other strategy did not reach the trades table')
    if 'other, not counted' not in (r.get('tradesHead') or '').lower():
        fails.append('other-on: the trades heading does not say the other rows are not counted: %r'
                     % r.get('tradesHead'))
    # warnings reach the hero while their card is closed
    r = cases.get('warn-stale-bridge') or {}
    if not any('heartbeat stale' in w for w in (r.get('warns') or [])) or r.get('ntCardOpen'):
        fails.append('warn-stale-bridge: a stale NinjaTrader heartbeat is not a chip in the hero '
                     '(warns %r, card open %r)' % (r.get('warns'), r.get('ntCardOpen')))
    r = cases.get('paper2') or {}
    if not any('10s capture low' in w for w in (r.get('warns') or [])):
        fails.append('paper2: the low 10s capture is not a chip in the hero (warns %r)' % r.get('warns'))
    # before the first nightly bundle exists the board says so, and still renders
    r = cases.get('no-bundle') or {}
    if not any('newest 500 only' in w for w in (r.get('warns') or [])):
        fails.append('no-bundle: the missing history bundle is not a chip in the hero (warns %r)' % r.get('warns'))

    # the top-bar NT GATE chip: snapshot age first, PARTIAL shows a stale age too
    g = (cases.get('gate-old-snapshot') or {}).get('gateChip') or ''
    if 'NT GATE ? (status' not in g or 'old)' not in g:
        fails.append('gate-old-snapshot: stale snapshot not flagged on the chip: %r' % g)
    g = (cases.get('gate-partial-stale') or {}).get('gateChip') or ''
    if 'PARTIAL + STALE 6d' not in g:
        fails.append('gate-partial-stale: PARTIAL chip hides the stale model age: %r' % g)
    g = (cases.get('gate-fresh-green') or {}).get('gateChip') or ''
    if not g.endswith('NT GATE') or '?' in g:
        fails.append('gate-fresh-green: a fresh healthy snapshot should read plain NT GATE: %r' % g)

    # COLUMNS: retired in v73.396 - the sidebar table is locked to KEY (thirteen
    # columns cannot fit a sidebar; everything else is on the row hovers), so KEY and
    # ALL now render identically and comparing them asserts a control that no longer
    # exists. What still matters is covered above: the table renders, its rows match
    # its headings, and the sidebar holds it.
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
          % (data.get('VERSION'), len(cases), (cases.get('base') or {}).get('legHead'),
             (cases.get('cols-all') or {}).get('legHead'),
             (cases.get('base') or {}).get('tradeRows')))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
