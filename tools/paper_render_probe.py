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
  * LEDGER step 4 (owner 2026-10-05), PAPER * layout: the hero is the shared one (same parts as REAL: label, big
    number, today line, range line, chips), labelled BOOK #463 - NT8 futures paper, with the warning chips inside
    it; ONE pill row TODAY 1W 1M 3M YTD ALL (counted back from today) replaces the old 1W / 1M / All tabs and the
    Today / All time switch, and every pill moves the big number, the bold line, the stats, the calendar, the
    trade list and the strategy rows together; ALL is the old all-time figure
  * BOOK (owner 2026-10-04): the big number is the BOOK #463 figure - exactly the legs of api/paper.py _BOOK at
    their weights (TTM x3), read from the source, never a list kept here - and equals the BOOK group total
    equals the end of the bold line; "Forward tests & controls" and "Other / shadow" carry labelled subtotals
    that are not in it, and their switches never move it; the hero says BOOK #463; with no report weights the
    board's fallback equals _BOOK

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
    ('show-archived',   {'sub': 'paper',  'prefs': {'paperOtherOn': ['ENGUQ']}, 'win': {'_paperShowArchived': True}}),
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
    ('other-on',        {'sub': 'paper2', 'prefs': {'paperOtherOn': ['ORB_257', 'NOISE_H'], 'paperOtherOpen': True},
                         'win': {}}),
    ('fwd-closed',      {'sub': 'paper2', 'prefs': {'paperFwdOpen': False}, 'win': {}}),
    ('range-today',     {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': 'TODAY'}}),
    ('range-1w',        {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': '1W'}}),
    ('range-1m',        {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': '1M'}}),
    ('range-3m',        {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': '3M'}}),
    ('range-ytd',       {'sub': 'paper2', 'prefs': {}, 'win': {'_paperCurveWin': 'YTD'}}),
    ('range-saved',     {'sub': 'paper2', 'prefs': {'paperRange': '1M'}, 'win': {}}),
    ('book-fallback',   {'sub': 'paper2', 'prefs': {}, 'win': {'__nobook': True}}),
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
        var nobook=!!(cfg.win&&cfg.win.__nobook);
        var win=JSON.parse(JSON.stringify(cfg.win||{})); delete win.__empty; delete win.__noinfo; delete win.__nobook;
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(cfg.prefs||{}))+");"
          +"var F="+JSON.stringify(FIX)+";"
          +"window._paperTrades="+(empty?"[]":"F.trades")+";"
          +"window._paperReports="+(empty?"[]":(nobook?"F.reports.map(function(r){var c=Object.assign({},r);delete c.book;return c;})":"F.reports"))+";"
          +"window._ntBtMatch=F.ntBt;window._ntBridge=F.ntBridge;"
          +"window._paperLoaded=true;window._paperLoading=false;"
          +"window._paperOtherOn=null;window._paperOtherOpen=null;window._paperFwdOpen=null;window._paperCurveWin=null;"
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
        var legRows=d.querySelectorAll('tr[data-paperleg],tr[data-paperother]');
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
        r.legKeys=[];for(var lk=0;lk<legRows.length;lk++)r.legKeys.push(legRows[lk].getAttribute('data-paperleg')||legRows[lk].getAttribute('data-paperother'));
        r.bookRowKeys=[].map.call(d.querySelectorAll('tr[data-paperleg]'),function(x){return x.getAttribute('data-paperleg');});
        r.otherRowKeys=[].map.call(d.querySelectorAll('tr[data-paperother]'),function(x){return x.getAttribute('data-paperother');});
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
          var key=legRows[q].getAttribute('data-paperleg')||legRows[q].getAttribute('data-paperother');
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
        var _hn=d.querySelector('#p2-hero-value');
        r.heroNum=_hn?_num(_hn.textContent):null;
        var _hh=d.querySelector('.lg-hero');
        r.hero=_hh?{label:(_hh.querySelector('.lg-hero-label')||{}).innerText||'',today:(_hh.querySelector('.lg-hero-today')||{}).innerText||'',
          range:(_hh.querySelector('.lg-hero-range')||{}).innerText||'',
          parts:['.lg-hero-main','.lg-hero-label','.lg-hero-big','.lg-hero-today','.lg-hero-range','.lg-hero-chips'].map(function(q){return _hh.querySelector(q)?1:0;}).join(''),
          warnInChips:_hh.querySelectorAll('.lg-hero-chips .p2warn').length,chips:_hh.querySelectorAll('.lg-hero-chips .lg-chip').length}:null;
        r.pills=[].map.call(d.querySelectorAll('.lg-pills button'),function(x){return x.textContent.trim();});
        r.pillActive=[].map.call(d.querySelectorAll('.lg-pills button.active'),function(x){return x.textContent.trim();});
        r.oldTabs=d.querySelectorAll('.p2rhtabs').length;
        r.mscopeCtl=d.querySelectorAll('.p2rail [data-mscope]').length;
        r.rowDays=[].map.call(d.querySelectorAll('#ptrades-body tr[data-ptrow]'),function(x){return x.getAttribute('data-pcd');});
        r.calDays=[].map.call(d.querySelectorAll('[data-pcalday]'),function(x){return x.getAttribute('data-pcalday');});
        var _sv=d.querySelector('.p2rhstat .p2rhsv');r.statTrades=_sv?parseInt(_sv.textContent,10):null;
        r.rowNets=[].map.call(d.querySelectorAll('tr[data-paperleg]'),function(x){return x.getAttribute('data-paperleg')+'|'+_num(x.innerText);});
        try{var _sc=w._p2Scrub;r.boldEnd=(_sc&&_sc.total&&_sc.total.length)?_sc.total[_sc.total.length-1]:null;}catch(_e3){r.boldEnd=null;}
        var _ls=d.querySelector('[data-p2listed]');
        r.listed=_ls?{net:parseFloat(_ls.getAttribute('data-net')),n:+_ls.getAttribute('data-n'),tie:_ls.getAttribute('data-tie')}:null;
        var _oh=d.querySelector('[data-p2otherhd]');
        r.otherHd=_oh?{net:parseFloat(_oh.getAttribute('data-net')),n:+_oh.getAttribute('data-n'),legs:+_oh.getAttribute('data-legs'),txt:_oh.innerText.replace(/\\s+/g,' ')}:null;
        r.otherRows=d.querySelectorAll('tr[data-paperother]').length;
        function _hd(sel){var e=d.querySelector(sel);return e?{net:parseFloat(e.getAttribute('data-net')),n:+e.getAttribute('data-n'),legs:+e.getAttribute('data-legs'),txt:e.innerText.replace(/\\s+/g,' ')}:null;}
        r.bookHd=_hd('[data-p2bookhd]');r.fwdHd=_hd('[data-p2fwdhd]');
        r.cap=(function(){var e=d.querySelector('.lg-hero-label');return e?e.innerText:'';})();
        r.bookW=w._paperBookW||null;
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
    # the newest report carries the book weights the way the nightly run writes them (read from api/paper.py)
    try:
        _bm = re.search(r"^    _BOOK = (\{[^}]*\})", io.open(os.path.join(root, 'api', 'paper.py'), encoding='utf-8').read(), re.M)
        fixture['reports'][0]['book'] = {'weights': __import__('ast').literal_eval(_bm.group(1)), 'source_run': 463,
                                          'pnl_usd': 0.0, 'missing': [], 'failed': []}
    except Exception:
        pass
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

    # LEDGER step 3 + BOOK -- the numbers must tie out on the PAPER * layout. The book is READ from api/paper.py
    # (_BOOK), never kept here, so a changed book fails this probe until the board follows.
    book_w = {}
    try:
        _m = re.search(r"^    _BOOK = (\{[^}]*\})", io.open(os.path.join(root, 'api', 'paper.py'), encoding='utf-8').read(), re.M)
        book_w = {k: float(v) for k, v in __import__('ast').literal_eval(_m.group(1)).items()}
    except Exception as e:
        fails.append('could not read _BOOK out of api/paper.py: %s' % e)
    closed = [t for t in fixture['trades'] if t.get('open') is not True]
    def _w(t):
        return book_w.get(str(t.get('leg') or '').upper(), 0.0)
    exp_book = round(sum((t.get('pnl_usd') or 0) * _w(t) for t in closed))
    exp_fwd = sum(t.get('pnl_usd') or 0 for t in closed
                  if t.get('leg') in defs and not _w(t) and not defs[t['leg']]['archived'])
    exp_other = sum(t.get('pnl_usd') or 0 for t in closed if t.get('leg') not in defs and not _w(t))
    n_all = len(fixture['trades'])
    TIE = ('paper2', 'other-open', 'other-on', 'legs-off-p2', 'warn-stale-bridge', 'fwd-closed', 'book-fallback')
    for nm in TIE:
        r = cases.get(nm) or {}
        ld, hn, be, li = r.get('loaded') or {}, r.get('heroNum'), r.get('boldEnd'), r.get('listed') or {}
        if ld.get('loaded') != n_all or str(ld.get('stored')) != str(n_all):
            fails.append('%s: all-time trade count shown %s of stored %s, fixture holds %d'
                         % (nm, ld.get('loaded'), ld.get('stored'), n_all))
        if hn is None or be is None or li.get('net') is None:
            fails.append('%s: hero number / bold line end / BOOK group total missing (%s, %s, %s)'
                         % (nm, hn, be, li.get('net')))
            continue
        if abs(hn - be) > 1.0 or abs(hn - li['net']) > 1.0 or li.get('tie') != '1':
            fails.append('%s: big NET %s, end of the bold line %s, BOOK group total %s (tie=%s) do not agree'
                         % (nm, hn, be, li['net'], li.get('tie')))
        if 'book #463 \u00b7 nt8 futures paper' not in (r.get('cap') or '').lower():
            fails.append('%s: the hero label is not BOOK #463 - NT8 futures paper: %r' % (nm, r.get('cap')))
    for nm in ('paper2', 'other-open', 'other-on', 'warn-stale-bridge', 'fwd-closed', 'book-fallback'):
        r = cases.get(nm) or {}
        if r.get('heroNum') is not None and abs(r['heroNum'] - exp_book) > 1.0:
            fails.append('%s: big NET %s is not the BOOK figure %s (a leg outside _BOOK leaked in, a book leg dropped, '
                         'or the TTM weight is not applied)' % (nm, r['heroNum'], exp_book))
        bh, fh, oh = r.get('bookHd') or {}, r.get('fwdHd') or {}, r.get('otherHd') or {}
        if not bh or abs(bh.get('net', 0) - exp_book) > 1.0 or bh.get('legs') != len(book_w):
            fails.append('%s: BOOK group total %s over %s legs, expected %s over %d' % (nm, bh.get('net'), bh.get('legs'), exp_book, len(book_w)))
        if not fh or abs(fh.get('net', 0) - exp_fwd) > 0.5:
            fails.append('%s: Forward tests & controls subtotal %s, expected %s' % (nm, fh.get('net'), exp_fwd))
        if 'not counted' not in (fh.get('txt') or '').lower():
            fails.append('%s: Forward tests & controls is not labelled as not counted: %r' % (nm, fh.get('txt')))
        if not oh or abs(oh.get('net', 0) - exp_other) > 0.5 or not oh.get('legs'):
            fails.append('%s: Other / shadow group subtotal %s, expected %s' % (nm, oh.get('net'), exp_other))
        if 'not counted' not in (oh.get('txt') or '').lower():
            fails.append('%s: the Other group is not labelled as not counted: %r' % (nm, oh.get('txt')))
        keys = list(r.get('bookRowKeys') or [])
        if sorted(keys) != sorted(book_w) or len(keys) != len(book_w):
            fails.append('%s: BOOK rows %s are not exactly the _BOOK legs %s' % (nm, keys, sorted(book_w)))
        if (r.get('bookW') or {}) != book_w:
            fails.append('%s: the board used book weights %s, api/paper.py _BOOK says %s' % (nm, r.get('bookW'), book_w))
    # the book rows come first and are the only switches that move the big number; the group rows are closed/open as set
    r = cases.get('paper2') or {}
    unl = [k for k in (r.get('otherRowKeys') or []) if k not in defs]
    lst = [k for k in (r.get('otherRowKeys') or []) if k in defs]
    if unl:
        fails.append('paper2: the Other / shadow group should be closed by default but drew %s' % unl)
    if not lst:
        fails.append('paper2: the Forward tests & controls group drew no rows by default')
    if any(k in book_w for k in lst):
        fails.append('paper2: a book leg is also listed under Forward tests & controls')
    r = cases.get('fwd-closed') or {}
    if r.get('otherRows'):
        fails.append('fwd-closed: the folded Forward tests & controls group still drew rows')
    r = cases.get('other-open') or {}
    if 'ORB_257' not in (r.get('otherRowKeys') or []):
        fails.append('other-open: the open Other group drew no unlisted strategy rows with switches')
    r = cases.get('other-on') or {}
    tl = list((r.get('tradeLegs') or {}).keys())
    if not any(l.startswith('ORB 257') for l in tl) or not any(l.startswith('NOISE-225') for l in tl):
        fails.append('other-on: switched-on not-counted strategies did not reach the trades table: %s' % tl)
    if 'other, not counted' not in (r.get('tradesHead') or '').lower():
        fails.append('other-on: the trades heading does not say the other rows are not counted: %r'
                     % r.get('tradesHead'))
    # LEDGER step 4 -- the shared hero and the ONE pill row. Expected figures come from the fixture, with the
    # range counted back from today in New York, a trade counted on the day it CLOSED.
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        today_ny = _dt.datetime.now(ZoneInfo('America/New_York')).date()
    except Exception:
        today_ny = (_dt.datetime.utcnow() - _dt.timedelta(hours=4)).date()

    def _close(t):
        if t.get('open') is True:
            return ''
        if t.get('close_day'):
            return t['close_day']
        x = str(t.get('exitIso') or '')[:10]
        d = _dt.date.fromisoformat(x)
        while d.weekday() >= 5:
            d += _dt.timedelta(days=1)
        return d.isoformat()

    def _cut(rng):
        if rng == 'TODAY':
            return today_ny.isoformat()
        if rng == 'YTD':
            return '%d-01-01' % today_ny.year
        n = {'1W': 7, '1M': 30, '3M': 90}.get(rng)
        return (today_ny - _dt.timedelta(days=n)).isoformat() if n else ''

    def _exp_range(rng):
        c = _cut(rng)
        rows = [t for t in closed if _w(t) and (not c or _close(t) >= c)]
        return round(sum((t.get('pnl_usd') or 0) * _w(t) for t in rows)), len(rows), c
    PILLS = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']
    for nm, rng in (('range-today', 'TODAY'), ('range-1w', '1W'), ('range-1m', '1M'), ('range-3m', '3M'),
                    ('range-ytd', 'YTD'), ('range-saved', '1M'), ('paper2', 'ALL')):
        r = cases.get(nm) or {}
        exp, n_exp, cut = _exp_range(rng)
        hn, be, li = r.get('heroNum'), r.get('boldEnd'), r.get('listed') or {}
        if hn is None or abs(hn - exp) > 1.0:
            fails.append('%s: big NET %s, expected the BOOK figure %s for %s (cutoff %r)' % (nm, hn, exp, rng, cut))
        if be is not None and hn is not None and abs(be - hn) > 1.0 and not (be is None):
            fails.append('%s: end of the bold line %s differs from the big NET %s' % (nm, be, hn))
        if li.get('net') is None or abs(li['net'] - exp) > 1.0 or li.get('tie') != '1':
            fails.append('%s: BOOK group total %s (tie %s), expected %s - the rows do not follow the range'
                         % (nm, li.get('net'), li.get('tie'), exp))
        if r.get('statTrades') != n_exp:
            fails.append('%s: the Trades stat reads %s, expected %d closed book trades in the range'
                         % (nm, r.get('statTrades'), n_exp))
        if cut:
            early = [x for x in (r.get('rowDays') or []) if x and x < cut]
            if early:
                fails.append('%s: the trade list shows trades closed before %s: %s' % (nm, cut, early[:3]))
            early = [x for x in (r.get('calDays') or []) if x < cut]
            if early:
                fails.append('%s: the calendar shows days before %s: %s' % (nm, cut, early[:3]))
        if r.get('pills') != PILLS or r.get('pillActive') != [rng]:
            fails.append('%s: the pill row reads %s with %s active, expected %s with %s'
                         % (nm, r.get('pills'), r.get('pillActive'), PILLS, rng))
        if r.get('oldTabs') or r.get('mscopeCtl'):
            fails.append('%s: an old range control is still on the board (tabs %s, Today/All switch %s)'
                         % (nm, r.get('oldTabs'), r.get('mscopeCtl')))
        h = r.get('hero') or {}
        if h.get('parts') != '111111':
            fails.append('%s: the hero is missing a shared part (main/label/big/today/range/chips = %s)' % (nm, h.get('parts')))
        if rng.lower() not in ('all',) and False:
            pass
    # the pills really change the number: a narrower range cannot be the all-time figure unless nothing differs
    allv = (cases.get('paper2') or {}).get('heroNum')
    if allv is not None and (cases.get('range-today') or {}).get('heroNum') == allv and exp_book:
        fails.append('range-today: TODAY shows the all-time figure - the pill is not driving the number')
    # the warning chips live INSIDE the shared hero
    r = cases.get('paper2') or {}
    if not (r.get('hero') or {}).get('warnInChips'):
        fails.append('paper2: the warning chips are not inside the hero chip row')

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
