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
var FIXB=__FIXB__, FIXW=__FIXW__, FIXBK=__FIXBK__;
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
    delete out._v;
    finish('done');
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){try{run();}catch(e){out.err=String(e&&e.stack?e.stack:e);finish('threw');}},2500);});
  setTimeout(function(){finish('backstop');},90000);
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


def attempt(chrome, root, alt_index, fixb, fixw, fixbk):
    pdir = os.path.join(root, '_wfoosprobe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, 'probe.html')
    js = (PROBE_JS.replace('__FIXB__', json.dumps(fixb)).replace('__FIXW__', json.dumps(fixw))
          .replace('__FIXBK__', json.dumps(fixbk)))
    io.open(ppath, 'w', encoding='utf-8').write(PROBE_HTML.replace('__JS__', js))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='wfoosprobe-')
    try:
        dom = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--user-data-dir=' + prof,
             '--virtual-time-budget=120000', '--dump-dom',
             'http://127.0.0.1:%d/_wfoosprobe/probe.html' % port],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300).stdout or ''
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
             (('b', 'run_report.json'), ('w', 'run_wfoos.json'), ('bk', 'run_book_synth.json'))}
    snap_path = os.path.join(fixd, 'wfoos_pastruns_snapshot.json')
    for k, p in paths.items():
        if not os.path.isfile(p):
            print('WFOOS PROBE: INCONCLUSIVE -- fixture missing: %s (build it with tools/make_wfoos_fixture.py)' % p)
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

    data, why = attempt(chrome, root, alt, fx['b'], fx['w'], fx['bk'])
    if data is None or data.get('why') not in ('done', 'noboot'):
        print('WFOOS PROBE: attempt 1 gave no complete readout (%s), retrying once' % (why or (data or {}).get('why')))
        data, why = attempt(chrome, root, alt, fx['b'], fx['w'], fx['bk'])
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
