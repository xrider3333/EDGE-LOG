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
  * LEDGER step 5 (owner 2026-10-05): the curve is the shared ledgerChartRender - drawn at least 200 px tall on the
    laptop, with dates and a price scale, one faint line per shown book leg and a legend for them; the LAST point is
    the big number; a mouse hover and a finger drag write the hero number and the range line, and leaving puts them back
  * LEDGER steps 6, 7 and 10 (owner plan 2026-10-05; MANAGER 2026-10-06), PAPER * layout, each checked against a
    recomputation from the FIXTURE (the counted trades: book legs at their weights, closed, in the range, walked in the
    order they closed) and never against a number read off the page:
      - STATS: the four shared tiles in order (win rate, profit factor, max drawdown, trades) replace the ten-cell grid;
        drawdown is a POSITIVE dollar amount equal to the recomputation; the More stats fold opens with Returns, Risk, Mix
        and "Strategy vs control", holds every value the old grid showed (average trade / win / loss, best / worst day,
        green days, drawdown) and is remembered per browser; a range with no counted trades reads -- (the shared strip)
      - CALENDAR: the shared month calendar - a month's total and trade count equal the fixture's, a WEEK column, amber
        caveat days (roll splice / ORB look-ahead), the month arrows and the fold remembered per browser, and a day tap
        selects the rows that CLOSED that day (a trade entered weeks earlier included)
      - STRATEGY LIST: the shared list in the order BOOK #463 / Forward tests & controls / Other / shadow / Retired (the
        last two folds, closed); the BOOK group total equals the big number; every row is named family + run number, has a
        live-state dot, a signed P&L with an arrow and a switch; flipping a BOOK switch moves the big number, the chart
        end, the tiles, the calendar, the list and the trade list together, a not-counted strategy's switch only lists its
        trades; a row tap does what its switch does
      - PHONE (375 x 812): the trade list starts within one screen of the board top, the strategy list sits BELOW it with
        one line per row, the folds are closed and the page never scrolls sideways
      - ?oldboards=1 still gives the previous layout (ten-cell grid, old calendar, LEGS table) for one more version
  * money colours FOLLOW THE THEME (owner decision 8, 2026-10-05): no fixed green / red hex on a money cell, and
    every headline money cell carries an arrow and a sign, every dense one a sign
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

# name -> {sub, prefs, win, ls, frame}
#   prefs -> written into localStorage augurPrefs
#   win   -> assigned onto the iframe window before renderApp (lens-style, unsaved state)
#   ls    -> extra localStorage items (the per-browser LEDGER fold / month choices) set before renderApp
#   frame -> which iframe renders it: 'f' (laptop, default), 'fp' (375 px phone), 'fo' (laptop with ?oldboards=1)
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
    # LEDGER steps 6, 7 and 10 (PAPER * layout): the Retired fold, the More stats / calendar folds and the calendar month
    # remembered per browser, a 375 px phone, and the ?oldboards=1 escape hatch (the previous layout, one more version)
    ('retired-open',    {'sub': 'paper2', 'prefs': {'paperOtherOn': ['ENGUQ']}, 'win': {'_paperShowArchived': True}}),
    ('stats-open',      {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_stats_nt8': '1'}}),
    ('cal-closed',      {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_cal_nt8': '0'}}),
    ('cal-aug',         {'sub': 'paper2', 'prefs': {}, 'win': {}, 'ls': {'el_lg_calmo_nt8': '2026-08'}}),
    ('phone375',        {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fp'}),
    ('oldboards-paper2', {'sub': 'paper2', 'prefs': {}, 'win': {}, 'frame': 'fo'}),
    # zero state: an empty board must render a clean "no trades yet", not throw.
    ('empty',           {'sub': 'paper',  'prefs': {}, 'win': {'__empty': True}}),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>paper probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<iframe id="fp" src="../index.html" style="width:375px;height:812px;border:0"></iframe>
<iframe id="fo" src="../index.html?oldboards=1" style="width:1500px;height:1000px;border:0"></iframe>
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
        fr=document.getElementById(cfg.frame||'f'); w=fr.contentWindow; d=fr.contentDocument;
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
          // the per-browser LEDGER choices (More stats fold, calendar fold, calendar month) start empty in every case
          +"localStorage.removeItem('el_lg_stats_nt8');localStorage.removeItem('el_lg_cal_nt8');localStorage.removeItem('el_lg_calmo_nt8');"
          +"var LS="+JSON.stringify(cfg.ls||{})+";for(var lk in LS)localStorage.setItem(lk,LS[lk]);"
          +"var W="+JSON.stringify(win)+";for(var k in W)window[k]=W[k];"
          +"activeTab='augur';augurSub="+JSON.stringify(cfg.sub)+";renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        var ap=d.getElementById('app');
        r.appLen=ap?ap.innerHTML.length:-1;
        // ---- the LEGS table: the one whose rows carry data-paperleg
        var legRows=d.querySelectorAll('tr[data-paperleg],tr[data-paperother]');
        var listRows=d.querySelectorAll('[data-lglist="p2"] [data-lgrow]');
        r.legRows=legRows.length+listRows.length;
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
        try{var _lr=d.querySelector('tr[data-paperleg],[data-lglist="p2"] [data-lgrow]');
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
        for(var lk2=0;lk2<listRows.length;lk2++)r.legKeys.push(listRows[lk2].getAttribute('data-lgrow'));
        var _gk=function(g){return [].map.call(d.querySelectorAll('[data-lglist="p2"] .lg-grp[data-lggroup="'+g+'"] [data-lgrow]'),function(x){return x.getAttribute('data-lgrow');});};
        r.bookRowKeys=[].map.call(d.querySelectorAll('tr[data-paperleg]'),function(x){return x.getAttribute('data-paperleg');}).concat(_gk('book'));
        r.otherRowKeys=[].map.call(d.querySelectorAll('tr[data-paperother]'),function(x){return x.getAttribute('data-paperother');}).concat(_gk('fwd'),_gk('other'),_gk('retired'));
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
            if((col.indexOf('e24b4a')>=0||col.indexOf('var(--red)')>=0)&&t.indexOf('\\u2717')>0)r.redNoNt.push(legTxt);
          }
        }
        // ---- crowns actually drawn, by leg key, in the LEGS table
        for(var q=0;q<legRows.length;q++){
          var key=legRows[q].getAttribute('data-paperleg')||legRows[q].getAttribute('data-paperother');
          r.crowned[key]=(legRows[q].innerHTML.indexOf('\\uD83D\\uDC51')>=0)?1:0;
        }
        for(var q2=0;q2<listRows.length;q2++){
          r.crowned[listRows[q2].getAttribute('data-lgrow')]=(listRows[q2].innerHTML.indexOf('\\uD83D\\uDC51')>=0)?1:0;
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
        r.calDays=[].map.call(d.querySelectorAll('[data-pcalday],[data-lgcalday]'),function(x){return x.getAttribute('data-pcalday')||x.getAttribute('data-lgcalday');});
        var _sv=d.querySelector('.p2rhstat .p2rhsv')||d.querySelector('[data-lgstat="trades"] .lg-stat-val');r.statTrades=_sv?parseInt(_sv.textContent,10):null;
        r.moneyHex=[].filter.call(d.querySelectorAll('#ptrades-body span.p2num, #p2legs span.p2num, .p2rhstat .p2rhsv span, [data-pcalday] div, tr[data-p2bookhd] span, tr[data-p2fwdhd] span, tr[data-p2otherhd] span, [data-lglist="p2"] .lg-row-val, [data-lglist="p2"] .lg-row-val *, [data-lglist="p2"] [data-p2grp] *, .lg-stats .lg-stat-val, .lg-more-panel .v, .lg-more-panel .v *, .lg-cal-panel [data-lgcalday], .lg-cal-panel [data-lgcalday] *'),function(x){return /#1d9e75|#e24b4a/i.test(x.getAttribute('style')||'');}).length;
        r.moneyMarks=[].map.call(d.querySelectorAll('#ptrades-body span.p2num, #p2legs span.p2num'),function(x){return x.innerText.trim();})
          .concat([].map.call(d.querySelectorAll('[data-lglist="p2"] .lg-row-val'),function(x){return x.innerText.split(String.fromCharCode(10))[0].trim();}));
        r.calMarks=[].map.call(d.querySelectorAll('[data-pcalday] > div:last-child'),function(x){return x.innerText.trim();})
          .concat([].map.call(d.querySelectorAll('[data-lgcalday] .m'),function(x){return x.innerText.trim();}));
        r.grpMarks=[].map.call(d.querySelectorAll('tr[data-p2bookhd] span:last-child, tr[data-p2fwdhd] > td > div > span:last-child, tr[data-p2otherhd] > td > div > span:last-child'),function(x){return x.innerText.trim();})
          .concat([].map.call(d.querySelectorAll('[data-p2grp] .lg-up, [data-p2grp] .lg-down'),function(x){return x.innerText.trim();})).filter(function(x){return x.indexOf('$')>=0;});
        r.maxDD=(function(){var o=null;[].forEach.call(d.querySelectorAll('.p2rhstat'),function(x){var l=x.querySelector('.p2rhsl');if(l&&/max drawdown/i.test(l.textContent))o=(x.querySelector('.p2rhsv')||{}).innerText||'';});
          var n2=d.querySelector('[data-lgstat="maxdd"] .lg-stat-val');if(n2)o=n2.innerText;return o;})();
        var _cs=d.querySelector('#p2-chart svg'),_pc=w._p2Chart||null;
        r.chart=_cs?{h:+_cs.getAttribute('height'),dates:_cs.querySelectorAll('[data-lgdate]').length,ticks:_cs.querySelectorAll('[data-lgtick]').length,
          legend:d.querySelectorAll('#p2-chart .lg-legend [data-lgline]').length,n:_pc?_pc.pts.length:0,last:(_pc&&_pc.pts.length)?_pc.pts[_pc.pts.length-1].v:null,
          faint:_cs.querySelectorAll('path[stroke-dasharray]').length}:null;
        r.scrub=null;
        if(_cs&&nm==='paper2'){
          try{
            var big=d.getElementById('p2-hero-value'),rng=d.getElementById('p2-hero-range');
            var b0=big.textContent,g0=rng.innerHTML,rc=_cs.getBoundingClientRect();
            var mk=function(t,x,pt){return new w.PointerEvent(t,{clientX:rc.left+x,clientY:rc.top+40,pointerType:pt,bubbles:true,pointerId:7});};
            _cs.dispatchEvent(mk('pointermove',rc.width*0.5,'mouse'));var m1=big.textContent,m1r=rng.innerText;
            _cs.dispatchEvent(mk('pointerleave',0,'mouse'));var mBack=(big.textContent===b0&&rng.innerHTML===g0);
            _cs.dispatchEvent(mk('pointerdown',rc.width*0.02,'touch'));var t1=big.textContent;
            _cs.dispatchEvent(mk('pointermove',rc.width*0.6,'touch'));var t2=big.textContent;
            _cs.dispatchEvent(mk('pointerup',0,'touch'));var tBack=(big.textContent===b0&&rng.innerHTML===g0);
            r.scrub={b0:b0,m1:m1,m1r:m1r,mBack:mBack,t1:t1,t2:t2,tBack:tBack};
          }catch(e){r.scrub={err:String(e)};}
        }
        r.rowNets=[].map.call(d.querySelectorAll('tr[data-paperleg]'),function(x){return x.getAttribute('data-paperleg')+'|'+_num(x.innerText);});
        try{var _sc=w._p2Scrub;r.boldEnd=(_sc&&_sc.total&&_sc.total.length)?_sc.total[_sc.total.length-1]:null;}catch(_e3){r.boldEnd=null;}
        var _ls=d.querySelector('[data-p2listed]');
        r.listed=_ls?{net:parseFloat(_ls.getAttribute('data-net')),n:+_ls.getAttribute('data-n'),tie:_ls.getAttribute('data-tie')}:null;
        var _oh=d.querySelector('[data-p2otherhd],[data-p2grp="other"]');
        r.otherHd=_oh?{net:parseFloat(_oh.getAttribute('data-net')),n:+_oh.getAttribute('data-n'),legs:+_oh.getAttribute('data-legs'),txt:_oh.innerText.replace(/\\s+/g,' ')}:null;
        r.otherRows=d.querySelectorAll('tr[data-paperother]').length+_gk('fwd').length+_gk('other').length+_gk('retired').length;
        function _hd(sel){var e=d.querySelector(sel);return e?{net:parseFloat(e.getAttribute('data-net')),n:+e.getAttribute('data-n'),legs:+e.getAttribute('data-legs'),txt:e.innerText.replace(/\\s+/g,' ')}:null;}
        r.bookHd=_hd('[data-p2bookhd],[data-p2grp="book"]');r.fwdHd=_hd('[data-p2fwdhd],[data-p2grp="fwd"]');r.retHd=_hd('[data-p2grp="retired"]');
        r.cap=(function(){var e=d.querySelector('.lg-hero-label');return e?e.innerText:'';})();
        r.bookW=w._paperBookW||null;
        var _ld=d.querySelector('[data-p2loaded]');
        r.loaded=_ld?{loaded:+_ld.getAttribute('data-loaded'),stored:_ld.getAttribute('data-stored'),other:+_ld.getAttribute('data-other'),txt:_ld.innerText}:null;
        r.warns=[].map.call(d.querySelectorAll('.p2warn'),function(x){return x.innerText.replace(/\\s+/g,' ').trim();});
        var _ntc=d.querySelector('[data-p2card="nt"]');
        r.ntCardOpen=_ntc?(_ntc.textContent.indexOf('\\u25be')>=0):null;
        r.tradesHead=(function(){var x=d.querySelector('#ptrades-wrap');var h=x&&x.parentElement?x.parentElement.querySelector('.p2sh'):null;return h?h.innerText.replace(/\\s+/g,' '):'';})();
        // ---- LEDGER steps 6, 7 and 10 on the PAPER * layout: the shared stats strip + More stats, the shared calendar, the shared list
        function _t(e){return e?e.textContent.replace(/\\s+/g,' ').trim():null;}
        function _top(e){if(!e)return null;return Math.round(e.getBoundingClientRect().top+(w.pageYOffset||0));}
        r.statTiles=[].map.call(d.querySelectorAll('.lg-stats [data-lgstat]'),function(e){return {k:e.getAttribute('data-lgstat'),v:_t(e.querySelector('.lg-stat-val')),sub:_t(e.querySelector('.lg-stat-sub')),top:_top(e)};});
        r.oldStatCells=d.querySelectorAll('.p2rhstat').length;
        r.oldHero=!!d.querySelector('[data-p2num]');
        var _ls0=d.querySelector('[data-lglist="p2"]');
        r.groups=_ls0?[].map.call(_ls0.querySelectorAll('.lg-grp'),function(g){var f=g.querySelector('[data-lggrp]');
          return {key:g.getAttribute('data-lggroup'),rows:g.querySelectorAll('[data-lgrow]').length,fold:!!f,open:f?f.getAttribute('aria-expanded'):null,txt:_t(g.querySelector('.lg-grp-hd'))};}):[];
        r.listRowInfo=_ls0?[].map.call(_ls0.querySelectorAll('[data-lgrow]'),function(x){var sw=x.querySelector('[data-lgsw]'),gp=x.closest('.lg-grp');
          return {key:x.getAttribute('data-lgrow'),name:_t(x.querySelector('.lg-row-name')),group:gp?gp.getAttribute('data-lggroup'):null,sw:sw?sw.getAttribute('aria-checked'):null,off:x.classList.contains('off'),
            val:(x.querySelector('.lg-row-val')||{innerText:''}).innerText.split(String.fromCharCode(10))[0].trim(),h:Math.round(x.getBoundingClientRect().height),dot:!!x.querySelector('.lg-row-name i'),sub:_t(x.querySelector('.lg-row-sub'))};}):[];
        var _tw=d.querySelector('#ptrades-wrap'),_tcard=(_tw&&_tw.closest)?_tw.closest('.p2sheet'):null;
        r.geo={vw:w.innerWidth,vh:w.innerHeight,scrollW:d.documentElement.scrollWidth,clientW:d.documentElement.clientWidth,boardTop:_top(d.querySelector('.p2rh')),
          tradesTop:_top(_tcard),listTop:_top(_ls0),moreTop:_top(d.querySelector('[data-lgmore="p2"]')),calTop:_top(d.querySelector('[data-lgcalfold="p2"]')),
          stripTop:_top(d.querySelector('.lg-stats')),chartTop:_top(d.querySelector('#p2-chart'))};
        r.sideSticky=(function(){var c=d.querySelector('[data-p2col="side"]');return c?w.getComputedStyle(c).position:null;})();
        r.calFold=(function(){var b=d.querySelector('[data-lgcalfold="p2"]');return b?b.getAttribute('aria-expanded'):null;})();
        r.moreFold=(function(){var b=d.querySelector('[data-lgmore="p2"]');return b?b.getAttribute('aria-expanded'):null;})();
        function _calState(){var g=d.querySelector('.lg-cal[data-lgcal="p2"]');if(!g)return null;
          var days=g.querySelectorAll('[data-lgcalday]');
          return {month:g.getAttribute('data-lgcalmonth'),title:_t(g.querySelector('.lg-cal-title')),sum:_t(g.querySelector('.lg-cal-sum')),
            days:[].map.call(days,function(b){return b.getAttribute('data-lgcalday');}),
            dayN:[].map.call(days,function(b){return parseInt((b.querySelector('.n')||{textContent:'0'}).textContent,10)||0;}),
            cells:g.querySelectorAll('.lg-cal-grid > *').length,cav:g.querySelectorAll('.lg-cal-day.cav').length,
            prevDis:(g.querySelector('[data-lgcalmo="-1"]')||{}).disabled,nextDis:(g.querySelector('[data-lgcalmo="1"]')||{}).disabled};}
        r.cal=_calState();
        r.calPanelHidden=(function(){var p=d.getElementById('p2-cal');return p?!!p.hidden:null;})();
        r.int=null;
        if(nm==='paper2'){
          try{
            var I={};
            var _click=function(sel){var e=d.querySelector(sel);if(!e)return false;e.click();return true;};
            var _heroN=function(){var e=d.getElementById('p2-hero-value');return e?_num(e.textContent):null;};
            var _snap=function(){
              var pc=w._p2Chart||null,tl={},bk=d.querySelector('[data-p2grp="book"]');
              [].forEach.call(d.querySelectorAll('.lg-stats [data-lgstat]'),function(e){tl[e.getAttribute('data-lgstat')]=_t(e.querySelector('.lg-stat-val'));});
              return {hero:_heroN(),chartLast:(pc&&pc.pts.length)?pc.pts[pc.pts.length-1].v:null,tiles:tl,bookNet:bk?parseFloat(bk.getAttribute('data-net')):null,
                bookN:bk?+bk.getAttribute('data-n'):null,tradeRows:d.querySelectorAll('#ptrades-body tr[data-ptrow]').length,cal:_calState(),
                sw:[].map.call(d.querySelectorAll('[data-lglist="p2"] [data-lgsw]'),function(s){return s.getAttribute('data-lgsw')+'='+s.getAttribute('aria-checked');}).join(',')};};
            // More stats: opens with Returns / Risk / Mix + this board's own group, remembered per browser, closes again
            I.more={start:r.moreFold};
            if(_click('[data-lgmore="p2"]')){
              I.more.open=d.querySelector('[data-lgmore="p2"]').getAttribute('aria-expanded');
              I.more.groups=[].map.call(d.querySelectorAll('#p2-more [data-lgmsgroup]'),function(g){return g.getAttribute('data-lgmsgroup');});
              I.more.rows=[].map.call(d.querySelectorAll('#p2-more .lg-ms-row'),function(x){return [_t(x.querySelector('.l')),_t(x.querySelector('.v'))];});
              var _vs=d.querySelector('#p2-more [data-lgmsgroup="Strategy vs control"]');
              I.more.vsRows=_vs?_vs.querySelectorAll('.lg-ms-row').length:0;
              I.more.vsSubs=_vs?[].map.call(_vs.querySelectorAll('.p2vs-sub'),function(x){return _t(x);}):[];
              I.more.vsCrown=_vs?(_vs.innerHTML.indexOf('\\uD83D\\uDC51')>=0):false;
              I.more.vsTxt=_vs?_t(_vs):'';
              I.more.stored=localStorage.getItem('el_lg_stats_nt8');
              _click('[data-lgmore="p2"]');
              I.more.closed=d.querySelector('[data-lgmore="p2"]').getAttribute('aria-expanded');
              I.more.storedClosed=localStorage.getItem('el_lg_stats_nt8');
            }
            // calendar: the newest month, a day tap (the rows that CLOSED that day), then the month arrow back
            var _tap=function(){
              var dd=d.querySelectorAll('.lg-cal[data-lgcal="p2"] [data-lgcalday]');if(!dd.length)return null;
              var b=dd[dd.length-1],day=b.getAttribute('data-lgcalday'),cellN=parseInt((b.querySelector('.n')||{textContent:'0'}).textContent,10)||0;
              b.click();
              var sel=d.querySelectorAll('#ptrades-body tr.ptsel');
              var o={day:day,cellN:cellN,sel:sel.length,selDays:[].map.call(sel,function(x){return x.getAttribute('data-pcd');}),
                forDay:d.querySelectorAll('#ptrades-body tr[data-ptrow][data-pcd="'+day+'"]').length};
              w._ptSel=null;return o;};
            I.cal0=_calState();
            I.tap0=_tap();
            if(_click('[data-lgcal="p2"][data-lgcalmo="-1"]')){
              I.calPrev=_calState();
              I.calStored=localStorage.getItem('el_lg_calmo_nt8');
              I.tap1=_tap();
            }
            // the switches: from here the calendar shows the earlier month, where the ORB trades closed
            I.flip0=_snap();
            if(_click('[data-lgsw="ORB"]')){I.flip1=_snap();_click('[data-lgsw="ORB"]');I.flip2=_snap();}
            // a strategy outside the book: its switch lists its trades and never moves a counted figure
            if(_click('[data-lgsw="NOISE_H"]')){I.oth1=_snap();_click('[data-lgsw="NOISE_H"]');I.oth2=_snap();}
            // tapping the row does what its switch does
            if(_click('[data-lglist="p2"] [data-lgrow="ORB"]')){I.rowTap=_snap();_click('[data-lglist="p2"] [data-lgrow="ORB"]');}
            _click('[data-lgcal="p2"][data-lgcalmo="1"]');
            I.calBack=_calState();
            // the calendar fold: closed means the panel is hidden and the choice is stored; open again
            if(_click('[data-lgcalfold="p2"]')){
              I.calFold={closed:d.querySelector('[data-lgcalfold="p2"]').getAttribute('aria-expanded'),hidden:(d.getElementById('p2-cal')||{}).hidden,stored:localStorage.getItem('el_lg_cal_nt8')};
              _click('[data-lgcalfold="p2"]');I.calFold.reopen=d.querySelector('[data-lgcalfold="p2"]').getAttribute('aria-expanded');
            }
            r.int=I;
          }catch(e){r.int={err:String(e&&e.stack?e.stack:e)};}
        }
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='PAPERPROBE: '+JSON.stringify(out);
  }
  var _nLoaded=0;
  ['f','fp','fo'].forEach(function(id){document.getElementById(id).addEventListener('load',function(){
    _nLoaded++; if(_nLoaded===3)setTimeout(function(){report('load');},3500);});});
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


def build_fixture(root, fix_path):
    """The real captured fixture plus everything it predates (injected trades, book weights, capture health).
    Shared by the probe and by any scratch harness that wants the same board."""
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
    return fixture


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

    fixture = build_fixture(root, fix_path)

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
        if nm in ('show-archived', 'retired-open'):
            if arch_labels and not leaked:
                fails.append('%s: archived legs did not come back into the trades table' % nm)
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
    TIE = ('paper2', 'other-open', 'other-on', 'legs-off-p2', 'warn-stale-bridge', 'fwd-closed', 'book-fallback',
           'retired-open', 'stats-open', 'cal-closed', 'cal-aug', 'phone375')
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
    if not any(l.startswith('ORB 257') for l in tl) or not any(l.startswith('NOISE #225') for l in tl):
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

    # money colours follow the theme and carry a marker that needs no colour
    import re as _re
    for nm in ('paper2', 'other-open', 'other-on', 'range-1m'):
        r = cases.get(nm) or {}
        if r.get('moneyHex'):
            fails.append('%s: %d money cell(s) still use a fixed green / red hex instead of the theme colours' % (nm, r['moneyHex']))
        bad = [x for x in (r.get('moneyMarks') or []) if x and not _re.match(r'^[\u25b2\u25bc] [+-]\$', x) and x != '\u2014']
        if bad:
            fails.append('%s: money cells without an arrow and a sign: %s' % (nm, bad[:3]))
        bad = [x for x in (r.get('calMarks') or []) if not _re.match(r'^[+-]\$', x)]
        if bad:
            fails.append('%s: calendar money without a sign: %s' % (nm, bad[:3]))
        bad = [x for x in (r.get('grpMarks') or []) if not _re.search(r'[\u25b2\u25bc] [+-]\$', x)]
        if bad:
            fails.append('%s: group totals without an arrow and a sign: %s' % (nm, bad[:3]))
    # Max drawdown prints POSITIVE, the way REAL prints it ($1,234.56, no minus sign)
    for nm in ('paper2', 'range-1m', 'range-1w', 'other-on'):
        v = (cases.get(nm) or {}).get('maxDD')
        if v is not None and v.strip() == '--' and not (cases.get(nm) or {}).get('statTrades'):
            continue   # the shared strip prints -- when the range holds no counted trade (there is no drawdown to read)
        if v is None or not _re.match(r'^\$[0-9,]+(\.[0-9]{2})?$', v.strip()):
            fails.append('%s: Max drawdown reads %r, expected a positive dollar figure like REAL' % (nm, v))
    if not ((cases.get('paper2') or {}).get('moneyMarks')):
        fails.append('paper2: the colour check found no money cells to read')

    # LEDGER step 5 -- the shared chart: drawn, the last point is the big number, scrub writes the hero and restores it
    for nm in ('paper2', 'other-open', 'other-on', 'legs-off-p2', 'range-3m', 'range-ytd', 'range-1m', 'range-saved'):
        r = cases.get(nm) or {}
        c, hn = r.get('chart'), r.get('heroNum')
        if not c:
            if nm in ('range-1m', 'range-saved') and not (r.get('statTrades') or 0):
                continue
            fails.append('%s: the shared equity chart did not draw' % nm)
            continue
        if c.get('last') is None or hn is None or abs(c['last'] - hn) > 1.0:
            fails.append('%s: the last chart point %s is not the big number %s' % (nm, c.get('last'), hn))
        if (c.get('h') or 0) < 200:
            fails.append('%s: the chart is %spx tall, expected at least 200 on a laptop' % (nm, c.get('h')))
    r = cases.get('paper2') or {}
    c = r.get('chart') or {}
    if (c.get('dates') or 0) < 2 or (c.get('ticks') or 0) < 2:
        fails.append('paper2: the chart shows %s dates and %s price labels, expected at least 2 of each'
                     % (c.get('dates'), c.get('ticks')))
    if c.get('legend') != len(book_w) or (c.get('faint') or 0) < 1:
        fails.append('paper2: the chart legend has %s switches and %s faint lines, expected one per shown book leg (%d)'
                     % (c.get('legend'), c.get('faint'), len(book_w)))
    sc = r.get('scrub') or {}
    if sc.get('err') or not sc:
        fails.append('paper2: the scrub probe failed: %s' % sc.get('err'))
    else:
        if not sc.get('mBack') or not sc.get('tBack'):
            fails.append('paper2: the hero was not restored after a scrub (mouse %s, finger %s)' % (sc.get('mBack'), sc.get('tBack')))
        if sc.get('m1') == sc.get('b0') or 'that day' not in (sc.get('m1r') or ''):
            fails.append('paper2: a mouse hover did not write the hero (%r, line %r)' % (sc.get('m1'), sc.get('m1r')))
        if sc.get('t1') != '$0.00' or sc.get('t2') == sc.get('b0'):
            fails.append('paper2: a finger drag did not write the hero (start %r, later %r, big number %r)'
                         % (sc.get('t1'), sc.get('t2'), sc.get('b0')))

    # ------------------------------------------------------------------------------------------------------------
    # LEDGER steps 6, 7 and 10 -- recomputed from the fixture: the counted trades are the book legs at their weights,
    # closed, with a close day in the range, walked in the order they closed (close day, then exit time)
    import math as _math

    def _rows_for(rng, exclude=()):
        c = _cut(rng)
        rows = [t for t in closed if _w(t) and t.get('leg') not in exclude and (not c or _close(t) >= c)]
        rows.sort(key=lambda t: (_close(t), t.get('exitTime') or t.get('entryTime') or 0))
        return rows

    def _stats_of(rows):
        if not rows:
            return None
        net = peak = cur = dd = gw = gl = 0.0
        wins = losses = 0
        by_day = {}
        for t in rows:
            v = (t.get('pnl_usd') or 0) * _w(t)
            net += v
            cur += v
            peak = max(peak, cur)
            dd = max(dd, peak - cur)
            if v > 0:
                wins += 1
                gw += v
            elif v < 0:
                losses += 1
                gl -= v
            by_day[_close(t)] = by_day.get(_close(t), 0.0) + v
        dv = list(by_day.values())
        return {'n': len(rows), 'wins': wins, 'losses': losses, 'net': net, 'gw': gw, 'gl': gl, 'dd': dd,
                'wr': (wins / float(wins + losses)) if (wins + losses) else None,
                'pf': None if (not gw and not gl) else (gw / gl if gl > 0 else float('inf')),
                'avg': net / len(rows), 'avgw': (gw / wins) if wins else None, 'avgl': (gl / losses) if losses else None,
                'best': max(dv), 'worst': min(dv), 'green': sum(1 for v in dv if v > 0), 'days': len(dv)}

    def _tiles_of(e):
        if e is None:
            return {'winrate': '--', 'pf': '--', 'maxdd': '--', 'trades': '0'}
        pf = '--' if e['pf'] is None else ('no losses' if e['pf'] == float('inf') else '%.2f' % e['pf'])
        wr = '--' if e['wr'] is None else '%d%%' % int(_math.floor(e['wr'] * 100 + 0.5))
        return {'winrate': wr, 'pf': pf, 'maxdd': '${:,.2f}'.format(e['dd']), 'trades': str(e['n'])}

    def _money_in(txt):
        m = _re.search(r'(-?)\$([0-9,]+(?:\.[0-9]+)?)', (txt or '').replace('+', ''))
        return None if not m else (-1 if m.group(1) else 1) * float(m.group(2).replace(',', ''))

    def _sum_net(rows):
        return sum((t.get('pnl_usd') or 0) * _w(t) for t in rows)

    # -- STEP 6: the four shared tiles, equal to the recomputation, drawdown positive; the old ten-cell grid is gone
    STAT_CASES = {'paper2': ('ALL', ()), 'other-open': ('ALL', ()), 'other-on': ('ALL', ()), 'fwd-closed': ('ALL', ()),
                  'warn-stale-bridge': ('ALL', ()), 'book-fallback': ('ALL', ()), 'stats-open': ('ALL', ()),
                  'cal-closed': ('ALL', ()), 'cal-aug': ('ALL', ()), 'retired-open': ('ALL', ()), 'phone375': ('ALL', ()),
                  'legs-off-p2': ('ALL', ('ORB',)), 'range-today': ('TODAY', ()), 'range-1w': ('1W', ()),
                  'range-1m': ('1M', ()), 'range-3m': ('3M', ()), 'range-ytd': ('YTD', ()), 'range-saved': ('1M', ())}
    for nm, (rng, excl) in STAT_CASES.items():
        r = cases.get(nm) or {}
        exp = _stats_of(_rows_for(rng, excl))
        want = _tiles_of(exp)
        tiles = r.get('statTiles') or []
        if [x.get('k') for x in tiles] != ['winrate', 'pf', 'maxdd', 'trades']:
            fails.append('%s: the stats strip reads %s, expected the four tiles win rate, profit factor, max drawdown, '
                         'trades in that order' % (nm, [x.get('k') for x in tiles]))
            continue
        got = dict((x['k'], x['v']) for x in tiles)
        for k in ('winrate', 'pf', 'trades'):
            if got[k] != want[k]:
                fails.append('%s: the %s tile reads %r, the fixture says %r' % (nm, k, got[k], want[k]))
        dd = got['maxdd'] or ''
        if exp is None:
            if dd != '--':
                fails.append('%s: max drawdown reads %r for a range with no counted trade (expected --)' % (nm, dd))
        elif not _re.match(r'^\$[0-9,]+\.[0-9]{2}$', dd) or abs(_money_in(dd) - exp['dd']) > 0.006:
            fails.append('%s: max drawdown reads %r, expected the POSITIVE amount %s from the fixture' % (nm, dd, want['maxdd']))
        if r.get('oldStatCells'):
            fails.append('%s: the old ten-cell stats grid is still on the board' % nm)
        if exp is not None:
            sub = dict((x['k'], x.get('sub') or '') for x in tiles)
            if '%d W' % exp['wins'] not in sub['winrate'] or '%d L' % exp['losses'] not in sub['winrate']:
                fails.append('%s: the win rate tile says %r, expected %d W and %d L' % (nm, sub['winrate'], exp['wins'], exp['losses']))
            if sub['trades'] != 'over %d day%s' % (exp['days'], '' if exp['days'] == 1 else 's'):
                fails.append('%s: the trades tile says %r, expected %d trading day(s)' % (nm, sub['trades'], exp['days']))

    I = (cases.get('paper2') or {}).get('int') or {}
    if I.get('err') or not I:
        fails.append('paper2: the in-page interaction probe did not run: %s' % (I.get('err') or 'no readout'))
        I = {}
    exp_all = _stats_of(_rows_for('ALL'))
    mo = I.get('more') or {}
    if mo.get('start') != 'false' or mo.get('open') != 'true':
        fails.append('paper2: More stats should start closed and open on a tap (start %r, after the tap %r)' % (mo.get('start'), mo.get('open')))
    if mo.get('groups') != ['Returns', 'Risk', 'Mix', 'Strategy vs control']:
        fails.append('paper2: More stats opened with groups %r, not Returns, Risk, Mix, Strategy vs control' % mo.get('groups'))
    if mo.get('stored') != '1' or mo.get('closed') != 'false' or mo.get('storedClosed') != '0':
        fails.append('paper2: the More stats choice is not remembered per browser (stored %r / %r, aria %r)'
                     % (mo.get('stored'), mo.get('storedClosed'), mo.get('closed')))
    rowsd = dict((a, b) for a, b in (mo.get('rows') or []))
    if exp_all:
        # every value the old ten-cell grid showed lives in the fold now
        for label, want_v in (('Net P&L', exp_all['net']), ('Average trade', exp_all['avg']), ('Average win', exp_all['avgw']),
                              ('Average loss', exp_all['avgl']), ('Best day', exp_all['best']), ('Worst day', exp_all['worst']),
                              ('Max drawdown', exp_all['dd'])):
            got_v = _money_in(rowsd.get(label))
            if got_v is None or abs(got_v - want_v) > 0.006:
                fails.append('paper2: More stats %r reads %r, the fixture says %.2f' % (label, rowsd.get(label), want_v))
        if rowsd.get('Green days') != '%d of %d' % (exp_all['green'], exp_all['days']):
            fails.append('paper2: More stats Green days reads %r, expected %d of %d' % (rowsd.get('Green days'), exp_all['green'], exp_all['days']))
    vs_txt = mo.get('vsTxt') or ''
    if (mo.get('vsRows') or 0) < 3 or ' vs ' not in vs_txt or 'backfilled' not in vs_txt or not mo.get('vsCrown'):
        fails.append('paper2: "Strategy vs control" should list each traded strategy with its matched control, the dollar gap, the '
                     'crowns and the forward / backfilled split (rows %s, crown %s)' % (mo.get('vsRows'), mo.get('vsCrown')))
    if not mo.get('vsSubs') or not any('gate ' in s and 'refused' in s for s in mo.get('vsSubs')):
        fails.append('paper2: "Strategy vs control" lost the gate line of the gated strategies (%r)' % (mo.get('vsSubs') or [])[:2])
    if (cases.get('stats-open') or {}).get('moreFold') != 'true':
        fails.append('stats-open: a stored open More stats fold did not open on load')

    # -- STEP 7: the calendar. Month totals and counts equal the fixture; a day tap selects the rows that CLOSED that day
    allrows = _rows_for('ALL')
    months = sorted(set(_close(t)[:7] for t in allrows))

    def _month_info(mo_, rows=None):
        rows = [t for t in (allrows if rows is None else rows) if _close(t)[:7] == mo_]
        cav = set(_close(t) for t in rows if t.get('leg') == 'ORB' or t.get('roll_artifact')
                  or 'lookahead-engine' in (t.get('flags') or []))
        return {'n': len(rows), 'net': _sum_net(rows), 'days': sorted(set(_close(t) for t in rows)), 'cav': len(cav)}

    def _cal_sum(txt):
        m = _re.search(r'(\d+) trades?', txt or '')
        return _money_in(txt), (int(m.group(1)) if m else 0)

    def _cal_ok(tag, cal, mo_, rows=None):
        if not cal:
            fails.append('%s: the calendar is missing' % tag)
            return
        e = _month_info(mo_, rows)
        if cal.get('month') != mo_:
            fails.append('%s: the calendar shows %r, expected %s' % (tag, cal.get('month'), mo_))
            return
        net_g, n_g = _cal_sum(cal.get('sum'))
        if net_g is None or abs(net_g - e['net']) > 0.006 or n_g != e['n']:
            fails.append('%s: the month header reads %r, the fixture says %+.2f over %d trade(s)' % (tag, cal.get('sum'), e['net'], e['n']))
        if sorted(cal.get('days') or []) != e['days'] or sum(cal.get('dayN') or []) != e['n']:
            fails.append('%s: the calendar days %s (%s trades) are not the fixture days %s (%d trades)'
                         % (tag, cal.get('days'), sum(cal.get('dayN') or []), e['days'], e['n']))
        if (cal.get('cells') or 0) % 8 or not cal.get('cells'):
            fails.append('%s: the calendar grid has %s cells (rows of 7 days + a WEEK cell expected)' % (tag, cal.get('cells')))
        if cal.get('cav') != e['cav']:
            fails.append('%s: %s caveat day(s) hatched, expected %d (days with a roll-splice or ORB look-ahead trade)' % (tag, cal.get('cav'), e['cav']))

    def _tap_ok(tag, tap):
        if not tap or not tap.get('sel') or tap.get('sel') != tap.get('forDay') or tap.get('sel') != tap.get('cellN') \
                or set(tap.get('selDays') or []) != set([tap.get('day')]):
            fails.append('%s: tapping a calendar day selected %r - expected exactly the %s row(s) that closed on %s' % (tag, tap, (tap or {}).get('cellN'), (tap or {}).get('day')))

    if len(months) < 2:
        fails.append('the fixture should span two months for the calendar probe (got %s)' % months)
    else:
        _cal_ok('paper2 calendar', I.get('cal0'), months[-1])
        _tap_ok('paper2 calendar (newest month)', I.get('tap0'))
        _cal_ok('paper2 calendar (earlier month)', I.get('calPrev'), months[-2])
        _tap_ok('paper2 calendar (earlier month)', I.get('tap1'))
        _cal_ok('paper2 calendar (back to the newest month)', I.get('calBack'), months[-1])
        cp = I.get('calPrev') or {}
        if not cp.get('prevDis') or cp.get('nextDis'):
            fails.append('paper2: the month arrows should stop at the first month with trades (earlier disabled %r, later disabled %r)'
                         % (cp.get('prevDis'), cp.get('nextDis')))
        if I.get('calStored') != months[-2]:
            fails.append('paper2: the calendar month is not remembered per browser (stored %r, expected %s)' % (I.get('calStored'), months[-2]))
        _cal_ok('cal-aug (a remembered month)', (cases.get('cal-aug') or {}).get('cal'), months[-2])
    cf = I.get('calFold') or {}
    if (cases.get('paper2') or {}).get('calFold') != 'true' or cf.get('closed') != 'false' or not cf.get('hidden') \
            or cf.get('stored') != '0' or cf.get('reopen') != 'true':
        fails.append('paper2: the calendar fold should start open on a laptop, close (panel hidden, choice stored) and reopen: %r' % cf)
    r = cases.get('cal-closed') or {}
    if r.get('calFold') != 'false' or r.get('calPanelHidden') is not True:
        fails.append('cal-closed: a stored closed calendar fold opened anyway (aria %r, panel hidden %r)' % (r.get('calFold'), r.get('calPanelHidden')))
    # the caveat hatch exists on a day with an ORB look-ahead trade (the same mark the trade rows carry)
    if not (I.get('calPrev') or {}).get('cav'):
        fails.append('paper2: no calendar day is hatched amber although ORB look-ahead engine trades closed in the range')

    # -- STEP 10: the shared strategy list - groups in order, the BOOK total is the big number, one switch moves everything
    r = cases.get('paper2') or {}
    gs = r.get('groups') or []
    if [g.get('key') for g in gs] != ['book', 'fwd', 'other', 'retired']:
        fails.append('paper2: the strategy list groups read %s, expected BOOK, Forward tests & controls, Other / shadow, Retired'
                     % [g.get('key') for g in gs])
    else:
        byk = dict((g['key'], g) for g in gs)
        want_titles = {'book': 'BOOK #463', 'fwd': 'Forward tests & controls', 'other': 'Other / shadow - not counted', 'retired': 'Retired'}
        for k, ttl in want_titles.items():
            if not (byk[k].get('txt') or '').startswith(ttl):
                fails.append('paper2: the %s group is titled %r, expected %r' % (k, byk[k].get('txt'), ttl))
        if byk['book'].get('fold') or byk['book'].get('rows') != len(book_w):
            fails.append('paper2: the BOOK group should be open with one row per book leg (%d), got %s' % (len(book_w), byk['book']))
        if not byk['fwd'].get('fold') or byk['fwd'].get('open') != 'true' or not byk['fwd'].get('rows'):
            fails.append('paper2: the Forward tests & controls group should be a fold, open by default: %s' % byk['fwd'])
        for k in ('other', 'retired'):
            if not byk[k].get('fold') or byk[k].get('open') != 'false' or byk[k].get('rows'):
                fails.append('paper2: the %s group should be a fold, closed by default, drawing no rows: %s' % (k, byk[k]))
        retired_defs = sorted(k for k, d in defs.items() if d['archived'])
        ret_legs = ((cases.get('paper2') or {}).get('retHd') or {}).get('legs')
        if not retired_defs or ret_legs != len(retired_defs):
            fails.append('paper2: the Retired group counts %s strategies, the source declares %d archived' % (ret_legs, len(retired_defs)))
    rr = cases.get('retired-open') or {}
    rk = [x['key'] for x in (rr.get('listRowInfo') or []) if x.get('group') == 'retired']
    if sorted(rk) != sorted(k for k, d in defs.items() if d['archived']):
        fails.append('retired-open: the open Retired group lists %s, expected the archived strategies %s'
                     % (rk, sorted(k for k, d in defs.items() if d['archived'])))
    for nm in ('paper2', 'other-open', 'retired-open', 'legs-off-p2', 'phone375'):
        for row in (cases.get(nm) or {}).get('listRowInfo') or []:
            nm_txt = (row.get('name') or '').replace('\U0001F451', '').strip()
            if not _re.search(r'^[A-Z][A-Za-z-]*( [A-Z][A-Za-z-]*)* #\d+', nm_txt):
                fails.append('%s: the row %r is not named family + run number (%r)' % (nm, row.get('key'), nm_txt))
            if not row.get('dot'):
                fails.append('%s: the row %r has no live-state dot' % (nm, row.get('key')))
            if row.get('sw') not in ('true', 'false'):
                fails.append('%s: the row %r has no switch' % (nm, row.get('key')))
            if row.get('group') == 'book' and (row.get('sw') == 'false') != bool(row.get('off')):
                fails.append('%s: the BOOK row %r is faded %r with its switch %r' % (nm, row.get('key'), row.get('off'), row.get('sw')))
    r = cases.get('other-open') or {}
    if not any(x.get('name', '').startswith('ORB #257') for x in (r.get('listRowInfo') or [])):
        fails.append('other-open: the unlisted ORB 257 strategy is not named the family-name way (ORB #257): %s'
                     % [x.get('name') for x in (r.get('listRowInfo') or []) if x.get('group') == 'other'])
    r = cases.get('legs-off-p2') or {}
    offs = sorted(x['key'] for x in (r.get('listRowInfo') or []) if x.get('group') == 'book' and x.get('sw') == 'false')
    if offs != ['ORB']:
        fails.append('legs-off-p2: the switched-off BOOK legs read %s, expected [ORB]' % offs)
    if (cases.get('paper2') or {}).get('sideSticky') != 'sticky':
        fails.append('paper2: the strategy list column is not sticky on a laptop (%r)' % (cases.get('paper2') or {}).get('sideSticky'))
    # one flip, everything moves: hero, chart end, tiles, BOOK total, calendar, list and trade list (recomputed, then restored)
    f0, f1, f2 = I.get('flip0') or {}, I.get('flip1') or {}, I.get('flip2') or {}
    orb = [t for t in allrows if t.get('leg') == 'ORB']
    orb_net = _sum_net(orb)
    if not f0 or not f1 or not f2 or not orb or abs(orb_net) < 0.01:
        fails.append('paper2: the switch probe did not run (the fixture needs ORB trades with money in the range)')
    else:
        e1 = _stats_of(_rows_for('ALL', ('ORB',)))
        if abs(f1['hero'] - (f0['hero'] - orb_net)) > 0.01:
            fails.append('paper2: switching ORB off moved the big number %.2f to %.2f, expected %.2f' % (f0['hero'], f1['hero'], f0['hero'] - orb_net))
        if abs((f1.get('chartLast') or 0) - f1['hero']) > 0.01 or abs((f1.get('bookNet') or 0) - f1['hero']) > 0.01:
            fails.append('paper2: after the flip the chart end %s / BOOK group total %s are not the big number %s' % (f1.get('chartLast'), f1.get('bookNet'), f1['hero']))
        if f1.get('tiles') != _tiles_of(e1):
            fails.append('paper2: after the flip the tiles read %s, the fixture says %s' % (f1.get('tiles'), _tiles_of(e1)))
        if f1.get('bookN') != f0.get('bookN') - len(orb) or f1.get('tradeRows') != f0.get('tradeRows') - len(orb):
            fails.append('paper2: after the flip the list counts %s trades and the trade list %s rows, expected %d and %d fewer by %d'
                         % (f1.get('bookN'), f1.get('tradeRows'), f0.get('bookN') - len(orb), f0.get('tradeRows') - len(orb), len(orb)))
        mo_ = months[-2] if len(months) > 1 else None
        if mo_ and f0.get('cal', {}).get('month') == mo_:
            _cal_ok('paper2 calendar before the flip', f0.get('cal'), mo_)
            _cal_ok('paper2 calendar after the flip', f1.get('cal'), mo_, _rows_for('ALL', ('ORB',)))
        if 'ORB=true' not in (f0.get('sw') or '') or 'ORB=false' not in (f1.get('sw') or ''):
            fails.append('paper2: the ORB switch did not change state (%r then %r)' % ('ORB=true' in (f0.get('sw') or ''), 'ORB=false' in (f1.get('sw') or '')))
        for k in ('hero', 'chartLast', 'tiles', 'tradeRows', 'sw', 'bookN'):
            if f2.get(k) != f0.get(k) and not (isinstance(f0.get(k), float) and abs(f2.get(k) - f0.get(k)) < 0.01):
                fails.append('paper2: flipping ORB back did not restore %s (%r then %r)' % (k, f0.get(k), f2.get(k)))
        rt = I.get('rowTap') or {}
        if abs((rt.get('hero') or 0) - f1['hero']) > 0.01 or 'ORB=false' not in (rt.get('sw') or ''):
            fails.append('paper2: tapping the ORB row did not do what its switch does (big number %s, expected %s)' % (rt.get('hero'), f1['hero']))
        # a strategy outside the book: its switch lists its trades and never moves a counted figure
        o1, o2 = I.get('oth1') or {}, I.get('oth2') or {}
        nh = [t for t in fixture['trades'] if t.get('leg') == 'NOISE_H' and t.get('open') is not True]
        if not o1 or not nh:
            fails.append('paper2: the not-counted switch probe did not run')
        else:
            same = ('hero', 'chartLast', 'tiles', 'bookNet', 'bookN')
            if any(o1.get(k) != f0.get(k) for k in same):
                fails.append('paper2: a not-counted strategy switch moved a counted figure: %s' % [(k, f0.get(k), o1.get(k)) for k in same if o1.get(k) != f0.get(k)])
            if o1.get('tradeRows') != f0.get('tradeRows') + len(nh) or 'NOISE_H=true' not in (o1.get('sw') or ''):
                fails.append('paper2: switching NOISE #225 tree HYBRID on listed %s trade rows, expected %d more than %s'
                             % (o1.get('tradeRows'), len(nh), f0.get('tradeRows')))
            if o2.get('tradeRows') != f0.get('tradeRows') or 'NOISE_H=false' not in (o2.get('sw') or ''):
                fails.append('paper2: switching the not-counted strategy off again did not restore the trade list')

    # -- PHONE 375 x 812: trade list within one screen, the list below it, one line a row, folds closed, no sideways scroll
    r = cases.get('phone375') or {}
    g = r.get('geo') or {}
    if g.get('vw') != 375:
        fails.append('phone375: the phone frame is %s px wide, not 375' % g.get('vw'))
    if (g.get('scrollW') or 0) > (g.get('clientW') or 0) + 1:
        fails.append('phone375: the page scrolls sideways (scrollWidth %s > clientWidth %s)' % (g.get('scrollW'), g.get('clientW')))
    if not g.get('tradesTop') or g.get('boardTop') is None:
        fails.append('phone375: could not locate the trade list or the board top (%s)' % g)
    else:
        dist = g['tradesTop'] - g['boardTop']
        if dist > (g.get('vh') or 0):
            fails.append('phone375: the trade list starts %d px below the board top, more than one screen (%s px) - LEDGER mistake #12'
                         % (dist, g.get('vh')))
        if not g.get('listTop') or g['listTop'] <= g['tradesTop']:
            fails.append('phone375: the strategy list (top %s) is not below the trade list (top %s)' % (g.get('listTop'), g['tradesTop']))
        for key in ('moreTop', 'calTop'):
            if not g.get(key) or g[key] <= g['tradesTop']:
                fails.append('phone375: the %s fold sits above the trade list on a phone (%s <= %s)' % (key[:-3], g.get(key), g['tradesTop']))
    rh = [x.get('h') or 0 for x in (r.get('listRowInfo') or [])]
    if not rh or max(rh) > 48:
        fails.append('phone375: strategy rows are up to %s px tall - one line per row expected (48 or less)' % (max(rh) if rh else None))
    tt = [x.get('top') for x in (r.get('statTiles') or [])]
    if len(tt) != 4 or not (tt[0] == tt[1] and tt[2] == tt[3] and tt[2] > tt[0]):
        fails.append('phone375: the four stat tiles should sit two by two (tops %s)' % tt)
    if r.get('calFold') != 'false' or r.get('moreFold') != 'false':
        fails.append('phone375: the calendar / More stats folds should start closed on a phone (%r / %r)' % (r.get('calFold'), r.get('moreFold')))
    c = r.get('chart') or {}
    if (c.get('h') or 0) < 150:
        fails.append('phone375: the chart is %s px tall on a phone, expected at least 150' % c.get('h'))
    if r.get('pills') != ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']:
        fails.append('phone375: the pill row reads %s' % r.get('pills'))

    # -- ?oldboards=1 keeps the previous layout for one more version
    r = cases.get('oldboards-paper2') or {}
    if r.get('oldStatCells') != 10 or r.get('statTiles') or r.get('groups'):
        fails.append('oldboards-paper2: ?oldboards=1 should keep the old ten-cell grid, no shared tiles and no shared list (cells %s, tiles %s, groups %s)'
                     % (r.get('oldStatCells'), len(r.get('statTiles') or []), len(r.get('groups') or [])))
    if not r.get('oldHero') or not r.get('calDays') or sorted(r.get('bookRowKeys') or []) != sorted(book_w) \
            or ((r.get('listed') or {}).get('tie') != '1'):
        fails.append('oldboards-paper2: the previous layout lost its hero, calendar, LEGS table or tie-out line (hero %s, calendar days %s, book rows %s, tie %s)'
                     % (r.get('oldHero'), r.get('calDays'), r.get('bookRowKeys'), (r.get('listed') or {}).get('tie')))

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

    # the new layout has a strategy list (shared ledgerListHtml rows) where the LEGS table was; ?oldboards=1 still draws the table
    print('PAPERPROBE: PASS (VERSION=%s, %d cases, strategy list %s rows, ?oldboards=1 LEGS table %s cols, %s trade rows)'
          % (data.get('VERSION'), len(cases), len((cases.get('base') or {}).get('listRowInfo') or []),
             (cases.get('oldboards-paper2') or {}).get('legHead'),
             (cases.get('base') or {}).get('tradeRows')))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
