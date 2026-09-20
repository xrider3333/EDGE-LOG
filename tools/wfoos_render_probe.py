#!/usr/bin/env python3
"""
tools/wfoos_render_probe.py -- render gate for the saved walk-forward test (validate.wf_oos).

WHY THIS EXISTS (2026-09-15)
----------------------------
The engine now saves one small walk-forward block per validated run: every fold's own
out-of-sample trades joined in fold order (net, PF, win rate, drawdown, Sharpe, Sortino, a
<=200-point curve, fold dates). The web reads it through ONE checked reader and shows it on
the run report (1C curve and chips, 1E walk-forward column, WF OOS pill, 1A / funnel fold
hovers, 2B / 2C pill) and in Past Runs (WF cell and Sharpe hovers).

Two ways this can pass a gate while being broken on the live site, and this probe closes both:
  * THE LIST MASK. Past Runs, COMPARE, RUNBOARD and EXPLORE read PROJECTED ("lite") run rows.
    If 'validate.wf_oos' is not in RUNS_LITE_FIELDS every list reader silently says "not saved",
    while a probe that injects the whole fixture document stays green. So the Past Runs cases
    here project every fixture through the page's own RUNS_LITE_FIELDS first, exactly as the
    REST read does, and only the REPORT cases use whole documents (the report hydrates one).
  * THE CHECK. A block that disagrees with the fold rows must be refused, never averaged in.
    Thirteen variants of the fixture exercise every refusal and every missing-figure reason.

FIXTURES (all built offline by tools/make_wfoos_fixture.py; nothing here touches Firestore)
  tools/fixtures/run_report.json      run #306, saved before the block existed ("absent")
  tools/fixtures/run_wfoos.json       run #306 + an engine-built validate.wf_oos
  tools/fixtures/run_book_synth.json  a synthetic book (a book tunes nothing: no block, ever)
  tools/fixtures/run_wfoos_zero.json  run #306 as id 90308, every fold tested no trade, its block built by the
                                      engine's own wf_oos_block (tools/make_wfoos_zero_fixture.py) - the R5
                                      cases: its $0 and 0 trades are readings on every screen, every ratio and
                                      the drawdown dash with one sentence, and nothing it shows wins a mark
  tools/fixtures/wfoos_pastruns_snapshot.json   Past Runs row text + order for runs WITHOUT a
                                      block, written from the pre-change build with
                                      --write-snapshot; compared on every run.
Every expected number is read out of those JSON files inside the probe; none is typed in here.

The F cases cover the four low findings the first build's own verification left open:
  F1  a fold that tested no trade drew a stripe cut out of the fold before it (the engine's fold
      start falls back to the last saved point) -- it now draws a hairline no-trades marker instead.
      F1d / F1e: several untraded folds in a row all pointed at the same next fold that traded and so
      all landed on ONE hairline, where only the last one drawn could be hovered and the earlier folds'
      hovers were unreachable with no error anywhere -- each now takes its own slot back from that
      shared edge (a run with no room to its left slides right as one) and every marker is drawn after
      the stripes, so no stripe can cover one either.
  F2  "too few walk-forward trades" was said for a Sortino with no losing trade and a Sharpe with no
      spread -- each cause now has its own plain reason.
  F3  a block with no saved window dates let the walk-forward column divide by the bar-count estimate
      while the 1C chip beside it dashed -- both dash now, and the heading says which window is shown.
  F4  the walk-forward heading said PF and win % were pooled while the info text said they came from
      the test -- every hover now names one source per figure.

ASSERTIONS are tagged NEW (tests behaviour this build adds, and must fail on the build before
it) or NOREG (must hold on both builds). Exit codes match the other gates: 0 PASS, 1 FAIL,
2 INCONCLUSIVE. A non-PASS attempt that produced no readout is retried once.

The live signed-in check (window._runsLiteOk===true after boot, response size, a backfilled
run) cannot run here without Firebase and stays a manual step in real Chrome.

Usage:
  python tools/wfoos_render_probe.py                 # gates this repo's index.html
  python tools/wfoos_render_probe.py --file X.html   # gates X as if it were index.html
  python tools/wfoos_render_probe.py --write-snapshot   # (re)write the Past Runs snapshot
  python tools/wfoos_render_probe.py --verbose       # print every assertion, not just failures
Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
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
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

PROBE_JS = r"""
var FIXB=__FIXB__, FIXW=__FIXW__, FIXBK=__FIXBK__, FIXZ=__FIXZ__;
(function(){
  var reported=false, out={res:[],snap:{}}, t0=Date.now();
  function finish(why){if(reported)return;reported=true;out.why=why;out.ms=Date.now()-t0;
    document.getElementById('o').textContent='WFOOSPROBE: '+JSON.stringify(out);}
  function clone(x){return JSON.parse(JSON.stringify(x));}
  function A(id,kind,ok,detail){out.res.push({id:id,kind:kind,ok:!!ok,detail:(detail==null?'':String(detail).slice(0,600))});}
  function fmtUsd(v){return ((v||0)<0?'-$':'$')+Math.abs(Math.round(v||0)).toLocaleString();}
  function mdy(s){var t=new Date(String(s).slice(0,10));return (t.getUTCMonth()+1)+'/'+t.getUTCDate()+'/'+String(t.getUTCFullYear()).slice(2);}
  function hook(w){if(w.__probeSink)return w.__probeSink;var sink=w.__probeSink={errors:[],uncaught:[]};var orig=w.console.error;
    w.console.error=function(){var p=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];p.push(a&&a.stack?String(a.stack):String(a));}sink.errors.push(p.join(' '));try{orig.apply(w.console,arguments);}catch(_){}};
    w.addEventListener('error',function(ev){sink.uncaught.push(String(ev&&ev.message||ev));});
    w.addEventListener('unhandledrejection',function(ev){var r=ev&&ev.reason;sink.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    return sink;}
  function run(){
    var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument, sink=hook(w);
    out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
    if(w.eval('typeof renderApp')!=='function'){finish('noboot');return;}
    var L=w.eval('RUNS_LITE_FIELDS');
    // ── documents are built INSIDE the app frame, normalised the way the read paths do ──
    function mk(obj,isLite){w.__pj=JSON.stringify(obj);var x=w.eval('_bookUnitsOnRead(_isoTs(JSON.parse(window.__pj)))');if(isLite)x._lite=true;return x;}
    function project(doc,fields){var o={};fields.forEach(function(f){var p=f.split('.'),src=doc,ok=true;
      for(var i=0;i<p.length;i++){if(src&&typeof src==='object'&&!Array.isArray(src)&&(p[i] in src))src=src[p[i]];else{ok=false;break;}}
      if(!ok)return;var dst=o;for(var j=0;j<p.length-1;j++){dst[p[j]]=dst[p[j]]||{};dst=dst[p[j]];}dst[p[p.length-1]]=clone(src);});return o;}
    function lite(doc,id){var p=project(doc,L);p.id=String(id!=null?id:doc.id);return mk(p,true);}
    function full(doc){return mk(doc,false);}
    function render(prefs,runs,fullDocs,sel){
      sink.errors.length=0;sink.uncaught.length=0;
      var arr=w.eval('[]');runs.forEach(function(x){arr.push(x);});
      var fm=w.eval('({})');(fullDocs||[]).forEach(function(x){fm[String(x.id)]=x;});
      w.__runs=arr;w.__full=fm;
      return w.eval("(function(){try{localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(prefs||{}))+");"
        +"if(typeof APREF==='object'&&APREF){for(var k in APREF)delete APREF[k];var P="+JSON.stringify(prefs||{})+";for(var k2 in P)APREF[k2]=P[k2];}"
        +"runHistory=window.__runs;window._runFull=window.__full;window._runFullOrder=[];window._runHydrating={};window._wfoBad={};"
        +"activeTab='augur';augurSub='runs';augurRunSel="+(sel==null?'null':JSON.stringify(String(sel)))+";renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");}
    function q(sel){return Array.prototype.slice.call(d.querySelectorAll(sel));}
    function txt(sel){return q(sel).map(function(e){return (e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();});}
    function tips(){return q('[data-tip]').map(function(e){return e.getAttribute('data-tip')||'';});}
    function rows(){return q('tr.arow[data-run]').map(function(tr){var tds=Array.prototype.slice.call(tr.children);
      return {id:tr.getAttribute('data-run'),cells:tds.map(function(td){return (td.innerText||'').replace(/\s+/g,' ').trim();}),titles:tds.map(function(td){return td.getAttribute('title')||'';})};});}
    function kpi(){var t=q('table').filter(function(t){var h=t.querySelector('thead');return h&&/METRIC/.test(h.innerText)&&/TOTAL/.test(h.innerText);})[0];
      if(!t)return null;var head=Array.prototype.map.call(t.querySelectorAll('thead th'),function(x){return (x.innerText||'').replace(/\s+/g,' ').trim();});
      var o={head:head,col:{},cell:{},title:{}};head.forEach(function(h,i){var m=h.match(/^(IS|WF|LB|TOTAL)/);if(m)o.col[m[1]]=i;});
      Array.prototype.forEach.call(t.querySelectorAll('tbody tr'),function(tr){var tds=tr.children;if(tds.length<2)return;var lbl=(tds[0].innerText||'').trim();
        o.cell[lbl]=Array.prototype.map.call(tds,function(td){return (td.innerText||'').trim();});
        o.title[lbl]=Array.prototype.map.call(tds,function(td){var s=td.querySelector('[title]');return s?s.getAttribute('title'):'';});});
      return o;}
    function kc(K,lbl,col){return (K&&K.cell[lbl]&&K.col[col]!=null)?K.cell[lbl][K.col[col]]:null;}
    function kt(K,lbl,col){return (K&&K.title[lbl]&&K.col[col]!=null)?K.title[lbl][K.col[col]]:null;}
    // the hover on one 1E column heading (the heading says where each figure in that column came from)
    function kpiHeadTip(col){var t=q('table').filter(function(t){var h=t.querySelector('thead');return h&&/METRIC/.test(h.innerText)&&/TOTAL/.test(h.innerText);})[0];
      if(!t)return '';var th=Array.prototype.slice.call(t.querySelectorAll('thead th')).filter(function(x){return new RegExp('^'+col+'\\b').test(norm(x.textContent));})[0];
      return th?(th.getAttribute('title')||''):'';}
    // one chip under the 1C walk-forward curve, by its label
    function chipOf(lbl){var e=q('[data-wfochips] span').filter(function(x){return norm(x.textContent).indexOf(lbl+' ')===0;})[0];
      return e?norm(e.textContent).slice(lbl.length+1):null;}
    function infopops(re){return q('[data-infopop]').map(function(e){try{return decodeURIComponent(e.getAttribute('data-infopop'));}catch(_){return '';}}).filter(function(t){return re.test(t);});}
    function norm(s){return String(s||'').replace(/\s+/g,' ').trim();}
    // the 1C fold-bar chart box (its svg carries the fold hover axis) and the walk-forward test curve's own sized box
    function foldBox(){return q('#res-detail .rschart-box').filter(function(b){var s=b.querySelector('svg[data-xh]');if(!s)return false;
      try{return JSON.parse(decodeURIComponent(s.getAttribute('data-xh'))).xl==='fold';}catch(_){return false;}})[0]||null;}
    function cboxOf(c){return c?(c.classList.contains('rschart-box')?c:(c.closest('.rschart-box')||c.querySelector('.rschart-box'))):null;}
    // the hover on the "WALK-FORWARD TEST" label in 1C
    function testTip(){var e=q('#res-detail [title]').filter(function(x){return norm(x.textContent)==='WALK-FORWARD TEST';})[0];return e?(e.getAttribute('title')||''):'';}
    // THE PAGE'S OWN chart-name readers, lifted out of the app script text (never re-typed here): the
    //   full-screen title (findHdr) and the saved-height key (_keyOf) both take the nearest text above a chart box
    var appSrc=q('script').map(function(s){return s.textContent||'';}).filter(function(t){return t.indexOf('const _keyOf=box=>{')>=0;})[0]||'';
    function grab(start){var END='n=n.parentElement;}return null;};',i=appSrc.indexOf(start);if(i<0)return null;var j=appSrc.indexOf(END,i);return (j<0)?null:appSrc.slice(i,j+END.length);}
    var keyOf=null,findHdr=null,helpErr='';
    try{keyOf=(new Function(grab('const _keyOf=box=>{')+' return _keyOf;'))();findHdr=(new Function(grab('const findHdr=bx=>{')+' return findHdr;'))();}catch(e){helpErr=String(e&&e.message||e);}
    // geometry of the curve panel: nothing it draws may spill onto the caption, the drag grip or the fold bars
    function geo(tag){var cv=q('[data-wfocurve]');if(cv.length!==1)return {ok:false,why:tag+' curves='+cv.length};
      var c=cv[0],box=cboxOf(c),bad=[];try{c.scrollIntoView({block:'center'});}catch(_){}
      var R=c.getBoundingClientRect(),inner=c.querySelector('.rschart-box'),sv=c.querySelector('svg');
      if(!box)bad.push('curve is not in a sized chart box');
      if(inner){var IR=inner.getBoundingClientRect();if(IR.bottom>R.bottom+0.5)bad.push('chart box overflows the panel by '+(IR.bottom-R.bottom).toFixed(1)+'px');}
      if(sv){var S=sv.getBoundingClientRect();if(S.bottom>R.bottom+0.5)bad.push('chart overflows the panel by '+(S.bottom-R.bottom).toFixed(1)+'px');}
      var sib=c.nextElementSibling,n=0;
      while(sib&&n<4){var r=sib.getBoundingClientRect();
        if(r.width>0&&r.height>0){var e=d.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
          if(!(e&&(e===sib||sib.contains(e))))bad.push('next element '+n+' ('+(sib.hasAttribute('data-rsrow')?'drag grip':norm(sib.textContent).slice(0,24))+') is covered by '+(e?(e.tagName+(e.getAttribute('data-wfofold')?('[fold '+e.getAttribute('data-wfofold')+']'):'')+(c.contains(e)?' in the curve box':'')):'nothing'));}
        sib=sib.nextElementSibling;n++;}
      var fb=foldBox();if(fb){var F=fb.getBoundingClientRect();if(R.top<F.bottom-0.5)bad.push('curve top '+R.top.toFixed(1)+' sits above the fold bars bottom '+F.bottom.toFixed(1));}
      return {ok:!bad.length,why:tag+' h='+R.height.toFixed(0)+(bad.length?(' '+bad.join('; ')):'')};}
    function clean(nm,call){var det=d.getElementById('res-detail');var t=det?(det.innerText||''):'';
      var ok=(call==='OK')&&!sink.errors.length&&!sink.uncaught.length&&!!det&&!/couldn.t render/i.test(t);
      A('R0.'+nm,'NOREG',ok,'call='+String(call).slice(0,300)+' errors='+JSON.stringify(sink.errors.slice(0,2))+' uncaught='+JSON.stringify(sink.uncaught.slice(0,2))+' detail='+!!det);}

    var B=FIXW.validate.wf_oos, M=+(FIXW.multiplier||20);
    var FL=(FIXW.top10_results||[]).filter(function(f){return f&&f.fold!=null;});
    var sN=FL.reduce(function(a,f){return a+(+f.oos_pnl||0);},0), sT=FL.reduce(function(a,f){return a+(+f.oos_trades||0);},0);
    var noGate=function(x){var c=clone(x);delete c.gate_validate;delete c.ml_gate;return c;};

    // ── §5.2 the list mask ─────────────────────────────────────────────────────────────
    A('A1 mask carries validate.wf_oos','NEW',L.indexOf('validate.wf_oos')>=0,'index '+L.indexOf('validate.wf_oos'));
    A('A2 mask lists no sub-path of it','NOREG',!L.some(function(f){return f.indexOf('validate.wf_oos.')===0;}),L.filter(function(f){return f.indexOf('validate.wf_oos')===0;}).join(','));
    var LW=lite(FIXW);
    A('A3 a projected row keeps the whole block','NEW',!!(LW.validate&&LW.validate.wf_oos&&+LW.validate.wf_oos.trades===+B.trades&&LW.validate.wf_oos.equity&&LW.validate.wf_oos.equity.length===B.equity.length),
      'projected keys: '+Object.keys(LW.validate||{}).filter(function(k){return /wf/.test(k);}).join(','));

    // one plain render so the reader exists
    var c0=render({},[LW],[],null);
    var Hw=w._wfOos, H0ok=!!(Hw&&typeof Hw.of==='function'&&typeof Hw.chk==='function'&&typeof Hw.why==='function');
    A('H0 the shared reader is reachable after a render','NEW',H0ok,typeof Hw);
    // on a build without the reader every assertion below still RUNS and records a failure
    var H=H0ok?Hw:{chk:function(){return {st:'(reader missing)'};},of:function(){return null;},why:function(){return '(reader missing)';}};
    function hsafe(f){try{return f();}catch(e){return {__err:String(e&&e.message||e)};}}
    function T(id,fn,det){var ok=false,dt='';try{ok=!!fn();dt=det?det():'';}catch(e){ok=false;dt='threw: '+String(e&&e.message||e);}A(id,'NEW',ok,dt);}
    {
      var DW=full(FIXW), O=H.of(DW,M)||{}, eqL=B.equity.length;
      A('H1 accepted block state ok','NEW',O.st==='ok',JSON.stringify(H.chk(DW).st));
      T('H2 drawdown = saved max drawdown x multiplier',function(){return Math.abs(O.dd-Math.abs(B.max_drawdown)*M)<1e-9;},function(){return O.dd+' vs '+Math.abs(B.max_drawdown)*M;});
      T('H3 curve starts at $0, one point longer, ends on the block net',function(){return O.curve&&O.curve[0]===0&&O.curve.length===eqL+1&&Math.abs(O.curve[eqL]-B.equity[eqL-1]*M)<1e-6&&Math.abs(O.curve[eqL]-B.net*M)<1e-6;},
        function(){return O.curve?(O.curve[0]+' len '+O.curve.length+' last '+O.curve[O.curve.length-1]+' net*M '+B.net*M):'no curve';});
      var marX=((sN*M)/B.years)/(Math.abs(B.max_drawdown)*M);
      T('H4 MAR = pooled net / block years / block drawdown',function(){return Math.abs(O.poolNet-sN*M)<1e-6&&O.yrs===B.years&&Math.abs(O.mar-marX)<=1e-9*Math.max(1,Math.abs(marX));},function(){return O.mar+' vs '+marX;});
      T('H5 ratios read as saved',function(){return O.sharpe===B.sharpe&&O.sortino===B.sortino&&O.pf===B.profit_factor&&Math.abs(O.wr-100*B.wins/B.trades)<1e-9&&O.tr===B.trades&&O.nFolds===B.n_folds;},
        function(){return JSON.stringify({sh:O.sharpe,so:O.sortino,pf:O.pf,wr:O.wr,tr:O.tr,nf:O.nFolds});});
      var fiX=[];B.fold_idx.forEach(function(i){var v=i+1;if(fiX.indexOf(v)<0&&v>=1&&v<=eqL)fiX.push(v);});
      T('H6 fold marks + fold rows carried, money x multiplier',function(){return JSON.stringify(O.foldIdx)===JSON.stringify(fiX)&&O.folds.length===B.folds.length&&O.folds[0].from===B.folds[0].from&&Math.abs(O.folds[1].net-B.folds[1].net*M)<1e-6;},
        function(){return JSON.stringify(O.foldIdx)+' vs '+JSON.stringify(fiX);});
      T('H7 memo per multiplier',function(){var O2=H.of(DW,M),same=(O2===H.of(DW,M)),O3=H.of(DW,1000);return same&&!!O2&&O2.st==='ok'&&!!O3&&O3!==O2&&Math.abs(O3.dd-Math.abs(B.max_drawdown)*1000)<1e-9;},function(){return '';});
      // ── the thirteen variants (§5.1) + base, book, never validated ──
      function V(id,mut,mc){var x=clone(FIXW);mut(x);return full(x);}
      function chkV(id,doc,st,what,frag,extra){var c=hsafe(function(){return H.chk(doc);}),y=hsafe(function(){return what?H.why(doc,what):'';});
        var ok=(c&&c.st===st)&&(!frag||(typeof y==='string'&&y.indexOf(frag)>=0))&&(!extra||extra());
        A(id,'NEW',ok,'state='+(c&&c.st)+' why='+JSON.stringify(y));}
      chkV('V0 run saved before the block (absent)',full(FIXB),'absent','dd','saved before walk-forward detail was recorded');
      chkV('V1 block null, walk-forward ran',V('v1',function(x){x.validate.wf_oos=null;x.validate.wf_ran=true;}),'none','sh','no walk-forward detail was saved on this run');
      chkV('V2 walk-forward did not run, key absent',V('v2',function(x){delete x.validate.wf_oos;x.validate.wf_ran=false;}),'nowf','dd','walk-forward did not run');
      w._wfoBad={};var d3=V('v3',function(x){x.validate.wf_oos.trades=x.validate.wf_oos.trades+1;});
      chkV('V3 mismatch: trades + 1',d3,'mismatch','dd','does not match',function(){var b=w._wfoBad&&w._wfoBad[String(FIXW.id)];return !!(b&&b.trades===B.trades+1&&b.poolTrades===sT)&&H.of(d3,M)===null;});
      chkV('V4 mismatch: net + 2 points',V('v4',function(x){x.validate.wf_oos.net=x.validate.wf_oos.net+2;}),'mismatch','mar','does not match');
      var d5=V('v5',function(x){x.validate.wf_oos.net=x.validate.wf_oos.net+0.6;x.multiplier=1000;});
      chkV('V5 tolerance: net + 0.6 point, multiplier 1000, accepted',d5,'ok','dd','',function(){var o=H.of(d5,1000);return !!(o&&Math.abs(o.dd-Math.abs(B.max_drawdown)*1000)<1e-9&&Math.abs(o.poolNet-sN*1000)<1e-6);});
      chkV('V6 other fold scheme',V('v6',function(x){x.validate.wf_oos.mode=(x.validate.wf_best_mode==='rolling')?'anchored':'rolling';}),'mode','dd','belongs to the other fold scheme');
      chkV('V7 newer format',V('v7',function(x){x.validate.wf_oos.v=2;}),'shape','sh','newer format');
      var d8=V('v8',function(x){var b=x.validate.wf_oos;b.trades=0;b.wins=0;b.win_rate=0;b.net=0;b.gross_win=0;b.gross_loss=0;b.profit_factor=null;b.avg_win=null;b.avg_loss=null;b.max_drawdown=0;b.sharpe=null;b.sortino=null;b.equity=[];b.equity_n=0;b.fold_idx=b.fold_idx.map(function(){return 0;});b.folds.forEach(function(f){f.trades=0;f.net=0;});
        x.top10_results.forEach(function(f){if(f&&f.fold!=null){f.oos_trades=0;f.oos_pnl=0;f.oos_wins=0;}});});
      chkV('V8 zero-trade block',d8,'ok','pf','This run took no trades in the walk-forward folds.',function(){var o=H.of(d8,M);return !!(o&&o.zeroTr&&o.pf==null&&o.curve===null);});
      var d9=V('v9',function(x){x.validate.wf_oos.profit_factor=null;x.validate.wf_oos.gross_loss=0;});
      chkV('V9 no losing trade: PF null, gross loss 0',d9,'ok','pf','No walk-forward trade lost',function(){var o=H.of(d9,M);return !!(o&&o.pfNoLoss&&o.pf==null);});
      var d10=V('v10',function(x){var f=x.top10_results.filter(function(f){return f&&f.fold!=null;})[0];f.oos_pf=0;});
      chkV('V10 a fold with PF 0 keeps the exact block PF',d10,'ok','pf','',function(){var o=H.of(d10,M);return !!(o&&o.pf===B.profit_factor);});
      chkV('V11 fold list trimmed',V('v11',function(x){x.top10_results=[];}),'nofolds','dd','fold list on this run was trimmed');
      chkV('V12 duplicate fold rows',V('v12',function(x){var f=x.top10_results.filter(function(f){return f&&f.fold!=null;})[0];x.top10_results.push(clone(f));}),'mismatch','sh','does not match');
      var d13=V('v13',function(x){var b=x.validate.wf_oos;b.years=null;b.from=null;b.to=null;b.sharpe=null;b.sortino=null;b.folds.forEach(function(f){f.from=null;f.to=null;});});
      chkV('V13 window dates missing: no years, Sharpe, Sortino',d13,'ok','sh','window dates were not saved, so it cannot be annualised',
        function(){var o=H.of(d13,M);return !!(o&&o.yrs==null&&o.sharpe==null&&o.mar==null&&H.why(d13,'yrs').indexOf('window dates are not saved')>=0);});
      var dbk=full(FIXBK);
      chkV('Vbook a book never has the block',dbk,'book','dd','a book trades frozen configurations',function(){return H.of(dbk,M)===null;});
      chkV('Vnoval a run never validated',full({id:1,strategy:'X_1_0.py',top10_results:[]}),'noval','any','never validated');
      // keep variant docs for the report cases below
      out._v={d3:d3,d8:d8,d10:d10,d13:d13};
    }

    // ── §5.3 run report (whole documents, as the report hydrates them) ───────────────────
    var fW=full(FIXW), cW=render({},[lite(FIXW)],[fW],FIXW.id); clean('wfoos',cW);
    var chips=txt('[data-wfochips]').join(' || ');
    A('R1 1C chips from the block','NEW',q('[data-wfocurve]').length===1&&chips.indexOf('NET '+fmtUsd(sN*M))>=0&&chips.indexOf('TRADES '+(+B.trades).toLocaleString())>=0&&chips.indexOf(B.n_folds+' folds')>=0
      &&chips.indexOf(B.from+' – '+B.to)>=0&&chips.indexOf('SHARPE '+(+B.sharpe).toFixed(2))>=0&&chips.indexOf('MAX DD '+fmtUsd(-Math.abs(B.max_drawdown)*M))>=0&&chips.indexOf('rebuilt after the run')<0,
      'curves='+q('[data-wfocurve]').length+' chips='+chips);
    var withTr=B.folds.filter(function(f){return f.trades>0;}).length, st1=q('[data-wfofold="'+B.folds[0].f+'"]')[0];
    A('R2 1C fold stripes with real dates','NEW',q('[data-wfofold]').length===withTr&&!!st1&&(st1.getAttribute('data-tip')||'').indexOf(B.folds[0].from+' → '+B.folds[0].to)>=0,
      'stripes='+q('[data-wfofold]').length+' of '+withTr+' tip='+(st1?st1.getAttribute('data-tip'):''));
    var t1c=tips().filter(function(t){return t.indexOf('<b>Fold f'+B.folds[0].f+'</b> · test ')===0;});
    A('R3 1C fold bar hover dates from the block','NEW',t1c.length>=1&&t1c.every(function(t){return t.indexOf(B.folds[0].from)>=0&&t.indexOf(B.folds[0].trades+' trades')>=0;}),JSON.stringify(t1c.slice(0,1)));
    var t1a=tips().filter(function(t){return t.indexOf('<b>WF fold f'+B.folds[0].f+'</b>')===0;});
    A('R4 1A / funnel fold band hover dates from the block','NEW',t1a.length>=1&&t1a.every(function(t){return t.indexOf(mdy(B.folds[0].from))>=0&&t.indexOf(B.folds[0].trades+' trades')>=0;}),'n='+t1a.length+' '+JSON.stringify(t1a.slice(0,2)));
    var wfPill=q('[data-distsecm="wf"]').map(function(e){return e.getAttribute('title')||'';})[0]||'';
    var nS=Array.isArray(FIXW.win_dist_wf)?FIXW.win_dist_wf.length:0;
    A('R5 2B / 2C walk-forward pill says it is a sample','NEW',wfPill.indexOf('a sample of '+nS.toLocaleString()+' of the '+(+B.trades).toLocaleString()+' walk-forward trades')>=0,wfPill);
    var K=kpi(), UW=(FIXW.gate_validate||{}).ungated_wf||{};
    A('R6 1E exact WF Sharpe / Sortino = the champion held constant','NEW',kc(K,'SHARPE','WF')===(+UW.sharpe).toFixed(2)&&kc(K,'SORTINO','WF')===(+UW.sortino).toFixed(2),'WF SHARPE '+kc(K,'SHARPE','WF')+' SORTINO '+kc(K,'SORTINO','WF')+' expect '+UW.sharpe+'/'+UW.sortino);
    var LBv=FIXW.validate.lockbox||{};
    A('R7 1E exact LB Sortino follows the lockbox strip','NOREG',kc(K,'SORTINO','LB')===(+LBv.sortino).toFixed(2)&&kc(K,'SHARPE','LB')===(+LBv.sharpe).toFixed(2),'LB '+kc(K,'SHARPE','LB')+'/'+kc(K,'SORTINO','LB'));
    A('R8 1E exact TOTAL Sharpe / Sortino unchanged','NOREG',kc(K,'SHARPE','TOTAL')===(+FIXW.validate.total_sharpe).toFixed(2)&&kc(K,'SORTINO','TOTAL')===(+FIXW.validate.total_sortino).toFixed(2),'TOTAL '+kc(K,'SHARPE','TOTAL')+'/'+kc(K,'SORTINO','TOTAL'));
    var pill=q('span[title]').map(function(e){return e.getAttribute('title');}).filter(function(t){return t.indexOf('walk-forward PROCEDURE result')>=0;})[0]||'';
    A('R9 WF OOS pill: fold count + the block','NEW',pill.indexOf(FL.length+' folds')>=0&&pill.indexOf('see 1C for the curve')>=0&&pill.indexOf('PF '+(+B.profit_factor).toFixed(2))>=0&&pill.indexOf('eight folds')<0,pill);
    var mtEx=infopops(/Three sections/);
    A('R10 1E info text on the exact path','NEW',mtEx.length>=1&&mtEx.every(function(t){return t.indexOf('champion held constant over the walk-forward years')>=0;}),JSON.stringify(mtEx.map(function(t){return t.slice(0,140);})));
    var mtExact=mtEx[0]||'';
    var knetW=K&&K.cell['NET P&L']?K.cell['NET P&L'].join('|'):'';
    var tipEx=testTip();
    A('R10b walk-forward test label hover, exact path: a separate reading from the champion columns, never in TOTAL','NEW',tipEx.indexOf('never added into TOTAL')>=0&&tipEx.indexOf('holds the champion constant')>=0,tipEx);
    var chipTc=q('[data-wfochips]').map(function(e){return norm(e.textContent);}).join(' || ');
    A('R1b chips read apart as plain text (a space between chips)','NEW',chipTc.indexOf('NET '+fmtUsd(sN*M)+' PF ')>=0&&chipTc.indexOf('TRADES '+(+B.trades).toLocaleString()+' ')>=0,chipTc);

    // ── 1C chart names: full-screen title + saved-height key (the page's own readers) ────────
    A('K0 the page chart-name readers were found in the app script','NOREG',!!keyOf&&!!findHdr,helpErr||('keyOf '+typeof keyOf+' findHdr '+typeof findHdr));
    if(keyOf&&findHdr){
      var hdrOf=function(b){var h=b?findHdr(b):null;return h?norm(h.textContent):'';};
      var chk1C=function(id,kind,label){var fb=foldBox(),t=hdrOf(fb),k=fb?keyOf(fb):null;
        A(id,kind,!!fb&&/^1C\b/.test(t)&&t.indexOf('WALK-FORWARD')>=0&&k==='rsz_1C',label+' title='+t.slice(0,140)+' key='+k);};
      render({},[lite(FIXW)],[full(FIXW)],FIXW.id);
      chk1C('K1 block run: the fold bars keep the 1C title and the 1C saved-height key','NOREG','block');
      var cb=cboxOf(q('[data-wfocurve]')[0]),cT=hdrOf(cb),cKey=cb?keyOf(cb):null;
      var allK=q('#res-detail .rschart-box').map(function(b){return keyOf(b);});
      A('K2 the walk-forward test curve has its own title and its own saved-height key','NEW',!!cb&&cT.indexOf('WALK-FORWARD TEST')===0&&cT.length<140&&!!cKey&&allK.filter(function(k){return k===cKey;}).length===1,
        'title='+cT.slice(0,160)+' key='+cKey+' all keys='+JSON.stringify(allK));
      render({},[lite(FIXB)],[full(FIXB)],FIXB.id);
      chk1C('K3 run saved before the block: the fold bars keep the 1C title and key','NOREG','base');
      render({wfView:'alt'},[lite(FIXW)],[full(FIXW)],FIXW.id);
      chk1C('K4 comparison scheme view: the fold bars keep the 1C title and key','NOREG','alt');
      render({rszH:{rsz_1C:300}},[lite(FIXW)],[full(FIXW)],FIXW.id);
      var fb5=foldBox(),cb5=cboxOf(q('[data-wfocurve]')[0]);
      A('K5 a saved 1C height still sizes the fold bars on a run with the block, and not the curve','NEW',!!fb5&&fb5.style.height==='300px'&&!!cb5&&cb5.style.height!=='300px',
        'fold bars '+(fb5?fb5.style.height:'none')+' curve '+(cb5?cb5.style.height:'none'));
      if(cKey){var o6={};o6[cKey]=150;render({rszH:o6},[lite(FIXW)],[full(FIXW)],FIXW.id);
        var fb6=foldBox(),cb6=cboxOf(q('[data-wfocurve]')[0]);
        A('K6 the curve saved height sizes only the curve','NEW',!!cb6&&cb6.style.height==='150px'&&!!fb6&&fb6.style.height!=='150px','curve '+(cb6?cb6.style.height:'none')+' fold bars '+(fb6?fb6.style.height:'none'));}
    }

    // ── 1C curve geometry in every report layout ────────────────────────────────────────────
    var geoBad=[],geoOk=[],geoSkip=[];
    ['classic','neo','funnel','pills','dense','gauges'].forEach(function(lay){['3','1'].forEach(function(cols){
      var cg=render({repLayout:lay,repCols:cols},[lite(FIXW)],[full(FIXW)],FIXW.id);
      if(cg!=='OK'){geoBad.push(lay+'/'+cols+' render '+String(cg).slice(0,120));return;}
      if(!foldBox()&&!q('[data-wfocurve]').length){geoSkip.push(lay+'/'+cols);return;}
      var g=geo(lay+'/'+cols);
      // ...and in every layout the fold bars keep the 1C key while the curve key is its own and unique
      if(keyOf){var fbL=foldBox(),cbL=cboxOf(q('[data-wfocurve]')[0]),kL=cbL?keyOf(cbL):null,allL=q('#res-detail .rschart-box').map(function(b){return keyOf(b);});
        if(!fbL||keyOf(fbL)!=='rsz_1C'){g.ok=false;g.why+=' fold bars key '+(fbL?keyOf(fbL):'none');}
        if(!kL||allL.filter(function(k){return k===kL;}).length!==1){g.ok=false;g.why+=' curve key '+kL+' among '+JSON.stringify(allL);}}
      (g.ok?geoOk:geoBad).push(g.why);});});
    A('L1 1C curve fits its own panel in every report layout: caption, drag grip and fold bars stay clear','NEW',geoOk.length>=8&&!geoBad.length,
      'ok '+geoOk.length+' ['+geoOk.join(', ')+'] skipped ['+geoSkip.join(', ')+'] BAD: '+geoBad.join(' | '));

    // ── 1E exact path: the WALK-FORWARD column is the champion held constant, so the block never touches it ──
    var noBlk=function(x){var c=clone(x);delete c.validate.wf_oos;return c;};
    var ungWF=function(x,f){['gate_validate','ml_gate'].forEach(function(g){if(x[g]&&x[g].ungated_wf)f(x[g].ungated_wf);});return x;};
    var wfCol=function(doc){render({},[lite(doc)],[full(doc)],doc.id);var KK=kpi();if(!KK||KK.col.WF==null)return null;var oo={};
      Object.keys(KK.cell).forEach(function(l){oo[l]=[KK.cell[l][KK.col.WF],KK.title[l][KK.col.WF]];});return oo;};
    var exV={
      'as saved':clone(FIXW),
      'champion PF under 1 and fold PF under 1':(function(){var x=ungWF(clone(FIXW),function(u){u.profit_factor=0.95;u.total_pnl=-500;});
        x.top10_results.forEach(function(f){if(f&&f.fold!=null)f.oos_pf=0.9;});return x;})(),
      'gate study without a drawdown':ungWF(clone(FIXW),function(u){delete u.max_drawdown;}),
      'gate study without PF and win rate':ungWF(clone(FIXW),function(u){delete u.profit_factor;delete u.win_rate;})};
    var exBad=[],exCols={};
    Object.keys(exV).forEach(function(k){var a=wfCol(exV[k]),b=wfCol(noBlk(exV[k]));exCols[k]=a;
      if(!a||!b){exBad.push(k+': no WF column');return;}
      var dd=Object.keys(a).filter(function(l){return JSON.stringify(a[l])!==JSON.stringify(b[l]);});
      if(dd.length)exBad.push(k+': '+dd.map(function(l){return l+' '+JSON.stringify(a[l][0])+' vs '+JSON.stringify(b[l][0]);}).join(', '));});
    A('E1 1E exact WALK-FORWARD column is identical with and without the block (4 gate-study shapes)','NOREG',!exBad.length,exBad.join(' | '));
    var cPF=exCols['gate study without PF and win rate']||{},cLo=exCols['champion PF under 1 and fold PF under 1']||{},cDD=exCols['gate study without a drawdown']||{};
    var cell=function(o,l){return (o[l]||[])[0];};
    A('E2 exact WF: a PF or win rate the gate study lacks is a dash, never a walk-forward test or fold figure','NEW',cell(cPF,'PF')==='—'&&cell(cPF,'WIN %')==='—','PF '+cell(cPF,'PF')+' WIN % '+cell(cPF,'WIN %'));
    A('E3 exact WF: champion PF under 1 leaves AVG WIN, AVG LOSS and DD (R) dashed','NOREG',cell(cLo,'AVG WIN')==='—'&&cell(cLo,'AVG LOSS')==='—'&&cell(cLo,'DD (R)')==='—',
      'AVG WIN '+cell(cLo,'AVG WIN')+' AVG LOSS '+cell(cLo,'AVG LOSS')+' DD (R) '+cell(cLo,'DD (R)'));
    A('E4 exact WF: a drawdown the gate study lacks is never the walk-forward test drawdown','NOREG',!!cDD.DD&&String(cDD.DD[1]).indexOf('Exact: '+fmtUsd(Math.abs(B.max_drawdown)*M))<0,JSON.stringify(cDD.DD));

    var cFn=render({eqTab:'funnel'},[lite(FIXW)],[full(FIXW)],FIXW.id); clean('funnel',cFn);
    var tFn=tips().filter(function(t){return t.indexOf('<b>WF fold f'+B.folds[0].f+'</b>')===0;});
    A('R4b report funnel fold stripe hover dates from the block','NEW',tFn.length>=1&&tFn.every(function(t){return t.indexOf(mdy(B.folds[0].from))>=0&&t.indexOf(B.folds[0].trades+' trades')>=0;}),'n='+tFn.length+' '+JSON.stringify(tFn.slice(0,1)));

    var fBF=clone(FIXW);fBF.validate.wf_oos.src='backfill';
    var cBF=render({},[lite(fBF)],[full(fBF)],FIXW.id); clean('backfill',cBF);
    A('R11 backfilled block is marked','NEW',q('[data-wfobackfill]').length===1&&txt('[data-wfochips]').join(' ').indexOf('rebuilt after the run')>=0,txt('[data-wfochips]').join(' '));

    var cAlt=render({wfView:'alt'},[lite(FIXW)],[full(FIXW)],FIXW.id); clean('alt',cAlt);
    A('R12 comparison scheme hides the curve','NEW',q('[data-wfocurve]').length===0&&q('[data-wfochips]').length===0&&txt('[data-wfowhy]').join(' ').indexOf('covers the primary fold scheme only')>=0,
      'curves='+q('[data-wfocurve]').length+' why='+txt('[data-wfowhy]').join(' | '));

    var fLg=noGate(FIXW), cLg=render({},[lite(fLg)],[full(fLg)],FIXW.id); clean('legacy',cLg);
    var KL=kpi();
    A('R13 1E legacy WF column: drawdown, Sharpe, Sortino, PF, days from the block','NEW',
      (kt(KL,'DD','WF')||'').indexOf('Exact: '+fmtUsd(Math.abs(B.max_drawdown)*M))>=0&&kc(KL,'SHARPE','WF')===(+B.sharpe).toFixed(2)&&kc(KL,'SORTINO','WF')===(+B.sortino).toFixed(2)
      &&kc(KL,'PF','WF')===(+B.profit_factor).toFixed(2)&&kc(KL,'DAYS','WF')===Math.round(B.years*365.25).toLocaleString()&&kc(KL,'TRADES','WF')===sT.toLocaleString(),
      'DD title='+kt(KL,'DD','WF')+' SH '+kc(KL,'SHARPE','WF')+' SO '+kc(KL,'SORTINO','WF')+' PF '+kc(KL,'PF','WF')+' DAYS '+kc(KL,'DAYS','WF')+' TR '+kc(KL,'TRADES','WF'));
    var mtLg=infopops(/Three sections/);
    A('R14 1E info text differs by path','NEW',mtLg.length>=1&&mtLg[0].indexOf('sum to TOTAL')>=0&&mtLg[0].indexOf('gives the WALK-FORWARD drawdown')>=0&&mtLg[0]!==mtExact,JSON.stringify(mtLg.map(function(t){return t.slice(-160);})));
    var tipLg=testTip();
    A('R14b walk-forward test hover + 1E info, legacy path: the WF column reads these trades and its NET is in the sum','NEW',
      tipLg.indexOf('sum to TOTAL')>=0&&tipLg.indexOf('never added into TOTAL')<0&&mtLg.length>=1&&mtLg.every(function(t){return t.indexOf('never added into TOTAL')<0;}),
      'label='+tipLg+' || info tail='+(mtLg[0]||'').slice(-200));

    var fBL=noGate(FIXB), cBL=render({},[lite(fBL)],[full(fBL)],FIXB.id); clean('base-legacy',cBL);
    var KB=kpi();
    A('R15 1E legacy WF on a run saved before the block: dashes with the reason','NEW',kc(KB,'DD','WF')==='—'&&(kt(KB,'DD','WF')||'').indexOf('saved before walk-forward detail was recorded')>=0&&kc(KB,'SHARPE','WF')==='—'&&kc(KB,'SORTINO','WF')==='—',
      'DD '+kc(KB,'DD','WF')+' title='+kt(KB,'DD','WF')+' SH '+kc(KB,'SHARPE','WF'));

    var cB=render({},[lite(FIXB)],[full(FIXB)],FIXB.id); clean('base',cB);
    var pillB=q('span[title]').map(function(e){return e.getAttribute('title');}).filter(function(t){return t.indexOf('walk-forward PROCEDURE result')>=0;})[0]||'';
    A('R16 run saved before the block: no curve, the reason, fold count on the pill','NEW',q('[data-wfocurve]').length===0&&txt('[data-wfowhy]').join(' ').indexOf('No walk-forward curve — this run was saved before walk-forward detail was recorded')>=0&&pillB.indexOf(FL.length+' folds')>=0,
      'why='+txt('[data-wfowhy]').join(' | ')+' pill='+pillB.slice(0,80));
    var KB2=kpi(),knetB=KB2&&KB2.cell['NET P&L']?KB2.cell['NET P&L'].join('|'):'';
    A('R8b 1E champion columns do not move when the block arrives','NOREG',!!knetW&&knetW===knetB&&kc(KB2,'DD','TOTAL')===kc(K,'DD','TOTAL')&&kc(KB2,'TRADES','WF')===kc(K,'TRADES','WF'),knetW+' vs '+knetB);

    if(out._v){
      var cM=render({},[lite(FIXW)],[out._v.d3],FIXW.id); clean('mismatch',cM);
      A('R17 mismatched block: no curve, the reason, recorded','NEW',q('[data-wfocurve]').length===0&&txt('[data-wfowhy]').join(' ').indexOf('does not match')>=0&&!!(w._wfoBad&&w._wfoBad[String(FIXW.id)]),
        'why='+txt('[data-wfowhy]').join(' | '));
      var cZ=render({},[lite(FIXW)],[out._v.d8],FIXW.id); clean('zero',cZ);
      A('R18 zero-trade block: chips, no curve, the reason','NEW',q('[data-wfocurve]').length===0&&txt('[data-wfochips]').join(' ').indexOf('TRADES 0')>=0&&txt('[data-wfowhy]').join(' ').indexOf('took no trades in the walk-forward folds')>=0,
        'chips='+txt('[data-wfochips]').join(' ')+' why='+txt('[data-wfowhy]').join(' | '));
      var cY=render({},[lite(FIXW)],[out._v.d13],FIXW.id); clean('noyears',cY);
      var shChip=q('[data-wfochips] span[title]').filter(function(e){return /^SHARPE/.test((e.innerText||'').trim());})[0];
      A('R19 no window dates: Sharpe dashes with the reason','NEW',!!shChip&&/SHARPE\s*—/.test(shChip.innerText)&&shChip.getAttribute('title').indexOf('window dates were not saved')>=0,shChip?(shChip.innerText+' / '+shChip.getAttribute('title')):'no chip');
      var f10=noGate(FIXW);var r10=f10.top10_results.filter(function(f){return f&&f.fold!=null;})[0];r10.oos_pf=0;
      var c10=render({},[lite(f10)],[full(f10)],FIXW.id); clean('pf0-legacy',c10);
      A('R20 a fold with PF 0: legacy WF PF is the exact block PF','NEW',kc(kpi(),'PF','WF')===(+B.profit_factor).toFixed(2),'WF PF '+kc(kpi(),'PF','WF')+' expect '+B.profit_factor);
      var fNP=noGate(FIXB);fNP.top10_results.forEach(function(f){if(f&&f.fold!=null)delete f.oos_pf;});
      var cNP=render({},[lite(fNP)],[full(fNP)],FIXB.id); clean('nopf-legacy',cNP);
      A('R21 legacy run without the block whose folds saved no PF: WF PF is a dash, not 0.00','NOREG',kc(kpi(),'PF','WF')==='—','WF PF '+kc(kpi(),'PF','WF'));
    }

    // ── THE FOUR LOW FINDINGS THE VERIFICATION LEFT OPEN (every F case fails on the build before) ──
    // L1 A fold that tested no trade must not take a stretch of the curve off the fold before it. The
    //    engine maps a fold to the earliest saved point that already reflects its first trade, so a fold
    //    at the very end with nothing to reflect falls back to the LAST point - which is inside its
    //    neighbour. Here fold 9 tests bars but takes no trade, exactly as a live run can.
    var _fl0=(FIXW.top10_results||[]).filter(function(f){return f&&f.fold!=null;});
    var nfE=(+_fl0[_fl0.length-1].fold)+1;
    var dEmp=(function(){var x=clone(FIXW),b=x.validate.wf_oos,row=clone(_fl0[_fl0.length-1]);
      row.fold=nfE;row.oos_trades=0;row.oos_pnl=0;row.oos_wins=0;row.oos_pf=0;row.total_pnl=0;
      x.top10_results.push(row);
      b.n_folds=_fl0.length+1;
      b.folds=b.folds.concat([{f:nfE,from:b.to,to:b.to,trades:0,net:0}]);
      b.fold_idx=b.fold_idx.concat([b.equity.length-1]);   // the engine's own fallback for a fold past the last kept point
      return x;})();
    var cEm=render({},[lite(dEmp)],[full(dEmp)],FIXW.id); clean('emptyfold',cEm);
    var OE=H.of(full(dEmp),M)||{};
    var svgE=q('[data-wfocurve] svg')[0],vbE=svgE?String(svgE.getAttribute('viewBox')||'').split(/\s+/):[],CWe=(vbE.length>2)?+vbE[2]:0;
    var stE=q('[data-wfofold]'),mkE=q('[data-wfofoldnotr="'+nfE+'"]')[0];
    var lastE=stE[stE.length-1],endE=lastE?(+lastE.getAttribute('x')+ +lastE.getAttribute('width')):null;
    var mkX=mkE?+mkE.getAttribute('x'):null,mkTip=mkE?(mkE.getAttribute('data-tip')||''):'';
    A('F1 an empty last fold draws a no-trades marker at the end and leaves the fold before it whole','NEW',
      stE.length===_fl0.length&&!!mkE&&mkTip.indexOf('no trades')>=0&&CWe>0&&endE!=null&&endE>=CWe-0.6&&mkX!=null&&mkX>=CWe-2
      &&Array.isArray(OE.foldStart)&&OE.foldStart[_fl0.length]===null&&Array.isArray(OE.foldIdx)&&OE.foldIdx.length===_fl0.length,
      'stripes='+stE.length+' of '+_fl0.length+' marker x='+mkX+' of '+CWe+' last stripe ends '+endE+' tip='+mkTip+' starts='+JSON.stringify(OE.foldStart));
    var barE=tips().filter(function(t){return t.indexOf('<b>Fold f'+nfE+'</b>')===0&&t.indexOf('in-sample')>=0;})[0]||'';
    A('F1b the empty fold hover says no trades, not 0 trades','NEW',barE.indexOf('no trades')>=0&&barE.indexOf('0 trades')<0,barE);
    // ...and an empty fold in the MIDDLE: its marker must stay reachable, and the fold before it must
    //    run all the way to the fold after it, losing nothing.
    var midF=(_fl0.length>=5)?(+_fl0[3].fold):null;
    var dMid=(function(){if(midF==null)return null;var x=clone(FIXW),b=x.validate.wf_oos;
      var row=x.top10_results.filter(function(f){return f&&String(f.fold)===String(midF);})[0];
      var lostT=+row.oos_trades||0,lostN=+row.oos_pnl||0;
      row.oos_trades=0;row.oos_pnl=0;row.oos_wins=0;row.oos_pf=0;
      b.trades=b.trades-lostT;b.net=Math.round((b.net-lostN)*10)/10;
      b.folds.forEach(function(f){if(String(f.f)===String(midF)){f.trades=0;f.net=0;}});
      return x;})();
    if(dMid){var cMd=render({},[lite(dMid)],[full(dMid)],FIXW.id); clean('emptymidfold',cMd);
      var stM=q('[data-wfofold]'),mkM=q('[data-wfofoldnotr="'+midF+'"]')[0];
      var pos=function(f){var e=q('[data-wfofold="'+f+'"]')[0];return e?{x:+e.getAttribute('x'),w:+e.getAttribute('width')}:null;};
      var pB=pos(midF-1),pA=pos(midF+1),mX=mkM?+mkM.getAttribute('x'):null;
      A('F1c an empty middle fold: a reachable marker, and its neighbours keep every point between them','NEW',
        stM.length===_fl0.length-1&&!!mkM&&(mkM.getAttribute('data-tip')||'').indexOf('no trades')>=0&&!!pB&&!!pA
        &&Math.abs((pB.x+pB.w)-pA.x)<=0.2&&mX!=null&&(mX+1.4)<=pA.x+0.01&&!q('[data-wfofold="'+midF+'"]').length,
        'stripes='+stM.length+' of '+(_fl0.length-1)+' before='+JSON.stringify(pB)+' after='+JSON.stringify(pA)+' marker x='+mX);}
    // ...and SEVERAL untraded folds in a ROW (the repair a reviewer proved was missing): they all point
    //    at the same next fold that traded, so ONE edge has to hold more than one marker. Each needs its
    //    own slot, or the last one drawn sits exactly on top of the ones before it and their hovers can
    //    never be reached by a mouse - silent information loss, with no error anywhere. The markers are
    //    also drawn after every stripe, so no stripe can cover one either.
    var zeroFold=function(x,fn){var b=x.validate.wf_oos;
      var row=x.top10_results.filter(function(f){return f&&String(f.fold)===String(fn);})[0];
      if(!row)return;
      b.trades=b.trades-(+row.oos_trades||0);b.net=b.net-(+row.oos_pnl||0);   // block stays consistent with the fold rows, so the reader still accepts it
      row.oos_trades=0;row.oos_pnl=0;row.oos_wins=0;row.oos_pf=0;
      b.folds.forEach(function(f){if(String(f.f)===String(fn)){f.trades=0;f.net=0;}});};
    // every rect of the curve in the order the browser paints them: a later one covers an earlier one
    var cRects=function(){var s=q('[data-wfocurve] svg')[0];return s?Array.prototype.slice.call(s.querySelectorAll('rect')):[];};
    var cRect=function(sel){var R=cRects(),e=q('[data-wfocurve] svg '+sel)[0];
      return e?{x:+e.getAttribute('x'),w:+e.getAttribute('width'),z:R.indexOf(e),tip:(e.getAttribute('data-tip')||'')}:null;};
    var lastStripeZ=function(){var R=cRects(),z=-1;R.forEach(function(e,i){if(e.hasAttribute('data-wfofold'))z=i;});return z;};
    var jx=function(o){return o?('x='+o.x+' w='+o.w+' drawn#'+o.z):'missing';};
    var noTr=function(o){return !!o&&o.tip.indexOf('no trades')>=0;};
    var adjF=(_fl0.length>=6)?[+_fl0[3].fold,+_fl0[4].fold]:null;
    var dAdj=(function(){if(!adjF)return null;var x=clone(FIXW);adjF.forEach(function(fn){zeroFold(x,fn);});return x;})();
    if(dAdj){var cAj=render({},[lite(dAdj)],[full(dAdj)],FIXW.id); clean('emptyadjfolds',cAj);
      var a1=cRect('[data-wfofoldnotr="'+adjF[0]+'"]'),a2=cRect('[data-wfofoldnotr="'+adjF[1]+'"]');
      var aB=cRect('[data-wfofold="'+(adjF[0]-1)+'"]'),aA=cRect('[data-wfofold="'+(adjF[1]+1)+'"]'),aZ=lastStripeZ();
      A('F1d two untraded folds in a row: two markers side by side, neither drawn on top of the other','NEW',
        !!a1&&!!a2&&!!aB&&!!aA&&a1.x>=0&&(a1.x+a1.w)<=a2.x+0.01&&(a2.x+a2.w)<=aA.x+0.01
        &&noTr(a1)&&noTr(a2)&&a1.z>aZ&&a2.z>aZ
        &&!q('[data-wfofold="'+adjF[0]+'"]').length&&!q('[data-wfofold="'+adjF[1]+'"]').length
        &&Math.abs((aB.x+aB.w)-aA.x)<=0.2,
        'f'+adjF[0]+' '+jx(a1)+' | f'+adjF[1]+' '+jx(a2)+' | fold before '+jx(aB)+' | fold after '+jx(aA)+' | last stripe drawn#'+aZ);}
    // ...and a run of untraded folds at the very START, where the first fold that traded begins at the
    //    first saved point and leaves no room at all to their left: the run slides right as one and the
    //    markers still land on separate slots, on top of that first wide stripe.
    var leadF=(_fl0.length>=6)?[+_fl0[0].fold,+_fl0[1].fold,+_fl0[2].fold]:null;
    var dLead=(function(){if(!leadF)return null;var x=clone(FIXW);leadF.forEach(function(fn){zeroFold(x,fn);});
      // with nothing traded before it, the engine maps the first fold that traded to the FIRST saved point
      x.validate.wf_oos.fold_idx=x.validate.wf_oos.fold_idx.map(function(v,j){return (j<=leadF.length)?0:v;});
      return x;})();
    if(dLead){var cLd=render({},[lite(dLead)],[full(dLead)],FIXW.id); clean('emptyleadfolds',cLd);
      var L1=cRect('[data-wfofoldnotr="'+leadF[0]+'"]'),L2=cRect('[data-wfofoldnotr="'+leadF[1]+'"]'),L3=cRect('[data-wfofoldnotr="'+leadF[2]+'"]');
      var LA=cRect('[data-wfofold="'+(leadF[2]+1)+'"]'),LZ=lastStripeZ();
      A('F1e untraded folds at the very start, with no room to their left: separate slots, none covered','NEW',
        !!L1&&!!L2&&!!L3&&!!LA&&LA.x<=0.01&&L1.x>=0&&(L1.x+L1.w)<=L2.x+0.01&&(L2.x+L2.w)<=L3.x+0.01
        &&noTr(L1)&&noTr(L2)&&noTr(L3)&&L1.z>LZ&&L2.z>LZ&&L3.z>LZ,
        'f'+leadF[0]+' '+jx(L1)+' | f'+leadF[1]+' '+jx(L2)+' | f'+leadF[2]+' '+jx(L3)+' | first fold that traded '+jx(LA)+' | last stripe drawn#'+LZ);}

    // L2 The engine also leaves Sortino empty when no trade lost, and Sharpe empty when every trade
    //    made the same amount. Neither is a trade-count problem, so neither may say so.
    var dWin=(function(){var x=clone(FIXW),b=x.validate.wf_oos;
      b.gross_loss=0;b.gross_win=b.net;b.avg_loss=null;b.profit_factor=null;b.wins=b.trades;b.win_rate=100;b.sharpe=null;b.sortino=null;return x;})();
    var dW=full(dWin),soW=H.why(dW,'so'),shW=H.why(dW,'sh');
    A('F2 no walk-forward trade lost: the Sortino reason is the missing losing side, not the trade count','NEW',
      soW.indexOf('no walk-forward trade lost, so there is nothing to divide by')>=0&&soW.indexOf('too few')<0&&soW.indexOf('window dates')<0,soW);
    A('F2b every trade the same amount: the Sharpe reason is the missing spread, not the trade count','NEW',
      shW.indexOf('no spread to divide by')>=0&&shW.indexOf('too few')<0,shW);
    var d2t=(function(){var x=clone(FIXW),b=x.validate.wf_oos,f=clone(_fl0[0]);
      f.oos_trades=2;f.oos_pnl=10;f.oos_wins=1;f.oos_pf=2;x.top10_results=[f];
      b.n_folds=1;b.trades=2;b.wins=1;b.win_rate=50;b.net=10;b.gross_win=20;b.gross_loss=10;b.profit_factor=2;
      b.avg_win=20;b.avg_loss=10;b.max_drawdown=10;b.sharpe=null;b.sortino=null;b.equity=[-10,10];b.equity_n=2;
      b.fold_idx=[0];b.folds=[{f:f.fold,from:b.from,to:b.to,trades:2,net:10}];return x;})();
    var sh2=H.why(full(d2t),'sh');
    A('F2c only two walk-forward trades: then the reason IS the trade count','NEW',sh2.indexOf('too few walk-forward trades')>=0&&sh2.indexOf('at least three')>=0,sh2);
    var cW2=render({},[lite(dWin)],[full(dWin)],FIXW.id); clean('nolosses',cW2);
    var soChip=q('[data-wfochips] span[title]').filter(function(e){return /^SORTINO/.test(norm(e.textContent));})[0];
    A('F2d the 1C Sortino chip carries that reason','NEW',!!soChip&&/SORTINO\s*—/.test(norm(soChip.textContent))&&(soChip.getAttribute('title')||'').indexOf('nothing to divide by')>=0,
      soChip?(norm(soChip.textContent)+' / '+soChip.getAttribute('title')):'no chip');

    // L3 A block whose window dates were never saved: the legacy walk-forward column used to divide by
    //    the bar-count estimate while the 1C chip beside it dashed. The two must agree, and the column
    //    heading must say which window its dates and DAYS describe.
    var dNoW=(function(){var x=noGate(clone(FIXW)),b=x.validate.wf_oos;b.years=null;b.from=null;b.to=null;b.sharpe=null;b.sortino=null;
      b.folds.forEach(function(f){f.from=null;f.to=null;});return x;})();
    var cNW=render({},[lite(dNoW)],[full(dNoW)],FIXW.id); clean('nowindow-legacy',cNW);
    var KN=kpi(),tipN=kpiHeadTip('WF'),marN=chipOf('MAR / YR');
    A('F3 legacy WF with no saved window: MAR, ROC and R / YR blank like the 1C chip, DAYS kept, heading says which window','NEW',
      kc(KN,'MAR','WF')==='—'&&marN==='—'&&(kt(KN,'MAR','WF')||'').indexOf('window dates are not saved')>=0
      &&kc(KN,'R / YR','WF')==='—'&&kc(KN,'ROC % / YR','WF')==='—'&&kc(KN,'DAYS','WF')!=='—'
      &&tipN.indexOf('estimated from the fold bar counts')>=0,
      'MAR '+kc(KN,'MAR','WF')+' chip '+marN+' R/YR '+kc(KN,'R / YR','WF')+' ROC '+kc(KN,'ROC % / YR','WF')+' DAYS '+kc(KN,'DAYS','WF')+' heading='+tipN.slice(-240));
    var cLg2=render({},[lite(fLg)],[full(fLg)],FIXW.id); clean('legacy-window',cLg2);
    var KL2=kpi(),marL=chipOf('MAR / YR'),tipL=kpiHeadTip('WF'),mtL=infopops(/Three sections/)[0]||'',tstL=testTip();
    A('F3b with the window saved, the legacy WF MAR equals the 1C chip and the heading names that window','NEW',
      !!marL&&marL!=='—'&&kc(KL2,'MAR','WF')===marL+'×'&&tipL.indexOf(B.from+' to '+B.to)>=0,
      '1E '+kc(KL2,'MAR','WF')+' chip '+marL+' heading='+tipL.slice(-200));

    // ...and the PARALLEL view of the same table reads the same years, or draws no point at all
    var pTip=function(ph,ax){var t=tips().filter(function(t){return t.indexOf('<b>'+ph+'</b>')===0&&t.indexOf(' '+ax+'<br>')>0;})[0]||'';
      var m=t.match(/<br><b>([^<]*)<\/b>/);return m?m[1]:null;};
    var cPar=render({mtxView:'parallel'},[lite(fLg)],[full(fLg)],FIXW.id); clean('legacy-parallel',cPar);
    var parMar=pTip('WF','MAR'),parRpy=pTip('WF','R / YR');
    var cPar2=render({mtxView:'parallel'},[lite(dNoW)],[full(dNoW)],FIXW.id); clean('nowindow-parallel',cPar2);
    var parMarN=pTip('WF','MAR'),parRpyN=pTip('WF','R / YR'),parIsN=pTip('IS','MAR');
    A('F3c the PARALLEL view of 1E reads the same walk-forward years as the table','NEW',
      parMar===marL&&parMarN===null&&parRpyN===null&&parIsN!=null&&parRpy!=null,
      'with window MAR '+parMar+' (table '+marL+') R/YR '+parRpy+' || without window MAR '+parMarN+' R/YR '+parRpyN+' in-sample MAR still '+parIsN);

    // L4 One source per figure, named the same way by every hover on that screen.
    var ttl=function(K,l){return (kt(K,l,'WF')||'');};
    A('F4 legacy WF with the block: heading, info text, the 1C label and every cell name one source per figure','NEW',
      tipL.indexOf('NET and TRADES are pooled across the fold rows')>=0
      &&tipL.indexOf('PF and WIN % come from the saved walk-forward test when the run has one')>=0
      &&tipL.indexOf('NET, PF, WIN % and TRADES are pooled')<0
      &&mtL.indexOf('its PF and win % as well')>=0&&mtL.indexOf('stay pooled across the fold rows')>=0
      &&tstL.indexOf('PF and win % all come from here')>=0
      &&ttl(KL2,'PF').indexOf('comes from the saved walk-forward test')>=0&&ttl(KL2,'WIN %').indexOf('comes from the saved walk-forward test')>=0
      &&ttl(KL2,'DD').indexOf('comes from the saved walk-forward test')>=0&&ttl(KL2,'SHARPE').indexOf('comes from the saved walk-forward test')>=0
      &&ttl(KL2,'SORTINO').indexOf('comes from the saved walk-forward test')>=0,
      'heading='+tipL.slice(0,230)+' || PF cell='+ttl(KL2,'PF')+' || info tail='+mtL.slice(-200)+' || 1C label='+tstL.slice(0,160));
    var cBL2=render({},[lite(fBL)],[full(fBL)],FIXB.id); clean('base-legacy-source',cBL2);
    var KB3=kpi(),tipB=kpiHeadTip('WF');
    A('F4b legacy WF without the block: PF and WIN % say they are pooled, and the heading says the same','NEW',
      ttl(KB3,'PF').indexOf('pooled across the fold rows')>=0&&ttl(KB3,'WIN %').indexOf('pooled across the fold rows')>=0
      &&ttl(KB3,'PF').indexOf('saved walk-forward test')<0&&tipB.indexOf('are pooled across the fold rows when it does not')>=0,
      'PF cell='+ttl(KB3,'PF')+' || WIN % cell='+ttl(KB3,'WIN %')+' || heading='+tipB.slice(0,200));

    // ── Past Runs (projected rows only) ─────────────────────────────────────────────────
    var PLAIN=clone(FIXB);delete PLAIN.validate;PLAIN.id=305;
    var cP=render({},[lite(FIXW),lite(FIXBK),lite(PLAIN)],[],'999999'); clean('pastruns',cP);
    var RW=rows(), rw=RW.filter(function(r){return r.id===String(FIXW.id);})[0], rbk=RW.filter(function(r){return r.id===String(FIXBK.id);})[0];
    var wfTitle=function(r){return r?r.titles.filter(function(t){return /walk-forward/i.test(t)&&t.indexOf('whole-run total')<0;}).join(' || '):'';};
    A('P1 WF cell hover carries the block (projected row)','NEW',!!rw&&wfTitle(rw).indexOf('Walk-forward test (each fold re-tuned): net '+fmtUsd(sN*M))>=0&&wfTitle(rw).indexOf('PF '+(+B.profit_factor).toFixed(2))>=0&&wfTitle(rw).indexOf((+B.trades).toLocaleString()+' trades')>=0,wfTitle(rw));
    // the list reader must follow the PROJECTION: the same run read through a mask without the block reads as "saved before"
    var Lno=L.filter(function(f){return f!=='validate.wf_oos';}), pNo=project(FIXW,Lno);pNo.id=String(FIXW.id);
    render({},[mk(pNo,true)],[],'999999');var rNo=rows()[0];
    A('P1b the list reads what the mask projects (no block in the mask = saved before)','NEW',!!rNo&&wfTitle(rNo).indexOf('saved before walk-forward detail was recorded')>=0&&wfTitle(rNo).indexOf('Walk-forward test (each fold re-tuned)')<0,wfTitle(rNo));
    render({},[lite(FIXW),lite(FIXBK),lite(PLAIN)],[],'999999');
    A('P3 book row says a book has no walk-forward folds','NEW',!!rbk&&wfTitle(rbk).indexOf('a book trades frozen configurations')>=0,wfTitle(rbk));
    var cellsW=rw?rw.cells.join(' | '):'';
    var cP2=render({},[lite(FIXB),lite(FIXBK),lite(PLAIN)],[],'999999');
    var rb=rows().filter(function(r){return r.id===String(FIXB.id);})[0];
    A('P2 run saved before the block: WF cell hover gives the reason','NEW',!!rb&&wfTitle(rb).indexOf('saved before walk-forward detail was recorded')>=0,wfTitle(rb));
    A('P4 whole-run cells identical with and without the block','NOREG',!!rb&&cellsW===rb.cells.join(' | '),cellsW+'  VS  '+(rb?rb.cells.join(' | '):''));
    var sorts=['id','date','score','pnl','perday','maxdd','mar','pf','sharpe','wr','trd','days','took'], ordW={}, snap={};
    sorts.forEach(function(s){render({rfSort:s},[lite(FIXW),lite(FIXBK),lite(PLAIN)],[],'999999');ordW[s]=rows().map(function(r){return r.id;}).join(',');});
    var sameOrd=true, bad=[];
    sorts.forEach(function(s){render({rfSort:s},[lite(FIXB),lite(FIXBK),lite(PLAIN)],[],'999999');var rr=rows();snap[s]=rr.map(function(r){return r.id+' :: '+r.cells.join(' | ');});
      var o=rr.map(function(r){return r.id;}).join(',');if(o!==ordW[s]){sameOrd=false;bad.push(s+': '+o+' vs '+ordW[s]);}});
    A('P5 sort order identical with and without the block','NOREG',sameOrd,bad.join(' ; '));
    out.snap=snap;
    var nsP=clone(FIXW);delete nsP.validate.total_sharpe;var nsB=clone(FIXB);delete nsB.validate.total_sharpe;
    render({},[lite(nsP)],[],'999999');var tSh=(rows()[0]||{titles:[]}).titles.filter(function(t){return /whole-run Sharpe needs/.test(t);})[0]||'';
    render({},[lite(nsB)],[],'999999');var tShB=(rows()[0]||{titles:[]}).titles.filter(function(t){return /whole-run Sharpe needs/.test(t);})[0]||'';
    A('P7 Sharpe fallback hover is the walk-forward test Sharpe, only with the block','NEW',tSh.indexOf('Walk-forward Sharpe (per trade) '+(+B.sharpe).toFixed(2))>=0&&tShB.indexOf('Walk-forward Sharpe')<0&&tShB.indexOf('Out-of-sample Sharpe')<0,tSh+'  ||  '+tShB);

    // ── Books (whole document on the report) ─────────────────────────────────────────────
    var cBk=render({},[lite(FIXBK)],[full(FIXBK)],FIXBK.id); clean('book',cBk);
    var detBk=d.getElementById('res-detail'), tBk=detBk?(detBk.innerText||''):'';
    A('B1 book report: no walk-forward test figure, the book reason','NEW',q('[data-wfocurve]').length===0&&q('[data-wfochips]').length===0&&txt('[data-wfowhy]').join(' ').indexOf('a book trades frozen configurations')>=0,
      'why='+txt('[data-wfowhy]').join(' | '));
    A('B2 book report never prints the walk-forward test','NOREG',tBk.indexOf('WALK-FORWARD TEST')<0,'');

    // ══ P3 / P4 - THE BOARDS AND EXPLORE READ THE SAME SAVED WALK-FORWARD TEST ══════════
    //    The report (above) was the first reader. These cases cover the COMPARE tab's
    //    LEADERBOARD, its comparison table and its chart, the hosted PICK RUNS table, the
    //    hosted RUNBOARD and the EXPLORE run rows. Each renders PROJECTED rows, the way the
    //    live list screens read them. Money and trade counts must stay pooled from the fold
    //    results everywhere; the whole-run, tuning and lockbox stretches must not move at all.
    function rend2(prefs,runs,sub){
      sink.errors.length=0;sink.uncaught.length=0;
      var arr=w.eval('[]');runs.forEach(function(x){arr.push(x);});
      w.__runs=arr;
      return w.eval("(function(){try{localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(prefs||{}))+");"
        +"if(typeof APREF==='object'&&APREF){for(var k in APREF)delete APREF[k];var P="+JSON.stringify(prefs||{})+";for(var k2 in P)APREF[k2]=P[k2];}"
        +"runHistory=window.__runs;window._runFull={};window._runFullOrder=[];window._runHydrating={};window._wfoBad={};window._c2Open=new Set();window._starRuns=[];"
        +"activeTab='augur';augurSub='"+(sub||'cmp2')+"';augurRunSel=null;renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");}
    function clean2(call){return (call==='OK')&&!sink.errors.length&&!sink.uncaught.length;}
    function titles2(){return q('[title]').map(function(e){return e.getAttribute('title')||'';});}
    function anyText(s){var b=d.body?(d.body.innerText||''):'';if(b.indexOf(s)>=0)return true;
      return titles2().concat(q('[data-infopop]').map(function(e){try{return decodeURIComponent(e.getAttribute('data-infopop')||'');}catch(_){return '';}}))
        .some(function(t){return String(t).indexOf(s)>=0;});}
    // every table row on screen, by the label in its first cell: the cell texts and the reason
    //   hovers beside them. First row of a given label wins.
    function tbl2(){var o={c:{},t:{}};
      q('tr').forEach(function(tr){var tds=Array.prototype.slice.call(tr.children);if(tds.length<2)return;
        var lab=norm(tds[0].textContent);if(!lab||Object.prototype.hasOwnProperty.call(o.c,lab))return;
        o.c[lab]=tds.slice(1).map(function(td){return norm(td.textContent);});
        o.t[lab]=tds.slice(1).map(function(td){var s=td.querySelector('[title]');return s?(s.getAttribute('title')||''):(td.getAttribute('title')||'');});});
      return o;}
    function bestOn(lab){var tr=q('tr').filter(function(t){return norm((t.children[0]||{}).textContent)===lab;})[0];
      if(!tr)return null;return Array.prototype.slice.call(tr.children).slice(1).map(function(td){
        return {v:norm(td.textContent),best:/font-weight:\s*(700|bold)/.test(td.getAttribute('style')||'')};});}
    function famBig(){var e=q('.c2-row[data-c2fam] .c2-big')[0];
      return e?{v:norm(e.textContent),t:(e.getAttribute('title')||'')}:null;}
    // one EXPLORE run row, by run number, read through its own column headings
    function reRow(id){var h=q('tr th').map(function(x){return norm(x.textContent).replace(/[^A-Z /%$()]/g,'').trim();});
      var tr=q('tr[data-rerow]').filter(function(x){return (x.textContent||'').indexOf('#'+id)>=0;})[0];
      if(!tr)return null;var v={};
      h.forEach(function(nm,i){if(nm&&tr.cells[i]&&!(nm in v))v[nm]=norm(tr.cells[i].textContent);});
      return {v:v,t:function(nm){var i=h.indexOf(nm),td=(i>=0)?tr.cells[i]:null,s=td&&td.querySelector('[title]');
        return s?(s.getAttribute('title')||''):(td?(td.getAttribute('title')||''):'');}};}
    // the two money formats the boards use, mirrored so an expected figure is never re-typed
    var AB$=function(v){var a=Math.abs(v||0),sg=(v<0?'-$':'$');
      return a>=1e6?(sg+(a/1e6).toFixed(2).replace(/\.?0+$/,'')+'M'):(a>=1000?(sg+Math.round(a/1000)+'k'):(sg+Math.round(a)));};
    var ABR=function(v){var a=Math.abs(v);if(a>=1e6)return (a/1e6).toFixed(2).replace(/0$/,'').replace(/\.0?$/,'')+'M';
      if(a>=1e4)return String(Math.round(a/1e3))+'k';if(a>=1e3)return (a/1e3).toFixed(1)+'k';return String(Math.round(a));};
    var USD=function(v){return ((v<0)?'-$':'$')+Math.round(Math.abs(v)).toLocaleString();};
    // what the saved test says, read out of the fixture itself
    var POOL=sN*M, DDW=Math.abs(B.max_drawdown)*M, MARW=(POOL/B.years)/DDW, WRW=100*B.wins/B.trades;
    var LW2=lite(FIXW), LBK2=lite(FIXBK);
    var NOBID=String(+FIXB.id+900001);
    // the same run WITHOUT the saved test (the regression control), and a second run that never
    //   saved one (so the two can be picked together)
    var NOBLK=(function(){var x=clone(FIXW);delete x.validate.wf_oos;return lite(x);})();
    var NOB=(function(){var x=clone(FIXB);x.id=NOBID;x.strategy='ZNOBLK_1_0.py';x.starred=false;return lite(x,NOBID);})();
    var MM2=(function(){var x=clone(FIXW);x.validate.wf_oos.trades=x.validate.wf_oos.trades+1;return lite(x);})();
    var PN2=(function(){var x=clone(FIXW);x.validate.wf_oos.profit_factor=null;x.validate.wf_oos.gross_loss=0;return lite(x);})();
    var NW2=(function(){var x=clone(FIXW),b=x.validate.wf_oos;b.years=null;b.from=null;b.to=null;b.sharpe=null;b.sortino=null;
      b.folds.forEach(function(f){f.from=null;f.to=null;});return lite(x);})();
    var MAR3={};

    // ── P0b: a job that backfills the test must not leave an open report saying "not saved" ──
    (function(){var det='';
      try{
        w.__pjW=JSON.stringify(FIXW);w.__pjN=JSON.stringify((function(){var x=clone(FIXW);delete x.validate.wf_oos;return x;})());
        det=w.eval("(function(){var W=JSON.parse(window.__pjW),N=JSON.parse(window.__pjN);"
          +"window._runFull={};window._runFullOrder=[];window._runCfg={};"
          +"window._runFull[String(N.id)]=N;window._runFullOrder.push(String(N.id));window._runCfg[String(N.id)]=N;"
          +"var dropped=_wfoDropStale([W]),gone=!window._runFull[String(W.id)],cfgGone=!window._runCfg[String(W.id)],ord=window._runFullOrder.length;"
          +"window._runFull[String(W.id)]=W;var again=_wfoDropStale([W]),kept=!!window._runFull[String(W.id)];"
          +"return JSON.stringify({dropped:dropped,gone:gone,cfgGone:cfgGone,ord:ord,again:again,kept:kept});})()");
        var o=JSON.parse(det);
        A('p0b a backfilled test drops the cached whole document; an unchanged one is kept','NEW',
          o.dropped===1&&o.gone===true&&o.cfgGone===true&&o.ord===0&&o.again===0&&o.kept===true,det);
      }catch(e){A('p0b a backfilled test drops the cached whole document; an unchanged one is kept','NEW',false,'threw: '+String(e&&e.message||e));}})();

    // ── COMPARE beta, LEADERBOARD ────────────────────────────────────────────────────────
    var p3=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'mar'},[LW2]);
    var g1=famBig();MAR3.lead=g1?g1.v:null;
    A('p3a LEADERBOARD walk-forward MAR is the saved test drawdown, exact','NEW',
      clean2(p3)&&!!g1&&g1.v===MARW.toFixed(2),'call='+p3+' got '+(g1&&g1.v)+' want '+MARW.toFixed(2));
    var note3=q('.c2-note').map(function(e){return norm(e.textContent);}).join(' || ');
    A('p3c LEADERBOARD note says what walk-forward MAR is built on','NEW',
      note3.indexOf('MAR uses the drawdown of the walk-forward folds')>=0&&note3.indexOf('no run summary carries')<0,note3.slice(-300));
    var pillWf=titles2().filter(function(t){return t.indexOf('the walk-forward folds, each re-tuned on its own past')===0;});
    A('p3c2 the walk-forward stage pill says what the stretch is','NEW',pillWf.length>=1,'n='+pillWf.length);
    var p3b=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'rpy'},[LW2]);
    var g2=famBig();
    A('p3b LEADERBOARD walk-forward R / YR needs no saved split date','NEW',
      clean2(p3b)&&!!g2&&/^[0-9]+\.[0-9]$/.test(g2.v)&&+g2.v>0,'got '+(g2&&g2.v)+' title='+(g2&&g2.t));
    var p3d=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'mar'},[NOB]);
    var g3=famBig();
    A('p3d a run saved before the test dashes, and the dash says so','NEW',
      clean2(p3d)&&!!g3&&g3.v==='—'&&g3.t.indexOf('saved before walk-forward detail was recorded')>=0
      &&g3.t.indexOf('does not mark where the folds begin')<0,'got '+(g3&&g3.v)+' title='+(g3&&g3.t));
    var p3e=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'mar'},[MM2]);
    var g4=famBig();
    A('p3e a test that disagrees with its folds is refused, and the dash says so','NEW',
      clean2(p3e)&&!!g4&&g4.v==='—'&&g4.t.indexOf('does not match')>=0
      &&!!(w._wfoBad&&Object.keys(w._wfoBad).length),'title='+(g4&&g4.t)+' bad='+JSON.stringify(Object.keys(w._wfoBad||{})));
    var p3p=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'pf'},[PN2]);
    var g5=famBig();
    A('p3p no losing walk-forward trade: the profit factor dashes with its own reason','NEW',
      clean2(p3p)&&!!g5&&g5.v==='—'&&g5.t.indexOf('No walk-forward trade lost')>=0,'got '+(g5&&g5.v)+' title='+(g5&&g5.t));

    // ── COMPARE beta, the comparison table ───────────────────────────────────────────────
    var p3f=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id)],c2Heat:false},[LW2]);
    var T3=tbl2();
    A('p3f the comparison table on walk-forward: money pooled, risk from the saved test, no ~','NEW',
      clean2(p3f)&&!!T3.c['DRAWDOWN']
      &&T3.c['NET'][0]===USD(POOL)&&T3.c['TRADES'][0]===sT.toLocaleString()
      &&T3.c['DRAWDOWN'][0]==='$'+Math.round(DDW).toLocaleString()&&T3.c['MAR'][0]===MARW.toFixed(2)
      &&T3.c['SHARPE'][0]===(+B.sharpe).toFixed(2)&&T3.c['PF'][0]===(+B.profit_factor).toFixed(2)
      &&T3.c['WIN %'][0]===WRW.toFixed(1)+'%'&&T3.c['YEARS'][0]===(+B.years).toFixed(1)
      &&[T3.c['DRAWDOWN'][0],T3.c['MAR'][0],T3.c['PF'][0]].every(function(s){return s.indexOf('~')<0;}),
      'NET '+T3.c['NET']+' TR '+T3.c['TRADES']+' DD '+T3.c['DRAWDOWN']+' MAR '+T3.c['MAR']+' SH '+T3.c['SHARPE']
      +' PF '+T3.c['PF']+' WR '+T3.c['WIN %']+' YRS '+T3.c['YEARS']+' want DD $'+Math.round(DDW).toLocaleString()+' MAR '+MARW.toFixed(2));
    var p3q=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id)],c2Heat:false},[NW2]);
    var TN=tbl2();
    A('p3q a test with no saved window: the drawdown stands, MAR, years and Sharpe dash with the reason','NEW',
      clean2(p3q)&&!!TN.c['MAR']&&TN.c['DRAWDOWN'][0]==='$'+Math.round(DDW).toLocaleString()
      &&TN.c['MAR'][0]==='—'&&TN.c['YEARS'][0]==='—'&&TN.c['SHARPE'][0]==='—'
      &&(TN.t['MAR'][0]||'').indexOf('window dates are not saved')>=0
      &&(TN.t['SHARPE'][0]||'').indexOf('window dates were not saved')>=0,
      'DD '+TN.c['DRAWDOWN']+' MAR '+TN.c['MAR']+' / '+TN.t['MAR']+' YRS '+TN.c['YEARS']+' SH '+TN.t['SHARPE']);
    var mdiff=[];
    ['full','is','lb'].forEach(function(st){
      var a=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:st,cmpIds:[String(FIXW.id)],c2Heat:false},[LW2]);
      var ta=JSON.stringify(tbl2());
      var b=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:st,cmpIds:[String(FIXW.id)],c2Heat:false},[NOBLK]);
      var tb=JSON.stringify(tbl2());
      if(a!=='OK'||b!=='OK'||ta.length<200||ta!==tb)mdiff.push(st+(ta===tb?' (render '+a+'/'+b+')':' differs'));});
    A('p3g the whole-run, tuning and lockbox tables are untouched by the saved test','NOREG',!mdiff.length,mdiff.join(' ; '));

    // ── COMPARE beta, the chart ──────────────────────────────────────────────────────────
    var p3h=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id)]},[LW2]);
    var SS=w._cmpEqxSeries||[],S1=SS[0]||{};
    A('p3h the chart draws the test own curve: dashed end to end, its own dates, no trade list','NEW',
      clean2(p3h)&&SS.length===1&&S1.wfi===0&&S1.li===null&&S1.blot===null&&!S1.wfFolds&&!S1.wfInfo
      &&Array.isArray(S1.span)&&S1.span[0]===B.from&&S1.span[1]===B.to
      &&Array.isArray(S1.eq)&&S1.eq.length===B.equity.length+1&&S1.eq[0]===0
      &&anyText('DASHED = WALK-FORWARD FOLDS, JOINED END TO END'),
      'n='+SS.length+' wfi='+S1.wfi+' li='+S1.li+' blot='+JSON.stringify(S1.blot)+' span='+JSON.stringify(S1.span)
      +' eq0='+(S1.eq&&S1.eq[0])+' len='+(S1.eq&&S1.eq.length));
    A('p3h2 the note says how that curve is drawn and what its drawdown pane can hide','NEW',
      anyText('joined end to end and spaced evenly by trade')&&anyText('can look shallower than the DRAWDOWN row'),'');
    var p3i=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id),NOBID]},[LW2,NOB]);
    var NC3=w._cmpEqxNoCurve||[];
    // (deferred round, D31) the key gives that run's own reason - the sentence the reader gives, lower-cased after its label
    var NCW=function(x){var s=H.why(x,'curve')||'';return s.charAt(0).toLowerCase()+s.slice(1);};
    A('p3i a picked run with no saved test is listed beside the chart, never drawn as its whole run','NEW',
      clean2(p3i)&&(w._cmpEqxSeries||[]).length===1&&NC3.length===1&&!!NCW(NOB)&&NC3[0].why===NCW(NOB)
      &&anyText(NCW(NOB)),
      'series='+(w._cmpEqxSeries||[]).length+' noCurve='+JSON.stringify(NC3));
    var p3i2=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[NOBID]},[NOB]);
    var S2=(w._cmpEqxSeries||[])[0]||{};
    A('p3i2 with no saved test at all the whole-run chart stays, and says so','NEW',
      clean2(p3i2)&&(w._cmpEqxSeries||[]).length===1&&!S2.span&&!!(S2.blot&&S2.blot.run_id)
      &&anyText('None of these runs saved a walk-forward curve, so the whole run is shown.'),
      'span='+JSON.stringify(S2.span)+' blot='+!!S2.blot);

    // ── PICK RUNS (hosted) ───────────────────────────────────────────────────────────────
    var p3j=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(FIXW.id)]},[LW2]);
    var TP=tbl2();
    A('p3j PICK RUNS on walk-forward carries the saved test rows','NEW',
      clean2(p3j)&&!!TP.c['WF drawdown']&&TP.c['WF drawdown'][0]===AB$(DDW)
      &&TP.c['WF MAR'][0]===MARW.toFixed(2)&&TP.c['WF Sharpe'][0]===(+B.sharpe).toFixed(2)
      &&TP.c['WF Sortino'][0]===(+B.sortino).toFixed(2)&&TP.c['WF PF'][0]===(+B.profit_factor).toFixed(2)
      &&TP.c['WF win %'][0]===Math.round(WRW)+'%'&&!TP.c['Pooled fold PF'],
      'DD '+TP.c['WF drawdown']+' MAR '+TP.c['WF MAR']+' SH '+TP.c['WF Sharpe']+' SO '+TP.c['WF Sortino']
      +' PF '+TP.c['WF PF']+' WR '+TP.c['WF win %']+' oldPF='+!!TP.c['Pooled fold PF']);
    var p3k=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(FIXW.id),NOBID]},[LW2,NOB]);
    var bd=bestOn('WF drawdown')||[],bm=bestOn('WF MAR')||[];
    A('p3k a missing walk-forward figure sinks in the order, never wins the row','NEW',
      clean2(p3k)&&bd.length===2&&bm.length===2
      &&bd.filter(function(o){return o.v==='—';}).length===1
      &&bd.filter(function(o){return o.best;}).length===1&&!bd.filter(function(o){return o.v==='—';})[0].best
      &&bm.filter(function(o){return o.best;}).length===1&&!bm.filter(function(o){return o.v==='—';})[0].best,
      'DD '+JSON.stringify(bd)+' MAR '+JSON.stringify(bm));

    // ── RUNBOARD (hosted) ────────────────────────────────────────────────────────────────
    var p3l=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[LW2]);
    var TR=tbl2();MAR3.board=TR.c['MAR']?TR.c['MAR'][0]:null;
    A('p3l RUNBOARD walk-forward: real panels, pooled money, the saved test risk figures','NEW',
      clean2(p3l)&&!!d.querySelector('#cmp-ovl-host')&&q('[data-rbrow]').length===1&&!!TR.c['MAR']
      &&TR.c['TOTAL'][0]===AB$(POOL)&&TR.c['DD'][0]===AB$(DDW)&&TR.c['MAR'][0]===MARW.toFixed(2)
      &&TR.c['SHARPE'][0]===(+B.sharpe).toFixed(2)&&TR.c['PF'][0]===(+B.profit_factor).toFixed(2)
      &&TR.c['WIN %'][0]===Math.round(WRW)+'%'&&TR.c['TRADES'][0]===sT.toLocaleString()
      &&TR.c['WINDOW'][0].indexOf(B.from)===0&&TR.c['WINDOW'][0].indexOf((+B.years).toFixed(1)+'y')>0
      &&anyText('BOOKS HAVE NO WALK-FORWARD STAGE')&&!anyText('RUNBOARD HAS NO WALK-FORWARD STAGE'),
      'host='+!!d.querySelector('#cmp-ovl-host')+' rows='+q('[data-rbrow]').length+' TOTAL '+TR.c['TOTAL']
      +' DD '+TR.c['DD']+' MAR '+TR.c['MAR']+' SH '+TR.c['SHARPE']+' PF '+TR.c['PF']+' WR '+TR.c['WIN %']
      +' TR '+TR.c['TRADES']+' WINDOW '+TR.c['WINDOW']);
    var fn=(w._cmpEqxSeries||[])[0]||{};
    A('p3l2 the RUNBOARD funnel draws that same curve, with no lockbox door','NEW',
      Array.isArray(fn.eq)&&fn.eq.length===B.equity.length+1&&fn.eq[0]===0&&fn.wfi===0&&fn.li===null
      &&fn.blot===null&&Array.isArray(fn.span)&&fn.span[0]===B.from,
      'len='+(fn.eq&&fn.eq.length)+' wfi='+fn.wfi+' li='+fn.li+' span='+JSON.stringify(fn.span));
    var p3m=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[LBK2]);
    var TB=tbl2();
    A('p3m a book on the walk-forward sample reads nothing, and says why','NEW',
      clean2(p3m)&&!!TB.c['MAR']&&TB.c['TOTAL'][0]==='—'&&TB.c['DD'][0]==='—'&&TB.c['MAR'][0]==='—'
      &&TB.c['SHARPE'][0]==='—'&&(TB.t['MAR'][0]||'').indexOf('book tunes nothing')>=0,
      'TOTAL '+TB.c['TOTAL']+' DD '+TB.c['DD']+' MAR '+TB.c['MAR']+' title='+(TB.t['MAR']&&TB.t['MAR'][0]));
    var rdiff=[];
    ['full','is','lb'].forEach(function(st){
      var a=rend2({c2Screen:'cmp',c2View:'board',c2Stage:st,rbRank:'mar',rbHeat:false},[LW2]);
      var ta=JSON.stringify(tbl2());
      var b=rend2({c2Screen:'cmp',c2View:'board',c2Stage:st,rbRank:'mar',rbHeat:false},[NOBLK]);
      var tb=JSON.stringify(tbl2());
      if(a!=='OK'||b!=='OK'||ta.length<200||ta!==tb)rdiff.push(st+(ta===tb?' (render '+a+'/'+b+')':' differs'));});
    A('p3n the RUNBOARD whole-run, tuning and lockbox grids are untouched by the saved test','NOREG',!rdiff.length,rdiff.join(' ; '));

    // ── EXPLORE run rows ─────────────────────────────────────────────────────────────────
    var EP=function(segs,extra){var o={c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:segs,
      resAxis:'evr',resXAxis:'so',resCols:'all',c2Tbl:true};if(extra)Object.keys(extra).forEach(function(k){o[k]=extra[k];});return o;};
    var p4a=rend2(EP(['wf']),[LW2]);
    var R4=reRow(FIXW.id);MAR3.explore=R4?R4.v['MAR']:null;
    A('p4a EXPLORE walk-forward alone: the saved test fills the row','NEW',
      clean2(p4a)&&!!R4&&R4.v['DRAWDOWN']==='$'+ABR(DDW)&&R4.v['MAR']===MARW.toFixed(2)
      &&R4.v['SHARPE']===(+B.sharpe).toFixed(2)&&R4.v['SORTINO']===(+B.sortino).toFixed(2)
      &&R4.v['PF']===(+B.profit_factor).toFixed(2)&&R4.v['WIN %']===Math.round(WRW)+'%'
      // this run saved no walk-forward split date at all, so a per-year figure here can only
      //   come from the test's own window
      &&/^[0-9]+\.[0-9]R$/.test(R4.v['R / YR']||'')&&/^[0-9]+\.[0-9]%$/.test(R4.v['ROC % / YR']||''),
      'row='+JSON.stringify(R4&&R4.v)+' want DD $'+ABR(DDW)+' MAR '+MARW.toFixed(2)+' SO '+(+B.sortino).toFixed(2));
    A('p3o one run, one walk-forward MAR on every screen','NEW',
      MAR3.lead!=null&&MAR3.lead===MAR3.board&&MAR3.board===MAR3.explore,JSON.stringify(MAR3));
    A('p4d the READ hover MAR is the ticked stretch own','NEW',
      titles2().filter(function(t){return t.indexOf('READ:')===0&&t.indexOf('#'+FIXW.id)>=0;})
        .some(function(t){return t.indexOf('MAR · walk-forward '+MARW.toFixed(2))>=0;}),
      (titles2().filter(function(t){return t.indexOf('READ:')===0;})[0]||'(no READ hover)').slice(0,300));
    // the long chart note lives on the PARALLEL chart (the one with an axis per measure)
    var p4f=rend2(EP(['wf'],{resChart:'par'}),[LW2]);
    A('p4f the chart note says where a run row walk-forward figures come from','NEW',
      clean2(p4f)&&anyText('On walk-forward alone a run row carries them when its walk-forward detail was saved with the run')
      &&anyText('on walk-forward plus lockbox the two are separate trade sequences'),
      'call='+p4f+' note='+(titles2().filter(function(t){return t.indexOf('Every axis left of NET')>=0;})[0]||'(no note)').slice(-320));
    // the chart, and the counts under it, must follow the saved test too: a run it fills is
    //   PLOTTED, so the "not on this chart" tally drops it
    var p4g1=rend2(EP(['wf']),[LW2]);var sh1=w._reShownN,sk1=w._reSkipN;
    var p4g2=rend2(EP(['wf']),[NOBLK]);var sh2=w._reShownN,sk2=w._reSkipN;
    A('p4g the chart plots a run the saved test fills, and the tally under it says so','NEW',
      clean2(p4g1)&&clean2(p4g2)&&sk1===0&&sk2>=1&&sh1>=1,
      'with the test shown='+sh1+' off='+sk1+' | without shown='+sh2+' off='+sk2);
    var p4b=rend2(EP(['wf','lb']),[LW2]);var Rb=reRow(FIXW.id);
    var p4b2=rend2(EP(['wf','lb']),[NOBLK]);var Rb2=reRow(FIXW.id);
    A('p4b walk-forward plus lockbox keeps its honest dashes, now with the reason','NEW',
      clean2(p4b)&&clean2(p4b2)&&!!Rb&&!!Rb2&&Rb.v['PF']===Rb2.v['PF']&&Rb.v['WIN %']===Rb2.v['WIN %']
      &&Rb.v['DRAWDOWN']==='—'&&Rb.v['MAR']==='—'&&Rb.v['SHARPE']==='—'&&Rb.v['SORTINO']==='—'
      &&Rb.t('SORTINO').indexOf('two separate trade sequences')>=0&&Rb.t('DRAWDOWN').indexOf('two separate trade sequences')>=0,
      'PF '+Rb.v['PF']+'/'+Rb2.v['PF']+' WR '+Rb.v['WIN %']+'/'+Rb2.v['WIN %']+' DD '+Rb.v['DRAWDOWN']
      +' SO '+Rb.v['SORTINO']+' why='+Rb.t('SORTINO').slice(0,120));
    var ediff=[];
    [['is'],['lb'],['is','wf'],['is','wf','lb']].forEach(function(sg){
      var a=rend2(EP(sg),[LW2]);var ra=reRow(FIXW.id);
      var b=rend2(EP(sg),[NOBLK]);var rb=reRow(FIXW.id);
      if(a!=='OK'||b!=='OK'||!ra||!rb||JSON.stringify(ra.v)!==JSON.stringify(rb.v))ediff.push(sg.join('+'));});
    A('p4c every other tick is untouched by the saved test','NOREG',!ediff.length,'differ on: '+ediff.join(', '));
    var p4e=rend2(EP(['wf']),[NOB]);var Rn=reRow(NOBID);
    A('p4e a run saved before the test says that, not that only a run carries one','NEW',
      clean2(p4e)&&!!Rn&&Rn.v['SORTINO']==='—'&&Rn.v['DRAWDOWN']==='—'
      &&Rn.t('SORTINO').indexOf('saved before walk-forward detail was recorded')>=0
      &&Rn.t('SORTINO').indexOf('Only a run')<0,
      'SO '+(Rn&&Rn.v['SORTINO'])+' why='+(Rn?Rn.t('SORTINO'):'(no row)'));

    // ══ P5 - THE THREE STATES ONLY A SAVED TEST CAN REACH ═══════════════════════════════
    //    A test that took NO TRADES, a test with NO WINDOW on a run that does carry a
    //    tuning-split date, and the rounding gap between a saved average loss and a saved
    //    profit factor. Each one used to read differently on different screens.
    // the RUNBOARD grid marks its best cell with a <b> inside the cell, not with a cell style
    function mark2(lab){var tr=q('tr').filter(function(t){return norm((t.children[0]||{}).textContent)===lab;})[0];
      if(!tr)return [];return Array.prototype.slice.call(tr.children).slice(1).map(function(td){
        var s=td.querySelector('[title]');
        return {v:norm(td.textContent),best:(/font-weight:\s*(700|800|bold)/.test(td.getAttribute('style')||'')||!!td.querySelector('b')),
          t:(s?(s.getAttribute('title')||''):(td.getAttribute('title')||''))};});}
    var LOCKWD='took no trades in the lockbox', FOLDWD='took no trades in the walk-forward folds';
    // a test that took no trades, in the shape the engine writes one: 0 trades, $0, a 0.0
    //   drawdown, no ratios, no curve - and fold rows that agree with it, so the check accepts it
    var ZERID=String(+FIXB.id+900002);
    var ZER=(function(){var x=clone(FIXW),b=x.validate.wf_oos;
      x.id=ZERID;x.strategy='ZZEROWF_1_0.py';x.starred=false;
      (x.top10_results||[]).forEach(function(f){if(f&&f.fold!=null){f.oos_trades=0;f.oos_pnl=0;f.oos_wins=0;f.oos_pf=null;}});
      b.trades=0;b.wins=0;b.win_rate=null;b.net=0.0;b.gross_win=0;b.gross_loss=0;b.profit_factor=null;
      b.avg_win=null;b.avg_loss=null;b.max_drawdown=0.0;b.sharpe=null;b.sortino=null;b.equity=[];b.equity_n=0;
      b.fold_idx=[];(b.folds||[]).forEach(function(f){f.trades=0;f.net=0;});
      return lite(x,ZERID);})();
    // a test with no window dates on a run that DOES carry a tuning-split date - the window the
    //   folds cover is unknown, and the split window is a longer stretch than they cover
    var WSP=(function(){var x=clone(FIXW),b=x.validate.wf_oos;
      x.validate.windows.wf_split='2014-01-01';
      b.years=null;b.from=null;b.to=null;b.sharpe=null;b.sortino=null;
      (b.folds||[]).forEach(function(f){f.from=null;f.to=null;});return lite(x);})();
    // a test in which NO walk-forward trade lost: no profit factor, no gross loss, no average loss
    var NLS=(function(){var x=clone(FIXW),b=x.validate.wf_oos;
      b.wins=b.trades;b.win_rate=100;b.profit_factor=null;b.gross_win=b.net;b.gross_loss=0;b.avg_loss=null;
      return lite(x);})();
    // the expectancy the saved test's OWN figures imply - the number every screen must print
    var EVR=(1-(+B.wins/+B.trades))*(+B.profit_factor-1), RPY=EVR*(+B.trades)/(+B.years);

    // ── a walk-forward that took no trades ───────────────────────────────────────────────
    var p5a=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'dd',rbHeat:false},[LW2,ZER]);
    var Zdd=mark2('DD'),Ztot=mark2('TOTAL'),Zpf=mark2('PF'),Ztr=mark2('TRADES');
    var Zz=function(a){return a.filter(function(o){return o.v==='—';});};
    // (R5) the pooled $0 is a reading, printed and never the best; the drawdown and the ratios still dash
    A('p5a RUNBOARD: a walk-forward that took no trades prints its $0, dashes its drawdown, and neither can win a row','NEW',
      clean2(p5a)&&Zdd.length===2&&Ztot.length===2&&Zz(Zdd).length===1&&Zz(Ztot).length===0&&Zz(Zpf).length===1
      &&Ztot.filter(function(o){return o.v==='$0'&&!o.best;}).length===1
      &&Zdd.filter(function(o){return o.best;}).length===1&&!Zz(Zdd)[0].best
      &&Zdd.filter(function(o){return o.best;})[0].v===AB$(DDW)
      &&Zz(Zdd)[0].t.indexOf(FOLDWD)>=0
      &&Ztr.filter(function(o){return o.v==='0';}).length===1,
      'DD '+JSON.stringify(Zdd)+' TOTAL '+JSON.stringify(Ztot)+' PF '+JSON.stringify(Zpf.map(function(o){return o.v;}))
      +' TRADES '+JSON.stringify(Ztr.map(function(o){return o.v;})));
    // the grid's own column headings carry the rank strip ('R1 · #306'), in rank order
    var rnk=q('th').map(function(e){return norm(e.textContent);}).filter(function(t){return /R[0-9]+ · #/.test(t);});
    A('p5a2 RUNBOARD: ranked on drawdown, the run that never traded the folds is not first','NEW',
      clean2(p5a)&&rnk.length===2&&rnk[0].indexOf('#'+FIXW.id)>=0&&rnk[1].indexOf('#'+ZERID)>=0,
      JSON.stringify(rnk));
    var p5b=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(FIXW.id),ZERID]},[LW2,ZER]);
    var Pdd=bestOn('WF drawdown')||[],Pnet=bestOn('WF net $ (out-of-sample)')||[];
    A('p5b PICK RUNS: the same run dashes on walk-forward drawdown and prints its $0 walk-forward money, never as the best','NEW',
      clean2(p5b)&&Pdd.length===2&&Pnet.length===2
      &&Pdd.filter(function(o){return o.v==='—';}).length===1&&Pnet.filter(function(o){return o.v==='—';}).length===0
      &&Pdd.filter(function(o){return o.best;}).length===1&&!Pdd.filter(function(o){return o.v==='—';})[0].best
      &&Pnet.filter(function(o){return o.v==='$0'&&!o.best;}).length===1,
      'DD '+JSON.stringify(Pdd)+' NET '+JSON.stringify(Pnet));
    var p5c=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[ZERID],c2Heat:false},[ZER]);
    var TZ=tbl2();
    A('p5c the comparison table prints the $0 and the 0 trades of a walk-forward that took no trades and dashes the rest','NEW',
      clean2(p5c)&&!!TZ.c['DRAWDOWN']&&TZ.c['NET'][0]==='$0'&&TZ.c['DRAWDOWN'][0]==='—'&&TZ.c['MAR'][0]==='—'
      &&TZ.c['PF'][0]==='—'&&TZ.c['EV R'][0]==='—'&&TZ.c['TRADES'][0]==='0',
      'NET '+TZ.c['NET']+' DD '+TZ.c['DRAWDOWN']+' MAR '+TZ.c['MAR']+' PF '+TZ.c['PF']+' EVR '+TZ.c['EV R']+' TR '+TZ.c['TRADES']);
    A('p5c2 and it says the folds, not the lockbox, on every one of those hovers','NEW',
      ['DRAWDOWN','MAR','PF','WIN %','EV R','R / YR'].every(function(k){
        var t=(TZ.t[k]&&TZ.t[k][0])||'';return t.indexOf(FOLDWD)>=0&&t.indexOf(LOCKWD)<0;}),
      ['DRAWDOWN','MAR','PF','EV R'].map(function(k){return k+'="'+((TZ.t[k]&&TZ.t[k][0])||'')+'"';}).join(' | '));
    var p5c3=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'mar'},[ZER]);
    var gz=famBig();
    A('p5c3 the LEADERBOARD gives that run the same sentence','NEW',
      clean2(p5c3)&&!!gz&&gz.v==='—'&&gz.t.indexOf(FOLDWD)>=0,'got '+(gz&&gz.v)+' title='+(gz&&gz.t));
    var p5c4=rend2(EP(['wf']),[ZER]);var Rz=reRow(ZERID);
    A('p5c4 the EXPLORE row keeps its own zero-trade dashes beside them','NOREG',
      clean2(p5c4)&&!!Rz&&Rz.v['DRAWDOWN']==='—'&&Rz.v['MAR']==='—'&&Rz.v['PF']==='—'
      &&Rz.t('MAR').indexOf('took no trades')>=0,
      'row='+JSON.stringify(Rz&&Rz.v)+' why='+(Rz?Rz.t('MAR'):'(no row)'));

    // ── a test with no saved window, on a run that has a tuning-split date ───────────────
    var p5d=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'mar'},[WSP]);
    var gw=famBig();
    A('p5d the LEADERBOARD does not annualise a windowless test on the tuning-split window','NEW',
      clean2(p5d)&&!!gw&&gw.v==='—'&&gw.t.indexOf('window dates are not saved')>=0,
      'got '+(gw&&gw.v)+' title='+(gw&&gw.t));
    var p5d2=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[WSP]);
    var TW=tbl2();
    A('p5d2 the RUNBOARD dashes its MAR and its window, and keeps the folds own drawdown','NEW',
      clean2(p5d2)&&!!TW.c['MAR']&&TW.c['MAR'][0]==='—'&&TW.c['WINDOW'][0]==='—'
      &&TW.c['DD'][0]===AB$(DDW)&&(TW.t['MAR'][0]||'').indexOf('window dates are not saved')>=0,
      'MAR '+TW.c['MAR']+' WINDOW '+TW.c['WINDOW']+' DD '+TW.c['DD']+' why='+(TW.t['MAR']&&TW.t['MAR'][0]));
    var p5d3=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(FIXW.id)]},[WSP]);
    var TP2=tbl2();
    A('p5d3 PICK RUNS dashes the same MAR','NEW',
      clean2(p5d3)&&!!TP2.c['WF MAR']&&TP2.c['WF MAR'][0]==='—'&&TP2.c['WF drawdown'][0]===AB$(DDW),
      'MAR '+TP2.c['WF MAR']+' DD '+TP2.c['WF drawdown']);
    var p5d4=rend2(EP(['wf']),[WSP]);var Rw=reRow(FIXW.id);
    A('p5d4 the EXPLORE row dashes MAR, R / YR and ROC with the window as the reason','NEW',
      clean2(p5d4)&&!!Rw&&Rw.v['MAR']==='—'&&Rw.v['R / YR']==='—'&&Rw.v['ROC % / YR']==='—'
      &&Rw.v['DRAWDOWN']==='$'+ABR(DDW)
      &&Rw.t('MAR').indexOf('window dates are not saved')>=0
      &&Rw.t('MAR').indexOf('records no date window')<0,
      'row='+JSON.stringify(Rw&&Rw.v)+' why='+(Rw?Rw.t('MAR'):'(no row)'));

    // ── one expectancy, from the test's own figures, on both screens ─────────────────────
    var p5e=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id)],c2Heat:false},[LW2]);
    var TE=tbl2();
    var p5e2=rend2(EP(['wf']),[LW2]);var Re=reRow(FIXW.id);
    A('p5e EV R and R / YR are the saved test own figures on the table and on the run row alike','NEW',
      clean2(p5e)&&clean2(p5e2)&&!!TE.c['EV R']&&!!Re
      &&TE.c['EV R'][0]===EVR.toFixed(2)&&TE.c['R / YR'][0]===RPY.toFixed(1)
      &&Re.v['EV R']===EVR.toFixed(2)+'R'&&Re.v['R / YR']===RPY.toFixed(1)+'R',
      'table EVR '+TE.c['EV R']+' RPY '+TE.c['R / YR']+' | row EVR '+(Re&&Re.v['EV R'])+' RPY '+(Re&&Re.v['R / YR'])
      +' | want '+EVR.toFixed(2)+' / '+RPY.toFixed(1));
    var p5f=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id)],c2Heat:false},[NLS]);
    var TL=tbl2();
    var p5f2=rend2(EP(['wf']),[NLS]);var Rl=reRow(FIXW.id);
    A('p5f no losing walk-forward trade: no expectancy in R on either screen','NEW',
      clean2(p5f)&&clean2(p5f2)&&!!TL.c['EV R']&&!!Rl
      &&TL.c['EV R'][0]==='—'&&TL.c['R / YR'][0]==='—'&&TL.c['PF'][0]==='—'
      &&Rl.v['EV R']==='—'&&Rl.v['R / YR']==='—'&&Rl.v['PF']==='—',
      'table EVR '+TL.c['EV R']+' RPY '+TL.c['R / YR']+' PF '+TL.c['PF']
      +' | row EVR '+(Rl&&Rl.v['EV R'])+' RPY '+(Rl&&Rl.v['R / YR'])+' PF '+(Rl&&Rl.v['PF']));

    // ══ R5 - A WALK-FORWARD THAT TOOK NO TRADES: ONE READING ON EVERY SCREEN ════════════════
    //    The run comes from the engine's own block helper (tools/make_wfoos_zero_fixture.py):
    //    every fold tested no trade, so the saved test is trades 0, net 0.0, max_drawdown 0.0 and
    //    no profit factor, Sharpe, Sortino or curve. Its pooled NET ($0) and TRADES (0) are real
    //    readings on every screen; every ratio, the drawdown and $ per trade dash with ONE
    //    sentence; neither the $0 nor the empty drawdown takes a best mark or a heat shade; and
    //    ranked on drawdown or MAR it sorts after the runs that traded.
    var ZWD='This run took no trades in the walk-forward folds.';
    var FZB=FIXZ.validate.wf_oos, ZID=String(FIXZ.id), NGID=String(+FIXZ.id+1);
    var FZL=(FIXZ.top10_results||[]).filter(function(f){return f&&f.fold!=null;});
    var LZ=lite(FIXZ), DZ=full(FIXZ);
    // a run that traded the folds and LOST money over them, so a $0 is the largest net on the
    //   row - the one place a $0 could steal a best mark it has no right to
    var NEG=(function(){var x=clone(FIXW),b=x.validate.wf_oos;x.id=NGID;x.strategy='NEGWF_1_0.py';x.starred=false;
      (x.top10_results||[]).forEach(function(f){if(f&&f.fold!=null)f.oos_pnl=-(+f.oos_pnl||0);});
      b.net=-b.net;b.equity=b.equity.map(function(v){return -v;});(b.folds||[]).forEach(function(f){f.net=-f.net;});
      return lite(x,NGID);})();
    // one cell of a labelled row, for one run: its text, its reason hover, a best mark, a heat shade
    function r5Row(lab){return q('tr').filter(function(t){return norm((t.children[0]||{}).textContent)===lab;})[0]||null;}
    function r5Cell(lab,id){var tr=r5Row(lab);if(!tr)return null;
      var td=tr.querySelector('td[data-rbc="'+id+'"]');
      if(!td){var tb=tr.closest('table'),h0=tb?tb.querySelector('tr'):null,hd=h0?Array.prototype.slice.call(h0.children):[],k=-1;
        hd.forEach(function(th,i){if(k<0&&i>0&&norm(th.textContent).indexOf('#'+id)>=0)k=i;});
        td=(k>0)?tr.children[k]:null;}
      if(!td)return null;var s=td.querySelector('[title]');
      return {v:norm(td.textContent),t:(s?(s.getAttribute('title')||''):(td.getAttribute('title')||'')),
        best:(/font-weight:\s*700/.test(td.getAttribute('style')||'')||!!td.querySelector('b')||!!td.querySelector('span[style*="font-weight:800"]')),
        heat:/hsla\(/.test(td.getAttribute('style')||'')};}
    function r5s(o){return o?(o.v+(o.best?' [best]':'')+(o.heat?' [heat]':'')+(o.t?(o.t===ZWD?' {ZWD}':(' {'+o.t.slice(0,46)+'}')):'')):'(no cell)';}
    function r5Dash(o){return !!o&&o.v==='—'&&o.t===ZWD&&!o.best&&!o.heat;}
    function r5v(o){return o?o.v:null;}

    A('R5a the zero-trade run is the engine block, and the reader accepts it','NOREG',
      String((FIXZ._fixture||{}).block_from||'').indexOf('engine analytics.wf_oos_block')===0
      &&FZB.v===1&&FZB.trades===0&&FZB.net===0&&FZB.max_drawdown===0&&FZB.profit_factor===null
      &&FZB.sharpe===null&&FZB.sortino===null&&Array.isArray(FZB.equity)&&FZB.equity.length===0
      &&FZL.length===FZB.n_folds&&FZL.every(function(f){return +f.oos_trades===0&&+f.oos_pnl===0;})
      &&H.chk(DZ).st==='ok'&&!!(H.of(DZ,M)&&H.of(DZ,M).zeroTr),
      JSON.stringify({src:String((FIXZ._fixture||{}).block_from||'').slice(0,40),trades:FZB.trades,net:FZB.net,max_drawdown:FZB.max_drawdown,
        pf:FZB.profit_factor,sharpe:FZB.sharpe,sortino:FZB.sortino,equity:(FZB.equity||[]).length,folds:FZL.length,state:H.chk(DZ).st}));

    var OZ=H.of(DZ,M)||{};
    A('R5b the reader: the $0 and the 0 trades are readings, the saved 0.0 drawdown is not','NEW',
      OZ.poolNet===0&&OZ.tr===0&&OZ.dd===null&&OZ.mar===null&&OZ.pf===null&&OZ.wr===null&&OZ.sharpe===null&&OZ.sortino===null
      &&H.why(DZ,'net')===''&&H.why(DZ,'ev')===ZWD&&H.why(DZ,'dd')===ZWD&&H.why(DZ,'mar')===ZWD&&H.why(DZ,'wr')===ZWD,
      JSON.stringify({net:OZ.poolNet,trades:OZ.tr,dd:OZ.dd,mar:OZ.mar,whyNet:H.why(DZ,'net'),whyEv:H.why(DZ,'ev'),whyDd:H.why(DZ,'dd')}));

    // ── LEADERBOARD: one family row per strategy, ranked on the picked figure ────────────────
    function r5Fams(){return q('.c2-row[data-c2fam]').map(function(e){var b=e.querySelector('.c2-big');
      return {txt:norm(e.textContent),v:b?norm(b.textContent):null,t:b?(b.getAttribute('title')||''):''};});}
    function r5At(rows,id){for(var i=0;i<rows.length;i++){if((' '+rows[i].txt+' ').indexOf('#'+id+' ')>=0)return i;}return -1;}
    var LEAD={};
    ['net','mar','pf','rpy'].forEach(function(rk){var c=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:rk},[LW2,LZ,NEG]);
      var fr=r5Fams(),iz=r5At(fr,ZID);LEAD[rk]={ok:clean2(c),n:fr.length,iz:iz,z:(iz>=0?fr[iz]:{v:null,t:''})};});
    A('R5c LEADERBOARD: on NET the run reads $0; on MAR, PF and R / YR it dashes with the one sentence, and on MAR it sorts last','NEW',
      ['net','mar','pf','rpy'].every(function(rk){return LEAD[rk].ok&&LEAD[rk].n===3&&LEAD[rk].iz>=0;})
      &&LEAD.net.z.v==='$0'&&!LEAD.net.z.t
      &&['mar','pf','rpy'].every(function(rk){return LEAD[rk].z.v==='—'&&LEAD[rk].z.t===ZWD;})
      &&LEAD.mar.iz===2,
      ['net','mar','pf','rpy'].map(function(rk){var o=LEAD[rk];return rk.toUpperCase()+' '+o.z.v+' (row '+(o.iz+1)+' of '+o.n+')'+(o.z.t?(o.z.t===ZWD?' {ZWD}':(' {'+o.z.t.slice(0,46)+'}')):'');}).join(' | '));

    // ══ g5-sink (owner decision 2026-09-16) - A WALK-FORWARD ZERO-TRADE RUN NEVER OUTRANKS A
    //    TRADED ONE, EVEN ON NET ═══════════════════════════════════════════════════════════
    //    LEADERBOARD, COMPARE CHAMPIONS and TOP RUNS share one ranking function (_c2Val). Before
    //    this fix it let a walk-forward test's pooled $0 net compete on its raw (zero) value, so
    //    against NEG - a run that traded the folds and LOST money - the $0 sat ABOVE the loss on
    //    NET while it correctly sank BELOW it on every other rank (see LEAD.mar.iz===2 above,
    //    already true beforehand). RUNBOARD (M_wf's -1e15 sentinel) and the comparison table
    //    (_mZero) already sank it correctly on NET too, so only _c2Val carried the exception.
    A('g5_sink_lead LEADERBOARD on NET: the zero-trade run still reads its pooled $0 (not a dash) but sorts LAST, behind the run that traded and lost','NEW',
      LEAD.net.ok&&LEAD.net.n===3&&LEAD.net.z.v==='$0'&&!LEAD.net.z.t&&LEAD.net.iz===2,
      'NET column: zero-trade run at row '+(LEAD.net.iz+1)+' of '+LEAD.net.n+' (want row 3, last, behind the loser)');

    function rbcOrder(){return q('th[data-rbc]').map(function(e){return e.getAttribute('data-rbc');});}
    var champWf=rend2({c2Screen:'cmp',c2View:'ovl',c2Src:'champ',c2Stage:'wf',c2Rank:'net',c2Heat:false},[LW2,LZ,NEG]);
    var champOrd=rbcOrder(), champIz=champOrd.indexOf(ZID);
    A('g5_sink_champ COMPARE CHAMPIONS on walk-forward NET: the zero-trade champion sorts LAST of the three picked columns','NEW',
      clean2(champWf)&&champOrd.length===3&&champIz===2,
      'champion column order '+JSON.stringify(champOrd)+' (zero-trade run '+ZID+' at position '+(champIz+1)+', want 3)');

    var topWf=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'net',c2Top:'best'},[LW2,LZ,NEG]);
    var topRows=q('.c2-card .c2-row.sub[data-c2run]').map(function(e){return e.getAttribute('data-c2run');});
    var topIz=topRows.indexOf(ZID);
    A('g5_sink_top TOP RUNS · BEST on walk-forward NET: the zero-trade run never takes the top slot and sorts LAST','NEW',
      clean2(topWf)&&topRows.length===3&&topIz===2&&topRows[0]===String(FIXW.id),
      'TOP RUNS order '+JSON.stringify(topRows)+' (zero-trade run '+ZID+' at position '+(topIz+1)+', want 3; best should be #'+FIXW.id+')');

    var topWfWorst=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'net',c2Top:'worst'},[LW2,LZ,NEG]);
    var topRowsW=q('.c2-card .c2-row.sub[data-c2run]').map(function(e){return e.getAttribute('data-c2run');});
    var topIzW=topRowsW.indexOf(ZID);
    A('g5_sink_top2 TOP RUNS · WORST on walk-forward NET: the zero-trade run is not a genuine "worst" result either, so it still sorts LAST, behind the actual loser','NEW',
      clean2(topWfWorst)&&topRowsW.length===3&&topIzW===2&&topRowsW[0]===NGID,
      'TOP RUNS WORST order '+JSON.stringify(topRowsW)+' (zero-trade run '+ZID+' at position '+(topIzW+1)+', want 3; worst should be the actual loser #'+NGID+')');

    // ── comparison table: three picks (so a heat scale exists), then two (so a $0 would be the top net) ──
    var t3=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[ZID,NGID,String(FIXW.id)],c2Heat:true},[LW2,LZ,NEG]);
    var CT={};['NET','DRAWDOWN','MAR','SHARPE','PF','WIN %','EV R','R / YR','EV $','TRADES'].forEach(function(k){CT[k]=r5Cell(k,ZID);});
    var CTw=r5Cell('NET',FIXW.id),CTg=r5Cell('NET',NGID);
    var t2=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[ZID,NGID],c2Heat:true},[LZ,NEG]);
    var C2={zNet:r5Cell('NET',ZID),gNet:r5Cell('NET',NGID),zDd:r5Cell('DRAWDOWN',ZID),gDd:r5Cell('DRAWDOWN',NGID)};
    A('R5d comparison table: $0 and 0 trades print; the ratios, the drawdown and EV $ dash with the one sentence; no best mark or heat on the $0 or the drawdown','NEW',
      clean2(t3)&&clean2(t2)&&!!CT.NET&&CT.NET.v==='$0'&&!CT.NET.best&&!CT.NET.heat&&!!CT.TRADES&&CT.TRADES.v==='0'
      &&['DRAWDOWN','MAR','SHARPE','PF','WIN %','EV R','R / YR','EV $'].every(function(k){return r5Dash(CT[k]);})
      &&!!CTw&&CTw.heat&&!!CTg&&CTg.heat
      &&!!C2.zNet&&C2.zNet.v==='$0'&&!C2.zNet.best&&!C2.zNet.heat&&!!C2.gNet&&C2.gNet.best&&r5Dash(C2.zDd)&&!!C2.gDd&&C2.gDd.best,
      'picks 3: '+['NET','DRAWDOWN','MAR','SHARPE','PF','WIN %','EV R','R / YR','EV $','TRADES'].map(function(k){return k+' '+r5s(CT[k]);}).join(' ; ')
      +' || picks 2: NET '+r5s(C2.zNet)+' vs loser '+r5s(C2.gNet)+' ; DD '+r5s(C2.zDd)+' vs '+r5s(C2.gDd));

    // ── PICK RUNS (hosted, walk-forward stage): beside a loser, then alone ───────────────────
    var PKL=['WF net $ (out-of-sample)','WF drawdown','WF MAR','WF Sharpe','WF Sortino','WF PF','WF win %','OOS trades'];
    var p2=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[ZID,NGID]},[LZ,NEG]);
    var PK={};PKL.forEach(function(k){PK[k]=r5Cell(k,ZID);});var PKg=r5Cell(PKL[0],NGID);
    var p1=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[ZID]},[LZ]);
    var PK1={net:r5Cell(PKL[0],ZID),dd:r5Cell('WF drawdown',ZID),mar:r5Cell('WF MAR',ZID)};
    A('R5e PICK RUNS: $0 and 0 OOS trades print, the $0 is never the best, the six ratio rows dash with the one sentence - alone too','NEW',
      clean2(p2)&&clean2(p1)&&!!PK[PKL[0]]&&PK[PKL[0]].v==='$0'&&!PK[PKL[0]].best&&!!PKg&&PKg.best
      &&!!PK['OOS trades']&&PK['OOS trades'].v==='0'
      &&PKL.slice(1,7).every(function(k){return r5Dash(PK[k]);})
      &&!!PK1.net&&PK1.net.v==='$0'&&!PK1.net.best&&r5Dash(PK1.dd)&&r5Dash(PK1.mar),
      PKL.map(function(k){return k.replace(' (out-of-sample)','')+' '+r5s(PK[k]);}).join(' ; ')+' | loser net '+r5s(PKg)
      +' || alone: net '+r5s(PK1.net)+' ; DD '+r5s(PK1.dd)+' ; MAR '+r5s(PK1.mar));

    // ── RUNBOARD walk-forward sample: ranked on DD, MAR and NET, heat on ─────────────────────
    var RB={};
    ['dd','mar','net'].forEach(function(rk){var c=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:rk,rbHeat:true},[LW2,LZ,NEG]);
      var cols=q('th').map(function(e){return norm(e.textContent);}).filter(function(t){return /R[0-9]+ · #/.test(t);});
      // a column heading runs the run number straight into the family alias ('R2 · #306NOISE-22')
      RB[rk]={ok:clean2(c),n:cols.length,iz:cols.map(function(t){return new RegExp('#'+ZID+'(?![0-9])').test(t);}).indexOf(true)};
      if(rk==='dd'){['TOTAL','DD','MAR','SHARPE','PF','WIN %','EV','TRADES'].forEach(function(k){RB[k]=r5Cell(k,ZID);});
        RB.wTot=r5Cell('TOTAL',FIXW.id);RB.gTot=r5Cell('TOTAL',NGID);}});
    var r2=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'net',rbHeat:true},[LZ,NEG]);
    RB.z2=r5Cell('TOTAL',ZID);RB.g2=r5Cell('TOTAL',NGID);
    A('R5f RUNBOARD WF: TOTAL $0 and TRADES 0 print without a mark or a shade; DD, MAR, SHARPE, PF, WIN % and EV dash with the one sentence; last on DD and MAR','NEW',
      RB.dd.ok&&RB.mar.ok&&RB.net.ok&&clean2(r2)&&RB.dd.n===3&&RB.dd.iz===2&&RB.mar.iz===2
      &&!!RB.TOTAL&&RB.TOTAL.v==='$0'&&!RB.TOTAL.best&&!RB.TOTAL.heat&&!!RB.wTot&&RB.wTot.heat&&!!RB.gTot&&RB.gTot.heat
      &&['DD','MAR','SHARPE','PF','WIN %','EV'].every(function(k){return r5Dash(RB[k]);})
      &&!!RB.TRADES&&RB.TRADES.v==='0'
      &&!!RB.z2&&RB.z2.v==='$0'&&!RB.z2.best&&!RB.z2.heat&&!!RB.g2&&RB.g2.best,
      'column on DD '+(RB.dd.iz+1)+'/'+RB.dd.n+', on MAR '+(RB.mar.iz+1)+'/'+RB.mar.n+', on NET '+(RB.net.iz+1)+'/'+RB.net.n+' ; '
      +['TOTAL','DD','MAR','SHARPE','PF','WIN %','EV','TRADES'].map(function(k){return k+' '+r5s(RB[k]);}).join(' ; ')
      +' || beside a loser: TOTAL '+r5s(RB.z2)+' vs '+r5s(RB.g2));

    // ── EXPLORE run rows, walk-forward ticked alone, ranked on DRAWDOWN and on MAR ───────────
    var EX={};
    [['dd','dd'],['ratio','mar']].forEach(function(p){var c=rend2(EP(['wf'],{resAxis:p[0]}),[LW2,LZ]);
      EX[p[1]]={ok:clean2(c),z:reRow(ZID),w:reRow(FIXW.id)};});
    var ez=EX.dd.z,ew=EX.dd.w,wk=ez?(Object.keys(ez.v).filter(function(k){return /^WALK/.test(k);})[0]||null):null;
    var EXL=['DRAWDOWN','MAR','SHARPE','SORTINO','PF','WIN %','EV R','R / YR'];
    A('R5g EXPLORE walk-forward tick: WALK-FWD $0 and TRADES 0 print; every ratio and the drawdown dash with the one sentence; unranked on DRAWDOWN and MAR','NEW',
      EX.dd.ok&&EX.mar.ok&&!!ez&&!!ew&&!!wk&&ez.v[wk]==='$0'&&ez.v['TRADES']==='0'
      &&EXL.every(function(k){return ez.v[k]==='—'&&ez.t(k)===ZWD;})
      &&ez.v['RANK']==='—'&&ez.t('RANK')===ZWD&&ew.v['RANK']==='1'
      &&!!EX.mar.z&&!!EX.mar.w&&EX.mar.z.v['RANK']==='—'&&EX.mar.w.v['RANK']==='1',
      (ez?(wk+' '+ez.v[wk]+' ; TRADES '+ez.v['TRADES']+' ; '+EXL.concat(['RANK']).map(function(k){var t=ez.t(k);return k+' '+ez.v[k]+(t?(t===ZWD?' {ZWD}':(' {'+t.slice(0,22)+'}')):'');}).join(' ; ')):'(no zero row)')
      +' || rank on DD: traded '+(ew?ew.v['RANK']:'?')+', on MAR: zero '+(EX.mar.z?EX.mar.z.v['RANK']:'?')+' traded '+(EX.mar.w?EX.mar.w.v['RANK']:'?'));

    // ── run report 1C chips (the report hydrates the whole document) ─────────────────────────
    var cR5=render({},[LZ],[DZ],FIXZ.id); clean('zero-engine',cR5);
    function r5Chip(lbl){var e=q('[data-wfochips] > span').filter(function(x){return norm(x.textContent).indexOf(lbl+' ')===0;})[0];
      return e?{v:norm(e.textContent).slice(lbl.length+1),t:e.getAttribute('title')||''}:null;}
    var K1={};['NET','PF','MAX DD','MAR / YR','SHARPE','SORTINO','WIN %','TRADES'].forEach(function(l){K1[l]=r5Chip(l);});
    A('R5h run report 1C: NET $0 and TRADES 0; PF, MAX DD, MAR, Sharpe, Sortino and win % dash with the one sentence','NEW',
      q('[data-wfocurve]').length===0&&!!K1.NET&&K1.NET.v==='$0'&&!K1.NET.t&&!!K1.TRADES&&K1.TRADES.v==='0'
      &&['PF','MAX DD','MAR / YR','SHARPE','SORTINO','WIN %'].every(function(l){return !!K1[l]&&K1[l].v==='—'&&K1[l].t===ZWD;})
      &&txt('[data-wfowhy]').join(' ').indexOf('took no trades in the walk-forward folds')>=0,
      Object.keys(K1).map(function(l){var o=K1[l];return l+' '+(o?(o.v+(o.t?(o.t===ZWD?' {ZWD}':(' {'+o.t.slice(0,40)+'}')):'')):'(no chip)');}).join(' ; ')
      +' || why: '+txt('[data-wfowhy]').join(' | ').slice(0,90));

    // ── the one reading, screen by screen ────────────────────────────────────────────────────
    var R5N={lead:LEAD.net.z.v,table:r5v(CT.NET),pick:r5v(PK[PKL[0]]),board:r5v(RB.TOTAL),explore:(ez&&wk)?ez.v[wk]:null,report:r5v(K1.NET)};
    var R5T={table:r5v(CT.TRADES),pick:r5v(PK['OOS trades']),board:r5v(RB.TRADES),explore:ez?ez.v['TRADES']:null,report:r5v(K1.TRADES)};
    var R5D={lead:(LEAD.mar.z.v==='—'&&LEAD.mar.z.t===ZWD),table:r5Dash(CT.DRAWDOWN),pick:r5Dash(PK['WF drawdown']),board:r5Dash(RB.DD),
      explore:!!(ez&&ez.v['DRAWDOWN']==='—'&&ez.t('DRAWDOWN')===ZWD),report:!!(K1['MAX DD']&&K1['MAX DD'].v==='—'&&K1['MAX DD'].t===ZWD)};
    A('R5z one reading on all six screens: net $0, trades 0, drawdown dashed with the one sentence','NEW',
      Object.keys(R5N).every(function(k){return R5N[k]==='$0';})&&Object.keys(R5T).every(function(k){return R5T[k]==='0';})
      &&Object.keys(R5D).every(function(k){return R5D[k]===true;}),
      JSON.stringify({net:R5N,trades:R5T,ddDashed:R5D}));

    // ══ R5 SECOND ROUND - THE RUNBOARD WALK-FORWARD SAMPLE SAYS WHICH READING IT IS ════════════
    //    The report has two walk-forward readings: its 1C WALK-FORWARD TEST chips and WF OOS pill
    //    (every fold re-tuned, the unseen trades joined) and its 1E WF column (the champion held fixed
    //    over those years). The RUNBOARD WF grid reads the first while calling itself 1E; it now says
    //    so. And with no saved test curve to draw, its funnel (and the hosted PICK RUNS chart) no
    //    longer claims the runs saved no equity curve and should be re-run.
    var R6SRC='WF here is the walk-forward test: every fold re-tuned on its own past, its unseen trades joined in fold order. These are the figures the run report shows in its 1C WALK-FORWARD TEST chips and on its WF OOS pill - not its 1E WF column, which holds the champion fixed over those years and so reads different numbers.';
    var R6EVOLD='EV = expected value: average net dollars per trade over the window this band names - net and trade count both read on that same window. The run-report 1E card carries the same row under the same name; it used to be called $ / TRADE.';
    function r6Caps(){return q('td[colspan]').map(function(td){var s=td.querySelector('[title]');
      return {v:norm(td.textContent),t:s?(s.getAttribute('title')||''):''};}).filter(function(o){return /^(return|reward ÷ risk) · /.test(o.v);});}
    function r6Ev(){var s=q('span[title]').filter(function(e){return norm(e.textContent)==='EV'&&(e.getAttribute('title')||'').indexOf('EV = expected value')===0;})[0];
      return s?(s.getAttribute('title')||''):null;}
    function r6Info(){return infopops(/SAMPLE picks the stretch every figure is measured on/).join(' || ');}
    function r6Src(){return q('[data-rbwfsrc]').map(function(e){return norm(e.textContent);});}

    var r6a=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[LW2]);
    var C6=r6Caps(),EV6=r6Ev(),IN6=r6Info(),SR6=r6Src(),TR6=tbl2();
    var r6h=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false,rbOrient:'h'},[LW2]);
    var TH6=q('table[data-rbhoriz] th[title]').map(function(e){return e.getAttribute('title')||'';});
    var SR6h=r6Src();
    A('R5m RUNBOARD WF grid names the walk-forward reading: the 1C WALK-FORWARD TEST chips and WF OOS pill, not the 1E WF column','NEW',
      clean2(r6a)&&clean2(r6h)&&C6.length===2&&C6[0].v==='return · WF test'&&C6[1].v==='reward ÷ risk · WF test'
      &&C6.every(function(o){return o.t===R6SRC;})
      &&!!EV6&&EV6.indexOf('over the walk-forward test')>0&&EV6.indexOf(R6SRC)>0&&EV6.indexOf('carries the same row under the same name')<0
      &&IN6.indexOf(R6SRC)>=0&&SR6.length===1&&SR6[0]===R6SRC
      &&TH6.indexOf('return · WF test')>=0&&TH6.indexOf('reward ÷ risk · WF test')>=0&&SR6h.length===1
      &&!!TR6.c['TOTAL']&&TR6.c['TOTAL'][0]===AB$(POOL)&&TR6.c['DD'][0]===AB$(DDW)&&TR6.c['MAR'][0]===MARW.toFixed(2),
      'captions '+JSON.stringify(C6.map(function(o){return o.v+(o.t===R6SRC?' {SRC}':(o.t?' {'+o.t.slice(0,40)+'}':''));}))
      +' | EV '+(EV6?EV6.slice(0,90):'(none)')+' | info has src '+(IN6.indexOf(R6SRC)>=0)+' | line '+SR6.length
      +' | sideways heads '+TH6.filter(function(t){return / · /.test(t);}).join(', ')+' line '+SR6h.length
      +' | TOTAL '+(TR6.c['TOTAL']||[])[0]+' DD '+(TR6.c['DD']||[])[0]+' MAR '+(TR6.c['MAR']||[])[0]);

    var N6=[];
    [['full','FULL'],['is','IS'],['lb','LB']].forEach(function(p){
      var c=rend2({c2Screen:'cmp',c2View:'board',c2Stage:p[0],rbRank:'mar',rbHeat:false},[LW2]);
      var cp=r6Caps(),ev=r6Ev(),inf=r6Info(),sr=r6Src();
      var ok=clean2(c)&&cp.length===2&&cp[0].v==='return · '+p[1]&&cp[1].v==='reward ÷ risk · '+p[1]&&cp.every(function(o){return !o.t;})
        &&ev===R6EVOLD&&inf.length>0&&inf.indexOf('WF OOS pill')<0&&sr.length===0;
      if(!ok)N6.push(p[1]+': call '+c+' captions '+JSON.stringify(cp)+' EV '+(ev===R6EVOLD?'(unchanged)':String(ev).slice(0,60))+' info '+inf.length+' line '+sr.length);});
    A('R5n RUNBOARD FULL, IS and LB keep their band captions, EV hover and info box word for word','NOREG',!N6.length,N6.join(' ; '));

    // two runs that saved no walk-forward test: the no-block copy of the tested run, and a run saved before the test
    function r6Empty(){var e=q('[data-rbwfnocurve]')[0];if(!e)return null;
      return {head:norm((e.firstElementChild||{}).textContent),lines:Array.prototype.slice.call(e.children).slice(1).map(function(x){return norm(x.textContent);}),all:norm(e.textContent)};}
    function r6EmptyOk(E){var ids=[String(FIXW.id),NOBID];
      return !!E&&E.head==='None of the selected runs saved a walk-forward test curve, so there is no walk-forward line to draw.'
        &&E.lines.length===2&&ids.every(function(id){return E.lines.filter(function(l){return l.indexOf('#'+id+' ')===0
          &&l.indexOf('No walk-forward curve — this run was saved before walk-forward detail was recorded')>0;}).length===1;})
        &&!anyText('saved an equity curve')&&!anyText('re-run them to record one');}
    var r6o=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[NOBLK,NOB]);
    var E6=r6Empty(),S6=(w._cmpEqxSeries||[]).length;
    A('R5o RUNBOARD funnel, walk-forward sample, no saved test: says no run saved a walk-forward test curve and gives each run its reason','NEW',
      clean2(r6o)&&S6===0&&r6EmptyOk(E6),
      'series '+S6+' | '+(E6?(E6.head+' || '+E6.lines.join(' || ')):('(no walk-forward empty state) old message '+anyText('saved an equity curve'))));
    var r6p=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(FIXW.id),NOBID]},[NOBLK,NOB]);
    var E6p=r6Empty(),S6p=(w._cmpEqxSeries||[]).length;
    A('R5p hosted PICK RUNS chart, walk-forward stage, no saved test: the same walk-forward empty state','NEW',
      clean2(r6p)&&S6p===0&&r6EmptyOk(E6p),
      'series '+S6p+' | '+(E6p?(E6p.head+' || '+E6p.lines.join(' || ')):('(no walk-forward empty state) old message '+anyText('saved an equity curve'))));

    var Q6=[];
    [['board','full'],['runs','lb'],['runs','full']].forEach(function(p){
      var pr={c2Screen:'cmp',c2View:p[0],c2Stage:p[1],rbRank:'mar',rbHeat:false};if(p[0]==='runs')pr.cmpIds=[String(FIXW.id),NOBID];
      var c=rend2(pr,[NOBLK,NOB]),n=(w._cmpEqxSeries||[]).length;
      if(!(clean2(c)&&n===2&&!q('[data-rbwfnocurve]').length&&!anyText('saved an equity curve')))Q6.push(p.join('/')+': call '+c+' series '+n+' empty state '+q('[data-rbwfnocurve]').length);});
    // (deferred round, D30) SPLIT: R5q was tagged NOREG but its mixed walk-forward check tested this release's own wording, so
    //   it failed on 73.818. The off-stage half stays NOREG; the mixed pick moves to R5q2 (NEW), which expects the run's own reason.
    A('R5q off the walk-forward stage the same runs still draw','NOREG',!Q6.length,Q6.join(' ; '));
    var r6q=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[LW2,NOB]);
    var NCq=w._cmpEqxNoCurve||[],NQW=(function(){var s=H.why(NOB,'curve')||'';return s.charAt(0).toLowerCase()+s.slice(1);})();
    A('R5q2 a mixed walk-forward pick still draws the one test and keys the other with its own reason','NEW',
      clean2(r6q)&&(w._cmpEqxSeries||[]).length===1&&NCq.length===1&&!!NQW&&NCq[0].why===NQW&&!q('[data-rbwfnocurve]').length,
      'series '+(w._cmpEqxSeries||[]).length+' noCurve '+JSON.stringify(NCq)+' expected '+NQW+' empty state '+q('[data-rbwfnocurve]').length);

    // ══ R5 THIRD ROUND - THE FULL-SCREEN VIEWER KEEPS EACH WALK-FORWARD TEST ON ITS OWN DATES ═════════
    //    The viewer (the expand button, or a double-click on the chart) read dates only from a run's
    //    trade list, and a walk-forward test curve carries none - only its own span. So it fell back to
    //    0..100% progress: a 1-year test and a 9-year one both began at the left edge, DATE RANGE greyed
    //    out, the calendar note went, and an IS label and an IN-SAMPLE stage sat on a chart that has no
    //    in-sample stretch. The in-page chart put the same curves on their real dates all along.
    var R7ID=String(+FIXW.id+900002),R7FROM='2024-01-05';
    // the same saved test, relabelled to a one-year window ending where #306's ends (the guard reads
    //   trades and net against the fold rows, never the window dates)
    var R7LATE=(function(){var x=clone(FIXW);x.id=R7ID;x.strategy='ZLATEWF_1_0.py';x.starred=false;x.validate.wf_oos.from=R7FROM;return lite(x,R7ID);})();
    var R7F=(Date.parse(R7FROM)-Date.parse(B.from))/(Date.parse(B.to)-Date.parse(B.from));
    // open the viewer on the series the chart just stashed, draw it now (a resize redraws at once),
    //   switch every curve on (one group-toggle click greys them all in, so each line's own x can be
    //   read), read the chart back, and close it
    function r7View(){var S=w._cmpEqxSeries||[],before=Array.prototype.slice.call(d.body.children),o={n:S.length,x:{},texts:[],stages:[]};
      o.split=S.some(function(s){return s&&(s.wfi!=null||s.li!=null);});
      try{w.expandCompareEq(S,{noTabs:true});}catch(e){o.threw=String(e&&e.message||e);return o;}
      var el=Array.prototype.slice.call(d.body.children).filter(function(x){return before.indexOf(x)<0;})[0];
      if(!el){o.none=true;return o;}
      try{w.dispatchEvent(new w.Event('resize'));var tg=el.querySelector('[data-ceqx-grp-tog="cfg"]');if(tg)tg.click();}catch(e){o.threw=String(e&&e.message||e);}
      var sv=el.querySelector('#ceqx-svg');
      o.texts=sv?Array.prototype.slice.call(sv.querySelectorAll('text')).map(function(t){return norm(t.textContent);}):[];
      (sv?Array.prototype.slice.call(sv.querySelectorAll('path[data-sr]')):[]).forEach(function(p){
        var m=(p.getAttribute('d')||'').match(/-?[0-9.]+/g)||[],xs=[];for(var i=0;i<m.length;i+=2)xs.push(+m[i]);if(!xs.length)return;
        var id=p.getAttribute('data-sr'),a=Math.min.apply(null,xs),b=Math.max.apply(null,xs),c=o.x[id];
        o.x[id]=c?[Math.min(c[0],a),Math.max(c[1],b)]:[a,b];});
      var band=sv?Array.prototype.slice.call(sv.querySelectorAll('rect')).filter(function(r){return (r.getAttribute('fill')||'').indexOf('96,165,250')>=0;})[0]:null;
      o.band=band?[+band.getAttribute('x'),(+band.getAttribute('x'))+(+band.getAttribute('width'))]:null;
      var dg=el.querySelector('#ceqx-viewdate'),sg=el.querySelector('#ceqx-viewstage');
      o.dateOn=!!(dg&&!dg.disabled);
      o.stages=sg?Array.prototype.slice.call(sg.querySelectorAll('option')).map(function(x){return x.value;}):[];
      o.errs=sink.errors.concat(sink.uncaught);
      var cl=el.querySelector('#ceqx-close');try{if(cl)cl.click();else el.remove();}catch(_){try{el.remove();}catch(__){}}
      return o;}
    function r7Dates(o){return o.texts.filter(function(t){return /^[0-9]{1,2}\/[0-9]{1,2}\/[0-9]{2}$/.test(t);});}
    var R7={},R7bad=[];
    [['RUNBOARD funnel',{c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false}],
     ['PICK RUNS chart',{c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[R7ID,String(FIXW.id)]}],
     ['COMPARE overlay',{c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[R7ID,String(FIXW.id)]}]].forEach(function(p){
      var c=rend2(p[1],[R7LATE,LW2]),first=String(((w._cmpEqxSeries||[])[0]||{}).id),o=r7View();R7[p[0]]=o;
      var xw=o.x[String(FIXW.id)],xl=o.x[R7ID],pw=xw?xw[1]:null,dd=r7Dates(o);
      var ok=clean2(c)&&!o.threw&&!o.none&&o.n===2&&!(o.errs||[]).length&&!!xw&&!!xl&&pw>100
        &&Math.abs(xw[0])<1&&Math.abs(xl[1]-pw)<1&&Math.abs(xl[0]/pw-R7F)<0.01
        &&o.texts.indexOf('x = calendar time (shared)')>=0&&dd.length>=2&&o.dateOn
        &&o.texts.indexOf('IS')<0&&o.texts.indexOf('WF')>=0&&!!o.band&&Math.abs(o.band[0])<1&&Math.abs(o.band[1]-pw)<1
        &&o.stages.indexOf('is')<0&&o.stages.indexOf('wf')>=0;
      if(!ok)R7bad.push(p[0]);
      o.sum=p[0].split(' ')[1]+(clean2(c)?'':(' call '+c))+(o.threw?(' threw '+o.threw):'')+(o.n===2?'':(' n'+o.n))+' 1st #'+first
        +': #'+FIXW.id+' '+(xw?xw.map(Math.round).join('-'):'-')+', #'+R7ID+' '+(xl?xl.map(Math.round).join('-'):'-')
        +' at '+(xl&&pw?(xl[0]/pw).toFixed(3):'-')+'/'+R7F.toFixed(3)
        +'; '+(dd[0]||'no date')+(o.texts.indexOf('x = calendar time (shared)')>=0?' cal':' nocal')
        +'; RANGE '+(o.dateOn?'on':'off')+'; IS '+(o.texts.indexOf('IS')>=0?'y':'n')+' WF '+(o.texts.indexOf('WF')>=0?'y':'n')
        +'; band '+(o.band?o.band.map(Math.round).join('-'):'-')+'; '+o.stages.join(',')+((o.errs||[]).length?(' ERR '+String(o.errs[0]).slice(0,60)):'');});
    A('R5r full-screen viewer draws each walk-forward test over its own dates, on one calendar, with no in-sample stretch','NEW',
      !R7bad.length,Object.keys(R7).map(function(k){return R7[k].sum;}).join(' || '));

    var R7n=[];
    [['board',{c2Screen:'cmp',c2View:'board',c2Stage:'full',rbRank:'mar',rbHeat:false}],
     ['board is',{c2Screen:'cmp',c2View:'board',c2Stage:'is',rbRank:'mar',rbHeat:false}],
     ['overlay',{c2Screen:'cmp',c2View:'ovl',c2Stage:'full',cmpIds:[String(FIXW.id)]}]].forEach(function(p){
      var c=rend2(p[1],[LW2]),S0=(w._cmpEqxSeries||[])[0]||{},o=r7View();
      // F5 (audit round 3) gave a RUNBOARD IS/LB slice its OWN [from,to] span too, so it can
      //   draw on its own stretch of calendar in the inline funnel instead of the whole run's
      //   width — a second, unrelated reason for a series to carry `span`, so this guard now
      //   checks the one thing R5 is actually about (a walk-forward TEST curve, which has no
      //   trade list and is dated by span alone) rather than "no span at all".
      var ok=clean2(c)&&!o.threw&&!o.none&&o.n===1&&!(o.errs||[]).length&&!S0.wfoCurve&&!!(S0.blot&&S0.blot.date_from)
        &&o.texts.indexOf('x = calendar time (shared)')>=0&&o.dateOn&&o.stages.join(',')==='is,wf,lb'
        &&((o.texts.indexOf('IS')>=0)===o.split);
      if(!ok)R7n.push(p[0]+': call '+c+(o.threw?(' threw '+o.threw):'')+' series '+o.n+' wfoCurve '+JSON.stringify(!!S0.wfoCurve)+' span '+JSON.stringify(S0.span||null)
        +' note '+(o.texts.indexOf('x = calendar time (shared)')>=0)+' DATE RANGE '+o.dateOn+' stages '+o.stages.join(',')
        +' split '+o.split+' IS label '+(o.texts.indexOf('IS')>=0)+((o.errs||[]).length?(' errors '+String(o.errs[0]).slice(0,80)):''));});
    A('R5s off the walk-forward stage the full-screen viewer keeps its calendar, DATE RANGE, IN-SAMPLE stage and IS label','NOREG',!R7n.length,R7n.join(' ; '));

    // ══ DEFERRED ROUND - one case per re-verified finding (D01, D18, D19, D27, D28, D29, D31, D32, D33, D37) ══════════
    //    Round 2 adds D18b (item 4), D18c (item 3) and D27b (item 1) - each fails on the round-1 build and
    //    passes once its fix lands.
    //    Each NEW case fails on 73.820 and passes once the fix lands. DX37 is time-zone dependent: it can only fail on the
    //    old build where the machine is west of UTC (this one is America/Los_Angeles), and passes on every zone after the fix.
    function dxNote(){var c=q('div').filter(function(x){return x.querySelector('b')&&/not on this chart/.test(x.textContent||'');});
      c.sort(function(a,b){return (a.textContent||'').length-(b.textContent||'').length;});return c[0]?norm(c[0].textContent):'';}
    function dxFold(id,name,fold,mod){var x=clone(FIXB);x.id=String(id);x.strategy=name;x.starred=false;delete x.gate_validate;delete x.ml_gate;
      (x.top10_results||[]).forEach(function(f){if(f&&f.fold===fold)mod(f);});return x;}
    function dxNum(s){var m=String(s==null?'':s).match(/-?[0-9]+[.][0-9]+/);return m?+m[0]:null;}
    function dxView(fn){var S=w._cmpEqxSeries||[],before=Array.prototype.slice.call(d.body.children),o={};
      try{w.expandCompareEq(S,{noTabs:true});}catch(e){o.threw=String(e&&e.message||e);return o;}
      var el=Array.prototype.slice.call(d.body.children).filter(function(x){return before.indexOf(x)<0;})[0];if(!el){o.none=true;return o;}
      try{fn(el,o);}catch(e){o.threw=String(e&&e.message||e);}
      var cl=el.querySelector('#ceqx-close');try{if(cl)cl.click();else el.remove();}catch(_){try{el.remove();}catch(__){}}
      return o;}

    // D01 - the report's older walk-forward column (no gate study, no saved test) pools an all-loss or an all-win fold the way
    //   the LEADERBOARD and PICK RUNS do. It dropped that fold and read 1.81 against 1.76 / 1.84.
    var D01=[];
    [['all-loss',function(f){f.oos_pf=0;f.oos_wins=0;f.oos_pnl=-300;}],['all-win',function(f){f.oos_pf=null;f.oos_wins=f.oos_trades;f.oos_pnl=400;}]].forEach(function(p,i){
      var x=dxFold(+FIXB.id+930001+i,'ZPOOL'+i+'_1_0.py',5,p[1]);
      var c1=render({},[lite(x)],[full(x)],x.id),K=kpi(),rep=kc(K,'PF','WF');
      var c2=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'pf'},[lite(x)]),fb=famBig(),lead=fb?fb.v:null;
      var c3=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(x.id)]},[lite(x)]),T=tbl2(),pick=(T.c['WF PF']||[])[0];
      D01.push({ok:(c1==='OK')&&clean2(c2)&&clean2(c3)&&dxNum(rep)!=null&&dxNum(rep)===dxNum(lead)&&dxNum(lead)===dxNum(pick),
        s:p[0]+': report '+rep+' / leaderboard '+lead+' / pick runs '+pick});});
    A('DX01 report 1E walk-forward PF with no saved test pools an all-loss or all-win fold like the LEADERBOARD and PICK RUNS','NEW',
      D01.length===2&&D01.every(function(o){return o.ok;}),D01.map(function(o){return o.s;}).join(' | '));

    // D01 (repair) - an older run with no whole-run averages saved and one walk-forward fold that broke exactly even. The first
    //   D01 build dashed that walk-forward PF, and the same dash dropped the whole walk-forward stretch out of the Past Runs PF
    //   and the report TOTAL PF, AVG WIN, AVG LOSS and DD (R) (Past Runs 1.36 -> 1.07). The twin's fold 2 sits a hair off even
    //   with the same $0, which every pool reads as adding nothing, so the twin reads what 73.820 read; the even run must read
    //   the same whole-run figures. Holds on 73.820 and after the repair; fails on the first D01 build.
    function dxOldRun(id,name,pf){var x=dxFold(id,name,2,function(f){f.oos_pf=pf;f.oos_pnl=0;});
      ['total_avg_win','total_avg_loss','total_win_rate'].forEach(function(k){delete x.validate[k];});
      if(x.validate.gate_bakeoff)delete x.validate.gate_bakeoff.ungated_full;return x;}
    var EV01=dxOldRun(+FIXB.id+930041,'ZEVENOLD_1_0.py',1.0),TW01=dxOldRun(+FIXB.id+930042,'ZEVENTWIN_1_0.py',1.0002);
    function pastPf(x){var c=render({},[lite(x)],[],'999999'),tr=q('tr.arow[data-run]')[0];if(c!=='OK'||!tr)return '(render)';
      var tb=tr.closest('table'),ths=tb?Array.prototype.slice.call(tb.querySelectorAll('thead th')):[];
      var i=ths.map(function(th){return norm(th.textContent);}).findIndex(function(t){return /^PF\b/.test(t);});
      return (i>=0&&tr.children[i])?norm(tr.children[i].textContent):'(no PF column)';}
    function totOf(x){var c=render({},[lite(x)],[full(x)],x.id),K=kpi(),o={call:c};
      ['PF','AVG WIN','AVG LOSS','DD (R)'].forEach(function(l){o[l]=kc(K,l,'TOTAL');});o.wf=kc(K,'PF','WF');return o;}
    var pE01=pastPf(EV01),pT01=pastPf(TW01),kE01=totOf(EV01),kT01=totOf(TW01);
    A('DX01b an older run with one walk-forward fold broken exactly even keeps the walk-forward stretch in the Past Runs PF and the report TOTAL column','NOREG',
      /^[0-9]+[.][0-9]{2}$/.test(pT01)&&pE01===pT01&&kE01.call==='OK'&&kT01.call==='OK'
      &&['PF','AVG WIN','AVG LOSS','DD (R)'].every(function(l){return !!kT01[l]&&kT01[l]!=='—'&&kE01[l]===kT01[l];}),
      'Past Runs PF '+pE01+' vs twin '+pT01+' | TOTAL '+['PF','AVG WIN','AVG LOSS','DD (R)'].map(function(l){return l+' '+kE01[l]+' vs '+kT01[l];}).join(', ')
      +' | WF PF '+kE01.wf+' vs twin '+kT01.wf);

    // D18 - a fold that broke exactly even: every screen names it, not 'saved before walk-forward detail was recorded'
    var BE=dxFold(+FIXB.id+930011,'ZBREAKEVEN_1_0.py',2,function(f){f.oos_pf=1.0;f.oos_pnl=0;});
    var BEW='Walk-forward fold 2 broke exactly even (profit factor 1.00)',D18={};
    (function(){var c=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'pf'},[lite(BE)]),f=famBig();D18.leadPF=(clean2(c)&&f)?f.t:'(render)';})();
    (function(){var c=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:'rpy'},[lite(BE)]),f=famBig();D18.leadRYR=(clean2(c)&&f)?f.t:'(render)';})();
    (function(){var c=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(BE.id)]},[lite(BE)]),T=tbl2();
      D18.ovlPF=clean2(c)?((T.t['PF']||[])[0]||''):'(render)';D18.ovlRYR=clean2(c)?((T.t['R / YR']||[])[0]||''):'(render)';})();
    (function(){var c=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[lite(BE)]),T=tbl2();D18.boardPF=clean2(c)?((T.t['PF']||[])[0]||''):'(render)';})();
    (function(){var c=render({},[lite(BE)],[full(BE)],BE.id);D18.reportPF=(c==='OK')?(kt(kpi(),'PF','WF')||''):'(render)';})();
    A('DX18 a walk-forward fold that broke exactly even is named on the LEADERBOARD, OVERLAY, RUNBOARD and report dashes','NEW',
      Object.keys(D18).length===6&&Object.keys(D18).every(function(k){return D18[k].indexOf(BEW)===0;}),
      Object.keys(D18).map(function(k){return k+' {'+D18[k].slice(0,60)+'}';}).join(' | '));

    // D18b (deferred round 2, item 4) - PICK RUNS 'WF PF': a run with no saved test used to print a bare
    //   dash with no reason, unlike RUNBOARD / OVERLAY / LEADERBOARD just above. It must dash through the
    //   same walk-forward dash helper and carry the same fold reason.
    var c18b=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(BE.id)]},[lite(BE)]),T18b=tbl2();
    var pf18b=(T18b.c['WF PF']||[])[0]||'',tip18b=(T18b.t['WF PF']||[])[0]||'';
    A('DX18b PICK RUNS \'WF PF\' dashes with the walk-forward fold reason (broke exactly even), not a bare dash','NEW',
      clean2(c18b)&&pf18b==='—'&&!!tip18b&&tip18b.indexOf(BEW)===0,
      'cell='+pf18b+' tip={'+tip18b.slice(0,120)+'}');

    // D18c (deferred round 2, item 3) - a fold that saved profit factor 0.00 (the engine's own reading for
    //   a fold that lost every dollar) with negative money and no saved win count: the fold-pooling 'why'
    //   text used to say it 'saved no profit factor that splits its money' - contradicting the 1C chart on
    //   the same page, which draws PF 0.00 for that very fold. It must get its own sentence, and the
    //   pooled PF must still dash (pooling itself is unchanged).
    var PZ=dxFold(+FIXB.id+930081,'ZPFZERO_1_0.py',3,function(f){f.oos_pf=0;f.oos_pnl=-500;delete f.oos_wins;});
    var pzWhy=H.why(full(PZ),'pf');
    var c18c=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[lite(PZ)]),T18c=tbl2();
    var pf18c=(T18c.c['PF']||[])[0]||'',tip18c=(T18c.t['PF']||[])[0]||'';
    A('DX18c a walk-forward fold with profit factor 0.00 and no saved win count gets its own pooled-PF reason, not \'saved no profit factor\'','NEW',
      clean2(c18c)&&pzWhy.indexOf('lost every dollar')>=0&&pzWhy.indexOf('profit factor 0.00')>=0&&pzWhy.indexOf('no win count')>=0
      &&pzWhy.indexOf('saved no profit factor that splits')<0&&pf18c==='—'&&tip18c.indexOf('lost every dollar')>=0,
      'why={'+pzWhy.slice(0,170)+'} | RUNBOARD PF cell='+pf18c+' tip={'+tip18c.slice(0,170)+'}');

    // D19 - the note under the EXPLORE chart gives that same cause (and says '1 records')
    var c19=rend2({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['wf'],resAxis:'evr',resXAxis:'so'},[lite(BE),lite(FIXB)]),N19=dxNote();
    A('DX19 EXPLORE note: a run whose walk-forward fold broke even is counted by that cause, not as recording no average loss','NEW',
      clean2(c19)&&N19.indexOf('a walk-forward fold broke exactly even, so no PF or EV R can be pooled')>=0
      &&N19.indexOf('no average loss recorded for EV R')<0&&!/(^| )1 record [a-z]/.test(N19),N19.slice(0,420));

    // D19 (repair) - the cause is worded by the stretch that gave it. IN-SAMPLE on a run with no whole-run average win or
    //   loss, and LOCKBOX on a lockbox with no average win and loss and no PF, read 'walk-forward money cannot be split'
    //   on the first 73.820 build. Walk-forward keeps its own clause, and in-sample inherits a broken-even fold's clause.
    var OLD19=(function(){var x=clone(FIXB);x.id=String(+FIXB.id+930015);x.strategy='ZOLDAVG_1_0.py';x.starred=false;
      delete x.validate.total_avg_win;delete x.validate.total_avg_loss;return lite(x);})();
    var LBN19=(function(){var x=clone(FIXB);x.id=String(+FIXB.id+930016);x.strategy='ZLBNOAVG_1_0.py';x.starred=false;
      var lb=x.validate.lockbox;delete lb.avg_win;delete lb.avg_loss;lb.pf=null;return lite(x);})();
    var SP19=dxFold(+FIXB.id+930019,'ZSPLIT_1_0.py',3,function(f){f.oos_pf=0;delete f.oos_wins;});
    var OK19a=(function(){var x=clone(FIXB);x.id=String(+FIXB.id+930017);x.strategy='ZFINE_1_0.py';x.starred=false;return lite(x);})();
    var OK19b=(function(){var x=clone(FIXB);x.id=String(+FIXB.id+930018);x.strategy='ZFINE2_1_0.py';x.starred=false;return lite(x);})();
    // F2 (g2-stage) supersedes the isLong / isShort / isEven premises below: IN-SAMPLE on a
    //   run row now reads the champion's own measured gate-study slice (gate_validate.
    //   ungated_is), never a figure derived from the run's whole-run averages or its
    //   walk-forward fold rows - so a run missing either no longer dashes IN-SAMPLE at all
    //   (isLong / isShort now plot cleanly, moved off the SORTINO axis, which IN-SAMPLE
    //   still never saves, onto PF, which it now does). isEven's premise (a broken-even WF
    //   fold blanking IN-SAMPLE) cannot be reproduced any more - IN-SAMPLE cannot see the
    //   fold rows at all now - so that sub-case is retired outright. LOCKBOX and
    //   WALK-FORWARD keep their own clause, unchanged.
    var N19r={},C19=[],P19={lbLong:'its lockbox saved no average win and loss, so no PF or EV R can be worked out',
      wfSplit:'its walk-forward money cannot be split into winning and losing trades, so no PF or EV R can be pooled'};
    [['isLong',['is'],'evr','pf',[OLD19,OK19a]],['isShort',['is'],'pf','wr',[OLD19,OK19a,OK19b]],['lbLong',['lb'],'evr','so',[LBN19,OK19a]],
     ['wfSplit',['wf'],'evr','so',[lite(SP19),OK19a]]].forEach(function(p){
      C19.push(rend2({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:p[1],resAxis:p[2],resXAxis:p[3]},p[4]));N19r[p[0]]=dxNote();});
    A('DX19b EXPLORE note: F2 - a run missing its whole-run averages no longer dashes IN-SAMPLE at all (isLong / isShort plot clean); LOCKBOX and WALK-FORWARD keep their own clause','NEW',
      C19.every(clean2)&&!N19r.isLong&&!N19r.isShort
      &&(N19r.lbLong||'').indexOf(P19.lbLong)>=0&&(N19r.wfSplit||'').indexOf(P19.wfSplit)>=0
      &&N19r.wfSplit.indexOf('lockbox saved')<0&&N19r.wfSplit.indexOf('whole-run average')<0,
      Object.keys(N19r).map(function(k){return k+' {'+N19r[k].slice(0,230)+'}';}).join(' | '));

    // D27 - RUNBOARD WF WINDOW for a run with no saved test: the split-to-lockbox window its own years reader uses
    var NT=(function(){var x=clone(FIXB);x.id=String(+FIXB.id+930021);x.strategy='ZNOTEST_1_0.py';x.starred=false;x.validate.windows.wf_split='2015-01-02';return x;})();
    var c27=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[lite(NT)]),T27=tbl2();
    var win27=(T27.c['WINDOW']||[])[0]||'',tip27=(T27.t['WINDOW']||[])[0]||'';
    var c27o=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(NT.id)]},[lite(NT)]),yrs27=(tbl2().c['YEARS']||[])[0]||'';
    var lb27=String(((NT.validate.windows||{}).lockbox||[])[0]||(NT.validate.lockbox||{}).from||'').slice(0,10);
    A('DX27 RUNBOARD walk-forward WINDOW with no saved test reads the split to the lockbox door, the years the OVERLAY uses','NEW',
      clean2(c27)&&clean2(c27o)&&!!lb27&&win27.indexOf('2015-01-02 – '+lb27)===0&&!!yrs27&&win27.slice(-(yrs27.length+1))===yrs27+'y'
      &&tip27.indexOf('walk-forward split')>=0,'WINDOW '+win27+' {'+tip27.slice(0,70)+'} | OVERLAY YEARS '+yrs27+' | lockbox door '+lb27);

    // D27b (deferred round 2, item 1) - RUNBOARD WF WINDOW for a run whose saved test is REJECTED (a
    //   trade-count mismatch against its own fold rows), not merely absent. The hover must not claim
    //   'No walk-forward test is saved' - it must say the saved test is not used and name the check's own
    //   reason (the same one the neighbouring MAR / DD cells give), then still read the split-to-lockbox
    //   window like the no-test case above.
    var MM27=(function(){var x=clone(FIXW);x.id=String(+FIXW.id+930091);x.strategy='ZMISMATCH_1_0.py';x.starred=false;
      x.validate=clone(FIXW.validate);x.validate.wf_oos=clone(FIXW.validate.wf_oos);
      x.validate.wf_oos.trades=+x.validate.wf_oos.trades+7;
      x.validate.windows=clone(FIXW.validate.windows||{});x.validate.windows.wf_split='2016-03-04';return x;})();
    var mm27St=H.chk(lite(MM27)).st;
    var c27m=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[lite(MM27)]),T27m=tbl2();
    var win27m=(T27m.c['WINDOW']||[])[0]||'',tip27m=(T27m.t['WINDOW']||[])[0]||'';
    A('DX27b RUNBOARD walk-forward WINDOW: a rejected saved test (trade-count mismatch) names the reason instead of \'No walk-forward test is saved\'','NEW',
      clean2(c27m)&&mm27St==='mismatch'&&!!win27m&&tip27m.indexOf('No walk-forward test is saved on this run')<0
      &&tip27m.indexOf('is not used on this run')>=0&&tip27m.indexOf('does not match this run')>=0
      &&tip27m.indexOf('its walk-forward years are read from the walk-forward split')>=0,
      'state='+mm27St+' WINDOW='+win27m+' tip={'+tip27m.slice(0,240)+'}');

    // D28 - EXPLORE on WALK-FWD alone, a saved test with no losing trade: MAR, PF and R / YR give the test's own reasons
    var NL28=(function(){var x=clone(FIXW);x.id=String(+FIXW.id+930031);x.strategy='ZNOLOSS_1_0.py';x.starred=false;
      var b=x.validate.wf_oos;b.profit_factor=null;b.max_drawdown=0;b.gross_loss=0;b.sortino=null;return x;})();
    var c28=rend2({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:['wf'],resAxis:'evr',resXAxis:'so',c2Tbl:true,resCols:'all'},[lite(NL28)]),R28=reRow(NL28.id);
    var PFNL='No walk-forward trade lost, so a profit factor cannot be worked out.',NDD='This stretch never drew down, so MAR has nothing to divide by.';
    A('DX28 EXPLORE walk-forward alone, a test with no losing trade: MAR says it never drew down, PF and R / YR say no trade lost','NEW',
      clean2(c28)&&!!R28&&R28.v['MAR']==='—'&&R28.t('MAR')===NDD&&R28.v['PF']==='—'&&R28.t('PF')===PFNL&&R28.v['R / YR']==='—'&&R28.t('R / YR')===PFNL,
      R28?['DRAWDOWN','MAR','PF','R / YR'].map(function(h){return h+' '+R28.v[h]+' {'+(R28.t(h)||'').slice(0,60)+'}';}).join(' | '):'(no row)');

    // D29 - LEADERBOARD WF note: the second count is only runs saved before the test (never a book, never a test with no trades)
    var ZB=lite(FIXZ),runs29=[LW2,NOB,lite(BE),lite(NL28),ZB,LBK2];
    var exp29=runs29.filter(function(x){return H.chk(x).st==='absent';}).length,N29=[];
    ['mar','pf','rpy'].forEach(function(rk){var c=rend2({c2Screen:'lead',c2Stage:'wf',c2Rank:rk},runs29),t=q('.c2-note').map(function(e){return norm(e.textContent);}).join(' ');
      if(!(clean2(c)&&t.indexOf('('+exp29+' saved before the walk-forward test was recorded)')>=0&&t.indexOf('without a walk-forward figure)')<0))
        N29.push(rk+': '+(t.match(/runs saved before that show a dash [(][^)]*[)]/)||['(no count)'])[0]);});
    A('DX29 LEADERBOARD walk-forward note counts only the runs saved before the test','NEW',exp29===2&&!N29.length,'expected '+exp29+' | '+N29.join(' | '));

    // D31 - chart keys on walk-forward: no in-sample line style, each test's length, and each missing curve's own reason
    var ids31=[String(FIXW.id),NOBID,String(FIXZ.id),String(FIXBK.id)],runs31=[LW2,NOB,ZB,LBK2];
    function keys31(){var o={key:q('.cmpovl-key').map(function(e){return norm(e.textContent);}).join(' || '),
      row:q('[data-ovltog="'+FIXW.id+'"]').map(function(e){return norm(e.textContent);})[0]||'',why:{},nc:[],
      rowH:(q('.cmpovl-key > [data-ovltog]')[0]||{}).offsetHeight||0};
      (w._cmpEqxNoCurve||[]).forEach(function(n){o.why[String(n.id)]=n.why||'';});
      // (repair) the no-curve rows themselves: one short line each, the run's reason in the hover
      q('.cmpovl-key > div:not([data-ovltog])').forEach(function(e){var t=norm(e.textContent);
        if(!/^#[0-9]+ /.test(t))return;
        o.nc.push({t:t,tip:e.getAttribute('title')||'',ws:w.getComputedStyle(e).whiteSpace,h:e.offsetHeight});});
      return o;}
    // a key row for a run with no walk-forward curve stays one short line (the key box sits over the plot), its reason in the hover
    function nc31(o,n){var whys=Object.keys(o.why).map(function(k){return o.why[k];});
      return o.nc.length===n&&o.rowH>0&&o.nc.every(function(r){return r.ws==='nowrap'&&/ · no walk-forward curve$/.test(r.t)
        &&!!r.tip&&whys.indexOf(r.tip)>=0&&r.t.indexOf(r.tip)<0&&r.h<=o.rowH+2;});}
    function ok31(o,withBook){return o.key.indexOf('in-sample')<0&&/· [0-9]+[.][0-9]y/.test(o.row)
      &&(o.why[NOBID]||'')===NCW(NOB)&&(o.why[String(FIXZ.id)]||'').indexOf('took no trades in the walk-forward folds')>=0
      &&(!withBook||o.why[String(FIXBK.id)]==='a book tunes nothing, so it has no walk-forward folds');}
    var c31p=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:ids31},runs31),K31p=keys31();
    var c31o=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:ids31},runs31),K31o=keys31(),note31=q('.c2-note').map(function(e){return norm(e.textContent);}).join(' ');
    var c31b=rend2({c2Screen:'cmp',c2View:'board',c2Stage:'wf',rbRank:'mar',rbHeat:false},[LW2,NOB,ZB]),K31b=keys31();
    A('DX31 walk-forward chart keys: no in-sample row, each test length, and a book, an empty test and an old run each give their own reason','NEW',
      clean2(c31p)&&clean2(c31o)&&clean2(c31b)&&ok31(K31p,true)&&ok31(K31o,true)&&ok31(K31b,false)
      &&note31.indexOf('hover each name in the chart key for the reason')>=0&&note31.indexOf('saved no walk-forward curve')<0,
      'PICK '+K31p.key.slice(0,90)+' '+JSON.stringify(K31p.why).slice(0,200)+' | BOARD row '+K31b.row+' | note points at the key hover '+(note31.indexOf('hover each name in the chart key for the reason')>=0));
    A('DX31c walk-forward chart keys: a run with no curve is one short line, its own reason in the hover of that row, not wrapped over the plot','NEW',
      nc31(K31p,3)&&nc31(K31o,3)&&nc31(K31b,2),
      ['PICK','OVERLAY','BOARD'].map(function(nm,i){var o=[K31p,K31o,K31b][i];return nm+' rowH '+o.rowH+' '+JSON.stringify(o.nc.map(function(r){return [r.t.slice(0,50),r.ws,r.h,r.tip.slice(0,40)];}));}).join(' | '));

    // D32 - the full-screen viewer on walk-forward: TRADES is off with its reason, and no hint promises trades
    // D37 - its DATE RANGE starts on the test's saved first date, not the day before
    var c32=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'wf',cmpIds:[String(FIXW.id)]},[LW2]);
    var hint32=q('.cmpovl-hint').map(function(e){return norm(e.textContent);})[0]||'';
    var v32=dxView(function(el,o){var b=el.querySelector('#ceqx-blot');o.dis=!!(b&&b.disabled);o.tip=b?(b.getAttribute('title')||''):'';
      var vs=el.querySelector('#ceqx-view');if(vs){vs.value='custom';if(vs.onchange)vs.onchange();}
      var cf=el.querySelector('#ceqx-cfrom'),ct=el.querySelector('#ceqx-cto');o.from=cf?cf.value:null;o.to=ct?ct.value:null;});
    var c32o=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'wf',cmpIds:[String(FIXW.id)]},[LW2]);
    var exp32=q('[data-cmpexpand]').map(function(e){return e.getAttribute('title')||'';})[0]||'';
    A('DX32 walk-forward viewer: TRADES is switched off with its reason, and neither hint promises a trade list','NEW',
      clean2(c32)&&clean2(c32o)&&!v32.threw&&!v32.none&&v32.dis===true&&v32.tip.indexOf('no single trade list')>=0
      &&hint32.indexOf('trades')<0&&hint32.indexOf('more')>=0&&exp32==='open the fullscreen explorer',
      'disabled '+v32.dis+' {'+String(v32.tip||'').slice(0,50)+'} hint '+hint32+' | expand '+exp32+(v32.threw?(' threw '+v32.threw):''));
    A('DX37 walk-forward viewer DATE RANGE opens on the saved test dates, not a day early','NEW',
      !v32.threw&&v32.from===String(B.from).slice(0,10)&&v32.to===String(B.to).slice(0,10),'from '+v32.from+' to '+v32.to+' saved '+B.from+' to '+B.to);
    var c32f=rend2({c2Screen:'cmp',c2View:'runs',c2Stage:'full',cmpIds:[String(FIXW.id)]},[LW2]);
    var hint32f=q('.cmpovl-hint').map(function(e){return norm(e.textContent);})[0]||'';
    var v32f=dxView(function(el,o){var b=el.querySelector('#ceqx-blot');o.dis=!!(b&&b.disabled);});
    var c32fo=rend2({c2Screen:'cmp',c2View:'ovl',c2Stage:'full',cmpIds:[String(FIXW.id)]},[LW2]);
    var exp32f=q('[data-cmpexpand]').map(function(e){return e.getAttribute('title')||'';})[0]||'';
    A('DX32b off the walk-forward stage TRADES stays on and both hints still offer the trade list','NOREG',
      clean2(c32f)&&clean2(c32fo)&&!v32f.threw&&v32f.dis===false&&hint32f.indexOf('trades + more')>=0&&exp32f==='open the fullscreen explorer, with the trade blotter',
      'disabled '+v32f.dis+' hint '+hint32f+' | expand '+exp32f);

    // D33 - the EXPLORE R / YR heading claims the 1E matrix figure only on LOCKBOX alone
    function h33(segs){var c=rend2({c2Screen:'explore',resLvl:'valid',resShow:'runs',resSegs:segs,resAxis:'evr',resXAxis:'so',c2Tbl:true,resCols:'all'},[LW2]);
      return clean2(c)?(q('th[data-resort="rpy"]').map(function(e){return e.getAttribute('title')||'';})[0]||''):'(render)';}
    var H33w=h33(['wf']),H33l=h33(['lb']),H33a=h33(['is','wf','lb']);
    A('DX33 EXPLORE R / YR heading: the 1E matrix claim only on LOCKBOX alone; WALK-FWD alone names the walk-forward test','NEW',
      H33l.indexOf('The same figure the run report 1E matrix prints.')>=0&&H33w.indexOf('1E matrix prints')<0&&H33w.indexOf('not its 1E WF column')>=0
      &&H33a.indexOf('1E matrix prints')<0&&H33a.indexOf('1E WF column')<0,
      'WF '+H33w.slice(-120)+' | LB has claim '+(H33l.indexOf('1E matrix prints')>=0)+' | all three has claim '+(H33a.indexOf('1E matrix prints')>=0));

    delete out._v;
    finish('done');
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){try{run();}catch(e){out.err=String(e&&e.stack?e.stack:e);finish('threw');}},2500);});
  setTimeout(function(){finish('backstop');},240000);
})();
"""

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>wf_oos probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
__JS__
</script>
</body></html>
"""


def find_chrome():
    cands = [os.path.join('C:' + os.sep, 'Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
             os.path.join('C:' + os.sep, 'Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe')]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'))
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
                with open(alt_index, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

        def log_message(self, *a):
            pass
    return H


def attempt(chrome, root, alt_index, fixb, fixw, fixbk, fixz):
    pdir = os.path.join(root, '_wfoosprobe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, 'probe.html')
    js = (PROBE_JS.replace('__FIXB__', json.dumps(fixb)).replace('__FIXW__', json.dumps(fixw))
          .replace('__FIXBK__', json.dumps(fixbk)).replace('__FIXZ__', json.dumps(fixz)))
    io.open(ppath, 'w', encoding='utf-8').write(PROBE_HTML.replace('__JS__', js))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='wfoosprobe-')
    try:
        dom = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--user-data-dir=' + prof,
             '--virtual-time-budget=300000', '--dump-dom',
             'http://127.0.0.1:%d/_wfoosprobe/probe.html' % port],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900).stdout or ''
    except Exception as e:
        return None, 'chrome failed: %s' % e
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'WFOOSPROBE: (\{.*?\})</pre>', dom, re.S)
    if not m:
        return None, 'probe produced no readout'
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
                          .replace('&amp;', '&')), ''
    except Exception as e:
        return None, 'unreadable readout: %s' % e


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--write-snapshot', action='store_true', help='write the Past Runs no-block snapshot and exit')
    ap.add_argument('--verbose', action='store_true', help='print every assertion')
    a = ap.parse_args(argv)
    t0 = time.time()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fixd = os.path.join(root, 'tools', 'fixtures')
    paths = {k: os.path.join(fixd, v) for k, v in
             (('b', 'run_report.json'), ('w', 'run_wfoos.json'), ('bk', 'run_book_synth.json'),
              ('z', 'run_wfoos_zero.json'))}
    snap_path = os.path.join(fixd, 'wfoos_pastruns_snapshot.json')
    for k, p in paths.items():
        if not os.path.isfile(p):
            print('WFOOS PROBE: INCONCLUSIVE -- fixture missing: %s (build it with tools/%s)'
                  % (p, 'make_wfoos_zero_fixture.py' if k == 'z' else 'make_wfoos_fixture.py'))
            return INCONCLUSIVE
    alt = os.path.abspath(a.file) if a.file else None
    if alt and not os.path.isfile(alt):
        print('WFOOS PROBE: INCONCLUSIVE -- --file not found: %s' % alt)
        return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print('WFOOS PROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    fx = {k: json.load(io.open(p, encoding='utf-8')) for k, p in paths.items()}
    if not (fx['w'].get('validate') or {}).get('wf_oos'):
        print('WFOOS PROBE: INCONCLUSIVE -- run_wfoos.json carries no validate.wf_oos')
        return INCONCLUSIVE

    data, why = attempt(chrome, root, alt, fx['b'], fx['w'], fx['bk'], fx['z'])
    if data is None or data.get('why') not in ('done', 'noboot'):
        print('WFOOS PROBE: attempt 1 gave no complete readout (%s), retrying once' % (why or (data or {}).get('why')))
        data, why = attempt(chrome, root, alt, fx['b'], fx['w'], fx['bk'], fx['z'])
    if data is None:
        print('WFOOS PROBE: INCONCLUSIVE -- %s' % why)
        return INCONCLUSIVE
    if data.get('why') == 'noboot':
        print('WFOOS PROBE: INCONCLUSIVE -- app did not boot; see preflight_boot')
        return INCONCLUSIVE
    if data.get('err'):
        print('WFOOS PROBE: FAIL -- probe threw: %s' % str(data['err'])[:800])
        return FAIL
    if data.get('why') != 'done':
        print('WFOOS PROBE: INCONCLUSIVE -- probe did not finish (why=%s, %s results)' % (data.get('why'), len(data.get('res') or [])))
        return INCONCLUSIVE

    if a.write_snapshot:
        io.open(snap_path, 'w', encoding='utf-8', newline='\n').write(json.dumps(
            {'note': 'Past Runs row text and order for runs WITHOUT a walk-forward block (run #306 as '
                     'saved, the synthetic book, a non-validated copy), per sort key. Written by '
                     'tools/wfoos_render_probe.py --write-snapshot from the pre-change build.',
             'VERSION': data.get('VERSION'), 'rows': data.get('snap')}, indent=1, ensure_ascii=False))
        print('WFOOS PROBE: snapshot written to %s (VERSION=%s)' % (snap_path, data.get('VERSION')))
        return PASS

    res = list(data.get('res') or [])
    if os.path.isfile(snap_path):
        want = json.load(io.open(snap_path, encoding='utf-8')).get('rows') or {}
        got = data.get('snap') or {}
        diffs = []
        for k in sorted(set(want) | set(got)):
            if want.get(k) != got.get(k):
                diffs.append('%s: %s  VS snapshot %s' % (k, json.dumps(got.get(k), ensure_ascii=False)[:300],
                                                         json.dumps(want.get(k), ensure_ascii=False)[:300]))
        res.append({'id': 'P6 Past Runs rows without a block match the pre-change snapshot', 'kind': 'NOREG',
                    'ok': not diffs, 'detail': ' ; '.join(diffs)[:900]})
    else:
        res.append({'id': 'P6 Past Runs snapshot', 'kind': 'NOREG', 'ok': False,
                    'detail': 'snapshot missing: run --write-snapshot against the pre-change build'})

    fails = [r for r in res if not r.get('ok')]
    n_new = sum(1 for r in res if r.get('kind') == 'NEW')
    n_new_ok = sum(1 for r in res if r.get('kind') == 'NEW' and r.get('ok'))
    n_nr = sum(1 for r in res if r.get('kind') == 'NOREG')
    n_nr_ok = sum(1 for r in res if r.get('kind') == 'NOREG' and r.get('ok'))
    if a.verbose or fails:
        for r in res:
            if a.verbose or not r.get('ok'):
                print('  %-4s %-5s %s%s' % ('ok' if r.get('ok') else 'FAIL', r.get('kind'), r.get('id'),
                                           '' if r.get('ok') and not a.verbose else ('  -- ' + str(r.get('detail'))[:500])))
    summary = 'NEW %d/%d, NOREG %d/%d' % (n_new_ok, n_new, n_nr_ok, n_nr)
    if fails:
        print('WFOOS PROBE: FAIL (VERSION=%s, %s, %.1fs)' % (data.get('VERSION'), summary, time.time() - t0))
        return FAIL
    print('WFOOS PROBE: PASS (VERSION=%s, %d assertions: %s, %.1fs)' % (data.get('VERSION'), len(res), summary, time.time() - t0))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
