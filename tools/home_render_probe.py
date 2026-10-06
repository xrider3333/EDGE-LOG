#!/usr/bin/env python3
"""
tools/home_render_probe.py -- render gate for HOME > REAL (the trading log's landing view).

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS, and the other render probes prove STUDIES,
PAPER, the run report, COMPARE beta and the importer draw. None of them ever opens HOME, which
is the view the owner lands on every time, on a laptop and on a phone. HOME grew a lot in
v73.96x-v73.97x (SHOULD HAVE TRADED list and form, the paste box, EL's own chart in the trade
panel with pan / zoom, the POINTS block) and every one of those paths could throw behind a green
boot gate.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe exactly as the boot gate does, waits
for the signed-out screen and keeps it off the page, then seeds HOME's globals the way the
Firestore listeners would: seven synthetic trades (six futures MNQ / MES on 1m, 10s, 5m and
"10s, 1m" with ps1.1 point scores - full, partial, all-NA and none - plus one stock trade) and,
per case, zero or two SHOULD HAVE TRADED entries. Nothing touches the network: the trade-bars
reader is fed through its own test hook (window._rtBarsSource) with synthetic packed bars in the
api/trade_bars.py _pack shape, and window._missedRef / colRef are in-memory stubs that only record
writes. requestAnimationFrame is replaced with a 0 ms timer, since a headless page may never run
animation frames.

Every case is its own fresh render (all HOME state reset, then renderApp()):
  viewport  laptop 1366x768 | phone 375x812        (the iframe IS the viewport)
  theme     glass (the owner's dark theme) | paper (light), via prefs.theme + applyTheme()
  missed    no entries | two (an MNQ entry with a point score, a stock entry)
  ledger    TABLE + SIMPLE | TABLE + FULL | FEED
= 24 cases. Then two interaction runs, one laptop (glass) and one phone (paper).

WHAT IT ASSERTS
---------------
Per case:
  * renderApp returned, and no uncaught exception, unhandled rejection or console.error
  * window._loadError never fired and no LOAD ERROR overlay is on the page
  * #hm-missed exists, with one row per SHOULD HAVE TRADED entry
  * the ledger exists with one row per seeded trade (SIMPLE / FULL table, or the feed)
  * on a phone the page does not scroll sideways (scrollWidth <= clientWidth + 1)
  * LEDGER step 8, the shared trade list frame ([data-lglist-frame="hm"]): exactly one frame, in the right mode
    (list / table), the chips ALL LONG SHORT WINS LOSSES FUTURES STOCKS, the LIST | TABLE toggle with the right half
    pressed, a search box, a count, one day header [data-lgday] per CLOSE day with a signed net that adds up to the
    trades' own P&L (an overnight trade sits under the day it closed), one row per trade, the PASTE box, and on a
    phone five cells per row with the list starting within ONE screen of the top of the board (mistake #12)
  * rows come out newest close first, a deposit sits in its day under BY TRADE, the AI ASSESSMENT is a closed fold, the
    account list is one line on a phone (a list on a laptop), and the SIMPLE table fits its box with no sideways scroll
  * the legacy TRADES and JOURNAL tabs (?oldtabs=1) draw on a phone without scrolling the page sideways (mistake #14)
  * ?oldboards=1 (a second page load) still draws the previous list: its own FEED / TABLE button and chips, no frame
Per interaction run:
  * a futures trade's panel opens, its chart body ends up holding an <svg> and the info line
    is filled in (the chart really drew), and the POINTS block shows the trade's score
  * the chart's - (zoom out) and DAY buttons redraw it without an error
  * a SHOULD HAVE TRADED panel opens with its symbol, POINTS block and chart
  * + ADD opens the form, SAVE with the fields empty shows a message and writes nothing
  * hmFileChartLink(<a TradingView link>) shows the paste note with its SHOULD HAVE TRADED
    button, and that button opens the form with the link filled in
  * nothing was written to the trades or missed_trades stubs
  * the shared frame: each chip lists the right trades (a $0 trade is neither a WINS nor a LOSSES row), the search
    box filters and keeps the cursor, LIST | TABLE is remembered, BY DAY shows one row per day, SIMPLE | FULL
    switches the table; a grade and a note edited in the TABLE reach the database stubs and every row keeps its
    EDIT (opens the edit window) and DELETE cells; the ANALYTICS calendar
    jump (gotoTradesByDate) opens the LEDGER table on that day and flashes its rows; the LEDGER calendar day tap
    flashes that day's header in the list and in the table; a TABLE header menu still sorts (no day headers once
    sorted by NET); the trade panel keeps EDIT / SNAPSHOT / OPEN IN TV / DELETE and edits the grade and the setup;
    the AI ASSESSMENT fold opens and fills

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks). A non-PASS
attempt is rendered once more before it blocks (as in report_render_probe.py); a retry that
passes is printed as a FLAKE line. --no-retry turns that off.

Usage:
  python tools/home_render_probe.py                # gates this repo's index.html
  python tools/home_render_probe.py --file X.html  # gates X as if it were index.html
  python tools/home_render_probe.py --selftest     # builds deliberately broken copies of the
                                                   # current index.html (MUTANTS below), asserts
                                                   # FAIL on each, then PASS on the real file

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import calendar
import http.server
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

VIEWPORTS = {'laptop': [1366, 768], 'phone': [375, 812], 'narrow': [1000, 768]}
THEMES = ['glass', 'paper']
LEDGERS = [('simple', 'table', 'simple'), ('full', 'table', 'full'), ('feed', 'feed', 'simple')]

LEDGER_RANGES = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']    # the shared range pills (LEDGER unify step 4)
CASES = []
for _vp in ('laptop', 'phone'):
    for _th in THEMES:
        for _mi in (0, 2):
            for _nm, _view, _led in LEDGERS:
                CASES.append(['%s/%s/missed%d/%s' % (_vp, _th, _mi, _nm),
                              {'vp': _vp, 'theme': _th, 'missed': _mi, 'view': _view, 'ledger': _led}])

# a narrower laptop window: the SIMPLE table (it fits its box with no sideways scroll) and the list
for _nm, _view, _led in (LEDGERS[0], LEDGERS[2]):
    CASES.append(['narrow/glass/missed0/%s' % _nm, {'vp': 'narrow', 'theme': 'glass', 'missed': 0, 'view': _view, 'ledger': _led}])
# LEDGER unify step 8 / mistake #14: the legacy TRADES and JOURNAL tabs (?oldtabs=1) on a phone
for _th in THEMES:
    for _tab in ('trades', 'journal'):
        CASES.append(['phone/%s/legacy-%s' % (_th, _tab),
                      {'vp': 'phone', 'theme': _th, 'kind': 'legacy', 'tab': _tab, 'missed': 0,
                       'view': 'feed', 'ledger': 'simple'}])
# the previous REAL list layout behind ?oldboards=1 (a second page load, see _attempt)
OLD_CASES = [['old/%s/%s' % (_vp, _nm), {'vp': _vp, 'theme': 'glass', 'missed': 0, 'view': _view, 'ledger': _led}]
             for _vp in ('laptop', 'phone') for _nm, _view, _led in (LEDGERS[0], LEDGERS[2])]
FRAME_CHIPS = 'ALL,LONG,SHORT,WINS,LOSSES,FUTURES,STOCKS'
JUMP_DAY = '2026-09-30'

PASTE_URL = 'https://www.tradingview.com/x/TEST1/'

# Two interaction runs. `tid` is the futures trade whose panel is opened (a 1m trade on the
# laptop, a 10s trade on the phone, so both bar sizes the reader serves are drawn).
INTERACTIONS = [
    ['laptop', {'vp': 'laptop', 'theme': 'glass', 'view': 'table', 'ledger': 'simple',
                'tid': 'probe_t1', 'pts': '7/8', 'mid': 'probe_m1', 'msym': 'MNQ', 'mpts': '5/9',
                'jumpday': JUMP_DAY}],
    ['phone', {'vp': 'phone', 'theme': 'paper', 'view': 'feed', 'ledger': 'simple',
               'tid': 'probe_t3', 'pts': '6/9', 'mid': 'probe_m1', 'msym': 'MNQ', 'mpts': '5/9',
               'jumpday': JUMP_DAY}],
]

# Builds this gate must catch, made from the CURRENT index.html by one string replacement each
# (so they never go stale the way a pinned old commit would). (name, anchor, replacement, why)
MUTANTS = [
    ('missed-section-throws',
     'function _hmMissedSectionHtml(){',
     'function _hmMissedSectionHtml(){_hmProbeNoSuchHelper();',
     'the SHOULD HAVE TRADED section builder throws a ReferenceError - HOME does not draw at all'),
    ('missed-row-dropped',
     'const rows=list.map(m=>`<tr data-hmmissed=',
     'const rows=list.slice(1).map(m=>`<tr data-hmmissed=',
     'the SHOULD HAVE TRADED table silently drops an entry'),
    ('points-block-gone',
     '${_hmPtsSheetHtml(t)}',
     '',
     "the trade panel lost its POINTS block"),
    ('chart-reader-silent',
     'const doc=await window._rtBarsDoc(x._tid);if(!doc)return null;',
     'const doc=null;if(!doc)return null;',
     'the trade-bars reader returns nothing, so no trade panel ever draws a chart (no error thrown)'),
    ('zoom-out-throws',
     "if(z==='out')zoomAt(1.6,0.5);",
     "if(z==='out')zoomAt(1.6,0.5,_hmProbeNoSuchHelper());",
     'the chart\'s zoom-out button throws when clicked'),
    ('drawdown-negative',
     "tile('maxdd','Max drawdown',s?ledgerMoney(s.maxDD):'--'",
     "tile('maxdd','Max drawdown',s?ledgerMoney(-s.maxDD):'--'",
     'the shared stats strip prints max drawdown as a negative number again'),
    ('calendar-jump-lost',
     '<div class="lg-tl-day" data-lgday="\'+ds+\'">\'+dayHd(ds,ts)',
     '<div class="lg-tl-day">\'+dayHd(ds,ts)',
     'the trade list lost its day markers, so a calendar day no longer jumps the list there'),
    ('legend-swatch-giant',
     '.lg-chart .lg-legend svg{display:inline-block;width:16px;height:4px;flex:none}',
     '.lg-chart .lg-legend svg{display:block;width:100%;height:260px}',
     'a chart-size rule reaches the legend swatches again, so each legend name is a block the height of the chart'),
    ('closed-panel-takes-room',
     '.hm-sheet.open{display:block;animation:hmSheetIn .22s ease}',
     '.hm-sheet.open{display:block;animation:hmSheetIn .22s ease}.hm-sheet:not(.open){display:block;transform:translateX(100%)}',
     'the closed trade panel is parked off-screen again and makes the page scroll sideways'),
    ('account-row-dead',
     "if(k!==(activeBroker||''))setBroker(k);",
     "if(k===null)setBroker(k);",
     'tapping an account row in the list no longer scopes the board'),
    ('phone-overflow',
     'content.innerHTML=`<div class="hm-wrap${LEDGER_OLDBOARDS?\'\':\' lg-flow\'}">',
     'content.innerHTML=`<div class="hm-wrap${LEDGER_OLDBOARDS?\'\':\' lg-flow\'}" style="min-width:640px">',
     'HOME is wider than a phone and the page scrolls sideways'),
    # LEDGER step 8: the shared trade list frame
    ('frame-day-net-unsigned',
     "+(n?'<span class=\"lg-tl-daymeta\">'+n+' trade'+(n===1?'':'s')+'</span><span class=\"lg-tl-daynet '+ledgerPnlCls(net)+'\">'+ledgerSigned(net)+'</span>':'')",
     "+(n?'<span class=\"lg-tl-daymeta\">'+n+' trade'+(n===1?'':'s')+'</span><span class=\"lg-tl-daynet '+ledgerPnlCls(net)+'\">'+ledgerMoney(net)+'</span>':'')",
     'a day header prints its net without a sign, so MONO cannot tell a good day from a bad one'),
    ('wins-chip-counts-flat',
     "if(chip==='WINS')return p>0;",
     "if(chip==='WINS')return p>=0;",
     'the WINS chip lists a $0 trade as a win'),
    ('phone-six-cells',
     'const LEDGER_TL_PHONE={time:1,sym:1,side:1,pnl:1,chart:1};',
     'const LEDGER_TL_PHONE={time:1,sym:1,side:1,size:1,pnl:1,chart:1};',
     'a phone row keeps six cells instead of five'),
    ('view-not-remembered',
     "function ledgerTradeViewSet(id,v){try{localStorage.setItem('el_lg_view_'+id,v==='table'?'table':'list');}catch(e){}}",
     "function ledgerTradeViewSet(id,v){try{}catch(e){}}",
     'LIST | TABLE is no longer remembered per board'),
    ('list-below-the-fold',
     "'<div id=\"hm-feed-container\">'+_hmFrameHtml(list)+'</div>'",
     "'<div style=\"height:900px\"></div><div id=\"hm-feed-container\">'+_hmFrameHtml(list)+'</div>'",
     'something tall sits above the trade list, so it starts more than a screen down on a phone (mistake #12)'),
    ('ai-box-open-by-default',
     "homeAiOpen=localStorage.getItem('el_lg_ai_real')==='1'",
     "homeAiOpen=localStorage.getItem('el_lg_ai_real')!=='0'",
     'the AI ASSESSMENT box is open again and fills the top of the page'),
    ('grade-edit-lost',
     'const field=sel.dataset.hmfield,id=sel.dataset.hmid,val=sel.value;',
     "const field=sel.dataset.hmfield,id=sel.dataset.hmid,val=sel.value+'x';",
     'the inline grade select saves the wrong value'),
    ('table-edit-cell-dead',
     "td.onclick=(e)=>{e.stopPropagation();openEditModal(td.dataset.hmedit);};",
     "td.onclick=(e)=>{e.stopPropagation();};",
     'the pencil cell on a TABLE row no longer opens the edit window'),
    ('header-menu-dead',
     "    case 'pnl':return _hmThCell(label,'pnl',cls+' num',_hmThFRange('minPnl','maxPnl'));",
     "    case 'pnl':return null;",
     'the NET header lost its sort / filter menu'),
    ('paste-box-gone',
     '<input type="text" id="hm-paste-chart" class="hm-feed-search hm-paste"',
     '<input type="text" id="hm-paste-chart-gone" class="hm-feed-search hm-paste"',
     'the PASTE box for snapshot links is gone from the toolbar'),
    ('analytics-jump-dead',
     "activeTab='home';homeView='table';",
     "activeTab='home';",
     'a jump from the ANALYTICS calendar no longer opens the LEDGER table'),
    ('oldboards-ignored',
     '${LEDGER_OLDBOARDS?_hmOldListBlockHtml():_hmFrameBlockHtml(list)}',
     '${_hmFrameBlockHtml(list)}',
     '?oldboards=1 no longer brings back the previous list layout'),
    ('legacy-journal-wide',
     ';margin-bottom:8px;overflow-wrap:anywhere}',
     ';margin-bottom:8px}',
     'a long unbroken line in a journal entry widens the page on a phone again (mistake #14)'),
    ('legacy-trades-wide',
     '@media(max-width:600px){#trd-tbl{min-width:0}',
     '@media(max-width:0px){#trd-tbl{min-width:0}',
     'the legacy TRADES table keeps its 24 columns on a phone (mistake #14)'),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>home probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html__QS__" style="width:1366px;height:768px;border:0;display:block"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__, INTER=__INTER__, VP=__VP__, DATA=__DATA__, BARS=__BARS__, PASTE=__PASTE__;
(function(){
  var out={cases:{},inter:{},notes:[]}, reported=false, t0=Date.now(), sink=null;
  function finish(why){
    if(reported)return; reported=true;
    out.why=why; out.ms=Date.now()-t0;
    document.getElementById('o').textContent='HOMEPROBE: '+JSON.stringify(out);
  }
  setTimeout(function(){finish('backstop');},52000);
  var fr=document.getElementById('f');
  function W(){return fr.contentWindow;}
  function D(){return fr.contentDocument;}
  function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  async function waitFor(fn,ms){
    var a=Date.now();
    while(Date.now()-a<ms){var v=false;try{v=fn();}catch(_e){} if(v)return true; await sleep(40);}
    try{return !!fn();}catch(_e2){return false;}
  }
  function hook(w){
    if(w.__probeSink)return w.__probeSink;
    var s=w.__probeSink={errors:[],uncaught:[],loadErr:[]};
    var orig=w.console.error;
    w.console.error=function(){
      var p=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];p.push(a&&a.stack?String(a.stack):String(a));}
      s.errors.push(p.join(' '));
      try{orig.apply(w.console,arguments);}catch(_){}
    };
    w.addEventListener('error',function(ev){
      if(/ResizeObserver loop/.test(String(ev&&ev.message||'')))return;   // a browser notice, as the app treats it
      s.uncaught.push(String(ev&&ev.message||ev)+(ev&&ev.error&&ev.error.stack?' :: '+ev.error.stack:''));});
    w.addEventListener('unhandledrejection',function(ev){
      var r=ev&&ev.reason;s.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    var le=w._loadError;
    w._loadError=function(err,stage){
      s.loadErr.push(String(err&&err.message||err)+' (stage '+stage+')');
      if(typeof le==='function')return le.apply(this,arguments);
    };
    return s;
  }
  function drain(){
    return {errors:sink.errors.splice(0).slice(0,12),uncaught:sink.uncaught.splice(0).slice(0,12),
            loadErr:sink.loadErr.splice(0).slice(0,12)};
  }
  function overlays(){
    var d=D(),n=0;
    [].slice.call(d.body.children).forEach(function(e){
      if(/^\\s*LOAD ERROR/.test(e.textContent||'')){n++;e.remove();}});
    return n;
  }
  async function setVp(name){
    var v=VP[name];
    fr.style.width=v[0]+'px';fr.style.height=v[1]+'px';
    await waitFor(function(){return W().innerWidth===v[0];},2000);
    await sleep(60);
  }
  function seed(cfg){
    return W().__probeSeed(JSON.stringify(cfg));
  }
  function offenders(d){
    // the outermost elements past the right edge; a fixed one is listed only when nothing in the
    // flow is (the closed trade panel is always parked off the right edge and is not the cause)
    var cw=d.documentElement.clientWidth,res=[],fix=[];
    var all=d.querySelectorAll('body *');
    for(var i=0;i<all.length&&res.length<4;i++){
      var e=all[i],r=e.getBoundingClientRect();
      if(r.width<=0||r.right<=cw+1)continue;
      var p=e.parentElement,pr=p?p.getBoundingClientRect():null;
      if(pr&&pr.right>cw+1)continue;
      var pos=d.defaultView.getComputedStyle(e).position;
      (pos==='fixed'?fix:res).push(e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(/\\s+/).join('.'):'')
               +' right='+Math.round(r.right)+(pos!=='static'?' ('+pos+')':''));
    }
    return res.length?res:fix.slice(0,3);
  }
  function sample(cfg){
    var d=D(),w=W(),r={};
    r.innerW=w.innerWidth;
    r.theme=d.documentElement.getAttribute('data-theme');
    r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
    if(cfg.kind==='legacy'){
      // LEDGER step 8 (mistake #14): the legacy TRADES / JOURNAL tabs on a phone must not scroll the page sideways
      r.legacy={tab:w.eval('activeTab'),table:!!d.getElementById('trd-tbl'),journalForm:!!d.getElementById('lt'),
        rows:d.querySelectorAll('#trd-tbl tbody tr.tr-row').length,lessons:d.querySelectorAll('.lesson-card').length};
      var tbl0=d.getElementById('trd-tbl'),box0=tbl0?tbl0.parentElement:null;
      r.legacy.boxScrollW=box0?box0.scrollWidth:null;r.legacy.boxClientW=box0?box0.clientWidth:null;
      r.scrollW=d.documentElement.scrollWidth;r.clientW=d.documentElement.clientWidth;
      if(r.scrollW>r.clientW+1)r.wide=offenders(d);
      r.overlay=overlays();
      return r;
    }
    // the escape hatch (?oldboards=1) draws the previous list: its own FEED / TABLE button and chips, no frame
    r.oldList={toggle:!!d.getElementById('hm-view-toggle'),chips:d.querySelectorAll('[data-hmchip]').length,
      frames:d.querySelectorAll('[data-lglist-frame]').length};
    // LEDGER shared trade list frame (unify step 8): toolbar, day headers with a signed net, rows, five cells on a phone.
    // Measured first, before the folds below are opened and move the page about.
    var fr=d.querySelector('[data-lglist-frame="hm"]');
    r.frameN=d.querySelectorAll('[data-lglist-frame]').length;
    r.frame=!!fr;
    function dayOf(row){var g=row.closest('[data-lgday]');if(g)return g.getAttribute('data-lgday');
      var p=row.previousElementSibling;while(p){if(p.hasAttribute&&p.hasAttribute('data-lgday'))return p.getAttribute('data-lgday');p=p.previousElementSibling;}
      return null;}
    if(fr){
      var txt1=function(e){return e?(e.textContent||'').replace(/\\s+/g,' ').trim():'';};
      r.mode=fr.getAttribute('data-lgmode');
      r.chipTxt=Array.prototype.map.call(fr.querySelectorAll('[data-lgchip]'),txt1).join(',');
      r.chipOn=Array.prototype.map.call(fr.querySelectorAll('[data-lgchip].active'),txt1).join(',');
      r.viewBtns=Array.prototype.map.call(fr.querySelectorAll('[data-lgview]'),function(b){return b.getAttribute('data-lgview')+(b.getAttribute('aria-pressed')==='true'?'*':'');}).join(',');
      r.searchBox=!!fr.querySelector('input[data-lgsearch]');
      r.count=txt1(fr.querySelector('[data-lgcount]'));
      r.days=Array.prototype.map.call(fr.querySelectorAll('[data-lgday]'),function(g){return g.getAttribute('data-lgday')+'='+txt1(g.querySelector('.lg-tl-daynet'));});
      r.frameRows=fr.querySelectorAll('[data-lgtrade]').length;
      var ov=fr.querySelector('[data-lgtrade="probe_o1"]');r.ovDay=ov?dayOf(ov):null;
      var row1=fr.querySelector('[data-lgtrade]'),vis=0;
      if(row1)Array.prototype.forEach.call(row1.children,function(c){if(w.getComputedStyle(c).display!=='none')vis++;});
      r.visCells=vis;
      var wrapEl=d.querySelector('.hm-wrap'),fb=fr.getBoundingClientRect(),wb=wrapEl?wrapEl.getBoundingClientRect():null;
      r.listTop=wb?Math.round(fb.top-wb.top):null;
      r.rowTop=(wb&&row1)?Math.round(row1.getBoundingClientRect().top-wb.top):null;
      r.viewH=w.innerHeight;
    }
    var wrap0=d.querySelector('.hm-wrap'),wb0=wrap0?wrap0.getBoundingClientRect():null,fh0=d.querySelector('.hm-feed-head'),fc0=d.getElementById('hm-feed-container');
    r.feedTop=(wb0&&fc0)?Math.round(fc0.getBoundingClientRect().top-wb0.top):null;
    r.activityTop=(wb0&&fh0)?Math.round(fh0.getBoundingClientRect().top-wb0.top):null;
    // the AI ASSESSMENT is a closed fold and the account list is one line on a phone (mistake #12)
    var aib=d.querySelector('[data-hmai-fold]');
    r.aiFold=aib?{closed:aib.getAttribute('aria-expanded')==='false',out:!!d.getElementById('overview-ai-output')}:null;
    var acb=d.querySelector('[data-hmacct-fold]'),acl=d.querySelector('.hm-sec-acct .lg-list');
    r.acctFold=acb?{btn:w.getComputedStyle(acb).display,list:acl?w.getComputedStyle(acl).display:null}:null;
    // the frame's own table box must not scroll sideways (SIMPLE fits the row), rows in close order, the deposit row
    var tb2=d.querySelector('table.lg-tl-table'),bx2=tb2?tb2.parentElement:null;
    r.tblBox=bx2?{sw:bx2.scrollWidth,cw:bx2.clientWidth,simple:tb2.classList.contains('hm-simple')}:null;
    r.order=Array.prototype.map.call(d.querySelectorAll('[data-lglist-frame="hm"] [data-lgtrade]'),function(e){return e.getAttribute('data-lgtrade');});
    r.depositRows=d.querySelectorAll('[data-lglist-frame="hm"] .hm-row-static').length;
    var pb=d.getElementById('hm-paste-chart');r.paste=!!pb;r.pasteVisible=!!(pb&&pb.getBoundingClientRect().width>0);
    var ms=d.getElementById('hm-missed');
    r.missed=!!ms;
    r.missedRows=ms?ms.querySelectorAll('tr[data-hmmissed]').length:-1;
    var fc=d.getElementById('hm-feed-container');
    r.feed=!!fc;
    if(cfg.view==='table'){
      var tb=fc?fc.querySelector('table.hm-dtable'):null;
      r.ledgerKind=tb?(tb.classList.contains('hm-simple')?'simple':'full'):'';
      r.ledgerRows=tb?tb.querySelectorAll('tbody tr[data-hmid]').length:0;
    }else{
      // the previous FEED rows (?oldboards=1) or the shared frame's LIST rows
      r.ledgerKind=fc&&fc.querySelector('.hm-row[data-hmid],.lg-tl-row[data-lgtrade]')?'feed':'';
      r.ledgerRows=fc?fc.querySelectorAll('.hm-row[data-hmid],.lg-tl-row[data-lgtrade]').length:0;
    }
    // LEDGER shared hero + range pills (unify step 4): the big number, the today line, the six pills
    var hv=d.getElementById('hm-hero-value'),ht=d.getElementById('hm-hero-today');
    r.heroBig=hv?(hv.textContent||'').trim():null;
    r.heroToday=ht?(ht.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.pills=Array.prototype.map.call(d.querySelectorAll('#hm-feed-container ~ * [data-hmrange], .hm-range-row [data-hmrange]'),function(b){return b.getAttribute('data-hmrange');}).join(',');
    // LEDGER shared equity chart (unify step 5): real height on every width, dates and a price scale
    var csv=d.querySelector('#hm-chart-wrap svg');
    // the DRAWN height: a viewBox scaled down to fit a narrow box draws a short band in a tall box (the old phone bug)
    r.chartH=0;
    if(csv){var cr=csv.getBoundingClientRect(),vb=(csv.getAttribute('viewBox')||'').split(/[ ,]+/).map(Number);
      r.chartH=Math.round(vb.length===4&&vb[2]>0&&vb[3]>0?vb[3]*Math.min(cr.width/vb[2],cr.height/vb[3]):cr.height);}
    r.chartDates=csv?csv.querySelectorAll('[data-lgdate]').length:0;
    r.chartTicks=csv?csv.querySelectorAll('[data-lgtick]').length:0;
    // LEDGER shared stats strip (unify step 6): four tiles in order, drawdown positive, the More stats fold opens
    r.stats=Array.prototype.map.call(d.querySelectorAll('#hm-stat-strip [data-lgstat]'),function(e){
      var v=e.querySelector('.lg-stat-val');return e.getAttribute('data-lgstat')+'='+(v?(v.textContent||'').trim():'');});
    var mb=d.querySelector('[data-lgmore="hm"]');
    r.moreGroups='';
    if(mb){mb.click();
      r.moreGroups=Array.prototype.map.call(d.querySelectorAll('#hm-more [data-lgmsgroup]'),function(g){return g.getAttribute('data-lgmsgroup');}).join(',');
      var mb2=d.querySelector('[data-lgmore="hm"]');if(mb2)mb2.click();}
    // LEDGER shared calendar (unify step 7): the fold opens, the month's day counts add up to its header, and
    // tapping a day in the feed flashes that day's group
    var cf=d.querySelector('[data-lgcalfold="hm"]');
    r.cal=null;
    if(cf){var wasOpen=cf.getAttribute('aria-expanded')==='true';
      if(!wasOpen){cf.click();}
      var cg=d.querySelector('[data-lgcal="hm"].lg-cal'),c={days:0,sumN:0,hdN:null};
      if(cg){var ds=cg.querySelectorAll('[data-lgcalday]');c.days=ds.length;
        Array.prototype.forEach.call(ds,function(b){var n=b.querySelector('.n');c.sumN+=n?parseInt(n.textContent,10)||0:0;});
        var sm=(cg.querySelector('.lg-cal-sum')||{textContent:''}).textContent.match(/(\\d+) trades?/);c.hdN=sm?+sm[1]:0;
        c.cells=cg.querySelectorAll('.lg-cal-grid > *').length;
        if(ds.length&&(cfg.view!=='table'||r.frame)){var pick=ds[ds.length-1].getAttribute('data-lgcalday');ds[ds.length-1].click();
          var g=d.querySelector('#hm-feed-container [data-hmday="'+pick+'"],#hm-feed-container [data-lgday="'+pick+'"]');c.jump=!!(g&&g.classList.contains('lg-flash'));}}
      r.cal=c;
      if(!wasOpen){var cf2=d.querySelector('[data-lgcalfold="hm"]');if(cf2)cf2.click();}}
    // the legend under the chart (P&L view, two brokers): each name is one short line - a chart-size rule once
    // made every swatch 260px tall. Switch to P&L, measure, switch back.
    W().eval("homeChartMode='pnl';renderApp();");
    var lgb=d.querySelectorAll('#hm-chart-wrap .lg-legend button');r.legendN=lgb.length;
    r.legendH=Math.max.apply(null,[0].concat(Array.prototype.map.call(lgb,function(b){return Math.round(b.getBoundingClientRect().height);})));
    W().eval("homeChartMode='equity';renderApp();");
    // the CLOSED trade panel must take no room (parked off-screen it widened the page: LEDGER mistake #13)
    var shc=d.getElementById('hm-sheet');r.sheetClosed=shc&&!shc.classList.contains('open')?W().getComputedStyle(shc).display:'open';
    // LEDGER shared account list (unify step 10): ALL + one row per broker, the tab-row ACCOUNT pill gone on LEDGER,
    // and tapping a broker row scopes the board (the hero label names it), then ALL again
    var lr=d.querySelectorAll('[data-lglist="hm"] [data-lgrow]');r.acctRows=lr.length;
    r.acctSel=(d.querySelector('[data-lglist="hm"] [data-lgrow].sel')||{getAttribute:function(){return null;}}).getAttribute('data-lgrow');
    r.acctPill=Array.prototype.some.call(d.querySelectorAll('button'),function(b){return /setBroker\\(/.test(b.getAttribute('onclick')||'');});
    var nb=d.querySelector('[data-lglist="hm"] [data-lgrow="NinjaTrader"]');r.acctScoped=null;
    if(nb){nb.click();var hl=d.getElementById('hm-hero-label');r.acctScoped=hl?(hl.textContent||'').indexOf('NINJATRADER')>=0:false;
      var ab=d.querySelector('[data-lglist="hm"] [data-lgrow=""]');if(ab)ab.click();}
    r.scrollW=d.documentElement.scrollWidth;
    r.clientW=d.documentElement.clientWidth;
    if(r.scrollW>r.clientW+1)r.wide=offenders(d);
    r.overlay=overlays();
    return r;
  }
  async function runCase(nm,cfg){
    var r={};
    await setVp(cfg.vp);
    drain();
    try{r.call=seed(cfg);}catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);   // deferred work (hold check, chart wiring) gets to run, and to throw
    try{Object.assign(r,sample(cfg));}catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
    Object.assign(r,drain());
    out.cases[nm]=r;
  }
  function q(sel){return D().querySelector(sel);}
  function txt(sel){var e=q(sel);return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;}
  async function step(res,name,fn){
    var st={};
    try{await fn(st);}catch(e){st.threw=String(e&&e.stack?e.stack:e);}
    await sleep(60);
    Object.assign(st,drain());
    st.overlay=overlays();
    res.steps[name]=st;
  }
  async function interact(nm,I){
    var w=W(),res={steps:{}};
    await setVp(I.vp);
    drain();
    try{res.seed=seed({vp:I.vp,theme:I.theme,missed:2,view:I.view,ledger:I.ledger});}
    catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(150);
    Object.assign(res,{seedErr:drain()});
    // 1. a futures trade's panel: the chart draws and the POINTS block shows the score
    await step(res,'panel',async function(st){
      w.eval('homeSheetId='+JSON.stringify(I.tid)+';renderApp();');
      st.drew=await waitFor(function(){
        var b=q('#hm-sheet [data-rtcandlesbody]'),inf=q('#hm-sheet [data-rtcandlesinfo]');
        return b&&b.querySelector('svg')&&inf&&(inf.textContent||'').trim();},6000);
      st.open=!!q('#hm-sheet.open');
      st.body=txt('#hm-sheet [data-rtcandlesbody]');
      if(st.body&&st.body.length>160)st.body=st.body.slice(0,160);
      st.info=txt('#hm-sheet [data-rtcandlesinfo]');
      var s=q('#hm-sheet [data-rtcandlesbody] svg');st.svg0=s?s.outerHTML.length:0;
      res._svg0=s?s.outerHTML:'';
      st.points=txt('#hm-sheet .hm-sheet-points');
      if(st.points)st.points=st.points.slice(0,80);
    });
    // 2. zoom out, then DAY: each redraws (on a timer when frames do not run), neither throws
    await step(res,'zoom',async function(st){
      var o=q('#hm-sheet [data-rtz="out"]'),dy=q('#hm-sheet [data-rtz="day"]');
      st.buttons=(o?1:0)+(dy?1:0);
      if(o)o.click();
      await sleep(120);
      st.infoOut=txt('#hm-sheet [data-rtcandlesinfo]');
      if(dy)dy.click();
      await sleep(120);
      st.infoDay=txt('#hm-sheet [data-rtcandlesinfo]');
      var s=q('#hm-sheet [data-rtcandlesbody] svg');
      st.svg=!!s;
      st.redrew=!!(s&&res._svg0&&s.outerHTML!==res._svg0);
    });
    delete res._svg0;
    // 3. a SHOULD HAVE TRADED entry's panel
    await step(res,'missedPanel',async function(st){
      w.eval('homeSheetId='+JSON.stringify('missed:'+I.mid)+';renderApp();');
      st.drew=await waitFor(function(){
        var b=q('#hm-sheet [data-rtcandlesbody]');return b&&b.querySelector('svg');},6000);
      st.open=!!q('#hm-sheet.open');
      st.sym=txt('#hm-sheet .hm-sheet-sym');
      st.sub=txt('#hm-sheet .hm-sheet-sub');
      st.points=txt('#hm-sheet .hm-sheet-points');
      if(st.points)st.points=st.points.slice(0,80);
      st.body=txt('#hm-sheet [data-rtcandlesbody]');
      if(st.body&&st.body.length>160)st.body=st.body.slice(0,160);
    });
    // 4. + ADD opens the form; SAVE with the fields empty explains itself and writes nothing
    await step(res,'addForm',async function(st){
      w.eval('homeSheetId=null;renderApp();');
      await sleep(60);
      var add=q('#hm-missed-add');st.addBtn=!!add;
      if(add)add.click();
      await sleep(80);
      st.form=!!q('#hm-missed-form');
      st.msg0=txt('#hmmf-msg');
      var sv=q('#hmmf-save');st.saveBtn=!!sv;
      if(sv)sv.click();
      await sleep(120);
      st.form2=!!q('#hm-missed-form');
      st.msg=txt('#hmmf-msg');
      st.writes=JSON.parse(w.eval('JSON.stringify(window.__probeWrites)'));
    });
    // 5. a pasted TradingView link: the note asks where it goes and offers SHOULD HAVE TRADED,
    //    which opens the form with the link filled in
    await step(res,'paste',async function(st){
      w.eval('window._hmMissedEdit=null;renderApp();');
      await sleep(40);
      await w.hmFileChartLink(PASTE);
      await sleep(80);
      st.note=!!q('#hm-paste-msg');
      st.noteText=txt('#hm-paste-msg');
      if(st.noteText&&st.noteText.length>160)st.noteText=st.noteText.slice(0,160);
      var b=q('#hm-paste-msg #hm-paste-missed');st.missedBtn=!!b;
      if(b){b.click();await sleep(150);}
      st.form=!!q('#hm-missed-form');
      var u=q('#hmmf-url');st.url=u?u.value:null;
      st.writes=JSON.parse(w.eval('JSON.stringify(window.__probeWrites)'));
    });
    // 6. LEDGER step 8, the shared trade list frame: the chips (a $0 trade is neither a win nor a loss), the search
    //    box, BY DAY, LIST | TABLE (remembered per board) and SIMPLE | FULL
    await step(res,'frame',async function(st){
      function fr1(){return q('[data-lglist-frame="hm"]');}
      function ids(){var f=fr1();return f?Array.prototype.map.call(f.querySelectorAll('[data-lgtrade]'),function(e){return e.getAttribute('data-lgtrade');}).sort():null;}
      function mode(){var f=fr1();return f?f.getAttribute('data-lgmode'):null;}
      function ls(k){try{return w.localStorage.getItem(k);}catch(e){return 'ERR';}}
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeFeedMode="trade";homeView="feed";renderApp();');
      st.chips={};
      ['WINS','LOSSES','LONG','SHORT','FUTURES','STOCKS','ALL'].forEach(function(c){
        var b=q('[data-lgchip="'+c+'"]');if(b){b.click();st.chips[c]=ids();}else st.chips[c]=null;});
      var inp=q('#hm-search');st.searchBox=!!inp;
      if(inp){inp.focus();inp.value='aapl';inp.dispatchEvent(new Event('input',{bubbles:true}));}
      st.search=ids();
      st.searchFocus=(D().activeElement&&D().activeElement.id)||'';
      inp=q('#hm-search');
      if(inp){inp.value='';inp.dispatchEvent(new Event('input',{bubbles:true}));}
      st.searchCleared=(ids()||[]).length;
      var bd=q('[data-hmfeed="day"]');st.byDayBtn=!!bd;
      if(bd){bd.click();var f1=fr1();st.byDayDays=f1?f1.querySelectorAll('[data-lgday]').length:-1;st.byDayTrades=f1?f1.querySelectorAll('[data-lgtrade]').length:-1;}
      var bt=q('[data-hmfeed="trade"]');if(bt)bt.click();
      var tbn=q('[data-lgview="table"]');st.viewBtn=!!tbn;
      if(tbn)tbn.click();
      st.modeTable=mode();st.savedTable=ls('el_lg_view_hm');
      var fl=q('[data-hmledger="full"]');st.fullBtn=!!fl;
      if(fl){fl.click();var tf=q('table.lg-tl-table');st.fullTable=!!(tf&&!tf.classList.contains('hm-simple'));st.fullCols=tf?tf.querySelectorAll('thead th').length:0;}
      var sm=q('[data-hmledger="simple"]');if(sm)sm.click();
      var ts=q('table.lg-tl-table');st.simpleTable=!!(ts&&ts.classList.contains('hm-simple'));st.simpleCols=ts?ts.querySelectorAll('thead th').length:0;
      var lbn=q('[data-lgview="list"]');if(lbn)lbn.click();
      st.modeList=mode();st.savedList=ls('el_lg_view_hm');
      st.paste=!!q('#hm-paste-chart');
      st.buttons={add:!!q('#hm-add-deposit'),scan:!!q('#hm-scan-dupes'),all:!!q('#hm-open-all'),nt:!!q('#hm-newtrade-toggle')};
      // NEW TRADE opens the form under the toolbar and closes it again
      var nt=q('#hm-newtrade-toggle');
      if(nt){nt.click();st.formOpen=!!q('#hm-newtrade-form #hnfsym');var nt2=q('#hm-newtrade-toggle');if(nt2)nt2.click();st.formClosed=!q('#hm-newtrade-form #hnfsym');}
      // the ... button (a phone only) opens the four action buttons; a laptop always shows them
      var tt=q('#hm-tools-toggle'),ta=q('#hm-tools');
      st.tools={toggle:tt?w.getComputedStyle(tt).display:null,box:ta?w.getComputedStyle(ta).display:null};
      if(tt&&st.tools.toggle!=='none'){tt.click();var ta2=q('#hm-tools');st.tools.boxOpen=ta2?w.getComputedStyle(ta2).display:null;tt=q('#hm-tools-toggle');if(tt)tt.click();var ta3=q('#hm-tools');st.tools.boxShut=ta3?w.getComputedStyle(ta3).display:null;}
    });
    // 7. REAL keeps its inline edits: a grade and a note saved from the TABLE reach the database stubs
    await step(res,'edits',async function(st){
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeView="table";homeLedger="simple";renderApp();');
      await sleep(40);
      w.eval('window.__probeData.length=0;');
      var sel=q('select[data-hmfield="grade"][data-hmid="probe_t1"]');st.gradeSel=!!sel;
      if(sel){sel.value='A';sel.dispatchEvent(new Event('change',{bubbles:true}));await sleep(80);}
      var ni=q('input[data-field="notes"][data-id="probe_t1"]');st.noteInput=!!ni;
      if(ni){ni.value='probe note edit';ni.dispatchEvent(new Event('blur'));await sleep(80);}
      st.data=JSON.parse(w.eval('JSON.stringify(window.__probeData)'));
      // every row keeps its EDIT and DELETE cells: EDIT opens the edit window (closed again here), DELETE is wired (it asks first, so it is not clicked)
      st.rowsN=D().querySelectorAll('table.lg-tl-table tbody tr[data-lgtrade]').length;
      st.editCells=D().querySelectorAll('table.lg-tl-table td[data-hmedit]').length;
      st.delCells=D().querySelectorAll('table.lg-tl-table td[data-hmdel]').length;
      var dcell=q('table.lg-tl-table td[data-hmdel]');st.delWired=!!(dcell&&typeof dcell.onclick==='function');
      var ecell=q('table.lg-tl-table td[data-hmedit]');
      if(ecell){var mb0=D().querySelectorAll('.modal-bg[id^="em_"]').length;ecell.click();await sleep(60);var mb1=D().querySelectorAll('.modal-bg[id^="em_"]');st.editOpened=mb1.length-mb0;Array.prototype.forEach.call(mb1,function(m){m.remove();});}
    });
    // 8. jumps into the list: the ANALYTICS calendar (gotoTradesByDate) opens the LEDGER table on that day and flashes its
    //    rows; a LEDGER calendar day tap in the table flashes that day's header
    await step(res,'jump',async function(st){
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeView="feed";activeTab="analytics";renderApp();');
      await sleep(40);
      st.analyticsShown=w.eval('activeTab');
      w.gotoTradesByDate(I.jumpday);
      await sleep(160);
      st.tab=w.eval('activeTab');st.view=w.eval('homeView');
      st.flashed=D().querySelectorAll('#hm-feed-container tbody tr.hm-flash').length;
      st.dayHeader=!!q('[data-lglist-frame="hm"] [data-lgday="'+I.jumpday+'"]');
      st.tableShown=!!q('table.lg-tl-table');
    });
    // 9. the TABLE header menus still sort through the frame: NET opens its menu, Sort ascending re-orders the rows and the
    //    day headers go (rows are no longer in day order)
    await step(res,'sortmenu',async function(st){
      w.eval('homeSheetId=null;homeChip="ALL";homeQuery="";homeView="table";homeLedger="simple";sortCol="date";sortDir=-1;window._thMenu=null;renderApp();');
      await sleep(40);
      var th=q('table.lg-tl-table th[data-thcol="pnl"] .thh');st.header=!!th;
      if(th){th.click();await sleep(120);}
      var menu=D().getElementById('_thFloatMenu');st.menu=!!menu;
      var asc=menu?Array.prototype.filter.call(menu.querySelectorAll('div'),function(e){return /Sort ascending/.test(e.textContent||'');})[0]:null;
      st.ascItem=!!asc;
      if(asc){asc.click();await sleep(120);}
      st.label=txt('#hm-sort-label');
      st.nets=Array.prototype.map.call(D().querySelectorAll('table.lg-tl-table tbody tr[data-lgtrade] .lg-c-pnl'),function(c){return (c.textContent||'').trim();});
      st.dayRows=D().querySelectorAll('table.lg-tl-table tr[data-lgday]').length;
      w.eval('sortCol="date";sortDir=-1;window._thMenu=null;renderApp();');
    });
    // 10. the trade panel keeps EDIT / SNAPSHOT / OPEN IN TV / DELETE and also edits the grade and the setup (a phone row
    //     keeps five cells, the rest is edited here)
    await step(res,'sheet',async function(st){
      w.eval('window.__probeData.length=0;homeSheetId="probe_t2";renderApp();');
      await sleep(80);
      st.buttons={edit:!!q('#hm-sheet-edit'),snap:!!q('#hm-sheet-chart'),tv:!!q('#hm-sheet-tv'),del:!!q('#hm-sheet-del')};
      var gs=q('#hm-sheet select[data-hmsheetfield="grade"]'),ss=q('#hm-sheet select[data-hmsheetfield="setup"]');
      st.sel=!!gs&&!!ss;
      if(gs){gs.value='A';gs.dispatchEvent(new Event('change',{bubbles:true}));await sleep(60);}
      if(ss&&ss.options.length>1){ss.selectedIndex=1;st.setupPicked=ss.value;ss.dispatchEvent(new Event('change',{bubbles:true}));await sleep(60);}
      st.data=JSON.parse(w.eval('JSON.stringify(window.__probeData)'));
      w.eval('homeSheetId=null;renderApp();');
    });
    // 11. the AI ASSESSMENT fold: closed, then open (the box is drawn and filled), then closed again
    await step(res,'aiFold',async function(st){
      w.eval('homeSheetId=null;homeView="feed";renderApp();');
      var b=q('[data-hmai-fold]');st.fold=!!b;
      st.closed=b?b.getAttribute('aria-expanded')==='false':null;st.outputBefore=!!q('#overview-ai-output');
      if(b){b.click();await sleep(80);}
      var b2=q('[data-hmai-fold]');st.open=b2?b2.getAttribute('aria-expanded')==='true':null;
      st.outputAfter=!!q('#overview-ai-output');st.text=txt('#overview-ai-output');
      if(st.text&&st.text.length>120)st.text=st.text.slice(0,120);
      if(b2){b2.click();await sleep(40);}
      var b3=q('[data-hmai-fold]');st.closedAgain=b3?b3.getAttribute('aria-expanded')==='false':null;
    });
    try{w.eval('homeSheetId=null;window._hmMissedEdit=null;window._hmPasteNote=null;renderApp();');}catch(_e){}
    drain();
    out.inter[nm]=res;
  }
  fr.addEventListener('load',function(){
    setTimeout(async function(){
      var w=W();
      try{
        out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
        out.renderApp=typeof w.renderApp;
        sink=hook(w);
      }catch(e){out.err=String(e);finish('hookfail');return;}
      if(out.renderApp!=='function'){finish('noboot');return;}
      // Firebase auth settles with no user and paints the SIGN IN screen; wait for it, then make
      // renderAuth a no-op so a late callback cannot paint over a case (report probe, 2026-09-28).
      out.authSettled=await waitFor(function(){return !!D().getElementById('tsu');},12000);
      try{w.eval('renderAuth=function(){};');}catch(e){out.notes.push('renderAuth stub: '+e);}
      await sleep(200);
      out.bootNoise=drain();
      overlays();
      try{
        w.__probeDataJson=JSON.stringify(DATA);
        w.__probeBarsJson=JSON.stringify(BARS);
        w.eval(__INSTALL__);
      }catch(e){out.err='install failed: '+(e&&e.stack?e.stack:e);finish('installfail');return;}
      out.hidden=!!D().hidden;
      for(var i=0;i<CASES.length;i++)await runCase(CASES[i][0],CASES[i][1]);
      for(var j=0;j<INTER.length;j++){
        try{await interact(INTER[j][0],INTER[j][1]);}
        catch(e){out.inter[INTER[j][0]]={threw:String(e&&e.stack?e.stack:e)};}
      }
      out.barReads=w.__probeBarReads||0;
      finish('done');
    },2500);
  });
})();
</script>
</body></html>
"""

# Runs inside the app's own realm (indirect eval), so it can reach its top-level `let` bindings
# (trades, missedTrades, homeView, colRef, prefs ...), which are not window properties.
INSTALL_JS = r"""
(function(){
  window.__probeWrites=[];window.__probeData=[];
  function mkRef(name){
    var log=function(op){window.__probeWrites.push(name+'.'+op);return Promise.resolve();};
    var ref={
      add:function(){window.__probeWrites.push(name+'.add');return Promise.resolve({id:'probe_new'});},
      doc:function(id){return {
        update:function(d){window.__probeData.push({n:name,id:String(id),d:d});return log('update '+id);},
        set:function(){return log('set '+id);},
        delete:function(){return log('delete '+id);},
        get:function(){return Promise.resolve({exists:false,id:id,data:function(){return null;}});},
        onSnapshot:function(){return function(){};}};},
      where:function(){return ref;},orderBy:function(){return ref;},limit:function(){return ref;},
      get:function(){return Promise.resolve({docs:[],empty:true,size:0,forEach:function(){}});},
      onSnapshot:function(){return function(){};}
    };
    return ref;
  }
  window._missedRef=mkRef('missed_trades');
  colRef=mkRef('trades');
  var BARS=JSON.parse(window.__probeBarsJson);
  window._rtBarsSource=async function(tid){
    window.__probeBarReads=(window.__probeBarReads||0)+1;
    var d=BARS[String(tid)];return d?JSON.parse(JSON.stringify(d)):null;};
  // a headless page may never run animation frames; the chart's pan / zoom redraw waits on one
  window.requestAnimationFrame=function(cb){return setTimeout(function(){cb(performance.now());},0);};
  window.cancelAnimationFrame=function(h){clearTimeout(h);};
  window.__probeSeed=function(cj){
    var C=JSON.parse(cj),S=JSON.parse(window.__probeDataJson);
    prefs.theme=C.theme;applyTheme();
    trades=S.trades;missedTrades=C.missed?S.missed:[];
    ledgerEvents=S.ledger||[];lessons=S.lessons||[];
    // the legacy TRADES / JOURNAL tabs only draw behind ?oldtabs=1 (the app reads this flag on every render)
    window.LOG_OLDTABS_ESCAPE_HATCH=!!C.tab;window._lastLogTab=C.tab||undefined;
    activeTab=C.tab||'home';homeView=C.view;homeLedger=C.ledger;homeSheetId=null;
    homeRange='ALL';homeChip='ALL';homeQuery='';homeFeedMode='trade';homeChartMode='equity';
    homeStatsOpen=false;homeExtras=false;homeNewTradeOpen=false;
    window._hmMissedEdit=null;window._hmPasteNote=null;window._hmPasteLast=null;window._hmPasteAsk=null;
    window._thMenu=null;window._hmTblScrollL=0;window._hmTblScrollT=0;window._hmNote=null;
    window._hmJumpPrevView=null;window._hmSearchTyping=false;window._rtSheetTfFor={};
    try{localStorage.removeItem('el_paste_hold');}catch(e){}
    window.__probeWrites.length=0;
    try{window.scrollTo(0,0);}catch(e){}
    // Same tab as the last render, so no tab-switch fade: while .fade's transform animates, the
    // closed trade panel (position:fixed, parked off the right edge) is laid out inside the
    // animated wrapper and the page measures 720px wide on a phone for those 0.2s. That is a
    // transient of the tab switch, not of HOME, and only the first case would ever see it.
    window._lastRenderTab='home';
    renderApp();
    return 'OK';
  };
})();
"""


# ---------------------------------------------------------------- synthetic data

def _et_epoch(date, hms):
    """New York wall clock -> epoch seconds. Every probe date sits in late Sept / early Oct 2026,
    inside daylight time (EDT, UTC-4, until 2026-11-01), so a fixed offset is exact here."""
    y, m, d = (int(x) for x in date.split('-'))
    hh, mm, ss = (int(x) for x in (hms.split(':') + ['0'])[:3])
    return calendar.timegm((y, m, d, hh, mm, ss)) + 4 * 3600


def _q(px):
    return round(px * 4) / 4.0


def _pack(t0, step, n, px, rng):
    """The api/trade_bars.py _pack shape: 'off,o,h,l,c,v;...' with off = (bar start - t0) / step."""
    parts = []
    for i in range(n):
        o = _q(px)
        c = _q(px + rng.uniform(-3.0, 3.0))
        h = _q(max(o, c) + rng.uniform(0, 1.5))
        lo = _q(min(o, c) - rng.uniform(0, 1.5))
        parts.append('%d,%s,%s,%s,%s,%d' % (i, ('%.2f' % o).rstrip('0').rstrip('.'),
                                            ('%.2f' % h).rstrip('0').rstrip('.'),
                                            ('%.2f' % lo).rstrip('0').rstrip('.'),
                                            ('%.2f' % c).rstrip('0').rstrip('.'),
                                            rng.randint(40, 900)))
        px = c
    return {'t0': t0, 'step': step, 's': ';'.join(parts)}


def _bars_doc(date, t_in, t_out, px, with10s, seed, overnight=False):
    rng = random.Random(seed)
    e = _et_epoch(date, t_in)
    x = (_et_epoch(date, t_out) + (86400 if overnight else 0)) if t_out else None
    m0 = (e // 60) * 60 - 30 * 60
    last = (x if x else e) + 30 * 60
    n1 = (last - m0) // 60 + 1
    doc = {'v': 1, 'entry': {'t': e, 'px': px}, 'exit': ({'t': x, 'px': px + 5} if x else None),
           'b1m': dict(_pack(m0, 60, n1, px, rng), src='probe 1m', shift=0), 'complete': True}
    if with10s:
        s0 = (e // 10) * 10 - 600            # 60 bars before the entry: the trade view is a slice
        s_last = (x if x else e) + 600
        doc['b10s'] = dict(_pack(s0, 10, (s_last - s0) // 10 + 1, px, rng), src='probe 10s', shift=0)
    return doc


def _ps(date, t_in, hits, na=0, trend=True):
    """A ps1.1 point score: nine points, `hits` of them hit, `na` of them NA (never a 0)."""
    keys = [('ma200_10s', 'Above 200 EMA (10s)'), ('ma200_1m', 'Above 200 EMA (1m)'),
            ('ma200_5m', 'Above 200 EMA (5m)'), ('ma200_30m', 'Above 200 EMA (30m)'),
            ('y_low', "Above yesterday's low"), ('y_close', "Above yesterday's close"),
            ('y_high', "Above yesterday's high"), ('big_body', "Largest body since today's low"),
            ('big_vol', "Largest volume since today's low")]
    pts = []
    for i, (k, label) in enumerate(keys):
        if i < na:
            pts.append({'k': k, 'label': label, 'hit': None, 'val': None, 'ref': None,
                        'na_reason': 'no 10-second data'})
        else:
            pts.append({'k': k, 'label': label, 'hit': (i - na) < hits, 'val': 20012.25 + i,
                        'ref': 20001.5 + i, 'na_reason': None})
    hh, mm = (int(v) for v in t_in.split(':')[:2])
    sig = '%02d:%02d' % ((hh * 60 + mm - 1) // 60, (hh * 60 + mm - 1) % 60)
    rec = {'v': 'ps1.1', 'side': 'LONG', 'total': hits, 'max': 9 - na, 'na_count': na,
           'signal_bar': '%s %s:00' % (date, sig), 'fill': '%s %s' % (date, (t_in + ':00')[:8]),
           'tf': '1m', 'points': pts, 'src': 'probe', 'notes': []}
    if trend:
        rec['trend'] = {'k': 'd_trend', 'label': 'Daily trend up', 'hit': True, 'val': 5801.25,
                        'ref': 5760.0, 'na_reason': None}
    return rec


def build_data():
    T = []

    def tr(i, sym, side, date, t_in, t_out, tf, entry, exit_, size, mult, fees, **kw):
        d = 1 if side == 'LONG' else -1
        gross = round((exit_ - entry) * d * size * mult, 2)
        t = {'id': i, 'symbol': sym, 'type': side, 'date': date, 'entryTime': t_in, 'exitTime': t_out,
             'timeframe': tf, 'entry': entry, 'exit': exit_, 'size': size, 'grossPnl': gross, 'fees': fees,
             'pnl': round(gross - fees, 2), 'setup': 'CBU', 'grade': 'B', 'broker': 'NinjaTrader',
             'account': 'probe', 'notes': '', 'tags': [], 'source': 'probe', 'durationMins': 7}
        t.update(kw)
        T.append(t)

    tr('probe_t1', 'MNQ', 'LONG', '2026-09-30', '10:00:00', '10:07:00', '1m', 20000.25, 20012.5, 2, 2, 1.48,
       pointScore=_ps('2026-09-30', '10:00:00', 7, na=1),
       notes='probe trade with a note')
    tr('probe_t2', 'MNQ', 'SHORT', '2026-09-30', '11:15:00', '11:21:30', '10s, 1m', 20040.0, 20046.75, 1, 2,
       0.74, pointScore=_ps('2026-09-30', '11:15:00', 3, na=2), chartUrl='https://www.tradingview.com/x/PROBE0/')
    tr('probe_t3', 'MES', 'LONG', '2026-10-01', '09:45:10', '09:52:40', '10s', 5801.0, 5804.25, 3, 5, 2.22,
       pointScore=_ps('2026-10-01', '09:45:10', 6, na=0, trend=False))
    tr('probe_t4', 'MES', 'SHORT', '2026-09-29', '14:02:00', '14:30:00', '5m', 5790.5, 5786.0, 1, 5, 0.74,
       statsExcluded=True, grade='C')
    tr('probe_t5', 'MNQ', 'LONG', '2026-09-28', '09:31:00', '09:33:00', '1m', 19950.0, 19947.25, 1, 2, 0.74,
       pointScore=_ps('2026-09-28', '09:31:00', 0, na=9))
    tr('probe_t6', 'MNQ', 'SHORT', '2026-10-01', '13:05:00', '13:12:00', '1m', 20110.5, 20101.0, 1, 2, 0.74,
       pointScore=_ps('2026-10-01', '13:05:00', 5, na=1))
    tr('probe_s1', 'AAPL', 'LONG', '2026-09-30', '15:30:00', '15:55:00', '5m', 231.4, 232.1, 50, 1, 0.0,
       broker='Webull', setup='Breakout')
    # a flat trade (entry == exit, no fee): neither a win nor a loss - the WINS and LOSSES chips must leave it out
    tr('probe_z1', 'MNQ', 'LONG', '2026-09-29', '15:10:00', '15:15:00', '1m', 20000.0, 20000.0, 1, 2, 0.0,
       notes='a flat trade: neither a win nor a loss')
    # entered 09-30 at 23:55, held 25 minutes: it CLOSES on 10-01 (the New York day it belongs to)
    tr('probe_o1', 'MNQ', 'SHORT', '2026-09-30', '23:55:00', '00:20:00', '1m', 20050.0, 20044.5, 1, 2, 0.74,
       durationMins=25)
    T.sort(key=lambda t: (t['date'], t['entryTime']))

    missed = [
        {'id': 'probe_m1', 'url': 'https://www.tradingview.com/x/PROBEM1/', 'setup': 'CBU', 'symbol': 'MNQ',
         'date': '2026-09-30', 'entryTime': '10:30', 'type': 'LONG', 'entry': 20030.0, 'stop': 20015.0,
         'target': 20060.0, 'note': 'probe: saw it, did not take it', 'source': 'form',
         'pointScore': _ps('2026-09-30', '10:30', 5, na=0)},
        {'id': 'probe_m2', 'url': '', 'setup': 'Fade', 'symbol': 'TSLA', 'date': '2026-10-01',
         'entryTime': '14:10', 'type': 'SHORT', 'entry': None, 'stop': None, 'target': None, 'note': '',
         'source': 'paste'},
    ]

    bars = {}
    px = {'MNQ': 20000.0, 'MES': 5800.0}
    for i, t in enumerate(T):
        if t['symbol'] in px:
            bars[t['id']] = _bars_doc(t['date'], t['entryTime'], t['exitTime'], px[t['symbol']],
                                      True, 1000 + i, overnight=(t['id'] == 'probe_o1'))
    bars['missed_probe_m1'] = _bars_doc('2026-09-30', '10:30:00', None, 20030.0, True, 77)
    ledger = [{'date': '2026-09-29', 'amount': 1000.0, 'desc': 'probe deposit', 'broker': 'NinjaTrader'}]
    lessons = [{'id': 'probe_l1', 'title': 'Chased a breakout and overtraded the open', 'date': '2026-09-30',
                'tags': ['psychology', 'risk management', 'entries'],
                'body': 'Entered the first push without waiting for the pullback. ' * 6
                        + 'A_very_long_unbroken_word_that_has_no_spaces_in_it_at_all_' * 4}]
    return {'trades': T, 'missed': missed, 'ledger': ledger, 'lessons': lessons}, bars


# ---------------------------------------------------------------- harness

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


def make_handler(root, alt_index):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            if alt_index and (self.path == '/index.html' or self.path.startswith('/index.html?')):
                try:
                    with open(alt_index, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError as e:
                    self.send_error(500, str(e))
                return
            super().do_GET()

        def log_message(self, *a):
            pass
    return H


def _render_page(chrome, root, alt_index, cases, inter, qs, data_obj, bars):
    """One render of the probe page in a fresh headless Chrome. Returns (data, error message or None)."""
    pdir = tempfile.mkdtemp(prefix='_homeprobe_', dir=root)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__QS__', qs)
            .replace('__CASES__', json.dumps(cases))
            .replace('__INTER__', json.dumps(inter))
            .replace('__VP__', json.dumps(VIEWPORTS))
            .replace('__DATA__', json.dumps(data_obj))
            .replace('__BARS__', json.dumps(bars))
            .replace('__PASTE__', json.dumps(PASTE_URL))
            .replace('__INSTALL__', json.dumps(INSTALL_JS)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='homeprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
             '--user-data-dir=' + prof, '--virtual-time-budget=56000', '--window-size=1500,1000',
             '--dump-dom', 'http://127.0.0.1:%d/%s/probe.html' % (port, os.path.basename(pdir))],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150).stdout
    except Exception as e:
        return None, 'chrome failed: %s' % e
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'HOMEPROBE: (\{.*?\})</pre>', out or '', re.S)
    if not m:
        return None, 'probe produced no readout'
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return None, 'unreadable readout: %s' % e
    return data, None


def _attempt(chrome, root, alt_index):
    """Render every case and interaction once in a fresh headless Chrome (main layout), then the
    ?oldboards=1 escape hatch in a second page load.
    Returns (verdict, fails, notes, data, retry_worthy)."""
    data_obj, bars = build_data()
    data, err = _render_page(chrome, root, alt_index, CASES, INTERACTIONS, '', data_obj, bars)
    if err:
        return INCONCLUSIVE, [err], [], None, True
    old, err = _render_page(chrome, root, alt_index, OLD_CASES, [], '?oldboards=1', data_obj, bars)
    if err:
        return INCONCLUSIVE, ['?oldboards=1 pass: %s' % err], [], data, True
    if os.environ.get('HOMEPROBE_DUMP'):
        io.open(os.path.join(root, '_homeprobe_dump.json'), 'w', encoding='utf-8').write(
            json.dumps({'main': data, 'old': old}, indent=1, ensure_ascii=False))
    data['old'] = old
    return _judge(data, data_obj)


def _close_day(t):
    """The New York day a trade closed - the same rule as the app's ledgerCloseDay."""
    import datetime
    if t.get('exitDate'):
        return t['exitDate'][:10]
    parts = [int(x) for x in (t.get('entryTime') or '').split(':')]
    dur = t.get('durationMins') or 0
    if t.get('date') and parts and dur > 0:
        e = parts[0] * 3600 + (parts[1] if len(parts) > 1 else 0) * 60 + (parts[2] if len(parts) > 2 else 0)
        add = (e + dur * 60) // 86400
        if add > 0:
            return (datetime.date.fromisoformat(t['date']) + datetime.timedelta(days=add)).isoformat()
    return t['date']


def _close_key(t):
    parts = [int(x) for x in (t.get('exitTime') or t.get('entryTime') or '0').split(':')]
    secs = parts[0] * 3600 + (parts[1] if len(parts) > 1 else 0) * 60 + (parts[2] if len(parts) > 2 else 0)
    return '%s %05d' % (_close_day(t), secs)


def _signed(v):
    return '%s$%s' % ('+' if v >= 0 else '-', format(abs(v), ',.2f'))


def expected_days(trades):
    """{close day: signed net} - what each day header of the frame must read."""
    nets = {}
    for t in trades:
        k = _close_day(t)
        nets[k] = nets.get(k, 0.0) + t['pnl']
    return {k: _signed(round(v, 2)) for k, v in nets.items()}


def _judge_old(old, data_obj):
    """?oldboards=1: the previous list layout is still drawn (FEED / TABLE button, 7 chips, no frame)."""
    fails, unfinished = [], []
    cases = (old or {}).get('cases') or {}
    n_trades = len(data_obj['trades'])
    for nm, cfg in OLD_CASES:
        r = cases.get(nm)
        tag = '?oldboards=1 %s' % nm
        if r is None:
            unfinished.append('%s: never ran' % tag)
            continue
        before = len(fails)
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('call'))))
        _errs(tag, r, fails)
        if len(fails) > before:
            continue
        ol = r.get('oldList') or {}
        if ol.get('frames'):
            fails.append('%s: the new trade list frame is drawn although ?oldboards=1 asks for the previous layout' % tag)
        if not ol.get('toggle') or ol.get('chips') != 7:
            fails.append('%s: the previous list toolbar is missing (FEED / TABLE button=%s, chips=%s)'
                         % (tag, ol.get('toggle'), ol.get('chips')))
        want_kind = cfg['ledger'] if cfg['view'] == 'table' else 'feed'
        if r.get('ledgerKind') != want_kind or r.get('ledgerRows') != n_trades:
            fails.append('%s: the previous ledger is %r with %s rows, expected %s with %d'
                         % (tag, r.get('ledgerKind'), r.get('ledgerRows'), want_kind.upper(), n_trades))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the previous layout scrolls sideways on a phone' % tag)
    return fails, unfinished


def _first(s, n=300):
    return (s or '').strip().splitlines()[0][:n] if (s or '').strip() else ''


def _errs(tag, r, fails):
    for e in r.get('errors') or []:
        fails.append('%s: console.error -- %s' % (tag, _first(e)))
    for e in r.get('uncaught') or []:
        fails.append('%s: uncaught -- %s' % (tag, _first(e)))
    for e in r.get('loadErr') or []:
        fails.append('%s: window._loadError fired -- %s' % (tag, _first(e)))
    if r.get('overlay'):
        fails.append('%s: the LOAD ERROR overlay is on the page' % tag)


def _judge(data, data_obj):
    why = data.get('why')
    if why == 'noboot':
        return (INCONCLUSIVE, ['app did not boot (renderApp=%s); see preflight_boot' % data.get('renderApp')],
                [], data, False)
    if data.get('err'):
        return FAIL, ['probe could not run: %s' % _first(data['err'])], [], data, True
    n_trades = len(data_obj['trades'])
    n_missed = len(data_obj['missed'])
    fails, notes, unfinished = [], [], []
    boot = data.get('bootNoise') or {}
    for e in (boot.get('errors') or []) + (boot.get('uncaught') or []):
        notes.append('before any case (boot, not judged): %s' % _first(e, 200))

    cases = data.get('cases') or {}
    for nm, cfg in CASES:
        r = cases.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (nm, why))
            continue
        before = len(fails)
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, _first(r.get('call'))))
        if r.get('sampleErr'):
            fails.append('%s: could not read the page -- %s' % (nm, _first(r['sampleErr'])))
        _errs(nm, r, fails)
        if len(fails) > before:
            continue                     # one crash explains everything below it
        want_w = VIEWPORTS[cfg['vp']][0]
        if r.get('innerW') != want_w:
            unfinished.append('%s: the viewport is %spx, not %spx' % (nm, r.get('innerW'), want_w))
            continue
        if r.get('theme') != cfg['theme']:
            fails.append('%s: data-theme is %r, not %r' % (nm, r.get('theme'), cfg['theme']))
        if cfg.get('kind') == 'legacy':
            # LEDGER step 8 / mistake #14: the legacy TRADES and JOURNAL tabs draw on a phone, in one column
            lg = r.get('legacy') or {}
            if lg.get('tab') != cfg['tab']:
                fails.append('%s: the %s tab did not open (activeTab=%r)' % (nm, cfg['tab'], lg.get('tab')))
            elif cfg['tab'] == 'trades' and (not lg.get('table') or lg.get('rows') != n_trades):
                fails.append('%s: the legacy TRADES table shows %s rows for %s trades (table present: %s)'
                             % (nm, lg.get('rows'), n_trades, lg.get('table')))
            elif cfg['tab'] == 'journal' and (not lg.get('journalForm') or not lg.get('lessons')):
                fails.append('%s: the legacy JOURNAL tab drew no form or no entry (form=%s entries=%s)'
                             % (nm, lg.get('journalForm'), lg.get('lessons')))
            if (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
                fails.append('%s: the legacy %s tab scrolls sideways on a phone (scrollWidth %s > clientWidth %s; '
                             'sticking out: %s)' % (nm, cfg['tab'].upper(), r.get('scrollW'), r.get('clientW'),
                                                    ', '.join(r.get('wide') or []) or '?'))
            if cfg['tab'] == 'trades' and lg.get('boxScrollW') is not None \
                    and lg['boxScrollW'] > (lg.get('boxClientW') or 0) + 1:
                fails.append('%s: the legacy TRADES table scrolls sideways inside its box on a phone (box scrollWidth '
                             '%s > clientWidth %s)' % (nm, lg.get('boxScrollW'), lg.get('boxClientW')))
            if (r.get('appLen') or 0) < 3000:
                fails.append('%s: the legacy tab rendered almost nothing (%s chars)' % (nm, r.get('appLen')))
            continue
        if not r.get('missed'):
            fails.append('%s: no #hm-missed (SHOULD HAVE TRADED) section' % nm)
        elif r.get('missedRows') != (n_missed if cfg['missed'] else 0):
            fails.append('%s: SHOULD HAVE TRADED shows %s rows for %s entries'
                         % (nm, r.get('missedRows'), n_missed if cfg['missed'] else 0))
        want_kind = cfg['ledger'] if cfg['view'] == 'table' else 'feed'
        if not r.get('feed'):
            fails.append('%s: no ledger container (#hm-feed-container)' % nm)
        elif r.get('ledgerKind') != want_kind:
            fails.append('%s: the ledger is %r, expected the %s view' % (nm, r.get('ledgerKind') or 'missing',
                                                                        want_kind.upper()))
        elif r.get('ledgerRows') != n_trades:
            fails.append('%s: the ledger shows %s rows for %s trades' % (nm, r.get('ledgerRows'), n_trades))
        # LEDGER unify step 8: the shared trade list frame (toolbar, day headers, rows, five cells on a phone)
        if r.get('frameN') != 1 or not r.get('frame'):
            fails.append('%s: the page draws %s trade list frames ([data-lglist-frame]), expected exactly one'
                         % (nm, r.get('frameN')))
        else:
            want_mode = 'table' if cfg['view'] == 'table' else 'list'
            if r.get('mode') != want_mode:
                fails.append('%s: the trade list frame is in %r mode, expected %r' % (nm, r.get('mode'), want_mode))
            if r.get('chipTxt') != FRAME_CHIPS:
                fails.append('%s: the frame chips read %r, not %s' % (nm, r.get('chipTxt'), FRAME_CHIPS))
            if r.get('chipOn') != 'ALL':
                fails.append('%s: the active chip is %r, expected ALL' % (nm, r.get('chipOn')))
            if r.get('viewBtns') != ('list,table*' if want_mode == 'table' else 'list*,table'):
                fails.append('%s: the LIST | TABLE toggle reads %r (a * marks the pressed half)' % (nm, r.get('viewBtns')))
            if not r.get('searchBox'):
                fails.append('%s: the frame has no search box' % nm)
            if r.get('count') != '%d / %d trades' % (n_trades, n_trades):
                fails.append('%s: the frame count reads %r, expected %d / %d trades' % (nm, r.get('count'), n_trades, n_trades))
            exp = expected_days(data_obj['trades'])
            got_days = [x.split('=', 1) for x in (r.get('days') or [])]
            if [g[0] for g in got_days] != sorted(exp, reverse=True):
                fails.append('%s: the day headers read %r, expected the close days %r newest first'
                             % (nm, [g[0] for g in got_days], sorted(exp, reverse=True)))
            else:
                for day, net in got_days:
                    if not re.match(r'^[+-]\$[\d,]+\.\d\d$', net):
                        fails.append('%s: the %s day header net reads %r (needs a sign and a dollar amount)' % (nm, day, net))
                    elif net != exp[day]:
                        fails.append('%s: the %s day header net is %s, expected %s' % (nm, day, net, exp[day]))
            if r.get('ovDay') != '2026-10-01':
                fails.append('%s: the overnight trade (entered 09-30 23:55, held 25 min) sits under %r, it closed on 2026-10-01'
                             % (nm, r.get('ovDay')))
            if r.get('frameRows') != n_trades:
                fails.append('%s: the frame draws %s trade rows for %s trades' % (nm, r.get('frameRows'), n_trades))
            if cfg['vp'] == 'phone':
                if r.get('visCells') != 5:
                    fails.append('%s: a phone row shows %s cells, expected five (time, symbol, side, net, chart)'
                                 % (nm, r.get('visCells')))
                if r.get('listTop') is None or r.get('listTop') > (r.get('viewH') or 0):
                    fails.append('%s: the trade list starts %spx below the top of the board on a phone, more than one '
                                 'screen (%spx) - mistake #12' % (nm, r.get('listTop'), r.get('viewH')))
        if cfg['view'] == 'feed' and r.get('frame'):
            exp_order = [t['id'] for t in sorted(data_obj['trades'], key=_close_key, reverse=True)]
            if r.get('order') != exp_order:
                fails.append('%s: the list rows run %r, expected newest close first %r' % (nm, r.get('order'), exp_order))
            if r.get('depositRows') != 1:
                fails.append('%s: the list shows %s deposit rows, expected the one deposit in its day' % (nm, r.get('depositRows')))
        ai = r.get('aiFold')
        if not ai or not ai.get('closed') or ai.get('out'):
            fails.append('%s: the AI ASSESSMENT is not a closed fold (%r) - it filled the top of the page' % (nm, ai))
        af = r.get('acctFold')
        if not af:
            fails.append('%s: the account line / list section is missing' % nm)
        elif cfg['vp'] == 'phone' and (af.get('btn') == 'none' or af.get('list') != 'none'):
            fails.append('%s: on a phone the account list should be one closed line (button display=%r, list display=%r)'
                         % (nm, af.get('btn'), af.get('list')))
        elif cfg['vp'] != 'phone' and (af.get('btn') != 'none' or af.get('list') == 'none'):
            fails.append('%s: on a laptop the account list is always drawn (button display=%r, list display=%r)'
                         % (nm, af.get('btn'), af.get('list')))
        tbx = r.get('tblBox')
        if cfg['view'] == 'table' and cfg['ledger'] == 'simple' and tbx and tbx['sw'] > tbx['cw'] + 1:
            fails.append('%s: the SIMPLE table scrolls sideways inside its box (scrollWidth %s > clientWidth %s)'
                         % (nm, tbx['sw'], tbx['cw']))
        if not r.get('paste'):
            fails.append('%s: the PASTE box for snapshot links (#hm-paste-chart) is gone' % nm)
        elif cfg['vp'] != 'phone' and not r.get('pasteVisible'):
            fails.append('%s: the PASTE box is on the page but not visible on a laptop' % nm)
        if (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1 and cfg['vp'] != 'phone':
            fails.append('%s: the page scrolls sideways on a laptop (scrollWidth %s > clientWidth %s; sticking out: %s)'
                         % (nm, r.get('scrollW'), r.get('clientW'), ', '.join(r.get('wide') or []) or '?'))
        if r.get('sheetClosed') not in ('none', 'open'):
            fails.append('%s: the closed trade panel is display:%s - parked off-screen it widens the page sideways'
                         % (nm, r.get('sheetClosed')))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (scrollWidth %s > clientWidth %s; '
                         'sticking out: %s)' % (nm, r.get('scrollW'), r.get('clientW'),
                                                ', '.join(r.get('wide') or []) or '?'))
        if not re.match(r'^-?\$[\d,]+\.\d\d$', r.get('heroBig') or ''):
            fails.append('%s: the hero big number reads %r, not a dollar amount' % (nm, r.get('heroBig')))
        if not (r.get('heroToday') or '').endswith('today'):
            fails.append('%s: the hero has no "today" line (got %r)' % (nm, r.get('heroToday')))
        if r.get('pills') != ','.join(LEDGER_RANGES):
            fails.append('%s: the range pills read %r, not %s' % (nm, r.get('pills'), ' '.join(LEDGER_RANGES)))
        min_h = 150 if cfg['vp'] == 'phone' else 200
        if (r.get('chartH') or 0) < min_h:
            fails.append('%s: the equity chart is %spx tall (squashed; needs %s+)' % (nm, r.get('chartH'), min_h))
        if r.get('acctRows') != 3 or r.get('acctSel') != '':
            fails.append('%s: the account list shows %s rows with %r selected (expected ALL + 2 brokers, ALL selected)'
                         % (nm, r.get('acctRows'), r.get('acctSel')))
        if r.get('acctPill'):
            fails.append('%s: the tab-row ACCOUNT pill still shows on LEDGER (the account list replaces it there)' % nm)
        if r.get('acctScoped') is not True:
            fails.append('%s: tapping the NinjaTrader row did not scope the board (hero label)' % nm)
        if (r.get('legendN') or 0) < 2:
            fails.append('%s: the P&L chart shows %s broker lines in its legend (the probe data has two brokers)' % (nm, r.get('legendN')))
        if (r.get('legendH') or 0) > 40:
            fails.append('%s: a chart legend entry is %spx tall (should be one short line)' % (nm, r.get('legendH')))
        if (r.get('chartDates') or 0) < 2 or (r.get('chartTicks') or 0) < 2:
            fails.append('%s: the equity chart has %s date labels and %s price labels (needs 2+ of each)'
                         % (nm, r.get('chartDates'), r.get('chartTicks')))
        st = r.get('stats') or []
        if [x.split('=')[0] for x in st] != ['winrate', 'pf', 'maxdd', 'trades']:
            fails.append('%s: the stats strip reads %r, not the four tiles win rate, profit factor, max drawdown, '
                         'trades' % (nm, st))
        else:
            vals = dict(x.split('=', 1) for x in st)
            if not re.match(r'^\$[\d,]+\.\d\d$', vals['maxdd']):
                fails.append('%s: max drawdown reads %r (must be a positive dollar amount)' % (nm, vals['maxdd']))
            if not re.match(r'^(\d+\.\d\d|no losses|--)$', vals['pf']):
                fails.append('%s: profit factor reads %r' % (nm, vals['pf']))
        if r.get('moreGroups') != 'Returns,Risk,Mix,Account':
            fails.append('%s: More stats opened with groups %r, not Returns, Risk, Mix, Account'
                         % (nm, r.get('moreGroups')))
        cal = r.get('cal')
        if not cal:
            fails.append('%s: the LEDGER calendar fold is missing' % nm)
        else:
            if not cal.get('days') or cal.get('cells', 0) % 8:
                fails.append('%s: the calendar shows %s traded days in %s cells (needs 1+ days, rows of 7 days + a week)'
                             % (nm, cal.get('days'), cal.get('cells')))
            elif cal.get('sumN') != cal.get('hdN'):
                fails.append('%s: the calendar days add up to %s trades but its header says %s'
                             % (nm, cal.get('sumN'), cal.get('hdN')))
            if cfg['view'] != 'table' and not cal.get('jump'):
                fails.append('%s: tapping a calendar day did not jump the trade list to that day' % nm)
        if (r.get('appLen') or 0) < 3000:
            fails.append('%s: HOME rendered almost nothing (%s chars)' % (nm, r.get('appLen')))

    inter = data.get('inter') or {}
    for nm, I in INTERACTIONS:
        res = inter.get(nm)
        tag = 'interaction %s' % nm
        if res is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if res.get('threw'):
            fails.append('%s: the probe itself threw -- %s' % (tag, _first(res['threw'])))
            continue
        if res.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get('seed'))))
            continue
        _errs(tag + ' (render)', res.get('seedErr') or {}, fails)
        st = res.get('steps') or {}
        p = st.get('panel') or {}
        _errs(tag + ' trade panel', p, fails)
        if p.get('threw'):
            fails.append('%s trade panel: %s' % (tag, _first(p['threw'])))
        if not p.get('open'):
            fails.append('%s: the trade panel for %s did not open' % (tag, I['tid']))
        if not p.get('drew'):
            body = p.get('body') or ''
            if 'loading the candles' in body and not any(p.get(k) for k in ('errors', 'uncaught')):
                unfinished.append('%s: the chart was still loading after 6s with no error' % tag)
            else:
                fails.append('%s: the trade panel chart never drew an <svg> (chart body says: %r)'
                             % (tag, body[:120]))
        pts = p.get('points') or ''
        if 'POINTS' not in pts or I['pts'] not in pts:
            fails.append('%s: the trade panel POINTS block is missing or does not show %s (%r)'
                         % (tag, I['pts'], pts[:80]))
        z = st.get('zoom') or {}
        _errs(tag + ' zoom out / DAY', z, fails)
        if z.get('threw'):
            fails.append('%s zoom: %s' % (tag, _first(z['threw'])))
        if p.get('drew'):
            if z.get('buttons') != 2:
                fails.append('%s: the chart has no - / DAY buttons' % tag)
            elif not z.get('svg'):
                fails.append('%s: the chart vanished after - / DAY' % tag)
            elif not z.get('redrew'):
                fails.append('%s: - and DAY did not redraw the chart (it still shows the trade view)' % tag)
        mp = st.get('missedPanel') or {}
        _errs(tag + ' SHOULD HAVE TRADED panel', mp, fails)
        if mp.get('threw'):
            fails.append('%s SHOULD HAVE TRADED panel: %s' % (tag, _first(mp['threw'])))
        if not mp.get('open') or mp.get('sym') != I['msym'] or 'SHOULD HAVE TRADED' not in (mp.get('sub') or ''):
            fails.append('%s: the SHOULD HAVE TRADED panel did not render (open=%s sym=%r sub=%r)'
                         % (tag, mp.get('open'), mp.get('sym'), (mp.get('sub') or '')[:60]))
        else:
            if 'POINTS' not in (mp.get('points') or '') or I['mpts'] not in (mp.get('points') or ''):
                fails.append('%s: the SHOULD HAVE TRADED panel has no POINTS block showing %s'
                             % (tag, I['mpts']))
            if not mp.get('drew'):
                fails.append('%s: the SHOULD HAVE TRADED panel chart never drew (%r)'
                             % (tag, (mp.get('body') or '')[:120]))
        af = st.get('addForm') or {}
        _errs(tag + ' + ADD / SAVE', af, fails)
        if af.get('threw'):
            fails.append('%s + ADD: %s' % (tag, _first(af['threw'])))
        if not af.get('addBtn') or not af.get('form') or not af.get('saveBtn'):
            fails.append('%s: + ADD did not open the SHOULD HAVE TRADED form (button=%s form=%s save=%s)'
                         % (tag, af.get('addBtn'), af.get('form'), af.get('saveBtn')))
        elif not af.get('msg') or af.get('msg') == af.get('msg0'):
            fails.append('%s: SAVE with empty fields showed no message (#hmmf-msg=%r)' % (tag, af.get('msg')))
        if af.get('writes'):
            fails.append('%s: SAVE with empty fields wrote to the database: %s' % (tag, af['writes']))
        ps = st.get('paste') or {}
        _errs(tag + ' paste box', ps, fails)
        if ps.get('threw'):
            fails.append('%s paste: %s' % (tag, _first(ps['threw'])))
        if not ps.get('note') or not ps.get('missedBtn'):
            fails.append('%s: hmFileChartLink showed no paste note with a SHOULD HAVE TRADED button '
                         '(note=%s button=%s)' % (tag, ps.get('note'), ps.get('missedBtn')))
        elif not ps.get('form') or ps.get('url') != PASTE_URL:
            fails.append('%s: the paste note SHOULD HAVE TRADED button did not open the form with the '
                         'link filled in (form=%s url=%r)' % (tag, ps.get('form'), ps.get('url')))
        if ps.get('writes'):
            fails.append('%s: the paste box wrote to the database before anyone chose: %s'
                         % (tag, ps['writes']))
        # LEDGER step 8: the shared frame's chips, search, view toggle, BY DAY and SIMPLE | FULL
        T = data_obj['trades']
        fs = st.get('frame') or {}
        _errs(tag + ' trade list frame', fs, fails)
        if fs.get('threw'):
            fails.append('%s trade list frame: %s' % (tag, _first(fs['threw'])))
        else:
            def ids(pred):
                return sorted(t['id'] for t in T if pred(t))
            futs = ('MNQ', 'MES')
            want = {'WINS': ids(lambda t: t['pnl'] > 0), 'LOSSES': ids(lambda t: t['pnl'] < 0),
                    'LONG': ids(lambda t: t['type'] == 'LONG'), 'SHORT': ids(lambda t: t['type'] == 'SHORT'),
                    'FUTURES': ids(lambda t: t['symbol'] in futs), 'STOCKS': ids(lambda t: t['symbol'] not in futs),
                    'ALL': ids(lambda t: True)}
            chips = fs.get('chips') or {}
            for c, w_ in want.items():
                if chips.get(c) != w_:
                    fails.append('%s: the %s chip lists %r, expected %r' % (tag, c, chips.get(c), w_))
            flat = [t['id'] for t in T if t['pnl'] == 0]
            for c in ('WINS', 'LOSSES'):
                if set(flat) & set(chips.get(c) or []):
                    fails.append('%s: the %s chip lists the $0 trade %s - a $0 trade is neither a win nor a loss'
                                 % (tag, c, flat))
            if not fs.get('searchBox'):
                fails.append('%s: the frame has no search box' % tag)
            elif fs.get('search') != ['probe_s1']:
                fails.append('%s: searching "aapl" lists %r, expected the one AAPL trade' % (tag, fs.get('search')))
            elif fs.get('searchFocus') != 'hm-search':
                fails.append('%s: typing in the search box lost the cursor (focus is on %r)' % (tag, fs.get('searchFocus')))
            elif fs.get('searchCleared') != len(T):
                fails.append('%s: clearing the search lists %s trades, expected %d' % (tag, fs.get('searchCleared'), len(T)))
            if not fs.get('byDayBtn'):
                fails.append('%s: the BY DAY button is missing in the list view' % tag)
            elif fs.get('byDayDays') != len(expected_days(T)) or fs.get('byDayTrades') != 0:
                fails.append('%s: BY DAY shows %s day rows and %s trade rows, expected %d and 0'
                             % (tag, fs.get('byDayDays'), fs.get('byDayTrades'), len(expected_days(T))))
            if not fs.get('viewBtn') or fs.get('modeTable') != 'table' or fs.get('savedTable') != 'table':
                fails.append('%s: the TABLE button did not switch the frame to the table and remember it '
                             '(mode=%r saved=%r)' % (tag, fs.get('modeTable'), fs.get('savedTable')))
            if fs.get('modeList') != 'list' or fs.get('savedList') != 'list':
                fails.append('%s: the LIST button did not switch the frame back and remember it (mode=%r saved=%r)'
                             % (tag, fs.get('modeList'), fs.get('savedList')))
            if not fs.get('fullBtn') or not fs.get('fullTable') or not fs.get('simpleTable'):
                fails.append('%s: SIMPLE | FULL did not switch the table (full button=%s full=%s simple=%s)'
                             % (tag, fs.get('fullBtn'), fs.get('fullTable'), fs.get('simpleTable')))
            elif (fs.get('fullCols') or 0) <= (fs.get('simpleCols') or 0):
                fails.append('%s: FULL shows %s columns, SIMPLE %s - FULL must show more'
                             % (tag, fs.get('fullCols'), fs.get('simpleCols')))
            if not fs.get('paste'):
                fails.append('%s: the PASTE box is gone from the frame toolbar' % tag)
            bt = fs.get('buttons') or {}
            if not (bt.get('add') and bt.get('scan') and bt.get('all') and bt.get('nt')):
                fails.append('%s: the toolbar lost one of NEW TRADE / ADD DEPOSIT / SCAN DUPLICATES / OPEN ALL (%r)' % (tag, bt))
            elif not fs.get('formOpen') or not fs.get('formClosed'):
                fails.append('%s: NEW TRADE did not open and close its form (open=%s closed=%s)'
                             % (tag, fs.get('formOpen'), fs.get('formClosed')))
            tl = fs.get('tools') or {}
            if I['vp'] == 'phone':
                if tl.get('toggle') == 'none' or tl.get('box') != 'none' or tl.get('boxOpen') != 'flex' or tl.get('boxShut') != 'none':
                    fails.append('%s: the ... button on a phone should open and close the four action buttons (%r)' % (tag, tl))
            elif tl.get('toggle') != 'none' or tl.get('box') == 'none':
                fails.append('%s: on a laptop the four action buttons are always shown and the ... button is not (%r)' % (tag, tl))
        sm = st.get('sortmenu') or {}
        _errs(tag + ' header sort menu', sm, fails)
        if sm.get('threw'):
            fails.append('%s header sort menu: %s' % (tag, _first(sm['threw'])))
        elif I['vp'] == 'laptop':
            if not sm.get('header') or not sm.get('menu') or not sm.get('ascItem'):
                fails.append('%s: the NET header did not open its sort / filter menu (header=%s menu=%s ascending=%s)'
                             % (tag, sm.get('header'), sm.get('menu'), sm.get('ascItem')))
            else:
                vals = [float(x.replace('$', '').replace(',', '').replace('+', '')) for x in (sm.get('nets') or [])]
                if len(vals) != len(data_obj['trades']) or vals != sorted(vals):
                    fails.append('%s: sorting NET ascending left the rows in this order: %r' % (tag, sm.get('nets')))
                if sm.get('dayRows'):
                    fails.append('%s: day headers are still drawn after sorting by NET (%s)' % (tag, sm.get('dayRows')))
                if 'NET' not in (sm.get('label') or '') or '\u25b2' not in (sm.get('label') or ''):
                    fails.append('%s: the sort label reads %r, expected SORTED BY NET with an up arrow' % (tag, sm.get('label')))
        sh = st.get('sheet') or {}
        _errs(tag + ' trade panel editors', sh, fails)
        if sh.get('threw'):
            fails.append('%s trade panel editors: %s' % (tag, _first(sh['threw'])))
        else:
            b = sh.get('buttons') or {}
            if not (b.get('edit') and b.get('snap') and b.get('tv') and b.get('del')):
                fails.append('%s: the trade panel lost one of EDIT / SNAPSHOT / OPEN IN TV / DELETE (%r)' % (tag, b))
            if not sh.get('sel'):
                fails.append('%s: the trade panel has no grade / setup editors' % tag)
            else:
                wr = sh.get('data') or []
                g = [x for x in wr if x.get('id') == 'probe_t2' and 'grade' in (x.get('d') or {})]
                s_ = [x for x in wr if x.get('id') == 'probe_t2' and 'setup' in (x.get('d') or {})]
                if not g or g[-1]['d']['grade'] != 'A':
                    fails.append('%s: changing the grade in the trade panel did not save {grade: A} (writes: %r)' % (tag, wr))
                if not s_ or s_[-1]['d']['setup'] != sh.get('setupPicked'):
                    fails.append('%s: changing the setup in the trade panel did not save it (picked %r, writes: %r)'
                                 % (tag, sh.get('setupPicked'), wr))
        ai = st.get('aiFold') or {}
        _errs(tag + ' AI assessment fold', ai, fails)
        if ai.get('threw'):
            fails.append('%s AI assessment fold: %s' % (tag, _first(ai['threw'])))
        elif not ai.get('fold') or ai.get('closed') is not True or ai.get('outputBefore'):
            fails.append('%s: the AI ASSESSMENT fold is not closed to start with (%r)' % (tag, ai))
        elif ai.get('open') is not True or not ai.get('outputAfter') or not ai.get('text') or ai.get('closedAgain') is not True:
            fails.append('%s: the AI ASSESSMENT fold did not open, fill and close again (%r)' % (tag, ai))
        ed = st.get('edits') or {}
        _errs(tag + ' inline edits', ed, fails)
        if ed.get('threw'):
            fails.append('%s inline edits: %s' % (tag, _first(ed['threw'])))
        elif I['vp'] == 'laptop':
            if not ed.get('gradeSel') or not ed.get('noteInput'):
                fails.append('%s: the TABLE has no inline grade select or note box for the first trade (grade=%s note=%s)'
                             % (tag, ed.get('gradeSel'), ed.get('noteInput')))
            else:
                wr = ed.get('data') or []
                g = [x for x in wr if x.get('id') == 'probe_t1' and 'grade' in (x.get('d') or {})]
                n = [x for x in wr if x.get('id') == 'probe_t1' and 'notes' in (x.get('d') or {})]
                if not g or g[-1]['d']['grade'] != 'A':
                    fails.append('%s: changing a grade in the TABLE did not save {grade: A} (writes: %r)' % (tag, wr))
                if not n or n[-1]['d']['notes'] != 'probe note edit':
                    fails.append('%s: editing a note in the TABLE did not save it (writes: %r)' % (tag, wr))
                if not ed.get('rowsN') or ed.get('editCells') != ed.get('rowsN') or ed.get('delCells') != ed.get('rowsN'):
                    fails.append('%s: every TABLE row should keep an EDIT and a DELETE cell (rows=%s edit=%s delete=%s)'
                                 % (tag, ed.get('rowsN'), ed.get('editCells'), ed.get('delCells')))
                elif not ed.get('delWired') or ed.get('editOpened') != 1:
                    fails.append('%s: the TABLE EDIT cell should open the edit window (opened=%s) and DELETE should be wired (wired=%s)'
                                 % (tag, ed.get('editOpened'), ed.get('delWired')))
        jp = st.get('jump') or {}
        _errs(tag + ' ANALYTICS jump', jp, fails)
        if jp.get('threw'):
            fails.append('%s ANALYTICS jump: %s' % (tag, _first(jp['threw'])))
        else:
            if jp.get('analyticsShown') != 'analytics':
                fails.append('%s: the ANALYTICS tab did not open before the jump (activeTab=%r)'
                             % (tag, jp.get('analyticsShown')))
            if jp.get('tab') != 'home' or jp.get('view') != 'table' or not jp.get('tableShown'):
                fails.append('%s: the ANALYTICS calendar jump did not land on the LEDGER table (tab=%r view=%r table=%s)'
                             % (tag, jp.get('tab'), jp.get('view'), jp.get('tableShown')))
            want_flash = len([t for t in T if t['date'] == JUMP_DAY])
            if jp.get('flashed') != want_flash:
                fails.append('%s: the jump to %s flashed %s rows, expected that day\'s %d trades'
                             % (tag, JUMP_DAY, jp.get('flashed'), want_flash))
            if not jp.get('dayHeader'):
                fails.append('%s: the LEDGER table has no day header for %s after the jump' % (tag, JUMP_DAY))

    of, ou = _judge_old(data.get('old'), data_obj)
    fails += of
    unfinished += ou
    if fails:
        return FAIL, fails, notes, data, True
    if unfinished:
        return INCONCLUSIVE, unfinished, notes, data, True
    return PASS, [], notes, data, False


def _report(t0, attempt, may_retry, chrome, root, alt_index):
    verdict, msgs, notes, data, retry = attempt
    first = None
    if verdict != PASS and retry and may_retry:
        first = (verdict, msgs)
        print('HOMEPROBE: attempt 1 did not pass, retrying once before blocking -- %s'
              % ('; '.join(msgs[:2]) or 'no detail'))
        verdict, msgs, notes, data, retry = _attempt(chrome, root, alt_index)
    elapsed = time.time() - t0
    data = data or {}
    if verdict == INCONCLUSIVE:
        print('HOMEPROBE: INCONCLUSIVE -- %s' % ('; '.join(msgs[:3]) if msgs else 'no detail'))
        return INCONCLUSIVE
    if verdict == FAIL:
        print('HOMEPROBE: FAIL (VERSION=%s, %.1fs%s, %d problem(s))'
              % (data.get('VERSION'), elapsed, ', both attempts' if first else '', len(msgs)))
        seen = set()
        for f in msgs:
            if f not in seen and len(seen) < 25:
                seen.add(f)
                print('  - ' + f)
        if len(set(msgs)) > 25:
            print('  - ... %d more' % (len(set(msgs)) - 25))
        for n in notes[:6]:
            print('  note: ' + n)
        return FAIL
    inter = data.get('inter') or {}
    zl = ((inter.get('laptop') or {}).get('steps') or {}).get('zoom') or {}
    print('HOMEPROBE: PASS (VERSION=%s, %d cases + %d ?oldboards=1 cases + %d interaction runs, %.1fs)'
          % (data.get('VERSION'), len(data.get('cases') or {}), len(((data.get('old') or {}).get('cases')) or {}),
             len(inter), elapsed))
    if first:
        print('  FLAKE: attempt 1 did not pass on this same file, the retry did. It said:')
        for f in first[1][:4]:
            print('    - ' + f)
    if os.environ.get('HOMEPROBE_VERBOSE'):
        print('  laptop chart after DAY: %s' % zl.get('infoDay'))
    for n in notes[:6]:
        print('  note: ' + n)
    return PASS


def selftest():
    """Exit 0 when the gate FAILS every MUTANT of the current index.html and PASSES the real file;
    1 when any expectation breaks; 2 when a mutant cannot be built (its anchor moved)."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='homeprobe-selftest-')
    bad = []
    try:
        for name, anchor, repl, why in MUTANTS:
            n = src.count(anchor)
            if n != 1:
                print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in '
                      'index.html (expected once). Update MUTANTS in tools/home_render_probe.py: %r'
                      % (name, n, anchor))
                return INCONCLUSIVE
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(anchor, repl))
            print('-- mutant %s (%s): expect FAIL' % (name, why))
            code = main(['--file', path, '--no-retry'])
            if code != FAIL:
                bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s'
                           % (name, code, why))
        print('-- current index.html: expect PASS')
        code = main([])
        if code != PASS:
            bad.append('current index.html did not PASS (exit %d)' % code)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL (%.1fs)' % (time.time() - t0))
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('SELFTEST: PASS -- gate caught %d/%d broken builds and passed the current one (%.1fs)'
          % (len(MUTANTS), len(MUTANTS), time.time() - t0))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--no-retry', action='store_true', help='do not re-render a failed attempt')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every MUTANT of index.html, then PASS on the real file')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    t0 = time.time()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('HOMEPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print('HOMEPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    return _report(t0, _attempt(chrome, root, alt_index), not args.no_retry, chrome, root, alt_index)


if __name__ == '__main__':
    sys.exit(main())
