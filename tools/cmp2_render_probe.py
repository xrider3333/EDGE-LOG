#!/usr/bin/env python3
"""
tools/cmp2_render_probe.py -- render gate for COMPARE beta (augurSub==='cmp2').

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. It never enters the new COMPARE-beta
tab (the "COMPARE \u03b2" LEADERBOARD shipped 2026-09-08), so a crash inside that branch
of renderApp -- or inside its handler wiring -- would ship green through every existing
gate. This is the same lesson studies_render_probe.py / paper_render_probe.py /
report_render_probe.py already encode for their own views, applied to cmp2.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe (like every other render
probe here), then -- inside the iframe's own global scope, where index.html's
top-level `let`/function bindings live -- forces the cmp2 tab and re-renders it for a
handful of states:

    activeTab='augur'; augurSub='cmp2'; renderApp();

with `runHistory`, `window._c2Open` and the `augurPrefs` localStorage doc (c2Screen /
c2Rank / c2Stage) set up per case first. Injecting a real run uses the exact
normalisation report_render_probe.py uses for the same fixture (tools/fixtures/
run_report.json, run #306) -- `_bookUnitsOnRead(_isoTs(doc))` -- so it reads to the
LEADERBOARD exactly as a live Firestore-synced run would.

WHAT IT ASSERTS, per case
--------------------------
  empty            -- no uncaught error, no console.error, body text says NO RUNS YET,
                       and the RANK ON / STAGE segmented controls still exist (4 + 3
                       [data-c2rank]/[data-c2stage] spans) even with zero runs.
  fixture-lb       -- no errors, >=1 [data-c2fam] family row, the champion's .c2-big
                       is non-empty (a number or the em dash), and .c2-note mentions
                       "1 strateg...".
  fixture-expand   -- pre-seeding window._c2Open with the family key read back from
                       fixture-lb reproduces a user's click: >=1 .c2-row.sub[data-c2run]
                       and >=1 [data-c2add] chip appear.
  stages           -- IS / WF / LB all render without throwing (values may honestly be
                       the dash -- this run fixture is thin on some stages).
  explore          -- the phase-4 EXPLORE screen. It is not a copy of the STUDIES board,
                       it IS that board: the tab hands the render to the old branch, so
                       this case checks the chart actually plotted points, the strategy
                       rail and study tables came with it, and COMPARE BETA's own screen
                       switcher sits above it. If EXPLORE ever renders without points
                       while the old tab still has them, the hand-off broke.
  runboard         -- the OLD tab's RUNBOARD (cmpMode 'board'), which no gate rendered
                       until the un-annualised MAR column was found by hand. Renders on all
                       three SAMPLE ticks and checks the lockbox MAR cell equals the
                       annualised figure computed here from the fixture's own lockbox pnl,
                       drawdown and window - so net-over-drawdown can never come back.
  compare          -- the phase-3 COMPARE screen with three runs picked (the fixture, a
                       twin with its stored lockbox drawdown removed so the curve-derived
                       path runs, and the synthesised book): the overlay draws the
                       solid + dotted paths with real coordinates, one removable chip per
                       picked run, a column per run and one row per metric, a best-in-row
                       mark on each contested row, a ~ on the derived drawdown, and a CLEAR
                       control; renders on IS / WF / LB without throwing. With nothing
                       picked it shows the empty card and its own way to the leaderboard.
  book             -- a synthesised BOOK run (engine shape: validate.lockbox = pnl/pf/
                       trades/pass only, `book` block with legs, lockbox {total_pnl,
                       max_drawdown, win_rate}, lockbox_from, date_to) beside the fixture:
                       a BOOKS family row exists next to the strategy row, its LB NET is
                       $70,000 exactly (no second contract multiplier), PF 1.40, and MAR
                       is a number (drawdown + window read off the book block).

No Firebase sign-in is needed; cmp2 reads only from the global runHistory array. cmp2's
render path is synchronous string-building (no deferred chart draw / no async render
step), so unlike report_render_probe.py this probe does not need to poll for settle --
every case is rendered and sampled back to back inside one script tick.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.

Usage:
  python tools/cmp2_render_probe.py                # gates this repo's index.html
  python tools/cmp2_render_probe.py --file X.html   # gates X as if it were index.html

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import http.server
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
PROBE_FILENAME = '_cmp2_probe.html'
N_CASES = 10

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>cmp2 probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1400px;height:900px;border:0"></iframe>
<pre id="o"></pre>
<script>
var FIX = __FIX__;
(function(){
  var reported=false;
  function hook(w){
    if(w.__probeSink)return w.__probeSink;
    var sink=w.__probeSink={errors:[],uncaught:[]};
    var orig=w.console.error;
    w.console.error=function(){
      var parts=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];
        parts.push(a&&a.stack?String(a.stack):String(a));}
      sink.errors.push(parts.join(' '));
      try{orig.apply(w.console,arguments);}catch(_){}
    };
    w.addEventListener('error',function(ev){
      sink.uncaught.push(String(ev&&ev.message||ev)+(ev&&ev.error&&ev.error.stack?' :: '+ev.error.stack:''));});
    w.addEventListener('unhandledrejection',function(ev){
      var r=ev&&ev.reason;sink.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    return sink;
  }
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      var sink=hook(w);
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.renderAppType=w.eval('typeof renderApp');
      if(out.renderAppType!=='function'){out.why='noboot';
        document.getElementById('o').textContent='CMP2PROBE: '+JSON.stringify(out);return;}

      function doRender(prefs, winCode, sub){
        sink.errors.length=0; sink.uncaught.length=0;
        var call;
        try{
          call=w.eval("(function(){try{"
            +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(prefs))+");"
            +winCode
            +"activeTab='augur';augurSub='"+(sub||'cmp2')+"';renderApp();return 'OK';"
            +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        }catch(e){call='ERR '+(e&&e.stack?e.stack:e);}
        return call;
      }
      function snap(name, call){
        var r={call:call,errors:sink.errors.slice(0,10),uncaught:sink.uncaught.slice(0,10)};
        out.cases[name]=r;
        return r;
      }
      var EMPTY_WIN="runHistory=[];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
      var FIX_WIN="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
        +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";

      // ── case 1: empty ──────────────────────────────────────────────────────────
      (function(){
        var call=doRender({c2Screen:'lead'}, EMPTY_WIN);
        var r=snap('empty', call);
        var bodyTxt=(d.body&&(d.body.innerText||d.body.textContent))||'';
        r.hasNoRuns=bodyTxt.indexOf('NO RUNS YET')>=0;
        r.rankCount=d.querySelectorAll('[data-c2rank]').length;
        r.stageCount=d.querySelectorAll('[data-c2stage]').length;
      })();

      // ── case 2: fixture-lb ─────────────────────────────────────────────────────
      var famKey=null;
      (function(){
        var call=doRender({c2Screen:'lead',c2Rank:'rpy',c2Stage:'lb'}, FIX_WIN);
        var r=snap('fixture-lb', call);
        var famRows=d.querySelectorAll('.c2-row[data-c2fam]');
        r.famRows=famRows.length;
        var champBig=famRows.length?famRows[0].querySelector('.c2-big'):null;
        r.champBigText=champBig?(champBig.textContent||'').trim():null;
        var note=d.querySelector('.c2-note');
        r.noteText=note?(note.textContent||'').trim():null;
        if(famRows.length)famKey=decodeURIComponent(famRows[0].getAttribute('data-c2fam'));
      })();

      // ── case 3: fixture-expand ─────────────────────────────────────────────────
      (function(){
        var wc=FIX_WIN+"window._c2Open=new Set(["+JSON.stringify(famKey)+"]);";
        var call=doRender({c2Screen:'lead',c2Rank:'rpy',c2Stage:'lb'}, wc);
        var r=snap('fixture-expand', call);
        r.famKey=famKey;
        r.subRows=d.querySelectorAll('.c2-row.sub[data-c2run]').length;
        r.addChips=d.querySelectorAll('[data-c2add]').length;
      })();

      // ── case 4: stages (IS / WF / LB) ─────────────────────────────────────────
      (function(){
        var stages=['is','wf','lb'], values={}, anyErr=null, allErrors=[], allUncaught=[];
        stages.forEach(function(st){
          var call=doRender({c2Screen:'lead',c2Rank:'rpy',c2Stage:st}, FIX_WIN);
          var famRows=d.querySelectorAll('.c2-row[data-c2fam]');
          var big=famRows.length?famRows[0].querySelector('.c2-big'):null;
          values[st]={call:call, big:big?(big.textContent||'').trim():null};
          if(call!=='OK'&&!anyErr)anyErr=st+': '+call;
          allErrors=allErrors.concat(sink.errors);
          allUncaught=allUncaught.concat(sink.uncaught);
        });
        var r=snap('stages', anyErr?('ERR '+anyErr):'OK');
        r.values=values;
        r.errors=allErrors.slice(0,10);
        r.uncaught=allUncaught.slice(0,10);
      })();

      // ── case 5: explore (phase 4) ────────────────────────
      (function(){
        var call=doRender({c2Screen:'explore',resLvl:'sweep'}, FIX_WIN);
        var r=snap('explore', call);
        r.points=d.querySelectorAll('[data-repoint]').length;
        r.rail=d.querySelectorAll('[data-refam]').length;
        r.rows=d.querySelectorAll('tr[data-rerow]').length;
        r.screenBtns=d.querySelectorAll('[data-c2screen]').length;
        r.hold=!!d.querySelector('.c2-hold');
        // phase 4b chrome: the preset bar, the three sheet buttons, and the two control
        //   groups that must never hide - the profit stage and the strategy rail. The old
        //   sidebar must be gone from this screen (it is still there on the old tab).
        r.presets=d.querySelectorAll('[data-respreset]').length;
        r.sheets=d.querySelectorAll('[data-c2sheet]').length;
        r.sidebar=d.querySelectorAll('[data-residel]').length;
        r.stage=d.querySelectorAll('[data-resstage]').length;
        r.help=d.querySelectorAll('[data-rehelptog]').length;
        // the study tables are built ON DEMAND here (they are ~3.5 MB of markup and were
        //   rebuilt on every click). Off by default; the button must bring them back, and
        //   the chart must be unaffected either way.
        r.tblBtn=d.querySelectorAll('[data-c2tbl]').length;
        r.rowsOff=d.querySelectorAll('tr[data-rerow]').length;
        var call2=doRender({c2Screen:'explore',resLvl:'sweep',c2Tbl:true}, FIX_WIN);
        r.call2=call2;
        r.rowsOn=d.querySelectorAll('tr[data-rerow]').length;
        r.pointsOn=d.querySelectorAll('[data-repoint]').length;
      })();

      // ── case 6: book (a BOOK run - own BOOKS row, dollars unscaled, LB dd off the book block) ─
      //    Synthesised from the fixture: the engine's book shape (augur_engine/book.py) - a
      //    validate.lockbox with ONLY pnl/pf/trades/pass and a `book` block carrying legs,
      //    lockbox {total_pnl, max_drawdown, win_rate}, lockbox_from and date_to.
      (function(){
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=String(+FIX.id+900000);BK.strategy='BOOK: '+String(FIX.strategy||'');BK.starred=false;
        BK.best_pnl_usd=250000;BK.best_dd_usd=30000;BK.multiplier=20;
        BK.book={name:'probe book',legs:[{strategy:FIX.strategy,weight:1},{strategy:'X_1_0.py',weight:1}],
          whole:{total_pnl:320000,max_drawdown:32000},pre_lockbox:{total_pnl:250000,max_drawdown:30000},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
          slices:[1,1,1,1,1,1,1,1],slices_held:8,slices_n:8,lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
        var wc="var F="+JSON.stringify(FIX)+";var B="+JSON.stringify(BK)+";"
          +"var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"var bdoc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(B)):B;"
          +"runHistory=[doc,bdoc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set(['BOOKS']);";
        var per={};
        ['mar','net','pf'].forEach(function(rk){
          var call=doRender({c2Screen:'lead',c2Rank:rk,c2Stage:'lb'}, wc);
          var rows=Array.prototype.slice.call(d.querySelectorAll('.c2-row[data-c2fam]'));
          var fams=rows.map(function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'');});
          var bi=fams.indexOf('BOOKS');
          var big=(bi>=0)?rows[bi].querySelector('.c2-big'):null;
          var bnm=(bi>=0)?rows[bi].querySelector('.c2-nm'):null;
          per[rk]={call:call,fams:fams,bookBig:big?(big.textContent||'').trim():null,bookNm:bnm?(bnm.textContent||'').trim():null,
            errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        });
        var ok=['mar','net','pf'].every(function(k){return per[k].call==='OK';});
        var r=snap('book', ok?'OK':'ERR');
        r.per=per;
        r.subRows=d.querySelectorAll('.c2-row.sub[data-c2run]').length;
      })();

      // ── case 7: compare (phase 3) ──────────────────────────────
      //    Three runs picked: the fixture (a 400-point validate.equity with an lb_idx, so it
      //    must draw a solid path AND a dotted lockbox tail); a twin of it with the stored
      //    lockbox drawdown deleted, which is the only run that reaches _c2eqDD, so the ~
      //    marker and its sentence in the note are actually executed; and the book from case
      //    6, whose validate was replaced and whose equity was deleted, so it has NO curve
      //    and must appear in the table but not on the chart, with the note saying so.
      (function(){
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=String(+FIX.id+900000);BK.strategy='BOOK: '+String(FIX.strategy||'');BK.starred=false;
        BK.best_pnl_usd=250000;BK.best_dd_usd=30000;BK.multiplier=20;
        BK.book={name:'probe book',legs:[{strategy:FIX.strategy,weight:1},{strategy:'X_1_0.py',weight:1}],
          whole:{total_pnl:320000,max_drawdown:32000},pre_lockbox:{total_pnl:250000,max_drawdown:30000},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
          slices:[1,1,1,1,1,1,1,1],slices_held:8,slices_n:8,lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
        delete BK.equity;   // a book with NO curve at all, so the disclosure line is tested
        // a third run with its stored lockbox drawdown removed: this is the only run that
        //   reaches _c2eqDD, so without it the headline of the change - the curve-derived
        //   drawdown, its ~ marker and its sentence in the note - is never executed here.
        var C=JSON.parse(JSON.stringify(FIX));
        C.id=String(+FIX.id+800000);C.starred=false;
        delete C.validate.lockbox.dd;
        var wc="var F="+JSON.stringify(FIX)+";var B="+JSON.stringify(BK)+";var K="+JSON.stringify(C)+";"
          +"var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"var bdoc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(B)):B;"
          +"var kdoc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(K)):K;"
          +"runHistory=[doc,bdoc,kdoc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var picks=[String(FIX.id),String(BK.id),String(C.id)];
        var per={};
        ['lb','is','wf','full'].forEach(function(st){
          var call=doRender({c2Screen:'cmp',c2Stage:st,cmpIds:picks}, wc);
          // scoped to the chart card, and the coordinates are read - an SVG whose d is full
          //   of NaN renders blank while still counting as a path, which is exactly the
          //   silent failure this case exists to catch.
          var ds=[].map.call(d.querySelectorAll('.c2-card svg path'),function(p){return p.getAttribute('d')||'';});
          per[st]={call:call,
            paths:ds.length,
            badD:ds.filter(function(t){return !t||/NaN|Infinity|undefined/.test(t);}).length,
            shortD:ds.filter(function(t){return (t.match(/L/g)||[]).length<1;}).length,
            // the live chart draws itself over the static one; its key rows are the proof it
            //   mounted, and the spotlight hook is what lets it reach into the table.
            host:d.querySelectorAll('#c2-ovl-host').length,
            keyRows:d.querySelectorAll('[data-ovltog]').length,
            expand:d.querySelectorAll('[data-cmpexpand]').length,
            spot:d.querySelectorAll('#rb-mtx-box [data-rbc]').length,
            apx:[].filter.call(d.querySelectorAll('.c2-card table td span'),function(e){
              return /^~/.test((e.textContent||'').trim());}).length,
            chips:d.querySelectorAll('.c2-lg').length,
            rm:d.querySelectorAll('[data-c2rm]').length,
            clr:d.querySelectorAll('[data-c2clr]').length,
            cols:d.querySelectorAll('.c2-card table th').length,
            rows:d.querySelectorAll('.c2-card table tr').length,
            best:d.querySelectorAll('[title="best of the picked runs on this row"]').length,
            note:((d.querySelector('.c2-note')||{}).textContent||'').slice(0,1400),
            // read named rows out of the matrix by their label, so a wrong number in a
            //   specific measure fails rather than hiding behind a row count.
            row:(function(){var o={};
              [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
                var c=tr.children; if(c.length<2)return;
                var lab=(c[0].textContent||'').trim();
                if(!lab)return;
                o[lab]=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
              return o;})(),
            errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        });
        var emptyCall=doRender({c2Screen:'cmp',c2Stage:'lb',cmpIds:[]}, wc);
        var _hold=d.querySelector('.c2-hold');
        var emptyHold=!!_hold, emptyGo=!!(_hold&&_hold.querySelector('[data-c2screen=\"lead\"]'));
        var ok=['lb','is','wf'].every(function(k){return per[k].call==='OK';})&&emptyCall==='OK';
        var r=snap('compare', ok?'OK':'ERR');
        r.per=per;r.emptyCall=emptyCall;r.emptyHold=emptyHold;r.emptyGo=emptyGo;
      })();

      // ── case 8: runboard (the OLD tab) ──────────────────────────
      (function(){
        var per={};
        ['lb','is','full'].forEach(function(smp){
          var call=doRender({cmpMode:'board',rbSample:smp,rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp');
          var mar=null, rows=[];
          [].forEach.call(d.querySelectorAll('tr'),function(tr){
            var c=[].map.call(tr.children,function(td){return (td.textContent||'').trim();});
            if(!c.length)return;
            rows.push(c[0]);
            if(c[0]==='MAR'&&mar===null){
              for(var i=1;i<c.length;i++){if(/^-?[0-9]/.test(c[i])){mar=c[i];break;}}}
          });
          per[smp]={call:call,mar:mar,hasMarRow:rows.indexOf('MAR')>=0,
            errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        });
        var ok=['lb','is','full'].every(function(k){return per[k].call==='OK';});
        var r=snap('runboard', ok?'OK':'ERR');
        r.per=per;
      })();

      // ── case 9: hosted views (phase 5) ───────────────────────
      //    With the old tab off the rail these are the ONLY way to reach the funnel and
      //    matrix, the picked-run tabs and saved sets, and the feature board. If one of
      //    them throws or draws nothing, a working feature has silently disappeared.
      (function(){
        var per={};
        ['board','runs','fam','feat'].forEach(function(v){
          var call=doRender({c2Screen:'cmp',c2View:v,cmpIds:[String(FIX.id)]}, FIX_WIN);
          var ap=d.getElementById('app');
          per[v]={call:call,
            len:ap?ap.innerHTML.length:-1,
            screenBtns:d.querySelectorAll('[data-c2screen]').length,
            viewBtns:d.querySelectorAll('[data-c2view]').length,
            oldPills:d.querySelectorAll('[data-cmpmode]').length,
            errors:sink.errors.slice(0,4),uncaught:sink.uncaught.slice(0,4)};
        });
        var ok=['board','runs','fam','feat'].every(function(v){return per[v].call==='OK';});
        var r=snap('hosted', ok?'OK':'ERR');
        r.per=per;
      })();

      // ── case 10: BOOKS (the old tab BOOKS tile, now a NATIVE view) ─────────────
      //    Two row sources - every real book run in history first, then the four
      //    offline rows - read from ONE pooled block per stage. The walk-forward
      //    stage must EXPLAIN itself: a book pools its legs over one window and
      //    tunes nothing, so ten empty cells would be a lie dressed as a table.
      (function(){
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=String(+FIX.id+900000);BK.strategy='BOOK: '+String(FIX.strategy||'');BK.starred=false;
        BK.best_pnl_usd=250000;BK.best_dd_usd=30000;BK.multiplier=20;
        BK.book={name:'probe book',legs:[{strategy:FIX.strategy,weight:1},{strategy:'X_1_0.py',weight:1}],
          whole:{total_pnl:320000,max_drawdown:32000,num_trades:2000,profit_factor:1.30},
          pre_lockbox:{total_pnl:250000,max_drawdown:30000,num_trades:1600,profit_factor:1.28},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
          worst_stretch:{from:'2020-02-19',to:'2020-03-23',depth:-32000},inert_legs:['X_1_0.py'],
          slices:[1,1,1,1,1,1,1,1],slices_held:8,slices_n:8,lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
        var wc="var F="+JSON.stringify(FIX)+";var B="+JSON.stringify(BK)+";"
          +"var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"var bdoc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(B)):B;"
          +"runHistory=[doc,bdoc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var per={};
        ['lb','is','full','wf'].forEach(function(st){
          var call=doRender({c2Screen:'cmp',c2View:'books',c2Stage:st}, wc);
          var ths=d.querySelectorAll('.c2-card table th');
          var bodyRows=d.querySelectorAll('.c2-card table tbody tr');
          var liveRows=d.querySelectorAll('.c2-card table tbody tr[data-c2run]');
          var txt=(d.body&&(d.body.innerText||d.body.textContent))||'';
          per[st]={call:call,
            ths:ths.length,
            bodyRows:bodyRows.length,
            liveRows:liveRows.length,
            statRows:bodyRows.length-liveRows.length,
            liveTxt:liveRows.length?(liveRows[0].textContent||'').slice(0,200):null,
            viewBtns:d.querySelectorAll('[data-c2view]').length,
            goRunboard:d.querySelectorAll('[data-c2view=board]').length,
            booksBtn:d.querySelectorAll('[data-c2view=books]').length,
            hold:!!d.querySelector('.c2-hold'),
            noWf:txt.indexOf('NO WALK-FORWARD STAGE')>=0,
            note:txt.indexOf('t5_runboard.py')>=0,
            launcher:txt.indexOf('RUN A BOOK')>=0,
            errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        });
        var ok=['lb','is','full','wf'].every(function(k){return per[k].call==='OK';});
        var r=snap('books', ok?'OK':'ERR');
        r.per=per;
      })();
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='CMP2PROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},3000);});
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


def clean(ppath, pdir):
    try:
        os.remove(ppath)
        os.rmdir(pdir)
    except OSError:
        pass


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', default=None,
                    help='gate this file as if it were index.html (self-test / diff use)')
    ap.add_argument('--fixture', default=None, help='override the run fixture path')
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('CMP2 PROBE: INCONCLUSIVE (--file not found: %s)' % alt_index)
        return INCONCLUSIVE

    fix_path = args.fixture or os.path.join(root, 'tools', 'fixtures', 'run_report.json')
    if not os.path.isfile(fix_path):
        print('CMP2 PROBE: INCONCLUSIVE (fixture missing: %s)' % fix_path)
        return INCONCLUSIVE
    try:
        fixture = json.load(io.open(fix_path, encoding='utf-8'))
    except Exception as e:
        print('CMP2 PROBE: INCONCLUSIVE (fixture unreadable: %s)' % e)
        return INCONCLUSIVE

    chrome = find_chrome()
    if not chrome:
        print('CMP2 PROBE: INCONCLUSIVE (no chrome found)')
        return INCONCLUSIVE

    pdir = os.path.join(root, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    html = PROBE_HTML.replace('__FIX__', json.dumps(fixture))
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(html)

    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    try:
        with tempfile.TemporaryDirectory() as ud:
            cargs = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                     '--hide-scrollbars', '--virtual-time-budget=30000',
                     '--user-data-dir=' + ud, '--dump-dom', url]
            try:
                out = subprocess.run(cargs, capture_output=True, text=True, encoding='utf-8',
                                     errors='replace', timeout=120).stdout or ''
            except subprocess.TimeoutExpired:
                print('CMP2 PROBE: INCONCLUSIVE (chrome timed out)')
                return INCONCLUSIVE
    finally:
        httpd.shutdown()
        clean(ppath, pdir)

    m = re.search(r'CMP2PROBE: (\{.*?\})\s*</pre>', out, re.S)
    if not m:
        print('CMP2 PROBE: INCONCLUSIVE (probe produced no reading)')
        return INCONCLUSIVE
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        print('CMP2 PROBE: INCONCLUSIVE (unreadable readout: %s)' % e)
        return INCONCLUSIVE

    if data.get('why') == 'noboot':
        print('CMP2 PROBE: INCONCLUSIVE (app did not boot; see preflight_boot)')
        return INCONCLUSIVE
    if data.get('err'):
        print('CMP2 PROBE: INCONCLUSIVE (probe threw: %s)' % data['err'])
        return INCONCLUSIVE

    cases = data.get('cases') or {}
    if len(cases) != N_CASES:
        print('CMP2 PROBE: INCONCLUSIVE (only %d of %d cases reported, why=%s)'
              % (len(cases), N_CASES, data.get('why')))
        return INCONCLUSIVE

    print('CMP2 PROBE: version %s, %d cases' % (data.get('VERSION'), len(cases)))
    bad = []

    def fail(msg):
        bad.append(msg)

    def line(name, ok, detail):
        print('  %-16s %-4s %s' % (name, 'OK' if ok else 'FAIL', detail))

    # case 1: empty
    r = cases.get('empty', {})
    ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
          and r.get('hasNoRuns') and r.get('rankCount') == 4 and r.get('stageCount') == 3)
    line('empty', ok, 'call=%s NO_RUNS_YET=%s rank=%s stage=%s errors=%s uncaught=%s'
         % (r.get('call'), r.get('hasNoRuns'), r.get('rankCount'), r.get('stageCount'),
            r.get('errors'), r.get('uncaught')))
    if not ok:
        if r.get('call') != 'OK':
            fail('empty: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('empty: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('empty: uncaught -- %s' % r['uncaught'][0][:200])
        if not r.get('hasNoRuns'):
            fail('empty: body text does not contain NO RUNS YET')
        if r.get('rankCount') != 4:
            fail('empty: expected 4 [data-c2rank] spans, got %s' % r.get('rankCount'))
        if r.get('stageCount') != 3:
            fail('empty: expected 3 [data-c2stage] spans, got %s' % r.get('stageCount'))

    # case 2: fixture-lb
    r = cases.get('fixture-lb', {})
    note_ok = bool(r.get('noteText')) and ('1 strateg' in r['noteText'])
    ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
          and (r.get('famRows') or 0) >= 1 and r.get('champBigText') and note_ok)
    line('fixture-lb', ok, 'call=%s famRows=%s champBig=%r note=%r errors=%s uncaught=%s'
         % (r.get('call'), r.get('famRows'), r.get('champBigText'), r.get('noteText'),
            r.get('errors'), r.get('uncaught')))
    if not ok:
        if r.get('call') != 'OK':
            fail('fixture-lb: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('fixture-lb: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('fixture-lb: uncaught -- %s' % r['uncaught'][0][:200])
        if (r.get('famRows') or 0) < 1:
            fail('fixture-lb: no [data-c2fam] family rows rendered')
        if not r.get('champBigText'):
            fail('fixture-lb: champion .c2-big is empty')
        if not note_ok:
            fail('fixture-lb: .c2-note does not mention "1 strateg..." (got %r)' % r.get('noteText'))

    # case 3: fixture-expand
    r = cases.get('fixture-expand', {})
    ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
          and (r.get('subRows') or 0) >= 1 and (r.get('addChips') or 0) >= 1)
    line('fixture-expand', ok, 'call=%s famKey=%r subRows=%s addChips=%s errors=%s uncaught=%s'
         % (r.get('call'), r.get('famKey'), r.get('subRows'), r.get('addChips'),
            r.get('errors'), r.get('uncaught')))
    if not ok:
        if r.get('call') != 'OK':
            fail('fixture-expand: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('fixture-expand: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('fixture-expand: uncaught -- %s' % r['uncaught'][0][:200])
        if not r.get('famKey'):
            fail('fixture-expand: no family key was available from fixture-lb')
        if (r.get('subRows') or 0) < 1:
            fail('fixture-expand: no .c2-row.sub[data-c2run] rendered when the family was pre-opened')
        if (r.get('addChips') or 0) < 1:
            fail('fixture-expand: no [data-c2add] chip rendered')

    # case 4: stages
    r = cases.get('stages', {})
    values = r.get('values') or {}
    stage_ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
                and all((values.get(s) or {}).get('call') == 'OK' for s in ('is', 'wf', 'lb')))
    line('stages', stage_ok, 'call=%s IS=%r WF=%r LB=%r errors=%s uncaught=%s'
         % (r.get('call'),
            (values.get('is') or {}).get('big'), (values.get('wf') or {}).get('big'),
            (values.get('lb') or {}).get('big'), r.get('errors'), r.get('uncaught')))
    if not stage_ok:
        if r.get('call') != 'OK':
            fail('stages: %s' % r.get('call'))
        if r.get('errors'):
            fail('stages: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('stages: uncaught -- %s' % r['uncaught'][0][:200])
        for s in ('is', 'wf', 'lb'):
            v = values.get(s) or {}
            if v.get('call') != 'OK':
                fail('stages: %s stage threw -- %s' % (s, str(v.get('call'))[:300]))

    # case 5: explore -- the board itself, hosted by the new tab
    r = cases.get('explore', {})
    ex_ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
             and (r.get('points') or 0) >= 1
             and (r.get('rail') or 0) >= 1
             and r.get('tblBtn') == 1           # the TABLES button is there
             and (r.get('rowsOff') or 0) == 0   # and the tables are off by default
             and r.get('call2') == 'OK'
             and (r.get('rowsOn') or 0) >= 1    # switching them on builds them
             and (r.get('pointsOn') or 0) >= 1  # and the chart still draws either way
             and r.get('screenBtns') == 3
             and (r.get('presets') or 0) >= 4   # the board's own COMPARE FOR bar
             and r.get('sheets') == 3           # FILTERS / VIEWS / AXES
             and r.get('sidebar') == 0          # the old control sidebar is gone here
             and (r.get('stage') or 0) >= 1     # the profit stage stays in view
             and (r.get('help') or 0) >= 1      # HOW TO READ is reachable from this screen
             and not r.get('hold'))
    line('explore', ex_ok, 'call=%s points=%s rail=%s rows=%s screenBtns=%s presets=%s '
         'sheets=%s sidebar=%s stage=%s help=%s tblBtn=%s rowsOff=%s rowsOn=%s hold=%s'
         % (r.get('call'), r.get('points'), r.get('rail'), r.get('rows'),
            r.get('screenBtns'), r.get('presets'), r.get('sheets'), r.get('sidebar'),
            r.get('stage'), r.get('help'), r.get('tblBtn'), r.get('rowsOff'),
            r.get('rowsOn'), r.get('hold')))
    if not ex_ok:
        if r.get('call') != 'OK':
            fail('explore: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('explore: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('explore: uncaught -- %s' % r['uncaught'][0][:200])
        if not (r.get('points') or 0) >= 1:
            fail('explore: the chart plotted no points - the hand-off to the studies '
                 'branch did not happen, or it drew an empty frame')
        if not (r.get('rail') or 0) >= 1:
            fail('explore: no strategy rail rendered')
        if r.get('tblBtn') != 1:
            fail('explore: the TABLES button is missing, so the study tables would be '
                 'unreachable on this screen')
        if (r.get('rowsOff') or 0) != 0:
            fail('explore: %s table rows built while the tables are off - the whole point is '
                 'that they are not assembled' % r.get('rowsOff'))
        if r.get('call2') != 'OK':
            fail('explore: turning the tables on threw -- %s' % str(r.get('call2'))[:300])
        if (r.get('rowsOn') or 0) < 1:
            fail('explore: turning the tables on produced no rows')
        if (r.get('pointsOn') or 0) < 1:
            fail('explore: the chart stopped drawing when the tables were turned on')
        if r.get('screenBtns') != 3:
            fail('explore: %s screen-switcher buttons, expected 3 - COMPARE BETA lost its '
                 'own strip on this screen' % r.get('screenBtns'))
        if not (r.get('presets') or 0) >= 4:
            fail('explore: the COMPARE FOR preset bar is missing (%s buttons)' % r.get('presets'))
        if not (r.get('help') or 0) >= 1:
            fail('explore: the HOW TO READ toggle is unreachable on this screen')
        if r.get('sheets') != 3:
            fail('explore: %s sheet buttons, expected 3' % r.get('sheets'))
        if r.get('sidebar'):
            fail('explore: the old control sidebar is still on this screen')
        if not (r.get('stage') or 0) >= 1:
            fail('explore: the profit stage picker is not in view - it must never be hidden')
        if r.get('hold'):
            fail('explore: still showing a placeholder card')

    # case 6: book
    r = cases.get('book', {})
    per = r.get('per') or {}
    mar, net, pf = (per.get('mar') or {}), (per.get('net') or {}), (per.get('pf') or {})
    fams = mar.get('fams') or []
    def _num(t):
        t = (t or '').strip().replace(',', '')
        neg = t.startswith('-')
        t = t.lstrip('-').lstrip('$')
        try:
            return -float(t) if neg else float(t)
        except Exception:
            return None
    book_ok = (r.get('call') == 'OK'
               and not any((per.get(k) or {}).get('errors') or (per.get(k) or {}).get('uncaught') for k in ('mar', 'net', 'pf'))
               and 'BOOKS' in fams and len(fams) >= 2
               and _num(mar.get('bookBig')) is not None            # MAR off book.lockbox.max_drawdown + lockbox_from
               and _num(net.get('bookBig')) == 70000.0             # dollars, NOT x20
               and _num(pf.get('bookBig')) == 1.4
               and 'BOOKS' in (mar.get('bookNm') or '')                # the row says BOOKS, not the first leg tag
               and (r.get('subRows') or 0) >= 1)
    line('book', book_ok, 'call=%s fams=%s MAR=%r NET=%r PF=%r subRows=%s'
         % (r.get('call'), fams, mar.get('bookBig'), net.get('bookBig'), pf.get('bookBig'), r.get('subRows')))
    if not book_ok:
        if r.get('call') != 'OK':
            fail('book: renderApp threw -- %s' % str(r.get('call'))[:300])
        for k in ('mar', 'net', 'pf'):
            p = per.get(k) or {}
            if p.get('errors'):
                fail('book: %s console.error -- %s' % (k, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('book: %s uncaught -- %s' % (k, p['uncaught'][0][:200]))
        if 'BOOKS' not in fams:
            fail('book: no BOOKS family row (fams=%s)' % fams)
        if len(fams) < 2:
            fail('book: the book swallowed the strategy row (fams=%s)' % fams)
        if _num(mar.get('bookBig')) is None:
            fail('book: MAR on LB is a dash for the book (got %r) - book.lockbox.max_drawdown / lockbox_from fallback broken' % mar.get('bookBig'))
        if _num(net.get('bookBig')) != 70000.0:
            fail('book: NET on LB is %r, expected $70,000 (a book must not take a second contract multiplier)' % net.get('bookBig'))
        if 'BOOKS' not in (mar.get('bookNm') or ''):
            fail('book: BOOKS row label is %r, expected it to say BOOKS' % mar.get('bookNm'))
        if _num(pf.get('bookBig')) != 1.4:
            fail('book: PF on LB is %r, expected 1.40' % pf.get('bookBig'))
        if (r.get('subRows') or 0) < 1:
            fail('book: BOOKS row pre-opened but no sub-row rendered')

    # case 7: compare (phase 3)
    r = cases.get('compare', {})
    per = r.get('per') or {}
    lb = per.get('lb') or {}
    stages_ok = all((per.get(k) or {}).get('call') == 'OK' for k in ('lb', 'is', 'wf', 'full'))
    errs_ok = not any((per.get(k) or {}).get('errors') or (per.get(k) or {}).get('uncaught')
                      for k in ('lb', 'is', 'wf', 'full'))
    # three picked runs: the fixture and its no-stored-drawdown twin each draw a solid
    # tuning stretch plus a dotted lockbox tail; the book draws nothing at all.
    cmp_ok = (r.get('call') == 'OK' and stages_ok and errs_ok
              and (lb.get('paths') or 0) >= 2
              and lb.get('host') == 1
              and (lb.get('keyRows') or 0) >= 1   # the live chart mounted
              and (lb.get('spot') or 0) >= 1      # and can reach the table columns
              and lb.get('expand') == 1           # the fullscreen explorer button exists
              and lb.get('badD') == 0               # no NaN / Infinity in any coordinate
              and lb.get('shortD') == 0             # every path actually draws a line
              and lb.get('chips') == 3              # one removable chip per picked run
              and lb.get('rm') == 3 and lb.get('clr') == 1
              and (lb.get('cols') or 0) >= 4        # blank corner + one column per run
              and (lb.get('rows') or 0) >= 15       # header + band captions + one row per measure
              and (lb.get('best') or 0) >= 5        # one per contested row that has a winner
              and (lb.get('apx') or 0) >= 1         # the curve-derived drawdown path ran at all
              and 'no equity curve' in (lb.get('note') or '')
              and 'under-state' in (lb.get('note') or '')
              # the walk-forward fold count must actually render - it was dead on arrival
              # once because the stage reader did not carry the counts at all
              and any('/' in c for c in ((lb.get('row') or {}).get('FOLDS HELD') or []))
              # a book's whole-run column must be its POOLED whole-run block, not its
              # pre-lockbox figure with the sealed year silently missing
              and '$320,000' in (((per.get('full') or {}).get('row') or {}).get('NET') or [])
              and r.get('emptyCall') == 'OK' and r.get('emptyHold') and r.get('emptyGo'))
    line('compare', cmp_ok,
         'call=%s paths=%s badD=%s shortD=%s chips=%s cols=%s rows=%s best=%s apx=%s rm=%s clr=%s '
         'empty=(%s,hold=%s,go=%s) stages=%s'
         % (r.get('call'), lb.get('paths'), lb.get('badD'), lb.get('shortD'), lb.get('chips'),
            lb.get('cols'), lb.get('rows'), lb.get('best'), lb.get('apx'), lb.get('rm'), lb.get('clr'),
            r.get('emptyCall'), r.get('emptyHold'),
            r.get('emptyGo'), {k: (per.get(k) or {}).get('call') for k in ('lb', 'is', 'wf', 'full')}))
    if not cmp_ok:
        for k in ('lb', 'is', 'wf', 'full'):
            p = per.get(k) or {}
            if p.get('call') != 'OK':
                fail('compare: %s stage threw -- %s' % (k, str(p.get('call'))[:300]))
            if p.get('errors'):
                fail('compare: %s console.error -- %s' % (k, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('compare: %s uncaught -- %s' % (k, p['uncaught'][0][:200]))
        if (lb.get('paths') or 0) < 2:
            fail('compare: the chart drew %s paths' % lb.get('paths'))
        if lb.get('host') != 1:
            fail('compare: the chart host is missing, so the live chart has nowhere to mount')
        if (lb.get('keyRows') or 0) < 1:
            fail('compare: the live chart did not mount - no key rows. The static fallback '
                 'may still be drawn, which is why the path count alone cannot catch this')
        if (lb.get('spot') or 0) < 1:
            fail('compare: the chart cannot reach the table - the spotlight looks inside one '
                 'named box and the table is not in it, so hovering a curve would lift the '
                 'curve and leave the columns alone')
        if lb.get('expand') != 1:
            fail('compare: the fullscreen explorer button is missing - and the chart '
                 'double-click looks for it, so its absence also breaks reset-zoom')
        if lb.get('badD'):
            fail('compare: %s overlay path(s) contain NaN / Infinity / undefined coordinates '
                 '- the chart would render blank' % lb.get('badD'))
        if lb.get('shortD'):
            fail('compare: %s overlay path(s) have no line segment at all' % lb.get('shortD'))
        if lb.get('chips') != 3:
            fail('compare: %s legend chips for 3 picked runs' % lb.get('chips'))
        if lb.get('rm') != 3 or lb.get('clr') != 1:
            fail('compare: remove/clear controls are rm=%s clr=%s, expected 3 and 1'
                 % (lb.get('rm'), lb.get('clr')))
        if (lb.get('cols') or 0) < 4:
            fail('compare: metric table has %s header cells, expected 4 (corner + 3 runs)'
                 % lb.get('cols'))
        if (lb.get('rows') or 0) < 15:
            fail('compare: metric table has %s rows, expected at least 15 (header, band captions, measures)'
                 % lb.get('rows'))
        if (lb.get('best') or 0) < 5:
            fail('compare: %s best-in-row marks, expected at least 5 (net, MAR, PF, EV R, R/YR, '
                 'drawdown - win rate, trades and years are not contests)' % lb.get('best'))
        if not (lb.get('apx') or 0) >= 1:
            fail('compare: no cell marked ~ - the run with no stored lockbox drawdown should '
                 'derive one from its saved curve and say so')
        if 'no equity curve' not in (lb.get('note') or ''):
            fail('compare: the note does not disclose the run with no curve (note=%r)'
                 % (lb.get('note') or '')[:180])
        if 'under-state' not in (lb.get('note') or ''):
            fail('compare: the note does not disclose that a derived drawdown under-states '
                 '(note=%r)' % (lb.get('note') or '')[:180])
        if not any('/' in c for c in ((lb.get('row') or {}).get('FOLDS HELD') or [])):
            fail('compare: FOLDS HELD renders no fold count on any run (%r) - the '
                 'walk-forward reader is not carrying held/n'
                 % ((lb.get('row') or {}).get('FOLDS HELD')))
        _fn = ((per.get('full') or {}).get('row') or {}).get('NET') or []
        if '$320,000' not in _fn:
            fail("compare: the book's whole-run NET is %r, expected $320,000 - falling back "
                 'to best_pnl_usd gives its PRE-LOCKBOX net under a column labelled end to '
                 'end' % _fn)
        if not (r.get('emptyCall') == 'OK' and r.get('emptyHold') and r.get('emptyGo')):
            fail('compare: empty state call=%s hold=%s leaderboard-link=%s'
                 % (r.get('emptyCall'), r.get('emptyHold'), r.get('emptyGo')))

    # case 8: runboard -- MAR must be ANNUALISED, i.e. (net / years) / drawdown.
    # The expectation is computed here from the fixture's own saved lockbox block, so it
    # tracks the fixture instead of being a number typed into the gate.
    r = cases.get('runboard', {})
    per = r.get('per') or {}
    lbc = per.get('lb') or {}
    want = None
    try:
        V = (fixture.get('validate') or {})
        lb = V.get('lockbox') or {}
        mult = float(fixture.get('multiplier') or 20)
        net = float(lb['pnl']) * mult
        ddv = abs(float(lb['dd'])) * mult
        d0 = datetime.datetime.strptime(str(lb['from'])[:10], '%Y-%m-%d')
        d1 = datetime.datetime.strptime(str(lb['to'])[:10], '%Y-%m-%d')
        yrs = (d1 - d0).days / 365.25
        want = '%.2f' % ((net / yrs) / ddv)
        naive = '%.2f' % (net / ddv)
    except Exception as e:
        want, naive = None, None
        print('  (runboard: could not derive the expected MAR from the fixture: %s)' % e)
    rb_ok = (r.get('call') == 'OK'
             and all((per.get(k) or {}).get('call') == 'OK' for k in ('lb', 'is', 'full'))
             and not any((per.get(k) or {}).get('uncaught') for k in ('lb', 'is', 'full'))
             and lbc.get('hasMarRow')
             and (want is None or lbc.get('mar') == want))
    line('runboard', rb_ok, 'lb MAR=%s (annualised=%s, net/dd would be %s) is=%s full=%s'
         % (lbc.get('mar'), want, naive,
            (per.get('is') or {}).get('mar'), (per.get('full') or {}).get('mar')))
    if not rb_ok:
        for k in ('lb', 'is', 'full'):
            p = per.get(k) or {}
            if p.get('call') != 'OK':
                fail('runboard: %s sample threw -- %s' % (k, str(p.get('call'))[:300]))
            if p.get('uncaught'):
                fail('runboard: %s uncaught -- %s' % (k, p['uncaught'][0][:200]))
        if not lbc.get('hasMarRow'):
            fail('runboard: no MAR row rendered on the lockbox sample')
        elif want is not None and lbc.get('mar') != want:
            fail('runboard: lockbox MAR reads %s, expected the ANNUALISED %s. %s is net over '
                 'drawdown with no years in it -- the whole point of this case.'
                 % (lbc.get('mar'), want,
                    ('That is exactly ' + str(naive) + ', which') if lbc.get('mar') == naive
                     else 'The app-wide definition since v73.460'))

    # case 9: hosted views
    r = cases.get('hosted', {})
    per = r.get('per') or {}
    hosted_ok = (r.get('call') == 'OK'
                 and all((per.get(v) or {}).get('call') == 'OK' for v in ('board', 'runs', 'fam', 'feat'))
                 and all(not (per.get(v) or {}).get('errors') and not (per.get(v) or {}).get('uncaught')
                         for v in ('board', 'runs', 'fam', 'feat'))
                 and all(((per.get(v) or {}).get('len') or 0) > 2000 for v in ('board', 'runs', 'fam', 'feat'))
                 and all((per.get(v) or {}).get('screenBtns') == 3 for v in ('board', 'runs', 'fam', 'feat'))
                 and all((per.get(v) or {}).get('viewBtns') == 6 for v in ('board', 'runs', 'fam', 'feat'))
                 and all(not (per.get(v) or {}).get('oldPills') for v in ('board', 'runs', 'fam', 'feat')))
    line('hosted', hosted_ok, ' '.join('%s=(call=%s len=%s scr=%s view=%s pills=%s)'
         % (v, (per.get(v) or {}).get('call'), (per.get(v) or {}).get('len'),
            (per.get(v) or {}).get('screenBtns'), (per.get(v) or {}).get('viewBtns'),
            (per.get(v) or {}).get('oldPills')) for v in ('board', 'runs', 'fam', 'feat')))
    if not hosted_ok:
        for v in ('board', 'runs', 'fam', 'feat'):
            p = per.get(v) or {}
            if p.get('call') != 'OK':
                fail('hosted: the %s view threw -- %s' % (v, str(p.get('call'))[:300]))
            if p.get('errors'):
                fail('hosted: %s console.error -- %s' % (v, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('hosted: %s uncaught -- %s' % (v, p['uncaught'][0][:200]))
            if (p.get('len') or 0) <= 2000:
                fail('hosted: the %s view rendered almost nothing (%s chars) - a feature that '
                     'is now only reachable here has gone missing' % (v, p.get('len')))
            if p.get('screenBtns') != 3 or p.get('viewBtns') != 6:
                fail('hosted: %s lost its navigation (screen=%s view=%s) - there would be no way '
                     'back out of it' % (v, p.get('screenBtns'), p.get('viewBtns')))
            if p.get('oldPills'):
                fail('hosted: %s still shows the old VIEW pills, which jump to a tab that is no '
                     'longer on the rail' % v)


    # case 10: books -- the old tab BOOKS tile, drawn natively on the new tab
    r = cases.get('books', {})
    per = r.get('per') or {}
    lbb, wfb = (per.get('lb') or {}), (per.get('wf') or {})
    books_ok = (r.get('call') == 'OK'
                and all((per.get(k) or {}).get('call') == 'OK' for k in ('lb', 'is', 'full', 'wf'))
                and not any((per.get(k) or {}).get('errors') or (per.get(k) or {}).get('uncaught')
                            for k in ('lb', 'is', 'full', 'wf'))
                and lbb.get('ths') == 10
                and (lbb.get('liveRows') or 0) >= 1
                and (lbb.get('statRows') or 0) >= 4
                and lbb.get('note') and not lbb.get('launcher')
                and (lbb.get('goRunboard') or 0) >= 2
                and (lbb.get('viewBtns') or 0) >= 6 and (lbb.get('booksBtn') or 0) >= 1
                and (wfb.get('ths') or 0) == 0
                and wfb.get('noWf') and wfb.get('hold')
                and (wfb.get('bodyRows') or 0) == 0)
    line('books', books_ok, 'lb=(call=%s th=%s live=%s static=%s note=%s launcher=%s go=%s view=%s) '
         'wf=(call=%s th=%s rows=%s explains=%s) is=%s full=%s'
         % (lbb.get('call'), lbb.get('ths'), lbb.get('liveRows'), lbb.get('statRows'),
            lbb.get('note'), lbb.get('launcher'), lbb.get('goRunboard'),
            str(lbb.get('viewBtns')) + '/books=' + str(lbb.get('booksBtn')),
            wfb.get('call'), wfb.get('ths'), wfb.get('bodyRows'), wfb.get('noWf'),
            (per.get('is') or {}).get('bodyRows'), (per.get('full') or {}).get('bodyRows')))
    if not books_ok:
        for k in ('lb', 'is', 'full', 'wf'):
            p = per.get(k) or {}
            if p.get('call') != 'OK':
                fail('books: the %s stage threw -- %s' % (k, str(p.get('call'))[:300]))
            if p.get('errors'):
                fail('books: %s console.error -- %s' % (k, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('books: %s uncaught -- %s' % (k, p['uncaught'][0][:200]))
        if lbb.get('ths') != 10:
            fail('books: the table has %s header cells, expected 10 (#, STRATEGY, VERSION, '
                 'NET, PF, MAX DD, MAR, TRADES, WF, VERDICT)' % lbb.get('ths'))
        if (lbb.get('liveRows') or 0) < 1:
            fail('books: no live book row rendered for a run that carries a book block - the '
                 'row source that matters most is dead')
        if (lbb.get('statRows') or 0) < 4:
            fail('books: %s offline rows rendered, expected the 4 hard-coded ones'
                 % lbb.get('statRows'))
        if not lbb.get('note'):
            fail('books: the provenance note under the table is missing')
        if lbb.get('launcher'):
            fail('books: the RUN A BOOK launcher was ported - it queues a real job and must '
                 'stay on the RUNBOARD view only')
        if (lbb.get('goRunboard') or 0) < 2:
            fail('books: no control pointing at the RUNBOARD view, so the launcher would be '
                 'unreachable from here')
        if (lbb.get('viewBtns') or 0) < 6 or (lbb.get('booksBtn') or 0) < 1:
            fail('books: the view strip reads %s buttons with %s BOOKS pill - the strip is '
                 'incomplete or BOOKS is not on it'
                 % (lbb.get('viewBtns'), lbb.get('booksBtn')))
        if (wfb.get('ths') or 0) != 0 or (wfb.get('bodyRows') or 0) != 0:
            fail('books: the walk-forward stage still draws a table (th=%s rows=%s). A book '
                 'pools its legs over one window and tunes nothing, so every cell would be '
                 'blank or invented' % (wfb.get('ths'), wfb.get('bodyRows')))
        if not (wfb.get('noWf') and wfb.get('hold')):
            fail('books: the walk-forward stage does not explain why there is nothing to show')

    if bad:
        print('CMP2 PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('CMP2 PROBE: PASS (VERSION=%s, %d cases)' % (data.get('VERSION'), len(cases)))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
