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
  gatewf           -- with the stage rail on WALK-FORWARD and return on capital across,
                       a GATE row must be ON the chart. Every gate row on the board was
                       off it at once because the gate row reported no walk-forward
                       figure; the engine saves one, and the two halves must still add
                       up to the pooled pre-lockbox figure.
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
N_CASES = 137

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
            +"window._starRuns=[];"
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
        // the study tables are built ON DEMAND here (measured around a dozen megabytes of
        //   markup with a full run history loaded, and were rebuilt on every click). Off by
        //   default; the button must bring them back, and the chart must be unaffected either
        //   way. F40 (audit3_report.md): the hover used to claim "about three and a half
        //   megabytes" - a re-measure on this build found the true cost close to 12 MB / ~73k
        //   elements, so the button's own hover text is checked here too, not just its count.
        r.tblBtn=d.querySelectorAll('[data-c2tbl]').length;
        r.tblBtnTitle=(d.querySelector('[data-c2tbl]')||{}).title||'';
        // the controls sheet renders as MENUS laid across, with the real buttons hidden
        //   behind them - and a menu must actually drive the button it stands for.
        doRender({c2Screen:'explore',resLvl:'sweep',c2Sheet:'filters'}, FIX_WIN);
        (function(){
          var host=d.querySelector('[data-remenus]');
          r.menuHost=!!host;
          r.menus=host?host.querySelectorAll('select').length:0;
          r.hiddenBoxes=host?[].filter.call(host.querySelectorAll('[data-regrpbtns]'),function(x){
            return x.style.display==='none';}).length:0;
          r.groups=host?host.querySelectorAll('[data-regrp]').length:0;
          // pick a menu, choose a different option, and see the preference move
          var sel=host?host.querySelector('select'):null;
          r.menuDrives=false;
          if(sel&&sel.options.length>1){
            var before=w.eval("JSON.stringify(JSON.parse(localStorage.getItem('augurPrefs')||'{}'))");
            var i2=(sel.selectedIndex===0)?1:0;
            sel.selectedIndex=i2;
            if(sel.onchange)sel.onchange();
            var after=w.eval("JSON.stringify(JSON.parse(localStorage.getItem('augurPrefs')||'{}'))");
            r.menuDrives=(before!==after);}
        })();
        r.rowsOff=d.querySelectorAll('tr[data-rerow]').length;
        var call2=doRender({c2Screen:'explore',resLvl:'sweep',c2Tbl:true}, FIX_WIN);
        r.call2=call2;
        r.rowsOn=d.querySelectorAll('tr[data-rerow]').length;
        r.pointsOn=d.querySelectorAll('[data-repoint]').length;
        // SIDE must really put the tables beside the chart, and the tables come FIRST.
        //   Measured on the page, because a layout can read correctly and still collapse.
        doRender({c2Screen:'explore',resLvl:'sweep',c2Tbl:true,resSplit:'side'}, FIX_WIN);
        (function(){
          var L=d.querySelector('[data-resplitl]');
          var sv=[].filter.call(d.querySelectorAll('svg'),function(x){return x.querySelector('[data-repoint]');})[0];
          r.splitCol=L?Math.round(L.getBoundingClientRect().width):0;
          r.splitChart=sv?Math.round(sv.getBoundingClientRect().width):0;
          r.splitLeftFirst=(L&&sv)?(L.getBoundingClientRect().left<sv.getBoundingClientRect().left):null;
          r.splitSameRow=(L&&sv)?(Math.abs(L.getBoundingClientRect().top-sv.getBoundingClientRect().top)<260):null;
        })();
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
            // F32 (2026-09-23) added a permanent sentence to this note (the chart drawdown
            //   tag is read off thinned curves on every stage, not only walk-forward), so the
            //   cap grew from 1400 to keep the later noCurve/apx disclosures within it.
            note:((d.querySelector('.c2-note')||{}).textContent||'').slice(0,2200),
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
        ['board','runs','feat'].forEach(function(v){
          var call=doRender({c2Screen:'cmp',c2View:v,cmpIds:[String(FIX.id)]}, FIX_WIN);
          var ap=d.getElementById('app');
          per[v]={call:call,
            len:ap?ap.innerHTML.length:-1,
            screenBtns:d.querySelectorAll('[data-c2screen]').length,
            viewBtns:d.querySelectorAll('[data-c2view]').length,
            oldPills:d.querySelectorAll('[data-cmpmode]').length,
            errors:sink.errors.slice(0,4),uncaught:sink.uncaught.slice(0,4)};
        });
        var ok=['board','runs','feat'].every(function(v){return per[v].call==='OK';});
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
            note:txt.indexOf('trades counted on exit date')>=0,
            launcher:txt.indexOf('RUN A BOOK')>=0,
            errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        });
        var ok=['lb','is','full','wf'].every(function(k){return per[k].call==='OK';});
        var r=snap('books', ok?'OK':'ERR');
        r.per=per;
      })();

      // ── TASK 1 case (RUNBOARD backlog item D, 2026-09-23): TRADES / YR,
      //    WORST MONTH and LONGEST FLAT STRETCH on the RUNBOARD 1E matrix (average $ per trade
      //    is the EV row already on the board, so it has no row of its own). The last two read
      //    the saved month-by-month P&L grid (top-level regime.monthly) via its own masked
      //    fetch (_hydrateRbMonthly), cached in window._rbMonthly - pre-seeding
      //    window._runFull lets this probe reach a resolved value with no Firebase sign-in
      //    (the fast whole-document cache path inside _hydrateRbMonthly). Every expected
      //    figure below is hand-computed from the seeded grid, so a wrong number fails here,
      //    not just a missing cell. A second run, a BOOK, proves the book-specific paths:
      //    WORST MONTH dashes (a book saves no regime block) and LONGEST FLAT STRETCH falls
      //    back to the book's own worst_stretch.trading_days, marked ~ and labelled DD span.
      (function(){
        var RID=String(+FIX.id+610000), BKID=String(+FIX.id+610500);
        var R=JSON.parse(JSON.stringify(FIX));
        R.id=RID;R.strategy='ZT1MONTHLY_1_0.py';R.starred=false;R.multiplier=1;
        R.date_from='2019-01-05';R.date_to='2022-01-05';
        R.best_pnl_usd=24500;R.best_dd_usd=5000;R.best_pf=1.3;R.best_trades=240;
        R.validate={verdict:'PASS',equity:[0,100,200,300,400],lb_idx:3,
          total_dd:-5000,total_sharpe:0.8,total_sortino:1.1,
          lockbox:{pnl:12500,pf:1.3,trades:60,pass:true},total_win_rate:45,total_avg_win:600,total_avg_loss:-400,
          // lite run data carries validate.windows (it is in RUNS_LITE_FIELDS), so the IS
          //   stretch reads its length from here exactly as the IS money rows do
          windows:{optimize:['2019-01-05','2021-03-05'],lockbox:['2021-03-05','2022-01-05']}};
        // 36 months, Jan 2019 - Dec 2021 (date_to is 2022-01-05, so January 2022 itself is
        //   outside every stage's own need-list and is deliberately left out of the grid).
        //   A steady $1,000/month climb, ONE bad month (July 2020, -$5,000) and five weak
        //   months after it (a peak at $18,000 in June 2020, a new high only in May 2021).
        var rows=[{year:2019,months:[1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000]},
                  {year:2020,months:[1000,1000,1000,1000,1000,1000,-5000,200,200,200,200,200]},
                  {year:2021,months:[1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000,1000]}];
        var FULLDOC=JSON.parse(JSON.stringify(R));
        FULLDOC.regime={monthly:{years:[2019,2020,2021],rows:rows}};
        FULLDOC.validate.windows={optimize:['2019-01-05','2021-03-05'],lockbox:['2021-03-05','2022-01-05']};
        // Review 2026-09-23: IS = the first 75% of the tuning window, 2019-01-05 to about
        //   2020-08-19, so Jan 2019 - Aug 2020: worst Jul '20, flat 2 mo (Jul, Aug). LB =
        //   Mar - Dec 2021: every month +$1k, worst Mar '21, flat 0 mo.
        // A second run whose grid STOPS at March 2021, April - December blank: the shape of a
        //   grid built over the tuning window only. Those blanks were never recorded, so they
        //   must not read as $0 months: FULL covers 27 of 36 months (~, worst Jul '20, flat
        //   ~9 mo - the first build read 18), LB covers 1 of 10 and dashes (the first build
        //   printed $0 Apr '21 and a 9 mo flat stretch).
        var PID=String(+FIX.id+610250);
        var P=JSON.parse(JSON.stringify(R));P.id=PID;P.strategy='ZT1PARTIAL_1_0.py';
        var prow=JSON.parse(JSON.stringify(rows));
        prow[2]={year:2021,months:[1000,1000,1000,null,null,null,null,null,null,null,null,null]};
        var PFULL=JSON.parse(JSON.stringify(FULLDOC));PFULL.id=PID;PFULL.strategy='ZT1PARTIAL_1_0.py';
        PFULL.regime={monthly:{years:[2019,2020,2021],rows:prow}};
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=BKID;BK.strategy='BOOK: T1 probe';BK.starred=false;BK.multiplier=1;
        BK.date_from='2019-01-05';BK.date_to='2022-01-05';
        BK.book={name:'T1 PROBE BOOK',legs:[{strategy:'AAA_1_0.py',weight:1},{strategy:'BBB_1_0.py',weight:1}],
          whole:{total_pnl:30000,max_drawdown:6000,num_trades:300,profit_factor:1.3},
          pre_lockbox:{total_pnl:24000,max_drawdown:6000,num_trades:250},
          lockbox:{total_pnl:6000,num_trades:50,win_rate:44,profit_factor:1.2,max_drawdown:3000},
          worst_stretch:{from:'2020-06-01',to:'2020-07-15',depth:6000,trading_days:42},
          // its own lockbox stretch (review 2026-09-23): LB reads THIS one, ~0.7 mo
          worst_stretch_lockbox:{from:'2021-03-01',to:'2021-03-20',depth:3000,trading_days:14},
          lockbox_from:'2021-01-05',date_from:'2019-01-05',date_to:'2022-01-05'};
        BK.validate={verdict:'PASS',lockbox:{pnl:6000,pf:1.2,trades:50,pass:true},book:true};
        var wc="var F="+JSON.stringify(R)+";var FD="+JSON.stringify(FULLDOC)+";var B="+JSON.stringify(BK)+";"
          +"var P="+JSON.stringify(P)+";var PD="+JSON.stringify(PFULL)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"var doc=f(F),pdoc=f(P),bdoc=f(B);runHistory=[doc,pdoc,bdoc];window._runFull={};"
          +"window._runFull[String(doc.id)]=f(FD);window._runFull[String(pdoc.id)]=f(PD);"
          +"window._rbMonthly={};window._rbMonthlyBusy={};window._rbMonthlyQ=[];"
          +"window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        function rowsOf(){var o={};
          [].forEach.call(d.querySelectorAll('#rb-mtx-box table tr'),function(tr){
            var c=tr.children;if(c.length<2)return;
            var lab=(c[0].textContent||'').trim();if(!lab)return;
            o[lab]=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
          return o;}
        var per={};
        ['full','is','lb'].forEach(function(smp){
          var call=doRender({cmpMode:'board',rbSample:smp,rbRank:'mar',cmpIds:[RID,PID,BKID]}, wc, 'cmp');
          per[smp]={call:call,row:rowsOf(),errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        });
        // WALK-FORWARD (review 2026-09-23): only the board hosted in COMPARE reaches this stage (the
        //   stand-alone board's own sample control stops at full / is / lb), and that hosted board is
        //   the one the owner uses - so this render goes through it, picked runs, stage WF.
        (function(){
          var call=doRender({c2Screen:'cmp',c2View:'board',c2Src:'pick',c2Stage:'wf',cmpIds:[RID,PID,BKID]}, wc);
          per.wf={call:call,row:rowsOf(),errors:sink.errors.slice(0,5),uncaught:sink.uncaught.slice(0,5)};
        })();
        var ok=['full','is','lb','wf'].every(function(k){return per[k].call==='OK';});
        var r=snap('task1rb', ok?'OK':'ERR');
        r.per=per;
        r.full=(per.full.row['WORST MONTH']||[]).concat(per.full.row['LONGEST FLAT STRETCH']||[])
          .concat(per.full.row['TRADES / YR']||[]);
      })();

      // ── F41 case (audit3_report.md, 2026-09-23): an old or hand-edited saved pick list
      //    (APREF.cmpIds) or saved set (APREF.cmpSets) in the wrong shape used to throw
      //    inside the shared render path - .map()/.filter() on a non-array truthy value -
      //    blanking RUNBOARD, PICK RUNS and FEATURES on every visit. Three malformed shapes
      //    at once: cmpIds saved as a bare object, and cmpSets holding a null entry and an
      //    entry whose own .ids is a string instead of an array. Driven through the same
      //    augurPrefs JSON channel every other case in this file uses - APREF itself lives
      //    inside the app's own closure (not reachable from this outer page), so it can only
      //    be shaped by what renderApp() reads back out of localStorage, never poked directly.
      (function(){
        var per={};
        ['board','runs','feat'].forEach(function(v){
          var badPrefs={c2Screen:'cmp',c2View:v,cmpIds:{bad:1},cmpSets:[null,{name:'ok'},{name:'bad',ids:'nope'}]};
          var call=w.eval("(function(){try{"
            +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(badPrefs))+");"
            +"runHistory=window.__runs||[];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();window._starRuns=[];"
            +"activeTab='augur';augurSub='cmp2';augurRunSel=null;renderApp();return 'OK';"
            +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
          var ap=d.getElementById('app');
          per[v]={call:call,len:ap?ap.innerHTML.length:-1,errors:sink.errors.slice(0,4),uncaught:sink.uncaught.slice(0,4)};
        });
        var ok=['board','runs','feat'].every(function(v){return per[v].call==='OK';});
        var r=snap('f41badshape', ok?'OK':'ERR');
        r.per=per;
      })();

      // ── case 11: top runs ───────────────────────────────
      //    The leaderboard shows champions; this panel ranks individual runs. Two runs with
      //    different figures must come out in OPPOSITE order under BEST and WORST, which is
      //    the one thing a row count cannot check.
      (function(){
        var A=JSON.parse(JSON.stringify(FIX));
        var B=JSON.parse(JSON.stringify(FIX));
        B.id=String(+FIX.id+700000);B.starred=false;
        // make B clearly the better run on the lockbox read
        if(B.validate&&B.validate.lockbox){B.validate.lockbox.pnl=(+FIX.validate.lockbox.pnl||0)*4+1000;
          B.validate.lockbox.pf=(+FIX.validate.lockbox.pf||1)+0.6;}
        var wc="var A="+JSON.stringify(A)+";var B="+JSON.stringify(B)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(A),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var per={};
        ['best','worst'].forEach(function(k){
          var call=doRender({c2Screen:'lead',c2Stage:'lb',c2Rank:'net',c2Top:k}, wc);
          var rows=[].slice.call(d.querySelectorAll('.c2-card .c2-row.sub[data-c2run]'));
          per[k]={call:call,tabs:d.querySelectorAll('[data-c2top]').length,
            n:rows.length,
            first:rows.length?rows[0].getAttribute('data-c2run'):null,
            errors:sink.errors.slice(0,4),uncaught:sink.uncaught.slice(0,4)};
        });
        var off=doRender({c2Screen:'lead',c2Stage:'lb',c2Rank:'net'}, wc);
        var r=snap('toprun',(per.best.call==='OK'&&per.worst.call==='OK'&&off==='OK')?'OK':'ERR');
        r.per=per;r.offCall=off;r.offRows=d.querySelectorAll('.c2-card .c2-row.sub[data-c2run]').length;
        r.betterId=String(+FIX.id+700000);
      })();


      // ── case 12: champions source ───────────────────────
      //    CHAMPIONS must name the SAME run the leaderboard names, because they now read one
      //    rule. Two runs of one strategy, one clearly better: the overlay must show exactly
      //    one chip, it must be that run, and it must match the leaderboard's champion.
      (function(){
        var A=JSON.parse(JSON.stringify(FIX));
        var B=JSON.parse(JSON.stringify(FIX));
        B.id=String(+FIX.id+600000);B.starred=true;   // your crown wins first
        var wc="var A="+JSON.stringify(A)+";var B="+JSON.stringify(B)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(A),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'champ',c2Stage:'lb',cmpIds:[]}, wc);
        var r=snap('champions', call);
        r.chips=d.querySelectorAll('.c2-lg').length;
        r.rm=d.querySelectorAll('[data-c2rm]').length;
        r.clr=d.querySelectorAll('[data-c2clr]').length;
        r.srcBtns=d.querySelectorAll('[data-c2src]').length;
        r.ids=[].map.call(d.querySelectorAll('.c2-card table th'),function(x){
          var m=(x.textContent||'').match(/#([0-9]+)/);return m?m[1]:null;}).filter(Boolean);
        // and the leaderboard's champion for the same history
        doRender({c2Screen:'lead',c2Stage:'lb'}, wc);
        var sub=d.querySelector('.c2-row[data-c2fam]');
        r.leadChamp=sub?((sub.textContent||'').match(/#([0-9]+)/)||[])[1]:null;
        r.expect=String(+FIX.id+600000);
      })();


      // ── case 13: the SETS sheet on the overlay, and the BOOK launcher on BOOKS ───
      //    Both are things that MOVED off a hosted view. The sheet must open on the
      //    overlay with real tab and set controls, must be gone under CHAMPIONS (that
      //    list refills itself, so a tab of it could never be saved), and the launcher
      //    must be present AND WIRED on BOOKS. [data-booknew] is counted rather than the
      //    words RUN A BOOK, and the panel it opens is opened for real, because a dead
      //    button and a button with no handler both read as a working screen otherwise.
      (function(){
        var picks=[String(FIX.id)];
        var base={c2Screen:'cmp',c2View:'ovl',c2Stage:'lb',cmpIds:picks,
                  cmpTabs:[picks,[]],cmpTabN:0,cmpSets:[{name:'probe set',ids:picks}]};
        function P(extra){var o={};for(var k in base)o[k]=base[k];for(var k2 in extra)o[k2]=extra[k2];return o;}
        var errs=[],unc=[];
        function keep(){errs=errs.concat(sink.errors);unc=unc.concat(sink.uncaught);}

        var openCall=doRender(P({c2Src:'pick',c2Sheet:'sets'}), FIX_WIN);
        var r=snap('sets', openCall); keep();
        r.openBtn=d.querySelectorAll('[data-c2sheet=sets]').length;
        r.tabs=d.querySelectorAll('[data-cmptab]').length;
        r.tabNew=d.querySelectorAll('[data-cmptabnew]').length;
        r.tabDel=d.querySelectorAll('[data-cmptabdel]').length;
        r.setChips=d.querySelectorAll('[data-cmpset]').length;
        r.setSave=d.querySelectorAll('[data-cmpsetsave]').length;
        r.setRen=d.querySelectorAll('[data-cmpsetren]').length;
        r.setDel=d.querySelectorAll('[data-cmpsetdel]').length;
        // the tab chips and the save control must be WIRED, not just drawn
        r.tabWired=(function(){var x=d.querySelector('[data-cmptab]');return !!(x&&typeof x.onclick==='function');})();
        r.saveWired=(function(){var x=d.querySelector('[data-cmpsetsave]');return !!(x&&typeof x.onclick==='function');})();

        // closed: the opener is still there, the sheet body is not
        r.shutCall=doRender(P({c2Src:'pick'}), FIX_WIN); keep();
        r.shutBtn=d.querySelectorAll('[data-c2sheet=sets]').length;
        r.shutTabs=d.querySelectorAll('[data-cmptab]').length;
        r.shutSave=d.querySelectorAll('[data-cmpsetsave]').length;

        // CHAMPIONS: nothing at all, and a line saying so
        r.champCall=doRender(P({c2Src:'champ',c2Sheet:'sets'}), FIX_WIN); keep();
        r.champBtn=d.querySelectorAll('[data-c2sheet=sets]').length;
        r.champTabs=d.querySelectorAll('[data-cmptab]').length;
        r.champSave=d.querySelectorAll('[data-cmpsetsave]').length;
        r.champSets=d.querySelectorAll('[data-cmpset]').length;
        r.champSays=((d.body&&(d.body.innerText||d.body.textContent))||'')
          .indexOf('TABS AND SETS ARE FOR PICKED RUNS ONLY')>=0;

        // nothing picked at all: this is the state you land in after CLEAR, and switching
        //   to a tab that HAS runs is the only way back, so the sheet must survive it.
        r.mtCall=doRender(P({c2Src:'pick',c2Sheet:'sets',cmpIds:[]}), FIX_WIN); keep();
        r.mtBtn=d.querySelectorAll('[data-c2sheet=sets]').length;
        r.mtTabs=d.querySelectorAll('[data-cmptab]').length;
        r.mtSave=d.querySelectorAll('[data-cmpsetsave]').length;
        r.mtSets=d.querySelectorAll('[data-cmpset]').length;
        r.mtWired=(function(){var x=d.querySelector('[data-cmptab]');return !!(x&&typeof x.onclick==='function');})();
        r.mtHold=!!d.querySelector('.c2-hold');

        // the launcher on the native BOOKS view
        r.bkCall=doRender({c2Screen:'cmp',c2View:'books',c2Stage:'lb',cmpIds:picks}, FIX_WIN); keep();
        r.bkBtn=d.querySelectorAll('[data-booknew]').length;
        r.bkWired=(function(){var b=d.querySelector('[data-booknew]');return !!(b&&typeof b.onclick==='function');})();
        r.bkOldLine=((d.body&&(d.body.innerText||d.body.textContent))||'').indexOf('lives on the RUNBOARD view')>=0;
        // open the panel for real. alert() is stubbed so an empty leg pool reports as a
        //   reading instead of hanging or silently doing nothing.
        r.bkAlert=null;r.bkModal=null;
        var oldAlert=w.alert;
        try{
          w.alert=function(m){r.bkAlert=String(m);};
          var b2=d.querySelector('[data-booknew]');
          if(b2&&b2.onclick){
            b2.onclick();
            r.bkModal={legs:d.querySelectorAll('[data-bkleg]').length,
                       from:d.querySelectorAll('[data-bkfrom]').length,
                       to:d.querySelectorAll('[data-bkto]').length,
                       lb:d.querySelectorAll('[data-bklb]').length,
                       nm:d.querySelectorAll('[data-bkname]').length,
                       win:d.querySelectorAll('[data-bkwin]').length,
                       run:d.querySelectorAll('[data-bkrun]').length,
                       cancel:d.querySelectorAll('[data-bkcancel]').length};
            var cx=d.querySelector('[data-bkcancel]');if(cx&&cx.onclick)cx.onclick();
            r.bkModalGone=d.querySelectorAll('[data-bkrun]').length===0;
          }
        }catch(e){r.bkModalErr=String(e&&e.message||e);}
        try{w.alert=oldAlert;}catch(_e){}
        keep();
        r.errors=errs.slice(0,8);r.uncaught=unc.slice(0,8);
      })();

      // -- case 14: a gate row is plottable on the WALK-FORWARD stage ---------------
      //    Every gate row on the board was off the chart at once - 600 of them, the same
      //    40 on each of 15 runs - because the gate row reported no walk-forward figure at
      //    all. No profit for the ticked stretch means no MAR and no return on capital, so
      //    nothing to plot and two dashes in the table. The engine does save the slice, so
      //    this pins it: with the stage rail on WALK-FORWARD and return on capital across,
      //    a GATE point must be ON the chart, and the two halves must still add up to the
      //    pooled pre-lockbox figure they came from.
      (function(){
        var blk=function(p,dd,n){return {total_pnl:p,max_drawdown:dd,num_trades:n,
          profit_factor:1.5,win_rate:0.4,sharpe:1.2,sortino:2.1,avg_pnl:(p/n),avg_loss:-100};};
        var cand={model:'logistic',threshold:0.5,eligible:true,
          pre_pnl:10000,pre_rec:4,pre_pf:1.5,pre_wr:0.4,kept_pre:100,
          pre_sharpe:1.2,pre_sortino:2.1,
          is_rng:blk(1000,-300,20),wf_rng:blk(9000,-500,80),
          lockbox:blk(2000,-200,25),full:blk(12000,-600,125),wf_lb:blk(11000,-550,105)};
        var GV={span:['2010-01-04','2026-01-02'],wf_range:['2016-01-04','2025-01-02'],
          lockbox_from:'2025-01-02',candidates:[cand],chosen:{model:'logistic',threshold:0.5},
          tilts:[],hybrids:[],gates:[],windows:{}};
        // the configurations are read out of the CONFIGS-ONLY document, so seed that
        var wc=FIX_WIN+'doc.gate_validate='+JSON.stringify(GV)+';runHistory=[doc];'
          +'window._runCfg={};window._runCfg[String(doc.id)]=doc;';
        var call=doRender({c2Screen:'explore',resLvl:'valid',resShow:'configs',
                           resCfgRun:[String(FIX.id)],
                           resSegs:['wf'],resXAxis:'roc',resMarks:'dot',
                           c2Tbl:true}, wc);
        var r=snap('gatewf', call);
        // A GATE POINT, not just any point: the hover text names the family, and it is the
        //   gate rows specifically that were missing.
        var pts=[].slice.call(d.querySelectorAll('[data-repoint]'));
        r.points=pts.length;
        r.gatePoints=pts.filter(function(g){
          var t=g.querySelector('title');return !!(t&&(t.textContent||'').indexOf('GATE')>=0);}).length;
        r.skipN=w._reSkipN; r.shownN=w._reShownN;
        // and the table row must carry real figures where it used to carry two dashes
        var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').trim();});
        var iMar=-1,iRoc=-1;
        hdr.forEach(function(h,i2){if(h.indexOf('MAR')===0&&iMar<0)iMar=i2;
                                   if(h.indexOf('ROC')===0&&iRoc<0)iRoc=i2;});
        var gtr=[].slice.call(d.querySelectorAll('tr[data-rerow]')).filter(function(tr){
          return (tr.textContent||'').indexOf('GATE')>=0;})[0]||null;
        var cell=function(i2){return (gtr&&i2>=0&&gtr.cells[i2])?(gtr.cells[i2].textContent||'').trim():null;};
        r.gateMar=cell(iMar); r.gateRoc=cell(iRoc);
        // RUN and TRADES / YR (v73.758): both headed, every body row as wide as its heading,
        //   and TRADES / YR agreeing with R / YR - they share one count and one window.
        var ix=function(name){for(var q=0;q<hdr.length;q++){if(hdr[q].replace(/[^A-Z /%$]/g,'').trim()===name)return q;}return -1;};
        r.iRun=ix('RUN'); r.iTpy=ix('TRADES / YR');
        r.thN=gtr?gtr.closest('table').querySelectorAll('tr th').length:null;
        r.tdBad=[].slice.call(d.querySelectorAll('tr[data-rerow]')).filter(function(tr){return tr.cells.length!==r.thN;}).length;
        r.gateRun=cell(r.iRun); r.gateTpy=cell(r.iTpy);
        r.gateEvr=cell(ix('EV R')); r.gateRpy=cell(ix('R / YR'));
        r.runSortable=!!d.querySelector('th[data-resort="run"]');
        r.tpySortable=!!d.querySelector('th[data-resort="tpy"]');
        r.expectRun='#'+String(FIX.id);
        // IN-SAMPLE + LOCKBOX is the one stage pair with no saved block of its own. It used to
        //   print the whole-run count (125) over a window that still held the unticked
        //   walk-forward years (16); it must read 20+25=45 trades over 6+1=7 years = 6.4 a year.
        //   All three ticked must be unchanged: 125 over the 16-year span = 7.8.
        function stageRead(segs){
          doRender({c2Screen:'explore',resLvl:'valid',resShow:'configs',resCfgRun:[String(FIX.id)],
                    resSegs:segs,resXAxis:'roc',resMarks:'dot',c2Tbl:true}, wc);
          var h2=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$]/g,'').trim();});
          var g2=[].slice.call(d.querySelectorAll('tr[data-rerow]')).filter(function(tr){return (tr.textContent||'').indexOf('GATE')>=0;})[0];
          var at=function(n){var q=h2.indexOf(n);return (g2&&q>=0&&g2.cells[q])?(g2.cells[q].textContent||'').trim():null;};
          return {trd:at('TRADES'),tpy:at('TRADES / YR'),ppt:at('$/TRD')};}
        r.isLb=stageRead(['is','lb']); r.allSeg=stageRead(['is','wf','lb']);
        r.wfOnly=stageRead(['wf']);
        // AXIS PARITY (v73.759): both pickers list the same twelve measures in one risk-to-reward
        //   order, and every pairing that is new draws the gate point rather than an empty chart.
        function axisPts(y,x){
          var c=doRender({c2Screen:'explore',resLvl:'valid',resShow:'configs',resCfgRun:[String(FIX.id)],
                          resSegs:['wf'],resAxis:y,resXAxis:x,resMarks:'dot'}, wc);
          var n=[].slice.call(d.querySelectorAll('[data-repoint]')).filter(function(g){
            var t=g.querySelector('title');return !!(t&&(t.textContent||'').indexOf('GATE')>=0);}).length;
          return c==='OK'?n:('ERR '+c).slice(0,160);}
        r.axOrdY=[].map.call(d.querySelectorAll('[data-resaxis]'),function(b){return b.getAttribute('data-resaxis');});
        r.axOrdX=[].map.call(d.querySelectorAll('[data-resxaxis]'),function(b){return b.getAttribute('data-resxaxis');});
        r.axNew={ydd:axisPts('dd','so'),xraw:axisPts('evr','raw'),xmar:axisPts('evr','ratio'),xev:axisPts('evr','ppt'),ywr:axisPts('wr','so'),xwr:axisPts('evr','wr')};
        // and the ALL layout, which lost its old grey RUN column as well as gaining two
        r.allCall=doRender({c2Screen:'explore',resLvl:'valid',resShow:'configs',resCfgRun:[String(FIX.id)],
                            resSegs:['wf'],resXAxis:'roc',resMarks:'dot',c2Tbl:true,resCols:'all'}, wc);
        (function(){var t=d.querySelector('tr[data-rerow]');var tb=t?t.closest('table'):null;
          var th=tb?tb.querySelectorAll('tr th').length:null;
          r.allTh=th; r.allBad=[].slice.call(d.querySelectorAll('tr[data-rerow]')).filter(function(x){return x.cells.length!==th;}).length;
          r.allRunHeads=tb?[].filter.call(tb.querySelectorAll('tr th'),function(h){return (h.textContent||'').replace(/[^A-Z ]/g,'').trim()==='RUN';}).length:null;})();
        r.hasGateRow=!!gtr;
        r.sums=(cand.is_rng.total_pnl+cand.wf_rng.total_pnl)===cand.pre_pnl;
      })();

      // -- case crowns: which book is champion, and which runs COMPARE is reading --------
      //    Three books. KNOB carries the most money AND the best pre-lockbox net/DD but is a
      //    labelled KNOB TEST, so it must never be champion unless starred. BEST has the best
      //    net/DD of the rest but LESS money than RICH, so a money order would pick RICH - the
      //    fault that crowned #378. Then RICH is starred and must win, saying your crown.
      (function(){
        function mk(id,name,pnl,dd,best){var B=JSON.parse(JSON.stringify(FIX));
          B.id=String(id);B.strategy='BOOK '+name;B.starred=false;B.best_pnl_usd=best;B.best_dd_usd=dd;B.multiplier=1;
          B.book={name:name,legs:[{strategy:FIX.strategy,weight:1}],whole:{total_pnl:pnl+10000,max_drawdown:dd},
            pre_lockbox:{total_pnl:pnl,max_drawdown:dd},lockbox:{total_pnl:10000,num_trades:100,win_rate:40,profit_factor:1.3,max_drawdown:5000},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:10000,pf:1.3,trades:100,pass:true},book:true};return B;}
        var KNOB=mk(910001,'SQUEEZE x4 KNOB TEST',900000,10000,900000);   // 90 net/DD, most money
        var RICH=mk(910002,'RICH',600000,20000,800000);                    // 30 net/DD
        var BEST=mk(910003,'BEST',500000,10000,500000);                    // 50 net/DD
        var pre='var norm=function(o){return (typeof _bookUnitsOnRead==="function"&&typeof _isoTs==="function")?_bookUnitsOnRead(_isoTs(o)):o;};'
          +'window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();';
        function hist(star){var a=JSON.parse(JSON.stringify([FIX,KNOB,RICH,BEST]));if(star)a[2].starred=true;
          return pre+'runHistory='+JSON.stringify(a)+'.map(norm);';}
        function bookWho(){var row=[].filter.call(d.querySelectorAll('.c2-row[data-c2fam]'),function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'')==='BOOKS';})[0];
          var w2=row?row.querySelector('.c2-who'):null;return w2?(w2.textContent||'').replace(/ +/g,' ').trim():null;}
        var c1=doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'lb'}, hist(false));
        var r=snap('crowns', c1);
        r.unstarred=bookWho();
        r.starCall=doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'lb'}, hist(true));
        r.starred=bookWho();
        // the run window: not capped (4 runs, limit 75) says ALL; capped says NEWEST with two wired loaders
        r.allCall=doRender({c2Screen:'lead'}, hist(false));
        r.allTxt=(function(){var t=d.body.innerText||'';var m=t.match(/(ALL|NEWEST) [0-9]+ RUNS/);return m?m[0]:null;})();
        r.allBtns=d.querySelectorAll('[data-c2loadruns]').length;
        var saved=w.eval('runsLimit');
        r.capped={};
        [['lead',null],['cmp','ovl'],['cmp','board'],['explore',null]].forEach(function(v){
          var p={c2Screen:v[0]};if(v[1])p.c2View=v[1];
          var c=doRender(p, hist(false)+'runsLimit=3;');
          var bs=d.querySelectorAll('[data-c2loadruns]');
          var txt=(d.body.innerText||'').match(/NEWEST [0-9]+ RUNS/);
          r.capped[v.join('/')]={call:c,txt:txt?txt[0]:null,btns:bs.length,
            wired:[].every.call(bs,function(b){return typeof b.onclick==='function';})};});
        w.eval('runsLimit='+saved+';');
      })();
      // -- case runstages: a RUN row follows the ticked stretch -----------------------------
      (function(){
        var R=JSON.parse(JSON.stringify(FIX));
        R.validate.windows=R.validate.windows||{};R.validate.windows.wf_split='2016-06-01';
        var V=R.validate,Lk=V.lockbox,fl=(R.top10_results||[]).filter(function(z){return z&&z.fold!=null;});
        var T=+V.total_trades,Wt=T*(+V.total_win_rate)/100;
        var wfT=0,wfW=0,wfGW=0,wfGL=0;fl.forEach(function(z){wfT+=(+z.oos_trades||0);wfW+=(+z.oos_wins||0);
          var pf=+z.oos_pf,p=+z.oos_pnl,g=Math.abs(p/(pf-1));wfGL+=g;wfGW+=pf*g;});
        var lT=+Lk.trades,lW=lT*(+Lk.win_rate)/100,lGW=(+Lk.avg_win)*lW,lGL=Math.abs(+Lk.avg_loss)*(lT-lW);
        var tGW=(+V.total_avg_win)*Wt,tGL=Math.abs(+V.total_avg_loss)*(T-Wt);
        var gvIs=(R.gate_validate&&R.gate_validate.ungated_is)||{};
        var isT=+gvIs.num_trades||0;
        var exp={wf:{pf:(wfGW/wfGL).toFixed(2),wr:Math.round(100*wfW/wfT)+'%',trd:wfT},
                 lb:{pf:(lGW/lGL).toFixed(2),wr:Math.round(+Lk.win_rate)+'%',trd:lT},
                 is:{pf:(+gvIs.profit_factor).toFixed(2),trd:isT},
                 all:{pf:(tGW/tGL).toFixed(2),trd:T},islb:{trd:isT+lT}};
        var wc='var F='+JSON.stringify(R)+';runHistory=[F];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();';
        function read(segs){
          var c=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:segs,resAxis:'evr',resXAxis:'so',c2Tbl:true}, wc);
          var h=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()]/g,'').trim();});
          var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(x){return (x.textContent||'').indexOf('#'+FIX.id)>=0;})[0];
          var at=function(nm){var q=h.indexOf(nm);return (tr&&q>=0&&tr.cells[q])?(tr.cells[q].textContent||'').trim():null;};
          return {call:c,row:!!tr,pf:at('PF'),wr:at('WIN %'),trd:at('TRADES'),sh:at('SHARPE'),mar:at('MAR'),so:at('SORTINO'),evr:at('EV R'),rpy:at('R / YR')};}
        var r=snap('runstages','OK');
        r.exp=exp;
        r.wf=read(['wf']);r.lb=read(['lb']);r.is=read(['is']);r.all=read(['is','wf','lb']);r.islb=read(['is','lb']);r.pre=read(['is','wf']);
        // MISSING SLICE: a run whose gate study never saved its ungated in-sample slice must
        //   dash IN-SAMPLE - never fall back to a whole-run-minus-the-rest remainder. WALK-FORWARD,
        //   LOCKBOX and ALL THREE (the run's own whole-run totals, not the IS split) are unaffected.
        var good=wc;
        var Rb=JSON.parse(JSON.stringify(R));delete Rb.gate_validate.ungated_is;
        wc='var F='+JSON.stringify(Rb)+';runHistory=[F];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();';
        r.badIs=read(['is']);r.badIsWf=read(['is','wf']);r.badAll=read(['is','wf','lb']);
        wc=good;
      })();
      // -- case fixes346 -------------------------------------------------------------------
      (function(){
        var r=snap('fixes346','OK');
        // (6) RUNBOARD whole-run MAR from the SAVED whole-run drawdown
        var V=FIX.validate,mult=+FIX.multiplier||20,eq=V.equity||[];
        var yrs=(Date.parse(String(FIX.date_to).slice(0,10))-Date.parse(String(FIX.date_from).slice(0,10)))/86400000/365.25;
        r.rbWant=((((+eq[eq.length-1])*mult)/yrs)/(Math.abs(+V.total_dd)*mult)).toFixed(2);
        function rbRead(win){doRender({cmpMode:'board',rbSample:'full',rbRank:'mar',cmpIds:[String(FIX.id)]}, win, 'cmp');
          var o={mar:null,dd:null,marBold:false};
          [].forEach.call(d.querySelectorAll('tr'),function(tr){var c=[].map.call(tr.children,function(td){return (td.textContent||'').trim();});
            if(c[0]==='MAR'&&o.mar===null){o.mar=c[1]||null;o.marBold=!!(tr.children[1]&&tr.children[1].querySelector('b'));}
            if(c[0]==='DD'&&o.dd===null)o.dd=c[1]||null;});return o;}
        r.rbSaved=rbRead(FIX_WIN);
        var NF=JSON.parse(JSON.stringify(FIX));delete NF.validate.total_dd;
        r.rbCurve=rbRead('var F='+JSON.stringify(NF)+';runHistory=[F];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();');
        // (3) + (4) on EXPLORE configs: a gate for the MAR axis, a hybrid for per-stretch sizing
        var blk=function(p,dd,n){return {total_pnl:p,max_drawdown:dd,num_trades:n,profit_factor:1.5,win_rate:40,sharpe:1.2,sortino:2.1,avg_pnl:(p/n),avg_loss:-10};};
        var cand={model:'logistic',threshold:0.5,eligible:true,pre_pnl:10000,pre_rec:4,pre_pf:1.5,pre_wr:0.4,kept_pre:100,pre_sharpe:1.2,pre_sortino:2.1,
          is_rng:blk(1000,-300,20),wf_rng:blk(9000,-500,80),lockbox:blk(2000,-200,25),full:blk(12000,-600,125),wf_lb:blk(11000,-550,105)};
        var H={model:'xgb',n_trades:200,is_rng:blk(500,-100,40),wf_rng:blk(1000,-200,50),lockbox:blk(1500,-300,110),full:blk(3000,-400,200),
          pre:blk(1500,-250,90),wf_lb:blk(2500,-350,160)};
        var GV={span:['2010-01-04','2026-01-02'],wf_range:['2016-01-04','2025-01-02'],lockbox_from:'2025-01-02',candidates:[cand],
          chosen:{model:'logistic',threshold:0.5},tilts:[],hybrids:[H],gates:[],windows:{},
          ungated_is:{num_trades:60,max_drawdown:-150},ungated_wf:{num_trades:100,max_drawdown:-250},
          ungated_lockbox:{num_trades:110,max_drawdown:-300},ungated_full:{num_trades:250,max_drawdown:-500},
          ungated_pre:{num_trades:160,max_drawdown:-260},ungated_wf_lb:{num_trades:210,max_drawdown:-360}};
        var wc=FIX_WIN+'doc.gate_validate='+JSON.stringify(GV)+';runHistory=[doc];window._runCfg={};window._runCfg[String(doc.id)]=doc;';
        doRender({c2Screen:'explore',resLvl:'valid',resShow:'configs',resCfgRun:[String(FIX.id)],resSegs:['wf'],resAxis:'ratio',resXAxis:'so',resMarks:'dot',c2Tbl:true,resCols:'all'}, wc);
        var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
        var trs=[].slice.call(d.querySelectorAll('tr[data-rerow]'));
        var gate=trs.filter(function(t){return (t.textContent||'').indexOf('GATE')>=0;})[0];
        var iMar=hdr.indexOf('MAR');
        r.gateMarCell=(gate&&iMar>=0)?(gate.cells[iMar].textContent||'').trim():null;
        var gp=[].filter.call(d.querySelectorAll('[data-repoint]'),function(g){var t=g.querySelector('title');return t&&(t.textContent||'').indexOf('GATE')>=0;})[0];
        var tt=gp?(gp.querySelector('title').textContent||''):'';var mi=tt.indexOf(' MAR ');
        r.gateMarPoint=(mi>=0)?parseFloat(tt.slice(mi+5).replace(/[^0-9.-].*$/,'')):null;
        var rec=trs.filter(function(t){var x=t.textContent||'';return x.indexOf('HYBRID ♻')>=0;})[0];
        var iWf=-1;hdr.forEach(function(h,k){if(iWf<0&&h.indexOf('WALK')===0)iWf=k;});
        var cellTitle=function(tr,i){var c=(tr&&i>=0)?tr.cells[i]:null;var sp=c?c.querySelector('[title]'):null;return sp?sp.getAttribute('title'):(c?(c.textContent||'').trim():null);};
        r.hybWf=cellTitle(rec,iWf);
        r.hybWfHdr=iWf>=0?hdr[iWf]:null;
        // combined tick: the recycled hybrid reads its WF+LB block total at the WF+LB factor (210/160)
        doRender({c2Screen:'explore',resLvl:'valid',resShow:'configs',resCfgRun:[String(FIX.id)],resSegs:['wf','lb'],resAxis:'evr',resXAxis:'so',resMarks:'dot',c2Tbl:true,resCols:'all'}, wc);
        var hdr2=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
        var rec2=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('HYBRID ♻')>=0;})[0];
        var im2=hdr2.indexOf('MAR');var mb=(rec2&&im2>=0)?rec2.cells[im2].querySelector('b[title]'):null;
        r.hybWfLbTip=mb?mb.getAttribute('title'):null;
        var iWf2=-1;hdr2.forEach(function(h,k){if(iWf2<0&&h.indexOf('WALK')===0)iWf2=k;});
        var ilb2=-1;hdr2.forEach(function(h,k){if(ilb2<0&&h.indexOf('LOCKBOX')===0)ilb2=k;});
        r.hybWfAtCombined=cellTitle(rec2,iWf2);r.hybLbAtCombined=cellTitle(rec2,ilb2);
      })();
      // -- case lvlall: LEVEL = ALL holds the sweeps AND the runs / configurations -----------
      (function(){
        var r=snap('lvlall','OK');
        var blk=function(p,dd,n){return {total_pnl:p,max_drawdown:dd,num_trades:n,profit_factor:1.5,win_rate:40,sharpe:1.2,sortino:2.1,avg_pnl:(p/n),avg_loss:-10};};
        var cand={model:'logistic',threshold:0.5,eligible:true,pre_pnl:10000,pre_rec:4,pre_pf:1.5,pre_wr:0.4,kept_pre:100,pre_sharpe:1.2,pre_sortino:2.1,
          is_rng:blk(1000,-300,20),wf_rng:blk(9000,-500,80),lockbox:blk(2000,-200,25),full:blk(12000,-600,125),wf_lb:blk(11000,-550,105)};
        var GV={span:['2010-01-04','2026-01-02'],wf_range:['2016-01-04','2025-01-02'],lockbox_from:'2025-01-02',candidates:[cand],
          chosen:{model:'logistic',threshold:0.5},tilts:[],hybrids:[],gates:[],windows:{}};
        var wc=FIX_WIN+'doc.gate_validate='+JSON.stringify(GV)+';runHistory=[doc];window._runCfg={};window._runCfg[String(doc.id)]=doc;';
        function read(extra){
          var p={c2Screen:'explore',resLvl:'all',resCfgRun:[String(FIX.id)],resAxis:'so',resXAxis:'roc',resMarks:'dot',c2Tbl:true};
          for(var k in extra)p[k]=extra[k];
          var c=doRender(p, wc);
          var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()]/g,'').trim();});
          var iRun=hdr.indexOf('RUN');
          var trs=[].slice.call(d.querySelectorAll('tr[data-rerow]'));
          var runTxt=function(t){return (iRun>=0&&t.cells[iRun])?(t.cells[iRun].textContent||'').trim():'';};
          var pts=[].slice.call(d.querySelectorAll('[data-repoint]'));
          return {call:c,rows:trs.length,
            sweeps:trs.filter(function(t){return runTxt(t).indexOf('#')!==0;}).length,
            runRows:trs.filter(function(t){return runTxt(t).indexOf('#'+FIX.id)===0;}).length,
            points:pts.length,
            gatePts:pts.filter(function(g){var t=g.querySelector('title');return !!(t&&(t.textContent||'').indexOf('GATE')>=0);}).length,
            runBtns:d.querySelectorAll('[data-recfgrun]').length+d.querySelectorAll('[data-reshow]').length};}
        r.cfg=read({resShow:'configs',resSegs:['wf']});
        r.runs=read({resShow:'runs',resSegs:['lb'],resAxis:'evr',resXAxis:'pf'});
      })();
      // -- case rbhoriz: RUNBOARD sideways reads the same rows as the grid --------------------
      (function(){
        var r=snap('rbhoriz','OK');r.per={};
        ['lb','full'].forEach(function(smp){
          var out={};
          ['v','h'].forEach(function(o){
            var c=doRender({cmpMode:'board',rbSample:smp,rbRank:'mar',rbOrient:o,cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp');
            var mar=null;
            if(o==='v'){[].forEach.call(d.querySelectorAll('tr'),function(tr){var cc=[].map.call(tr.children,function(td){return (td.textContent||'').trim();});
              if(cc[0]==='MAR'&&mar===null)mar=cc[1]||null;});}
            else{var t=d.querySelector('table[data-rbhoriz]');
              if(t){var hs=[].map.call(t.querySelectorAll('thead th'),function(x){return (x.textContent||'').trim();});
                var k=hs.indexOf('MAR');var row=t.querySelector('tbody tr');
                if(k>=0&&row&&row.children[k])mar=(row.children[k].textContent||'').trim();}}
            out[o]={call:c,mar:mar,horizTable:!!d.querySelector('table[data-rbhoriz]')};});
          r.per[smp]=out;});
      })();
      // -- case smalls: CHAMPIONS names its ranking; horizontal ticks carry their unit ------------
      (function(){
        var r=snap('smalls','OK');
        r.champCall=doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'champ',c2Stage:'lb',c2Rank:'mar'}, FIX_WIN);
        var t=(d.body.innerText||'');
        r.champLabel=(t.match(/[0-9]+ OF [0-9]+ STRATEGIES[^A-Z]*TOP [0-9]+ BY [A-Z /]+ ON [A-Z]+/)||[])[0]||null;
        r.champRankBtns=d.querySelectorAll('[data-c2rank]').length;
        r.pickCall=doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'lb',cmpIds:[String(FIX.id)]}, FIX_WIN);
        r.pickRankBtns=d.querySelectorAll('[data-c2rank]').length;
        r.tickCall=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'evr',resXAxis:'roc'}, FIX_WIN);
        var svg=[].filter.call(d.querySelectorAll('svg'),function(x){return x.querySelector('[data-repoint]');})[0];
        var ticks=svg?[].map.call(svg.querySelectorAll('text[text-anchor=middle]'),function(x){return (x.textContent||'').trim();}):[];
        r.pctTicks=ticks.filter(function(x){return /^-?[0-9.,]+[kM]?%$/.test(x);}).length;
      })();
      // -- case rbstage: hosted RUNBOARD follows the COMPARE tab's one STAGE --------------------
      (function(){
        var r=snap('rbstage','OK');
        function marOf(){var mar=null;[].forEach.call(d.querySelectorAll('tr'),function(tr){var cc=[].map.call(tr.children,function(td){return (td.textContent||'').trim();});
          if(cc[0]==='MAR'&&mar===null)mar=cc[1]||null;});return mar;}
        // the tab STAGE is IS while the old SAMPLE says LB: hosted RUNBOARD must read IS
        r.isCall=doRender({c2Screen:'cmp',c2View:'board',c2Stage:'is',rbSample:'lb',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN);
        r.isMar=marOf();
        r.lbCall=doRender({c2Screen:'cmp',c2View:'board',c2Stage:'lb',rbSample:'is',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN);
        r.lbMar=marOf();
        r.wfCall=doRender({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbSample:'lb',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN);
        r.wfHold=!!d.querySelector('[data-rbwf]');r.wfMar=marOf();
        r.wfTab=!!d.querySelector('[data-rbs=wf]');
        r.wfFunnel=!!d.querySelector('#cmp-ovl-host');r.wfRows=d.querySelectorAll('[data-rbrow]').length;
        // clicking SAMPLE FULL sets the tab STAGE
        var fb=d.querySelector('[data-rbs=full]');if(fb&&fb.onclick)fb.onclick();
        r.afterClick=w.eval("(JSON.parse(localStorage.getItem('augurPrefs')||'{}').c2Stage)||null");
        // outside the COMPARE tab RUNBOARD keeps its own SAMPLE and shows no WF tab
        r.oldCall=doRender({cmpMode:'board',rbSample:'lb',c2Stage:'is',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp');
        r.oldMar=marOf();r.oldWfTab=!!d.querySelector('[data-rbs=wf]');
        var ob=d.querySelector('[data-rbs=full]');if(ob&&ob.onclick)ob.onclick();
        r.oldClickStage=w.eval("(JSON.parse(localStorage.getItem('augurPrefs')||'{}').c2Stage)||null");
      })();
      // -- case a_champpf: FULL PF is the CHAMPION'S OWN reading first (item 1) --------
      //    validate.total_win_rate/total_avg_win/total_avg_loss belong to the SAME held-
      //    constant config the saved curve is drawn from, so PF built from them is not a
      //    reconstruction pooled across a different population (the walk-forward folds).
      (function(){
        var wr=(+FIX.validate.total_win_rate)/100,Wv=+FIX.validate.total_avg_win,Lv=Math.abs(+FIX.validate.total_avg_loss);
        var want=(wr*Wv)/((1-wr)*Lv);
        function mtxRow(lab){var found=null;
          [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
            var c=tr.children;if(c.length<2)return;
            if((c[0].textContent||'').trim()===lab)found=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
          return found;}
        var lc=doRender({c2Screen:'lead',c2Stage:'full',c2Rank:'pf'}, FIX_WIN);
        var r=snap('a_champpf', lc);
        r.want=want;
        var row=d.querySelector('.c2-row[data-c2fam]');
        var big=row?row.querySelector('.c2-big'):null;
        r.leadTxt=big?(big.textContent||'').trim():null;
        var oc=doRender({c2Screen:'cmp',c2Stage:'full',cmpIds:[String(FIX.id)]}, FIX_WIN);
        r.ovlCall=oc;
        r.ovlPf=(mtxRow('PF')||[])[0]||null;
        // twin with the whole-run averages removed: falls back to the pooled
        //   reconstruction, marked ~, on both the leaderboard and the overlay.
        var TW=JSON.parse(JSON.stringify(FIX));
        delete TW.validate.total_win_rate;delete TW.validate.total_avg_win;delete TW.validate.total_avg_loss;
        var wc2="var F="+JSON.stringify(TW)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var lc2=doRender({c2Screen:'lead',c2Stage:'full',c2Rank:'pf'}, wc2);
        r.twinCall=lc2;
        var row2=d.querySelector('.c2-row[data-c2fam]');
        var big2=row2?row2.querySelector('.c2-big'):null;
        r.twinTxt=big2?(big2.textContent||'').trim():null;
        var oc2=doRender({c2Screen:'cmp',c2Stage:'full',cmpIds:[String(FIX.id)]}, wc2);
        r.twinOvlCall=oc2;
        r.twinOvlPf=(mtxRow('PF')||[])[0]||null;
      })();

      // -- case a_champpf_ovl: on the OVERLAY matrix, EV R and R / YR on FULL follow the
      //    SAME ~ mark and best/heat exclusion as PF whenever they are built off a pfApx
      //    (rebuilt) PF -- audit round 2, item 1: mval reads S.pf for both
      //    (_evInR(S.wr,S.pf,S.tr)), so a PF the PF row itself refuses to let win must not
      //    let EV R / R per YR win on that same rebuilt number either -----------------------
      (function(){
        var TW2=JSON.parse(JSON.stringify(FIX));
        delete TW2.validate.total_avg_win;delete TW2.validate.total_avg_loss;
        TW2.id=String(+FIX.id+100001);TW2.starred=false;
        var wc="var A="+JSON.stringify(FIX)+";var B="+JSON.stringify(TW2)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(A),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        function mtxRowCells(lab){var found=null;
          [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
            var c=tr.children;if(c.length<2)return;
            if((c[0].textContent||'').trim()===lab)found=[].slice.call(c,1);});
          return found;}
        var oc=doRender({c2Screen:'cmp',c2Stage:'full',cmpIds:[String(FIX.id),String(TW2.id)]}, wc);
        var r=snap('a_champpf_ovl', oc);
        function bTxt(lab){var cells=mtxRowCells(lab);return cells?(cells[1].textContent||'').trim():null;}
        function bTitle(lab){var cells=mtxRowCells(lab);var sp=cells?cells[1].querySelector('span'):null;return sp?sp.getAttribute('title'):null;}
        r.pfB=bTxt('PF');r.pfBTitle=bTitle('PF');
        r.evB=bTxt('EV R');r.evBTitle=bTitle('EV R');
        r.rpyB=bTxt('R / YR');r.rpyBTitle=bTitle('R / YR');
      })();

      // -- case a_isyrs: IS years = 0.75 x the tuning window; a book's IS years run to
      //    lockbox_from, never the whole run (item 5) --------------------------------
      (function(){
        var opt=(FIX.validate.windows||{}).optimize||[];
        var tuneYrs=(Date.parse(opt[1])-Date.parse(opt[0]))/(365.25*86400000);
        var wantIsYrs=tuneYrs*0.75;
        var oc=doRender({c2Screen:'cmp',c2Stage:'is',cmpIds:[String(FIX.id)]}, FIX_WIN);
        var r=snap('a_isyrs', oc);
        var yrow=null;
        [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
          var c=tr.children;if(c.length<2)return;
          if((c[0].textContent||'').trim()==='YEARS')yrow=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
        r.gotYrs=yrow?parseFloat(yrow[0]):null;
        r.wantYrs=Math.round(wantIsYrs*10)/10;
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=String(+FIX.id+900500);BK.strategy='BOOK: probe isyrs';BK.starred=false;BK.multiplier=1;
        // a real book doc's best_* equal book.pre_lockbox (augur_engine/book.py sets
        //   result.best = result.book.pre_lockbox = best) - match that shape here so
        //   _c2is (which has no book branch of its own) reads the same figure this test
        //   expects, rather than an inherited fixture value from a plain run.
        BK.best_pnl_usd=250000;BK.best_dd_usd=25000;
        BK.book={name:'probe isyrs',legs:[{strategy:FIX.strategy,weight:1}],
          whole:{total_pnl:320000,max_drawdown:32000},
          pre_lockbox:{total_pnl:250000,max_drawdown:25000},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
        var bookIsYrs=(Date.parse('2025-02-11')-Date.parse('2010-06-07'))/(365.25*86400000);
        var wantBookMar=(250000/bookIsYrs)/25000;
        var wc="var B="+JSON.stringify(BK)+";var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var bc=doRender({c2Screen:'lead',c2Stage:'is',c2Rank:'mar'}, wc);
        r.bookCall=bc;
        var row=d.querySelector('.c2-row[data-c2fam]');
        var big=row?row.querySelector('.c2-big'):null;
        r.bookMarTxt=big?(big.textContent||'').trim():null;
        r.wantBookMar=Math.round(wantBookMar*100)/100;
        // A PLAIN AUTO-OPTIMIZE RUN'S SAVED scope IS AN EMOJI-PREFIXED LABEL, never the
        //   bare English words (the run_report fixture's own scope carries an emoji prefix
        //   too -- the same shape _modeNum already matches loosely) -- a strict === match
        //   never fires on real data, so this run type must still get the 75% correction.
        var AO=JSON.parse(JSON.stringify(FIX));delete AO.validate;
        AO.id=String(+FIX.id+700001);AO.strategy='ZAUTOOPT_1_0.py';AO.starred=false;AO.scope='🤖 Auto-Optimize';
        var wantAoYrs=(Date.parse(String(AO.date_to).slice(0,10))-Date.parse(String(AO.date_from).slice(0,10)))/(365.25*86400000)*0.75;
        var wcAo="var O="+JSON.stringify(AO)+";var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(O)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var aoc=doRender({c2Screen:'cmp',c2Stage:'is',cmpIds:[String(AO.id)]}, wcAo);
        r.aoCall=aoc;
        var aoRow=null;
        [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
          var c=tr.children;if(c.length<2)return;
          if((c[0].textContent||'').trim()==='YEARS')aoRow=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
        r.gotAoYrs=aoRow?parseFloat(aoRow[0]):null;
        r.wantAoYrs=Math.round(wantAoYrs*10)/10;
      })();

      // -- case a_wfyrs: WF R / YR on the leaderboard/overlay equals EXPLORE's own run-row
      //    reading (item 9); the WF MAR dash names the real reason -----------------------
      (function(){
        var R=JSON.parse(JSON.stringify(FIX));
        R.validate.windows=R.validate.windows||{};R.validate.windows.wf_split='2016-06-01';
        var wc="var F="+JSON.stringify(R)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var c1=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['wf'],resAxis:'evr',resXAxis:'so',c2Tbl:true}, wc);
        var h=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()]/g,'').trim();});
        var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(x){return (x.textContent||'').indexOf('#'+R.id)>=0;})[0];
        var iRpy=h.indexOf('R / YR');
        var expRpy=(tr&&iRpy>=0)?(tr.cells[iRpy].textContent||'').trim():null;
        var r=snap('a_wfyrs', c1);
        r.exploreRpy=expRpy;
        var c2=doRender({c2Screen:'lead',c2Stage:'wf',c2Rank:'rpy'}, wc);
        r.leadCall=c2;
        var row=d.querySelector('.c2-row[data-c2fam]');
        var big=row?row.querySelector('.c2-big'):null;
        r.leadRpy=big?(big.textContent||'').trim():null;
        var c3=doRender({c2Screen:'lead',c2Stage:'wf',c2Rank:'mar'}, wc);
        r.marCall=c3;
        var row2=d.querySelector('.c2-row[data-c2fam]');
        var big2=row2?row2.querySelector('.c2-big'):null;
        r.marTitle=big2?big2.getAttribute('title'):null;
      })();

      // -- case a_famlabel: an unregistered family prints its OWN name, not a tag shared
      //    with every other file whose first token happens to match (item 10) -----------
      (function(){
        var A=JSON.parse(JSON.stringify(FIX));A.id=String(+FIX.id+500001);A.strategy='ZTEST_ALPHA_1_0.py';A.starred=false;
        var B=JSON.parse(JSON.stringify(FIX));B.id=String(+FIX.id+500002);B.strategy='ZTEST_BETA_1_0.py';B.starred=false;
        var wc="var A="+JSON.stringify(A)+";var B="+JSON.stringify(B)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(A),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({c2Screen:'lead',c2Stage:'lb'}, wc);
        var r=snap('a_famlabel', call);
        var rows=[].slice.call(d.querySelectorAll('.c2-row[data-c2fam]'));
        r.rowsN=rows.length;
        function labelOf(k){
          var row=rows.filter(function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'')===k;})[0];
          var nm=row?row.querySelector('.c2-nm'):null;
          return nm?(nm.textContent||'').replace(/^[0-9]+/,''):null;}
        r.labelA=labelOf('ZTEST_ALPHA_1_0');
        r.labelB=labelOf('ZTEST_BETA_1_0');
        // same bug class, a second surface (audit round 2): the OVERLAY equity-chart
        //   legend / fullscreen multi-curve explorer (window._cmpEqxSeries, the label
        //   window.expandCompareEq renders) has its OWN unguarded stratTag call --
        //   check it separately from the leaderboard family-row spans above.
        var oc=doRender({c2Screen:'cmp',c2Stage:'full',cmpIds:[String(A.id),String(B.id)]}, wc);
        r.ovlCall=oc;
        // window._cmpEqxSeries/_cmpEqxNoCurve are set on the APP iframe's own window by
        //   renderApp, not on this probe page's window - read them back through w.eval,
        //   the same way every other app-global read in this file already does.
        var eqJson=w.eval('JSON.stringify((function(){var ser=(window._cmpEqxSeries||[]).concat(window._cmpEqxNoCurve||[]);function L(id){var m=ser.filter(function(s){return String(s.id)===String(id);})[0];return m?m.label:null;}return {a:L('+JSON.stringify(A.id)+'),b:L('+JSON.stringify(B.id)+')};})())');
        var eq=JSON.parse(eqJson);
        r.eqLabelA=eq.a;
        r.eqLabelB=eq.b;
      })();

      // -- case a_starruns: a run visible ONLY via window._starRuns still heads its family
      //    (item 4), and the run-window note names it -----------------------------------
      (function(){
        var S=JSON.parse(JSON.stringify(FIX));S.id=String(+FIX.id+400001);S.strategy='ZSTAR_ONE_1_0.py';S.starred=true;
        var wc="var F="+JSON.stringify(FIX)+";var S="+JSON.stringify(S)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(F)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();"
          +"window._starRuns=[f(S)];";
        var call=doRender({c2Screen:'lead',c2Stage:'lb'}, wc);
        var r=snap('a_starruns', call);
        var rows=[].slice.call(d.querySelectorAll('.c2-row[data-c2fam]'));
        var row=rows.filter(function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'')==='ZSTAR_ONE_1_0';})[0];
        r.famFound=!!row;
        var who=row?row.querySelector('.c2-who'):null;
        r.whoTxt=who?(who.textContent||'').trim():null;
        r.isCrown=r.whoTxt?/your crown/.test(r.whoTxt):false;
        var mm=(d.body.innerText||'').match(/\\+ [0-9]+ STARRED OLDER/);
        r.noteTxt=mm?mm[0]:null;
      })();

      // -- case a_lbzero: a zero-trade lockbox dashes with a true reason; a lockbox that
      //    lost every trade reads PF 0.00, not a dash (item 11a) -------------------------
      (function(){
        var Z=JSON.parse(JSON.stringify(FIX));Z.id=String(+FIX.id+300001);Z.strategy='ZZERO_TR_1_0.py';Z.starred=false;
        Z.validate.lockbox=Object.assign({},Z.validate.lockbox,{trades:0,pnl:0,dd:0,pf:0,win_rate:0});
        var P=JSON.parse(JSON.stringify(FIX));P.id=String(+FIX.id+300002);P.strategy='ZPFZERO_1_0.py';P.starred=false;
        P.validate.lockbox=Object.assign({},P.validate.lockbox,{trades:50,pf:0});
        var wc="var Z="+JSON.stringify(Z)+";var P="+JSON.stringify(P)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(Z),f(P)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({c2Screen:'lead',c2Stage:'lb',c2Rank:'pf'}, wc);
        var r=snap('a_lbzero', call);
        var rows=[].slice.call(d.querySelectorAll('.c2-row[data-c2fam]'));
        function rowOf(k){return rows.filter(function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'')===k;})[0];}
        var zRow=rowOf('ZZERO_TR_1_0'),pRow=rowOf('ZPFZERO_1_0');
        var zBig=zRow?zRow.querySelector('.c2-big'):null;
        r.zTxt=zBig?(zBig.textContent||'').trim():null;
        r.zTitle=zBig?zBig.getAttribute('title'):null;
        var zWho=zRow?zRow.querySelector('.c2-who'):null;
        r.zWhoTxt=zWho?(zWho.textContent||'').trim():null;
        var pBig=pRow?pRow.querySelector('.c2-big'):null;
        r.pTxt=pBig?(pBig.textContent||'').trim():null;
        var oc=doRender({c2Screen:'cmp',c2Stage:'lb',cmpIds:[String(P.id)]}, wc);
        r.ovlCall=oc;
        var mrow=null;
        [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
          var c=tr.children;if(c.length<2)return;
          if((c[0].textContent||'').trim()==='PF')mrow=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
        r.ovlPf=mrow?mrow[0]:null;
      })();

      // -- case a_topruns: the short-window caveat on TOP RUNS is truthful (item 11b) ------
      (function(){
        var A=JSON.parse(JSON.stringify(FIX));A.id=String(+FIX.id+200001);A.starred=false;
        A.date_from='2024-01-01';A.date_to='2024-06-01';
        var wc="var A="+JSON.stringify(A)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(A)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({c2Screen:'lead',c2Stage:'lb',c2Rank:'net',c2Top:'recent'}, wc);
        var r=snap('a_topruns', call);
        var warn=d.querySelector(".c2-card [title*='short sample']");
        r.title=warn?warn.getAttribute('title'):null;
      })();
      // -- case b_famBook (item 3): a BOOK named after a strategy is not a member of that
      //    strategy's family - the family matcher gives it its own BOOK key before the
      //    ENGU-Q name test ever runs. Checked on RUNBOARD's family chips (the old branch)
      //    and on the EXPLORE strategy rail, which is fixed for free by the same matcher
      //    (group C's region - no edit needed there). ------------------------------------
      (function(){
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=String(+FIX.id+500001);BK.strategy='BOOK X: ORB 1 + ENGU-Q 2';BK.starred=false;
        BK.best_pnl_usd=250000;BK.best_dd_usd=30000;BK.multiplier=1;
        BK.book={name:'BOOK X: ORB 1 + ENGU-Q 2',legs:[{strategy:'ORB_1_0.py',weight:1},{strategy:'ENGUQ_1_0.py',weight:1}],
          whole:{total_pnl:320000,max_drawdown:32000,num_trades:2000,profit_factor:1.3},
          pre_lockbox:{total_pnl:250000,max_drawdown:30000},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
        var wc="var F="+JSON.stringify(FIX)+";var B="+JSON.stringify(BK)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(F),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({cmpMode:'board',rbSample:'lb',rbRank:'mar'}, wc, 'cmp');
        var r=snap('b_famBook',call);
        r.chips=[].map.call(d.querySelectorAll('[data-rbfam]'),function(x){return x.getAttribute('data-rbfam');});
        doRender({c2Screen:'explore',resLvl:'valid'}, wc);
        r.railHasBook=!!d.querySelector('[data-refam="BOOK"]');
      })();

      // -- case b_rbBooksCol (item 3): the shared champion rule pools every book into ONE
      //    BOOKS column; a real strategy that merely shares a name keyword keeps its own.
      //    BK1 (lower net/DD) carries a HIGHER id than BK2, so the old id-descending walk
      //    hit it first - a book's score is NaN, and any comparison against NaN is false
      //    either way, so the old pool could never move off whichever book it saw first
      //    (the fault that kept a newest, unrelated book on the ENGU-Q slot). ------------
      (function(){
        function bkOf(id,name,pnl,dd){var B=JSON.parse(JSON.stringify(FIX));B.id=String(id);B.strategy=name;B.starred=false;
          B.best_pnl_usd=pnl;B.best_dd_usd=dd;B.multiplier=1;
          B.book={name:name,legs:[{strategy:'ENGUQ_1_0.py',weight:1}],
            whole:{total_pnl:pnl,max_drawdown:dd},pre_lockbox:{total_pnl:pnl,max_drawdown:dd},
            lockbox:{total_pnl:10000,num_trades:100,win_rate:40,profit_factor:1.3,max_drawdown:5000},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:10000,pf:1.3,trades:100,pass:true},book:true};return B;}
        var ENGU=JSON.parse(JSON.stringify(FIX));ENGU.id='500011';ENGU.strategy='ENGUQ_1_0.py';ENGU.starred=false;
        var BK1=bkOf(500012,'BOOK ALPHA: ENGU-Q x2',600000,20000);
        var BK2=bkOf(500013,'BOOK BETA: ORB + ENGU-Q',500000,10000);
        var wc="var E="+JSON.stringify(ENGU)+";var B1="+JSON.stringify(BK1)+";var B2="+JSON.stringify(BK2)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(E),f(B1),f(B2)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({cmpMode:'board',rbSample:'lb',rbRank:'mar'}, wc, 'cmp');
        var r=snap('b_rbBooksCol',call);
        // data-rbc decorates every CELL in a column (header AND body), not just the header -
        //   th[data-rbc] alone gives the header row, one id per column, in column order.
        r.colIds=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
      })();

      // -- case b_rbReads (item 6): one set of readers feeds the RANK BY order and the
      //    matrix cells; FULL TRADES prefers the saved whole-run count over a summed
      //    approximation; TRADES / WIN % carry no best mark or heat. -------------------
      (function(){
        function base(id,strat){var r=JSON.parse(JSON.stringify(FIX));r.id=String(id);r.starred=false;r.strategy=strat;
          r.validate=JSON.parse(JSON.stringify(FIX.validate||{}));delete r.validate.equity;
          delete r.validate.total_win_rate;delete r.validate.total_avg_win;delete r.validate.total_avg_loss;
          r.top10_results=[];return r;}
        var P=base(620001,'NOISE_1_0.py'),Q=base(620002,'ENGUQ_1_0.py');
        // P: a misleadingly HIGH best_pf (5.0) but a WEAK lockbox -> the true pooled FULL
        //    PF is low. It also saves a real whole-run trade count a naive sum would miss.
        P.best_pf=5.0;P.best_pnl_usd=10000;P.best_trades=300;
        P.validate.total_trades=5000;
        P.validate.lockbox={pnl:100,pf:1.01,trades:50,dd:2000};
        // Q: a misleadingly LOW best_pf (1.02) but a STRONG lockbox -> the true pooled
        //    FULL PF is high, the opposite order from best_pf. It saves NO whole-run trade
        //    count, so FULL TRADES must fall back to the summed approximation, marked ~.
        Q.best_pf=1.02;Q.best_pnl_usd=200;Q.best_trades=300;
        delete Q.validate.total_trades;
        Q.validate.lockbox={pnl:20000,pf:4.0,trades:200,dd:2000};
        var wc="var P="+JSON.stringify(P)+";var Q="+JSON.stringify(Q)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(P),f(Q)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({cmpMode:'board',rbSample:'full',rbRank:'pf',cmpIds:[]}, wc, 'cmp');
        var r=snap('b_rbReads',call);
        // data-rbc decorates every CELL in a column (header AND body), not just the header -
        //   th[data-rbc] alone gives the header row, one id per column, in column order.
        var colIds=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        r.colIds=colIds;
        function rowCells(lbl){var out=null;
          [].forEach.call(d.querySelectorAll('tr'),function(tr){
            var c=tr.children;if(!c.length)return;
            if((c[0].textContent||'').trim()===lbl&&out===null)out=[].slice.call(c,1);});
          return out||[];}
        var pfCells=rowCells('PF');
        var pfNums=[].map.call(pfCells,function(td){return parseFloat((td.textContent||'').replace(/[^0-9.-]/g,''));});
        r.pfNums=pfNums;
        r.pfNonIncreasing=pfNums.length===2&&pfNums.every(function(v,i){return i===0||!(v>pfNums[i-1]+1e-9);});
        var tdCells=rowCells('TRADES');
        var byId={};colIds.forEach(function(id,i){byId[id]={pf:pfCells[i],td:tdCells[i]};});
        var pTd=byId['620001']?(byId['620001'].td.textContent||'').trim():null;
        var qTd=byId['620002']?(byId['620002'].td.textContent||'').trim():null;
        r.pTradesTxt=pTd;r.qTradesTxt=qTd;
        r.pTrades=pTd?parseInt(pTd.replace(/[^0-9]/g,''),10):null;
        r.qTrades=qTd?parseInt(qTd.replace(/[^0-9]/g,''),10):null;
        r.pTradesApx=/~/.test(pTd||'');
        r.qTradesApx=/~/.test(qTd||'');
        function bestMarks(lbl){var n=0;
          [].forEach.call(d.querySelectorAll('tr'),function(tr){
            var c=tr.children;if(!c.length)return;
            if((c[0].textContent||'').trim()===lbl){
              for(var i=1;i<c.length;i++){if(c[i].querySelector('b[style*="color:var(--green)"]'))n++;}}});
          return n;}
        r.tradesBest=bestMarks('TRADES');
        r.winBest=bestMarks('WIN %');
      })();

      // -- case b_pickStage (item 7): hosted PICK RUNS follows the tab's STAGE, not the
      //    old tab's own, separate scope pref; the old, un-hosted tab is unaffected. -----
      (function(){
        var r=snap('b_pickStage','OK');
        function lbNet(){var v=null;
          [].forEach.call(d.querySelectorAll('tr'),function(tr){var c=[].map.call(tr.children,function(td){return (td.textContent||'').trim();});
            if(c[0]&&c[0].indexOf('Lockbox net')===0&&v===null)v=c[1]||null;});
          return v;}
        // hosted, c2Stage=lb, but the old cmpScope pref stuck on TOTAL: must still light
        //   LOCKBOX and print the lockbox net, not the stale TOTAL scope.
        r.call1=doRender({c2Screen:'cmp',c2View:'runs',c2Stage:'lb',cmpScope:'tot',cmpIds:[String(FIX.id)]}, FIX_WIN);
        r.lit=(function(){var b=d.querySelector('[data-cmpscope="lb"]');
          return !!(b&&(b.getAttribute('style')||'').indexOf('text4) 55%')>=0);})();
        r.net1=lbNet();
        // outside COMPARE, the old tab keeps reading its own cmpScope pref, unaffected
        r.call2=doRender({cmpMode:'runs',c2Stage:'lb',cmpScope:'tot',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp');
        r.oldTot=(function(){var b=d.querySelector('[data-cmpscope="tot"]');
          return !!(b&&(b.getAttribute('style')||'').indexOf('text4) 55%')>=0);})();
      })();

      // -- case b_rbSmalls (item 11): RUNBOARD BOOKS tile + native BOOKS view read NET
      //    DIVIDE DD (not MAR) and SLICES (not WF); TOP 10 RECENT dashes a run with no
      //    figure instead of printing $0; live book rows follow RANK BY. ----------------
      (function(){
        var r=snap('b_rbSmalls','OK');
        r.call1=doRender({cmpMode:'board',rbSample:'lb',rbRank:'mar'}, FIX_WIN, 'cmp');
        var ths=[].map.call(d.querySelectorAll('table th'),function(x){return (x.textContent||'').trim();});
        r.hasMarHdr=ths.indexOf('MAR')>=0;
        r.hasNetDdHdr=ths.indexOf('NET ÷ DD')>=0;
        r.hasWfHdr=ths.indexOf('WF')>=0;
        r.hasSlicesHdr=ths.indexOf('SLICES')>=0;
        var bodyTxt=(d.body&&(d.body.innerText||d.body.textContent))||'';
        r.noteSaysNetDd=bodyTxt.indexOf('NET ÷ DD = net divided by')>=0;
        r.noteSaysMarEquals=bodyTxt.indexOf('MAR = net divided by')>=0;
        r.call2=doRender({c2Screen:'cmp',c2View:'books',c2Stage:'lb'}, FIX_WIN);
        var bodyTxt2=(d.body&&(d.body.innerText||d.body.textContent))||'';
        r.nativeNoteSaysNetDd=bodyTxt2.indexOf('NET ÷ DD = net divided by')>=0;
        r.nativeNoteSaysMarEquals=bodyTxt2.indexOf('MAR = net divided by')>=0;
        var ths2=[].map.call(d.querySelectorAll('.c2-card table th'),function(x){return (x.textContent||'').trim();});
        r.nativeHasWfHdr=ths2.indexOf('WF')>=0;
        r.nativeHasSlicesHdr=ths2.indexOf('SLICES')>=0;

        var NR=JSON.parse(JSON.stringify(FIX));NR.id=String(+FIX.id+300001);NR.starred=false;
        NR.validate=JSON.parse(JSON.stringify(FIX.validate||{}));delete NR.validate.equity;
        NR.best_pnl_usd=null;NR.validate.lockbox=null;
        var wc3="var F="+JSON.stringify(FIX)+";var N="+JSON.stringify(NR)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(F),f(N)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        r.call3=doRender({cmpMode:'board',rbSample:'lb',rbRank:'mar',rbSide:'recent'}, wc3, 'cmp');
        var sideRow=d.querySelector('[data-rank-run="'+NR.id+'"]');
        var sideTxt=sideRow?(sideRow.textContent||'').trim():null;
        r.sideRowTxt=sideTxt;
        r.sideRowHasZero=(sideTxt||'').indexOf('$0')>=0;
        r.sideRowHasDash=(sideTxt||'').indexOf('—')>=0;

        function bk(id,pnl,dd){var B=JSON.parse(JSON.stringify(FIX));B.id=String(id);B.starred=false;
          B.book={name:'probe '+id,legs:[{strategy:FIX.strategy,weight:1}],
            whole:{total_pnl:pnl,max_drawdown:dd},pre_lockbox:{total_pnl:pnl,max_drawdown:dd},
            lockbox:{total_pnl:pnl,num_trades:100,win_rate:40,profit_factor:1.3,max_drawdown:dd},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:pnl,pf:1.3,trades:100,pass:true},book:true};return B;}
        var OLDB=bk(400001,900000,10000);
        var NEWB=bk(400002,100000,10000);
        var wc4="var O="+JSON.stringify(OLDB)+";var N2="+JSON.stringify(NEWB)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(O),f(N2)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        r.call4=doRender({cmpMode:'board',rbSample:'lb',rbRank:'net'}, wc4, 'cmp');
        r.liveOrder=[].map.call(d.querySelectorAll('tr[data-rank-run]'),function(tr){return tr.getAttribute('data-rank-run');});
      })();

      // -- case b_famBookPast (item 3, repair round): the book-not-a-family fix proven on
      //    Past Runs / RESULTS (augurSub==='runs'), which reads a run's family via
      //    stratInfo -> _stratMatch -> _famKey, never via _canonFam(r.strategy) directly.
      //    A real library entry (ORB_1_0.py) whose family+version match a bare digit IN
      //    the book's own title ("BOOK X: ORB 1 + ENGU-Q 2" names ORB's "1") used to make
      //    _stratMatch resolve the WHOLE BOOK to that file, so this tab kept reading it as
      //    ORB even once _canonFam alone said BOOK. A second real run (NOISE) is included
      //    so the family-chip bar renders at all (it needs >1 distinct family). ------------
      (function(){
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=String(+FIX.id+500002);BK.strategy='BOOK X: ORB 1 + ENGU-Q 2';BK.starred=false;
        BK.best_pnl_usd=250000;BK.best_dd_usd=30000;BK.multiplier=1;
        BK.book={name:'BOOK X: ORB 1 + ENGU-Q 2',legs:[{strategy:'ORB_1_0.py',weight:1},{strategy:'ENGUQ_1_0.py',weight:1}],
          whole:{total_pnl:320000,max_drawdown:32000,num_trades:2000,profit_factor:1.3},
          pre_lockbox:{total_pnl:250000,max_drawdown:30000},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
        var wc="var F0="+JSON.stringify(FIX)+";var B="+JSON.stringify(BK)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(F0),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();"
          +"metaStrats=[{file:'ORB_1_0.py',name:'ORB_1_0.py',params:[]},{file:'ORB_3_1.py',name:'ORB_3_1.py',params:[]}];";
        var call=doRender({}, wc, 'runs');
        var r=snap('b_famBookPast',call);
        r.chips=[].map.call(d.querySelectorAll('[data-rffam]'),function(x){return x.getAttribute('data-rffam');});
      })();

      // -- case b_pfApxExact (item 6, repair round): a run with NO walk-forward and NO
      //    lockbox never overlaps anything, so best_pf / best_trades are already the EXACT
      //    whole-run figures (see _pfOf / _trOf's own pre-existing "no wf, no lb" branch),
      //    not something pooled from stretches - FULL PF / FULL TRADES must not be marked
      //    ~ (and excluded from the best mark) for such a run just because it also saved
      //    no champion averages / no validate.total_trades. ------------------------------
      (function(){
        function plain(id,strat){var r=JSON.parse(JSON.stringify(FIX));r.id=String(id);r.starred=false;r.strategy=strat;
          r.validate={};r.top10_results=[];return r;}
        var P=plain(710001,'NOISE_1_0.py');
        P.best_pf=1.55;P.best_trades=842;P.best_pnl_usd=90000;
        var wc="var P="+JSON.stringify(P)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(P)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({cmpMode:'board',rbSample:'full',rbRank:'pf'}, wc, 'cmp');
        var r=snap('b_pfApxExact',call);
        function rowCells(lbl){var out2=null;
          [].forEach.call(d.querySelectorAll('tr'),function(tr){
            var c=tr.children;if(!c.length)return;
            if((c[0].textContent||'').trim()===lbl&&out2===null)out2=[].slice.call(c,1);});
          return out2||[];}
        var pfCells=rowCells('PF'),trCells=rowCells('TRADES');
        r.pfTxt=pfCells.length?(pfCells[0].textContent||'').trim():null;
        r.trTxt=trCells.length?(trCells[0].textContent||'').trim():null;
        r.pfHasTilde=/~/.test(r.pfTxt||'');
        r.trHasTilde=/~/.test(r.trTxt||'');
      })();

      // -- case b_pickBest (item 3, call-site audit finding): PICK RUNS' own "best run of
      //    this strategy" star marker (_bestByFam/_isBest) is a SEPARATE piece of code from
      //    the RUNBOARD champion pool B2 fixes above, and had the SAME NaN-comparison trap -
      //    a book's scoreRun is NaN, so the star could never move off whichever book the
      //    list saw FIRST. WEAK carries the HIGHER id (rs sorts id-descending, so it is seen
      //    first) but the WEAKER pre-lockbox net/DD; STRONG is seen second but is the real
      //    best book. -----------------------------------------------------------------------
      (function(){
        function bk(id,pnl,dd){var B=JSON.parse(JSON.stringify(FIX));B.id=String(id);B.starred=false;
          B.book={name:'probe '+id,legs:[{strategy:FIX.strategy,weight:1}],
            whole:{total_pnl:pnl,max_drawdown:dd},pre_lockbox:{total_pnl:pnl,max_drawdown:dd},
            lockbox:{total_pnl:pnl,num_trades:100,win_rate:40,profit_factor:1.3,max_drawdown:dd},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:pnl,pf:1.3,trades:100,pass:true},book:true};return B;}
        var WEAK=bk(800002,100000,20000),STRONG=bk(800001,600000,20000);
        var wc="var W="+JSON.stringify(WEAK)+";var S="+JSON.stringify(STRONG)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(W),f(S)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({cmpMode:'runs'}, wc, 'cmp');
        var r=snap('b_pickBest',call);
        function starOf(id){var row=d.querySelector('[data-cmpk="'+id+'"]');
          if(!row)return null;
          var star=row.querySelector('span[title="best run of this strategy"]');
          return !!(star&&/★/.test(star.textContent||''));}
        r.weakIsBest=starOf(WEAK.id);
        r.strongIsBest=starOf(STRONG.id);
      })();

      // -- case b_famCombinedGuard (item 3, repair round): a REAL strategy literally named
      //    COMBINED_ALPHA_1_0.py (no r.book, no 'Book' scope - _c2IsBook itself correctly
      //    leaves it alone) must not be swept into BOOK by _canonFam. The checker's own repro:
      //    this run plus one ordinary registered-family run (NOISE), rendered on RUNBOARD's
      //    family chip bar. On both base (no book test at all) and the fixed matcher, the
      //    COMBINED run's canonical family is '' (no keyword matches "combined"), so it drops
      //    out of the chip bar's Boolean filter and - with only one family (NOISE) left - the
      //    bar does not render at all (it needs >1 distinct family): chips=[]. The bug this
      //    case catches is narrower than "chips is empty": it is that 'BOOK' must never appear
      //    among them. --------------------------------------------------------------------
      (function(){
        function plain(id,strat){var r=JSON.parse(JSON.stringify(FIX));r.id=String(id);r.starred=false;r.strategy=strat;
          delete r.book;delete r.scope;r.best_pnl_usd=100000;r.best_dd_usd=10000;return r;}
        var CB=plain(640001,'COMBINED_ALPHA_1_0.py');
        var NS=plain(640002,'NOISE_1_0.py');
        var wc="var C="+JSON.stringify(CB)+";var N="+JSON.stringify(NS)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(C),f(N)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({cmpMode:'board',rbSample:'lb',rbRank:'mar'}, wc, 'cmp');
        var r=snap('b_famCombinedGuard',call);
        r.chips=[].map.call(d.querySelectorAll('[data-rbfam]'),function(x){return x.getAttribute('data-rbfam');});
      })();
      // ── case c_pool: item 2 - a CONFIG row's PF pools from the ticked single-stretch
      //    blocks when the run never saved a joint block for the combination (IN-SAMPLE +
      //    LOCKBOX always; PRE / WF+LB / FULL on an older run), instead of falling straight
      //    through to the row's own fixed whole-window figure. DRAWDOWN, which needs a
      //    stitched curve no such combination ever saves, dashes instead. Fixture #306's
      //    crowned RAW candidate (selection.candidates[5]) saves is_rng / wf_rng / lockbox
      //    but no pre / full / wf_lb of its own.
      (function(){
        var CID=String(FIX.id);
        var wc="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();";
        function crownTip(){
          var titles=[].slice.call(d.querySelectorAll('[data-repoint] title'));
          for(var i=0;i<titles.length;i++){if((titles[i].textContent||'').indexOf('RAW CROWNED')>=0)return titles[i].textContent;}
          return null;
        }
        var callIsLb=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['is','lb'],resAxis:'pf',resXAxis:'wr'}, wc);
        var tipIsLb=crownTip();
        var callIs=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['is'],resAxis:'pf',resXAxis:'wr'}, wc);
        var tipIs=crownTip();
        var callLb=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['lb'],resAxis:'pf',resXAxis:'wr'}, wc);
        var tipLb=crownTip();
        var r=snap('c_pool', (callIsLb==='OK'&&callIs==='OK'&&callLb==='OK')?'OK':('ERR '+callIsLb+' / '+callIs+' / '+callLb));
        // NB: this JS text lands inside cmp2_render_probe.py's own (non-raw) PROBE_HTML
        //   Python string, so no regex backslash escapes here - a character class like
        //   [0-9] or [.] stands in for a digit or dot class - or Python's own string
        //   parser mangles them before Chrome ever sees them (a bare word-boundary escape
        //   would silently become a backspace byte).
        function num(tip){var m=tip&&tip.match(/PF ([0-9]+[.][0-9]+)/);return m?parseFloat(m[1]):null;}
        r.pfIsLb=num(tipIsLb);r.pfIs=num(tipIs);r.pfLb=num(tipLb);
        r.ddDashedIsLb=!!(tipIsLb&&tipIsLb.indexOf('Worst drawdown not measured')>=0);
        r.ddShownIs=!!(tipIs&&/Worst drawdown [$][0-9]/.test(tipIs));
        r.tipIsLb=tipIsLb;
      })();

      // ── case c_hover: item 8 - the point hover names the real vertical measure for
      //    every one of the 13 modes (not just MAR / profit) and always adds the
      //    horizontal measure's name too, in ABSOLUTE mode as well as VS CROWN.
      (function(){
        var CID=String(FIX.id);
        var wc="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();";
        function crownTip(){
          var titles=[].slice.call(d.querySelectorAll('[data-repoint] title'));
          for(var i=0;i<titles.length;i++){if((titles[i].textContent||'').indexOf('RAW CROWNED')>=0)return titles[i].textContent;}
          return null;
        }
        var call=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['lb'],resAxis:'wr',resXAxis:'so'}, wc);
        var tip=crownTip();
        var r=snap('c_hover', call==='OK'?'OK':('ERR '+call));
        r.tip=tip;
        r.hasWinLabel=!!(tip&&tip.indexOf('WIN %')>=0);
        r.hasSortinoLabel=!!(tip&&tip.toLowerCase().indexOf('sortino')>=0);
        r.mislabeledProfit=!!(tip&&tip.indexOf('profit 31.23')>=0);
      })();

      // ── case c_hidedot: item 4 - right-click a point on the configs scatter hides it
      //    via a chart-only redraw (window._reRedrawChart), the SHOW ALL chip appears, the
      //    table underneath is untouched, and the chip brings the point back.
      (function(){
        var CID=String(FIX.id);
        var wc="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          // window._runCfg is reset here too, not just window._runFull: an earlier case
          //   (gatewf) leaves a stale, gate_validate-only doc parked under this same run id,
          //   and the config-row builder checks window._runCfg before window._runFull.
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();window._reHidePts={};window._runCfg={};";
        var call=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID]}, wc);
        var r=snap('c_hidedot', call==='OK'?'OK':('ERR '+call));
        var pts0=d.querySelectorAll('[data-repoint]');
        r.pts0=pts0.length;
        r.rows0=d.querySelectorAll('tr[data-rerow]').length;
        r.chipBefore=!!d.querySelector('[data-reunhide]');
        if(pts0.length>=2){
          var target=pts0[0];
          var hk=target.getAttribute('data-rehide');
          r.hkPresent=!!hk;
          try{target.dispatchEvent(new w.MouseEvent('contextmenu',{bubbles:true,cancelable:true}));}catch(e){r.dispatchErr=String(e);}
          r.pts1=d.querySelectorAll('[data-repoint]').length;
          var chip=d.querySelector('[data-reunhide]');
          r.chipAfter=!!chip;
          r.rows1=d.querySelectorAll('tr[data-rerow]').length;
          r.hkStillThere=[].some.call(d.querySelectorAll('[data-repoint]'),function(p){return p.getAttribute('data-rehide')===hk;});
          if(chip){
            try{chip.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));}catch(e){r.unhideErr=String(e);}
          }
          r.pts2=d.querySelectorAll('[data-repoint]').length;
          r.chipAfterUnhide=!!d.querySelector('[data-reunhide]');
        }
        r.errorsAfter=sink.errors.slice(0,10);
        r.uncaughtAfter=sink.uncaught.slice(0,10);
      })();

      // ── case c_qual: item 11(a) - the QUALITY preset's click (and its lit state) match
      //    its own description: vertical EV R, horizontal Sortino.
      (function(){
        var call=doRender({c2Screen:'explore',resLvl:'sweep'}, EMPTY_WIN);
        var r=snap('c_qual', call==='OK'?'OK':('ERR '+call));
        var btn=d.querySelector('[data-respreset="qual"]');
        r.btnFound=!!btn;
        if(btn&&btn.onclick)btn.onclick();
        var prefs=w.eval("JSON.parse(localStorage.getItem('augurPrefs')||'{}')");
        r.axisAfter=prefs.resAxis;r.xAxisAfter=prefs.resXAxis;
        doRender({c2Screen:'explore',resLvl:'sweep',resAxis:prefs.resAxis,resXAxis:prefs.resXAxis}, EMPTY_WIN);
        var btn2=d.querySelector('[data-respreset="qual"]');
        r.litWhenApplied=!!(btn2&&(btn2.getAttribute('style')||'').indexOf('color:var(--text)')>=0);
      })();

      // ── case c_mintrd: item 11(e) - MIN TRADES double-counted a row with no trade count.
      //    Such a row is NOTED (there is nothing to compare it against) but never turned
      //    away by the floor, so it still lands in the plotted set or the skipped set like
      //    any other row - counting it AGAIN in the chart's own 'N of M rows plotted'
      //    headline double-counted it against the table rows (live-reproduced as 1,580 vs
      //    1,531 table rows). Read straight off the real embedded research board with MIN
      //    TRADES on; no fixture needed, and the sentence is parsed rather than guessed.
      (function(){
        var call=doRender({c2Screen:'explore',resLvl:'all',resAxis:'dd',resXAxis:'raw',resMinTrd:'30'}, EMPTY_WIN);
        var r=snap('c_mintrd', call==='OK'?'OK':('ERR '+call));
        var infoIcon=[].filter.call(d.querySelectorAll('span[title]'),function(s){return /rows? plotted/.test(s.getAttribute('title')||'');})[0];
        var hint=infoIcon?(infoIcon.getAttribute('title')||''):'';
        r.hint=hint.slice(0,2000);
        var head=hint.match(/([0-9]+) of ([0-9]+) rows plotted/);
        var headAll=hint.match(/all ([0-9]+) rows plotted/);
        r.plotted=head?parseInt(head[1],10):(headAll?parseInt(headAll[1],10):null);
        r.nOff=head?parseInt(head[2],10):(headAll?parseInt(headAll[1],10):null);
        var sk=hint.match(/([0-9]+) of the ([0-9]+) rows now shown are not on the chart/);
        r.skip=sk?parseInt(sk[1],10):0;
        // g4_f20 reworded this sentence to name only the PLACEABLE failed-row count (the ones
        //   control 5 would actually draw), with the rows that lack a figure on these axes
        //   split into their own clause -- so the historical single-number match here now
        //   has to add both clauses back together to get the same total failOut.length this
        //   check was written against (nOff below is still built from the real failOut.length).
        var foP=hint.match(/([0-9]+) failed rows? (?:are|is) left off the chart on purpose/);
        var foZ=hint.match(/([0-9]+) failed rows? (?:has|have) no figure on these axes, so PLOT FAILURES/);
        var flOther=hint.match(/other ([0-9]+) failed rows? (?:has|have) no figure on these axes/);
        // repair round (F20 follow-up): a failed row held under MIN TRADES is now its OWN
        //   clause (it has both figures - it was never missing anything) instead of being
        //   folded into "no figure on these axes" - add it back in so this still sums to the
        //   real failOut.length this check was written against.
        var foMin=hint.match(/([0-9]+) failed rows? (?:are|is) held under the MIN TRADES floor/);
        r.foMin=foMin?parseInt(foMin[1],10):0;
        r.failOut=(foP?parseInt(foP[1],10):0)+(foZ?parseInt(foZ[1],10):0)+(flOther?parseInt(flOther[1],10):0)+r.foMin;
        var to=hint.match(/([0-9]+) rows? (?:are|is) left off the chart for a thin sample/);
        r.thinOut=to?parseInt(to[1],10):0;
        var tn=hint.match(/A further ([0-9]+) rows? records? no trade count at all/);
        r.thinNoCt=tn?parseInt(tn[1],10):0;
      })();

      // ── case c_champmsg: item 11(c), repair round - the chart's OWN "AXIS is set to
      //    CHAMPION..." note (built earlier in the render pass, beside the "N of M rows
      //    plotted" headline - a different sentence from the CHAMPION button hover and the
      //    AXIS control description fixed in the first pass) still said "the money it added
      //    and the drawdown it added" no matter what was actually on the axes. Read straight
      //    off the real embedded research board (same pattern as c_mintrd) with WIN % up the
      //    side and SORTINO across - neither is money or drawdown - and CHAMPION mode on.
      (function(){
        var call=doRender({c2Screen:'explore',resLvl:'all',resAxis:'wr',resXAxis:'so',resRel:'crown'}, EMPTY_WIN);
        var r=snap('c_champmsg', call==='OK'?'OK':('ERR '+call));
        var infoIcon=[].filter.call(d.querySelectorAll('span[title]'),function(s){return /AXIS is set to CHAMPION/.test(s.getAttribute('title')||'');})[0];
        var hint=infoIcon?(infoIcon.getAttribute('title')||''):'';
        r.hint=hint.slice(0,2000);
        r.saysMoneyDrawdown=/money it added and the drawdown it added/.test(hint);
        r.saysDifference=/difference it added against it on the two measures now on the axes/.test(hint);
        r.saysUpRight=/up and to the right beats the champion on both of them/.test(hint);
      })();

      // == review-round regression cases (r_*). Each one fails on 1ec67d6 and passes once
      //    the review fixes are in. ============================================================
      // -- case r_fullPfExact (R-A1): a run with best_pf and no walk-forward and no lockbox
      //    never pooled anything - its FULL PF on the LEADERBOARD is exact, never marked ~. ----
      (function(){
        var P=JSON.parse(JSON.stringify(FIX));P.id='720001';P.starred=false;P.strategy='NOISE_1_0.py';
        P.validate={};P.top10_results=[];P.best_pf=1.55;P.best_trades=842;P.best_pnl_usd=90000;
        var wc="var P="+JSON.stringify(P)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(P)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({c2Screen:'lead',c2Stage:'full',c2Rank:'pf'}, wc);
        var r=snap('r_fullPfExact',call);
        var row=d.querySelector('.c2-row[data-c2fam]');
        var big=row?row.querySelector('.c2-big'):null;
        r.pfTxt=big?(big.textContent||'').trim():null;
      })();

      // -- case r_starApply (R-A2): a failed starred read never wipes a good list, and an
      //    older successful read never overwrites a newer one. Called directly. ---------------
      (function(){
        var r=snap('r_starApply','OK');
        try{
          r.res=w.eval("(function(){if(typeof _starRunsApply!=='function')return {missing:true};"
            +"var g0=window._starRunsGen,a0=window._starRunsAt,s0=window._starRuns;"
            +"window._starRunsAt=0;window._starRuns=[];var o={};"
            +"o.ok1=_starRunsApply([{id:'g1'}],1);o.fail2=_starRunsApply(null,2);"
            +"o.afterFail=(window._starRuns||[]).map(function(x){return x.id;});"
            +"o.ok3=_starRunsApply([{id:'g3'}],3);o.late2=_starRunsApply([{id:'g2'}],2);"
            +"o.afterLate=(window._starRuns||[]).map(function(x){return x.id;});"
            +"window._starRunsGen=g0;window._starRunsAt=a0;window._starRuns=s0;return o;})()");
        }catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
      })();

      // -- case r_lbZeroTrades (R-A3 + B1): a lockbox that took no trades, beside a normal run
      //    that LOST money in its lockbox. OVERLAY TRADES reads 0; on RUNBOARD SAMPLE=LB its
      //    TOTAL / DD dash with the reason, its TRADES read 0, and the normal run holds the best
      //    marks and the crown column (the zero run's $0 used to win both). -------------------
      (function(){
        var Z=JSON.parse(JSON.stringify(FIX));Z.id=String(+FIX.id+730001);Z.strategy='ZZERO_TR_1_0.py';Z.starred=false;
        Z.validate.lockbox=Object.assign({},Z.validate.lockbox,{trades:0,pnl:0,dd:0,pf:0,win_rate:0,sharpe:0});
        var N=JSON.parse(JSON.stringify(FIX));N.id=String(+FIX.id+730002);N.strategy='ZKAPPA_1_0.py';N.starred=false;
        N.validate.lockbox=Object.assign({},N.validate.lockbox,{trades:120,pnl:-250,dd:900,pf:0.9,win_rate:30});
        var wc="var Z="+JSON.stringify(Z)+";var N="+JSON.stringify(N)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(Z),f(N)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var r=snap('r_lbZeroTrades','OK');
        r.zId=Z.id;r.nId=N.id;
        r.ovlCall=doRender({c2Screen:'cmp',c2Stage:'lb',cmpIds:[String(Z.id)]}, wc);
        r.ovlTr=null;
        [].forEach.call(d.querySelectorAll('.c2-card table tr'),function(tr){
          var c=tr.children;if(c.length<2)return;
          if((c[0].textContent||'').trim()==='TRADES'&&r.ovlTr===null)r.ovlTr=(c[1].textContent||'').trim();});
        r.rbCall=doRender({cmpMode:'board',rbSample:'lb',rbRank:'net'}, wc, 'cmp');
        r.colIds=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        function rowCells(lbl){var out2=null;
          [].forEach.call(d.querySelectorAll('tr'),function(tr){
            var c=tr.children;if(!c.length)return;
            if((c[0].textContent||'').trim()===lbl&&out2===null)out2=[].slice.call(c,1);});
          return out2||[];}
        function cellOf(lbl,id){var cells=rowCells(lbl),i=r.colIds.indexOf(String(id));return (i>=0&&cells[i])?cells[i]:null;}
        function best(td){return !!(td&&td.querySelector('b[style*="color:var(--green)"]'));}
        var zNet=cellOf('TOTAL',Z.id),nNet=cellOf('TOTAL',N.id),zDd=cellOf('DD',Z.id),nDd=cellOf('DD',N.id),zTr=cellOf('TRADES',Z.id);
        r.zNetTxt=zNet?(zNet.textContent||'').trim():null;
        var zt=zNet?zNet.querySelector('[title]'):null;r.zNetTitle=zt?zt.getAttribute('title'):null;
        r.zDdTxt=zDd?(zDd.textContent||'').trim():null;
        r.zTrTxt=zTr?(zTr.textContent||'').trim():null;
        r.nNetBest=best(nNet);r.zNetBest=best(zNet);r.nDdBest=best(nDd);r.zDdBest=best(zDd);
      })();

      // -- case r_trdSumAll3 (R-C1): the #306 crowned RAW candidate saves is_rng / wf_rng /
      //    lockbox but no FULL block. With all three stretches ticked its TRADES is the sum of
      //    the three, not the row's own count. ---------------------------------------------------
      (function(){
        var CID=String(FIX.id);
        var cand=((FIX.selection&&FIX.selection.candidates)||[]).filter(function(c){return c&&c.crowned;})[0]||null;
        var wc="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();"
          +"window._runCfg={};window._runCfg['"+CID+"']=doc;";
        var call=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['is','wf','lb'],resAxis:'pf',resXAxis:'wr'}, wc);
        var r=snap('r_trdSumAll3',call);
        r.hasFull=!!(cand&&cand.full);
        r.expect=cand?((+cand.is_rng.num_trades)+(+cand.wf_rng.num_trades)+(+cand.lockbox.num_trades)):null;
        var tip=null;
        [].slice.call(d.querySelectorAll('[data-repoint] title')).forEach(function(t){if(tip===null&&(t.textContent||'').indexOf('RAW CROWNED')>=0)tip=t.textContent;});
        r.tip=tip;
        var m=tip&&tip.match(/Trades ([0-9,]+)/);
        r.trades=m?parseInt(m[1].split(',').join(''),10):null;
      })();

      // -- case r_pfInfLeg (R-C2, tightened in repair round 3): the same row whose IN-SAMPLE stretch had
      //    NO LOSING TRADE, saved the way the engine really stores it - an infinite profit factor cannot be
      //    stored, json_safe writes null - with IN-SAMPLE + LOCKBOX ticked. The pooled PF is a number (that
      //    stretch adds its net as gross win and nothing as gross loss) and the point plots: (v1) the RAW
      //    block shape, losses 0 and no average loss; (v2) the GATE export shape, which saves no win or loss
      //    counts, only a zero drawdown. (v3) a null profit factor on a block that shows a loss (a drawdown)
      //    is NOT read as no-loss, so the point stays off the PF axis.
      (function(){
        var CID=String(FIX.id);
        var cand=((FIX.selection&&FIX.selection.candidates)||[]).filter(function(c){return c&&c.crowned;})[0]||null;
        function wcMod(mod){return "var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"(doc.selection.candidates||[]).forEach(function(c){if(c&&c.crowned&&c.is_rng){var b=c.is_rng;"+mod+"}});"
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();"
          +"window._runCfg={};window._runCfg['"+CID+"']=doc;";}
        var P={c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['is','lb'],resAxis:'pf',resXAxis:'wr'};
        function tipPf(){var tip=null;
          [].slice.call(d.querySelectorAll('[data-repoint] title')).forEach(function(t){if(tip===null&&(t.textContent||'').indexOf('RAW CROWNED')>=0)tip=t.textContent;});
          var m=tip&&tip.match(/PF ([0-9]+[.][0-9]+)/);return {plotted:!!tip,pf:(m?parseFloat(m[1]):null)};}
        var unc=[];
        var call=doRender(P, wcMod("b.profit_factor=null;b.losses=0;b.wins=b.num_trades;b.max_drawdown=0;b.avg_loss=null;"));
        unc=unc.concat(sink.uncaught.slice(0,5));
        var r=snap('r_pfInfLeg',call);
        var a=tipPf();r.plotted=a.plotted;r.pf=a.pf;
        r.call2=doRender(P, wcMod("b.profit_factor=null;delete b.losses;delete b.wins;delete b.avg_loss;b.max_drawdown=0;"));
        unc=unc.concat(sink.uncaught.slice(0,5));
        a=tipPf();r.plotted2=a.plotted;r.pf2=a.pf;
        r.call3=doRender(P, wcMod("b.profit_factor=null;delete b.losses;delete b.wins;delete b.avg_loss;b.max_drawdown=-500;"));
        unc=unc.concat(sink.uncaught.slice(0,5));
        a=tipPf();r.plotted3=a.plotted;r.pf3=a.pf;
        r.unc=unc;
        if(cand){var L=cand.lockbox,pf0=+L.profit_factor,tp=+L.total_pnl,gl=Math.abs(tp/(pf0-1)),gw=pf0*gl;
          r.isPnl=+cand.is_rng.total_pnl;r.expect=(gw+(+cand.is_rng.total_pnl))/gl;}
      })();

      // -- case r_champBooks (B2): Past Runs CHAMPIONS with two books, the WEAKER (lower
      //    pre-lockbox net over drawdown) listed first. A book scores NaN, so the old score sum
      //    tied them at 0 and kept whichever came first; the leaderboard rule keeps the stronger.
      (function(){
        function bk(id,name,pnl,dd){var B=JSON.parse(JSON.stringify(FIX));B.id=String(id);B.strategy=name;B.starred=false;
          B.best_pnl_usd=pnl;B.best_dd_usd=dd;B.multiplier=1;
          B.book={name:name,legs:[{strategy:FIX.strategy,weight:1}],
            whole:{total_pnl:pnl,max_drawdown:dd},pre_lockbox:{total_pnl:pnl,max_drawdown:dd},
            lockbox:{total_pnl:10000,num_trades:100,win_rate:40,profit_factor:1.3,max_drawdown:5000},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:10000,pf:1.3,trades:100,pass:true},book:true};return B;}
        var WEAK=bk(740002,'BOOK: PROBE WEAK',100000,20000),STRONG=bk(740001,'BOOK: PROBE STRONG',600000,20000);
        var wc="var W="+JSON.stringify(WEAK)+";var S="+JSON.stringify(STRONG)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(W),f(S)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        var call=doRender({rfChamp:true}, wc, 'runs');
        var r=snap('r_champBooks',call);
        r.weakId=WEAK.id;r.strongId=STRONG.id;
        r.ids=[].map.call(d.querySelectorAll('tr.arow[data-run]'),function(x){return x.getAttribute('data-run');});
      })();

      // -- case r_pickStageDefault (B3, updated 2026-09-20 - owner moved the default to
      //    WALK-FORWARD, item 1): no STAGE saved yet - PICK RUNS hosted in COMPARE falls
      //    back to the tab's own default, WALK-FORWARD, like the LEADERBOARD and RUNBOARD. --
      (function(){
        var call=doRender({c2Screen:'cmp',c2View:'runs',cmpIds:[String(FIX.id)]}, FIX_WIN);
        var r=snap('r_pickStageDefault',call);
        function lit(k){var b=d.querySelector('[data-cmpscope="'+k+'"]');
          return !!(b&&(b.getAttribute('style')||'').indexOf('text4) 55%')>=0);}
        r.lbLit=lit('lb');r.isLit=lit('all');r.wfLit=lit('wf');r.btns=d.querySelectorAll('[data-cmpscope]').length;
      })();
      // -- case r_zeroTrBlk (repair round): a stretch that TOOK NO TRADES. The engine still
      //    writes profit factor 0, win rate 0 and drawdown 0 on it, and EXPLORE read them as
      //    measured: PF 0.00, EV IN R -1.00, a $0 drawdown at the best end of a drawdown axis.
      //    A config row (the #306 crowned RAW candidate) and a run row, LOCKBOX ticked: the
      //    ratios and the drawdown dash with the reason, TRADES stays 0, the point leaves an
      //    EV R / drawdown axis, and IN-SAMPLE + LOCKBOX still pools to the in-sample figures.
      (function(){
        var CID=String(FIX.id);
        var r=snap('r_zeroTrBlk','OK');
        r.unc=[];function rd(p,wc){var c=doRender(p,wc);r.unc=r.unc.concat(sink.uncaught.slice(0,5));return c;}
        var ZLB="c.lockbox.num_trades=0;c.lockbox.total_pnl=0;c.lockbox.profit_factor=0;c.lockbox.win_rate=0;"
          +"c.lockbox.max_drawdown=0;c.lockbox.sharpe=0;c.lockbox.sortino=0;c.lockbox.avg_loss=0;";
        var wcC="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"(doc.selection.candidates||[]).forEach(function(c){if(c&&c.crowned&&c.lockbox){"+ZLB+"}});"
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();"
          +"window._runCfg={};window._runCfg['"+CID+"']=doc;";
        function tipOf(key){var tip=null;[].slice.call(d.querySelectorAll('[data-repoint] title')).forEach(function(t){
          if(tip===null&&(t.textContent||'').indexOf(key)>=0)tip=t.textContent;});return tip;}
        function cellsOf(key){
          var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
          var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf(key)>=0;})[0];
          var o={found:!!tr};if(!tr)return o;
          ['DRAWDOWN','MAR','SHARPE','SORTINO','PF','WIN %','EV R','TRADES'].forEach(function(h){
            var i=hdr.indexOf(h),c=(i>=0)?tr.cells[i]:null,sp=c?c.querySelector('[title]'):null;
            o[h]=c?[(c.textContent||'').trim(),sp?sp.getAttribute('title'):null]:null;});
          return o;}
        function pfOf(tip){var m=tip&&tip.match(/PF ([0-9]+[.][0-9]+)/);return m?parseFloat(m[1]):null;}
        function trOf(tip){var m=tip&&tip.match(/Trades ([0-9,.]+)/);return m?parseFloat(m[1].split(',').join('')):null;}
        // config row, EV R over WIN %: nothing to place it with
        r.cA=rd({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['lb'],resAxis:'evr',resXAxis:'wr',c2Tbl:true,resCols:'all'}, wcC);
        r.cfgPts=d.querySelectorAll('[data-repoint]').length;
        r.cfgTipEvr=tipOf('RAW CROWNED');
        r.cfgCells=cellsOf('RAW crowned');
        // config row, money over $ per trade (review round 4): a stretch with no trades is neither plotted nor
        //   ranked on money either - the LEADERBOARD / RUNBOARD rule - and its RANK dash says why
        r.cB=rd({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['lb'],resAxis:'raw',resXAxis:'ppt',c2Tbl:true,resCols:'all'}, wcC);
        r.cfgTipMoney=tipOf('RAW CROWNED');r.cfgPtsMoney=d.querySelectorAll('[data-repoint]').length;
        (function(){var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
          var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('RAW crowned')>=0;})[0];
          var i=hdr.indexOf('RANK'),c=(tr&&i>=0)?tr.cells[i]:null,sp=c?c.querySelector('[title]'):null;
          r.cfgRankMoney=c?[(c.textContent||'').trim(),sp?sp.getAttribute('title'):null]:null;
          r.cfgRanked=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){var cc=(i>=0)?t.cells[i]:null;return cc&&/^[0-9]+$/.test((cc.textContent||'').trim());}).length;})();
        // IN-SAMPLE + LOCKBOX pools to exactly the in-sample PF and trade count
        r.cC=rd({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['is','lb'],resAxis:'pf',resXAxis:'wr'}, wcC);
        var tIsLb=tipOf('RAW CROWNED');r.pfIsLb=pfOf(tIsLb);r.trIsLb=trOf(tIsLb);
        r.cD=rd({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['is'],resAxis:'pf',resXAxis:'wr'}, wcC);
        var tIs=tipOf('RAW CROWNED');r.pfIs=pfOf(tIs);r.trIs=trOf(tIs);
        // run rows: a zero-trade lockbox beside a normal one, on a drawdown axis
        var Z=JSON.parse(JSON.stringify(FIX));Z.id=String(+FIX.id+750001);Z.strategy='ZZERO_TR_1_0.py';Z.starred=false;
        Z.validate.lockbox=Object.assign({},Z.validate.lockbox,{trades:0,pnl:0,dd:0,pf:0,win_rate:0,sharpe:0,sortino:0,avg_loss:0,avg_win:0});
        var NN=JSON.parse(JSON.stringify(FIX));NN.id=String(+FIX.id+750002);NN.strategy='ZKAPPA_1_0.py';NN.starred=false;
        var wcR="var Z="+JSON.stringify(Z)+";var NN="+JSON.stringify(NN)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(Z),f(NN)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        r.cR=rd({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'raw',resXAxis:'dd',c2Tbl:true,resCols:'all'}, wcR);
        r.runTipZ=tipOf('#'+Z.id);r.runTipN=tipOf('#'+NN.id);
        r.runCellsZ=cellsOf('#'+Z.id);
        // (review round 4) the same two runs on money and on ROC over $ per trade (a whole-run measure, so only the
        //   vertical axis decides): the empty lockbox neither plots nor ranks; IN-SAMPLE + LOCKBOX still adds its $0
        function rankOf(key){var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
          var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf(key)>=0;})[0];
          var i=hdr.indexOf('RANK'),c=(tr&&i>=0)?tr.cells[i]:null,sp=c?c.querySelector('[title]'):null;
          return c?[(c.textContent||'').trim(),sp?sp.getAttribute('title'):null]:null;}
        r.cR2=rd({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'raw',resXAxis:'ppt',c2Tbl:true,resCols:'all'}, wcR);
        r.moneyTipZ=tipOf('#'+Z.id);r.moneyTipN=tipOf('#'+NN.id);r.moneyRankZ=rankOf('#'+Z.id);r.moneyRankN=rankOf('#'+NN.id);
        r.cR3=rd({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'roc',resXAxis:'ppt',c2Tbl:true,resCols:'all'}, wcR);
        r.rocTipZ=tipOf('#'+Z.id);r.rocTipN=tipOf('#'+NN.id);r.rocRankZ=rankOf('#'+Z.id);
        r.cR4=rd({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['is','lb'],resAxis:'raw',resXAxis:'ppt'}, wcR);
        r.isLbTipZ=tipOf('#'+Z.id);
      })();
      // -- case r_rawNullStretch (repair round 3): the engine saves a RAW configuration's stretch as null,
      //    never as a zero block, when it took no trades there (validate.py), so the zero-trade rule never
      //    reached a live RAW row and TRADES fell through to the whole-window count (3,205 against an empty
      //    lockbox, with EV R 0.00R and R / YR 0.0R built on it). (a) lockbox null beside a lockbox curve
      //    with no trade on it: LOCKBOX ticked reads TRADES 0, PF / WIN % / EV R / R / YR dash, DRAWDOWN says
      //    it took no trades; IN-SAMPLE + LOCKBOX is exactly the in-sample PF and count. (b) lockbox null and
      //    no curve (never measured): TRADES dashes with its reason - never the whole-window count, never the
      //    run's - and TRADES / YR, EV R, R / YR dash with it. (c) GATE rows with no lockbox block: TRADES
      //    dashes, never the pre-lockbox count.
      (function(){
        var CID=String(FIX.id);
        var cand=((FIX.selection&&FIX.selection.candidates)||[]).filter(function(c){return c&&c.crowned;})[0]||null;
        var r=snap('r_rawNullStretch','OK');
        r.unc=[];function rd(p,wc){var c=doRender(p,wc);r.unc=r.unc.concat(sink.uncaught.slice(0,5));return c;}
        function wcMod(mod){return "var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +mod
          +"runHistory=[doc];window._runFull={};window._runFull['"+CID+"']=doc;window._runFullOrder=['"+CID+"'];window._runHydrating={};window._c2Open=new Set();"
          +"window._runCfg={};window._runCfg['"+CID+"']=doc;";}
        var ZERO="(doc.selection.candidates||[]).forEach(function(c){if(c&&c.crowned){var b=(c.equity&&c.equity.final!=null)?c.equity.final:0;c.lockbox=null;c.lb_equity={cum:[],t:[],final:b,base:b};}});";
        var UNK="(doc.selection.candidates||[]).forEach(function(c){if(c&&c.crowned){c.lockbox=null;delete c.lb_equity;}});";
        var NOGLB="var GVd=doc.gate_validate||doc.ml_gate;((GVd&&GVd.candidates)||[]).forEach(function(c){delete c.lockbox;});";
        var H=['FAMILY','DRAWDOWN','PF','WIN %','EV R','R / YR','TRADES','TRADES / YR'];
        function cellsTr(tr){
          var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
          var o={};H.forEach(function(h){var i=hdr.indexOf(h),c=(i>=0&&tr)?tr.cells[i]:null,sp=c?c.querySelector('[title]'):null;
            o[h]=c?[(c.textContent||'').trim(),sp?sp.getAttribute('title'):null]:null;});return o;}
        function rawRow(){return [].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('RAW crowned')>=0;})[0]||null;}
        function tipOf(key){var tip=null;[].slice.call(d.querySelectorAll('[data-repoint] title')).forEach(function(t){
          if(tip===null&&(t.textContent||'').indexOf(key)>=0)tip=t.textContent;});return tip;}
        function pfOf(tip){var m=tip&&tip.match(/PF ([0-9]+[.][0-9]+)/);return m?parseFloat(m[1]):null;}
        function trOf(tip){var m=tip&&tip.match(/Trades ([0-9,.]+)/);return m?parseFloat(m[1].split(',').join('')):null;}
        function P(segs,tbl){var o={c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:segs,resAxis:'pf',resXAxis:'wr'};
          if(tbl){o.c2Tbl=true;o.resCols='all';}return o;}
        r.wholeTrd=(cand&&cand.metrics&&cand.metrics.num_trades!=null)?+cand.metrics.num_trades:null;
        r.isTrd=(cand&&cand.is_rng)?+cand.is_rng.num_trades:null;
        // (a) the lockbox took no trades
        r.a1=rd(P(['lb'],true), wcMod(ZERO));var ra=rawRow();r.aFound=!!ra;r.aLb=cellsTr(ra);
        r.a2=rd(P(['is','lb']), wcMod(ZERO));var t2=tipOf('RAW CROWNED');r.aPfIsLb=pfOf(t2);r.aTrIsLb=trOf(t2);
        r.a3=rd(P(['is']), wcMod(ZERO));var t3=tipOf('RAW CROWNED');r.aPfIs=pfOf(t3);r.aTrIs=trOf(t3);
        // (b) the lockbox was never measured
        r.b1=rd(P(['lb'],true), wcMod(UNK));var rb=rawRow();r.bFound=!!rb;r.bLb=cellsTr(rb);
        r.b2=rd(P(['is','lb'],true), wcMod(UNK));rb=rawRow();r.bIsLb=cellsTr(rb);
        // (c) GATE rows with no lockbox block
        r.c1=rd(P(['lb'],true), wcMod(NOGLB));
        r.gates=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){var c=cellsTr(t);return c.FAMILY&&c.FAMILY[0]==='GATE';})
          .map(function(t){return cellsTr(t).TRADES;});
      })();

      // -- case r_runZeroStretch (repair round 3): EXPLORE run rows saved the way the engine writes them.
      //    (Z) a lockbox that took no trades - profit factor 0, win rate 0, NO average win or loss - read as
      //    unknown grosses and blanked IN-SAMPLE, PF, WIN % and TRADES under a false 'folds overlap' reason;
      //    it must read exactly like the same run with its averages saved as 0 (Z0). (W) one walk-forward
      //    fold that took no trades (the cold-start fold) did the same. (NL) a fold whose every trade won
      //    saves its profit factor as null and must not blank them either. (B) IN-SAMPLE is read straight
      //    off the gate study's own measured slice (gate_validate.ungated_is), never derived from the fold
      //    rows or the run's own trade count - a run with no measured slice saved dashes it, with the true
      //    reason, and a fold-level quirk (a broken-even fold, P1) cannot leak into it.
      (function(){
        var r=snap('r_runZeroStretch','OK');
        r.unc=[];function rd(p,wc){var c=doRender(p,wc);r.unc=r.unc.concat(sink.uncaught.slice(0,5));return c;}
        function cl(o){return JSON.parse(JSON.stringify(o));}
        function folds(x){return (x.top10_results||[]).filter(function(q){return q&&q.fold!=null;});}
        var Z=cl(FIX);Z.id=String(+FIX.id+760001);Z.strategy='ZZERO_TR_1_0.py';Z.starred=false;
        Z.validate.lockbox=Object.assign({},Z.validate.lockbox,{trades:0,pnl:0,dd:0,pf:0,win_rate:0,sharpe:null,sortino:null,avg_win:null,avg_loss:null,pass:false});
        (function(){var e=Z.validate.equity,li=Z.validate.lb_idx;for(var i=li+1;i<e.length;i++)e[i]=e[li];})();
        var Z0=cl(Z);Z0.id=String(+FIX.id+760002);Z0.strategy='ZZEROB_1_0.py';Z0.validate.lockbox.avg_win=0;Z0.validate.lockbox.avg_loss=0;
        var W=cl(FIX);W.id=String(+FIX.id+760003);W.strategy='ZFOLD0_1_0.py';W.starred=false;
        (function(){var z=folds(W)[0];W.validate.total_trades=W.validate.total_trades-z.oos_trades;
          z.oos_trades=0;z.oos_wins=0;z.oos_pnl=0;z.oos_win_rate=0;z.oos_pf=0;})();
        var NL=cl(FIX);NL.id=String(+FIX.id+760004);NL.strategy='ZFOLDWIN_1_0.py';NL.starred=false;
        (function(){var z=folds(NL).slice().sort(function(a,b){return a.oos_trades-b.oos_trades;})[0];
          z.oos_wins=z.oos_trades;z.oos_pf=null;z.oos_pnl=Math.abs(z.oos_pnl);z.oos_win_rate=100;})();
        var B=cl(FIX);B.id=String(+FIX.id+760005);B.strategy='ZOVERLAP_1_0.py';B.starred=false;
        delete B.gate_validate.ungated_is;
        // (review round 4) three more shapes the engine writes, each beside a control that differs only in a figure
        //   that can be split: (AL) a fold whose every trade lost - profit factor 0 - against PF 1e-7; (LL) a lockbox
        //   whose every trade lost - pf 0, no average win - against average win 0; (LW) a lockbox whose every trade
        //   won - pf null, no average loss - against average loss 0. (P1) a fold that broke exactly even (PF 1.00,
        //   net 0): its grosses truly cannot be split, so only PF and EV R dash, naming that fold.
        var AL=cl(FIX);AL.id=String(+FIX.id+760006);AL.strategy='ZALLLOSS_1_0.py';AL.starred=false;
        (function(){var z=folds(AL)[4];z.oos_wins=0;z.oos_pf=0;z.oos_pnl=-Math.abs(z.oos_pnl);z.oos_win_rate=0;})();
        var ALc=cl(AL);ALc.id=String(+FIX.id+760007);ALc.strategy='ZALLLOSSC_1_0.py';(function(){folds(ALc)[4].oos_pf=1e-7;})();
        var LL=cl(FIX);LL.id=String(+FIX.id+760008);LL.strategy='ZLBLOSS_1_0.py';LL.starred=false;
        LL.validate.lockbox=Object.assign({},LL.validate.lockbox,{trades:5,win_rate:0,avg_win:null,avg_loss:100,pf:0,pnl:-500,dd:500,pass:false});
        var LLc=cl(LL);LLc.id=String(+FIX.id+760009);LLc.strategy='ZLBLOSSC_1_0.py';LLc.validate.lockbox.avg_win=0;
        var LW=cl(FIX);LW.id=String(+FIX.id+760010);LW.strategy='ZLBWIN_1_0.py';LW.starred=false;
        LW.validate.lockbox=Object.assign({},LW.validate.lockbox,{trades:5,win_rate:100,avg_win:100,avg_loss:null,pf:null,pnl:500,dd:0,pass:true});
        var LWc=cl(LW);LWc.id=String(+FIX.id+760011);LWc.strategy='ZLBWINC_1_0.py';LWc.validate.lockbox.avg_loss=0;
        var P1=cl(FIX);P1.id=String(+FIX.id+760012);P1.strategy='ZPFONE_1_0.py';P1.starred=false;
        (function(){var z=folds(P1)[1];z.oos_pnl=0;z.oos_pf=1.0;r.p1Fold=z.fold;})();
        var LIST=[Z,Z0,W,NL,B,AL,ALc,LL,LLc,LW,LWc,P1];
        r.nFolds=folds(FIX).length;
        var wc="var LST="+JSON.stringify(LIST)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=LST.map(f);window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();window._starRuns=[];";
        var H=['IN-SAMPLE','PF','WIN %','TRADES','EV R'];
        function grab(){var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()-]/g,'').trim();});
          var o={};LIST.forEach(function(x){
            var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('#'+x.id)>=0;})[0];
            if(!tr){o[x.strategy]=null;return;}
            var c={};H.forEach(function(h){var i=hdr.indexOf(h),td=(i>=0)?tr.cells[i]:null,sp=td?td.querySelector('[title]'):null;
              c[h]=td?[(td.textContent||'').trim(),sp?sp.getAttribute('title'):null]:null;});
            o[x.strategy]=c;});
          return o;}
        function P(segs){return {c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:segs,resAxis:'pf',resXAxis:'wr',c2Tbl:true,resCols:'all'};}
        r.cIs=rd(P(['is']),wc);r.is=grab();
        r.cWf=rd(P(['wf']),wc);r.wf=grab();
        r.cPre=rd(P(['is','wf']),wc);r.pre=grab();
        r.cLb=rd(P(['lb']),wc);r.lb=grab();
      })();

      // ── case e1_colorder: item 14 (owner: "move this junk to the end of the row, move
      //    the important stuff like the kpis up front. thats what i want to see first
      //    off"). RANK / FAMILY / RUN lead every EXPLORE table, CONFIG (the long name +
      //    badges) is last, in both the KEY and ALL column modes, and every row still
      //    carries exactly one cell per heading (no cell shifted under the wrong column).
      (function(){
        function readTbl(){
          var tr=d.querySelector('tr[data-rerow]');
          var tb=tr?tr.closest('table'):null;
          var hdr=tb?[].map.call(tb.querySelectorAll('tr th'),function(x){return (x.textContent||'').trim();}):[];
          var rows=tb?[].slice.call(tb.querySelectorAll('tr[data-rerow]')):[];
          var bad=rows.filter(function(x){return x.cells.length!==hdr.length;}).length;
          var lastTd=rows.length?rows[0].cells[rows[0].cells.length-1]:null;
          return {hdr:hdr,rowN:rows.length,bad:bad,
            lastIsConfig:lastTd?(lastTd.innerHTML||'').indexOf('permanent row handle')>=0:false};
        }
        var callKey=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',c2Tbl:true}, EMPTY_WIN);
        var r=snap('e1_colorder', callKey);
        var key=readTbl();
        r.keyHdr=key.hdr.slice(0,3);r.keyHdrLast=key.hdr[key.hdr.length-1];
        r.keyBad=key.bad;r.keyRows=key.rowN;r.keyLastIsConfig=key.lastIsConfig;r.keyN=key.hdr.length;
        var callAll=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',c2Tbl:true,resCols:'all'}, EMPTY_WIN);
        r.allCall=callAll;
        var all=readTbl();
        r.allHdr=all.hdr.slice(0,3);r.allHdrLast=all.hdr[all.hdr.length-1];
        r.allBad=all.bad;r.allRows=all.rowN;r.allLastIsConfig=all.lastIsConfig;r.allN=all.hdr.length;
      })();

      // ── case e1_scroll: item 15(a) (owner: "the table keeps snapping me back to the
      //    upper left"). A table's own scroll box keeps its scrollLeft / scrollTop across
      //    a re-render triggered by an UNRELATED pref (the vertical axis, same LEVEL /
      //    SHOW / strategy pick), and resets to the top-left once LEVEL genuinely changes
      //    the table set -- read straight off the real embedded research board, ALL
      //    columns so the table is wide enough to actually need a horizontal scrollbar.
      (function(){
        function scrollSet(){
          var raw=w.eval("(function(){try{"
            +"var sc=document.querySelector('[data-rescroll]');if(!sc)return JSON.stringify({found:false});"
            +"sc.scrollLeft=37;sc.scrollTop=41;sc.dispatchEvent(new Event('scroll'));"
            +"return JSON.stringify({found:true,l:sc.scrollLeft,t:sc.scrollTop});"
            +"}catch(e){return JSON.stringify({err:String(e&&e.stack?e.stack:e)});}})()");
          try{return JSON.parse(raw);}catch(e){return {err:'parse:'+String(e)};}
        }
        function scrollRead(){
          var raw=w.eval("(function(){"
            +"var sc=document.querySelector('[data-rescroll]');"
            +"return sc?JSON.stringify({found:true,l:sc.scrollLeft,t:sc.scrollTop}):JSON.stringify({found:false});"
            +"})()");
          try{return JSON.parse(raw);}catch(e){return {err:'parse:'+String(e)};}
        }
        var call=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',c2Tbl:true,resCols:'all'}, EMPTY_WIN);
        var r=snap('e1_scroll', call);
        var s0=scrollSet();
        r.foundBox=!!s0.found;r.setLeft=s0.l;r.setTop=s0.t;
        // unrelated pref change (vertical axis): same LEVEL / SHOW / strategy pick, so this
        //   is the SAME set of tables and must keep the scroll position.
        var call2=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',c2Tbl:true,resCols:'all',resAxis:'so'}, EMPTY_WIN);
        r.call2=call2;
        var s1=scrollRead();
        r.afterAxisLeft=s1.l;r.afterAxisTop=s1.t;
        // LEVEL actually changes: a genuinely different set of tables, so this must NOT
        //   carry the old position forward -- a fresh table still opens top-left.
        var call3=doRender({c2Screen:'explore',resLvl:'all',resFilt:'{"fam":["ORB"]}',c2Tbl:true,resCols:'all'}, EMPTY_WIN);
        r.call3=call3;
        var s2=scrollRead();
        r.afterLevelLeft=s2.l;r.afterLevelTop=s2.t;
      })();

      // ── case e1_split: item 15(b) (owner: "cant see the scroll to the right slider bc i
      //    have to scroll the entire page down"). In the SPLIT (side-by-side) layout the
      //    tables column is bounded to the viewport height so both of a table's own
      //    scrollbars stay on screen, and its header stays position:sticky. Every ORB
      //    study tile is forced open at once (BY STUDY, not the single pooled table) so the
      //    unbounded height this guards against is actually reached.
      (function(){
        doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',resView:'study',c2Tbl:true}, EMPTY_WIN);
        var openKeys=[].map.call(d.querySelectorAll('[data-restoggle]'),function(x){
          return decodeURIComponent(x.getAttribute('data-restoggle')||'');}).filter(Boolean);
        var call=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',resView:'study',
                           c2Tbl:true,resCols:'all',resSplit:'side',resOpen:openKeys}, EMPTY_WIN);
        var r=snap('e1_split', call);
        r.openTiles=openKeys.length;
        var raw=w.eval("(function(){try{"
          +"var sl=document.querySelector('[data-resplitl]');if(!sl)return JSON.stringify({found:false});"
          +"var rect=sl.getBoundingClientRect();"
          +"var th=document.querySelector('[data-rescroll] thead th');"
          +"var pos=th?getComputedStyle(th).position:null;"
          +"return JSON.stringify({found:true,height:Math.round(rect.height),maxHeightStyle:sl.style.maxHeight,"
          +"innerHeight:window.innerHeight,overflow:getComputedStyle(sl).overflow,thPos:pos});"
          +"}catch(e){return JSON.stringify({err:String(e&&e.stack?e.stack:e)});}})()");
        var res={};try{res=JSON.parse(raw);}catch(e){res={err:'parse:'+String(e)};}
        r.found=res.found;r.height=res.height;r.maxHeightStyle=res.maxHeightStyle;
        r.innerHeight=res.innerHeight;r.overflow=res.overflow;r.thPos=res.thPos;
        // (E1b) the bounded column is a scroller now, so it must keep its own scrollTop across an
        //   unrelated re-render (the vertical axis) like the table boxes inside it do.
        var raw2=w.eval("(function(){try{var sl=document.querySelector('[data-resplitl]');if(!sl)return JSON.stringify({found:false});"
          +"sl.scrollTop=120;sl.dispatchEvent(new Event('scroll'));return JSON.stringify({found:true,t:sl.scrollTop,room:sl.scrollHeight-sl.clientHeight});"
          +"}catch(e){return JSON.stringify({err:String(e&&e.stack?e.stack:e)});}})()");
        var s2={};try{s2=JSON.parse(raw2);}catch(e){s2={err:'parse:'+String(e)};}
        r.colSetTop=s2.t;r.colRoom=s2.room;
        r.call2=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',resView:'study',
                           c2Tbl:true,resCols:'all',resSplit:'side',resOpen:openKeys,resAxis:'so'}, EMPTY_WIN);
        r.colAfterAxisTop=w.eval("(function(){var sl=document.querySelector('[data-resplitl]');return sl?sl.scrollTop:null;})()");
      })();

      // ── case e1_sticky (E1b): items 14/15 - the identifying columns really stay put. The table
      //    is scrolled 300px right and 200px down inside its own box; the RANK / FAMILY / RUN body
      //    cells must sit exactly under their headers at the left edge with an opaque fill (so the
      //    KPI cells scrolling beneath cannot show through), the first KPI cell must have moved
      //    under them, and EVERY heading - the sortable RUN / MAR .. TRADES / YR ones included -
      //    must still be at the top of the box.
      (function(){
        var call=doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',c2Tbl:true,resCols:'all'}, EMPTY_WIN);
        var r=snap('e1_sticky', call);
        var raw=w.eval("(function(){try{"
          +"var sc=document.querySelector('[data-rescroll]');if(!sc)return JSON.stringify({found:false});"
          +"var tb=sc.querySelector('table'),tr=tb?tb.querySelector('tr[data-rerow]'):null;if(!tr)return JSON.stringify({found:false});"
          +"var ths=[].slice.call(tb.querySelectorAll('thead th'));"
          +"sc.scrollLeft=300;sc.scrollTop=200;"
          +"var s=sc.getBoundingClientRect();"
          +"var at=function(el){var q=el.getBoundingClientRect();return [Math.round(q.left-s.left),Math.round(q.top-s.top)];};"
          +"var o={found:true,sx:sc.scrollLeft,sy:sc.scrollTop,cellL:[],headL:[],cellPos:[],cellBg:[],headBg:[]};"
          +"for(var i=0;i<3;i++){o.cellL.push(at(tr.cells[i])[0]);o.headL.push(at(ths[i])[0]);"
          +"o.cellPos.push(getComputedStyle(tr.cells[i]).position);o.cellBg.push(getComputedStyle(tr.cells[i]).backgroundColor);"
          +"o.headBg.push(getComputedStyle(ths[i]).backgroundColor);}"
          +"o.kpiL=at(tr.cells[3])[0];"
          +"o.hdrTops=ths.map(function(x){return at(x)[1];});"
          +"o.offTop=ths.filter(function(x){var t=at(x)[1];return t<0||t>2;}).map(function(x){return (x.textContent||'').trim();});"
          +"return JSON.stringify(o);}catch(e){return JSON.stringify({err:String(e&&e.stack?e.stack:e)});}})()");
        var res={};try{res=JSON.parse(raw);}catch(e){res={err:'parse:'+String(e)};}
        r.res=res;
      })();
      // -- case e2_causes: item 12 - LEVEL ALL, SHOW RUNS, ORB strategy, WF stage.
      //    Part A: a synthetic FAIL run sits beside the REAL embedded ORB write-ups
      //    (LEVEL ALL reads the real registry too), so the note under the chart has
      //    to say why BOTH kinds of row are off screen: PLOT FAILURES hiding the
      //    run, older-run write-ups it cannot place, and write-ups recording no
      //    walk-forward money at all. Clicking the note's own PLOT FAILURES ON must
      //    plot the run, reading back the PF and ROC it actually saved. Part B:
      //    three fully controlled runs (LEVEL = AUTO VAL, so no registry rows at
      //    all) miss Sortino on purpose; the note must offer EV R with an honest
      //    count, and switching the axis to EV R must plot exactly that many.
      (function(){
        function mkRun(id,verdict){
          return "{id:"+id+",strategy:'ORB_3_6_1_0.py',starred:false,multiplier:20,date_from:'2010-06-07',date_to:'2026-08-01',"
            +"top10_results:[{fold:1,oos_pnl:15000,oos_trades:200,oos_pf:1.35,oos_wins:80}],"
            +"validate:{verdict:'"+verdict+"',total_trades:2100,total_win_rate:38,total_avg_win:900,total_avg_loss:-300,total_dd:31000,"
            +"windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']}}}";}
        function findNote(){
          var cands=[].filter.call(d.querySelectorAll('div'),function(x){
            return x.querySelector('b')&&/not on this chart/.test(x.textContent||'');});
          cands.sort(function(a,b){return (a.textContent||'').length-(b.textContent||'').length;});
          return cands[0]||null;}

        // part A -----------------------------------------------------------
        var wcA="runHistory=[];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();"
          +"runHistory=["+mkRun(990325,'FAIL')+"];";
        var callA=doRender({c2Screen:'explore',resLvl:'all',resShow:'runs',resFilt:{fam:['ORB']},resSegs:['wf'],resAxis:'pf',resXAxis:'roc',c2Tbl:true}, wcA);
        var r=snap('e2_causes', callA);
        r.myPointBefore=!!d.querySelector('[data-repoint="runs:990325"]');
        var note=findNote();
        r.noteText=note?note.textContent:null;
        var failBtn=note?note.querySelector('[data-resfail]'):null;
        r.failBtnFound=!!failBtn;
        r.causeA=w.eval('window._reCause');
        if(failBtn&&failBtn.onclick)failBtn.onclick();
        r.myPointAfter=!!d.querySelector('[data-repoint="runs:990325"]');
        var tr=d.querySelector('tr[data-rerow="runs:990325"]');
        if(tr){
          var hdr=[].map.call(tr.closest('table').querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$]/g,'').trim();});
          var iPf=hdr.indexOf('PF'),iRoc=-1;hdr.forEach(function(h,i){if(h.indexOf('ROC')===0&&iRoc<0)iRoc=i;});
          r.myPf=(tr.cells[iPf]||{}).textContent;
          r.myRoc=(tr.cells[iRoc]||{}).textContent;}

        // part B -----------------------------------------------------------
        var wcB="runHistory=[];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();"
          +"runHistory=["+mkRun(990401,'PASS')+","+mkRun(990402,'PASS')+","+mkRun(990403,'PASS')+"];";
        var callB1=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resFilt:{fam:['ORB']},resSegs:['wf'],resAxis:'so',resXAxis:'roc',c2Tbl:true}, wcB);
        // (E2b) ||{} - on a build without item 12 there is no tally; the case must FAIL on its
        //   assertions, not throw and turn the whole probe INCONCLUSIVE (the E2 original did).
        var causeB1=w.eval('window._reCause')||{};
        r.callB1=callB1;r.causeB1=causeB1;
        r.evrOffer=(causeB1.measAltY||[]).filter(function(x){return x.m==='evr';})[0]||null;
        var callB2=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resFilt:{fam:['ORB']},resSegs:['wf'],resAxis:'evr',resXAxis:'roc',c2Tbl:true}, wcB);
        var causeB2=w.eval('window._reCause')||{};
        r.callB2=callB2;r.plottedAfterSwitch=causeB2.plotted;
      })();

      // -- case e2_wryears: item 13 - a real write-up (registry) row that records
      //    IS + LOCKBOX but no WALK-FORWARD (row 1185, study orb6evr), citing a run
      //    that is NOT loaded here, so its own recorded window is the only one it
      //    has. LOCKBOX ticked alone must dash ROC % / YR with the new reason
      //    instead of dividing the lockbox money by the whole sixteen-year window;
      //    ticking every stretch it records must still show a number.
      (function(){
        var wc="runHistory=[];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        function rocFor(segs){
          var call=doRender({c2Screen:'explore',resLvl:'all',resShow:'runs',resFilt:{fam:['ORB']},resSegs:segs,c2Tbl:true}, wc);
          var tr=d.querySelector('tr[data-rerow="orb6evr:1185"]');
          if(!tr)return {call:call,found:false};
          var hdr=[].map.call(tr.closest('table').querySelectorAll('tr th'),function(x){return (x.textContent||'').trim();});
          var iRoc=-1;hdr.forEach(function(h,i){if(h.indexOf('ROC')===0&&iRoc<0)iRoc=i;});
          var cell=tr.cells[iRoc],span=cell?cell.querySelector('span'):null;
          return {call:call,found:true,text:cell?(cell.textContent||'').trim():null,title:span?(span.getAttribute('title')||''):null};}
        var lbOnly=rocFor(['lb']);
        var allTicked=rocFor(['is','wf','lb']);
        var r=snap('e2_wryears',(lbOnly.call==='OK'&&allTicked.call==='OK')?'OK':('ERR '+lbOnly.call+' / '+allTicked.call));
        r.lbOnly=lbOnly;r.allTicked=allTicked;
      })();

      // -- case e2_zerocause (E2b): the review round's no-trades rule meets item 12. Two copies of
      //    the fixture run, one whose LOCKBOX took no trades (the engine's zero block). LOCKBOX
      //    ticked, EV R up, DRAWDOWN across: the empty run leaves the chart. The note must count it
      //    as its own cause - "took no trades in the lockbox" - not as a row that "records no EV R",
      //    and must not offer a switch for it. IN-SAMPLE ticked (it traded there): no such cause.
      (function(){
        var Z=JSON.parse(JSON.stringify(FIX));Z.id=String(+FIX.id+770001);Z.strategy='ZZERO_TR_1_0.py';Z.starred=false;
        Z.validate.lockbox=Object.assign({},Z.validate.lockbox,{trades:0,pnl:0,dd:0,pf:0,win_rate:0,sharpe:0,sortino:0,avg_loss:0,avg_win:0});
        var NN=JSON.parse(JSON.stringify(FIX));NN.id=String(+FIX.id+770002);NN.strategy='ZKAPPA_1_0.py';NN.starred=false;
        var wc="var Z="+JSON.stringify(Z)+";var NN="+JSON.stringify(NN)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(Z),f(NN)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        function findNote(){
          var cands=[].filter.call(d.querySelectorAll('div'),function(x){
            return x.querySelector('b')&&/not on this chart/.test(x.textContent||'');});
          cands.sort(function(a,b){return (a.textContent||'').length-(b.textContent||'').length;});
          return cands[0]||null;}
        var call=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'evr',resXAxis:'dd',resFail:'1',c2Tbl:true}, wc);
        var r=snap('e2_zerocause', call);
        r.cause=w.eval('window._reCause');
        var note=findNote();
        r.noteText=note?note.textContent:null;
        r.noteBtns=note?note.querySelectorAll('[data-resstagealt],[data-resaxis],[data-resxaxis],[data-reshow],[data-resloadall]').length:null;
        r.zPt=!!d.querySelector('[data-repoint$=":'+Z.id+'"]');
        r.nPt=!!d.querySelector('[data-repoint$=":'+NN.id+'"]');
        r.callIs=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['is'],resAxis:'evr',resXAxis:'dd',resFail:'1',c2Tbl:true}, wc);
        r.causeIs=w.eval('window._reCause');
      })();
      // ---- REPAIR ROUND 4 (patch_R4.py) ------------------------------------------------------
      function r4Note(){
        var cands=[].filter.call(d.querySelectorAll('div'),function(x){
          return x.querySelector('b')&&/not on this chart/.test(x.textContent||'')&&!x.querySelector('svg');});
        cands.sort(function(a,b){return (a.textContent||'').length-(b.textContent||'').length;});
        return cands[0]||null;}
      function r4Win(runs){return "runHistory="+JSON.stringify(runs)+";window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";}
      function r4Row(key){var tr=d.querySelector('tr[data-rerow="'+key+'"]');if(!tr)return null;
        var hs=[].map.call(tr.closest('table').querySelectorAll('thead th'),function(x){return (x.textContent||'').replace(/[^A-Z0-9 /%$]/g,'').trim();});
        var o={};for(var i=0;i<tr.cells.length;i++){var c=tr.cells[i],sp=c.querySelector('span[title]');
          o[hs[i]]={t:(c.textContent||'').trim(),tip:sp?(sp.getAttribute('title')||''):''};}
        return o;}
      function r4Pts(){return d.querySelectorAll('[data-repoint]').length;}

      // -- case r4_wrwhole: a write-up's trade count is whole-row, so TRADES / YR and R / YR must divide it by
      //    the row's whole window on every tick even when its cited run is loaded (it read 2,609 and 420R on
      //    LOCKBOX). Money per year keeps the run's LOCKBOX dates; IN-SAMPLE is never dated off the run.
      (function(){
        var R234={id:234,strategy:'ORB_3_6_1_0.py',starred:false,multiplier:20,instrument:'NQ',date_from:'2010-06-07',date_to:'2026-08-13',timestamp:'2026-08-14T00:00:00Z',
          validate:{verdict:'PASS',total_trades:2607,total_win_rate:47.5,total_avg_win:900,total_avg_loss:-300,total_dd:1400,
            windows:{optimize:['2010-06-07','2025-08-13'],wf_split:'2016-10-12',lockbox:['2025-08-13','2026-08-13']},
            lockbox:{pnl:4400,trades:160,pf:1.3,win_rate:47,dd:600,pass:true}}};
        function read(segs,win,show){
          var call=doRender({c2Screen:'explore',resLvl:'all',resShow:show,resFilt:'{"fam":["ORB"]}',resSegs:segs,resAxis:'rpy',resXAxis:'pf',resFail:'1',resCols:'all',c2Tbl:true},win);
          var o=r4Row('orbmoney:1741')||{};
          var p=d.querySelector('[data-repoint="orbmoney:1741"] title');
          var mm=p?String(p.textContent).match(new RegExp('R / YR (-?[0-9.]+)')):null;
          return {call:call,found:!!o['TRADES'],trd:(o['TRADES']||{}).t,tpy:(o['TRADES / YR']||{}).t,tpyTip:(o['TRADES / YR']||{}).tip,
            rpy:(o['R / YR']||{}).t,roc:(o['ROC % / YR']||{}).t,rocTip:(o['ROC % / YR']||{}).tip,axis:mm?mm[1]:null};}
        var lbL=read(['lb'],r4Win([R234]),'configs');
        var allL=read(['is','wf','lb'],r4Win([R234]),'configs');
        var isL=read(['is'],r4Win([R234]),'configs');
        var lbN=read(['lb'],EMPTY_WIN,'runs');
        var ok=[lbL,allL,isL,lbN].every(function(x){return x.call==='OK';});
        var r=snap('r4_wrwhole',ok?'OK':('ERR '+[lbL.call,allL.call,isL.call,lbN.call].join(' / ')));
        r.lbL=lbL;r.allL=allL;r.isL=isL;r.lbN=lbN;
      })();

      // -- case r4_wfpool: the LEADERBOARD WF stage pools folds the way EXPLORE's run rows do. An all-loss fold
      //    (saved PF 0) used to be dropped from the pool (PF 2.00 against EXPLORE's 1.54); a fold that broke
      //    exactly even leaves the pooled PF unknown.
      (function(){
        function mk(id,folds){return {id:id,strategy:'NQDIP_1_0.py',starred:true,multiplier:20,instrument:'NQ',timeframe:'5m',date_from:'2010-06-07',date_to:'2026-06-29',timestamp:'2026-08-14T00:00:00Z',
          best_pnl_usd:40000,best_dd_usd:8000,best_pf:1.6,best_trades:60,best_win_rate:50,top10_results:folds,
          validate:{verdict:'PASS',total_trades:100,total_win_rate:48,total_avg_win:60,total_avg_loss:-40,total_dd:300,equity:[0,100,200,300,400,500,600,700,800,900,1000],lb_idx:8,
            windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']},lockbox:{pnl:200,trades:10,pf:1.5,win_rate:50,dd:100,pass:true}}};}
        var A=mk(990500,[{fold:1,oos_pnl:500,oos_trades:20,oos_pf:2.0,oos_wins:10},{fold:2,oos_pnl:-150,oos_trades:3,oos_pf:0,oos_wins:0}]);
        var B=mk(990501,[{fold:1,oos_pnl:500,oos_trades:20,oos_pf:2.0,oos_wins:10},{fold:2,oos_pnl:0,oos_trades:4,oos_pf:1.0,oos_wins:2}]);
        function big(){return [].map.call(d.querySelectorAll('.c2-big'),function(x){return (x.textContent||'').trim();});}
        var calls=[],res={};
        calls.push(doRender({c2Screen:'lead',c2Stage:'wf',c2Rank:'pf'},r4Win([A])));res.leadPfA=big();
        calls.push(doRender({c2Screen:'lead',c2Stage:'wf',c2Rank:'rpy'},r4Win([A])));res.leadRpyA=big();
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['wf'],resAxis:'evr',resXAxis:'pf',resCols:'all',c2Tbl:true},r4Win([A])));
        var o=r4Row('runs:990500')||{};res.expPf=(o['PF']||{}).t;res.expRpy=(o['R / YR']||{}).t;
        calls.push(doRender({c2Screen:'lead',c2Stage:'wf',c2Rank:'pf'},r4Win([B])));res.leadPfB=big();
        var r=snap('r4_wfpool',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r4_failnote: hidden failures are counted under PLOT FAILURES only when they would be drawn.
      (function(){
        function mkRun(id,verdict){
          return {id:id,strategy:'ORB_3_6_1_0.py',starred:false,multiplier:20,date_from:'2010-06-07',date_to:'2026-08-01',
            top10_results:[{fold:1,oos_pnl:15000,oos_trades:200,oos_pf:1.35,oos_wins:80}],
            validate:{verdict:verdict,total_trades:2100,total_win_rate:38,total_avg_win:900,total_avg_loss:-300,total_dd:31000,
              windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']}}};}
        var calls=[],res={};
        // (i) the default board with failures hidden: 611 hidden failures used to raise the note on their own
        calls.push(doRender({c2Screen:'explore',resLvl:'all',resAxis:'raw',resXAxis:'dd'},EMPTY_WIN));
        var n=r4Note(),C=w.eval('window._reCause')||{};
        res.defNote=n?n.textContent.slice(0,240):null;res.defFail=C.fail;res.defFailHidden=C.failHidden;
        // (ii) a failed run with no walk-forward Sortino, Sortino up: the switch would place nothing
        // (deferred round, D14) LOAD ALL is only offered while the loaded list is capped, so this one-run list stands for a capped one
        var WR=r4Win([mkRun(990325,'FAIL')])+"runsLimit=1;";
        calls.push(doRender({c2Screen:'explore',resLvl:'all',resShow:'runs',resFilt:{fam:['ORB']},resSegs:['wf'],resAxis:'so',resXAxis:'roc',c2Tbl:true},WR));
        n=r4Note();C=w.eval('window._reCause')||{};
        res.soNote=n?n.textContent.slice(0,300):null;res.soFailBtn=n?!!n.querySelector('[data-resfail]'):null;res.soOlder=C.older;
        // (iii) the same board on PF: the failed run places, so the button carries the count and draws exactly that many
        calls.push(doRender({c2Screen:'explore',resLvl:'all',resShow:'runs',resFilt:{fam:['ORB']},resSegs:['wf'],resAxis:'pf',resXAxis:'roc',c2Tbl:true},WR));
        n=r4Note();C=w.eval('window._reCause')||{};
        var fb=n?n.querySelector('[data-resfail]'):null,lb=n?n.querySelector('[data-resloadall]'):null;
        res.pfOlder=C.older;res.pfFail=C.fail;res.pfBtnTxt=fb?fb.textContent:null;res.loadTip=lb?(lb.getAttribute('title')||''):null;
        res.pfPlotted=r4Pts();
        if(fb&&fb.onclick)fb.onclick();
        res.pfPlottedAfter=r4Pts();
        w.eval('runsLimit=75');
        var r=snap('r4_failnote',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r4_relnote: CHAMPION skips are their own cause and every row the chart pass read is counted.
      (function(){
        var call=doRender({c2Screen:'explore',resLvl:'all',resRel:'crown',resFail:'1',resAxis:'evr',resXAxis:'so'},EMPTY_WIN);
        var C=w.eval('window._reCause')||{},n=r4Note();
        var r=snap('r4_relnote',call);
        r.rel=C.rel;r.shownN=w.eval('window._reShownN');
        r.sum=(C.plotted||0)+(C.fail||0)+(C.older||0)+(C.gone||0)+(C.zero||0)+(C.rel||0)+(C.missBoth||0)+(C.missX||0)+(C.missY||0)+(C.missGN||0);
        r.head=(n&&n.querySelector('b'))?n.querySelector('b').textContent:null;
      })();

      // -- case r4_offers: SWEEPS, LOCKBOX, MAR up, DRAWDOWN across (394 plotted). 'IS 225' used to be offered for
      //    a switch that left 225 points in all. Every offer now names the total after the click and beats now.
      (function(){
        var P={c2Screen:'explore',resLvl:'sweep',resSegs:['lb'],resAxis:'ratio',resXAxis:'dd'};
        var calls=[doRender(P,EMPTY_WIN)];
        var C=w.eval('window._reCause')||{},now=r4Pts(),offers=[];
        (C.segAlt||[]).forEach(function(a){offers.push({lbl:'tick '+a.seg.join('+'),set:{resSegs:a.seg},n:a.n});});
        (C.measAltY||[]).forEach(function(a){offers.push({lbl:'up '+a.m,set:{resAxis:a.m},n:a.n});});
        (C.measAltX||[]).forEach(function(a){offers.push({lbl:'across '+a.m,set:{resXAxis:a.m},n:a.n});});
        offers.slice(0,3).forEach(function(o){var p=JSON.parse(JSON.stringify(P));Object.keys(o.set).forEach(function(k){p[k]=o.set[k];});
          calls.push(doRender(p,EMPTY_WIN));o.after=r4Pts();});
        var r=snap('r4_offers',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        r.now=now;r.plotted=C.plotted;r.offers=offers.map(function(o){return {lbl:o.lbl,n:o.n,after:(o.after==null?null:o.after)};});
      })();

      // -- case r4_tpydash: a whole-row count over a whole-row window is not dashed by a partial stretch tick.
      (function(){
        function cnt(segs){
          var call=doRender({c2Screen:'explore',resLvl:'sweep',resView:'one',resSegs:segs,resCols:'all',c2Tbl:true},EMPTY_WIN);
          var tb=d.querySelector('[data-rescroll] table');if(!tb)return {call:call,found:false};
          var hdr=[].map.call(tb.querySelectorAll('thead th'),function(x){return (x.textContent||'').trim();});
          var iT=-1;hdr.forEach(function(h,i){if(iT<0&&h.indexOf('TRADES / YR')===0)iT=i;});
          var num=0,dash=0,b55=null;
          [].forEach.call(tb.querySelectorAll('tr[data-rerow]'),function(tr){var c=tr.cells[iT];var t=c?(c.textContent||'').trim():'';
            if(t==='—'||!t)dash++;else num++;if(tr.getAttribute('data-rerow')==='book55:1733')b55=t;});
          return {call:call,found:iT>=0,num:num,dash:dash,b55:b55};}
        var lb=cnt(['lb']),all=cnt(['is','wf','lb']);
        var r=snap('r4_tpydash',(lb.call==='OK'&&all.call==='OK')?'OK':('ERR '+lb.call+' / '+all.call));
        r.lb=lb;r.all=all;
      })();
      // ---- REVIEW ROUND 5 (patch_R4.py R4-5 .. R4-9) -------------------------------------------
      var R5DASH=String.fromCharCode(8212);

      // -- case r5_rawpre: a RAW configuration with IN-SAMPLE + WALK-FWD ticked reads the engine's saved optimize-window
      //    block (cal.pre) - DRAWDOWN, MAR, SHARPE and SORTINO used to dash under a 'no combined block' hover.
      (function(){
        var cum=[];for(var i=0;i<160;i++)cum.push(Math.round(i*9+30*Math.sin(i/3)));
        var lbcum=[];for(var i2=0;i2<40;i2++)lbcum.push(1400+i2*8);
        var c1={params:{a:1},is_pnl:500,wf_oos_pnl:900,folds_held:6,crowned:true,equity:{cum:cum},
          metrics:{total_pnl:1400,num_trades:300,profit_factor:1.4,win_rate:45,max_drawdown:-120,avg_pnl:4.67},
          cal:{is:{total_pnl:500,num_trades:100,win_rate:44,profit_factor:1.3,max_drawdown:-80,wins:44,losses:56,sharpe:0.9,sortino:1.2},
               wf:{total_pnl:900,num_trades:200,win_rate:45.5,profit_factor:1.45,max_drawdown:-100,wins:91,losses:109,sharpe:1.1,sortino:1.5},
               pre:{total_pnl:1400,num_trades:300,win_rate:45,profit_factor:1.4,max_drawdown:-120,wins:135,losses:165,sharpe:1.05,sortino:1.45}},
          lockbox:{total_pnl:300,num_trades:40,win_rate:50,profit_factor:1.6,max_drawdown:-50,wins:20,losses:20,sharpe:1.3,sortino:1.9},
          lb_equity:{cum:lbcum,final:1700,base:1400}};
        c1.is_rng=c1.cal.is;c1.wf_rng=c1.cal.wf;
        var lite={id:'995501',strategy:'NOISE_1_0.py',starred:0,multiplier:20,instrument:'NQ',timeframe:'5m',date_from:'2010-06-07',date_to:'2026-06-29',timestamp:'2026-09-01T00:00:00Z',
          validate:{verdict:'PASS',windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']}}};
        var full=JSON.parse(JSON.stringify(lite));full.selection={candidates:[c1]};
        full.gate_validate={span:['2010-06-07','2026-06-29'],wf_range:['2016-10-12','2025-06-29'],lockbox_from:'2025-06-29'};
        var WC="runHistory=["+JSON.stringify(lite)+"];window._runFull={};window._runCfg={'995501':"+JSON.stringify(full)+"};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();window._starRuns=[];";
        function readCfg(){var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return /#995501 RAW crowned/.test(t.textContent||'');})[0];
          if(!tr)return {found:false};
          var hs=[].map.call(tr.closest('table').querySelectorAll('thead th'),function(x){return (x.textContent||'').replace(/[^A-Z0-9 /%$]/g,'').trim();});
          var o={found:true};hs.forEach(function(h,j){var c=tr.cells[j];if(!c||o[h]!==undefined)return;var sp=c.querySelector('span[title]');
            o[h]={t:(c.textContent||'').trim(),tip:sp?(sp.getAttribute('title')||''):''};});return o;}
        var calls=[],res={};
        [['is','wf'],['is'],['is','lb']].forEach(function(sg){
          calls.push(doRender({c2Screen:'explore',resLvl:'all',resShow:'configs',resCfgRun:['995501'],resSegs:sg,c2Tbl:true,resCols:'all',resView:'one',resAxis:'dd',resXAxis:'so'},WC));
          var o=readCfg(),k=sg.join('+'),keep={found:o.found,pts:r4Pts()};
          ['DRAWDOWN','MAR','SHARPE','SORTINO','PF','TRADES'].forEach(function(h){if(o[h]){keep[h]=o[h].t;keep[h+'_tip']=o[h].tip.slice(0,160);}});
          res[k]=keep;});
        var r=snap('r5_rawpre',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        r.res=res;
      })();

      // -- case r5_rbpf0: RUNBOARD on LB, RANK BY PF. A lockbox that took 12 trades and lost them all prints PF 0.00, ranks
      //    below the runs with a figure and above the zero-trade lockbox, and stays in the TOP 10 WORST and BEST lists.
      (function(){
        function mk(id,strat,lb){return {id:id,strategy:strat,starred:0,multiplier:20,instrument:'NQ',timeframe:'5m',date_from:'2010-06-07',date_to:'2026-06-29',timestamp:'2026-08-1'+(id%10)+'T00:00:00Z',
          best_pnl_usd:40000,best_dd_usd:8000,best_pf:1.6,best_trades:600,best_win_rate:45,scope:'🧪 Auto-Validate',
          top10_results:[{fold:1,oos_pnl:500,oos_trades:40,oos_pf:1.4,oos_wins:18},{fold:2,oos_pnl:300,oos_trades:30,oos_pf:1.3,oos_wins:14}],
          validate:{verdict:'PASS',total_trades:900,total_win_rate:45,total_avg_win:60,total_avg_loss:-40,total_dd:500,is_sharpe:1,total_sharpe:1,
            equity:[0,100,200,300,400,500,600,700,800,900,1000,1100],lb_idx:10,passed:8,total_gates:10,
            windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']},lockbox:lb}};}
        var runs=[mk(995601,'NOISE_1_0.py',{pnl:-30,trades:12,pf:0,win_rate:0,dd:35,pass:false}),
          mk(995602,'ORB_3_6_1_0.py',{pnl:100,trades:20,pf:1.5,win_rate:50,dd:20,pass:true}),
          mk(995603,'TTM_SQZ_1_0.py',{pnl:40,trades:25,pf:1.1,win_rate:40,dd:30,pass:true}),
          mk(995604,'ENGUQ_1_0.py',{pnl:0,trades:0,pf:0,win_rate:0,dd:0,pass:false})];
        var WC=r4Win(runs)+"window._starRuns=[];";
        function side(){return [].map.call(d.querySelectorAll('[data-rank-run]'),function(x){
          var v=[].filter.call(x.children,function(c){return /flex:0 0 56px/.test(c.getAttribute('style')||'');})[0];
          return [x.getAttribute('data-rank-run'),v?(v.textContent||'').trim():null];});}
        function grid(){var pfTr=[].filter.call(d.querySelectorAll('tr'),function(t){return t.cells.length>2&&(t.cells[0].textContent||'').trim()==='PF';})[0];
          if(!pfTr)return null;var tb=pfTr.closest('table'),hr=tb.querySelector('tr');
          var ids=[].map.call(hr.cells,function(c){var m2=(c.textContent||'').match(/#(99560[0-9])/);return m2?m2[1]:null;});
          var o={order:ids.filter(Boolean),pf:{}};ids.forEach(function(id,j){if(id)o.pf[id]=(pfTr.cells[j].textContent||'').trim();});return o;}
        var calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'lb',rbRank:'pf',rbSide:'worst'},WC));res.worst=side();res.grid=grid();
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'lb',rbRank:'pf',rbSide:'best'},WC));res.best=side();
        var r=snap('r5_rbpf0',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r5_lbonly: a write-up recording only a LOCKBOX figure beside a whole-row TOTAL (row ttmsqz5:696) must not
      //    divide a one-year lockbox by its sixteen-year window on any tick; a loaded run dates the lockbox it covers.
      (function(){
        function cells(key){var o=r4Row(key)||{};var k={found:!!o['TRADES']};
          ['MAR','ROC % / YR','PER YEAR','YEARS','TRADES / YR'].forEach(function(h){if(o[h]){k[h]=o[h].t;k[h+'_tip']=o[h].tip.slice(0,220);}});return k;}
        var R289={id:289,strategy:'TTM_SQZ_ES_1_0.py',starred:false,multiplier:50,instrument:'ES',timeframe:'30m',date_from:'2010-06-07',date_to:'2026-06-30',timestamp:'2026-08-20T00:00:00Z',
          validate:{verdict:'PASS',total_trades:276,total_win_rate:40,total_avg_win:900,total_avg_loss:-300,total_dd:3740,
            windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-30','2026-06-30']},
            lockbox:{pnl:100,trades:30,pf:1.6,win_rate:45,dd:60,pass:true}}};
        var calls=[],res={};
        function sweep(segs){calls.push(doRender({c2Screen:'explore',resLvl:'sweep',resView:'one',resBasis:'year',resFilt:JSON.stringify({fam:['TTM']}),resSegs:segs,c2Tbl:true,resCols:'all',resAxis:'roc',resXAxis:'dd'},EMPTY_WIN));
          var k=cells('ttmsqz5:696');k.pt=!!d.querySelector('[data-repoint="ttmsqz5:696"]');return k;}
        function cfg(segs,runs){calls.push(doRender({c2Screen:'explore',resLvl:'all',resShow:'configs',resView:'one',resBasis:'year',resFilt:JSON.stringify({fam:['TTM']}),resSegs:segs,c2Tbl:true,resCols:'all',resAxis:'roc',resXAxis:'dd'},r4Win(runs)));
          return cells('ttmsqz4:1026');}
        res.lb=sweep(['lb']);res.all=sweep(['is','wf','lb']);
        res.lbLoaded=cfg(['lb'],[R289]);res.wflbLoaded=cfg(['wf','lb'],[R289]);res.lbUnloaded=cfg(['lb'],[]);
        var r=snap('r5_lbonly',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r5_split: SPLIT layout on laptop-height windows. The table's horizontal scrollbar (its box's bottom edge)
      //    is inside both the tables column and the window at the page top, after a page scroll, and after a render
      //    made while the page was scrolled; a study opened by its header gets its box capped to the column too.
      (function(){
        var fr=document.getElementById('f');
        function size(W,H){fr.style.width=W+'px';fr.style.height=H+'px';void fr.offsetHeight;try{void d.body.offsetHeight;}catch(e){}return [w.innerWidth,w.innerHeight];}
        function visBox(){return [].filter.call(d.querySelectorAll('[data-rescroll]'),function(b){return b.offsetParent!==null&&b.querySelector('tr[data-rerow]');})[0]||null;}
        function kick(){try{w.dispatchEvent(new w.Event('scroll'));}catch(e){}}   // the scroll event this run does not fire itself
        function st(){var sl=d.querySelector('[data-resplitl]'),bx=visBox();if(!sl||!bx)return {none:true};
          var q=sl.getBoundingClientRect(),b=bx.getBoundingClientRect();
          return {inner:w.innerHeight,colBottom:Math.round(q.bottom),boxBottom:Math.round(b.bottom),hOver:bx.scrollWidth-bx.clientWidth,
            ok:(b.bottom<=q.bottom+1)&&(b.bottom<=w.innerHeight+1)&&(b.bottom>=0)};}
        var B={c2Screen:'explore',resLvl:'all',resFilt:'{"fam":["ORB"]}',resView:'one',resCols:'all',c2Tbl:true,resSplit:'side'};
        var calls=[],res={};
        [[1366,768],[1400,650]].forEach(function(sz){
          var o={};o.inner=size(sz[0],sz[1]);w.scrollTo(0,0);kick();
          calls.push(doRender(B,EMPTY_WIN));o.top=st();
          var sl=d.querySelector('[data-resplitl]');
          if(sl){w.scrollTo(0,Math.round(sl.getBoundingClientRect().top+w.pageYOffset));kick();o.scrolled=st();
            w.scrollTo(0,140);kick();var p=JSON.parse(JSON.stringify(B));p.resAxis='so';calls.push(doRender(p,EMPTY_WIN));
            w.scrollTo(0,0);kick();o.backTop=st();}
          res['h'+sz[1]]=o;});
        // BY STUDY: one study open, then a second opened by its header (no re-render)
        size(1366,768);w.scrollTo(0,0);
        calls.push(doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',resView:'study',c2Tbl:true},EMPTY_WIN));
        var keys=[].map.call(d.querySelectorAll('[data-restoggle]'),function(x){return decodeURIComponent(x.getAttribute('data-restoggle')||'');}).filter(Boolean);
        calls.push(doRender({c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',resView:'study',c2Tbl:true,resCols:'all',resSplit:'side',resOpen:keys.slice(0,1)},EMPTY_WIN));
        var hd=[].filter.call(d.querySelectorAll('[data-restoggle]'),function(x){return decodeURIComponent(x.getAttribute('data-restoggle')||'')!==keys[0];})[0];
        res.study={keys:keys.length};
        if(hd&&hd.onclick){hd.onclick();
          var sl2=d.querySelector('[data-resplitl]'),bd=d.querySelector('[data-rebody="'+CSS.escape(hd.getAttribute('data-restoggle'))+'"]');
          var bx2=bd?bd.querySelector('[data-rescroll]'):null;
          if(sl2&&bx2){var colH=parseFloat(sl2.style.maxHeight)||0,mh=parseFloat(bx2.style.maxHeight)||0;
            var off=bx2.getBoundingClientRect().top-sl2.getBoundingClientRect().top+sl2.scrollTop;
            res.study.colH=colH;res.study.mh=mh;res.study.off=Math.round(off);
            res.study.ok=(off+mh<=colH+1)||(mh<=colH&&off+200>colH);}}
        size(1400,900);w.scrollTo(0,0);
        var r=snap('r5_split',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r5_samemeas: the note's measure offers never propose the measure already on the other axis.
      (function(){
        var RUN={id:990326,strategy:'ORB_3_6_1_0.py',starred:false,multiplier:20,date_from:'2010-06-07',date_to:'2026-08-01',
          top10_results:[{fold:1,oos_pnl:15000,oos_trades:200,oos_pf:1.35,oos_wins:80}],
          validate:{verdict:'FAIL',total_trades:2100,total_win_rate:38,total_avg_win:900,total_avg_loss:-300,total_dd:31000,
            windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']}}};
        var WC="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
          +"runHistory=["+JSON.stringify(RUN)+",doc];window._runFull={};window._runFull[String(F.id)]=doc;window._runCfg={};window._runCfg[String(F.id)]=doc;window._runFullOrder=[String(F.id)];window._runHydrating={};window._c2Open=new Set();";
        var base={c2Screen:'explore',resLvl:'all',resShow:'runs',resFilt:'{"fam":["ORB"]}',resSegs:['wf'],c2Tbl:true};
        var calls=[],res={};
        [['so','pf'],['so','dd'],['pf','so'],['dd','so']].forEach(function(ax){
          var p=JSON.parse(JSON.stringify(base));p.resAxis=ax[0];p.resXAxis=ax[1];calls.push(doRender(p,WC));
          var C=w.eval('window._reCause')||{},n=r4Note();
          res[ax.join('_')]={y:ax[0],x:ax[1],up:(C.measAltY||[]).map(function(a){return a.m;}),across:(C.measAltX||[]).map(function(a){return a.m;}),
            btnUp:n?[].map.call(n.querySelectorAll('[data-resaxis]'),function(b){return b.getAttribute('data-resaxis');}):[],
            btnAcross:n?[].map.call(n.querySelectorAll('[data-resxaxis]'),function(b){return b.getAttribute('data-resxaxis');}):[]};});
        var r=snap('r5_samemeas',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        r.res=res;
      })();
      // ---- REVIEW ROUND 6 (patch_R4.py R4-10 .. R4-12) -----------------------------------------

      // -- case r6_evapx: RUNBOARD 1E matrix on FULL. A run that saved no whole-run trade count has its FULL count
      //    summed from the stretches, which the TRADES row marks ~. EV is that same count under the net, so it must
      //    carry the same ~, say so on hover, and never take the best-in-row mark off it: three runs on the same
      //    whole-run net read $43, $43 and $66, and only the summed count made the $66.
      (function(){
        function mk(id,strat,extra){
          var r={id:id,strategy:strat,starred:0,multiplier:20,instrument:'NQ',timeframe:'5m',date_from:'2010-06-07',date_to:'2026-06-29',
            timestamp:'2026-08-1'+(id%10)+'T00:00:00Z',best_pnl_usd:100000,best_dd_usd:20000,best_pf:1.5,best_trades:1000,best_win_rate:40,
            top10_results:[{fold:1,oos_pnl:1000,oos_trades:100,oos_pf:1.5,oos_wins:40},{fold:2,oos_pnl:500,oos_trades:80,oos_pf:1.25,oos_wins:30}],
            validate:{verdict:'PASS',total_trades:2000,total_win_rate:40,total_avg_win:150,total_avg_loss:-70,total_dd:900,total_sharpe:0.9,total_sortino:1.3,
              equity:[0,200,500,900,1400,1800,2300,2700,3100,3500,3900,4300],lb_idx:9,
              windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-29','2026-06-29']},
              lockbox:{pnl:400,trades:120,pf:1.6,win_rate:45,dd:150,pass:true,avg_win:20,avg_loss:-10,from:'2025-06-29',to:'2026-06-29'}}};
          if(extra)extra(r);return r;}
        var A=mk(990001,'ORB_3_6_1_0.py'),B2=mk(990002,'NOISE_1_0.py');
        var N=mk(990008,'VWAP_1_0.py',function(r){delete r.validate.total_trades;delete r.validate.total_avg_win;
          delete r.validate.total_avg_loss;delete r.validate.total_win_rate;});
        function grid(){
          var T=null;[].slice.call(d.querySelectorAll('table')).forEach(function(t){var x=t.textContent||'';
            if(!T&&/ROBUSTNESS/.test(x)&&/FOLDS HELD/.test(x))T=t;});
          if(!T)return {};
          var ids=[].map.call(T.querySelectorAll('thead th'),function(x){return x.getAttribute('data-rbc')||'';});
          var o={};
          [].forEach.call(T.querySelectorAll('tbody tr'),function(tr){
            if(tr.cells.length<2)return;
            var lbl=(tr.cells[0].textContent||'').trim();
            if(lbl!=='EV'&&lbl!=='TRADES'&&lbl!=='PF')return;
            var row={};
            for(var i=1;i<tr.cells.length;i++){var c=tr.cells[i],sp=c.querySelector('span[title]'),bb=c.querySelector('b');
              row[ids[i]||('c'+i)]={t:(c.textContent||'').trim(),apx:(c.textContent||'').indexOf('~')>=0,
                best:!!(bb&&/--green/.test(bb.getAttribute('style')||'')),tip:sp?(sp.getAttribute('title')||'').slice(0,200):''};}
            o[lbl]=row;});
          return o;}
        var WC=r4Win([A,B2,N]),calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'full',rbRank:'mar',rbHeat:false},WC));res.full=grid();
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'is',rbRank:'mar',rbHeat:false},WC));res.is=grid();
        var r=snap('r6_evapx',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r6_yrscol: EXPLORE on the PER YEAR basis. The YEARS column is the row's OWN recorded window: a
      //    write-up whose ticked money covers only part of it (row ttmsqz5:696; row ttmsqz4:1026 with the run it
      //    cites loaded) shows that length instead of a dash claiming the row records no window, and says on hover
      //    why PER YEAR and MAR / YR beside it dash. A run row still shows the stretches actually ticked.
      (function(){
        var COLS=['MAR','PER YEAR','YEARS','MAR / YR','TRADES / YR','TRADES','DATA WINDOW'];
        function cells(key){var o=r4Row(key)||{};var k={found:!!(o&&o['TRADES'])};
          if(o)COLS.forEach(function(h){if(o[h]){k[h]=o[h].t;k[h+'_tip']=o[h].tip.slice(0,300);}});return k;}
        function hdr(){var th=[].filter.call(d.querySelectorAll('th'),function(x){return (x.textContent||'').replace(/[^A-Z]/g,'')==='YEARS';})[0];
          return th?(th.getAttribute('title')||''):'';}
        function rowByText(rx){var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return rx.test(t.textContent||'');})[0];
          return tr?tr.getAttribute('data-rerow'):null;}
        var R289b={id:289,strategy:'TTM_SQZ_ES_1_0.py',starred:false,multiplier:50,instrument:'ES',timeframe:'30m',
          date_from:'2010-06-07',date_to:'2026-06-30',timestamp:'2026-08-20T00:00:00Z',
          validate:{verdict:'PASS',total_trades:276,total_win_rate:40,total_avg_win:900,total_avg_loss:-300,total_dd:3740,
            windows:{optimize:['2010-06-07','2025-06-29'],wf_split:'2016-10-12',lockbox:['2025-06-30','2026-06-30']},
            lockbox:{pnl:100,trades:30,pf:1.6,win_rate:45,dd:60,pass:true}}};
        var BAS={c2Screen:'explore',resView:'one',resBasis:'year',resFilt:'{"fam":["TTM"]}',c2Tbl:true,resCols:'all',resAxis:'roc',resXAxis:'dd'};
        function P6(extra){var p=JSON.parse(JSON.stringify(BAS));Object.keys(extra).forEach(function(k){p[k]=extra[k];});return p;}
        var calls=[],res={};
        calls.push(doRender(P6({resLvl:'sweep',resSegs:['lb']}),EMPTY_WIN));res.w1=cells('ttmsqz5:696');res.hdr=hdr();
        calls.push(doRender(P6({resLvl:'sweep',resSegs:['is','wf','lb']}),EMPTY_WIN));res.w3=cells('ttmsqz5:696');
        calls.push(doRender(P6({resLvl:'all',resShow:'configs',resSegs:['lb']}),r4Win([R289b])));res.loaded=cells('ttmsqz4:1026');
        calls.push(doRender(P6({resLvl:'all',resShow:'runs',resSegs:['lb']}),r4Win([R289b])));
        var k1=rowByText(/#289/);res.runLb=k1?cells(k1):{found:false};
        calls.push(doRender(P6({resLvl:'all',resShow:'runs',resSegs:['is','wf','lb']}),r4Win([R289b])));
        var k2=rowByText(/#289/);res.runAll=k2?cells(k2):{found:false};
        var r=snap('r6_yrscol',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();

      // -- case r6_split: SPLIT layout with the FILTERS sheet open - the ordinary state, since COLUMNS, ORDER and
      //    MIN TRADES live in that sheet. At 1366x768 and 1400x650 the table's bottom edge (its horizontal scrollbar)
      //    must be inside the column AND on screen with the page at the top, and after a page scroll the column must
      //    take the room the sheet gives back instead of keeping the height it had for the page at its top.
      (function(){
        var fr6=document.getElementById('f');
        function size6(W,H){fr6.style.width=W+'px';fr6.style.height=H+'px';void fr6.offsetHeight;try{void d.body.offsetHeight;}catch(e){}return w.innerHeight;}
        function kick6(){try{w.dispatchEvent(new w.Event('scroll'));}catch(e){}}
        function box6(){return [].filter.call(d.querySelectorAll('[data-rescroll]'),function(b){return b.offsetParent!==null&&b.querySelector('tr[data-rerow]');})[0]||null;}
        function st6(){var sl=d.querySelector('[data-resplitl]'),bx=box6();
          if(!sl||!bx)return {none:true};
          var q=sl.getBoundingClientRect(),b=bx.getBoundingClientRect(),cm=Math.round(parseFloat(sl.style.maxHeight)||0);
          return {inner:w.innerHeight,colTop:Math.round(q.top),colMax:cm,colBottom:Math.round(q.bottom),
            pos:w.getComputedStyle(sl).position,boxH:Math.round(b.height),boxBottom:Math.round(b.bottom),
            boxMax:Math.round(parseFloat(bx.style.maxHeight)||0),
            inside:(b.bottom<=q.bottom+1)&&(b.bottom<=w.innerHeight+1)&&(b.bottom>=0),
            reaches:(Math.round(q.top)+cm)>=(w.innerHeight-20)};}
        var B6={c2Screen:'explore',resLvl:'sweep',resFilt:'{"fam":["ORB"]}',resView:'one',resCols:'all',c2Tbl:true,resSplit:'side',c2Sheet:'filters'};
        var calls=[],res={};
        [[1366,768],[1400,650]].forEach(function(sz){
          var o={};size6(sz[0],sz[1]);w.scrollTo(0,0);kick6();
          calls.push(doRender(B6,EMPTY_WIN));o.top=st6();
          var sl=d.querySelector('[data-resplitl]');
          if(sl){w.scrollTo(0,Math.round(sl.getBoundingClientRect().top+w.pageYOffset));kick6();o.scrolled=st6();
            w.scrollTo(0,0);kick6();o.backTop=st6();}
          res['h'+sz[1]]=o;});
        size6(1400,900);w.scrollTo(0,0);kick6();
        var r=snap('r6_split',calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));
        Object.keys(res).forEach(function(k){r[k]=res[k];});
      })();
      // ---- DEFERRED ROUND (dfx_*): one case per re-verified finding. Each check is a named boolean computed here, and
      //      each case fails on 73.820. No backslash anywhere below: this JavaScript sits in a plain Python string.
      function dfxN(s){return String(s==null?'':s).split(String.fromCharCode(10)).join(' ').split(String.fromCharCode(9)).join(' ')
        .split(String.fromCharCode(160)).join(' ').replace(/ +/g,' ').trim();}
      function dfxClone(x){return JSON.parse(JSON.stringify(x));}
      function dfxWin(docs,extra){return "var __D="+JSON.stringify(docs)+";var __f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
        +"runHistory=__D.map(__f);window._runFull={};runHistory.forEach(function(x){window._runFull[String(x.id)]=x;});"
        +"window._runFullOrder=runHistory.map(function(x){return String(x.id);});window._runHydrating={};window._c2Open=new Set();window._runCfg={};window._wfoBad={};runsLimit=75;"
        +(extra||'');}
      function dfxRow(lbl){var o=null;[].forEach.call(d.querySelectorAll('tr'),function(tr){var c=tr.children;if(!c.length||o)return;if(dfxN(c[0].textContent)===lbl)o=[].slice.call(c,1);});return o||[];}
      function dfxCell(td){var t=td.querySelector('[title]');return {v:dfxN(td.textContent),best:!!td.querySelector('b[style*="color:var(--green)"]'),
        tip:t?(t.getAttribute('title')||''):'',bg:(td.style&&td.style.background)||''};}
      function dfxTips(sub){return [].map.call(d.querySelectorAll('[title]'),function(e){return e.getAttribute('title')||'';}).filter(function(s){return s.indexOf(sub)>=0;});}
      function dfxNote(){var c=[].filter.call(d.querySelectorAll('div'),function(x){return x.querySelector('b')&&/not on this chart/.test(x.textContent||'');});
        c.sort(function(a,b){return (a.textContent||'').length-(b.textContent||'').length;});return c[0]?dfxN(c[0].textContent):'';}
      function dfxCase(name,calls,ck,info){var r=snap(name,calls.every(function(c){return c==='OK';})?'OK':('ERR '+calls.join(' / ')));r.ck=ck;r.info=info||{};return r;}
      function dfxLbRun(id,name,lb){var x=dfxClone(FIX);x.id=String(id);x.strategy=name;x.starred=false;x.validate.lockbox=Object.assign({},x.validate.lockbox,lb);return x;}

      // D03 - MIN TRADES note: a configuration row judged on its ticked stretches added up is not 'judged on a WHOLE-RUN count'
      (function(){var CID=String(FIX.id),F=dfxClone(FIX),cand=(((F.selection||{}).candidates)||[]).filter(function(c){return c&&c.crowned;})[0];
        if(cand){cand.is_rng.num_trades=50;cand.wf_rng.num_trades=60;cand.lockbox.num_trades=40;}
        var calls=[],tip={};
        [['is','lb'],['is','wf','lb']].forEach(function(segs){
          calls.push(doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:segs,resAxis:'pf',resXAxis:'wr',resMinTrd:250},dfxWin([F],"window._runCfg['"+CID+"']=runHistory[0];")));
          tip[segs.join('+')]=dfxTips('thin sample').join(' || ');});
        calls.push(doRender({c2Screen:'explore',resLvl:'sweep',resSegs:['lb'],resAxis:'pf',resXAxis:'wr',resMinTrd:250},dfxWin([])));
        tip.sweep=dfxTips('thin sample').join(' || ');
        dfxCase('dfx_d03',calls,{
          'the fixture has a crowned candidate':!!cand,
          'IS + LOCKBOX: the thin-sample note is there':tip['is+lb'].indexOf('left off the chart for a thin sample')>=0,
          'IS + LOCKBOX: no configuration row is called judged on a WHOLE-RUN count':tip['is+lb'].indexOf('WHOLE-RUN count')<0,
          'all three: no configuration row is called judged on a WHOLE-RUN count':tip['is+wf+lb'].indexOf('thin sample')>=0&&tip['is+wf+lb'].indexOf('WHOLE-RUN count')<0,
          'write-ups are, and the reason says they record no per-stage count':tip.sweep.indexOf('judged on a WHOLE-RUN count rather than the ticked stretches, because they record no per-stage trade count')>=0},
          {isLb:tip['is+lb'].slice(0,260),sweep:(tip.sweep.match(/Of those[^.]*[.]/)||[''])[0]});})();

      // D04 - RUNBOARD FULL 'LB $': a lockbox that took no trades prints $0 but never wins the best mark
      (function(){var Z=dfxLbRun(910011,'ZZERO_TR_1_0.py',{trades:0,pnl:0,dd:0,pf:0,win_rate:0,sharpe:null}),N=dfxLbRun(910012,'ZKAPPA_1_0.py',{trades:120,pnl:-250,dd:900,pf:0.9,win_rate:30});
        var W=dfxWin([Z,N]),calls=[],res={};
        function lb(){var ids=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');}),o={};
          dfxRow('LB $').forEach(function(td,i){o[ids[i]]=dfxCell(td);});return o;}
        function ok(o){var z=o[Z.id]||{},n=o[N.id]||{};return z.v==='$0'&&!z.best&&(z.tip||'').indexOf('took no trades in the lockbox')>=0&&n.best===true;}
        calls.push(doRender({cmpMode:'board',rbSample:'full',rbRank:'net',rbHeat:true,cmpIds:[Z.id,N.id]},W,'cmp'));res.old=lb();
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'full',rbHeat:true},W));res.hosted=lb();
        dfxCase('dfx_d04',calls,{'old tab FULL: $0 prints, says why, and the real lockbox takes the best mark':ok(res.old),
          'hosted RUNBOARD FULL: the same':ok(res.hosted)},res);})();

      // D05 - the CHAMPIONS chip hover names the rule the filter uses
      (function(){var c=doRender({},dfxWin([FIX]),'runs'),t=[].map.call(d.querySelectorAll('[data-rfchamp]'),function(e){return e.getAttribute('title')||'';})[0]||'';
        dfxCase('dfx_d05',[c],{'the chip is there':!!t,'it names the book rule, pre-lockbox net over drawdown':t.indexOf('pre-lockbox net over drawdown')>=0,
          'it says a KNOB TEST loses unless starred':t.indexOf('KNOB TEST')>=0,'it no longer says highest SCORE':t.indexOf('highest SCORE')<0},{tip:t});})();

      // D06 (rewritten 2026-09-20, item 1): the RUNBOARD inside COMPARE with no STAGE saved
      //    now reads WALK-FORWARD, not LOCKBOX and not the old tab's own SAMPLE pref -
      //    proved directly: the no-stage render must match an explicit WF render and must
      //    differ from an explicit LB render.
      (function(){var Z=dfxLbRun(910011,'ZZERO_TR_1_0.py',{trades:0,pnl:0,dd:0,pf:0,win_rate:0,sharpe:null}),N=dfxLbRun(910012,'ZKAPPA_1_0.py',{trades:120,pnl:-250,dd:900,pf:0.9,win_rate:30});
        var W=dfxWin([Z,N]),calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'board'},W));
        res.hostRest=dfxRow('IS $').length;res.defaultTotal=dfxRow('TOTAL').map(function(td){return dfxCell(td).v;});
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'wf'},W));
        res.wfTotal=dfxRow('TOTAL').map(function(td){return dfxCell(td).v;});
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'lb'},W));
        res.lbTotal=dfxRow('TOTAL').map(function(td){return dfxCell(td).v;});
        calls.push(doRender({cmpMode:'board',rbSample:'full',cmpIds:[Z.id,N.id]},W,'cmp'));res.oldRest=dfxRow('IS $').length;
        dfxCase('dfx_d06',calls,{'hosted, no STAGE saved: no FULL-only row':res.hostRest===0,
          'hosted with no STAGE saved matches an explicit WALK-FORWARD stage':JSON.stringify(res.defaultTotal)===JSON.stringify(res.wfTotal),
          'hosted with no STAGE saved differs from LOCKBOX, the old default':JSON.stringify(res.defaultTotal)!==JSON.stringify(res.lbTotal),
          'the old tab still follows its own SAMPLE (FULL)':res.oldRest>0},res);})();

      // D07 - Past Runs GROUP view: a book group's champion is its best pre-lockbox net over drawdown, and no 'score NaN'
      (function(){function bk(id,name,pre,dd,whole){var B=dfxClone(FIX);B.id=String(id);B.strategy=name;B.starred=false;B.best_pnl_usd=whole;B.best_dd_usd=dd;B.multiplier=1;
          B.book={name:name,legs:[{strategy:FIX.strategy,weight:1}],whole:{total_pnl:whole,max_drawdown:dd},pre_lockbox:{total_pnl:pre,max_drawdown:dd},
            lockbox:{total_pnl:10000,num_trades:100,win_rate:40,profit_factor:1.3,max_drawdown:5000},lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:10000,pf:1.3,trades:100,pass:true},book:true};delete B.top10_results;return B;}
        var WEAK=bk(740002,'BOOK: PROBE WEAK',600000,60000,610000),STRONG=bk(740001,'BOOK: PROBE STRONG',300000,10000,310000);
        var W=dfxWin([WEAK,STRONG]),calls=[],res={};
        calls.push(doRender({resGroup:true},W,'runs'));
        res.tiles=[].map.call(d.querySelectorAll('[data-grp]'),function(e){return dfxN(e.textContent);});
        calls.push(doRender({rfChamp:true},W,'runs'));res.champ=[].map.call(d.querySelectorAll('tr.arow[data-run]'),function(x){return x.getAttribute('data-run');});
        var t=res.tiles.join(' || ');
        dfxCase('dfx_d07',calls,{'one group tile':res.tiles.length===1,'its champion is the book with the better pre-lockbox net over drawdown':t.indexOf('$310,000')>=0&&t.indexOf('$610,000')<0,
          'no score NaN on the tile':t.indexOf('NaN')<0,'CHAMPIONS keeps the same book':res.champ.length===1&&res.champ[0]==='740001'},res);})();

      // D10 - EXPLORE point hovers print a trade count as a whole number
      (function(){var CID=String(FIX.id),c=doRender({c2Screen:'explore',resLvl:'cfg',resCfgRun:[CID],resSegs:['lb'],resAxis:'raw',resXAxis:'dd'},dfxWin([FIX],"window._runCfg['"+CID+"']=runHistory[0];"));
        var tt=[].map.call(d.querySelectorAll('[data-repoint] title'),function(x){return x.textContent||'';});
        var with2=tt.filter(function(s){return /Trades [0-9,]+[.][0-9][0-9]/.test(s);}),whole=tt.filter(function(s){return /Trades [0-9]/.test(s);});
        dfxCase('dfx_d10',[c],{'points drew':tt.length>0,'some hover names its trades':whole.length>0,'none prints two decimals':with2.length===0},
          {sample:(with2[0]||whole[0]||'').match(/Trades [0-9.,]+/)});})();

      // D12 - PICK RUNS 'Lockbox PF': a lockbox where every trade won dashes with its reason instead of reading 0.00
      (function(){var NL=dfxLbRun(910001,'ZNOLOSS_1_0.py',{trades:30,pnl:500,pf:null,win_rate:100,dd:0,sharpe:2,pass:true}),
          AL=dfxLbRun(910002,'ZALLLOSS_1_0.py',{trades:30,pnl:-500,pf:0,win_rate:0,dd:500}),NM=dfxLbRun(910003,'ZNORMAL_1_0.py',{trades:30,pnl:300,pf:1.4,win_rate:40,dd:200});
        var c=doRender({c2Screen:'cmp',c2View:'runs',c2Stage:'lb',cmpIds:[NL.id,AL.id,NM.id]},dfxWin([NL,AL,NM])),cells=dfxRow('Lockbox PF').map(dfxCell);
        dfxCase('dfx_d12',[c],{'three cells':cells.length===3,'no-loss lockbox dashes':!!cells[0]&&cells[0].v==='—',
          'and says no lockbox trade lost':!!cells[0]&&cells[0].tip.indexOf('No lockbox trade lost')===0,
          'all-loss lockbox still reads 0.00':!!cells[1]&&cells[1].v==='0.00','normal lockbox reads 1.40':!!cells[2]&&cells[2].v==='1.40'},
          {cells:cells.map(function(x){return x.v+(x.tip?(' {'+x.tip.slice(0,40)+'}'):'');})});})();

      // D13 - the note under the chart names MAR / PROFIT, never 'the vertical measure'
      (function(){var calls=[],n={};
        calls.push(doRender({c2Screen:'explore',resLvl:'sweep',resSegs:['lb'],resAxis:'ratio',resXAxis:'dd'},dfxWin([FIX])));n.mar=dfxNote();
        calls.push(doRender({c2Screen:'explore',resLvl:'sweep',resSegs:['lb'],resAxis:'raw',resXAxis:'dd'},dfxWin([FIX])));n.raw=dfxNote();
        dfxCase('dfx_d13',calls,{'MAR up: the note is there':n.mar.indexOf('not on this chart')>=0,'MAR up: it names MAR':n.mar.indexOf('neither MAR nor')>=0,
          'PROFIT up: it names PROFIT ($)':n.raw.indexOf('neither PROFIT ($) nor')>=0,'never the vertical measure':(n.mar+n.raw).indexOf('the vertical measure')<0},
          {mar:n.mar.slice(0,160),raw:n.raw.slice(0,160)});})();

      // D14 - LOAD ALL is offered only while the loaded runs list is capped
      (function(){var calls=[],res={};
        calls.push(doRender({c2Screen:'explore',resLvl:'all'},dfxWin([FIX])));res.loadFull=d.querySelectorAll('[data-resloadall]').length;res.noteFull=dfxNote();
        calls.push(doRender({c2Screen:'explore',resLvl:'all'},dfxWin([FIX],'runsLimit=1;')));res.loadCap=d.querySelectorAll('[data-resloadall]').length;res.noteCap=dfxNote();
        w.eval('runsLimit=75');
        dfxCase('dfx_d14',calls,{'every run loaded: no LOAD ALL':res.loadFull===0,'every run loaded: the rows cite a run not on this account':res.noteFull.indexOf('not on this account')>=0,
          'a capped list still offers LOAD ALL for runs older than what is loaded':res.loadCap>0&&res.noteCap.indexOf('older than what is loaded')>=0},
          {loadFull:res.loadFull,loadCap:res.loadCap,noteFull:res.noteFull.slice(0,200)});})();

      // D22 (deferred round 2, item 2) - a load in flight must not flip 'older than what is loaded' into
      //   'not on this account'. _subscribeRuns bumps the reactive runsLimit to the new number BEFORE the
      //   bigger list it asked for comes back (LOAD ALL, or a small starred-runs read re-rendering first),
      //   so comparing the loaded list's length against runsLimit reads as uncapped for those few seconds.
      //   Here: a list of 1 run loaded with limit 1 (window._runsLoadedLimit=1), then runsLimit bumped to
      //   5000 with no new list ever arriving - the note must still say 'older than what is loaded' and
      //   still offer LOAD ALL, never 'not on this account'.
      (function(){var calls=[],res={};
        calls.push(doRender({c2Screen:'explore',resLvl:'all'},dfxWin([FIX],"window._runsLoadedLimit=1;runsLimit=5000;")));
        res.loadInFlight=d.querySelectorAll('[data-resloadall]').length;res.noteInFlight=dfxNote();
        w.eval('window._runsLoadedLimit=undefined;runsLimit=75;');
        dfxCase('dfx_d22',calls,{'a load in flight for a bigger limit still reads as capped, offering LOAD ALL':res.loadInFlight>0&&res.noteInFlight.indexOf('older than what is loaded')>=0,
          'and never claims the run is not on this account while that bigger fetch is still out':res.noteInFlight.indexOf('not on this account')<0},
          {loadInFlight:res.loadInFlight,noteInFlight:res.noteInFlight.slice(0,220)});})();

      // D15 - hovering a table row lights its three pinned cells too, and leaving puts them back
      (function(){var c=doRender({c2Screen:'explore',resLvl:'sweep',c2Tbl:true,resCols:'all'},dfxWin([FIX])),res={};
        var tr=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return t.children.length>3&&w.getComputedStyle(t.children[0]).backgroundImage==='none';})[0];
        function imgs(){return [0,1,2].map(function(i){return w.getComputedStyle(tr.children[i]).backgroundImage;});}
        if(tr){res.before=imgs();tr.dispatchEvent(new w.MouseEvent('mouseenter'));res.on=imgs();tr.dispatchEvent(new w.MouseEvent('mouseleave'));res.after=imgs();
          res.pos=w.getComputedStyle(tr.children[0]).position;res.col=w.getComputedStyle(tr.children[0]).backgroundColor;}
        dfxCase('dfx_d15',[c],{'a plain row was found':!!tr,'its first three cells are pinned':res.pos==='sticky',
          'hovered: all three carry the highlight layer':!!res.on&&res.on.every(function(s){return s.indexOf('gradient')>=0;}),
          'and stay opaque':/^rgb[(]/.test(res.col||''),'left: all three are back as they were':!!res.after&&JSON.stringify(res.after)===JSON.stringify(res.before)},res);})();

      // D16 - STACK layout at 1366x768: the table's sideways scrollbar sits inside the capped column
      (function(){var fr=document.getElementById('f');fr.style.width='1366px';fr.style.height='768px';void fr.offsetHeight;
        var c=doRender({c2Screen:'explore',resLvl:'sweep',c2Tbl:true,resCols:'all',resView:'one'},dfxWin([FIX])),res={};
        var col=d.querySelector('[data-restackl]'),bx=col?[].filter.call(col.querySelectorAll('[data-rescroll]'),function(b){return b.offsetParent!==null;})[0]:null;
        if(col&&bx){var cr=col.getBoundingClientRect(),br=bx.getBoundingClientRect();res.clip=Math.round(cr.top+col.clientTop+col.clientHeight);res.boxBottom=Math.round(br.bottom);
          res.boxMax=bx.style.maxHeight;res.colMax=col.style.maxHeight;res.sideways=bx.scrollWidth>bx.clientWidth;res.boxH=Math.round(br.height);}
        fr.style.width='1400px';fr.style.height='900px';void fr.offsetHeight;
        dfxCase('dfx_d16',[c],{'STACK column and a table box are there':!!(col&&bx),'the table scrolls sideways (so its scrollbar matters)':res.sideways===true,
          'the box bottom edge is inside the column':res.boxBottom!=null&&res.boxBottom<=res.clip+1,'the box keeps a usable height':(res.boxH||0)>=120},res);})();

      // D17 - 1E CONFIGS: one 'not on this chart' count, not a second one beside it
      (function(){var CID=String(FIX.id),c=doRender({c2Screen:'explore',resLvl:'all',resShow:'configs',resCfgRun:[CID],resSegs:['is','lb'],resAxis:'ratio',resXAxis:'dd'},dfxWin([FIX],"window._runCfg['"+CID+"']=runHistory[0];"));
        var t=dfxN(d.body.innerText);
        dfxCase('dfx_d17',[c],{'the breakdown note is there':/[0-9]+ of [0-9]+ not on this chart/.test(t),'no second per-run count beside it':!/#[0-9]+×[0-9]+/.test(t)},
          {note:(t.match(/[0-9]+ of [0-9]+ not on this chart[^.]{0,60}/)||[''])[0],second:(t.match(/[0-9]+ not on this chart: #[0-9]+×[0-9]+/)||[''])[0]});})();

      // D20 - the ticked stage's sticky heading is opaque, with its tint laid over the ground
      (function(){var c=doRender({c2Screen:'explore',resLvl:'sweep',c2Tbl:true,resCols:'all',resSegs:['lb']},dfxWin([FIX])),res={};
        [].forEach.call(d.querySelectorAll('th[data-recol]'),function(th){var k=th.getAttribute('data-recol');if((k==='LOCKBOX'||k==='IN-SAMPLE')&&!res[k]){var s=w.getComputedStyle(th);res[k]={pos:s.position,col:s.backgroundColor,img:s.backgroundImage.slice(0,40)};}});
        var L=res.LOCKBOX||{},I=res['IN-SAMPLE']||{};
        dfxCase('dfx_d20',[c],{'LOCKBOX heading is sticky':L.pos==='sticky','LOCKBOX heading ground is opaque':/^rgb[(]/.test(L.col||''),
          'LOCKBOX heading still carries its tint':(L.img||'').indexOf('gradient')>=0,'an unticked heading is unchanged (opaque, no tint)':/^rgb[(]/.test(I.col||'')&&I.img==='none'},res);})();

      // D21 - RUNBOARD heat map: an approximate (~) figure takes no shade and does not move the scale
      (function(){var A=dfxClone(FIX);A.id='760001';A.strategy='ZAPX_1_0.py';delete A.validate.total_trades;
        var Bn=dfxClone(FIX);Bn.id='760002';Bn.strategy='ZEXACT_1_0.py';var Cn=dfxClone(FIX);Cn.id='760003';Cn.strategy='ZEXACT2_1_0.py';Cn.validate.total_trades=+Cn.validate.total_trades*2;
        var c=doRender({cmpMode:'board',rbSample:'full',rbRank:'net',rbHeat:true,cmpIds:[A.id,Bn.id,Cn.id]},dfxWin([A,Bn,Cn]),'cmp');
        var ids=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');}),ev={};
        dfxRow('EV').forEach(function(td,i){ev[ids[i]]=dfxCell(td);});
        var a=ev['760001']||{},b=ev['760002']||{},cc=ev['760003']||{};
        dfxCase('dfx_d21',[c],{'the EV row has all three runs':!!(a.v&&b.v&&cc.v),'the run with no whole-run count reads ~':(a.v||'').indexOf('~')===0,
          'its ~ figure is not heat-shaded':!/rgba|hsla/.test(a.bg||''),'the two exact figures are shaded':/rgba|hsla/.test(b.bg||'')&&/rgba|hsla/.test(cc.bg||'')},
          {ev:[a,b,cc].map(function(x){return (x.v||'')+' bg='+(x.bg||'').slice(0,40);})});})();

      // == g1-pool: Starred/older/archived pool + family grouping (F1, F6, F7, F11, F12) ==

      // -- g1_f1 (F1): Past Runs must never silently fall back to the first row for an
      //    EXPLICIT selection - a starred crown click, or any run id set from elsewhere -
      //    that sits outside runHistory. It must find a starred-outside-the-window run
      //    directly, and for one truly unresolved it must say LOADING, not substitute #1.
      (function(){
        var F=dfxClone(FIX);F.id=String(+FIX.id+810001);F.starred=false;
        var S=dfxClone(FIX);S.id=String(+FIX.id+810002);S.strategy='ZSTARCROWN_1_0.py';S.starred=true;
        var W1=dfxWin([F],"window._starRuns=[__f("+JSON.stringify(S)+")];augurRunSel="+JSON.stringify(S.id)+";");
        var c1=doRender({},W1,'runs');
        var sRow=d.querySelector('tr[data-run="'+S.id+'"]');
        var sRowOn=d.querySelector('tr[data-run="'+S.id+'"][style*="background:var(--bg1)"]');
        var W2=dfxWin([F],"window._starRuns=[__f("+JSON.stringify(S)+")];augurRunSel='ZNONE_G1_F1';");
        var c2=doRender({},W2,'runs');
        var bodyTxt2=dfxN(d.body.innerText||'');
        var fRowOn2=d.querySelector('tr[data-run="'+F.id+'"][style*="background:var(--bg1)"]');
        dfxCase('g1_f1',[c1,c2],{
          'renders OK':c1==='OK'&&c2==='OK',
          'a starred run outside the loaded window is in the explicit-selection pool':!!sRow,
          'and it is the one actually selected, not the first row':!!sRowOn,
          'a genuinely unresolved explicit pick shows LOADING, never the first row':bodyTxt2.indexOf('LOADING RUN #ZNONE_G1_F1')>=0,
          'and does not silently select the first row instead':!fRowOn2
        },{sRowFound:!!sRow,sRowOn:!!sRowOn,loading:bodyTxt2.indexOf('LOADING RUN #ZNONE_G1_F1')>=0,fRowOn2:!!fRowOn2});
      })();

      // -- g1_f6 (F6): RUNBOARD's family chips and drill-down must read the same pool as
      //    LEADERBOARD/OVERLAY - runHistory plus any starred run outside the loaded window -
      //    so a family whose only run is a starred older crown still gets a chip and a drill,
      //    instead of a false empty board with no way back.
      (function(){
        var F=dfxClone(FIX);F.id=String(+FIX.id+820001);F.starred=false;
        var S=dfxClone(FIX);S.id=String(+FIX.id+820002);S.strategy='ORB_1_0.py';S.starred=true;
        var W=dfxWin([F],"window._starRuns=[__f("+JSON.stringify(S)+")];");
        var c=doRender({cmpMode:'board',rbFam:'ORB',rbSample:'lb',rbRank:'net'},W,'cmp');
        var bodyTxt=dfxN(d.body.innerText||'');
        var sRow=bodyTxt.indexOf('#'+S.id)>=0;
        var chip=d.querySelector('[data-rbfam="ORB"]');
        dfxCase('g1_f6',[c],{
          'renders OK':c==='OK',
          'the ORB family chip appears even though its only run is a starred crown outside the window':!!chip,
          'drilling into it shows the starred run, not a false empty state':sRow,
          'the empty-board placeholder is not shown':bodyTxt.indexOf('NO SAVED RUNS YET')<0
        },{chip:!!chip,sRow:sRow});
      })();

      // -- g1_f7 (F7): EXPLORE's LEVEL CROWN keeps one row per family (a star always wins);
      //    a book row uses the book's own name, and its hover never reads 'on .' when the
      //    book has no single market.
      (function(){
        function mkBook(idOff,name){
          var B=dfxClone(FIX);B.id=String(+FIX.id+idOff);B.strategy=name;B.starred=true;
          B.instrument='';B.timeframe='';
          B.book={name:name,legs:[{strategy:'ORB_1_0.py',weight:1},{strategy:'ENGUQ_1_0.py',weight:1}],
            whole:{total_pnl:300000,max_drawdown:30000,num_trades:2000,profit_factor:1.3},
            pre_lockbox:{total_pnl:250000,max_drawdown:28000},
            lockbox:{total_pnl:50000,num_trades:300,win_rate:40,profit_factor:1.3,max_drawdown:20000},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          return B;
        }
        var B1=mkBook(830001,'BOOK: PROBE ONE'),B2=mkBook(830002,'BOOK: PROBE TWO');
        var W=dfxWin([B1,B2]);
        var c=doRender({c2Screen:'explore',resLvl:'crown',resCols:'all',c2Tbl:true},W);
        var rows=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(x){
          return (x.textContent||'').indexOf('#'+B1.id)>=0||(x.textContent||'').indexOf('#'+B2.id)>=0;});
        var hasB1=rows.some(function(x){return (x.textContent||'').indexOf('#'+B1.id)>=0;});
        var hasB2=rows.some(function(x){return (x.textContent||'').indexOf('#'+B2.id)>=0;});
        var row2=rows.filter(function(x){return (x.textContent||'').indexOf('#'+B2.id)>=0;})[0];
        var nameEl=row2?[].filter.call(row2.querySelectorAll('b'),function(b){return (b.textContent||'').indexOf('BOOK')>=0;})[0]:null;
        var nameTxt=nameEl?dfxN(nameEl.textContent):'';
        var whatCell=row2?[].filter.call(row2.querySelectorAll('td'),function(td){var t=td.textContent||'';return t.indexOf('Auto-Validate run #')>=0||t.indexOf('Book run #')>=0;})[0]:null;
        var whatTxt=whatCell?dfxN(whatCell.textContent):'';
        dfxCase('g1_f7',[c],{
          'renders OK':c==='OK',
          'exactly one row for the two starred books in the same family (the higher id wins the tie)':rows.length===1&&hasB2&&!hasB1,
          "the surviving row uses the book's own name, not a family-abbreviated tag":nameTxt.indexOf('BOOK: PROBE TWO')>=0,
          'its hover names the market or says it pools several, never reading blank ("on .")':whatTxt&&whatTxt.indexOf(' on .')<0,
          // repair round (F16/item 16): a book is a book run, never an Auto-Validate one - its
          //   own hovers say it tunes nothing and runs no walk-forward.
          "a book row's WHAT IT DOES never claims it is an Auto-Validate run":whatTxt&&whatTxt.indexOf('Auto-Validate')<0,
          "a book row's WHAT IT DOES calls it a book run and says it pools several strategies and markets":whatTxt&&whatTxt.indexOf('Book run #')>=0&&whatTxt.indexOf('pooled')>=0
        },{rowsN:rows.length,nameTxt:nameTxt,whatSnippet:whatTxt.slice(0,200)});
      })();

      // -- g1_f11 (F11): archived runs are left out of the LEADERBOARD champion pick and the
      //    RUNBOARD pool, matching what Past Runs itself hides by default.
      (function(){
        var A=dfxClone(FIX);A.id=String(+FIX.id+840001);A.strategy='ZARCHFAM_1_0.py';A.starred=false;A.archived=true;A.best_pnl_usd=999999;A.best_dd_usd=1;
        var B=dfxClone(FIX);B.id=String(+FIX.id+840002);B.strategy='ZARCHFAM_1_0.py';B.starred=false;B.archived=false;B.best_pnl_usd=1000;B.best_dd_usd=500;
        var W=dfxWin([A,B]);
        var c=doRender({c2Screen:'lead',c2Stage:'is',c2Rank:'net'},W);
        var row=d.querySelector('.c2-row[data-c2fam="ZARCHFAM_1_0"]');
        var big=row?row.querySelector('.c2-big'):null;
        var bigTxt=big?dfxN(big.textContent):'';
        var c2=doRender({cmpMode:'board',rbSample:'is',rbRank:'net'},W,'cmp');
        var colIds=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        dfxCase('g1_f11',[c,c2],{
          'renders OK':c==='OK'&&c2==='OK',
          "LEADERBOARD champion is the live run, not the archived one's bigger number":bigTxt.indexOf('999,999')<0,
          'RUNBOARD pool never shows the archived run as a column':colIds.indexOf(A.id)<0,
          'RUNBOARD pool still shows the live run':colIds.indexOf(B.id)>=0
        },{bigTxt:bigTxt,colIds:colIds});
      })();

      // -- g1_f12 (F12): family grouping falls back to the family-keyword table, which now
      //    matches ETFDIP, so several ETFDIP files pool into one family instead of one row
      //    per file name.
      (function(){
        var A=dfxClone(FIX);A.id=String(+FIX.id+850001);A.strategy='ETFDIP_1_0.py';A.starred=false;
        var B=dfxClone(FIX);B.id=String(+FIX.id+850002);B.strategy='ETFDIP_2_3.py';B.starred=false;
        var W=dfxWin([A,B]);
        var c=doRender({c2Screen:'lead',c2Stage:'is',c2Rank:'net'},W);
        var rows=[].slice.call(d.querySelectorAll('.c2-row[data-c2fam]'));
        var famKeys=rows.map(function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'');});
        dfxCase('g1_f12',[c],{
          'renders OK':c==='OK',
          'two ETFDIP files pool into ONE family row (DIP since the v73.893 vocabulary), not two':famKeys.filter(function(k){return k==='DIP';}).length===1,
          'no leftover per-file ETFDIP_1_0 / ETFDIP_2_3 rows remain':famKeys.indexOf('ETFDIP_1_0')<0&&famKeys.indexOf('ETFDIP_2_3')<0
        },{famKeys:famKeys});
      })();

      // -- g2_f2 (F2): EXPLORE run rows, RUNBOARD FULL and PICK RUNS FULL all read the
      //    champion's own measured in-sample slice (gate_validate.ungated_is), never the
      //    whole-run-minus-walk-forward-minus-lockbox remainder, which mixed the fixed
      //    champion with the re-fitted folds - and dash with the true reason, never that
      //    remainder, when the run never saved the slice.
      (function(){
        var A=dfxClone(FIX);A.id=String(+FIX.id+870001);A.strategy='ZGVIS_1_0.py';A.starred=false;
        var N=dfxClone(FIX);N.id=String(+FIX.id+870002);N.strategy='ZNOGVIS_1_0.py';N.starred=false;
        delete N.gate_validate.ungated_is;
        var gv=A.gate_validate.ungated_is;
        var wantPf=(+gv.profit_factor).toFixed(2),wantTr=(+gv.num_trades).toLocaleString();
        var W=dfxWin([A,N]);
        var c1=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['is'],resAxis:'pf',resXAxis:'wr',c2Tbl:true},W);
        var hdr=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()]/g,'').trim();});
        function g2RowOf(id){return [].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('#'+id)>=0;})[0];}
        function g2CellOf(id,nm){var tr=g2RowOf(id),q=hdr.indexOf(nm);return (tr&&q>=0)?dfxN(tr.cells[q].textContent):null;}
        var expPf=g2CellOf(A.id,'PF'),expTr=g2CellOf(A.id,'TRADES');
        var c2=doRender({cmpMode:'board',rbSample:'full',cmpIds:[A.id,N.id]},W,'cmp');
        var colIds=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        function g2RbCell(id,lbl){var i=colIds.indexOf(String(id)),cells=dfxRow(lbl);return (i>=0&&cells[i])?dfxCell(cells[i]):null;}
        var rbA=g2RbCell(A.id,'IS $'),rbN=g2RbCell(N.id,'IS $');
        var c3=doRender({cmpScope:'tot',cmpIds:[A.id,N.id]},W,'cmp');
        var prCells=dfxRow(String.fromCharCode(0x251c)+' in-sample $');
        var prA=prCells[0]?dfxCell(prCells[0]):null,prN=prCells[1]?dfxCell(prCells[1]):null;
        dfxCase('g2_f2',[c1,c2,c3],{
          'renders OK':c1==='OK'&&c2==='OK'&&c3==='OK',
          'EXPLORE run row IN-SAMPLE PF is the measured slice, not a remainder':expPf===wantPf,
          'EXPLORE run row IN-SAMPLE TRADES is the measured slice count':expTr===wantTr,
          'RUNBOARD FULL "IS $" reads the measured slice ($11k)':!!rbA&&rbA.v==='$11k',
          'RUNBOARD FULL "IS $" label drops the misleading REST suffix':dfxRow('IS $ '+String.fromCharCode(0xb7)+' REST').length===0,
          'RUNBOARD FULL "IS $" dashes with the true reason when the slice was never saved':!!rbN&&rbN.v===String.fromCharCode(0x2014)&&rbN.tip.indexOf('in-sample')>=0,
          'PICK RUNS FULL in-sample $ reads the same measured slice':!!prA&&prA.v.indexOf('11k')>=0,
          'PICK RUNS FULL in-sample $ dashes (never a remainder) when the slice was never saved':!!prN&&prN.v===String.fromCharCode(0x2014)
        },{expPf:expPf,expTr:expTr,rbA:rbA,rbN:rbN,prA:prA,prN:prN});
      })();

      // -- g2_f10 (F10): a Gate-Validate JOB TYPE run saves no validate block, so its curve
      //    (net) is the UNGATED whole-run backtest while best_pf/best_trades/best_dd_usd are
      //    the GATED headline pick - a different population. FULL PF/TRADES/DRAWDOWN must
      //    come from gate_validate.ungated_full (the same population as the curve), on both
      //    the LEADERBOARD and the OVERLAY table, never the gated headline beside the ungated
      //    net; IS must dash rather than annualise the gated headline over the whole run.
      (function(){
        var G={id:String(+FIX.id+890001),strategy:'ZGVFULL_1_0.py',starred:false,instrument:'NQ',timeframe:'5m',
          timestamp:'2026-09-01 00:00',multiplier:20,date_from:'2010-01-01',date_to:'2026-01-01',
          scope:String.fromCharCode(0x1f6aa)+String.fromCharCode(0x1f9ed)+' Gate-Validate',
          best_pf:2.50,best_trades:34,best_pnl_usd:16000,best_dd_usd:2000,best_win_rate:50,
          equity:{cum:[0,2000,5000]},
          gate_validate:{ungated_full:{num_trades:600,total_pnl:5000,profit_factor:1.30,win_rate:32,max_drawdown:-400}}};
        var W=dfxWin([G]);
        var c1=doRender({c2Screen:'lead',c2Stage:'full',c2Rank:'pf'},W);
        var row=d.querySelector('.c2-row[data-c2fam]');
        var fullPfTxt=row?dfxN((row.querySelector('.c2-big')||{}).textContent):null;
        var c2=doRender({c2Screen:'lead',c2Stage:'is',c2Rank:'pf'},W);
        var row2=d.querySelector('.c2-row[data-c2fam]');
        var isPfBig=row2?row2.querySelector('.c2-big'):null;
        var isPfTxt=isPfBig?dfxN(isPfBig.textContent):null;
        var isPfTitle=isPfBig?(isPfBig.getAttribute('title')||''):'';
        var c3=doRender({c2Screen:'cmp',c2View:'ovl',c2Stage:'full',cmpIds:[G.id]},W);
        var ovlPfCells=dfxRow('PF');
        var ovlPfTxt=ovlPfCells[0]?dfxN(ovlPfCells[0].textContent):null;
        dfxCase('g2_f10',[c1,c2,c3],{
          'renders OK':c1==='OK'&&c2==='OK'&&c3==='OK',
          'LEADERBOARD FULL PF is the ungated_full reading, not the gated headline best_pf':fullPfTxt==='1.30',
          'LEADERBOARD IS dashes rather than annualise the gated headline over the whole run':isPfTxt===String.fromCharCode(0x2014),
          'LEADERBOARD IS dash names a real reason':isPfTitle.length>0,
          'the OVERLAY table FULL PF matches the LEADERBOARD, not best_pf':ovlPfTxt==='1.30'
        },{fullPfTxt:fullPfTxt,isPfTxt:isPfTxt,isPfTitle:isPfTitle,ovlPfTxt:ovlPfTxt});
      })();

      // -- g2_f3 (F3): a book's run report 1E KPI MATRIX builds IS / LB / TOTAL from the
      //    book's own pre_lockbox / lockbox / whole blocks - net, PF, trades, drawdown all
      //    measured, never a residual off a curve this run type never saves the windows for
      //    - and no WF column, since a book tunes nothing and never runs one.
      (function(){
        function bkBlk(net,tr,wins,losses,wr,pf,dd){var gl=net/(pf-1),gw=pf*gl;
          return {total_pnl:net,num_trades:tr,wins:wins,losses:losses,win_rate:wr,profit_factor:pf,max_drawdown:dd,
            gross_win:gw,gross_loss:gl};}
        var pre=bkBlk(1395904,9085,3000,6085,33.02,1.49,34000);
        var lb=bkBlk(289811,622,200,422,32.15,1.56,28066);
        var whole=bkBlk(1685715,9707,3200,6507,32.97,1.50,36562);
        var B=dfxClone(FIX);B.id=String(+FIX.id+900001);B.strategy='BOOK: PROBE F3';B.starred=false;B.multiplier=1;
        B.best_pnl_usd=pre.total_pnl;B.best_pf=pre.profit_factor;B.best_trades=pre.num_trades;B.best_dd_usd=pre.max_drawdown;B.best_win_rate=pre.win_rate;
        B.book={name:'BOOK: PROBE F3',legs:[{strategy:FIX.strategy,weight:1}],whole:whole,pre_lockbox:pre,lockbox:lb,
          lockbox_from:'2025-06-30',date_from:'2010-06-07',date_to:'2026-08-13'};
        B.validate={verdict:'PASS',lockbox:{pnl:lb.total_pnl,pf:lb.profit_factor,trades:lb.num_trades,pass:true},book:true};
        delete B.top10_results;delete B.gate_validate;delete B.ml_gate;
        var W=dfxWin([B],"augurRunSel='"+B.id+"';");
        var c=doRender({},W,'runs');
        var ths=[].slice.call(d.querySelectorAll('#res-detail th[title]'));
        var bookIsTh=ths.filter(function(th){return (th.getAttribute('title')||'').indexOf('A book pools every leg over one window')>=0;})[0];
        var bookLbTh=ths.filter(function(th){return (th.getAttribute('title')||'').indexOf('the book')>=0&&(th.getAttribute('title')||'').indexOf('lockbox backtest')>=0;})[0];
        var bookTotTh=ths.filter(function(th){return (th.getAttribute('title')||'').indexOf('no walk-forward stage')>=0;})[0];
        var wfTh=ths.filter(function(th){return dfxN(th.textContent)==='WF';})[0];
        function colIndex(th){if(!th)return -1;var tr=th.closest('tr');return [].indexOf.call(tr.children,th);}
        var iIS=colIndex(bookIsTh),iLB=colIndex(bookLbTh),iTOT=colIndex(bookTotTh);
        function metricRow(lbl){var rows=[].slice.call(d.querySelectorAll('#res-detail tbody tr'));
          for(var i=0;i<rows.length;i++){var td=rows[i].children[0];if(td&&dfxN(td.textContent)===lbl)return rows[i];}
          return null;}
        function cellTitle(row,ci){if(!row||ci<0)return null;var td=row.children[ci];if(!td)return null;
          var sp=td.querySelector('[title]');return sp?sp.getAttribute('title'):null;}
        var netRow=metricRow('NET P&L'),ddRow=metricRow('DD'),pfRow=metricRow('PF'),trRow=metricRow('TRADES');
        var netIS=cellTitle(netRow,iIS),netLB=cellTitle(netRow,iLB),netTOT=cellTitle(netRow,iTOT);
        var pfTxt=function(row,ci){return (row&&row.children[ci])?dfxN(row.children[ci].textContent):null;};
        var pfIS=pfTxt(pfRow,iIS),pfTOT=pfTxt(pfRow,iTOT),trIS=pfTxt(trRow,iIS),trTOT=pfTxt(trRow,iTOT);
        dfxCase('g2_f3',[c],{
          'renders OK, #res-detail exists':c==='OK'&&!!d.getElementById('res-detail'),
          'the matrix has exactly three columns: IS, LB, TOTAL (no WF)':iIS>=0&&iLB>=0&&iTOT>=0&&!wfTh,
          'IS NET is the book\u2019s own pre_lockbox net, not a near-zero residual':netIS==='$1,395,904',
          'LB NET is the book\u2019s own lockbox net':netLB==='$289,811',
          'TOTAL NET is the book\u2019s own whole net, not the lockbox PF mislabelled':netTOT==='$1,685,715',
          'IS PF is measured (1.49), not dashed':pfIS==='1.49',
          'TOTAL PF is the whole-book PF (1.50), not the lockbox PF standing in for it':pfTOT==='1.50',
          'IS TRADES is the pre-lockbox count (9,085), not a lockbox-only count':trIS==='9,085',
          'TOTAL TRADES is the whole-book count (9,707)':trTOT==='9,707'
        },{iIS:iIS,iLB:iLB,iTOT:iTOT,hasWf:!!wfTh,netIS:netIS,netLB:netLB,netTOT:netTOT,pfIS:pfIS,pfTOT:pfTOT,trIS:trIS,trTOT:trTOT});
      })();

      // -- g2_f13 (F13): EXPLORE must not rebuild a book's Sharpe/Sortino from the thinned
      //    saved curve - the engine never measures either for a book (book.whole /
      //    book.lockbox carry neither), and the curve is thinned for storage, so an estimate
      //    off it reads nothing like a true measurement and, unmarked, took the top ranks.
      //    OVERLAY and RUNBOARD already dash a book's Sharpe/Sortino outright; EXPLORE must
      //    dash with the same reason, not estimate off the curve.
      (function(){
        function bkBlk(net,tr,wins,losses,wr,pf,dd){var gl=net/(pf-1),gw=pf*gl;
          return {total_pnl:net,num_trades:tr,wins:wins,losses:losses,win_rate:wr,profit_factor:pf,max_drawdown:dd,
            gross_win:gw,gross_loss:gl};}
        var pre=bkBlk(500000,3000,1000,2000,33.33,1.45,40000);
        var lb=bkBlk(120000,700,230,470,32.86,1.40,20000);
        var whole=bkBlk(620000,3700,1230,2470,33.24,1.44,45000);
        var eq=[0,20000,15000,35000,50000,30000,60000,80000,70000,100000,120000,110000,140000,160000,150000,180000,200000,190000,220000,240000];
        var B=dfxClone(FIX);B.id=String(+FIX.id+910001);B.strategy='BOOK: PROBE F13';B.starred=false;B.multiplier=1;
        B.best_pnl_usd=pre.total_pnl;B.best_pf=pre.profit_factor;B.best_trades=pre.num_trades;B.best_dd_usd=pre.max_drawdown;B.best_win_rate=pre.win_rate;
        B.book={name:'BOOK: PROBE F13',legs:[{strategy:FIX.strategy,weight:1}],whole:whole,pre_lockbox:pre,lockbox:lb,
          lockbox_from:'2022-01-01',date_from:'2010-01-01',date_to:'2025-01-01'};
        B.validate={verdict:'PASS',equity:eq,lb_idx:15,lockbox:{pnl:lb.total_pnl,pf:lb.profit_factor,trades:lb.num_trades,pass:true},book:true};
        delete B.top10_results;delete B.gate_validate;delete B.ml_gate;
        var W=dfxWin([B]);
        function hdrOf(){return [].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()]/g,'').trim();});}
        function rowOf(id){return [].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('#'+id)>=0;})[0];}
        function cellTitleAt(tr,q){var td=tr&&tr.cells[q];if(!td)return null;var sp=td.querySelector('[title]');return sp?sp.getAttribute('title'):null;}
        function read(segs){
          var c=doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:segs,resAxis:'pf',resXAxis:'wr',c2Tbl:true},W);
          var h=hdrOf(),tr=rowOf(B.id);
          var qSh=h.indexOf('SHARPE'),qSo=h.indexOf('SORTINO');
          return {call:c,sh:(tr&&qSh>=0)?dfxN(tr.cells[qSh].textContent):null,so:(tr&&qSo>=0)?dfxN(tr.cells[qSo].textContent):null,
            shTip:cellTitleAt(tr,qSh),soTip:cellTitleAt(tr,qSo)};}
        var isR=read(['is']),lbR=read(['lb']),allR=read(['is','wf','lb']);
        var wantReason='This run is a book. A book pools every leg\u2019s trades into one line and never saves a Sharpe or a Sortino for it.';
        dfxCase('g2_f13',[isR.call,lbR.call,allR.call],{
          'renders OK':isR.call==='OK'&&lbR.call==='OK'&&allR.call==='OK',
          'IN-SAMPLE SHARPE dashes rather than estimate off the thinned curve':isR.sh===String.fromCharCode(0x2014),
          'IN-SAMPLE SORTINO dashes too':isR.so===String.fromCharCode(0x2014),
          'IN-SAMPLE dash names the real reason (a book saves neither)':(isR.shTip||'').indexOf(wantReason)>=0,
          'LOCKBOX SHARPE dashes rather than estimate off the thinned curve':lbR.sh===String.fromCharCode(0x2014),
          'LOCKBOX SORTINO dashes too':lbR.so===String.fromCharCode(0x2014),
          'ALL THREE (whole run) SHARPE dashes rather than estimate off the thinned curve':allR.sh===String.fromCharCode(0x2014),
          'ALL THREE (whole run) SORTINO dashes too':allR.so===String.fromCharCode(0x2014)
        },{isR:isR,lbR:lbR,allR:allR});
      })();

      // -- g2_f18 (F18): a champion whose own window covers under two years must sink below
      //    every full-length champion on the LEADERBOARD family list and in COMPARE CHAMPIONS'
      //    own TOP 10 pick - it still shows (RUNBOARD's own rule: a short sample is a caveat,
      //    not a disqualifier here) but it must never rank above a full-length run just because
      //    a near-zero drawdown inflated its ratio, and it must carry a mark saying why.
      (function(){
        var A=dfxClone(FIX);A.id=String(+FIX.id+920001);A.strategy='ZLONGYR_1_0.py';A.starred=false;
        var B=dfxClone(FIX);B.id=String(+FIX.id+920002);B.strategy='ZSHORTYR_1_0.py';B.starred=false;
        B.date_from='2026-05-10';B.date_to='2026-05-28';   // 18 days, the real #42 evidence from the audit
        delete B.validate.equity;delete B.equity;
        B.best_pnl_usd=5000000;B.validate.total_dd=-200;B.validate.total_trades=500;B.validate.total_win_rate=90;
        var W=dfxWin([A,B]);
        var c1=doRender({c2Screen:'lead',c2Stage:'full',c2Rank:'mar'},W);
        function famOrder(){return [].map.call(d.querySelectorAll('.c2-row[data-c2fam]'),function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'');});}
        var order=famOrder();
        var iA=order.indexOf('ZLONGYR_1_0'),iB=order.indexOf('ZSHORTYR_1_0');
        function pillTitleFor(fk){var row=[].filter.call(d.querySelectorAll('.c2-row[data-c2fam]'),function(x){return decodeURIComponent(x.getAttribute('data-c2fam')||'')===fk;})[0];
          if(!row)return null;var pills=[].slice.call(row.querySelectorAll('.c2-pill'));
          var p=pills.filter(function(x){return (x.textContent||'').indexOf('short window')>=0;})[0];
          return p?p.getAttribute('title'):null;}
        var bPill=pillTitleFor('ZSHORTYR_1_0'),aPill=pillTitleFor('ZLONGYR_1_0');
        var c2=doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'champ',c2Stage:'full',c2Rank:'mar'},W);
        var champOrder=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        var jA=champOrder.indexOf(A.id),jB=champOrder.indexOf(B.id);
        // F18 fix (repair round): column ORDER already sank the short-window champion, but the
        //   per-row BEST mark (bold + "best of the picked runs on this row") is a SEPARATE
        //   mechanism and used to still land on it regardless of order - checked here on MAR,
        //   the row named in the audit evidence.
        function marBestCol(){var cells=dfxRow('MAR');for(var i2=0;i2<cells.length;i2++){
          var b=cells[i2].querySelector('[title="best of the picked runs on this row"]');if(b)return i2;}return -1;}
        var marBestIdx=marBestCol();
        // TOP RUNS (BEST), ranked on MAR - the LEADERBOARD's own top-runs strip.
        var c3=doRender({c2Screen:'lead',c2Stage:'full',c2Rank:'mar',c2Top:'best'},W);
        function topRunsOrder(){return [].map.call(d.querySelectorAll('[data-c2run]'),function(x){return x.getAttribute('data-c2run');});}
        var topOrder=topRunsOrder();
        dfxCase('g2_f18',[c1,c2,c3],{
          'renders OK':c1==='OK'&&c2==='OK'&&c3==='OK',
          'both strategies appear on the LEADERBOARD':iA>=0&&iB>=0,
          'the 18-day run sinks BELOW the full-length one on the LEADERBOARD despite its far larger MAR':iA<iB,
          'the 18-day run carries a short-window mark naming a real reason':!!bPill&&bPill.length>0,
          'the full-length run carries no such mark':aPill===null,
          'both champions appear in COMPARE CHAMPIONS':jA>=0&&jB>=0,
          'COMPARE CHAMPIONS ranks the 18-day champion BELOW the full-length one too':jA<jB,
          'COMPARE CHAMPIONS: the MAR best-in-row mark goes to the full-length column, not the short-window one':marBestIdx>=0&&marBestIdx===jA,
          'TOP RUNS (BEST) puts the full-length run ahead of the short-window one on MAR':topOrder.indexOf(A.id)>=0&&topOrder.indexOf(B.id)>=0&&topOrder.indexOf(A.id)<topOrder.indexOf(B.id)
        },{iA:iA,iB:iB,bPill:bPill,aPill:aPill,jA:jA,jB:jB,champOrder:champOrder,marBestIdx:marBestIdx,topOrder:topOrder});
      })();

      // == g3-books-picks: Book flags and PICK RUNS marks/tiles (F4, F8, F9, F22) ==

      // -- g3_f4 (F4): the ORB look-ahead badge (and its always-on note) must flag only the
      //    touch-entry ORB family - ORB_2_0, ORB_3_0 to ORB_3_3 and their forks, ORB_3_1_125 but
      //    not its fixed close-confirmed fork _125C - never the legal ORB_3_6 line, on both the
      //    RUNBOARD books tile and the native BOOKS view, and "CHAMPION included" must be gone.
      (function(){
        function mkBook(idOff,name,legNames){
          var B=dfxClone(FIX);B.id=String(+FIX.id+idOff);B.strategy=name;B.starred=false;
          B.best_pnl_usd=250000;B.best_dd_usd=30000;B.multiplier=20;
          B.book={name:name,legs:legNames.map(function(n){return {strategy:n,weight:1};}),
            whole:{total_pnl:320000,max_drawdown:32000},pre_lockbox:{total_pnl:250000,max_drawdown:30000},
            lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:25000},
            slices_held:8,slices_n:8,lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true};
          return B;
        }
        var LEGAL=mkBook(931001,'BOOK: G3F4 LEGAL',['ORB_3_6_C2.py','ENGUQ_1_0.py']);
        var FLAGGED=mkBook(931002,'BOOK: G3F4 FLAGGED',['ORB_3_0.py','ENGUQ_1_0.py']);
        var FIXEDFORK=mkBook(931003,'BOOK: G3F4 FIXEDFORK',['ORB_3_1_125C.py','ENGUQ_1_0.py']);
        var STILLBAD=mkBook(931004,'BOOK: G3F4 STILLBAD',['ORB_3_1_125.py','ENGUQ_1_0.py']);
        var W=dfxWin([LEGAL,FLAGGED,FIXEDFORK,STILLBAD]);
        var calls=[];
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'full'},W));
        var rbTxt=dfxN(d.body.innerText||'');
        function rbBadged(id){var row=d.querySelector('tr[data-rank-run="'+id+'"]');return !!(row&&/ORB leg/.test(row.textContent||''));}
        var rb={legal:rbBadged(LEGAL.id),flagged:rbBadged(FLAGGED.id),fixedfork:rbBadged(FIXEDFORK.id),stillbad:rbBadged(STILLBAD.id)};
        var rbNoteGone=rbTxt.indexOf('CHAMPION included')<0;
        calls.push(doRender({c2Screen:'cmp',c2View:'books',c2Stage:'full'},W));
        var bkTxt=dfxN(d.body.innerText||'');
        function bkBadged(id){var row=d.querySelector('tr[data-c2run="'+id+'"]');return !!(row&&/ORB leg/.test(row.textContent||''));}
        var bk={legal:bkBadged(LEGAL.id),flagged:bkBadged(FLAGGED.id),fixedfork:bkBadged(FIXEDFORK.id),stillbad:bkBadged(STILLBAD.id)};
        var bkNoteGone=bkTxt.indexOf('CHAMPION included')<0;
        dfxCase('g3_f4',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'RUNBOARD: the legal ORB 3.6 leg carries no badge':!rb.legal,
          'RUNBOARD: a touch-entry ORB leg (3.0) carries the badge':rb.flagged,
          'RUNBOARD: the fixed close-confirmed 3.1_125C fork carries no badge':!rb.fixedfork,
          'RUNBOARD: the still-open 3.1_125 fork carries the badge':rb.stillbad,
          'RUNBOARD: the always-on CHAMPION-included note is gone':rbNoteGone,
          'BOOKS: the legal ORB 3.6 leg carries no badge':!bk.legal,
          'BOOKS: a touch-entry ORB leg (3.0) carries the badge':bk.flagged,
          'BOOKS: the fixed close-confirmed 3.1_125C fork carries no badge':!bk.fixedfork,
          'BOOKS: the still-open 3.1_125 fork carries the badge':bk.stillbad,
          'BOOKS: the always-on CHAMPION-included note is gone':bkNoteGone
        },{rb:rb,bk:bk});
      })();

      // -- g3_f8 (F8): PICK RUNS "Max DD" (IS) and "Max DD (in-sample)" (FULL) must compare the
      //    ABSOLUTE drawdown - smallest wins - and a missing drawdown must dash and never win.
      //    A book saves its drawdown positive and a single run saves it negative; before the
      //    fix the raw signed value was ranked with 'max', so any picked book always won.
      (function(){
        var BK=dfxClone(FIX);BK.id=String(+FIX.id+941001);BK.strategy='BOOK: G3F8';BK.starred=false;
        BK.best_dd_usd=36562.4;
        BK.book={legs:[{strategy:FIX.strategy}],whole:{total_pnl:1,max_drawdown:1},
          pre_lockbox:{total_pnl:1,max_drawdown:1},
          lockbox:{total_pnl:1,num_trades:1,win_rate:1,profit_factor:1,max_drawdown:1},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:1,pf:1,trades:1,pass:true},book:true};
        var SMALL=dfxClone(FIX);SMALL.id=String(+FIX.id+941002);SMALL.strategy='ZG3F8SMALL_1_0.py';SMALL.starred=false;SMALL.best_dd_usd=-14297.8;
        var BIG=dfxClone(FIX);BIG.id=String(+FIX.id+941003);BIG.strategy='ZG3F8BIG_1_0.py';BIG.starred=false;BIG.best_dd_usd=-53925;
        var NONE=dfxClone(FIX);NONE.id=String(+FIX.id+941004);NONE.strategy='ZG3F8NONE_1_0.py';NONE.starred=false;delete NONE.best_dd_usd;
        var ids=[BK.id,SMALL.id,BIG.id,NONE.id];
        var W=dfxWin([BK,SMALL,BIG,NONE]);
        function cellOf(td){return {v:dfxN(td.textContent),best:/color:var\(--green\)/.test(td.getAttribute('style')||'')};}
        var calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'runs',c2Stage:'is',cmpIds:ids},W));
        res.is=dfxRow('Max DD').map(cellOf);
        calls.push(doRender({c2Screen:'cmp',c2View:'runs',c2Stage:'full',cmpIds:ids},W));
        res.full=dfxRow('Max DD (in-sample)').map(cellOf);
        function chk(cells){
          return {n4:cells.length===4,
            bookAbs:!!cells[0]&&cells[0].v==='$37k',
            smallAbs:!!cells[1]&&cells[1].v==='$14k',
            bigAbs:!!cells[2]&&cells[2].v==='$54k',
            noneDash:!!cells[3]&&cells[3].v==='—',
            smallestWins:!!cells[1]&&cells[1].best===true,
            bookNotBest:!!cells[0]&&cells[0].best!==true,
            noneNotBest:!!cells[3]&&cells[3].best!==true};
        }
        var ci=chk(res.is),cf=chk(res.full);
        dfxCase('g3_f8',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'IS: four cells, all printed as positive dollar amounts':ci.n4&&ci.bookAbs&&ci.smallAbs&&ci.bigAbs,
          'IS: a missing drawdown dashes':ci.noneDash,
          'IS: the smallest ABSOLUTE drawdown wins, not the books positive sign':ci.smallestWins&&ci.bookNotBest,
          'IS: the missing figure never wins':ci.noneNotBest,
          'FULL: four cells, all printed as positive dollar amounts':cf.n4&&cf.bookAbs&&cf.smallAbs&&cf.bigAbs,
          'FULL: a missing drawdown dashes':cf.noneDash,
          'FULL: the smallest ABSOLUTE drawdown wins, not the books positive sign':cf.smallestWins&&cf.bookNotBest,
          'FULL: the missing figure never wins':cf.noneNotBest
        },{is:res.is.map(function(x){return x.v+(x.best?' [BEST]':'');}),full:res.full.map(function(x){return x.v+(x.best?' [BEST]':'');})});
      })();

      // -- g3_f9 (F9): the PICK RUNS NET P&L tile must follow STAGE (TOTAL/LB/WF/IS) instead of
      //    always showing the in-sample tuning-score money labelled "whole-run", and a missing
      //    figure must dash instead of printing $0.
      (function(){
        var F0=dfxClone(FIX);
        var E=dfxClone(FIX);E.id=String(+FIX.id+951001);E.strategy='ZG3F9EMPTY_1_0.py';E.starred=false;
        delete E.best_pnl_usd;delete E.top10_results;delete E.validate.lockbox;
        var ids=[String(F0.id),E.id];
        var W=dfxWin([F0,E]);
        function tileInfo(){
          var lbl=[].filter.call(d.querySelectorAll('.lbl'),function(e){return (e.textContent||'').indexOf('NET P&L')===0;})[0];
          if(!lbl)return null;
          var span=lbl.querySelector('span');
          var bars=lbl.nextElementSibling;
          var rows=bars?[].slice.call(bars.children):[];
          return {label:span?dfxN(span.textContent):null,
            vals:rows.map(function(row){var sp=row.querySelectorAll('span');return sp.length?dfxN(sp[sp.length-1].textContent):null;})};
        }
        var calls=[],res={};
        ['is','wf','lb','full'].forEach(function(st){
          calls.push(doRender({c2Screen:'cmp',c2View:'runs',c2Stage:st,cmpIds:ids},W));
          res[st]=tileInfo();
        });
        dfxCase('g3_f9',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'IS labelled in-sample (tuning), not whole-run':!!res.is&&/in-sample/i.test(res.is.label||'')&&!/whole-run/i.test(res.is.label||''),
          'IS reads the tuning-score money ($65,427, the fixtures best_pnl_usd)':!!res.is&&res.is.vals[0]==='$65,427',
          'IS: a run with no tuning score dashes, not $0':!!res.is&&res.is.vals[1]==='—',
          'WF labelled walk-forward':!!res.wf&&/walk-forward/i.test(res.wf.label||''),
          'WF reads a different figure than IS (the walk-forward net, not the tuning score)':!!res.wf&&!!res.is&&res.wf.vals[0]!==res.is.vals[0]&&res.wf.vals[0]!=='—',
          'WF: a run with no saved folds dashes, not $0':!!res.wf&&res.wf.vals[1]==='—',
          'LB labelled lockbox':!!res.lb&&/lockbox/i.test(res.lb.label||''),
          'LB reads a different figure than IS (the lockbox net, not the tuning score)':!!res.lb&&!!res.is&&res.lb.vals[0]!==res.is.vals[0]&&res.lb.vals[0]!=='—',
          'LB: a run with no saved lockbox dashes, not $0':!!res.lb&&res.lb.vals[1]==='—',
          'FULL labelled whole-run':!!res.full&&/whole-run/i.test(res.full.label||''),
          'FULL reads a different figure than IS (the whole-run total, not the tuning score)':!!res.full&&!!res.is&&res.full.vals[0]!==res.is.vals[0]
        },res);
      })();

      // -- g3_f22 (F22, NaN part only): PICK RUNS Robustness must print a dash with a reason for
      //    a book (its validate block saves no per-gate pass count) instead of the literal text
      //    "NaN", and GROUP mode must order every group - book or strategy - by the CHAMPIONS
      //    book rule (crown, then robustness / pre-lockbox net over drawdown, then money)
      //    instead of a raw scoreRun difference, which is NaN-vs-NaN for two book groups.
      (function(){
        var calls=[],res={};
        // -- Robustness dash-with-reason, IS and FULL --
        var BK=dfxClone(FIX);BK.id=String(+FIX.id+961001);BK.strategy='BOOK: G3F22 ROB';BK.starred=false;
        BK.book={legs:[{strategy:FIX.strategy}],whole:{total_pnl:1,max_drawdown:1},
          pre_lockbox:{total_pnl:1,max_drawdown:1},
          lockbox:{total_pnl:1,num_trades:1,win_rate:1,profit_factor:1,max_drawdown:1},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:1,pf:1,trades:1,pass:true},book:true};
        var robIds=[String(FIX.id),BK.id];
        var Wr=dfxWin([dfxClone(FIX),BK]);
        calls.push(doRender({c2Screen:'cmp',c2View:'runs',c2Stage:'is',cmpIds:robIds},Wr));
        res.robIs=dfxRow('Robustness').map(dfxCell);
        calls.push(doRender({c2Screen:'cmp',c2View:'runs',c2Stage:'full',cmpIds:robIds},Wr));
        res.robFull=dfxRow('Robustness').map(dfxCell);
        // -- GROUP order: two book-only groups (distinct _labOf labels via distinct file-style
        //    strategy strings), inserted LOW-before-HIGH (LOW gets the larger id so the
        //    id-descending picker pool visits it first) so a stable, order-preserving sort over
        //    an always-NaN comparator would leave the WRONG book (LOW) on top. --
        function mkBook2(idOff,name,net,dd){
          var B=dfxClone(FIX);B.id=String(+FIX.id+idOff);B.strategy=name;B.starred=false;
          B.book={legs:[{strategy:FIX.strategy}],whole:{total_pnl:net,max_drawdown:dd},
            pre_lockbox:{total_pnl:net,max_drawdown:dd},
            lockbox:{total_pnl:1,num_trades:1,win_rate:1,profit_factor:1,max_drawdown:1},
            lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
          B.validate={verdict:'PASS',lockbox:{pnl:1,pf:1,trades:1,pass:true},book:true};
          return B;
        }
        var HIGH=mkBook2(962001,'ZBKHI_1_0.py',300000,10000);   // pre-lockbox net / dd = 30 - the real champions-rule winner
        var LOW=mkBook2(962002,'ZBKLO_1_0.py',50000,10000);     // pre-lockbox net / dd = 5
        var Wg=dfxWin([LOW,HIGH]);   // insertion order LOW, HIGH; LOW.id > HIGH.id so the id-sorted pool visits LOW first
        calls.push(doRender({c2Screen:'cmp',c2View:'runs',cmpGroup:true,cmpIds:[LOW.id]},Wg));
        // read the actual GROUP header rows in DOM order - not raw page HTML, which also lists
        //   every strategy label in a <select> filter built off the unsorted run pool and would
        //   give a false pass/fail unrelated to gs.sort.
        var grpTxt=[].map.call(d.querySelectorAll('[data-cmpgrp]'),function(e){return e.textContent||'';});
        var jHigh=grpTxt.findIndex(function(s){return s.indexOf('ZBKHI')>=0;});
        var jLow=grpTxt.findIndex(function(s){return s.indexOf('ZBKLO')>=0;});
        var highBeforeLow=(jHigh>=0&&jLow>=0&&jHigh<jLow);
        dfxCase('g3_f22',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'IS Robustness: a normal run still reads a real number':!!res.robIs[0]&&/^[0-9]+$/.test(res.robIs[0].v),
          'IS Robustness: the book reads a dash, never the text NaN':!!res.robIs[1]&&res.robIs[1].v==='—'&&res.robIs[1].v.indexOf('NaN')<0,
          'IS Robustness: the books dash carries a reason on hover':!!res.robIs[1]&&res.robIs[1].tip.length>0,
          'FULL Robustness: a normal run still reads a real number':!!res.robFull[0]&&/^[0-9]+$/.test(res.robFull[0].v),
          'FULL Robustness: the book reads a dash, never the text NaN':!!res.robFull[1]&&res.robFull[1].v==='—'&&res.robFull[1].v.indexOf('NaN')<0,
          'FULL Robustness: the books dash carries a reason on hover':!!res.robFull[1]&&res.robFull[1].tip.length>0,
          'GROUP: the book with the better pre-lockbox net over drawdown (CHAMPIONS rule) is listed first':highBeforeLow
        },{robIs:res.robIs.map(function(x){return x.v;}),robFull:res.robFull.map(function(x){return x.v;}),jHigh:jHigh,jLow:jLow,grpTxt:grpTxt});
      })();

      // ============================================================================
      // g4-charts (F5, F15, F16, F17, F19, F20, F21): chart dates, full-screen view,
      // +ADD, EXPLORE hovers. Built on top of g1/g2/g3's fixtures and helpers.
      // ============================================================================

      // -- g4_f5 (F5): RUNBOARD 1A FUNNEL on LB/IS must slice the curve to ITS OWN calendar
      //    span (the lockbox door to date_to on LB; date_from to the lockbox door on IS)
      //    instead of the whole run's [date_from,date_to], and the key's ending $ must read
      //    the table's own stage figure (_netOf), marked ~, instead of the raw endpoint of
      //    a downsampled, differently-anchored curve slice.
      //    REPAIR ROUND additions: the IS half only got half-fixed (span still ran to the
      //    lockbox door, and the key still printed best_pnl_usd, a DIFFERENT overlapping
      //    window) -- the IS span must end at the first walk-forward fold instead, and its
      //    key must read the slice's own endpoint, not a swapped-in table figure. --
      (function(){
        var calls=[],res={};
        function lbSeries(){
          var raw=w.eval("JSON.stringify((window._cmpEqxSeries||[]).map(function(s){return {id:s.id,span:s.span||null,keyEnd:(s.keyEnd==null?null:s.keyEnd),keyApx:!!s.keyApx};}))");
          var arr=JSON.parse(raw);
          for(var i=0;i<arr.length;i++){if(String(arr[i].id)===String(FIX.id))return arr[i];}
          return {};
        }
        calls.push(doRender({cmpMode:'board',rbSample:'lb',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp'));
        var sLb=lbSeries();res.lbSpan=sLb.span;res.lbKeyEnd=sLb.keyEnd;res.lbKeyApx=sLb.keyApx;
        var keyRowLb=d.querySelector('.cmpovl-key [data-ovltog="'+FIX.id+'"]');
        res.lbKeyText=keyRowLb?dfxN(keyRowLb.textContent):null;
        res.lbKeyTilde=!!(res.lbKeyText&&res.lbKeyText.indexOf('~')>=0);
        var lbYrsM=/\xb7 ([0-9.]+)y/.exec(res.lbKeyText||'');res.lbKeyYrs=lbYrsM?+lbYrsM[1]:null;
        var expBtn=d.querySelector('[data-cmpexpand]');
        res.hasExpandBtn=!!expBtn;
        if(expBtn&&expBtn.onclick)expBtn.onclick();
        try{w.dispatchEvent(new w.Event('resize'));}catch(_rf){}
        var dateLabels=[].map.call(d.querySelectorAll('#ceqx-svg text[font-size="7.5"]'),function(t){return t.textContent||'';});
        res.fsFirstLabel=dateLabels[0]||null;
        var fsYm=/\/(\d{2})$/.exec(res.fsFirstLabel||'');res.fsFirstYear=fsYm?(2000+ +fsYm[1]):null;
        var fsClose=d.querySelector('#ceqx-close');if(fsClose&&fsClose.onclick)fsClose.onclick();
        calls.push(doRender({cmpMode:'board',rbSample:'is',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp'));
        var sIs=lbSeries();res.isSpan=sIs.span;res.isKeyEnd=sIs.keyEnd;res.isKeyApx=sIs.keyApx;
        var keyRowIs=d.querySelector('.cmpovl-key [data-ovltog="'+FIX.id+'"]');
        res.isKeyText=keyRowIs?dfxN(keyRowIs.textContent):null;
        res.isKeyTilde=!!(res.isKeyText&&res.isKeyText.indexOf('~')>=0);
        var expLbNet=FIX.validate.lockbox.pnl*(FIX.multiplier||20);
        var expIsNet=FIX.best_pnl_usd;
        var _folds=(FIX.top10_results||[]).filter(function(f){return f&&f.fold!=null&&(+f.test_bars>0);}).sort(function(a,b){return a.fold-b.fold;});
        var _tr0=+_folds[0].train_bars||0,_tbSum=_folds.reduce(function(s,f){return s+(+f.test_bars||0);},0);
        var _frac0=_tr0/(_tr0+_tbSum);
        var _dp=function(s){var m=/^([0-9]{4})-([0-9]{2})-([0-9]{2})/.exec(String(s||''));return m?+new Date(+m[1],+m[2]-1,+m[3]):Date.parse(s||'');};
        var _t0=_dp(FIX.date_from),_tLb=_dp(FIX.validate.lockbox.from);
        var _expIsEndMs=_t0+_frac0*(_tLb-_t0);
        var _p2=function(n){return n<10?('0'+n):(''+n);};
        var _expIsEndD=new Date(_expIsEndMs);
        var expIsEnd=_expIsEndD.getFullYear()+'-'+_p2(_expIsEndD.getMonth()+1)+'-'+_p2(_expIsEndD.getDate());
        var BK=dfxClone(FIX);BK.id=+FIX.id+969001;BK.strategy='BOOK G5: NOISE + ORB';BK.starred=false;BK.multiplier=1;
        delete BK.date_from;delete BK.date_to;
        BK.book={name:BK.strategy,legs:[{strategy:'NOISE_1_0.py',weight:1},{strategy:'ORB_1_0.py',weight:1}],
          whole:{total_pnl:300000,max_drawdown:20000,num_trades:2000,profit_factor:1.3},
          pre_lockbox:{total_pnl:250000,max_drawdown:18000},
          lockbox:{total_pnl:70000,num_trades:400,win_rate:44.5,profit_factor:1.4,max_drawdown:9000},
          lockbox_from:'2025-06-30',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:70000,pf:1.4,trades:400,pass:true},book:true,
          equity:FIX.validate.equity.slice(),lb_idx:FIX.validate.lb_idx};
        calls.push(doRender({cmpMode:'board',rbSample:'lb',rbRank:'net'}, dfxWin([FIX,BK]), 'cmp'));
        var rawBk=w.eval("JSON.stringify((window._cmpEqxSeries||[]).map(function(s){return {id:s.id,span:s.span||null};}))");
        var arrBk=JSON.parse(rawBk);
        function findSpan(bid){for(var i=0;i<arrBk.length;i++){if(String(arrBk[i].id)===String(bid))return arrBk[i].span;}return null;}
        res.bkSpan=findSpan(BK.id);
        res.fixSpanWithBook=findSpan(FIX.id);
        dfxCase('g4_f5',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'LB slice gets its OWN span, not the whole run (does not start at date_from)':Array.isArray(res.lbSpan)&&res.lbSpan.length===2&&res.lbSpan[0]!==FIX.date_from,
          'LB span starts at the saved lockbox door':Array.isArray(res.lbSpan)&&String(res.lbSpan[0]).slice(0,10)===FIX.validate.lockbox.from,
          'LB span ends at date_to':Array.isArray(res.lbSpan)&&String(res.lbSpan[1]).slice(0,10)===FIX.date_to,
          'LB key reads the table figure for lockbox net, not the raw curve tail':res.lbKeyEnd!=null&&Math.abs(res.lbKeyEnd-expLbNet)<1,
          'LB key is marked approximate (sourced from the table, not the drawn slice)':res.lbKeyApx===true,
          'LB key row shows the ~ mark on screen':res.lbKeyTilde,
          'LB key years read the SLICE span (about 1.5y), not the whole 16-year run':res.lbKeyYrs!=null&&res.lbKeyYrs>0.5&&res.lbKeyYrs<3,
          'IS slice gets its OWN span, not the whole run (does not run out to date_to)':Array.isArray(res.isSpan)&&res.isSpan.length===2&&res.isSpan[1]!==FIX.date_to,
          'IS span starts at date_from':Array.isArray(res.isSpan)&&String(res.isSpan[0]).slice(0,10)===FIX.date_from,
          'IS span ends at the first walk-forward fold, not the lockbox door':Array.isArray(res.isSpan)&&String(res.isSpan[1]).slice(0,10)===expIsEnd,
          'IS span end is well before the lockbox door (the fold, not the door)':Array.isArray(res.isSpan)&&String(res.isSpan[1]).slice(0,10)!==FIX.validate.lockbox.from,
          'IS key does NOT read best_pnl_usd (a different, overlapping tuning-score window)':res.isKeyEnd==null,
          'IS key is NOT marked approximate (it is the slice line own endpoint, not a swapped-in table figure)':res.isKeyApx===false,
          'IS key row shows no ~ mark on screen':!res.isKeyTilde,
          'a BOOK gets a real LB span from its own lockbox_from, not null':Array.isArray(res.bkSpan)&&res.bkSpan.length===2,
          'a BOOK LB span starts at its own book.lockbox_from':Array.isArray(res.bkSpan)&&String(res.bkSpan[0]).slice(0,10)===BK.book.lockbox_from,
          'a BOOK LB span ends at its own book.date_to':Array.isArray(res.bkSpan)&&String(res.bkSpan[1]).slice(0,10)===BK.book.date_to,
          'with a book on the board, the OTHER run keeps its own short LB span':Array.isArray(res.fixSpanWithBook)&&res.fixSpanWithBook.length===2&&res.fixSpanWithBook[0]!==FIX.date_from,
          'fullscreen: the LB slice keeps its own span (earliest x-axis date is 2025 or later)':res.fsFirstYear!=null&&res.fsFirstYear>=2025
        },res);
      })();

      // -- g4_f15 (F15): OVERLAY / PICK RUNS / RUNBOARD FULL must place the lockbox door at
      //    its own saved calendar date, not spread evenly across [date_from,date_to] as if
      //    the curve's points were dated one per day. Checked by reading each series' OWN
      //    pts[li].x AFTER cmpOvlMount has run (cmpOvlMount mutates the series objects in
      //    place, so window._cmpEqxSeries[i].pts is the real drawn geometry, not a re-derived
      //    guess). --
      (function(){
        var calls=[],res={};
        function doorInfo(){
          var raw=w.eval("JSON.stringify((window._cmpEqxSeries||[]).map(function(s){return {id:s.id,li:s.li,n:(s.pts?s.pts.length:((s.eq&&s.eq.length)||0)),doorX:(s.pts&&s.li!=null&&s.pts[s.li])?s.pts[s.li].x:null};}))");
          var arr=JSON.parse(raw);
          for(var i=0;i<arr.length;i++){if(String(arr[i].id)===String(FIX.id))return arr[i];}
          return {};
        }
        var t0=new Date(2010,5,7).getTime(), t1=new Date(2026,7,12).getTime(), tLb=new Date(2025,1,11).getTime();
        var correctFrac=(tLb-t0)/(t1-t0);
        calls.push(doRender({cmpMode:'board',rbSample:'full',rbRank:'mar',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp'));
        var rb=doorInfo();res.rbDoorX=rb.doorX;
        var naiveFrac=(rb.li!=null&&rb.n>1)?(rb.li/(rb.n-1)):null;
        calls.push(doRender({cmpMode:'runs',cmpIds:[String(FIX.id)]}, FIX_WIN, 'cmp'));
        var pr=doorInfo();res.prDoorX=pr.doorX;
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'lb',cmpIds:[String(FIX.id)]}, FIX_WIN));
        var ov=doorInfo();res.ovDoorX=ov.doorX;
        res.naiveFrac=naiveFrac;res.correctFrac=correctFrac;
        function close(a,b,tol){return a!=null&&b!=null&&Math.abs(a-b)<tol;}
        function far(a,b,tol){return a!=null&&b!=null&&Math.abs(a-b)>tol;}
        dfxCase('g4_f15',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the fixture is a real test: the naive trade-count fraction and the true calendar fraction differ by a measurable amount':far(naiveFrac,correctFrac,0.004),
          'RUNBOARD FULL: the lockbox door lands on its real saved date':close(res.rbDoorX,correctFrac,0.001),
          'RUNBOARD FULL: the door is NOT the naive even-by-trade-count spread':far(res.rbDoorX,naiveFrac,0.003),
          'PICK RUNS: the lockbox door lands on its real saved date':close(res.prDoorX,correctFrac,0.001),
          'PICK RUNS: the door is NOT the naive even-by-trade-count spread':far(res.prDoorX,naiveFrac,0.003),
          'OVERLAY: the lockbox door lands on its real saved date':close(res.ovDoorX,correctFrac,0.001),
          'OVERLAY: the door is NOT the naive even-by-trade-count spread':far(res.ovDoorX,naiveFrac,0.003)
        },res);
      })();

      // -- g4_f16 (F16): the fullscreen explorer must open with every picked/visible run
      //    drawn, not collapse to a single "RAW (n)" row showing only the highest-ending
      //    line -- and that group must be labelled RUNS (these are different strategies),
      //    not RAW (raw configs of one run). --
      (function(){
        var calls=[],res={};
        var A=dfxClone(FIX);
        var B=dfxClone(FIX);B.id=+FIX.id+964001;B.strategy='ZG16B_1_0.py';B.starred=false;
        B.validate.equity=B.validate.equity.map(function(v){return v*0.5;});
        var C=dfxClone(FIX);C.id=+FIX.id+964002;C.strategy='ZG16C_1_0.py';C.starred=false;
        C.validate.equity=C.validate.equity.map(function(v){return v*0.25;});
        var ids=[String(A.id),String(B.id),String(C.id)];
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'full',cmpIds:ids}, dfxWin([A,B,C])));
        var btn=d.querySelector('[data-cmpexpand]');
        res.hasBtn=!!btn;
        if(btn&&btn.onclick)btn.onclick();
        // the modal's first paint is scheduled via requestAnimationFrame, which will not have
        //   fired yet in this same synchronous tick; a dispatched resize event runs render()
        //   synchronously (its own onResize handler calls render() unconditionally) without
        //   waiting on a real animation frame.
        try{w.dispatchEvent(new w.Event('resize'));}catch(_rf){}
        var legend=d.querySelector('#ceqx-legend');
        res.legendHtml=legend?legend.innerHTML:'';
        var drawnSet={};
        [].forEach.call(d.querySelectorAll('#ceqx-chart path[data-sr]'),function(p){drawnSet[p.getAttribute('data-sr')]=1;});
        res.drawnIds=Object.keys(drawnSet);
        res.allThreeDrawn=ids.every(function(id){return !!drawnSet[id];});
        var closeBtn=d.querySelector('#ceqx-close');if(closeBtn&&closeBtn.onclick)closeBtn.onclick();
        dfxCase('g4_f16',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the expand button exists':res.hasBtn,
          'the fullscreen legend opens':!!legend,
          'every picked run is drawn, not just the highest-ending one':res.allThreeDrawn,
          'the group is labelled RUNS, not RAW (these are different strategies, not raw configs of one run)':res.legendHtml.indexOf('RUNS')>=0
        },res);
      })();

      // -- g4_f17 (F17): a run greyed or hidden in the OVERLAY chart key must stay
      //    greyed/hidden in the fullscreen view (id type mismatch: the key stores hidden
      //    ids as STRINGS, a series id off a lite read is a NUMBER). --
      (function(){
        var calls=[],res={};
        var A=dfxClone(FIX);
        var B=dfxClone(FIX);B.id=+FIX.id+965001;B.strategy='ZG17B_1_0.py';B.starred=false;
        // B must end HIGHER than A: with F16 also live, expandCompareEq's default-visibility
        //   pick is "whichever line ends highest" -- with a tie (two clones) that pick alone
        //   could mask F17 (B would coincidentally not be drawn even while genuinely still
        //   counted as "visible" by the buggy id-mismatch filter). Scaling B up makes it the
        //   one line F16's own default WOULD show, so seeing it correctly excluded proves the
        //   hidden-run filter, not F16's separate default-visibility pick.
        B.validate.equity=B.validate.equity.map(function(v){return v*1.5;});
        var ids=[String(A.id),String(B.id)];
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'full',cmpIds:ids}, dfxWin([A,B])));
        var keyRow=d.querySelector('.cmpovl-key [data-ovltog="'+B.id+'"]');
        res.hasKeyRow=!!keyRow;
        if(keyRow){
          keyRow.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
          keyRow.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
        }
        res.hiddenSet=w.eval("JSON.stringify(Array.from(window._cmpOvlHide||[]))");
        var btn=d.querySelector('[data-cmpexpand]');
        if(btn&&btn.onclick)btn.onclick();
        try{w.dispatchEvent(new w.Event('resize'));}catch(_rf){}
        var drawn={};
        [].forEach.call(d.querySelectorAll('#ceqx-chart path[data-sr]'),function(p){drawn[p.getAttribute('data-sr')]=1;});
        res.aDrawn=!!drawn[String(A.id)];res.bDrawn=!!drawn[String(B.id)];
        var closeBtn=d.querySelector('#ceqx-close');if(closeBtn&&closeBtn.onclick)closeBtn.onclick();
        dfxCase('g4_f17',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the key row exists':res.hasKeyRow,
          'the hidden set records the run as hidden, keyed by its string id':res.hiddenSet.indexOf(String(B.id))>=0,
          'run A stays drawn in the fullscreen view':res.aDrawn,
          'run B (hidden in the key) stays OUT of the fullscreen view':!res.bDrawn
        },res);
      })();

      // -- g4_f29 (F29, audit3_report.md): the fullscreen multi-run chart used to draw ONE
      //    SHARED lockbox (and walk-forward) band, positioned at whichever series happened to
      //    be first, and apply it to every run on screen -- even a run whose own lockbox door
      //    sits somewhere else on the shared calendar axis. _regionBounds' opts.noTabs branch
      //    now checks every VISIBLE series' own door and only returns a position when they all
      //    agree; disagreeing runs must draw with no band at all, never a borrowed one. Checked
      //    by mutating the already-mounted series geometry directly (the same objects
      //    expandCompareEq itself reads on every redraw -- see g4_f15's own note on why this is
      //    the real drawn geometry, not a re-derived guess) so the two doors provably disagree,
      //    then counting the lockbox band's own <rect fill="rgba(167,139,250,...)"> elements. --
      (function(){
        var calls=[],res={};
        var A=dfxClone(FIX);
        var B=dfxClone(FIX);B.id=+FIX.id+929001;B.strategy='ZG29B_1_0.py';B.starred=false;
        var ids=[String(A.id),String(B.id)];
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'full',cmpIds:ids}, dfxWin([A,B])));
        function lbRectCount(){return d.querySelectorAll('#ceqx-chart rect[fill*="167,139,250"]').length;}
        function openFresh(){var b2=d.querySelector('[data-cmpexpand]');if(b2&&b2.onclick)b2.onclick();
          try{w.dispatchEvent(new w.Event('resize'));}catch(_rf){}}
        function closeIt(){var c=d.querySelector('#ceqx-close');if(c&&c.onclick)c.onclick();}
        res.hasBtn=!!d.querySelector('[data-cmpexpand]');
        // baseline: two identical clones naturally agree on their own door (same dates, same
        //   lb_idx) -- the band must draw, proving the test is not just always-off.
        openFresh();
        res.agreeCount=lbRectCount();
        closeIt();
        // force genuine disagreement on the mounted series -- each keeps its OWN pts array
        //   (real per-run calendar fractions), so two clearly different indices give two doors
        //   that are not coincidentally equal.
        var mutated=w.eval("(function(){var S=window._cmpEqxSeries||[];if(S.length<2)return 'too few: '+S.length;"
          +"var a=S[0],b=S[1];if(!a.pts||!a.pts.length||!b.pts||!b.pts.length)return 'no pts';"
          +"var ia=Math.round(a.pts.length*0.2),ib=Math.round(b.pts.length*0.8);"
          +"a.li=ia;b.li=ib;return JSON.stringify({ax:a.pts[ia].x,bx:b.pts[ib].x});})()");
        res.mutated=mutated;
        openFresh();
        res.disagreeCount=lbRectCount();
        closeIt();
        var mObj=(function(){try{return JSON.parse(mutated);}catch(_e){return null;}})();
        res.doorGap=(mObj&&mObj.ax!=null&&mObj.bx!=null)?Math.abs(mObj.ax-mObj.bx):null;
        dfxCase('g4_f29',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the expand button exists':res.hasBtn,
          'the fixture is a real test: two agreeing runs DO draw a lockbox band':res.agreeCount>0,
          'the mutation genuinely put the two doors at different x positions':res.doorGap!=null&&res.doorGap>0.05,
          'two runs that genuinely disagree on their own lockbox door draw NO shared lockbox band':res.disagreeCount===0
        },res);
      })();

      // -- g4_f19 (F19): RUNBOARD +ADD must always get a hand-added run a column, even when
      //    10 family champions already fill the board, by re-packing the champion list
      //    around the pin rather than pushing the pin past a full slice -- and the overflow
      //    note must name the real cap and RANK BY, not a fixed "top-8 score cutoff". --
      (function(){
        var calls=[],res={};
        var docs=[],baseNet=FIX.validate.equity[FIX.validate.equity.length-1];
        for(var i=0;i<13;i++){
          var r=dfxClone(FIX);
          r.id=+FIX.id+968000+i;
          r.strategy='ZG19FAM'+i+'_1_0.py';
          r.starred=false;
          r.validate.equity=FIX.validate.equity.map(function(v){return v*(1-i*0.01);});
          docs.push(r);
        }
        var lowestId=docs[10].id;    // rank 11 -- cut even with no pins at all (original case)
        var rank9Id=docs[8].id;      // rank 9  -- a column BEFORE any pin is added
        var rank10Id=docs[9].id;     // rank 10 -- a column BEFORE any pin is added
        var outA=docs[11].id;        // rank 12 -- always outside the cutoff
        var outB=docs[12].id;        // rank 13 -- always outside the cutoff
        var Wr=dfxWin(docs);
        function findNote(){
          var c=[].filter.call(d.querySelectorAll('div'),function(x){var t=x.textContent||'';return t.indexOf('more famil')>=0&&t.indexOf('cutoff')>=0;});
          c.sort(function(a,b){return (a.textContent||'').length-(b.textContent||'').length;});
          return c[0]?dfxN(c[0].textContent):'';
        }
        function seriesIds(){return JSON.parse(w.eval("JSON.stringify((window._cmpEqxSeries||[]).map(function(s){return String(s.id);}))"));}
        calls.push(doRender({cmpMode:'board',rbSample:'full',rbRank:'net'}, Wr, 'cmp'));
        var before=seriesIds();res.beforeCount=before.length;res.beforeHasLowest=before.indexOf(String(lowestId))>=0;
        // the overflow note before +ADD: with 13 families and a cap of 10, three are genuinely
        //   cut here, so this is the state that actually exercises the note's wording.
        res.noteText=findNote();
        calls.push(doRender({cmpMode:'board',rbSample:'full',rbRank:'net',rbAdd:[String(lowestId)]}, Wr, 'cmp'));
        var after=seriesIds();res.afterCount=after.length;res.afterHasLowest=after.indexOf(String(lowestId))>=0;

        // -- F19 REGRESSION (a): two pins, BOTH already outside the top 10. The two
        //    champions they push out (rank 9 and rank 10) must land in the overflow note,
        //    not vanish -- that note exists precisely so nothing does. --
        calls.push(doRender({cmpMode:'board',rbSample:'full',rbRank:'net',rbAdd:[String(outA),String(outB)]}, Wr, 'cmp'));
        var segA=seriesIds();
        res.aCount=segA.length;
        res.aHasOutA=segA.indexOf(String(outA))>=0;
        res.aHasOutB=segA.indexOf(String(outB))>=0;
        res.aHasRank9=segA.indexOf(String(rank9Id))>=0;
        res.aHasRank10=segA.indexOf(String(rank10Id))>=0;
        res.aNote=findNote();
        var aNoteM=/\+(\d+) more/.exec(res.aNote);res.aNoteCount=aNoteM?+aNoteM[1]:null;

        // -- F19 REGRESSION (b): a pin already sitting at column 9, together with two
        //    outside pins. All three must survive as columns -- the already-seated pin
        //    must never be the one that gets sliced away to make room for the others. --
        calls.push(doRender({cmpMode:'board',rbSample:'full',rbRank:'net',rbAdd:[String(rank9Id),String(outA),String(outB)]}, Wr, 'cmp'));
        var segB=seriesIds();
        res.bCount=segB.length;
        res.bHasRank9=segB.indexOf(String(rank9Id))>=0;
        res.bHasOutA=segB.indexOf(String(outA))>=0;
        res.bHasOutB=segB.indexOf(String(outB))>=0;

        dfxCase('g4_f19',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'before +ADD: exactly 10 champion columns (the RUNBOARD cap)':res.beforeCount===10,
          'before +ADD: the 11th-ranked family is cut, as expected':!res.beforeHasLowest,
          'after +ADD: the hand-added run actually joins the chart and matrix':res.afterHasLowest,
          'after +ADD: still at most 10 columns (re-packed, not broken)':res.afterCount<=10,
          'the overflow note names the real cap (10), not a fixed "top-8"':res.noteText.indexOf('top-8')<0&&res.noteText.indexOf('10 column')>=0,
          'the overflow note blames RANK BY, not an unrelated "score" cutoff':res.noteText.indexOf('score cutoff')<0,
          'regression (a): both outside pins join the columns':res.aHasOutA&&res.aHasOutB,
          'regression (a): still at most 10 columns':res.aCount<=10,
          'regression (a): the two champions the pins displaced (rank 9 and 10) are pushed out, not dropped silently':!res.aHasRank9&&!res.aHasRank10,
          'regression (a): the overflow note reports all 3 families the pins pushed below the cutoff':res.aNoteCount===3,
          'regression (b): a pin already at column 9 survives when other pins are added too':res.bHasRank9,
          'regression (b): both outside pins also join alongside it':res.bHasOutA&&res.bHasOutB,
          'regression (b): at most 10 columns total':res.bCount<=10
        },res);
      })();

      // -- g4_f20 (F20): EXPLORE's "N of M rows plotted" hover must count only the failed
      //    rows PLOT FAILURES would actually draw (both figures present), not every hidden
      //    failed row, and must say so about the rest instead of promising the switch draws
      //    all of them. --
      (function(){
        var calls=[],res={};
        var PASS=dfxClone(FIX);PASS.id=+FIX.id+967001;PASS.strategy='ZG20PASS_1_0.py';PASS.starred=false;PASS.validate.verdict='PASS';
        var FAILPL=dfxClone(FIX);FAILPL.id=+FIX.id+967002;FAILPL.strategy='ZG20FAILPL_1_0.py';FAILPL.starred=false;FAILPL.validate.verdict='FAIL';
        var FAILNF=dfxClone(FIX);FAILNF.id=+FIX.id+967003;FAILNF.strategy='ZG20FAILNF_1_0.py';FAILNF.starred=false;FAILNF.validate.verdict='FAIL';
        delete FAILNF.validate.lockbox;
        var Wr=dfxWin([PASS,FAILPL,FAILNF]);
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'raw',resXAxis:'dd',resFail:'0'}, Wr));
        var hintOff=dfxTips('rows plotted')[0]||'';
        res.hintOff=hintOff;
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'raw',resXAxis:'dd',resFail:'1'}, Wr));
        var plottedTitles=[].map.call(d.querySelectorAll('[data-repoint] title'),function(t){return t.textContent||'';});
        res.failPlDrawnOn=plottedTitles.some(function(s){return s.indexOf('#'+FAILPL.id)>=0;});
        // F20 follow-up (repair round): a failed row held under MIN TRADES has BOTH figures -
        //   it is not missing anything - so it must get its own sentence, not be folded into
        //   "no figure on these axes" (which used to be the ONLY sentence shown when every
        //   placeable failure also happened to sit under the floor).
        var FAILMIN=dfxClone(FIX);FAILMIN.id=+FIX.id+967004;FAILMIN.strategy='ZG20FAILMIN_1_0.py';FAILMIN.starred=false;FAILMIN.validate.verdict='FAIL';
        FAILMIN.validate.lockbox.trades=10;   // below the 30-trade floor; FAILPL's own 301 stays above it
        var Wr2=dfxWin([PASS,FAILPL,FAILNF,FAILMIN]);
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['lb'],resAxis:'raw',resXAxis:'dd',resFail:'0',resMinTrd:'30'}, Wr2));
        var hintMin=dfxTips('rows plotted')[0]||'';
        var _mtIdx=hintMin.indexOf('held under the MIN TRADES floor');
        delete res.hintOff;
        res.hintMinTail=_mtIdx>=0?hintMin.slice(Math.max(0,_mtIdx-60),_mtIdx+200):('NOT FOUND: '+hintMin.slice(0,400));
        dfxCase('g4_f20',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the hover names the PLACEABLE failed-row count (1), not every failed row (2)':hintOff.indexOf(' 1 failed row is left off')>=0,
          'the hover does not claim 2 failed rows are left off on purpose':hintOff.indexOf(' 2 failed row')<0,
          'the hover separately names the failed row with no figure on these axes':hintOff.indexOf('no figure on these axes')>=0,
          'turning PLOT FAILURES on actually draws the placeable failed row':res.failPlDrawnOn,
          'MIN TRADES: a failed row under the floor names that real reason':hintMin.indexOf('held under the MIN TRADES floor')>=0,
          'MIN TRADES: that row is not ALSO folded into "no figure on these axes"':(function(){
            var noFig=hintMin.match(/([0-9]+) failed rows? (?:has|have) no figure on these axes/);
            return !noFig||parseInt(noFig[1],10)===1;})()
        },res);
      })();

      // -- g4_f21 (F21): EXPLORE's PF axis-button hover must not claim PF ignores PROFIT
      //    STAGE "and says so on the axis" -- PF follows the stage on run/configuration
      //    rows, and the axis caption never made that claim. --
      (function(){
        var calls=[],res={};
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs'}, FIX_WIN));
        var btn=d.querySelector('[data-resaxis="pf"]');
        res.pfHover=btn?(btn.getAttribute('title')||''):'';
        dfxCase('g4_f21',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the PF axis button exists':!!btn,
          'the hover no longer claims PF ignores PROFIT STAGE':res.pfHover.indexOf('ignores PROFIT STAGE')<0,
          'the hover says PF follows PROFIT STAGE on run and configuration rows':res.pfHover.indexOf('follows PROFIT STAGE')>=0,
          'the hover no longer points to a false "says so on the axis" claim':res.pfHover.indexOf('says so on the axis')<0
        },res);
      })();

      // -- g5_gv (repair round, item 4): a GATE-VALIDATE JOB (no `validate` block at all) must
      //    print its whole-run and in-sample money off its own ungated backtest -
      //    x.equity.cum and gate_validate.ungated_is/ungated_full - never the GATED headline
      //    pick (best_pnl_usd/best_pf/best_trades/best_dd_usd, sometimes the lockbox trades
      //    themselves), on PICK RUNS FULL, PICK RUNS IS, RUNBOARD's family drill and EXPLORE. --
      (function(){
        var calls=[],res={};
        var G=dfxClone(FIX);G.id=String(+FIX.id+972001);G.strategy='ZGATEVAL_1_0.py';G.starred=false;
        delete G.validate;delete G.top10_results;
        G.scope='Gate-Validate';
        var W=dfxWin([G]);
        var gf=G.gate_validate.ungated_full,gi=G.gate_validate.ungated_is,mc=+G.multiplier||20;
        var wantFullNet=_ab$Like((+G.equity.cum[G.equity.cum.length-1]||0)*mc);
        var wantIsNet=_ab$Like((+gi.total_pnl||0)*mc);
        var wantGatedIs=_ab$Like(+G.best_pnl_usd);
        function _ab$Like(v){var a=Math.abs(v||0),sg=(v<0?'-$':'$');
          return a>=1e6?(sg+(a/1e6).toFixed(2).replace(/\.?0+$/,'')+'M'):(a>=1000?(sg+Math.round(a/1000)+'k'):(sg+Math.round(a)));}
        // PICK RUNS FULL (old tab, cmpScope 'tot')
        calls.push(doRender({cmpScope:'tot',cmpIds:[G.id]},W,'cmp'));
        var totCells=dfxRow('Total net $ (whole run)');
        var isCells=dfxRow(String.fromCharCode(0x251c)+' in-sample $');
        res.fullTotTxt=totCells[0]?dfxN(totCells[0].textContent):null;
        res.fullIsTxt=isCells[0]?dfxCell(isCells[0]).v:null;
        res.fullHasIsOnlyPill=res.fullTotTxt?(res.fullTotTxt.indexOf('IS only')>=0):null;
        // PICK RUNS IS (old tab, default scope 'all')
        calls.push(doRender({cmpScope:'all',cmpIds:[G.id]},W,'cmp'));
        var netRow=dfxRow('Net P&L'),pfRow=dfxRow('PF'),trRow=dfxRow('Trades');
        res.isNetTxt=netRow[0]?dfxN(netRow[0].textContent):null;
        res.isPfTxt=pfRow[0]?dfxN(pfRow[0].textContent):null;
        res.isTrTxt=trRow[0]?dfxN(trRow[0].textContent):null;
        // EXPLORE (LEVEL AUTO-VAL, run rows table - mirrors g2_f2's own layout)
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['is','wf','lb'],resAxis:'raw',resXAxis:'dd',resCols:'all',c2Tbl:true},W));
        var exRow=[].filter.call(d.querySelectorAll('tr[data-rerow]'),function(t){return (t.textContent||'').indexOf('#'+G.id)>=0;})[0];
        var whatCell=exRow?[].filter.call(exRow.querySelectorAll('td'),function(td){var t=td.textContent||'';return t.indexOf('Auto-Validate run #')>=0||t.indexOf('Gate-Validate job #')>=0;})[0]:null;
        res.exWhat=whatCell?dfxN(whatCell.textContent):null;
        res.exRowTxt=exRow?dfxN(exRow.textContent):null;
        var hdrEx=[].map.call(d.querySelectorAll('tr th'),function(x){return (x.textContent||'').replace(/[^A-Z /%$()]/g,'').trim();});
        res.exHdr=hdrEx;
        function exCellOf2(nm){var q=hdrEx.indexOf(nm);return (exRow&&q>=0)?dfxN(exRow.cells[q].textContent):null;}
        res.exTotalCell=exCellOf2('TOTAL');
        res.exDdCell=exCellOf2('DRAWDOWN');
        res.exPfCell=exCellOf2('PF');
        res.exTradesCell=exCellOf2('TRADES');
        res.exWfCell=exCellOf2('WALKFWD');
        res.exLbCell=exCellOf2('LOCKBOX');
        dfxCase('g5_gv',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'PICK RUNS FULL: Total net $ reads the ungated whole-run curve, not the gated headline':!!res.fullTotTxt&&res.fullTotTxt.indexOf(wantFullNet)>=0,
          'PICK RUNS FULL: Total net $ never shows the gated headline figure instead':!!res.fullTotTxt&&res.fullTotTxt.indexOf(wantGatedIs)<0,
          'PICK RUNS FULL: no false "IS only" pill (this run has an honest whole-run curve)':res.fullHasIsOnlyPill===false,
          'PICK RUNS FULL: in-sample $ reads the measured pre-fold slice, not the gated headline':res.fullIsTxt===wantIsNet,
          'PICK RUNS IS: Net P&L reads the measured pre-fold slice, not the gated headline':!!res.isNetTxt&&res.isNetTxt.indexOf(wantIsNet)>=0&&res.isNetTxt.indexOf(wantGatedIs)<0,
          'PICK RUNS IS: PF reads the measured slice profit factor':!!res.isPfTxt&&res.isPfTxt.indexOf((+gi.profit_factor).toFixed(2))>=0,
          'PICK RUNS IS: Trades reads the measured slice trade count':!!res.isTrTxt&&res.isTrTxt.indexOf(String(gi.num_trades))>=0,
          'EXPLORE: TOTAL reads the ungated whole-run net, not the gated headline':res.exTotalCell===wantFullNet,
          'EXPLORE: DRAWDOWN reads the ungated whole-run drawdown':res.exDdCell==='$22k',
          'EXPLORE: PF reads the ungated whole-run profit factor':!!res.exPfCell&&res.exPfCell.indexOf((+gf.profit_factor).toFixed(2))>=0,
          'EXPLORE: TRADES reads the ungated whole-run trade count':!!res.exTradesCell&&res.exTradesCell.replace(/,/g,'')===String(gf.num_trades),
          'EXPLORE: WALKFWD dashes (this job saved no walk-forward folds of its own)':res.exWfCell==='—',
          'EXPLORE: LOCKBOX dashes (this job saved no lockbox slice of its own)':res.exLbCell==='—',
          'EXPLORE: WHAT IT DOES calls it a Gate-Validate job, not an Auto-Validate run':!!res.exWhat&&res.exWhat.indexOf('Gate-Validate job #'+G.id)>=0
        },res);
      })();

      // -- g5_bookis (repair round, item 5 - F2 REGRESSION): a BOOK never saves gate_validate
      //    (it pools legs, not an ML-gate bake-off), so gvIS in _totA used to read null for
      //    every book and PICK RUNS FULL / RUNBOARD FULL dashed "in-sample $" with a false
      //    "no in-sample figures" reason even though book.pre_lockbox carries exactly that
      //    figure - the same one LEADERBOARD IS / OVERLAY IS / the run report already print,
      //    and the one that makes IS + WF + LB add back up to TOTAL. --
      (function(){
        var calls=[],res={};
        var BK=dfxClone(FIX);BK.id=String(+FIX.id+973001);BK.strategy='BOOK G2: NOISE + ORB';BK.starred=false;BK.multiplier=1;
        delete BK.top10_results;delete BK.gate_validate;
        BK.book={name:BK.strategy,legs:[{strategy:'NOISE_1_0.py',weight:1},{strategy:'ORB_1_0.py',weight:1}],
          whole:{total_pnl:1685715,max_drawdown:22000,num_trades:9707,profit_factor:1.50},
          pre_lockbox:{total_pnl:1395904,max_drawdown:18000},
          lockbox:{total_pnl:289811,num_trades:622,win_rate:44.5,profit_factor:1.49,max_drawdown:9000},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-08-12'};
        BK.validate={verdict:'PASS',lockbox:{pnl:289811,pf:1.49,trades:622,pass:true},book:true,
          equity:[0,500000,1000000,1685715],lb_idx:2};
        var W=dfxWin([BK]);
        // PICK RUNS FULL (old tab, cmpScope 'tot')
        calls.push(doRender({cmpScope:'tot',cmpIds:[BK.id]},W,'cmp'));
        var isCells=dfxRow(String.fromCharCode(0x251c)+' in-sample $');
        var isCell=isCells[0]?dfxCell(isCells[0]):null;
        res.prIsTxt=isCell?isCell.v:null;
        res.prIsTip=isCell?isCell.tip:null;
        var totCells=dfxRow('Total net $ (whole run)');
        res.prTotTxt=totCells[0]?dfxN(totCells[0].textContent):null;
        var wfCells=dfxRow(String.fromCharCode(0x251c)+' walk-forward $');
        res.prWfTxt=wfCells[0]?dfxN(wfCells[0].textContent):null;
        var lbCells=dfxRow(String.fromCharCode(0x2514)+' lockbox $');
        res.prLbTxt=lbCells[0]?dfxN(lbCells[0].textContent):null;
        // RUNBOARD FULL "IS $" row
        calls.push(doRender({cmpMode:'board',rbSample:'full',cmpIds:[BK.id]},W,'cmp'));
        var colIds=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        function rbCellOf(lbl){var i=colIds.indexOf(String(BK.id)),cells=dfxRow(lbl);return (i>=0&&cells[i])?dfxCell(cells[i]):null;}
        var rbIs=rbCellOf('IS $');
        res.rbIsTxt=rbIs?rbIs.v:null;
        res.rbIsTip=rbIs?rbIs.tip:null;
        dfxCase('g5_bookis',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'PICK RUNS FULL: a book’s in-sample $ reads its own pre_lockbox pool, not a dash':res.prIsTxt==='$1.4M',
          'PICK RUNS FULL: the in-sample $ dash reason is gone for a book':!res.prIsTip,
          'PICK RUNS FULL: the whole-run total still reads the book’s own curve endpoint':!!res.prTotTxt&&res.prTotTxt.indexOf('$1.69M')>=0,
          'RUNBOARD FULL: "IS $" reads the book’s pre_lockbox pool too, not a bare dash':res.rbIsTxt==='$1.4M',
          'RUNBOARD FULL: "IS $" carries no empty/false reason once it has a real figure':!res.rbIsTip
        },res);
      })();

      // -- g5_archpick (repair round, item 13): a PICKED run that is ARCHIVED must read as
      //    archived, not as "older than the loaded runs" with a false LOAD ALL promise - LOAD
      //    ALL (a full-account Firestore read) can never bring an archived run back; only
      //    switching on archived runs in Past Runs can. --
      (function(){
        var calls=[],res={};
        var A=dfxClone(FIX);A.id=String(+FIX.id+974001);A.strategy='ZARCHPICK_1_0.py';A.starred=false;A.archived=true;
        var N=dfxClone(FIX);N.id=String(+FIX.id+974002);N.strategy='ZARCHPICK2_1_0.py';N.starred=false;
        var W=dfxWin([A,N]);
        // PICK RUNS (old tab)
        calls.push(doRender({cmpIds:[A.id]},W,'cmp'));
        var bodyTxt=dfxN(d.body.innerText||'');
        res.prHasArchNote=bodyTxt.indexOf('is archived - switch on archived runs in Past Runs')>=0;
        res.prHasFalseOlderNote=bodyTxt.indexOf(String(A.id))>=0&&bodyTxt.indexOf('older than the loaded runs - LOAD ALL')>=0;
        // OVERLAY (cmp2, PICKED source)
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'lb',cmpIds:[A.id,N.id]},W));
        var bodyTxt2=dfxN(d.body.innerText||'');
        res.ovlHasArchNote=bodyTxt2.indexOf('archived, so')>=0&&bodyTxt2.indexOf('switch on archived runs in Past Runs')>=0;
        res.ovlHasFalseOlderNote=bodyTxt2.indexOf('older than the loaded runs, so')>=0;
        res.ovlHasWrongLoadAllPastRuns=bodyTxt2.indexOf('LOAD ALL on Past Runs')>=0;
        dfxCase('g5_archpick',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'PICK RUNS: an archived pick reads "is archived - switch on archived runs", not older-than-loaded':res.prHasArchNote&&!res.prHasFalseOlderNote,
          'OVERLAY: an archived pick reads the same true reason, not the false older-than-loaded promise':res.ovlHasArchNote&&!res.ovlHasFalseOlderNote,
          'OVERLAY: never points to the non-existent "LOAD ALL on Past Runs" button':!res.ovlHasWrongLoadAllPastRuns
        },res);
      })();

      // -- g5_wfrange (repair round, item 7): a run validated through the ML-gate bake-off (the
      //    crowns evidence) saves gate_validate.wf_range - the fold-1 boundary under a different
      //    name - but no validate.windows.wf_split. _reRunStages could then never place BOTH ends
      //    of the in-sample stretch, so IN-SAMPLE and the default all-three-stage view dashed MAR
      //    and R / YR with "This row records no date window", even though DATA WINDOW on the very
      //    same row showed real dates and OVERLAY FULL printed MAR / R-per-YR for the identical run. --
      (function(){
        var calls=[],res={};
        var CR=dfxClone(FIX);CR.id=String(+FIX.id+975001);CR.strategy='ZWFRANGE_1_0.py';CR.starred=true;
        res.hasWfRange=!!(CR.gate_validate&&Array.isArray(CR.gate_validate.wf_range)&&CR.gate_validate.wf_range[0]);
        res.hasWfSplit=!!(CR.validate&&CR.validate.windows&&CR.validate.windows.wf_split);
        var W=dfxWin([CR]);
        function numTxt(t){return t!=null&&/^-?[0-9]/.test(t);}
        calls.push(doRender({c2Screen:'explore',resLvl:'all',resShow:'runs',resSegs:['is'],resCols:'all',c2Tbl:true,resAxis:'ratio',resXAxis:'dd'},W));
        var isRow=r4Row('runs:'+CR.id)||{};
        res.isMar=isRow['MAR']?isRow['MAR'].t:null;res.isMarTip=isRow['MAR']?isRow['MAR'].tip:null;
        res.isRpy=isRow['R / YR']?isRow['R / YR'].t:null;
        res.isWin=isRow['DATA WINDOW']?isRow['DATA WINDOW'].t:null;
        calls.push(doRender({c2Screen:'explore',resLvl:'all',resShow:'runs',resSegs:['is','wf','lb'],resCols:'all',c2Tbl:true,resAxis:'ratio',resXAxis:'dd'},W));
        var allRow=r4Row('runs:'+CR.id)||{};
        res.allMar=allRow['MAR']?allRow['MAR'].t:null;res.allMarTip=allRow['MAR']?allRow['MAR'].tip:null;
        res.allRpy=allRow['R / YR']?allRow['R / YR'].t:null;
        dfxCase('g5_wfrange',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'fixture actually matches the evidence: wf_range present, wf_split absent':res.hasWfRange&&!res.hasWfSplit,
          'IN-SAMPLE: MAR is a real number, not dashed for a missing date window':numTxt(res.isMar),
          'IN-SAMPLE: R / YR is a real number, not dashed':numTxt(res.isRpy),
          'IN-SAMPLE: the false "records no date window" reason is gone':!res.isMarTip||res.isMarTip.indexOf('records no date window')<0,
          'ALL THREE STAGES: MAR is a real number, not dashed':numTxt(res.allMar),
          'ALL THREE STAGES: R / YR is a real number, not dashed':numTxt(res.allRpy),
          'ALL THREE STAGES: the false "records no date window" reason is gone':!res.allMarTip||res.allMarTip.indexOf('records no date window')<0
        },res);
      })();

      // -- g6_gvisyrs (repair round): a Gate-Validate JOB TYPE run (no `validate` block at
      //    all) switched PICK RUNS' IN-SAMPLE row - Net P&L / Max DD / PF / Win % / Trades -
      //    to the measured gate_validate.ungated_is slice, but left MAR, R / YR and $/day on
      //    the OLD gated headline (best_pnl_usd / best_dd_usd / best_win_rate / best_pf /
      //    best_trades) divided by the WHOLE run's years - reviewer reproduction: MAR 0.39,
      //    R / YR 23.3, exactly $65,427 over $10,303 across the run's 16.2 years. The WHOLE-
      //    RUN tab's "Max DD (in-sample)" row, and RUNBOARD's FULL-sample "DD" row, had the
      //    matching gap: both kept printing the gated headline drawdown instead of the
      //    ungated one (live #390: "in-sample $ --" beside "Max DD (in-sample)" still the
      //    gated figure; #391 / #393: "IS $ --" beside "DD" still the gated figure). RUNBOARD's
      //    IS-sample MAR shares _isYrs with PICK RUNS through _rbYrs and read a THIRD wrong
      //    number off the SAME measured net/drawdown (0.13, since those two cells were already
      //    correct there pre-fix and only the years were wrong). --
      (function(){
        var calls=[],res={};
        var G=dfxClone(FIX);G.id=String(+FIX.id+994001);G.strategy='ZGVISYR_1_0.py';G.starred=false;
        delete G.validate;delete G.top10_results;G.scope='Gate-Validate';
        var N=dfxClone(G);N.id=String(+FIX.id+994002);N.strategy='ZGVISYRB_1_0.py';
        delete N.gate_validate.ungated_is;
        var W=dfxWin([G,N]);
        // PICK RUNS IN-SAMPLE (old tab, cmpScope 'all')
        calls.push(doRender({cmpScope:'all',cmpIds:[G.id,N.id]},W,'cmp'));
        var marRow=dfxRow('MAR'),rpyRow=dfxRow('R/yr'),dayRow=dfxRow(String.fromCharCode(36)+'/day');
        res.prIsMarG=marRow[0]?dfxN(marRow[0].textContent):null;
        res.prIsMarN=marRow[1]?dfxN(marRow[1].textContent):null;
        res.prIsRpyG=rpyRow[0]?dfxN(rpyRow[0].textContent):null;
        res.prIsRpyN=rpyRow[1]?dfxN(rpyRow[1].textContent):null;
        res.prIsDayG=dayRow[0]?dfxN(dayRow[0].textContent):null;
        res.prIsDayN=dayRow[1]?dfxN(dayRow[1].textContent):null;
        // PICK RUNS WHOLE-RUN (old tab, cmpScope 'tot')
        calls.push(doRender({cmpScope:'tot',cmpIds:[G.id,N.id]},W,'cmp'));
        var ddisRow=dfxRow('Max DD (in-sample)');
        var ddisG=ddisRow[0]?dfxCell(ddisRow[0]):null,ddisN=ddisRow[1]?dfxCell(ddisRow[1]):null;
        res.prTotDdisG=ddisG?ddisG.v:null;
        res.prTotDdisN=ddisN?ddisN.v:null;res.prTotDdisNTip=ddisN?ddisN.tip:null;
        // RUNBOARD FULL sample: the "DD" and "MAR" rows
        calls.push(doRender({cmpMode:'board',rbSample:'full',cmpIds:[G.id,N.id]},W,'cmp'));
        var colIdsF=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        function rbCellF(lbl,id){var i=colIdsF.indexOf(String(id)),cells=dfxRow(lbl);return (i>=0&&cells[i])?dfxCell(cells[i]):null;}
        var rbDdG=rbCellF('DD',G.id),rbMarF=rbCellF('MAR',G.id);
        res.rbFullDdG=rbDdG?rbDdG.v:null;
        res.rbFullMarG=rbMarF?rbMarF.v:null;
        // RUNBOARD IS sample: the "MAR" cell (shares _rbYrs / _isYrs with PICK RUNS)
        calls.push(doRender({cmpMode:'board',rbSample:'is',cmpIds:[G.id,N.id]},W,'cmp'));
        var colIdsI=[].map.call(d.querySelectorAll('th[data-rbc]'),function(x){return x.getAttribute('data-rbc');});
        function rbCellI(lbl,id){var i=colIdsI.indexOf(String(id)),cells=dfxRow(lbl);return (i>=0&&cells[i])?dfxCell(cells[i]):null;}
        var rbMarG=rbCellI('MAR',G.id),rbMarN=rbCellI('MAR',N.id);
        res.rbIsMarG=rbMarG?rbMarG.v:null;
        res.rbIsMarN=rbMarN?rbMarN.v:null;
        dfxCase('g6_gvisyrs',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'PICK RUNS IS: MAR reads the measured in-sample slice over its OWN in-sample years, not the gated headline over the whole run':res.prIsMarG==='0.37',
          'PICK RUNS IS: MAR dashes (never the gated headline) when the run saved no measured slice':res.prIsMarN===String.fromCharCode(0x2014),
          'PICK RUNS IS: R / YR reads the same measured slice and years':res.prIsRpyG==='19.6',
          'PICK RUNS IS: R / YR dashes when the run saved no measured slice':res.prIsRpyN===String.fromCharCode(0x2014),
          'PICK RUNS IS: $/day reads the measured slice over its own in-sample day count':res.prIsDayG==='$5',
          'PICK RUNS IS: $/day dashes when the run saved no measured slice':res.prIsDayN===String.fromCharCode(0x2014),
          'PICK RUNS WHOLE-RUN: Max DD (in-sample) reads the measured slice drawdown, not the gated headline':res.prTotDdisG==='$5k',
          'PICK RUNS WHOLE-RUN: Max DD (in-sample) dashes with the true reason when the run saved no measured slice':res.prTotDdisN===String.fromCharCode(0x2014)&&res.prTotDdisNTip.indexOf('in-sample')>=0,
          'RUNBOARD FULL: DD reads the ungated whole-run drawdown, not the gated headline':res.rbFullDdG==='$22k',
          'RUNBOARD FULL: MAR follows that corrected drawdown':res.rbFullMarG==='0.77',
          'RUNBOARD IS: MAR matches PICK RUNS IS MAR (the same shared in-sample-years helper)':res.rbIsMarG==='0.37',
          'RUNBOARD IS: MAR dashes when the run saved no measured slice':res.rbIsMarN===String.fromCharCode(0x2014)
        },res);
      })();

      // -- g6_gvexplore (repair round): EXPLORE's run-row stage builder (_reRunStages) bailed
      //    out entirely for a Gate-Validate JOB TYPE run (it saves no `validate` block at
      //    all), so its IN-SAMPLE tick and the default all-three-stretches tick both fell
      //    through to the whole-row date_from/date_to window for MAR / R per YR / ROC % per
      //    YR - reproduced MAR 0.03 on BOTH ticks (the all-three tick silently summed the
      //    in-sample money alone over the whole-run span, the in-sample tick divided the
      //    correct in-sample money by the wrong whole-run drawdown and years). --
      (function(){
        var calls=[],res={};
        var G=dfxClone(FIX);G.id=String(+FIX.id+994003);G.strategy='ZGVEXPA_1_0.py';G.starred=false;
        delete G.validate;delete G.top10_results;G.scope='Gate-Validate';
        var N=dfxClone(G);N.id=String(+FIX.id+994004);N.strategy='ZGVEXPB_1_0.py';
        delete N.gate_validate.ungated_is;
        var W=dfxWin([G,N]);
        function numTxt(t){return t!=null&&/^-?[0-9]/.test(t);}
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['is'],resCols:'all',c2Tbl:true,resAxis:'ratio',resXAxis:'dd'},W));
        var isRowG=r4Row('runs:'+G.id)||{},isRowN=r4Row('runs:'+N.id)||{};
        res.isMarG=isRowG['MAR']?isRowG['MAR'].t:null;
        res.isRpyG=isRowG['R / YR']?isRowG['R / YR'].t:null;
        res.isRocG=isRowG['ROC % / YR']?isRowG['ROC % / YR'].t:null;
        res.isMarN=isRowN['MAR']?isRowN['MAR'].t:null;
        res.isMarNTip=isRowN['MAR']?isRowN['MAR'].tip:null;
        calls.push(doRender({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['is','wf','lb'],resCols:'all',c2Tbl:true,resAxis:'ratio',resXAxis:'dd'},W));
        var allRowG=r4Row('runs:'+G.id)||{};
        res.allMarG=allRowG['MAR']?allRowG['MAR'].t:null;
        res.allRpyG=allRowG['R / YR']?allRowG['R / YR'].t:null;
        res.allRocG=allRowG['ROC % / YR']?allRowG['ROC % / YR'].t:null;
        dfxCase('g6_gvexplore',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'IN-SAMPLE tick: MAR reads the measured slice over its own in-sample years, not the whole run':res.isMarG==='0.37',
          'IN-SAMPLE tick: R / YR matches the same measured slice and years':res.isRpyG==='19.6R',
          'IN-SAMPLE tick: ROC % / YR matches':res.isRocG==='1.9%',
          'IN-SAMPLE tick: MAR dashes with a real reason (never the whole run) when the run saved no measured slice':!numTxt(res.isMarN)&&!!res.isMarNTip,
          'ALL-THREE-STRETCHES tick (the default view): MAR is the real whole-run figure, not the old 0.03':res.allMarG==='0.78',
          'ALL-THREE-STRETCHES tick: R / YR matches':res.allRpyG==='53.2R',
          'ALL-THREE-STRETCHES tick: ROC % / YR matches':res.allRocG==='17.0%'
        },res);
      })();

      // ═══════════════════════════════════════════════════════════════════════════
      // WALK-FORWARD RANKING ROUND (2026-09-20, RESEARCH.md item 8): default stage
      // moves to WALK-FORWARD, a thin walk-forward test (under 30 trades) sinks below
      // one that cleared the floor but stays above a zero-trade test, a gap chip reads
      // the crowning score against the walk-forward test, and the lockbox stage carries
      // a veto note instead of ranking. Cases h1-h14.
      // ═══════════════════════════════════════════════════════════════════════════

      // -- h1: LEADERBOARD, no STAGE saved -> WALK-FORWARD is the lit default (item 1) --
      (function(){
        var calls=[],res={};
        calls.push(doRender({c2Screen:'lead'}, FIX_WIN));
        function lit(k){var e=d.querySelector('[data-c2stage="'+k+'"]');return !!(e&&e.className==='on');}
        res.wfOn=lit('wf');res.lbOn=lit('lb');
        dfxCase('h1_defaultstage_lead',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'no saved STAGE: WALK-FORWARD is lit on the LEADERBOARD':res.wfOn,
          'LOCKBOX is not lit':!res.lbOn
        },res);
      })();

      // -- h2: an explicitly saved LOCKBOX stage still wins - only the default changed --
      (function(){
        var calls=[],res={};
        calls.push(doRender({c2Screen:'lead',c2Stage:'lb'}, FIX_WIN));
        function lit(k){var e=d.querySelector('[data-c2stage="'+k+'"]');return !!(e&&e.className==='on');}
        res.wfOn=lit('wf');res.lbOn=lit('lb');
        dfxCase('h2_defaultstage_persists',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'an explicitly saved LOCKBOX stage still wins':res.lbOn,
          'WALK-FORWARD is not lit once LOCKBOX was explicitly saved':!res.wfOn
        },res);
      })();

      // -- h3: CHAMPIONS, no STAGE saved -> WALK-FORWARD is the lit default (item 1) --
      (function(){
        var calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'champ'}, FIX_WIN));
        function lit(k){var e=d.querySelector('[data-c2stage="'+k+'"]');return !!(e&&e.className==='on');}
        res.wfOn=lit('wf');res.lbOn=lit('lb');
        dfxCase('h3_defaultstage_champions',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'no saved STAGE: WALK-FORWARD is lit on CHAMPIONS':res.wfOn,
          'LOCKBOX is not lit':!res.lbOn
        },res);
      })();

      // shared fixture builder for h5-h9: one walk-forward fold, a controlled trade
      // count and net so the thin-test floor (under 30 trades) can be aimed exactly.
      function hWfFold(id,name,tr,net,pf){
        var x=dfxClone(FIX);x.id=String(id);x.strategy=name;x.starred=false;
        x.top10_results=[{fold:1,oos_trades:tr,oos_pnl:net,oos_wins:Math.round(tr*0.55),oos_pf:pf,total_pnl:net}];
        x.multiplier=1;
        delete x.validate.wf_oos;
        return x;
      }
      // a proper zero-trade walk-forward TEST (not just an empty fold list) needs its own
      // consistent validate.wf_oos block, matching the g5-sink fixture shape exactly, so
      // the engine-level zero-trade check (not just an absent test) is what is compared.
      function hWfZero(id,name){
        var x=dfxClone(FIX);x.id=String(id);x.strategy=name;x.starred=false;
        x.top10_results=[{fold:1,oos_trades:0,oos_pnl:0,oos_wins:0,oos_pf:0,total_pnl:0}];
        x.multiplier=1;
        x.validate.wf_oos={v:1,trades:0,net:0,wins:0,profit_factor:null,gross_loss:0,n_folds:1,
          from:'2016-05-02',to:'2025-02-11',years:8.8,max_drawdown:0,sharpe:null,sortino:null,equity:[],
          folds:[{f:1,from:'2016-05-02',to:'2025-02-11',trades:0,net:0}],fold_idx:[]};
        return x;
      }

      // -- h5: LEADERBOARD, rank NET, WF stage - a thin test (15 trades) must sink below a
      //    run that cleared the 30-trade floor, even though the thin run's raw net is far
      //    larger. Reuses the g5 zero-trade sink pattern (item 8, RESEARCH.md).
      (function(){
        var THIN=hWfFold(960001,'ZTHIN_1_0.py',15,87000,3.0);
        var CLEAR=hWfFold(960002,'ZCLEAR_1_0.py',40,9000,1.4);
        var W=dfxWin([THIN,CLEAR]),calls=[],res={};
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'wf'},W));
        var famRows=d.querySelectorAll('.c2-row[data-c2fam]');
        res.order=[].map.call(famRows,function(e){return decodeURIComponent(e.getAttribute('data-c2fam'));});
        var thinIdx=res.order.indexOf('ZTHIN_1_0'),clearIdx=res.order.indexOf('ZCLEAR_1_0');
        res.thinIdx=thinIdx;res.clearIdx=clearIdx;
        res.thinBodyHasBigNet=(d.body.innerText||'').indexOf('$87,000')>=0;
        dfxCase('h5_thin_sinks_below_cleared',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'both families are on the board':thinIdx>=0&&clearIdx>=0,
          'the run that cleared 30 trades ranks ahead of the 15-trade thin test on NET':clearIdx<thinIdx,
          'the thin run still prints its real (larger) net rather than a dash':res.thinBodyHasBigNet
        },res);
      })();

      // -- h6: a zero-trade walk-forward test must rank below a thin (but traded) one --
      (function(){
        var THIN=hWfFold(960003,'ZTHINB_1_0.py',15,-500,0.8);
        var ZERO=hWfZero(960004,'ZZEROWFB_1_0.py');
        var W=dfxWin([THIN,ZERO]),calls=[],res={};
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'wf'},W));
        var famRows=d.querySelectorAll('.c2-row[data-c2fam]');
        res.order=[].map.call(famRows,function(e){return decodeURIComponent(e.getAttribute('data-c2fam'));});
        var thinIdx=res.order.indexOf('ZTHINB_1_0'),zeroIdx=res.order.indexOf('ZZEROWFB_1_0');
        res.thinIdx=thinIdx;res.zeroIdx=zeroIdx;
        dfxCase('h6_zero_sinks_below_thin',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'both families are on the board':thinIdx>=0&&zeroIdx>=0,
          'the thin (traded, net -$500) run ranks ahead of the zero-trade ($0) run on NET':thinIdx<zeroIdx
        },res);
      })();

      // -- h7: the thin run's expanded row still shows its real figures, with a small mark
      //    and a hover saying the test is too thin to rank on --
      (function(){
        var THIN=hWfFold(960005,'ZTHINC_1_0.py',12,4400,2.1);
        var W=dfxWin([THIN]),calls=[],res={};
        var wc=W+"window._c2Open=new Set(['ZTHINC_1_0']);";
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'wf'},wc));
        res.bodyText=d.body.innerText||'';
        res.hasRealNet=res.bodyText.indexOf('$4,400')>=0;
        res.hasThinWord=res.bodyText.toLowerCase().indexOf('thin test')>=0;
        var markEl=[].filter.call(d.querySelectorAll('[title]'),function(e){
          return /took only 12 trade/i.test(e.getAttribute('title')||'');})[0];
        res.markTitle=markEl?markEl.getAttribute('title'):null;
        dfxCase('h7_thin_shows_figures_and_mark',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the thin run still prints its real net, not a dash':res.hasRealNet,
          'a "thin test" mark is shown':res.hasThinWord,
          'the mark hover names the exact trade count and the 30-trade floor':!!res.markTitle&&res.markTitle.indexOf('30')>=0
        },res);
      })();

      // -- h8: the comparison table (PICK RUNS/CHAMPIONS) never gives a thin test the best
      //    mark, even when its raw NET is the larger of the two picked runs --
      (function(){
        var THIN=hWfFold(960006,'ZTHIND_1_0.py',10,120000,4.0);
        var CLEAR=hWfFold(960007,'ZCLEARD_1_0.py',35,6000,1.3);
        var W=dfxWin([THIN,CLEAR]),calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',cmpIds:[THIN.id,CLEAR.id],c2Stage:'wf'},W));
        var bestSpans=[].map.call(d.querySelectorAll('span[title="best of the picked runs on this row"]'),
          function(s){return (s.textContent||'').trim();});
        res.bestSpans=bestSpans;
        res.thinNeverBest=bestSpans.indexOf('$120,000')<0;
        res.clearIsBestSomewhere=bestSpans.indexOf('$6,000')>=0;
        dfxCase('h8_thin_never_bestmark',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the thin run (bigger raw NET) never takes the best mark':res.thinNeverBest,
          'the run that cleared the floor takes a best mark somewhere':res.clearIsBestSomewhere
        },res);
      })();

      // -- h9: the thin-test floor is a WALK-FORWARD-only rule - the same run on the
      //    LOCKBOX stage carries no thin mark and is not sunk --
      (function(){
        var THIN=hWfFold(960008,'ZTHINE_1_0.py',10,500,1.2);
        THIN.validate.lockbox=Object.assign({},THIN.validate.lockbox,{trades:200,pnl:5000,pf:1.3,win_rate:35,pass:true});
        var W=dfxWin([THIN]),calls=[],res={};
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'lb'},W));
        res.bodyText=d.body.innerText||'';
        res.hasThinWordOnLb=res.bodyText.toLowerCase().indexOf('thin test')>=0;
        res.hasLbNet=res.bodyText.indexOf('$5,000')>=0;
        dfxCase('h9_thin_floor_only_on_wf',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'on LOCKBOX the same run carries no thin-test mark':!res.hasThinWordOnLb,
          'its LOCKBOX net prints normally':res.hasLbNet
        },res);
      })();

      // shared fixture builder for h10-h12 (gap chip): a run with BOTH the crowning score
      // (gate_validate.ungated_wf) and the walk-forward test (validate.wf_oos), pooled
      // trades/net kept consistent with FIX's own 8 folds so the engine's own consistency
      // check accepts the test.
      function hGapRun(id,name,fixedPf,retunedPf,dropWfOos,dropCrown){
        var x=dfxClone(FIX);x.id=String(id);x.strategy=name;x.starred=false;
        if(dropCrown){delete x.gate_validate;delete x.ml_gate;}
        else{x.gate_validate.ungated_wf=Object.assign({},x.gate_validate.ungated_wf,{profit_factor:fixedPf,num_trades:1895,total_pnl:12169.71});}
        var folds=x.top10_results.filter(function(f){return f&&f.fold!=null;});
        var sT=folds.reduce(function(a,f){return a+(+f.oos_trades||0);},0);
        var sN=folds.reduce(function(a,f){return a+(+f.oos_pnl||0);},0);
        if(!dropWfOos){
          x.validate.wf_oos={v:1,trades:sT,net:sN,wins:300,profit_factor:retunedPf,gross_loss:1,n_folds:folds.length,
            from:'2016-05-02',to:'2025-02-11',years:8.8,max_drawdown:-500,sharpe:1.1,sortino:1.5,
            equity:folds.map(function(_,i){return (i+1)*100;}),
            folds:folds.map(function(f){return {f:f.fold,from:'2016-05-02',to:'2025-02-11',trades:f.oos_trades,net:f.oos_pnl};}),
            fold_idx:folds.map(function(_,i){return i;})};
        }else{delete x.validate.wf_oos;}
        return x;
      }

      // -- h10: the gap chip reads (fixed - retuned) / fixed as a percentage of the
      //    crowning score, on the leaderboard's expanded run row --
      (function(){
        var G=hGapRun(960020,'ZGAP_1_0.py',1.50,1.20,false,false);
        var W=dfxWin([G]),calls=[],res={};
        var wc=W+"window._c2Open=new Set(['ZGAP_1_0']);";
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'wf'},wc));
        var chip=[].filter.call(d.querySelectorAll('.c2-pill'),function(e){return /^gap /i.test((e.textContent||'').trim());})[0];
        res.chipText=chip?(chip.textContent||'').trim():null;
        res.chipTitle=chip?chip.getAttribute('title'):null;
        dfxCase('h10_gapchip_percent',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'a gap chip is shown':!!chip,
          'the chip reads gap 20% ((1.50-1.20)/1.50)':res.chipText==='gap 20%',
          'the hover names the crowning score as 20% above the walk-forward test':!!res.chipTitle&&res.chipTitle.indexOf('20%')>=0&&res.chipTitle.indexOf('above')>=0&&res.chipTitle.indexOf('walk-forward test')>=0
        },res);
      })();

      // -- h11: a pinned run (fixed PF === re-tuned PF) shows 'same reading', never 'gap 0%' --
      (function(){
        var G=hGapRun(960021,'ZGAPPIN_1_0.py',1.35,1.35,false,false);
        var W=dfxWin([G]),calls=[],res={};
        var wc=W+"window._c2Open=new Set(['ZGAPPIN_1_0']);";
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'wf'},wc));
        var pills=[].map.call(d.querySelectorAll('.c2-pill'),function(e){return (e.textContent||'').trim();});
        res.pills=pills;
        res.hasSame=pills.indexOf('same reading')>=0;
        res.hasZeroPct=pills.indexOf('gap 0%')>=0;
        dfxCase('h11_gapchip_pinned_equal',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'the chip says same reading, not a number':res.hasSame,
          'it never shows gap 0%':!res.hasZeroPct
        },res);
      })();

      // -- h12: only one of the two readings saved -> no gap chip at all --
      (function(){
        var G=hGapRun(960022,'ZGAPMISS_1_0.py',1.50,1.20,true,false);
        var W=dfxWin([G]),calls=[],res={};
        var wc=W+"window._c2Open=new Set(['ZGAPMISS_1_0']);";
        calls.push(doRender({c2Screen:'lead',c2Rank:'net',c2Stage:'wf'},wc));
        var pills=[].map.call(d.querySelectorAll('.c2-pill'),function(e){return (e.textContent||'').trim();});
        res.pills=pills;
        res.hasGapWord=pills.some(function(t){return /^gap /i.test(t)||t==='same reading';});
        dfxCase('h12_gapchip_missing_reading',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'no gap chip shows when the walk-forward test was not saved':!res.hasGapWord
        },res);
      })();

      // -- h13: LOCKBOX is framed as a veto, not a ranking, on the LEADERBOARD and on
      //    PICK RUNS/CHAMPIONS - present on the LOCKBOX stage, absent elsewhere --
      (function(){
        var calls=[],res={};
        calls.push(doRender({c2Screen:'lead',c2Stage:'lb'}, FIX_WIN));
        var noteLb=d.querySelector('.c2-note');
        res.leadLbNote=noteLb?(noteLb.textContent||''):'';
        calls.push(doRender({c2Screen:'lead',c2Stage:'wf'}, FIX_WIN));
        var noteWf=d.querySelector('.c2-note');
        res.leadWfNote=noteWf?(noteWf.textContent||''):'';
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',cmpIds:[String(FIX.id)],c2Stage:'lb'}, FIX_WIN));
        var notePick=d.querySelector('.c2-note');
        res.pickLbNote=notePick?(notePick.textContent||''):'';
        function saysVeto(t){return t.indexOf('one look')>=0&&t.indexOf('11%')>=0&&t.indexOf('half the time')>=0;}
        dfxCase('h13_lockbox_veto_note',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'LEADERBOARD, LOCKBOX stage: the veto note is there':saysVeto(res.leadLbNote),
          'LEADERBOARD, WALK-FORWARD stage: no veto note':!saysVeto(res.leadWfNote),
          'PICK RUNS, LOCKBOX stage: the veto note is there too':saysVeto(res.pickLbNote)
        },res);
      })();

      // -- h14: the RUNBOARD carries the same veto wording in its info hover on LOCKBOX --
      (function(){
        var calls=[],res={};
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'lb'}, FIX_WIN));
        var pops=[].map.call(d.querySelectorAll('[data-infopop]'),function(e){
          try{return decodeURIComponent(e.getAttribute('data-infopop'));}catch(_){return '';}});
        res.lbPop=pops.filter(function(t){return t.indexOf('one look')>=0;})[0]||'';
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'wf'}, FIX_WIN));
        var popsWf=[].map.call(d.querySelectorAll('[data-infopop]'),function(e){
          try{return decodeURIComponent(e.getAttribute('data-infopop'));}catch(_){return '';}});
        res.wfHasVeto=popsWf.some(function(t){return t.indexOf('one look')>=0&&t.indexOf('pass-or-fail')>=0;});
        dfxCase('h14_lockbox_veto_runboard',calls,{
          'renders OK':calls.every(function(c){return c==='OK';}),
          'RUNBOARD info hover on LOCKBOX names the veto (one look, 11%, half the time)':res.lbPop.indexOf('11%')>=0&&res.lbPop.indexOf('half the time')>=0,
          'the same hover on WALK-FORWARD does not carry the veto wording':!res.wfHasVeto
        },res);
      })();

      // -- i1 (F25, audit3_report.md, 2026-09-24): RUNBOARD grid, WINDOW row on IS and LB now
      //    reads THIS STAGE'S OWN stretch (dates + years, the same _rbYrs the MAR / TRADES-per-
      //    YR rows beside it divide by), instead of the whole run's span next to figures measured
      //    over a fraction of it. Three run shapes, rendered through the board hosted in COMPARE
      //    (the one the owner uses): a plain run (IS = 75% of the tuning window from its own
      //    start, LB = the saved lockbox dates), a BOOK (IS = book start to its own lockbox door,
      //    LB = that door to book end - exact dates, no reconstruction), and a LEGACY run with no
      //    windows/lockbox saved at all (LB dashes honestly with a reason instead of showing the
      //    whole run under the LB caption). FULL and WF are unchanged, checked here to prove it.
      //    Every figure below is hand-computed from the seeded dates (_yrsBetween's own linear
      //    ms/365.25-day formula: 2010-06-07..2020-06-07 is 10.0y, x0.75 IS-split = 7.5y,
      //    reconstructed via the SAME t0+y*365.25*864e5 arithmetic _rbStageRange itself uses ->
      //    2017-12-06; 2025-06-30..2026-06-30 = 1.0y exactly, no reconstruction on LB;
      //    2010-06-07..2024-06-07 = 14.0y and 2024-06-07..2026-06-30 = 2.1y for the book, both
      //    exact, no reconstruction at all) and was checked against a real render before being
      //    written here, so a wrong number fails, not just a missing row.
      (function(){
        var RID=String(+FIX.id+620101), BID=String(+FIX.id+620102), LID=String(+FIX.id+620103);
        var R=JSON.parse(JSON.stringify(FIX));
        R.id=RID;R.strategy='ZF25WIN_1_0.py';R.starred=false;R.multiplier=1;
        R.date_from='2010-06-07';R.date_to='2026-06-30';
        R.best_pnl_usd=50000;R.best_dd_usd=5000;R.best_pf=1.2;R.best_trades=300;
        R.validate={verdict:'PASS',total_dd:-5000,total_win_rate:45,total_avg_win:600,total_avg_loss:-400,
          lockbox:{pnl:8000,pf:1.2,trades:40,pass:true},
          windows:{optimize:['2010-06-07','2020-06-07'],lockbox:['2025-06-30','2026-06-30']}};
        var BK=JSON.parse(JSON.stringify(FIX));
        BK.id=BID;BK.strategy='BOOK: F25 PROBE';BK.starred=false;BK.multiplier=1;
        BK.date_from='2010-06-07';BK.date_to='2026-06-30';
        BK.book={name:'F25 PROBE',legs:[{strategy:'AAA_1_0.py',weight:1},{strategy:'BBB_1_0.py',weight:1}],
          whole:{total_pnl:40000,max_drawdown:6000,num_trades:400,profit_factor:1.3},
          pre_lockbox:{total_pnl:30000,max_drawdown:6000,num_trades:300},
          lockbox:{total_pnl:10000,num_trades:100,win_rate:44,profit_factor:1.25,max_drawdown:4000},
          lockbox_from:'2024-06-07',date_from:'2010-06-07',date_to:'2026-06-30'};
        BK.validate={verdict:'PASS',lockbox:{pnl:10000,pf:1.25,trades:100,pass:true},book:true};
        var L=JSON.parse(JSON.stringify(FIX));
        L.id=LID;L.strategy='ZF25LEGACY_1_0.py';L.starred=false;L.multiplier=1;
        L.date_from='2010-06-07';L.date_to='2026-06-30';
        L.best_pnl_usd=20000;L.best_dd_usd=4000;L.best_pf=1.1;L.best_trades=150;
        L.validate={verdict:'PASS',total_dd:-4000};   // no windows, no lockbox saved at all
        var wc="var R="+JSON.stringify(R)+";var B="+JSON.stringify(BK)+";var L="+JSON.stringify(L)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(R),f(B),f(L)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
        function rowsOf(){var o={};
          [].forEach.call(d.querySelectorAll('#rb-mtx-box table tr'),function(tr){
            var c=tr.children;if(c.length<2)return;
            var lab=(c[0].textContent||'').trim();if(!lab)return;
            o[lab]=[].slice.call(c,1).map(function(td){return (td.textContent||'').trim();});});
          return o;}
        function titleFor(lab,substr){var found=null;
          [].forEach.call(d.querySelectorAll('#rb-mtx-box table tr'),function(tr){
            var c=tr.children;if(c.length<2)return;
            if((c[0].textContent||'').trim()!==lab)return;
            [].forEach.call(c,function(td){if(found)return;
              var t=(td.textContent||'').trim();if(t.indexOf(substr)<0)return;
              var h=td.querySelector('[title]');found=h?h.getAttribute('title'):(td.getAttribute('title')||'');});});
          return found;}
        var calls=[],per={},titles={};
        ['is','lb','full','wf'].forEach(function(smp){
          calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Src:'pick',c2Stage:smp,cmpIds:[RID,BID,LID]}, wc));
          per[smp]=rowsOf();
          // read the dash's own hover WHILE this stage's render is still on screen - titleFor
          //   reads the live DOM, so it must run inside this loop, not after it has moved on.
          titles[smp]=titleFor('WINDOW','—');
        });
        var isTxt=(per.is['WINDOW']||[]).join(' | '), lbTxt=(per.lb['WINDOW']||[]).join(' | '),
            fullTxt=(per.full['RUN WINDOW']||[]).join(' | ');
        var lbDashCount=(per.lb['WINDOW']||[]).filter(function(t){return t==='—';}).length;
        var legacyLbTitle=titles.lb;
        dfxCase('i1_f25_window_stage', calls, {
          'renders OK on IS / LB / FULL / WF': calls.every(function(c){return c==='OK';}),
          'IS and LB use the label WINDOW (not RUN WINDOW)': !!per.is['WINDOW']&&!!per.lb['WINDOW'],
          'WF also uses the label WINDOW': !!per.wf['WINDOW'],
          'FULL keeps the label RUN WINDOW, not WINDOW': !!per.full['RUN WINDOW']&&!per.full['WINDOW'],
          'plain run, IS: starts at the tuning-window date (2010-06-07)': isTxt.indexOf('2010-06-07')>=0,
          'plain run, IS: ends at 2017-12-06 - 75% of the 2010-2020 tuning window, not the lockbox door or run end': isTxt.indexOf('2017-12-06')>=0,
          'plain run, IS: reads 7.5y, never the whole run 16.1y': isTxt.indexOf('7.5y')>=0,
          'plain run, LB: reads the saved lockbox dates 2025-06-30 to 2026-06-30, 1.0y': lbTxt.indexOf('2025-06-30')>=0&&lbTxt.indexOf('2026-06-30')>=0&&lbTxt.indexOf('1.0y')>=0,
          'book, IS: run start to its own lockbox door (2010-06-07 to 2024-06-07), 14.0y - exact': isTxt.indexOf('2024-06-07')>=0&&isTxt.indexOf('14.0y')>=0,
          'book, LB: lockbox door to run end (2024-06-07 to 2026-06-30), 2.1y': lbTxt.indexOf('2024-06-07')>=0&&lbTxt.indexOf('2026-06-30')>=0&&lbTxt.indexOf('2.1y')>=0,
          'legacy run with no saved windows: exactly one dash on LB, not the other two': lbDashCount===1,
          'that dash carries a plain-language reason on hover naming the lockbox': !!legacyLbTitle&&/lockbox window/i.test(legacyLbTitle),
          'FULL is unaffected: every run still reads its whole-run 16.1y': fullTxt.split(' | ').filter(function(t){return t.indexOf('16.1y')>=0;}).length===3
        }, {is:per.is['WINDOW'],lb:per.lb['WINDOW'],full:per.full['RUN WINDOW'],wf:per.wf['WINDOW'],legacyLbTitle:legacyLbTitle});
      })();

      // -- i2 (F30, audit3_report.md, 2026-09-24): book names read like strategy file names on
      //    OVERLAY's own no-curve label builder (never checked r.book), the RUNBOARD matrix
      //    header doubled a run's id when it carries no famKey/famSeq (the audit's own live
      //    "#19 #19"), and ETFDIP read two different abbreviations depending on which screen was
      //    reading it ("ETFDI", un-curated stratInfo fallback, vs "ETFDIP", the family-key table).
      (function(){
        var BID2=String(+FIX.id+630001), EID=String(+FIX.id+630002), PID=String(+FIX.id+630003);
        var BK2=JSON.parse(JSON.stringify(FIX));
        BK2.id=BID2;BK2.strategy='BOOK: FOUR-LEG: ORB 234 + ENGU-Q 335 + TTM SS x3 + NOISE 304';BK2.starred=false;BK2.multiplier=1;
        delete BK2.equity;
        BK2.book={name:'FOUR-LEG',legs:[{strategy:'ORB_234.py',weight:1},{strategy:'ENGUQ_335.py',weight:1}],
          whole:{total_pnl:500000,max_drawdown:40000,num_trades:4000,profit_factor:1.3},
          pre_lockbox:{total_pnl:400000,max_drawdown:40000,num_trades:3600},
          lockbox:{total_pnl:100000,num_trades:400,win_rate:44,profit_factor:1.3,max_drawdown:20000},
          lockbox_from:'2025-02-11',date_from:'2010-06-07',date_to:'2026-06-30'};
        BK2.validate={verdict:'PASS',lockbox:{pnl:100000,pf:1.3,trades:400,pass:true},book:true};
        var ET=JSON.parse(JSON.stringify(FIX));
        ET.id=EID;ET.strategy='ETFDIP_2_0.py';ET.starred=false;ET.multiplier=1;
        delete ET.famKey;delete ET.famSeq;
        var PL=JSON.parse(JSON.stringify(FIX));
        PL.id=PID;PL.strategy='ZOLDRUN_1_0.py';PL.starred=true;PL.multiplier=1;
        delete PL.famKey;delete PL.famSeq;
        var wc2="var B="+JSON.stringify(BK2)+";var E="+JSON.stringify(ET)+";var P="+JSON.stringify(PL)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(B),f(E),f(P)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();window._starRuns=[];";
        var calls=[];
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'lb',cmpIds:[BID2]}, wc2));
        var noCurve=JSON.parse(w.eval("JSON.stringify((window._cmpEqxNoCurve||[]).map(function(s){return {id:String(s.id),label:s.label};}))"));
        var bookLabel=(noCurve.filter(function(s){return s.id===BID2;})[0]||{}).label||'';
        calls.push(doRender({c2Screen:'cmp',c2View:'board',c2Stage:'full',cmpIds:[PID,EID]}, wc2));
        var headers=[].map.call(d.querySelectorAll('#rb-mtx-box table th'),function(th){return th.innerHTML;});
        var plainHeader=headers.filter(function(h){return h.indexOf('#'+PID)>=0;})[0]||'';
        var idOccurrences=(plainHeader.match(new RegExp('#'+PID,'g'))||[]).length;
        var rbFamText=[].map.call(d.querySelectorAll('[data-rbfam]'),function(e){return (e.textContent||'').trim();});
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'champ',c2Stage:'lb'}, wc2));
        var ovlAll=JSON.parse(w.eval("JSON.stringify((window._cmpEqxSeries||[]).concat(window._cmpEqxNoCurve||[]).map(function(s){return {id:String(s.id),label:s.label};}))"));
        var etfOverlayLabel=(ovlAll.filter(function(s){return s.id===EID;})[0]||{}).label||'';
        dfxCase('i2_f30_book_and_naming', calls, {
          'renders OK': calls.every(function(c){return c==='OK';}),
          'a curve-less book on OVERLAY reads as a book, its full name verbatim': bookLabel.indexOf('BOOK: FOUR-LEG: ORB 234 + ENGU-Q 335 + TTM SS x3 + NOISE 304')>=0,
          'RUNBOARD matrix header: a run with no famKey/famSeq shows its id once, not twice': idOccurrences===1,
          'RUNBOARD family chip reads the family in full (DIP since the v73.893 vocabulary)': rbFamText.indexOf('DIP')>=0,
          'OVERLAY run label also reads the family in full (DIP), not truncated': /(^|[^A-Z])DIP [0-9]/.test(etfOverlayLabel)
        }, {bookLabel:bookLabel,plainHeader:plainHeader,idOccurrences:idOccurrences,rbFamText:rbFamText,etfOverlayLabel:etfOverlayLabel});
      })();

      // -- i3 (F30, audit3_report.md, 2026-09-24): a rank number (R1..Rn) belongs only on a
      //    genuinely ranked list (CHAMPIONS or RUNBOARD); a hand-picked list used to print R1..Rn
      //    in pick order as if it were one, on both the newer c2Screen 'cmp' code (OVERLAY / PICK
      //    RUNS) and the older shared _cmpMode code the old tab and the hosted RUNBOARD reuse.
      (function(){
        var AID3=String(+FIX.id+630011), BID3=String(+FIX.id+630012);
        var A3=JSON.parse(JSON.stringify(FIX));A3.id=AID3;A3.strategy='ZRANKA_1_0.py';A3.starred=false;
        var B3=JSON.parse(JSON.stringify(FIX));B3.id=BID3;B3.strategy='ZRANKB_1_0.py';B3.starred=false;
        var wc3="var A="+JSON.stringify(A3)+";var B="+JSON.stringify(B3)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(A),f(B)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();window._starRuns=[];";
        var calls=[];
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'lb',cmpIds:[AID3,BID3]}, wc3));
        var ovlPickedFwd=w.eval("(window._cmpEqxSeries||[]).some(function(s){return s.rank!=null;})");
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'pick',c2Stage:'lb',cmpIds:[BID3,AID3]}, wc3));
        var ovlPickedRev=w.eval("(window._cmpEqxSeries||[]).some(function(s){return s.rank!=null;})");
        calls.push(doRender({c2Screen:'cmp',c2View:'ovl',c2Src:'champ',c2Stage:'lb'}, wc3));
        var ovlChampHasRank=w.eval("(window._cmpEqxSeries||[]).length>0&&(window._cmpEqxSeries||[]).every(function(s){return s.rank!=null;})");
        calls.push(doRender({c2Screen:'cmp',c2View:'runs',c2Src:'pick',c2Stage:'lb',cmpIds:[AID3,BID3]}, wc3));
        var runsPickedNoRank=w.eval("(window._cmpEqxSeries||[]).length>0&&(window._cmpEqxSeries||[]).every(function(s){return s.rank==null;})");
        calls.push(doRender({cmpMode:'fam'}, wc3, 'cmp'));
        var oldFamHasRank=w.eval("(window._cmpEqxSeries||[]).length>0&&(window._cmpEqxSeries||[]).every(function(s){return s.rank!=null;})");
        dfxCase('i3_f30_rank_on_picked', calls, {
          'renders OK': calls.every(function(c){return c==='OK';}),
          'OVERLAY PICKED: no run carries a rank number': !ovlPickedFwd,
          'OVERLAY PICKED, reversed pick order: still no rank number': !ovlPickedRev,
          'OVERLAY CHAMPIONS: every drawn run carries a rank number': ovlChampHasRank,
          'PICK RUNS (hosted), PICKED: no run carries a rank number': runsPickedNoRank,
          'the old tab, BY STRATEGY (its own CHAMPIONS mode): every drawn run carries a rank number': oldFamHasRank
        }, {});
      })();

      // -- i4 (F31, audit3_report.md, 2026-09-24): RUNBOARD chart key on LB, a run whose lockbox
      //    took no trades. CONFIRMED ALREADY FIXED on current origin/main (no index.html change
      //    made for this item, per the task's own "verify with a probe case either way; fix only
      //    if still wrong" instruction) - the reason is genuinely "the lockbox took no trades",
      //    not the old false "no curve saved" (the curve IS saved; only the lockbox slice of it
      //    is empty). Locked in here as a regression guard - the audit's own note says the
      //    visible caption wording ("no walk-forward curve") is a separate, already being-fixed
      //    item this task does not touch, so only the underlying reason is asserted here.
      (function(){
        var EQi4=[];for(var _k=0;_k<343;_k++)EQi4.push(Math.round(_k*50));
        var ZID=String(+FIX.id+630021);
        var Z=JSON.parse(JSON.stringify(FIX));
        Z.id=ZID;Z.strategy='ZLBZERO_1_0.py';Z.starred=false;Z.multiplier=1;Z.equity=EQi4;
        Z.validate={verdict:'FAIL',equity:EQi4,lb_idx:341,total_dd:-3000,
          windows:{optimize:['2010-06-07','2024-06-07'],lockbox:['2025-06-30','2026-06-30']},
          lockbox:{pnl:0,pf:0,trades:0,pass:false}};
        var wc4="var Z="+JSON.stringify(Z)+";"
          +"var f=function(x){return (typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(x)):x;};"
          +"runHistory=[f(Z)];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();window._starRuns=[];";
        var call=doRender({c2Screen:'cmp',c2View:'board',c2Stage:'lb',cmpIds:[ZID]}, wc4);
        var noCurve4=JSON.parse(w.eval("JSON.stringify((window._cmpEqxNoCurve||[]).map(function(s){return {id:String(s.id),why:s.why};}))"));
        var zWhy=(noCurve4.filter(function(s){return s.id===ZID;})[0]||{}).why||'';
        dfxCase('i4_f31_lb_zero_reason', [call], {
          'renders OK': call==='OK',
          'a zero-trade lockbox is placed in the no-curve list with a reason, not silently': !!zWhy,
          'the reason names the true cause - the lockbox took no trades': /lockbox.*took no trades/i.test(zWhy),
          'the reason does not claim the curve was never saved (it is saved; only the lockbox slice is empty)': !/no curve saved/i.test(zWhy)&&/is saved/i.test(zWhy)
        }, {zWhy:zWhy});
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
          and r.get('hasNoRuns') and r.get('rankCount') == 4 and r.get('stageCount') == 4)
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
        if r.get('stageCount') != 4:
            fail('empty: expected 4 [data-c2stage] spans (IS, WF, LB, FULL), got %s' % r.get('stageCount'))

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
             # F40 (audit3_report.md): the hover figure was re-measured and corrected
             and 'three and a half' not in (r.get('tblBtnTitle') or '')
             and 'dozen megabytes' in (r.get('tblBtnTitle') or '')
             and r.get('menuHost') is True
             and (r.get('groups') or 0) >= 5
             and (r.get('menus') or 0) >= 3      # single-choice groups became menus
             and (r.get('hiddenBoxes') or 0) >= 3
             and r.get('menuDrives') is True     # and a menu really drives its buttons
             and (r.get('rowsOff') or 0) == 0   # and the tables are off by default
             and r.get('call2') == 'OK'
             and (r.get('rowsOn') or 0) >= 1    # switching them on builds them
             and (r.get('pointsOn') or 0) >= 1  # and the chart still draws either way
             and (r.get('splitCol') or 0) > 100      # the tables column has real width
             and (r.get('splitChart') or 0) > 100    # and so does the chart
             and r.get('splitLeftFirst') is True     # tables on the left, chart to their right
             and r.get('splitSameRow') is True
             and r.get('screenBtns') == 3
             and (r.get('presets') or 0) >= 4   # the board's own COMPARE FOR bar
             and r.get('sheets') == 3           # FILTERS / VIEWS / AXES
             and r.get('sidebar') == 0          # the old control sidebar is gone here
             and (r.get('stage') or 0) >= 1     # the profit stage stays in view
             and (r.get('help') or 0) >= 1      # HOW TO READ is reachable from this screen
             and not r.get('hold'))
    line('explore', ex_ok, 'call=%s points=%s rail=%s rows=%s screenBtns=%s presets=%s '
         'sheets=%s sidebar=%s stage=%s help=%s tblBtn=%s rowsOff=%s rowsOn=%s split=(t%s c%s L%s R%s) hold=%s'
         % (r.get('call'), r.get('points'), r.get('rail'), r.get('rows'),
            r.get('screenBtns'), r.get('presets'), r.get('sheets'), r.get('sidebar'),
            r.get('stage'), r.get('help'), r.get('tblBtn'), r.get('rowsOff'),
            r.get('rowsOn'), r.get('splitCol'), r.get('splitChart'),
            r.get('splitLeftFirst'), r.get('splitSameRow'), r.get('hold')))
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
        if r.get('menuHost') is not True or (r.get('groups') or 0) < 5:
            fail('explore: the controls sheet did not render its groups (host=%s groups=%s)'
                 % (r.get('menuHost'), r.get('groups')))
        if (r.get('menus') or 0) < 3 or (r.get('hiddenBoxes') or 0) < 3:
            fail('explore: the controls did not become menus (%s menus, %s button rows hidden)'
                 % (r.get('menus'), r.get('hiddenBoxes')))
        if r.get('menuDrives') is not True:
            fail('explore: choosing from a menu changed no setting - the menu is not driving '
                 'the button behind it')
        if r.get('tblBtn') != 1:
            fail('explore: the TABLES button is missing, so the study tables would be '
                 'unreachable on this screen')
        if 'three and a half' in (r.get('tblBtnTitle') or '') or 'dozen megabytes' not in (r.get('tblBtnTitle') or ''):
            fail('explore: F40 -- the TABLES hover still claims the old, re-measured-as-wrong '
                 'figure (title=%r)' % (r.get('tblBtnTitle') or ''))
        if (r.get('rowsOff') or 0) != 0:
            fail('explore: %s table rows built while the tables are off - the whole point is '
                 'that they are not assembled' % r.get('rowsOff'))
        if r.get('call2') != 'OK':
            fail('explore: turning the tables on threw -- %s' % str(r.get('call2'))[:300])
        if (r.get('rowsOn') or 0) < 1:
            fail('explore: turning the tables on produced no rows')
        if (r.get('pointsOn') or 0) < 1:
            fail('explore: the chart stopped drawing when the tables were turned on')
        if (r.get('splitCol') or 0) <= 100 or (r.get('splitChart') or 0) <= 100:
            fail('explore: the side-by-side split collapsed a column (tables %spx, chart %spx)'
                 % (r.get('splitCol'), r.get('splitChart')))
        if r.get('splitLeftFirst') is not True:
            fail('explore: the chart is to the LEFT of the tables - this board puts the tables '
                 'first')
        if r.get('splitSameRow') is not True:
            fail('explore: on SIDE the two are stacked, not beside each other')
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
              # F32 (audit3_report.md): the chart's dashed drawdown line is read off the
              # thinned, saved curve on EVERY stage, not only when a walk-forward test curve
              # is drawn - the disclosure sentence must say so on IS / LB / FULL as well,
              # not just WF, where it used to be the only stage that ever showed it.
              and all('thinned for storage on every' in ((per.get(k) or {}).get('note') or '')
                      for k in ('is', 'lb', 'full'))
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
        for _k in ('is', 'lb', 'full'):
            _note = (per.get(_k) or {}).get('note') or ''
            if 'thinned for storage on every' not in _note:
                fail('compare: F32 -- the %s stage note does not disclose that the chart '
                     'drawdown tag is read off a thinned curve on every stage, not only '
                     'walk-forward (note=%r)' % (_k, _note[-260:]))
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
                 and all((per.get(v) or {}).get('call') == 'OK' for v in ('board', 'runs', 'feat'))
                 and all(not (per.get(v) or {}).get('errors') and not (per.get(v) or {}).get('uncaught')
                         for v in ('board', 'runs', 'feat'))
                 and all(((per.get(v) or {}).get('len') or 0) > 2000 for v in ('board', 'runs', 'feat'))
                 and all((per.get(v) or {}).get('screenBtns') == 3 for v in ('board', 'runs', 'feat'))
                 and all((per.get(v) or {}).get('viewBtns') == 5 for v in ('board', 'runs', 'feat'))
                 and all(not (per.get(v) or {}).get('oldPills') for v in ('board', 'runs', 'feat')))
    line('hosted', hosted_ok, ' '.join('%s=(call=%s len=%s scr=%s view=%s pills=%s)'
         % (v, (per.get(v) or {}).get('call'), (per.get(v) or {}).get('len'),
            (per.get(v) or {}).get('screenBtns'), (per.get(v) or {}).get('viewBtns'),
            (per.get(v) or {}).get('oldPills')) for v in ('board', 'runs', 'feat')))
    if not hosted_ok:
        for v in ('board', 'runs', 'feat'):
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
            if p.get('screenBtns') != 3 or p.get('viewBtns') != 5:
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
                and lbb.get('note') and lbb.get('launcher')
                and (lbb.get('viewBtns') or 0) >= 5 and (lbb.get('booksBtn') or 0) >= 1
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
        if not lbb.get('launcher'):
            fail('books: the RUN A BOOK launcher is missing - it lives on this view now, and '
                 'nothing else points at where it used to be')
        if (lbb.get('viewBtns') or 0) < 5 or (lbb.get('booksBtn') or 0) < 1:
            fail('books: the view strip reads %s buttons with %s BOOKS pill - the strip is '
                 'incomplete or BOOKS is not on it'
                 % (lbb.get('viewBtns'), lbb.get('booksBtn')))
        if (wfb.get('ths') or 0) != 0 or (wfb.get('bodyRows') or 0) != 0:
            fail('books: the walk-forward stage still draws a table (th=%s rows=%s). A book '
                 'pools its legs over one window and tunes nothing, so every cell would be '
                 'blank or invented' % (wfb.get('ths'), wfb.get('bodyRows')))
        if not (wfb.get('noWf') and wfb.get('hold')):
            fail('books: the walk-forward stage does not explain why there is nothing to show')

    # TASK 1 (RUNBOARD backlog item D): TRADES / YR, WORST MONTH, LONGEST FLAT STRETCH.
    # Expected figures hand-computed from the seeded regime.monthly grids -- see the JS case
    # comment for the full derivation (review 2026-09-23: IS stretch + partial-grid run).
    r = cases.get('task1rb', {})
    per = r.get('per') or {}

    def _row(stage, label):
        return (((per.get(stage) or {}).get('row') or {}).get(label) or [])
    t1_ok = (r.get('call') == 'OK'
             and all((per.get(k) or {}).get('call') == 'OK' for k in ('full', 'is', 'lb', 'wf'))
             # the full-grid run
             and any(v == '-$5k Jul ’20' for v in _row('full', 'WORST MONTH'))
             and any(v == '10 mo' for v in _row('full', 'LONGEST FLAT STRETCH'))
             and any(v == '-$5k Jul ’20' for v in _row('is', 'WORST MONTH'))
             and any(v == '2 mo' for v in _row('is', 'LONGEST FLAT STRETCH'))
             and any(v == '$1k Mar ’21' for v in _row('lb', 'WORST MONTH'))
             and any(v == '0 mo' for v in _row('lb', 'LONGEST FLAT STRETCH'))
             # the grid that stops at March 2021: partial on FULL, a dash on LB
             and any(v == '~-$5k Jul ’20' for v in _row('full', 'WORST MONTH'))
             and any(v == '~9 mo' for v in _row('full', 'LONGEST FLAT STRETCH'))
             and _row('lb', 'WORST MONTH').count('—') == 2
             and _row('lb', 'LONGEST FLAT STRETCH').count('—') == 1
             # the book: its own stretch for each stage - whole run on FULL and (it ended
             #   before the lockbox) IS, its lockbox stretch on LB, nothing on WF
             and _row('full', 'WORST MONTH').count('—') == 1
             and any(('~2.0 mo' in v and 'DD span' in v) for v in _row('full', 'LONGEST FLAT STRETCH'))
             and any(('~2.0 mo' in v and 'DD span' in v) for v in _row('is', 'LONGEST FLAT STRETCH'))
             and any(('~0.7 mo' in v and 'DD span' in v) for v in _row('lb', 'LONGEST FLAT STRETCH'))
             and not any('~2.0 mo' in v for v in _row('lb', 'LONGEST FLAT STRETCH'))
             # walk-forward: no month can be read, for runs or the book
             and len(_row('wf', 'WORST MONTH')) == 3 and _row('wf', 'WORST MONTH').count('—') == 3
             and len(_row('wf', 'LONGEST FLAT STRETCH')) == 3 and _row('wf', 'LONGEST FLAT STRETCH').count('—') == 3
             and len(_row('full', 'TRADES / YR')) == 3 and not _row('full', 'AVG $ / TRADE'))
    line('task1rb', t1_ok, 'full worst=%s flat=%s | is worst=%s flat=%s | lb worst=%s flat=%s | wf worst=%s flat=%s | tradesPerYr=%s'
         % (_row('full', 'WORST MONTH'), _row('full', 'LONGEST FLAT STRETCH'),
            _row('is', 'WORST MONTH'), _row('is', 'LONGEST FLAT STRETCH'),
            _row('lb', 'WORST MONTH'), _row('lb', 'LONGEST FLAT STRETCH'),
            _row('wf', 'WORST MONTH'), _row('wf', 'LONGEST FLAT STRETCH'),
            _row('full', 'TRADES / YR')))
    if not t1_ok:
        for k in ('full', 'is', 'lb', 'wf'):
            p = per.get(k) or {}
            if p.get('call') != 'OK':
                fail('task1rb: %s stage threw -- %s' % (k, str(p.get('call'))[:300]))
            if p.get('errors'):
                fail('task1rb: %s console.error -- %s' % (k, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('task1rb: %s uncaught -- %s' % (k, p['uncaught'][0][:200]))
        if not (_row('full', 'TRADES / YR')
                and _row('full', 'WORST MONTH') and _row('full', 'LONGEST FLAT STRETCH')):
            fail('task1rb: one or more of the three new rows never rendered at all')
        else:
            fail('task1rb: a new row read a figure that does not match the hand-computed grid '
                 '(see the JS case comment for the derivation) -- '
                 'full=%s/%s is=%s/%s lb=%s/%s' % (_row('full', 'WORST MONTH'), _row('full', 'LONGEST FLAT STRETCH'),
                                                    _row('is', 'WORST MONTH'), _row('is', 'LONGEST FLAT STRETCH'),
                                                    _row('lb', 'WORST MONTH'), _row('lb', 'LONGEST FLAT STRETCH')))

    # F41 (audit3_report.md): a malformed saved cmpIds / cmpSets shape must not blank
    # RUNBOARD, PICK RUNS or FEATURES.
    r = cases.get('f41badshape', {})
    per = r.get('per') or {}
    f41_ok = (r.get('call') == 'OK'
              and all((per.get(v) or {}).get('call') == 'OK' for v in ('board', 'runs', 'feat'))
              and all((per.get(v) or {}).get('len', -1) > 200 for v in ('board', 'runs', 'feat'))
              and not any((per.get(v) or {}).get('errors') or (per.get(v) or {}).get('uncaught')
                          for v in ('board', 'runs', 'feat')))
    line('f41badshape', f41_ok, 'board=(call=%s len=%s) runs=(call=%s len=%s) feat=(call=%s len=%s)'
         % (tuple(x for v in ('board', 'runs', 'feat') for x in ((per.get(v) or {}).get('call'), (per.get(v) or {}).get('len')))))
    if not f41_ok:
        for v in ('board', 'runs', 'feat'):
            p = per.get(v) or {}
            if p.get('call') != 'OK':
                fail('f41badshape: %s view threw on a malformed cmpIds/cmpSets shape -- %s' % (v, str(p.get('call'))[:400]))
            if p.get('errors'):
                fail('f41badshape: %s console.error -- %s' % (v, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('f41badshape: %s uncaught -- %s' % (v, p['uncaught'][0][:200]))
            if p.get('call') == 'OK' and p.get('len', -1) <= 200:
                fail('f41badshape: %s rendered almost nothing (%s chars) - a swallowed error blanked the screen instead of throwing where we can see it' % (v, p.get('len')))

    # case 11: top runs
    r = cases.get('toprun', {})
    per = r.get('per') or {}
    b, w = (per.get('best') or {}), (per.get('worst') or {})
    top_ok = (r.get('call') == 'OK'
              and not b.get('errors') and not b.get('uncaught')
              and b.get('tabs') == 3 and w.get('tabs') == 3
              and (b.get('n') or 0) >= 2 and (w.get('n') or 0) >= 2
              and b.get('first') == r.get('betterId')      # the better run leads BEST
              and w.get('first') != b.get('first'))        # and does not lead WORST
    line('toprun', top_ok, 'best=(call=%s tabs=%s n=%s first=%s) worst=(first=%s) better=%s off=(%s rows=%s)'
         % (b.get('call'), b.get('tabs'), b.get('n'), b.get('first'), w.get('first'),
            r.get('betterId'), r.get('offCall'), r.get('offRows')))
    if not top_ok:
        for k in ('best', 'worst'):
            p = per.get(k) or {}
            if p.get('call') != 'OK':
                fail('toprun: %s threw -- %s' % (k, str(p.get('call'))[:300]))
            if p.get('errors'):
                fail('toprun: %s console.error -- %s' % (k, p['errors'][0][:200]))
        if b.get('tabs') != 3:
            fail('toprun: %s tabs, expected BEST / WORST / NEWEST' % b.get('tabs'))
        if (b.get('n') or 0) < 2:
            fail('toprun: only %s rows listed for two runs' % b.get('n'))
        if b.get('first') != r.get('betterId'):
            fail('toprun: BEST leads with run %s, but %s is the better run on this read'
                 % (b.get('first'), r.get('betterId')))
        if w.get('first') == b.get('first'):
            fail('toprun: BEST and WORST lead with the same run, so the ordering is not '
                 'reversing')

    # case 12: champions source
    r = cases.get('champions', {})
    ch_ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
             and r.get('srcBtns') == 2
             and r.get('chips') == 1                      # one family, one champion
             and (r.get('ids') or []) == [r.get('expect')]
             and r.get('rm') == 0 and r.get('clr') == 0    # nothing to remove; it fills itself
             and r.get('leadChamp') == r.get('expect'))    # and the leaderboard agrees
    line('champions', ch_ok, 'call=%s src=%s chips=%s ids=%s expect=%s rm=%s clr=%s lead=%s'
         % (r.get('call'), r.get('srcBtns'), r.get('chips'), r.get('ids'), r.get('expect'),
            r.get('rm'), r.get('clr'), r.get('leadChamp')))
    if not ch_ok:
        if r.get('call') != 'OK':
            fail('champions: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('srcBtns') != 2:
            fail('champions: %s source buttons, expected PICKED and CHAMPIONS' % r.get('srcBtns'))
        if r.get('chips') != 1:
            fail('champions: %s chips for one family - it should show one champion each'
                 % r.get('chips'))
        if (r.get('ids') or []) != [r.get('expect')]:
            fail('champions: the overlay shows %s, expected the crowned run %s'
                 % (r.get('ids'), r.get('expect')))
        if r.get('rm') or r.get('clr'):
            fail('champions: remove/clear controls are showing (rm=%s clr=%s) on a list that '
                 'fills itself' % (r.get('rm'), r.get('clr')))
        if r.get('leadChamp') != r.get('expect'):
            fail('champions: the leaderboard names %s as champion but the overlay shows %s - '
                 'the two screens are not reading one rule'
                 % (r.get('leadChamp'), r.get('expect')))

    # case 13: the SETS sheet on the overlay + the BOOK launcher on BOOKS
    r = cases.get('sets', {})
    bm = r.get('bkModal') or {}
    sets_ok = (r.get('call') == 'OK' and r.get('shutCall') == 'OK'
               and r.get('champCall') == 'OK' and r.get('bkCall') == 'OK'
               and r.get('mtCall') == 'OK'
               and not r.get('errors') and not r.get('uncaught')
               # open on PICKED: opener, both tabs, the +, a close on each, the saved set
               # with its rename/delete, and the save-current control -- all wired
               and r.get('openBtn') == 1 and (r.get('tabs') or 0) >= 2
               and r.get('tabNew') == 1 and (r.get('tabDel') or 0) >= 2
               and (r.get('setChips') or 0) >= 1 and r.get('setSave') == 1
               and (r.get('setRen') or 0) >= 1 and (r.get('setDel') or 0) >= 1
               and r.get('tabWired') and r.get('saveWired')
               # closed: opener only
               and r.get('shutBtn') == 1 and r.get('shutTabs') == 0 and r.get('shutSave') == 0
               # nothing picked: the sheet is still there, and still wired
               and r.get('mtHold') and r.get('mtBtn') == 1 and (r.get('mtTabs') or 0) >= 2
               and r.get('mtSave') == 1 and (r.get('mtSets') or 0) >= 1 and r.get('mtWired')
               # champions: nothing, and it says why
               and r.get('champBtn') == 0 and r.get('champTabs') == 0
               and r.get('champSave') == 0 and r.get('champSets') == 0
               and r.get('champSays')
               # the launcher, on BOOKS, wired, opening the real panel
               and r.get('bkBtn') == 1 and r.get('bkWired') and not r.get('bkOldLine')
               and bm.get('run') == 1 and bm.get('cancel') == 1 and (bm.get('legs') or 0) >= 1
               and bm.get('from') == 1 and bm.get('to') == 1 and bm.get('lb') == 1
               and bm.get('nm') == 1 and bm.get('win') == 1
               and r.get('bkModalGone')
               and not r.get('bkAlert') and not r.get('bkModalErr'))
    line('sets', sets_ok,
         'open=(btn=%s tabs=%s new=%s del=%s sets=%s save=%s ren=%s sdel=%s wired=%s/%s) '
         'shut=(btn=%s tabs=%s save=%s) empty=(hold=%s btn=%s tabs=%s save=%s sets=%s wired=%s) '
         'champ=(btn=%s tabs=%s sets=%s says=%s) '
         'books=(btn=%s wired=%s oldline=%s modal=%s alert=%r)'
         % (r.get('openBtn'), r.get('tabs'), r.get('tabNew'), r.get('tabDel'),
            r.get('setChips'), r.get('setSave'), r.get('setRen'), r.get('setDel'),
            r.get('tabWired'), r.get('saveWired'),
            r.get('shutBtn'), r.get('shutTabs'), r.get('shutSave'),
            r.get('mtHold'), r.get('mtBtn'), r.get('mtTabs'), r.get('mtSave'),
            r.get('mtSets'), r.get('mtWired'),
            r.get('champBtn'), r.get('champTabs'), r.get('champSets'), r.get('champSays'),
            r.get('bkBtn'), r.get('bkWired'), r.get('bkOldLine'), bm, r.get('bkAlert')))
    if not sets_ok:
        for k, lbl in (('call', 'overlay/open'), ('shutCall', 'overlay/closed'),
                       ('champCall', 'overlay/champions'), ('mtCall', 'overlay/nothing-picked'),
                       ('bkCall', 'books')):
            if r.get(k) != 'OK':
                fail('sets: the %s render threw -- %s' % (lbl, str(r.get(k))[:300]))
        if r.get('errors'):
            fail('sets: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('sets: uncaught -- %s' % r['uncaught'][0][:200])
        if r.get('openBtn') != 1:
            fail('sets: %s TABS + SETS openers on the overlay, expected exactly 1'
                 % r.get('openBtn'))
        if (r.get('tabs') or 0) < 2 or r.get('tabNew') != 1 or (r.get('tabDel') or 0) < 2:
            fail('sets: the sheet drew %s tab chips, %s add controls and %s close controls '
                 '-- two saved tabs should give two chips, one +, and a close on each'
                 % (r.get('tabs'), r.get('tabNew'), r.get('tabDel')))
        if (r.get('setChips') or 0) < 1 or r.get('setSave') != 1:
            fail('sets: %s saved-set chips and %s save-current controls, expected the one '
                 'saved set and exactly one save control' % (r.get('setChips'), r.get('setSave')))
        if (r.get('setRen') or 0) < 1 or (r.get('setDel') or 0) < 1:
            fail('sets: the saved set has no rename (%s) or no delete (%s) control'
                 % (r.get('setRen'), r.get('setDel')))
        if not (r.get('tabWired') and r.get('saveWired')):
            fail('sets: the sheet controls are drawn but dead (tab wired=%s, save wired=%s) '
                 '-- which looks exactly like a working screen'
                 % (r.get('tabWired'), r.get('saveWired')))
        if r.get('shutBtn') != 1 or r.get('shutTabs') or r.get('shutSave'):
            fail('sets: with the sheet closed the overlay still shows %s tab chips and %s '
                 'save controls (opener=%s)'
                 % (r.get('shutTabs'), r.get('shutSave'), r.get('shutBtn')))
        if not (r.get('mtHold') and r.get('mtBtn') == 1 and (r.get('mtTabs') or 0) >= 2
                and r.get('mtSave') == 1 and (r.get('mtSets') or 0) >= 1 and r.get('mtWired')):
            fail('sets: with nothing picked the overlay shows hold=%s opener=%s tabs=%s '
                 'save=%s sets=%s wired=%s -- after CLEAR, switching to a tab that has runs '
                 'in it is the only way back, so the sheet has to survive an empty comparison'
                 % (r.get('mtHold'), r.get('mtBtn'), r.get('mtTabs'), r.get('mtSave'),
                    r.get('mtSets'), r.get('mtWired')))
        if (r.get('champBtn') or r.get('champTabs') or r.get('champSave')
                or r.get('champSets')):
            fail('sets: CHAMPIONS still shows sheet controls (opener=%s tabs=%s save=%s '
                 'sets=%s) -- that list refills itself, so they would be dead'
                 % (r.get('champBtn'), r.get('champTabs'), r.get('champSave'),
                    r.get('champSets')))
        if not r.get('champSays'):
            fail('sets: CHAMPIONS hides the sheet without saying why')
        if r.get('bkBtn') != 1:
            fail('sets: %s [data-booknew] buttons on the BOOKS view, expected exactly 1'
                 % r.get('bkBtn'))
        if not r.get('bkWired'):
            fail('sets: the RUN A BOOK button on BOOKS has no handler')
        if r.get('bkOldLine'):
            fail('sets: the BOOKS view still says the launcher lives on the RUNBOARD view')
        if r.get('bkModalErr'):
            fail('sets: opening the book panel threw -- %s' % r['bkModalErr'])
        if r.get('bkAlert'):
            fail('sets: the book launcher refused to open -- %s' % r['bkAlert'])
        if not (bm.get('run') == 1 and bm.get('cancel') == 1 and (bm.get('legs') or 0) >= 1
                and bm.get('from') == 1 and bm.get('to') == 1 and bm.get('lb') == 1
                and bm.get('nm') == 1 and bm.get('win') == 1):
            fail('sets: the book panel is not the launcher -- %s (want >=1 leg checkbox and '
                 'one each of FROM, TO, LOCKBOX MONTHS, NAME, the window readout, QUEUE BOOK '
                 'and CANCEL)' % bm)
        if not r.get('bkModalGone'):
            fail('sets: CANCEL did not close the book panel')


    # case 14: a gate row is plottable on the WALK-FORWARD stage
    #   600 gate rows - every one on the board, the same 40 on each of 15 runs - were off
    #   the chart because the gate row reported no walk-forward figure at all. Other rows
    #   on this board legitimately record nothing for a walk-forward stretch (a sweep row
    #   from the studies registry has no such slice), so this asserts the GATE point, not
    #   an empty skip list.
    r = cases.get('gatewf', {})
    dash = '—'
    def _f(x):
        try:
            return float(str(x).replace('R', '').replace(',', '').strip())
        except (TypeError, ValueError):
            return None
    _e, _t, _y = _f(r.get('gateEvr')), _f(r.get('gateTpy')), _f(r.get('gateRpy'))
    tpy_agrees = (_e is not None and _t is not None and _y is not None and _y != 0
                  and abs(_e * _t - _y) / abs(_y) < 0.05)
    _il, _as = (r.get('isLb') or {}), (r.get('allSeg') or {})
    # $/TRD is whole-run money over whole-run trades on EVERY stage tick: tot 12,000 x 20 / 125 trades = $1,920
    _wo = (r.get('wfOnly') or {})
    _ppts = [_wo.get('ppt'), _il.get('ppt'), _as.get('ppt')]
    stages_ok = (all(p == _ppts[2] for p in _ppts) and _ppts[2] not in (None, '', '—')
                 and str(_il.get('trd')).startswith('45') and _il.get('tpy') == '6.4'
                 and str(_as.get('trd')).startswith('125') and _as.get('tpy') == '7.8')
    line('stage-counts', stages_ok, 'IS+LB trades=%r per yr=%r (want 45 / 6.4) | all three trades=%r per yr=%r (want 125 / 7.8) | $/TRD wf/is+lb/all=%r (all equal)'
         % (_il.get('trd'), _il.get('tpy'), _as.get('trd'), _as.get('tpy'), _ppts))
    if not stages_ok:
        fail('stage-counts: IN-SAMPLE + LOCKBOX is not reading the ticked stretches (or all three moved) -- see the stage-counts line')
    _ORDER = ['so', 'sh', 'ddr', 'ddp', 'dd', 'ratio', 'pf', 'wr', 'evr', 'ppt', 'rpy', 'roc', 'raw']
    _ax = r.get('axNew') or {}
    axes_ok = (r.get('axOrdY') == _ORDER and r.get('axOrdX') == _ORDER
               and all(isinstance(v, int) and v >= 1 for v in _ax.values()) and len(_ax) == 6)
    line('axes', axes_ok, 'vertical=%s horizontal=%s gate points on new pairings=%s'
         % (r.get('axOrdY'), r.get('axOrdX'), _ax))
    if not axes_ok:
        fail('axes: the two axis pickers differ from the agreed order, or a new pairing drew no gate point -- see the axes line')
    cols_ok = (r.get('allCall') == 'OK' and r.get('allBad') == 0 and r.get('allRunHeads') == 1
               and r.get('iRun', -1) >= 0 and r.get('iTpy', -1) >= 0 and r.get('tdBad') == 0
               and r.get('runSortable') and r.get('tpySortable')
               and str(r.get('gateRun') or '').startswith(str(r.get('expectRun'))) and tpy_agrees)
    gw_ok = (cols_ok and r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
             and r.get('hasGateRow') and r.get('sums')
             and (r.get('gatePoints') or 0) >= 1
             and r.get('gateMar') not in (None, '', dash)
             and r.get('gateRoc') not in (None, '', dash))
    line('gatewf', gw_ok, 'call=%s gateRow=%s gatePts=%s of %s pts (skip %s of %s) MAR=%r '
         'ROC=%r sums=%s'
         % (r.get('call'), r.get('hasGateRow'), r.get('gatePoints'), r.get('points'),
            r.get('skipN'), r.get('shownN'), r.get('gateMar'), r.get('gateRoc'),
            r.get('sums')))
    line('columns', cols_ok, 'RUN at %s (%r, want %s, sorts=%s) TRADES/YR at %s (%r, sorts=%s) misaligned rows=%s EVR*TPY=%s vs R/YR=%s | ALL: th=%s misaligned=%s RUN headings=%s'
         % (r.get('iRun'), r.get('gateRun'), r.get('expectRun'), r.get('runSortable'), r.get('iTpy'),
            r.get('gateTpy'), r.get('tpySortable'), r.get('tdBad'),
            (None if (_e is None or _t is None) else round(_e * _t, 1)), _y,
            r.get('allTh'), r.get('allBad'), r.get('allRunHeads')))
    if not cols_ok:
        fail('columns: RUN / TRADES-YR columns wrong -- see the columns line above (a misaligned row means a cell was added without its heading, or the reverse)')
    if not gw_ok:
        if r.get('call') != 'OK':
            fail('gatewf: renderApp threw -- %s' % str(r.get('call'))[:300])
        if not r.get('hasGateRow'):
            fail('gatewf: no GATE row rendered at all, so the case proves nothing')
        if not r.get('sums'):
            fail('gatewf: the probe fixture is wrong - in-sample plus walk-forward must add '
                 'up to the pooled pre-lockbox figure, or the split would double-count')
        if (r.get('gatePoints') or 0) < 1:
            fail('gatewf: the GATE row is not on the chart on the walk-forward stage - it is '
                 'reporting no walk-forward figure again (%s points drawn, %s of %s rows off)'
                 % (r.get('points'), r.get('skipN'), r.get('shownN')))
        if r.get('gateMar') in (None, '', dash) or r.get('gateRoc') in (None, '', dash):
            fail('gatewf: the GATE row shows MAR=%r and ROC=%r on the walk-forward stage - a '
                 'dash there means the stage profit is missing again'
                 % (r.get('gateMar'), r.get('gateRoc')))

    # case crowns: knob test never champion, books on pre-lockbox net/DD, star wins; run window
    r = cases.get('crowns', {})
    un, st = str(r.get('unstarred') or ''), str(r.get('starred') or '')
    cap = r.get('capped') or {}
    cap_ok = (len(cap) == 4 and all(v.get('call') == 'OK' and v.get('txt') == 'NEWEST 4 RUNS'
                                    and v.get('btns') == 2 and v.get('wired') for v in cap.values()))
    cr_ok = (r.get('call') == 'OK' and r.get('starCall') == 'OK' and not r.get('errors')
             and 'top pick' in un and '#910003' in un and '#910001' not in un
             and 'your crown' in st and '#910002' in st
             and str(r.get('allTxt') or '').startswith('ALL 4 RUNS') and r.get('allBtns') == 0 and cap_ok)
    line('crowns', cr_ok, 'unstarred=%r | starred=%r | uncapped=%r btns=%s | capped=%s'
         % (un[:60], st[:60], r.get('allTxt'), r.get('allBtns'), cap))
    if not cr_ok:
        fail('crowns: champion or run-window note wrong -- see the crowns line (want BEST #910003 as top pick with the KNOB TEST passed over, RICH #910002 as your crown once starred, ALL 4 RUNS uncapped, NEWEST 4 RUNS with two wired loaders on every screen when capped)')
    # case runstages: a RUN row follows the ticked stretch
    r = cases.get('runstages', {})
    ex = r.get('exp') or {}
    def _n(v):
        try:
            return int(str(v).replace(',', '').strip())
        except (TypeError, ValueError):
            return None
    dash = chr(0x2014)
    rs_checks = {
        'wf pf': (r.get('wf') or {}).get('pf') == (ex.get('wf') or {}).get('pf'),
        'wf win': (r.get('wf') or {}).get('wr') == (ex.get('wf') or {}).get('wr'),
        'wf trades': _n((r.get('wf') or {}).get('trd')) == (ex.get('wf') or {}).get('trd'),
        'wf sharpe dashes (no saved boundary)': (r.get('wf') or {}).get('sh') == dash,
        'wf MAR dashes (no saved boundary)': (r.get('wf') or {}).get('mar') == dash,
        'is MAR is a number now that its own measured drawdown is known': (r.get('is') or {}).get('mar') not in (None, '', dash),
        'is+wf MAR from the lockbox boundary, marked ~': str((r.get('pre') or {}).get('mar') or '').startswith('~'),
        'lb pf': (r.get('lb') or {}).get('pf') == (ex.get('lb') or {}).get('pf'),
        'lb trades': _n((r.get('lb') or {}).get('trd')) == (ex.get('lb') or {}).get('trd'),
        'lb MAR not ~ (saved drawdown)': not str((r.get('lb') or {}).get('mar') or '').startswith('~'),
        'is pf': (r.get('is') or {}).get('pf') == (ex.get('is') or {}).get('pf'),
        'is trades': _n((r.get('is') or {}).get('trd')) == (ex.get('is') or {}).get('trd'),
        'all pf': (r.get('all') or {}).get('pf') == (ex.get('all') or {}).get('pf'),
        'all trades': _n((r.get('all') or {}).get('trd')) == (ex.get('all') or {}).get('trd'),
        'is+lb pf dashes': (r.get('islb') or {}).get('pf') == dash,
        'is+lb trades add': _n((r.get('islb') or {}).get('trd')) == (ex.get('islb') or {}).get('trd'),
        'no measured slice: IS dashes EV R': (r.get('badIs') or {}).get('evr') == dash,
        'no measured slice: IS dashes PF': (r.get('badIs') or {}).get('pf') == dash,
        'no measured slice: IS+WF dashes EV R and R/YR': (r.get('badIsWf') or {}).get('evr') == dash and (r.get('badIsWf') or {}).get('rpy') == dash,
        'no measured slice: ALL THREE = the clean run': (r.get('badAll') or {}).get('evr') == (r.get('all') or {}).get('evr') not in (None, '', dash),
    }
    rs_ok = all(rs_checks.values()) and all((r.get(k) or {}).get('call') == 'OK' and (r.get(k) or {}).get('row') for k in ('wf', 'lb', 'is', 'all', 'islb', 'pre', 'badIs', 'badIsWf', 'badAll'))
    line('runstages', rs_ok, 'failed=%s | wf=%s lb=%s is=%s all=%s is+lb=%s | expected=%s'
         % ([k for k, v in rs_checks.items() if not v], r.get('wf'), r.get('lb'), r.get('is'), r.get('all'), r.get('islb'), ex))
    if not rs_ok:
        fail('runstages: a run row is not reading the ticked stretch -- see the runstages line')
    # case fixes346
    r = cases.get('fixes346', {})
    sv, cv = (r.get('rbSaved') or {}), (r.get('rbCurve') or {})
    def _fl(x):
        try:
            return float(str(x).replace('~', '').replace(',', '').strip())
        except (TypeError, ValueError):
            return None
    chk = {
        '6 RUNBOARD full MAR from saved dd': sv.get('mar') == r.get('rbWant'),
        '6 saved dd not marked ~': '~' not in str(sv.get('mar') or '') and '~' not in str(sv.get('dd') or ''),
        '6 curve fallback marked ~': str(cv.get('mar') or '').startswith('~') and str(cv.get('dd') or '').startswith('~'),
        '6 curve fallback never best': not cv.get('marBold'),
        '3 chart MAR = table MAR (per year)': (_fl(r.get('gateMarCell')) is not None and r.get('gateMarPoint') is not None
                                               and abs(_fl(r.get('gateMarCell')) - float(r.get('gateMarPoint'))) < 0.011),
        '4 WF pick sizes on the WF twin': r.get('hybWf') == '$40,000',
        '4 combined tick reads the combined block at its own factor': 'profit of $65,625' in str(r.get('hybWfLbTip') or ''),
        '4 option A: one size for the WF+LB pick, rows add up': (r.get('hybWfAtCombined') == '$26,250' and r.get('hybLbAtCombined') == '$39,375'),
    }
    f346_ok = all(chk.values())
    line('fixes346', f346_ok, 'failed=%s | rb saved=%s curve=%s want=%s | gate MAR cell=%r point=%r | hybrid WF(%s)=%r'
         % ([k for k, v in chk.items() if not v], sv, cv, r.get('rbWant'), r.get('gateMarCell'), r.get('gateMarPoint'), r.get('hybWfHdr'), r.get('hybWf')))
    if not f346_ok:
        fail('fixes346: see the fixes346 line')
    # case lvlall: LEVEL = ALL holds the sweeps AND the runs / configurations
    r = cases.get('lvlall', {})
    c, u = (r.get('cfg') or {}), (r.get('runs') or {})
    la_chk = {
        'configs view: call ok': c.get('call') == 'OK',
        'configs view: sweeps listed': (c.get('sweeps') or 0) >= 1,
        'configs view: config points on Sortino x ROC (WF)': (c.get('gatePts') or 0) >= 1,
        'runs view: call ok': u.get('call') == 'OK',
        'runs view: the run itself listed': (u.get('runRows') or 0) >= 1,
        'runs view: sweeps listed': (u.get('sweeps') or 0) >= 1,
        'runs view: something plotted': (u.get('points') or 0) >= 1,
    }
    la_ok = all(la_chk.values())
    line('lvlall', la_ok, 'failed=%s | configs=%s | runs=%s' % ([k for k, v in la_chk.items() if not v], c, u))
    if not la_ok:
        fail('lvlall: LEVEL = ALL is not showing sweeps together with runs / configurations -- see the lvlall line')
    # case rbhoriz: RUNBOARD sideways reads the same rows as the grid
    r = cases.get('rbhoriz', {})
    per = r.get('per') or {}
    rbh_ok = all(((per.get(sm) or {}).get('v') or {}).get('mar') not in (None, '')
                 and ((per.get(sm) or {}).get('h') or {}).get('mar') == ((per.get(sm) or {}).get('v') or {}).get('mar')
                 and ((per.get(sm) or {}).get('h') or {}).get('horizTable')
                 for sm in ('lb', 'full'))
    line('rbhoriz', rbh_ok, 'lb=%s full=%s' % (per.get('lb'), per.get('full')))
    if not rbh_ok:
        fail('rbhoriz: RUNBOARD sideways does not show the grid rows (MAR differs from the vertical grid) -- see the rbhoriz line')
    # case smalls: CHAMPIONS names its ranking; ticks carry their unit; no garbled lockbox tooltip
    r = cases.get('smalls', {})
    sm_chk = {
        'all three renders OK': all(r.get(k) == 'OK' for k in ('champCall', 'pickCall', 'tickCall')),
        'champions label names the ranking': bool(r.get('champLabel')) and ' BY MAR ON LB' in str(r.get('champLabel')),
        'RANK ON on CHAMPIONS': (r.get('champRankBtns') or 0) == 4,
        'no RANK ON on PICKED': (r.get('pickRankBtns') or 0) == 0,
        'ROC ticks carry %': (r.get('pctTicks') or 0) >= 2,
    }
    sm_ok = all(sm_chk.values())
    line('smalls', sm_ok, 'failed=%s | %s' % ([k for k, v in sm_chk.items() if not v], {k: r.get(k) for k in ('champLabel', 'champRankBtns', 'pickRankBtns', 'pctTicks')}))
    if not sm_ok:
        fail('smalls: see the smalls line')
    # case rbstage: hosted RUNBOARD follows the COMPARE tab's one STAGE
    r = cases.get('rbstage', {})
    rbw = (cases.get('runboard') or {}).get('per') or {}
    want_is, want_lb = (rbw.get('is') or {}).get('mar'), (rbw.get('lb') or {}).get('mar')
    rs_chk = {
        'renders OK': all(r.get(k) == 'OK' for k in ('isCall', 'lbCall', 'wfCall', 'oldCall')),
        'hosted IS reads the tab stage (not SAMPLE LB)': r.get('isMar') == want_is and want_is is not None,
        'hosted LB reads the tab stage (not SAMPLE IS)': r.get('lbMar') == want_lb and want_lb is not None,
        # v73.817: the board reads the saved walk-forward test, so the WF sample is a real
        # sample. Only the BOOKS table is held (its walk-forward entry is a held count, not
        # figures). A run with no saved test dashes; it no longer takes the whole view down.
        'hosted WF keeps its panels and holds only BOOKS': (bool(r.get('wfHold')) and bool(r.get('wfTab'))
                                                           and bool(r.get('wfFunnel')) and (r.get('wfRows') or 0) == 1),
        'hosted WF dashes a run that saved no walk-forward test': r.get('wfMar') in ('\u2014', None),
        'old tab SAMPLE click leaves the COMPARE stage alone': r.get('oldClickStage') == 'is',
        'SAMPLE click sets the tab stage': r.get('afterClick') == 'full',
        'outside COMPARE keeps its own SAMPLE': r.get('oldMar') == want_lb and not r.get('oldWfTab'),
    }
    rs2_ok = all(rs_chk.values())
    line('rbstage', rs2_ok, 'failed=%s | %s | want is=%s lb=%s' % ([k for k, v in rs_chk.items() if not v], {k: r.get(k) for k in ('isMar', 'lbMar', 'wfHold', 'wfMar', 'wfTab', 'wfFunnel', 'wfRows', 'afterClick', 'oldMar', 'oldWfTab', 'oldClickStage')}, want_is, want_lb))
    if not rs2_ok:
        fail('rbstage: see the rbstage line')
    # case a_champpf: FULL PF is the champion's own reading (item 1)
    r = cases.get('a_champpf', {})
    def _f(v):
        m = re.match(r'~?(-?[0-9.]+)', str(v))
        return float(m.group(1)) if m else None
    ac_lead = _f(r.get('leadTxt'))
    ac_ovl = _f(r.get('ovlPf'))
    ac_want = r.get('want')
    ac_ok = (r.get('call') == 'OK' and r.get('ovlCall') == 'OK' and r.get('twinCall') == 'OK'
             and r.get('twinOvlCall') == 'OK'
             and ac_lead is not None and ac_want is not None and abs(ac_lead - ac_want) < 0.02
             and not str(r.get('leadTxt') or '').startswith('~')
             and ac_ovl is not None and abs(ac_ovl - ac_want) < 0.02
             and str(r.get('twinTxt') or '').startswith('~')
             and str(r.get('twinOvlPf') or '').startswith('~'))
    line('a_champpf', ac_ok, 'want=%.3f lead=%s ovl=%s twin=%s twinOvl=%s'
         % (ac_want or -1, r.get('leadTxt'), r.get('ovlPf'), r.get('twinTxt'), r.get('twinOvlPf')))
    if not ac_ok:
        fail('a_champpf: FULL PF is not the champion own whole-run reading (item 1) -- see the a_champpf line')

    # case a_champpf_ovl: EV R / R per YR on the OVERLAY matrix carry the SAME ~ mark as
    # PF whenever they are built off a pfApx (rebuilt) PF -- audit round 2, item 1
    r = cases.get('a_champpf_ovl', {})
    aco_ok = (r.get('call') == 'OK'
             and str(r.get('pfB') or '').startswith('~')
             and str(r.get('evB') or '').startswith('~')
             and str(r.get('rpyB') or '').startswith('~')
             and 'rebuilt' in str(r.get('evBTitle') or '')
             and 'rebuilt' in str(r.get('rpyBTitle') or ''))
    line('a_champpf_ovl', aco_ok, 'pfB=%r evB=%r evBTitle=%r rpyB=%r rpyBTitle=%r'
         % (r.get('pfB'), r.get('evB'), r.get('evBTitle'), r.get('rpyB'), r.get('rpyBTitle')))
    if not aco_ok:
        fail('a_champpf_ovl: EV R / R per YR on the OVERLAY FULL matrix do not carry the ~ mark (and best/heat exclusion) when built off a pfApx PF (item 1, round 2)')

    # case a_isyrs: IS years = 0.75 x the tuning window; a book runs date_from -> lockbox_from
    r = cases.get('a_isyrs', {})
    ai_ok = (r.get('call') == 'OK' and r.get('bookCall') == 'OK'
             and r.get('gotYrs') is not None and r.get('wantYrs') is not None
             and abs(r['gotYrs'] - r['wantYrs']) < 0.15
             and _f(r.get('bookMarTxt')) is not None and r.get('wantBookMar') is not None
             and abs(_f(r.get('bookMarTxt')) - r['wantBookMar']) < 0.03
             and r.get('aoCall') == 'OK'
             and r.get('gotAoYrs') is not None and r.get('wantAoYrs') is not None
             and abs(r['gotAoYrs'] - r['wantAoYrs']) < 0.15)
    line('a_isyrs', ai_ok, 'gotYrs=%s wantYrs=%s bookMar=%s wantBookMar=%s gotAoYrs=%s wantAoYrs=%s'
         % (r.get('gotYrs'), r.get('wantYrs'), r.get('bookMarTxt'), r.get('wantBookMar'), r.get('gotAoYrs'), r.get('wantAoYrs')))
    if not ai_ok:
        fail('a_isyrs: IS years is not 0.75 of the tuning window, or a book IS MAR does not run date_from -> lockbox_from, or a plain Auto-Optimize run with an emoji-prefixed scope is not corrected (item 5)')

    # case a_wfyrs: WF R / YR on the leaderboard/overlay equals EXPLORE's own run-row reading
    r = cases.get('a_wfyrs', {})
    aw_lead = _f(r.get('leadRpy'))
    aw_exp = _f(r.get('exploreRpy'))
    aw_ok = (r.get('call') == 'OK' and r.get('leadCall') == 'OK' and r.get('marCall') == 'OK'
             and aw_lead is not None and aw_exp is not None and abs(aw_lead - aw_exp) <= max(0.3, 0.03 * abs(aw_exp))
             # v73.817: the reason is the saved test's own. run_report.json has none, so it
             # reads 'saved before walk-forward detail was recorded' rather than claiming a
             # curve cut was attempted.
             and 'saved before walk-forward detail was recorded' in str(r.get('marTitle') or ''))
    line('a_wfyrs', aw_ok, 'lead=%s explore=%s marTitle=%r'
         % (r.get('leadRpy'), r.get('exploreRpy'), r.get('marTitle')))
    if not aw_ok:
        fail('a_wfyrs: leaderboard WF R / YR does not match EXPLORE own run-row reading, or the WF MAR dash reason still claims a cut was attempted (item 9)')

    # case a_famlabel: two unregistered strategies sharing a tag render two distinct names
    r = cases.get('a_famlabel', {})
    af_ok = (r.get('call') == 'OK' and (r.get('rowsN') or 0) >= 2
             and r.get('labelA') and r.get('labelB') and r.get('labelA') != r.get('labelB'))
    line('a_famlabel', af_ok, 'rowsN=%s labelA=%r labelB=%r' % (r.get('rowsN'), r.get('labelA'), r.get('labelB')))
    if not af_ok:
        fail('a_famlabel: two unregistered strategies still render the same shared tag as their family name (item 10)')
    # same case, second surface: the OVERLAY equity-chart legend / fullscreen multi-curve
    # explorer label (window._cmpEqxSeries) must not collapse the same two files either
    af2_ok = (r.get('ovlCall') == 'OK'
             and r.get('eqLabelA') and r.get('eqLabelB') and r.get('eqLabelA') != r.get('eqLabelB'))
    line('a_famlabel_ovl', af2_ok, 'eqLabelA=%r eqLabelB=%r' % (r.get('eqLabelA'), r.get('eqLabelB')))
    if not af2_ok:
        fail('a_famlabel_ovl: the OVERLAY equity-chart legend / fullscreen explorer still renders the same shared tag for two unregistered strategies (item 10, window._cmpEqxSeries label)')

    # case a_starruns: a run visible only via window._starRuns still heads its family
    r = cases.get('a_starruns', {})
    as_ok = (r.get('call') == 'OK' and r.get('famFound') and r.get('isCrown') and r.get('noteTxt'))
    line('a_starruns', as_ok, 'famFound=%s whoTxt=%r noteTxt=%r' % (r.get('famFound'), r.get('whoTxt'), r.get('noteTxt')))
    if not as_ok:
        fail('a_starruns: a run known only via window._starRuns does not head its family, or the run-window note does not name it (item 4)')

    # case a_lbzero: zero-trade lockbox dashes with the true reason; PF exactly 0 (with
    # trades) reads 0.00, not a dash
    r = cases.get('a_lbzero', {})
    az_ok = (r.get('call') == 'OK' and r.get('ovlCall') == 'OK'
             and r.get('zTxt') == u'\u2014'
             and 'took no trades in the lockbox' in str(r.get('zTitle') or '')
             and 'no LB trades' in str(r.get('zWhoTxt') or '').replace(u'\u00b7', '.')
             and '$0' not in str(r.get('zWhoTxt') or '')
             and r.get('pTxt') == '0.00'
             and r.get('ovlPf') == '0.00')
    line('a_lbzero', az_ok, 'zTxt=%r zTitle=%r zWho=%r pTxt=%r ovlPf=%r'
         % (r.get('zTxt'), r.get('zTitle'), r.get('zWhoTxt'), r.get('pTxt'), r.get('ovlPf')))
    if not az_ok:
        fail('a_lbzero: a zero-trade lockbox still reads a $0/0.00 figure instead of a dashed reason, or a lockbox that lost every trade still dashes PF instead of reading 0.00 (item 11a)')

    # case a_topruns: the short-window caveat on TOP RUNS is truthful
    r = cases.get('a_topruns', {})
    at_ok = (r.get('call') == 'OK' and r.get('title')
             and 'leaves runs like this out' not in r['title'])
    line('a_topruns', at_ok, 'title=%r' % r.get('title'))
    if not at_ok:
        fail('a_topruns: the short-window hover still claims the champion list leaves the run out, which is false for the leaderboard (item 11b)')
    # case b_famBook (item 3): a book named after a strategy is not a member of that family
    r = cases.get('b_famBook', {})
    fb_chk = {
        'renders OK': r.get('call') == 'OK',
        # TASK 2 (2026-09-23): the RUNBOARD chip list and its drill-down now key on
        # _c2FamOf (the structural r.book.legs test every book run always satisfies),
        # not _canonFam's own "does the label start with BOOK" guess - so every real
        # book groups the same way here as it already does in the champion pool just
        # above it (_c2FamsOf), under the same 'BOOKS' string. _canonFam keeps its own
        # 'BOOK' singular for the EXPLORE rail below, untouched by this change.
        'RUNBOARD family chips show BOOKS': 'BOOKS' in (r.get('chips') or []),
        'the book does not fold into an ENGU-Q chip': 'ENGU-Q' not in (r.get('chips') or []),
        'EXPLORE strategy rail shows BOOK (fixed for free by the same matcher)': bool(r.get('railHasBook')),
    }
    fb_ok = all(fb_chk.values())
    line('b_famBook', fb_ok, 'failed=%s | chips=%s railHasBook=%s' % ([k for k, v in fb_chk.items() if not v], r.get('chips'), r.get('railHasBook')))
    if not fb_ok:
        fail('b_famBook: see the b_famBook line')

    # case b_rbBooksCol (item 3): the shared champion rule pools books into ONE BOOKS column
    r = cases.get('b_rbBooksCol', {})
    ids = r.get('colIds') or []
    rb2_chk = {
        'renders OK': r.get('call') == 'OK',
        'exactly two columns (the ENGU-Q run + one BOOKS champion)': len(ids) == 2,
        'the real ENGU-Q run keeps its own column': '500011' in ids,
        'the higher net/DD book (BETA) is the BOOKS champion': '500013' in ids,
        'the lower net/DD book (ALPHA) does not get a second column': '500012' not in ids,
    }
    rb2_ok = all(rb2_chk.values())
    line('b_rbBooksCol', rb2_ok, 'failed=%s | colIds=%s' % ([k for k, v in rb2_chk.items() if not v], ids))
    if not rb2_ok:
        fail('b_rbBooksCol: see the b_rbBooksCol line')

    # case b_rbReads (item 6): one set of readers feeds RANK BY and the matrix cells
    r = cases.get('b_rbReads', {})
    rr_chk = {
        'renders OK': r.get('call') == 'OK',
        'exactly two columns': len(r.get('colIds') or []) == 2,
        'FULL PF row is sorted (non-increasing)': bool(r.get('pfNonIncreasing')),
        "P keeps its saved whole-run trade count (5000)": r.get('pTrades') == 5000,
        'P is not marked ~ (it saved a real count)': not r.get('pTradesApx'),
        'Q falls back to the summed count (500) marked ~': r.get('qTrades') == 500 and bool(r.get('qTradesApx')),
        'no best mark on TRADES': (r.get('tradesBest') or 0) == 0,
        'no best mark on WIN %': (r.get('winBest') or 0) == 0,
    }
    rr_ok = all(rr_chk.values())
    line('b_rbReads', rr_ok, 'failed=%s | colIds=%s pfNums=%s pTrades=%s(~%s) qTrades=%s(~%s)' % (
        [k for k, v in rr_chk.items() if not v], r.get('colIds'), r.get('pfNums'),
        r.get('pTrades'), r.get('pTradesApx'), r.get('qTrades'), r.get('qTradesApx')))
    if not rr_ok:
        fail('b_rbReads: see the b_rbReads line')

    # case b_pickStage (item 7): hosted PICK RUNS follows the tab's STAGE
    r = cases.get('b_pickStage', {})
    ps_chk = {
        'renders OK': r.get('call1') == 'OK' and r.get('call2') == 'OK',
        'hosted PICK RUNS lights LOCKBOX (not the stale TOTAL cmpScope)': bool(r.get('lit')),
        'hosted PICK RUNS prints the lockbox net': bool(r.get('net1')) and r.get('net1') not in (None, '', '—'),
        "the old, un-hosted tab keeps reading its own cmpScope (TOTAL) unaffected": bool(r.get('oldTot')),
    }
    ps_ok = all(ps_chk.values())
    line('b_pickStage', ps_ok, 'failed=%s | %s' % ([k for k, v in ps_chk.items() if not v], r))
    if not ps_ok:
        fail('b_pickStage: see the b_pickStage line')

    # case b_rbSmalls (item 11): small RUNBOARD / BOOKS label and read fixes
    r = cases.get('b_rbSmalls', {})
    sm2_chk = {
        'renders OK': all(r.get(k) == 'OK' for k in ('call1', 'call2', 'call3', 'call4')),
        'RUNBOARD tile header reads NET DIVIDE DD, not MAR': bool(r.get('hasNetDdHdr')) and not r.get('hasMarHdr'),
        'RUNBOARD tile header reads SLICES, not WF': bool(r.get('hasSlicesHdr')) and not r.get('hasWfHdr'),
        'RUNBOARD tile note reads NET DIVIDE DD = net divided by...': bool(r.get('noteSaysNetDd')) and not r.get('noteSaysMarEquals'),
        'native BOOKS view header reads SLICES, not WF': bool(r.get('nativeHasSlicesHdr')) and not r.get('nativeHasWfHdr'),
        'native BOOKS view note reads NET DIVIDE DD = net divided by...': bool(r.get('nativeNoteSaysNetDd')) and not r.get('nativeNoteSaysMarEquals'),
        'TOP 10 RECENT dashes a run with no figure (not $0)': bool(r.get('sideRowHasDash')) and not r.get('sideRowHasZero'),
        'live book rows rank by RANK BY (best net/DD first, not newest id first)': r.get('liveOrder') == ['400001', '400002'],
    }
    sm2_ok = all(sm2_chk.values())
    line('b_rbSmalls', sm2_ok, 'failed=%s | %s' % ([k for k, v in sm2_chk.items() if not v], r))
    if not sm2_ok:
        fail('b_rbSmalls: see the b_rbSmalls line')

    # case b_famBookPast (item 3, repair round): Past Runs / RESULTS family chips read BOOK
    # too, via _famKey (not just _canonFam) - _stratMatch's fuzzy version-matching used to
    # resolve a book's own leg-version digit to a real library file and read THAT file's family.
    r = cases.get('b_famBookPast', {})
    fbp_chk = {
        'renders OK': r.get('call') == 'OK',
        'Past Runs family chips show BOOK': 'BOOK' in (r.get('chips') or []),
        'the book does not resolve to ORB via a real library file matching its leg-version digit': 'ORB' not in (r.get('chips') or []),
    }
    fbp_ok = all(fbp_chk.values())
    line('b_famBookPast', fbp_ok, 'failed=%s | chips=%s' % ([k for k, v in fbp_chk.items() if not v], r.get('chips')))
    if not fbp_ok:
        fail('b_famBookPast: see the b_famBookPast line')

    # case b_pfApxExact (item 6, repair round): a run with no walk-forward and no lockbox
    # shows its exact best_pf / best_trades on FULL, never marked ~.
    r = cases.get('b_pfApxExact', {})
    pae_chk = {
        'renders OK': r.get('call') == 'OK',
        'FULL PF shows the exact best_pf (1.55), not marked ~': r.get('pfTxt') == '1.55' and not r.get('pfHasTilde'),
        'FULL TRADES shows the exact best_trades (842), not marked ~': r.get('trTxt') == '842' and not r.get('trHasTilde'),
    }
    pae_ok = all(pae_chk.values())
    line('b_pfApxExact', pae_ok, 'failed=%s | pfTxt=%s trTxt=%s' % ([k for k, v in pae_chk.items() if not v], r.get('pfTxt'), r.get('trTxt')))
    if not pae_ok:
        fail('b_pfApxExact: see the b_pfApxExact line')

    # case b_pickBest (item 3, call-site audit finding): PICK RUNS' own star marker is not
    # trapped by a book's NaN scoreRun the way it used to be.
    r = cases.get('b_pickBest', {})
    pb_chk = {
        'renders OK': r.get('call') == 'OK',
        'the STRONGER book (by pre-lockbox net over drawdown) is starred as best': bool(r.get('strongIsBest')),
        'the WEAKER book (seen first in the id-descending walk) is not starred': not r.get('weakIsBest'),
    }
    pb_ok = all(pb_chk.values())
    line('b_pickBest', pb_ok, 'failed=%s | weakIsBest=%s strongIsBest=%s' % (
        [k for k, v in pb_chk.items() if not v], r.get('weakIsBest'), r.get('strongIsBest')))
    if not pb_ok:
        fail('b_pickBest: see the b_pickBest line')

    # case b_famCombinedGuard (item 3, repair round): a real strategy literally named
    # COMBINED_ALPHA_1_0.py (never a book) must not be swept into BOOK by _canonFam. The book-
    # name test must run on the raw string, before normalisation turns its underscore into a
    # space and manufactures a word boundary the raw name never has.
    r = cases.get('b_famCombinedGuard', {})
    cg_chk = {
        'renders OK': r.get('call') == 'OK',
        "a real strategy literally named COMBINED_... is not folded into BOOK": 'BOOK' not in (r.get('chips') or []),
    }
    cg_ok = all(cg_chk.values())
    line('b_famCombinedGuard', cg_ok, 'failed=%s | chips=%s' % ([k for k, v in cg_chk.items() if not v], r.get('chips')))
    if not cg_ok:
        fail('b_famCombinedGuard: see the b_famCombinedGuard line')
    # case c_pool: item 2 - CONFIG row PF pools across ticked stretches; DRAWDOWN dashes
    r = cases.get('c_pool', {})
    pf_is_lb, pf_is, pf_lb = r.get('pfIsLb'), r.get('pfIs'), r.get('pfLb')
    c_pool_chk = {
        'renders OK': r.get('call') == 'OK',
        'IS+LB PF sits strictly between the IS and LB figures': (
            pf_is_lb is not None and pf_lb is not None and pf_is is not None
            and min(pf_lb, pf_is) < pf_is_lb < max(pf_lb, pf_is)),
        'IS+LB DRAWDOWN dashes': bool(r.get('ddDashedIsLb')),
        'IS alone is unchanged (still has its own drawdown)': bool(r.get('ddShownIs')),
    }
    c_pool_ok = all(c_pool_chk.values())
    line('c_pool', c_pool_ok, 'failed=%s | pfIsLb=%s pfIs=%s pfLb=%s | tip=%r'
         % ([k for k, v in c_pool_chk.items() if not v], pf_is_lb, pf_is, pf_lb, r.get('tipIsLb')))
    if not c_pool_ok:
        fail('c_pool: a CONFIG row under IS+LB should pool PF between its IS and LB figures and dash DRAWDOWN -- see the c_pool line')
    # case c_hover: item 8 - the point hover names both measures, not just MAR / profit
    r = cases.get('c_hover', {})
    c_hover_chk = {
        'renders OK': r.get('call') == 'OK',
        'names WIN % on the vertical value': bool(r.get('hasWinLabel')),
        'names Sortino on the horizontal value': bool(r.get('hasSortinoLabel')),
        'WIN % is not mislabeled profit': not r.get('mislabeledProfit'),
    }
    c_hover_ok = all(c_hover_chk.values())
    line('c_hover', c_hover_ok, 'failed=%s | tip=%r' % ([k for k, v in c_hover_chk.items() if not v], r.get('tip')))
    if not c_hover_ok:
        fail('c_hover: the point hover should name WIN % and SORTINO, not label WIN % as profit -- see the c_hover line')
    # case c_hidedot: item 4 - right-click hides a point via a chart-only redraw; SHOW ALL
    #   restores it; the table row count never moves
    r = cases.get('c_hidedot', {})
    pts0, pts1, pts2 = r.get('pts0'), r.get('pts1'), r.get('pts2')
    c_hidedot_chk = {
        'renders OK': r.get('call') == 'OK',
        'fixture has at least 2 points': (pts0 or 0) >= 2,
        'no SHOW ALL chip before any hide': not r.get('chipBefore'),
        'the hidden point carried a data-rehide key': bool(r.get('hkPresent')),
        'point count drops by exactly one after the hide': (None not in (pts0, pts1)) and (pts1 == pts0 - 1),
        'SHOW ALL chip appears after the hide': bool(r.get('chipAfter')),
        'table row count is unchanged by a chart-only hide': r.get('rows1') == r.get('rows0'),
        "the hidden point's own key is gone from the chart": not r.get('hkStillThere'),
        'point count is restored after clicking SHOW ALL': (None not in (pts0, pts2)) and (pts2 == pts0),
        'the chip clears itself once nothing is hidden': not r.get('chipAfterUnhide'),
        'no console errors': not r.get('errorsAfter'),
        'no uncaught exceptions': not r.get('uncaughtAfter'),
    }
    c_hidedot_ok = all(c_hidedot_chk.values())
    line('c_hidedot', c_hidedot_ok, 'failed=%s | pts0=%s pts1=%s pts2=%s rows0=%s rows1=%s'
         % ([k for k, v in c_hidedot_chk.items() if not v], pts0, pts1, pts2, r.get('rows0'), r.get('rows1')))
    if not c_hidedot_ok:
        fail('c_hidedot: right-click-to-hide should drop the point count by one, show the SHOW ALL chip, '
             'leave the table row count unchanged, and restore the point on click -- see the c_hidedot line')
    # case c_qual: item 11(a) - QUALITY preset matches its own description
    r = cases.get('c_qual', {})
    c_qual_chk = {
        'preset button exists': bool(r.get('btnFound')),
        'click sets vertical EV R': r.get('axisAfter') == 'evr',
        'click sets horizontal Sortino': r.get('xAxisAfter') == 'so',
        'button lights when its own axes are applied': bool(r.get('litWhenApplied')),
    }
    c_qual_ok = all(c_qual_chk.values())
    line('c_qual', c_qual_ok, 'failed=%s | axis=%s xAxis=%s' % ([k for k, v in c_qual_chk.items() if not v], r.get('axisAfter'), r.get('xAxisAfter')))
    if not c_qual_ok:
        fail('c_qual: the QUALITY preset should set vertical EV R / horizontal Sortino to match its own description -- see the c_qual line')
    # case c_mintrd: item 11(e) - MIN TRADES no longer double-counts a no-trade-count row
    r = cases.get('c_mintrd', {})
    plotted, skip_n, fail_out, thin_out, thin_no_ct, n_off = (
        r.get('plotted'), r.get('skip'), r.get('failOut'), r.get('thinOut'), r.get('thinNoCt'), r.get('nOff'))
    expect = (plotted + skip_n + fail_out + thin_out) if None not in (plotted, skip_n, fail_out, thin_out) else None
    c_mintrd_chk = {
        'renders OK': r.get('call') == 'OK',
        'a no-trade-count row exists to exercise the bug': (thin_no_ct or 0) > 0,
        'the headline count equals plotted + skipped + failed + thin (no double count)': expect is not None and n_off == expect,
    }
    c_mintrd_ok = all(c_mintrd_chk.values())
    line('c_mintrd', c_mintrd_ok, 'failed=%s | plotted=%s skip=%s failOut=%s thinOut=%s thinNoCt=%s nOff=%s expect=%s'
         % ([k for k, v in c_mintrd_chk.items() if not v], plotted, skip_n, fail_out, thin_out, thin_no_ct, n_off, expect))
    if not c_mintrd_ok:
        fail('c_mintrd: MIN TRADES should not double-count a no-trade-count row in the "rows plotted" headline -- see the c_mintrd line')
    # case c_champmsg: item 11(c), repair round - the chart's OWN CHAMPION-mode note names
    # the two measures actually on the axes instead of always saying money / drawdown
    r = cases.get('c_champmsg', {})
    c_champmsg_chk = {
        'renders OK': r.get('call') == 'OK',
        'the note was found (CHAMPION mode is on)': bool(r.get('hint')),
        'no longer says "the money it added and the drawdown it added"': not r.get('saysMoneyDrawdown'),
        'says "the difference it added against it on the two measures now on the axes"': bool(r.get('saysDifference')),
        'names the correct better corner for WIN % up / SORTINO across (up and to the right)': bool(r.get('saysUpRight')),
    }
    c_champmsg_ok = all(c_champmsg_chk.values())
    line('c_champmsg', c_champmsg_ok, 'failed=%s | hint=%r' % ([k for k, v in c_champmsg_chk.items() if not v], r.get('hint')))
    if not c_champmsg_ok:
        fail('c_champmsg: the chart\'s own CHAMPION-mode note should name the two measures actually on the axes, not always money / drawdown -- see the c_champmsg line')
    # == review-round regression cases (r_*) ==
    # case r_fullPfExact (R-A1): FULL PF of a run with no walk-forward and no lockbox is exact
    r = cases.get('r_fullPfExact', {})
    ck = {
        'renders OK': r.get('call') == 'OK' and not r.get('uncaught'),
        'LEADERBOARD FULL PF prints 1.55 without ~': r.get('pfTxt') == '1.55',
    }
    ok = all(ck.values())
    line('r_fullPfExact', ok, 'failed=%s | pfTxt=%r' % ([k for k, v in ck.items() if not v], r.get('pfTxt')))
    if not ok:
        fail('r_fullPfExact: see the r_fullPfExact line')

    # case r_starApply (R-A2): starred-runs reads cannot wipe or roll back a good list
    r = cases.get('r_starApply', {})
    res = r.get('res') or {}
    ck = {
        'the starred-list apply step exists': r.get('call') == 'OK' and not res.get('missing') and bool(res),
        'a failed read after a good one keeps the good list': res.get('afterFail') == ['g1'] and res.get('fail2') is False,
        'a late older read does not overwrite a newer one': res.get('afterLate') == ['g3'] and res.get('late2') is False,
    }
    ok = all(ck.values())
    line('r_starApply', ok, 'failed=%s | res=%s call=%s' % ([k for k, v in ck.items() if not v], res, str(r.get('call'))[:200]))
    if not ok:
        fail('r_starApply: see the r_starApply line')

    # case r_lbZeroTrades (R-A3 + B1): zero-trade lockbox on OVERLAY and RUNBOARD LB
    r = cases.get('r_lbZeroTrades', {})
    ids = r.get('colIds') or []
    ck = {
        'renders OK': r.get('ovlCall') == 'OK' and r.get('rbCall') == 'OK',
        'OVERLAY TRADES reads 0 for the zero-trade lockbox': r.get('ovlTr') == '0',
        'RUNBOARD shows both runs': len(ids) == 2 and r.get('zId') in ids and r.get('nId') in ids,
        'the normal run heads the board (crown column)': bool(ids) and ids[0] == r.get('nId'),
        'the zero-trade TOTAL is a dash': r.get('zNetTxt') == u'\u2014',
        'the dash says why': 'took no trades in the lockbox' in str(r.get('zNetTitle') or ''),
        'the zero-trade DD is a dash, not $0': r.get('zDdTxt') == u'\u2014',
        'the zero-trade TRADES reads 0': r.get('zTrTxt') == '0',
        'the normal run holds the TOTAL and DD best marks': bool(r.get('nNetBest')) and bool(r.get('nDdBest'))
            and not r.get('zNetBest') and not r.get('zDdBest'),
    }
    ok = all(ck.values())
    line('r_lbZeroTrades', ok, 'failed=%s | %s' % ([k for k, v in ck.items() if not v], r))
    if not ok:
        fail('r_lbZeroTrades: see the r_lbZeroTrades line')

    # case r_trdSumAll3 (R-C1): all three stretches ticked, no FULL block -> TRADES is the sum
    r = cases.get('r_trdSumAll3', {})
    ck = {
        'renders OK': r.get('call') == 'OK',
        'the fixture row really has no FULL block': r.get('hasFull') is False and r.get('expect') is not None,
        'the crowned point plotted': bool(r.get('tip')),
        'TRADES is in-sample + walk-forward + lockbox': r.get('trades') is not None and r.get('trades') == r.get('expect'),
    }
    ok = all(ck.values())
    line('r_trdSumAll3', ok, 'failed=%s | trades=%s expect=%s' % ([k for k, v in ck.items() if not v], r.get('trades'), r.get('expect')))
    if not ok:
        fail('r_trdSumAll3: see the r_trdSumAll3 line')

    # case r_pfInfLeg (R-C2, repair round 3): a no-loss stretch STORED as the engine stores it (PF null) pools
    r = cases.get('r_pfInfLeg', {})
    exp = r.get('expect')
    def _near(v):
        return v is not None and exp is not None and abs(v - exp) < 0.006
    ck = {
        'renders OK': all(r.get(k) == 'OK' for k in ('call', 'call2', 'call3')) and not r.get('unc'),
        'the fixture in-sample stretch made money (a no-loss stretch cannot lose)': r.get('isPnl') is not None and r.get('isPnl') >= 0,
        'RAW shape (PF null, no losing trade): the crowned point plotted': bool(r.get('plotted')),
        'RAW shape: the pooled PF matches gross win over gross loss': _near(r.get('pf')),
        'GATE export shape (PF null, zero drawdown, no counts): plotted with the same PF': bool(r.get('plotted2')) and _near(r.get('pf2')),
        'a null PF on a block that shows a drawdown is not read as no-loss (off the PF axis)': r.get('plotted3') is False,
    }
    ok = all(ck.values())
    line('r_pfInfLeg', ok, 'failed=%s | pf=%s pf2=%s plotted3=%s expect=%s unc=%s' % (
        [k for k, v in ck.items() if not v], r.get('pf'), r.get('pf2'), r.get('plotted3'), exp, (r.get('unc') or [])[:3]))
    if not ok:
        fail('r_pfInfLeg: see the r_pfInfLeg line')

    # case r_champBooks (B2): Past Runs CHAMPIONS keeps the stronger book
    r = cases.get('r_champBooks', {})
    ids = r.get('ids') or []
    ck = {
        'renders OK': r.get('call') == 'OK',
        'the stronger book (pre-lockbox net over drawdown) is the champion': r.get('strongId') in ids,
        'the weaker book listed first is not': r.get('weakId') not in ids,
    }
    ok = all(ck.values())
    line('r_champBooks', ok, 'failed=%s | ids=%s' % ([k for k, v in ck.items() if not v], ids))
    if not ok:
        fail('r_champBooks: see the r_champBooks line')

    # case r_pickStageDefault (B3, updated 2026-09-20): hosted PICK RUNS with no STAGE
    # saved now reads WALK-FORWARD (item 1) - LOCKBOX is no longer the default.
    r = cases.get('r_pickStageDefault', {})
    ck = {
        'renders OK': r.get('call') == 'OK',
        'WALK-FORWARD is lit': bool(r.get('wfLit')),
        'LOCKBOX is not lit': not r.get('lbLit'),
        'IN-SAMPLE is not lit': not r.get('isLit'),
    }
    ok = all(ck.values())
    line('r_pickStageDefault', ok, 'failed=%s | lb=%s is=%s btns=%s' % ([k for k, v in ck.items() if not v], r.get('lbLit'), r.get('isLit'), r.get('btns')))
    if not ok:
        fail('r_pickStageDefault: see the r_pickStageDefault line')
    # case r_zeroTrBlk (repair round): a stretch that took no trades states no ratio and no drawdown
    r = cases.get('r_zeroTrBlk', {})
    dash = u'\u2014'
    cc = r.get('cfgCells') or {}
    rz = r.get('runCellsZ') or {}
    def _cell(o, h):
        v = o.get(h)
        return (v or [None, None])
    def _dashed(o, h):
        return _cell(o, h)[0] == dash
    def _why(o, h):
        return 'took no trades in the lockbox' in str(_cell(o, h)[1] or '')
    tm = str(r.get('cfgTipMoney') or '')
    ck = {
        'renders OK': all(r.get(k) == 'OK' for k in ('cA', 'cB', 'cC', 'cD', 'cR')) and not r.get('unc'),
        'config row: other points still plot on EV R x WIN %': (r.get('cfgPts') or 0) > 0,
        'config row: no EV R / WIN % point (was EV IN R -1.00, win % 0.00)': r.get('cfgTipEvr') is None,
        'config row: the table row is there': bool(cc.get('found')),
        'config row: PF, WIN %, EV R, DRAWDOWN, MAR, SHARPE, SORTINO all dash':
            all(_dashed(cc, h) for h in ('PF', 'WIN %', 'EV R', 'DRAWDOWN', 'MAR', 'SHARPE', 'SORTINO')),
        'config row: DRAWDOWN / SHARPE / SORTINO dashes say it took no trades':
            _why(cc, 'DRAWDOWN') and _why(cc, 'SHARPE') and _why(cc, 'SORTINO'),
        'config row: TRADES reads 0': _cell(cc, 'TRADES')[0] == '0',
        'config row: LOCKBOX on money is not plotted at $0 (review round 4)': r.get('cfgTipMoney') is None and (r.get('cfgPtsMoney') or 0) > 0,
        'config row: LOCKBOX on money - its RANK dashes and says it took no trades, the other rows still rank':
            (r.get('cfgRankMoney') or [None])[0] == dash and 'took no trades in the lockbox' in str((r.get('cfgRankMoney') or [None, None])[1] or '')
            and (r.get('cfgRanked') or 0) > 0,
        'IN-SAMPLE + LOCKBOX pools to the in-sample PF':
            r.get('pfIsLb') is not None and r.get('pfIs') is not None and abs(r.get('pfIsLb') - r.get('pfIs')) < 0.006,
        'IN-SAMPLE + LOCKBOX trades equal the in-sample trades':
            r.get('trIsLb') is not None and r.get('trIsLb') == r.get('trIs'),
        'run rows: the normal run plots on the drawdown axis': r.get('runTipN') is not None,
        'run rows: the zero-trade run does not sit at $0 drawdown': r.get('runTipZ') is None,
        'run rows: its DRAWDOWN and SHARPE dash with the reason, TRADES reads 0':
            bool(rz.get('found')) and _dashed(rz, 'DRAWDOWN') and _why(rz, 'DRAWDOWN') and _dashed(rz, 'SHARPE')
            and _why(rz, 'SHARPE') and _cell(rz, 'TRADES')[0] == '0',
        'run rows, LOCKBOX on money: the empty lockbox is not plotted, the normal run is (review round 4)':
            all(r.get(k) == 'OK' for k in ('cR2', 'cR3', 'cR4')) and r.get('moneyTipZ') is None and r.get('moneyTipN') is not None,
        'run rows, LOCKBOX on money: the empty lockbox RANK dashes with the reason, the normal run ranks 1':
            (r.get('moneyRankZ') or [None])[0] == dash and 'took no trades in the lockbox' in str((r.get('moneyRankZ') or [None, None])[1] or '')
            and (r.get('moneyRankN') or [None])[0] == '1' and 'RANK 1 of 1' in str(r.get('moneyTipN') or ''),
        'run rows, LOCKBOX on ROC: the empty lockbox is neither plotted nor ranked':
            r.get('rocTipZ') is None and r.get('rocTipN') is not None and (r.get('rocRankZ') or [None])[0] == dash,
        'run rows, IN-SAMPLE + LOCKBOX on money: the lockbox $0 still adds, so it plots': r.get('isLbTipZ') is not None,
    }
    ok = all(ck.values())
    line('r_zeroTrBlk', ok, 'failed=%s | unc=%s cfgTipEvr=%r cfgCells=%s pf=%s/%s tr=%s/%s runTipZ=%r runCellsZ=%s' % (
        [k for k, v in ck.items() if not v], (r.get('unc') or [])[:3], (r.get('cfgTipEvr') or '')[:160], {k: (v[0] if isinstance(v, list) else v) for k, v in cc.items()},
        r.get('pfIsLb'), r.get('pfIs'), r.get('trIsLb'), r.get('trIs'), (r.get('runTipZ') or '')[:160],
        {k: (v[0] if isinstance(v, list) else v) for k, v in rz.items()}))
    if not ok:
        fail('r_zeroTrBlk: see the r_zeroTrBlk line')
    # case r_rawNullStretch (repair round 3): a RAW stretch saved as null (took no trades / never measured)
    r = cases.get('r_rawNullStretch', {})
    dash = u'—'
    def _c(o, h):
        return ((o or {}).get(h) or [None, None])
    aL, bL, bB = r.get('aLb') or {}, r.get('bLb') or {}, r.get('bIsLb') or {}
    gates = r.get('gates') or []
    ck = {
        'renders OK': all(r.get(k) == 'OK' for k in ('a1', 'a2', 'a3', 'b1', 'b2', 'c1')) and not r.get('unc'),
        'the fixture row counts its whole window apart from its in-sample':
            r.get('wholeTrd') is not None and r.get('isTrd') is not None and r.get('wholeTrd') != r.get('isTrd'),
        '(a) empty lockbox: the row is on the table': bool(r.get('aFound')),
        '(a) LOCKBOX ticked: TRADES reads 0': _c(aL, 'TRADES')[0] == '0',
        '(a) LOCKBOX ticked: PF, WIN %, EV R, R / YR dash': all(_c(aL, h)[0] == dash for h in ('PF', 'WIN %', 'EV R', 'R / YR')),
        '(a) LOCKBOX ticked: DRAWDOWN dashes because it took no trades in the lockbox':
            _c(aL, 'DRAWDOWN')[0] == dash and 'took no trades in the lockbox' in str(_c(aL, 'DRAWDOWN')[1] or ''),
        '(a) IN-SAMPLE + LOCKBOX pools to the in-sample PF':
            r.get('aPfIsLb') is not None and r.get('aPfIs') is not None and abs(r.get('aPfIsLb') - r.get('aPfIs')) < 0.006,
        '(a) IN-SAMPLE + LOCKBOX counts the in-sample trades':
            r.get('aTrIsLb') is not None and r.get('aTrIsLb') == r.get('aTrIs') == r.get('isTrd'),
        '(b) never-measured lockbox: the row is on the table': bool(r.get('bFound')),
        '(b) LOCKBOX ticked: TRADES dashes and says the lockbox count was not saved':
            _c(bL, 'TRADES')[0] == dash and 'saved no trade count for its lockbox' in str(_c(bL, 'TRADES')[1] or ''),
        '(b) LOCKBOX ticked: TRADES / YR, EV R, R / YR dash': all(_c(bL, h)[0] == dash for h in ('TRADES / YR', 'EV R', 'R / YR')),
        '(b) IN-SAMPLE + LOCKBOX: TRADES, TRADES / YR, EV R, R / YR dash':
            all(_c(bB, h)[0] == dash for h in ('TRADES', 'TRADES / YR', 'EV R', 'R / YR')),
        '(c) GATE rows with no lockbox block are on the table': len(gates) > 0,
        '(c) every one dashes TRADES (never its pre-lockbox count)': len(gates) > 0 and all((g or [None])[0] == dash for g in gates),
    }
    ok = all(ck.values())
    line('r_rawNullStretch', ok, 'failed=%s | unc=%s whole=%s is=%s aLb=%s pf=%s/%s tr=%s/%s bLb=%s bIsLb=%s gates=%s' % (
        [k for k, v in ck.items() if not v], (r.get('unc') or [])[:3], r.get('wholeTrd'), r.get('isTrd'),
        {k: (v[0] if isinstance(v, list) else v) for k, v in aL.items()}, r.get('aPfIsLb'), r.get('aPfIs'), r.get('aTrIsLb'), r.get('aTrIs'),
        {k: (v[0] if isinstance(v, list) else v) for k, v in bL.items()}, {k: (v[0] if isinstance(v, list) else v) for k, v in bB.items()},
        [(g or [None])[0] for g in gates][:6]))
    if not ok:
        fail('r_rawNullStretch: see the r_rawNullStretch line')

    # case r_runZeroStretch (repair round 3): run rows - an empty lockbox or fold, or a no-loss fold, keeps IN-SAMPLE
    r = cases.get('r_runZeroStretch', {})
    ri, rwf = r.get('is') or {}, r.get('wf') or {}
    def _v(o, s, h):
        return (((o or {}).get(s) or {}).get(h) or [None, None])
    def _fig(o, s, h):
        return _v(o, s, h)[0] not in (None, dash, '')
    Zs, Z0s, Ws, NLs, Bs = 'ZZERO_TR_1_0.py', 'ZZEROB_1_0.py', 'ZFOLD0_1_0.py', 'ZFOLDWIN_1_0.py', 'ZOVERLAP_1_0.py'
    H4 = ('IN-SAMPLE', 'PF', 'WIN %', 'TRADES')
    ck = {
        'renders OK': r.get('cIs') == 'OK' and r.get('cWf') == 'OK' and not r.get('unc'),
        'the fixture has walk-forward folds': (r.get('nFolds') or 0) > 1,
        'all five run rows are on the table': all(ri.get(s) for s in (Zs, Z0s, Ws, NLs, Bs)),
        '(Z) empty lockbox, no averages saved: IN-SAMPLE, PF, WIN %, TRADES are figures': all(_fig(ri, Zs, h) for h in H4),
        '(Z) reads exactly like the same run with its averages saved as 0': all(_v(ri, Zs, h)[0] == _v(ri, Z0s, h)[0] for h in H4),
        '(W) one fold with no trades: IN-SAMPLE, PF, WIN %, TRADES are figures': all(_fig(ri, Ws, h) for h in H4),
        '(W) WALK-FWD ticked: its PF is a figure': _fig(rwf, Ws, 'PF'),
        '(NL) a fold whose every trade won: IN-SAMPLE, PF, WIN %, TRADES are figures': all(_fig(ri, NLs, h) for h in H4),
        '(NL) WALK-FWD ticked: its PF is a figure': _fig(rwf, NLs, 'PF'),
        '(B) a run with no measured in-sample slice dashes IN-SAMPLE': _v(ri, Bs, 'IN-SAMPLE')[0] == dash,
        '(B) its TRADES dash names the true reason, not the old overlap or studies-registry ones':
            _v(ri, Bs, 'TRADES')[0] == dash and 'measured' in str(_v(ri, Bs, 'TRADES')[1] or '')
            and 'overlap' not in str(_v(ri, Bs, 'TRADES')[1] or '')
            and 'studies registry' not in str(_v(ri, Bs, 'TRADES')[1] or ''),
    }
    # review round 4: an all-loss fold, an all-loss lockbox and an all-win lockbox read exactly like controls whose
    #   grosses can be split; a fold that broke exactly even dashes only PF and EV R, and names the fold
    rpre, rlb = r.get('pre') or {}, r.get('lb') or {}
    H5 = H4 + ('EV R',)
    PAIRS = (('ZALLLOSS_1_0.py', 'ZALLLOSSC_1_0.py'), ('ZLBLOSS_1_0.py', 'ZLBLOSSC_1_0.py'), ('ZLBWIN_1_0.py', 'ZLBWINC_1_0.py'))
    P1s = 'ZPFONE_1_0.py'
    p1f = r.get('p1Fold')
    def _p1why(o, h):
        t = str(_v(o, P1s, h)[1] or '')
        return ('fold %s ' % p1f) in t and 'broke exactly even' in t and 'overlap' not in t
    ck.update({
        'renders OK (IN-SAMPLE + WALK-FWD, LOCKBOX)': r.get('cPre') == 'OK' and r.get('cLb') == 'OK',
        'the new run rows are on the table': all(ri.get(s) for p in PAIRS for s in p) and bool(ri.get(P1s)),
        '(AL/LL/LW) IN-SAMPLE ticked: IN-SAMPLE, PF, WIN %, TRADES, EV R are figures':
            all(_fig(ri, s, h) for s, _c0 in PAIRS for h in H5),
        '(AL/LL/LW) IN-SAMPLE ticked: each reads exactly like its control':
            all(_v(ri, s, h)[0] == _v(ri, c0, h)[0] for s, c0 in PAIRS for h in H5),
        '(AL/LL/LW) IN-SAMPLE + WALK-FWD ticked: each reads exactly like its control, with figures':
            all(_fig(rpre, s, h) and _v(rpre, s, h)[0] == _v(rpre, c0, h)[0] for s, c0 in PAIRS for h in H5),
        '(AL) WALK-FWD ticked: PF and EV R are figures, equal to the control':
            all(_fig(rwf, 'ZALLLOSS_1_0.py', h) and _v(rwf, 'ZALLLOSS_1_0.py', h)[0] == _v(rwf, 'ZALLLOSSC_1_0.py', h)[0] for h in ('PF', 'EV R')),
        '(LL) LOCKBOX ticked: an all-loss lockbox reads PF 0.00 like its control':
            _v(rlb, 'ZLBLOSS_1_0.py', 'PF')[0] == '0.00' and _v(rlb, 'ZLBLOSSC_1_0.py', 'PF')[0] == '0.00',
        '(P1) the fixture fold number is known': p1f is not None,
        '(P1) IN-SAMPLE ticked: IN-SAMPLE, WIN %, TRADES are figures': all(_fig(ri, P1s, h) for h in ('IN-SAMPLE', 'WIN %', 'TRADES')),
        '(P1) IN-SAMPLE ticked: PF and EV R are figures too - a walk-forward fold breaking even cannot leak into a slice that never reads the fold rows':
            all(_fig(ri, P1s, h) for h in ('PF', 'EV R')),
        '(P1) WALK-FWD ticked: WIN % and TRADES are figures, PF and EV R dash naming the fold':
            all(_fig(rwf, P1s, h) for h in ('WIN %', 'TRADES')) and all(_v(rwf, P1s, h)[0] == dash and _p1why(rwf, h) for h in ('PF', 'EV R')),
        '(P1) IN-SAMPLE + WALK-FWD ticked: TRADES a figure, PF dashes naming the fold':
            _fig(rpre, P1s, 'TRADES') and _v(rpre, P1s, 'PF')[0] == dash and _p1why(rpre, 'PF'),
    })
    ok = all(ck.values())
    line('r_runZeroStretch', ok, 'failed=%s | unc=%s is=%s wfPF=%s p1=%s' % (
        [k for k, v in ck.items() if not v], (r.get('unc') or [])[:3],
        {s: {h: _v(ri, s, h)[0] for h in H5} for s in (Zs, Z0s, Ws, NLs, Bs) + tuple(s for p in PAIRS for s in p) + (P1s,)},
        {s: _v(rwf, s, 'PF')[0] for s in (Ws, NLs, 'ZALLLOSS_1_0.py', 'ZALLLOSSC_1_0.py')},
        {h: (_v(ri, P1s, h)[1] or '')[:90] for h in ('PF', 'EV R')}))
    if not ok:
        fail('r_runZeroStretch: see the r_runZeroStretch line')
    # case e1_colorder: item 14 -- RANK / FAMILY / RUN lead, CONFIG is last, both column modes
    r = cases.get('e1_colorder', {})
    e1c_chk = {
        'KEY renders OK': r.get('call') == 'OK',
        'ALL renders OK': r.get('allCall') == 'OK',
        'KEY header starts RANK, FAMILY, RUN': r.get('keyHdr') == ['RANK', 'FAMILY', 'RUN'],
        'ALL header starts RANK, FAMILY, RUN': r.get('allHdr') == ['RANK', 'FAMILY', 'RUN'],
        'KEY header ends CONFIG': r.get('keyHdrLast') == 'CONFIG',
        'ALL header ends CONFIG': r.get('allHdrLast') == 'CONFIG',
        'KEY last cell is the CONFIG cell': bool(r.get('keyLastIsConfig')),
        'ALL last cell is the CONFIG cell': bool(r.get('allLastIsConfig')),
        'KEY has rows to check': (r.get('keyRows') or 0) > 0,
        'ALL has rows to check': (r.get('allRows') or 0) > 0,
        'KEY cells align with headers (no misaligned rows)': r.get('keyBad') == 0,
        'ALL cells align with headers (no misaligned rows)': r.get('allBad') == 0,
    }
    e1c_ok = all(e1c_chk.values())
    line('e1_colorder', e1c_ok, 'KEY hdr=%s..%s (rows=%s bad=%s) | ALL hdr=%s..%s (n=%s rows=%s bad=%s)'
         % (r.get('keyHdr'), r.get('keyHdrLast'), r.get('keyRows'), r.get('keyBad'),
            r.get('allHdr'), r.get('allHdrLast'), r.get('allN'), r.get('allRows'), r.get('allBad')))
    if not e1c_ok:
        fail('e1_colorder: item 14 column order broke -- failed %s -- see the e1_colorder line'
             % [k for k, v in e1c_chk.items() if not v])
    # case e1_scroll: item 15(a) -- scroll position survives an unrelated re-render, resets on LEVEL
    r = cases.get('e1_scroll', {})
    e1s_chk = {
        'first render OK': r.get('call') == 'OK',
        'axis re-render OK': r.get('call2') == 'OK',
        'level re-render OK': r.get('call3') == 'OK',
        'a scroll box was found': bool(r.get('foundBox')),
        'the test setup could actually scroll it': (r.get('setLeft') or 0) > 0 and (r.get('setTop') or 0) > 0,
        'an unrelated pref change (axis) keeps scrollLeft': r.get('afterAxisLeft') == r.get('setLeft'),
        'an unrelated pref change (axis) keeps scrollTop': r.get('afterAxisTop') == r.get('setTop'),
        'a LEVEL change resets scrollLeft to 0': r.get('afterLevelLeft') == 0,
        'a LEVEL change resets scrollTop to 0': r.get('afterLevelTop') == 0,
    }
    e1s_ok = all(e1s_chk.values())
    line('e1_scroll', e1s_ok, 'set=(%s,%s) afterAxis=(%s,%s) afterLevel=(%s,%s)'
         % (r.get('setLeft'), r.get('setTop'), r.get('afterAxisLeft'), r.get('afterAxisTop'),
            r.get('afterLevelLeft'), r.get('afterLevelTop')))
    if not e1s_ok:
        fail('e1_scroll: item 15(a) scroll memory broke -- failed %s -- see the e1_scroll line'
             % [k for k, v in e1s_chk.items() if not v])
    # case e1_split: item 15(b) -- SPLIT tables column bounded to the viewport, header sticky
    r = cases.get('e1_split', {})
    e1sp_chk = {
        'renders OK': r.get('call') == 'OK',
        'more than one study tile is open (the scenario the bug needs)': (r.get('openTiles') or 0) > 1,
        'the split tables column was found': bool(r.get('found')),
        "its rendered height fits inside the viewport": (r.get('height') if r.get('height') is not None else 999999) <= (r.get('innerHeight') or 0),
        'it actually sets a max-height (not left unbounded)': bool(r.get('maxHeightStyle')),
        'its own overflow is scrollable': r.get('overflow') in ('auto', 'scroll'),
        'the table header stays sticky while the table scrolls': r.get('thPos') == 'sticky',
        '(E1b) the column could be scrolled for the test': (r.get('colRoom') or 0) > 120 and r.get('colSetTop') == 120,
        '(E1b) the column keeps its scrollTop across an unrelated re-render': r.get('call2') == 'OK' and r.get('colAfterAxisTop') == r.get('colSetTop'),
    }
    e1sp_ok = all(e1sp_chk.values())
    line('e1_split', e1sp_ok, 'openTiles=%s height=%s innerHeight=%s maxHeightStyle=%r overflow=%r thPos=%r colRoom=%s colSetTop=%s colAfterAxisTop=%s'
         % (r.get('openTiles'), r.get('height'), r.get('innerHeight'), r.get('maxHeightStyle'), r.get('overflow'), r.get('thPos'),
            r.get('colRoom'), r.get('colSetTop'), r.get('colAfterAxisTop')))
    if not e1sp_ok:
        fail('e1_split: item 15(b) SPLIT layout height bound broke -- failed %s -- see the e1_split line'
             % [k for k, v in e1sp_chk.items() if not v])
    # case e1_sticky (E1b): RANK / FAMILY / RUN body cells pinned under their headers, opaque, whole header row on top
    r = cases.get('e1_sticky', {})
    rs = r.get('res') or {}
    cl, hl = rs.get('cellL') or [], rs.get('headL') or []
    clear = 'rgba(0, 0, 0, 0)'
    e1k_chk = {
        'renders OK': r.get('call') == 'OK',
        'a table box was found and scrolled both ways': bool(rs.get('found')) and (rs.get('sx') or 0) > 0 and (rs.get('sy') or 0) > 0,
        'RANK / FAMILY / RUN body cells are position:sticky': rs.get('cellPos') == ['sticky', 'sticky', 'sticky'],
        'RANK body cell is pinned at the left edge': len(cl) == 3 and 0 <= cl[0] <= 1,
        'each pinned body cell sits under its own pinned header': len(cl) == 3 and cl == hl,
        'the pinned cells keep their order (no overlap)': len(cl) == 3 and cl[0] < cl[1] < cl[2],
        'the first KPI cell scrolled under them': len(cl) == 3 and rs.get('kpiL') is not None and rs.get('kpiL') < cl[2],
        'pinned body cells have an opaque fill': len(rs.get('cellBg') or []) == 3 and clear not in rs.get('cellBg'),
        'pinned headers have an opaque fill': len(rs.get('headBg') or []) == 3 and clear not in rs.get('headBg'),
        'every heading stays at the top of the box': (rs.get('offTop') == []) and bool(rs.get('hdrTops')),
    }
    e1k_ok = all(e1k_chk.values())
    line('e1_sticky', e1k_ok, 'scroll=(%s,%s) cellL=%s headL=%s kpiL=%s pos=%s cellBg=%s headBg=%s offTop=%s'
         % (rs.get('sx'), rs.get('sy'), cl, hl, rs.get('kpiL'), rs.get('cellPos'), rs.get('cellBg'), rs.get('headBg'), rs.get('offTop')))
    if not e1k_ok:
        fail('e1_sticky: the identifying columns or the header row do not stay put -- failed %s -- see the e1_sticky line'
             % [k for k, v in e1k_chk.items() if not v])
    # case e2_causes: item 12 - the note breaks off-chart rows down by cause with
    # counts, offers a working PLOT FAILURES ON button, and an offered
    # alternative's count matches the plotted count after actually switching to it.
    r = cases.get('e2_causes', {})
    causeA = r.get('causeA') or {}
    causeB1 = r.get('causeB1') or {}
    evr_offer = r.get('evrOffer') or {}
    e2c_chk = {
        'renders OK': r.get('call') == 'OK',
        'note found (mentions "not on this chart")': 'not on this chart' in (r.get('noteText') or ''),
        'the PLOT FAILURES ON button is in the note': bool(r.get('failBtnFound')),
        'at least one row is hidden as a failure before the click': (causeA.get('fail') or 0) >= 1,
        'at least one row is missing a figure on this stage': ((causeA.get('missBoth') or 0) + (causeA.get('missX') or 0) + (causeA.get('missY') or 0)) >= 1,
        'the missing-figure cause names the real reason (no WF money)': 'no WF money recorded' in (r.get('noteText') or ''),
        'the run is not plotted before the click': r.get('myPointBefore') is False,
        "clicking the note's PLOT FAILURES ON plots the run": r.get('myPointAfter') is True,
        "the plotted run's own PF and ROC read back what it saved": r.get('myPf') == '1.35' and str(r.get('myRoc') or '').startswith('34.4'),
        'part B renders OK': r.get('callB1') == 'OK' and r.get('callB2') == 'OK',
        'the controlled fixture starts fully off the chart, missing Sortino': causeB1.get('plotted') == 0 and causeB1.get('missY') == 3,
        'EV R is offered as an alternative with an honest count': evr_offer.get('m') == 'evr' and evr_offer.get('n') == 3,
        "the offered alternative's count equals the plotted count after switching": evr_offer.get('n') is not None and r.get('plottedAfterSwitch') == evr_offer.get('n'),
    }
    e2c_ok = all(e2c_chk.values())
    line('e2_causes', e2c_ok, 'failed=%s | causeA=%s | myBefore=%s myAfter=%s myPf=%s myRoc=%s | causeB1=%s evrOffer=%s plottedAfterSwitch=%s'
         % ([k for k, v in e2c_chk.items() if not v], causeA, r.get('myPointBefore'), r.get('myPointAfter'),
            r.get('myPf'), r.get('myRoc'), causeB1, evr_offer, r.get('plottedAfterSwitch')))
    if not e2c_ok:
        fail('e2_causes: the not-on-chart note should break off-chart rows down by cause with a working PLOT FAILURES ON button and honestly-counted alternatives -- see the e2_causes line')

    # case e2_wryears: item 13 - a write-up under a partial tick dashes its
    # per-year figures with the real reason instead of dividing a stretch's
    # money by the row's whole window; ticking every recorded stretch still works.
    r = cases.get('e2_wryears', {})
    lb = r.get('lbOnly') or {}
    allt = r.get('allTicked') or {}
    dash = chr(0x2014)
    e2y_chk = {
        'renders OK': r.get('call') == 'OK',
        'the row was found both times': bool(lb.get('found')) and bool(allt.get('found')),
        'LOCKBOX alone dashes ROC % / YR': lb.get('text') == dash,
        'the dash names the real reason': 'records one window for the whole row' in (lb.get('title') or ''),
        'all three stretches ticked shows a number': bool(re.match(r'^-?[0-9.]+%$', str(allt.get('text') or ''))),
    }
    e2y_ok = all(e2y_chk.values())
    line('e2_wryears', e2y_ok, 'failed=%s | lbOnly=%s | allTicked=%s'
         % ([k for k, v in e2y_chk.items() if not v], lb, allt))
    if not e2y_ok:
        fail('e2_wryears: a write-up under a partial tick should dash ROC % / YR with the real reason, not divide a stretch by the whole row -- see the e2_wryears line')

    # case e2_zerocause (E2b): an empty ticked stretch is its own cause in the note, never
    # "records no <measure>", and offers no switch.
    r = cases.get('e2_zerocause', {})
    zc = r.get('cause') or {}
    zci = r.get('causeIs') or {}
    zt = r.get('noteText') or ''
    e2z_chk = {
        'renders OK': r.get('call') == 'OK' and r.get('callIs') == 'OK',
        'the empty-lockbox run is off the chart, the other run is on it': r.get('zPt') is False and r.get('nPt') is True,
        'the tally counts exactly one row as took-no-trades': zc.get('zero') == 1,
        'that row is not also counted as missing a figure': (zc.get('missBoth') or 0) + (zc.get('missX') or 0) + (zc.get('missY') or 0) == 0,
        'the note names the cause in plain words': 'took no trades in the lockbox' in zt,
        'the note does not call it a missing measure': ('record neither' not in zt) and ('record no ' not in zt),
        'no switch is offered for it': r.get('noteBtns') == 0,
        'IN-SAMPLE ticked (it traded there): no such cause': (zci.get('zero') or 0) == 0,
    }
    e2z_ok = all(e2z_chk.values())
    line('e2_zerocause', e2z_ok, 'failed=%s | cause=%s | note=%r btns=%s zPt=%s nPt=%s | causeIs.zero=%s'
         % ([k for k, v in e2z_chk.items() if not v], zc, zt[:220], r.get('noteBtns'), r.get('zPt'), r.get('nPt'), zci.get('zero')))
    if not e2z_ok:
        fail('e2_zerocause: the note under the chart should name a ticked stretch with no trades as its own cause -- see the e2_zerocause line')

    # ---- REPAIR ROUND 4 (patch_R4.py) ----------------------------------------------------------
    dash = chr(0x2014)

    # case r4_wrwhole
    r = cases.get('r4_wrwhole', {})
    lbL, allL, isL, lbN = (r.get('lbL') or {}), (r.get('allL') or {}), (r.get('isL') or {}), (r.get('lbN') or {})
    r4w_chk = {
        'renders OK': r.get('call') == 'OK',
        'row 1741 found on every render': all(x.get('found') for x in (lbL, allL, isL, lbN)),
        'TRADES / YR is a number, not the whole-run count': bool(re.match(r'^[0-9][0-9,.]*$', str(allL.get('tpy') or ''))) and allL.get('tpy') != allL.get('trd'),
        'TRADES / YR on LOCKBOX (run loaded) equals all three stretches': lbL.get('tpy') == allL.get('tpy'),
        'TRADES / YR on IN-SAMPLE (run loaded) equals all three stretches': isL.get('tpy') == allL.get('tpy'),
        'TRADES / YR on LOCKBOX with the run not loaded is the same number, not a dash': lbN.get('tpy') == allL.get('tpy'),
        'no write-up partial-tick reason on TRADES / YR': 'records one window' not in (lbN.get('tpyTip') or ''),
        'R / YR column on LOCKBOX equals all three stretches': bool(allL.get('rpy')) and allL.get('rpy') != dash and lbL.get('rpy') == allL.get('rpy'),
        'R / YR chart axis on LOCKBOX equals all three stretches': allL.get('axis') is not None and lbL.get('axis') == allL.get('axis'),
        'LOCKBOX ROC % / YR is still dated off the loaded run': bool(re.match(r'^-?[0-9.]+%$', str(lbL.get('roc') or ''))),
        'IN-SAMPLE ROC % / YR is never dated off the run (dash)': isL.get('roc') == dash,
        'that dash names the write-up reason': 'records one window for the whole row' in (isL.get('rocTip') or ''),
    }
    r4w_ok = all(r4w_chk.values())
    line('r4_wrwhole', r4w_ok, 'failed=%s | lbLoaded=%s | allLoaded=%s | isLoaded=%s | lbNotLoaded=%s'
         % ([k for k, v in r4w_chk.items() if not v],
            {k: lbL.get(k) for k in ('trd', 'tpy', 'rpy', 'roc', 'axis')}, {k: allL.get(k) for k in ('trd', 'tpy', 'rpy', 'roc', 'axis')},
            {k: isL.get(k) for k in ('tpy', 'rpy', 'roc')}, {k: lbN.get(k) for k in ('tpy', 'rpy', 'roc')}))
    if not r4w_ok:
        fail('r4_wrwhole: a write-up citing a loaded run must keep whole-row TRADES / YR and R / YR on every tick -- see the r4_wrwhole line')

    # case r4_wfpool
    r = cases.get('r4_wfpool', {})
    r4p_chk = {
        'renders OK': r.get('call') == 'OK',
        'LEADERBOARD WF PF pools the all-loss fold (1.54)': (r.get('leadPfA') or [None])[0] == '1.54',
        'EXPLORE WF PF agrees': r.get('expPf') == '1.54',
        'LEADERBOARD WF R / YR equals EXPLORE': (r.get('leadRpyA') or [None])[0] == '0.8' and r.get('expRpy') == '0.8R',
        'a fold that broke exactly even leaves LEADERBOARD WF PF unknown': not re.match(r'^[0-9]', str((r.get('leadPfB') or [''])[0])),
    }
    r4p_ok = all(r4p_chk.values())
    line('r4_wfpool', r4p_ok, 'failed=%s | leadPfA=%s leadRpyA=%s expPf=%s expRpy=%s leadPfB=%s'
         % ([k for k, v in r4p_chk.items() if not v], r.get('leadPfA'), r.get('leadRpyA'), r.get('expPf'), r.get('expRpy'), r.get('leadPfB')))
    if not r4p_ok:
        fail('r4_wfpool: the LEADERBOARD walk-forward PF must pool folds the way EXPLORE does -- see the r4_wfpool line')

    # case r4_failnote
    r = cases.get('r4_failnote', {})
    _m = re.search(r'PLOT FAILURES ON\D*(\d+)\s*$', str(r.get('pfBtnTxt') or ''))
    _n = int(_m.group(1)) if _m else None
    r4f_chk = {
        'renders OK': r.get('call') == 'OK',
        'default board, failures hidden: no note (only rows lacking a figure raise it)': r.get('defNote') is None,
        'placeable failures are fewer than hidden failures there': (r.get('defFail') or 0) < (r.get('defFailHidden') or 0),
        'failed run with no WF Sortino: no PLOT FAILURES ON offer': r.get('soFailBtn') is False,
        'failed run that places: PLOT FAILURES ON carries its count': _n is not None and _n == r.get('pfFail') and _n >= 1,
        'the click draws exactly that many more points': _n is not None and r.get('pfPlottedAfter') == (r.get('pfPlotted') or 0) + _n,
        'LOAD ALL counts fewer rows when no run records a WF Sortino': r.get('soOlder') is not None and r.get('pfOlder') is not None and r.get('soOlder') < r.get('pfOlder'),
        'LOAD ALL hover says the write-ups give way to run rows on this level': 'replaced by each run' in (r.get('loadTip') or ''),
    }
    r4f_ok = all(r4f_chk.values())
    line('r4_failnote', r4f_ok, 'failed=%s | defNote=%r defFail=%s/%s | soFailBtn=%s soOlder=%s | pfBtn=%r pfFail=%s pts %s->%s pfOlder=%s'
         % ([k for k, v in r4f_chk.items() if not v], r.get('defNote'), r.get('defFail'), r.get('defFailHidden'),
            r.get('soFailBtn'), r.get('soOlder'), r.get('pfBtnTxt'), r.get('pfFail'), r.get('pfPlotted'), r.get('pfPlottedAfter'), r.get('pfOlder')))
    if not r4f_ok:
        fail('r4_failnote: PLOT FAILURES ON and LOAD ALL must only claim rows they can place -- see the r4_failnote line')

    # case r4_relnote
    r = cases.get('r4_relnote', {})
    _sh = r.get('shownN')
    r4r_chk = {
        'renders OK': r.get('call') == 'OK',
        'rows with no champion figure are counted as their own cause': (r.get('rel') or 0) > 0,
        'the tally adds up to every row the chart pass read': _sh is not None and r.get('sum') == _sh,
        "the note's total is that same number": _sh is not None and str(r.get('head') or '').startswith('%s of %s' % (_sh, _sh)),
    }
    r4r_ok = all(r4r_chk.values())
    line('r4_relnote', r4r_ok, 'failed=%s | rel=%s sum=%s shownN=%s head=%r'
         % ([k for k, v in r4r_chk.items() if not v], r.get('rel'), r.get('sum'), _sh, r.get('head')))
    if not r4r_ok:
        fail('r4_relnote: CHAMPION-mode rows with nothing to read against must be counted in the note -- see the r4_relnote line')

    # case r4_offers
    r = cases.get('r4_offers', {})
    _offs = r.get('offers') or []
    _chk = [o for o in _offs if o.get('after') is not None]
    r4o_chk = {
        'renders OK': r.get('call') == 'OK',
        'something is offered': len(_offs) > 0 and len(_chk) > 0,
        'every offer beats what is plotted now': all((o.get('n') or 0) > (r.get('now') or 0) for o in _offs),
        'every checked offer holds exactly its number after the click': all(o.get('after') == o.get('n') for o in _chk),
    }
    r4o_ok = all(r4o_chk.values())
    line('r4_offers', r4o_ok, 'failed=%s | now=%s offers=%s' % ([k for k, v in r4o_chk.items() if not v], r.get('now'), _offs))
    if not r4o_ok:
        fail('r4_offers: each offer must name the rows on the chart after the switch -- see the r4_offers line')

    # case r4_tpydash
    r = cases.get('r4_tpydash', {})
    _lb, _all = (r.get('lb') or {}), (r.get('all') or {})
    r4t_chk = {
        'renders OK': r.get('call') == 'OK' and _lb.get('found') and _all.get('found'),
        'TRADES / YR shows numbers': (_all.get('num') or 0) > 0,
        'LOCKBOX shows a number on as many rows as all three stretches': _lb.get('num') == _all.get('num'),
        'book round 55 row 1733 reads the same on both': _lb.get('b55') is not None and _lb.get('b55') == _all.get('b55'),
    }
    r4t_ok = all(r4t_chk.values())
    line('r4_tpydash', r4t_ok, 'failed=%s | lb=%s | all=%s' % ([k for k, v in r4t_chk.items() if not v], _lb, _all))
    if not r4t_ok:
        fail('r4_tpydash: TRADES / YR must not dash a whole-row count under a partial stretch tick -- see the r4_tpydash line')

    # ---- REVIEW ROUND 5 (patch_R4.py R4-5 .. R4-9) --------------------------------------------
    dash5 = chr(0x2014)

    # case r5_rawpre
    r = cases.get('r5_rawpre', {})
    _rp = r.get('res') or {}
    _iw, _is, _il = (_rp.get('is+wf') or {}), (_rp.get('is') or {}), (_rp.get('is+lb') or {})
    r5r_chk = {
        'renders OK': r.get('call') == 'OK',
        'the RAW row was found on every tick': all(x.get('found') for x in (_iw, _is, _il)),
        'IS + WF DRAWDOWN reads the saved block ($2.4k)': _iw.get('DRAWDOWN') == '$2.4k',
        'IS + WF MAR is annualised on that drawdown (0.77)': _iw.get('MAR') == '0.77',
        'IS + WF SHARPE is the block own (1.05)': _iw.get('SHARPE') == '1.05',
        'IS + WF SORTINO is the block own (1.45)': _iw.get('SORTINO') == '1.45',
        'IS + WF PF and TRADES are the block own (1.40, 300)': _iw.get('PF') == '1.40' and _iw.get('TRADES') == '300',
        'no false no-combined-block hover on IS + WF': 'no combined drawdown' not in (_iw.get('DRAWDOWN_tip') or ''),
        'the row stays on the DRAWDOWN / SORTINO chart on IS + WF as on IS': _iw.get('pts') is not None and _iw.get('pts') == _is.get('pts'),
        'IS + LB still dashes DRAWDOWN with the no-combined-block reason': _il.get('DRAWDOWN') == dash5 and 'no combined drawdown' in (_il.get('DRAWDOWN_tip') or ''),
    }
    r5r_ok = all(r5r_chk.values())
    line('r5_rawpre', r5r_ok, 'failed=%s | is+wf=%s | is=%s | is+lb=%s'
         % ([k for k, v in r5r_chk.items() if not v],
            {k: _iw.get(k) for k in ('DRAWDOWN', 'MAR', 'SHARPE', 'SORTINO', 'PF', 'TRADES', 'pts')},
            {k: _is.get(k) for k in ('DRAWDOWN', 'MAR', 'SORTINO', 'pts')}, {k: _il.get(k) for k in ('DRAWDOWN', 'MAR')}))
    if not r5r_ok:
        fail('r5_rawpre: a RAW configuration must read its saved in-sample + walk-forward block -- see the r5_rawpre line')

    # case r5_rbpf0
    r = cases.get('r5_rbpf0', {})
    _wo, _be, _gr = (r.get('worst') or []), (r.get('best') or []), (r.get('grid') or {})
    _ord = _gr.get('order') or []
    r5b_chk = {
        'renders OK': r.get('call') == 'OK',
        'WORST lists the all-loss lockbox first at 0.00': _wo[:1] == [['995601', '0.00']],
        'WORST then lists the runs with a figure': [x[0] for x in _wo] == ['995601', '995603', '995602'],
        'BEST keeps the all-loss lockbox, last': [x[0] for x in _be] == ['995602', '995603', '995601'],
        'the zero-trade lockbox is in neither list': all(x[0] != '995604' for x in _wo + _be),
        'grid PF prints 0.00 for the all-loss lockbox': (_gr.get('pf') or {}).get('995601') == '0.00',
        'grid PF dashes the zero-trade lockbox': (_gr.get('pf') or {}).get('995604') == dash5,
        'RANK BY PF puts the all-loss run above the zero-trade run': '995601' in _ord and '995604' in _ord and _ord.index('995601') < _ord.index('995604'),
    }
    r5b_ok = all(r5b_chk.values())
    line('r5_rbpf0', r5b_ok, 'failed=%s | worst=%s best=%s grid=%s' % ([k for k, v in r5b_chk.items() if not v], _wo, _be, _gr))
    if not r5b_ok:
        fail('r5_rbpf0: RUNBOARD must keep a real profit factor of 0 on a stretch that traded -- see the r5_rbpf0 line')

    # case r5_lbonly
    r = cases.get('r5_lbonly', {})
    _lb, _al = (r.get('lb') or {}), (r.get('all') or {})
    _ll, _wl, _lu = (r.get('lbLoaded') or {}), (r.get('wflbLoaded') or {}), (r.get('lbUnloaded') or {})
    _noIs = 'money only for its lockbox'
    r5l_chk = {
        'renders OK': r.get('call') == 'OK',
        'rows found on every render': all(x.get('found') for x in (_lb, _al, _ll, _wl, _lu)),
        'LOCKBOX: MAR, ROC % / YR and PER YEAR dash on row 696': all(_lb.get(k) == dash5 for k in ('MAR', 'ROC % / YR', 'PER YEAR')),
        'LOCKBOX: each dash says the row records no in-sample money': all(_noIs in (_lb.get(k + '_tip') or '') for k in ('MAR', 'ROC % / YR', 'PER YEAR')),
        'all three stretches: the same dashes (the money is still only the lockbox)': all(_al.get(k) == dash5 for k in ('MAR', 'ROC % / YR', 'PER YEAR')),
        'row 696 is off the ROC chart on LOCKBOX': _lb.get('pt') is False,
        'TRADES / YR is still the whole-row figure (36.6)': _lb.get('TRADES / YR') == '36.6' and _al.get('TRADES / YR') == '36.6',
        'loaded run: LOCKBOX is still placed on the year the run dates (MAR 1.36, hover says 1.00 years)':
            _ll.get('MAR') == '1.36' and '1.00 years the run this row cites dates' in (_ll.get('PER YEAR_tip') or ''),
        'loaded run: WALK-FORWARD + LOCKBOX dates only the lockbox it covers':
            _wl.get('PER YEAR') == _ll.get('PER YEAR') and '1.00 years the run this row cites dates' in (_wl.get('PER YEAR_tip') or ''),
        'loaded run: YEARS shows the whole window the row records, not the dated stretch (round 6)':
            _ll.get('YEARS') == '16.1' and _wl.get('YEARS') == '16.1',
        'run not loaded: MAR dashes and names the lockbox-only reason': _lu.get('MAR') == dash5 and _noIs in (_lu.get('MAR_tip') or ''),
    }
    r5l_ok = all(r5l_chk.values())
    line('r5_lbonly', r5l_ok, 'failed=%s | lb=%s | all=%s | lbLoaded=%s | wflbLoaded=%s | lbUnloaded=%s'
         % ([k for k, v in r5l_chk.items() if not v],
            {k: _lb.get(k) for k in ('MAR', 'ROC % / YR', 'PER YEAR', 'YEARS', 'TRADES / YR', 'pt')},
            {k: _al.get(k) for k in ('MAR', 'ROC % / YR', 'PER YEAR', 'TRADES / YR')},
            {k: _ll.get(k) for k in ('MAR', 'PER YEAR', 'YEARS')}, {k: _wl.get(k) for k in ('MAR', 'PER YEAR', 'YEARS')},
            {k: _lu.get(k) for k in ('MAR', 'YEARS')}))
    if not r5l_ok:
        fail('r5_lbonly: a lockbox-only write-up must not divide its lockbox by the whole window -- see the r5_lbonly line')

    # case r5_split
    r = cases.get('r5_split', {})
    _h7, _h6, _sd = (r.get('h768') or {}), (r.get('h650') or {}), (r.get('study') or {})
    def _okb(o):
        return bool(o) and not o.get('none') and bool(o.get('ok'))
    r5s_chk = {
        'renders OK': r.get('call') == 'OK',
        'the iframe really was laptop-sized': (_h7.get('inner') or [0, 0])[1] == 768 and (_h6.get('inner') or [0, 0])[1] == 650,
        'the table really scrolls sideways (a scrollbar to lose)': ((_h7.get('top') or {}).get('hOver') or 0) > 0,
        '768 high, page top: scrollbar inside column and window': _okb(_h7.get('top')),
        '768 high, after a page scroll: still inside': _okb(_h7.get('scrolled')),
        '768 high, render while scrolled then back to top: still inside': _okb(_h7.get('backTop')),
        '650 high, page top: scrollbar inside column and window': _okb(_h6.get('top')),
        '650 high, after a page scroll: still inside': _okb(_h6.get('scrolled')),
        '650 high, render while scrolled then back to top: still inside': _okb(_h6.get('backTop')),
        'a study opened by its header gets its box capped to the column': (_sd.get('keys') or 0) > 1 and _sd.get('ok') is True,
    }
    r5s_ok = all(r5s_chk.values())
    line('r5_split', r5s_ok, 'failed=%s | h768=%s | h650=%s | study=%s' % ([k for k, v in r5s_chk.items() if not v], _h7, _h6, _sd))
    if not r5s_ok:
        fail('r5_split: the SPLIT table scrollbars must stay on screen at laptop heights -- see the r5_split line')

    # case r5_samemeas
    r = cases.get('r5_samemeas', {})
    _sm = r.get('res') or {}
    _combos = [v for v in _sm.values() if isinstance(v, dict)]
    r5m_chk = {
        'renders OK': r.get('call') == 'OK' and len(_combos) == 4,
        'offers were made at all (the check is not vacuous)': any(v.get('up') or v.get('across') for v in _combos),
        'no offer up the side repeats the measure across': all(v.get('x') not in (v.get('up') or []) and v.get('x') not in (v.get('btnUp') or []) for v in _combos),
        'no offer across repeats the measure up the side': all(v.get('y') not in (v.get('across') or []) and v.get('y') not in (v.get('btnAcross') or []) for v in _combos),
    }
    r5m_ok = all(r5m_chk.values())
    line('r5_samemeas', r5m_ok, 'failed=%s | %s' % ([k for k, v in r5m_chk.items() if not v], _sm))
    if not r5m_ok:
        fail('r5_samemeas: the note must never offer the measure already on the other axis -- see the r5_samemeas line')

    # ---- REVIEW ROUND 6 (patch_R4.py R4-10 .. R4-12) -------------------------------------------

    # case r6_evapx
    r = cases.get('r6_evapx', {})
    _f6, _i6 = (r.get('full') or {}), (r.get('is') or {})
    _fev, _ftr = (_f6.get('EV') or {}), (_f6.get('TRADES') or {})
    _bestEv = [k for k, v in _fev.items() if (v or {}).get('best')]
    _n8 = _fev.get('990008') or {}
    r6e_chk = {
        'renders OK on FULL and on IS': r.get('call') == 'OK' and bool(_fev) and bool(_i6.get('EV')),
        'the run that saved no whole-run count marks its FULL trade count ~': (_ftr.get('990008') or {}).get('apx') is True,
        'its EV carries the same ~': _n8.get('apx') is True,
        'and says on hover that the count is the summed fallback': 'summed tuning-window, walk-forward and lockbox counts' in (_n8.get('tip') or ''),
        'that EV is not given the best-in-row mark': _n8.get('best') is False,
        'the best EV mark sits on one run whose count is exact': (len(_bestEv) == 1 and _bestEv[0] != '990008'
                                                                 and (_fev.get(_bestEv[0]) or {}).get('apx') is False),
        'on IS no EV cell is approximate (the tuning count is saved)': all(not (v or {}).get('apx') for v in (_i6.get('EV') or {}).values()),
    }
    r6e_ok = all(r6e_chk.values())
    line('r6_evapx', r6e_ok, 'failed=%s | EV=%s | TRADES=%s' % ([k for k, v in r6e_chk.items() if not v],
         {k: (v.get('t'), v.get('best'), v.get('apx')) for k, v in _fev.items()},
         {k: (v.get('t'), v.get('apx')) for k, v in _ftr.items()}))
    if not r6e_ok:
        fail('r6_evapx: the FULL EV row must not win its row on a trade count the TRADES row marks ~ -- see the r6_evapx line')

    # case r6_yrscol
    r = cases.get('r6_yrscol', {})
    _w1, _w3, _ld = (r.get('w1') or {}), (r.get('w3') or {}), (r.get('loaded') or {})
    _rl, _ra, _hd6 = (r.get('runLb') or {}), (r.get('runAll') or {}), (r.get('hdr') or '')
    _yt = _w1.get('YEARS_tip') or ''
    r6y_chk = {
        'renders OK': r.get('call') == 'OK',
        'every row was found': all(x.get('found') for x in (_w1, _w3, _ld, _rl, _ra)),
        'lockbox-only write-up: YEARS is its own window (16.1) on LOCKBOX and on all three': _w1.get('YEARS') == '16.1' and _w3.get('YEARS') == '16.1',
        'and DATA WINDOW on the same row says the same window': '2010-06-07' in (_w1.get('DATA WINDOW') or '') and '2026-06-30' in (_w1.get('DATA WINDOW') or ''),
        'the YEARS hover says why PER YEAR and MAR / YR dash, not that the row records no window':
            'PER YEAR and MAR / YR beside it dash' in _yt and 'records no data window' not in _yt,
        'PER YEAR and MAR / YR on that row still dash': _w1.get('PER YEAR') == dash5 and _w1.get('MAR / YR') == dash5,
        'the YEARS heading says what the column holds for each kind of row':
            'stretches now ticked added up' in _hd6 and 'whole window it records' in _hd6,
        'loaded run: YEARS is the whole window while PER YEAR stays on the dated stretch':
            _ld.get('YEARS') == '16.1' and _ld.get('PER YEAR') == '$5.1k' and '1.00 years the run this row cites dates' in (_ld.get('PER YEAR_tip') or ''),
        'a run row keeps the ticked stretch length (LOCKBOX 1.0, all three 16.1)': _rl.get('YEARS') == '1.0' and _ra.get('YEARS') == '16.1',
    }
    r6y_ok = all(r6y_chk.values())
    line('r6_yrscol', r6y_ok, 'failed=%s | 696 lb=%s | 696 all=%s | loaded=%s | run lb/all=%s/%s'
         % ([k for k, v in r6y_chk.items() if not v],
            {k: _w1.get(k) for k in ('YEARS', 'PER YEAR', 'MAR / YR', 'TRADES / YR', 'DATA WINDOW')},
            {k: _w3.get(k) for k in ('YEARS', 'PER YEAR')},
            {k: _ld.get(k) for k in ('YEARS', 'PER YEAR', 'MAR')}, _rl.get('YEARS'), _ra.get('YEARS')))
    if not r6y_ok:
        fail('r6_yrscol: the YEARS column must never contradict DATA WINDOW -- see the r6_yrscol line')

    # case r6_split
    r = cases.get('r6_split', {})
    _s7, _s6 = (r.get('h768') or {}), (r.get('h650') or {})
    _t7, _c7, _b7 = (_s7.get('top') or {}), (_s7.get('scrolled') or {}), (_s7.get('backTop') or {})
    _t6, _c6, _b6 = (_s6.get('top') or {}), (_s6.get('scrolled') or {}), (_s6.get('backTop') or {})
    _all6 = (_t7, _c7, _b7, _t6, _c6, _b6)
    r6s_chk = {
        'renders OK with the FILTERS sheet open, at both heights': r.get('call') == 'OK' and all(bool(x) and not x.get('none') for x in _all6),
        'the column is pinned to the top of the screen': _c7.get('pos') == 'sticky' and _c6.get('pos') == 'sticky',
        '768 high, page top: the table bottom edge is inside the column and on screen': _t7.get('inside') is True,
        '768 high, page top: the column reaches the bottom of the window': _t7.get('reaches') is True,
        '768 high, scrolled to the tables: it still reaches the bottom of the window': _c7.get('reaches') is True,
        '768 high, scrolled to the tables: the table gained at least 100px and stays inside':
            _c7.get('inside') is True and (_c7.get('boxH') or 0) >= (_t7.get('boxH') or 0) + 100,
        '768 high, back at the top: the table bottom edge is inside again': _b7.get('inside') is True,
        '650 high, page top: inside, and reaching the bottom of the window': _t6.get('inside') is True and _t6.get('reaches') is True,
        '650 high, scrolled to the tables: reaches the bottom, gained 100px, stays inside':
            _c6.get('reaches') is True and _c6.get('inside') is True and (_c6.get('boxH') or 0) >= (_t6.get('boxH') or 0) + 100,
        '650 high, back at the top: inside again': _b6.get('inside') is True,
        'no table box is ever made taller than the cap it was drawn with': all((x.get('boxMax') or 0) <= 560 for x in _all6),
    }
    r6s_ok = all(r6s_chk.values())
    line('r6_split', r6s_ok, 'failed=%s | h768=%s | h650=%s' % ([k for k, v in r6s_chk.items() if not v], _s7, _s6))
    if not r6s_ok:
        fail('r6_split: with the FILTERS sheet open the SPLIT tables must keep their scrollbar on screen and take the room a page scroll gives back -- see the r6_split line')

    # == DEFERRED ROUND (dfx_*): each case carries its own named checks (r['ck']); all must hold ==
    DFX = ['dfx_d03', 'dfx_d04', 'dfx_d05', 'dfx_d06', 'dfx_d07', 'dfx_d10', 'dfx_d12', 'dfx_d13', 'dfx_d14', 'dfx_d15',
           'dfx_d16', 'dfx_d17', 'dfx_d20', 'dfx_d21', 'dfx_d22',
           # g1-pool (Starred/older/archived pool + family grouping): F1, F6, F7, F11, F12
           'g1_f1', 'g1_f6', 'g1_f7', 'g1_f11', 'g1_f12',
           # g2-stage (Stage math and book reports): F2, F3, F10, F13, F18
           'g2_f2', 'g2_f3', 'g2_f10', 'g2_f13', 'g2_f18',
           # g3-books-picks (Book flags and PICK RUNS marks/tiles): F4, F8, F9, F22
           'g3_f4', 'g3_f8', 'g3_f9', 'g3_f22',
           # g4-charts (Chart dates, full-screen view, +ADD, EXPLORE hovers): F5, F15, F16, F17, F19, F20, F21, F29
           'g4_f5', 'g4_f15', 'g4_f16', 'g4_f17', 'g4_f19', 'g4_f20', 'g4_f21', 'g4_f29',
           # g5 (repair round): F4 Gate-Validate job headline money
           'g5_gv', 'g5_bookis', 'g5_archpick', 'g5_wfrange',
           # g6 (repair round): Gate-Validate job in-sample years for MAR / R per YR / ROC % per YR
           'g6_gvisyrs', 'g6_gvexplore',
           # h1-h14 (2026-09-20): WALK-FORWARD default stage, thin-test floor, gap chip,
           # and the lockbox veto note (RESEARCH.md item 8)
           'h1_defaultstage_lead', 'h2_defaultstage_persists', 'h3_defaultstage_champions',
           'h5_thin_sinks_below_cleared', 'h6_zero_sinks_below_thin', 'h7_thin_shows_figures_and_mark',
           'h8_thin_never_bestmark', 'h9_thin_floor_only_on_wf',
           'h10_gapchip_percent', 'h11_gapchip_pinned_equal', 'h12_gapchip_missing_reading',
           'h13_lockbox_veto_note', 'h14_lockbox_veto_runboard',
           # i1-i4 (audit3_report.md round, 2026-09-24): F25 WINDOW row stage stretch,
           # F30 book-name labels + rank-on-picked + side issues, F31 LB zero-trade reason.
           'i1_f25_window_stage', 'i2_f30_book_and_naming', 'i3_f30_rank_on_picked',
           'i4_f31_lb_zero_reason']
    for name in DFX:
        r = cases.get(name) or {}
        ck = r.get('ck') or {}
        ok = r.get('call') == 'OK' and not r.get('uncaught') and bool(ck) and all(ck.values())
        line(name, ok, 'failed=%s | call=%s | %s' % ([k for k, v in ck.items() if not v], str(r.get('call'))[:80],
                                                     json.dumps(r.get('info'), ensure_ascii=False)[:500]))
        if not ok:
            fail(name + ': see the ' + name + ' line')

    if bad:
        print('CMP2 PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('CMP2 PROBE: PASS (VERSION=%s, %d cases)' % (data.get('VERSION'), len(cases)))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
